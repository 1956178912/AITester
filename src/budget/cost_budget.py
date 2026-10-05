"""
5.4 改进：任务级 LLM token/费用预算硬上限。

背景：
    当前成本管控只有"告警"（LLM_N_COST_WEIGHT 成本告警阈值，故障转移到
    昂贵 provider 时记 WARNING），缺少**硬性预算上限**——单任务 token
    消耗失控（死循环迭代 / LLM 反复重采样 / 多候选全拒绝后继续空转）
    时只能靠 MAX_ITERATIONS 间接兜底，无法直接封顶费用。

设计（与 token_usage.py 同口径：线程局部累计，--parallel 互不串扰）：
    - 预算开关：COST_BUDGET_ENABLE（默认 false，保持历史行为）；
    - 预算值（二选一，先 token 后费用）：
        COST_BUDGET_TOKENS：单任务 token 硬上限（默认 0 = 不限）；
        COST_BUDGET_USD：单任务费用硬上限（美元，需配 COST_USD_PER_1K，
          默认 0 = 未配置时费用口径不生效）；
    - 行为：超预算时 record_budget() 返回 False，调用方
      （BaseAgent._call_llm 前置守卫）抛出 BudgetExceededError；
      工作流捕获后把任务标记为 BUDGET_EXCEEDED（不继续迭代，
      保存已有结果），避免"继续烧 token 也大概率修不好"的无效空转；
    - 观测层：get_budget_stats() 返回 {consumed, limit, unit, exceeded}，
      供实验汇总与 CHANGELOG 成本趋势分析消费。

与 3.4 成本告警的关系：告警是"路由决策侧"的旁路观测（哪个 provider
贵），预算是"任务执行侧"的硬闸（本任务还能花多少），两层独立、
可叠加启用。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ─── 预算配置解析（环境变量，模块级缓存 + 刷新入口，与 config.py 同模式）───
# 线程局部累计器（与 token_usage._thread_local 同口径，--parallel 每任务独立）
_thread_local = threading.local()
_lock = threading.Lock()
# 进程级累计统计（观测层：全部任务的预算消耗/超限次数，供实验汇总）
_process_stats: dict[str, int] = {"total_consumed": 0, "budget_exceeded_events": 0, "tasks_capped": 0}


def _budget_enabled() -> bool:
    """预算开关（COST_BUDGET_ENABLE，默认 false 保持历史行为）。"""
    return os.getenv("COST_BUDGET_ENABLE", "false").strip().lower() in ("true", "1", "on")


def _budget_tokens_limit() -> int:
    """token 硬上限（COST_BUDGET_TOKENS，默认 0 = 不限）。"""
    try:
        return int(os.getenv("COST_BUDGET_TOKENS", "0").strip() or 0)
    except ValueError:
        return 0


def _budget_usd_limit() -> float:
    """费用硬上限（COST_BUDGET_USD，默认 0 = 未配置不生效）。"""
    try:
        return float(os.getenv("COST_BUDGET_USD", "0").strip() or 0)
    except ValueError:
        return 0


def _usd_per_1k() -> float:
    """每 1K token 费用（美元；COST_USD_PER_1K，默认 0 = 费用口径不生效）。"""
    try:
        return float(os.getenv("COST_USD_PER_1K", "0").strip() or 0)
    except ValueError:
        return 0


class BudgetExceededError(RuntimeError):
    """单任务 LLM 预算耗尽（BaseAgent._call_llm 前置守卫抛出）。"""

    def __init__(self, consumed: int, limit: int, unit: str) -> None:
        super().__init__(f"LLM 预算耗尽：已消耗 {consumed} {unit} >= 上限 {limit} {unit}")
        self.consumed = consumed
        self.limit = limit
        self.unit = unit


@dataclass
class BudgetSnapshot:
    """当前线程（任务）的预算快照。"""

    consumed_tokens: int = 0
    consumed_usd: float = 0.0
    token_limit: int = 0
    usd_limit: float = 0.0
    exceeded: bool = False
    enabled: bool = False

    def as_dict(self) -> dict[str, float | int | bool | str]:
        return {
            "consumed_tokens": self.consumed_tokens,
            "consumed_usd": round(self.consumed_usd, 6),
            "token_limit": self.token_limit,
            "usd_limit": self.usd_limit,
            "exceeded": self.exceeded,
            "enabled": self.enabled,
            "unit": "tokens" if self.token_limit > 0 else ("usd" if self.usd_limit > 0 else "none"),
        }


def _current_budget() -> BudgetSnapshot:
    """获取（必要时创建）当前线程的预算累计器。"""
    budget: BudgetSnapshot | None = getattr(_thread_local, "budget", None)
    if budget is None:
        budget = BudgetSnapshot()
        _thread_local.budget = budget
    return budget


def check_budget(consumed_delta_tokens: int = 0, consumed_delta_usd: float = 0.0) -> bool:
    """预算前置守卫：记录本次消耗并返回"是否仍允许继续调用 LLM"。

    流程：
    1. 开关关闭 → 直接 True（历史口径，零行为变化）；
    2. 累加消耗（token / 费用，费用未配单价时 0）；
    3. 超限判定（token 上限与费用上限任一达到即超限，未配置的侧不参与）；
    4. 超限 → 进程级统计 +1，记 WARNING，返回 False（调用方应停止）。

    Args:
        consumed_delta_tokens: 本次 LLM 调用的 token 消耗（入+出）。
        consumed_delta_usd: 本次调用的费用（美元，可为 0）。

    Returns:
        True = 预算内可继续；False = 已超限（调用方应停止 LLM 调用）。
    """
    if not _budget_enabled():
        return True
    budget = _current_budget()
    # C8（2026-10-05 系统审查 P0）：字段读改写整体入锁——专家池 worker 经
    # attach_budget 与任务线程共享同一 BudgetSnapshot 实例，无锁并发
    # "get→+=→set" 存在丢更新窗口（与 token_usage.round8 同口径修复）。
    _was_exceeded = budget.exceeded
    with _lock:
        budget.enabled = True
        budget.consumed_tokens += consumed_delta_tokens
        budget.consumed_usd += consumed_delta_usd
        budget.token_limit = _budget_tokens_limit()
        budget.usd_limit = _budget_usd_limit()

        exceeded = False
        if budget.token_limit > 0 and budget.consumed_tokens >= budget.token_limit:
            exceeded = True
        if budget.usd_limit > 0 and _usd_per_1k() > 0 and budget.consumed_usd >= budget.usd_limit:
            exceeded = True
        # O35（2026-09-30 全面审查 P2）：tasks_capped 语义修正——此前超限后的
        # **每一次** check_budget 调用都 +1（含被前置守卫拦下的后续调用），
        # 该字段名是"被封顶的任务数"，实际计的是"被拦下的 LLM 调用数"
        # （一次封顶任务可累计数十）。现只在 False→True 转跃沿 +1：
        # budget_exceeded_events 保持逐事件计数（语义本就是事件数），两者解耦。
        budget.exceeded = exceeded
        if exceeded:
            _process_stats["budget_exceeded_events"] += 1
            if not _was_exceeded:
                _process_stats["tasks_capped"] += 1
            _process_stats["total_consumed"] += consumed_delta_tokens
        elif consumed_delta_tokens:
            _process_stats["total_consumed"] += consumed_delta_tokens
    if exceeded and not _was_exceeded:
        logger.warning(
            "5.4 任务级预算超限：消耗 %d tokens / $%.4f >= 上限（tokens=%d, usd=%.4f），停止后续 LLM 调用",
            budget.consumed_tokens,
            budget.consumed_usd,
            budget.token_limit,
            budget.usd_limit,
        )
    return not exceeded


def record_usage_and_check(input_tokens: int, output_tokens: int, usd_cost: float = 0.0) -> bool:
    """record_usage 的预算包装：本调用消耗记账 + 前置守卫一步完成。

    Args:
        input_tokens: 本次调用输入 token。
        output_tokens: 本次调用输出 token。
        usd_cost: 本次调用费用（美元，0 = 未计价）。

    Returns:
        True = 预算内；False = 超限（后续调用应被拒绝）。
    """
    return check_budget(consumed_delta_tokens=input_tokens + output_tokens, consumed_delta_usd=usd_cost)


def get_budget_stats() -> dict[str, float | int | bool | str]:
    """当前线程（任务）的预算快照（供任务收尾 / 实验汇总消费）。"""
    return _current_budget().as_dict()


def current_budget() -> BudgetSnapshot:
    """当前线程预算累计器**实例**（C8：跨线程传播用，返回可变引用）。

    与 get_budget_stats 的区别：本函数返回实例本身，供任务线程在提交
    并发工作前捕获、经 attach_budget 在工作线程内重新绑定（预算作用域
    跟随任务而非线程）。
    """
    return _current_budget()


def attach_budget(budget: BudgetSnapshot) -> None:
    """C8（2026-10-05 系统审查 P0）：把指定预算累计器绑定到当前线程。

    专家池 worker 线程默认 _current_budget() 惰性创建全新 BudgetSnapshot
    （enabled=False, limits=0）——专家池内的 LLM 调用既不计入任务预算、
    也不受上限约束（线程局部记账被并发组件击穿）。提交前捕获任务实例，
    工作线程内经本函数绑定同一实例，预算即恢复对并发组件生效。
    """
    _thread_local.budget = budget


def get_process_budget_stats() -> dict[str, int]:
    """进程级预算统计（观测层：全任务累计消耗 / 超限事件 / 封顶任务数）。"""
    with _lock:
        return dict(_process_stats)


def reset_budget() -> None:
    """重置当前线程的预算累计器（每个任务开始前调用，与 token_usage.reset 同口径）。"""
    _thread_local.budget = BudgetSnapshot()


def is_budget_exceeded() -> bool:
    """当前线程预算是否已超限（工作流节点判断"是否继续迭代"用）。"""
    return _current_budget().exceeded
