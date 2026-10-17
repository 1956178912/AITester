# P-2 / B8：A-19 覆盖率停滞检测开/关消融（探索性，2026-10-18）

> **性质：探索性描述性测量（非 confirmatory）**。不主张「显著提升/因果」；报告配对 Δ、配对一致性、后验 MDE 与局限。
> 切点：`aeadb7bac0741313c09d3af58b5a3ce271ed091e`（p-stagnation，含 A-19 wiring 修复）；worktree `/Users/wangchenyu/Workspace/AITester-p2-b8-14a9662`；commit `aeadb7bac0741313c09d3af58b5a3ce271ed091e`。

## 1. 协议（固定；预注册见 `PREREG.md` / `PREREG.json`，跑前落盘）

- 两臂**并发**：A=`--enable-stagnation`（`COVERAGE_STALL_DETECT_ENABLE=true`）/ B=`--no-stagnation`（=false 显式）；`--dataset synthetic --task-count 10 --seed 42 --baselines aitester`。
- `AITESTER_PROFILE=fast`（理由：隔离 workflow 迭代/停止路由单变量，避免 logic/scientific 档 oracle/mutation/branch-coverage/detection-first 噪声；与 logic 档差异见 PREREG §2）；`TEMPERATURE=0.0 LLM_THINKING_MODE=disabled BENCHMARK_PARALLELISM=4`；`AITESTER_LLM_CACHE=0`；`COST_BUDGET_ENABLE=true COST_BUDGET_USD=1`；`AITESTER_BATCH_MAX_CALLS=100`；两臂独立 namespace。
- 预算 ≤ $0.3；墙钟 ≤ 60min；每臂 watchdog 3600s；单臂失败/超时如实报告不重跑。

## 2. 修复背景：A-19 wiring（纸面功能 → 真提前停止）

修复前 `14a9662`：`_coverage_stall_detected` 仅被 `determine_stop_reason` 调用；`_should_debug` / `_route_after_diagnosis` 无短路段，且停滞分支在 MAX_ITERATIONS 之后 → 标签被遮蔽、提前停止从不发生。修复 `aeadb7b`（2 文件，+329/−23）：两路由函数在最后 `return "debug"` 前短路为 done+`stop_reason=coverage_stall`；`determine_stop_reason` 停滞分支移至 MAX_ITERATIONS 之前；文档同步。回归：新测试 26 个 + 既有 workflow 路由 205 个全绿；ruff/mypy 干净。零 LLM 修复前/后证据：

| 状态（iteration=2, max=3；最近 2 轮 failed 且 coverage_delta=0） | 修复前 `14a9662` | 修复后 `aeadb7b` |
|---|---|---|
| `_coverage_stall_detected`（ON） | `True` | `True` |
| `determine_stop_reason`（ON, iter=2） | `coverage_stall` | `coverage_stall` |
| **`_should_debug`（ON, iter=2）** | `debug` | `done` |
| `determine_stop_reason`（ON, iter=max） | `max_iterations` | `coverage_stall` |
| `_route_after_diagnosis`（ON） | `—` | `done` |
| **OFF 口径（_should_debug / max 标签）** | `debug / max_iterations` | `debug / max_iterations` |

（证据文件：`WIRING_EVIDENCE_before.json` / `WIRING_EVIDENCE_after.json` / `WIRING_DIFF.patch`）

## 3. 两臂表（实测）

| 项 | A（stagnation ON） | B（stagnation OFF） |
|---|---|---|
| 批次 sha256 | `5164eca3909b7b92…` | `0950a9fe58ef94f4…` |
| 行数 | 10 | 10 |
| exit code | 0 | 0 |
| 墙钟(s) | 29 | 31 |
| tokens / LLM calls | 32993 / 20 | 36612 / 21 |
| 成本（标准价上界） | $0.022606 | $0.024666 |
| env_snapshot.COVERAGE_STALL_DETECT_ENABLE | `true` | `false` |
| stop_reason 分布 | `test_passed`=10 | `test_passed`=10 |
| `coverage_stall` 标签计数 | **0** | 0 |
| trace `reason=coverage_stall` 计数 | **0** | 0 |
| 行字段完整（8 键） | `{'task_id': 10, 'passed': 10, 'coverage': 10, 'iterations': 10, 'stop_reason': 10, 'detection_rate': 10, 'repair_rate': 10, 'false_fix_rate': 10}` | `{'task_id': 10, 'passed': 10, 'coverage': 10, 'iterations': 10, 'stop_reason': 10, 'detection_rate': 10, 'repair_rate': 10, 'false_fix_rate': 10}` |
| 样本 difficulty 分布 | `{"1": 4, "2": 3, "3": 1, "5": 2}` | `{"1": 4, "2": 3, "3": 1, "5": 2}` |

## 4. 主指标配对对比（共同任务；A−B）

共同任务：**10**。

| 指标 | n | A 均值 | B 均值 | Δ(A−B) 均值 | 中位 Δ | bootstrap 95% CI | 后验 MDE | 符号(A<B/=/A>B) |
|---|---|---|---|---|---|---|---|---|
| iterations | 10 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | 0.0000 | 0/10/0 |
| coverage(%) | 10 | 95.7000 | 95.8000 | -0.1000 | 0.0000 | [-0.6000, 0.3000] | 0.6537 | 1/8/1 |
| test_passed(1/0) | 10 | 1.0000 | 1.0000 | 0.0000 | 0.0000 | [0.0000, 0.0000] | 0.0000 | 0/10/0 |

`test_passed` 配对 2×2：both_pass=10、A_only=0、B_only=0、both_fail=0。

## 5. 次指标（detection / repair / false_fix；None 不参与配对）

| 指标 | n | A 均值 | B 均值 | Δ(A−B) | 符号(A<B/=/A>B) |
|---|---|---|---|---|---|
| detection_rate | 10 | 0.0000 | 0.0000 | 0.0000 | 0/10/0 |
| repair_rate | 10 | 0.0000 | 0.0000 | 0.0000 | 0/10/0 |
| false_fix_rate | 10 | 1.0000 | 1.0000 | 0.0000 | 0/10/0 |

两臂 detection 聚合：A=`{"measurable": 10, "detected": 0, "rate": 0.0}` / B=`{"measurable": 10, "detected": 0, "rate": 0.0}`。

**关键解读**：两臂 `detection_rate` 均 **0.0/10**、`repair_rate` 均 **0.0/10**、`false_fix_rate` 均 **1.0/10**——即 10/10 任务生成的测试在 **buggy 代码上直接全绿**（未检出缺陷、无修复、全部 false fix），`passed=True`/`stop_reason=test_passed` 只表示「测试全绿」，**不代表任务成功**；workflow 因此从未进入 debugger 修复循环。

## 6. stall 触发证据

本批**未观测到任何提前停止/停滞标签**（A 臂 coverage_stall 标签=0、trace `reason=coverage_stall`=0）。

- 直接原因：两臂任务阶段均为**首轮一次通过**——A 臂 `10/10` 任务 iterations=0 且 passed、B 臂 `10/10`；executor 首轮 PASS，trace 每任务仅 1 条（planner→generator→executor→`_should_debug:done`@test_passed）。
- 停滞判据要求「最近 K=2 轮 failed 且 |coverage_delta|<eps」才可能触发；首轮即通过时**没有修复循环/第二轮**，结构上不可能触发。
- 直接证据：两臂 `detection_rate=0/10`、`repair_rate=0/10`、`false_fix_rate=1.0`（10/10）——生成的测试在 buggy 代码上全绿（未检出），因此没有失败测试、没有 debugger 修复循环（iterations=0、trace 仅 1 条）。与历史口径一致（BASELINE.yaml：synthetic+aitester 覆盖率 84–94% 而检出率仅 13–16%），本样本恰为 0/10 检出的抽样情形。
- 归因：**场景/功效限制**（synthetic mixed + seed=42 前 10 任务未产生失败测试 → 无修复轮次），**不是 wiring 缺陷**——接线已由 §2 零 LLM 前后证据锁定。
- 结论：本轮**无法评估**提前停止的 token 收益/修复代价；需下一轮改用**保证多轮失败**的任务集（如更高 difficulty / 真实缺陷 QuixBugs / 增大任务数与筛选失败样本）再消融。

## 7. 成本 / 墙钟

- 两臂成本合计（标准价上界）≈ **$0.047272**（预算 ≤$0.3）。
- 两臂并发墙钟：A=29s / B=31s。

## 8. 局限

- 探索性、n=10 配对；单模型/单 dataset/单 seed；**不做 confirmatory/因果主张**；后验 MDE 仅披露。
- synthetic 任务含 mixed difficulty 随机模板；fast 档无 oracle/mutation 等后处理——结论不外推 logic/scientific 档。
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU，后处理指标受争抢影响（主指标在任务阶段采集）。
- 提前停止是 A-19 的预期 trade-off（连续 2 轮失败且 |Δcoverage|<eps、MAX_ITERATIONS=3 下从 3→2 轮），须结合 `iterations↓ / repair / detection` 一并解读。
- **本批无触发机会（关键局限）**：两臂 10/10 任务首轮一次通过（iterations=0、trace 仅 1 条、stop_reason=test_passed），修复循环从未进入 → 停滞判据（最近 K=2 轮失败且 |Δcoverage|<eps）结构上不可达；因此本批**无法回答**停滞检测的收益/代价，需下一轮用保证多轮失败的任务集（更高 difficulty / 真实缺陷 QuixBugs / 扩大任务数并筛失败样本）重做消融。
- **次指标退化（常量）**：行级 `detection_rate`/`repair_rate`/`false_fix_rate` 本批在场但两臂均为常量（detection=0、repair=0、false_fix=1.0）→ 无配对变异、Δ 恒 0，不能提供额外区分信息；主指标 iterations/coverage/test_passed 可用。
- **执行备注（透明披露）**：两臂 LLM 执行均 exit=0、批次 JSON 完整；runner 在 [5/7] 分析阶段因可选证据键 KeyError 中断，本报告的 ABLATION_REPORT/README 由两臂已完成批次 JSON **零 LLM 补算**生成（未重跑任何 LLM 臂；analyzer 已修复并重跑）。

## 9. 探索性结论

**分类：`no_stall_trigger_observed`** —— 本批未触发任何停滞判定（A 臂 coverage_stall 标签=0、trace 计数=0）→ **无法评估提前停止的收益/代价**。直接原因：两臂 10/10 任务生成的测试在 buggy 代码上全绿（detection=0/10、false_fix=1.0），无失败测试 → 从未进入 debugger 修复循环（iterations=0）→ 停滞判据（最近 2 轮失败）无机会触发——属场景/功效限制（非 wiring 缺陷；wiring 已由零 LLM 前后证据锁定）。

## 10. 文件

| 文件 | 说明 |
|---|---|
| `PREREG.md` / `PREREG.json` | 跑前落盘的探索性预注册（含修复披露） |
| `PREFLIGHT.json` | 切点/干净度/env 开关生效性/wiring 证据/预算门禁 |
| `benchmark_synthetic_*.json` | 两臂批次工件 |
| `log_stagnation.log` / `log_no_stagnation.log` | 两臂完整日志（env/命令/开始结束/git） |
| `traces_stagnation/` / `traces_no_stagnation/` | 逐任务 trace（含 `_should_debug` 决策/`reason=coverage_stall` 证据） |
| `arm_stagnation.meta.json` / `arm_no_stagnation.meta.json` | 逐臂元数据（token/成本/逐任务/stall 计数/trace 统计） |
| `ABLATION_REPORT.json` | 机读聚合（配对 Δ/CI/MDE/2×2/stall 证据/分类） |
| `WIRING_EVIDENCE_before.json` / `WIRING_EVIDENCE_after.json` / `WIRING_DIFF.patch` | A-19 wiring 修复前/后证据与 diff |
| `SHA256SUMS` | `checksum_results.py --write` 生成（跑后校验 verify） |

