# Q05 交互中心失败归因：跨批次分层聚合（2026-10-30）

> 口径：只读 `experiments/results/**/benchmark_*.json` 的既有 `failure_bucket_distribution.{edge_counts,fault_side_counts}`，不产生新归因判定。聚合单元 = 批次目录 × 臂。

- 批次文件：46 份（含归因字段 44 份）；聚合单元 65 个
- 可分类任务行合计：3097（编排臂 1088 / 对照臂 2009）

## 分层汇总（结论口径）

| 层 | 单元数 | 任务行 | planner→gen | gen→exec | debugger→exec | harness | uncategorized |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 编排臂 (aitester) | 26 | 1088 | 43 | 1 | 206 | 838 | 0 |
| 对照臂 | 39 | 2009 | 6 | 0 | 0 | 690 | 1313 |
| 全量(仅对账) | 65 | 3097 | 49 | 1 | 206 | 1528 | 1313 |

## 结构发现

1. **对照臂几乎不产出交互边归因**（维度只在编排链路上被标注）——对照臂 uncategorized = 2003
   行中的绝大多数；跨臂合并会把「维度没被触发」读成「维度测过且为 0」，故结论只取编排臂层。
2. 编排臂内 edge 分布（占比按编排臂任务行 1088 计）：
   planner_to_generator 43（3.95%）、debugger_to_executor 206（18.93%）、harness 838（77.02%）、generator_to_executor 1（0.09%）。
3. fault_side：environment 与 grader 两侧在全部工件中恒为 0（标注器当前不产出这两类）——读「0」前必须先读这条，这是标注器覆盖上限，不是实测为零。

## 工件

- 机器可读：`q05_interaction_attribution_20261030/Q05_AGGREGATE.json`
- 本摘要：`q05_interaction_attribution_20261030/Q05_SUMMARY.md`
