#!/usr/bin/env python3
"""emse_test_sanity_audit.py — 生成测试/官方测试健全性审计（零 LLM，2026-10-15 批次八）。

背景（批次八测量有效性发现）：
    归档 Mut@k（截断面口径）中包含大量"在正确代码上失败/不终止"的测试
    套件——这类套件的"击杀"是恒红/超时驱动的平凡信号，会把 mutation
    score 系统性抬高（如 ULT replace 组 437/460 → 健全子集 69/90）。
    本审计对三个任务集逐任务运行生成测试与（ULT）官方 gold 测试，
    30s 界限内分类 pass / fail / nonterminate，作为：
    1. 全量 Mut@k 跑批的**健全性前置门**依据（fail/nonterminate →
       保守跳过，见 emse_quixbugs_mutk_full.py / emse_ult_mutk_full.py）；
    2. 稿件披露节的证据工件（测试有效性分类 + 原因样本）。

范围：QuixBugs 50（生成）/ ULT lite46（生成 + gold）/ ULT probe25（生成 + gold）。
零 LLM；只读归档工件；结果写入 experiments/results/emse_test_sanity_20261015/。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from experiments._m1_metrics import _suite_has_effective_pass  # noqa: E402
from experiments.emse_ult_mutk import _gold_tests_to_pytest_code  # noqa: E402
from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.process_utils import run_with_timeout  # noqa: E402

CAP_SECONDS = 30
OUT_DIR = REPO / "experiments/results/emse_test_sanity_20261015"

SETS: list[tuple[str, Path, tuple[str, ...]]] = [
    (
        "quixbugs50",
        REPO / "experiments/results/emse_spec_ir_quixbugs_20261013/benchmark_quixbugs_20261014_005101.json",
        ("generated",),
    ),
    (
        "ult_lite46",
        sorted((REPO / "experiments/results/spec_ab_scale87_20261012/ult_lite46_replace").glob("benchmark_ult_*.json"))[
            0
        ],
        ("generated", "gold"),
    ),
    (
        "ult_probe25",
        REPO / "experiments/results/emse_ult_specir_probe_20261014/benchmark_ult_20261014_130937.json",
        ("generated", "gold"),
    ),
]


def _test_code_for(row: dict[str, Any], kind: str, is_ult: bool) -> tuple[str, str]:
    """返回 (module_name, test_code)；材料缺失时返回 ("", "")。"""
    meta = row.get("task_metadata") or {}
    if is_ult:
        name = meta.get("function_name") or ""
        if kind == "gold":
            return name, _gold_tests_to_pytest_code(meta.get("gold_tests"), name)
        return name, row.get("generated_test") or ""
    name = (row.get("task_id", "").split("__", 1)[-1]) if "__" in row.get("task_id", "") else row.get("task_id", "")
    return name, row.get("generated_test") or ""


def _run_one(module_name: str, fixed_code: str, test_code: str) -> dict[str, Any]:
    """物化并运行一次测试（30s 上限），返回分类记录。"""
    with tempfile.TemporaryDirectory(prefix="sanity_") as td_s:
        td = Path(td_s)
        (td / f"{module_name}.py").write_text(fixed_code, encoding="utf-8")
        tf = f"test_{module_name}.py"
        (td / tf).write_text(test_code, encoding="utf-8")
        t0 = time.time()
        try:
            proc = run_with_timeout(
                [sys.executable, "-m", "pytest", tf, "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=str(td),
                capture_output=True,
                text=True,
                timeout=CAP_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {
                "status": "nonterminate",
                "rc": None,
                "wall_s": round(time.time() - t0, 1),
                "tail": f">{CAP_SECONDS}s",
            }
    tail = ""
    stdout = (proc.stdout or "").strip()
    if stdout:
        tail = stdout.splitlines()[-1][:160]
    # BB（2026-10-21，F03 同型）：rc==0 但无有效通过 ⇒ unverifiable（fail-closed）
    if proc.returncode == 0:
        status = (
            "pass" if _suite_has_effective_pass((proc.stdout or "") + "\n" + (proc.stderr or "")) else "unverifiable"
        )
    else:
        status = "fail"
    return {"status": status, "rc": proc.returncode, "wall_s": round(time.time() - t0, 1), "tail": tail}


def main() -> int:
    records: list[dict[str, Any]] = []
    for set_label, path, kinds in SETS:
        if not Path(path).is_file():
            print(f"[sanity] 任务源缺失：{path}", file=sys.stderr)
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = data["results"]["aitester"]["details"]
        is_ult = set_label.startswith("ult")
        for kind in kinds:
            for i, row in enumerate(rows, 1):
                meta = row.get("task_metadata") or {}
                fixed = meta.get("fixed") or ""
                module_name, test_code = _test_code_for(row, kind, is_ult)
                rec: dict[str, Any] = {
                    "set": set_label,
                    "kind": kind,
                    "task_id": row.get("task_id"),
                }
                if not fixed.strip() or not module_name.strip() or not test_code.strip():
                    rec.update(status="material_missing", rc=None, wall_s=0.0, tail="")
                else:
                    rec.update(_run_one(module_name, fixed, test_code))
                records.append(rec)
                print(
                    f"[sanity] {set_label} {kind} {i}/{len(rows)} {rec['task_id']}: "
                    f"{rec['status']} rc={rec['rc']} {rec['wall_s']}s {rec['tail'][:60]}",
                    flush=True,
                )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "SANITY_AUDIT.json"
    atomic_write_json(out, records, indent=2, mode=0o644)
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    (OUT_DIR / "SHA256SUMS.txt").write_text(f"{sha}  SANITY_AUDIT.json\n", encoding="utf-8")

    # 汇总表（入 README）
    lines = [
        "# 生成测试 / 官方测试健全性审计（2026-10-15 批次八）",
        "",
        "> **用途**：全量 Mut@k 跑批的健全性前置门依据 + 稿件披露节证据。",
        "> 判定：测试在**正确代码**（task_metadata.fixed）上 30s 内运行，",
        "> rc=0 ∧ 有有效通过 → pass；rc=0 但全 skip/xfail/deselect →",
        "> unverifiable（BB 轮：rc==0 不等于有断言执行）；rc≠0 → fail；",
        "> 超时 → nonterminate。",
        "> 口径：pass 集合 = Mut@k 可测任务（fail/nonterminate/unverifiable",
        "> 的击杀为恒红/超时/没跑起来驱动的平凡信号，不可归因于变异敏感性）。",
        "",
        "| 任务集 | 测试 | pass | fail | nonterminate | unverifiable | material_missing | 合计 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for set_label, _, kinds in SETS:
        for kind in kinds:
            sub = [r for r in records if r["set"] == set_label and r["kind"] == kind]
            if not sub:
                continue
            counts = {
                s: sum(1 for r in sub if r["status"] == s)
                for s in ("pass", "fail", "nonterminate", "unverifiable", "material_missing")
            }
            lines.append(
                f"| {set_label} | {kind} | {counts['pass']} | {counts['fail']} | "
                f"{counts['nonterminate']} | {counts['unverifiable']} | {counts['material_missing']} | {len(sub)} |"
            )
    lines.extend(
        [
            "",
            "## 明细",
            "",
            "见 `SANITY_AUDIT.json`（逐任务 status/rc/wall_s/失败摘要 tail）。",
            "",
            "## 复现",
            "",
            "```bash",
            "# 零 LLM：只读归档批次工件 + 本地 pytest 判定",
            "python experiments/emse_test_sanity_audit.py",
            "```",
            "",
        ]
    )
    (OUT_DIR / "README.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"[sanity] 审计完成 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
