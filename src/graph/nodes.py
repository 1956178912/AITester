"""
工作流节点函数模块。

从 workflow.py 拆分而来（代码可维护性优化）：承载 LangGraph 工作流图的各个
节点实现（Planner / Generator / Executor / Debugger / CrossFileAnalyzer /
PatchApplier）及其辅助函数（路径白名单校验、原子写盘、多候选补丁、Planner
输出校验与默认计划）。图构建与条件路由保留在 workflow.py，通过
`from .nodes import ...` 注册这些节点函数。
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import asdict
from typing import Any, cast

from config import (
    ENABLE_RAG,
    EXECUTION_TIMEOUT,
    EXECUTOR_AUTO_INSTALL_DEPS,
    EXECUTOR_DEP_INSTALL_TIMEOUT,
    EXECUTOR_DOCKER_IMAGE,
    EXECUTOR_USE_DOCKER,
    EXECUTOR_USE_VENV,
    MAX_ITERATIONS,
    TEMPERATURE,
)
from src.agents.debugger import DebuggerAgent
from src.agents.executor import ExecutorAgent
from src.agents.generator import GeneratorAgent, _repro_test_enabled
from src.agents.planner import PlannerAgent
from src.graph.cost_budget import BudgetExceededError
from src.graph.event_bus import (
    PlanGenerated,
    publish_debugger_diagnosed,
    publish_event,
    publish_patch_applied,
    publish_tests_executed,
)
from src.graph.rag import (
    RAG_MODULE_AVAILABLE,
    TestCaseRetriever,
    _build_rag_stat,
    get_rag_retriever,
    rag_guarded,
)
from src.graph.state import AITesterState
from src.graph.tracing import _trace_node
from src.tools.cross_file import analyze_multi_entry_deps, cross_file_enabled
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

# P0 3.2 多候选自适应触发的"困难错误类别"（断言/运行时/逻辑/下标错误才值得
# 多候选；简单任务保持单候选省 token）。模块级 frozenset（此前在函数内每次
# 调用重建 set，--parallel 多任务热路径累积无谓分配）
_HARD_ERROR_CATEGORIES = frozenset({"assertion", "runtime", "logic_error", "index_error"})

# P0 1.1 分层代码压缩：调用链展开层数（与 BaseAgent.truncate_code 同口径，
# CODE_FOCUS_DEPTH 环境变量，默认 1；跨文件任务建议 2）
CODE_FOCUS_DEPTH: int = int(os.getenv("CODE_FOCUS_DEPTH", "1"))


def _patch_resample_enabled() -> bool:
    """2.2 改进：补丁后处理重采样开关（PATCH_RESAMPLE_ENABLE=true 时启用，默认 false）。

    启用后 _patch_applier_node 在应用失败时触发 apply_patch_with_resample
    （AST 验证 + 负面反馈重采样，最多 PATCH_RESAMPLE_MAX 次），仍失败则
    把该轮标记为 patch_syntax_invalid（refine_failure_category 消费）。
    默认关闭保持历史单补丁口径（不产生额外 LLM 调用）。
    """
    return os.getenv("PATCH_RESAMPLE_ENABLE", "false").lower() == "true"


def _patch_resample_max() -> int:
    """2.2 改进：重采样上限（PATCH_RESAMPLE_MAX，默认 2，与 2.2 口径一致）。

    上限 0/负数视为 0（单次应用即放弃，等价历史口径）；上限过高时钳到 5
    （防止 LLM token 空烧，--parallel 场景累积）。
    """
    try:
        n = int(os.getenv("PATCH_RESAMPLE_MAX", "2"))
    except ValueError:
        n = 2
    return max(0, min(n, 5))


def _patch_resample_temperature() -> float | None:
    """2.2 改进：重采样 LLM 温度（1.3 降级链档位温度优先；未读到时 None →
    沿用 config.TEMPERATURE 默认口径）。

    读 patch_applier._current_context_tier() 的档位温度——被符号守卫拒绝
    后自动降级到的档位（0.2/0.1/0.0），越严档位温度越低，重采样也按该
    温度走（与"降级层用更严格采样"的 1.3 口径一致）。
    """
    try:
        from src.tools.patch_applier import _current_context_tier

        _name, _idx, temp = _current_context_tier()
        return temp
    except Exception:
        return None


def _context_tier_downgrade_enabled() -> bool:
    """1.3 改进：分层压缩降级链开关（CONTEXT_TIER_DOWNGRADE_ENABLE=true 时
    启用，默认 false）。

    启用后 _patch_applier_node 的命名契约守卫拒绝补丁时，调
    advance_context_tier() 推进档位并把 (档位名, 缺失符号) 写入
    state["_1_3_contract_feedback"]——下一轮 _debugger_node 读到该反馈
    后按"更高约束"的上下文（补丁配方保留 / 签名+import 极简）+ 更低温度
    重新生成。默认关闭时仅记录缺失符号（state["_1_3_contract_missing"]），
    不动档位（保持历史单补丁口径）。
    """
    return os.getenv("CONTEXT_TIER_DOWNGRADE_ENABLE", "false").lower() == "true"


# 安全检查 2 用：函数定义探测正则（re 编译缓存命中，热路径零编译开销）。
# 锚定行首（含缩进行）后的 `def `，与旧的"逐行 startswith('def ')"语义等价
# （行内首 token 非 def 的注释/docstring 不命中，避免误判）。
# 2026-09-26 round8 修正（graph 子代理 P1）：补 `(?:async\s+)?` 前缀，与
# patch_applier._TOP_DEF_RE / _find_function_range_ast / 单函数模式按名正则
# （round7 P2-2/P2-3/P2-4 已统一含 async）同口径——此前 async-only 被测
# 模块（目标代码与 LLM 补丁片段仅含 async def）会被安全检查 2 误判"无
# 函数定义"拒写盘 → target_code 永不更新 → 修复循环空烧 token 不收敛。
# 默认行为不变：同步 def 为主的默认数据集命中口径不变，仅 async-only 边界
# 场景由"误拒"变"正确接受"。
_HAS_FUNC_DEF_RE = re.compile(r"^\s*(?:async\s+)?def ", re.MULTILINE)

# 安全检查 3 用：路径白名单根（项目根目录 + 系统临时目录），模块加载期
# 归一化一次。此前每次补丁应用都现场算 4 层 dirname + 3 次 realpath，
# --parallel 多任务累积为重复的 stat/lstat 系统调用。
# 两侧统一 realpath 归一（realpath 内部已含 abspath 语义，旧实现外层再包一层
# abspath 属冗余已去除）；macOS /var→/private/var 符号链接场景下 realpath
# 归一是白名单判定正确性的关键（见 _is_within_allowed_roots 说明）。
# realpath 结果进程内稳定（符号链接不变），加载期归一化一次，
# 热路径 _is_within_allowed_roots 免每次重复解析根目录。
_ALLOWED_WRITE_ROOTS: tuple[str, ...] = tuple(
    os.path.realpath(root)
    for root in (
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        tempfile.gettempdir(),
    )
)
# 2026-09-26 性能优化：预计算前缀对（root, prefix），避免热路径每次
# 对每个 root 重算 root.rstrip(os.sep) + os.sep。语义不变：
# prefix = root 去末尾 sep 后再加 sep（防 AITester_backup/ 兄弟目录碰撞）。
_ALLOWED_WRITE_ROOT_PREFIXES: tuple[tuple[str, str], ...] = tuple(
    (root, root.rstrip(os.sep) + os.sep) for root in _ALLOWED_WRITE_ROOTS
)


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
    except (json.JSONDecodeError, RuntimeError, OSError) as e:
        # LLM 调用失败或返回非 JSON 格式时，使用默认计划兜底
        # 这确保了即使 LLM 服务异常，工作流仍可以继续执行（降级模式）
        # 2026-09-26 全面审查：扩捕获 OSError——agent.plan 内部 LLM 文件缓存
        # 读写（_call_llm_with_cache）在缓存目录被外部删除/磁盘满等场景抛
        # OSError，此前未捕获会让整图崩溃（与 debugger 节点同口径兜底）。
        # 复用 _get_default_test_plan（与上方验证失败分支同一构造点）：
        # 其 "or 'unknown'" 兜底比原内联 .get(key, "unknown") 更严格
        # （空串/None 键值也会归一为 "unknown"，语义向成功分支收敛）
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）同走默认计划兜底，
        # 任务不会因预算异常崩溃（后续迭代前置守卫快速失败，自然收敛）
        _planner_budget_hit = isinstance(e, BudgetExceededError)
        logger.warning(
            "Planner LLM 失败（%s），使用默认计划: %s", "5.4 预算封顶" if _planner_budget_hit else "JSON 解析失败", e
        )
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
    # 1.4 事件总线接线：PlanGenerated（纯观测，不改路由）
    publish_event(
        PlanGenerated(
            task_uuid=str(state.get("task_uuid", "")),
            function_name=str(test_plan.get("function_name") or ""),
            test_case_count=len(test_plan.get("test_cases", [])),
            iteration=int(state.get("iteration", 0)),
        )
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
    # 仅当 RAG 开关开启、模块可用时才进行检索（统一走 rag_guarded 降级守卫，P1 重构）
    # 闭包写回需要外层可变容器（list 包装：Python 闭包内无法 rebinding 外层局部名）
    rag_refs_box: list = [None]

    def _on_retrieve(retriever) -> None:
        # top_k=3 是经验值：太多会增加 prompt 长度，太少可能缺乏代表性
        refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
        logger.info("RAG 检索到 %d 个相似测试用例", len(refs) if refs else 0)
        rag_refs_box[0] = refs

    rag_guarded(
        "retrieve_test_cases",
        _on_retrieve,
        enabled=ENABLE_RAG,
        module_available=RAG_MODULE_AVAILABLE,
        retriever_cls=TestCaseRetriever,
        get_retriever=get_rag_retriever,
    )
    rag_refs: list | None = rag_refs_box[0]

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
    # Planner 缺席时 test_plan 为 None（documented behavior：Generator 基于裸代码自行推断，
    # 见 tests/test_workflow.py::test_generator_node_missing_test_plan_key_no_keyerror 回归口径）。
    # mypy 按 TypedDict 报 dict|None → dict，显式 cast 收窄（运行期传 None，Generator 内
    # isinstance(test_plan, dict) 守卫已覆盖 None 路径，行为不变）
    test_plan = cast("dict[str, Any]", state.get("test_plan"))

    # 2026-09-26 全面审查（P1 降级兜底）：此前 agent.generate 无 try-except，
    # LLM 调用失败（RuntimeError，含跨 API 故障转移耗尽）/ 缓存 OSError 会
    # 直接让整图崩溃——与 planner/debugger 节点"降级兜底"口径不一致（二者
    # 均有默认计划 / 空 patch 兜底），且 workflow.py 文档声称"使用 try-except
    # 捕获 LLM 调用异常，确保工作流不因单点故障而崩溃"。现补降级：LLM 失败时
    # 生成空测试 + 记诊断，executor 拿到空测试自然失败 → 路由到 debugger
    # （修代码）或 done，不再崩溃整图。历史行为是崩溃，新行为是优雅降级——
    # 对"LLM 完全不可用"场景更合理（崩溃 = 零产出，降级 = 仍有修复机会）。
    try:
        generated_test = agent.generate(
            test_plan,  # Planner 节点在图中时必带 test_plan；缺席时为 None，Generator 自行推断
            state["target_code"],
            module_name=state.get("module_name", ""),
            rag_references=rag_refs,
            focus_function=state.get("target_function"),
            # 1.2 改进（MutGen 式变异反馈闭环）：上一轮变异测试的存活变异体注入
            # prompt，引导生成针对"当前未捕获故障"的更强断言（None 时不注入）
            mutation_feedback=state.get("mutation_feedback"),
            # 3.3 改进：执行反馈驱动的动态 temperature（覆盖率连降时减半，None 时不覆盖）
            temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as e:
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）快速降级空测试，
        # 后续迭代经 MAX_ITERATIONS 自然收敛（各节点前置预算守卫行为一致）
        if isinstance(e, BudgetExceededError):
            logger.warning("Generator LLM 调用失败（5.4 预算封顶），降级为空测试: %s", e)
        else:
            logger.warning("Generator LLM 调用失败，降级为空测试: %s", e)
        generated_test = ""

    # 2.3 改进：复现测试专项生成（REPRO_TEST_ENABLE=true 且已有缺陷描述时）。
    # 缺陷描述优先取 diagnosis（上一轮 Debugger 根因分析），跨文件修复场景下
    # 该描述含缺陷触发路径信息；生成覆盖触发路径的复现测试写入 state["repro_test"]。
    repro_test: str | None = None
    defect_description = state.get("diagnosis") or state.get("review_reason") or ""
    if _repro_test_enabled() and defect_description:
        # target_module 缺失/空串时跳过（falsy 过滤保持原语义），非空则纳入跨文件提示
        cross_modules = [
            str(d["target_module"]) for d in (state.get("cross_file_deps") or []) if d.get("target_module")
        ]
        repro_test = agent.generate_repro_test(
            defect_description=defect_description,
            target_code=state["target_code"],
            module_name=state.get("module_name", ""),
            cross_file_modules=cross_modules or None,
            temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
        )
        logger.info("复现测试（2.3）生成完成，长度=%d", len(repro_test))
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
    # 2.3 改进：复现测试生成结果（未启用 / 无缺陷描述时保持 None）
    if repro_test:
        update["repro_test"] = repro_test
    # 累计 RAG 检索指标（本节点读取后携带历史值，避免后续节点覆盖丢失）
    if update_rag_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), update_rag_stat]
    # 再生成路径检测：两类进入方式都需 +1 计数并清空上一轮诊断：
    #   1. _should_debug 路由 "regenerate"（iteration >= max_iterations，诊断指向测试生成错误）；
    #   2. 3.1 双向诊断路由 "regenerate"（defect_type == "test_defect"，Review Agent
    #      判定为测试缺陷，可在任意 iteration 触发）。
    #   - 首次生成：不改变 regeneration_count，保留原有 diagnosis（尚无修复结论）
    #   - 再生成：计数 +1（供 _should_debug 上限判断），并清空上一轮诊断，
    #     避免旧的 diagnosis 关键词在新测试仍失败时再次触发 regenerate（死循环根因）
    if (
        state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        or state.get("defect_type") == "test_defect"
    ):
        update["regeneration_count"] = state.get("regeneration_count", 0) + 1
        update["diagnosis"] = None
        update["error_category"] = None
        # 3.1 双向诊断：重新生成测试后清空旧判定，避免"test_defect"信号
        # 在下一轮仍触发 regenerate（与 regeneration_count 上限共同防死循环）
        update["defect_type"] = None
        update["review_reason"] = None
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
    3.2 执行反馈轨迹：每次执行经 _record_execution_trace 追加到
    state["execution_trace"]（3.2 默认常开，纯观测层，不参与路由）。
    """
    # CLI 通过 state 注入的执行超时优先，未注入时回退到 config 中已校验的值
    executor_timeout = int(state.get("execution_timeout") or EXECUTION_TIMEOUT)
    t0 = time.time()
    # 隔离沙箱参数（P1 依赖隔离）：默认关闭，保持与历史实验一致；
    # 通过环境变量 EXECUTOR_USE_VENV / EXECUTOR_AUTO_INSTALL_DEPS 开启。
    # 4.3 Docker 隔离执行：EXECUTOR_USE_DOCKER=true 时经 docker CLI 在容器内
    # 跑 pytest（镜像 EXECUTOR_DOCKER_IMAGE，默认 aitester:latest）。
    # （2026-09-26 全面审查：EXECUTOR_DOCKER_IMAGE / EXECUTOR_USE_DOCKER 移入
    # 文件头导入，与同文件其他 config 符号风格一致）
    agent = ExecutorAgent(
        timeout=executor_timeout,
        use_docker=EXECUTOR_USE_DOCKER,
        use_venv=EXECUTOR_USE_VENV,
        auto_install_deps=EXECUTOR_AUTO_INSTALL_DEPS,
        dep_install_timeout=EXECUTOR_DEP_INSTALL_TIMEOUT,
        docker_image=EXECUTOR_DOCKER_IMAGE,
    )
    result = agent.execute(
        test_code=state["generated_test"] or "",
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

    # 统一走 rag_guarded 降级守卫（P1 重构）：测试通过时入库成功用例
    if result["passed"]:
        rag_guarded(
            "add_case",
            lambda r: r.add_case(
                code=state["target_code"],
                test_code=state["generated_test"],
                passed=True,
                metadata={"function": state.get("target_function"), "coverage": result["coverage"]},
            ),
            enabled=ENABLE_RAG,
            module_available=RAG_MODULE_AVAILABLE,
            retriever_cls=TestCaseRetriever,
            get_retriever=get_rag_retriever,
        )

    # 3.2 执行反馈轨迹：追加本次执行记录（纯观测层，默认常开）。
    # 上一轮覆盖率从入参轨迹前缀直接读（_record_execution_trace 内部再
    # 复制一份轨迹，故此处不预先计算 prev_coverage，避免重复扫描）
    new_trace = _record_execution_trace(
        state,
        passed=result["passed"],
        coverage=result["coverage"],
        elapsed_seconds=round(time.time() - t0, 2),
    )
    # 3.2 改进：基于历史轨迹（含本次）的动态迭代策略建议（观测层，不参与路由）
    prev_coverage = None
    if state.get("execution_trace"):
        prev_coverage = state["execution_trace"][-1].get("coverage")
    coverage_delta = round(result["coverage"] - prev_coverage, 2) if prev_coverage is not None else None
    strategy_suggestion = _suggest_iteration_strategy(new_trace, coverage_delta)

    # 1.4 事件总线接线：TestsExecuted（纯观测，不改路由）
    publish_tests_executed(state, passed=result["passed"], coverage=result["coverage"])

    return {
        "test_passed": result["passed"],
        "test_output": result["output"],
        "coverage_report": result["coverage"],
        "failed_cases": result["failed_cases"],
        "execution_trace": new_trace,
        "iteration_strategy_suggestion": strategy_suggestion,
    }


def _record_execution_trace(
    state: AITesterState,
    passed: bool,
    coverage: float,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    """3.2 执行反馈轨迹：把本次 Executor 执行追加到 state["execution_trace"]。

    轨迹为纯观测层（默认常开）：每次执行记录"通过/失败、相对上一轮的
    覆盖率变化、墙钟耗时"与保守线性归一的多维奖励信号
    （correctness / efficiency / simplicity），供未来执行反馈驱动的微调
    备料。轨迹不参与工作流路由决策，写入失败不阻断主流程（观测层
    失败不应改变被测系统行为，口径与 tracing 一致）。

    Args:
        state: 当前状态（已含上一轮 execution_trace 前缀）。
        passed: 本次测试是否通过。
        coverage: 本次覆盖率百分比（0-100，未测得时 0.0）。
        elapsed_seconds: 本次 Executor 节点墙钟耗时（秒）。

    Returns:
        追加本次记录后的完整 execution_trace 列表。
    """
    # 上一轮覆盖率从入参轨迹前缀读取（首轮为 None，与调用方口径一致）；
    # 调用方 _executor_node 已用同一公式计算过覆盖变化，此处仅服务
    # 追加的轨迹记录，避免重复全轨迹扫描
    trace = list(state.get("execution_trace") or [])
    prev_coverage = trace[-1].get("coverage") if trace else None
    coverage_delta = round(coverage - prev_coverage, 2) if prev_coverage is not None else None

    # 3.2 改进：基于历史轨迹的动态迭代策略调整——根据前几轮的
    # 覆盖率变化趋势，动态建议后续迭代的 temperature 或提示策略。
    # 保守口径：仅输出"建议"到 state["iteration_strategy_suggestion"]，
    # 不直接改变 LLM 调用参数（温度调整需经 BaseAgent 消费，此处只做观测层建议）。
    # 若前 2 轮覆盖率持续下降（delta < 0 两次），建议"降低 temperature
    # + 收紧提示"（当前路径过于发散）；若覆盖率停滞（delta ≈ 0 两次），
    # 建议"切换修复视角"（如从最小改动切到根因修复）
    # 注意：本函数只负责"追加轨迹"，保持返回轨迹列表的历史口径；
    # 策略建议由调用方（_executor_node）单独经 _suggest_iteration_strategy 计算
    # 并写入 state["iteration_strategy_suggestion"]（观测层，不参与路由）
    return _append_trace_record(
        state,
        trace,
        passed=passed,
        coverage=coverage,
        coverage_delta=coverage_delta,
        elapsed_seconds=elapsed_seconds,
    )


def _append_trace_record(
    state: AITesterState,
    trace: list[dict[str, Any]],
    passed: bool,
    coverage: float,
    coverage_delta: float | None,
    elapsed_seconds: float,
) -> list[dict[str, Any]]:
    """把本次执行记录追加到轨迹列表（3.2 观测层，写入失败不阻断主流程）。"""
    reward_signals = _compute_reward_signals(passed, coverage_delta, elapsed_seconds)
    trace.append(
        {
            "iteration": state.get("iteration", 0),
            "passed": passed,
            "coverage": coverage,
            "coverage_delta": coverage_delta,
            "elapsed_seconds": elapsed_seconds,
            "reward_signals": reward_signals,
        }
    )
    return trace


def _compute_reward_signals(passed: bool, coverage_delta: float | None, elapsed_seconds: float) -> dict[str, float]:
    """计算多维度奖励信号（3.2 保守线性归一，供执行反馈 RL 备料）。

    Args:
        passed: 测试是否通过。
        coverage_delta: 相对上一轮覆盖率变化（首轮为 None）。
        elapsed_seconds: 本次执行耗时（秒）。

    Returns:
        {"correctness": 0.0-1.0, "efficiency": 0.0-1.0,
         "simplicity": 0.0-1.0} 的保守归一奖励信号。
    """
    correctness = 1.0 if passed else 0.0
    # efficiency/simplicity 沿用历史口径（基于 EXECUTION_TIMEOUT 的线性归一），
    # 不改变奖励信号定义（避免影响历史实验数据可比性）
    efficiency = max(0.0, round(1.0 - elapsed_seconds / EXECUTION_TIMEOUT, 3))
    simplicity = max(0.0, round(1.0 - elapsed_seconds / (EXECUTION_TIMEOUT * 2.0), 3))
    return {
        "correctness": round(correctness, 4),
        "efficiency": efficiency,
        "simplicity": simplicity,
    }


def _suggest_iteration_strategy(trace: list[dict[str, Any]], coverage_delta: float | None) -> str | None:
    """3.2 改进：基于历史轨迹动态调整后续迭代策略（纯观测层建议）。

    Args:
        trace: 完整执行轨迹（含本次，已追加）。
        coverage_delta: 本次覆盖率变化。

    Returns:
        策略建议字符串（None 表示无需调整，保持默认）：
        - "lower_temperature": 前 2 轮覆盖率持续下降，建议降低温度收紧提示；
        - "switch_repair_view": 覆盖率停滞 2 轮，建议切换修复视角；
        - "keep": 无需调整。
    """
    if len(trace) < 2:
        return None  # 首轮无历史，不调整
    # 覆盖率 delta 过滤 None 后按 float 归一（trace 中 coverage_delta 可能缺失/非数值）
    # 2026-09-26 round10 P1：非数值 delta（"n/a"/dict 等历史落盘异常值）float()
    # 抛 ValueError 使 executor 节点崩溃 → try/except 跳过该条目（口径：非数值
    # delta 视为无信号，与 None 同语义），默认数值路径零变化
    recent_deltas: list[float] = []
    for t in trace[-3:-1]:
        val = t.get("coverage_delta")
        if val is None:
            continue
        try:
            recent_deltas.append(float(val))
        except (TypeError, ValueError):
            continue
    if not recent_deltas:
        return None
    declining = all(d < 0 for d in recent_deltas[-2:]) if len(recent_deltas) >= 2 else False
    stagnant = all(abs(d) < 0.5 for d in recent_deltas[-2:]) if len(recent_deltas) >= 2 else False
    if declining:
        return "lower_temperature"
    if stagnant:
        return "switch_repair_view"
    return None


def _dynamic_temperature_from_suggestion(suggestion: str | None) -> float | None:
    """3.3 改进：把迭代策略建议映射为动态 temperature（真正接线，非观测层）。

    此前 iteration_strategy_suggestion 仅记录不改变路由（观测层）。本函数
    把建议映射为实际采样温度，供 Generator / Debugger 节点在 LLM 调用时
    透传覆盖（_call_llm_with_cache 的 temperature 参数）：

    - "lower_temperature"：覆盖率连降 → 温度减半（下限 0.0），收紧采样发散；
    - 其他建议 / None：不覆盖（返回 None，沿用 config.TEMPERATURE）。

    Args:
        suggestion: executor 节点写入的迭代策略建议字符串。

    Returns:
        覆盖后的温度（None 表示不覆盖，沿用默认）。
    """
    if suggestion == "lower_temperature":
        # TEMPERATURE=0 时减半仍为 0（无收紧空间）→ 返回 None 沿用默认，
        # 避免"覆盖为 0.0"的无意义透传（2026-09-26 全面审查修复）
        if TEMPERATURE <= 0.0:
            logger.info("动态策略（3.3）：TEMPERATURE 已为 0，无可收紧空间，不覆盖")
            return None
        lowered = round(max(0.0, TEMPERATURE * 0.5), 3)
        logger.info("动态策略（3.3）：覆盖率连降，temperature %.2f → %.2f", TEMPERATURE, lowered)
        return lowered
    return None


def _diagnosis_node(state: AITesterState) -> dict[str, Any]:
    """三、双向代码-测试诊断节点（BiVCode 式 DiagnosisNode，默认关）。

    在 _debugger_node 之前执行：分析测试失败的根本原因，判断是"代码缺陷"
    还是"测试缺陷"，并把判定结果写入 state 供 _should_debug 路由消费：
    - 代码缺陷（implementation_defect）→ 路由到 _debugger_node 生成补丁；
    - 测试缺陷（test_defect）→ 路由回 generator 重新生成测试。

    复用 DebuggerAgent._run_review_diagnosis（BiVCoder 式 Review Agent），
    不重复 LLM prompt 工程；本节点仅做"路由前诊断 + 状态写入 + 观测追踪"。

    开关：DIAGNOSIS_NODE_ENABLE=true 时启用（默认 false，保持历史实验口径——
    历史路径由 _debugger_node 内部 BIDIRECTIONAL_DIAGNOSIS_ENABLE 完成诊断，
    本节点为工作流级的显式诊断点，二者可叠加但默认都关）。

    观测口径：纯诊断层，不修改 target_code / generated_test；LLM 调用失败时
    保守判定为 implementation_defect（与 _run_review_diagnosis 同口径），
    不因诊断失败阻断修复主流程。

    Args:
        state: 当前工作流状态（含 target_code / test_output / failed_cases /
            error_category 等字段）。

    Returns:
        更新后的状态字典，含 defect_type / review_reason / diagnosis_source。
    """
    agent = DebuggerAgent()
    t0 = time.time()
    # 截断超长代码与测试输出（诊断 prompt 的 token 预算与 _debugger_node 同口径）
    from src.agents.base_agent import BaseAgent

    truncated_code = BaseAgent.truncate_code(
        state.get("target_code") or "", focus_function=state.get("target_function")
    )
    truncated_output = BaseAgent.truncate_code(state.get("test_output") or "", max_chars=1500)
    failed_cases = state.get("failed_cases") or []
    error_category = str(state.get("error_category") or "unknown")

    review = agent._run_review_diagnosis(truncated_code, truncated_output, failed_cases, error_category)
    defect_type = review.get("defect_type", "implementation_defect")
    review_reason = review.get("reason", "")
    logger.info("三、双向诊断（DiagnosisNode）判定：%s（%s）", defect_type, review_reason[:80])
    _trace_node(
        "diagnosis",
        output_summary={
            "defect_type": defect_type,
            "review_reason": review_reason[:200],
            "error_category": error_category,
        },
        decision=defect_type,
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )
    return {
        "defect_type": defect_type,
        "review_reason": review_reason,
        # 诊断来源标记（区分工作流级 DiagnosisNode 与 _debugger_node 内联诊断）
        "diagnosis_source": "diagnosis_node",
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

    # 统一走 rag_guarded 降级守卫（P1 重构）：有失败用例时检索相似修复案例
    rag_refs_box: list = [None]
    if state.get("failed_cases"):

        def _on_retrieve_repairs(retriever) -> None:
            refs = retriever.retrieve_repairs(
                error_category=state.get("error_category", "unknown"),
                target_code=state["target_code"],
                top_k=2,
            )
            logger.info("RAG 检索到 %d 个相似修复案例", len(refs) if refs else 0)
            rag_refs_box[0] = refs

        rag_guarded(
            "retrieve_repairs",
            _on_retrieve_repairs,
            enabled=ENABLE_RAG,
            module_available=RAG_MODULE_AVAILABLE,
            retriever_cls=TestCaseRetriever,
            get_retriever=get_rag_retriever,
        )
    rag_refs: list | None = rag_refs_box[0]

    try:
        result = agent.debug(
            target_code=state["target_code"],
            test_output=state.get("test_output") or "",
            failed_cases=state.get("failed_cases") or [],
            rag_references=rag_refs,
            focus_function=state.get("target_function"),
            target_module=state.get("module_name"),
            # P0 1.1 分层代码压缩：跨文件任务时，把 cross_file_analyzer 构建的
            # 各模块"目标函数 + CODE_FOCUS_DEPTH 层调用链"聚焦上下文注入 prompt，
            # 替代"整模块全文 → 截断后靠猜"的旧口径（纯静态文本，零 LLM token）
            cross_file_contexts=state.get("cross_file_contexts") or None,
            # 3.3 改进：执行反馈驱动的动态 temperature（覆盖率连降时减半，None 时不覆盖）
            temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
            # 1.3 分层压缩降级链：上一轮补丁被命名契约符号守卫拒绝时
            # （_patch_applier_node 写入 state["contract_reject_feedback"] =
            # {"tier", "missing_symbols"}），本轮按"更高约束"的上下文档位
            # （补丁配方保留 / 签名+import 极简）+ 更低温度重新生成；
            # 未触发时 None（行为与历史完全一致）
            # mypy：AITesterState.get 对 TypedDict 返回 Any/Optional 视
            # 键是否已声明而定，显式 cast 收窄到 debug 期望类型
            contract_reject_feedback=cast("dict[str, Any] | None", state.get("contract_reject_feedback")),
        )
    except (json.JSONDecodeError, RuntimeError, OSError) as e:
        # 2026-09-26 全面审查：扩捕获 OSError——agent.debug 内部 LLM 文件缓存
        # 读写（_call_llm_with_cache）在缓存目录被外部删除/磁盘满等场景抛
        # OSError，此前未捕获会让整图崩溃（与 planner 节点同口径兜底）。
        # 5.4 任务级预算硬上限：BudgetExceededError（RuntimeError 子类，
        # 消息含 "LLM 预算耗尽"）捕获后本轮修复跳过，error_category 标记
        # "budget_exceeded"（供实验分析"预算封顶任务数"消费），不再空转
        # 迭代烧 token（后续迭代前置守卫同样快速失败，自然收敛）。
        _is_budget_hit = isinstance(e, BudgetExceededError)
        logger.warning("Debugger 本轮修复跳过: %s%s", e, "（5.4 预算封顶）" if _is_budget_hit else "")
        result = {
            "root_cause": f"JSON 解析失败: {e}",
            "error_category": "budget_exceeded" if _is_budget_hit else "unknown",
            "fix_strategy": "",
            "patch": "",
        }
    logger.info(
        "Debugger 完成第 %d 轮修复：类别=%s，根因=%s",
        state.get("iteration", 0) + 1,
        result.get("error_category", "unknown"),
        result.get("root_cause", "")[:80],
    )
    # 1.4 事件总线接线：DebuggerDiagnosed（含 2.1 修复策略标签，纯观测）
    publish_debugger_diagnosed(state, error_category=result.get("error_category", "unknown"))
    _trace_node(
        "debugger",
        output_summary={
            "error_category": result.get("error_category"),
            "root_cause": result.get("root_cause", "")[:200],
            "patch_len": len(result.get("patch", "")),
            # 3.2 对抗性推理校验结果
            "adversarial_check": result.get("adversarial_check", {}),
            # 3.1 双向诊断结果
            "defect_type": result.get("defect_type"),
        },
        decision=result.get("error_category", "unknown"),
        duration_ms=(time.time() - t0) * 1000,
        iteration=state.get("iteration", 0),
    )

    # 统一走 rag_guarded 降级守卫（P1 重构）：入库修复案例
    rag_guarded(
        "add_repair",
        lambda r: r.add_repair(
            original_code=state["target_code"],
            patch=result.get("patch", ""),
            error_category=result.get("error_category", "unknown"),
        ),
        enabled=ENABLE_RAG,
        module_available=RAG_MODULE_AVAILABLE,
        retriever_cls=TestCaseRetriever,
        get_retriever=get_rag_retriever,
    )

    # 显式标注 dict[str, Any]：值类型混含 str / dict（adversarial_check），
    # mypy 按字面量推断为 dict[str, str | dict[str, int]] 导致后续
    # update["rag_stats"] = list[...] 赋值报错
    update: dict[str, Any] = {
        "diagnosis": result["root_cause"],
        "error_category": result.get("error_category", "unknown"),
        "patch": result["patch"],
        # 3.2 对抗性推理：记录 LLM 输出的对抗性校验结果（缺省时为零值）
        "adversarial_check": result.get("adversarial_check", {"scenarios_checked": 0, "all_passed": False}),
        # 3.1 双向诊断结果（未启用时 debug() 恒返回 implementation_defect）
        "defect_type": result.get("defect_type", "implementation_defect"),
        "review_reason": result.get("review_reason", ""),
        # 3.3 位置感知修复定位结果（未启用/无法定位时 focused=False, hint=""）
        "position_aware_focus": result.get(
            "position_aware_focus",
            {"focused": False, "function_name": None, "line": None, "hint": ""},
        ),
        # 2.1 类型修复层疑点（空列表 = 无疑点；LLM 层修订成功时 patch 已替换，
        # 疑点仍保留供实验分析消费。2026-09-26 补传播：此前 debug() 返回值
        # 已含该键但节点未写入 state（schema 有键却无值，消费侧恒 None））
        "type_repair_findings": result.get("type_repair_findings", []),
        # 2.1 mypy 静态层观测（TYPE_CHECK_ENABLE=true 时非 0，未启用/未安装时 0）
        "mypy_findings_count": result.get("mypy_findings_count", 0),
        # 1.3 分层压缩降级链：本轮是否因契约拒绝反馈而收紧了上下文
        # （contract_reject_feedback 非空时 True；实验分析"降级链触发率"消费）
        "downgrade_triggered": result.get("downgrade_triggered", False),
        "downgrade_tier": result.get("downgrade_tier"),
        # 2.1 P1 改进：结构化修复策略标签（错误分类 → 修复路径显式映射，
        # 实验分析"哪类错误走了哪条修复路径"消费；缺省 None = 未产出）
        "fix_strategy_tag": result.get("fix_strategy_tag"),
        "fix_strategy_action": result.get("fix_strategy_action"),
        # 4. 失败知识库闭环落点 B 观测标志（_debugger_node 写入；默认 None，
        # FAILURE_KB_ENABLE 默认关时恒 None，历史口径不变）
        "kb_prompt_snippet_applied": result.get("kb_prompt_snippet_applied"),
    }
    # 累计 RAG 修复检索指标（P1）
    repair_stat = _build_rag_stat(rag_refs, kind="repairs")
    if repair_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), repair_stat]
    return update


def _is_within_allowed_roots(path: str, roots: tuple[str, ...] | None = None) -> bool:
    """判断文件路径是否位于任一允许根目录之内（含根目录自身）。

    前缀比较必须带上 os.sep，否则 AITester_backup/ 这类兄弟目录会因
    startswith(project_root) 命中而绕过白名单（前缀碰撞）。

    用 realpath 归一化两侧：macOS 上 /var 是 /private/var 的符号链接，
    pytest 的 tmp_path 与 tempfile.gettempdir() 一侧带 /private 一侧不带，
    abspath 会失配；realpath 统一解析符号链接后再比较。
    _ALLOWED_WRITE_ROOTS 已在模块加载期 realpath 归一化（进程内稳定），
    本函数仅对入参做 realpath，避免热路径重复解析根目录。

    Args:
        path: 待校验的文件路径。
        roots: 允许的根目录元组（已 realpath 归一化）。None 时使用
            模块级 _ALLOWED_WRITE_ROOT_PREFIXES（热路径，零重算开销）。

    Returns:
        True 表示路径位于某根目录内（或即根目录本身）。
    """
    abs_path = os.path.realpath(path)
    if roots is None:
        return any(abs_path == root or abs_path.startswith(prefix) for root, prefix in _ALLOWED_WRITE_ROOT_PREFIXES)
    return any(abs_path == root or abs_path.startswith(root.rstrip(os.sep) + os.sep) for root in roots)


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

    # 3.5 二期：多入口依赖分析（保守口径：一级展开，不递归——防依赖图爆炸）。
    # 当前 state 中仅 target_code 可用（单入口视角），entry_modules 传 [entry]；
    # 未来扩展多入口时，把其他模块名追加进 entry_modules 即可，节点无需改动。
    source_files: dict[str, str] = {}
    entry_modules: list[str] = []
    if entry_module:
        source_files[entry_module] = target_code
        entry_modules.append(entry_module)
    # 若有其他模块内容（未来扩展），在此追加到 source_files 与 entry_modules

    deps = analyze_multi_entry_deps(entry_modules, source_files)
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

    # 显式 asdict（而非 d.__dict__）：dataclass 未来加内部字段会无声改变
    # state["cross_file_deps"] 的 schema，下游节点按固定 key 取值的契约
    # （_patch_applier_node :985）保持稳定——2026-09-26 全面审查修复
    update: dict[str, Any] = {"cross_file_deps": [asdict(d) for d in deps]}

    # ── P0 1.1 分层代码压缩（跨文件调用链上下文）────────────────────────
    # 跨文件任务时，为每个依赖边的 target_module 构建"目标函数 → 被调函数
    # （CODE_FOCUS_DEPTH 层）"的调用链上下文（纯静态、不消耗 LLM token），
    # 写入 state["cross_file_contexts"]：{module_name: focused_code}。
    # 后续 _debugger_node 生成跨文件补丁时把相关模块的聚焦上下文一并注入
    # prompt，替代"整模块全文 → 截断猜"的旧口径。
    if deps:
        from src.tools.code_analyzer import extract_function_context

        focused_contexts: dict[str, str] = {}
        for dep in deps:
            module_src = source_files.get(dep.target_module, "")
            if not module_src:
                continue
            focused = extract_function_context(module_src, dep.symbol, depth=CODE_FOCUS_DEPTH)
            if focused:
                focused_contexts.setdefault(dep.target_module, focused)
        if focused_contexts:
            update["cross_file_contexts"] = focused_contexts
            logger.info(
                "P0 1.1 跨文件调用链上下文：构建 %d 个模块的聚焦上下文（depth=%d）",
                len(focused_contexts),
                CODE_FOCUS_DEPTH,
            )

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
    except Exception:
        # 失败时清理临时文件，避免残留；再把异常抛给调用方。
        # 用 Exception 而非 BaseException（PEP 8）：KeyboardInterrupt/SystemExit
        # 不应插入清理路径，临时文件由进程退出兜底回收
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def _select_multi_candidate_patch(
    state: AITesterState,
    original_code: str,
    iteration: int = 0,
) -> tuple[str, bool, dict[str, Any]]:
    """3.1 多候选补丁：生成 N 候选 + 静态筛选 + 执行验证，返回最优候选。

    无有效候选（全静态拒绝 / 执行全失败）时回退到 state 中的单补丁，
    保证多候选策略不会比原单补丁路径更差（只多不少）。

    5.2 持续细化：把多候选统计放入返回的 update dict
    （candidates / static_passed / exec_validated / selected），供
    refine_failure_category 识别 MULTI_CANDIDATE_ALL_REJECTED 类别。
    经 update dict 传递而非原地写 state（节点函数保持无副作用约定，
    避免 --parallel 线程下共享 TypedDict 串扰）。

    执行验证开关：环境变量 MULTI_CANDIDATE_EXEC_VALIDATE=true 时启用
    逐候选跑测试（成本更高但筛选更准），默认关闭走纯静态筛选。

    P0 3.2 多候选自适应触发（MULTI_CANDIDATE_TRIGGER_STRATEGY）：
    - adaptive（默认）：仅当 iteration >= 1（首次修复已失败）且
      error_category ∈ {assertion, runtime, logic_error, index_error}
      时启用多候选；简单任务 / 早期迭代保持单候选，省 Token。
    - always：历史口径，每次失败都启用多候选。

    Args:
        state: 当前工作流状态（含 target_code / generated_test / failed_cases /
            target_function / module_name 等字段）。
        original_code: 本轮修复的原始被测代码。
        iteration: 当前迭代轮次（从 0 开始），供自适应触发判断。

    Returns:
        (最优候选应用后的代码, 是否成功应用, update dict 含 multi_candidate_stats)。
        回退单补丁时与原 apply_patch_to_code 同口径。
    """
    # P0 3.2 多候选自适应触发（MULTI_CANDIDATE_TRIGGER_STRATEGY=adaptive 时，
    # 仅当"首次修复已失败（iteration >= 1）且错误类型 ∈ 困难类别"才启用；
    # 否则回退单候选，避免简单任务 +79% Token 的无收益成本）
    strategy = os.getenv("MULTI_CANDIDATE_TRIGGER_STRATEGY", "adaptive").strip().lower()
    if strategy == "adaptive":
        error_category = state.get("error_category") or "unknown"
        if iteration < 1 or error_category not in _HARD_ERROR_CATEGORIES:
            logger.info(
                "P0 3.2 多候选自适应触发：iteration=%d error_category=%s 不满足启用条件"
                "（iteration>=1 且 category∈%s），回退单候选",
                iteration,
                error_category,
                _HARD_ERROR_CATEGORIES,
            )
            # 回退单候选路径（与 else 分支同口径）
            new_code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")
            update: dict[str, Any] = {
                "multi_candidate_stats": {
                    "candidates": 1,
                    "static_passed": 1 if applied else 0,
                    "exec_validated": False,
                    "selected": 0 if applied else None,
                    "adaptive_skipped": True,
                    "skip_reason": f"iteration={iteration},category={error_category}",
                }
            }
            return new_code, applied, update

    n = multi_candidate_count()
    debugger = DebuggerAgent()
    candidates = generate_candidates(
        debugger=debugger,
        target_code=original_code,
        test_output=state.get("test_output") or "",
        failed_cases=state.get("failed_cases") or [],
        num_candidates=n,
        focus_function=state.get("target_function"),
        target_module=state.get("module_name"),
    )
    use_exec = multi_candidate_exec_validate()
    executor = ExecutorAgent(timeout=EXECUTION_TIMEOUT, use_venv=EXECUTOR_USE_VENV) if use_exec else None
    best = select_best_candidate(
        candidates=candidates,
        original_code=original_code,
        test_code=state.get("generated_test") or "",
        target_file=state.get("target_file"),
        target_function=state.get("target_function"),
        use_execution_validation=use_exec,
        executor=executor,
        # 3.3 改进：把历史执行反馈轨迹传入，供轻量奖励预测器调节候选排序
        execution_trace=state.get("execution_trace"),
    )
    static_passed_count = sum(1 for c in candidates if c.static_passed)
    _trace_node(
        "multi_candidate",
        output_summary={
            "candidates": len(candidates),
            "static_passed": static_passed_count,
            "exec_validated": use_exec,
            "selected": (best.index if best else None),
        },
        decision=f"selected_{best.index + 1}" if best else "fallback_single",
        iteration=state.get("iteration", 0),
    )
    # 5.2 持续细化：记录多候选统计（供 refine_failure_category 识别
    # MULTI_CANDIDATE_ALL_REJECTED：candidates>0 且 static_passed==0）
    # 走 update dict 而非原地写 state（节点函数应保持无副作用；state 是
    # LangGraph 共享 TypedDict，原地写入在 --parallel 线程下会串扰）
    stats_update: dict[str, Any] = {
        "multi_candidate_stats": {
            "candidates": len(candidates),
            "static_passed": static_passed_count,
            "exec_validated": use_exec,
            "selected": best.index if best else None,
        },
    }
    if best is None:
        # 多候选全部失败 → 回退到单补丁（保持历史行为，不引入劣化）
        logger.info("多候选无有效补丁，回退到单补丁流程")
        code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")
        return code, applied, stats_update
    code, applied = apply_patch_to_code(original_code=original_code, patch=best.patch)
    return code, applied, stats_update


def _safe_write_patch(original_code: str, new_code: str, applied: bool, state: AITesterState) -> bool:
    """
    安全检查 + 原子写盘：将新代码写入 state["target_file"]。

    三道安全检查（任一不过则拒绝写入，返回 False）：
    1. 补丁不能是空字符串或比原代码短得多（防止 LLM 返回空文件）；
    2. 补丁必须含至少一个函数定义（防止 LLM 返回无意义内容）；
    3. 目标路径必须在项目根目录或系统临时目录内（防路径穿越）。

    Args:
        original_code: 应用补丁前的原始代码（用于长度比较安全检查）。
        new_code: 应用补丁后的新代码。
        applied: 补丁应用是否成功（静态校验通过）。
        state: 当前状态，读取 target_file 与写入路径校验。

    Returns:
        True 表示代码已写盘，False 表示被安全检查拒绝或补丁未生效。
    """
    if not applied or new_code == original_code:
        return False
    # 安全检查 1：空或过短（长度 < 原代码 10%，防 LLM 返回残缺文件）
    if not new_code or len(new_code) < len(original_code) * 0.1:
        logger.error("补丁内容异常（空或过短），跳过写入: %s", state["target_file"])
        return False
    # 安全检查 2：必须含至少一个函数定义（防 LLM 返回无意义内容）。
    # 单遍字符串扫描（re.search 命中即停，不再把补丁全文逐行拆成
    # list[str] 再逐行 startswith——补丁普遍数百行，每次应用都产生
    # O(行数) 临时列表，--parallel 场景下累积可观）
    if not _HAS_FUNC_DEF_RE.search(new_code):
        logger.error("补丁不含任何函数定义，跳过写入: %s", state["target_file"])
        return False
    # 安全检查 3：路径白名单（项目根目录或系统临时目录，前缀比较带 os.sep 防兄弟目录碰撞）
    # 白名单根在模块加载期归一化（_ALLOWED_WRITE_ROOTS，abspath 与历史判定语义一致）
    target_file_path = os.path.abspath(state["target_file"])
    if not _is_within_allowed_roots(target_file_path):
        logger.error("非法文件路径，拒绝写入: %s", state["target_file"])
        return False
    # 原子写入：写临时文件后 os.replace，崩溃不损坏用户源文件
    # 写目标用 abspath（无符号链接归一化）：白名单判定走 realpath 语义，
    # 写盘路径保持调用方视角的原始路径（行为与历史一致）
    _write_file_atomic(os.path.abspath(state["target_file"]), new_code)
    logger.info("补丁已应用到文件: %s", state["target_file"])
    return True


def _patch_applier_node(state: AITesterState) -> dict[str, Any]:
    """
    补丁应用节点：将 Debugger 生成的补丁应用到被测代码，并写回文件。
    应用后更新 iteration 计数器，供下次循环使用。

    2.2 补丁后处理重采样（PATCH_RESAMPLE_ENABLE=true，默认关）：应用失败
    （定位不到目标函数 / AST 解析不通过）时，把"负面反馈"回传 Debugger
    重新生成一次（严格 prompt + 1.3 降级链档位收紧温度），最多
    PATCH_RESAMPLE_MAX（默认 2）次；仍失败则把该轮标记为
    patch_syntax_invalid（refine_failure_category 消费）并保留原代码。

    1.3 分层压缩降级链（CONTEXT_TIER_DOWNGRADE_ENABLE=true，默认关）：
    符号守卫（check_naming_contract）拒绝补丁时，调 advance_context_tier()
    推进上下文档位，并把 (档位, 缺失符号) 作为 contract_reject_feedback
    写入 state——下一轮 _debugger_node 读到该反馈后按"更高约束"的
    上下文（补丁配方保留 / 签名+import 极简）+ 更低温度重新生成。
    未启用时（默认）行为与历史完全一致（仅拒绝本轮、不动档位）。

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
    # 多候选分支的额外状态更新（multi_candidate_stats，经 update dict 传递）
    multi_candidate_update: dict[str, Any] = {}
    new_code: str
    applied: bool
    cross_file_deps = state.get("cross_file_deps") or []
    if cross_file_deps and cross_file_enabled():
        # 3.5 跨文件修复分支：按依赖图拓扑序对多个模块应用补丁
        from src.tools.cross_file import CrossFileDependency, apply_multi_file_patch, cross_file_fallback_single_file

        # 把 state 中序列化的依赖边还原为 CrossFileDependency 对象
        # （拓扑序补丁应用需要结构化边信息，被调用方先改、调用方后改）
        dep_objects = [
            CrossFileDependency(
                source_module=d.get("source_module", ""),
                target_module=d.get("target_module", ""),
                symbol=d.get("symbol", ""),
                call_line=int(d.get("call_line", 0)),
                context=d.get("context", ""),
            )
            for d in cross_file_deps
        ]
        # 从 state 收集所有模块的原始代码（当前仅 target_code 可用；
        # 二期扩展后从 source_files 字典读取）
        entry_module = state.get("module_name") or os.path.basename(state.get("target_file", ""))
        original_files = {entry_module: original_code}
        # 多文件补丁：entry_module 用 state["patch"]（当前单补丁路径生成），
        # 其他模块的补丁由 _debugger_node 后续生成（二期）
        patches: dict[str, str] = {}
        if state.get("patch"):
            patch_val = state["patch"]
            assert isinstance(patch_val, str)  # TypedDict 标 str | None，真值守卫后必为 str
            patches[entry_module] = patch_val
        # 尝试多文件应用（传依赖边 → 拓扑序）；失败时降级为单文件
        new_files, applied = apply_multi_file_patch(original_files, patches, entry_module, deps=dep_objects)
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
        new_code, applied, multi_candidate_update = _select_multi_candidate_patch(
            state, original_code, iteration=state.get("iteration", 0)
        )
    else:
        new_code, applied = apply_patch_to_code(original_code=original_code, patch=state.get("patch") or "")

    # ── 1.1 LLM 输出后处理层（P1 空壳检测 + P2/P3 卫生化，默认观测口径）──
    # P2 导入回填 / P3 契约别名回填默认关（环境变量控制，见
    # patch_postprocess.postprocess_enabled_flags）；P1 空壳检测默认启用，
    # 仅产出"empty_patch"标签观测（EMPTY_LLM_PATCH 场景从不可观测变为
    # 可识别标签，供 refine_failure_category / 实验分析消费），不改代码。
    # P2/P3 启用时：卫生化结果替换本轮 patch 后重新应用（仅单文件分支；
    # 多候选/跨文件分支的候选池各有独立静态筛选，不重复卫生化）。
    postprocess_labels: list[str] = []
    postprocess_update: dict[str, Any] = {}
    if (not cross_file_deps or not cross_file_enabled()) and not multi_candidate_available():
        try:
            from src.tools.patch_postprocess import postprocess_enabled_flags, sanitize_patch

            _pp_flags = postprocess_enabled_flags()
            _sanitized, _pp_labels = sanitize_patch(original_code, state.get("patch"))
            postprocess_labels = list(_pp_labels)
            if (_pp_flags["import_repair"] or _pp_flags["contract_alias"]) and (
                "imports_repaired" in _pp_labels or "contract_aliases_restored" in _pp_labels
            ):
                # P2/P3 生效：用卫生化后的补丁重新应用单文件路径
                new_code, applied = apply_patch_to_code(original_code=original_code, patch=_sanitized)
            postprocess_update["postprocess_labels"] = postprocess_labels
        except Exception:
            logger.debug("1.1 后处理层执行异常（保守跳过，保持历史口径）", exc_info=True)

    # P0 1.3 命名契约检查：补丁应用前对比修改前后的模块级符号集合
    # （函数/类/__all__/注册装饰器/插件入口点），缺失任何原符号则拒绝应用。
    # 开关 PATCH_CONTRACT_CHECK（默认 true）；设 false 回退历史口径。
    contract_missing: list[str] = []
    if applied and new_code != original_code:
        from src.tools.patch_applier import check_naming_contract

        ok, missing = check_naming_contract(original_code, new_code)
        if not ok:
            logger.warning("P0 1.3 命名契约检查失败，拒绝应用补丁：缺失符号 %s", missing)
            applied = False
            new_code = original_code
            contract_missing = list(missing)
            # 1.3 分层压缩降级链：守卫拒绝时推进上下文档位（进程内状态），
            # 并把 (档位名, 缺失符号) 经 state 透传给下一轮 _debugger_node。
            # 开关 CONTEXT_TIER_DOWNGRADE_ENABLE（默认 false，保持历史口径；
            # true 时降级链全链路生效）。
            if _context_tier_downgrade_enabled():
                from src.tools.patch_applier import _current_context_tier, advance_context_tier

                advance_context_tier()
                tier_name, _idx, _temp = _current_context_tier()
                # 临时键：本节点函数内先写入、末尾经 state.pop 取出合并进返回
                # dict（键本身不进入 LangGraph 通道——通道键为
                # contract_reject_feedback，见 1.3 降级链注释）。mypy 无法
                # 对 TypedDict 的临时动态键收窄，故对 state 做窄化 cast。
                _state = cast("dict[str, Any]", state)
                _state["_1_3_contract_feedback"] = {
                    "tier": tier_name,
                    "missing_symbols": contract_missing,
                }
            # mypy：同上，cast 收窄（临时键不入 TypedDict 声明）
            cast("dict[str, Any]", state)["_1_3_contract_missing"] = contract_missing

    # ── 2.2 改进：补丁后处理重采样（PATCH_RESAMPLE_ENABLE=true，默认关）──
    # 应用失败（定位不到目标函数 / AST 解析不通过）时，把"负面反馈"回传
    # Debugger 重新生成（严格 prompt + 1.3 降级链档位收紧温度），最多
    # PATCH_RESAMPLE_MAX（默认 2）次；仍失败则把该轮标记为
    # patch_syntax_invalid（refine_failure_category 消费）并保留原代码。
    # 未启用时（默认）行为与历史完全一致，不产生额外 LLM 调用。
    resample_stats: dict[str, Any] | None = None
    if not applied and _patch_resample_enabled():
        from src.agents.debugger import DebuggerAgent
        from src.tools.patch_applier import apply_patch_with_resample

        resampler = DebuggerAgent()

        def _on_resample(query: str, original_code: str, patch: str, ast_error: str) -> str | None:
            """2.2 重采样回调：严格 prompt + 1.3 降级链档位温度重新生成补丁。

            注入"被拒补丁 + AST 错误 + 原始代码片段 + 档位温度"，让 LLM 在
            更高约束下修订。返回的修订补丁已通过静态验证（AST 合法 + 不破坏
            命名契约 + 能成功应用）才返回，否则 None（保守保留原代码）。
            """
            if not patch and not ast_error:
                return None
            # 提取被拒补丁里的 python 代码块（LLM 输出可能带 markdown 包裹）
            from src.utils.helpers import extract_code_block

            _rejected = extract_code_block(patch or "", language="python") or (patch or "")[:1000]
            # 注入 1.3 降级链档位（被符号守卫拒绝后自动降级到的档位）
            from src.tools.patch_applier import _current_context_tier

            _tier_name, _idx, _temp = _current_context_tier()
            strict_prompt = (
                "【补丁语法校验失败反馈】上一轮补丁应用后 AST 解析失败或未能定位到目标函数，"
                f"具体错误：\n{ast_error[:500]}\n\n"
                "请基于同样的错误上下文，重新生成一个语法合法的补丁。"
                "必须保留原文件中所有模块级符号（函数名/类名/__all__/注册装饰器/插件入口点），"
                "只允许修改函数/方法体内部逻辑。用 ```python ... ``` 包裹输出。"
                f"\n\n【当前档位：{_tier_name}（温度 {_temp}）】"
                f"\n【被拒补丁片段】\n```\n{_rejected}\n```\n"
                f"\n【原始代码片段】\n```\n{(original_code or '')[:2000]}\n```"
            )
            try:
                _result = resampler._call_llm_with_cache(strict_prompt, temperature=_patch_resample_temperature())
                _extracted = extract_code_block(_result or "", language="python")
                if not _extracted:
                    return None
                # 二次静态验证：必须能 ast.parse 且不破坏命名契约
                from src.tools.patch_applier import check_naming_contract, safe_apply_patch

                _try_code, _try_ok = safe_apply_patch(original_code, _extracted)
                if not _try_ok:
                    return None
                _contract_ok, _missing = check_naming_contract(original_code, _try_code)
                if not _contract_ok:
                    return None
                return _extracted
            except Exception:
                logger.debug("2.2 重采样 LLM 调用失败（保守返回 None，不阻断主流程）", exc_info=True)
                return None

        new_code, applied, resample_stats = apply_patch_with_resample(
            original_code,
            state.get("patch") or "",
            resample_fn=_on_resample,
            max_resamples=_patch_resample_max(),
        )
        if resample_stats.get("resampled"):
            logger.info(
                "2.2 补丁后处理重采样 %d 次，成功=%s",
                resample_stats.get("resample_count", 0),
                resample_stats.get("success", False),
            )
            # 重采样成功后重新走契约检查与写盘路径
            if applied and new_code != original_code:
                from src.tools.patch_applier import check_naming_contract as _ck

                _ok2, _missing2 = _ck(original_code, new_code)
                if not _ok2:
                    logger.warning("2.2 重采样后命名契约仍被破坏（%s），拒绝写盘", _missing2[:5])
                    applied = False
                    new_code = original_code
                    contract_missing = list(_missing2)
            if resample_stats.get("success") is False and resample_stats.get("resampled"):
                # 2.2 标记：重采样耗尽仍失败 → patch_syntax_invalid
                # （refine_failure_category 在任务收尾时消费）
                cast("dict[str, Any]", state)["_2_2_patch_syntax_invalid"] = True

    # 默认视为"未真正写盘"，任何安全检查失败都保持该值
    written = _safe_write_patch(original_code, new_code, applied, state)

    # 状态/磁盘一致性：仅写盘成功才更新 target_code，否则保留原代码
    effective_code = new_code if written else original_code

    # 0.8 一致性口径：节点函数保持"纯函数更新字典"（--parallel 线程下
    # LangGraph 共享 TypedDict 不允许原地写）——此前 history.append 直接
    # 改写 state["repair_history"] 原列表（其他节点/路由对同一 state 的读取
    # 会看到被改写的中间值）；现改为拷贝后追加、经 update dict 写回
    history = list(state.get("repair_history") or [])
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
    # 1.3 改进：把本轮契约缺失符号（可能来自 2.2 重采样路径）写回 state，
    # 供 refine_failure_category / 实验分析消费（"5/7 任务破坏 sqlfluff
    # 插件命名契约"场景的直接可观测信号）
    contract_update: dict[str, Any] = {}
    # mypy：_1_3_contract_missing 为本节点函数内写入的临时键（不进入
    # AITesterState TypedDict 声明——通道键为 contract_missing_symbols，
    # 见上方 1.3 注释），对 state 做窄化 cast 消除 typeddict-unknown-key
    _state_pop = cast("dict[str, Any]", state)
    _missing_now = _state_pop.pop("_1_3_contract_missing", None) or []
    if _missing_now:
        contract_update["contract_missing_symbols"] = list(_missing_now)
    # 1.3 降级链档位反馈：透传给 _debugger_node（下一轮 debug 按档位收紧上下文）
    feedback_update: dict[str, Any] = {}
    _feedback_now = _state_pop.pop("_1_3_contract_feedback", None)
    if _feedback_now:
        feedback_update["contract_reject_feedback"] = _feedback_now
    # 2.2 重采样统计 + patch_syntax_invalid 标记（refine 消费）
    resample_update: dict[str, Any] = {}
    if resample_stats is not None:
        resample_stats_out = dict(resample_stats)
        from src.tools.patch_applier import _current_context_tier as _tier_fn

        _tier_name_now, _idx_now, _temp_now = _tier_fn()
        resample_stats_out["tiered_context"] = _tier_name_now
        resample_update["patch_resample_stats"] = resample_stats_out
    _syntax_invalid_flag = _state_pop.pop("_2_2_patch_syntax_invalid", False)
    if _syntax_invalid_flag:
        # patch_syntax_invalid 标记写入 error_category（refine_failure_category
        # 会在任务收尾时把 "patch_syntax_invalid" 归一到 PATCH_SYNTAX_INVALID）
        resample_update["error_category"] = "patch_syntax_invalid"
    # 1.4 事件总线接线：PatchApplied（含 1.1 后处理标签，纯观测）
    publish_patch_applied(state, applied=written, new_code=effective_code)
    return {
        "target_code": effective_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
        **multi_candidate_update,
        **contract_update,
        **feedback_update,
        **resample_update,
        **postprocess_update,
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
    return isinstance(la, dict)


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
