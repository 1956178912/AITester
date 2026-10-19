#!/usr/bin/env python3
"""emse_ult_dfsmoke_accuracy.py — ULT 检出优先冒烟 accuracy 判定（零 LLM）。

对 `plain_llm_df` 冒烟批次工件逐任务做 green_on_fut 判定（与
`emse_test_sanity_audit.py::_run_one` 同方法）：物化 `task_metadata.fixed`
（正确 FUT）+ `generated_test`，在独立 tmp 树 30s 内 pytest，分类
pass / fail / nonterminate / material_missing，并输出 accuracy。

判定口径（预注册 `ULT_DFSMOKE_PREREG_2026-10-17.md` §3）：
    accuracy = pass / (pass + fail + nonterminate)；
    material_missing 单列，不进分母。

用法：
    python experiments/emse_ult_dfsmoke_accuracy.py \
        --benchmark <benchmark_ult_*.json> --arm plain_llm_df \
        --out <ACCURACY_REPORT.json>
"""

from __future__ import annotations

import argparse
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

from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.process_utils import run_with_timeout  # noqa: E402

CAP_SECONDS = 30


def _run_one(module_name: str, fixed_code: str, test_code: str) -> dict[str, Any]:
    """物化并运行一次测试（30s 上限），返回分类记录。"""
    with tempfile.TemporaryDirectory(prefix="dfsmo_") as td_s:
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
    status = "pass" if proc.returncode == 0 else "fail"
    return {"status": status, "rc": proc.returncode, "wall_s": round(time.time() - t0, 1), "tail": tail}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--benchmark", required=True, help="benchmark_ult_*.json 路径")
    ap.add_argument("--arm", default="plain_llm_df", help="结果中的臂名")
    ap.add_argument("--out", required=True, help="ACCURACY_REPORT.json 输出路径")
    args = ap.parse_args()

    data = json.loads(Path(args.benchmark).read_text(encoding="utf-8"))
    rows = data["results"][args.arm]["details"]

    records: list[dict[str, Any]] = []
    for i, row in enumerate(rows, 1):
        meta = row.get("task_metadata") or {}
        fixed = meta.get("fixed") or ""
        module_name = meta.get("function_name") or ""
        test_code = row.get("generated_test") or ""
        rec: dict[str, Any] = {"task_id": row.get("task_id")}
        if not fixed.strip() or not module_name.strip() or not test_code.strip():
            rec.update(status="material_missing", rc=None, wall_s=0.0, tail="")
        else:
            rec.update(_run_one(module_name, fixed, test_code))
        records.append(rec)
        print(
            f"[dfsmo] {i}/{len(rows)} {rec['task_id']}: {rec['status']} "
            f"rc={rec['rc']} {rec['wall_s']}s {rec['tail'][:60]}",
            flush=True,
        )

    n_pass = sum(1 for r in records if r["status"] == "pass")
    n_fail = sum(1 for r in records if r["status"] == "fail")
    n_nonterm = sum(1 for r in records if r["status"] == "nonterminate")
    n_missing = sum(1 for r in records if r["status"] == "material_missing")
    denom = n_pass + n_fail + n_nonterm
    accuracy = round(n_pass / denom, 4) if denom else None

    report = {
        "benchmark": args.benchmark,
        "arm": args.arm,
        "caliber": "green_on_fut（生成套件在 task_metadata.fixed 上 30s 内通过）",
        "counts": {"pass": n_pass, "fail": n_fail, "nonterminate": n_nonterm, "material_missing": n_missing},
        "denominator": denom,
        "accuracy": accuracy,
        "records": records,
    }
    atomic_write_json(args.out, report, indent=2, mode=0o644)
    print(f"\n[dfsmo] accuracy = {accuracy}（{n_pass}/{denom}）; fail={n_fail} nonterm={n_nonterm} missing={n_missing}")
    print(f"[dfsmo] 报告 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
