"""df_spec 臂（检出优先 + 规格锚）QuixBugs 双臂实验分析（预注册件，2026-10-16）。

零 LLM：读 2 臂批次 JSON（plain_llm_df_spec / plain_llm_df），产出：
- 主对比：df_spec vs df 配对 McNemar（精确；单向 H1: df_spec > df）+ BF10 + MDE；
- 绝对线核对：df_spec detection（41 缺陷程序口径）vs 60% 成功线 / 50% 失败线；
- 审计面：spec_replace_applied 命中统计（锚覆盖分母）、特异性门 verdict 分布；
- 判定：confirmed / trend / not_confirmed（预注册 §3 一并复算双侧精确 p 供报告）。

预注册：docs/emse/EMSE_DF_SPEC_PREREG_2026-10-16.md（本地件）；判据常量与
§3 表逐项对齐，改动须同步预注册（脚本内含一致性注释锚）。

用法：
    python -m experiments.emse_df_spec_analysis --dfspec <A.json> --df <B.json>
        [--dfspec-arm plain_llm_df_spec --df-arm plain_llm_df] [--out report.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.emse_quixbugs_specir_expand import (  # noqa: E402
    bayes_factor_10,
    mcnemar_exact_p,
    mde_two_proportion,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# ─── 预注册常量（EMSE_DF_SPEC_PREREG_2026-10-16.md §3；改此表必须同步预注册）──
SUCCESS_LINE = 0.60  # C1：df_spec detection ≥ 60%（41 口径可判定子集）
FAIL_LINE = 0.50  # 失败线：detection < 50%
CONFIRM_P = 0.05  # C2：单向 H1（df_spec > df）精确 p < 0.05
TREND_P = 0.10  # trend：p < 0.10 ∧ δ > 0
OVER_RED_DROP_TARGET = 0.30  # 机制侧描述性信号：over_red 占比降幅 ≥30%


class MissingArtifactError(Exception):
    """臂 JSON 工件缺失或结构不完整。"""


# ─── 加载 ───────────────────────────────────────────────────────────────
def load_arm_rows(path: Path, arm_key: str | None = None) -> dict[str, dict[str, Any]]:
    """从批次 JSON 提取 task_id → 行摘要映射。

    arm_key=None 时自动选择**唯一**含非空 details 的臂；多臂且未显式
    指定时报错（防错配——预注册要求显式声明臂名）。

    行集折叠口径（AB-12d）：``out[tid] = ...`` 让**后出现的同 task_id 行覆盖前一行**，
    返回字典因此可以比 ``details`` 行数少，而下游的 41 缺陷程序口径、可判定子集与配对
    检验都按这个字典算——分母就这样静默缩掉。本轮把折叠改成一条命名 WARN：点名文件、
    臂、``details 行数 / 行摘要数 / 被覆盖行数``与被覆盖的 task_id，并把"无主键行"按
    形态分开计（键缺席 / 值为 null / 空串 / 非字符串 / 不可哈希；五桶互斥，一行只进一桶，
    否则披露自身的计数就会虚增）。真批次实测 0 实例——覆盖面按桶记账：glob 命中 246 份
    ``benchmark_*.json``，其中 242 份（320 个臂、10659 个 dict 行）真正提供了证据，另
    4 份是 2 份空 ``details`` 例与 2 份 ``.mdo.json`` 非臂形状，只点名承认、不计入分子也
    不计入"干净"（见 ``tests/test_experiments_arm_row_collapse_ab12.py`` 的分桶等式）。
    故入库读数一字不变；有实例时也不得再被读成"该臂只有 N 个任务"。
    """
    if not path.exists():
        raise MissingArtifactError(f"工件缺失: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise MissingArtifactError(f"工件 JSON 损坏: {path}（{e}）") from e
    results = data.get("results", {})
    if arm_key is None:
        candidates = [
            k for k, v in results.items() if isinstance(v, dict) and isinstance(v.get("details"), list) and v["details"]
        ]
        if len(candidates) != 1:
            raise MissingArtifactError(f"工件含 {len(candidates)} 个有效臂{tuple(candidates)}，需显式指定 arm_key")
        arm_key = candidates[0]
    arm = results.get(arm_key)
    if not isinstance(arm, dict) or not isinstance(arm.get("details"), list):
        raise MissingArtifactError(f"臂 {arm_key!r} 缺失或 details 非 list: {path}")
    out: dict[str, dict[str, Any]] = {}
    details = arm["details"]
    overwritten: list[Any] = []
    keyless = {"key_absent": 0, "value_null": 0, "empty_string": 0, "not_string": 0, "unhashable": 0}
    non_object_detail_rows = 0
    for row in details:
        if not isinstance(row, dict):
            non_object_detail_rows += 1
            continue
        tid = row.get("task_id", "")
        if "task_id" not in row:
            keyless["key_absent"] += 1
        elif tid is None:
            keyless["value_null"] += 1
        elif isinstance(tid, str) and not tid.strip():
            keyless["empty_string"] += 1
        elif not isinstance(tid, str):
            try:
                hash(tid)
            except TypeError:
                keyless["unhashable"] += 1
                continue
            keyless["not_string"] += 1
        if tid in out:
            overwritten.append(tid)
        out[tid] = {
            "detection_rate": row.get("detection_rate"),
            "spec_replace_applied": row.get("spec_replace_applied"),
            "specificity_gate_verdict": row.get("specificity_gate_verdict"),
            "red_regression_violation": row.get("red_regression_violation"),
        }
    segments: list[str] = []
    if overwritten:
        shown = "、".join(repr(t) for t in overwritten[:10])
        more = f"（只点名前 {min(10, len(overwritten))} 个）" if len(overwritten) > 10 else ""
        segments.append(f"被覆盖 task_id {len(overwritten)} 个：{shown}{more}")
    if any(keyless.values()):
        segments.append("无主键行 " + "、".join(f"{k} {v}" for k, v in keyless.items() if v))
    if non_object_detail_rows:
        segments.append(f"非对象详情行 {non_object_detail_rows}")
    if segments:
        print(
            f"[WARN] {path.name}：臂 {arm_key!r} 行集折叠 details 行 {len(details)} → 行摘要 {len(out)}"
            f"（{'；'.join(segments)}）——后出现的同 id 行会覆盖前一行，"
            "41 缺陷程序口径与配对检验的分母随之缩水，不得读成'该臂只有 N 个任务'",
            file=sys.stderr,
        )
    return out


def defect_program_ids(rows: dict[str, dict[str, Any]]) -> set[str]:
    """41 缺陷程序口径：task_id 不以 `_test` 结尾（9 个测试驱动单列除外）。"""
    return {tid for tid in rows if not tid.endswith("_test")}


# ─── 统计 ───────────────────────────────────────────────────────────────
def detection_summary(rows: dict[str, dict[str, Any]], subset: set[str] | None = None) -> dict[str, Any]:
    """可判定子集（detection 非 None）的检出统计。

    Args:
        rows: task_id → 行摘要。
        subset: 限定口径（如 41 缺陷程序）；None=全量。
    """
    ids = set(rows) if subset is None else (set(rows) & set(subset))
    measurable = [tid for tid in ids if rows[tid]["detection_rate"] is not None]
    positive = [tid for tid in measurable if rows[tid]["detection_rate"] == 1]
    rate = len(positive) / len(measurable) if measurable else None
    return {
        "denominator_rows": len(ids),
        "measurable": len(measurable),
        "positive": len(positive),
        "rate": round(rate, 4) if rate is not None else None,
    }


def effective_pair(
    a: dict[str, dict[str, Any]],
    b: dict[str, dict[str, Any]],
    subset: set[str] | None = None,
) -> tuple[int, int, int]:
    """有效配对子集（双方 detection 非 None）：(a_pos_only, b_pos_only, n_pairs)。

    a_pos_only = 仅 a 检出（a=1,b=0；df_spec 唯一检出）；b_pos_only 对称。
    """
    ids = set(a) & set(b)
    if subset is not None:
        ids &= set(subset)
    a_pos = 0
    b_pos = 0
    n_pairs = 0
    for tid in ids:
        da = a[tid]["detection_rate"]
        db = b[tid]["detection_rate"]
        if da is None or db is None:
            continue
        n_pairs += 1
        a1, b1 = int(da == 1.0), int(db == 1.0)
        if a1 and not b1:
            a_pos += 1
        elif b1 and not a1:
            b_pos += 1
    return a_pos, b_pos, n_pairs


def one_sided_p(a_pos: int, b_pos: int) -> float:
    """单向精确 p（H1: a > b）：P(X ≥ a_pos | n=a_pos+b_pos, p0=0.5)。

    方向不符（a_pos ≤ b_pos 且 n>0）时该尾概率 ≥0.5，如实返回
    （判定层据此必然不显著）；n=0 返回 1.0。
    """
    n = a_pos + b_pos
    if n == 0:
        return 1.0
    from math import comb

    tail = sum(comb(n, i) for i in range(a_pos, n + 1)) * (0.5**n)
    return min(1.0, tail)


def domain_stats(rows: dict[str, dict[str, Any]], key: str, subset: set[str] | None = None) -> dict[str, int]:
    """取值域分布（None 单列 'none' 桶；用于 spec_replace_applied / verdict）。"""
    ids = set(rows) if subset is None else (set(rows) & set(subset))
    out: dict[str, int] = {}
    for tid in ids:
        v = rows[tid].get(key)
        bucket = "none" if v is None else str(v)
        out[bucket] = out.get(bucket, 0) + 1
    return dict(sorted(out.items()))


def contrast(
    a: dict[str, dict[str, Any]],
    b: dict[str, dict[str, Any]],
    subset: set[str] | None = None,
) -> dict[str, Any]:
    """df_spec(a) vs df(b) 配对对比（标准口径：双方非 None）。"""
    a_pos, b_pos, n_pairs = effective_pair(a, b, subset)
    delta_pp = (a_pos - b_pos) / n_pairs * 100 if n_pairs else 0.0
    return {
        "n_pairs": n_pairs,
        "a_only": a_pos,
        "b_only": b_pos,
        "ratio": f"{a_pos}:{b_pos}",
        "delta_pp": round(delta_pp, 2),
        "p_two_sided": round(mcnemar_exact_p(a_pos, b_pos), 4),
        "p_one_sided": round(one_sided_p(a_pos, b_pos), 4),
        "bf10": round(bayes_factor_10(a_pos, b_pos), 4),
        "mde_pp": mde_two_proportion(n_pairs),
    }


# ─── 判定（预注册 §3 三态 + 绝对线/失败线）───────────────────────────────
def decide(c: dict[str, Any], df_spec_rate: float | None) -> dict[str, Any]:
    """按预注册规则判定。

    - confirmed：rate ≥ 0.60 ∧ 单向 p < 0.05；
    - trend：单向 p < 0.10 ∧ δ > 0（方向为正、未达显著性）；
    - not_confirmed：其余；
    - fail_line_triggered：rate < 0.50（独立标记，与三态并列报告）。
    """
    p1 = c["p_one_sided"]
    delta = c["delta_pp"]
    if df_spec_rate is None:
        verdict = "not_confirmed"
        confirmed = trend = False
    else:
        confirmed = df_spec_rate >= SUCCESS_LINE and p1 < CONFIRM_P
        trend = (not confirmed) and p1 < TREND_P and delta > 0
        verdict = "confirmed" if confirmed else ("trend" if trend else "not_confirmed")
    return {
        "verdict": verdict,
        "conditions": {
            "absolute_line": {
                "threshold": SUCCESS_LINE,
                "rate": df_spec_rate,
                "met": None if df_spec_rate is None else df_spec_rate >= SUCCESS_LINE,
            },
            "one_sided_p_lt_0.05": p1 < CONFIRM_P,
            "direction_positive": delta > 0,
        },
        "fail_line_triggered": None if df_spec_rate is None else df_spec_rate < FAIL_LINE,
    }


def build_analysis(dfspec_path: Path, df_path: Path, dfspec_arm: str | None, df_arm: str | None) -> dict[str, Any]:
    """完整分析：加载 → 41 口径主判定 + 全量口径补充 + 审计面。"""
    a = load_arm_rows(dfspec_path, dfspec_arm)
    b = load_arm_rows(df_path, df_arm)
    main41 = defect_program_ids(a) & defect_program_ids(b)

    det_a_41 = detection_summary(a, main41)
    det_b_41 = detection_summary(b, main41)
    c_41 = contrast(a, b, main41)
    c_all = contrast(a, b, None)

    over_red_a = domain_stats(a, "specificity_gate_verdict", main41)
    over_red_b = domain_stats(b, "specificity_gate_verdict", main41)

    def _over_red_share(dist: dict[str, int]) -> float | None:
        sr, orr = dist.get("specific_red", 0), dist.get("over_red", 0)
        return round(orr / (sr + orr), 4) if (sr + orr) else None

    share_a, share_b = _over_red_share(over_red_a), _over_red_share(over_red_b)
    drop = None
    if share_a is not None and share_b is not None and share_b > 0:
        drop = round((share_b - share_a) / share_b, 4)

    return {
        "inputs": {"dfspec": str(dfspec_path), "df": str(df_path)},
        "caliber": "QuixBugs 41 缺陷程序（非 _test 后缀）；可判定子集（detection 非 None）",
        "df_spec": {"detection_41": det_a_41},
        "df": {"detection_41": det_b_41},
        "contrast_41": c_41,
        "contrast_all": c_all,
        "decision": decide(c_41, det_a_41["rate"]),
        "audit": {
            "spec_replace_applied_dfspec": domain_stats(a, "spec_replace_applied", None),
            "spec_replace_applied_df": domain_stats(b, "spec_replace_applied", None),
            "verdict_dfspec_41": over_red_a,
            "verdict_df_41": over_red_b,
            "over_red_share_dfspec": share_a,
            "over_red_share_df": share_b,
            "over_red_drop_ratio": drop,
            "over_red_drop_target": OVER_RED_DROP_TARGET,
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dfspec", required=True, help="df_spec 臂批次 JSON")
    ap.add_argument("--df", required=True, help="df 对照臂批次 JSON")
    ap.add_argument("--dfspec-arm", default="plain_llm_df_spec", help="df_spec 臂键名（默认 plain_llm_df_spec）")
    ap.add_argument("--df-arm", default="plain_llm_df", help="df 臂键名（默认 plain_llm_df）")
    ap.add_argument("--out", default=None, help="结果落盘路径（JSON）")
    args = ap.parse_args(argv)

    # 单臂批次（每文件仅一臂）时 arm_key 自动；双键冲突由 load_arm_rows 报错防错配
    try:
        result = build_analysis(Path(args.dfspec), Path(args.df), args.dfspec_arm, args.df_arm)
    except MissingArtifactError as e:
        print(f"[emse_df_spec_analysis] ✗ {e}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        atomic_write_json(Path(args.out), result)
        print(f"[emse_df_spec_analysis] 已落盘：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
