"""
测试代码生成师智能体，根据测试计划生成 pytest 测试代码。
"""

from __future__ import annotations

from typing import Any, Dict

from src.agents.base_agent import BaseAgent
from src.prompts.templates import GENERATOR_SYSTEM_PROMPT


class GeneratorAgent(BaseAgent):
    """
    测试生成师：根据测试计划生成可运行的 pytest 代码。

    输入:
        test_plan: PlannerAgent 输出的测试计划字典。
        target_code: 被测代码全文（用于 import 引用）。

    输出:
        完整的 pytest 测试代码字符串。
    """

    def __init__(self) -> None:
        super().__init__(GENERATOR_SYSTEM_PROMPT)

    def generate(self, test_plan: Dict[str, Any], target_code: str) -> str:
        """
        生成 pytest 测试代码。

        Args:
            test_plan: 测试计划字典（PlannerAgent 输出）。
            target_code: 被测代码全文。

        Returns:
            完整的 pytest 测试代码字符串。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        import json
        query = (
            f"测试计划（JSON）：\n{json.dumps(test_plan, ensure_ascii=False, indent=2)}\n\n"
            f"目标代码：\n```\n{target_code}\n```"
            f"\n\n请根据以上计划生成完整的 pytest 测试代码。"
        )
        raw = self._call_llm(query)
        return self._extract_python_code(raw)
