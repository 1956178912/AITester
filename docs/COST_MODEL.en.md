# Cost Model

> Last updated: 2026-11-04 · 中文: [COST_MODEL.md](COST_MODEL.md)

This file defines cost **calculation calibers, units and limits** only. The single
sources of truth for prices and batch readings are
[`experiments/price_table.json`](../experiments/price_table.json) and
[`BASELINE.yaml`](../BASELINE.yaml); this file does not copy batch cost numbers.

## 1. Pricing Sources

| Source | Content | Caliber |
|--------|---------|---------|
| `experiments/price_table.json` | Per-model `input_per_mtok` / `output_per_mtok` (in the **registered currency**, per million tokens) | Must carry `currency` / `source` / `as_of`; `deepseek-flash` and `mimo-v2.6-pro` are both registered as `currency=CNY` |
| `COST_USD_PER_1K` | Fallback blended price when the table is unavailable (per thousand tokens) | Unset by default; applies only when greater than 0. The name is legacy; since 2026-11-04 its value is read in the **baseline currency (CNY)** |
| Batch provenance `usage` | The real token triple of each call | Counts only real API consumption on cache misses |

Current entries (peak/standard full prices, both conservative upper bounds):
deepseek-flash at input 2 / output 8 CNY per million tokens (`as_of=2026-11-04`,
official DeepSeek pricing page); mimo-v2.6-pro at input 3 / output 6 CNY per million
tokens (`as_of=2026-10-21`, official MiMo pay-as-you-go page). Off-peak half prices,
cache-hit prices and batch-inference half prices are **not** applied.

Unregistered models, undeterminable currency and null price fields mean **unpriced**:
they must not be counted as 0 in averages, nor extrapolated.

## 2. Per-Task Cost Formula

```text
cost_task = Σ_calls ( input_tokens × price_in + output_tokens × price_out ) / 1_000_000
```

- Units: tokens as counts; `price_in` / `price_out` in the **registered currency** of
  the price table (currently CNY) per million tokens; the amount is in that currency.
  Production accounting uses `pricing.estimate_in_table_currency()`, which returns
  `(amount, currency, source)` and performs **no foreign-exchange conversion** (this
  project has no FX source of truth).
- `pricing.estimate_usd()` keeps its historical "USD only" contract as the dollar
  column entry point; with the table in CNY it returns `unpriced` for those models.
  Callers and reports must **not** print a CNY amount with a dollar sign.
- Fallback: `cost_task = (input_tokens + output_tokens) / 1000 × COST_USD_PER_1K`.
- Calls are counted per real LLM call: the multi-agent path is Planner + Generator +
  one Debugger per iteration + optional FaultLocalizer / ExpertPool; baseline paths
  are usually a single generation call.
- `LLM_THINKING_MODE` defaults to **`disabled`** (caliber corrected by the user on
  2026-11-04). Chain-of-thought bills as output and is the dominant cost term: on one
  identical Generator call, thinking-on emitted 10,859 tokens (9,664 of them reasoning)
  for deepseek and 9,640 (8,407 reasoning) for mimo, versus 709 and 342 with thinking
  off — i.e. −92.4% / −94.1%. `reasoning_effort` is **not** a cross-model equivalent
  dial (measured: mimo's `max` tier came out shorter than its default), so batch
  comparisons fix the thinking key only.
- Cost is a **standard-price estimate**, not a provider invoice; reports must state
  both `source` and `as_of`.
- Batch cost = sum of task costs; task mean = batch cost / number of tasks. Failed or
  timed-out tasks keep their incurred calls and are not reallocated to successes.

## 3. Caching and Batch Discounts

- **Response cache**: a hit in the LLM cache (default `~/.cache/aitester/llm`) makes
  no API call and is recorded as `cache_hits` plus the separate
  `cache_avoided_tokens`; it does not enter the real token triple and is not billed.
- **Cache-hit and off-peak prices**: DeepSeek officially also has a cache-hit price
  (0.04 CNY per million tokens) and an off-peak half price, and MiMo officially has a
  batch-inference half price; the table registers the peak/standard full price without
  deducting any of them, so the registered cost is an **upper bound**.
- **Batch discount**: the repository applies none; running several tasks in one batch
  does not change unit prices.
- **Cold start vs warm cache**: the first run, including venv creation and dependency
  installation, is a cold start; a warm cache only reuses LLM responses and the venv
  and does not lower the unit price of calls already made.

## 4. Unknowns and Limits

| Item | Caliber |
|------|---------|
| Price of an unregistered model | Not measured; the accounting channel returns `unpriced`, never 0 |
| Gap between estimate and provider invoice | Not measured; the model is a standard-price estimate |
| Exchange rate | No registered source of truth; nothing is converted across currencies — `estimate_in_table_currency` returns the amount in the registered currency |
| Per-task token / amount hard caps | `COST_BUDGET_ENABLE` (off by default); `COST_BUDGET_TOKENS` / `COST_BUDGET_USD` of 0 means unlimited. The `COST_BUDGET_USD` name is legacy: its value is read in the price table's baseline currency (currently CNY), and the over-limit message prints the matching symbol |
| Per-call wall-clock cap | `LLM_CALL_BUDGET_SECONDS` (default 600 s, monotonic clock); re-checked before every request — exceeding it fails fast without further requests; `LlmCallBudgetExceeded` subclasses `BudgetExceededError`, so nodes set `budget_exceeded` → stop reason `BUDGET_EXCEEDED` |
| Post-process wall-clock warning | `AITESTER_POSTPROCESS_WARN_S` (default 600 s); warning only, scoring unchanged |

## 5. Cost-Reduction Candidates: Registered, Not Enabled

Thinking is off by default now (chain-of-thought was ~90% of output; measured −92%/−94% per
call, tier table in `src/agents/llm_client.py`). Each candidate below changes model behaviour or
artifact shape, so under the single-variable rule it must win its own A/B cell first. Bounded and
left alone: the second paid call on bad JSON / mismatched parametrize (one retry, corrective hint).

| Candidate | Knob | Effect | Measure first |
| --- | --- | --- | --- |
| No full-file patch echo | `EDIT_INTENT_ENABLE=true` (`src/tools/patch_intent.py`, default false) | Biggest Debugger output term | Patch-application failure rate |
| Cap test-case count | Planner section of `src/prompts/templates.py` (unbounded today) | Saves Planner output and Generator input | Detection rate |
| Drop per-test docstring mandate | Same file, Generator section | ~100-300 tokens/task | Coupling with docstring studies |
| Forced regeneration when all-green | `DETECTION_FIRST_ENABLE` / `MAX_REGENERATIONS` | One fewer paid sample per task | RT1 confound: off only if the net effect is ~0 |
| Localizer call | `FAULT_LOCALIZER_ENABLE` (on by default) | One fewer call per task | Its contribution to detection |

If a reading here conflicts with `BASELINE.yaml`, the latter is the registration
authority: recheck the price-table `as_of` and the batch `usage`, then update the
document and the register.
