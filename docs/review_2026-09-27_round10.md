# 2026-09-27 第十轮全面审查与保守优化轮

> 范围：全项目（src/ + experiments/ + tests/ + scripts/）。
> 方法：4 路并行子代理（graph / api / datasets / tools / agents 全域深审）+ 主代理逐条复现验证（`extract_json_object` / `_should_debug` / `patch_applier` / `dependency` / `debugger` / `executor_repo` 均经 `.venv/bin/python` 实证）。
> 原则：**默认行为不变**（所有改动均不改变任何默认开关路径的语义；新能力/修复仅在已启用分支或已锁定口径内收敛）；**保守可落地**（每项改动有最小回归测试锁定）；**全量回归零失守**（1920 测试全通过 / ruff 全绿 / mypy 全绿）。

---

## 一、审查基线（进入本轮前）

| 指标 | 数值 | 来源 |
|------|------|------|
| 全量测试 | **1887 passed / 0 failed** | `pytest tests -q` 实测（第九轮 `98b478a` 之上） |
| 静态检查 | ruff 全绿 / mypy 0 错误（62 源文件） | `ruff check` + `mypy src` |
| 上次提交 | `98b478a` 第九轮全面审查（round9 改动处于工作区） | `git log` |

---

## 二、本轮改动清单（按文件）

| # | 文件 | 改动 | 严重度 | 默认行为 |
|---|------|------|--------|----------|
| 1 | `src/graph/nodes.py` | `_suggest_iteration_strategy` 非数值 `coverage_delta`（"n/a"/dict 等历史落盘异常值）裸 `float()` 崩溃 executor 节点 → try/except 跳过该条目（口径：非数值 delta 视为无信号，与 None 同语义） | **P1** | 否（数值路径零变化） |
| 2 | `src/agents/base_agent.py` | 负缓存 `_lru_negatives` 无容量上限（长程 benchmark 内存无界增长）→ 与正缓存同 `_LRU_MAXSIZE` 上限 FIFO 淘汰 | **P1** | 否（正缓存行为不变；负缓存新增容量上限） |
| 3 | `experiments/analysis_parts/rag_analysis.py` | `_rag_similarity_distribution` 负 `max_similarity` 致 `bins` 键 KeyError 崩溃整份 `build_analysis` → 下界钳位到 0 + 非数值 `float()` try/except 跳过 | **P1** | 否（正常 [0,1] 区间不变） |
| 4 | `experiments/analysis_parts/convergence_analysis.py` | `_execution_trace_summary` 非数值 `reward_signals` / `coverage`（"high"/"80%"/dict 等）裸 `float()` 崩溃 → `contextlib.suppress` 跳过（口径：非数值不计入均值） | **P1** | 否（数值路径不变） |
| 5 | `experiments/statistical_analysis.py` | `_pair_by_task` 跨批次重复 `task_id` 旧 dict 推导"末者胜"静默丢弃早期批次（样本量被截断且不确定）→ 首见优先去重 + warning 日志（口径可追溯） | **P1** | 否（无重复 task_id 场景不变） |
| 6 | `experiments/run_benchmark.py` | 汇总裸 `r["iterations"]` / `r["elapsed_seconds"]` 在键存在但值为 None 时 KeyError/TypeError 崩溃 → `r.get(...) or 0` 防护（缺省语义：该任务未记录，贡献 0） | **P1** | 否（正常记录场景不变） |
| 7 | `src/agents/executor_repo.py` | `verify()` 流程注释与 docstring "git stash" 措辞改为实际实现 "git checkout -- . / clean -fd"（grep 确认 verify 体无 stash） | P2 | 否（纯注释/docstring） |
| 8 | `src/agents/executor_runtime.py` | `TimeoutExpired` 分支：第 2 次超时不再覆盖第 1 次有效 pytest 输出（追加 `[timeout attempt N]` 快照，对齐 round9 通用异常追加口径；单次超时场景 `last_output` 原为空串，结果不变） | P2 | 否 |
| 9 | `src/agents/generator.py` | `_fix_import_module` 带点路径（pkg.mod）裸子串 `code.replace` 会把包形式 `from pkg import mod` 也误改（残留损坏导入）→ 按模块名锚定的正则（与 `executor_imports` 同口径），仅替换精确匹配的 `from {wm} import` 行首 | P2 | 否（无点路径场景不变） |
| 10 | `src/cli/app.py` | `--verbose + --json` 组合：`--json` 静音 stdout 使 DEBUG 日志无法输出，旧实现静默吞掉 flag 冲突 → 显式提示 verbose 在 `--json` 模式下不生效 | P2 | 否（单 flag 场景不变） |
| 11 | `src/datasets/dataset_loader.py` | `total_test_count` 兜底口径：旧 `len(FAIL_TO_PASS)` 分母漏计 P2P（通过率先被低估）→ `len(F2P) + len(P2P)`（SWE-bench 官方 "total = F2P + P2P" 语义），官方字段存在时仍以官方值为准 | P2 | 否（官方字段存在时不变） |
| 12 | `src/reports/generator.py` | `error_context` None 字段渲染 "None" 语义不清 → 渲染 "未知"/"—"（`to_text` 与 `to_markdown` 双格式同口径） | P2 | 否（非 None 场景不变） |
| 13 | `src/tools/code_context.py` | `_closure_names` depth=N 口径文档澄清（N 层被调，焦点自身 0 层；边界层 N+1 函数名进 key 但不展开） | P2 | 否（纯 docstring） |
| 14 | `experiments/analysis_parts/convergence_analysis.py` | 模块级 `_safe_int` / `_safe_float` 辅助 + 所有裸 `int()` / `float()` 转换点（`_repair_convergence_curve` / `_metrics`、`_convergence_token_efficiency` 含逐轮明细 fallback、`_difficulty_stratified_iterations`、`_quality_proxy_metrics` 均值/中位数、`_convergence_failure_modes`）统一安全归一（非数字回退 0） | P2 | 否（数值路径不变） |
| 15 | `experiments/analysis_parts/rag_analysis.py` | `_iter_rag_stats` 生成器跳过非 dict 元素（历史落盘/手动编辑 JSON 混入），3 个调用点更新；`_rag_token_efficiency` `iterations` / `total_tokens` 经 `_safe_int` / `_safe_float` 归一；`_rag_similarity_distribution` 均值按截断后 [0,1] 口径（与分桶一致） | P2 | 否 |
| 16 | `experiments/compare_failures.py` | `cross_batch_comparison`：`regressed` 排除 `new_categories`（品牌新类别 [0,0,1] 同时被列"恶化"与"新增"→ 渲染层混淆） | P2 | 否（非新增类别不变） |
| 17 | `experiments/run_benchmark.py` | L701：`results[baseline]["mutation_feedback"]` 死写（L711 `_build_task_result` 整体替换新 dict，键消失）→ 删除死写，仅保留 `final_state["mutation_feedback"]`（workflow 下轮 Generator 消费，正确） | P2 | 否 |
| 18 | `experiments/statistical_analysis.py` | `run_all_statistics`：区分两种 nan 成因（n_pairs < 3 样本量不足 vs 配对差值全 0 零方差），旧文案统一报 "n<3" 误诊 | P2 | 否（正常场景不变） |
| 19 | `experiments/statistical_analysis.py` | `cohens_d` docstring：n_pairs < 2 实际返回 `(nan, n_pairs)`（0 或 1），旧 doc 声称恒返回 0 → 修正 | P2 | 否（纯 docstring） |
| 20 | `experiments/analyze_failures.py` | 非数值数据健壮性补强 | P2 | 否 |
| 21 | `experiments/analyze_results.py` | 非数值数据健壮性补强 | P2 | 否 |
| 22 | `experiments/contamination_check.py` | 健壮性补强 | P2 | 否 |
| 23 | `experiments/difficulty_stratification.py` | 非数值数据健壮性补强 | P2 | 否 |
| 24 | `experiments/mutation_testing.py` | 健壮性补强 | P2 | 否 |
| 25 | `experiments/visualize_results.py` | 健壮性补强 | P2 | 否 |
| 26 | `src/agents/executor.py` | 健壮性补强 | P2 | 否 |
| 27 | `src/agents/executor_modes.py` | 健壮性补强 | P2 | 否 |
| 28 | `tests/test_2026_09_27_review_round10.py` | 新增（33 用例，锁定 P1×6 + P2×13 全部改动点 + 默认路径不变验证） | 配套 | — |

**改动统计**：源文件 15 个 / 实验文件 11 个 / 测试文件 1 个（新增）；净增 ~867 行（含注释）。

---

## 三、P1 级缺陷修复（6 项，均已回归测试锁定）

### P1-1 `src/graph/nodes.py::_suggest_iteration_strategy` — 非数值 coverage_delta 崩溃

**问题**：`_suggest_iteration_strategy` 读取 `state.get("coverage_delta")` 后裸 `float(delta)` 做迭代策略判定。历史落盘结果中 `coverage_delta` 可能为 "n/a"（字符串）、dict 等非数值异常值，裸 `float()` 崩溃 executor 节点，整条工作流中断。

**修复**：try/except 跳过该条目（口径：非数值 delta 视为无信号，与 None 同语义），正常数值路径零变化。

**回归守卫**：`tests/test_2026_09_27_review_round10.py` 中 P1-1 相关用例（3 例）。

### P1-2 `src/agents/base_agent.py::_lru_store` — 负缓存无上限

**问题**：`_lru_negatives` dict 无容量上限，长程 benchmark 运行中负缓存条目只增不减，内存无界增长。

**修复**：与正缓存同 `_LRU_MAXSIZE` 上限，FIFO 淘汰最早插入的负缓存条目。

**回归守卫**：`tests/test_2026_09_27_review_round10.py` 中 P1-2 相关用例（3 例）。

### P1-3 `experiments/analysis_parts/rag_analysis.py::_rag_similarity_distribution` — bins KeyError

**问题**：`_rag_similarity_distribution` 计算分桶时 `max_similarity` 为负值（历史落盘异常），`bins` 字典键计算越界致 KeyError，崩溃整份 `build_analysis`。

**修复**：下界钳位到 0（`max(0.0, max_similarity)`）+ 非数值 `float()` try/except 跳过。

**回归守卫**：`tests/test_2026_09_27_review_round10.py` 中 P1-3 相关用例（3 例）。

### P1-4 `experiments/analysis_parts/convergence_analysis.py::_execution_trace_summary` — 非数值崩溃

**问题**：`_execution_trace_summary` 对 `reward_signals` / `coverage` 字段裸 `float()` 转换，"high"/"80%"/dict 等历史异常值崩溃。

**修复**：`contextlib.suppress` 跳过非数值条目（口径：非数值不计入均值）。

**回归守卫**：`tests/test_2026_09_27_review_round10.py` 中 P1-4 相关用例（3 例）。

### P1-5 `experiments/statistical_analysis.py::_pair_by_task` — 跨批次静默丢弃

**问题**：`_pair_by_task` 用 dict 推导配对，跨批次重复 `task_id` 时旧实现"末者胜"，早期批次被静默丢弃（样本量被截断且不确定），统计分析结果不可信。

**修复**：首见优先去重 + warning 日志，确保样本量可追溯。

**回归守卫**：`tests/test_2026_09_27_review_round10.py` 中 P1-5 相关用例（3 例）。

### P1-6 `experiments/run_benchmark.py` 汇总 — None 值崩溃

**问题**：汇总阶段裸 `r["iterations"]` / `r["elapsed_seconds"]`，在键存在但值为 None 时 KeyError/TypeError 崩溃（历史落盘部分任务未记录这些字段）。

**修复**：`r.get("iterations", 0) or 0` / `r.get("elapsed_seconds", 0) or 0` 防护（缺省语义：该任务未记录，贡献 0），`total_time` 同步。

**回归守卫**：`tests/test_2026_09_27_review_round10.py` 中 P1-6 相关用例（3 例）。

---

## 四、P2 改动（13 项，均默认行为不变）

### P2-1 `src/agents/executor_repo.py` — verify() 注释/docstring 措辞

`verify()` 流程注释与 docstring 写 "git stash"，实际实现是 `git checkout -- . / clean -fd`（grep 确认 verify 体无 stash）。改为实际实现描述。

### P2-2 `src/agents/executor_runtime.py` — TimeoutExpired 快照追加

第 2 次超时不再覆盖第 1 次有效 pytest 输出，改为追加 `[timeout attempt N]` 快照（对齐 round9 通用异常追加口径）。单次超时场景 `last_output` 原为空串，结果不变。

### P2-3 `src/agents/generator.py::_fix_import_module` — 带点路径误改

带点路径（pkg.mod）裸子串 `code.replace` 会把包形式 `from pkg import mod` 也误改（残留损坏导入）。改为按模块名锚定的正则（与 `executor_imports` 同口径），仅替换精确匹配的 `from {wm} import` 行首。

### P2-4 `src/cli/app.py` — --verbose + --json 冲突提示

`--json` 静音 stdout 使 DEBUG 日志无法输出，旧实现静默吞掉 flag 冲突。现显式提示 verbose 在 `--json` 模式下不生效。

### P2-5 `src/datasets/dataset_loader.py` — total_test_count 兜底口径

旧 `len(FAIL_TO_PASS)` 分母漏计 P2P（通过率先被低估）。改为 `len(F2P) + len(P2P)`（SWE-bench 官方 "total = F2P + P2P" 语义），官方字段存在时仍以官方值为准。

### P2-6 `src/reports/generator.py` — error_context None 渲染

None 字段渲染 "None" 语义不清，改为渲染 "未知"/"—"（`to_text` 与 `to_markdown` 双格式同口径）。

### P2-7 `src/tools/code_context.py::_closure_names` — depth 口径文档澄清

depth=N 口径文档澄清：N 层被调，焦点自身 0 层；边界层 N+1 函数名进 key 但不展开。纯 docstring 修正。

### P2-8 `experiments/analysis_parts/convergence_analysis.py` — 安全归一

模块级 `_safe_int` / `_safe_float` 辅助 + 所有裸 `int()` / `float()` 转换点统一安全归一（非数字回退 0）。

### P2-9 `experiments/analysis_parts/rag_analysis.py` — 非 dict 跳过

`_iter_rag_stats` 生成器跳过非 dict 元素（历史落盘/手动编辑 JSON 混入），3 个调用点更新。`_rag_token_efficiency` 经 `_safe_int` / `_safe_float` 归一。`_rag_similarity_distribution` 均值按截断后 [0,1] 口径。

### P2-10 `experiments/compare_failures.py` — regressed 排除 new_categories

品牌新类别 [0,0,1] 同时被列"恶化"与"新增"导致渲染层混淆。现 `regressed` 排除 `new_categories`。

### P2-11 `experiments/run_benchmark.py` — 死写删除

L701 `results[baseline]["mutation_feedback"]` 死写（L711 `_build_task_result` 整体替换新 dict，键消失）。删除死写，仅保留 `final_state["mutation_feedback"]`（workflow 下轮 Generator 消费，正确）。

### P2-12 `experiments/statistical_analysis.py` — nan 成因区分

`run_all_statistics` 区分两种 nan 成因（n_pairs < 3 样本量不足 vs 配对差值全 0 零方差），旧文案统一报 "n<3" 误诊。`cohens_d` docstring 修正（n_pairs < 2 实际返回 `(nan, n_pairs)`，旧 doc 声称恒返回 0）。

### P2-13 实验文件健壮性补强

`experiments/analyze_failures.py` / `analyze_results.py` / `contamination_check.py` / `difficulty_stratification.py` / `mutation_testing.py` / `visualize_results.py` 非数值数据健壮性补强 + `src/agents/executor.py` / `executor_modes.py` 健壮性补强。

---

## 五、验证结果

| 指标 | 数值 |
|------|------|
| 全量 pytest | **1920 passed / 0 failed**（基线 1887 + 33 新增回归 = 1920） |
| ruff | 全绿（`ruff check` + `ruff format --check`，220 文件） |
| mypy | 0 错误（62 源文件） |

---

## 六、核实后无需修改项

- `cross_file` 拓扑排序（Kahn + 字典序）/ `from X import *` 星号导入漏边（opt-in 保守口径）/ `code_context` 类方法同名冲突（保守 setdefault 口径）/ `patch_applier` AST vs 正则兜底路径一致性 / `type_repair` 类型家族保守口径 / `multi_candidate` credit 默认 0.0 防御写法 / `dependency` `_importable_cache` 无锁双读（幂等无损坏）/ `executor_imports` LRU 失效（单任务顺序路径不触发）/ `llm_client` zai 双层重试（deadline 快速失败机制既有）——均为设计口径或 opt-in 路径，默认行为不变，留作记录。

---

## 七、延期项（下轮处理或需决策）

- `is_similar_module_name` 0.6 阈值误伤真实第三方包（需 find_spec 守卫 vs 提高阈值，需决策）
- `patch_applier._TOP_DEF_RE` async 前缀与"行首 def" docstring 不符（文档化）
- `credential_scrub` 缺失多厂商 API key 变体（需补全厂商清单）
- `config_manager._scan_llm_indices` 注释行干扰（纯注释修正，低优）
- `embedding_utils` 缓存 DCL 竞态（需补锁，低优）
- RAG `_cleanup` 容量触底双全表 get（性能优化，低优）
- `_RemoveNotTransformer` 主流 slot 覆盖（边界场景，低优）
- `analyze_failures` L508 vs L566 输入不一致（需核实口径）
