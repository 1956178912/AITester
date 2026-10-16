#!/usr/bin/env python3
"""批次跑批前置闸（EMSE 批次 2026-10-15）：配额预算 + 模型指纹 + 工作树状态。

## 为什么需要它（来自本轮审计的实证）

1. **SWE-bench Lite 的失败根因是"没有批次级配额闸"，不是模型能力**——
   `experiments/results/emse_swebench_disclosure.md` 记录：20 次尝试中 10 次超时、
   7 次完成者全部因 API 429 限流失败，`capability_conclusion =
   none_valid_infrastructure_failure`，且**该数据集的 pass_rate 不得引用**。
   该披露文档自己写明："复跑前置：客户端已具备 429 退避，**但下载器/跑批入口
   无配额预算控制——重跑前需先补配额闸**"。本工具就是那道闸的前置检查。
2. **头条批次的模型指纹缺失**——主批次 provenance 10/10 `git_dirty=true`、
   0/10 有 `model_fingerprint`，而模型是浮动别名 `deepseek-flash`；
   `scripts/gates/check_model_fingerprint.py` 只扫近 2 天，历史批次被豁免。
   跑新批次前必须先确认"这次跑出来会带 `pinned=true` 指纹"，否则复跑一次仍不可复现。

## 与既有机制的关系（不重复造）

- **任务级**硬上限已存在：`COST_BUDGET_ENABLE` / `COST_BUDGET_TOKENS` /
  `COST_BUDGET_USD`（`src/budget/cost_budget.py`）——超限抛
  `BudgetExceededError`，任务标记 `BUDGET_EXCEEDED`。
- 本工具补的是**批次级**：任务数 × 重试 × 并行度 的请求量估算与"是否配了
  批次级上限"的判定。二者叠加使用（任务级防单任务失控，批次级防整批烧穿配额）。

## 用法

    python scripts/tools/run_preflight.py                      # 只读体检（零网络）
    python scripts/tools/run_preflight.py --expect-tasks 261   # 按计划任务数估算请求量
    python scripts/tools/run_preflight.py --check-quota        # 追加一次最小 LLM 探测（消耗 1 次调用）
    python scripts/tools/run_preflight.py --strict             # 任一项不达标 → 退出码非 0

退出码：0 = 通过（或非 strict 模式下的告警）；1 = strict 模式下存在阻断项；
2 = 用法/环境错误（如 --check-quota 但无可用 key）。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 批次级配额口径的**权威实现**在 `src/budget/batch_quota.py`（同时是 evn 变量
# 登记表的扫描面）；本工具只做编排与打印，不再自带一份解析逻辑（去重）。
from src.budget.batch_quota import (  # noqa: E402
    assess_batch_budget,
)


def git_state() -> dict[str, Any]:
    """工作树状态（干净树是"可复现批次"的必要条件之一）。"""
    out: dict[str, Any] = {"sha": None, "dirty": None, "dirty_reason": None}
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10)
        if sha.returncode == 0:
            out["sha"] = sha.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=_REPO_ROOT, capture_output=True, text=True, timeout=10
        )
        if status.returncode == 0:
            lines = [ln for ln in status.stdout.splitlines() if ln.strip()]
            out["dirty"] = bool(lines)
            out["dirty_reason"] = f"{len(lines)} 个未提交变更" if lines else None
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 环境异常
        out["dirty_reason"] = f"git 调用失败：{type(exc).__name__}"
    return out


def recent_fingerprints(limit: int = 5) -> list[dict[str, Any]]:
    """近期批次的模型指纹状态（新批次必须 pinned=true 才能锁住可复现性）。"""
    rows: list[dict[str, Any]] = []
    for path in sorted(
        (_REPO_ROOT / "experiments" / "results").glob("**/benchmark_*.json"),
        key=lambda p: p.stat().st_mtime if p.exists() else 0,
        reverse=True,
    )[:limit]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        prov = data.get("provenance") or {}
        fp = prov.get("model_fingerprint") or {}
        rows.append(
            {
                "file": str(path.relative_to(_REPO_ROOT)),
                "model_name": prov.get("model_name"),
                "pinned": fp.get("pinned"),
                "returned_model": fp.get("returned_model"),
                "git_dirty": prov.get("git_dirty"),
            }
        )
    return rows


def batch_budget_report(expect_tasks: int, parallelism: int) -> dict[str, Any]:
    """批次级请求量估算 + 上限配置检查（口径来自 `src/budget/batch_quota.py`）。"""
    assessment = assess_batch_budget(expect_tasks)
    return {
        "expect_tasks": expect_tasks,
        "parallelism": parallelism,
        "estimated_calls_upper_bound": assessment.estimated_calls_upper_bound,
        "task_level": {
            "enabled": assessment.task_level_enabled,
            "tokens": assessment.task_level_tokens,
            "usd": assessment.task_level_usd,
        },
        "batch_cap_calls": assessment.batch_cap_calls,
        "batch_cap_usd": assessment.batch_cap_usd,
        "preflight_required": assessment.preflight_required,
        "blocking": list(assessment.blocking),
    }


def quota_probe() -> dict[str, Any]:
    """最小 LLM 连通性/配额探测（**消耗 1 次调用**，仅在 --check-quota 时执行）。"""
    if not any(os.getenv(k, "").strip() for k in ("LLM_1_API_KEY", "DEEPSEEK_API_KEY")):
        return {"ok": False, "skipped": True, "reason": "未检测到 LLM_1_API_KEY / DEEPSEEK_API_KEY"}
    try:
        from src.agents.llm_client import LLMClient  # 延迟导入：零网络体检路径不加载
    except Exception as exc:  # pragma: no cover - 依赖异常
        return {"ok": False, "skipped": True, "reason": f"导入 LLMClient 失败：{type(exc).__name__}"}
    try:  # pragma: no cover - 需要真实凭据
        client = LLMClient()
        resp = client.call("Reply with the single token: OK", temperature=0.0)
        text = resp if isinstance(resp, str) else str(resp)
        return {"ok": "ok" in text.lower(), "skipped": False, "response_prefix": text[:40]}
    except Exception as exc:  # pragma: no cover - 网络/配额异常
        return {"ok": False, "skipped": False, "reason": f"{type(exc).__name__}: {exc}"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="批次跑批前置闸（配额/指纹/工作树）")
    parser.add_argument("--expect-tasks", type=int, default=261, help="计划任务数（默认主批次 261）")
    parser.add_argument("--parallelism", type=int, default=int(os.getenv("BENCHMARK_PARALLELISM", "4") or 4))
    parser.add_argument("--check-quota", action="store_true", help="追加一次最小 LLM 探测（消耗 1 次调用）")
    parser.add_argument("--strict", action="store_true", help="存在阻断项时退出码非 0")
    args = parser.parse_args(argv)

    git = git_state()
    budget = batch_budget_report(args.expect_tasks, args.parallelism)
    prints = recent_fingerprints()
    pinned_recent = [r for r in prints if r.get("pinned") is True]

    print("=" * 72)
    print("批次跑批前置闸（EMSE 批次 2026-10-15）")
    print("=" * 72)
    print(
        f"工作树：sha={git['sha']}  dirty={git['dirty']}"
        + (f"（{git['dirty_reason']}）" if git["dirty_reason"] else "")
    )
    print(
        f"计划任务数={budget['expect_tasks']}  并行度={budget['parallelism']}  "
        f"估算请求量上界={budget['estimated_calls_upper_bound']}"
    )
    print(
        f"任务级预算：enabled={budget['task_level']['enabled']} "
        f"tokens={budget['task_level']['tokens']} usd={budget['task_level']['usd']}"
    )
    print(f"批次级上限：AITESTER_BATCH_MAX_CALLS={budget['batch_cap_calls']}")
    print(f"近期批次指纹（近 {len(prints)} 个）：pinned=true 的有 {len(pinned_recent)} 个")
    for row in prints:
        print(f"  - {row['file']}｜alias={row['model_name']}｜pinned={row['pinned']}｜dirty={row['git_dirty']}")

    blocking = list(budget["blocking"])
    if git["dirty"]:
        blocking.append("工作树不干净：新批次 provenance 将记 git_dirty=true（复现性主张打折）")
    if prints and not pinned_recent:
        blocking.append("近期批次均无 pinned=true 模型指纹：新批次须确认带指纹后再跑")

    if args.check_quota:
        probe = quota_probe()
        print(f"配额探测：{probe}")
        if not probe.get("ok"):
            blocking.append(f"配额/连通性探测未通过：{probe.get('reason') or probe}")
    else:
        print("配额探测：未执行（加 --check-quota 可消耗 1 次调用探测）")

    if blocking:
        print("\n阻断/告警项：")
        for item in blocking:
            print(f"  ✗ {item}")
    else:
        print("\n✓ 前置闸全部通过")
    print("=" * 72)
    if blocking and args.strict:
        print("strict 模式：存在阻断项，退出码 1")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
