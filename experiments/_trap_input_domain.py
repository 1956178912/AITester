"""Self-Repair Trap 判定核**输入可达域**的单一事实源（BU 轮，2026-10-22）。

背景：`self_repair_trap_suspected` / `self_repair_trap_signals` 自批次 XIV（ADR-0028）
写入结果行，但全树只有写入点、没有任何读者（BU 普查：13 个只写不读键之一）。归档里
5935 行判定恒为 `False`、信号恒为空——"恒不怀疑"里混着输入不足、输入形状不符、
输入够且判干净三种完全不同的事实，而 `src/tools/self_repair_trap.detect_self_repair_trap`
的三个信号各有自己的最少点数门槛，报告面从不披露这些门槛落在哪里。

本模块只做**读侧分档**，不改判定核、不改任何行的值：
- `SIGNAL_MIN_POINTS` 必须与判定核里的字面比较逐项对齐（AST 结构锁盯这条）；
- 分档回答"这行的输入够不够判定核去看"，不回答"判定结果是什么"。
"""

from __future__ import annotations

from typing import Any

#: 结果行里承载判定与输入的两个键（缺判定键 = 批次早于 ADR-0028，不是"干净"）。
TRAP_VERDICT_KEY = "self_repair_trap_suspected"
TRAP_SIGNALS_KEY = "self_repair_trap_signals"
TRAP_HISTORY_KEY = "oracle_quality_history"

#: 三个信号各自的最少输入点数，与 `detect_self_repair_trap` 的字面比较一致：
#: `assert_count_declining` 需 ≥3 个可解析断言计数、`assertion_collapse` 需 ≥2 个、
#: `mutation_score_declining` 需 ≥2 个非 None 分数。改判定核门槛必须同步改这里。
SIGNAL_MIN_POINTS: dict[str, int] = {
    "assert_count_declining": 3,
    "assertion_collapse": 2,
    "mutation_score_declining": 2,
}

#: 输入形态四档（互斥且求和 = 该臂结果行总数）。
BUCKET_NOT_RECORDED = "not_recorded"
BUCKET_MALFORMED = "history_malformed"
BUCKET_BELOW_FLOOR = "below_min_floor"
BUCKET_FLOOR_REACHED = "min_floor_reached"

#: 进入任一信号可达域所需的全局最低门槛（= 各信号门槛的最小值）。
GLOBAL_MIN_POINTS = min(SIGNAL_MIN_POINTS.values())


def _points(history: object) -> list[dict[str, Any]]:
    if not isinstance(history, list):
        return []
    return [h for h in history if isinstance(h, dict)]


def assert_counts(history: object) -> list[int]:
    """判定核口径的断言计数序列：末点不可解析时返回空（不冒充退化）。"""
    points = _points(history)
    if not points or points[-1].get("parse_ok") is not True:
        return []
    return [int(h.get("assert_count") or 0) for h in points if h.get("parse_ok") is True]


def mutation_scores(history: object) -> list[float]:
    """判定核口径的变异分数序列：`None` 与非数值不进序列，布尔不算数值。"""
    scores: list[float] = []
    for h in _points(history):
        v = h.get("mutation_score")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            scores.append(float(v))
    return scores


def signal_domains(history: object) -> dict[str, bool]:
    """该行输入落在哪些信号的可达域内（输入够不够，不是判没判出来）。"""
    counts = assert_counts(history)
    scores = mutation_scores(history)
    return {
        "assert_count_declining": len(counts) >= SIGNAL_MIN_POINTS["assert_count_declining"],
        "assertion_collapse": len(counts) >= SIGNAL_MIN_POINTS["assertion_collapse"],
        "mutation_score_declining": len(scores) >= SIGNAL_MIN_POINTS["mutation_score_declining"],
    }


def input_bucket(row: dict[str, object]) -> str:
    """按输入形态给单行分档；缺判定键的行不进输入档（读作未记录）。"""
    if not isinstance(row, dict) or TRAP_VERDICT_KEY not in row:
        return BUCKET_NOT_RECORDED
    history = row.get(TRAP_HISTORY_KEY)
    if not isinstance(history, list):
        return BUCKET_MALFORMED
    if len(history) < GLOBAL_MIN_POINTS:
        return BUCKET_BELOW_FLOOR
    return BUCKET_FLOOR_REACHED


def two_point_decline_outside_domain(row: dict[str, object]) -> bool:
    """两点连续下降但点数不足 `assert_count_declining` 门槛——证据存在、判据进不去。"""
    if input_bucket(row) != BUCKET_FLOOR_REACHED:
        return False
    counts = assert_counts(row.get(TRAP_HISTORY_KEY))
    return 2 <= len(counts) < SIGNAL_MIN_POINTS["assert_count_declining"] and counts[-1] < counts[-2]
