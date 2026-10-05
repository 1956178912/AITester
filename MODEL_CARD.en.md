# AITester Model Card

Last updated: 2026-10-05 (optimization batch T6)

## 1. System Overview

AITester is a logic-driven multi-agent test generation and self-repair research
system: given function-level repair tasks (from a synthetic dataset or SWE-bench
Lite splits), a LangGraph-orchestrated Planner → Generator → Executor →
Debugger → PatchApplier loop generates pytest tests, executes them, diagnoses
failures, and patches code. This card describes model usage, data provenance,
and the risk surface (following NIST AI RMF and common model-card entries; the
system is research code, not a deployed product).

## 2. Model Usage

- **Model provenance**: this project trains no models. All intelligence comes
  from user-configured OpenAI-compatible endpoints (`.env.local` `LLM_N_*`
  triples: API key / base URL / model name; any OpenAI-compatible provider and
  Zhipu zai-sdk endpoints are supported).
- **Model roles**: Planner (logic analysis / spec production), Generator (test
  code), Debugger/Review (root-cause diagnosis and patches), optional
  ExpertPool (parallel dimension experts).
- **Deterministic channels**: SpecIR v2 DSL-compiled assertions, SMT witnesses
  (`[formal]` extra), Ochiai spectral fault localization, mutation scoring, and
  the P2P regression gate are **non-LLM** deterministic components; the system
  degrades conservatively when the LLM fails (see module docstrings).

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

- Current main batch (synthetic n=50, seed 42): detection_rate=2.0%,
  repair_rate=0.0%, false_fix_rate=89.8% (see the `benchmark` section of
  `BASELINE.yaml`); real SWE-bench Lite (n=20 smoke run): 0/20 resolved.
  The system's effectiveness claims are **not yet supported by real-benchmark
  evidence**; BASELINE.yaml is the single source of truth for numbers.
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
