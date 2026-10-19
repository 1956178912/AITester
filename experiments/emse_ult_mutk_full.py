#!/usr/bin/env python3
"""emse_ult_mutk_full.py — ULT 全变异体 cosmic-ray Mut@k（零 LLM，2026-10-15 批次八）。

动机（D3 口径链）：
    ULT 的 Mut@k 实测此前为 ``max_mutants=10`` 截断面（归档
    ``emse_ult_mutk_20261014``）；且批次八勘误：截断保留的是 **uuid4 随机序
    子集**（非确定性样本，见 ``ult_adapter._trim_work_items`` docstring）。
    本件把 ULT 三组（specir / replace / gold）切到 cosmic-ray **全变异体**
    口径（不截断哨兵），使"变异强但缺陷盲"的 ULT 侧证据逐位可复现。
    （ult_adapter 整体超时已改按实测条目数计算——10**9 哨兵不再触发
    PyTime_t 溢出，本脚本依赖该修复方可实跑。）

口径（与 emse_ult_mutk.py 逐项一致，仅 max_mutants 与健全性门不同）：
    - target = task_metadata.fixed；test = generated_test（specir/replace）
      或 gold_tests 包装为 pytest 代码（gold 组）；
    - max_mutants = _FULL_MUTANTS（10**9 哨兵 = 不截断，cosmic-ray 全变异体）；
    - timeout = 120s（ULT 官方口径，timeout 计 killed）；
    - **健全性前置门（批次八新增）**：测试须在正确代码上 30s 内终止且通过
      （rc=0），否则保守跳过（skip_reason=test_nonterminating_on_fixed /
      test_fails_on_fixed，不进 Mut@k 分母）——挂死/在正确代码上失败的测试
      所产出的"击杀"不可归因于变异敏感性（重跑开销亦随同规避）；
    - 保守跳过口径不变（无 fixed / 空测试 / cosmic-ray 不可用）。

零 LLM 纪律：只消费已归档工件；cosmic-ray 变异 + pytest 判定均为确定性
本地执行。
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.emse_ult_mutk import (  # noqa: E402
    _gold_tests_to_pytest_code,
    _load_detail_rows,
)
from experiments.ult_adapter import (  # noqa: E402
    cosmic_ray_config_hash,
    cosmic_ray_version,
    is_cosmic_ray_available,
    ult_mutation_score,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.process_utils import run_with_timeout  # noqa: E402

# 全变异体哨兵：cosmic-ray 生成多少评估多少（不截断）。
_FULL_MUTANTS = 10**9
TIMEOUT_SECONDS = 120
# 健全性前置门的上限：生成测试在正确代码上的终止界限（秒）。
SANITY_TIMEOUT_SECONDS = 30

_PROBE_JSON = "experiments/results/emse_ult_specir_probe_20261014/benchmark_ult_20261014_130937.json"
_LITE46_GLOB = "experiments/results/spec_ab_scale87_20261012/ult_lite46_replace/benchmark_ult_*.json"
_OUT_DIR = _REPO_ROOT / "experiments/results/emse_ult_mutk_full_20261015"

# 组注册表：组名 → （标签、任务源、测试来源）
GROUPS: dict[str, dict[str, str]] = {
    "specir": {"label": "specir_generated", "source": "probe", "test_kind": "generated"},
    "replace": {"label": "replace_generated", "source": "lite46", "test_kind": "generated"},
    "gold": {"label": "gold_upper_bound", "source": "probe", "test_kind": "gold"},
}


def _sanity_gate(fixed_code: str, test_code: str, module_name: str) -> dict[str, Any]:
    """健全性前置门：在**正确代码**上跑一次测试（30s 上限）。

    Returns:
        {"status": "pass" | "fail" | "nonterminate", "rc": int | None, "wall_s": float}
    """
    with tempfile.TemporaryDirectory(prefix="ult_sanity_") as td_s:
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
                timeout=SANITY_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return {"status": "nonterminate", "rc": None, "wall_s": round(time.time() - t0, 1)}
    return {
        "status": "pass" if proc.returncode == 0 else "fail",
        "rc": proc.returncode,
        "wall_s": round(time.time() - t0, 1),
    }


def measure_task(row: dict[str, Any], test_kind: str) -> dict[str, Any]:
    """单任务全变异体 Mut@k（键集合同构；健全性门 + 跳过/失败保守口径）。"""
    task_id = row.get("task_id", "")
    meta = row.get("task_metadata") or {}
    fixed_code = meta.get("fixed") or ""
    function_name = meta.get("function_name") or ""
    if test_kind == "gold":
        test_code = _gold_tests_to_pytest_code(meta.get("gold_tests"), function_name)
        test_source = "gold_tests_wrapped"
    else:
        test_code = row.get("generated_test") or ""
        test_source = "generated_test"
    base: dict[str, Any] = {
        "task_id": task_id,
        "test_source": test_source,
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
    }

    def _skip(reason: str, sanity: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            **base,
            "skipped": True,
            "skip_reason": reason,
            "mutation_score": None,
            "mutants_killed": 0,
            "mutants_total": 0,
            "elapsed_s": 0.0,
            "sanity": sanity,
        }

    if not fixed_code.strip() or not function_name.strip() or not test_code.strip():
        return _skip("no_fixed_or_empty_test")
    if not is_cosmic_ray_available():
        return _skip("cosmic-ray_not_installed")

    sanity = _sanity_gate(fixed_code, test_code, function_name)
    if sanity["status"] != "pass":
        reason = "test_nonterminating_on_fixed" if sanity["status"] == "nonterminate" else "test_fails_on_fixed"
        return _skip(reason, sanity)

    t0 = time.time()
    res = ult_mutation_score(
        target_code=fixed_code,
        test_code=test_code,
        module_name=function_name,
        max_mutants=_FULL_MUTANTS,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    return {
        **base,
        "skipped": res.get("skipped", True),
        "skip_reason": res.get("skip_reason", ""),
        "mutation_score": res.get("mutation_score"),
        "mutants_killed": res.get("mutants_killed", 0),
        "mutants_total": res.get("mutants_total", 0),
        "elapsed_s": round(time.time() - t0, 1),
        "sanity": sanity,
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """池化口径聚合（与 emse_ult_mutk._aggregate 同构 + 健全性门统计）。"""
    measured = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    total_killed = sum(r.get("mutants_killed", 0) for r in measured)
    total_mutants = sum(r.get("mutants_total", 0) for r in measured)
    scores = [r.get("mutation_score") for r in measured if r.get("mutation_score") is not None]
    gate = [r for r in skipped if str(r.get("skip_reason", "")).startswith("test_")]
    return {
        "n_tasks": len(results),
        "n_measured": len(measured),
        "n_skipped": len(skipped),
        "skip_reasons": sorted({r.get("skip_reason", "?") for r in skipped}),
        "n_sanity_gate_excluded": len(gate),
        "mutants_killed": total_killed,
        "mutants_total": total_mutants,
        "pooled_mutation_score": (round(total_killed / total_mutants, 6) if total_mutants > 0 else None),
        "mean_mutation_score": (round(sum(scores) / len(scores), 6) if scores else None),
    }


def _resolve_group_source(spec: dict[str, str]) -> Path | None:
    """解析组任务源路径（probe 固定路径 / lite46 通配取最新 mtime）。"""
    if spec["source"] == "probe":
        path = _REPO_ROOT / _PROBE_JSON
        return path if path.is_file() else None
    candidates = list(_REPO_ROOT.glob(_LITE46_GLOB))
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def _dump(payload: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_path, payload, indent=2, mode=0o644)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--groups",
        default="replace",
        help="逗号分隔的组名（specir | replace | gold；默认 replace——控制单批算力）",
    )
    ap.add_argument("--out", default=str(_OUT_DIR / "MUTK_ULT_FULL.json"), help="结果落盘路径")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不执行")
    args = ap.parse_args(argv)

    if not is_cosmic_ray_available():
        print("[ult-mutk-full] cosmic-ray 不可用——终止（无结果不得伪报）")
        return 1

    group_names = [g.strip() for g in args.groups.split(",") if g.strip()]
    unknown = [g for g in group_names if g not in GROUPS]
    if unknown or not group_names:
        print(f"[ult-mutk-full] 未知组名：{unknown or group_names}（可选：{sorted(GROUPS)}）")
        return 1

    plan = {
        "groups": group_names,
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
        "max_mutants": "full (no truncation)",
        "timeout_seconds": TIMEOUT_SECONDS,
        "sanity_gate_timeout_seconds": SANITY_TIMEOUT_SECONDS,
        "out": str(args.out),
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    out_path = Path(args.out)
    payload: dict[str, Any] = {
        "caliber": "cosmic-ray full mutants (no truncation) + sanity gate (terminates & passes on fixed, 30s)",
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
        "timeout_seconds": TIMEOUT_SECONDS,
        "timeout_counts_as_killed": True,
        "sanity_gate": {
            "timeout_seconds": SANITY_TIMEOUT_SECONDS,
            "criteria": "generated/gold test must terminate AND pass (rc=0) on task_metadata.fixed",
        },
        "groups": [],
    }

    for gname in group_names:
        spec = GROUPS[gname]
        source_path = _resolve_group_source(spec)
        if source_path is None:
            print(f"[ult-mutk-full] {gname}: 任务源未定位（{spec['source']}）——跳过该组")
            payload["groups"].append({"label": spec["label"], "source": None, "note": "任务源未定位——本组 skipped"})
            _dump(payload, out_path)
            continue
        rows = _load_detail_rows(source_path)
        print(
            f"[ult-mutk-full] {gname}（{spec['label']}）：{len(rows)} 任务；源 {source_path.name}；"
            f"全变异体口径 + 健全性门 {SANITY_TIMEOUT_SECONDS}s",
            flush=True,
        )
        results: list[dict[str, Any]] = []
        for index, row in enumerate(rows, 1):
            res = measure_task(row, spec["test_kind"])
            results.append(res)
            if res.get("skipped"):
                print(
                    f"[ult-mutk-full] {gname} {index}/{len(rows)} {res['task_id']}: skipped:{res.get('skip_reason')}",
                    flush=True,
                )
            else:
                print(
                    f"[ult-mutk-full] {gname} {index}/{len(rows)} {res['task_id']}: "
                    f"{res.get('mutation_score')} ({res.get('mutants_killed')}/{res.get('mutants_total')}) "
                    f"{res.get('elapsed_s')}s",
                    flush=True,
                )
            if index % 5 == 0 or index == len(rows):
                group_out = {
                    "label": spec["label"],
                    "source": str(source_path),
                    "test_kind": spec["test_kind"],
                    "aggregate": _aggregate(results),
                    "per_task": results,
                }
                labels = [g.get("label") for g in payload["groups"]]
                if spec["label"] in labels:
                    payload["groups"][labels.index(spec["label"])] = group_out
                else:
                    payload["groups"].append(group_out)
                _dump(payload, out_path)

        agg = _aggregate(results)
        print(
            f"[ult-mutk-full] {gname} 完成：pooled={agg['pooled_mutation_score']} "
            f"({agg['mutants_killed']}/{agg['mutants_total']}, n={agg['n_measured']}, "
            f"skip={agg['n_skipped']} 含健全性门 {agg['n_sanity_gate_excluded']})",
            flush=True,
        )

    print(f"[ult-mutk-full] 工件：{out_path}")
    _dump(payload, out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
