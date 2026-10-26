# Performance and Cost Guide

Last updated: 2026-10-26 · 中文版: [performance_guide.md](performance_guide.md)

This guide defines the **calibers** for cost and latency, how to measure them, and how they relate
to `BASELINE.yaml`. The repository promises no fixed performance numbers: reproducible readings
live in `BASELINE.yaml`, and this document contains formulas and units only.

## 1. Cost Model

Per-task LLM cost:

```text
cost_task = Σ_calls ( input_tokens × price_in + output_tokens × price_out ) / 1_000_000
```

- Units: USD per million tokens; `price_in` / `price_out` come from the registered price table
  (currently only DeepSeek official deepseek-flash peak rates; see [COST_MODEL.en.md](COST_MODEL.en.md)).
- The multi-agent path uses Planner + Generator + one Debugger call per iteration (possibly
  several) + optional FaultLocalizer / ExpertPool; baseline paths usually use a single generation
  call.
- Recorded spend for baselines such as `plain_llm_df` is a **lower bound**
  (`cost_caliber="recorded_lower_bound"`): rows with an all-zero token triple but a non-empty
  generation enter the numerator as 0, so true spend can only be higher.
- Cache hits incur no API billing; cold-start and warm-cache runs are not directly comparable.
- Optional cost gate: `COST_BUDGET_ENABLE` (off by default) enforces a per-task token / USD cap.

## 2. Latency Model

```text
wall_task ≈ llm_calls × (latency_llm + retry_wait)
          + iterations × (pytest_wall + patch_apply_wall + snapshot_wall)
```

- `latency_llm`: wall-clock latency of one LLM call; endpoint- and model-dependent, **not measured**
  under a single universal caliber.
- `retry_wait`: `LLM_RETRY_WAIT` (default 30s) × recoverable failures (rate limits / timeouts /
  `finish_reason` truncation).
- `pytest_wall`: bounded by `EXECUTION_TIMEOUT` (default 30s); timeouts count as failures.
- `iterations`: actual repair rounds within `MAX_ITERATIONS` (default 3).
- Concurrency: CLI `--parallel` (default 1) and benchmark `BENCHMARK_PARALLELISM` (0 = serial)
  reduce total wall clock but do not change per-task cost.
- First-time venv sandbox creation and dependency installs are cold-start overhead; cache hits
  reduce it substantially (`AITESTER_VENV_CACHE_DIR`; clean with `clean-venv-cache`).

## 3. How to Measure

```bash
make perf-bench
make perf-check
```

- `make perf-bench` writes `experiments/results/performance_benchmark.json` (same caliber as
  `perf.yml`).
- `make perf-check` compares the current reading with the baseline; warnings are non-blocking by
  default, and `--strict` is available for local investigation.
- Per-task detail: `python3 main.py run <file> --json` returns timing fields; structured traces go
  to the directory given by `AITESTER_TRACE_DIR` (when unset nothing is written; the in-process
  snapshot buffer remains, and an uncreatable directory warns and degrades to memory-only).
- Cost readings: multiply the batch provenance `usage` / token triples by the price table; never
  estimate from log text.

Measurement discipline: same machine, same dependency lock, same endpoint; state explicitly
whether the cache was **cold or warm**, plus concurrency and sample size; a single run is not a
performance conclusion.

## 4. Relation to BASELINE Readings

- `BASELINE.yaml` is the single registration point for cost, latency, and test counts; this
  document and the README copy no concrete numbers.
- Benchmark cost is registered **per batch** and never pooled with the withdrawn n=261/arm pool;
  different generations (model, code tree, before/after the data purge) are not directly
  comparable.
- Unknown items are written as "not measured" and never extrapolated; an absent key in
  `BASELINE.yaml` means unmeasured, not zero.
- To refresh readings before a release: measure first, update `BASELINE.yaml` and
  [PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) §1, then run `make gates` to reconcile.
