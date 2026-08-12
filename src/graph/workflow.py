"""
LangGraph 工作流编排：定义智能体节点和执行路由逻辑。
"""

from __future__ import annotations

import os
from typing import Any, Dict

from langgraph.graph import StateGraph, END

from src.graph.state import AITesterState
from src.agents.planner import PlannerAgent
from src.agents.generator import GeneratorAgent
from src.agents.executor import ExecutorAgent
from src.agents.debugger import DebuggerAgent
from src.tools.patch_applier import apply_patch_to_code
from config import MAX_ITERATIONS, COVERAGE_THRESHOLD


def _create_workflow() -> StateGraph:
    """
    构建多智能体工作流图。

    Returns:
        已注册的 StateGraph 实例（尚未编译）。
    """
    workflow = StateGraph(AITesterState)

    # 注册节点
    workflow.add_node("planner", _planner_node)
    workflow.add_node("generator", _generator_node)
    workflow.add_node("executor", _executor_node)
    workflow.add_node("debugger", _debugger_node)
    workflow.add_node("patch_applier", _patch_applier_node)

    # 设置入口
    workflow.set_entry_point("planner")

    # 路由逻辑
    workflow.add_edge("planner", "generator")
    workflow.add_edge("generator", "executor")
    workflow.add_conditional_edges(
        "executor",
        _should_debug,
        {
            "debug": "debugger",
            "done": END,
        },
    )
    workflow.add_edge("debugger", "patch_applier")
    workflow.add_edge("patch_applier", "executor")

    return workflow


def _should_debug(state: AITesterState) -> str:
    """
    判断是否进入调试修复环节。

    路由条件：
    - 测试未通过
    - 且未达到最大迭代次数

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


def _planner_node(state: AITesterState) -> Dict[str, Any]:
    """
    PlannerAgent 节点：生成测试计划。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典（仅包含 test_plan 字段）。
    """
    agent = PlannerAgent()
    test_plan = agent.plan(state["target_code"], state.get("target_function"))
    return {"test_plan": test_plan}


def _generator_node(state: AITesterState) -> Dict[str, Any]:
    """
    GeneratorAgent 节点：生成 pytest 测试代码。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典（仅包含 generated_test 字段）。
    """
    agent = GeneratorAgent()
    generated_test = agent.generate(state["test_plan"], state["target_code"])
    return {"generated_test": generated_test}


def _executor_node(state: AITesterState) -> Dict[str, Any]:
    """
    ExecutorAgent 节点：执行测试并记录结果。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典（包含 test_passed, test_output, coverage_report, failed_cases）。
    """
    agent = ExecutorAgent(
        timeout=30,
        use_docker=False,  # 默认本地执行
    )
    result = agent.execute(
        test_code=state["generated_test"],
        target_file=state["target_file"],
        target_function=state.get("target_function"),
    )
    return {
        "test_passed": result["passed"],
        "test_output": result["output"],
        "coverage_report": result["coverage"],
        "failed_cases": result["failed_cases"],
    }


def _debugger_node(state: AITesterState) -> Dict[str, Any]:
    """
    DebuggerAgent 节点：分析失败原因并生成补丁。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典（包含 diagnosis, patch）。
    """
    agent = DebuggerAgent()
    result = agent.debug(
        target_code=state["target_code"],
        test_output=state.get("test_output", ""),
        failed_cases=state.get("failed_cases", []) or [],
    )
    return {
        "diagnosis": result["root_cause"],
        "patch": result["patch"],
    }


def _patch_applier_node(state: AITesterState) -> Dict[str, Any]:
    """
    补丁应用节点：将 Debugger 生成的补丁应用到被测代码，并写回文件。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典（包含更新后的 target_code 和修复历史）。
    """
    new_code, applied = apply_patch_to_code(
        original_code=state["target_code"],
        patch=state.get("patch", ""),
    )
    
    # 写回目标文件，确保后续测试使用修复后的代码
    if applied and new_code != state["target_code"]:
        with open(state["target_file"], "w", encoding="utf-8") as f:
            f.write(new_code)
        print(f"补丁已应用到文件: {state['target_file']}")

    # 记录修复历史
    history = state.get("repair_history", []) or []
    history.append({
        "iteration": state.get("iteration", 0) + 1,
        "diagnosis": state.get("diagnosis", ""),
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

    Returns:
        编译后的 LangGraph StateGraph 对象。
    """
    workflow = _create_workflow()
    return workflow.compile()
