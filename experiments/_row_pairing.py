"""按 task_id 选择"最新记录"的共享原语（A07 单一事实来源）。

背景（2026-10-18 第三方复核报告 A07 残留，2026-10-19 补修）：

批次加载顺序 = 批次文件名内嵌时间戳降序（`_sort_batch_files_deterministic`），
因此同一 `task_id` 的**首见行即最新记录**。三条统计消费路径必须共用同一口径：

1. **首见占位，不看字段值**——最新记录即使不可测（`None`）也占位，
   旧批次的可测值不得顶替（M1 诚实指标：最新记录不可测 = 该任务整体不可测）；
2. **None 过滤在去重之后单独进行**——`None` 表示"无 gold 材料、分母外"，
   不是"测量为失败"，不能混入分母；
3. **元数据与数值同源**——模板聚类的 `pattern_name` 必须取同一条最新行，
   否则旧模板元数据会取代最新元数据。

历史实现分叉：`_pair_by_task` 与 `bayesian_paired.paired_contingency` 已按上述
契约修复，但 `template_cluster_sensitivity._binary` 仍"先跳过 None 再后写覆盖"，
且用 `{r["task_id"]: r for r in rows}` 建元数据字典（同样后写覆盖）。后果：

- 最新 `None` 被旧 `0` 顶替 → 不可测任务被并入分母；
- 最新可测值被旧值覆盖 → discordant 计数与簇内均值方向改变；
- 模板元数据取到旧行 → 簇归属漂移。

本模块把选择逻辑收敛为单点，三个消费方共用，防止再次漂移。
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def latest_rows_by_task(rows: Iterable[dict[str, Any]]) -> dict[Any, dict[str, Any]]:
    """按 `task_id` 保留首见行（调用方保证"最新批次在前"）。

    Args:
        rows: 行级结果列表；同一 `task_id` 的多行按输入顺序"首见胜出"。

    Returns:
        `{task_id: 最新行}`。缺 `task_id`（None/空串）的行不参与配对，
        直接丢弃——与 `_pair_by_task` 的历史口径一致（归档主批实测 0 行）。

    Notes:
        本函数**不**看任何字段值：即使最新行的目标字段为 `None`，它仍占位，
        以阻止旧批次的可测值顶替。None 过滤由调用方在去重后单独执行。
    """
    latest: dict[Any, dict[str, Any]] = {}
    for row in rows:
        tid = row.get("task_id")
        if not tid or tid in latest:
            continue
        latest[tid] = row
    return latest


def latest_binary_by_task(
    rows: Iterable[dict[str, Any]],
    field: str = "detection_rate",
) -> tuple[dict[Any, int], dict[Any, dict[str, Any]]]:
    """去重后排除 None，返回 (可测二值映射, task_id→最新行)。

    二值口径与 `_pair_by_task` / `paired_contingency` 一致：真值 → 1，
    假值 → 0；`None` 在占位去重**之后**排除（该任务整体不可测）。

    Args:
        rows: 行级结果列表（最新批次在前）。
        field: 二值结果字段名（`detection_rate` / `passed` / `repair_rate`）。

    Returns:
        `(binary, latest)`：`binary[task_id] ∈ {0, 1}`；`latest` 为最新行映射，
        供调用方从**同一条**记录读取元数据（模板簇归属）。
    """
    latest = latest_rows_by_task(rows)
    binary: dict[Any, int] = {}
    for tid, row in latest.items():
        value = row.get(field)
        if value is None:
            continue
        binary[tid] = 1 if value else 0
    return binary, latest
