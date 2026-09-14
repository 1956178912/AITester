> **Language**: [中文版](optimization_plan.md) | English (this document)

> **Archive note (2026-09-15)**: This document was originally `OPTIMIZATION_PLAN.md` at the repository root; it is now archived under `docs/history/` (historical round work records, not a currently maintained document). See the CHANGELOG and the global decision log in the user workspace for current-round optimization decisions.

# AITester Project Optimization Plan

> Basis: Phase 0 baseline (1020 tests passed / all ruff green / 91% coverage / clean working tree) + two audit subagents in Phase 1 + independent verification.

## Improvement Checklist Status Audit (2026-09-14, 5 categories, 22 items)

> The user provided a 5-category improvement checklist (1.1~1.3 / 2.1~2.3 / 3.1~3.5 / 4.1~4.4 / 5.1~5.3).
> This round cross-referenced each item against the repository's actual code state; conclusion: **most items were already implemented in earlier batches**;
> the real gaps concentrate in 4 places, plus 2 are research/experimental items (not pure code changes).
>
> **Implementation completion status (2026-09-14 improvement checklist batch + circuit breaker half-open probe batch)**:
> - G-01 Test smell detection ✅ (commit ffb77cf)
> - G-02 Repair convergence curve ✅ (commit ffb77cf, same batch as G-01)
> - G-03 Dependency cache monitoring ✅ (commit 6b0e64d)
> - G-04 Failure root-cause classification + case knowledge base ✅ (commit 247fc91)
> - R-05 Assertion augmentation strategy ✅ (commit ed4c237, off by default)
> - 3.5 Cross-file repair ✅ (commit 670f368, off by default, design doc at docs/design/cross_file_repair.md)
> - 4.2 Circuit breaker half-open probe ✅ (commit b69d811, on by default: after the cooldown expires, the node first enters the half-open window and carries only one probe request;
>   on success it closes / on failure it reopens with a half cooldown of min(cooldown/2, cap=30s); `enable_half_open_probe=False`
>   falls back to the 4.1 behavior for comparison experiments; TestHalfOpenProbe 12 cases)
> - Full-suite baseline advanced to **1237 passed / 0 failed** (net +74 from 1163; the 4.2 batch net +12 from 1225);
>   ruff check / format all green

### 1. Already Implemented (No Need to Re-implement in This Round)

| Checklist Item | Current Evidence | Notes |
|----------|----------|------|
| 1.1 Multi-dimensional quality proxies (coverage/runtime/assertion strength) | `analyze_results.py:_quality_proxy_metrics` (coverage_proxy / runtime_proxy / assertion_proxy + failure_top_categories) | Marked as proxies, no exact AST cyclomatic complexity values; `code_analyzer.compute_cyclomatic_complexity` has the capability but is not yet wired in |
| 1.3 First-attempt success rate / iteration distribution | `analyze_results.py:_repair_convergence_metrics` (first_attempt_success_rate + success/failed_iteration_stats) | Iteration distribution table already exists |
| 2.1 SWE-bench 20-task archive + source export | `experiments/results/swebench_20_summary.json` (7 completed / 10 timed out, API rate-limiting recorded on file); `scripts/export_swe_bench_source.py` | 20-task results are archived but pass_rate is 0/7 (due to rate limiting) |
| 2.3 RAG automatic summary (RAG vs disabled comparison + which error type benefits most) | `analyze_results.py:_rag_by_kind_from_details` + `_rag_hit_by_failure_category` | RAG enabled/disabled token comparison requires running the experiment once each; the script has no built-in support |
| 3.3 Multi-candidate patches off by default + optionally enabled | `ENABLE_MULTI_CANDIDATE_PATCH` defaults to false; `src/tools/multi_candidate.py` has a complete implementation (static filtering + execution verification) | Comparison experiment not yet run |
| 4.1 Structured trace layer explicitly enabled | `src/observability/trace.py` + `AITESTER_TRACE_DIR` (no-op by default) | Trace layer implemented; not explicitly enabled in large-scale experiments |
| 4.2 Circuit breaker cooldown + half-open probe | `api_manager.py:circuit_open_until` (default 60s, `APIManagerConfig.circuit_cooldown_seconds`) + half-open probe (`in_circuit_half_open` / `_probe_circuit_half_open`, `enable_half_open_probe` defaults to True, penalty = min(cooldown/2, 30s cap)) | ✅ 4.2 batch implemented: after the cooldown expires, enter the half-open window; on probe success close / on failure reopen the half cooldown; get_status emits the three-valued circuit_state |
| 4.3 Complete log redaction audit | `docs/redaction_audit.md` (three-layer defense + per-exit walkthrough + LLM file cache recorded as a known risk) | Audit done |
| 4.4 Dependency caching | `dependency.py:venv_cache_dir` (md5 cache per dependency combination) + `create_venv` reuse | Cache hit-rate statistics / cleanup command / multi-version not implemented |
| 5.1 CLI module coverage improvement | `tests/test_cli_app.py` 27 cases (batch ② 1.4c added 8: timeout / invalid dataset / single-task non-blocking / check-dataset boundaries / glob concurrency semantics) | cli/app.py coverage still 64% (the lowest) |
| 5.2 Error classification refinement | `error_classifier.py` 12 categories (batch ② 1.1s: PATCH_VALIDATION_FAILED + RAG_RETRIEVAL_EMPTY) | Goes through the `refine_failure_category()` pure function, not text regex |
| 5.3 Failure analysis depth enhancement | `analyze_failures.py` (clustering by baseline/error type + representative cases); `compare_failures.py` (locates "AITester failed but Plain LLM succeeded" flip tasks + stage-level comparison + auto verdict hints) | Failure root-cause classification (LLM capability boundary / dependency / framework) and failure case knowledge base not implemented |

### 2. Real Gaps (4 places, need implementation)

| ID | Checklist Item | Gap | Implementation Points | Impact Scope | Test Method |
|------|----------|------|----------|----------|----------|
| G-01 | 1.2 | **Test smell detection not integrated**: `grep -rni "smell" src/ experiments/` zero hits; no detection of LLM-generated smells such as Assertion Roulette / Magic Number Test | Add `test_smell_detection(details)` pure function to `analyze_results.py` (AST scan of generated_test, detecting: test without assertions / tautological assertions / unnamed magic number constants / assertion weakening: assertion count decreased from round 0 → final round) + Markdown rendering | Analysis layer only, zero runtime path changes | `tests/test_experiments_scripts.py` +2 cases |
| G-02 | 1.3 | **Repair convergence curve missing**: `analyze_results.py` has no "pass rate changes as iteration count grows" visualization | Add `repair_convergence_curve(details)` pure function (cumulative pass rate + cumulative repair cost per iteration round 0/1/2/3), Markdown output table | Analysis layer only | +1 case |
| G-03 | 4.4 | **Dependency cache monitoring and cleanup**: `venv_cache_dir` has no hit-rate statistics / cleanup command / multi-version | Add `VenvCacheStats` to `dependency.py` (hit/miss/created counters) + `clear_venv_cache(max_age_days / max_size_mb)` + `list_venv_cache()`; CLI or scripts command entry | New additions only, does not change `create_venv` reuse behavior | `tests/test_dependency.py` +3 cases |
| G-04 | 5.3 | **Failure root-cause classification + case knowledge base**: `analyze_failures.py` has no root-cause categorization (LLM capability / dependency / framework) and no structured knowledge base | Add `root_cause_classification(details)` (error_category mapping + diagnosis text matching) + `experiments/failure_knowledge_base.json` (structured storage: task_id / root_cause / error_category / reproducible steps / suggested fix) + `analyze_failures.py` renders the knowledge base section | Analysis layer only, zero runtime path changes | +2 cases |

### 3. Research / Experimental Items (not pure code; need independent projects or manual experiment runs)

| ID | Checklist Item | Nature | Description |
|------|----------|------|------|
| R-01 | 2.1 | Experimental | SWE-bench Verified / Pro subsets need real API quota + data download; the 20-task archive backfill requires manually running `run_benchmark.py --dataset swe_bench` |
| R-02 | 2.2 | Experimental + architectural | Synthetic vs real failure-mode cross analysis (requires running each experiment once + comparison); task difficulty stratification (requires dataset_loader to stratify by complexity/dependency count); cross-language generalization (Defects4J is Python-subset only, requires Java ecosystem exploration) |
| R-03 | 3.1 | Research | Adversarial reasoning mechanism (AdverIntent-Agent): multi-agent architecture change, needs a design doc |
| R-04 | 3.2 | Research | Execution-feedback-driven reinforcement learning (BoostAPR): reward signal design + policy fine-tuning, not a pure code change |
| R-05 | 3.4 | Implementable | Assertion augmentation strategy: add an "leverage existing assertions" strategy to `generator.py` (AST-extract existing assert in the code under test + prompt injection) |
| R-06 | 3.5 | Architectural | Cross-file repair: multi-file dependency analysis + patch stitching, needs an independent design doc |

### 4. Implementation Batch Proposal

| Batch | Goal | Files | Change Method | Test Method | Commit Message |
|------|------|------|---------|---------|-------------|
| B-1 | G-01 Test smell detection | `experiments/analyze_results.py` + `tests/test_experiments_scripts.py` | Pure function + Markdown rendering + 2 cases | pytest test_experiments_scripts.py | `feat(experiments): 1.2 test smell detection integration (analyze_results adds test_smell_detection)` |
| B-2 | G-02 Repair convergence curve | `experiments/analyze_results.py` + `tests/test_experiments_scripts.py` | Pure function + Markdown rendering + 1 case | pytest test_experiments_scripts.py | `feat(experiments): 1.3 repair convergence curve (cumulative pass rate per iteration round + repair cost)` |
| B-3 | G-03 Dependency cache monitoring | `src/tools/dependency.py` + `tests/test_dependency.py` | VenvCacheStats + clear/list commands + 3 cases | pytest test_dependency.py | `feat(tools): 4.4 dependency cache monitoring (hit-rate statistics + cleanup command + multi-version)` |
| B-4 | G-04 Failure root-cause classification + knowledge base | `experiments/analyze_failures.py` + `experiments/failure_knowledge_base.json` (new) + `tests/` | root_cause_classification + JSON knowledge base + Markdown section + 2 cases | pytest affected tests | `feat(experiments): 5.3 failure root-cause classification + case knowledge base (LLM/dependency/framework attribution + structured storage)` |
| B-5 (optional) | R-05 Assertion augmentation | `src/agents/generator.py` + `src/prompts/templates.py` + `tests/test_generator.py` | AST-extract existing assert + prompt injection + strategy switch (off by default) | pytest test_generator.py | `feat(agents): 3.4 assertion augmentation strategy (leverage existing assert to improve generated test quality, off by default)` |
| B-6 | Documentation sync | `CHANGELOG.md` + `optimization_plan.md` + `optimization_report.md` | Append this batch's record | Manual check | `docs(optimize): 2026-09-14 improvement checklist status audit + G-01~G-04 implementation record` |

### User Confirmation Required

1. **Implementation scope**: this round implements G-01~G-04 (4 pure code + tests) + R-05 (assertion augmentation, off by default) + 3.5 (cross-file repair, off by default, with design doc); all completed.
2. **Batch order**: B-1→B-2→B-3→B-4→B-5→B-6 serial (each batch an independent commit, individually revertable).
3. **R-01~R-04 / R-06** are recorded as research/experimental items and excluded from this round's code changes (3.5 was implemented as B-6, off by default to keep the historical baseline).
4. **Push**: this batch has 6 commits (including ruff normalization), `git push origin main` direct push (following the historical-rounds main-direct-push mode).

## Improvement Checklist Implementation Change Log (2026-09-14 improvement checklist batch)

> New baseline: 1225 passed / 0 failed / ruff check + ruff format all green / clean working tree / in sync with origin/main (on top of `ffb77cf`).
> User checklist: G-01~G-04 + R-05 + 3.5 all landed; the research-capability items off by default (3.4/3.5) do not change the historical experiment baseline.
>
> ### Commit sequence of this batch
>
> | # | commit | Content |
> |------|--------|------|
> | 1 | ffb77cf | 1.2 test smell detection + 1.3 repair convergence curve (analyze_results adds two regression sections) |
> | 2 | 6b0e64d | 4.4 dependency cache monitoring (venv hit-rate statistics + cleanup command + multi-version list) |
> | 3 | 247fc91 | 5.3 failure root-cause classification + case knowledge base (LLM/dependency/framework attribution + structured storage) |
> | 4 | ed4c237 | 3.4 assertion augmentation strategy (AST-extract existing assert into prompt, off by default) |
> | 5 | 670f368 | 3.5 cross-file repair (coordinator-proposer architecture, off by default) |
> | 6 | (this batch) | ruff normalization + documentation sync (README / CHANGELOG / .env.example / OPTIMIZATION_PLAN / decision log) |
>
> ### Design trade-offs
>
> - **3.4/3.5 off by default**: env vars `ASSERTION_AUGMENT_ENABLE` / `CROSS_FILE_ENABLE` default to false, keeping the historical experiment baseline unchanged; enabling is an explicit act.
> - **3.5 single-entry perspective**: the current `analyze_cross_file_deps` only analyzes entry_module's own import relationships (does not recursively expand the caller's imports, avoiding dependency graph explosion); Phase 2 extends to multi-entry analysis.
> - **Cross-file patch downgrade**: when `apply_multi_file_patch` fails, `cross_file_fallback_single_file` applies the patch only to entry_module; other modules stay as-is (conservative baseline, no degradation introduced).
> - **4.4 deadlock fix**: `threading.Lock` is not reentrant; when `_record_venv_cache_event` called `_persist_cache_stats`, the latter's second lock acquisition would hang the process — changed to a single lock boundary (`_persist` assumes the caller already holds the lock).
> - **5.3 conservative heuristic**: root-cause classification is based on error_category + diagnosis keyword matching (no LLM reasoning), avoiding introducing LLM call cost into the analysis layer; unmatched rules fall back to `llm_capability` (the most general fallback).

## Full-Project Documentation Sync Round (2026-09-14, batch F)

> Baseline: 1158 passed / ruff check + ruff format all green / 91% coverage (TOTAL 3911/354 miss) / in sync with origin/main (`797a406`).
>
> **Update (2026-09-14 batch ③)**: the first batch of multi-dimensional evaluation metrics (1.1/1.2 analysis-layer enhancements) has advanced the current baseline to 1163 passed; this file's 1158-related items are kept as historical batch records.
> User directive: update all documentation to the latest and upload to GitHub. Pure documentation + script docstring changes, zero functional changes.
>
> ### Optimization Points of This Round
>
> | ID | Category | Location | Problem | Implementation | Verification |
> |----|------|------|------|------|------|
> | F-01 | Docs | README.md project structure | Structure tree diverges from current code in 4 places: missing `src/observability/`, `src/graph/token_usage.py`, `src/tools/` missing code_context.py/dependency.py/multi_candidate.py, experiments/ missing 4 scripts | Filled in 8 lines per the actual `ls` listing + added 4 experiment script lines | Cross-checked line by line against `ls src/ experiments/` |
> | F-02 | Security/docs | docs/redaction_audit.md item C | LLM file cache path recorded as `~/.cache/aitester/llm_cache/` ("in HOME, naturally outside the repo path"), but the actual code `_LLM_CACHE_DIR_DEFAULT` is `src/cache/` (inside the repo, gitignored) | Item C's path and trust-level discussion corrected to `src/cache/*.json` + AITESTER_LLM_CACHE_DIR overridable + runtime-artifact note | Cross-checked against src/agents/base_agent.py:371-383 |
> | F-03 | Docs | docs/performance_guide.md:197 | `rm -rf .chroma_cache/` points to a non-existent directory (chromadb 1.x persists to rag_data/, .chroma_cache has no consumer) | Changed to `rm -rf rag_data/` + RAG_PERSIST_PATH override note | Cross-checked against src/rag/retriever.py |
> | F-04 | Wording | README.md + experiments/analyze_failures.py | Residual "for the paper discussion section" phrasing (09-13 privacy cleanup round missed 2 places) | 1 place in the README structure tree + script docstring/default output path `docs/paper/` → `experiments/results/` | `grep -rn "for the paper" .` zero residual |
> | F-05 | Docs | README.md:5.3 cost-aware routing | After 3.2 threshold configurability landed, still wrote "cost_weight>=2.0" (default-value baseline); did not mention that APIManagerConfig.cost_alert_threshold is configurable | Section title + description now note 3.2 configurability (default 2.0 + tuning direction + 0.0=no-information fallback to the 1.0 baseline) | Cross-checked against the 3.2 comment in api_manager.py |
> | F-06 | Docs | README.md core methods | Missing the 2.1 SWE-bench source-export automation subsection (batch ② already landed the script + tasks_missing_source; README had no entry point) | Added section 5.7 (script usage + check-dataset linkage) | Cross-checked against scripts/export_swe_bench_source.py |
> | F-07 | Docs | docs/api_reference.md version history | Version table stops at 0.9.13; batch ② (12 categories/configurable threshold/source export/RAG summary/redaction audit) unrecorded | Added an Unreleased (2026-09-14 batch ②) row at the top of version history (the 0.9.13 row kept as a historical record) | Cross-checked against the CHANGELOG batch ② entry |
> | F-08 | Template | .env.example section 3.4 | 3.2 threshold configurability not in the template comment; LLM_N_COST_WEIGHT baseline inconsistent (config.py actually 0.1~1000, unconfigured default 0.0 not 1.0) | Comment adds cost_alert_threshold configurability note + COST_WEIGHT numeric range/default baseline aligned to code | Cross-checked against config.py:150 |
> | F-09 | Docs | Doc timestamps | performance_guide.md "Last updated 2026-08-16", usage_examples.md "2026-09-11" stale | Both files' timestamps synced to 2026-09-14 | Manual check |
> | F-10 | Link | docs/usage_examples.md:357 | Referenced lowercase `contributing.md` (the actual file is CONTRIBUTING.md at the repo root; it does not exist under docs/) | Link changed to `../CONTRIBUTING.md` | Cross-checked against `ls docs/` |
>
> > Search conclusions (dimensions with no optimization points): `.env.example`/`config.local.example` template placeholders contain no real keys; each QUICKSTART step cross-checked against the actual CLI parameters; docs/algorithm_design.md is algorithm narrative (with the "for technical review" baseline), no data drift against the code; failure_analysis.md is a historical snapshot and its 09-14 status note already states "take analyze_results.py output as authoritative", original text kept without rewriting to follow the baseline (reasonable).
>
> ### Implementation Batches
>
> | # | Goal | Files | Change Method | Test Method | Commit Message |
> |------|------|------|---------|---------|-------------|
> | F-1 | F-01~F-10 full-project documentation sync | README.md + docs/{redaction_audit,performance_guide,usage_examples,api_reference}.md + .env.example + experiments/analyze_failures.py | Structure tree fill-in + cache path correction + chroma_cache fix + 2 paper-wording places + 5.3/5.7 + version history row + template baseline + timestamps + link | ruff check/format + full pytest + `grep` drift re-check | `docs: full-project documentation sync to 2026-09-14 batch ② latest state` |
> | F-2 | Plan/report check-in | optimization_plan.md + optimization_report.md | This batch's section + round appendix | Manual check | `docs(optimize): 2026-09-14 full-project documentation sync round plan and change record` |
>
> ### Points Needing User Confirmation
>
> 1. **F-02 cache path correction**: the redaction_audit item C "known acceptable risk" conclusion is unchanged (local trusted domain); only the path and trust-level discussion are aligned with the actual code (`src/cache/` inside the repo + gitignored);
> 2. **F-04 analyze_failures.py default output path**: the `--output` default changed from `docs/paper/failure_analysis.md` (directory no longer exists) to `experiments/results/failure_analysis.md` (no test references this script, zero regression surface);
> 3. **Phase 6 push**: user directive "upload to GitHub", following the historical-rounds main-direct-push (no feature branch, no PR).

## Documentation Wrap-up Round (2026-09-14 batch ② wrap-up, documentation data alignment)

> New baseline: 1158 passed / ruff all green / 91% coverage / lock in sync / clean working tree / in sync with origin/main.
>
> **Batch ③ note (2026-09-14)**: this round advanced 1.1/1.2 analysis-layer enhancements on top of batch ② (`analyze_results.py` adds two regression sections: repair convergence efficiency and multi-dimensional quality proxies); the current full-suite baseline is now **1163 passed**; the 1158 items above are kept as historical batch records.
> This round is the documentation wrap-up for batch ② (7 pure code items): the user confirmed "execute all + push main".
>
> ### Optimization Points of This Round
>
> | ID | Category | Location | Problem | Implementation | Verification |
> |----|------|------|------|------|------|
> | O-01 | Docs | README.md:621-666 test coverage module main table | 9 rows' case counts drifted from the measured `def test_` counts (not synced after 09-14 batch ①/② added 41 cases) | Synced to measured values: test_api_manager 80→77, test_cli_app 30→27, test_cost_aware_routing 14→13, test_dataset_validation 20→22, test_experiments_scripts 23→19, test_swe_bench_source_export 11→13, test_core_modules 29→19, test_executor_sandbox 14→7, test_dataset_loader_extended 73→59 (baseline follows the main table's existing def test_ counting method; the remaining 37 rows checked with no drift) | Per-file `grep -c 'def test_'` cross-check |
> | O-02 | Docs | README.md:607 | "Currently 1111 cases" stale (batch ① data); measured 1158 | 1111→1158 (consistent with the status table's 1158 collected/passed) | pytest collect-only |
> | O-03 | Docs | docs/api_reference.md:174-189 | Error classification "ten-category" enumeration table missing the 2 status-refined categories added in batch ② (1.1: PATCH_VALIDATION_FAILED / RAG_RETRIEVAL_EMPTY); the priority note did not mention the refine_failure_category baseline | Title ten categories→twelve categories; enumeration table adds 2 rows (verdict source + handling strategy); priority note adds the status-category verdict baseline (no regex, successful tasks returned as-is) | Cross-checked against the 12-member enum in src/agents/error_classifier.py |
> | O-04 | Docs | docs/failure_analysis.md:7 | Status note says "expanded to 10 categories"; after batch ② it is 12 | 10 categories→12 (noting batch ② added 2 status-refined categories) | Read the CHANGELOG batch ② entry |
> | O-05 | Docs | QUICKSTART.md:95-96 | 3.2 cost-alert threshold configurability (batch ② APIManagerConfig.cost_alert_threshold) not in the "advanced switches" section | Added 3 lines (default 2.0 + tuning direction + APIManagerConfig example) | Read the 3.2 comment in api_manager.py |
> | O-06 | Docs | CHANGELOG.md | The batch ② wrap-up data alignment changes had no change record | Added a "Documentation alignment (batch ② wrap-up)" subsection to the top Unreleased batch ② entry | Manual check |
>
> > Search conclusions (dimensions with no optimization points): no eval/exec/os.system dangerous calls in the source (re-checked); no real key residual in tracked files (`git ls-files` shows only the .env.example / .env.local.template placeholder templates; .env.local is gitignored); CI matrix/lock check/ruff 0.16.3/pip-audit exemptions (5 PYSEC) with no drift; no TODO/FIXME residual in src; the QUICKSTART `src/cache` cache directory description is consistent with history (the cache directory is created on demand by base_agent, not a fixed directory; kept).
>
> ### Implementation Batches
>
> | # | Goal | Files | Change Method | Test Method | Commit Message |
> |------|------|------|---------|---------|-------------|
> | W1 | O-01~O-05 documentation data alignment | README.md + docs/api_reference.md + docs/failure_analysis.md + QUICKSTART.md | Main table 9 rows + case count 1 + enumeration table 2 rows + priority note + status note 1 row + QUICKSTART 3 lines | ruff check + affected module test subset (test_error_classifier 81 / test_cost_aware_routing 13) | `docs: full-project documentation sync 2026-09-14 batch ② wrap-up (main table 9-row case count drift + error classification 10→12 categories + QUICKSTART cost threshold)` |
> | W2 | O-06 CHANGELOG + plan/report check-in | CHANGELOG.md + optimization_plan.md + optimization_report.md | Batch ② wrap-up documentation alignment subsection + this round's record | Manual check | `docs(optimize): 2026-09-14 batch ② wrap-up round plan and change record` |
>
> ### Points Needing User Confirmation
>
> 1. **O-01 baseline**: the main table keeps the existing `def test_` counting method (not the pytest collection count — parameterized cases differ between the two baselines; the historical M-01 round used this baseline); the 9 rows changed to the measured def test_ values;
> 2. **Phase 6 push**: the user confirmed "execute all + push main" (consistent with historical rounds, direct push rather than feature branch + PR); no new feature branch.

## Status Refinement + Configurable Threshold + Boundary Test Backfill + Source Export + Redaction Audit Round (2026-09-14 batch ②)

> New baseline: 1111 passed (batch ①: 1.2r / 4.1r / 4.3 / 2.2r) / ruff all green / 91% coverage / clean working tree.
> User checklist audit conclusion (2026-09-14 improvement checklist, 14 items): this batch digests 7 pure code items (1.1 status refinement / 1.4 CLI test backfill / 1.5 circuit breaker boundary backfill / 2.1 source export automation / 2.3 RAG metric auto-summary / 3.2 cost alert threshold configurability / 4.1 complete redaction audit); experimental-flow and research items (1.2/1.3 running experiments with env vars, 2.2 SWE-bench backfill, 3.1 cross-file repair, 3.3 dependency cache enhancement, 4.2 Docker enablement, 4.3 archive automation) untouched — see "Explicitly Not Doing" at the end.
>
> Design trade-offs:
> - **1.1 status-refined categories do not use text regex**: `classify()` keeps the 10-category pure-text classification unchanged; `PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` are flow-status categories, determined by `refine_failure_category()` at task wrap-up via `repair_history` / `rag_stats` signals (patch rejected takes priority over RAG empty), with consistent baselines at the benchmark and CLI exits; successful tasks are returned as-is.
> - **3.2 default unchanged**: `cost_alert_threshold` defaults to the module constant 2.0, not changing existing alert behavior; tuning is an explicit configuration act.
> - **4.1 LLM cache not redacted**: the `base_agent` file cache relies on exact `prompt == user_message` match hits; redacted on-disk values would break read-side matching; the cache under HOME shares the trust level of the user repo, recorded as a known acceptable risk.

### Optimization Points of This Round

| ID | Category | Location | Problem | Implementation | Verification |
|----|------|------|------|------|------|
| 1.1s | Error classification | src/agents/error_classifier.py | In the failure distribution "repair failed" and "patch unsafe" are mixed together; the RAG failure scenario (all retrieval empty) has no separate marker | ErrorCategory adds PATCH_VALIDATION_FAILED + RAG_RETRIEVAL_EMPTY (12 categories); new pure function refine_failure_category() (refines at task wrap-up per repair_history/rag_stats, effective only for failed tasks); get_fix_strategy + reports/generator.py if/elif chains synced in 2 places; run_benchmark._build_task_result + CLI _run_single_task wired | tests/test_error_classifier.py +9 cases (81 total) |
| 3.2t | Cost routing | src/api/api_manager.py | Cost alert threshold 2.0 hardcoded; tuning per Provider cost distribution requires code changes | APIManagerConfig.cost_alert_threshold (default 2.0), _try_call_node's alert judgment and message use the configured value | tests/test_cost_aware_routing.py +4 cases (14 total) |
| 1.5b | Tests | tests/test_api_manager.py | Circuit breaker cooldown had only state-machine and routing-filter cases; boundary behavior was not pinned | New TestCircuitCooldownBoundaries 3 cases (expiry auto-return / multi-node simultaneous cooldown degradation / fast failure during cooldown with zero calls) | pytest TestCircuitCooldownBoundaries |
| 1.4c | Tests | tests/test_cli_app.py | CLI parameter exception paths and concurrency timeout/glob behavior untested (64% coverage is the lowest) | 3 groups of 8 new cases (--timeout end-to-end / invalid dataset degradation / single-task timeout does not block the batch / check-dataset boundaries / glob concurrency semantics) | pytest TestRunParallelTimeoutAndInterrupt + TestCheckDatasetBoundaries + TestGlobInParallelMode |
| 2.1e | Experiment | scripts/export_swe_bench_source.py (new) | SWE-bench source supplementation required manual export (official JSONL has no instance_code field); check-dataset had no missing-list output | New script: patch `+++ b/<path>` extracts the first non-test target file + `git show <base_commit>:<path>` read-only export + enrichment JSONL output + `--instance-ids` (comma/@file) + `--dry-run`; SWEBenchDataset.tasks_missing_source() + check-dataset outputs the missing instance_id list | tests/test_swe_bench_source_export.py (new, 11 cases) + tests/test_dataset_validation.py +2 |
| 2.3r | Experiment | experiments/analyze_results.py | RAG metrics only had baseline-level summary; could not analyze "which retrieval type is more effective / which error type benefits most from RAG" | RAG section adds 2 sub-aggregations: breakdown by retrieval type (test_cases vs repairs) + RAG hit × failure-category cross table (1.1s refined categories form their own group; rag_retrieval_empty hit share is always 0 and can serve as a self-check metric) | tests/test_experiments_scripts.py +4 cases (23 total) |
| 4.1a | Security | src/api/api_manager.py + docs/redaction_audit.md (new) | Redaction was only wired into CLI/benchmark entry handlers; when APIManager is used embedded (examples/third-party integration), failover log str(e) and base_url could leak raw | Module-level _redact() in-place redaction at 7 log points (independent of entry wiring); get_status() exit base_url redaction (print_status_table prints directly to stdout, bypassing the logging handler); complete audit docs/redaction_audit.md (three-layer defense overview + per-exit walkthrough + LLM file cache recorded as a known risk) | tests/test_api_manager.py +2 cases (80 total) |

### Implementation Batches

| # | Goal | Files | Change Method | Test Method | Commit Message |
|------|------|------|---------|---------|-------------|
| F1 | 1.1s status refinement 2 categories | error_classifier.py + reports/generator.py + run_benchmark.py + cli/app.py + test_error_classifier.py | Enum + refine pure function + strategy messages + 2 wiring points + 9 cases | pytest test_error_classifier.py | `feat(agents): error classification adds 2 status-refined categories (1.1: PATCH_VALIDATION_FAILED + RAG_RETRIEVAL_EMPTY)` |
| F2 | 3.2t threshold configurability | api_manager.py + test_cost_aware_routing.py | Config field + alert judgment + 4 cases | pytest test_cost_aware_routing.py | `feat(api): cost alert threshold configurable (3.2: cost_alert_threshold, default 2.0)` |
| F3 | 1.5b + 1.4c boundary test backfill | tests/test_api_manager.py + tests/test_cli_app.py | 3 cooldown boundary cases + 8 CLI cases | pytest both test files | `test: circuit breaker cooldown 3 boundaries + CLI parameter exception/concurrency/glob test backfill (1.5 + 1.4)` |
| F4 | 2.1e source export | scripts/export_swe_bench_source.py (new) + dataset_loader.py + cli/app.py + 2 test files | New script + tasks_missing_source + check-dataset list + 13 cases | pytest test_swe_bench_source_export.py + test_dataset_validation.py | `feat(datasets): SWE-bench source export automation (2.1: git show export + missing list)` |
| F5 | 2.3r + 4.1a | analyze_results.py + api_manager.py + docs/redaction_audit.md (new) + 3 test files | RAG dual sub-aggregations + _redact at 7 places + get_status redaction + audit report + 6 cases | pytest 3 test files | `feat(experiments): RAG metric auto-summary (2.3) + complete redaction audit fix (4.1)` |

### Full Verification

- Full suite **1158 passed / 0 failed** (batch ① 1111 + this batch net +47); ruff check all green.
- End-to-end verification: `experiments/analyze_results.py --input <JSON with rag_stats>` outputs the RAG by-type breakdown + cross table sections; `scripts/export_swe_bench_source.py --dry-run` prints the export plan.

### Explicitly Not Doing (Excluded This Round)

- **3.1 Cross-file repair**: architectural level (coordinator-proposer + cross-file dependency analysis + multi-file patch stitching); a standalone project with a design doc;
- **3.3 Dependency cache enhancement** (hit-rate statistics/cleanup command/multi-version): venv lifecycle changes, enabled on demand via a switch;
- **4.2 Docker actual enablement** (that round's 4.2 refers to Docker enablement, not the later 4.2 half-open probe batch — the numbers are reused but the meanings differ; do not confuse): keeps the D-06 reserved interface (use_docker=False); requires confirming the experimental environment has a Docker daemon;
- **4.3 Archive automation** (Zenodo upload/version comparison/summary cards): archive scripts not yet projectized; before enabling, a unified redaction pass is required (see item D of the 4.1a audit conclusion);
- **2.2 SWE-bench backfill + difficulty stratification**: requires API quota relief; experimental flow, not a code change.

## System Feature Enhancement Round (2026-09-14, batch 1.2 residual / 4.1 residual / 4.3 / 2.2)

> New baseline: 1085 passed (09-13 round) / ruff all green / 91% coverage / clean working tree.
> User checklist audit conclusion (verified against the 09-12/09-13 round records): 8 items already implemented (1.2 import/type/logic split, 1.3 dependency isolation EXECUTOR_USE_VENV, 1.4 connection pool configurability MYSQL_POOL_*, 2.1 SWE-bench validation validate_task/quality_report, 2.2 token efficiency token_usage, 2.3 RAG evaluate_retrieval/--enable-rag, 1.1 log redaction SensitiveFormatter, 4.1 circuit breaker max_consecutive_failures threshold wiring); this batch handles the 4 items that are truly residual:
>
> 1. **1.2 residual**: ErrorCategory still lacks LLM_FORMAT_ERROR / INDEX_ERROR. failure_analysis.md shows UNKNOWN at 75% (JSON parse failures + empty responses), and case 2's IndexError was misclassified as UNKNOWN; the Debugger cannot target the repair;
> 2. **4.1 residual**: the circuit breaker threshold (max_consecutive_failures=3) is wired, but there is no cooldown — a dead provider is flipped back to is_healthy=True by the health-check thread within 60s, and traffic flows back, wasting time and tokens;
> 3. **4.3**: run_benchmark.py's output JSON can only be paged through manually; there is no summary analysis entry;
> 4. **2.2 residual**: token_metrics are recorded but the summary/progress output does not print the "efficiency-vs-effectiveness" comparison; fairness checks lack data.
>
> Explicitly not doing (excluded this round, standalone projects or on-demand switches): 1.3 venv reuse (large executor lifecycle change), 2.1 SWE-bench data validation (requires real data), 3.3 cross-file repair (architectural design), 3.1/3.2 default switches (just set the ENABLE_MULTI_CANDIDATE_PATCH / AITESTER_TRACE_DIR env vars when running experiments; no code change), 4.2 Docker (the D-06 reserved interface, no consumer kept).

### Optimization Points of This Round

| ID | Category | Location | Problem | Implementation | Verification |
|----|------|------|------|------|------|
| 1.2r | Error classification | src/agents/error_classifier.py | UNKNOWN accounts for 75% of failure samples; two sub-types — JSON parse failure/empty response (LLM response format) and IndexError (out of bounds) — have targeted repair paths but are classified as UNKNOWN, forcing the Debugger onto the generic fallback strategy | ErrorCategory adds LLM_FORMAT_ERROR + INDEX_ERROR; classify() priority adjusted (LLM_FORMAT first — JSON parse text almost never contains IndexError, whereas IndexError text may contain assert; reversing the order misclassifies); new _RE_LLM_FORMAT_ERRORS (JSONDecodeError/Expecting value/Could not find complete JSON/empty response/incomplete-truncated) and _RE_INDEX_ERROR (IndexError/index out of range/subscript out of range); get_fix_strategy adds 2 strategies; reports/generator.py if/elif chains synced in 2 places | tests/test_error_classifier.py +10 cases (72 total) |
| 4.1r | Observability | src/api/api_manager.py | The circuit breaker only "marks unhealthy" with no cooldown: after a dead provider is flipped back healthy by the periodic health check, traffic immediately flows back, and the consecutive-fail→flip-back→fail-again cycle wastes tokens | APIHealth adds circuit_open_until (monotonic) + circuit_cooldown_seconds fields and the in_circuit_open property; mark_failure writes the cooldown deadline on reaching the threshold, mark_success resets; get_healthy_nodes() and _build_node_list fallback candidates uniformly filter nodes inside the cooldown; APIManagerConfig.circuit_cooldown_seconds defaults to 60.0; get_status() exposes circuit_open_remaining_s; add_node/reset_stats wired | tests/test_api_manager.py +9 cases (72 total) |
| 4.3 | Experiment | experiments/analyze_results.py | Result JSON requires manual field paging; summary work grows linearly with experiment scale | New analysis script: core metric comparison table + token efficiency comparison table (2.2 fairness) + iteration count distribution + per-baseline failure-reason distribution (1.2 refined categories countable separately) + RAG retrieval quality (output only when retrievals>0); old JSON missing token_metrics/rag_metrics keys falls back to details; terminal print + writes analysis_summary.md | tests/test_experiments_scripts.py +6 cases (pure function, no file system access) |
| 2.2r | Experiment | experiments/run_benchmark.py | token_metrics are persisted but the summary/progress output has no efficiency dimension; "full system vs Plain LLM" looking only at success rate is unfair | Summary stage adds baseline-level failure_category_distribution field; logger + progress output print per-baseline "average tokens / LLM call count per task" (two-dimensional efficiency-effectiveness comparison) | Full pytest + manual analyze_results run to verify fields |

### Implementation Batches

| # | Goal | Files | Change Method | Test Method | Rollback | Commit Message |
|------|------|------|---------|---------|---------|-------------|
| F1 | 1.2r error classification adds 2 categories | src/agents/error_classifier.py + src/reports/generator.py + tests/test_error_classifier.py | Enum + classify priority + regex + strategy messages + report branches + 10 cases | pytest test_error_classifier.py | `git revert` | `feat(agents): error classification adds LLM_FORMAT_ERROR + INDEX_ERROR (1.2 residual, the 75% UNKNOWN root cause separated)` |
| F2 | 4.1r circuit breaker cooldown | src/api/api_manager.py + tests/test_api_manager.py | APIHealth/APIManagerConfig fields + routing filter + 9 cases | pytest test_api_manager.py | `git revert` | `feat(api): 4.1 circuit breaker cooldown (circuit_open_until + routing-layer cooldown filter, default 60s)` |
| F3 | 4.3 result analysis script | experiments/analyze_results.py + experiments/run_benchmark.py + tests/test_experiments_scripts.py | New analysis script + baseline-level failure distribution field + fairness output + 6 cases | pytest test_experiments_scripts.py + manual script run | `git revert` | `feat(experiments): 4.3 result analysis script + 2.2 baseline token efficiency summary output` |
| F4 | Documentation sync | CHANGELOG.md + optimization_plan.md | Append 09-14 round entry | Manual check | `git revert` | `docs(optimize): 2026-09-14 round plan and change record` |

### Points Needing User Confirmation

1. **1.2r priority adjustment**: LLM_FORMAT_ERROR placed before IMPORT_ERROR (at the front). Impact: errors whose text contains JSON signatures such as "Expecting value" now take the LLM format strategy instead of the import/syntax strategy; if a task has both an import error and an LLM format problem (rare), the LLM format is handled with priority.
2. **4.1r default 60s cooldown**: provider failover scenarios in historical experiments should have skipped dead nodes to begin with; the cooldown merely extends "skip" from the is_healthy dimension to the window during which is_healthy has been flipped back to True; normal failover is unaffected (after the cooldown expires, traffic passes automatically).
3. **Push**: this batch has 4 commits, consistent with historical rounds, `git push origin main` direct push.

## System Feature Enhancement Round (2026-09-13, batch 3.1 / 3.4 / 4.1 / 2.3 / 1.5)

> New baseline: 1085 passed / ruff all green / 91% coverage (TOTAL 3536/318 miss baseline unchanged; src line count grew after adding new modules) / clean working tree.
> User checklist audit: 8 items already implemented (1.2 error classification refinement import/type/logic, 1.3 dependency isolation EXECUTOR_USE_VENV,
> 1.4 connection pool configurability MYSQL_POOL_*, 2.1 SWE-bench validation validate_task/quality_report,
> 2.2 token efficiency token_usage, 2.3 RAG evaluate_retrieval/--enable-rag, 1.1 log redaction SensitiveFormatter,
> 4.3 circuit breaker max_consecutive_failures threshold wiring); this batch implements the 4 items that are truly missing + strengthens 2.3/1.5.

### Optimization Points of This Round

| ID | Category | Location | Problem | Implementation | Verification |
|----|------|------|------|------|------|
| 3.1 | Feature | src/tools/multi_candidate.py | A single patch "one wrong step and every step is wrong": LLM occasionally outputs a bad patch that pollutes target_code and carries the wrong diagnosis into the next round | Multi-candidate patches: N candidates (perspective-perturbation prompts) + static filtering (ast syntax/function completeness/10% length) + optional execution verification picks the best; wired through workflow _patch_applier_node, ENABLE_MULTI_CANDIDATE_PATCH defaults to false, no valid candidate falls back to single patch | tests/test_multi_candidate.py (19 cases) |
| 4.1 | Observability | src/observability/trace.py | Experiment analysis could only reverse-engineer from log text "what decision some agent made on some task, how many tokens/time it spent"; no structured replay | JSONL trace layer: TraceSession records node I/O/decision path/tokens/time per <task_uuid>.trace.jsonl; wired into workflow nodes + benchmark/CLI; when AITESTER_TRACE_DIR is unset it is fully no-op with zero performance tax; when set, it passes through redaction | tests/test_trace_observability.py (12 cases) |
| 3.4 | Performance | src/api/api_manager.py | APIManager failover ignores cost and may switch all traffic to an expensive provider | COST_AWARE strategy (50% success rate + 50% 1/cost scoring) + cost alert (cost_weight>=2.0 logs WARNING, can be disabled); LLMConfig.cost_weight read via LLM_N_COST_WEIGHT | tests/test_cost_aware_routing.py (10 cases) |
| 2.3 | Experiment | reproduce.sh | Synthetic dataset experiments did not enable RAG by default; "full system vs Plain LLM" comparison lacked retrieval augmentation | reproduce.sh defaults to --enable-rag for synthetic/examples (rag_data/ persistent reuse), --no-rag can fall back; run_benchmark.py adds the --no-rag argument | Manual reproduce.sh run to verify argument passing |
| 1.5 | Tests | tests/test_cli_app.py | CLI parallel/json boundaries, argument parsing, and error exit paths had low coverage | New TestRunParallelJsonBoundaries (6 cases): single file + concurrency takes the sequential branch, multi-file concurrency degradation, glob wildcard intercepted by click, concurrency all-pass/has-failure exit codes | Full pytest |

### Implementation Batches

| # | Goal | Files | Change Method | Test Method | Rollback | Commit Message |
|------|------|------|---------|---------|---------|-------------|
| F1 | 4.1 structured JSONL trace layer | src/observability/{__init__,trace}.py + src/graph/workflow.py + src/cli/app.py + experiments/run_benchmark.py + tests/test_trace_observability.py | New observability package + workflow node/benchmark/CLI wiring | pytest test_trace_observability.py | `git revert` | `feat(observability): 4.1 new structured JSONL trace layer (node decision/tokens/time, off by default)` |
| F2 | 3.4 cost-aware routing | src/api/api_manager.py + config.py + tests/test_cost_aware_routing.py | COST_AWARE strategy + cost alert + LLMConfig.cost_weight | pytest test_cost_aware_routing.py | `git revert` | `feat(api): 3.4 cost-aware routing COST_AWARE + expensive provider cost alert` |
| F3 | 3.1 multi-candidate patches | src/tools/multi_candidate.py + src/graph/workflow.py + tests/test_multi_candidate.py | Multi-candidate generation + static/execution verification filtering + workflow wiring | pytest test_multi_candidate.py | `git revert` | `feat(tools): 3.1 multi-candidate patch generation and verification filtering (off by default, falls back to single patch with no candidate)` |
| F4 | 2.3 RAG on by default | reproduce.sh + experiments/run_benchmark.py | Synthetic/built-in datasets default to --enable-rag + --no-rag argument | Manual verification | `git revert` | `feat(experiments): 2.3 reproduce.sh synthetic dataset RAG on by default + --no-rag` |
| F5 | 1.5 CLI boundary test backfill + docs | tests/test_cli_app.py + .env.example + CHANGELOG.md + README.md + src/tools/__init__.py | 6 CLI boundary cases + new module docs | pytest test_cli_app.py + ruff | `git revert` | `test(cli): 1.5 parallel/json boundary test backfill + new module doc alignment` |

### Points Needing User Confirmation

1. **Safe off-by-default switches**: 3.1/4.1 are both off by default via env vars, keeping the historical experiment baseline unchanged; enabling is an explicit act (`ENABLE_MULTI_CANDIDATE_PATCH=true` / `AITESTER_TRACE_DIR=<dir>`), with no implicit behavior change.
2. **3.4 cost field source**: `LLM_N_COST_WEIGHT` goes through `.env.local` (gitignored, not in the repo), unconfigured default 1.0 baseline; to persist per-provider costs, add a cost_weight field to llm_configs.json (this round uses the env-var baseline first to avoid changing the JSON structure).
3. **Push**: this batch has 5 commits, consistent with historical rounds, `git push origin main` direct push (if main is ahead, push everything).

## Phase 1 Optimization Points List (Final Version After Deduplication and False-Positive Removal)

| ID | Category | Location | Problem | Evidence | Impact | Suggestion | Priority | Risk | Verification |
|----|------|------|------|------|------|------|--------|------|---------|
| D-01 | Docs | README.md:887-892 | The v0.9.10 "new test modules" table lists 4 non-existent test files | `test_api_manager_large_scale.py`/`test_error_classifier_improvements.py`/`test_executor_integration.py`/`test_patch_applier_improvements.py` have no corresponding tests/ files | Ghost docs mislead readers | Remove these 4 rows from the table (keep the actually existing rows such as test_api_manager.py/test_base_agent_extended.py/test_report_generator.py) | P2 | None | `ls tests/` line-by-line check |
| D-02 | Docs | README.md | "Latest optimization" status table case counts do not match 0.9.11's actual 1020 (table shows 963 etc., old 0.9.10-era values) [speculative: needs line-by-line check] | Read the README test status table to confirm | Stale data | Sync to 1020 after checking | P2 | None | Cross-check with CHANGELOG 0.9.11 |
| D-03 | Config | .env.example:84 | RAG_PERSIST_PATH exists only as a comment line; configurable but not exemplified | `# RAG_PERSIST_PATH=` | Low | Keep as-is or provide a non-comment example | P3 | None | Read .env.example |
| D-04 | Docs | .env.example | DOCKER_IMAGE=python:3.12-slim matches the Dockerfile FROM, but config.py default is python:3.12-slim while the local .env actually writes python:3.11-slim (local .env inconsistent with the default) | Local .env line 32 `DOCKER_IMAGE=python:3.11-slim` | Local .env inconsistent with the doc template (.env not in the repo; local confusion only) | Change the local .env DOCKER_IMAGE to 3.12-slim (local only, does not affect commits) | P3 | None | Compare |
| D-05 | Security | local .env / src/.env.local / .env.local | Real API keys written in plaintext (22 LLM_N_ configs, multiple sk- prefixed keys) | `grep -c "sk-" .env` = 2; src/.env.local 2680B real keys | Key leak risk (currently not git-tracked, no historical commit; a local asset, not a repo leak) | Do not commit to git; recommend the user rotate/converge keys; the code layer already uses placeholders | P1 (notification item, not a code change this round) | Low (read-only reminder) | `git ls-files` confirms untracked |
| D-06 | Code | src/graph/workflow.py:476 / src/agents/executor.py:153 | `use_docker` parameter kept but always False, no consumer; `DOCKER_ENABLED` is read but there is no real Docker execution path | `grep DOCKER_ENABLED` only in config.py/executor.py comments | Dead interface; docs explain it as "reserved" | Docs already explain; code kept, not deleted (avoids breaking the API) | P3 | None | Read the comments |
| D-07 | Security | src/utils/logging_utils.py | API key redaction regex `sk-[a-zA-Z0-9]{20,}` only matches 20+ chars with the `sk-` prefix; local keys include `sk-ws-H.EPIHIXL...` (with dots) and `e2b08862...` (no sk- prefix) — two types not covered by this pattern | Local key shapes vary | Some keys logged would bypass redaction | Extend the redaction regex to cover generic hex/base64 long strings | P2 | Medium (must not over-match) | Unit tests cover the new patterns |
| D-08 | Docs | README.md | Test status table and coverage description need to align with 0.9.11 (1020/91%) | See D-02 | Stale data | Sync | P2 | None | Cross-check with CHANGELOG |
| D-09 | Docs | README.md:346 | README says "ablation experiment switches are configured in .env or config.py", but the actual switches (ENABLE_PLANNER/RAG/DEBUGGER) are only read by config.py; .env.example has no such items | README inconsistent with .env.example | Reader confusion | Change README wording to "config.py defaults or .env injection" | P3 | None | Read .env.example |
| T-01 | Tests | tests/conftest.py | Each test file repeatedly constructs LLMConfig/APIManager mocks; a common fixture could be extracted [subagent suggestion, needs check] | Spot-checked 8-12 files | Maintenance cost | Extract `make_llm_config`/`make_api_manager` into conftest | P3 | Medium (refactoring) | Full pytest |
| T-02 | Code | src/prompts/templates.py 42% coverage | Prompt string templates have low coverage (reasonable — string concatenation is hard to unit test) | 91% total coverage, this file 42% | Low | Keep as-is, do not force coverage up | P3 | None | Read the file |
| T-03 | Code | src/cli/app.py 61% / output.py 58% coverage | CLI command parsing and rich output branches have low coverage | 0.9.10 already mentioned app.py 50%→61% | Medium | Backfill 2-3 key CLI cases (list-examples/--version already covered; add parallel/json boundaries) | P2 | Low | New tests |
| T-04 | Security | src/agents/executor.py sandbox | The subprocess sandbox executing the code under test needs confirmation that no eval/exec/os.system direct execution exists | Subagent to confirm | High (if there is an escape) | Audit the subprocess boundary | P1 (to confirm) | Low | grep exec/eval |
| T-05 | Code | root expand_models.py / init_db.py / config.py | Root-level scripts are not packaged by setup.py (find_packages only), but README/QUICKSTART call them directly via `python xxx.py`; they are "in-repo scripts", not in-package | Docs and reality match (local run) | Low (after installing as a package the root scripts are unavailable, but docs target in-repo running) | Docs already explain; keep | P3 | None | Read the docs |
| T-06 | Code | src/api/api_manager.py | Health-check thread consumes quota; 0.9.11 added the `enable_health_checker` switch and tests use False | Already fixed | None | Keep | P3 (done) | None | Read CHANGELOG |
| D-10 | CI | .github/workflows/ci.yml | CI already includes lock sync check + pinned ruff version + pip-audit + Codecov, structure complete; 5 local ahead commits unpushed | `git status` ahead 5 | Pushing passes CI (no sign of failure) | Verify CI-equivalent commands locally before pushing | None | None | Local ruff/pytest |

## Post-0.9.11 Optimization Round (2026-09-13, documentation data alignment batch M-01~M-03)

> New baseline: 1038 passed / ruff all green / 91% coverage (TOTAL 3536/318 miss) / lock in sync (19 vs 130) / sdist+wheel build passed / pip-audit no unexempted vulnerabilities (venv Python 3.14.6).
> Working tree clean, local main in sync with origin/main (the 09-12 round's 18 commits all pushed, no backlog).
> Previous round's completed items (N-01~N-04) are not repeated.

### New Optimization Points of This Round (search coverage: README test data, docs directory, dangerous calls, key residual, CI, executor sandbox boundary)

| ID | Category | Location | Problem | Evidence | Impact | Suggestion | Priority | Risk | Verification |
|----|------|------|------|------|------|--------|------|--------|---------|
| M-01 | Docs | README.md:581-621 test coverage module main table | 13 files' "test function counts" drifted from measured `def test_` counts (not synced after 27 regression cases were added two rounds ago) | Per-file regex measurements: test_api_manager 62→63, test_cli_app 11→15, test_config_manager 29→32, test_dataset_loader_extended 57→62, test_dependency 27→35, test_error_classifier 56→60, test_executor 35→39, test_experiments_analysis 11→15, test_experiments_scripts 8→10, test_generator 21→30, test_mysql_client 12→13, test_patch_applier 36→38, test_workflow 28→30 | Main table data inconsistent with code (acceptance criteria require docs consistent with code) | Sync the 13 rows' values to the measured values (the header's intent is "test function count", by the `def test_` counting baseline) | P2 | None | Cross-check with per-file grep measurements |
| M-02 | Docs | README.md:577/619 | ① "41 test files" does not match the actual 44 .py files in tests/; ② main table missing `test_logging_utils.py` (the 14-case redaction test added in the 09-11 round) | `ls tests/*.py | wc -l` = 44 (45 entries including `__init__.py`); main table's last row is test_workflow_extended, no logging_utils row | Readers miss the redaction tests' existence | 41→44; insert a `test_logging_utils.py` row after the test_llm_file_cache row (14, log redaction regex regression) | P2 | None | `ls tests/` check |
| M-03 | Docs | CHANGELOG.md | Unreleased (2026-09-13) round entry missing; this round's doc changes have no change record | Current Unreleased only reaches 2026-09-12 | Changes not traceable | Add the 2026-09-13 round entry (M-01/M-02 notes + full-suite test conclusion) | P3 | None | Read CHANGELOG |

> Search conclusions (dimensions with no optimization points, to avoid re-checking in later rounds):
> - Dangerous call re-check: no `eval(`/`exec(`/`os.system` calls in src/ (only the `evaluate_retrieval` method name in retriever.py false-positive);
> - executor subprocess boundary re-check: `_run_pytest_with_retry`'s `subprocess.run(cmd, ...)` command is a controlled constructed pytest invocation (with timeout/cwd/env constraints), not user-input concatenation; no escape calls at the sandbox boundary (deep audit still listed as a follow-up);
> - Key residual re-check: `git ls-files` tracks only .env.example / .env.local.template (placeholders); real keys exist only in the gitignored local .env (2 sk-) and src/.env.local (5 sk-); consistent with the 09-12 round conclusion; rotation recommended;
> - Dependencies: all 130 items in sync with requirements.lock; pip-audit (same 4 PYSEC exemptions as CI) No known vulnerabilities found, 5 ignored;
> - CI structure no drift (matrix 3.12/3.14, lock check, pinned ruff 0.16.3, codecov, pip-audit);
> - No stale case-count/coverage residual in docs/ or QUICKSTART; README version narrative sections (v0.9/v0.10) are historical version records, not synced with the baseline (reasonable).

### Implementation Batches of This Round

| # | Goal | Files | Change Method | Test Method | Rollback | Commit Message |
|------|------|------|---------|---------|---------|-------------|
| B2-1 | M-01 main table 13-row drift sync + M-02 file count 41→44 and add test_logging_utils row | README.md | 13 rows' values to measured, title row 41→44, insert 1 row | Per-file grep cross-check + ruff, no code impact | `git revert` | `docs(readme): test coverage main table 13 case-count drifts synced + test_logging_utils row added` |
| B2-2 | M-03 CHANGELOG 2026-09-13 entry + plan/report check-in | CHANGELOG.md / optimization_plan.md / optimization_report.md | Append Unreleased round entry and this round's record | Manual check | `git revert` | `docs(optimize): 2026-09-13 round plan and report check-in (M-01~M-03 documentation data alignment batch)` |

### Points Needing User Confirmation

1. **M-01/M-02 main table sync**: pure documentation changes, zero code risk, recommended to execute directly.
2. **Phase 6 push**: the user confirmed "documentation batch + push; retry if the push fails". This round adds 2 commits; push `git push origin main` (if 443 hangs, retry or fall back to `http.version HTTP/1.1` per the 09-11/09-12 round experience); no new feature branch, main direct push (consistent with historical rounds; the PR body is kept as a manual fallback).

## Post-0.9.11 Optimization Round (2026-09-12)

> New baseline: 1038 passed / ruff all green / 91% coverage (TOTAL) / lock in sync / wheel+sdist build passed (venv Python 3.14.6).
> Previous round's completed items (D-01~D-09, T-02/T-03/T-05/T-06, B1/B2, setup.py py_modules, CI exemption sync) are not repeated.

### New Optimization Points of This Round (search coverage: directory structure/duplicate code, dependencies & security, error handling/boundaries, performance, tests, CI, doc consistency)

| ID | Category | Location | Problem | Evidence | Impact | Suggestion | Priority | Risk | Verification |
|----|------|------|------|------|------|--------|------|--------|---------|
| N-01 | Docs | README.md:12/16 | Core module coverage data stale: `logging_utils 83%`, `cli-app 61%` (0.9.11 batch old values); actually up to 88% / 64% (drifted without sync after 18 cases were added last round) | `pytest --cov=src --cov-report=term-missing` measured 88%/64% | Docs inconsistent with code (acceptance requirement) | Sync the two coverage rows to 88%/64% | P2 | None | Cross-check with measured coverage output |
| N-02 | Docs | README.md:66 | CI security scan note still says "4 known CVEs"; last round the exemption IDs drifted to PYSEC-2026-311/3813/3814/3815 (still 4 exemptions but the wording/baseline is outdated) | `grep "4 known CVEs" README.md` 1 hit; ci.yml already changed to the PYSEC baseline | Readers think it is still the old CVE list | Change to "5 exemptions (including 2 duplicate PYSEC-2026-311 entries + PYSEC-2026-3813/3814/3815)", aligned with the ci.yml comments | P2 | None | Read the ci.yml comments |
| N-03 | Docs | QUICKSTART.md:48 | Step 4 title "Verify configuration"; the command `python3 -c "from config import LLM_CONFIGS; print(...)"` only verifies configuration **loading**, does not test the API connection (no network call) | That line's docstring does not match the command's behavior | Users may think the command probes the network | Change the title to "Verify configuration loaded", add a note (a real connection probe uses `python scripts/check_quota.py`, already present in step 6) | P3 | None | Read config.py |
| N-04 | Code | README.md ghost check (new round) | Last round removed v0.9.10's 4 ghost test-file rows; need to re-check whether the README "test status" section still drifts from the actual 45 files in tests/ | `ls tests/` vs README references | Low | Fix if drift is found after checking | P2 | None | `grep -oE "tests/test_[a-z_0-9]+\.py" README.md | sort -u` then `ls` each one |

> Search conclusions (dimensions with no optimization points, to avoid re-checking in later rounds):
> - No eval/exec/os.system calls in the source (the only `grep` hit is the `evaluate_retrieval` method name at retriever.py:425, not a dangerous call);
> - No real key residual in source or tests (normalized in 80e2f05 last round; re-check passed this round);
> - All 130 dependency items in sync with requirements.lock; pip-audit (same exemptions as CI) No known vulnerabilities found, 5 ignored;
> - CI structure complete (matrix 3.12/3.14, lock check, pinned ruff 0.16.3, failure diagnostic annotations, codecov, pip-audit); no new drift;
> - No TODO/FIXME residual in src; T-04 executor sandbox audit (carried over from last round) re-checked only the subprocess boundary — no escape calls; the deep audit still needs a design doc, kept as a follow-up suggestion.

### Implementation Batches of This Round

| # | Goal | Files | Change Method | Test Method | Rollback | Commit Message |
|------|------|------|---------|---------|---------|-------------|
| B1-1 | N-01 coverage data alignment | README.md | 83%→88%, 61%→64% (two rows) | Cross-check with measured coverage | `git revert` | `docs(readme): core module coverage data aligned to 88%/64% measured values` |
| B1-2 | N-02 CVE baseline alignment | README.md | "4 known CVEs" changed to the PYSEC exemption baseline | Read the ci.yml comments | `git revert` | `docs(readme): security scan note aligned to the PYSEC exemption list baseline` |
| B1-3 | N-03 wording fix | QUICKSTART.md | Title "Verify configuration"→"Verify configuration loaded" + one-line note | Read config.py | `git revert` | `docs(quickstart): configuration verification step wording fixed (load check only; see check_quota for connection probing)` |
| B1-4 | N-04 ghost test file re-check | README.md | Change if drift found; no commit if no drift | grep+ls check | N/A | Per check result |

### Points Needing User Confirmation

1. **N-01/N-02 documentation alignment** (batch B1): pure documentation changes, zero code risk, recommended to execute directly.
2. **Phase 6 push**: main is already 18 commits ahead of origin/main (including all previous round's results); this round will add another 1-3 commits. Push and create a PR? (The same flow was confirmed last round; the network was once blocked by a 443 long-connection hang; this round will retry the push; on failure, output manual commands + the PR body.)

## Scope of This Implementation (by priority, rollback-safe, atomic commits)

> Principle: only **low-risk, high-certainty** fixes and doc alignment; no large refactoring (T-01 common fixtures, T-04 sandbox audit listed as follow-up suggestions). Each logical change is a separate commit.

### Batch A (P1/P2 doc-code consistency, pure docs, zero code risk)
| # | Goal | Files | Change Method | Test Method | Rollback | Commit Message |
|------|------|------|---------|---------|---------|-------------|
| A1 | Remove 4 ghost test-file rows from README | README.md | Delete 4 table rows | `grep` check + no code changes | `git revert` | `docs(readme): remove 4 non-existent test files from the test status table` |
| A2 | Align README test/coverage data to 1020/91% | README.md | Update the "latest optimization" row and case count | Cross-check with CHANGELOG | `git revert` | `docs(readme): test case count and coverage aligned to the 0.9.11 baseline` |
| A3 | Align README ablation switch wording (.env has no ENABLE_*) | README.md:346 | Wording changed to "config.py defaults or .env injection" | Read .env.example | `git revert` | `docs(readme): ablation experiment switch configuration location wording aligned` |

### Batch B (P2 code, small scope + new/updated tests)
| # | Goal | Files | Change Method | Test Method | Rollback | Commit Message |
|------|------|------|---------|---------|---------|-------------|
| B1 | Extend log redaction regex (covers dot-separated / long keys without sk- prefix) | src/utils/logging_utils.py | Regex adds `.` and generic long-string branches + unit tests | New pytest cases (redaction assertions) | `git revert` | `fix(utils): log redaction regex covers dots and keys without sk- prefix` |
| B2 | Backfill key CLI branch tests (parallel/json boundaries) | tests/test_cli_app.py | Add 2-3 cases | Full pytest | `git revert` | `test(cli): backfill run parallel and json boundary regressions` |

### Batch C (P3 local config alignment, local .env only, not committed to git)
- C1: Change the local `.env`'s `DOCKER_IMAGE` to 3.12-slim (consistent with the template/default) — local file only; `.env` is not in the repo anyway; noted separately, not committed.

### Out of Scope This Time (Listed as Follow-up Suggestions)
- T-01 common fixture extraction (refactoring, needs broad regression)
- T-04 executor sandbox deep audit (high risk, needs a design doc)
- D-05 key rotation (user-side operation, no code change)
- CI push of 5 ahead commits (phase 6)

## Points Needing User Confirmation
1. **Batch B1 redaction regex extension**: it will change `logging_utils.py` behavior (affects all log redaction going through that module). Please confirm whether to include it this round, or proceed with docs-only batch A first.
2. **Phase 6 push**: main is 5 commits ahead of origin/main, and this round will add another 3-5 commits. Push and create a PR? (The user answered "allowed", but the push is a network/production high-risk act; before pushing I will list all commits to be pushed for final confirmation.)

---

## 2026-09-15 Full-Project Convergence Round (Implementation Completion Record)

> Baseline: 1247 passed / 91% coverage. Three-way subagent audits + manual review; landed 11 files + 23 cases → 1270 passed / 92% coverage.
> Detailed record in optimization_report.md "Appendix: 2026-09-15 Full-Project Convergence Round" and CHANGELOG [0.9.14].

### Landed Items
- Config centralization: removed 3 dead constants from config.py; converged SWE_BENCH_ENRICHMENT into config; converged MULTI_CANDIDATE_EXEC_VALIDATE into a helper.
- Bug fixes: executor's standard-library list wrongly listed third-party diskcache (reused is_standard_library); cross-file fallback could not write to disk (dict vs str);
  _set_thread_api backfilled model_name.
- Dead code cleanup at 4 places + RAG retriever write lock/`_upsert` extraction + refine wiring convergence + cross_file docstring made truthful.
- Test backfill: nodes.py off-by-default branches + config_manager empty-field/write-disk exceptions + CLI check-dataset + env switches, 23 cases in total.

### Intentionally Kept (recorded, not fixed, deferred to later batches)
- A third residual implementation of the statistical significance test (`src/experiments/analysis.py::_compute_significance` vs
  `experiments/statistical_analysis.py`): paired-logic + `_MIN_SAMPLES_FOR_TEST=3` magic number duplicated in two places; medium risk.
- AITesterState initialization dict duplicated at two places, cli/app.py and run_benchmark.py (~18 keys); suggest extracting a `make_initial_state()` factory.
- retriever `retrieve_test_cases` / `retrieve_repairs` are isomorphic (different result fields; extraction payoff is moderate).
- cli/app.py coverage still 70% (the lowest); pure display/`__main__` demo blocks make up a large share; test backfill cost-effectiveness is low.

### Version
- 0.9.11 → 0.9.14; CHANGELOG's 14 Unreleased entries converged into 0.9.12/0.9.13/0.9.14; api_reference/README synced.
