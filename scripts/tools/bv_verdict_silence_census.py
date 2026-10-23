#!/usr/bin/env python3
"""BV 轮（2026-10-23）只读普查：两份判定核的沉默分档 + 键池复核。

背景：BU 轮把「只写不读」键池点清（13 键 / 76488 行），并收口了 Self-Repair
Trap 两键。BV 收口池里的下两项判定族——批次 VIII 的 test-hacking 判定核
（`test_hacking_suspected` / `_signals`）与批次 XIV 的 FL 约束门
（`fl_constraint_verdict` / `_hit_rank` / `_changed_functions`）。本探针把
「沉默」量清楚：hack 侧四档（已求值 / 没看 / 状态未记录 / 判定未记录），
FL 侧判定值 × 成因来源（记录 / 推断下界）。

三段（全部只读；仓库零写入、零 LLM）：
    A 段  全归档跑 `detector_silence_stats`：hack 四档 + 信号分布 + True 行点名，
          FL 判定值 / 成因来源 / hit 比 / 变更函数分档 / 恒等式。
    B 段  键池复核：跑 BU 的普查器，确认这两族接入读端后池子应剩 9 键 / 34943 行。
    C 段  具名批次核对：与 `tests/test_verdict_silence_bv.py` 的 PINNED_BATCHES 对照。

用法：.venv/bin/python scripts/tools/bv_verdict_silence_census.py [--segment a|b|c|all]
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _archive_rows() -> tuple[list[dict], int]:
    """全归档结果行（只收批次形状的文件：`results` 必须是 dict）。"""
    rows: list[dict] = []
    batches = 0
    for path in sorted((ROOT / "experiments" / "results").rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not (isinstance(doc, dict) and isinstance(doc.get("results"), dict)):
            continue
        batches += 1
        for block in doc["results"].values():
            rows.extend(r for r in (block or {}).get("details") or [] if isinstance(r, dict))
    return rows, batches


def print_archive() -> None:
    from experiments.statistical_analysis import detector_silence_stats

    rows, batches = _archive_rows()
    out = detector_silence_stats(rows)
    hack, fl = out["hack"], out["fl"]
    print(f"=== A 段：全归档判定核沉默分档（批次 {batches} / 行 {out['n_rows']}）===")
    print(
        f"hack: 有判定 {hack['n_verdict_recorded']} | 状态已记录 {hack['n_status_recorded']} | "
        f"已求值 {hack['n_evaluated']} | 没看 {hack['n_silent']} | 状态未记录 {hack['n_status_unrecorded']} | "
        f"判定未记录 {hack['n_not_recorded']}"
    )
    print(f"hack 状态分布 {hack['status']}")
    print(
        f"hack 判 True {hack['n_suspected']} / 信号非空 {hack['n_signal_nonempty']} / "
        f"信号分布 {hack['signals']} / 词表外 {hack['unknown_signals'] or '无'}"
    )
    print(
        f"hack 判 True 却非 ok {hack['n_suspected_without_evaluation']} | 四档恒等式 "
        f"{'成立' if hack['n_evaluated'] + hack['n_silent'] + hack['n_status_unrecorded'] + hack['n_not_recorded'] == out['n_rows'] else '**破裂**'}"
    )
    ratio = "—" if fl["hit_ratio"] is None else f"{fl['hit_ratio']:.4f}"
    print(
        f"FL: 有判定 {fl['n_verdict_recorded']} | hit {fl['n_hit']} / miss {fl['n_miss']} / "
        f"not_evaluable {fl['n_not_evaluable']} | 已求值 {fl['n_evaluated']} | hit 比 {ratio}"
    )
    print(f"FL 成因来源 {fl['basis']}")
    print(f"FL 成因（记录）{fl['reason_recorded']}")
    print(f"FL 成因（推断，下界）{fl['reason_inferred']}")
    judge = sum(fl["reason_recorded"].values()) + sum(fl["reason_inferred"].values())
    print(
        f"FL 成因不一致 {fl['n_reason_mismatch']} | 成因恒等式 {'成立' if judge == fl['n_not_evaluable'] else '**破裂**'}"
    )
    print(f"FL hit_rank 分布 {fl['hit_rank']}")
    print(f"FL 变更函数分档 {fl['changed_len']}")


def print_pool() -> None:
    sys.path.insert(0, str(ROOT / "scripts" / "tools"))
    import bu_writeonly_key_census as bu

    cls, report_face, batches, rows = bu.census_readers()
    print("\n=== B 段：只写不读键池复核（BU 口径）===")
    pool: list[tuple[int, str]] = []
    for key, n in rows.items():
        c = cls.get(key, {})
        if c.get("row_read", 0) == 0 and c.get("state_read", 0) + c.get("other_read", 0) == 0:
            pool.append((n, key))
    pool.sort(reverse=True)
    print(f"批次文件 {batches}；键种 {len(rows)}；零读者键 {len(pool)} 个，行合计 {sum(n for n, _ in pool)}")
    for n, key in pool:
        print(f"  {key:38s} {n:6d}")
    print("BV 两族现状（报告面读者数单列）：")
    for key in (
        "test_hacking_suspected",
        "test_hacking_signals",
        "fl_constraint_verdict",
        "fl_constraint_hit_rank",
        "fl_constraint_changed_functions",
    ):
        c = cls.get(key, {})
        print(
            f"  {key:32s} 归档行 {rows[key]:6d} | row_read {c.get('row_read', 0)} "
            f"(报告面 {report_face.get(key, 0)}) | state_read {c.get('state_read', 0)} | write {c.get('write', 0)}"
        )
    # 期望：改前池 = 11 键 / 64618 行（BU 轮口径）；BV 两族共 5 键接入读端后
    # 池应剩 11 − 5 = 6 键，行合计 64618 − 5 × 5935 = 34943。
    # 键数与行数必须**同时**对上——只对行数会漏掉「键被拆/并」的漂移。
    print("> 期望：池 = 6 键 / 34943 行（11 键 − 5 键；64618 − 5 × 5935）。对不上即为接线漂移。")
    if len(pool) != 6 or sum(n for n, _ in pool) != 34943:
        print("  **漂移**：池的键数/行数与期望不符。")
    else:
        print("  池口径 OK（6 键 / 34943 行）。")


def print_pinned() -> int:
    """C 段：逐档核对四个具名冻结批次。返回 0 = 全部 OK，非 0 = 有失败。

    **失败路径必须给非零退出码**（BV 自纠①）：此前本段解析失败时只打印一行
    「解析失败」就 `return`，退出码仍是 0——四个批次的核对从未真正跑过，
    而整轮普查看起来像跑完了。段失败 ≠ 段成功。
    """
    from experiments.statistical_analysis import detector_silence_stats

    print("\n=== C 段：具名冻结批次逐档读数（与测试锁同源）===")
    tests = ROOT / "tests" / "test_verdict_silence_bv.py"
    if not tests.exists():
        print("  测试文件缺失，**失败**")
        return 1
    tree = ast.parse(tests.read_text(encoding="utf-8"))
    literal = None
    for node in ast.walk(tree):
        # `PINNED_BATCHES: dict[str, dict[str, int]] = {...}` 是**带注解**赋值
        # （ast.AnnAssign），不是 ast.Assign——只认 Assign 会静默解析失败。
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "PINNED_BATCHES":
                literal = ast.literal_eval(node.value)
        elif isinstance(node, ast.Assign):
            for tg in node.targets:
                if isinstance(tg, ast.Name) and tg.id == "PINNED_BATCHES":
                    literal = ast.literal_eval(node.value)
    if not isinstance(literal, dict):
        print("  PINNED_BATCHES 解析失败，**失败**")
        return 1
    n_ok = 0
    for rel, want in sorted(literal.items()):
        path = ROOT / rel
        if not path.exists():
            print(f"  缺失：{rel}，**失败**")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = [
            r
            for blk in (doc.get("results") or {}).values()
            for r in (blk or {}).get("details") or []
            if isinstance(r, dict)
        ]
        out = detector_silence_stats(rows)
        hack, fl = out["hack"], out["fl"]
        got = {
            "n_rows": out["n_rows"],
            "hack_verdict_recorded": hack["n_verdict_recorded"],
            "hack_status_unrecorded": hack["n_status_unrecorded"],
            "hack_evaluated": hack["n_evaluated"],
            "hack_suspected": hack["n_suspected"],
            "fl_hit": fl["n_hit"],
            "fl_miss": fl["n_miss"],
            "fl_not_evaluable": fl["n_not_evaluable"],
            "fl_reason_inferred": sum(fl["reason_inferred"].values()),
            "fl_changed_0": fl["changed_len"].get("0", 0),
        }
        drift = {k: (v, got[k]) for k, v in want.items() if got[k] != v}
        if not drift:
            n_ok += 1
        print(f"  {'OK  ' if not drift else 'DRIFT'} {path.name}  {drift or ''}")
    n_all = len(literal)
    if n_ok != n_all:
        print(f"  C 段 {n_ok}/{n_all} 通过，**失败**")
        return 1
    print(f"  C 段 {n_ok}/{n_all} 全部 OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="BV 轮只读普查（判定核沉默分档 + 键池复核）")
    ap.add_argument("--segment", choices=("a", "b", "c", "all"), default="all")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    rc = 0
    if args.segment in {"a", "all"}:
        print_archive()
    if args.segment in {"b", "all"}:
        print_pool()
    if args.segment in {"c", "all"}:
        rc |= print_pinned()
    return rc


if __name__ == "__main__":
    sys.exit(main())
