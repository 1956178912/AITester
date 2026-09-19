> **Language**: [简体中文](CHANGELOG.md) | English (this file)

# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [0.2] - 2026-09-19 Code quality & reliability optimization round

Two atomic commits (`9f83197` + `d5f21f6`), zero functional breakage, full test suite 1459→1460 (+1 case), Ruff all green.

### Refactors and fixes
- **RAG guarded helper extraction** (`graph/rag.py` adds `rag_guarded`, dependency-injection style):
  Unifies 4 structurally identical "ENABLE_RAG precondition + retriever singleton fetch +
  try/except degradation" blocks in `graph/nodes.py` (generator retrieval / executor
  ingestion / debugger retrieval / debugger ingestion). Dependencies are injected as
  parameters instead of read from module globals, so the historical patch paths
  (`src.graph.nodes.ENABLE_RAG` / `get_rag_retriever`, used by 8 test cases) stay valid.
- **Multi-function patch sort performance** (`tools/patch_applier.py`):
  `apply_multi_function_patch` sort key changed from "each patch splits the code lines
  itself" (O(n·m)) to "pre-split lines reused" (O(n+m)); large multi-file patch
  scenarios benefit directly.
- **Experiment ranking binding fix** (`experiments/analysis.py`): `_rank_by_metric` now
  sorts (name, value) tuples, eliminating the structural risk of position-based zip
  mis-pairing; 1 new out-of-order-insertion regression test (1459→1460).
- **Database name whitelist** (`init_db.py`): `MYSQL_DATABASE` is validated against
  `[A-Za-z0-9_]+` before being interpolated into `CREATE DATABASE`, closing an
  environment-variable multi-statement SQL injection vector; import ordering normalized.
- **Lazy import elimination** (`agents/base_agent.py`): the in-function lazy imports of
  `_find_balanced_json` and `extract_focused_code` moved to module top level (neither
  module has a circular dependency), removing per-call import-mechanism overhead and
  alias noise.
- **Redaction dual-implementation convergence** (`agents/llm_client.py` + `api/api_manager.py`):
  the near-duplicate `_redact` / `_redact_log_text` implementations converge on the same
  delegation to `logging_utils.mask_sensitive_info`, with a comment marking the single
  implementation entry to prevent drift.
- **Atomic-write exception narrowing** (`graph/nodes.py`): temp-file cleanup changed from
  `except BaseException` to `except Exception` (PEP 8: KeyboardInterrupt/SystemExit must
  not enter the cleanup path; stray temp files are reaped at process exit).
- **API manager performance & configurability** (`api/api_manager.py` + `api/api_health.py`):
  `get_status` now reuses one `get_healthy_nodes()` call instead of two full node-pool
  traversals; the hardcoded 0.1s inter-node interval in batch health checks is exposed as
  `APIManagerConfig.batch_health_check_interval` (default 0.1s keeps historical behavior;
  100+ node pools can set 0 or raise it alongside a concurrent probe scheme).

### Test cleanup
- Fixed 1 tautological assertion (`tests/test_weak_coverage_modules.py`
  `assert ... or True` — the case always passed and was effectively a no-op).
- Ruff auto + manual cleanup of 24 pre-existing test-suite warnings (unused variables /
  unused imports / implicit Optional / bare `open` / redundant monkeypatch aliases, etc.).

### Engineering baseline
- Full suite **1460 passed / 0 failed** (~30s); `ruff check src/ tests/` all green
- Complete static-analysis report archived at `docs/code_analysis_report.md`
  (30 findings + "worth doing / not recommended" list; 6 high-value items landed in this round)

## [0.1] - 2026-09-18 First official release (full feature set)

### Multi-agent architecture
- Four-agent collaboration: Planner (Logic-driven CoT) / Generator (RAG-enhanced) / Executor (local/venv/Docker modes) / Debugger (hierarchical error repair)
- Twelve error categories: LLM format / import / syntax / type / index / assertion / logic / runtime / timeout / unknown / patch rejected by safety guard / RAG empty
- AST-based precise code replacement (`code_analyzer.py` / `patch_applier.py`), avoiding regex mis-matches
- Retrieval-augmented generation (ChromaDB, off by default; enable with `ENABLE_RAG=true`, persisted to `rag_data/`)

### Experiments and evaluation
- Multi-baseline comparison (aitester / plain_llm / single_agent) + ablation (Planner / Debugger toggles)
- Four dataset backends: SWE-bench / Defects4J-Python / synthetic / built-in examples
- SWE-bench source export automation (`scripts/export_swe_bench_source.py`) + data contamination detection (token-level Jaccard)
- Statistical tests (paired t-test / Mann-Whitney U / Cohen's d)
- Results analysis layer (`experiments/analyze_results.py`): success rate / coverage / iteration distribution / token efficiency / failure-cause distribution / RAG retrieval quality / repair convergence / boundary-case coverage / mutation score / assertion strength / execution feedback trace
- Built-in mutation test generator (`experiments/mutation_testing.py`, AST-level 3 mutation types, ≤20 per task)
- Test smell detection (Assertion Roulette / Magic Number / weakened assertions / trivial tests / Eager Test / Lack of Cohesion)

### Observability and reliability
- Structured JSONL tracing layer (4.1, off by default; enable with `AITESTER_TRACE_DIR`)
- Multi-candidate patch generation and verification (3.1, off by default)
- Cost-aware routing + circuit-breaker cooldown + half-open probe (3.4 + 4.1 + 4.2)
- Cross-file repair (coordinator-proposer architecture, 3.5, off by default)
- Assertion augmentation (AST-based existing-assert extraction, 3.4, off by default)
- Docker isolated execution (`EXECUTOR_USE_DOCKER`, 4.3)
- Dependency cache monitoring (venv hit-rate observability + `clean-venv-cache` CLI)

### Engineering
- Ruff lint + pre-commit + GitHub Actions CI
- **1459 test cases** / **96%** coverage / Ruff all green
- Three-layer log redaction (Handler layer / entry-point wiring / trace JSONL side-channel redaction)

### Benchmarks (synthetic dataset, 50 tasks, 3 baselines)

| Baseline | Success rate (%) | Avg. coverage (%) | Avg. iterations | Avg. elapsed (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **88.0** | **97.8** | 0.64 | 45.33 |
| Plain LLM | 68.0 | 98.0 | 0.0 | 16.6 |
| Single Agent | 4.0 | 0.0 | 0.24 | 26.85 |

Key findings:
- AITester achieves significantly higher success rate than Plain LLM (88.0% vs 68.0%), with comparable coverage (97.8% vs 98.0%)
- Single Agent baseline success rate is only 4.0% (2/50 tasks passed), confirming the necessity of the multi-agent architecture
- Statistical test: AITester vs Single Agent difference is highly significant (p < 0.001)

## Version notes

The current version is 0.2. All previously internal iteration versions (0.9.x / 0.10 etc.) are no longer recorded separately; their features have been merged into 0.1, and 0.2 is a code-quality optimization round on top of it (no new features — refactors/fixes/test cleanup only, zero functional breakage).
