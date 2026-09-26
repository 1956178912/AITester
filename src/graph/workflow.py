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
import threading
from pathlib import Path
from typing import Any

from langgraph.graph import END, StateGraph

from config import ENABLE_DEBUGGER, ENABLE_PLANNER, ENABLE_RAG, MAX_ITERATIONS
from src.agents.llm_client import _llm_cache_dir, _llm_cache_enabled

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
    _record_execution_trace,
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

# 诊断关键词 → "测试生成错误"判定（路由回 generator 的触发词）。
# 2026-09-26 全面审查：从 _should_debug 函数体内提取为模块级常量——
# 此前每次路由调用（每轮迭代）都重建 list 字面量；提取后口径单一来源，
# 后续调整触发词只改一处（与 _MAX_REGENERATIONS 同文件同注释区）。
_TEST_GEN_DIAGNOSIS_KEYWORDS = [
    "测试生成错误",
    "测试设计存在错误",
    "test code",
    "AttributeError",
    "NameError",
    "SyntaxError",
    "测试用例",
    "期望的异常类型",
]


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
    # 与 _recent_repairs_invalid（L210）的 truthiness 口径不一致——若 executor
    # 某路径写入非 bool 的真值（如 numpy.bool_），`is True` 为假 → 误路由 debug。
    # 现统一为 truthiness（与 _recent_repairs_invalid / _executor_node 写入口径
    # 一致：test_passed 由 executor 的 test_result["passed"] 赋值，语义即"测试全过"）。
    if state.get("test_passed"):
        _trace_node("_should_debug", decision="done", output_summary={"reason": "test_passed"})
        return "done"
    # 智能优化：若连续修复无效，直接结束而非继续浪费 token
    # （纯数据判定，日志副作用留在路由层；_recent_repairs_invalid 保持零副作用）
    if _recent_repairs_invalid(state):
        logger.info("连续多次修复无效，跳过 Debugger")
        _trace_node("_should_debug", decision="done", output_summary={"reason": "skip_debugger_repair_invalid"})
        return "done"

    # 3.1 双向诊断：Review Agent 判定为"测试缺陷"时，直接路由回 generator
    # 重新生成测试（分支修复），不进入 debugger 修代码；regeneration_count
    # 上限防止 generator↔executor 无限乒乓（与 diagnosis 关键词路径同口径）。
    # 上限已满且仍判定为测试缺陷：继续修代码无意义（Review Agent 认为代码无
    # 缺陷），直接结束，避免空耗剩余迭代。
    if state.get("defect_type") == "test_defect":
        if state.get("regeneration_count", 0) < _MAX_REGENERATIONS:
            logger.info("双向诊断（3.1）：测试缺陷，路由回 generator 重新生成测试")
            _trace_node("_should_debug", decision="regenerate", output_summary={"reason": "review_test_defect"})
            return "regenerate"
        logger.info("双向诊断（3.1）：已达重新生成上限，结束流程")
        _trace_node("_should_debug", decision="done", output_summary={"reason": "test_defect_regeneration_cap"})
        return "done"

    if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS):
        diagnosis = state.get("diagnosis", "") or ""
        # 若诊断指出失败源于测试代码本身的问题（如 Attribute error、测试预期值错误），
        # 重新生成测试代码而不是放弃
        if any(kw in diagnosis for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS):
            # 上限保护：已再生成过（旧 diagnosis 关键词反复命中）时不再路由 regenerate，
            # 避免 generator↔executor 无限乒乓撞上 recursion_limit
            if state.get("regeneration_count", 0) < _MAX_REGENERATIONS:
                logger.info("诊断表明测试生成错误，触发重新生成测试代码")
                _trace_node("_should_debug", decision="regenerate", output_summary={"reason": "test_gen_diagnosis"})
                return "regenerate"
            logger.info("已达重新生成上限，结束流程")
        _trace_node("_should_debug", decision="done", output_summary={"reason": "max_iterations"})
        return "done"

    # 2026-09-26 全面审查（P1 路由语义澄清）：诊断指向"测试生成错误"时，
    # 此前**只有**达迭代上限（iteration >= max_iterations）才路由 regenerate，
    # 早期迭代（iteration < max）命中关键词仍走 debugger 修代码——与
    # _generator_node 再生成判定（含 defect_type == test_defect 任意迭代可触发）
    # 及 3.1 双向诊断路径口径不一致。现把诊断关键词判定提升为独立分支：
    # 任意 iteration 命中即 regenerate（仍受 regeneration_count 上限保护）；
    # 上限已满时落到下方常规 debug（保守口径：上限保护不变）。
    diagnosis = state.get("diagnosis", "") or ""
    if (
        any(kw in diagnosis for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS)
        and state.get("regeneration_count", 0) < _MAX_REGENERATIONS
    ):
        logger.info("诊断表明测试生成错误（iteration < max），触发重新生成测试代码")
        _trace_node("_should_debug", decision="regenerate", output_summary={"reason": "test_gen_diagnosis_early"})
        return "regenerate"
    # 早期迭代但（关键词未命中或再生成上限已满）：落到下方常规 debug

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
    """统计生产 LLM 文件缓存（src/cache/*.json）当前条目数。

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
    return {
        "llm_cache": {"entries": _file_cache_entry_count(), "enabled": _llm_cache_enabled()},
        "workflow_config": {
            "ENABLE_PLANNER": ENABLE_PLANNER,
            "ENABLE_DEBUGGER": ENABLE_DEBUGGER,
            "ENABLE_RAG": ENABLE_RAG,
            "MAX_ITERATIONS": MAX_ITERATIONS,
        },
    }
