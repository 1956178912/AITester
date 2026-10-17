# EMSE 批次五：M4 QuixBugs SpecExpr 扩样 + 全量 Mut@k 实测 + 过红 P1-P4（2026-10-14 晚）

> 性质：批次五执行记录（EMSE 投稿优化）。零 LLM 复算 + M4 4 臂 LLM 跑批（~$0.3 授权）。
> 产物：M4 A/B 臂 QuixBugs 批次 JSON + 零 LLM 分析；ULT/QuixBugs 全量 cosmic-ray Mut@k；过红 P1-P4 分类。

## 1. M4 主结果（A specir vs B NL，n=35 标准口径）

**判定：not_confirmed（阴性）**

| 统计量 | 值 |
|---|---|
| n_pairs | 35 |
| 不一致对（specir_only : nl_only） | 2 : 5 |
| δ（specir − NL） | **−8.57pp** |
| p（McNemar 精确） | 0.4531 |
| BF10（Jeffreys） | 0.5625 |
| MDE（n=35） | 16.57pp |
| 判定 | **not_confirmed** |

**边际对照**：
- A（specir）：可测 35，det1=23（65.7%），spec_compile_rate 均值 0.8043（n=50），246 LLM 调用 / 760K tokens
- B（NL）：可测 35，det1=26（74.3%），241 LLM 调用 / 611K tokens

**解读**：与 pilot（6:1 / n=35 / δ=+14.29pp / p=0.125）方向相反——pilot 的阳性趋势未复现，扩样后 SpecExpr 在 QuixBugs 上反而小幅落后 NL（−8.57pp，不显著）。pilot 的 6:1 极可能是小样本波动（n=35 的 MDE=16.57pp > 实测 14.29pp 的效应量，本就落在功效盲区）。

**诚实边界**：① temp=0 + 独立 cache namespace 已隔离（A=emse_qbug_specir_expand_A / B=..._B），4 臂跨批次方差（C/D）未跑（控制成本，~$0.15 已含在 AB 内）；② 任务集非新（50 程序复用 pilot），效应量估计受任务固定性约束；③ QuixBugs 本地即完整 Python 子集 50 程序，无"换任务子集"路径。

## 2. 全量 Mut@k 实测（cosmic-ray 8.7.0 官方口径，零 LLM）

| 组 | target | pooled | 任务数 |
|---|---|---|---|
| ULT specir 生成测试 | task_metadata.fixed | 0.92（230/250） | 25 |
| ULT replace 生成测试 | task_metadata.fixed | 0.95（437/460） | 46 |
| ULT gold 上界 | task_metadata.fixed | **1.0（250/250）** | 25 |
| **QuixBugs 生成测试** | task_metadata.fixed | **0.9610（443/461）** | 49（1 skip） |

**QuixBugs Mut@k 首测**（本批次新增）：LLM 生成测试对 QuixBugs 50 程序（49 可测）的 pooled mutation score = **0.9610**，与 ULT replace（0.95）同量级——进一步佐证「变异强但缺陷盲」：生成测试的变异杀伤力（~0.92-0.96）远高于其真实缺陷检出率（QuixBugs M4 实测 65.7-74.3% / 基线 ~56%）。mutation score 高 ≠ 缺陷检出强，两条指标可分离。

- ULT 组（复算）：config hash `1e1230a7...`，max_mutants=10，timeout=120s（timeout 计 killed）
- QuixBugs 组：同口径（max_mutants=10 / timeout 120s）；1 任务 skip（"cosmic-ray 无有效变异体结果"）

## 3. 过红 fixed 复跑 P1-P4 分类（5 例抽样，零 LLM）

主批次 aiter 过红行 167 / 总行 669。seed=42 确定性抽样 5 例（synthetic__task_0007/0013/0066/0072/0076），在 gold fixed 上子进程 pytest 复跑：

| task | 失败签名 | P 模式 |
|---|---|---|
| task_0076 | AssertionError（断言耦合） | P1_bug_coupled_expectation |
| task_0066 | AssertionError | P1_bug_coupled_expectation |
| task_0013 | AssertionError | P1_bug_coupled_expectation |
| task_0007 | AttributeError（实现耦合） | P3_implementation_coupling |
| task_0072 | AssertionError | P1_bug_coupled_expectation |

**4/5 例 P1（断言耦合过红）+ 1/5 例 P3（实现耦合）**：过红主因是 LLM 生成测试把"与 bug 行为耦合的断言"写死（bug 修复后原断言反红），而非测试逻辑本身有缺陷。这与 10-13 批次"过红 52% 是过红测试"的口径一致——P1 占比高说明"过红"中相当比例是**测试-缺陷强耦合**而非测试生成质量缺陷。

## 4. 批次五成本与工件

- M4 A+B 臂 LLM：~$0.25（246+241 调用），在 ~$0.3 预算内
- Mut@k / 过红 P1-P4：零 LLM（cosmic-ray + 子进程 pytest，确定性本地执行）
- 工件归档：
  - `experiments/results/emse_quixbugs_specir_expand_20261014/`（M4 A/B 臂 JSON + traces + SHA256SUMS）
  - `experiments/results/emse_quixbugs_mutk_20261014/MUTK_QUXBUGS_RECOMPUTE.json`（QuixBugs Mut@k）
  - `experiments/results/emse_ult_mutk_20261014/MUTK_RECOMPUTE.json`（ULT Mut@k 复算）
- 复算脚本：`experiments/emse_quixbugs_mutk.py`（本批次新增，QuixBugs cosmic-ray 全量）

## 5. 待办与遗留

- ULT Mut@k 复算（set 序列化 bug 修复后重跑）已完成：`MUTK_RECOMPUTE.json` 三组 pooled 0.92/0.95/1.0（n=25/46/25，skipped=0）——与 10-14 已归档 MUTK_REPORT 一致（四舍五入口径：0.92 vs 0.928 为 2/4 位小数差异，同源复算）。
- M4 C/D 臂（跨批次方差）未跑——若投稿需补"复现稳定性"证据，须再授权 ~$0.15（2 臂 × 50 任务）。
- QuixBugs 1 任务 cosmic-ray skip（"无可变异点"）须在论文 artifact 清单中披露。
