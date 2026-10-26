# AITester API Reference

Last updated: 2026-10-26 · 中文版: [api_reference.md](api_reference.md)

A quick reference for developers: modules, CLI, configuration, exceptions, and the LLM invocation
contract. For architecture see [algorithm_design.en.md](algorithm_design.en.md); for security
boundaries see [threat_model.en.md](threat_model.en.md).

## 1. Module Map

| Path | Responsibility | Main entry points |
|------|----------------|-------------------|
| `src/agents/` | Agents and error classification | `PlannerAgent`, `GeneratorAgent`, `ExecutorAgent`, `DebuggerAgent`, `FaultLocalizerAgent`, `ErrorClassifier` |
| `src/graph/` | Workflow orchestration, state machine, events, budget | `WorkflowGraph`, node functions, `EventBus`, `CostBudget` |
| `src/tools/` | Static analysis, patching and rollback, context building | `CodeAnalyzer`, `PatchApplier`, `CodeContext`, snapshot rollback |
| `src/specs/` | SpecIR intermediate representation and SMT witnesses | spec compilation, oracle generation |
| `src/api/` | Provider pool, circuit breaker, health checks | `APIManager`, `APIManagerConfig` |
| `src/datasets/` | Dataset loading and synthetic task generation | `DatasetLoader`, `SyntheticDataset` |
| `src/observability/` | Structured tracing and telemetry | `TraceSession`, `AgentTelemetry` |
| `src/measurement/` | Policy-agnostic metrics (MDO), recovery latency and retrieval quality | `compute_mdo`, `compute_recovery_latency`, `retrieval_relevance` |
| `src/budget/` | Token and cost accounting | `CostBudget`, `BudgetExceededError` |
| `src/reports/` | Defect report generation | `ErrorReport` |
| `src/cli/` | Command-line implementation | `src/cli/app.py` (`main.py` is a thin wrapper) |
| `src/utils/` | Exceptions, log redaction, shared helpers | `AITesterError` hierarchy, `mask_sensitive_info` |
| `config.py` | Environment and centralized configuration | `LLM_CONFIGS`, `MODEL_NAME` |

Workflow: Planner → Generator → Executor → Debugger → PatchApplier; the orchestration layer is
an ablatable container (ADR-0016), not a primary claim. The M1 metrics (detection / repair /
false_fix) are not in `src/measurement/`: they live in `experiments/_m1_metrics.py` and are
consumed by `experiments/run_benchmark.py` (they need gold materials).

## 2. CLI and Entry Points

```bash
python3 main.py --help
python3 main.py run examples/calculator.py --func divide
python3 main.py run examples/calculator.py --json
python3 main.py doctor
```

| Command | Purpose | Key options |
|---------|---------|-------------|
| `run` | Run test-generation and repair tasks | `--func` / `-f`, `--max-iterations`, `--coverage-threshold`, `--parallel` / `-p`, `--timeout` / `-t`, `--json`, `--verbose` / `-v`, `--dump-trace-on-failure` |
| `list-examples` | List example files under `examples/` | — |
| `check-dataset` | Validate dataset loading quality | `--subset` / `-s`, `--limit` / `-n` |
| `clean-venv-cache` | Clean the Executor venv dependency cache | `--max-age-days`, `--max-size-mb`, `--list-only` / `-l` |
| `doctor` | Zero-LLM self-check (environment + probe matrix) | `--json`, `--groups`, `--timeout`, `--strict` |

`doctor` exit codes: 0 pass; 1 failure (or warn/skip/matrix unavailable under `--strict`);
2 usage error (empty `--groups` or unknown group). The feature matrix needs
`scripts/tools/e2e_probe.py` from a source checkout; wheel installs report `unavailable`
(not counted as a failure) and environment checks still apply.

`doctor --json` emits the **same key set** on all three exits (success / usage error /
doctor-internal exception): `schema`, `generated_at`, `cwd`, `command`, `python`, `checks`,
`check_summary`, `matrix`, `conclusion`, `ok`, `strict`, `exit_code`, `error`. `error` is
`null` outside the exception path; on an internal exception `matrix.status` is `internal`
and uncollected aggregates (`checks`, `check_summary`, matrix summary/groups/lists) are
`null` (unknown ≠ all-zero), so consumers never branch on key existence.

CLI exit codes are uniform: 0 pass; 1 runtime failure (`run` had failed tasks — a coverage
shortfall is a per-task verdict and summary disclosure, never a task failure;
`check-dataset` hit a load error, loaded 0 tasks, could not honor the requested subset, or
its full quality report found loading problems, or `clean-venv-cache` failed to delete an
entry); 2 usage error (unknown dataset name,
negative `--limit`, `--subset` on a dataset without subsets or an unknown subset name,
`run --func` or `check-dataset --subset` explicitly blank (empty or whitespace-only),
negative `--max-age-days` / `--max-size-mb`, `run` with no valid target, or invalid numeric
options including `--coverage-threshold=nan`). A blank value is not "not provided": an
unset shell variable (`--func "$FUNC"`) arrives as `""`, and treating it as absent would
silently widen the scope to every function (LLM spend per function) or the full dataset;
omit the option to ask for "all".

`run`'s TARGET_FILES accept only regular files: an explicit directory / special file, or a
pattern that matches only directories, is a usage error (rc=2) and starts no task (it is no
longer disguised as a task failure); a file matched by both a glob and an explicit path is
deduplicated by absolute path and run once, so LLM calls are not repeated.

`run --dump-trace-on-failure` attempts to export the in-memory trace snapshot when a task fails
(including a crash): on success the result carries `trace_dump_path`; when no snapshot exists or
the write fails it carries `trace_dump_error` and discloses the reason on stderr. Export failure
never changes the task result, and in `--json` mode stdout still carries JSON only. Multiple or
concurrent dumps within one second each land in their own file: an existing name gets a numeric
suffix (`<ts>_2_failed_trace.jsonl`), so older snapshots are never overwritten.
`check-dataset` accepts only names returned by `get_available_datasets()` (case- and
hyphen-insensitive); the library function `load_dataset` still degrades unknown names to the
built-in examples, but that lenient contract does not apply to the diagnostic command —
otherwise "the dataset you asked about was never loaded" would be reported as a pass.
For `clean-venv-cache`, a `0` filter is the explicit "everything is stale" semantics
(equivalent to omitting both filters); only negative values are rejected.

`check-dataset --subset` takes effect only when the loader really supports subsets: the
`swe_bench` family maps the name to `swe_bench_<subset>_instances.jsonl`, and `ult` supports
`lite` / `full` (official subset files). Other datasets (built-in examples, QuixBugs,
BugsInPy, Defects4J, synthetic) have no subset concept — passing `--subset` is rejected as a
usage error (exit code 2) with the datasets that do support it listed. For `ult`, a missing
subset file, an unknown subset name, or a data source that is an explicit file is never
silently substituted: the command exits 1 and discloses why the requested subset was not
applied. Drop `--subset` to validate the fallback data instead.

Combining `clean-venv-cache --list-only` with filters previews the actual deletion set
(`[将删除]` / `[保留]`); the preview and the real cleanup share one predicate, so their
name lists cannot drift apart. A failed deletion (the directory still exists, e.g. due to
permissions) is reported per entry and exits with code 1 — failures are never counted as
removed and freed space is never overstated.

`check-dataset` prints "full quality check passed" only when the loader implements
`quality_report`; datasets such as the built-in examples, QuixBugs and ULT do not, and the
command explicitly discloses "quality_report not provided — skipping the full check". A
missing `tasks_missing_source` is disclosed the same way. Skipping a capability is not a
failure: the exit code stays 0. A non-empty quality report — real loading problems were
found — is listed and exits 1 (same code as a load error, distinguishable text:
`加载质量校验未通过：N 个任务存在加载问题`); a non-empty `tasks_missing_source` is
informational (source still to be exported) and does not change the exit code on its own.

`run` reports, per task, whether the tests pass, the coverage verdict (`coverage_ok`), the
coverage value and the iteration count. The batch summary (non-`--json`) aggregates coverage
attainment (met / missed / unmeasured); `--json` emits per-task structured output including
`coverage_ok`. A crashed task (e.g. a source file that is not valid UTF-8, or an exception
from the workflow) still produces a result line: under `--json` it carries exactly the same
key set as a successful result (unknown judgments such as `coverage` / `coverage_ok` /
`iterations` / `diagnosis` / `error_category` / observability stats are explicitly `null`,
plus the `error` description); without `--json` the reason goes to stderr while stdout keeps
the results table only (the iteration column shows `N/A` instead of a fabricated 0).
`--coverage-threshold` affects only the coverage verdict and that summary — it
does **not** change the exit code (the exit code reflects test pass/fail only). The detection /
repair / false_fix metrics belong to the benchmark surface and are computed by
`experiments/_m1_metrics.py` and consumed by `experiments/run_benchmark.py` (they need gold
materials); the CLI neither computes nor prints them. When installed as a package, the
`aitester` console entry point is also available (see `pyproject.toml`).

## 3. Configuration

Sources: `.env.local` (LLM credentials, gitignored), `.env.example` (tracked template), and
`config.local.example` (tracked LLM template). `LLM_N_*` supports multiple providers (N from 1).

| Option | Type | Default | Meaning |
|--------|------|---------|---------|
| `LLM_N_API_KEY` / `LLM_N_BASE_URL` / `LLM_N_MODEL_NAME` | str | — | Nth OpenAI-compatible endpoint |
| `LLM_N_COST_WEIGHT` | float | 0.0 | Cost-aware routing weight (0.0 = no information) |
| `MAX_ITERATIONS` | int | 3 | Maximum repair iterations |
| `COVERAGE_THRESHOLD` | float | 80.0 | Coverage threshold (%) |
| `EXECUTION_TIMEOUT` | int | 30 | pytest execution timeout (seconds) |
| `LLM_TIMEOUT` / `LLM_RETRY_WAIT` | int | 60 / 30 | LLM timeout and retry wait (seconds) |
| `TEMPERATURE` | float | 0.2 | Sampling temperature; deterministic runs force 0.0 |
| `EXECUTOR_USE_VENV` | bool | true | venv sandbox isolation (true by default since R10; false is debug-only) |
| `EXECUTOR_AUTO_INSTALL_DEPS` | bool | false | Install missing dependencies inside the venv |
| `EXECUTOR_USE_DOCKER` | bool | false | Docker isolation; returns `docker_unavailable` when unavailable, no silent fallback |
| `ENABLE_RAG` | bool | false | Enable RAG case retrieval |
| `ENABLE_MUTATION_SCORING` | bool | false | Enable mutation scoring |
| `LLM_JSON_MODE` | str | "on" | JSON Output contract (`json_object`); `off` is the historical byte-identical caliber |
| `LLM_THINKING_MODE` | str | "disabled" | DeepSeek reasoning chains off by default (cost protection) |
| `FAULT_LOCALIZER_ENABLE` | bool | true | RGFL-style LLM reasoning localization; false falls back to spectral only |
| `AITESTER_PROFILE` | str | unset | Preset: `safe` / `scientific` / `logic` / `fast` |
| `AITESTER_TRACE_DIR` | str | unset | Structured JSONL tracing; when unset nothing is written (in-memory snapshot buffer only); an uncreatable directory warns and degrades to memory-only without blocking tasks |
| `TRACE_MEMORY_BUFFER_ENABLE` | bool | true | In-process snapshot ring buffer behind `--dump-trace-on-failure`; false restores the zero-overhead mode |
| `COST_BUDGET_ENABLE` | bool | false | Per-task token / USD hard budget |

The authoritative full list is `config.py` plus `docs/env_budget.yaml`; batch provenance records
an `env_snapshot` for reproducibility audits.

## 4. Exceptions and Error Classification

```python
from src.utils.exceptions import AITesterError, APIError, ParsingError

try:
    ...
except APIError as exc:
    ...
```

| Exception | Parent | Trigger |
|-----------|--------|---------|
| `ConfigurationError` | `AITesterError` | Missing or invalid configuration |
| `ExecutionError` | `AITesterError` | Test execution failed |
| `TimeoutError` | `ExecutionError` | Test execution timed out (same name as the builtin, existing API) |
| `ParsingError` | `AITesterError` | LLM output parsing failed |
| `JSONParseError` | `ParsingError` | JSON-contract response is unparseable |
| `SyntaxParseError` | `ParsingError` | Generated code has a syntax error |
| `APIError` | `AITesterError` | Provider call failed |
| `RateLimitError` | `APIError` | 429 rate limiting |
| `AuthenticationError` | `APIError` | 401/403 authentication failure |
| `BudgetExceededError` | `RuntimeError` | Per-task budget exceeded |
| `SandboxUnavailable` | `RuntimeError` | Kernel sandbox unavailable (fail-closed) |

`ErrorClassifier` yields 18 `ErrorCategory` values: `llm_format_error`, `llm_empty_response`,
`llm_json_parse_failed`, `import_error`, `syntax`, `type_error`, `index_error`, `assertion`,
`logic_error`, `runtime`, `timeout`, `unknown`, `patch_validation_failed`,
`rag_retrieval_empty`, `execution_trace_missing`, `multi_candidate_all_rejected`,
`patch_syntax_invalid`, `test_regenerated_pass_unverified`. Classification is rule-based, with
unknown shapes falling back to `unknown` and conservative handling.

Structured execution diagnostics: `error_info.type` may be `execution_dependency_missing`
(missing pytest and friends; install `aitester[execution]`), `docker_unavailable`, or
`docker_timeout`.

## 5. LLM Invocation Contract

- **Provider**: OpenAI-compatible endpoints; credentials only via `.env.local`; the only built-in
  provider is the official DeepSeek endpoint.
- **JSON contract**: seven call sites (Planner plan, Debugger patch / strict retry / critic /
  breaking tests / defect classification, FaultLocalizer localization) bind
  `response_format={"type": "json_object"}` when `LLM_JSON_MODE=on`; `off` replays historical
  batches byte for byte.
- **Thinking mode**: `LLM_THINKING_MODE=disabled` by default (V4 reasoning chains are billed as
  output); `LLM_REASONING_EFFORT` and `LLM_MAX_OUTPUT_TOKENS` are optional overrides.
- **Recoverable failures**: `finish_reason ∈ {length, insufficient_system_resource}` is retried;
  Python numeric expressions in JSON value positions are repaired by a bounded parse layer
  (no `eval`).
- **Caching**: the LLM file cache lives in the user cache directory (`~/.cache/aitester/llm`);
  cache keys include provider / model / temperature / JSON mode identity fields; the seed is used
  only for task sampling and is never sent to the API.
- **Routing and circuit breaking**: `APIManager` provides health checks, circuit breaking, and
  cost-aware routing; failures degrade conservatively and never fake success. Credentials are
  scrubbed from the subprocess environment by `credential_scrub.scrub_os_environ` on all three
  execution paths.
