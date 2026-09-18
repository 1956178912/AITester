> **Language**: [简体中文](CHANGELOG.md) | English (this file)

# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

The current version is 0.1, the project's first official release. All previously internal iteration versions (0.9.x / 0.10 etc.) are no longer recorded separately; their features have been merged into 0.1.
