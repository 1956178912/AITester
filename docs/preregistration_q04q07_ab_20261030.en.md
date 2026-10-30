# Q03/Q04/Q07 A/B Pre-registration (2026-10-30, frozen before any data)

Last updated: 2026-10-30

> Authorization: user, 2026-10-30 — "LLM experiments may also run" + "start whatever can run first".
> This file is written to disk **before any arm starts**; criteria are frozen before data
> collection; deviations must be logged in a deviation table.
> Budget gates: task-level COST_BUDGET_USD=1.0 / batch-level AITESTER_BATCH_MAX_USD=6.0, always on.

## Common caliber

- Dataset synthetic 87 / seed 42 (E8 corpus; spec_compile measurable); Q07 additionally
  runs quixbugs 50 (deterministic_repair's target scenario);
- Arm config: `AITESTER_PROFILE=logic TEMPERATURE=0.0 LLM_THINKING_MODE=disabled
  MAX_ITERATIONS=3 EXECUTION_TIMEOUT=30 ENABLE_RAG=false AITESTER_LLM_CACHE=0`
  (E8 current-off caliber; thinking off is the cost-protection caliber);
- Each arm runs `--baselines aitester` single-arm with `--skip-stats`; verdict post hoc;
- Both switches are covered by the snapshot-key guard (ORACLE_CONTEXT_TIER scanned in
  logic_spec.py; DETERMINISTIC_REPAIR_FIRST_ENABLE matched by the `_ENABLE$` CI pattern).

## Q04: oracle generation-context ablation (ORACLE_CONTEXT_TIER)

- H (ASE-2025-direction recheck): minimal (four enhancement segments stripped) is within
  ±5pp (ROPE) of full on spec_compile_rate; equivalence ⇒ supports a lower default cost;
  significant negative ⇒ keep full as default.
- Primary endpoint: spec_compile_rate; secondary: token cost / detection_rate.
- Verdict: paired difference over 87 tasks + bootstrap 95% CI (10,000 resamples).

## Q07: deterministic-repair-first gray release (DETERMINISTIC_REPAIR_FIRST_ENABLE)

- H: on is not worse than off by more than −3pp (detection_rate); significant token cost
  reduction supports promotion. Zero-LLM deterministic takeover consumes no tokens —
  the on arm is expected to cost less.
- Primary endpoints: detection_rate / false_fix_rate; secondary: token cost / LLM call count.

## Q03: CF runtime gold-injection arm

- Switch and replay protocol follow the on-disk implementation in
  `src/agents/fault_localizer.py` (switch name and default verified by grep before launch;
  if the implementation gap cannot be closed within budget ⇒ disclose and abandon, no
  forced run).

## Honesty clause

- Single seed, single model (deepseek-flash), synthetic-corpus saturation risk (G03
  lesson: both arms may saturate on the synthetic corpus) — if both arms saturate,
  record "indistinguishable", not "zero effect";
- Criteria must not be changed before verdicts are read; dirty-tree status disclosed
  (results writing).

## Deviation log (registered after data collection, 2026-10-30)

| # | Preregistered text | Actual execution | Impact | Disposition |
|---|---|---|---|---|
| D1 | Common protocol: "Q07 additionally runs quixbugs 50" (together with "each arm, `--baselines aitester`") | Only `q07_on_quixbugs` (50 tasks) was produced; **no off control arm** | The paired on−off difference δ cannot be computed on the real corpus; only a single-arm descriptive reading exists (19/50 = 38%) | The primary verdict stays with the synthetic-87 comparison (δ = −3.45 pp), which remains negative; the quixbugs single-arm reading is descriptive only and must not be juxtaposed with, or converted into, the synthetic figure; adding the off arm requires a separate budget batch |
| D2 | Q04 primary endpoint spec_compile_rate | As preregistered (both arms produced) | None | — |
| D3 | Q03 follows the implemented switch | As preregistered (both arms produced) | None | — |
