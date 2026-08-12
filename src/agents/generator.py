"""
测试代码生成师智能体，根据测试计划生成 pytest 测试代码。
支持 RAG 检索增强：在生成前先检索相似历史测试用例作为参考。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from src.agents.base_agent import BaseAgent
from src.prompts.templates import GENERATOR_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class GeneratorAgent(BaseAgent):
    """
    测试生成师：根据测试计划生成可运行的 pytest 代码。
    可选地接收 RAG 检索到的历史相似案例，增强生成质量。

    输入:
        test_plan: PlannerAgent 输出的测试计划字典。
        target_code: 被测代码全文（用于 import 引用）。
        rag_references: RAG 检索到的相似历史测试用例列表（可选）。

    输出:
        完整的 pytest 测试代码字符串。
    """

    def __init__(self) -> None:
        super().__init__(GENERATOR_SYSTEM_PROMPT)

    def generate(
        self,
        test_plan: Dict[str, Any],
        target_code: str,
        rag_references: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        生成 pytest 测试代码。
        若提供 rag_references，将其作为参考注入 prompt。

        Args:
            test_plan: 测试计划字典（PlannerAgent 输出）。
            target_code: 被测代码全文。
            rag_references: RAG 检索到的相似历史案例，每项含 test_code 字段。

        Returns:
            完整的 pytest 测试代码字符串。

        Raises:
            RuntimeError: LLM 调用失败时抛出。
        """
        # 将测试计划序列化为 JSON 字符串
        plan_json = json.dumps(test_plan, ensure_ascii=False, indent=2)

        # 构建基础查询，包含测试计划和目标代码
        query = (
            f"测试计划（JSON）：\n{plan_json}\n\n"
            f"目标代码：\n```\n{target_code}\n```"
            f"\n\n请根据以上计划生成完整的 pytest 测试代码。"
        )

        # RAG 增强：若检索到相似案例，注入参考代码
        if rag_references:
            refs_text = []
            for i, ref in enumerate(rag_references[:3], start=1):
                # 取 test_code 字段（最多前3个案例，避免 prompt 过长）
                test_code = ref.get("test_code", "")
                if test_code:
                    refs_text.append(f"【参考案例 {i}】\n```python\n{test_code}\n```")
            if refs_text:
                query += "\n\n以下历史测试用例可作为参考风格：\n" + "\n\n".join(refs_text)
                logger.info("Generator 使用了 %d 个 RAG 参考案例", len(refs_text))

        raw = self._call_llm(query)
        return self._extract_python_code(raw)
