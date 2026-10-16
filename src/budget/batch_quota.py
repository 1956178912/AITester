"""批次级配额预算（EMSE 批次 2026-10-15）：跑批前置闸的权威口径模块。

## 与任务级预算的分工

- **任务级**：`src/budget/cost_budget.py`（`COST_BUDGET_ENABLE` / `COST_BUDGET_TOKENS` /
  `COST_BUDGET_USD`）——单任务 token/费用硬上限，超限抛 `BudgetExceededError`。
- **批次级（本模块）**：整批请求量上界与配置检查——防止"任务级没失控、但整批
  烧穿配额"的失败模式。

## 为什么必须有批次级（实证依据）

`experiments/results/emse_swebench_disclosure.md`：SWE-bench Lite 20 次尝试中
**10 次超时、7 次完成者全部因 API 429 限流失败**，能力结论被标注为
`none_valid_infrastructure_failure`，且该数据集 `pass_rate` 不得引用。该披露文档
自述复跑前置为"**下载器/跑批入口无配额预算控制——重跑前需先补配额闸**"。
本模块即该闸的口径来源，消费方为 `scripts/tools/run_preflight.py`。

## 环境变量（新增须在 docs/env_budget.yaml 登记，本模块为扫描面）

| 变量 | 默认 | 含义 |
|---|---|---|
| `AITESTER_BATCH_MAX_CALLS` | 未设 | 批次级 LLM 调用次数上限（估算上界超过它即判为阻断） |
| `AITESTER_BATCH_MAX_USD` | 未设 | 批次级费用上限（美元；与价目表口径配合） |
| `AITESTER_RUN_PREFLIGHT` | 未设 | 跑批脚本是否强制先跑前置闸（`true` 时未过闸即中止） |

零网络、零 LLM：本模块只做配置解析与算术估算，不做任何外部调用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from src.utils.env_utils import env_flag

# ─── 环境变量名常量（供门禁扫描与文档引用，避免散落字面量） ──────────────
_ENV_BATCH_MAX_CALLS = "AITESTER_BATCH_MAX_CALLS"
_ENV_BATCH_MAX_USD = "AITESTER_BATCH_MAX_USD"
_ENV_RUN_PREFLIGHT = "AITESTER_RUN_PREFLIGHT"

# 单任务请求量经验值：主批次实测 aitester 4.24 次 LLM 调用/任务（最坏臂），
# 批次估算取最坏臂作为上界；重试系数覆盖 429/超时退避重试（base_agent）。
PER_TASK_CALLS_WORST = 4.3
RETRY_FACTOR = 1.5


def _flag(name: str) -> bool:
    """布尔开关解析（env_flag 单一事实源；含 "yes" 扩展集，2026-10-16 C 轮收敛）。"""
    return env_flag(name, extra_true=("yes",))


def _int_or_none(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def _float_or_none(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def batch_cap_calls() -> int | None:
    """批次级调用上限（未配置 → None，调用方须按"未配置"而非"无限"处理）。"""
    return _int_or_none(_ENV_BATCH_MAX_CALLS)


def batch_cap_usd() -> float | None:
    """批次级费用上限（未配置 → None）。"""
    return _float_or_none(_ENV_BATCH_MAX_USD)


def preflight_required() -> bool:
    """跑批脚本是否强制前置闸（AITESTER_RUN_PREFLIGHT）。"""
    return _flag(_ENV_RUN_PREFLIGHT)


def estimate_calls(
    expect_tasks: int, *, per_task_calls: float = PER_TASK_CALLS_WORST, retry_factor: float = RETRY_FACTOR
) -> int:
    """批次请求量上界估算（任务数 × 最坏臂每任务调用数 × 重试系数，向上取整）。"""
    if expect_tasks <= 0:
        return 0
    return int(expect_tasks * per_task_calls * retry_factor) + 1


@dataclass
class BatchBudgetAssessment:
    """批次预算评估结果（供前置闸打印与判定）。"""

    expect_tasks: int
    estimated_calls_upper_bound: int
    batch_cap_calls: int | None
    batch_cap_usd: float | None
    task_level_enabled: bool
    task_level_tokens: int | None
    task_level_usd: float | None
    preflight_required: bool = False
    blocking: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocking


def assess_batch_budget(expect_tasks: int) -> BatchBudgetAssessment:
    """批次预算评估（纯函数式读取环境，便于测试注入 monkeypatch）。"""
    cap_calls = batch_cap_calls()
    cap_usd = batch_cap_usd()
    est = estimate_calls(expect_tasks)
    task_enabled = _flag("COST_BUDGET_ENABLE")
    task_tokens = _int_or_none("COST_BUDGET_TOKENS")
    task_usd = _float_or_none("COST_BUDGET_USD")
    blocking: list[str] = []
    if not task_enabled:
        blocking.append(
            "任务级预算未启用（COST_BUDGET_ENABLE=false）——单任务失控无硬闸；"
            "启用：COST_BUDGET_ENABLE=true + COST_BUDGET_TOKENS=<上限>"
        )
    if cap_calls is None:
        blocking.append(
            f"批次级调用上限未配置（{_ENV_BATCH_MAX_CALLS} 未设）——整批可能烧穿配额"
            "（SWE-bench Lite 20 次尝试即因此产生 10 次超时 + 7 次 429 失败）"
        )
    elif cap_calls < est:
        blocking.append(
            f"批次级上限 {cap_calls} 低于估算上界 {est}"
            f"（= 任务数 {expect_tasks} × 最坏臂 {PER_TASK_CALLS_WORST} × 重试系数 {RETRY_FACTOR}）"
            "——批次会被闸掉或跑不完"
        )
    return BatchBudgetAssessment(
        expect_tasks=expect_tasks,
        estimated_calls_upper_bound=est,
        batch_cap_calls=cap_calls,
        batch_cap_usd=cap_usd,
        task_level_enabled=task_enabled,
        task_level_tokens=task_tokens,
        task_level_usd=task_usd,
        preflight_required=preflight_required(),
        blocking=blocking,
    )
