#!/usr/bin/env python3
"""BU 轮（2026-10-22）只读探针：只写不读键池普查 + Self-Repair Trap 输入可达域。

背景：
    BH→BT 系列量到 BQ 轮已经确立一条口径（`docs/MEASUREMENT_INTEGRITY.md` §61①）——
    「写了没人读」要按**读法**分类计数（从哪儿读、读进哪个判定），不能按键名出现次数
    计数。BN/BQ/BT 各收了一组通道，但归档结果行里仍有一整批键处于「只有写入点」的
    状态。BU 轮先把这批键点清，再从里面挑一个判定族收口：
    `self_repair_trap_suspected` / `self_repair_trap_signals`（批次 XIV，ADR-0028）。

三段（全部只读；仓库零写入、零 LLM）：
    A 段  键池普查：`experiments/results/**/*.json` 的 details 行键集合 × `src/` +
          `experiments/` + `scripts/` 的 AST 读法分类（write / state_read / row_read /
          other_read），点出「行读 = 0 且非写入命中 = 0」的键，并给报告面
          （`analyze_results.py` + `statistical_analysis.py`）读者数单列。
    B 段  可达域读数：全归档跑 `self_repair_trap_domain_stats`，打印四档、三信号
          各自输入域、两点下降域外行数、同进程重跑对账（不一致 / 异常 / 读不懂）。
    C 段  具名批次核对：三份冻结批次的逐档读数，与 `tests/test_trap_input_domain_bu.py`
          的 `PINNED_BATCHES` 对照（锁与量具同源，任一边漂移都会在这里露出来）。

用法：.venv/bin/python scripts/tools/bu_writeonly_key_census.py
"""

from __future__ import annotations

import argparse
import ast
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CODE_DIRS = ("src", "experiments", "scripts")
REPORT_FACE = ("experiments/analyze_results.py", "experiments/statistical_analysis.py")

STATE_RECEIVERS = re.compile(r"^(final_state|state|_post|post|self\.state|task_state|graph_state|result_state)\b")
ROW_RECEIVERS = re.compile(r"^(row|rows|r|rec|record|item|entry|detail|details|res|result|task_result|arm|block|d)\b")


def _target_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tg in targets:
                ids.update(id(sub) for sub in ast.walk(tg) if isinstance(sub, ast.Subscript))
    return ids


def _key_hits(node: ast.AST, ctx_fn: str, consts: dict[str, str]) -> list[tuple[str, str]]:
    """返回 (键名, 接收者文本)；接收者以 `<dict-literal:…>` 前缀标记字面量写点。

    键位允许是字符串字面量，也可以是模块级大写字面量常量（如
    `TRAP_VERDICT_KEY = "self_repair_trap_suspected"`）——只认字面量的普查会把
    经由常量取键的读侧数成 0（BU 轮读侧正是这种写法）。
    """

    def _resolve(expr: ast.AST) -> str | None:
        if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
            return expr.value
        if isinstance(expr, ast.Name):
            return consts.get(expr.id)
        return None

    if isinstance(node, ast.Subscript):
        key = _resolve(node.slice)
        if key is not None:
            return [(key, ast.unparse(node.value))]
        return []
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"get", "pop", "setdefault"}
        and node.args
    ):
        key = _resolve(node.args[0])
        if key is not None:
            return [(key, ast.unparse(node.func.value))]
        return []
    if (
        isinstance(node, ast.Compare)
        and any(isinstance(op, (ast.In, ast.NotIn)) for op in node.ops)
        and node.left is not None
    ):
        key = _resolve(node.left)
        if key is not None:
            return [(key, ast.unparse(node.comparators[0]))]
        return []
    if isinstance(node, ast.Dict):
        return [
            (k.value, f"<dict-literal:{ctx_fn}>")
            for k in node.keys
            if isinstance(k, ast.Constant) and isinstance(k.value, str)
        ]
    return []


def _string_constants(trees: list[ast.Module]) -> dict[str, str]:
    """模块级大写字面量常量表（键名的符号形态；同名多值只留首个）。"""
    table: dict[str, str] = {}
    for tree in trees:
        for node in tree.body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)):
                continue
            name = node.targets[0].id
            if name.isupper() and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                table.setdefault(name, node.value.value)
    return table


def census_readers() -> tuple[dict[str, collections.Counter], dict[str, int], int, collections.Counter]:
    """AST 读法普查：键 → 分类计数，键 → 报告面读者数，归档行数，键 → 行读数。"""
    cls: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    report_face: dict[str, int] = collections.defaultdict(int)
    rows: collections.Counter = collections.Counter()
    batch_files = 0
    parsed: list[tuple[str, ast.Module]] = []
    for directory in CODE_DIRS:
        for path in sorted((ROOT / directory).rglob("*.py")):
            rel = str(path.relative_to(ROOT))
            try:
                parsed.append((rel, ast.parse(path.read_text(encoding="utf-8"))))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
    consts = _string_constants([tree for _, tree in parsed])
    for rel, tree in parsed:
        target_ids = _target_ids(tree)
        owner: dict[int, str] = {}
        for fn in ast.walk(tree):
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for inner in ast.walk(fn):
                    owner.setdefault(id(inner), fn.name)
        for node in ast.walk(tree):
            ctx_fn = owner.get(id(node)) or "<module>"
            for key, recv in _key_hits(node, ctx_fn, consts):
                if recv.startswith("<dict-literal") or (isinstance(node, ast.Subscript) and id(node) in target_ids):
                    kind = "write"
                elif STATE_RECEIVERS.match(recv):
                    kind = "state_read"
                elif ROW_RECEIVERS.match(recv):
                    kind = "row_read"
                else:
                    kind = "other_read"
                cls[key][kind] += 1
                if kind == "row_read" and rel in REPORT_FACE:
                    report_face[key] += 1

    for path in sorted((ROOT / "experiments" / "results").rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not (isinstance(doc, dict) and isinstance(doc.get("results"), dict)):
            continue
        batch_files += 1
        for block in doc["results"].values():
            for r in (block or {}).get("details") or []:
                if isinstance(r, dict):
                    rows.update(r.keys())
    return cls, dict(report_face), batch_files, rows


def print_pool(
    cls: dict[str, collections.Counter], report_face: dict[str, int], batch_files: int, rows: collections.Counter
) -> None:
    print("=== A 段：只写不读键池（读法分类口径，§61①）===")
    print(f"批次文件 {batch_files}；结果行键种 {len(rows)}")
    pool: list[tuple[int, str, int]] = []
    for key, n in rows.items():
        c = cls.get(key, collections.Counter())
        if c["row_read"] == 0 and c["state_read"] + c["other_read"] == 0:
            pool.append((n, key, c["write"]))
    pool.sort(key=lambda t: -t[0])
    print(f"全树零读者（只有写入点）的键 = {len(pool)} 个，归档行合计 = {sum(t[0] for t in pool)}")
    for n, key, w in pool:
        print(f"  {key:38s} 归档行 {n:6d} 写入点 {w:2d}")
    print("\nBU 轮点名的两键现状（报告面读者数单列）：")
    for key in ("self_repair_trap_suspected", "self_repair_trap_signals"):
        c = cls.get(key, collections.Counter())
        print(
            f"  {key:32s} 归档行 {rows[key]:6d} | row_read {c['row_read']} "
            f"(报告面 {report_face.get(key, 0)}) | state_read {c['state_read']} | write {c['write']}"
        )
    print(
        "\n> 改前基线（本会话普查在 BU 代码落地前的形态）：13 键 / 76488 行 = 上表键集 "
        "+ 上述两键（各 5935 行）。两键接入报告面后应剩 11 键 / 64618 行；"
        "对不上即为接线漂移。"
    )
    two = rows["self_repair_trap_suspected"] + rows["self_repair_trap_signals"]
    pool_sum = sum(t[0] for t in pool)
    print(f"> 核对：池合计 {pool_sum} + 两键 {two} = {pool_sum + two}（改前登记值 76488）")


def print_domain() -> None:
    from experiments.statistical_analysis import self_repair_trap_domain_stats

    rows: list[dict] = []
    for path in sorted((ROOT / "experiments" / "results").rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not (isinstance(doc, dict) and isinstance(doc.get("results"), dict)):
            continue
        for block in doc["results"].values():
            rows.extend(r for r in (block or {}).get("details") or [] if isinstance(r, dict))
    out = self_repair_trap_domain_stats(rows)
    print("\n=== B 段：Self-Repair Trap 输入可达域（全归档）===")
    print(
        f"行 {out['n_rows']} 有判定 {out['n_with_verdict']} | 四档 "
        f"未记录 {out['not_recorded']} / 历史 null {out['history_malformed']} / "
        f"<2 点 {out['below_min_floor']} / ≥2 点 {out['min_floor_reached']}"
    )
    assert (
        out["not_recorded"] + out["history_malformed"] + out["below_min_floor"] + out["min_floor_reached"]
        == out["n_rows"]
    ), "四档恒等式破裂"
    dom = out["signal_domain"]
    print(
        f"三信号可达域：declining {dom['assert_count_declining']} / "
        f"collapse {dom['assertion_collapse']} / score {dom['mutation_score_declining']}"
    )
    print(
        f"判定为真 {out['n_verdict_true']} 信号非空 {out['n_signals_nonempty']} "
        f"域外两点下降 {out['n_decline2_outside_domain']}"
    )
    print(
        f"同进程重跑对账：判定不一致 {out['n_suspected_mismatch']} 信号不一致 "
        f"{out['n_signals_mismatch']} 重跑异常 {out['n_rerun_error']} 读不懂 {out['n_unmeasurable']}"
    )


def print_pinned() -> None:
    from experiments.statistical_analysis import self_repair_trap_domain_stats

    print("\n=== C 段：具名冻结批次逐档读数（与测试锁同源）===")
    tests = ROOT / "tests" / "test_trap_input_domain_bu.py"
    if not tests.exists():
        print("  测试文件缺失，跳过")
        return
    tree = ast.parse(tests.read_text(encoding="utf-8"))
    literal = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for tg in node.targets:
                if isinstance(tg, ast.Name) and tg.id == "PINNED_BATCHES":
                    literal = ast.literal_eval(node.value)
    if not isinstance(literal, dict):
        print("  PINNED_BATCHES 解析失败")
        return
    for rel, want in sorted(literal.items()):
        path = ROOT / rel
        if not path.exists():
            print(f"  缺失：{rel}")
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = [
            r
            for blk in (doc.get("results") or {}).values()
            for r in (blk or {}).get("details") or []
            if isinstance(r, dict)
        ]
        out = self_repair_trap_domain_stats(rows)
        got = {
            "n_rows": out["n_rows"],
            "n_with_verdict": out["n_with_verdict"],
            "not_recorded": out["not_recorded"],
            "history_malformed": out["history_malformed"],
            "below_min_floor": out["below_min_floor"],
            "min_floor_reached": out["min_floor_reached"],
            "declining": out["signal_domain"]["assert_count_declining"],
            "collapse": out["signal_domain"]["assertion_collapse"],
            "score": out["signal_domain"]["mutation_score_declining"],
            "n_decline2_outside_domain": out["n_decline2_outside_domain"],
            "n_verdict_true": out["n_verdict_true"],
            "n_signals_nonempty": out["n_signals_nonempty"],
            "n_suspected_mismatch": out["n_suspected_mismatch"],
            "n_signals_mismatch": out["n_signals_mismatch"],
            "n_unmeasurable": out["n_unmeasurable"],
        }
        drift = {k: (v, got[k]) for k, v in want.items() if got[k] != v}
        print(f"  {'OK  ' if not drift else 'DRIFT'} {path.name}  {drift or ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description="BU 轮只读普查（只写不读键池 + 输入可达域）")
    ap.add_argument("--segment", choices=("a", "b", "c", "all"), default="all", help="只跑某一段")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    if args.segment in {"a", "all"}:
        print_pool(*census_readers())
    if args.segment in {"b", "all"}:
        print_domain()
    if args.segment in {"c", "all"}:
        print_pinned()
    return 0


if __name__ == "__main__":
    sys.exit(main())
