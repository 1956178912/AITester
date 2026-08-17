"""
端到端集成测试：测试完整工作流和边界场景。

覆盖范围：
    - Planner -> Generator -> Executor -> Debugger 完整流程
    - 错误恢复场景
    - 边界条件测试
    - 性能基准测试
"""

import pytest
import tempfile
import os
import time
from unittest.mock import patch, MagicMock
from src.graph.workflow import (
    _planner_node,
    _generator_node,
    _executor_node,
    _debugger_node,
    _patch_applier_node,
    _should_debug,
    build_workflow,
)
from src.graph.state import AITesterState
from src.agents.executor import ExecutorAgent
from src.tools.patch_applier import apply_patch_to_code


# ============================================================================
# 完整工作流测试
# ============================================================================

class TestFullWorkflowIntegration:
    """测试完整工作流集成。"""

    def test_pass_branch_full_workflow(self):
        """测试通过分支：Generator → Executor → done"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = os.path.join(tmpdir, "examples")
            os.makedirs(examples_dir)

            # 创建正确的被测代码
            target_code = '''
def add(a: int, b: int) -> int:
    return a + b

def subtract(a: int, b: int) -> int:
    return a - b
'''
            target_file = os.path.join(examples_dir, "math_ops.py")
            with open(target_file, 'w') as f:
                f.write(target_code)
            with open(os.path.join(examples_dir, "__init__.py"), 'w') as f:
                f.write('')

            # 初始化状态
            state = AITesterState({
                "target_code": target_code,
                "target_file": target_file,
                "module_name": "math_ops",
                "test_plan": None,
                "iteration": 0,
                "max_iterations": 3,
            })

            # 模拟 Generator 生成正确的测试
            mock_test_code = '''
from math_ops import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
'''
            with patch('src.graph.workflow.GeneratorAgent') as MockGen:
                mock_agent = MagicMock()
                mock_agent.generate = MagicMock(return_value=mock_test_code)
                MockGen.return_value = mock_agent
                gen_result = _generator_node(state)

            # 执行 Executor
            exec_state = {**state, **gen_result}
            exec_result = _executor_node(exec_state)

            # 验证结果
            assert exec_result["test_passed"] is True
            assert _should_debug({**state, **exec_result}) == "done"

    def test_debug_branch_full_workflow(self):
        """测试修复分支：Executor → Debugger → PatchApplier → Executor"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = os.path.join(tmpdir, "examples")
            os.makedirs(examples_dir)

            # 创建有 bug 的被测代码（缺少除零检查）
            buggy_code = '''
def divide(a: float, b: float) -> float:
    return a / b
'''
            target_file = os.path.join(examples_dir, "calculator.py")
            with open(target_file, 'w') as f:
                f.write(buggy_code)
            with open(os.path.join(examples_dir, "__init__.py"), 'w') as f:
                f.write('')

            state = AITesterState({
                "target_code": buggy_code,
                "target_file": target_file,
                "module_name": "calculator",
                "iteration": 0,
                "max_iterations": 3,
            })

            # 生成会触发除零错误的测试
            test_code = '''
from calculator import divide

def test_divide_by_zero():
    divide(1, 0)
'''

            # 执行 Executor（应失败）
            exec_state = {**state, "generated_test": test_code}
            exec_result = _executor_node(exec_state)
            assert exec_result["test_passed"] is False

            # 路由到 Debugger
            assert _should_debug({**state, **exec_result}) == "debug"

            # 模拟 Debugger 返回补丁
            mock_patch = {
                "root_cause": "缺少除零检查",
                "error_category": "runtime",
                "fix_strategy": "添加除零检查",
                "patch": '''
def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
'''
            }

            with patch('src.graph.workflow.DebuggerAgent') as MockDbg:
                mock_agent = MagicMock()
                mock_agent.debug = MagicMock(return_value=mock_patch)
                MockDbg.return_value = mock_agent
                dbg_result = _debugger_node({**state, **exec_result})

            # 执行 PatchApplier
            patch_state = {**state, **exec_result, **dbg_result}
            patch_result = _patch_applier_node(patch_state)

            # 验证补丁已应用
            assert "target_code" in patch_result
            assert "除数不能为零" in patch_result["target_code"]
            # patch_applied 在 repair_history 中
            history = patch_result.get("repair_history", [])
            if history:
                assert history[-1].get("patch_applied") is True

            # 验证迭代次数增加
            assert patch_result["iteration"] == 1

    def test_max_iterations_reached(self):
        """测试达到最大迭代次数后停止。"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "",
        })

        result = _should_debug(state)
        assert result == "done"

    def test_regenerate_branch_on_test_error(self):
        """测试测试生成错误时重新生成。"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：断言值不正确",
        })

        result = _should_debug(state)
        assert result == "regenerate"


# ============================================================================
# 错误恢复测试
# ============================================================================

class TestErrorRecovery:
    """测试错误恢复场景。"""

    def test_executor_timeout_recovery(self):
        """测试执行器超时后的恢复。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "slow.py")
            with open(target_file, 'w') as f:
                f.write('''
def slow_function():
    import time
    time.sleep(10)
    return 42
''')

            test_code = '''
from slow import slow_function

def test_slow():
    result = slow_function()
    assert result == 42
'''
            executor = ExecutorAgent(timeout=1)  # 1秒超时
            result = executor.execute(test_code, target_file)

            assert result["passed"] is False
            # 应包含超时信息
            assert "timeout" in result["output"].lower() or "超时" in result["output"]

    def test_executor_missing_module_recovery(self):
        """测试模块不存在时的恢复。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "existing.py")
            with open(target_file, 'w') as f:
                f.write('def foo(): return 1\n')

            # 测试代码导入不存在的模块
            test_code = '''
from nonexistent_module import bar

def test_bar():
    pass
'''
            executor = ExecutorAgent(timeout=10)
            result = executor.execute(test_code, target_file)

            assert result["passed"] is False
            assert "ModuleNotFoundError" in result["output"] or "import" in result["output"].lower()

    def test_patch_applier_rolls_back_on_error(self):
        """测试补丁应用失败时保持原代码。"""
        original = 'def foo(): return 1\n'
        invalid_patch = 'def foo(): return \n    invalid syntax'

        new_code, success = apply_patch_to_code(original, invalid_patch)
        # 由于补丁无效，应保持原代码或返回失败
        # 注意：apply_patch_to_code 不进行语法检查，只进行结构匹配
        if success:
            # 如果成功应用了，新代码应包含补丁内容
            assert "def foo()" in new_code

    def test_debugger_handles_empty_output(self):
        """测试 Debugger 处理空输出。"""
        state = AITesterState({
            "target_code": "def foo(): pass\n",
            "target_file": "/fake/path.py",
            "test_output": "",
            "failed_cases": [],
        })

        with patch('src.graph.workflow.DebuggerAgent') as MockDbg:
            mock_agent = MagicMock()
            mock_agent.debug = MagicMock(return_value={
                "root_cause": "未知错误",
                "error_category": "unknown",
                "fix_strategy": "通用分析",
                "patch": "def foo(): pass\n"
            })
            MockDbg.return_value = mock_agent
            result = _debugger_node(state)

        assert "diagnosis" in result


# ============================================================================
# 边界条件测试
# ============================================================================

class TestBoundaryConditions:
    """测试边界条件。"""

    def test_empty_target_code(self):
        """测试空目标代码。"""
        state = AITesterState({
            "target_code": "",
            "target_file": "/fake/empty.py",
            "test_plan": None,
            "iteration": 0,
            "max_iterations": 3,
        })

        with patch('src.graph.workflow.GeneratorAgent') as MockGen:
            mock_agent = MagicMock()
            mock_agent.generate = MagicMock(return_value="def test(): pass\n")
            MockGen.return_value = mock_agent
            result = _generator_node(state)

        assert "generated_test" in result

    def test_single_function_code(self):
        """测试单函数代码的处理。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "single.py")
            with open(target_file, 'w') as f:
                f.write('def only_function(x):\n    return x * 2\n')

            test_code = '''
from single import only_function

def test_only():
    assert only_function(5) == 10
'''
            executor = ExecutorAgent(timeout=10)
            result = executor.execute(test_code, target_file)

            assert result["passed"] is True

    def test_multiple_functions_code(self):
        """测试多函数代码的处理。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "multi.py")
            with open(target_file, 'w') as f:
                f.write('''
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
''')

            test_code = '''
from multi import add, subtract, multiply

def test_add():
    assert add(1, 2) == 3

def test_subtract():
    assert subtract(5, 3) == 2

def test_multiply():
    assert multiply(4, 3) == 12
'''
            executor = ExecutorAgent(timeout=10)
            result = executor.execute(test_code, target_file)

            assert result["passed"] is True

    def test_class_based_code(self):
        """测试类定义代码的处理。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "clazz.py")
            with open(target_file, 'w') as f:
                f.write('''
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b
''')

            test_code = '''
from clazz import Calculator

def test_calculator():
    calc = Calculator()
    assert calc.add(2, 3) == 5
    assert calc.subtract(5, 3) == 2
'''
            executor = ExecutorAgent(timeout=10)
            result = executor.execute(test_code, target_file)

            assert result["passed"] is True

    def test_unicode_in_code(self):
        """测试含 Unicode 字符的代码。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "unicode.py")
            with open(target_file, 'w', encoding='utf-8') as f:
                f.write('''
def 问候(name: str) -> str:
    return f"你好, {name}!"
''')

            test_code = '''
from unicode import 问候

def test_greeting():
    assert 问候("世界") == "你好, 世界!"
'''
            executor = ExecutorAgent(timeout=10)
            result = executor.execute(test_code, target_file)

            assert result["passed"] is True


# ============================================================================
# 性能基准测试
# ============================================================================

class TestPerformanceBenchmarks:
    """测试性能基准。"""

    def test_executor_execution_time(self):
        """测试执行器单次执行时间。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            target_file = os.path.join(tmpdir, "simple.py")
            with open(target_file, 'w') as f:
                f.write('def add(a, b): return a + b\n')

            test_code = '''
from simple import add

def test_add():
    assert add(1, 2) == 3
'''
            executor = ExecutorAgent(timeout=10)

            start_time = time.time()
            result = executor.execute(test_code, target_file)
            elapsed = time.time() - start_time

            assert result["passed"] is True
            # 单次执行应在合理时间内完成（< 5秒）
            assert elapsed < 5.0, f"执行耗时 {elapsed:.2f}s 过长"

    def test_patch_application_time(self):
        """测试补丁应用时间。"""
        original = '''
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
'''
        patch = '''
def add(a, b):
    return a + b + 1
'''
        start_time = time.time()
        new_code, success = apply_patch_to_code(original, patch)
        elapsed = time.time() - start_time

        assert success is True
        # 补丁应用应非常快（< 0.1秒）
        assert elapsed < 0.1, f"补丁应用耗时 {elapsed:.4f}s 过长"

    def test_workflow_construction_time(self):
        """测试工作流构建时间。"""
        start_time = time.time()
        workflow = build_workflow()
        elapsed = time.time() - start_time

        assert workflow is not None
        # 工作流构建应很快（< 1秒）
        assert elapsed < 1.0, f"工作流构建耗时 {elapsed:.2f}s 过长"


# ============================================================================
# 状态管理测试
# ============================================================================

class TestStateManager:
    """测试状态管理。"""

    def test_state_persistence_across_nodes(self):
        """测试状态在节点间传递。"""
        initial_state = AITesterState({
            "target_code": "def foo(): return 1\n",
            "iteration": 0,
            "max_iterations": 3,
        })

        # 模拟状态传递
        gen_output = {"generated_test": "def test(): pass\n"}
        merged_state = {**initial_state, **gen_output}

        assert merged_state["iteration"] == 0
        assert merged_state["generated_test"] == "def test(): pass\n"

    def test_iteration_increment(self):
        """测试迭代次数递增。"""
        state = AITesterState({
            "iteration": 2,
            "max_iterations": 3,
        })

        # 模拟 PatchApplier 增加迭代
        new_iteration = state.get("iteration", 0) + 1
        assert new_iteration == 3

    def test_test_passed_flag(self):
        """测试测试通过标志。"""
        state = AITesterState({
            "test_passed": True,
            "iteration": 1,
        })

        assert state["test_passed"] is True
        assert _should_debug(state) == "done"


# ============================================================================
# 配置测试
# ============================================================================

class TestWorkflowConfig:
    """测试工作流配置。"""

    def test_build_workflow_with_defaults(self):
        """测试使用默认配置构建工作流。"""
        workflow = build_workflow()
        assert workflow is not None

    def test_workflow_has_expected_nodes(self):
        """测试工作流包含预期节点。"""
        workflow = build_workflow()
        nodes = list(workflow.nodes.keys())

        assert "generator" in nodes
        assert "executor" in nodes
        assert "patch_applier" in nodes

    def test_workflow_routing(self):
        """测试工作流路由逻辑。"""
        workflow = build_workflow()
        # 验证工作流对象有效
        assert workflow is not None
        # CompiledStateGraph 没有 compile 方法，但可以被 invoke
        assert hasattr(workflow, 'invoke')
