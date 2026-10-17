# 统计报告规范补强（Wilson CI / 效应量 / 成本 bootstrap）

- 口径：Wilson CI / Cohen's g / OR / 配对 bootstrap（第十九轮评审 A-15）
- bootstrap：n=10000，seed=42（逐位可复现）
- 输入：R-P0-2 三种子（261 任务/臂口径）+ E6 对照 + E4 QuixBugs 修正结算（零 LLM 重算）

## 1. 各臂点估计 + Wilson 95% CI

| 臂 | 指标 | k/n | 点估计 | Wilson 95% CI |
|---|---|---|---|---|
| rp02_aitester | detection | 38/240 | 15.83% | [11.76%, 20.99%] |
| rp02_plain_llm | detection | 4/261 | 1.53% | [0.60%, 3.87%] |
| rp02_plain_llm_df | detection | 117/261 | 44.83% | [38.91%, 50.89%] |
| e4_aitester | detection | 17/37 | 45.95% | [31.04%, 61.62%] |
| e4_aitester | repair | 37/40 | 92.50% | [80.14%, 97.42%] |
| e4_plain_llm_df | detection | 31/37 | 83.78% | [68.86%, 92.35%] |
| e4_plain_llm_df | repair | 0/41 | 0.00% | [0.00%, 8.57%] |
| e6_aitester | detection | 8/87 | 9.20% | [4.73%, 17.11%] |
| e6_plain_llm | detection | 0/87 | 0.00% | [0.00%, 4.23%] |
| e6_plain_llm_df | detection | 30/87 | 34.48% | [25.34%, 44.94%] |

## 2. 配对对比（McNemar 精确检验 + Cohen's g + OR + bootstrap diff CI）

| 对比 | n10(a only) | n01(b only) | rate_a | rate_b | Cohen's g | OR [95% CI] | 精确 p | bootstrap Δ [95% CI] |
|---|---|---|---|---|---|---|---|---|
| rp02_aitester_vs_df | 12 | 80 | 15.83% | 44.17% | 0.739 | 0.155 [0.086, 0.282] | 1.073e-12 | [-35.00pp, -21.25pp] |
| rp02_df_vs_plain_llm | 113 | 0 | 44.83% | 1.53% | 1.000 | 227.000 [14.112, 3651.365] | 1.931e-12 | [+37.55pp, +49.04pp] |
| e6_aitester_vs_df | 2 | 24 | 9.20% | 34.48% | 0.846 | 0.102 [0.028, 0.375] | 1.049e-05 | [-35.63pp, -16.09pp] |
| e4_aitester_vs_df | 0 | 14 | 45.95% | 83.78% | 1.000 | 0.034 [0.002, 0.578] | 0.0001221 | [-54.05pp, -21.62pp] |

## 3. 成本（token/task + $/task 点估计 + bootstrap CI）

| 臂 | tokens/task | tokens/task 95% CI | $/task | 换算假设 |
|---|---|---|---|---|
| rp02_aitester | 26115 | [24226, 28086] | $0.0259 | 价目加权（in:out=1581326:5234651）；未计价模型：无 |
| rp02_plain_llm | 3209 | [2964, 3474] | $0.0034 | 价目加权（in:out=142783:694881）；未计价模型：无 |
| rp02_plain_llm_df | 4223 | [3823, 4643] | $0.0045 | 价目加权（in:out=152103:950127）；未计价模型：无 |

## 4. 口径纪律

- Wilson CI 为 Wilson score 区间（小样本稳健）；不与 naive 正态近似混用；
- Cohen's g 仅用 McNemar 不一致对（b/c），与 OR 互为方向/强度表述；
- bootstrap 为任务级重抽样（配对结构保持），种子 42，10k 次；
- 表中 rate_a / rate_b 为**配对子集**口径（denominator = n_paired），与第 1 节
  全分母口径（如 df 44.83% @261）可能不同，引用时须区分；
- n01=0 时 OR 经 Haldane-Anscombe +0.5 修正，CI 上界极大属正确行为
  （零不一致对 = 点估计无穷方向的保守截断），不得解读为「效应不显著」；
- $/task 换算假设见各行 note（价目表官方登记口径，峰时全价保守上界）；
- 本工件所有数字可由 `python -m experiments.emse_stats_extensions` 零 LLM 逐位复算。
