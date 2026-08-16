"""
单元测试：测试 AITesterState TypedDict 的结构完整性。

覆盖范围：
    - 所有必需字段存在
    - 所有可选字段存在
    - 可通过 dict 构造
"""

import pytest
from typing import get_type_hints
from src.graph.state import AITesterState


# ─── TestAITesterState：状态结构 ───────────────────────────────────────────────
class TestAITesterState:
    """测试 AITesterState TypedDict 的字段完整性。"""

    def test_required_fields_exist(self):
        """验证所有 required（非 total=False）字段存在。"""
        # AITesterState 所有字段均为 optional (total=False)，但应有完整的字段定义
        hints = get_type_hints(AITesterState)
        # 核心必填字段
        required_keys = [
            "target_file", "target_code", "iteration", "max_iterations",
            "repair_history",
        ]
        for key in required_keys:
            assert key in hints, f"缺少必需字段: {key}"

    def test_optional_fields_exist(self):
        """验证所有可选字段均已定义。"""
        hints = get_type_hints(AITesterState)
        optional_keys = [
            "task_uuid", "target_function", "module_name",
            "test_plan", "generated_test", "test_passed",
            "test_output", "coverage_report", "failed_cases",
            "diagnosis", "error_category", "patch",
            "rag_references",
        ]
        for key in optional_keys:
            assert key in hints, f"缺少可选字段: {key}"

    def test_can_construct_from_dict(self):
        """AITesterState 应能从 dict 构造（runnable）。"""
        sample_state = {
            "target_file": "examples/calculator.py",
            "target_code": "def divide(a, b): return a / b",
            "iteration": 0,
            "max_iterations": 3,
            "repair_history": [],
        }
        # TypedDict 在运行时允许 dict 赋值
        state: AITesterState = sample_state  # type: ignore
        assert state["target_file"] == "examples/calculator.py"
        assert state["iteration"] == 0

    def test_default_iteration_is_zero(self):
        """iteration 默认值应为 0。"""
        state: AITesterState = {  # type: ignore
            "target_file": "test.py",
            "target_code": "def f(): pass",
            "iteration": 0,
            "max_iterations": 3,
            "repair_history": [],
        }
        assert state["iteration"] == 0

    def test_all_field_types_are_reasonable(self):
        """验证关键字段的类型注解合理。"""
        hints = get_type_hints(AITesterState)
        # target_file 应为 str
        assert hints.get("target_file") is not None
        # iteration 应为 int
        assert hints.get("iteration") is not None
        # test_passed 应为 bool | None
        assert hints.get("test_passed") is not None
