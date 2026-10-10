# Pre-registration: E1–E4 Validation Experiments (Detection-First Protocol + Logic Chain + Double Gates)

Last updated: 2026-10-07 (**E2 iteration batch**: the user approved
spending the pre-registered "exactly one" gate/routing fix re-run —
three defect fixes as iteration preconditions: (1) fl_at_k 0/174 root
cause = implementation deviating from the R8 docstring design (system
patch diff only, while synthetic patches are whole-file replacement
text that never parses, plus `_extract_diff_line_numbers` calling a
two-arg function with one arg — the swallowed TypeError left the
fallback dead since birth); fixed to gold-diff-first (SequenceMatcher
buggy-side diff lines, same axis as fl Top-k line numbers) + a repaired
patch-diff fallback; (2) recursion_limit 8×MAX+8=32 still exhausted
16/174 task-runs → 16×MAX+8=56; (3) mutation 31/174 is **conservative
by design, not a defect** (generated tests not all-green on gold fixed
→ None instead of a false 0; i.e. 82% of generated tests fail on
correct code — itself a major scientific finding). All three are
harness/measurement fixes touching no primary-endpoint decision rules
or the statistical protocol; the re-run uses the same commands and
seeds. Previously the same day, E2 first-run adjudication: both
channels reduced 67.0%/85.7% past the stop line into this iteration
branch, H2c δ=−0.3673 significantly negative → conclusion escalated;
E1 executed 0.367≥0.3 keep. Previously the same day, batch AO: E6
matched-cap source amendment — caps now derived from E2 measured means,
the amendment precedes any E6 data. Previously the same day, batch AN:
AN2/AN5 presentation-only additions merged into the E3 section.
Batch AM, 2026-10-06: E6 execution-precondition statement + E6/E7 rows
in the execution log + E6 ready-commands block)

## Purpose and Scope of Effect

This document fixes the hypotheses, primary endpoints, pre-registered
thresholds, stopping rules, and statistical analysis plan **before** any
E1/E2 rerun is launched (Round-11 review N4; previously the pre-registration
content was scattered across ADR-0016 and `statistical_report_3seed_pooled.md`
with no standalone citable artifact).

Scope of effect: E1 (contract smoke) / E2 (double-gate replication) /
E3 (all-metrics, merged into E2) / E4 (first real-benchmark run) /
E6 (budget-matched four-arm) / E7 (repair-ceiling stratified sampling).
E6/E7 were added by the AL batch (2026-10-06) — the amendment precedes any
E6/E7 data (the E7 sampling script has not been run against real artifacts;
no E6 batches exist). E5 (model gradient) is **exploratory**, not bound by
this document, and must be labeled as such when reported.

## Honest Statement on Prior Results (against "post-hoc preregistration" criticism)

- The R-P0-2 life-or-death experiment was completed and archived on
  2026-10-06: plain_llm_df +43pp vs plain_llm, aitester +14pp vs plain_llm,
  **aitester −28pp vs plain_llm_df**, repair = 0 across all arms
  (**amendment note, batch XIII 2026-10-07, ADR-0021/0027**: the
  all-arms repair = 0 was a patch-field fence-residue measurement
  artifact — corrected-caliber replay gives R-P0-2 = 35.9% (52/145
  replayable rows). The detection-side conclusions and H2 rulings are
  unaffected (the detection channel was not contaminated); wherever
  repair figures are quoted, the corrected caliber prevails.)
  (`statistical_report_3seed_pooled.md`, 261 pairs, robust after cluster
  correction).
- The AB1 12-task validation batch was completed **before** the contract fix
  (spec_compile_rate all 0).
- Therefore E1/E2 are **replications**: thresholds are fixed at the time this
  file lands, but prior knowledge of experiment direction exists — no
  interpretation may claim blind prediction.
- Chronology audit: the commit that lands this file must precede the commits
  landing E1/E2 rerun artifacts (verifiable via git history).

## E1: Spec-Contract Fix Smoke (AC1 acceptance)

- **Hypothesis H1**: with `SPEC_EXPR_CONTRACT_SECTION` injected, the Planner
  produces spec clauses in the `{"desc": NL, "expr": DSL}` dual-channel form
  that pass the spec_ir_v2 compiler (before the fix, every real run measured
  spec_compile_rate = 0.0 — prompt Chinese NL vs `_EXPR_TOKEN_RE` ASCII
  whitelist contract break).
- **Design**: the same 12 tasks as ab1_validation (synthetic seed=42, first
  12 tasks), `AITESTER_PROFILE=logic`, `TEMPERATURE=0`, cache namespace
  seed42.
- **Primary endpoint**: spec_compile_rate (expr channel; row-level field
  plumbed in AB3).
- **Pre-registered decision**:
  - ≥ 0.3 → contract fix effective, the "logic-driven" claim is retained,
    proceed to E2;
  - < 0.2 → **abandon the logic-driven claim** per the ADR-0016
    pre-written threshold (follow-up work pivots to an LLM property-template
    route as a separate effort, out of this document's scope);
  - [0.2, 0.3) gray zone → allowed **exactly one** prompt-contract iteration
    and one rerun (artifacts of both runs archived); still < 0.3 → treat as
    abandoned.
- **Secondary endpoint**: spec_expr_coverage non-null rate = 100%
  (plumbing soundness).
- **Budget**: ≈ 0.1M tokens.

## E2: Double-Gate Replication (AC2 acceptance; E3 merged into the same run)

- **Hypotheses**:
  - H2a: the specificity gate drives the "over-red test" channel (buggy red
    ∧ fixed also red — not defect-specific, wastes the repair loop) to zero
    rows;
  - H2b: the red-regression gate drives the "erase-red" channel
    (red_then_green but the final test turns green on buggy — detection
    evidence destroyed by the repair loop) to zero rows;
  - H2c: after the gates, the aitester vs plain_llm_df detection paired
    difference converges (|δ| posterior 95% CI contains 0) or reverses.
- **Design**: synthetic n=87 × 3 arms {aitester, plain_llm, plain_llm_df} ×
  2 seeds {42, 44} × `AITESTER_PROFILE=logic` × gates on
  (`DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE`,
  auto-injected by the logic profile) × `ENABLE_MUTATION_SCORING=true`
  (E3 merged) × `TEMPERATURE=0` × `--max-pattern-repeat 2` ×
  `--pool-seeds`. AI1 (2026-10-06) completed the logic profile's
  `FL_SPECTRAL_ENABLE` injection — the E2 batch will produce fl_at_k data
  for the first time (previously empty in all logic-profile batches,
  0/87 measured).
- **Primary endpoints**:
  1. Over-red / erase-red channel row counts (decision rule = the measured
     method in the merged report's "known measurement gaps" section:
     red_not_repaired ∧ detection=0 as over-red candidate; red_then_green ∧
     detection=0 as erase-red candidate);
  2. aitester vs plain_llm_df detection paired difference (McNemar +
     Bayesian).
- **Pre-registered decision**:
  - Both channel row counts = 0 → H2a/H2b confirmed;
  - aitester vs df: δ posterior 95% CI contains 0 or δ > 0 → the net
    negative orchestration contribution is withdrawn (ADR-0016
    "negative/risk" clause lifted); still significantly negative → the
    "orchestration container is structurally inferior on detection"
    conclusion is upgraded (pre-written in ADR-0016, equally publishable).
- **Stopping rule**: if a channel row count does not reach zero but drops
  ≥ 50% relative to baseline (88 over-red / 28 erase-red rows) → allowed
  **exactly one** gate-parameter/routing fix and one rerun; drop < 50% →
  accept the result, no further iteration (prevents gate-parameter search
  overfitting the benchmark).
- **Secondary endpoints**: whether repair breaks zero; E3 all-metrics
  row-level non-null rates (next section).
- **Budget**: ≈ 3–6M tokens (AD-batch `LLM_THINKING_MODE=disabled` basis).

## E3: All Metrics On (merged into the E2 run)

- Requirement: mutation_detection_rate / fl_at_k / patch_precision /
  spec_compile_rate / spec_expr_coverage non-null on all measurable rows
  (None allowed only under the "no gold material" rule, with share and root
  cause disclosed in the report — no "schema present but runtime flag off"
  cases allowed).
- AN2/AN5 (2026-10-07) presentation-only additions: the E2 statistical
  report gains a "test-suite reliability" section (per-arm aggregation of
  mutation_detection_rate, aligned with the SWE-Mutation 2026 framing) and
  a $/detection derived column in the cost section ($/task ÷ detection
  rate) — both are **presentation-only additions** (aggregation/quotient of
  already-registered measurements, not new measurements); primary
  endpoints, preregistered thresholds and stopping rules are unchanged.
  The additions predate any E2 data (the commit introducing this change
  lands before the E2 batch artifacts are committed — auditable in git
  history), guarding against a "post-hoc presentation" objection.

## E4: First Real-Benchmark Run (QuixBugs L1)

- **Preconditions**: ① QuixBugs upstream license verified and recorded in
  DATA_CARD (existing registered item); ② data placed under `data/`
  (gitignored, not committed).
- **Design**: Python subset 29 tasks × 3 arms {aitester, plain_llm,
  plain_llm_df} × 1 seed (42) × logic profile × gates on.
- **Primary endpoint / acceptance line** (BASELINE pre-registered rule):
  any arm with detection > 0 ∧ resolved > 0.
- **Decision**: met → L2 of the real-benchmark ladder (BugsInPy) is
  chartered; both arms all 0 → recorded as negative and a **mandatory root
  cause analysis** (error_category × stop_reason aggregation) is required
  before any dataset switch — silently swapping benchmarks is forbidden.
- **Budget**: ≈ 0.3M tokens.

### E4 contamination control (R4, 2026-10-09 pre-registration addition, before any formal E4 data)

> Background: SWE-bench-family benchmarks carry systematic training-data
> contamination that has been documented by 2024–2025 literature. This
> addition upgrades "contamination control" from an implicit assumption to a
> pre-registered **mandatory disclosure clause**, so that E4's "real-benchmark"
> conclusion cannot be overturned by contamination challenges. The addition
> predates any formal E4 three-arm data (at the R4 stage only the R4
> by-product single-arm existed, which is not E4); verifiable via git history.

- **Contamination risk statement (cited evidence; E4 report must mark
  DOI/URL in its references)**:
  ① Aleithan et al. 2024 — 94% of original SWE-bench instances predate
  mainstream LLM training cutoffs, so high scores may partly reflect
  memorization rather than generalization; ② Liang et al. 2025 — SOTA LLMs
  guess the buggy file path from the issue description alone at 76% (SWE-bench
  Verified); ③ Wang et al. 2025 (PatchDiff) — differential testing shows up
  to 6.4pp of apparent gain is "illusory" (unsound evaluation); ④ Yu et al.
  2025 (UTBoost) — test augmentation and stricter parsing revised 24% of
  leaderboard entries. QuixBugs is a classic pedagogical benchmark (Derrick
  Lin et al.) within mainstream LLM training corpora, so contamination risk
  **cannot be assumed zero**.
- **Mandatory disclosure (E4 report must contain a dedicated subsection)**:
  1. **Model training cutoff vs instance time**: record the public training
     cutoff of E4 models (deepseek-flash etc.) and cross-check against
     QuixBugs instance introduction time, reporting the share of
     "potentially overlapping" instances;
  2. **Target-mismatch declaration**: continue the SWE-bench Lite 0/20 honest
     disclosure — if E4 is negative, distinguish "method ineffective" vs
     "target mismatch" (function-level single-file repair vs repository-level
     task), without silently attributing to either direction;
  3. **Differential-testing re-check (PatchDiff-style)**: for E4 rows with
     positive detection/resolved, sample a differential re-run with
     localization clues removed — if positives drop significantly after clue
     removal, report the contamination component interval;
  4. **Reproducibility**: contamination disclosure must not rely on manual
     judgment — encode "model cutoff + instance time + differential re-run"
     as objective fields in result rows or the report appendix.
- **Decision hardening**: the original "any arm detection>0 ∧ resolved>0"
  is unchanged; add the hard constraint "a missing contamination-disclosure
  subsection renders the E4 report incomplete and unusable for external
  citation".
- **Budget impact**: contamination control is offline field recording +
  sampled differential re-run, with no additional full-scale LLM cost
  (differential re-run only on positive-result samples, ≈ 0.01M tokens),
  leaving the E4 budget unchanged.

## E6: Budget-Matched Four Arms (Orchestration vs Compute Attribution; pre-registered by AL, run pending budget)

- **Motivation (R4/AL7)**: in R-P0-2, aitester used 26,115 tokens/task vs
  plain_llm_df 4,223 (8.1×); the −28pp admits two explanations —
  orchestration structure vs budget confounding (long-loop context
  bloat/attrition). The 2026 cost consensus ($/resolved spanning $0.46–$74
  across six frontier models at score parity) requires attribution
  isolation before structural conclusions.
- **Design**: 2×2 four arms = {aitester, plain_llm_df} × {standard,
  budget-matched}; synthetic n=87 × 2 seeds {42, 44} × logic profile ×
  both gates on × `TEMPERATURE=0` × `--max-pattern-repeat 2` ×
  `--pool-seeds`.
  - budget-matched definition (**amended by batch AO, 2026-10-07, before
    any E6 data**): matched caps must be derived from the **per-task
    total-token empirical means of the E2 same-seed standard batches**
    (row-level `token_usage.total_tokens` aggregated per arm) —
    df(matched) = standard df arm with the cap raised to the E2 aitester
    standard-arm mean (more regeneration rounds until the cap);
    aitester(matched) = standard aitester arm with the cap pressed down
    to the E2 df standard-arm mean. The R-P0-2 figures (26,115/4,223)
    are a **gate-less caliber**: magnitude references only, never to be
    used as caps directly — the gates change the aitester token
    consumption curve (gate routing removes futile repair loops); if the
    gated mean falls below the old df mean, a hardcoded cap would never
    bind, degenerating aitester(matched) into an unconstrained arm and
    voiding the equal-budget contrast.
  - **Amendment effect statement**: this amendment (batch AO,
    2026-10-07) is a design amendment — primary endpoints, decision
    rules and the stopping rule are unchanged; only the numeric source
    of the matched caps moves from the R-P0-2 constants to E2 measured
    means. It precedes any E6 batch data (zero E6 batches exist),
    auditable via git history.
  - **Run precondition (met by batch AM, 2026-10-06)**:
    `run_main_batch/run_benchmark` now implement `--per-task-token-caps`
    (arm=cap mapping, injected via `set_task_token_cap` into the task
    budget instance; cap hit exits via the existing budget stop path —
    stop_reason=budget_exceeded, row field token_budget_capped=true,
    provenance.per_task_token_caps recorded).
    Note: the original pre-registration text said stop_reason records
    "budget_cap"; the implementation reuses the existing enum value
    `budget_exceeded` (same semantics — read that field for the decision).
    This is the only erratum; the decision rules are unchanged.
- **Primary endpoint**: detection paired difference δ (McNemar + Bayesian +
  BH-FDR) for the two equal-budget comparisons — df(matched) vs
  aitester(standard), aitester(matched) vs df(standard).
- **Pre-registered decision rules** (significant = |δ| 95% CI excludes 0
  and outside ROPE ±5pp):
  - both pairs δ≈0 → budget confounding ruled out; −28pp attributes to
    orchestration structure (ADR-0016 conclusion hardened);
  - df(matched) significantly up OR aitester(matched) significantly down →
    budget confounding significant; −28pp must be downgraded to "not
    verified under equal budget";
  - mixed → report the dominant channel as-is, no second iteration.
- **Stopping rule**: one-shot experiment, no iteration clause.
- **Budget**: ≈ 4M tokens (thinking-off caliber).

## E7: Repair-Ceiling Stratified Sampling for Manual Review (pre-registered by AL)

- **Motivation (R9/AL10)**: in the repair=0 funnel (patch produced 94.2% →
  plausible 46.8% → correct 0, `repair_ceiling_report.md`), correct=0 comes
  from gold equality adjudication — the possibility that "overly strict
  gold adjudication underestimates repair" must be excluded before the
  ceiling conclusion is finalized.
- **Design**: sampling frame = patch_plausible=1 rows (72/261) in
  repair_ceiling_report §1; stratification key = patch_evidence_level
  {none, sbfl, keyword}; per stratum sample ceil(stratum × 10%)
  (deterministic seed=42, script `experiments/repair_sample_selection.py`,
  emitting the candidate-row manifest for manual comparison).
- **Manual-review rubric**: compare each patch against the gold diff and
  label it ∈ {equivalent (semantically equal, should count as repair),
  plausible_overfit, wrong_location, test_only, incomplete}.
- **Pre-registered decision**: equivalent share > 0 → the repair metric is
  underestimated; BASELINE/pooled reports must be corrected with the
  revised repair upper bound; = 0 → "the repair ceiling is bounded by
  plausibility and gold correctness" is finalized.
  **Amendment note (batch XIII, 2026-10-07, predating any human-review
  data)**: E7's motivation has been answered mechanistically by
  ADR-0021 — the gold adjudication was not "overly strict"; it never
  executed the real patch (patch-field fence residue → 100% NameError);
  corrected-caliber repair = 35.9% (52/145, `make corrected-metrics`).
  The "= 0 → true zero" branch is void. Manual review retains
  independent value (auditing whether the 61% wrong_patch rows under
  the corrected caliber hide semantic equivalents), downgraded from
  "caliber underestimation test" to "residual semantic-equivalence
  sampling audit".
- **Cost**: ~1 person-day, zero LLM cost (offline sampling + manual diff).
- **Candidate list (generated in batch AO, 2026-10-07)**:
  `experiments/results/main_batch/e7_repair_sample_candidates.md` — the
  sampling script has been run against the real artifacts (seed=42,
  deterministic, reproducible); the manual review proceeds row by row
  from that list, and the execution log table is filled in per the
  decision rules above once the review completes.
  **Side-by-side review worksheet (generated in batch AP, 2026-10-07)**:
  `experiments/results/main_batch/e7_review_worksheet.md` — each candidate
  section embeds four materials (generated patch / gold fixed / gold
  official tests / final generated test) plus judgment checkboxes; under
  the whole-file-replacement caliber the patch body IS the post-patch
  full file, so a line-by-line comparison against gold fixed suffices for
  classification. The review verdict remains a human judgment — the
  worksheet prepares materials, it does not adjudicate.

## Statistical Analysis Plan (common to all experiments)

- Test family: McNemar (continuity correction) + BH-FDR (α=0.05) +
  Bayesian Dirichlet paired analysis (ROPE ±5pp, MC seed=42) + template
  cluster DEFF sensitivity + template-level sign test (AC4 rule,
  `--cluster-by-template`).
- Multi-seed pooling always via `--pool-seeds` (AB4 rule); the analysis
  basis is the current version of statistical_analysis.py, with analysis
  code and artifacts archived in the same batch.
- Primary endpoints presented first; secondary endpoints labeled
  "exploratory"; **no switching primary endpoints or adding/removing tests
  post hoc**.
- Power basis: `scripts/tools/power_analysis.py` (baseline detection 2%, a 10pp
  difference needs n≈87; if the E2 double gates act as near-deterministic
  channel elimination, the replication focuses on channel zeroing with
  effect-size estimation as secondary).

## Artifacts and Reproducibility

- Each experiment produces: batch JSON + full traces + statistical report +
  SHA256SUMS, all archived via the git whitelist
  (experiments/results/main_batch/ rules);
- Before each run, verify provenance `git_dirty=False`; otherwise abort and
  record the reason. **never** pass `--allow-dirty` in re-runs (AK erratum
  note, reworded into a forbidding context by AL1: R-P0-2 itself was run
  under that flag — the provenance flaw is registered in the pooled
  report's "AK erratum" section; tracking of report-referenced artifacts is
  enforced by `scripts/gates/check_artifacts_tracked.py` in CI);
- Recompute commands written into each report header (existing R2 protocol);
- Cost basis: $/task driven by `experiments/price_table.json` (AE2); fill in
  the corresponding model prices (with source and effective date) before
  generating E1/E2/E4 reports. AK note (2026-10-06): deepseek-flash and
  qwen-long are registered from official pages ($/task computable; the main
  model deepseek-flash is unblocked); agnes-3.0-flash stays null absent a
  public official price — batches using it must register first.

## Bias Control and Honesty Clauses

- passed is a self-referential metric, diagnostic only, never a basis for
  conclusions;
- rows without gold material stay out of denominators (M1 rule) with shares
  disclosed in the report;
- task deaths / degradation exits (error_category) are disclosed, never
  silently dropped;
- quota interruption / budget overrun → the experiment is recorded as
  "aborted"; completed portions may be reported but no top-up reruns;
- any deviation from this pre-registration (including gray-zone iteration,
  stopping-rule triggers) must be recorded in the execution log and appended
  to the global decision log.

## Execution Log (appended after each run; decision rules must not be rewritten)

| Experiment | Status | Batch artifacts | Primary endpoint result | Decision | Date |
|------------|--------|-----------------|-------------------------|----------|------|
| E1 | executed (12/12 valid; 2 tasks hit recursion_limit with no terminal state, fixed in an E1 follow-up, see the note at the top) | `experiments/results/ab1_validation_e1/` (AITESTER_PROFILE=logic, seed 42, temp 0.0, git_dirty=False, deepseek-flash, 87,495 tok) | spec_compile_rate mean=0.367 (n=10/12 measurable); accompanying observations: detection=20.0% (both cases confirmed by the specific_red gate), repair=0.0%, false_fix=80.0% | **keep** (≥0.3) | 2026-10-07 |
| E2+E3 | executed (first run + iteration re-run, each 2 seeds 42/44 × 3 arms; the iteration reproduced the first-run primary metrics digit-for-digit — temp-0.0 cache-hit deterministic replay; this was the exactly-once iteration, no further iterations) | iteration `main_batch/benchmark_synthetic_20261007_181638.json` + `..._185941.json` + `statistical_report_e2_iter.md`; first run `..._161053.json` + `..._170147.json` + `statistical_report_e2.md` | Final adjudication: over-red 88→31 (−64.8%), erase-red 28→2 (−92.9%); aitester vs df δ=−0.3673 [−0.4552,−0.2785] (bayes_neg, digit-identical to the first run); pooled detection: aitester 12.7% / plain_llm 1.7% / df 52.3%; repair 0.0% across all arms; spec_compile_rate=0.212 (grey zone); **FL@1 measurable for the first time: 19/53=35.8%** (after the gold-diff fix); mutation measurable 31/174, mean 0.767 (conservative semantics); recursion exhaustion 16/174 (under the 56 cap the df-arm runaway loop persists, disclosed as-is) | H2a/H2b **not upheld** (not zeroed; both reductions ≥50% but the exactly-once iteration is spent → accepted per the stop rule: gates cut over-red by ~2/3 and erase-red by ~93%); H2c **the "orchestration container is structurally inferior on detection" conclusion is finalized** (pre-written in ADR-0016, publishable); secondary endpoint repair stays at zero; E3 non-null rates: fl 30% measurable (post-fix) / mutation 18% (by design) / spec 91% | 2026-10-07 |
| R4 A/B + QuixBugs single-arm (**out-of-preregistration debug exemption**, not E4) | executed (a by-product of R4 channel-prototype validation; the two synthetic arms ran on a **dirty tree**, the two QuixBugs arms on a clean tree) | `experiments/results/r4_batches/{r4_ab_arm_a,r4_ab_arm_b,r4_synth_arm_b2,r4_qb_arm_a,r4_qb_arm_b,loc_test_quix}` (committed in batch R2, 2026-10-08, with SHA256SUMS/README) | synthetic repair 8/50; QuixBugs A/B repair M1 measurable caliber **37/41, 36/41** (all-task 37/50, 36/50) | R4 localization constraint is **negative** (no A/B gain); the QuixBugs single-arm only validates the pipeline and does **not constitute the formal E4 execution** | 2026-10-08 |
| E4 | **executed (2026-10-09; both arms, fully settled: `aitester` + `plain_llm_df`)** | `experiments/results/e6_a1_batches/e4_quixbugs_aitester/` (`benchmark_quixbugs_20261009_215514.json`) + `e4_quixbugs_plain_llm_df/` (`benchmark_quixbugs_20261009_223101.json`), each with 50 traces and logs | **41-defect-program caliber: BOTH arms have detection 0/41 = 0.0%**; aitester repair 35/40 = 87.5%, false_fix 2.5%, token/task 17,156, red_seen 40/41; df repair 0 (no repair channel), token/task 2,370, red_seen 41/41. **Paired McNemar (detection): discordant pairs = 0, p = 1.0000** (41/41 identical); Bayesian delta=+0.0000, 95% CI [-0.0659, +0.0672], P(|delta|<=ROPE)=0.8943 | **Primary endpoint FAILED** (neither arm has detection > 0). **Mechanism settled**: red tests are widespread (red_seen 40-41/41) but **non-specific** - stage 2 of the F2P three-stage verdict (green on fixed) does not hold, so "0% detection" precisely means **"red without specificity"** (wrong/over-strict assertions, or the 30s execution timeout), sharing a root with the synthetic over-red channel. The **"repair relies on non-F2P signals" hypothesis is refuted**: repair is adjudicated independently by the gold tests and does not intersect the generated-test channel. **On the real benchmark, orchestration vs plain prompting shows no detection difference** (p=1.0) while orchestration costs 7.2x the tokens. Limitation: each arm ran at its own standard budget, not an equal-budget comparison | 2026-10-09 |
| E6 | **executed (2026-10-09, two phases: cold-cache standard + matched)** | `experiments/results/e6_a1_batches/e6_phase1_standard_coldcache/` (three standard arms) + `e6_phase2_matched_coldcache/` (two matched arms), with SHA256SUMS/README | Four-arm detection: aitester standard 6.9% (6/87, 8,857 tok) · aitester matched 2.3% (2/87, 87/87 capped) · df standard 31.0% (27/87, 2,586 tok) · df matched 26.4% (23/87, 2,602 tok) | **Budget confounding refuted**: df(matched) vs aitester(standard) chi2=13.474 p=0.0002 (BH q=0.0002); raising df's budget leaves its consumption unchanged (2,586 to 2,602) with no significant detection change (p=0.2888) → **-28pp attributed to orchestration structure; ADR-0016 reinforced**. Limitation: aitester(matched)'s cap is below its per-task need (84/87 rows capped early), so that arm measures orchestration under budget starvation, not a strict equal-energy comparison | 2026-10-09 |
| E7 | pending manual review (candidate list generated, batch AO) | — | — | — | — |
| **A1 ablation (outside preregistration, 2026-10-09 review report §5 path A1)** | **running (2026-10-09, see the A1 design declaration below)** | to be deposited | — | **declared before data** | — |

### E6 execution addendum (2026-10-09, registered **before any data**)

**Motivation**: the E6 preregistration (AO amendment) requires budget-matched caps to
be taken from the "**measured per-task total token mean of the same-seed E2 standard
batch**". Pre-execution inspection shows this premise **does not hold**: across the four
E2 batches (`..._161053/_170147/_181638/_185941`) **only the aitester arm carries
`token_usage.total_tokens`**; the `plain_llm_df` and `plain_llm` arms have **no token
rows** (df had 79/87 rows in R-P0-2 but **0 rows** in the E2 batches). Hence the
**df-arm matched cap is not derivable** from existing artifacts, and E6 cannot start
under its original design.

**Addendum decision (primary endpoint / decision rules / stopping rules unchanged)**:
first run an **E6 control** batch with the E2 protocol parameters (seed 42, n=87, logic
profile, both gates, `TEMPERATURE=0`, `--max-pattern-repeat 2`,
**`LLM_THINKING_MODE=disabled`** — consistent with E2 and with the E6 preregistered
budget basis, see line 132 of this file), in order to:

1. supply the **df-arm token measurement** (the missing item) so the matched cap
   becomes derivable;
2. supply the **same-batch aitester control** required by the A1 ablation arm (same code
   state, same seed, same protocol);
3. serve as the **current-run reproduction baseline** for the E6 standard arm (the code
   state now includes the landed R2–R5 changes and differs from E2's git state, so E2
   rows cannot be reused as the control).

**Known deviation (registered honestly)**: in the control batch the df arm's
`token_usage` is still **partially 0** (small-sample smoke test: 3/5 rows populated;
zeros come from two paths — "no test selected after truncation" and "detection without
regeneration") — therefore the **df matched cap can only be derived from the mean of
populated rows, with a denominator below 87**, and citations must state the denominator.
This does not affect the E6 primary endpoint (the detection paired difference does not
depend on cap precision), but it does affect whether the matched arm **actually binds**
its cap, and must be disclosed explicitly in the results report.

### A1 ablation design declaration (2026-10-09, **outside preregistration; declared before data**)

**Honest preamble**: A1 is **not** part of the original E1–E7 preregistration; it is an
**exploratory test** of a hypothesis raised by the 2026-10-09 review report (§5 path A1,
§8.6 red-team RT3). This section is registered before execution to preserve auditable
"declare-then-measure" ordering; it **must not** be presented as E1–E7-grade evidence.

**Hypothesis (H-A1)**: the dominant mechanism behind aitester's significant deficit
versus `plain_llm_df` in R-P0-2 (δ=−0.279) is **not** the "structural inferiority of
orchestration" claimed by ADR-0016, but **oracle-from-implementation**: the Planner
reads the **buggy code** and emits `test_cases[].expected_output` (`templates.py:25`)
→ the Generator injects the whole plan JSON into the prompt (`generator.py:353`)
→ the expected value equals the implementation's current (wrong) behavior → assertions
are all-green on the buggy target (the never-red channel, 86/240).

**Intervention (single variable)**: `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true` — strip only
`test_cases[].expected_output` from the Generator prompt, **preserving** `case_name` /
`input_args` / `category` / `description` / `logic_coverage` and the entire
`logic_analysis`. Default false (zero change to the historical caliber, ADR-0003).

**Design**: 2 arms = {aitester(standard), aitester(strip)} × seed 42 × n=87 ×
E2 protocol parameters (logic profile / both gates / temp 0.0 / thinking disabled /
`--max-pattern-repeat 2`); the control is the aitester arm of the E6 control batch above
(same code state).

**Primary endpoint**: the detection paired difference δ (McNemar + BH-FDR; plus the
**template-cluster DEFF correction and sign test** used in the pooled report — at the
nominal n=87 the template clusters number k≈31, so n_eff is far below 87).

**Decision rules (declared in advance)**:
- if the strip arm's detection is significantly **higher** than aitester(standard)
  (CI excludes 0 and outside the ±5pp ROPE) → **H-A1 holds**: the dominant mechanism of
  −28pp is oracle-from-implementation, and ADR-0016's "structural inferiority of
  orchestration" must be **downgraded to "not decoupled from an implementation defect"**;
- if δ≈0 → H-A1 does not hold and the never-red channel has another cause (pivot to
  paths A2/A3);
- mixed/borderline → report honestly, no second iteration.

**Stopping rule**: one-shot experiment, no iteration clause. **Budget**: ≈1.2M tokens
(thinking-disabled basis).

### A1 execution result (2026-10-09, **appended after data; decision rules unchanged**)

| Item | Result |
|---|---|
| detection (standard) | **8/87 = 9.2%** |
| detection (strip) | **8/87 = 9.2%** |
| Paired McNemar | discordant **2**, χ²=0.500, p=0.4795, **BH-FDR q=1.0000** |
| Bayesian paired | δ=**+0.0000**, 95% CI **[−0.0451, +0.0445]**, P(\|δ\|≤ROPE)=**0.9691** |
| Template-cluster correction | k=29, ICC=0.671, DEFF=4.356, n_eff=39.9/174; sign test 1:1, p=1.0000 |
| **Verdict** | **H-A1 does not hold.** The 95% CI lies **entirely inside the ±5pp ROPE** → under the equivalence reading this is **practically equivalent to zero** (stronger than "not significant"); the path is retracted |

**Scope limitation (must be stated alongside)**: the intervention was **structurally
inert on 34/87 (39%) tasks** — when the Planner output is structurally incomplete it
falls back to the default plan with `test_cases = []`, so there is **no
`expected_output` to strip** (`nodes.py:242-248` → `_get_default_test_plan`). The
effective scope is therefore the remaining **61%** of tasks, where the effect was still
zero. **By-product**: this 39% empty-plan rate is a **new candidate root cause** for the
never-red channel (higher priority than the original A1/A2/A3).

**Artifacts**: `experiments/results/e6_a1_batches/a1_strip_seed42/` (with
SHA256SUMS/README).

### E6 phase 1 execution addendum (2026-10-09, registered **before data**)

**Motivation (continuing the "E6 execution addendum" above)**: the control batch
confirmed that the `plain_llm` and `plain_llm_df` arms report tokens in **0/87 rows**
and aitester in only 37/87. Root cause located: on a cache hit,
`src/agents/base_agent.py:389/437` returns early, **bypassing `record_usage`** — and
that same file states at `:339` that "a cache hit … consumes no further tokens — the
historical caliber is preserved. **Formal experiments must set `AITESTER_LLM_CACHE=0`
explicitly**". In other words, **token accounting from a warm-cache batch is inherently
incomplete**; this is an existing design caliber, not a new defect. But the E6 matched
cap requires **complete** accounting.

**Addendum decision (primary endpoint / decision rules / stopping rules unchanged)**:
run E6 in two phases —

- **Phase 1 (this run)**: the three standard arms × **`AITESTER_LLM_CACHE=0` (cold
  cache)** × seed 42 × n=87 × otherwise the same protocol as the control batch (logic
  profile / both gates / temp 0.0 / thinking disabled / `--max-pattern-repeat 2`).
  Purpose: obtain **complete** per-task token accounting (all three arms), from which
  the matched caps are derived per the AO amendment;
- **Phase 2 (pending phase-1 results)**: the two matched arms — `df(matched)` (cap
  raised to the measured aitester mean) and `aitester(matched)` (cap lowered to the
  measured df mean) — injected via `--per-task-token-caps`.

**Known cost (registered honestly)**: the cold cache means **forfeiting cache reuse**,
so phase 1 consumes more tokens/cost than a warm-cache batch, and phase 1's aitester arm
is **not directly pairable** with the control batch (different cache state) — phase 1
serves only to **derive the caps**; the E6 primary-endpoint comparison runs between
phase 2 and phase 1's standard arms.

**Stopping rule**: phase 2 is one-shot, no iteration clause.

**v2 corrected-caliber pointer (2026-10-08 R2, R27/R13)**: the E2+E3 row's
"repair 0.0% across all arms" is the raw value doubly contaminated by the
ADR-0021 fencing artifact and the **third artifact (cross-file tasks not
materialized, R27)**. Replayed under the corrected caliber after the R27 fix
(`experiments/results/main_batch/corrected_report_v2.md`): R-P0-2 corrected
repair **39.31% (57/145)** (v1 35.86%, 52/145); E1/E2 **54.72% (58/106)**
(v1 48.11%, 51/106). All external citations must follow v2 and the caliber
matrix in `docs/design/repair_caliber_matrix.md` (citing must state the
numerator/denominator/oracle/arm).

## Ready-to-Run Commands (AH2 preset: execute directly once the budget is approved and the tree is clean)

E1 contract smoke (12 tasks, ≈0.1M tokens; `run_main_batch` refuses dirty
trees by default — a clean tree is enforced by the tool, **do not** pass
`--allow-dirty`, which would violate this pre-registration):

```bash
AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
  --task-count 12 --seed 42 --baselines aitester \
  --output-dir ab1_validation_e1 --skip-stats
```

Result verification (spec_compile_rate mean against the pre-registered
thresholds: ≥0.3 retain / <0.2 abandon):

```bash
.venv/bin/python -c "import json,glob; f=sorted(glob.glob('experiments/results/ab1_validation_e1/benchmark_*.json'))[-1]; rows=json.load(open(f))['results']['aitester']['details']; vals=[r['spec_compile_rate'] for r in rows if r.get('spec_compile_rate') is not None]; print(f, f'spec_compile_rate mean={sum(vals)/len(vals):.3f} (n={len(vals)}/{len(rows)})')"
```

E4 precondition status (updated in AH1): the QuixBugs upstream license is
verified as MIT (GitHub API, 2026-10-06) — precondition ① is lifted; record
the fetched commit together with the E4 artifacts. BugsInPy (L2) has no
SPDX license — see the decision gate in DATA_CARD §4; out of E4's scope.

### A1 false-negative correction and controlled arms for two specificity fixes (2026-10-10)

**A1 false negative**: the original A1 batch `a1_strip_seed42` had
`env_snapshot.PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` = **`None`** (unset), zero
"A1 ablation fired" log lines, and identical per-task detection in both arms (8/87)
- i.e. **the ablation never fired**, so the original "zero effect" was a **false
negative**. **Conclusion: the H-A1 refutation in Result 1 is void.**

**A1's first genuinely-firing controlled arm**
(`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE=true`, fixed scoring tree, QuixBugs
41-defect-program caliber, firing verified): detection **45.9% to 51.4%** (+5.5pp),
first-round `over_red` 21 to 17; paired McNemar **p=0.7237** (not significant).

**over_red strengthening-section controlled arm** (new `OVER_RED_SECTION_ENABLE`,
**default false**): detection **45.9% to 51.4%** (+5.5pp), first-round `over_red`
21 to 18; paired McNemar **p=0.7237** (not significant). **Both directions land on
identical numbers and neither is significant.**

**Two audit gaps (both fixed)**

1. **Ablation switch absent from the provenance snapshot**: the over_red first run's
   `env_snapshot` lacked the key, so **the intervention could not be verified from
   artifacts** (same class as the A1 false negative). `OVER_RED_SECTION_ENABLE` was
   added to `_env_snapshot_keys`, with a regression test.
2. **A prompt-changing ablation must use an independent cache namespace**: the
   over_red first run reused the standard arm's namespace, and the strengthening
   section is injected **only on regeneration** - so the cached regeneration
   responses were reused and **the intervention text never reached the model**.
   The first run's 59.5% is not used as evidence.

**Bottleneck relocated**: both prompt directions stalled at +5.5pp, showing they
**do not touch the main cause** - a substantial share of `over_red` tasks are
**non-terminating defect implementations** (hangs): all four `detection=None` tasks
(`bitcount`/`find_first_in_sorted`/`sqrt`/`wrap`) are of this kind (`bitcount`'s
defect `n ^= n - 1` should be `n &= n - 1` and never terminates for any n).
**No prompt can make a hanging test turn red**; what is needed is
**test-side timeout adjudication** (counting a hang as detection), registered as a
separate follow-up design task.

### Fourth measurement artifact fix and E4 re-settlement (2026-10-10)

**Artifact (fixed)**: the M1 scoring tree `_prepare_packaged_test_tree` provided only the
QuixBugs package layout `python_programs/{module}.py`, while the target module name is the
last segment of `task_id` and the production execution sandbox writes the module **flat** as
`{module}.py`; so the **flat imports** the Generator emits (e.g.
`from bitcount import bitcount`, which are correct in the environment they were generated
in) always raised `ModuleNotFoundError` in the scoring tree -> pytest `rc=2` (collection
aborted) -> `detection` was **structurally pinned to 0**.

**Fix**: dual layout (also write `{module}.py` at the tmpdir root). The **three-stage verdict
is unchanged and the bar is not relaxed** (a constantly-failing test still scores 0 under the
new layout; a regression test locks this).

**Zero-LLM verification**: of the 9 defect programs in the 12-task subset, **9/9 returned
rc=2 on both the buggy and fixed sides** before the fix; on the same artifacts, changing only
the scoring tree moved F2P detection from **0/7 to 6/7**.

**E4 re-settlement (single variable: same protocol, same cache namespace reusing the original
responses)**

| Arm | detection (41-defect-program caliber) | token/task |
|---|---|---|
| `aitester` | **17/37 = 45.9%** (before fix: 0/41 = 0.0%) | 16,038 |
| `plain_llm_df` | **31/37 = 83.8%** | **1,905** |

Paired McNemar (before vs after fix, aitester): discordant 17, chi2=15.059, **p=1.042e-04**;
2x2: **n10=17, n01=0** (one-way flips). Paired McNemar (two arms): discordant 14,
chi2=12.071, **p=0.0005**.

**Conclusion (supersedes this preregistration's earlier E4 wording)**: on the real benchmark
the full orchestration detects significantly less than plain prompting (45.9% vs 83.8%) at
8.4x the cost; the two arms are complementary (df detects cheaply, aitester repairs at 92.5%).

### E4 dataset-caliber addendum (2026-10-09, registered **before any data**)

**Finding (zero LLM cost, per-task inspection)**: `data/quixbugs` was re-fetched
successfully (commit `4257f44b0ff1181dedaedee6a447e133219fcebf`, matching the record
above), but of the **50 tasks the loader yields, 9 are QuixBugs "test driver scripts"**
(`program` ending in `_test`, e.g. `breadth_first_search_test`) with **no gold
`test_cases`**, so the M1 verdict is necessarily `detection=None` / `repair=None`.

**Decision (primary-endpoint definition unchanged; only the denominator changes)**:
- the **E4 primary endpoint `detection>0 AND resolved>0` is computed only over the 41
  defect programs that have gold material**;
- the 9 test-driver tasks are **excluded from the task set** (or listed separately as
  "non-defect samples" and kept out of the denominator);
- rationale: these 9 are **structurally unsolvable** (they are themselves test scripts),
  so counting them in the denominator would penalise the system unconditionally and bias
  E4 toward false negatives.

**Timing declaration**: this addendum is registered **before any formal E4 data exists**
(the E4 execution record still reads "pending"), satisfying the
"amendments declared before data" clause.

**Correction**: the earlier phrasing "QuixBugs 50 programs / 41 gold" should read
"**50 Python files = 41 defect programs + 9 test drivers**".

### E4 ready commands (added in batch AJ: data fetched, 2026-10-06)

The data precondition is complete: `data/quixbugs` is cloned (**commit
`4257f44b0ff1181dedaedee6a447e133219fcebf`**, gitignored, provenance
registered in DATA_CARD §4). Zero-LLM loader smoke measured: 50 programs
loaded, 41 with the complete gold triplet (buggy+fixed+official tests; the
pre-registration design section's "29 tasks" was an estimate — the decision
rule "any arm detection>0 ∧ resolved>0" does not depend on n; the 9 tasks
without official tests get detection=None per the M1 rule and stay out of
the denominator). Run command:

```bash
AITESTER_QUIXBUGS_DATA=data/quixbugs AITESTER_PROFILE=logic \
  .venv/bin/python experiments/run_main_batch.py --dataset quixbugs \
  --seed 42 --baselines aitester,plain_llm,plain_llm_df --skip-stats
```

### E2 ready commands (added in batch AJ)

Two-seed batches (87 tasks × 3 arms each; --max-pattern-repeat 2 matching
the lifespan experiment; likewise **never** pass --allow-dirty):

```bash
for SEED in 42 44; do
  AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
    --task-count 87 --seed "$SEED" \
    --baselines aitester,plain_llm,plain_llm_df \
    --max-pattern-repeat 2 --skip-stats
done
```

Pooled statistics (**the --batches whitelist must select only the new E2
batches**: same-seed reruns are deduplicated "newest batch wins", so mixing
in the old lifespan batches would mispair pre-gate and post-gate bases):

```bash
.venv/bin/python experiments/statistical_analysis.py --results-dir experiments/results \
  --batches main_batch/benchmark_synthetic_<E2_seed42 ts>.json,main_batch/benchmark_synthetic_<E2_seed44 ts>.json \
  --pool-seeds --output experiments/results/main_batch/statistical_report_e2.md
```

Primary-endpoint-1 channel counting (over-red/erase-red rows, expected → 0;
same file whitelist as above):

```bash
.venv/bin/python -c "
import json, sys
rows = [r for f in sys.argv[1:] for r in json.load(open(f))['results']['aitester']['details']]
over = sum(1 for r in rows if r.get('detection_first_status')=='red_not_repaired' and r.get('detection_rate')==0)
erase = sum(1 for r in rows if r.get('detection_first_status')=='red_then_green' and r.get('detection_rate')==0)
print(f'over-red={over}  erase-red={erase}  (n={len(rows)})')"
```

### E6 ready commands (added in batch AM: the `--per-task-token-caps` precondition flag is implemented; amended in batch AO: caps from E2 measured means)

E6 four arms = {aitester, plain_llm_df} × {standard, budget-matched};
the standard caliber reuses the E2 double-gate batches (same seeds 42/44,
same gate/profile), so only the two matched-arm batches need new runs.
**Do not use the R-P0-2 legacy constants (26,115/4,223) as matched caps**
— per the AO amendment, extract them from the E2 standard batches.

Step 1 — extract the per-arm per-task token means from the E2 standard batches:

```bash
.venv/bin/python -c "
import json, sys
for f in sys.argv[1:]:
    d = json.load(open(f))
    for arm in sorted(d['results']):
        toks = [r['token_usage']['total_tokens'] for r in d['results'][arm]['details'] if r.get('token_usage')]
        if toks:
            print(f.rsplit('/',1)[-1], arm, f'mean_total_tokens_per_task={sum(toks)/len(toks):.0f}')
" experiments/results/main_batch/benchmark_synthetic_<E2 seed42 timestamp>.json \
  experiments/results/main_batch/benchmark_synthetic_<E2 seed44 timestamp>.json
```

Step 2 — substitute `AITESTER_MEAN` / `DF_MEAN` with the printed
aitester / plain_llm_df means, then run (df(matched) is raised to the
aitester mean, nearly unconstrained for df — kept as the symmetric
control). Likewise **never** pass --allow-dirty:

```bash
AITESTER_MEAN=<E2 aitester measured mean> DF_MEAN=<E2 df measured mean>
for SEED in 42 44; do
  AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
    --task-count 87 --seed "$SEED" \
    --baselines aitester --per-task-token-caps "aitester=${DF_MEAN}" \
    --max-pattern-repeat 2 --skip-stats
  AITESTER_PROFILE=logic .venv/bin/python experiments/run_main_batch.py \
    --task-count 87 --seed "$SEED" \
    --baselines plain_llm_df --per-task-token-caps "plain_llm_df=${AITESTER_MEAN}" \
    --max-pattern-repeat 2 --skip-stats
done
```

Paired analysis: pool the matched batches with the same-seed E2 standard
batches via `--pool-seeds` (task_id prefixed with `s<seed>__`, paired by
task); the --batches whitelist = the two matched batches + the E2
same-seed batches; the decision reads the detection paired differences for
aitester(matched) vs df(standard) and df(matched) vs aitester(standard).
Guardrail check (token_budget_capped=True rows should concentrate in the
aitester(matched) arm):

```bash
.venv/bin/python -c "
import json, glob
for f in sorted(glob.glob('experiments/results/main_batch/benchmark_synthetic_*.json')):
    d = json.load(open(f)); caps = d.get('provenance', {}).get('per_task_token_caps')
    if not caps:
        continue
    for arm, rows in d['results'].items():
        n = sum(1 for r in rows['details'] if r.get('token_budget_capped'))
        print(f, arm, f'capped={n}/{len(rows[\"details\"])}', caps)"
```
