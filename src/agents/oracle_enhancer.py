"""
测试预言增强器（Oracle Enhancer，默认关）。

背景（P0 测试预言生成方向）：
    LLM 生成的测试用例常因"预言缺失或错误"而无法有效暴露缺陷——
    测试"通过"可能只是因为断言太弱（恒真断言 / 弱断言 / 魔数未命名），
    产生"高覆盖率 ≠ 高质量"的虚假安全感。本模块引入**规约驱动预言增强**：
    在 Planner 产出 logic_analysis（输入域/输出域/前置-后置条件/边界情况）后，
    由独立 LLM 调用对每个 test_case 的"期望值"做规约推理，产出更精确、
    可执行的断言预言（oracle），并标注该预言的"来源"（postcondition /
    edge_case / invariant），供 Generator 生成更强断言。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `ORACLE_ENHANCE_ENABLE=false`（默认）时，本模块零行为变化：
      Planner 输出原样传递，Generator prompt 与历史逐字节一致；
    - 开关开启后，仅当 test_plan 含非空 test_cases 时触发；LLM 调用失败
      时**保守降级**（保留原 test_cases，仅记录 oracle_enhanced=False），
      不阻断生成主流程；
    - 增强结果是"追加字段"（test_cases[].oracle），不修改 test_cases 既有
      结构，下游 Generator 按"oracle 字段存在则优先消费"的保守口径使用；
    - 预言有效性评估（区分"通过测试"与"有效测试"）作为纯观测层：
      增强后为每个 test_case 标注 `oracle_confidence`（LLM 自评 0.0-1.0），
      供实验分析统计"弱预言占比"，不参与路由。

使用方式（workflow 节点 / PlannerAgent 集成）：
    from src.agents.oracle_enhancer import OracleEnhancerAgent, oracle_enhance_enabled

    if oracle_enhance_enabled():
        enhancer = OracleEnhancerAgent()
        test_plan = enhancer.enhance(test_plan)
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from src.agents.base_agent import BaseAgent
from src.prompts.templates import ORACLE_ENHANCER_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

# 增强后注入的预言字段最大保留数（避免 test_cases 过多时 prompt 爆炸；
# 与 generator._MAX_RAG_REFERENCES 同口径，经验值 10）
_MAX_ORACLE_CASES = 10


def oracle_enhance_enabled() -> bool:
    """测试预言增强开关（ORACLE_ENHANCE_ENABLE=true 时启用，默认 false）。

    默认关闭保持历史实验口径不变（Planner → Generator 零变化）。
    """
    return os.getenv("ORACLE_ENHANCE_ENABLE", "false").lower() == "true"


class OracleEnhancerAgent(BaseAgent):
    """测试预言增强器：基于逻辑分析（规约）对测试用例的期望值做推理增强。

    输入:
        test_plan: PlannerAgent 输出的测试计划字典（含 logic_analysis / test_cases）。

    输出:
        增强后的 test_plan（原字典就地追加 oracle 字段，不破坏既有结构）：
        - test_cases[i].oracle: 强化断言预言字符串（如 "assert result == a + b"）；
        - test_cases[i].oracle_source: "postcondition" | "edge_case" | "invariant" | "unknown"；
        - test_cases[i].oracle_confidence: float（LLM 自评，0.0-1.0）；
        - test_plan["oracle_enhanced"]: bool（本次增强是否成功注入）。
    """

    def __init__(self) -> None:
        super().__init__(ORACLE_ENHANCER_SYSTEM_PROMPT)

    def enhance(self, test_plan: dict[str, Any]) -> dict[str, Any]:
        """对 test_plan 中的 test_cases 做规约驱动预言增强（保守降级）。

        流程：
        1. 提取 logic_analysis（前置/后置条件 + 边界情况）作为规约输入；
        2. 构造 query，要求 LLM 为每个 test_case 产出强化断言预言；
        3. 解析 LLM 输出（JSON），按 case_name 对齐回写 oracle 字段；
        4. 任意一步失败（LLM 异常 / 解析失败 / 对齐缺失）→ 保留原 test_cases，
           仅置 oracle_enhanced=False（不阻断主流程）。

        Args:
            test_plan: PlannerAgent 输出的测试计划字典。

        Returns:
            增强后的 test_plan（同一引用，oracle 字段追加式写入）。
        """
        test_cases = test_plan.get("test_cases") or []
        logic_analysis = test_plan.get("logic_analysis") or {}
        if not test_cases:
            test_plan["oracle_enhanced"] = False
            return test_plan

        # 截断 test_cases 数量（避免 prompt 爆炸），与 _MAX_ORACLE_CASES 同口径
        limited_cases = test_cases[:_MAX_ORACLE_CASES]

        # 规约来源：logic_analysis 的前置/后置条件 + 边界情况（纯文本，零额外 LLM 成本）
        spec_input = json.dumps(
            {
                "preconditions": logic_analysis.get("preconditions", []),
                "postconditions": logic_analysis.get("postconditions", []),
                "edge_cases": logic_analysis.get("edge_cases", []),
                "input_domain": logic_analysis.get("input_domain", ""),
                "output_domain": logic_analysis.get("output_domain", ""),
            },
            ensure_ascii=False,
        )
        cases_input = json.dumps(limited_cases, ensure_ascii=False)
        query = (
            f"以下是测试规划的规约输入（前置/后置条件 + 边界情况）：\n{spec_input}\n\n"
            f"以下是测试用例列表（JSON）：\n{cases_input}\n\n"
            "请为每个 test_case 产出强化断言预言。"
            '输出 JSON 数组，每项含 {"case_name": str, "oracle": str, '
            '"oracle_source": "postcondition"|"edge_case"|"invariant"|"unknown", '
            '"oracle_confidence": float(0.0-1.0)}。'
        )
        try:
            raw = self._call_llm_with_cache(query)
            parsed = self._extract_json(raw)
            # _extract_json 可能返回单个对象（包裹在 {"oracles": [...]}）或列表
            if isinstance(parsed, dict) and "oracles" in parsed:
                parsed = parsed["oracles"]
            if not isinstance(parsed, list):
                logger.warning("OracleEnhancer LLM 输出非列表，保守降级（保留原 test_cases）")
                test_plan["oracle_enhanced"] = False
                return test_plan
            # 按 case_name 对齐回写（对齐缺失时保守跳过，不阻断）。
            # 经类调用 staticmethod（而非 self._apply_oracles）：保持"追加式
            # 纯函数"语义，不依赖实例状态（_apply_oracles 是 @staticmethod）。
            OracleEnhancerAgent._apply_oracles(test_cases, parsed)
            test_plan["oracle_enhanced"] = True
        except (json.JSONDecodeError, RuntimeError, OSError) as e:
            # LLM 调用失败 / 缓存 OSError / 解析失败：保守降级，保留原 test_cases
            logger.warning("OracleEnhancer 增强失败（保守降级，保留原 test_cases）: %s", e)
            test_plan["oracle_enhanced"] = False
        return test_plan

    @staticmethod
    def _apply_oracles(test_cases: list[dict[str, Any]], oracles: list[Any]) -> None:
        """把 LLM 输出的预言按 case_name 对齐回写 test_cases（追加式，不改既有字段）。"""
        oracle_by_name: dict[str, dict[str, Any]] = {}
        for entry in oracles:
            if isinstance(entry, dict):
                name = str(entry.get("case_name", ""))
                if name:
                    oracle_by_name[name] = entry
        for case in test_cases:
            name = str(case.get("case_name", ""))
            entry = oracle_by_name.get(name)
            if entry is None:
                continue  # 对齐缺失：保留原 case，不注入预言（保守）
            case["oracle"] = str(entry.get("oracle", ""))
            case["oracle_source"] = str(entry.get("oracle_source", "unknown"))
            conf = entry.get("oracle_confidence")
            try:
                case["oracle_confidence"] = max(0.0, min(1.0, float(conf)))
            except (TypeError, ValueError):
                case["oracle_confidence"] = 0.0
