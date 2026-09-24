> **Language**: [中文版](README.md) | English (this document)

# AITester: A Logic-Driven Multi-Agent Test Generation and Self-Repair System

> AITester is a Python automation framework for test generation and self-repair based on multi-agent collaboration.
> Core innovations: **Logic-driven Chain-of-Thought (Logic-driven CoT)** + **Hierarchical Repair Mechanism**.

## Test Status

| Metric | Status |
|------|------|
| **Total Tests** | ✅ 1672 collected (full dependencies) / reduced environment (when chromadb/matplotlib are missing, RAG/visualization cases are auto-skipped: ~1612 collected) |
| **Unit Tests** | ✅ Full: 1672 passed, 0 failed; reduced environment: ~1612 passed (`skipif`/`importorskip` graceful degradation, not false-positive ERROR) |
| **Code Coverage** | 94% total coverage (src/; 0.7 debt items P2×8 landed with 7 regression cases + full-audit round added 13 cases, full suite 1672 green; core modules: base_agent 100% / api_manager 94% / dataset_loader 94% / graph/nodes.py 95% / code_analyzer 100% / planner 100% / dependency 96% / multi_candidate 94% / cross_file 95% / rag/retriever 95%) |
| **Known Failures** | ✅ 0 (RAG / dataset download tests fixed; CI 3.12/3.14 all green; when optional dependencies are missing, related cases are skipped via `skipif` instead of erroring) |
| **Security Audit** | ✅ No hardcoded secrets (`.env*` / `.env.local.bak` / `.private` are gitignored / removed); three-layer log redaction defense (Handler-layer SensitiveFilter/Formatter + entry-point wiring + trace JSONL side-channel redaction); APIManager log points use in-place `_redact()` (independent of entry wiring, embedded-safe); `get_status()` redacts base_url at the exit; **all three execution paths (local/venv/Docker) now uniformly scrub LLM credentials via `credential_scrub.scrub_os_environ` (dynamic pattern covering the entire `LLM_N_API_KEY` family, closing the leak path where generated code inherits host credentials)**; LLM file cache logging is a known acceptable risk (local trusted domain, not committed to git) |
| **Latest Optimization** | ✅ 2026-09-24 full-audit fixes: credential scrubbing factored into dynamic-pattern `credential_scrub.py` shared by all three execution paths + CLI `finally`-block fragile code eliminated + multi-candidate node made side-effect-free + patch function-location regex→AST + 5 ruff nits cleared; full suite 1672 passed / zero regression / mypy 0 errors / ruff all green. Prior to that: 2026-09-24 code-quality round + 2026-09-23 static-type zeroing + 0.7 debt items landed. See [CHANGELOG.en.md](CHANGELOG.en.md). |
| **Core Module Coverage** | ✅ code_analyzer.py (100%), helpers.py (100%), llm_cache.py (100%), planner.py (100%), base_agent.py (100%), mysql_client.py (98%), token_usage.py (98%), reports/generator.py (99%), api_manager.py (94%), rag/retriever.py (95%), dataset_loader.py (94%), graph/nodes.py (95%), config/config_manager.py (95%), multi_candidate.py (94%), observability/trace.py (98%), error_classifier.py (95%), cli/app.py (93%), cli/output.py (94%), logging_utils.py (95%), tools/dependency.py (96%), executor_modes.py (96%), cross_file.py (95%), credential_scrub.py (100%) |
| **Code Style** | ✅ Ruff checks all pass (`ruff check` + `ruff format --check`, CI pinned to 0.16.3; 15 ruff warnings cleared + 33-file format normalization in 0.6 + 5 tests/ nits cleared in the full-audit round) |
| **Recent Changes** | ✅ 2026-09-24 full-audit fixes: credential scrubbing factored into `src/utils/credential_scrub.py` (dynamic `LLM_N_API_KEY` pattern, shared by local/venv/Docker paths) + CLI `finally`-block fragile code eliminated (explicit `final_state` init) + multi-candidate node side-effect-free (stats passed via update dict) + patch function-location regex→AST (decorated/commented functions no longer truncated early) + `requirements.txt` now explicitly declares `openai==2.54.0`; see [CHANGELOG.en.md](CHANGELOG.en.md). |

For more details, see [CHANGELOG.md](CHANGELOG.md), [QUICKSTART.md](QUICKSTART.md), [docs/api_reference.md](docs/api_reference.md), [docs/usage_examples.md](docs/usage_examples.md).

## Development Tools

### Lint and Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) for code checking and formatting (CI pinned to `0.16.3`, consistent with `requirements.lock`, to avoid upstream releases drifting the formatting gate):

```bash
# Install ruff (pin the same version as CI)
pip install "ruff==0.16.3"

# Check code
ruff check .

# Auto-fix fixable issues
ruff check --fix .

# Format code
ruff format .

# Check formatting (without modifying)
ruff format --check .
```

### Pre-commit Hooks

Pre-commit hooks are recommended to run checks automatically before commits:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Manually run all hooks
pre-commit run --all-files
```

### CI/CD

The project is configured with GitHub Actions continuous integration, supporting:
- Multi-Python-version testing (3.12, 3.14; the lower bound is determined by locked dependencies: scipy requires ≥3.12)
- Ruff lint checks
- pytest tests + coverage reports
- Dependency security scanning (pip-audit; chromadb 1.5.9 hits 5 known vulnerabilities (PYSEC-2026-311 counted twice + PYSEC-2026-3813/3814/3815), explicitly exempted because no fixed version is yet available on PyPI; see the ci.yml comments and CHANGELOG for details)
- Consistency validation between requirements and requirements.lock (scripts/check_lock_sync.py)
- Test failure diagnostic annotations: when a test step fails, the list of FAILED/ERROR cases is automatically written as GitHub annotations (readable via the check-runs annotations API, no need for admin to download logs)

### Test Commands

```bash
# Run all unit tests (full 1672 cases; when chromadb/matplotlib are missing, RAG/visualization cases are auto-skipped, ~1612 collected)
.venv/bin/python -m pytest tests/ -v

# Run tests with coverage
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run only workflow integration tests (end-to-end orchestration)
.venv/bin/python -m pytest tests/test_workflow.py tests/test_workflow_extended.py -v

# Run only dataset loader tests
.venv/bin/python -m pytest tests/test_dataset_loader.py tests/test_dataset_loader_extended.py -v
```

## Quick Start

```bash
# 0. Create a virtual environment (Python 3.12+ recommended; the locked dependency scipy requires ≥3.12)
python3 -m venv .venv
source .venv/bin/activate

# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment variables
cp .env.example .env
# Edit .env and fill in the API Key and other information

# 3. Initialize the database (optional, if you need to persist experiment data)
python init_db.py

# 4. Run a single-file test
python main.py run examples/calculator.py --func divide

# 5. Batch benchmark (built-in example dataset, three baseline comparisons)
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. Run the full system only + limit task count
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. Ablation experiment: enable Planner only
ENABLE_PLANNER=true ENABLE_DEBUGGER=false python experiments/run_benchmark.py --dataset examples

# 8. Run synthetic dataset benchmark (no external download needed, customizable scale)
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --baselines aitester,plain_llm,single_agent

# 9. Visualize experiment results (with statistical significance tests)
python experiments/visualize_results.py
python experiments/visualize_results.py --results-dir experiments/results/synthetic_full

# 10. Run the benchmark in parallel (speeds up multi-task processing)
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 20

# 11. Specify parallelism with the --parallel option
python experiments/run_benchmark.py --dataset examples --parallel 4

# 12. Set a global timeout with the --timeout option
python main.py run examples/calculator.py --func divide --timeout 120

# 13. Benchmark results are emitted as JSON (structured JSON goes directly to stdout, no extra option needed)
python experiments/run_benchmark.py --dataset examples
```

## Performance Optimization Notes

### RAG Retriever Singleton

The system implements a **lazy-loading singleton pattern** for the RAG retriever, initializing the ChromaDB client only once during the entire workflow execution, avoiding the overhead of repeatedly loading the embedding model (~100MB) and opening the vector index.

**Performance gain**: saves 2-6 seconds of initialization time per task.

**Technical implementation**: the `get_rag_retriever()` function in `src/graph/rag.py` (re-exported via `workflow.py` to preserve the legacy import path).

### LLM File Cache (saves tokens)

The LLM calls in `base_agent` are wired to a **persistent file cache** (`src/cache/*.json`, named by `md5(prompt + system_prompt)`). Identical input hits the cache from the second call onward, consuming no more tokens — for model providers that "stop once the free quota is used up", this significantly extends usable time.

- **Enabled by default**; set the environment variable `AITESTER_LLM_CACHE=0` to disable it; the cache directory can be overridden with `AITESTER_LLM_CACHE_DIR`.
- **Only successful responses are cached**: failed calls (e.g. 403 quota exhausted) are not written to the cache.
- The cache is a local optimization artifact; `src/cache/` is already in `.gitignore` and will not be committed.

```bash
export AITESTER_LLM_CACHE=0      # Temporarily disable the cache (when you need to "regenerate with a different approach")
rm -rf src/cache                # Clear the cache so all prompts call the LLM again
```

### LLM Client Reuse (shared connection pool)

The LLM clients in `base_agent` are now **reused** per configuration, avoiding a new client (including its underlying HTTP connection pool) on every call:

- **OpenAI-compatible path** (`ChatOpenAI`): cached by `(model_name, temperature, api_key, base_url)`, capped at 16 entries (FIFO eviction).
- **zai SDK path** (`ZhipuAiClient`): cached by `(api_key, base_url)`, capped at 16 entries.

**Performance gain**: multiple LLM calls with the same configuration share a connection pool, eliminating repeated connection-establishment overhead; under concurrent multi-task execution the connection pool state is consistent and behavior is more predictable.

**Technical implementation**: `_get_or_create_chat_client()` and `_get_or_create_zai_client()` in `src/agents/base_agent.py`.

### Model Quota Probing (scripts/check_quota.py)

Probes whether each configured model is currently "alive / free quota exhausted (403) / rate-limited / key invalid / model not found"; each model receives only a 1-token request, and **no secret is ever printed**:

```bash
.venv/bin/python scripts/check_quota.py                      # Probe all LLMs configured in .env.local
.venv/bin/python scripts/check_quota.py --provider aliyun_bailian   # Scan all models in a provider directory
.venv/bin/python scripts/check_quota.py --models qwen-max,qwen-plus --provider aliyun_bailian
.venv/bin/python scripts/check_quota.py --dry-run           # Only list the targets to be probed, send no requests
```

### LLM Call Timeout Configuration

The `LLM_TIMEOUT` configuration item controls the timeout for a single LLM call, preventing a task from hanging when the API responds too slowly.

```bash
# .env file configuration
LLM_TIMEOUT=60          # Single LLM call timeout (seconds), default 60
LLM_RETRY_WAIT=30       # LLM retry wait time (seconds), default 30
EXECUTION_TIMEOUT=30    # pytest execution timeout (seconds), default 30
```

### Parallel Execution (BENCHMARK_PARALLELISM)

Multi-threaded parallel execution of multiple benchmark tasks is supported, significantly reducing total wall time for large test batches.

```bash
# Run in parallel with 4 threads (environment variable approach)
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 50

# Use the --parallel option (command-line approach)
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --parallel 4

# Serial execution (default)
python experiments/run_benchmark.py --dataset synthetic --task-count 50
```

**Note**: parallel execution requires a dedicated API Key per thread; API Key rotation can be implemented through multiple configuration groups such as `LLM_1_*`, `LLM_2_*`, etc.

See the [Performance Tuning Guide](docs/performance_guide.md) for more details.

### Timeout Control (--timeout)

The timeout for a single test execution is controlled by the `--timeout` option or the `EXECUTION_TIMEOUT` environment variable, preventing tasks from hanging.

```bash
# Specify a timeout (seconds) on the command line
python main.py run examples/calculator.py --func divide --timeout 120

# Or via environment variable
EXECUTION_TIMEOUT=120 python main.py run examples/calculator.py --func divide
```

On timeout the test is force-terminated, its status is marked `timeout`, and the Debugger can perform targeted repair for timeout scenarios.

### JSON Output (default behavior for benchmark results)

`run_benchmark.py` always prints the summary results to stdout as structured JSON on exit (it also writes `benchmark_<dataset>_<timestamp>.json` under `--output-dir`; with `--save-state`, per-stage state is additionally saved to `raw/<task_id>/`). It can be piped directly to tools like `jq` for programmatic processing. Note: this script has no `--json` switch — JSON output is the default and only result output form.

```bash
# Structured JSON results go directly to stdout
python experiments/run_benchmark.py --dataset examples

# Combine with --output-dir to save the result JSON to a directory
python experiments/run_benchmark.py --dataset examples --output-dir ./results
```

The JSON output contains complete result statistics, per-baseline detailed data, and performance metrics, ready for downstream analysis scripts.

See the [Performance Tuning Guide](docs/performance_guide.md) for more details.

## Project Structure

```
AITester/
├── src/                              # Core source code
│   ├── agents/                       # Multi-agent modules
│   │   ├── base_agent.py             # Agent base class (LLM calls + file cache + JSON parsing; client factory split out to llm_client.py)
│   │   ├── llm_client.py             # LLM client utility functions (ChatOpenAI factory + module-level connection pool cache, split in 0.1)
│   │   ├── planner.py                # Test planner (includes logic-driven chain of thought)
│   │   ├── generator.py              # Test code generator (with RAG augmentation support)
│   │   ├── executor.py               # Test executor (class body + local execution orchestration; import fix / result parsing / sandbox & Docker modes / subprocess runtime split out into executor_* submodules)
│   │   ├── executor_imports.py       # Import-path auto-fixing (module-name extraction / sys.path injection / similar-name replacement, split in 0.1)
│   │   ├── executor_modes.py         # venv sandbox + Docker isolation execution modes (split in 0.1)
│   │   ├── executor_output.py        # Result parsing (coverage / failed cases / error info, split in 0.1)
│   │   ├── executor_runtime.py       # Subprocess running, retry & temp resource cleanup (split in 0.1)
│   │   ├── debugger.py               # Debugging repair agent (hierarchical error repair)
│   │   └── error_classifier.py       # Error type classifier (rule-based matching)
│   ├── api/                          # API configuration management
│   │   ├── api_manager.py            # Multi-LLM config CRUD (.env.local / llm_configs.json) + circuit breaker/routing
│   │   └── api_health.py             # API health status and routing strategy data models (APIHealth/APIManagerConfig/RotationStrategy)
│   ├── config/                       # Configuration management
│   │   ├── config_manager.py         # LLM config add/remove/query
│   │   └── config_generator.py       # .env / llm_configs template generation
│   ├── datasets/                     # Dataset loading layer
│   │   ├── dataset_loader.py         # SWE-bench loader + data model / abstract base / factory (Defects4J & InMemory subclasses split out)
│   │   ├── dataset_defects4j.py      # Defects4J-Python loader (split in 0.1)
│   │   ├── dataset_inmemory.py       # Built-in sample dataset (split in 0.1)
│   │   └── synthetic_dataset.py      # Synthetic dataset generator (local generation)
│   ├── cli/                          # Command-line interface (click command groups + rich output)
│   │   ├── app.py                    # CLI command definitions and task execution
│   │   └── output.py                 # ANSI/Rich terminal output utilities
│   ├── utils/                        # Shared utilities
│   │   ├── exceptions.py             # Unified exception hierarchy
│   │   ├── helpers.py                # Regex / JSON / code-block extraction utilities
│   │   └── logging_utils.py          # Logging utilities
│   ├── tools/                        # Tool function modules
│   │   ├── code_analyzer.py          # AST code analysis (exact replacement, avoids regex false matches)
│   │   ├── patch_applier.py          # Patch application (supports whole-file and single-function modes)
│   │   ├── code_context.py           # AST smart extraction (P0 large-file context optimization)
│   │   ├── dependency.py             # Dependency detection and venv cache management (P1 execution isolation) + 4.4 hit-rate stats/cleanup
│   │   ├── multi_candidate.py        # Multi-candidate patch generation and validation filtering (3.1, off by default)
│   │   └── cross_file.py             # 3.5 cross-file repair (coordinator-proposer architecture, off by default)
│   ├── graph/                        # Workflow orchestration modules
│   │   ├── workflow.py               # LangGraph workflow graph (supports ablation switches; node registration and RAG wiring)
│   │   ├── nodes.py                  # Node function implementations (_planner/_generator/_executor/_debugger/_patch_applier/_cross_file_analyzer)
│   │   ├── rag.py                    # RAG retriever singleton management (get_rag_retriever, re-exported via workflow.py)
│   │   ├── tracing.py                # Tracing layer wiring (task-level JSONL sessions, re-exported via workflow.py)
│   │   ├── state.py                  # Global state definitions (TypedDict) + create_initial_state factory (single construction point)
│   │   ├── token_usage.py            # Thread-local LLM token usage stats (P0 efficiency metric)
│   │   └── llm_cache.py             # LLM in-memory LRU cache (optional, with hit statistics)
│   ├── observability/                # Structured observability (4.1)
│   │   └── trace.py                  # JSONL node-level tracing (off by default, enabled via AITESTER_TRACE_DIR)
│   ├── prompts/                      # Prompt templates
│   │   └── templates.py              # Planner/Generator/Debugger system prompts (PLANNER_SYSTEM_PROMPT, etc.)
│   ├── db/                           # Database module
│   │   └── mysql_client.py           # MySQL singleton client (tasks, tests, repair records)
│   ├── rag/                          # Retrieval-augmented generation module
│   │   └── retriever.py              # ChromaDB vector retriever (test cases and repair cases)
│   ├── reports/                      # Report generation
│   │   └── generator.py             # Experiment result reports
│   └── experiments/                  # Experiment analysis
│       └── analysis.py               # Statistical tests and result analysis
├── experiments/                      # Experiment script modules
│   ├── run_benchmark.py              # Batch benchmark (multi-baseline comparison + ablation experiments + fairness token output)
│   ├── visualize_results.py          # Result visualization (bar charts + detailed tables + statistical tests)
│   ├── analyze_results.py            # Result analysis script (4.3 + 1.1/1.2/1.3/3.2/4.4: Markdown summary + RAG auto-summary + repair convergence/quality proxy + smell detection + mutation score + boundary coverage + execution trace + cache hit rate, legacy JSON fallback)
│   ├── compare_failures.py           # Failure-flip task comparison (Planner/Debugger/environment attribution + 5.3 cross-batch failure-mode comparison)
│   ├── analyze_failures.py           # Failure case clustering report (for technical review)
│   ├── mutation_testing.py           # 1.2 built-in mutation generator (AST-level three mutant classes + mutation_score_from_details aggregation)
│   ├── contamination_check.py        # 2.1 SWE-bench data contamination check (token-level Jaccard overlap)
│   ├── difficulty_stratification.py # 2.2 task difficulty stratification analysis
│   ├── run_large_scale.py            # Large-scale experiment entry point
│   ├── run_statistical_test.py       # Statistical test entry point
│   └── statistical_analysis.py       # Statistical analysis utilities
├── reproduce.sh                    # One-click experiment reproduction script (quick/full modes)
├── tests/                            # Unit tests
│   ├── test_code_analyzer.py
│   ├── test_error_classifier.py
│   ├── test_patch_applier.py
│   └── test_dataset_loader.py        # Dataset loader tests (new)
├── docs/                             # Documentation
│   ├── algorithm_design.md           # Algorithm design and theoretical description
│   ├── api_reference.md              # API reference
│   ├── usage_examples.md             # Usage examples
│   ├── performance_guide.md          # Performance tuning guide (including profiling benchmarks)
│   ├── failure_analysis.md           # Failure case analysis (historical snapshot)
│   └── history/                      # Archived historical round work records
│       ├── optimization_plan.md
│       └── optimization_report.md
├── examples/                         # Example code under test (with known bugs)
│   ├── calculator.py                 # Calculator example (division by zero, negative factorial bugs)
│   ├── buggy_library.py              # Algorithm library example (binary search, sort-merge, etc.)
│   └── string_utils.py               # String utilities example (palindrome, Caesar cipher, etc.)
├── main.py                           # CLI entry point (thin wrapper, implementation in src/cli/)
├── config.py                         # Global configuration (includes ablation experiment switches)
├── init_db.py                        # Database initialization script
├── setup.py                          # Package management configuration
├── requirements.txt                  # Python dependency list
├── Dockerfile                        # Docker image definition
└── .env.example                      # Environment variable template
```

## Core Methods

### 1. Logic-driven Chain-of-Thought
Before outputting the test plan, the Planner performs explicit analysis of the function's **input domain, output domain, preconditions, postconditions, and boundary cases**, guiding the Generator to produce test cases with logic coverage.

**Technical implementation**:
- The `PlannerAgent.plan()` method in [src/agents/planner.py](src/agents/planner.py)
- The `PLANNER_SYSTEM_PROMPT` in [src/prompts/templates.py](src/prompts/templates.py)

### 2. Hierarchical Error Repair Strategy
Test failures are classified into twelve categories: **LLM response format anomaly (llm_format_error), import failure (import_error), syntax error (syntax), type mismatch (type_error), index out of range (index_error), assertion failure (assertion), test logic error (logic_error), runtime exception (runtime), timeout (timeout), unknown (unknown), patch rejected by safety guard (patch_validation_failed), and all-empty RAG retrieval (rag_retrieval_empty)**. Each category uses a differentiated repair strategy (P2 refinement: the import/type/logic categories were split out from the older five-category set; 1.2 residual: LLM_FORMAT_ERROR and INDEX_ERROR split out of UNKNOWN; 1.1 status refinement: PATCH_VALIDATION_FAILED and RAG_RETRIEVAL_EMPTY are flow-status categories, determined by `refine_failure_category()` at task wrap-up based on repair_history/rag_stats signals — the first 10 go through `classify()` text regex, the last 2 do not go through regex; successful tasks are returned as-is).

**Technical implementation**:
- The `ErrorClassifier` class in [src/agents/error_classifier.py](src/agents/error_classifier.py) (rule-based matching)
- The `DebuggerAgent.debug()` method in [src/agents/debugger.py](src/agents/debugger.py)
- The `DEBUGGER_SYSTEM_PROMPT` in [src/prompts/templates.py](src/prompts/templates.py)

### 3. AST-Based Precise Code Replacement
The `ast` module is used for function parsing and replacement, avoiding false matches from regex in scenarios with nested functions or same-named functions.

**Technical implementation**:
- The `replace_function_code()` function in [src/tools/code_analyzer.py](src/tools/code_analyzer.py)
- The `apply_patch_to_code()` function in [src/tools/patch_applier.py](src/tools/patch_applier.py)

### 4. Retrieval-Augmented Generation (RAG)
ChromaDB stores historically successful test cases and repair patches; before the Generator and Debugger produce output, similar cases are retrieved as reference.

**Technical implementation**:
- The `TestCaseRetriever` class in [src/rag/retriever.py](src/rag/retriever.py)
- Enabled/disabled via the `ENABLE_RAG` flag in [src/graph/workflow.py](src/graph/workflow.py)

### 5. Multi-Baseline Comparison and Ablation Experiments (new)
Four experiment configurations are supported for one-click comparison of individual component contributions:

| Baseline Name | Configuration | Description |
|---------|------|------|
| `aitester` | Both Planner+Debugger enabled | Full multi-agent system |
| `plain_llm` | Both Planner+Debugger disabled | Pure LLM single-call baseline |
| `single_agent` | Planner+Debugger merged into a single call | Single-agent comparison baseline |

**Ablation switches** (defaults are read from [config.py](config.py) and can be overridden via environment variables injected through `.env`; `.env` is already in `.gitignore` and not committed):
```bash
ENABLE_PLANNER=true      # Enable Planner (default true)
ENABLE_DEBUGGER=true     # Enable the Debugger repair loop (default true)
ENABLE_RAG=false         # Enable RAG retrieval augmentation (default false)
```

### 5.1 Multi-Candidate Patches and Validation (3.1, off by default)
The "one bad step and every step after is wrong" risk of single-patch repair: when the LLM occasionally emits syntactically incomplete patches, deletes functions by mistake, or edits the wrong lines, the bad patch pollutes target_code and carries an incorrect diagnosis into the next round, wasting the repair budget. The multi-candidate patch strategy generates N candidates within the same round (perspective-perturbed prompts steer each candidate down a different repair path: minimal change / root-cause fix / defensive fix), a static filter (`ast.parse` syntax + function integrity + 10% length safety) eliminates bad candidates, optional execution validation runs tests per candidate and picks the one with the highest pass rate/coverage, and only a selected candidate that strictly beats the original code is committed.

**Technical implementation**:
- `generate_candidates()` / `select_best_candidate()` / `static_validate_patch()` in [src/tools/multi_candidate.py](src/tools/multi_candidate.py)
- Wired in via `_patch_applier_node` in [src/graph/workflow.py](src/graph/workflow.py); `ENABLE_MULTI_CANDIDATE_PATCH` defaults to false to preserve historical experiment semantics; when no valid candidate exists it automatically falls back to a single patch

### 5.2 Structured Observability (4.1, off by default)
Append-only JSONL records each agent node's input/output, decision path (debug/done/regenerate), token consumption, and wall-clock time per task, enabling per-agent replay for experiment analysis (logs are for human reading, get redaction-sampled, and cannot support structured replay). When `AITESTER_TRACE_DIR` is unset, everything is a no-op with zero performance tax; when set, traces are written as `<task_uuid>.trace.jsonl` and pass through redaction.

**Technical implementation**:
- The `TraceSession` class in [src/observability/trace.py](src/observability/trace.py)
- Per-node recording in the workflow nodes (planner/generator/executor/debugger/patch_applier/_should_debug); the benchmark entry point and CLI record task_end in a finally block

### 5.3 Cost-Aware Routing (3.4 + 3.2 configurable threshold)
The `COST_AWARE` strategy in `APIManager` ranks by a composite score of "success rate 50% + 1/cost 50%", so failover avoids shifting the full traffic onto expensive providers; when failing over to an expensive node with `cost_weight >= threshold` (`APIManagerConfig.cost_alert_threshold`, default 2.0, configurable in 3.2 — if the threshold is too low and false alarms are frequent, raise it to e.g. 3.0/5.0; if you are more cost-sensitive, lower it; no code changes needed) a WARNING cost alert is logged (`cost_alert_enabled` can turn it off; the alert message prints the configured threshold to avoid misleading tuning). `LLMConfig.cost_weight` is read via `LLM_N_COST_WEIGHT` (0.1~1000; unset defaults to 0.0 = no information, APIManager falls back to the 1.0 baseline; `APIManagerConfig.node_cost_weights` supports an explicit mapping override).

**Technical implementation**:
- `RotationStrategy.COST_AWARE` / `_select_node_cost_aware()` / the cost alert branch in [src/api/api_manager.py](src/api/api_manager.py)

### 5.4 RAG Included in Main Experiments (2.3)
`reproduce.sh` explicitly passes `--enable-rag` by default for synthetic/built-in datasets (`rag_data/` is persisted and reused across experiments); `--no-rag` falls back to the config default; `run_benchmark.py` adds a `--no-rag` option that, together with `--enable-rag`, overrides `config.ENABLE_RAG`.

### 5.5 Result Analysis Script (4.3 + 1.1/1.2 first-round metric extensions)
`experiments/analyze_results.py` extracts from the benchmark JSON: success rate / coverage / iteration count distribution / token efficiency / per-baseline failure-reason distribution (1.2 refined categories counted separately) / RAG retrieval quality / repair convergence efficiency (first-attempt success rate, iteration and time statistics for successful vs failed tasks) / multi-dimensional quality proxies (coverage and time proxies, optional `generated_test` assertion-line-count proxy, failure category Top N); it prints a Markdown summary to the terminal and writes `analysis_summary.md`; when legacy JSON lacks `token_metrics`/`rag_metrics`/`generated_test` keys, it automatically falls back or degrades gracefully without crashing.

```bash
# Analyze the most recent benchmark results
python experiments/analyze_results.py --results-dir experiments/results

# Analyze a specific file
python experiments/analyze_results.py --input experiments/results/benchmark_xxx.json
```

### 5.6 Circuit Breaker Cooldown + Half-Open Probing (4.1 + 4.2)
The `APIManager`'s circuit breaker enters a cooldown period (`APIManagerConfig.circuit_cooldown_seconds`, default 60s) after a node's consecutive failures reach `max_consecutive_failures`. During the cooldown, even if the health-check thread flips `is_healthy` back to True, the routing layer (`get_healthy_nodes()` and the backup candidates in `_build_node_list`) still skips that node, avoiding re-hitting a dead provider with traffic (wasting time and tokens); `mark_success` resets the circuit breaker, and `get_status()` exposes `circuit_open_remaining_s` and `circuit_state` (closed / open / half_open) fields for monitoring.

The 4.2 half-open probe (on by default, `APIManagerConfig.enable_half_open_probe=True`): when the cooldown expires, the node does not immediately resume full routing but enters a "half-open" window — the node becomes a routing candidate (`in_circuit_half_open`) carrying one probe request; a successful probe closes the circuit breaker and restores full routing, while a failed one re-opens a half-cooldown (`min(cooldown/2, half_open_probe_penalty_cap_seconds)`, default cap 30s), preventing a dead provider from being repeatedly hit. The success and exception branches of `call()` and `check_health()` uniformly consume the probe result; setting `enable_half_open_probe=False` reverts to the 4.1 pass-through behavior, for comparison experiments.

### 5.7 SWE-bench Source Export Automation (2.1)
The official SWE-bench JSONL has no `instance_code` field (a task only contains patch text). A new `scripts/export_swe_bench_source.py` automates the fill-in: it reads the downloaded JSONL, extracts the first non-test target file from the patch's `+++ b/<path>`, and exports it read-only via `git show <base_commit>:<path>` (without polluting the working tree), producing an enrichment JSONL in `SWE_BENCH_ENRICHMENT` format; it supports `--instance-ids` (comma-separated or @file, combined with the missing-list output of check-dataset for batch fill-in), `--dry-run`, and `--limit`. `SWEBenchDataset` adds `tasks_missing_source()` (identifies tasks whose instance_code falls back to issue text); the `check-dataset` quality report outputs the list of instance_ids missing source code and fill-in guidance.

```bash
# Fill in all missing source (requires the SWE-bench repo cache + git)
python scripts/export_swe_bench_source.py --dry-run          # Inspect the export plan first
python scripts/export_swe_bench_source.py --instance-ids @missing_ids.txt
# Load the enrichment (auto-merged into tasks' instance_code)
python main.py check-dataset swe_bench
```

### 5.8 Cross-File Repair (3.5, off by default)
About 40% of tasks in real datasets (SWE-bench / Defects4J) require multi-file changes. Coordinator-proposer architecture: the `cross_file_analyzer` node (enabled with `CROSS_FILE_ENABLE=true`) is inserted between `executor → debugger`, performing AST cross-file import dependency analysis (single-entry view) and writing the dependency edges into `state["cross_file_deps"]`; the cross-file branch of `_patch_applier_node` applies patches to multiple modules in topological order (callee first, caller later), and if any file's application fails the whole thing rolls back (same semantics as single-file `safe_apply_patch`). Single-file projects degrade automatically (when there are no dependency edges, `cross_file_plan=None`, taking the single-file path).

```bash
# Enable cross-file repair (set the environment variables explicitly)
CROSS_FILE_ENABLE=true CROSS_FILE_MAX_MODULES=5 python main.py run examples/calculator.py
# Off by default (the historical single-file semantics are unchanged)
```

Design document: [docs/design/cross_file_repair.md](docs/design/cross_file_repair.md)

### 5.9 Assertion Augmentation Strategy (3.4, off by default)
Before generating, `GeneratorAgent` extracts existing `assert` statements in the code under test via AST (deduplicated, at most 10) and injects them into the prompt as "anchor assertions", steering the LLM away from code smells such as assertion weakening / tautological assertions / unnamed magic numbers. The default `false` preserves historical generation semantics; enabling it requires an explicit `ASSERTION_AUGMENT_ENABLE=true`.

### 5.10 Dependency Cache Monitoring (4.4)
The `venv` cache is upgraded from "reuse without monitoring" to "observable hit rate + cleanable":
- `get_venv_cache_stats()`: in-process cumulative hit/create events + on-disk JSON cross-process aggregation, returning `hit_rate = hits/(hits+creates)`
- `list_venv_cache()`: lists every venv in the cache directory (name/path/size_mb/created_at)
- `clear_venv_cache(max_age_days, max_size_mb)`: filters and cleans by age/size; when both are None, clears everything

### 5.11 Test Smell / Convergence Curve / Convergence Failure Mode / Boundary Coverage / Mutation Score / Assertion-Strength AST (1.2/1.3)
Six new conservative, re-computable sections in `experiments/analyze_results.py` (all "field-missing → skip", legacy JSON never crashes):
- **Test smell detection (1.2)**: an AST scan over `details[].generated_test` identifying four smell types: Assertion Roulette / Magic Number / assertion weakening / trivial tests
- **Repair convergence curve (1.3)**: aggregates cumulative pass rate and average time by iteration round 0/1/2/3+, showing "how the pass rate changes as iterations increase"
- **Convergence failure-mode attribution (1.2)**: for tasks that still fail at MAX_ITERATIONS, distinguishes "cannot pinpoint root cause" (repeated identical diagnosis, patch never written) vs "cannot produce an effective patch" (patch written but still failing, or repeatedly rejected by safety guards)
- **Boundary case coverage (1.3)**: AST-based conservative check of `generated_test` for coverage of None / empty string / empty collection / 0 / -1 / >= / <= boundary conditions; reports per-type hit counts and coverage rate
- **Mutation score (1.3)**: collects `details[].mutation_score` (produced by an external mutation tester such as mutmut); aggregates mean / high (>=0.7) / low (<0.4) distribution; skips the section when the field is absent
- **Assertion-strength AST enhancement (1.3)**: in addition to the original `assert` line-count metric, adds an AST basis (`ast.parse` + `ast.Assert` node counting), outputting `ast_avg_assertions` and `ast_parse_failed_tasks`

When legacy JSON lacks `generated_test` / `mutation_score` fields, it degrades gracefully without crashing.

### 5.12 Failure Root-Cause Classification and Case Knowledge Base (5.3)
Additions in `experiments/analyze_failures.py`:
- **Failure root-cause classification**: three root causes (`llm_capability` / `dependency` / `framework`) conservatively and heuristically classified by `error_category` + `diagnosis` keywords
- **Case knowledge base**: typical failure cases selected with diversity priority over `error_category`, structured into `experiments/results/failure_knowledge_base.json` (containing task_id / root_cause / reproducible_steps / suggested_fix)

A new CLI option `--knowledge-base/-k` controls the output path.

### 5.13 Execution Feedback Trace Collection (3.2)
`state.py` adds an `execution_trace` field (list, default `[]`; `create_initial_state` keeps it in sync). `_executor_node` in `nodes.py` appends one record to `state["execution_trace"]` on every execution:

```
{
  "iteration": int,
  "passed": bool,
  "coverage": float,
  "coverage_delta": float | None,   # None for the first round
  "elapsed_seconds": float,
  "reward_signals": {               # conservative linear normalization, recorded only, never used for routing
    "correctness": 0.0 | 1.0,
    "efficiency": 0.0~1.0,          # 1 - elapsed / EXECUTION_TIMEOUT
    "simplicity": 0.0~1.0           # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
  }
}
```

A pure observability layer, enabled by default (does not affect repair routing). `run_benchmark.py` result rows carry `execution_trace` (failure branch falls back to `None` to keep key-set parity); `analyze_results.py` adds an "Execution Feedback Trace Summary (3.2)" section: observed task count / total executions / average rounds / first-round pass rate / last-round correctness & efficiency means / first-vs-last coverage trend (delta). Legacy JSON without the field skips the section.

> Purpose: preparing data for future execution-feedback-driven fine-tuning (BoostAPR-style methods) — every benchmark automatically writes "pass/fail, coverage change, elapsed time, multi-dimensional reward signals" into the result JSON; no extra trace-collection script needed.

### 6. Standard Dataset Integration (new)
Multiple datasets are supported through the `src/datasets/` subpackage (`dataset_loader.py` + `synthetic_dataset.py`):

```python
from src.datasets import SWEBenchDataset, load_dataset
from src.datasets import SyntheticDataset

# Load the built-in example dataset (no download needed, 3 predefined bug tasks)
dataset = load_dataset("examples")

# Load SWE-bench (data must be downloaded first)
dataset = SWEBenchDataset(subset="lite")  # 500 tasks
SWEBenchDataset.download_from_huggingface(subset="mini")

# Generate a synthetic dataset (local generation, no external data needed)
dataset = SyntheticDataset(task_count=50, seed=42)
```

## Experiment Reproduction

### Environment Requirements
- Python 3.12+ (the locked dependency scipy requires ≥3.12)
- MySQL 5.7/8.0 (optional, for persisting experiment data)
- LLM API Key (e.g. OpenAI, DeepSeek, etc.)

### Reproduction Steps
```bash
# 1. Clone the repository
git clone <repository-url>
cd AITester

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env and fill in the API Key and other information

# 4. Initialize the database (optional)
python init_db.py

# 5. Run the benchmark (built-in example dataset, three baseline comparisons)
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. Limit the task count (quick validation)
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. Inspect results
ls experiments/results/
python experiments/visualize_results.py
```

### Running the SWE-bench Benchmark (requires data download)
```bash
# Method 1: download the lite subset from HuggingFace (~500 tasks)
python -c "from src.datasets import SWEBenchDataset; SWEBenchDataset.download_from_huggingface(subset='lite')"

# Method 2: download manually and place into ~/.cache/aitester/swe_bench/swe_bench_instances.jsonl

# Run the benchmark
python experiments/run_benchmark.py --dataset swe_bench --subset lite --task-limit 10
```

### SWE-bench Loading Quality Validation and Source Enrichment (P0)

The official SWE-bench JSONL **does not include a source-code-under-test field** (only issue text + repair patch);
running the benchmark directly means the LLM never sees the real code, so results can only validate the workflow and produce no effective repair comparison.
Diagnose/fill in with the following two steps:

```bash
# 1. Validate loading quality (per-task instance_code/test_code completeness + full quality report)
python main.py check-dataset swe_bench --subset lite

# 2. Provide a source enrichment file (JSONL, keyed by instance_id):
#    {"instance_id": "r/r-1", "instance_code": "def f(): ...", "test_code": "def test_f(): ..."}
#    Can be generated by exporting target file contents via git checkout <base_commit>
SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

Target function localization: the loader automatically extracts the target function name
from the hunk headers of the official `patch`
(`metadata["suggested_function"]`; measured extraction rate 96% on a local cache of 225 tasks);
the benchmark uses it to initialize `target_function`, driving the
**AST focused extraction** of the Planner/Generator/Debugger — large source files are no longer hard-truncated "half head, half tail", but instead
keep the import + target function + the helper functions it calls directly (see `src/tools/code_context.py`).

### Result Files

Benchmark results are saved in the `experiments/results/` directory as JSON:
```
experiments/results/benchmark_<dataset>_<timestamp>.json  # e.g. benchmark_examples_20260814_120000.json, benchmark_synthetic_20260814_120000.json
```
This directory is already in `.gitignore` and will not be committed to version control.

---

## Synthetic Dataset and Statistical Tests

### Synthetic Dataset
AITester ships a built-in `SyntheticDataset` that generates defect tasks of any scale without relying on SWE-bench/Defects4J:
- 10 predefined bug patterns (division by zero, boundary conditions, logic errors, etc.)
- Task count controlled by `--task-count` (≥ 50 recommended to meet publication requirements)
- A fixed seed guarantees reproducible results

### Statistical Significance Testing
`visualize_results.py` automatically outputs:
- **Paired t-test**: compares the statistical significance of pass rates between baselines
- **Mann-Whitney U test**: a non-parametric test as a supplement
- **Cohen's d**: quantifies effect size
- **p-value heatmap**: visualizes significance differences

Output files:
- `experiments/results/charts/statistical_significance.png`
- `experiments/results/charts/summary_stats.md`

---

## Execution Isolation and Dependency Management (P1)

Local execution by default runs under the system Python: when a third-party library imported by the code under test is missing, the test fails immediately,
and it is impossible to distinguish "code bug" from "missing environment dependency"; dependencies of different tasks also conflict with each other.
With the venv sandbox enabled, each task executes in a temp directory + an isolated venv cached by dependency combination,
with `PYTHONPATH` pointing only at the sandbox directory:

```bash
# Isolated venv execution (missing dependencies are only detected and logged; test results are still produced normally)
EXECUTOR_USE_VENV=true python experiments/run_benchmark.py --dataset swe_bench --task-limit 10

# Auto pip install missing dependencies before execution (installed only into the venv, the system environment stays clean)
EXECUTOR_USE_VENV=true EXECUTOR_AUTO_INSTALL_DEPS=true \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

- venvs are disk-cached by "missing package combination" (`~/.cache/aitester/venvs/`); tasks with the same dependencies are reused;
- missing dependencies are written into the result's `error_info.missing_dependencies` and classified by the error
  classifier into a distinct `import_error` category (as opposed to `syntax`, where the code itself has wrong syntax);
- when dependency installation fails, it returns `dependency_install_failed` early, so test results do not mislead analysis.

## RAG Retrieval Augmentation and Quality Metrics (P1)

RAG is off by default (`ENABLE_RAG=false`). Once enabled, the Generator/Debugger retrieve
similar historical cases; the retrieval corpus is persisted to `rag_data/` (configurable via `RAG_PERSIST_PATH`),
**reusable across experiment runs**, with a default TTL of 7 days (`RAG_TTL_SECONDS`):

```bash
# Explicitly enable RAG for an ablation experiment (the retrieval corpus accumulates across runs)
python experiments/run_benchmark.py --dataset synthetic --enable-rag

# Inspect RAG retrieval quality metrics (results.<baseline>.rag_metrics in the result JSON:
# retrievals / hits / hit_rate / avg_max_similarity; JSON is the default output, no switch needed)
python experiments/run_benchmark.py --dataset synthetic --enable-rag
```

Evaluate retrieval corpus quality standalone (Hit Rate@k / MRR, against known labeled queries):

```python
from src.rag.retriever import TestCaseRetriever

retriever = TestCaseRetriever(persist_path="rag_data")
metrics = retriever.evaluate_retrieval(
    [{"query": "def add(a, b): ...", "expected_id": "<doc_id at ingest time>"}],
    top_k=5,
)
# → {"num_queries": 1, "hits": 1, "hit_rate": 1.0, "mrr": 1.0}
```

## Efficiency Metrics and Baseline Comparison Diagnostics (P0)

Every benchmark run automatically records token consumption (`results.<baseline>.token_metrics`
and per-task `token_usage` in the result JSON), used for "full system vs plain LLM cost-effectiveness" comparison.
If you find a baseline overtaking the full system, use the comparison tool to locate the diverging stage:

```bash
# 1. Run two baselines and persist per-stage artifacts (test plan / generated code / diagnosis / patch)
python experiments/run_benchmark.py --dataset synthetic \
    --baselines aitester,plain_llm --save-state

# 2. Find tasks where "plain_llm succeeded but aitester failed", compare stage by stage + output a Markdown report
python experiments/compare_failures.py \
    --results experiments/results/benchmark_synthetic_<ts>.json \
    --raw-dir experiments/results/raw --max-tasks 5 \
    --report experiments/results/failure_analysis.md
```

For each flipped task the report gives a "suspected stage" hint (Planner noise / Debugger not converging /
environment dependency failure) and summarizes the token comparison.

---

## Docker One-Click Reproduction

Using Docker fully isolates the execution environment and avoids local dependency conflicts.

```bash
# Build the image (first time takes ~5 minutes, depending on network speed)
docker build -t aitester:latest .

# Run the benchmark
# LLM keys are mounted into the container together with .env.local in $(pwd); no -e needed (the old OPENAI_API_KEY variable is deprecated)
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python experiments/run_benchmark.py --dataset examples --task-limit 1

# Run a single-file test
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python main.py run examples/calculator.py
```

## Unit Tests

```bash
# Run all tests (full 1672 cases; optional dependencies missing → auto-skip degradation)
.venv/bin/python -m pytest tests/ -v

# Run tests and generate a coverage report
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run tests for a specific module
.venv/bin/python -m pytest tests/test_dataset_loader.py -v
```

**Tested modules** (68 test files, full 1672 collected pytest cases; reduced environment collects ~1612 / auto-skips RAG and visualization cases, total src coverage 94%):

| Test File | Test Function Count | Coverage Scope |
|---------|-------|---------|
| `test_api_manager.py` | 77 | API manager (rotation/weighted-random/health-aware strategies, health thread switch, failure threshold config wiring, 4.1 circuit breaker cooldown state machine and routing filter, 1.5 cooldown boundary 3 cases, 4.1 redaction wiring 2 cases) |
| `test_api_circuit_breaker.py` | 16 | 4.4/0.6 circuit-breaker exponential backoff (`API_CIRCUIT_BACKOFF` on/off dual paths) + Prometheus export (`API_PROMETHEUS_EXPORT` default empty string) |
| `test_api_manager_extended.py` | 74 | API manager extended paths (health recovery, rate-limit marking, 4.2 half-open probe TestHalfOpenProbe 12 cases) |
| `test_base_agent.py` | 39 | JSON extraction, code block extraction, client reuse, AST smart extraction |
| `test_base_agent_extended.py` | 46 | Exponential backoff retry, LLM cache, zai client reuse |
| `test_cli_app.py` | 30 | 27 | CLI commands (list-examples/--version/argument validation/parallel/json edge cases + 1.4 timeout pass-through/concurrency fault tolerance/check-dataset edge cases/glob concurrency 8 cases) |
| `test_cli_output.py` | 10 | CLI output layer regression (colorize TTY dual branch, success/error/warning/info icons and stdout/stderr routing, print_rich_table empty list/missing key fallback/coverage=0.0 not misjudged as N/A, O-01 batch) |
| `test_cli_parallel.py` | 10 | Concurrent dispatcher `_dispatch_parallel_tasks` and `run` concurrent branch regression (rich/no-rich dual paths, per-task fault tolerance, CI gate exit 1) (0.1) |
| `test_cli_run.py` | 6 | run command orchestration (timeout/coverage threshold pass-through) |
| `test_cli_console_output.py` | 8 | run non-JSON console summary (success/failure/diagnosis/suggestions) + _dispatch_concurrent rich/fallback/JSON-silent branches (0.1) |
| `test_code_analyzer.py` | 17 | AST parsing, cyclomatic complexity, code replacement |
| `test_code_context.py` | 18 | 11 | AST smart extraction (P0 large-file context) |
| `test_complex_logic.py` | 12 | Complex business logic (email validation, etc.) |
| `test_config_generator.py` | 26 | LLM config generator templates |
| `test_config_manager.py` | 35 | 32 | Config manager (LLM config add/remove) |
| `test_config.py` | 15 | 14 | config.py defaults and tolerant parsing |
| `test_core_modules.py` | 29 | Core module smoke tests (multiple classes of BenchmarkTask / InMemoryDataset / Planner / Executor / DatasetLoader) |
| `test_contamination_check.py` | 15 | 2.1 data contamination detection (token extraction / Jaccard overlap / grading / detect scan / rendered section) |
| `test_contamination_multidim.py` | 25 | 2.1 multi-dimensional contamination detection (structural AST-skeleton LCS + semantic token-bag cosine, three-dimensional similarity / combined risk level / full detect flow / resistant-benchmark registry) |
| `test_cost_aware_routing.py` | 13 | Cost-aware routing and expensive-provider cost alerts (3.4 + 3.2 configurable threshold 4 cases) |
| `test_dataset_loader.py` | 83 | Dataset loader (InMemory/SWEBench) |
| `test_dataset_loader_extended.py` | 73 | Dataset loader extended paths (raw loading/field validation) |
| `test_dataset_validation.py` | 22 | SWE-bench loading quality validation and source enrichment (P0) + tasks_missing_source (2.1) |
| `test_debugger.py` | 29 | Error diagnosis, RAG injection, classification pass-through |
| `test_defects4j_smoke.py` | 9 | 3.4 Defects4J-Python loader smoke test (graceful degradation without data directory / full-directory parsing / field integrity) |
| `test_dependency.py` | 43 | Dependency detection and venv management (P1) + 4.4 cache monitoring (hit-rate stats/listing/cleanup, 8 cases) |
| `test_dependency_edge_cases.py` | 14 | Dependency edge branches (stdlib fallback / find_spec exception / venv creation timeout / OSError silent degradation, new in 0.1) |
| `test_error_classifier.py` | 89 | 85 | Twelve-category error classification and repair strategy mapping (P2 refinement + 1.2 residual + 1.1 status refinement: refine_failure_category) |
| `test_error_classifier_new_categories.py` | 16 | 5.2 two new error-category determinations (`EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED`, priority / fix-strategy description / final_state wiring) |
| `test_exceptions.py` | 33 | Custom exception classes and decorators |
| `test_executor.py` | 50 | 48 | Coverage parsing, failed case parsing |
| `test_executor_docker.py` | 11 | 4.3 Docker execution mode (unavailable diagnostics / mode flag / docker precedence over venv / subprocess env credential stripping + TestDockerExecutionFlow in-container execution 6 cases + sandbox cleanup fallback) |
| `test_executor_sandbox.py` | 14 | Sandbox execution path and dependency installation (P1, including install failure short-circuit / target file missing edge case; subprocess patch target migrated to executor_runtime) |
| `test_experiments_analysis.py` | 15 | Experiment result analysis (ranking/statistics) |
| `test_experiments_scripts.py` | 36 | visualize result selection / normalized experiment return keys / benchmark parallelism regression (0.1) + 4.3 analyze_results pure functions + 2.3 RAG auto-summary + 1.1/1.2 repair convergence and quality proxy metrics + 1.2 test smell detection + 1.3 repair convergence curve (6 cases) |
| `test_failure_kb.py` | 181 | 5.3 failure case knowledge base + cross-batch failure pattern comparison (failure_knowledge_base structured JSON / cross_batch_comparison batch trends / three major failure root causes) |
| `test_generator.py` | 43 | parametrize validation, import fixing, LLM calls + 3.4 assertion augmentation (TestAssertionAugmentation: AST extraction of existing assert, off by default, 9 cases) |
| `test_llm_cache.py` | 16 | LLM in-memory cache |
| `test_llm_file_cache.py` | 5 | LLM file cache hit/miss |
| `test_logging_utils.py` | 14 | Log redaction regexes (sk- prefix / dotted-segment / prefix-less long hex·base64, three forms; 0.1 redaction extension regression) |
| `test_mysql_client.py` | 15 | MySQL client singleton/transaction/connection pool parameters |
| `test_multi_candidate.py` | 23 | Multi-candidate patch generation and static/execution validation filtering (3.1) |
| `test_packaging.py` | 3 | Packaging integrity (subpackage __init__ all present) |
| `test_patch_applier.py` | 38 | Patch application (whole-file/single-function modes) |
| `test_planner.py` | 5 | PlannerAgent planning logic serialization |
| `test_prompts_templates.py` | 14 | Structural contract of the three system-prompt constants (key instruction sections/error categories/JSON output format, 0.1) |
| `test_rag_metrics.py` | 13 | RAG retrieval quality metrics Hit Rate/MRR (P1) |
| `test_rag_retriever.py` | 42 | RAG retriever add/remove/query/clear and persistence |
| `test_report_generator.py` | 48 | Error report generator (including twelve-category classification branches) |
| `test_run_benchmark.py` | 5 | Benchmark result construction and exception path regression (0.1 deduplication refactor) |
| `test_swe_bench_source_export.py` | 13 | SWE-bench source export script (patch target file extraction / enrichment persistence / dry-run, 2.1) |
| `test_smell_detection_v2.py` | 6 | 1.1 smell-detection hardening (Eager Test / Lack of Cohesion trigger and no-trigger cases + syntax-error fallback) |
| `test_state.py` | 8 | AITesterState single-construction-point factory (create_initial_state key-set guard / module_name derivation / mutable container isolation, deep-refactor batch) |
| `test_viz_significance.py` | 6 | Statistical significance convergence (visualize_results reuses statistical_analysis paired primitives / NaN placeholder / primitive reference lock, deep-refactor batch) |
| `test_string_utils.py` | 10 | String utilities |
| `test_synthetic_dataset.py` | 5 | Synthetic dataset generation and determinism verification |
| `test_token_usage.py` | 9 | Token consumption stats (P0 efficiency metric) |
| `test_trace_observability.py` | 12 | Structured JSONL tracing layer (4.1) |
| `test_venv_cache_monitoring.py` | 11 | 4.4 venv cache capacity monitoring (`get_venv_cache_size_mb` / `check_venv_cache_size` 5GB threshold alert / stats file path dynamic-ization / hit-rate / cleanup) |
| `test_workflow.py` | 38 | Workflow graph construction and routing + 3.5 cross-file repair (CROSS_FILE_ENABLE enabled/disabled paths, 2 cases) |
| `test_workflow_extended.py` | 47 | 38 | Workflow extended paths (RAG initialization singleton, planner default plan deduplication, etc.) |
| `test_cross_file.py` | 27 | 3.5 cross-file repair (AST dependency analysis / coordinator-proposer / multi-file patch application / single-file fallback / serialization) |
| `test_cross_file_bidirectional.py` | 16 | 2.2 cross-file bidirectional dependency graph (single-direction / bidirectional baselines / `CROSS_FILE_BIDIRECTIONAL` env-var switch / symbol definition-line localization) |
| `test_analyze_failures.py` | 13 | 5.3 failure root-cause classification (three root causes: LLM/dependency/framework) + case knowledge base + CLI --knowledge-base |
| `test_weak_coverage_modules.py` | 16 | 5.1 weak-coverage module hardening round 1 (cli_output print_rich_table edge cases / error_classifier new classification paths / executor_runtime cleanup and retry exception branches) |
| `test_weak_coverage_modules2.py` | 10 | 5.1 weak-coverage module hardening round 2 (config_generator main entry / prompts_templates constant structure / synthetic_dataset edge generation) |
| `test_weak_coverage_modules3.py` | 13 | 5.1 weak-coverage module hardening round 3 (trace disk-write failure degradation / analysis statistical-test edge cases / error_classifier branches / cli_output non-rich degradation / prompts __main__) |

## Configuration

All configuration items are managed uniformly in [config.py](config.py) and injected via `.env` and `.env.local` files:

| Config Item | Description | Default |
|--------|------|--------|
| `LLM_N_API_KEY` | LLM API key (multi-config support, see `config.local.example`) | required |
| `LLM_N_BASE_URL` | LLM Base URL | - |
| `LLM_N_MODEL_NAME` | LLM model name | agnes-3.0-flash |
| `MODEL_NAME` | Backward compatible: default LLM model name | agnes-3.0-flash |
| `MAX_ITERATIONS` | Maximum number of repair iterations | 3 |
| `COVERAGE_THRESHOLD` | Coverage threshold | 80.0 |
| `CROSS_FILE_ENABLE` | 3.5 cross-file repair switch (coordinator-proposer architecture, off by default) | false |
| `CROSS_FILE_MAX_MODULES` | 3.5 cross-file dependency analysis max module count | 5 |
| `ASSERTION_AUGMENT_ENABLE` | 3.4 assertion augmentation strategy (AST extraction of existing assert into prompt, off by default) | false |

| `EXECUTION_TIMEOUT` | pytest execution timeout (seconds) | 30 |
| `LLM_TIMEOUT` | Single LLM call timeout (seconds) | 60 |
| `LLM_RETRY_WAIT` | LLM retry wait time (seconds) | 30 |
| `ENABLE_PLANNER` | Enable Planner (ablation switch) | true |
| `ENABLE_DEBUGGER` | Enable the Debugger repair loop (ablation switch) | true |
| `ENABLE_RAG` | Enable RAG retrieval augmentation | false |
| `RAG_PERSIST_PATH` | RAG persistence path (empty = in-memory mode, default project-root rag_data/) | rag_data |
| `RAG_COLLECTION_NAME` | RAG ChromaDB collection name | aitester_cases |
| `RAG_TTL_SECONDS` | RAG cache TTL (seconds; default 7 days in persistence mode) | 604800 |
| `EXECUTOR_USE_VENV` | venv sandbox isolated execution (dependency isolation, P1) | false |
| `EXECUTOR_AUTO_INSTALL_DEPS` | Auto pip install missing dependencies before execution (P1) | false |
| `EXECUTOR_DEP_INSTALL_TIMEOUT` | Dependency installation timeout (seconds) | 120 |
| `MYSQL_POOL_MIN_CACHED` | Minimum reserved connections in the pool | 5 |
| `MYSQL_POOL_MAX_CACHED` | Maximum idle connections in the pool | 10 |
| `MYSQL_POOL_MAX_CONNECTIONS` | Maximum total connections in the pool | 20 |
| `MYSQL_POOL_TIMEOUT` | Connection acquisition wait timeout (seconds) | 30 |
| `LLM_N_COST_WEIGHT` | Relative cost multiplier of the Nth LLM (3.4 cost-aware routing; 0.0 = unset, APIManager falls back to the 1.0 baseline) | 1.0 |
| `SWE_BENCH_ENRICHMENT` | SWE-bench source enrichment JSONL path (P0, optional) | none |
| `BENCHMARK_PARALLELISM` | Batch test parallelism (0 = serial) | 0 |
| `TEMPERATURE` | LLM sampling temperature | 0.2 |

## Advanced Switches (all off by default, enable as needed)

The following switches are all provided as environment variables; defaults preserve historical experiment semantics unchanged; enabling them is an explicit act.

| Switch | Default | Effect when enabled | Related section |
|------|------|---------|----------|
| `ENABLE_MULTI_CANDIDATE_PATCH` | false | Multi-candidate patch generation and validation filtering (3.1) | 5.1 |
| `AITESTER_TRACE_DIR` | unset (no-op) | Structured JSONL tracing layer (4.1) | 5.2 |
| `ENABLE_MUTATION_SCORING` | false | 1.2 mutation-score evaluation: after the benchmark run, computes `mutation_score` per task from "generated test vs source under test" (built-in lightweight mutation generator, ≤ `MUTATION_MAX_MUTANTS` mutants per task). Significantly longer runtime; off by default to preserve the historical baseline. | 5.14 |
| `MUTATION_MAX_MUTANTS` | 10 | 1.2 cap on mutants evaluated per task (takes effect together with `ENABLE_MUTATION_SCORING=true`) | 5.14 |
| `CROSS_FILE_ENABLE` | false | Cross-file repair (coordinator-proposer architecture, 3.5) | 5.8 |
| `ASSERTION_AUGMENT_ENABLE` | false | Assertion augmentation strategy (AST extraction of existing assert, 3.4) | 5.9 |

See [QUICKSTART.md](QUICKSTART.md) and [.env.example](.env.example) for details.

### Multi-LLM Configuration Support

The system supports configuring multiple LLM providers, enabling API Key rotation and high availability:

```bash
# .env.local configuration example
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com/v1
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com/v1
LLM_2_MODEL_NAME=model-2
```

Usage in code:
```python
from config import LLM_CONFIGS, DEFAULT_LLM_CONFIG

# Get all configurations
all_configs: list[LLMConfig] = LLM_CONFIGS
# Get the default configuration (the first one)
default_config: LLMConfig | None = DEFAULT_LLM_CONFIG
```

For more configuration details, see [docs/api_reference.md](docs/api_reference.md) and [config.local.example](config.local.example).

---

## CLI Command Reference

### `python main.py run` — Run a single test task

```
python main.py run <target_file> [OPTIONS]

Arguments:
  target_file    Path to the Python file under test (must exist)

Options:
  --func, -f          Name of the function under test; omit to test all functions
  --max-iterations    Maximum number of repair iterations, default 3
  --coverage-threshold  Coverage threshold percentage, default 80.0
  --timeout           pytest execution timeout (seconds), overrides the EXECUTION_TIMEOUT config
  --json              Output results in JSON format (stdout carries pure JSON only; logs/progress go to stderr, making piping to jq easy)
```

> **Exit codes**: when any test task fails (including task crash), the process exits with `1`; when all pass, it exits with `0`, so it can be used as a gate in CI/scripts.

**Examples:**
```bash
# Test a single function
python main.py run examples/calculator.py --func divide

# Specify a maximum iteration count
python main.py run examples/buggy_library.py --func binary_search --max-iterations 5

# Output results as JSON
python main.py run examples/string_utils.py --func is_palindrome --json
```

### `python experiments/run_benchmark.py` — Batch benchmark

```
python experiments/run_benchmark.py [OPTIONS]

Options:
  --dataset, -d       Dataset name (examples/synthetic/swe_bench/defects4j_py)
  --subset, -s        Data subset (e.g. swe_bench_lite)
  --baselines, -b     Comma-separated list of baseline methods (default: aitester,plain_llm,single_agent)
  --output-dir, -o    Result output directory (default: experiments/results)
  --verbose, -v       Verbose log output
  --task-limit, -n    Limit the number of tasks to run
  --task-count, -c    Number of synthetic dataset tasks
  --parallel, -p      Number of parallel tasks (replaces the BENCHMARK_PARALLELISM environment variable)
  --timeout           Global execution timeout (seconds)
  --json              Output results in JSON format
  --enable-rag        Explicitly enable RAG retrieval augmentation (P1 ablation experiment; defaults to config.ENABLE_RAG)
  --save-state        Persist per-stage state to <output-dir>/raw/ (for P0 baseline comparison diagnostics)
```

**Examples:**
```bash
# Quick validation (2 tasks, single baseline)
python experiments/run_benchmark.py --dataset examples --task-limit 2 --baselines aitester

# Parallel execution (4 threads, 100 synthetic tasks)
python experiments/run_benchmark.py --dataset synthetic --task-count 100 \
    --baselines aitester,plain_llm,single_agent --parallel 4

# Run the aitester full system only (JSON is the default output, no --json switch needed)
python experiments/run_benchmark.py --dataset examples --baselines aitester
```

### `python main.py list-examples` — List example files

```
python main.py list-examples
```

## Datasets

| Dataset Name | Data Source | Task Count | Download Requirement |
|-----------|---------|-------|---------|
| `examples` | Built-in examples (calculator/buggy_library/string_utils) | 3 | No download needed |
| `synthetic` / `synth` | Locally generated, customizable scale | Configurable | No download needed |
| `swe_bench` | HuggingFace SWE-bench | 500 (lite) | Requires calling download_from_huggingface() |
| `defects4j_python` | Defects4J-Python dataset | Variable | Requires manual download |

For more details, see the [Performance Tuning Guide](docs/performance_guide.md), [API Reference](docs/api_reference.md), and [Usage Examples](docs/usage_examples.md).

## Tech Stack

- **LLM framework**: LangChain + LangGraph
- **Database**: MySQL (pymysql driver)
- **Vector database**: ChromaDB (RAG module)
- **Test framework**: pytest + pytest-cov
- **Command line**: Click
- **Datasets**: SWE-bench / Defects4J-Python (loaded via the HuggingFace datasets library)
- **Visualization**: matplotlib + pandas

## Benchmark Results

### Built-in Example Dataset (examples, 3 tasks)

| Task | Status | Coverage | Iteration Count | LLM Call Count |
|------|------|--------|----------|-------------|
| `calculator.py::divide` | ✅ PASS | 100% | 0 | 1 |
| `buggy_library.py::binary_search` | ✅ PASS | 100% | 1 | 2 (including retry) |
| `string_utils.py::is_palindrome` | ✅ PASS | 75% | 0 | 1 |

**Summary**: success rate **100%**, average coverage **91.7%**, average time **30.1s/task**.

### Synthetic Dataset Experiment (50 tasks, 3-baseline comparison, historical data snapshot)

> A data snapshot from one 50-task run (3-baseline comparison), used to demonstrate the multi-baseline methodology; not a performance commitment of the current version.

| Baseline Method | Success Rate (%) | Avg Coverage (%) | Avg Iteration Count | Avg Time (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **68.0** | **98.0** | 1.26 | 47.2 |
| Plain LLM | 68.0 | 95.2 | 1.10 | 348.3 |
| Single Agent | 22.0 | 71.1 | 0.62 | 17.3 |

**Key findings**:
- AITester's success rate is on par with Plain LLM, but coverage is higher (98.0% vs 95.2%)
- AITester is **7.4x faster** (47.2s vs 348.3s), demonstrating multi-agent collaboration efficiency
- The Single Agent baseline performs significantly worse (22.0%), validating the necessity of the multi-agent architecture
- Statistical tests show the AITester vs Single Agent difference is significant (p < 0.001, Cohen's d = 0.848)

See [experiments/results/synthetic_50_final/charts/](experiments/results/synthetic_50_final/charts/) for detailed results (kept locally, not committed; the repo's `experiments/results/` only tracks a placeholder note, historical artifacts are excluded via .gitignore).

### SWE-bench Lite Experiment (20 tasks)

This batch of experiments was affected by API rate limits, and results were not archived to the repository; subsequent re-run data is kept in a local private directory (not committed).

### Key Repair Records

- `_validate_parametrize` switched from regex to ast parsing, resolving the parameter misjudgment problem caused by nested lists
- Safety guards added to `_patch_applier_node` (non-empty, ≥10% length, contains a function definition)
- Secondary parametrize validation in the Generator, avoiding the LLM repeatedly generating the same wrong code


## FAQ

### Q: `ModuleNotFoundError` at runtime

**Cause**: the test file and the module are not in the same directory; Python cannot find the module under test.
**Fix**: make sure the `target_file` path is correct, or check the `module_name` configuration.

### Q: LLM returns non-JSON output

**Cause**: the model output does not match the expected format.
**Fix**: check the `LLM_N_*` settings in `.env.local` (model name, Base URL) and ensure the API Key is valid.

### Q: Coverage is always 0%

**Cause**: the coverage statistics file was not generated or has a wrong path.
**Fix**: check that `pytest-cov` is installed correctly and that the `--cov` argument is being passed.

### Q: Synthetic dataset success rate is low (< 10%)

**Cause**: the synthetic dataset's bug patterns are relatively complex; a single repair round may not cover all scenarios.
**Fix**:
1. Increase `MAX_ITERATIONS` (default 3, can be raised to 5)
2. Enable RAG augmentation: `ENABLE_RAG=true`
3. Use a more capable model (e.g. `gpt-4o` instead of `gpt-4o-mini`)

---

## Technical Documentation

- [Algorithm Design Document](docs/algorithm_design.md): formal description of the core algorithm
- [Failure Case Analysis](docs/failure_analysis.md): root-cause analysis of failure rates and an improvement roadmap (historical data snapshot)
- [Performance Tuning Guide](docs/performance_guide.md): parallel execution, RAG singleton, timeout configuration, profiling benchmarks
- [API Reference](docs/api_reference.md): module interface documentation
- [Usage Examples](docs/usage_examples.md): programming interfaces and CLI usage
- [Advanced Switches](QUICKSTART.md): structured tracing / multi-candidate patches / cost-aware routing (all off by default, enable as needed)
- [Historical Optimization Records](docs/history/optimization_plan.md): archived historical round optimization plans and reports (`docs/history/`, not currently maintained)

---

## Contribution Guide

Contributions are welcome! Read the [Contributing Guide](CONTRIBUTING.md) to learn how to participate in project development.

---

## Iteration records

### v0.1 (2026-09-18) — First official release

**Key features**:
- Four-agent architecture (Planner / Generator / Executor / Debugger) + hierarchical error repair (12 error categories)
- Logic-driven Chain-of-Thought (Logic-driven CoT): Planner explicitly analyzes input/output domains, pre/post conditions, and boundary cases
- RAG retrieval enhancement (ChromaDB, off by default; enable with `ENABLE_RAG=true`)
- Multi-baseline comparison and ablation (aitester / plain_llm / single_agent)
- Multi-candidate patch generation and verification (3.1, off by default)
- Structured observability: JSONL node-level tracing (4.1, off by default; enable with `AITESTER_TRACE_DIR`)
- Cost-aware routing + circuit-breaker cooldown + half-open probe (3.4 + 4.1 + 4.2)
- SWE-bench source export automation (2.1) + data contamination detection (token-level Jaccard)
- Cross-file repair (coordinator-proposer architecture, 3.5, off by default)
- Assertion augmentation (AST-based existing-assert extraction, 3.4, off by default)
- Dependency cache monitoring (venv hit-rate observability + `clean-venv-cache` CLI)
- Test smell detection / repair convergence curves / boundary case coverage / mutation score / execution feedback traces (1.2/1.3/3.2)
- Built-in mutation test generator (`experiments/mutation_testing.py`, AST-level 3 mutation types)
- Docker isolated execution (`EXECUTOR_USE_DOCKER`, 4.3)
- 1672 test cases / 94% coverage / Ruff all green (0.7 iteration; see iteration records below)

**Benchmarks** (synthetic dataset, 50 tasks, 3 baselines):
- AITester: 88.0% success rate, 97.8% avg. coverage, 45.33s avg. elapsed
- Plain LLM: 68.0% success rate, 98.0% avg. coverage, 16.6s avg. elapsed
- Single Agent: 4.0% success rate, 0.0% avg. coverage, 26.85s avg. elapsed

**Verification**: 1672 tests passed / 0 failed / Ruff all green / 94% coverage

## License

MIT License
