"""反例驱动精化（CEGIR，R4 2026-10-09 审查落地·S1 第二部分）。

背景（2026-10-09 系统评审 R4·S1）：
    SpecSMT（src/specs/spec_smt.py）只做**检测**——前件空洞
    （check_precondition_vacuity）与后件自相矛盾
    （check_postcondition_consistency）的 UNSAT 判定。但"逻辑驱动"主张的
    完整闭环还缺**反例回灌 LLM 修正契约**这一步：检测到矛盾后，把矛盾
    子句回灌 LLM，让它**只修正契约（不改代码）**，再 SMT 复验，预算化
    迭代直到收敛。这是把 H1（spec_compile_rate 灰区，E2=0.212）从
    "悬置"推进到"成立"的关键机制——Balestra et al. ICST 2026
    （LLM 反例丢弃 11.68% 无效断言、规格推断 precision +7pp）与
    SpecPylot（icontract+CrossHair 预算化反例精化）的前沿共识。

设计（与 spec_smt / spec_ir_v2 同口径：默认关，零 LLM 成本）：
    - SPEC_REFINE_ENABLE=true 时启用（默认 false，历史口径零变化）；
    - 迭代上限 SPEC_REFINE_MAX_ROUNDS（默认 2，下限 0 上限 5）；
    - 每轮：check_spec_consistency 检测 → 前件/后件均非 unsat 即收敛；
      存在 unsat → 构造反例 prompt（含被测代码 + 矛盾说明）→ LLM 修正
      契约 → 替换 spec 的 pre/post/inv 子句 → 复验；
    - LLM 返回非 JSON / 无有效子句 / 调用异常 → 保守停止（保留当前 spec，
      不臆造、不静默覆盖），与"宁可无见证，不产坏约束"同口径。

本模块是**独立可调用能力**（可观测、可测试、默认关），不接入主链路
（Planner/Generator 调用点的接入属后续批次，需先定"在哪一步消费精化
结果、如何进 M1 指标"）。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_ENV_REFINE = "SPEC_REFINE_ENABLE"
_ENV_MAX_ROUNDS = "SPEC_REFINE_MAX_ROUNDS"


def spec_refine_enabled() -> bool:
    """反例精化开关（SPEC_REFINE_ENABLE=true 时启用，默认 false）。"""
    return os.getenv(_ENV_REFINE, "false").strip().lower() in ("true", "1", "on")


def _max_refine_rounds() -> int:
    """迭代上限（SPEC_REFINE_MAX_ROUNDS，默认 2，下限 0 上限 5）。"""
    try:
        return max(0, min(5, int(os.getenv(_ENV_MAX_ROUNDS, "2"))))
    except ValueError:
        return 2


def _has_conflict(findings: dict[str, Any]) -> bool:
    """联合检测结果中是否存在任一 unsat（前件空洞 / 后件自相矛盾）。"""
    pre = findings.get("precondition") or {}
    post = findings.get("postcondition") or {}
    return pre.get("status") == "unsat" or post.get("status") == "unsat"


def _build_refine_prompt(
    target_code: str,
    spec: dict[str, Any],
    findings: dict[str, Any],
) -> str:
    """构造反例精化 prompt：只让 LLM 修正矛盾子句，不改代码。"""
    pre = spec.get("preconditions") or []
    post = spec.get("postconditions") or []
    inv = spec.get("invariants") or []
    pre_f = findings.get("precondition") or {}
    post_f = findings.get("postcondition") or {}
    parts: list[str] = [
        "你是一名软件测试专家，正在修正一段函数的逻辑规约。",
        "被测函数代码如下：",
        f"```\n{target_code}\n```",
        "",
        "该函数当前的逻辑规约如下：",
        f"- 前置条件 preconditions: {json.dumps(pre, ensure_ascii=False)}",
        f"- 后置条件 postconditions: {json.dumps(post, ensure_ascii=False)}",
        f"- 不变量 invariants: {json.dumps(inv, ensure_ascii=False)}",
        "",
        "经 SMT 求解器检验，上述规约存在逻辑矛盾（无法被任何取值同时满足）：",
    ]
    if pre_f.get("status") == "unsat":
        parts.append("- 前置条件互相矛盾：不存在任何输入能同时满足全部前置条件。")
    if post_f.get("status") == "unsat":
        parts.append("- 后置条件互相矛盾：不存在任何返回值能同时满足全部后置条件。")
    parts.extend(
        [
            "",
            "请**只修正互相矛盾的规约子句**，不要修改代码，也不要臆造代码没有的性质。要求：",
            (
                "1. 每个前置/后置/不变量子句必须是**可机器执行的表达式**（只用 ASCII 运算符，"
                "如 `x > 0`、`r == a + b`、`0 <= r < 100`，禁止中文描述或自然语言短语）；"
            ),
            "2. 修正后所有前置条件必须可同时满足，所有后置条件必须可同时满足；",
            "3. 保持与代码语义一致。",
            "",
            "只输出 JSON，不要输出任何其他文字，格式如下：",
            '{"preconditions": ["..."], "postconditions": ["..."], "invariants": ["..."]}',
        ]
    )
    return "\n".join(parts)


def _apply_refinement(spec: dict[str, Any], refined: dict[str, Any]) -> dict[str, Any]:
    """把 LLM 修正结果应用到 spec（仅替换 pre/post/inv 三个字段，其余字段保留）。

    只接受非空 str 列表；缺失 / 非法字段保持原值（保守：不臆造、不破坏）。
    """
    new = dict(spec)
    for key in ("preconditions", "postconditions", "invariants"):
        val = refined.get(key)
        if isinstance(val, list):
            cleaned = [str(v).strip() for v in val if isinstance(v, str) and str(v).strip()]
            if cleaned:
                new[key] = cleaned
    return new


def _default_refine_fn(temperature: float) -> Callable[[str], str]:
    """默认 LLM 精化回调：复用 PlannerAgent 的缓存 LLM 调用（测试可注入替代）。"""
    from src.agents.planner import PlannerAgent

    agent = PlannerAgent()

    def _refine(prompt: str) -> str:
        return agent._call_llm_with_cache(prompt, temperature=temperature)

    return _refine


def refine_spec_with_counterexample(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
    target_code: str = "",
    max_rounds: int | None = None,
    temperature: float = 0.0,
    _llm_refine: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """反例驱动精化：检测规约矛盾 → 回灌 LLM 修正契约 → SMT 复验（预算化迭代）。

    Args:
        spec: SpecIR 字典（parse_logic_analysis 产物；None = 无规约材料）。
        signature_params: 被测函数参数名列表（SMT 排序推断用；None/空 → 无法
            检测，直接返回不精化）。
        target_code: 被测代码全文（LLM 修正契约需要代码语义上下文）。
        max_rounds: 迭代上限（None 时读 SPEC_REFINE_MAX_ROUNDS，默认 2）。
        temperature: LLM 采样温度（默认 0.0，确定性修正）。
        _llm_refine: 可注入 LLM 回调（测试用；None 时用 PlannerAgent 默认实现）。

    Returns:
        {
            "spec": 修正后的 SpecIR（无变化时返回原 spec 引用）,
            "rounds": 实际迭代轮数（0 = 首轮即收敛或未精化）,
            "converged": bool（True = 最终前件/后件均非 unsat）,
            "initial_findings": 首轮 check_spec_consistency 结果,
            "final_findings": 末轮 check_spec_consistency 结果,
            "history": [{"round": n, "findings": ..., "refined": bool}],
        }
    """
    from src.specs.spec_smt import check_spec_consistency

    cap = max_rounds if max_rounds is not None else _max_refine_rounds()
    initial = check_spec_consistency(spec, signature_params)
    history: list[dict[str, Any]] = [{"round": 0, "findings": initial, "refined": False}]
    result: dict[str, Any] = {
        "spec": spec,
        "rounds": 0,
        "converged": True,
        "initial_findings": initial,
        "final_findings": initial,
        "history": history,
    }

    # 保守早退：开关关 / 无规约 / 无签名 / 无代码 / 无冲突 / 迭代上限 0
    if not spec_refine_enabled():
        return result
    if not spec or not signature_params or not target_code:
        return result
    if not _has_conflict(initial):
        return result
    if cap <= 0:
        result["converged"] = False
        return result

    refine_fn = _llm_refine if _llm_refine is not None else _default_refine_fn(temperature)

    current = spec
    findings = initial
    for round_no in range(1, cap + 1):
        try:
            prompt = _build_refine_prompt(target_code, current, findings)
            raw = refine_fn(prompt)
            from src.utils.helpers import extract_json_object

            refined = extract_json_object(raw)
        except Exception:
            # LLM 调用异常 / 非 JSON 输出 → 保守停止（保留当前 spec，不臆造）
            logger.warning("SpecRefine 第 %d 轮精化失败（保守停止，保留当前规约）", round_no, exc_info=True)
            result["converged"] = False
            break
        if not isinstance(refined, dict):
            result["converged"] = False
            break
        new_spec = _apply_refinement(current, refined)
        new_findings = check_spec_consistency(new_spec, signature_params)
        history.append({"round": round_no, "findings": new_findings, "refined": True})
        current = new_spec
        findings = new_findings
        result["rounds"] = round_no
        result["spec"] = current
        result["final_findings"] = new_findings
        if not _has_conflict(new_findings):
            result["converged"] = True
            break
        result["converged"] = False
    return result


__all__ = [
    "refine_spec_with_counterexample",
    "spec_refine_enabled",
]
