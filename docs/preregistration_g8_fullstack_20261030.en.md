# G8 Full-Stack Re-run Pre-registration (2026-10-30, frozen before any data)

Last updated: 2026-10-30

> Authorization: user, 2026-10-30 — "LLM experiments may also run".
> This file is written to disk **before any G8 arm starts**; criteria are frozen before
> data collection; deviations must be logged in a deviation table.
> Data prerequisite closed: SWE-bench Pro data on disk (default 642 + hard 51) +
> instance_code enrichment (172 rows) ⇒ `check_swe_bench_pro_ready.py` ready 223/693
> (most of the python subset for ansible/openlibrary; js/go is outside this repo's
> Python test scope — structurally not ready, which is "disclosed", not "skipped").

## Design (all-four-switches-on vs historical default-off, same code state)

- Arm ON: `RUNTIME_PROBE_ENABLE / STRATEGY_BANK_ENABLE / EXPERT_POOL_ENABLE /
  CROSS_FILE_ENABLE` all true (exported explicitly by the runner);
- Arm OFF: all four false (same code state; OFF first, then ON within one session);
- Data: ready python-subset tasks; scale tiers — smoke 3 → main 30 (--task-limit);
  full 223 pending the main-batch budget reading (measure-then-extend discipline);
- Budget gates: task-level COST_BUDGET_USD=1.0 / batch-level AITESTER_BATCH_MAX_USD=6.0.

## Primary endpoint and criteria

- Primary: detection_rate (paired ON − OFF difference, bootstrap 95% CI);
- H (direction check): ON ≥ OFF − 3pp (the four switches must not hurt); if
  ON − OFF > +5pp ⇒ supports a later default-value review; within ±3pp ROPE ⇒ equivalent;
- Secondary: token cost / LLM call count / crash rate (the runtime_probe layer must not
  introduce harness_invalid).

## Honesty clause

- The 223/693 ready composition must be disclosed (python-only constraint);
- Judgment-infrastructure side: Pro has no Docker; the ansible path was measured by
  `swe_pro_judge_20261030` (73/82 judged); instances that are collection_failed on
  openlibrary/qutebrowser **do not enter the G8 main-batch denominator** (no
  observation is neither 0 nor a failure);
- Single seed 42, single model deepseek-flash without thinking; ON/OFF same code
  state (provenance git_sha recorded).
