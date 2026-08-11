"""
调试修复师智能体，分析测试失败并生成代码补丁。
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.agents.base_agent import BaseAgent
from src.prompts.templates import DEBUGGER_SYSTEM_PROMPT


class DebuggerAgent(BaseAgent):
    """
    调试修复师：分析测试失败，生成根因诊断和代码补丁。

    输入:
        target_code: 被测代码全文。
        test_output: 测试失败输出。
        failed_cases: 失败用例列表。

    输出:
        包含根因分析、修复策略和补丁代码的字典。
    """

    def __init__(self) -> None:
        super().__init__(DEBUGGER_SYSTEM_PROMPT)

    def debug(
        self,
        target_code: str,
        test_output: str,
        failed_cases: List[Dict[str, str]],
    ) -> Dict[str, str]:
        """
        分析测试失败并生成修复补丁。

        Args:
            target_code: 被测代码全文。
            test_output: 测试失败输出。
            failed_cases: 失败用例列表，每个元素为 {"name": str, "error": str}。

        Returns:
            包含以下键的字典：
            - root_cause (str): 根因分析。
            - fix_strategy (str): 修复策略。
            - patch (str): 修复后的完整代码（含代码块标记）。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        cases_summary = "\n".join(
            [f"- {case['name']}: {case['error'][:200]}" for case in failed_cases[:5]]
        )

        query = (
            f"被测代码：\n```\n{target_code}\n```\n\n"
            f"测试输出：\n```\n{test_output}\n```\n\n"
            f"失败用例：\n{cases_summary}"
        )

        raw = self._call_llm(query)
        result = self._extract_json(raw)

        # 确保返回格式一致
        return {
            "root_cause": result.get("root_cause", "未知"),
            "fix_strategy": result.get("fix_strategy", ""),
            "patch": result.get("patch", ""),
        }
