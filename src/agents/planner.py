"""
测试规划师模块：实现逻辑驱动思维链（Logic-driven Chain-of-Thought）。

Planner 在输出测试计划前，先对函数进行输入域、输出域、前置条件、
后置条件、边界情况的显式分析，引导 Generator 按逻辑覆盖生成测试用例。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from src.agents.base_agent import BaseAgent
from src.prompts.templates import PLANNER_SYSTEM_PROMPT
from src.graph.llm_cache import cached_llm_call, get_cache_stats

# 模块级日志记录器
logger = logging.getLogger(__name__)


class LogicAnalysisResult:
    """
    逻辑分析结果：记录 Planner 对单个函数的结构化分析。

    该结果包含函数的输入域、输出域、前置/后置条件和边界情况，
    用于引导后续测试生成器覆盖所有重要路径。

    属性:
        input_domain: 输入参数描述（含类型、取值范围、特殊值）。
        output_domain: 返回值描述（含类型、可能的异常）。
        preconditions: 调用前的前提条件列表。
        postconditions: 调用后的后置条件列表。
        edge_cases: 边界情况列表（如除零、空集合、负数等）。

    使用示例:
        >>> result = LogicAnalysisResult(
        ...     input_domain="整数 a, b，无范围限制",
        ...     output_domain="整数，a+b 的算术和",
        ...     preconditions=["a, b 均为整数"],
        ...     postconditions=["result == a + b"],
        ...     edge_cases=["a=0", "b=0", "大整数溢出"],
        ... )
        >>> result.to_dict()
        {'input_domain': '整数 a, b，无范围限制', ...}
    """

    def __init__(
        self,
        input_domain: str,
        output_domain: str,
        preconditions: List[str],
        postconditions: List[str],
        edge_cases: List[str],
    ) -> None:
        # 初始化各字段
        self.input_domain = input_domain
        self.output_domain = output_domain
        self.preconditions = preconditions
        self.postconditions = postconditions
        self.edge_cases = edge_cases

    def to_dict(self) -> Dict[str, Any]:
        """
        将逻辑分析结果序列化为字典。
        便于 JSON 存储、传递和后续使用。

        Returns:
            包含五个字段的字典。
        """
        return {
            "input_domain": self.input_domain,
            "output_domain": self.output_domain,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "edge_cases": self.edge_cases,
        }


class PlannerAgent(BaseAgent):
    """
    测试规划师：读取目标代码，先生成逻辑分析（思维链），再输出结构化测试计划。

    工作流程：
    1. 接收被测代码和可选的目标函数名
    2. 调用 LLM，要求其先进行逻辑分析，再生成测试计划 JSON
    3. 解析响应，确保包含 logic_analysis 字段

    输入:
        target_code: 被测 Python 源代码字符串。
        target_function: 指定要测试的函数名（可为 None，表示测试全部函数）。

    输出:
        测试计划字典，包含 logic_analysis（思维链）和 test_cases 列表。
    """

    def __init__(self) -> None:
        # 使用增强版 system prompt，要求先输出逻辑分析再输出测试计划
        super().__init__(PLANNER_SYSTEM_PROMPT)

    def plan(self, target_code: str, target_function: str | None = None) -> Dict[str, Any]:
        """
        生成测试计划（含逻辑驱动思维链）。

        LLM 输出分为两个阶段：
        Phase 1: 逻辑分析（输入域、输出域、前置/后置条件、边界情况）
        Phase 2: 结构化测试计划 JSON

        Args:
            target_code: 被测代码全文。
            target_function: 目标函数名，用于聚焦分析；None 则分析全部。

        Returns:
            测试计划字典，结构如下：
            {
                "function_name": str,
                "description": str,
                "logic_analysis": {
                    "input_domain": str,
                    "output_domain": str,
                    "preconditions": List[str],
                    "postconditions": List[str],
                    "edge_cases": List[str]
                },
                "test_cases": List[dict]
            }

        Raises:
            RuntimeError: LLM 调用失败或返回非 JSON 格式时抛出。
        """
        # 截断超长代码，节省 token
        target_code = BaseAgent.truncate_code(target_code)
        # 构建查询：包含代码和可选的函数限定
        query = f"请分析以下代码并制定测试计划：\n\n```\n{target_code}\n```"
        if target_function:
            # 明确指定要测试的函数，要求输出中包含该函数名
            query += f"\n\n**重要：请只针对以下函数生成测试计划，不要分析其他函数：**\n`{target_function}`"
            query += f"\n\n输出的 function_name 字段必须是 `{target_function}`。"

        # 调用 LLM 获取原始响应（内含逻辑分析和测试计划）
        raw = self._call_llm(query)
        # 解析 JSON 响应
        result = self._extract_json(raw)

        # 兼容性处理：确保返回的 JSON 包含 logic_analysis 字段
        # 部分模型可能跳过思维链步骤直接输出测试计划，填充空值避免下游崩溃
        if "logic_analysis" not in result or result["logic_analysis"] is None:
            result["logic_analysis"] = {
                "input_domain": "",
                "output_domain": "",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            }
            logger.warning("LLM 未输出 logic_analysis，已填充空值")

        # 记录规划完成日志，便于追踪每个函数的分析耗时
        logger.info("Planner 完成对 %s 的逻辑分析", result.get("function_name", "unknown"))
        return result
