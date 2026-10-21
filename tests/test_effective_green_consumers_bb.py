"""BB 轮（2026-10-21，F03 同型）：rc==0 判绿消费点的剩余收口（experiments 侧 11 处）。

缺陷族（与 BA 轮同一族）：pytest 对"没有任何断言执行"的套件同样返回
``rc==0``——全 skip / xfail / xpass / deselect 的摘要行里 ``passed==0``。
BA 轮已收口 M1 detection/repair、repair_replay 重放、mutation_detection
基线四个消费点（共享谓词 ``_m1_metrics._suite_has_effective_pass``）；
本文件锁的是**同族的其余 experiments 侧消费点**：

1. ``emse_gold_conformance_audit._audit_one``：gold 自洽性审计
   （"pass" → 需有效通过，否则 ``unverifiable``）；
2. ``emse_optimization._rerun_on_fixed``：过红案例 P4 复跑
   （``passes_on_fixed`` → True/None/False 三态 + P5 新模式）；
3. ``gold_consistency_pruning``：块级剪枝保留判据
   （无有效通过的块按不一致剔除，不保留假绿块）；
4. ``emse_testlevel_detection``：任务级三段判据与 BA 后口径同步
   （fixed 无有效通过 → ``task_level_reproduced=None``）；
5. ``emse_ult_gold_diagnosis``：``_parse_pytest`` status 与归因
   （``unverifiable`` → ``undecidable_no_effective_pass``）；
6. ``suite_repair_pipeline._runs_green_on``：见证安全门/终检
   （无有效通过 → False，不得作为注入依据）；
7-10. 四个健全性门（``emse_ult_mutk_full`` / ``emse_quixbugs_mutk_full``
   / ``emse_test_sanity_audit`` / ``emse_ult_dfsmoke_accuracy``）：
   ``pass`` 需有效通过，否则 ``unverifiable`` 并阻断后续测量；
11. ``mutation_testing.compute_mutation_score``：基线诊断区分
   pre-existing failure（测试真在原始代码上全过）与
   ``baseline_no_effective_pass``（套件没跑起来）。

口径边界（与 BA 轮一致）：**部分 skip 与真实 passed 并存仍算有效通过**；
干净 rc==0 行为逐位不变；摘要不可解析 ⇒ fail-closed。

执行方式：与项目既有测试同口径——真实子进程 pytest（零 LLM、零网络），
仅归因/解析等纯函数直接调用。
"""

from __future__ import annotations

import inspect
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import pytest

import experiments.emse_gold_conformance_audit as gca
import experiments.emse_optimization as opt
import experiments.emse_quixbugs_mutk_full as qmf
import experiments.emse_test_sanity_audit as tsa
import experiments.emse_testlevel_detection as tld
import experiments.emse_ult_dfsmoke_accuracy as dfsm
import experiments.emse_ult_gold_diagnosis as gd
import experiments.emse_ult_mutk_full as umf
import experiments.gold_consistency_pruning as gcp
import experiments.mutation_testing as mt
import experiments.suite_repair_pipeline as srp
from experiments.mutation_testing import Mutant

ROOT = Path(__file__).resolve().parents[1]

# ─── 测试代码 fixture（真实 pytest 语义） ───────────────────────────────
CODE = "def add(a, b):\n    return a + b\n"
BUGGY_CODE = "def add(a, b):\n    return a + b + 1\n"

CLEAN = "from m import add\n\n\ndef test_ok():\n    assert add(1, 2) == 3\n"
SKIP_ALL = "from m import add\n\n\ndef test_s():\n    import pytest\n\n    pytest.skip('instrument unavailable')\n"
XFAIL_ALL = "from m import add\n\n\ndef test_x():\n    import pytest\n\n    pytest.xfail('expected failure')\n"
FAIL = "from m import add\n\n\ndef test_f():\n    assert add(1, 2) == 4\n"
PARTIAL_SKIP = (
    "from m import add\n\n\ndef test_real():\n    assert add(1, 2) == 3\n\n\n"
    "def test_s():\n    import pytest\n\n    pytest.skip('no signal')\n"
)
# 剪枝用：通过 / 失败 / 全 skip 三个独立测试块（整suite 在 gold 上不绿 → 进块级剪枝）
THREE_BLOCKS = (
    "from m import add\n\n\ndef test_a():\n    assert add(1, 2) == 3\n\n\n"
    "def test_b():\n    assert add(1, 2) == 4\n\n\n"
    "def test_c():\n    import pytest\n\n    pytest.skip('no signal')\n"
)


@dataclass
class _FakeTask:
    _task_id: str
    instance_code: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self._task_id


def _task(gold: str = CLEAN, fixed: str = CODE) -> _FakeTask:
    return _FakeTask(
        _task_id="probe__m",
        instance_code=BUGGY_CODE,
        metadata={"source": "synthetic", "fixed": fixed, "test_cases": gold, "is_cross_file": False},
    )


# ─── 1. emse_gold_conformance_audit ────────────────────────────────────
class TestGoldConformanceAudit:
    """gold 自洽性审计：rc==0 但无有效通过 ⇒ unverifiable（fail-closed）。"""

    def test_clean_gold_suite_passes(self):
        rec = gca._audit_one("synthetic", _task(gold=CLEAN))
        assert rec["status"] == "pass"
        assert rec["rc"] == 0

    def test_partial_skip_gold_suite_passes(self):
        rec = gca._audit_one("synthetic", _task(gold=PARTIAL_SKIP))
        assert rec["status"] == "pass"

    def test_all_skip_gold_suite_unverifiable(self):
        rec = gca._audit_one("synthetic", _task(gold=SKIP_ALL))
        assert rec["status"] == "unverifiable"
        assert rec["rc"] == 0
        assert "无有效通过" in rec["reason"]

    def test_all_xfail_gold_suite_unverifiable(self):
        rec = gca._audit_one("synthetic", _task(gold=XFAIL_ALL))
        assert rec["status"] == "unverifiable"

    def test_failing_gold_suite_still_fail(self):
        rec = gca._audit_one("synthetic", _task(gold=FAIL))
        assert rec["status"] == "fail"
        assert rec["failure_class"]

    def test_material_missing_unchanged(self):
        rec = gca._audit_one("synthetic", _task(gold=""))
        assert rec["status"] == "material_missing"


# ─── 2. emse_optimization._rerun_on_fixed ──────────────────────────────
class TestOptimizationRerunOnFixed:
    """P4 复跑：passes_on_fixed 三态 + P5 新模式。"""

    def test_clean_run_passes(self):
        out = opt._rerun_on_fixed("synthetic__m", CODE, CLEAN)
        assert out["passes_on_fixed"] is True
        assert out["failure_mode"] == "P4_passes_on_fixed"

    def test_partial_skip_run_passes(self):
        out = opt._rerun_on_fixed("synthetic__m", CODE, PARTIAL_SKIP)
        assert out["passes_on_fixed"] is True

    def test_all_skip_run_unmeasurable(self):
        out = opt._rerun_on_fixed("synthetic__m", CODE, SKIP_ALL)
        assert out["passes_on_fixed"] is None
        assert out["failure_mode"] == "P5_no_effective_pass_on_fixed"
        assert out["rc"] == 0

    def test_all_xfail_run_unmeasurable(self):
        out = opt._rerun_on_fixed("synthetic__m", CODE, XFAIL_ALL)
        assert out["passes_on_fixed"] is None
        assert out["failure_mode"] == "P5_no_effective_pass_on_fixed"

    def test_failing_run_not_passes(self):
        out = opt._rerun_on_fixed("synthetic__m", CODE, FAIL)
        assert out["passes_on_fixed"] is False
        assert out["failure_mode"].startswith("P1_")

    def test_over_red_failure_modes_smoke(self):
        """既有入口行为不变：真实复跑仍然 ok + P4。"""
        rows = [
            (
                "b1.json",
                {
                    "task_id": "synthetic__m",
                    "detection_first_status": "red_not_repaired",
                    "detection_rate": 0.0,
                    "generated_test": CLEAN,
                    "task_metadata": {"fixed": CODE},
                },
            )
        ]
        out = opt.over_red_failure_modes([{"task_id": "synthetic__m", "source_file": "b1.json"}], rows)
        assert out[0]["status"] == "ok"
        assert out[0]["passes_on_fixed"] is True


# ─── 3. gold_consistency_pruning ───────────────────────────────────────
class TestGoldConsistencyPruning:
    """块级剪枝：无有效通过的块按不一致剔除（不保留假绿块）。"""

    def test_already_green_on_clean_suite(self):
        res = gcp.prune_inconsistent_blocks(test_code=CLEAN, gold_code=CODE, module_name="m", timeout=30)
        assert res.available is True
        assert res.not_available_reason == "already_green_on_gold"

    def test_all_skip_suite_is_not_already_green(self):
        """原套件全 skip：没有"本就全绿"的证据，进入块级剪枝。"""
        res = gcp.prune_inconsistent_blocks(test_code=SKIP_ALL, gold_code=CODE, module_name="m", timeout=30)
        assert res.not_available_reason != "already_green_on_gold"

    def test_skip_block_pruned_with_reason(self):
        """失败块按 rc 剔除；全 skip 块按"无有效通过"剔除（不保留假绿块）。"""
        res = gcp.prune_inconsistent_blocks(test_code=THREE_BLOCKS, gold_code=CODE, module_name="m", timeout=30)
        assert res.available is True
        assert len(res.kept_blocks) == 1  # 仅 test_a
        assert len(res.pruned_blocks) == 2  # test_b（rc=1）+ test_c（无有效通过）
        assert any("无有效通过" in r for r in res.pruned_reasons)
        assert any("rc=1" in r for r in res.pruned_reasons)

    def test_partial_skip_suite_is_already_green(self):
        """部分 skip + 真实 passed = 有效绿：整 suite 无需剪枝（口径边界）。"""
        res = gcp.prune_inconsistent_blocks(test_code=PARTIAL_SKIP, gold_code=CODE, module_name="m", timeout=30)
        assert res.not_available_reason == "already_green_on_gold"

    def test_all_blocks_skip_not_available(self):
        code = "from m import add\n\n\ndef test_a():\n    import pytest\n\n    pytest.skip('x')\n"
        res = gcp.prune_inconsistent_blocks(test_code=code, gold_code=CODE, module_name="m", timeout=30)
        assert res.available is False
        assert res.not_available_reason == "all_blocks_inconsistent"


# ─── 4. emse_testlevel_detection ───────────────────────────────────────
class TestTestlevelEffectivePass:
    """_fixed_side_effective_pass 判据 + run_source 接线锁。"""

    def test_outcomes_with_pass_is_effective(self):
        assert tld._fixed_side_effective_pass({"outcomes": {"t1": "pass", "t2": "skip"}}) is True

    def test_outcomes_all_skip_not_effective(self):
        assert tld._fixed_side_effective_pass({"outcomes": {"t1": "skip", "t2": "xfail"}}) is False

    def test_outcomes_empty_fallback_to_stdout(self):
        assert tld._fixed_side_effective_pass({"outcomes": {}, "stdout": "1 passed in 0.01s"}) is True
        assert tld._fixed_side_effective_pass({"outcomes": {}, "stdout": "1 skipped in 0.01s"}) is False

    def test_no_evidence_not_effective(self):
        assert tld._fixed_side_effective_pass({"outcomes": {}, "stdout": ""}) is False

    def test_run_source_uses_helper(self):
        """接线锁：三段判据必须经过 _fixed_side_effective_pass。"""
        src = inspect.getsource(tld.run_source)
        assert "_fixed_side_effective_pass" in src
        assert "reproduced = None" in src


# ─── 5. emse_ult_gold_diagnosis ────────────────────────────────────────
class TestGoldDiagnosisStatus:
    """_parse_pytest status 三值 + 归因不得把无有效通过判成缺陷类。"""

    def test_clean_pass(self):
        r = gd._parse_pytest("test_x.py::test_a PASSED [100%]\n\n1 passed in 0.01s", 0)
        assert r["status"] == "pass"

    def test_all_skip_unverifiable(self):
        r = gd._parse_pytest("test_x.py::test_a SKIPPED [100%]\n\n1 skipped in 0.01s", 0)
        assert r["status"] == "unverifiable"
        assert r["n_passed"] == 0

    def test_all_xfail_unverifiable(self):
        r = gd._parse_pytest("test_x.py::test_a XFAIL\n\n1 xfailed in 0.01s", 0)
        assert r["status"] == "unverifiable"

    def test_failure_still_fail(self):
        r = gd._parse_pytest("test_x.py::test_a FAILED\n\n1 failed in 0.01s", 1)
        assert r["status"] == "fail"

    def test_collection_error_unchanged(self):
        r = gd._parse_pytest("ERROR collecting test_x.py\n\n1 error in 0.01s", 2)
        assert r["status"] == "collection_error"

    def test_attribute_unverifiable_is_undecidable(self):
        run = {"status": "unverifiable", "n_passed": 0, "bucket_by_test": {}, "buckets": {}}
        verdict, why = gd.attribute_task({"status": "pass", "n_passed": 1}, run, n_gold=1)
        assert verdict == "undecidable_no_effective_pass"
        assert "无有效通过" in why

    def test_attribute_clean_pass_unchanged(self):
        """既有归因行为不变（C 全过 ∧ O 全过 → project_only_defect）。"""
        run_c = {"status": "pass", "n_passed": 1, "bucket_by_test": {}, "buckets": {}}
        run_o = {"status": "pass", "n_passed": 1, "bucket_by_test": {}, "buckets": {}}
        verdict, _ = gd.attribute_task(run_o, run_c, n_gold=1)
        assert verdict == "project_only_defect"


# ─── 6. suite_repair_pipeline ──────────────────────────────────────────
class TestSuiteRepairGreen:
    """见证安全门/终检：无有效通过 ⇒ False（不得作为注入依据）。"""

    def test_clean_green(self):
        assert srp._runs_green_on(CODE, CLEAN, "m", 30) is True

    def test_all_skip_not_green(self):
        assert srp._runs_green_on(CODE, SKIP_ALL, "m", 30) is False

    def test_all_xfail_not_green(self):
        assert srp._runs_green_on(CODE, XFAIL_ALL, "m", 30) is False

    def test_failure_not_green(self):
        assert srp._runs_green_on(CODE, FAIL, "m", 30) is False


# ─── 7-10. 四个健全性门 ────────────────────────────────────────────────
class TestSanityGates:
    """健全性门：pass 需有效通过；unverifiable 阻断后续测量。

    四个门签名不同（``_run_one(module, fixed, test)`` vs
    ``_sanity_gate(fixed, test, module)``），统一经 lambda 归一到
    ``(fixed, test, module)`` 调用序。
    """

    GATES: ClassVar[list] = [
        lambda fixed, test, module: tsa._run_one(module, fixed, test),
        lambda fixed, test, module: dfsm._run_one(module, fixed, test),
        umf._sanity_gate,
        qmf._sanity_gate,
    ]

    @pytest.mark.parametrize("gate", GATES)
    def test_clean_pass(self, gate):
        assert gate(CODE, CLEAN, "m")["status"] == "pass"

    @pytest.mark.parametrize("gate", GATES)
    def test_all_skip_unverifiable(self, gate):
        r = gate(CODE, SKIP_ALL, "m")
        assert r["status"] == "unverifiable"
        assert r["rc"] == 0

    @pytest.mark.parametrize("gate", GATES)
    def test_all_xfail_unverifiable(self, gate):
        assert gate(CODE, XFAIL_ALL, "m")["status"] == "unverifiable"

    @pytest.mark.parametrize("gate", GATES)
    def test_failure_still_fail(self, gate):
        assert gate(CODE, FAIL, "m")["status"] == "fail"

    def test_mutk_measure_task_skips_unverifiable(self, monkeypatch):
        """mutk_full：健全性门 unverifiable ⇒ skipped + test_no_effective_pass_on_fixed。"""
        monkeypatch.setattr(umf, "is_cosmic_ray_available", lambda: True)
        monkeypatch.setattr(
            umf,
            "_sanity_gate",
            lambda fixed_code, test_code, module_name: {"status": "unverifiable", "rc": 0, "wall_s": 0.1},
        )
        row = {"task_id": "ult__f", "task_metadata": {"fixed": CODE, "function_name": "f"}, "generated_test": SKIP_ALL}
        out = umf.measure_task(row, "generated")
        assert out["skipped"] is True
        assert out["skip_reason"] == "test_no_effective_pass_on_fixed"
        assert out["sanity"]["status"] == "unverifiable"

    def test_quixbugs_measure_task_skips_unverifiable(self, monkeypatch):
        monkeypatch.setattr(qmf, "is_cosmic_ray_available", lambda: True)
        monkeypatch.setattr(
            qmf,
            "_sanity_gate",
            lambda fixed_code, test_code, module_name: {"status": "unverifiable", "rc": 0, "wall_s": 0.1},
        )
        row = {"task_id": "quixbugs__f", "task_metadata": {"fixed": CODE}, "generated_test": SKIP_ALL}
        out = qmf.measure_task(row)
        assert out["skipped"] is True
        assert out["skip_reason"] == "test_no_effective_pass_on_fixed"

    def test_mutk_measure_task_skips_fail_unchanged(self, monkeypatch):
        """回归：fail 的跳过理由保持 test_fails_on_fixed（未被新状态吞并）。"""
        monkeypatch.setattr(umf, "is_cosmic_ray_available", lambda: True)
        monkeypatch.setattr(
            umf, "_sanity_gate", lambda fixed_code, test_code, module_name: {"status": "fail", "rc": 1, "wall_s": 0.1}
        )
        row = {"task_id": "ult__f", "task_metadata": {"fixed": CODE, "function_name": "f"}, "generated_test": FAIL}
        out = umf.measure_task(row, "generated")
        assert out["skip_reason"] == "test_fails_on_fixed"


# ─── 11. mutation_testing 基线诊断 ─────────────────────────────────────
class TestMutationTestingBaseline:
    """基线三态：杀死 / pre-existing failure / baseline_no_effective_pass。"""

    def test_detail_reports_effective_pass(self):
        detail: list[dict[str, Any]] = []
        killed = mt._run_mutant_tests(
            Mutant(code=CODE, mutant_type="original", description="probe"), CLEAN, "m", 30, detail=detail
        )
        assert killed is False  # 测试在正确代码上全过
        assert detail[-1]["effective_pass"] is True

    def test_detail_reports_no_effective_pass(self):
        detail: list[dict[str, Any]] = []
        killed = mt._run_mutant_tests(
            Mutant(code=CODE, mutant_type="original", description="probe"), SKIP_ALL, "m", 30, detail=detail
        )
        assert killed is False
        assert detail[-1] == {"rc": 0, "effective_pass": False}

    def test_detail_reports_kill(self):
        detail: list[dict[str, Any]] = []
        killed = mt._run_mutant_tests(
            Mutant(code=CODE, mutant_type="original", description="probe"), FAIL, "m", 30, detail=detail
        )
        assert killed is True  # rc==1 = 杀死
        assert detail[-1]["rc"] == 1
        assert detail[-1]["effective_pass"] is False

    def test_score_baseline_pre_existing_failure(self):
        """测试在原始（正确）代码上全过 ⇒ pre_existing_failures=1（历史口径不变）。"""
        out = mt.compute_mutation_score(CODE, CLEAN, "m.py", max_mutants=3, timeout_seconds=30)
        assert out["pre_existing_failures"] == 1
        assert out["baseline_no_effective_pass"] is False

    def test_score_baseline_no_effective_pass(self):
        """全 skip 套件 ⇒ baseline_no_effective_pass=1，pre_existing=0（不得误诊）。"""
        out = mt.compute_mutation_score(BUGGY_CODE, SKIP_ALL, "m.py", max_mutants=3, timeout_seconds=30)
        assert out["baseline_no_effective_pass"] is True
        assert out["pre_existing_failures"] == 0
        # 保守口径不变：没跑起来不得夸大成"测试杀死了变异体"
        assert out["mutation_score"] == 0.0

    def test_score_killing_baseline_clean(self):
        """测试真的在原始缺陷代码上失败 ⇒ 两个基线标记均为 0。"""
        out = mt.compute_mutation_score(BUGGY_CODE, CLEAN, "m.py", max_mutants=3, timeout_seconds=30)
        assert out["pre_existing_failures"] == 0
        assert out["baseline_no_effective_pass"] is False


# ─── 真语料静态适用面（只读；不回填、不改写归档） ──────────────────────
class TestRealCorpusApplicability:
    """归档语料中不存在模块级全 skip 套件——本轮的 fail-closed 分支在
    已归档批次上零命中（静态适用≠已证实假阳性；机制由上面的锁证明）。"""

    def test_no_module_level_all_skip_in_archive(self):
        n_bench = 0
        n_module_level_skip = 0
        for path in sorted(ROOT.glob("experiments/results/**/benchmark_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            n_bench += 1
            for arm in (data.get("results") or {}).values():
                for row in arm.get("details") or []:
                    test = str(row.get("generated_test") or "")
                    if "allow_module_level=True" in test or "@pytest.mark.skip" in test.split("\n\n", maxsplit=1)[0]:
                        n_module_level_skip += 1
        assert n_bench > 0
        assert n_module_level_skip == 0

    def test_gold_suites_have_no_module_level_skip(self):
        """gold 套件（736 份唯一）不含模块级 skip 标记（与 BA 轮语料复核一致）。"""
        n_gold = 0
        n_module_level_skip = 0
        seen: set[str] = set()
        for path in sorted(ROOT.glob("experiments/results/**/benchmark_*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for arm in (data.get("results") or {}).values():
                for row in arm.get("details") or []:
                    md = row.get("task_metadata") or {}
                    gold = str(md.get("test_cases") or "")
                    if not gold.strip() or gold in seen:
                        continue
                    seen.add(gold)
                    n_gold += 1
                    if "allow_module_level=True" in gold or "@pytest.mark.skip" in gold.split("\n\n", maxsplit=1)[0]:
                        n_module_level_skip += 1
        assert n_gold > 0
        assert n_module_level_skip == 0
