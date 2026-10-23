"""BX 轮（2026-10-23）：写而不读键池最后两键（`risk_summary` / `mdo_crash_rate`）的读侧口径。

背景：
    BU 普查量出 13 键 / 76,488 行的「只写不读」池；BV 收掉两份判定核、BW 收掉
    补丁接收链四条，池内只剩两键：`risk_summary`（8,864 行）与 `mdo_crash_rate`
    （4,044 行）。两键都没有报告面读者，且各自的**输入域与分母**在行里以三种
    方式被折叠：

    `risk_summary`
        - 全归档 8,864 行 `enabled=False`：`risk_level` / `approval_action` /
          `risk_score` 全为 `None`、`factors={}`、`reasons=[]`。这是**通道没开**的
          占位，与「开启了且判低风险」在任何按字段读取的消费者眼里同形；
          `pause_requested=False` 同理是「没请求暂停」，不是「判定无需暂停」。
        - 2,333 行键缺席（早于该键落盘）——缺席 ≠ 低风险。
        - 两种历史形状（7 键带 `pause_requested` / 6 键不带）；`contract_status`
          （BL 起落盘）在归档里 0 行在场，因此「缺失符号为空可不可信」在归档上
          **没有可读证据**。

    `mdo_crash_rate`
        - 五层输入域，缺一层就会把不同事实读成同一个 `None`：
          `not_run`（腿没跑）/ `material_absent`（写侧材料早退，`mdo_available`
          仍是 `None`，只有 `reason` 说明）/ `not_measurable`（`available=False`
          带原因）/ `provisional_pool`（池未达下限，规范键被 T6 出口拦成
          `None`、原始值在 `mdo_raw`）/ `measured`（规范值可读）。
        - `mdo_pool_floor_ok=False` 是**两义键**：暂定池行（530）与不可测行
          （986，`MDOResult` 默认值）同值。按该键筛「池不足」会多算 986 行。
        - crash 率的分母是**全池 n**（`src/measurement/mdo.py` 的 CRASH 行），
          与 MTR/MDR 的**可评估**分母不同；四个可评估计数
          （`mdo_status` / `mdo_evaluable` / `mdo_non_terminating` /
          `mdo_probe_invalid` / `mdo_no_effective_pass`）被写入端逐键白名单
          丢弃，归档 0 行在场 ⇒ 可评估分母**无法从归档复算**。
        - `None`（未测 / 池不足被拦）不是 0；`0.0` 是实测零崩溃。
        - 规范值已四舍五入到 4 位；分子可由 `round(c/n,4)==rate` 在 `0..n`
          内反推（归档 94/94、530/530 唯一）。池化率因此以**整数分子 / 全池
          分母**给出，与「逐行均值」（每行等权）是两个口径。

外部口径：
    - crash 率必须带分母：Google Play `vitals.crashrate` 的 `crashRate` 以
      「去重用户数」归一化，并明确禁止再聚合该计数（同一用户在汇总期只算一次）；
      同一分子换分母（per-session vs per-request）会得到不同读数。
    - 风险级别是序数/半定量分箱映射出的定性标签（NIST SP 800-30），不是概率；
      没有 `enabled=True` 的行就没有任何可读级别。

本轮只做读侧分档与对账：不改写入端、不改任何行的值与方向、不改任何判定核。
"""

from __future__ import annotations

import statistics
from typing import Any

RISK_KEY = "risk_summary"
CRASH_KEY = "mdo_crash_rate"

#: `enabled=False` 占位必须同时满足的空值形状（任一不空即写侧缺陷信号）。
RISK_PLACEHOLDER_FIELDS = ("risk_level", "approval_action", "risk_score")
RISK_PAUSE_KEY = "pause_requested"
RISK_CONTRACT_STATUS_KEY = "contract_status"

#: 五层输入域（顺序即报告顺序：从未跑到可读值）。
CRASH_NOT_RUN = "not_run"
CRASH_MATERIAL_ABSENT = "material_absent"
CRASH_NOT_MEASURABLE = "not_measurable"
CRASH_PROVISIONAL = "provisional_pool"
CRASH_MEASURED = "measured"
CRASH_LAYERS = (CRASH_NOT_RUN, CRASH_MATERIAL_ABSENT, CRASH_NOT_MEASURABLE, CRASH_PROVISIONAL, CRASH_MEASURED)
#: 「这条腿没给出规范值」的三层（报告里合并成一列前先看原因）。
CRASH_UNMEASURED_LAYERS = (CRASH_NOT_RUN, CRASH_MATERIAL_ABSENT, CRASH_NOT_MEASURABLE)

#: `MDOResult.as_dict` 产出、但 `run_benchmark` 写入端白名单未复制的可评估计数。
MDO_EVALUABILITY_KEYS = (
    "mdo_status",
    "mdo_evaluable",
    "mdo_non_terminating",
    "mdo_probe_invalid",
    "mdo_no_effective_pass",
)


def crash_layer(row: dict[str, Any]) -> str | None:
    """单行 crash 率的输入可达域层级；键缺席（早于 MDO）返回 None。"""
    if CRASH_KEY not in row:
        return None
    available = row.get("mdo_available")
    if available is True:
        return CRASH_PROVISIONAL if row.get("mdo_provisional") is True else CRASH_MEASURED
    if available is False:
        return CRASH_NOT_MEASURABLE
    # `available is None` 有两义：写侧材料早退会留下 reason，腿没跑则连 reason 都没有。
    reason = row.get("mdo_not_available_reason")
    if isinstance(reason, str) and reason.strip():
        return CRASH_MATERIAL_ABSENT
    return CRASH_NOT_RUN


def _value_summary(values: list[float]) -> dict[str, Any]:
    """数值列摘要；空列返回全 None（不是 0）。"""
    if not values:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 6),
        "median": round(statistics.median(values), 6),
        "min": min(values),
        "max": max(values),
    }


def _reconstruct_count(rate: float | None, pool_size: Any) -> list[int] | None:
    """由 `round(c/n,4)==rate` 反推整数分子；输入不完整返回 None。

    返回候选列表（调用方要求长度为 1 才计入池化）——四舍五入可能让两个分子
    落在同一个 4 位读数上，此时不做假设。
    """
    if (
        isinstance(pool_size, bool)
        or not isinstance(pool_size, int)
        or pool_size <= 0
        or isinstance(rate, bool)
        or not isinstance(rate, (int, float))
    ):
        return None
    return [c for c in range(pool_size + 1) if round(c / pool_size, 4) == rate]


def _pooled(
    items: list[tuple[float | None, Any]],
) -> dict[str, Any]:
    """把 (rate, pool_size) 反推成整数分子后池化；歧义/缺料单列，不猜。"""
    crash = pool = 0
    unique = ambiguous = failed = 0
    for rate, size in items:
        cands = _reconstruct_count(rate, size)
        if cands is None:
            failed += 1
            continue
        if len(cands) != 1:
            ambiguous += 1
            continue
        unique += 1
        crash += cands[0]
        pool += int(size)
    return {
        "n_unique": unique,
        "n_ambiguous": ambiguous,
        "n_failed": failed,
        "n_crash": crash,
        "n_pool": pool,
        "rate": (crash / pool) if pool else None,
    }


def risk_summary_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """`risk_summary` 的读侧分档（只统计，不改任何判定）。"""
    present = [r for r in rows if RISK_KEY in r]
    docs = [r[RISK_KEY] for r in present if isinstance(r[RISK_KEY], dict)]
    shape = {"enabled_true": 0, "enabled_false": 0, "enabled_missing": 0}
    level: dict[str, int] = {}
    action: dict[str, int] = {}
    scores: list[float] = []
    enabled_unscored = 0
    placeholder_mismatch = 0
    pause = {"true": 0, "false": 0, "absent": 0, "other": 0}
    contract_status = {"present": 0, "absent": 0}
    for doc in docs:
        flag = doc.get("enabled")
        if flag is True:
            shape["enabled_true"] += 1
            lv = doc.get("risk_level")
            level[str(lv)] = level.get(str(lv), 0) + 1
            action[str(doc.get("approval_action"))] = action.get(str(doc.get("approval_action")), 0) + 1
            if isinstance(doc.get("risk_score"), (int, float)):
                scores.append(float(doc["risk_score"]))
            if lv is None:
                enabled_unscored += 1
        elif flag is False:
            shape["enabled_false"] += 1
            if any(doc.get(k) is not None for k in RISK_PLACEHOLDER_FIELDS) or doc.get("factors") or doc.get("reasons"):
                placeholder_mismatch += 1
        else:
            shape["enabled_missing"] += 1
        if RISK_PAUSE_KEY not in doc:
            pause["absent"] += 1
        elif doc[RISK_PAUSE_KEY] is True:
            pause["true"] += 1
        elif doc[RISK_PAUSE_KEY] is False:
            pause["false"] += 1
        else:
            # 键在场但不是布尔（写侧异常）——单列，不折叠进 false（BW 字符串布尔纪律）。
            pause["other"] += 1
        if RISK_CONTRACT_STATUS_KEY in doc:
            contract_status["present"] += 1
        else:
            contract_status["absent"] += 1
    # 只有 enabled=True 的行才有可读级别；enabled=False 行即使残留 level 值也只是
    # 写侧缺陷（已由 placeholder_mismatch 单列），不得计成「级别可读」。
    levels_nonnull = sum(1 for doc in docs if doc.get("enabled") is True and doc.get("risk_level") is not None)
    # 键级形状：报告要能说清「这条归档里根本没有 contract_status」。
    schemas: dict[str, int] = {}
    for doc in docs:
        key = "|".join(sorted(doc))
        schemas[key] = schemas.get(key, 0) + 1
    return {
        "n_rows": len(rows),
        "n_key_present": len(present),
        "n_key_absent": len(rows) - len(present),
        "n_non_dict": len(present) - len(docs),
        "enabled": shape,
        "schema_shapes": schemas,
        "level": level,
        "level_nonnull": levels_nonnull,
        "action": action,
        "score": _value_summary(scores),
        "n_enabled_unscored": enabled_unscored,
        "placeholder_mismatch": placeholder_mismatch,
        "pause": pause,
        "contract_status": contract_status,
        # 报告可直接引用的读法：有 enabled=True 的行才有级别可读。
        "distribution_readable": shape["enabled_true"] > 0,
    }


def mdo_crash_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """`mdo_crash_rate` 的五层输入域、值域与分母口径（只统计）。"""
    present = [r for r in rows if CRASH_KEY in r]
    layers = {layer: 0 for layer in CRASH_LAYERS}
    reasons: dict[str, int] = {}
    for row in present:
        layer = crash_layer(row)
        assert layer is not None  # 键在场，crash_layer 必返回层级
        layers[layer] += 1
        if layer in CRASH_UNMEASURED_LAYERS:
            reason = row.get("mdo_not_available_reason")
            key = str(reason) if isinstance(reason, str) and reason.strip() else "<none>"
            reasons[key] = reasons.get(key, 0) + 1

    measured = [r for r in present if crash_layer(r) == CRASH_MEASURED]
    values = [float(r[CRASH_KEY]) for r in measured if isinstance(r[CRASH_KEY], (int, float))]
    provisional = [r for r in present if crash_layer(r) == CRASH_PROVISIONAL]
    raw_values = [
        float(r["mdo_raw"]["crash_rate"])
        for r in provisional
        if isinstance(r.get("mdo_raw"), dict) and isinstance(r["mdo_raw"].get("crash_rate"), (int, float))
    ]
    raw_pools = [
        r.get("mdo_pool_size")
        for r in provisional
        if isinstance(r.get("mdo_raw"), dict) and isinstance(r["mdo_raw"].get("crash_rate"), (int, float))
    ]
    measured_pools = [r.get("mdo_pool_size") for r in measured if isinstance(r[CRASH_KEY], (int, float))]

    floor_false = sum(1 for r in present if r.get("mdo_pool_floor_ok") is False)
    floor_false_provisional = sum(
        1 for r in present if r.get("mdo_pool_floor_ok") is False and r.get("mdo_provisional") is True
    )
    return {
        "n_rows": len(rows),
        "n_key_present": len(present),
        "n_key_absent": len(rows) - len(present),
        "layers": layers,
        "unmeasured_reasons": reasons,
        "n_value_nonnull": len(values),
        "n_value_null": len(present) - len(values),
        "value": _value_summary(values),
        "n_zero": sum(1 for v in values if v == 0),
        "n_nonzero": sum(1 for v in values if v != 0),
        "pooled": _pooled(list(zip(values, measured_pools, strict=True))),
        "provisional_raw": {
            "n_present": len(raw_values),
            "n_missing": len(provisional) - len(raw_values),
            "value": _value_summary(raw_values),
            "n_zero": sum(1 for v in raw_values if v == 0),
            "n_nonzero": sum(1 for v in raw_values if v != 0),
            "pooled": _pooled(list(zip(raw_values, raw_pools, strict=True))),
        },
        # `mdo_pool_floor_ok=False` 的两义：默认值（不可测）vs 池不足。
        "floor_false": floor_false,
        "floor_false_provisional": floor_false_provisional,
        "floor_false_other": floor_false - floor_false_provisional,
        "provisional_flag_missing": sum(1 for r in present if r.get("mdo_provisional") is None),
        # 可评估计数是否落盘（0 = 分母构成不可从归档复算）。
        "n_evaluability_recorded": sum(1 for r in present if any(k in r for k in MDO_EVALUABILITY_KEYS)),
        "evaluability_keys": list(MDO_EVALUABILITY_KEYS),
    }


def residual_keys_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """两键合并读数（报告面与批次摘要共用）。"""
    return {
        "n_rows": len(rows),
        "risk_summary": risk_summary_stats(rows),
        "mdo_crash": mdo_crash_stats(rows),
    }
