"""M4 4 臂 QuixBugs specir 扩样跑批（独立 cache namespace，2026-10-14）。

背景（预注册 EMSE_QUIXBUGS_SPECIR_EXPAND_PREREG_2026-10-14.md §2）：
    QuixBugs 本地即完整 Python 子集 50 程序（任务集耗尽），扩样改为
    同任务 × 跨批次新抽样。4 臂设计（每臂 n=50，共 200 任务实例）：
    - A/C：DETECTION_SPEC_MODE=replace + SPEC_IR_ENABLE + SPEC_IR_DSL_ENABLE（完整规格优先）
    - B/D：DETECTION_SPEC_MODE=replace（纯 NL 基线）
    - C/D：A/B 复跑（独立 cache namespace，测跨批次抽样方差）
    跑批前验证 4 臂 provenance.cache_namespace 互异（防 temp=0 缓存命中
    退化为零信息重放）。

执行方式：本脚本调用 run_benchmark.py（click CLI）4 臂（每臂独立
AITESTER_CACHE_NAMESPACE），输出到 out_dir 下的 benchmark_quixbugs_*.json。
零 LLM 分析用 `emse_quixbugs_specir_expand.py --analyze`。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent

# 4 臂 cache namespace（互异，防跨臂缓存命中；与历史批次不冲突）
_CACHE_NAMESPACES = {
    "A": "emse_qbug_specir_expand_A_20261014",
    "B": "emse_qbug_specir_expand_B_20261014",
    "C": "emse_qbug_specir_expand_C_20261014",
    "D": "emse_qbug_specir_expand_D_20261014",
}

# 4 臂参数（预注册 §2；SPEC_EXPR_GRAMMAR_ENABLE 是 DSL 文法开关，A/C 开启）
_ARM_PARAMS: dict[str, dict[str, str]] = {
    "A": {  # 完整规格优先（NL+SpecExpr+z3）
        "DETECTION_SPEC_MODE": "replace",
        "SPEC_IR_ENABLE": "true",
        "SPEC_IR_DSL_ENABLE": "true",
    },
    "B": {  # 纯 NL 规格优先
        "DETECTION_SPEC_MODE": "replace",
    },
    "C": {  # A 复跑（独立 cache namespace）
        "DETECTION_SPEC_MODE": "replace",
        "SPEC_IR_ENABLE": "true",
        "SPEC_IR_DSL_ENABLE": "true",
    },
    "D": {  # B 复跑（独立 cache namespace）
        "DETECTION_SPEC_MODE": "replace",
    },
}


def _verify_cache_namespace_isolation() -> bool:
    """验证 4 臂 cache namespace 互异（防跨臂缓存命中退化）。"""
    names = list(_CACHE_NAMESPACES.values())
    if len(set(names)) != len(names):
        return False
    # 额外检查：与历史批次 namespace 不冲突
    return all(("spec_ir_qb" not in ns) and ("emse_d1_quixbugs" not in ns) for ns in names)


def _run_arm(arm: str, out_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    """执行单臂跑批（run_benchmark.py QuixBugs 50 任务，仅 aiter 基线）。"""
    env = dict(os.environ)
    # 独立 cache namespace（防跨臂命中；run_benchmark 缓存开启时自动设
    # AITESTER_CACHE_NAMESPACE=seed42，此处显式覆盖）
    env["AITESTER_CACHE_NAMESPACE"] = _CACHE_NAMESPACES[arm]
    # 4 臂参数（预注册 §2）
    env.update(_ARM_PARAMS[arm])
    # 仅跑 aiter 基线（预注册主分析是 A vs B 配对，plain_llm/same_agent
    # 不需要，省成本）
    env["AITESTER_LLM_CACHE"] = "1"

    cmd = [
        sys.executable,
        "experiments/run_benchmark.py",
        "--dataset",
        "quixbugs",
        "--baselines",
        "aitester",
        "--output-dir",
        str(out_dir),
        "--seed",
        "42",
    ]
    if dry_run:
        print(f"[M4 dry-run] arm {arm}: " + " ".join(cmd))
        print("  env: " + ", ".join(f"{k}={v}" for k, v in _ARM_PARAMS[arm].items()))
        print(f"  AITESTER_CACHE_NAMESPACE={_CACHE_NAMESPACES[arm]}")
        print("  AITESTER_LLM_CACHE=1")
        return {"arm": arm, "dry_run": True, "cmd": " ".join(cmd)}

    print(f"\n[M4] 跑臂 {arm}（QuixBugs 50 任务，cache namespace={_CACHE_NAMESPACES[arm]}）...")
    t0 = time.time()
    from src.utils.process_utils import run_with_timeout

    proc = run_with_timeout(
        cmd, env=env, cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=3600, logger_name="m4_arm"
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        print(f"[M4] 臂 {arm} 失败（rc={proc.returncode}，{elapsed:.0f}s）：")
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        return {"arm": arm, "dry_run": False, "cmd": " ".join(cmd), "returncode": proc.returncode, "elapsed_s": elapsed}
    print(f"[M4] 臂 {arm} 完成（{elapsed:.0f}s）")
    return {"arm": arm, "dry_run": False, "cmd": " ".join(cmd), "returncode": 0, "elapsed_s": elapsed}


def _find_latest_benchmark_json(out_dir: Path) -> Path | None:
    """找 out_dir 下最新的 benchmark_quixbugs_*.json（每臂跑完由 run_benchmark 生成）。"""
    files = sorted(out_dir.glob("benchmark_quixbugs_*.json"))
    return files[-1] if files else None


def _select_latest_per_arm(out_dir: Path) -> dict[str, Path]:
    """按 cache namespace 臂字母选每臂最新工件（防同臂重跑混淆）。

    2026-10-15 批次七修复：原实现取"最近 4 个文件"——单臂重跑时会把旧臂
    文件挤出窗口或把同臂两次跑批当"重复 namespace"误报。改为按 namespace
    臂字母分组取 mtime 最新（映射逻辑与 emse_quixbugs_specir_expand.
    map_arm_paths 同一实现，经 sys.path 导入复用单一事实源）。
    """
    sys.path.insert(0, str(_REPO_ROOT))
    from experiments.emse_quixbugs_specir_expand import map_arm_paths

    return map_arm_paths(sorted(out_dir.glob("benchmark_quixbugs_*.json")))


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只打印 4 臂配置不执行")
    ap.add_argument(
        "--out-dir",
        default="experiments/results/emse_quixbugs_specir_expand_20261014",
        help="输出目录（4 臂 benchmark_quixbugs_*.json 工件）",
    )
    ap.add_argument("--arms", default="ABCD", help="要跑哪些臂（如 'AB' 先跑 2 臂验证）")
    args = ap.parse_args(argv)

    if not _verify_cache_namespace_isolation():
        print("[M4] ✗ 4 臂 cache namespace 互异验证失败——终止（防跨臂缓存命中退化）")
        return 1
    print("[M4] ✓ 4 臂 cache namespace 互异验证通过")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for arm in args.arms.upper():
        if arm not in _ARM_PARAMS:
            print(f"[M4] 未知臂 {arm}（有效：ABCD）")
            continue
        results.append(_run_arm(arm, out_dir, dry_run=args.dry_run))

    if not args.dry_run:
        # 4 臂 provenance 校验（cache namespace 互异 + 与历史批次不冲突）
        # 2026-10-15 批次七修复：原调用传 --verify-provenance 给没有该 CLI
        # 模式的分析脚本（argparse 必失败 ⇒ C/D 复跑链断裂），且"最近 4 个
        # 文件"选法在单臂重跑时误报。现按 namespace 臂字母选每臂最新工件，
        # 调用修复后的 --verify-provenance 模式。
        arm_paths = _select_latest_per_arm(out_dir)
        analysis_script = _REPO_ROOT / "experiments" / "emse_quixbugs_specir_expand.py"
        if not arm_paths:
            print("[M4] 未找到可判定臂的 benchmark_quixbugs_*.json，跳过 provenance 校验")
        elif analysis_script.is_file():
            from src.utils.process_utils import run_with_timeout

            proc = run_with_timeout(
                [sys.executable, str(analysis_script), "--verify-provenance", *[str(p) for p in arm_paths.values()]],
                cwd=_REPO_ROOT,
                capture_output=True,
                text=True,
                timeout=60,
            )
            print(proc.stdout[-1500:])
            if proc.returncode != 0:
                print(f"[M4] ✗ provenance 校验失败（rc={proc.returncode}）")
                print(proc.stderr[-500:])
                return 1
            print("[M4] ✓ 4 臂 provenance 校验通过")
        else:
            print("[M4] 分析脚本未找到，跳过 provenance 校验")

    # 汇总
    print(f"\n[M4] 完成（{'dry-run' if args.dry_run else '实跑'}）：")
    for r in results:
        status = "ok" if r.get("returncode") == 0 or r.get("dry_run") else f"FAILED(rc={r.get('returncode')})"
        print(f"  臂 {r['arm']}: {status}（{r.get('elapsed_s', 0):.0f}s）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
