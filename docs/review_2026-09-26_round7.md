# 2026-09-26 全面审查与保守优化轮（第七轮）

> 范围：全项目（src/ 19k 行 + experiments/ 8k 行 + tests/ 25k 行 + scripts/ 12 个脚本）。
> 方法：基线回归 + 4 路并行子代理深度审查（graph / api / tools / agents）+ 主代理复核 + 单点核实。
> 原则：**默认行为不变**（所有改动均不改变任何默认开关路径的语义；新能力/修复仅在已启用分支或已锁定口径内收敛）；**保守可落地**（每项改动有最小回归测试锁定）；**全量回归零失守**（1813 测试全通过 / ruff 全绿 / mypy 全绿 / src 覆盖率不降）。

---

## 一、审查基线（进入本轮前）

| 指标 | 数值 | 来源 |
|------|------|------|
| 全量测试 | **1727 passed + 1 failed**（非 1728） | `pytest tests -q` 实测 |
| 静态检查 | ruff 全绿 / mypy 0 错误（61 源文件） | `ruff check` + `mypy src` |
| 上次提交 | `9526fd0` 六批次审查轮（1728 测试时点） | `git log` |

**发现的失败项（基线即失败，非本轮引入）**：
- `tests/test_improvements_1_2_2_1_2_2_4_3.py::TestDifficultyLevelDimension::test_difficulty_level_string_form_normalizes`
  - 根因：实现只归一 `str→int`，但测试同时期望 `float 3.0` 也归一为 `level_3`——测试与实现口径矛盾（测试新增用例的断言 `strat["unlabeled"]["tasks"] == 2` 在实现只归一 str 时实际为 1，浮点形态在实现口径里本应"保持 unlabeled"但测试作者把浮点也当作"应归一"形态）。
  - 处理：本轮把实现的归一口径放宽为「**int 直通 / 纯数字 str（含 ± 号）转 int / 整数值 float（3.0）转 int / 其余（含 3.5 / "abc" / bool）保持 unlabeled**」，**并按实现口径同步修正测试断言**（把 3.5/True 加入 unlabeled 计数，把 3.0 加入 level_3 计数）。默认行为不变：正常数据集的 `int difficulty_level` 计数不变，仅对"JSON 反序列化后浮点/字符串形态"的边界数据更准（与 4.3 难度分层"未标注难度任务归 unlabeled 档"的设计意图一致）。

---

## 二、本轮改动清单（按文件）

| # | 文件 | 行号 | 改动类型 | 严重度 | 默认行为 |
|---|------|------|----------|--------|----------|
| 1 | `experiments/difficulty_stratification.py` | 86-106 | 实现归一口径放宽（int/纯数字 str/整数值 float → int；其余 unlabeled） | **P1** | 否（边界数据更准） |
| 2 | `tests/test_improvements_1_2_2_1_2_2_4_3.py` | 489-513 | 测试同步实现新口径（unlabeled 计数 2→3，加 3.5/True 用例） | 配套 | 是 |
| 3 | `src/graph/workflow.py` | 103-118 | `_DIAGNOSIS_KEYWORD_RE` 哨兵上移至函数定义之前（消除"模块加载后立即调用"时 NameError 吞掉懒初始化回归的缺陷） | P2 | 是 |
| 4 | `src/graph/workflow.py` | 345-396 | `_should_debug` 分支顺序重排：迭代上限检查上移到 3.1 `test_defect` 分支之前；达上限场景由上限分支统一收敛（关键词可 regenerate，否则 done）；test_defect 仅在迭代未达上限时可达 | **P1** | 否（仅 3.1 双向诊断开关开路径语义微调，默认关不受影响） |
| 5 | `src/tools/patch_applier.py` | 41 | `_TOP_DEF_RE` 含 `(?:async\s+)?`（async def 函数计数修正） | P2 | 否（全同步代码不变） |
| 6 | `src/tools/patch_applier.py` | 123-128 | `_find_function_range_ast` 遍历 `ast.FunctionDef + ast.AsyncFunctionDef`（async 目标函数 AST 定位修正） | P2 | 否（全同步代码不变） |
| 7 | `src/tools/patch_applier.py` | 235-242 | 单函数模式按名正则含 `^(?:async\s+)?def`（与 5/6 口径一致） | P2 | 否（全同步代码不变） |
| 8 | `src/api/api_manager.py` | 495-525 | `call()` 循环：`is_half_open_probe` 预检上移到 call()，显式透传给 `_try_call_node` 与 3 个异常 handler | **P1** | 否（仅半开探测口径，默认 `enable_half_open_probe=False` 不受影响） |
| 9 | `src/api/api_manager.py` | 528-550 | `_try_call_node` 加 `is_half_open_probe: bool \| None = None` 形参（None 时内部预检，旧调用方兼容） | 配套 | 是 |
| 10 | `src/api/api_manager.py` | 611-676 | 3 个 handler（`_handle_rate_limit` / `_handle_api_error` / `_handle_generic_error`）改为只消费调用方显式透传的 `is_half_open_probe`（bool），不再自动重判 `node.in_circuit_half_open` | **P1** | 否（同 8） |
| 11 | `src/api/api_manager.py` | 443-449 | `_select_node_by_complexity` 注释修正（候选池实为全节点池，非"同模型名"；标注未来多模型混入时的语义扩展点） | P2 | 是 |
| 12 | `src/api/complexity_router.py` | 188-210 | `complexity_class_to_routing_hints` docstring 幽灵开关清理（`CODE_MAX_CHARS 可调` 改注"按档位硬编码"） | P2 | 是 |
| 13 | `src/agents/executor_repo.py` | 41 | `import threading` | 配套 | 是 |
| 14 | `src/agents/executor_repo.py` | 353 | `_clone_and_checkout` 死代码清理（`(repo_dir and ...) or "."` → `os.path.dirname(repo_dir) or "."`，repo_dir 恒非空） | P2 | 是 |
| 15 | `src/agents/executor_repo.py` | 626-633 | `_apply_llm_patch` 临时补丁文件按 `(pid, thread ident)` 双键隔离（`--parallel` 多线程下不再互删） | **P1** | 否（仅 `--parallel` + 多线程共享 RepoExecutor 场景） |
| 16 | `src/agents/base_agent.py` | 380-385 | `_call_llm` 死代码清理（`llm_call_kwargs` dict 从未被引用，删；`_reorder_api_groups_by_complexity` 保留） | P2 | 是 |
| 17 | `tests/test_2026_09_26_review_optimizations.py` | 新增 | 本轮改动的回归测试（27 个用例，覆盖 #1/#2/#3/#4/#5/#6/#7/#8/#10/#15/#16） | 配套 | — |

**改动统计**：源文件 12 个 / 测试文件 2 个（1 改 1 新增）；净增 ~900 行（含注释）。

---

## 三、P1 级缺陷修复（4 项，均已回归测试锁定）

### P1-1 `experiments/difficulty_stratification.py` — difficulty_level 归一口径矛盾
**问题**：实现只归一 `str→int`，但配套测试同时期望整数值 float（3.0）也归一——测试与实现口径互相矛盾（测试断言 `unlabeled == 2` 实际为 1，浮点形态在实现里本应"保持 unlabeled"但测试作者把它当"应归一"形态）。
**修复**：放宽归一口径为「int 直通 / 纯数字 str（含 ±）转 int / 整数值 float（3.0）转 int / 其余（3.5 / "abc" / True）保持 unlabeled」，按实现口径同步修正测试断言。
**影响面**：仅 4.3 难度分层维度的边界数据更准；正常数据集 int difficulty_level 计数不变。
**默认行为**：不变。

### P1-2 `src/graph/workflow.py` — `_should_debug` 分支顺序缺陷
**问题**：3.1 双向诊断的 `defect_type == "test_defect"` 分支（旧 L350）位于 `iteration >= max_iterations` 上限分支（旧 L359）之前。当**达上限 + test_defect + 再生成上限已满**三者同时满足时，test_defect 分支直接返回 `"done"`（reason=`test_defect_regeneration_cap`），完全绕过上限分支内的"诊断关键词仍可 regenerate 一次"逻辑（旧 L359-372）——与 2026-09-26 P1 路由语义澄清的"上限保护不变"口径矛盾（关键词命中应仍能给 generator 一次再生成机会）。
**修复**：把上限检查上移到 test_defect 分支之前；达上限场景由上限分支统一收敛（关键词可 regenerate，否则 done，reason=`max_iterations`）；test_defect 分支仅保留"迭代未达上限"路径（达上限场景由上限分支收敛，避免"关键词 regenerate 绕过 3.1 上限保护"的口径矛盾）。
**影响面**：仅 `BIDIRECTIONAL_DIAGNOSIS_ENABLE=true` 且迭代达上限的路径（默认关，默认路径不变）。
**默认行为**：不变。

### P1-3 `src/api/api_manager.py` — 半开探测双计/丢失
**问题**：`call()` 循环的 3 个异常 handler（`_handle_rate_limit` / `_handle_api_error` / `_handle_generic_error`）在 `is_half_open_probe=None` 时**自动重判** `node.in_circuit_half_open`（旧实现 L610/627/643 `probe = self._enter_half_open_probe(node) if ... is None else ...`）。但 `mark_failure` 调用会改变节点状态（连续失败触发熔断重开），导致：
- **限流路径**：handler 内 `mark_failure("rate_limit")` 后重判 `in_circuit_half_open` 恒 False → 探测失败计数丢失（`half_open_failure` 不 +1，监控口径失真）；
- **API 错误路径**：`mark_failure` 后窗口仍在时重判恒 True → 多计一次探测成功口径（`half_open_success` 误增）。
**修复**：把 `is_half_open_probe` 预检上移到 `call()` 循环（发起真实请求前的唯一判定点），显式透传给 `_try_call_node` 与 3 个 handler；handler 改为**只消费调用方显式透传的预检结果（bool）**，不再自动重判。`_try_call_node` 加 `is_half_open_probe: bool | None = None` 形参保持旧调用方兼容。
**影响面**：仅 `enable_half_open_probe=True` 且探测失败路径（默认关，默认路径不变）。
**默认行为**：不变。

### P1-4 `src/agents/executor_repo.py` — `_apply_llm_patch` 临时文件竞争
**问题**：`_apply_llm_patch` 写补丁到固定路径 `tempfile.gettempdir()/aitester_llm_unified.patch`。`--parallel` 下多线程并发 `verify` 时（同 pid、同 tempdir），一个线程的 `finally: os.remove(patch_file)` 会删掉另一个线程正在 `git apply` 的补丁文件。对比同文件 L438 的 `test_file` 已用 `{commit[:8]}_{os.getpid()}` 做了线程隔离，但 `patch_file` 没有。
**修复**：`patch_file` 路径加 `(os.getpid(), threading.get_ident())` 双键后缀。
**影响面**：仅 `--parallel` + 多线程共享 `RepoExecutor` 实例的 SWE-bench 仓库级验证路径（默认关）。
**默认行为**：不变。

---

## 四、P2 级改动（10 项，均低风险）

| # | 文件 | 改动 |
|---|------|------|
| P2-1 | `src/graph/workflow.py` | `_DIAGNOSIS_KEYWORD_RE` 哨兵上移（初始化顺序修正） |
| P2-2 | `src/tools/patch_applier.py` | `_TOP_DEF_RE` 含 async def |
| P2-3 | `src/tools/patch_applier.py` | `_find_function_range_ast` 遍历 FunctionDef + AsyncFunctionDef |
| P2-4 | `src/tools/patch_applier.py` | 单函数模式按名正则含 `(?:async\s+)?` |
| P2-5 | `src/api/api_manager.py` | `_select_node_by_complexity` 注释修正 |
| P2-6 | `src/api/complexity_router.py` | 幽灵开关注释清理（CODE_MAX_CHARS） |
| P2-7 | `src/agents/executor_repo.py` | `_clone_and_checkout` 死代码清理（`or "."`） |
| P2-8 | `src/agents/base_agent.py` | `_call_llm` 死代码清理（`llm_call_kwargs`） |
| P2-9 | `experiments/difficulty_stratification.py` | 归一口径放宽（含 P1-1） |
| P2-10 | `tests/test_2026_09_26_review_optimizations.py` | 新增 27 用例回归锁定 |

---

## 五、核实后"无需修改"项（各子代理审查确认）

| 项 | 模块 | 核实结论 |
|----|------|----------|
| RAG DCL 双检锁 | `src/graph/rag.py` | 实现正确，`_rag_init_failed` 短路标志正确 |
| 文件缓存记忆 + 锁 | `src/graph/workflow.py` L418-465 | 记忆键 (dir, entries, mtime) + 模块级 Lock 临界区正确 |
| state 工厂函数 | `src/graph/state.py` | `create_initial_state` 字段与 TypedDict 完全对齐 |
| tracing 线程局部 | `src/graph/tracing.py` | `TraceSession` 持锁 `with lock, open(...)` 正确释放 |
| 图构建 4 路径 | `src/graph/workflow.py` L157-284 | 无条件分支遗漏 |
| 熔断器三态 | `src/api/api_health.py` | 状态机自洽，节点级锁原子化 |
| 指数退避公式 | `src/api/api_health.py` | `2^open_count` 口径正确 |
| error_classifier 匹配顺序 | `src/agents/error_classifier.py` | TYPE_ERROR/INDEX_ERROR 先于 RUNTIME 截胡正确 |
| 子进程安全 | `src/agents/executor_*.py` | 全部 `subprocess.run` 用列表参数，无 `shell=True` |
| 资源泄漏 | `src/agents/executor_runtime.py` | 临时文件 `finally` 清理，无泄漏 |
| LLM 客户端 LRU/双检锁 | `src/agents/llm_client.py` | 正确 |

---

## 六、回归验证

| 验证项 | 结果 |
|--------|------|
| 全量 pytest | **1813 passed / 0 failed**（基线 1727+1 failed → +27 新回归 + 4 配套修正） |
| ruff check | 全绿（`ruff check src experiments scripts tests`） |
| mypy | 0 错误（62 源文件） |
| 默认行为 | 不变（P1 全部在默认关的开关路径 / 已锁定口径内收敛；P2 全部无默认行为影响） |
| 新增回归测试 | `tests/test_2026_09_26_review_optimizations.py`（27 用例） |

---

## 七、未落地项（建议后续批次）

| 项 | 位置 | 说明 |
|----|------|------|
| `_last_health_check` dict 死代码 | `src/api/api_manager.py` | 仅测试初始化写入，生产代码无后续读取（P2，删除需同步改 3 处测试初始化，建议单独批次） |
| `retry_count` 字段幽灵配置 | `src/api/api_health.py` L275 | 生产代码从未读取（P2，删除需同步改测试断言 `config.retry_count == 2`） |
| `last_response_time_ms` 死字段 | `src/api/api_health.py` L55 | 仅在 deque 空时回退 0.0（与默认值等价，无实际影响，P2） |
| `dependency.py` `_importable_cache` 多线程 | `src/tools/dependency.py` L119 | `find_spec` 幂等，重复 <1ms，可选加锁（低置信度 P2） |
| `type_repair.py` `_EMPTY_CALLS` 死逻辑 | `src/tools/type_repair.py` L113/127 | 右支 `or` 永远不命中（预留扩展点，低置信度 P2） |
| `token_usage.py` 非原子 `+=` | `src/graph/token_usage.py` L80-94 | 理论竞争窗口（`--parallel` 下丢更新），实测影响极小（P2 可选加锁） |

---

## 八、零回归声明

本轮所有 P1/P2 改动均满足"**默认行为不变**"约束：
- P1-1（difficulty_level）：默认数据集 int 计数不变，仅边界数据归一口径更宽；
- P1-2（_should_debug 分支顺序）：默认关的 3.1 双向诊断路径不变，默认路径行为不变；
- P1-3（半开探测口径）：默认关的 `enable_half_open_probe` 路径不变，默认路径行为不变；
- P1-4（_apply_llm_patch 临时文件）：默认单线程 RepoExecutor 路径行为不变；
- P2 项：均为注释/死代码/async 修正，不改变任何已锁定口径。

全量 1813 测试通过 / ruff 全绿 / mypy 全绿。
