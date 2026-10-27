# AITester Model Card

A **detection-first** research system for repair-evaluation (attribution-aware) Python test
generation and repair. Covers model usage, data, evaluation calibers, and known limitations.

Last updated: 2026-10-27

## 1. System Overview

Given function-level repair tasks (synthetic dataset or SWE-bench Lite splits), a
LangGraph-orchestrated Planner → Generator → Executor → Debugger → PatchApplier loop
generates pytest tests, executes them, diagnoses failures, and patches code. "Multi-agent
orchestration" is an **ablatable container**, not a primary claim (ADR-0016; E2 double
gates: aitester vs plain_llm_df δ=−0.3673, structurally inferior). Research code, not a
deployed product.

## 2. Model Usage

- **Provenance**: no self-trained or fine-tuned models; all intelligence comes from
  user-configured OpenAI-compatible endpoints (`.env.local` `LLM_N_*`: API key / base URL /
  model name). The only built-in provider is the official DeepSeek endpoint and the price
  table registers only deepseek-flash — a **single model family**, so conclusions do not
  extend to other families.
- **Roles**: Planner (logic analysis), Generator (tests), Debugger/Review (diagnosis and
  patches), FaultLocalizer (RGFL-style reasoning localization, no repair), optional
  ExpertPool.
- **Deterministic channels**: SpecIR v2 DSL assertions, SMT witnesses, Ochiai spectral
  localization, mutation scoring, and the P2P regression gate are non-LLM; the system
  degrades conservatively when the LLM fails.
- **Dual-channel localization**: spectral (Ochiai, non-LLM) plus reasoning
  (`FaultLocalizerAgent`, consumes LLM, `FAULT_LOCALIZER_ENABLE` on by default, degrades to
  `None` on failure).
- **Invocation (ADR-0031)**: `LLM_THINKING_MODE` off by default (reasoning chains are billed
  as output); `LLM_JSON_MODE` on by default (seven JSON-contract sites bind
  `response_format=json_object`); `finish_reason ∈ {length, insufficient_system_resource}`
  retried as recoverable; numeric expressions in JSON values repaired by a bounded parse
  layer (no `eval`).

## 3. Data

- **No training data.** Evaluation data: `data/swe_bench_lite_*` from public SWE-bench Lite
  (the official repository distributes it under Apache-2.0; re-verify the current
  declaration) and synthetic tasks from `src/datasets/synthetic_dataset.py` (in-house, MIT).
  RAG cases come from the experiments' own history (local `rag_data/`, never committed).
- **Known biases**: Python only; synthetic templates are hand-written boundary/exception/
  contract defects that differ systematically from real-repository defect distributions;
  tasks are mostly function-level single-file; generation and repair share one LLM pool, so
  self-production/self-verification (`false_fix` measures it) is quantified but not
  eliminated.

## 4. Metrics and Calibers

- **repair = 39.31% (v2, 57/145 replayable rows, independent gold adjudication)**. The
  historical "0.0% across all arms" came from two stacked measurement artifacts (ADR-0021
  patch-field fence residue + ADR-0029 cross-file tasks not materialized); v1 caliber 35.86%
  is a cross-file artifact lower bound (matrix: `docs/design/repair_caliber_matrix.md`).
- **Generation notice**: the multi-seed pool at "n=261/arm" was withdrawn on 2026-10-24 and
  is historical only; current readings live in `BASELINE.yaml` and the rebuilt batches,
  never pooled with the 261-row pool.
- **Detection**: after the E2 double gates aitester vs plain_llm_df δ=−0.3673 — the full
  system is worse than the plain prompting protocol on a strong model; detection gains
  attribute to the detection-first protocol, not the "logic-driven" spec chain.
- **Effective pass (BA→BC)**: pytest also returns `rc==0` for all-skip/xfail/deselect
  suites, so derived readings require at least one passed and zero failed, otherwise
  fail-closed (`None`/`unverifiable`).
- **spec_compile_rate** is 0.0 in the logic profile (AB1 12/12); E1 (preregistered ≥0.3
  keep / <0.2 drop) decides that claim.
- **Cost**: aitester $0.0259 / plain_llm_df $0.0045 per task (deepseek-flash peak rates);
  plain_llm_df is a **lower bound** on recorded spend (`cost_caliber="recorded_lower_bound"`), not free.
- **Real SWE-bench Lite (n=20 smoke)**: infrastructure failure with **no valid capability
  conclusion** — 7 completions all hit 429, 3 failures, 10 timeouts
  (`experiments/results/swebench_20_summary.json`); the benchmark is on the re-run list.
- **E7 (repair-ceiling stratified sampling) is preregistered but not executed**
  (`docs/preregistration.md`): ceiling attribution cannot be claimed until E7 data exists.

## 5. Known Limitations

- Single model family and mostly synthetic data: numbers do not extrapolate to other models
  or real-repository distributions.
- repair 39.31% is a measured reading, not a claim that "self-repair is achieved"; the
  repair-engine route (localize → synthesize → verify) is in progress.
- Real-benchmark evidence is missing: the n=20 smoke run supports neither a negative nor a
  positive capability claim.
- E7 is not executed, so the repair-ceiling attribution is not closed.
- Arbitrary-code-execution risk: generated code runs on the host; the venv sandbox is on by
  default (`EXECUTOR_USE_VENV`), Docker isolation is optional (`--network=none` +
  `--read-only` + `--cap-drop=ALL`). Keys live only in `.env.local`, with gitleaks scans and
  subprocess environment scrubbing.
- No human subjects or personal data; SWE-bench tasks come from public issue/PR history. License: `LICENSE` (MIT); citation: `CITATION.cff`.
