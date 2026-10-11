# E2 / P0-2 环境开关 provenance 门禁报告（`_env_snapshot_keys` 完备性）

生成时间：2026-10-10（E2 审查批次 task-6）　生成者：patch-analyst

## 0. 结论摘要

- **首测（本轮审查开始时的门禁基线）**：`src/**/*.py` 中 `*_ENABLE` 开关 **74** 个，`_env_snapshot_keys` 收录 **39** 键，**缺失 57 个 → exit 1**。其中 **37 个**直接字面量可见（与 T2 审计 37/55 对账一致）+ **20 个**只能经模块级常量间接引用发现（正则/直接字面量扫描的漏检面）。
- **本次重跑（报告定稿时的工作树）**：快照已由其他成员补入 **11** 个默认开/P0 键 → `_env_snapshot_keys` **50** 键，**缺失降至 46 个（仍 exit 1）**；其中字面量默认 `true` 的仅剩 2 个（`API_HEALTH_CHECKER_ENABLE`, `CREDENTIAL_SCRUB_WHITELIST_ENABLE`）。
- **与 A1/RT1/D3 三起事故同族的风险**：未入快照的开关使"干预是否生效"无法从工件 provenance 证明——本次已消除 11 个默认开开关的同族风险（见 §9 变更记录），其余 46 个按 §3 的 P0→P3 顺序收口。
- 已知三起事故复现：`DETECTION_FIRST_SECTION_ENABLE` 首测缺失、现已补入；`OVER_RED_SECTION_ENABLE` / `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 首测即在快照内（通过）。
- 本报告**只报告不改**：`experiments/run_benchmark.py::_env_snapshot_keys` 的增补属 lead/其他成员收口范围。

## 1. 复现命令与口径

```bash
# 人读（缺失 → exit 1）
.venv/bin/python scripts/gates/check_env_snapshot_keys.py
# 机读（本次报告数据源，退出码同上）
.venv/bin/python scripts/gates/check_env_snapshot_keys.py --json > review_2026/E2_env_snapshot_report.json
# 全量环境变量（不限 _ENABLE）
.venv/bin/python scripts/gates/check_env_snapshot_keys.py --all-keys
```

口径（AST，非正则）：

- 扫描面：`src/**/*.py`（`--scan-root` 可重复；附加 `config.py` 实测只多出 2 个已在快照中的 `*_ENABLE`，`missing` 不变 → 默认扫描面足够）；
- 识别形态：`os.getenv("X")` / `os.environ.get("X")` / `os.environ["X"]` / `os.environ.setdefault("X", ...)` / `_flag("X")` 及同族开关 helper / `from os import getenv` 别名；
- 间接引用：模块级字符串常量（值形如环境变量名，如 `_ENV = "FAULT_LOCALIZER_ENABLE"`、`_GOLD_INJECTION_ENV = "FL_GOLD_INJECTION_ENABLE"`）被用作读取实参时解析回字面量；
- 快照提取：`ast.literal_eval` 精确求值 `_env_snapshot_keys`（本次 `mode=literal_eval`，逐键可信）；
- 阻断条件：`missing`（扣除白名单）非空；白名单文件默认 `review_2026/E2_env_snapshot_allowlist.txt`（不存在即空，当前无豁免键）。

## 2. 计数与对账

| 项 | 数量 |
|---|---|
| `*_ENABLE` 开关全集（`src/`，AST） | 74 |
| └ 含直接字面量读取点 | 53 |
| └ 仅常量间接引用（正则扫不到） | 21 |
| 快照 `_env_snapshot_keys` 键数（`*_ENABLE` 形态 17） | 50 |
| 已覆盖 | 28 |
| **缺失（门禁阻断）** | **46** |
| └ 直接字面量可见 | 29 |
| └ 仅常量间接引用可见 | 17 |
| 白名单豁免 | 0 |
| 快照内未在扫描面出现的键（信息项，不阻断） | 22 |

**与 T2 审计（37/55）对账**：门禁**首测**的"直接字面量可见"子集为 **53** 个开关、缺失 **37** 个——与 T2 的 37 完全一致；另有 **20** 个开关**只能**经模块级字符串常量间接引用发现（T2 的正则扫描面外）→ 首测真实缺失面 **57 而非 37**（若按正则实现会漏掉 35% 的缺失键）。本次重跑：直接可见缺失 **29**、常量间接缺失 **17**、合计 **46**。

## 3. 建议加入快照的键（有序建议）

### P0（0 个）—— 默认开（字面量默认 `true`）——**最高优先**：不入快照则"该开关默认已生效"无法从工件证明，未来翻转为 false 亦不可审计

（空）首测的默认开缺失键已在本次重跑前由其他成员补入快照（见 §9）；剩余 2 个默认开键（纯运维类）归入 P3。

### P1（40 个）—— 修复/裁决/测量主链路开关（定义点位于 workflow / nodes / flags / patch_* / detection_gates / specs 等）——改变实验臂语义，须入快照

| # | 键 | 定义点 | 字面量默认 |
|---|---|---|---|
| 1 | `ADVERSARIAL_DEBUGGING_ENABLE` | src/agents/debugger.py:82 | false |
| 2 | `ASSERTION_AUGMENT_ENABLE` | src/agents/generator.py:43 | false |
| 3 | `BIDIRECTIONAL_DIAGNOSIS_ENABLE` | src/agents/debugger.py:119 | false |
| 4 | `CONTEXT_TIER_DOWNGRADE_ENABLE` | src/graph/flags.py:233 | false |
| 5 | `CONTRACT_ALIAS_ENABLE` | src/tools/patch_postprocess.py:60 | false |
| 6 | `COVERAGE_STALL_DETECT_ENABLE` | src/graph/workflow.py:602 | false |
| 7 | `CROSS_FILE_ENABLE` | src/tools/cross_file.py:53 | false |
| 8 | `DETECTION_SPECIFICITY_GATE_ENABLE` | src/tools/detection_gates.py:61 | false |
| 9 | `DETERMINISTIC_GUARD_ENABLE` | src/agents/deterministic_guard.py:34 | false |
| 10 | `DETERMINISTIC_REPAIR_FIRST_ENABLE` | src/tools/deterministic_repair.py:87 | false |
| 11 | `EDIT_INTENT_ENABLE` | src/tools/patch_intent.py:47 | false |
| 12 | `EXPERT_POOL_DEBATE_ENABLE` | src/graph/expert_pool.py:142 | false |
| 13 | `FAILURE_FREQUENCY_ENABLE` | src/graph/flags.py:76, src/tools/failure_frequency.py:59 | false |
| 14 | `FAILURE_KB_ENABLE` | src/agents/failure_kb.py:58 | false |
| 15 | `FL_GOLD_INJECTION_ENABLE` | src/agents/fault_localizer.py:71 | false |
| 16 | `GRAPH_RAG_ENABLE` | src/tools/graphrag.py:51 | false |
| 17 | `HIERARCHICAL_SUMMARY_ENABLE` | src/tools/hierarchical_summary.py:60 | false |
| 18 | `IMPORT_REPAIR_ENABLE` | src/tools/patch_postprocess.py:54 | false |
| 19 | `LOCALIZED_EDIT_ENABLE` | src/tools/patch_localized.py:45 | false |
| 20 | `ORACLE_ENHANCE_ENABLE` | src/agents/oracle_enhancer.py:55, src/graph/flags.py:64 | false |
| 21 | `ORACLE_VALIDATE_ENABLE` | src/graph/flags.py:87, src/tools/oracle_validator.py:62 | false |
| 22 | `PATCH_SNAPSHOT_ROLLBACK_ENABLE` | src/tools/patch_rollback.py:88 | false |
| 23 | `PROBE_SNAPSHOT_LOCATE_ENABLE` | src/agents/debugger.py:109, src/graph/flags.py:113 | false |
| 24 | `RAG_CONDITIONAL_ENABLE` | src/graph/rag.py:241 | false |
| 25 | `RAG_JUDGE_INSTRUCTION_ENABLE` | src/agents/debugger.py:490 | false |
| 26 | `RAG_KEYWORD_FALLBACK_ENABLE` | src/graph/rag.py:341 | false |
| 27 | `RAG_RELEVANCE_THRESHOLD_ENABLE` | src/graph/rag.py:221 | false |
| 28 | `RED_REGRESSION_GATE_ENABLE` | src/tools/detection_gates.py:66 | false |
| 29 | `REPRO_TEST_ENABLE` | src/agents/generator.py:96 | false |
| 30 | `REWARD_PREDICTOR_ENABLE` | src/tools/multi_candidate.py:458 | false |
| 31 | `RISK_APPROVAL_ENABLE` | src/graph/risk_approval.py:59, src/graph/workflow.py:874 | false |
| 32 | `ROUTE_STRUCTURED_ENABLE` | src/graph/workflow.py:285 | false |
| 33 | `RUNTIME_PROBE_ENABLE` | src/agents/runtime_probe.py:75, src/graph/flags.py:98 | false |
| 34 | `SPEC_IR_DSL_ENABLE` | src/graph/flags.py:182, src/specs/spec_ir_v2.py:80 | false |
| 35 | `SPEC_REFINE_ENABLE` | src/specs/spec_refine.py:44 | false |
| 36 | `SPEC_SMT_ENABLE` | src/specs/spec_smt.py:60 | false |
| 37 | `STRATEGY_BANK_ENABLE` | src/tools/strategy_bank.py:114 | false |
| 38 | `TESTLESS_VALIDATION_ENABLE` | src/tools/testless_validation.py:43 | false |
| 39 | `TEST_SUITE_DEDUP_ENABLE` | src/graph/nodes.py:937 | false |
| 40 | `TYPE_REPAIR_LLM_ENABLE` | src/tools/type_repair.py:48 | false |

### P2（3 个）—— 其余行为类开关（debugger prompt 增强 / 检索 / 生成器辅助）——影响执行路径，建议入快照

| # | 键 | 定义点 | 字面量默认 |
|---|---|---|---|
| 1 | `INJECTION_GUARD_ENABLE` | src/agents/injection_guard.py:53 | false |
| 2 | `ROGUE_MONITOR_ENABLE` | src/agents/rogue_monitor.py:39 | false |
| 3 | `SEMANTIC_CACHE_ENABLE` | src/agents/semantic_cache.py:44 | false |

### P3（3 个）—— 纯运维 / 遥测开关（不影响任务结果口径）——可登记白名单豁免，不入快照

| # | 键 | 定义点 | 字面量默认 |
|---|---|---|---|
| 1 | `AGENT_TELEMETRY_ENABLE` | src/observability/agent_telemetry.py:135 | false |
| 2 | `API_HEALTH_CHECKER_ENABLE` | src/api/api_manager.py:109 | true |
| 3 | `CREDENTIAL_SCRUB_WHITELIST_ENABLE` | src/utils/credential_scrub.py:122 | true |

**收口建议**：先补 P0（10 个默认开开关，收益最高、风险最低）+ 2 个默认开的 P3 键（`API_HEALTH_CHECKER_ENABLE` / `CREDENTIAL_SCRUB_WHITELIST_ENABLE`——若决定豁免则须写白名单，否则门禁持续阻断）→ 再补 P1（修复/裁决主链路 41 个，按表内顺序即字母序，可整段粘贴）→ P2（3 个）随下个批次批量补 → P3 纯运维键登记 `review_2026/E2_env_snapshot_allowlist.txt` 豁免（避免快照被无关键稀释）。

## 4. 已知事故复现

| 开关 | 事故 | 本次门禁判定 | 定义点 |
|---|---|---|---|
| `DETECTION_FIRST_SECTION_ENABLE` | RT1（检出优先协议，未登记） | 在快照中 → 门禁通过 | experiments/run_benchmark.py（快照清单内） |
| `OVER_RED_SECTION_ENABLE` | D3（over_red 受控臂首跑 NOTVERIFIABLE） | 在快照中 → 门禁通过 | experiments/run_benchmark.py（快照清单内） |
| `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` | A1 首跑（消融假阴性） | 在快照中 → 门禁通过 | experiments/run_benchmark.py（快照清单内） |

## 5. 完整缺失清单（按定义文件分组，57 键）

- **src/agents/debugger.py**（4）：`ADVERSARIAL_DEBUGGING_ENABLE`, `BIDIRECTIONAL_DIAGNOSIS_ENABLE`, `PROBE_SNAPSHOT_LOCATE_ENABLE`, `RAG_JUDGE_INSTRUCTION_ENABLE`
- **src/agents/deterministic_guard.py**（1）：`DETERMINISTIC_GUARD_ENABLE`
- **src/agents/failure_kb.py**（1）：`FAILURE_KB_ENABLE`
- **src/agents/fault_localizer.py**（1）：`FL_GOLD_INJECTION_ENABLE`
- **src/agents/generator.py**（2）：`ASSERTION_AUGMENT_ENABLE`, `REPRO_TEST_ENABLE`
- **src/agents/injection_guard.py**（1）：`INJECTION_GUARD_ENABLE`
- **src/agents/oracle_enhancer.py**（1）：`ORACLE_ENHANCE_ENABLE`
- **src/agents/rogue_monitor.py**（1）：`ROGUE_MONITOR_ENABLE`
- **src/agents/runtime_probe.py**（1）：`RUNTIME_PROBE_ENABLE`
- **src/agents/semantic_cache.py**（1）：`SEMANTIC_CACHE_ENABLE`
- **src/api/api_manager.py**（1）：`API_HEALTH_CHECKER_ENABLE`
- **src/graph/expert_pool.py**（1）：`EXPERT_POOL_DEBATE_ENABLE`
- **src/graph/flags.py**（7）：`CONTEXT_TIER_DOWNGRADE_ENABLE`, `FAILURE_FREQUENCY_ENABLE`, `ORACLE_ENHANCE_ENABLE`, `ORACLE_VALIDATE_ENABLE`, `PROBE_SNAPSHOT_LOCATE_ENABLE`, `RUNTIME_PROBE_ENABLE`, `SPEC_IR_DSL_ENABLE`
- **src/graph/nodes.py**（1）：`TEST_SUITE_DEDUP_ENABLE`
- **src/graph/rag.py**（3）：`RAG_CONDITIONAL_ENABLE`, `RAG_KEYWORD_FALLBACK_ENABLE`, `RAG_RELEVANCE_THRESHOLD_ENABLE`
- **src/graph/risk_approval.py**（1）：`RISK_APPROVAL_ENABLE`
- **src/graph/workflow.py**（3）：`COVERAGE_STALL_DETECT_ENABLE`, `RISK_APPROVAL_ENABLE`, `ROUTE_STRUCTURED_ENABLE`
- **src/observability/agent_telemetry.py**（1）：`AGENT_TELEMETRY_ENABLE`
- **src/specs/spec_ir_v2.py**（1）：`SPEC_IR_DSL_ENABLE`
- **src/specs/spec_refine.py**（1）：`SPEC_REFINE_ENABLE`
- **src/specs/spec_smt.py**（1）：`SPEC_SMT_ENABLE`
- **src/tools/cross_file.py**（1）：`CROSS_FILE_ENABLE`
- **src/tools/detection_gates.py**（2）：`DETECTION_SPECIFICITY_GATE_ENABLE`, `RED_REGRESSION_GATE_ENABLE`
- **src/tools/deterministic_repair.py**（1）：`DETERMINISTIC_REPAIR_FIRST_ENABLE`
- **src/tools/failure_frequency.py**（1）：`FAILURE_FREQUENCY_ENABLE`
- **src/tools/graphrag.py**（1）：`GRAPH_RAG_ENABLE`
- **src/tools/hierarchical_summary.py**（1）：`HIERARCHICAL_SUMMARY_ENABLE`
- **src/tools/multi_candidate.py**（1）：`REWARD_PREDICTOR_ENABLE`
- **src/tools/oracle_validator.py**（1）：`ORACLE_VALIDATE_ENABLE`
- **src/tools/patch_intent.py**（1）：`EDIT_INTENT_ENABLE`
- **src/tools/patch_localized.py**（1）：`LOCALIZED_EDIT_ENABLE`
- **src/tools/patch_postprocess.py**（2）：`CONTRACT_ALIAS_ENABLE`, `IMPORT_REPAIR_ENABLE`
- **src/tools/patch_rollback.py**（1）：`PATCH_SNAPSHOT_ROLLBACK_ENABLE`
- **src/tools/strategy_bank.py**（1）：`STRATEGY_BANK_ENABLE`
- **src/tools/testless_validation.py**（1）：`TESTLESS_VALIDATION_ENABLE`
- **src/tools/type_repair.py**（1）：`TYPE_REPAIR_LLM_ENABLE`
- **src/utils/credential_scrub.py**（1）：`CREDENTIAL_SCRUB_WHITELIST_ENABLE`

## 6. 逐键明细（定义点 file:line，供直接增补快照用）

| 键 | 优先级 | 定义点（file:line） | 字面量默认 |
|---|---|---|---|
| `ADVERSARIAL_DEBUGGING_ENABLE` | P1 | src/agents/debugger.py:82 | false |
| `ASSERTION_AUGMENT_ENABLE` | P1 | src/agents/generator.py:43 | false |
| `BIDIRECTIONAL_DIAGNOSIS_ENABLE` | P1 | src/agents/debugger.py:119 | false |
| `CONTEXT_TIER_DOWNGRADE_ENABLE` | P1 | src/graph/flags.py:233 | false |
| `CONTRACT_ALIAS_ENABLE` | P1 | src/tools/patch_postprocess.py:60 | false |
| `COVERAGE_STALL_DETECT_ENABLE` | P1 | src/graph/workflow.py:602 | false |
| `CROSS_FILE_ENABLE` | P1 | src/tools/cross_file.py:53 | false |
| `DETECTION_SPECIFICITY_GATE_ENABLE` | P1 | src/tools/detection_gates.py:61 | false |
| `DETERMINISTIC_GUARD_ENABLE` | P1 | src/agents/deterministic_guard.py:34 | false |
| `DETERMINISTIC_REPAIR_FIRST_ENABLE` | P1 | src/tools/deterministic_repair.py:87 | false |
| `EDIT_INTENT_ENABLE` | P1 | src/tools/patch_intent.py:47 | false |
| `EXPERT_POOL_DEBATE_ENABLE` | P1 | src/graph/expert_pool.py:142 | false |
| `FAILURE_FREQUENCY_ENABLE` | P1 | src/graph/flags.py:76, src/tools/failure_frequency.py:59 | false |
| `FAILURE_KB_ENABLE` | P1 | src/agents/failure_kb.py:58 | false |
| `FL_GOLD_INJECTION_ENABLE` | P1 | src/agents/fault_localizer.py:71 | false |
| `GRAPH_RAG_ENABLE` | P1 | src/tools/graphrag.py:51 | false |
| `HIERARCHICAL_SUMMARY_ENABLE` | P1 | src/tools/hierarchical_summary.py:60 | false |
| `IMPORT_REPAIR_ENABLE` | P1 | src/tools/patch_postprocess.py:54 | false |
| `LOCALIZED_EDIT_ENABLE` | P1 | src/tools/patch_localized.py:45 | false |
| `ORACLE_ENHANCE_ENABLE` | P1 | src/agents/oracle_enhancer.py:55, src/graph/flags.py:64 | false |
| `ORACLE_VALIDATE_ENABLE` | P1 | src/graph/flags.py:87, src/tools/oracle_validator.py:62 | false |
| `PATCH_SNAPSHOT_ROLLBACK_ENABLE` | P1 | src/tools/patch_rollback.py:88 | false |
| `PROBE_SNAPSHOT_LOCATE_ENABLE` | P1 | src/agents/debugger.py:109, src/graph/flags.py:113 | false |
| `RAG_CONDITIONAL_ENABLE` | P1 | src/graph/rag.py:241 | false |
| `RAG_JUDGE_INSTRUCTION_ENABLE` | P1 | src/agents/debugger.py:490 | false |
| `RAG_KEYWORD_FALLBACK_ENABLE` | P1 | src/graph/rag.py:341 | false |
| `RAG_RELEVANCE_THRESHOLD_ENABLE` | P1 | src/graph/rag.py:221 | false |
| `RED_REGRESSION_GATE_ENABLE` | P1 | src/tools/detection_gates.py:66 | false |
| `REPRO_TEST_ENABLE` | P1 | src/agents/generator.py:96 | false |
| `REWARD_PREDICTOR_ENABLE` | P1 | src/tools/multi_candidate.py:458 | false |
| `RISK_APPROVAL_ENABLE` | P1 | src/graph/risk_approval.py:59, src/graph/workflow.py:874 | false |
| `ROUTE_STRUCTURED_ENABLE` | P1 | src/graph/workflow.py:285 | false |
| `RUNTIME_PROBE_ENABLE` | P1 | src/agents/runtime_probe.py:75, src/graph/flags.py:98 | false |
| `SPEC_IR_DSL_ENABLE` | P1 | src/graph/flags.py:182, src/specs/spec_ir_v2.py:80 | false |
| `SPEC_REFINE_ENABLE` | P1 | src/specs/spec_refine.py:44 | false |
| `SPEC_SMT_ENABLE` | P1 | src/specs/spec_smt.py:60 | false |
| `STRATEGY_BANK_ENABLE` | P1 | src/tools/strategy_bank.py:114 | false |
| `TESTLESS_VALIDATION_ENABLE` | P1 | src/tools/testless_validation.py:43 | false |
| `TEST_SUITE_DEDUP_ENABLE` | P1 | src/graph/nodes.py:937 | false |
| `TYPE_REPAIR_LLM_ENABLE` | P1 | src/tools/type_repair.py:48 | false |
| `INJECTION_GUARD_ENABLE` | P2 | src/agents/injection_guard.py:53 | false |
| `ROGUE_MONITOR_ENABLE` | P2 | src/agents/rogue_monitor.py:39 | false |
| `SEMANTIC_CACHE_ENABLE` | P2 | src/agents/semantic_cache.py:44 | false |
| `AGENT_TELEMETRY_ENABLE` | P3 | src/observability/agent_telemetry.py:135 | false |
| `API_HEALTH_CHECKER_ENABLE` | P3 | src/api/api_manager.py:109 | true |
| `CREDENTIAL_SCRUB_WHITELIST_ENABLE` | P3 | src/utils/credential_scrub.py:122 | true |

## 7. 快照内、但未在 `src/` 扫描面出现的键（信息项，不阻断）

22 个：`AITESTER_CACHE_ISOLATE_MODEL`, `AITESTER_CACHE_NAMESPACE`, `AITESTER_LLM_CACHE`, `AITESTER_PROFILE`, `DETECTION_FIRST_ENABLE`, `ENABLE_DEBUGGER`, `ENABLE_PLANNER`, `ENABLE_RAG`, `EXECUTION_TIMEOUT`, `FLAKY_REPEAT_COUNT`, `FL_SPECTRAL_TOP_K`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_REASONING_EFFORT`, `LLM_THINKING_MODE`, `LLM_TIMEOUT`, `MAX_ITERATIONS`, `MUTATION_TEST_ENABLE`, `RAG_POISONING_FILTER`, `REPO_LEVEL_EXECUTION`, `SWE_BENCH_P2P_GATE_ENABLE`, `SWE_BENCH_P2P_GATE_THRESHOLD`, `TEMPERATURE`

说明：这些键或在 `config.py`（根目录，非 `src/`）读取，或由实验脚本侧消费（如 `MAX_ITERATIONS`/`TEMPERATURE`）——属正常，不构成缺失。

## 8. 能力边界（已知漏网面，诚实声明）

1. **动态拼接**：`os.getenv(f"{prefix}_ENABLE")` / 变量名传参静态不可见——本门禁是"名字集合一致性检查"，不是开关完备性证明；
2. **函数内局部常量**：仅解析**模块级**字符串常量间接引用（函数内 `k = "X_ENABLE"; os.getenv(k)` 会漏）；
3. **`experiments/` 侧开关**：默认不扫（产品开关面口径与 `scripts/gates/check_env_budget.py` 一致），实验脚本新增开关需人工判断是否入快照；
4. **`_env_snapshot_keys` 提取模式**：当前为 `literal_eval`（精确）；若未来改为运行时构造，门禁自动退化为字面量扫描并在 JSON 的 `snapshot.mode` / `note` 中标注，**审计时须检查该字段**。

## 9. 变更记录（门禁报告首测 → 本次重跑）

- 首测（本轮审查开始时）：缺失 **57** 个，`_env_snapshot_keys` 39 键；
- 本次重跑：缺失 **46** 个，`_env_snapshot_keys` 50 键（快照行 `2731`）；
- 期间由其他成员补入快照的 **11** 个键（均为默认开/P0 优先项）：`CFG_ANALYSIS_ENABLE`、`CONTEST_AST_SCAN_ENABLE`、`DETECTION_FIRST_SECTION_ENABLE`、`EVENT_BUS_ENABLE`、`FAULT_LOCALIZER_ENABLE`、`INJECTION_GUARD_OUTPUT_ENABLE`、`P2P_GATE_ENABLE`、`PATCH_EVIDENCE_GATE_ENABLE`、`POSITION_AWARE_REPAIR_ENABLE`、`SPEC_ORACLE_EXEC_ENABLE`、`TRACE_MEMORY_BUFFER_ENABLE`
- 新增缺失：无（本次为 0，说明源码面未新增开关）
- 门禁是**棘轮**：`missing` 归零前一直 exit 1，因此该清单只会被消掉、不会被静默遗忘。
