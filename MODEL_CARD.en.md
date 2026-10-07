# AITester Model Card

Last updated: 2026-10-07 (repair-engine batch I: paradigm shift to "localization → synthesis → verification" — standalone FaultLocalizer landed [RGFL-style LLM reasoning localization + Ochiai spectral corroboration dual channel, `FAULT_LOCALIZER_ENABLE` on by default] + the standalone localization metric `localization_hit_function` first measured; previous batch AL: the AK-annotation erratum restored the AJ red-line guard to green + external positioning de-emphasizes the self-repair claim in line with CITATION.cff + E6/E7 pre-registration)

## 1. System Overview

AITester is a logic-anchored multi-agent test generation and repair-evaluation
research system (detection-first criterion): given function-level repair
tasks (from a synthetic dataset or SWE-bench Lite splits), a
LangGraph-orchestrated Planner → Generator → Executor → Debugger →
PatchApplier loop generates pytest tests, executes them, diagnoses failures,
and patches code. The three-seed main batch measured repair = 0.0% (gold
adjudication) — **self-repair is a measurable metric, not a demonstrated
claim** (AL5 repositioning; ceiling attribution in
`experiments/results/main_batch/repair_ceiling_report.md`). This card
describes model usage, data provenance, and the risk surface (following
NIST AI RMF and common model-card entries; the
system is research code, not a deployed product).

## 2. Model Usage

- **Model provenance**: this project trains no models. All intelligence comes
  from user-configured OpenAI-compatible endpoints (`.env.local` `LLM_N_*`
  triples: API key / base URL / model name; any OpenAI-compatible provider and
  Zhipu zai-sdk endpoints are supported).
- **Model roles**: Planner (logic analysis / spec production), Generator (test
  code), Debugger/Review (root-cause diagnosis and patches), FaultLocalizer
  (RGFL-style reasoning fault localization, localization only no repair,
  since repair-engine batch I 2026-10-07), optional ExpertPool (parallel
  dimension experts).
- **Deterministic channels**: SpecIR v2 DSL-compiled assertions, SMT witnesses
  (`[formal]` extra), Ochiai spectral fault localization, mutation scoring, and
  the P2P regression gate are **non-LLM** deterministic components; the system
  degrades conservatively when the LLM fails (see module docstrings). Note:
  fault localization is **dual-channel** — besides the spectral channel
  (Ochiai, non-LLM), the reasoning channel (RGFL-style `FaultLocalizerAgent`,
  `FAULT_LOCALIZER_ENABLE` on by default) **consumes LLM** and degrades
  conservatively to None on failure; `FAULT_LOCALIZER_ENABLE=false` falls
  back to the pure-spectral ablation caliber.

## 3. Training Data and Data Sources

- This project **trains no models**; there is no training data.
- Evaluation data: `data/swe_bench_lite_*` (derived from the public SWE-bench
  Lite dataset; **the license is whatever the official SWE-bench repository
  declares — verify and record the exact license here before publication:
  TODO**) and programmatic synthetic tasks from
  `src/datasets/synthetic_dataset.py` (no third-party copyright).
- RAG case base: historical cases produced by the user's own experiment runs
  (local `rag_data/`).

## 4. Evaluation Protocol and Known Limitations (Honesty Notes)

- Current caliber = R-P0-2 lifespan experiment, three seeds pooled
  (2026-10-06, n=261/arm, logic profile, deepseek-flash, McNemar + BH-FDR
  all significant; see the `benchmark` section of `BASELINE.yaml` and
  `statistical_report_3seed_pooled.md`): detection plain_llm_df 44.8% >
  aitester 15.8% > plain_llm 1.5%; aitester vs df **−28pp** — the full
  system is significantly worse than the plain prompting protocol on a
  strong model (net-negative orchestration contribution; robust under dual
  bounds for the 21 missing rows).
- **repair 0.0% across all arms** (zero discordant pairs): the repair claim
  has no supporting evidence. Ceiling attribution
  (`repair_ceiling_report.md`, AK1): repair loop 154/261 → patch produced
  94.2% → plausible 46.8% → correct 0 — the bottleneck is patch plausibility
  and gold correctness, not patch production. After the 2026-10-07 paradigm
  shift, repair turns from "an honestly measured conclusion" into "a target
  to optimize" (repair-engine route: localization → synthesis → verification).
- Localization dimension: `fl_at_k` (spectral line-level Top-k hit, since R8)
  and `localization_hit_function` (LLM reasoning localization function-level
  hit, since batch I, compared against the gold changed-function set;
  schema-isomorphic placeholder when unlocalized / no gold material) ship
  alongside detection / repair metrics. The E2 final-adjudication batch
  first measured FL@1 at 19/53 = 35.8% (after the gold-diff alignment fix).
- Cost: aitester $0.0259 / plain_llm_df $0.0045 per task (officially sourced
  price table, 2026-10-06: deepseek-flash peak-hour rates, qwen-long
  standard rates; agnes unregistered absent a public official price).
- spec_compile_rate measured constantly 0.0 in the logic profile (AB1
  validation batch 12/12) — the "logic-driven" spec chain is not activated;
  current detection gains attribute to the detection-first prompting
  protocol. E1 (preregistered thresholds ≥0.3 keep / <0.2 drop) is the
  deciding experiment for that claim.
- Real SWE-bench Lite (n=20 smoke run): 0/20 resolved. The system's
  effectiveness claims are **not yet supported by real-benchmark evidence**;
  BASELINE.yaml is the single source of truth for numbers.
- The full "logic-driven" chain (SpecIR DSL / deterministic oracle / structured
  routing) is off by default; enable with `AITESTER_PROFILE=logic`.

## 5. Risk Surface and Mitigations

- **Arbitrary code execution**: LLM-generated code runs on the host.
  Mitigations: venv sandbox on by default (`EXECUTOR_USE_VENV`), optional
  Docker isolation (defaults to `--network=none`, `--read-only`,
  `--cap-drop=ALL`), optional kernel sandbox (bwrap/Landlock, Linux),
  path-traversal guards, patch evidence gate, and snapshot rollback.
- **Credential management**: API keys live only in `.env.local` (never
  committed), with gitleaks working-tree and full-history scans plus
  subprocess environment scrubbing (`scrub_os_environ`).
- **Prompt injection**: input-side `detect_prompt_injection` feature scanning
  (off by default, `INJECTION_GUARD_ENABLE`); hits warn but do not
  auto-block (the "detect + isolate" posture of the OWASP LLM Top 10).
- **Cost**: per-task token/USD hard budget (off by default) plus an LLM-call
  wall-clock budget.

## 6. Ethics and Compliance

- No human subjects, no personal-data collection; SWE-bench tasks come from
  public-repository issue/PR history.
- Under the EU AI Act this system is a software development tool (not a GPAI
  provider/deployer obligation holder); compliance for third-party LLM
  endpoints rests with the endpoint provider and the user.
- Generation disclosure: development of this project used LLM assistance;
  per team convention, code and docs carry no AI attribution and the
  repository maintainers are responsible for all content.

## 7. Citation and License

- Project code: see the repository root `LICENSE`.
- Referenced benchmarks/methods: see the five `*_BASELINE_2023-2026.md`
  surveys at the repository root (citation liveness is checked weekly by
  `scripts/check_citations.py`).
