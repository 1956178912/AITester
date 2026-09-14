> **Language**: [中文版](cross_file_repair.md) | English (this document)

# 3.5 Cross-File Repair Capability Design Document

> Kickoff date: 2026-09-14
> Status: **Implemented** (commit 670f368, off by default `CROSS_FILE_ENABLE=false`; §3 below has 3 deviations from the implementation, see §5 deviation notes)
> Related list: Improvement list 3.5
> Prerequisite dependency: 3.1 Multi-candidate patches (`multi_candidate.py` already landed)

## 1. Background and Goals

### 1.1 Current State

The current system assumes "repair happens only within the single `target_file`":

- `patch_applier.py` applies patches on a single-file basis (`apply_patch_to_code(original_code, patch)`);
- `ExecutorAgent` only runs pytest for `target_file` inside the sandbox;
- Candidate screening in `multi_candidate.py` is also single-file scoped;
- `extract_import_module_names` in `dependency.py` can already recognize cross-file imports (top-level module names), but it is not used for repair planning.

### 1.2 Problem

In real datasets (SWE-bench / Defects4J), **about 40% of tasks require multi-file changes** (e.g.:

- Fixing a function in file A requires synchronously updating the caller in file B;
- Changing a shared library interface requires updating N callers;
- When fixing test cases, the mock dependencies of the code under test must be fixed synchronously.

The single-file assumption guarantees that this kind of task must fail under the current architecture: the Debugger can only see `target_code` (the content of a single file) and cannot diagnose cross-file dependencies.

### 1.3 Goals

- Support "multi-file patches" at the `patch_applier` layer (one patch fragment per file);
- Add a new `CrossFileAnalyzer` node at the `workflow` layer (optional, off by default) that performs AST dependency analysis on the code under test and produces a "cross-file repair plan";
- Inject cross-file context into the `DebuggerAgent` prompt so that the LLM is aware that "modifying function X affects file Y";
- Extend candidate screening in `multi_candidate.py`: statically validate the patch for each file, while execution validation still reuses the single-file path (cross-file execution validation is left for phase two).

Success criteria (measurable):
- Construct 3 synthetic tasks in `examples/` containing cross-file bugs (a function in file A has a bug, file B calls A, and the repair requires changing A + synchronously changing B);
- When `CROSS_FILE_ENABLE=true` is enabled, the task pass rate is significantly higher than before;
- Do not change the default value of `CROSS_FILE_ENABLE` (false), so the criteria of historical experiments remain unchanged.

## 2. Approach Comparison

### Approach A: Coordinator-Proposer Architecture (PhoenixRepair idea)

- A "coordinator" node analyzes cross-file dependencies and produces a repair plan (which files to change, what to change in each file);
- Multiple "proposer" nodes (one per file) generate patches in parallel;
- The coordinator aggregates them and hands them to the existing `patch_applier` for application.

Pros: clear architecture, easy to integrate with the existing `planner → generator → executor → debugger → patch_applier` five-node graph; extensible to N files; parallelism between proposers saves time.

Cons: high complexity — the coordinator must implement the "cross-file dependency graph + repair plan" data structures; patch conflicts between proposers need arbitration by the coordinator.

### Approach B: Pure LLM End-to-End (put all multi-file content into the prompt)

- In the Debugger node, feed "target_code + the content of all related files" to the LLM together;
- The LLM directly outputs a multi-file diff.

Pros: simple implementation (only the prompt needs changing).

Cons: token cost explosion (cross-file scenarios in large projects); the LLM context window may not fit; static screening is not possible (multi-file candidate screening is expensive).

### Final Choice: Approach A (Coordinator-Proposer Architecture)

Reasons:

1. Cross-file dependency analysis is done with AST (deterministic, low-cost), which is more reliable than letting the LLM directly "guess";
2. Proposers generate in parallel, keeping token cost under control;
3. It can reuse the "candidate screening + execution validation" mechanism of the existing `multi_candidate.py`;
4. Phase two can extend to "dependency graph + topological sort + batched repair".

## 3. Final Approach

### 3.1 Data Structures

New file `src/tools/cross_file.py`:

```python
@dataclass
class CrossFileDependency:
    """Cross-file dependency edge: module_a calls symbol_b in module_b."""

    source_module: str  # Caller module name (without .py)
    target_module: str  # Callee module name
    symbol: str  # The called function/class name
    call_line: int  # Line number in the caller source
    context: str  # Call-site context (for the LLM to understand)


@dataclass
class CrossFileRepairPlan:
    """Cross-file repair plan."""

    plan_id: str
    target_modules: list[str]  # List of modules that need to be modified
    per_module_patches: dict[str, str]  # Module name → patch text
    dependency_edges: list[CrossFileDependency]  # Dependency relations
    estimated_token_cost: int  # Estimated token cost


def analyze_cross_file_deps(
    entry_module: str,
    source_files: dict[str, str],
) -> list[CrossFileDependency]:
    """AST analysis of the dependency relations between the entry module and other modules."""


def build_cross_file_repair_plan(
    deps: list[CrossFileDependency],
    debugger: "DebuggerAgent",
    target_code: str,
    test_output: str,
    failed_cases: list[dict[str, str]],
    focus_function: str | None = None,
    target_module: str | None = None,
    max_modules: int | None = None,
) -> CrossFileRepairPlan:
    """Generate a multi-file repair plan based on the dependency graph + LLM (coordinator-proposer architecture:
    one proposer per module, reusing the existing DebuggerAgent call path; the actual signature
    includes target_code / test_output / failed_cases context parameters, see the §5 deviation notes)."""
```

### 3.2 Workflow Integration Point

In `workflow.py`, insert an optional `_cross_file_analyzer_node` before `_debugger_node` (enabled when `CROSS_FILE_ENABLE=true`):

```
... executor → (cross_file_analyzer →) debugger → patch_applier ...
```

- `cross_file_analyzer` node: calls `analyze_cross_file_deps` and writes the result into `state["cross_file_deps"]`;
- When cross-file mode is enabled, `_debugger_node` appends "the following files may need to be modified synchronously" to the prompt;
- When cross-file mode is enabled, `_patch_applier_node` takes the "multi-file patch application" branch (calling `apply_multi_file_patch`, new).

### 3.3 Multi-File Patch Application

New in `src/tools/cross_file.py` (note: the implementation lives in `cross_file.py` rather than the designed `patch_applier.py`, see the §5 deviation notes):

```python
def apply_multi_file_patch(
    original_files: dict[str, str],  # Module name → original code
    patches: dict[str, str],  # Module name → patch
    entry_module: str,
) -> tuple[dict[str, str], bool]:
    """Apply patches to multiple files at the same time.

    Strategy: apply in the topological order of the dependency graph
    (callee modified first, caller second); if any file fails to apply,
    roll back to the original code (with the same semantics as single-file safe_apply_patch).
    """


def cross_file_fallback_single_file(
    original_files: dict[str, str],
    patches: dict[str, str],
    entry_module: str,
) -> tuple[dict[str, str], bool]:
    """3.5 Single-file degradation: when the cross-file multi-file application fails,
    apply the patch only to the entry module (with the same semantics as single-file
    safe_apply_patch), guaranteeing "a cross-file failure is no worse than single-file"."""
```

### 3.4 Configuration Switches

New in `config.py`:

```python
# 3.5 Cross-file repair: off by default, preserving the historical single-file criteria
CROSS_FILE_ENABLE: bool = os.getenv("CROSS_FILE_ENABLE", "false").lower() == "true"
# Maximum module count for cross-file dependency analysis (prevents LLM context explosion, default 5)
CROSS_FILE_MAX_MODULES: int = int(os.getenv("CROSS_FILE_MAX_MODULES", "5"))
```

### 3.5 Compatibility Impact

- `CROSS_FILE_ENABLE=false` (default): behavior of all paths is unchanged;
- `CROSS_FILE_ENABLE=true`: the project containing `target_file` must have parseable multi-file source; single-file projects automatically degrade to single-file mode;
- A new field `cross_file_files: list[str]` is appended to `repair_history` (records the module names involved in this repair round).

## 4. Testing Strategy

### 4.1 Unit Tests

`tests/test_cross_file.py` (new):

| Case Group | Coverage Points |
|--------|--------|
| `test_analyze_deps` | Cross-file import / call recognition is correct |
| `test_build_plan` | Repair plan structure is complete, token cost estimate is reasonable |
| `test_apply_multi_file_patch` | Multi-file patch application succeeds / partial failure rolls back |
| `test_topological_order` | Callee modified first, caller second |
| `test_single_file_fallback` | Degrades when `CROSS_FILE_ENABLE=true` but only a single file exists |
| `test_workflow_integration` | End-to-end: a cross-file bug passes with `CROSS_FILE_ENABLE=true` |

### 4.2 Integration Tests

Construct 3 synthetic tasks in `experiments/results/`:
- `task_1.py` + `task_2.py`: A has a bug, B calls A (the repair requires synchronizing B);
- `task_3.py` + `task_4.py` + `task_5.py`: a three-file dependency chain;
- Verify the pass-rate difference before and after enabling `CROSS_FILE_ENABLE`.

## 5. Rollback Plan

- Off by default (`CROSS_FILE_ENABLE=false`); without enabling it, there is zero behavior change;
- If the repair success rate drops after enabling, just `git revert` the cross-file node wiring (the node code is kept; with the switch off it simply does not run).

## 6. Phase Two Extensions (Out of Scope This Time)

- Cross-file execution validation (currently only single-file candidate execution validation is supported);
- Extending candidate screening in `multi_candidate.py` (statically validate the patch for each file; cross-file execution validation is left for phase two and was not implemented this time);
- Dependency graph visualization (`dot` output);
- Repair plan caching (reuse LLM generation results for the same dependency graph);
- Integration with RAG (cross-file repair cases entered into the knowledge base).

## 7. Implementation Deviation Notes (Design vs. Implementation, commit 670f368)

| Design (§3) | Implementation (src/tools/cross_file.py + workflow.py) | Reason for Deviation |
|------------|----------------------------------------------|----------|
| `build_cross_file_repair_plan(deps, debugger)` | The actual signature adds three required context parameters `target_code` / `test_output` / `failed_cases` plus optional parameters `focus_function` / `target_module` / `max_modules` | The coordinator needs full context (original code + test output + failed cases) to generate the repair plan, which was not listed at design time |
| `apply_multi_file_patch` lives in `patch_applier.py` | It actually lives in `src/tools/cross_file.py` | Multi-file patching and cross-file dependency analysis both belong to the 3.5 capability; centralizing them in cross_file.py avoids spreading responsibility into patch_applier.py; single-file `safe_apply_patch` remains in patch_applier.py unchanged |
| Single-file fallback not mentioned | The implementation adds `cross_file_fallback_single_file()`: when the cross-file multi-file application fails, only the patch for the entry module is applied | Guarantees "a cross-file failure is no worse than single-file", consistent with the 3.5 compatibility criteria |

> The data structures (`CrossFileDependency` / `CrossFileRepairPlan`) and the configuration switches (default values of `CROSS_FILE_ENABLE` / `CROSS_FILE_MAX_MODULES`) are **field-by-field / default-value-by-default-value consistent** between design and implementation, with no deviations.
