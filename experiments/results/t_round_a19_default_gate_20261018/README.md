# T4 A-19 默认协议复验（2026-10-18，真实 LLM，预注册冻结）

> 复验对象：T4 的 A-19 抢占优先级修复（`src/graph/workflow.py::_should_debug`）在**生产默认协议**
> （`PATCH_EVIDENCE_GATE_ENABLE=true`）下是否让停滞分支真正拥有终止决定（承接 S-2 登记缺陷）。
> 协议：复用 S-2 失败注入 harness（`experiments/run_b8_injection.py`），10 任务 synthetic seed=42
> fast 档、两臂并发、默认证据门、**唯一差异 `COVERAGE_STALL_DETECT_ENABLE=true|false`**；
> PRE-REG 冻结 sha256 `83a8a645…`；切点 `962c77e`（含 T4 修复）干净 worktree；生产文件零 diff
> （见 `ISOLATION.json`）。真实 LLM 花费 **$0.098**（两臂合计，预算上界 $0.15）；两臂 crash=0。
>
> **口径声明**：本批主判定 = `ANALYSIS.json`（T4 预注册 P1–P4）。同目录 `REPORT.json` 是
> S-2 harness 的通用聚合（其 primary/secondary 判据是"注入下行 + ≥1 轮节省"的 S-2 口径，
> 在默认协议下**结构上不适用于本复验**）；`REPORT.json.verdict.classification=not_confirmed`
> 与本批 T4 判定（`unexpected_delta`）**不是同一个判据**，引用时必须区分。

## 0. 预注册判定（按 `ANALYSIS.json`，逐条报告，不做事后改判）

| 判据 | 规则（预注册原文） | 实测 | met |
|---|---|---|---|
| **P1 分支归属（主判据）** | ON 臂 `stop_reason=coverage_stall` 率=1.0 ∧ 优先日志计数=**10** ∧ repair-invalid 日志=0 | stall 率 **1.0（10/10）**、优先日志 **8**、repair-invalid 日志 **0** | ❌（字面） |
| **P2 默认关零变化** | OFF 臂 repair-invalid 率=1.0 ∧ 该分支日志=**10** ∧ 停滞日志=0 ∧ crash=0 | repair-invalid 率 **0.9（9/10）**、日志 9、停滞日志 0、crash 0 | ❌（字面） |
| **P3 零迭代节省（负向预注册）** | `iterations_mean(on) == iterations_mean(off)`（Δ=off−on=0） | on **1.9** vs off **2.1**，Δ=**0.2** | ❌ |
| **P4 harness 有效性** | 两臂 tasks_with_injection=10 ∧ injected_rounds>0 ∧ crash=0 | ON 10/30/0、OFF 10/31/0 | ✅ |

**classification = `unexpected_delta`**（按预注册：P3 违例即记该类，**不得当作收益**）。

## 1. 两臂实测（数字来自 `ANALYSIS.json` / `REPORT.json`）

| 项 | on 臂（stall ON） | off 臂（stall OFF） |
|---|---|---|
| 任务数 | 10 | 10 |
| stop_reason 分布 | `coverage_stall`×10 | `skip_debugger_repair_invalid`×9、`max_iterations`×1 |
| stall 触发率 | **10/10 = 1.0** | 0/10 = 0.0 |
| iterations 均值 / 中位 / max | 1.9 / 2 / 2 | 2.1 / 2 / 3 |
| 优先（preempt）/停滞/repair-invalid 日志 | 8 / 10 / **0** | 0 / 0 / 9 |
| coverage 均值 | 0.0 | 10.0（由 1/10 任务的真实轮贡献） |
| tokens / LLM calls | 87,835 / 60 | 87,216 / 62 |
| 成本（标准价上界） | $0.049308 | $0.048692 |
| 注入记录（注入/真实轮） | 30/0 | 30/1 |
| provenance | `962c77e…`/dirty=False | `962c77e…`/dirty=False |

## 2. 结果逐项解读（事实 → 解释边界）

### 2.1 P1：机制归属实质成立，但预注册的日志计数口径过窄

- ON 臂 **10/10** 任务 `stop_reason=coverage_stall`、repair-invalid 日志 **0** → 停滞分支
  确实拥有终止决定；`preempt` 专用日志 **8** 条，其余 **2** 条经**既有尾部停滞短路**
  （该 2 任务本轮无 repair-invalid 平局，走修复前就存在的尾部路径，日志文案不同）。
- 即 P1 的实质主张（"停滞分支拥有决定而非 repair-invalid 标签兜底"）由 10/10 支持；
  预注册把"优先日志=10"写死（隐含 10/10 均出现同迭代平局的假设）未成立（8/10 有平局）。
- **判据口径缺陷，不是机制失败**；按纪律不改判，登记为下轮预注册修正项。

### 2.2 P2：OFF 臂 1/10 任务轨迹不同（LLM 非确定性），非代码回归

- OFF 臂 9/10 以 `skip_debugger_repair_invalid` 结束、1/10（`synthetic__task_0003`）以
  `max_iterations` 结束；该臂注入记录 31/30（1 条真实轮，coverage=100）——两臂独立发起 LLM
  调用、温度 0 仍有服务端非确定性 → 该任务在 OFF 臂的轨迹未形成"连续无效"序列。
- OFF 臂代码路径与历史完全一致（T 轮零变化由改前黄金表 18/18 逐位锁定，见
  `t_round_semantic_fixes_20261018/`），故该 1/10 属**运行轨迹差异**，不是"默认关行为被改"。
  按规则仍记 P2 不满足并如实披露。

### 2.3 P3：Δ=0.2 的非对称按"不可归因"处理

- 配对结构：off>on **2/10**、相等 **8/10**；Δ=0.2 全部来自 2 个轨迹不同的任务
  （`task_0001` 1 vs 2 轮、`task_0003` 2 vs 3 轮）。
- 本修复语义是"同迭代平局内换归属、迭代数不变"，**不产生系统性迭代节省机制**；
  Δ=0.2 与"服务端非确定性导致轨迹分叉"一致，**不得**表述为"抢占优先级节省迭代"。
- 按冻结规则 classification 保持 `unexpected_delta`；**不作收益主张**。

## 3. 结论

1. **代码侧语义修复有效**：ON 臂停滞分支 10/10 拥有终止决定、repair-invalid 日志清零；
   默认关路径零变化由改前黄金表 18/18 逐位锁定。
2. **本批判据未全部满足**：P1/P2 的日志计数按字面未达 10/10、P3 负向判据被 2/10 轨迹分叉
   打破 → 预注册 classification=`unexpected_delta`，**不得当作 confirmed**（`REPORT.json` 的
   S-2 口径 `not_confirmed` 亦按该文自身口径记录，两者都不支持"收益"主张）。
3. **下轮修正项（登记，不在本批改判）**：
   - P1 拆成"平局任务数 = preempt 日志数"与"无平局任务走尾部短路"两个子判据；
   - P2/P3 用**注入层固定响应重放**消除 LLM 轨迹分叉（或同任务交替顺序 + 重复 2 次）；
   - P3 改为"配对方向检验 + 预注册等价界（如 |Δ|≤0.5 轮）"或改为描述性；
   - 加 seed 44 复本 + 交替启动顺序，检验 Δ 的非对称是否可复现（不复现 → 噪声）。

## 4. 产物与限制

`PREREG.md`（冻结文本）/`RUN_SUMMARY.log`/`log_arm_on.log`/`log_arm_off.log`/`arm_on/`、`arm_off/`
（批次 JSON + 注入记录 + traces）/`REPORT.json`（S-2 harness 聚合，**非本批判据**）/
`ANALYSIS.json`（本批判定）/`ISOLATION.json`/`SHA256SUMS`。
限制：n=10、单 seed、fast 档、单模型、单次运行；只作机制验证，不外推。
