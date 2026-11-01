#!/usr/bin/env python3
"""convert_minimal_to_bench.py — 极简生成 jsonl → 判定器所需 benchmark json 形态。

判定器（judge_c8/judge_swebench）读 benchmark_<date>.json 的
results[arm].details[]（task_id/generated_test/token_usage）。本工具把
minimal_gen 的极简 jsonl 聚合转换为该形态（task_id 去重取最后）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-dir", required=True)
    ap.add_argument("--arm", required=True)
    ap.add_argument("--out-dir", required=True, help="benchmark json 落盘目录")
    args = ap.parse_args()

    bd = Path(args.bench_dir)
    merged: dict[str, dict] = {}
    for jf in sorted(bd.rglob("*.jsonl")):
        for line in jf.read_text(encoding="utf-8").splitlines():
            try:
                d = json.loads(line)
                merged[d.get("task_id", f"__{len(merged)}")] = {
                    "task_id": d.get("task_id", ""),
                    "generated_test": d.get("generated_test", ""),
                    "token_usage": d.get("token_usage", {}),
                }
            except Exception as e:
                print(f"[warn] {jf.name} 行解析失败: {e}", file=sys.stderr)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"benchmark_minimal_{stamp}.json"
    doc = {
        "total_tasks": len(merged),
        "results": {
            args.arm: {
                "details": list(merged.values()),
                "harness_invalid_count": 0,
            }
        },
    }
    out.write_text(json.dumps(doc, ensure_ascii=False, allow_nan=False, indent=1), encoding="utf-8")
    print(f"转换完成: {len(merged)} 任务 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
