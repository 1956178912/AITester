> **Language**: [中文版](algorithm_design.md) | English (this document)

# Multi-Agent Collaborative Test Generation and Self-Repair Protocol (Algorithm Design Document)

> This document describes the core algorithm design and theoretical framework of AITester, for technical review and code review reference.
> The appendix provides a precise mapping table from algorithms to source code, to help locate implementation details quickly.

---

## Appendix: Algorithm - Code Mapping Table

| Algorithm No. | Algorithm Name | Source Location | Key Functions/Classes |
|:--------:|---------|---------|------------|
| Algorithm 1 | Logic-Driven Test Planning | [src/agents/planner.py](../src/agents/planner.py) | `PlannerAgent.plan()` |
| Algorithm 2 | Error Classification (rule matching) | [src/agents/error_classifier.py](../src/agents/error_classifier.py) | `ErrorClassifier.classify()` |
| Algorithm 3 | Iterative Repair Loop | [src/graph/workflow.py](../src/graph/workflow.py) | `_should_debug()` + conditional routing edges |
| Patch Application | Patch written to original file | [src/tools/patch_applier.py](../src/tools/patch_applier.py) | `apply_patch_to_code()` |
| Cross-file repair (3.5, off by default) | Cross-file dependency analysis + multi-file patches | [src/tools/cross_file.py](../src/tools/cross_file.py) + [src/graph/workflow.py](../src/graph/workflow.py) `cross_file_analyzer` node (inserted between executor→debugger) | `analyze_cross_file_deps()` / `build_cross_file_repair_plan()` / `apply_multi_file_patch()` / `cross_file_fallback_single_file()` |
| RAG Retrieval | Vector similarity retrieval | [src/rag/retriever.py](../src/rag/retriever.py) | `TestCaseRetriever` |
| Batch Experiments | Benchmark execution | [experiments/run_benchmark.py](../experiments/run_benchmark.py) | `run_benchmark()` |
| Data contamination detection (2.1) | Token-level Jaccard overlap of generated vs. golden patches | [experiments/contamination_check.py](../experiments/contamination_check.py) | `patch_overlap_score()` / `detect_contamination()` / `render_contamination_section()` |
| Task difficulty stratification (2.2) | Stratify by code_size / dependency_count / complexity_proxy | [experiments/difficulty_stratification.py](../experiments/difficulty_stratification.py) | `stratify_by_dimension()` / `render_stratification_section()` |
| Docker isolated execution (4.3) | Run pytest inside a container via the docker CLI | [src/agents/executor.py](../src/agents/executor.py) | `ExecutorAgent._execute_docker()` |
| Dependency cache monitoring (4.4) | venv cache hit-rate statistics + cleanup | [src/tools/dependency.py](../src/tools/dependency.py) | `get_venv_cache_stats()` / `list_venv_cache()` / `clear_venv_cache()` |

---

## 1. System Overview

AITester is a Python automated test generation and self-repair system based on multi-agent collaboration.

The system consists of four core agents, with responsibilities as follows:

| Agent | Responsibility | Calls LLM |
|:------:|------|:------------:|
| **PlannerAgent** | Performs logical analysis of the target function and outputs a structured test plan | ✅ Yes |
| **GeneratorAgent** | Generates runnable pytest code based on the test plan | ✅ Yes |
| **ExecutorAgent** | Executes tests in an isolated environment and captures output and coverage | ❌ No |
| **DebuggerAgent** | Analyzes failure causes and generates layered repair patches | ✅ Yes |

The system's overall workflow is a directed graph (orchestrated by LangGraph), supporting looped repair paths and ablation experiment switches.

---

## 2. Logic-Driven Chain-of-Thought Algorithm (Algorithm 1)

### 2.1 Problem Modeling

Let the function under test be $f: D_{in} \rightarrow D_{out}$, where $D_{in}$ is the input domain and $D_{out}$ is the output range.

**Objective**: Generate a test set $\mathcal{T} = \{t_1, t_2, \ldots, t_n\}$ such that each $t_i$ corresponds to a logical branch or boundary condition of $f$, and $\bigcup_i \text{coverage}(t_i) \geq \theta$ (coverage threshold, default 80%).

### 2.2 Algorithm Steps

```
Algorithm 1: Logic-Driven Test Planning
Input:  source code S, target function f (optional, None means analyze all functions)
Output: test plan P = (LA, TC), where LA is the logic analysis and TC is the list of test cases

1:  LA ← LLM_Analyze(S, f)          // Logic analysis: input domain, output range, pre/postconditions, edge cases
2:  TC ← []                          // Initialize empty test case list
3:  for each pre-condition pc in LA.preconditions do
4:      TC.append(TestCase(pc, category="normal"))   // Precondition → normal input case
5:  end for
6:  for each post-condition pc in LA.postconditions do
7:      TC.append(TestCase(pc, category="normal"))   // Postcondition → normal input case
8:  end for
9:  for each edge-case ec in LA.edge_cases do
10:     cat ← "boundary" if ec involves a boundary value else "error"  // boundary or error
11:     TC.append(TestCase(ec, category=cat))
12: end for
13: return P = (LA, TC)
```

### 2.3 Complexity Analysis

- **Time complexity**: $O(k \cdot C_{LLM})$, where $k=5$ is the number of logic analysis dimensions and $C_{LLM}$ is the cost of a single LLM call.
- **Space complexity**: $O(|S| + |P|)$, storing the source code and structured test plan.

### 2.4 Implementation Notes

- Code location: [src/agents/planner.py](../src/agents/planner.py)
- The System Prompt is defined in `PLANNER_SYSTEM_PROMPT` in [src/prompts/templates.py](../src/prompts/templates.py)
- If the LLM does not return a `logic_analysis` field (compatibility fallback), empty values are filled in automatically to avoid downstream crashes

---

## 3. Layered Error Repair Protocol (Algorithms 2 & 3)

### 3.1 Error Classifier (Algorithm 2)

Define the error type enumeration $\mathcal{E} = \{\text{SYNTAX}, \text{RUNTIME}, \text{ASSERTION}, \text{TIMEOUT}, \text{UNKNOWN}\}$.

The classification function $C: \text{TestOutput} \rightarrow \mathcal{E}$ uses **rule matching** (regular expressions), ensuring $O(1)$ classification time without consuming LLM tokens.

```
Algorithm 2: Error Classification (rule matching)
Input:  test output text O, list of failed cases F
Output: error category e ∈ E

1:  combined ← O ⊕ concat(F[*].error)    // Concatenate output text with failed case error messages
2:  if matches(combined, SYNTAX_PATTERNS) then return SYNTAX
3:  if matches(combined, RUNTIME_PATTERNS) then return RUNTIME
4:  if matches(combined, ASSERTION_PATTERNS) then return ASSERTION
5:  if matches(combined, TIMEOUT_PATTERNS) then return TIMEOUT
6:  return UNKNOWN                        // Fallback category
```

**Regular expression pattern definitions** (see [src/agents/error_classifier.py](../src/agents/error_classifier.py)):
- `SYNTAX_PATTERNS`: compile-time errors such as SyntaxError, ImportError, ModuleNotFoundError, etc.
- `RUNTIME_PATTERNS`: runtime exceptions such as ZeroDivisionError, TypeError, KeyError, IndexError, etc.
- `ASSERTION_PATTERNS`: AssertionError, assert statements, Expected...but got, etc.
- `TIMEOUT_PATTERNS`: timeout, TimedOut, Test ran for longer than, etc.

### 3.2 Layered Repair Strategies

Each error type $e \in \mathcal{E}$ corresponds to a unique differentiated repair strategy $Strat(e)$:

| Error Type | Repair Strategy | LLM Call Mode |
|:--------:|---------|:------------:|
| SYNTAX | Rewrite the complete file (syntax/import repair) | Directly output the complete file |
| RUNTIME | Locate the exception stack and fix the specific function logic | Output the complete repaired file |
| ASSERTION | Determine whether it is a code logic error or a wrong test expected value | Output repair patches per case |
| TIMEOUT | Check loop/recursion conditions and add exit logic | Output the complete repaired file |
| UNKNOWN | Perform general analysis and decide autonomously | Output repair patches |

### 3.3 Iterative Repair Loop (Algorithm 3)

```
Algorithm 3: Iterative Repair Loop
Input:  original source code S, maximum iteration count K
Output: repaired source code S', whether tests pass (bool)

1:  S_current ← S                          // Start from the original code
2:  for i ← 1 to K do
3:      T ← Generator(S_current)           // GeneratorAgent generates test code
4:      (passed, output, failed_cases) ← Executor(T, S_current)
5:      if passed then return (S_current, true)   // Tests pass, early termination
6:      e ← Classifier(output, failed_cases)   // ErrorClassifier classifies the error
7:      patch ← Debugger(S_current, output, e)  // DebuggerAgent generates a repair patch
8:      S_current ← ApplyPatch(S_current, patch) // PatchApplier applies the patch
9:  end for
10: return (S_current, false)               // Reached maximum iterations without passing
```

**Implementation location**: `_should_debug()` in [src/graph/workflow.py](../src/graph/workflow.py) controls the routing condition.

> **3.5 Cross-file extension path** (enabled when `CROSS_FILE_ENABLE=true`, off by default): a `cross_file_analyzer` node (`_cross_file_analyzer_node`) is inserted between `executor` and `debugger`, performing AST cross-file import dependency analysis and writing the dependency edges into `state["cross_file_deps"]`; `_patch_applier_node` applies patches to multiple modules in topological order in the cross-file branch (callee modified first, caller second); if any file fails, `cross_file_fallback_single_file()` degrades to applying the patch only to the entry module (with the same semantics as single-file `safe_apply_patch`). See [docs/design/cross_file_repair.md](design/cross_file_repair.md) for details.

---

## 4. Multi-Agent Collaboration Protocol

### 4.1 State Transition Diagram

The system state space $\mathcal{S}$ is defined by the TypedDict `AITesterState` (see [src/graph/state.py](../src/graph/state.py)), containing the following key fields:

```
task_uuid ─▶ target_file ─▶ target_code
                     │
                     ▼
               test_plan ─▶ generated_test ─▶ test_passed
                                           │
                               ┌───────────┼───────────┐
                               │           │           │
                            passed?      failed     max_iter?
                               │           │           │
                               ▼           ▼           ▼
                              END     Debugger ─▶ PatchApplier ─┘
```

### 4.2 Ablation Experiment Configuration Matrix

Boolean switches control node enablement/disabling, forming 4 experiment variants (configuration in [config.py](../config.py)):

| Variant | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | Corresponding Baseline |
|:----:|:--------------:|:---------------:|:----------:|---------|
| Full system | true | true | false | AITester |
| No Planner | false | true | false | No-planning baseline |
| No Debugger | true | false | false | No-repair baseline |
| Plain LLM | false | false | false | plain_llm |
| Single agent | — | — | — | single_agent |

---

## 5. Theoretical Correctness Notes

### Theorem 1 (Completeness)

If the function under test $f$ has a repairable bug and the LLM has sufficient capability, the probability that the algorithm converges to a state where all tests pass within $K$ iterations is $p > 0$.

**Proof**: Each Debugger call provides a targeted repair strategy based on error classification, covering the four known pattern classes SYNTAX/RUNTIME/ASSERTION/TIMEOUT. For the UNKNOWN class, the LLM performs general analysis. Since the LLM output space contains correct repair solutions (assuming the model is capable enough), there exists a path from the initial state to the success state. ∎

### Theorem 2 (Termination)

The algorithm guarantees termination after $K$ iterations and will not loop infinitely.

**Proof**: The loop upper bound is controlled by `MAX_ITERATIONS` (default 3), and each iteration executes a fixed node sequence (Generator → Executor → Debugger → PatchApplier), with no recursive self-calls. ∎

---

## 6. Comparison with Existing Methods

| Method | Logic Planning | Layered Repair | RAG Augmentation | Ablation Experiments |
|:---:|:-------:|:-------:|:-------:|:-------:|
| Pynguin (traditional tool) | ✗ | ✗ | ✗ | ✗ |
| Direct single LLM call | ✗ | ✗ | ✗ | ✗ |
| Single-agent system | ✗ | Partial | ✗ | ✗ |
| **AITester (this system)** | ✅ | ✅ | ✅ (optional) | ✅ |

---

## 7. Dataset Loading Architecture

```
load_dataset(name, data_dir=None)
├── "examples" / "in_memory"   → InMemoryDataset (3 predefined bug tasks, no download required)
├── "swe_bench" / "swebench"   → SWEBenchDataset (reads from ~/.cache/aitester/swe_bench/,
│                                 supports automatic download from HuggingFace: download_from_huggingface())
├── "swe_rebench" / "swebench_rebench" → SWEBenchDataset (2.1 anti-contamination benchmark,
│                                 data_dir points at the SWE-rebench data directory; fields are isomorphic to SWE-bench)
├── "defects4j_python" / "d4j_py" → Defects4JPYDataset (parsed from a local directory)
├── "synthetic" / "synth"      → SyntheticDataset (generated locally, supports custom scale)
└── other names                → InMemoryDataset (graceful degradation, no crash)
```

Each task is unified into the `BenchmarkTask` data structure (defined in [src/datasets/dataset_loader.py](../src/datasets/dataset_loader.py)):

| Field | Type | Description |
|-----|------|------|
| `task_id` | str | Unique identifier, e.g. `examples__calculator_divide` |
| `repo_name` | str | Name of the repository/module it belongs to |
| `problem_statement` | str | Bug description |
| `instance_code` | str | The buggy original code |
| `test_code` | str | Reference test code |
| `expected_pass_count` | int | Minimum number of tests expected to pass |
| `total_test_count` | int | Total number of test cases |
| `metadata` | dict | Additional metadata (source, bug type, etc.) |
