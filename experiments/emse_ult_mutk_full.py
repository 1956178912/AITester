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
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from experiments._m1_metrics import _suite_has_effective_pass  # noqa: E402
from experiments.emse_ult_mutk import (  # noqa: E402
    _gold_tests_to_pytest_code,
)
from experiments.ult_adapter import (  # noqa: E402
    cosmic_ray_config_hash,
    cosmic_ray_version,
    is_cosmic_ray_available,
    ult_mutation_score,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.process_utils import nested_pytest_env, run_with_timeout  # noqa: E402

# 全变异体哨兵：cosmic-ray 生成多少评估多少（不截断）。
_FULL_MUTANTS = 10**9
TIMEOUT_SECONDS = 120
# 健全性前置门的上限：生成测试在正确代码上的终止界限（秒）。
SANITY_TIMEOUT_SECONDS = 120

_PROBE_JSON = "experiments/results/emse_ult_specir_probe_20261014/benchmark_ult_20261014_130937.json"
_LITE46_GLOB = "experiments/results/spec_ab_scale87_*/ult_lite46_replace/benchmark_ult_*.json"
_OUT_DIR = _REPO_ROOT / "experiments/results/emse_ult_mutk_full_20261015"

# 组注册表：组名 → （标签、任务源、测试来源）
GROUPS: dict[str, dict[str, str]] = {
    "specir": {"label": "specir_generated", "source": "probe", "test_kind": "generated"},
    "replace": {"label": "replace_generated", "source": "lite46", "test_kind": "generated"},
    "gold": {"label": "gold_upper_bound", "source": "probe", "test_kind": "gold"},
}


def _sanity_gate(fixed_code: str, test_code: str, module_name: str) -> dict[str, Any]:
    """健全性前置门：在**正确代码**上跑一次测试（120s 上限）。

    Returns:
        {"status": "pass" | "fail" | "nonterminate" | "unverifiable", "rc": int | None, "wall_s": float}
    """
    with tempfile.TemporaryDirectory(prefix="ult_sanity_") as td_s:
        td = Path(td_s)
        (td / f"{module_name}.py").write_text(fixed_code, encoding="utf-8")
        tf = f"test_{module_name}.py"
        (td / tf).write_text(test_code, encoding="utf-8")
        t0 = time.time()
        try:
            # PYTEST_DISABLE_PLUGIN_AUTOLOAD（2026-10-29）：主仓 venv 的某插件
            # autoload 在 pytest 收尾时挂死（测试 0.1s 跑完、进程挂 121s 被超时
            # 杀——96 流下 Mut@k 分母全灭的终版根因）。sanity 的单文件物化
            # 不需要任何插件，禁 autoload 后 rc=0 wall=0.1s（实测对照）。
            # nested_pytest_env（2026-10-30，B1 批）：`{**os.environ, ...}` 会把
            # 宿主 PYTEST_PLUGINS/PYTEST_ADDOPTS 与凭证整体带进嵌套 pytest
            # （test_nested_pytest_env_convergence 抓到的 H2 缺陷形态）——改走
            # 仓内统一净环境构造器，禁 autoload 作为显式 override 保留。
            proc = run_with_timeout(
                [sys.executable, "-m", "pytest", tf, "-q", "--no-header", "-p", "no:cacheprovider"],
                cwd=str(td),
                capture_output=True,
                text=True,
                timeout=SANITY_TIMEOUT_SECONDS,
                env=nested_pytest_env(PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"),
            )
        except subprocess.TimeoutExpired:
            return {"status": "nonterminate", "rc": None, "wall_s": round(time.time() - t0, 1)}
        # 口径修正（2026-10-29）：run_with_timeout 超时终止返回 rc=-9（SIGKILL）
        # 且**不抛 TimeoutExpired**——rc=-9 是"没跑完"，按 nonterminate 归因，
        # 不得落入 rc!=0 的 fail 分支（96 流并发下 pytest 启动超 30s 曾把全部
        # 任务误判 test_fails_on_fixed ⇒ Mut@k 分母全灭——MEASUREMENT_INTEGRITY
        # §48"无证据的数字"同族）。
        if proc.returncode == -9:
            return {"status": "nonterminate", "rc": proc.returncode, "wall_s": round(time.time() - t0, 1)}
    # BB（2026-10-21，F03 同型）：rc==0 但无有效通过 ⇒ unverifiable（fail-closed）
    return {
        "status": "pass"
        if proc.returncode == 0 and _suite_has_effective_pass((proc.stdout or "") + "\n" + (proc.stderr or ""))
        else ("unverifiable" if proc.returncode == 0 else "fail"),
        "rc": proc.returncode,
        "wall_s": round(time.time() - t0, 1),
    }


def measure_task(row: dict[str, Any], test_kind: str, sanity: dict[str, Any] | None = None) -> dict[str, Any]:
    """单任务全变异体 Mut@k（键集合同构；健全性门 + 跳过/失败保守口径）。

    sanity 参数（D3 加速，2026-10-29）：调用方已并行预筛健全性门时传入其
    结果，本函数跳过重复 sanity 直达 exec（两阶段并行口径）；None = 历史
    单任务口径（内部自跑 sanity）。
    """
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

    if sanity is None:
        sanity = _sanity_gate(fixed_code, test_code, function_name)
    if sanity["status"] != "pass":
        # BB（2026-10-21，F03 同型）：unverifiable（rc==0 但无有效通过）
        # 与 fail 同样阻断测量——不得把"没跑起来"当成"在 fixed 上通过"。
        reason = {
            "nonterminate": "test_nonterminating_on_fixed",
            "unverifiable": "test_no_effective_pass_on_fixed",
        }.get(sanity["status"], "test_fails_on_fixed")
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


def _load_rows_any_arm(path: Path) -> tuple[list[dict[str, Any]], str]:
    """加载 detail 行：优先 aitester 臂，缺失（如 2026-10-29 df 单臂批）则取
    第一个有 details 的臂——返回 (rows, arm 名)。零行返回 ([], "")."""
    data = json.loads(path.read_text(encoding="utf-8"))
    results = data.get("results") or {}
    for arm in ("aitester", "plain_llm_df", "plain_llm"):
        det = (results.get(arm) or {}).get("details")
        if isinstance(det, list) and det:
            return det, arm
    return [], ""


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
    ap.add_argument(
        "--source",
        default=None,
        help="自定义任务源（benchmark_*.json 路径；与 --groups 一起给出时覆盖该组源——"
        "供新语料分片并发复用同口径，2026-10-29 ULT 全量 df 臂语料）",
    )
    ap.add_argument(
        "--shard",
        default=None,
        help="分片 'i/N'（1 起始）——只处理 tasks 的第 i 片（并发多实例用，0 填充落盘互不覆盖）",
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
        spec = dict(GROUPS[gname])
        source_path = _resolve_group_source(spec)
        if args.source:
            # 自定义源覆盖（分片并发口径）：组标签加 shard 后缀避免互写
            source_path = Path(args.source)
            if args.shard:
                spec["label"] = f"{spec['label']}_shard{args.shard.split('/')[0]}"
        if source_path is None:
            print(f"[ult-mutk-full] {gname}: 任务源未定位（{spec['source']}）——跳过该组")
            payload["groups"].append({"label": spec["label"], "source": None, "note": "任务源未定位——本组 skipped"})
            _dump(payload, out_path)
            continue
        rows, loaded_arm = _load_rows_any_arm(source_path)
        if args.shard:
            shard_i, shard_n = (int(x) for x in args.shard.split("/"))
            rows = rows[shard_i - 1 :: shard_n]  # 1 起始：第 i 片 = 每隔 N 取一个（均匀分片）
        # D3 加速两级（2026-10-29）：健全性门并行预筛——fail 任务的 30s 超时
        # 等待是串行口径的最大空转源。AITESTER_MUTK_SANITY_THREADS>1 时先
        # 线程池并行预筛全部任务，pass 的任务再串行进 exec（http worker 并行
        # 变异体）。默认 1 = 历史串行口径。gold 组（test_code 包装口径不同）
        # 不走预筛。
        sanity_threads = int(os.environ.get("AITESTER_MUTK_SANITY_THREADS", "1"))
        sanity_map: dict[int, dict[str, Any]] = {}
        if sanity_threads > 1 and spec["test_kind"] == "generated":
            from concurrent.futures import ThreadPoolExecutor

            def _sanity_of(row: dict[str, Any]) -> tuple[int, dict[str, Any]]:
                meta = row.get("task_metadata") or {}
                s = _sanity_gate(
                    meta.get("fixed") or "", row.get("generated_test") or "", meta.get("function_name") or ""
                )
                return id(row), s

            with ThreadPoolExecutor(max_workers=sanity_threads) as pool:
                sanity_map = dict(pool.map(_sanity_of, rows))
            n_pass = sum(1 for s in sanity_map.values() if s["status"] == "pass")
            print(
                f"[ult-mutk-full] {gname} 健全性门预筛完成：{n_pass}/{len(rows)} 通过（{sanity_threads} 线程）",
                flush=True,
            )
        print(
            f"[ult-mutk-full] {gname}（{spec['label']}）：{len(rows)} 任务（臂={loaded_arm or '空'}）；源 {source_path.name}；"
            f"全变异体口径 + 健全性门 {SANITY_TIMEOUT_SECONDS}s",
            flush=True,
        )
        if not rows:
            payload["groups"].append(
                {"label": spec["label"], "source": str(source_path), "note": "任务源零行——本组 skipped"}
            )
            _dump(payload, out_path)
            continue
        results: list[dict[str, Any]] = []
        for index, row in enumerate(rows, 1):
            res = measure_task(row, spec["test_kind"], sanity=sanity_map.get(id(row)))
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
