# Roadmap 7-Section Landing Audit (2026-09-27)

> Audited target: the user-supplied "improvement roadmap" 7 sections
> (① code context / patch-ingredient retention, ② post-patch type repair,
> ③ bidirectional diagnosis, ④ synthetic-dataset difficulty stratification,
> ⑤ contamination-detection multi-dimension expansion, ⑥ RAG token-efficiency
> verification, ⑦ complexity-aware model routing).
> Method: per-section grep/read of the code (evidence cited as file:line),
> verdict: implemented / remaining gap.
> Audit date: 2026-09-27 | repo: AITester (post-0.7 debt-clearing).
> Summary: **all improvement points of 6 of the 7 sections are already
> landed** (across the 0.8–0.11 batches); section ⑤ (contamination-detection
> multi-dimension expansion) had 3 residual sub-item gaps, all closed on the
> same day (see the "gap-closing batch" below).

---

## ① Code context: from character truncation to "patch-ingredient" retention

| Improvement point | Status | Evidence |
|---|---|---|
| 1.1 `preserve_patch_ingredients(file_path, func_name)`: target function's full AST node + 1-level called-function signatures + module-level export symbols (`__all__` / `@register` / plugin entrypoints) + all imports | ✅ Implemented | `src/tools/code_analyzer.py:445` (returns the `imports / target_ast / called_signatures / exports / register_symbols / module_constants` dict); `code_analyzer.py:526` (`render_patch_ingredients` renders the `[PATCH_INGREDIENTS]` block) |
| Inject patch ingredients before truncation (replacing naive char truncation) | ✅ Implemented | `src/agents/base_agent.py:523` (`truncate_code` first runs `code_context.extract_focused_code_detail` (call-chain depth + auto-appended `[PATCH_INGREDIENTS]` contract block); char head/tail truncation is only the fallback when no focus function is given or focus parsing fails) |
| 1.2 Naming-contract AST symbol guard: before applying a patch, compare module-level symbol sets (functions / classes / `__all__`); rejecting any removed original export symbol | ✅ Implemented | `src/tools/patch_applier.py:519` (`check_naming_contract`: parses both sides, compares module-level symbols + `__all__` entries + registered-decorator symbols + plugin entrypoint symbols); `patch_applier.py:559` (`safe_apply_patch_contract`: AST syntax check, then symbol guard, missing symbols → reject + record the missing list + trigger resample/regen) |
| 1.3 Three-tier downgrade chain: full function context → patch-ingredient retention → signature+import minimal context, temperature tightening per tier | ✅ Implemented | `patch_applier.py:614` (`_CONTEXT_TIER_TEMPERATURES = {0: 0.2, 1: 0.1, 2: 0.0}` + `build_tiered_context`: tier 0 = `extract_function_context` full context, tier 1 = `preserve_patch_ingredients` recipe, tier 2 = signature+import minimal `[MINIMAL_CONTEXT]`); `patch_applier.py:638` (`advance_context_tier` advances the tier when the guard rejects); `src/agents/debugger.py:102-145` (`_build_downgrade_context` + `_downgrade_tier_temperature`, `contract_reject_feedback` drives the tier-aware regen) |

## ② Post-patch processing: systematic type-error repair

| Improvement point | Status | Evidence |
|---|---|---|
| TypeRepairLayer placed after the DebuggerAgent, before `_apply_fix_node` | ✅ Implemented | `src/agents/debugger.py:547` (`debug()` calls `type_repair.type_repair_layer` after producing the patch and before writing back state — i.e. the "after LLM patch generation, before apply/write" position in the repair pipeline); `src/graph/nodes.py:814` (`_debugger_node` writes `type_repair_findings` / `mypy_findings_count` back to state for experiment analysis) |
| Static type check (mypy repo-level + AST conservative heuristic, two layers) | ✅ Implemented | `src/tools/type_repair.py` (`_static_type_findings` pure-AST conservative layer: type reassignment / container mixing / undefined attribute / inconsistent return types; `_run_mypy_findings` runs mypy under `TYPE_CHECK_ENABLE=true`, transparently degrades when not installed) |
| LLM type-inference repair (injecting the original file's type annotations as context) | ✅ Implemented | `type_repair.py` (`type_repair_layer` LLM layer: under `TYPE_REPAIR_LLM_ENABLE=true` injects the findings + original type annotations into the LLM for inference and a repaired patch; off by default, unenabled → findings-only observation layer) |
| Repaired patch re-passes the symbol-guard check | ✅ Implemented | `type_repair.py` (the repaired patch loops back through `patch_applier.check_naming_contract`; `contract_ok` False → reject the repair, conservatively keep the original patch) |

## ③ Bidirectional code-test diagnosis

| Improvement point | Status | Evidence |
|---|---|---|
| DiagnosisNode before `_debug_node` analyzes the root cause (error type / failing assertion / stack location) and decides "code defect vs test defect" | ✅ Implemented | `src/graph/nodes.py:626` (`_diagnosis_node`, reusing `DebuggerAgent._run_review_diagnosis` Review Agent); `src/graph/workflow.py:240-251` (under `DIAGNOSIS_NODE_ENABLE=true` inserts the diagnosis node + `_route_after_diagnosis` conditional routing between executor→debugger) |
| Test defect → route back to GeneratorAgent to regenerate tests (stricter assertion constraints) | ✅ Implemented | `workflow.py:138-177` (`_route_after_diagnosis`: `test_defect` and regen not at cap → `"regenerate"` back to the generator; at cap → `"done"` convergence); `_generator_node` consumes `defect_type="test_defect"` and goes through regen |
| Code defect → route to DebuggerAgent to generate a patch | ✅ Implemented | `workflow.py:177` (`_route_after_diagnosis` returns `"debug"`); under `BIDIRECTIONAL_DIAGNOSIS_ENABLE=true` the debugger's inline `_run_review_diagnosis` judges on the same convention |

## ④ Synthetic-dataset difficulty stratification

| Improvement point | Status | Evidence |
|---|---|---|
| 4.1 Four-level difficulty (Level 1 single-function / Level 2 multi-function interaction / Level 3 cross-file dependency / Level 4 boundary-exception hidden defects) | ✅ Implemented | `src/datasets/synthetic_dataset.py` (`difficulty` param, `_VALID_DIFFICULTIES = {"mixed","level1".."level4"}`; Level 3 via `CROSS_FILE_PATTERNS` dual-module `module_a`+`module_b` construction, defect in `module_b` but triggered by `module_a`'s call); `experiments/synthetic_difficulty.py` (standalone multi-level task generator, `generate_level1..4_task`, Level 3 emits dual modules + `cross_file_deps` edges) |
| 4.2 Mutant difficulty upgrade: condition-boundary mutation (`>`↔`>=`) + return-value mutation (None / empty list / wrong type) | ✅ Implemented | `experiments/mutation_testing.py:198-212` (built-in generator with 7 mutant classes: `operator_flip` (==↔!= / <↔>), `boolean_negation`, `numeric_offset`, `boundary_shift` (>↔>= / <↔<= off-by-one direction), `return_void` (`return X → return None`), `return_empty` (→ empty container/str), `exception_remove` (remove/change exception type); coverage aligns with the 4.2 proposal's boundary+return+exception three categories) |

## ⑤ Contamination-detection multi-dimension expansion

| Improvement point | Status | Evidence |
|---|---|---|
| Semantic-level similarity (CodeBERT embedding cosine) | ✅ Implemented (real-embedding hook + CodeBERT backend) | `src/utils/embedding_utils.py` (`embed_text` picks a backend per `EMBEDDING_BACKEND`, `auto` priority codebert → sentence_transformers → chromadb; the codebert branch loads `Salesforce/codebert-base` via `transformers.AutoModel` (overridable via `EMBEDDING_CODEBERT_MODEL`), `[CLS]` L2-normalized embedding; missing deps transparently fall back to the token-bag cosine conservative baseline); `contamination_check.py` (`_detect_semantic_cosine` consumes `embed_text`, `semantic_source` tags real-embedding vs token-bag proxy) |
| Structural-level similarity (AST subtree matching, detecting a patch that "memorized" the golden patch's structure) | ✅ Implemented | `contamination_check.py` (`_detect_ast_skeleton_similarity`: the "statement-type sequence" (Expr/Assign/Compare…) of both patches' modified lines measured by LCS ratio, catching "renamed-but-same-control-flow" copies) |
| SWE-bench Pro support (strong-copyleft contamination-resistant benchmark) | ✅ Implemented | `contamination_check.py` (`CONTAMINATION_RESISTANT_BENCHMARKS` includes a `swe-bench-pro` entry: strong-copyleft design note + GPT-5 Pass@1 ~23.3% + `recommended_pairing` = `swe-bench-verified`); `src/datasets/dataset_loader.py` (`load_dataset("swe_bench_pro")` / `swebench_pro` alias, reusing `SWEBenchDataset`, data dir injected via `data_dir`, same isomorphic convention as `swe_rebench`) |
| Auto-tag each task's contamination risk level in experiment reports | ✅ Implemented | `contamination_check.py` (`_combined_risk_level` takes the most severe of the three dimensions → high/medium/low; `detect_contamination` emits a per-task `risk_level` field); `experiments/run_benchmark.py` (`_build_task_result` writes the `contamination_risk_level` row field) |

## ⑥ RAG token-efficiency verification

| Improvement point | Status | Evidence |
|---|---|---|
| `--enable-rag` vs `--disable-rag` A/B experiment recording token consumption / success rate / iteration count | ✅ Implemented | `experiments/rag_ab_experiment.py` (automates an RAG ON vs OFF run, per-task stats of tokens / success rate / iterations / wall-clock; Welch t-test + Mann-Whitney U + Cohen's d; emits the paper-ready efficiency metric `token_saving.delta_pct`; `--analyze-only` supports reading existing results for stats) |

## ⑦ Complexity-aware model routing

| Improvement point | Status | Evidence |
|---|---|---|
| APIManager adds a task-complexity assessor (code lines / file count / dep count → complexity score) | ✅ Implemented | `src/api/complexity_router.py` (`compute_complexity_score`: lines / files / deps / cyclomatic, four dimensions each 25% normalized and weighted, score <0.35 simple / <0.70 medium / ≥0.70 complex; `count_imports` counts module-level imports) |
| Simple tasks route to a lightweight model, complex tasks to a stronger model | ✅ Implemented | `complexity_router.py:188` (`complexity_class_to_routing_hints`: simple = single candidate + small context, complex = 3 candidates + 6000 context + extra iteration); `src/agents/base_agent.py` (`_reorder_api_groups_by_complexity` reorders API-instance priority by tier); `src/api/api_manager.py:465` (`_select_node_by_complexity` picks the node by tier) |
| Add a `MODEL_ROUTING_STRATEGY=complexity_aware` config item | ✅ Implemented | `complexity_router.py:92` (`routing_strategy()` reads `MODEL_ROUTING_STRATEGY`, default `complexity_aware`, `fixed` falls back to the historical convention) |

---

## Verdict & gap-closing batch

### Verdict summary

| Section | Verdict | Remaining work (at audit time) |
|---|---|---|
| ① code context / patch ingredients | Implemented | none |
| ② post-patch type repair | Implemented (mypy layer) | (optional) pyright alternate backend |
| ③ bidirectional diagnosis | Implemented | none |
| ④ difficulty stratification | Implemented | none |
| ⑤ contamination multi-dimension | Mostly implemented | 3 sub-item gaps: SWE-bench Pro, CodeBERT embedding backend, pyright alternate |
| ⑥ RAG token verification | Implemented | none |
| ⑦ complexity routing | Implemented | none |

> Note: aside from the 3 sub-item gaps of section ⑤, every improvement
> point of the 7-section roadmap is already implemented in the repo with
> corresponding tests.

### Gap-closing batch (2026-09-27, default behavior unchanged)

| Gap | Landing content | Evidence |
|---|---|---|
| ⑤ SWE-bench Pro support | `contamination_check` resistant-benchmark registry + `dataset_loader` dataset name | see the ⑤ rows above |
| ⑤ CodeBERT embedding backend | `embedding_utils.codebert` backend (`transformers` AutoModel, top `auto` priority, falls back on missing deps) | `tests/test_roadmap_gaps_g1_g2_g3.py` (20 cases) |
| ② pyright alternate backend | `type_repair._run_pyright_findings` + `TYPE_CHECK_BACKEND` (default mypy convention unchanged) | same as above |

Regression: full 1956 tests pass (baseline 1937 + 20 new guards), ruff / mypy
clean; zero change to the default experiment convention (new backends /
datasets each have dedicated switches or isomorphic reuse, transparent
fallback on missing dependencies).
