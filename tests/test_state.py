"""
create_initial_state 工厂函数单元测试。

锁定单一构造点行为（2026-09-15 深度重构批次）：
- 字段全集与 AITesterState TypedDict 一致（新增字段时工厂同步更新）
- module_name 缺省推导规则
- 可选参数注入
"""

from __future__ import annotations

import src.graph.state as state_mod
from src.graph.state import AITesterState, create_initial_state


class TestCreateInitialState:
    """create_initial_state 工厂函数行为锁定。"""

    def test_returns_aitester_state(self) -> None:
        """工厂返回 AITesterState 实例（TypedDict 字典，键集完整）。"""
        s = create_initial_state(
            task_uuid="t1",
            target_file="examples/calculator.py",
            target_code="def add(a, b):\n    return a + b",
            max_iterations=3,
        )
        assert isinstance(s, dict)
        # 与 TypedDict 定义比对（键集一致，防漂移）
        expected_keys = set(AITesterState.__annotations__.keys())
        assert set(s.keys()) == expected_keys

    def test_module_name_default_derived_from_target_file(self) -> None:
        """module_name 缺省时按 target_file 推导（os.path.splitext 口径）。"""
        s = create_initial_state(
            task_uuid="t1",
            target_file="examples/calculator.py",
            target_code="code",
            max_iterations=3,
        )
        assert s["module_name"] == "calculator"

    def test_module_name_explicit_overrides_derivation(self) -> None:
        """显式 module_name 优先于推导（benchmark SWE-bench 场景：instance_file 与 module_name 解耦）。"""
        s = create_initial_state(
            task_uuid="t1",
            target_file="/tmp/instance_abc.py",
            target_code="code",
            max_iterations=3,
            module_name="calculator",
        )
        assert s["module_name"] == "calculator"

    def test_optional_fields_default_none(self) -> None:
        """可选字段缺省为 None（CLI 不传 execution_timeout 时 Executor 回退 config）。"""
        s = create_initial_state(
            task_uuid="t1",
            target_file="f.py",
            target_code="code",
            max_iterations=3,
        )
        assert s["execution_timeout"] is None
        assert s["coverage_threshold"] is None
        assert s["target_function"] is None
        assert s["cross_file_deps"] is None
        assert s["cross_file_plan"] is None

    def test_optional_fields_injected(self) -> None:
        """可选参数注入后原样落字段。"""
        s = create_initial_state(
            task_uuid="t1",
            target_file="f.py",
            target_code="code",
            max_iterations=5,
            target_function="add",
            execution_timeout=120,
            coverage_threshold=85.5,
        )
        assert s["target_function"] == "add"
        assert s["execution_timeout"] == 120
        assert s["coverage_threshold"] == 85.5
        assert s["max_iterations"] == 5

    def test_mutables_are_fresh_per_call(self) -> None:
        """repair_history 等可变容器每次调用独立实例（防跨任务串扰）。"""
        s1 = create_initial_state(task_uuid="a", target_file="f.py", target_code="c", max_iterations=3)
        s2 = create_initial_state(task_uuid="b", target_file="f.py", target_code="c", max_iterations=3)
        s1["repair_history"].append({"iteration": 0})
        assert s2["repair_history"] == []

    def test_typed_dict_fields_present_in_factory(self) -> None:
        """守护测试：AITesterState 新增字段时，本测试因键集不一致失败，强制同步工厂。"""
        # 与 TestCreateInitialState.test_returns_aitester_state 同一比对逻辑，
        # 独立成例便于在 CI 失败时直接定位"字段漂移"
        s = create_initial_state(task_uuid="t", target_file="f.py", target_code="c", max_iterations=3)
        missing = set(AITesterState.__annotations__.keys()) - set(s.keys())
        extra = set(s.keys()) - set(AITesterState.__annotations__.keys())
        assert not missing, f"工厂缺少 TypedDict 字段: {missing}"
        assert not extra, f"工厂多出 TypedDict 之外的字段: {extra}"


class TestStateModuleExports:
    """state 模块导出面。"""

    def test_state_module_exposes_create_initial_state(self) -> None:
        """create_initial_state 在模块导出面（import src.graph.state.create_initial_state 可用）。"""
        assert hasattr(state_mod, "create_initial_state")
        assert callable(state_mod.create_initial_state)
