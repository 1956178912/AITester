> **Language**: [中文版](api_reference.md) | English (this document)

# AITester API Reference Document

> This document describes the core classes and methods of AITester, for developer integration and extension.
> Last updated: 2026-10-06 (Round-12 review batch AK: experiments side adds `experiments/repair_ceiling_analysis.py` offline attribution [repair=0 funnel + detection=None dual-bound sensitivity; see the statistical-analysis companion entries]; zero src/ changes, default behavior unchanged; batch AA and earlier see "Previous" and CHANGELOG)
> Previous: 2026-10-06 (code-optimization batch AA: `AITESTER_PROFILE` expanded to four tiers, with the logic tier now injecting `DETECTION_FIRST_ENABLE` [completing the ADR-0015 detection-first preset gap]; `SyntheticDataset` gains `max_pattern_repeat` (per-pool template repeat cap) + `run_benchmark` gains the `--max-pattern-repeat` CLI flag (both opt-in, default None = legacy behavior, seed=42 reproducibility unchanged); README CI-matrix drift fix; default behavior unchanged)
>
> Earlier: 2026-10-05 (review batch R1-R18: R1a/R1b spec-compilation fixes + signature-aware binding / R1c spec oracle executed alongside LLM tests (`SPEC_ORACLE_EXEC_ENABLE` default off) / R4b rollback fail-closed (`PATCH_ROLLBACK_FAIL_CLOSED` default off) / R5 mutation detection rate (gated by `ENABLE_MUTATION_SCORING`) / R2 statistical report persisted (McNemar/BH-FDR/bootstrap CI/Cliff's delta/`--batches`) / R17 structured routing priority (`ROUTE_STRUCTURED_ENABLE` default off) / R16 rogue-agent monitoring (`ROGUE_MONITOR_ENABLE` default off) / R11 deterministic sampling (`run_benchmark(deterministic=True)`) / R15 `AITESTER_PROFILE` three-tier presets / `API_HEALTH_CHECKER_ENABLE` health-checker-thread switch / LLM cache directory default migrated to `~/.cache/aitester/llm`; default behavior unchanged, all new capabilities behind independent switches)
>
> Previous: 2026-09-29 (Review/optimization round: P0 runtime-probe defect fix — the historical `sys.settrace` exception-event collection does not propagate to the called frame when an exception is raised inside the function body, measured frames were permanently empty (the probe never actually worked since introduction); this round reads the `exc.__traceback__` frame chain at exception-raise time (zero trace overhead), synchronously fixed single-character-variable mis-filtering / line-number error (`f_lineno` → `tb_lineno`) / module-filter never matching / child-thread unhandled-exception leak; default behavior unchanged, when `RUNTIME_PROBE_ENABLE=false` zero difference)
>
> Previous: 2026-09-28 (Frontier-recommendation batch P0/P1/P2 gaps landed: G2 risk-tiered human approval loop (`src/graph/risk_approval.py`, `RISK_APPROVAL_ENABLE` default off) / G8 full-stack SWE-bench Pro re-test (`experiments/run_full_stack_swe_bench_pro.py` + `scripts/check_swe_bench_pro_ready.py` + `experiments/summarize_full_stack.py`) / G3 kernel-level sandbox (`src/agents/kernel_sandbox.py`, `KERNEL_SANDBOX_ENABLE` default off, macOS Seatbelt / Linux Landlock+bwrap, fail-closed) / G1 Tree-sitter precise AST backend (`src/tools/tree_sitter_backend.py`, optional dependency, transparent degradation when the dependency is missing) / G4 AgentTelemetry failure-detection benchmark (`src/observability/agent_telemetry.py`, `AGENT_TELEMETRY_ENABLE` default off, 10 built-in failure patterns) / G5 testless execution-irrelevant validation (`src/tools/testless_validation.py`, `TESTLESS_VALIDATION_ENABLE` default off, four independently toggleable layers) / G6 multi-agent debate convergence (`src/graph/expert_pool.py` new `debate_round()`, `EXPERT_POOL_DEBATE_ENABLE` default off) / G7 defect-report generation (`src/reports/generator.py` `ErrorReport` new `oracle_stats` + `with_oracle_stats()`) / doc-consistency P2 (`docs/dependency_exemptions.md` + `scripts/check_dependency_exemptions.py` CI gate + `scripts/check_docs_history_drift.py` warning-only drift detection); default behavior unchanged, all new capabilities behind independent switches)
>
> Prior: 2026-09-28 (Improvement-checklist full batch P0/P1/P2/P3: P0 baseline drift guard (`scripts/check_baseline_numbers.py`) + static-report auto-refresh (`scripts/generate_static_report.py`) + BASELINE CI validation (`scripts/check_baseline.py`); P1 branch-coverage gate/backfill (`scripts/check_branch_coverage.py`) + LLM-cache 0600 permissions & TTL cleanup (`llm_client.ensure_llm_cache_dir` / `secure_cache_file` / `cleanup_expired_cache_files`) + error-classifier confidence layering (`classify_with_confidence` / L2 protocol reservation); P2 failure-KB minimal closed loop (`src/agents/failure_kb.py`) + LLM output anomaly injection tests + optional `--smoke-llm` CI (`experiments/run_smoke_llm.py`) + multiprocess cache hit-rate coordination (`record_cache_hit` / `get_cache_hit_rate`) + bilingual H2 skeleton comparison + ADR index (`docs/adr/README.md`) + CI/CD integration examples (`docs/integration/`); P3 multi-language extension & long-file hierarchical summarization design docs; default behavior unchanged, all new capabilities behind independent switches)
>
> Previous: 2026-09-28 P0/P1 improvement batch (1.1 LLM output post-processing layer (`patch_postprocess.sanitize_patch` + P1 empty-shell detection / P2 import backfill / P3 contract alias backfill) / 2.1 error-classification → fix-strategy explicit mapping (`get_recommended_fix_strategy`) / 5.4 task-level token/cost budget hard cap (`COST_BUDGET_ENABLE` + `cost_budget`) / 5.1 semantic LLM cache (`SEMANTIC_CACHE_ENABLE` + `semantic_cache`) / 3.3 end-to-end smoke test script (`scripts/smoke_test.sh`) / 2.2 control-flow-graph static analysis (`control_flow.analyze_control_flow`, CFG path coverage injected into planner prompt) / 1.4 lightweight event bus (`event_bus`, observation-only decoupling layer); default behavior unchanged, all new features have independent switches)
>
> Prior: 2026-09-27 (tenth-batch full-project P1/P2 convergence round: non-numeric input crash guards / negative cache capacity cap / rag similarity bins KeyError / non-numeric reward_signals crash / cross-batch duplicate task_id silent drop / summary None crash / comment & docstring wording fixes / TimeoutExpired snapshot append / dotted module-name import fix / CLI flag conflict notice / total_test_count fallback / report None rendering / closure depth caliber / convergence safe normalization / regressed excludes new_categories / dead-write removal / NaN cause disambiguation + `cohens_d` docstring fix; full 1920 test cases / ruff 0 warnings / mypy 62 source files 0 errors / 94% coverage)

---

## Table of Contents

1. [Agent Modules](#agent-modules)
2. [Tool Modules](#tool-modules)
3. [Workflow Orchestration](#workflow-orchestration)
4. [Dataset Loading](#dataset-loading)
5. [Configuration Management](#configuration-management)

---

## Agent Modules

### PlannerAgent

The test planner, responsible for analyzing the target function and generating a structured test plan.

```python
from src.agents.planner import PlannerAgent

agent = PlannerAgent()
plan = agent.plan(
    target_code="def divide(a, b): return a / b",
    target_function="divide",
)
```

**Key methods:**

| Method | Parameters | Return Value | Description |
|------|------|--------|------|
| `plan()` | `target_code: str`, `target_function: str \| None = None` | `dict` | Generates a test plan containing `logic_analysis` and `test_cases`; when `target_function` is None, all functions are analyzed |

**Return format:**
```json
{
  "function_name": "divide",
  "description": "Division of two numbers",
  "logic_analysis": {
    "input_domain": "float, float",
    "output_domain": "float",
    "preconditions": ["b != 0"],
    "postconditions": ["result * b == a"],
    "edge_cases": ["raises ValueError when b == 0"]
  },
  "test_cases": [...]
}
```

---

### GeneratorAgent

The test code generator, producing runnable pytest code based on the test plan.

```python
from src.agents.generator import GeneratorAgent

agent = GeneratorAgent()
test_code = agent.generate(
    test_plan=plan,
    target_code="def divide(a, b): return a / b",
    module_name="calculator",
    rag_references=[...],  # optional, RAG retrieval results
)
```

**Key methods:**

| Method | Parameters | Return Value | Description |
|------|------|--------|------|
| `generate()` | `test_plan: dict`, `target_code: str`, `module_name: str = ""`, `rag_references: list[dict] \| None = None`, `focus_function: str \| None = None` | `str` | Generates pytest test code (performs AST smart truncation by focus_function when over budget; the last three parameters all default to None/"") |

**Validation methods:**

| Method | Parameters | Return Value | Description |
|------|------|--------|------|
| `_validate_parametrize()` | `code: str` | `bool` | Validates parametrize argument matching |
| `_fix_import_module()` | `code: str`, `expected_module: str` | `str` | Fixes an incorrect import module name |

---

### ExecutorAgent

The test executor, running pytest in a local environment, isolated sandbox, or Docker container and capturing results.

```python
from src.agents.executor import ExecutorAgent

agent = ExecutorAgent(timeout=30)  # Executes in the default local system environment
result = agent.execute(
    test_code="import pytest\nfrom calculator import divide\n\ndef test_divide():\n    assert divide(1, 2) == 0.5",
    target_file="examples/calculator.py",
    target_function="divide",
)

# venv sandbox isolated execution (P1: does not pollute the system environment; dependency conflicts do not affect each other)
sandbox_agent = ExecutorAgent(use_venv=True, auto_install_deps=True)

# 4.3 Docker isolated execution (runs pytest inside a container via the docker CLI; dependencies baked into the image)
docker_agent = ExecutorAgent(use_docker=True, docker_image="aitester:latest")
```

**Key methods:**

| Method | Parameters | Return Value | Description |
|------|------|--------|------|
| `execute()` | `test_code: str`, `target_file: str`, `target_function: str \| None` | `dict` | Executes the tests and returns pass/fail status, coverage, and failed cases; execution mode priority: Docker > venv sandbox > local |
| `_execute_docker()` | same as `execute()` | `dict` | 4.3 Docker isolated execution: passes the code under test into the container via `docker run` + volume mount; when docker is unavailable, returns a `docker_unavailable` diagnostic (does not silently fall back to local) |

**Return format:**
```json
{
  "passed": true,
  "failed_cases": [],
  "coverage": 85.5,
  "output": "...",
  "docker_image": "aitester:latest"
}
```

> Docker mode additionally carries a `docker_image` field (for experimental analysis to record execution-mode differences); on failure, `error_info.type` may be `docker_unavailable` / `docker_timeout`.

---

### DebuggerAgent

The debugging repairer, analyzing test failures and generating repair patches.

```python
from src.agents.debugger import DebuggerAgent

agent = DebuggerAgent()
result = agent.debug(
    target_code="def divide(a, b): return a - b",
    test_output="AssertionError: expected 0.5, got -1.0",
    failed_cases=[{"name": "test_divide", "error": "expected 0.5, got -1.0"}],
    rag_references=[...],  # optional, RAG repair cases
)
```

**Key methods:**

| Method | Parameters | Return Value | Description |
|------|------|--------|------|
| `debug()` | `target_code: str`, `test_output: str`, `failed_cases: list`, `rag_references: list[dict] \| None = None`, `focus_function: str \| None = None`, `target_module: str \| None = None` | `dict` | Analyzes the failure and generates a repair patch (the last three are all None by default: AST focused truncation for large files / distinguishing ASSERTION from LOGIC_ERROR) |

**Return format:**
```json
{
  "root_cause": "Division is a subtraction rather than division; line 3 should be return a / b",
  "error_category": "assertion",
  "fix_strategy": "Change the division operator",
  "patch": "```python\ndef divide(a, b): return a / b\n```"
}
```

---

### ErrorClassifier

The error type classifier, using rule matching to quickly determine the error category.

```python
from src.agents.error_classifier import ErrorClassifier, ErrorCategory

classifier = ErrorClassifier()
category = classifier.classify(test_output, failed_cases)
# When the module under test is provided, an assertion failure can distinguish ASSERTION (code bug) from LOGIC_ERROR (wrong test expected value)
category = classifier.classify(test_output, failed_cases, target_module="calculator")
```

**Error category enumeration (16 categories: P2 refinement + 1.2 residuals + 1.1 state refinement + 5.2 ongoing refinement + P0 4.1 sub-class split):**

| Value | Description | Handling Strategy |
|----|------|---------|
| `llm_format_error` | LLM response format anomaly (JSON parse failure / truncated response); one of the root causes of the former 75% UNKNOWN (1.2 residual refinement) | Re-request the LLM to generate a compliant response / strip markdown code blocks before parsing / reduce per-call output length |
| `llm_empty_response` | Empty LLM response (empty string / whitespace-only body), a precise sub-class of `LLM_FORMAT_ERROR` (P0 4.1 batch) — classified by `ErrorClassifier.classify_llm_response(raw_response)` right after the LLM response arrives and before JSON parsing; does not go through `classify()` text regex | Debugger automatically retries once with a stricter prompt; if it still fails, degrades to lenient JSON extraction; the raw response snippet is recorded to `failure_knowledge_base.json` |
| `llm_json_parse_failed` | Non-empty LLM response whose JSON extraction failed (markdown-wrapped / truncated / malformed), a precise sub-class of `LLM_FORMAT_ERROR` (P0 4.1 batch); same classification criteria as above | Record the raw response snippet + retry once with reduced per-call output length; if it still fails, degrade to lenient extraction |
| `import_error` | Module import failure (ModuleNotFoundError/ImportError), usually a missing third-party dependency or an incorrect module path | Install the missing dependency / fix the import statement (combined with executor `auto_install_deps` for automatic dependency installation) |
| `syntax` | Syntax/compile error (SyntaxError, IndentationError) | Regenerate the complete file |
| `type_error` | Type mismatch (TypeError) | Check parameter and return types |
| `index_error` | Out-of-bounds index (IndexError / index out of range / subscript out of range); formerly fell into RUNTIME/UNKNOWN so the Debugger could not repair it in a targeted way (1.2 residual refinement) | Add boundary checks (check for empty containers before access); do not silently swallow out-of-bounds errors with try/except |
| `assertion` | Assertion failure and the failure stack touches the code under test | Determine it is a code logic error |
| `logic_error` | Assertion failure but the failure stack does not touch the module under test; suspected wrong test expected value | Fix the test case assertions (rather than blindly changing the code under test) |
| `runtime` | Other runtime exceptions (division by zero, NameError, etc.) | Analyze the exception stack to locate the bug |
| `timeout` | Execution timeout | Check for infinite loops |
| `unknown` | Unrecognizable error | General analysis (LLM fallback) |
| `patch_validation_failed` | Patch rejected by the PatchApplier safety guard (empty/too short/no function definition/illegal path, patch_applied=False in repair_history); 1.1 state refinement — determined by `refine_failure_category()` based on repair_history signals, not through `classify()` text regex | Regenerate the complete repair patch (first add function definitions and minimum length before going through validation); distinguish "patch not applied" from "patch applied but still failed" |
| `rag_retrieval_empty` | RAG enabled but all retrieval hits within the task are 0 (rag_stats is non-empty and all results==0); identifies RAG-failure scenarios (1.1 state refinement) — determined by `refine_failure_category()` based on rag_stats signals, not through `classify()` text regex | Check whether the RAG retrieval library has been populated / lower top_k / switch to hybrid retrieval; this category's hit ratio is always 0, so it can serve as a RAG self-check metric |

| `execution_trace_missing` | Task failed but `execution_trace` is empty (executor abnormal path: executor node did not write the trace, or it was truncated by an upstream crash); identifies "execution trace lost" (5.2 ongoing refinement) — determined by `refine_failure_category()` based on execution_trace signals, not through `classify()` text regex | Investigate the execution chain (venv/sandbox/timeout config) and retry; fix the code conservatively per the normal strategy |
| `multi_candidate_all_rejected` | Multi-candidate patch strategy failed: all N candidates rejected by static screening (`ENABLE_MULTI_CANDIDATE_PATCH=true` but none passed `static_validate_patch`) (5.2 ongoing refinement) — determined by `refine_failure_category()` based on multi_candidate_stats signals, not through `classify()` text regex | Fall back to the single-patch flow and reduce candidate-perspective perturbation |
| `patch_syntax_invalid` | Patch post-processing resampling exhausted: with `PATCH_RESAMPLE_ENABLE=true`, the patch is still syntactically broken after `PATCH_RESAMPLE_MAX` resamples (2.2 batch) — determined by `refine_failure_category()` / `refine_final_error_category()` based on `patch_resample_stats` signals, not through `classify()` text regex | Check LLM output quality (whether the prompt constrained valid Python syntax); increase resample count or reduce per-call output length |

**Improvement checklist P1 batch (2026-09-28): confidence-layered classification (L1 rule layer + L2 protocol reservation + low-confidence fallback)**

```python
from src.agents.error_classifier import (
    ClassificationResult,
    ErrorClassifier,
    ProbabilisticClassifier,
    classify_with_confidence,
)

# Module-level convenience function (equivalent to ErrorClassifier().classify_with_confidence)
result: ClassificationResult = classify_with_confidence(
    test_output,
    failed_cases=failed_cases,
    target_module="calculator",
)
# result.category / result.confidence / result.confidence_basis /
# result.fallback_used / result.fallback_category
```

- **L1 rule layer** (`_classify_confidence`, zero LLM cost, deterministic & reproducible): concrete-feature hit (exception keyword / missing module name / line-number location) → confidence 0.9; weak hit (only generic `file.py:line:col` / `E` prefix format, no concrete exception keyword, e.g. `SYNTAX` weak hit / `IMPORT_ERROR` without extractable module name) → confidence 0.5; miss (`UNKNOWN`) → confidence 0.2;
- **Low-confidence fallback strategy** (`enable_fallback=True`, default on): samples with confidence ≤ 0.5 trigger fallback — category converges to the fallback category (`UNKNOWN` / weak `SYNTAX` → `generic_analysis` instead of a hard "rewrite whole file" route), `fallback_used=True` / `fallback_category=UNKNOWN`; with `enable_fallback=False` the classification is byte-equivalent to the historical 17-category criterion (`_classify_combined` via the new kernel, fallback does not fire);
- **L2 probabilistic / ML layer protocol reservation** (`ProbabilisticClassifier`; currently `_default_probabilistic_classifier` is always `None`): low-confidence samples can be refined via the `classifier` parameter (an L2 classifier's `predict(combined, target_module) → (category, confidence)`); when L2 confidence > 0.5 it overrides the L1 verdict; landing L2 requires a separate ADR + regression guard (see [ADR-0002](adr/0002-error-classifier-rules.md) "Known limitations & evolution directions").

Classification priority (10 categories in `classify()` text regex): `LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN`, all based on regex rule matching, no LLM token consumption. LLM_FORMAT_ERROR is placed first (JSON parse failure text rarely contains IndexError, but IndexError text may contain assert; reversing the order would misclassify). The latter 5 categories (`PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` / `EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED` / `PATCH_SYNTAX_INVALID`) are state-refinement categories that do not go through `classify()` text regex; instead, the pure function `refine_failure_category()` determines them at task completion based on `repair_history` (patch rejected) / `rag_stats` (retrieval all empty) / `execution_trace` (trace missing) / `multi_candidate_stats` (all candidates rejected) / `patch_resample_stats` (resampling exhausted) signals — decision priority `patch_rejected > rag_empty > trace_missing > multi_rejected > patch_syntax_invalid`; successful tasks are returned as-is. The benchmark and CLI exits use the same criteria. The two P0 4.1 sub-classes (`LLM_EMPTY_RESPONSE` / `LLM_JSON_PARSE_FAILED`) are classified by `classify_llm_response()` directly on the raw LLM response (empty → `LLM_EMPTY_RESPONSE`; non-empty but JSON extraction failed → `LLM_JSON_PARSE_FAILED`), decided after the response arrives and before JSON parsing; on a hit the Debugger retries once with a stricter prompt without going through `classify()` text regex.

---

## Tool Modules

**Improvement checklist P1/P2 batch (2026-09-28): LLM cache security hardening + multiprocess cache coordination + failure-KB minimal closed loop**

```python
from src.agents.llm_client import (
    cleanup_expired_cache_files,
    ensure_llm_cache_dir,
    get_cache_hit_rate,
    record_cache_hit,
    reset_cache_hit_stats,
    secure_cache_file,
)

# Hit-rate observation (pure read, does not change cache correctness; thread-safe, --parallel concurrent calls)
rate = get_cache_hit_rate()  # This process's hit rate (0.0-1.0); None when no records
record_cache_hit(True)  # Hit/miss instrumentation (auto-called by _call_llm_with_cache)
reset_cache_hit_stats()  # Reset counters (batch boundary / test isolation)

# Cache security (18. permission convergence + TTL expiry cleanup)
ensure_llm_cache_dir()  # New dir 0o700; existing dir untouched; returns path
secure_cache_file(tmp_path)  # os.chmod(tmp_path, 0o600); OSError silenced
removed = cleanup_expired_cache_files()  # mtime-based delete of *.json older than TTL; returns count
# TTL: AITESTER_LLM_CACHE_TTL_DAYS (default 7 days; 0/negative = cleanup disabled)
```

- When hit rate < 0.5 (multiprocess `--parallel` high-frequency repeated tasks): each
  worker's first 30s negative-cache window triggers repeated LLM calls;
  recommend "main-process cache prewarm + shared directory" (first run
  high-frequency tasks in single-process sequential mode to prewarm the
  LLM file-cache directory (default `~/.cache/aitester/llm` since
  2026-10-05), then run the batch in multiprocess mode) or switch to the
  multithread mode (`BENCHMARK_PARALLELISM=N`, L1 process-level shared dict
  visible cross-thread); see [performance_guide.md](performance_guide.md)
  "3.5 Concurrency & multiprocess cache semantics".
- `get_workflow_stats()["llm_cache"]["hit_rate"]` automatically attaches this
  process's hit rate (the key is omitted when there are no LLM call records,
  keeping the existing stats snapshot byte-equivalent).

**4. Failure knowledge base minimal closed loop (landing point B online consumption + decay, 2026-09-28 improvement batch)**

```python
from src.agents.failure_kb import (
    kb_debugger_snippet,
    load_knowledge_base,
    rank_knowledge_entries,
)

# Offline accumulation: python experiments/analyze_failures.py -k failure_knowledge_base.json
# Online consumption (FAILURE_KB_ENABLE=true auto-injected by _debugger_node; default off)
snippet = kb_debugger_snippet("syntax")  # Same-category case snippets matching error_category="syntax"
entries = load_knowledge_base()  # Load KB (missing/corrupt/non-list → [])
ranked = rank_knowledge_entries(entries, "syntax")  # Frequency × time-decay ranked top-k
# Decay: FAILURE_KB_DECAY_DAYS (default 30 days); older entry last_seen → lower weight
# (0.5 ** (age_days / half_life_days); missing last_seen / half-life ≤0 → weight 1.0)
```

- `kb_prompt_snippet_applied` (state observation key): set to `True` when
  `_debugger_node` injects the KB snippet; always `None` when
  `FAILURE_KB_ENABLE` is off (default; historical criterion unchanged),
  for `analyze_results.py` to tally "which tasks went through the KB-enhanced
  path" (effect verification ⑤).

### CodeAnalyzer

An AST code analysis tool providing precise code replacement capabilities.

```python
from src.tools.code_analyzer import analyze_complexity, replace_function_code

# Compute cyclomatic complexity
complexity = analyze_complexity(code_string)

# Replace a function implementation
new_code = replace_function_code(
    original_code,
    function_name,
    new_body,
)
```

**Key functions:**

| Function | Parameters | Return Value | Description |
|------|------|--------|------|
| `analyze_complexity()` | `code: str` | `int` | Computes cyclomatic complexity |
| `replace_function_code()` | `original_code`, `function_name`, `new_body` | `str` | AST-precise replacement of a function body |

---

### PatchApplier

A patch application tool supporting full-file and single-function modes.

```python
from src.tools.patch_applier import apply_patch_to_code

# Apply a full-file patch
fixed_code = apply_patch_to_code(
    original_code=buggy_code,
    patch="```python\ndef divide(a, b): return a / b\n```",
    mode="full_file",
)

# Single-function mode (recommended)
fixed_code = apply_patch_to_code(
    original_code=buggy_code,
    patch="return a / b",
    mode="function",
    function_name="divide",
)
```

**Key functions:**

| Function | Parameters | Return Value | Description |
|------|------|--------|------|
| `apply_patch_to_code()` | `original_code`, `patch`, `mode`, `function_name` | `str` | Apply a patch to code |
| `apply_multi_function_patch()` | `code: str`, `patches: list[dict]` | `tuple[str, bool]` | Repair multiple functions simultaneously: each patch entry is `{"function_name": str, "patch": str}`; applied in descending order of function start line (to avoid line-number offset). 0.2 performance optimization: the sort key reuses the pre-split lines (O(n+m); previously each patch split the code itself, O(n·m)) |
| `safe_apply_patch()` | `code`, `patch` | `tuple[str, bool]` | Apply the patch, then run a syntax check; on failure automatically roll back to the original code |

---

### CodeContext

An AST-based smart code extraction tool (P0: LLM context optimization for large-file scenarios).

```python
from src.tools.code_context import extract_focused_code

focused = extract_focused_code(
    source_code,
    focus_function="divide",  # Keep imports + this function and its directly dependent helper functions
    max_chars=3000,
)
```

**Key functions:**

| Function | Parameters | Return Value | Description |
|------|------|--------|------|
| `extract_focused_code()` | `code`, `focus_function`, `max_chars` | `str` | AST extraction: keeps imports + the focus function and direct dependencies; returns the original/fallback result when unparseable or still over budget |

---

### Dependency

Third-party dependency detection and cached venv management (P1: execution isolation).

```python
from src.tools.dependency import find_missing_modules, venv_cache_dir, create_venv, install_packages

missing = find_missing_modules("import pandas\ndef f(): ...")
# → {"pandas"} (the standard library and non-import statements are filtered out)

venv_dir = venv_cache_dir(
    ["pandas"]
)  # disk cache directory keyed by dependency combo + current Python version (4.4 multi-version)
venv_dir_310 = venv_cache_dir(["pandas"], python_version="3.10")  # explicit Python version (py3.10 prefix isolates)
venv_python = create_venv(venv_dir, timeout=120)
install_packages(venv_python, ["pandas"], timeout=120)
```

**Key functions:**

| Function | Parameters | Return Value | Description |
|------|------|--------|------|
| `extract_imported_modules()` | `code: str` | `set[str]` | Extracts the top-level module names imported by the code |
| `is_standard_library()` | `module_name: str` | `bool` | Determines whether it is a standard library module |
| `find_missing_modules()` | `code: str` | `set[str]` | Third-party modules imported by the code but unavailable in the current environment |
| `suggest_package_names()` | `module_names: set[str]` | `list[str]` | Module name → suggested pip package name (handles underscore/alias mapping) |
| `venv_cache_dir()` | `required_packages: list[str]`, `python_version: str \| None = None` | `str` | 4.4 multi-version cache: compute the cache directory by dependency combo + Python version (when `python_version` is None, uses the first two digits of `sys.version_info`; different versions are isolated in separate directories to avoid cross-reuse) |
| `create_venv()` | `venv_dir: str`, `timeout: int` | `str` | Creates a venv and returns the python interpreter path (reuses disk cache) |
| `install_packages()` | `venv_python`, `packages`, `timeout` | `bool` | Runs pip install inside the venv (returns False on failure, does not raise) |
| `get_venv_cache_stats()` | none | `dict` | 4.4 Dependency cache hit-rate statistics: accumulates in-process hit/create events + on-disk JSON cross-process aggregation, returns `hit_rate = hits/(hits+creates)` |
| `list_venv_cache()` | none | `list[dict]` | 4.4 Lists all cached venvs in the cache directory (name / path / size_mb / created_at) |
| `clear_venv_cache()` | `max_age_days: int \| None`, `max_size_mb: int \| None` | `dict` | 4.4 Clears the cache filtered by age / size; when both are None, clears everything |

---

### Data Contamination Detection (2.1)

`experiments/contamination_check.py`: mitigating SWE-bench data contamination risk — compares the token-level Jaccard similarity between the system's generated patch and the dataset's official golden patch, flagging highly overlapping tasks (suspected training-data contamination / verbatim reproduction).

```python
from experiments.contamination_check import (
    detect_contamination,
    patch_overlap_score,
    render_contamination_section,
)

# Overlap score for a single patch pair ([0.0, 1.0]; empty patches return 0.0)
score = patch_overlap_score(generated_patch, golden_patch)

# Batch-scan benchmark result details (details[].patch + a golden_patches mapping, or task_metadata.golden_patch)
report = detect_contamination(details, golden_patches={"task_1": "..."})
# → {"checked": n, "high": [...], "medium": [...], "scores": {...}, "contaminated_tasks": [...]}

# Markdown section rendering (returns an empty list when checked=0; the caller skips it)
lines = render_contamination_section(report, baseline="aitester")
```

**Criteria:** high ≥ 0.85 (suspected verbatim reproduction) / medium ≥ 0.6 (manual review recommended); tokens are lowercased identifier/numeric splits counting only diff modification lines (diff metadata is discarded). Supporting pieces: `dataset_loader` stores the official patch into `task.metadata["golden_patch"]` (not exposed to the LLM), `run_benchmark` result rows carry a `patch` field, and `load_dataset` supports the `swe_rebench` alias (an anti-contamination benchmark).

---

### Task Difficulty Stratification (2.2)

`experiments/difficulty_stratification.py`: stratifies tasks by code complexity / dependency count / file size to locate "in which difficulty interval does system capability degrade".

```python
from experiments.difficulty_stratification import stratify_by_dimension, render_stratification_section

# Stratify by the given dimension (code_size / dependency_count / complexity_proxy)
strat = stratify_by_dimension(details, "code_size", instance_codes={...}, test_codes={...})
# → {"small": {"tasks": n, "passed": n, "success_rate": f}, "medium": {...}, "large": {...}}

# Markdown section rendering (returns an empty list when there are no details)
lines = render_stratification_section(details, baseline="aitester")
```

**Stratification boundaries (conservative, interpretable criteria):** code_size small <2KB / medium 2–10KB / large >10KB; dependency_count low 0 / medium 1–2 / high ≥3; complexity_proxy easy 0 / medium 1 / hard ≥2 (`iterations × (1 - passed)`; successful tasks are always 0).

---

### Convergence Failure-Mode Attribution (1.2)

`experiments/analyze_results.py:_convergence_failure_modes(details)`: for tasks still failing at MAX_ITERATIONS (iterations>=3), distinguishes two failure modes:
- **Cannot pinpoint root cause**: diagnosis text repeatedly identical (the last two rounds of diagnosis are the same) and the patch was never successfully written — the Debugger keeps emitting the same conclusion without actually identifying the problem
- **Cannot produce an effective patch**: the patch was successfully written (patch_applied=True) but the test still fails, or it was repeatedly rejected by the safety guards (patch_applied=False with a patch record present)

```python
from experiments.analyze_results import _convergence_failure_modes

report = _convergence_failure_modes(details)
# → {"total_converged_failed": n, "root_cause_stuck": n, "patch_generation_failed": n,
#    "tasks": [...], "available": bool}
# available=False when there are no failures that reached MAX_ITERATIONS; the rendering layer skips the section
```

**Conservative heuristics, LLM-free**: consumes only the existing details[].iterations / diagnosis / repair_history / patch fields.

---

### Boundary Case Coverage (1.3)

`experiments/analyze_results.py:_boundary_case_coverage(details)`: an AST conservative check of details[].generated_test for coverage of None / empty string / empty collection / 0 / -1 / >= / <= boundary conditions.

```python
from experiments.analyze_results import _boundary_case_coverage

report = _boundary_case_coverage(details)
# → {"available": bool, "observed_tasks": n, "boundary_types": {"none": n, ...},
#    "tasks_covering_any_boundary": n, "coverage_rate": f}
# available=False when legacy JSON has no generated_test; the rendering layer skips the section
```

---

### Mutation Score (1.3)

`experiments/analyze_results.py:_mutation_score_metrics(details)`: collects details[].mutation_score (produced by an external mutation tester such as mutmut, 0.0–1.0), aggregating the mean / high (>=0.7) / low (<0.4) distribution. available=False when the field is absent; the section is skipped without blocking the main flow.

```python
from experiments.analyze_results import _mutation_score_metrics

report = _mutation_score_metrics(details)
# → {"available": bool, "observed_tasks": n, "avg_mutation_score": f,
#    "high_score_tasks": n, "low_score_tasks": n}
```

---

### Mutation Detection Rate (R5, 2026-10-05 batch)

`experiments/mutation_detection.py`: the SWE-Mutation 2026-caliber objective metric of test validity — the generated tests must be fully green on the **gold fixed code** (first proving the tests themselves are valid), and the metric is the share of the code's AST mutants they turn red. Complementary to the 1.3 mutation score: the latter mutates the **buggy code** (generator-perspective fault coverage), while this metric mutates the **gold fixed code** (an independent verdict on test validity). Wired into `run_benchmark.py` (sharing the `ENABLE_MUTATION_SCORING` gate and hook point with the 1.2 mutation score); result rows gain three fields.

```python
from experiments.mutation_detection import mutation_detection_rate

result = mutation_detection_rate(
    fixed_code=gold_fixed_code,
    test_code=generated_test,
    module_name="calculator",
    n_mutants=20,
)
# → {"rate": 0.65, "mutants_killed": 13, "mutants_total": 20, "skipped": False, ...}
# Missing gold-fixed material / tests not green on fixed / no mutants generatable
# → rate=None + skipped=True (conservatively no false 0; the stats layer skips
#   as unmeasurable)
```

| Result field | Type | Description |
|---------|------|------|
| `mutation_detection_rate` | `float \| None` | Mutation detection rate (None when skip conditions hit) |
| `mutants_killed` | `int` | Number of mutants detected (0 placeholder when skipped, isomorphic to the function return) |
| `mutants_total` | `int` | Total number of mutants evaluated (0 placeholder when skipped) |

**Conservative criteria (pure subprocess, zero LLM)**: a mutant counts as detected only when pytest rc != 0 and it is NOT a collection error (rc >= 2 / "no tests were run" etc. — the suite never ran — do not count); a single-mutant timeout / IO exception counts as "survived" (does not inflate the rate); when there are more mutants than `n_mutants`, random sampling by `seed` (reproducible across runs).

---

### Statistical Test Report (R2, 2026-10-05 batch)

`experiments/statistical_analysis.py`: McNemar paired test (task_id-paired 2×2 discordant pairs, chi2 with continuity correction) / independent two-group binomial test / BH-FDR multiple-comparison correction results are persisted to `statistical_report.md` (previously console-only); two new nonparametric statistics functions and a batch-whitelist CLI:

```python
from experiments.statistical_analysis import bootstrap_paired_diff_ci, cliffs_delta

# Percentile-method bootstrap 95% CI of the paired-difference mean (default
# 10000 resamples, seed=42; pure-Python random.Random(seed) with a fixed seed —
# byte-reproducible across calls with the same parameters, auditable)
mean_diff, ci_low, ci_high, n_pairs = bootstrap_paired_diff_ci(aitester_results, baseline_results)

# Sign-version Cliff's delta for paired differences (δ = (n⁺ − n⁻) / n_pairs;
# more robust than Cohen's d for binary paired data — d degrades to ±inf on
# zero-variance differences); output alongside d
delta, n_pairs = cliffs_delta(aitester_results, baseline_results)
# Effect-size grading (interpret_cliffs_delta, Romano et al. 2006 thresholds):
# |δ| < 0.147 negligible / < 0.33 small / < 0.474 medium / ≥ 0.474 large
```

```bash
# --batches batch whitelist: include only the specified result files
# (comma-separated paths relative to --results-dir; when omitted, the
# historical "recursive glob of the whole directory" behavior is unchanged)
python experiments/statistical_analysis.py \
    --results-dir experiments/results \
    --batches main_batch/benchmark_synthetic_20261001_112528.json,main_batch/benchmark_synthetic_20261001_112801.json
```

- The report header gains a **"Data sources" audit section**: the batch files actually included and their entry counts, so readers can verify the sample behind each p-value;
- Companion: `experiments/analyze_results.py` aggregates the four M1 metrics (`detection_rate` / `repair_rate` / `false_fix_rate` / `test_error_rate`; None values are excluded from the denominator; old JSON without the field is skipped automatically).
- Companion (AK1, 2026-10-06): `experiments/repair_ceiling_analysis.py` — pure-offline attribution over R-P0-2 artifacts: the repair=0 funnel (repair loop → patch produced → patch_plausible → patch_correct, with patch_evidence_level / stop_reason / error_category distributions and fl_at_k / mutation observation coverage) plus dual-bound sensitivity for the 21 `detection=None` rows (None→0/1 fill then McNemar recomputation). Same parameter caliber as the pooled report (`--batches` whitelist + `--pool-seeds`); emits `experiments/results/main_batch/repair_ceiling_report.md`.

---

### Assertion-Strength AST Enhancement (1.3)

`experiments/analyze_results.py:_assertion_strength_proxy(details)`: in addition to the original `assert` line-count metric, adds an AST basis (ast.parse + ast.Assert node counting), outputting `ast_avg_assertions` and `ast_parse_failed_tasks` (a list of parse-failure tasks, cross-referenceable with smell detection). When legacy JSON has no generated_test, the whole proxy is available=False.

```python
from experiments.analyze_results import _assertion_strength_proxy

report = _assertion_strength_proxy(details)
# → {"available": bool, "observed_tasks": n, "avg_assertions_per_task": f,
#    "min_assertions": n, "max_assertions": n, "tasks_with_zero_assertions": n,
#    "ast_avg_assertions": f | None, "ast_parse_failed_tasks": [...]}
```

---

### Execution Feedback Trace (3.2)

`state.execution_trace` (list, default `[]`) + `nodes._record_execution_trace`: appends one record to `state["execution_trace"]` on every executor execution; a pure observability layer, enabled by default, does not affect repair routing.

```python
from src.graph.state import AITesterState, create_initial_state
from src.graph.nodes import _record_execution_trace

state = create_initial_state(
    task_uuid="t1", target_file="/p.py", target_code="def f(): pass", target_function=None, max_iterations=3
)
# After workflow execution, state["execution_trace"] looks like:
[
    {
        "iteration": 0,
        "passed": False,
        "coverage": 40.0,
        "coverage_delta": None,  # no previous round
        "elapsed_seconds": 2.0,
        "reward_signals": {  # conservative linear normalization, recorded only, never used for routing
            "correctness": 0.0,  # 1.0 if passed else 0.0
            "efficiency": 0.93,  # 1 - elapsed / EXECUTION_TIMEOUT
            "simplicity": 0.97,  # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
        },
    },
    {
        "iteration": 1,
        "passed": True,
        "coverage": 85.0,
        "coverage_delta": 45.0,  # 85 - 40
        "elapsed_seconds": 3.0,
        "reward_signals": {"correctness": 1.0, "efficiency": 0.9, "simplicity": 0.95},
    },
]
```

`run_benchmark.py` result rows carry `execution_trace` (failure branch falls back to `None` to keep key-set parity); `analyze_results.py` adds an "Execution Feedback Trace Summary (3.2)" section: observed task count / total executions / average rounds / first-round pass rate / last-round correctness & efficiency means / first-vs-last coverage trend (delta). Legacy JSON without the field skips the section.

**Purpose**: preparing data for future execution-feedback-driven fine-tuning (BoostAPR-style methods) — every benchmark automatically writes "pass/fail, coverage change, elapsed time, multi-dimensional reward signals" into the result JSON; no extra trace-collection script needed.

---

### Structured Tracing Layer (4.1)

`src/observability/trace.py`: an append-only JSONL recorder capturing "task-level" events (node input/output summaries, token consumption, wall-clock latency, routing decisions) for each workflow task, consumed directly by experimental analysis. Disabled by default (a complete no-op with zero performance cost when `AITESTER_TRACE_DIR` is unset); enable it explicitly.

```python
from src.observability.trace import TraceSession, trace_enabled

if trace_enabled():
    session = TraceSession(task_id, trace_dir, config_flags)
    session.record_node("planner", output_summary=..., decision="plan_complete")
    session.record_task_end(passed=True)
```

**Key properties:** thread-safe (under `--parallel`, multiple worker threads append to the same JSONL; each single append+flush happens inside the lock); all written text is uniformly passed through `mask_sensitive_info` (the same source as log redaction); a write-to-disk failure never blocks the main flow (it only logs a warning).

**In-memory snapshot buffer (enabled by default, never written to disk):** even when `AITESTER_TRACE_DIR` is unset (file tracing fully no-op), `TraceSession` still accumulates a "minimal node snapshot" (node decisions / tokens / latency) for each task into a process-level ring buffer (capacity 64; disable entirely with `TRACE_MEMORY_BUFFER_ENABLE=false`), so the CLI `--dump-trace-on-failure` flag can write the most recent task snapshots to a temporary JSONL (`./tmp_trace/<ts>_failed_trace.jsonl`) on task failure for diagnostics; when no snapshot is available or the write fails it silently skips (a diagnostics exit, never blocking the main flow). Default behavior is unchanged (no disk I/O, zero cost).

---

### TokenUsage

Thread-local LLM token usage statistics (P0: efficiency metrics).

```python
from src.graph import token_usage

token_usage.record_usage(1200, 300, model="gpt-4o")
usage = token_usage.get_usage()
print(usage.total_tokens)  # 1500
usage.reset()  # Single-thread reset (called before a baseline run)
```

**Key functions:**

| Function | Parameters | Return Value | Description |
|------|------|--------|------|
| `record_usage()` | `input_tokens`, `output_tokens`, `model` | `None` | Records into the current thread's statistics (bucketed by model) |
| `get_usage()` | - | `TokenUsage` | The current thread's cumulative totals (including total_tokens / by_model, serializable via `as_dict()`) |
| `reset()` | - | `TokenUsage` | Resets the current thread's statistics and returns the pre-reset snapshot |

---

## Workflow Orchestration

### WorkflowGraph

A LangGraph workflow graph coordinating the multi-agent collaboration process.

```python
from src.graph.workflow import build_workflow
from src.graph.state import AITesterState

# Build and compile the workflow graph. planner / debugger can explicitly override config switches
# (ablation baselines such as plain_llm can pass False); None (default) reads config.ENABLE_PLANNER / ENABLE_DEBUGGER
graph = build_workflow()
# Ablation example: plain LLM baseline (no planning, no repair loop)
# graph = build_workflow(planner=False, debugger=False)

# Run the workflow: invoke takes an initial state dict and returns the final state
state: AITesterState = {
    "target_code": "def divide(a, b): return a - b",
    "target_file": "/path/to/calculator.py",
    "target_function": "divide",
    "max_iterations": 3,
}
final_state = graph.invoke(state)
```

**Workflow nodes** (node IDs are registered via `add_node` in `src/graph/workflow.py`; node function implementations are in `src/graph/nodes.py`, all prefixed with an underscore as `_<id>_node`):

| Node ID | Function | Calls LLM |
|---------|------|-------------|
| `planner` | Generates the test plan | ✅ |
| `generator` | Generates test code | ✅ |
| `executor` | Executes the tests | ❌ |
| `debugger` | Layered diagnosis + generates repair patches (error classification is called inline within the node via `error_classifier.classify`; there is no standalone classification node) | ✅ |
| `patch_applier` | Applies patches (single-file `safe_apply_patch`; when `CROSS_FILE_ENABLE=true`, takes the cross-file multi-file branch) | ❌ |
| `cross_file_analyzer` | 3.5 Cross-file dependency analysis (registered only when `CROSS_FILE_ENABLE=true`, inserted between `executor → debugger`) | ❌ |

**Conditional routing:**
- `_should_debug()`: decides whether to continue into the debug loop based on test results and iteration count (loop termination logic)
- Maximum iteration count limit: prevents infinite loops

**RAG degradation guard (new in 0.2)**: `rag_guarded` in `src/graph/rag.py` unifies the 4 structurally identical "ENABLE_RAG precondition + retriever singleton fetch + try/except degradation" blocks in `nodes.py` (generator retrieval / executor ingestion / debugger retrieval / debugger ingestion). It uses a **dependency-injection design** (`enabled` / `module_available` / `retriever_cls` / `get_retriever` passed as parameters rather than read from module globals), keeping the historical patch paths (`src.graph.nodes.ENABLE_RAG` / `get_rag_retriever`, etc.) valid. Future RAG degradation-policy changes (failure counting, circuit breakers, etc.) only touch `rag_guarded` in one place; the 4 call sites stay unchanged.

---

## Dataset Loading

### DatasetLoader

The dataset loader base class.

```python
from src.datasets import load_dataset

# Load the built-in example dataset
dataset = load_dataset("examples")

# Load a synthetic dataset
from src.datasets import SyntheticDataset

dataset = SyntheticDataset(task_count=50, seed=42)
# AA (2026-10-06): per-pool template repeat cap (opt-in, default None =
# legacy behavior; with >=1, a (difficulty, pattern) pair appears at most N
# times, preventing distribution collapse — see DATA_CARD §2)
dataset = SyntheticDataset(task_count=50, seed=42, max_pattern_repeat=2)

# Load the SWE-bench dataset
from src.datasets import SWEBenchDataset

dataset = SWEBenchDataset(subset="lite")

# 2.1 Load the SWE-rebench anti-contamination benchmark (field-compatible with SWE-bench; point data_dir at the rebench data directory)
dataset = load_dataset("swe_rebench", data_dir="/path/to/rebench_data")

# 2.1 Load the SWE-bench Pro anti-contamination benchmark (strong copyleft design, field-compatible; point data_dir at the Pro data directory)
dataset = load_dataset("swe_bench_pro", data_dir="/path/to/pro_data")
```

**Supported dataset names** (the `dataset_map` in `load_dataset`, including aliases):
`swe_bench` / `swebench` / `swe_rebench` / `swebench_rebench` / `swe_bench_pro` / `swebench_pro` / `defects4j_python` / `d4j_py` / `in_memory` / `examples` / `synthetic` / `synth`. Names not in the list degrade to `InMemoryDataset` (graceful degradation).

**Dataset interface:**

```python
# Iterate over tasks
for task in dataset:
    target_code = task["target_code"]
    function_name = task["function_name"]
    # ...

# Look up by task_id (O(1) table lookup; 2026-09-26 full-review round: the
# former O(n) linear scan was O(n^2) over SWE-bench full (2294 tasks) x the
# benchmark loop. Now an O(1) dict index with lazy invalidation via a
# length marker; add_task appends trigger an index rebuild on the next
# get_task_by_id call)
task = dataset.get_task_by_id("sqlfluff__sqlfluff-1234")
```

**Base-class capabilities (hardened in the 2026-09-26 full-review round):**

| Method | Description |
|------|------|
| `add_task(task)` | Append a task to the dataset (now on the base class; the former `InMemoryDataset` override was merged in). The length change in `_tasks` triggers a lazy index rebuild on the next `get_task_by_id` (O(n) once, O(1) thereafter) |
| `get_task_by_id(task_id)` | O(1) dict lookup (`_task_index` + `_index_size` length-marker invalidation); rebuilt automatically after load completes / after `add_task` appends |

---

## Configuration Management

### Config

Global configuration management, read from environment variables and configuration files.

```python
from config import LLM_CONFIGS, MODEL_NAME

print(len(LLM_CONFIGS))  # Number of loaded LLM providers
print(MODEL_NAME)  # Name of the default model (LLM_1)
```

**Configuration item list:**

| Item | Type | Default | Description |
|--------|------|--------|------|
| `LLM_N_API_KEY` | str | - | API key for the Nth LLM (written in `.env.local`) |
| `LLM_N_BASE_URL` | str | - | Base API URL for the Nth LLM |
| `LLM_N_MODEL_NAME` | str | - | Model name for the Nth LLM |
| `LLM_N_COST_WEIGHT` | float | 0.0 (= no information) | Relative cost multiplier for 3.4 cost-aware routing (0.1~1000; when unset at 0.0, APIManager falls back to a 1.0 baseline) |
| `MAX_ITERATIONS` | int | 3 | Maximum number of repair iterations |
| `COVERAGE_THRESHOLD` | float | 80.0 | Coverage threshold |
| `EXECUTION_TIMEOUT` | int | 30 | pytest execution timeout (seconds) |
| `LLM_TIMEOUT` | int | 60 | LLM call timeout (seconds) |
| `LLM_RETRY_WAIT` | int | 30 | LLM retry wait (seconds) |
| `ENABLE_PLANNER` | bool | true | Enable the Planner |
| `ENABLE_DEBUGGER` | bool | true | Enable the Debugger |
| `ENABLE_RAG` | bool | false | Enable RAG |
| `CROSS_FILE_ENABLE` | bool | false | 3.5 Cross-file repair: enables the `cross_file_analyzer` node (inserted between executor→debugger) + the multi-file patch branch |
| `CROSS_FILE_MAX_MODULES` | int | 5 | 3.5 Maximum module count for a cross-file repair plan (prevents token explosion) |
| `CROSS_FILE_BIDIRECTIONAL` | bool | false | 2.2 Bidirectional cross-file dependency graph: on top of `CROSS_FILE_ENABLE=true`, additionally collects reverse "other module → entry" dependency edges (callee perspective) so the repair plan can synchronously update caller modules; requires `CROSS_FILE_ENABLE=true`, and the independent switch guarantees a two-level conservative policy |
| `ADVERSARIAL_DEBUGGING_ENABLE` | bool | false | 3.1 Adversarial reasoning: before patch generation, the Debugger injects 2-3 "break this implementation" adversarial intent hypotheses (AdverIntent-style), generates targeted tests, then an independent critic evaluates; on breakthrough the patch is regenerated once; observation-only, enabling adds 2-4 LLM calls per repair round |
| `API_CIRCUIT_BACKOFF` | bool | true | 4.4 API circuit-breaker exponential backoff switch: `mark_failure` now cools down for `base * 2^open_count` (capped by `half_open_probe_penalty_cap_seconds`), so a dead provider's cooldown grows monotonically; set to false to revert to the 4.2 fixed-cooldown baseline (for comparison experiments) |
| `API_PROMETHEUS_EXPORT` | bool | false | 4.4 Prometheus metrics export switch: when enabled, `APIManager.to_prometheus_text()` outputs 7 metric groups (health / circuit_state / open_remaining_s / open_count / probe_success_rate / success_rate / avg_response_ms) for monitoring; pure side-band, no impact on existing routing behavior |
| `ASSERTION_AUGMENT_ENABLE` | bool | false | 3.4 Assertion augmentation: AST-extracts existing asserts in the code under test and injects them into the prompt |
| `ENABLE_MULTI_CANDIDATE_PATCH` | bool | false | 3.1 Multi-candidate patch generation with static/execution validation screening (off by default; when there are no candidates, falls back to a single patch); the `reproduce.sh` reproduction flow explicitly enables it by default (can revert to the historical baseline with `--no-multi-candidate`) |
| `AITESTER_TRACE_DIR` | str | unset (no-op) | 4.1 Output directory for the structured JSONL tracing layer (when unset, the tracing layer is a no-op and does not affect execution); `reproduce.sh` enables it by default (`experiments/results/traces`) |
| `BENCHMARK_PARALLELISM` | int | 0 | Parallelism level (0 = serial) |
| `TEMPERATURE` | float | 0.2 | LLM sampling temperature |
| `MODEL_NAME` / `OPENAI_API_KEY` / `OPENAI_BASE_URL` | str | - | Derived values only (taken from LLM_1, for backward compatibility); **not configuration inputs** |
| `EXECUTOR_USE_DOCKER` | bool | false | 4.3 Docker isolated execution (runs pytest inside a container via the docker CLI; requires local docker and a built image; when unavailable, returns a `docker_unavailable` diagnostic without falling back to local) |
| `EXECUTOR_DOCKER_IMAGE` | str | `aitester:latest` | 4.3 Docker image name used for execution (corresponds to the Dockerfile at the repo root) |
| `EXECUTOR_USE_VENV` | bool | false | venv sandbox isolated execution (disk cache keyed by dependency combination; does not pollute the system environment) |
| `EXECUTOR_AUTO_INSTALL_DEPS` | bool | false | Automatically pip install missing dependencies before execution |
| `AITESTER_VENV_CACHE_DIR` | str | `~/.cache/aitester/venvs` | 4.4 Override the venv cache directory (in container/CI isolation, point at a mounted volume; clean up with the `clean-venv-cache` subcommand) |
| `AITESTER_PROFILE` | str | unset (no injection) | R15 switch presets (non-boolean; four tiers as of batch AA, 2026-10-06): `safe` security-sensitive (KERNEL_SANDBOX / PATCH_SNAPSHOT_ROLLBACK / PATCH_ROLLBACK_FAIL_CLOSED / INJECTION_GUARD / ROGUE_MONITOR / FLAKY_CHECK all on) / `scientific` research-evaluation (SPEC_IR / SPEC_IR_DSL / SPEC_SMT / SPEC_ORACLE_EXEC / ENABLE_MUTATION_SCORING / ORACLE_VALIDATE / PATCH_SNAPSHOT_ROLLBACK all on, pair with `run_benchmark(deterministic=True)`) / `logic` full logic chain (scientific superset + PATCH_ROLLBACK_FAIL_CLOSED + LOGIC_SPEC_STRICT / DETERMINISTIC_GUARD / BRANCH_COVERAGE_INJECT / ROUTE_STRUCTURED all on + `DETECTION_FIRST_ENABLE` [completed in batch AA 2026-10-06 — the ADR-0015 detection-first protocol; an all-green first round no longer counts as success]) / `fast` historical defaults (all off, equivalent to unset); injected via `os.environ.setdefault`, explicitly set single switches are never overridden; unrecognized values log a WARNING and are ignored |

**APIManagerConfig fields** (data model in `src/api/api_health.py`, consumed by `api_manager.py`; a programming-interface configuration, not an environment variable; 4.1/4.2 circuit breaker + 3.4 cost awareness):

| Field | Type | Default | Description |
|------|------|--------|------|
| `circuit_cooldown_seconds` | float | 60.0 | 4.1 Circuit breaker cooldown duration: after a node fails `max_consecutive_failures` times in a row, it enters a cooldown period |
| `enable_half_open_probe` | bool | True | 4.2 Half-open probe switch: after the cooldown expires, the node first enters a half-open window that carries only one probe; a success closes the circuit breaker / a failure re-opens a half cooldown; set to False to fall back to 4.1 direct-pass behavior |
| `half_open_probe_penalty_cap_seconds` | float | 30.0 | 4.2 Upper bound on the half-open probe failure penalty duration: failed re-open cooldown = `min(circuit_cooldown_seconds/2, this field)` |
| `cost_alert_threshold` | float | 2.0 | 3.4 Cost alert threshold: logs a WARNING when failover transfers to an expensive node with `cost_weight >= threshold` |
| `batch_health_check_interval` | float | 0.1 | Interval (seconds) between nodes in a batch health check: avoids triggering rate limits with a burst of traffic during serial probing; 0 = pure serial queuing (large node-pool scenarios); 0.1 keeps the historical default behavior |

> Monitoring: `get_status()` outputs `circuit_open_remaining_s` (remaining seconds of circuit breaker cooldown) and `circuit_state` (three-state `closed` / `open` / `half_open`; half_open is reported only when `enable_half_open_probe=True`) per node.

---

## Error Handling

### Common Exceptions

| Exception | Trigger Scenario | How to Handle |
|------|---------|---------|
| `RuntimeError` | LLM call failure | Check the API key and network connection |
| `ModuleNotFoundError` | Imported module does not exist | Check the `module_name` configuration |
| `SyntaxError` | Generated code has a syntax error | The Debugger will regenerate it |
| `TimeoutError` | Test execution timeout | Increase `EXECUTION_TIMEOUT` |

---

## Redaction Boundaries & Known Blind Spots

> 4.1 audit scope: redaction is a **bypass observation layer** that never blocks the main flow; this section registers the **capability boundaries** and **known blind spots** of redaction, for users evaluating "is it safe to share logs / traces".

### Covered channels (where redaction applies)

| Channel | Redaction function | Credential replacement | Degradation strategy |
|------|---------|---------|---------|
| Console logs (stdout/stderr) | `logging_utils.mask_sensitive_info` + `redact_text` | `<REDACTED_API_KEY>` / `<REDACTED_BEARER>` | Three-tier degradation: ① regex replacement ② on import failure, output raw + warning ③ if the redaction function itself crashes, silently skip |
| Trace JSONL (`AITESTER_TRACE_DIR`) | same `mask_sensitive_info` (same source; uniformly passed in `TraceSession._append`) | same | serialization failure drops the record + warning; redaction import failure degrades to raw write (never blocks the observation layer) |
| In-memory snapshot (before `--dump-trace-on-failure` writes to disk) | snapshot records already passed through redaction when entering `TraceSession._append` | same | write failure returns None + warning (diagnostics exit, never blocks the main flow) |
| `os.environ` process-level credentials | `credential_scrub.scrub_os_environ` | set to empty / placeholder | called before 3 exec paths; import failure silently skips (main flow does not depend on it) |
| LLM call exception logs | `api_manager._redact` → `redact_text` | same | when exception body echoes request headers / base_url (containing API Key), uniformly redacted |

### Known blind spots (paths redaction does NOT cover)

| Blind spot | Explanation | Mitigation |
|------|------|------|
| LLM gateway 401/5xx error body echoing request headers | some openai-compatible SDKs' `str(e)` put `Authorization` or `base_url` (API Key in query-param form) into the exception message; `_redact` already covers the SDK path, but **third-party gateway custom error bodies** (exceptions not raised by the standard openai SDK) may bypass it | when deploying with non-standard gateways, recommend passing the error response body through `redact_text` as well; or use `credential_scrub` to clear `os.environ` before subprocess exec |
| Custom credentials in `os.environ` with prefixes other than `LLM_N_*` / `GITHUB_*` | the 3 exec paths of `scrub_os_environ` match by prefix (`LLM_N_API_KEY` / `LLM_N_BASE_URL` / `GITHUB_TOKEN` / `GITHUB_REPOSITORY`); user-defined prefixes (e.g. `MY_PROVIDER_API_KEY`) are NOT auto-cleared | manually `del os.environ[...]` for custom prefixes before the exec call; or add to the prefix table in `scrub_os_environ` |
| Credentials in nested non-str values inside trace meta fields | `TraceSession._append`'s redaction acts on the JSON-serialized full-line text; if `task_meta` nested dict contains an `api_key` key, the serialized form is matched by line-wide regex (covered), but **plaintext appearing in non-key form** (e.g. a meta value that is a whole string containing the Key) depends on regex hit, with possible misses | avoid putting whole credential-bearing text as meta values when constructing `task_meta`; credentials go through `os.environ` (already cleared by `scrub_os_environ`) |
| Degraded raw output when write fails / redaction import fails | `TraceSession._append`'s redaction import failure "degrades to raw write" (never blocks the observation layer); in extreme scenarios (e.g. `logging_utils` monkeypatched out), credentials may be written to disk raw | degradation path logs a warning; production environments should not monkeypatch `logging_utils` |

### Verification

- `tests/test_trace_observability.py::TestRedaction`: `sk-ws-`-prefixed credentials are replaced with `<REDACTED_API_KEY>` in the trace JSONL.
- `tests/test_redaction_audit.py` (if present): full-project redaction audit (0.7 audit scope).
- Manual check: set `AITESTER_TRACE_DIR=/tmp/tr`, run `python main.py run examples/calculator.py --json`, then `grep -r 'sk-ws-' /tmp/tr` should yield 0 hits.

---

## Extension Development

### Adding a New Agent

1. Inherit the `BaseAgent` class
2. Define the System Prompt
3. Implement the core methods
4. Register it in the workflow graph

```python
from src.agents.base_agent import BaseAgent


class MyAgent(BaseAgent):
    def __init__(self):
        super().__init__(MY_SYSTEM_PROMPT)

    def my_method(self, input_data):
        # Implementation logic
        pass
```

### Adding a New Dataset

1. Implement the `BaseDatasetLoader` abstract base class
2. Return `target_code`, `function_name`, `module_name`
3. Register it in the `dataset_map` of the `load_dataset()` factory function

```python
from src.datasets.dataset_loader import BaseDatasetLoader


class CustomDataset(BaseDatasetLoader):
    def __init__(self):
        self.tasks = [...]

    def __iter__(self):
        return iter(self.tasks)
```

---

## Version History
| 0.12 (2026-09-28) | 2026-09-28 | Frontier-recommendation batch landed (gap_report P0/P1/P2 gaps, all default behavior unchanged + new capabilities all behind independent switches): ① G2 P0 risk-tiered human approval loop (`src/graph/risk_approval.py`, `RISK_APPROVAL_ENABLE` default off, three-factor weighted scoring → low/medium/high → auto_merge/human_confirm/force_review, `run_benchmark` result rows gain a `risk_summary` placeholder field); ② G8 P0 full-stack SWE-bench Pro re-test (`experiments/run_full_stack_swe_bench_pro.py` one-key seven-switches + `scripts/check_swe_bench_pro_ready.py` data pre-gate + `experiments/summarize_full_stack.py` ON/OFF contrast & error-bucket comparison); ③ G3 P1 kernel-level sandbox (`src/agents/kernel_sandbox.py`, `KERNEL_SANDBOX_ENABLE` default off, macOS Seatbelt / Linux Landlock+bwrap dual backend, platform-unsupported → fail-closed rejection); ④ G1 P1 Tree-sitter precise AST backend (`src/tools/tree_sitter_backend.py`, optional dependency, transparently degrades to the lexical layer when `tree_sitter` is missing, does not block the Python main path); ⑤ G4 P1 AgentTelemetry failure-detection benchmark (`src/observability/agent_telemetry.py`, `AGENT_TELEMETRY_ENABLE` default off, 10 built-in failure-pattern regex matches, zero LLM cost, pure observation, outputs a Markdown report); ⑥ G5 P2 testless execution-irrelevant validation (`src/tools/testless_validation.py`, `TESTLESS_VALIDATION_ENABLE` default off, four independently toggleable layers: AST symbol guard / mypy static check / naming-contract regression / import smoke; any layer failure → overall fail); ⑦ G6 P2 multi-agent debate convergence (`src/graph/expert_pool.py` new `debate_round()`, `EXPERT_POOL_DEBATE_ENABLE` default off requiring `EXPERT_POOL_ENABLE=true`, top-K (default 2, `EXPERT_POOL_DEBATE_TOP_K` [2,4]) candidate debate convergence produces one `debate_revise` revised candidate; on LLM failure, conservatively degrades back to the original verified list); ⑧ G7 P2 defect-report generation (`src/reports/generator.py` `ErrorReport` new `oracle_stats` field + `with_oracle_stats()` method; the "Oracle validity (Oracle augmentation, G7)" section is rendered only when `total_oracles > 0`); ⑨ doc-consistency P2 (`docs/dependency_exemptions.md` dependency-exemption registry + `scripts/check_dependency_exemptions.py` CI gate + `scripts/check_docs_history_drift.py` warning-only historical-snapshot drift detection); full 2487 tests passed with zero regressions (baseline 2453, +34 new tests covering the above 8 gaps) / ruff 0 warnings / mypy 0 errors (86 source files) |
| 0.9 (2026-09-27) | 2026-09-27 | Roadmap remaining-gaps landed + round-11 feature batch (default behavior unchanged): ① error classification 16→17 (new `PATCH_SYNTAX_INVALID`, 2.2 resample-exhausted marker); ② 2.2 patch post-processing resampling (`PATCH_RESAMPLE_ENABLE`, up to `PATCH_RESAMPLE_MAX` times); ③ 1.3 layered-compression downgrade-chain propagation (`contract_reject_feedback` cross-round via `_debugger_node` + tier-temperature mapping); ④ multi-dimensional contamination detection (`contamination_risk_level` field + `rag_ab_experiment.compare_ab` new `token_saving.delta_pct`); ⑤ 2.1 mypy static layer (`TYPE_CHECK_ENABLE` when `type_repair._run_mypy_findings` supplements layered type findings); ⑥ roadmap remaining gaps filled: SWE-bench Pro support (`swe_bench_pro` / `swebench_pro` registration) + CodeBERT embedding backend (`EMBEDDING_BACKEND=codebert`, `transformers.AutoModel` loading, conservative fallback when the dependency is missing) + pyright static-type backend (`TYPE_CHECK_BACKEND=pyright`, pyright CLI / pyright-python, degrades to ast static layer when unavailable); full 1937 tests passed (baseline 1920 + 17 new) / ruff / mypy all green (64 source files) / coverage 94% | ninth-batch parallel subagent deep-audit P1×4 (`patch_applier` single-function import prefix misclassified as full-file mode — local imports landing in the first 200 chars triggered top-level import silent-drop; `multi_candidate` execution-validation mode still returned the least-bad candidate and wrote degraded code when all candidates had `exec_passed=False` — guard returns None; `dependency` `create_venv` cache-hit-check + create sequence unlocked under `--parallel` same-cache-dir races — per-dir lock; `executor_repo` `verify()` temp test file name keyed only on `(commit, pid)` so same-pid threads overwrote each other — added thread-ident third key + `setup()` clone/venv/pip per-env_dir lock) + P2×10 (`debugger` two-consecutive-malformed-JSON always raised `JSONDecodeError` crashing the node — try/except degrades to empty patch + critic requery same guard; `executor_runtime` generic-exception branch nullified first-attempt `last_result` losing real test output — keep most-recent valid result + return `(UNAVAILABLE, error_info)` marker when none; `patch_applier` `_find_function_start_line_in_lines` regex lacked async prefix — added `(?:async\s+)?` aligned with `_TOP_DEF_RE`; `multi_candidate` `_coverage_trend` non-numeric delta `float()` crash — try/except skip; `generator` per-call `re.compile` — precompiled module-level `_FROM_IMPORT_RE`; `convergence_analysis` no-per-round-detail path double-counted `total_tokens` — each task total counted once at its final-reached round + increment taken directly from current round_tokens) + 26 new regression guards (`tests/test_2026_09_26_review_round9.py`); tenth-batch full-project P1/P2 convergence P1×6 (`graph/nodes._suggest_iteration_strategy` non-numeric `coverage_delta` bare `float()` crash in executor node — try/except skip; `agents/base_agent._lru_store` unbounded negative cache — capped at `_LRU_MAXSIZE` FIFO eviction; `experiments/analysis_parts/rag_analysis._rag_similarity_distribution` negative `max_similarity` bins KeyError — clamp to 0 + non-numeric skip; `experiments/analysis_parts/convergence_analysis._execution_trace_summary` non-numeric `reward_signals`/`coverage` bare `float()` crash — `contextlib.suppress`; `experiments/statistical_analysis._pair_by_task` cross-batch duplicate `task_id` last-wins dict dropped early batches — first-seen dedup + warning; `experiments/run_benchmark` summary bare `r["iterations"]`/`r["elapsed_seconds"]` crash on None values — `r.get(...) or 0`) + P2×10 (`executor_repo` verify() "git stash" wording corrected to actual "git checkout -- . / clean -fd"; `executor_runtime` second `TimeoutExpired` no longer overwrites first valid pytest output — appends `[timeout attempt N]` snapshot; `generator._fix_import_module` dotted-path bare substring replace mis-edited package-form imports — module-name-anchored regex; `cli/app.py` `--verbose + --json` conflict now explicitly noticed; `dataset_loader` `total_test_count` fallback now `len(F2P) + len(P2P)`; `reports/generator` `error_context` None renders "unknown"/"—"; `code_context._closure_names` depth=N caliber documented; `convergence_analysis` module-level `_safe_int`/`_safe_float` + all bare int()/float() sites normalized; `rag_analysis` `_iter_rag_stats` skips non-dict elements + similarity mean over truncated [0,1] range; `compare_failures` regressed excludes new_categories; `run_benchmark` L701 dead write of `results[baseline]["mutation_feedback"]` removed; `statistical_analysis.run_all_statistics` distinguishes the two NaN causes + `cohens_d` docstring corrected) + 33 new regression guards (`tests/test_2026_09_27_review_round10.py`); repo-wide ruff format normalization of 14 files; full 1920 tests pass / ruff 0 warnings / mypy 62 source files 0 errors / 94% coverage |
| Unreleased (2026-09-26) | 2026-09-26 | Full-review & conservative-optimization round (default behavior unchanged, six batches): static checks zeroed (4 mypy errors + 5 ruff lint + 11 files format-normalized); dead-code cleanup (unreachable block in `_build_node_list`) + thread hygiene (`reset_manager`'s health-check thread stop moved out of the global-lock critical section); project hygiene (`.gitignore` extended for tool caches / experiment data dirs); P0 credential-scrub hardening (numbered variants `OPENAI_(API_KEY\|BASE_URL)_\d+` + provider intermediate vars coupled with `PROVIDER_TEMPLATES` keys; `APIManager.call` all-node-failure exception exit uniformly `_redact`-ed; `config_manager.add_llm_config` rejects newlines / `#` in var values; `retry_with_backoff` log lazy-redacted; `SensitiveFormatter` fallback now takes the pure-regex path first); concurrency race fixes (`APIHealth` node-level `threading.Lock` atomicity, `health_check_all/batch` lock-held snapshot iteration + stop-event check between batches, LLM cache and cross-file plan cache rewritten as "temp file + `os.replace`" atomic writes, `ReportGenerator` double-checked lock); CF-3 cross-file repair defect fixed (`build_cross_file_repair_plan` gains a `source_files` parameter so each module's patch is generated from its own source — previously all modules shared the entry code, misaligning multi-file patches; the cache wrapper now passes it through transparently); fifth-batch P0 (mutation test `_run_mutant_tests` now judges kills by the official pytest exit codes (rc==1 kill / other non-zero conservatively alive, fixing the always-1.0 score misjudgment) + (lineno, col_offset)-keyed mutant location + round-robin dedupe sampling, `run_benchmark` parallel API rotation switched to `zlib.crc32` for cross-process reproducibility (former `hash()` was subject to `PYTHONHASHSEED` randomization), `single_agent` baseline write guarded with minimal safety checks, `repo_verification` state schema explicitly declared, `_parse_failed_cases` now matches pytest short-output patterns); sixth-batch node-layer routing semantics & robustness (`_should_debug` diagnosis-keyword check promoted to an independent branch — early-iteration "test generation error" now regenerates via the generator, `test_passed` unified to truthiness semantics, `_generator_node` LLM failure degrades to empty test instead of crashing the whole graph, planner/debugger fallback widened to `OSError`, `_FILE_CACHE_COUNT_MEMORY` read-modify-write locked, `extract_focused_code_detail` eliminates the duplicate AST parse, `DatasetLoader.get_task_by_id` O(n)→O(1) indexed lookup, `redact_dict` string-input contract fixed); full 1785 tests pass (~29s) / zero regressions / ruff + mypy all green |
| Unreleased (2026-09-24) | 2026-09-24 | Full-audit fix round (security + correctness + maintainability): credential scrubbing factored into a dynamic-pattern module — new `src/utils/credential_scrub.py` (`scrub_os_environ()` strips `LLM_\d+_API_KEY` / `LLM_\d+_BASE_URL` via dynamic pattern + common SDK credentials), wired into all three execution paths (local / venv / Docker; previously local popped only 7 hard-coded vars and venv/Docker inherited the host environment verbatim, so `LLM_N_API_KEY` credentials were readable by generated code); CLI `finally`-block fragile code eliminated (`final_state` explicitly initialized to `None` + `is not None` check, replacing the `locals()` check); multi-candidate node made side-effect-free (`_select_multi_candidate_patch` now passes stats via its update dict instead of writing the shared TypedDict in place); patch function-location regex→AST (`_find_function_range_ast` reads `FunctionDef.lineno/end_lineno` so decorated / comment-containing functions are no longer truncated early, with automatic regex fallback when the source can't parse); `requirements.txt` now explicitly declares `openai==2.54.0` (`api_manager.py` imports it at top level, previously satisfied only by a transitive dep); deleted `.env.local.bak` (a backup file holding real keys); 5 tests/ ruff nits fixed (I001/F401/RUF100/E741/SIM115); full 1672 tests pass / ruff 0 warnings / mypy 0 errors / src coverage 94% |
| Unreleased (2026-09-23) | 2026-09-23 | Static-type zeroing + code-quality cleanup round (default behavior unchanged): mypy 0 errors across the repo (19 files type-fixed — explicit `dict[str, Any]` where dict values mix str/int/dict/list, `ast.Module` parameter narrowing, TimeoutExpired merge `_to_str` normalization, module-time attribute-binding ignores, zai retry-tuple dead-subclass removal, `setup_logger_safety` idempotent short-circuit, chromadb metadata normalized via `float`); 3 test files' `time.sleep` mocked (suite ~30s→~22s); full 1659 tests pass / ruff 0 warnings / mypy 0 errors / src coverage 94% |
| 0.7 | 2026-09-21 | Cross-file phase 2 + data-integrity fix + research kickoff (A/B/C directions): 3.5 cross-file repair phase 2 — multi-entry dependency analysis (`analyze_multi_entry_deps`, first-level expansion + dedupe merge) + topological-order patch application (`apply_multi_file_patch(deps=...)`, Kahn's algorithm callee-first, cycles broken lexicographically, omitted `deps` falls back to lexicographic order preserving phase-1 semantics) + repair-plan cache (`build_cross_file_repair_plan_cached`, dependency-graph fingerprint persisted to the LLM cache directory, zero LLM calls on hit); 4.4 dependency-cache consistency fix (`list_venv_cache` getctime→getmtime, cross-platform alignment with `clear_venv_cache`); RAG write-lock hot-path optimization (`_upsert` cleanup/capacity-check moved out of the lock, only upsert inside the write lock, `--parallel` + RAG ingestion no longer queues, transient over-capacity relaxed to "at most parallelism-count entries, converges next cleanup window", 0.6 P1-4 eviction semantics unchanged); run_benchmark silent-fallback misleading-archive fix (empty requested subset falls back to examples, archived `dataset` field reset accordingly + warning explicitly marks "not the originally requested dataset", exposed by the R-01 probe first run); R-01 SWE-bench backfill probe kickoff (`docs/design/swe_bench_probe.md`, found lite subset JSONL empty + generic file lacking `instance_code` — the real blocker is "dataset has no usable source code" rather than quota, option (c) logged); `llm_cache.py` docstring marks "production path now uses the file cache, this module keeps interfaces only" (eliminating dual-cache cognitive drift); full 1627 tests pass / ruff 0 warnings / src coverage 94% |
| 0.6 | 2026-09-20 | P0 fix batch (three-track performance audit: dead code/technical debt + hot paths + doc drift, manually reviewed): P0-1 LLM OpenAI path zero-retry → exponential-backoff failover (`_retry_with_exponential_backoff` 1s/2s/4s wired into the OpenAI path, aligned with the zai path; empty responses also trigger retry; failover only after retries are exhausted); P0-2 venv cache stats dual-lock separation (ns-level counting lock + independent persist lock protecting read/snapshot/write — a naive move out of the counting lock would cause lost-update under concurrency, verified by a new guard test: 8 threads × 100 events, 0 lost); P0-3 ghost-switch implementation (`API_CIRCUIT_BACKOFF` default true / `API_PROMETHEUS_EXPORT` default false, centrally declared in `config.py`, wired into `api_health.mark_failure` + `_probe_circuit_half_open` and `api_manager.to_prometheus_text` — six doc promises finally have code read points); multi_candidate double-patch-apply elimination (`static_validate_patch` signature 2-tuple → 3-tuple reusing the `apply` result); 15 ruff warnings cleared + 33-file format normalization; full 1612 tests pass / 94% src coverage |
| 0.4 | 2026-09-20 | Five-chapter capability enhancement: 1.1 evaluation metrics deepened (EagerTest/LackOfCohesion smells + convergence token efficiency + difficulty-stratified iterations + mutation × assertion cross-check + RAG token/similarity + root-cause trends + contamination cross-analysis); 1.2 mutation feedback loop (boundary_shift/return_void mutants + prompt injection + run_single_task flag fix); 2.1 multi-dimensional contamination detection (structural AST skeleton LCS + semantic token-bag cosine + SWE-rebench registry); 2.2 cross-file bidirectional dependency graph (reverse edges + symbol def-line, `CROSS_FILE_BIDIRECTIONAL` default false); 3.1 adversarial reasoning (AdverIntent + critic evaluation + patch re-generation, `ADVERSARIAL_DEBUGGING_ENABLE` default false); 3.2 execution-feedback dynamic iteration strategy + line-level credit assignment (BOOSTAPR-style); 4.4 circuit-breaker exponential backoff + Prometheus export (`API_CIRCUIT_BACKOFF` default true / `API_PROMETHEUS_EXPORT` default false) + venv cache capacity monitoring (5GB threshold, monitor-only); 4.2 `redact_dict` recursive redaction + JWT fallback + injection regression CI cases; 5.2 error-classification taxonomy 12→14 (EXECUTION_TRACE_MISSING + MULTI_CANDIDATE_ALL_REJECTED); full 1548 tests pass / zero regressions |
| 0.2 | 2026-09-19 | Code-quality & reliability optimization round (no new features, zero functional breakage): RAG degradation guard extraction (`graph/rag.py` adds a dependency-injection `rag_guarded`, unifying 4 isomorphic templates in `nodes.py`, historical patch paths unchanged); multi-function patch sort O(n·m)→O(n+m) (`patch_applier.py` adds `_find_function_start_line_in_lines` reusing pre-split lines); experiment ranking-binding fix (`experiments/analysis.py` sorts by name/value binding + new out-of-order-insertion regression test, full suite 1459→1460); database name whitelist (`init_db.py`, closes the env-variable SQL-injection vector); lazy-import elimination (`base_agent.py`); redaction dual-implementation convergence (`llm_client._redact_log_text` / `api_manager._redact`); batch health-check interval exposed as configurable `APIManagerConfig.batch_health_check_interval`; 24 pre-existing Ruff warnings in tests/ cleaned + 1 tautological assertion fixed; `ruff check src/ tests/` all green |
| 0.1 | 2026-09-18 | First official release: four-agent architecture (Planner/Generator/Executor/Debugger) + 12-category hierarchical error repair + Logic-driven CoT; multi-baseline comparison (aitester/plain_llm/single_agent) + SWE-bench/Defects4J-Python/synthetic dataset support; SWE-bench source export automation + data contamination detection; statistical tests (t-test/Mann-Whitney U/Cohen's d); results analysis layer (repair convergence/boundary coverage/mutation score/assertion strength/execution feedback traces); built-in mutation test generator + test smell detection; structured JSONL tracing layer; multi-candidate patches; cost-aware routing + circuit-breaker cooldown + half-open probe; cross-file repair; assertion augmentation; Docker isolated execution; dependency cache monitoring + clean-venv-cache CLI; Ruff + pre-commit + GitHub Actions CI; 1459 test cases / 96% coverage |

