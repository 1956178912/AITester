"""P1-B（2026-10-12 独立评审落地）：MTTR-A 式认知恢复延迟（SRE 口径指标）。

背景（独立评审 C3 / 优化方案 P1-B，差异化机会）：
    MTTR-A（Mean Time-to-Recovery for Agentic Systems）为多智能体系统提供
    "认知恢复延迟"量化框架——度量的是**推理漂移被检测到恢复一致操作的时间**，
    而非基础设施修复时间。LangGraph 模拟显示自动反射恢复中位约 6.21s
    （一手数据稀薄：VIGIL 仅 n=1 案例、ESBMC-AI 摘要无数值——自修复 SRE
    口径的一手量化当前是**空白**，先占机会）。

本模块把该口径落到 AITester 的多智能体工作流，定义两个纯测量量：

    1. **Detection Latency（检测延迟）**：从"测试失败被观测到"到
       "首次有效红测试生成"的墙钟时间——对应 MTTR-A 的"漂移检测"段。
       "有效红测试"= 在缺陷代码上失败（红）且非过红（特异性门通过 /
       无特异性门时保守以"红"计并标注 unverified_specificity）。
    2. **Reconfiguration Latency（重配延迟）**：从"补丁合成"到
       "gold 裁决通过"的墙钟时间——对应 MTTR-A 的"恢复一致操作"段。

保守口径（测量纪律，与 MDO 的诚实披露同族）：
    - 任一端点事件缺失 → 对应延迟为 **None**（"不可测量"），绝不以 0.0
      冒充（零延迟 = 神话；None = 诚实缺口，下游按缺失处理）；
    - 时钟必须同源（同一会话的 time.time() 序列）；跨源时钟混用 →
      ValueError（负延迟是数据错误，不是快恢复）；
    - 聚合只报**实际有测量**的任务数（n_measured），不把 None 当 0 平均。

事件 schema（工作流埋点协议，供 executor / debugger / 判定节点填充）：
    RecoveryEvent = {
        "kind": "failure_observed"          # 测试失败被观测（executor 首红）
              | "effective_red_generated"   # 首次有效红测试生成
              | "patch_synthesized"         # 补丁合成完成（debugger 产出）
              | "gold_adjudicated_pass"     # gold 裁决通过
              | "gold_adjudicated_fail",    # gold 裁决未过（非恢复端点）
        "ts": float,                        # time.time() epoch 秒（必填）
        "iteration": int,                   # 迭代轮次（可选，供分层报告）
    }

状态字段建议（接线批次）：state["recovery_events"]: list[RecoveryEvent]，
由 _executor_node / _generator_node / _debugger_node / M1 判定点 append；
本模块纯函数消费，不 import graph 层（避免循环依赖）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 事件类型闭合集合（下游 schema / 测试锁定）
_EVENT_KINDS = (
    "failure_observed",
    "effective_red_generated",
    "patch_synthesized",
    "gold_adjudicated_pass",
    "gold_adjudicated_fail",
)

# 两个延迟量的端点事件对（有序：先 start 后 end）
_DETECTION_PAIR = ("failure_observed", "effective_red_generated")
_RECONFIGURATION_PAIR = ("patch_synthesized", "gold_adjudicated_pass")


@dataclass
class RecoveryLatency:
    """单任务的认知恢复延迟测量（端点缺失 → None，不冒充 0.0）。"""

    detection_latency: float | None = None
    reconfiguration_latency: float | None = None
    # 未验证特异性标记：无特异性门时 effective_red 只是"红"，未证明缺陷特异
    specificity_unverified: bool = False
    events_seen: int = 0

    def as_dict(self) -> dict[str, Any]:
        """序列化为结果行字段（None 恒输出 None——下游不得误读为 0）。"""
        return {
            "detection_latency": self.detection_latency,
            "reconfiguration_latency": self.reconfiguration_latency,
            "specificity_unverified": self.specificity_unverified,
            "events_seen": self.events_seen,
        }


def _first_ts(events: list[dict[str, Any]], kind: str) -> float | None:
    """某类事件的**首次**时间戳（事件列表按发生序；缺 kind → None）。"""
    for event in events:
        if event.get("kind") == kind:
            ts = event.get("ts")
            if isinstance(ts, (int, float)) and not isinstance(ts, bool):
                return float(ts)
    return None


def compute_recovery_latency(
    events: list[dict[str, Any]] | None,
    specificity_verified: bool = True,
) -> RecoveryLatency:
    """从事件序列计算单任务的认知恢复延迟（端点缺失 → None）。

    Args:
        events: RecoveryEvent 列表（按发生序；None / 空 → 全 None）。
        specificity_verified: effective_red_generated 是否经过特异性门
            （False 时仅知"红"、未证缺陷特异 → specificity_unverified=True，
            检测延迟仍计算但带标记——消费方须知情）。

    Returns:
        RecoveryLatency；任何端点缺失对应项为 None（ honest gap ）。

    Raises:
        ValueError: 事件含未知 kind 或端点逆序（负延迟 = 数据错误）。
    """
    result = RecoveryLatency(specificity_unverified=not specificity_verified)
    if not events:
        return result
    result.events_seen = len(events)
    for event in events:
        if event.get("kind") not in _EVENT_KINDS:
            raise ValueError(f"未知事件 kind: {event.get('kind')!r}（闭合集合 {_EVENT_KINDS}）")

    def _latency(pair: tuple[str, str]) -> float | None:
        start = _first_ts(events, pair[0])
        end = _first_ts(events, pair[1])
        if start is None or end is None:
            return None
        if end < start:
            raise ValueError(f"端点逆序（负延迟 = 数据错误）: {pair[0]}@{start} → {pair[1]}@{end}")
        return end - start

    result.detection_latency = _latency(_DETECTION_PAIR)
    result.reconfiguration_latency = _latency(_RECONFIGURATION_PAIR)
    return result


@dataclass
class RecoveryLatencySummary:
    """多样本聚合（None 不计入——平均只覆盖实际有测量的任务）。"""

    n_total: int = 0
    n_detection_measured: int = 0
    n_reconfiguration_measured: int = 0
    detection_median: float | None = None
    detection_mean: float | None = None
    reconfiguration_median: float | None = None
    reconfiguration_mean: float | None = None
    specificity_unverified_n: int = 0
    per_task: list[RecoveryLatency] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "n_total": self.n_total,
            "n_detection_measured": self.n_detection_measured,
            "n_reconfiguration_measured": self.n_reconfiguration_measured,
            "detection_median": self.detection_median,
            "detection_mean": self.detection_mean,
            "reconfiguration_median": self.reconfiguration_median,
            "reconfiguration_mean": self.reconfiguration_mean,
            "specificity_unverified_n": self.specificity_unverified_n,
        }


def summarize_recovery_latencies(
    per_task: list[RecoveryLatency],
) -> RecoveryLatencySummary:
    """聚合多个任务的恢复延迟（中位数为主口径——延迟分布右偏，均值失真）。

    MTTR-A 的一手参考口径即中位数（LangGraph 模拟 ~6.21s median）；
    None 样本不进任何统计（"不可测量"不是"零延迟"）。
    """
    detections = [r.detection_latency for r in per_task if r.detection_latency is not None]
    reconfigs = [r.reconfiguration_latency for r in per_task if r.reconfiguration_latency is not None]

    def _median(values: list[float]) -> float:
        ordered = sorted(values)
        n = len(ordered)
        mid = n // 2
        return ordered[mid] if n % 2 else (ordered[mid - 1] + ordered[mid]) / 2

    return RecoveryLatencySummary(
        n_total=len(per_task),
        n_detection_measured=len(detections),
        n_reconfiguration_measured=len(reconfigs),
        detection_median=round(_median(detections), 4) if detections else None,
        detection_mean=round(sum(detections) / len(detections), 4) if detections else None,
        reconfiguration_median=round(_median(reconfigs), 4) if reconfigs else None,
        reconfiguration_mean=round(sum(reconfigs) / len(reconfigs), 4) if reconfigs else None,
        specificity_unverified_n=sum(1 for r in per_task if r.specificity_unverified),
        per_task=list(per_task),
    )


__all__ = [
    "RecoveryLatency",
    "RecoveryLatencySummary",
    "compute_recovery_latency",
    "summarize_recovery_latencies",
]
