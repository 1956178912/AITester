# O-3 跨文件修复路径真 LLM 强制端到端（analyzer 路由真实进入 + 多文件补丁/回滚）

> **性质**：O 轮 O-3 验证性端到端工件（不是正式实验证据，不用于论文数字）。
> **日期/环境**：2026-10-18（Asia/Shanghai）；HEAD `1425ee74490ba6e2be15fd0feb87fc6f07ea856e`
> （O-1 收口提交）+ **O 轮并发未提交工作树**（本工件 `provenance.git_dirty=true`
> 如实记录，不是冻结快照）；Python 3.14.6；模型 `deepseek-flash`
> （`TEMPERATURE=0.0` / `LLM_THINKING_MODE=disabled` / `AITESTER_LLM_CACHE=0`
> 强制真实调用、禁止缓存重放）；`AITESTER_PROFILE=logic`（FL_spectral 定位与
> 特异性门等生产链路；`ENABLE_PLANNER=false` 控预算，真实 LLM = generator +
> debugger）。
>
> **目标（承接 N-4 的 D3）**：N-4 真实批次里 `cross_file_analyzer` **从未进入**
> （L3 任务首轮即绿）。O-3 构造**确定性首轮必失败**的跨文件场景 → 真实 LLM
> 跑完整图路由 → 验证 analyzer 进入、`cross_file_deps/plan` 落态、多文件补丁
> 应用/安全回滚、结果行审计字段完整。

## 1. 场景构造（确定性首轮失败 + 真实跨文件依赖，零 LLM 自检）

自定义双模块 synthetic 场景（数据构造在实验层，不改判分口径）：

| 模块 | 内容 |
|---|---|
| `o3_target.py`（被调方 / module-under-test） | `add(a, b)` docstring 声明"返回 a 与 b 的和"，**实现为 `a - b`** → 任何按意图写断言的测试在缺陷代码上**必然失败**（首轮必红） |
| `o3_caller.py`（调用方） | `from o3_target import add`；`add_twice(a,b) = add(a,b)+add(a,b)` → 真实跨文件依赖 |
| 任务 metadata | `is_cross_file=True` + `module_a_code/name` + `dep_chain=[o3_caller, o3_target]` + `target_module` + gold `test_cases/fixed`（M1 裁决材料） |

零 LLM 自检（`preflight_zero_llm.json`）：

- **场景确定性**：gold 契约测试在缺陷代码上 **fail**（failed_cases=1）、在 fixed
  上 **pass** —— 首轮必失败成立；
- **图装配差集**：`CROSS_FILE_ENABLE=false` 无边/节点；`true` 时新增
  `cross_file_analyzer`，且存在 `executor→cross_file_analyzer`、
  `cross_file_analyzer→debugger` 路由边；
- **analyzer 直调**：预置 `cross_file_deps` 被保留（非空）、`cross_file_plan=null`
  （当前占位实现，见 §4 D3b）；
- **孤儿计划构建器**：`cross_file.build_cross_file_repair_plan` 用 stub 提议者
  可产出**双模块补丁计划**、`apply_multi_file_patch` 可双文件落盘；
  但 AST 扫描 `src/graph/**` 对 `build_cross_file_repair_plan` **零调用点**
  （D3b 直接证据）。

## 2. 命令（可复现；真实 LLM 共 2 次运行）

```bash
# 零 LLM 预检（机制/装配/孤儿构建器/场景确定性）
.venv/bin/python experiments/results/o_round_cross_file_20261017/_helpers/preflight_zero_llm.py \
  /Users/wangchenyu/Workspace/AITester /Users/wangchenyu/Workspace/AITester/experiments/results/o_round_cross_file_20261017

# Run #1：完整图路由 + 真实 LLM（1 任务；generator + debugger = 3 次调用）
.venv/bin/python experiments/results/o_round_cross_file_20261017/_helpers/run_o3_real.py \
  /Users/wangchenyu/Workspace/AITester /Users/wangchenyu/Workspace/AITester/experiments/results/o_round_cross_file_20261017 run1 \
  > experiments/results/o_round_cross_file_20261017/logs/run1.log 2>&1

# Run #2：组件级真实 LLM 多文件计划 + 多文件应用/回滚（2 次调用；非图路由，见披露）
.venv/bin/python experiments/results/o_round_cross_file_20261017/_helpers/run_o3_component_multifile.py \
  /Users/wangchenyu/Workspace/AITester /Users/wangchenyu/Workspace/AITester/experiments/results/o_round_cross_file_20261017 \
  > experiments/results/o_round_cross_file_20261017/logs/run2_component.log 2>&1

# 观测性修复后 trace 取证（零 LLM 重放）+ 证据汇总
.venv/bin/python experiments/results/o_round_cross_file_20261017/_helpers/capture_analyzer_trace_after_fix.py \
  /Users/wangchenyu/Workspace/AITester /Users/wangchenyu/Workspace/AITester/experiments/results/o_round_cross_file_20261017
.venv/bin/python experiments/results/o_round_cross_file_20261017/_helpers/summarize_o3.py \
  /Users/wangchenyu/Workspace/AITester/experiments/results/o_round_cross_file_20261017
```

## 3. Run #1 结果（完整图路由，真实 LLM）

**路由链（`traces/run1/*.trace.jsonl`，逐节点）**：

| # | 节点 | decision | 说明 |
|---|---|---|---|
| 1 | generator | generated | 真实 LLM 生成 6 个测试（断言求和，正是缺陷代码必失败的行为） |
| 2 | executor | **FAIL** | 首轮真实执行失败（failed_cases=1，coverage=100%） |
| 3 | _should_debug | debug | 失败 → 进入修复分支 |
| 4 | **cross_file_analyzer** | single_file_fallback（**修复前 trace 口径**，见 §4 D3c） | **analyzer 真实进入**（trace 节点在案）；实际保留预置 dep_chain 边 1 条 |
| 5 | debugger | assertion | 真实 LLM 诊断："第 6 行 return a-b 与 docstring 求和语义不符" |
| 6 | patch_applier | written | 多文件补丁分支（cross_file_deps 非空 + CROSS_FILE_ENABLE=true）写盘成功 |
| 7 | executor | **PASS** | 补丁后真实复跑通过 |
| 8 | _should_debug | done | 收敛 |

**关键字段（批次结果行 + raw 状态互证）**：

- `cross_file_enabled=true`；`cross_file_deps=[{source_module: o3_caller, target_module: o3_target, source: benchmark_preset}]`（1 条，**落态**）；`cross_file_plan_present=false`（占位实现，D3b）；
- `repair_history=[{iteration:1, error_category:assertion, patch_applied:true}]`；`patch_plausible=1`；`patch_evidence_level=sbfl`（FL_spectral 定位证据 → 通过默认 N9 证据门）；`source_patched_unverified=false`；
- `passed=true`；`iterations=1`；`stop_reason=test_passed`；`detection_rate=null`（本场景无 M1 buggy/fixed 对比口径，不参与结论）；
- raw 产物 `run_artifacts/run1/raw/synthetic__o3_target/aitester.json`：`patch` 为把
  `return a - b` 改为 `return a + b` 的真实 LLM 补丁；`generated_test` 为 6 个测试的真实生成物；
  `test_passed=true`；
- 墙钟 **11.59s**；真实 LLM **3 次调用**（generator 1 + debugger 2）/ **4,340 tokens**。

**结论**：N-4 D3 的"analyzer 从未进入"不是装配缺陷——**只要首轮真实失败**，
真实图路由会依次进入 `executor(FAIL) → _should_debug(debug) → cross_file_analyzer
→ debugger → patch_applier(written) → executor(PASS)`。N-4 未进入的根因是
L3 真实任务首轮全绿（测试未检出，路由从不进修复分支），属**场景/测试质量
触发频率**问题。

**多文件补丁分支的真实边界**：图内 `patch_applier` 走的是"多文件应用"函数
（`apply_multi_file_patch`，deps 非空），但入参 `original_files/patches` 只含
**入口模块**——`cross_file_plan` 从未生成同伴模块补丁（D3b）。即：**分支进入
≠ 多模块协同修复**；Run #2 用组件级真实验证该缺口的另一半。

## 4. 缺陷清单（3 项）

### D3a（已验证机制；N-4 D3 根因归类）
N-4 的"analyzer 从未进入"= **首轮全绿导致路由不进入修复分支**（场景频率），
不是节点装配/开关问题。O-3 强制首轮失败后 analyzer 真实进入（Run #1 trace）。

### D3b（open；修复需 Lead 批准——涉及 LLM 调用/路由变化）
**多文件修复计划从未接线**：`cross_file.build_cross_file_repair_plan`（协调器-
提议者：每模块一次 debugger → `CrossFileRepairPlan.per_module_patches`）在
`src/graph/**` **零调用点**；`_cross_file_analyzer_node` 显式写
`cross_file_plan=None`（"占位，待二期实现完整计划构建"）。后果：
- 图通路永远只应用**入口模块**补丁（Run #1 实证）；`cross_file_plan_present`
  恒 False；
- 结果行无法区分"跨文件修复成功"与"单文件修复成功"。

O-3 组件级 Run #2（真实 LLM）证明组件本身可用：真实 Debugger 对
`o3_target`/`o3_caller` 各产出一个补丁（126/99 字符），`apply_multi_file_patch`
进入拓扑序应用；本次 `o3_caller` 补丁是"漏掉 `add_twice` 的整文件重写"，被
apply 层以 `完整文件补丁漏掉原代码函数 ['add_twice']` **保守拒绝 → 整体回滚**
（安全语义正确，日志见 `logs/run2_component.log`）。零 LLM stub 预检则证明
"合法双模块补丁 → 双文件落盘成功"。**修复建议（待批）**：在
`_cross_file_analyzer_node`（或在 debugger 之后新增 plan 节点）接线
`build_cross_file_repair_plan`，以 `cross_file_plan.target_modules` 供
debugger/patch_applier 消费；代价 = 每跨文件任务 +(模块数-1) 次 debugger 调用，
且需新增多文件回滚/证据门测试。

### D3c（已修复；观测性缺陷，写域内）
`_cross_file_analyzer_node` 的 trace `dep_edges`/`decision` 只统计 **AST 推导边**，
而 benchmark 层预置 `dep_chain` 边在下游实际被保留——真实跨文件任务
（AST 0 边 + 预置 1 边）在 trace 中被标 `single_file_fallback`/`dep_edges=0`
（Run #1 修复前 trace 实证），审计侧会误判"analyzer 没找到依赖"。
**修复**（`src/graph/nodes.py::_cross_file_analyzer_node`，纯观测）：
- trace 分列 `ast_dep_edges` / `preset_dep_edges` / `dep_edges`（有效边）；
- `decision` 按**有效依赖边**判定（预置边非空 → `deps_found`）；
- 仅在"AST 空且预置边空"时打印"降级为单文件模式"（原实现会对预置边场景误打）。
**路由/落态零变化**；修复后零 LLM 重放 trace：`decision=deps_found`、
`dep_edges=1`（`analyzer_trace_after_fix.json`）。
**回归**：`tests/test_o_round_cross_file_analyzer.py` **11 例**（预置边不误标 /
AST 优先 / 单文件降级不变 / plan 占位锁定 / 图装配边 / 多文件应用与原子回滚 /
孤儿构建器静态扫描 / 场景确定性）。既有 `test_workflow_extended.py`、
`test_cross_file*.py` 全绿（117 passed）。

## 5. 成本与预算（≤2 次真实运行、≤$0.1）

| 项 | Run #1（图路由） | Run #2（组件级） | 合计 |
|---|---|---|---|
| 真实 LLM 调用 | 3 | 2 | **5** |
| input / output tokens | 3,579 / 761 | 2,641 / 558 | **6,220 / 1,319** |
| 估算成本（deepseek-flash 标准价上界，`experiments/price_table.json`） | $0.0020 | $0.0015 | **≈$0.00345** |

远低于 $0.1 预算；其后所有重放/取证均为零 LLM。真实运行 2 次（符合 ≤2 约束；
未中断、未重跑）。

## 6. 局限（如实披露）

1. **自定义双模块场景**，非官方 synthetic L3 任务；结论在"机制可达性"层面，
   不代表 L3 批次检出率。
2. `ENABLE_PLANNER=false`（控预算）：真实 LLM = generator + debugger；
   planner 链路（已在 N-4/M 轮验证）不在本工件。
3. Run #2 为**组件级**（不经 LangGraph 路由），与 Run #1 互补；不作"图已支持
   多文件修复"证据。
4. 工作树非冻结快照（O 轮并发改动，`git_dirty=true` 如实记录）；
   模型非确定性意味着入口模块补丁内容可跨次波动。
5. `patch_rollback_verdict/patch_rolled_back` 未进结果行 schema（raw 白名单
   也不含），Run #1 的 A-03 协议实际执行与否无法从本工件逐字段断言；
   回滚证据以 Run #2 多文件原子回滚 + 既有 `safety-patch-rollback` 探针覆盖。
6. D3c 修复在 Run #1 之后；图路由未重跑（预算/运行次数约束），修复验证用
   零 LLM 同形状重放 + 回归测试闭环（路由逻辑未变）。

## 7. 工件清单

| 文件 | 内容 |
|---|---|
| `O3_EVIDENCE.json` | 汇总证据（路由链/落态/补丁/回滚/缺陷/成本/全目录 sha256） |
| `preflight_zero_llm.json` | 零 LLM 预检（装配/analyzer/孤儿构建器/场景确定性） |
| `run_run1_summary.json` / `run_artifacts/run1/` | Run #1 图路由批次 JSON + raw 状态 + traces |
| `run_run2_component_summary.json` / `logs/run2_component.log` | Run #2 组件级真实 LLM 多文件计划 + 回滚原因 |
| `analyzer_trace_after_fix.json` / `trace_after_fix/` | D3c 修复后零 LLM trace 取证 |
| `logs/run1.log` | Run #1 运行日志（stdout/progress） |
| `_helpers/*.py` | 场景定义 / 预检 / 运行 / 汇总脚本（可复现） |
| `SHA256SUMS` | 本目录全部工件内容哈希 |

## 8. 未决项（Lead 决策，2026-10-18）

O-3 交付后 Lead 对两个上报项的决策如下（本轮**不实施**，登记后续任务；
本工件的 Run #1/#2 结论与证据不受影响，task-17 维持 completed）：

### 8.1 D3b：多模块修复计划构建器零调用点 → 本轮不接线

- **决策**：`cross_file.build_cross_file_repair_plan`（协调器-提议者多模块协同）
  接入图通路会**改变跨文件任务的 LLM 调用数/修复路由**，属能力变更——按纪律
  必须先设计 + 预注册 + 同批对照，**留给下一轮任务**。
- **登记**：登记册 §4 新登记 P1——"跨文件图通路接
  `build_cross_file_repair_plan`（多模块协同）+ 调用成本/证据门/回滚测试"。
- **本轮现状（不阻塞）**：图通路保持"只修入口模块 + 结果行审计字段"口径；
  `cross_file_plan` 仍为 None 占位、`cross_file_plan_present` 恒 False 是
  **已知登记状态**，不是本轮静默失败。
- **证据位置**：
  - `O3_EVIDENCE.json` → `defects[]` 中 `id="D3b"`（含根因/现状/组件级验证）；
  - `preflight_zero_llm.json` → `orphan_plan_builder`（图内调用点=0 的 AST 取证 +
    stub 双模块补丁计划可构建/可双文件落盘）；
  - `run_run2_component_summary.json` + `logs/run2_component.log`（真实 LLM
    双模块补丁产出；apply 层因整文件重写漏函数而**整体回滚**的安全语义证据）；
  - 本 README §4 D3b、§6 局限 1–4。

### 8.2 `patch_rollback_verdict/patch_rolled_back` 未进结果行 schema → P2 候选

- **决策**：登记为 **P2 schema 扩充候选**，下一轮与 D3b 一起做（届时需保持
  成功/失败分支键位一致并补回归）。
- **本轮覆盖（已在 §6 局限 5 披露）**：A-03 协议字段未逐行透出，不等于协议
  未执行；回滚语义由
  - `run_run2_component_summary.json` → `multi_file_apply` / `rollback_reason_lines`
    与 `logs/run2_component.log`（多文件原子回滚，真实 LLM 补丁被 apply 层拒绝）；
  - 既有 `scripts/tools/e2e_probes_workflow.py::safety-patch-rollback` 探针
    （N-1，P2P 失败自动回滚/通过保留/开关可观测）覆盖。
