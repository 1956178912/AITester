#!/usr/bin/env python3
"""BY 轮变异验证：分析集流量账的 41 个锚点 + 1 个中性对照。

纪律（与 BH→BX 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 加星号）必须 0 红。

锚点方向：每一处都是「把 BY 补的记账退回沉默、退回并档、退回同形」：
文件层归层顺序（数据集先于 schema、schema 先于形状）、未登记基线不校验、
读取失败不记层、白名单重复路径、扫描面外不盘点；行层去重（后写覆盖即旧批次
顶替最新、缺 task_id 并进重复、载入行只数唯一行）、字段 None 与可测互换；
报告面（标题、未登记基线行、None ≠ 0、未闭合仍报闭合、扫描面外、混批口径、
PRISMA/Hurlbert、只记账声明）与控制台摘要；以及统计读端的三处接线。
受影响面 = BY 新锁（`tests/test_analysis_flow_by.py`）。

外环（加载器 / 判定端）不在本轮变异范围内：BY 只读，`src/` 零改动，
`_load_batch_file` 与 `_batch_is_m1_schema_complete` 的判定值一处不动。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"

AF = "experiments/_analysis_flow.py"
SA = "experiments/statistical_analysis.py"

BASE_TESTS = ["tests/test_analysis_flow_by.py"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)
BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 文件层归层：顺序 / 缺失标注 / 形状 ─────────────────────────────────
    (
        "F01-dataset-whitelist-disabled",
        AF,
        "        if dataset not in supported_datasets:\n"
        '            name = dataset if isinstance(dataset, str) and dataset else "<缺失>"',
        "        if False:  # mutation: 数据集白名单不再判定\n"
        '            name = dataset if isinstance(dataset, str) and dataset else "<缺失>"',
        [],
    ),
    (
        "F02-empty-dataset-not-labelled-missing",
        AF,
        '            name = dataset if isinstance(dataset, str) and dataset else "<缺失>"',
        '            name = dataset if isinstance(dataset, str) else "<缺失>"  # mutation: 空串不记缺失',
        [],
    ),
    (
        "F03-schema-gate-off",
        AF,
        "        if not allow_schema_mixed and not batch_is_m1_schema_complete(doc):",
        "        if False:  # mutation: 默认口径不再剔除 schema 不完备",
        [],
    ),
    (
        "F04-schema-gate-ignores-flag",
        AF,
        "        if not allow_schema_mixed and not batch_is_m1_schema_complete(doc):",
        "        if not batch_is_m1_schema_complete(doc):  # mutation: 混批旗标被忽略",
        [],
    ),
    (
        "F05-untracked-blocks-validated",
        AF,
        "        for baseline, block in results.items():\n"
        "            if baseline not in tracked_baselines:\n"
        "                continue",
        "        for baseline, block in results.items():\n"
        "            if False:  # mutation: 未登记基线也校验形状\n"
        "                continue",
        [],
    ),
    (
        "F06-non-dict-block-skipped",
        AF,
        '                return "load_error", {"error": f"{baseline} block {type(block).__name__}"}',
        "                continue  # mutation: 非对象基线块按空块跳过",
        [],
    ),
    (
        "F07-non-list-details-skipped",
        AF,
        '                return "load_error", {"error": f"{baseline}.details {type(details).__name__}"}',
        "                continue  # mutation: details 非列表按空表跳过",
        [],
    ),
    (
        "F08-non-dict-row-skipped",
        AF,
        '                    return "load_error", {"error": f"{baseline}.details row {type(row).__name__}"}',
        "                    continue  # mutation: 非对象行跳过",
        [],
    ),
    (
        "F09-results-non-dict-included",
        AF,
        '            return "load_error", {"error": f"results {type(results).__name__}"}',
        '            return "included", {}  # mutation: results 非字典按空结果计入',
        [],
    ),
    (
        "F10-top-level-non-dict-included",
        AF,
        '    if not isinstance(doc, dict):\n        return "load_error", {"error": f"top-level {type(doc).__name__}"}',
        '    if not isinstance(doc, dict):\n        return "included", {}  # mutation: 顶层非对象按空文档计入',
        [],
    ),
    (
        "F11-schema-any-row-counts",
        AF,
        '            if isinstance(row, dict) and row.get("detection_rate") is not None:',
        "            if isinstance(row, dict):  # mutation: 只看行在场不看 detection_rate",
        [],
    ),
    (
        "F12-schema-non-dict-block-complete",
        AF,
        '    for baseline_data in data.get("results", {}).values():\n'
        "        if not isinstance(baseline_data, dict):\n"
        "            continue",
        '    for baseline_data in data.get("results", {}).values():\n'
        "        if not isinstance(baseline_data, dict):\n"
        "            return True  # mutation: 非对象块被当成有 measurement",
        [],
    ),
    (
        "F13-row-counts-non-dict-rows",
        AF,
        "        n = sum(1 for row in details if isinstance(row, dict))",
        "        n = len(details)  # mutation: 非对象行也计行",
        [],
    ),
    # ─── 文件层计数：白名单 / 失败 / 扫描面 / tracked 分账 ────────────────
    (
        "F14-whitelist-dedup-off",
        AF,
        "            if path not in seen:",
        "            if True:  # mutation: 白名单重复路径重复计数",
        [],
    ),
    (
        "F15-read-error-not-counted",
        AF,
        "        except Exception as exc:\n"
        '            status_files["read_error"] += 1\n'
        '            read_errors.append({"file": path.name, "error": type(exc).__name__})',
        "        except Exception as exc:\n"
        '            read_errors.append({"file": path.name, "error": type(exc).__name__})'
        "  # mutation: 失败文件不计层",
        [],
    ),
    (
        "F16-scan-rows-not-counted",
        AF,
        "        scan_rows += rows_all",
        "        scan_rows += 0  # mutation: 扫描行数不计",
        [],
    ),
    (
        "F17-flow-ignores-schema-flag",
        AF,
        "            tracked_baselines=tracked_baselines,\n"
        "            allow_schema_mixed=allow_schema_mixed,\n"
        "        )",
        "            tracked_baselines=tracked_baselines,\n"
        "            allow_schema_mixed=False,  # mutation: 流量账忽略混批旗标\n"
        "        )",
        [],
    ),
    (
        "F18-untracked-rows-counted-tracked",
        AF,
        "                if baseline in tracked_baselines:",
        "                if True:  # mutation: 未登记基线的行也并进 tracked",
        [],
    ),
    (
        "F19-schema-default-counts-all",
        AF,
        "            if allow_schema_mixed and not batch_is_m1_schema_complete(doc):",
        "            if allow_schema_mixed:  # mutation: 默认口径可剔除数按全部已载入计",
        [],
    ),
    (
        "F20-dataset-breakdown-folded",
        AF,
        '            datasets[info["dataset"]] += 1',
        '            datasets["<缺失>"] += 1  # mutation: 数据集分布不再按实际值',
        [],
    ),
    (
        "F21-status-rows-not-counted",
        AF,
        "        status_rows[status] += rows_all",
        "        status_rows[status] += 0  # mutation: 层行数不计",
        [],
    ),
    # ─── 行层：去重 / None / 计数 ─────────────────────────────────────────
    (
        "F22-last-wins-dedup",
        AF,
        "        latest = latest_rows_by_task(rows)",
        '        latest = {row.get("task_id"): row for row in rows}  # mutation: 后写覆盖（旧批次顶替最新）',
        [],
    ),
    (
        "F23-missing-task-id-counted-duplicate",
        AF,
        '        n_duplicates = sum(1 for row in rows if row.get("task_id")) - len(latest)',
        "        n_duplicates = n_rows - len(latest)  # mutation: 缺 task_id 的行算进重复",
        [],
    ),
    (
        "F24-missing-task-id-not-counted",
        AF,
        '        n_no_task_id = sum(1 for row in rows if not row.get("task_id"))',
        "        n_no_task_id = 0  # mutation: 缺 task_id 不记账",
        [],
    ),
    (
        "F25-loaded-rows-only-unique",
        AF,
        "        rows_total += n_rows",
        "        rows_total += len(latest)  # mutation: 载入行只数唯一行",
        [],
    ),
    (
        "F26-measurable-includes-none",
        AF,
        '            per_field[field] = {"none": n_none, "measurable": len(latest) - n_none}',
        '            per_field[field] = {"none": n_none, "measurable": len(latest)}  # mutation: None 也算可测',
        [],
    ),
    (
        "F27-none-and-measurable-swapped",
        AF,
        "            n_none = sum(1 for row in latest.values() if row.get(field) is None)",
        "            n_none = sum(1 for row in latest.values() if row.get(field) is not None)"
        "  # mutation: None 与可测互换",
        [],
    ),
    (
        "F28-archive-non-benchmark-hidden",
        AF,
        '        if not path.name.startswith("benchmark_"):',
        "        if False:  # mutation: 扫描面外的非 benchmark 文件不再盘点",
        [],
    ),
    (
        "F29-archive-non-benchmark-rows-zeroed",
        AF,
        "            non_benchmark_rows += n_rows",
        "            non_benchmark_rows += 0  # mutation: 扫描面外行数不计",
        [],
    ),
    (
        "F41-fields-total-measurable-includes-none",
        AF,
        '            fields_total[field]["measurable"] += len(latest) - n_none',
        '            fields_total[field]["measurable"] += len(latest)  # mutation: 总计可测数也把 None 算进去',
        [],
    ),
    # ─── 控制台摘要 ──────────────────────────────────────────────────────
    (
        "F30-console-drops-schema",
        AF,
        '        f" → 剔除 数据集外 {_fmt(unsupported)} 行、schema {_fmt(schema)} 行、"',
        '        f" → 剔除 数据集外 {_fmt(unsupported)} 行、"  # mutation: 控制台不再点名 schema 层',
        [],
    ),
    (
        "F31-console-collapse-hidden",
        AF,
        "        f\" → 折叠重复 {_fmt(loaded['duplicates'])} 行 → 唯一 {_fmt(loaded['unique'])} 行\"",
        "        f\" → 唯一 {_fmt(loaded['unique'])} 行\"  # mutation: 折叠量不再披露",
        [],
    ),
    # ─── 报告面 ──────────────────────────────────────────────────────────
    (
        "F32-heading-renamed",
        AF,
        '        "### 分析集流量（BY：逐层剔除与去重）",',
        '        "### 分析集流量",  # mutation: 章节名不再区分剔除与去重',
        [],
    ),
    (
        "F33-untracked-row-collapsed",
        AF,
        "        f\"| 基线未登记 | 0 | −{_fmt(untracked_rows)} | {_breakdown(untracked) or '无'} |\",",
        "        f\"| 基线未登记 | 0 | 0 | {_breakdown(untracked) or '无'} |\",  # mutation: 未登记基线行数抹平",
        [],
    ),
    (
        "F34-none-not-zero-phrase-removed",
        AF,
        '            f"| None 在去重后、配对前剔除；**None ≠ 0** |"',
        '            f"| None 在去重后、配对前剔除 |"  # mutation: None 与 0 同形',
        [],
    ),
    (
        "F35-reconciliation-always-closed",
        AF,
        '        + ("两项均闭合。" if reconciles else "**对账未闭合，见下方差异。**"),',
        '        + "两项均闭合。",  # mutation: 未闭合也报闭合',
        [],
    ),
    (
        "F36-archive-footnote-suppressed",
        AF,
        '    if flow["mode"] == "glob" and archive is not None:',
        "    if False:  # mutation: 扫描面外不披露",
        [],
    ),
    (
        "F37-mixed-footnote-suppressed",
        AF,
        '    if flow.get("allow_schema_mixed"):',
        "    if False:  # mutation: 混批口径不点名",
        [],
    ),
    (
        "F38-external-caliber-removed",
        AF,
        '        "> 外部口径（联网核对）：PRISMA 2020 流程图要求逐阶段记录数量与排除理由，且流程图数字"',
        '        "> 逐阶段记录数量与排除理由，且流程图数字"  # mutation: 外部口径来源消失',
        [],
    ),
    (
        "F39-read-only-promise-removed",
        AF,
        '        "> 本表只记账：不改任何判定值、不改 passed / repair / 分母，也不回填归档行。",',
        '        "> 本表为审计视图。",  # mutation: 零改动声明消失',
        [],
    ),
    (
        "F40-layer-order-drops-read-error",
        AF,
        '    "read_error",\n    "load_error",\n)',
        '    "load_error",\n)  # mutation: 读取失败层从闭合集合消失',
        [],
    ),
    # ─── 统计读端接线与对账 ──────────────────────────────────────────────
    (
        "W01-report-section-not-rendered",
        SA,
        "        report_lines.extend(_analysis_flow.render_analysis_flow_lines(_flow))",
        "        _ = _flow  # mutation: 报告面不渲染流量",
        [],
    ),
    (
        "W02-console-line-not-printed",
        SA,
        "    print(_analysis_flow.flow_console_line(_flow))",
        "    pass  # mutation: 控制台不打印流量",
        [],
    ),
    (
        "W03-reconciliation-second-clause-dropped",
        SA,
        '        and flow["included"]["rows_tracked"] == loaded["rows"]',
        "        and True  # mutation: 载入行对账不再比较",
        [],
    ),
    (
        "W04-archive-computed-for-whitelist",
        SA,
        '    flow["archive"] = _analysis_flow.archive_universe(results_dir) if batch_files is None else None',
        '    flow["archive"] = _analysis_flow.archive_universe(results_dir)  # mutation: 白名单也扫全归档',
        [],
    ),
    # ─── 中性对照（仅改 docstring，不动任何判据） ─────────────────────────
    (
        CONTROL,
        AF,
        '"""分析集流量账的单一事实源（BY）。',
        '"""**分析集流量账的单一事实源（BY）。',
        [],
    ),
]


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in BROKER_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BASE_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str, list[str]]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BASE_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_by_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    failed = FAILED_RE.findall(output)
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, len(failed), tail, failed


def precheck() -> bool:
    ok = True
    seen: set[str] = set()
    for name, relpath, old, _new, _ in MUTANTS:
        if name in seen:
            print(f"[{name}] DUPLICATE ANCHOR NAME")
            ok = False
        seen.add(name)
        counts = (ROOT / relpath).read_text(encoding="utf-8").count(old)
        if counts != 1:
            print(f"[{name}] PRECHECK anchor count={counts} in {relpath}")
            ok = False
    print(f"[precheck] 锚点唯一性 {'全部通过' if ok else '有失败'}（{len(MUTANTS)} 个）")
    return ok


def main() -> int:
    if not precheck():
        return 1
    rc, red, tail, _ = run_tests([])
    print(f"[baseline] rc={rc} red={red} collected={collect_count([])}\n{tail}")
    if rc != 0 or red != 0:
        print("BASELINE NOT GREEN — abort")
        return 1

    selected = MUTANTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [m for m in MUTANTS if any(m[0].startswith(w) for w in wanted)]
        print(f"[filter] running {len(selected)} of {len(MUTANTS)}")

    results = []
    for name, relpath, old, new, extra in selected:
        path = ROOT / relpath
        original = path.read_bytes()
        sha_before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR", -1, []))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR", -1, []))
            continue
        expected_collected = collect_count(extra)
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail, failed = run_tests(extra)
            mutated_collected = collect_count(extra)
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != expected_collected:
            print(f"[{name}] COLLECTED DRIFT {expected_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT", red, failed))
            continue
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        killers = [f.rsplit("::", 1)[-1] for f in failed[:4]]
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict} 红名={killers}")
        results.append((name, verdict, red, failed))

    print("\n=== SUMMARY ===")
    for name, verdict, red, _failed in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    survivors = [n for n, v, _r, _f in results if v != "FAILED" and n != CONTROL]
    wrong_control = [n for n, v, _r, _f in results if n == CONTROL and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
