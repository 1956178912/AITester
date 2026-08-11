"""
测试规划师智能体，分析被测代码并输出测试计划 JSON。
"""

from __future__ import annotations

from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.prompts.templates import PLANNER_SYSTEM_PROMPT


class PlannerAgent(BaseAgent):
    """
    测试规划师：读取目标代码，生成结构化的测试计划。

    输入:
        target_code: 被测 Python 源代码字符串。
        target_function: 指定要测试的函数名（可为 None，表示测试全部函数）。

    输出:
        测试计划字典，包含 test_cases 列表。
    """

    def __init__(self) -> None:
        super().__init__(PLANNER_SYSTEM_PROMPT)

    def plan(self, target_code: str, target_function: str | None = None) -> Dict[str, Any]:
        """
        生成测试计划。

        Args:
            target_code: 被测代码全文。
            target_function: 目标函数名，用于聚焦分析；None 则分析全部。

        Returns:
            测试计划字典，结构如下：
            {
                "function_name": str,
                "description": str,
                "test_cases": List[dict]
            }

        Raises:
            RuntimeError: LLM 调用失败或返回非 JSON 格式时抛出。
        """
        query = f"请分析以下代码并制定测试计划：\n\n```\n{target_code}\n```"
        if target_function:
            # 明确指定要测试的函数，要求输出中包含该函数名
            query += f"\n\n**重要：请只针对以下函数生成测试计划，不要分析其他函数：**\n`{target_function}`"
            query += f"\n\n输出的 function_name 字段必须是 `{target_function}`。"

        raw = self._call_llm(query)
        return self._extract_json(raw)
