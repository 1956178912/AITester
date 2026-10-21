#!/usr/bin/env python3
"""emse_quixbugs_mutk_full.py — QuixBugs **全变异体** cosmic-ray Mut@k（零 LLM，2026-10-15 批次八）。

动机（D3 口径链的最后一环）：
    ULT/QuixBugs 的 Mut@k 实测此前均为 `max_mutants=10` 截断面（引用须带
    标签，见 docs/design/ult_bridge_plan.md §4.3 与分层叙事 §3）；批次八
    勘误确认该截断保留的是 **uuid4 随机序子集**（非确定性样本）。本件把
    QuixBugs 这一**真实基准**切到 cosmic-ray 全变异体口径（与 ULT 官方
    "不设 operators 过滤 = 全变异体"一致），截断面标签与抽样不确定性在该
    基准上可一并摘除；ULT 3,909 任务的全量仍属 6 周量级（T-07 原范围），
    不在本件（lite46 全量另件 emse_ult_mutk_full.py）。

口径（与批次五 QuixBugs 截断面跑批逐项一致，仅 max_mutants 与健全性门不同）：
    - target = task_metadata.fixed；test_code = row.generated_test；
    - max_mutants = _FULL（10**9 哨兵 = 不截断，cosmic-ray 全变异体）；
      （ult_adapter 整体超时已改按实测条目数计算——哨兵不再触发
      PyTime_t 溢出，本脚本依赖该修复方可实跑。）
    - timeout = 120s（ULT 官方口径，timeout 计 killed）；
    - **健全性前置门（批次八新增）**：生成测试须在正确代码上 30s 内终止
      且通过（rc=0），否则保守跳过（skip_reason=test_nonterminating_on_fixed /
      test_fails_on_fixed，不进 Mut@k 分母）——挂死/在正确代码上失败
      （如 `*_test` 程序变体的相对导入收集错误）的测试所产出的"击杀"
      不可归因于变异敏感性；
    - 保守跳过口径不变（无 fixed / 空 test / cosmic-ray 不可用）。

零 LLM 纪律：只消费已归档工件；cosmic-ray 变异 + pytest 判定均为确定性
本地执行。输入工件与 emse_quixbugs_mutk.py（截断面版）同源。
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

from experiments._m1_metrics import _suite_has_effective_pass  # noqa: E402
from experiments.ult_adapter import (  # noqa: E402
    cosmic_ray_config_hash,
    cosmic_ray_version,
    is_cosmic_ray_available,
    ult_mutation_score,
)
from src.utils.atomic_io import atomic_write_json  # noqa: E402
from src.utils.process_utils import run_with_timeout  # noqa: E402

# 全变异体哨兵：cosmic-ray 生成多少评估多少（不再截断面）。
# ult_mutation_score 的 max_mutants 语义是"上限"，10**9 在实际程序规模下
# 等价于不设上限；配置哈希随工件透出（含 cosmic-ray 版本）。
_FULL_MUTANTS = 10**9
TIMEOUT_SECONDS = 120
# 健全性前置门的上限：生成测试在正确代码上的终止界限（秒）。
SANITY_TIMEOUT_SECONDS = 30

_INPUT_JSON = Path("experiments/results/emse_spec_ir_quixbugs_20261013/benchmark_quixbugs_20261014_005101.json")
_OUT_DIR = _REPO_ROOT / "experiments/results/emse_quixbugs_mutk_full_20261015"


def _sanity_gate(fixed_code: str, test_code: str, module_name: str) -> dict[str, Any]:
    """健全性前置门：在**正确代码**上跑一次测试（30s 上限）。

    Returns:
        {"status": "pass" | "fail" | "nonterminate", "rc": int | None, "wall_s": float}
    """
    with tempfile.TemporaryDirectory(prefix="qb_sanity_") as td_s:
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
    # BB（2026-10-21，F03 同型）：rc==0 但无有效通过 ⇒ unverifiable（fail-closed）
    return {
        "status": "pass"
        if proc.returncode == 0 and _suite_has_effective_pass((proc.stdout or "") + "\n" + (proc.stderr or ""))
        else ("unverifiable" if proc.returncode == 0 else "fail"),
        "rc": proc.returncode,
        "wall_s": round(time.time() - t0, 1),
    }


def measure_task(row: dict[str, Any]) -> dict[str, Any]:
    """单任务全变异体 Mut@k（健全性门 + 跳过/失败保守口径同截断面版）。"""
    task_id = row.get("task_id", "")
    meta = row.get("task_metadata") or {}
    fixed_code = meta.get("fixed") or ""
    test_code = row.get("generated_test") or ""
    # 模块名与截断面版同口径：QuixBugs 程序文件即模块（task_id 去数据集前缀）
    module_name = task_id.split("__", 1)[-1] if "__" in task_id else task_id
    base: dict[str, Any] = {
        "task_id": task_id,
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

    if not fixed_code or not test_code or not module_name:
        return _skip("no_fixed_or_empty_test")
    if not is_cosmic_ray_available():
        return _skip("cosmic-ray_not_installed")
    sanity = _sanity_gate(fixed_code, test_code, module_name)
    if sanity["status"] != "pass":
        # BB（2026-10-21，F03 同型）：unverifiable（rc==0 但无有效通过）
        # 与 fail 同样阻断测量——不得把"没跑起来"当成"在 fixed 上通过"。
        reason = {
            "nonterminate": "test_nonterminating_on_fixed",
            "unverifiable": "test_no_effective_pass_on_fixed",
        }.get(sanity["status"], "test_fails_on_fixed")
        return _skip(reason, sanity)
    t0 = time.time()
    result = ult_mutation_score(
        fixed_code,
        test_code,
        module_name,
        max_mutants=_FULL_MUTANTS,
        timeout_seconds=TIMEOUT_SECONDS,
    )
    result["task_id"] = task_id
    result["elapsed_s"] = round(time.time() - t0, 1)
    result["sanity"] = sanity
    return result


def main() -> int:
    if not is_cosmic_ray_available():
        print("[mutk-full] cosmic-ray 不可用——终止（无结果不得伪报）")
        return 1
    if not _INPUT_JSON.exists():
        print(f"[mutk-full] 输入工件缺失：{_INPUT_JSON}")
        return 1
    data = json.loads(_INPUT_JSON.read_text(encoding="utf-8"))
    rows = data["results"]["aitester"]["details"]
    print(f"[mutk-full] 输入 {len(rows)} 任务；cosmic-ray {cosmic_ray_version()}；全变异体口径")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        res = measure_task(row)
        results.append(res)
        score = res.get("mutation_score")
        total = res.get("mutants_total")
        print(
            f"[mutk-full] {index}/{len(rows)} {res['task_id']}: "
            f"{'skipped:' + str(res.get('skip_reason')) if res.get('skipped') else f'{score} ({res.get("mutants_killed")}/{total}) {res.get("elapsed_s")}s'}"
        )
        # 增量落盘（长跑批防丢：每 5 个任务刷一次）
        if index % 5 == 0 or index == len(rows):
            payload = {
                "caliber": "cosmic-ray full mutants (no truncation) + sanity gate (terminates & passes on fixed, 30s)",
                "cosmic_ray_version": cosmic_ray_version(),
                "cosmic_ray_config_hash": cosmic_ray_config_hash(),
                "timeout_seconds": TIMEOUT_SECONDS,
                "timeout_counts_as_killed": True,
                "sanity_gate": {
                    "timeout_seconds": SANITY_TIMEOUT_SECONDS,
                    "criteria": "generated test must terminate AND pass (rc=0) on task_metadata.fixed",
                },
                "input": str(_INPUT_JSON),
                "tasks_total": len(rows),
                "results": results,
            }
            atomic_write_json(_OUT_DIR / "MUTK_QUIXBUGS_FULL.json", payload, indent=2, mode=0o644)

    measured = [r for r in results if not r.get("skipped")]
    skipped = [r for r in results if r.get("skipped")]
    killed = sum(r.get("mutants_killed") or 0 for r in measured)
    total = sum(r.get("mutants_total") or 0 for r in measured)
    pooled = round(killed / total, 4) if total else None
    summary = {
        "tasks_total": len(results),
        "tasks_measured": len(measured),
        "tasks_skipped": len(skipped),
        "skip_reasons": sorted({r.get("skip_reason", "?") for r in skipped}),
        "n_sanity_gate_excluded": sum(1 for r in skipped if str(r.get("skip_reason", "")).startswith("test_")),
        "mutants_killed": killed,
        "mutants_total": total,
        "pooled": pooled,
    }
    payload = {
        "caliber": "cosmic-ray full mutants (no truncation) + sanity gate (terminates & passes on fixed, 30s)",
        "cosmic_ray_version": cosmic_ray_version(),
        "cosmic_ray_config_hash": cosmic_ray_config_hash(),
        "timeout_seconds": TIMEOUT_SECONDS,
        "timeout_counts_as_killed": True,
        "sanity_gate": {
            "timeout_seconds": SANITY_TIMEOUT_SECONDS,
            "criteria": "generated test must terminate AND pass (rc=0) on task_metadata.fixed",
        },
        "input": str(_INPUT_JSON),
        "summary": summary,
        "results": results,
    }
    out = _OUT_DIR / "MUTK_QUIXBUGS_FULL.json"
    atomic_write_json(out, payload, indent=2, mode=0o644)
    print(f"\n[mutk-full] 完成：{summary}")
    print(f"[mutk-full] 工件：{out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
