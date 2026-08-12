"""
调试修复师智能体，分析测试失败并生成代码补丁。
引入分层错误修复机制：根据 ErrorCategory 选择不同的修复策略。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from src.agents.base_agent import BaseAgent
from src.agents.error_classifier import ErrorCategory, ErrorClassifier, get_fix_strategy
from src.prompts.templates import DEBUGGER_SYSTEM_PROMPT

# 模块级 logger
logger = logging.getLogger(__name__)


class DebuggerAgent(BaseAgent):
    """
    调试修复师：分析测试失败，输出根因诊断、错误分类和代码补丁。

    引入分层错误修复机制（Hierarchical Repair Strategy）：
    - SYNTAX 类：直接让 LLM 重写完整文件（无需语义分析）
    - RUNTIME 类：分析异常栈，定位 bug 所在函数
    - ASSERTION 类：判断是代码逻辑错误还是测试预期值错误
    - TIMEOUT 类：检查死循环/无限递归，添加退出条件
    - UNKNOWN 类：通用分析

    输入:
        target_code: 被测代码全文。
        test_output: 测试失败输出。
        failed_cases: 失败用例列表。

    输出:
        包含 root_cause、error_category、fix_strategy、patch 的字典。
    """

    def __init__(self) -> None:
        super().__init__(DEBUGGER_SYSTEM_PROMPT)
        # 实例化分类器，用于在调用 LLM 前先确定错误类型
        self.classifier = ErrorClassifier()

    def debug(
        self,
        target_code: str,
        test_output: str,
        failed_cases: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """
        分析测试失败并生成修复补丁。

        流程：
        1. 先用规则分类器确定错误类型（快速，不消耗 LLM token）
        2. 将错误类型及对应修复策略注入 prompt，引导 LLM 按类修复

        Args:
            target_code: 被测代码全文。
            test_output: 测试失败输出。
            failed_cases: 失败用例列表，每个元素为 {"name": str, "error": str}。

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
        # Step 2: 获取对应修复策略
        strategy_text = get_fix_strategy(error_category)
        # 记录分类结果，便于日志追踪
        logger.info("错误分类结果: %s", error_category.value)

        cases_summary = "\n".join(
            [f"- {case['name']}: {case['error'][:200]}" for case in failed_cases[:5]]
        )

        # 在 prompt 中显式注入错误类型和修复策略，引导 LLM 分层处理
        query = (
            f"【错误类型】{error_category.value}\n"
            f"【修复策略】{strategy_text}\n\n"
            f"被测代码：\n```\n{target_code}\n```\n\n"
            f"测试输出：\n```\n{test_output}\n```\n\n"
            f"失败用例：\n{cases_summary}"
        )

        raw = self._call_llm(query)
        result = self._extract_json(raw)

        # 确保返回格式一致
        return {
            "root_cause": result.get("root_cause", "未知"),
            "error_category": error_category.value,
            "fix_strategy": result.get("fix_strategy", strategy_text),
            "patch": result.get("patch", ""),
        }
