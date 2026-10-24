"""BC 轮（2026-10-21，F03 同型）：misguided_metrics 重放对账的 rc==0 判绿收口。

缺陷族（与 BA/BB 同一族）：pytest 对"没有任何断言执行"的套件同样返回
``rc==0``——全 skip / xfail / deselect 的摘要行里 ``passed==0``。本模块的
**逐测试**四分类早已把 skip 单列为"无 pass/fail 信号"
（``UNCLASSIFIABLE_REASONS.skipped``），但**任务级**重放判绿此前只看
``rc==0``——同一工具内两层口径不一致。BA 轮 §7.2 将本工具登记为"保留
原口径"；BC 轮收口以下三处：

1. ``replay_detection``：fixed 侧 rc==0 还必须含有效通过（≥1 个真实
   ``pass``），否则记 ``None``（不可测，不误报检出）；
2. ``replay_fixed_green``（``analyze_task`` 内）：rc==0 但无有效通过 ⇒
   字段保持 ``None``（"未演示 green"），cross_check 表已有 none 桶；
3. ``_verdict_agreement``：fixed 侧 rc==0 但无有效通过 ⇒
   ``not_applicable``（不得记 mismatch 冤枉归档——既不能确认"转绿"
   也不能确认"仍红"）。

口径边界（与 BA/BB 一致）：**部分 skip 与真实 passed 并存仍算有效
通过**；干净 rc==0 行为逐位不变；buggy 侧 rc==0 → detection 仍为 0.0
（不是检出）；对账标签语义新增"口径修正"归因分支。

证据源：优先逐测试 ``outcomes``（junit/verbose，``run_side`` 原生产物），
回退 ``run_side`` 保留的 pytest 摘要行（``exec_summary_line``，仅内部
判定、不进报告 body）；两者都读不到 ⇒ False（fail-closed）。

真语料（只读静态）：3 份归档 MISGUIDED_REPORT（350 任务行 / 700 侧）中
rc==0 且无 pass 的侧为 **0**——本轮的 fail-closed 分支对历史归档读数
零影响（不回填、不重生成任何归档）。
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

import experiments.misguided_metrics as metrics

ROOT = Path(__file__).resolve().parents[1]

# ─── 微型 fixture（与 tests/test_misguided_metrics.py 同口径） ─────────────
BUGGY_ADD = "def add(a, b):\n    return a - b\n"
FIXED_ADD = "def add(a, b):\n    return a + b\n"

# F03 最小复现：buggy 上失败（a-b=0 ≠ 3），fixed 上 skip（a+b=3 ⇒ 跳过）
F2P_SKIP_ON_FIXED = """from add import add


def test_conditional():
    if add(1, 2) == 3:
        import pytest

        pytest.skip("fixed side: instrument unavailable")
    assert add(1, 2) == 3
"""

# 干净 F2P：buggy 上失败，fixed 上真实通过
CLEAN_F2P = """from add import add


def test_ok():
    assert add(1, 2) == 3
"""

# 两侧都 skip（buggy 侧 rc==0：不是检出，保持 0.0）
SKIP_BOTH = """from add import add


def test_s():
    import pytest

    pytest.skip("no signal")
"""


def _make_qxb_root(tmp_path: Path) -> Path:
    """最小 QuixBugs 口径数据根（buggy/fixed 两份 add.py）。"""
    root = tmp_path / "qxb"
    (root / "python_programs").mkdir(parents=True)
    (root / "correct_python_programs").mkdir(parents=True)
    (root / "python_programs" / "add.py").write_text(BUGGY_ADD, encoding="utf-8")
    (root / "correct_python_programs" / "add.py").write_text(FIXED_ADD, encoding="utf-8")
    return root


def _task_row(
    program: str,
    generated_test: str,
    fixed_code: str,
    *,
    task_id: str | None = None,
    detection: float | None = None,
    verdict: str | None = None,
) -> dict:
    return {
        "task_id": task_id or f"quixbugs__{program}",
        "generated_test": generated_test,
        "task_metadata": {
            "source": "quixbugs",
            "program": program,
            "test_cases": "",
            "fixed": fixed_code,
            "suggested_function": program,
            "is_cross_file": False,
        },
        "specificity_gate_verdict": verdict,
        "detection_rate": detection,
        "passed": False,
    }


def _side(**overrides) -> dict:
    """构造 run_side 形态的侧结果 dict（纯函数测试用；outcomes 优先判据）。"""
    base = {
        "ok": True,
        "collect_ok": True,
        "collect_reason": None,
        "collect_rc": 0,
        "collect_timed_out": False,
        "collected": ["test_generated.py::test_x"],
        "n_collected": 1,
        "exec_ok": True,
        "exec_rc": 0,
        "exec_timed_out": False,
        "exec_error": False,
        "outcomes": {"test_generated.py::test_x": "pass"},
        "n_outcomes": 1,
        "missing_reason": None,
    }
    base.update(overrides)
    return base


# ─── 1. 侧级有效通过谓词 ──────────────────────────────────────────────────
class TestSideHasEffectivePass:
    """_side_has_effective_pass：outcomes 优先、摘要行回退、fail-closed。"""

    def test_outcomes_with_pass_is_effective(self):
        assert metrics._side_has_effective_pass(_side(outcomes={"t": "pass"})) is True

    def test_outcomes_partial_skip_is_effective(self):
        assert metrics._side_has_effective_pass(_side(outcomes={"a": "pass", "b": "skip"})) is True

    def test_outcomes_all_skip_not_effective(self):
        assert metrics._side_has_effective_pass(_side(outcomes={"t": "skip"})) is False

    def test_outcomes_all_xfail_mapped_skip_not_effective(self):
        # junit 把 xfail 记为 skip：全 xfail ⇒ 无有效通过
        assert metrics._side_has_effective_pass(_side(outcomes={"t": "skip"})) is False

    def test_outcomes_fail_with_pass_not_effective(self):
        # 与共享谓词同口径：有 failed 不算有效通过
        assert metrics._side_has_effective_pass(_side(outcomes={"a": "pass", "b": "fail"})) is False

    def test_empty_outcomes_falls_back_to_summary_line(self):
        side = _side(outcomes={}, exec_summary_line="1 passed in 0.01s")
        assert metrics._side_has_effective_pass(side) is True

    def test_empty_outcomes_summary_skip_not_effective(self):
        side = _side(outcomes={}, exec_summary_line="1 skipped in 0.01s")
        assert metrics._side_has_effective_pass(side) is False

    def test_no_evidence_not_effective(self):
        assert metrics._side_has_effective_pass(_side(outcomes={})) is False
        assert metrics._side_has_effective_pass({}) is False


# ─── 2. replay_detection ─────────────────────────────────────────────────
class TestReplayDetectionEffectiveGreen:
    """fixed 侧 rc==0 还必须含有效通过；否则 None（不误报检出）。"""

    def test_f2p_with_skip_on_fixed_is_unmeasurable(self):
        buggy = _side(exec_rc=1, outcomes={"t": "fail"})
        fixed = _side(exec_rc=0, outcomes={"t": "skip"})
        assert metrics.replay_detection(buggy, fixed) is None

    def test_f2p_with_xfail_on_fixed_is_unmeasurable(self):
        # junit 把 xfail 记为 skip（本工具 outcomes 词汇）
        buggy = _side(exec_rc=1, outcomes={"t": "fail"})
        fixed = _side(exec_rc=0, outcomes={"t": "skip"})
        assert metrics.replay_detection(buggy, fixed, strict=True) is None

    def test_clean_f2p_stays_detected(self):
        buggy = _side(exec_rc=1, outcomes={"t": "fail"})
        fixed = _side(exec_rc=0, outcomes={"t": "pass"})
        assert metrics.replay_detection(buggy, fixed) == 1.0

    def test_partial_skip_f2p_stays_detected(self):
        buggy = _side(exec_rc=1, outcomes={"a": "fail"})
        fixed = _side(exec_rc=0, outcomes={"a": "pass", "b": "skip"})
        assert metrics.replay_detection(buggy, fixed) == 1.0

    def test_buggy_side_skip_is_not_detection(self):
        # buggy 侧 rc==0（含 all-skip）⇒ 0.0，不被新谓词改写
        buggy = _side(exec_rc=0, outcomes={"t": "skip"})
        fixed = _side(exec_rc=0, outcomes={"t": "pass"})
        assert metrics.replay_detection(buggy, fixed) == 0.0

    def test_both_sides_skip_is_zero(self):
        buggy = _side(exec_rc=0, outcomes={"t": "skip"})
        fixed = _side(exec_rc=0, outcomes={"t": "skip"})
        assert metrics.replay_detection(buggy, fixed) == 0.0

    def test_fixed_failure_stays_zero(self):
        buggy = _side(exec_rc=1, outcomes={"t": "fail"})
        fixed = _side(exec_rc=1, outcomes={"t": "fail"})
        assert metrics.replay_detection(buggy, fixed) == 0.0

    def test_collect_failure_and_timeout_unchanged(self):
        assert metrics.replay_detection(_side(collect_ok=False), _side()) is None
        assert metrics.replay_detection(_side(exec_timed_out=True), _side()) is None

    def test_summary_line_fallback_path(self):
        # outcomes 缺失（解析失败）时用摘要行判据
        buggy = _side(exec_rc=1, outcomes={}, exec_summary_line="1 failed in 0.01s")
        fixed = _side(exec_rc=0, outcomes={}, exec_summary_line="1 skipped in 0.01s")
        assert metrics.replay_detection(buggy, fixed) is None

    def test_disagreement_reason_names_caliber_change(self):
        reason = metrics._detection_disagreement_reason(
            1.0,
            None,
            None,
            _side(exec_rc=1, outcomes={"t": "fail"}),
            _side(exec_rc=0, outcomes={"t": "skip"}),
        )
        assert "旧口径" in reason
        assert "有效通过" in reason


# ─── 3. _verdict_agreement ───────────────────────────────────────────────
class TestVerdictAgreementEffectiveGreen:
    """fixed 侧 rc==0 但无有效通过 ⇒ not_applicable（不冤枉归档）。"""

    def test_specific_red_with_skip_fixed_not_applicable(self):
        fixed = _side(exec_rc=0, outcomes={"t": "skip"})
        tag, reason = metrics._verdict_agreement("specific_red", fixed)
        assert tag == "not_applicable"
        assert "无有效通过" in reason

    def test_over_red_with_skip_fixed_not_applicable(self):
        fixed = _side(exec_rc=0, outcomes={"t": "skip"})
        tag, _reason = metrics._verdict_agreement("over_red", fixed)
        assert tag == "not_applicable"

    def test_specific_red_clean_fixed_matches(self):
        fixed = _side(exec_rc=0, outcomes={"t": "pass"})
        assert metrics._verdict_agreement("specific_red", fixed)[0] == "match"

    def test_specific_red_red_fixed_mismatches(self):
        fixed = _side(exec_rc=1, outcomes={"t": "fail"})
        assert metrics._verdict_agreement("specific_red", fixed)[0] == "mismatch"

    def test_over_red_red_fixed_matches(self):
        fixed = _side(exec_rc=1, outcomes={"t": "fail"})
        assert metrics._verdict_agreement("over_red", fixed)[0] == "match"

    def test_unavailable_verdict_not_applicable(self):
        assert metrics._verdict_agreement("unavailable", _side(exec_rc=0))[0] == "not_applicable"
        assert metrics._verdict_agreement(None, _side(exec_rc=0))[0] == "not_applicable"


# ─── 4. analyze_task 端到端（真实 pytest 子进程，零 LLM） ─────────────────
class TestAnalyzeTaskReplayFixedGreen:
    """replay_fixed_green 与 replay_detection 在真实重放中的口径。"""

    def _run(self, tmp_path: Path, generated_test: str, **row_kwargs):
        root = _make_qxb_root(tmp_path)
        row = _task_row("add", generated_test, FIXED_ADD, **row_kwargs)
        return metrics.analyze_task(
            row,
            roots=[root],
            pytest_timeout_s=0.0,
            collect_timeout_s=30.0,
            file_timeout_s=30.0,
            siblings_cache={},
        )

    def test_clean_f2p_green_and_detected(self, tmp_path: Path):
        task = self._run(tmp_path, CLEAN_F2P)
        assert task["status"] == "ok"
        assert task["replay_fixed_green"] is True
        assert task["replay_detection"] == 1.0

    def test_skip_on_fixed_not_green_and_unmeasurable(self, tmp_path: Path):
        # fixed 侧全 skip：逐测试分类不可分类 ⇒ 任务级结构跳过，但重放
        # 判绿字段与对账归因必须在跳过前按新口径落值。
        task = self._run(tmp_path, F2P_SKIP_ON_FIXED, detection=1.0)
        assert task["status"] == "structural_skip"
        assert task["skip_reason"] == "no_classifiable_tests"
        assert task["replay_fixed_green"] is None  # 未演示 green，不是 False
        assert task["replay_detection"] is None  # 不误报检出
        assert task["detection_agreement"] == "replay_none"
        assert "旧口径" in task["detection_disagreement_reason"]

    def test_skip_on_both_sides_is_zero_detection(self, tmp_path: Path):
        # buggy 侧 rc==0（含 all-skip）⇒ detection 0.0（不是检出；BA 同序）
        task = self._run(tmp_path, SKIP_BOTH)
        assert task["replay_detection"] == 0.0
        assert task["replay_fixed_green"] is None

    def test_verdict_specific_red_with_skip_fixed_not_applicable(self, tmp_path: Path):
        task = self._run(tmp_path, F2P_SKIP_ON_FIXED, verdict="specific_red")
        assert task["verdict_agreement"] == "not_applicable"
        assert "无有效通过" in task["verdict_disagreement_reason"]

    def test_verdict_specific_red_clean_fixed_matches(self, tmp_path: Path):
        task = self._run(tmp_path, CLEAN_F2P, verdict="specific_red")
        assert task["verdict_agreement"] == "match"


# ─── 5. 真语料静态适用面（只读；不回填、不重生成归档） ────────────────────
ARCHIVED_REPORTS = (
    "emse_misguided_20261017",
    "emse_misguided_augment_20261017",
    "emse_misguided_docstring_anchor_20261017",
)


class TestArchivedCorpusApplicability:
    """归档重放报告中 rc==0 的侧全部含有效通过——本轮对历史读数零影响。"""

    def test_no_rc0_side_without_effective_pass(self):
        pytest.skip(
            "结果工件不在盘（2026-10-24 用户指令清除历史数据、DeepSeek 重跑前）："
            "语料前提缺失具名 skip，重跑落盘后自动恢复判定"
        )
        n_reports = 0
        n_sides = 0
        n_rc0 = 0
        n_rc0_no_pass = 0
        for name in ARCHIVED_REPORTS:
            path = ROOT / "experiments" / "results" / name / "MISGUIDED_REPORT.json"
            if not path.is_file():
                continue
            n_reports += 1
            data = json.loads(path.read_text(encoding="utf-8"))
            for arm in data["report"].get("arms", []):
                for task in arm.get("tasks", []):
                    for side_name in ("buggy_side", "fixed_side"):
                        side = task.get(side_name) or {}
                        n_sides += 1
                        oc = side.get("outcome_counts") or {}
                        if side.get("exec_rc") == 0:
                            n_rc0 += 1
                            if oc.get("pass", 0) == 0:
                                n_rc0_no_pass += 1
        assert n_reports == len(ARCHIVED_REPORTS), "归档报告缺失——静态面测量不成立"
        assert n_sides > 0
        assert n_rc0 > 0
        assert n_rc0_no_pass == 0, (
            f"发现 {n_rc0_no_pass} 个 rc==0 但无有效通过的侧——本轮的 fail-closed 分支将改变其归档读数，必须重新评估"
        )


# ─── 6. 接线源码锁 ───────────────────────────────────────────────────────
class TestWiringSourceLocks:
    """三处判绿点必须经过共享证据判据。"""

    def test_replay_detection_uses_side_predicate(self):
        src = inspect.getsource(metrics.replay_detection)
        assert "_side_has_effective_pass(fixed_side)" in src
        assert "return None" in src

    def test_analyze_task_guards_replay_fixed_green(self):
        src = inspect.getsource(metrics.analyze_task)
        assert "_side_has_effective_pass(fixed_side)" in src

    def test_verdict_agreement_uses_side_predicate(self):
        src = inspect.getsource(metrics._verdict_agreement)
        assert "_side_has_effective_pass(fixed_side)" in src
        assert "not_applicable" in src

    def test_run_side_retains_summary_line(self):
        src = inspect.getsource(metrics.run_side)
        assert "exec_summary_line" in src

    def test_side_record_excludes_summary_line(self):
        """报告 body schema 不变：摘要行只进内部判定。"""
        keys = metrics._side_record(_side(exec_summary_line="1 passed in 0.01s")).keys()
        assert "exec_summary_line" not in keys
