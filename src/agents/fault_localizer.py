"""RGFL 式推理引导故障定位（修复引擎第一阶段，2026-10-07 范式转向批）。

背景（2026-10-07 用户拍板"立即转向修复引擎"）：
    E2 定案"编排容器在检出口径下结构性劣后"（δ=−0.367 bayes_neg）+
    FL@1 35.8% 首度测量，证实局部化是当前管线的第一短板。前沿 APR 的
    共识范式为"局部化 → 合成 → 验证"且局部化是瓶颈（Hunk-SWE/Maple：
    局部化相近的智能体修复准确率差 30pp；RGFL：file-level Hit@1
    71.4%→85%——arXiv 2601.18044，引用核验 2026-10-07）。

本模块把局部化从"Debugger 的副产品"升格为**可独立量化的阶段**：

双通道融合：
    A. Ochiai 谱系（零 LLM，复用 fl_spectral 测量层）——行级可疑度
       排序，作为 LLM 推理的客观佐证注入 prompt；
    B. LLM 推理定位（本模块，RGFL 式）——输入失败测试 + 错误输出 +
       谱系 Top-k 佐证，输出结构化 JSON：
       {"function_name", "line_start", "line_end", "confidence",
        "reasoning"}。

消费方式：
    - Debugger prompt 注入（定位段落，与既有谱系段落并列）；
    - 实验指标（局部化独立口径，与检出率/修复率/FL@k 并列输出）：
      * localization_hit_function：LLM 定位函数 ∈ gold 变更函数集合；
      * localization_hit_file：跨文件任务才有效（单文件恒命中）；
      * 行级沿用 FL@k（fl_at_k）。

降级口径（保守）：
    LLM 调用失败 / JSON 解析失败 / 必填字段缺失 → None（不产出
    假定位；评估层按"不可测"处理，键集合同构保持历史批次兼容）。

开关：FAULT_LOCALIZER_ENABLE（默认 true——修复引擎主路径；显式
"false" 退回纯谱系口径，消融对照用）。
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
from typing import Any

from src.agents.base_agent import BaseAgent

logger = logging.getLogger(__name__)

_ENV = "FAULT_LOCALIZER_ENABLE"


def fault_localizer_enabled() -> bool:
    """修复引擎第一阶段开关（默认开；显式 false 退回纯谱系消融口径）。"""
    return os.getenv(_ENV, "true").lower() in ("true", "1", "on")


FAULT_LOCALIZER_SYSTEM_PROMPT = """\
你是资深 Python 故障定位专家。给定：被测源码、失败的测试代码、\
测试错误输出、以及谱系定位（Ochiai）的可疑行佐证。你的任务是\
**只定位、不修复**——找出导致测试失败的缺陷位置。

要求：
1. 输出必须是单个 JSON 对象，不要任何额外文字或 markdown 围栏；
2. function_name 填缺陷所在的函数名（模块级缺陷填 "<module>"）；
3. line_start/line_end 填缺陷语句在源码中的行号（1-based，含端点）；
4. confidence 取 0.0~1.0 的浮点数；
5. reasoning 用不超过 60 字说明定位依据；
6. 谱系佐证仅供参考——若你推断的可疑行与其冲突，以你的推理为准\
并在 reasoning 中说明。

输出格式：
{"function_name": "...", "line_start": 1, "line_end": 1, "confidence": 0.0, "reasoning": "..."}"""


class FaultLocalizerAgent(BaseAgent):
    """RGFL 式 LLM 推理定位智能体（只定位不修复，结构化 JSON 输出）。"""

    def __init__(self) -> None:
        super().__init__(FAULT_LOCALIZER_SYSTEM_PROMPT)

    def localize(
        self,
        *,
        target_code: str,
        test_code: str,
        test_output: str,
        failed_cases: list[dict[str, Any]] | None = None,
        spectral_top_k: list[dict[str, Any]] | None = None,
        max_retries: int = 2,
    ) -> dict[str, Any] | None:
        """LLM 推理定位（结构化 JSON；失败保守返回 None）。

        Args:
            target_code: 被测源码全文（带行号渲染辅助定位）。
            test_code: 当前失败的测试代码全文。
            test_output: pytest 错误输出（traceback）。
            failed_cases: executor 解析的失败用例列表（触发条件）。
            spectral_top_k: Ochiai 谱系 Top-k（[{"line", "score"}, ...]
                佐证；None/空时 prompt 不含谱系段）。
            max_retries: LLM 重试次数。

        Returns:
            {"function_name": str, "line_start": int, "line_end": int,
             "confidence": float, "reasoning": str} 或 None（保守降级）。
        """
        if not target_code.strip() or not failed_cases:
            return None
        prompt = self._build_prompt(
            target_code=target_code,
            test_code=test_code,
            test_output=test_output,
            failed_cases=failed_cases,
            spectral_top_k=spectral_top_k,
        )
        try:
            raw = self._call_llm_with_cache(prompt, max_retries=max_retries, temperature=0.0)
        except Exception as e:  # 保守降级：定位失败不阻断修复主流程
            logger.warning("FaultLocalizer LLM 调用失败，保守降级 None: %s", e)
            return None
        parsed = self._parse_localization(raw)
        if parsed is None:
            logger.warning("FaultLocalizer JSON 解析失败，保守降级 None")
        return parsed

    def _build_prompt(
        self,
        *,
        target_code: str,
        test_code: str,
        test_output: str,
        failed_cases: list[dict[str, Any]] | None,
        spectral_top_k: list[dict[str, Any]] | None,
    ) -> str:
        """组装定位 prompt（源码带行号 + 失败测试 + 错误输出 + 谱系佐证）。"""
        numbered = "\n".join(f"{i:4d} | {line}" for i, line in enumerate(target_code.splitlines(), start=1))
        spectral_section = ""
        if spectral_top_k:
            rows = ", ".join(f"L{item.get('line')}({item.get('score')})" for item in spectral_top_k[:5])
            spectral_section = f"\n【谱系定位佐证（Ochiai Top-k）】{rows}\n"
        failed_names = ", ".join(str(c.get("test") or c.get("nodeid") or "?") for c in (failed_cases or [])[:5])
        return (
            f"【被测源码（带行号）】\n{numbered}\n"
            f"\n【失败的测试】\n{test_code}\n"
            f"\n【失败用例】{failed_names}\n"
            f"\n【测试错误输出（截断）】\n{(test_output or '')[:2000]}\n"
            f"{spectral_section}"
            "\n请输出定位 JSON（只定位不修复）。"
        )

    def _parse_localization(self, raw: str) -> dict[str, Any] | None:
        """解析 LLM 定位输出（容错 markdown 围栏；必填字段缺失 → None）。"""
        try:
            data = self._extract_json(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        fn = data.get("function_name")
        if not isinstance(fn, str) or not fn.strip():
            return None
        try:
            line_start = max(1, int(data.get("line_start") or 0))
            line_end = max(line_start, int(data.get("line_end") or line_start))
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):
            return None
        return {
            "function_name": fn.strip(),
            "line_start": line_start,
            "line_end": line_end,
            "confidence": max(0.0, min(1.0, confidence)),
            "reasoning": str(data.get("reasoning") or "")[:200],
        }


def build_localization_prompt_section(loc: dict[str, Any] | None) -> str:
    """把定位结果渲染为 Debugger prompt 段落（None/空 → 空串，历史口径）。"""
    if not loc or not loc.get("function_name"):
        return ""
    return (
        f"\n【推理定位（LLM，置信度 {loc.get('confidence', 0):.2f}）】"
        f"缺陷位于函数 `{loc['function_name']}`"
        f"（L{loc.get('line_start')}-L{loc.get('line_end')}）：{loc.get('reasoning', '')}\n"
    )


def gold_changed_functions(buggy_code: str, fixed_code: str) -> set[str]:
    """gold 变更函数集合（buggy 与 fixed 的 diff 行 → AST 所属函数名）。

    函数级局部化命中的 gold 口径：缺陷行（buggy 侧被 gold 修复删除/
    替换的行）向上追溯所属函数；跨文件场景由调用方按模块分别调用。
    模块级（函数外）变更记 "<module>"。
    """
    if not buggy_code.strip() or not fixed_code.strip():
        return set()
    buggy_lines = buggy_code.splitlines()
    sm = difflib.SequenceMatcher(a=buggy_lines, b=fixed_code.splitlines(), autojunk=False)
    defect_lines: set[int] = set()
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            defect_lines.update(range(i1 + 1, i2 + 1))
    if not defect_lines:
        return set()
    try:
        tree = ast.parse(buggy_code)
    except SyntaxError:
        return {"<module>"}

    functions = [
        (node.lineno, node.end_lineno or node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    hits: set[str] = set()
    for ln in defect_lines:
        matched = [(start, name) for (start, end, name) in functions if start <= ln <= end]
        if matched:
            # 嵌套函数取起始行最大者（最内层）
            hits.add(max(matched)[1])
        else:
            hits.add("<module>")
    return hits


def localization_hit(
    loc: dict[str, Any] | None,
    gold_functions: set[str],
) -> dict[str, Any] | None:
    """函数级局部化命中判定（局部化独立指标口径）。

    Returns:
        {"localization_hit_function": bool}；loc 为 None（未定位）时
        返回 None（不可测，键集合同构占位）。
    """
    if loc is None or not gold_functions:
        return None
    fn = str(loc.get("function_name") or "")
    # gold 函数名按 "." 分隔的最后一段与 LLM 输出归一比较（方法/嵌套容错）
    gold_leaf = {g.split(".")[-1] for g in gold_functions}
    return {"localization_hit_function": fn.rsplit(".", maxsplit=1)[-1] in gold_leaf}
