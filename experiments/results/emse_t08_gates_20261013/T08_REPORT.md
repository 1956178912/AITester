# T-08 双门复跑结果报告（2026-10-13）

> 批次：`emse_t08_gates_20261013`；复算：`experiments/emse_t08_gates_recompute.py`
> （零 LLM 纯 stdlib）；对比对象：主批次 R-P0-2 seed42（无双门）vs 本批 seed42
> （含双门），87 任务配对（同 task_id）。

## 1. 实验设计

- **动机**：主批次（2026-10-06）aitester 臂 logic 档**无双门**（env_snapshot 无
  `DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE`），检出率
  14.81%（seed42 单种子），留下 37 行过红 + 9 行抹红（seed42）。双门于 AC2
  （第十轮审查 T-P0-4）加入 logic 档，本批验证其能否消除过红/抹红、提升检出。
- **命令**：`AITESTER_PROFILE=logic AITESTER_CACHE_NAMESPACE=t08_gates_seed42`
  `--dataset synthetic --baselines aitester --seed 42 --task-count 87 --parallel 2`
- **provenance 确认**：`profile=logic`、双门两开关 `true`、cache_hits 仅 7/395
  （1.74%，全新抽样 ✅）、模型 `deepseek-flash`、temp=0。
- **成本**：1,008,472 token / 395 次 LLM 调用 ≈ **$0.28**（1h5m 墙钟）。

## 2. 结果（配对公平对比，seed42 单种子 n=87）

| 指标 | 主批次（无双门） | T-08（含双门） | Δ |
|---|---|---|---|
| detection 率 | 14.81%（12/81） | 9.20%（8/87） | **−5.61pp** |
| 过红（red_not_repaired ∧ det=0） | 37 | 17 | −20 |
| 抹红（red_then_green ∧ det=0） | 9 | 10 | +1 |
| 全绿假成功（all_green ∧ det=0） | 23 | 52 | **+29** |
| 不可测（detection=None） | 6 | 0 | −6 |

配对级 detection 迁移（87 任务，同 task_id）：

| 迁移 | 计数 |
|---|---|
| det0 → det0 | 65 |
| **det0 → det1（双门救回）** | 4 |
| **det1 → det0（双门抹掉）** | **8** |
| det1 → det1 | 4 |
| detNone → det0 | 6 |

净效果 = +4 − 8 = **−4**（12 → 8）。

## 3. 机制分析

### 3.1 特异性门拦截了过红，但 regenerate 产物是"全绿假成功"

`specificity_gate_verdict` 分布：None=52、`over_red`=25、`specific_red`=10。
特异性门确实拦截了 25 个过红并路由 regenerate，但状态迁移显示：

- `red_not_repaired → all_green_unverified`：**23** 行（过红被 regenerate 成
  全绿假成功，而非检出）；
- `red_then_green → all_green_unverified`：**13** 行（原"红后绿"被 regenerate
  成全绿）；
- 全绿假成功总量 23 → **52**（+29）。

即：特异性门把"过红"（至少见过红）推向了"全绿"（连红都看不到了）——regenerate
后的测试在缺陷原码上全绿，检出被系统性抹掉，与 `spec_first.py` 文档描述的
"oracle-from-implementation"机制同源：regenerate 的生成器仍从实现反推期望值。

### 3.2 红回归门从未触发

`red_regression_violation` 分布：87/87 全 None——抹红通道（10 行）**没有得到
对症处理**。原因是红回归门需要"再生成测试在未修补源码上变绿"这一具体场景，而
本批 `regeneration_count` 83/87 仅 regenerate 1 次（首轮全绿 → DETECTION_FIRST
触发一次），未进入红回归门的判定窗口。

### 3.3 双门"抹掉"8 个原本检出的任务

配对迁移 `det1 → det0` 共 8 行：主批次检出的任务（red_then_green det=1）在
双门复跑下被 regenerate 成全绿假成功（落入 3.1 的 13 行 red_then_green →
all_green 之中）。这是双门（特异性门 regenerate 路由）与 DETECTION_FIRST
（首轮全绿 → regenerate）在"首轮红"后**交互竞争**的副作用：原本已检出的任务
被误路由 regenerate，再生成产物全绿。

### 3.4 根本瓶颈：全绿假成功（"测试生成侧不产红"）

T-08 全绿假成功 52/87 = **59.8%**，比主批次 23/87 = 26.4% 更高。这印证
BASELINE.yaml T5 段（2026-10-11）的判断：**−28pp 的真实主机制是"测试生成侧
不产红"（首轮全绿），而非过红/抹红通道**。双门（特异性门 + 红回归门）只针对
"首轮红之后"的通道，对 59.8% 的"首轮全绿"无从介入——是"对症不对根"。

## 4. 结论

1. **双门不能消除 −28pp，且小幅恶化**：detection 14.81% → 9.20%（配对净 −4）。
   特异性门拦截过红（37→17）有效，但 regenerate 产物是"全绿假成功"而非检出，
   并把 8 个原本检出的任务误抹成全绿。
2. **红回归门从未触发**（87/87 None），抹红通道未得到对症处理。
3. **根本瓶颈确认**：全绿假成功占 59.8%，双门是"对症不对根"——与 D1（QuixBugs
   协议增益不可复现）及评审 v2 F7/F8 一致：**协议层加法不是解决 −28pp 的路径**。

**EMSE 叙事价值**：这是一项可发表的**阴性结果**（符合 Negative Results 征稿），
把"双门"这一协议层机制在真实（合成）基准上的无效性做了**机制级归因**：双门
解决的"过红/抹红"不是主机制，主机制是"测试生成侧不产红"，需从**生成器侧**
（规格优先 / 变异反馈 / 生成器能力）而非**协议侧**（双门路由）入手。

## 5. 复现

```bash
# 配对对比（零 LLM）
.venv/bin/python experiments/emse_t08_gates_recompute.py \
  --main experiments/results/main_batch/benchmark_synthetic_20261006_*.json \
  --t08 experiments/results/emse_t08_gates_20261013/*.json
```
