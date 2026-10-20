> Last updated: 2026-10-19 (Z-round third-party review F15/F16: the red_not_repaired detection semantics is corrected to "protocol-layer mechanism state that does not by itself constitute a valid detection"; title and opening repositioned per ADR-0016 as a detection-first protocol plus ablatable orchestration container)

> **Language**: [中文版](algorithm_design.md) | English (this document)

# Detection-First Test Generation and Repair-Attribution Evaluation Protocol (Algorithm Design Document)

> This document describes the core algorithm design and theoretical framework of AITester, for technical review and code review reference.
> The appendix provides a precise mapping table from algorithms to source code, to help locate implementation details quickly.
>
> **Baseline numbers**: treat the repo-root [BASELINE.yaml](../BASELINE.yaml) as the single
> source of truth (refreshed after each batch lands); this document no longer embeds
> baseline numbers, avoiding stale snapshots. Historical trajectory: see `CHANGELOG.md`
> entries and `docs/history/`.

---

## Appendix: Algorithm - Code Mapping Table

| Algorithm No. | Algorithm Name | Source Location | Key Functions/Classes | Related ADR |
|:--------:|---------|---------|------------|---------|
| Algorithm 1 | Logic-Driven Test Planning | [src/agents/planner.py](../src/agents/planner.py) | `PlannerAgent.plan()` | 0001 |
| Algorithm 2 | Error Classification (rule matching + confidence layering) | [src/agents/error_classifier.py](../src/agents/error_classifier.py) | `ErrorClassifier.classify()` / `classify_with_confidence()` | 0002 |
| Algorithm 3 | Iterative Repair Loop | [src/graph/workflow.py](../src/graph/workflow.py) | `_should_debug()` + conditional routing edges | 0001, 0005 |
| Patch Application | Patch written to original file | [src/tools/patch_applier.py](../src/tools/patch_applier.py) | `apply_patch_to_code()` | 0003, 0005 |
| Cross-file repair (3.5, off by default) | Cross-file dependency analysis + multi-file patches | [src/tools/cross_file.py](../src/tools/cross_file.py) + [src/graph/workflow.py](../src/graph/workflow.py) `cross_file_analyzer` node (inserted between executor→debugger) | `analyze_cross_file_deps()` / `build_cross_file_repair_plan()` / `apply_multi_file_patch()` / `cross_file_fallback_single_file()` | 0003 |
| RAG Retrieval | Vector similarity retrieval | [src/rag/retriever.py](../src/rag/retriever.py) | `TestCaseRetriever` | 0004 |
| Batch Experiments | Benchmark execution | [experiments/run_benchmark.py](../experiments/run_benchmark.py) | `run_benchmark()` | 0001 |
| Data contamination detection (2.1) | Token-level Jaccard overlap of generated vs. golden patches | [experiments/contamination_check.py](../experiments/contamination_check.py) | `patch_overlap_score()` / `detect_contamination()` / `render_contamination_section()` | — |
| Task difficulty stratification (2.2) | Stratify by code_size / dependency_count / complexity_proxy | [experiments/difficulty_stratification.py](../experiments/difficulty_stratification.py) | `stratify_by_dimension()` / `render_stratification_section()` | — |
| Docker isolated execution (4.3) | Run pytest inside a container via the docker CLI | [src/agents/executor.py](../src/agents/executor.py) | `ExecutorAgent._execute_docker()` | 0005 |
| Dependency cache monitoring (4.4) | venv cache hit-rate statistics + cleanup | [src/tools/dependency.py](../src/tools/dependency.py) | `get_venv_cache_stats()` / `list_venv_cache()` / `clear_venv_cache()` | 0003 |
| Convergence failure-mode attribution (1.2) | Distinguishes "cannot pinpoint root cause" vs "cannot produce an effective patch" | [experiments/analyze_results.py](../experiments/analyze_results.py) | `_convergence_failure_modes()` | — |
| Boundary case coverage (1.3) | AST conservative check of generated_test for boundary-condition coverage | [experiments/analyze_results.py](../experiments/analyze_results.py) | `_boundary_case_coverage()` | — |
| Mutation score (1.3) | Collects details[].mutation_score (produced by an external mutation tester) | [experiments/analyze_results.py](../experiments/analyze_results.py) | `_mutation_score_metrics()` | — |
| Execution feedback trace (3.2) | Appends passed/coverage_delta/elapsed/reward_signals on every execution | [src/graph/state.py](../src/graph/state.py) + [src/graph/nodes.py](../src/graph/nodes.py) | `_record_execution_trace()` / `state.execution_trace` | 0001, 0005 |
| Spectral fault localization (O2, on by default) | Ochiai Top-k line-level suspiciousness ranking (zero LLM), Top-k section injected into the Debugger prompt | [src/agents/fl_spectral.py](../src/agents/fl_spectral.py) | `measure_fl_spectral_focus()` / `compute_ochiai_scores()` / `rank_top_k()` / `build_fl_spectral_prompt_section()` | — |
| RGFL reasoning fault localization (repair-engine phase one, on by default) | Spectral Top-k corroboration + LLM structured localization [function/line range/confidence], gold diff→AST function-level hit adjudication | [src/agents/fault_localizer.py](../src/agents/fault_localizer.py) | `FaultLocalizerAgent.localize()` / `gold_changed_functions()` / `localization_hit()` / `build_localization_prompt_section()` | 0017 |

---

## 1. System Overview

AITester is a Python test-generation and self-repair system / evaluation protocol built around the detection-first protocol, with multi-agent orchestration positioned as an ablatable container (`docs/adr/0016-orchestration-container-repositioning.md`).

The system consists of five core agents, with responsibilities as follows:

| Agent | Responsibility | Calls LLM |
|:------:|------|:------------:|
| **PlannerAgent** | Performs logical analysis of the target function and outputs a structured test plan | ✅ Yes |
| **GeneratorAgent** | Generates runnable pytest code based on the test plan | ✅ Yes |
| **ExecutorAgent** | Executes tests in an isolated environment and captures output and coverage | ❌ No |
| **DebuggerAgent** | Analyzes failure causes and generates layered repair patches | ✅ Yes |
| **FaultLocalizerAgent** | RGFL-style LLM reasoning fault localization (localization only, no repair; repair-engine phase one; inline-invoked by the `debugger` node, not a standalone graph node) | ✅ Yes |

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

### 2.5 Spec-Oracle Compilation and Side-by-Side Execution (2026-10-05 review batch R1)

Machine-executable compilation of the logic analysis (LA) happens in two layers (previously LA existed only as prompt-injected material with no executable spec-side artifact):

1. **Boundary parametrize layer (v1, `src/specs/spec_ir.py::compile_to_hypothesis`)**: SpecIR `boundaries` (deterministic boundary anchors, input/expected pairs) compile into `@pytest.mark.parametrize` assertions; NL pre/post/invariant clauses produce no tests (R1a fix: the historical version emitted `assert True` tautologies for invariants — a fake-pass channel, now sealed; empty string when no boundary material).
2. **Restricted-expression DSL layer (v2, `src/specs/spec_ir_v2.py::compile_spec_oracle`)**: expression-shaped clauses such as `r == x * 2` pass whitelist AST validation (11 pure-function call names + attribute whitelist + node-type restrictions) and compile into `assert <expr>`; non-mechanizable clauses degrade to NL provenance comments. **Signature-aware binding (R1b)**: `extract_signature_params` extracts real parameter names from the target function's AST signature (tri-state: None = not found, degrade; [] = zero params; non-empty = per signature); the binding context extends from the hardcoded `{r,x,a,b,y}` to the real parameter set, and call arity is fixed per signature.
3. **Side-by-side execution wiring (R1c, `SPEC_ORACLE_EXEC_ENABLE`, default off)**: `_generator_node` appends the v2 compilation output to the tail of the LLM-generated tests via `_append_spec_oracle_to_test` so both run **side by side** — LLM tests passing ≠ the spec oracle passing; the oracle's failure on the **buggy** side is only a **one-sided signal** and **does not constitute a "deterministic detection" verdict**: detection must be adjudicated independently by the evaluation layer under the two-sided criterion (red on buggy ∧ green on gold-fixed/repaired code ∧ no collection/syntax errors on either side, i.e. the F2P caliber); one-sided failures serve only as mechanism observations / attribution clues (the evaluation layer must not count them as detection; since N-3 the oracle is judged separately via `oracle_suite_verdict`). Observation field `state["spec_oracle_injected"]`. Enable via the single switch or one-shot via `AITESTER_PROFILE=scientific`.

**Compilation-rate observation**: `spec_compile_rate` (compilable clauses / non-empty clauses) quantifies how much of "logic-driven" is actually mechanized (written to state by the Planner node when `SPEC_IR_DSL_ENABLE=true`).

---

## 3. Layered Error Repair Protocol (Algorithms 2 & 3)

> **Repair-engine paradigm (2026-10-07 batch I paradigm shift)**: the repair pipeline is upgraded to the three stages "**localization → synthesis → verification**", with localization promoted from a Debugger by-product to an independently quantifiable first stage. Localization uses **dual-channel fusion**:
> 1. **Spectral channel** (zero LLM): Ochiai spectral Top-k line-level suspiciousness ranking (`FL_SPECTRAL_ENABLE`, true by default), injected into the prompt as objective corroboration;
> 2. **Reasoning channel** (LLM): RGFL-style structured localization (`FAULT_LOCALIZER_ENABLE`, true by default) — fed the line-numbered source + failing test + error output + spectral Top-k corroboration, it outputs `{function_name, line_start, line_end, confidence, reasoning}`, **localizing without repairing**; LLM failure / JSON parse failure degrade conservatively to None — no fabricated localization, no blocking of repair.
>
> The fusion wiring lives in `_debugger_node`: the localization result is written to `state["llm_localization"]` and injected into the Debugger prompt side by side with the spectral section via `build_localization_prompt_section()`. Localization quality is quantified by standalone metrics: `localization_hit_function` (the LLM-localized function ∈ the gold changed-function set, function level) and `fl_at_k` (spectral line-level Top-k hit), output alongside detection / repair rates.

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

> **Protocol note (current ADR-0015 / ADR-0016 caliber, synced 2026-10-18)**: this algorithm is rewritten under the **detection-first ("red before green")** protocol. The historical version (each iteration `T ← Generator(S_current)`, success as soon as `passed`) is inconsistent with the current implementation and the ADRs, and has been corrected per ADR-0015 (detection-first protocol) and ADR-0016 (orchestration as an ablatable container + the **test-file locking principle**). The protocol switches are off by default (ADR-0003 zero-default-behaviour-change principle); the `AITESTER_PROFILE=logic` profile injects `DETECTION_FIRST_ENABLE=true` plus both gates — with the switches off, the historical "all-green first round ends the run" caliber applies and the terminal fields are `None` (key-set isomorphic).

```
Algorithm 3: Detection-First Iterative Repair Loop (red before green)
Input:  original buggy code S₀; maximum repair iterations K; regeneration budget R (_MAX_REGENERATIONS)
Output: repaired code S'; whether detected (detection); whether repaired (repair);
        terminal label status ∈ {red_then_green, all_green_unverified, red_not_repaired}

1:  S_current ← S₀ ; red_seen ← false ; status ← None
2:  T ← Generator(S₀)                     // tests are generated before the repair loop and locked inside it
3:  (passed, output, failed_cases) ← Executor(T, S₀)   // first-round baseline execution (unrepaired code)
4:  if passed then                         // all-green first round = no defect detected → not success
5:      T ← RegenerateStrengthened(T, ≤R)  // red-before-green strengthening prompt; capped by R
6:      if still all green then return (S₀, detection=false, repair=false, all_green_unverified)
7:  if first round red then
8:      red_seen ← true ; T* ← T            // red-witness snapshot (the locked test)
9:      if specificity gate on then
10:         v ← ExecuteOnGoldFixed(T)       // in-loop two-sided control: gold-fixed side must turn green
11:         if v == over_red then T ← Regenerate(T, ≤R) ; goto 3  // over-red → replace with defect-specific test, no repair loop
12: for i ← 1 to K do
13:     e ← Classifier(output, failed_cases)          // ErrorClassifier (Algorithm 2)
14:     patch ← Debugger(S_current, output, e)        // generates source-repair patches only
15:     S_current ← ApplyPatch(S_current, patch)      // PatchApplier; roll back on failure
16:     (passed, output, failed_cases) ← Executor(T, S_current)
17:     if passed then
18:         red-regression gate (if on): if T was regenerated/replaced and S_current is unpatched → T ← T*, mark failed, continue
19:         status ← red_seen ? red_then_green : all_green_unverified
20:         return (S_current, detection=red_seen, repair=red_seen, status)
21: end for
22: status ← red_seen ? red_not_repaired : all_green_unverified
23: return (S_current, detection=red_seen, repair=false, status)
```

**Success calibers ("passed" alone is not success)**:

- **Detection — two-sided criterion**: F2P = the generated test is red on the original buggy code **∧** green on the gold-fixed (or repaired) code **∧** no collection/syntax/execution errors on either side; red on the buggy side alone (one-sided) is only a mechanism signal and is not counted as detection.
- **Repair — two-sided criterion**: the protocol loop requires "a red witness exists (the defect was detected) **∧** the patched code is all green"; the evaluation layer's `repair_rate` is adjudicated independently against **gold material** — a repair counts only when the gold tests are all green on the **final code with the patch actually written** (no patch written → 0.0; unmeasurable → None). `all_green_unverified` (never red, yet all green = weak-test false success) **must not be counted as detection/repair success by the evaluation layer**; `red_not_repaired` (red was observed and the defect was not repaired) is only a **protocol-layer mechanism state** (`detection=red_seen` in the pseudocode is likewise a protocol-layer signal) and **does not by itself constitute a valid detection** — valid detection is always adjudicated by the evaluation layer's independent three-part F2P criterion (red on buggy **∧** green on fixed **∧** no execution errors); the 88 main-batch `red_not_repaired` rows whose buggy/fixed sides are both red (over-red, failing F2P) are the counter-example (`detection=0`) and must not be re-counted as detections to fit the text.
- **Test locking / no green by swapping tests**: inside the repair loop the test `T` is locked; regeneration is allowed only through three dedicated routes bounded by `R` (all-green first round, specificity gate `over_red`, diagnosis-reported test defect). The red-regression gate detects "previously red + test regenerated + source unpatched", restores the red-witness test and hands control back to the repair-the-source channel — the mechanism guarantee for ADR-0016 decision 4 ("the repair loop must not reach green by swapping tests").
- **Switches and defaults**: `DETECTION_FIRST_ENABLE` / `DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE` are all off by default (ADR-0003); the logic profile and explicit experiment batches enable them. With them off, the historical caliber is byte-identical.

**Implementation location**: routing in `_should_debug()` in [src/graph/workflow.py](../src/graph/workflow.py); first-round red observation / terminal labeling in `_executor_node` in [src/graph/nodes.py](../src/graph/nodes.py) (`_derive_detection_first_status` derives the three values from `(passed, red_seen)`); both gates in [src/tools/detection_gates.py](../src/tools/detection_gates.py).

> **Routing-signal priority (2026-10-05 review batch R17)**: when `ROUTE_STRUCTURED_ENABLE=true` (default off), the "test-generation error" routing signal uses a **structured-first, keyword-fallback** policy — `error_category=logic_error` (classified from the failure stack: an assertion failure whose stack never touches the module under test, i.e., a test-side logic error) takes priority over Chinese diagnosis-keyword matching (`_test_gen_signal_hit`); the signal source (`structured_error_category` / `diagnosis_keyword`) is written to trace, making the keyword-fallback rate measurable. Motivation: keyword matching relies on LLM diagnosis text and was misled by source-code exception signatures (AttributeError/NameError/SyntaxError) in the M5 incident into triggering a false pass. With the switch off, behavior is byte-identical to the historical keyword policy.

> **3.5 Cross-file extension path** (enabled when `CROSS_FILE_ENABLE=true`, off by default): a `cross_file_analyzer` node (`_cross_file_analyzer_node`) is inserted between `executor` and `debugger`, performing AST cross-file import dependency analysis and writing the dependency edges into `state["cross_file_deps"]`; `_patch_applier_node` applies patches to multiple modules in topological order in the cross-file branch (callee modified first, caller second); if any file fails, `cross_file_fallback_single_file()` degrades to applying the patch only to the entry module (with the same semantics as single-file `safe_apply_patch`). See [docs/design/cross_file_repair.md](design/cross_file_repair.md) for details.

---

## 4. Multi-Agent Orchestration Protocol (ablatable container, ADR-0016)

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

> **State keys added in repair-engine batch I**: `llm_localization` (RGFL reasoning-localization result, written by `_debugger_node`, `{function_name, line_start, line_end, confidence, reasoning}` or None); the existing key `fl_spectral_focus` (spectral Top-k, O2) carries the spectral channel. Both feed the experiment layer's localization metrics.

### 4.2 Ablation Experiment Configuration Matrix

Boolean switches control node enablement/disabling, forming 4 experiment variants (configuration in [config.py](../config.py)):

| Variant | ENABLE_PLANNER | ENABLE_DEBUGGER | ENABLE_RAG | Corresponding Baseline |
|:----:|:--------------:|:---------------:|:----------:|---------|
| Full system | true | true | false | AITester |
| No Planner | false | true | false | No-planning baseline |
| No Debugger | true | false | false | No-repair baseline |
| Plain LLM | false | false | false | plain_llm |
| Single agent | — | — | — | single_agent |

> **Localization-channel ablation (since repair-engine batch I)**: `FAULT_LOCALIZER_ENABLE` (true by default; false = pure-spectral ablation caliber) and `FL_SPECTRAL_ENABLE` (true by default) are independent of the four variants above and can be combined into four localization ablation arms — "dual-channel full / spectral-only / reasoning-only / no localization" — to isolate each localization channel's contribution.

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
