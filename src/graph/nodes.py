"""
工作流节点函数模块。

从 workflow.py 拆分而来（代码可维护性优化）：承载 LangGraph 工作流图的各个
节点实现（Planner / Generator / Executor / Debugger / CrossFileAnalyzer /
PatchApplier）及其辅助函数（路径白名单校验、原子写盘、多候选补丁、Planner
输出校验与默认计划）。图构建与条件路由保留在 workflow.py，通过
`from .nodes import ...` 注册这些节点函数。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from typing import Any

from config import (
    ENABLE_RAG,
    EXECUTION_TIMEOUT,
    EXECUTOR_AUTO_INSTALL_DEPS,
    EXECUTOR_DEP_INSTALL_TIMEOUT,
    EXECUTOR_USE_VENV,
    MAX_ITERATIONS,
)
from src.agents.debugger import DebuggerAgent
from src.agents.executor import ExecutorAgent
from src.agents.generator import GeneratorAgent
from src.agents.planner import PlannerAgent
from src.graph.rag import RAG_MODULE_AVAILABLE, TestCaseRetriever, _build_rag_stat, get_rag_retriever
from src.graph.state import AITesterState
from src.graph.tracing import _trace_node
from src.tools.cross_file import analyze_cross_file_deps, cross_file_enabled
from src.tools.multi_candidate import (
    generate_candidates,
    multi_candidate_available,
    multi_candidate_count,
    multi_candidate_exec_validate,
    select_best_candidate,
)
from src.tools.patch_applier import apply_patch_to_code

# 模块级 logger，用于记录节点执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)

# 修复历史上限：超过后仅保留最近 N 条，防止长迭代循环占用内存（经验值 5）
_MAX_REPAIR_HISTORY = 5


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
    t0 = time.time()
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
        # 复用 _get_default_test_plan（与上方验证失败分支同一构造点）：
        # 其 "or 'unknown'" 兜底比原内联 .get(key, "unknown") 更严格
        # （空串/None 键值也会归一为 "unknown"，语义向成功分支收敛）
        logger.warning("Planner JSON 解析失败，使用默认计划: %s", e)
        test_plan = _get_default_test_plan(state.get("target_function"))
    _trace_node(
        "planner",
        output_summary={
            "function_name": test_plan.get("function_name"),
            "test_cases": len(test_plan.get("test_cases", [])),
        },
        decision="plan_complete",
        duration_ms=(time.time() - t0) * 1000,
    )
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

    # P1：记录本次 RAG 检索的质量指标（命中数/相似度），随状态累计供实验汇总
    update_rag_stat = _build_rag_stat(rag_refs, kind="test_cases")

    # 调用 Generator 生成测试代码
    # 参数说明：
    #   - test_plan: 若启用 Planner 则传入结构化计划，否则为 None（Generator 将自行推断）
    #   - target_code: 被测代码全文，Generator 需要它来理解业务逻辑和生成 import 语句
    #   - module_name: 模块名（不含 .py），用于生成正确的 from X import Y 语句
    #   - rag_references: RAG 检索到的历史案例，用于风格参考（可为 None）
    #   - focus_function: 目标函数名（P0 大文件优化），超长代码时按该函数
    #     做 AST 智能截取，保留目标函数及直接依赖，避免 LLM 看不到完整上下文
    generated_test = agent.generate(
        state.get("test_plan"),  # Planner 节点在图中时必带 test_plan；缺席时为 None，Generator 自行推断
        state["target_code"],
        module_name=state.get("module_name", ""),
        rag_references=rag_refs,
        focus_function=state.get("target_function"),
    )
    # 记录生成结果长度，便于评估 Generator 的输出质量
    logger.info("Generator 完成测试代码生成，长度=%d", len(generated_test))
    _trace_node(
        "generator",
        output_summary={"generated_test_len": len(generated_test)},
        decision="regenerated"
        if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        else "generated",
    )
    update: dict[str, Any] = {
        "generated_test": generated_test,
        "rag_references": rag_refs,
    }
    # 累计 RAG 检索指标（本节点读取后携带历史值，避免后续节点覆盖丢失）
    if update_rag_stat:
        update["rag_stats"] = list(state.get("rag_stats") or []) + [update_rag_stat]
    # 再生成路径检测：首次生成时 iteration < max_iterations（尚未进入修复循环），
    # 只有 _should_debug 路由 "regenerate"（此时 iteration >= max_iterations）才会带着
    # 高 iteration 回到 generator。据此区分两类进入方式：
    #   - 首次生成：不改变 regeneration_count，保留原有 diagnosis（尚无修复结论）
    #   - 再生成：计数 +1（供 _should_debug 上限判断），并清空上一轮诊断，
    #     避免旧的 diagnosis 关键词在新测试仍失败时再次触发 regenerate（死循环根因）
    if state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS):
        update["regeneration_count"] = state.get("regeneration_count", 0) + 1
        update["diagnosis"] = None
        update["error_category"] = None
    return update


def _executor_node(state: AITesterState) -> dict[str, Any]:
    """
    ExecutorAgent 节点：执行测试并记录结果。
    测试通过后自动入库（若 RAG 可用且已启用），供后续检索使用。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含 test_passed, test_output, coverage_report, failed_cases。

    超时优先级：state["execution_timeout"]（CLI --timeout 注入）> config.EXECUTION_TIMEOUT。
    此前直接读环境变量原始值，绕过了 config 的范围校验（_validate_timeout），
    导致 CLI --timeout 不生效且非法配置（如 0s）未被兜底。
    """
    # CLI 通过 state 注入的执行超时优先，未注入时回退到 config 中已校验的值
    executor_timeout = int(state.get("execution_timeout") or EXECUTION_TIMEOUT)
    t0 = time.time()
    # 隔离沙箱参数（P1 依赖隔离）：默认关闭，保持与历史实验一致；
    # 通过环境变量 EXECUTOR_USE_VENV / EXECUTOR_AUTO_INSTALL_DEPS 开启
    agent = ExecutorAgent(
        timeout=executor_timeout,
        use_docker=False,
        use_venv=EXECUTOR_USE_VENV,
        auto_install_deps=EXECUTOR_AUTO_INSTALL_DEPS,
        dep_install_timeout=EXECUTOR_DEP_INSTALL_TIMEOUT,
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
    _trace_node(
        "executor",
        output_summary={
            "passed": result["passed"],
            "coverage": result["coverage"],
            "failed_cases": len(result["failed_cases"]),
        },
        decision=status,
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
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
    t0 = time.time()

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
            focus_function=state.get("target_function"),
            target_module=state.get("module_name"),
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
    _trace_node(
        "debugger",
        output_summary={
            "error_category": result.get("error_category"),
            "root_cause": result.get("root_cause", "")[:200],
            "patch_len": len(result.get("patch", "")),
        },
        decision=result.get("error_category", "unknown"),
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
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

    update = {
        "diagnosis": result["root_cause"],
        "error_category": result.get("error_category", "unknown"),
        "patch": result["patch"],
    }
    # 累计 RAG 修复检索指标（P1）
    repair_stat = _build_rag_stat(rag_refs, kind="repairs")
    if repair_stat:
        update["rag_stats"] = list(state.get("rag_stats") or []) + [repair_stat]
    return update


def _is_within_allowed_roots(path: str, roots: tuple[str, ...]) -> bool:
    """判断文件路径是否位于任一允许根目录之内（含根目录自身）。

    前缀比较必须带上 os.sep，否则 AITester_backup/ 这类兄弟目录会因
    startswith(project_root) 命中而绕过白名单（前缀碰撞）。

    用 realpath 归一化两侧：macOS 上 /var 是 /private/var 的符号链接，
    pytest 的 tmp_path 与 tempfile.gettempdir() 一侧带 /private 一侧不带，
    abspath 会失配；realpath 统一解析符号链接后再比较。

    Args:
        path: 待校验的文件路径。
        roots: 允许的根目录元组。

    Returns:
        True 表示路径位于某根目录内（或即根目录本身）。
    """
    abs_path = os.path.realpath(path)
    for root in roots:
        root_abs = os.path.realpath(root).rstrip(os.sep)
        if abs_path == root_abs or abs_path.startswith(root_abs + os.sep):
            return True
    return False


def _cross_file_analyzer_node(state: AITesterState) -> dict[str, Any]:
    """3.5 跨文件修复：分析被测代码的跨文件依赖关系（CROSS_FILE_ENABLE=true 时启用）。

    流程：
        1. 从 state["target_code"] 提取源码；
        2. 调用 analyze_cross_file_deps 做 AST 依赖分析（entry → target 的 import 关系）；
        3. 把依赖边列表写入 state["cross_file_deps"]（供后续节点 / 报告使用）；
        4. 若依赖图为空（单文件项目），写入空列表并降级为单文件模式
           （cross_file_plan 置 None，后续 patch_applier 走单文件路径）。

    设计约束：
        - 默认关闭（CROSS_FILE_ENABLE=false），启用时需显式设置环境变量；
        - 单文件项目自动降级（依赖边为空时 cross_file_plan 保持 None）；
        - 节点不直接生成补丁，仅做"协调器"角色（依赖分析 + 路由决策），
          补丁生成仍由现有 _debugger_node 完成（提议者角色），保持 LLM 调用路径不变。

    Args:
        state: 当前工作流状态（含 target_code / target_file / module_name 等字段）。

    Returns:
        更新后的状态字典，包含 cross_file_deps（依赖边列表，可为空）。
    """
    t0 = time.time()
    entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
    target_code = state.get("target_code", "")

    # 保守实现：当前仅分析 entry_module 自身的 import 关系（单入口视角），
    # 不递归展开调用方的 import（避免依赖图爆炸）。完整多入口分析留作二期。
    source_files: dict[str, str] = {}
    if entry_module:
        source_files[entry_module] = target_code
    # 若有其他模块内容（未来扩展），在此追加到 source_files

    deps = analyze_cross_file_deps(entry_module=entry_module, source_files=source_files)
    _trace_node(
        "cross_file_analyzer",
        output_summary={
            "entry_module": entry_module,
            "dep_edges": len(deps),
        },
        decision="deps_found" if deps else "single_file_fallback",
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    update: dict[str, Any] = {"cross_file_deps": [d.__dict__ for d in deps]}
    # 单文件项目降级：依赖边为空时不生成跨文件计划（保持单文件路径）
    if not deps:
        logger.info("3.5 跨文件修复：依赖图为空（单文件项目），降级为单文件模式")
        update["cross_file_plan"] = None
    else:
        logger.info("3.5 跨文件修复：发现 %d 条跨文件依赖边", len(deps))
        # 完整修复计划由 _debugger_node 后续生成（协调器-提议者：提议者=debugger）
        update["cross_file_plan"] = None  # 占位，待二期实现完整计划构建
    return update


def _write_file_atomic(path: str, content: str) -> None:
    """先写临时文件再 os.replace 原子替换目标文件。

    直接 open(path, "w") 会先截断再写，中途崩溃会留下被截断的用户源文件；
    原子替换保证任何时刻目标文件要么是旧内容、要么是完整新内容。

    Args:
        path: 目标文件路径。
        content: 要写入的完整内容。
    """
    directory = os.path.dirname(path) or "."
    fd, tmp_path = tempfile.mkstemp(suffix=".tmp", prefix=".aitester_", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, path)
    except BaseException:
        # 失败时清理临时文件，避免残留；再把异常抛给调用方
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _select_multi_candidate_patch(state: AITesterState, original_code: str) -> tuple[str, bool]:
    """3.1 多候选补丁：生成 N 候选 + 静态筛选 + 执行验证，返回最优候选。

    无有效候选（全静态拒绝 / 执行全失败）时回退到 state 中的单补丁，
    保证多候选策略不会比原单补丁路径更差（只多不少）。

    执行验证开关：环境变量 MULTI_CANDIDATE_EXEC_VALIDATE=true 时启用
    逐候选跑测试（成本更高但筛选更准），默认关闭走纯静态筛选。

    Args:
        state: 当前工作流状态（含 target_code / generated_test / failed_cases /
            target_function / module_name 等字段）。
        original_code: 本轮修复的原始被测代码。

    Returns:
        (最优候选应用后的代码, 是否成功应用)。回退单补丁时与原
        apply_patch_to_code 同口径。
    """
    from src.agents.debugger import DebuggerAgent
    from src.agents.executor import ExecutorAgent

    n = multi_candidate_count()
    debugger = DebuggerAgent()
    candidates = generate_candidates(
        debugger=debugger,
        target_code=original_code,
        test_output=state.get("test_output", ""),
        failed_cases=state.get("failed_cases", []) or [],
        num_candidates=n,
        focus_function=state.get("target_function"),
        target_module=state.get("module_name"),
    )
    use_exec = multi_candidate_exec_validate()
    executor = ExecutorAgent(timeout=EXECUTION_TIMEOUT, use_venv=EXECUTOR_USE_VENV) if use_exec else None
    best = select_best_candidate(
        candidates=candidates,
        original_code=original_code,
        test_code=state.get("generated_test"),
        target_file=state.get("target_file"),
        target_function=state.get("target_function"),
        use_execution_validation=use_exec,
        executor=executor,
    )
    _trace_node(
        "multi_candidate",
        output_summary={
            "candidates": len(candidates),
            "static_passed": sum(1 for c in candidates if c.static_passed),
            "exec_validated": use_exec,
            "selected": (best.index if best else None),
        },
        decision=f"selected_{best.index + 1}" if best else "fallback_single",
        iteration=state.get("iteration", 0),
    )
    if best is None:
        # 多候选全部失败 → 回退到单补丁（保持历史行为，不引入劣化）
        logger.info("多候选无有效补丁，回退到单补丁流程")
        return apply_patch_to_code(original_code=original_code, patch=state.get("patch", ""))
    return apply_patch_to_code(original_code=original_code, patch=best.patch)


def _patch_applier_node(state: AITesterState) -> dict[str, Any]:
    """
    补丁应用节点：将 Debugger 生成的补丁应用到被测代码，并写回文件。
    应用后更新 iteration 计数器，供下次循环使用。

    状态/磁盘一致性：只有当补丁真正写入磁盘成功时，才把 target_code 更新为
    新代码并记录 patch_applied=True；任何一道安全检查（空/过短/无函数定义/
    路径不合法）拒绝写入时，target_code 保持原代码、patch_applied 记 False，
    避免下游 Executor 测旧文件、Debugger 却分析新代码的"幻象迭代"。

    Args:
        state: 当前状态。

    Returns:
        更新后的状态字典，包含更新后的 target_code 和修复历史。
    """
    original_code = state["target_code"]

    # ── 3.1 多候选补丁分支（ENABLE_MULTI_CANDIDATE_PATCH=true 时启用）──
    # 默认关闭，保持历史单补丁口径。开启时：生成 N 个候选 → 静态筛选 →
    # （可选）执行验证 → 选最优候选作为本轮补丁。任一环节无有效候选时
    # 回退到 state 中已有的单补丁（state["patch"]），不引入劣化。
    # ── 3.5 跨文件修复：cross_file_deps 非空时走多文件补丁路径 ─────────────
    new_code: str
    applied: bool
    cross_file_deps = state.get("cross_file_deps") or []
    if cross_file_deps and cross_file_enabled():
        # 3.5 跨文件修复分支：按依赖图拓扑序对多个模块应用补丁
        from src.tools.cross_file import apply_multi_file_patch, cross_file_fallback_single_file

        # 从 state 收集所有模块的原始代码（当前仅 target_code 可用；
        # 二期扩展后从 source_files 字典读取）
        entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
        original_files = {entry_module: original_code}
        # 多文件补丁：entry_module 用 state["patch"]（当前单补丁路径生成），
        # 其他模块的补丁由 _debugger_node 后续生成（二期）
        patches: dict[str, str] = {}
        if state.get("patch"):
            patches[entry_module] = state["patch"]
        # 尝试多文件应用；失败时降级为单文件
        new_files, applied = apply_multi_file_patch(original_files, patches, entry_module)
        new_code = new_files.get(entry_module, original_code)
        if not applied:
            # 多文件失败 → 降级单文件（保守口径，不引入劣化）
            logger.info("3.5 跨文件补丁应用失败，降级单文件模式")
            # 注意：cross_file_fallback_single_file 返回 (新文件映射, 成功)，
            # 需再取 entry_module 的代码字符串——此前误把整个映射当 new_code，
            # len(dict) 恒为 1，降级补丁永远卡在"过短"安全检查、永远写不进盘
            fallback_files, applied = cross_file_fallback_single_file(original_files, patches, entry_module)
            new_code = fallback_files.get(entry_module, original_code)
    elif multi_candidate_available():
        new_code, applied = _select_multi_candidate_patch(state, original_code)
    else:
        new_code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch", ""))

    # 默认视为"未真正写盘"，任何安全检查失败都保持该值
    written = False
    if applied and new_code != original_code:
        # 安全检查 1：补丁不能是空字符串或比原代码短得多（防止 LLM 返回空文件）
        if not new_code or len(new_code) < len(original_code) * 0.1:
            logger.error("补丁内容异常（空或过短），跳过写入: %s", state["target_file"])
        # 安全检查 2：补丁必须含至少一个函数定义（防止 LLM 返回无意义内容）
        elif not any(line.strip().startswith("def ") for line in new_code.splitlines()):
            logger.error("补丁不含任何函数定义，跳过写入: %s", state["target_file"])
        else:
            target_file_path = os.path.abspath(state["target_file"])
            project_root = os.path.abspath(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            temp_dir = os.path.abspath(tempfile.gettempdir())
            # 允许项目目录内或系统临时目录（前缀比较带 os.sep，防兄弟目录碰撞）
            if not _is_within_allowed_roots(target_file_path, (project_root, temp_dir)):
                logger.error("非法文件路径，拒绝写入: %s", state["target_file"])
            else:
                # 原子写入：写临时文件后 os.replace，崩溃不损坏用户源文件
                _write_file_atomic(target_file_path, new_code)
                written = True
                logger.info("补丁已应用到文件: %s", target_file_path)

    # 状态/磁盘一致性：仅写盘成功才更新 target_code，否则保留原代码
    effective_code = new_code if written else original_code

    history = state.get("repair_history", []) or []
    history.append(
        {
            "iteration": state.get("iteration", 0) + 1,
            "diagnosis": state.get("diagnosis", ""),
            "error_category": state.get("error_category", "unknown"),
            "patch_applied": written,
        }
    )
    # 限制 repair_history 大小，避免无限增长占用内存（最多保留 _MAX_REPAIR_HISTORY 条）
    if len(history) > _MAX_REPAIR_HISTORY:
        history = history[-_MAX_REPAIR_HISTORY:]
    _trace_node(
        "patch_applier",
        output_summary={"patch_applied": written, "new_code_len": len(effective_code)},
        decision="written" if written else "rejected",
        iteration=state.get("iteration", 0),
    )
    return {
        "target_code": effective_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
    }


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
