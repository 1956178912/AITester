"""
调试修复师模块：分析测试失败并生成代码补丁。

引入分层错误修复机制（Hierarchical Repair Strategy）：
- SYNTAX 类：直接让 LLM 重写完整文件（无需语义分析）
- RUNTIME 类：分析异常栈，定位 bug 所在函数
- ASSERTION 类：判断是代码逻辑错误还是测试预期值错误
- TIMEOUT 类：检查死循环/无限递归，添加退出条件
- UNKNOWN 类：通用分析
支持 RAG 检索增强修复策略。
"""

from __future__ import annotations

import logging
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
# ───────────────────────────────────────────────────────────────────────────


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
    ) -> dict[str, str]:
        """
        分析测试失败并生成修复补丁。

        流程：
        1. 先用规则分类器确定错误类型（快速，不消耗 LLM token）
        2. 将错误类型及对应修复策略注入 prompt，引导 LLM 按类修复
        3. 若提供 RAG 参考，注入历史修复案例增强生成质量

        Args:
            target_code: 被测代码全文。
            test_output: 测试失败输出。
            failed_cases: 失败用例列表，每个元素为 {"name": str, "error": str}。
            rag_references: RAG 检索到的相似修复案例，每项含 patch 字段。

        Returns:
            包含以下键的字典：
            - root_cause (str): 根因分析。
            - error_category (str): 错误类型枚举字符串。
            - fix_strategy (str): 修复策略描述。
            - patch (str): 修复后的完整代码（含代码块标记）。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # Step 1: 用规则分类器快速判断错误类型（不消耗 LLM token）
        error_category = self.classifier.classify(test_output, failed_cases)
        # Step 2: 获取对应修复策略描述
        strategy_text = get_fix_strategy(error_category)
        # 记录分类结果，便于日志追踪和实验分析
        logger.info("错误分类结果: %s", error_category.value)

        # 截断超长代码，节省 token
        target_code = BaseAgent.truncate_code(target_code)
        # 截断超长测试输出，保留关键错误信息
        test_output = BaseAgent.truncate_code(test_output, max_chars=1500)

        # 构建失败用例摘要（最多展示前 _MAX_FAILED_CASES_SUMMARY 个，避免 prompt 过长）
        # 每条用例的错误信息截断至 _FAILED_CASE_ERROR_TRUNCATE_LEN 字符
        cases_summary = "\n".join(
            [
                f"- {case['name']}: {case['error'][:_FAILED_CASE_ERROR_TRUNCATE_LEN]}"
                for case in failed_cases[:_MAX_FAILED_CASES_SUMMARY]
            ]
        )

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

        # 调用 LLM 获取修复响应
        raw = self._call_llm(query)
        result = self._extract_json(raw)

        # 确保返回格式一致，即使 LLM 未返回某些字段也有默认值
        return {
            "root_cause": result.get("root_cause", "未知"),
            "error_category": error_category.value,
            "fix_strategy": result.get("fix_strategy", strategy_text),
            "patch": result.get("patch", ""),
        }
