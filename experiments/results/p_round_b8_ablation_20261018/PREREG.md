# P-2 探索性预注册（r3）：A-19 覆盖率停滞检测 wiring 修复后的缩小消融

> **性质：探索性消融测量（exploratory，非 confirmatory）**。不做"显著提升/因果"主张；
> 只报告描述性配对结果 + 配对一致性 + 后验 MDE + 局限。本文件在真实跑批**之前**落盘。
> 任务：登记册 §2 B8（A-19 覆盖率停滞检测开/关消融）——验"修好接线后是否真提前停止/省 token/影响收敛"。
> 日期：2026-10-18（P 轮）；执行：exp-runner-m；不 commit、不跑全量、不重跑失败臂。

## 0. 切点与修复版本

| 项 | 值 |
|---|---|
| 切点 commit（含 A-19 wiring 修复） | **`aeadb7bac0741313c09d3af58b5a3ce271ed091e`**（`p-stagnation`；仅 2 文件：`src/graph/workflow.py` + `tests/test_p_round_stagnation_wiring.py`，+329/−23） |
| 干净 worktree | `/Users/wangchenyu/Workspace/AITester-p2-b8-14a9662`（detached HEAD=`aeadb7b`；跑前/跑后 `git status --porcelain` 必须 0 行） |
| 修复前缺陷基线 | `14a9662`（A-19 为纸面功能：标签不可达 + 无提前停止；零 LLM 证据见 `WIRING_EVIDENCE_before.json`） |
| 解释器/数据 | 主仓 `.venv`（Python 3.14.6）；`.env.local` 在 worktree（gitignore 覆盖，不计 dirty） |
| 模型 | deepseek-flash；`TEMPERATURE=0.0`；`LLM_THINKING_MODE=disabled`；`AITESTER_LLM_CACHE=0` |
| 并发 | 两臂**并发**、独立 `AITESTER_CACHE_NAMESPACE`/log/trace；`BENCHMARK_PARALLELISM=4` |
| 预算/墙钟 | **≤ $0.3**；墙钟 **≤ 60min**；每臂 watchdog **3600s**（超时即终止、如实报告、不重跑） |

## 1. 修复说明（本消融的前提；commit `aeadb7b`）

修复前（`14a9662`）：`_coverage_stall_detected` 只被 `determine_stop_reason` 调用，
`_should_debug` / `_route_after_diagnosis` **不消费**该判定（无短路段），且停滞分支位于
MAX_ITERATIONS 之后 → `COVERAGE_STALL` 标签在自然终止时被遮蔽、提前停止从不发生。

修复（`aeadb7b`，已通过 26 个新回归测试 + 既有 205 个 workflow 路由测试 + ruff/mypy）：
1. `_should_debug` / `_route_after_diagnosis` 在**各自最后一个 `return "debug"` 之前**加入
   `_coverage_stall_enabled() and _coverage_stall_detected(state)` → trace `decision="done"/reason="coverage_stall"`、
   `state["stop_reason"]="coverage_stall"`、`return "done"`；不抢占任何既有 regenerate/done 分支；
2. `determine_stop_reason` 停滞分支移至 MAX_ITERATIONS 之前（新优先级 5；OFF 时检测器恒 False →
   历史标签逐位不变）；
3. 注释/文档同步（"纯观测层"→"短路消费"）。

**零 LLM 修复前/后证据（落盘，供 README 引用）**：
| 状态（iteration=2, max=3；最近 2 轮 failed 且 delta=0） | 修复前 `14a9662` | 修复后 `aeadb7b` |
|---|---|---|
| `_coverage_stall_detected` ON | True | True |
| `determine_stop_reason` ON | `coverage_stall`（仅标签） | `coverage_stall` |
| **`_should_debug` ON** | **`debug`（无提前停）** | **`done` + `stop_reason=coverage_stall`** |
| iteration=3(max) `determine_stop_reason` ON | `max_iterations`（遮蔽） | **`coverage_stall`** |
| `_route_after_diagnosis` ON | `debug` | **`done` + `coverage_stall`** |
| 全部 OFF 口径 | `debug` / `unknown` / `max_iterations` | **同左（零行为变化）** |
清单：`experiments/results/p_round_b8_ablation_20261018/WIRING_EVIDENCE_before.json`、
`WIRING_EVIDENCE_after.json`、`WIRING_DIFF.patch`（148 行 diff）。

## 2. 设计（两臂消融；r3 缩小规模）

| 项 | A 臂（stagnation ON） | B 臂（stagnation OFF） |
|---|---|---|
| CLI | `--enable-stagnation` | `--no-stagnation` |
| 生效 env | `COVERAGE_STALL_DETECT_ENABLE=true` | `COVERAGE_STALL_DETECT_ENABLE=false`（显式，覆盖档位预设） |
| 其余协议 | 同 cut、同命令、同 seed/判分口径 | 同左 |
| 命令 | `python -m experiments.run_benchmark --dataset synthetic --task-count 10 --seed 42 --baselines aitester --output-dir .staging_stagnation --enable-stagnation` | 同命令 + `--no-stagnation` |

- 两臂互斥 fail-fast（`experiments/run_benchmark.py::_apply_stagnation_arm`）；provenance
  `env_snapshot.COVERAGE_STALL_DETECT_ENABLE` 必须显示 true/false **不同**（预检 effective-env 门禁）。
- **档位：`AITESTER_PROFILE=fast`（显式理由）**：B8 只关心 workflow 迭代/停止路由；logic/scientific 档额外打开
  SPEC_IR/DSL/SMT/oracle 注入、mutation scoring/advisor、branch coverage 注入、detection-first 等，
  会引入非目标后处理开销/噪声并改变迭代次数；fast 保持 planner/generator/executor/debugger 主链路默认、
  `MAX_ITERATIONS=3`、`DETECTION_FIRST_ENABLE=false`、mutation scoring 关，隔离单变量。
  **与 logic 档差异**：logic = scientific 超集（上述开关全开）；本批结论只对 fast 口径负责，不外推。
- **r3 缩小规模披露**：task-count 15→**10**/臂（Lead 裁决；预算 ≤$0.3/墙钟 ≤60min，已获 Lead 批准）；
  预检估算若 >$0.3 自动降为 **8** 任务/臂并写 `PREREG_DOWNGRADE.md`。

## 3. 主/次指标与配对分析

**主指标（逐任务配对，A−B）**：`iterations`、`coverage`（%）、`test_passed`（收敛二值）。
**次要指标**：`stop_reason` 分布（尤 `coverage_stall` 触发计数）、`detection_rate`/`repair_rate`/`false_fix_rate`、
tokens/成本/墙钟、trace 中 `_should_debug`/`_route_after_diagnosis` 的 `reason=coverage_stall` 计数。
**配对口径**：共同 `task_id`（synthetic seed=42 确定性同序）；连续指标报告两臂均值/中位数、配对 Δ 均值、
符号一致性（降低/持平/升高）、**配对 bootstrap 95% CI（10,000 次，固定 seed）**；
**MDE（后验）**：`(z_{1-α/2}+z_{power})·sd(Δ)/√n`（α=0.05、power=0.8，n=配对数；因用观测 sd 属后验/探索性，不作 confirmatory）；
二值 `test_passed` 报告两臂比例 + 配对 2×2（A 独有/B 独有/一致）。

## 4. 判定（探索性三分类）

- `no_detectable_difference`：主指标 Δ 的 95% CI 跨 0 且 |Δ| < 后验 MDE → "本批未检出差异"；
- `direction_hint`：Δ 方向一致且 CI 不跨 0，但样本小/探索性 → 只报方向性提示，不作效果主张；
- **预期（修复后）**：ON 臂应在部分任务**提前停止**（stop_reason=coverage_stall、iterations 下降、tokens 下降），
  并可能在 repair/detection 上出现 trade-off（提前停可能放弃最后修复机会）——如实报告，不作"提升/损害"确证主张。
- 若 ON 臂仍无任何 coverage_stall 触发 → 如实报告（可能 synthetic/fast 任务太易、无连续 2 轮停滞场景，属功效限制而非再次接线缺陷）。

## 5. 局限与风险

- n=10 配对 + 单模型/单 synthetic 数据集/单 seed → 功效低；后验 MDE 只作披露；
- synthetic 任务含 mixed difficulty 随机模板混合，不跨 seed 稳定；fast 档无 oracle/mutation 等后处理，结论不外推 logic 档；
- `TEMPERATURE=0` 仍有服务端非确定性；两臂并发共享 CPU（后处理指标受影响，主指标在任务阶段采集）；
- 提前停止是 A-19 的预期 trade-off（连续 2 轮失败且 |Δcoverage|<eps、MAX_ITERATIONS=3 下从 3→2 轮），非缺陷；
- watchdog 3600s/臂：后处理长尾可能触发终止 → 如实报告、不重跑；
- 真实开关生效性由 provenance env_snapshot + trace 双重核验。

## 6. 产物

`experiments/results/p_round_b8_ablation_20261018/`：`PREREG.md`/`PREREG.json`、`PREFLIGHT.json`、
两臂 `benchmark_synthetic_*.json`、`log_stagnation.log`/`log_no_stagnation.log`、`traces_stagnation/`/`traces_no_stagnation/`、
`arm_stagnation.meta.json`/`arm_no_stagnation.meta.json`、`ABLATION_REPORT.json`、`README.md`、`SHA256SUMS`（`checksum_results.py --write` 校验通过）；
修复证据 `WIRING_EVIDENCE_before.json`/`WIRING_EVIDENCE_after.json`/`WIRING_DIFF.patch`；
worktree 保留待 Lead 清理；不 commit、不跑全量、不重跑失败臂。
