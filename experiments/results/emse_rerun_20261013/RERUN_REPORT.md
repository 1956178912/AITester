# EMSE 确认性实验复跑报告（2026-10-13 晚至 2026-10-14 晨）

> 状态：**已完成**（emse-rerun 子代理启动受阻后，由主进程直接接管完成）
> 批次：`emse_rerun_20261013`

## 0. 执行摘要

| 子实验 | 状态 | 结果 |
|---|---|---|
| T-08 seed 42（基线） | ✅ 已完成（历史） | detection 14.81%→9.20%（见 `emse_t08_gates_20261013/T08_REPORT.md`） |
| T-08 seed 43 | ✅ 已完成（v2 重跑） | 3 种子合并确认阴性（§2） |
| T-08 seed 44 | ✅ 已完成 | 3 种子合并确认阴性（§2） |
| spec_ir 冒烟（3 任务） | ✅ 已完成 | SPEC_IR 管线开 + spec_replace 生效（§4） |
| spec_ir 全量（50 任务） | ✅ 已完成 | **+12pp 正向增益，p=0.0703**（§4） |

## 1. 实验设计

### 实验 1：T-08 双门复跑（补 seed 43/44）

- 目标：对齐主批次 3 种子（42/43/44），验证双门（特异性门 + 红回归门）对 detection/过红/抹红的效应是否跨种子稳健。
- 主批次基线：`experiments/results/main_batch/benchmark_synthetic_20261006_*.json`（seed 42/43/44，各 87 任务，无双门）。
- 命令：`AITESTER_PROFILE=logic AITESTER_CACHE_NAMESPACE=t08_gates_seed{43,44} .venv/bin/python experiments/run_benchmark.py --dataset synthetic --baselines aitester --seed {43,44} --task-count 87 --parallel 2`

### 实验 2：spec_ir（完整规格优先 NL + SpecExpr）

- 目标：补跑 scale87 缺失的"SpecExpr 形式化子句注入"臂。scale87 的 replace 臂 `SPEC_IR_ENABLE=None`（规格解析管线未开，规格文档仅 NL+docstring）。
- **干净口径**（主进程修正）：`DETECTION_SPEC_MODE=replace + SPEC_IR_ENABLE + SPEC_IR_DSL_ENABLE`，**不设 profile**（fast 档，无 mutation/双门）——与 scale87 replace 臂唯一变量 = SPEC_IR，可干净隔离 SpecExpr 通道贡献。
- 冒烟验证：不设 profile 时 spec_expr_coverage 仍 >0（SpecExpr 子句在干净口径下仍生成），故全量采用此口径。

## 2. T-08 双门复跑：3 种子合并确认阴性

工件：`emse_t08_gates_20261013`（seed42）+ `emse_t08_gates_seed43_v2_20261013` + `emse_t08_gates_seed44_20261013`；对照 = 主批次 3 种子。

| 指标 | 主批次（无双门，261 行） | T-08（含双门，261 行） | Δ |
|---|---|---|---|
| detection 率 | 15.83%（38/240） | **8.43%**（22/261） | **−7.40pp** |
| 过红（red_not_repaired ∧ det=0） | 88 | 45 | −43 |
| 抹红（red_then_green ∧ det=0） | 28 | 19 | −9 |
| 全绿假成功（all_green ∧ det=0） | 86 | **175** | **+89** |

**结论（确认性）**：seed 42 的阴性结果跨 3 种子稳健——双门不仅不能消除 −28pp，反而使 detection 下降 7.4pp。机制：特异性门确实拦截过红（88→45），但拦截后 regenerate 的测试大多变成**全绿假成功**（86→175，+89），把"可见的红"转化为"不可见的全绿"；抹红通道小幅下降（28→19）。**双门是"对症不对根"——根本瓶颈（测试生成侧不产红）不受双门影响，反而被双门的 regenerate 加重。**

## 3. 复算口径

- detection 率 = detection_rate==1 行数 / detection_rate 非 None 行数
- 过红 = detection_first_status=='red_not_repaired' ∧ detection_rate==0
- 抹红 = detection_first_status=='red_then_green' ∧ detection_rate==0
- 全绿假成功 = detection_first_status=='all_green_unverified' ∧ detection_rate==0

## 4. spec_ir 全量结果：SpecExpr 通道有正向增益

工件：`experiments/results/emse_spec_ir_quixbugs_20261013/benchmark_quixbugs_20261014_005101.json`（50 任务 QuixBugs seed42）。

provenance 确认：`profile=None`、`SPEC_IR_ENABLE=true`、`SPEC_IR_DSL_ENABLE=true`、`DETECTION_SPEC_MODE=replace`、`ENABLE_MUTATION_SCORING=None`、`spec_replace_applied=50/50`、cache_hits=1（全新抽样）。spec_compile_rate=0.6321（n=50）、spec_expr_coverage=0.6069（n=45）。

| 臂 | detection | 说明 |
|---|---|---|
| off 基线（scale87） | 65.71%（23/35） | 不规格优先 |
| replace 纯 NL（scale87） | 62.86%（22/35） | 纯 NL 规格优先 |
| **replace + SpecExpr（本次）** | **77.78%**（28/36） | 完整规格优先 |

**配对 McNemar（spec_ir vs scale87 replace，50 任务同 task_id）**：仅 spec_ir 检出 7、仅 scale87 检出 1、双中 21、双未 21；不一致对 8，δ=**+12.00pp**，**p=0.0703**。

**结论**：SpecExpr 形式化子句通道有**方向明确的正向增益**（+12pp，7:1 不一致对），p=0.0703 为趋势显著（未达 0.05），n=50 功效不足，需补样确认。这与 T-08 的阴性结果形成关键对比：

- **协议层加法（双门）无效**（T-08：−7.4pp）；
- **规格层升级（SpecExpr）有增益**（spec_ir：+12pp，p=0.07）。

即：优化方向是**规格驱动（生成器侧）**，而非协议加法——与评审 v2 "优化方向 = 规格驱动 / 变异反馈"的判断一致，为论文核心主张提供实证支持。

## 5. 成本

| 跑批 | token | 调用 | 估算成本 |
|---|---|---|---|
| T-08 seed43_v2 + seed44（2×87 任务） | ~200 万 | ~790 | ~$0.56 |
| spec_ir（50 任务 QuixBugs） | 711,673 | 236 | ~$0.20 |
| **合计** | | | **~$0.76** |

## 6. 基础设施问题（emse-rerun 记录，供团队知悉）

T-08 seed 43 的早期三次启动（emse-rerun 子代理执行）均受阻：

1. **沙箱内后台跑批**：85/87（98%，28m42s）被外部 SIGKILL——沙箱对 >28 分钟长跑有资源回收。
2. **非沙箱 + mutation 开启**：87/87 完成但 mutation 后处理病态慢（64+ 分钟，大量 30s 超时），手动停止。
3. **非沙箱 + --no-mutation**：启动 5 分钟 fork EAGAIN。

**根因**：第 2 次非沙箱跑批在 mutation 后处理阶段批量 spawn 大量 python 子进程（每变异体一个，无沙箱进程数上限），TaskStop 杀父进程后子进程成孤儿，耗尽进程表/内存，导致 shell 全面崩坏（新进程 spawn 即 SIGSEGV）。

**恢复与最终成功**：shell 恢复后，由**主进程直接启动**的串联跑批（`run_in_background` task XqhcMZ，seed43_v2 → seed44 → spec_ir）顺利完成（22:59 / 00:26 / 00:51 写盘）——佐证崩溃是孤儿进程耗尽型临时故障，非环境永久损坏。

**经验**：子代理启动的后台跑批会因子代理生命周期结束而被连带终止（summary json 未写盘）；长跑批应由主进程直接启动（`run_in_background`），更稳健。

## 7. 对 EMSE 叙事的价值

1. **T-08（阴性）**：双门不能消除 −28pp 的机制级归因——"对症不对根"，双门的 regenerate 反而加重全绿假成功。
2. **spec_ir（阳性趋势）**：SpecExpr 形式化子句通道 +12pp（p=0.07），首次在同一数据集上隔离"SPEC_IR"变量给出正向证据——把 scale87 的"纯 NL 规格优先阴性"升级为"完整规格优先阳性趋势"，为"规格驱动"路线提供实证支点。
3. 两者共同构成"**协议层做减法、规格层做加法**"的完整证据链，直接支撑 EMSE 论文的核心主张。
