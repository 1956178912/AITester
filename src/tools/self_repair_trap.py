"""Self-Repair Trap 观测器（修复引擎批次 XIV，ADR-0028）。

背景（外部报告 P1-3 净新增 + DCAware"Self-Repair Trap"风险口径）：
    迭代自修复与执行反馈优化的是"执行成功率"这一代理目标，可能与
    "真正能检出故障的测试"这一真实目标错位——修复循环逐步驱使模型
    生成更容易满足但检测效果更差的断言。本项目对应事实：82% 生成
    测试在 gold fixed 上不全绿（E2 定性，设计保守口径）；假修复通道
    （修正 false_fix 87.2%）与"抹红"通道（红回归门削减 93%）均以
    oracle 退化为前提——退化发生时系统需要一面镜子。

定位（观测层先行，AN2 / ADR-0020 先例）：
    - 数据面：Generator 每次产出测试后落一份质量快照
      （state["oracle_quality_history"]：断言数 / 测试函数数 /
      变异分〔mutation_feedback 可用时〕/ 可解析性）；
    - 判定核：detect_self_repair_trap 纯函数（零 LLM），三信号保守判定；
    - 消费面：结果行 self_repair_trap_suspected / self_repair_trap_signals
      （passed 历史口径零变化，键集合同构）；
    - 刻意不做：阻断 / 策略切换（如强制切 ORACLE_CONTEXT_TIER=minimal
      重生成）——须先有 A/B 数据与预注册判据（ADR-0028"演进方向"）。

信号口径（保守，全部要求最新快照可解析，避免把"写不出测试"误读为
"断言退化"——语法损坏是另一类失败模式，由 test_error_rate 与 O4
通道度量）：
    - assert_count_declining：最新快照可解析、可解析快照 ≥3 且断言数
      最后两段连续下降（DCAware"驱使生成更易满足的断言"的代理信号）；
    - assertion_collapse：最新快照可解析且 0 断言，而历史存在 >0 断言
      （oracle 突然失去检出结构）；
    - mutation_score_declining：≥2 个非 None 变异分且末值 < 首值
      （直接信号；变异分默认稀疏缺失——31/174——缺失不进判定，
      AN2 口径）。
"""

from __future__ import annotations

import ast
from typing import Any


def snapshot_test_quality(
    test_code: str,
    mutation_score: float | None = None,
    regeneration: int = 0,
) -> dict[str, Any]:
    """单次生成测试的质量快照（数据面，零 LLM）。

    Args:
        test_code: 生成测试代码（去重与规约注入之后的最终形态）。
        mutation_score: state["mutation_feedback"]["mutation_score"]
            （ENABLE_MUTATION_SCORING 链路可用时；默认 None 缺失不进判定）。
        regeneration: 快照时的 regeneration_count（0 = 首次生成）。

    Returns:
        {"regeneration": int, "assert_count": int, "test_count": int,
         "parse_ok": bool, "mutation_score": float | None}；
        语法不可解析如实记 parse_ok=False（计数 0/0，判定核据此豁免）。
    """
    assert_count = 0
    test_count = 0
    tree: ast.Module | None = None
    try:
        tree = ast.parse(test_code or "")
    except SyntaxError:
        tree = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                assert_count += 1
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                node.name.startswith("test_") or node.name.endswith("_test")
            ):
                test_count += 1
    return {
        "regeneration": int(regeneration),
        "assert_count": assert_count,
        "test_count": test_count,
        "parse_ok": tree is not None,
        "mutation_score": mutation_score,
    }


def detect_self_repair_trap(history: list[dict[str, Any]] | None) -> dict[str, Any]:
    """Self-Repair Trap 判定核（纯函数零 LLM；三信号保守判定）。

    Args:
        history: state["oracle_quality_history"] 快照序列（按生成顺序）。

    Returns:
        {"suspected": bool, "signals": [str, ...]}；history 为 None/空 /
        快照不足时 {"suspected": False, "signals": []}（保守不怀疑，
        与 test-hacking / 弃权门降级口径一致）。
    """
    empty: dict[str, Any] = {"suspected": False, "signals": []}
    if not history:
        return empty
    points = [h for h in history if isinstance(h, dict)]
    if not points:
        return empty
    signals: list[str] = []
    # 最新快照可解析才评估"最新测试是否退化"——最新不可解析说明本轮
    # 写出的是语法损坏测试（另一类失败），不冒充断言退化信号。
    if points[-1].get("parse_ok") is True:
        parsed = [h for h in points if h.get("parse_ok") is True]
        counts = [int(h.get("assert_count") or 0) for h in parsed]
        if len(counts) >= 3 and counts[-2] < counts[-3] and counts[-1] < counts[-2]:
            signals.append("assert_count_declining")
        if len(counts) >= 2 and counts[-1] == 0 and any(c > 0 for c in counts[:-1]):
            signals.append("assertion_collapse")
    scores = [
        float(h["mutation_score"])
        for h in points
        if isinstance(h.get("mutation_score"), (int, float)) and not isinstance(h.get("mutation_score"), bool)
    ]
    if len(scores) >= 2 and scores[-1] < scores[0]:
        signals.append("mutation_score_declining")
    return {"suspected": bool(signals), "signals": signals}
