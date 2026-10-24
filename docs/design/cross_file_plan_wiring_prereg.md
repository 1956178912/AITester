# D3b 跨文件图通路接线（`build_cross_file_repair_plan`）：设计与预注册草案

> 状态：**Step A 已实装（2026-10-18 第三轮独立评审落地，双开关默认关、OFF/OFF 与历史逐位一致）；Step B（多模块协同修复）与 D3b-AB1 跑批未执行。AA 轮（2026-10-19）完成 Step B 四件前置件核查并把它钉成 3 例反面锁定，见 §3.5。**
> 归属：T4 / T 轮 2026-10-18；承接 O 轮登记（`docs/PROJECT_STATUS_REGISTER.md`
> §4 "D3b：`build_cross_file_repair_plan` 图内零调用点"）。
> 结论先行（**T 轮切点、实装前**）：**接线会改变跨文件任务的 LLM 调用数与 debugger 的修复路由**
> （下游已有消费点），当时不满足"默认关接线且不改路由行为"的判据 → 只做
> 设计 + 预注册草案。**U 轮已按本文件 §3 Step A 实装**（双开关默认关，OFF/OFF
> 与历史逐位一致，实装口径修正见 §1.5）；Step B / D3b-AB1 仍待下一轮。

## 1.5 实现备注（2026-10-18 Step A 落地，对 §3 的两处修正）

1. **生产节点位置修正**：§3 原写"`_cross_file_analyzer_node` 调
   `build_cross_file_repair_plan_cached`"——实测不可行：builder 需要
   `debugger` 实例与 `test_output`/`failed_cases`，而 analyzer 运行于执行
   前、三者均不在场。实装改为 **`_debugger_node` 的 LLM 分支**（确定性接管
   分支不构建——避免白烧调用），构建结果经节点 `update` 写
   `state["cross_file_plan"]`（覆盖 analyzer 的 None 占位）；BUILD 关时
   不写键，返回键集合与历史逐位一致。
2. **消费门控层级修正**：`CROSS_FILE_PLAN_CONSUME_ENABLE` 仅门控 **plan
   读取**；"依赖边末元素"回退是 plan 入图前的历史口径，任何开关下保留
   （首版实现曾把整个 `if cross_file_deps` 块纳入门控，被契约测试
   `test_consume_off_ignores_plan_in_state` 抓住——默认配置会丢失回退、
   构成行为变化；已修复并为该对偶用例建档）。
3. 回归锁：`tests/test_cross_file_plan_wiring.py`（13 例：双开关默认 /
   读取、消费门控 6 情形、节点构建 4 情形含失败降级）；
   `tests/test_debugger_node_branches.py::TestResolveTargetModule` 增补
   消费关对偶用例。

## 1. 实装前切点现状（2026-10-18 T 轮切点；Step A 后已变化，见 §1.5）

### 1.1 实装前：图内零调用点（历史证据）

```
$ grep -rn "build_cross_file_repair_plan(" src/graph/
（无输出——仅 nodes.py:1954 注释提到该函数）
$ grep -rn "build_cross_file_repair_plan(" src/ experiments/ tests/ scripts/ --include=*.py
src/tools/cross_file.py:801                       # build_cross_file_repair_plan_cached 内部调用（工具层自用）
tests/test_cross_file.py / test_o_round_cross_file_analyzer.py   # 单测
experiments/results/o_round_cross_file_20261017/_helpers/*.py   # O 轮组件级证据脚本
```

- `src/graph/nodes.py::_cross_file_analyzer_node` 只做 AST 依赖分析，计划落态是
  **硬编码占位**：`update["cross_file_plan"] = None  # 占位，待二期实现完整计划构建`。
- `src/tools/cross_file.py::build_cross_file_repair_plan`（协调器-提议者）**零生产调用点**；
  其缓存包装 `build_cross_file_repair_plan_cached` 同样零图内调用点。
  （以上为**实装前口径**；U 轮 Step A 后：`src/graph/debugger.py::_debugger_node` 在
  `CROSS_FILE_PLAN_BUILD_ENABLE=true` 且 deps 非空时为生产调用点，见 §1.5 与 CHANGELOG U 轮。）

### 1.2 关键发现：`cross_file_plan` 已有**下游消费者**（接线即改行为）

O 轮登记只说"接线会改变 LLM 调用/修复路由"，本批进一步定位到具体机制：

1. **debugger 经 `cross_file_plan.target_modules` 改 target_module 解析**
   （`src/graph/debugger.py::_resolve_target_module`，`_debugger_node` 调用处）：
   跨文件任务且 `cross_file_plan` 携带 `target_modules` 时，debugger 的定位/探针
   `target_module` 从 `state["module_name"]` 切到 `target_modules[0]`；
   该值直接进入 `DebuggerAgent.debug(...)` 的 prompt 与 `_locate_repair_focus`
   的跨文件保护判定 → **prompt 内容与修复路由都会变**。
   即：只要把真实计划写进 `state["cross_file_plan"]`（哪怕不让 patch_applier 消费），
   debugger 行为就已经改变——**不存在"纯观测接线"**，除非再加一个消费门控开关。
2. **`per_module_patches` 目前无消费者**：`_patch_applier_node` 的跨文件分支只把
   entry 模块的 `state["patch"]` 放进 `patches` 字典（其他模块"由 `_debugger_node`
   后续生成（二期）"），所以接 builder 若不改 patch_applier，只是**白烧 LLM 调用**
   （N 个模块 × 每轮修复）而不产生多文件修复能力。
3. 因此真正的"多模块协同修复"需要同时改：analyzer（产出 plan）→ debugger
   （消费 target_modules / 每模块补丁）→ patch_applier（`apply_multi_file_patch`
   消费 `per_module_patches`，拓扑序 + 整体回滚）——是一条**能力变更链**。

### 1.3 成本量级（接线 ON 时的增量）

- `build_cross_file_repair_plan` 对每个模块调用一次 `DebuggerAgent.debug`
  （协调器-提议者：每模块一个提议者），模块数上界 `CROSS_FILE_MAX_MODULES`（默认 5）。
- 即：每次进入修复环、每次跨文件任务，**+1..5 次 debugger LLM 调用**（及其 token），
  且无缓存命中时重复（`build_cross_file_repair_plan_cached` 可复用依赖图指纹缓存，
  但基准跑批默认 `AITESTER_LLM_CACHE=0`，文件缓存路径也不保证命中）。
- 对照：O-3 实测单次跨文件真实 LLM 修复 ≈5 次调用/≈$0.00345；接 plan 后按 2–3 模块
  估算 +2–3 次调用/修复轮 ⇒ 成本约 ×1.5–2（同任务口径，需 A/B 实测确认）。

## 2. 处置判定（对照任务判据）

| 判据 | 接线是否满足 | 说明 |
|---|---|---|
| 默认关（env 未设）时行为零变化 | ✅ 可实现 | 开关默认 false，OFF 时 analyzer 仍写 `cross_file_plan=None` |
| 关闭时 LLM 调用/修复路由零变化 | ✅ | 与现行为逐位一致（只需一次守卫） |
| **开启（ON）时不改变 LLM 调用/修复路由** | ❌ | plan 的 `target_modules` 被 debugger 现有消费点读取（§1.2-1）⇒ prompt/路由必变；builder 本身必增 LLM 调用（§1.3） |
| 因此本轮是否硬接线 | ❌ 不接线（T 轮切点判定，已被 U 轮 §1.5 取代） | 符合任务"会改变 LLM 调用/修复路由 → 设计+预注册"分支 |

**T 轮切点决定（已被 U 轮 Step A 取代）**：当时不改 `src/graph/nodes.py` /
`src/graph/debugger.py` / 默认开关，`cross_file_plan` 保持 `None` 占位。
**U 轮 Step A 已实装**（BUILD/CONSUME 双开关默认关；OFF/OFF 与历史逐位一致；
Step B 多模块协同与 D3b-AB1 跑批仍未执行），实现修正见 §1.5。

## 3. 建议实施方案（下一轮，分两步）

> 注：本节为 **T 轮设计稿**；Step A 实装与本节的两处差异见 §1.5
> （生产节点改为 `_debugger_node` LLM 分支；`_patch_applier_node` 消费未在
> Step A 接线，属 Step B）。

### Step A（观测/接线期，默认关）——"plan 构建 + 显式消费门控"

- 新增开关 `CROSS_FILE_PLAN_BUILD_ENABLE`（默认 **false**）：
  `_cross_file_analyzer_node` 在 `cross_file_enabled()` 且 deps 非空且开关 ON 时，
  调 `build_cross_file_repair_plan_cached`（复用依赖图指纹缓存）写
  `state["cross_file_plan"] = plan.to_dict()`；OFF 时保持 `None`（零变化）。
- 新增开关 `CROSS_FILE_PLAN_CONSUME_ENABLE`（默认 **false**）：
  `_resolve_target_module` 与 `_patch_applier_node` 只在消费开关 ON 时读 plan；
  OFF 时即使 plan 已在 state 也不消费（保证"构建"与"消费"解耦，便于分阶段 A/B）。
- 契约测试（零 LLM）：双开关矩阵 × 4 组合的 state/路由快照；OFF/OFF 与现行为逐位一致。

### Step B（能力期，默认关）——"多模块协同修复"

- `_debugger_node` 消费 `per_module_patches`（或按 target_modules 逐模块生成）；
- `_patch_applier_node` 用 `apply_multi_file_patch(original_files, patches, entry_module, deps)`
  拓扑序应用 + 整体回滚（apply 层已有失败整体回滚语义，O-3 Run2 已验证）；
- 回归：单文件分支零变化 + 跨文件整体回滚/部分失败降级到单文件。

## 3.5 Step B 前置件核查（AA 轮 2026-10-19，零 LLM、零行为变化）

> 结论先行：**AA 轮不实施 Step B**。按 §3 Step B 逐条对当前代码核查后确认：
> 它不是"再加一个消费分支"的量级，而是**四件前置件**，其中 (a) 单独就会改变
> 跨文件任务的依赖边构成与修复路由（与 §1.2-1 同类、且比 §2 判据更硬），
> (c) 触碰的是写盘安全不变量。任一前置件半接线都会产生"代码看起来接了、
> 能力其实不存在"的假主张——登记册 §4 对此有明确禁令。核查结果先钉成**反面
> 锁定**，实装时该锁必红，从而强制文档/登记同步。

### 3.5.1 四条前置件与当前落点

| # | 前置件 | 当前落点（核查于 2026-10-19） | 为什么不是"顺手能接" |
|---|---|---|---|
| (a) | 非入口模块源码进 `source_files` | `src/graph/nodes.py:2114-2119`：只把 entry 塞进 `source_files/entry_modules`（注释即"未来扩展"）；同文件 `:2188` 对 `dep.target_module` 恒取 `""` 跳过（L4 已知缺口） | 磁盘上其实**有**伴生模块：benchmark 层 `experiments/run_benchmark.py:2312-2348::_write_cross_file_modules` 已把 `module_a/b/c_code` 物化到任务 tmp_dir。但一旦载入，`analyze_multi_entry_deps` 的输入从 1 个模块变 N 个 → **会新产出今天不存在的 AST 依赖边** → `cross_file_deps` 内容、`_resolve_target_module` 的末元素回退、`cross_file_contexts` 全部变化。即 (a) 单独就不是观测中性，必须先有开关 + 同批对照 |
| (b) | `original_files` / `patches` 由 plan 供给 | `src/graph/nodes.py:2569-2577`：`original_files = {entry: original_code}`、`patches` 只放 `state["patch"]`；`:2580` 取 `new_files.get(entry_module, original_code)` | 现状是**计算完即丢弃**：`apply_multi_file_patch` 的返回映射里，非入口模块的新代码从未被读；由于 `patches` 恒只 1 个键，`_topological_order`（`src/tools/cross_file.py:603+`） today 是单元素退化。接 `per_module_patches` 需要 (a) 提供原文，否则 `cross_file.py:585-588` 的"模块不在 original_files → 跳过"分支会把多模块补丁静默吞掉 |
| (c) | 多文件写盘 + 整体回滚 | `src/graph/patch_io.py:351-409::_safe_write_patch` 只写 `state["target_file"]` 一个路径（四道安全检查 + 单文件快照）；`src/graph/nodes.py:2598::_apply_snapshot_rollback` 也只恢复该单文件；`src/graph/state.py:249-255 / :607-608` 无"跨模块新代码 / 逐模块快照"通道键（`cross_file_contexts` 是聚焦摘录，**不是**整模块原文，不可当源码通道用） | 这是**安全不变量**改造：路径白名单、`PATCH_PROTECT_REPO_CORE` 仓库核心保护、快照失败 fail-closed（W12）、O35"只有经 update dict 才回写 channel"。整体回滚目前只在 apply 层成立（`cross_file.py:595-597` 失败即返回 `original_files`），O-3 Run2 验证的也是 apply 层拒绝，**从未有 >1 个模块真正落盘**。写盘面扩到 N 个文件必须与回滚面同时扩，否则出现"部分写盘"——正是 §4.3 安全判据要禁止的形态 |
| (d) | D3b-AB1 三臂 LLM 预算 | §4 草案（A0/A1/A2）；登记册 §4 "U 轮新登记（评审遗留，需授权/预算）" 已列 `D3b-AB1 + Step B` | 能力主张必须同批对照（§4.3 归因判据要求 A1−A0 调用增量 >0 且 A1 与 A0 的 passed 差 ≤1）。预算未授权前，(a)(b)(c) 即便实现也只能停在"默认关 + 无结论"，不得对外称跨文件多模块修复能力 |

### 3.5.2 本批落地的反面锁定（3 例，零 LLM）

`tests/test_cross_file_plan_wiring.py::TestStepBNotWired`（同文件既有 13 例 Step A 锁不变）：

| 用例 | 钉住的事实 | 变异验证（AA 轮实测） |
|---|---|---|
| `test_analyzer_source_files_excludes_sibling_module_on_disk` | (a)：同目录 `module_c.py` 真实存在，`analyze_multi_entry_deps` 仍只收到 `(["module_a"], {"module_a": …})` | 在 `nodes.py:2114` 块内临时从磁盘读伴生模块 → **红**（`entry_modules` 多出 `module_c`），已还原 |
| `test_patch_applier_builds_entry_only_original_files_and_patches` | (b)：CONSUME 开 + plan 带两模块 `per_module_patches` 时，apply 入参两个字典仍各只有 entry 键；伴生文件磁盘内容不变（(c) 写盘面） | 在 `nodes.py:2573` 后临时把 `per_module_patches` 灌进 `original_files/patches` → **红**（`patches` 多出 `module_c`），已还原 |
| `test_state_has_no_multi_module_write_back_channel` | (c)：`AITesterState` 无 `cross_file_source_files` / `cross_file_new_files` / `cross_file_snapshots` 类通道键 | 临时加 `cross_file_new_files` 声明 → **红**，已还原 |

三条变异均由断言直接捕获（非靠异常），故锁具有判别力；同时它们**不是**期望行为——
实装 Step B 时必须连同 §3.5.1 表格与本文件 §1.5/§3、登记册 §4 的"Step B 未接线"
披露行一起改写，不得只把断言改成新行为放行。

### 3.5.3 建议实装顺序（下一轮若获得授权）

1. **(a′) 带开关的源码载入**：新增 `CROSS_FILE_SOURCE_LOAD_ENABLE`（默认 false，需按
   `check_env_budget.py` 走显式登记），只在该开关下把 entry 同目录、且出现在依赖边上的
   模块原文读入 `source_files`；OFF 时 `analyze_multi_entry_deps` 入参逐位不变
   （用 `TestStepBNotWired` 第一条作对偶基线）。
2. **(b′) plan 供给 patches**：CONSUME 开时 `original_files` 取 (a′) 的源码、
   `patches` 取 `per_module_patches ∩ original_files`（交集而非并集，避免
   `cross_file.py:585` 静默跳过被当成成功）。
3. **(c′) 写盘 + 回滚同时扩面**：`_safe_write_patch` 逐模块走同一套四道安全检查 +
   每模块快照，任一模块写失败 → 已写模块全部按快照恢复；快照失败仍 fail-closed。
4. **(d′) D3b-AB1 三臂**（§4），A2 臂才允许出现"多文件写盘计数 > 0"。

顺序不可打乱：先有 (a′) 的可控入图，(b′) 才有原文可用；(c′) 未做前 (b′) 的
非入口补丁只是内存里的死值；(d′) 未跑前，前三步都只是"默认关的通路"，
不构成能力主张。

## 4. 预注册草案（下一轮跑批前冻结；本批**不执行**）

> 标题：D3b-AB1：`build_cross_file_repair_plan` 图通路（Step A 构建 + Step B 消费）的
> 两臂对照。**跑前冻结 PREREG.md 并落 sha256**；本文件仅为草案，不构成执行授权。

### 4.1 假设

- H1（主）：跨文件任务上，启用 plan 构建+消费后 `repair_rate` 提升 ≥10pp
  （或 `passed` 提升 ≥1 个任务/臂），且不劣化单文件任务（单文件臂 passed 差 ≤1）。
- H0（成本）：每任务 LLM 调用数增量可估且 ≤ +40%；token 成本增量随预算闸可见。

### 4.2 臂设计（同一批次、同数据集、同 seed）

| 臂 | 开关 |
|---|---|
| A0（对照） | `CROSS_FILE_ENABLE=true`，`CROSS_FILE_PLAN_BUILD_ENABLE=false`，`CROSS_FILE_PLAN_CONSUME_ENABLE=false`（= 当前行为） |
| A1（构建不消费） | BUILD=true、CONSUME=false（测"白烧调用"成本上界 + plan 落态观测） |
| A2（全链路） | BUILD=true、CONSUME=true（Step B；能力臂） |

- 数据集：O-3 确定性双模块场景（`synthetic` 跨文件构造 + `dep_chain` 预置边）**加**
  synthetic 跨文件子集（按任务 metadata 含 `cross_file`/`dep_chain` 过滤，n≥20）；
  另抽 10 个单文件任务作"单文件非回归"子集。
- 协议：`AITESTER_PROFILE=fast`、`TEMPERATURE=0.0`、`LLM_THINKING_MODE=disabled`、
  `AITESTER_LLM_CACHE=0`、`BENCHMARK_PARALLELISM=4`、干净切点 worktree（sha 冻结）、
  任务级 + 批次级预算闸、watchdog。
- 隔离：与 T4/S-2 相同的进程内隔离要求（生产文件零 diff + 模块来源校验）。

### 4.3 判据（机读写入 ANALYSIS.json）

| 编号 | 规则 |
|---|---|
| 主判据 | A2 vs A0：跨文件子集 `repair_rate` 差 ≥+10pp 或 `passed` 差 ≥+1；且单文件子集 `passed` 差 ≥−1（非回归） |
| 成本判据 | A2−A0：`llm_calls/任务` 增量 ≤ +40%；`tokens/任务` 增量 ≤ +50%；超限 → `not_confirmed_cost` |
| 归因判据 | A1−A0：调用增量必须 >0（证明 builder 真正执行）；A1 与 A0 的 `passed` 差 ≤1（构建不消费=无收益，验证消费是收益来源） |
| 安全判据 | A2 的多文件 apply 失败全部整体回滚（`patch_rolled_back=true` 计数 == apply 失败计数），不得出现部分写盘 |
| 失败判据 | 任一臂 crash>0 → 如实披露，不得删除失败行 |

### 4.4 预算/失败策略

- 预算上界：按 A1/A2 增量估算，先跑 3 任务冒烟（≤$0.10）再决定主批（上界 ≤$1.0）；
  超预算如实停批（不静默续跑）。
- 单臂失败/超时如实记录、不重跑；两臂并发 + 独立 cache namespace。
- 不外推：fast 档 + 单模型 + 单 seed 的机制验证；能力结论需 3-seed 复现后再主张。

### 4.5 披露要点（跑后必须写入 README）

- plan 是否真被消费（A1→A2 差）、多文件写盘/整体回滚计数、token 增量、
  单文件非回归结论、以及"观测 vs 能力"边界（A1 无收益不得写成收益）。

## 5. 风险与回滚

- **上下文爆炸**：`CROSS_FILE_MAX_MODULES` 上界与 prompt 预算需同批审计（每模块聚焦上下文
  已有 `cross_file_contexts`，但 plan 的每模块补丁会把 debugger 输出量 ×N）。
- **默认口径污染**：所有新开关默认 false；未显式开启时 `cross_file_plan=None` 历史口径不变。
- **回滚**：仅删开关分支与消费调用即可；无 schema/数据迁移。
- **不做的理由重申**：本批若硬接线，B2/T1 主批次与默认协议实验的可比性会被污染
  （每次跨文件修复多 N 次 LLM 调用），且 R-P0-2 复现结论无法归因。

## 6. 参考

- O 轮证据：`（工件已清除）`（O3_EVIDENCE.json D3b、
  preflight_zero_llm.json orphan_plan_builder、run2 组件级整体回滚）。
- 相关代码：`src/tools/cross_file.py`（builder/cached/apply_multi_file_patch）、
  `src/graph/nodes.py::_cross_file_analyzer_node` / `_patch_applier_node`、
  `src/graph/debugger.py::_resolve_target_module`、`src/graph/state.py`（cross_file_* 字段）。
