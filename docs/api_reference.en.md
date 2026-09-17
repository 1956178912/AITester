> **Language**: [中文版](api_reference.md) | English (this document)

# AITester API Reference Document

> This document describes the core classes and methods of AITester, for developer integration and extension.
> Last updated: 2026-09-16 (dataset & evaluation deepening round: 2.1 contamination detection / 2.2 difficulty stratification / 4.3 Docker execution mode / 4.4 dependency cache)

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

venv_dir = venv_cache_dir(["pandas"])  # Disk cache directory keyed by dependency combination
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

state = create_initial_state(task_uuid="t1", target_file="/p.py", target_code="def f(): pass",
                              target_function=None, max_iterations=3)
# After workflow execution, state["execution_trace"] looks like:
[
  {
    "iteration": 0,
    "passed": False,
    "coverage": 40.0,
    "coverage_delta": None,       # no previous round
    "elapsed_seconds": 2.0,
    "reward_signals": {           # conservative linear normalization, recorded only, never used for routing
      "correctness": 0.0,         # 1.0 if passed else 0.0
      "efficiency": 0.93,         # 1 - elapsed / EXECUTION_TIMEOUT
      "simplicity": 0.97          # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
    }
  },
  {
    "iteration": 1,
    "passed": True,
    "coverage": 85.0,
    "coverage_delta": 45.0,       # 85 - 40
    "elapsed_seconds": 3.0,
    "reward_signals": {"correctness": 1.0, "efficiency": 0.9, "simplicity": 0.95}
  }
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

| Version | Date | Changes |
|------|------|---------|
| 0.9.20 | 2026-09-17 | Structural optimization round: `executor.py` split into 4 focused submodules (`executor_imports.py` / `executor_modes.py` / `executor_output.py` / `executor_runtime.py`; class methods re-bound onto `ExecutorAgent`, so old import paths and test patch targets are unchanged); `dataset_loader.py` split into `dataset_defects4j.py` / `dataset_inmemory.py` (re-export keeps the old import path; `SWEBenchDataset` stays in the main module because its module-level `_datasets` global is a test patch target); Docker execution 5-path mock tests backfilled (`TestDockerExecutionFlow`, previously 0 coverage), dependency edge cases +14 (`tools/dependency.py` 90%→99%), duplicated JSON-parsing dead code in `dataset_loader.py` removed, pytest `filterwarnings` suppresses the scipy constant-group t-test "precision loss" warning; 21 new cases, full suite 1386 passed / 95% coverage |
| Unreleased | 2026-09-16 | Evaluation-metrics deepening round: 1.2 convergence failure-mode attribution (`analyze_results.py:_convergence_failure_modes`, distinguishing "cannot pinpoint root cause" vs "cannot produce an effective patch" for tasks still failing at MAX_ITERATIONS) / 1.3 boundary case coverage (`_boundary_case_coverage`, AST conservative detection of None / empty collection / 0 / -1 / >= / <= boundary conditions) / 1.3 mutation score (`_mutation_score_metrics`, collects details[].mutation_score) / 1.3 assertion-strength AST enhancement (`_assertion_strength_proxy` adds `ast_avg_assertions` + `ast_parse_failed_tasks`) / 3.2 execution feedback trace (`state.execution_trace` + `nodes._record_execution_trace` + `run_benchmark.py` result rows carry the trace + `analyze_results.py` auto-summary, a pure observability layer enabled by default, preparing data for RL fine-tuning); 14 new test cases, full suite 1365 passed / 95% coverage |
| Unreleased | 2026-09-16 | Dataset & evaluation deepening round: 2.1 data contamination detection (`experiments/contamination_check.py`, token-level Jaccard overlap, high ≥ 0.85 / medium ≥ 0.6; `dataset_loader` stores the official patch into `metadata["golden_patch"]`; `load_dataset` supports the `swe_rebench` alias) / 2.2 task difficulty stratification (`experiments/difficulty_stratification.py`, code_size / dependency_count / complexity_proxy) / 4.3 Docker execution mode promotion (`ExecutorAgent._execute_docker` + `EXECUTOR_USE_DOCKER` / `EXECUTOR_DOCKER_IMAGE`; when docker is unavailable, returns a `docker_unavailable` diagnostic without falling back to local; `scripts/compare_executor_modes.py` timing comparison) / 4.4 dependency cache monitoring (CLI `clean-venv-cache` + `AITESTER_VENV_CACHE_DIR` + hit-rate in analysis) / 4.1 redaction audit (`scripts/audit_log_redaction.py` + subprocess credential stripping) / 3.1 `reproduce.sh` enables multi-candidate patches by default + 3.2t `reproduce.sh` explicitly enables `AITESTER_TRACE_DIR` / 5.1 low-coverage module hardening (logging_utils 90%→100%, analysis.py statistical boundary tests, cli/app.py concurrent interrupt / signal handling tests) |
| 0.9.16 | 2026-09-15 | Deep refactor round: AITesterState initialization dual-write converged into the `create_initial_state()` factory (single construction point for CLI + benchmark), statistical tests in experiments/visualize_results.py converged to reuse the paired-test primitives in statistical_analysis.py + NaN/Inf guards, code_context.py added 9 test cases (module coverage 89%→98%), README structure tree completed with 5 split artifacts (tracing/rag/nodes, api_health, llm_client) + 13 inline numbers in the test status table synchronized + parameter default values annotated in api_reference; full suite 1291 passed / ruff all green / coverage 94% |
| 0.9.14 | 2026-09-15 | Whole-project convergence round: config centralization (removed dead CROSS_FILE/ASSERTION constants, converged SWE_BENCH_ENRICHMENT into config, converged MULTI_CANDIDATE_EXEC_VALIDATE into a helper), fixed the executor's standard-library list incorrectly listing diskcache, fixed the cross-file fallback path unable to write to disk, removed 4 dead-code spots, RAG retriever write lock + `_upsert` extraction, `refine_final_error_category` convergence; full suite 1270 passed / ruff all green |
| 0.9.14 | 2026-09-15 | `tests/test_rag_retriever.py` added module-level `pytestmark=skipif(not _chroma_available())` (consistent in criteria with `test_rag_metrics.py`; when chromadb is missing, 32 RAG retriever test cases are skipped gracefully instead of raising an ImportError ERROR); the `TestVisualizeLoadLatestResult` / `TestVisualizeSummaryMdTable` fixtures in `tests/test_experiments_scripts.py` add `pytest.importorskip("matplotlib")` before the lazy import of `experiments.visualize_results` (when matplotlib is missing, 5 visualization test cases are skipped). In a minimal environment (where `requirements.txt` is not fully installed), the full baseline is **1208 passed / 39 skipped / 0 failed**; after fully installing the dependencies it recovers to **1247 passed / 0 skipped** |
| 0.9.14 | 2026-09-15 | O-01 added `tests/test_cli_output.py` (10 cases: colorize TTY dual branches / message stderr routing / print_rich_table boundaries); `src/cli/output.py` coverage 58%→92% |
| 0.9.13 | 2026-09-14 | 4.2 Circuit breaker half-open probe: `APIHealth` added `in_circuit_half_open` and `_probe_circuit_half_open()` (a success closes it / a failure re-opens a half cooldown `min(cooldown/2, cap)`), `get_healthy_nodes()` / `_build_node_list()` include nodes in the half-open window as routing candidates, `call()` / `check_health()` uniformly consume probe results, `get_status()` added `circuit_state` (closed / open / half_open); `APIManagerConfig` added `enable_half_open_probe` (default True; setting False falls back to 4.1 direct-pass behavior) and `half_open_probe_penalty_cap_seconds` (default 30.0); python code block formatting in `docs/design/cross_file_repair.md` normalized; full suite 1237 passed / ruff all green |
| 0.9.13 | 2026-09-14 | 1.2 Test smell detection + 1.3 repair convergence curve (`analyze_results.py` added pure functions `test_smell_detection` / `repair_convergence_curve` + Markdown sections), 4.4 Dependency cache monitoring (`dependency.py` added `get_venv_cache_stats` / `list_venv_cache` / `clear_venv_cache` + `create_venv` records hit/create events; fixed the `threading.Lock` non-reentrant deadlock), 5.3 Failure root-cause classification + case knowledge base (`analyze_failures.py` added `root_cause_classification` / `failure_knowledge_base` + CLI `--knowledge-base`), 3.4 Assertion augmentation strategy (`generator.py` added `_extract_existing_assertions` + `ASSERTION_AUGMENT_ENABLE` switch, off by default), 3.5 Cross-file repair (added coordinator-proposer architecture in `src/tools/cross_file.py` + cross_file_analyzer node in `workflow.py` + `CROSS_FILE_ENABLE` / `CROSS_FILE_MAX_MODULES` switches, off by default); new design document `docs/design/cross_file_repair.md` added; full suite 1225 passed / ruff all green |
| 0.9.13 | 2026-09-14 | Result analysis layer 1.1/1.2 metric enhancements: `experiments/analyze_results.py` added `repair_convergence_metrics` (first-attempt success rate, iteration min/avg/median/max for successful/failed tasks, average elapsed time for successful tasks) and `quality_proxy_metrics` (coverage/elapsed-time proxies, optional `generated_test` assertion-line-count proxy, top-N failure categories); `build_analysis` and `render_markdown` render two Markdown sections "Repair Convergence Efficiency (1.2)" and "Multi-dimensional Quality Proxies (1.1, conservatively recomputable)"; when old JSON lacks `generated_test` / details, it automatically degrades to N/A or skips the section, without crashing. Full suite 1163 passed |
| 0.9.13 | 2026-09-14 | Error classification 10→12 categories (state refinement of PATCH_VALIDATION_FAILED + RAG_RETRIEVAL_EMPTY, determined at task completion by `refine_failure_category()`), configurable cost alert threshold (`APIManagerConfig.cost_alert_threshold`, default 2.0), automated SWE-bench source export (`scripts/export_swe_bench_source.py` + `tasks_missing_source()`), automated RAG metrics summary (breakdown by retrieval type + RAG hit × failure category cross-tabulation), complete redaction audit (7 logging sites in APIManager use in-place `_redact()` + `get_status()` base_url output redaction; the former redaction audit `docs/redaction_audit.md` has been merged into the README security section, and the former performance profile `docs/performance_profile_report.md` has been merged into chapter 9 of `docs/performance_guide.md`); full suite 1158 passed |
| 0.9.13 | 2026-09-14 | Error classification 8→10 categories (LLM_FORMAT_ERROR + INDEX_ERROR, 1.2 residuals), APIManager circuit breaker cooldown period (4.1 residual, default 60s), result analysis script analyze_results.py (4.3), baseline token efficiency summary (2.2) |
| 0.9.12 | 2026-09-13 | Multi-candidate patches (3.1, off by default), structured JSONL tracing layer (4.1, off by default), cost-aware routing (3.4), RAG included in the main experiment (2.3), CLI boundary test completion (1.5) |
| 1.0.0 | 2026-08-17 | Initial version, including 4 agents and the complete workflow |
| 0.9.11 | 2026-09-11 | Single implementation of import extraction, failover model routing, MySQL singleton DCL, RAG stickiness flag, NaN/Inf serialization fixes (see CHANGELOG for details) |
| 0.9.10 | 2026-09-11 | CLI concurrent dispatcher deduplication and regression protection (see CHANGELOG for details) |
| 0.9.9 | 2026-09-11 | Dead branch cleanup, visualize result mis-selection and normalized experiment KeyError fixes (see CHANGELOG for details) |
| 0.9.8 | 2026-09-10 | Format gate restoration, benchmark result construction deduplication, background health thread can be disabled (see CHANGELOG for details) |
| 0.9.7 | 2026-09-10 | AST smart truncation, SWE-bench quality validation, token statistics, venv sandbox, RAG persistence, error classification 5→8 categories (see CHANGELOG for details) |
| 0.9.6 | 2026-09-10 | 14 fixes including the regenerate infinite loop, atomic patch write-to-disk, strengthened redaction, CLI failure gating, etc. (see CHANGELOG for details) |
| 0.9.5 | 2026-09-10 | Whole-block configuration removal, packaging fixes, tolerant parsing of numeric environment variables, logging redaction integration (see CHANGELOG for details) |
| 0.9.4 | 2026-09-13 | Environment variable name derivation, genuine t-test, convergence of the dual statistical implementations, modern chromadb API (see CHANGELOG for details) |
| 0.9.3 | 2026-09-13 | Configuration write-path correction and runtime refresh (see CHANGELOG for details) |
| 0.9.2 | 2026-09-09 | CI gate fixes, singleton thread safety, background thread leak fixes, single source of version numbers (see CHANGELOG for details) |
| 0.9.1 | 2026-09-09 | CLI option state pass-through, backoff formula correction, import replacement similarity gating (see CHANGELOG for details) |
| 0.9.0 | 2026-08-16 | Added RAG support and performance optimizations |
