# 能力演示：任务级成本预算硬上限（COST_BUDGET_ENABLE）

最小可运行脚本，验证"消耗超限时自动停调用，避免免费额度跑飞"的观测口径。

## 运行

```bash
python examples/cost_budget_demo/run.py
```

无需真实 LLM key 即可离线运行——脚本仅演示预算累计器 / 超限判定
的观测口径，不发起 LLM 调用。

## 预期输出

- **默认口径（COST_BUDGET_ENABLE=false）**：`check_budget` 恒 `True`
  （开关关时预算守卫短路，历史行为不变）；
- **启用口径（COST_BUDGET_ENABLE=true + COST_BUDGET_TOKENS=1000）**：
  消耗 100 token 返回 `True`（预算内可继续），再消耗 9999 token
  返回 `False`（超限应停调），`is_budget_exceeded()` 变 `True`。

真实工作流中超限经 `BaseAgent._call_llm` 前置守卫抛
`BudgetExceededError`，planner / generator / debugger 节点降级兜底
（不再空转烧 token）。

## 涉及的环境变量开关

| 开关 | 默认 | 说明 |
|------|------|------|
| `COST_BUDGET_ENABLE` | false | 任务级预算硬上限总开关 |
| `COST_BUDGET_TOKENS` | 0（不限） | token 预算值（`COST_BUDGET_ENABLE=true` 时生效） |
| `COST_BUDGET_USD` | 0（不生效） | 费用预算值（与 token 预算取先到者） |
| `COST_USD_PER_1K` | 0 | 每 1K token 计价（费用预算换算用） |

## 真实工作流中的效果验证

启用后跑一次带修复循环的任务（多轮迭代），`--json` 输出的
`cost_budget` 字段（`get_process_budget_stats()`）可观测超限事件：

```bash
COST_BUDGET_ENABLE=true COST_BUDGET_TOKENS=50000 \
  python main.py run examples/calculator.py --func divide --json
```
