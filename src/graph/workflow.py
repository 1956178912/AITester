"""
LangGraph 工作流编排模块：定义多智能体协作的工作流图和执行路由逻辑。

本模块是 AITester 系统的"中枢神经系统"，负责：
1. 根据消融实验开关动态构建有向图（StateGraph）
2. 实现节点间的条件路由（通过测试？达到最大迭代？重新生成？）
3. 协调 Planner → Generator → Executor → Debugger → PatchApplier 的循环修复流程
4. 集成 RAG 检索增强，在生成和修复阶段注入历史案例参考

工作流程（完整版）：
    Planner → Generator → Executor → (Debugger → PatchApplier) × N → END

工作流程（消融模式 - 无 Planner）：
    Generator → Executor → (Debugger → PatchApplier) × N → END

工作流程（消融模式 - 无 Debugger）：
    Planner → Generator → Executor → END

工作流程（消融模式 - 无 Planner/Debugger）：
    Generator → Executor → END  （纯 LLM 基线）

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

import json
import logging
import os
import threading
from typing import Any

from langgraph.graph import END, StateGraph

from config import (
    ENABLE_DEBUGGER,
    ENABLE_PLANNER,
    ENABLE_RAG,
    MAX_ITERATIONS,
)
from src.agents.debugger import DebuggerAgent
from src.agents.executor import ExecutorAgent
from src.agents.generator import GeneratorAgent
from src.agents.planner import PlannerAgent
from src.graph.llm_cache import get_cache_stats
from src.graph.state import AITesterState
from src.tools.patch_applier import apply_patch_to_code

# 模块级 logger，用于记录工作流执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)

# 可选导入 RAG 检索器（未安装 chromadb 时优雅降级，不影响主流程）
# 使用延迟导入而非 top-level import，避免 chromadb 未安装时整个项目无法启动
try:
    from src.rag.retriever import TestCaseRetriever

    RAG_MODULE_AVAILABLE = True
except ImportError:
    RAG_MODULE_AVAILABLE = False
    TestCaseRetriever = None
    logger.info("RAG 模块未就绪（chromadb 未安装），将跳过检索增强")

# 最大修复迭代次数常量（来自 config.py），控制 Debugger 循环的上限
# 避免 LLM 反复生成相同错误补丁导致无限循环
_DEFAULT_MAX_ITERATIONS = 3

# ─── RAG 检索器单例 ────────────────────────────────────────────────────────────
# _rag_retriever 模块级缓存：避免每次节点调用都重新初始化 ChromaDB 客户端
# ChromaDB 客户端初始化涉及模型加载和向量存储打开，耗时 2-6 秒
# 单例化后整个工作流执行期间只初始化一次
_rag_retriever = None
# 线程锁：保护单例初始化的双重检查锁定，确保多线程环境下的安全性
_rag_lock = threading.Lock()


def get_rag_retriever():
    """
    获取 RAG 检索器单例实例（线程安全版本）。

    使用双重检查锁定模式（Double-Checked Locking）：
    - 第一次检查（无锁）：若已初始化直接返回，避免后续调用的锁开销
    - 加锁后第二次检查：防止多线程并发时多次初始化

    保证 ChromaDB 客户端在整个工作流执行期间只初始化一次，
    避免每个节点都创建新实例导致的 2-6 秒重复初始化开销。

    Returns:
        TestCaseRetriever 实例。若 RAG 模块不可用则返回 None。
    """
    global _rag_retriever
    # 第一次检查：无锁快速路径，已初始化时直接返回
    if _rag_retriever is not None:
        return _rag_retriever
    # 加锁进行二次检查和初始化
    with _rag_lock:
        # 第二次检查：防止多线程并发时多次初始化
        if _rag_retriever is None and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
            try:
                _rag_retriever = TestCaseRetriever()
                logger.info("RAG 检索器单例已初始化")
            except Exception as e:
                logger.warning("RAG 检索器初始化失败，将跳过 RAG 增强: %s", e)
                _rag_retriever = None  # 标记为不可用，避免重复尝试
    return _rag_retriever


def _create_workflow() -> StateGraph:
    """
    构建多智能体工作流图（有向无环图 + 条件循环）。

    核心设计思路：
    - 使用 LangGraph 的 StateGraph 作为图编排引擎，每个节点是一个 Python 函数
    - 根据 config.py 中的消融开关动态选择启用的节点和边
    - Debugger + PatchApplier 构成循环结构，通过 _should_debug 条件路由控制是否继续迭代

    消融开关说明：
    - ENABLE_PLANNER=True  → 包含 Planner 节点（逻辑驱动思维链）
    - ENABLE_DEBUGGER=True → 包含 Debugger + PatchApplier 修复循环
    - ENABLE_RAG=True      → Generator/Debugger 节点中使用 RAG 检索增强

    Returns:
        已注册的 StateGraph 实例（尚未编译，需调用 .compile() 后才能运行）。
        编译后返回 Runnable 对象，可通过 .invoke() 执行完整流程。
    """
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
    if ENABLE_PLANNER:
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
    if ENABLE_DEBUGGER:
        # 添加调试节点和补丁应用节点，构成修复循环
        workflow.add_node("debugger", _debugger_node)
        workflow.add_node("patch_applier", _patch_applier_node)

        # 条件边：Executor 完成后，根据 _should_debug 返回值决定下一步
        # 返回 "debug"   → 进入 Debugger 进行根因分析和补丁生成
        # 返回 "done"     → 直接结束工作流（测试通过或达到最大迭代）
        # 返回 "regenerate" → 回到 Generator 重新生成测试代码
        workflow.add_conditional_edges(
            "executor",
            _should_debug,
            {
                "debug": "debugger",  # 需要修复时进入 debugger
                "done": END,  # 测试通过或达到最大迭代时结束
                "regenerate": "generator",  # 测试生成错误时重新生成测试代码
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
        return "done"
    # 智能优化：若连续修复无效，直接结束而非继续浪费 token
    if _should_skip_debugger(state):
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
            logger.info("诊断表明测试生成错误，触发重新生成测试代码")
            return "regenerate"
        return "done"
    return "debug"


# ─── 节点函数定义 ────────────────────────────────────────────────────────────


def _planner_node(state: AITesterState) -> dict[str, Any]:
    """
    PlannerAgent 节点：生成逻辑驱动的结构化测试计划。

    优化：添加输出验证，确保 Planner 返回符合预期的 JSON 结构。
    若验证失败，使用默认计划兜底。

    这是工作流的第一个节点（当 ENABLE_PLANNER=True 时），负责：
    1. 调用 PlannerAgent 对被测代码进行逻辑分析（输入域/输出域/前置-后置条件/边界情况）
    2. 生成包含 logic_analysis 和 test_cases 的结构化测试计划 JSON
    3. 若 LLM 返回格式不良的 JSON，使用默认计划兜底，确保工作流不中断

    设计考虑：
    - 使用 try-except 捕获 LLM 调用失败，避免单点故障导致整个流程崩溃
    - 验证输出结构，确保包含必需的字段（function_name, logic_analysis）
    - 默认计划包含空逻辑分析，下游 Generator 仍可基于目标代码生成测试

    Args:
        state: 当前状态，包含 target_code（被测代码）和 target_function（可选的目标函数名）。

    Returns:
        更新后的状态字典，包含 test_plan 字段（PlannerAgent 输出的测试计划）。
    """
    agent = PlannerAgent()
    try:
        # 调用 Planner 生成测试计划，传入被测代码和可选的目标函数名
        # 若指定了 target_function，Planner 将只分析该函数，缩小分析范围
        test_plan = agent.plan(state["target_code"], state.get("target_function"))
        # 验证输出结构
        if not _validate_planner_output(test_plan):
            logger.warning("Planner 输出结构不完整，使用默认计划")
            test_plan = _get_default_test_plan(state.get("target_function"))
        logger.info("Planner 完成规划，函数=%s", test_plan.get("function_name", "unknown"))
    except (json.JSONDecodeError, RuntimeError) as e:
        # LLM 调用失败或返回非 JSON 格式时，使用默认计划兜底
        # 这确保了即使 LLM 服务异常，工作流仍可以继续执行（降级模式）
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


def _generator_node(state: AITesterState) -> dict[str, Any]:
    """
    GeneratorAgent 节点：根据测试计划生成 pytest 测试代码。

    本节点的核心职责：
    1. 若 RAG 已启用，先检索相似历史测试用例作为风格参考（检索增强）
    2. 调用 GeneratorAgent 生成完整的 pytest 测试代码字符串
    3. 记录生成结果的长度，便于后续分析和调试

    设计考虑：
    - RAG 检索失败时静默跳过（logger.warning），不影响主流程
    - 若 ENABLE_PLANNER=False，传入 None 作为 test_plan，Generator 将基于裸代码生成

    Args:
        state: 当前状态，包含 test_plan（可选）、target_code、module_name 等字段。

    Returns:
        更新后的状态字典，包含 generated_test（测试代码字符串）和 rag_references（RAG 参考列表）。
    """
    agent = GeneratorAgent()

    # 初始化 RAG 参考列表为 None（默认不使用检索增强）
    rag_refs: list | None = None
    # 仅当 RAG 开关开启、模块可用、且存在失败用例时才进行检索
    if ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
        try:
            # 使用单例检索器，避免重复初始化 ChromaDB 客户端
            retriever = get_rag_retriever()
            if retriever is not None:
                # top_k=3 是经验值：太多会增加 prompt 长度，太少可能缺乏代表性
                rag_refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
                logger.info("RAG 检索到 %d 个相似测试用例", len(rag_refs) if rag_refs else 0)
        except Exception as e:
            # RAG 检索失败时记录警告但不中断流程，Generator 仍可使用无 RAG 模式生成
            logger.warning("RAG 检索失败，跳过增强: %s", e)

    # 调用 Generator 生成测试代码
    # 参数说明：
    #   - test_plan: 若启用 Planner 则传入结构化计划，否则为 None（Generator 将自行推断）
    #   - target_code: 被测代码全文，Generator 需要它来理解业务逻辑和生成 import 语句
    #   - module_name: 模块名（不含 .py），用于生成正确的 from X import Y 语句
    #   - rag_references: RAG 检索到的历史案例，用于风格参考（可为 None）
    generated_test = agent.generate(
        state["test_plan"] if ENABLE_PLANNER else None,
        state["target_code"],
        module_name=state.get("module_name", ""),
        rag_references=rag_refs,
    )
    # 记录生成结果长度，便于评估 Generator 的输出质量
    logger.info("Generator 完成测试代码生成，长度=%d", len(generated_test))
    return {
        "generated_test": generated_test,
        "rag_references": rag_refs,
    }


def _executor_node(state: AITesterState) -> dict[str, Any]:
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
            # 使用单例检索器入库成功测试用例
            retriever = get_rag_retriever()
            if retriever is not None:
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


def _debugger_node(state: AITesterState) -> dict[str, Any]:
    """
    DebuggerAgent 节点：分析失败原因并生成分层修复补丁。
    若 RAG 可用且已启用，检索相似历史修复案例作为参考。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 diagnosis, error_category, patch。
    """
    agent = DebuggerAgent()

    rag_refs: list | None = None
    if ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None and state.get("failed_cases"):
        try:
            error_cat = state.get("error_category", "unknown")
            # 使用单例检索器
            retriever = get_rag_retriever()
            if retriever is not None:
                rag_refs = retriever.retrieve_repairs(
                    error_category=error_cat,
                    target_code=state["target_code"],
                    top_k=2,
                )
                logger.info("RAG 检索到 %d 个相似修复案例", len(rag_refs) if rag_refs else 0)
        except Exception as e:
            logger.warning("RAG 检索失败，跳过增强: %s", e)

    try:
        result = agent.debug(
            target_code=state["target_code"],
            test_output=state.get("test_output", ""),
            failed_cases=state.get("failed_cases", []) or [],
            rag_references=rag_refs,
        )
    except (json.JSONDecodeError, RuntimeError) as e:
        logger.warning("Debugger JSON 解析失败，跳过本轮修复: %s", e)
        result = {
            "root_cause": f"JSON 解析失败: {e}",
            "error_category": "unknown",
            "fix_strategy": "",
            "patch": "",
        }
    logger.info(
        "Debugger 完成第 %d 轮修复：类别=%s，根因=%s",
        state.get("iteration", 0) + 1,
        result.get("error_category", "unknown"),
        result.get("root_cause", "")[:80],
    )

    if ENABLE_RAG and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
        try:
            # 使用单例检索器入库修复案例
            retriever = get_rag_retriever()
            if retriever is not None:
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


def _patch_applier_node(state: AITesterState) -> dict[str, Any]:
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
        # 安全检查：补丁不能是空字符串或比原代码短得多（防止 LLM 返回空文件）
        if not new_code or len(new_code) < len(state["target_code"]) * 0.1:
            logger.error("补丁内容异常（空或过短），跳过写入: %s", state["target_file"])
        elif not any(line.strip().startswith("def ") for line in new_code.splitlines()):
            logger.error("补丁不含任何函数定义，跳过写入: %s", state["target_file"])
        else:
            # 安全检查：验证目标文件路径合法性，防止路径穿越攻击
            import os
            import tempfile

            target_file_path = os.path.abspath(state["target_file"])
            project_root = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            temp_dir = os.path.abspath(tempfile.gettempdir())
            # 允许项目目录内或系统临时目录
            allowed_prefixes = [project_root, temp_dir]
            if not any(target_file_path.startswith(prefix) for prefix in allowed_prefixes):
                logger.error("非法文件路径，拒绝写入: %s", state["target_file"])
            else:
                with open(target_file_path, "w", encoding="utf-8") as f:
                    f.write(new_code)
                logger.info("补丁已应用到文件: %s", target_file_path)

    history = state.get("repair_history", []) or []
    history.append(
        {
            "iteration": state.get("iteration", 0) + 1,
            "diagnosis": state.get("diagnosis", ""),
            "error_category": state.get("error_category", "unknown"),
            "patch_applied": applied,
        }
    )
    # 限制 repair_history 大小，避免无限增长占用内存（最多保留 5 条）
    _MAX_REPAIR_HISTORY = 5
    if len(history) > _MAX_REPAIR_HISTORY:
        history = history[-_MAX_REPAIR_HISTORY:]
    return {
        "target_code": new_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
    }


# ─── 辅助函数：Planner 输出验证 ────────────────────────────────────────────────


def _validate_planner_output(test_plan: dict[str, Any]) -> bool:
    """
    验证 Planner 输出是否符合预期结构。

    检查必需字段：function_name 和 logic_analysis。

    Args:
        test_plan: PlannerAgent 输出的测试计划字典。

    Returns:
        True 表示结构完整，False 表示需要降级使用默认计划。
    """
    if not isinstance(test_plan, dict):
        return False
    # 必需字段检查
    required_keys = ["function_name", "logic_analysis"]
    for key in required_keys:
        if key not in test_plan:
            logger.warning("Planner 输出缺少必需字段: %s", key)
            return False
    # logic_analysis 内部结构验证
    la = test_plan.get("logic_analysis", {})
    if not isinstance(la, dict):
        return False
    return True


def _get_default_test_plan(function_name: str | None) -> dict[str, Any]:
    """
    生成默认测试计划（降级方案）。

    Args:
        function_name: 目标函数名。

    Returns:
        默认测试计划字典。
    """
    return {
        "function_name": function_name or "unknown",
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


# ─── 工作流编译与缓存 ──────────────────────────────────────────────────────────


def build_workflow() -> Any:
    """
    编译工作流图并返回可执行的 graph 对象。
    每次调用都创建新的 graph 实例，避免状态污染。

    Returns:
        编译后的 LangGraph StateGraph 对象。
    """
    workflow = _create_workflow()
    return workflow.compile()


def get_workflow_stats() -> dict[str, Any]:
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
