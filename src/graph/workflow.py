"""
LangGraph 工作流编排模块：定义智能体节点和执行路由逻辑。
集成 RAG 检索增强和分层错误修复。
工作流程：Planner → Generator → Executor → (Debugger → PatchApplier) × N → END
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from src.graph.state import AITesterState
from src.agents.planner import PlannerAgent
from src.agents.generator import GeneratorAgent
from src.agents.executor import ExecutorAgent
from src.agents.debugger import DebuggerAgent
from src.tools.patch_applier import apply_patch_to_code
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD

# 模块级 logger，用于记录工作流执行过程
logger = logging.getLogger(__name__)

# 可选导入 RAG 检索器（未安装 chromadb 时 gracefully degrade，不影响主流程）
try:
    from src.rag.retriever import TestCaseRetriever
    RAG_ENABLED = True
except ImportError:
    RAG_ENABLED = False
    TestCaseRetriever = None
    logger.info("RAG 模块未就绪（chromadb 未安装），将跳过检索增强")


def _create_workflow() -> StateGraph:
    """
    构建多智能体工作流图。
    使用 LangGraph 的 StateGraph API 定义有向图，节点为各智能体，边为状态转移。

    Returns:
        已注册的 StateGraph 实例（尚未编译，需调用 .compile() 后才能运行）。
    """
    workflow = StateGraph(AITesterState)

    # 注册四个核心节点：planner、generator、executor、debugger、patch_applier
    workflow.add_node("planner", _planner_node)
    workflow.add_node("generator", _generator_node)
    workflow.add_node("executor", _executor_node)
    workflow.add_node("debugger", _debugger_node)
    workflow.add_node("patch_applier", _patch_applier_node)

    # 设置入口：从 planner 开始
    workflow.set_entry_point("planner")

    # 定义边：planner → generator → executor
    workflow.add_edge("planner", "generator")
    workflow.add_edge("generator", "executor")

    # 条件路由：executor 根据测试结果决定进入 debugger 还是结束
    workflow.add_conditional_edges(
        "executor",
        _should_debug,  # 路由函数，返回 "debug" 或 "done"
        {
            "debug": "debugger",   # 需要修复时进入 debugger
            "done": END,           # 测试通过或达到最大迭代时结束
        },
    )
    # debugger 修复后应用补丁，然后重新执行测试
    workflow.add_edge("debugger", "patch_applier")
    workflow.add_edge("patch_applier", "executor")

    return workflow


def _should_debug(state: AITesterState) -> str:
    """
    判断是否进入调试修复环节的路由函数。

    路由条件：
    - 测试已通过 → 结束流程（"done"）
    - 已达到最大迭代次数 → 结束流程（"done"）
    - 否则 → 进入 debugger（"debug"）

    Args:
        state: 当前工作流状态。

    Returns:
        "debug" 表示进入调试，"done" 表示流程结束。
    """
    # 测试已通过，无需修复
    if state.get("test_passed") is True:
        return "done"
    # 已达到最大迭代次数，停止修复
    if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS):
        return "done"
    # 需要进入 debugger 进行修复
    return "debug"


def _planner_node(state: AITesterState) -> Dict[str, Any]:
    """
    PlannerAgent 节点：生成逻辑驱动的结构化测试计划。

    负责分析被测代码的输入域、输出域、前置/后置条件和边界情况，
    输出包含 logic_analysis 和 test_cases 的结构化计划。

    Args:
        state: 当前状态，包含 target_code 和 target_function。

    Returns:
        更新后的状态字典，包含 test_plan 字段。
    """
    agent = PlannerAgent()
    # 调用 Planner 生成测试计划（含逻辑分析）
    test_plan = agent.plan(state["target_code"], state.get("target_function"))
    logger.info("Planner 完成规划，函数=%s", test_plan.get("function_name", "unknown"))
    return {"test_plan": test_plan}


def _generator_node(state: AITesterState) -> Dict[str, Any]:
    """
    GeneratorAgent 节点：根据测试计划生成 pytest 测试代码。
    若 RAG 可用，先检索相似历史测试用例作为参考。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 generated_test 和 rag_references。
    """
    agent = GeneratorAgent()

    # RAG 检索：查找相似历史测试用例
    rag_refs: Optional[list] = None
    if RAG_ENABLED and TestCaseRetriever is not None:
        try:
            retriever = TestCaseRetriever()
            rag_refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
            logger.info("RAG 检索到 %d 个相似测试用例", len(rag_refs) if rag_refs else 0)
        except Exception as e:
            logger.warning("RAG 检索失败，跳过增强: %s", e)

    # 调用 Generator 生成测试代码
    generated_test = agent.generate(
        state["test_plan"],
        state["target_code"],
        rag_references=rag_refs,
    )
    logger.info("Generator 完成测试代码生成，长度=%d", len(generated_test))
    return {
        "generated_test": generated_test,
        "rag_references": rag_refs,
    }


def _executor_node(state: AITesterState) -> Dict[str, Any]:
    """
    ExecutorAgent 节点：执行测试并记录结果。
    测试通过后自动入库，供后续 RAG 检索使用。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 test_passed, test_output, coverage_report, failed_cases。
    """
    agent = ExecutorAgent(
        timeout=int(os.getenv("EXECUTION_TIMEOUT", "30")),
        use_docker=False,  # 默认本地执行，Docker 模式需额外配置
    )
    # 执行测试
    result = agent.execute(
        test_code=state["generated_test"],
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )
    status = "PASS" if result["passed"] else "FAIL"
    logger.info(
        "Executor 完成第 %d 轮测试：%s，覆盖率=%.1f%%，失败用例数=%d",
        state.get("iteration", 0) + 1,
        status,
        result["coverage"],
        len(result["failed_cases"]),
    )

    # 测试通过后入库，供后续 RAG 检索使用
    # 这样随着实验进行，RAG 库会积累更多高质量测试案例
    if result["passed"] and RAG_ENABLED and TestCaseRetriever is not None:
        try:
            retriever = TestCaseRetriever()
            retriever.add_case(
                code=state["target_code"],
                test_code=state["generated_test"],
                passed=True,
                metadata={"function": state.get("target_function"), "coverage": result["coverage"]},
            )
            logger.debug("成功测试用例已入库 RAG")
        except Exception as e:
            logger.warning("RAG 入库失败: %s", e)

    return {
        "test_passed": result["passed"],
        "test_output": result["output"],
        "coverage_report": result["coverage"],
        "failed_cases": result["failed_cases"],
    }


def _debugger_node(state: AITesterState) -> Dict[str, Any]:
    """
    DebuggerAgent 节点：分析失败原因并生成分层修复补丁。
    若 RAG 可用，检索相似历史修复案例作为参考。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 diagnosis, error_category, patch。
    """
    agent = DebuggerAgent()

    # RAG 检索：查找相似历史修复案例
    rag_refs: Optional[list] = None
    if RAG_ENABLED and TestCaseRetriever is not None and state.get("failed_cases"):
        try:
            # 使用已分类的错误类型（若有）或默认 UNKNOWN
            error_cat = state.get("error_category", "unknown")
            retriever = TestCaseRetriever()
            rag_refs = retriever.retrieve_repairs(
                error_category=error_cat,
                target_code=state["target_code"],
                top_k=2,
            )
            logger.info("RAG 检索到 %d 个相似修复案例", len(rag_refs) if rag_refs else 0)
        except Exception as e:
            logger.warning("RAG 检索失败，跳过增强: %s", e)

    # 调用 Debugger 分析失败原因并生成修复补丁
    result = agent.debug(
        target_code=state["target_code"],
        test_output=state.get("test_output", ""),
        failed_cases=state.get("failed_cases", []) or [],
        rag_references=rag_refs,
    )
    logger.info(
        "Debugger 完成第 %d 轮修复：类别=%s，根因=%s",
        state.get("iteration", 0) + 1,
        result.get("error_category", "unknown"),
        result.get("root_cause", "")[:80],
    )

    # 修复案例入库（无论是否成功，都记录以供后续检索）
    # 这有助于 Debugger 在遇到类似错误时参考历史修复方案
    if RAG_ENABLED and TestCaseRetriever is not None:
        try:
            retriever = TestCaseRetriever()
            retriever.add_repair(
                original_code=state["target_code"],
                patch=result.get("patch", ""),
                error_category=result.get("error_category", "unknown"),
            )
            logger.debug("修复案例已入库 RAG")
        except Exception as e:
            logger.warning("RAG 修复入库失败: %s", e)

    return {
        "diagnosis": result["root_cause"],
        "error_category": result.get("error_category", "unknown"),
        "patch": result["patch"],
    }


def _patch_applier_node(state: AITesterState) -> Dict[str, Any]:
    """
    补丁应用节点：将 Debugger 生成的补丁应用到被测代码，并写回文件。
    应用后更新 iteration 计数器，供下次循环使用。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含更新后的 target_code 和修复历史。
    """
    # 调用补丁应用工具
    new_code, applied = apply_patch_to_code(
        original_code=state["target_code"],
        patch=state.get("patch", ""),
    )

    # 写回目标文件，确保后续测试使用修复后的代码
    # 注意：此操作会修改原始文件，若需保留原文件应使用备份
    if applied and new_code != state["target_code"]:
        with open(state["target_file"], "w", encoding="utf-8") as f:
            f.write(new_code)
        logger.info("补丁已应用到文件: %s", state["target_file"])

    # 记录修复历史，便于后续分析和实验统计
    history = state.get("repair_history", []) or []
    history.append({
        "iteration": state.get("iteration", 0) + 1,
        "diagnosis": state.get("diagnosis", ""),
        "error_category": state.get("error_category", "unknown"),
        "patch_applied": applied,
    })
    return {
        "target_code": new_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
    }


def build_workflow() -> Any:
    """
    编译工作流图并返回可执行的 graph 对象。
    每次调用都创建新的 graph 实例，避免状态污染。

    Returns:
        编译后的 LangGraph StateGraph 对象。
    """
    workflow = _create_workflow()
    return workflow.compile()
