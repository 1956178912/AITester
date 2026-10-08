# repair 口径矩阵（R13，2026-10-08 R2）

> 目的：终结"四个 repair 数字分母混杂"的口径危机（R2 §4/§6.4）。**在建立本表之前，
> 任何对外引用 repair 数字都有被审稿人一枪命中的风险**——16% / 35.86% / 48.11% /
> 90.2% 的分母、oracle、臂、数据集均不同。本表逐行给出**分子 / 分母定义 / oracle /
> 数据集 / 臂 / 种子 / 开关 / 工件路径 / 可复算命令**，并标注跨文件测量修复（R27）
> 后的 v2 修正值。

## 1. 口径矩阵

| # | 数字 | 分子/分母 | 分母定义 | oracle | 数据集 | 臂 | 种子 | 关键开关 | 工件路径 | 可复算命令 |
|---|------|-----------|----------|--------|--------|----|------|----------|----------|-----------|
| ① | **16.0%（8/50）** | 8/50 | all-task（n=50，无 gold 材料行仍计 0） | gold 独立裁决（gold 测试在补丁后代码全过） | synthetic | aitester（EDIT_INTENT_ENABLE=true） | 42 | logic 档；`LOCALIZED_EDIT_ENABLE` ∈ {false(A), true(B)} | `experiments/results/r4_batches/r4_ab_arm_a\|b` | `make repair-replay` 变体 / `.venv/bin/python -m experiments.repair_replay experiments/results/r4_batches/r4_ab_arm_a --arm aitester` |
| ② | **35.86%（52/145）** | 52/145 | 修正口径**可重放**行（patch 非空 ∧ gold 材料齐备） | gold 独立裁决（normalize 清理后） | synthetic | aitester | {42,43,44} pooled | 双门开 | `experiments/results/main_batch/benchmark_synthetic_2026100{6_140906,6_151907,6_164357}.json` | `make corrected-metrics`（ADR-0027 报告） |
| ③ | **48.11%（51/106）** | 51/106 | 修正口径可重放行 | 同上 | synthetic | aitester | {42,44} | logic 档双门开 | `.../main_batch/benchmark_synthetic_20261007_18{1638,5941}.json`（+E1 批） | `make corrected-metrics`（ADR-0027 报告） |
| ④ | **90.2%（37/41）** / **87.8%（36/41）** | 37/41、36/41 | **M1 可测口径**（有官方 gold 测试的 41 行；9 行无官方测试不进分母） | QuixBugs 官方 gold 测试（包结构物化后） | QuixBugs（n=50，41 可测） | aitester（A 对照 / B 行级约束） | 42 | logic 档；B 臂 `LOCALIZED_EDIT_ENABLE=true` | `experiments/results/r4_batches/r4_qb_arm_a\|b` | `.venv/bin/python /tmp/wb_verify_qb_recompute.py`（只读重放，见 §3） |
| ④' | 74% / 72%（37/50、36/50） | 37/50、36/50 | all-task（无 gold 材料行计入分母）——**仅作保守展示** | 同上 | 同上 | 同上 | 同上 | 同上 | 同上 | 同上 |
| ⑤ **v2：39.31%（57/145）** | 57/145 | 修正口径可重放行（含 R27 跨文件物化） | gold 独立裁决 | synthetic | aitester | {42,43,44} | 双门开 | 同 ②§ | 同 ② | `make corrected-metrics` → `experiments/results/main_batch/corrected_report_v2.md` |
| ⑥ **v2：54.72%（58/106）** | 58/106 | 修正口径可重放行（含 R27 跨文件物化） | gold 独立裁决 | synthetic | aitester | {42,44} | logic 档双门开 | 同 ③ | 同 ③ | 同 ⑤ |
| ⑦ **v2：55.6%（10/18）** | 10/18 | 修正口径可重放行（含 R27 跨文件物化） | gold 独立裁决 | synthetic | aitester | 42 | logic 档 EDIT_INTENT（A 臂） | `experiments/results/r4_batches/r4_ab_arm_a` | `experiments/results/r4_batches/replay_r4_ab_arm_a_v2.md` |
| ⑧ v2：90.2%/87.8% | 37/41、36/41 | M1 可测口径 | QuixBugs 官方测试 | QuixBugs | aitester A/B | 42 | 同 ④ | 同 ④ | **逐位不变**（R27 不影响 QuixBugs 子串分派路径） |

**读法**：① 与 ④ 是"all-task vs M1 可测"两口径，②③⑤⑥⑦ 是"修正口径（可重放行）"，
④ 与项目记忆中"74%/72%"是同一批数据的 all-task 口径（保守展示）。**不同口径之间的
数字不可直接相减/比较**。

## 2. R27 跨文件测量修复的 v2 增量（受影响的六个批次）

第三起测量伪影（跨文件任务 gold 测试 import `module_a/b/c` 未物化 → rc=2）使
**六个批次**的跨文件行 repair 系统性 0。R27 修复后重放，跨文件行由恒 0 变为可测：

| 批次 | 跨文件行（带补丁） | v1 correct | v2 correct | 非跨文件行（带补丁） | v2 correct |
|------|-------------------|-----------|-----------|---------------------|-----------|
| R4-A（`r4_ab_arm_a`） | 2 | 0 | **2** | 16 | 8 |
| E2 seed42（`..._181638`） | 2 | 0 | **2** | 25 | 13 |
| E2 seed44（`..._185941`） | 2 | 0 | **2** | 24 | 12 |
| R-P0-2 种子 a（`..._140906`） | 6 | 0 | **2** | 48 | 18 |
| R-P0-2 种子 b（`..._151907`） | 5 | 0 | **2** | 41 | 18 |
| R-P0-2 种子 c（`..._164357`） | 8 | 0 | **1** | 37 | 16 |
| **合计** | **25** | **0** | **11** | **191** | **85** |

- R-P0-2（三种子 pooled）修正 repair：**35.86%（52/145）→ 39.31%（57/145）**；
- E1/E2（logic 档）修正 repair：**48.11%（51/106）→ 54.72%（58/106）**；
- R4-A 修正 repair（可重放 18 行）：44.4%（8/18）→ **55.6%（10/18）**；
- QuixBugs（④/⑧）：**逐位不变**（R27 显式分派不影响 QuixBugs 子串回退路径）。

> 观察：跨文件行修复并非"全部可判 1.0"（25 行中 11 行 correct）——说明跨文件任务
> 本身更难（补丁难通过 gold 的跨模块断言），伪影只是**擦除了本可测信号**。

## 3. 引用纪律（强制）

1. **对外（论文/README/报告/CHANGELOG）引用 repair 数字时必须注明口径编号**（本表 §1 的
   ①–⑧），或至少同时给出"分子/分母 + oracle + 数据集 + 臂"。
2. **禁止**把 all-task 口径与 M1 可测口径混用（如"37/50=74%"与"37/41=90.2%"不得互换陈述）。
3. **禁止**引用未修正口径的旧数字（16.0% pooled R-P0-2 等的**跨文件零行**已知为伪影）——
   须引用 v2 修正值（⑤⑥⑦⑧）或明确标注为"修正前下界"。
4. 新增 repair 数字须在本表新增一行（schema 见 §1 表头），否则不得进入对外材料。

## 4. 可复算工件与命令（零 LLM）

```bash
# v2 修正口径总报告（main_batch aitester，含跨文件物化）
make corrected-metrics   # 或：
.venv/bin/python -m experiments.corrected_metrics experiments/results/main_batch \
  --arm aitester --out experiments/results/main_batch/corrected_report_v2.md

# R4-A 重放（可重放行 + 原口径对照）
.venv/bin/python -m experiments.repair_replay \
  experiments/results/r4_batches/r4_ab_arm_a --arm aitester

# QuixBugs 两臂独立重放（包结构口径；③ 只读参考脚本）
.venv/bin/python /tmp/wb_verify_qb_recompute.py
```

## 5. 关联工件

- ADR-0021（围栏伪影）、ADR-0027（修正口径重估）、**ADR-0029（跨文件未物化伪影 + 包结构 import 伪影）**；
- `experiments/results/main_batch/corrected_report_v2.md`、`experiments/results/r4_batches/README.md`；
- 预注册执行记录（`docs/preregistration.md`）与 `docs/design/r4_localized_edit_ab.md` 勘误块。
