# 成本模型（Cost Model）

> 最后更新：2026-11-04 · English: [COST_MODEL.en.md](COST_MODEL.en.md)

本文只定义成本的**计算口径、单位与上限**。价目与批次读数的唯一事实源分别是
[`experiments/price_table.json`](../experiments/price_table.json) 与
[`BASELINE.yaml`](../BASELINE.yaml)；本文不复制批次成本数字。

## 1. 价目来源

| 来源 | 内容 | 使用口径 |
|------|------|----------|
| `experiments/price_table.json` | 模型级 `input_per_mtok` / `output_per_mtok`（**登记币种** / 百万 token） | 须填 `currency` / `source` / `as_of`；当前登记 deepseek-flash 与 mimo-v2.6-pro 两家，均为 `currency=CNY` |
| `COST_USD_PER_1K` | 价目表缺失时的回退混合价（千 token） | 默认未配置；仅大于 0 时生效。变量名是历史遗留，2026-11-04 起数值按**基准币种 CNY** 解释 |
| 批次 provenance 的 `usage` | 每次调用的真实 token 三元组 | 只统计缓存未命中的真实 API 消耗 |

当前登记（峰时/标准全额价，均为保守上界）：deepseek-flash input 2 / output 8 CNY
每百万 token（`as_of=2026-11-04`，DeepSeek 官方价目页）；mimo-v2.6-pro input 3 /
output 6 CNY 每百万 token（`as_of=2026-10-21`，MiMo 官方按量付费页）。非峰时半价、
缓存命中价与批量推理半价**均不采用**。

未登记模型、币种不可判定、价格字段为 null → **未计价**：不得按 0 计入均值，
也不得外推估计。

## 2. 每任务成本公式

```text
cost_task = Σ_calls ( input_tokens × price_in + output_tokens × price_out ) / 1_000_000
```

- 单位：token 为个；`price_in` / `price_out` 为**价目表登记币种**（当前 CNY）每百万
  token；结果金额即该币种。生产记账走
  `pricing.estimate_in_table_currency()`，返回 `(amount, currency, source)`，
  **不做汇率换算**（本项目无汇率事实源）。
- `pricing.estimate_usd()` 保留历史"只认 `currency=USD`"契约，作为美元列入口；价目表
  改为 CNY 后它对该模型返回 `unpriced`。调用方与报表**不得**把 CNY 金额按美元符号打印。
- 回退口径：`cost_task = (input_tokens + output_tokens) / 1000 × COST_USD_PER_1K`。
- 调用数按实际 LLM 调用计：多智能体路径 = Planner + Generator + 每轮 Debugger
  + 可选 FaultLocalizer / ExpertPool；基线路径通常为单次生成。
- `LLM_THINKING_MODE` 默认 **`disabled`**（2026-11-04 用户更正口径）。思维链 token 计入
  输出计费，是成本的主项：同一 prompt 单条 Generator 调用实测 thinking-on 输出
  deepseek 10,859（其中思维链 9,664）→ disabled 709、mimo 9,640（思维链 8,407）→
  disabled 342，即 −92.4% / −94.1%。`reasoning_effort` 档位**不是**跨模型等价旋钮
  （实测 mimo 的 `max` 比默认更短，非单调），故批量对比只固定 thinking 键。
- 成本是**标准价估算**，不是供应商账单；报告须同时给出 `source` 与 `as_of`。
- 批次成本 = 各任务成本之和；任务均值 = 批次成本 / 任务数。失败或超时任务
  按已发生调用计入，不重摊到成功任务。

## 3. 缓存与批量折扣

- **响应缓存**：LLM 缓存（默认 `~/.cache/aitester/llm`）命中不产生 API 调用，
  记 `cache_hits` 与独立的 `cache_avoided_tokens`，不进入真实 token 三元组，
  因而不计费。
- **缓存命中价与错峰价**：DeepSeek 官方另有缓存命中价（0.04 CNY / 百万 token）与非
  峰时半价，MiMo 官方另有批量推理半价；价目表按峰时/标准全额价登记、不做扣减，
  登记成本是**上界**。
- **批量折扣**：仓库不应用批量折扣；同批运行多个任务不改变单价。
- **冷启动 vs 热缓存**：含 venv 创建与依赖安装的首次运行是冷启动；热缓存只
  复用 LLM 响应与 venv，不降低已发生调用的单价。

## 4. 未知值与上限

| 项 | 口径 |
|----|------|
| 未登记模型的单价 | 未测；记账通道返回 `unpriced`，不按 0 计 |
| 估算与供应商账单的差额 | 未测；只做 standard-price 估算 |
| 汇率 | 未登记事实源；跨币种不换算，`estimate_in_table_currency` 按登记币种原样返回 |
| 任务 token / 金额硬上限 | `COST_BUDGET_ENABLE`（默认关）；`COST_BUDGET_TOKENS` / `COST_BUDGET_USD` 为 0 表示不限。`COST_BUDGET_USD` 变量名是历史遗留，数值按价目表基准币种（当前 CNY）解释，超限消息按同币种符号打印 |
| 单次调用墙钟上限 | `LLM_CALL_BUDGET_SECONDS`（默认 600s，monotonic 计时）；每次请求前复查，超限快速失败、不再发请求；`LlmCallBudgetExceeded` 是 `BudgetExceededError` 子类，节点写 `budget_exceeded` → 终止原因 `BUDGET_EXCEEDED` |
| 批后处理墙钟告警 | `AITESTER_POSTPROCESS_WARN_S`（默认 600s）；只告警，不改判分 |

## 5. 降本候选：只登记，不默认启用

默认档已关思考（思维链原占输出约 90%，单调用实测 −92%/−94%，档位表见 `src/agents/llm_client.py`）。
其余候选都会改变模型行为或产物形状，按第 12 条单变量纪律须先在独立 A/B 格胜出：

| 候选 | 旋钮 | 效应 | 启用前必须测 |
| --- | --- | --- | --- |
| 补丁不整文件回显 | `EDIT_INTENT_ENABLE=true`（`src/tools/patch_intent.py`，默认 false） | Debugger 输出侧最大单项 | 补丁应用失败率 |
| 测试条数设上限 | `src/prompts/templates.py` Planner 段（现无上限） | 省 Planner 输出与 Generator 输入 | 检出率 |
| 去掉逐条 docstring 硬要求 | 同文件 Generator 段 | ~100–300 token/任务 | 与 docstring 锚定实验的耦合 |
| 全绿强制再生成 | `DETECTION_FIRST_ENABLE` / `MAX_REGENERATIONS` | 每任务少一次付费采样 | RT1 未解耦项：净效应≈0 才该关 |
| 定位器调用 | `FAULT_LOCALIZER_ENABLE`（默认开） | 每任务少一次调用 | 对检出的实际贡献 |

刻意不动的一处：坏 JSON / parametrize 不匹配的第二次付费调用本就有界（带纠正提示、只多一次），属韧性而非浪费。

本文读数与 `BASELINE.yaml` 冲突时，以 `BASELINE.yaml` 为登记权威；先复核
价目表 `as_of` 与批次 `usage`，再同步文档与登记册。
