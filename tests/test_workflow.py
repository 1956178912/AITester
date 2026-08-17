"""
单元测试：测试工作流路由逻辑（_should_debug）和图构建。

覆盖范围：
    - _should_debug：测试通过/未达迭代/达最大迭代+关键词/达最大迭代+无关键词
    - _create_workflow：PLANNER/DEBUGGER 开关控制节点注册
    - build_workflow：编译返回 StateGraph 实例
    - 节点函数：_planner_node, _generator_node, _executor_node, _debugger_node, _patch_applier_node
"""

import pytest
from unittest.mock import patch, MagicMock
from src.graph.workflow import (
    _should_debug,
    _should_skip_debugger,
    _create_workflow,
    build_workflow,
    get_workflow_stats,
    _planner_node,
    _generator_node,
    _executor_node,
    _debugger_node,
    _patch_applier_node,
    _validate_planner_output,
    _get_default_test_plan,
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
            "logic_analysis": {"input_domain": "", "output_domain": "", "preconditions": [], "postconditions": [], "edge_cases": []},
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
                result = _generator_node(state)
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
        from unittest.mock import patch
        import json
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
            "logic_analysis": {"input_domain": "", "output_domain": "", "preconditions": [], "postconditions": [], "edge_cases": []}
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
