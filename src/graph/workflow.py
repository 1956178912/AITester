"""
LangGraph 工作流编排模块：定义多智能体协作的工作流图和执行路由逻辑。

本模块是 AITester 系统的"中枢神经系统"，负责：
1. 根据消融实验开关动态构建有向图（StateGraph）
2. 实现节点间的条件路由（通过测试？达到最大迭代？重新生成？）
3. 协调 Planner → Generator → Executor → Debugger → PatchApplier 的循环修复流程

工作流程（完整版）：
    Planner → Generator → Executor → (Debugger → PatchApplier) × N → END

工作流程（消融模式 - 无 Planner）：
    Generator → Executor → (Debugger → PatchApplier) × N → END

工作流程（消融模式 - 无 Debugger）：
    Planner → Generator → Executor → END

工作流程（消融模式 - 无 Planner/Debugger）：
    Generator → Executor → END  （纯 LLM 基线）

节点函数实现已拆分到 `src/graph/nodes.py`、RAG 检索器单例拆分到
`src/graph/rag.py`、结构化追踪拆分到 `src/graph/tracing.py`
（代码可维护性优化）。本模块保留图构建与路由逻辑，并通过 re-import
保持历史 `from src.graph.workflow import ...` 导入路径不变。

设计原则：
- 各节点函数接收状态字典并返回更新后的字段，保持状态无副作用
- 条件路由函数 _should_debug 实现循环终止逻辑
- 使用 try-except 捕获 LLM 调用异常，确保工作流不因单点故障而崩溃

使用示例：
    from src.graph.workflow import build_workflow
    from src.graph.state import AITesterState

    graph = build_workflow()
    initial_state: AITesterState = {
        "target_code": "def add(a, b): return a + b",
        "target_file": "/path/to/target.py",
        "target_function": "add",
    }
    result = graph.invoke(initial_state)
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, StateGraph

from config import ENABLE_DEBUGGER, ENABLE_PLANNER, ENABLE_RAG, MAX_ITERATIONS
from src.graph.llm_cache import get_cache_stats

# 纯 re-export：保持历史 `from src.graph.workflow import ...` 导入路径不变。
# 这些符号的实现已拆分到 nodes/rag/tracing 模块，workflow 自身不直接使用，
# 仅通过命名空间转发供测试与外部调用方访问。
from src.graph.nodes import (  # noqa: F401
    _cross_file_analyzer_node,
    _debugger_node,
    _executor_node,
    _generator_node,
    _get_default_test_plan,
    _patch_applier_node,
    _planner_node,
    _validate_planner_output,
)
from src.graph.rag import RAG_MODULE_AVAILABLE, TestCaseRetriever, get_rag_retriever  # noqa: F401
from src.graph.state import AITesterState
from src.graph.tracing import _trace_local, _trace_node, end_task_trace, start_task_trace  # noqa: F401
from src.tools.cross_file import cross_file_enabled

# 模块级 logger，用于记录工作流执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)

# 重新生成测试代码的上限：达到最大迭代后，诊断指向"测试生成错误"时路由回
# generator 再生成一次。若无上限，旧的 diagnosis 关键词会反复命中，
# generator↔executor 无限乒乓，最终撞上 LangGraph recursion_limit 崩掉任务并空烧 token。
# 取 1：一次再生成已足够验证"换一版测试"是否解决问题，再多只会浪费。
_MAX_REGENERATIONS = 1


def _create_workflow(planner: bool | None = None, debugger: bool | None = None) -> StateGraph:
    """
    构建多智能体工作流图（有向无环图 + 条件循环）。

    核心设计思路：
    - 使用 LangGraph 的 StateGraph 作为图编排引擎，每个节点是一个 Python 函数
    - 根据 config.py 中的消融开关（或本次构建的显式覆盖）动态选择启用的节点和边
    - Debugger + PatchApplier 构成循环结构，通过 _should_debug 条件路由控制是否继续迭代

    消融开关说明：
    - planner=True（或 config.ENABLE_PLANNER=True）→ 包含 Planner 节点（逻辑驱动思维链）
    - debugger=True（或 config.ENABLE_DEBUGGER=True）→ 包含 Debugger + PatchApplier 修复循环
    - ENABLE_RAG=True → Generator/Debugger 节点中使用 RAG 检索增强

    Args:
        planner: 是否启用 Planner 节点。None（默认）时读取 config.ENABLE_PLANNER。
                 消融实验可按需显式传 False 构建无规划基线图，无需 reload 模块。
        debugger: 是否启用 Debugger + PatchApplier 修复循环。None（默认）时读取
                 config.ENABLE_DEBUGGER。

    Returns:
        已注册的 StateGraph 实例（尚未编译，需调用 .compile() 后才能运行）。
        编译后返回 Runnable 对象，可通过 .invoke() 执行完整流程。
    """
    # 显式覆盖 > 配置文件开关：planner/debugger 为 None 时回落到 config 值
    enable_planner = ENABLE_PLANNER if planner is None else planner
    enable_debugger = ENABLE_DEBUGGER if debugger is None else debugger

    workflow = StateGraph(AITesterState)

    # ── 始终注册的节点（核心必选组件）─────────────────────────────────────────
    # Generator 负责生成测试代码，Executor 负责执行测试，这两个节点缺一不可
    # 若缺少任何一个，系统将无法完成"生成→执行"的基本闭环
    workflow.add_node("generator", _generator_node)
    workflow.add_node("executor", _executor_node)

    # ── 固定边：Generator → Executor（单向顺序依赖）──────────────────────────
    # Generator 必须先于 Executor 执行，因为 Executor 需要 Generator 的输出作为输入
    workflow.add_edge("generator", "executor")

    # ── 条件注册：Planner（消融开关 ENABLE_PLANNER 控制）────────────────────
    if enable_planner:
        workflow.add_node("planner", _planner_node)
        # 入口设置：从 planner 开始，确保每个任务都先经过逻辑分析
        # 这样 Generator 拿到的是结构化测试计划而非裸代码，提升生成质量
        workflow.set_entry_point("planner")
        workflow.add_edge("planner", "generator")
    else:
        # 无 Planner 模式：跳过逻辑分析，直接从 generator 开始
        # 适用于纯 LLM 基线实验或消融实验中移除 Planner 的场景
        workflow.set_entry_point("generator")

    # ── 条件注册：Debugger + PatchApplier（消融开关 ENABLE_DEBUGGER 控制）────
    if enable_debugger:
        # 添加调试节点和补丁应用节点，构成修复循环
        workflow.add_node("debugger", _debugger_node)
        workflow.add_node("patch_applier", _patch_applier_node)

        # 3.5 跨文件修复：可选的 cross_file_analyzer 节点（CROSS_FILE_ENABLE=true 时启用）
        # 位于 executor → debugger 之间，分析跨文件依赖并写入 state["cross_file_deps"]
        if cross_file_enabled():
            workflow.add_node("cross_file_analyzer", _cross_file_analyzer_node)
            # 将 executor → debugger 边拆分为 executor → cross_file_analyzer → debugger
            workflow.add_conditional_edges(
                "executor",
                _should_debug,
                {
                    "debug": "cross_file_analyzer",
                    "done": END,
                    "regenerate": "generator",
                },
            )
            workflow.add_edge("cross_file_analyzer", "debugger")
        else:
            # 默认路径：executor → debugger（保持历史行为）
            workflow.add_conditional_edges(
                "executor",
                _should_debug,
                {
                    "debug": "debugger",
                    "done": END,
                    "regenerate": "generator",
                },
            )

        # 顺序边：Debugger 输出补丁 → PatchApplier 应用到代码 → 回到 Executor 验证
        # 这构成一个可多次迭代的修复循环，每次循环后更新 iteration 计数
        workflow.add_edge("debugger", "patch_applier")
        workflow.add_edge("patch_applier", "executor")
    else:
        # 无 Debugger 模式：Executor 完成后直接结束，不做任何修复尝试
        # 适用于消融实验中移除 Debugger 或纯 LLM 单次调用基线
        workflow.add_edge("executor", END)

    return workflow


def _should_skip_debugger(state: AITesterState) -> bool:
    """
    智能判断是否可以跳过 Debugger 节点。

    优化策略：
    - 若连续多次修复后测试仍失败，说明问题可能无法通过补丁解决
    - 若诊断表明是测试代码自身错误（非被测代码 bug），应触发重新生成而非修复

    Args:
        state: 当前工作流状态。

    Returns:
        True 表示应跳过 Debugger，False 表示应继续修复。
    """
    if not state.get("test_passed") and ENABLE_DEBUGGER:
        repair_history = state.get("repair_history", []) or []
        # 若最近 2 次修复均未成功应用或无效，考虑跳过
        if len(repair_history) >= 2:
            recent = repair_history[-2:]
            if all(not h.get("patch_applied", False) for h in recent):
                logger.info("连续多次修复无效，跳过 Debugger")
                return True
    return False


def _should_debug(state: AITesterState) -> str:
    """
    判断是否进入调试修复环节的路由函数。

    路由条件：
    - 测试已通过 → 结束流程（"done"）
    - 已达到最大迭代次数 → 若诊断表明是测试生成错误，重新生成测试（"regenerate"）
                         → 否则结束流程（"done"）
    - 否则 → 进入 debugger（"debug"）

    Args:
        state: 当前工作流状态。

    Returns:
        "debug" 表示进入调试，"done" 表示流程结束，"regenerate" 表示重新生成测试代码。
    """
    if state.get("test_passed") is True:
        _trace_node("_should_debug", decision="done", output_summary={"reason": "test_passed"})
        return "done"
    # 智能优化：若连续修复无效，直接结束而非继续浪费 token
    if _should_skip_debugger(state):
        _trace_node("_should_debug", decision="done", output_summary={"reason": "skip_debugger_repair_invalid"})
        return "done"

    if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS):
        diagnosis = state.get("diagnosis", "") or ""
        # 若诊断指出失败源于测试代码本身的问题（如 Attribute error、测试预期值错误），
        # 重新生成测试代码而不是放弃
        test_gen_keywords = [
            "测试生成错误",
            "测试设计存在错误",
            "test code",
            "AttributeError",
            "NameError",
            "SyntaxError",
            "测试用例",
            "期望的异常类型",
        ]
        if any(kw in diagnosis for kw in test_gen_keywords):
            # 上限保护：已再生成过（旧 diagnosis 关键词反复命中）时不再路由 regenerate，
            # 避免 generator↔executor 无限乒乓撞上 recursion_limit
            if state.get("regeneration_count", 0) < _MAX_REGENERATIONS:
                logger.info("诊断表明测试生成错误，触发重新生成测试代码")
                _trace_node("_should_debug", decision="regenerate", output_summary={"reason": "test_gen_diagnosis"})
                return "regenerate"
            logger.info("已达重新生成上限，结束流程")
        _trace_node("_should_debug", decision="done", output_summary={"reason": "max_iterations"})
        return "done"
    _trace_node("_should_debug", decision="debug", output_summary={"iteration": state.get("iteration", 0)})
    return "debug"


def build_workflow(planner: bool | None = None, debugger: bool | None = None) -> Any:
    """
    编译工作流图并返回可执行的 graph 对象。
    每次调用都创建新的 graph 实例，避免状态污染。

    Args:
        planner: 是否启用 Planner 节点（None 时读取 config.ENABLE_PLANNER）。
        debugger: 是否启用 Debugger 修复循环（None 时读取 config.ENABLE_DEBUGGER）。
        消融实验（如 plain_llm 基线）可显式传 False 构建降级图，无需 reload 模块。

    Returns:
        编译后的 LangGraph StateGraph 对象。
    """
    workflow = _create_workflow(planner=planner, debugger=debugger)
    return workflow.compile()


def get_workflow_stats() -> dict:
    """
    获取工作流执行统计信息。

    包含：
    - llm_cache: LLM 调用缓存统计
    - workflow_config: 当前启用的功能开关

    Returns:
        统计信息字典。
    """
    return {
        "llm_cache": get_cache_stats(),
        "workflow_config": {
            "ENABLE_PLANNER": ENABLE_PLANNER,
            "ENABLE_DEBUGGER": ENABLE_DEBUGGER,
            "ENABLE_RAG": ENABLE_RAG,
            "MAX_ITERATIONS": MAX_ITERATIONS,
        },
    }
