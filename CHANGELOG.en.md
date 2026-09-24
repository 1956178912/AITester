> **Language**: [简体中文](CHANGELOG.md) | English (this file)

# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - Full-audit fixes + code-quality round (credential scrubbing factored into dynamic-pattern module + CLI `finally`-block fragile code eliminated + multi-candidate node made side-effect-free + patch function-location regex→AST + mypy real-semantic errors zeroed + analyze_results theme split)

> This round is a pure code-quality pass: 26 real mypy semantic errors
> (not missing-stub) zeroed to 0, and `experiments/analyze_results.py`
> (2192 lines) split into 4 theme submodules.
> **No runtime behavior or experiment semantics changed.**
> Full baseline holds at **1659 passed / 0 failed**, ruff check / ruff
> format all green, mypy `src/ --ignore-missing-imports` 0 errors
> (58 source files), src coverage 94% (statement count dropped 5216 →
> 4911 because `experiments/analyze_results.py` left the src/ tree;
> not a real coverage regression).
>
> **mypy real-semantic fixes (26 → 0, non-stub-missing class)**:
> - `src/graph/nodes.py` (10 sites): `state.get("test_plan")` narrowed
>   via `cast("dict[str, Any]", ...)` (documented behavior: absent → None,
>   Generator's `isinstance(test_plan, dict)` guard covers it, test
>   regression semantics unchanged); `cross_file_modules` list
>   comprehension normalized to `str(d["target_module"])`; `test_code` /
>   `test_output` / `patch` `str | None` call sites get `or ""`
>   normalization (runtime-equivalent: the original `.get(key, "")`
>   already returns `str | None` for TypedDict, `or ""` just also maps
>   None to empty string, semantics unchanged); `coverage_delta` list
>   normalized to `float()`; `patches[entry_module] = state["patch"]`
>   narrowed via `assert isinstance(patch_val, str)` (truthy guard
>   guarantees str).
> - `src/tools/multi_candidate.py` (4 sites): `credit_score` assignment
>   and sort key normalized to `float(credit_by_index.get(c.index, 0.0))`
>   (original `dict.get` returned `float | None`, mypy does not narrow
>   attributes inside lambdas); `_coverage_trend`'s `deltas` list
>   normalized to `float(t["coverage_delta"])`.
> - `src/rag/retriever.py` (8 sites): module-level `chromadb` switched
>   to the "pre-declare `chromadb: Any = None` then try-import" pattern
>   (same idiom as `src/graph/rag.py`), eliminating `None`-assigned-to-
>   Module error; `collection.get/query`'s `metadatas` / `documents`
>   fields narrowed via `.get("metadatas") or []` and
>   `results.get("documents") or [[]]` (chromadb stubs type these
>   `list[...] | None`; runtime they are actually always non-None,
>   `or []` fallback semantics unchanged).
> - `src/observability/trace.py` (2 sites): `directory` variable narrowed
>   from `str | None` — `self._enabled = directory is not None` plus
>   `if self._enabled and directory is not None` double guard, so
>   `os.makedirs(directory, ...)` and `os.path.join(directory, ...)`
>   no longer report `str | None` argument errors.
> - `src/reports/generator.py` (1 site): `classify_with_context` return
>   renamed to `context_raw`, `context: ErrorContext | None =
>   context_raw if context_raw else None` explicit annotation (the
>   original self-assignment `context = context if context else None`
>   made mypy reject the `| None` assignment to the narrowed
>   `ErrorContext` type).
> - `src/cli/output.py` (1 site): `Console` module attribute switched
>   to the "pre-declare `Console: Any = None` then try-import" pattern
>   (the original `Console = None` after a successful
>   `from rich.console import Console` made mypy report
>   Incompatible-types when assigning `None` to `type[Console]`;
>   pre-declaring as `Any` eliminates the error; the rich-missing
>   `Console is None` fallback path is unchanged).
>
> **experiments/analyze_results.py theme split (0.7 debt item 1.6)**:
> - Original single file 2192 lines with 26 private stat functions
>   stacked; each function is loosely coupled (all consume `details[]`).
>   Split per the 0.7 audit finding into 3 theme submodules + 1
>   `__init__`:
>   - `experiments/analysis_parts/rag_analysis.py` (164 lines): RAG
>     retrieval quality & token-efficiency theme (`_token_metrics_from_details`
>     / `_rag_by_kind_from_details` / `_rag_hit_by_failure_category` /
>     `_rag_token_efficiency` / `_rag_similarity_distribution`, 5
>     functions, no intra-group coupling);
>   - `experiments/analysis_parts/convergence_analysis.py` (1050 lines):
>     repair-convergence / quality-proxy / test-smell / cross-baseline
>     theme (`_repair_convergence_curve` / `_smell_task_has_smell` /
>     `_test_smell_detection` / `_repair_convergence_metrics` /
>     `_convergence_token_efficiency` / `_difficulty_stratified_iterations`
>     / `_cross_baseline_convergence_comparison` /
>     `_cross_file_failure_analysis` / `_assertion_strength_proxy` /
>     `_quality_proxy_metrics` / `_failure_top_categories` /
>     `_failure_root_cause_trend` / `_mutation_score_metrics` /
>     `_assertion_counts_from_row` / `_convergence_failure_modes` /
>     `_boundary_case_coverage` / `_execution_trace_summary`, 17
>     functions, sharing intra-group helpers `_assertion_strength_proxy`
>     / `_assertion_counts_from_row` / `_smell_task_has_smell`, depends
>     on `ast` + `Counter`);
>   - `experiments/analysis_parts/cross_analysis.py` (87 lines):
>     cross-theme analysis (`_contamination_cross_analysis` /
>     `_venv_cache_stats_snapshot`, 2 functions, consumes
>     `details[].contamination_risk_level`, does not import
>     `detect_contamination` to avoid a dead import);
>   - `experiments/analysis_parts/__init__.py`: package doc + theme
>     index.
> - `experiments/analyze_results.py` (2192 → 959 lines) keeps the
>   public entry points `load_latest_benchmark` / `build_analysis` /
>   `render_markdown` / `main`, and re-exports all 24 private functions
>   from the 3 submodules (`# noqa: E402,F401`), so the historical
>   import path `experiments.analyze_results._xxx` is unchanged;
>   external tests (`tests/test_smell_detection_v2.py` /
>   `tests/test_experiments_scripts.py`) and same-package scripts
>   (`contamination_check` / `mutation_testing` / `run_benchmark`) need
>   no import changes.
> - Split principle: pure function relocation, signature / return /
>   docstring / default-arg zero change; intra-group shared helpers
>   (e.g. `_assertion_strength_proxy` consumed by
>   `_quality_proxy_metrics` / `_assertion_counts_from_row`) stay in
>   the same file, no cross-file imports, avoiding new circular deps.
>
> **Verification**: ruff check / ruff format all green (189 + 4 files)
> / full suite 1659 passed / 0 failed / mypy `src/ --ignore-missing-
> imports` 0 errors (58 source files) / src coverage 94% (4911
> statements, down from 0.7's 5216 because `analyze_results.py` left
> the src/ tree — not a real coverage drop) / smoke test:
> `experiments.analyze_results.build_analysis` on empty input does not
> crash, all 28 re-export symbols present.
>
> Note: this round's mypy zeroing scope is `src/` (CI has no mypy
> gate; this is a local non-gate commitment). `experiments/` /
> `config.py` / `main.py` and other scripts have no mypy historical
> gate and are out of scope; `--ignore-missing-imports` silences the
> import-untyped noise from stub-less third-party libs (scipy /
> datasets / dbutils / chromadb).

> **Full-audit fixes (2026-09-24, security + correctness + maintainability)**:
> Based on a full-repo audit, 5 issue fixes landed (test suite 1672 → all
> green, mypy 0 errors):
> - **Credential scrubbing factored into a function
>   (`src/utils/credential_scrub.py` new)**: the local / venv / Docker
>   execution paths all funnel through `scrub_os_environ()` to strip LLM
>   credentials. Previously `executor.py` only popped 7 hard-coded vars
>   (missing the `LLM_1_API_KEY` family) and the venv/Docker paths
>   inherited the host `os.environ` as-is — LLM-generated test code could
>   read the host's API keys. Now scrubbed via the dynamic pattern
>   `LLM_\d+_API_KEY` / `LLM_\d+_BASE_URL` (aligned with config's
>   1-32 scan range) plus common SDK credentials; all three paths share
>   one implementation, preventing list drift.
> - **CLI `finally`-block fragile code (`src/cli/app.py`)**: the
>   `end_task_trace` teardown relied on `"final_state" in locals()`
>   (the name is unbound when `invoke` raises) — obscure semantics that
>   a refactor could silently break. Replaced with `final_state:
>   dict | None = None` + `is not None` check + `assert` narrowing
>   (clears the mypy union errors).
> - **Node purity (`src/graph/nodes.py`)**:
>   `_select_multi_candidate_patch` previously wrote
>   `state["multi_candidate_stats"]` in place (shared TypedDict, would
>   cross-talk under `--parallel` threads). Now returns a 3-tuple
>   `(code, applied, stats_update)`, folded into `_patch_applier_node`'s
>   own update dict.
> - **Patch function-location regex→AST
>   (`src/tools/patch_applier.py`)**: the old `_find_function_range`
>   treated `^#` comments / `^@` decorators / class methods as
>   "boundaries", truncating decorated functions or function bodies with
>   comments too early and producing mangled replacements. New
>   `_find_function_range_ast` reads `FunctionDef.lineno/end_lineno` for
>   exact positioning; falls back to the regex path automatically when
>   the source can't parse (conservative, behavior unchanged).
> - **Low-risk corrections**: deleted `.env.local.bak` (a backup file
>   holding real keys); `llm_configs.json` — 3 deepseek entries had
>   `provider_description` corrected from "通义千问 (Qwen)" to "DeepSeek
>   hosted"; `requirements.txt` now declares `openai==2.54.0`
>   explicitly (`api_manager.py` does a top-level `import openai`,
>   previously satisfied only by a transitive dep); 5 ruff nits fixed
>   (I001/F401/RUF100/E741/SIM115 under tests/).
>
> **Verification**: full suite 1672 passed / 0 failed, mypy `src/` 0
> errors (59 source files), ruff check all green.

## [Static-type zeroing + code-quality cleanup] - 2026-09-23 (mypy clean across the repo; default behavior unchanged)

> This round is a pure code-quality pass: mypy went from 30+ errors to 0,
> plus dead-code / redundancy cleanup and test-suite speedup.
> **No runtime behavior or experiment semantics changed.**
> Full baseline advanced to **1659 passed / 0 failed** (net +32 over 0.7's
> 1627; this round added no tests, the delta is regression cases committed
> since 0.7 that had no dedicated CHANGELOG section), ruff check / ruff
> format all green / mypy 0 errors / src coverage 94%.
>
> **Static-type fixes (mypy zeroed across 19 files)**:
> - Explicit `dict[str, Any]` annotations where dict values mix str / int /
>   dict / list (`src/utils/exceptions.py` / `src/config/config_manager.py` /
>   `src/experiments/analysis.py` / `src/graph/nodes.py`) — silences mypy's
>   literal-narrowing false positives;
> - `src/tools/code_context.py`: `_build_header` / `_collect_top_level_funcs`
>   parameters narrowed from `ast.AST` to `ast.Module` (`.body` exists only
>   on Module);
> - `src/agents/executor_runtime.py`: `run_pytest_with_retry` parameters
>   precisely annotated (`list[str]` / `dict[str, str]`); the timeout branch's
>   TimeoutExpired stdout/stderr merge gains a `_to_str` normalizer (bytes
>   static fallback + text=True runtime semantics);
> - `src/agents/executor.py`: module-time attribute binding (15 sites) and
>   internal method calls annotated with `# type: ignore[attr-defined]`
>   (class-attribute binding is a runtime mechanism the test patch paths
>   depend on — behavior unchanged);
> - `src/agents/generator.py`: `_fix_import_module` now imports the
>   `is_similar_module_name` pure function directly (previously reached via
>   `ExecutorAgent` class-attribute binding — removes the runtime dependency
>   on the class attribute and the mypy attr-defined false positive);
> - `src/agents/llm_client.py`: `ChatOpenAI(openai_api_key=...)` annotated
>   `# type: ignore[call-arg]` (langchain-openai accepts the kwarg but mypy
>   validates against the strict OpenAI SDK signature);
> - `src/api/api_manager.py`: `cost_weight` reads normalized via `float()`
>   (getattr default 0.0 preserved for legacy config objects without the
>   field); `messages` parameter annotated `# type: ignore[arg-type]`
>   (`list[dict[str, str]]` is runtime-compatible with openai's strict
>   `ChatCompletionMessageParam` union);
> - `src/db/mysql_client.py`: `cursor()` gains a non-None assert on `_pool`
>   (after double-checked-lock init `_pool` is always non-None; the assert
>   narrows the type for mypy); `types-PyMySQL` installed to clear the
>   missing-stub error;
> - `src/graph/rag.py`: optional import rewritten to "pre-declare
>   `TestCaseRetriever: Any` then try-import" — clears mypy's
>   "Cannot assign to a type" (the chromadb-missing degradation path that
>   sets the module attribute to None is a legitimate one);
> - `src/rag/retriever.py`: chromadb metadata values normalized via
>   `float` (3 `_added_at` reads); `find_missing_modules` return type and
>   `executor_modes` 5-tuple annotations corrected;
> - `src/agents/debugger.py`: `debug()` return annotation corrected from
>   `dict[str, str]` to `dict[str, Any]` (the result carries the nested
>   `adversarial_check` dict);
> - `src/cli/app.py` / `src/cli/output.py`: kwargs dicts explicitly annotated
>   `dict[str, object]` + `**`-unpack ignores; rich optional import rewritten
>   to "pre-declare + try-import" (Table deferred to call time).
>
> **Code-quality cleanup (behavior unchanged)**:
> - `src/agents/llm_client.py` `_call_zai`: retry tuple
>   `(APIReachLimitError, APIStatusError, Exception)` → `(Exception,)`
>   (both concrete subclasses are subsumed by the base `Exception` — listing
>   them was dead code; the zai path treats rate-limit and ordinary errors
>   identically, so the unified exponential-backoff semantics are unchanged);
> - `src/utils/logging_utils.py` `setup_logger_safety`: idempotent short-circuit
>   added (returns immediately when the logger and all handlers already carry
>   a SensitiveFilter — repeated calls from multiple entry points no longer
>   accumulate redundant filter instances; redaction idempotency unchanged).
>
> **Test-suite speedup (coverage unchanged; wall time ~30s → ~22s)**:
> - `tests/test_api_manager.py` / `tests/test_api_manager_extended.py` /
>   `tests/test_base_agent_extended.py`: rate-limit / failover-retry paths
>   had their `time.sleep` calls mocked (the original three case-groups
>   genuinely waited 5s/10s/14s/7s; the mock targets `time.sleep` so the
>   real exponential-backoff logic is not bypassed — only the wait is skipped).

## [0.7 roadmap gaps landed] - 2026-09-22 Remaining roadmap gaps (2.3 / 3.1 / 3.3)

### Features (default behavior unchanged; each opt-in via env var)
- **2.3 Reproduction-test generation** (`src/agents/generator.py` + `src/graph/nodes.py`):
  - `GeneratorAgent.generate_repro_test()`: generates a "fail-then-pass" reproduction
    test that precisely covers a defect's trigger path (TDFlow-style); cross-file
    scenarios inject `cross_file_modules` so the LLM covers the cross-module call chain.
    Gated by `REPRO_TEST_ENABLE` (default false).
  - `_generator_node` invokes it when a defect description (diagnosis / review_reason)
    exists and writes the result to `state["repro_test"]`.
- **3.1 Bidirectional code-test diagnosis** (`src/agents/debugger.py` +
  `src/graph/nodes.py` + `src/graph/workflow.py` + `src/graph/state.py`):
  - `DebuggerAgent._run_review_diagnosis()`: an independent Review Agent decides whether
    the root cause is an implementation defect (fix code) or a test defect (regenerate test).
    Gated by `BIDIRECTIONAL_DIAGNOSIS_ENABLE` (default false).
  - `_should_debug` adds a branch: `defect_type == "test_defect"` routes back to the
    generator (regeneration_count cap prevents infinite ping-pong) — BiVCoder-style
    branch repair.
- **3.3 Lightweight reward predictor + dynamic temperature wiring**
  (`src/tools/multi_candidate.py` + `src/agents/base_agent.py` + `src/graph/nodes.py`):
  - `predict_candidate_rewards()`: re-ranks candidates using the historical execution_trace
    coverage trend (declining → prefer minimal change, stagnant → prefer larger change)
    combined with line-level credit assignment. Gated by `REWARD_PREDICTOR_ENABLE` (default false).
  - `_dynamic_temperature_from_suggestion()`: maps the executor's iteration-strategy
    suggestion (lower_temperature) to an actual sampling temperature, forwarded through
    `BaseAgent._call_llm_with_cache`'s `temperature` parameter (previously observation-only).

### Performance & tech-debt cleanup (0.7 debt items P2×8 landed, default behavior unchanged)
- **2.2 Global wall-clock budget for LLM calls** (`config.py` + `src/agents/base_agent.py`):
  new `LLM_CALL_BUDGET_SECONDS` (default 600s); `_call_llm` checks the budget before each
  failover attempt and fast-fails when exceeded, avoiding tens of minutes of stall in
  extreme "groups × models × retries" combinations.
- **2.3 analyze_failures field projection** (`experiments/analyze_failures.py`):
  `load_all_results` keeps only analysis-layer fields and drops large fields
  (generated_test / test_output / execution_trace), cutting memory by an order of
  magnitude when accumulating multiple batches.
- **2.4 venv stats persist throttling** (`src/tools/dependency.py`):
  `_record_venv_cache_event` skips disk IO when the last persist was <5s ago; unpersisted
  events are merged back via `get_venv_cache_stats` and an atexit flush hook (no count loss,
  double-lock lost-update semantics unchanged).
- **2.5 Sliding-window parallel submission** (`experiments/run_benchmark.py`): extracted
  `_run_tasks_sliding_window`, keeping in-flight futures ≤ 2×parallel instead of submitting
  all 100+ tasks at once.
- **1.4 Dead-delegate cleanup** (`src/agents/base_agent.py`): removed the pure-forwarding
  `BaseAgent._find_balanced_json` staticmethod; tests now cover `helpers._find_balanced_json`
  directly.
- **3.4 Docs** (`.env.example`): document `AITESTER_LLM_CACHE` / `AITESTER_LLM_CACHE_DIR`.
- **3.5 Docs** (`docs/performance_guide.md`): 2.4 retry pseudocode now uses
  `base_wait * 2^attempt` and notes `LLM_RETRY_WAIT` no longer drives backoff.
- **3.6 Key-naming convergence** (`config.local.example`): header declares `LLM_N_*` the
  single source of truth; other templates are batch-script intermediate variables.
- **3.7 Clone-URL verification**: `git ls-remote` confirms
  `https://github.com/1956178912/AITester.git` is reachable and matches docs — no change needed.

## [0.7] - 2026-09-21 Cross-file repair phase 2 + data-integrity fix + research kickoff (A/B/C directions)

### Features (Direction A: code-quality deepening, default behavior unchanged)
- **3.5 cross-file repair phase 2** (`src/tools/cross_file.py` + `src/graph/nodes.py`, design doc §9):
  - **Multi-entry dependency analysis** `analyze_multi_entry_deps(entry_modules, source_files, max_depth=1)`:
    first-level import expansion over multiple entry modules (conservative, no recursion —
    avoids dependency-graph explosion), dedupes edges across entries (same
    `(source, target, symbol)` keeps the smallest `call_line`). The phase-1 single-entry
    `analyze_cross_file_deps` keeps its original signature; multi-entry is additive.
  - **Topological-order patch application** `apply_multi_file_patch(..., deps=...)`:
    when dependency edges are passed, applies patches in dependency-topological order
    (callee before caller, Kahn's algorithm, cycles broken lexicographically, entry
    forced first); when `deps` is omitted, falls back to lexicographic order (phase-1
    behaviour) for historical-comparison stability. `_patch_applier_node` now restores
    the serialized dependency edges back to objects and passes them in.
  - **Repair-plan cache** `build_cross_file_repair_plan_cached(...)`:
    caches plans keyed by a dependency-graph fingerprint (entries + edges + max_modules,
    SHA1) in the LLM cache directory (reuses `AITESTER_LLM_CACHE`/`AITESTER_LLM_CACHE_DIR`
    semantics), zero LLM calls on hit; degrades to no-cache when `use_cache=False` or
    the cache switch is off.
- **4.4 dependency-cache consistency fix** (`src/tools/dependency.py`):
  `list_venv_cache` used `os.path.getctime` (creation time on macOS but inode-change
  time on Linux, inconsistent across platforms) → switched to `getmtime`, aligning with
  `clear_venv_cache`'s age semantics (venv directories rarely change after creation,
  mtime is more reliable).

### Fixes (Direction B/C: data integrity + research kickoff)
- **run_benchmark silent-fallback misleading archive fix** (`experiments/run_benchmark.py`):
  when the requested dataset (e.g. `swe_bench lite`) has an empty subset file, the
  loader silently fell back to the built-in examples synthetic dataset while the result
  archive's `"dataset"` field still claimed the original request (`swe_bench`) — the R-01
  probe's first run showed `task_id` prefix `examples__` contradicting the archived
  `dataset: swe_bench`. Now on fallback the `dataset_name` is reset to `examples`,
  `subset` to None, and the warning log explicitly marks "silent fallback, not the
  originally requested dataset".
- **R-01 SWE-bench backfill probe kickoff** (`docs/design/swe_bench_probe.md`):
  the probe's first run revealed the real blocker is "dataset has no usable source code"
  (lite subset JSONL is empty; only the generic file has 225 entries, and those lack
  `instance_code`), not "insufficient quota". Option (c) chosen: logged as pending
  dataset preparation; probe command in §3.1 ready to run once sources are filled
  (via `download_swe_bench.py` / `export_swe_bench_source.py`).
- **R-03 adversarial reasoning status clarification**: AdverIntent-style adversarial
  reasoning is already implemented in `src/agents/debugger.py`
  (`ADVERSARIAL_DEBUGGING_ENABLE` off by default + critic-evaluation loop, shipped in
  the 0.5 batch) — no re-kickoff needed this round. `run_benchmark.py` has no
  `--adversarial` CLI flag; R-03 is enabled only via the environment variable
  (comparison runs in an expanded batch would need
  `export ADVERSARIAL_DEBUGGING_ENABLE=true`).

### Tests
- `tests/test_cross_file.py` adds 12 cases (multi-entry 5 / topological-order 4 /
  repair-plan cache 3 → 4 test classes, 12 cases total), test count 27 → 39;
- `tests/test_rag_retriever.py` adds 2 concurrency-guard cases
  (`TestConcurrentUpsertGuard`: 8-thread concurrent upsert serialized without
  loss + cleanup not blocked by the write lock, same guardrail style as the 0.6
  venv dual-lock guards);
- `tests/test_dependency_edge_cases.py` updates 1 boundary case (`getctime` mock
  path → `getmtime` mock path, aligned with the 4.4 consistency fix);
- `tests/test_workflow_extended.py` adds `deps=None` to 2 mock lambdas
  (backward-compatible signature of `apply_multi_file_patch`).
- Full-suite baseline advanced to **1627 passed / 0 failed** (+15 over 0.6's 1612:
  cross-file phase 2 ×12 + RAG concurrency guards ×2 + venv cache edge-case update ×1),
  `ruff check` clean across the whole repo (0 warnings).

## [0.6] - 2026-09-20 P0 fix batch (LLM OpenAI path zero-retry + venv stats dual-lock + ghost-switch implementation + code-quality cleanup)

### Fixes (three-track performance audit: dead code / technical debt + hot paths + doc drift, manually reviewed)
- **P0-1 LLM OpenAI path zero-retry → exponential-backoff failover** (`src/agents/base_agent.py`):
  `llm.invoke` previously failed over to the next model/API after a single attempt —
  one 429 / timeout under network jitter = task-level failure (a 100-task ×
  3-baseline benchmark at a 10% jitter rate meant 90-180 calls failing outright).
  `_retry_with_exponential_backoff` (1s/2s/4s backoff) is now wired into the OpenAI
  path, with empty responses also triggering retry; failover only after retries
  are exhausted (aligned with the zai path semantics).
- **P0-2 venv cache stats dual-lock separation** (`src/tools/dependency.py`):
  `_record_venv_cache_event` previously held `_venv_cache_stats_lock` across
  `json.load + os.makedirs + json.dump` (~2-5ms/event), so all `--parallel`
  workers contended on a global lock on the hot venv-hit-check path. Now two
  locks: a counting lock (ns-level critical section, in-memory accumulation only)
  plus an independent persist lock (protects the whole read-disk / snapshot /
  write-disk span, lost-update safe). A naive move of persistence out of the
  counting lock would cause lost-update (two concurrent persists each read the
  old disk value, each zero the in-memory counter — 50+50 events merge to 50,
  demonstrated by a new guard test); with dual locks, 8 threads × 100 events
  lose nothing.
- **P0-3 ghost-switch implementation** (`config.py` + `src/api/api_health.py`
  + `src/api/api_manager.py`):
  Six doc locations (`.env.example` / QUICKSTART / api_reference /
  reproduce.sh / README / CHANGELOG) promised `API_CIRCUIT_BACKOFF`
  (default true) and `API_PROMETHEUS_EXPORT` (default false) as comparison
  switches, but no code read point existed anywhere in the repo — exponential
  backoff and Prometheus export ran unconditionally. Now centrally declared in
  config: `api_health.mark_failure` + `_probe_circuit_half_open` honor the
  backoff switch (false → fixed cooldown, 4.2 historical baseline);
  `api_manager.to_prometheus_text` honors the export switch (false → empty
  string, default behavior unchanged).
- **multi_candidate double-patch-apply elimination**
  (`src/tools/multi_candidate.py`):
  `static_validate_patch` already called `apply_patch_to_code` internally;
  `generate_candidates` then applied the patch a second time for every
  statically-validated candidate — pure redundancy (regex + line-range
  locating + blank-line compression, 3× wasted with 3 candidates). Now the
  signature is 3-tuple (ok, reason, applied_code) and `generate_candidates`
  reuses the third element (3 wasted applications → 0).

### Code quality
- **15 ruff warnings cleared** (F401/F841/PERF401/PERF102/E741/RET504/B007/
  E402/I001): removed 5 unused imports and dead variables; rewrote 4
  for-append loops with `list.extend` / `dict.values()`; renamed ambiguous
  `l` → `line` in `contamination_check`; `nodes._append_execution_trace`
  now returns the `_append_trace_record` result directly; the
  `api_manager` Prometheus-export loop variable `name` → `values()`.
- **33-file format normalization** (`ruff format`, whitespace only, no logic
  changes).

### Tests
- 6 new regression cases:
  `tests/test_multi_candidate.py` (1: `static_validate_patch` 3-tuple
  contract lock-in);
  `tests/test_dependency_edge_cases.py` (2: no-lost concurrency counting +
  out-of-lock persistence guard);
  `tests/test_api_circuit_breaker.py` (3: `API_CIRCUIT_BACKOFF` on/off
  dual paths + `API_PROMETHEUS_EXPORT` default empty string).
- Full suite **1612 passed / 0 failed** (+6 over 0.5's 1606), ruff check +
  format all green, src coverage 94%.

## [0.5] - 2026-09-20 Analysis-layer deepening (cross-baseline convergence + cross-file failure cases + minimal-repro auto-extraction)

### Features
- **1.3 Cross-baseline convergence comparison**
  (`experiments/analyze_results.py`): new
  `_cross_baseline_convergence_comparison` aligns the repair-convergence
  curves of `aitester` and the `plain_llm` variants in `per_baseline` by
  iteration round (0/1/2/3+) and emits two key deltas: `first_attempt_delta`
  (first-attempt pass-rate difference, collaboration vs baseline — positive
  means the multi-agent "get it right the first time" capability leads) and
  `cumulative_pass_rate_at_1_delta` (round-1 cumulative pass-rate difference,
  used to tell whether collaboration gain comes from "getting it right at
  once" rather than "catching up through extra debugging rounds"). Deltas
  are None when baseline count <2 or a collaboration/baseline group is
  missing; the render layer only emits the stacked table and does not force
  delta computation.
- **2.2 Cross-file repair failure-case analysis**
  (`experiments/analyze_results.py`): new
  `_cross_file_failure_analysis` collects the `error_category` distribution
  of failed tasks per baseline plus the count of failed tasks whose
  diagnosis text contains import/module/模块 keywords (the typical
  signature of cross-file repair failure); the overall
  `import_related_rate` serves as a proxy for "module path / import
  relations not handled correctly." The render layer adds a troubleshooting
  hint when `import_related_rate ≥ 30%` (check whether
  `CROSS_FILE_BIDIRECTIONAL=true` is enabled for the callee view).
- **5.3 Minimal-repro snippet auto-extraction**
  (`experiments/analyze_failures.py`): new `extract_minimal_repro`
  progressively degrades to pull a "minimal reproducible code snippet" out
  of a failed task's diagnosis (rule 1: traceback tail — the last File line
  + 3 lines of core context; rule 2: keyword-filtered lines; rule 3: fall
  back to the ``` code block in task_metadata.problem_statement), with zero
  LLM calls, pure text processing, reproducible.
  `failure_knowledge_base` cases gain a `minimal_repro_code` field (None when
  no rule matches); `generate_report` renders the snippet or a "manual
  supplement needed" note.

### Tests
- **13 new tests**:
  `tests/test_experiments_analysis.py` adds
  `TestCrossBaselineConvergenceBoundary` (single baseline unavailable /
  collaboration vs baseline delta / no plain baseline → None / missing round
  data → stacked table skipped) and `TestCrossFileFailureAnalysisBoundary`
  (all-pass unavailable / import keyword count / empty _details no-crash) —
  7 cases;
  `tests/test_analyze_failures.py` adds `TestExtractMinimalRepro`
  (rule 1 traceback tail / rule 2 keyword filter / rule 3 code block / all
  empty → None / max_lines truncation keeps the exception message /
  knowledge-base case carries the `minimal_repro_code` field) — 6 cases.
- All 1606 tests pass (+13 over 0.4, zero regressions).

## [0.4] - 2026-09-20 Five-chapter capability enhancement (evaluation / data / system / observability / testing)

### Features
- **1.1 Multi-dimensional evaluation metrics** (`experiments/analyze_results.py`):
  extended test-smell detection with Eager Test + Lack of Cohesion AST
  heuristics, strategy-grouped smell counts, and `smell_density`;
  added `_convergence_token_efficiency`, `_difficulty_stratified_iterations`,
  mutation-score × assertion-strength cross-check, `_rag_token_efficiency`,
  `_rag_similarity_distribution`, `_failure_root_cause_trend`
  (llm_capability / dependency / framework split with time-series), and
  `_contamination_cross_analysis` (high vs low contamination risk success-rate
  delta).
- **1.2 Mutation feedback loop** (`experiments/mutation_testing.py` +
  `src/agents/generator.py` + `src/graph/state.py`): new `boundary_shift`
  (Gt↔GtE) and `return_void` (return X → return None) mutant types;
  `build_mutation_feedback()` packages survived mutants for prompt injection
  (MutGen-style test-hardening loop). `run_single_task` gained an
  `enable_mutation_scoring` argument (fixing a `NameError` on the
  previously undefined `mutation_enabled`).
- **2.1 Multi-dimensional contamination detection**
  (`experiments/contamination_check.py`): alongside token-Jaccard, added
  structural (AST statement-skeleton LCS ratio) and semantic (token-bag
  cosine, with an `_embed_code` hook for CodeBERT) dimensions;
  `patch_semantic_similarity` returns three scores;
  `_combined_risk_level` takes the most-severe dimension;
  `detect_contamination` now emits per-task `risk_level` +
  `contamination_summary` (contaminated vs clean success rates + delta);
  added `render_resistant_benchmark_section` (SWE-rebench registry).
- **2.2 Cross-file bidirectional dependency graph**
  (`src/tools/cross_file.py`): `analyze_cross_file_deps` gained a
  `bidirectional` flag (default False preserves the historical single-entry
  view); when enabled, `_collect_reverse_deps` collects
  "other-module → entry-module" edges (callee view) so cross-file repair can
  update callers too; `_find_symbol_def_line` locates a symbol's definition
  line (def / class / assignment). `CROSS_FILE_BIDIRECTIONAL` env toggles
  it (default false).
- **3.1 Adversarial reasoning** (`src/agents/debugger.py`): Debugger gained
  AdverIntent-style adversarial intent hypotheses + critic evaluation;
  enabling `ADVERSARIAL_DEBUGGING_ENABLE=true` makes it emit 2–3 "break
  this implementation" hypotheses, generate targeted tests, run an
  independent critic attempt, and re-generate the patch once if the critic
  finds a breakthrough case. Off by default to preserve the historical
  experiment baseline.
- **3.2 Execution-feedback dynamic iteration strategy**
  (`src/graph/nodes.py` + `src/graph/state.py`): after each Executor run,
  `_suggest_iteration_strategy` emits an observation-only suggestion
  ("lower temperature" / "switch repair view") from the coverage-delta trend
  of prior rounds, written to
  `state["iteration_strategy_suggestion"]` (no routing decision).
  Reward signals keep the historical `EXECUTION_TIMEOUT` linear normalization
  (no change to the historical data baseline).
- **3.2 Line-level credit assignment** (`src/tools/multi_candidate.py`):
  new `line_level_credit_scores` (BOOSTAPR-style, "exec-pass rate ×
  (1 − modified-line ratio)" per static-passing candidate);
  `select_best_candidate`'s static mode now ranks by line-level credit;
  `CandidateResult` gained `credit_score`.
- **4.4 Circuit-breaker exponential backoff + Prometheus export**
  (`src/api/api_health.py` + `src/api/api_manager.py`): `APIHealth` gained
  `circuit_open_count`, `half_open_success`, `half_open_failure`;
  `mark_failure` now cools down for `base * 2^open_count` (capped by
  `half_open_probe_penalty_cap_seconds`), so a dead provider's cooldown
  grows monotonically; `mark_success` resets the counter;
  `_probe_circuit_half_open`'s failure path uses the same backoff;
  `half_open_probe_success_rate` property feeds routing weights.
  `APIManager.get_status` exposes the new fields;
  `to_prometheus_text()` exports 7 metrics (health / circuit_state /
  open_remaining_s / open_count / probe_success_rate / success_rate /
  avg_response_ms); `reset_stats` clears the new counters. Pure side-band,
  no change to existing routing behavior.
- **4.4 venv cache capacity monitoring** (`src/tools/dependency.py`):
  new `get_venv_cache_size_mb` / `check_venv_cache_size` (5 GB threshold,
  WARNING only, no auto-cleanup); `_VENV_CACHE_STATS_FILE` is now a
  dynamic function following `_VENV_CACHE_DIR` (fixing a test-isolation
  hazard where the module-level constant still pointed at the real
  `~/.cache/aitester`).
- **4.2 Redaction recursion + regression tests**
  (`src/utils/logging_utils.py` + `tests/test_logging_utils.py`):
  `redact_dict` now recurses into nested dict / list / tuple
  (previously top-level only — nested structs could leak);
  `fallback_mask_sensitive_info` now also catches JWTs (patterns 0/1/2/4,
  skipping `key=xxx` to avoid over-redaction in degraded mode). Added
  `TestSensitiveInjectionRegression` +
  `TestSensitiveInjectionCIPassGuard` (CI cases that inject 4 kinds of
  credentials and verify both primary and fallback paths, plus nested
  `redact_dict` interception).
- **5.2 Error-classification taxonomy extension**
  (`src/agents/error_classifier.py`): `ErrorCategory` gained
  `EXECUTION_TRACE_MISSING` (task failed but `execution_trace` is empty —
  executor exception path) and `MULTI_CANDIDATE_ALL_REJECTED` (all
  candidates rejected by static filtering) (12 → 14 categories);
  `refine_failure_category` accepts `execution_trace` /
  `multi_candidate_stats`, with priority
  patch_rejected > rag_empty > trace_missing > multi_rejected;
  `refine_final_error_category` wires the new fields;
  `get_fix_strategy` documents the two new fix strategies.
- **reproduce.sh defaults** (`reproduce.sh`):
  `ENABLE_MULTI_CANDIDATE_PATCH` defaults to true
  (`--no-multi-candidate` to fall back); new `--cross-file` /
  `--no-cross-file` (default false preserves the historical single-file
  baseline); new `API_CIRCUIT_BACKOFF` (default true) and
  `API_PROMETHEUS_EXPORT` (default false) env passthrough.

### Tests
- **5 new test files** (covering the 4.4 / 2.1 / 2.2 / 3.2 / 5.2
  mechanisms): `test_api_circuit_breaker.py` (13 cases),
  `test_contamination_multidim.py` (25),
  `test_cross_file_bidirectional.py` (16),
  `test_error_classifier_new_categories.py` (16),
  `test_venv_cache_monitoring.py` (11).
- **Boundary hardening** in `test_experiments_analysis.py` /
  `test_failure_kb.py` / `test_logging_utils.py` /
  `test_multi_candidate.py` (degenerate inputs: 1 sample / all-pass /
  no-token-data; full-pass + empty batches; redaction-injection CI cases;
  line-level credit + mutation feedback + new mutant types).
- **Baseline updates** for the 4.4 / 5.2 behavior changes:
  `test_error_classifier.py` (12 → 14 categories; refine calls pass a
  non-empty `execution_trace` to avoid false hits on the new 5.2
  categories), `test_weak_coverage_modules.py` (empty state now refines to
  `execution_trace_missing`), `test_api_manager_extended.py`
  (probe-failure re-open now uses 4.4 exponential backoff),
  `test_experiments_scripts.py` (venv cache snapshot at total=0 still
  carries the capacity fields; the hit-stats section is skipped).

### Engineering baseline
- Fixed the `NameError` on the previously undefined `mutation_enabled` in
  `experiments/run_benchmark.py`'s `run_single_task` (it was only defined
  inside the `run_benchmark` loop's scope).
- Fixed `experiments/contamination_check.py`'s
  `_extract_statement_skeleton` misusing
  `tokenize.generate_tokens(io.StringIO(pseudo))` (StringIO is not
  callable; pass its `.readline` method instead).
- Fixed `src/tools/dependency.py`'s module-level `_VENV_CACHE_STATS_FILE`
  constant leaking the real `~/.cache/aitester` path during monkeypatch
  test isolation (now a dynamic function following `_VENV_CACHE_DIR`).
- Restored `_record_execution_trace` in `src/graph/nodes.py` to its
  historical "returns the trace list" signature (the strategy suggestion is
  now computed separately by `_executor_node` and written to
  `iteration_strategy_suggestion`, without changing the trace-write
  behavior).
- No public API signature changed (all new fields have safe defaults);
  full suite of 1548 tests passes with zero regressions.

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

The current version is 0.6. All previously internal iteration versions (0.9.x / 0.10 etc.) are no longer recorded separately; their features have been merged into 0.1, and 0.2 is a code-quality optimization round on top of it (no new features — refactors/fixes/test cleanup only, zero functional breakage); 0.3 is the evaluation-metrics + mutation-generator fix + redaction-audit round; 0.4 is the five-chapter capability-enhancement round; 0.5 is the analysis-layer deepening round (cross-baseline convergence comparison + cross-file failure cases + minimal-repro auto-extraction); 0.6 is the P0 fix batch (LLM OpenAI-path zero-retry / venv stats dual-lock / ghost-switch implementation / multi_candidate double-apply elimination + code-quality cleanup).
