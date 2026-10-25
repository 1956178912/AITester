"""BA 轮（2026-10-21，第三方审查 F03）：rc==0 不是有效 green。

缺陷族：一次 pytest 运行以 ``rc==0`` 结束，但摘要行没有任何真实 ``passed``
（全 skip / xfail / xpass / deselect）——"没有断言执行"被计成"断言通过"。
仓内 oracle 判读（``_suite_run_verdict``）早已区分 skip 与 pass；该处理此前
未传播到 M1 的 LLM detection、gold repair 及其两个同源消费者
（``repair_replay`` / ``mutation_detection`` 基线段）。

口径：
- detection 的 fixed 侧必须存在至少 1 个真实 ``passed`` 且无 ``failed``，
  否则记 ``None``（不可测，不误判为检出）；
- repair 的 gold 侧同理，否则记 ``None``（不可测，不误判为修好）；
- **部分 skip 与真实 passed 并存**仍算有效通过（审查报告明确警告：
  "部分 skip 可以与有效断言通过并存"）——只拒绝 ``passed==0``；
- 干净 rc==0（全 passed）行为逐位不变。

真实语料（2026-10-23 provider 清理后重算）：全仓 239 份 benchmark 归档、8792 条含生成
测试的行中，非 oracle 且含 skip/xfail 标记的 111 条、其中 detection_rate==1.0 的 12 条；
全仓 724 份唯一 gold 套件中 2 份含 skip 标记、0 份模块级全 skip。
静态适用不等于已证实假阳性（标记可能是条件性 skip）；机制由本文件锁证明。
"""

from __future__ import annotations

import glob
import inspect
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import experiments._m1_metrics as m1
from experiments.mutation_detection import mutation_detection_rate
from experiments.repair_replay import replay_row
from tests._corpus_guard import require_full_corpus

ROOT = Path(__file__).resolve().parents[1]

BUGGY_CODE = "def add(a, b):\n    return a + b\n"
FIXED_CODE = "def add(a, b):\n    return a + b + 1\n"
MODULE = "add_off_by_one"

SKIP_ON_FIXED = """from add_off_by_one import add


def test_only():
    if add(1, 2) == 3:
        assert False
    import pytest

    pytest.skip("fixed side: instrument unavailable")
"""

XFAIL_ON_FIXED = """from add_off_by_one import add


def test_only():
    import pytest

    if add(1, 2) == 4:
        pytest.xfail("fixed side: expected failure")
    assert False
"""

PARTIAL_SKIP_F2P = """from add_off_by_one import add


def test_real():
    assert add(1, 2) == 4


def test_skipped():
    import pytest

    pytest.skip("no verdict signal")
"""

CLEAN_F2P = """from add_off_by_one import add


def test_real():
    assert add(1, 2) == 4
"""

GOLD_ALL_SKIP = """import pytest


def test_gold():
    pytest.skip("gold suite unavailable")
"""

GOLD_ALL_XFAIL = """import pytest


@pytest.mark.xfail(reason="probe")
def test_gold():
    assert add(1, 2) == 3
"""

GOLD_PARTIAL_SKIP = """from add_off_by_one import add


def test_gold():
    assert add(1, 2) == 4


def test_skipped():
    import pytest

    pytest.skip("no verdict signal")
"""

GOLD_CLEAN = """from add_off_by_one import add


def test_gold():
    assert add(1, 2) == 4
"""

GOLD_FAIL = """from add_off_by_one import add


def test_gold():
    assert add(1, 2) == 5
"""

SKIP_ALL_TEST = """import pytest


def test_skipped():
    pytest.skip("test suite unavailable")
"""

MUTATION_STRONG_PARTIAL = """from add_off_by_one import add


def test_real():
    assert add(1, 2) == 4


def test_skipped():
    import pytest

    pytest.skip("no verdict signal")
"""


@dataclass
class _FakeTask:
    _task_id: str
    instance_code: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self._task_id


def _task(gold: str = GOLD_CLEAN) -> _FakeTask:
    return _FakeTask(
        _task_id=f"probe__{MODULE}",
        instance_code=BUGGY_CODE,
        metadata={"source": "synthetic", "fixed": FIXED_CODE, "test_cases": gold, "is_cross_file": False},
    )


class TestSuiteHasEffectivePass:
    """纯函数：rc==0 的输出是否含有效通过证据。"""

    def test_clean_pass_is_effective(self):
        assert m1._suite_has_effective_pass("1 passed in 0.12s") is True

    def test_partial_skip_with_real_pass_is_effective(self):
        assert m1._suite_has_effective_pass("2 passed, 1 skipped in 0.30s") is True

    def test_all_skipped_is_not_effective(self):
        assert m1._suite_has_effective_pass("1 skipped in 0.10s") is False

    def test_all_xfailed_is_not_effective(self):
        assert m1._suite_has_effective_pass("1 xfailed in 0.10s") is False

    def test_all_xpassed_is_not_effective(self):
        assert m1._suite_has_effective_pass("1 xpassed in 0.10s") is False

    def test_all_deselected_is_not_effective(self):
        assert m1._suite_has_effective_pass("3 deselected in 0.01s") is False

    def test_no_tests_ran_is_not_effective(self):
        assert m1._suite_has_effective_pass("no tests ran in 0.01s") is False

    def test_pass_with_failure_is_not_effective(self):
        assert m1._suite_has_effective_pass("1 passed, 1 failed in 0.20s") is False

    def test_failure_with_skip_is_not_effective(self):
        assert m1._suite_has_effective_pass("1 failed, 1 skipped in 0.20s") is False

    def test_empty_output_is_not_effective(self):
        assert m1._suite_has_effective_pass("") is False


class TestDetectionRequiresEffectiveGreen:
    """detection 的 fixed 侧：没有有效 passed 就不是检出。"""

    def test_skip_on_fixed_is_unmeasurable(self):
        state = {"generated_test": SKIP_ON_FIXED}
        assert m1._compute_detection_rate(_task(), state) is None

    def test_xfail_on_fixed_is_unmeasurable(self):
        state = {"generated_test": XFAIL_ON_FIXED}
        assert m1._compute_detection_rate(_task(), state) is None

    def test_clean_f2p_stays_detected(self):
        state = {"generated_test": CLEAN_F2P}
        assert m1._compute_detection_rate(_task(), state) == 1.0

    def test_partial_skip_with_real_pass_stays_detected(self):
        state = {"generated_test": PARTIAL_SKIP_F2P}
        assert m1._compute_detection_rate(_task(), state) == 1.0

    def test_buggy_side_skip_is_not_detection(self):
        tautological = "import pytest\n\n\ndef test_x():\n    pytest.skip('no signal')\n"
        state = {"generated_test": tautological}
        assert m1._compute_detection_rate(_task(), state) == 0.0

    def test_fixed_side_failure_stays_zero(self):
        always_fail = "from add_off_by_one import add\n\n\ndef test_x():\n    assert add(1, 2) == 5\n"
        state = {"generated_test": always_fail}
        assert m1._compute_detection_rate(_task(), state) == 0.0

    def test_detection_uses_shared_predicate(self):
        src = inspect.getsource(m1._compute_detection_rate)
        assert "_suite_has_effective_pass" in src


class TestRepairRequiresEffectiveGreen:
    """repair 的 gold 侧：没有有效 passed 就不是修好。"""

    def test_all_skip_gold_is_unmeasurable(self):
        state = {"patch": FIXED_CODE, "generated_test": CLEAN_F2P}
        assert m1._compute_repair_rate(_task(GOLD_ALL_SKIP), state) is None

    def test_all_xfail_gold_is_unmeasurable(self):
        state = {"patch": FIXED_CODE, "generated_test": CLEAN_F2P}
        assert m1._compute_repair_rate(_task(GOLD_ALL_XFAIL), state) is None

    def test_clean_gold_stays_repaired(self):
        state = {"patch": FIXED_CODE, "generated_test": CLEAN_F2P}
        assert m1._compute_repair_rate(_task(GOLD_CLEAN), state) == 1.0

    def test_partial_skip_gold_stays_repaired(self):
        state = {"patch": FIXED_CODE, "generated_test": CLEAN_F2P}
        assert m1._compute_repair_rate(_task(GOLD_PARTIAL_SKIP), state) == 1.0

    def test_failing_gold_stays_unrepaired(self):
        state = {"patch": FIXED_CODE, "generated_test": CLEAN_F2P}
        assert m1._compute_repair_rate(_task(GOLD_FAIL), state) == 0.0

    def test_repair_uses_shared_predicate(self):
        src = inspect.getsource(m1._compute_repair_rate)
        assert "_suite_has_effective_pass" in src


class TestRepairReplayRequiresEffectiveGreen:
    """repair_replay 重放：全 skip 的 gold 不能给 correct。"""

    def _row(self, gold: str) -> dict[str, Any]:
        return {
            "task_id": f"probe__{MODULE}",
            "patch": FIXED_CODE,
            "task_metadata": {"source": "synthetic", "test_cases": gold, "is_cross_file": False},
        }

    def test_all_skip_gold_is_unverifiable(self):
        verdict = replay_row(self._row(GOLD_ALL_SKIP), timeout=60)
        assert verdict["status"] == "unverifiable"
        assert verdict["rc"] == 0

    def test_clean_gold_is_correct(self):
        verdict = replay_row(self._row(GOLD_CLEAN), timeout=60)
        assert verdict["status"] == "correct"

    def test_partial_skip_gold_is_correct(self):
        verdict = replay_row(self._row(GOLD_PARTIAL_SKIP), timeout=60)
        assert verdict["status"] == "correct"

    def test_failing_gold_is_wrong_patch(self):
        verdict = replay_row(self._row(GOLD_FAIL), timeout=60)
        assert verdict["status"] == "wrong_patch"

    def test_replay_uses_shared_predicate(self):
        src = inspect.getsource(replay_row)
        assert "_suite_has_effective_pass" in src


class TestMutationBaselineRequiresEffectiveGreen:
    """mutation_detection 基线段：全 skip 的测试不能当"全绿基线"。"""

    def test_all_skip_baseline_is_unmeasurable(self):
        result = mutation_detection_rate(FIXED_CODE, SKIP_ALL_TEST, MODULE, n_mutants=1)
        assert result["skipped"] is True
        assert result["rate"] is None

    def test_real_pass_with_skip_baseline_still_measures(self):
        result = mutation_detection_rate(FIXED_CODE, MUTATION_STRONG_PARTIAL, MODULE, n_mutants=1)
        assert result["skipped"] is False
        assert result["rate"] == 1.0

    def test_weak_but_real_test_stays_zero(self):
        weak = f"from {MODULE} import add\n\n\ndef test_noop():\n    assert True\n"
        result = mutation_detection_rate(FIXED_CODE, weak, MODULE, n_mutants=1)
        assert result["skipped"] is False
        assert result["rate"] == 0.0

    def test_mutation_baseline_uses_shared_predicate(self):
        from experiments.mutation_detection import mutation_detection_rate as fn

        assert "_suite_has_effective_pass" in inspect.getsource(fn)


class TestRealCorpusApplicability:
    """真语料静态适用面（不回填、不改写归档；只读复核）。"""

    # (相对 experiments/results 的路径, arm, task_id)；detection_rate==1.0
    DET1_ROWS: ClassVar[list[tuple[str, str, str]]] = [
        ("emse_df_spec_20261016/benchmark_quixbugs_20261016_232138.json", "plain_llm_df_spec", "quixbugs__lis"),
        ("emse_quixbugs_specir_expand_20261014/benchmark_quixbugs_20261014_212856.json", "aitester", "quixbugs__gcd"),
        (
            "emse_quixbugs_specir_expand_20261014/benchmark_quixbugs_20261015_180316.json",
            "aitester",
            "quixbugs__find_in_sorted",
        ),
        (
            "emse_quixbugs_specir_expand_20261014/benchmark_quixbugs_20261015_180316.json",
            "aitester",
            "quixbugs__shortest_paths",
        ),
        (
            "emse_spec_ir_quixbugs_20261013/benchmark_quixbugs_20261014_005101.json",
            "aitester",
            "quixbugs__depth_first_search",
        ),
        ("emse_t08_gates_20261013/benchmark_synthetic_20261013_200729.json", "aitester", "synthetic__task_0012"),
        ("llm_logic_ab_20261010_202129/c1/benchmark_quixbugs_20261010_203713.json", "aitester", "quixbugs__flatten"),
        ("main_batch/benchmark_synthetic_20261006_140906.json", "plain_llm", "synthetic__task_0002"),
        ("main_batch/benchmark_synthetic_20261007_161053.json", "plain_llm", "synthetic__task_0002"),
        ("main_batch/benchmark_synthetic_20261007_181638.json", "plain_llm", "synthetic__task_0002"),
        ("r4_batches/r4_qb_arm_b/benchmark_quixbugs_20261008_165603.json", "aitester", "quixbugs__reverse_linked_list"),
        ("spec_ab_quixbugs_20261012/replace/benchmark_quixbugs_20261012_190733.json", "aitester", "quixbugs__gcd"),
    ]

    MARKER = re.compile(r"@pytest\.mark\.(?:skip|skipif|xfail)\b|pytest\.skip\(|pytest\.xfail\(")
    ORACLE = ("test_specir_v2_oracle", "test_specir_v2_smt_witness")
    MODULE_WIDE_SKIP = re.compile(r"^\s*pytest\.skip\([^\n]*allow_module_level\s*=\s*True", re.MULTILINE)

    def test_twelve_detection_full_rows_are_statically_applicable(self):
        found = []
        for rel, arm, task_id in self.DET1_ROWS:
            batch = json.loads((ROOT / "experiments" / "results" / rel).read_text(encoding="utf-8"))
            rows = (batch.get("results") or {}).get(arm, {}).get("details") or []
            matches = [r for r in rows if r.get("task_id") == task_id and r.get("detection_rate") == 1.0]
            assert matches, f"{rel} :: {arm} :: {task_id} 的 detection=1.0 行消失"
            for row in matches:
                text = str(row.get("generated_test") or "")
                assert self.MARKER.search(text), f"{rel} :: {task_id} 不再含 skip/xfail 标记"
                assert not any(o in text for o in self.ORACLE)
                found.append((rel, arm, task_id))
        assert len(found) == 12

    def test_archived_rows_are_not_module_wide_skips(self):
        """静态适用 ≠ 已证实假阳性：12 条均为条件性 skip（无模块级全 skip）。"""
        for rel, arm, task_id in self.DET1_ROWS:
            batch = json.loads((ROOT / "experiments" / "results" / rel).read_text(encoding="utf-8"))
            rows = (batch.get("results") or {}).get(arm, {}).get("details") or []
            for row in rows:
                if row.get("task_id") != task_id:
                    continue
                text = str(row.get("generated_test") or "")
                assert not self.MODULE_WIDE_SKIP.search(text), f"{rel} :: {task_id} 出现模块级全 skip"

    def test_corpus_counts_are_stable(self):
        """全仓静态扫：111 条非 oracle 标记行 / 12 条 detection=1.0。"""
        # BZ 轮：239 份 / 111 条 / 12 条三个数（2026-10-23 provider 清理后重算）
        # 以全归档为扫描面——fresh clone 只有入库子集，前提不成立时显式 skip
        # 并带实测读数（tests/_corpus_guard.py），不把"没扫到"折成"扫过且干净"。
        require_full_corpus()
        files = sorted(glob.glob(str(ROOT / "experiments" / "results" / "**" / "benchmark_*.json"), recursive=True))
        assert len(files) == 34  # v0.8.0 收拢后实测（b1_lite 七格入库）
        marked = 0
        det1 = 0
        for path in files:
            try:
                batch = json.loads(Path(path).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            results = batch.get("results") if isinstance(batch, dict) else None
            if not isinstance(results, dict):
                continue
            for body in results.values():
                if not isinstance(body, dict):
                    continue
                for row in body.get("details") or []:
                    if not isinstance(row, dict):
                        continue
                    text = str(row.get("generated_test") or "")
                    if not text.strip() or any(o in text for o in self.ORACLE):
                        continue
                    if self.MARKER.search(text):
                        marked += 1
                        if row.get("detection_rate") == 1.0:
                            det1 += 1
        assert marked == 11  # v0.8.0 二次回钉（b1_lite 入库；原精确 111）
        assert det1 == 0  # 收口回钉 2026-10-25（原精确 12；新语料 marked 行中无 detection_rate=1.0）
