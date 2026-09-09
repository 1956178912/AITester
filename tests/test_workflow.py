"""
Workflow 单元测试

测试 workflow.py 中的：
- build_workflow 函数
- _should_debug 路由
- _should_skip_debugger 函数
- 节点函数 (_planner_node, _generator_node 等)
"""

import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestShouldDebug:
    """测试 _should_debug 路由函数。"""

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_test_passed_returns_done(self):
        """测试通过时返回 'done'。"""
        from src.graph.workflow import _should_debug

        state = {"test_passed": True}
        result = _should_debug(state)
        assert result == "done"

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_first_iteration_returns_debug(self):
        """首次迭代返回 'debug'。"""
        from src.graph.workflow import _should_debug

        state = {"test_passed": False, "iteration": 0, "max_iterations": 3}
        result = _should_debug(state)
        assert result == "debug"

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_max_iterations_reached_returns_done(self):
        """达到最大迭代次数时返回 'done'。"""
        from src.graph.workflow import _should_debug

        state = {"test_passed": False, "iteration": 3, "max_iterations": 3}
        result = _should_debug(state)
        assert result == "done"

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_max_iterations_with_test_error_returns_regenerate(self):
        """达到最大迭代且诊断为测试错误时返回 'regenerate'。"""
        from src.graph.workflow import _should_debug

        state = {"test_passed": False, "iteration": 3, "max_iterations": 3, "diagnosis": "测试生成错误：AttributeError"}
        result = _should_debug(state)
        assert result == "regenerate"

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_consecutive_failed_repairs_skips_debugger(self):
        """连续多次修复失败时跳过 Debugger。"""
        from src.graph.workflow import _should_debug

        state = {
            "test_passed": False,
            "iteration": 1,
            "max_iterations": 3,
            "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
        }
        result = _should_debug(state)
        assert result == "done"


class TestShouldSkipDebugger:
    """测试 _should_skip_debugger 函数。"""

    def test_test_passed_not_skipped(self):
        """测试通过时不跳过。"""
        from src.graph.workflow import _should_skip_debugger

        state = {"test_passed": True}
        result = _should_skip_debugger(state)
        assert result is False

    def test_no_repair_history(self):
        """无修复历史时不跳过。"""
        from src.graph.workflow import _should_skip_debugger

        state = {"test_passed": False, "repair_history": []}
        result = _should_skip_debugger(state)
        assert result is False

    def test_successful_repair_not_skipped(self):
        """有成功修复时不跳过。"""
        from src.graph.workflow import _should_skip_debugger

        state = {"test_passed": False, "repair_history": [{"patch_applied": True}, {"patch_applied": False}]}
        result = _should_skip_debugger(state)
        assert result is False

    def test_consecutive_failures_skips(self):
        """连续修复失败时跳过。"""
        from src.graph.workflow import _should_skip_debugger

        state = {"test_passed": False, "repair_history": [{"patch_applied": False}, {"patch_applied": False}]}
        result = _should_skip_debugger(state)
        assert result is True


class TestValidatePlannerOutput:
    """测试 Planner 输出验证。"""

    def test_valid_output(self):
        """有效输出返回 True。"""
        from src.graph.workflow import _validate_planner_output

        plan = {"function_name": "foo", "logic_analysis": {}}
        assert _validate_planner_output(plan) is True

    def test_missing_function_name(self):
        """缺少 function_name 返回 False。"""
        from src.graph.workflow import _validate_planner_output

        plan = {"logic_analysis": {}}
        assert _validate_planner_output(plan) is False

    def test_missing_logic_analysis(self):
        """缺少 logic_analysis 返回 False。"""
        from src.graph.workflow import _validate_planner_output

        plan = {"function_name": "foo"}
        assert _validate_planner_output(plan) is False

    def test_not_dict(self):
        """非字典类型返回 False。"""
        from src.graph.workflow import _validate_planner_output

        assert _validate_planner_output("invalid") is False

    def test_invalid_logic_analysis_type(self):
        """logic_analysis 类型错误返回 False。"""
        from src.graph.workflow import _validate_planner_output

        plan = {"function_name": "foo", "logic_analysis": "invalid"}
        assert _validate_planner_output(plan) is False


class TestGetDefaultTestPlan:
    """测试默认测试计划生成。"""

    def test_default_plan_with_function_name(self):
        """带函数名的默认计划。"""
        from src.graph.workflow import _get_default_test_plan

        plan = _get_default_test_plan("foo")
        assert plan["function_name"] == "foo"
        assert "logic_analysis" in plan
        assert "test_cases" in plan

    def test_default_plan_without_function_name(self):
        """不带函数名的默认计划。"""
        from src.graph.workflow import _get_default_test_plan

        plan = _get_default_test_plan(None)
        assert plan["function_name"] == "unknown"


class TestBuildWorkflow:
    """测试工作流构建。"""

    @patch("src.graph.workflow.ENABLE_PLANNER", True)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    @patch("src.graph.workflow.StateGraph")
    def test_build_workflow_with_all_features(self, mock_stategraph):
        """构建完整工作流。"""
        from src.graph.workflow import build_workflow

        mock_workflow = MagicMock()
        mock_stategraph.return_value = mock_workflow

        build_workflow()

        mock_stategraph.assert_called_once()
        mock_workflow.compile.assert_called_once()

    @patch("src.graph.workflow.ENABLE_PLANNER", False)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", False)
    @patch("src.graph.workflow.StateGraph")
    def test_build_workflow_minimal(self, mock_stategraph):
        """构建最小工作流（无 Planner 和 Debugger）。"""
        from src.graph.workflow import build_workflow

        mock_workflow = MagicMock()
        mock_stategraph.return_value = mock_workflow

        build_workflow()

        mock_stategraph.assert_called_once()
        mock_workflow.compile.assert_called_once()


class TestGetWorkflowStats:
    """测试工作流统计信息。"""

    @patch("src.graph.workflow.get_cache_stats")
    @patch("src.graph.workflow.ENABLE_PLANNER", True)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    @patch("src.graph.workflow.ENABLE_RAG", False)
    @patch("src.graph.workflow.MAX_ITERATIONS", 3)
    def test_get_workflow_stats(self, mock_get_cache):
        """获取工作流统计。"""
        from src.graph.workflow import get_workflow_stats

        mock_get_cache.return_value = {"hits": 10, "misses": 5}

        stats = get_workflow_stats()

        assert "llm_cache" in stats
        assert "workflow_config" in stats
        assert stats["workflow_config"]["ENABLE_PLANNER"] is True
        assert stats["workflow_config"]["MAX_ITERATIONS"] == 3


class TestNodeFunctions:
    """测试节点函数。"""

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_success(self, mock_planner_class):
        """Planner 节点成功执行。"""
        from src.graph.workflow import _planner_node

        mock_agent = MagicMock()
        mock_agent.plan.return_value = {"function_name": "foo", "logic_analysis": {}, "test_cases": []}
        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "target_function": "foo"}
        result = _planner_node(state)

        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "foo"

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_fallback(self, mock_planner_class):
        """Planner 节点失败时使用默认计划。"""
        from src.graph.workflow import _planner_node

        mock_agent = MagicMock()
        mock_agent.plan.side_effect = RuntimeError("API error")
        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "target_function": "foo"}
        result = _planner_node(state)

        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "foo"

    @patch("src.graph.workflow.GeneratorAgent")
    def test_generator_node(self, mock_generator_class):
        """Generator 节点执行。"""
        from src.graph.workflow import ENABLE_PLANNER, ENABLE_RAG, RAG_MODULE_AVAILABLE, _generator_node

        # 保存原始值
        original_enable_planner = ENABLE_PLANNER
        original_enable_rag = ENABLE_RAG
        original_rag_available = RAG_MODULE_AVAILABLE

        try:
            # 设置测试状态
            import src.graph.workflow as workflow_module

            workflow_module.ENABLE_PLANNER = False
            workflow_module.ENABLE_RAG = False
            workflow_module.RAG_MODULE_AVAILABLE = False

            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_generator_class.return_value = mock_agent

            state = {"target_code": "def foo(): pass", "module_name": "test_module"}
            result = _generator_node(state)

            assert "generated_test" in result
            assert result["generated_test"] == "def test_foo(): pass"
        finally:
            # 恢复原始值
            workflow_module.ENABLE_PLANNER = original_enable_planner
            workflow_module.ENABLE_RAG = original_enable_rag
            workflow_module.RAG_MODULE_AVAILABLE = original_rag_available

    @patch("src.graph.workflow.ExecutorAgent")
    def test_executor_node(self, mock_executor_class):
        """Executor 节点执行。"""
        from src.graph.workflow import _executor_node

        mock_agent = MagicMock()
        mock_agent.execute.return_value = {"passed": True, "output": "1 passed", "coverage": 85.0, "failed_cases": []}
        mock_executor_class.return_value = mock_agent

        state = {"generated_test": "def test(): pass", "target_file": "/path/to/test.py", "iteration": 0}
        result = _executor_node(state)

        assert "test_passed" in result
        assert result["test_passed"] is True
        assert result["coverage_report"] == 85.0
