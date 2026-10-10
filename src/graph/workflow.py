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
import os
import re
import threading
from enum import Enum
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from config import (
    ENABLE_DEBUGGER,
    ENABLE_PLANNER,
    ENABLE_RAG,
    MAX_ITERATIONS,
    MAX_REGENERATIONS,
    detection_first_enabled,
)
from src.agents.llm_client import _llm_cache_dir, _llm_cache_enabled
from src.graph.mutation_advisor import (
    _mutation_advisor_node,
    mutation_advisor_enabled,
)

# 纯 re-export：保持历史 `from src.graph.workflow import ...` 导入路径不变。
# 这些符号的实现已拆分到 nodes/rag/tracing 模块，workflow 自身不直接使用，
# 仅通过命名空间转发供测试与外部调用方访问。
from src.graph.nodes import (  # noqa: F401
    _cross_file_analyzer_node,
    _debugger_node,
    _diagnosis_node,
    _executor_node,
    _generator_node,
    _get_default_test_plan,
    _patch_applier_node,
    _planner_node,
    _record_execution_trace,
    _validate_planner_output,
)
from src.graph.rag import RAG_MODULE_AVAILABLE, TestCaseRetriever, get_rag_retriever  # noqa: F401
from src.graph.state import AITesterState
from src.graph.tracing import _trace_local, _trace_node, end_task_trace, start_task_trace  # noqa: F401
from src.tools.cross_file import cross_file_enabled

# 模块级 logger，用于记录工作流执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)


# ─── StopReason 枚举（2026-09-29 审查 P0：统一停止条件单点判定）────────────
# 历史口径：终止原因散落在 _should_debug / _route_after_diagnosis 的多个
# 分支里（test_passed / max_iterations / skip_debugger_repair_invalid /
# test_defect_regeneration_cap / test_gen_diagnosis / test_gen_diagnosis_early
# / test_passed_converged / max_iterations_reached / budget_exceeded /
# regression_detected），各分支各写各的字符串，口径不一且"一个开关可
# 全部绕过"。现收拢为枚举 + 单点判定函数 determine_stop_reason：
# 所有路由函数在返回 "done" 前经本函数判定终止原因并写入
# state["stop_reason"]（纯观测，不参与路由），供实验层"终止原因
# 分布可解释"消费。
class StopReason(Enum):
    """工作流终止原因（统一单点判定口径）。"""

    TEST_PASSED = "test_passed"
    MAX_ITERATIONS = "max_iterations"
    REPAIR_INVALID = "skip_debugger_repair_invalid"
    TEST_DEFECT_REGEN_CAP = "test_defect_regeneration_cap"
    TEST_GEN_KEYWORD_EARLY = "test_gen_diagnosis_early"
    TEST_GEN_KEYWORD_LATE = "test_gen_diagnosis"
    TEST_PASSED_CONVERGED = "test_passed_converged"
    MAX_ITERATIONS_REACHED = "max_iterations_reached"
    BUDGET_EXCEEDED = "budget_exceeded"
    REGRESSION_DETECTED = "regression_detected"
    # P2-4（2026-10 停滞检测最小版）：连续 COVERAGE_STALL_ROUNDS 轮
    # 覆盖率 delta < eps 且测试仍失败 → 提前停止（归因"无法生成有效
    # 补丁"口径，与 1.3 收敛失败模式归因对齐）。COVERAGE_STALL_DETECT_ENABLE
    # 默认关，OFF 时本枚举值不可达（determine_stop_reason 守卫）。
    COVERAGE_STALL = "coverage_stall"
    RECURSION_LIMIT = "recursion_limit"
    UNKNOWN = "unknown"


def determine_stop_reason(state: AITesterState) -> StopReason:
    """单点判定终止原因（纯数据，零副作用）。

    所有路由函数在返回 "done" 时调用本函数获取终止原因枚举，
    并写入 state["stop_reason"]（纯观测字段，不参与路由逻辑）。
    判定优先级（从上到下，首个命中即返回）：
    1. test_passed=True → TEST_PASSED / TEST_PASSED_CONVERGED
    2. budget_exceeded=True → BUDGET_EXCEEDED
    3. regression_detected=True → REGRESSION_DETECTED
    4. defect_type=test_defect 且再生成达上限 → TEST_DEFECT_REGEN_CAP
    5. iteration >= max_iterations → MAX_ITERATIONS / MAX_ITERATIONS_REACHED
    6. 最近 2 次修复均无效 → REPAIR_INVALID
    6.5. P2-4 覆盖率停滞（COVERAGE_STALL_DETECT_ENABLE=true，默认关）：
        连续 N 轮 coverage_delta < eps 且 test_passed 为假 → COVERAGE_STALL
        （插入在 REPAIR_INVALID 与诊断关键词之间，OFF 时零行为变化）
    7. 诊断关键词命中（早期/晚期）→ TEST_GEN_KEYWORD_EARLY / LATE
    8. 未知 → UNKNOWN

    Args:
        state: 当前工作流状态。

    Returns:
        StopReason 枚举值。
    """
    # 1. 测试已通过（最优先：收敛即终止）
    if state.get("test_passed"):
        return StopReason.TEST_PASSED
    # 2. 预算超限（硬上界优先于迭代上限）
    if state.get("budget_exceeded"):
        return StopReason.BUDGET_EXCEEDED
    # 3. 回归检测（P2P 门禁 / regression_detected 标记）
    if state.get("regression_detected"):
        return StopReason.REGRESSION_DETECTED
    # 4. 测试缺陷 + 再生成达上限
    if state.get("defect_type") == "test_defect" and state.get("regeneration_count", 0) >= _MAX_REGENERATIONS:
        return StopReason.TEST_DEFECT_REGEN_CAP
    # 5. 迭代达上限
    if int(state.get("iteration", 0)) >= int(state.get("max_iterations", MAX_ITERATIONS)):
        return StopReason.MAX_ITERATIONS
    # 6. 连续修复无效快速终止
    if _recent_repairs_invalid(state):
        return StopReason.REPAIR_INVALID
    # 6.5. P2-4 覆盖率停滞检测（COVERAGE_STALL_DETECT_ENABLE=true 时启用，
    # 默认关零行为变化）：连续 N 轮覆盖率 delta < eps 且测试仍失败 →
    # 提前停止（"无法生成有效补丁"口径，对齐 1.3 收敛失败模式归因）。
    # 纯观测层判定（本函数本身不改路由；消费方按返回的 COVERAGE_STALL
    # 决定是否提前 done——见 _should_debug / _route_after_diagnosis 的
    # 停滞短路分支）。
    if _coverage_stall_detected(state):
        return StopReason.COVERAGE_STALL
    # 7. 诊断关键词命中（R17：结构化 error_category 优先，关键词兜底——
    #    ROUTE_STRUCTURED_ENABLE 默认关时与历史关键词口径逐字节一致）
    diagnosis = state.get("diagnosis", "") or ""
    if _test_gen_signal_hit(state, diagnosis)[0]:
        if int(state.get("iteration", 0)) < int(state.get("max_iterations", MAX_ITERATIONS)):
            return StopReason.TEST_GEN_KEYWORD_EARLY
        return StopReason.TEST_GEN_KEYWORD_LATE
    # 8. 未知（保守兜底）
    return StopReason.UNKNOWN


def effective_stop_reason(state: AITesterState) -> str | None:
    """读取终止原因（O35 修复：路由层写入会被 LangGraph 丢弃，读取侧兜底）。

    背景：``_should_debug`` / ``_route_after_diagnosis`` 在返回 "done" 前执行
    ``state["stop_reason"] = _stop_reason.value``——但条件边函数拿到的 state 是
    LangGraph 按 channel 值物化的**入参副本**，原地改写不会写回状态（已在
    langgraph 1.2.11 实测复现：路由里改 state，最终输出仍为初始 None）。
    于是 ``final_state["stop_reason"]`` 恒为初始值 None，实验结果的
    stop_reason 列全空，StopReason 机制实际不可观测。

    本函数作为**唯一读取口径**：优先取 state 里已有的 stop_reason（若未来
    有节点经 update dict 正规写入），缺失时用 determine_stop_reason 按
    同一优先级对最终状态重新判定——路由层判定与读取时判定基于同一组
    输入键（test_passed / budget_exceeded / iteration / diagnosis 等），
    仅可能相差 iteration 的自增时机，观测语义等价。

    Args:
        state: 工作流最终状态（或任意中间状态）。

    Returns:
        终止原因字符串（枚举 .value）；状态信息不足时返回 None。
    """
    existing = state.get("stop_reason")
    if existing:
        return str(existing)
    if not state:
        return None
    return determine_stop_reason(state).value


# 重新生成测试代码的上限：达到最大迭代后，诊断指向"测试生成错误"时路由回
# generator 再生成一次。若无上限，旧的 diagnosis 关键词会反复命中，
# generator↔executor 无限乒乓，最终撞上 LangGraph recursion_limit 崩掉任务并空烧 token。
# 取 1：一次再生成已足够验证"换一版测试"是否解决问题，再多只会浪费。
# Z2（2026-10-06 审查修复）：数值迁至 config.MAX_REGENERATIONS 单一事实源
# （nodes 侧原有一份同值局部字面量，靠注释"同口径"维系——已删除并改为
# 同源 import；本别名保留以维持模块内既有引用不变）。
_MAX_REGENERATIONS = MAX_REGENERATIONS

# 诊断关键词 → "测试生成错误"判定（路由回 generator 的触发词）。
# 2026-09-26 全面审查：从 _should_debug 函数体内提取为模块级常量——
# 此前每次路由调用（每轮迭代）都重建 list 字面量；提取后口径单一来源，
# 后续调整触发词只改一处（与 _MAX_REGENERATIONS 同文件同注释区）。
#
# M5（2026-09-29 审查 P0）：删除三个源码缺陷最常见的异常签名
# （AttributeError / NameError / SyntaxError）。这三个词出现在被测代码
# 的失败 traceback 中时，诊断节点会**误判为测试生成错误** → 路由回
# generator 重写测试 → 源码一字未改而测试通过 → 假通过且无任何标记
# （error_classifier.py:1202 的 test_passed is not False 早退使该假通过
# 永远不会被标记）。保留其余通用词，源码缺陷签名交由
# test_regenerated_pass_unverified 标记通道处理（见 M5 对应节点改动）。
_TEST_GEN_DIAGNOSIS_KEYWORDS: tuple[str, ...] = (
    "测试生成错误",
    "测试设计存在错误",
    "test code",
    "测试用例",
    "期望的异常类型",
)


# 延迟初始化哨兵（避免模块加载时 import re 的额外开销）。
# 2026-09-26 全面审查（P2 初始化顺序）：此前该哨兵定义在本函数之后
# （下方 `_diagnosis_node_enabled` 之前）——模块加载后立即调用本函数
# （早于模块体执行到哨兵赋值）时 `global` 重绑定会创建"从未被赋值"的
# 模块属性，首读抛 NameError，被函数吞掉懒初始化后每次都重建正则（优化
# 彻底失效且语义上"None 才编译"的契约被破坏）。现上移至函数定义之前。
_DIAGNOSIS_KEYWORD_RE: re.Pattern[str] | None = None


def _diagnosis_hits_test_gen_keywords(diagnosis: str) -> bool:
    """2026-09-26 性能优化：诊断文本是否命中"测试生成错误"关键词。

    预编译为单个 alternation 正则（`kw1|kw2|...`），一次 O(n) 扫描替代
    9 次 `any(kw in text)` 的 O(9n) 子串搜索。_TEST_GEN_DIAGNOSIS_KEYWORDS
    提取为常量后此处只编译一次，后续调用零开销。
    """
    global _DIAGNOSIS_KEYWORD_RE
    if _DIAGNOSIS_KEYWORD_RE is None:
        _DIAGNOSIS_KEYWORD_RE = re.compile("|".join(re.escape(kw) for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS))
    assert _DIAGNOSIS_KEYWORD_RE is not None  # 上方 if 分支已赋值
    return bool(_DIAGNOSIS_KEYWORD_RE.search(diagnosis))


# R17（2026-10-05 审查 P1）：结构化"测试生成错误"信号——错误分类器的
# error_category（ErrorCategory.LOGIC_ERROR = 断言失败但失败栈未触及被测
# 模块，即"测试逻辑错误"语义）优先于中文诊断关键词匹配做路由判定。
# 动机：关键词匹配依赖 LLM 诊断文本（M5 事故证明其脆弱性——AttributeError/
# NameError/SyntaxError 曾被误判为测试生成错误触发假通过）；结构化枚举
# 由 error_classifier 从失败栈零歧义判定。
# 受 ROUTE_STRUCTURED_ENABLE 守门（默认 false，历史关键词口径逐字节不变）。
_ROUTE_STRUCTURED_ENV = "ROUTE_STRUCTURED_ENABLE"
# 结构化判定为"测试侧缺陷"的 error_category 集合（保守：仅收录语义无歧义的
# LOGIC_ERROR；TYPE_ERROR 等两侧皆可归因的类别不纳入，防误路由）
_TEST_GEN_ERROR_CATEGORIES: frozenset[str] = frozenset({"logic_error"})


def _structured_route_enabled() -> bool:
    """R17 结构化路由开关（ROUTE_STRUCTURED_ENABLE=true 时启用，默认 false）。"""
    return os.getenv(_ROUTE_STRUCTURED_ENV, "false").lower() in ("true", "1", "on")


def _test_gen_signal_hit(state: AITesterState, diagnosis: str) -> tuple[bool, str]:
    """R17：测试生成错误信号判定（结构化优先，关键词兜底）。

    Returns:
        (是否命中, 信号来源标签)——来源 ∈ {"structured_error_category",
        "diagnosis_keyword", ""}，供 trace 打点度量"关键词兜底触发率"
        （验证指标：<1%，高则说明分类器覆盖不足）。
    """
    if _structured_route_enabled():
        category = state.get("error_category") or ""
        if category in _TEST_GEN_ERROR_CATEGORIES:
            return True, "structured_error_category"
    if _diagnosis_hits_test_gen_keywords(diagnosis):
        return True, "diagnosis_keyword"
    return False, ""


def _diagnosis_node_enabled() -> bool:
    """三、双向诊断节点开关（DIAGNOSIS_NODE_ENABLE=true 时启用，默认 false）。

    启用后工作流在 executor → debugger 之间插入显式 DiagnosisNode
    （_diagnosis_node）：先诊断"代码缺陷 vs 测试缺陷"，再按判定路由
    （测试缺陷 → generator 重新生成；代码缺陷 → debugger 生成补丁）。
    默认关闭保持历史实验口径（历史路径由 _debugger_node 内部
    BIDIRECTIONAL_DIAGNOSIS_ENABLE 完成内联诊断，二者可叠加但默认都关）。
    """
    return os.getenv("DIAGNOSIS_NODE_ENABLE", "false").lower() == "true"


def _route_after_diagnosis(state: AITesterState) -> str:
    """DiagnosisNode 之后的条件路由（三、双向诊断）。

    按 defect_type 判定路由：
    - test_defect 且再生成未达上限 → "regenerate"（路由回 generator 重新生成测试）；
    - test_defect 且再生成已达上限 → "done"（与 _should_debug 同口径收敛，
      防 generator↔executor 无上限乒乓撞 recursion_limit）；
    - test_passed=True 或 iteration>=max_iterations → "done"（M4 收敛保护，
      与 _should_debug 同口径，防无界回环撞 LangGraph 默认 recursion_limit）；
    - 其余（implementation_defect / 缺省）→ "debug"（路由到 debugger 生成补丁）。

    Args:
        state: 当前工作流状态（含 defect_type / regeneration_count 等字段）。

    Returns:
        "regenerate" / "done" / "debug"。
    """
    defect_type = state.get("defect_type")
    if defect_type == "test_defect":
        # 测试缺陷 → 重新生成测试（regeneration_count 上限保护在 _should_debug
        # 与 _generator_node 再生成判定中已有；此处直接路由，上限由 generator
        # 侧的再生成判定统一兜底，避免 generator↔executor 无限乒乓）。
        # 2026-09-26 全面审查（P2 一致性）：本路径是 DIAGNOSIS_NODE_ENABLE=true
        # 时 executor → diagnosis → generator 的路由，此前**无条件** regenerate
        # 不检查 regeneration_count——Review Agent 反复判 test_defect 时
        # （_generator_node 再生成判定仅在 defect_type 写入态才 +1，下一轮
        # diagnosis 节点可重新写入 test_defect），generator↔executor 无上限
        # 乒乓，最终撞 LangGraph recursion_limit 崩任务并空烧 token；而
        # _should_debug 的 test_defect 上限收敛分支（reason=test_defect_
        # regeneration_cap）在同一条件下收敛 done。
        # 现补同口径上限门控：regeneration_count 达 _MAX_REGENERATIONS 时
        # 直接 done，与 _should_debug 行为对齐（仅影响双开关默认关的
        # DIAGNOSIS_NODE_ENABLE 路径，默认行为不变）。
        if state.get("regeneration_count", 0) >= _MAX_REGENERATIONS:
            logger.info("双向诊断（三）：已达重新生成上限，结束流程")
            _stop_reason = determine_stop_reason(state)
            _trace_node(
                "_route_after_diagnosis",
                decision="done",
                output_summary={"reason": _stop_reason.value},
            )
            state["stop_reason"] = _stop_reason.value
            return "done"
        _trace_node("_route_after_diagnosis", decision="regenerate", output_summary={"reason": "diagnosis_test_defect"})
        return "regenerate"
    # M4（2026-09-29 审查 P0）：双向诊断开启时，test_passed 收敛与迭代上限
    # 曾在此分支全部绕过（test_passed=True / iteration>=MAX_ITERATIONS 时仍
    # 返回 debug，回环只受 LangGraph 默认 recursion_limit=10007 约束）。
    # 现补同口径收敛保护：已收敛即 done；超迭代上限即 done。
    # 2026-09-29 审查 P0（StopReason）：终止原因经 determine_stop_reason 单点判定。
    if state.get("test_passed") is True:
        _stop_reason = determine_stop_reason(state)
        _trace_node(
            "_route_after_diagnosis",
            decision="done",
            output_summary={"reason": _stop_reason.value},
        )
        state["stop_reason"] = _stop_reason.value
        return "done"
    max_iterations = state.get("max_iterations", MAX_ITERATIONS)
    if int(state.get("iteration", 0)) >= int(max_iterations):
        logger.info("双向诊断（三）：已达迭代上限，结束流程")
        _stop_reason = determine_stop_reason(state)
        _trace_node(
            "_route_after_diagnosis",
            decision="done",
            output_summary={"reason": _stop_reason.value, "iteration": int(state.get("iteration", 0))},
        )
        state["stop_reason"] = _stop_reason.value
        return "done"
    _trace_node("_route_after_diagnosis", decision="debug", output_summary={"defect_type": defect_type})
    return "debug"


def _create_workflow(
    planner: bool | None = None, debugger: bool | None = None, allow_regeneration: bool = False
) -> StateGraph:
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
        allow_regeneration: X1（2026-10-05 审查 P0-3）：debugger=False 时是否
                 保留 executor → generator 的再生成路由。默认 False（历史：
                 executor → END）。True 供 plain_llm_df 基线使用——无修复
                 循环但保留"检出优先再生成"（_should_debug 的
                 detection_first_all_green 分支；"debug"（测试失败需修复）
                 在无 Debugger 语义下映射为 "done"：失败测试本身即潜在
                 检出，保留失败状态交 M1 裁决，不触发修复）。enable_debugger
                 =True 时本参数无效果（默认图已含完整路由）。

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
        # M7（2026-09-29 审查 P0）：mutation_advisor 节点（MUTATION_ADVISOR_ENABLE
        # =true 时启用，默认关）。在 executor → _should_debug 的 "regenerate"
        # 路径中插入该节点（executor → mutation_advisor → generator），
        # 把历史"benchmark 层预置 mutation_feedback 死代码"变为图内即时
        # 产出（每轮 executor 失败后跑变异评估，存活变异体清单写入
        # state["mutation_feedback"]，Generator 下一轮消费补强断言）。
        # 默认关时图拓扑与历史完全一致。
        use_mutation_advisor = mutation_advisor_enabled()
        if use_mutation_advisor:
            workflow.add_node("mutation_advisor", _mutation_advisor_node)
            # mutation_advisor → generator 固定边（regenerate 路径终点）
            workflow.add_edge("mutation_advisor", "generator")
        # M7：regenerate 目标节点——启用 mutation_advisor 时路由到
        # "mutation_advisor"（经变异评估后再生成），否则直接路由到 "generator"
        _regen_target = "mutation_advisor" if use_mutation_advisor else "generator"
        # 添加调试节点和补丁应用节点，构成修复循环
        workflow.add_node("debugger", _debugger_node)
        workflow.add_node("patch_applier", _patch_applier_node)

        # 三、双向诊断节点（DIAGNOSIS_NODE_ENABLE=true 时启用，默认关）：
        # 在 executor → debugger 之间插入显式 DiagnosisNode（先诊断"代码缺陷
        # vs 测试缺陷"，再按判定路由：测试缺陷 → generator 重新生成测试；
        # 代码缺陷 → debugger 生成补丁）。默认关闭保持历史口径。
        use_diagnosis_node = _diagnosis_node_enabled()
        if use_diagnosis_node:
            workflow.add_node("diagnosis", _diagnosis_node)

        # 3.5 跨文件修复：可选的 cross_file_analyzer 节点（CROSS_FILE_ENABLE=true 时启用）
        # 位于 executor → debugger 之间，分析跨文件依赖并写入 state["cross_file_deps"]
        if cross_file_enabled():
            workflow.add_node("cross_file_analyzer", _cross_file_analyzer_node)
            if use_diagnosis_node:
                # 诊断节点开启时：executor → diagnosis → (generator | cross_file_analyzer → debugger)
                workflow.add_edge("executor", "diagnosis")
                workflow.add_conditional_edges(
                    "diagnosis",
                    _route_after_diagnosis,
                    {
                        "regenerate": _regen_target,
                        "debug": "cross_file_analyzer",
                        # P2 一致性（2026-09-26）：test_defect 达再生成上限时
                        # 路由 done（与 _should_debug 同口径收敛）
                        "done": END,
                    },
                )
                workflow.add_edge("cross_file_analyzer", "debugger")
            else:
                # 仅跨文件（无诊断节点）：executor → _should_debug → cross_file_analyzer → debugger
                workflow.add_conditional_edges(
                    "executor",
                    _should_debug,
                    {
                        "debug": "cross_file_analyzer",
                        "done": END,
                        "regenerate": _regen_target,
                    },
                )
                workflow.add_edge("cross_file_analyzer", "debugger")
        elif use_diagnosis_node:
            # 诊断节点开启：executor → diagnosis → (generator | debugger)
            workflow.add_edge("executor", "diagnosis")
            workflow.add_conditional_edges(
                "diagnosis",
                _route_after_diagnosis,
                {
                    "regenerate": _regen_target,
                    "debug": "debugger",
                    # P2 一致性（2026-09-26）：test_defect 达再生成上限时
                    # 路由 done（与 _should_debug 同口径收敛）
                    "done": END,
                },
            )
        else:
            # 默认路径：executor → _should_debug → (debugger | END | generator)
            workflow.add_conditional_edges(
                "executor",
                _should_debug,
                {
                    "debug": "debugger",
                    "done": END,
                    "regenerate": _regen_target,
                },
            )

        # 顺序边：Debugger 输出补丁 → PatchApplier 应用到代码 → 回到 Executor 验证
        # 这构成一个可多次迭代的修复循环，每次循环后更新 iteration 计数
        workflow.add_edge("debugger", "patch_applier")
        workflow.add_edge("patch_applier", "executor")
    elif allow_regeneration:
        # X1（2026-10-05 审查 P0-3）：无修复循环但保留再生成路由——
        # plain_llm_df 基线（plain_llm + 检出优先协议）专用拓扑：
        # executor → _route_no_debugger → ("regenerate" → generator | "done" → END)。
        # 检出优先分支的生效条件由调用方经线程级覆盖控制
        # （config.set_detection_first_thread_override，见
        # run_benchmark.run_plain_llm_df_baseline）。
        workflow.add_conditional_edges(
            "executor",
            _route_no_debugger,
            {
                "regenerate": "generator",
                "done": END,
            },
        )
    else:
        # 无 Debugger 模式：Executor 完成后直接结束，不做任何修复尝试
        # 适用于消融实验中移除 Debugger 或纯 LLM 单次调用基线
        workflow.add_edge("executor", END)

    return workflow


def _recent_repairs_invalid(state: AITesterState) -> bool:
    """判断最近 2 次修复是否均未成功应用（纯数据判定，无日志副作用）。

    优化策略：
    - 若连续多次修复后测试仍失败，说明问题可能无法通过补丁解决
    - 若诊断表明是测试代码自身错误（非被测代码 bug），应触发重新生成而非修复

    Args:
        state: 当前工作流状态。

    Returns:
        True 表示最近 2 次修复均未成功应用（且 test_passed 为假）。
    """
    if state.get("test_passed"):
        return False
    repair_history = state.get("repair_history", []) or []
    if len(repair_history) < 2:
        return False
    recent = repair_history[-2:]
    return all(not h.get("patch_applied", False) for h in recent)


# ── P2-4（2026-10 停滞检测最小版）：覆盖率停滞 → 提前停止 ──────────────────
# 背景：修复循环的停止条件此前为 MAX_ITERATIONS 常数 + 预算硬上限；
# 覆盖率连续多轮无增益（delta < eps）的"无效迭代"仍会耗尽全部
# MAX_ITERATIONS 轮才停（浪费 token，与 1.3 收敛失败模式归因中
# "无法生成有效补丁" 口径对齐）。本层提供纯观测判定（默认关，
# OFF 时 determine_stop_reason 的 6.5 分支恒 False，零行为变化）。
# 判定口径：从 state["execution_trace"]（3.2 默认常开的执行反馈轨迹）
# 取最近 K 轮（COVERAGE_STALL_ROUNDS，默认 2）的 coverage_delta，
# 全部 |delta| < eps（COVERAGE_STALL_EPS，默认 0.5 个百分点；按绝对值
# 口径——小幅负增长与零增长都算停滞，显著负增长 |delta| >= eps 视为
# "仍在变化"不判停滞）且最近一轮 test_passed 为假 → 判为停滞。
# 首轮 delta=None（无上一轮）不计入（保守不判）。
def _coverage_stall_enabled() -> bool:
    """P2-4 停滞检测开关（COVERAGE_STALL_DETECT_ENABLE=true 时启用，默认关）。"""
    return os.getenv("COVERAGE_STALL_DETECT_ENABLE", "false").lower() in ("true", "1", "on")


def _coverage_stall_rounds() -> int:
    """P2-4：停滞判定窗口轮数（COVERAGE_STALL_ROUNDS，默认 2，下限 1）。"""
    try:
        return max(1, int(os.getenv("COVERAGE_STALL_ROUNDS", "2")))
    except ValueError:
        return 2


def _coverage_stall_eps() -> float:
    """P2-4：覆盖率 delta 停滞阈值 eps（COVERAGE_STALL_EPS，默认 0.5，即 0.5 个百分点）。"""
    try:
        return float(os.getenv("COVERAGE_STALL_EPS", "0.5"))
    except ValueError:
        return 0.5


def _coverage_stall_detected(state: AITesterState) -> bool:
    """P2-4 判定最近 K 轮覆盖率是否停滞（纯数据，无日志副作用）。

    开关 OFF（默认）时恒返回 False（零行为变化）；ON 时：
    - 从 state["execution_trace"] 尾部取 K 轮；不足 K 轮 → False（保守：
      信息不足不判停滞，保持 MAX_ITERATIONS 自然收敛口径）；
    - 任一轮 delta 为 None（首轮）或 test_passed=True → False；
    - 全部 delta < eps（按绝对值口径：负增长与零增长都算停滞）→ True。
    """
    if not _coverage_stall_enabled():
        return False
    if state.get("test_passed"):
        return False
    trace = state.get("execution_trace") or []
    k = _coverage_stall_rounds()
    if len(trace) < k:
        return False
    recent = trace[-k:]
    eps = _coverage_stall_eps()
    for entry in recent:
        if not isinstance(entry, dict):
            return False
        if entry.get("passed"):
            return False
        delta = entry.get("coverage_delta")
        if delta is None:
            return False
        if abs(float(delta)) >= eps:
            return False
    return True


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
    # 2026-09-26 全面审查（P1 一致性）：此前用 `is True` 严格恒等判定，
    # 与 _recent_repairs_invalid 的 truthiness 口径不一致——若 executor
    # 某路径写入非 bool 的真值（如 numpy.bool_），`is True` 为假 → 误路由 debug。
    # 现统一为 truthiness（与 _recent_repairs_invalid / _executor_node 写入口径
    # 一致：test_passed 由 executor 的 test_result["passed"] 赋值，语义即"测试全过"）。
    if state.get("test_passed"):
        # W3（2026-10-05 审查落地·检出优先协议，DETECTION_FIRST_ENABLE 默认关时
        # 零行为变化）：首轮全绿（iteration==0，被测代码未修复，测试在缺陷代码上
        # 全通过 = 未检出任何缺陷）且再生成预算未用尽时，不把全绿当成功——路由
        # regenerate 逼 generator 产出能让缺陷代码变红的测试（先红后绿协议）。
        # 上限保护：regeneration_count < _MAX_REGENERATIONS（与 generator 侧
        # 计数 +1 联动，防 executor↔generator 乒乓撞 recursion_limit）。
        # 执行过判定：execution_trace 非空（防未执行态误路由）。
        if (
            detection_first_enabled()
            and int(state.get("iteration", 0)) == 0
            and not state.get("detection_first_red_seen")
            and int(state.get("regeneration_count", 0)) < _MAX_REGENERATIONS
            and state.get("execution_trace")
        ):
            logger.info("W3 检出优先：首轮全绿未检出缺陷，触发再生成更强的测试（先红后绿）")
            _trace_node(
                "_should_debug",
                decision="regenerate",
                output_summary={"reason": "detection_first_all_green"},
            )
            return "regenerate"
        _stop_reason = determine_stop_reason(state)
        _trace_node("_should_debug", decision="done", output_summary={"reason": _stop_reason.value})
        state["stop_reason"] = _stop_reason.value
        return "done"
    # AC2（2026-10-06 第十轮审查 T-P0-4①）特异性门路由：首轮红但判定为
    # 过红（gold fixed 上也红，非缺陷特异，verdict 由 _executor_node 的
    # 门①对照执行写入）→ 修代码无意义（测试对无缺陷代码也失败），
    # 路由 regenerate 换缺陷特异的测试（regeneration_count 上限保护与
    # 其余再生成路径同口径）。verdict 缺失 / unavailable 时零行为变化。
    from src.tools.detection_gates import detection_specificity_gate_enabled as _specificity_gate_on

    if (
        _specificity_gate_on()
        and int(state.get("iteration", 0)) == 0
        and state.get("specificity_gate_verdict") == "over_red"
        and int(state.get("regeneration_count", 0)) < _MAX_REGENERATIONS
    ):
        logger.info("AC2 特异性门：过红测试（gold fixed 上仍红），路由再生成缺陷特异测试")
        _trace_node(
            "_should_debug",
            decision="regenerate",
            output_summary={"reason": "specificity_gate_over_red"},
        )
        return "regenerate"
    # 智能优化：若连续修复无效，直接结束而非继续浪费 token
    # （纯数据判定，日志副作用留在路由层；_recent_repairs_invalid 保持零副作用）。
    # 2026-09-26 全面审查（P1 分支顺序）：本判定限定在"迭代未达上限"时执行——
    # 此前无条件下前置（见上方 test_passed 判定块），最后一轮（iteration >=
    # max_iterations）若最近 2 次修复均 patch_applied=False（"补丁反复失败"
    # 典型场景），本分支先于迭代上限分支执行并直接 done，永远遮蔽上限分支内
    # 的关键词 regenerate 与 test_defect 上限收敛分支——test_passed 判定块
    # 注释承诺的"达上限+关键词命中仍给 generator 一次 regenerate 机会"
    # 被静默打破（终止 reason 还被误标为 skip_debugger_repair_invalid，
    # 掩盖真实终止原因；现测试均用空 repair_history 锁定 regenerate 语义，
    # 该遮蔽无回归覆盖）。
    # 达上限时由下方上限分支统一决策（关键词命中 → 一次 regenerate 机会，
    # 否则 done）；repair_invalid 的"连续修复无效快速终止"语义仅在早期迭代
    # 生效（此时继续修代码确无意义，省 token 口径不变）。
    if state.get("iteration", 0) < state.get("max_iterations", MAX_ITERATIONS) and _recent_repairs_invalid(state):
        logger.info("连续多次修复无效，跳过 Debugger")
        _stop_reason = determine_stop_reason(state)
        _trace_node(
            "_should_debug",
            decision="done",
            output_summary={"reason": _stop_reason.value, "iteration": int(state.get("iteration", 0))},
        )
        state["stop_reason"] = _stop_reason.value
        return "done"

    # 3.1 双向诊断：Review Agent 判定为"测试缺陷"时，直接路由回 generator
    # 重新生成测试（分支修复），不进入 debugger 修代码；regeneration_count
    # 上限防止 generator↔executor 无限乒乓（与 diagnosis 关键词路径同口径）。
    # 上限已满且仍判定为测试缺陷：继续修代码无意义（Review Agent 认为代码无
    # 缺陷），直接结束，避免空耗剩余迭代。
    # 注意（2026-09-26 全面审查 P1 分支顺序）：本分支置于迭代上限检查之后——
    # 达上限且再生成上限已满时由下方 test_defect 上限收敛分支（reason=
    # test_defect_regeneration_cap）统一判定（与 2026-09-25 原始语义一致），
    # 避免"关键词 regenerate 绕过 3.1 上限保护"的口径矛盾；
    # 达上限 + 关键词命中场景仍由上方上限分支给 generator 一次 regenerate
    # 机会（上限保护不变）。
    if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS):
        diagnosis = state.get("diagnosis", "") or ""
        # 若诊断指出失败源于测试代码本身的问题（如 Attribute error、测试预期值错误），
        # 重新生成测试代码而不是放弃（R17：结构化 error_category 优先，关键词兜底）
        _hit, _hit_source = _test_gen_signal_hit(state, diagnosis)
        if _hit:
            # 上限保护：已再生成过（旧 diagnosis 关键词反复命中）时不再路由 regenerate，
            # 避免 generator↔executor 无限乒乓撞上 recursion_limit
            if state.get("regeneration_count", 0) < _MAX_REGENERATIONS:
                logger.info("诊断表明测试生成错误（信号=%s），触发重新生成测试代码", _hit_source)
                _trace_node(
                    "_should_debug",
                    decision="regenerate",
                    output_summary={"reason": "test_gen_diagnosis", "signal": _hit_source},
                )
                return "regenerate"
            logger.info("已达重新生成上限，结束流程")
        _stop_reason = determine_stop_reason(state)
        _trace_node("_should_debug", decision="done", output_summary={"reason": _stop_reason.value})
        state["stop_reason"] = _stop_reason.value
        return "done"

    if state.get("defect_type") == "test_defect":
        if state.get("regeneration_count", 0) < _MAX_REGENERATIONS:
            logger.info("双向诊断（3.1）：测试缺陷，路由回 generator 重新生成测试")
            _trace_node("_should_debug", decision="regenerate", output_summary={"reason": "review_test_defect"})
            return "regenerate"
        logger.info("双向诊断（3.1）：已达重新生成上限，结束流程")
        # 2026-09-30 审查修复：与其余 done 分支同口径，经 determine_stop_reason
        # 单点判定终止原因并写入 state["stop_reason"]（此前该分支只 trace
        # 了硬编码 reason 而未写 stop_reason，effective_stop_reason 读取侧
        # 会落到 UNKNOWN，掩盖真实终止原因 test_defect_regeneration_cap）。
        _stop_reason = determine_stop_reason(state)
        _trace_node(
            "_should_debug",
            decision="done",
            output_summary={"reason": _stop_reason.value, "regeneration_count": state.get("regeneration_count", 0)},
        )
        state["stop_reason"] = _stop_reason.value
        return "done"

    # 2026-09-26 全面审查（P1 路由语义澄清）：诊断指向"测试生成错误"时，
    # 此前**只有**达迭代上限（iteration >= max_iterations）才路由 regenerate，
    # 早期迭代（iteration < max）命中关键词仍走 debugger 修代码——与
    # _generator_node 再生成判定（含 defect_type == test_defect 任意迭代可触发）
    # 及 3.1 双向诊断路径口径不一致。现把诊断关键词判定提升为独立分支：
    # 任意 iteration 命中即 regenerate（仍受 regeneration_count 上限保护）；
    # 上限已满时落到下方常规 debug（保守口径：上限保护不变）。
    # R17：结构化 error_category 优先，关键词兜底（信号来源入 trace 打点）。
    diagnosis = state.get("diagnosis", "") or ""
    _hit_early, _hit_early_source = _test_gen_signal_hit(state, diagnosis)
    if _hit_early and state.get("regeneration_count", 0) < _MAX_REGENERATIONS:
        logger.info("诊断表明测试生成错误（iteration < max，信号=%s），触发重新生成测试代码", _hit_early_source)
        _trace_node(
            "_should_debug",
            decision="regenerate",
            output_summary={"reason": "test_gen_diagnosis_early", "signal": _hit_early_source},
        )
        return "regenerate"
    # 早期迭代但（信号未命中或再生成上限已满）：落到下方常规 debug

    _trace_node("_should_debug", decision="debug", output_summary={"iteration": state.get("iteration", 0)})
    return "debug"


def _route_no_debugger(state: AITesterState) -> str:
    """X1（2026-10-05 审查 P0-3）：无 Debugger 拓扑的 executor 路由包装。

    复用 _should_debug 的全部判定（含 W3 检出优先的
    detection_first_all_green 分支），仅把 "debug"（测试失败需修复——
    无 Debugger 可去）映射为 "done"：失败测试本身即潜在检出（buggy 侧
    变红），保留失败状态交 M1 独立裁决，不触发修复（与 plain_llm
    "不修复"口径一致）。供 plain_llm_df 基线拓扑
    （build_workflow(allow_regeneration=True)）使用；模块级定义便于
    直接单测。
    """
    verdict = _should_debug(state)
    return "done" if verdict == "debug" else verdict


def build_workflow(planner: bool | None = None, debugger: bool | None = None, allow_regeneration: bool = False) -> Any:
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
    # 18. 缓存安全启动钩子（每次 build_workflow 调用触发一次，纯卫生性操作）：
    # 1) 收敛缓存目录权限到 0o700（目录不存在时以 0o700 创建；已存在则尽力 chmod）；
    # 2) 按 AITESTER_LLM_CACHE_TTL_DAYS（默认 7 天）清理过期缓存文件，避免缓存
    #    目录长期积累敏感 prompt/响应。失败不阻断工作流构建（主流程不变）。
    try:
        from src.agents.llm_client import cleanup_expired_cache_files, ensure_llm_cache_dir

        if _llm_cache_enabled():
            ensure_llm_cache_dir()
            removed = cleanup_expired_cache_files()
            if removed:
                logger.info("18. LLM 缓存过期清理：删除 %d 个 TTL 过期条目", removed)
    except Exception:
        # 缓存目录收敛/清理属卫生性操作，任何异常（含权限 / IO）不得阻断工作流
        pass
    workflow = _create_workflow(planner=planner, debugger=debugger, allow_regeneration=allow_regeneration)
    # M12（2026-09-30 审查 D.4-2）：RISK_APPROVAL_ENABLE=true 时注入
    # checkpointer，使 LangGraph interrupt() 可真正暂停并恢复。
    # 默认关时（RISK_APPROVAL_ENABLE=false）不注入，保持历史行为零变化。
    # 使用 MemorySaver（进程内）；SqliteSaver 需 langgraph-checkpoint-sqlite
    # 包，当前未安装，待后续批次引入。
    _checkpointer = None
    try:
        # P2-2（2026-10-02 审查）：复用模块顶部 `import os`（L47），
        # 此前函数内 `import os as _os` 冗余。
        if os.getenv("RISK_APPROVAL_ENABLE", "false").lower() in ("true", "1", "on"):
            from langgraph.checkpoint.memory import MemorySaver

            _checkpointer = MemorySaver()
            logger.info("M12：RISK_APPROVAL_ENABLE=true，注入 MemorySaver checkpointer")
    except ImportError:
        logger.warning("M12：MemorySaver 不可用（langgraph.checkpoint.memory 缺失），跳过 checkpointer")

    # 20. M4（2026-09-29 审查 P0）：DIAGNOSIS_NODE_ENABLE=true 时诊断分支曾绕过
    # 收敛保护，回环只受 LangGraph 默认 recursion_limit=10007 约束（已实测发生
    # Recursion limit of 10007 reached 事故）。现通过带 recursion_limit 的可运行
    # 包装注入显式上界：每次 invoke 传入 langgraph 的 config 参数（recursion_limit
    # 为合法键），使无界回环在 4*MAX_ITERATIONS+8 个 super-step 后终止，
    # 不再依赖框架默认值。包装仅重写 invoke / ainvoke（注入 config），
    # 其余方法透传底层 CompiledStateGraph，语义不变。
    _base_graph = workflow.compile(checkpointer=_checkpointer) if _checkpointer else workflow.compile()

    class _RecursionLimitedGraph:
        """带显式 recursion_limit 的 LangGraph 包装（M4 硬上界 + M12 checkpointer）。

        - invoke / ainvoke 透传给底层 CompiledStateGraph 并注入
          config={"recursion_limit": N}（LangGraph 的 invoke 接受 config
          参数，recursion_limit 为合法键），覆盖框架默认 10007；
          M12 checkpointer 启用时同时注入 configurable.thread_id（invoke
          调用方需传入 thread_id，否则用默认 "default"）；
        - 其余方法（get_state / stream / with_config 等）透传，语义不变。
        """

        def __init__(self, graph, recursion_limit: int, has_checkpointer: bool):
            self._graph = graph
            self._recursion_limit = recursion_limit
            self._has_checkpointer = has_checkpointer

        def _build_config(self, thread_id: str | None = None) -> dict:
            config: dict = {"recursion_limit": self._recursion_limit}
            if self._has_checkpointer:
                config["configurable"] = {"thread_id": thread_id or "default"}
            return config

        def invoke(self, *args, **kwargs):
            # 调用方已显式传 config（含自己的 recursion_limit）时不覆盖
            if "config" in kwargs and kwargs["config"] is not None:
                return self._graph.invoke(*args, **kwargs)
            # 合并调用方传入的 thread_id（M12 checkpointer 场景）
            thread_id = kwargs.pop("thread_id", None)
            kwargs["config"] = self._build_config(thread_id)
            return self._graph.invoke(*args, **kwargs)

        async def ainvoke(self, *args, **kwargs):
            if "config" in kwargs and kwargs["config"] is not None:
                return await self._graph.ainvoke(*args, **kwargs)
            thread_id = kwargs.pop("thread_id", None)
            kwargs["config"] = self._build_config(thread_id)
            return await self._graph.ainvoke(*args, **kwargs)

        def __getattr__(self, item):
            return getattr(self._graph, item)

    # E1/E2 实证（2026-10-07）：logic 档双门（特异性门 over_red 路由
    # 再生成 + 红回归门）显著增加图节点往返——4×MAX+8=20 使 E1 2/12 任务
    # 触顶；8×MAX+8=32 仍使 E2 16/174 任务次触顶（正常任务 trace 事件
    # p90=21，生产布局复现最长 ~36 步）。上界升至 16×MAX+8（MAX=3 → 56，
    # 为实测最长任务的 ~1.55 倍）；防失控语义仍由内部 _MAX_REGENERATIONS
    # 等轮次上限承担，本值只是 LangGraph 层最后防线。
    return _RecursionLimitedGraph(_base_graph, 16 * int(MAX_ITERATIONS) + 8, _checkpointer is not None)


# 缓存条目数统计的进程内记忆（0.10 轮次）：生产 LLM 文件缓存在本进程内
# 只增不删（文件缓存 LRU 淘汰的是进程内响应值，磁盘文件保留；本进程无
# 删除缓存文件的代码路径，测试环境经 AITESTER_LLM_CACHE_DIR 指向独立临时
# 目录天然隔离记忆键）。条目数在本进程视角单调不减。记忆键 = (缓存目录,
# 条目数, 统计时目录 mtime)，跨 get_workflow_stats 调用复用（--parallel
# 多任务收尾报告逐任务调用时省 N-1 次 glob 目录扫描）；目录切换 / 目录
# mtime 变化（外部进程删除/新增缓存文件）时自动重扫，消除"外部清理后
# 记忆值偏大"的观测层失真（2026-09-26 全面审查：旧口径仅信 os.stat 成功
# 即复用记忆，外部删除文件后统计偏高直至目录整体消失才归 0）。
_FILE_CACHE_COUNT_MEMORY: tuple[str, int, float] | None = None
# 2026-09-26 全面审查（P2 线程卫生）：--parallel 多任务收尾报告并发调用
# get_workflow_stats → _file_cache_entry_count 时，_FILE_CACHE_COUNT_MEMORY 的
# 读-改-写无锁保护，可能读到半更新的记忆元组（另一线程 stat/glob 中途）。
# 加模块级 Lock 把"记忆读 + stat/glob + 记忆写"整段串行化（普通 Lock 即可，
# 临界区内无重入）；记忆键本身仍是 (目录, 条目数, mtime)，语义不变。
_FILE_CACHE_COUNT_MEMORY_LOCK = threading.Lock()


def _file_cache_entry_count() -> int:
    """统计生产 LLM 文件缓存（默认 ~/.cache/aitester/llm/*.json）当前条目数。

    缓存目录不存在或为空时返回 0（只读操作，不改变缓存内容）。
    0.10 性能：带进程内记忆（见上方 _FILE_CACHE_COUNT_MEMORY 说明）——
    同目录且 mtime 未变直接复用上次统计，免重复 glob；目录切换 / 目录
    消失（OSError）/ mtime 变化（外部删除或新增缓存文件）时自动重扫。
    """
    global _FILE_CACHE_COUNT_MEMORY
    cache_dir = _llm_cache_dir()
    # 2026-09-26 全面审查（P2 线程卫生）：记忆读-改-写整段加锁，--parallel
    # 多任务收尾并发调用时防读到半更新元组（临界区内 stat/glob 均为只读
    # 系统调用，无重入，普通 Lock 足够）
    with _FILE_CACHE_COUNT_MEMORY_LOCK:
        remembered = _FILE_CACHE_COUNT_MEMORY
        if remembered is not None and remembered[0] == cache_dir:
            # 记忆复用前做廉价 stat（O(1) 系统调用，比 glob 全目录扫描便宜）：
            # 目录仍在且 mtime 与统计时一致则信记忆免重扫；目录被外部删除
            # （OSError）或 mtime 变化（文件被外部增删）时自动重扫。
            try:
                st = os.stat(cache_dir)
            except OSError:
                _FILE_CACHE_COUNT_MEMORY = (cache_dir, 0, 0.0)
                return 0
            if st.st_mtime == remembered[2]:
                return remembered[1]
        try:
            entries = len(list(Path(cache_dir).glob("*.json")))
            # 统计成功同步记录目录 mtime（供下次调用免重扫判断）
            try:
                mtime = os.stat(cache_dir).st_mtime
            except OSError:
                mtime = 0.0
        except OSError:
            # 目录不存在（首次/被外部删除）：归 0 并记忆
            _FILE_CACHE_COUNT_MEMORY = (cache_dir, 0, 0.0)
            return 0
        _FILE_CACHE_COUNT_MEMORY = (cache_dir, entries, mtime)
        return entries


def get_workflow_stats() -> dict[str, Any]:
    """
    获取工作流执行统计信息。

    包含：
    - llm_cache: 生产 LLM 文件缓存统计（entries=当前缓存条目数，
      enabled=缓存开关状态；0.7 P1-1.3 双套缓存漂移消除后，
      进程内 LRU 统计（src/graph/llm_cache，仅测试/嵌入式引用）已随该
      死模块一并删除，统一以文件缓存口径报告）
    - workflow_config: 当前启用的功能开关

    Returns:
        统计信息字典。
    """
    stats: dict[str, Any] = {
        "llm_cache": {"entries": _file_cache_entry_count(), "enabled": _llm_cache_enabled()},
        "workflow_config": {
            "ENABLE_PLANNER": ENABLE_PLANNER,
            "ENABLE_DEBUGGER": ENABLE_DEBUGGER,
            "ENABLE_RAG": ENABLE_RAG,
            "MAX_ITERATIONS": MAX_ITERATIONS,
        },
    }
    # 5.4/5.1 观测层：预算与语义缓存统计（纯读操作，无副作用）
    try:
        from src.agents.semantic_cache import get_semantic_cache_stats
        from src.budget.cost_budget import get_process_budget_stats

        stats["cost_budget"] = get_process_budget_stats()
        stats["semantic_cache"] = get_semantic_cache_stats()
    except Exception:
        logger.debug("get_workflow_stats 预算/语义缓存统计读取失败（保守跳过）", exc_info=True)
    # 15. 多进程缓存协调观测层：本进程视角的 LLM 文件缓存命中率（命中率 < 阈值
    # 时，--parallel 多 worker 各自重读文件 + 重调 LLM，建议"主进程预热缓存
    # + 共享目录"或单进程顺序模式；多进程场景下各 worker 需聚合本进程值）。
    # 仅当本进程确有命中/未命中记录时才附 hit_rate 键（无任何 LLM 调用的纯统计
    # 快照不附带该键，保持既有 get_workflow_stats 口径逐字节不变）。
    try:
        from src.agents.llm_client import get_cache_hit_rate

        _cache_hit_rate = get_cache_hit_rate()
        if _cache_hit_rate is not None:
            stats["llm_cache"]["hit_rate"] = _cache_hit_rate
    except Exception:
        logger.debug("get_workflow_stats 缓存命中率读取失败（保守跳过）", exc_info=True)
    # P1 执行感知可观测性升级：分层缓存命中统计（tiered_cache_stats）。
    # 双套缓存（精确 LRU + 语义向量）口径统一：
    #   - LRU 精确层：record_cache_hit 命中/未命中计数（_lru_lookup 快路径）
    #   - 语义层：SemanticCacheIndex._hits/_misses + 假阳性抽样统计
    # 仅当任一层确有计数时才附该键（零 LLM 调用的纯统计快照不附带，
    # 保持既有 get_workflow_stats 口径逐字节不变——与 llm_cache.hit_rate 同模式）。
    try:
        from src.agents.llm_client import _LLM_CACHE_HIT_STATS, _LLM_CACHE_HIT_STATS_LOCK
        from src.agents.semantic_cache import get_semantic_cache_stats as _get_sem_stats

        # 精确层（LRU + 文件）：hits/misses 经 llm_client._LLM_CACHE_HIT_STATS
        # 累计（record_cache_hit 写入）；此处直接读进程级计数（与
        # stats["llm_cache"]["hit_rate"] 同一口径——hit_rate = file_hits /
        # (file_hits + file_misses)，无记录时 hit_rate=None 且 total=0）
        with _LLM_CACHE_HIT_STATS_LOCK:
            _exact_hits = int(_LLM_CACHE_HIT_STATS.get("file_hits", 0))
            _exact_misses = int(_LLM_CACHE_HIT_STATS.get("file_misses", 0))
        _sem_stats = _get_sem_stats()
        _exact_total = _exact_hits + _exact_misses
        _sem_total = int(_sem_stats.get("hits", 0)) + int(_sem_stats.get("misses", 0))
        if _exact_total > 0 or _sem_total > 0:
            stats["tiered_cache_stats"] = {
                "exact_layer": {
                    "hits": _exact_hits,
                    "misses": _exact_misses,
                    "hit_rate": (round(_exact_hits / _exact_total, 4) if _exact_total else None),
                },
                "semantic_layer": {
                    "enabled": bool(_sem_stats.get("enabled", False)),
                    "hits": int(_sem_stats.get("hits", 0)),
                    "misses": int(_sem_stats.get("misses", 0)),
                    "hit_rate": (round(int(_sem_stats.get("hits", 0)) / _sem_total, 4) if _sem_total else None),
                    # 3.6 假阳性抽样验证统计（SEMANTIC_FALSE_POSITIVE_SAMPLING，
                    # 默认 0.1 = 10%）：命中条目的抽样比对结果，供"语义缓存
                    # 是否真正省了 token"的 A/B 分析消费
                    "fp_checked": int(_sem_stats.get("fp_checked", 0)),
                    "fp_confirmed": int(_sem_stats.get("fp_confirmed", 0)),
                    "fp_false_positive": int(_sem_stats.get("fp_false_positive", 0)),
                    "fp_rate": float(_sem_stats.get("fp_rate", 0.0)),
                },
            }
    except Exception:
        logger.debug("get_workflow_stats 分层缓存统计读取失败（保守跳过）", exc_info=True)
    return stats
