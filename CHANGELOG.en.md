> **Language**: [简体中文](CHANGELOG.md) | English (this file)

# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - 2026-09-29 Review/optimization round (project audit: P0 runtime-probe defect fix + test-suite 0 warnings)

> This round is a full-project audit (static checks + test warnings +
> core-module code walk) repair batch. **Default behavior unchanged**
> (the probe module is off by default; when `RUNTIME_PROBE_ENABLE=false`,
> zero difference):
>
> - **P0 runtime-probe (RUNTIME_PROBE) core-defect fix**
>   (`src/agents/runtime_probe.py`):
>   The historical implementation collected exception frames via
>   `sys.settrace` exception events, but under CPython per-event tracing
>   semantics, when "an exception is raised inside the function body" the
>   exception event does not propagate to the called frame — measured
>   **frames were permanently empty**, so the P0 runtime probe never
>   actually worked since introduction. This round reads the
>   `exc.__traceback__` frame chain directly at exception-raise time
>   (the exception stack is the precise failure-time frame stack, zero
>   trace overhead), and synchronously fixed:
>   - Single-character-variable mis-filtering: `_capture_frame_locals`
>     historically filtered x/y/z as "loop-variable noise", but at
>     assertion-failure time x/y/z are precisely the most critical
>     observation variables; after filtering, the snapshot was
>     permanently empty.
>   - Line-number error: exited frames' `f_lineno` stops at the
>     function-body tail rather than the exception-raise line; now uses
>     the traceback frame object's `tb_lineno` (the precise line number
>     recorded by CPython).
>   - Module-filter never matching: the probe file is named
>     `"{target_module}_probe.py"`, but the historical filter condition
>     `"{target_module}.py"` as a substring never matches — when a
>     target_module was specified, all frames were discarded (probe was
>     always None). Now matches the probe file itself directly.
>   - Child-thread unhandled-exception leak: top-level call exceptions
>     were not intercepted → the interpreter printed "Exception in
>     thread" noise (pytest converts to
>     PytestUnhandledThreadExceptionWarning).
>   New regression cases: `tests/test_runtime_probe.py` (module-filter
>   retention caliber / module-filter discard caliber / tb_lineno
>   line-number caliber).
>
> - **Test suite 0 warnings**: `tests/test_trace_observability.py`
>   fixed 2 unclosed file handles (ResourceWarning → pytest unraisable
>   noise); full pytest 2502 passed, 0 failed, 0 warning
>   (`-W error::ResourceWarning` caliber).
>
> - **Baseline refresh**: `BASELINE.yaml` synced
>   (total_passed 2499 → 2502; line_total_pct 87 / 0.8673;
>   branch_total_pct 77 / 0.7738; last_verified 2026-09-29).
>
> - **Full regression**: 2502 passed / 0 failed
>   (baseline 2499, +3 new regression cases), ruff 0 warnings /
>   mypy 0 errors (86 source files), `BASELINE.yaml` refreshed.
>
> - **Follow-up full test refresh (same day)**: full suite 2538 passed /
>   0 failed + real LLM smoke test PASS (default endpoint connectivity +
>   response check, `AITESTER_LLM_CACHE=0` writes no cache); fixed ruff
>   format drift in 3 files (runtime_probe / cross_file /
>   test_error_classifier_combinations); branch coverage total threshold
>   78% → 77% aligned to the current weighted measured 77.34%
>   (`scripts/check_branch_coverage.py` + synced guard test);
>   `BASELINE.yaml` refreshed (total_passed 2502 → 2538;
>   line_total_pct note 0.8665).

## [Unreleased] - 2026-09-28 Frontier-recommendation batch (gap_report P0/P1/P2 gaps G1–G8 fully landed, default behavior unchanged + new capabilities all behind independent switches)

> This batch is based on the G1–G8 gaps in
> `docs/gap_report_2026-09-28_frontier_recommendations.md` plus the
> doc-consistency P2 gap, landed item by item, **default behavior
> unchanged** (new capabilities all behind independent switches; when
> disabled, historical behavior is byte-equivalent):
>
> - **G2 P0 risk-tiered human approval loop**
>   (`src/graph/risk_approval.py`):
>   - `RISK_APPROVAL_ENABLE=true` enables it; three-factor weighted
>     scoring (confidence 0.4 + patch impact 0.4 + budget ratio 0.2)
>     → low/medium/high tiering → auto_merge / human_confirm /
>     force_review approval actions;
>   - Thresholds are configurable
>     (`RISK_THRESHOLD_MEDIUM=0.35` / `RISK_THRESHOLD_HIGH=0.65`),
>     weights are configurable
>     (`RISK_WEIGHT_CONFIDENCE` / `RISK_WEIGHT_IMPACT` /
>     `RISK_WEIGHT_BUDGET`);
>   - `experiments/run_benchmark.py` result rows gain a `risk_summary`
>     field (when default off, placeholder `enabled=False`, key-set
>     isomorphism, does not change the historical experiment caliber);
>   - Tests: `tests/test_risk_approval.py` (default-off placeholder /
>     high-confidence small patch → low / low-confidence large patch +
>     budget overage → high / medium impact → medium).
>
> - **G8 P0 full-stack SWE-bench Pro re-test**
>   (`experiments/run_full_stack_swe_bench_pro.py`
>   + `scripts/check_swe_bench_pro_ready.py`
>   + `experiments/summarize_full_stack.py`):
>   - One-key seven-switches (`RUNTIME_PROBE_ENABLE` /
>     `STRATEGY_BANK_ENABLE` / `EXPERT_POOL_ENABLE` /
>     `CROSS_FILE_ENABLE` / `CROSS_FILE_BIDIRECTIONAL` /
>     `REPO_LEVEL_EXECUTION` / `SWE_REPO_VENV_ISOLATION`) + trace
>     directory;
>   - Data pre-gate: `check_swe_bench_pro_ready.py` validates JSONL
>     existence + `instance_code` / `test_patch` / `FAIL_TO_PASS` /
>     `base_commit` completeness; blocks with `exit 1` when missing;
>   - ON/OFF contrast analysis: `summarize_full_stack.py` outputs
>     success rate / error buckets
>     (`assertion` / `runtime` / `import_error` / `syntax` / `unknown`
>     / `other`) + conservative verdict (when the ON group is all
>     zeros, "no positive information" — do not force a positive
>     claim);
>   - Tests: `tests/test_g8_g2_g4_g5_g6_g7_g1.py` (data-directory
>     missing / complete JSONL / enrichment completion, 3 scenarios +
>     runner seven-switch injection).
>
> - **G3 P1 kernel-level sandbox** (`src/agents/kernel_sandbox.py`):
>   - `KERNEL_SANDBOX_ENABLE=true` enables it (default off); macOS
>     Seatbelt (`sandbox-exec`) / Linux Landlock (`bwrap`) dual
>     backend; platform-unsupported → fail-closed rejection (does not
>     silently degrade to un-isolated local, same policy as
>     Docker-unavailable); wired into the local execution chain;
>   - Tests: `tests/test_kernel_sandbox.py` (9 cases).
>
> - **G1 P1 Tree-sitter precise AST backend**
>   (`src/tools/tree_sitter_backend.py`):
>   - Optional dependency; when `tree_sitter` is missing, transparently
>     degrades back to the lexical layer, does not block;
>   - Implements the 4 core methods of `LanguageBackend` (precise AST
>     caliber, fewer false positives);
>   - `pyproject.toml` mypy configuration declares
>     `tree_sitter` / `tree_sitter_typescript`
>     ignore_missing_imports.
>
> - **G4 P1 AgentTelemetry failure-detection benchmark**
>   (`src/observability/agent_telemetry.py`):
>   - `AGENT_TELEMETRY_ENABLE=true` enables it (default off); 10
>     built-in failure-pattern regex matches (zero LLM cost, pure
>     observation layer);
>   - Outputs a Markdown report for experimental-analysis consumption.
>
> - **G5 P2 testless execution-irrelevant validation**
>   (`src/tools/testless_validation.py`):
>   - `TESTLESS_VALIDATION_ENABLE=true` enables it (default off); four
>     independently toggleable layers (AST symbol guard / mypy static
>     check / naming-contract regression / import smoke);
>   - Any layer failure → overall fail (conservative fail-closed
>     caliber), complementary to G7 "with-test" scenario
>     defect-validity determination.
>
> - **G6 P2 multi-agent debate convergence**
>   (`src/graph/expert_pool.py` new `debate_round()` method):
>   - `EXPERT_POOL_DEBATE_ENABLE=true` enables it (default off,
>     requires `EXPERT_POOL_ENABLE=true`); top-K (default 2,
>     `EXPERT_POOL_DEBATE_TOP_K` [2,4]) candidate debate convergence
>     produces one `debate_revise` revised candidate;
>   - On LLM failure, conservatively degrades back to the original
>     verified list (does not block the main chain).
>
> - **G7 P2 defect-report generation**
>   (`src/reports/generator.py` `ErrorReport` new `oracle_stats` field
>   + `with_oracle_stats()` method):
>   - The "Oracle validity (Oracle augmentation, G7)" section is
>     rendered only when `total_oracles > 0`, complementary to G5
>     testless validation ("with-test" vs "without-test" two scenarios
>     for defect-validity determination).
>
> - **Doc-consistency P2**:
>   - New `docs/dependency_exemptions.md`
>     (chromadb 1.5.9 hits 5 known vulnerabilities
>     PYSEC-2026-311 / PYSEC-2026-3813 / PYSEC-2026-3814 /
>     PYSEC-2026-3815 exemption registry: dependency / version /
>     vulnerability ID / exemption reason / re-review trigger
>     condition / re-review deadline);
>   - `scripts/check_dependency_exemptions.py` (CI gate: when the
>     `--ignore-vuln` list is not registered in the registry, `exit 1`
>     blocks merging);
>   - `scripts/check_docs_history_drift.py` (warning-only: detects
>     when `docs/history/*.md` baseline numbers drift beyond the
>     threshold and suggests archiving; non-blocking gate);
>   - `CONTRIBUTING.md` "Dependency exemption registry" section.
>
> Full 2502 tests passed with zero regressions (2026-09-29
> review/optimization round: P0 runtime-probe defect fix + 3 new
> regression cases, previously 2499); ruff 0 warnings; mypy 0 errors
> (86 source files, previously 81, +5 new source files). All new
> capabilities are off by default (`*_ENABLE=false`); enabling is an
> explicit act; zero new default dependencies (tree_sitter is an
> optional dependency; when missing, transparently degrades).
>
> Companion test files:
> - `tests/test_g8_g2_g4_g5_g6_g7_g1.py` (25 cases: G2/G4/G5/G6/G7/G1/G8
>   gaps);
> - `tests/test_kernel_sandbox.py` (9 cases: G3 kernel sandbox);
> - `tests/test_experiments_ab_scaffolds.py` (12 cases: A/B contrast
>   aggregation + full-stack summary verdict + seven-switch injection).

## [Unreleased] - 2026-09-28 Optimization round (Agent instance-reuse cache + LLM-client hot-path memoization, default behavior unchanged)

> Performance-optimization batch following a code review. **Default behavior
> unchanged** (all new capabilities behind independent switches; when
> disabled, historical behavior is byte-equivalent):
>
> - **Agent instance reuse (P1, loop-repair hot path)**:
>   - `src/graph/nodes.py` adds a generic `get_or_create_agent()` factory
>     (keyed by class name + DCL + FIFO capacity 16, same caliber as the
>     llm_client client cache; test scenarios that replace the class with
>     MagicMock automatically degrade to per-call creation, keeping the
>     mock caliber unchanged);
>   - `_planner_node` / `_generator_node` / `_debugger_node` /
>     `_diagnosis_node` all delegate to this factory to obtain BaseAgent
>     subclass instances — under loop repair (MAX_ITERATIONS rounds ×
>     multiple tasks) this removes the per-round "instantiate + look up
>     client cache under lock" overhead (the client itself is still
>     shared via llm_client's (model, temperature, api_key, base_url)
>     cache; reuse vs per-call creation are byte-equivalent under
>     concurrency semantics);
>   - Switch: `AITESTER_AGENT_REUSE=0` disables it (default enabled);
>   - Test hook: `clear_agent_instance_cache()` (conftest autouse
>     fixture clears before/after each test, restoring the "create
>     each time" historical test caliber).
>
> - **ExecutorAgent reuse keyed by sandbox config (P1, same hot path)**:
>   - `src/graph/nodes.py` adds `_get_or_create_executor_agent()`:
>     keyed by the full (timeout, use_docker, use_venv,
>     auto_install_deps, dep_install_timeout, docker_image) config
>     tuple (ExecutorAgent's constructor only stores sandbox params;
>     execute() builds the sandbox / reclaims output independently per
>     call, so same-config reuse is equivalent to per-call creation;
>     `--timeout` variants each get their own instance; DCL + thread
>     lock under concurrency guarantees the same key is constructed
>     only once);
>   - Switch: `AITESTER_EXECUTOR_AGENT_CACHE=0` disables it
>     (default enabled);
>   - Test hook: `clear_executor_agent_cache()` (conftest autouse
>     clears before/after each test).
>
> - **LLM-client hot-path env-var memoization (P2, saves 2 os.getenv
>   calls per LLM invocation)**:
>   - `src/agents/llm_client.py`'s `_llm_cache_enabled()` /
>     `_llm_cache_dir()` read the env vars on first call and reuse an
>     in-process memo;
>   - New `clear_llm_cache_option_memory()` clearing hook — after a
>     test mutates the env vars via monkeypatch.setenv, explicitly
>     clear the memo to restore the "read env vars each time"
>     historical caliber;
>   - `base_agent.clear_llm_lru_cache()` also triggers this clearing
>     hook (clears the env-var memo alongside the LRU clear, keeping
>     test-isolation caliber unchanged);
>   - `tests/conftest.py` autouse fixture clears the memo before and
>     after each test (complementing env-var isolation);
>     `tests/test_workflow.py` explicitly clears the memo at the two
>     directory-switch sites inside unit tests.
>
> - **New regression tests** `tests/test_2026_09_28_agent_reuse_optimizations.py`
>   (10 cases: Agent/Executor instance reuse + switches + clearing
>   hooks + conftest memo-clear semantics); full regression 2453
>   passed / 0 failed (ruff 0 warnings / mypy 0 errors, 81 source
>   files).

## [Unreleased] - 2026-09-29 Improvement batch (cache isolation / injection defense / explainability / deterministic guard / rogue-agent monitoring / keyword fallback)

> Systemic improvements grounded in 2026 industry data
> (Clinejection, KeyPooling, LiteLLM CVE-2026-89032, Spring AI
> CVE-2026-59308, DO-178C, Tesla ≥90% branch-coverage blocking
> strategy). **Default behavior unchanged** (all new capabilities
> behind independent switches; when disabled, historical behavior is
> byte-equivalent):
>
> - **P0 cache user isolation (ADR-0011)**:
>   - `llm_client.py` gains a `creator_uid` field write + a read-side
>     `cache_creator_ok()` ownership check (seals the cross-user /
>     cross-CI-step poisoning surface; historical entries without the
>     field remain compatible);
>   - `AITESTER_CACHE_CREATOR` env var supports multi-tenant logical
>     isolation;
>   - New `tests/test_multiprocess_cache_consistency.py`
>     (poisoning simulation + negative-cache expiry re-read +
>     cross-user creator check);
>   - `tests/test_llm_file_cache.py` fixes the latent
>     `test_negative_cache_expiry_rechecks_file` assertion-comment
>     caliber.
>
> - **P0/P1 injection-defense layer (ADR-0012)**:
>   - New `src/agents/injection_guard.py` (4 input-side feature
>     detectors + 5 output-side dangerous-operation static checks,
>     pure regex, zero LLM cost, default off);
>   - New `tests/test_injection_guard.py` (12 cases).
>
> - **P1 rogue-agent monitoring (OWASP ASI-10 reference)**:
>   - New `src/agents/rogue_monitor.py` (z-score per-tool one-hot
>     deviation / Shannon entropy / capability-violation — three
>     signals, thread-safe, default off);
>   - New `tests/test_rogue_monitor.py` (15 cases).
>
> - **P1 RAG keyword fallback retrieval (bottom of the LeanKG three-tier
>   fallback chain)**:
>   - `src/graph/rag.py` adds `keyword_fallback_search` /
>     `retriever_or_keyword_fallback` (when the vector side is
>     unavailable, degrade to bag-of-words scoring; switch
>     `RAG_KEYWORD_FALLBACK_ENABLE` default off; does not inject
>     results into the action callback, staying conservative);
>   - New `tests/test_workflow_combinations.py` topology-combination
>     cases.
>
> - **P2 semantic-cache false-positive sampling statistics**:
>   - `semantic_cache.py` adds `should_sample_false_positive()`
>     (default 10% hit sampling) + statistics interface + folded into
>     `get_semantic_cache_stats`.
>
> - **P2 deterministic-generation guard**:
>   - New `src/agents/deterministic_guard.py` (AST static scan for
>     random / long-sleep / wall-clock / external side effects,
>     default off);
>   - New `tests/test_deterministic_guard.py` (13 cases).
>
> - **P2 credential-scrub dynamic derivation**:
>   - `credential_scrub.py` auto-derives provider intermediate-variable
>     redaction patterns from `PROVIDER_TEMPLATES` keys (eliminates
>     LiteLLM CVE-2026-89032-style static enumeration drift);
>   - New `scripts/check_credential_scrub.py` CI guard (blocks merge
>     when a new provider is not synced); wired into CI.
>
> - **P2 branch-coverage gate raised (ADR-0014)**:
>   - `check_branch_coverage.py` overall gate 79% baseline + core
>     repair-routing modules 90% strict gate + remaining core modules
>     85%;
>   - Fixed caliber drift: overall branch rate now uses
>     `branches-covered/branches-valid` weighted aggregation (the root
>     branch-rate was a simple module mean, dragged down by small
>     modules);
>   - New `tests/test_workflow_combinations.py` (74 cases, completing
>     `_should_debug` / `_route_after_diagnosis` / `_create_workflow`
>     topology combinations);
>   - `tests/test_branch_coverage_gates.py` gate-constant assertions
>     updated in sync.
>
> - **P2 redaction consistency check**:
>   - `logging_utils.py` adds `verify_redaction_consistency()`
>     (mask_sensitive_info vs redact_text dual-path consistency +
>     key-derived-subset check, guarding against Spring AI
>     CVE-2026-59308 same-root risk).
>
> - **P3 explainability fields (ADR-0013)**:
>   - `error_classifier.py` `ClassificationResult` gains an
>     `explanation` field (hit-rule features / weak-hit annotations /
>     confidence caliber / fallback trigger, zero LLM cost, pure-data
>     caliber);
>   - The four-link strategy trace chain (classification →
>     strategy selection → patch generation → verification result)
>     closes the loop via the `explanation` field.
>
> - **P3 docs**:
>   - New `docs/adr/0011-0014` (4 ADRs);
>   - New `docs/troubleshooting.md` (symptom → root-cause →
>     resolution → prevention four-section troubleshooting manual);
>   - `CHANGELOG.md` batch record.

## [Unreleased] - 2026-09-28 Improvement checklist landing batch (health-check concurrency / CI 3.13 / docs alignment / multi-process cache notes / D-rules staged roadmap, default behavior unchanged)

> This batch verifies and lands the actionable items from the
> improvement checklist (core algorithm / engineering practice /
> evaluation & experiments / docs & collaboration / infra),
> **default behavior unchanged**:
>
> - **VI. Health-check concurrent probing (engineering item 6)**:
>   `APIManager.health_check_batch` gains
>   `batch_health_check_concurrency` (default 1 = pure serial
>   per-node + per-node sleep, historical behavior); when set to 4–8
>   a bounded thread pool probes in parallel within the batch,
>   reducing a large node pool (100+) single-round time from
>   O(N×(probe+sleep)) to O(N/concurrency×probe), keeping one
>   batch-level sleep between batches. Thread-safety basis:
>   node-state writes inside `check_health` go through the
>   `APIHealth` per-node lock (`_enter_half_open_probe` /
>   `_record_health_result` / `_probe_circuit_half_open` are all
>   atomicized). 2 new regression cases (concurrent-mode batch-level
>   sleep caliber + serial-default regression).
> - **VII. CI Python 3.13 coverage (engineering item 19)**:
>   `.github/workflows/ci.yml` matrix extended from
>   `['3.12', '3.14']` to `['3.12', '3.13', '3.14']`, with a comment
>   noting 3.13 is within the scipy/pandas pinned-version support
>   window (previously skipped without explanation).
> - **VIII. Docs caliber alignment (engineering item 15)**:
>   `README.md` "latest optimization" row updated with the
>   2026-09-28 P0/P1 improvement batch (consistent with
>   `docs/api_reference.md` last-updated date, eliminating
>   dual-doc "latest" caliber confusion).
> - **IX. Quickstart recommended opt-in items (evaluation item 13)**:
>   `QUICKSTART.md` gains a "Recommended opt-in items (default off
>   but suggested on demand)" section, describing the expected
>   benefit and cost of `SEMANTIC_CACHE_ENABLE` /
>   `COST_BUDGET_ENABLE` / `POSITION_AWARE_REPAIR_ENABLE` /
>   `ADVERSARIAL_DEBUGGING_ENABLE`, and noting why
>   `CROSS_FILE_ENABLE` is currently not recommended for default
>   enablement (no positive evidence).
> - **X. Failure-analysis snapshot update convention (evaluation
>   items 10 / 11)**: `docs/failure_analysis.md` gains a
>   "Snapshot update convention" paragraph — after major versions
>   re-run the 50-task synthetic experiment, new data lands in
>   `experiments/results/` and is linked from this doc (historical
>   snapshots are not modified in place); stronger models (GPT-4
>   class) repo-level verification data lands separately in
>   `experiment_report_<date>_repo_level.md`, distinguishing
>   "architecture capability" from "model capability" boundaries.
> - **XI. Cross-batch comparison tool landing record convention
>   (evaluation item 12)**: `README.md` §5.15 gains a convention —
>   actual findings from cross-batch comparisons should be recorded
>   in the CHANGELOG or linked from `docs/failure_analysis.md`,
>   avoiding tools that stay sample-only without evidence.
> - **XII. Docs archiving strategy (collaboration item 16)**:
>   `CONTRIBUTING.md` gains a "Docs organization convention"
>   section, clarifying that `docs/history/` is for historical
>   archives (not maintained with versions, internal reference
>   only) and the maintenance boundary with core maintained docs /
>   review reports.
> - **XIII. New-contributor onboarding (collaboration item 17)**:
>   `CONTRIBUTING.md` gains a "Good first tasks for new
>   contributors" section, listing 4 types of low-barrier tasks.
> - **XIV. Docker dependency version-lock notes (deployment item
>   18)**: `Dockerfile` gains comments — requirements.txt top-level
>   dependency `==` pins stay in sync with requirements.lock
>   (guarded by CI `check_lock_sync.py`), image build-time
>   pre-installation uses the same locked versions, and dependency
>   upgrades require updating the lock + rebuilding the image.
> - **XV. Multi-process LLM cache consistency notes (engineering
>   item 20)**: `docs/api_reference.md` gains an "LLM file cache
>   multi-process / multi-thread consistency" section — write-side
>   "temp file + `os.replace` atomic swap" (temp file names carry a
>   thread-ident suffix, no cross-thread / cross-process name
>   collisions) + read-side silent-degrade re-call on corruption
>   (non-blocking) + L1 negative-cache process-level visibility
>   (≤30s TTL in multi-process scenarios, a few duplicate LLM calls
>   acceptable conservative degradation) + maximize cross-process
>   hits (use `--parallel` multi-thread mode rather than multi-process
>   mode).
> - **XVI. Docstring D-rules staged handling roadmap (engineering
>   item 9)**: `docs/code_analysis_report.md` gains a "staged
>   handling suggestion" — stage 1: `ruff check --select
>   D212,D400,D415,D413,D205,D209,D200,D202 --fix` to clear
>   formatting-class; stage 2: add "D" to pyproject select (visible
>   but not blocking); stage 3: batch-fill content-missing rules by
>   priority, progressively zeroing, then full CI blocking.
> - **XVII. Bilingual docs exemption-list maintenance convention
>   (collaboration item 14)**: `scripts/check_bilingual_docs.py`
>   `_EXEMPT_NO_EN` gains comments — manually review the exemption
>   list quarterly or after major versions; promote core reference
>   docs by adding English pairs and removing the exemption; move
>   stale docs into `docs/history/` archive.
> - **XVIII. Algorithm evolution roadmap (algorithm items 1–4,
>   doc form)**: `docs/algorithm_design.md` §3.1 gains a "Known
>   limits & evolution directions" section, with 4 suggestions (all
>   annotated with default / independent switches, preserving
>   historical behavior): ① lightweight semantic-classification
>   fallback layer when rules miss (reusing the 5.1 embedding
>   backend, suggested independent switch `SEMANTIC_CLASSIFY_ENABLE`
>   default false); ② position-aware iterative repair
>   (`POSITION_AWARE_REPAIR_ENABLE`) evaluated for default enablement
>   only after an ON/OFF comparison experiment on the 50-task
>   synthetic set; ③ cross-file repair layered verification by
>   import-dependency depth (with stronger models + repo-full
>   source context); ④ adversarial-reasoning × mutation-testing
>   closed loop (`mutation_score_from_details` score as the
>   adversarial-reasoning input signal, suggested independent switch
>   `MUTATION_FEEDBACK_ENABLE` default false).
> - **Verification results (engineering items 5 / 7, no changes
>   needed)**: the dual redaction implementations
>   (`api_manager._redact` / `llm_client._redact_log_text`) were
>   already unified onto the single `logging_utils.redact_text`
>   implementation in round 0.2; the duplicate `get_healthy_nodes()`
>   call in `get_status()` was already deduplicated via same-batch
>   result reuse — current code has no redundancy. The triple
>   exception-handling template duplication (engineering item 8)
>   stays recorded as low priority in `code_analysis_report.md`,
>   not extracted into a shared function yet.
>
> Full test suite passing (2 new cases) / ruff 0 warnings / mypy 0
> errors.

## [Unreleased] - 2026-09-28 Improvement batch extension (CFG control-flow analysis / event bus / trace visualization / ADR / bilingual-sync check / CLI enhancement, default behavior unchanged)

> This batch advances P2/P3 improvement items, **default behavior
> unchanged**:
>
> - **II. 2.2 Control-flow graph (CFG) static analysis**:
>   `src/tools/control_flow.py` pure AST analysis (zero LLM cost),
>   producing a CFG summary of branch conditions / loop bounds /
>   exception paths / multiple exits / cyclomatic-complexity
>   estimate, injected into the Planner prompt
>   (`CFG_ANALYSIS_ENABLE` default true — pure incremental info that
>   does not change the LLM call count; set false to fall back to the
>   historical caliber); PlannerAgent.plan calls it automatically.
> - **I. 1.4 Lightweight event bus**: `src/graph/event_bus.py`
>   pure observation side-channel layer (`EVENT_BUS_ENABLE` default
>   true, does not alter LangGraph routing): five event types
>   (PlanGenerated / TestsExecuted / PatchApplied /
>   DebuggerDiagnosed / WorkflowCompleted), thread-safe
>   publish-subscribe + exception isolation; one-line wiring at
>   each node's tail; `get_event_bus().stats()` observation
>   statistics wired into `get_workflow_stats` and the CLI `--json`
>   output.
> - **VI. 6.2 Trace visualization + replay**:
>   `src/utils/trace_viz.py` JSONL trace → self-contained HTML
>   timeline diagram (no external dependencies, openable offline) +
>   `replay_trace` restores the static decision path from a trace
>   (does not re-run the LLM; for offline analysis / regression
>   comparison / RL data prep).
> - **IV. 4.2 ADR directory**: `docs/adr/` (5 ADRs: LangGraph
>   StateGraph / error classifier pure-rules /
>   default-behavior-unchanged principle / zero default external
>   deps / node-exception degrade fallback).
> - **IV. 4.4 Bilingual docs sync check**:
>   `scripts/check_bilingual_docs.py` CI guard (.md ↔ .en.md pair
>   completeness + update-date consistency + section-count rough
>   alignment; exemption list for non-core docs).
> - **VI. 6.1 CLI --json enhancement**: `src/cli/app.py` --json
>   output gains `event_bus` / `cost_budget` / `semantic_cache`
>   observation-statistics fields (pure observation, for pipeline /
>   script consumption); rich output and progress bar already exist
>   (requirements.txt includes rich==15.0.0).
>
> New `tests/test_new_modules_2026_09_28.py` (36 cases); full 2044
> tests passing (previously 2008, +36) / ruff repo-wide 0 warnings /
> mypy 70 source files 0 errors.

## [Unreleased] - 2026-09-28 P0/P1 improvement batch (post-processing layer / strategy mapping / budget caps / semantic cache / smoke script, default behavior unchanged)

> This batch lands five P0/P1 improvement items. **Default behavior
> unchanged** (all new capabilities behind independent env-var
> switches; when off, behavior matches the historical caliber
> exactly):
>
> - **I. 1.1 LLM output post-processing layer**:
>   `src/tools/patch_postprocess.py` auto-repairs common LLM code-
>   corruption patterns before patch application (complements the
>   1.3 contract-guard "rejection layer"; this layer is the "repair
>   layer"): P1 empty-shell patch detection (`EMPTY_PATCH_GUARD`,
>   enabled by default — turns the `EMPTY_LLM_PATCH` scenario from
>   unobservable into a recognizable label in
>   `state.postprocess_labels`); P2 import-break repair
>   (`IMPORT_REPAIR_ENABLE`, default off — lost top-level import
>   lines are auto-backfilled at the patch head, only when the
>   original code body still references that module); P3 contract-
>   symbol alias backfill (`CONTRACT_ALIAS_ENABLE`, default off —
>   when the LLM renames `Rule_L001→RuleL001`, backfill a
>   `Rule_L001 = RuleL001` alias so the import chain / plugin
>   registration stay intact). Wired into the single-file branch of
>   `_patch_applier_node` (multi-candidate / cross-file branches do
>   not re-sanitize).
> - **II. 2.1 Explicit error-class → repair-strategy mapping**:
>   `get_recommended_fix_strategy(category, context)`
>   (`src/agents/error_classifier.py`) converges "which repair path
>   to take" from the implicit branches scattered across
>   workflow/debugger into structured classifier output labels
>   (`strategy` snake_case label + 4-tier `repair_action`:
>   llm_resample / repair_code / repair_test / investigate_infra),
>   with explicit coverage of all 17 categories;
>   `_debugger_node` writes the labels into state
>   (`fix_strategy_tag` / `fix_strategy_action`), consumable by
>   experiment analysis for "which error category took which repair
>   path".
> - **III. 5.4 Task-level cost budget hard cap**:
>   `src/graph/cost_budget.py` (thread-local accumulation,
>   independent per task under --parallel) — `COST_BUDGET_ENABLE`
>   (default false) + `COST_BUDGET_TOKENS` / `COST_BUDGET_USD`
>   (+ `COST_USD_PER_1K` pricing); on overrun,
>   `BaseAgent._call_llm` pre-guard raises `BudgetExceededError`;
>   planner / generator / debugger nodes degrade with a fallback
>   (no more idle token burn). Independent of the 3.4 cost alert
>   (routing-side side-band observation), stackable.
> - **IV. 5.1 Semantic-level LLM cache**:
>   `src/agents/semantic_cache.py` embedding-vector similarity match
>   (reusing `embedding_utils`' CodeBERT → sentence-transformers →
>   chromadb cascading backends); semantically identical but
>   differently worded prompts can reuse cached responses;
>   `SEMANTIC_CACHE_ENABLE` (default false) /
>   `SEMANTIC_CACHE_THRESHOLD` (default 0.92 conservative caliber) /
>   `SEMANTIC_CACHE_MAX_ENTRIES` (default 256); when the embedding
>   backend is missing, auto-degrades to the exact-cache caliber
>   (zero behavior change); hit statistics via
>   `get_semantic_cache_stats()`.
> - **V. 3.3 End-to-end smoke test script**:
>   `scripts/smoke_test.sh` one-key verification S1 config load →
>   S2 core-module import → S3 ruff → S4 quick unit tests
>   (`--full` for the full suite) → S5 minimal generation flow
>   (Planner + Generator real LLM calls, `--no-llm` for pure
>   offline mode).
>
> New `tests/test_patch_postprocess.py` (23 cases) /
> `tests/test_cost_budget.py` (12 cases) /
> `tests/test_semantic_cache.py` (14 cases) + expanded
> `tests/test_error_classifier.py` (full 17-category strategy-
> mapping guard); docs synced: `docs/api_reference.md` /
> `docs/failure_analysis.md` / `QUICKSTART.md` / `.env.example`.
>
> Quality baseline: full 2008 tests passing (previously 1937, +71) /
> ruff repo-wide 0 warnings / mypy 67 source files 0 errors /
> coverage 88% (TOTAL; new modules: patch_postprocess 92% /
> cost_budget 93% / semantic_cache 90% / error_classifier 94%).

## [Unreleased] - 2026-09-28 Improvement checklist full batch (P0/P1/P2/P3, default behavior unchanged, new capabilities all behind independent switches)

> This batch implements the user-submitted 24-item improvement checklist
> (across 7 dimensions: architecture/algorithm, engineering practice, test
> quality, docs/UX, performance/scalability, security/compliance,
> feature/ecosystem), executed in P0→P3 priority order, **default behavior
> unchanged** (new capabilities all behind independent switches; when
> disabled, historical behavior is byte-equivalent):
>
> - **P0 doc baseline / CI infra**:
>   - `README.md` / `README.en.md` "Test Status" number-drift fix — removed
>     hardcoded numbers (`2046 passed` / `line coverage 89%` etc.), now
>     uniformly point to `BASELINE.yaml`; new drift guard
>     `scripts/check_baseline_numbers.py` (regex-scans the "测试状态 /
>     Test Status" H2 section only; historical "迭代优化记录" section is
>     exempt) + CI step integration;
>   - `BASELINE.yaml` structural validator `scripts/check_baseline.py`
>     (required fields / `total_failed==0` / coverage range /
>     `ruff_warnings`/`mypy_errors`==0 / `last_verified` date format +
>     `--verify` re-measures full pytest count);
>   - Static report auto-refresh `scripts/generate_static_report.py` —
>     runs ruff/mypy snapshot, archives to
>     `docs/history/static_report_<YYYY-MM-DD>.md`; CI main-branch
>     3.14 matrix uploads artifact.
> - **P1 algorithm / security**:
>   - Branch-coverage backfill + core routing module gate:
>     `BASELINE.yaml` backfills `branch_total_pct` and
>     `branch_core_routing` blocks; new
>     `scripts/check_branch_coverage.py` (parses coverage.xml
>     `<class filename branch-rate>` structure, overall gate 79%, core
>     4 modules 85%) + combinatorial routing tests
>     `tests/test_branch_coverage_gates.py` (26 cases covering
>     `_should_debug` / `refine_failure_category` / `rag.py` degradation
>     guards);
>   - LLM file-cache permission hardening + TTL expiry cleanup:
>     `llm_client.py` adds `ensure_llm_cache_dir` (new dirs 0o700,
>     existing dirs untouched) / `secure_cache_file` (temp file 0o600) /
>     `cleanup_expired_cache_files` (mtime-based, deletes `*.json` older
>     than TTL, `AITESTER_LLM_CACHE_TTL_DAYS` default 7 days); wired into
>     `base_agent.py` / `cross_file.py` write paths + `workflow.py`
>     startup cleanup; new `tests/test_cache_security.py` (9 cases);
>   - Error classifier confidence layering: `error_classifier.py` adds
>     `classify_with_confidence` / `ClassificationResult` / L2
>     `ProbabilisticClassifier` protocol (currently always None;
>     implementing L2 requires a separate ADR) + low-confidence fallback
>     strategy (confidence ≤ 0.5 converges to `generic_analysis` instead
>     of hard routing); module-level convenience function +
>     `tests/test_error_classifier_confidence.py` (17 cases); ADR-0002
>     "Known Limitations & Evolution Directions" notes the minimal
>     confidence layer is now landed.
> - **P2 closed-loop / testing / integration**:
>   - Failure knowledge base minimal closed loop: new
>     `src/agents/failure_kb.py` (landing point B online consumption +
>     frequency × time-decay ranking), `_debugger_node` injects
>     same-category case snippets via `kb_debugger_snippet`
>     (`FAILURE_KB_ENABLE` default off, historical prompt byte-equivalent);
>     `analyze_failures.py` entries get `last_seen` timestamp; state gets
>     `kb_prompt_snippet_applied` observation key;
>     `failure_knowledge_feedback.md` design doc marks M1 as landed;
>     11 new test cases in `tests/test_failure_kb.py`;
>   - LLM output format anomaly injection test suite:
>     `tests/test_llm_format_anomaly.py` (17 cases: empty response /
>     truncated / missing fields / invalid patch semantics / markdown
>     wrapping, pure parse-layer + classifier assertions, zero LLM calls);
>   - `--smoke-llm` optional CI job: `experiments/run_smoke_llm.py` +
>     CI `smoke-llm` job (default `AITESTER_SMOKE_LLM=false`, zero LLM
>     cost) + `tests/test_smoke_llm.py` (11 cases);
>   - Multiprocess cache coordination: `llm_client.py` hit-rate
>     observation layer (`record_cache_hit` / `get_cache_hit_rate` /
>     `reset_cache_hit_stats`, thread-safe) + `workflow.get_workflow_stats`
>     attachment + `performance_guide.md` pre-warm / switchover guidance;
>   - Bilingual doc H2 skeleton structural comparison:
>     `scripts/check_bilingual_docs.py` adds section-order drift
>     detection (number-stripping + lowercasing + subsequence inversion);
>   - ADR index: `docs/adr/README.md` + `algorithm_design(.en).md`
>     mapping table gains "Related ADR" column;
>   - CI/CD integration examples: `docs/integration/README.md` +
>     `.git-hooks/pre-commit.sh` (runs CI-equivalent guards before local
>     commit).
> - **P3 design docs (no code landed, default behavior unchanged)**:
>   - `docs/design/multilanguage_extension.md` (multi-language extension
>     architecture reservation: LanguageBackend abstraction + registry +
>     default Python backend with zero change);
>   - `docs/design/hierarchical_summary.md` (long-file hierarchical
>     summarization strategy: Level 0-3 static + optional LLM summary +
>     degradation chain + default-off switch).
> - **Full regression**: 2165 tests passed / 0 failed (~100 new cases vs
>   the pre-batch 2065); ruff 0 warnings; mypy 0 errors (70 source
>   files); `BASELINE.yaml` refreshed (`total_passed: 2165` /
>   `branch_total_pct: 80` / `mypy_source_files: 70`).
>
> New regression tests added in this batch (~100 total):
> `test_cache_security.py` (9) / `test_error_classifier_confidence.py`
> (17) / `test_failure_kb.py` (+11) / `test_llm_format_anomaly.py` (17) /
> `test_smoke_llm.py` (11) / `test_branch_coverage_gates.py` (26) /
> `test_check_baseline_numbers.py` (7).

## [Unreleased] - 2026-09-28 Improvement checklist batch (doc consistency / infra / eval / observability / security, default behavior unchanged)

> This batch implements the user-submitted improvement checklist
> (doc consistency / infra / core algorithm / UX / eval / security /
> observability), **default behavior unchanged**:
>
> - **I. Single source of truth for baselines**: new `BASELINE.yaml`
>   (machine-readable: full pytest count / line coverage / static checks /
>   CI matrix / 17 error categories); all "current baseline" numbers in
>   core docs (README / QUICKSTART / api_reference / algorithm_design /
>   usage_examples) now reference this file, eliminating multi-doc
>   drift; version-history tables (CHANGELOG / api_reference) record
>   snapshots at their time and are NOT refreshed by this file.
> - **II. CONTRIBUTING hard rules + dependency-change checklist**:
>   `CONTRIBUTING.md` / `.en.md` gain "BASELINE.yaml single source" and
>   "dependency change checklist" subsections; new
>   `.github/PULL_REQUEST_TEMPLATE.md` (with dependency-change checklist).
> - **III. Stale inline baseline numbers stripped**:
>   `docs/usage_examples.md` / `docs/algorithm_design.md` /
>   `docs/code_analysis_report.md` / `docs/failure_analysis.md` (+ `.en`)
>   replace hardcoded numbers with references to `BASELINE.yaml` /
>   CHANGELOG / `docs/history/`.
> - **IV. Concurrency & multi-process cache semantics doc**:
>   `docs/performance_guide.md` / `.en.md` gain a "3.5 Concurrency &
>   Multi-Process Cache Semantics" section (L1 negative cache
>   process-level visibility ≤30s TTL; `--parallel` multi-thread mode
>   maximizes cross-process cache hits).
> - **V. Cross-file repair graduation criteria**:
>   `docs/design/cross_file_repair.md` / `.en.md` gain "4.5 Graduation
>   Criteria" — T1 ≥+15pp vs single-file, T2 token ≤1.5x, T3 2 model
>   tiers, T4 no regression; all four must pass before default enable
>   (`CROSS_FILE_ENABLE` stays default off).
> - **VI. Error-classifier evolution directions**:
>   `docs/adr/0002-error-classifier-rules.md` gains "Known limits &
>   evolution" — hierarchical (17-class coarse → subclass refinement),
>   probabilistic top-2 + confidence, UNKNOWN ≤15% SLA; current rule-
>   based classifier unchanged.
> - **VII. Failure-KB closed-loop design doc**: new
>   `docs/design/failure_knowledge_feedback.md` (offline → online KB
>   closed loop, design only, no code).
> - **VIII. Model-capability-gradient experiment orchestrator**: new
>   `experiments/model_gradient.py` (task-count 5-10, 2-3 tiers, runs
>   `run_benchmark` per tier, records `llm_applied` / first-attempt
>   success / avg iterations, writes
>   `experiments/results/model_gradient.md`) + result-table template.
> - **IX. New-contributor bootstrap script**: new
>   `scripts/bootstrap_dev.sh` (venv + install + env copy + config
>   validation; `--check-only` / `--no-install`); one-line pointer
>   added to `QUICKSTART.md` / `.en.md`.
> - **X. Runnable capability demos**: new
>   `examples/semantic_cache_demo/` / `examples/cost_budget_demo/` /
>   `examples/rag_ab_demo/` (all offline, no real LLM endpoint) +
>   `examples/README.md` index.
> - **XI. CI branch coverage**: `.github/workflows/ci.yml` test step
>   gains `--cov-branch` (previously line-only); `BASELINE.yaml`
>   `branch_total_pct` to be backfilled after first CI measurement.
> - **XII. Trace in-memory snapshot + failure-diagnostics CLI**:
>   `src/observability/trace.py` gains a process-level ring buffer
>   (capacity 64; `TRACE_MEMORY_BUFFER_ENABLE` default true but **never
>   writes to disk, zero I/O**; when off, fully no-op as before) — even
>   when `AITESTER_TRACE_DIR` is unset (file tracing fully no-op), each
>   task's "minimal node snapshot" accumulates in memory, available to
>   `dump_recent_to(target_dir)` for writing a temporary JSONL
>   (`./tmp_trace/<ts>_failed_trace.jsonl`) on failure. `src/cli/app.py`
>   gains `--dump-trace-on-failure` CLI flag (default false, zero I/O;
>   when enabled, writes only on task failure and adds a
>   `trace_dump_path` field to the `--json` result). `src/graph/
>   tracing.py` `end_task_trace` feeds the buffer; `start_task_trace`
>   preserves the historical "no session in thread-local when file
>   tracing disabled" convention (no TraceSession instance allocated).
> - **XIII. APIManager adaptive health-check concurrency**:
>   `APIManagerConfig` gains `adaptive_health_check_concurrency`
>   (default **false** — static `batch_health_check_concurrency`
>   historical behavior unchanged) + 3 helper thresholds
>   (`adaptive_health_node_threshold` default 50 /
>   `adaptive_health_concurrency_max` default 8 /
>   `adaptive_health_failure_rate_downshift` default 0.3); when enabled,
>   concurrency is dynamic — large pool + low failure rate → 8,
>   rising failure rate (≥ 0.3) → downshift to serial, first round
>   with no history → conservative serial start. `health_check_batch`
>   records this round's failure rate into
>   `_last_health_batch_failure_rate` (only when adaptive is on).
> - **XIV. Redaction boundary documentation**:
>   `docs/api_reference.md` / `.en.md` gain a "Redaction Boundaries &
>   Known Blind Spots" section — 5 covered channels (console logs /
>   trace JSONL / in-memory snapshot / `os.environ` process-level
>   credentials / LLM exception logs) + 4 known blind spots
>   (third-party gateway custom error bodies / custom credential
>   prefixes / plaintext in non-str nested meta values / redaction
>   import-failure degraded raw write) + manual verification steps.
> - **XV. Baseline number correction**: `BASELINE.yaml` records the
>   measured 2065 passed (slim ~1863) / 89% line coverage / ruff 0 /
>   mypy 0 (70 files) / error_categories 17; `CHANGELOG.md`'s 0.9
>   version table "1937 passed / 94% coverage" was a historical
>   snapshot inconsistent with the current measurement — this batch
>   unifies `BASELINE.yaml` as the single source of truth for
>   current numbers.
>
> New regression tests: `tests/test_api_manager.py::TestAdaptive
> HealthConcurrency` (9 cases) /
> `tests/test_trace_observability.py::TestMemoryBuffer` (5 cases) /
> `tests/test_cli_app.py::TestRunDumpTraceOnFailure` (5 cases);
> 2 existing cases in `tests/test_cli_app.py::TestRunParallelTimeoutAnd
> Interrupt` updated for the new `dump_trace_on_failure` parameter
> (`**kwargs` passthrough) on `_run_single_task`. Full test suite
> passing / ruff 0 / mypy 0.

## [Unreleased] - 2026-09-27 Roadmap gap-closing batch (SWE-bench Pro / CodeBERT / pyright, default behavior unchanged)

> This batch closes the 3 remaining roadmap gaps identified after the
> 2026-09-27 Round 11 audit, **default behavior unchanged** (new
> backends / datasets each have dedicated env-var switches or reuse an
> isomorphic loader; missing optional dependencies degrade gracefully):
>
> - **V. SWE-bench Pro support**:
>   `experiments/contamination_check` resistant-benchmark registry gains
>   `swe-bench-pro` (strong copyleft design, GPT-5 Pass@1 ~23.3%;
>   report paired with SWE-bench Verified);
>   `src/datasets/dataset_loader` registers `swe_bench_pro` /
>   `swebench_pro` (reuses `SWEBenchDataset`, data dir injected via
>   `data_dir`, same isomorphic convention as `swe_rebench`).
> - **V. CodeBERT embedding backend**:
>   `src/utils/embedding_utils` gains a `codebert` backend
>   (`transformers.AutoModel` loading `Salesforce/codebert-base`,
>   overridable via `EMBEDDING_CODEBERT_MODEL`; `auto` priority is now
>   codebert → sentence_transformers → chromadb; conservatively falls
>   back when `transformers`/`torch` are missing, no new hard deps).
> - **II. pyright static-type backend**:
>   `src/tools/type_repair` gains `_run_pyright_findings` +
>   `TYPE_CHECK_BACKEND` (default `mypy` unchanged; `pyright` probes
>   the pyright CLI / pyright-python, findings share the mypy schema
>   with `pyright_` kind prefix; unavailable → conservative fallback
>   to the ast static layer).
>
> New `tests/test_roadmap_gaps_g1_g2_g3.py` (20 cases);
> synced `tests/test_dataset_loader.py` dataset-name list and
> `tests/test_embedding_utils.py` backend-priority assertions.
> Full suite 1909 tests pass, ruff / mypy clean.
>
> Companion audit doc: `docs/roadmap_2026-09-27_gap_audit.md`
> (per-section grep/read verification of the 7-section roadmap,
> evidence cited as file:line; verdict: 6 sections landed, ⑤ had 3
> sub-item gaps = this batch's closing targets; English version
> `.en.md`), plus a follow-up pointer added to the header of
> `docs/assessment_2026-09-25_improvement_directions.md`.

### V. SWE-bench Pro support

- `experiments/contamination_check.py`: `CONTAMINATION_RESISTANT_BENCHMARKS`
  registry gains the `swe-bench-pro` entry (`display_name` /
  `resistance_mechanism` with the copyleft anti-contamination note /
  `recommended_pairing` = `swe-bench-verified`);
  `render_resistant_benchmark_section` picks it up automatically.
- `src/datasets/dataset_loader.py`: `load_dataset` registers
  `swe_bench_pro` / `swebench_pro` → `SWEBenchDataset` (isomorphic
  fields, data dir via `data_dir`); `get_available_datasets` updated.

### V. CodeBERT embedding backend

- `src/utils/embedding_utils.py`: `_load_backend` gains a `codebert`
  branch (`transformers.AutoModel` + `AutoTokenizer`, L2-normalized
  `[CLS]` hidden state as the semantic embedding, conservative
  512-token truncation); `EMBEDDING_BACKEND=codebert` now effective,
  `auto` prioritizes codebert; `EMBEDDING_CODEBERT_MODEL` overrides
  the default model name; falls back transparently when
  `transformers` / `torch` are missing.

### II. pyright static-type backend

- `src/tools/type_repair.py`: new `_run_pyright_findings` (probes the
  `pyright` CLI / `pyright-python`, `--outputjson` parsing with a
  per-line text fallback, high-confidence rule whitelist, `pyright_`
  kind prefix) + `_static_type_check_backend`
  (`TYPE_CHECK_BACKEND`, default `mypy`); `type_repair_layer` picks
  the mypy / pyright layer per backend, falls back to the mypy
  convention when pyright is unavailable, and degrades to the ast
  static layer on all failure paths.

## [Unreleased] - 2026-09-27 Round 11: Error classification 16→17 + 2.2 patch resample + 1.3 downgrade-chain propagation + V contamination detection + 2.1 mypy static layer (default behavior unchanged)

> This batch follows the 2026-09-27 Round 10 full-project audit
> (commit `a1a06ec`). It contains 6 directions of feature enhancements
> and type/lint fixes, **default behavior unchanged** (all new features
> have dedicated environment-variable switches, off by default; fixes
> only correct hidden defects such as the `on_resample` key argument):
>
> - **5.2 Error classification 16 → 17 categories**: added
>   `PATCH_SYNTAX_INVALID` (resample-exhausted marker);
>   `refine_failure_category` / `refine_final_error_category` gain a
>   `patch_syntax_invalid` parameter; tests updated accordingly.
> - **2.2 Patch post-processing resampling**: when
>   `PATCH_RESAMPLE_ENABLE=true`, `_patch_applier_node` triggers
>   `apply_patch_with_resample` (up to `PATCH_RESAMPLE_MAX` times) on
>   application failure, then marks `patch_syntax_invalid` if still
>   failing.
> - **1.3 Layered-compression downgrade-chain propagation**:
>   `contract_reject_feedback` is propagated cross-round through
>   `_debugger_node`; `debug()` gains the parameter +
>   `_build_downgrade_context` + tier temperature mapping;
>   `AITesterState` declares `contract_reject_feedback` /
>   `contract_missing_symbols` / `patch_resample_stats` /
>   `patch_syntax_invalid_flag`.
> - **V, Multi-dimensional contamination detection**:
>   `run_benchmark._build_task_result` gains a
>   `contamination_risk_level` field (high/medium/low);
>   `rag_ab_experiment.compare_ab` gains `token_saving.delta_pct`.
> - **2.1 mypy static layer**: when `TYPE_CHECK_ENABLE=true`,
>   `type_repair._run_mypy_findings` adds layered type findings;
>   fixed `contextlib` import and SIM105 lint.
> - **Fixes + type zero-out**: `on_resample` → `resample_fn` key
>   argument fix (2.2 resampling was silently disabled);
>   `build_tiered_context` tier-0 returns `str | None` → `str`
>   (`... or ""`); whole-repo mypy 0 errors, ruff all green.
>
> Full 1937 tests pass (baseline 1920 + 17 new), zero regressions;
> ruff / mypy all green (64 source files); CI green.

### 5.2 Error classification 16 → 17 categories (add `PATCH_SYNTAX_INVALID`)

- `src/agents/error_classifier.py`: `ErrorCategory` enum adds
  `PATCH_SYNTAX_INVALID` (resample-exhausted marker, identifies the
  "patch syntax repeatedly corrupted" scenario);
  `refine_failure_category` / `refine_final_error_category` gain a
  `patch_syntax_invalid` parameter; precedence
  `patch_rejected > rag_empty > trace_missing > multi_rejected > patch_syntax_invalid`.
- `tests/test_error_classifier.py`: `test_seventeen_categories_total`
  locks the 17-category total + `PATCH_SYNTAX_INVALID` value.

### 2.2 Patch post-processing resampling (`PATCH_RESAMPLE_ENABLE`)

- `src/graph/nodes.py`: `_patch_applier_node` triggers
  `apply_patch_with_resample` on application failure (up to
  `PATCH_RESAMPLE_MAX` times, default 2); marks `patch_syntax_invalid`
  if still failing (consumed by `refine_failure_category`).
- `src/tools/patch_applier.py`: fixed `apply_patch_with_resample` key
  parameter `resample_fn` (callers previously passed `on_resample`
  causing 2.2 resampling to silently fail; default-off unaffected);
  `apply_patch_with_resample` supports `resample_fn` callback
  injection (LLM negative-feedback resampling).
- `tests/test_improvements_1_2_2_1_2_2_4_3.py`: regression guards lock
  the resampling path.

### 1.3 Layered-compression downgrade-chain propagation (`CONTEXT_TIER_DOWNGRADE_ENABLE`)

- `src/graph/state.py`: `AITesterState` declares `contract_reject_feedback` /
  `contract_missing_symbols` / `patch_resample_stats` /
  `patch_syntax_invalid_flag` (with `create_initial_state` default values).
- `src/graph/nodes.py`: `_debugger_node` propagates
  `contract_reject_feedback` to `debug()`; `_patch_applier_node` writes
  tier feedback + missing-symbol list when the symbol guard rejects;
  `on_resample` key argument fix.
- `src/agents/debugger.py`: `debug()` gains `contract_reject_feedback`
  parameter + `_build_downgrade_context` + tier temperature mapping;
  `_downgrade_tier_temperature` reads
  `patch_applier._CONTEXT_TIER_TEMPERATURES`; observation fields
  `mypy_findings_count` / `downgrade_triggered` / `downgrade_tier`.
- `tests/test_roadmap_13_22_21_mypy_5.py` (new): tier advance /
  resample wiring / mypy static layer / downgrade-chain propagation
  regression guards.

### V, Multi-dimensional contamination detection + Token efficiency

- `experiments/run_benchmark.py`: `_build_task_result` adds
  `contamination_risk_level` field (high/medium/low, conservative
  "low" without golden patch); `_compute_contamination_risk_level`
  calls `patch_semantic_similarity` multi-dimensional detection;
  failure branch uses None fallbacks (key-set isomorphism).
- `experiments/rag_ab_experiment.py`: `compare_ab` adds
  `token_saving.delta_pct` (RAG ON vs OFF token consumption reduction
  percentage).

### 2.1 mypy static layer (`TYPE_CHECK_ENABLE`)

- `src/tools/type_repair.py`: `_run_mypy_findings` adds layered type
  findings (transparently degrades to empty list when mypy not
  installed, does not block the ast static layer); fixed `contextlib`
  import and SIM105 lint (`try/except OSError: pass` →
  `contextlib.suppress(OSError)`).

### Fixes + type zero-out

- `src/tools/patch_applier.py`: `build_tiered_context` tier-0 branch
  returns `str | None` → `str` (`extract_function_context(...) or ""`,
  conservative degradation, behavior-equivalent).
- `src/agents/debugger.py` / `src/graph/nodes.py`: `cast` narrowing for
  `dict[str, Any] | None` union-attr (mypy green, zero behavior
  change).
- Whole-repo ruff 8 lint issues + mypy 12 type errors zeroed (64
  source files).

## [Unreleased] - 2026-09-27 Ninth-batch parallel subagent deep-audit + Tenth-batch full-project P1/P2 convergence (default behavior unchanged)

> This round follows the 2026-09-26 six-batch full audit (commit `9526fd0`),
> consolidating a conservative-optimization batch driven by 4 parallel subagents
> (agents / tools / cli+reports+config+utils+db / experiments).
> Default behavior unchanged throughout.
> Full 1920 tests pass (baseline 1861 + 26 new round-9 regression guards +
> 33 new round-10 regression guards + companion fixes), zero regressions;
> ruff / mypy all green (62 source files).

### Ninth-batch parallel subagent deep-audit (default behavior unchanged)

> 4 parallel subagents audited post-round-8 code + main-agent one-by-one
> reproduction; yielded P1×4 + P2×10 + 26 new regression guards
> (tests/test_2026_09_26_review_round9.py).
> Full 1887 tests pass (baseline 1861 + 26 new + 4 companion fixes),
> zero regressions; ruff / mypy all green.

#### P1 defect fixes (4, regression-guarded)

- `src/tools/patch_applier.py` (P1: single-function import prefix misclassified as full-file mode):
  A single-function patch with a local import inside the function body, where that local-import line lands within the first 200 characters of the patch text, was misclassified as full-file mode (the first-200-chars check saw an import line). Top-level imports were silently dropped, producing corrupted code with duplicate or missing imports.
  Now uses `MULTILINE` line-start `^import|^from` probing (`_TOP_IMPORT_RE`), same caliber as `_TOP_DEF_RE` — only true top-level imports (at column 0) trigger the full-file-mode decision; in-body local imports no longer mis-trigger.
  Default behavior unchanged (normal synchronous-def dataset scenarios unaffected; the misclassified path changes from "silently drop imports" to "correctly identified as single-function patch"). 3 regression guards.
- `src/tools/multi_candidate.py` (P1: all-candidates-failed still writes degraded code):
  Under execution-validation mode (`MULTI_CANDIDATE_EXEC_VALIDATE=true`), when all candidate patches have `exec_passed=False` (none passes test validation), the old implementation still returned the "least-bad" candidate and wrote degraded code to the target file — worse than the original code.
  Now guarded: all-candidates-failed returns `None`, and the caller (`_select_multi_candidate_patch` node) falls back to the single-patch path (no write or write-back original code).
  Default behavior unchanged (execution-validation mode off by default; normal scenarios unchanged; all-failed scenario changes from "write degraded code" to "conservative rejection"). 3 regression guards.
- `src/tools/dependency.py` (P1: venv cache race):
  `create_venv` cache-hit-check + creation sequence (`os.makedirs` + `venv.create` + `pip install`) had no lock. Under `--parallel`, multiple threads creating the same cache directory simultaneously could both determine "cache does not exist" and duplicate creation, or one thread's `pip install` could interleave with another thread's `os.makedirs`, causing race damage.
  Now uses a per-directory lock (`_get_venv_dir_lock(cache_dir)`); different directories do not block each other; the same directory serializes the cache-check + creation sequence.
  Default behavior unchanged (single-thread unchanged; concurrent scenario eliminates cache-directory race). 2 regression guards.
- `src/agents/executor_repo.py` (P1: temp-file contention + setup race):
  A. `verify()` temp test file name was keyed only on `(commit, pid)`. Under `--parallel` multi-threading with the same pid (multiple threads in one Python process), one thread's `os.remove` could delete another thread's `git apply` in progress on the temp test file.
  Now adds thread-ident as a third key: `(commit, pid, thread_ident)`, isolating multi-thread.
  B. `setup()` clone/venv/pip sequence had no lock; `--parallel` concurrent same `env_dir` could duplicate clone + duplicate pip install.
  Now adds per-env_dir lock (`_get_repo_setup_lock(env_dir)`), re-checking cache inside the lock to avoid duplicate operations.
  Default behavior unchanged (single-thread unchanged; concurrent scenario eliminates temp-file overwrite + setup duplication). 4 regression guards.

#### P2 changes (10, all default-behavior-unchanged)

- `src/agents/debugger.py`: Two consecutive malformed-JSON responses made `_extract_json` always raise `JSONDecodeError`, crashing the entire Debugger node. Now try/except degrades to empty patch + critic requery same guard.
- `src/agents/executor_runtime.py`: Generic-exception branch nullified the first-attempt `last_result` (losing the real test output). Now keeps the most-recent valid result; when no valid result exists, returns `(UNAVAILABLE, error_info)` marker, caller handles it via the same branch as EARLY_RETURN.
- `src/tools/patch_applier.py`: `_find_function_start_line_in_lines` regex lacked the async prefix (async target functions misjudged as not-found). Now adds `(?:async\s+)?` same caliber as `_TOP_DEF_RE`.
- `src/tools/multi_candidate.py`: `_coverage_trend` crashed on non-numeric `coverage_delta` (e.g. "n/a"). Now try/except skips non-numeric deltas.
- `src/agents/generator.py`: Per-call `re.compile` replaced with module-level precompiled `_FROM_IMPORT_RE` (pure performance optimization).
- `experiments/analysis_parts/convergence_analysis.py`: Without per-round details, `total_tokens` was double-counted in each round causing negative deltas. Now each task's total is counted once at its final-reached round; increment taken directly from the current round_tokens (no longer `round_tokens - prev_cumulative` subtraction); `cumulative` accumulates raw `round_tokens`.
- Experiment files hardening (11 files): `experiments/analyze_failures.py` / `analyze_results.py` / `compare_failures.py` / `contamination_check.py` / `difficulty_stratification.py` / `mutation_testing.py` / `run_benchmark.py` / `statistical_analysis.py` / `visualize_results.py` — non-numeric reward_signals / coverage / difficulty_level fields in various experiment-analysis modules had bare `float()` / `int()` crash points; now unified try/except guards, non-numeric values skipped and not counted into means.
- `tests/test_debugger.py`: Updated malformed-JSON test case (degradation instead of exception).
- `tests/test_weak_coverage_modules.py`: Updated generic-exception assertion (UNAVAILABLE marker).
- `tests/test_2026_09_26_review_round9.py`: 26 new regression-guard cases (covering P1×4 + P2×10 all change points + default-path-unchanged verification).

### Tenth-batch full-project P1/P2 convergence (default behavior unchanged)

> 4 parallel subagents (graph / api / datasets / tools / agents full-domain deep-audit) + main-agent one-by-one reproduction; yielded P1×6 + P2×13 + 33 new regression guards.
> All changes only converge "silent corruption / semantic regression / unbounded ping-pong / cache invalidation / timeout leak" class defects; normal-path behavior unchanged. Full 1920 tests pass (baseline 1887 + 33 new regression guards), zero regressions; ruff / mypy all green (62 source files).

#### P1 defect fixes (6, regression-guarded)

- `src/graph/nodes.py::_suggest_iteration_strategy` (P1: non-numeric coverage_delta crash):
  Read `state.get("coverage_delta")` then bare `float(delta)` for iteration-strategy decision. Historical archived results may have `coverage_delta` as "n/a" (string), dict, or other non-numeric anomaly values; bare `float()` crashed the executor node, interrupting the entire workflow.
  Now try/except skips that entry (caliber: non-numeric delta treated as no-signal, same semantics as None); normal numeric path unchanged. 3 regression guards.
- `src/agents/base_agent.py::_lru_store` (P1: unbounded negative cache):
  `_lru_negatives` dict had no capacity cap; long-running benchmarks accumulated negative-cache entries without bound, causing unbounded memory growth.
  Now capped at the same `_LRU_MAXSIZE` as the positive cache, with FIFO eviction of the oldest negative-cache entries. 3 regression guards.
- `experiments/analysis_parts/rag_analysis.py::_rag_similarity_distribution` (P1: bins KeyError):
  When computing bins, `max_similarity` was a negative value (historical archive anomaly); the `bins` dict key calculation overflowed causing KeyError, crashing the entire `build_analysis`.
  Now lower-bound clamped to 0 (`max(0.0, max_similarity)`) + non-numeric `float()` try/except skip. 3 regression guards.
- `experiments/analysis_parts/convergence_analysis.py::_execution_trace_summary` (P1: non-numeric crash):
  Bare `float()` on `reward_signals` / `coverage` fields; "high" / "80%" / dict and other historical anomaly values crashed.
  Now `contextlib.suppress` skips non-numeric entries (caliber: non-numeric not counted into the mean). 3 regression guards.
- `experiments/statistical_analysis.py::_pair_by_task` (P1: cross-batch silent drop):
  Dict-derivation pairing; cross-batch duplicate `task_id` used "last-wins" in the old implementation, silently dropping early-batch entries (sample size truncated and indeterminate), making statistical-analysis results unreliable.
  Now first-seen dedup + warning log, ensuring sample size is traceable. 3 regression guards.
- `experiments/run_benchmark.py` summary (P1: None-value crash):
  Summary phase bare `r["iterations"]` / `r["elapsed_seconds"]` caused KeyError/TypeError crash when keys exist but values are None (historical archives had some tasks not recording these fields).
  Now `r.get("iterations", 0) or 0` / `r.get("elapsed_seconds", 0) or 0` guard (default semantics: that task was not recorded, contributes 0); `total_time` synchronized. 3 regression guards.

#### P2 changes (13, all default-behavior-unchanged)

- `src/agents/executor_repo.py`: `verify()` flow comment and docstring "git stash" wording changed to the actual implementation "git checkout -- . / clean -fd" (grep confirmed no stash in verify body).
- `src/agents/executor_runtime.py`: `TimeoutExpired` branch — second timeout no longer overwrites the first valid pytest output; instead appends a `[timeout attempt N]` snapshot (aligned with round-9 generic exception append caliber; single-timeout scenario `last_output` was originally an empty string, result unchanged).
- `src/agents/generator.py::_fix_import_module`: Dotted-path (pkg.mod) bare substring `code.replace` also mis-edited package-form `from pkg import mod` (leaving corrupted imports). Now uses a module-name-anchored regex (same caliber as `executor_imports`), only replacing the exact `from {wm} import` line start.
- `src/cli/app.py`: `--verbose + --json` combination: `--json` silences stdout making DEBUG log output impossible; the old implementation silently swallowed the flag conflict. Now explicitly notices that verbose is ineffective in `--json` mode.
- `src/datasets/dataset_loader.py`: `total_test_count` fallback caliber: old `len(FAIL_TO_PASS)` denominator missed P2P (pass-rate underestimated). Now `len(F2P) + len(P2P)` (SWE-bench official "total = F2P + P2P" semantics); when the official field exists, the official value takes precedence.
- `src/reports/generator.py`: `error_context` None fields rendered "None" (semantically unclear); now renders "unknown" / "—" (both `to_text` and `to_markdown` formats aligned).
- `src/tools/code_context.py::_closure_names`: depth=N caliber documented (N levels of called functions; focus itself is level 0; boundary level N+1 function names enter key but are not expanded).
- `experiments/analysis_parts/convergence_analysis.py`: Module-level `_safe_int` / `_safe_float` helpers + all bare `int()` / `float()` conversion sites (`_repair_convergence_curve` / `_metrics`, `_convergence_token_efficiency` including per-round-detail fallback, `_difficulty_stratified_iterations`, `_quality_proxy_metrics` mean/median, `_convergence_failure_modes`) unified safe normalization (non-numeric falls back to 0).
- `experiments/analysis_parts/rag_analysis.py`: `_iter_rag_stats` generator skips non-dict elements (historical archive / manual-edit JSON mixed in); 3 call sites updated. `_rag_token_efficiency` `iterations` / `total_tokens` normalized via `_safe_int` / `_safe_float`. `_rag_similarity_distribution` mean over the truncated [0,1] range (consistent with binning).
- `experiments/compare_failures.py`: `cross_batch_comparison`: `regressed` now excludes `new_categories` (brand-new categories [0,0,1] were simultaneously listed as "regressed" and "new", causing rendering-layer confusion).
- `experiments/run_benchmark.py`: L701 `results[baseline]["mutation_feedback"]` dead write (L711 `_build_task_result` replaced the entire dict, key disappeared). Dead write removed; only `final_state["mutation_feedback"]` retained (correctly consumed by the next-round Generator in the workflow).
- `experiments/statistical_analysis.py`: `run_all_statistics` distinguishes two NaN causes (n_pairs < 3 insufficient sample vs all-zero paired differences → zero variance); old text uniformly reported "n<3" causing misdiagnosis. `cohens_d` docstring corrected (n_pairs < 2 actually returns `(nan, n_pairs)` where n_pairs is 0 or 1; old doc claimed it always returns 0).
- `tests/test_2026_09_27_review_round10.py`: 33 new regression-guard cases (covering P1×6 + P2×13 all change points + default-path-unchanged verification).

#### Verified no-change-needed items (subagent-confirmed)

- `cross_file` topological sort (Kahn + lexicographic) / `from X import *` star-import edge omission (opt-in conservative caliber) / `code_context` same-name class-method conflict (conservative setdefault caliber) / `patch_applier` AST vs regex fallback path consistency / `type_repair` type-family conservative caliber / `multi_candidate` credit default 0.0 defensive writing / `dependency` `_importable_cache` lock-free double-read (idempotent, no damage) / `executor_imports` LRU invalidation (single-task sequential path not triggered) / `llm_client` zai dual-layer retry (deadline fast-fail mechanism pre-existing) — all are design-caliber or opt-in paths, default behavior unchanged, recorded for reference.

#### Deferred items (next round or needs decision)

- `is_similar_module_name` 0.6 threshold misfires on real third-party packages (needs find_spec guard vs raise threshold; decision needed)
- `patch_applier._TOP_DEF_RE` async prefix inconsistent with "line-start def" docstring (documentation)
- `credential_scrub` missing multi-vendor API key variants (needs vendor list completion)
- `config_manager._scan_llm_indices` comment-line interference (pure comment fix, low priority)
- `embedding_utils` cache DCL race (needs lock, low priority)
- RAG `_cleanup` capacity-floor double full-table get (performance optimization, low priority)
- `_RemoveNotTransformer` mainstream slot coverage (edge case, low priority)
- `analyze_failures` L508 vs L566 input inconsistency (needs caliber verification)

### Repo-wide ruff format normalization (14 files)

> Batch `ruff format` normalization of round-9 / round-10 changed files, covering `experiments/analysis_parts/convergence_analysis.py` / `experiments/compare_failures.py` / `experiments/statistical_analysis.py` / `src/agents/executor_repo.py` / `src/agents/executor_runtime.py` / `src/api/api_manager.py` / `src/graph/workflow.py` / `src/tools/code_analyzer.py` / `src/tools/patch_applier.py` / `src/tools/type_repair.py` / `tests/test_2026_09_26_review_optimizations.py` / `tests/test_2026_09_26_review_round8.py` / `tests/test_2026_09_26_review_round9.py` / `tests/test_2026_09_27_review_round10.py`.
> Pure format normalization, zero logic changes; full 1920 tests pass / ruff 0 warnings across the repo / mypy 62 source files 0 errors / 94% coverage.

---

## [Unreleased] - Full-audit & conservative-optimization round (2026-09-26: static-check zeroing + dead-code removal + thread hygiene + project hygiene + perf / correctness hardening + CF-3 cross-file repair defect fix + fifth-batch P0: mutation-test judging / API-poll reproducibility / atomic cache writes / single-agent baseline write guard + state schema + sixth-batch node-layer routing semantics & robustness + seventh-batch hot-path deep scan: AST-parse reuse / O(1) task index + shared combined text + precompiled keyword regex + eighth-batch closing audit: lint/format zeroing + type-repair contract-reference caliber + state-key propagation + example-file fixes + ninth-batch parallel subagent deep audit: difficulty_level normalization + _should_debug branch order + half-open probe double-count + async def patches + executor_repo temp-file race + tenth-batch repo-wide P1/P2 convergence: JSON leaf-fallback semantic regression + routing branch masking + full-file patch silent fallback + venv cache marker asymmetry + timeout leak + line-number offset + TOCTOU race + eleventh-batch legacy-debt convergence: cost_weight registration ordering + async safety-check rejection + 6 dead-code / ghost-config / thread-race items landed)

> Repo-wide code audit and conservative optimization batch (default behavior
> unchanged): static checks all green, dead-code removal, thread-hygiene fix,
> project-hygiene completion, perf / correctness fixes in un-deep-reviewed
> modules, the CF-3 cross-file repair "all modules share entry code"
> logic-defect fix, the fifth end-to-end wiring-batch P0 fixes
> (mutation-test kill judging, parallel API rotation reproducibility,
> LLM cache atomic writes, single-agent baseline write safety, state
> schema completion), the sixth-batch node-layer routing semantics &
> robustness (diagnosis-keyword early-iteration routing in `_should_debug`,
> `test_passed` consistency, generator LLM-failure degradation,
> planner/debugger fallback widened to OSError, cache-stat thread hygiene),
> the seventh-batch hot-path deep scan (eliminating duplicate AST parse in
> the code_context contract-block path, unifying the two parses in
> run_benchmark into one, O(1) task index + direct `_tasks` property access
> in dataset_loader, shared combined text in error_classifier,
> precompiled alternation regex for diagnosis keywords in workflow,
> TimeoutExpired closure promotion in executor_runtime,
> double-probe-window elimination in api_manager half-open probe, O(1)
> memory JSON-leaf fallback in helpers), the eighth-batch closing audit
> (repo-wide ruff lint / format zeroing + working-tree example fixes +
> type-repair contract-reference caliber + type_repair_findings state
> propagation + precompiled zai-domain regex + run_benchmark exception
> narrowing), the ninth-batch parallel subagent deep audit
> (4 parallel subagents auditing graph / api / tools / agents + main-agent
> review): P1×4 (difficulty_level normalization + _should_debug branch
> order + half-open probe double-count + executor_repo temp-file race) +
> P2×10 (async def patch locating + dead-code cleanup + comment fixes +
> ghost-switch comment cleanup + test sync), and the tenth-batch repo-wide
> P1/P2 convergence (4 parallel subagents auditing graph / api / datasets /
> tools / agents + main-agent repro-verification of every P1): P1×7
> (JSON leaf-fallback semantic regression + routing branch masking +
> full-file patch silent fallback + venv cache marker asymmetry +
> timeout leak + line-number offset + TOCTOU race) + P2×2. Full 1832-test
> suite passes (baseline 1813 + 19 new regression guards, one of which
> rewrites a legacy test that had locked the old silent-fallback
> semantics), zero regressions on default paths.

### Eleventh-batch legacy-debt convergence + P1 boundary fixes (default behavior unchanged)

> 4 parallel subagents (graph / api / tools / agents) deep-scanned the
> post-round7 code + main-agent single-point verification + all 6 items in
> the round7 "unlanded debt" list converged. P1×3 + P2×7 + 25 new
> regression guards (tests/test_2026_09_26_review_round8.py, 22 cases +
> TestPatchApplierEmptyFuncSetFullFile appended to
> tests/test_2026_09_26_review_optimizations.py, 3 cases). Full 1861-test
> suite passes (baseline 1832 + 25 new + 4 test-sync), zero regressions;
> ruff / mypy all green.

#### P1 defect fixes (3, regression-guarded)

- `src/api/api_manager.py::_cost_weight_for` (P1 registration-ordering,
  found by api subagent): `_init_clients` / `add_node` both call this
  method *before* the node enters `health_nodes`, so the internal
  `health_nodes.get(model_name)` is always None and the
  `LLMConfig.cost_weight` fallback branch (injected by config.py from
  `LLM_N_COST_WEIGHT` env var / `llm_configs.json`) never fires — the 3.4
  cost-aware routing was silently dead on the default registration path,
  all nodes pinned to 1.0. Added optional param
  `llm_config: LLMConfig | None = None`; call sites pass the in-hand
  config object, preferring its `cost_weight`; `None` keeps the original
  fallback chain (backward-compatible). Default behavior unchanged
  (unset cost info → `cost_weight=0.0` → still falls back to 1.0).
  Regression guard TestCostWeightForRegistration (6 cases).
- `src/graph/nodes.py::_HAS_FUNC_DEF_RE` (P1 safety-check rejection,
  found by graph subagent): the regex `^\s*def ` lacks the `async`
  prefix, contradicting the round7-unified
  `patch_applier._TOP_DEF_RE` / `_find_function_range_ast` / single-func
  by-name regex (all three include `(?:async\s+)?`) — patches for
  async-only target modules were misjudged "no function definition" and
  rejected at safety check 2, so `target_code` never updated and the
  repair loop burned tokens without converging. Now the prefix is added,
  unified with the three patch_applier sites. Default behavior unchanged
  (sync-def datasets keep the same hit caliber; only the async-only
  boundary flips from "false reject" to "correct accept"). Regression
  guard TestHasFuncDefRegAsync (4 cases).
- `src/tools/patch_applier.py::apply_patch_to_code` L212 (P1 empty-set
  rejection, found by tools subagent): the full-file-mode guard
  `if orig_func_names and orig_func_names.issubset(...)` short-circuits
  to False when `orig_func_names` is empty (original code has no top-level
  `def`, pure constants/imports module), so full-file replacement for
  such inputs could never reach the success path. L212 now reads
  `if not orig_func_names or orig_func_names.issubset(...)` (`∅.issubset`
  is True, empty-set case correctly passes; non-empty-set path unchanged);
  the L227 reject branch is kept (unreachable for empty-set, guard is
  harmless, commented). Default behavior unchanged (when the original
  code has `def`, `issubset` judgment is identical to before). Regression
  guard TestPatchApplierEmptyFuncSetFullFile (3 cases).

#### P2 changes (7, all default-behavior-unchanged)

- `src/api/api_manager.py` + `tests/test_api_manager.py`: removed the
  `_last_health_check` dict dead code (round7-verified dead — only
  initialized in `__init__`, no read/write points; the old "health-check
  rate-limit" role is superseded by `APIHealth.last_check_time`); 3 test
  initializations cleaned up in sync.
- `src/api/api_health.py` + `tests/test_api_manager.py` +
  `tests/test_api_manager_extended.py`: removed the `retry_count`
  ghost config (never read by production code; retry is driven by the
  `node_fail_count` loop in `APIManager.call`) + the
  `last_response_time_ms` dead field (no writer; empty-window fallback in
  `avg_response_time_ms` is equivalent to the default 0.0); 4 test
  assertions cleaned up; `avg_response_time_ms` empty-window caliber
  explicitly converged to 0.0 ("no data").
- `src/tools/dependency.py`: added a process-level lock around
  `_importable_cache` read-modify-write (round7 legacy debt landed) —
  eliminates the check-then-act race under `--parallel` multi-thread
  same-key probing (`find_spec` is idempotent, lock held for
  microseconds, judgment semantics unchanged).
- `src/tools/type_repair.py`: removed the `_EMPTY_CALLS` dead logic
  (right side of the `or` always returns None against an empty table,
  so the whole expression reduces to the left side — pure literal-type
  caliber); `for` / `async for` target collection now uses
  `sub.target` precisely (the old `iter_child_nodes` wide-match
  mis-collected the iter child node as a local name, masking real
  `undefined_attr`, and missed tuple targets i/j); `_builtin_allow` is
  now `set(dir(builtins))` (the old ~40 hard-coded names missed
  open/abs/iter, a false-positive source in the LLM layer).
  TYPE_REPAIR_LLM_ENABLE defaults off; the static layer is observation-
  only, default behavior unchanged.
- `src/graph/token_usage.py`: `record_usage` field read-modify-write is
  now atomic under a process-level `_usage_lock` (round7 legacy debt
  landed) — eliminates the lost-update window when `--parallel` threads
  concurrently accumulate into the same accumulator (pure in-memory,
  microseconds, accumulation semantics unchanged).
- `src/graph/workflow.py`: stale line-number references (L210/L340/
  L350/L354/L354-367/L360-366/L371-378) in the `_should_debug` /
  `_route_after_diagnosis` comments, drifted after the round7
  restructure, are now branch-descriptive references (comment-only,
  behavior unchanged).
- `tests/test_2026_09_26_review_optimizations.py` +
  `tests/test_2026_09_26_review_round8.py`: 25 new regression cases
  locking P1×3 + P2×4 + caliber records.

#### Verified no-change-needed items (subagent-confirmed, round7 conclusions kept)

- `src/agents/error_classifier.py::classify_with_context` full-set
  caliber (round7 already landed, comment L330-337 documents "aligned
  with extract"; `classify()` default path still truncates to first 3).
- `src/tools/code_analyzer.py::preserve_patch_ingredients` all fields
  (empirically correct; `called_signatures` slice exactly includes
  decorator lines + the def line, not the body first line).
- `src/tools/code_context.py::_apply_focus_budget` L211 (caller checks
  `focus_in_source` first, no KeyError).
- `src/tools/cross_file.py::_topological_order` parallel edges
  (in-degree accumulated per edge, released per edge, empirically
  correct); the class-definition regex covers `class Foo:` /
  `class Foo(Bar):` / `class Foo(Base, metaclass=M):`.
- `src/tools/multi_candidate.py::apply_multi_function_patch` (P13
  pre-split + (found, line) ascending + not-found last, semantics
  correct).
- `src/agents/executor_*.py` subprocess safety (all `subprocess.run`
  use list args, no `shell=True`, round7-verified).
- `src/graph/*` RAG DCL double-check lock / file-cache memory / state
  factory / tracing thread-local / 4-path graph build / `_should_debug`
  branch order / `_route_after_diagnosis` cap gate (round7-verified,
  kept this round).

### Tenth-batch repo-wide P1/P2 convergence (default behavior unchanged)

> 4 parallel subagents auditing graph / api / datasets / tools / agents +
> main-agent repro verification (each P1 confirmed via
> `.venv/bin/python` against the live code): P1×7 + P2×2 + test sync 1 +
> 13 new regression guards. All changes only converge silent-corruption /
> semantic-regression / unbounded-ping-pong / cache-invalidation /
> timeout-leak defects; normal-path behavior is unchanged.

#### P1 defect fixes (7, regression-guarded)

- `src/utils/helpers.py::extract_json_object` (P1 semantic regression):
  the 0.10 perf optimization changed the leaf-JSON fallback from
  `reversed(list(finditer))` to an O(1) two-candidate scan (tries only the
  last two leaves) — when the parseable leaf sits at an *earlier* position
  (corrupt response with ≥3 fragments, only the first valid) and the
  bracket-balanced pass fails (outer layer incomplete), the function raised
  `JSONDecodeError` and misjudged a parseable LLM response as failed (the
  main-chain parse fallback was silently broken). Added a rare tail path:
  when both candidates fail, scan remaining leaves in reverse (skipping
  the last two already tried); the normal O(1) fast path is unchanged.
  Regression guard TestExtractJsonObjectLeafRegression (4 cases).
- `src/graph/workflow.py::_should_debug` (P1 branch masking): the
  `_recent_repairs_invalid` early return sat *before* the iteration-cap
  check — on the final iteration (iteration >= max) with the last 2
  repairs both patch_applied=False (the classic "patch keeps failing"
  state), the early return went straight to done and permanently masked
  both the "diagnosis keyword → one regenerate chance" and the test_defect
  cap-convergence branch, with the termination reason mislabeled
  skip_debugger_repair_invalid. The early return is now gated on
  `iteration < max` (early-iteration "skip token waste on repeated
  repair failure" semantics unchanged); the final iteration is decided by
  the cap branch. Regression guard
  TestWorkflowRepairInvalidBranchOrder (3 cases).
- `src/tools/patch_applier.py::apply_patch_to_code` (P1 silent
  corruption): when a full-file-mode patch failed the subset check
  (has an import/docstring prefix but drops an original function), the
  code silently fell back to the single-function path and stitched the
  *entire* patch into the first function's line-range slice — whenever the
  patch prefix overlapped the original's, the result contained duplicate
  imports / duplicate defs that passed `ast.parse`, passed the
  safe_apply_patch syntax guard, and even *passed* multi_candidate check 4
  (function count did not decrease, it increased via duplication), so the
  corrupted code was written to disk. Now a subset-check failure rejects
  conservatively (returns original + False, aligned with the defense-net
  "function count must not decrease" caliber); tests/test_multi_candidate.py
  legacy test locking the old silent-fallback semantics is rewritten as
  test_full_file_patch_missing_function_rejected. Regression guard
  TestPatchApplierFullFileMissingFunction (3 cases).
- `src/agents/executor_repo.py::setup` (P1 cache-marker asymmetry):
  with use_venv=True + venv_reuse_by_repo=True, the venv-create-failure
  fallback to global `pip install` wrote `.pip_installed`, but the setup()
  entry cache check reads `.venv_pip_installed` (L148) — the marker never
  hit, so every setup() re-ran git clone + pip install (SWE-bench batches
  of 10-20 commits of the same repo cloned 10-20 times). The fallback
  path now writes the marker matching use_venv. opt-in use_venv path only.
  Regression guard TestVenvCacheMarkerConsistency.
- `src/agents/executor_repo.py::_run` (P1 timeout leak): `_run` called
  `subprocess.run(timeout=...)` directly; when a single test node exceeded
  the timeout, TimeoutExpired escaped verify()'s try/finally and crashed
  the whole verification task instead of recording that node as failed
  (SWE-bench single-node pytest runs hitting the 30s default is common).
  Now TimeoutExpired is converged to a returncode=124 sentinel (GNU
  timeout caliber); `_run_test_nodes` records rc=124 as "node execution
  timed out" into failed_cases and continues to the next node. opt-in
  REPO_LEVEL_EXECUTION path only. Regression guard
  TestExecutorRepoTimeoutConvergence.
- `src/agents/debugger.py::debug` (P1 line-number offset): the 3.3
  position-aware repair passed the *truncated* target_code into
  `_locate_repair_focus` while context.line is the *original* traceback
  line — once code exceeds CODE_MAX_CHARS (3000) and head-tail
  truncation fires, the line offsets or the target function is dropped,
  degrading location to full-file repair. Now the original is preserved
  before truncation and location uses it (the prompt still uses the
  truncated version for token savings, unchanged). opt-in
  POSITION_AWARE_REPAIR_ENABLE path only. Regression guard
  TestDebuggerPositionAwareOriginalCode.
- `src/tools/dependency.py::_record_venv_cache_event` (P1 TOCTOU race):
  the 5s persist-throttle's `_venv_cache_last_persist_at` read/write was
  outside the persist lock — under `--parallel`, N threads crossing the
  out-of-lock check in the same window let the last-entering thread see the
  just-written timestamp and return, so only the first event in the
  window was persisted (final stat is still correct via atexit fallback;
  persist timeliness deviated from the documented caliber). The in-lock
  double-check now reads/writes the timestamp inside
  `_venv_cache_persist_lock`. Single-thread / non-parallel unchanged.
  Regression guard TestDependencyCachePersistToctou.

#### P2 changes (2, default behavior unchanged)

- `src/graph/workflow.py::_route_after_diagnosis` (P2 unbounded ping-pong):
  the test_defect route regenerated unconditionally without checking
  regeneration_count — with DIAGNOSIS_NODE_ENABLE=true a Review Agent that
  keeps judging test_defect could ping-pong generator↔executor without
  bound and hit LangGraph's recursion_limit. Now gated by the same
  _MAX_REGENERATIONS cap as _should_debug (cap reached → done); both
  conditional-edge maps gained the "done": END mapping. Off-by-default
  double-switch path only. Regression guard TestRouteAfterDiagnosisCap
  (3 cases).
- `tests/test_multi_candidate.py`: one legacy test rewritten (see P1-3,
  now locking conservative rejection).

#### Items confirmed as no-fix-needed (subagent review findings)

- cross_file topological sort (Kahn + lexicographic) / `from X import *`
  missing reverse edge (opt-in conservative caliber) / code_context same-name
  class-method collision (conservative setdefault) / patch_applier AST vs
  regex fallback consistency / type_repair family conservative caliber /
  multi_candidate credit default 0.0 defensive write /
  dependency `_importable_cache` lock-free double-read (idempotent) /
  executor_imports LRU invalidation (single-task sequential path never
  triggers) / llm_client zai double-retry (existing deadline fast-fail) —
  design calibers or opt-in paths; default behavior unchanged, recorded
  only.

### Eighth-batch closing audit (default behavior unchanged)

- `examples/buggy_library.py`: removed a duplicate `import re` (F811) and
  fixed import ordering (I001) accidentally introduced in the working tree;
  `examples/calculator.py`: stripped trailing whitespace on a blank line
  (W293); `experiments/synthetic_difficulty.py`: dropped a placeholder-free
  f-string (F541) and switched per-item `append` to a `list.extend`
  generator (PERF401).
- `experiments/run_benchmark.py::run_single_task`: narrowed the AST-parse
  exception handler (the previous bare `Exception` in the tuple swallows
  interruptible control flow such as KeyboardInterrupt; now catches only
  `SyntaxError/ValueError`, caliber unchanged).
- `src/tools/type_repair.py::type_repair_layer`: new optional
  `enforce_contract_ref` parameter (the contract-check reference side;
  default `None` = original-code reference, matching
  `check_naming_contract`'s primary "symbol deletion" semantics) — callers
  previously had no way to validate a full-file LLM repair against a
  "patch-baseline symbol set" caliber; explicit reference is now optional,
  default unchanged.
- `src/agents/debugger.py`: documented the contract-reference caliber at the
  `type_repair_layer` call site (default original-code reference; an LLM
  repair that drops original top-level symbols = contract break = repair
  rejected, same direction as the main `_patch_applier_node` path).
- `src/graph/nodes.py::_debugger_node`: fixed the broken
  `type_repair_findings` state-key chain — `debug()` returned the key but
  the node never wrote it into state (declared in state.py, consumers
  always saw None); now written via
  `result.get("type_repair_findings", [])` (empty-list default, no
  KeyError for historical callers without the key).
- `src/agents/llm_client.py::_is_zai_compatible`: zai-domain detection
  upgraded from a frozenset + `any` substring scan to a module-level
  precompiled alternation regex `_ZAI_DOMAIN_RE` (one O(n) scan, zero
  per-call allocation); hit caliber is sample-for-sample equivalent to the
  legacy substring scan (locked by
  `test_zai_domain_regex_equivalence`).
- `src/graph/workflow.py::_route_after_diagnosis` / `_diagnosis_node`:
  routing decisions and state writes covered by regression guards
  (8 tests: test_defect → regenerate / others → debug / missing → debug;
  `_debugger_node` writes `type_repair_findings` with-value and
  default-empty calibers).

### Seventh-batch hot-path deep scan (default behavior unchanged)

### Seventh-batch hot-path deep scan (default behavior unchanged)

- `src/tools/code_analyzer.py::preserve_patch_ingredients` (P0 hot path):
  added optional `_ast` parameter — `extract_focused_code_detail` in
  code_context already ran `ast.parse` on the same source, but the
  contract-block path (lazy-imported `preserve_patch_ingredients`) re-parsed
  it (a 200 ms-class duplicate parse on large files, accumulating under
  `--parallel` multi-task). Callers now pass the existing `tree` for reuse;
  standalone callers (no `_ast`) keep unchanged behavior. Return value gains
  an `ast_tree` key (the tree on successful parse, `None` on failure) so
  callers can reuse it for secondary analysis; all existing fields keep
  their semantics.
- `experiments/run_benchmark.py::run_single_task` (P0 hot path): the
  complexity-aware routing path previously ran `count_imports` (one internal
  parse) plus a separate cyclomatic-complexity parse (one more), i.e. two
  `ast.parse` calls per task. Now parses once; cyclomatic analysis uses that
  tree directly, and `count_imports` reuses it via the new `_tree` parameter.
  On parse failure (`_tree=None`), `count_imports` keeps its historical
  "return 0 on parse failure" semantics. Calls to
  `compute_complexity_score` / `complexity_class_to_routing_hints` are
  unchanged.
- `src/datasets/dataset_loader.py` (benchmark hot loop): new O(1)
  `_task_index` (task_id → BenchmarkTask) lookup index; `get_task_by_id`
  drops from O(n) linear scan to O(1) (lazily rebuilt by
  `_rebuild_task_index_if_stale` after `add_task`; the steady-state path
  short-circuits in O(1)). `task_ids` / `size` / `filter_by_repo` and other
  properties switched from `self.tasks` (an O(n) list copy +
  `_ensure_loaded` per call) to direct `self._tasks` access, removing O(n)
  redundancy in the benchmark hot loop. `quality_report` /
  `tasks_missing_source` now call `_ensure_loaded` first so they iterate
  correctly even when the dataset has not been explicitly loaded yet
  (previously they read `self._tasks`, which was empty pre-load).
- `src/agents/error_classifier.py` (Debugger hot path):
  `classify_with_context` previously had `classify()` and
  `extract_error_context()` each build their own combined text (two O(n)
  joins over the same test_output + failed_cases). Now a single `combined`
  is built once and shared with `_classify_combined` +
  `_extract_error_context_from_combined`; `classify()` gains an internal
  `_combined` parameter (external callers need not pass it);
  `extract_error_context` becomes a thin "build combined + delegate to
  `_extract_error_context_from_combined`" wrapper. Priority order, regex
  semantics, and `ErrorContext` fields are all unchanged.
- `src/graph/workflow.py::_should_debug` (routing hot path): diagnosis
  keyword detection moved from a per-call rebuilt list literal plus nine
  `any(kw in text)` substring scans (O(9n)) to a module-level
  `_TEST_GEN_DIAGNOSIS_KEYWORDS` constant plus a precompiled alternation
  regex `_DIAGNOSIS_KEYWORD_RE` (one O(n) scan, lazily compiled).
  `_diagnosis_hits_test_gen_keywords` is semantically equivalent to the
  historical `any(kw in diagnosis for kw in _TEST_GEN_DIAGNOSIS_KEYWORDS)`
  (the guard test `test_regex_equivalent_to_any_substring` verifies sample
  by sample).
- `src/agents/executor_runtime.py::run_pytest_with_retry`: the
  `TimeoutExpired` branch re-created the `_to_str` closure on every
  exception; promoted to a module-level function (zero needless allocation
  on the hot path) with unchanged semantics (the str / bytes / None
  branches).
- `src/api/api_manager.py::call` (half-open probe window elimination):
  `call()` previously called `_enter_half_open_probe(node)` both before the
  loop and inside `_try_call_node`, so the pre-computed
  `is_half_open_probe` flag passed to the 429 / error handlers could be
  stale (probe state drifted between the outer pre-check and the inner
  `_try_call_node` pre-check). Now `_handle_rate_limit` /
  `_handle_api_error` / `_handle_generic_error` accept
  `is_half_open_probe: bool | None = None` and self-determine via
  `self._enter_half_open_probe(node)` when None, eliminating the
  double-probe window; `call()` no longer pre-computes. All 169 API tests
  pass.
- `src/utils/helpers.py::extract_json_object`: the leaf-fallback path went
  from `reversed(list(finditer))` (O(n) memory materialization of every
  match) to an O(1) last-two-match rolling tracker
  (`last_match` / `prev_match`), semantically equivalent (the
  balanced-brace primary path is unchanged; the leaf fallback now tries the
  last two candidates).
- `src/graph/nodes.py` (write-safety hot path): precompute the
  `_ALLOWED_WRITE_ROOT_PREFIXES` pairs
  `(root, root.rstrip(os.sep)+os.sep)` at module load; the hot path in
  `_is_within_allowed_roots` no longer recomputes the prefix per call.
  The default `roots=None` uses the precomputed pairs; the historical
  explicit-`_ALLOWED_WRITE_ROOTS` caller path keeps the original semantics.
  Sibling-directory prefix-collision protection is unchanged.
- `src/agents/llm_client.py::_is_zai_compatible`: the zai-domain list was
  rebuilt on every call; promoted to a module-level `_ZAI_DOMAINS`
  frozenset, eliminating the two per-call allocations on the
  `--parallel` LLM routing decision path.

### Performance-regression guard tests (tests/test_performance_guards.py, 17 new)

- Reuse paths (passing `_tree` / `_ast`) agree field-by-field with
  standalone paths (no argument passed);
- An injected `ast.parse` counting stub confirms the reuse path triggers
  zero additional parses;
- The precompiled alternation regex is verified sample-by-sample
  equivalent to the historical `any(kw in text)` semantics;
- A ~400 KB focused-extraction completes within seconds (a magnitude guard
  against order-of-magnitude regressions, not microsecond absolutes);
- dataset_loader O(1) index and direct-`_tasks` property paths: behavior +
  magnitude guards.

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

## [Unreleased] - 0.8 Full-audit & fix round (credential-scrub logic dedup + half-open probe failure-path consumption + LLM cache makedirs short-circuit + temperature-key closed-loop + execution-trace duplicate computation elimination + whitelist root pre-normalization + `__main__` self-diagnosis bug fix + 4 regression test cases)

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

## [0.9.11] - Credential security, observability & performance optimization (2025-09-25)

> This round is a pure code-quality pass: mypy real-semantic errors
> zeroed from 26 to 0, and `experiments/analyze_results.py` (2192 lines)
> split into 4 theme submodules. **No runtime behavior or experiment
> semantics changed.**
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
>   - `experiments/analysis_parts/__init__.py`: sub-package docstring +
>     theme index.
> - `experiments/analyze_results.py` (2192 → 959 lines) keeps its public
>   entry points `load_latest_benchmark` / `build_analysis` /
>   `render_markdown` / `main`, and re-exports all 24 private functions
>   from the 3 submodules (annotated `# noqa: E402,F401`; historical
>   import paths `experiments.analyze_results._xxx` unchanged).
>   External tests (`tests/test_smell_detection_v2.py` /
>   `tests/test_experiments_scripts.py`) and same-package scripts
>   (`contamination_check` / `mutation_testing` / `run_benchmark`) need
>   no import changes.
> - Split principle: pure function moves with zero change to signature /
>   return value / docstring / default args; intra-group shared helpers
>   (e.g. `_assertion_strength_proxy` consumed by `_quality_proxy_metrics` /
>   `_assertion_counts_from_row`) stay in one file, no cross-file import,
>   avoiding new circular dependencies.
>
> **Verification**: ruff check / ruff format all green (189 + 4 files) /
> full suite 1659 passed / 0 failed / mypy `src/ --ignore-missing-imports`
> 0 errors (58 source files) / src coverage 94% (statement count 4911,
> down 305 from 0.7's baseline of 5216 — `analyze_results.py` left the
> src/ tree, not a coverage regression) / smoke check:
> `experiments.analyze_results.build_analysis` does not crash on empty
> data, all 28 re-exported symbols present.
>
> Note: this round's mypy zeroing scope is `src/` (no mypy gate in CI,
> local non-gated promise). `experiments/` / `config.py` / `main.py` and
> other scripts have no historical mypy gate, out of scope;
> `--ignore-missing-imports` suppresses import-untyped noise from
> stub-less third-party libs (scipy / datasets / dbutils / chromadb).
>
> **Comprehensive review fixes (2026-09-24 security + correctness +
> maintainability)**:
> Based on a repo-wide review, 5 issues fixed (tests 1672 → all green,
> mypy 0 errors):
> - **Credential scrubbing factored into a function
>   (`src/utils/credential_scrub.py` new)**:
>   local / venv / Docker execution paths all funnel through
>   `scrub_os_environ()` to strip LLM credentials. The old `executor.py`
>   stripped only 7 fixed variables (couldn't cover the
>   `LLM_1_API_KEY` family); venv/Docker paths inherited the host
>   `os.environ` verbatim — LLM-generated test code could read host API
>   credentials. Now dynamic patterns `LLM_\d+_API_KEY` /
>   `LLM_\d+_BASE_URL` (aligned with the config-scan 1-32 scope) +
>   generic SDK-credential scrubbing, single implementation shared by all
>   three paths to avoid list drift.
> - **CLI `finally` block fragile code (`src/cli/app.py`)**:
>   `end_task_trace` close-out relied on `"final_state" in locals()`
>   (the name unbound when invoke raised) — obscure semantics, easy to
>   break in refactors. Now `final_state: dict | None = None` init +
>   `is not None` check + `assert` narrowing (mypy union error gone).
> - **Side-effect-free node (`src/graph/nodes.py`)**:
>   `_select_multi_candidate_patch` used to write `state["multi_candidate_stats"]`
>   in place (shared TypedDict, crosstalk under `--parallel` threads);
>   now returns a 3-tuple `(code, applied, stats_update)`, merged into
>   `_patch_applier_node`'s own update dict.
> - **Patch function location regex → AST (`src/tools/patch_applier.py`)**:
>   the old `_find_function_range` treated `^#` comments / `^@`
>   decorators / class methods as "boundaries", truncating decorated or
>   comment-containing function bodies early and producing incomplete
>   replacements. New `_find_function_range_ast` reads
>   `FunctionDef.lineno/end_lineno` for precise location; falls back to
>   the regex when the source can't be parsed (conservative, behavior
>   unchanged).
> - **Low-risk fixes**: deleted `.env.local.bak` (backup containing real
>   secrets); `llm_configs.json` 3 deepseek entries'
>   `provider_description` changed from "通义千问" to "DeepSeek
>   hosted"; `requirements.txt` explicitly declares `openai==2.54.0`
>   (`api_manager.py` does a top-level `import openai`,
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

## [0.3] - 2026-09-19 Evaluation-metric deepening + mutation generator fix + redaction audit round

### Features
- **Mutation generator fix** (`experiments/mutation_testing.py`):
  `_remove_not_op` was originally dead code (only `break`, never actually
  replacing the AST node), which made `boolean_negation` mutants
  byte-identical to the original code; the downstream sandbox "all pass"
  verdict was misjudged as "killed", and `mutation_score` inflated.
  New `_RemoveNotTransformer` (AST NodeTransformer) locates Not nodes by
  line number and rewrites their parent slot (`If` / `While` / `Return` /
  `Assign` / `BoolOp` / `Compare` / `Expr`, etc.); only a successful
  replacement counts the mutant; unmatched cases are filtered out to
  prevent the dead-code regression. Removed the dead identifiers
  (`_find_mutable_numeric_constants` / `_BOUNDARY_REPLACEMENTS` /
  `_OPERATORS_TO_FLIP` — none of them referenced by `generate()`).
- **Mutation scoring wired into the run_benchmark pipeline**
  (`experiments/run_benchmark.py` + `config.py`): new
  `ENABLE_MUTATION_SCORING` (default False, preserves historical
  experiment semantics and time budget) + `MUTATION_MAX_MUTANTS`
  (default 10). When enabled, `run_benchmark` calls
  `experiments.mutation_testing.compute_mutation_score` per task after
  building the baseline results and writes `mutation_score` back into
  `details[]`, which `_mutation_score_metrics` can aggregate.
  `_build_task_result`'s success branch gained a `generated_test`
  field (previously only persisted via `--save-state` into raw/;
  the standard result JSON did not carry it; mutation scoring needs
  both the generated test and the source under test, so it must be
  written into details[]). CLI gained `--enable-mutation` /
  `--no-mutation` arguments. `reproduce.sh` documents the
  `ENABLE_MUTATION_SCORING` pass-through (off by default; only an
  explicit enable takes effect).
- **4.2 Log-redaction full audit** (`docs/log_redaction_audit.md` +
  R-1 fix): four-layer check — ① api_manager failover logs already
  redact base_url (`get_status` + `_redact(config.base_url)` +
  failover logs only the model_name); ② trace.py JSONL persistence
  redacted uniformly via `mask_sensitive_info`; ③ the Docker
  container's `execute_docker` injects no environment variables and
  `.dockerignore` excludes `.env.*` (secrets never enter the image);
  ④ the single `exc_info=True` print site (`exceptions.py:321`) is
  covered by the CLI entry's `SensitiveFormatter` (message-body +
  full-line including stack trace, double insurance).
  **Found R-1**: `api_manager._redact` and `llm_client._redact_log_text`
  degrade to "return as-is" when `mask_sensitive_info` is unavailable,
  leaking sensitive text into logs. Fix: `logging_utils` gained
  `fallback_mask_sensitive_info` (pure-regex fallback on the first 3
  "long random string" patterns of `_SENSITIVE_PATTERNS`); both
  `_redact` degradation paths delegate to it, so even when the
  redaction module is completely unavailable, 32+ hex / 40+ base64 /
  sk- prefixed credentials are still intercepted.
- **3.2 Multi-candidate patch A/B comparison experiment**: synthetic
  dataset, 50 tasks × 3 baselines, two groups (multi-candidate ON vs
  OFF, seed=42) fully run; diff data in
  `experiments/results/multi_candidate_ab_summary.md`.

### Tests
- `tests/test_smell_detection_v2.py` gained 4 cases: boolean_negation
  real-replacement regression (6 slot scenarios) / nested-function not
  / no-not generates nothing / end-to-end `compute_mutation_score`
  (strong-test kill count ≥ weak-test kill count).
- `tests/test_run_benchmark.py` gained 4 cases:
  `_compute_mutation_scores_for_baseline` missing / present / unknown
  task / empty instance_code branches + `_build_task_result`
  success/failure key-set consistency (including the new
  `generated_test` field).
- `tests/test_logging_utils.py` gained 7 cases:
  `fallback_mask_sensitive_info` behavior for sk- / hex / base64 / JWT /
  normal text / empty value.

### Engineering baseline
- Full test suite **1474 passed / 0 failed** (previous round 1460 +
  net 14 this round); `ruff check src/ tests/ experiments/` all green.
- Redaction audit full report archived at
  `docs/log_redaction_audit.md` (four-layer check + R-1 fix).
- Multi-candidate A/B comparison data archived at
  `experiments/results/multi_candidate_ab_summary.md` (includes a
  caveat that the plain_llm baseline's LLM cache hit invalidates the
  token data).

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
