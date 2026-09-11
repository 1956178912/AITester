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

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_regenerate_capped_at_max_regenerations(self):
        """达到重新生成上限后，即便诊断命中关键词也返回 done（防 generator↔executor 死循环）。"""
        from src.graph.workflow import _MAX_REGENERATIONS, _should_debug

        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：AttributeError",
            "regeneration_count": _MAX_REGENERATIONS,
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

    @patch("src.graph.workflow.GeneratorAgent")
    def test_generator_node_missing_test_plan_key_no_keyerror(self, mock_generator_class):
        """Generator 节点：state 缺 test_plan 键时不得 KeyError。

        回归：此前 `state["test_plan"] if ENABLE_PLANNER else None` 在 ENABLE_PLANNER
        为 True 且 state 无 test_plan 键时直接 KeyError；现改为 state.get() 缺失传 None，
        由 Generator 自行推断，跟随图结构而非全局开关。
        """
        import src.graph.workflow as workflow_module
        from src.graph.workflow import _generator_node

        original_enable_planner = workflow_module.ENABLE_PLANNER
        original_enable_rag = workflow_module.ENABLE_RAG
        original_rag_available = workflow_module.RAG_MODULE_AVAILABLE
        try:
            workflow_module.ENABLE_PLANNER = True
            workflow_module.ENABLE_RAG = False
            workflow_module.RAG_MODULE_AVAILABLE = False

            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_generator_class.return_value = mock_agent

            # 注意：state 中故意不含 test_plan 键
            state = {"target_code": "def foo(): pass", "module_name": "test_module"}
            result = _generator_node(state)

            assert result["generated_test"] == "def test_foo(): pass"
            mock_agent.generate.assert_called_once()
            assert mock_agent.generate.call_args.args[0] is None
        finally:
            workflow_module.ENABLE_PLANNER = original_enable_planner
            workflow_module.ENABLE_RAG = original_enable_rag
            workflow_module.RAG_MODULE_AVAILABLE = original_rag_available

    def test_rag_init_failure_no_retry(self):
        """RAG 检索器构造失败后置位标志，后续调用直接返回 None 不再重试构造。

        回归：此前 except 分支把 _rag_retriever 置 None（本就是 None，no-op），
        每个 generator/executor/debugger 节点都会重复尝试初始化（各付 2-6s）。
        现置位 _rag_init_failed，快路径直接短路。
        """
        import src.graph.workflow as workflow_module
        from src.graph.workflow import get_rag_retriever

        original_retriever = workflow_module._rag_retriever
        original_failed = workflow_module._rag_init_failed
        original_available = workflow_module.RAG_MODULE_AVAILABLE
        original_cls = workflow_module.TestCaseRetriever
        try:
            workflow_module._rag_retriever = None
            workflow_module._rag_init_failed = False
            workflow_module.RAG_MODULE_AVAILABLE = True

            failing_cls = MagicMock()
            failing_cls.side_effect = RuntimeError("持久目录损坏")
            workflow_module.TestCaseRetriever = failing_cls

            assert get_rag_retriever() is None
            assert workflow_module._rag_init_failed is True
            assert failing_cls.call_count == 1

            # 第二次调用：快路径短路，不再尝试构造
            assert get_rag_retriever() is None
            assert failing_cls.call_count == 1
        finally:
            workflow_module._rag_retriever = original_retriever
            workflow_module._rag_init_failed = original_failed
            workflow_module.RAG_MODULE_AVAILABLE = original_available
            workflow_module.TestCaseRetriever = original_cls


class TestPatchApplierNode:
    """_patch_applier_node 状态/磁盘一致性回归测试。"""

    @staticmethod
    def _state(target_file: str, target_code: str, patch: str) -> dict:
        return {
            "target_file": target_file,
            "target_code": target_code,
            "patch": patch,
            "diagnosis": "诊断",
            "error_category": "runtime",
            "iteration": 1,
            "repair_history": [],
        }

    def test_write_success_updates_state(self, tmp_path):
        """写盘成功：target_code 更新、patch_applied=True、文件被真实修改。"""
        from src.graph.workflow import _patch_applier_node

        target = tmp_path / "mod.py"
        target.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        state = self._state(str(target), "def add(a, b):\n    return a + b\n", "def add(a, b):\n    return a + b + 1\n")
        result = _patch_applier_node(state)
        assert "+ 1" in result["target_code"]
        assert result["repair_history"][-1]["patch_applied"] is True
        assert "+ 1" in target.read_text(encoding="utf-8")

    def test_rejected_path_keeps_original_state(self, tmp_path):
        """路径不在白名单（项目根/系统临时目录）→ 拒绝写盘，target_code 保留原代码、patch_applied=False。"""
        from src.graph.workflow import _patch_applier_node

        # 既不在项目根目录下、也不在系统临时目录下的绝对路径
        target = "/definitely_not_allowed_path/mod.py"
        state = self._state(target, "def add(a, b):\n    return a + b\n", "def add(a, b):\n    return a + b + 1\n")
        result = _patch_applier_node(state)
        assert result["target_code"] == "def add(a, b):\n    return a + b\n"
        assert result["repair_history"][-1]["patch_applied"] is False


class TestGeneratorNodeRegeneration:
    """_generator_node 再生成路径：递增 regeneration_count 并清空过期 diagnosis。"""

    @staticmethod
    def _with_rag_disabled():
        import src.graph.workflow as workflow_module

        orig = (workflow_module.ENABLE_PLANNER, workflow_module.ENABLE_RAG, workflow_module.RAG_MODULE_AVAILABLE)
        workflow_module.ENABLE_PLANNER = False
        workflow_module.ENABLE_RAG = False
        workflow_module.RAG_MODULE_AVAILABLE = False
        return workflow_module, orig

    @staticmethod
    def _restore(workflow_module, orig):
        workflow_module.ENABLE_PLANNER, workflow_module.ENABLE_RAG, workflow_module.RAG_MODULE_AVAILABLE = orig

    @patch("src.graph.workflow.GeneratorAgent")
    def test_regeneration_increments_counter(self, mock_generator_class):
        workflow_module, orig = self._with_rag_disabled()
        try:
            mock_generator_class.return_value.generate.return_value = "def test_x(): pass"
            # 再生成路径：iteration >= max_iterations
            state = {
                "iteration": 3,
                "max_iterations": 3,
                "target_code": "def x(): pass",
                "module_name": "m",
                "diagnosis": "测试生成错误",
            }
            result = workflow_module._generator_node(state)
            assert result["regeneration_count"] == 1
            assert result["diagnosis"] is None
            assert result["error_category"] is None
        finally:
            self._restore(workflow_module, orig)

    @patch("src.graph.workflow.GeneratorAgent")
    def test_first_generation_does_not_increment(self, mock_generator_class):
        workflow_module, orig = self._with_rag_disabled()
        try:
            mock_generator_class.return_value.generate.return_value = "def test_x(): pass"
            # 首次生成：iteration < max_iterations
            state = {
                "iteration": 0,
                "max_iterations": 3,
                "target_code": "def x(): pass",
                "module_name": "m",
                "diagnosis": "旧诊断",
            }
            result = workflow_module._generator_node(state)
            assert "regeneration_count" not in result
            assert "diagnosis" not in result  # 首次生成不清空 diagnosis
        finally:
            self._restore(workflow_module, orig)
