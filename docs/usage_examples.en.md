> **Language**: [中文版](usage_examples.md) | English (this document)

# AITester Usage Examples

> This document provides detailed usage examples to help developers get started with AITester quickly.
> Last updated: 2026-09-14

---

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Batch Benchmarking](#batch-benchmarking)
3. [Configuration Tuning](#configuration-tuning)
4. [Advanced Features](#advanced-features)
5. [FAQ](#faq)

---

## Basic Usage

### Example 1: Testing a Single Function

```bash
# Test the divide function of calculator.py
python main.py run examples/calculator.py --func divide
```

**Example output:**
```
[Planner] Starting analysis of function: divide
[Generator] Generating test code...
[Executor] Running tests...
[Debugger] No errors found that need repair
Result: PASS, Coverage: 100%
```

---

### Example 2: Testing a Function That Contains a Bug

```bash
# Test the binary_search function of buggy_library.py (contains a bug)
python main.py run examples/buggy_library.py --func binary_search
```

**Example output:**
```
[Planner] Starting analysis of function: binary_search
[Generator] Generating test code...
[Executor] Running tests...
[Debugger] Detected an assertion error, starting repair...
[Debugger] Repair patch applied, re-running tests...
Result: PASS, Coverage: 100%, Iterations: 1
```

---

### Example 3: Testing All Functions

```bash
# Without specifying --func, test all functions in the file
python main.py run examples/calculator.py
```

---

## Batch Benchmarking

### Example 4: Running the Built-in Dataset

```bash
# Run the examples dataset, comparing three baselines
python experiments/run_benchmark.py \
    --dataset examples \
    --baselines aitester,plain_llm,single_agent
```

---

### Example 5: Limiting the Number of Tasks (Quick Validation)

```bash
# Run only 2 tasks
python experiments/run_benchmark.py \
    --dataset examples \
    --task-limit 2
```

---

### Example 6: Running the Synthetic Dataset

```bash
# Generate and run 50 synthetic tasks
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 50 \
    --baselines aitester
```

---

### Example 7: Parallel Execution (Speedup)

```bash
# Execute in parallel with 4 threads
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 100
```

Or use a command-line argument:
```bash
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 100 \
    --parallel 4
```

---

## Configuration Tuning

### Example 8: Adjusting the Timeout

```bash
# Set the pytest execution timeout to 60 seconds
python main.py run examples/calculator.py --timeout 60
```

Or configure an environment variable:
```bash
EXECUTION_TIMEOUT=60 python main.py run examples/calculator.py
```

---

### Example 9: Adjusting the Maximum Number of Iterations

```bash
# Repair for up to 5 rounds
python main.py run examples/buggy_library.py --func binary_search --max-iterations 5
```

---

### Example 10: Enabling RAG Augmentation

Edit the `.env` file:
```bash
ENABLE_RAG=true
```

Then run:
```bash
python main.py run examples/calculator.py --func divide
```

---

### Example 11: Ablation Experiments

```bash
# Enable the Planner only (disable the Debugger)
ENABLE_PLANNER=true ENABLE_DEBUGGER=false python experiments/run_benchmark.py \
    --dataset examples
```

---

## Advanced Features

### Example 12: JSON Output (Programmatic Processing)

```bash
# Results are output in JSON format (printed to stdout directly, no switch needed)
python experiments/run_benchmark.py \
    --dataset examples
```

**Example output:**
```json
{
  "dataset": "examples",
  "total_tasks": 3,
  "results": [
    {
      "task_id": "calculator.py::divide",
      "status": "pass",
      "coverage": 100.0,
      "iterations": 0
    }
  ]
}
```

---

### Example 13: Result Visualization

```bash
# Generate visualization charts
python experiments/visualize_results.py

# Specify a results directory
python experiments/visualize_results.py \
    --results-dir experiments/results/synthetic_full
```

Output files:
- `experiments/results/charts/baseline_comparison.png`
- `experiments/results/charts/statistical_significance.png`
- `experiments/results/charts/summary_stats.md`

---

### Example 13.5: Structured Result Analysis (4.3 + 1.1/1.2/1.3 Metrics)

```bash
# Analyze the latest benchmark results
python experiments/analyze_results.py --results-dir experiments/results

# Analyze a specific benchmark JSON
python experiments/analyze_results.py \
    --input experiments/results/benchmark_synthetic_<timestamp>.json
```

Output:
- Prints a Markdown summary to the terminal (success rate / Token efficiency / iteration count distribution / failure cause distribution / RAG quality / repair convergence efficiency / multi-dimensional quality proxies / test smell detection / repair convergence curve)
- `<same directory as the input file>/analysis_summary.md`

**New metric descriptions (1.1 multi-dimensional evaluation + 1.2 repair convergence efficiency + 1.3 repair convergence curve + 1.2 test smell detection)**:

| Metric Group | Field | Description |
|--------|------|------|
| Repair convergence efficiency | `repair_convergence_metrics.first_attempt_success_rate` | Share of tasks that passed on the first attempt (iterations==0) |
| Repair convergence efficiency | `repair_convergence_metrics.success_iteration_stats` | min/avg/median/max of iteration counts for successful tasks |
| Repair convergence efficiency | `repair_convergence_metrics.success_elapsed_seconds` | min/avg/median/max of elapsed times for successful tasks |
| Multi-dimensional quality proxies | `quality_proxy_metrics.coverage_proxy` | Mean and median coverage for successful/failed tasks |
| Multi-dimensional quality proxies | `quality_proxy_metrics.runtime_proxy` | Mean and median elapsed time for successful/failed tasks |
| Multi-dimensional quality proxies | `quality_proxy_metrics.assertion_proxy` | If `details[].generated_test` exists, counts `assert` lines per task (proxy for assertion strength) |
| Multi-dimensional quality proxies | `quality_proxy_metrics.failure_top_categories` | Top-N error categories for failed tasks (helps attribution) |
| Test smell detection (1.2) | `test_smell_detection` | Scans `details[].generated_test` with AST, detecting 4 categories of LLM-generated smells: Assertion Roulette (no effective assertion) / Magic Number (≥3 unnamed integers) / Weakened assertion (fewer assertion lines than the previous round) / Trivial test (function body is only pass / tautological assertion); when old JSON lacks `generated_test`, `available=False` skips the section |
| Repair convergence curve (1.3) | `repair_convergence_curve` | Statistics by iteration round 0/1/2/3+ of "tasks reached / cumulative passes / cumulative pass rate / cumulative average elapsed time", observing how the pass rate evolves as iterations increase |

> Note: this section uses conservative proxy metrics (recomputable from the existing result fields) and is not equivalent to precise structural/performance metrics such as AST cyclomatic complexity or memory usage; `assertion_proxy` / test smell detection / repair convergence curve are available only when `details[].generated_test` is provided in the result JSON, and old JSONs automatically degrade to `N/A` or skip the section.

---

### Example 13.6: Failure Root-Cause Analysis + Case Knowledge Base (5.3)

```bash
# Failure case clustering report + three major root-cause classes (LLM capability / dependency / framework) + writing out a structured knowledge base
python experiments/analyze_failures.py \
    --results-dir experiments/results \
    --knowledge-base experiments/results/failure_knowledge_base.json
```

Output:
- A Markdown report clustering failure cases by baseline / error type (`--output` defaults to `experiments/results/failure_analysis.md`)
- The three major failure root-cause classes (`llm_capability` / `dependency` / `framework`, conservatively heuristically classified by `root_cause_classification()`, up to 3 representative cases per class)
- The structured case knowledge base `failure_knowledge_base.json` (selected by `error_category` diversity first, containing `task_id` / `root_cause` / `reproducible_steps` / `suggested_fix`)

---

### Example 14: Listing Examples

```bash
python main.py list-examples
```

**Output:**
```
Available example files:
  - examples/calculator.py (divide, factorial)
  - examples/buggy_library.py (binary_search, merge_sorted)
  - examples/string_utils.py (is_palindrome, caesar_cipher)
```

---

## Python API Usage

### Example 15: Programmatic Invocation

```python
from src.agents.planner import PlannerAgent
from src.agents.generator import GeneratorAgent
from src.agents.executor import ExecutorAgent
from src.agents.debugger import DebuggerAgent
from src.tools.patch_applier import apply_patch_to_code

# Target code
target_code = """
def divide(a: float, b: float) -> float:
    '''Returns the quotient of two numbers.'''
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
"""

# Step 1: Plan
planner = PlannerAgent()
plan = planner.plan(target_code, "divide")

# Step 2: Generate tests
generator = GeneratorAgent()
test_code = generator.generate(plan, target_code, "calculator")

# Step 3: Execute tests
executor = ExecutorAgent()
result = executor.execute(test_code)

print(f"Test result: {result['status']}")
print(f"Coverage: {result['coverage']}%")
```

---

### Example 16: Using the Workflow Graph

```python
from src.graph.workflow import build_workflow
from src.graph.state import AITesterState

# Build the workflow (planner/debugger default to None, reading config.ENABLE_PLANNER / ENABLE_DEBUGGER)
graph = build_workflow()

# Run the workflow: invoke takes an initial state dict and returns the final state
state: AITesterState = {
    "target_code": "def add(a, b): return a - b",  # Intentionally wrong
    "target_function": "add",
    "module_name": "calculator",
    "max_iterations": 3,
}
result = graph.invoke(state)

print(f"Did the test pass: {result['test_passed']}")
print(f"Repaired code:\n{result['target_code']}")
```

---

## FAQ

### Q: How do I add a new file under test?

Place the Python file in the `examples/` directory and make sure it contains function definitions and known bugs (optional).

```python
# examples/my_module.py
def my_function(x: int) -> int:
    """Returns the square of x."""
    return x * x  # Normal implementation
```

Then run:
```bash
python main.py run examples/my_module.py --func my_function
```

---

### Q: How do I handle ModuleNotFoundError?

**Cause**: the module name in the import statement does not match the actual file.

**Solution**:
1. Check that the `module_name` parameter matches the file name
2. Confirm the file under test is on the Python path
3. Use a relative import: `from src.my_module import my_function`

---

### Q: How do I change the LLM model?

Edit `.env.local` (where LLM-sensitive configuration lives) and modify the `LLM_N_*` group:
```bash
LLM_1_MODEL_NAME=gpt-4o
LLM_1_BASE_URL=https://api.openai.com/v1
# Or
LLM_1_MODEL_NAME=agnes-3.0-flash
LLM_1_BASE_URL=https://api.agnes-ai.cn/v1
```

---

### Q: How do I see detailed logs?

Add the `-v` argument:
```bash
python main.py run examples/calculator.py -v
```

Or set the log level:
```bash
LOG_LEVEL=DEBUG python main.py run examples/calculator.py
```

---

## More Resources

- [API Reference](api_reference.md)
- [Performance Tuning Guide](performance_guide.md)
- [Algorithm Design Document](algorithm_design.md)
- [Contributing Guide](../CONTRIBUTING.md)
