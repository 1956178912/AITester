#!/usr/bin/env python3
"""论文数字复算薄 CLI（零模型调用）。

两个子命令对应 Appendix A 的两类入口：

- ``aggregate``：运行 ``scripts/tools/results_data_pack_20261111.py``；
  ``--check`` 时先备份已入库聚合，重算后按 JSON 语义比较，再恢复原文件。
- ``swebench-filter``：从 SWE-bench 跑批记录的 provenance 提取 225→217
  的 8 个剔除实例与两条剔除原因，供审稿人逐条核对。

用法：
    python scripts/tools/paper_recompute.py aggregate --check
    python scripts/tools/paper_recompute.py swebench-filter
    python scripts/tools/paper_recompute.py swebench-filter --json

退出码：0 = 全部一致；1 = 复算不一致或证据不完整；2 = 用法/环境错误。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PACK_SCRIPT = ROOT / "scripts" / "tools" / "results_data_pack_20261111.py"
PACK_OUT = ROOT / "experiments" / "results" / "RESULTS_DATA_PACK_20261111.json"
SWE_BENCH_GLOB = "experiments/results/**/benchmark_swebench_*.json"

#: 本地 SWE-bench 池规模与剔除后规模（稿件 §3.5 / Appendix B 的登记值）。
EXPECTED_POOL = 225
EXPECTED_AFTER_FILTER = 217
EXPECTED_SKIPPED = 8


def _json_load(path: Path) -> Any:
    """读取 JSON；失败时抛出带路径的 ``SystemExit``，避免静默跳过证据。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"无法读取 {path}: {type(exc).__name__}: {exc}") from exc


def collect_swebench_filter_evidence(pattern: str = SWE_BENCH_GLOB) -> dict[str, Any]:
    """从全部 SWE-bench 跑批记录提取筛选证据。

    Returns:
        包含 ``records``、``pool``、``after_filter``、``skipped`` 与两类
        剔除清单的字典。全部记录必须给出一致的清单，否则抛 ``SystemExit``。
    """
    records: list[dict[str, Any]] = []
    variants: dict[tuple[tuple[str, ...], tuple[str, ...]], list[str]] = {}

    for raw in sorted(glob.glob(str(ROOT / pattern), recursive=True)):
        path = Path(raw)
        data = _json_load(path)
        prov = data.get("provenance") or {}
        inst = tuple(str(x) for x in (prov.get("strict_skipped_task_ids") or []))
        test = tuple(str(x) for x in (prov.get("strict_skipped_test_task_ids") or []))
        count = prov.get("strict_skipped_count")
        records.append(
            {
                "record": str(path.relative_to(ROOT)),
                "strict_skipped_count": count,
                "strict_skipped_task_ids": list(inst),
                "strict_skipped_test_task_ids": list(test),
            }
        )
        variants.setdefault((inst, test), []).append(str(path.relative_to(ROOT)))

    if not records:
        raise SystemExit(f"未找到 SWE-bench 跑批记录：{pattern}")
    if len(variants) != 1:
        raise SystemExit(f"SWE-bench 剔除清单不一致：{len(variants)} 种变体")

    (inst_ids, test_ids), owners = next(iter(variants.items()))
    skipped = len(inst_ids) + len(test_ids)
    if skipped != EXPECTED_SKIPPED:
        raise SystemExit(f"剔除数 {skipped} ≠ 登记值 {EXPECTED_SKIPPED}")
    if EXPECTED_POOL - skipped != EXPECTED_AFTER_FILTER:
        raise SystemExit(f"{EXPECTED_POOL} - {skipped} ≠ {EXPECTED_AFTER_FILTER}：登记值自相矛盾")

    return {
        "records": len(records),
        "pool": EXPECTED_POOL,
        "after_filter": EXPECTED_AFTER_FILTER,
        "skipped": skipped,
        "instance_code_skipped": list(inst_ids),
        "test_material_skipped": list(test_ids),
        "record_files": owners,
    }


def _run_aggregate() -> None:
    """运行聚合脚本；失败时抛出 ``SystemExit``。"""
    if not PACK_SCRIPT.is_file():
        raise SystemExit(f"缺少聚合脚本：{PACK_SCRIPT}")
    proc = subprocess.run(
        [sys.executable, str(PACK_SCRIPT)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"聚合复算失败（rc={proc.returncode}）：{detail[:500]}")
    if not PACK_OUT.is_file():
        raise SystemExit(f"聚合脚本未写出 {PACK_OUT}")


def cmd_aggregate(args: argparse.Namespace) -> int:
    """执行聚合复算；``--check`` 时与入库件做语义比较并恢复原文件。"""
    if not PACK_OUT.is_file():
        raise SystemExit(f"缺少已入库聚合：{PACK_OUT}")

    if not args.check:
        _run_aggregate()
        pack = _json_load(PACK_OUT)
        print(f"written {PACK_OUT.relative_to(ROOT)} | cells: {len(pack.get('cells', {}))}")
        return 0

    original_bytes = PACK_OUT.read_bytes()
    original_stat = PACK_OUT.stat()
    produced: dict[str, Any] | None = None
    try:
        _run_aggregate()
        produced = _json_load(PACK_OUT)
    finally:
        # 无论复算成功与否都恢复入库件，避免 CLI 改变投稿证据。
        PACK_OUT.write_bytes(original_bytes)
        os.utime(PACK_OUT, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    expected = json.loads(original_bytes.decode("utf-8"))
    if produced == expected:
        print(f"[ok] aggregate 复算与入库件语义一致 | cells: {len(expected.get('cells', {}))}")
        return 0
    print("[FAIL] aggregate 复算与入库件不一致", file=sys.stderr)
    return 1


def cmd_swebench_filter(args: argparse.Namespace) -> int:
    """输出 225→217 筛选证据。"""
    evidence = collect_swebench_filter_evidence()
    if args.json:
        print(json.dumps(evidence, ensure_ascii=False, indent=2))
        return 0

    print(
        f"SWE-bench pool {evidence['pool']} -> {evidence['after_filter']} "
        f"({evidence['skipped']} excluded, {evidence['records']} records)"
    )
    print("  instance_code fallback:", ", ".join(evidence["instance_code_skipped"]))
    print("  no Python test material:", ", ".join(evidence["test_material_skipped"]))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    """一次跑完聚合复算与筛选证据，供投稿前一键核验。"""
    rc = cmd_aggregate(argparse.Namespace(check=True))
    if rc != 0:
        return rc
    return cmd_swebench_filter(argparse.Namespace(json=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="论文数字复算薄 CLI（零模型调用）")
    sub = parser.add_subparsers(dest="command", required=True)

    p_agg = sub.add_parser("aggregate", help="运行 50 格聚合复算")
    p_agg.add_argument(
        "--check",
        action="store_true",
        help="重算后与入库聚合做语义比较，并恢复入库件",
    )
    p_agg.set_defaults(func=cmd_aggregate)

    p_filter = sub.add_parser("swebench-filter", help="输出 225→217 筛选证据")
    p_filter.add_argument("--json", action="store_true", help="输出 JSON")
    p_filter.set_defaults(func=cmd_swebench_filter)

    p_verify = sub.add_parser("verify", help="aggregate --check + swebench-filter")
    p_verify.set_defaults(func=cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
