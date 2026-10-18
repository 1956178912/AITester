# T4 / A-19 抢占优先级修复：默认协议真实 LLM 复验预注册（**跑前冻结**）

> 性质：机制验证性复验（harness-based revalidation）。复验对象是 **A-19 抢占优先级
> 语义修复**（T 轮 2026-10-18），不是能力收益估计；真实 LLM 执行由 Lead 在干净
> 切点 worktree 上跑，预算上界 **≤$0.15**（两臂合计）。
> 本文件由 `experiments/run_t4_a19_revalidation.sh` 复制为 `<OUT>/PREREG.md`，
> 并在两臂启动**之前**记录 sha256（`RUN_SUMMARY.log` / `ANALYSIS.json` 均可复核）。
> **跑后不得修改本文件**（改动即使跑批结果不可用）。

## 0. 复验要回答的问题

S-2（`experiments/results/s_round_b8_injection_20261018/`）已登记真实缺陷：

> 生产默认协议（`PATCH_EVIDENCE_GATE_ENABLE=true`）下，证据门反复拒绝写盘 →
> `repair_history` 连续 `patch_applied=False`，`repair-invalid` 与停滞窗口在
> **同一迭代**收敛。修复前 `_should_debug` 的 repair-invalid 分支先命中并 return
> `done`，函数末尾的停滞短路永不执行 → ON 臂的 `coverage_stall` 只是
> `determine_stop_reason` 的**标签兜底**（日志仍写"连续多次修复无效"），
> 即 A-19 在默认协议下"只改标签、不省迭代"（S-2 默认闸冒烟：ON/OFF 均
> iterations=2，两任务 stop_reason 分别为 coverage_stall / repair_invalid）。

T4 修复（`src/graph/workflow.py::_should_debug`）：repair-invalid 命中时，若
`COVERAGE_STALL_DETECT_ENABLE=true` 且停滞判定为真，**停滞优先**（分支归属/
日志/打点如实反映"停滞"，`preempted=skip_debugger_repair_invalid`）。默认关时
守卫不可达 → 历史行为逐位不变。

**本批要回答（唯一假设 H1）**：默认闸协议下，停滞 ON 臂的终止决定由"停滞优先"
分支拥有（可观测的日志归属变化），而 OFF 臂保持 repair-invalid 历史口径。
**明确不主张**：本修复不带来迭代节省（见 P3 负向预注册）。

## 1. 协议（跑前冻结）

| 项 | 值 |
|---|---|
| 切点 | 干净 worktree（`git status --porcelain` 为空；`HEAD` 必须等于 `--expect-sha`；T4 提交后的 sha） |
| 数据集 | synthetic（`--dataset synthetic --task-count 10 --seed 42`，与 S-2 可比） |
| 档位 | `AITESTER_PROFILE=fast`（与 S-2 同；单变量=停滞开关） |
| 采样 | `TEMPERATURE=0.0`；`LLM_THINKING_MODE=disabled`；`AITESTER_LLM_CACHE=0` |
| 并行 | `BENCHMARK_PARALLELISM=4`（两臂**并发**两个进程，cache namespace 独立：`s2_b8_injection_on/off`） |
| 注入 | `--inject-rounds 3`（K=2 窗口需 3 个强制失败轮；两臂注入完全相同） |
| **证据门** | **保持默认**（不设 `PATCH_EVIDENCE_GATE_ENABLE=false`）——这正是本批复验场景 |
| 两臂唯一差异 | `COVERAGE_STALL_DETECT_ENABLE=true`（on）/ `false`（off） |
| 预算护栏 | 任务级 `COST_BUDGET_ENABLE=true COST_BUDGET_USD=1.0`；`AITESTER_BATCH_MAX_CALLS=150`/臂；watchdog `1500s`/臂 |
| 真实 LLM | 是（planner/generator/debugger 真实调用；驱动仅进程内 monkeypatch 执行结果，生产文件零改动） |
| 成本上界 | 参考 S-2 默认闸冒烟（2 任务/臂：on 14395 tok、off 16293 tok）→ 10 任务两臂 ≈ **$0.08**（标准价上界），硬预算 ≤$0.15 |
| 失败策略 | 单臂失败/超时**如实记录、不重跑**（不 `--force` 覆盖）；两臂任一失败 → 不生成 ANALYSIS |

## 2. 判据（预注册，全部机读写入 `<OUT>/ANALYSIS.json`）

| 编号 | 规则 | 满足条件 |
|---|---|---|
| **P1 分支归属（主判据）** | ON 臂停滞优先分支实际拥有终止决定 | `stop_reason=coverage_stall` 率 = **1.0（10/10）** 且 日志 `"P2-4 覆盖率停滞（同迭代优先于 repair-invalid"` 计数 = **10** 且 日志 `"连续多次修复无效"` 计数 = **0** |
| **P2 默认关零变化** | OFF 臂保持历史 repair-invalid 口径 | `stop_reason=skip_debugger_repair_invalid` 率 = **1.0（10/10）** 且 该分支日志计数 = **10** 且 停滞日志计数 = **0** 且 crash = **0** |
| **P3 零迭代节省（负向预注册）** | 本修复**不承诺**迭代节省 | `iterations_mean(on) == iterations_mean(off)`（Δ=off−on=**0**）。Δ≠0 → `classification=unexpected_delta`（调查项，**不得**当作收益） |
| **P4 harness 有效性** | 注入确实覆盖两臂 | 两臂 `tasks_with_injection = 10` 且 `injected_rounds > 0` 且 crash = 0 |

**classification**：
- 全部满足 → `confirmed_priority`；
- P3 不满足（Δ≠0）→ `unexpected_delta`（无论 P1/P2）；
- 其余 → `not_confirmed`（逐项在 ANALYSIS 给出未满足项）。

**S-2 harness 聚合的 verdict 不作本批判据**：`REPORT.json` 的 S-2 主/次判据
（含"迭代节省 ≥1.0"）在默认闸协议下**结构上不可满足**（S-2 已登记），本批保留
该工件仅供审计对照；判定一律以 P1–P4 为准。

## 3. 预期与风险披露

- **预期**：P1 满足（修复后 ON 臂日志由停滞分支写出）；P2 满足（OFF 分支未改）；
  P3 Δ=0（默认协议下平局止于同一迭代，零迭代节省是**预期结果**）；P4 满足。
- **风险 1（样本量）**：n=10、单 seed、单模型（deepseek-flash）、fast 档；结论仅限
  机制/归因语义与默认协议非回归，不外推到能力收益或 logic/scientific 档。
- **风险 2（注入构造）**：失败为实验层强制注入，非自然缺陷失败率；repair-invalid
  由默认证据门拒绝写盘驱动（真实机制），但触发频率不代表真实任务分布。
- **风险 3（日志归属口径）**：P1/P2 的日志计数是**文本**证据；若日志文案在本批
  切点后被改动，计数会失真——脚本以当前定稿文案匹配（与代码注释同一口径）。
- **风险 4（并发干扰）**：两臂并发共享 CPU；S-2 同口径（墙钟不可比，判定不看墙钟）。
- **失败处理**：任何臂失败/看门狗超时 → 如实保留日志与半成品工件，不重跑；
  若注入记录显示 `injected_rounds=0`（注入未生效）→ P4 不满足 → `not_confirmed`
  （harness_limitation，不得解释为修复失败）。

## 4. 复验命令（Lead 在干净切点 worktree 上执行）

```bash
bash experiments/run_t4_a19_revalidation.sh \
  --root /Users/wangchenyu/Workspace/AITester-t-t4-<cutpoint-sha> \
  --expect-sha <cutpoint-sha> \
  --out experiments/results/t_round_a19_default_gate_20261018 \
  --tasks 10 --seed 42 --parallel 4 --inject-rounds 3 --watchdog-seconds 1500
# 可选：--strict（classification != confirmed_priority 时退出码 3）
```

执行前可先 `--dry-run` 校验路径/协议（零 LLM 调用，允许脏树）。
