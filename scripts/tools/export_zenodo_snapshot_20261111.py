#!/usr/bin/python3
"""导出 Zenodo 版本锁定快照：只含派生判定行，不含原始 trace 或模型转录。

输出目录默认在仓库外（~/Workspace/aitester_zenodo_20261111），不污染工作树。
口径与 scripts/tools/results_data_pack_20261111.py 一致：
- 同一批三目录来源白名单，诊断通道不入；
- 逐行只保留零 LLM 复算所需的数值 / 布尔 / 类别字段，
  剥掉 execution_trace、patch、generated_test、diagnosis、repair_history 等
  原始执行 trace、模型输出与自由文本；
- 保持原文件相对路径与原行顺序，让复算脚本的血统去重与浮点累加顺序不变。

导出后在临时树上真的跑一遍复算脚本，与官方底稿逐字节比对；不一致即中止，
绝不产出一个「看起来能复现」的包。
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path.home() / "Workspace" / "aitester_zenodo_20261111"

# 与 results_data_pack_20261111.py 的 SOURCE_ROOTS 保持一致。
SOURCE_ROOTS = (
    "experiments/results/test_run_20261106T101605Z",
    "experiments/results/rerun_swebench_20261110",
    "experiments/results/rerun_testgeneval_20261110_v5",
)
DIAGNOSTIC_MARKERS = ("/verify/", "/retry6/", "/probe/")

# 与 results_data_pack_20261111.py 的 NUMERIC / BOOL_COUNTS 保持一致。
NUMERIC_KEYS = (
    "coverage",
    "false_fix_rate",
    "detection_rate",
    "llm_suite_detection_rate",
    "mdr",
    "mtr",
    "repair_rate",
    "regression_rate",
    "patch_precision",
    "fl_at_k",
    "localization_mrr",
    "localization_hit_function",
    "localization_hit_function_at_3",
    "test_error_rate",
    "iterations",
    "elapsed_seconds",
)
BOOL_KEYS = (
    "patch_correct",
    "patch_validated",
    "patch_rolled_back",
    "patch_abstained",
    "test_hacking_suspected",
    "self_repair_trap_suspected",
    "flaky_detected",
    "patch_plausible",
    "harness_invalid",
    "test_regenerated_pass_unverified",
    "source_patched_unverified",
    "red_regression_violation",
)
KEEP_FIELDS = frozenset(
    {
        "task_id",
        "repo",
        "passed",
        "harness_invalid",
        "error_category",
        "token_usage",
        *NUMERIC_KEYS,
        *BOOL_KEYS,
    }
)

PACK_SCRIPT = "scripts/tools/results_data_pack_20261111.py"
AGGREGATES = (
    "experiments/results/RESULTS_DATA_PACK_20261111.json",
    "experiments/results/RESULTS_DIGEST_20261111.json",
)
PROVENANCE = (
    "experiments/results/test_run_20261106T101605Z/REPORT.json",
    "experiments/results/test_run_20261106T101605Z/SMOKE_GATE.json",
    "experiments/results/rerun_swebench_20261110/B2_REPORT.json",
    "experiments/results/prompt_artifacts_2026-10-15/PROMPT_ARTIFACTS.json",
)


def official_files() -> list[Path]:
    files: list[Path] = []
    for root in SOURCE_ROOTS:
        base = ROOT / root
        if not base.is_dir():
            raise SystemExit(f"official source root missing: {base}")
        files.extend(Path(f) for f in glob.glob(str(base / "**/llm_sweep/*/INCREMENTAL_RESULTS.jsonl"), recursive=True))
    return sorted(f for f in files if not any(m in str(f) for m in DIAGNOSTIC_MARKERS))


def slim_line(line: str) -> str | None:
    if not line.strip():
        return None
    try:
        row = json.loads(line)
    except json.JSONDecodeError:
        return None
    tid = row.get("task_id")
    if not tid:
        return None
    results = {}
    for arm, payload in (row.get("results") or {}).items():
        if isinstance(payload, dict):
            results[arm] = {k: v for k, v in payload.items() if k in KEEP_FIELDS}
    if not results:
        return None
    return json.dumps({"task_id": tid, "results": results}, ensure_ascii=False)


def verify_in_fresh_tree(tree: Path, official_pack: Path) -> None:
    """在临时树上按 reviewer 的方式复算，逐字节比对官方底稿。"""
    with tempfile.TemporaryDirectory(prefix="aitester_zenodo_verify_") as td:
        clone = Path(td) / "clone"
        shutil.copytree(tree, clone)
        proc = subprocess.run(
            [sys.executable, str(clone / PACK_SCRIPT)],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise SystemExit(f"recompute failed in fresh tree:\n{proc.stdout}\n{proc.stderr}")
        reproduced = clone / AGGREGATES[0]
        if not reproduced.exists():
            raise SystemExit("recompute produced no aggregate in fresh tree")
        a = reproduced.read_bytes()
        b = official_pack.read_bytes()
        if a != b:
            raise SystemExit(
                "FATAL: slim verdict rows do not reproduce the official 50-cell "
                "aggregate byte-for-byte; refusing to export a misleading deposit"
            )
        print(f"[verify] fresh-tree recompute byte-identical ({len(a)} bytes)")
        print(f"[verify] {proc.stdout.strip()}")


def write_text_files(out: Path) -> None:
    (out / "README.md").write_text(
        """# Where Orchestration Pays — replication snapshot (2026-11-11)

This is the version-locked replication package for the manuscript
"Where Orchestration Pays: A Measurement-First Evaluation of LLM Test
Generation Across Five Benchmarks" (submitted to Empirical Software
Engineering). It contains **derived per-task verdict rows only**: no raw
execution traces, no model prompts, no model transcripts, no generated
patches and no generated test code.

## Layout

- `verdict_rows/` — a tree that can be merged into a fresh clone of
  <https://github.com/1956178912/AITester> at its root. It carries the three
  registered batch directories and the zero-LLM recomputation script.
- `aggregates/` — the 50-cell aggregate used by every table in the paper,
  plus the independent digest used for cross-checking.
- `provenance/` — batch report, smoke gate record, SWE-bench rerun report and
  the registered prompt-artifact manifest.
- `INVENTORY.md` — the field-level inventory rule and the exclusion list.
- `zenodo_metadata.json` — deposition metadata for the Zenodo record.
- `SHA256SUMS` — checksums of every shipped file.
- `verify.sh` — one-command reproduction of the published aggregate.

## Verify

```sh
sh verify.sh
```

The script runs the shipped recomputation script inside `verdict_rows/` and
compares its output with `aggregates/RESULTS_DATA_PACK_20261111.json` byte for
byte. It makes **no model calls** and needs only Python 3.

## Counting rules

One latest row per (cell, task identifier) wins (lineage deduplication).
Diagnostic channels (`/verify/`, `/retry6/`, `/probe/`) and any smoke run are
not evidence and are excluded by a source-root whitelist in the shipped
script. `harness_invalid` rows carry no verdict and are reported separately.
Each metric keeps its own observation count; an unobserved metric is never
read as zero. The two model endpoints are a replication pair and are never
pooled.

## Licence

Derived artifacts: CC0-1.0. Code and gate scripts: MIT. Third-party benchmark
data remain under their upstream licences; only derived outputs are here.
""",
        encoding="utf-8",
    )
    (out / "INVENTORY.md").write_text(
        """# Inventory rule

Every shipped JSONL row is a **derived verdict row**. Starting from the raw
batch rows, only the fields required to reproduce the paper's numbers are
kept, in their original file paths and original line order. Keeping the line
order is deliberate: the recomputation adds floating-point metrics by
traversal order, so a reordered deposit could differ in the last decimal
place even when every value is correct.

## Kept fields (per arm payload)

- Identity and verdict: `task_id`, `repo`, `passed`, `harness_invalid`,
  `error_category`.
- Cost: `token_usage` (provider usage counters only).
- Numeric metrics: """
        + ", ".join(f"`{k}`" for k in NUMERIC_KEYS)
        + """.
- Boolean flags: """
        + ", ".join(f"`{k}`" for k in BOOL_KEYS)
        + """.

## Removed fields (exhaustive by policy: anything not listed above)

In particular the deposit contains no `execution_trace`, `patch`,
`generated_test`, `diagnosis`, `repair_history`, `oracle_quality_history`,
`task_metadata`, `*_outcomes`, `*_signals`, `*_verdict`, `*_status` or
`rag_stats` content. These are raw execution traces, model outputs or free
text, and none of them is read by the recomputation chain.

The exclusion is enforced by a whitelist, not by a blacklist: a future field
is absent from the deposit unless someone deliberately adds it here.

## Source roots

"""
        + "\n".join(f"- `{r}`" for r in SOURCE_ROOTS)
        + """

Smoke and temporary output directories (`test_run_*_smoke/`) are never
scanned. Because lineage deduplication takes the latest row for a given cell
and task identifier, an unrestricted recursive scan would let a later smoke
run silently overwrite an archived verdict; the whitelist is the guard.

## Integrity

`SHA256SUMS` covers every shipped file. `verify.sh` reproduces the published
aggregate from `verdict_rows/` and compares it with `aggregates/` byte for
byte. The export itself refuses to finish when that comparison fails.
""",
        encoding="utf-8",
    )
    (out / "verify.sh").write_text(
        """#!/bin/sh
# Zero-LLM reproduction of the published 50-cell aggregate.
set -eu
here=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$here/verdict_rows"
python3 scripts/tools/results_data_pack_20261111.py
cmp experiments/results/RESULTS_DATA_PACK_20261111.json \\
    "$here/aggregates/RESULTS_DATA_PACK_20261111.json"
echo "OK: published 50-cell aggregate reproduced byte-for-byte with zero model calls"
""",
        encoding="utf-8",
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()
    out = args.out.resolve()
    if out == ROOT or ROOT in out.parents:
        raise SystemExit("refusing to write the deposit inside the repository working tree")
    if out.exists():
        shutil.rmtree(out)
    (out / "verdict_rows" / "scripts" / "tools").mkdir(parents=True)
    (out / "aggregates").mkdir()
    (out / "provenance").mkdir()

    files = official_files()
    rows = 0
    for src in files:
        rel = src.relative_to(ROOT)
        dst = out / "verdict_rows" / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(src, encoding="utf-8", errors="replace") as fh, open(dst, "w", encoding="utf-8") as fout:
            for line in fh:
                slim = slim_line(line)
                if slim is not None:
                    fout.write(slim + "\n")
                    rows += 1
    print(f"[export] {len(files)} source files -> {rows} derived verdict rows")

    shutil.copy2(ROOT / PACK_SCRIPT, out / "verdict_rows" / PACK_SCRIPT)
    for rel in AGGREGATES:
        shutil.copy2(ROOT / rel, out / "aggregates" / Path(rel).name)
    for rel in PROVENANCE:
        shutil.copy2(ROOT / rel, out / "provenance" / Path(rel).name)

    write_text_files(out)

    metadata = {
        "metadata": {
            "title": (
                "Replication snapshot for 'Where Orchestration Pays: A "
                "Measurement-First Evaluation of LLM Test Generation Across "
                "Five Benchmarks'"
            ),
            "upload_type": "dataset",
            "access_right": "open",
            "license": "CC0-1.0",
            "publication_date": "2026-11-11",
            "description": (
                "Derived per-task verdict rows and zero-LLM recomputation chain "
                "for a 2-model x 5-arm x 5-benchmark evaluation of LLM test "
                "generation (6,377 attempts, 4,458 judgeable verdicts, 1,919 "
                "harness-invalid exclusions). The deposit contains no raw "
                "execution traces, model prompts, model transcripts, generated "
                "patches or generated tests. See INVENTORY.md and verify.sh."
            ),
            "keywords": [
                "software testing",
                "LLM",
                "test generation",
                "orchestration",
                "false fix",
                "measurement",
                "replication package",
                "EMSE",
            ],
            "creators": [
                {"name": "Wang, Chenyu"},
                {"name": "Wang, Shaopin"},
                {"name": "Lin, Bolun"},
                {"name": "Yang, Jinglin"},
                {"name": "Xu, Tong"},
                {"name": "Yu, Xing"},
                {"name": "Xu, Yue"},
                {"name": "Xu, Da"},
            ],
            "related_identifiers": [
                {
                    "identifier": "https://github.com/1956178912/AITester",
                    "relation": "isSupplementTo",
                    "scheme": "url",
                }
            ],
            "notes": (
                "Version-locked snapshot. A reserved DOI is obtained when the "
                "Zenodo deposition is created and is cited in the published "
                "version of the manuscript. No DOI is fabricated in this file."
            ),
        }
    }
    (out / "zenodo_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    verify_in_fresh_tree(out / "verdict_rows", ROOT / AGGREGATES[0])

    sha_lines = []
    for f in sorted(out.rglob("*")):
        if not f.is_file() or f.name == "SHA256SUMS":
            continue
        if f.name == "RESULTS_DATA_PACK_20261111.json" and f.parent.name == "results":
            continue  # regenerated by verify.sh, not a shipped input
        digest = hashlib.sha256(f.read_bytes()).hexdigest()
        sha_lines.append(f"{digest}  {f.relative_to(out).as_posix()}")
    (out / "SHA256SUMS").write_text("\n".join(sha_lines) + "\n", encoding="utf-8")
    total = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"[export] wrote {out} | {len(sha_lines)} files | {total / 1024 / 1024:.2f} MiB")


if __name__ == "__main__":
    main()
