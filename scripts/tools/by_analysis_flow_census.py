#!/usr/bin/env python3
"""BY 轮（2026-10-23）只读普查：分析集流量账的接线、全归档读数与具名批次。

背景：
    报告 `## 数据来源` 只列纳入的批次，加载器在到达该清单前已剔除四层
    （扫描面外 / 数据集白名单 / schema 不完备 / 未登记基线），载入后又折叠
    两层（重复 task_id / 字段 None）。BY 为这些层补读侧记账
    （`experiments/_analysis_flow.py` + `statistical_analysis` 报告面 + 控制台
    一行），不改加载器判定、不改归档行。

三段（全部只读；仓库零写入、零 LLM）：
    A 段  接线与只读面：源码级断言（报告面两处调用、流量模块不写文件/不改
          results、层集合与字段集合闭合）。
    B 段  归档读数：全归档跑默认与混批两个口径，打印逐层数字并断言三层
          对账；当归档仍是登记时点（257 份带 results 的 JSON / 11,197 行）时，
          同时断言手册登记的逐项读数。
    C 段  具名批次核对：从 `tests/test_analysis_flow_by.py` 的 `PINNED_BATCHES`
          解析五份冻结批次的逐层读数（AST 字面量），与测试锁同源。

用法：.venv/bin/python scripts/tools/by_analysis_flow_census.py [--segment a|b|c|all]
"""

from __future__ import annotations

import argparse
import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments import _analysis_flow as af  # noqa: E402
from experiments import statistical_analysis as sa  # noqa: E402

SA = ROOT / "experiments/statistical_analysis.py"
AF = ROOT / "experiments/_analysis_flow.py"
TEST = ROOT / "tests/test_analysis_flow_by.py"

TRACKED = frozenset(sa._BASELINES)
SUPPORTED = frozenset(sa._SUPPORTED_DATASETS)
REGISTRATION_ARCHIVE = {"files": 257, "rows": 11_197}


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    return ast.unparse(node)


def _calls_in(node: ast.AST) -> list[str]:
    return [_dotted(sub.func) for sub in ast.walk(node) if isinstance(sub, ast.Call)]


def segment_a() -> bool:
    """接线与只读面：报告面两处调用、流量模块不写。"""
    ok = True
    sa_tree = ast.parse(SA.read_text(encoding="utf-8"))
    af_tree = ast.parse(AF.read_text(encoding="utf-8"))

    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "experiments"
        and any(alias.name == "_analysis_flow" for alias in node.names)
        for node in ast.walk(sa_tree)
    )
    print(f"[A] statistical_analysis 导入 _analysis_flow: {imported}")
    ok &= imported

    defined = any(isinstance(node, ast.FunctionDef) and node.name == "analysis_flow_stats" for node in sa_tree.body)
    print(f"[A] statistical_analysis 定义 analysis_flow_stats: {defined}")
    ok &= defined

    runner = next(
        (node for node in ast.walk(sa_tree) if isinstance(node, ast.FunctionDef) and node.name == "run_all_statistics"),
        None,
    )
    runner_calls = _calls_in(runner) if runner is not None else []
    console = "_analysis_flow.flow_console_line" in runner_calls
    render = "_analysis_flow.render_analysis_flow_lines" in runner_calls
    print(f"[A] run_all_statistics 打印流量行: {console}；报告面渲染: {render}")
    ok &= console and render

    forbidden_calls = {"open", "json.dump", "_load_batch_file"}
    hits = sorted({call for call in _calls_in(af_tree) if call in forbidden_calls or call.endswith(".write_text")})
    print(f"[A] 流量模块写/加载调用（应为空）：{hits}")
    ok &= not hits

    writes_results: list[str] = []
    for node in ast.walk(af_tree):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Subscript):
                    continue
                root = target.value
                while isinstance(root, (ast.Subscript, ast.Attribute)):
                    root = root.value
                if isinstance(root, ast.Name) and root.id == "results":
                    writes_results.append(ast.unparse(target))
    print(f"[A] 流量模块对 results 的写入（应为空）：{writes_results}")
    ok &= not writes_results

    attrs = {node.targets[0].id for node in af_tree.body if isinstance(node, ast.Assign) and len(node.targets) == 1}
    print(f"[A] 层集合闭合：{af.LAYER_ORDER}；字段集合：{af.FLOW_FIELDS}；模块常量：{sorted(attrs)}")
    ok &= af.LAYER_ORDER == (
        "included",
        "unsupported_dataset",
        "schema_incomplete",
        "read_error",
        "load_error",
    )
    ok &= af.FLOW_FIELDS == ("passed", "detection_rate", "repair_rate")
    return bool(ok)


def _flow_report(flow: dict) -> None:
    status = flow["status"]
    print(
        "  扫描 {files:,} 份 / {rows:,} 行 → 数据集外 {u_f} 份 / {u_r:,} 行、"
        "schema {s_f} 份 / {s_r:,} 行、读取/加载失败 {e_f} 份 / {e_r:,} 行、"
        "未登记基线 {x:,} 行 → 载入 {i_f} 份 / {t:,} 行"
        " → 折叠重复 {d:,} 行 → 唯一 {n:,} 行".format(
            files=flow["scan"]["files"],
            rows=flow["scan"]["rows"],
            u_f=status["unsupported_dataset"]["files"],
            u_r=status["unsupported_dataset"]["rows"],
            s_f=status["schema_incomplete"]["files"],
            s_r=status["schema_incomplete"]["rows"],
            e_f=status["read_error"]["files"] + status["load_error"]["files"],
            e_r=status["read_error"]["rows"] + status["load_error"]["rows"],
            x=sum(flow["untracked_baselines"].values()),
            i_f=flow["included"]["files"],
            t=flow["included"]["rows_tracked"],
            d=flow["loaded"]["duplicates"],
            n=flow["loaded"]["unique"],
        )
    )
    print(f"  字段 None / 可测：{flow['loaded']['fields']}")
    print(f"  未登记基线：{flow['untracked_baselines']}")
    print(f"  数据集分布：{flow['datasets']}")
    print(f"  对账闭合：{flow['reconciles']}")


def segment_b() -> bool:
    """全归档读数：默认与混批两个口径 + 三层对账。"""
    archive = af.archive_universe("experiments/results")
    print(f"[B] 全归档带 results 的 JSON：{archive}")
    data, sources = sa.load_experiment_results_with_sources("experiments/results")
    flow = sa.analysis_flow_stats(data, "experiments/results")
    mixed_data, mixed_sources = sa.load_experiment_results_with_sources("experiments/results", allow_schema_mixed=True)
    mixed = sa.analysis_flow_stats(mixed_data, "experiments/results", allow_schema_mixed=True)
    print(f"[B] 默认口径（{len(sources)} 份纳入）：")
    _flow_report(flow)
    print(f"[B] 混批口径（{len(mixed_sources)} 份纳入）：")
    _flow_report(mixed)

    ok = flow["reconciles"] and mixed["reconciles"]
    ok &= flow["included"]["files"] == len(sources)
    ok &= flow["included"]["rows_tracked"] == sum(len(rows) for rows in data.values())
    ok &= mixed["included"]["files"] == len(mixed_sources)
    ok &= mixed["included"]["rows_tracked"] == sum(len(rows) for rows in mixed_data.values())

    if archive["files"] == REGISTRATION_ARCHIVE["files"] and archive["rows"] == REGISTRATION_ARCHIVE["rows"]:
        expected_default = {
            "scan_files": 246,
            "scan_rows": 10_659,
            "unsupported_files": 77,
            "unsupported_rows": 886,
            "schema_files": 59,
            "schema_rows": 2_463,
            "included_files": 110,
            "included_rows_all": 7_310,
            "included_rows_tracked": 7_010,
            "loaded_rows": 7_010,
            "duplicates": 6_449,
            "unique": 561,
            "untracked_rows": 300,
            "none_detection": 45,
            "none_repair": 52,
            "none_passed": 0,
            "archive_non_benchmark_files": 13,
            "archive_non_benchmark_rows": 538,
        }
        actual_default = {
            "scan_files": flow["scan"]["files"],
            "scan_rows": flow["scan"]["rows"],
            "unsupported_files": flow["status"]["unsupported_dataset"]["files"],
            "unsupported_rows": flow["status"]["unsupported_dataset"]["rows"],
            "schema_files": flow["status"]["schema_incomplete"]["files"],
            "schema_rows": flow["status"]["schema_incomplete"]["rows"],
            "included_files": flow["included"]["files"],
            "included_rows_all": flow["included"]["rows_all"],
            "included_rows_tracked": flow["included"]["rows_tracked"],
            "loaded_rows": flow["loaded"]["rows"],
            "duplicates": flow["loaded"]["duplicates"],
            "unique": flow["loaded"]["unique"],
            "untracked_rows": sum(flow["untracked_baselines"].values()),
            "none_detection": flow["loaded"]["fields"]["detection_rate"]["none"],
            "none_repair": flow["loaded"]["fields"]["repair_rate"]["none"],
            "none_passed": flow["loaded"]["fields"]["passed"]["none"],
            "archive_non_benchmark_files": flow["archive"]["non_benchmark_files"],
            "archive_non_benchmark_rows": flow["archive"]["non_benchmark_rows"],
        }
        expected_mixed = {
            "included_files": 169,
            "loaded_rows": 9_473,
            "duplicates": 8_494,
            "unique": 979,
            "schema_if_default_files": 59,
            "schema_if_default_rows": 2_463,
        }
        actual_mixed = {
            "included_files": mixed["included"]["files"],
            "loaded_rows": mixed["loaded"]["rows"],
            "duplicates": mixed["loaded"]["duplicates"],
            "unique": mixed["loaded"]["unique"],
            "schema_if_default_files": mixed["schema_incomplete_if_default"]["files"],
            "schema_if_default_rows": mixed["schema_incomplete_if_default"]["rows"],
        }
        for label, expected, actual in (
            ("默认", expected_default, actual_default),
            ("混批", expected_mixed, actual_mixed),
        ):
            if expected != actual:
                print(f"[B] {label}口径与登记读数不符：")
                print(f"    期望 {expected}")
                print(f"    实测 {actual}")
                ok = False
        print("[B] 归档仍为登记时点：逐项读数与手册一致" if ok else "[B] 归档读数与登记不一致")
    else:
        print("[B] 归档已漂移——只断言对账闭合，逐项读数不做登记时点断言")
    return bool(ok)


def _pinned() -> dict:
    tree = ast.parse(TEST.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "PINNED_BATCHES":
            return ast.literal_eval(node.value)
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "PINNED_BATCHES" for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError("测试文件里没有 PINNED_BATCHES")


def segment_c() -> bool:
    """具名冻结批次：逐层读数与测试锁同源。"""
    ok = True
    pinned = _pinned()
    print(f"[C] 具名批次 {len(pinned)} 份")
    for rel, expected in pinned.items():
        doc = json.loads((ROOT / rel).read_text(encoding="utf-8"))
        layer, info = af.classify_document(
            doc,
            supported_datasets=SUPPORTED,
            tracked_baselines=TRACKED,
            allow_schema_mixed=False,
        )
        rows, per_baseline = af._row_counts(doc)
        tracked_rows = sum(v for b, v in per_baseline.items() if b in TRACKED)
        untracked = {b: v for b, v in per_baseline.items() if b not in TRACKED}
        loaded: dict[str, list[dict]] = {baseline: [] for baseline in sa._BASELINES}
        accepted = sa._load_batch_file(loaded, ROOT / rel)
        observed = {
            "layer": layer,
            "info": info,
            "rows": rows,
            "per_baseline": per_baseline,
            "tracked_rows": tracked_rows,
            "untracked": untracked,
        }
        if accepted:
            flow = af.loaded_flow(loaded)
            observed["unique"] = {b: v["unique"] for b, v in flow["per_baseline"].items() if v["rows"]}
            observed["none"] = {
                b: {f: v["fields"][f]["none"] for f in af.FLOW_FIELDS}
                for b, v in flow["per_baseline"].items()
                if v["rows"]
            }
        else:
            observed["unique"] = {}
            observed["none"] = {}
        mismatches = {
            key: (expected.get(key), observed.get(key)) for key in expected if expected.get(key) != observed.get(key)
        }
        print(f"  {'OK' if not mismatches else 'MISMATCH'} {rel} layer={layer} rows={rows}")
        if mismatches:
            for key, (want, got) in mismatches.items():
                print(f"    {key}: 期望 {want!r} / 实测 {got!r}")
            ok = False
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="BY 分析集流量账只读普查")
    parser.add_argument("--segment", choices=("a", "b", "c", "all"), default="all")
    args = parser.parse_args()
    ok = True
    if args.segment in {"a", "all"}:
        ok &= segment_a()
    if args.segment in {"b", "all"}:
        ok &= segment_b()
    if args.segment in {"c", "all"}:
        ok &= segment_c()
    print(f"\n[BY census] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
