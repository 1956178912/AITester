"""ULT Mut@k 真实基准变异指标复算脚本（cosmic-ray 官方口径，零 LLM 成本）。

背景（EMSE 投稿优化，docs/design/ult_bridge_plan.md §4.3）：
    ULT（UnLeakedTestbench）官方评测口径要求 cosmic-ray 全变异体 + 120s
    超时（击杀 = 原码通过 ∧ 变异码失败；timeout 计 killed，2026-10-13
    裁定）。本脚本对既有 ULT 批次工件中的**生成测试**（LLM 已产出，
    缓存复用）跑 cosmic-ray Mut@k 复算，使 mutation score 主指标在
    真实基准（ULT）上可量化，回应"合成集 mutation_score 0.955 饱和/
    变异体太弱"的审稿人质疑。

口径（与 ult_bridge_plan §4.3 裁定 + 归档报告
    experiments/results/emse_ult_mutk_20261014/MUTK_REPORT.md 一致）：
    - target = task_metadata.fixed（ULT 正确实现；变异体从正确代码生成）；
    - max_mutants = 10（确定性截断面，与自研 AST 变异体口径一致；
      **非** cosmic-ray 全变异体——跨报告引用须带此口径标签）；
    - timeout = 120s（cosmic-ray 官方 ULT 口径，timeout 计 killed）；
    - 配置哈希 = cosmic_ray_config_hash()（全变异体事实 + 版本 + 超时，
      ult_adapter 单一事实源）。

零 LLM 纪律：本脚本只消费**已归档工件**中的 generated_test / gold_tests
字段，不触发任何 LLM 调用；cosmic-ray 变异体生成与 pytest 判定均为
确定性本地执行。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# 项目根（experiments/ 的上级）加入 sys.path，使 ult_adapter 可导入
# （脚本可经 `python experiments/emse_ult_mutk.py` 或测试导入两种方式运行）
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments.ult_adapter import (  # noqa: E402
    cosmic_ray_config_hash,
    cosmic_ray_version,
    is_cosmic_ray_available,
    ult_mutation_score,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402

# 口径常量（与 ult_bridge_plan.md §4.3 裁定一致，测试锁定）
MAX_MUTANTS = 10  # 确定性截断面（与自研 AST 变异体口径一致）
TIMEOUT_SECONDS = 120  # ULT 官方 Cosmic-Ray 口径（timeout 计 killed）

# ULT 批次工件（相对仓库根）
_ULT_PROBE_JSON = "experiments/results/emse_ult_specir_probe_20261014/benchmark_ult_20261014_130937.json"
_ULT_LITE46_JSON = "experiments/results/spec_ab_scale87_20261012/ult_lite46_replace/benchmark_ult_20261012_214028.json"


def _load_detail_rows(path: Path) -> list[dict[str, Any]]:
    """从 ULT 批次 JSON 工件提取 aiter 细节行（task_results.details）。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    details = data.get("results", {}).get("aitester", {}).get("details", [])
    return details if isinstance(details, list) else []


def _gold_tests_to_pytest_code(gold_tests: list[str] | None, function_name: str) -> str:
    """把官方 gold_tests（裸断言片段列表）包装为 pytest 可执行的测试文件。

    ULT 官方 gold_tests_raw 为裸 `assert` 片段（不依赖 pytest 框架）；
    复算时需包装为 `from <module> import <fn>` + `test_<i>` 函数，与
    dataset_ult.py 的 M1 归一化口径一致（见 ult_bridge_plan §3.1）。
    """
    if not gold_tests:
        return ""
    lines = [f"from {function_name} import {function_name}  # noqa: F401", ""]
    for i, raw in enumerate(gold_tests):
        lines.append(f"def test_gold_{i}():")
        for assert_line in raw.splitlines() or [raw]:
            stripped = assert_line.strip()
            if stripped:
                lines.append(f"    {stripped}")
        lines.append("")
    return "\n".join(lines)


def measure_task(row: dict[str, Any], test_code: str) -> dict[str, Any]:
    """对单个 ULT 任务跑 cosmic-ray Mut@k（确定性，零 LLM）。

    Args:
        row: ULT 批次 JSON 的 details 行（含 task_id / task_metadata /
            generated_test 等字段）。
        test_code: 用于变异判定的测试代码（生成测试或 gold 包装测试）。

    Returns:
        结果 dict：task_id / skipped / skip_reason / mutation_score /
        mutants_killed / mutants_total / cosmic_ray_version /
        cosmic_ray_config_hash。保守口径：无 fixed / 无模块 / 空测试 /
        cosmic-ray 不可用 → skipped=True（不进 Mut@k 分母）。
    """
    task_id = row.get("task_id", "")
    meta = row.get("task_metadata") or {}
    fixed_code = meta.get("fixed") or ""
    function_name = meta.get("function_name") or ""
    base = {
        "task_id": task_id,
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
    }

    # 保守跳过分支（不进分母）
    if not (fixed_code or "").strip() or not (function_name or "").strip():
        return {
            **base,
            "skipped": True,
            "skip_reason": "no_fixed_or_module",
            "mutation_score": None,
            "mutants_killed": 0,
            "mutants_total": 0,
        }
    if not (test_code or "").strip():
        return {
            **base,
            "skipped": True,
            "skip_reason": "empty_test",
            "mutation_score": None,
            "mutants_killed": 0,
            "mutants_total": 0,
        }
    if not is_cosmic_ray_available():
        return {
            **base,
            "skipped": True,
            "skip_reason": "cosmic-ray_not_installed",
            "mutation_score": None,
            "mutants_killed": 0,
            "mutants_total": 0,
        }

    res = ult_mutation_score(
        target_code=fixed_code,
        test_code=test_code,
        module_name=function_name,
        max_mutants=MAX_MUTANTS,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    return {
        **base,
        "skipped": res.get("skipped", True),
        "skip_reason": res.get("skip_reason", ""),
        "mutation_score": res.get("mutation_score"),
        "mutants_killed": res.get("mutants_killed", 0),
        "mutants_total": res.get("mutants_total", 0),
    }


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    """池化口径聚合（killed/total 合计 + 任务级均值 + 跳过统计）。

    纪律：pooled_mutation_score = Σkilled / Σtotal（**合计口径**，非均值
    平均）；无可测任务 → None（不得假报 0.0，与 _m1_metrics 保守口径一致）。
    """
    measured = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    total_killed = sum(r.get("mutants_killed", 0) for r in measured)
    total_mutants = sum(r.get("mutants_total", 0) for r in measured)
    scores = [r.get("mutation_score") for r in measured if r.get("mutation_score") is not None]
    return {
        "n_tasks": len(results),
        "n_measured": len(measured),
        "n_skipped": len(skipped),
        "skip_reasons": sorted({r.get("skip_reason", "?") for r in skipped}),
        "mutants_killed": total_killed,
        "mutants_total": total_mutants,
        "pooled_mutation_score": (round(total_killed / total_mutants, 6) if total_mutants > 0 else None),
        "mean_mutation_score": (round(sum(scores) / len(scores), 6) if scores else None),
    }


def run_group(
    path: Path,
    label: str,
    test_kind: str = "generated",
) -> dict[str, Any]:
    """对一个 ULT 批次工件跑 Mut@k 全组复算。

    Args:
        path: 批次 JSON 工件路径。
        label: 组标签（入报告）。
        test_kind: "generated"（用 generated_test 字段）/ "gold"
            （用 gold_tests 包装为 pytest 代码）。

    Returns:
        组级结果 dict（label / source / aggregate / per_task）。
    """
    rows = _load_detail_rows(path)
    per_task: list[dict[str, Any]] = []
    for row in rows:
        if test_kind == "gold":
            meta = row.get("task_metadata") or {}
            test_code = _gold_tests_to_pytest_code(meta.get("gold_tests"), meta.get("function_name", ""))
        else:
            test_code = row.get("generated_test", "") or ""
        per_task.append(measure_task(row, test_code))
    agg = _aggregate(per_task)
    return {
        "label": label,
        "source": str(path),
        "test_kind": test_kind,
        "max_mutants": MAX_MUTANTS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "aggregate": agg,
        "per_task": [
            {
                "task_id": r["task_id"],
                "killed": r.get("mutants_killed", 0),
                "total": r.get("mutants_total", 0),
                "score": r.get("mutation_score"),
                "skipped": r.get("skipped", False),
                "skip_reason": r.get("skip_reason", ""),
            }
            for r in per_task
        ],
    }


def _find_ult_lite46_json(repo_root: Path) -> Path | None:
    """定位 ult_lite46 批次 JSON（通配符匹配，取最新 mtime）。"""
    candidates = list(repo_root.glob(_ULT_LITE46_JSON))
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：复算三组 ULT Mut@k（探针生成 / lite46 生成 / 探针 gold）。"""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--probe-json",
        default=_ULT_PROBE_JSON,
        help="ULT 探针 25 批次 JSON（相对仓库根）",
    )
    ap.add_argument(
        "--lite46-json",
        default=None,
        help="ULT lite46 批次 JSON（相对仓库根；None=通配符自动定位）",
    )
    ap.add_argument(
        "--out",
        default="experiments/results/emse_ult_mutk_20261014/MUTK_RECOMPUTE.json",
        help="复算结果落盘路径（相对仓库根）",
    )
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不执行")
    args = ap.parse_args(argv)

    repo_root = _REPO_ROOT
    probe_path = (repo_root / args.probe_json).resolve()
    lite46_path_arg = args.lite46_json or _find_ult_lite46_json(repo_root)
    lite46_path = (repo_root / lite46_path_arg).resolve() if lite46_path_arg else None

    plan = {
        "probe_json": str(probe_path),
        "lite46_json": str(lite46_path) if lite46_path else None,
        "cosmic_ray_available": is_cosmic_ray_available(),
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
        "max_mutants": MAX_MUTANTS,
        "timeout_seconds": TIMEOUT_SECONDS,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False))
        return 0

    if not is_cosmic_ray_available():
        print("[emse_ult_mutk] cosmic-ray 不可用——按保守口径全组 skipped（不误报 0.0）", file=sys.stderr)

    groups: list[dict[str, Any]] = []
    groups.append(run_group(probe_path, "specir_generated", test_kind="generated"))
    if lite46_path is not None:
        groups.append(run_group(lite46_path, "replace_generated", test_kind="generated"))
    else:
        groups.append(
            {
                "label": "replace_generated",
                "source": None,
                "note": "ult_lite46 批次 JSON 未定位——本组 skipped（任务集不同，描述性证据）",
            }
        )
    groups.append(run_group(probe_path, "gold_upper_bound", test_kind="gold"))

    report = {
        "caliber": plan,
        "groups": groups,
    }
    out_path = (repo_root / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_json(out_path, report, indent=2, mode=0o644)
    print(f"[emse_ult_mutk] 复算完成 → {out_path}")
    for g in groups:
        agg = g.get("aggregate")
        if agg is None:
            print(f"  {g['label']}: {g.get('note', 'n/a')}")
        else:
            print(
                f"  {g['label']}: pooled={agg['pooled_mutation_score']} "
                f"({agg['mutants_killed']}/{agg['mutants_total']}, n={agg['n_measured']})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
