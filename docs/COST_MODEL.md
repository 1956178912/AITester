# 成本模型（Cost Model）

> 最后更新：2026-10-26 · English: [COST_MODEL.en.md](COST_MODEL.en.md)

本文只定义成本的**计算口径、单位与上限**。价目与批次读数的唯一事实源分别是
[`experiments/price_table.json`](../experiments/price_table.json) 与
[`BASELINE.yaml`](../BASELINE.yaml)；本文不复制批次成本数字。

## 1. 价目来源

| 来源 | 内容 | 使用口径 |
|------|------|----------|
| `experiments/price_table.json` | 模型级 `input_per_mtok` / `output_per_mtok`（USD / 百万 token） | 须填 `currency` / `source` / `as_of`；当前仅登记 DeepSeek 官方 deepseek-flash |
| `COST_USD_PER_1K` | 价目表缺失时的回退混合价（USD / 千 token） | 默认未配置；仅大于 0 时生效 |
| 批次 provenance 的 `usage` | 每次调用的真实 token 三元组 | 只统计缓存未命中的真实 API 消耗 |

当前登记：deepseek-flash 的 input 0.3 / output 1.2 USD 每百万 token，
`currency=USD`，`source` 为 DeepSeek 官方价目页，`as_of=2026-10-06`（峰时全额价）。

未登记模型、币种不可判定、价格字段为 null → **未计价**：不得按 0 计入均值，
也不得外推估计。

## 2. 每任务成本公式

```text
cost_task = Σ_calls ( input_tokens × price_in + output_tokens × price_out ) / 1_000_000
```

- 单位：token 为个；`price_in` / `price_out` 为 USD / 百万 token；结果为 USD。
- 回退口径：`cost_task = (input_tokens + output_tokens) / 1000 × COST_USD_PER_1K`。
- 调用数按实际 LLM 调用计：多智能体路径 = Planner + Generator + 每轮 Debugger
  + 可选 FaultLocalizer / ExpertPool；基线路径通常为单次生成。
- 成本是**标准价估算**，不是供应商账单；报告须同时给出 `source` 与 `as_of`。
- 批次成本 = 各任务成本之和；任务均值 = 批次成本 / 任务数。失败或超时任务
  按已发生调用计入，不重摊到成功任务。

## 3. 缓存与批量折扣

- **响应缓存**：LLM 缓存（默认 `~/.cache/aitester/llm`）命中不产生 API 调用，
  记 `cache_hits` 与独立的 `cache_avoided_tokens`，不进入真实 token 三元组，
  因而不计费。
- **缓存命中价与错峰价**：DeepSeek 官方另有缓存命中价（0.006 USD / 百万
  token）与非峰时半价；价目表按峰时全额登记、不做扣减，登记成本是**上界**。
- **批量折扣**：仓库不应用批量折扣；同批运行多个任务不改变单价。
- **冷启动 vs 热缓存**：含 venv 创建与依赖安装的首次运行是冷启动；热缓存只
  复用 LLM 响应与 venv，不降低已发生调用的单价。

## 4. 未知值与上限

| 项 | 口径 |
|----|------|
| 未登记模型的单价 | 未测；`estimate_usd` 返回 `unpriced`，不按 0 计 |
| 估算与供应商账单的差额 | 未测；只做 standard-price 估算 |
| 任务 token / USD 硬上限 | `COST_BUDGET_ENABLE`（默认关）；`COST_BUDGET_TOKENS` / `COST_BUDGET_USD` 为 0 表示不限 |
| 单次调用墙钟上限 | `LLM_CALL_BUDGET_SECONDS`（默认 600s）；超限快速失败，不继续发请求 |
| 批后处理墙钟告警 | `AITESTER_POSTPROCESS_WARN_S`（默认 600s）；只告警，不改判分 |

本文读数与 `BASELINE.yaml` 冲突时，以 `BASELINE.yaml` 为登记权威；先复核
价目表 `as_of` 与批次 `usage`，再同步文档与登记册。
