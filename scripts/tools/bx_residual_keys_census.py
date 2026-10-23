#!/usr/bin/env python3
"""BX 轮（2026-10-23）只读探针：写而不读键池最后两键的读侧普查。

背景：
    BU 普查（2026-10-22）量出 13 键 / 76,488 行的「只写不读」池；BV 收掉两份判定核
    （剩 6 键 / 34,943 行），BW 收掉补丁接收链四条（22,035 行），池内只剩
    `risk_summary`（8,864 行）与 `mdo_crash_rate`（4,044 行）——合计 2 键 / 12,908 行。
    BX 为两键补读侧（`experiments/_residual_keys.py` + 报告面章节 + 批次摘要行），
    不改写入端、不改任何行的值与方向。

三段（全部只读；仓库零写入、零 LLM）：
    A 段  键池普查：按 BW 同一套 AST 读法分类，断言 BX 之后零读者池**为空**，
          且两键都有行读侧命中（含报告面），归档行数合计仍为 12,908。
    B 段  归档读数：全归档跑 `residual_keys_stats`，打印五层输入域、值域与分母口径，
          并断言分档恒等式；当归档仍是登记时点（257 份批次 / 11,197 行）时，
          同时断言手册登记的逐项读数。
    C 段  具名批次核对：从 `tests/test_residual_keys_bx.py` 的 `PINNED_BATCHES`
          解析三份冻结批次的逐档读数（AST 字面量），与测试锁同源。

用法：.venv/bin/python scripts/tools/bx_residual_keys_census.py [--segment a|b|c|all]
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
#: 报告面读侧：`_residual_keys` 是单一事实源，`run_main_batch` 是批次摘要。
REPORT_FACE = (
    "experiments/analyze_results.py",
    "experiments/statistical_analysis.py",
    "experiments/_residual_keys.py",
    "experiments/run_main_batch.py",
)
RESIDUAL_KEYS = ("risk_summary", "mdo_crash_rate")

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
    assert pool == [], pool

    two_key_rows = 0
    print("\nBX 接入的两键（读侧命中单列）：")
    for key in RESIDUAL_KEYS:
        c = cls.get(key, collections.Counter())
        print(
            f"  {key:38s} 归档行 {rows.get(key, 0):6d} | row_read {c['row_read']} "
            f"(报告面 {report_face.get(key, 0)}) | state_read {c['state_read']} | write {c['write']}"
        )
        assert c["row_read"] > 0, f"{key} 仍无行读侧"
        assert report_face.get(key, 0) > 0, f"{key} 未进报告面"
        two_key_rows += rows.get(key, 0)
    assert two_key_rows == 12908, two_key_rows

    # BU 池的逐轮收口算术（登记值）：BV 41,545 + BW 22,035 + BX 12,908 = BU 76,488。
    print(
        f"> 核对：BU 池 13 键 / 76,488 行 = BV 41,545 + BW 22,035 + BX {two_key_rows} "
        f"= {41545 + 22035 + two_key_rows} 行；BX 之后零读者池为空。"
    )
    assert 41545 + 22035 + two_key_rows == 76488


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
    from experiments._residual_keys import (
        CRASH_UNMEASURED_LAYERS,
        MDO_EVALUABILITY_KEYS,
        residual_keys_stats,
    )

    rows, files = _archive_rows()
    out = residual_keys_stats(rows)
    r, c = out["risk_summary"], out["mdo_crash"]
    layers = c["layers"]
    pooled = c["pooled"]
    raw = c["provisional_raw"]
    print("\n=== B 段：归档读数（全 JSON 扫描，含 schema 混批）===")
    print(f"批次文件 {files}；行 {out['n_rows']}")
    print(
        f"risk_summary：在场 {r['n_key_present']} / 缺席 {r['n_key_absent']} / 非字典 {r['n_non_dict']} | "
        f"enabled {dict(r['enabled'])} | 形状 {dict(r['schema_shapes'])}"
    )
    print(
        f"  level 非空 {r['level_nonnull']} | pause {dict(r['pause'])} | "
        f"contract_status {dict(r['contract_status'])} | 占位失配 {r['placeholder_mismatch']}"
    )
    print(
        f"mdo_crash_rate：在场 {c['n_key_present']} / 缺席 {c['n_key_absent']} | "
        f"五层 {dict(layers)} | 未给出规范值的成因 {dict(c['unmeasured_reasons'])}"
    )
    print(
        f"  值非空 {c['n_value_nonnull']}（0 {c['n_zero']} / ≠0 {c['n_nonzero']}，均值 {c['value']['mean']}）| "
        f"空 {c['n_value_null']} | 池化 {pooled['n_crash']}/{pooled['n_pool']} = {pooled['rate']}"
    )
    print(
        f"  暂定池原始值 {raw['n_present']}（0 {raw['n_zero']} / ≠0 {raw['n_nonzero']}，"
        f"池化 {raw['pooled']['n_crash']}/{raw['pooled']['n_pool']} = {raw['pooled']['rate']}）| "
        f"floor=False {c['floor_false']} = 暂定 {c['floor_false_provisional']} + 其它 {c['floor_false_other']}"
    )
    print(
        f"  可评估计数在场 {c['n_evaluability_recorded']} 行（键 {list(MDO_EVALUABILITY_KEYS)}）| "
        f"provisional 标记缺失 {c['provisional_flag_missing']}"
    )

    # 分档恒等式（与测试锁同一口径）。
    assert r["n_key_present"] + r["n_key_absent"] == out["n_rows"]
    assert sum(r["enabled"].values()) == r["n_key_present"] - r["n_non_dict"]
    assert sum(r["schema_shapes"].values()) == r["n_key_present"] - r["n_non_dict"]
    assert sum(r["pause"].values()) == r["n_key_present"] - r["n_non_dict"]
    assert sum(r["contract_status"].values()) == r["n_key_present"] - r["n_non_dict"]
    assert r["level_nonnull"] <= r["enabled"]["enabled_true"]
    assert c["n_key_present"] + c["n_key_absent"] == out["n_rows"]
    assert sum(layers.values()) == c["n_key_present"]
    assert sum(c["unmeasured_reasons"].values()) == sum(layers[layer] for layer in CRASH_UNMEASURED_LAYERS)
    assert c["n_value_nonnull"] + c["n_value_null"] == c["n_key_present"]
    assert c["n_zero"] + c["n_nonzero"] == c["n_value_nonnull"]
    assert pooled["n_unique"] + pooled["n_ambiguous"] + pooled["n_failed"] == c["n_value_nonnull"]
    assert raw["pooled"]["n_unique"] + raw["pooled"]["n_ambiguous"] + raw["pooled"]["n_failed"] == raw["n_present"]
    assert c["floor_false"] == c["floor_false_provisional"] + c["floor_false_other"]
    assert c["floor_false_provisional"] == layers["provisional_pool"]
    assert c["n_evaluability_recorded"] == 0
    assert pooled["n_ambiguous"] == 0 and pooled["n_failed"] == 0
    assert raw["pooled"]["n_ambiguous"] == 0 and raw["pooled"]["n_failed"] == 0

    if (files, out["n_rows"]) != (257, 11197):
        print(f"> 归档已漂移（{files} 份 / {out['n_rows']} 行）：只校验恒等式，登记读数需按新时点重测。")
        return

    shape7 = "approval_action|enabled|factors|pause_requested|reasons|risk_level|risk_score"
    shape6 = "approval_action|enabled|factors|reasons|risk_level|risk_score"
    want = {
        "risk_present": 8864,
        "risk_absent": 2333,
        "enabled_true": 0,
        "enabled_false": 8864,
        "enabled_missing": 0,
        "shape7": 8012,
        "shape6": 852,
        "level_nonnull": 0,
        "pause_false": 8012,
        "pause_absent": 852,
        "pause_other": 0,
        "contract_present": 0,
        "placeholder_mismatch": 0,
        "score_n": 0,
        "crash_present": 4044,
        "crash_absent": 7153,
        "not_run": 2312,
        "material_absent": 122,
        "not_measurable": 986,
        "provisional": 530,
        "measured": 94,
        "value_nonnull": 94,
        "zero": 79,
        "nonzero": 15,
        "value_mean": 0.003978,
        "pooled_unique": 94,
        "pooled_crash": 15,
        "pooled_pool": 3200,
        "pooled_rate": 0.0046875,
        "raw_present": 530,
        "raw_missing": 0,
        "raw_zero": 518,
        "raw_nonzero": 12,
        "raw_crash": 12,
        "raw_pool": 7190,
        "raw_rate": 0.0016689847009735744,
        "floor_false": 1516,
        "floor_provisional": 530,
        "floor_other": 986,
        "provisional_missing": 2434,
        "evaluability": 0,
        "reason_none": 2312,
        "reason_baseline_execution_error": 1,
        "reason_baseline_timeout": 38,
        "reason_no_gold_fixed_material": 6,
        "reason_no_gold_material": 116,
        "reason_test_not_green": 947,
    }
    got = {
        "risk_present": r["n_key_present"],
        "risk_absent": r["n_key_absent"],
        "enabled_true": r["enabled"]["enabled_true"],
        "enabled_false": r["enabled"]["enabled_false"],
        "enabled_missing": r["enabled"]["enabled_missing"],
        "shape7": r["schema_shapes"].get(shape7, 0),
        "shape6": r["schema_shapes"].get(shape6, 0),
        "level_nonnull": r["level_nonnull"],
        "pause_false": r["pause"]["false"],
        "pause_absent": r["pause"]["absent"],
        "pause_other": r["pause"]["other"],
        "contract_present": r["contract_status"]["present"],
        "placeholder_mismatch": r["placeholder_mismatch"],
        "score_n": r["score"]["n"],
        "crash_present": c["n_key_present"],
        "crash_absent": c["n_key_absent"],
        "not_run": layers["not_run"],
        "material_absent": layers["material_absent"],
        "not_measurable": layers["not_measurable"],
        "provisional": layers["provisional_pool"],
        "measured": layers["measured"],
        "value_nonnull": c["n_value_nonnull"],
        "zero": c["n_zero"],
        "nonzero": c["n_nonzero"],
        "value_mean": c["value"]["mean"],
        "pooled_unique": pooled["n_unique"],
        "pooled_crash": pooled["n_crash"],
        "pooled_pool": pooled["n_pool"],
        "pooled_rate": pooled["rate"],
        "raw_present": raw["n_present"],
        "raw_missing": raw["n_missing"],
        "raw_zero": raw["n_zero"],
        "raw_nonzero": raw["n_nonzero"],
        "raw_crash": raw["pooled"]["n_crash"],
        "raw_pool": raw["pooled"]["n_pool"],
        "raw_rate": raw["pooled"]["rate"],
        "floor_false": c["floor_false"],
        "floor_provisional": c["floor_false_provisional"],
        "floor_other": c["floor_false_other"],
        "provisional_missing": c["provisional_flag_missing"],
        "evaluability": c["n_evaluability_recorded"],
        "reason_none": c["unmeasured_reasons"].get("<none>", 0),
        "reason_baseline_execution_error": c["unmeasured_reasons"].get("baseline_execution_error", 0),
        "reason_baseline_timeout": c["unmeasured_reasons"].get("baseline_timeout", 0),
        "reason_no_gold_fixed_material": c["unmeasured_reasons"].get("no_gold_fixed_material", 0),
        "reason_no_gold_material": c["unmeasured_reasons"].get("no_gold_material", 0),
        "reason_test_not_green": c["unmeasured_reasons"].get("test_not_green_on_base(rc=1)", 0),
    }
    drift = {k: (v, got[k]) for k, v in want.items() if got[k] != v}
    assert not drift, drift
    print("> 登记读数逐项一致（BX 手册 §1–§4）。")


def _pinned_batches() -> dict[str, dict]:
    tests = ROOT / "tests" / "test_residual_keys_bx.py"
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


def _reading(rows: list[dict]) -> dict:
    from experiments._residual_keys import residual_keys_stats

    out = residual_keys_stats(rows)
    r, c = out["risk_summary"], out["mdo_crash"]
    return {
        "n_rows": out["n_rows"],
        "risk": {
            "present": r["n_key_present"],
            "absent": r["n_key_absent"],
            "enabled_true": r["enabled"]["enabled_true"],
            "enabled_false": r["enabled"]["enabled_false"],
            "enabled_missing": r["enabled"]["enabled_missing"],
            "shapes": r["schema_shapes"],
            "level_nonnull": r["level_nonnull"],
            "level": r["level"],
            "action": r["action"],
            "score": r["score"],
            "pause": r["pause"],
            "contract_status": r["contract_status"],
            "placeholder_mismatch": r["placeholder_mismatch"],
            "distribution_readable": r["distribution_readable"],
        },
        "crash": {
            "present": c["n_key_present"],
            "absent": c["n_key_absent"],
            "layers": c["layers"],
            "reasons": c["unmeasured_reasons"],
            "value_nonnull": c["n_value_nonnull"],
            "zero": c["n_zero"],
            "nonzero": c["n_nonzero"],
            "value": c["value"],
            "pooled": c["pooled"],
            "raw_present": c["provisional_raw"]["n_present"],
            "raw_zero": c["provisional_raw"]["n_zero"],
            "raw_nonzero": c["provisional_raw"]["n_nonzero"],
            "raw_pooled": c["provisional_raw"]["pooled"],
            "floor_false": c["floor_false"],
            "floor_provisional": c["floor_false_provisional"],
            "floor_other": c["floor_false_other"],
            "provisional_missing": c["provisional_flag_missing"],
            "evaluability": c["n_evaluability_recorded"],
        },
    }


def print_pinned() -> None:
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
        got = _reading(rows)
        drift = {k: (v, got.get(k)) for k, v in want.items() if got.get(k) != v}
        print(f"  {'OK  ' if not drift else 'DRIFT'} {path.name}  {drift or ''}")
        assert not drift, (rel, drift)


def main() -> int:
    ap = argparse.ArgumentParser(description="BX 轮只读普查（残池两键的读侧与分母）")
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
