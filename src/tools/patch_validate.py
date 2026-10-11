"""补丁验证层（修复引擎批次 XVI，2026-10-10，ADR-0020 弃权+验证双策略的"验证"半边）。

背景（独立审查 2026-10-10 落地，引用核验）：
    - Abstain and Validate（Google，ICSE-SEIP 2026，DOI 10.1145/3786583.3786858）：
      双 LLM 策略——**bug 弃权**（低置信不产补丁）+ **补丁验证**（patch critic
      拒绝不太可能是好修复的补丁），在 174 个人工报告 bug 上合计提升最多
      39pp（弃权 +13pp、验证 +15pp、组合 +39pp）；
    - 本仓现状：弃权半边（`patch_abstain.py`，五信号判定核）已落地为观测层，
      但**验证半边缺失**——补丁落盘后没有任何"独立于生成器的验证证据"判定，
      与弃权门互补的"该补丁是否可信"问题无人回答。

本模块是验证层的**判定核**（纯函数、零 LLM、零新增测量），与
`patch_abstain.evaluate_patch_abstention` 对称：

    - 弃权门（abstain）回答"这个 **passed** 是否可信"——命中不可信信号
      → 该"成功"被压制（false_fix / 过红 / 无证据写盘）；
    - 验证层（validate）回答"这个**补丁**是否有独立于生成器的验证证据"——
      命中正面证据 → 该补丁可被独立验证，否则为"未验证补丁"。

    两者组合即 Abstain-and-Validate 的 filtered success rate 口径：
    filtered success = (passed ∧ ¬abstain ∧ validated)。

验证证据信号（正面证据，全部为既有 state/结果行键，零新增测量）：
    1. "gold"       —— state["repo_verification"]["passed"] is True
                       （gold 测试独立裁决通过，最强）；
    2. "deterministic"—— deterministic_repair_status["patch_produced"] is True
                       （确定性修复引擎产出，非 LLM 自由文本，ADR-0019）；
    3. "evidence"   —— patch_evidence_level in ("gold", "sbfl")
                       （已有确定性证据门放行，与 patch_evidence.py 同源）；
    4. "unvalidated" —— 以上均未命中（补丁存在但无独立验证证据）。

分档纪律（对齐 ADR-0020 观测层先行）：
    - 观测层（本批）：结果行透出 patch_validated / patch_validate_verdict，
      统计层据此计算 filtered success rate——主终点/passed 历史口径零变化；
    - 阻断档（待 A/B 后转正）：verdict != "validated" 时回滚补丁 + 终态
      rejected（Abstain-and-Validate 的 patch critic 语义），转正判据 =
      验证精确率（被验证放行的补丁中 correct 占比）≥ 预注册阈值且不误杀
      gold 正确补丁。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# 证据等级强弱序（高 → 低）。用于把"验证证据"分档为可读的 verdict。
# "gold" 最强（gold 测试独立裁决），"deterministic" 次之（确定性引擎），
# "evidence" 最弱（确定性证据门放行），无命中为 "unvalidated"。
_VALIDATION_ORDER: tuple[str, ...] = ("gold", "deterministic", "evidence")


def evaluate_patch_validation(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """补丁验证判定核（state 与结果行双上下文——键名同构，纯推导）。

    与 `patch_abstain.evaluate_patch_abstention` 对称：弃权门看"不可信
    信号"，本核看"正面验证证据"。两者正交——一个补丁可以同时
    "未被弃权"（无不可信信号）且"未被验证"（无正面证据），这正是
    filtered success rate 要收紧的中间地带。

    Args:
        record: 工作流 final_state 或批次结果行（Mapping）；None → 不可评估。

    Returns:
        {
          "validated": bool,          # 是否有独立于生成器的验证证据
          "verdict": str,             # "gold" / "deterministic" / "evidence" /
                                      #   "unvalidated" / "not_applicable"
          "signals": [str, ...],      # 命中的验证证据等级名（诊断分层用）
        }
        record 为 None 时 {"validated": False, "verdict": "not_applicable",
        "signals": []}（保守：不可评估 = 不可验证，与弃权门 None 口径一致）。
    """
    if record is None:
        # 与空 dict 区分：None = 不可评估（not_applicable）；空 dict = 可评估
        # 但无任何验证证据（unvalidated）。两者都保守判 validated=False。
        return {"validated": False, "verdict": "not_applicable", "signals": []}

    # 1. gold：gold 测试独立裁决通过（最强证据）
    repo_ver = record.get("repo_verification")
    if isinstance(repo_ver, dict) and repo_ver.get("passed") is True:
        return {"validated": True, "verdict": "gold", "signals": ["gold"]}

    # 2. deterministic：确定性修复引擎产出（非 LLM 自由文本，ADR-0019）
    det = record.get("deterministic_repair_status")
    if isinstance(det, dict) and det.get("patch_produced") is True:
        return {"validated": True, "verdict": "deterministic", "signals": ["deterministic"]}

    # 3. evidence：确定性证据门放行（gold/sbfl 证据，与 patch_evidence.py 同源）
    ev_level = record.get("patch_evidence_level")
    if ev_level in ("gold", "sbfl"):
        return {"validated": True, "verdict": "evidence", "signals": ["evidence"]}

    # 无正面验证证据
    return {"validated": False, "verdict": "unvalidated", "signals": []}


def patch_validate_verdict_names() -> tuple[str, ...]:
    """verdict 枚举值清单（测试与文档对齐用，防口径漂移）。"""
    return (*_VALIDATION_ORDER, "unvalidated", "not_applicable")


def filtered_success(row: Mapping[str, Any]) -> bool:
    """filtered success 判定（Abstain-and-Validate 口径，纯函数）。

    一个结果行计为 filtered success 当且仅当：
        passed 为 True（原始成功）
        ∧ ¬abstain（弃权门未命中不可信信号）
        ∧ validated（验证层命中正面证据）

    Args:
        row: 批次结果行（须含 passed / patch_abstained / patch_validated 键）。

    Returns:
        True 表示该行在"弃权+验证"双策略下仍计为可信成功。

    与 `experiments/trusted_verification.py` 的 trusted_pass 口径区别：
    trusted_pass = passed ∧ ¬abstain（仅弃权半边）；本函数在此基础上再
    加 validated（验证半边），是 Abstain-and-Validate 的完整 filtered
    success 语义。
    """
    return bool(row.get("passed")) and not bool(row.get("patch_abstained")) and bool(row.get("patch_validated"))
