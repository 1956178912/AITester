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
       谱系 Top-k 佐证，输出结构化 JSON（批次 II 起为 Top-3 候选排序）：
       {"candidates": [{"function_name", "line_start", "line_end",
         "confidence", "expected_logic", "reasoning"}, ...]}（按可能性
       从高到低；expected_logic = RGFL 推理引导——先陈述"该处应有的
       正确行为"再对比实际代码）。

消费方式：
    - Debugger prompt 注入（定位段落，与既有谱系段落并列；用首位候选）；
    - 实验指标（局部化独立口径，与检出率/修复率/FL@k 并列输出）：
      * localization_hit_function：首位候选函数 ∈ gold 变更函数集合
        （元素级 Hit@1，批次 I 起已有）；
      * localization_hit_function_at_3 / localization_mrr：Top-3 命中
        与 MRR（元素级排序指标，批次 II 起，对齐 RGFL 两阶段排序
        评测口径；经 localization_rank_metrics 计算）；
      * localization_hit_file：跨文件任务才有效（单文件恒命中）；
      * 行级沿用 FL@k（fl_at_k）；
      * fl_constraint_verdict：FL Top-k 约束观测门（批次 XIV，ADR-0028）
        ——补丁变更函数集合与定位 Top-3 候选求交，量化定位信号被
        合成侧实际消费的程度（run_benchmark 结果行透出）。

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
# 修复引擎批次 X（ADR-0024）：反事实 FL 上界实验的 gold 注入开关——
# 开启时定位段直接用 gold 变更函数构造（跳过 LLM），模拟"完美定位"
# 反事实臂。默认关（ADR-0003）；该臂结果**不得与正常口径混读**
# （state["gold_fixed_code"] 本为门禁专用材料，本开关是显式消融例外）。
_GOLD_INJECTION_ENV = "FL_GOLD_INJECTION_ENABLE"


def fault_localizer_enabled() -> bool:
    """修复引擎第一阶段开关（默认开；显式 false 退回纯谱系消融口径）。"""
    return os.getenv(_ENV, "true").lower() in ("true", "1", "on")


def gold_injection_enabled() -> bool:
    """反事实臂开关（默认关）——开启时定位用 gold 函数构造，跳过 LLM。"""
    return os.getenv(_GOLD_INJECTION_ENV, "false").lower() in ("true", "1", "on")


def build_gold_injection_localization(target_code: str, gold_fixed_code: str) -> dict[str, Any] | None:
    """反事实臂定位构造器（零 LLM）：gold 变更函数 → 同构定位结果。

    用 gold_changed_functions 提取 gold 函数集合，对每个函数在
    target_code 中以 AST 定位行范围，构造与 LLM 输出同构的候选列表
    （confidence=1.0，reasoning 标注 gold injection 反事实臂身份——
    报告/结果行可据此识别与剔除）。无 gold 材料 / gold 函数在
    target_code 中不可定位 → None（保守降级，与 LLM 失败同口径）。

    "<module>"（模块级变更）无函数可定位，跳过不构造候选。
    """
    if not target_code.strip() or not gold_fixed_code.strip():
        return None
    gold_fns = gold_changed_functions(target_code, gold_fixed_code)
    if not gold_fns:
        return None
    try:
        tree = ast.parse(target_code)
    except SyntaxError:
        return None
    ranges: dict[str, tuple[int, int]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in gold_fns:
            ranges[node.name] = (node.lineno, node.end_lineno or node.lineno)
    if not ranges:
        return None
    candidates: list[dict[str, Any]] = []
    for fn, (start, end) in sorted(ranges.items(), key=lambda kv: kv[1][0]):
        candidates.append(
            {
                "function_name": fn,
                "line_start": start,
                "line_end": end,
                "confidence": 1.0,
                "expected_logic": "",
                "reasoning": "gold injection（反事实臂：完美定位上界实验，非系统能力）",
            }
        )
    first = dict(candidates[0])
    first["candidates"] = candidates
    return first


FAULT_LOCALIZER_SYSTEM_PROMPT = """\
你是资深 Python 故障定位专家。给定：被测源码、失败的测试代码、\
测试错误输出、以及谱系定位（Ochiai）的可疑行佐证。你的任务是\
**只定位、不修复**——找出导致测试失败的缺陷位置。

要求（推理引导，先期望后对比）：
1. 对每个候选位置，先在 expected_logic 写出"该处应有的正确行为"\
（不超过 60 字），再在 reasoning 对比实际代码说明缺陷依据\
（不超过 60 字）；
2. 输出 1~3 个候选，按可能性从高到低排序（首候选用于注入修复\
prompt，全部候选用于 Hit@3/MRR 排序评测）；
3. 输出必须是单个 JSON 对象，不要任何额外文字或 markdown 围栏；
4. function_name 填缺陷所在的函数名（模块级缺陷填 "<module>"）；
5. line_start/line_end 填缺陷语句在源码中的行号（1-based，含端点）；
6. confidence 取 0.0~1.0 的浮点数；
7. 谱系佐证仅供参考——若你推断的可疑行与其冲突，以你的推理为准\
并在 reasoning 中说明。

输出格式：
{"candidates": [{"function_name": "...", "line_start": 1, "line_end": 1, "confidence": 0.0, "expected_logic": "...", "reasoning": "..."}]}"""


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
             "confidence": float, "expected_logic": str, "reasoning": str,
             "candidates": [同构候选 dict × 1~3（按可能性降序）]}
            或 None（保守降级）。顶层字段 = 首位候选（向后兼容：prompt
            段落渲染与既有指标只读顶层）。
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
            "\n请输出定位 JSON（只定位不修复，1~3 个候选按可能性降序）。"
        )

    def _parse_localization(self, raw: str) -> dict[str, Any] | None:
        """解析 LLM 定位输出（容错 markdown 围栏；无有效候选 → None）。

        兼容两种 schema（批次 II 起请求新格式，旧格式降级接受）：
        - 新：{"candidates": [候选, ...]}（1~3 个，截断到 3）；
        - 旧：单对象 {"function_name": ...}（视为单候选）。
        顶层返回首位候选字段 + "candidates" 完整列表。
        """
        try:
            data = self._extract_json(raw)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        raw_candidates = data.get("candidates")
        if isinstance(raw_candidates, list) and raw_candidates:
            parsed = [c for c in (self._normalize_candidate(x) for x in raw_candidates) if c]
        else:
            parsed = [c for c in (self._normalize_candidate(data),) if c]
        if not parsed:
            return None
        parsed = parsed[:3]
        out = dict(parsed[0])
        out["candidates"] = parsed
        return out

    @staticmethod
    def _normalize_candidate(data: Any) -> dict[str, Any] | None:
        """单候选字段校验与归一（必填缺失/类型错误 → None）。"""
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
            "expected_logic": str(data.get("expected_logic") or "")[:200],
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


def _functions_containing_lines(tree: ast.Module, lines: set[int]) -> set[str]:
    """把 1-based 行号集合映射到所属函数名（嵌套取最内层；函数外记 "<module>"）。

    gold_changed_functions / patch_changed_functions 共用的 AST 归属口径。
    行号 0（补丁文件顶部插入的哨兵锚点）不属于任何函数 → "<module>"。
    """
    functions = [
        (node.lineno, node.end_lineno or node.lineno, node.name)
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    hits: set[str] = set()
    for ln in lines:
        matched = [(start, name) for (start, end, name) in functions if start <= ln <= end]
        if matched:
            # 嵌套函数取起始行最大者（最内层）
            hits.add(max(matched)[1])
        else:
            hits.add("<module>")
    return hits


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

    return _functions_containing_lines(tree, defect_lines)


def patch_changed_functions(buggy_code: str, patched_code: str) -> set[str]:
    """补丁变更函数集合（buggy 与 patched 的 diff 行 → AST 所属函数名）。

    批次 XIV（ADR-0028）：FL Top-k 约束门的"补丁侧"输入——补丁实际
    修改了哪些函数。与 gold_changed_functions 同一 AST 归属口径
    （嵌套取最内层，模块级记 "<module>"），差异两点：
    - **insert 段锚定 buggy 侧 i1**（插入发生在第 i1 行之后；i1=0 即
      文件顶部，哨兵行 0 经 _functions_containing_lines 落 "<module>"）
      ——纯插入型修复（如函数内补一个前置判空）在 gold 口径（只计
      delete/replace）下是空集合，约束门此处必须计入；
    - 无早退：buggy 不可解析 → {"<module>"}（与 gold 同口径的保守
      粗粒度）；patched 不可解析**不阻断**（行级 diff 纯文本，函数
      归属只在 buggy 侧）——LLM 产出的坏补丁同样可测其触碰范围。
    两码本相同（无删除无插入）时返回空集合（调用方落 not_evaluable）。
    """
    if not buggy_code.strip() or not patched_code.strip():
        return set()
    sm = difflib.SequenceMatcher(a=buggy_code.splitlines(), b=patched_code.splitlines(), autojunk=False)
    changed_lines: set[int] = set()
    for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            changed_lines.update(range(i1 + 1, i2 + 1))
        elif tag == "insert":
            changed_lines.add(i1 if i1 >= 1 else 0)
    if not changed_lines:
        return set()
    try:
        tree = ast.parse(buggy_code)
    except SyntaxError:
        return {"<module>"}
    return _functions_containing_lines(tree, changed_lines)


def fl_constraint_verdict(loc: dict[str, Any] | None, changed_functions: set[str]) -> dict[str, Any] | None:
    """FL Top-k 约束观测门判定核（批次 XIV，ADR-0028）。

    问题口径（外部报告 P0-3 净新增）："补丁是否真的修改了定位候选
    位置之一"——定位命中但补丁改在别处 = 定位信号被合成侧浪费
    （ADR-0024"生成侧主导"假设的行级验证器）。

    判定：定位候选（叶子名归一去重排序，与 localization_rank_metrics
    同口径；旧 schema 无 "candidates" 时退化为单候选）与补丁变更函数
    集合求交——任一候选命中 → "hit"（hit_rank = 首个命中候选的序数，
    供阻断档分层设计）；有候选但零交集 → "miss"。

    Returns:
        {"verdict": "hit" | "miss", "hit_rank": int | None,
         "changed_functions": sorted(list)}；
        loc 为 None / 无有效候选 / 变更集合为空 → None（调用方落
        not_evaluable，保守降级与 test-hacking 门口径一致）。

    已知局限（ADR-0028 登记）：整文件重写补丁的变更集合 ≈ 全文件
    函数，判定近乎恒 hit（无约束力）——约束力集中在局部编辑通道
    （EDIT_INTENT / 函数级补丁）；"<module>" 级变更（如纯 import 调整）
    与任何函数候选不相交，记 miss 属口径内事实（阻断档判据须为此
    设豁免，见 ADR-0028）。
    """
    if loc is None or not changed_functions:
        return None
    changed_leaf = {g.split(".")[-1] for g in changed_functions}
    candidates = loc.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        candidates = [loc]
    rank = 0
    seen: set[str] = set()
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        leaf = str(cand.get("function_name") or "").rsplit(".", maxsplit=1)[-1]
        if not leaf or leaf in seen:
            continue
        seen.add(leaf)
        rank += 1
        if leaf in changed_leaf:
            return {"verdict": "hit", "hit_rank": rank, "changed_functions": sorted(changed_functions)}
    if not seen:
        # 无有效候选（如空定位对象）→ 不可评估而非 miss
        return None
    return {"verdict": "miss", "hit_rank": None, "changed_functions": sorted(changed_functions)}


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


def localization_rank_metrics(
    loc: dict[str, Any] | None,
    gold_functions: set[str],
) -> dict[str, Any] | None:
    """元素级 Top-k 命中与 MRR（批次 II，RGFL 两阶段排序评测口径）。

    候选按可能性降序去重（叶子名归一，方法/嵌套与 hit 判定同口径）后：
      - localization_hit_function_at_3：Top-3 内任一候选命中 gold；
      - localization_mrr：首个命中候选的 1/rank（无命中 0.0）。
    loc 无 "candidates"（批次 I 旧 schema / 历史工件）时退化为单候选：
    at_3 = hit@1，MRR = 命中 1.0 / 未命中 0.0。

    Returns:
        {"localization_hit_function_at_3": bool, "localization_mrr": float}；
        loc 为 None / 无有效候选 / gold 空 → None（不可测）。
    """
    if loc is None or not gold_functions:
        return None
    gold_leaf = {g.split(".")[-1] for g in gold_functions}
    candidates = loc.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        candidates = [loc]
    ranked: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        if not isinstance(cand, dict):
            continue
        leaf = str(cand.get("function_name") or "").rsplit(".", maxsplit=1)[-1]
        if leaf and leaf not in seen:
            seen.add(leaf)
            ranked.append(leaf)
    if not ranked:
        return None
    top3 = ranked[:3]
    mrr = 0.0
    for rank, leaf in enumerate(top3, start=1):
        if leaf in gold_leaf:
            mrr = 1.0 / rank
            break
    return {
        "localization_hit_function_at_3": any(leaf in gold_leaf for leaf in top3),
        "localization_mrr": mrr,
    }
