# AITester Model Card

A **detection-first** research system for repair-evaluation (attribution-aware) Python test
generation and repair. Covers model usage, data, evaluation calibers, and known limitations.

Last updated: 2026-11-12 (refreshed against the current authoritative batch)

> **Caliber statement**: this card's current caliber = `experiments/results/RESULTS_DATA_PACK_20261111.json`
> (50-cell zero-LLM aggregate, per-metric n_obs) + the manuscript `paper/tex/manuscript.tex` (40 pages /
> 86 references). Derived verdict rows and the 50-cell aggregate are DOI-locked and public under DOI
> `10.5281/zenodo.24136905` (no raw traces or model transcripts). Numbers marked "historical readings" belong
> to a retired protocol generation: **never pooled with the current manuscript**, never current capability
> conclusions; round-by-round records: `CHANGELOG.en.md` and `docs/design/repair_caliber_matrix.md`.

## 1. System Overview

Given five benchmarks (QuixBugs, BugsInPy, SWE-bench, TestGenEval, ULT; per-face sizes and availability in
`docs/DATA_CARD.en.md`), a LangGraph-orchestrated Planner → Generator → Executor → Debugger → PatchApplier
loop generates pytest tests, executes them, diagnoses failures, and patches code.

"Multi-agent orchestration" is an **ablatable container**, not a primary claim. The current manuscript's
central claims are the false-fix paired reporting of "declared pass ≠ adjudicated real pass" (RQ2) and the
harness-exclusion disclosure (RQ3); orchestration carries no independent capability claim. Research code,
not a deployed product.

## 2. Model Usage

- **Provenance**: no self-trained or fine-tuned models; all intelligence comes from user-configured
  OpenAI-compatible endpoints (`.env.local` `LLM_N_*`: API key / base URL / model name). `PROVIDER_TEMPLATES`
  ships two providers (DeepSeek and xiaomi MiMo); the current authoritative batch compares `deepseek-flash`
  and `mimo-v2.6-pro` cell by cell, concurrency resolved per provider allowance; prices and allowances are
  registered in `MODEL_RATE_LIMITS`. **Cross-model readings are split by model × arm × face, never pooled.**
- **Roles**: Planner (logic analysis), Generator (tests), Debugger/Review (diagnosis and patches),
  FaultLocalizer (RGFL-style reasoning localization, no repair), optional ExpertPool.
- **Deterministic channels**: SpecIR v2 DSL assertions, SMT witnesses, Ochiai spectral localization,
  mutation scoring, and the P2P regression gate are non-LLM; the system degrades conservatively when the LLM fails.
- **Dual-channel localization**: spectral (Ochiai, non-LLM) plus reasoning (`FaultLocalizerAgent`, consumes
  LLM, `FAULT_LOCALIZER_ENABLE` on by default, degrades to `None` on failure).
- **Invocation (ADR-0031)**: `LLM_THINKING_MODE` off by default (cross-model comparisons pinned to one
  reasoning tier; reasoning chains billed as output); `LLM_JSON_MODE` on by default (seven JSON-contract
  sites bind `response_format=json_object`); `finish_reason ∈ {length, insufficient_system_resource}` retried
  as recoverable; numeric expressions in JSON values repaired by a bounded parse layer (no `eval`).

## 3. Data

- **No training data.** This project trains no models.
- Evaluation data: the current authoritative batch is `test_run_20261106T101605Z` (50 cells) +
  `rerun_swebench_20261110` + `rerun_testgeneval_20261110_v5`; the three-directory source whitelist is pinned
  by `scripts/tools/results_data_pack_20261111.py` so smoke batches cannot pollute the manuscript base.
  Per-face licences, leak controls and unverified items: `docs/DATA_CARD.en.md`.
- RAG cases come from the experiments' own history (local `rag_data/`, never committed).
- **Known biases**: Python only; function-level single-file and repository-level tasks differ substantially
  at the execution layer; generation and repair share one LLM pool, and the self-production/self-verification
  loop is intercepted by independent held-out gold adjudication; SWE-bench `harness_invalid` is a
  protocol-level structural exclusion, recorded row by row and kept out of the verdict denominator (RQ3).

## 4. Metrics and Calibers

- **Current authoritative caliber**: every declared pass is adjudicated against held-out gold material; pass
  rates must be reported paired with false-fix rates (manuscript RQ2, per-cell adjudicated real passes on
  QuixBugs). All 50-cell metrics derive from `RESULTS_DATA_PACK_20261111.json` with per-metric `n_obs`; no
  observation means no zero denominator. The first-pass verdict reading (4,458 judged / 711 passed) is
  the paper's RQ1 endpoint, but quoting it alone collides with the false-fix caliber: the table must be
  reported paired under RQ2, and first-pass verdicts must not be read as a capability claim
  (`RESULTS_DIGEST_20261111.json` carries this warning verbatim).
- **Effective pass (BA→BC)**: pytest also returns `rc==0` for all-skip/xfail/deselect suites, so derived
  readings require at least one passed and zero failed, otherwise fail-closed (`None`/`unverifiable`).
- **E7-r2 (2026-11-12 design revision)**: the human-calibration frame is replaced by a **census of the 89
  declared-pass verdict rows** on QuixBugs in the current authoritative batch (= every verdict row of
  manuscript tab:falsefix): a 42-row patch track under the five-class audit, a 47-row suite track with
  structural confirmation + shape labels. Preparation pack and handoff zip are generated; **adjudication is
  still pending human execution** (two independent raters + third-party merge, Cohen's κ unchanged); the old
  72-row `patch_plausible` stratified frame is void.
- **Historical readings (retired protocol generation, never pooled with the current manuscript)**: repair
  39.31% (v2, 57/145 replayable rows), v1 35.86%, the "n=261/arm" three-seed pool, E2 δ=−0.3673,
  `spec_compile_rate` constantly 0.0, aitester $0.0259 / plain_llm_df $0.0045 per task, the n=20 SWE-bench
  Lite smoke (429 throttling, no capability conclusion). Facts of their time; provenance: CHANGELOG + caliber matrix.
- **Current SWE-bench face**: of 2,197 rows, 1,919 are `harness_invalid` (structural exclusion), 278
  judgeable; excluded rows never enter the denominator, and smoke throttling is not a capability reading.

## 5. Known Limitations

- Current readings are limited to this batch of two endpoints × five arms × five benchmarks; no extrapolation
  to untested endpoints or task sets; **no cross-batch pooling** — historical readings must carry a batch label.
  One of the five arms (specification replacement) never received its anchor table and ran at the
  detection-first fallback; its column is a repeat of that arm, not a delivered specification treatment.
- The current manuscript centers on the verdict caliber (declared vs adjudicated real pass) and **does not
  claim** "self-repair achieved"; the repair-engine route (localize → synthesize → verify) is in progress.
- E7-r2 human adjudication not executed; external calibration not closed; no Kappa artifact exists anywhere.
- Arbitrary-code-execution risk: generated code runs on the host; venv sandbox on by default
  (`EXECUTOR_USE_VENV`), Docker optional (`--network=none` + `--read-only` + `--cap-drop=ALL`). Keys only in
  `.env.local` (never committed), with gitleaks scans and subprocess environment scrubbing.
- No human subjects or personal data; SWE-bench tasks come from public issue/PR history. License: `LICENSE` (MIT); citation: `CITATION.cff`.
