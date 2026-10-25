# 统计报告规范补强（Wilson CI / 效应量 / 成本 bootstrap）

- 口径：Wilson CI / Cohen's g / OR / 配对 bootstrap（第十九轮评审 A-15）
- bootstrap：n=10000，seed=42（逐位可复现）
- 输入：R-P0-2 三种子（261 任务/臂口径）+ E6 对照 + E4 QuixBugs 修正结算（零 LLM 重算）
- 工件沿革：AZ 轮（2026-10-21）重发，修正 Cohen's g 尺度与精确二项尾的
  epsilon 放大；`emse_stats_extensions_20261016/` 保留为历史值（不重写）。

## 1. 各臂点估计 + Wilson 95% CI

| 臂 | 指标 | k/n | 点估计 | Wilson 95% CI |
|---|---|---|---|---|
| rp02_aitester | detection | 0/20 | 0.00% | [0.00%, 16.11%] |
| rp02_plain_llm | detection | 1/20 | 5.00% | [0.89%, 23.61%] |
| rp02_single_agent | detection | 3/20 | 15.00% | [5.24%, 36.04%] |
| e4_aitester | detection | 21/35 | 60.00% | [43.57%, 74.45%] |
| e4_aitester | repair | 2/20 | 10.00% | [2.79%, 30.10%] |
| e4_plain_llm_df | detection | 29/36 | 80.56% | [64.97%, 90.25%] |
| e4_plain_llm_df | repair | 0/41 | 0.00% | [0.00%, 8.57%] |
| e6_aitester | detection | 20/35 | 57.14% | [40.86%, 72.02%] |
| e6_plain_llm | detection | 26/36 | 72.22% | [56.01%, 84.15%] |
| e6_single_agent | detection | 29/36 | 80.56% | [64.97%, 90.25%] |

## 2. 配对对比（McNemar 精确检验 + Cohen's g + OR + bootstrap diff CI）

| 对比 | n10(a only) | n01(b only) | rate_a | rate_b | Cohen's g | OR [95% CI] | 精确 p | bootstrap Δ [95% CI] |
|---|---|---|---|---|---|---|---|---|
| rp02_aitester_vs_df | 2 | 9 | 60.00% | 80.00% | 0.318 | 0.263 [0.065, 1.060] | 0.06543 | [-37.14pp, -2.86pp] |
| rp02_df_vs_plain_llm | 3 | 8 | 57.14% | 71.43% | 0.227 | 0.412 [0.119, 1.430] | 0.2266 | [-31.43pp, +2.86pp] |
| e4_aitester_vs_df | 2 | 9 | 60.00% | 80.00% | 0.318 | 0.263 [0.065, 1.060] | 0.06543 | [-37.14pp, -2.86pp] |

## 3. 成本（token/task + $/task 点估计 + bootstrap CI）

| 臂 | tokens/task | tokens/task 95% CI | $/task | 换算假设 |
|---|---|---|---|---|
| rp02_aitester | 3231 | [3021, 3430] | $0.0022 | 价目加权（in:out=38014:26604）；未计价模型：无；缓存口径：命中 0 次、避免 0 tokens（20/20 行带缓存字段；真实 API 消耗不含避免 token，$/task 仍为真实花费口径） |
| rp02_plain_llm | 1065 | [972, 1174] | $0.0009 | 价目加权（in:out=8969:12333）；未计价模型：无；缓存口径：命中 0 次、避免 0 tokens（20/20 行带缓存字段；真实 API 消耗不含避免 token，$/task 仍为真实花费口径） |
| rp02_single_agent | 1292 | [1116, 1505] | $0.0010 | 价目加权（in:out=12289:13549）；未计价模型：无；缓存口径：命中 0 次、避免 0 tokens（20/20 行带缓存字段；真实 API 消耗不含避免 token，$/task 仍为真实花费口径） |

## 4. 口径纪律

- Wilson CI 为 Wilson score 区间（小样本稳健）；不与 naive 正态近似混用；
- 精确 p 为 p=0.5 的对称双尾二项尾（整数权重比较，无 1e-12 epsilon 容差）；
- Cohen's g = |n10-n01| / (2*(n10+n01))（effectsize 口径，范围 0–0.5），
  仅用 McNemar 不一致对，与 OR 互为方向/强度表述；
- bootstrap 为任务级重抽样（配对结构保持），种子 42，10k 次；
- 表中 rate_a / rate_b 为**配对子集**口径（denominator = n_paired），与第 1 节
  全分母口径（如 df 44.83% @261）可能不同，引用时须区分；
- n01=0 时 OR 经 Haldane-Anscombe +0.5 修正，CI 上界极大属正确行为
  （零不一致对 = 点估计无穷方向的保守截断），不得解读为「效应不显著」；
- tokens/task 仅在每行 token_usage 为对象、三个计数字段均为非负整数时给出读数；
  形状/缺席/类型/负数/非有限、无任务分母一律记「—（无 token 读数）」并点名机制；
- $/task 另要求行级 in+out = total_tokens 且 by_model 合计 = total_tokens；
  未登记、无归因、归因不闭合、token 读数问题一律记「—（无金额）」并在 note 点名机制；
- $/task 换算假设见各行 note（价目表官方登记口径，峰时全价保守上界）；
- 本工件所有数字可由 `python -m experiments.emse_stats_extensions` 零 LLM 逐位复算。
