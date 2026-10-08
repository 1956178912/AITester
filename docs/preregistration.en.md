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
- Power basis: `scripts/power_analysis.py` (baseline detection 2%, a 10pp
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
  enforced by `scripts/check_artifacts_tracked.py` in CI);
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
| E4 | pending | — | — | real-benchmark ladder — the 2026-10-08 QuixBugs rerun is an **R4 by-product single-arm** (n=50, no statistical report, not 3-arm), **≠ the formal E4 execution**; E4 must follow the design above: 3 arms × logic profile × primary endpoint detection>0 ∧ resolved>0 + statistical report, and must first wire quixbugs into the stats gate via R17 | — |
| E6 | pending (precondition flag implemented, batch AM) | — | — | — | — |
| E7 | pending manual review (candidate list generated, batch AO) | — | — | — | — |

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
