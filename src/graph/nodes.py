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
    MAX_REGENERATIONS,
    detection_first_enabled,
)

# S4（2026-10-09 R4）：DebuggerAgent / ExecutorAgent 顶层导入保留（noqa）——
# nodes.py 自身已不直接构造二者（patch 簇拆分后由 patch_io / debugger 模块
# 构造），但 agents_cache.py 的延迟导入 `from src.graph.nodes import
# DebuggerAgent/ExecutorAgent` 与测试 `patch("src.graph.nodes.DebuggerAgent")`
# 的历史 mock 口径依赖此命名空间转发（与 flags re-export 同口径，须保留）。
from src.agents.debugger import DebuggerAgent  # noqa: F401
from src.agents.executor import ExecutorAgent  # noqa: F401
from src.agents.generator import GeneratorAgent, _repro_test_enabled
from src.agents.planner import PlannerAgent
from src.agents.rogue_monitor import rogue_monitor_enabled
from src.budget.cost_budget import BudgetExceededError

# S7（2026-10-08 R3）：Agent 复用缓存已拆分到 src/graph/agents_cache.py，
# 此处 re-export 保持 `from src.graph.nodes import get_or_create_agent` 等
# 历史导入路径不变。
from src.graph.agents_cache import (  # noqa: F401
    _MAX_CACHED_AGENTS,
    _agent_instance_cache,
    _agent_instance_cache_lock,
    _executor_agent_cache,
    _executor_agent_cache_lock,
    _get_or_create_debugger_agent,
    _get_or_create_executor_agent,
    clear_agent_instance_cache,
    clear_executor_agent_cache,
    get_or_create_agent,
)

# S7（2026-10-08 R3）：debugger 节点簇已拆分到 src/graph/debugger.py，此处
# re-export 保持 `from src.graph.nodes import _debugger_node` 历史导入路径不变。
from src.graph.debugger import (  # noqa: F401
    _build_failure_frequency_section,
    _debugger_node,
    _diagnosis_node,
    _resolve_target_module,
)
from src.graph.event_bus import (
    PlanGenerated,
    publish_event,
    publish_patch_applied,
    publish_tests_executed,
)

# S7（2026-10-08 R3）：功能开关辅助已拆分到 src/graph/flags.py，此处
# re-export 保持 `from src.graph.nodes import _xxx_enabled` 历史导入路径不变。
# 注：下一行 F401 豁免是因为部分开关已不再被 nodes.py 直接使用（改由
# debugger / agents_cache 等拆分模块消费），但测试与历史调用方仍从
# src.graph.nodes 导入，须保留。
from src.graph.flags import (  # noqa: F401
    _agent_reuse_enabled,
    _boundary_triplets_enabled,
    _branch_coverage_inject_enabled,
    _context_tier_downgrade_enabled,
    _failure_frequency_enabled,
    _fl_spectral_enabled,
    _flaky_check_enabled,
    _oracle_enhance_enabled,
    _oracle_validate_enabled,
    _patch_resample_enabled,
    _patch_resample_max,
    _patch_resample_temperature,
    _probe_snapshot_locate_enabled,
    _repo_core_protection_enabled,
    _runtime_probe_enabled,
    _spec_ir_dsl_enabled,
    _spec_ir_enabled,
    _spec_oracle_exec_enabled,
)

# S4（2026-10-09 R4）：补丁应用安全核心已拆分到 src/graph/patch_io.py，
# 此处 re-export 保持 `from src.graph.nodes import _safe_write_patch` 等
# 历史导入路径不变（与 S7 拆分 debugger/flags 同口径）。
from src.graph.patch_io import (  # noqa: F401
    _ALLOWED_WRITE_ROOTS,
    _ALLOWED_WRITE_ROOT_PREFIXES,
    _HARD_ERROR_CATEGORIES,
    _HAS_FUNC_DEF_RE,
    _PROTECTED_CORE_BASENAMES,
    _PROTECTED_CORE_DIRS,
    _is_repo_core_path,
    _is_within_allowed_roots,
    _rollback_last_patch,
    _safe_write_patch,
    _select_multi_candidate_patch,
    _write_file_atomic,
)
from src.graph.rag import (
    RAG_MODULE_AVAILABLE,
    TestCaseRetriever,
    _build_rag_stat,
    get_rag_retriever,
    rag_guarded,
)
from src.graph.state import AITesterState

# S7（2026-10-08 R3）：trace/reward 簇已拆分到 src/graph/trace_reward.py，
# 此处 re-export 保持 `from src.graph.nodes import _record_execution_trace`
# 等历史导入路径与 workflow.py 的 re-export 逐字节不变。
from src.graph.trace_reward import (  # noqa: F401
    _append_trace_record,
    _compute_reward_signals,
    _dynamic_temperature_from_suggestion,
    _patch_line_delta_for_reward,
    _record_execution_trace,
    _suggest_iteration_strategy,
)
from src.graph.tracing import _trace_node
from src.tools.cross_file import analyze_multi_entry_deps, cross_file_enabled
from src.tools.multi_candidate import (
    multi_candidate_available,
)
from src.tools.patch_applier import apply_patch_to_code
from src.tools.patch_rollback import snapshot_rollback_enabled

# 模块级 logger，用于记录节点执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)

# 修复历史上限：超过后仅保留最近 N 条，防止长迭代循环占用内存（经验值 5）
_MAX_REPAIR_HISTORY = 5

# P0 1.1 分层代码压缩：调用链展开层数（与 BaseAgent.truncate_code 同口径，
# CODE_FOCUS_DEPTH 环境变量，默认 1；跨文件任务建议 2）
CODE_FOCUS_DEPTH: int = int(os.getenv("CODE_FOCUS_DEPTH", "1"))


def _append_spec_oracle_to_test(generated_test: str, state: AITesterState) -> tuple[str, bool]:
    """R1c：把确定性规约 oracle 测试追加到 LLM 生成测试尾部（可独立测试的纯函数）。

    compile_spec_oracle 产物（签名感知绑定的可执行断言）与 LLM 测试**并列**
    执行——LLM 测试通过 ≠ 规约 oracle 通过，后者失败 = "逻辑驱动"通道的
    确定性检出。产物经编译层 ast.parse 自检 + "无断言即丢弃"双重守卫
    （spec_ir_v2 口径），注入面与 LLM 生成代码同沙箱档执行。

    Args:
        generated_test: LLM 生成的测试代码。
        state: 工作流状态（spec_ir / test_plan / target_code / module_name /
            target_function）。

    Returns:
        (追加后的测试代码, 是否注入)。编译失败 / 无材料 / 异常 → 原文 + False。
    """
    from src.specs import compile_spec_oracle as _compile_spec_oracle
    from src.specs import extract_signature_params as _extract_signature_params
    from src.specs import parse_logic_analysis as _parse_logic_analysis

    # 规约材料两级降级：state["spec_ir"]（R7 开关产物）→ 现场解析
    # test_plan.logic_analysis（与 DSL 层独立降级同口径）
    spec_material: dict[str, Any] | None = state.get("spec_ir")
    if spec_material is None:
        spec_material = _parse_logic_analysis(
            (state.get("test_plan") or {}).get("logic_analysis") if isinstance(state.get("test_plan"), dict) else None
        )
    oracle_func = state.get("target_function") or (spec_material or {}).get("function_name") or ""
    if not (spec_material and oracle_func and state.get("module_name")):
        return generated_test, False
    sig_params = _extract_signature_params(state.get("target_code") or "", str(oracle_func))
    try:
        oracle_code = _compile_spec_oracle(
            spec_material,
            target_module=str(state.get("module_name") or ""),
            target_function=str(oracle_func),
            signature_params=sig_params,
        )
    except (SyntaxError, ValueError, TypeError, KeyError) as e:
        # 编译层内部已保守降级，此处兜底捕获意外异常（防注入链路崩图）
        logger.warning("R1c 规约 oracle 编译异常，保守跳过注入：%s", e)
        return generated_test, False
    if not oracle_code:
        return generated_test, False
    logger.info(
        "R1c 确定性规约 oracle 已注入（fn=%s, sig_params=%d, 追加 %d 字符）",
        oracle_func,
        len(sig_params or []),  # 签名提取失败时为 None，日志口径按 0 参计
        len(oracle_code),
    )
    return f"{generated_test}\n\n\n{oracle_code}", True


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
    agent = get_or_create_agent(PlannerAgent)
    t0 = time.time()
    _planner_budget_hit = False  # 5.4 预算封顶标记（O35；正常 / 验证降级路径恒 False）
    try:
        # 调用 Planner 生成测试计划，传入被测代码和可选的目标函数名
        # 若指定了 target_function，Planner 将只分析该函数，缩小分析范围
        test_plan = agent.plan(state["target_code"], state.get("target_function"))
        # 验证输出结构
        if not _validate_planner_output(test_plan):
            logger.warning("Planner 输出结构不完整，使用默认计划")
            test_plan = _get_default_test_plan(state.get("target_function"))
            # M10（2026-09-29 审查 P0）：验证失败走默认计划 → 逻辑驱动路径
            # 实际未发生，标记 logic_degraded=True（纯观测，供实验层区分
            # "逻辑驱动成功"与"降级到默认计划"）。
            test_plan["logic_degraded"] = True
        # P0 测试预言增强（ORACLE_ENHANCE_ENABLE=true 时启用，默认关）：
        # 在 Planner 产出 logic_analysis（规约）后，由独立 LLM 调用对每个
        # test_case 做规约驱动预言推理，追加 oracle / oracle_source /
        # oracle_confidence 字段；下游 Generator 经 _build_query 的
        # json.dumps(test_plan) 自然消费强化断言预言。
        # 保守降级：LLM 失败时保留原 test_cases（oracle_enhanced=False），不阻断生成。
        # 默认关闭时零行为变化（历史口径不变）。
        if _oracle_enhance_enabled():
            from src.agents.oracle_enhancer import OracleEnhancerAgent

            enhancer = OracleEnhancerAgent()
            test_plan = enhancer.enhance(test_plan)
            _oracle_enhanced = bool(test_plan.get("oracle_enhanced"))
            logger.info(
                "P0 测试预言增强：%s（函数=%s，oracle 注入 %d 条）",
                "成功" if _oracle_enhanced else "降级保留原 test_cases",
                test_plan.get("function_name", "unknown"),
                sum(1 for c in test_plan.get("test_cases", []) if c.get("oracle")),
            )
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
        # M10（2026-09-29 审查 P0）：LLM 失败走默认计划 → 逻辑驱动路径
        # 实际未发生，标记 logic_degraded=True（纯观测，供实验层区分
        # "逻辑驱动成功"与"降级到默认计划"）。
        test_plan["logic_degraded"] = True
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
    # 观测层：把"预言增强是否触发"写回 state（供实验分析消费，默认关时不写）
    update: dict[str, Any] = {"test_plan": test_plan}
    if _oracle_enhance_enabled():
        update["oracle_enhanced"] = bool(test_plan.get("oracle_enhanced"))
    # R7（2026-09-30 独立审查 P0）：SpecIR——把 logic_analysis（自然语言规约）
    # + 确定性边界三元组解析为可执行 SpecIR IR，校验 findings 写回 state
    # （SPEC_IR_ENABLE=true 时非空，默认关时 None，历史口径零变化）。
    # 保守：解析/校验失败 → spec_ir=None（不阻断 Planner 主流程）。
    if _spec_ir_enabled():
        from src.specs import parse_logic_analysis, validate_spec_ir
        from src.tools.logic_spec import derive_boundary_triplets

        _spec_ir = parse_logic_analysis(
            test_plan.get("logic_analysis"),
            boundary_triplets=derive_boundary_triplets(state["target_code"], state.get("target_function")),
        )
        if _spec_ir is not None:
            _spec_ir["findings"] = validate_spec_ir(_spec_ir)
        update["spec_ir"] = _spec_ir
    # A-01（2026-10-04 系统审查 P0）：SpecIR v2 DSL 层——"逻辑驱动"主张的
    # 可测量内核：SPEC_IR_DSL_ENABLE=true（默认关，与 R7 主开关独立）时，
    # 对 SpecIR 的 pre/post/invariant 子句做"可编译率"判定（受限表达式
    # DSL + 白名单，纯静态零 LLM）写入 state["spec_compile_rate"]（float
    # 0.0~1.0，无规约材料时 0.0——可证伪口径："逻辑驱动"贡献 = 可编译率，
    # 而非 100% 宣称）。纯观测字段，不参与路由（与 spec_ir 同档位）。
    if _spec_ir_dsl_enabled():
        from src.specs import compile_readiness, spec_expr_coverage, spec_provenance

        _dsl_spec = update.get("spec_ir")
        if _dsl_spec is None:
            # DSL 层独立于 R7 主开关：R7 关但 DSL 开时，直接解析
            # logic_analysis（保守降级：无材料 → 0.0）
            from src.specs import parse_logic_analysis

            _dsl_spec = parse_logic_analysis(test_plan.get("logic_analysis"))
        update["spec_compile_rate"] = compile_readiness(_dsl_spec)
        # AC1（2026-10-06 第十轮审查 T-P0-2）：表达式通道覆盖率并列透出
        # （compile_rate=编译器接受率，coverage=LLM 形式化覆盖率，正交观测）
        update["spec_expr_coverage"] = spec_expr_coverage(_dsl_spec)
        _prov = spec_provenance(_dsl_spec)
        if _prov:
            update["spec_provenance"] = _prov
    # 5.4 预算封顶标记（O35）：置真后不回退，供 determine_stop_reason 的
    # BUDGET_EXCEEDED 分支与实验分析消费（此前该分支无任何写入点，恒不可达）。
    if _planner_budget_hit:
        update["budget_exceeded"] = True
    return update


def _detection_first_regenerate_entry(state: AITesterState) -> bool:
    """W3（2026-10-05 审查落地·检出优先协议）：判定本节点是否由"检出优先
    再生成"路由进入（_should_debug 的 detection_first_all_green 分支）。

    特征（与首生成 / 其他三类再生成路径可区分）：
    - DETECTION_FIRST_ENABLE=true；
    - test_passed 为 True（首生成恒 None；其余再生成路径均因测试失败触发）；
    - iteration==0（未发生修复；detection_first 的再生成只发生在首轮）。

    供两处消费：
    1. 再生成计数（regeneration_count +1，防 executor↔generator 乒乓，
       与其余三类再生成路径同口径）；
    2. 构造"先红后绿"强化提示段落（见 _detection_first_section）。
    """
    return detection_first_enabled() and state.get("test_passed") is True and int(state.get("iteration", 0)) == 0


def _specificity_over_red_regenerate_entry(state: AITesterState) -> bool:
    """AC2 特异性门过红再生成入口检测（修复引擎批次 III 补漏，2026-10-07）。

    根因（E2 实证 16/174 任务撞 recursion_limit 的通道之一）：
    _should_debug 的 over_red 分支以 test_passed=**False** 进入 generator
    （测试红、但红得不特异），而 _detection_first_regenerate_entry 只认
    test_passed is True → 五类再生成入口检测无一命中 → regeneration_count
    恒不递增 → over_red 分支的 regeneration_count < MAX_REGENERATIONS
    上限永不绑定 → executor↔generator 无限乒乓直至 recursion_limit
    （O4/W3 同类漏计根因的第三个实例）。

    判定特征：iteration==0（over_red 分支只在首轮触发）且
    specificity_gate_verdict=="over_red"（该值只在特异性门对照执行时
    写入——门关时恒 None，无需重复判门开关）。
    """
    return int(state.get("iteration", 0)) == 0 and state.get("specificity_gate_verdict") == "over_red"


def _detection_first_section(state: AITesterState) -> str | None:
    """W3：检出优先再生成路径的 prompt 强化段落（非该路径时 None 不注入）。

    RT1 消融（2026-10-09 审查报告 §8.6 红队 RT1，`DETECTION_FIRST_SECTION_ENABLE`）：
    该开关默认 **true**（历史口径零变化）。置 false 时**保留再生成路由**
    （`_should_debug` 的 `detection_first_all_green` 分支与 `regeneration_count`
    计数照旧）但**不注入本强化段落**——用于分离"协议提示词效应"与
    "多一次采样的效应"：
    - `plain_llm_df` 臂有再生成 + 有强化段（现口径）；
    - RT1 臂有再生成 + **无**强化段；
    - 二者检出差即**协议文本的净效应**，其余样本量/调用次数对齐。
    动机：df 臂在首轮全绿时**必然**再生成一次，而 `plain_llm` 只生成一次——
    "+43pp 协议效应"与"多一次采样的效应"在既有对照中未解耦（RT1）。
    """
    if not _detection_first_section_enabled():
        return None
    if not _detection_first_regenerate_entry(state):
        return None
    return (
        "【检出优先·先红后绿】上一版测试在当前（未修复的）代码上全部通过——"
        "这说明测试没有检出任何缺陷，属于无效的全绿测试。请重新生成更强的测试："
        "针对代码中最可能隐藏缺陷的边界条件、异常路径与特殊输入构造断言，"
        "使测试在当前含缺陷的代码上**至少一个用例失败（变红）**。"
        "禁止放松、删减或条件化断言来换取通过；禁止重新实现被测函数；"
        "断言的期望值必须来自问题语义（数学定律/规约），不得抄袭实现当前行为。"
    )


def _over_red_section_enabled() -> bool:
    """过红再生成强化段落的消融开关（``OVER_RED_SECTION_ENABLE``，默认 **false**）。

    默认关 = 历史口径零变化（ADR-0003：新功能默认关）；置 "true"/"1" 时
    `_over_red_section` 才可能注入段落。置 false 时**再生成路由与计数不受影响**
    （与 `DETECTION_FIRST_SECTION_ENABLE` 同一口径：开关只控制提示词，不控制路由）。
    """
    return os.getenv("OVER_RED_SECTION_ENABLE", "false").lower() in ("1", "true")


def _over_red_section(state: AITesterState) -> str | None:
    """过红（over_red）再生成路径的 prompt 强化段落（非该路径时 None 不注入）。

    背景（2026-10-10 审查报告 §11.1b 结果二十四/二十五，实测证据）
    ---------------------------------------------------------------
    QuixBugs 41 缺陷程序口径下的**轮次级**观测：

    | 首轮 verdict | aitester 占比 | 两臂 detection |
    |---|---|---|
    | ``specific_red``（首轮特异红） | 19/50（38%） | **100%** |
    | ``over_red``（盲/过红，需再生成） | **30/50（60%）** | **0%** |

    即 **`over_red` 覆盖 aitester 六成任务，而其中检出率为 0**。
    代码级根因：`_detection_first_section` 要求
    ``_detection_first_regenerate_entry``（``test_passed is True``），
    而 ``over_red`` 是 ``test_passed=False`` 进入的（测试红了，但红得不特异——
    或**因缺陷代码不终止而挂起**）→ **拿不到任何强化提示** →
    再生成只是"用同一份计划再问一次" → 注定同样 over_red，**不可恢复**。

    与 ``plain_llm_df`` 的对照印证：df 无 Planner 故无缺陷锚定的计划，
    首轮特异红 34/50（68%）、over_red 仅 15/50（30%）。

    本段落针对性给出"过红"专有的三条指令：
    1. **不终止即失败**：若上一版测试在缺陷代码上**挂起/超时**，说明它无法
       给出判定——须改用**输入规模受控**的用例，使函数要么返回、要么快速失败
       （实测样例：`bitcount` 的缺陷实现 `n ^= n - 1` 对任何 n 都不终止，
       `assert bitcount(127) == 7` 只会永久挂起）；
    2. **期望值来自契约而非实现**：期望值须由 docstring / 类型注解 /
       数学性质推出，**不得**照抄被测实现当前行为（那是缺陷行为）；
    3. **保持特异性**：不得为求通过而放松/删减/条件化断言。

    Args:
        state: 工作流状态。

    Returns:
        强化段落文本，或 None（开关关 / 非 over_red 路径）。
    """
    if not _over_red_section_enabled():
        return None
    if not _specificity_over_red_regenerate_entry(state):
        return None
    return (
        "【过红修复·重写为特异测试】上一版测试在**未修复**的代码上变红了，"
        "但这个红**不可判定**或**不特异**——常见两种形态："
        "① 测试**挂起/超时**（被测函数在当前缺陷实现下不终止），"
        "此时它既不能算检出也不能算通过；"
        "② 测试红了，但红了**非缺陷相关**的位置（如收集错误、与被测函数无关的断言）。"
        "请重新生成测试，务必满足："
        "**（a）输入规模受控**——所有用例都必须在有限时间内返回或快速抛错，"
        "禁止使用会让当前实现陷入长循环的大输入（若要触发已知的非终止缺陷，"
        "请用 `pytest.raises` / `pytest.mark.timeout` 或在断言前限制迭代规模的等价手段，"
        "使测试**快速失败**而不是挂起）；"
        "**（b）期望值必须来自契约**——由 docstring、类型注解与数学性质推出，"
        "严禁照抄被测实现当前的返回值（当前实现含缺陷，照抄即等于把缺陷写成期望）；"
        "**（c）保持特异性**——故障必须出在**被测函数的行为断言**上，"
        "且该断言在正确实现下应当通过；"
        "禁止放松、删减或条件化断言来换取通过。"
    )


def _detection_first_section_enabled() -> bool:
    """RT1 消融开关（`DETECTION_FIRST_SECTION_ENABLE`，默认 true = 历史口径）。

    置 "false"/"0" 时 `_detection_first_section` 返回 None（不注入强化段落），
    但 `_detection_first_regenerate_entry` 与再生成路由**不受影响**。
    """
    return os.getenv("DETECTION_FIRST_SECTION_ENABLE", "true").lower() not in ("0", "false")


def _derive_detection_first_status(passed: bool, red_seen: bool | None) -> str | None:
    """Y1（2026-10-05 X 批次真实冒烟发现）：检出优先终态标注的三值推导（纯函数）。

    背景：W3 原实现仅在 test_passed=True 时写 detection_first_status——
    "首轮全绿 → 再生成 → 第二版变红 → 终止"轨迹（plain_llm_df 冒烟实测，
    trace: PASS→regenerate→FAIL→done）下，exec1 写入的 all_green_unverified
    残留为终值，与 detection_first_red_seen=True 并列出现语义矛盾
    （"从未红"标注 vs "曾检出"信号）。终态标注应覆盖失败终局：

    - passed ∧ red_seen  → red_then_green（先检出再修复——W3 原口径）
    - passed ∧ 无 red    → all_green_unverified（弱测试假成功——W3 原口径）
    - ¬passed ∧ red_seen → red_not_repaired（检出成功但未修复：plain_llm_df
      无修复循环的正常终态 / aitester 修复失败的终态；**这是有效检出**，
      评估层 detection 口径应计数，不得因 passed=False 丢弃）
    - ¬passed ∧ 无 red   → None（不写：无检出无修复的失败无可标注语义，
      保留上一轮写入值）

    每轮执行后写，LangGraph 后写覆盖 → 最终值即终态（与 W3 注释口径一致）。
    """
    if passed:
        return "red_then_green" if red_seen else "all_green_unverified"
    if red_seen:
        return "red_not_repaired"
    return None


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
    agent = get_or_create_agent(GeneratorAgent)

    # 初始化 RAG 参考列表为 None（默认不使用检索增强）
    # 仅当 RAG 开关开启、模块可用时才进行检索（统一走 rag_guarded 降级守卫，P1 重构）
    # 闭包写回需要外层可变容器（list 包装：Python 闭包内无法 rebinding 外层局部名）
    rag_refs_box: list = [None]

    def _on_retrieve(retriever) -> None:
        # top_k=3 是经验值：太多会增加 prompt 长度，太少可能缺乏代表性
        refs = retriever.retrieve_test_cases(state["target_code"], top_k=3)
        # P2 RAG 相关性评分 + 条件注入（2026-10 改进，A/B 阴性结果驱动）：
        # 生成侧同样做相关性过滤（默认关，历史口径零变化）——低相关案例
        # 反增 token 噪声（ContextSniper 式"先筛选再注入"）
        if refs:
            from src.graph.rag import filter_by_relevance

            refs, _filtered_n, _filter_rate = filter_by_relevance(refs)
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
    _generator_budget_hit = False  # 5.4 预算封顶标记（O35；正常路径恒 False）
    try:
        # 修复引擎批次 XI（ADR-0025）：oracle 上下文消融档——minimal 时
        # 下方四个增强段（分支覆盖/AST 边界锚点/蜕变/差分）全部保持
        # None 不注入（ASE 2025"额外上下文无边际收益"的消融对照臂）。
        # 默认 full：各段按自身开关构造，历史口径零变化。
        from src.tools.logic_spec import oracle_context_minimal as _oracle_ctx_minimal

        _ctx_minimal = _oracle_ctx_minimal()
        # O3（2026-09-29 审查 P1）：分支覆盖率注入——_executor_node 上一轮测量
        # 的未覆盖分支清单渲染为 prompt 段落（BRANCH_COVERAGE_INJECT_ENABLE=true
        # 时非空，默认关时 None，历史口径零变化）
        _bc_section: str | None = None
        if not _ctx_minimal and _branch_coverage_inject_enabled() and state.get("branch_coverage"):
            from src.tools.branch_coverage_inject import build_branch_coverage_prompt_section as _build_bc_section

            _bc_section = _build_bc_section(state.get("branch_coverage"))
        # M10（2026-09-29 审查 P0）：确定性边界锚点——从 target_code 的 AST
        # 分支条件推导边界三元组（零 LLM 成本），渲染为 prompt 段落注入
        # Generator（BOUNDARY_TRIPLETS_ENABLE=true 时非空，默认关时 None，
        # 历史口径零变化）。与 O3 分支覆盖率注入同位（在 generate 调用前
        # 构建，传入 generate 的新参数 boundary_triplets_section）。
        _bt_section: str | None = None
        if not _ctx_minimal and _boundary_triplets_enabled():
            from src.tools.logic_spec import build_boundary_triplets_section as _build_bt_section
            from src.tools.logic_spec import derive_boundary_triplets as _derive_bt

            _bt_triplets = _derive_bt(state["target_code"], state.get("target_function"))
            if _bt_triplets:
                _bt_section = _build_bt_section(_bt_triplets)
        # P2-7（N2/N4 接线审计，2026-10）：无 oracle 场景增强段落。
        # N2 蜕变关系：从函数名/签名/文档启发式匹配 MR 模板（零 LLM 成本），
        # 命中时渲染 prompt 段落注入（METAMORPHIC_ENABLE=true 时非空，默认关
        # 时 None，历史口径零变化）。
        # N4 差分测试：引导 LLM 生成"参考实现 vs 被测实现"随机输入比对指令
        # （DIFFERENTIAL_TEST_ENABLE=true 时非空，默认关时 None）。
        # 两节均为纯观测层 prompt 增强，不改变路由 / 开关默认行为。
        _fn_name = state.get("target_function") or ""
        _mr_section: str | None = None
        _diff_section: str | None = None
        try:
            from experiments.metamorphic_oracle import (
                build_metamorphic_prompt_section as _build_mr_section,
            )
            from experiments.metamorphic_oracle import (
                metamorphic_enabled as _mr_enabled,
            )
            from experiments.metamorphic_oracle import (
                suggest_metamorphic_relations as _suggest_mrs,
            )

            if not _ctx_minimal and _mr_enabled() and _fn_name:
                _mrs = _suggest_mrs(_fn_name)
                if _mrs:
                    _mr_section = _build_mr_section(_mrs)
            from experiments.differential_test import (
                build_differential_prompt_section as _build_diff_section,
            )
            from experiments.differential_test import (
                differential_enabled as _diff_enabled,
            )

            if not _ctx_minimal and _diff_enabled() and _fn_name:
                _diff_section = _build_diff_section(_fn_name)
        except Exception as _oracle_hook_exc:  # 观测层钩子失败不得阻断主生成
            logger.warning("N2/N4 无 oracle 增强段落构建失败，降级跳过: %s", _oracle_hook_exc)
        # P2（2026-10 批次·续二）：注入扫描回归基准接线——此前
        # detect_prompt_injection 输入侧全仓无调用方（孤儿函数，威胁模型 P2
        # 缺口"注入扫描无回归基准"）。本段在 Generator 消费外部可控文本
        # （problem_statement / 缺陷描述 / 任务描述）前做输入侧注入特征扫描
        # （INJECTION_GUARD_ENABLE 默认关时恒 []，历史口径零变化）；命中时
        # 把 findings 写入 state["injection_findings"]（供 agent_telemetry
        # 的 injection_detected 模式消费 + trace 记录）并经
        # build_injection_warning 追加系统侧警示到本次 LLM query（OWASP ASI
        # "检测+隔离"口径：只警示不自动阻断，阻断决策留给调用方）。
        # 外部可控文本来源（按优先级）：
        #   1. state["problem_statement"]（SWE-bench 任务描述 / issue 文本）
        #   2. state["diagnosis"] / state["review_reason"]（上一轮诊断描述）
        #   3. state["task_description"]（CLI 自定义任务描述，若存在）
        _injection_task_text = (
            state.get("problem_statement")
            or state.get("diagnosis")
            or state.get("review_reason")
            or state.get("task_description")
            or ""
        )
        _injection_findings: list[str] = []
        _injection_warning: str | None = None
        if _injection_task_text:
            from src.agents.injection_guard import (
                build_injection_warning,
                detect_prompt_injection,
            )
            from src.agents.injection_guard import (
                injection_guard_enabled as _injection_guard_enabled,
            )

            _injection_text = str(_injection_task_text)
            if _injection_guard_enabled():
                _injection_findings = detect_prompt_injection(_injection_text)
                if _injection_findings:
                    _injection_warning = build_injection_warning(_injection_findings)
                    logger.warning(
                        "P2 注入扫描：外部文本检出注入特征 %s（追加系统侧警示，不自动阻断）", _injection_findings
                    )
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
            # O12（2026-09-29 审查 P1）：复杂度感知路由——complexity_class 非 None 时
            # 经 _call_llm_with_cache → _call_llm → _reorder_api_groups_by_complexity
            # 按档位重排 API 组（complex → 高成本端点在前），使
            # MODEL_ROUTING_STRATEGY=complexity_aware（默认值）真实生效。
            complexity_class=state.get("complexity_class"),
            # O3（2026-09-29 审查 P1）：未覆盖分支清单提示段落（None 时不注入）
            branch_coverage_section=_bc_section,
            # M10（2026-09-29 审查 P0）：确定性边界锚点提示段落（None 时不注入）
            boundary_triplets_section=_bt_section,
            # P2-7（N2/N4）：无 oracle 场景增强段落（None 时不注入）
            metamorphic_section=_mr_section,
            differential_section=_diff_section,
            # W3（2026-10-05 审查落地·检出优先协议）：检出优先再生成路径的
            # "先红后绿"强化段落（非该路径时 None 不注入，历史口径零变化）
            detection_first_section=_detection_first_section(state),
            # 2026-10-10（结果二十四）：过红再生成强化段落
            # （OVER_RED_SECTION_ENABLE 默认关 → None 不注入，历史口径零变化）
            over_red_section=_over_red_section(state),
            # P2（2026-10 批次·续二）：注入扫描系统侧警示（命中注入特征时非空，
            # INJECTION_GUARD_ENABLE 默认关时恒 None，历史口径零变化）
            injection_warning=_injection_warning,
        )
    except (RuntimeError, OSError, json.JSONDecodeError) as e:
        # 5.4 预算封顶：BudgetExceededError（isinstance 判定）快速降级空测试，
        # 后续迭代经 MAX_ITERATIONS 自然收敛（各节点前置预算守卫行为一致）
        if isinstance(e, BudgetExceededError):
            logger.warning("Generator LLM 调用失败（5.4 预算封顶），降级为空测试: %s", e)
        else:
            logger.warning("Generator LLM 调用失败，降级为空测试: %s", e)
        generated_test = ""
        _generator_budget_hit = isinstance(e, BudgetExceededError)

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
        # 2026-10-01 全面审查 P1 修复：2.3 复现测试分支此前无 try/except 兜底——
        # 主生成路径（agent.generate，L546）有 try/except (RuntimeError, OSError,
        # json.JSONDecodeError) 降级为空测试，但 generate_repro_test 走同一条 LLM
        # 调用路径（_call_llm_with_cache，可抛 RuntimeError / BudgetExceededError /
        # OSError / JSONDecodeError），异常直接传播出 _generator_node 崩整图，
        # 与主生成路径的"降级兜底"口径不一致（workflow.py 文档承诺"工作流不因
        # 单点故障崩溃"）。现补同口径 try/except：LLM 失败时 repro_test=None
        # 降级（复现测试缺失不阻断主生成路径，executor 仍走 generated_test）。
        try:
            repro_test = agent.generate_repro_test(
                defect_description=defect_description,
                target_code=state["target_code"],
                module_name=state.get("module_name", ""),
                cross_file_modules=cross_modules or None,
                temperature=_dynamic_temperature_from_suggestion(state.get("iteration_strategy_suggestion")),
            )
        except (RuntimeError, OSError, json.JSONDecodeError) as e:
            if isinstance(e, BudgetExceededError):
                logger.warning("复现测试（2.3）LLM 调用失败（5.4 预算封顶），降级为跳过: %s", e)
            else:
                logger.warning("复现测试（2.3）LLM 调用失败，降级为跳过（不阻断主生成）: %s", e)
            repro_test = None
        logger.info("复现测试（2.3）生成完成，长度=%d", len(repro_test or ""))
    # 记录生成结果长度，便于评估 Generator 的输出质量
    logger.info("Generator 完成测试代码生成，长度=%d", len(generated_test))

    # AST 级断言一致性检查（ORACLE_VALIDATE_ENABLE=true 时启用，默认关）：
    # 纯 AST 静态分析（零 LLM 成本），识别恒真断言 / 魔数断言 / 类型不一致
    # 三类疑点，写入 state["oracle_findings"] 供实验分析消费（观测层，不阻断
    # 主流程）。开关关闭 / 无生成内容时不执行（历史口径不变）。
    oracle_findings: list[dict[str, Any]] = []
    if _oracle_validate_enabled() and generated_test:
        from src.tools.oracle_validator import check_assertions

        oracle_findings = check_assertions(generated_test, state["target_code"])
        if oracle_findings:
            logger.info(
                "AST 断言一致性检查发现 %d 个疑点（类型=%s）",
                len(oracle_findings),
                [f.get("type") for f in oracle_findings],
            )
    # O6（2026-09-29 审查 P1）：确定性守卫（DETERMINISTIC_GUARD_ENABLE=true 时启用，默认关）。
    # 对 LLM 生成的测试代码做非确定性静态扫描（random / time.sleep / wall_clock /
    # 外部副作用），含 finding 的测试文件标记为"非确定性"，供实验层决定是否
    # 入库确定性套件。纯 AST 扫描（零 LLM 成本），不阻断主流程。
    # 开关关闭时 scan_test_file 返回空 findings（is_deterministic 恒 True），
    # 历史口径零变化。
    deterministic_guard_report: Any = None
    if generated_test:
        from src.agents.deterministic_guard import scan_test_file as _scan_det_guard

        _det_report = _scan_det_guard(generated_test, filename=state.get("module_name", "<memory>"))
        if _det_report.findings:
            logger.info(
                "O6 确定性守卫：%d 个非确定性 finding（规则=%s）",
                len(_det_report.findings),
                [f.rule for f in _det_report.findings],
            )
            deterministic_guard_report = _det_report
    # O4（2026-09-29 审查 P1）：恒真断言触发一次强制重生成。
    # tautological>=1 时标记 defect_type=test_defect，路由回 generator
    # 重生成（受再生成上限保护，防死循环）。
    # 开关关闭（ORACLE_VALIDATE_ENABLE=false，默认）时 oracle_findings 恒空，
    # 历史口径零变化。
    # Z2（2026-10-06 审查修复）：删除本函数内的同值局部字面量
    # `_MAX_REGENERATIONS = 1`（与 workflow 模块常量双源，靠注释"同口径"
    # 维系，漂移风险已登记），改用 config.MAX_REGENERATIONS 单一事实源。
    _tautological_count = sum(1 for f in oracle_findings if f.get("type") == "tautological")
    _o4_triggered = (
        _tautological_count >= 1
        and state.get("defect_type") != "test_defect"
        and int(state.get("regeneration_count", 0)) < MAX_REGENERATIONS
    )

    # N5（2026-09-29 审查 P2）：测试套件断言去重（HYPOTHESIS_ENABLE 同口径，
    # 独立开关 TEST_SUITE_DEDUP_ENABLE 默认 false 保持历史口径）。
    # LLM 生成的测试套件常含大量恒真断言（O4 已识别但无去重）；
    # 本层在 generator 产出后对 test_code 做 AST 级重复断言去除
    # （experiments/test_suite_minimize.dedup_assertions），纯数据
    # 零 LLM 成本，不改变路由 / 开关默认行为。
    if os.getenv("TEST_SUITE_DEDUP_ENABLE", "false").lower() in ("true", "1", "on"):
        from experiments.test_suite_minimize import dedup_assertions as _dedup_assertions

        _deduped_code, _dedup_removed = _dedup_assertions(generated_test)
        if _dedup_removed:
            generated_test = _deduped_code
            logger.info("N5 测试套件断言去重：移除 %d 条重复断言", len(_dedup_removed))

    # R1c（2026-10-05 审查 P0）：确定性规约 oracle 注入（SPEC_ORACLE_EXEC_ENABLE=true
    # 时启用，默认关时零注入，历史口径不变）。详见 _append_spec_oracle_to_test。
    if _spec_oracle_exec_enabled():
        generated_test, _spec_oracle_injected = _append_spec_oracle_to_test(generated_test, state)
    else:
        _spec_oracle_injected = False

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
    # R1c（2026-10-05 审查 P0）：确定性规约 oracle 注入标记（state 键已声明，
    # 不会被 LangGraph 白名单丢弃；默认关时恒 False）
    if _spec_oracle_injected:
        update["spec_oracle_injected"] = True
    # 5.4 预算封顶标记（O35）：Generator 捕获 BudgetExceededError 时置真
    # （planner / debugger 同口径），使 determine_stop_reason 可达 BUDGET_EXCEEDED。
    if _generator_budget_hit or state.get("budget_exceeded"):
        update["budget_exceeded"] = True
    # 2.3 改进：复现测试生成结果（未启用 / 无缺陷描述时保持 None）
    if repro_test:
        update["repro_test"] = repro_test
    # P2（2026-10 批次·续二）：注入扫描 findings 写入 state（INJECTION_GUARD_ENABLE
    # 默认关时恒 []，历史口径零变化；非空时供 agent_telemetry 的
    # injection_detected 模式消费 + trace 记录，配合 experiments/
    # injection_benchmark_samples.json 回归基准度量召回/误伤）。
    update["injection_findings"] = _injection_findings
    # AST 级断言一致性检查（ORACLE_VALIDATE_ENABLE=true 时非空，默认关时零变化）
    if oracle_findings:
        update["oracle_findings"] = oracle_findings
    # 修复引擎批次 XIV（ADR-0028 观测层）：oracle 质量历史快照——
    # Self-Repair Trap（DCAware：迭代自修复驱使断言退化）的数据面。
    # 每次生成/再生成的最终测试（去重与规约注入之后）落一份快照；
    # 空测试不落（生成失败是另一类失败模式，不属于"断言退化"）。
    # 纯观测零行为影响；阻断 / 策略切换须先有 A/B 数据与预注册判据。
    if generated_test:
        from src.tools.self_repair_trap import snapshot_test_quality

        _mf = state.get("mutation_feedback")
        _ms = _mf.get("mutation_score") if isinstance(_mf, dict) else None
        _quality_history = list(state.get("oracle_quality_history") or [])
        _quality_history.append(
            snapshot_test_quality(
                generated_test,
                mutation_score=float(_ms) if isinstance(_ms, (int, float)) and not isinstance(_ms, bool) else None,
                regeneration=int(state.get("regeneration_count", 0)),
            )
        )
        update["oracle_quality_history"] = _quality_history
    # O4（2026-09-29 审查 P1）：恒真断言强制重生成——标记 defect_type=test_defect，
    # 触发 _should_debug 的 regenerate 路由（受 regeneration_count 上限保护，防死循环）。
    if _o4_triggered:
        logger.info(
            "O4：恒真断言 %d 条，标记 defect_type=test_defect 触发强制重生成（regeneration_count=%d）",
            _tautological_count,
            state.get("regeneration_count", 0),
        )
        update["defect_type"] = "test_defect"
    # O6（2026-09-29 审查 P1）：确定性守卫报告（DETERMINISTIC_GUARD_ENABLE=true 时非空，默认关时零变化）
    if deterministic_guard_report is not None:
        update["deterministic_guard_report"] = {
            "filename": deterministic_guard_report.filename,
            "findings": [
                {"rule": f.rule, "detail": f.detail, "line": f.line} for f in deterministic_guard_report.findings
            ],
            "is_deterministic": deterministic_guard_report.is_deterministic,
        }
    # O4（2026-09-29 审查 P1）：恒真断言强制重生成路径。
    # _tautological_count >= 1 时已写入 update["defect_type"] = "test_defect"，
    # 下方再生成路径检测的条件 2（state.get("defect_type") == "test_defect"）
    # 读取的是**历史** state（非 update），故须将 O4 触发条件并入再生成路径判定：
    # _tautological_count >= 1 且 regeneration_count 未达上限时，视为再生成路径，
    # +1 计数并清空旧诊断（与 3.1 双向诊断路径同口径，防死循环）。
    # _o4_triggered 已在上方（L658）定义，此处直接引用。
    # 累计 RAG 检索指标（本节点读取后携带历史值，避免后续节点覆盖丢失）
    if update_rag_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), update_rag_stat]
    # 再生成路径检测：判定"本节点是否由 regenerate 路由进入"。
    # 覆盖三类进入方式：
    #   1. _should_debug 路由 "regenerate"（iteration >= max_iterations，诊断指向测试生成错误）；
    #   2. 3.1 双向诊断路由 "regenerate"（defect_type == "test_defect"，Review Agent
    #      判定为测试缺陷，可在任意 iteration 触发）；
    #   3. _should_debug 早期路由 "regenerate"（iteration < max_iterations 且 diagnosis
    #      命中 test-generation 关键词，2026-09-26 审查提升为任意 iteration 可触发的
    #      独立分支，reason=test_gen_diagnosis_early）：特征为 iteration > 0 且
    #      diagnosis 非空（首生成恒 iteration=0 且 diagnosis=None，故可区分）。
    # 此前仅条件 1/2 成立时 +1 计数，条件 3 的早期路径漏计 regeneration_count
    # → _should_debug 第 425 行上限保护（regeneration_count < _MAX_REGENERATIONS）
    # 永远 0 < 1 成立 → 关键词持续命中时 generator↔executor 无限乒乓
    # （实测 fibonacci_inefficient 任务 trace 6000+ 行死循环）。
    # - 首次生成（iteration=0，diagnosis=None）：不改变 regeneration_count，保留原有
    #   diagnosis（尚无修复结论）
    # - 再生成：计数 +1（供 _should_debug 上限判断），并清空上一轮诊断，
    #   避免旧的 diagnosis 关键词在新测试仍失败时再次触发 regenerate（死循环根因）
    if (
        state.get("iteration", 0) >= state.get("max_iterations", MAX_ITERATIONS)
        or state.get("defect_type") == "test_defect"
        or (state.get("iteration", 0) > 0 and state.get("diagnosis") is not None)
        or _o4_triggered
        # W3（2026-10-05 审查落地·检出优先协议）：第 4 类再生成进入方式——
        # _should_debug 的 detection_first_all_green 分支（首轮全绿未检出）。
        # 特征 iteration==0 + test_passed=True 与首生成（test_passed=None）可区分，
        # 不并入本条件则该路径 regeneration_count 恒 0 → 上限保护失效 →
        # executor↔generator 无限乒乓直至 recursion_limit（O4 同类根因）。
        or _detection_first_regenerate_entry(state)
        # 修复引擎批次 III（AC2 补漏）：第 5 类再生成进入方式——特异性门
        # over_red 路由（test_passed=False，W3 检测不覆盖；不并入则该路径
        # 计数恒 0 → 上限失效 → executor↔generator 无限乒乓撞 recursion_limit，
        # E2 实证 16/174 触顶的根因通道）。
        or _specificity_over_red_regenerate_entry(state)
    ):
        update["regeneration_count"] = state.get("regeneration_count", 0) + 1
        update["diagnosis"] = None
        update["error_category"] = None
        # 3.1 双向诊断 + O4：重新生成测试后清空旧判定，避免"test_defect"信号
        # 在下一轮仍触发 regenerate（与 regeneration_count 上限共同防死循环）
        update["defect_type"] = None
        update["review_reason"] = None
    return update


# ─── ExecutorAgent 惰性单例（2026-09-28 性能优化）────────────────────────────
# _executor_node 每轮迭代 new 一个 ExecutorAgent。其构造仅存储沙箱配置
# （timeout/use_docker/use_venv/auto_install_deps/dep_install_timeout/
# docker_image），无内部可变状态：agent.execute() 每次调用独立构建沙箱、
# 运行 pytest、回收输出。沙箱参数全部来自 config 模块常量（进程内不变），
# 仅 execution_timeout 可经 CLI 注入——故按完整参数元组分键缓存实例：
# 同配置复用（省每轮构造 + 日志初始化），不同配置（--timeout 变体）各建一份，
# 并发下 DCL + 线程锁保证同键只构造一次。开关：
# AITESTER_EXECUTOR_AGENT_CACHE=0 关闭（默认启用，行为不变）。


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
    agent = _get_or_create_executor_agent(
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
    _consume_pending_repair = False
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
        # C10（2026-10-05 系统审查 P1）：修复案例验证门入库。上一轮写盘的
        # 补丁（_patch_applier_node 暂存 last_applied_repair）经本轮执行验证
        # 通过（test_passed=True）才进入修复案例库——失败/回滚补丁不再污染
        # 后续任务的 RAG 检索参考。入库后经下方 update dict 置 None 消费
        # （防重复入库）。
        _pending_repair = state.get("last_applied_repair")
        if _pending_repair and _pending_repair.get("patch"):
            rag_guarded(
                "add_repair",
                lambda r: r.add_repair(
                    original_code=_pending_repair.get("original_code", ""),
                    patch=_pending_repair.get("patch", ""),
                    error_category=_pending_repair.get("error_category", "unknown"),
                ),
                enabled=ENABLE_RAG,
                module_available=RAG_MODULE_AVAILABLE,
                retriever_cls=TestCaseRetriever,
                get_retriever=get_rag_retriever,
            )
            _consume_pending_repair = True

    # P0 运行时探针采集层（RUNTIME_PROBE_ENABLE=true 时启用，默认关）：
    # 测试失败时，经 sys.settrace 一次性探针捕获"失败时刻局部变量快照"，
    # 写入 state["runtime_probe_snapshot"] 供下一轮 _debugger_node 注入 prompt。
    # 纯观测层：探针失败 / 测试全过时 state["runtime_probe_snapshot"]=None，
    # 历史口径不变。默认关闭时零行为变化。
    runtime_probe_snapshot: dict[str, Any] | None = None
    if not result["passed"] and _runtime_probe_enabled():
        from src.agents.runtime_probe import capture_failure_snapshot

        runtime_probe_snapshot = capture_failure_snapshot(
            test_code=state.get("generated_test") or "",
            target_module=state.get("module_name"),
        )
        _trace_node(
            "runtime_probe",
            output_summary={
                "captured": runtime_probe_snapshot is not None,
                "frames": len((runtime_probe_snapshot or {}).get("frames", [])),
            },
            decision="probe_captured" if runtime_probe_snapshot else "probe_degraded",
            iteration=state.get("iteration", 0),
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

    update: dict[str, Any] = {
        "test_passed": result["passed"],
        "test_output": result["output"],
        "coverage_report": result["coverage"],
        "failed_cases": result["failed_cases"],
        "execution_trace": new_trace,
        "iteration_strategy_suggestion": strategy_suggestion,
    }
    # C10：验证门入库消费——入库完成的暂存补丁置 None（经 update dict
    # 合法通道回写，防下一轮重复入库）
    if _consume_pending_repair:
        update["last_applied_repair"] = None
    # R16（2026-10-05 审查 P1）：流氓 agent 行为监控消费点
    # （ROGUE_MONITOR_ENABLE=true 时启用，默认关零开销）。对四个核心
    # agent（BaseAgent 上报侧的 agent_id = 类名）做三类信号检测
    # （调用频率 z-score / 动作熵 / 能力违规），findings 非空写入
    # state["rogue_findings"]（纯观测，不改路由——隔离/升级由调用方决定，
    # 与 rogue_monitor 模块"只报警不熔断"口径一致）。
    if rogue_monitor_enabled():
        from src.agents.rogue_monitor import get_rogue_monitor as _get_rogue_monitor

        _rogue_findings: list[dict[str, Any]] = []
        _monitor = _get_rogue_monitor()
        for _agent_cls in ("PlannerAgent", "GeneratorAgent", "ExecutorAgent", "DebuggerAgent"):
            _rogue_findings.extend(
                {"agent_id": f.agent_id, "kind": f.kind, "detail": f.detail, "metric": f.metric}
                for f in _monitor.check(_agent_cls)
            )
        if _rogue_findings:
            logger.warning(
                "R16 流氓行为监控：%d 个 finding（%s）", len(_rogue_findings), [f["kind"] for f in _rogue_findings]
            )
            update["rogue_findings"] = _rogue_findings
    # R35/R31（2026-09-30 独立审查 P0）：flaky 门禁（FLAKY_CHECK_ENABLE=true
    # 时启用，默认关）。对**失败轮**做重复执行一致性检测：同 (target_code,
    # generated_test) 重跑 FLAKY_REPEAT_COUNT 次（默认 3），既有 pass 又有
    # fail → flaky（测试本身不稳定）。flaky 时 test_passed 保守记 False
    # （失败口径：不稳定结果不能作"修复正确"证据），并写 flaky_detected /
    # flaky_pass_count / flaky_total_count（统计层 flaky fraction 消费）。
    # 纯 subprocess（LLM 缓存命中下零成本）；仅失败轮触发（全绿即稳定，免重测）。
    if _flaky_check_enabled() and not result["passed"]:
        from src.agents.flaky_gate import detect_flaky as _detect_flaky

        _flaky = _detect_flaky(
            executor=agent,
            test_code=state.get("generated_test") or "",
            target_file=state.get("target_file") or "",
            target_function=state.get("target_function"),
            base_result=result,
        )
        update["flaky_detected"] = bool(_flaky["flaky"])
        update["flaky_pass_count"] = _flaky["pass_count"]
        update["flaky_total_count"] = _flaky["total"]
        if _flaky["flaky"]:
            logger.warning(
                "R35 flaky 检测：同测试 %d 次执行 %d 通过 / %d 失败（不稳定），test_passed 保守记 False",
                _flaky["total"],
                _flaky["pass_count"],
                _flaky["fail_count"],
            )
            # flaky 轮：结果不可信，保守按失败处理（不作"修复正确"证据）
            update["test_passed"] = False
            update["flaky_unverified"] = True
        else:
            # 全 fail（稳定失败）：结果可信，保留原 test_passed=False
            update["flaky_unverified"] = False
    # P0 运行时探针快照（RUNTIME_PROBE_ENABLE=true 时写入；默认关时不写，
    # 历史口径不变。None 表示探针未触发 / 降级；非 None 时含 frames 列表）
    if _runtime_probe_enabled():
        update["runtime_probe_snapshot"] = runtime_probe_snapshot
    # M5（2026-09-29 审查 P0）：测试重生成假通过标记。
    # 判定：本节点由"再生成"路由进入（regeneration_count > 0，即测试在
    # 当前轮或前轮被重新生成过）且本轮 test_passed=True。此时源码并未被
    # 修复（regenerate 路由不经过 debugger/patch_applier），测试重生成后
    # 通过**不等于缺陷被处理**——这是经典 oracle-from-implementation 假
    # 成功通道。写入 test_regenerated_pass_unverified 标记（纯观测，不改
    # 路由），供评估层把该类任务归入"未验证假通过"而非"修复成功"。
    if result["passed"] and int(state.get("regeneration_count", 0)) > 0:
        update["test_regenerated_pass_unverified"] = True
    # W3（2026-10-05 审查落地·检出优先协议，DETECTION_FIRST_ENABLE 默认关时
    # 零行为变化）：见 config.detection_first_enabled 协议说明。
    # - 首轮（iteration==0，被测代码未修复）执行：detection_first_red_seen 为
    #   **任务级粘性信号**——本轮红灯（测试让缺陷代码变红）或历史任一轮
    #   iteration==0 曾红过即为 True（再生成换一版测试不抹掉"系统曾检出"
    #   的事实；"当前这套测试"口径由 M5 test_regenerated_pass_unverified 单独标记）。
    # - 每轮执行后按 (passed, red_seen) 写三值终态标注（Y1 补失败终局，
    #   纯函数 _derive_detection_first_status）：red_then_green /
    #   all_green_unverified / red_not_repaired。最后一次写入即终态
    #   （LangGraph 后写覆盖）。
    if detection_first_enabled():
        if int(state.get("iteration", 0)) == 0:
            update["detection_first_red_seen"] = (not result["passed"]) or bool(state.get("detection_first_red_seen"))
        _df_red_seen = update.get("detection_first_red_seen", state.get("detection_first_red_seen"))
        _df_status = _derive_detection_first_status(bool(result["passed"]), _df_red_seen)
        if _df_status is not None:
            update["detection_first_status"] = _df_status
    # AC2（2026-10-06 第十轮审查 T-P0-4）：检出优先协议双门——
    # ①特异性门（DETECTION_SPECIFICITY_GATE_ENABLE，默认关）：首轮红时把
    #   当前测试在 gold fixed 代码上执行（复用 M1 原语），specific_red =
    #   缺陷特异红（放行修复循环）/ over_red = 过红（_should_debug 路由
    #   regenerate）/ unavailable = 无 gold 或不可判定（保守放行）；
    # ②红回归门（RED_REGRESSION_GATE_ENABLE，默认关）：曾见红 + 测试被
    #   再生成后变绿 + 源码未修补 = 抹红假成功——恢复红证人测试并保守
    #   置失败，交回修复循环走"修源码"通道（纯状态比较，零额外执行）。
    # 红证人快照随检出优先主开关注入（iteration==0 首轮红且非过红）。
    if detection_first_enabled():
        from src.tools.detection_gates import (
            detection_specificity_gate_enabled,
            red_regression_check,
            specificity_verdict,
        )

        _gate_passed = bool(update.get("test_passed", result["passed"]))
        if int(state.get("iteration", 0)) == 0 and not _gate_passed:
            _verdict: str | None = None
            if detection_specificity_gate_enabled():
                _verdict = specificity_verdict(
                    state.get("generated_test") or "",
                    state.get("gold_fixed_code"),
                    state.get("module_name"),
                )
                update["specificity_gate_verdict"] = _verdict
                logger.info("AC2 特异性门判定：%s", _verdict)
            if _verdict != "over_red":
                update["red_witness_test_code"] = state.get("generated_test")
        elif _gate_passed:
            _gate_upd = red_regression_check(state, state.get("generated_test") or "")
            if _gate_upd:
                update.update(_gate_upd)
                # 门②恢复后同步重推三值终态（本轮 test_passed 已被门改 False）
                _rv_status = _derive_detection_first_status(
                    False, update.get("detection_first_red_seen", state.get("detection_first_red_seen"))
                )
                if _rv_status is not None:
                    update["detection_first_status"] = _rv_status
                logger.warning("AC2 红回归门：再生成测试抹掉红证人（源码未修补），恢复红证人交回修复循环")
    # O3（2026-09-29 审查 P1）：分支覆盖率注入层（BRANCH_COVERAGE_INJECT_ENABLE=true
    # 时启用，默认关）。本节点在本地 / venv 沙箱执行完成后，用 coverage 模块
    # （subprocess 同解释器，独立临时数据文件）对 (target_file, generated_test)
    # 做 branch=True 测量，解析 coverage.json 的 missing_branches，写入
    # state["branch_coverage"]。纯观测层（不阻断主流程）；测量失败 / coverage
    # 不可用 / Docker 链路时 branch_coverage=None，历史口径不变。
    # Docker 链路（EXECUTOR_USE_DOCKER=true）暂不支持（O16 单独处理容器内
    # JSON 报告回传），本地 / venv 口径。
    if _branch_coverage_inject_enabled() and not EXECUTOR_USE_DOCKER:
        from src.tools.branch_coverage_inject import measure_branch_coverage as _measure_bc

        _bc_result = _measure_bc(
            target_file=state.get("target_file") or "",
            test_code=state.get("generated_test") or "",
            module_name=state.get("module_name") or "",
        )
        if _bc_result is not None:
            update["branch_coverage"] = _bc_result
    # M6（2026-09-29 审查 P0）：坏补丁失败回滚。
    # 当本轮 executor 判定失败（test_passed=False）且 state 中存在上一轮
    # 补丁快照（_last_patch_snapshot，由 _safe_write_patch 在写盘前写入）时，
    # 恢复原始代码，使修复质量不被坏补丁叠加污染。回滚成功后置
    # last_patch_rolled_back=True（纯观测，不参与路由），供评估层报告
    # "回滚成功率"。回滚失败（IO 异常）不阻断主流程。
    # O35：回滚成功必须经 update dict 把两个快照键清空——_rollback_last_patch
    # 内部的 state.pop 改写的是节点入参 dict，LangGraph 不回写（否则陈旧
    # 快照路径会留在 state，下一轮失败时重复回滚到更早的版本）。
    if not result["passed"]:
        # C6（2026-10-05 系统审查 P0）：磁盘与 state 同事务恢复——
        # restored_out 携带快照原文，写回 state["target_code"]，否则下一轮
        # Debugger 分析/补丁基底仍是坏补丁代码（"测原码/修补码"幻象迭代）。
        _restored: dict[str, Any] = {}
        _rolled_back = _rollback_last_patch(state, restored_out=_restored)
        if _rolled_back:
            update["last_patch_rolled_back"] = True
            update["_last_patch_snapshot"] = None
            update["_last_patch_iteration"] = None
            if "content" in _restored:
                update["target_code"] = _restored["content"]
        # C10：本轮失败 → 上一轮补丁未通过验证，丢弃暂存（不入修复案例库）
        update["last_applied_repair"] = None
    return update


# ─── BaseAgent 子类惰性单例复用（2026-09-28 性能优化）────────────────────────
# _debugger_node / _diagnosis_node 每轮迭代都 new 一个 DebuggerAgent()，而
# BaseAgent.__init__ 的实质工作是"查 llm_client 的客户端缓存（或新建
# ChatOpenAI 并锁内插缓存）"——循环修复（MAX_ITERATIONS 轮 × 多任务）下该
# 构造/查表开销线性累积。实例缓存的并发等价性：
# - BaseAgent 实例唯一状态 = self.llm（共享缓存客户端，线程安全）+
#   self.system_prompt（不可变构造参数，实例间同值）；
# - 实例方法不写实例字段（execute/debug 均走模块函数 + 共享缓存），
#   按类键单例与按次新建在任意并发模式下逐字节等价。
# 键 = 类名（str，稳定可哈希）；容量 16 + FIFO 淘汰（与 llm_client 客户端
# 缓存同口径）。开关：AITESTER_AGENT_REUSE=0 关闭（默认启用，行为不变）。


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
    #
    # 2026-10 P3（A/B 阴性结果驱动）：跨文件任务预置依赖边（_write_cross_file_state
    # 按 dep_chain 写入 state["cross_file_deps"]）时，本节点只对被调方
    # target_code（如 module_c）做 AST 分析——module_c 是被调方，其 import
    # 方向为反向（不 import 调用方 module_a/b）→ AST 分析 0 条边 → 覆盖预置边。
    # 修复：AST 分析结果为空、且预置边非空时，保留预置边（双向依赖图：被调方
    # 视角缺失的"调用方 → 被调方"反向边由 dep_chain 预置补全）。预置边为空时
    # 维持历史 AST 单视角口径（零行为变化）。
    _preset_deps = state.get("cross_file_deps") or []
    if deps:
        # AST 分析命中 → 用 AST 结果（历史口径）
        # O11（2026-09-29 审查 P1）：显式标记边来源为 AST 推导
        # （区别于 _write_cross_file_state 的 benchmark 层预置边）。
        # "source": "ast_derived" 使实验分析能区分两类边，
        # 跨文件 A/B 结论可外推的前提是两类边均非空。
        _ast_edges = [asdict(d) for d in deps]
        for _edge in _ast_edges:
            _edge["source"] = "ast_derived"
        update: dict[str, Any] = {"cross_file_deps": _ast_edges}
    elif _preset_deps:
        # AST 为空 + 预置边非空 → 保留预置边（双向依赖图反向补全）
        update = {"cross_file_deps": _preset_deps}
        logger.info(
            "3.5 跨文件修复：AST 单视角 0 条边，保留预置依赖边 %d 条"
            "（双向依赖图：被调方视角缺失的调用方反向边由 dep_chain 补全）",
            len(_preset_deps),
        )
    else:
        # 无 AST 边 + 无预置边 → 历史单文件降级口径
        update = {"cross_file_deps": []}

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
            # L4 逻辑修复（2026-09-29 审查）：source_files 一期仅含 entry
            # 模块（L1349-1351），被依赖模块（dep.target_module）源码未载入
            # → L1382 对非 entry 模块恒 "" 跳过。日志须如实反映"仅 entry
            # 模块生效"，避免高估已构建的模块数（二期扩展跨文件源码载入后
            # 此处可改回全模块口径）。
            logger.info(
                "P0 1.1 跨文件调用链上下文：构建 %d 个模块的聚焦上下文"
                "（depth=%d，当前仅 entry 模块 %s 生效——被依赖模块源码"
                "二期扩展后自动纳入）",
                len(focused_contexts),
                CODE_FOCUS_DEPTH,
                state.get("module_name") or os.path.basename(state.get("target_file") or ""),
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
    # S2 安全（2026-09-29）：dangerous_api_added 守卫——补丁新引入
    # os.system / subprocess / eval / 网络外连 / 凭证读取时拒绝应用
    # （开关 PATCH_DANGEROUS_API_GUARD，默认 true；与命名契约检查并列）。
    contract_missing: list[str] = []
    _naming_contract: tuple | None = None
    _dangerous_added: list[str] | None = None
    if applied and new_code != original_code:
        from src.tools.patch_applier import check_naming_contract, dangerous_api_added

        _naming_contract = check_naming_contract(original_code, new_code)
        ok, missing = _naming_contract
        # P0-4 性能（2026-10-01）：预计算 AST 危险差集，供下方 S2 双保险复用
        # （同一 (original, new) 输入只算一次，避免重复 ast.parse×2）
        _dangerous_added = dangerous_api_added(original_code, new_code)
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
        if applied:
            # S2 安全双保险（2026-09-29 审查）：危险操作拦截走正则
            # （injection_guard.check_llm_patch_safety，默认开）+ AST 差集
            # （patch_applier.dangerous_api_added，默认开）双通道。
            # 正则 findings 或 AST 差集非空即拒绝（保守不引入半应用状态）。
            from src.agents.injection_guard import check_llm_patch_safety

            _regex_hits = check_llm_patch_safety(new_code)
            # P0-4 性能（2026-10-01）：复用上方已算的 dangerous_api_added 结果，
            # 避免对同一 (original_code, new_code) 重复做 AST 差集（两遍
            # ast.parse×2）
            _added = _dangerous_added if _dangerous_added is not None else dangerous_api_added(original_code, new_code)
            _hits = list(dict.fromkeys(_regex_hits + _added))  # 去重保序
            if _hits:
                logger.warning("S2 危险操作拦截：补丁被拒绝（%s）", "、".join(_hits))
                applied = False
                new_code = original_code

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
                from src.tools.patch_applier import safe_apply_patch

                _try_code, _try_ok = safe_apply_patch(original_code, _extracted)
                if not _try_ok:
                    return None
                # P0-4 性能（2026-10-01）：safe_apply_patch 已对
                # (original_code, _extracted) 做过命名契约 + 危险 API 差集
                # （safe_apply_patch_contract 路径），此处重复调用是纯冗余
                # AST 解析。契约结果已由 safe_apply_patch 把关（_try_ok
                # 非 True 即代表契约/语法/危险 API 任一失败），此处仅保留
                # 契约检查用于收集 missing 符号供日志观测（缺失时保守返回
                # None 与原行为一致）。
                from src.tools.patch_applier import check_naming_contract as _ck

                _contract_ok, _missing = _ck(original_code, _try_code)
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

    # 默认视为"未真正写盘"，任何安全检查失败都保持该值。
    # O35（P1）：快照经出参取回（见 _safe_write_patch 的 snapshot_out 注释），
    # 再放进本函数**返回的 update dict**——只有经 update dict 才会被 LangGraph
    # 写回 channel，_rollback_last_patch（下一轮 executor）才读得到快照。
    _snapshot: dict[str, Any] = {}
    written = _safe_write_patch(original_code, new_code, applied, state, snapshot_out=_snapshot)

    # P0（2026-10-05 独立审查）：源码补丁证据门**真阻断**——文档契约
    # （patch_evidence.py / state.py：等级不足"拒绝写盘，源码保持原样"）
    # 此前未兑现：实现为"写盘后仅标记"，无证据补丁留在盘上，若下一轮
    # 测试恰好通过（迁就错误测试）坏补丁即固化（主批次 patch_correct=0/15
    # 的场景）。现对齐 fail-closed 契约（与 W12 快照失败拒绝写盘同文化）：
    # gate 启用（默认 true）+ 证据等级不足 → 恢复磁盘原文件 + written=False
    # （与"安全检查失败保持原代码"同口径，A-03 / M6 / history / 事件总线
    # 全部自然一致）；证据等级仍记录（消融对照不受影响）。
    _evidence_update: dict[str, Any] = {}
    if written:
        from src.tools.patch_evidence import (
            assess_patch_evidence,
            evidence_allows_write,
            patch_evidence_gate_enabled,
        )

        _ev_level = assess_patch_evidence(cast("dict[str, Any]", state), original_code, new_code)
        _evidence_update["patch_evidence_level"] = _ev_level
        if patch_evidence_gate_enabled() and not evidence_allows_write(_ev_level):
            _evidence_update["source_patched_unverified"] = True
            _disk_restored_ev = False
            try:
                _write_file_atomic(os.path.abspath(state.get("target_file", "")), original_code)
                _disk_restored_ev = True
            except Exception:
                logger.exception(
                    "证据门阻断恢复原文件失败：磁盘仍保留无证据补丁（target_file=%s）",
                    state.get("target_file"),
                )
            if _disk_restored_ev:
                written = False
                new_code = original_code
                _snapshot.clear()  # 与"安全检查拒绝"同构：无可回滚物，快照键不写 channel
                logger.warning(
                    "P0 源码补丁证据门：本轮补丁证据等级=%s（不足 gold/sbfl），"
                    "已恢复原文件（拒绝写盘，patch_applied=False）",
                    _ev_level,
                )
            else:
                # 恢复失败时如实降级为"写盘后标记"口径（C6 教训：磁盘与
                # 状态必须一致声明——盘上有补丁就不能声称拒绝写盘）
                logger.warning(
                    "P0 源码补丁证据门：等级=%s 不足但原文件恢复失败，"
                    "降级为写盘后标记口径（source_patched_unverified）",
                    _ev_level,
                )
        else:
            _evidence_update["source_patched_unverified"] = False

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
        # L1 逻辑修复（2026-09-29 审查）：同时补写 TypedDict 通道键
        # patch_syntax_invalid_flag（state.py:242 声明，refine_final_error_category
        # 经 final_state.get("patch_syntax_invalid_flag") 消费）——历史实现只写
        # error_category 字符串值，flag 通道恒 False（死通道），5.2 失败细化
        # 仅靠字符串路径兜底可达，与 TypedDict 契约脱节。双通道一致。
        resample_update["patch_syntax_invalid_flag"] = True
    # A-03（2026-10-04 系统审查 P0）：快照/P2P 全量回归/失败自动回滚协议
    # （PATCH_SNAPSHOT_ROLLBACK_ENABLE=true 时启用，默认 false 历史口径零变化）。
    # 协议：写盘后对"应用补丁后的代码"跑独立测试套件 P2P 回归——
    #   回归失败（rc=1 断言级）→ 自动回滚：target_code 恢复 original_code
    #     **且磁盘同步写回原文**（C6 2026-10-05：此前仅改 state 不写盘，
    #     状态与存储分叉；回滚落盘失败时如实记 rolled_back=False）；
    #   回归通过（rc=0）→ 保留补丁并标注 verdict=verified（M1 可消费）；
    #   无测试材料（no_oracle）/ 坏测试（regression_error）→ 保守保留补丁
    #     （不臆测测试、不误杀好补丁，由 M1 repair_rate 的 None 口径兜底）。
    # 观测字段（纯观测，不参与路由，与 spec_compile_rate 同档位）：
    #   patch_rollback_verdict: verified / regression_failed / no_oracle /
    #     regression_error / apply_failed / not_enabled
    #   patch_rolled_back: bool（True = 本轮补丁已被 P2P 回归失败回滚）
    if snapshot_rollback_enabled() and written:
        from src.tools.patch_rollback import PatchRollbackProtocol

        _pr_result = PatchRollbackProtocol().run(
            original_code=original_code,
            patch=state.get("patch") or "",
            test_code=state.get("generated_test") or "",
            module_name=state.get("module_name") or "module_under_test",
        )
        _verdict = _pr_result["verdict"]
        _rolled_back = bool(_pr_result["rolled_back"])
        if _rolled_back and _verdict == "regression_failed":
            # 自动回滚：target_code 恢复快照原文（written=False，patch_applied
            # 记 False——与"安全检查失败保持原代码"同口径，避免 Executor
            # 测回滚前代码、Debugger 分析回滚后代码的"幻象迭代"）
            # C6（2026-10-05 系统审查 P0）：同时恢复**磁盘**——此前仅改
            # state（effective_code/original_code）不写回 target_file，下一轮
            # executor 读磁盘测到的仍是"已回滚"的坏补丁代码，状态与存储分叉。
            effective_code = original_code
            written = False
            _disk_restored = False
            try:
                _write_file_atomic(os.path.abspath(state.get("target_file", "")), original_code)
                _disk_restored = True
            except Exception:
                logger.exception(
                    "A-03 回滚落盘失败：磁盘仍保留坏补丁（target_file=%s）",
                    state.get("target_file"),
                )
            # 磁盘未恢复时如实报告 rolled_back=False（避免下游把
            # "仅状态回滚"当作已恢复证据消费）
            _rolled_back = _disk_restored
            logger.warning(
                "A-03 P2P 回归失败，补丁已自动回滚（verdict=%s, snapshot=%s, disk_restored=%s）",
                _verdict,
                _pr_result["snapshot_id"],
                _disk_restored,
            )
        resample_update["patch_rollback_verdict"] = _verdict
        resample_update["patch_rolled_back"] = _rolled_back
    else:
        resample_update["patch_rollback_verdict"] = "not_enabled"
        resample_update["patch_rolled_back"] = False
    # 1.4 事件总线接线：PatchApplied（含 1.1 后处理标签，纯观测）
    # P0（2026-10-05 独立审查）：证据门判定已**前移**至写盘点之后
    # （_safe_write_patch 返回处）——阻断语义（等级不足恢复原文件、
    # written=False）必须在 A-03 快照回滚 / repair_history / 事件总线
    # 构造之前生效，否则下游基于"已写盘"的假象运行。此处仅剩
    # publish_patch_applied 消费阻断后的 written。
    publish_patch_applied(state, applied=written, new_code=effective_code)
    # O6（2026-09-29 审查 P1）：testless 修复验证层（TESTLESS_VALIDATION_ENABLE=true 时启用，默认关）。
    # 补丁应用成功后，经 run_testless_validation 对 (original_code, effective_code)
    # 做四层静态验证（AST 符号守卫 / mypy / 命名契约 / 导入冒烟），
    # 验证结果写入 state["testless_validation"]（纯观测，不阻断主流程）。
    # 开关关闭时零行为变化，历史口径不变。
    testless_validation_result: dict[str, Any] | None = None
    if written:
        from src.tools.testless_validation import run_testless_validation as _run_tlv
        from src.tools.testless_validation import testless_validation_enabled as _tlv_enabled

        if _tlv_enabled():
            try:
                testless_validation_result = _run_tlv(
                    original_code=original_code,
                    patched_code=effective_code,
                    target_module=state.get("module_name", ""),
                )
                if not testless_validation_result.get("passed", True):
                    logger.info(
                        "O6 testless 验证未通过（失败层: %s），标记为观测信号（不阻断主流程）",
                        testless_validation_result.get("failed_layers", []),
                    )
            except Exception:
                logger.debug("O6 testless 验证执行异常（保守跳过，保持历史口径）", exc_info=True)
    _testless_update: dict[str, Any] = {}
    if testless_validation_result is not None:
        _testless_update["testless_validation"] = testless_validation_result
    # C10（2026-10-05 系统审查 P1）：验证门修复案例暂存——写盘成功的补丁
    # 三元组（含写盘前原文）经 state["last_applied_repair"] 交给下一轮
    # executor：验证通过才 add_repair 入库，失败/回滚（written=False）置
    # None 丢弃。多候选胜出时补丁文本取 stats.applied_patch（胜出候选，
    # 而非 debugger 原始单补丁）。
    _repair_patch = state.get("patch") or ""
    _mc_stats_for_repair = multi_candidate_update.get("multi_candidate_stats") or {}
    if isinstance(_mc_stats_for_repair.get("applied_patch"), str) and _mc_stats_for_repair["applied_patch"]:
        _repair_patch = _mc_stats_for_repair["applied_patch"]
    _repair_stash_update: dict[str, Any] = (
        {
            "last_applied_repair": {
                "original_code": original_code,
                "patch": _repair_patch,
                "error_category": state.get("error_category") or "unknown",
            }
        }
        if written
        else {"last_applied_repair": None}
    )
    return {
        "target_code": effective_code,
        "repair_history": history,
        "iteration": state.get("iteration", 0) + 1,
        **multi_candidate_update,
        **contract_update,
        **feedback_update,
        **resample_update,
        **postprocess_update,
        **_testless_update,
        # P0（2026-09-30 独立审查 N9/R33）：源码补丁证据门（证据等级 +
        # 未验证标记，纯观测；opt-out 时 patch_evidence_level 仍记录）
        **_evidence_update,
        # O35（P1）M6 快照经 update dict 落 channel（仅写盘成功时写；
        # 写盘被拒时不写该键，保留上一轮尚待 executor 消费的快照，
        # 避免把"可回滚状态"提前清空）。
        **(
            {"_last_patch_snapshot": _snapshot["path"], "_last_patch_iteration": _snapshot["iteration"]}
            if "path" in _snapshot
            else {}
        ),
        # C10：验证门修复案例暂存（见上方注释）
        **_repair_stash_update,
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
