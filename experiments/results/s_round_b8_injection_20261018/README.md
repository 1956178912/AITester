# S-2 / B8 / A-19：覆盖率停滞检测开/关消融（**确定性失败注入 harness**，2026-10-18）

> **性质**：机制验证性消融（harness-based ablation）——用**实验层确定性失败注入**保证
> 多轮失败 + 覆盖率停滞，回答"停滞检测（P-2 已接线）是否真的提前停止、省多少迭代"。
> **不是**对自然任务收益的估计：注入的失败是实验构造，结论只关于 A-19 停止逻辑本身。
> 预注册（跑前冻结）：[`PREREG.md`](PREREG.md) sha256=`982a19be5bc5955cd9abc1ee31d2efd47857f8fd63e5327369d05cd7d6c6ee80`；
> 切点 = 干净 worktree `566f97339b0b9728f8a948afbf449a2eb87408c2`（HEAD 见 `REPORT.json`/`ISOLATION.json`）。

## 1. 结论（预注册判定）

**classification = `confirmed`**

| 判据 | 规则 | 实测 | 满足 |
|---|---|---|---|
| 主判据 | on 臂 coverage_stall 触发率 ≥80% 且 off 臂 =0% | on **10/10 = 1.0**；off **0/10 = 0.0** | ✅ |
| 次判据 | on 平均 iterations 比 off 少 ≥1 轮且两臂 0 crash | iterations 均值 on **1.8** vs off **3.0**（off−on = **1.2**）；crash on/off = 0/0 | ✅ |
| harness 有效性 | on 臂注入覆盖任务 ≥80% 且注入轮 >0 | 10/10 任务、30 注入轮 | ✅ |

## 2. 注入方法与隔离证明

- **patch 目标（仅进程内 monkeypatch，`AITESTER_B8_INJECTION_ENABLE=1` 生效）**：
  1. `src.graph.nodes._executor_node`（及 `src.graph.workflow` 模块级引用）：**仅透传 state**，原逻辑原样执行；
  2. `src.agents.executor.ExecutorAgent.execute`：前 `inject_rounds=3` 轮（按 `state["iteration"]`）
     返回强制失败 `passed=False, output="INJECTED_FAILURE…"`，`coverage=上一轮 coverage`（首轮 0.0）
     → `execution_trace` 的 `coverage_delta` 从第 2 轮起恒 `0.0`（|Δ|<eps=0.5），满足
     `_coverage_stall_detected`（K=2 窗口；首轮 delta=None 不计数，故需 3 个强制失败轮）；
     第 `3 + 1` 轮起**恢复真实执行**（调原 `ExecutorAgent.execute`）。
- **两臂注入完全相同**，唯一差异 = `COVERAGE_STALL_DETECT_ENABLE=true|false`。
- **隔离证明**：生产文件零 diff（`git status --porcelain` / `git diff --stat` 前后为空，
  见 `ISOLATION.json` checks 全绿）；驱动在主仓 untracked，通过 `--root` 对 worktree 运行；
  运行时校验所有项目模块 `__file__` 均来自 `--root`。
- **注入记录**：`arm_on/injection_records_on.jsonl` / `arm_off/injection_records_off.jsonl`
  （逐轮 `task_id/iteration/injected/passed/coverage/coverage_delta/…`）。

## 3. 协议

| 项 | 值 |
|---|---|
| 切点 | 干净 worktree（HEAD `566f97339b0b9728f8a948afbf449a2eb87408c2`，dirty=0；两臂 provenance 见下） |
| 数据集 | synthetic（`--dataset synthetic --task-count 10 --seed 42`） |
| 档位 | `AITESTER_PROFILE=fast`（与 P-2 同：隔离 workflow 停止路由单变量）；`TEMPERATURE=0.0` / `LLM_THINKING_MODE=disabled` |
| 并行 | `BENCHMARK_PARALLELISM=4`；两臂**并发**（两个进程、独立 cache namespace `s2_b8_injection_on/off`） |
| 真实 LLM | 是（planner/generator/debugger 真实调用；`AITESTER_LLM_CACHE=0`）；cap `AITESTER_BATCH_MAX_CALLS`、任务级 `COST_BUDGET_ENABLE/USD`、watchdog `1500.0s/臂` |
| 注入轮 | `--inject-rounds 3`（两臂相同） |
| 额外 env（两臂同设） | `{"PATCH_EVIDENCE_GATE_ENABLE": "false"}`（理由见 PREREG §2） |

主批实际命令（两臂**并发**两个进程、同一 worktree/同一 out；worktree 跑后保留）：

```bash
# 臂 on（stall ON）
.venv/bin/python experiments/run_b8_injection.py --root /Users/wangchenyu/Workspace/AITester-s2-b8-566f973 \
  --out experiments/results/s_round_b8_injection_20261018 --arm on --tasks 10 --seed 42 \
  --profile fast --inject-rounds 3 --watchdog-seconds 1500.0 \
  --extra-env PATCH_EVIDENCE_GATE_ENABLE=false
# 臂 off（stall OFF）：同上，--arm off
# 零 LLM 聚合（判定/成本/隔离证据/SHA）
.venv/bin/python experiments/run_b8_injection.py --out experiments/results/s_round_b8_injection_20261018 --aggregate-only
```

## 4. 两臂实测

| 项 | on 臂（stall ON） | off 臂（stall OFF） |
|---|---|---|
| 任务数 | 10 | 10 |
| 墙钟(s) | 65.26 | 84.27 |
| stop_reason 分布 | `coverage_stall`×10 | `max_iterations`×6, `test_passed`×4 |
| **coverage_stall 触发** | **10/10 = 1.0** | **0/10 = 0.0** |
| iterations 均值/中位/max | 1.8 / 2 / 2 | 3.0 / 3 / 3 |
| coverage 均值 | 0.0 | 94.7 |
| passed 行数 | 0 | 4 |
| detection（可测/检出） | 10/0（0.0） | 10/0（0.0） |
| crash 行 | 0 | 0 |
| 注入记录（注入/真实轮） | 30/0 | 32/10 |
| tokens / LLM calls | 83246 / 58 | 113638 / 82 |
| 成本（标准价上界） | $0.046531 | $0.060761 |
| provenance git_sha/dirty | 566f97339b0b9728f8a948afbf449a2eb87408c2/False | 566f97339b0b9728f8a948afbf449a2eb87408c2/False |
| env_snapshot.COVERAGE_STALL_DETECT_ENABLE | true | false |

成本合计 ≈ **$0.107292**（预算 ≤$0.3）；两臂并发墙钟合计 149.53s。

## 5. 配对（共同任务；Δ iterations = off − on）

n_pairs = 10；Δ均值 = **1.2**；
方向 off>on / = / off<on = 10 / 0 / 0。

| task_id | iter(on) | iter(off) | Δ(off−on) | stop(on) | stop(off) | 注入轮(on) | 注入轮(off) |
|---|---|---|---|---|---|---|---|
| synthetic__task_0000 | 2 | 3 | +1 | coverage_stall | max_iterations | 3 | 3 |
| synthetic__task_0001 | 1 | 3 | +2 | coverage_stall | max_iterations | 3 | 4 |
| synthetic__task_0002 | 2 | 3 | +1 | coverage_stall | max_iterations | 3 | 3 |
| synthetic__task_0003 | 2 | 3 | +1 | coverage_stall | test_passed | 3 | 3 |
| synthetic__task_0004 | 2 | 3 | +1 | coverage_stall | test_passed | 3 | 3 |
| synthetic__task_0005 | 2 | 3 | +1 | coverage_stall | max_iterations | 3 | 3 |
| synthetic__task_0006 | 2 | 3 | +1 | coverage_stall | max_iterations | 3 | 3 |
| synthetic__task_0007 | 2 | 3 | +1 | coverage_stall | test_passed | 3 | 4 |
| synthetic__task_0008 | 1 | 3 | +2 | coverage_stall | max_iterations | 3 | 3 |
| synthetic__task_0009 | 2 | 3 | +1 | coverage_stall | test_passed | 3 | 3 |

## 6. 判读

- 若 confirmed：在"确实多轮失败且覆盖率停滞"的构造场景下，停滞检测按设计在 1.8 轮提前停止（off 臂 3.0 轮），**省 1.2 轮**且两臂无 crash；说明 P-2 的 wiring 修复在真实 workflow 中生效（非仅零 LLM 单测）。
- 若 not_confirmed：按 REPORT 中 `criteria` 逐项给出未满足项与归因（注入未稳定触发→harness_limitation；被判据以外的路由分支抢占→如实记录）。
- **不外推**：注入失败是实验构造（非自然缺陷失败率）；结论限于停止逻辑，不代表真实任务上的收益/代价，也不代表 logic/scientific 档行为（fast 档单变量）。
- **iteration 计数语义**：行级 `iterations` = 修复轮次索引（patch_applier 每次 +1），不是执行次数；
  ON 臂 2 个任务在执行第 3 轮时经 generator-regenerate 路径、修复索引仍为 1（trace_len=3），
  故 `iterations_mean=1.8` 而非 2.0。判定按预注册规则（停滞窗口 K=2 满足后短路），该差异已在
  §5 配对表逐任务披露（`delta` 仍 ≥1）。
- **注入轮数**：on 臂 30 个强制失败轮（10 任务×3）；off 臂
  32 个（2 个任务因 regenerate 路径出现额外 iteration<3 的执行轮，
  仍属同一注入规则 `iteration < inject_rounds`，非重跑/补测）。

## 7. 局限

- synthetic + fast 档 + 单 seed（42）+ 单模型（deepseek-flash）；两臂并发共享 CPU。
- 注入只 patch 执行结果，planner/generator/debugger 仍真实 LLM 调用——不同任务的 debugger 补丁行为可能使循环提前停止（repair_invalid 等），这些真实分支抢占会如实反映在 stop_reason 分布中。
- 探索性机制验证：n=10，不做 confirmatory/因果主张。
- 注入轮=3（K=2 窗口需要 3 个强制失败轮，理由见 §2）。

## 9. 跑前 harness 冒烟（非主判定；披露）

两轮冒烟用于在冻结预注册前验证注入 harness 与停滞判据可达性（工件在
`_harness_smoke/`、`_harness_smoke_gateoff/`，不参与主判定）。冒烟合计
**64415 tokens ≈ $0.033032**（标准价）；主批 196884 tokens ≈ $0.107292；
**含冒烟总成本 ≈ $0.140324**（预算 ≤$0.3）。

| 冒烟目录 | 臂 | PATCH_EVIDENCE_GATE_ENABLE | iterations | iterations 均值 | stop_reason 分布 |
|---|---|---|---|---|---|
| `_harness_smoke` | on | default(true) | [2, 2] | 2.0 | `coverage_stall`×2 |
| `_harness_smoke` | off | default(true) | [2, 2] | 2.0 | `skip_debugger_repair_invalid`×2 |
| `_harness_smoke_gateoff` | on | false | [2, 2] | 2.0 | `coverage_stall`×2 |
| `_harness_smoke_gateoff` | off | false | [3, 3] | 3.0 | `max_iterations`×1, `test_passed`×1 |

关键结论：**默认协议（证据门默认 true）下，repair-invalid 分支在停滞窗口同一迭代收敛**——
on/off 两臂均 iterations=2，ON 仅把终止标签换成 `coverage_stall`（无迭代节省）；这是 A-19
接线后的**默认口径局限**，本批通过两臂同设 `PATCH_EVIDENCE_GATE_ENABLE=false` 解除前置抢占后
测量"可达场景"的提前停止收益（主判定口径）。该发现写入 README/PREREG，不改主判定规则。

## 10. 文件

| 文件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结的预注册（sha256 见上） |
| `REPORT.json` | 机读聚合（两臂汇总/配对/判据/成本/隔离） |
| `arm_on/`、`arm_off/` | 每臂批次 JSON（自带时间戳）+ `traces/` + 注入记录 + meta JSON |
| `ISOLATION.json` | 生产文件零 diff 证据（git status/diff 前后快照 + checks） |
| `SHA256SUMS` | 全工件校验（`shasum -a 256 -c SHA256SUMS`） |
