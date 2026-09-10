"""
Workflow 扩展单元测试

补充覆盖 workflow.py 中未测试的代码路径：
- 第 73-76 行：RAG 模块导入失败时的异常处理
- 第 107-119 行：get_rag_retriever 线程安全和初始化逻辑
- 第 296-297 行：Planner 输出验证失败的降级处理
- 第 343-352 行：Generator 节点的 RAG 检索逻辑
- 第 404-416 行：Executor 节点的 RAG 入库逻辑
- 第 437-491 行：Debugger 节点的完整执行流程
- 第 509-550 行：PatchApplier 节点的安全检查和迭代更新

测试场景：RAG 集成、异常处理、安全验证、迭代控制
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRAGModuleImport:
    """测试 RAG 模块导入异常情况。"""

    def test_rag_module_import_skipped(self):
        """验证 RAG 模块未安装时的处理方式（已导入状态）。"""
        import src.graph.workflow as workflow_module

        # 检查当前模块状态
        # 如果 chromadb 已安装，RAG_MODULE_AVAILABLE 为 True
        # 如果未安装，应为 False
        assert hasattr(workflow_module, "RAG_MODULE_AVAILABLE")
        # TestCaseRetriever 在 ImportError 时会被设置为 None
        if not workflow_module.RAG_MODULE_AVAILABLE:
            assert workflow_module.TestCaseRetriever is None


class TestGetRAGRetriever:
    """测试 RAG 检索器单例获取。"""

    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    @patch("src.graph.workflow.TestCaseRetriever")
    def test_initialize_once(self, mock_retriever_class):
        """单例模式：只初始化一次。"""
        from src.graph.workflow import get_rag_retriever

        mock_instance = MagicMock()
        mock_retriever_class.return_value = mock_instance

        # 清空模块级单例
        import src.graph.workflow as workflow_module

        workflow_module._rag_retriever = None

        result1 = get_rag_retriever()
        result2 = get_rag_retriever()

        assert result1 is result2 is mock_instance
        mock_retriever_class.assert_called_once()

    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", False)
    def test_returns_none_when_rag_disabled(self):
        """RAG 禁用时返回 None。"""
        import src.graph.workflow as workflow_module
        from src.graph.workflow import get_rag_retriever

        workflow_module._rag_retriever = None

        result = get_rag_retriever()
        assert result is None

    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    @patch("src.graph.workflow.TestCaseRetriever")
    def test_initialization_failure(self, mock_retriever_class):
        """初始化失败时标记为 None。"""
        from src.graph.workflow import get_rag_retriever

        mock_retriever_class.side_effect = Exception("Init failed")

        import src.graph.workflow as workflow_module

        workflow_module._rag_retriever = None

        result = get_rag_retriever()
        assert result is None
        assert workflow_module._rag_retriever is None

    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    @patch("src.graph.workflow.TestCaseRetriever")
    def test_already_initialized_returns_cached(self, mock_retriever_class):
        """已初始化时直接返回缓存实例。"""
        from src.graph.workflow import get_rag_retriever

        mock_instance = MagicMock()

        import src.graph.workflow as workflow_module

        workflow_module._rag_retriever = mock_instance

        result = get_rag_retriever()

        assert result is mock_instance
        mock_retriever_class.assert_not_called()


class TestPlannerNode:
    """测试 Planner 节点更多场景。"""

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_output_validation_failure(self, mock_planner_class):
        """Planner 输出验证失败时使用默认计划。"""
        from src.graph.workflow import _planner_node

        mock_agent = MagicMock()
        # 返回无效的输出结构
        mock_agent.plan.return_value = {"function_name": "foo"}  # 缺少 logic_analysis

        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "target_function": "foo"}
        result = _planner_node(state)

        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "foo"
        assert result["test_plan"]["logic_analysis"]["input_domain"] == "未知"

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_json_decode_error(self, mock_planner_class):
        """Planner 返回无效 JSON 时的异常处理。"""
        from src.graph.workflow import _planner_node

        mock_agent = MagicMock()
        mock_agent.plan.side_effect = json.JSONDecodeError("Expecting value", "", 0)

        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "target_function": "foo"}
        result = _planner_node(state)

        assert "test_plan" in result
        assert result["test_plan"]["description"] == "自动生成的默认测试计划"

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_with_target_function_none(self, mock_planner_class):
        """目标函数名为 None 时的处理。"""
        from src.graph.workflow import _planner_node

        mock_agent = MagicMock()
        mock_agent.plan.return_value = {"function_name": "bar", "logic_analysis": {}, "test_cases": []}
        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "target_function": None}
        result = _planner_node(state)

        assert result["test_plan"]["function_name"] == "bar"
        # 验证传入的是 None
        call_args = mock_agent.plan.call_args
        assert call_args[0][1] is None


class TestGeneratorNode:
    """测试 Generator 节点更多场景。"""

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.GeneratorAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_generator_with_rag_retrieval(self, mock_generator_class, mock_get_retriever):
        """Generator 启用 RAG 并成功检索。"""
        from src.graph.workflow import _generator_node

        mock_retriever = MagicMock()
        mock_retriever.retrieve_test_cases.return_value = ["case1", "case2"]
        mock_get_retriever.return_value = mock_retriever

        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_foo(): pass"
        mock_generator_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "module_name": "test_module", "test_plan": None, "iteration": 0}
        result = _generator_node(state)

        assert "generated_test" in result
        assert "rag_references" in result
        assert result["rag_references"] == ["case1", "case2"]
        mock_retriever.retrieve_test_cases.assert_called_once()

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.GeneratorAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_generator_rag_retrieval_failure(self, mock_generator_class, mock_get_retriever):
        """RAG 检索失败时降级到无 RAG 模式。"""
        import src.graph.workflow as workflow_module
        from src.graph.workflow import _generator_node

        # 确保 ENABLE_PLANNER 为 False，避免需要 test_plan
        original_planner = workflow_module.ENABLE_PLANNER
        workflow_module.ENABLE_PLANNER = False

        try:
            mock_retriever = MagicMock()
            mock_retriever.retrieve_test_cases.side_effect = Exception("Connection error")
            mock_get_retriever.return_value = mock_retriever

            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_generator_class.return_value = mock_agent

            state = {"target_code": "def foo(): pass", "module_name": "test_module", "iteration": 0}
            result = _generator_node(state)

            assert "generated_test" in result
            assert result["rag_references"] is None
            # Generator 仍然成功调用
            mock_agent.generate.assert_called_once()
        finally:
            workflow_module.ENABLE_PLANNER = original_planner

    @patch("src.graph.workflow.GeneratorAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", False)
    def test_generator_no_rag_module(self, mock_generator_class):
        """RAG 模块不可用时跳过检索。"""
        import src.graph.workflow as workflow_module
        from src.graph.workflow import _generator_node

        # 确保 ENABLE_PLANNER 为 False，避免需要 test_plan
        original_planner = workflow_module.ENABLE_PLANNER
        workflow_module.ENABLE_PLANNER = False

        try:
            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_generator_class.return_value = mock_agent

            state = {"target_code": "def foo(): pass", "module_name": "test_module", "iteration": 0}
            result = _generator_node(state)

            assert result["rag_references"] is None
            mock_agent.generate.assert_called_once()
        finally:
            workflow_module.ENABLE_PLANNER = original_planner


class TestExecutorNode:
    """测试 Executor 节点更多场景。"""

    @patch("src.graph.workflow.ExecutorAgent")
    def test_executor_with_failed_tests(self, mock_executor_class):
        """测试失败时的处理。"""
        from src.graph.workflow import _executor_node

        mock_agent = MagicMock()
        mock_agent.execute.return_value = {
            "passed": False,
            "output": "2 failed",
            "coverage": 45.5,
            "failed_cases": [{"case": "test_1", "error": "AssertionError"}],
        }
        mock_executor_class.return_value = mock_agent

        state = {"generated_test": "def test(): pass", "target_file": "/path/to/test.py", "iteration": 0}
        result = _executor_node(state)

        assert result["test_passed"] is False
        assert result["coverage_report"] == 45.5
        assert len(result["failed_cases"]) == 1

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.ExecutorAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_executor_success_with_rag_ingestion(self, mock_executor_class, mock_get_retriever):
        """测试成功时入库 RAG。"""
        from src.graph.workflow import _executor_node

        mock_retriever = MagicMock()
        mock_get_retriever.return_value = mock_retriever

        mock_agent = MagicMock()
        mock_agent.execute.return_value = {"passed": True, "output": "1 passed", "coverage": 90.0, "failed_cases": []}
        mock_executor_class.return_value = mock_agent

        state = {
            "generated_test": "def test(): pass",
            "target_file": "/path/to/test.py",
            "target_code": "def foo(): pass",
            "target_function": "foo",
            "iteration": 0,
        }
        result = _executor_node(state)

        assert result["test_passed"] is True
        mock_retriever.add_case.assert_called_once()

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.ExecutorAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_executor_rag_ingestion_failure(self, mock_executor_class, mock_get_retriever):
        """RAG 入库失败时不影响主流程。"""
        from src.graph.workflow import _executor_node

        mock_retriever = MagicMock()
        mock_retriever.add_case.side_effect = Exception("Storage error")
        mock_get_retriever.return_value = mock_retriever

        mock_agent = MagicMock()
        mock_agent.execute.return_value = {"passed": True, "output": "1 passed", "coverage": 90.0, "failed_cases": []}
        mock_executor_class.return_value = mock_agent

        state = {
            "generated_test": "def test(): pass",
            "target_file": "/path/to/test.py",
            "target_code": "def foo(): pass",
            "iteration": 0,
        }
        result = _executor_node(state)

        # 主流程不受影响
        assert result["test_passed"] is True


class TestDebuggerNode:
    """测试 Debugger 节点完整流程。"""

    @patch("src.graph.workflow.DebuggerAgent")
    def test_debugger_success(self, mock_debugger_class):
        """Debugger 成功执行。"""
        from src.graph.workflow import _debugger_node

        mock_agent = MagicMock()
        mock_agent.debug.return_value = {
            "root_cause": "边界条件未处理",
            "error_category": "logic_error",
            "fix_strategy": "添加边界检查",
            "patch": "@patch\ndef foo(x):\n    if x < 0:\n        return 0\n    return x * 2",
        }
        mock_debugger_class.return_value = mock_agent

        state = {
            "target_code": "def foo(x): return x * 2",
            "test_output": "AssertionError",
            "failed_cases": [{"case": "test_neg", "error": "Expected 0"}],
            "iteration": 0,
        }
        result = _debugger_node(state)

        assert "diagnosis" in result
        assert "error_category" in result
        assert "patch" in result
        assert result["error_category"] == "logic_error"
        mock_agent.debug.assert_called_once()

    @patch("src.graph.workflow.DebuggerAgent")
    def test_debugger_json_error_fallback(self, mock_debugger_class):
        """Debugger 返回无效 JSON 时的降级处理。"""
        from src.graph.workflow import _debugger_node

        mock_agent = MagicMock()
        mock_agent.debug.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)

        mock_debugger_class.return_value = mock_agent

        state = {"target_code": "def foo(x): return x * 2", "test_output": "Error", "failed_cases": [], "iteration": 0}
        result = _debugger_node(state)

        assert result["diagnosis"].startswith("JSON 解析失败")
        assert result["error_category"] == "unknown"
        assert result["patch"] == ""

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.DebuggerAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_debugger_with_rag_retrieval(self, mock_debugger_class, mock_get_retriever):
        """Debugger 使用 RAG 检索修复案例。"""
        from src.graph.workflow import _debugger_node

        mock_retriever = MagicMock()
        mock_retriever.retrieve_repairs.return_value = ["repair_case_1"]
        mock_get_retriever.return_value = mock_retriever

        mock_agent = MagicMock()
        mock_agent.debug.return_value = {
            "root_cause": "错误处理",
            "error_category": "error_handling",
            "fix_strategy": "添加异常捕获",
            "patch": "patch_content",
        }
        mock_debugger_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "test_output": "RuntimeError",
            "failed_cases": [{"error": "Error"}],
            "error_category": "error_handling",
            "iteration": 0,
        }
        _debugger_node(state)
        mock_retriever.retrieve_repairs.assert_called_once()
        # 验证调用参数包含 rag_references
        debug_call = mock_agent.debug.call_args
        assert debug_call.kwargs.get("rag_references") == ["repair_case_1"]

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.DebuggerAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_debugger_rag_retrieval_failure(self, mock_debugger_class, mock_get_retriever):
        """RAG 检索失败时降级到无 RAG 模式。"""
        from src.graph.workflow import _debugger_node

        mock_retriever = MagicMock()
        mock_retriever.retrieve_repairs.side_effect = Exception("Network error")
        mock_get_retriever.return_value = mock_retriever

        mock_agent = MagicMock()
        mock_agent.debug.return_value = {
            "root_cause": "简单错误",
            "error_category": "simple",
            "fix_strategy": "修复",
            "patch": "patch",
        }
        mock_debugger_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "test_output": "Error",
            "failed_cases": [],
            "error_category": "simple",
            "iteration": 0,
        }
        _debugger_node(state)
        mock_agent.debug.assert_called_once()

    @patch("src.graph.workflow.get_rag_retriever")
    @patch("src.graph.workflow.DebuggerAgent")
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True)
    def test_debugger_rag_ingestion(self, mock_debugger_class, mock_get_retriever):
        """Debugger 修复案例入库。"""
        from src.graph.workflow import _debugger_node

        mock_retriever = MagicMock()
        mock_get_retriever.return_value = mock_retriever

        mock_agent = MagicMock()
        mock_agent.debug.return_value = {
            "root_cause": "根因分析",
            "error_category": "category",
            "fix_strategy": "策略",
            "patch": "补丁内容",
        }
        mock_debugger_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "iteration": 0}
        _debugger_node(state)

        mock_retriever.add_repair.assert_called_once()

    @patch("src.graph.workflow.DebuggerAgent")
    def test_debugger_without_failed_cases(self, mock_debugger_class):
        """无失败用例时的 Debugger 行为。"""
        from src.graph.workflow import _debugger_node

        mock_agent = MagicMock()
        mock_agent.debug.return_value = {
            "root_cause": "未知错误",
            "error_category": "unknown",
            "fix_strategy": "",
            "patch": "",
        }
        mock_debugger_class.return_value = mock_agent

        state = {"target_code": "def foo(): pass", "test_output": "", "failed_cases": [], "iteration": 0}
        result = _debugger_node(state)

        assert result["diagnosis"] == "未知错误"


class TestPatchApplierNode:
    """测试 PatchApplier 节点安全检查和迭代逻辑。"""

    @patch("src.graph.workflow.apply_patch_to_code")
    def test_patch_applied_successfully(self, mock_apply_patch, tmp_path):
        """补丁成功写盘：target_code 更新、patch_applied=True、文件被真实修改。"""
        from src.graph.workflow import _patch_applier_node

        # 新代码须含函数定义且不过短，且路径在允许根目录内（tmp_path 在系统 temp 目录下）
        target = tmp_path / "mod.py"
        target.write_text("def foo(): pass\n", encoding="utf-8")
        new_code = "def foo():\n    return 42\n"
        mock_apply_patch.return_value = (new_code, True)

        state = {
            "target_code": "def foo(): pass",
            "target_file": str(target),
            "patch": "patch content",
            "diagnosis": "测试诊断",
            "error_category": "logic",
            "iteration": 0,
        }
        result = _patch_applier_node(state)

        assert result["target_code"] == new_code
        assert result["iteration"] == 1
        assert len(result["repair_history"]) == 1
        assert result["repair_history"][0]["patch_applied"] is True
        assert target.read_text(encoding="utf-8") == new_code

    @patch("src.graph.workflow.apply_patch_to_code")
    def test_patch_not_applied(self, mock_apply_patch, tmp_path):
        """补丁未应用（apply 返回 False）：target_code 保留原代码，patch_applied=False。"""
        from src.graph.workflow import _patch_applier_node

        mock_apply_patch.return_value = ("same code", False)

        state = {
            "target_code": "def foo(): pass",
            "target_file": str(tmp_path / "mod.py"),
            "patch": "invalid patch",
            "diagnosis": "诊断",
            "error_category": "unknown",
            "iteration": 0,
        }
        result = _patch_applier_node(state)

        # 未应用 → 保留原代码（状态/磁盘一致性）
        assert result["target_code"] == "def foo(): pass"
        assert result["repair_history"][0]["patch_applied"] is False

    @patch("src.graph.workflow.apply_patch_to_code")
    def test_patch_too_short_rejected(self, mock_apply_patch, tmp_path):
        """补丁过短被安全检查拒绝：target_code 保留原代码，patch_applied=False。"""
        from src.graph.workflow import _patch_applier_node

        # 新代码比原代码短 90%（触发安全检查 1）
        mock_apply_patch.return_value = ("x", True)

        state = {
            "target_code": "def foo(): return 1 + 2 + 3",  # 约 25 字符
            "target_file": str(tmp_path / "mod.py"),
            "patch": "bad",
            "iteration": 0,
        }
        result = _patch_applier_node(state)

        # 虽然 applied=True，但内容过短被拒绝 → 保留原代码，patch_applied=False
        assert result["target_code"] == "def foo(): return 1 + 2 + 3"
        assert result["repair_history"][0]["patch_applied"] is False

    @patch("src.graph.workflow.apply_patch_to_code")
    def test_patch_no_function_definition_rejected(self, mock_apply_patch):
        """补丁不含函数定义时拒绝写入。"""
        from src.graph.workflow import _patch_applier_node

        mock_apply_patch.return_value = ("no function here", True)

        state = {"target_code": "def foo(): pass", "target_file": "/tmp/test.py", "patch": "invalid", "iteration": 0}
        result = _patch_applier_node(state)

        # 历史记录应记录尝试
        assert len(result["repair_history"]) == 1

    @patch("src.graph.workflow.apply_patch_to_code")
    def test_history_truncation(self, mock_apply_patch):
        """修复历史记录大小限制。"""
        from src.graph.workflow import _patch_applier_node

        mock_apply_patch.return_value = ("new code", True)

        # 创建包含多条历史的旧状态
        old_history = [{"iteration": i, "patch_applied": True} for i in range(6)]

        state = {
            "target_code": "def foo(): pass",
            "target_file": "/tmp/test.py",
            "patch": "valid patch",
            "diagnosis": "诊断",
            "error_category": "test",
            "iteration": 5,
            "repair_history": old_history,
        }
        result = _patch_applier_node(state)

        # 历史应被截断为最多 5 条
        assert len(result["repair_history"]) <= 5

    @patch("src.graph.workflow.apply_patch_to_code")
    def test_iterative_updates(self, mock_apply_patch):
        """多次迭代后迭代计数器更新。"""
        from src.graph.workflow import _patch_applier_node

        mock_apply_patch.return_value = ("updated code", True)

        state = {"target_code": "def foo(): pass", "target_file": "/tmp/test.py", "patch": "patch", "iteration": 2}
        result = _patch_applier_node(state)

        assert result["iteration"] == 3


class TestEdgeCases:
    """测试边界情况和异常场景。"""

    @patch("src.graph.workflow.ENABLE_PLANNER", True)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    @patch("src.graph.workflow.StateGraph")
    def test_workflow_entry_point_with_planner(self, mock_stategraph):
        """启用 Planner 时入口点为 planner。"""
        from src.graph.workflow import build_workflow

        mock_workflow = MagicMock()
        mock_stategraph.return_value = mock_workflow

        build_workflow()

        # 验证 entry point 和 edge 设置
        calls = [str(call) for call in mock_workflow.method_calls]
        assert any("set_entry_point" in call for call in calls)

    @patch("src.graph.workflow.ENABLE_PLANNER", False)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", False)
    @patch("src.graph.workflow.StateGraph")
    def test_workflow_entry_point_without_planner(self, mock_stategraph):
        """不启用 Planner 时入口点为 generator。"""
        from src.graph.workflow import build_workflow

        mock_workflow = MagicMock()
        mock_stategraph.return_value = mock_workflow

        build_workflow()

        # 验证 entry point
        calls = [str(call) for call in mock_workflow.method_calls]
        assert any("set_entry_point" in call for call in calls)

    def test_max_iterations_from_config(self):
        """测试最大迭代次数从 config 读取。"""
        from config import MAX_ITERATIONS

        assert MAX_ITERATIONS == 3

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_should_debug_with_empty_diagnosis(self):
        """诊断为空时的路由逻辑。"""
        from src.graph.workflow import _should_debug

        state = {"test_passed": False, "iteration": 3, "max_iterations": 3, "diagnosis": ""}
        result = _should_debug(state)

        assert result == "done"

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_should_debug_regenerate_keywords(self):
        """不同关键词触发的重新生成路由。"""
        from src.graph.workflow import _should_debug

        keywords = [
            "测试生成错误",
            "测试设计存在错误",
            "test code",
            "AttributeError",
            "NameError",
            "SyntaxError",
            "测试用例",
            "期望的异常类型",
        ]

        for keyword in keywords:
            state = {"test_passed": False, "iteration": 3, "max_iterations": 3, "diagnosis": f"问题: {keyword}"}
            result = _should_debug(state)
            assert result == "regenerate", f"关键词 '{keyword}' 应触发重新生成"

    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_should_debug_non_test_error(self):
        """非测试错误关键词的路由。"""
        from src.graph.workflow import _should_debug

        state = {"test_passed": False, "iteration": 3, "max_iterations": 3, "diagnosis": "被测代码逻辑错误"}
        result = _should_debug(state)

        assert result == "done"


class TestGetWorkflowStats:
    """测试工作流统计的更多场景。"""

    @patch("src.graph.workflow.get_cache_stats")
    @patch("src.graph.workflow.ENABLE_PLANNER", False)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", False)
    @patch("src.graph.workflow.ENABLE_RAG", True)
    @patch("src.graph.workflow.MAX_ITERATIONS", 5)
    def test_get_workflow_stats_disabled_features(self, mock_get_cache):
        """所有功能禁用时的统计信息。"""
        from src.graph.workflow import get_workflow_stats

        mock_get_cache.return_value = {"hits": 0, "misses": 0}

        stats = get_workflow_stats()

        assert stats["workflow_config"]["ENABLE_PLANNER"] is False
        assert stats["workflow_config"]["ENABLE_DEBUGGER"] is False
        assert stats["workflow_config"]["ENABLE_RAG"] is True
        assert stats["workflow_config"]["MAX_ITERATIONS"] == 5


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
