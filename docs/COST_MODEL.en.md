# Cost and Wall-Time Model: Batch Post-Processing Wall Observability (Q-3)

> Last updated: 2026-10-18
>
> This document defines the **batch post-processing wall** observability contract.
> It fills a blind spot in the existing cost/wall-time bookkeeping: batch JSON has
> only total wall time and token/USD cost, without per-stage (mutation / M1 / MDO /
> other) per-task duration distributions. As a result it is impossible to answer
> "which stage, which class of tasks, or whether a long tail caused a 2400s run".

## 1. Background and Problem

The O-2 real-LLM validation batch (same cut/protocol) exposed run-to-run
post-processing wall-time variance: the control arm went **2102s -> >2400s (hit the
2400s post-processing watchdog) -> 2297s**, a >=14% swing. Existing batch fields
only expose total wall time and cannot distinguish:

- which post-processing stage (mutation / M1 / MDO) contributed the swing;
- whether all tasks got slower or only a few long-tail tasks did (stable p50 but
  exploding p95/max);
- whether tasks were truncated by the watchdog or genuinely became slower
  (timed-out task counts).

The module therefore records post-processing wall time as a stable, serializable,
warnable field archived with the batch JSON (alongside token/USD cost, forming a
two-dimensional resource-vs-time diagnosis).

## 2. Metrics and JSON Shape

Output of `experiments/postprocess_wall.py::build_postprocess_wall` (one entry per
stage, in input order):

```json
{
  "mdo": {
    "wall_s": 123.4,
    "n_tasks": 15,
    "mean_s": 8.23,
    "p50_s": 3.1,
    "p95_s": 40.0,
    "max_s": 60.0,
    "timed_out_tasks": 1
  }
}
```

- `wall_s`: sum of per-task durations for the stage (task-level; not the stage wall
  including queue/IO waits, and not total batch wall time);
- `n_tasks`: number of timed tasks (including timed-out tasks);
- `mean_s` / `p50_s` / `p95_s` / `max_s`: per-task duration distribution in seconds,
  rounded to 6 decimals;
- `timed_out_tasks`: tasks judged timed out by the caller (passed by the hook);
- a stage with no tasks emits an all-zero distribution (stable key set);
- warnings never enter JSON: `build_postprocess_wall` returns the `dict` subclass
  `PostprocessWallResult`; `json.dumps()` serializes only the stage mapping while
  threshold warnings live on `.warnings` for the caller's `logger.warning`.

## 3. Quantile Algorithm (pure stdlib, numpy `linear` / R-7 compatible)

For sorted samples `v[0..n-1]` and quantile `p` in `[0,1]`:

```
rank = p * (n - 1)
lo   = floor(rank)
hi   = min(lo + 1, n - 1)
value = v[lo] + (rank - lo) * (v[hi] - v[lo])
```

- `n == 1` returns the single value; `n == 0` returns 0.0 (no-task convention);
- matches the existing repository helper
  `experiments/bayesian_paired.py::_percentile_linear` (documented as numpy default
  "linear"); this module implements it independently to avoid cross-module imports;
- known exact examples: `[10,20,30,40]` -> p50=25, p95=38.5; `[10,20,30]` ->
  p50=20, p95=29; `[42]` -> 42.

## 4. Threshold and Warnings

- Threshold env: `AITESTER_POSTPROCESS_WARN_S` (default **600 seconds**; registered
  by Q-1 in the env budget gate). The reader lives in
  `src/utils/env_utils.py::postprocess_warn_seconds` (Q-3 decision option a:
  `check_env_budget.py` scans `src/**/*.py` + `config.py` but not `experiments/`;
  keeping the read in src prevents the registry entry from being pruned as
  unused); `experiments/postprocess_wall.py::postprocess_warn_s` delegates to it.
- `postprocess_warn_s()`: reads and validates the threshold; unset/empty/non-numeric
  /NaN/inf/<=0 falls back to the default 600 (a bad env must not crash observability
  or silently disable warnings).
- Trigger: `wall_s > warn_s` produces one warning message (equal threshold does not
  warn) containing stage name, measured wall, threshold and env name; the module
  never logs itself, leaving `logger.warning` to the caller.

## 5. Hook Integration (wired into run_benchmark, R-3, 2026-10-18)

**Status: wired in.** The per-baseline post-processing block in
`experiments/run_benchmark.py` (mutation scoring/detection + MDO calls) is wrapped
with `StageTimer` and archived through three small helpers
(`_run_postprocess_stage` / `_run_baseline_postprocess_with_wall` /
`_attach_postprocess_wall_to_summary`; the default call path is byte-equivalent,
observation only).

**Current granularity = `per_baseline`**: one wall sample per baseline per stage
(total wall of that baseline's post-processing calls in that stage), recorded in
the batch summary:

```json
{
  "postprocess_wall": {
    "mutation": {"wall_s": 1.1e-05, "n_tasks": 1, "mean_s": 1.1e-05,
                  "p50_s": 1.1e-05, "p95_s": 1.1e-05, "max_s": 1.1e-05,
                  "timed_out_tasks": 0},
    "mdo":      {"wall_s": 3e-06, "n_tasks": 1}
  },
  "postprocess_wall_granularity": "per_baseline"
}
```

- **field always present**: with `mutation_enabled=False` (default),
  `postprocess_wall={}` (empty mapping; only actually executed stages are included,
  no empty stage keys) while `postprocess_wall_granularity` stays `"per_baseline"`;
- threshold warnings are emitted one by one via the hook's `logger.warning`
  (threshold `AITESTER_POSTPROCESS_WARN_S`, default 600s; reader in §4); JSON does
  not contain warnings;
- exception path: the stage wall sample is still appended before the original
  exception is re-raised - exceptions are never swallowed and retry/timeout/scoring
  logic is unchanged;
- finer granularity (per task / per mutant) is a possible follow-up; the Q-3 module
  API is unchanged.

Integration shape (as in `run_benchmark.py` now):

```python
# post-processing collector (R-3): stage -> per-baseline wall samples
postprocess_stage_durations: dict[str, list[float]] = {}

# per-baseline post-processing (same call order/args/log as before, wall added)
_run_baseline_postprocess_with_wall(
    bl_results,
    tasks,
    postprocess_stage_durations,
    mutation_enabled=mutation_enabled,
    mutation_max_mutants=MUTATION_MAX_MUTANTS,
    seed=seed,
)

# batch summary: write the two keys and log threshold warnings
_attach_postprocess_wall_to_summary(summary, postprocess_stage_durations)
```

## 6. Trade-offs and Known Boundaries

- **Zero behavior change**: the module only times/aggregates; no post-processing or
  scoring field changes; overhead is two `time.perf_counter()` calls per task.
- **Task-level accounting**: the sum of `wall_s` is not total batch wall time
  (serialization/parallelism/IO waits are excluded); consume existing batch timing
  fields for the total.
- **Timeout semantics**: the caller should pass watchdog-truncated durations; the
  module treats computation and queue timeouts alike (both counted in
  `timed_out_tasks` and in the distribution).
- **Threading**: `StageTimer` is not thread-safe (post-processing hook collects
  serially on one thread); for parallel collection, use one timer per thread and
  merge duration lists.
- **Registered stage names**: `registered_stage_names()` returns
  `("mutation","m1","mdo","other")`; `build_postprocess_wall` raises `ValueError`
  for unregistered names (prevents silent metric renames from hook typos); new
  stages must be registered and documented here.

## 7. Verification and Tests

- Tests: `tests/test_postprocess_wall_metrics.py` (88 cases, no network, no LLM, no
  numpy): timers normal/exception/empty/nested/decorator, exact quantile values
  (even/odd/single/unsorted/duplicates), JSON shape and serialization, threshold and
  env fallback, all-timeout/no-task/inconsistent-data fail-fast, hook sample.
- Smoke artifact: `experiments/results/q_round_postprocess_wall_20261018/`
  (deterministic JSON sample built from synthetic durations + SHA256 manifest; shape
  demo only, not real batch numbers).
- Integration tests (R-3): `tests/test_run_benchmark_postprocess_hook.py`
  (23 cases): mutation-off zero behavior, identical call order/args, per-baseline
  granularity, threshold warnings, exception path still records a sample and
  re-raises, summary adds exactly two keys and stays JSON-serializable;
- Default zero-behavior evidence (R-3): running `run_benchmark()` with the same
  fake baseline on **HEAD (pre-integration)** and the current working tree
  (examples, 1 task; provenance/timing volatile fields normalized) yields
  **identical** legacy summary fields for both mutation-off and mutation-on
  modes; the only difference is the two added keys `postprocess_wall` /
  `postprocess_wall_granularity`;
- Acceptance: `python -m pytest -q tests/test_postprocess_wall_metrics.py
  tests/test_run_benchmark_postprocess_hook.py`; target files clean under
  `ruff check` / `mypy` (no new errors beyond the pre-existing run_benchmark ones).
