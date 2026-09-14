> **Language**: [中文版](CHANGELOG.md) | English (this document)

# Changelog

All notable changes are recorded in this file. The format follows [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/).

## [0.9.16] - 2026-09-15 Deep refactoring round (single construction-point convergence + statistical-test convergence + doc alignment)

### AITesterState initialization double-write convergence (tech-debt digestion)
- Added a `create_initial_state()` factory function to `src/graph/state.py` (with every TypedDict field explicitly assigned);
  the hand-written initialization dictionaries in the CLI (`cli/app.py`) and the benchmark (`experiments/run_benchmark.py`) have been removed
- The single construction point eliminates double-write drift when new fields are added (tech debt recorded by the 0.9.14 batch)
- Added `tests/test_state.py` (8 cases): key-set guard / module_name inference / mutable-container isolation / optional-parameter injection

### Convergence of the third residual copy of the statistical significance (tech-debt digestion)
- The statistical test in `experiments/visualize_results.py` now reuses the paired primitives from
  `experiments/statistical_analysis.py` (`_pair_by_task` / `cohens_d` / `interpret_p` / `interpret_d`);
  scipy is kept only for the native `ttest_rel` + `mannwhitneyu` calls (chart-specific metrics)
- Added NaN/Inf guards: for constant groups (all 1s vs. all 0s) the paired t-test gives t=inf → a NaN placeholder,
  consistent with the guard convention in `src/experiments/analysis.py` (avoiding `round(float(inf))` producing a non-standard `Infinity` token)
- Deprecated the old "fill every task_id with 0.0" convention; now tasks are paired by task_id and missing tasks are not counted in the sample
- Added `tests/test_viz_significance.py` (6 cases): task_id pairing convention / NaN placeholder / primitive-reference lock

### Code-coverage test backfill
- `tests/test_code_context.py` gained 9 cases (second-layer trimming / last-resort path / private-helper boundaries /
  skipping comment lines / short function bodies / non-prebuilt segments / fallback when the focus is missing); module coverage went from 89% to 98%

### Documentation sync (aligned with the 0.9.15 maintainability deep-dive split)
- The README project structure tree was completed with 5 split-off artifacts: `src/graph/{tracing,rag,nodes}.py`,
  `src/api/api_health.py`, `src/agents/llm_client.py`
- The README's location note for `get_rag_retriever()` was corrected from `workflow.py` to `rag.py` (re-exported via workflow)
- 13 inline numbers in the README test-status table were synced (test_cli_app / test_code_context / test_config /
  test_config_manager / test_error_classifier / test_executor / test_multi_candidate /
  test_workflow_extended, etc.), and two new rows were added for `test_state.py` / `test_viz_significance.py`
- README total test count 1270 → 1291, file count 50 → 52, coverage 92% → 94%
- `docs/api_reference.md`: completed the default values and optional annotations of `generate()` / `debug()` parameters
  (`module_name: str = ""`, `rag_references: list | None = None`, `focus_function/target_module: str | None = None`);
  the workflow node implementation location now points to `nodes.py`; APIManagerConfig field ownership now points to `api_health.py`

### Verification
- Full suite **1291 passed / 0 failed** (+21 new), ruff check + format all green,
  total src coverage **94%** (+1%)

## [0.9.15] - 2026-09-15 Code maintainability deep-dive round (type annotations + cyclomatic complexity + Ruff rule strengthening)

### Ruff rule-set strengthening
- Added `SIM` (flake8-simplify), `PERF` (perflint),
  `RET` (flake8-return), `RUF` (ruff's own rules) to the select list in `pyproject.toml`
- RUF ignores RUF001/002/003 (false positives on full-width punctuation inside Chinese comments; 5012 hits, none of which are real issues)
- Fixed 63 hits: SIM code simplifications, PERF list comprehensions/values(), RET return-statement improvements,
  RUF012 mutable class attributes now annotated with ClassVar, RUF005 iterable unpacking, RUF021/022, etc.

### Type-annotation completion
- Completed annotations for 5 functions that had none at all (_build_error_info, _check_parametrize_decorator,
  _validate_case_tuple, _retry_with_exponential_backoff, mysql_client.cursor)
- Tightened 12 bare list/dict/tuple/set annotations into generics with element types
- All 337 functions in the project now have complete parameter + return-value annotations (zero gaps after excluding self/cls)

### Cyclomatic complexity refactoring (7 of the 9 over-threshold functions refactored)
- get_fix_strategy: a 156-line if chain → a mapping table + 2 context helper functions (14→3)
- run: split into three helper functions for parameter validation / glob expansion / summary output (22→ below 10)
- check_dataset: split per-task printing / quality report / missing source code (13→4)
- generate: query construction split into _build_query (13→7)
- _execute_sandboxed: dependency-detection install split into _prepare_dependencies (11→8)
- clear_venv_cache: directory size statistics split into _dir_size_mb + a simplified filtering check (12→9)
- analyze_cross_file_deps: import collection split into _collect_imported_symbols (15→ below 10)
- _analyze_root_cause / _generate_fix_suggestion: if chain → mapping table + helper functions (17→4 / 16→5)
- Deliberately kept check_health (11) and extract_focused_code (13): their complexity comes from reasonable
  exception-handling branches and a coherent "degrade layer by layer within the budget" trimming logic; forcing a split would hurt readability

## [0.9.14] - 2026-09-15 Project-wide convergence round (config centralization + dead-code cleanup + default-off feature fixes)

### Config centralization convergence (dual-source drift + env bypass)
- Removed the three "dead constants" CROSS_FILE_ENABLE / CROSS_FILE_MAX_MODULES /
  ASSERTION_AUGMENT_ENABLE from config.py that had no consumers (each feature module reads the env at its own call time;
  dual-source definitions drift easily); pointer comments kept to state ownership
- SWE_BENCH_ENRICHMENT in dataset_loader.py was converged from a raw `os.environ` read to a
  config constant (a new "Dataset configuration" subsection added); the corresponding entry was added to .env.example; test_dataset_validation
  now locks the new convention with monkeypatch.setattr
- MULTI_CANDIDATE_EXEC_VALIDATE in nodes.py was converged from a raw `os.getenv` read to the
  newly added multi_candidate_exec_validate() helper in multi_candidate.py

### Defect fixes (3 places)
- 🔴 The hardcoded stdlib list in executor.py mistakenly listed the third-party diskcache and was missing asyncio/importlib;
  the 80-item frozenset was removed and dependency.is_standard_library is now reused
  (the authoritative `sys.stdlib_module_names` list), and _extract_imports explicitly skips pytest
- 🔴 The cross-file fallback path in _patch_applier_node treated the "file-mapping dict" returned by
  cross_file_fallback_single_file as a "code string" and assigned it to new_code; len(dict) is always 1, so the fallback patch
  was forever stuck at the "too short" safety check and could never be written to disk; fixed to fetch the entry_module code from the mapping
- _set_thread_api was dropping api["model"]; during multi-model polling the model always fell back to the first config; the
  `_thread_local.model_name` assignment was added

### Dead-code cleanup (4 places)
- Removed templates.EXECUTOR_SYSTEM_PROMPT (a zero-reference placeholder constant)
- Removed patch_applier.safe_apply_multi_function_patch (zero references)
- Removed run_benchmark._call_llm_with_fallback and _is_zai_url (both dead code and a stale copy of the
  failover logic in base_agent._call_llm)
- Removed the performance_profile.benchmark decorator (never used) + the cross_file dead function topo_key

### Concurrency and DRY
- TestCaseRetriever (a cross-thread shared singleton): add_case/add_repair were factored into a private _upsert as the single
  write point + threading.Lock serializing "cleanup + capacity check + upsert", eliminating the
  check-then-act race under --parallel; _cleanup now defends against meta=None with (meta or {})
- The "fetch field → refine" wiring of refine_failure_category was converged into the newly added
  refine_final_error_category(final_state) in error_classifier, reused in both cli and run_benchmark
- The docstring and comments of cross_file.apply_multi_file_patch now truthfully describe "currently lexicographic order",
  and the misleading topological-order promise was removed

### Tests
- Full suite **1270 passed / 0 failed** (net +23 since 1247); ruff check / format all green
- Coverage improved: total src coverage 91%→92%; graph/nodes.py 76%→95%,
  config/config_manager.py 87%→95% (23 cases covering new default-off feature branches, cross-file fallback regressions,
  empty-field validation, write-disk exceptions, env switches, etc.)

## [0.9.12] - 2026-09-12 Code maintainability split batch

### Code maintainability: split three oversized files by responsibility
- Background: 9 files exceeded 600 lines; among them workflow.py (1089) / api_manager.py (927) /
  base_agent.py (648) had mixed responsibilities, and subsequent extension and maintenance were costly
- base_agent.py (648→308): 11 LLM client utility functions (client cache / exponential-backoff retry /
  log redaction / token statistics / zai compatibility detection / config fetching / file-cache switch) moved to
  llm_client.py, keeping only the BaseAgent base class and re-exports
- api_manager.py (927→721): RotationStrategy / APIHealth / APIManagerConfig /
  _COST_ALERT_THRESHOLD moved to api_health.py, separating pure data models from routing logic; also fixed
  the duplicate definition of the enable_half_open_probe and half_open_probe_penalty_cap_seconds fields in APIManagerConfig
  (a merge leftover from the 4.2 batch; the values were identical, no side effect)
- workflow.py (1089→292): node functions moved to nodes.py, the RAG retriever singleton to rag.py,
  structured tracing to tracing.py; graph construction / conditional routing / public API retained, forming an acyclic dependency layering;
  re-exports keep the historical `from src.graph.workflow import ...` paths unchanged
- Test patch paths were precisely redirected to the new modules according to symbol ownership; full suite 1247 passed with zero regressions

### Performance analysis (scripts/performance_profile.py)
- Measured with cProfile / tracemalloc and confirmed: the runtime logic is efficient with no CPU hotspots (ErrorClassifier
  about 10μs per call, CodeAnalyzer normal AST walks), and no memory leaks
- The real bottleneck is third-party import overhead (chromadb 0.6s / pandas+datasets 0.53s /
  openai 0.9s), an inherent cost of the core dependencies; no low-hanging-fruit optimization points
- Corrected the template-style conclusions of the profile script; see docs/performance_profile_report.md for details

### Dependency audit
- Rerunning pip-audit found nltk==3.10.3 hits CVE-2026-81726 (path traversal, model-loading API),
  but nltk is an indirect dependency of the vulnerability-scanning tool safety, has zero references in the project code, and CI scans direct
  dependencies only with `--no-deps` — zero runtime impact, and PyPI has no fixed version yet; recorded for reference

## [0.9.12] - 2026-09-12 Full review batch

### Full project review (security / code quality / tests / dependencies)
- Security: no sensitive files leaked anywhere in the git history — `.env` / `.env.local` / `.env.local.bak` / `.local/private.md` never appeared in any commit; only the two placeholder templates `.env.example` / `.env.local.template` show up in historical paths; no hardcoded keys in the whole codebase (a regex scan only hits sample tokens of third-party libraries under `.venv`); the local real keys (6 sk- prefixed entries in `.env` + `.env.local` combined) all live in gitignored files, are untracked, and are never uploaded
- Code quality: `ruff check` / `ruff format --check` all green (ruff 0.16.3, 139 files); no real TODO/FIXME leftovers (all 7 hits are example text inside comments); bare `pass` statements are all reasonable fault-tolerance/placeholder uses (click group callbacks, fallback to defaults after a swallowed `except`, and `raise` after cleaning up temporary files)
- Tests: full `pytest tests/` **1247 passed / 0 failed** (30.5s, Python 3.14.6); only 2 harmless third-party warnings (chromadb `asyncio.iscoroutinefunction` deprecation + a scipy precision-loss RuntimeWarning)
- Dependencies: `scripts/check_lock_sync.py` passes (19 items in requirements.txt ↔ 130 items in requirements.lock); rerunning `pip-audit` confirmed chromadb==1.5.9 hits 5 known vulnerabilities (PYSEC-2026-311 ×2 + PYSEC-2026-3813/3814/3815); PyPI has no fixed version yet, and the CI security job explicitly exempts them (consistent with the comment in ci.yml)

### Documentation fixes (R-01 / R-02)
- R-01 The README "Configuration description" table was broken: the `Advanced switches` heading had been inserted in the middle of the "Configuration description" table, leaving 20 configuration items starting from `EXECUTION_TIMEOUT` without a header and breaking the Markdown rendering; now the 20 items have been moved back up and merged into the "Configuration description" table, and `Advanced switches` stands as an independent section
- R-02 The `.env.local.template` onboarding was misleading: the header originally said "copy this file to .env.local", but that template actually carries `{PROVIDER}_API_KEY` intermediate variables (read by `generate_batch_config.py`), while `config.py` at runtime only reads the numbered `LLM_N_*` format — following it would load no LLM configuration at all; now `src/config/config_generator.py::generate_env_template()` generates the header and the committed `.env.local.template`, clearly stating the "intermediate-variable template" role and pointing to `config.local.example` (placeholder content unchanged; existing test assertions are not affected)

## [0.9.14] - 2026-09-15 Test-suite optional-dependency degradation batch: O-01a

### Test-suite false ERROR when optional dependencies are not installed (tests/test_rag_retriever.py + tests/test_experiments_scripts.py)
- Background: `chromadb` / `matplotlib` are heavyweight optional dependencies; running `pytest tests/` in a slim environment (without the full `pip install -r requirements.txt`) produces 32+5=37 `ImportError` ERRORs (not skips), obscuring the real test conclusion
- Added a module-level `pytestmark = pytest.mark.skipif(not _chroma_available(), reason="chromadb not installed")` to `tests/test_rag_retriever.py`, consistent with the skipif convention in the existing `test_rag_metrics.py` (the two case sets of the same optional dependency behave uniformly in a slim environment)
- In `tests/test_experiments_scripts.py`, the two fixture groups `TestVisualizeLoadLatestResult` / `TestVisualizeSummaryMdTable` got `pytest.importorskip("matplotlib", ...)` before the lazy `from experiments import visualize_results`: when matplotlib is not installed, they skip gracefully instead of erroring during setup
- Full suite: **1208 passed / 39 skipped / 0 failed** (slim environment missing chromadb + matplotlib); restoring 1247 passed after installing all dependencies; `ruff check` all green

## [0.9.14] - 2026-09-15 CLI output-layer test backfill batch: O-01

### O-01 CLI output-layer regression backfill (tests/test_cli_output.py, new)
- Background: `src/cli/output.py` (100 lines, the CLI output layer) had 58% coverage, one of the lowest in src/ (`app.py` at 70%); the two branches of `colorize` under TTY, the icon prefixes of `success_msg`/`error_msg`/`warning_msg`/`info_msg` and their stdout/stderr routing, and the empty-list / missing-key fallback / `coverage=0.0` boundary of `print_rich_table` all had no regression cases
- Added `tests/test_cli_output.py` (10 cases, 3 groups): `TestColorize` (non-TTY pass-through / TTY wrapping with ANSI + RESET), `TestMessageHelpers` (✓/✗/⚠/ℹ prefixes + error/warning go to stderr, success/info go to stdout), `TestPrintRichTable` (no N/A produced for an empty list, missing-key fallbacks `func=all` and `coverage=N/A`, **0.0 as a legal coverage value is not misjudged as N/A by falsy logic**, status icons and basename rendering)
- Fixed and locked one semantic detail: the `is not None` check in `print_rich_table` (0.0 coverage shows `0.0%` instead of `N/A`); previously no test guarded it, and a mistaken change to a truthy check would silently degrade it
- Coverage: `src/cli/output.py` 58% → **92%** (the 4 misses are rich table rendering details)
- Full suite: **1247 passed / 0 failed** (net +10 since 1237); `ruff check` / `ruff format --check` all green

### Documentation alignment (O-02)
- README test-status table: total cases 1237→1247, test files 48→49, 5 case-count drifts in the main table corrected (core_modules 19→29 / dataset_loader_extended 59→73 / executor_sandbox 7→14 / experiments_scripts 30→36 / generator 27→43) + a test_cli_output row added + core-module coverage data refreshed (workflow 90%→83%, and 7 more)

## [0.9.13] - 2026-09-14 Circuit breaker half-open probe batch: 4.2

### 4.2 Circuit breaker half-open probe (src/api/api_manager.py)
- After the 4.1 circuit breaker cooldown expires, the node immediately resumes full routing; dead providers get hit over and over. This batch completes the classic three states (closed / open / half-open): after the cooldown expires the node first enters a "half-open" window that carries a single probe request; only a successful probe closes the circuit breaker and restores full routing; a failure reopens a half-length cooldown period
- Added `in_circuit_half_open` (cooldown expired, probe not yet completed) and `_probe_circuit_half_open()` (success closes / failure reopens) to `APIHealth`; the half-open penalty duration = `min(cooldown/2, half_open_probe_penalty_cap_seconds)`, default cap 30s, preventing a fully downed provider from shrinking its cooldown period more and more
- `get_healthy_nodes()` / `_build_node_list()` include half-open-window nodes as routing candidates (only when the switch is on) and carry the probe request; the success / exception branches of `call()` and `check_health()` uniformly consume the probe result
- Added a `circuit_state` (closed / open / half_open) field to `get_status()`, so monitoring and experimental analysis can observe the three states directly
- Added `enable_half_open_probe` (default True) and `half_open_probe_penalty_cap_seconds` (default 30.0) to `APIManagerConfig`; setting it to False reverts to the old 4.1 behavior, convenient for comparative experiments
- Documentation sync: version history + the 4.1 related notes updated in `docs/api_reference.md`
- Tests: `tests/test_api_manager_extended.py` gained `TestHalfOpenProbe` with 12 cases (window properties / successful closure / failure reopen / penalty cap / no-op boundaries / switch-off fallback / consumption on both call and check_health paths / three states in get_status)

### Format normalization (docs/design/cross_file_repair.md)
- A python code block in the 3.5 design document (dataclass comment alignment) triggered ruff format gate drift; uniformly normalized, no logic changes

### Full verification
- `pytest tests/` **1237 passed / 0 failed** (net +12 since the previous batch's 1225)
- `ruff check` / `ruff format --check` all green

## [0.9.13] - 2026-09-14 Improvement list G-01~G-04 + 3.4 + 3.5 implementation batch

### 1.2 Test smell detection (analyze_results.py)
- Added a `_test_smell_detection()` pure function to `experiments/analyze_results.py`: it AST-scans `details[].generated_test` to detect 4 kinds of LLM-generated smells — **Assertion Roulette** (no effective assertion but non-trivial), **Magic Number** (≥3 unnamed integer literals with no constant assignment), **assertion weakening** (assertion line count decreased compared to the previous round), and **trivial tests** (function body is only pass / an always-true assertion); when the old JSON has no `generated_test`, `available=False` and the section is skipped during rendering, zero regression surface
- The Markdown renders a "Test smell detection (1.2)" section: outputs the smell counts per baseline + a list of tasks with smells
- Tests: `tests/test_experiments_scripts.py` +3 cases (trivial+roulette / magic number / skipped when no generated_test)

### 1.3 Repair convergence curve (analyze_results.py)
- Added a `_repair_convergence_curve()` pure function: statistics per iteration round 0/1/2/3+ of "tasks reached / cumulative passes / cumulative pass rate / cumulative average latency", showing how the pass rate changes as iterations increase; an empty baseline returns `rounds={}` without dividing by zero
- The Markdown renders a "Repair convergence curve (1.3)" section
- Tests: `tests/test_experiments_scripts.py` +3 cases (monotonic cumulative pass rate / empty details / rendering regression)

### 4.4 Dependency cache monitoring (src/tools/dependency.py)
- Added `get_venv_cache_stats()` (hit-rate statistics: in-process cumulative hit/create + cross-process aggregation from the on-disk JSON, `hit_rate = hits/(hits+creates)`), `list_venv_cache()` (lists all venvs in the cache directory: name/path/size_mb/created_at), `clear_venv_cache(max_age_days, max_size_mb)` (cleans up by age/size filters; clears everything when both are None)
- The reuse/create paths of `create_venv` record hit/create events (the hit rate becomes observable)
- Pitfall fixed: `threading.Lock` is not reentrant, so nested self-locking in `_record_venv_cache_event` and `_persist_cache_stats` would hang the process — changed to a single locking boundary (`_persist` assumes the caller already holds the lock)
- Tests: `tests/test_dependency.py` +8 cases (43 total)

### 5.3 Failure root-cause classification + case knowledge base (analyze_failures.py)
- Added `root_cause_classification()`: the three major root causes (`llm_capability` / `dependency` / `framework`) are classified by a conservative heuristic on `error_category` + `diagnosis` keywords, with at most 3 representative cases per category; when no rule hits, it falls back to `llm_capability`
- Added `failure_knowledge_base()`: selects cases by `error_category` diversity first (top 2 per category); structured cases include `task_id / root_cause / reproducible_steps / suggested_fix`; default output is `experiments/results/failure_knowledge_base.json`
- Added "5. Failure root-cause classification" + "6. Failure case knowledge base" sections to `generate_report`
- Added a `--knowledge-base/-k` CLI option (default path `<results-dir>/failure_knowledge_base.json`)
- Tests: `tests/test_analyze_failures.py` (new, 13 cases)

### 3.4 Assertion augmentation strategy (src/agents/generator.py, off by default)
- Added `_extract_existing_assertions()`: extracts existing `assert` statements in the code under test via AST (deduplicated, at most 10); returns empty conservatively on syntax errors
- Added `_assertion_augment_enabled()`: enabled by the environment variable `ASSERTION_AUGMENT_ENABLE=true` (default false, preserving the historical convention)
- `generate()` appends an "assertion augmentation" paragraph after RAG injection (only when the switch is on and existing asserts exist), guiding the LLM to avoid assertion weakening / always-true assertions / unnamed magic numbers
- Tests: `tests/test_generator.py` +6 cases (27 total)

### 3.5 Cross-file repair capability (src/tools/cross_file.py + workflow wiring, off by default)
- Added `src/tools/cross_file.py`: `CrossFileDependency` / `CrossFileRepairPlan` data structures + `analyze_cross_file_deps` (AST cross-file import dependency analysis) + `build_cross_file_repair_plan` (coordinator-proposer: one proposer per module, reusing the existing DebuggerAgent call path) + `apply_multi_file_patch` (multi-file patch application with whole rollback on failure) + `cross_file_fallback_single_file` (single-file fallback)
- `src/graph/workflow.py`: when `CROSS_FILE_ENABLE=true`, the path becomes `executor → cross_file_analyzer → debugger`; `_patch_applier_node` gains a cross-file branch (multi-file application + fallback to single-file on failure)
- `src/graph/state.py`: added the two fields `cross_file_deps` / `cross_file_plan`
- `config.py`: added `CROSS_FILE_ENABLE` (default false) + `CROSS_FILE_MAX_MODULES` (default 5) + `ASSERTION_AUGMENT_ENABLE` (default false)
- Design document `docs/design/cross_file_repair.md` (option comparison: coordinator-proposer vs. pure end-to-end LLM; data structures; test strategy; rollback plan; phase-2 extensions)
- Tests: `tests/test_cross_file.py` (new, 27 cases) + `tests/test_workflow.py` +2 cases (workflow cross-file enabled/disabled paths)

### Documentation and decision log
- Added an "Improvement list status audit" section to `docs/history/optimization_plan.md` (a three-way classification: implemented / real gaps / research items)
- Design document `docs/design/cross_file_repair.md` (3.5)
- Project-wide documentation sync (README / QUICKSTART / api_reference / usage_examples / .env.example with 3.4/3.5/4.4 switch notes added)

### Full verification
- `pytest tests/` **1225 passed / 0 failed** (net +62 since the 1.1/1.2 first-batch baseline of 1163)
- `ruff check` / `ruff format --check` all green

## [0.9.13] - 2026-09-14 First batch of multi-dimensional evaluation metrics: 1.1/1.2 analysis-layer enhancements

### Experiments (1.1 multi-dimensional evaluation + 1.2 repair convergence efficiency)
- `experiments/analyze_results.py` gained two regressable aggregation sections: `repair_convergence_metrics` (first-attempt success rate, iteration min/avg/median/max for successful/failed tasks, average latency of successful tasks) and `quality_proxy_metrics` (coverage/latency proxies, an optional assert-line-count proxy of `generated_test`, Top N failure categories)
- `build_analysis` and `render_markdown` render two Markdown sections in sync: "Repair convergence efficiency (1.2)" and "Multi-dimensional quality proxies (1.1, conservatively recomputable)"; when an old JSON has no `generated_test` / no details, it automatically degrades to N/A or skips the section without crashing
- Tests: `tests/test_experiments_scripts.py` +5 cases (empty/non-empty convergence metrics, quality proxies with existing fields only, assertion proxy with `generated_test`, Markdown rendering regression)
- Documentation sync: `README.md` (test status / recent changes / test coverage table / project structure notes / 5.5 results analysis section), `QUICKSTART.md` (advanced-switch results analysis notes), `docs/api_reference.md` (version history), `docs/usage_examples.md` (example 13.5 structured analysis + metric-convention table), `docs/performance_guide.md` (derived-metric monitoring notes), `docs/failure_analysis.md` (status notes)

Full related regressions: `tests/test_experiments_scripts.py` + `tests/test_run_benchmark.py` 28 passed; `ruff check` / `ruff format --check` all green; full `pytest tests/` **1163 passed / 0 failed**

## [0.9.13] - 2026-09-14 Project-wide documentation sync batch F-01~F-10

### Documentation
- **README project structure sync**: the structure tree was completed at 4 missing spots (`src/observability/`, `src/graph/token_usage.py`, code_context/dependency/multi_candidate under `src/tools/`, run_large_scale/run_statistical_test/statistical_analysis/analyze_failures under experiments/); the phrasing "for the paper discussion section" changed to "for technical review"; 5.3 cost-aware routing gained a configurable 3.2 threshold note; added a new 5.7 SWE-bench source export automation subsection
- **docs/redaction_audit.md C item cache path correction**: the actual LLM file cache path is `src/cache/` (`_LLM_CACHE_DIR_DEFAULT` resolves relative to `src/agents/`, overridable via `AITESTER_LLM_CACHE_DIR`, already in `.gitignore`); it was previously misrecorded as `~/.cache/aitester/llm_cache/` (the argument "it is naturally outside the repo path under HOME" no longer holds); the "known acceptable risk" conclusion is unchanged (local trusted domain; redaction and cache exact-hit matching are mutually exclusive)
- **docs/performance_guide.md**: `rm -rf .chroma_cache/` pointed to a non-existent directory (chromadb 1.x persists under `rag_data/`), changed to `rm -rf rag_data/` + a note on the `RAG_PERSIST_PATH` override; timestamp 2026-08-16→2026-09-14
- **experiments/analyze_failures.py**: the phrasing "for the paper discussion" changed to "for technical review"; the `--output` default changed from `docs/paper/failure_analysis.md` (that directory no longer exists) to `experiments/results/failure_analysis.md` (no test references this script, zero regression surface)
- **docs/api_reference.md version history**: added an Unreleased (batch ②) row at the top (the 0.9.13 row kept as history)
- **docs/usage_examples.md**: the lowercase `contributing.md` reference changed to `../CONTRIBUTING.md`; timestamp 2026-09-11→2026-09-14
- **.env.example 3.4 section**: added a configurable note for the 3.2 `cost_alert_threshold`; the `LLM_N_COST_WEIGHT` numeric convention was aligned with config.py's actual parsing (0.1~1000; unset defaults to 0.0 = no information, APIManager falls back to 1.0; previously miswritten as 1.0 = baseline)

Full suite **1158 passed / 0 failed**; `ruff check` / `ruff format --check` all green; pure documentation + script docstring changes, zero functional changes

## [0.9.13] - 2026-09-14 State refinement + configurable thresholds + boundary test backfill + source export + redaction audit batch

### Error classification (1.1 state refinement)
- **ErrorCategory gained 2 state-refinement classes**: `PATCH_VALIDATION_FAILED` (a patch rejected by the PatchApplier safety guards, with patch_applied=False in repair_history) and `RAG_RETRIEVAL_EMPTY` (RAG is enabled but all in-task retrieval results==0, flagging RAG-failure scenarios). 10 text classes + 2 state classes = 12 classes. Added the pure function `refine_failure_category()` (refines signals from repair_history/rag_stats at task teardown; a rejected patch takes priority over empty RAG; successful tasks are returned as-is); the two if/elif chains in `get_fix_strategy()` and `reports/generator.py` gained 2 branches in sync; `run_benchmark._build_task_result` and the CLI `_run_single_task` call refine at teardown of failed tasks (benchmark and CLI conventions consistent)
- Tests: `tests/test_error_classifier.py` +9 cases (3 enum values + 6 refine decision-matrix), 81 total

### Cost routing (3.2 configurable threshold)
- Added `cost_alert_threshold` to `APIManagerConfig` (default follows the module constant 2.0); the alert check in `_try_call_node` now uses the configured value — when a threshold that is too low produces too many false alarms, raise it (e.g. 3.0/5.0 alerts only on truly expensive providers); when cost sensitivity is high, lower it; no code changes needed. The alert message prints the configured threshold (to avoid misleading tuning)
- Tests: `tests/test_cost_aware_routing.py` +4 cases (default-value regression ×1 + raising suppresses moderately expensive ×1 + lowering alerts on cheaper nodes ×1 + message contains the configured threshold ×1)

### Test strengthening (1.4 / 1.5)
- **Circuit cooldown boundary (1.5)**: added `TestCircuitCooldownBoundaries` (3 cases) to `tests/test_api_manager.py` — after the cooldown expires, the node automatically returns to the routing pool (no mark_success needed); when multiple nodes are in cooldown simultaneously, routing degrades as a whole (select_node returns None + call fails fast + get_status exposes the remaining cooldown seconds); during the cooldown, new requests do not hit the cooling-down node (traffic lands on healthy nodes, the cooling-down node gets zero calls)
- **CLI argument exceptions and concurrent behavior (1.4)**: added 3 groups of 8 cases to `tests/test_cli_app.py` — `TestRunParallelTimeoutAndInterrupt` (--timeout propagates to the task, defaults fall back to config.EXECUTION_TIMEOUT, a single task timeout does not block the whole batch and gates with exit 1), `TestCheckDatasetBoundaries` (an invalid dataset value degrades to InMemory instead of crashing, --limit negative-value boundary), `TestGlobInParallelMode` (the boundary semantics where literal wildcards are intercepted by click's exists check + after shell expansion, multi-file concurrency dispatches the full list)

### Experiments (2.1 / 2.3)
- **SWE-bench source export automation (2.1)**: added `scripts/export_swe_bench_source.py` — reads a downloaded JSONL, extracts the first non-test target file from the patch's `+++ b/<path>`, and does a read-only export via `git show <base_commit>:<path>` (does not pollute the working tree), outputting JSONL in `SWE_BENCH_ENRICHMENT` format; supports `--instance-ids` (comma-separated or @file, used with the missing list from check-dataset output to bulk-fill), `--dry-run`, `--limit`. `SWEBenchDataset` gained `tasks_missing_source()` (identifies tasks whose instance_code fell back to the issue text); the check-dataset quality report outputs the list of missing-source instance_ids with fill-in guidance
- **Automatic RAG metric aggregation (2.3)**: added two sub-aggregations to the RAG section of `experiments/analyze_results.py` — breakdown by retrieval type (retrieval counts/hit rates/similarity of test_cases vs repairs respectively, to analyze which kind of retrieval is more effective) and a RAG-hit × failure-category cross table (for failed tasks, groups RAG hit share by error_category to analyze which error type RAG helps repair most; after the 1.1 refinement, rag_retrieval_empty forms its own group, with hit share necessarily 0)
- Tests: `tests/test_swe_bench_source_export.py` (new file, 11 cases), `tests/test_dataset_validation.py` +2, `tests/test_experiments_scripts.py` +4

### Security (4.1 redaction audit)
- **Complete audit of redaction coverage**: added `docs/redaction_audit.md` (a three-layer defense-line overview + per-exit walkthrough conclusions). Fixed two real blind spots — (A) 7 log points of `APIManager` failover/health checks (str(e) and base_url) now have a module-level `_redact()` that redacts in place; embedded usage (examples/third-party integration/unit tests) is safe without relying on entry-point wiring; (B) the `get_status()` exit redacts base_url (gateway URLs with embedded tokens were printed directly to stdout via print_status_table, bypassing the logging handler). The LLM file cache (prompt/response full text written to disk) is assessed as a known risk in the local trusted domain; redaction would break exact cache-hit matching, so it is recorded as a known acceptable risk with optional follow-up options
- Tests: `tests/test_api_manager.py` +2 cases (get_status base_url redaction regression + _redact helper behavior)

### Documentation alignment (closing batch ②)
- **README data sync**: synced the 9 case-count drifts in the "Test coverage modules" main table against the actual `def test_` counts (test_api_manager 80→77, test_cli_app 30→27, test_cost_aware_routing 14→13, test_dataset_validation 20→22, test_experiments_scripts 23→19, test_swe_bench_source_export 11→13, test_core_modules 29→19, test_executor_sandbox 14→7, test_dataset_loader_extended 73→59, cases added by the 09-14 batches ①/② had not been synced); "currently 1111 cases" corrected to 1158 (consistent with the status table / full measured results)
- **docs/api_reference.md error classification 10→12 classes**: added two state-refinement rows `patch_validation_failed` / `rag_retrieval_empty` to the enum table (1.1); the priority notes gained the `refine_failure_category()` decision convention (a batch ② sync oversight)
- **docs/failure_analysis.md status notes**: "extended to 10 classes" corrected to 12 classes (noting that batch ② added the 2 state-refinement classes)
- **QUICKSTART.md gained a configurable 3.2 cost-alert threshold** (`APIManagerConfig.cost_alert_threshold`, default 2.0)

Full suite **1158 passed / 0 failed** (2 scipy precision warnings are degenerate-data warnings, not code problems)

## [0.9.13] - 2026-09-14 Error classification refinement + circuit cooldown + result analysis batch

### Error classification (1.2 residuals)
- **ErrorCategory gained 2 classes**: `LLM_FORMAT_ERROR` (LLM response format anomalies: JSON parse failure / truncation / empty response — one of the root causes of the previous 75% UNKNOWN) and `INDEX_ERROR` (out-of-range indexing, previously falling into RUNTIME/UNKNOWN so the Debugger could not repair it specifically); `classify()` priority adjusted to LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN (LLM_FORMAT placed first to avoid a misjudgment when an IndexError message happens to contain "assert")
- `get_fix_strategy()` gained 2 targeted strategy texts (LLM regeneration / relaxing JSON extraction; boundary checks for out-of-range indexing, no exception swallowing allowed); the two if/elif chains in root-cause analysis and fix suggestions in `reports/generator.py` gained 2 branches in sync
- Tests: 10 new cases in `tests/test_error_classifier.py` (4 positive classification cases, 2 priority-conflict cases, 2 enum values, 2 fix strategies)

### Observability (4.1 residuals)
- **APIManager circuit cooldown period**: added the `circuit_open_until` / `circuit_cooldown_seconds` fields and the `in_circuit_open` property (monotonic-clock judgment) to `APIHealth`; when `mark_failure` reaches the threshold it writes the cooldown deadline, and `mark_success` resets the circuit breaker; `get_healthy_nodes()` and `_build_node_list` uniformly filter out cooling-down nodes as backup candidates (even if the health-check thread flips `is_healthy` back to True, they are still skipped, to avoid traffic hitting the dead provider again); the default of `APIManagerConfig.circuit_cooldown_seconds` is 60.0s (the `circuit_open_remaining_s` field is exposed via `get_status()`)
- Tests: 9 new cases in `tests/test_api_manager.py` (5 APIHealth circuit state-machine + 4 routing-layer cooldown filters)

### Experiments
- **Result analysis script (4.3)**: added `experiments/analyze_results.py` — extracts success rate / coverage / iteration distribution / Token efficiency / failure-cause distribution (the 1.2 refined categories count separately) / RAG retrieval quality from the benchmark JSON, prints a Markdown summary to the terminal and writes `analysis_summary.md`; compatible with old JSON (when the token_metrics/rag_metrics keys are missing, it falls back to cumulative values from details)
- **Fairness comparison output (2.2)**: added a baseline-level `failure_category_distribution` field to the aggregation stage of `run_benchmark.py`, and printed "average tokens per task / LLM call count" for each baseline in the logger and progress output (a two-dimensional efficiency-effect comparison, not just success rate)
- Tests: 6 new cases in `tests/test_experiments_scripts.py` (5 analyze_results pure-function + 1 prefix recognition)

Full suite **1111 passed / 0 failed**; `ruff check` all green

## [0.9.12] - 2026-09-13 System feature enhancement round

### Features
- **Multi-candidate patches and verification (3.1, off by default)**: added `src/tools/multi_candidate.py` — the Debugger generates N candidate patches in one round (perspective-perturbation prompts, each taking a different repair path); static filtering (`ast.parse` syntax + function completeness + 10% length safety) eliminates bad candidates; optional execution verification (`MULTI_CANDIDATE_EXEC_VALIDATE`) runs tests per candidate and picks the one with the highest pass rate/coverage; wired in via the workflow's `_patch_applier_node`; `ENABLE_MULTI_CANDIDATE_PATCH` defaults to false, preserving the historical experimental convention; when there is no valid candidate, it automatically falls back to a single patch without introducing degradation. Added `tests/test_multi_candidate.py` (19 cases)

### Observability
- **Structured JSONL tracing layer (4.1, off by default)**: added `src/observability/trace.py` — records each task's agent-node inputs/outputs, decision paths (debug/done/regenerate), token consumption, and wall-clock latency in JSONL append mode; when `AITESTER_TRACE_DIR` is unset, everything is a no-op with zero performance tax; when set, it writes `<task_uuid>.trace.jsonl` and passes redaction. Workflow nodes (planner/generator/executor/debugger/patch_applier/_should_debug) record per node; the benchmark entry and the CLI's `_run_single_task` close out task_end in finally. Added `tests/test_trace_observability.py` (12 cases)

### Performance
- **Cost-aware routing (3.4)**: `APIManager` gained the `COST_AWARE` strategy (ranked by a composite score of "50% success rate + 50% 1/cost", so failover avoids switching the full traffic to an expensive provider) and a cost alert (logging a WARNING when failing over to an expensive node with `cost_weight>=2.0`; can be disabled via `cost_alert_enabled`); added a `cost_weight` field to `LLMConfig` (read by `config.py` from `LLM_N_COST_WEIGHT`; unset defaults to 0.0 = no information, APIManager falls back to the 1.0 baseline); `APIManagerConfig.node_cost_weights` supports explicit mappings. Added `tests/test_cost_aware_routing.py` (10 cases)

### Experiments
- **Bringing RAG into the main experiment (2.3)**: `reproduce.sh` now explicitly passes `--enable-rag` by default for synthetic/built-in datasets (rag_data/ persists and is reused across experiments); `--no-rag` can fall back to the config default; `run_benchmark.py` gained the `--no-rag` argument (together with `--enable-rag` it overrides `config.ENABLE_RAG`)

### Tests
- **CLI boundary test backfill (1.5)**: added `TestRunParallelJsonBoundaries` (6 cases) to `tests/test_cli_app.py` — a single file + concurrency takes the sequential branch, the multi-file concurrency fallback path, glob wildcards intercepted at the click `exists=True` parsing layer (exit 2), and the exit-code semantics of all-pass / has-failures under concurrency. Full suite **1085 passed / 0 failed**; total src coverage 91%; `ruff check` / `ruff format --check` all green

## [0.9.12] - 2026-09-13 Documentation alignment batch M-01~M-03

### Documentation
- Synced 13 case-count drifts in the README "Test coverage modules" main table (test_api_manager 62→63, test_cli_app 11→15, test_config_manager 29→32, test_dataset_loader_extended 57→62, test_dependency 27→35, test_error_classifier 56→60, test_executor 35→39, test_experiments_analysis 11→15, test_experiments_scripts 8→10, test_generator 21→30, test_mysql_client 12→13, test_patch_applier 36→38, test_workflow 28→30, unsynced after the 0.9.11 batch added 27 regression cases); "41 test files" corrected to 44; added a `test_logging_utils.py` (14-case redaction regression) row. The historical version narrative table for v0.9/v0.10 keeps its original values
- Full suite **1038 passed / 0 failed**; total src coverage 91%; `ruff check` / `ruff format --check` / lock sync / sdist+wheel build / pip-audit (same CI exemptions) all passed (pure documentation changes, no code changes, test suite unaffected)

## [0.9.12] - 2026-09-12 Optimization round

### Documentation
- Aligned the README core-module coverage data with measured values (logging_utils 83%→88%, cli/app.py 61%→64%; the drift after the previous round added 18 cases had not been synced)
- Aligned the README security-scan notes with the PYSEC exemption convention ("4 known CVEs"→"5 exemptions: PYSEC-2026-311 duplicate entries ×2 + PYSEC-2026-3813/3814/3815", consistent with the ci.yml comment)
- Corrected the wording of the QUICKSTART configuration-verification step: `from config import LLM_CONFIGS` only verifies that configuration loads (no network calls); the real connectivity probe points to `python scripts/check_quota.py`
- Full suite **1038 passed / 0 failed**; total src coverage 91%; `ruff check` / `ruff format --check` / lock sync / sdist+wheel build / pip-audit (same CI exemptions) all passed

## [0.9.12] - 2026-09-11 Optimization round

### Security
- **Extended the log-redaction regex**: the API key redaction pattern in `src/utils/logging_utils.py` previously only covered `sk-` prefixed keys + 20+ alphanumeric characters; now two real key shapes that previously bypassed redaction are added — long sk- type keys with dot/hyphen segments (shaped like `sk-ws-xxx.yyy...`) and long hexadecimal keys without the `sk-` prefix (≥32 chars) / long base64 keys (≥40 chars); locked by the newly added `tests/test_logging_utils.py` (14 cases, all using synthetic placeholders, no real keys introduced)
- **Synced the CI security gate exemptions**: the pip-audit exemption list in `.github/workflows/ci.yml` had drifted in practice (a local 9-11 rerun of chromadb==1.5.9 reported `PYSEC-2026-311`×2 + `PYSEC-2026-3813/3814/3815`, while the old list still exempted `CVE-2026-45830/45831/45833`); 4 exemptions were synced to match the measured results with a comment explaining the drift, restoring the credibility of the security job

### Packaging
- **Completed setup.py**: added `py_modules=["config"]` (previously `find_packages()` did not collect the root-level `config.py`, so after a formal install `from config import ...` raised ModuleNotFoundError, breaking all core CLI/API entry points); added `experiments` (scipy+datasets) and `ux` (rich+tqdm) to extras, and `pytest-timeout` to dev

### Tests
- Added 14 log-redaction cases + 4 CLI parameter-validation cases (--parallel=0 / --max-iterations=0 / --coverage-threshold out-of-range / a non-existent file intercepted by click); full suite **1038 passed / 0 failed** (0.9.11's 1014 + 6 locally added regression fixes + 18 this round); total src coverage 91%; `ruff check` / `ruff format --check` / lock-sync validation all passed

### Documentation
- Removed 4 non-existent test files from the v0.9.10 section of the README (`test_api_manager_large_scale.py` / `test_error_classifier_improvements.py` / `test_executor_integration.py` / `test_patch_abplier_improvements.py` were all ghost entries)
- Aligned the README case counts/coverage data with this round's baseline (987/1014 → 1020/1038 converged in two stages, final 1038); aligned the wording of where ablation-experiment switch configuration lives (config.py defaults + `.env` injection; .env is gitignored)
- **Committed optimization records**: newly added and committed `docs/history/optimization_plan.md` (the full 16-item stage-1 optimization table + implementation scope + items needing confirmation) and `docs/history/optimization_report.md` (complete delivery records for stages 0-5 + the measured full-test results table for stage 4) as traceable documents for the 0.9.11 optimization round; the DOCKER_IMAGE drift correction in the local `.env` (3.11-slim → 3.12-slim) is local-only (`\`.env\` is gitignored, no committed impact)

## [0.9.11] - 2026-09-11

### Source layer: import extraction and dependency detection convergence
- **Single implementation for import extraction (DRY)**: added the shared implementation `extract_import_module_names` to `src/tools/dependency.py` (handles comma-separated multi-module imports, `as` aliases, trailing comments, skipping relative imports, and multi-line parenthesized imports); `extract_imported_modules` delegates to it, and `executor._extract_imports` reuses it too (no longer maintaining a locally copied regex) — previously the two copied regexes `^import\s+([\w.]+)` only captured the first module, so `import numpy, scipy` would miss `scipy`; the missing dependency escaped detection and the venv had fewer packages installed, causing the test to fail with ImportError
- **Tightened the standard-library check**: `is_standard_library` removed the dead-code `_FALLBACK_STDLIB` whitelist (under Python 3.12+ `sys.stdlib_module_names` always exists, so that branch was unreachable, and the whitelist incorrectly listed the third-party `pytest` as stdlib); when the authoritative list is missing, it now returns False and defers to an actual `find_spec` probe

### Source layer: execution environment and concurrency safety
- **executor project-root correction one level up**: `project_root` now walks up three levels from `src/agents/executor.py` to the repository root (consistent with the patch allowlist in workflow.py and the root-directory convention in cli/app.py); it previously walked up two levels, stopping at `src/`, so the `rglob` module search could not see directories outside src such as `examples/`, breaking the import repair chain for non-same-name helpers
- **PYTHONPATH trailing-separator guard**: when the original PYTHONPATH was unset, direct concatenation produced a trailing empty segment `"<dir>:"` (an empty element in sys.path is equivalent to the CWD, and a same-named file could shadow a third-party library); now empty segments are filtered before `os.pathsep.join`, unified across both the non-sandbox and sandbox paths
- **Double-checked locking for the MySQL singleton**: added `_instance_lock` / `_pool_lock` at the class level of `MySQLClient`; both `__new__` and `__init__` use a "lock-free fast path + locked re-check" DCL; previously the lock-free check-then-set under concurrent first construction could produce multiple instances and amplify the connection pool
- **Unified DCL for base_agent caches**: both the chat-client cache and the zai-client cache now use lock + re-check double-checked locking; when `base_url` is empty in `_get_llm_config`, a symmetric fallback to `LLM_CONFIGS[0].base_url` was added (fixing an AttributeError)

### Source layer: fault tolerance and semantic corrections
- **Model routing semantics of failover**: when `APIManager.call` explicitly specifies a model, only the primary attempt uses the specified model; after failing over to a backup node, that node's own model name is used — previously the specified model was carried over on every attempt, and a backup provider without that model was dragged down one by one by APIErrors, rendering failover a no-op
- **Made the RAG init-failure flag sticky**: when `get_rag_retriever`'s construction throws, it sets `_rag_init_failed`, and subsequent node calls return None directly on the fast path without retrying; previously the except branch set `_rag_retriever` to None (which was None anyway, a no-op), and each generator/executor/debugger node paid the 2-6s initialization cost repeatedly
- **Decoupled the generator node from the global switch**: the test_plan argument now goes through `state.get("test_plan")` (a missing key passes None and Generator infers it itself); previously `state["test_plan"] if ENABLE_PLANNER else None` raised KeyError when ENABLE_PLANNER was on but the graph had no planner node
- **Strictified the index parameter of add_llm_config**: an explicit index is validated for `index >= 1` and no collision with an occupied LLM_N number (collision returns False); previously there was no validation, and appends produced double blocks with the same number, with undefined read behavior where the later read overwrote the earlier one
- **Fixed NaN/Inf serialization in the significance test**: when the two groups' pass rates are fully constant (all 1s or all 0s), scipy returns NaN (paired t with zero difference) or ±Inf (Welch with zero variance); `round(float(...))` would write non-standard tokens into the result JSON, and strict parsers (such as JS JSON.parse) would error; now guarded with `math.isfinite`, recording a `status: "skipped"` entry instead of a numeric entry (that comparison statistically has no "significance" to speak of in the first place)
- **Converged frame matching to a single endswith**: the old three-clause logic in `error_classifier._is_test_side_assertion` (basename exact match / module name exact match / endswith) — for pytest .py frames the first two are subsets of the latter — was converged to a single `endswith(f"{target}.py")` (the existing limitation of "mycalc.py falsely hitting calc.py" is preserved and locked with a regression test); the `import os` used only here was removed
- **Full env variable names in the config template**: `generate_env_template` variable names are unified to the `{PROVIDER}_API_KEY` full-name convention (ALIYUN_BAILIAN_API_KEY / AGNES_DOMESTIC_API_KEY / AGNES_INTERNATIONAL_API_KEY / BIGMODEL_API_KEY / DEEPSEEK_API_KEY), with the same derivation rule as generate_batch_config; previously the hardcoded short names (ALIYUN_API_KEY, etc.) did not match the provider key names and could never be read; `.env.local.template` was regenerated by the generator itself
- **Dead branch and no-op cleanup**: executor removed the unreachable `if missing_packages and not self.use_venv:` dead branch (the `use_venv` guard is kept for regression tests); `analyze_failures.py` removed two no-op list comprehensions; `.env.example` removed the DATASET_DEFAULT ghost config block (zero consumers repo-wide)
- **Fixed the visualize summary table**: the baseline summary table header in `write_summary_md` previously had 5 columns + 3 columns split across two rows, misaligned with the 8-column data rows; now a single 8-column header + 8 separators

### Experiment/script layer
- **Unified SWE-bench download output naming**: the output of `scripts/download_swe_bench.py` is now `swe_bench_{subset}_instances.jsonl`, consistent with the loader's `_resolve_jsonl_paths` convention

### Documentation
- Removed 4 ghost `run_benchmark --json` mentions from the README (benchmark JSON output is the default behavior; that flag is not needed; `main.py run --json` is a separate CLI spot and is retained); the same error fixed in docs/usage_examples.md; docs/api_reference.md version table completed for 0.9.1-0.9.10

### Tests
- Added 27 regression cases: dependency comma-import extraction 8 / executor project root and PYTHONPATH 4 / api_manager model routing 1 / mysql concurrent construction 1 / config_manager index validation 3 / significance NaN-Inf guard 2 / error_classifier frame matching 4 / visualize table alignment 2 / workflow test_plan decoupling and RAG sticky flag 2
- Full suite **1014 passed / 0 failed** (0.9.10's 987 + 27 new); total src coverage 91%; `ruff check` / `ruff format --check` / lock-sync validation all passed
- Deliberately kept: the token_usage dead-thread aggregation (needed for aggregation at the end of a benchmark run, locked by `test_global_aggregates_threads`); the `rate_limit_remaining` field (referenced by 8 tests); the error_classifier SYNTAX+IMPORT_ERROR defensive branch

## [0.9.10] - 2026-09-11

### Source layer: DRY-ified the CLI concurrent dispatch
- **Merged the two isomorphic blocks of `run`'s concurrent execution**: in the multi-file scenario of the `run` command in `src/cli/app.py` with `--parallel>1`, the rich progress-bar branch and the plain-text fallback branch each maintained a copy of the isomorphic "future submission + `as_completed` aggregation + per-task fault tolerance" loop (about 30 lines of duplication); a result-structure change had to be synchronized in two places, drifting easily; now a shared dispatcher `_dispatch_parallel_tasks()` is extracted as the single construction point; the two modes differ only in progress-feedback strategy, injected via `on_progress` / `on_success` callbacks (rich advances the progress bar / plain text prints `✓ done`, silent when `--json`); behavior unchanged

### Tests
- Added `tests/test_cli_parallel.py` (10 cases): all-success / a single task exception does not break the whole batch / `on_success` fires only on success and passes the basename / `on_progress` fires at the end of each task (including failures) of `_dispatch_parallel_tasks`; error-result redaction and isomorphic key sets of `_handle_task_exception`; four end-to-end paths of the `run` concurrent branch (rich available / no rich / single file falls back to sequential execution / failure gates with exit 1, with mocked workflow)
- Full suite **987 passed / 0 failed** (+10 new); cli/app.py coverage 50% → 61%, total src coverage 90% → 91%; `ruff check` / `ruff format --check` all passed

## [0.9.9] - 2026-09-11

### Experiment/script layer: wrong-result selection and crash-guaranteed KeyError fixes
- **Fixed visualize wrong result selection**: `load_latest_result` in `experiments/visualize_results.py` previously took the first of the bare-filename descending sort over all JSON in the results directory, wrongly selecting `swebench_20_summary.json` / `performance_benchmark.json` / `synthetic_plain_llm_*.json` ('s'/'p' both sort after 'b'), so charts were actually based on non-benchmark data; now only the `benchmark_*` prefix is recognized (consistent with the run_benchmark naming convention), falling back to the full set with a notice when there is no match
- **Fixed the crash-guaranteed KeyError in the standardized experiment**: all three return branches (success/failed, timeout, error) of `run_experiment` in `scripts/run_standardized_experiments.py` lacked the `description` key, while `main()` unconditionally read `r['description']` when writing the summary report — a guaranteed KeyError on every run, and EXPERIMENT_SUMMARY.md could never be generated; now all three branches carry a description
- **Fixed the benchmark parallelism config bypass**: the parallel default in `experiments/run_benchmark.py` previously read the raw environment variable directly via `int(os.getenv("BENCHMARK_PARALLELISM","0"))`, so a bad value (such as "abc") crashed with ValueError immediately, bypassing the config's fault tolerance; now it uniformly goes through `config.BENCHMARK_PARALLELISM` (`_parse_int_env` fault tolerance + lower-bound validation)
- **Added logging to the silent error-swallowing of the benchmark LLM fallback**: the outer `except` of `_call_llm_with_fallback` previously did a silent `continue`, so when the zai branch's retries were exhausted and raised, or when zai/openai client construction failed, the whole chain had no log trail; now a warning log is added (aligned with the existing convention of the openai branch)

### Source layer: dead code and ghost config cleanup
- **Removed the dead branch in executor**: in `_execute_sandboxed`, when dependency installation fails / venv creation fails (`sandbox_error_info` is non-None), the dependency-detection stage returns early; the following "installation failure takes priority to overwrite error_info" branch is therefore always unreachable (the variable is always None); the dead branch was removed, behavior unchanged
- **De-duplicated the planner default plan**: the except fallback branch of `_planner_node` previously inlined a copy of the default plan dict isomorphic to `_get_default_test_plan` (the validation-failure branch had long since gone through the helper); dual maintenance drifts easily; now it uniformly goes through the helper as the single construction point, and its "or 'unknown'" fallback is stricter than the original inline `.get` default value (empty string / None key values are also normalized)
- **Removed the dead constant in generator**: `_MAX_PARAMETRIIZE_RETRIES = 2` had no code reference outside the docstring; the actual implementation retries only once on parametrize validation failure; the constant was removed and the docstring aligned to the actual behavior
- **Wired up the MySQL connection pool idle_timeout**: `_POOL_IDLE_TIMEOUT = 600` was defined but never passed into the PooledDB constructor (a dead constant), yet the comment claimed it was the idle_timeout; now wired up — idle connections are reaped after 600s, preventing the server's wait_timeout from severing long-lived connections
- **Wired up the ghost config in APIManager**: `APIManagerConfig.max_consecutive_failures` (default 3) was defined but never consumed by `mark_failure` (the node threshold was hardcoded to 3); now APIHealth gains the same-named field (default 3, preserving historical behavior), injected from the manager config at APIManager construction/add_node time, and `mark_failure` reads its own field

### Tests
- Added 14 regression cases (visualize prefix filtering 3 / standardized return keys 4 / benchmark parallelism guard 1 / planner de-duplication 2 / mysql idle_timeout 1 / api_manager ghost config 3); full suite **977 passed / 0 failed**; total src coverage 90%; `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.8] - 2026-09-10

### Engineering: restoring the format gate and fixing doc drift
- **Restored the `ruff format` gate**: after 0.9.7, 15 files (13 .py + README.md / docs/api_reference.md) had line-break/whitespace drift from the ruff 0.16.3 format, and `ruff format --check` turned the CI lint step red; the gate was restored after uniformly reformatting (pure whitespace normalization, no logic changes)
- **Drift in the README test-status table**: the case count was stuck at 860 (the old 0.9.5 value), and the "latest optimization" row still pointed to 0.9.5; now aligned with measured values (963 cases / total src coverage 90%)

### Refactoring: de-duplicating the benchmark result construction
- **De-duplicated the three result dicts in `run_benchmark`**: the success / rate-limit retry / exception branches of `run_single_task` each wrote a copy of the isomorphic 12-field result dict; a new metric (token_metrics, etc.) had to be synchronized in three places and drifts easily; now `_build_task_result()` is extracted as the single construction point (the success path takes the `final_state` values, the failure path uses placeholder values), and a key-set consistency regression guard was added
- **The single_agent baseline's timeout bypassed config validation**: `ExecutorAgent(timeout=int(os.getenv("EXECUTION_TIMEOUT", "30")))` read the raw environment variable directly; a bad value (such as "abc") would crash immediately with ValueError, bypassing the [10, 300] range validation; now it uniformly goes through `config.EXECUTION_TIMEOUT` (fault-tolerant parsing + range validation, consistent with the workflow executor node's convention)

### Converging the APIManager construction side effect
- **The background health-check thread can be turned off**: `APIManager.__init__` previously started a daemon thread unconditionally, issuing real LLM health-check requests to all nodes every 60s (consuming API quota); embedded usage and unit-test scenarios produced network side effects at construction time. A new `enable_health_checker` parameter was added (default True, preserving historical behavior); tests all construct with `enable_health_checker=False`, and the suite no longer produces stray threads

### Performance
- **Precompiled the failed-case parsing regex in executor**: `_parse_failed_cases` re-ran `re.compile` on every call; it is now precompiled at module level (aligned with the "precompile to avoid repeated overhead" convention of other regexes in the same module)

### Tests
- Full suite **963 passed** (+6 new: 4 benchmark result construction + 2 health-thread switch), 0 skipped; total src coverage 90%; `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.7] - 2026-09-10

### P0: large-file context and dataset quality
- **AST smart extraction (code_context)**: when `BaseAgent.truncate_code` exceeds the budget, it no longer hard-truncates "half head, half tail"; it first does AST extraction by the focus function (keeping imports + the target function and its directly dependent helper functions, with head/tail truncation for over-long function bodies), falling back to character-level last-resort only if still over budget; Generator/Planner/Debugger pass `focus_function` through the whole chain; SWE-bench tasks initialize `target_function` with the `suggested_function` extracted from the official patch
- **SWE-bench loading quality validation (check-dataset)**: the official JSONL has no source-code field under test; `validate_task()`/`quality_report()` check per task the instance_code fallback value, source code validity, and the test_code cases and case count; `_extract_suggested_function()` extracts the target function from the official patch hunk headers (measured 96% extraction rate on 225 local tasks); `_load_enrichment()` fills in the source-code fields via the JSONL specified by `SWE_BENCH_ENRICHMENT`; the CLI gained a new `check-dataset` command as the troubleshooting entry point
- **LLM token usage statistics (token_usage)**: thread-local cumulative input/output tokens, bucketed by model; `reset()` before a benchmark run, and `token_metrics`/`token_usage` are output with the result JSON at the end, supporting the cost-effectiveness comparison of the full system vs Plain LLM

### P1: execution isolation and RAG
- **Executor venv sandbox**: when `EXECUTOR_USE_VENV=true`, tasks run pytest in an isolated venv with a temporary sandbox directory + a disk cache keyed by dependency combination; `PYTHONPATH` points only to the sandbox directory, so dependencies across tasks do not conflict and the system environment is not polluted; `EXECUTOR_AUTO_INSTALL_DEPS=true` auto pip-installs missing dependencies (only into the venv); missing dependencies are written to `error_info.missing_dependencies`, classified by the classifier as `import_error`, so "the environment lacks dependencies" is no longer misjudged as a code bug
- **RAG persistence + retrieval quality metrics**: the retrieval store is persisted to `rag_data/` (configurable via `RAG_PERSIST_PATH`/`RAG_COLLECTION_NAME`/`RAG_TTL_SECONDS`, TTL default 7 days, an empty path falls back to in-memory mode), reusable across experiment runs; `TestCaseRetriever.evaluate_retrieval()` provides Hit Rate@k / MRR; `AITesterState.rag_stats` accumulates the hits and similarities of the two retrievals (test_cases/repairs), and the benchmark result JSON outputs `rag_metrics`

### P2: error classification refinement
- **Five classes → eight classes**: `IMPORT_ERROR` (split off from SYNTAX: missing dependencies and syntax mistakes have completely different repair paths), `TYPE_ERROR` (split off from RUNTIME: check parameters and return types), `LOGIC_ERROR` (split off from ASSERTION: the assertion failed but the failure stack did not touch the module under test, suggesting to fix the test rather than blindly changing the code); `classify()` gained a `target_module` parameter to support LOGIC_ERROR judgment; the fix strategies and the report generator synchronously gained the three new-class branches

### Engineering and security
- **Externalized configuration**: the four MySQL connection-pool parameters (`MYSQL_POOL_*`) were moved from hardcoding in `mysql_client.py` to environment-variable injection in `config.py` (defaults consistent with history, behavior unchanged when unset); the three execution-isolation and three RAG parameters were also added to `.env.example`
- **Hardened log redaction**: LLM exception text in `base_agent` uniformly goes through `mask_sensitive_info` (including the zai path and the final raise); the `experiments/run_benchmark.py` entry explicitly mounts `setup_logger_safety()`, filling the redaction blind spot of non-CLI entries such as experiments
- **Benchmark troubleshooting toolchain**: `--save-state` writes the stage-level state (test plan / generated code / diagnosis / patch) to `output_dir/raw/`; added `compare_failures.py`, which compares per stage the tasks "failed in baseline A but succeeded in baseline B" and outputs a Markdown report (suspected-stage hints + token summary)
- **Doc sync**: `docs/api_reference.md` updated the eight-class table, `focus_function`/`target_module` parameters, and the new tool modules (CodeContext/Dependency/TokenUsage); the `src/tools/__init__.py` docstring completed the module list; the README test-coverage table aligned with measured case counts (40 files / 957 cases)

### Tests
- Added 6 test files (code_context 11 / dependency 27 / executor_sandbox 7 / dataset_validation 14 / token_usage 9 / rag_metrics 5), 40 test files in total, 957 collected cases, total src coverage 90%

## [0.9.6] - 2026-09-10

### Workflow correctness fixes
- **regenerate routing infinite loop**: `_should_debug` routed back to the generator to regenerate when the maximum iterations were reached and the diagnosis hit the "test generation error" keyword, but the old implementation did not increment the counter or clear `diagnosis`, so the repeated keyword hits ping-ponged generator↔executor forever until the task crashed on LangGraph's `recursion_limit`, wasting a dozen or so rounds of LLM calls in vain. `regeneration_count` was added to `state`, incremented by 1 on each regeneration with the stale `diagnosis`/`error_category` cleared; after reaching `_MAX_REGENERATIONS` (=1), `_should_debug` returns "done". 3 regression tests added
- **patch_applier state/disk desync**: when the safety checks (empty / too short / no function definition / illegal path) rejected a write to disk, the node still returned `new_code` as `target_code` and recorded `patch_applied=True`, causing the "phantom iteration" where the downstream Executor tested the old file while the Debugger analyzed the new code. Now `target_code` is updated and `patch_applied=True` recorded only on a successful write; otherwise the original code is kept and False is recorded. 3 cases added: success / rejected / too short
- **Path allowlist prefix collision**: `startswith((project_root, temp_dir))` lacked `os.sep`, so a sibling directory `AITester_backup/` could hit and bypass the allowlist; now compared with `os.sep` via `_is_within_allowed_roots`, and normalized with `realpath` (the macOS `/var`↔`/private/var` symlink mismatch)
- **Non-atomic writes to disk**: `open("w")` truncated before writing, and a mid-way crash would corrupt the user's source file. Now `_write_file_atomic` writes a temporary file and atomically replaces via `os.replace`
- **Generator wrongly rewrote third-party library imports**: `_fix_import_module` previously replaced all `from X import` statements outside the allowlist unconditionally with the module under test's name (breaking `from numpy import array`). Now it reuses the executor's ready-made `SequenceMatcher` similarity gate (threshold 0.6, same source as `_is_similar_module_name`), replacing only "typo"-level similar names and preserving dissimilar third-party libraries

### Security
- **Added `.dockerignore`**: the Dockerfile's `COPY . .` previously baked the local `.env`/`.env.local` with real LLM keys, `.venv/`, `.git/`, `.private/`, and various caches into the image. All sensitive/irrelevant content is now excluded
- **Exception-stack redaction blind spot**: `SensitiveFilter` covered only `record.getMessage()`; the traceback from `exc_info`, generated by `formatException`, bypassed the filter (the trigger point was `safe_execute`'s `logger.error(..., exc_info=True)`), contradicting the module's claim that "exception text is redacted". A new `SensitiveFormatter` redacts again over the fully formatted result (including the stack), mounted uniformly on the CLI handler; 2 cases added
- **Redaction of the JSON error field**: the `error` field of a task exception (`str(error)`) went to stdout via `click.echo`; the redaction filter covered only the logging channel, so an LLM exception message containing a key would leak bare. Now it is redacted via `mask_sensitive_info`

### Defect fixes
- **CLI failed yet exited 0**: the `run` command returned 0 regardless of success or failure, so CI/scripts could not gate on it. Now `raise SystemExit(1)` when any task fails (including error results produced by crashes); exit 0 when all pass. 2 gating cases added
- **`--json` output polluted**: the log `StreamHandler(stdout)` and the rich progress bar shared stdout, so `| jq` parsing always failed. Now JSON mode temporarily silences the stdout console handler via `_quiet_console_logs()` (only changes the level, not the stream — friendly to tests), the rich progress bar goes through `Console(stderr=True)`, and `stdout` carries only JSON
- **Executor timeout lost partial output**: `TimeoutExpired` carries partial stdout/stderr; the old implementation returned empty strings, so the Debugger could not see the scene. Now `e.output`/`e.stderr` are merged into the output. 1 case added
- **`reproduce.sh`'s default quick mode did not limit tasks**: the default `MODE="quick"` but `TASK_LIMIT=""`, so running without arguments actually ran unlimited tasks, contradicting the documented "quick=3". Now the default `TASK_LIMIT=3`
- **Field name mismatch in `generate_batch_config.py`**: it read `model.get("name")`, but the field in `llm_configs.json` is `model_name`, so the generated model names were all `unknown` in the column. Now `model_name` takes priority, with `name` as the fallback
- **ruff `target-version` drift**: `pyproject.toml` said `py310`, but `setup.py` has `python_requires>=3.12` and the CI matrix floor is 3.12. Now aligned to `py312`

### Engineering
- **CI speedup and reliability**: added `cache: pip` + `cache-dependency-path: requirements.txt` to the two `setup-python` steps (saves 3-8 minutes per matrix); added `timeout-minutes` to the `test`/`security` jobs (30/10) to prevent long hangs; pinned `pip-audit` to `==2.10.1` (consistent with the "pin versions to prevent drift" principle)

### Tests
- Full suite **870 passed** (+10 new cases: regenerate cap ×1, patch_applier consistency ×2, generator regeneration ×2, generator import gating ×1, executor timeout partial output ×1, redaction ×2, CLI gating ×2, of which 1 is an update of an existing assertion), 0 skipped; `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.5] - 2026-09-10

### Critical defect fixes
- **`remove_llm_config` left key lines after removing a model**: the old implementation's per-line skip matching only hit the `LLM_N_MODEL_NAME` line; the comment lines / `API_KEY` / `BASE_URL` lines of the same block remained in `.env.local` — keys lingered in the file long-term, the numbers stayed occupied causing the auto-allocation offset, and the `gone_indices` environment variable cleanup never triggered. Now, after recognizing the number set from the MODEL_NAME line (exact end-of-line match), the whole block is removed; 4 regression tests added (whole-block removal / preserving other models / multiple numbers with the same name / a partial name does not falsely delete)
- **`src/utils` missing `__init__.py`; the pip package missed the subpackage**: `find_packages()` collects only directories with `__init__.py`, so `src.utils` was not in the distribution package, and after install `from src.utils.helpers import ...` raised ImportError directly (the problem was masked locally by the PEP 420 namespace-package mechanism). Added the package marker files, and a new `tests/test_packaging.py` (filesystem assertions, no setuptools dependency, including subpackage drift detection)
- **CLI log configuration silently broken under Python 3.14**: the module-level `logging.info()` at the tail of `logging_utils.setup_logger_safety()` triggered an implicit `basicConfig()` when the root had no handler (attaching a bare StreamHandler), making app.py's subsequent `basicConfig` (custom format + FileHandler) a whole no-op — file logging had never taken effect. Changed to record with the module logger

### Defect fixes
- **Fault-tolerant parsing of numeric environment variables**: `MAX_ITERATIONS` / `COVERAGE_THRESHOLD` / `BENCHMARK_PARALLELISM` / `LLM_RETRY_WAIT` / `MYSQL_PORT` / `TEMPERATURE` / `EXECUTION_TIMEOUT` / `LLM_TIMEOUT` previously used bare `int()/float(os.getenv(...))` conversion; a single bad value (such as `MAX_ITERATIONS=abc`) raised ValueError at import time, making the whole program unable to start. Added `_parse_int_env` / `_parse_float_env`: bad values / out-of-range log a WARNING and fall back to defaults; `COVERAGE_THRESHOLD` gained a [0,100] constraint and `TEMPERATURE` a [0,2] constraint
- **CLI sequential mode: a single task exception aborted the whole batch**: in the multi-file scenario of `--parallel=1`, any task exception (file read failure / workflow crash) aborted the whole batch, inconsistent with the concurrent branch's per-task fault tolerance. Now the sequential branch has per-task try/except, reusing the unified `_make_task_error_result` to append the error result and continue; `--timeout` gained >=1 validation (a negative / 0 would make the subprocess time out immediately)
- **Log redaction never took effect + two implementation defects**: `logging_utils.SensitiveFilter` had no entry reference (a dead module), so the redaction capability did not actually exist. Now the CLI entry calls `setup_logger_safety()` after `basicConfig` to mount the filter, and fixed: (a) logger-level filters cannot stop messages propagated from child loggers; they must also be mounted at the handler level; (b) per-field masking missed keys split across msg and args (`logger.info("sk-%s expired", key)`); it now first formats with `getMessage()` and redacts the whole string

### Refactoring
- `api_manager`: moved `_HEALTH_CHECKER_SHUTDOWN_TIMEOUT` to be defined before the `APIManager` class that uses it (it was originally at the end of the file, relying on late binding of module-level names)
- `reports/generator`: removed the write-only-never-read `_report_counter` dead property
- `dataset_loader`: synced `get_available_datasets` with `load_dataset`'s `dataset_map` (added the `examples` / `synthetic` / `synth` aliases); updated the corresponding tests
- `patch_applier`: changed 3 per-line `re.match` calls inside loops to precompile before the loop
- `error_classifier`: promoted `syntax_keywords` to the module-level constant `_SYNTAX_ERROR_KEYWORDS` (it previously rebuilt the list on every call)
- `helpers`: precompiled the ```python regex of `extract_code_block`; corrected the docstring numbering
- `cli/app`: removed the dead `else` inside the non-empty branch of `list_examples`
- `.env.example`: removed the drift in the `BENCHMARK_PARALLELISM` comment (parallelism is implemented, not "not yet implemented"); added an `LLM_RETRY_WAIT` description

### Tests
- Full suite **860 passed** (+18 new cases: 4 config_manager whole-block removal regression, 3 packaging, 6 config fault-tolerant parsing, 3 CLI fault tolerance, 2 redaction wiring), 0 skipped; total coverage **90%** (88% → 90%); `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.4] - 2026-09-13

### Defect fixes
- **Environment variable name mismatch in the batch config generator (M20)**: `generate_batch_config.py` and the embedded template's `main()` hardcoded reading 4 environment variable names such as `ALIYUN_API_KEY`/`AGNES_API_KEY`, but `generate_config` looks up keys by `{PROVIDER}_API_KEY` (e.g. `aliyun_bailian → ALIYUN_BAILIAN_API_KEY`); the two never matched and could only land on placeholders. Now the key names are derived from the providers that actually appear in models (same source as `generate_config`), so any provider can be read; the root script and the embedded template are synced, and a subprocess regression test was added
- **False t-test in `analysis.py` (M15)**: the `significance` field previously wrote the hardcoded placeholder text `"t-test (requires scipy)"` (never actually executed). Now it is really computed from the per-task `details`: `task_id` pairing goes through `ttest_rel`, otherwise Welch's two-sample test; when the sample is insufficient / scipy is missing / there are no details, it honestly returns `insufficient_data` / `unavailable` instead of pretending the test was run; `generate_comparison_report` gained a Significance Test section
- **Three distortions in `code_analyzer`**: `replace_function_code` matched only `ast.FunctionDef`, silently missing `async def` (`AsyncFunctionDef` is not a subclass of it); cyclomatic complexity missed the ternary expression `ast.IfExp`; the `BoolOp` comment contradicted CPython's actual behavior (chained `and` collapses to a single node rather than a binary tree); `parse_function_nodes`' doc claimed args exclude self/cls but the code never excluded them — all three fixed

### Refactoring
- **Converged the double statistical-test implementations**: `experiments/statistical_analysis.py` and `run_statistical_test.py` each had a near-duplicate implementation, and the old version paired by position (truncating at min_len) — when the two baselines' result orders disagreed, different tasks were wrongly paired together, distorting the t/p values. Now pairing is uniformly by `task_id` (each task runs once under each of the two baselines), the canonical implementation converged into `statistical_analysis.py` (the filename the paper submission package references), and `run_statistical_test.py` degrades to a thin-shell entry; the pairing logic was extracted as `_pair_by_task`, the effect size uses the paired-difference standard deviation convention, the NaN branch is safe, and the Markdown report shows n/a for nan values
- **Migrated to the chromadb 1.x modern client API**: `chromadb.Client(Settings(persist_directory=...))` is deprecated, and `Settings()` defaults to `persist_directory='./chroma'` — "memory mode" (`persist_path=None`) actually creates a persistent directory in the CWD (the same kind of pollution as aiterator.log). Now when `persist_path` is given it uses `PersistentClient`, otherwise `EphemeralClient` is purely in-memory, and `anonymized_telemetry` is turned off to avoid background telemetry reporting

### Performance
- **60s throttling for RAG cleanup's full-table scan**: the old behavior ran a `collection.get(include=[metadatas])` full-table scan (O(N)) on every `add_case`/`add_repair` call, accumulating to O(N²) over long runs with a large cache. Now the scan is skipped when "capacity not full AND already cleaned before AND less than 60s since the last cleanup"; a full capacity (eviction needed) and the first cleanup still run every time, with unchanged eviction semantics; TTL defaults to 3600s, and the worst-case 60s cleanup delay is negligible for the actual expiration semantics

### Tests and documentation
- Completed tests for low-coverage modules: `planner.py` (from 42%, mocking `_call_llm_with_cache` to cover the four paths of `plan()` + `LogicAnalysisResult`), `synthetic_dataset.py` (from 48%, triggering lazy loading to verify structure / seed reproducibility / different-seed differences / modulo coverage), `code_analyzer.py` (from 0%, 17 cases), `analysis.py` (from 0%, 11 cases), `cli/app.py` (`list-examples` normal / missing directory + `--version`); the `run` command is 140 lines of orchestration glue requiring heavy mocking, not covered this round
- Corrected the `plan()` doc: non-JSON actually raises `JSONDecodeError` (`_extract_json` delegates to `extract_json_object`), previously mislabeled as `RuntimeError`
- **Regression**: full suite **842 passed** (+44 new cases), 0 skipped, 1 warning (chromadb internal DeprecationWarning, third-party library); total coverage 88%; `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.3] - 2026-09-13

### Configuration and experiment correctness fixes
- **`.env.local` write path and refresh did not take effect**: `config_manager` previously wrote LLM config into `src/config/.env.local` (the module's directory), while the application only reads the root-directory `.env.local`, so `add_llm_config`/`remove_llm_config` had no effect after a restart. Now writes are unified to the root directory; a new `config.refresh_llm_configs()` refreshes `LLM_CONFIGS` in place (an import-time snapshot does not update automatically), and removal synchronously cleans up residual `LLM_N_*` variables in `os.environ`; auto-numbering now scans the occupied numbers in the file and takes max+1 (number gaps no longer collide); duplicate-model checking covers arbitrary numbers
- **Baseline comparison validity**: `build_workflow` gained `planner`/`debugger` parameters (None falls back to config values); the `plain_llm` baseline now builds a degraded graph directly — previously `importlib.reload` changed the global switches in the `run_benchmark` namespace, and after `workflow.py` re-ran `from config import` it still got the original values, so the switches actually did not take effect (plain_llm was actually running the full pipeline); `run_single_task` deepcopies the initial state per baseline and resets the disk instance files (the single_agent baseline writes repair code back to target_file, and with a shared state subsequent baselines would start from an already-repaired state); `run_benchmark` gained a `seed` parameter passed through to `SyntheticDataset` (previously hardcoded to 42, and `--seed` was silently ignored), and the result JSON records the seed
- **Aligned the SWE-bench download/loading paths**: `download_from_huggingface` previously wrote `~/.cache/aitester/swe_bench_instances.jsonl`, while the loader read `~/.cache/aitester/swe_bench/` — after downloading it could never be found. Now the default directory is aligned with the loader's data_dir, and the filename carries a subset marker (mini/lite/full no longer overwrite each other); the loader reads the dedicated file per subset, and when unspecified merges all subset files and dedupes by instance_id; `instance_code` priority is `instance_code > base_code > problem_statement` fallback
- **Data-loss protection in the batch config generator**: `generate_batch_config.py` and the embedded template, when the model list is empty, wrote `.env.local` in "w" mode, wiping all existing LLM config; now they report an error and exit (a subprocess regression test was added)

### Defect fixes
- **Error report context ineffective**: `ReportGenerator.generate()` previously used `classify() + context=None`; the ImportError root-cause / fix-suggestion branches (depending on `context.module_name`) were dead code, and `error_subtype` was always None. Now it wires up `classify_with_context`, and fixed the `.value` crash when `context.subtype` is None; `save_report` sanitizes the task_id that joins the filename with a whitelist + truncation (preventing path traversal); the classifier's traceback branch no longer mislabels pure runtime errors with the `SYNTAX_ERROR` subtype
- **RAG similarity stuck at 0.0**: in ChromaDB's cosine space, distance is not in metadatas; the old `meta.get("distance", 0.0)` always got the default value. Now `similarity = round(1 - distance, 4)` is converted from the query result's `distances` field
- **CLI robustness**: the module-import-time `FileHandler("aitester.log")` crashed the whole CLI with PermissionError under a read-only CWD; now it catches OSError and degrades to console-only; a coverage of 0.0 is legal data — three falsy checks that wrongly displayed N/A were changed to `is not None`
- **BaseAgent client reuse**: `__init__` previously created a new `ChatOpenAI` per instance (all production calls went through the cached client in `_call_llm`, and `self.llm` was actually a placeholder property); now it reuses the module-level cache; corrected the `_call_zai` docstring (in reality all retryable exceptions uniformly use a 5s-base backoff; the old comment did not match the implementation)

### Refactoring
- **`APIManger` → `APIManager`**: the misspelled class name was uniformly renamed (6 files in src/api, the `__init__` exports, and tests and examples); the background thread name was corrected in sync; no external users before 1.0, so no alias compatibility; the old spelling in the CHANGELOG history is preserved
- **Simplified the loading hack**: the duplicated `importlib + sys.modules` alias loading of `config.py` in `api_manager`/`config_manager` was changed to the ordinary `from config import` (no circular-import risk, and it eliminates two independent module instances)
- **Cleaned up CLI dead code**: removed the unreferenced `tqdm`/`TQDM_AVAILABLE` detection block and the re-exported `rich.progress` component

### Documentation and consistency
- **reproduce.sh**: created the unit-test tee directory upfront + pipefail tolerance; fixed the SWE-bench import path (`src.datasets.dataset_loader`); the environment validation changed from the deprecated `OPENAI_API_KEY` to `LLM_1_API_KEY`; Python 3.10+ → 3.12+ (required by the pinned dependency scipy==1.18.0)
- **`.env.example`**: `DOCKER_IMAGE` 3.11-slim → 3.12-slim (aligned with the pinned dependencies / config.py default / Dockerfile); the `DOCKER_ENABLED` comment truthfully notes that container isolation is not yet implemented (`use_docker` is a reserved interface)
- **Regression**: full suite **798 passed** (+11 new cases), 0 skipped, 1 warning (chromadb internal DeprecationWarning, third-party library); total coverage 83%; `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.2] - 2026-09-09

### CI gate fixes (main branch back to all green)
- **Fixed the ruff format gate turning red**: the main branch CI failed at the "Lint with ruff" step (`ruff format --check` required reformatting of the three files `src/agents/base_agent.py`, `src/cli/app.py`, `tests/test_cli_run.py`); the whole repo was re-run with `ruff format` to fix it
- **Pinned the ruff version in CI**: previously CI's `pip install ruff` installed the latest version, and when upstream releases changed the formatting rules the gate would turn red at random (the two adjacent CI runs on 2026-09-09 disagreeing was exactly this cause). Now pinned to `ruff==0.16.3` (consistent with `requirements.lock`); the lock is updated in sync when upgrading
- **Completed the DBUtils dependency declaration**: `src/db/mysql_client.py` uses `dbutils.pooled_db.PooledDB`, but it was not declared in `requirements.txt`/`requirements.lock`/`setup.py` — a fresh install in a clean environment would ImportError the `src.db` module. Now `DBUtils==3.1.2` is added, and a new `tests/test_mysql_client.py` (11 cases, mocking the connection pool to cover the singleton, commit/rollback, and CRUD on the three tables)

### Test quality improvements
- **Re-enabled the 6 LLM file-cache tests**: the 6 tests in `test_base_agent_extended.py` that were skipped on the grounds of "local import os/json cannot be patched" — their skip reason had become invalid after the source was refactored to module-level imports. Now implemented via the `AITESTER_LLM_CACHE`/`AITESTER_LLM_CACHE_DIR` environment variables: cache miss, hit, prompt mismatch, reading corrupt JSON, successful write, and write exception — all 6 paths covered (skips cleared to zero)
- **API manager thread-hygiene tests**: 5 cases added (singleton consistency, reset stops the health-check thread, concurrent get_manager yields a single instance, failover migration log)
- **Completed the report generator tests**: added `tests/test_report_generator.py` (44 cases); `src/reports/generator.py` coverage went from **0% to 100%**. Covers all branches of the four ErrorReport serializations (dict/text/markdown/json), the five major error-classification paths of generate(), the context branches of root-cause / fix-suggestion (context is always None inside `generate()`, so the private method must be called directly to construct an `ErrorContext` for coverage), the `_parse_failed_cases` parsing (including the name fallback to unknown boundary), and `save_report`'s three-format persistence and singleton semantics

### Defect fixes
- **API manager background thread leak**: `reset_manager()` previously only cleared the global reference; the background health-check daemon thread started by `APIManger`'s initialization (issuing a real LLM probe every 60s) lingered, continuing to consume API quota for the old instance. Now it calls the newly added `_stop_health_checker()` before reset to explicitly stop and wait for the thread to exit
- **Failover log error**: the "failover succeeded" log in `_try_call_node` previously printed the **current** node name twice (`%s -> %s` with the same value), so the migration path could not be seen. Now it records "previous node -> current node" via the `prev_model` parameter
- **Singleton thread safety**: `get_manager()` gained double-checked locking; concurrent multi-threaded calls create only one manager instance

### Code quality
- **Version number converged to a single source of truth**: `src/__init__.py` gained `__version__` (0.9.2); both `setup.py` and the CLI `--version` read from it, eliminating two hardcoded drift points
- **Pytest collection warning for RAG classes**: the `TestCaseRetriever` class name starts with Test, triggering `PytestCollectionWarning`; `__test__ = False` was added to silence it
- **Promoted magic numbers**: `_MAX_REPAIR_HISTORY` inside `workflow._patch_applier_node` was promoted to a module-level constant (with a comment)
- **Cleaned up redundant imports**: removed the duplicated `import ast` inside the method of `generator._validate_parametrize` (already imported at the top of the module)

### Documentation and consistency
- **Refreshed the README test status**: test count 708→787 passed, 0 skipped; the "latest optimization / recent changes" rows synced with this round's content
- **Corrected the outdated requirements.txt comment**: the CI Python matrix note 3.10-3.12 → 3.12-3.14; the ruff installation note changed to the pinned version
- **Regression**: full suite 787 passed, 0 skipped, 1 warning (chromadb internal DeprecationWarning, a third-party library issue); `ruff check` / `ruff format --check` / lock-sync validation all passed

## [0.9.1] - 2026-09-09

### CLI option inactivation fixes (state plumbing)
- **--timeout takes effect**: previously the value of `run --timeout` passed into `_run_single_task` was never used; the Executor read `os.getenv("EXECUTION_TIMEOUT", "30")` directly, bypassing the config's range validation. Now the new `execution_timeout` state field plumbs it through to `_executor_node` (priority: state injection > config.EXECUTION_TIMEOUT)
- **--coverage-threshold takes effect**: previously the option only did 0-100 validation and never participated in any judgment. Now the new `coverage_threshold` state field plumbs it through; the result dict gained `coverage_ok` (None when there is no coverage data, so it is not misjudged) and the `coverage_threshold` field; the text summary shows the target-met status

### Defect fixes
- **LLM config loading aborted on a number gap**: the original implementation of `config._load_llm_configs` did `break` at the first incomplete number, so removing a middle provider (e.g. LLM_2) silently disabled subsequent numbers (LLM_3+). Now it scans up to the limit of 32, skipping incomplete numbers, with the results kept in the original number order
- **Exponential backoff formula error**: the wait time in `base_agent._retry_with_exponential_backoff` was wrongly written as `base_wait**attempt` — with the default base_wait=1 it degenerated to a fixed 1s (not the documented 1s/2s/4s), and the zai path with base=5 inflated to 5s/25s/125s. Corrected to `base_wait * 2**attempt` (1s/2s/4s; zai 5s/10s/20s)
- **Executor import replacement wrongly hurt third-party libraries**: `_apply_import_replacements` previously used an unanchored regex for global replacement over **all** import statements; third-party libraries such as `import numpy` in the test code were wrongly rewritten to the module under test's name. Now the regex is anchored by module name, and a similarity gate (SequenceMatcher ≥ 0.6, e.g. calculater→calculator) replaces only typo variants of the target module name; the unused module-level regexes `_RE_FROM_REPLACE`/`_RE_IMPORT_REPLACE` were also removed as a side effect

### Code quality
- **De-duplicated CLI statistics**: the total/passed/failed of the `run` command were previously computed once in each of the JSON / non-JSON branches; merged into a single computation point
- **De-duplicated exception handling**: `future.exception()` in `_handle_task_exception` was reduced from two calls to one and logged
- **Minor executor optimizations**: the multi-directory injection in `_build_sys_path_code` no longer produces duplicate `import sys` lines; `_parse_coverage` preferentially scans only the TOTAL summary line (keeping the full-text scan fallback)
- **Regression**: 13 regression tests added (6 CLI state plumbing + 3 Executor import protection + 1 backoff formula + 3 config gap tolerance); full suite 721 passed, 6 skipped; ruff all green

## [0.9.0] - 2026-09-09

> Note: iterative work in the 0.4.0–0.8.0 era is recorded in the README's "Iteration optimization records" section; the CHANGELOG did not record every version. This is the most recent version release.

### CI compatibility and security scan fixes (2026-09-09)
- **Aligned the matrix with the locked versions**: the lock was generated from a Python 3.14 dev environment; `scipy==1.18.0` requires `>=3.12`, and `pandas/matplotlib` require `>=3.11`, so the locked version set could not be installed on the original matrix's 3.10/3.11. The matrix was narrowed to `['3.12', '3.14']` (lower bound + dev environment), and the Codecov upload condition was synchronously changed to 3.14
- **Migrated the security scan**: the deprecated `safety` tool (its `check` subcommand has been unsupported since 2024-06, exit code 64 on CI) was replaced with `pip-audit`, maintained by PyPA
- **chromadb vulnerability exemption (on record)**: `chromadb==1.5.9` hits PYSEC-2026-311 (=CVE-2026-45829), CVE-2026-45830/45831/45833 — 4 known vulnerabilities in total; no fixed version on PyPI (1.5.9 is the latest). CI explicitly ignores them with `--ignore-vuln` and a comment; **follow-up: upgrade immediately when chromadb releases a fix and remove the ignore**
- **Downgraded pytest-timeout 2.5.0→2.4.0**: 2.5.0 has been yanked upstream (reason "accidental breaking change (probably)"); the lock had mistakenly pinned that yanked version. Downgraded to the latest non-yanked 2.4.0 (verified the `--timeout` behavior with pytest 9.1.1 works normally); requirements/lock/local .venv synchronized in three places
- **Bumped action versions**: `checkout@v4→v5`, `setup-python@v5→v6` (eliminating the Node.js 20 deprecation warnings)
- **Fixed the root cause of the CI test-step failure**: a clean simulation without a local `.env.local` (mocking only `LLM_1_*`) reproduced the only failing case, `test_contains_expected_models` — it hardcoded an assertion that model names contain `qwen/deepseek/agnes/glm`, and CI's mock name `test-model` does not match (an environment-dependent test defect). Refactored into a structural check (model names correspond one-to-one with the configured LLMs) + `pytest.skip` when no real vendor config exists; the dev environment (real `.env.local`) behavior is unchanged
- **CI test-failure diagnostic annotation**: a new `if: failure()` diagnostic step; on failure it re-runs `pytest -q --tb=no -rf` to extract the FAILED/ERROR list and write `::error` annotations (the check-runs annotations API is publicly readable, no admin log download needed); the diagnostic step and the test step carry the same set of mock envs, avoiding false failures from the rerun

### CI lock consistency check (2026-09-09)
- **Added a lock-sync check**: `scripts/check_lock_sync.py` (pure stdlib) verifies that every dependency in `requirements.txt` exists in `requirements.lock` and its `==` pinned version matches the lock; CI gained a "Check lock sync" step that blocks merging when versions are out of sync
- **Verification**: deliberately changed the langgraph version to 9.9.9; the script correctly reported "version out of sync" and exited with code 1; passed after restoring it

### Performance optimizations (2026-09-09)
- **ChatOpenAI client reuse**: `base_agent._call_llm` previously created a new `ChatOpenAI` instance on every call (the underlying httpx connection pool was rebuilt with it, and TCP/TLS connections could not be reused). Added `_get_or_create_chat_client`, caching instances by `(model, temperature, api_key, base_url)` (cap 16, FIFO eviction), reusing connections in-process; the client is thread-safe and compatible with `--parallel` concurrency
- **zai path client reuse**: `_call_zai` previously created a new `ZhipuAiClient` on every call. After verifying that `ZhipuAiClient` inherits from the OpenAI SDK base class and shares a thread-safe `httpx.Client` underneath, added `_get_or_create_zai_client`, caching by `(api_key, base_url)` (model is a request parameter and not in the key)
- **Test isolation**: `tests/test_base_agent_extended.py` gained an autouse fixture that clears the two client caches, avoiding mock instances leaking across tests; 8 client-reuse unit tests added (4 ChatOpenAI + 4 zai, the latter tracking construction counts by injecting a fake `zai` module into `sys.modules`)
- **Regression**: 708 passed, 6 skipped

### CLI split and CI fixes (2026-09-09)
- **Split main.py into src/cli/**: the 507-line main.py was split into `src/cli/app.py` (command definitions and task execution) + `src/cli/output.py` (ANSI/Rich output utilities); main.py remains a thin entry, and the behavior of `python main.py ...` and the setup.py console script is unchanged; the `list-examples` path locating was changed to compute from the project root (before the split it used `__file__` pointing to the root directory)
- **Fixed the CI formatting gate**: `ruff format` unified across the whole repo (33 files, pure formatting changes); previously the `ruff format --check` step always failed
- **De-duplicated the CI install step**: `pytest-cov` is already pinned in requirements.txt; the duplicate install line in CI was removed
- **Regression**: 700 passed, 6 skipped; `python main.py --help` / `list-examples` smoke passed

### Dependency governance (2026-09-09)
- **Pinned the top-level dependencies**: the 18 top-level dependencies in `requirements.txt` were changed from `>=` to `==`, with versions synchronized to `requirements.lock`, guaranteeing reproducible installs in CI (the Python 3.10-3.12 matrix)
- **Installed the missing CI plugin**: added `pytest-timeout==2.5.0` (`--timeout=1200` in the addopts of `pyproject.toml` depends on it; the previous CI install step did not include it, and pytest failed to recognize the `--timeout` argument)
- **Removed an unused dependency**: `radon` has no import reference anywhere in the project; removed from `requirements.txt` and `setup.py` (a comment records it for reference)
- **Corrected an outdated comment**: `requests` is actually used by `scripts/check_quota.py`; the old "not directly used" comment was corrected

### Architecture refactoring and performance optimization (2026-09-09 continued)
- **Grouped modules into subpackages**: `dataset_loader`/`synthetic_dataset` → `src/datasets/`, `api_manager` → `src/api/`, `config_manager`/`config_generator` → `src/config/`, `exceptions` → `src/utils/`; all import references updated
- **Wired up the LLM file cache**: `base_agent._call_llm_with_cache` officially wired into planner/generator/debugger; identical prompts hit the cache and save tokens; added the `AITESTER_LLM_CACHE` switch and the `AITESTER_LLM_CACHE_DIR` directory (enabled by default, tests auto-isolated)
- **Rewrote llm_cache**: `src/graph/llm_cache.py` was changed from an empty shell to a usable thread-safe LRU, with accurate hit-rate statistics (an optional in-memory cache tool)
- **Added a quota-probe script**: `scripts/check_quota.py`, probing per model with a 1-token request for alive / 403 quota / rate limit / dead key, without printing keys
- **Updated the model catalog**: Agnes domestic site `agnes-2.5-flash` → `agnes-3.0-flash`; the default model `LLM_1` switched to `agnes-3.0-flash`
- **Fixed tests**: fixed dataset_loader interface / environment-dependent / download mocks; full suite 700 passed, 6 skipped, 0 failed
- **Documentation**: README/QUICKSTART/docs synchronized architecture, cache, scripts, and models; `.gitignore` added `src/cache/`, `.env.local.bak`

### Code optimization (2026-09-09)
- **Extracted the common utility module**: added `src/utils/helpers.py`, unifying the code-block and JSON extraction logic
  - `extract_code_block()`: extracts a code block from LLM output (supports multiple formats)
  - `extract_json_object()`: extracts a JSON object from text (including the bracket-balancing method)
- **Refactored base_agent.py**: removed duplicate code, delegating to the common utility functions (-85 lines)
- **Refactored patch_applier.py**: replaced `_extract_patch_code()` with the common utility functions (-34 lines)
- **Optimized workflow.py**:
  - Removed the redundant constant `_DEFAULT_MAX_ITERATIONS`
  - Simplified the path safety-check logic (using a tuple instead of a list)
  - Improved type annotations
- **Fixed tests**: updated the test files to adapt to the new import paths
- **Test results**: 524 passed, 6 skipped (core modules 100% passing)

---

### Code quality optimization
- **Fixed the code-convention issues**: all E501 (line length) and C901 (complexity) issues fixed
- **Refactored config_manager.py**:
  - Extracted the `_is_model_config_line()` helper function
  - Extracted the `_is_model_comment()` helper function
  - Extracted the `_find_and_remove_model_block()` helper function
  - Reduced the complexity of `remove_llm_config()` (11→9)
- **Refactored dataset_loader.py**:
  - Extracted the `_load_project_version()` method
  - Reduced the complexity of `Defects4JPYDataset._load_raw_data()` (13→9)
- **Fixed the test files**:
  - Simplified the sys.path imports in test_debugger.py
  - Fixed the line length in test_error_classifier.py
  - Fixed the long list definition in test_rag_retriever.py
  - Fixed the test logic in test_dataset_loader.py

### Test status
- Total test count: 686
- Passed: 551 (core tests)
- Skipped: 6
- Failed: 5 (network timeouts, dataset download tests)
- Coverage: 70% (core modules 85%+)

### Code conventions
- ✅ Ruff check all passed
- ✅ Line length ≤ 120 characters
- ✅ Code complexity meets the requirements

---

## [0.3.0] - 2026-08-18

> Note: this section's work was completed on 2026-08-18, but had stayed under [Unreleased] without a version release all along; it was back-logged as 0.3.0 during the 2026-09-09 cleanup and archived together with 0.9.0.

### Full functional validation (2026-08-18)
- **Test results**: 873 test cases collected, 860 passed (98.6%), 12 failed (known boundary issues), 1 skipped
- **Validation scope**: unit tests + integration tests + CLI end-to-end + module imports + experiment scripts
- **Passed modules**:
  - CLI: the `run` and `list-examples` commands work normally
  - Agent layer: BaseAgent(46), ExecutorAgent(30), PlannerAgent(5), ErrorClassifier(44), GeneratorAgent(7), DebuggerAgent(5)
  - Tool layer: CodeAnalyzer(12), PatchApplier(33)
  - Workflow layer: workflow(63), state(5), llm_cache(24)
  - Integration tests: integration(52), e2e(34), examples(90)
  - API manager: APIManager(50, including the large-scale 22-node test)
  - RAG retriever: retriever(16), report_generator(43)
  - Datasets: dataset_loader_extended(33), synthetic_dataset(40)
  - Experiment scripts: run_benchmark/run_large_scale/visualize_results/statistical_analysis/analyze_failures all usable
- **Known failures**:
  - 6 in `test_retriever_extended.py` (Python 3.14 MagicMock behavior changes)
  - 2 in `test_base_agent_zai.py` (API quota exhausted)
  - 3 in `test_dataset_loader.py` (HuggingFace mock configuration)
  - 1 in `test_concurrent_execution_safety` (randomness, passes on rerun)
- **Detailed report**: `FUNCTIONAL_VALIDATION_REPORT_20260818.md` (the file is no longer in the repo; kept as a record only)

### New features
- **API manager enhancements**: added the `src/api_manager.py` module, supporting multi-provider polling and high-availability failover
  - Implements four strategies: round-robin, weighted random, health-aware, and fastest-first
  - Supports dynamic node addition/removal
  - Automatic health checks and failover
  - Added 31 unit tests covering the full functionality
- **LLM cache mechanism**: implemented `src/graph/llm_cache.py`, supporting caching of LLM call results
  - Reduces duplicate API calls, saving token consumption
  - Provides a cache statistics interface
- **Error report generator**: added the `src/reports/` module, supporting the transformation of test-failure information into structured diagnostic reports
  - Supports text, JSON, and Markdown output formats
  - Automatically classifies error types (syntax/runtime/assertion/timeout/unknown)
  - Generates root-cause analysis and fix suggestions
  - Integrates `ErrorClassifier` for error classification
  - Added 13 unit tests covering the full functionality
- **Multi-LLM config support**: the `LLM_CONFIGS` list supports API key polling and high availability
  - Config format: `LLM_N_API_KEY`, `LLM_N_BASE_URL`, `LLM_N_MODEL_NAME`
  - Backward compatibility: the old variable names such as `MODEL_NAME`, `OPENAI_API_KEY` are retained

### Code quality
- **Ruff code formatting**: fixed 791 code-style issues (import ordering, blank lines, outdated type annotations, etc.)
- **Modernized type annotations**: replaced `Optional[X]` with `X | None`, following the Python 3.10+ style

### Engineering improvements
- **Ruff Lint configuration**: added `pyproject.toml`, configuring ruff for checking and formatting (replacing flake8 + isort)
- **Pre-commit hooks**: added `.pre-commit-config.yaml`, integrating checks such as ruff, mypy, and trailing-whitespace
- **GitHub Actions CI**: added `.github/workflows/ci.yml`, supporting multi-Python-version tests, lint checks, and security scanning
- **pytest configuration**: configured the pytest parameters (test paths, markers, output format) in `pyproject.toml`

### Performance optimizations
- **Singletonized the RAG retriever**: changed the ChromaDB client to a lazy-loading singleton pattern (`src/graph/workflow.py`), saving 2-6 seconds of initialization per task
- **Wired up the LLM_TIMEOUT config**: wired `LLM_TIMEOUT` into `src/agents/base_agent.py`, preventing LLM calls from hanging
- **Supported concurrent execution**: implemented `BENCHMARK_PARALLELISM` environment-variable-driven multi-threaded parallel benchmarking (`experiments/run_benchmark.py`)
- **Optimized the Parametrize retry logic**: fixed the issue in `src/agents/generator.py` where parametrize validation failure retried with the same query; now it appends a negative-feedback prompt
- **Optimized the Executor import path search**: limited the full rglob walk of `_auto_fix_imports`, preferring to check common paths (`src/`, `lib/`, the current directory); 98.6% improvement

### Bug fixes
- **Exponential backoff retry logic**: fixed the retry backoff strategy in `src/agents/base_agent.py`
- **Path safety check**: strengthened the path validation in `src/tools/patch_applier.py` against path traversal attacks
- **Optimized the module import path search**: limited the full rglob walk of `_auto_fix_imports`, preferring to check common paths (`src/`, `lib/`, the current directory)

### Documentation updates
- **README.md**: added a performance-optimization section, covering the RAG singleton, the LLM_TIMEOUT config, and a concurrency usage guide
- **README.md**: updated the quick-start section, adding a concurrent execution command example
- **README.md**: updated the config description table, adding the LLM_TIMEOUT and LLM_RETRY_WAIT config items
- **README.md**: updated the iteration optimization records, adding the v0.10 and v0.9 change records
- **README.md**: updated the test status table, reflecting the latest test results (696+ passed)
- **CHANGELOG.md**: added the multi-LLM config support notes
- **New documents**: `docs/performance_optimization_report.md`, `docs/report_generator_guide.md`, `API_MANAGER_EXTENSION_GUIDE.md` (that batch of files was later cleaned out of the repo; kept here as a historical record only)
- **Iteration reports**: `ITERATION_REPORT_20260818.md`, `FINAL_ITERATION_SUMMARY.md`, `ITERATION_REPORT_ROUND2.md` (that batch of files was later cleaned out of the repo; kept here as a historical record only)
- **Architecture doc**: updated `docs/algorithm_design.md` to reflect the RAG singletonization changes

## [0.2.0] - 2026-08-17

### Engineering improvements
- **Ruff Lint configuration**: added `pyproject.toml`, configuring ruff for code checking and formatting
- **Pre-commit hooks**: added `.pre-commit-config.yaml`, integrating checks such as ruff, mypy, and trailing-whitespace
- **GitHub Actions CI**: added `.github/workflows/ci.yml`, supporting multi-Python-version tests, lint checks, and security scanning
- **pytest configuration**: configured the pytest parameters (test paths, markers, output format) in `pyproject.toml`

### Documentation updates
- **README.md**: updated the test status table; the integration tests are marked as passing (52 passed)
- **README.md**: added a "Development tools" section, including Ruff lint, Pre-commit hooks, CI/CD, and test command notes
- **CHANGELOG.md**: updated to follow the Keep a Changelog format convention

### Test status
- Unit tests: 215 passed (including the integration tests)
- No hardcoded keys
- Code coverage 75% (target 80%+)

---

## [0.1.0] - 2026-08-14

### Added
- Initial version release
- Four-agent collaboration architecture (Planner → Generator → Executor → Debugger)
- Supports the examples, synthetic, and swe_bench datasets
- One-click Docker reproduction support
- Complete unit tests (185 cases, 17 test files)

---

## Version notes

- `Unreleased`: features currently in development, not yet officially released
- Version numbers follow [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)
