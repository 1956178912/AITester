"""P1-B（2026-10-12 独立评审落地）：评测去污染（decontamination）时间戳过滤。

背景（独立评审 C3 / 优化方案 P1-B，一手依据）：
    SWE-rebench（Badertdinov, Golubev et al., NeurIPS 2025，arXiv:2505.20411）
    实证：DeepSeek-V3 在 SWE-bench Verified 上 resolved rate 39.7%，在**去污染
    的同源基准**上降至 21.3%——**污染膨胀 −18.4pp**。根因是基准任务进入模型
    训练数据后，模型"记住答案"而非"解决问题"，分数虚高。对策：仅保留
    **创建时间晚于模型知识截止**的任务（时间戳切片）。

本模块提供纯函数层（零 IO、零 LLM、数据集加载器无关）：
    1. `parse_created_at`：把任务的创建时间字段归一为 epoch 秒（ISO 8601 /
       epoch 数值 / 日期only 三形态；不可解析 → None）；
    2. `filter_tasks_by_created_at`：按知识截止过滤任务，三种不可判定情形
       （无字段 / 不可解析 / 时区缺失）按模式分流；
    3. `decontamination_report`：审计报告（保留 / 剔除 / 无法验证计数）——
       "去污染切片"必须可审计：剔了多少、为什么剔，不能静默。

设计口径（保守，与 SWE-rebench 的 decontaminated 口径对齐）：
    - 默认 `mode="drop_unverifiable"`：无时间戳 / 不可解析的任务**不进**
      去污染切片（无法证明新鲜 = 不可信；防"launder"——把污染任务混进
      干净切片）；
    - `mode="keep_flagged"`：保留但在报告里单列 `unverifiable`（供敏感性
      分析：干净切片 vs 含未验证任务的分数差 = 污染膨胀的估计）；
    - cutoff 语义：任务创建时间 **严格晚于** cutoff 才保留（同日创建视为
      可能污染——模型知识截止通常按日期，同日任务无法证明先后）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

# 任务级创建时间字段的常见命名（按优先级探测；数据集可扩展）
_CREATED_AT_FIELDS: tuple[str, ...] = (
    "task_created_at",
    "created_at",
    "creation_date",
    "task_creation_date",
)

# 过滤模式（闭合集合，下游 schema 可校验）
_FILTER_MODES = ("drop_unverifiable", "keep_flagged")


def parse_created_at(value: Any) -> float | None:
    """把任务创建时间字段归一为 epoch 秒（不可解析 → None）。

    支持形态：
    - int/float：视为 epoch 秒（负数 / 非有限值 → None，防垃圾值）；
    - str：ISO 8601（含 "Z" 后缀 / 偏移 / 日期only "2025-06-01"）；
      date-only 按 **UTC 00:00:00** 解析（与"模型知识截止按日期"的
      粗粒度对齐；无法证明更细，宁保守）；
    - 其他类型 → None。

    时区缺失的 aware 字符串按 UTC 解释（基准任务时间戳通常为 UTC；
    错误时区假设的后果是边界任务误判，报告层的 unverifiable 计数会
    暴露异常规模）。
    """
    if isinstance(value, bool):  # bool 是 int 子类，先排除（True→epoch 1 无意义）
        return None
    if isinstance(value, (int, float)):
        import math

        if not math.isfinite(value) or value < 0:
            return None
        return float(value)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        # 退化形态：纯数字字符串按 epoch 秒
        try:
            epoch = float(text)
        except ValueError:
            return None
        import math

        if not math.isfinite(epoch) or epoch < 0:
            return None
        return epoch
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.timestamp()


def task_created_at(task: dict[str, Any]) -> float | None:
    """提取任务的创建时间 epoch 秒（按 _CREATED_AT_FIELDS 优先级探测）。"""
    if not isinstance(task, dict):
        return None
    for field in _CREATED_AT_FIELDS:
        if field in task:
            parsed = parse_created_at(task[field])
            if parsed is not None:
                return parsed
    return None


def filter_tasks_by_created_at(
    tasks: list[dict[str, Any]],
    cutoff_epoch: float,
    mode: str = "drop_unverifiable",
) -> list[dict[str, Any]]:
    """按知识截止过滤任务（仅保留创建时间**严格晚于** cutoff 的任务）。

    Args:
        tasks: 任务 dict 列表（含 _CREATED_AT_FIELDS 之一的字段）。
        cutoff_epoch: 模型知识截止的 epoch 秒（严格大于才保留）。
        mode: "drop_unverifiable"（默认）——无时间戳 / 不可解析的任务剔除；
              "keep_flagged"——保留但由 decontamination_report 单列
              （不静默：报告层必须披露未验证规模）。

    Returns:
        过滤后的任务列表（保序；不修改原列表）。
    """
    if mode not in _FILTER_MODES:
        raise ValueError(f"mode 必须 ∈ {_FILTER_MODES}，收到 {mode!r}")
    kept: list[dict[str, Any]] = []
    for task in tasks:
        created = task_created_at(task)
        if created is None:
            if mode == "keep_flagged":
                kept.append(task)  # 报告层单列 unverifiable，不静默
            continue
        if created > cutoff_epoch:  # 严格晚于（同日视为无法证明先后）
            kept.append(task)
    return kept


def decontamination_report(
    tasks: list[dict[str, Any]],
    cutoff_epoch: float,
) -> dict[str, Any]:
    """去污染切片的审计报告（可写入结果行；纯观测、零 IO）。

    返回：
        {
          "total": int,             # 输入任务数
          "kept": int,              # 去污染切片大小（严格晚于 cutoff）
          "dropped_before_cutoff": int,   # 早于等于 cutoff（可能污染）
          "unverifiable": int,      # 无时间戳 / 不可解析（无法证明新鲜）
          "kept_ratio": float,      # kept / total（total=0 → 0.0）
          "decontamination_rate": float,  # kept / (kept + dropped_before_cutoff)
                                          # （可判定子集的干净比例；无可判定 → 0.0）
        }
    口径纪律：`unverifiable > 0` 时任何"去污染分数"都必须同时披露该计数——
    静默丢弃不可验证任务会把"数据缺口"伪装成"干净"。
    """
    total = len(tasks)
    kept = dropped = unverifiable = 0
    for task in tasks:
        created = task_created_at(task)
        if created is None:
            unverifiable += 1
        elif created > cutoff_epoch:
            kept += 1
        else:
            dropped += 1
    decidable = kept + dropped
    return {
        "total": total,
        "kept": kept,
        "dropped_before_cutoff": dropped,
        "unverifiable": unverifiable,
        "kept_ratio": round(kept / total, 4) if total else 0.0,
        "decontamination_rate": round(kept / decidable, 4) if decidable else 0.0,
    }


__all__ = [
    "decontamination_report",
    "filter_tasks_by_created_at",
    "parse_created_at",
    "task_created_at",
]
