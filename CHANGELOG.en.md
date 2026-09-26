> **Language**: [简体中文](CHANGELOG.md) | English (this file)

# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - Full-audit & conservative-optimization round (2026-09-26: static-check zeroing + dead-code removal + thread hygiene + project hygiene + perf / correctness hardening + CF-3 cross-file repair defect fix + fifth-batch P0: mutation-test judging / API-poll reproducibility / atomic cache writes / single-agent baseline write guard + state schema + sixth-batch node-layer routing semantics & robustness)

> Repo-wide code audit and conservative optimization batch (default behavior unchanged):
> static checks all green, dead-code removal, thread-hygiene fix, project-hygiene
> completion, perf / correctness fixes in un-deep-reviewed modules, the CF-3
> cross-file repair "all modules share entry code" logic-defect fix, the fifth
> end-to-end wiring-batch P0 fixes (mutation-test kill judging, parallel API
> rotation reproducibility, LLM cache atomic writes, single-agent baseline write
> safety, state schema completion), and the sixth-batch node-layer routing
> semantics & robustness (diagnosis-keyword early-iteration routing in
> `_should_debug`, `test_passed` consistency, generator LLM-failure
> degradation, planner/debugger fallback widened to OSError, cache-stat
> thread hygiene). Full 1728-test suite passes, zero regressions.

### Static-check zeroing (mypy / ruff)

- `src/agents/executor_repo.py::_dep_fingerprint`: dependency-fingerprint content-part list annotation
  `list[str]` -> `list[bytes]` (binary fragments read in `"rb"` mode; the old annotation did not match the
  runtime type and caused 4 mypy arg-type errors at `hashlib.update`);
- `src/datasets/synthetic_dataset.py`: difficulty-distribution stat `dist` annotated as `dict[str, int]`
  (resolves mypy var-annotated);
- `tests/test_executor_repo.py`: unused imports removed (`json` / `sys` / `textwrap` / `shutil` alias),
  file read switched to `with open(...)` context management (SIM115);
- `ruff format --check` normalized 11 unformatted files (experiments / scripts / src / tests formatting drift,
  CI pinned to ruff 0.16.3).

### Dead code & thread hygiene

- `src/api/api_manager.py::_build_node_list`: the full-pool fallback-candidate construction block after the
  `if/else` (both branches already `return`) was unreachable; removed, with the semantically equivalent
  full-pool fallback construction retained on the complexity-routing hit path (behavior unchanged);
- `src/api/api_manager.py::reset_manager`: `_stop_health_checker()` moved outside the global singleton-lock
  critical section (swap out the old instance and clear the reference first, then stop its background
  health-checker thread outside the lock), so the shutdown 5s join no longer blocks concurrent
  `get_manager()` calls creating a new manager.

### Project hygiene

- `.gitignore`: added `.mypy_cache/`, `.ruff_cache/` (tool caches) and `data/`, `results/` (local
  experiment-data directories, consistent with the `experiments/results/` scope, preventing accidental
  commits);
- Verification: `ruff check` / `ruff format --check` / `mypy src/` all green;
  full 1714-test suite passes (31.5s), zero regressions.

### Security (credential-scrub hardening, P0, with empirical proof)

- `src/utils/credential_scrub.py` (P0): the fixed credential list missed the
  numbered multi-endpoint naming actually present in `.env`
  (`OPENAI_API_KEY_2/3`, `OPENAI_BASE_URL_2/3`) — the old `^OPENAI_API_KEY$`
  anchor didn't match numbered variants, so credentials reached the
  code-under-test subprocess verbatim (execution vector + leak surface). Now
  widened with numbered-variant wildcards `OPENAI_(API_KEY|BASE_URL)_\d+`
  and provider intermediate vars (`ALIYUN_BAILIAN_API_KEY` /
  `AGNES_{DOMESTIC|INTERNATIONAL}_API_KEY` / `BIGMODEL_API_KEY` /
  `DEEPSEEK_API_KEY`, coupled with `config_generator`'s
  `PROVIDER_TEMPLATES` keys to prevent list drift);
- `src/api/api_manager.py::call` (P0): the all-nodes-failed path raised a
  `RuntimeError` carrying the raw, un-redacted openai exception body
  (gateway errors may echo the token-bearing base_url) — the exception
  propagation chain was a redaction blind spot; the exit is now uniformly
  `_redact`-ed, aligned with the log path;
- `src/config/config_manager.py::add_llm_config` (P0): api_key / base_url /
  model_name were written to `.env.local` verbatim without validation —
  values containing `\n` could inject arbitrary variable lines
  (hijacking subsequent config); values containing `#` were truncated by
  dotenv parsing. Inputs containing newline / `#` are now rejected before
  writing; the success log redacts base_url at the exit (URL-embedded
  token case);
- `src/utils/exceptions.py::retry_with_backoff`: retry-warning logs printed
  the raw exception object (which may echo request bodies / credentials)
  without redaction — now delegates lazily to `logging_utils.redact_text`
  (same criteria as `api_manager._redact`; lazy import avoids a module-load
  circular dependency);
- `src/utils/logging_utils.py::SensitiveFormatter`: when the primary redaction
  path failed, it fell back to the **un-redacted** full line (including
  stack) — now runs `fallback_mask_sensitive_info`'s pure-regex fallback
  first, and only returns the raw line when that is truly unavailable;
- Regression tests: `tests/test_credential_scrub.py` new (numbered variants /
  provider vars / high-number boundary / input immutability, 5 cases) +
  `tests/test_logging_utils.py` gains 2 `redact_dict` string-input cases.

### Correctness

- `src/utils/logging_utils.py::redact_dict` (P1): string inputs previously
  silently returned `{}` (the whole redacted value was dropped, making
  redaction a no-op in trace / exception serialization) — str inputs are
  now redacted and wrapped as `{"value": ...}`, preserving the dict-returning
  signature contract; the redundant `_redact_scalars_dict` alias removed;
- `src/observability/trace.py::_append` (P1): the `except` swallowed both
  `json.dumps` failures and import failures, silently dropping
  un-serializable records with no warning — split into two branches:
  serialization failure logs a warning and drops this record; redaction
  unavailability writes the raw text (same last-resort criteria as
  logging_utils' three-level fallback);
- `src/graph/workflow.py::_file_cache_entry_count` (P1): the entry-count
  memory key upgraded to `(dir, count, dir-mtime-at-stat)` — the old
  criteria kept a stale high count after external deletion of cached files
  until the directory vanished; mtime changes auto-rescan, eliminating the
  observability-layer distortion (same-dir-unchanged-mtime still reuses the
  memory to skip the glob; perf criteria unchanged);
- `src/graph/nodes.py` (P1): `_HARD_ERROR_CATEGORIES` promoted from a
  per-call function-local set rebuild to a module-level `frozenset`
  (saves needless allocations on the `--parallel` hot path);
  `_cross_file_analyzer_node`'s `cross_file_deps` serialization switched to
  explicit `asdict` (`d.__dict__` includes dataclass internal fields —
  future field additions would silently change the state schema; the
  downstream `_patch_applier_node`'s fixed-key read contract was unstable);
- `src/graph/nodes.py::_dynamic_temperature_from_suggestion` (P1): with
  `TEMPERATURE=0`, "halve the temperature" still passed 0.0 through
  (a meaningless override) — now returns None to keep the default;
- `src/agents/executor_repo.py::verify` (P1): the repo-level verification
  test_patch temp files are named by `base_commit[:8]`; under `--parallel`
  same-repo concurrent verification raced on write/read — the file name now
  carries an `os.getpid()` suffix;
- `src/agents/debugger.py::debug` (P1): an in-function local import of
  `ErrorCategory` / `ErrorClassifier` duplicated the file-header import
  (historical residue) — merged into the header imports;
- `src/agents/base_agent.py` (P1): file-header `import os` was followed by
  a second `import os as _os` (refactor residue, readability) — alias
  import removed;
- `src/utils/helpers.py::_find_balanced_json` (P1): on unclosed JSON it
  returned the residual `text[start:]` (which `json.loads` always rejects,
  paying another O(n) parse for nothing) — now uniformly returns None,
  letting callers take the regex-fallback path (regression cases updated).

### Concurrency (`--parallel` + background-thread races)

- `src/api/api_health.py::APIHealth` (P1): `mark_success` / `mark_failure` /
  `_probe_circuit_half_open` mutated the same node concurrently between the
  routing thread and the background health-checker thread (counters /
  circuit state / response-time deque all non-atomic) — now guarded by a
  node-level `threading.Lock` (pure in-memory read-modify-write, held for
  microseconds; judgment semantics unchanged, only atomized);
- `src/api/api_manager.py` (P1): `health_check_all` / `health_check_batch`
  iterated the live `health_nodes` dict directly, which could `RuntimeError:
  dictionary changed size during iteration` against concurrent
  `remove_node` / `add_node` — now iterate a lock-held snapshot;
  `health_check_batch` checks the stop event between batches
  (`HealthCheckerThread` gains a `stop_event` property);
  `_stop_health_checker` keeps the reference after the join timeout instead
  of setting None (the residual thread exits at the next batch boundary,
  no wasted quota);
- `src/utils/logging_utils.py::setup_logger_safety` (P1): the check-then-
  append section was lock-free; concurrent calls each appended a filter
  instance (handler.filters bloat) — a module-level lock now serializes the
  idempotent short-circuit;

### Maintainability

- `src/graph/workflow.py::_should_debug` (P2): the diagnosis-keyword list
  was rebuilt inside the routing function on every call — extracted to a
  module-level constant `_TEST_GEN_DIAGNOSIS_KEYWORDS` (single source of
  truth; tuning trigger words now touches one place);
- `src/graph/nodes.py` (P2): `_executor_node`'s in-function local imports of
  `EXECUTOR_DOCKER_IMAGE` / `EXECUTOR_USE_DOCKER` drifted from the 9
  file-header config symbols — merged into the header imports;

### Performance (un-deep-reviewed module hardening, 2026-09-26 round 3)

- `src/datasets/dataset_loader.py` (P1): `get_task_by_id` demoted from O(n)
  linear scan to O(1) lookup — SWE-bench full (2294 tasks) × the benchmark
  loop was O(n²). Implementation: `__init__` builds
  `_task_index: dict[str, BenchmarkTask]` + an `_index_size` length marker
  (O(1) invalidation check); `_ensure_loaded` rebuilds it once after load;
  `add_task` appends and triggers a lazy rebuild on length change (O(n)
  once, O(1) thereafter). The base class gains `add_task` (the former
  `InMemoryDataset` appended directly with no index maintenance); the
  subclass override was removed;
- `src/tools/code_analyzer.py` + `src/tools/code_context.py` (P1, C-1):
  `extract_function_context` did a **second** `ast.parse + ast.walk` when
  `extract_focused_code` returned the source verbatim to confirm the
  function existed — doubling the ~200ms cost on large files. New
  `extract_focused_code_detail` returns a `(code, focus_resolved)` pair;
  `extract_function_context` consumes `focus_resolved` directly with zero
  re-parsing. `extract_focused_code` (original signature) delegates to the
  new function for compatibility; the 3 call sites needed no changes;

### Correctness (un-deep-reviewed module hardening, 2026-09-26 round 3)

- `experiments/rag_ab_experiment.py` (P0): `_parse_task_record` read field
  names (`tokens_total` / `total_tests` / `passed_count` / `duration_s` /
  `failure_category`) with zero overlap with the keys
  `run_benchmark._build_task_result` actually produces
  (`token_usage{total_tokens}` / `elapsed_seconds` / `iterations` /
  `passed` / `error_category`) — every `.get` fell to its default, so the
  RAG A/B report's token-gain / elapsed-time / error-distribution
  conclusions were always false data. Now read with the real keys;
- `experiments/rag_ab_experiment.py` (P1): `_run_benchmark_once` gains a
  `sub_run_dir` parameter — the RAG ON / OFF runs now write to separate
  subdirectories (`<output_dir>/rag_on`, `<output_dir>/rag_off`), avoiding
  same-second mtime collisions when sharing one output_dir (the
  `benchmark_*.json` timestamp precision is seconds);
- `experiments/run_benchmark.py` (P2): `task_limit` boundary normalization —
  a negative value silently truncated the slice (`tasks[:-1]` dropped the
  last task), 0 fell into the else branch as full. Now `<1` uniformly means
  "no limit" (full), only positive values apply, and a warning is logged;
- `scripts/compare_executor_modes.py` (P1): `main.py run --json` on multiple
  files emits stdout as concatenated JSON objects (one segment per task, not
  a single array) — the old `json.loads(proc.stdout)` always failed on the
  concatenation → `tasks_passed` was always 0. New `_parse_json_stream`
  consumes objects one by one with `JSONDecoder.raw_decode` (compatible
  with single object / array / concatenated forms);
- `src/reports/generator.py` (P1): `get_report_generator()` was a lock-free
  check-then-act; the first `--parallel` concurrent construction race
  created one `ReportGenerator` per thread (each with its own
  `ErrorClassifier`) — now guarded by a module-level `threading.Lock`
  double-checked lock;
- `src/reports/generator.py` (P2): `ErrorReport.to_dict`'s
  `error_context.__dict__` direct-introspection serialization would
  silently change the schema when a dataclass field is added — switched to
  explicit `asdict` (same-class fix as nodes.py' cross_file_deps);
- `src/tools/cross_file.py` (P1): `build_cross_file_repair_plan` caught
  only `(json.JSONDecodeError, RuntimeError)` when generating each module's
  patch; LLM timeouts propagated and aborted the whole plan — now catches
  all `Exception` (a failed module is skipped without killing the plan,
  same criteria as multi_candidate.generate_candidates);
- `src/datasets/dataset_defects4j.py` (P2): `info.json` parse failures
  silently returned None (a corrupted version was skipped without trace) —
  now logs a `logger.warning` for data-problem localization;

### Concurrency (un-deep-reviewed module hardening, 2026-09-26 round 3)

- `src/tools/cross_file.py` (P1): `_save_repair_plan_cache` used a plain
  `open("w") + json.dump` (non-atomic) — two `--parallel` workers writing
  the same dependency graph interleaved and corrupted the JSON → the reader
  degraded to None → an extra LLM call (cost amplification). Now writes a
  temp file then `os.replace` atomic-swap (same pattern as nodes.py
  `_write_file_atomic`); the temp file is cleaned up on failure;
- `scripts/check_lock_sync.py` (P2): new rule 4 (WARNING, does not affect
  the exit code): "extra" lock entries not declared in requirements.txt
  (e.g. radon==6.0.1 remains in the lock after removal from requirements)
  now prompts a lock regeneration (the lock includes transitive deps;
  WARNING only, non-blocking);

### Cross-file repair logic defect (CF-3, 2026-09-26 round 4)

- `src/tools/cross_file.py::build_cross_file_repair_plan` (P0): the
  coordinator-proposer architecture's intent is "each module's proposer
  generates its patch from that module's own code", but the old code passed
  the **entry module's `target_code`** to `debugger.debug()` for every
  module — module B's patch was actually generated from module A's code,
  misaligning multi-file patches. New optional `source_files:
  dict[str, str] | None` parameter: when provided, each module uses its own
  source (`source_files.get(module_name)`); a missing module falls back to
  `target_code` (conservative, does not block that module's patch).
  `source_files=None` preserves historical behavior (all modules share
  `target_code`, backward-compatible); `target_module` is now passed per
  module name (`module_name`) rather than the caller's fixed value — the
  LLM prompt constrains "the module the current proposer is responsible
  for";
- `src/tools/cross_file.py::build_cross_file_repair_plan_cached`: the cache
  wrapper naturally holds `source_files` (used for dependency analysis) but
  previously didn't pass it through to the underlying
  `build_cross_file_repair_plan` → even with sources available, the
  underlying layer shared `target_code` across all modules. Now passed
  through; the cache-hit and LLM-generation paths share one criteria;
- Regression tests: `tests/test_cross_file.py` gains 3 cases
  (`test_source_files_per_module_code` verifies each module receives its own
  source + module name; `test_source_files_fallback_to_target_code`
  verifies the entry-code fallback when a module is absent;
  `test_source_files_none_keeps_legacy_behavior` verifies the all-share
  `target_code` historical behavior when `source_files=None`);

### Mutation-test judging & mutant generation (P0/P1, 2026-09-26 round 5)

- `experiments/mutation_testing.py::_run_mutant_tests` (P0): the old
  `return proc.returncode != 0` treated **every** non-zero pytest exit
  code (including 2 = collection error / ModuleNotFoundError / syntax
  error) as "killed" — the exact opposite of the documented conservative
  criteria ("execution failures such as import errors count as alive"). In
  the measured e2e path where the test's imported module name didn't match
  the written `mutated_module.py`, every mutant subprocess exited rc=2 →
  all misjudged "killed" → mutation_score was always 1.0, weak and strong
  tests were indistinguishable (the metric was broken). Now judged by the
  official pytest exit codes: rc==1 (test failures) = killed; rc==0 =
  alive; others (2/5/timeout/exception) = alive (conservative, no
  score inflation);
- `experiments/mutation_testing.py` (P1): mutant "best-effort location by
  line number" defect — `_flip_comparison_op` / `_offset_numeric` /
  `_shift_boundary_op` located "the first same-type Compare on that line"
  after deepcopy; with multiple comparisons on one line
  (`a < b and c < d`) only the first was mutated while the description
  recorded the original operator — inconsistent descriptions + duplicate
  mutants. The location key is now the **(lineno, col_offset) pair**,
  precise to the specific comparison expression;
- `experiments/mutation_testing.py::generate` (P1): the old
  registration-order `mutants[:20]` truncation without deduplication — on
  comparison-rich code the first 4 classes (comparison / boolean / numeric
  / boundary) exploded and squeezed out the P0 3.3 classes 5-7
  (return_void / return_empty / exception_*) entirely, defeating the
  "all 7 classes enabled" design; invalid mutants (target unchanged → code
  unchanged → judged alive) inflated the downstream mutation_score. Now
  deduplicated by `mutant.code` (eliminating duplicate mutants) +
  round-robin type-balanced sampling (the 7 classes fill the cap in
  round-robin, guaranteeing every class has representation);
- `experiments/mutation_testing.py` (P1 companion): `_OPERATOR_FLIP_MAP`
  previously included `Lt↔LtE / Gt↔GtE`, which generated the **same
  mutant code** as the `boundary_shift` class — code-level dedup would
  eliminate boundary_shift entirely. operator_flip now keeps only
  equality pairs (Eq↔NotEq, not covered by boundary_shift); strict-
  comparison boundary mutation is exclusively boundary_shift — the two
  classes no longer overlap and each has its own mutants;
- `experiments/mutation_testing.py` (P2): `_run_mutant_tests`'
  `__import__("subprocess")` anti-pattern replaced with a regular local
  `import subprocess` (the function already locally imports os/sys/
  tempfile);
- Regression tests: `tests/test_smell_detection_v2.py` e2e case's import
  name mismatch fixed (`from module import check` → `from mutated_module
  import check`, making the "weak-test low score / strong-test high score"
  assertion actually work); `tests/test_multi_candidate.py`'s
  boundary_shift case source updated to strict comparison to match the
  post-fix type distribution.

### Parallel API-poll reproducibility (P0, 2026-09-26 round 5)

- `experiments/run_benchmark.py::run_single_task` (P0): the task→API
  rotation index used `hash(task.task_id) % len(_VALID_APIS)` — Python 3's
  built-in `str` hash is randomized by `PYTHONHASHSEED`, so the same task
  mapped to different API indices across processes/starts, breaking the
  documented "stable task→API rotation" promise (baseline comparisons not
  reproducible). Now `zlib.crc32(task_id)` (cross-process deterministic) +
  baseline-index mixing: `(crc32(task_id) + baseline_idx) % n`, preserving
  the historical within-task multi-baseline offset behavior;
- `experiments/run_benchmark.py::run_single_agent_baseline` (P0): the
  single_agent baseline wrote the LLM's `new_code` via a plain
  `open(state["target_file"], "w")`, bypassing `_patch_applier_node`'s
  safety checks — an empty/too-short LLM shell would wipe the target file,
  and subsequent baselines/retries would see empty code. Now guarded:
  non-empty (≥ 10% of original) + function-definition count not decreased
  (aligned with the workflow write-disk criteria); on failure the write is
  skipped and the original code is kept (warning logged).

### LLM cache atomic writes (P1, 2026-09-26 round 5)

- `src/agents/base_agent.py::_call_llm_with_cache` (P1): the old plain
  `open(cache_file, "w") + json.dump` was non-atomic — two `--parallel`
  workers on the same key (same prompt material → same md5 → same
  cache_file) could race; the other reader might observe a half-written
  JSON → `json.load` failed → silent LLM re-call (wasted tokens + latency).
  The cache key is the content md5, so concurrent writers produce
  byte-identical JSON. Now "write a thread-unique temp file
  (`.tmp.<thread_id>`) → `os.replace` atomic swap" (same pattern as
  cross_file CF-8 / nodes._write_file_atomic); the temp file is cleaned up
  on replace failure.

### State schema & write-disk safety checks (P2, 2026-09-26 round 5)

- `src/graph/state.py` (P2): the `repo_verification` field was set by
  `run_benchmark` after invoke but **not declared on the AITesterState
  TypedDict** (the guard test test_state.py missed it). Now explicitly
  declared as `repo_verification: dict[str, Any] | None` and initialized
  to None by `create_initial_state` (key set aligned with `__annotations__`);
- `src/reports/generator.py::_parse_failed_cases` (P2): the fallback
  parser's hard conditions `"FAILED" in line and "[" in line` missed
  modern pytest short output (`FAILED test_x.py::test_y - AssertionError`,
  no `[`); `"Error" in line` was too broad (any line containing "Error"
  overwrote the error field). Now matches pytest's actual output patterns:
  the case name takes the first token on the FAILED line (compatible with
  `[E]`/`[F]` suffix / short-format suffix); the short-format inline error
  suffix is extracted directly; the detailed format takes the first
  exception-class line after the FAILED line; name-missing falls back to
  "unknown" (historical behavior preserved);
- `scripts/verify_swe_bench_export.py::_extract_suggested_func_from_patch`
  (P2): `line.startswith("@@") or line.startswith("@")` was semantically
  contradictory with the regex below — `startswith("@")` also hit diff
  deletion lines containing decorators (`-@decorator` starts with `@` but
  is not a hunk header). Now tightened to hunk headers `@@` only, with
  `split("@@", 2)[2]` extracting the trailing context (same criteria as
  dataset_loader._extract_suggested_function).

### Node-layer routing semantics & robustness (P1/P2, 2026-09-26 round 6)

- `src/graph/workflow.py::_should_debug` (P1 routing-semantics
  clarification): the diagnosis-keyword check was previously nested inside
  the "max iterations reached" block — early iterations (iteration < max)
  hitting "test generation error" keywords still went to the debugger to
  fix code rather than back to the generator for regeneration,
  inconsistent with `_generator_node`'s regeneration decision
  (`defect_type == test_defect` triggerable at any iteration) and the 3.1
  bidirectional diagnosis path. Now promoted to an independent branch
  (any-iteration keyword hit regenerates, still protected by the
  `regeneration_count` cap; when the cap is filled, falls back to normal
  debug);
- `src/graph/workflow.py::_should_debug` (P1 consistency): `test_passed`
  used strict `is True` identity while `_recent_repairs_invalid` used
  truthiness (non-bool truthy values such as `numpy.bool_` were
  misjudged as failed by `is True` → misrouted to debug). Now unified to
  truthiness;
- `src/graph/nodes.py::_generator_node` (P1 degradation fallback): the old
  code had no try-except around `agent.generate` — an LLM failure
  (RuntimeError, including cross-API failover exhaustion) or cache OSError
  crashed the entire graph, inconsistent with the planner/debugger nodes'
  "degrade on failure" criteria (both have default-plan / empty-patch
  fallbacks), and the workflow.py module docstring claims "LLM-call
  exceptions are caught so the workflow never crashes on a single point of
  failure". Now degraded: on LLM failure an empty test is generated with a
  warning, and the executor naturally fails → routes to debugger/done
  instead of crashing (for a "totally unavailable LLM": crash = zero
  output, degrade = still a repair chance);
- `src/graph/nodes.py::_planner_node` / `_debugger_node` (P2 fallback
  widening): the except clause caught only `(json.JSONDecodeError,
  RuntimeError)`, missing `OSError` from LLM file-cache IO (cache dir
  deleted externally / disk full) — now widened to
  `(json.JSONDecodeError, RuntimeError, OSError)`, consistent with the
  "node degradation fallback" design (cache IO exceptions no longer crash
  the graph);
- `src/graph/workflow.py` (P2 thread hygiene): `_FILE_CACHE_COUNT_MEMORY`
  read-modify-write was lock-free; concurrent `--parallel` task-end
  reports calling `get_workflow_stats → _file_cache_entry_count` could
  observe a half-updated tuple (another thread mid stat/glob). Now a
  module-level `threading.Lock` serializes the memory read + stat/glob +
  memory write (the critical section is all read-only syscalls; a plain
  Lock suffices; memory-key semantics unchanged);
- `src/tools/cross_file.py` (P2 import hygiene): `_save_repair_plan_cache`
  except-branch local `import contextlib` promoted to a module-top import
  (no more in-function imports, aligned with other module-level import
  criteria).

Regression tests: `tests/test_workflow.py` gains
`test_generator_node_llm_failure_degrades_to_empty` (generator LLM-failure
degradation to empty test); `tests/test_workflow_extended.py` gains
`test_should_debug_regenerate_at_early_iteration` (early-iteration
diagnosis-keyword routing to regenerate + regeneration-cap protection).

### Verification

- `ruff check` / `ruff format --check` / `mypy src/` all green;
- Full 1728-test suite passes (28.7s), zero regressions (round-6 adds 2
  regression cases: generator LLM-failure degradation + early-iteration
  diagnosis-keyword routing; round-5 fixed the existing mutation-test e2e
  case's import-name mismatch so its assertion actually works, and added 2
  report-parsing regression cases).

## [Unreleased] - P0 improvement batch: 13 items landed (layered code compression / complexity-aware routing / naming-contract validation / stratified synthetic difficulty / cross-file synthetic tasks / SWE-bench export quality verification / RAG A/B experiment script / adaptive multi-candidate trigger / mutation difficulty upgrade / error sub-classes + response retry / default trace layer / per-repo venv reuse)

> Corresponds to the experiment data gaps (SWE-bench 0/20, synthetic stats covered but real-dataset A/B missing)
> and the improvement roadmap in `docs/assessment_2026-09-25_improvement_directions.md`.
> All default behaviors remain compatible (default parameters fall back to historical baselines; new capabilities require explicit opt-in).
> See `docs/implementation_2026-09-25_p0_batch.md` for full details.

### Features (default behavior unchanged, enabled via environment variables)

- **1.1 Layered code compression (function-level slicing + call-chain depth)**
  (`src/tools/code_context.py` + `src/tools/code_analyzer.py` + `src/agents/base_agent.py`):
  - `extract_function_context(source, func_name, depth=2, max_chars=3000)` delegates to
    `extract_focused_code()` BFS call-chain closure (`_closure_names`); depth=1 keeps direct
    dependencies (historical behavior), depth=2 expands one more level of callee dependencies;
  - `BaseAgent.truncate_code()` gains a `focus_depth` parameter (reads `CODE_FOCUS_DEPTH`,
    default 1); `_CODE_MAX_CHARS` now reads the `CODE_MAX_CHARS` env var (default 3000);
  - `debugger.py` `cross_file_contexts` generated via `extract_function_context`
    (per-module 2000-char budget + 4000-char total budget), injected into the Debugger prompt.

- **1.2 Complexity-aware routing (fixed Agnes 3.0-flash multi-provider endpoints)**
  (`src/api/complexity_router.py` new + `src/api/api_manager.py` + `src/graph/state.py` +
  `experiments/run_benchmark.py`):
  - `compute_complexity_score(lines, num_files, num_deps, cyclomatic_complexity)` outputs a
    [0,1] normalized score (`<0.35 → simple / <0.70 → medium / >=0.70 → complex`, per-dimension
    weights configurable via `ROUTING_COMPLEXITY_*_NORM` env vars);
  - `APIManager._select_node_by_complexity(complexity_class)` sorts APIHealth nodes by
    cost_weight (complex → high-cost-weight endpoints first, simple → low-cost-weight first);
  - `state["complexity_class"]` / `state["complexity_score"]` / `state["complexity_breakdown"]`
    / `state["routing_hints"]` computed and written by `run_benchmark.py` after
    `create_initial_state`;
  - Constraint: routes only among Agnes 3.0-flash multi-provider endpoints; no external model
    family introduced; `MODEL_ROUTING_STRATEGY=fixed` falls back to the historical strategy.

- **1.3 Patch naming-contract validation (on by default)**
  (`src/tools/patch_applier.py` + `src/graph/nodes.py`):
  - `check_naming_contract(original_code, patched_code) -> (bool, list[str])`: AST-compares
    module-level symbols (functions / classes / `__all__` / registration decorators /
    module-level constants) before and after; rejects the patch if any original symbol is
    missing;
  - `PATCH_CONTRACT_CHECK=true` (default) invokes the check before writing the patch in
    `_patch_applier_node`;
  - The Debugger prompt is injected with `_CONTRACT_CONSTRAINT` ("must not modify or delete
    the following symbols...").

- **2.1 Stratified synthetic difficulty (difficulty parameter)**
  (`src/datasets/synthetic_dataset.py` + `experiments/run_benchmark.py`):
  - `SyntheticDataset(task_count, seed, subset, difficulty="mixed", **kwargs)` supports five
    difficulty tiers: `mixed` / `level1` / `level2` / `level3` / `level4`;
  - Level 1 (historical baseline) / Level 2 (multi-function interaction defects) /
    Level 3 (cross-file dual-module construction) / Level 4 (subtle boundary + exception
    defects);
  - The CLI `--difficulty` option applies only to the synthetic dataset.

- **2.2 Cross-file synthetic task construction (Level 3 dual-module)**
  (`src/datasets/synthetic_dataset.py`):
  - `CROSS_FILE_PATTERNS` dual-module templates (module_a entry + module_b defective callee);
  - `instance_code=module_b_code`, `metadata.module_a_code` / `target_module` /
    `fixed_module_b_code` / `num_files=2` for the cross-file repair architecture;
  - Repair requires modifying the module_b interface → exercises the coordinator-proposer
    cross-file repair architecture.

- **3.2 Adaptive multi-candidate trigger (default adaptive)**
  (`src/graph/nodes.py`):
  - `MULTI_CANDIDATE_TRIGGER_STRATEGY=adaptive` (default): multi-candidate is enabled only
    when `iteration >= 1` AND `error_category ∈ {assertion, runtime, logic_error,
    index_error}`; simple tasks / early iterations keep the single candidate to save tokens;
  - `MULTI_CANDIDATE_TRIGGER_STRATEGY=always` falls back to the historical baseline.

- **3.3 Mutation difficulty upgrade (7 mutation types)**
  (`experiments/mutation_testing.py`):
  - New `_ReturnEmptyTransformer` / `_RemoveRaiseTransformer` /
    `_ExceptionTypeTransformer` transformers;
  - Mutation types extended from 5 to 7 (operator_flip / boolean_negation / numeric_offset /
    boundary_shift / return_void / return_empty + exception_remove + exception_type_swap),
    improving coverage of "boundary + exception-path" defect classes.

- **4.1 Error sub-classes + response-format retry**
  (`src/agents/error_classifier.py` + `src/agents/debugger.py`):
  - `ErrorCategory` gains `LLM_EMPTY_RESPONSE` / `LLM_JSON_PARSE_FAILED` (precise sub-classes
    split out of `LLM_FORMAT_ERROR`; 14 → 16 categories);
  - `ErrorClassifier.classify_llm_response(raw_response)` directly inspects the raw LLM
    response (empty → LLM_EMPTY_RESPONSE; non-empty but JSON extraction failed →
    LLM_JSON_PARSE_FAILED);
  - `debugger.py::debug()` automatically retries once with a stricter prompt when a format
    anomaly is detected, falling back to lenient JSON extraction if still failing.

- **4.3 Per-repo venv reuse (SWE-bench multi-commit scenarios)**
  (`src/agents/executor_repo.py`):
  - `RepoExecutor(venv_reuse_by_repo=True)`: multiple commits of the same repo share one
    repo-level venv (`<repo>/_shared_venv/`), rebuilt only when the dependency fingerprint
    (SHA256 of requirements/pyproject/setup) changes; source-code switches do not trigger a
    reinstall (the editable install's `.pth` automatically follows the checkout);
  - Greatly reduces venv rebuild overhead for SWE-bench multi-commit scenarios (10-20x);
  - Enabled via `SWE_REPO_VENV_REUSE_BY_REPO=true` (requires REPO_LEVEL_EXECUTION +
    SWE_REPO_VENV_ISOLATION).

### Observability & experiment scripts
- **2.3 SWE-bench source export quality verification**
  (`scripts/verify_swe_bench_export.py` new):
  - 5-dimension verification (non-empty / line count / Python syntax / target function
    presence / target file path match), outputting a structured quality report
    (`pass_rate` / `by_label` / `failed_instances` / `avg_line_count`);
  - CLI: `--enrichment` / `--instances` / `--output` / `--min-lines`.
- **3.1 RAG A/B comparison experiment script** (`experiments/rag_ab_experiment.py` new):
  - Automatically runs two benchmarks (RAG ON / RAG OFF), paired analysis of token /
    success rate / iterations / elapsed time, Welch t-test + Mann-Whitney U + Cohen's d
    (same methodology as the 0.7 report);
  - Per-error-type grouped analysis of RAG benefit (which error categories are significantly
    reduced with RAG ON);
  - `--analyze-only` mode (reads existing result JSONs and computes statistics directly,
    skipping the experiment run).
- **4.2 Default-enabled trace layer** (`experiments/run_benchmark.py`):
  - On entry, if `AITESTER_TRACE_DIR` is unset (or empty), it is automatically set to
    `<output_dir>/traces/`;
  - Node-level JSONL records (input length / output length / tokens / elapsed time / routing
    decisions) are automatically appended during workflow execution;
  - Set `AITESTER_TRACE_DIR=` (empty string) to explicitly disable.

### Docs & tests
- **Doc sync**:
  - `README.md` / `README.en.md`: error categories 14 → 16 + new §5.21 P0 improvement batch
    (13 items) + updated "latest optimization" / "recent changes" rows;
  - `.env.example`: P0 batch env vars (CODE_FOCUS_DEPTH / CODE_MAX_CHARS /
    MODEL_ROUTING_STRATEGY / ROUTING_COMPLEXITY_*_NORM / PATCH_CONTRACT_CHECK /
    MULTI_CANDIDATE_TRIGGER_STRATEGY / SWE_REPO_VENV_REUSE_BY_REPO);
  - `docs/implementation_2026-09-25_p0_batch.md` (new): full P0 batch implementation list.
- **Test updates**:
  - `tests/test_error_classifier.py`: 14 → 16 category assertion + P0 4.1 sub-class existence
    check;
  - `tests/test_synthetic_dataset.py`: difficulty stratification tests + cross-file Level 3
    structure validation;
  - `tests/test_workflow_extended.py`: adaptive multi-candidate strategy env var +
    `_select_multi_candidate_patch` signature (`iteration` parameter);
  - `tests/test_executor_repo.py`: `_run_test_nodes` mock signature (`repo_url` parameter).

### Verification
- Full regression: `python3 -m pytest tests/ -q` → **1667 passed, 47 skipped**
  (same as baseline, zero regressions)
- Affected subset: test_base_agent (40) / test_code_context (18) / test_error_classifier (77) /
  test_debugger (38) / test_workflow_extended (37) / test_executor_repo (17) /
  test_synthetic_dataset (5) / test_api_manager + extended (152) / test_code_analyzer (17)

## [Unreleased] - Improvement-direction batch: 5 items landed (3.3 position-aware iterative repair + 5.2 error-classifier 14-category doc sync + 5.1 single-batch boundary tests + 4.2 redaction auto-check hook + 2.1 real-embedding hook)

> Corresponds to the "real remaining work" list in
> `docs/assessment_2026-09-25_improvement_directions.md` (after verifying 16
> improvement sub-directions item by item, 10 were already implemented and 6
> had remaining work; this batch lands 5 of them. The remaining item #5 —
> multi-candidate A/B experiment data — is an experiment-run task and is not
> part of this code batch).

### Feature (default behavior unchanged, enabled via env var)
- **3.3 position-aware iterative repair (LoopRepair-style locate-then-patch)**
  (`src/agents/debugger.py` + `src/graph/state.py` + `src/graph/nodes.py`):
  - New `POSITION_AWARE_REPAIR_ENABLE` switch (default false, preserves the
    historical experiment baseline).
  - `DebuggerAgent._locate_repair_focus()`: takes the exception location
    already extracted by `error_classifier` (traceback line / syntax-error
    line:col), uses AST to locate the "shortest enclosing function" around the
    anomalous line, and injects a position-aware repair hint into the patch
    prompt so the LLM fixes the located spot instead of blindly searching the
    whole file. Purely static, costs no LLM tokens; degrades to the normal
    whole-file repair when it cannot locate (no line number / broken AST /
    cross-file protection).
  - `debug()` return dict gains a `position_aware_focus` key (focused /
    function_name / line / hint); the debugger node writes it into
    `state["position_aware_focus"]`.
  - `tests/test_debugger.py` gains `TestPositionAwareRepair` (9 cases).

### Observability & engineering
- **4.2 log-redaction auto-check hook** (`.pre-commit-config.yaml` +
  `.github/workflows/ci.yml`):
  - pre-commit gains a local hook `audit-log-redaction` (when touching
    `src/**/*.py` / `experiments/**/*.py` it runs
    `scripts/audit_log_redaction.py`; if it finds "a log call whose args contain
    a sensitive field name without redaction" it exits 1 and blocks the commit).
    CI gains an "Audit log redaction (4.2)" step using the same script, so
    local and remote share one code path.
  - New "simulated sensitive-info injection" regression test
    `tests/test_audit_log_redaction.py` (6 cases: repo baseline zero findings,
    unredacted injection must be flagged, redacted not flagged, Bearer/sk-
    credential flagged, exc_info tracebacks not a finding, tests/ dir skipped).

### Evaluation metric (optional dependency, zero external deps by default)
- **2.1 real semantic-embedding hook** (`src/utils/embedding_utils.py` +
  `experiments/contamination_check.py`):
  - New `src/utils/embedding_utils.py` (no new hard dependencies): `embed_text()`
    picks an embedding backend via the `EMBEDDING_BACKEND` env var (auto:
    sentence-transformers > chromadb DefaultEmbeddingFunction > None; none:
    force None to keep the token-bag conservative baseline, enabling a
    "real-embedding vs token-bag" A/B control); `cosine_similarity()` uses
    numpy (already a project dep), with a pure-Python fallback, non-negative
    clamping so it is comparable to the token-bag cosine; `backend_name()`
    reports the semantic-level source for the report.
  - `experiments/contamination_check.py` wiring: `_embed_code` delegates to
    `embedding_utils.embed_text` (loaded lazily at call time, keeping the
    experiments package free of default external hard deps);
    `patch_semantic_similarity` gains a `semantic_source` field
    ("embedding"/"token_bag"); the contamination report renderer labels the
    semantic-level source.
  - Test `tests/test_embedding_utils.py` (12 cases).

### Docs & tests
- **5.2 error-classifier 12 → 14 category doc sync**: `README.md` /
  `README.en.md` / `docs/api_reference.md` / `docs/api_reference.en.md` /
  `docs/failure_analysis.md` "twelve/12 categories" wording synced to fourteen,
  adding the `EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED` enum
  rows and decision-priority note
  (`patch_rejected > rag_empty > trace_missing > multi_rejected`);
  `docs/history/*` historical snapshots intentionally keep the 12-category
  wording.
- **5.1 cross_batch_comparison single-batch boundary test hardening**
  (`tests/test_smell_detection_v2.py` + `tests/test_failure_kb.py`): hardened
  `test_single_batch_no_trend` (added `resolved_categories` / `failure_trend`
  assertions) and added `test_single_batch_all_passed_empty_trend` (failure_trend
  is an empty dict when all tasks pass) and `test_empty_summaries_list`
  (empty batch list does not crash).

> Verification: full regression `pytest tests/ -q` passes; the affected
> subsets (test_debugger 38 / test_smell_detection_v2 / test_failure_kb /
> test_audit_log_redaction 6 / test_contamination_check+multidim 40 /
> test_embedding_utils 12) all pass; `ruff check` on changed files is clean.
> See `docs/implementation_2026-09-25_improvement_directions.md`.

## [Unreleased] - 0.10 deep-audit fixes on 0.9 batch (LLM-cache negative-cache TTL correctness regression + write-root normalization + trace-layer redundant summarization + stats de-glob + 2 regression tests)

> Baseline: 0.9 batch (uncommitted worktree) 1665 passed / ruff 0 / mypy 0 (58 source files).
> This round is a deep-audit + backport of the 0.9 batch: **1667 passed / 0 failed**
> (+2 regression tests, no functional regression), ruff check / ruff format / mypy all green.

### P1 correctness: LLM-cache negative-cache TTL (src/agents/base_agent.py)

The 0.9 batch's "LRU fast-path + negative cache" design had two correctness drifts:
1. **Negative cache never expires**: `_lru_negatives` records "file absent for this key"
   with no TTL; if the cache dir is later restored or new files are written, same-key
   calls in the negative-hit window **skip the file read** and a cache entry that
   could have hit stays invisible forever (contradicting the module's own comment
   "the file remains the source of truth"). Fixed with `_LRU_NEGATIVE_TTL_SECONDS = 30.0`:
   within the window the same-key call skips the file re-read (saves the "read a
   nonexistent file" IO); after expiry the negative entry is lazily dropped and the
   file is re-read (restores external-write visibility).
2. **Write-success path did not clear the negative cache**: `_lru_store` used
   `del _lru_negatives[key]` (KeyError when no negative entry was ever recorded)
   and, semantically, "file now exists" must invalidate the key's negative cache.
   Fixed to `_lru_negatives.pop(key, None)` (idempotent). Regression test
   `test_negative_cache_expiry_rechecks_file` locks in "write-success clears the
   negative cache + post-TTL recheck hits the on-disk entry".

### P1 correctness: write-root normalization symmetry (src/graph/nodes.py)

0.9's `_ALLOWED_WRITE_ROOTS` normalization was redundant and its comment drifted
from the implementation: `os.path.realpath(os.path.abspath(...))` — `realpath`
already includes `abspath` semantics, so the outer `abspath` is dead code; and the
comment claimed "both sides unified via realpath" while the root computation did
not sit on the same normalization path as `_is_within_allowed_roots` (on macOS the
/var→/private/var symlink makes `abspath` and `realpath` diverge; `realpath`
resolution is what makes the whitelist decision correct). Now unified to
`os.path.realpath(root)` over the raw dirname/tempdir values, exactly symmetric
with `_is_within_allowed_roots`'s input normalization; comment corrected.

### P2 performance: trace-layer redundant meta summarization removed (src/observability/trace.py)

`TraceSession._append` previously did `dict(record)` shallow-copy +
`payload["meta"] = {k: _summarize(v) ...}` rebuild — but `task_start`'s meta is
already summarized in `__init__`, and `record_node`'s output / `record_task_end`'s
extra are summarized at the call site; the second summarization in `_append` is
pure redundancy (deep processing + temp dict allocation, accumulating on the
`--parallel` multi-task tracing hot path). Now: record objects are read-only
serialized; summarization is unified at the entry points; `_append` only does
redaction + write.

### P2 performance: `_file_cache_entry_count` in-process memory (src/graph/workflow.py)

0.9's `get_workflow_stats()` `llm_cache.entries` stat did a full
`Path(cache_dir).glob("*.json")` directory scan on every call — under `--parallel`
multi-task end-of-run reporting this accumulates N redundant scans. Now a
module-level `_FILE_CACHE_COUNT_MEMORY = (cache_dir, entries)` memo: same dir
reuses the last count (no glob); dir switch (env var change) invalidates the key
and re-scans; external dir deletion (stat failure) resets to 0. Counting
semantics (glob real-time value) unchanged; only repeated scans are saved.

### Verification

- ruff check 0 across the repo; ruff format 195 files all green; mypy 58 source files 0 errors;
- full suite **1667 passed / 0 failed** (0.9 baseline 1665 + 2 new regression tests:
  `test_negative_cache_expiry_rechecks_file` / `test_file_cache_entry_count_memory`);
- negative-cache TTL benchmark: in-window hit = zero file IO (only the LLM call
  itself remains), post-expiry recheck = disk-cache hit with zero LLM calls.

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
