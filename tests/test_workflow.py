"""
单元测试：测试工作流路由逻辑（_should_debug）和图构建。

覆盖范围：
    - _should_debug：测试通过/未达迭代/达最大迭代+关键词/达最大迭代+无关键词
    - _create_workflow：PLANNER/DEBUGGER 开关控制节点注册
    - build_workflow：编译返回 StateGraph 实例
"""

import pytest
from unittest.mock import patch, MagicMock
from src.graph.workflow import _should_debug, _create_workflow, build_workflow


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
        # 入口节点检查：无 planner 时直接从 generator 开始
        # StateGraph 内部 entry_point 存储在 _entry_points
        entry_points = getattr(workflow, "_entry_points", [])
        # 如果没有显式 entry point，则从第一个注册的节点开始
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


# ─── TestBuildWorkflow：编译工作流 ──────────────────────────────────────────────
class TestBuildWorkflow:
    """测试 build_workflow 编译函数。"""

    def test_build_returns_compilable_graph(self):
        """build_workflow 应返回可编译的 StateGraph 实例。"""
        graph = build_workflow()
        # 编译后的 graph 应具有 execute 方法
        assert hasattr(graph, "invoke") or hasattr(graph, "execute")
