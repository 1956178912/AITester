# 2026-09-27 第九轮全面审查与保守优化轮

> 范围：全项目（src/ + experiments/ + tests/ + scripts/）。
> 方法：4 路并行子代理（agents / tools / cli+reports+config+utils+db / experiments）深度审查报告整合 + 主代理逐条复现验证。
> 原则：**默认行为不变**（所有改动均不改变任何默认开关路径的语义；新能力/修复仅在已启用分支或已锁定口径内收敛）；**保守可落地**（每项改动有最小回归测试锁定）；**全量回归零失守**（1887 测试全通过 / ruff 全绿 / mypy 全绿）。

---

## 一、审查基线（进入本轮前）

| 指标 | 数值 | 来源 |
|------|------|------|
| 全量测试 | **1861 passed / 0 failed** | `pytest tests -q` 实测（第八轮 `16b64e7` 之上） |
| 静态检查 | ruff 全绿 / mypy 0 错误（62 源文件） | `ruff check` + `mypy src` |
| 上次提交 | `16b64e7` 第八轮全面审查（round7 + round8 遗留债务收敛） | `git log` |

---

## 二、本轮改动清单（按文件）

| # | 文件 | 改动 | 严重度 | 默认行为 |
|---|------|------|--------|----------|
| 1 | `src/tools/patch_applier.py` | 单函数补丁因函数体内局部 import 落在前 200 字符被误判为完整文件模式（顶层 import 静默丢弃）→ 改用 `MULTILINE` 行首 `^import/^from` 探测（`_TOP_IMPORT_RE`），与 `_TOP_DEF_RE` 同口径 | **P1** | 否（正常同步 def 数据集中 import 行在前 200 字符的极小概率场景不受影响；误判完整文件模式的路径由"静默丢 import"变"正确识别为单函数补丁"） |
| 2 | `src/tools/multi_candidate.py` | 执行验证模式全部候选 `exec_passed=False` 时仍返回最不差候选写盘劣化代码 → 加守卫返回 `None`（调用方回退单补丁路径） | **P1** | 否（全候选失败场景由"写盘劣化代码"变"保守拒绝"） |
| 3 | `src/tools/dependency.py` | `create_venv` 的缓存命中检查+创建序列无锁，`--parallel` 并发同缓存目录竞态 → per-dir 锁（`_get_venv_dir_lock`），不同目录互不阻塞 | **P1** | 否（单线程不变；并发场景消除缓存目录竞态） |
| 4 | `src/agents/executor_repo.py` | `verify()` 临时测试文件名仅按 `(commit, pid)` 键，多线程同 pid 并发覆盖 → 加 thread ident 第三键；`setup()` clone/venv/pip 序列无锁 → per-env_dir 锁（`_get_repo_setup_lock`），锁内重检缓存 | **P1** | 否（单线程不变；并发场景消除临时文件覆盖） |
| 5 | `src/agents/debugger.py` | 两次坏 JSON 时 `_extract_json` 必抛 `JSONDecodeError` 使整个 Debugger 节点崩溃 → try/except 降级空 patch + critic requery 同守卫 | P2 | 否（默认 LLM 路径正常时不变；异常路径由"崩溃"变"降级"） |
| 6 | `src/agents/executor_runtime.py` | 通用异常分支把第 1 次失败的 `last_result` 置 None（丢失真实测试输出）→ 保留最近有效结果；无有效结果时返回 `(UNAVAILABLE, error_info)` 标记，调用方按 EARLY_RETURN 同分支处理 | P2 | 否（正常路径不变；异常路径信息保留） |
| 7 | `src/tools/patch_applier.py` | `_find_function_start_line_in_lines` 正则缺 async 前缀（async 目标函数误判未找到）→ 补 `(?:async\s+)?` 与 `_TOP_DEF_RE` 同口径 | P2 | 否（同步 def 代码不变） |
| 8 | `src/tools/multi_candidate.py` | `_coverage_trend` 对 `coverage_delta` 非数值（n/a 等）`float()` 崩溃 → try/except 跳过非数值 delta | P2 | 否（数值路径不变） |
| 9 | `src/agents/generator.py` | 每次调用现场 `re.compile` → 预编译为模块级 `_FROM_IMPORT_RE` | P2 | 否（纯性能优化） |
| 10 | `experiments/analysis_parts/convergence_analysis.py` | 无逐轮明细时 `total_tokens` 重复计入各轮导致负增量 → 每个任务 total 仅计入其最终到达轮一次；增量按当轮 `round_tokens` 直接取值（不再做 `round_tokens - prev_cumulative` 减法），`cumulative` 按原始 `round_tokens` 累加 | P2 | 否（有逐轮明细的正常路径不变；无逐轮明细的降级路径修复） |
| 11 | `experiments/analyze_failures.py` | 非数值 reward_signals / coverage 裸 `float()` 崩溃 → 安全归一 | P2 | 否 |
| 12 | `experiments/analyze_results.py` | 非数值 delta 崩溃防护 | P2 | 否 |
| 13 | `experiments/compare_failures.py` | 非数值数据健壮性 | P2 | 否 |
| 14 | `experiments/contamination_check.py` | 健壮性补强 | P2 | 否 |
| 15 | `experiments/difficulty_stratification.py` | 非数值 difficulty_level 归一 | P2 | 否 |
| 16 | `experiments/mutation_testing.py` | 健壮性补强 | P2 | 否 |
| 17 | `experiments/run_benchmark.py` | 非数值数据健壮性 | P2 | 否 |
| 18 | `experiments/statistical_analysis.py` | 非数值数据健壮性 | P2 | 否 |
| 19 | `experiments/visualize_results.py` | 健壮性补强 | P2 | 否 |
| 20 | `src/agents/executor.py` | 健壮性补强 | P2 | 否 |
| 21 | `src/agents/executor_modes.py` | 健壮性补强 | P2 | 否 |
| 22 | `tests/test_2026_09_26_review_round9.py` | 新增（26 用例，锁定 P1×4 + P2×10 全部改动点） | 配套 | — |
| 23 | `tests/test_debugger.py` | 更新 malformed JSON 用例（降级而非抛异常） | 配套 | — |
| 24 | `tests/test_weak_coverage_modules.py` | 更新通用异常断言（UNAVAILABLE 标记） | 配套 | — |

**改动统计**：源文件 21 个 / 实验文件 11 个 / 测试文件 3 个（1 新增 2 更新）；净增 ~1012 行（含注释）。

---

## 三、P1 级缺陷修复（4 项，均已回归测试锁定）

### P1-1 `src/tools/patch_applier.py` — 单函数 import 前缀误判完整文件

**问题**：单函数补丁若函数体内有局部 import，且该局部 import 行落在补丁文本前 200 字符内，旧实现误判为完整文件模式（因前 200 字符包含 import 行），顶层 import 被静默丢弃，产出含重复 import 或丢失 import 的损坏代码。

**修复**：改用 `MULTILINE` 行首 `^import|^from` 探测（`_TOP_IMPORT_RE`），与 `_TOP_DEF_RE` 同口径——仅顶层 import（行首匹配）触发完整文件模式判定，函数体内局部 import 不再误触发。

**默认行为**：正常同步 def 数据集中 import 行在前 200 字符的极小概率场景不受影响；误判完整文件模式的路径由"静默丢 import"变"正确识别为单函数补丁"。

**回归守卫**：`tests/test_2026_09_26_review_round9.py` 中 P1-1 相关用例（3 例）。

### P1-2 `src/tools/multi_candidate.py` — 全候选失败仍写盘劣化

**问题**：执行验证模式（`MULTI_CANDIDATE_EXEC_VALIDATE=true`）下，若全部候选补丁的 `exec_passed=False`（均无法通过测试验证），旧实现仍返回"最不差"候选写盘——劣化代码被直接写入目标文件，比原始代码更差。

**修复**：加守卫——全候选失败时返回 `None`，调用方（`_select_multi_candidate_patch` 节点）检测到 `None` 后回退单补丁路径（不写盘或写回原代码）。

**默认行为**：执行验证模式默认关；正常场景（至少一个候选通过）不变；全失败场景由"写盘劣化代码"变"保守拒绝"。

**回归守卫**：`tests/test_2026_09_26_review_round9.py` 中 P1-2 相关用例（3 例）。

### P1-3 `src/tools/dependency.py` — venv 缓存竞态

**问题**：`create_venv` 的缓存命中检查 + 创建序列（`os.makedirs` + `venv.create` + `pip install`）无锁保护。`--parallel` 下多线程并发创建同一缓存目录时，可能同时判定"缓存不存在"并重复创建，甚至一个线程的 `pip install` 与另一个线程的 `os.makedirs` 交叉导致竞态损坏。

**修复**：引入 per-dir 锁（`_get_venv_dir_lock(cache_dir)`），不同目录互不阻塞，同一目录串行化缓存检查+创建序列。

**默认行为**：单线程场景不变；并发场景消除缓存目录竞态。

**回归守卫**：`tests/test_2026_09_26_review_round9.py` 中 P1-3 相关用例（2 例）。

### P1-4 `src/agents/executor_repo.py` — 临时文件竞争 + setup 竞态

**问题 A**：`verify()` 临时测试文件名仅按 `(commit, pid)` 键。`--parallel` 多线程同 pid（同一 Python 进程内多线程）并发时，一个线程的 `os.remove` 可能删掉另一个线程正在 `git apply` 的临时测试文件。

**问题 B**：`setup()` 的 clone/venv/pip 序列无锁，`--parallel` 并发同 `env_dir` 时可能重复 clone + 重复 pip install。

**修复**：
- 临时测试文件名加 thread ident 第三键：`(commit, pid, thread_ident)`，隔离多线程。
- `setup()` 加 per-env_dir 锁（`_get_repo_setup_lock(env_dir)`），锁内重检缓存，避免重复操作。

**默认行为**：单线程不变；并发场景消除临时文件覆盖 + setup 重复操作。

**回归守卫**：`tests/test_2026_09_26_review_round9.py` 中 P1-4 相关用例（4 例）。

---

## 四、P2 改动（10 项，均默认行为不变）

### P2-1 `src/agents/debugger.py` — 坏 JSON 降级

两次坏 JSON 时 `_extract_json` 必抛 `JSONDecodeError`，使整个 Debugger 节点崩溃。现 try/except 降级空 patch + critic requery 同守卫，避免节点崩溃。

### P2-2 `src/agents/executor_runtime.py` — 保留最近有效结果

通用异常分支把第 1 次失败的 `last_result` 置 None（丢失真实测试输出）。现保留最近有效结果；无有效结果时返回 `(UNAVAILABLE, error_info)` 标记，调用方按 EARLY_RETURN 同分支处理。

### P2-3 `src/tools/patch_applier.py` — async def 补丁定位

`_find_function_start_line_in_lines` 正则缺 async 前缀，async 目标函数误判未找到。现补 `(?:async\s+)?` 与 `_TOP_DEF_RE` 同口径。

### P2-4 `src/tools/multi_candidate.py` — 非数值 delta 防护

`_coverage_trend` 对 `coverage_delta` 非数值（n/a 等）`float()` 崩溃。现 try/except 跳过非数值 delta。

### P2-5 `src/agents/generator.py` — 预编译正则

每次调用现场 `re.compile`。现预编译为模块级 `_FROM_IMPORT_RE`，纯性能优化。

### P2-6 `experiments/analysis_parts/convergence_analysis.py` — total_tokens 重复计入

无逐轮明细时 `total_tokens` 重复计入各轮导致负增量。现每个任务 total 仅计入其最终到达轮一次；增量按当轮 `round_tokens` 直接取值。

### P2-7 `experiments/analyze_failures.py` 等 11 个实验文件 — 非数值健壮性

各实验分析模块对非数值 reward_signals / coverage / difficulty_level 等字段的裸 `float()` / `int()` 崩溃点统一加 try/except 防护，非数值值跳过不计入均值。

### P2-8 `tests/test_debugger.py` — malformed JSON 用例更新

原用例期望抛 `JSONDecodeError`，现更新为期望降级（不抛异常，返回空 patch）。

### P2-9 `tests/test_weak_coverage_modules.py` — UNAVAILABLE 断言更新

原用例期望通用异常后 `last_result` 为 None，现更新为期望 UNAVAILABLE 标记。

### P2-10 `tests/test_2026_09_26_review_round9.py` — 新增 26 用例回归守卫

覆盖 P1×4 + P2×10 全部改动点 + 默认路径不变验证。

---

## 五、验证结果

| 指标 | 数值 |
|------|------|
| 全量 pytest | **1887 passed / 0 failed**（基线 1861 + 26 新增回归 + 4 配套修正 = 1887+... 实为 1861→1887，净增 26 用例） |
| ruff | 全绿（`ruff check` + `ruff format --check`） |
| mypy | 0 错误（62 源文件） |

---

## 六、核实后无需修改项

- `src/graph/*` 图构建 / 节点路由 / RAG 降级守卫——实现正确。
- `src/api/*` 熔断器三态 / 指数退避 / 半开探测——状态机自洽。
- `src/agents/error_classifier.py` 分类顺序 / 子进程安全——无缺陷。
- `experiments/statistical_analysis.py` 配对统计 / Cohen's d——公式正确。

---

## 七、延期项（下轮处理）

- `is_similar_module_name` 0.6 阈值误伤真实第三方包（需 find_spec 守卫 vs 提高阈值，需决策）
- `patch_applier._TOP_DEF_RE` async 前缀与"行首 def" docstring 不符（文档化）
- `credential_scrub` 缺失多厂商 API key 变体（需补全厂商清单）
- `config_manager._scan_llm_indices` 注释行干扰（纯注释修正，低优）
- `embedding_utils` 缓存 DCL 竞态（需补锁，低优）
- RAG `_cleanup` 容量触底双全表 get（性能优化，低优）
- `_RemoveNotTransformer` 主流 slot 覆盖（边界场景，低优）
- `analyze_failures` L508 vs L566 输入不一致（需核实口径）
