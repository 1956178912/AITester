# 2026-09-26 全面审查与保守优化轮（第八轮）

> 范围：全项目（src/ + experiments/ + tests/ + scripts/）。
> 方法：基线回归 + 4 路并行子代理深度审查（graph / api / tools / agents）+ 主代理单点核实 + 回归测试锁定。
> 原则：**默认行为不变**（所有改动均不改变任何默认开关路径的语义；新能力/修复仅在已启用分支或已锁定口径内收敛）；**保守可落地**（每项改动有最小回归测试锁定）；**全量回归零失守**（1861 测试全通过 / ruff 全绿 / mypy 全绿）。

---

## 一、审查基线（进入本轮前）

| 指标 | 数值 | 来源 |
|------|------|------|
| 全量测试 | **1832 passed / 0 failed** | `pytest tests -q` 实测（round7 未提交改动之上） |
| 静态检查 | ruff 全绿 / mypy 0 错误 | `ruff check` + `mypy src` |
| 上次提交 | `9526fd0` 第七轮审查（round7 改动处于工作区未提交） | `git log` |

**round7 遗留债务清单**（round7 文档第七节"未落地项"，本轮全部落地或记录）：
- `_last_health_check` dict 死代码（api_manager）
- `retry_count` 字段幽灵配置（api_health）
- `last_response_time_ms` 死字段（api_health）
- `dependency.py` `_importable_cache` 多线程竞态
- `type_repair.py` `_EMPTY_CALLS` 死逻辑
- `token_usage.py` 非原子 `+=`

---

## 二、本轮改动清单（按文件）

| # | 文件 | 改动 | 严重度 | 默认行为 |
|---|------|------|--------|----------|
| 1 | `src/api/api_manager.py` | 删除 `_last_health_check` dict 死代码 + 同步清理 3 处测试初始化；`_cost_weight_for` 增加可选 `llm_config` 参数修复注册时序缺陷（P1，子代理发现）；`_try_call_node` docstring 笔误 "attem"→"attempt" | P1 | 否（仅未设 LLM_N_COST_WEIGHT 时口径不变） |
| 2 | `src/api/api_health.py` | 删除 `retry_count` 幽灵配置 + `last_response_time_ms` 死字段；`avg_response_time_ms` 窗口为空口径收敛为 0.0 | P2 | 否 |
| 3 | `src/tools/dependency.py` | `_importable_cache` 加进程级锁原子化读改写（消除 --parallel 多线程 check-then-act 竞态） | P2 | 否（find_spec 幂等，仅消除重复探测） |
| 4 | `src/tools/type_repair.py` | 删除 `_EMPTY_CALLS` 死逻辑（右支查空表恒 None）；`for/async for` 目标改 `sub.target` 精确取（原 `iter_child_nodes` 宽匹配会误收集 iter 子节点为局部名）；`_builtin_allow` 改 `set(dir(builtins))` 动态生成（原硬编码 ~40 名漏掉 open/abs/iter） | P2 | 否（TYPE_REPAIR_LLM_ENABLE 默认关） |
| 5 | `src/graph/token_usage.py` | `record_usage` 加进程级 `_usage_lock` 原子化字段读改写（消除 --parallel 多线程丢更新窗口） | P2 | 否（纯内存微秒级，累计语义不变） |
| 6 | `src/graph/nodes.py` | `_HAS_FUNC_DEF_RE` 补 `(?:async\s+)?` 前缀，与 patch_applier 三处正则统一口径（graph 子代理 P1：async-only 被测模块的补丁不再被安全检查 2 误拒） | **P1** | 否（仅 async-only 边界场景由"误拒"变"正确接受"） |
| 7 | `src/graph/workflow.py` | `_should_debug` / `_route_after_diagnosis` 注释中 round7 重构后失效的行号引用（L210/L340/L350/L354/L360-366/L371-378）改为按分支描述引用（graph 子代理 P2） | P2 | 否（纯注释） |
| 8 | `src/tools/patch_applier.py` | L212 空函数集全文件替换被误拒修复（`not orig_func_names or ...`，round7 已落盘；本轮 tools 子代理终读确认 + 回归测试锁定 3 用例） | **P1** | 否（仅空函数集场景由"误拒"变"正确接受"） |
| 9 | `tests/test_2026_09_26_review_optimizations.py` | 新增 `TestPatchApplierEmptyFuncSetFullFile`（3 用例，锁定 #8） | 配套 | — |
| 10 | `tests/test_2026_09_26_review_round8.py` | 新增（22 用例，锁定 #1/#2/#3/#4/#5/#6/#7） | 配套 | — |

**改动统计**：源文件 7 个 / 测试文件 2 个（1 改 1 新增）；净增 ~450 行（含注释）。

---

## 三、P1 级缺陷修复（3 项，均已回归测试锁定）

### P1-1 `src/api/api_manager.py` — `_cost_weight_for` 注册时序缺陷
**问题**：`_init_clients`（L127）与 `add_node`（L847）都在节点入池（`health_nodes[name] = health`）**之前**调用 `_cost_weight_for(model_name)`，该方法内部 `self.health_nodes.get(model_name)` 此时恒为 None，导致 `LLMConfig.cost_weight`（config.py 从 `LLM_N_COST_WEIGHT` 环境变量 / `llm_configs.json` 注入）的回退分支永远不生效——3.4 成本感知路由在默认注册路径上静默失效，全节点恒 1.0。
**修复**：`_cost_weight_for` 增加可选参数 `llm_config: LLMConfig | None = None`，两个调用点传入手上配置对象，优先读其 `cost_weight`；`llm_config=None` 时保持原回退链（已入池节点反查 → 1.0），兼容外部调用与既有测试。
**默认行为**：不变——未设成本信息时 `LLMConfig.cost_weight=0.0`，仍回退 1.0 基准；仅"用户显式设置 LLM_N_COST_WEIGHT"这一此前静默失效的路径按文档语义生效。
**回归测试**：`TestCostWeightForRegistration`（6 用例：在手配置 / 0.0 回退 / 显式映射优先 / None 保持回退链 / add_node 注入 / 默认 1.0）。

### P1-2 `src/graph/nodes.py` — `_HAS_FUNC_DEF_RE` 不含 async 前缀
**问题**：安全检查 2 的函数定义探测正则 `^\s*def ` 不含 `async`，与 round7 已统一的 `patch_applier._TOP_DEF_RE` / `_find_function_range_ast` / 单函数模式按名正则（三处均含 `(?:async\s+)?`）口径矛盾——async-only 被测模块（目标代码与 LLM 补丁片段仅含 async def）的补丁被误判"无函数定义"拒写盘 → `target_code` 永不更新 → 修复循环空烧 token 不收敛。
**修复**：正则补 `(?:async\s+)?` 前缀，与 patch_applier 三处口径统一；注释同步说明。
**默认行为**：不变——同步 def 为主的默认数据集命中口径不变，仅 async-only 边界场景由"误拒"变"正确接受"。
**回归测试**：`TestHasFuncDefRegAsync`（4 用例：async 命中 / sync 命中 / 非 def 不命中 / 与 patch_applier 口径一致性）。

### P1-3 `src/tools/patch_applier.py` — 空函数集全文件替换被误拒
**问题**：`apply_patch_to_code` 完整文件模式 L206 旧实现 `if orig_func_names and orig_func_names.issubset(...)`，`orig_func_names` 为空集（原代码无顶层 def，纯常量/import 模块）时前置守卫短路为 False → 全文件替换永远落不到（错落到 Step 4b 单函数路径又因补丁无 def 返回 False）。
**修复**：L212 改为 `if not orig_func_names or orig_func_names.issubset(...)`（`∅.issubset(任意) == True`，空集场景正确通过；非空集路径判定口径不变）；L227 拒绝分支保留（空集时 subset 必已在 L212 通过，该分支逻辑上不可达，守卫冗余但无害，注释已说明）。
**默认行为**：不变——原代码含 def 时 `orig_func_names` 非空，`issubset` 判定与改前完全一致；仅空函数集场景由"误拒"恢复为"全文件替换成功"（本就是注释声明的设计意图"防止部分替换导致函数丢失"的对称补全）。
**回归测试**：`TestPatchApplierEmptyFuncSetFullFile`（3 用例：空集 apply / 空集 safe_apply / 非空集 subset 失败仍拒绝）。

---

## 四、P2 级改动（5 项，均低风险）

| # | 文件 | 改动 | 默认行为 |
|---|------|------|----------|
| P2-1 | `src/api/api_manager.py` + `tests/test_api_manager.py` | 删除 `_last_health_check` dict（round7 核实为死代码：只在 `__init__` 初始化，无读/写点；旧用途已被 `APIHealth.last_check_time` 取代）；3 处测试初始化同步清理 | 否 |
| P2-2 | `src/api/api_health.py` + `tests/test_api_manager.py` + `tests/test_api_manager_extended.py` | 删除 `retry_count` 幽灵配置（生产代码从未读取）+ `last_response_time_ms` 死字段（无写入点，`avg_response_time_ms` 窗口为空时回退等价于默认 0.0）；4 处测试断言同步清理；`avg_response_time_ms` 窗口为空口径显式收敛为 0.0 | 否 |
| P2-3 | `src/tools/dependency.py` | `_importable_cache` 加进程级锁（round7 遗留债务项落地）：读改写在锁内原子化，消除 --parallel 多线程同键并发 check-then-act 竞态（find_spec 幂等、持锁微秒级，判定语义不变） | 否 |
| P2-4 | `src/tools/type_repair.py` | `_EMPTY_CALLS` 死逻辑删除（右支查空表恒 None，整个 or 恒为左支）；`for/async for` 目标收集改 `sub.target` 精确取（原 `iter_child_nodes` 宽匹配会把 iter 子节点误收为局部名）；`_builtin_allow` 改 `set(dir(builtins))` 动态生成（原硬编码 ~40 名漏 open/abs/iter，LLM 层误报源） | 否（TYPE_REPAIR_LLM_ENABLE 默认关，静态层仅观测） |
| P2-5 | `src/graph/token_usage.py` | `record_usage` 各字段读改写加进程级 `_usage_lock`（round7 遗留债务项落地）：消除 --parallel 多线程并发累加同一累计器的丢更新窗口（纯内存微秒级，累计语义不变） | 否 |
| P2-6 | `src/graph/workflow.py` | `_should_debug` / `_route_after_diagnosis` 注释中 round7 重构后失效的行号引用（L210/L340/L350/L354/L354-367/L360-366/L371-378）改为按分支描述引用，消除"注释指错位置"的维护性缺陷 | 否（纯注释） |
| P2-7 | `tests/test_2026_09_26_review_optimizations.py` + `tests/test_2026_09_26_review_round8.py` | 新增 25 用例回归锁定（P1×3 + P2×4 + 口径记录） | — |

---

## 五、核实后"无需修改"项（各子代理审查确认）

| 项 | 模块 | 核实结论 |
|----|------|----------|
| `_cost_weight_for` 回退链 3 层 | `src/api/api_manager.py` | node_cost_weights > LLMConfig.cost_weight > 1.0，test_cost_aware_routing 已锁定，正确 |
| `code_analyzer.preserve_patch_ingredients` 全字段 | `src/tools/code_analyzer.py` | imports/exports/register_symbols/target_ast/called_signatures/module_constants 实测正确；`called_signatures` 切片 `lines[dec_start-1:callee_start]` 恰好含装饰器行 + def 行（不含函数体首行），与 docstring 口径一致 |
| `code_context._apply_focus_budget` L211 | `src/tools/code_context.py` | 调用方先检查 `focus_in_source`，`top_level_funcs[focus]` 不会 KeyError |
| `cross_file._topological_order` 并行边 | `src/tools/cross_file.py` | 入度按边累加、释放逐边扣减，实测顺序正确；类定义正则 `[\(:]` 覆盖 `class Foo:` / `class Foo(Bar):` / `class Foo(Base, metaclass=M):` |
| `multi_candidate.apply_multi_function_patch` | `src/tools/multi_candidate.py` | P13 预切分 + (found, line) 升序 + 未找到排末尾，语义正确 |
| `error_classifier.classify_with_context` 全量口径 | `src/agents/error_classifier.py` | round7 已落盘（注释 L330-337 详尽说明"与 extract 口径一致"），非缺陷；`classify()` 默认路径仍截前 3，历史口径不变 |
| 子进程安全 | `src/agents/executor_*.py` | 全部 `subprocess.run` 用列表参数，无 `shell=True`（round7 已核实） |
| RAG DCL 双检锁 / 文件缓存记忆 / state 工厂 / tracing 线程局部 / 图构建 4 路径 / _should_debug 分支顺序 / _route_after_diagnosis 上限门控 | `src/graph/*` | round7 已核实，本轮保持 |

---

## 六、回归验证

| 验证项 | 结果 |
|--------|------|
| 全量 pytest | **1861 passed / 0 failed**（基线 1832 + 25 新增回归 + 4 配套修正） |
| ruff check | 全绿（`ruff check src experiments scripts tests`） |
| mypy | 0 错误（62 源文件） |
| 默认行为 | 不变（P1 全部在默认关的开关路径 / 已锁定口径内收敛；P2 全部无默认行为影响） |
| 新增回归测试 | `tests/test_2026_09_26_review_round8.py`（22 用例）+ `tests/test_2026_09_26_review_optimizations.py`（新增 `TestPatchApplierEmptyFuncSetFullFile` 3 用例） |

---

## 七、零回归声明

本轮所有 P1/P2 改动均满足"**默认行为不变**"约束：
- P1-1（_cost_weight_for）：未设成本信息时仍回退 1.0，仅显式设置 LLM_N_COST_WEIGHT 的路径按文档语义生效（此前静默失效）；
- P1-2（_HAS_FUNC_DEF_RE）：同步 def 命中口径不变，仅 async-only 边界场景由"误拒"变"正确接受"；
- P1-3（patch_applier 空集守卫）：非空函数集判定口径不变，仅空函数集场景由"误拒"变"正确接受"；
- P2-1/P2-2（死代码/幽灵配置清理）：删除的生产代码本无任何读/写点，测试断言同步修正为等价口径；
- P2-3（dependency 锁）：find_spec 幂等，仅消除重复探测，判定结果不变；
- P2-4（type_repair）：TYPE_REPAIR_LLM_ENABLE 默认关，静态层仅为观测输出；
- P2-5（token_usage 锁）：纯内存微秒级读改写，累计语义不变；
- P2-6（workflow 注释）：纯注释修正，行为不变。

全量 1861 测试通过 / ruff 全绿 / mypy 全绿。
