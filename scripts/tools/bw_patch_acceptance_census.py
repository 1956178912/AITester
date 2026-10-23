#!/usr/bin/env python3
"""BW 轮（2026-10-23）只读探针：补丁接收链的分母与输入可达域普查。

背景：
    BU 普查（2026-10-22）量出 13 键 / 76,488 行的「只写不读」池；BV 收掉两份判定核后
    剩 6 键 / 34,943 行。BW 收掉其中四条（`patch_precision`、`patch_plausible_evidence`、
    `patch_plausible_invariant_violation`、`patch_abstain_signals`），并顺带把只有测试
    读者的 `patch_validated` / `patch_validate_verdict` 接进报告面。四组判定值本身忠实，
    沉默在分母与输入可达域上（详见 `experiments/_patch_acceptance.py`）。

三段（全部只读；仓库零写入、零 LLM）：
    A 段  键池普查：`experiments/results/**/*.json` 的 details 行键集合 × `src/` +
          `experiments/` + `scripts/` 的 AST 读法分类（write / state_read / row_read /
          other_read），断言 BW 接入后池内只剩 `risk_summary` / `mdo_crash_rate`
          （2 键 / 12,908 行），且四条 BW 键都有读侧命中。
    B 段  归档读数：全归档跑 `patch_acceptance_stats`，打印四组读数并断言分档恒等式；
          当归档仍是登记时点（257 份批次 / 11,197 行）时，同时断言手册登记的逐项读数。
    C 段  具名批次核对：从 `tests/test_patch_acceptance_bw.py` 的 `PINNED_BATCHES`
          解析五份冻结批次的逐档读数（AST 字面量），与测试锁同源。
          任一边漂移都会在这里露出来。

用法：.venv/bin/python scripts/tools/bw_patch_acceptance_census.py
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
#: 报告面读侧：`_patch_acceptance` 是单一事实源，`run_main_batch` 是批次摘要。
REPORT_FACE = (
    "experiments/analyze_results.py",
    "experiments/statistical_analysis.py",
    "experiments/_patch_acceptance.py",
    "experiments/run_main_batch.py",
)

STATE_RECEIVERS = re.compile(r"^(final_state|state|_post|post|self\.state|task_state|graph_state|result_state)\b")
ROW_RECEIVERS = re.compile(r"^(row|rows|r|rec|record|item|entry|detail|details|res|result|task_result|arm|block|d)\b")

BW_KEYS = (
    "patch_precision",
    "patch_plausible_evidence",
    "patch_plausible_invariant_violation",
    "patch_abstain_signals",
)
VALIDATED_KEYS = ("patch_validated", "patch_validate_verdict")


def _target_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tg in targets:
                ids.update(id(sub) for sub in ast.walk(tg) if isinstance(sub, ast.Subscript))
    return ids


def _key_hits(node: ast.AST, ctx_fn: str, consts: dict[str, str]) -> list[tuple[str, str]]:
    """返回 (键名, 接收者文本)；接收者以 `<dict-literal:…>` 前缀标记字面量写点。"""

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
    print("=== A 段：只写不读键池（读法分类口径）===")
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
    assert [key for _, key, _ in pool] == ["risk_summary", "mdo_crash_rate"], pool
    assert sum(t[0] for t in pool) == 12908, sum(t[0] for t in pool)

    print("\nBW 接入的四键（读侧命中单列）：")
    bw_rows = 0
    for key in BW_KEYS:
        c = cls.get(key, collections.Counter())
        print(
            f"  {key:38s} 归档行 {rows.get(key, 0):6d} | row_read {c['row_read']} "
            f"(报告面 {report_face.get(key, 0)}) | state_read {c['state_read']} | write {c['write']}"
        )
        assert c["row_read"] > 0, f"{key} 仍无行读侧"
        assert report_face.get(key, 0) > 0, f"{key} 未进报告面"
        bw_rows += rows.get(key, 0)
    for key in VALIDATED_KEYS:
        c = cls.get(key, collections.Counter())
        print(
            f"  {key:38s} 归档行 {rows.get(key, 0):6d} | row_read {c['row_read']} "
            f"(报告面 {report_face.get(key, 0)}) | state_read {c['state_read']} | write {c['write']}"
        )
        assert c["row_read"] > 0, f"{key} 仍无行读侧"
        assert report_face.get(key, 0) > 0, f"{key} 未进报告面"

    post = sum(t[0] for t in pool)
    # 四条池内键的行数（patch_validated 不在 BU 池内，单独披露但不进恒等式）。
    print(
        f"> 核对：接入后池 {len(pool)} 键 / {post} 行 + BW 四条池内键 {bw_rows} 行 "
        f"= {post + bw_rows}（应为改前 6 键 / 34943 行）"
    )
    assert (len(pool), post + bw_rows) == (2, 34943)


def _archive_rows() -> tuple[list[dict], int]:
    rows: list[dict] = []
    files = 0
    for path in sorted((ROOT / "experiments" / "results").rglob("*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not (isinstance(doc, dict) and isinstance(doc.get("results"), dict)):
            continue
        files += 1
        for block in doc["results"].values():
            rows.extend(r for r in (block or {}).get("details") or [] if isinstance(r, dict))
    return rows, files


def print_archive() -> None:
    from experiments.statistical_analysis import patch_acceptance_stats

    rows, files = _archive_rows()
    out = patch_acceptance_stats(rows)
    a, e, ab, va = out["acceptance"], out["evidence"], out["abstain"], out["validate"]
    print("\n=== B 段：归档读数（全 JSON 扫描，含 schema 混批）===")
    print(f"批次文件 {files}；行 {out['n_rows']}")
    print(
        f"接收链：已记录 {a['n_recorded']} | plausible {a['n_plausible']} | correct {a['n_correct']} | "
        f"交 {a['n_plausible_correct']} | 接受集判错 {a['n_plausible_incorrect']} | "
        f"排除集判对 {a['n_implausible_correct']} | 无 gold {a['n_plausible_no_gold']}"
    )
    print(
        f"  精确率 {a['precision']['value']:.6f} / 并集 {a['precision']['union_value']:.6f} / "
        f"gold {a['precision']['gold_value']:.6f}；覆盖率 {a['coverage']['value']:.6f}"
    )
    print(f"  不变量 {dict(a['invariant'])}")
    print(
        f"证据：已记录 {e['n_recorded']} / 未记录 {e['n_unrecorded']} | basis {dict(e['basis'])} | "
        f"隐含 plausible {e['n_implied_plausible']} | plausible 无证据 {e['n_plausible_without_evidence']} | "
        f"不一致 {e['n_mismatch']}"
    )
    print(
        f"弃权：已记录 {ab['n_recorded']} | abstained {ab['n_abstained']} | 无可抑制对象 {ab['n_no_effect']} | "
        f"可抑制 {ab['n_actionable']} | 抑制 passed {ab['n_suppressed']} | "
        f"抑制精确率 {ab['suppressed_precision']['value']:.6f}（{ab['suppressed_precision']['numerator']}/"
        f"{ab['suppressed_precision']['denominator']}）| 全部分母 "
        f"{ab['suppressed_precision']['all_value']:.6f}"
    )
    print(
        f"验证：已记录 {va['n_recorded']} | validated {va['n_validated']} | unvalidated {va['n_unvalidated']} | "
        f"无输入 {va['n_no_input']} | 未验证且无输入 {va['n_unvalidated_without_input']} | "
        f"输入 {dict(va['input_counts'])} | 等级 {dict(va['evidence_level_values'])}"
    )
    print(
        f"  passed {va['n_passed']}（抑制 {va['n_passed_abstained']} / 未抑制 {va['n_passed_not_abstained']}）| "
        f"filtered success {va['n_filtered_success']} | 覆盖率 "
        f"{va['filtered_coverage_passed']:.6f} / 未抑制 {va['filtered_coverage_passed_not_abstained']:.6f}"
    )

    # 分档恒等式（与测试锁同一口径）。
    assert (
        a["n_plausible_correct"]
        + a["n_plausible_incorrect"]
        + a["n_implausible_correct"]
        + a["n_implausible_incorrect"]
        == a["n_recorded"]
    )
    assert a["n_plausible"] == a["n_plausible_correct"] + a["n_plausible_incorrect"]
    assert a["n_correct"] == a["n_plausible_correct"] + a["n_implausible_correct"]
    assert a["precision_mismatch"] == 0
    assert e["n_recorded"] + e["n_unrecorded"] == out["n_rows"]
    assert sum(e["basis"].values()) == out["n_rows"]
    assert e["n_mismatch"] == 0
    assert sum(sum(c.values()) for c in ab["buckets"].values()) == ab["n_recorded"]
    assert ab["n_actionable"] + ab["n_no_effect"] == ab["n_abstained"]
    assert ab["n_abstain_mismatch"] == 0 and ab["n_signal_mismatch"] == 0
    assert va["n_validated"] + va["n_unvalidated"] + va["n_other"] == va["n_recorded"]
    assert sum(va["verdict"].values()) == va["n_recorded"]
    assert va["n_verdict_mismatch"] == 0 and va["n_validated_mismatch"] == 0

    if (files, out["n_rows"]) != (257, 11197):
        print(f"> 归档已漂移（{files} 份 / {out['n_rows']} 行）：只校验恒等式，登记读数需按新时点重测。")
        return

    want = {
        "acc_recorded": 8012,
        "plausible": 1331,
        "correct": 746,
        "pc": 607,
        "pi": 724,
        "ic": 139,
        "no_gold": 283,
        "gold_correct": 607,
        "gold_incorrect": 441,
        "inv_violation": 139,
        "inv_flag_true": 10,
        "inv_flag_missing": 129,
        "inv_flag_unrecorded": 3968,
        "ev_recorded": 4044,
        "ev_applied": 614,
        "ev_atr": 32,
        "ev_rejected": 368,
        "ev_no_patch": 3030,
        "ev_implied": 646,
        "ev_pwe": 685,
        "ab_recorded": 5935,
        "abstained": 3605,
        "no_effect": 608,
        "actionable": 2997,
        "suppressed": 1960,
        "suppressed_correct": 117,
        "suppressed_gi": 1825,
        "suppressed_ng": 18,
        "signal_nonempty": 3605,
        "multi_signal": 2042,
        "va_recorded": 4044,
        "validated": 594,
        "unvalidated": 3450,
        "no_input": 3037,
        "unvalidated_without_input": 3037,
        "level_input": 1007,
        "level_sbfl": 594,
        "level_none": 387,
        "level_keyword": 26,
        "level_null": 3037,
        "verdict_evidence": 594,
        "verdict_unvalidated": 3450,
        "passed": 2116,
        "passed_abstained": 1198,
        "passed_not_abstained": 918,
        "filtered": 329,
    }
    got = {
        "acc_recorded": a["n_recorded"],
        "plausible": a["n_plausible"],
        "correct": a["n_correct"],
        "pc": a["n_plausible_correct"],
        "pi": a["n_plausible_incorrect"],
        "ic": a["n_implausible_correct"],
        "no_gold": a["n_plausible_no_gold"],
        "gold_correct": a["n_gold_correct"],
        "gold_incorrect": a["n_gold_incorrect"],
        "inv_violation": a["invariant"].get("violation", 0),
        "inv_flag_true": a["invariant"].get("flag_true", 0),
        "inv_flag_missing": a["invariant"].get("flag_missing", 0),
        "inv_flag_unrecorded": a["invariant"].get("flag_unrecorded", 0),
        "ev_recorded": e["n_recorded"],
        "ev_applied": e["basis"].get("applied", 0),
        "ev_atr": e["basis"].get("applied_then_rejected", 0),
        "ev_rejected": e["basis"].get("rejected", 0),
        "ev_no_patch": e["basis"].get("no_patch", 0),
        "ev_implied": e["n_implied_plausible"],
        "ev_pwe": e["n_plausible_without_evidence"],
        "ab_recorded": ab["n_recorded"],
        "abstained": ab["n_abstained"],
        "no_effect": ab["n_no_effect"],
        "actionable": ab["n_actionable"],
        "suppressed": ab["n_suppressed"],
        "suppressed_correct": ab["suppressed_status"].get("correct", 0),
        "suppressed_gi": ab["suppressed_status"].get("gold_incorrect", 0),
        "suppressed_ng": ab["suppressed_status"].get("no_gold", 0),
        "signal_nonempty": ab["n_signal_nonempty"],
        "multi_signal": ab["n_multi_signal"],
        "va_recorded": va["n_recorded"],
        "validated": va["n_validated"],
        "unvalidated": va["n_unvalidated"],
        "no_input": va["n_no_input"],
        "unvalidated_without_input": va["n_unvalidated_without_input"],
        "level_input": va["input_counts"].get("patch_evidence_level", 0),
        "level_sbfl": va["evidence_level_values"].get("sbfl", 0),
        "level_none": va["evidence_level_values"].get("none", 0),
        "level_keyword": va["evidence_level_values"].get("keyword", 0),
        "level_null": va["evidence_level_values"].get("null", 0),
        "verdict_evidence": va["verdict"].get("evidence", 0),
        "verdict_unvalidated": va["verdict"].get("unvalidated", 0),
        "passed": va["n_passed"],
        "passed_abstained": va["n_passed_abstained"],
        "passed_not_abstained": va["n_passed_not_abstained"],
        "filtered": va["n_filtered_success"],
    }
    drift = {k: (v, got[k]) for k, v in want.items() if got[k] != v}
    assert not drift, drift
    print("> 登记读数逐项一致（BW 手册 §1–§4）。")


def _pinned_batches() -> dict[str, dict]:
    tests = ROOT / "tests" / "test_patch_acceptance_bw.py"
    tree = ast.parse(tests.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "PINNED_BATCHES"
            and node.value is not None
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("测试文件里没有 PINNED_BATCHES")


def print_pinned() -> None:
    from experiments.statistical_analysis import patch_acceptance_stats

    print("\n=== C 段：具名冻结批次逐档读数（与测试锁同源）===")
    for rel, want in _pinned_batches().items():
        path = ROOT / rel
        doc = json.loads(path.read_text(encoding="utf-8"))
        rows = [
            r
            for blk in (doc.get("results") or {}).values()
            for r in (blk or {}).get("details") or []
            if isinstance(r, dict)
        ]
        out = patch_acceptance_stats(rows)
        a, e, ab, va = out["acceptance"], out["evidence"], out["abstain"], out["validate"]
        got = {
            "n_rows": out["n_rows"],
            "acc_recorded": a["n_recorded"],
            "plausible": a["n_plausible"],
            "correct": a["n_correct"],
            "pc": a["n_plausible_correct"],
            "pi": a["n_plausible_incorrect"],
            "ic": a["n_implausible_correct"],
            "iic": a["n_implausible_incorrect"],
            "no_gold": a["n_plausible_no_gold"],
            "gold_correct": a["n_gold_correct"],
            "gold_incorrect": a["n_gold_incorrect"],
            "precision_mismatch": a["precision_mismatch"],
            "invariant": a["invariant"],
            "evidence": {
                "n_recorded": e["n_recorded"],
                "n_unrecorded": e["n_unrecorded"],
                "basis": e["basis"],
                "n_plausible_without_evidence": e["n_plausible_without_evidence"],
                "n_mismatch": e["n_mismatch"],
            },
            "abstain": {
                "n_recorded": ab["n_recorded"],
                "n_abstained": ab["n_abstained"],
                "n_no_effect": ab["n_no_effect"],
                "n_actionable": ab["n_actionable"],
                "n_suppressed": ab["n_suppressed"],
                "suppressed_status": ab["suppressed_status"],
                "n_signal_nonempty": ab["n_signal_nonempty"],
                "n_multi_signal": ab["n_multi_signal"],
                "signals": ab["signals"],
                "n_abstain_mismatch": ab["n_abstain_mismatch"],
                "n_signal_mismatch": ab["n_signal_mismatch"],
            },
            "validate": {
                "n_recorded": va["n_recorded"],
                "n_validated": va["n_validated"],
                "n_unvalidated": va["n_unvalidated"],
                "n_no_input": va["n_no_input"],
                "n_unvalidated_without_input": va["n_unvalidated_without_input"],
                "verdict": va["verdict"],
                "evidence_level_values": va["evidence_level_values"],
                "n_passed": va["n_passed"],
                "n_passed_abstained": va["n_passed_abstained"],
                "n_passed_not_abstained": va["n_passed_not_abstained"],
                "n_filtered_success": va["n_filtered_success"],
                "n_verdict_mismatch": va["n_verdict_mismatch"],
                "n_validated_mismatch": va["n_validated_mismatch"],
            },
        }
        drift = {k: (v, got.get(k)) for k, v in want.items() if got.get(k) != v}
        print(f"  {'OK  ' if not drift else 'DRIFT'} {path.name}  {drift or ''}")
        assert not drift, (rel, drift)


def main() -> int:
    ap = argparse.ArgumentParser(description="BW 轮只读普查（接收链分母 + 输入可达域）")
    ap.add_argument("--segment", choices=("a", "b", "c", "all"), default="all", help="只跑某一段")
    args = ap.parse_args()
    sys.path.insert(0, str(ROOT))
    if args.segment in {"a", "all"}:
        print_pool(*census_readers())
    if args.segment in {"b", "all"}:
        print_archive()
    if args.segment in {"c", "all"}:
        print_pinned()
    return 0


if __name__ == "__main__":
    sys.exit(main())
