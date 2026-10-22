#!/usr/bin/env python3
"""BQ 轮（2026-10-22）只读探针：三个 status 通道在实验/报告读侧的读者普查。

背景（BN 轮落盘归位后的剩余半项）：
    BM 轮（2026-10-22）把 `contract_status` 接进实验侧最后一个"写了没人读"的
    消费点（`run_benchmark._build_risk_summary_for_result`），并在登记册写明
    `static_check_status` / `safety_check_status` / `oracle_check_status` /
    `check_status` 四处仍是「写了没人读」。BN 轮（同日）随后把 static/safety/
    oracle 三通道的 status+outcomes 写进结果行两分支与 raw 白名单——**写侧
    闭合，读侧仍为零**：`experiments/` + `scripts/` 没有任何一个**报告面
    行读者**（从 details 行读这四个键的消费者）。BM 给 contract_status 接的
    是生产侧透传（final_state → 结果行），报告面对四个通道一律为零。

三段（全部只读；仓库零写入）：
    A 段  读者普查：字面读点（.get / 下标 / 比较）按 state 读与行读分类 +
          接线普查（build_analysis / render_markdown / run_main_batch 是否
          接上 `_check_leg_measurability`）。改前读数 = 行读 0、未接线。
    B 段  归档取值分布：`experiments/results/**/*.json` 递归统计七个键的
          出现次数（改前读数 = 三通道 0，`contract_status` 0，即 BN 之后
          没有批次跑过；`contract_missing_symbols` 为 BL 之前的历史行）。
    C 段  合成七档栅格：对 `_check_leg_measurability` 灌入七种形状
          （ok / disabled / unavailable / error / null / absent / other），
          核对分档计数与恒等式。助手未实现时打印"改前状态"而非崩溃。

用法：.venv/bin/python scripts/tools/bq_check_leg_probe.py
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

#: BN 轮（2026-10-22）写进结果行两分支的四个 status 通道（raw 白名单另含
#: detection_first_status / edit_intent_status / deterministic_repair_status，
#: 其中 check_status 嵌套在 edit_intent_status 里——raw 侧读者不在本轮范围，按名登记）
CHANNELS = (
    "contract_status",
    "static_check_status",
    "safety_check_status",
    "oracle_check_status",
)
#: 对照组：findings 键，其"为空"正是四通道 status 要限定的对象
CONTROL = ("contract_missing_symbols",)
#: state 侧读取的接收者名（持久化写路径，不是 details 行消费者）
STATE_RECEIVERS = {"final_state", "state", "_post", "st", "_safety_now"}
#: 工具链自引用目录（变异/探针脚本把键名当载荷字符串，不算数据消费者）
TOOLING_DIRS = ("scripts/tools",)


def _py_files() -> list[pathlib.Path]:
    files: list[pathlib.Path] = []
    for base in ("experiments", "scripts"):
        for path in sorted((ROOT / base).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if any(part in ("__pycache__", "results") for part in rel.split("/")):
                continue
            files.append(path)
    return files


def _receiver_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return "<expr>"


def _classify(path: pathlib.Path, key: str) -> dict[str, list[str]]:
    """把一个文件里所有等于 key 的字面量按 AST 上下文分类。"""
    out: dict[str, list[str]] = {"write": [], "state_read": [], "row_read": [], "other": []}
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return out
    rel = path.relative_to(ROOT).as_posix()

    def note(kind: str, node: ast.AST) -> None:
        out[kind].append(f"{rel}:{getattr(node, 'lineno', '?')}")

    def walk(node: ast.AST, in_dict_key: bool, in_compare: bool) -> None:
        if isinstance(node, ast.Constant) and node.value == key:
            if in_dict_key:
                note("write", node)
            elif in_compare:
                note("row_read", node)
            else:
                note("other", node)
            return
        if isinstance(node, ast.Dict):
            # key 位置与 value 位置分开传：dict 键 = 写点，value 里的 .get = 读点
            for key_node, value_node in zip(node.keys, node.values, strict=False):
                if key_node is not None:
                    walk(key_node, in_dict_key=True, in_compare=in_compare)
                if value_node is not None:
                    walk(value_node, in_dict_key=False, in_compare=in_compare)
            return
        if isinstance(node, ast.Compare):
            for child in ast.iter_child_nodes(node):
                walk(child, in_dict_key=in_dict_key, in_compare=True)
            return
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == key
        ):
            # .get(key) 的第一个实参：按接收者分 state 读（持久化写路径）与行读（消费者）
            kind = "state_read" if _receiver_name(node.func.value) in STATE_RECEIVERS else "row_read"
            note(kind, node.args[0])
            return
        for child in ast.iter_child_nodes(node):
            walk(child, in_dict_key=in_dict_key, in_compare=in_compare)

    walk(tree, in_dict_key=False, in_compare=False)
    return out


def section_a() -> None:
    print("=" * 72)
    print("A. 读者普查（experiments/ + scripts/，排除 results/ 与 __pycache__）")
    print("=" * 72)
    files = _py_files()
    print(f"扫描 {len(files)} 个 .py 文件")
    for key in (*CHANNELS, *CONTROL):
        agg: dict[str, list[str]] = {"write": [], "state_read": [], "row_read": [], "other": []}
        for path in files:
            got = _classify(path, key)
            for kind, hits in got.items():
                agg[kind].extend(hits)
        print(f"\n[{key}]")
        print(
            f"    写点(dict-key)={len(agg['write'])}  state读={len(agg['state_read'])}"
            f"  行读={len(agg['row_read'])}  其它={len(agg['other'])}"
        )
        for kind, label in (("row_read", "行读"), ("state_read", "state读"), ("write", "写点")):
            for hit in agg[kind]:
                print(f"    {label}: {hit}")
    # A2：接线普查（新读者以助手形式接线，字面普查数不到，故单列）
    print("\n[A2] 接线普查（_check_leg_measurability）")
    ar = (ROOT / "experiments/analyze_results.py").read_text(encoding="utf-8")
    rmb = (ROOT / "experiments/run_main_batch.py").read_text(encoding="utf-8")
    helper = ROOT / "experiments/analysis_parts/check_leg_analysis.py"
    print(f"    助手模块存在 = {helper.exists()}")
    print(f"    analyze_results import 助手 = {'check_leg_measurability' in ar}")
    print(f"    build_analysis 调用助手 = {'_check_leg_measurability(details)' in ar}")
    print(f"    render_markdown 渲染章节 = {'检查腿可测量性' in ar}")
    print(f"    run_main_batch 摘要行接线 = {'检查腿' in rmb}")


def _iter_result_jsons() -> list[pathlib.Path]:
    base = ROOT / "experiments/results"
    return sorted(p for p in base.rglob("*.json") if p.is_file())


def _count_keys(obj: object, keys: tuple[str, ...], counts: dict[str, int]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                counts[k] += 1
            _count_keys(v, keys, counts)
    elif isinstance(obj, list):
        for item in obj:
            _count_keys(item, keys, counts)


def section_b() -> None:
    print()
    print("=" * 72)
    print("B. 归档取值分布（experiments/results/**/*.json，递归）")
    print("=" * 72)
    files = _iter_result_jsons()
    keys = (*CHANNELS, *CONTROL)
    counts = {k: 0 for k in keys}
    parsed = failed = 0
    failures: dict[str, int] = {}
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            failed += 1
            failures[type(exc).__name__] = failures.get(type(exc).__name__, 0) + 1
            continue
        parsed += 1
        _count_keys(data, keys, counts)
    print(f"扫描文件={len(files)}  可解析={parsed}  解析失败={failed} {failures}")
    for key in keys:
        print(f"    [{key}] 出现={counts[key]}")


def section_c() -> None:
    print()
    print("=" * 72)
    print("C. 合成七档栅格（_check_leg_measurability）")
    print("=" * 72)
    try:
        from experiments.analysis_parts.check_leg_analysis import _check_leg_measurability
    except ImportError:
        print("    助手模块未实现（改前状态）——C 段在接线后复跑")
        return
    rows: list[dict] = []
    for grade in ("ok", "disabled", "unavailable", "error", "null"):
        row: dict = {"task_id": f"t-{grade}", "passed": True}
        for key in CHANNELS:
            row[key] = None if grade == "null" else grade
        rows.append(row)
    rows.append({"task_id": "t-absent", "passed": True})  # 四键全缺席（BN 之前的历史批次）
    other_row: dict = {"task_id": "t-other", "passed": True}
    for key in CHANNELS:
        other_row[key] = "ok"
    other_row["static_check_status"] = "OK"  # 词表外真值（自成一档，不进 ok）
    rows.append(other_row)
    # 混合行：一腿 error、一腿 by-design、一腿缺席——归档里最接近真实的形状
    rows.append(
        {
            "task_id": "t-mixed",
            "passed": True,
            "contract_status": "ok",
            "static_check_status": "error",
            "safety_check_status": "disabled",
        }
    )
    result = _check_leg_measurability(rows)
    n = len(rows)
    print(
        f"    n_rows={result['n_rows']} recorded_rows={result['recorded_rows']}"
        f" rows_any_unmeasurable={result['rows_any_unmeasurable']}"
        f" available={result['available']}"
    )
    for key in CHANNELS:
        ch = result["channels"][key]
        total = sum(ch[g] for g in ("ok", "disabled", "unavailable", "error", "null", "absent", "other"))
        print(
            f"    [{key}] ok={ch['ok']} disabled={ch['disabled']} unavailable={ch['unavailable']}"
            f" error={ch['error']} null={ch['null']} absent={ch['absent']} other={ch['other']}"
            f"  合计={total} other_values={ch['other_values']}"
        )
        assert total == n, f"恒等式破裂：{key}"
    assert result["recorded_rows"] == n - 1, result  # 仅 t-absent 四键全缺席
    assert result["rows_any_unmeasurable"] == 3, result  # t-unavailable / t-error / t-mixed
    print(f"    恒等式全部成立（每通道分档合计 == n_rows={n}）")


def main() -> int:
    section_a()
    section_b()
    section_c()
    return 0


if __name__ == "__main__":
    sys.exit(main())
