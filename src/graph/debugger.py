"""Debugger 节点模块（S7 拆分自 nodes.py，2026-10-08 R3）。

承载 _diagnosis_node / _debugger_node 及专属辅助
（_build_failure_frequency_section / _resolve_target_module）。nodes.py 通过
`from .debugger import ...` re-export，保持历史导入路径不变。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, cast

from config import (
    EXECUTOR_USE_DOCKER,
)
from src.agents.runtime_probe import build_probe_prompt_section
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
from src.graph.event_bus import (
    publish_debugger_diagnosed,
)
from src.graph.expert_pool import expert_pool_enabled

# S7（2026-10-08 R3）：功能开关辅助已拆分到 src/graph/flags.py，此处
# re-export 保持 `from src.graph.nodes import _xxx_enabled` 历史导入路径不变。
from src.graph.flags import (
    _failure_frequency_enabled,
    _fl_spectral_enabled,
    _probe_snapshot_locate_enabled,
    _runtime_probe_enabled,
)
from src.graph.rag import (
    TestCaseRetriever,
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
from src.tools.deterministic_repair import deterministic_repair_first_enabled

# 模块级 logger，用于记录节点执行过程，便于实验追踪和问题排查
logger = logging.getLogger(__name__)


# 修复历史上限：超过后仅保留最近 N 条，防止长迭代循环占用内存（经验值 5）
def _build_failure_frequency_section(state: AITesterState) -> str:
    """构建 ANNEAL-lite 故障频率强化提示片段（FAILURE_FREQUENCY_ENABLE=true 时非空）。

    保守口径：
    - 开关关闭 / repair_history 为空 / 非高频故障时返回空串（prompt 与历史逐字节一致）；
    - 高频故障时返回 failure_frequency.get_escalated_strategy_hint() 产出的强化提示
      （纯配置级策略映射表查询，零 LLM 成本）。
    """
    if not _failure_frequency_enabled():
        return ""
    from src.tools.failure_frequency import detect_high_frequency_failure, get_escalated_strategy_hint

    signal = detect_high_frequency_failure(
        repair_history=state.get("repair_history") or [],
        current_category=state.get("error_category"),
        target_module=state.get("module_name"),
    )
    if signal is None:
        return ""
    hint = get_escalated_strategy_hint(signal)
    if not hint:
        return ""
    logger.info(
        "ANNEAL-lite 故障频率检测：%s 在近 %d 轮中出现（阈值 %d），注入强化策略提示",
        signal.get("category"),
        signal.get("count", 0),
        signal.get("threshold", 2),
    )
    return hint


def _resolve_target_module(state: AITesterState) -> str | None:
    """2026-10 P0（A/B 阴性结果驱动）：解析定位/探针用的 target_module。

    跨文件任务（state 携带 cross_file_deps / cross_file_plan 的 target_modules）
    时，被调方真实模块名是依赖图里的 target_module（如 module_c），而
    state["module_name"] 是 task_id 末段（如 synthetic__xxx__test）——
    两者不一致会导致 _locate_repair_focus 的跨文件保护误判
    "traceback 帧文件名与 target_module 不符"而降级全文件修复
    （L3.5 三模块深链定位无法激活的根因）。

    解析口径（保守，单文件零变化）：
    - 跨文件任务（state.get("cross_file_deps") 非空）且 cross_file_plan
      携带 target_modules（analyze 节点解析出的被调方模块名列表）→
      取首元素；
    - 单文件任务 / 无 cross_file_deps / 无 target_modules → 取
      state["module_name"]（历史口径逐字节不变）。

    Args:
        state: 当前工作流状态。

    Returns:
        定位/探针用的 target_module（str），单文件任务恒为
        state["module_name"]。
    """
    cross_file_deps = state.get("cross_file_deps")
    if cross_file_deps:
        cross_file_plan = state.get("cross_file_plan") or {}
        target_modules = cross_file_plan.get("target_modules") or []
        if target_modules:
            return target_modules[0]
        # cross_file_plan 缺失时（analyze 节点未产出计划），回退到
        # cross_file_deps 里 target_module 字段去重集合的**末元素**
        # （依赖链末位 = 最内层被调用方，如 module_a → module_b → module_c
        # 中的 module_c；缺陷通常在最内层被调用模块）
        target_from_deps = [d.get("target_module") for d in cross_file_deps if d.get("target_module")]
        if target_from_deps:
            return target_from_deps[-1]
    return state.get("module_name")


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
    agent = _get_or_create_debugger_agent()
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
    # 延迟 import（非模块顶层）：从 src.graph.nodes 取 RAG 相关符号，使测试
    # patch("src.graph.nodes.ENABLE_RAG/RAG_MODULE_AVAILABLE/get_rag_retriever")
    # 的 mock 能作用到本函数（历史 mock 口径，与 agents_cache 的延迟 import 同源）。
    from src.graph.nodes import ENABLE_RAG, RAG_MODULE_AVAILABLE, get_rag_retriever

    agent = _get_or_create_debugger_agent()
    t0 = time.time()

    # 统一走 rag_guarded 降级守卫（P1 重构）：有失败用例时检索相似修复案例
    rag_refs_box: list = [None, 0, 0.0]  # [refs, relevance_filtered, relevance_filter_rate]
    if state.get("failed_cases"):

        def _on_retrieve_repairs(retriever) -> None:
            refs = retriever.retrieve_repairs(
                error_category=state.get("error_category", "unknown"),
                target_code=state["target_code"],
                top_k=2,
            )
            # P2 RAG 相关性评分 + 条件注入（2026-10 改进，A/B 阴性结果驱动）：
            # 1. 相关性阈值过滤：similarity < RAG_RELEVANCE_THRESHOLD 的案例
            #    不注入 prompt（避免"检索到但没用上"的噪声，默认关保持历史口径）；
            # 2. 条件注入门控：仅当有匹配案例时才注入（零结果不占位，默认关）。
            # 两开关均默认 false 时，refs 原样透传，行为与历史逐字节一致。
            if refs:
                from src.graph.rag import filter_by_relevance, should_inject_refs

                refs, _filtered_n, _filter_rate = filter_by_relevance(refs)
                _inject = should_inject_refs(refs, error_category=state.get("error_category"))
                refs = refs if _inject else []
                if not _inject:
                    logger.info(
                        "P2 RAG 条件注入：error_category=%s 无匹配案例，本轮不注入",
                        state.get("error_category"),
                    )
                rag_refs_box[1] = _filtered_n
                rag_refs_box[2] = _filter_rate
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
        # O2（2026-09-29 审查 P1）：谱系故障定位先验（FL_SPECTRAL_ENABLE=true
        # 时启用，默认关）。在 agent.debug 调用前，经 measure_fl_spectral_focus
        # 对 (target_file, target_code, generated_test, failed_cases) 做一次
        # Ochiai Top-k 测量（零 LLM 成本，subprocess + coverage 行级），
        # 把"Top-k 可疑行 + Ochiai 分数"渲染为定位先验段落注入修复 prompt。
        # 保守降级：测量失败 / coverage 不可用 / 无失败用例 / Docker 链路时
        # fl_spectral_focus=None，定位先验段落为空串，prompt 与历史逐字节一致。
        _fl_section: str = ""
        _fl_focus: dict[str, Any] | None = None
        if _fl_spectral_enabled() and not EXECUTOR_USE_DOCKER and state.get("failed_cases"):
            from src.agents.fl_spectral import (
                build_fl_spectral_prompt_section as _build_fl_section,
            )
            from src.agents.fl_spectral import (
                measure_fl_spectral_focus as _measure_fl,
            )

            _fl_focus = _measure_fl(
                target_file=state.get("target_file") or "",
                target_code=state.get("target_code") or "",
                test_code=state.get("generated_test") or "",
                failed_cases=state.get("failed_cases") or [],
                module_name=state.get("module_name") or "",
            )
            if _fl_focus is not None:
                _fl_section = _build_fl_section(_fl_focus)
                if _fl_section:
                    logger.info(
                        "O2 FL_spectral 定位先验注入：Top-%d 首行=%s",
                        len(_fl_focus.get("top_k", [])),
                        _fl_focus.get("top_k", [{}])[0].get("line"),
                    )
        # 修复引擎第一阶段（2026-10-07 范式转向）：RGFL 式 LLM 推理定位——
        # 谱系 Top-k 作佐证，LLM 输出结构化定位（函数/行/置信度），渲染为
        # 定位段落与谱系段落并列注入；结果写 state["llm_localization"]
        # 供实验层函数级命中指标消费。保守降级：开关关 / LLM 失败 / JSON
        # 解析失败 → None（不阻断修复主流程，历史口径零变化）。
        from src.agents.fault_localizer import (
            build_localization_prompt_section as _build_loc_section,
        )

        _loc_result: dict[str, Any] | None = None
        if state.get("failed_cases"):
            from src.agents.fault_localizer import FaultLocalizerAgent as _FLAgent
            from src.agents.fault_localizer import (
                build_gold_injection_localization as _build_gold_loc,
            )  # 修复引擎批次 X：反事实臂构造器 + 双开关（ruff I001 合并例外：保持可读）
            from src.agents.fault_localizer import (
                fault_localizer_enabled as _fl_enabled,
            )
            from src.agents.fault_localizer import (
                gold_injection_enabled as _gold_inj_on,
            )

            # 修复引擎批次 X（ADR-0024）：反事实 FL 上界臂——gold 注入开关
            # 开启且 state 带 gold 材料时，定位段直接用 gold 变更函数构造
            # （零 LLM，跳过推理通道），模拟"完美定位"。优先级高于
            # FAULT_LOCALIZER_ENABLE；该臂数据不得与正常口径混读
            # （reasoning 字段自带反事实臂标注）。
            if _gold_inj_on() and state.get("gold_fixed_code"):
                _loc_result = _build_gold_loc(
                    state.get("target_code") or "",
                    str(state.get("gold_fixed_code") or ""),
                )
            elif _fl_enabled():
                try:
                    _loc_agent = _FLAgent()
                    _loc_result = _loc_agent.localize(
                        target_code=state.get("target_code") or "",
                        test_code=state.get("generated_test") or "",
                        test_output=state.get("test_output") or "",
                        failed_cases=state.get("failed_cases") or [],
                        spectral_top_k=(_fl_focus or {}).get("top_k"),
                    )
                    if _loc_result is not None:
                        logger.info(
                            "FaultLocalizer 定位：fn=%s conf=%.2f",
                            _loc_result.get("function_name"),
                            _loc_result.get("confidence", 0.0),
                        )
                except Exception as _loc_err:  # 定位失败不阻断修复主流程
                    logger.warning("FaultLocalizer 异常，保守降级 None: %s", _loc_err)
                    _loc_result = None

        # ── 修复引擎批次 IV（ADR-0019）：确定性优先修复路由（默认关）──
        # DETERMINISTIC_REPAIR_FIRST_ENABLE 开启且本任务尚未尝试过
        # （state["deterministic_repair_status"] is None）时，先走确定性
        # 变换器（缺 import 推断 / 导入别名回填 / tab 缩进归一，零 LLM）；
        # 产出候选则跳过本轮 LLM 调用（省 token），由 executor 回归验证
        # 兜底——补丁无效时下一轮 state 已带 status，自然回落 LLM 路径
        # （每任务至多一次确定性尝试，防同签名无限重试）。
        _det_status: dict[str, Any] | None = None
        _det_result: dict[str, Any] | None = None
        if deterministic_repair_first_enabled() and state.get("deterministic_repair_status") is None:
            from src.tools.deterministic_repair import attempt_deterministic_repair

            _det = attempt_deterministic_repair(
                target_code=state["target_code"],
                test_output=state.get("test_output") or "",
                error_category=str(state.get("error_category") or ""),
            )
            _det_status = {
                "attempted": bool(_det.get("attempted")),
                "method": _det.get("method"),
                "reason": _det.get("reason"),
                "patch_produced": bool(_det.get("patch_code")),
            }
            if _det.get("patch_code"):
                from src.tools.deterministic_repair import build_deterministic_debug_result

                _det_result = build_deterministic_debug_result(
                    patch_code=str(_det["patch_code"]),
                    method=str(_det.get("method")),
                    reason=str(_det.get("reason")),
                    error_category=str(state.get("error_category") or ""),
                )
                logger.info("确定性接管命中（%s），跳过本轮 LLM 修复调用", _det.get("method"))

        if _det_result is not None:
            result = _det_result
        else:
            result = agent.debug(
                target_code=state["target_code"],
                test_output=state.get("test_output") or "",
                failed_cases=state.get("failed_cases") or [],
                rag_references=rag_refs,
                focus_function=state.get("target_function"),
                # 2026-10 P0（A/B 阴性结果驱动）：跨文件任务的定位/探针 target_module
                # 应取 cross_file_plan.target_modules[0]（被调方真实模块名，如 module_c），
                # 而非 state["module_name"]（task_id 末段，如 synthetic__xxx__test）。
                # 单文件任务两者一致（module_name = 被测文件名 stem），行为不变。
                target_module=_resolve_target_module(state),
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
                # P0 运行时探针注入层（RUNTIME_PROBE_ENABLE=true 时启用，默认关）：
                # 上一轮 _executor_node 在测试失败时经 sys.settrace 一次性探针捕获的
                # "失败时刻局部变量快照"，渲染为 prompt 片段注入修复上下文（运行时
                # 证据替代静态猜测，提升仓库级修复质量）。保守降级：快照为 None /
                # 开关关时 probe_section 为空串，prompt 与历史逐字节一致。
                probe_section=(
                    build_probe_prompt_section(state.get("runtime_probe_snapshot")) if _runtime_probe_enabled() else ""
                ),
                # P1 探针快照第二定位源（PROBE_SNAPSHOT_LOCATE_ENABLE=true 时启用，默认关）：
                # 把结构化探针快照（非渲染文本）透传给 debugger，使 _locate_repair_focus
                # 在 traceback 行号缺失（assertion 主导失败）时可用快照最内层帧定位。
                # 开关关闭 / 快照缺失时 probe_snapshot=None，debugger 走历史降级口径。
                probe_snapshot=(state.get("runtime_probe_snapshot") if _probe_snapshot_locate_enabled() else None),
                # 2026-10 P0（A/B 阴性结果驱动）：定位/探针 target_module 解析
                # （跨文件任务取 cross_file_plan.target_modules[0]，单文件取 module_name）
                # 注：target_module 已在调用首段传入（_resolve_target_module），
                # 此处不再重复传入——debug 调用的 target_module 即解析后的值。
                # ANNEAL-lite 故障频率强化（FAILURE_FREQUENCY_ENABLE=true 时启用，默认关）：
                # 检测当前 error_category 是否在 repair_history 中反复出现（≥ 阈值），
                # 高频时注入强化策略提示（如"优先启用 oracle_enhancer / runtime_probe"），
                # 引导 LLM 换更强修复路径。零 LLM 成本（纯配置级策略映射表查询）。
                # 默认关闭时 failure_frequency_section 为空串，prompt 与历史逐字节一致。
                failure_frequency_section=_build_failure_frequency_section(state),
                # O2（2026-09-29 审查 P1）：谱系定位先验段落（FL_SPECTRAL_ENABLE=true
                # 时非空；默认关 / 测量失败时为空串，prompt 与历史逐字节一致）
                fl_spectral_section=_fl_section,
                # 修复引擎第一阶段：RGFL 式推理定位段落（_loc_result 渲染；
                # None 时 build_localization_prompt_section 返回空串 = 不注入）
                localization_section=_build_loc_section(_loc_result),
                # R4（2026-10-08 局部编辑通道原型）：结构化定位结果透传
                # （与 localization_section 同源但未渲染），供 debug() 在
                # LOCALIZED_EDIT_ENABLE 开启时转化为 edit_intents 局部性约束。
                localization=_loc_result,
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

    # P2 并行专家 Agent 池（EXPERT_POOL_ENABLE=true 时启用，默认关）：
    # 在单 Agent 修复路径完成后，先经 ExpertPoolAgent.generate_parallel 并发调用
    # N 个专家子 Agent（各聚焦一个修复维度），再经 cross_validate 做两两一致性
    # 投票（过滤误报候选），取被验证数最高的候选作为本轮补丁。
    # 保守降级：专家池全失败 / 投票无达标候选时，保留单 Agent 路径产出的
    # result["patch"]，不引入劣化。开关默认关时本分支零执行，历史口径不变。
    expert_pool_meta: dict[str, Any] = {}
    # O13（2026-09-29 审查 P1）：策略银行独立于专家池——此前
    # STRATEGY_BANK_ENABLE 嵌套在 if expert_pool_enabled(): 内，单独开启
    # 策略银行（EXPERT_POOL_ENABLE=false）时策略检索永不触发（死开关）。
    # 现拆出独立条件：expert_pool_enabled() 或 strategy_bank_enabled() 时
    # 均检索策略。Z1（2026-10-06 审查修复）：prompt_hint 不再拼进 patch
    # 代码（自然语言混入代码，靠下游 AST 守卫兜底拒绝——浪费候选），
    # 改存 state 新声明键 strategy_bank_hint（观测 + 后续 prompt 注入挂点）。
    from src.tools.strategy_bank import select_strategy as _select_strategy
    from src.tools.strategy_bank import strategy_bank_enabled as _sb_enabled

    # Z1：本节点检出的策略提示文本（两条路径共用；None = 未检出/开关关，
    # 经 update["strategy_bank_hint"] 持久化，默认关时恒 None 键集合同构）
    _sb_hint: str | None = None

    if expert_pool_enabled():
        from src.graph.expert_pool import ExpertPoolAgent

        pool = ExpertPoolAgent()
        candidates = pool.generate_parallel(
            target_code=state["target_code"],
            test_output=state.get("test_output") or "",
            failed_cases=state.get("failed_cases") or [],
            rag_references=rag_refs,
            focus_function=state.get("target_function"),
            # P2-2（2026-10 批次）：把当前 error_category 传给专家池，
            # EXPERT_POOL_CATEGORY_CONDITIONED=true 时按类别重排维度
            # （命中维度排前，expert_count 不变）；开关 OFF 或类别为
            # None 时本参数零作用（维度表固定原序，历史口径零变化）。
            error_category=state.get("error_category"),
        )
        verified = pool.cross_validate(candidates, min_agreement=2)
        # G6 多 Agent 辩论收敛（EXPERT_POOL_DEBATE_ENABLE=true 时启用，默认关）：
        # 在 cross_validate 投票结果之上对 top-K 候选做"互辩修订"——
        # 产出一个综合修订版候选（吸收 top-K 共性修复点，规避各自弱点），
        # 修订候选非空时插入 verified 列表首位（优先级最高），不再与
        # top-K 重新投票（修订版是"综合版"，投票口径不适用）。
        # 保守降级：top-K 不足 2 / LLM 调用失败 / 空补丁时返回原 verified
        # 列表（不阻断主链路），标记 debate_revise=False。
        # 默认关时本分支零执行（expert_pool_debate_enabled() 恒 False），
        # 历史 cross_validate 口径不变。
        from src.graph.expert_pool import expert_pool_debate_enabled as _debate_enabled

        if verified and _debate_enabled():
            debate_result = pool.debate_round(
                verified=verified,
                target_code=state["target_code"],
                test_output=state.get("test_output") or "",
                failed_cases=state.get("failed_cases") or [],
                focus_function=state.get("target_function"),
            )
            if debate_result:
                verified = debate_result
                # 辩论胜出候选（修订版或原 top-K 首位）标记
                best_revise = debate_result[0].get("debate_revise", False)
                if best_revise:
                    logger.info("G6 辩论收敛：修订候选插入首位（top-K 综合版）")
                expert_pool_meta["debate_revise"] = best_revise
                expert_pool_meta["debate_top_k"] = len(debate_result) if best_revise else 0
        # 策略银行协同（STRATEGY_BANK_ENABLE=true 时）：按失败签名检索策略，
        # 把策略 prompt_hint 记录到 _sb_hint（零额外 LLM 成本，纯静态映射；
        # Z1：不再字符串拼进候选 patch——见上方 _sb_hint 初始化处注释）
        if verified and _sb_enabled():
            strategy = _select_strategy(
                error_category=state.get("error_category") or "unknown",
                fix_strategy_tag=state.get("fix_strategy_tag"),
                cross_file=bool(state.get("cross_file_deps")),
            )
            if strategy and strategy.get("prompt_hint"):
                _sb_hint = str(strategy["prompt_hint"])
        if verified:
            best = verified[0]
            # 专家池胜出候选替换单 Agent 补丁（保守：仅当单 Agent 补丁为空或
            # 专家池候选被更多专家投票通过时才替换）
            if not result.get("patch") or len(verified) >= 2:
                result["patch"] = best["patch"]
                result["expert_pool_winner"] = True
                # P2-3 ESDA Phase 2（2026-10 批次）：把策略银行的 (签名, 策略名,
                # 是否产出可执行补丁) 追加到 outcome 积累侧（record_strategy_outcome），
                # 供后续离线挖掘"哪类签名 + 哪条策略 历史成功率最高"。
                # 纯追加（不改写策略库 strategies 字段，零 LLM 成本）；写盘失败
                # 静默降级（纯观测层，不阻断修复主流程，与 record_strategy_outcome
                # 自身口径一致）。默认关（STRATEGY_BANK_ENABLE=false）时本段零执行，
                # 历史口径零变化。success=False 为占位（离线分析可结合 task_id
                # 关联后续执行结果做"真实成功率"归因，不预判本节点内结果）。
                if _sb_enabled() and strategy:
                    from src.tools.strategy_bank import record_strategy_outcome as _record_sb_outcome

                    _sb_signature = (
                        (state.get("error_category") or "unknown").strip().lower() or "unknown",
                        (state.get("fix_strategy_tag") or "").strip().lower() or None,
                        bool(state.get("cross_file_deps")),
                    )
                    _record_sb_outcome(
                        signature=_sb_signature,
                        strategy=str(strategy.get("strategy") or ""),
                        success=False,
                        task_id=str(
                            state.get("task_uuid") or ""
                        ),  # P1-6：task_id 未声明（死读恒 None），改读 task_uuid
                    )
                # M14（2026-09-29 审查 P0）：expert_pool_winner 此前写入 result
                # 但从未并入节点返回 dict（result 的键 ≠ update 的键），现并入
                # expert_pool_meta 供 state 消费。
                expert_pool_meta["expert_pool_winner"] = True
            # 多解合成（PRISM 式，EXPERT_POOL_ENABLE=true 且验证候选 ≥ 2 时）：
            # 对验证通过的多个候选做 AST 级修改区域检测——无重叠时合并为
            # 更完整方案（合成 = "从多个部分正确候选中拼出完整方案"，而非
            # "投票选最好的"）。保守降级：有重叠 / 语法校验失败 / 无多候选
            # 时保留投票胜出候选，不引入劣化。
            if len(verified) >= 2:
                # 合成输入须为"应用后的完整代码"（synthesize_candidates 契约：
                # new_code 参与 AST 区域 diff）。专家池候选自带 new_code 时
                # 直接使用（expert_pool.generate_parallel 已应用补丁）；否则
                # 经 static_validate_patch 应用补丁得到（静态筛选失败的候选
                # 无 new_code，跳过——无有效修改区域可供合成）。
                # 2026-09-30 审查修复：此前误把 c["patch"]（未应用的补丁文本）
                # 当 new_code 传入——补丁文本不是合法源码，区域 diff 全错，
                # 且 result["patch"] 可能被合成出的"非源码"覆盖写盘。
                from src.tools.multi_candidate import CandidateResult
                from src.tools.multi_candidate import static_validate_patch as _static_validate
                from src.tools.multi_candidate import synthesize_candidates as _synth_candidates

                synth_inputs: list[CandidateResult] = []
                for i, c in enumerate(verified):
                    _cp = str(c.get("patch") or "")
                    _applied = c.get("new_code")
                    if not _applied:
                        _sok, _sreason, _applied2 = _static_validate(state["target_code"], _cp)
                        _applied = _applied2 if _sok else None
                    if _applied:
                        synth_inputs.append(CandidateResult(index=i, patch=_cp, new_code=_applied, static_passed=True))
                synth_code, synth_labels = _synth_candidates(state["target_code"], synth_inputs)
                if synth_code:
                    result["patch"] = synth_code
                    result["expert_pool_winner"] = True
                    expert_pool_meta["synthesized"] = True
                    expert_pool_meta["expert_pool_winner"] = True
                    logger.info(
                        "多解合成：合并 %d 个无重叠候选，区域=%s",
                        len(verified),
                        synth_labels,
                    )
            # O35（2026-09-30 全面审查 P2）：此前这里是 `expert_pool_meta = {...}`
            # **整体重绑定**，而同一 if verified 分支上方刚写入的
            # expert_pool_winner / debate_revise / debate_top_k / synthesized
            # 属于旧 dict 对象——重绑定后全部丢失（这些键正是 M14 补声明时
            # 在 state.py 承诺可观测的字段）。改为 update() 原地合并。
            expert_pool_meta.update(
                {
                    "dimensions_consulted": len(candidates),
                    "verified_count": len(verified),
                    "winner_dimension": best.get("dimension"),
                    "agreed_dimensions": best.get("agreed_dimensions", []),
                    "expert_pool_applied": bool(best.get("patch")),
                }
            )
            logger.info(
                "P2 并行专家池：咨询 %d 个专家，投票通过 %d 个候选，胜出维度=%s（被 %d 个专家同意）",
                len(candidates),
                len(verified),
                best.get("dimension"),
                best.get("verified_count", 1),
            )
            _trace_node(
                "expert_pool",
                output_summary={
                    "dimensions_consulted": len(candidates),
                    "verified_count": len(verified),
                    "winner_dimension": best.get("dimension"),
                },
                decision=f"expert_{best.get('dimension')}",
                iteration=state.get("iteration", 0),
            )

    # C10（2026-10-05 系统审查 P1）：修复案例入库从"debugger 每轮无条件写入"
    # 改为"验证门写入"——_patch_applier_node 写盘成功时把补丁三元组暂存
    # state["last_applied_repair"]，_executor_node 验证通过后才 add_repair。
    # （此前此处每轮无条件 add_repair，未经验证（含最终失败/回滚）的补丁
    # 进入修复案例库，成为后续任务检索到的"参考修复案例"——记忆污染。）
    # O13（2026-09-29 审查 P1）：策略银行独立于专家池——专家池未启用时，
    # 若 STRATEGY_BANK_ENABLE=true 仍检索策略并记录提示文本
    # （零额外 LLM 成本，纯静态映射。Z1：prompt_hint 不再追加到
    # result["patch"]，改入 _sb_hint → state["strategy_bank_hint"]）。
    if not expert_pool_enabled() and _sb_enabled():
        _sb_strategy = _select_strategy(
            error_category=state.get("error_category") or "unknown",
            fix_strategy_tag=state.get("fix_strategy_tag"),
            cross_file=bool(state.get("cross_file_deps")),
        )
        if _sb_strategy and _sb_strategy.get("prompt_hint"):
            # Z1：不再以 result.get("patch") 非空为前提——提示文本与补丁
            # 是否产出解耦（空补丁轮次的策略命中同样有观测价值）
            _sb_hint = str(_sb_strategy["prompt_hint"])
            logger.info("O13 策略银行（独立路径）：记录 prompt_hint（error_category=%s）", state.get("error_category"))
    # 显式标注 dict[str, Any]：值类型混含 str / dict（adversarial_check），
    # mypy 按字面量推断为 dict[str, str | dict[str, int]] 导致后续
    # update["rag_stats"] = list[...] 赋值报错
    update: dict[str, Any] = {
        "diagnosis": result["root_cause"],
        "error_category": result.get("error_category", "unknown"),
        # P2-4（2026-10-05 独立审查）：规则分类置信度入 state（risk_approval
        # 置信度因子的信号源；此前该键未声明未写入，三因子恒缺一）
        "error_confidence": result.get("error_confidence"),
        # Z1（2026-10-06 审查修复）：策略银行提示文本入 state（新声明键，
        # 两条检索路径共用；默认关时恒 None，键集合同构）
        "strategy_bank_hint": _sb_hint,
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
        # P0 运行时探针注入层观测标志（_debugger_node 写入；RUNTIME_PROBE_ENABLE
        # 默认关 / 快照为 None 时恒 False，历史口径不变）
        "probe_section_applied": result.get("probe_section_applied"),
        # M14（2026-09-29 审查 P0）：专家池元数据并入 state（原为节点内死局部
        # 变量，6 处赋值从未写入返回 dict → 专家池/辩论假设不可证伪）。
        # 专家池未启用（EXPERT_POOL_ENABLE=false）时 expert_pool_meta 为初始
        # 空 dict，此处写 None 保持历史缺省口径；启用且运行后为结构化元数据。
        "expert_pool_meta": expert_pool_meta or None,
        # O2（2026-09-29 审查 P1）：谱系故障定位 Top-k 结果（FL_SPECTRAL_ENABLE=true
        # 时由 _debugger_node 经 measure_fl_spectral_focus 测量后写入；开关默认关 /
        # 测量失败时恒 None，历史口径不变）。
        "fl_spectral_focus": _fl_focus,
        # 修复引擎第一阶段（2026-10-07 范式转向）：RGFL 式 LLM 推理定位
        # （FaultLocalizer 结构化输出；开关关 / 失败 / 无失败用例时恒
        # None，历史口径零变化）。实验层消费：函数级命中指标
        # localization_hit_function（与 gold 变更函数集合比对）。
        "llm_localization": _loc_result,
        # 修复引擎批次 III（2026-10-07）：编辑意图确定性落盘观测
        # （EDIT_INTENT_ENABLE 默认关时恒 None；开启时 {"ok","applied",
        # "total","diagnostics"}，ok=False 表示锚点校验拒绝并回落
        # 整文件补丁通道——实验层据此统计意图通道接管率）。
        "edit_intent_status": result.get("edit_intent_status"),
        # R4（2026-10-08 局部编辑通道原型）：局部编辑合规观测
        # （LOCALIZED_EDIT_ENABLE 默认关时恒 None；开启时 {"localized_count",
        # "total","constrained","candidate_functions","violations",
        # "localized_ratio"}——定位信号被合成侧消费程度的行级观测）。
        "edit_localization": result.get("edit_localization"),
        # 修复引擎批次 IV（ADR-0019）：确定性优先修复路由观测
        # （DETERMINISTIC_REPAIR_FIRST_ENABLE 默认关时恒 None；开启且
        # 已尝试过一轮后非 None——{"attempted","method","reason",
        # "patch_produced"}，patch_produced=True 表示该轮跳过 LLM、
        # 补丁由确定性变换器产出）。
        "deterministic_repair_status": _det_status,
        # 5.4 预算封顶标记（O35）：Debugger 捕获 BudgetExceededError 时
        # error_category 已被置为 "budget_exceeded"（上方 except 分支），
        # 据此写 budget_exceeded=True；已由上游节点置真时同样保持（不回退）。
        # 此前 determine_stop_reason 的 BUDGET_EXCEEDED 分支无任何写入点，
        # 预算封顶任务在结果里恒被标成 max_iterations。
        "budget_exceeded": True
        if result.get("error_category") == "budget_exceeded" or state.get("budget_exceeded")
        else state.get("budget_exceeded"),
        # M14（2026-09-29 审查 P0）：_debugger_node 此前有 4 个返回键未在
        # AITesterState TypedDict 声明（adversarial_check / position_aware_focus
        # / type_repair_findings / mypy_findings_count），LangGraph 静默丢弃
        # 未声明键 → "已实现能力"不可度量。现补齐声明（state.py L227/L244/
        # L249），本行写入保留不变，消除静默丢弃。
    }
    # 累计 RAG 修复检索指标（P1 + P2 相关性观测）
    from src.graph.rag import _build_rag_stat_with_relevance

    repair_stat = _build_rag_stat_with_relevance(
        rag_refs,
        kind="repairs",
        relevance_filtered=rag_refs_box[1],
        relevance_filter_rate=rag_refs_box[2],
    )
    if repair_stat:
        update["rag_stats"] = [*list(state.get("rag_stats") or []), repair_stat]

    # M12（2026-09-29 审查 P0 + D.4-2 修复 2026-10-02）：风险分级人工回路暂停接线。
    # 历史口径：risk_approval.assess_task_risk 产出 risk_level/approval_action
    # 纯数据（JSON 字符串字段），但全仓无消费方把 approval_action 落成
    # LangGraph interrupt_before + checkpoint 的人工暂停。
    # D.4-2 修复：build_risk_summary 此前以 confidence=None / changed_files=None /
    # budget_ratio=None 调用，三因子中两个恒取默认值 → 风险分接近常量，
    # pause_requested 几乎永不触发。现传入真实信号：
    #   - confidence：error_classifier.classify_with_confidence 产出（state 键）
    #   - changed_files：cross_file_deps 长度（跨文件数代理）
    #   - budget_ratio / budget_exceeded：cost_budget.get_budget_stats() 实时值
    # 并配合 workflow.py M12 checkpointer 注入（MemorySaver），interrupt() 可
    # 真正暂停并等待人工 approve/reject（Command(resume=...) 恢复）。
    # 默认关时（RISK_APPROVAL_ENABLE=false）零行为变化（历史口径不变）。
    from src.graph.risk_approval import build_risk_summary as _build_risk_summary
    from src.graph.risk_approval import risk_approval_enabled as _risk_enabled

    if _risk_enabled():
        # M12 D.4-2：传入真实三因子（此前恒 None → 风险分接近常量）
        # P2-4（2026-10-05 独立审查）：error_confidence 已声明为 state 键
        # （debugger.classify_with_confidence 产出，_debugger_node 写入），
        # 此处读真实值；None（未运行 debugger / 旧路径）按保守高风险处理
        _confidence_val: float | None = state.get("error_confidence")
        _changed_files_val = len(state.get("cross_file_deps") or []) or None
        _budget_ratio_val: float | None = None
        _budget_exceeded_val: bool | None = None
        try:
            from src.budget.cost_budget import get_budget_stats

            _budget_stats = get_budget_stats()
            # 预算快照键：consumed_tokens / token_limit / consumed_usd / usd_limit
            _token_limit = int(_budget_stats.get("token_limit", 0) or 0)
            _consumed_tokens = int(_budget_stats.get("consumed_tokens", 0) or 0)
            _usd_limit = float(_budget_stats.get("usd_limit", 0.0) or 0.0)
            _consumed_usd = float(_budget_stats.get("consumed_usd", 0.0) or 0.0)
            # 取有值的维度计算 ratio
            if _token_limit > 0:
                _budget_ratio_val = _consumed_tokens / _token_limit
                _budget_exceeded_val = _consumed_tokens >= _token_limit
            elif _usd_limit > 0:
                _budget_ratio_val = _consumed_usd / _usd_limit
                _budget_exceeded_val = _consumed_usd >= _usd_limit
        except (ImportError, Exception):
            pass
        _risk_result = _build_risk_summary(
            confidence=_confidence_val,
            changed_lines=len([ln for ln in (result.get("patch") or "").splitlines() if ln.strip()]),
            changed_files=_changed_files_val,
            contract_missing_symbols=state.get("contract_missing_symbols"),
            full_file_patch=False,
            budget_ratio=_budget_ratio_val,
            budget_exceeded=_budget_exceeded_val,
        )
        if _risk_result.get("pause_requested"):
            from langgraph.types import interrupt  # 延迟导入：默认关时零导入开销

            _resume_value = interrupt(
                {
                    "reason": "M12 risk_approval pause",
                    "risk_level": _risk_result.get("risk_level"),
                    "approval_action": _risk_result.get("approval_action"),
                    "risk_score": _risk_result.get("risk_score"),
                }
            )
            # P2-4（2026-10-05 独立审查）：resume 值消费——人工审批决策记录入
            # state（此前仅判 None 不消费，审批结果丢失，回路闭环不完整）。
            # 决策语义（保守）：Command(resume=True/"approve") = 放行本轮补丁
            # 继续；其余值（False / "reject"）= 人工拒绝——保守丢弃本轮补丁
            # （patch 置空，路由走"无补丁"分支，不应用未审批的高风险修改）。
            _approved = _resume_value in (True, "approve", "approved")
            if _resume_value is not None:
                update["risk_approval_decision"] = {
                    "resume_value": _resume_value
                    if isinstance(_resume_value, (str, int, float, bool))
                    else str(_resume_value),
                    "approved": _approved,
                    "risk_level": _risk_result.get("risk_level"),
                }
                if not _approved:
                    logger.warning(
                        "M12 人工审批拒绝（resume=%r）：丢弃本轮高风险补丁（risk_level=%s）",
                        _resume_value,
                        _risk_result.get("risk_level"),
                    )
                    result["patch"] = ""
                    # 修复（2026-10-08 补测暴露）：update 字典已在节点前段用旧
                    # patch 值构造，仅置空 result["patch"] 不影响返回——须同时
                    # 置空 update["patch"] 才能真正丢弃高风险补丁（否则 M12
                    # "拒绝=丢弃"语义失效，未审批补丁仍被下游应用）。
                    update["patch"] = ""
            if _resume_value is None:
                logger.warning(
                    "M12 暂停未生效（无 checkpointer），继续工作流（risk_level=%s）",
                    _risk_result.get("risk_level"),
                )
    return update


__all__ = [
    "_build_failure_frequency_section",
    "_debugger_node",
    "_diagnosis_node",
    "_resolve_target_module",
]
