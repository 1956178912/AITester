"""
P1 流氓 agent 行为监控（2026-09-29 批次）。

外部参照（微软 Agent Governance Toolkit agent-sre + OWASP ASI-10 流氓 agent
检测）：自主 agent 的三类故障信号——
  1. 工具调用频率 z-score（失控循环：反复调用相同工具而燃烧 token）；
  2. 动作熵（行为漂移：重复性过高的决策序列）；
  3. 能力违规（agent 使用了其能力配置之外的工具）；
三者任一越限即标记"疑似失控"，由调用方决定隔离/升级人工（本模块只报
警不自动熔断，保守口径）。

设计约束：
- 纯数据层（零 LLM 成本、零外发）：调用方按 agent 会话上报事件
  （report_tool_call），本模块维护滑动窗口统计；
- 阈值可配置（环境变量 + 构造参数，测试可注入）；z-score 按滑动窗口内
  工具调用计数分布计算，样本数 < 4 时 z-score 恒 0（保守：小样本不判异）；
- 能力配置（allowed_tools）缺省为空 = 不检查能力违规（历史口径零变化）；
- 结果消费：check() 返回结构化 findings（非空即异常），供 workflow 收尾
  写 reports / state（P2 批次接 CI 阻断）。
"""

from __future__ import annotations

import os
import threading
from collections import Counter, deque
from dataclasses import dataclass, field


class _ConfigDefaults:
    """默认阈值（环境变量可覆盖，构造参数优先）。"""

    WINDOW_SIZE = 50          # 滑动窗口事件数（z-score / 熵统计口径）
    ZSCORE_LIMIT = 3.0        # 工具调用频率 z-score 越限阈值
    ENTROPY_FLOOR = 0.5       # 动作熵下限（bits；序列过重复 → 疑似漂移）
    ENTROPY_CEIL = 4.0       # 动作熵上限（bits；序列过度混乱 → 疑似漂移）
    CAPABILITY_VIOLATION_LIMIT = 0   # 能力违规计数阈值（0 = 首次违规即报）

    @classmethod
    def _env(cls, name: str, default: str) -> str:
        return os.getenv(name, default)

    @classmethod
    def window_size(cls) -> int:
        try:
            return max(8, int(cls._env("ROGUE_AGENT_WINDOW_SIZE", str(cls.WINDOW_SIZE))))
        except ValueError:
            return cls.WINDOW_SIZE

    @classmethod
    def zscore_limit(cls) -> float:
        try:
            return float(cls._env("ROGUE_AGENT_ZSCORE_LIMIT", str(cls.ZSCORE_LIMIT)))
        except ValueError:
            return cls.ZSCORE_LIMIT

    @classmethod
    def entropy_bounds(cls) -> tuple[float, float]:
        try:
            lo = float(cls._env("ROGUE_AGENT_ENTROPY_FLOOR", str(cls.ENTROPY_FLOOR)))
            hi = float(cls._env("ROGUE_AGENT_ENTROPY_CEIL", str(cls.ENTROPY_CEIL)))
        except ValueError:
            lo, hi = cls.ENTROPY_FLOOR, cls.ENTROPY_CEIL
        return lo, hi

    @classmethod
    def capability_violation_limit(cls) -> int:
        try:
            return max(0, int(cls._env("ROGUE_AGENT_CAPABILITY_VIOLATION_LIMIT", "0")))
        except ValueError:
            return cls.CAPABILITY_VIOLATION_LIMIT


@dataclass
class AgentEvent:
    """一次 agent 工具调用事件（上报输入）。"""

    agent_id: str
    tool: str
    ts: float | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class RogueFinding:
    """流氓行为 finding（check() 输出）。"""

    agent_id: str
    kind: str          # "zscore" / "entropy" / "capability"
    detail: str
    metric: float


class RogueAgentMonitor:
    """按 agent_id 维护滑动窗口事件统计的监控器（线程安全）。

    用法：
        monitor = RogueAgentMonitor(allowed_tools={"read_file", "run_tests"})
        monitor.report_tool_call(AgentEvent(agent_id="dbg-1", tool="read_file"))
        findings = monitor.check("dbg-1")
        # findings 非空 → 隔离/升级人工（调用方决定，本模块不自动熔断）
    """

    def __init__(
        self,
        allowed_tools: set[str] | None = None,
        *,
        window_size: int | None = None,
        zscore_limit: float | None = None,
        entropy_floor: float | None = None,
        entropy_ceil: float | None = None,
        capability_violation_limit: int | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, deque[AgentEvent]] = {}
        self._capability_violations: Counter = Counter()
        self._allowed_tools: frozenset[str] = frozenset(allowed_tools or set())
        self._window_size = window_size or _ConfigDefaults.window_size()
        self._zscore_limit = zscore_limit if zscore_limit is not None else _ConfigDefaults.zscore_limit()
        floor, ceil = _ConfigDefaults.entropy_bounds()
        self._entropy_floor = entropy_floor if entropy_floor is not None else floor
        self._entropy_ceil = entropy_ceil if entropy_ceil is not None else ceil
        self._capability_limit = (
            capability_violation_limit
            if capability_violation_limit is not None
            else _ConfigDefaults.capability_violation_limit()
        )

    def report_tool_call(self, event: AgentEvent) -> None:
        """上报一次工具调用（滑动窗口保留最近 _window_size 条 + 违规计数）。"""
        with self._lock:
            window = self._events.setdefault(event.agent_id, deque(maxlen=self._window_size))
            window.append(event)
            # 能力违规：agent 声明了能力配置且工具越界 → 计数
            if self._allowed_tools and event.tool not in self._allowed_tools:
                self._capability_violations[event.agent_id] += 1

    def check(self, agent_id: str) -> list[RogueFinding]:
        """对单个 agent 做三类信号检测（z-score / 熵 / 能力违规）。

        Returns:
            findings 列表（可能为空）；顺序：zscore → entropy → capability。
        """
        findings: list[RogueFinding] = []
        with self._lock:
            window = list(self._events.get(agent_id, ()))
            violations = self._capability_violations.get(agent_id, 0)

        # 1. 工具调用频率 z-score：窗口内**逐事件**工具标签的 one-hot 均值
        #    向量上计算逐工具偏离（失控循环 = 某工具调用频率相对其余工具
        #    极端偏离）；样本数 < 4 时跳过（保守：小样本不判异）。
        if len(window) >= 4:
            n = len(window)
            distinct = len({e.tool for e in window})
            tool_counts: Counter = Counter(e.tool for e in window)
            if distinct > 1:
                for tool, cnt in tool_counts.items():
                    expected = n / distinct
                    variance = sum((c - expected) ** 2 for c in tool_counts.values()) / len(tool_counts)
                    stdev = variance**0.5
                    if stdev > 0:
                        z = (cnt - expected) / stdev
                        if z >= self._zscore_limit:
                            findings.append(
                                RogueFinding(
                                    agent_id=agent_id,
                                    kind="zscore",
                                    detail=(
                                        f"工具 '{tool}' 调用 {cnt} 次，相对窗口内各工具均值 "
                                        f"{expected:.1f} 偏离 z={z:.2f} 越限（失控循环信号）"
                                    ),
                                    metric=z,
                                )
                            )
                            break  # 取最极端的一个工具即可（避免重复报告）

        # 2. 动作熵：窗口内工具序列的香农熵（bits）。过低 = 重复性失控，
        #    过高 = 混乱漂移（无收敛策略）。样本 < 2 时跳过（小样本不判异）。
        if len(window) >= 2:
            seq = [e.tool for e in window]
            n = len(seq)
            freq = Counter(seq)
            entropy = -sum((c / n) * _log2(c / n) for c in freq.values())
            if entropy < self._entropy_floor or entropy > self._entropy_ceil:
                findings.append(
                    RogueFinding(
                        agent_id=agent_id,
                        kind="entropy",
                        detail=f"工具序列熵 {entropy:.3f} bits 越出 [{self._entropy_floor}, {self._entropy_ceil}] 区间",
                        metric=entropy,
                    )
                )

        # 3. 能力违规：agent 使用了能力配置之外的工具
        if violations > 0 and violations >= self._capability_limit:
            with self._lock:
                used = sorted({e.tool for e in window if e.tool not in self._allowed_tools})
            findings.append(
                RogueFinding(
                    agent_id=agent_id,
                    kind="capability",
                    detail=f"{violations} 次越界工具调用（越界工具：{', '.join(used) or '未知'}）",
                    metric=float(violations),
                )
            )
        return findings

    def reset(self, agent_id: str) -> None:
        """清空某 agent 的窗口与违规计数（新会话 / 测试隔离）。"""
        with self._lock:
            self._events.pop(agent_id, None)
            self._capability_violations.pop(agent_id, None)


def _log2(x: float) -> float:
    """log2（导入 math 仅用于熵计算，惰性函数避免模块头无谓 import）。"""
    import math

    return math.log2(x)


# ─── 进程内单例（--parallel 共享观测口径，与 semantic_cache 同模式）─────────
_default_monitor: RogueAgentMonitor | None = None
_monitor_lock = threading.Lock()


def get_rogue_monitor(allowed_tools: set[str] | None = None) -> RogueAgentMonitor:
    """获取进程内流氓 agent 监控单例（allowed_tools 提供时重建，测试注入）。"""
    global _default_monitor
    with _monitor_lock:
        if _default_monitor is None or allowed_tools is not None:
            _default_monitor = RogueAgentMonitor(allowed_tools=allowed_tools)
        return _default_monitor


def reset_rogue_monitor() -> None:
    """重置进程内监控单例（测试隔离）。"""
    global _default_monitor
    with _monitor_lock:
        _default_monitor = None
