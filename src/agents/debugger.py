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

import logging
import os
from typing import Any

from src.agents.base_agent import BaseAgent
from src.agents.error_classifier import ErrorClassifier, get_fix_strategy
from src.prompts.templates import DEBUGGER_SYSTEM_PROMPT

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


def _bidirectional_diagnosis_enabled() -> bool:
    """3.1 双向代码-测试诊断开关（BIDIRECTIONAL_DIAGNOSIS_ENABLE=true 时启用，默认 false）。

    启用后 Debugger.debug 在生成补丁前先由 Review Agent 判断根因是
    "实现缺陷"（修复代码）还是"测试缺陷"（重新生成测试），实现 BiVCoder
    式的双向诊断与分支修复。默认关闭保持历史实验口径不变。
    """
    return os.getenv("BIDIRECTIONAL_DIAGNOSIS_ENABLE", "false").lower() == "true"


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
    ) -> dict[str, str]:
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

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # Step 1: 用规则分类器快速判断错误类型（不消耗 LLM token）
        # target_module 提供时，断言失败可区分 ASSERTION 与 LOGIC_ERROR（P2 细化）
        error_category = self.classifier.classify(test_output, failed_cases, target_module=target_module)
        # Step 2: 获取对应修复策略描述
        strategy_text = get_fix_strategy(
            error_category, context=self.classifier.extract_error_context(test_output, failed_cases)
        )
        # 记录分类结果，便于日志追踪和实验分析
        logger.info("错误分类结果: %s", error_category.value)

        # 截断超长代码，节省 token（大文件按焦点函数做 AST 智能截取）
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
                    "fix_strategy": "重新生成测试（测试缺陷，非实现缺陷）",
                    "patch": "",
                    "adversarial_check": {"scenarios_checked": 0, "all_passed": False},
                    "defect_type": defect_type,
                    "review_reason": review_reason,
                }

        # 在 prompt 中显式注入错误类型和修复策略，引导 LLM 分层处理
        query = (
            f"【错误类型】{error_category.value}\n"
            f"【修复策略】{strategy_text}\n\n"
            f"被测代码：\n```\n{target_code}\n```\n\n"
            f"测试输出：\n```\n{test_output}\n```\n\n"
            f"失败用例：\n{cases_summary}"
        )

        # RAG 增强：若检索到相似修复案例，注入参考补丁
        # 最多取前 _MAX_RAG_REPAIR_REFS 个案例
        # 同时截断 original_code 至 _RAG_ORIGINAL_CODE_TRUNCATE_LEN 字符，避免 prompt 过长
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
                query += "\n\n以下历史修复案例可作为参考：\n" + "\n\n".join(refs_text)
                logger.info("Debugger 使用了 %d 个 RAG 修复参考", len(refs_text))

        # ── 3.1 改进（对抗性推理机制，默认关）─────────────────────────────
        # 若启用，先做"对抗性意图假设 + 针对性测试"，再把结果注入 prompt
        # 让 LLM 在生成补丁时考虑这些对抗场景；生成后独立"批评者"评估
        # 是否能击穿补丁，被击穿则重新生成一次
        adversarial_check: dict[str, Any] = {"scenarios_checked": 0, "all_passed": False}
        adversarial_hypotheses: list[str] = []
        if _adversarial_debugging_enabled():
            adversarial_hypotheses = self._generate_adversarial_intents(target_code, error_category.value)
            if adversarial_hypotheses:
                query += self._build_adversarial_prompt_section(adversarial_hypotheses)
                logger.info(
                    "对抗性推理注入了 %d 个意图假设（3.1）",
                    len(adversarial_hypotheses),
                )

        # 调用 LLM 获取修复响应，带文件缓存省 token
        raw = self._call_llm_with_cache(query, temperature=temperature)
        result = self._extract_json(raw)
        patch = result.get("patch", "")

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
                result2 = self._extract_json(raw2)
                patch2 = result2.get("patch", patch)
                if patch2 and patch2 != patch:
                    patch = patch2
                    logger.info("对抗性重新生成成功，补丁已更新（3.1）")
                else:
                    logger.warning("对抗性重新生成未产出有效补丁，保留原补丁（3.1）")

        # 确保返回格式一致，即使 LLM 未返回某些字段也有默认值
        return {
            "root_cause": result.get("root_cause", "未知"),
            "error_category": error_category.value,
            "fix_strategy": result.get("fix_strategy", strategy_text),
            "patch": patch,
            # 3.1 改进：对抗性推理结果（未启用时为零值，启用时含
            # intent_hypotheses / critic_break_cases / all_passed）
            "adversarial_check": adversarial_check,
            # 3.1 双向诊断结果：implementation_defect | test_defect
            # （未启用时恒为 implementation_defect，保持历史口径）
            "defect_type": defect_type,
            "review_reason": review_reason,
        }

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
                "break_cases": break_cases,
                "intent_hypotheses": hypotheses,
                "scenarios_checked": len(hypotheses),
            }
        except Exception as e:
            logger.warning("批评者评估失败（视为未击穿，3.1）: %s", e)
            return {
                "all_passed": True,
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
