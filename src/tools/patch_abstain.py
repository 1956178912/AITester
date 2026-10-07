"""补丁弃权门（修复引擎批次 V，2026-10-07，ADR-0020——观测层先行）。

背景（验证段对症，引用核验 2026-10-07）：
    - Abstain and Validate（Google，ICSE-SEIP 2026，arXiv:2510.03217）：
      双 LLM 策略——低置信时**弃权**（不产补丁）+ 补丁验证，在 174 个
      人工报告 bug 上合计提升最多 39pp；
    - 本仓 CPR/IDR 首测（批次 II）：IDR = 27.78%（40/144）——72% 的
      plausible-but-wrong 补丁零负信号通过，验证通道缺口定量化。

本模块是弃权门的**判定核**（纯函数、零 LLM、零新增测量）：从既有
观测键推导"该补丁/该通过是否可信"，命中任一信号 → abstain。

信号集（接受时刻的不可信证据，全部为既有 state/结果行键）：
    1. test_regenerated_pass_unverified is True（M5 假通过标记——
       测试重生成后通过且源码未改）；
    2. detection_first_status == "all_green_unverified"（Y1 终态——
       全程全绿未检出，"修复"的缺陷从未被证明存在）；
    3. specificity_gate_verdict == "over_red"（终审过红——验收测试
       对无缺陷代码也失败）；
    4. patch_evidence_level == "none"（补丁与定位证据零重叠背书）；
    5. source_patched_unverified is True（写盘无验证）。

分档纪律（ADR-0020）：
    - 观测层（本批）：结果行透出 patch_abstained / patch_abstain_signals，
      统计层据此计算"弃权调整后 passed 率"——主终点/passed 历史口径
      零变化（AN2 呈现性增补先例）；
    - 阻断档（待 A/B 后转正）：命中即回滚补丁 + 终态 abstained
      （Abstain-and-Validate 语义），转正判据 = 弃权精确率（被压制
      的"成功"中 false_fix 占比）≥ 预注册阈值且不压制 gold 正确补丁。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# 信号集：(键, 期望值)——命中即构成弃权证据。与 CPR/IDR 的负信号
# 口径同源（IDR 另含 rolled_back / red_regression / regression_detected
# 三类"已拦截"信号，弃权门只看"接受时刻仍带病通过"的信号）。
_ABSTAIN_SIGNALS: tuple[tuple[str, Any], ...] = (
    ("test_regenerated_pass_unverified", True),
    ("detection_first_status", "all_green_unverified"),
    ("specificity_gate_verdict", "over_red"),
    ("patch_evidence_level", "none"),
    ("source_patched_unverified", True),
)


def evaluate_patch_abstention(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """弃权判定核（state 与结果行双上下文——键名同构，纯推导）。

    Args:
        record: 工作流 final_state 或批次结果行（Mapping）；None → 不弃权。

    Returns:
        {"abstain": bool, "signals": [str, ...]}——signals 为命中信号
        键名列表（诊断/统计分层用）；record 为 None 时 {"abstain": False,
        "signals": []}（保守：不可评估 = 不弃权，与既有降级口径一致）。
    """
    if not record:
        return {"abstain": False, "signals": []}
    signals = [name for name, expected in _ABSTAIN_SIGNALS if record.get(name) == expected]
    return {"abstain": bool(signals), "signals": signals}


def patch_abstain_signal_names() -> tuple[str, ...]:
    """信号键名清单（测试与文档对齐用，防口径漂移）。"""
    return tuple(name for name, _expected in _ABSTAIN_SIGNALS)
