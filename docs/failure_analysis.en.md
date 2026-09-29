> **Language**: [中文版](failure_analysis.md) | English (this document)

# Failure Case Analysis

> ## 🚨 Historical Snapshot Warning (reader notice, pinned 2026-10)
>
> **This document is a 2026-09-14 batch data snapshot** (50-task synthetic
> experiment + SWE-bench repo-level verification P0/P1); **all data is frozen
> to that batch and is not auto-refreshed across version iterations**:
>
> 1. **All repo-level verification data is based on the free-tier model
>    (`agnes-3.0-flash`)**, reflecting that model's capability boundary rather
>    than AITester's architecture. Results from stronger models (GPT-4 class)
>    are stored separately in
>    `experiments/results/experiment_report_<date>_repo_level.md` and are not
>    appended here (to avoid polluting the free-tier baseline snapshot).
> 2. **Error-classification counts in the body (e.g. "12 classes / 16
>    classes") are in-batch historical figures**. The classification scheme now
>    has **17 categories** (`ErrorCategory` enum, `PATCH_SYNTAX_INVALID` added
>    in the 2026-09-27 batch); see
>    [docs/api_reference.md](api_reference.md) § error-category enum
>    (seventeen categories) for the canonical list.
> 3. After re-running experiments, treat the latest
>    `experiments/analyze_failures.py` / `experiments/analyze_results.py` output
>    as authoritative; this file is retained only as a historical evidence
>    chain.
>
> Snapshot frozen date: 2026-09-14 (batch scope).

> ⚠️ **Historical snapshot**: this document is a 2026-09 batch data snapshot (50-task synthetic experiment + SWE-bench repo-level P0/P1); **data is not auto-refreshed across version iterations**. All repo-level verification data is based on the free-tier model (`agnes-3.0-flash`); results from stronger models are stored in separate files, not appended here.

## Overview

This document analyzes in depth the failure cases of AITester in synthetic dataset experiments, identifying system bottlenecks and directions for improvement.

> **Historical-snapshot declaration** (archival rule: CONTRIBUTING.md "Documentation organization conventions"): this document is a
> historical data snapshot (50-task synthetic experiment + SWE-bench repo-level
> verification P0/P1, measured on a free-tier small model) and its data is not
> auto-refreshed as versions iterate. The "UNKNOWN 75%" distribution below is the
> 2026-09-14-batch historical baseline, corresponding to the state in which
> `ErrorCategory` had been extended to 12 classes (adding `LLM_FORMAT_ERROR` /
> `INDEX_ERROR`, etc.) and the classifier had already identified them separately —
> **the historical wording records the classifier state at the time, not current
> capability**; the current category count and failure-attribution baseline follow
> [BASELINE.yaml](../BASELINE.yaml) (category count) and `docs/api_reference.md`.
>
> When the experiment is re-run, the new failure distribution should be significantly
> lower than this snapshot; take the three sections output by the latest
> `experiments/analyze_results.py` as authoritative: **"Failure Cause Distribution
> by Baseline"** (1.2 refined categories counted separately) + **"Repair Convergence
> Efficiency (1.2)"** (first-attempt success rate / iteration and elapsed statistics
> for successful tasks) + **"Multi-dimensional Quality Proxies (1.1, conservatively
> recomputable)"** (coverage / elapsed / assertion lines / top-N failure categories).
> Additionally: after the 5.3 batch, `experiments/analyze_failures.py` added the
> **three major failure root-cause classes** (`llm_capability` / `dependency` /
> `framework`) + a **failure case knowledge base** (structured JSON from
> `failure_knowledge_base()`, written to disk via CLI `--knowledge-base/-k`); take
> that script's output as the authoritative failure-attribution baseline. The
> offline-to-online closed loop from the failure knowledge base into repair strategy
> is designed in [docs/design/failure_knowledge_feedback.md](design/failure_knowledge_feedback.md).
>
> **SWE-bench 0/7 failure-attribution boundary**: measured on the **free-tier small
> model (agnes-3.0-flash)**; it reflects the fix-quality boundary of that model on
> real repo-level code, not a limitation of the AITester architecture itself. With a
> stronger model (GPT-4 class), the failure categorization and counts are expected to
> change significantly; stronger-model repo-level verification data is stored
> separately in `experiments/results/experiment_report_<date>_repo_level.md` and is
> not appended in-place here (to avoid polluting the free-tier baseline snapshot).

> **Status note (2026-09-25, SWE-bench repo-level verification P0/P1)**: The first 0/20 on SWE-bench lite-20 repo-level verification (`RepoExecutor`, `REPO_LEVEL_EXECUTION=true`) was initially misdiagnosed as "the LLM engine cannot produce an applicable patch" (`repo_verification.llm_applied` all False). **Root cause corrected** — the 0/20 was the superposition of three defect layers: data pipeline (missing `instance_code`) + execution environment (a single temporary-file executor cannot hold repo-level code + global-python cross-commit editable-install pollution) + patch pipeline (`_diff_codes` hand-joining with difflib produced corrupt unified diffs in the "whole-file rewrite" scenario, rejected by `git apply`) — **not LLM engine capability**. After the fixes (`SWE_BENCH_ENRICHMENT` injecting real source + `RepoExecutor` repo-level clone + pip install -e + venv isolation + `_diff_codes` switched to `git diff --no-index` for an applicable unified diff), the P1 single-source 0/7 failure categorization is: 5/7 `LLM_BREAKS_IMPORT` (LLM rewrites break sqlfluff's plugin naming contract — a mangled `Rule_L*` class name → the whole import chain crashes) + 2/7 `EMPTY_LLM_PATCH` (LLM produced no fix) — **this is the real measurement of the LLM engine's fix-quality boundary** (free-tier small model on actual repo-level code). Cross-file tasks (13/20 multi-source) have no positive signal before the engine-capability breakthrough (ON/OFF both 0/N); cross-file gain validation needs a stronger model + full-repo source context. See [experiments/results/experiment_report_20260925.md](../experiments/results/experiment_report_20260925.md) §7 and [docs/design/swe_bench_probe.md](design/swe_bench_probe.md) §0.

**Experiment setup** (historical data snapshot, not a current-version performance commitment):
- Dataset: Synthetic Dataset (50 tasks)
- Baseline: AITester (full system)
- Failures: 16/50 (32% failure rate)

---

## Failure Case Statistics

### Distribution by Error Type

| Error Type | Count | Share | Typical Scenario |
|---------|------|------|---------|
| UNKNOWN | 12 | 75% | JSON parse failure, empty response |
| RUNTIME | 3 | 19% | Unexpected exception type |
| ASSERTION | 1 | 6% | Test assertion mismatch |

### Distribution by Bug Pattern

| Bug Pattern | Failures | Success Rate |
|--------|--------|--------|
| palindrome_case_sensitive | 2 | 0% |
| off_by_one_right | 1 | 50% |
| clamp_range_error | 1 | 0% |
| divide_by_zero_missing | 1 | 50% |
| string_split_empty | 1 | 0% |
| Others | 10 | ~70% |

---

## Typical Failure Case Analysis

### Case 1: JSON Parse Failure (UNKNOWN)

**Task ID**: `synthetic__palindrome_case_sensitive_0002`

**Failure symptom**:
```
diagnosis: "JSON 解析失败: Could not find complete JSON: line 1 column 1 (char 0)"
```

**Root cause analysis**:
1. The LLM response format did not meet expectations (non-standard JSON)
2. The JSON extraction logic in GeneratorAgent was too strict
3. The system prompt may not have explicitly specified output format requirements

**Improvement suggestions**:
- Increase the robustness of JSON extraction, supporting multiple formats (markdown code blocks, pure JSON, mixed content)
- Add response format validation and automatic repair mechanisms
- Optimize the system prompt to clearly specify the output format spec

**Priority**: 🔴 High (affects the core flow)

---

### Case 2: Boundary Condition Handling Failure (UNKNOWN)

**Task ID**: `synthetic__off_by_one_right_0001`

**Failure symptom**: The Debugger failed to correctly identify the problem while repairing the binary search boundary error

**Root cause analysis**:
1. The error classifier categorized the problem as UNKNOWN instead of RUNTIME
2. The Debugger's repair strategy was not targeted enough for boundary errors
3. There was no dedicated handling rule for out-of-bounds index issues

**Improvement suggestions**:
- Extend the error classification patterns with IndexError-related matching rules
- Add dedicated repair strategy templates for boundary errors
- Enhance the Debugger's context understanding capability

**Priority**: 🟠 Medium (requires algorithm improvement)

---

### Case 3: Complex Logic Repair Failure (RUNTIME)

**Task ID**: `synthetic__clamp_range_error_0005`

**Failure symptom**: The clamp function did not raise an exception when min_val > max_val

**Root cause analysis**:
1. The test case expected specific behavior (raising ValueError)
2. The original code only handled the normal-range case
3. The Debugger failed to generate the correct boundary check code

**Improvement suggestions**:
- Add recognition of value-domain validation errors
- Add dedicated repair templates for range checks
- Enhance RAG retrieval to find similar range validation cases

**Priority**: 🟡 Low (can be mitigated by prompt engineering)

---

## Systemic Issues

### Issue 1: Unstable LLM Response Quality

**Impact scope**: 75% of failure cases

**Symptoms**:
- Some responses contain the reasoning process (reasoning_content)
- Some responses do not conform to the JSON spec
- Some responses are empty or truncated

**Solutions**:
1. Implement a response post-processing pipeline to standardize output format
2. Add a retry mechanism that automatically retries on format errors
3. Use a more reliable model (e.g., gpt-4o instead of the flash model)

---

### Issue 2: Insufficient Error Classifier Coverage

**Impact scope**: All failure cases

**Symptoms**:
- 12/16 failure cases were categorized as UNKNOWN
- The classifier relies on regex matching, making it hard to cover complex error patterns
- Lacks semantic-level error understanding

**Solutions**:
1. Expand the error pattern library to cover more exception types
2. Introduce lightweight semantic classification (using a small model)
3. Add human-labeled data for model fine-tuning

---

### Issue 3: Limited RAG Retrieval Effectiveness

**Impact scope**: Medium

**Symptoms**:
- Current RAG enablement rate is low (default false)
- Vector retrieval has limited matching precision for similar bugs
- ~~Lacks a knowledge base of failure cases~~ → Implemented in 5.3: `experiments/analyze_failures.py --knowledge-base/-k` outputs a structured failure case knowledge base (`failure_knowledge_base.json`, containing task_id / root_cause / reproducible_steps / suggested_fix), selected by error_category diversity first

**Solutions**:
1. ~~Enable RAG and build a failure case knowledge base~~ (5.3 has landed `failure_knowledge_base`: structured cases + reproducible steps + suggested fixes)
2. Optimize the embedding model to improve semantic matching precision
3. Implement hybrid retrieval (vector + keyword)

---

## Improvement Roadmap

### Short-term Improvements (1-2 weeks)

- [x] ~~Enhance JSON extraction logic to support multiple response formats~~ → Implemented: JSON extraction now supports multiple formats (markdown code blocks / raw JSON / mixed content; see `extract_json_object`)
- [x] ~~Expand the error classification pattern library~~ → Implemented: error classification expanded from 5 to 17 categories (e.g. `LLM_FORMAT_ERROR` / `INDEX_ERROR` / `PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` / `PATCH_SYNTAX_INVALID`; full 17-category enum in [docs/api_reference.md](api_reference.md) § error-category enum). The "12 categories" figure in this line was a 2026-09-14 in-batch count; see the snapshot warning at the top of this file.
- [ ] Add dedicated repair templates for key bug patterns
- [x] ~~Enable RAG and optimize the retrieval strategy~~ → Implemented: `--enable-rag` included in the main experiment (2.3 RAG ablation); retrieval metrics auto-summarized (Hit Rate / MRR / breakdown by retrieval type / RAG hit × failure-category cross-tab)

### Medium-term Improvements (1 month)

- [x] ~~Implement the response post-processing pipeline~~ → Implemented: retry + failover (APIManager circuit breaker cooldown + half-open probe + cost-aware routing)
- [x] ~~Add a mechanism for learning from failure cases and precipitating knowledge~~ → Implemented: 5.3 three major failure root-cause classes (`llm_capability` / `dependency` / `framework`) + structured failure case knowledge base (`failure_knowledge_base.json`)
- [ ] Optimize the system prompt templates
- [ ] Introduce a model selection strategy (automatically select a model based on task complexity)
- [x] ~~Data contamination risk mitigation (2.1)~~ → Implemented: SWE-bench golden-patch overlap detection (`experiments/contamination_check.py`, high ≥ 0.85 / medium ≥ 0.6) + SWE-rebench anti-contamination benchmark support (`load_dataset("swe_rebench")`); analysis reports auto-flag suspected-contamination tasks
- [x] ~~Task difficulty stratification analysis (2.2)~~ → Implemented: stratify by code_size / dependency_count / complexity_proxy (`experiments/difficulty_stratification.py`) to locate "in which difficulty interval system capability degrades"
- [x] ~~Convergence failure-mode attribution (1.2)~~ → Implemented: `analyze_results.py:_convergence_failure_modes` distinguishes "cannot pinpoint root cause" (repeated identical diagnosis, patch never written) vs "cannot produce an effective patch" (patch written but still failing / repeatedly rejected by safety guards) for tasks still failing at MAX_ITERATIONS
- [x] ~~Boundary case coverage detection (1.3)~~ → Implemented: `analyze_results.py:_boundary_case_coverage` performs an AST conservative check on generated_test for coverage of None / empty string / empty collection / 0 / -1 / >= / <= boundary conditions, reporting per-type hit counts and coverage rate
- [x] ~~Mutation score collection (1.3)~~ → Implemented: `analyze_results.py:_mutation_score_metrics` collects details[].mutation_score (produced by an external mutation tester); aggregates mean / high (>=0.7) / low (<0.4) distribution; skips the section when the field is absent
- [x] ~~Assertion-strength AST enhancement (1.3)~~ → Implemented: `_assertion_strength_proxy` adds an AST basis (ast.parse + ast.Assert node counting) on top of the original `assert` line-count metric, outputting `ast_avg_assertions` and `ast_parse_failed_tasks`
- [x] ~~Execution feedback trace collection (3.2, preparing data for RL fine-tuning)~~ → Implemented: `state.execution_trace` + `nodes._record_execution_trace` appends passed / coverage_delta / elapsed / reward_signals {correctness, efficiency, simplicity} on every executor execution (a pure observability layer, enabled by default); `run_benchmark.py` result rows carry the trace, and `analyze_results.py` auto-summaries and renders it

### Long-term Improvements (3 months)

- [ ] Develop a dedicated fine-tuned model
- [x] ~~Build the failure case knowledge base~~ → Implemented (5.3, see above)
- [ ] Implement a human-machine collaborative repair mechanism
- [ ] Extend to multi-language support (cross-language generalization: currently Python only; preliminary adaptation validation is possible on the Java ecosystem's Defects4J)

---

## Conclusion

The current 32% failure rate mainly comes from LLM response format issues and insufficient error classifier coverage. By enhancing JSON extraction robustness, expanding the error pattern library, and enabling RAG retrieval, the failure rate is expected to be reduced to below 15%. Next key improvement directions:

1. **Standardizing response formats**: handle the diversity of LLM outputs
2. **Refining error classification**: upgrade from rule matching to semantic understanding
3. **Knowledge base construction**: accumulate failure cases and repair experience
