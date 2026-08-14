"""
LangGraph 工作流编排模块：定义智能体节点和执行路由逻辑。
集成 RAG 检索增强和分层错误修复。

工作流程（完整版）：
    Planner → Generator → Executor → (Debugger → PatchApplier) × N → END

工作流程（消融模式 - 无 Planner）：
    Generator → Executor → (Debugger → PatchApplier) × N → END

工作流程（消融模式 - 无 Debugger）：
    Planner → Generator → Executor → END

工作流程（消融模式 - 无 Planner/Debugger）：
    Generator → Executor → END  （纯 LLM 基线）
"""

from __future__ import annotations

import json
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
from config import (
    MAX_ITERATIONS,
    COVERAGE_THRESHOLD,
    ENABLE_PLANNER,
    ENABLE_RAG,
    ENABLE_DEBUGGER,
)

# 模块级 logger，用于记录工作流执行过程
logger = logging.getLogger(__name__)

# 可选导入 RAG 检索器（未安装 chromadb 时 gracefully degrade，不影响主流程）
try:
    from src.rag.retriever import TestCaseRetriever
    RAG_MODULE_AVAILABLE = True
except ImportError:
    RAG_MODULE_AVAILABLE = False
    TestCaseRetriever = None
    logger.info("RAG 模块未就绪（chromadb 未安装），将跳过检索增强")


def _create_workflow() -> StateGraph:
    """
    构建多智能体工作流图。

    根据 config.py 中的消融开关动态选择启用的节点：
    - ENABLE_PLANNER=True  → 包含 Planner 节点
    - ENABLE_DEBUGGER=True → 包含 Debugger + PatchApplier 循环
    - ENABLE_RAG=True      → Generator/Debugger 使用 RAG 增强

    Returns:
        已注册的 StateGraph 实例（尚未编译，需调用 .compile() 后才能运行）。
    """
    workflow = StateGraph(AITesterState)

    # ── 始终注册的节点 ──────────────────────────────────────────────────────
    # Generator 和 Executor 是必选项
    workflow.add_node("generator", _generator_node)
    workflow.add_node("executor", _executor_node)

    # ── 固定边：Generator → Executor ─────────────────────────────────────────
    workflow.add_edge("generator", "executor")

    # ── 条件注册：Planner（消融开关控制）────────────────────────────────────
    if ENABLE_PLANNER:
        workflow.add_node("planner", _planner_node)
        # 入口：从 planner 开始
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "generator")
    else:
        # 无 Planner 模式：直接从 generator 开始
        workflow.set_entry_point("generator")

    # ── 条件注册：Debugger + PatchApplier（消融开关控制）────────────────────
    if ENABLE_DEBUGGER:
        workflow.add_node("debugger", _debugger_node)
        workflow.add_node("patch_applier", _patch_applier_node)
        # Executor → 条件路由 → debugger 或 END
        # Executor → Debugger 条件路由：根据测试是否通过/迭代次数决定是否进入修复循环
        workflow.add_conditional_edges(
            "executor",
            _should_debug,
            {
                "debug": "debugger",   # 需要修复时进入 debugger
                "done": END,           # 测试通过或达到最大迭代时结束
            },
        )
        workflow.add_edge("debugger", "patch_applier")
        workflow.add_edge("patch_applier", "executor")
    else:
        # 无 Debugger 模式：Executor 直接到 END
        workflow.add_edge("executor", END)

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
    if state.get("test_passed") is True:
        return "done"
    if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS):
        return "done"
    return "debug"


# ─── 节点函数定义 ────────────────────────────────────────────────────────────


def _planner_node(state: AITesterState) -> Dict[str, Any]:
    """
    PlannerAgent 节点：生成逻辑驱动的结构化测试计划。

    负责分析被测代码的输入域、输出域、前置/后置条件和边界情况，
    输出包含 logic_analysis 和 test_cases 的结构化计划。
    若 LLM 返回格式不良的 JSON，使用默认计划兜底。

    Args:
        state: 当前状态，包含 target_code 和 target_function。

    Returns:
        更新后的状态字典，包含 test_plan 字段。
    """
    agent = PlannerAgent()
    try:
        test_plan = agent.plan(state["target_code"], state.get("target_function"))
        logger.info("Planner 完成规划，函数=%s", test_plan.get("function_name", "unknown"))
    except (json.JSONDecodeError, RuntimeError) as e:
        logger.warning("Planner JSON 解析失败，使用默认计划: %s", e)
        test_plan = {
            "function_name": state.get("target_function", "unknown"),
            "description": "自动生成的默认测试计划",
            "logic_analysis": {
                "input_domain": "未知",
                "output_domain": "未知",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            },
            "test_cases": [],
        }
    return {"test_plan": test_plan}


def _generator_node(state: AITesterState) -> Dict[str, Any]:
    """
    GeneratorAgent 节点：根据测试计划生成 pytest 测试代码。
    若 RAG 可用且已启用，先检索相似历史测试用例作为参考。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 generated_test 和 rag_references。
    """
    agent = GeneratorAgent()

    rag_refs: Optional[list] = None
    if ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
        try:
            retriever = TestCaseRetriever()
            rag_refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
            logger.info("RAG 检索到 %d 个相似测试用例", len(rag_refs) if rag_refs else 0)
        except Exception as e:
            logger.warning("RAG 检索失败，跳过增强: %s", e)

    generated_test = agent.generate(
        state["test_plan"] if ENABLE_PLANNER else None,
        state["target_code"],
        module_name=state.get("module_name", ""),
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
    测试通过后自动入库（若 RAG 可用且已启用），供后续检索使用。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 test_passed, test_output, coverage_report, failed_cases。
    """
    agent = ExecutorAgent(
        timeout=int(os.getenv("EXECUTION_TIMEOUT", "30")),
        use_docker=False,
    )
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

    if result["passed"] and ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
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
    若 RAG 可用且已启用，检索相似历史修复案例作为参考。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 diagnosis, error_category, patch。
    """
    agent = DebuggerAgent()

    rag_refs: Optional[list] = None
    if ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None and state.get("failed_cases"):
        try:
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

    if ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
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
    new_code, applied = apply_patch_to_code(
        original_code=state["target_code"],
        patch=state.get("patch", ""),
    )

    if applied and new_code != state["target_code"]:
        with open(state["target_file"], "w", encoding="utf-8") as f:
            f.write(new_code)
        logger.info("补丁已应用到文件: %s", state["target_file"])

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
