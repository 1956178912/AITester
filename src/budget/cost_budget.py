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

G 轮（2026-10-16）坏值口径修正——**fail-closed**：
    此前三个数值配置（COST_BUDGET_TOKENS / COST_BUDGET_USD /
    COST_USD_PER_1K）解析失败一律 ``except ValueError: return 0``，而 0 在
    本模块语义里是"未配置 = 不限 / 该侧口径不生效"。即：开了预算闸却把上限
    拼错（``COST_BUDGET_TOKENS=500k``、``COST_USD_PER_1K=0.0O6`` 字母 O）时，
    守卫**静默降级为无上限**，只留一条都没有的日志——正是"最该拦的场景拦不住，
    且无人知晓"。现三态区分：未设置/空串 = 合法的"未配置"；可解析且非负 = 生效；
    **不可解析或负数 = 配置错误**，记 ERROR（每 变量+原值 一次）并让
    check_budget 直接返回 False（拒绝后续 LLM 调用），进程级统计单独计
    ``budget_misconfigured_events``（不污染"真实超限"计数）。
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass

from src.utils.env_utils import env_flag

logger = logging.getLogger(__name__)

# ─── 预算配置解析（环境变量，模块级缓存 + 刷新入口，与 config.py 同模式）───
# 线程局部累计器（与 token_usage._thread_local 同口径，--parallel 每任务独立）
_thread_local = threading.local()
_lock = threading.Lock()
# 进程级累计统计（观测层：全部任务的预算消耗/超限次数，供实验汇总）
_process_stats: dict[str, int] = {
    "total_consumed": 0,
    "budget_exceeded_events": 0,
    "tasks_capped": 0,
    # G 轮新增：因**配置错误**（非真实超限）而拒绝 LLM 调用的事件数。与
    # budget_exceeded_events 分开计，避免"拼错环境变量"被读成"任务烧爆预算"。
    "budget_misconfigured_events": 0,
}

# 预算数值配置项名（模块级常量：ADR-0003 env 预算门禁按"名字含 ENV 的模块级
# 字符串常量"扫描，字面量散在调用点会绕过预算治理）。
_ENV_COST_BUDGET_TOKENS = "COST_BUDGET_TOKENS"
_ENV_COST_BUDGET_USD = "COST_BUDGET_USD"
_ENV_COST_USD_PER_1K = "COST_USD_PER_1K"

#: 已记过 ERROR 的 (变量名, 原值)——check_budget 每次 LLM 调用都解析配置，
#: 不去重会按调用次数刷屏（GIL 下 set.add 原子，最坏情况只是重复一行）。
_bad_value_logged: set[tuple[str, str]] = set()
#: 已记过 WARNING 的"启用但无任何上限"提示（同因去重）。
_no_limit_warned: set[str] = set()


def _budget_enabled() -> bool:
    """预算开关（COST_BUDGET_ENABLE，默认 false 保持历史行为）。"""
    return env_flag("COST_BUDGET_ENABLE")


def _read_budget_number(name: str, *, integer: bool) -> tuple[int | float, bool]:
    """读取预算数值配置，三态区分（G 轮 fail-closed 的核心）。

    Args:
        name: 环境变量名。
        integer: True 按 int 解析（token 数），False 按 float 解析（美元）。

    Returns:
        ``(值, 是否可用)``：

        - 未设置 / 空串 → ``(0, True)``：合法的"未配置"，该侧口径不生效
          （历史文档口径，不变）；
        - 可解析且非负 → ``(值, True)``；
        - 不可解析或为负 → ``(0, False)``：**配置错误**，调用方必须
          fail-closed。此前这里一律回退 ``(0, True)``，等于把"拼错上限"
          静默当成"不限"。
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return 0, True
    text = raw.strip()
    kind = "整数" if integer else "浮点数"
    try:
        value: int | float = int(text) if integer else float(text)
    except ValueError:
        _log_bad_budget_value(name, raw, f"无法解析为{kind}")
        return 0, False
    if value < 0:
        _log_bad_budget_value(name, raw, f"为负数（{kind}上限不得为负）")
        return 0, False
    return value, True


def _log_bad_budget_value(name: str, raw: str, reason: str) -> None:
    """预算配置坏值 ERROR（每 变量+原值 记一次）。"""
    key = (name, raw)
    if key in _bad_value_logged:
        return
    _bad_value_logged.add(key)
    logger.error(
        "预算配置 %s=%r %s：按 fail-closed 拒绝后续 LLM 调用。"
        "坏值不等于“未配置”，不得静默降级为不限（G 轮 2026-10-16）",
        name,
        raw,
        reason,
    )


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
    # AM1（2026-10-06 第十三轮审查 / 预注册 E6 执行前置）：任务级 token 上限
    # 的**实例级**覆盖（0 = 无覆盖）。放在 BudgetSnapshot 实例而非线程局部，
    # 使 cap 作用域跟随任务而非线程——专家池 worker 经 attach_budget 绑定
    # 同一实例后自动继承（与 C8 预算作用域修复同语义）；reset_budget()
    # 每 (任务, 基线) 重建实例时天然清零，无跨任务残留。
    token_cap_override: int = 0

    def as_dict(self) -> dict[str, float | int | bool | str]:
        return {
            "consumed_tokens": self.consumed_tokens,
            "consumed_usd": round(self.consumed_usd, 6),
            "token_limit": self.token_limit,
            "usd_limit": self.usd_limit,
            "exceeded": self.exceeded,
            "enabled": self.enabled,
            "token_cap_override": self.token_cap_override,
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
    1. 开关关闭（且无实例级 cap 覆盖）→ 直接 True（历史口径，零行为变化）；
    2. 解析三项预算配置，区分"未配置"与"配置错误"（G 轮）；
    3. 累加消耗（token / 费用，费用未配单价时 0）；
    4. 超限判定（token 上限与费用上限任一达到即超限，未配置的侧不参与）；
    5. 超限 → 进程级统计 +1，记 WARNING，返回 False（调用方应停止）；
    6. **配置错误 → 同样返回 False（fail-closed）**，记 ERROR 并单独计
       ``budget_misconfigured_events``——坏值不得静默当成"不限"。

    Args:
        consumed_delta_tokens: 本次 LLM 调用的 token 消耗（入+出）。
        consumed_delta_usd: 本次调用的费用（美元，可为 0）。

    Returns:
        True = 预算内可继续；False = 已超限**或预算配置不可用**（调用方应停止
        LLM 调用）。
    """
    # AM1：实例级 cap 覆盖存在时预算检查自动生效（无需 COST_BUDGET_ENABLE）——
    # CLI --per-task-token-caps 注入的 cap 自足生效，env 开关语义不变。
    if not _budget_enabled() and getattr(_current_budget(), "token_cap_override", 0) <= 0:
        return True
    # G 轮：配置解析前置到锁外（每次 LLM 调用都会走一遍，锁内做字符串解析纯属
    # 浪费），并把"坏值"与"未配置"分开——坏值 fail-closed（见模块 docstring）。
    tokens_raw, tokens_ok = _read_budget_number(_ENV_COST_BUDGET_TOKENS, integer=True)
    usd_raw, usd_ok = _read_budget_number(_ENV_COST_BUDGET_USD, integer=False)
    per_1k_raw, per_1k_ok = _read_budget_number(_ENV_COST_USD_PER_1K, integer=False)
    misconfigured = sorted(
        name
        for name, ok in (
            (_ENV_COST_BUDGET_TOKENS, tokens_ok),
            (_ENV_COST_BUDGET_USD, usd_ok),
            (_ENV_COST_USD_PER_1K, per_1k_ok),
        )
        if not ok
    )
    budget = _current_budget()
    # C8（2026-10-05 系统审查 P0）：字段读改写整体入锁——专家池 worker 经
    # attach_budget 与任务线程共享同一 BudgetSnapshot 实例，无锁并发
    # "get→+=→set" 存在丢更新窗口（与 token_usage.round8 同口径修复）。
    _was_exceeded = budget.exceeded
    with _lock:
        budget.enabled = True
        budget.consumed_tokens += consumed_delta_tokens
        budget.consumed_usd += consumed_delta_usd
        # AM1：cap 覆盖优先于 env（E6 预算匹配臂按臂设 cap，--parallel 下
        # env 全局值会串扰邻基线——X1 检出优先线程局部 override 同因）。
        budget.token_limit = budget.token_cap_override if budget.token_cap_override > 0 else int(tokens_raw)
        budget.usd_limit = float(usd_raw)
        per_1k = float(per_1k_raw)

        exceeded = False
        if budget.token_limit > 0 and budget.consumed_tokens >= budget.token_limit:
            exceeded = True
        if budget.usd_limit > 0 and per_1k > 0 and budget.consumed_usd >= budget.usd_limit:
            exceeded = True
        # G 轮：配置错误时上限值不可信，**不得**按"不限"放行——与真实超限同样
        # 阻断，但计数分列（budget_misconfigured_events），避免把拼错环境变量
        # 读成"任务烧爆预算"。
        blocked = exceeded or bool(misconfigured)
        # O35（2026-09-30 全面审查 P2）：tasks_capped 语义修正——此前超限后的
        # **每一次** check_budget 调用都 +1（含被前置守卫拦下的后续调用），
        # 该字段名是"被封顶的任务数"，实际计的是"被拦下的 LLM 调用数"
        # （一次封顶任务可累计数十）。现只在 False→True 转跃沿 +1：
        # budget_exceeded_events 保持逐事件计数（语义本就是事件数），两者解耦。
        budget.exceeded = blocked
        if exceeded:
            _process_stats["budget_exceeded_events"] += 1
        if misconfigured:
            _process_stats["budget_misconfigured_events"] += 1
        if blocked:
            if not _was_exceeded:
                _process_stats["tasks_capped"] += 1
            _process_stats["total_consumed"] += consumed_delta_tokens
        elif consumed_delta_tokens:
            _process_stats["total_consumed"] += consumed_delta_tokens
    if misconfigured and not _was_exceeded:
        logger.error(
            "5.4 预算守卫：配置项 %s 不可用，按 fail-closed 停止后续 LLM 调用（非真实超限）",
            ", ".join(misconfigured),
        )
    elif exceeded and not _was_exceeded:
        logger.warning(
            "5.4 任务级预算超限：消耗 %d tokens / $%.4f >= 上限（tokens=%d, usd=%.4f），停止后续 LLM 调用",
            budget.consumed_tokens,
            budget.consumed_usd,
            budget.token_limit,
            budget.usd_limit,
        )
    if (
        not misconfigured
        and not exceeded
        and budget.token_limit <= 0
        and budget.usd_limit <= 0
        and "no_limit" not in _no_limit_warned
    ):
        # 守卫开着却没配任何上限 = 不设闸（历史默认口径，不改行为），但必须
        # 让操作者在日志里看见，而不是误以为"预算已受控"。
        _no_limit_warned.add("no_limit")
        logger.warning(
            "5.4 预算守卫已启用但无任何有效上限（%s / %s 均未配置或为 0）：等同不设闸",
            _ENV_COST_BUDGET_TOKENS,
            _ENV_COST_BUDGET_USD,
        )
    return not blocked


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


def set_task_token_cap(cap: int) -> None:
    """AM1（预注册 E6 执行前置）：设置当前任务实例的 token 上限覆盖。

    写入当前线程 BudgetSnapshot 实例的 token_cap_override 字段（0 = 清除，
    回落 COST_BUDGET_TOKENS env 口径）。cap 跟随实例而非线程：
    - 专家池 worker 经 attach_budget 绑定同一实例后自动继承（C8 语义）；
    - reset_budget() 每任务重建实例时天然清零，无跨任务残留；
    - cap > 0 时预算检查自动生效（无需 COST_BUDGET_ENABLE），
      超限走既有 BudgetExceededError → BUDGET_EXCEEDED 停止通道。

    供 run_benchmark --per-task-token-cap 按 (任务, 基线) 注入。
    """
    _current_budget().token_cap_override = max(0, int(cap))


def is_budget_exceeded() -> bool:
    """当前线程预算是否已超限（工作流节点判断"是否继续迭代"用）。"""
    return _current_budget().exceeded
