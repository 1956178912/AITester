"""R5（2026-10-05 审查建议）：变异检出率（mutation detection rate）回归测试。

覆盖 experiments/mutation_detection.mutation_detection_rate 的核心口径：
- 强断言测试杀死变异体 → rate=1.0；弱断言测试（assert True）杀不动 → rate=0.0；
- 测试在 gold fixed 代码上不绿 → rate=None + skipped=True（测试本身坏则
  无法裁决，保守不误报）；
- 变异体上的收集错误（模块级断言在 import 期失败 → rc=2）不算检出；
- n_mutants 超过可得变异体数 → 用实际可得数，不越界不误报；
- seed 固定 → 两次调用的采样与检出数产物稳定；
- run_benchmark 接线（_compute_mutation_detection_for_baseline）：mock 口径
  验证字段写回与缺 gold fixed 材料时 None 跳过。

子进程口径说明：每个用例触发 1 次基线 + ≤ n_mutants 次变异体 pytest 子进程
（微型模块，单次 ~0.3-0.5s），单用例 < 20s；接线用例全部 mock，零子进程。

变异体产物依据（MutationGenerator 实测，GRADE_FIXED 共 6 个）：
numeric_offset（90→91）/ boundary_shift（>=→>）/ return_void ×2（A、B 分支）/
return_empty ×2；ADD_FIXED 仅 1 个（return_void；return_empty 产出的
return None 与其代码相同，被代码级去重消除）。
"""

from typing import Any

import experiments.run_benchmark as rb
from experiments.mutation_detection import _mutant_detected, mutation_detection_rate
from src.datasets.dataset_loader import BenchmarkTask

# ─── 共享测试材料 ─────────────────────────────────────────────────────────────

# gold 修复代码（变异基底）：>=90 得 "A"，否则 "B"（含比较常量 + 双分支
# 返回值，能产出 4 类共 6 个变异体）
GRADE_FIXED = 'def grade(score):\n    if score >= 90:\n        return "A"\n    return "B"\n'

# 强断言测试：钉死边界（90）与双分支返回值 → 能杀死全部 6 个变异体
STRONG_TEST = 'from r5mod_grade import grade\n\n\ndef test_grade_a_boundary():\n    assert grade(90) == "A"\n\n\ndef test_grade_b():\n    assert grade(89) == "B"\n'

# 弱断言测试：只跑不验（assert True）→ 杀不动任何变异体
WEAK_TEST = "from r5mod_grade import grade\n\n\ndef test_grade_noop():\n    assert True\n"

# 坏测试：在 gold fixed 代码上就不绿 → 无法裁决（保守 None）
BROKEN_TEST = 'from r5mod_grade import grade\n\n\ndef test_wrong_expectation():\n    assert grade(90) == "Z"\n'

# 收集错误测试：模块级断言在 pytest 收集（import）阶段执行——变异体使
# grade(90) 偏离 "A" 时 import 期即失败 → rc=2 收集错误，按口径不算检出
COLLECTION_ERROR_TEST = 'from r5mod_coll import grade\n\nassert grade(90) == "A"\n\n\ndef test_ok():\n    assert True\n'

# 单变异体代码（ADD_FIXED 仅 1 个可得变异体，n_mutants 越界用实际数）
ADD_FIXED = "def add(a, b):\n    return a + b\n"
ADD_STRONG_TEST = "from r5mod_add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"

# 部分检出测试：只断言远离边界的返回值 → 仅杀死 return_void/return_empty
# 类变异体（2/6），boundary/numeric 类存活——用于 seed 稳定性的真判定
SELECTIVE_TEST = 'from r5mod_sel import grade\n\n\ndef test_return_value_only():\n    assert grade(95) == "A"\n'


class TestMutationDetectionRate:
    """mutation_detection_rate 纯函数级回归（真实子进程，微型模块）。"""

    def test_strong_test_kills_all_mutants(self):
        """强断言测试：fixed 基线全绿 + 全部变异体被检出 → rate=1.0。"""
        result = mutation_detection_rate(GRADE_FIXED, STRONG_TEST, "r5mod_grade", n_mutants=6)
        assert result["skipped"] is False
        assert result["mutants_total"] == 6
        assert result["mutants_killed"] == 6
        assert result["rate"] == 1.0

    def test_weak_test_kills_none(self):
        """弱断言测试（assert True）：fixed 基线全绿但杀不动变异体 → rate=0.0。"""
        result = mutation_detection_rate(GRADE_FIXED, WEAK_TEST, "r5mod_grade", n_mutants=6)
        assert result["skipped"] is False
        assert result["mutants_total"] == 6
        assert result["mutants_killed"] == 0
        assert result["rate"] == 0.0

    def test_broken_test_on_fixed_skips_with_none(self):
        """测试在 fixed 上不绿 → 无法裁决：rate=None + skipped=True（保守不误报 0）。"""
        result = mutation_detection_rate(GRADE_FIXED, BROKEN_TEST, "r5mod_grade", n_mutants=6)
        assert result["skipped"] is True
        assert result["rate"] is None
        assert "不绿" in result["skip_reason"]

    def test_collection_error_not_counted_as_detection(self):
        """收集错误不算检出：变异体使模块级断言在收集期失败（rc=2）→ rate=0.0。

        场景：测试唯一的"检出力"经 import 期断言显现，但那是收集错误
        （套件根本没跑起来），按保守口径不得记为检出。
        """
        result = mutation_detection_rate(GRADE_FIXED, COLLECTION_ERROR_TEST, "r5mod_coll", n_mutants=6)
        assert result["skipped"] is False, "测试在 fixed 上全绿（模块级断言通过），不应跳过"
        assert result["mutants_total"] == 6
        assert result["mutants_killed"] == 0, "收集错误（rc=2）的变异体不算检出"
        assert result["rate"] == 0.0

    def test_n_mutants_over_available_uses_actual_count(self):
        """n_mutants 超过可得变异体数：用实际可得数（1），不越界不误报。"""
        result = mutation_detection_rate(ADD_FIXED, ADD_STRONG_TEST, "r5mod_add", n_mutants=50)
        assert result["skipped"] is False
        assert result["mutants_total"] == 1, "ADD_FIXED 仅 1 个可得变异体（return_void）"
        assert result["mutants_killed"] == 1
        assert result["rate"] == 1.0

    def test_seed_fixed_produces_stable_results(self):
        """seed 固定产物稳定：部分检出场景下两次调用采样与检出数一致。"""
        first = mutation_detection_rate(GRADE_FIXED, SELECTIVE_TEST, "r5mod_sel", n_mutants=3, seed=42)
        second = mutation_detection_rate(GRADE_FIXED, SELECTIVE_TEST, "r5mod_sel", n_mutants=3, seed=42)
        assert first["skipped"] is False and second["skipped"] is False
        assert first["mutants_total"] == second["mutants_total"] == 3
        assert first["mutants_killed"] == second["mutants_killed"]
        assert first["rate"] == second["rate"]
        # 部分检出 sanity：只断言返回值的测试至多杀死 return_void/return_empty
        # 类（采样 3 个时杀死数应在 0-2 之间，证明采样确实生效而非全杀/全活）
        assert 0 <= first["mutants_killed"] <= 2

    def test_empty_inputs_skip_with_none(self):
        """输入材料缺失（空 fixed / 空测试）→ rate=None + skipped=True。"""
        result = mutation_detection_rate("", STRONG_TEST, "r5mod_grade")
        assert result["skipped"] is True
        assert result["rate"] is None
        result2 = mutation_detection_rate(GRADE_FIXED, "   ", "r5mod_grade")
        assert result2["skipped"] is True
        assert result2["rate"] is None

    def test_no_mutable_statements_skips_with_none(self):
        """无可变异语句（纯 pass 代码）→ rate=None + skipped=True。"""
        result = mutation_detection_rate(
            "def noop():\n    pass\n",
            "from r5mod_pass import noop\n\n\ndef test_noop():\n    noop()\n",
            "r5mod_pass",
        )
        assert result["skipped"] is True
        assert result["rate"] is None
        assert "无可变异" in result["skip_reason"]

    def test_invalid_n_mutants_skips_with_none(self):
        """n_mutants 非正数 → 直接跳过（rate=None），不触发除零。"""
        result = mutation_detection_rate(GRADE_FIXED, STRONG_TEST, "r5mod_grade", n_mutants=0)
        assert result["skipped"] is True
        assert result["rate"] is None


class TestMutantDetectedPredicate:
    """_mutant_detected 检出谓词的纯逻辑回归（零子进程）。"""

    def test_rc_zero_is_survived(self):
        """rc=0（全绿）→ 未检出。"""
        assert _mutant_detected(0, "1 passed in 0.01s") is False

    def test_rc_one_assertion_failure_is_detected(self):
        """rc=1（断言失败，普通 pytest 摘要）→ 检出。"""
        assert _mutant_detected(1, "1 failed in 0.01s") is True

    def test_rc_two_collection_error_is_not_detected(self):
        """rc=2（收集/编译阶段中断）→ 未检出（套件没跑起来）。"""
        assert _mutant_detected(2, "Interrupted: 1 error during collection") is False

    def test_rc_five_no_tests_is_not_detected(self):
        """rc=5 + "no tests were run" 标记 → 未检出。"""
        assert _mutant_detected(5, "no tests were run in 0.01s") is False

    def test_syntax_error_marker_is_not_detected(self):
        """rc=1 但输出含 SyntaxError 标记 → 未检出（执行错误兜底通道）。"""
        assert _mutant_detected(1, "SyntaxError: invalid syntax") is False


def _make_synthetic_task(fixed: str | None = 'def grade(score):\n    return "A"\n') -> BenchmarkTask:
    """构造带 gold fixed 材料的合成数据集任务（metadata 同 SyntheticDataset 口径）。"""
    return BenchmarkTask(
        task_id="synthetic__grade",
        repo_name="synthetic/grade",
        problem_statement="fix grade",
        instance_code='def grade(score):\n    return "B"\n',
        test_code="def test_grade():\n    from grade import grade\n",
        expected_pass_count=1,
        total_test_count=1,
        metadata={"source": "synthetic", "test_cases": "def test_gold(): ...", "fixed": fixed or ""},
    )


class TestWiringComputeMutationDetection:
    """run_benchmark._compute_mutation_detection_for_baseline 接线回归（mock，零子进程）。"""

    def test_missing_gold_fixed_writes_none(self, monkeypatch):
        """缺 gold fixed 材料 → mutation_detection_rate=None，不调用实现。"""
        from experiments import mutation_detection as md

        task = _make_synthetic_task(fixed="")
        calls: list[dict] = []
        monkeypatch.setattr(
            md,
            "mutation_detection_rate",
            lambda **kw: calls.append(kw) or {"rate": 0.5, "mutants_total": 5, "mutants_killed": 2, "skipped": False},
        )
        bl_results = [{"task_id": task.task_id, "repo": task.repo_name, "generated_test": "def t(): pass"}]
        rb._compute_mutation_detection_for_baseline(bl_results, {task.task_id: task}, n_mutants=5)
        assert bl_results[0]["mutation_detection_rate"] is None, "缺 gold fixed 应记 None"
        assert bl_results[0]["mutants_killed"] == 0 and bl_results[0]["mutants_total"] == 0
        assert calls == [], "缺 gold fixed 不应调用 mutation_detection_rate"

    def test_missing_generated_test_writes_none(self, monkeypatch):
        """无生成测试（失败分支 / 旧 JSON）→ None 占位，不调用实现。"""
        from experiments import mutation_detection as md

        task = _make_synthetic_task()
        calls: list[dict] = []
        monkeypatch.setattr(
            md,
            "mutation_detection_rate",
            lambda **kw: calls.append(kw) or {"rate": 0.5, "mutants_total": 5, "mutants_killed": 2, "skipped": False},
        )
        bl_results = [{"task_id": task.task_id, "repo": task.repo_name, "generated_test": None}]
        rb._compute_mutation_detection_for_baseline(bl_results, {task.task_id: task}, n_mutants=5)
        assert bl_results[0]["mutation_detection_rate"] is None
        assert calls == []

    def test_with_gold_fixed_writes_fields(self, monkeypatch):
        """有 gold fixed + 生成测试 → 调用实现并写回三字段（材料对齐校验）。"""
        from experiments import mutation_detection as md

        task = _make_synthetic_task()
        captured: list[dict] = []

        def fake_rate(**kw: Any) -> dict[str, Any]:
            captured.append(kw)
            return {
                "rate": 0.6,
                "mutants_total": 5,
                "mutants_killed": 3,
                "skipped": False,
                "skip_reason": "",
                "elapsed_seconds": 1.0,
            }

        monkeypatch.setattr(md, "mutation_detection_rate", fake_rate)
        bl_results = [{"task_id": task.task_id, "repo": task.repo_name, "generated_test": "def t(): pass"}]
        rb._compute_mutation_detection_for_baseline(bl_results, {task.task_id: task}, n_mutants=5, seed=7)
        assert bl_results[0]["mutation_detection_rate"] == 0.6
        assert bl_results[0]["mutants_killed"] == 3
        assert bl_results[0]["mutants_total"] == 5
        # 材料对齐：fixed 取 metadata["fixed"]（完整文件形态直用），模块名
        # 取 task_id 末段，测试取 generated_test，采样种子透传
        assert len(captured) == 1
        assert captured[0]["fixed_code"] == 'def grade(score):\n    return "A"\n'
        assert captured[0]["test_code"] == "def t(): pass"
        assert captured[0]["module_name"] == "grade"
        assert captured[0]["n_mutants"] == 5
        assert captured[0]["seed"] == 7

    def test_swe_bench_task_writes_none(self, monkeypatch):
        """SWE-bench 任务（无合成 gold fixed 材料）→ None 跳过。"""
        from experiments import mutation_detection as md

        task = _make_synthetic_task()
        task.metadata = {"source": "swe_bench"}
        calls: list[dict] = []
        monkeypatch.setattr(
            md,
            "mutation_detection_rate",
            lambda **kw: calls.append(kw) or {"rate": 0.5, "mutants_total": 5, "mutants_killed": 2, "skipped": False},
        )
        bl_results = [{"task_id": task.task_id, "repo": task.repo_name, "generated_test": "def t(): pass"}]
        rb._compute_mutation_detection_for_baseline(bl_results, {task.task_id: task}, n_mutants=5)
        assert bl_results[0]["mutation_detection_rate"] is None
        assert calls == []

    def test_unknown_task_id_writes_none(self):
        """task_id 不在 dataset_tasks 映射（任务缺失）→ None 跳过，不崩溃。"""
        bl_results = [{"task_id": "ghost__task", "repo": "x/y", "generated_test": "def t(): pass"}]
        rb._compute_mutation_detection_for_baseline(bl_results, {}, n_mutants=5)
        assert bl_results[0]["mutation_detection_rate"] is None
        assert bl_results[0]["mutants_killed"] == 0
        assert bl_results[0]["mutants_total"] == 0
