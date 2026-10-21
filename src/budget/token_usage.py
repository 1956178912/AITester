"""
LLM Token 消耗统计模块（P0 效率指标：完整系统 vs Plain LLM 的性价比对比）。

背景：
    完整多智能体系统每个任务要经过 Planner → Generator → Executor(多轮) →
    Debugger 多次 LLM 调用，token 消耗远多于单次调用基线。若性能没有优势，
    性价比反而不如 Plain LLM。实验必须记录每个任务的 token 消耗作为效率指标。

设计：
    - 线程局部累计（threading.local）：--parallel 模式下每个工作线程（任务）
      独立累计，互不串扰；
    - 每次 LLM 调用成功后由 BaseAgent 调用 record_usage() 累加；
    - 跨线程聚合（global_usage）供实验汇总；
    - 所有计数均为"本进程内、缓存未命中时"的真实 API 消耗。

使用方式（benchmark 入口）：
    from src.budget.token_usage import get_usage, reset
    reset()                      # 每个任务/基线开始前重置本线程
    ... 运行工作流 ...
    usage = get_usage()          # 取本线程累计
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TokenUsage:
    """单个作用域（线程/任务）的 token 消耗快照。"""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    # P0 止血（缓存记账缺口）：缓存命中路径此前只记 record_cache_hit、不记
    # token，导致 $/task 与 token 效率结论随缓存命中率系统性偏低（缓存密集的
    # 多智能体场景可能低报 30-50%）。新增两个独立口径（不污染 record_usage 的
    # "真实 API 消耗"语义）：
    #   cache_hits           —— 缓存命中次数（真实调用次数 = llm_calls 不变，
    #                           命中额外计数，供报告层算命中率）；
    #   cache_avoided_tokens —— 命中时"若未命中会消耗"的 token（缓存文件记录的
    #                           上次实际调用 token；LRU 快路径无该值记 0）。
    cache_hits: int = 0
    cache_avoided_tokens: int = 0
    by_model: dict[str, int] = field(default_factory=dict)  # 模型名 → total_tokens
    # AT（2026-10-21）：写入口拒绝的机制计数。坏值不计入上面任何总量（不给
    # 部分和），但"调用/命中确实发生过"仍计入 llm_calls / cache_hits。只在
    # 真发生时经 as_dict 落盘 ⇒ 干净工件 schema 逐字不变；读端见到非空标记
    # 即把该行 token / 缓存读数判为不可读（部分和不得冒充全额）。
    token_write_reasons: dict[str, int] = field(default_factory=dict)
    cache_write_reasons: dict[str, int] = field(default_factory=dict)

    def merge(self, other: TokenUsage) -> None:
        """把另一个快照累加到自身（用于跨线程聚合）。"""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.total_tokens += other.total_tokens
        self.llm_calls += other.llm_calls
        self.cache_hits += other.cache_hits
        self.cache_avoided_tokens += other.cache_avoided_tokens
        for model, tokens in other.by_model.items():
            self.by_model[model] = self.by_model.get(model, 0) + tokens
        for code, count in other.token_write_reasons.items():
            self.token_write_reasons[code] = self.token_write_reasons.get(code, 0) + count
        for code, count in other.cache_write_reasons.items():
            self.cache_write_reasons[code] = self.cache_write_reasons.get(code, 0) + count

    def as_dict(self) -> dict[str, int | dict[str, int]]:
        """转为可 JSON 序列化的字典（拒绝披露键只在真发生时出现）。"""
        payload: dict[str, int | dict[str, int]] = {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "llm_calls": self.llm_calls,
            "cache_hits": self.cache_hits,
            "cache_avoided_tokens": self.cache_avoided_tokens,
            "by_model": dict(self.by_model),
        }
        if self.token_write_reasons:
            payload["token_write_reasons"] = dict(self.token_write_reasons)
        if self.cache_write_reasons:
            payload["cache_write_reasons"] = dict(self.cache_write_reasons)
        return payload


# ─── 线程局部累计器 ─────────────────────────────────────────────────────────────
_thread_local = threading.local()
# 跨线程聚合：{thread_id: TokenUsage}，由 _registry_lock 保护。
# 已退出线程的条目刻意保留（不清理）：基准运行结束时 global_usage() 需聚合
# 全部已完成任务（worker 线程已退出）的 token 消耗；条目数受并发线程规模
# 限制（常驻线程池场景），量级可忽略
_registry: dict[int, TokenUsage] = {}
_registry_lock = threading.Lock()
# 进程级累计锁（2026-09-26 round8，round7 遗留债务项落地）：
# TokenUsage 各字段为普通 int/dict，record_usage 的 "get→+1→set" 非原子。
# --parallel 下 LangChain 线程池 worker 复用 + 同任务多 agent 线程可能
# 并发累加同一 ThreadLocal 的 TokenUsage，存在丢更新窗口（理论竞态，
# 实测影响极小）。加进程级单锁原子化读改写：纯内存操作（微秒级，无 I/O），
# 不改变任何累计语义，仅消除丢更新。
# 设计取舍：用单锁而非"per-instance 锁字典"——ThreadLocal 的 TokenUsage
# 在 reset() 时被新实例替换（旧实例仅存于已退出线程的 registry），
# 按 id(实例) 建锁字典会让键随实例替换/线程退出而漂移（同 id 复用
# 风险 + 字典无界增长），无实际收益。进程级单锁持锁时间为单次
# record_usage 的字段读改写（微秒级，无 I/O），不会成为 --parallel
# 瓶颈；跨线程一致性由 _registry_lock 在 global_usage 聚合点保证。
_usage_lock = threading.Lock()
# 同类拒绝机制只告警一次（全局）：坏 usage 每个 LLM 调用都可能复现，逐次告警
# 会把日志刷爆；机制名本身已按次计入 token_write_reasons / cache_write_reasons。
_warned_write_reasons: set[str] = set()
_warned_cache_write_reasons: set[str] = set()
_warned_model_issues: set[str] = set()


def _current_usage() -> TokenUsage:
    """获取（必要时创建）当前线程的累计器。"""
    usage: TokenUsage | None = getattr(_thread_local, "usage", None)
    if usage is None:
        usage = TokenUsage()
        _thread_local.usage = usage
        with _registry_lock:
            _registry[threading.get_ident()] = usage
    return usage


def record_usage(input_tokens: Any, output_tokens: Any, model: str = "") -> list[str]:
    """记录一次 LLM 调用的 token 消耗（累加到当前线程）。

    AT（2026-10-21）：写入口与读端共用 :func:`count_reason`。任一计数不是
    非负整数（bool / 小数 / 字符串 / 负数 / 非有限）→ **整次写入的 token
    不计入**（不给部分和），机制名计入 ``token_write_reasons``；调用确实
    发生过，``llm_calls`` 照常 +1。非字符串 model 不并入 ``by_model``
    （读端 ``by_model_reason`` 不认非字符串键，写入端从源头拦住）。

    Args:
        input_tokens: 本次调用的输入 token 数（原始值，缺失由调用方归一为 0）。
        output_tokens: 本次调用的输出 token 数。
        model: 产生本次消耗的模型名（用于 by_model 分桶，可为空）。

    Returns:
        拒绝机制名列表；空列表 = 两个计数都已计入。

    线程安全（2026-09-26 round8）：各字段读改写在进程级 _usage_lock 内
    原子化（--parallel 下并发累加同一累计器时消除丢更新窗口）；纯内存
    操作（微秒级，无 I/O），不改变累计语义。
    """
    reasons: list[str] = []
    for value, field_name in ((input_tokens, "input_tokens"), (output_tokens, "output_tokens")):
        reason = count_reason(value, field_name)
        if reason is not None:
            reasons.append(reason)
    usage = _current_usage()
    warn_codes: list[str] = []
    warn_model = False
    with _usage_lock:
        usage.llm_calls += 1
        if reasons:
            for code in reasons:
                usage.token_write_reasons[code] = usage.token_write_reasons.get(code, 0) + 1
                if code not in _warned_write_reasons:
                    _warned_write_reasons.add(code)
                    warn_codes.append(code)
        else:
            usage.input_tokens += input_tokens
            usage.output_tokens += output_tokens
            usage.total_tokens += input_tokens + output_tokens
            if model and isinstance(model, str):
                usage.by_model[model] = usage.by_model.get(model, 0) + input_tokens + output_tokens
            elif model and "model_not_str" not in _warned_model_issues:
                _warned_model_issues.add("model_not_str")
                warn_model = True
    for code in warn_codes:
        logger.warning("token 写入被拒绝（同类机制只告警一次）: %s", code)
    if warn_model:
        logger.warning("token 写入的 model 不是字符串（不并入 by_model）: %s", type(model).__name__)
    return reasons


def record_cache_hit_usage(avoided_tokens: Any, model: str = "") -> list[str]:
    """记录一次缓存命中（P0 止血：缓存命中路径的 token 记账缺口）。

    缓存命中不产生真实 API 消耗，但"若未命中会消耗"的 token 数必须可观测，
    否则 $/task 与 token 效率结论随缓存命中率系统性漂移。本函数把"避免的
    token"独立累计到 cache_hits / cache_avoided_tokens，**不写入 record_usage
    的 input/output/total/llm_calls**（保持"真实 API 消耗"口径不变，避免破坏
    既有 $/task 结论）；报告层可据 total_tokens + cache_avoided_tokens 还原
    "无缓存理论成本"。

    AT（2026-10-21）：avoided 同样交 :func:`count_reason` 判定。命中确实发生
    → ``cache_hits`` 照常 +1；坏 avoided 不计入金额口径，机制名计入
    ``cache_write_reasons``（读端据此把整行缓存读数判为不可读）。

    Args:
        avoided_tokens: 本次命中若未发生会消耗的 token 数（缓存文件记录的
            上次实际调用 token；LRU 快路径拿不到该值时传 0，仅记命中次数）。
        model: 产生原始消耗的模型名（供报告层分桶，不并入 by_model 的真实
            消耗累计）。

    Returns:
        拒绝机制名列表；空列表 = avoided 已计入。
    """
    reason = count_reason(avoided_tokens, "cache_avoided_tokens")
    reasons = [reason] if reason is not None else []
    usage = _current_usage()
    warn_codes: list[str] = []
    with _usage_lock:
        usage.cache_hits += 1
        if reasons:
            for code in reasons:
                usage.cache_write_reasons[code] = usage.cache_write_reasons.get(code, 0) + 1
                if code not in _warned_cache_write_reasons:
                    _warned_cache_write_reasons.add(code)
                    warn_codes.append(code)
        else:
            usage.cache_avoided_tokens += avoided_tokens
    for code in warn_codes:
        logger.warning("缓存 avoided-token 写入被拒绝（同类机制只告警一次）: %s", code)
    return reasons


def write_rejection_count() -> int:
    """当前线程累计的写拒绝次数（token + 缓存）。

    缓存写入路径用它判断"调用前后 total_tokens 差值"是否仍可当完整消耗量：
    本次调用发生过任一写拒绝 ⇒ 差值只是部分和，缓存文件 ``tokens`` 记
    null（未知），命中侧据披露而非把部分和当全额。
    """
    usage = _current_usage()
    with _usage_lock:
        return sum(usage.token_write_reasons.values()) + sum(usage.cache_write_reasons.values())


def get_usage() -> TokenUsage:
    """获取当前线程的 token 消耗快照（不影响累计器，可重复调用）。"""
    return _current_usage()


def attach_usage(usage: TokenUsage) -> None:
    """C8（2026-10-05 系统审查 P0）：把指定累计器实例绑定到当前线程。

    专家池等"任务内并发组件"在 ThreadPoolExecutor 工作线程里发起 LLM 调用——
    此前工作线程 _current_usage() 惰性创建全新实例，token 记到孤儿线程上：
    任务级 get_usage() 失真（get_usage 是同一可变实例的引用，工作线程的
    累加看不到）、预算约束完全被绕过。调用方在提交前捕获任务累计器实例
    （get_usage()），在工作线程内经本函数重新绑定，使记账作用域跟随
    **任务**而非线程。

    registry 以实例同一性去重：同一实例被多线程共享绑定时，
    global_usage() 不重复累计（否则同任务 token 被按线程数翻倍）。
    """
    _thread_local.usage = usage
    with _registry_lock:
        if not any(existing is usage for existing in _registry.values()):
            _registry[threading.get_ident()] = usage


def reset() -> TokenUsage:
    """重置当前线程累计器，并返回重置前的快照。

    用于"每个任务/基线开始前清零"的实验隔离语义。

    Returns:
        重置前本线程已累计的 TokenUsage。
    """
    previous = get_usage()
    fresh = TokenUsage()
    _thread_local.usage = fresh
    with _registry_lock:
        _registry[threading.get_ident()] = fresh
    return previous


def global_usage() -> TokenUsage:
    """聚合所有线程的 token 消耗（快照，含已退出线程的条目）。

    跨线程求和，供实验结束时输出全局效率指标：基准运行结束时聚合需包含
    全部已完成任务（worker 线程已退出）的消耗，故此处不做死线程清理——
    僵尸条目在后续 _current_usage/reset（新批次任务开始记录时）被机会性
    清掉，保证长进程多批次场景下 global_usage 不被历史批次污染。

    Returns:
        全进程聚合的 TokenUsage。
    """
    total = TokenUsage()
    with _registry_lock:
        for usage in _registry.values():
            total.merge(usage)
    return total


# ─── AJ（2026-10-21）：缓存口径的共享读取 ────────────────────────────────────
#
# `cache_hits` / `cache_avoided_tokens` 由 record_cache_hit_usage 写入，但本仓的
# 成本读端（statistical_analysis / emse_stats_report / emse_stats_extensions）此前
# 从未消费这两个字段：缓存命中行因"真实 token 为 0"被 S11 读成**记账断裂**，在
# 成本汇总里被读成"零 / 未计价"——于是缓存密集的臂被误判 NOT_COMPUTABLE。
#
# 缓存命中是第三种记账状态：**既不是记账断裂，也不是"免费"**。真实 API 消耗为 0
# 是正确读数；"若未命中会消耗"的 token 另记在 cache_avoided_tokens（LRU 快路径
# 拿不到该值时只记命中次数，avoided 为 0）。下面两个读取器把"一行 / 一臂的缓存
# 口径是什么"一次判完，值域机制沿用 token 计数的同一套词汇（token_field_absent /
# token_not_count / token_not_finite / token_negative），四个消费点不再各写一遍。

_CACHE_FIELDS = ("cache_hits", "cache_avoided_tokens")


def count_reason(value: Any, field: str) -> str | None:
    """一个 token 计数是什么：非负整数；bool / 小数 / 非有限 / 字符串都不是计数。

    AI（2026-10-21）自 `experiments/emse_stats_extensions.token_count_reason` 迁到
    生产者模块，成为 token 三元组与缓存字段共用的值域谓词：`"100"` 不得被求和、
    `True` 不得当 1 收下、`-5` 不得让总量为负、`inf`/`nan` 不得混进区间估计。
    """
    if isinstance(value, bool):  # bool 是 int 的子类：计数不认布尔
        return f"token_not_count:{field}:bool"
    if isinstance(value, float) and not math.isfinite(value):
        return f"token_not_finite:{field}"
    if not isinstance(value, int):
        return f"token_not_count:{field}:{type(value).__name__}"
    if value < 0:
        return f"token_negative:{field}"
    return None


def _marker_reasons(usage: dict[str, Any], field_name: str, prefix: str) -> list[str]:
    """写拒绝披露的读取（AT）：缺席 / null / 空对象 = 无拒绝；非对象与坏计数点名。"""
    raw = usage.get(field_name)
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"{field_name}_not_object:{type(raw).__name__}"]
    reasons: list[str] = []
    for code, count in raw.items():
        if not isinstance(code, str) or not code:
            reasons.append(f"{field_name}_key_not_str:{type(code).__name__}")
            continue
        if count_reason(count, field_name) is not None or count == 0:
            reasons.append(f"{field_name}_count_invalid:{code}")
            continue
        reasons.append(f"{prefix}:{code}")
    return reasons


def token_write_rejection_reasons(usage: dict[str, Any]) -> list[str]:
    """单行 `token_usage` 的真实调用写拒绝披露（AT，2026-10-21）。"""
    return _marker_reasons(usage, "token_write_reasons", "token_write_rejected")


def cache_write_rejection_reasons(usage: dict[str, Any]) -> list[str]:
    """单行 `token_usage` 的缓存写拒绝披露（AT，2026-10-21）。"""
    return _marker_reasons(usage, "cache_write_reasons", "cache_write_rejected")


def cache_caliber(usage: dict[str, Any]) -> dict[str, Any]:
    """单行 `token_usage` 的缓存口径读数（AJ，2026-10-21）。

    - `present`：出现任一缓存字段（生产者 schema 代次判别——旧批次两个键都缺席，
      任何披露都必须保持逐字不变）；
    - `complete`：两个字段都在且值域合法——只有此时命中数 / 避免 token 才是可读的和；
    - `hits` / `avoided`：合法读数（缺席 / 坏值记 0，不折成部分和）；
    - `evidence`：任一字段合法且 > 0 —— 缓存命中为"有记账"提供正向证据；
    - `reasons`：坏值机制名；`missing`：半套 schema 的缺席机制名。

    值域坏不得被读成"没有缓存"：`cache_hits = -1` / `"2"` / `nan` 会进 `reasons`
    且不参与 `evidence`，调用方不得据此认定该行零命中。

    AT（2026-10-21）：写入口拒绝（`cache_write_reasons` 非空）同样让 `complete`
    为 False——命中数可信，但"避免的 token"是未知量，不得折成 0 参与金额。
    """
    markers = cache_write_rejection_reasons(usage)
    present = any(name in usage for name in _CACHE_FIELDS) or bool(markers)
    reading: dict[str, Any] = {
        "present": present,
        "complete": False,
        "hits": 0,
        "avoided": 0,
        "evidence": False,
        "reasons": list(markers),
        "missing": [],
    }
    if not present:
        return reading
    for name in _CACHE_FIELDS:
        if name not in usage:
            reading["missing"].append(f"token_field_absent:{name}")
            continue
        reason = count_reason(usage[name], name)
        if reason is not None:
            reading["reasons"].append(reason)
            continue
        reading["hits" if name == "cache_hits" else "avoided"] = usage[name]
        if usage[name] > 0:
            reading["evidence"] = True
    reading["complete"] = not reading["reasons"] and not reading["missing"]
    return reading


_ROW_TOKEN_FIELDS = ("total_tokens", "input_tokens", "output_tokens")


def row_token_counts(row: dict[str, Any]) -> tuple[tuple[int, int, int] | None, list[str]]:
    """单行 token 三元组：`(total, input, output)` 或 `(None, 机制名列表)`。

    AL（2026-10-21）自 `experiments/emse_stats_extensions._row_token_counts` 迁入：
    同一行在 ext 读不动、在报告 §4.1 却被 `or 0` 折成 0 并计价——值域判定只应
    写一遍。AI 的既有别名与外层调用零改动。

    键缺席不是 0（AB-11）：`token_usage` 缺席 / 为 null / 为非对象都不是"零 token"；
    字段缺席按 `token_field_absent:<field>` 点名，值域交 :func:`count_reason`。
    三项全部合法才返回三元组；任一不合法 → `(None, reasons)`，不得部分求和。

    AT（2026-10-21）：写入口拒绝标记（`token_write_reasons`）在场时，行内三元组
    只是"已收下部分"的和——同样不可读，机制名以 `token_write_rejected:` 前缀返回。
    """
    if "token_usage" not in row:
        return None, ["token_usage_absent"]
    usage = row["token_usage"]
    if not isinstance(usage, dict):
        return None, [f"token_usage_not_object:{type(usage).__name__}"]
    markers = token_write_rejection_reasons(usage)
    counts: list[int] = []
    reasons: list[str] = []
    for name in _ROW_TOKEN_FIELDS:
        if name not in usage:
            reasons.append(f"token_field_absent:{name}")
            continue
        reason = count_reason(usage[name], name)
        if reason is not None:
            reasons.append(reason)
            continue
        counts.append(usage[name])
    if markers or reasons:
        return None, markers + reasons
    total, inp, out = counts
    return (total, inp, out), []


def row_token_reading(row: dict[str, Any]) -> dict[str, Any]:
    """单行 token 三元组的成本口径读数（AM 语义，AN 迁入生产者模块）。

    - `token_usage` 键缺席或值为 `None` → `absent=True`、三元组按 0（历史口径；
      AK 的成本下界披露负责说明这些行）；
    - 非对象、或字段**在场**却不是计数 → `counts=None` + 机制名（读不动不是 0，
      不得折成部分和）；
    - 部分字段在场：全 0 / 全缺按 AE2 零行读；**任何正值 + 缺字段都是读不动**
      ——缺字段不是 0，正值的 in/out 部分和不得显示成总量；
    - 唯一例外：只有 `total_tokens` 缺席而 in/out 双全（且合法）——成本只需
      in/out，总量按两者之和（可核验），故该行仍可读。

    AN（2026-10-21）：本策略此前只住在 `statistical_analysis._row_cost_tokens`，
    写盘 `token_metrics` / 可信报告 / 旧批次兜底各自抄了一遍宽松版本——同一事实
    三个读数。现由本函数唯一判定，成本表保留别名。

    AT（2026-10-21）：写拒绝标记在场时，连"全 0 部分字段按历史零行读"的回退也
    不适用——被拒绝的量未知，零只是已收下部分的和。
    """
    if "token_usage" not in row:
        return {"absent": True, "usage": None, "counts": (0, 0, 0), "reasons": []}
    raw = row["token_usage"]
    if raw is None:
        return {"absent": True, "usage": None, "counts": (0, 0, 0), "reasons": []}
    markers = token_write_rejection_reasons(raw) if isinstance(raw, dict) else []
    counts, reasons = row_token_counts(row)
    if counts is not None:
        return {"absent": False, "usage": raw, "counts": counts, "reasons": []}
    if not markers and isinstance(raw, dict):
        present = {name: raw[name] for name in _ROW_TOKEN_FIELDS if name in raw}
        if all(count_reason(value, name) is None and value == 0 for name, value in present.items()):
            return {"absent": False, "usage": raw, "counts": (0, 0, 0), "reasons": []}
        if "total_tokens" not in present and {"input_tokens", "output_tokens"} <= set(present):
            inp = present["input_tokens"]
            out = present["output_tokens"]
            if count_reason(inp, "input_tokens") is None and count_reason(out, "output_tokens") is None:
                return {"absent": False, "usage": raw, "counts": (inp + out, inp, out), "reasons": []}
    return {"absent": False, "usage": raw, "counts": None, "reasons": reasons}


def row_total_token_reading(row: dict[str, Any]) -> dict[str, Any]:
    """单行“总 token”读数（AO，2026-10-21）：报告级总量消费者共用。

    与 :func:`row_token_reading` 的分工：成本口径要 in/out 才能计价，故三元组
    任一在场坏值即整行不可读；报告只展示“总 token”时，`total_tokens` 在场且
    合法即可读（旧 JSON 常见只有 total），不因 in/out 缺席而否定一个在场的
    总量。值域仍由 :func:`count_reason` 唯一判定，三个报告消费者不再各写
    `int(... or 0)` / `_safe_float(... or 0)`。

    - 整键缺席 / null → `absent=True`、`total=0`（历史 0）；
    - 非对象 / `total_tokens` 在场却不是计数 → `total=None` + 机制名；
    - `total_tokens` 缺席：全 0 / 全缺按历史零行；in/out 双全合法时取
      in+out（可核验）；其余部分和为不可读（正值的部分和不得冒充总量）；
    - `total_tokens` 与 in/out 双全且不符 → 总量仍可读，
      `contradiction=True`（报告披露，不阻断）。

    AT（2026-10-21）：`token_write_reasons` 非空 → 在场总量也只是已收下部分的和，
    `total=None`（写拒绝的量未知）。
    """
    if "token_usage" not in row or row["token_usage"] is None:
        return {"absent": True, "total": 0, "reasons": [], "contradiction": False}
    usage = row["token_usage"]
    if not isinstance(usage, dict):
        return {
            "absent": False,
            "total": None,
            "reasons": [f"token_usage_not_object:{type(usage).__name__}"],
            "contradiction": False,
        }
    markers = token_write_rejection_reasons(usage)
    if markers:
        return {"absent": False, "total": None, "reasons": markers, "contradiction": False}
    if "total_tokens" in usage:
        reason = count_reason(usage["total_tokens"], "total_tokens")
        if reason is not None:
            return {"absent": False, "total": None, "reasons": [reason], "contradiction": False}
        total = usage["total_tokens"]
        contradiction = False
        if "input_tokens" in usage and "output_tokens" in usage:
            inp_ok = count_reason(usage["input_tokens"], "input_tokens") is None
            out_ok = count_reason(usage["output_tokens"], "output_tokens") is None
            if inp_ok and out_ok and usage["input_tokens"] + usage["output_tokens"] != total:
                contradiction = True
        return {"absent": False, "total": total, "reasons": [], "contradiction": contradiction}
    present = {name: usage[name] for name in ("input_tokens", "output_tokens") if name in usage}
    if all(count_reason(value, name) is None and value == 0 for name, value in present.items()):
        return {"absent": False, "total": 0, "reasons": [], "contradiction": False}
    reasons = ["token_field_absent:total_tokens"]
    for name in ("input_tokens", "output_tokens"):
        if name not in usage:
            reasons.append(f"token_field_absent:{name}")
            continue
        reason = count_reason(usage[name], name)
        if reason is not None:
            reasons.append(reason)
    if len(reasons) > 1:
        return {"absent": False, "total": None, "reasons": reasons, "contradiction": False}
    return {
        "absent": False,
        "total": usage["input_tokens"] + usage["output_tokens"],
        "reasons": [],
        "contradiction": False,
    }


def aggregate_row_token_totals(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """多行“总 token”聚合（AO，2026-10-21）：报告级总量消费者的唯一求和。

    任一行不可读 → `total_tokens=None`（不给部分和）；机制名按行计数。
    整键缺席 / null 仍计历史 0（`n_absent_rows`）；`total_tokens` 与 in+out
    不符的行仍计入总量，只进 `n_contradiction_rows`（总量本身可读）。
    """
    n_rows = 0
    n_absent = 0
    n_unreadable = 0
    n_contradiction = 0
    total = 0
    readable = True
    reasons: dict[str, int] = {}
    for row in rows:
        n_rows += 1
        reading = row_total_token_reading(row)
        if reading["absent"]:
            n_absent += 1
        if reading["total"] is None:
            readable = False
            n_unreadable += 1
            for code in reading["reasons"]:
                reasons[code] = reasons.get(code, 0) + 1
            continue
        total += reading["total"]
        if reading["contradiction"]:
            n_contradiction += 1
    return {
        "n_rows": n_rows,
        "n_absent_rows": n_absent,
        "n_unreadable_rows": n_unreadable,
        "reading_reasons": dict(sorted(reasons.items())),
        "n_contradiction_rows": n_contradiction,
        "total_tokens": total if readable else None,
    }


def by_model_reason(by_model: dict[Any, Any], total: int) -> str | None:
    """单行 `by_model` 归因是否与 token 总量自洽（AL/AM 共用，2026-10-21）。

    - 键必须是字符串（非字符串键不得靠 `str()` 归一后混入同名模型）；
    - 值必须是 :func:`count_reason` 认的计数；
    - 求和必须等于该行总量（总量取 `total_tokens`；缺席时调用方可传 `input+output`）。

    返回第一个机制名或 None。报告侧（AL）只在 `total > 0` 时用非 None 读数阻断金额
    （零 token 行历史文本不变）；成本表聚合（AM）对 `total == 0` 的坏归因同样废金额
    ——`by_model` 声称有 token 而行内三元组为 0，按 0 计价会编出"免费"。
    """
    for model, value in by_model.items():
        if not isinstance(model, str):
            return f"by_model_key_not_str:{type(model).__name__}"
        reason = count_reason(value, f"by_model:{model}")
        if reason is not None:
            return reason
    if sum(by_model.values()) != total:
        return "by_model_sum_mismatch"
    return None


def cache_totals(usages: Iterable[Any]) -> dict[str, Any]:
    """多行缓存口径汇总（行值 = 结果行的 `token_usage` 原值）。

    任意行带缓存字段即 `present=True`；`complete` 要求这些行的两个字段全部合法。
    不完整时 `hits` / `avoided` 为 `None`（部分和不得冒充全额），机制名按行计数
    留在 `reasons` / `missing` 里。`n_hit_rows` 只数**合法正向证据**的行，无效值
    不计入。
    """
    n_rows = 0
    n_rows_with_fields = 0
    n_hit_rows = 0
    hits = 0
    avoided = 0
    complete = True
    present = False
    reasons: dict[str, int] = {}
    missing: dict[str, int] = {}
    for usage in usages:
        n_rows += 1
        if not isinstance(usage, dict):
            continue
        cal = cache_caliber(usage)
        if not cal["present"]:
            continue
        present = True
        n_rows_with_fields += 1
        if cal["evidence"]:
            n_hit_rows += 1
        hits += cal["hits"]
        avoided += cal["avoided"]
        if not cal["complete"]:
            complete = False
        for code in cal["reasons"]:
            reasons[code] = reasons.get(code, 0) + 1
        for code in cal["missing"]:
            missing[code] = missing.get(code, 0) + 1
    return {
        "present": present,
        "complete": present and complete,
        "n_rows": n_rows,
        "n_rows_with_fields": n_rows_with_fields,
        "n_hit_rows": n_hit_rows,
        "hits": hits if (present and complete) else None,
        "avoided": avoided if (present and complete) else None,
        "reasons": dict(sorted(reasons.items())),
        "missing": dict(sorted(missing.items())),
    }


def aggregate_row_token_usage(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """多行 token 记账聚合（AN，2026-10-21）——三个聚合消费者共用的唯一读数。

    此前写盘 `token_metrics`、可信验证报告、旧批次兜底各自用
    `(row.get("token_usage") or {}).get(..., 0)` 求和：非对象真值行 AttributeError，
    bool / 小数 / 字符串 / 负数 / nan 静默入总量，行内 `total_tokens` 与 in+out
    矛盾时一处取 in+out、一处取行内值——同一事实两个读数。

    口径（与 AM 的成本表一致，并区分"独立事实各自阻断"）：
    - 整键缺席 / null：历史 0（AE2 口径），计入 `n_absent_rows`；
    - 三元组在场坏值 / 部分正和：`input/output/total` 全为 None（不给部分和），
      行数与机制名进 `n_unreadable_rows` / `reading_reasons`；
    - `llm_calls` 是独立计数：缺席按 0，在场坏值只让 `llm_calls` 为 None
      （不连坐 token 总量）；坏 `llm_calls` 与坏三元组同样进可读性披露；
    - 行内 `total_tokens` 与 in+out 不符：token 总量仍可读（两者各自定义），
      只进 `n_contradiction_rows` / `contradiction_reasons`（AM 的金额级阻断在
      成本侧发生；本聚合没有金额，不得因矛盾丢掉可读的总量）；
    - 缓存沿用 :func:`cache_totals`：整批旧 schema 无缓存字段 → `present=False`
      （消费者按历史 0），半套 / 坏值 / 非对象行 → 命中与避免为 None。
    """
    n_rows = 0
    n_absent = 0
    n_unreadable = 0
    reading_reasons: dict[str, int] = {}
    n_contradiction = 0
    contradiction_reasons: dict[str, int] = {}
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    llm_calls = 0
    tokens_readable = True
    calls_readable = True
    cache_usages: list[Any] = []
    non_object_reasons: list[str] = []

    def _bump(counter: dict[str, int], code: str) -> None:
        counter[code] = counter.get(code, 0) + 1

    for row in rows:
        n_rows += 1
        raw = row.get("token_usage")
        cache_usages.append(raw)
        reading = row_token_reading(row)
        row_unreadable = False
        if reading["absent"]:
            n_absent += 1
        if reading["counts"] is None:
            tokens_readable = False
            row_unreadable = True
            for code in reading["reasons"]:
                _bump(reading_reasons, code)
        else:
            total, inp, out = reading["counts"]
            input_tokens += inp
            output_tokens += out
            total_tokens += total
            if not reading["absent"] and inp + out != total:
                n_contradiction += 1
                _bump(contradiction_reasons, "token_split_mismatch")
        if isinstance(raw, dict):
            if "llm_calls" in raw:
                reason = count_reason(raw["llm_calls"], "llm_calls")
                if reason is None:
                    llm_calls += raw["llm_calls"]
                else:
                    calls_readable = False
                    row_unreadable = True
                    _bump(reading_reasons, reason)
        elif raw is not None:
            # 非对象：调用计数同样不可读；三元组读取器已点名机制（类型在码里）。
            calls_readable = False
            row_unreadable = True
            non_object_reasons.extend(reading["reasons"])
        if row_unreadable:
            n_unreadable += 1

    cache = cache_totals(cache_usages)
    if non_object_reasons:
        reasons = dict(cache["reasons"])
        for code in non_object_reasons:
            _bump(reasons, code)
        cache = {
            **cache,
            "present": True,
            "complete": False,
            "hits": None,
            "avoided": None,
            "reasons": dict(sorted(reasons.items())),
        }

    return {
        "n_rows": n_rows,
        "n_absent_rows": n_absent,
        "n_unreadable_rows": n_unreadable,
        "reading_reasons": dict(sorted(reading_reasons.items())),
        "n_contradiction_rows": n_contradiction,
        "contradiction_reasons": dict(sorted(contradiction_reasons.items())),
        "input_tokens": input_tokens if tokens_readable else None,
        "output_tokens": output_tokens if tokens_readable else None,
        "total_tokens": total_tokens if tokens_readable else None,
        "llm_calls": llm_calls if calls_readable else None,
        "cache": cache,
    }


def token_metric_reading(metrics: Any, key: str, *, allow_float: bool = False) -> dict[str, Any]:
    """单份聚合 `token_metrics` 的字段读数（AP，2026-10-21）：报告侧汇总消费者的唯一判定。

    AO 的 :func:`row_total_token_reading` 读 details[] 的嵌套 `token_usage`；本函数
    读 run_benchmark 写盘的聚合 `token_metrics`（T1/B2 池化、B8 README、分析报告
    共用同形对象）。两者不可互换：聚合对象里的 `None` 是上游已拒绝（AN/AO），
    不是"字段缺席"，更不是 0。

    - 整份 metrics 缺席 / null：`absent=True`、`value=0`（AE2 历史口径）；
    - 非对象：`value=None` + `token_metrics_not_object:<T>`；
    - 字段缺席：`absent=True`、`value=0`（旧 schema 的口径）；
    - 字段在场为 null：`value=None` + `token_metric_unreadable:<key>`（上游拒绝）；
    - 计数在场坏值：`value=None` + :func:`count_reason` 机制名；
    - `allow_float=True`（派生的均值字段）：有限非负 int/float 可读，其余拒绝。
    """
    if metrics is None:
        return {"absent": True, "value": 0, "reasons": []}
    if not isinstance(metrics, dict):
        return {
            "absent": False,
            "value": None,
            "reasons": [f"token_metrics_not_object:{type(metrics).__name__}"],
        }
    if key not in metrics:
        return {"absent": True, "value": 0, "reasons": []}
    value = metrics[key]
    if value is None:
        return {"absent": False, "value": None, "reasons": [f"token_metric_unreadable:{key}"]}
    if allow_float:
        if isinstance(value, bool):
            return {"absent": False, "value": None, "reasons": [f"token_not_number:{key}:bool"]}
        if isinstance(value, float) and not math.isfinite(value):
            return {"absent": False, "value": None, "reasons": [f"token_not_finite:{key}"]}
        if not isinstance(value, (int, float)):
            return {"absent": False, "value": None, "reasons": [f"token_not_number:{key}:{type(value).__name__}"]}
        if value < 0:
            return {"absent": False, "value": None, "reasons": [f"token_negative:{key}"]}
        return {"absent": False, "value": value, "reasons": []}
    reason = count_reason(value, key)
    if reason is not None:
        return {"absent": False, "value": None, "reasons": [reason]}
    return {"absent": False, "value": value, "reasons": []}


def sum_token_metric_values(metrics: Iterable[Any], key: str) -> dict[str, Any]:
    """多份聚合 `token_metrics` 的同一字段求和（AP）：任一不可读 ⇒ None（不给部分和）。

    与 :func:`aggregate_row_token_totals` 的分工：那个按 details[] 行求和并处理
    三元组/缓存/矛盾；本函数只汇总已经写盘的聚合 metrics（T1/B2 的逐 seed 池化、
    B8 冒烟合计）。缺席的 metrics / 字段按历史 0（AE2），不贡献机制名；在场
    `None` / 坏值让该字段整列不可读，机制名计数随 `reasons` 返回。
    """
    total = 0
    n_readable = 0
    n_absent = 0
    n_unreadable = 0
    reasons: dict[str, int] = {}
    for item in metrics:
        reading = token_metric_reading(item, key)
        if reading["value"] is None:
            n_unreadable += 1
            for code in reading["reasons"]:
                reasons[code] = reasons.get(code, 0) + 1
            continue
        if reading["absent"]:
            n_absent += 1
            continue
        n_readable += 1
        total += reading["value"]
    return {
        "value": None if n_unreadable else total,
        "n_readable": n_readable,
        "n_absent": n_absent,
        "n_unreadable": n_unreadable,
        "reasons": dict(sorted(reasons.items())),
    }
