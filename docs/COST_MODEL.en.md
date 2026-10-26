# Cost Model

> Last updated: 2026-10-26 · 中文: [COST_MODEL.md](COST_MODEL.md)

This file defines cost **calculation calibers, units and limits** only. The single
sources of truth for prices and batch readings are
[`experiments/price_table.json`](../experiments/price_table.json) and
[`BASELINE.yaml`](../BASELINE.yaml); this file does not copy batch cost numbers.

## 1. Pricing Sources

| Source | Content | Caliber |
|--------|---------|---------|
| `experiments/price_table.json` | Per-model `input_per_mtok` / `output_per_mtok` (USD per million tokens) | Must carry `currency` / `source` / `as_of`; currently only DeepSeek official deepseek-flash is registered |
| `COST_USD_PER_1K` | Fallback blended price when the table is unavailable (USD per thousand tokens) | Unset by default; applies only when greater than 0 |
| Batch provenance `usage` | The real token triple of each call | Counts only real API consumption on cache misses |

Current entry: deepseek-flash at input 0.3 / output 1.2 USD per million tokens,
`currency=USD`, `source` is the official DeepSeek pricing page, `as_of=2026-10-06`
(peak-time full price).

Unregistered models, undeterminable currency and null price fields mean **unpriced**:
they must not be counted as 0 in averages, nor extrapolated.

## 2. Per-Task Cost Formula

```text
cost_task = Σ_calls ( input_tokens × price_in + output_tokens × price_out ) / 1_000_000
```

- Units: tokens as counts; `price_in` / `price_out` in USD per million tokens;
  the result is USD.
- Fallback: `cost_task = (input_tokens + output_tokens) / 1000 × COST_USD_PER_1K`.
- Calls are counted per real LLM call: the multi-agent path is Planner + Generator +
  one Debugger per iteration + optional FaultLocalizer / ExpertPool; baseline paths
  are usually a single generation call.
- Cost is a **standard-price estimate**, not a provider invoice; reports must state
  both `source` and `as_of`.
- Batch cost = sum of task costs; task mean = batch cost / number of tasks. Failed or
  timed-out tasks keep their incurred calls and are not reallocated to successes.

## 3. Caching and Batch Discounts

- **Response cache**: a hit in the LLM cache (default `~/.cache/aitester/llm`) makes
  no API call and is recorded as `cache_hits` plus the separate
  `cache_avoided_tokens`; it does not enter the real token triple and is not billed.
- **Cache-hit and off-peak prices**: DeepSeek officially also has a cache-hit price
  (0.006 USD per million tokens) and an off-peak half price; the table registers the
  peak-time full price without deducting either, so the registered cost is an **upper
  bound**.
- **Batch discount**: the repository applies none; running several tasks in one batch
  does not change unit prices.
- **Cold start vs warm cache**: the first run, including venv creation and dependency
  installation, is a cold start; a warm cache only reuses LLM responses and the venv
  and does not lower the unit price of calls already made.

## 4. Unknowns and Limits

| Item | Caliber |
|------|---------|
| Price of an unregistered model | Not measured; `estimate_usd` returns `unpriced`, never 0 |
| Gap between estimate and provider invoice | Not measured; the model is a standard-price estimate |
| Per-task token / USD hard caps | `COST_BUDGET_ENABLE` (off by default); `COST_BUDGET_TOKENS` / `COST_BUDGET_USD` of 0 means unlimited |
| Per-call wall-clock cap | `LLM_CALL_BUDGET_SECONDS` (default 600 s, monotonic clock); re-checked before every request — exceeding it fails fast without further requests; `LlmCallBudgetExceeded` subclasses `BudgetExceededError`, so nodes set `budget_exceeded` → stop reason `BUDGET_EXCEEDED` |
| Post-process wall-clock warning | `AITESTER_POSTPROCESS_WARN_S` (default 600 s); warning only, scoring unchanged |

If a reading here conflicts with `BASELINE.yaml`, the latter is the registration
authority: recheck the price-table `as_of` and the batch `usage`, then update the
document and the register.
