# E8 任务 ID 逐项对照（2026-11-01，零 LLM）

> 目的（checkpoint 遗留项）：E8-legacy-on 与 R-P0-2 原批的任务 ID 逐项对照，
> 完成 E8 漂移归因的最后一块实证（此前 2026-10-29 只做了 15 任务抽样哈希对照）。

## 对照两侧

| 侧 | 来源 | 任务数 |
|---|---|---|
| R-P0-2 原批（seed42） | `main_batch/benchmark_synthetic_20261006_140906.json` @ git 历史 `f61d26bf`（工作树已删，从 git 恢复解析） | 87 |
| E8 legacy-on（seed42） | `e8_2x2_20261028/legacy-on/seed42/benchmark_synthetic_20261029_002927.json` | 87 |

## 结果（哈希基 = sha256(pattern_name + fixed + test_cases)[:16]）

- **task_id 集合：87/87 完全一致**（两侧同 ID 集）。
- **内容哈希：30/87 相同（34.5%）、57/87 不同（65.5%）**——同 ID 不同题大面积存在。
  （2026-10-29 抽样口径 3/15 = 20%；全量口径 34.5%，结论同向且更强。）

### 漂移维度分解（87 任务）

| 分解 | 任务数 | 说明 |
|---|---|---|
| 四维全同（pattern/fixed/tests/noise_seed） | 21 | 完全一致 |
| 仅 noise_seed 不同（三元组同） | 9 | 内容实质相同 |
| pattern+fixed+tests 变、noise_seed 同 | 14 | 实质漂移 |
| 四维全变 | 29 | 实质漂移 |
| pattern+tests 变、fixed 同 | 3 | 实质漂移 |
| pattern+tests+noise_seed 变、fixed 同 | 11 | 实质漂移 |
| **实质漂移小计（三元组变）** | **57** | |

## 判定与影响

1. **任务发生器非确定性实证升级为全量口径**：同切点（b533cff1）、同 seed（42）、
   同 ID 集下 57/87 任务内容不同——"同任务集口径"假设在 E8↔R-P0-2 之间不成立
   （10-29 抽样结论的全量确认）。
2. **E8 漂移归因终版：双因素已观测**——
   - 任务集漂移：本对照 57/87（65.5%）；
   - 模型快照漂移：`b2_fingerprint_20261029_r2/FINGERPRINT_COMPARISON.md`
     （10-24→10-28 窗口同探针指纹 e72d3c7f→bc19ba97 实锤）。
   - "legacy-on df 6.9% vs R-P0-2 59.58%" 的复现失败**不得单因归模型侧**；
     harness 侧任务发生器漂移是已观测的并列因素。
3. 机器可读：`TASK_ID_COMPARISON.json`（87 行逐任务对照）。

## 复算

```bash
# R-P0-2 侧从 git 历史恢复（勿写入工作树）
git show f61d26bf:experiments/results/main_batch/benchmark_synthetic_20261006_140906.json > /tmp/rp02.json
# 对照脚本逻辑见 TASK_ID_COMPARISON.json 的 hash_basis 与 rows（本文件由同一脚本产出）
```
