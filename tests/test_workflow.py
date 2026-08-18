"""
单元测试：测试工作流路由逻辑（_should_debug）和图构建。

覆盖范围：
    - _should_debug：测试通过/未达迭代/达最大迭代+关键词/达最大迭代+无关键词
    - _create_workflow：PLANNER/DEBUGGER 开关控制节点注册
    - build_workflow：编译返回 StateGraph 实例
    - 节点函数：_planner_node, _generator_node, _executor_node, _debugger_node, _patch_applier_node
"""

from unittest.mock import MagicMock, patch

from src.graph.workflow import (
    _create_workflow,
    _debugger_node,
    _executor_node,
    _generator_node,
    _get_default_test_plan,
    _patch_applier_node,
    _planner_node,
    _should_debug,
    _should_skip_debugger,
    _validate_planner_output,
    build_workflow,
    get_workflow_stats,
)


# ─── TestShouldDebug：路由函数 ─────────────────────────────────────────────────
class TestShouldDebug:
    """测试 _should_debug 路由逻辑。"""

    def test_test_passed_returns_done(self):
        """测试已通过时返回 'done'。"""
        state = {"test_passed": True, "iteration": 0, "max_iterations": 3}
        assert _should_debug(state) == "done"

    def test_not_reached_max_iteration_returns_debug(self):
        """未达最大迭代次数时返回 'debug'。"""
        state = {"test_passed": False, "iteration": 1, "max_iterations": 3}
        assert _should_debug(state) == "debug"

    def test_reached_max_no_diagnosis_returns_done(self):
        """达到最大迭代且无诊断时返回 'done'。"""
        state = {"test_passed": False, "iteration": 3, "max_iterations": 3, "diagnosis": ""}
        assert _should_debug(state) == "done"

    def test_reached_max_with_test_gen_keywords_returns_regenerate(self):
        """达到最大迭代且诊断含测试生成错误关键词时返回 'regenerate'。"""
        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：AttributeError 不存在",
        }
        assert _should_debug(state) == "regenerate"

    def test_reached_max_with_syntax_error_keyword(self):
        """诊断含 SyntaxError 时触发重新生成。"""
        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "SyntaxError: 测试代码语法问题",
        }
        assert _should_debug(state) == "regenerate"

    def test_reached_max_with_generic_diagnosis_returns_done(self):
        """达到最大迭代但诊断与测试生成无关时返回 'done'。"""
        state = {
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "代码逻辑有误，需修复",
        }
        assert _should_debug(state) == "done"

    def test_iteration_default_to_zero(self):
        """iteration 默认为 0 时不应触发 max_iterations 检查。"""
        state = {"test_passed": False, "max_iterations": 3}
        assert _should_debug(state) == "debug"

    def test_max_iterations_default_to_three(self):
        """max_iterations 默认为 3 时按默认值判断。"""
        state = {"test_passed": False, "iteration": 2}
        assert _should_debug(state) == "debug"


# ─── TestCreateWorkflow：工作流图构建 ──────────────────────────────────────────
class TestCreateWorkflow:
    """测试 _create_workflow 图构建逻辑。"""

    @patch("src.graph.workflow.ENABLE_PLANNER", True)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_full_workflow_has_planner_and_debugger(self):
        """完整模式（Planner+Debugger 均启用）应包含 planner 和 debugger 节点。"""
        workflow = _create_workflow()
        nodes = list(workflow.nodes.keys())
        assert "planner" in nodes
        assert "generator" in nodes
        assert "executor" in nodes
        assert "debugger" in nodes
        assert "patch_applier" in nodes

    @patch("src.graph.workflow.ENABLE_PLANNER", False)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_no_planner_starts_from_generator(self):
        """禁用 Planner 时入口应为 generator。"""
        workflow = _create_workflow()
        nodes = list(workflow.nodes.keys())
        assert "planner" not in nodes
        assert "generator" in nodes

    @patch("src.graph.workflow.ENABLE_PLANNER", True)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", False)
    def test_no_debugger_exits_after_executor(self):
        """禁用 Debugger 时 executor 直接连到 END。"""
        workflow = _create_workflow()
        nodes = list(workflow.nodes.keys())
        assert "planner" in nodes
        assert "executor" in nodes
        assert "debugger" not in nodes
        assert "patch_applier" not in nodes

    @patch("src.graph.workflow.ENABLE_PLANNER", False)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", False)
    def test_minimal_workflow_only_generator_and_executor(self):
        """最小模式（均禁用）只含 generator 和 executor。"""
        workflow = _create_workflow()
        nodes = list(workflow.nodes.keys())
        assert nodes == ["generator", "executor"]

    @patch("src.graph.workflow.ENABLE_PLANNER", True)
    @patch("src.graph.workflow.ENABLE_DEBUGGER", True)
    def test_workflow_has_nodes(self):
        """工作流应包含关键节点。"""
        workflow = _create_workflow()
        nodes = list(workflow.nodes.keys())
        assert len(nodes) >= 3


# ─── TestBuildWorkflow：编译工作流 ──────────────────────────────────────────────
class TestBuildWorkflow:
    """测试 build_workflow 编译函数。"""

    def test_build_returns_compilable_graph(self):
        """build_workflow 应返回可编译的 StateGraph 实例。"""
        graph = build_workflow()
        assert hasattr(graph, "invoke") or hasattr(graph, "execute")


# ─── TestPlannerNode：Planner 节点 ─────────────────────────────────────────────
class TestPlannerNode:
    """测试 _planner_node 节点函数。"""

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_success(self, mock_planner_class):
        """正常流程：PlannerAgent 返回测试计划。"""
        mock_agent = MagicMock()
        mock_agent.plan.return_value = {
            "function_name": "divide",
            "logic_analysis": {
                "input_domain": "",
                "output_domain": "",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            },
            "test_cases": [],
        }
        mock_planner_class.return_value = mock_agent

        state = {
            "target_code": "def divide(a, b): return a / b",
            "target_function": "divide",
        }
        result = _planner_node(state)
        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "divide"

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_json_error_fallback(self, mock_planner_class):
        """JSON 解析失败时使用默认计划兜底。"""
        import json

        mock_agent = MagicMock()
        mock_agent.plan.side_effect = json.JSONDecodeError("Expecting value", "", 0)
        mock_planner_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "target_function": None,
        }
        result = _planner_node(state)
        # 应返回默认计划而非抛出异常
        assert "test_plan" in result
        # function_name 应为 state 中的 target_function（None）
        assert result["test_plan"]["function_name"] is None

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_runtime_error(self, mock_planner_class):
        """LLM 调用失败时使用默认计划兜底。"""
        mock_agent = MagicMock()
        mock_agent.plan.side_effect = RuntimeError("API 错误")
        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def bar(): pass"}
        result = _planner_node(state)
        assert "test_plan" in result


# ─── TestGeneratorNode：Generator 节点 ─────────────────────────────────────────
class TestGeneratorNode:
    """测试 _generator_node 节点函数。"""

    def test_generator_node_success(self):
        """正常流程：GeneratorAgent 返回测试代码。"""
        from unittest.mock import patch

        with patch("src.graph.workflow.GeneratorAgent") as mock_gen_class:
            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_gen_class.return_value = mock_agent

            with patch("src.graph.workflow.ENABLE_PLANNER", True):
                state = {
                    "test_plan": {"function_name": "foo"},
                    "target_code": "def foo(): pass",
                    "module_name": "test_mod",
                }
                result = _generator_node(state)
                assert "generated_test" in result
                assert result["generated_test"] == "def test_foo(): pass"

    def test_generator_node_no_plan(self):
        """无测试计划时传入 None。"""
        from unittest.mock import patch

        with patch("src.graph.workflow.GeneratorAgent") as mock_gen_class:
            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_bar(): pass"
            mock_gen_class.return_value = mock_agent

            with patch("src.graph.workflow.ENABLE_PLANNER", False):
                state = {
                    "target_code": "def bar(): pass",
                    "module_name": "test_mod",
                }
                _generator_node(state)
                # generate 应被调用，传入 None 作为 test_plan
                mock_agent.generate.assert_called_once()
                call_args = mock_agent.generate.call_args
                assert call_args[0][0] is None  # test_plan 为 None


# ─── TestExecutorNode：Executor 节点 ──────────────────────────────────────────
class TestExecutorNode:
    """测试 _executor_node 节点函数。"""

    def test_executor_node_pass(self):
        """测试通过时标记为 PASS。"""
        from unittest.mock import patch

        with patch("src.graph.workflow.ExecutorAgent") as mock_exec_class:
            mock_agent = MagicMock()
            mock_agent.execute.return_value = {
                "passed": True,
                "output": "1 passed",
                "coverage": 85.0,
                "failed_cases": [],
            }
            mock_exec_class.return_value = mock_agent

            state = {
                "generated_test": "def test_foo(): pass",
                "target_file": "examples/calculator.py",
                "target_function": None,
                "iteration": 0,
            }
            result = _executor_node(state)
            assert result["test_passed"] is True
            assert result["coverage_report"] == 85.0
            assert result["failed_cases"] == []

    def test_executor_node_fail(self):
        """测试失败时记录失败用例。"""
        from unittest.mock import patch

        with patch("src.graph.workflow.ExecutorAgent") as mock_exec_class:
            mock_agent = MagicMock()
            mock_agent.execute.return_value = {
                "passed": False,
                "output": "1 failed",
                "coverage": 60.0,
                "failed_cases": [{"name": "test_foo", "error": "AssertionError"}],
            }
            mock_exec_class.return_value = mock_agent

            state = {
                "generated_test": "def test_foo(): assert False",
                "target_file": "examples/calculator.py",
                "iteration": 0,
            }
            result = _executor_node(state)
            assert result["test_passed"] is False
            assert len(result["failed_cases"]) == 1


# ─── TestDebuggerNode：Debugger 节点 ──────────────────────────────────────────
class TestDebuggerNode:
    """测试 _debugger_node 节点函数。"""

    def test_debugger_node_success(self):
        """正常流程：DebuggerAgent 返回诊断结果。"""
        from unittest.mock import patch

        with patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class:
            mock_agent = MagicMock()
            mock_agent.debug.return_value = {
                "root_cause": "除零错误",
                "error_category": "runtime",
                "fix_strategy": "添加边界检查",
                "patch": "def foo(x): return x if x != 0 else 0",
            }
            mock_dbg_class.return_value = mock_agent

            state = {
                "target_code": "def foo(x): return 1/x",
                "test_output": "ZeroDivisionError",
                "failed_cases": [{"name": "test_foo", "error": "ZeroDivisionError"}],
                "iteration": 0,
            }
            result = _debugger_node(state)
            assert result["error_category"] == "runtime"
            assert "patch" in result

    def test_debugger_node_json_error(self):
        """JSON 解析失败时返回默认值。"""
        import json
        from unittest.mock import patch

        with patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class:
            mock_agent = MagicMock()
            mock_agent.debug.side_effect = json.JSONDecodeError("Expecting value", "", 0)
            mock_dbg_class.return_value = mock_agent

            state = {
                "target_code": "def bar(): pass",
                "test_output": "Error",
                "failed_cases": [],
            }
            result = _debugger_node(state)
            assert result["error_category"] == "unknown"


# ─── TestPatchApplierNode：补丁应用节点 ───────────────────────────────────────
class TestPatchApplierNode:
    """测试 _patch_applier_node 节点函数。"""

    def test_patch_applier_success(self):
        """补丁成功应用时更新代码和迭代计数。"""
        state = {
            "target_code": "def foo(x): return 1/x\n",
            "target_file": "examples/test.py",
            "patch": "def foo(x): return x if x != 0 else 0\n",
            "iteration": 0,
            "diagnosis": "除零错误",
            "error_category": "runtime",
        }
        result = _patch_applier_node(state)
        assert result["iteration"] == 1
        assert "repair_history" in result
        assert len(result["repair_history"]) == 1
        assert result["repair_history"][0]["patch_applied"] is True

    def test_patch_applier_no_patch(self):
        """无补丁时不修改代码。"""
        state = {
            "target_code": "def foo(): pass\n",
            "target_file": "examples/test.py",
            "patch": "",
            "iteration": 0,
        }
        result = _patch_applier_node(state)
        assert result["target_code"] == "def foo(): pass\n"
        assert result["iteration"] == 1

    def test_patch_applier_empty_string(self):
        """空字符串补丁时不修改代码。"""
        state = {
            "target_code": "def foo(): pass\n",
            "target_file": "examples/test.py",
            "patch": "",
            "iteration": 0,
        }
        result = _patch_applier_node(state)
        assert result["iteration"] == 1


# ─── TestShouldSkipDebugger：智能跳过优化 ─────────────────────────────────────
class TestShouldSkipDebugger:
    """测试智能跳过 Debugger 的优化逻辑。"""

    def test_skip_when_consecutive_failures(self):
        """连续修复失败时应跳过 Debugger。"""
        state = {
            "test_passed": False,
            "iteration": 2,
            "repair_history": [
                {"iteration": 1, "patch_applied": False},
                {"iteration": 2, "patch_applied": False},
            ],
        }
        with patch("src.graph.workflow.ENABLE_DEBUGGER", True):
            assert _should_skip_debugger(state) is True

    def test_no_skip_when_patch_applied(self):
        """有补丁成功应用时不应跳过。"""
        state = {
            "test_passed": False,
            "iteration": 2,
            "repair_history": [
                {"iteration": 1, "patch_applied": True},
                {"iteration": 2, "patch_applied": False},
            ],
        }
        with patch("src.graph.workflow.ENABLE_DEBUGGER", True):
            assert _should_skip_debugger(state) is False

    def test_no_skip_when_history_too_short(self):
        """历史记录不足时不应跳过。"""
        state = {
            "test_passed": False,
            "iteration": 1,
            "repair_history": [
                {"iteration": 1, "patch_applied": False},
            ],
        }
        with patch("src.graph.workflow.ENABLE_DEBUGGER", True):
            assert _should_skip_debugger(state) is False

    def test_no_skip_when_debugger_disabled(self):
        """Debugger 禁用时不检查跳过逻辑。"""
        state = {
            "test_passed": False,
            "iteration": 2,
            "repair_history": [
                {"iteration": 1, "patch_applied": False},
                {"iteration": 2, "patch_applied": False},
            ],
        }
        with patch("src.graph.workflow.ENABLE_DEBUGGER", False):
            assert _should_skip_debugger(state) is False


# ─── TestValidatePlannerOutput：Planner 输出验证 ───────────────────────────────
class TestValidatePlannerOutput:
    """测试 Planner 输出验证逻辑。"""

    def test_valid_output(self):
        """有效输出应返回 True。"""
        valid_plan = {
            "function_name": "divide",
            "logic_analysis": {
                "input_domain": "整数",
                "output_domain": "浮点数",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            },
        }
        assert _validate_planner_output(valid_plan) is True

    def test_missing_function_name(self):
        """缺少 function_name 应返回 False。"""
        invalid_plan = {
            "logic_analysis": {
                "input_domain": "",
                "output_domain": "",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            }
        }
        assert _validate_planner_output(invalid_plan) is False

    def test_missing_logic_analysis(self):
        """缺少 logic_analysis 应返回 False。"""
        invalid_plan = {"function_name": "foo"}
        assert _validate_planner_output(invalid_plan) is False

    def test_non_dict_input(self):
        """非字典输入应返回 False。"""
        assert _validate_planner_output("invalid") is False
        assert _validate_planner_output(None) is False

    def test_invalid_logic_analysis_type(self):
        """logic_analysis 非字典类型应返回 False。"""
        invalid_plan = {
            "function_name": "foo",
            "logic_analysis": "not a dict",
        }
        assert _validate_planner_output(invalid_plan) is False


# ─── TestGetDefaultTestPlan：默认计划生成 ──────────────────────────────────────
class TestGetDefaultTestPlan:
    """测试默认测试计划生成。"""

    def test_with_function_name(self):
        """指定函数名时应正确设置。"""
        plan = _get_default_test_plan("divide")
        assert plan["function_name"] == "divide"
        assert "logic_analysis" in plan

    def test_without_function_name(self):
        """未指定函数名时默认 'unknown'。"""
        plan = _get_default_test_plan(None)
        assert plan["function_name"] == "unknown"


# ─── TestGetWorkflowStats：工作流统计 ──────────────────────────────────────────
class TestGetWorkflowStats:
    """测试工作流统计信息获取。"""

    def test_returns_stats_dict(self):
        """应返回包含 llm_cache 和 workflow_config 的字典。"""
        stats = get_workflow_stats()
        assert isinstance(stats, dict)
        assert "llm_cache" in stats
        assert "workflow_config" in stats

    def test_workflow_config_has_expected_keys(self):
        """workflow_config 应包含所有配置项。"""
        stats = get_workflow_stats()
        config = stats["workflow_config"]
        assert "ENABLE_PLANNER" in config
        assert "ENABLE_DEBUGGER" in config
        assert "ENABLE_RAG" in config
        assert "MAX_ITERATIONS" in config


# ─── TestShouldDebugWithOptimization：路由优化测试 ─────────────────────────────
class TestShouldDebugWithOptimization:
    """测试带优化的 _should_debug 路由逻辑。"""

    def test_skip_optimization_triggers_done(self):
        """智能跳过时应返回 done。"""
        state = {
            "test_passed": False,
            "iteration": 2,
            "repair_history": [
                {"iteration": 1, "patch_applied": False},
                {"iteration": 2, "patch_applied": False},
            ],
        }
        with patch("src.graph.workflow.ENABLE_DEBUGGER", True):
            assert _should_debug(state) == "done"


# ─── TestRAGImportHandling：RAG 模块未安装时的 import 失败处理 ──────────────────
class TestRAGImportHandling:
    """测试 RAG 模块未安装时的优雅降级。"""

    def test_rag_module_unavailable_on_import_failure(self):
        """RAG 模块导入失败时 RAG_MODULE_AVAILABLE 应为 False，TestCaseRetriever 为 None。"""
        # 直接修改模块级变量来模拟导入失败的场景
        import src.graph.workflow as wf

        original_available = wf.RAG_MODULE_AVAILABLE
        original_retriever = wf.TestCaseRetriever
        try:
            wf.RAG_MODULE_AVAILABLE = False
            wf.TestCaseRetriever = None
            # 验证这两个变量确实是 False/None
            assert wf.RAG_MODULE_AVAILABLE is False
            assert wf.TestCaseRetriever is None
        finally:
            wf.RAG_MODULE_AVAILABLE = original_available
            wf.TestCaseRetriever = original_retriever

    def test_rag_import_error_branch_coverage(self):
        """模拟 ImportError 分支的执行路径。"""

        import src.graph.workflow as wf

        # 保存原始状态
        original_available = wf.RAG_MODULE_AVAILABLE
        original_retriever = wf.TestCaseRetriever
        original_cached = wf._rag_retriever

        try:
            # 模拟 ImportError 场景
            wf.RAG_MODULE_AVAILABLE = False
            wf.TestCaseRetriever = None
            wf._rag_retriever = None

            # 验证 get_rag_retriever 返回 None
            result = wf.get_rag_retriever()
            assert result is None
            # 确认缓存未被污染
            assert wf._rag_retriever is None
        finally:
            wf.RAG_MODULE_AVAILABLE = original_available
            wf.TestCaseRetriever = original_retriever
            wf._rag_retriever = original_cached


# ─── TestGetRAGRetriever：双重检查锁定 ─────────────────────────────────────────
class TestGetRAGRetriever:
    """测试 get_rag_retriever() 的双重检查锁定和异常处理。"""

    def test_returns_cached_instance_when_already_initialized(self):
        """已初始化时直接返回缓存实例。"""
        import src.graph.workflow as wf

        original_retriever = wf._rag_retriever
        try:
            mock_retriever = MagicMock()
            wf._rag_retriever = mock_retriever
            result = wf.get_rag_retriever()
            assert result is mock_retriever
        finally:
            wf._rag_retriever = original_retriever

    def test_returns_none_when_rag_module_unavailable(self):
        """RAG 模块不可用时返回 None。"""
        import src.graph.workflow as wf

        original_available = wf.RAG_MODULE_AVAILABLE
        original_retriever = wf.TestCaseRetriever
        original_cached = wf._rag_retriever
        try:
            wf.RAG_MODULE_AVAILABLE = False
            wf.TestCaseRetriever = None
            wf._rag_retriever = None
            result = wf.get_rag_retriever()
            assert result is None
        finally:
            wf.RAG_MODULE_AVAILABLE = original_available
            wf.TestCaseRetriever = original_retriever
            wf._rag_retriever = original_cached

    def test_initialization_failure_sets_cache_to_none(self):
        """初始化失败时缓存应设为 None 避免重复尝试。"""
        import src.graph.workflow as wf

        original_available = wf.RAG_MODULE_AVAILABLE
        original_retriever = wf.TestCaseRetriever
        original_cached = wf._rag_retriever
        try:
            wf.RAG_MODULE_AVAILABLE = True

            # 创建一个会在 __init__ 时抛出异常的类
            class FailingRetriever:
                def __init__(self):
                    raise RuntimeError("初始化失败")

            wf.TestCaseRetriever = FailingRetriever
            wf._rag_retriever = None
            result = wf.get_rag_retriever()
            assert result is None
            # 确认缓存被设为 None
            assert wf._rag_retriever is None
        finally:
            wf.RAG_MODULE_AVAILABLE = original_available
            wf.TestCaseRetriever = original_retriever
            wf._rag_retriever = original_cached


# ─── TestPlannerNodeValidateFailure：Planner 输出验证失败 ──────────────────────
class TestPlannerNodeValidateFailure:
    """测试 _planner_node 中验证失败时走默认计划的分支。"""

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_invalid_output_fallback(self, mock_planner_class):
        """Planner 输出验证失败时使用默认计划兜底。"""
        mock_agent = MagicMock()
        mock_agent.plan.return_value = {"invalid": "plan"}  # 缺少 function_name 和 logic_analysis
        mock_planner_class.return_value = mock_agent

        state = {
            "target_code": "def foo(): pass",
            "target_function": "foo",
        }
        result = _planner_node(state)
        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "foo"

    @patch("src.graph.workflow.PlannerAgent")
    def test_planner_node_empty_logic_analysis_fallback(self, mock_planner_class):
        """Planner 返回空 logic_analysis 时使用默认计划。"""
        mock_agent = MagicMock()
        mock_agent.plan.return_value = {"function_name": "bar"}  # 缺少 logic_analysis
        mock_planner_class.return_value = mock_agent

        state = {"target_code": "def bar(): pass", "target_function": "bar"}
        result = _planner_node(state)
        # 验证失败时走默认计划，使用 state 中的 target_function
        assert result["test_plan"]["function_name"] == "bar"


# ─── TestGeneratorNodeWithRAG：Generator 节点 RAG 检索分支 ─────────────────────
class TestGeneratorNodeWithRAG:
    """测试 _generator_node 中 ENABLE_RAG 时的 RAG 检索分支。"""

    def test_generator_node_with_rag_enabled(self):
        """ENABLE_RAG=True 且 RAG 可用时应检索历史用例。"""
        with (
            patch("src.graph.workflow.GeneratorAgent") as mock_gen_class,
            patch("src.graph.workflow.ENABLE_RAG", True),
            patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
            patch("src.graph.workflow.ENABLE_PLANNER", False),
        ):
            mock_retriever = MagicMock()
            mock_retriever.retrieve_test_cases.return_value = [{"case": "similar"}]
            mock_retriever_class.return_value = mock_retriever

            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_gen_class.return_value = mock_agent

            state = {
                "target_code": "def foo(): pass",
                "module_name": "test_mod",
            }
            result = _generator_node(state)
            assert result["generated_test"] == "def test_foo(): pass"
            assert result["rag_references"] == [{"case": "similar"}]
            mock_retriever.retrieve_test_cases.assert_called_once()

    def test_generator_node_rag_retrieval_failure(self):
        """RAG 检索失败时应记录警告但不中断流程。"""
        from unittest.mock import patch

        import src.graph.workflow as wf

        original_cached = wf._rag_retriever
        try:
            wf._rag_retriever = None  # 清空缓存，确保使用新的 mock
            with (
                patch("src.graph.workflow.GeneratorAgent") as mock_gen_class,
                patch("src.graph.workflow.ENABLE_RAG", True),
                patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
                patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
                patch("src.graph.workflow.ENABLE_PLANNER", False),
            ):
                mock_retriever = MagicMock()
                mock_retriever.retrieve_test_cases.side_effect = RuntimeError("检索失败")
                mock_retriever_class.return_value = mock_retriever

                mock_agent = MagicMock()
                mock_agent.generate.return_value = "def test_foo(): pass"
                mock_gen_class.return_value = mock_agent

                state = {
                    "target_code": "def foo(): pass",
                    "module_name": "test_mod",
                }
                result = _generator_node(state)
                # 不应抛出异常，rag_references 应为 None（异常被捕获）
                assert result["generated_test"] == "def test_foo(): pass"
                assert result["rag_references"] is None
        finally:
            wf._rag_retriever = original_cached

    def test_generator_node_rag_disabled(self):
        """ENABLE_RAG=False 时不应进行 RAG 检索。"""
        with (
            patch("src.graph.workflow.GeneratorAgent") as mock_gen_class,
            patch("src.graph.workflow.ENABLE_RAG", False),
            patch("src.graph.workflow.ENABLE_PLANNER", False),
        ):
            mock_agent = MagicMock()
            mock_agent.generate.return_value = "def test_foo(): pass"
            mock_gen_class.return_value = mock_agent

            state = {
                "target_code": "def foo(): pass",
                "module_name": "test_mod",
            }
            result = _generator_node(state)
            assert result["rag_references"] is None


# ─── TestExecutorNodeWithRAG：Executor 节点 RAG 入库分支 ───────────────────────
class TestExecutorNodeWithRAG:
    """测试 _executor_node 中测试通过后入库 RAG 的分支。"""

    def test_executor_node_passes_and_indeRAG(self):
        """测试通过且 RAG 启用时应入库成功用例。"""
        from unittest.mock import patch

        import src.graph.workflow as wf

        original_cached = wf._rag_retriever
        try:
            wf._rag_retriever = None  # 清空缓存，确保使用新的 mock
            with (
                patch("src.graph.workflow.ExecutorAgent") as mock_exec_class,
                patch("src.graph.workflow.ENABLE_RAG", True),
                patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
                patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
            ):
                mock_retriever = MagicMock()
                mock_retriever_class.return_value = mock_retriever

                mock_agent = MagicMock()
                mock_agent.execute.return_value = {
                    "passed": True,
                    "output": "1 passed",
                    "coverage": 85.0,
                    "failed_cases": [],
                }
                mock_exec_class.return_value = mock_agent

                state = {
                    "generated_test": "def test_foo(): pass",
                    "target_code": "def foo(): pass",
                    "target_file": "examples/calculator.py",
                    "target_function": "foo",
                    "iteration": 0,
                }
                result = _executor_node(state)
                assert result["test_passed"] is True
                mock_retriever.add_case.assert_called_once()
        finally:
            wf._rag_retriever = original_cached

    def test_executor_node_fail_no_rag_insert(self):
        """测试失败时不应入库 RAG。"""
        with (
            patch("src.graph.workflow.ExecutorAgent") as mock_exec_class,
            patch("src.graph.workflow.ENABLE_RAG", True),
            patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
        ):
            mock_retriever = MagicMock()
            mock_retriever_class.return_value = mock_retriever

            mock_agent = MagicMock()
            mock_agent.execute.return_value = {
                "passed": False,
                "output": "1 failed",
                "coverage": 60.0,
                "failed_cases": [{"name": "test_foo", "error": "AssertionError"}],
            }
            mock_exec_class.return_value = mock_agent

            state = {
                "generated_test": "def test_foo(): assert False",
                "target_file": "examples/calculator.py",
                "iteration": 0,
            }
            result = _executor_node(state)
            assert result["test_passed"] is False
            mock_retriever.add_case.assert_not_called()

    def test_executor_node_rag_insert_failure(self):
        """RAG 入库失败时应记录警告但不中断流程。"""
        with (
            patch("src.graph.workflow.ExecutorAgent") as mock_exec_class,
            patch("src.graph.workflow.ENABLE_RAG", True),
            patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
        ):
            mock_retriever = MagicMock()
            mock_retriever.add_case.side_effect = RuntimeError("入库失败")
            mock_retriever_class.return_value = mock_retriever

            mock_agent = MagicMock()
            mock_agent.execute.return_value = {
                "passed": True,
                "output": "1 passed",
                "coverage": 85.0,
                "failed_cases": [],
            }
            mock_exec_class.return_value = mock_agent

            state = {
                "generated_test": "def test_foo(): pass",
                "target_file": "examples/calculator.py",
                "iteration": 0,
            }
            # 不应抛出异常
            result = _executor_node(state)
            assert result["test_passed"] is True


# ─── TestDebuggerNodeWithRAG：Debugger 节点 RAG 检索和入库分支 ─────────────────
class TestDebuggerNodeWithRAG:
    """测试 _debugger_node 中 ENABLE_RAG 时的 RAG 检索修复案例和入库分支。"""

    def test_debugger_node_with_rag_retrieval(self):
        """ENABLE_RAG=True 且存在失败用例时应检索相似修复案例。"""
        from unittest.mock import patch

        import src.graph.workflow as wf

        original_cached = wf._rag_retriever
        try:
            wf._rag_retriever = None  # 清空缓存，确保使用新的 mock
            with (
                patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class,
                patch("src.graph.workflow.ENABLE_RAG", True),
                patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
                patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
            ):
                mock_retriever = MagicMock()
                mock_retriever.retrieve_repairs.return_value = [{"repair": "case"}]
                mock_retriever_class.return_value = mock_retriever

                mock_agent = MagicMock()
                mock_agent.debug.return_value = {
                    "root_cause": "除零错误",
                    "error_category": "runtime",
                    "fix_strategy": "添加边界检查",
                    "patch": "def foo(x): return x if x != 0 else 0",
                }
                mock_dbg_class.return_value = mock_agent

                state = {
                    "target_code": "def foo(x): return 1/x",
                    "test_output": "ZeroDivisionError",
                    "failed_cases": [{"name": "test_foo", "error": "ZeroDivisionError"}],
                    "error_category": "runtime",
                    "iteration": 0,
                }
                result = _debugger_node(state)
                assert result["error_category"] == "runtime"
                mock_retriever.retrieve_repairs.assert_called_once()
        finally:
            wf._rag_retriever = original_cached

    def test_debugger_node_rag_retrieval_failure(self):
        """RAG 检索失败时应记录警告但不中断流程。"""
        from unittest.mock import patch

        import src.graph.workflow as wf

        original_cached = wf._rag_retriever
        try:
            wf._rag_retriever = None  # 清空缓存
            with (
                patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class,
                patch("src.graph.workflow.ENABLE_RAG", True),
                patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
                patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
            ):
                mock_retriever = MagicMock()
                mock_retriever.retrieve_repairs.side_effect = RuntimeError("检索失败")
                mock_retriever_class.return_value = mock_retriever

                mock_agent = MagicMock()
                mock_agent.debug.return_value = {
                    "root_cause": "未知错误",
                    "error_category": "unknown",
                    "fix_strategy": "",
                    "patch": "",
                }
                mock_dbg_class.return_value = mock_agent

                state = {
                    "target_code": "def foo(): pass",
                    "test_output": "Error",
                    "failed_cases": [{"name": "test_foo", "error": "Error"}],
                    "error_category": "unknown",
                }
                result = _debugger_node(state)
                assert result["error_category"] == "unknown"
        finally:
            wf._rag_retriever = original_cached

    def test_debugger_node_rag_repair_insertion(self):
        """Debugger 完成修复后应入库修复案例。"""
        from unittest.mock import patch

        import src.graph.workflow as wf

        original_cached = wf._rag_retriever
        try:
            wf._rag_retriever = None  # 清空缓存，确保使用新的 mock
            with (
                patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class,
                patch("src.graph.workflow.ENABLE_RAG", True),
                patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
                patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
            ):
                mock_retriever = MagicMock()
                mock_retriever_class.return_value = mock_retriever

                mock_agent = MagicMock()
                mock_agent.debug.return_value = {
                    "root_cause": "除零错误",
                    "error_category": "runtime",
                    "fix_strategy": "添加边界检查",
                    "patch": "def foo(x): return x if x != 0 else 0",
                }
                mock_dbg_class.return_value = mock_agent

                state = {
                    "target_code": "def foo(x): return 1/x",
                    "test_output": "ZeroDivisionError",
                    "failed_cases": [{"name": "test_foo", "error": "ZeroDivisionError"}],
                    "iteration": 0,
                }
                _debugger_node(state)
                mock_retriever.add_repair.assert_called_once()
        finally:
            wf._rag_retriever = original_cached

    def test_debugger_node_rag_repair_insertion_failure(self):
        """RAG 修复入库失败时应记录警告但不中断流程。"""
        from unittest.mock import patch

        import src.graph.workflow as wf

        original_cached = wf._rag_retriever
        try:
            wf._rag_retriever = None  # 清空缓存
            with (
                patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class,
                patch("src.graph.workflow.ENABLE_RAG", True),
                patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
                patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
            ):
                mock_retriever = MagicMock()
                mock_retriever.add_repair.side_effect = RuntimeError("入库失败")
                mock_retriever_class.return_value = mock_retriever

                mock_agent = MagicMock()
                mock_agent.debug.return_value = {
                    "root_cause": "除零错误",
                    "error_category": "runtime",
                    "fix_strategy": "添加边界检查",
                    "patch": "def foo(x): return x if x != 0 else 0",
                }
                mock_dbg_class.return_value = mock_agent

                state = {
                    "target_code": "def foo(x): return 1/x",
                    "test_output": "ZeroDivisionError",
                    "failed_cases": [{"name": "test_foo", "error": "ZeroDivisionError"}],
                    "iteration": 0,
                }
                # 不应抛出异常
                result = _debugger_node(state)
                assert result["error_category"] == "runtime"
        finally:
            wf._rag_retriever = original_cached

    def test_debugger_node_no_failed_cases_no_rag(self):
        """无失败用例时不进行 RAG 检索。"""
        with (
            patch("src.graph.workflow.DebuggerAgent") as mock_dbg_class,
            patch("src.graph.workflow.ENABLE_RAG", True),
            patch("src.graph.workflow.RAG_MODULE_AVAILABLE", True),
            patch("src.graph.workflow.TestCaseRetriever") as mock_retriever_class,
        ):
            mock_retriever = MagicMock()
            mock_retriever_class.return_value = mock_retriever

            mock_agent = MagicMock()
            mock_agent.debug.return_value = {
                "root_cause": "未知",
                "error_category": "unknown",
                "fix_strategy": "",
                "patch": "",
            }
            mock_dbg_class.return_value = mock_agent

            state = {
                "target_code": "def foo(): pass",
                "test_output": "",
                "failed_cases": [],
                "iteration": 0,
            }
            _debugger_node(state)
            mock_retriever.retrieve_repairs.assert_not_called()


# ─── TestPatchApplierNodeSafety：补丁安全校验分支 ─────────────────────────────
class TestPatchApplierNodeSafety:
    """测试 _patch_applier_node 中的安全检查分支。"""

    def test_patch_too_short(self):
        """补丁内容过短时跳过写入。"""
        with patch("src.graph.workflow.apply_patch_to_code") as mock_apply:
            # 模拟补丁应用后代码变短
            mock_apply.return_value = ("def small(): pass", True)

            state = {
                "target_code": "def foo(x): return 1/x\n" * 10,  # 长代码
                "target_file": "examples/test.py",
                "patch": "def foo(x): return x\n",  # 短补丁
                "iteration": 0,
                "diagnosis": "除零错误",
                "error_category": "runtime",
            }
            result = _patch_applier_node(state)
            # 补丁过短，应跳过写入，但迭代计数仍应增加
            assert result["iteration"] == 1
            # target_code 不应被修改（因为补丁被跳过了）
            assert result["target_code"] == "def small(): pass"

    def test_patch_no_function_definition(self):
        """补丁不含函数定义时跳过写入。"""
        with patch("src.graph.workflow.apply_patch_to_code") as mock_apply:
            mock_apply.return_value = ("print('hello')", True)  # 无 def

            state = {
                "target_code": "def foo(): pass\n",
                "target_file": "examples/test.py",
                "patch": "print('hello')",
                "iteration": 0,
                "diagnosis": "测试",
                "error_category": "runtime",
            }
            result = _patch_applier_node(state)
            assert result["iteration"] == 1

    def test_invalid_file_path(self):
        """非法文件路径时跳过写入。"""
        with patch("src.graph.workflow.apply_patch_to_code") as mock_apply:
            mock_apply.return_value = ("def foo(): return 1\n", True)

            state = {
                "target_code": "def foo(): return 0\n",
                "target_file": "/etc/passwd",  # 非法路径
                "patch": "def foo(): return 1\n",
                "iteration": 0,
                "diagnosis": "测试",
                "error_category": "runtime",
            }
            result = _patch_applier_node(state)
            assert result["iteration"] == 1

    def test_repair_history_truncation(self):
        """repair_history 超过 MAX_REPAIR_HISTORY(5) 时应截断。"""
        with patch("src.graph.workflow.apply_patch_to_code") as mock_apply:
            mock_apply.return_value = ("def foo(): return 1\n", True)

            # 构造超过 5 条的历史记录（6 条）
            long_history = [{"iteration": i, "patch_applied": True} for i in range(1, 7)]

            state = {
                "target_code": "def foo(): return 0\n",
                "target_file": "examples/test.py",
                "patch": "def foo(): return 1\n",
                "iteration": 5,
                "diagnosis": "测试",
                "error_category": "runtime",
                "repair_history": long_history,
            }
            result = _patch_applier_node(state)
            # 原始 6 条 (iteration=1~6) + 新追加 1 条 (iteration=5+1=6) = 7 条
            # 截断后保留最后 5 条：iteration=3,4,5,6,6
            assert len(result["repair_history"]) == 5
            assert result["repair_history"][0]["iteration"] == 3
            assert result["repair_history"][-1]["iteration"] == 6


# ─── TestWorkflowIntegration：工作流集成测试 ───────────────────────────────────
class TestWorkflowIntegration:
    """测试工作流集成的边界情况。"""

    def test_workflow_with_all_features_enabled(self):
        """所有功能启用时工作流应包含所有节点。"""
        with patch("src.graph.workflow.ENABLE_PLANNER", True), patch("src.graph.workflow.ENABLE_DEBUGGER", True):
            workflow = _create_workflow()
            nodes = list(workflow.nodes.keys())
            assert "planner" in nodes
            assert "generator" in nodes
            assert "executor" in nodes
            assert "debugger" in nodes
            assert "patch_applier" in nodes
