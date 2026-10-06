"""
测试规划师模块：实现逻辑驱动思维链（Logic-driven Chain-of-Thought）。

Planner 在输出测试计划前，先对函数进行输入域、输出域、前置条件、
后置条件、边界情况的显式分析，引导 Generator 按逻辑覆盖生成测试用例。
"""

from __future__ import annotations

import logging
import os
from typing import Any

from src.agents.base_agent import BaseAgent
from src.prompts.templates import PLANNER_SYSTEM_PROMPT, SPEC_EXPR_CONTRACT_SECTION
from src.specs import spec_ir_dsl_enabled
from src.tools.control_flow import build_cfg_prompt_section, cfg_analysis_enabled

# 模块级日志记录器
logger = logging.getLogger(__name__)


def _logic_spec_strict_fallback_enabled() -> bool:
    """AB1（2026-10-06 生死实验根因修复）：M10 强校验拒绝的降级出口开关。

    生死实验（n=87×3 臂×3 种子，logic 档）实测 21/261 任务因
    LOGIC_SPEC_STRICT_ENABLE=true 在 Planner 第 0 轮直接 raise ——
    error_category='error'、detection=None（M1 分母外），而同任务在
    plain_llm_df 臂正常检出。强校验的设计意图（M10）是"拒绝**静默**
    兜底、供 CI 科学主张测试消费"，但 raise 把"模型未输出规约"
    （模型行为）升级成"整任务死亡"（系统故障），引入 8% 吞吐损失。

    开启本开关时，强校验拒绝改为**显式标记降级**：result 写入
    logic_spec_rejected=<原因> 后继续执行（空规约走 degraded 路径，
    下游 spec 链材料为空、spec_compile_rate 不受污染）——非静默
    （标记 + 日志），科学主张口径不回退。默认 false：独立 raise
    语义原样保留（CI 科学主张测试依赖）。logic profile 预设注入
    true（实验档吞吐恢复，行为经 provenance 可追溯）。
    """
    return os.getenv("LOGIC_SPEC_STRICT_FALLBACK_ENABLE", "false").strip().lower() in ("true", "1", "on")


def _strict_reject(result: dict[str, Any], message: str) -> None:
    """M10 强校验拒绝出口：默认 raise；fallback 开启时标记降级继续。

    标记保留**首因**：logic_analysis 缺失路径先标记后进入 schema 校验，
    后续分支的 findings（对已填充空值的校验）是缺失的下游产物——
    覆盖首因会掩盖根因（观测口径以第一次拒绝为准）。

    Args:
        result: Planner 解析结果（fallback 时写入 logic_spec_rejected 标记）。
        message: 拒绝原因（raise 消息 / 标记值，含 M10 前缀供下游归因）。
    """
    if _logic_spec_strict_fallback_enabled():
        if "logic_spec_rejected" not in result:
            result["logic_spec_rejected"] = message
            logger.warning("M10 强校验拒绝已降级（LOGIC_SPEC_STRICT_FALLBACK_ENABLE=true）：%s", message)
        else:
            logger.warning("M10 强校验后续拒绝（首因已标记，保留）：%s", message)
        return
    raise ValueError(message)


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
        preconditions: list[str],
        postconditions: list[str],
        edge_cases: list[str],
    ) -> None:
        # 初始化各字段
        self.input_domain = input_domain
        self.output_domain = output_domain
        self.preconditions = preconditions
        self.postconditions = postconditions
        self.edge_cases = edge_cases

    def to_dict(self) -> dict[str, Any]:
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

    def plan(self, target_code: str, target_function: str | None = None) -> dict[str, Any]:
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
            RuntimeError: LLM 调用失败（重试耗尽）时抛出。
            json.JSONDecodeError: LLM 返回非 JSON 格式时抛出（_extract_json 委托 extract_json_object）。
        """
        # 截断超长代码，节省 token（大文件按焦点函数做 AST 智能截取，
        # 保留 import 与直接依赖，避免 LLM 看不到目标函数）
        target_code = BaseAgent.truncate_code(target_code, focus_function=target_function)
        # 构建查询：包含代码和可选的函数限定
        query = f"请分析以下代码并制定测试计划：\n\n```\n{target_code}\n```"
        if target_function:
            # 明确指定要测试的函数，要求输出中包含该函数名
            query += f"\n\n**重要：请只针对以下函数生成测试计划，不要分析其他函数：**\n`{target_function}`"
            query += f"\n\n输出的 function_name 字段必须是 `{target_function}`。"

        # 2.2 控制流图（CFG）静态层：纯 AST 分析（零 LLM 成本），把分支/
        # 循环/异常路径摘要注入 prompt，使测试用例覆盖系统化（按路径
        # 而非 LLM 自由发挥）。CFG_ANALYSIS_ENABLE=false 时零变化。
        if cfg_analysis_enabled():
            from src.tools.control_flow import analyze_control_flow

            cfg = analyze_control_flow(target_code, target_function)
            cfg_section = build_cfg_prompt_section(cfg)
            if cfg_section:
                query += cfg_section

        # AC1（2026-10-06 第十轮审查 T-P0-2）：规约表达式通道契约段。
        # SPEC_IR_DSL_ENABLE=true（logic/scientific 档）时追加，要求 LLM 在
        # 中文 NL 规约之外并行输出可机器执行的表达式子句——修复 prompt 与
        # SpecIR v2 编译器的契约断裂（NL 中文子句被 _EXPR_TOKEN_RE 白名单
        # 100% 拒绝 → spec_compile_rate 恒 0.0，AB1 验证批 12/12 实证）。
        # 默认关不追加，prompt 零变化（ADR-0003）。
        if spec_ir_dsl_enabled():
            query += SPEC_EXPR_CONTRACT_SECTION

        # 调用 LLM 获取原始响应（内含逻辑分析和测试计划），带文件缓存省 token
        raw = self._call_llm_with_cache(query)
        # 解析 JSON 响应
        result = self._extract_json(raw)

        # 兼容性处理：确保返回的 JSON 包含 logic_analysis 字段
        # 部分模型可能跳过思维链步骤直接输出测试计划，填充空值避免下游崩溃
        # M10（2026-09-29 审查 P0）：静默兜底改为显式标记。
        # 历史口径：LLM 不输出 logic_analysis 时静默填 5 个空字段
        # （"逻辑驱动"主张不可证伪）。现补 logic_degraded=True 标记
        # （纯观测，不参与路由），供实验层把该任务归入"未走逻辑驱动
        # 路径"而非"逻辑驱动成功"。LOGIC_SPEC_STRICT_ENABLE=true
        # （默认 false）时把 degraded 态提升为 ValueError（强校验），
        # 供 CI 科学主张测试消费。
        if "logic_analysis" not in result or result["logic_analysis"] is None:
            result["logic_analysis"] = {
                "input_domain": "",
                "output_domain": "",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            }
            result["logic_degraded"] = True
            logger.warning("M10：LLM 未输出 logic_analysis，已填充空值并标记 logic_degraded=True")
            if os.getenv("LOGIC_SPEC_STRICT_ENABLE", "false").lower() in ("true", "1", "on"):
                _strict_reject(result, "M10 LOGIC_SPEC_STRICT_ENABLE=true：logic_analysis 缺失，拒绝静默兜底")
        else:
            result.setdefault("logic_degraded", False)
        # M10（2026-09-29 审查 P0）：schema 强校验——对 logic_analysis 做
        # 必填字段 + 类型 + 非空校验（纯数据，零 LLM 成本）。findings 非空时
        # 写入 result["logic_spec_findings"]（纯观测，不参与路由），供
        # 实验层"空值率 = 0"指标消费。LOGIC_SPEC_STRICT_ENABLE=true
        # （默认 false）时把 degraded 态提升为 ValueError（强校验），
        # 供 CI 科学主张测试消费。
        from src.tools.logic_spec import logic_spec_strict_enabled as _logic_spec_strict_enabled
        from src.tools.logic_spec import validate_logic_spec as _validate_spec

        _spec_findings = _validate_spec(result.get("logic_analysis"))
        if _spec_findings:
            result["logic_spec_findings"] = _spec_findings
            # 仅当 LLM 已输出 logic_analysis（非静默兜底路径）且 findings 非空时
            # 才标记 logic_degraded=True（静默兜底路径已在上方 L176 标记）
            if not result.get("logic_degraded", False):
                result["logic_degraded"] = True
            logger.warning(
                "M10 schema 校验：%d 条 findings（fields=%s）",
                len(_spec_findings),
                [f.get("field") for f in _spec_findings],
            )
            if _logic_spec_strict_enabled() and result.get("logic_degraded"):
                _strict_reject(
                    result, "M10 LOGIC_SPEC_STRICT_ENABLE=true：logic_analysis schema 校验失败，拒绝静默兜底"
                )
        # M10（2026-09-29 审查 P0）：logic_coverage 字段消费者验证。
        # 历史口径：prompt 要求 test_case 标注 logic_coverage，但全仓
        # 无任何消费者（字段纯写入无读取）。现补 coverage_completeness
        # 观测指标（0.0–1.0）：统计 test_cases 中非空 logic_coverage
        # 的占比，供实验层度量"逻辑驱动"实际生效程度（纯观测，默认
        # 零行为变化）。
        _cases = result.get("test_cases") or []
        if _cases:
            _with_cov = sum(1 for c in _cases if isinstance(c, dict) and c.get("logic_coverage"))
            result["coverage_completeness"] = round(_with_cov / len(_cases), 4)
        else:
            result["coverage_completeness"] = None

        # 记录规划完成日志，便于追踪每个函数的分析耗时
        logger.info("Planner 完成对 %s 的逻辑分析", result.get("function_name", "unknown"))
        return result
