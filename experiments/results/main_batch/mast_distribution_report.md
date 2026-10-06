# MAST 失效模式分布报告（trace 离线聚合——AG1）

- 数据源：`experiments/results/main_batch/traces`（963 个 trace 文件，损坏 0 个——损坏计入各臂 damaged，不静默丢弃）
- 判定口径：src/observability/agent_telemetry.match_failure_patterns（Y2 MAST 14 类映射；budget_early_stop / 伞形两类无对应类显式 None）
- 观测单元 = 单 trace 文件（单任务×单臂×单次运行）；命中率 = 命中文件数 / 该臂有效文件数
- 纯离线静态匹配：零 LLM / 零网络；本报告为衍生工件，可用本脚本从入库 trace 逐位复算

**解读警示（诚实口径）**：模式与 error_category 值来自 trace 中debugger 节点事件的落盘字段——plain_llm / plain_llm_df 臂无 debugger 节点，trace 天然不含该字段，其"零命中"反映 **trace schema 差异而非零失败**（plain_llm_df 的 44.8% 任务未检出是既有结论）；跨臂对比仅在 aitester 与历史含 debugger 节点的批次内有效。

## 臂：aitester

有效文件数：326（损坏 0）

| 失效模式 | MAST 类 | MAST 大类 | 命中文件数 | 命中率 |
|----------|---------|-----------|------------|--------|
| known_error_category_hit | — | — | 178 | 54.6% |

### error_category 原始值分布（按文件计，每文件每类别至多计 1）

| error_category | 文件数 | 占比 |
|----------------|--------|------|
| assertion | 75 | 23.0% |
| runtime | 51 | 15.6% |
| type_error | 37 | 11.3% |
| syntax | 11 | 3.4% |
| unknown | 6 | 1.8% |
| index_error | 4 | 1.2% |
| timeout | 3 | 0.9% |


## 臂：plain_llm

有效文件数：326（损坏 0）

（零模式命中）

## 臂：plain_llm_df

有效文件数：261（损坏 0）

（零模式命中）

## 臂：single_agent

有效文件数：50（损坏 0）

（零模式命中）

---
*报告生成：experiments/mast_trace_analysis.py（AG1，2026-10-06）*
