"""M1 指标语义单测（2026-09-30 独立审查 N1/R5，P0 + R4 回归率）。

直接调用 `experiments/_m1_metrics._compute_detection_rate`（不引用项目
自述），用**构造任务 + 固定 5 种测试形态**锁定 fail-to-pass 语义：

    | 生成测试形态                        | detection_rate | test_error_rate |
    |------------------------------------|----------------|-----------------|
    | 恒失败（assert False）             | 0.0            | 0.0             |
    | 收集错误（import 不存在的模块）     | 0.0            | 1.0             |
    | 语法错误（def test_a(:）           | 0.0            | 1.0             |
    | 合法 F2P（buggy 红 / fixed 绿）     | 1.0            | 0.0             |
    | 恒真断言（无检出）                 | 0.0            | 0.0             |

N1 核心防线：只需让 LLM 输出一个语法坏掉的测试文件，**不得**再获得
100% detection_rate。

不依赖 LLM / 网络，纯确定性断言，CI 可安全运行。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ── 构造任务（_extract_gold_material 消费 metadata["test_cases"] /
#    metadata["fixed"]；module_name 取 task_id 末段）─────────────────────


@dataclass
class _FakeTask:
    _task_id: str
    instance_code: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self._task_id

    @property
    def repo_name(self) -> str:
        return "synthetic/_probe"


BUGGY_CODE = "def add(a: int, b: int) -> int:\n    return a + b\n"
FIXED_CODE = "def add(a: int, b: int) -> int:\n    return a + b + 1\n"
# 被测模块以 task_id 末段命名（add_off_by_one.py），import 目标 = 该末段。
# 期望值 4 = fixed 行为：GOLD_TEST 在 buggy（add(1,2)=3）上必红、在
# fixed（add(1,2)=4）上必绿（repair_rate 的独立裁决材料语义正确）。
GOLD_TEST = "from add_off_by_one import add\n\n\ndef test_gold():\n    assert add(1, 2) == 4\n"


def _make_task() -> _FakeTask:
    """构造 F2P 可判定的合成任务。

    材料语义（与 _m1_metrics 的判定口径一致）：
    - instance_code = BUGGY_CODE（add 返回 a+b，add(1,2)=3）；
    - metadata["fixed"] = FIXED_CODE（add 返回 a+b+1，add(1,2)=4）；
    - metadata["test_cases"] = GOLD_TEST（断言 add(1,2)==4）：在 buggy
      上必红、在 fixed 上必绿——repair_rate 的独立裁决材料语义正确。

    生成测试的 F2P 判定（detection_rate）：
    - LEGIT_F2P：断言 add(1,2)==4 → buggy 红（3≠4）/ fixed 绿（4==4）→ 1.0；
    - TAUTOLOGICAL：断言 add(1,2)==3 → buggy 绿（3==3）→ 缺陷未检出 → 0.0。

    注意：_m1_metrics 把被测模块以 task_id 末段命名（add_off_by_one.py），
    故生成测试的 import 都用 `add_off_by_one`。
    """
    return _FakeTask(
        _task_id="probe__add_off_by_one",
        instance_code=BUGGY_CODE,
        metadata={
            "source": "synthetic",
            "test_cases": GOLD_TEST,
            "fixed": FIXED_CODE,
            "is_cross_file": False,
        },
    )


def _state_with_generated_test(test_code: str) -> dict[str, Any]:
    return {"generated_test": test_code, "test_passed": True, "regeneration_count": 0}


from experiments._m1_metrics import _compute_regression_rate  # noqa: E402

# 5 种测试形态（N1 探针口径；import 目标 = task_id 末段 add_off_by_one）
ALWAYS_FAIL = "from add_off_by_one import add\n\n\ndef test_always_fail():\n    assert False\n"
COLLECTION_ERROR = "from definitely_not_a_module_xyz import add\n\n\ndef test_import():\n    pass\n"
SYNTAX_ERROR = "def test_a(:\n    pass\n"
# 合法 F2P：buggy（add(1,2)=3）上红、fixed（add(1,2)=4）上绿
LEGIT_F2P = "from add_off_by_one import add\n\n\ndef test_f2p():\n    assert add(1, 2) == 4\n"
# 恒真 / 无检出：buggy 上直接通过（add(1,2)=3 成立）→ 缺陷未被检出
TAUTOLOGICAL = "from add_off_by_one import add\n\n\ndef test_taut():\n    assert add(1, 2) == 3\n"


class TestM1MetricSemantics:
    """_compute_detection_rate / _compute_test_error_rate 语义锁定。"""

    def _detection(self, generated: str) -> float | None:
        from experiments._m1_metrics import _compute_detection_rate

        return _compute_detection_rate(_make_task(), _state_with_generated_test(generated))

    def _test_error(self, generated: str) -> float | None:
        from experiments._m1_metrics import _compute_test_error_rate

        return _compute_test_error_rate(_make_task(), _state_with_generated_test(generated))

    def test_always_failing_test_must_not_score_full(self):
        """恒失败测试（assert False）：buggy 红但 fixed 也红 → 非 F2P。"""
        assert self._detection(ALWAYS_FAIL) == 0.0, "N1：恒失败测试不得获得 detection=1.0"
        # 恒失败不是"测试执行错误"（断言正常执行了，只是恒假）→ 0.0
        assert self._test_error(ALWAYS_FAIL) == 0.0

    def test_collection_error_must_not_score_full(self):
        """收集错误（import 不存在的模块）：根本没运行断言。"""
        assert self._detection(COLLECTION_ERROR) == 0.0, "N1：收集错误测试不得获得 detection=1.0"
        # 收集错误 → test_error_rate = 1.0（坏测试直接防线）
        assert self._test_error(COLLECTION_ERROR) == 1.0

    def test_syntax_error_must_not_score_full(self):
        """语法错误（连文件都无法解析）：收集阶段即失败。"""
        assert self._detection(SYNTAX_ERROR) == 0.0, "N1：语法错误测试不得获得 detection=1.0"
        assert self._test_error(SYNTAX_ERROR) == 1.0

    def test_legit_fail_to_pass_scores_full(self):
        """合法 F2P：buggy 上红、fixed 上绿、无收集错误 → 1.0。"""
        assert self._detection(LEGIT_F2P) == 1.0, "合法 fail-to-pass 测试必须记 1.0"
        assert self._test_error(LEGIT_F2P) == 0.0

    def test_tautological_test_scores_zero(self):
        """恒真 / 无检出测试（buggy 上直接通过）→ 0.0。"""
        assert self._detection(TAUTOLOGICAL) == 0.0

    def test_no_generated_test_is_none(self):
        """无生成测试 → 保守 None（不误报）。"""
        from experiments._m1_metrics import _compute_detection_rate

        state: dict[str, Any] = {"generated_test": "", "test_passed": False}
        assert _compute_detection_rate(_make_task(), state) is None

    def test_no_gold_material_is_none(self):
        """无 gold 材料（SWE-bench / examples）→ 三指标保守 None。"""
        from experiments._m1_metrics import (
            _compute_detection_rate,
            _compute_false_fix_rate,
            _compute_repair_rate,
            _compute_test_error_rate,
        )

        swe_task = _FakeTask(
            _task_id="swe__probe",
            instance_code=BUGGY_CODE,
            metadata={"source": "swe_bench"},
        )
        state = _state_with_generated_test(LEGIT_F2P)
        assert _compute_detection_rate(swe_task, state) is None
        assert _compute_repair_rate(swe_task, state) is None
        assert _compute_false_fix_rate(swe_task, state) is None
        assert _compute_test_error_rate(swe_task, state) is None

    def test_build_m1_task_metrics_key_isomorphism(self):
        """build_m1_task_metrics 键集合同构（无 gold 材料时全 None，
        成功分支含 test_error_rate 新键）。"""
        from experiments._m1_metrics import build_m1_task_metrics

        # 无 gold 材料（examples 源无 test_cases/fixed）
        ex_task = _FakeTask(
            _task_id="examples__probe",
            instance_code=BUGGY_CODE,
            metadata={"source": "examples"},
        )
        m = build_m1_task_metrics(ex_task, _state_with_generated_test(LEGIT_F2P))
        assert m["detection_rate"] is None
        assert m["repair_rate"] is None
        assert m["false_fix_rate"] is None
        assert m["test_error_rate"] is None
        assert m["regression_rate"] is None
        assert "test_regenerated_pass_unverified" in m

        # 有 gold 材料的任务：新键存在
        m2 = build_m1_task_metrics(_make_task(), _state_with_generated_test(LEGIT_F2P))
        assert m2["test_error_rate"] == 0.0
        assert m2["detection_rate"] == 1.0


class TestM1InterpreterPolicy:
    """R2（2026-09-30 独立审查 N4）：解释器口径 + 前置断言。"""

    def test_default_interpreter_is_sys_executable(self):
        """默认解释器 = 本进程解释器（sys.executable），非硬编码 python3。"""
        import sys

        from experiments._m1_metrics import _python_interpreter

        assert _python_interpreter() == sys.executable

    def test_env_override_is_respected(self, monkeypatch):
        """AITESTER_M1_PYTHON 可显式覆盖（特殊执行环境）。"""
        import sys

        monkeypatch.setenv("AITESTER_M1_PYTHON", sys.executable)
        from experiments._m1_metrics import _python_interpreter

        assert _python_interpreter() == sys.executable

    def test_interpreter_without_pytest_raises(self, monkeypatch):
        """无 pytest 的解释器 → 模块加载期即 raise（fail-fast，
        不再静默退化为 collection error 全 1.0 口径）。"""
        import subprocess
        import sys
        from unittest import mock

        def _fake_run(cmd, **_kwargs):
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="No module named pytest")

        monkeypatch.setenv("AITESTER_M1_PYTHON", sys.executable)
        with mock.patch("experiments._m1_metrics.subprocess.run", side_effect=_fake_run):
            from experiments import _m1_metrics

            try:
                _m1_metrics._python_interpreter()
                raised = False
            except RuntimeError:
                raised = True
        assert raised, "无 pytest 的解释器必须 raise RuntimeError"


class TestRegressionRate:
    """R4（2026-09-30 独立审查 P0）：回归率（修复引入回归观测）。

    定义：补丁应用后 gold P2P 基线测试出现"原本全过 → 现失败"的回归
    → regression_rate = 1.0；否则（无回归 / 无补丁）→ 0.0；
    无 gold 材料 / 无 P2P 材料 / 执行超时 → None（不可测量，不误报）。
    """

    def test_no_p2p_material_is_none(self):
        """无 P2P 材料（metadata 缺 pass_to_pass）→ None（不可测量，保守不误报）。"""
        task = _make_task()  # 无 pass_to_pass
        state = {"generated_test": LEGIT_F2P, "patch": FIXED_CODE, "test_passed": True}
        assert _compute_regression_rate(task, state) is None

    def test_no_patch_is_zero(self):
        """有 P2P 材料但无补丁 → P2P 在原始代码上跑（基线自洽）→ 0.0。"""
        task = _FakeTask(
            _task_id="add_off_by_one",
            instance_code=BUGGY_CODE,
            metadata={
                "source": "synthetic",
                "test_cases": GOLD_TEST,
                "fixed": FIXED_CODE,
                "pass_to_pass": ["def test_p2p_base():\n    assert add(1, 2) == 3\n"],
            },
        )
        state = {"generated_test": LEGIT_F2P, "patch": "", "test_passed": False}
        # 无补丁：new_code = original（buggy），P2P "add(1,2)==3" 在 buggy 上
        # 全过（buggy 行为就是 a+b=3）→ 基线 rc=0，补丁后 rc=0 → 无回归 → 0.0
        assert _compute_regression_rate(task, state) == 0.0

    def test_swe_bench_is_none(self):
        """SWE-bench 无 gold 材料 → None（不可测量）。"""
        swe_task = _FakeTask(
            _task_id="swe__probe",
            instance_code=BUGGY_CODE,
            metadata={"source": "swe_bench", "pass_to_pass": ["test_p"]},
        )
        state = {"generated_test": LEGIT_F2P, "patch": FIXED_CODE, "test_passed": True}
        assert _compute_regression_rate(swe_task, state) is None

    def test_no_final_state_is_none(self):
        """final_state=None → None（失败分支占位）。"""
        assert _compute_regression_rate(_make_task(), None) is None


if __name__ == "__main__":
    import sys

    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
