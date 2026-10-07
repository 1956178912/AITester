"""
调试修复师模块：分析测试失败并生成代码补丁。

引入分层错误修复机制（Hierarchical Repair Strategy）：
- SYNTAX 类：直接让 LLM 重写完整文件（无需语义分析）
- RUNTIME 类：分析异常栈，定位 bug 所在函数
- ASSERTION 类：判断是代码逻辑错误还是测试预期值错误
- TIMEOUT 类：检查死循环/无限递归，添加退出条件
- UNKNOWN 类：通用分析
支持 RAG 检索增强修复策略。

3.1 改进（对抗性推理机制，参考 ISSTA 2025 AdverIntent-Agent）：
    在分层修复基础上引入对抗性意图推理 + 批评者评估：
    1. 对抗性意图假设：LLM 在生成补丁前，先输出 2-3 个"对抗性程序意图"
       （攻击者/缺陷视角的假设：哪些输入/调用场景会击穿当前实现）；
    2. 针对性测试用例：为每个对抗性意图假设生成对应的测试用例
       （验证补丁是否真正覆盖了这些"被击穿"的场景）；
    3. 批评者评估：独立 LLM 调用扮演"批评者"，尝试构造能击穿补丁的
       对抗性测试用例；若批评者成功构造出击穿用例（all_passed=False），
       补丁需重新生成（迭代 1 次，仍失败则保留当前补丁并记录风险）。
    该机制默认关闭（ADVERSARIAL_DEBUGGING_ENABLE=true 启用），
    保持历史实验口径不变。

3.1 双向代码-测试诊断机制（BiVCoder 式 Review Agent，默认关）：
    在执行测试失败时，先由独立"审查智能体"判断根因是"实现缺陷"还是
    "测试缺陷"（参考 BiVCoder 的双向诊断）：
    1. implementation_defect（实现缺陷）：被测代码逻辑错误 → Debugger 修复代码；
    2. test_defect（测试缺陷）：测试自身设计错误（预期值写错 / 断言了错误行为）→
       返回 defect_type="test_defect"，由上层路由回 Generator 重新生成测试。
    该机制默认关闭（BIDIRECTIONAL_DIAGNOSIS_ENABLE=true 启用），
    未启用时 defect_type 恒为 "implementation_defect"（保持历史口径）。
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, cast

from src.agents.base_agent import BaseAgent
from src.agents.error_classifier import (
    ErrorCategory,
    ErrorClassifier,
    get_fix_strategy,
    get_recommended_fix_strategy,
)
from src.prompts.templates import DEBUGGER_SYSTEM_PROMPT
from src.tools.patch_intent import edit_intent_enabled
from src.tools.type_repair import type_repair_layer

# 模块级日志记录器
logger = logging.getLogger(__name__)

# ─── 魔数常量（统一管理，便于后续调整）─────────────────────────────────────
# 失败用例摘要最大展示数量：避免 prompt 过长导致 token 浪费
_MAX_FAILED_CASES_SUMMARY = 5
# 失败用例错误信息截断长度（字符数）：单条用例错误信息最长展示此长度
_FAILED_CASE_ERROR_TRUNCATE_LEN = 200
# RAG 修复参考案例最大数量：同时限制 each original_code 的截断长度
_MAX_RAG_REPAIR_REFS = 2
# RAG 参考案例中 original_code 截断长度（字符数）：避免 prompt 过长
_RAG_ORIGINAL_CODE_TRUNCATE_LEN = 500
# 3.1 改进：对抗性意图假设数量（AdverIntent-Agent 用 2-3 个，取 3 保证覆盖）
_ADVERSARIAL_INTENT_COUNT = 3
# 3.1 改进：对抗性测试用例最大长度（字符数）：注入 prompt 时截断
_ADVERSARIAL_CASE_TRUNCATE_LEN = 300
# 3.1 改进：批评者评估的击穿用例最大数量（避免 prompt 过长）
_MAX_CRITIC_BREAK_CASES = 3
# ───────────────────────────────────────────────────────────────────────────


def _adversarial_debugging_enabled() -> bool:
    """3.1 改进：对抗性推理机制开关（ADVERSARIAL_DEBUGGING_ENABLE=true 时启用，默认 false）。

    启用后 Debugger.debug 在生成补丁前会：
    1. 让 LLM 输出 2-3 个对抗性程序意图假设（攻击者视角的缺陷场景）；
    2. 为每个假设生成针对性测试用例；
    3. 独立"批评者"LLM 调用尝试构造击穿补丁的对抗性测试；
    若批评者成功（all_passed=False），触发一次补丁重新生成（仍失败则保留当前补丁）。
    """
    return os.getenv("ADVERSARIAL_DEBUGGING_ENABLE", "false").lower() == "true"


def _position_aware_repair_enabled() -> bool:
    """3.3 改进：位置感知迭代修复开关（POSITION_AWARE_REPAIR_ENABLE=true 时启用，默认 false）。

    参考 LoopRepair（位置感知 + 轨迹引导迭代修复）：在生成补丁前先做
    "修复位置定位"阶段——把 error_classifier 已提取的异常位置（traceback
    文件/行号、语法错误行列）经 AST 定位到所属函数/方法，生成"位置感知
    修复指引"注入补丁 prompt，让 LLM 优先修定位到的位置而非全文件盲搜。
    该定位是纯静态（不消耗 LLM token）；LLM 调用失败或无法定位时降级为
    常规全文件修复（保持历史口径，不因定位失败阻断修复）。
    """
    return os.getenv("POSITION_AWARE_REPAIR_ENABLE", "true").lower() == "true"


def _probe_snapshot_locate_enabled() -> bool:
    """P1 探针快照第二定位源开关（PROBE_SNAPSHOT_LOCATE_ENABLE=true 时启用，默认 false）。

    2026-10 改进（A/B 阴性结果驱动）：位置感知 A/B 定位命中 0/30，根因是
    合成集失败以 assertion 为主、无 traceback 行号，_locate_repair_focus
    的 context.line 恒 None 而直接降级全文件修复。本开关启用后：当
    traceback 行号缺失且 RUNTIME_PROBE_ENABLE 已产出探针快照时，用快照
    "最内层帧"的函数名 + 行号作为第二定位源，使纯 assertion 失败也能
    激活定位阶段。纯静态（零 LLM 成本），探针快照缺失/帧不可解析时
    保持历史降级口径。需同时启用 POSITION_AWARE_REPAIR_ENABLE 才生效。
    """
    return os.getenv("PROBE_SNAPSHOT_LOCATE_ENABLE", "false").lower() == "true"


def _bidirectional_diagnosis_enabled() -> bool:
    """3.1 双向代码-测试诊断开关（BIDIRECTIONAL_DIAGNOSIS_ENABLE=true 时启用，默认 false）。

    启用后 Debugger.debug 在生成补丁前先由 Review Agent 判断根因是
    "实现缺陷"（修复代码）还是"测试缺陷"（重新生成测试），实现 BiVCoder
    式的双向诊断与分支修复。默认关闭保持历史实验口径不变。
    """
    return os.getenv("BIDIRECTIONAL_DIAGNOSIS_ENABLE", "false").lower() == "true"


# ─── 1.3 分层压缩降级链（符号守卫拒绝后的收紧生成）────────────────────────────
# 与 patch_applier 的三级上下文档位（full_context / patch_ingredients /
# minimal）配套的 prompt 侧实现：_patch_applier_node 的符号守卫拒绝补丁时
# 调 advance_context_tier() 推进档位，并把 (档位名, 缺失符号) 作为
# contract_reject_feedback 经 _debugger_node 透传回本模块；本模块据此：
#   1. _build_downgrade_context：按档位构建"更高约束"的代码上下文
#      （patch_ingredients = 补丁配方保留片段；minimal = 签名+import 极简），
#      替代"全文件截断"——被拒轮次的 prompt 不再携带已破坏契约的大段代码；
#   2. _downgrade_tier_temperature：档位 → 温度映射（降级层更低温度，
#      减少"创造性改写"再破坏命名契约）；
#   3. 把缺失符号列表注入 prompt 负面反馈（"上轮补丁删除了这些符号，
#      必须保留"）。
# 默认（feedback 为 None）零行为变化，历史实验口径不变。


def _downgrade_tier_temperature(tier_name: str) -> float | None:
    """1.3 降级链：档位名 → LLM 温度映射（patch_applier 档位表同口径）。"""
    from src.tools.patch_applier import _CONTEXT_TIER_TEMPERATURES

    return _CONTEXT_TIER_TEMPERATURES.get(tier_name)


def _build_downgrade_context(
    original_code: str,
    focus_function: str | None,
    feedback: dict[str, Any],
) -> str:
    """1.3 降级链：按被拒档位构建收紧的代码上下文（纯静态，零 LLM token）。

    Args:
        original_code: 原始被测代码全文。
        focus_function: 焦点函数名（None 时各层退化为无焦点口径）。
        feedback: _patch_applier_node 透传的拒绝反馈，含
            {"tier": "patch_ingredients"|"minimal",
             "missing_symbols": [被守卫判定的缺失模块级符号]}。

    Returns:
        收紧后的上下文文本（"档位上下文 + 契约缺失符号负面反馈"）；
        该档位上下文构建失败（AST 解析失败等）时返回空串，调用方回退
        历史截断口径（保守降级，不阻断修复主流程）。
    """
    tier = str(feedback.get("tier", "minimal"))
    try:
        from src.tools.patch_applier import build_tiered_context

        tier_idx = 2 if tier == "minimal" else 1
        ctx = build_tiered_context(original_code, focus_function, tier=tier_idx)
    except Exception as e:  # 构建失败必须保守降级（空串）
        logger.warning("1.3 降级链上下文构建失败（回退历史截断口径）: %s", e)
        return ""
    if not ctx:
        return ""
    missing = feedback.get("missing_symbols") or []
    if missing:
        ctx += (
            f"\n\n【契约守卫负面反馈】上一轮补丁删除了以下必须保留的模块级符号：{', '.join(sorted(missing)[:10])}。"
            "本轮修复必须原样保留这些符号（名称/定义均不得删除或重命名），"
            "只允许修改函数/方法体内部逻辑。"
        )
    return ctx


class DebuggerAgent(BaseAgent):
    """
    调试修复师：分析测试失败，输出根因诊断、错误分类和代码补丁。

    引入分层错误修复机制，根据错误类型采用不同策略：
    1. 先用规则分类器快速判断错误类型（不消耗 LLM token）
    2. 将错误类型及对应修复策略注入 prompt，引导 LLM 按类修复
    3. 若提供 RAG 参考，注入历史修复案例增强生成质量

    错误分类策略:
        - SYNTAX: 语法错误，直接让 LLM 重写完整文件
        - RUNTIME: 运行时异常，分析异常栈定位 bug
        - ASSERTION: 断言失败，判断是代码逻辑错误还是测试预期值错误
        - TIMEOUT: 超时，检查死循环/无限递归
        - UNKNOWN: 通用分析

    输入:
        target_code: 被测代码全文。
        test_output: 测试失败输出。
        failed_cases: 失败用例列表。
        rag_references: RAG 检索到的相似修复案例（可选）。

    输出:
        包含 root_cause、error_category、fix_strategy、patch 的字典。

    使用示例:
        >>> agent = DebuggerAgent()
        >>> result = agent.debug(
        ...     target_code="def add(a, b): return a - b",
        ...     test_output="AssertionError: expected 5, got -1",
        ...     failed_cases=[{"name": "test_add", "error": "expected 5, got -1"}],
        ... )
        >>> result["error_category"]
        <ErrorCategory.ASSERTION: 'assertion'>
    """

    def __init__(self) -> None:
        # 使用分层修复专用 system prompt
        super().__init__(DEBUGGER_SYSTEM_PROMPT)
        # 实例化分类器，用于在调用 LLM 前先确定错误类型（不消耗 LLM token）
        self.classifier = ErrorClassifier()

    def debug(
        self,
        target_code: str,
        test_output: str,
        failed_cases: list[dict[str, str]],
        rag_references: list[dict[str, Any]] | None = None,
        focus_function: str | None = None,
        target_module: str | None = None,
        temperature: float | None = None,
        cross_file_contexts: dict[str, str] | None = None,
        contract_reject_feedback: dict[str, Any] | None = None,
        probe_section: str | None = None,
        failure_frequency_section: str | None = None,
        probe_snapshot: dict[str, Any] | None = None,
        # O2（2026-09-29 审查 P1）：谱系定位先验段落（FL_SPECTRAL_ENABLE=true
        # 时由 _debugger_node 经 measure_fl_spectral_focus 测量并经
        # build_fl_spectral_prompt_section 渲染传入）。None / 空串时不注入，
        # 历史口径零变化。
        fl_spectral_section: str | None = None,
        # 修复引擎第一阶段（2026-10-07 范式转向）：RGFL 式 LLM 推理定位段落
        # （FaultLocalizerAgent.localize 产出，经 build_localization_prompt_section
        # 渲染传入）。None / 空串时不注入，历史口径零变化。
        localization_section: str | None = None,
    ) -> dict[str, Any]:
        """
        分析测试失败并生成修复补丁。

        流程：
        1. 先用规则分类器确定错误类型（快速，不消耗 LLM token）
        2. 将错误类型及对应修复策略注入 prompt，引导 LLM 按类修复
        3. 若提供 RAG 参考，注入历史修复案例增强生成质量
        4. 3.1 双向诊断（默认关）：若启用，先由 Review Agent 判断根因是
           实现缺陷还是测试缺陷；测试缺陷时直接返回不生成补丁
        5. 3.1 改进（对抗性推理，默认关）：若启用，在补丁生成前注入
           对抗性意图假设 + 针对性测试用例，生成后再经"批评者"评估，
           若被击穿则重新生成一次补丁

            9. 3.3 改进（位置感知迭代修复，默认关）：若启用，在补丁生成前
               把异常位置（traceback 行号/语法错误行列）经 AST 定位到所属
               函数，生成"位置感知修复指引"注入 prompt，让 LLM 优先修定位
               到的位置（LoopRepair 式先定位再补丁）；无法定位时降级常规修复

        Args:
            target_code: 被测代码全文。
            test_output: 测试失败输出。
            failed_cases: 失败用例列表，每个元素为 {"name": str, "error": str}。
            rag_references: RAG 检索到的相似修复案例，每项含 patch 字段。
            focus_function: 焦点函数名（可选）。超长代码时按该函数做 AST
                智能截取，保留目标函数及直接依赖，提升修复定位精度。
            target_module: 被测模块名（可选）。提供时断言失败可进一步
                区分 ASSERTION（代码 bug）与 LOGIC_ERROR（测试预期值写错）。
            temperature: 采样温度覆盖（可选，3.3 动态策略接线用）；None 时
                沿用 config.TEMPERATURE。
            cross_file_contexts: P0 1.1 分层代码压缩——跨文件任务的各模块
                聚焦上下文 {module_name: focused_code}（由 cross_file_analyzer
                按 CODE_FOCUS_DEPTH 层调用链构建，纯静态）。非 None 时注入
                prompt，供 LLM 跨文件修复时理解被调模块接口；None 为历史口径。
            failure_frequency_section: ANNEAL-lite 故障频率强化提示（默认关
                FAILURE_FREQUENCY_ENABLE）。当同一 error_category 在近期迭代
                中反复出现（≥ 阈值）时，由 failure_frequency 模块生成的
                强化策略提示文本（如"优先启用 oracle_enhancer 重新生成断言"），
                注入 prompt 尾部引导 LLM 换一条更强的修复路径。None / 空串
                时 prompt 与历史逐字节一致（保守降级）。

        Returns:
            包含以下键的字典：
            - root_cause (str): 根因分析。
            - error_category (str): 错误类型枚举字符串。
            - fix_strategy (str): 修复策略描述。
            - patch (str): 修复后的完整代码（含代码块标记）。
            - adversarial_check (dict): 3.1 对抗性推理结果（启用时含
              intent_hypotheses / critic_break_cases / all_passed；
              未启用时 scenarios_checked=0, all_passed=False）。
            - defect_type (str): 3.1 双向诊断结果（implementation_defect /
              test_defect；未启用时恒为 implementation_defect）。
            - review_reason (str): Review Agent 判定依据（未启用时为空串）。
            - position_aware_focus (dict): 3.3 位置感知修复定位结果（启用时
              focused=True 且 hint 非空，function_name/line 为定位到的函数与行号；
              未启用或无法定位时 focused=False, hint=""）。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # Step 1: 用规则分类器快速判断错误类型（不消耗 LLM token）
        # target_module 提供时，断言失败可区分 ASSERTION 与 LOGIC_ERROR（P2 细化）
        # P2-4（2026-10-05 独立审查）：改走 classify_with_confidence（fallback 关闭
        # 时分类结果与 classify 逐样本等价），置信度随返回 dict 写 state
        # error_confidence——risk_approval 三因子风险的"错误置信度"因子此前
        # 恒 None 占位，接线后真实信号可用。
        _cls_result = self.classifier.classify_with_confidence(
            test_output,
            target_module=target_module,
            failed_cases=failed_cases,
            enable_fallback=False,
        )
        error_category = _cls_result.category
        error_confidence: float = _cls_result.confidence
        # Step 2: 提取错误上下文（含 traceback 行号/语法错误行列，3.3 位置感知复用）
        context = self.classifier.extract_error_context(test_output, failed_cases)
        # Step 2b: 获取对应修复策略描述
        strategy_text = get_fix_strategy(error_category, context=context)
        # 2.1 P1 改进：分类器输出附带结构化修复策略标签（get_recommended_fix_strategy
        # 把"该走哪条修复路径"从 workflow/debugger 的隐式分支收敛为分类器
        # 的显式输出；本轮标签随返回 dict 写入 state，供实验分析消费）
        _strategy_record = get_recommended_fix_strategy(error_category, context=context)
        # 记录分类结果，便于日志追踪和实验分析
        logger.info("错误分类结果: %s", error_category.value)

        # 截断超长代码，节省 token（大文件按焦点函数做 AST 智能截取，
        # P0 1.1 调用链展开层数由 CODE_FOCUS_DEPTH 控制，默认 1 = 历史行为）
        # 2026-09-26 全面审查（P1 正确性）：先保留原始全文副本——3.3 位置
        # 感知修复（_locate_repair_focus）依赖 context.line（pytest traceback
        # 的原始行号）在**原始**源码中定位，截断版（头尾保留中间省略）会
        # 使行号偏移或目标函数被整体丢弃 → focused=False 降级全文件修复。
        original_target_code = target_code
        # 1.3 分层压缩降级链：上一轮补丁被命名契约符号守卫拒绝时
        # （contract_reject_feedback 非空，由 _patch_applier_node 经
        # _debugger_node 透传），按被拒档位构建"更高约束"的代码上下文
        # （补丁配方保留 / 签名+import 极简）并注入契约缺失符号负面反馈；
        # 未触发时截断口径与历史完全一致（零回归）。
        tiered_ctx_text = ""
        if contract_reject_feedback:
            tiered_ctx_text = _build_downgrade_context(original_target_code, focus_function, contract_reject_feedback)
        if tiered_ctx_text:
            target_code = tiered_ctx_text
            # mypy：收窄到此处保证非 None（上方 if contract_reject_feedback 后不再为 None）
            _feedback = cast("dict[str, Any] | None", contract_reject_feedback)
            logger.info(
                "1.3 降级链：上一轮补丁被符号守卫拒绝（%s），本轮上下文降级为%s档（%d 字符）",
                ",".join((_feedback or {}).get("missing_symbols", [])[:5]) or "未知缺失",
                (_feedback or {}).get("tier", "minimal"),
                len(tiered_ctx_text),
            )
        else:
            target_code = BaseAgent.truncate_code(target_code, focus_function=focus_function)
        # 截断超长测试输出，保留关键错误信息（测试输出非源码，不做 AST 截取）
        test_output = BaseAgent.truncate_code(test_output, max_chars=1500)

        # 构建失败用例摘要（最多展示前 _MAX_FAILED_CASES_SUMMARY 个，避免 prompt 过长）
        # 每条用例的错误信息截断至 _FAILED_CASE_ERROR_TRUNCATE_LEN 字符
        cases_summary = "\n".join(
            [
                f"- {case['name']}: {case['error'][:_FAILED_CASE_ERROR_TRUNCATE_LEN]}"
                for case in failed_cases[:_MAX_FAILED_CASES_SUMMARY]
            ]
        )

        # ── 3.1 双向代码-测试诊断（BiVCoder 式 Review Agent，默认关）──────
        # 在执行测试失败时，先由独立"审查智能体"判断根因是"实现缺陷"还是
        # "测试缺陷"：实现缺陷 → 继续生成代码补丁；测试缺陷 → 不生成补丁，
        # 返回 defect_type="test_defect" 由上层路由回 Generator 重新生成测试。
        defect_type = "implementation_defect"
        review_reason = ""
        if _bidirectional_diagnosis_enabled():
            review = self._run_review_diagnosis(target_code, test_output, failed_cases, error_category.value)
            defect_type = review.get("defect_type", "implementation_defect")
            review_reason = review.get("reason", "")
            logger.info("双向诊断（3.1）Review Agent 判定：%s（%s）", defect_type, review_reason[:80])
            if defect_type == "test_defect":
                # 分支修复：测试缺陷 → 不修代码，返回信号让上层重新生成测试
                return {
                    "root_cause": review_reason or "测试本身存在缺陷（Review Agent 判定）",
                    "error_category": error_category.value,
                    "error_confidence": error_confidence,
                    "fix_strategy": "重新生成测试（测试缺陷，非实现缺陷）",
                    "patch": "",
                    "adversarial_check": {"scenarios_checked": 0, "all_passed": False, "critic_degraded": False},
                    "defect_type": defect_type,
                    "review_reason": review_reason,
                }

        # 在 prompt 中显式注入错误类型和修复策略，引导 LLM 分层处理
        # P0 1.3 契约验证：在 prompt 中加入命名契约约束，防止 LLM 重写
        # 时删除/重命名模块级符号（sqlfluff 插件命名契约 / 注册装饰器 /
        # __all__ 导出 / 模块级常量）导致 import 链崩溃。
        _CONTRACT_CONSTRAINT = (
            "\n【命名契约约束】不得修改或删除以下符号（函数名、类名、模块级导出符号、"
            "注册装饰器、插件入口点、__all__ 条目）。"
            "修复时只能修改函数/方法体的内部逻辑，保持所有公共接口名称不变。"
            "若必须删除某个符号，请在补丁注释中明确说明理由。"
        )
        query = (
            f"【错误类型】{error_category.value}\n"
            f"【修复策略】{strategy_text}\n"
            f"{_CONTRACT_CONSTRAINT}\n"
            f"被测代码：\n```\n{target_code}\n```\n\n"
            f"测试输出：\n```\n{test_output}\n```\n\n"
            f"失败用例：\n{cases_summary}"
        )

        # P0 运行时探针注入层（RUNTIME_PROBE_ENABLE=true 时启用，默认关）：
        # 探针快照经 nodes._debugger_node 渲染为 probe_section 字符串注入
        # prompt 尾部（运行时证据替代静态猜测）。probe_section 为空串 / None
        # 时 prompt 与历史逐字节一致（保守降级）。
        if probe_section:
            query += probe_section
            logger.info("运行时探针（P0）注入 %d 字符快照片段", len(probe_section))

        # ANNEAL-lite 故障频率强化（FAILURE_FREQUENCY_ENABLE=true 时启用，默认关）：
        # 当同一 error_category 在近期迭代中反复出现（≥ 阈值），注入强化策略
        # 提示（如"优先启用 oracle_enhancer / runtime_probe"），引导 LLM 换
        # 更强的修复路径而非继续用同一策略碰运气。None / 空串时不注入
        # （prompt 与历史逐字节一致，保守降级）。
        if failure_frequency_section:
            query += "\n\n" + failure_frequency_section
            logger.info("ANNEAL-lite 故障频率强化注入 %d 字符提示", len(failure_frequency_section))

        # O2（2026-09-29 审查 P1）：谱系定位先验段落（FL_SPECTRAL_ENABLE=true
        # 时非空；None / 空串时不注入，prompt 与历史逐字节一致，保守降级）
        if fl_spectral_section:
            query += "\n\n" + fl_spectral_section
            logger.info("O2 FL_spectral 定位先验注入 %d 字符提示", len(fl_spectral_section))

        # 修复引擎第一阶段（2026-10-07 范式转向）：RGFL 式推理定位段落
        # （FaultLocalizer 结构化定位注入；None / 空串时不注入，历史口径零变化）
        if localization_section:
            query += "\n\n" + localization_section
            logger.info("FaultLocalizer 定位段落注入 %d 字符提示", len(localization_section))

        # P0 1.1 分层代码压缩：跨文件任务时注入"被调模块的聚焦上下文"
        # （extract_function_context 按调用链截取，非整模块全文），让 LLM
        # 修复跨文件缺陷时理解被调模块的接口契约；每模块 2000 字符预算，
        # 总预算 4000 字符（_CROSS_FILE_CONTEXT_MAX_CHARS）。
        if cross_file_contexts:
            _CROSS_FILE_CONTEXT_MAX_CHARS = 4000
            _CROSS_FILE_MODULE_MAX_CHARS = 2000
            module_sections = []
            total_chars = 0
            for module_name, focused_code in cross_file_contexts.items():
                snippet = (focused_code or "")[:_CROSS_FILE_MODULE_MAX_CHARS]
                if total_chars + len(snippet) > _CROSS_FILE_CONTEXT_MAX_CHARS:
                    break
                total_chars += len(snippet)
                module_sections.append(f"【依赖模块 {module_name}（调用链聚焦视图）】\n```python\n{snippet}\n```")
            if module_sections:
                query += (
                    "\n\n以下是被测代码依赖的其他模块的调用链聚焦视图（目标函数及其 1-2 层被调函数），"
                    "修改跨文件缺陷时须保持这些模块的接口契约：\n" + "\n\n".join(module_sections)
                )
                logger.info("跨文件聚焦上下文注入 %d 个模块（P0 1.1）", len(module_sections))

        # RAG 增强：若检索到相似修复案例，注入参考补丁
        # 最多取前 _MAX_RAG_REPAIR_REFS 个案例
        # 同时截断 original_code 至 _RAG_ORIGINAL_CODE_TRUNCATE_LEN 字符，避免 prompt 过长
        # P2 RAG 判断指令（2026-10 改进，RAG_RAG_JUDGE_INSTRUCTION_ENABLE=true 时启用，默认关）：
        # 注入"以下历史案例仅供参考，若与当前错误类型/代码上下文不匹配请忽略"指令，
        # 让 LLM 自主判断相关性而非盲目拼接（ContextSniper 式"先筛选再注入"的
        # prompt 侧配套）。默认关时 prompt 与历史逐字节一致。
        if rag_references:
            refs_text = []
            for i, ref in enumerate(rag_references[:_MAX_RAG_REPAIR_REFS], start=1):
                orig = ref.get("original_code", "")[:_RAG_ORIGINAL_CODE_TRUNCATE_LEN]
                patch = ref.get("patch", "")
                if orig and patch:
                    refs_text.append(
                        f"【参考修复案例 {i}】\n原始代码：\n```python\n{orig}\n```\n修复代码：\n```python\n{patch}\n```"
                    )
            if refs_text:
                _rag_header = "\n\n以下历史修复案例可作为参考："
                if os.getenv("RAG_JUDGE_INSTRUCTION_ENABLE", "false").lower() == "true":
                    _rag_header += (
                        "【判断指令】以下案例仅供参考，若与当前错误类型或代码上下文不匹配请忽略，不要强行套用历史补丁。"
                    )
                query += _rag_header + "\n" + "\n\n".join(refs_text)
                logger.info("Debugger 使用了 %d 个 RAG 修复参考", len(refs_text))

        # ── 4. 失败知识库闭环（落点 B，默认关 FAILURE_KB_ENABLE）──────────
        # 离线 accumulate（analyze_failures.py -k）→ 在线消费：按当前 error_category
        # 匹配知识库条目（频次 × 时间衰减排序），注入针对性修复方向片段。
        # 开关关闭 / 知识库缺失 / 无匹配条目时返回 None，prompt 与历史逐字节一致。
        # 追加到既有 prompt 尾部（不替换历史模板，保守口径）。
        from src.agents.failure_kb import kb_debugger_snippet

        _kb_snippet = kb_debugger_snippet(error_category.value)
        if _kb_snippet:
            query += "\n\n" + _kb_snippet
            logger.info("失败知识库闭环（4. 落点 B）注入了同类案例提示（类别=%s）", error_category.value)

        # ── 修复引擎第二阶段（批次 III）：结构化编辑意图输出契约（默认关）──
        # EDIT_INTENT_ENABLE=true 时要求 LLM 在 JSON 中附加 edit_intents
        # 字段（唯一锚点 search/replace 意图），供下方确定性引擎最小化落盘
        # （arXiv:2609.00227：宽容 diff ~1/7 静默错应用 → LLM 产意图、
        # 确定性管道执行）。开关关时 prompt 与历史逐字节一致。
        _edit_intent_on = False
        if edit_intent_enabled():
            from src.tools.patch_intent import EDIT_INTENT_PROMPT_SECTION

            _edit_intent_on = True
            query += "\n\n" + EDIT_INTENT_PROMPT_SECTION
            logger.info("编辑意图输出契约注入（EDIT_INTENT_ENABLE）")

        # ── 3.1 改进（对抗性推理机制，默认关）─────────────────────────────
        # 若启用，先做"对抗性意图假设 + 针对性测试"，再把结果注入 prompt
        # 让 LLM 在生成补丁时考虑这些对抗场景；生成后独立"批评者"评估
        # 是否能击穿补丁，被击穿则重新生成一次
        adversarial_check: dict[str, Any] = {
            "scenarios_checked": 0,
            "all_passed": False,
            "critic_degraded": False,
        }
        adversarial_hypotheses: list[str] = []
        if _adversarial_debugging_enabled():
            adversarial_hypotheses = self._generate_adversarial_intents(target_code, error_category.value)
            if adversarial_hypotheses:
                query += self._build_adversarial_prompt_section(adversarial_hypotheses)
                logger.info(
                    "对抗性推理注入了 %d 个意图假设（3.1）",
                    len(adversarial_hypotheses),
                )

        # ── 3.3 改进（位置感知迭代修复，默认关）──────────────────────────
        # LoopRepair 式"先定位再补丁"：若启用，把 error_classifier 已提取的
        # 异常位置（traceback 行号/语法错误行列）经 AST 定位到所属函数，
        # 生成"位置感知修复指引"注入 prompt，让 LLM 优先修定位到的位置。
        # 定位是纯静态（不消耗 LLM token）；无法定位时降级为常规全文件修复。
        position_aware_section = ""
        focus_result: dict[str, Any] = {"focused": False, "function_name": None, "line": None, "hint": ""}
        if _position_aware_repair_enabled():
            # 复用已提取的 context（Step 2 的 get_fix_strategy 已调用
            # extract_error_context；此处再取一次保证含 line/column 字段）
            # 2026-09-26 全面审查（P1 正确性）：定位必须用**原始**全文
            # （original_target_code）——context.line 是原始源文件行号，
            # 传入截断版会使行号偏移/目标函数被丢弃（focused=False 降级
            # 全文件修复或定位到错误函数）；prompt 用截断版省 token 不变。
            focus_result = self._locate_repair_focus(original_target_code, context, target_module)
            # P1 探针快照第二定位源（PROBE_SNAPSHOT_LOCATE_ENABLE=true 时启用，默认关）：
            # assertion 主导的失败无 traceback 行号，context.line 恒 None → 定位
            # 阶段降级全文件修复。启用探针快照定位后，从 probe_snapshot（RUNTIME_PROBE_ENABLE
            # 开启时由 _executor_node 写入 state["runtime_probe_snapshot"]，经
            # _debugger_node 透传）取"最内层帧"的函数名 + 行号作为第二定位源，
            # 使纯 assertion 失败也能定位到问题函数。纯静态（零 LLM 成本），
            # 探针快照缺失 / 帧不可解析时保持 focus_result 原值（历史口径不变）。
            if not focus_result.get("focused") and _probe_snapshot_locate_enabled() and probe_snapshot:
                probe_focus = self._locate_repair_focus_from_probe(original_target_code, probe_snapshot, target_module)
                if probe_focus.get("focused"):
                    focus_result = probe_focus
                    logger.info(
                        "P1 探针快照定位：assertion 失败（无 traceback 行号）经探针最内层帧定位到 %s() 第 %s 行",
                        focus_result.get("function_name"),
                        focus_result.get("line"),
                    )
            position_aware_section = self._build_position_aware_prompt_section(focus_result)
            if focus_result.get("focused"):
                logger.info(
                    "位置感知修复（3.3）：定位到 %s() 第 %s 行，注入修复指引",
                    focus_result.get("function_name"),
                    focus_result.get("line"),
                )
            else:
                logger.debug("位置感知修复（3.3）：无法定位，降级为常规全文件修复")
            query += position_aware_section

        # 1.3 改进：分层压缩降级链——上一轮补丁被命名契约符号守卫拒绝时
        # （contract_reject_feedback 非空，由 _patch_applier_node 经
        # _debugger_node 透传），在更严格的温度下重新生成（降级层温度映射
        # patch_applier._CONTEXT_TIER_TEMPERATURES；patch 层拒绝 = 更高约束）。
        # 未触发时（feedback 为 None）温度口径与历史完全一致。
        eff_temperature: float | None = temperature
        if contract_reject_feedback:
            tier_name = str(contract_reject_feedback.get("tier", "minimal"))
            tier_temperature = _downgrade_tier_temperature(tier_name)
            if tier_temperature is not None:
                eff_temperature = tier_temperature
                logger.info("1.3 降级链：上下文档位 %s，本轮 LLM 温度收紧为 %.2f", tier_name, tier_temperature)

        # 调用 LLM 获取修复响应，带文件缓存省 token
        raw = self._call_llm_with_cache(query, temperature=eff_temperature)

        # P0 4.1 响应格式重试：JSON 解析失败 / 空响应时用更严格 prompt 重新请求一次
        # ErrorCategory 在文件头已导入（与 ErrorClassifier 同模块），删除函数内
        # 冗余的局部导入（同一模块重复 import 是历史残留，无运行期差异）
        _response_format = ErrorClassifier.classify_llm_response(raw)
        if _response_format in (
            ErrorCategory.LLM_EMPTY_RESPONSE,
            ErrorCategory.LLM_JSON_PARSE_FAILED,
        ):
            # 记录原始响应片段（截断到 500 字符）到 failure knowledge base
            _snippet = (raw or "")[:500]
            logger.warning(
                "P0 4.1 LLM 响应格式异常（%s），用更严格 prompt 重新请求一次。原始片段: %s...",
                _response_format.value,
                _snippet[:80],
            )
            _strict_retry_query = (
                query + "\n\n【格式要求】只输出一个 JSON 对象，不要输出任何其他文本、注释或 markdown 代码块。"
                'JSON 结构：{"root_cause": str, "error_category": str, "fix_strategy": str, "patch": str}'
            )
            raw2_strict = self._call_llm_with_cache(_strict_retry_query, temperature=eff_temperature)
            _strict_response_format = ErrorClassifier.classify_llm_response(raw2_strict)
            if _strict_response_format not in (
                ErrorCategory.LLM_EMPTY_RESPONSE,
                ErrorCategory.LLM_JSON_PARSE_FAILED,
            ):
                raw = raw2_strict
                logger.info("P0 4.1 严格 prompt 重试成功，响应格式正常")
            else:
                logger.warning(
                    "P0 4.1 严格 prompt 重试仍失败（%s），降级到宽松 JSON 提取",
                    _strict_response_format.value,
                )

        # 宽松 JSON 提取（容忍 markdown 包裹 / 前后自然语言）
        # 2026-09-26 round9 P2：_extract_json 在两次坏 JSON 时必抛
        # json.JSONDecodeError（严格 prompt 重试已在上文降级，raw 仍为
        # 宽松提取对象），不捕获则整个 Debugger 节点崩溃。包 try/except
        # 降级为空 patch（保守：无有效补丁时走下游"无补丁"分支，不阻断
        # 实验循环），并记 warning 诊断。
        try:
            result = self._extract_json(raw)
        except json.JSONDecodeError as e:
            logger.warning("P2 JSON 提取失败（降级空 patch）: %s；原始片段: %s", e, (raw or "")[:200])
            result = {}
        patch = result.get("patch", "")

        # ── 修复引擎第二阶段（批次 III）：编辑意图确定性落盘（默认关）────
        # LLM 在 JSON 中附加 edit_intents 时，用确定性引擎应用到原码
        # （锚点唯一性 + 原子性 + AST 语法门，见 src/tools/patch_intent.py），
        # 成功则用最小编辑结果替换整文件 patch（最小 diff 口径，对标
        # PatchPilot/2609.00227）；失败原子回退 legacy 整文件补丁通道。
        # 开关关时零行为变化（edit_intent_status 恒 None）。
        edit_intent_status: dict[str, Any] | None = None
        if _edit_intent_on:
            from src.tools.patch_intent import apply_edit_intents, parse_edit_intents

            _intents = parse_edit_intents(result.get("edit_intents"))
            if _intents:
                _intent_result = apply_edit_intents(target_code, _intents)
                edit_intent_status = _intent_result
                if _intent_result.get("ok"):
                    patch = f"```python\n{_intent_result['code']}\n```"
                    logger.info(
                        "编辑意图确定性落盘成功（%d/%d 条），补丁替换为最小编辑结果",
                        _intent_result.get("applied", 0),
                        _intent_result.get("total", 0),
                    )
                else:
                    logger.warning(
                        "编辑意图被确定性引擎拒绝（%s），回落整文件补丁通道",
                        "; ".join(_intent_result.get("diagnostics") or []),
                    )
            else:
                edit_intent_status = {
                    "ok": False,
                    "code": "",
                    "applied": 0,
                    "total": 0,
                    "diagnostics": ["no_valid_edit_intents_in_response"],
                }

        # 3.1 改进：批评者评估——若启用对抗性推理，独立 LLM 调用尝试构造
        # 击穿补丁的对抗性测试用例；若批评者成功（构造出击穿用例），
        # 触发一次补丁重新生成（仍被击穿则保留当前补丁并记录风险）
        if _adversarial_debugging_enabled() and adversarial_hypotheses and patch:
            critic_result = self._run_critic_eval(patch, target_code, adversarial_hypotheses)
            adversarial_check = critic_result
            if not critic_result.get("all_passed", False):
                logger.warning(
                    "批评者评估发现 %d 个击穿用例（3.1），重新生成补丁",
                    len(critic_result.get("break_cases", [])),
                )
                # 把击穿用例注入 prompt 重新生成一次（带负面反馈）
                requery = query + self._build_critic_feedback(critic_result)
                raw2 = self._call_llm_with_cache(requery, temperature=temperature)
                # 2026-09-26 round9 P2：critic requery 的 JSON 提取同样可能
                # 失败（LLM 二次输出仍为坏 JSON），不捕获则对抗性分支
                # 崩溃使整个 Debugger 节点失败。降级为保留原 patch。
                try:
                    result2 = self._extract_json(raw2)
                    patch2 = result2.get("patch", patch)
                except json.JSONDecodeError as e:
                    logger.warning("P2 对抗性重新生成 JSON 提取失败（保留原 patch）: %s", e)
                    patch2 = patch
                if patch2 and patch2 != patch:
                    patch = patch2
                    logger.info("对抗性重新生成成功，补丁已更新（3.1）")
                else:
                    logger.warning("对抗性重新生成未产出有效补丁，保留原补丁（3.1）")

        # 确保返回格式一致，即使 LLM 未返回某些字段也有默认值
        # ── 2.1 PAGENT 风格类型修复层（后处理）────────────────────────────
        # 补丁生成后对"原代码 vs 补丁后代码"做静态类型疑点识别 + 可选 LLM
        # 修复 + 命名契约回环验证（PAGENT 混合架构，默认 LLM 层关闭）。
        # 疑点非空且 TYPE_REPAIR_LLM_ENABLE=true 时自动修订；未启用时仅记录
        # 疑点观测层（type_repair_findings），不影响历史实验口径。
        type_repair_findings: list[dict[str, Any]] = []
        mypy_findings_count: int = 0
        if patch:
            # 先用 patch_applier 把补丁应用到原代码得到"补丁后代码"，再喂给
            # type_repair_layer（静态层需要两侧代码做对比识别；
            # TYPE_CHECK_ENABLE=true 时内部还会跑 mypy 仓库级静态类型分析）
            from src.tools.patch_applier import apply_patch_to_code

            _patched, _applied = apply_patch_to_code(target_code, patch)
            _type_repair = type_repair_layer(target_code, _patched if _applied else target_code)
            type_repair_findings = _type_repair.get("findings", [])
            mypy_findings_count = int(_type_repair.get("mypy_findings_count", 0))
            if _type_repair.get("repaired"):
                # LLM 层修订成功且通过契约回环 → 用修订代码替换 patch
                _repaired = _type_repair.get("repaired_code") or _patched
                patch = f"```python\n{_repaired}\n```"
                logger.info("2.1 类型修复层修订了补丁（静态疑点 %d 处）", len(type_repair_findings))
            elif type_repair_findings:
                logger.debug(
                    "2.1 类型疑点 %d 处（静态层记录，LLM 层未修订；mypy 层 %d 条）",
                    len(type_repair_findings),
                    mypy_findings_count,
                )

        return {
            "root_cause": result.get("root_cause", "未知"),
            "error_category": error_category.value,
            # P2-4：规则分类置信度（0.2/0.5/0.9 分层），供 state["error_confidence"]
            # → risk_approval 置信度因子消费（此前三因子恒缺一）
            "error_confidence": error_confidence,
            "fix_strategy": result.get("fix_strategy", strategy_text),
            "patch": patch,
            # 3.1 改进：对抗性推理结果（未启用时为零值，启用时含
            # intent_hypotheses / critic_break_cases / all_passed）
            "adversarial_check": adversarial_check,
            # 3.1 双向诊断结果：implementation_defect | test_defect
            # （未启用时恒为 implementation_defect，保持历史口径）
            "defect_type": defect_type,
            "review_reason": review_reason,
            # 修复引擎批次 III：编辑意图确定性落盘观测（EDIT_INTENT_ENABLE
            # 默认关时恒 None；开启时 {"ok","applied","total","diagnostics"}）
            "edit_intent_status": edit_intent_status,
            # 3.3 改进：位置感知修复定位结果（未启用时 focused=False，hint=""）
            # 启用时 focused=True 且 hint 非空（已注入 prompt），function_name/line 供实验消费
            "position_aware_focus": focus_result,
            # 2.1 PAGENT 风格类型修复层：静态识别的类型疑点（LLM 层未启用时
            # 仍记录，供实验分析消费；修订成功时 patch 已被替换）
            "type_repair_findings": type_repair_findings,
            # 2.1 mypy 静态层观测：mypy 补充的类型疑点数（未启用/未安装时 0）
            "mypy_findings_count": mypy_findings_count,
            # 1.3 分层压缩降级链：本轮是否因契约拒绝反馈而收紧了上下文
            # （contract_reject_feedback 非空时 True；实验分析"降级链触发率"消费）
            "downgrade_triggered": bool(contract_reject_feedback),
            "downgrade_tier": (str(contract_reject_feedback.get("tier")) if contract_reject_feedback else None),
            # 2.1 P1 改进：结构化修复策略标签（错误分类 → 修复路径显式映射）
            "fix_strategy_tag": _strategy_record["strategy"],
            "fix_strategy_action": _strategy_record["repair_action"],
            # 4. 失败知识库闭环（落点 B）：本轮是否注入了 KB 同类案例提示
            # （_kb_snippet 非 None 时 True；FAILURE_KB_ENABLE 默认关时恒 False）
            "kb_prompt_snippet_applied": bool(_kb_snippet),
            # P0 运行时探针注入层：本轮是否注入了探针快照片段（probe_section
            # 非空时 True；RUNTIME_PROBE_ENABLE 默认关 / 快照为 None 时恒 False）
            "probe_section_applied": bool(probe_section),
        }

    # ─── 3.3 位置感知迭代修复（LoopRepair 式：先定位再补丁）──────────────

    def _locate_repair_focus(
        self,
        target_code: str,
        context: Any,
        target_module: str | None,
    ) -> dict[str, Any]:
        """3.3 改进：位置感知修复定位（纯静态，不消耗 LLM token）。

        参考 LoopRepair 的"位置感知迭代修复"：在生成补丁前，先基于
        error_classifier 已提取的异常位置（traceback 文件/行号、语法错误
        行列）做 AST 定位，找出异常行所属的函数/方法，生成"位置感知修复
        指引"。LLM 据此优先修定位到的位置，而非全文件盲搜。

        定位口径（保守、可复算）：
        - 仅当 context.line 可解析为正整数且 target_code 可 ast.parse 时定位；
        - 取"包围异常行"的最内层函数/方法（FunctionDef/AsyncFunctionDef）；
        - 跨文件异常（traceback 文件名与 target_module 不符）时不定位到
          本文件，返回 focused=False（避免误导 LLM 修错文件）；
        - 无法定位（无行号 / AST 解析失败 / 行号越界 / 无包围函数）时
          focused=False，主流程降级为常规全文件修复（保持历史口径）。

        Args:
            target_code: 被测代码全文（未截断版由调用方传入，便于行号对齐）。
            context: ErrorContext（含 filename / line / column / module_name）。
            target_module: 被测模块名（可选，用于跨文件判断）。

        Returns:
            {"focused": bool, "function_name": str | None, "line": int | None,
             "hint": str}
            focused=True 时 hint 非空（供 prompt 注入）；False 时 hint 为空串。
        """
        import ast

        line = getattr(context, "line", None)
        if not isinstance(line, int) or line <= 0:
            return {"focused": False, "function_name": None, "line": None, "hint": ""}

        # 跨文件保护：traceback 文件名与 target_module 不符时，异常发生在
        # 其他文件，本文件定位无意义（避免误导 LLM 修错文件）
        # 口径：basename == target_module（精确）或 startswith(target_module)
        # （允许 ".py" 后缀；编号后缀场景下 target_module 本身含编号，
        # 精确匹配已覆盖，无需放宽——保持保守"宁缺勿误"）
        if target_module and getattr(context, "filename", None):
            file_base = str(context.filename).rsplit("/", 1)[-1]
            if file_base not in (target_module, f"{target_module}.py") and not file_base.startswith(target_module):
                return {"focused": False, "function_name": None, "line": line, "hint": ""}

        try:
            tree = ast.parse(target_code)
        except (SyntaxError, ValueError):
            # 代码本身语法损坏（SYNTAX 类）：AST 定位不可用，降级全文件重写
            return {"focused": False, "function_name": None, "line": line, "hint": ""}

        # 找包围异常行的最内层函数/方法（行号落在 [lineno, end_lineno] 区间）
        enclosing = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.lineno <= line <= (node.end_lineno or node.lineno)
        ]
        if not enclosing:
            return {"focused": False, "function_name": None, "line": line, "hint": ""}

        # 最内层（嵌套最浅的包围节点；取子节点最多的最内层，保守取最后一个
        # 匹配且无更深嵌套的）：优先选"包围区间最短"的函数作为焦点
        focus = min(enclosing, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)
        focus_name = focus.name
        col = getattr(context, "column", None)
        hint = (
            f"位置感知修复指引（3.3）：异常定位在 `{focus_name}()`"
            f"（第 {line} 行"
            + (f"、第 {col} 列" if isinstance(col, int) and col and col > 0 else "")
            + "）。请优先检查并修复该函数内的逻辑，避免改动无关代码。"
        )
        return {"focused": True, "function_name": focus_name, "line": line, "hint": hint}

    def _locate_repair_focus_from_probe(
        self,
        target_code: str,
        probe_snapshot: dict[str, Any] | None,
        target_module: str | None,
    ) -> dict[str, Any]:
        """P1 探针快照第二定位源（纯静态，不消耗 LLM token）。

        2026-10 改进（A/B 阴性结果驱动）：assertion 主导的失败无 traceback
        行号，_locate_repair_focus 的 context.line 恒 None 而全文件降级。
        本方法从 runtime_probe 快照的"最内层帧"（frames[0]，抛出点）取
        函数名 + 行号，经 AST 定位到所属函数，生成位置感知修复指引。

        定位口径（保守、与 _locate_repair_focus 同族）：
        - 探针快照 frames 为空 / 首帧无 function/line → focused=False（降级）；
        - 首帧文件名与 target_module 不符（跨文件）→ focused=False（不误导）；
        - 行号越界 / AST 解析失败 → focused=False（降级全文件修复）；
        - 定位成功 → hint 明确标注"来自运行时探针"，与 traceback 路径区分。

        Args:
            target_code: 被测代码全文（未截断版，便于行号对齐）。
            probe_snapshot: runtime_probe.capture_failure_snapshot 产物
                （{"frames": [{"function", "file", "line", "locals"}...]}），
                帧序为"最内层抛出点 → 外层"，frames[0] 即抛出点帧。
            target_module: 被测模块名（可选，用于跨文件保护）。

        Returns:
            {"focused": bool, "function_name": str | None, "line": int | None,
             "hint": str, "probe_sourced": bool}
            focused=True 时 hint 非空且 probe_sourced=True；False 时 probe_sourced=True、
            hint 空串（主流程据此区分"探针尝试过但失败"与"探针未启用"）。
        """
        result: dict[str, Any] = {
            "focused": False,
            "function_name": None,
            "line": None,
            "hint": "",
            "probe_sourced": True,
        }
        frames = (probe_snapshot or {}).get("frames") or []
        if not frames:
            return result
        first = frames[0]
        probe_line = first.get("line")
        probe_func = first.get("function") or ""
        probe_file = first.get("file") or ""
        if not isinstance(probe_line, int) or probe_line <= 0:
            return result
        # 跨文件保护：探针帧文件名与 target_module 不符时，异常发生在其他文件
        if target_module and probe_file:
            file_base = probe_file.rsplit("/", 1)[-1]
            if not (file_base.startswith(target_module) or file_base == f"{target_module}.py"):
                return result
        # 行号落在被测代码（original_target_code）内才有效
        code_lines = target_code.count("\n") + 1
        if probe_line > code_lines:
            return result
        # AST 定位：找包围探针帧行号的最内层函数（与 _locate_repair_focus 同族）
        try:
            import ast

            tree = ast.parse(target_code)
        except (SyntaxError, ValueError):
            return result
        enclosing = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.lineno <= probe_line <= (node.end_lineno or node.lineno)
        ]
        if not enclosing:
            # 探针帧行号落在模块顶层（如模块级 assert / 顶层表达式）：
            # 保守降级全文件修复（与 traceback 路径同口径）
            return result
        focus = min(enclosing, key=lambda n: (n.end_lineno or n.lineno) - n.lineno)
        focus_name = focus.name
        # 探针帧的函数名优先（co_name 即抛出点所在函数），AST 包围函数作交叉验证
        hint = (
            f"位置感知修复指引（P1 探针快照）：运行时探针捕获到异常抛出点"
            f" `{probe_func or focus_name}()` 第 {probe_line} 行"
            + (f"（AST 包围函数为 `{focus_name}()`，与探针帧一致）" if focus_name == probe_func else "")
            + "。请优先检查并修复该位置附近的逻辑，避免改动无关代码。"
        )
        result.update({"focused": True, "function_name": focus_name, "line": probe_line, "hint": hint})
        return result

    def _build_position_aware_prompt_section(self, focus: dict[str, Any]) -> str:
        """把位置感知修复指引注入 prompt（focus["focused"] 为 False 时返回空串）。"""
        if not focus.get("focused"):
            return ""
        return f"\n\n{focus.get('hint', '')}"

    # ─── 3.1 对抗性推理辅助方法（AdverIntent-Agent 式）────────────────────

    def _generate_adversarial_intents(self, target_code: str, error_category: str) -> list[str]:
        """生成 2-3 个对抗性程序意图假设（攻击者/缺陷视角）。

        让 LLM 从"想让代码出 bug"的角度思考：哪些输入/调用场景会击穿
        当前实现。用于引导生成针对性测试用例 + 让补丁覆盖这些场景。

        Args:
            target_code: 被测代码（已截断）。
            error_category: 错误类别（影响假设方向，如 ASSERTION → 边界值）。

        Returns:
            对抗性意图假设列表（字符串，最多 _ADVERSARIAL_INTENT_COUNT 个）；
            LLM 调用失败或无输出时返回空列表。
        """
        query = (
            f"你是对抗性测试专家。针对以下被测代码，从攻击者视角提出 "
            f"{_ADVERSARIAL_INTENT_COUNT} 个“可能击穿该实现”的程序意图假设"
            f"（缺陷场景）。每个假设用一句话描述：什么输入/调用序列会让代码"
            f"产生错误结果或崩溃。当前错误类别：{error_category}。\n\n"
            f"被测代码：\n```\n{target_code}\n```\n\n"
            f"请输出 JSON 数组（字符串列表），每个元素是一个假设。"
        )
        try:
            raw = self._call_llm_with_cache(query)
            arr = self._extract_json(raw)
            if isinstance(arr, list):
                return [str(x) for x in arr[:_ADVERSARIAL_INTENT_COUNT]]
            # LLM 输出非列表时尝试提取
            if isinstance(arr, dict) and "hypotheses" in arr:
                return [str(x) for x in arr["hypotheses"][:_ADVERSARIAL_INTENT_COUNT]]
        except Exception as e:
            logger.warning("对抗性意图假设生成失败（跳过，3.1）: %s", e)
        return []

    def _build_adversarial_prompt_section(self, hypotheses: list[str]) -> str:
        """把对抗性意图假设 + 针对性测试用例要求注入 prompt。"""
        lines = [
            "\n\n【对抗性推理（3.1）】以下是可能击穿当前实现的缺陷场景假设，请在生成补丁时确保这些场景被正确处理：",
        ]
        for i, h in enumerate(hypotheses, start=1):
            lines.append(f"  假设 {i}：{h}")
        lines.append("请为每个假设生成一个针对性测试用例（验证补丁覆盖该场景），并在 patch 的修复中处理这些对抗场景。")
        return "\n".join(lines)

    def _run_critic_eval(self, patch: str, target_code: str, hypotheses: list[str]) -> dict[str, Any]:
        """批评者评估：独立 LLM 调用尝试构造击穿补丁的对抗性测试。

        Args:
            patch: 当前生成的补丁。
            target_code: 被测代码。
            hypotheses: 对抗性意图假设列表。

        Returns:
            {"all_passed": bool, "break_cases": list[str],
             "intent_hypotheses": list[str]}
            all_passed=True 表示批评者未能构造出击穿用例（补丁稳健）；
            False 表示构造出了击穿用例（break_cases 非空）。
        """
        query = (
            "你是独立的代码批评者。以下补丁声称修复了若干缺陷，"
            "请尝试构造 1-3 个能'击穿'该补丁的对抗性测试用例"
            "（让修复后的代码仍产生错误结果或崩溃的输入/调用）。\n\n"
            f"原始代码：\n```\n{target_code}\n```\n\n"
            f"补丁：\n```\n{patch[:2000]}\n```\n\n"
            f"已知对抗场景假设：\n" + "\n".join(f"- {h}" for h in hypotheses) + "\n\n"
            '请输出 JSON：{"break_cases": [测试用例描述...], "all_passed": bool}'
        )
        try:
            raw = self._call_llm_with_cache(query)
            result = self._extract_json(raw)
            break_cases = [str(c) for c in (result.get("break_cases") or [])[:_MAX_CRITIC_BREAK_CASES]]
            return {
                "all_passed": bool(result.get("all_passed", not break_cases)),
                "critic_degraded": False,
                "break_cases": break_cases,
                "intent_hypotheses": hypotheses,
                "scenarios_checked": len(hypotheses),
            }
        except Exception as e:
            # U5（2026-10-05 系统性审查落地）：fail-open 乐观偏向三态化——
            # 历史口径：critic 异常 → all_passed=True（"批评者未击穿"），
            # 把"评估不可用"与"评估通过"混为一谈（乐观偏向：下游把降级
            # 当稳健）。现保持 all_passed=True 路由语义不变（ADR-0003：
            # 不改默认行为），但新增 critic_degraded=True 显式标记
            # "该 all_passed 是降级产物而非评估结论"，随 adversarial_check
            # 写入 state 供实验分析/报告层区分三态（通过 / 被击穿 / 不可用）。
            logger.warning("批评者评估失败（降级：视为未击穿并标记 critic_degraded）: %s", e)
            return {
                "all_passed": True,
                "critic_degraded": True,
                "break_cases": [],
                "intent_hypotheses": hypotheses,
                "scenarios_checked": len(hypotheses),
            }

    def _build_critic_feedback(self, critic_result: dict[str, Any]) -> str:
        """把批评者发现的击穿用例作为负面反馈注入重新生成 prompt。"""
        lines = ["\n\n【批评者反馈（3.1）】以下对抗性测试用例会击穿当前补丁，请在重新生成时确保这些场景被正确处理："]
        lines.extend(f"- {c[:_ADVERSARIAL_CASE_TRUNCATE_LEN]}" for c in critic_result.get("break_cases", []))
        return "\n".join(lines)

    # ─── 3.1 双向代码-测试诊断辅助方法（BiVCoder 式）──────────────────────

    def _run_review_diagnosis(
        self,
        target_code: str,
        test_output: str,
        failed_cases: list[dict[str, str]],
        error_category: str,
    ) -> dict[str, str]:
        """3.1 双向诊断：Review Agent 判断失败根因是"实现缺陷"还是"测试缺陷"。

        参考 BiVCoder 的双向代码-测试诊断机制：独立 LLM 调用扮演"审查智能体"
        区分两类缺陷并触发针对性修复：
        - implementation_defect：被测代码逻辑错误 → Debugger 修复代码；
        - test_defect：测试自身设计错误（预期值写错 / 断言了错误行为 /
          复现测试覆盖了错误路径）→ Generator 重新生成测试。

        Args:
            target_code: 被测代码（已截断）。
            test_output: 测试失败输出（已截断）。
            failed_cases: 失败用例列表。
            error_category: 错误类别（供判断参考，如 ASSERTION 更可能是测试预期值错误）。

        Returns:
            {"defect_type": "implementation_defect" | "test_defect",
             "reason": str}。LLM 调用失败或输出非法时保守判定为实现缺陷
            （保持"修复代码"的历史默认行为，不因诊断失败而阻断修复）。
        """
        cases_summary = "\n".join(
            f"- {case['name']}: {case['error'][:_FAILED_CASE_ERROR_TRUNCATE_LEN]}"
            for case in failed_cases[:_MAX_FAILED_CASES_SUMMARY]
        )
        query = (
            "你是独立的代码审查智能体（Review Agent）。以下是测试失败信息，"
            "请判断失败根因是【实现缺陷】还是【测试缺陷】：\n"
            "- 实现缺陷：被测代码逻辑错误（返回值错误、边界处理缺失、异常未处理）；\n"
            "- 测试缺陷：测试自身设计错误（预期值写错、断言了错误行为、复现测试覆盖了错误路径）。\n\n"
            f"错误类别：{error_category}\n\n"
            f"被测代码：\n```\n{target_code}\n```\n\n"
            f"测试输出：\n```\n{test_output}\n```\n\n"
            f"失败用例：\n{cases_summary}\n\n"
            '请输出 JSON：{"defect_type": "implementation_defect" 或 "test_defect", '
            '"reason": "一句话判断依据"}'
        )
        try:
            raw = self._call_llm_with_cache(query)
            result = self._extract_json(raw)
            defect_type = str(result.get("defect_type", "implementation_defect"))
            if defect_type not in ("implementation_defect", "test_defect"):
                # 非法值保守归为实现缺陷（保持历史默认行为）
                defect_type = "implementation_defect"
            return {"defect_type": defect_type, "reason": str(result.get("reason", ""))}
        except Exception as e:
            logger.warning("双向诊断 Review Agent 调用失败（保守判定为实现缺陷，3.1）: %s", e)
            return {"defect_type": "implementation_defect", "reason": ""}
