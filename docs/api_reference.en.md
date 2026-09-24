> **Language**: [中文版](api_reference.md) | English (this document)

# AITester API Reference Document

> This document describes the core classes and methods of AITester, for developer integration and extension.
> Last updated: 2026-09-24 (full-audit fix round: credential scrubbing factored into dynamic-pattern `credential_scrub.py` shared by the three execution paths (covers the entire `LLM_N_API_KEY` family), CLI `finally`-block fragile code eliminated, multi-candidate node made side-effect-free, patch function-location regex→AST, `requirements.txt` now explicitly declares `openai`; full 1672 test cases / ruff 0 warnings / mypy 0 errors / 94% coverage)

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

**Error category enumeration (12 categories: P2 refinement + 1.2 residuals + 1.1 state refinement):**

| Value | Description | Handling Strategy |
|----|------|---------|
| `llm_format_error` | LLM response format anomaly (JSON parse failure / truncated response / empty response); one of the root causes of the former 75% UNKNOWN (1.2 residual refinement) | Re-request the LLM to generate a compliant response / strip markdown code blocks before parsing / reduce per-call output length |
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

Classification priority (10 categories in `classify()` text regex): `LLM_FORMAT_ERROR > IMPORT_ERROR > SYNTAX > TYPE_ERROR > INDEX_ERROR > RUNTIME > ASSERTION/LOGIC_ERROR > TIMEOUT > UNKNOWN`, all based on regex rule matching, no LLM token consumption. LLM_FORMAT_ERROR is placed first (JSON parse failure text rarely contains IndexError, but IndexError text may contain assert; reversing the order would misclassify). The latter 2 categories (`PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY`) are 1.1 state-refinement categories that do not go through `classify()` text regex; instead, the pure function `refine_failure_category()` determines them at task completion based on `repair_history` (patch rejected) / `rag_stats` (retrieval all empty) signals — patch rejection takes priority over empty RAG retrieval; successful tasks are returned as-is. The benchmark and CLI exits use the same criteria.

---

## Tool Modules

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

# Load the SWE-bench dataset
from src.datasets import SWEBenchDataset

dataset = SWEBenchDataset(subset="lite")

# 2.1 Load the SWE-rebench anti-contamination benchmark (field-compatible with SWE-bench; point data_dir at the rebench data directory)
dataset = load_dataset("swe_rebench", data_dir="/path/to/rebench_data")
```

**Supported dataset names** (the `dataset_map` in `load_dataset`, including aliases):
`swe_bench` / `swebench` / `swe_rebench` / `swebench_rebench` / `defects4j_python` / `d4j_py` / `in_memory` / `examples` / `synthetic` / `synth`. Names not in the list degrade to `InMemoryDataset` (graceful degradation).

**Dataset interface:**

```python
# Iterate over tasks
for task in dataset:
    target_code = task["target_code"]
    function_name = task["function_name"]
    # ...
```

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
| Unreleased (2026-09-24) | 2026-09-24 | Full-audit fix round (security + correctness + maintainability): credential scrubbing factored into a dynamic-pattern module — new `src/utils/credential_scrub.py` (`scrub_os_environ()` strips `LLM_\d+_API_KEY` / `LLM_\d+_BASE_URL` via dynamic pattern + common SDK credentials), wired into all three execution paths (local / venv / Docker; previously local popped only 7 hard-coded vars and venv/Docker inherited the host environment verbatim, so `LLM_N_API_KEY` credentials were readable by generated code); CLI `finally`-block fragile code eliminated (`final_state` explicitly initialized to `None` + `is not None` check, replacing the `locals()` check); multi-candidate node made side-effect-free (`_select_multi_candidate_patch` now passes stats via its update dict instead of writing the shared TypedDict in place); patch function-location regex→AST (`_find_function_range_ast` reads `FunctionDef.lineno/end_lineno` so decorated / comment-containing functions are no longer truncated early, with automatic regex fallback when the source can't parse); `requirements.txt` now explicitly declares `openai==2.54.0` (`api_manager.py` imports it at top level, previously satisfied only by a transitive dep); deleted `.env.local.bak` (a backup file holding real keys); 5 tests/ ruff nits fixed (I001/F401/RUF100/E741/SIM115); full 1672 tests pass / ruff 0 warnings / mypy 0 errors / src coverage 94% |
| Unreleased (2026-09-23) | 2026-09-23 | Static-type zeroing + code-quality cleanup round (default behavior unchanged): mypy 0 errors across the repo (19 files type-fixed — explicit `dict[str, Any]` where dict values mix str/int/dict/list, `ast.Module` parameter narrowing, TimeoutExpired merge `_to_str` normalization, module-time attribute-binding ignores, zai retry-tuple dead-subclass removal, `setup_logger_safety` idempotent short-circuit, chromadb metadata normalized via `float`); 3 test files' `time.sleep` mocked (suite ~30s→~22s); full 1659 tests pass / ruff 0 warnings / mypy 0 errors / src coverage 94% |
| 0.7 | 2026-09-21 | Cross-file phase 2 + data-integrity fix + research kickoff (A/B/C directions): 3.5 cross-file repair phase 2 — multi-entry dependency analysis (`analyze_multi_entry_deps`, first-level expansion + dedupe merge) + topological-order patch application (`apply_multi_file_patch(deps=...)`, Kahn's algorithm callee-first, cycles broken lexicographically, omitted `deps` falls back to lexicographic order preserving phase-1 semantics) + repair-plan cache (`build_cross_file_repair_plan_cached`, dependency-graph fingerprint persisted to the LLM cache directory, zero LLM calls on hit); 4.4 dependency-cache consistency fix (`list_venv_cache` getctime→getmtime, cross-platform alignment with `clear_venv_cache`); RAG write-lock hot-path optimization (`_upsert` cleanup/capacity-check moved out of the lock, only upsert inside the write lock, `--parallel` + RAG ingestion no longer queues, transient over-capacity relaxed to "at most parallelism-count entries, converges next cleanup window", 0.6 P1-4 eviction semantics unchanged); run_benchmark silent-fallback misleading-archive fix (empty requested subset falls back to examples, archived `dataset` field reset accordingly + warning explicitly marks "not the originally requested dataset", exposed by the R-01 probe first run); R-01 SWE-bench backfill probe kickoff (`docs/design/swe_bench_probe.md`, found lite subset JSONL empty + generic file lacking `instance_code` — the real blocker is "dataset has no usable source code" rather than quota, option (c) logged); `llm_cache.py` docstring marks "production path now uses the file cache, this module keeps interfaces only" (eliminating dual-cache cognitive drift); full 1627 tests pass / ruff 0 warnings / src coverage 94% |
| 0.6 | 2026-09-20 | P0 fix batch (three-track performance audit: dead code/technical debt + hot paths + doc drift, manually reviewed): P0-1 LLM OpenAI path zero-retry → exponential-backoff failover (`_retry_with_exponential_backoff` 1s/2s/4s wired into the OpenAI path, aligned with the zai path; empty responses also trigger retry; failover only after retries are exhausted); P0-2 venv cache stats dual-lock separation (ns-level counting lock + independent persist lock protecting read/snapshot/write — a naive move out of the counting lock would cause lost-update under concurrency, verified by a new guard test: 8 threads × 100 events, 0 lost); P0-3 ghost-switch implementation (`API_CIRCUIT_BACKOFF` default true / `API_PROMETHEUS_EXPORT` default false, centrally declared in `config.py`, wired into `api_health.mark_failure` + `_probe_circuit_half_open` and `api_manager.to_prometheus_text` — six doc promises finally have code read points); multi_candidate double-patch-apply elimination (`static_validate_patch` signature 2-tuple → 3-tuple reusing the `apply` result); 15 ruff warnings cleared + 33-file format normalization; full 1612 tests pass / 94% src coverage |
| 0.4 | 2026-09-20 | Five-chapter capability enhancement: 1.1 evaluation metrics deepened (EagerTest/LackOfCohesion smells + convergence token efficiency + difficulty-stratified iterations + mutation × assertion cross-check + RAG token/similarity + root-cause trends + contamination cross-analysis); 1.2 mutation feedback loop (boundary_shift/return_void mutants + prompt injection + run_single_task flag fix); 2.1 multi-dimensional contamination detection (structural AST skeleton LCS + semantic token-bag cosine + SWE-rebench registry); 2.2 cross-file bidirectional dependency graph (reverse edges + symbol def-line, `CROSS_FILE_BIDIRECTIONAL` default false); 3.1 adversarial reasoning (AdverIntent + critic evaluation + patch re-generation, `ADVERSARIAL_DEBUGGING_ENABLE` default false); 3.2 execution-feedback dynamic iteration strategy + line-level credit assignment (BOOSTAPR-style); 4.4 circuit-breaker exponential backoff + Prometheus export (`API_CIRCUIT_BACKOFF` default true / `API_PROMETHEUS_EXPORT` default false) + venv cache capacity monitoring (5GB threshold, monitor-only); 4.2 `redact_dict` recursive redaction + JWT fallback + injection regression CI cases; 5.2 error-classification taxonomy 12→14 (EXECUTION_TRACE_MISSING + MULTI_CANDIDATE_ALL_REJECTED); full 1548 tests pass / zero regressions |
| 0.2 | 2026-09-19 | Code-quality & reliability optimization round (no new features, zero functional breakage): RAG degradation guard extraction (`graph/rag.py` adds a dependency-injection `rag_guarded`, unifying 4 isomorphic templates in `nodes.py`, historical patch paths unchanged); multi-function patch sort O(n·m)→O(n+m) (`patch_applier.py` adds `_find_function_start_line_in_lines` reusing pre-split lines); experiment ranking-binding fix (`experiments/analysis.py` sorts by name/value binding + new out-of-order-insertion regression test, full suite 1459→1460); database name whitelist (`init_db.py`, closes the env-variable SQL-injection vector); lazy-import elimination (`base_agent.py`); redaction dual-implementation convergence (`llm_client._redact_log_text` / `api_manager._redact`); batch health-check interval exposed as configurable `APIManagerConfig.batch_health_check_interval`; 24 pre-existing Ruff warnings in tests/ cleaned + 1 tautological assertion fixed; `ruff check src/ tests/` all green |
| 0.1 | 2026-09-18 | First official release: four-agent architecture (Planner/Generator/Executor/Debugger) + 12-category hierarchical error repair + Logic-driven CoT; multi-baseline comparison (aitester/plain_llm/single_agent) + SWE-bench/Defects4J-Python/synthetic dataset support; SWE-bench source export automation + data contamination detection; statistical tests (t-test/Mann-Whitney U/Cohen's d); results analysis layer (repair convergence/boundary coverage/mutation score/assertion strength/execution feedback traces); built-in mutation test generator + test smell detection; structured JSONL tracing layer; multi-candidate patches; cost-aware routing + circuit-breaker cooldown + half-open probe; cross-file repair; assertion augmentation; Docker isolated execution; dependency cache monitoring + clean-venv-cache CLI; Ruff + pre-commit + GitHub Actions CI; 1459 test cases / 96% coverage |

