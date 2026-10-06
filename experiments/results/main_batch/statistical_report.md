# 统计显著性检验报告

## 数据来源

R2 审计：本报告实际纳入 3 个批次文件（--batches 白名单模式）：

- `benchmark_synthetic_20261006_164357.json`
- `benchmark_synthetic_20261006_151907.json`
- `benchmark_synthetic_20261006_140906.json`

复算命令（工件与代码齐备时数值逐位可复现）：`python experiments/statistical_analysis.py --results-dir experiments/results/main_batch --output <report.md> --batches benchmark_synthetic_20261006_164357.json,benchmark_synthetic_20261006_151907.json,benchmark_synthetic_20261006_140906.json --pool-seeds`

去重口径：同一 task_id 跨批次重复时最新批次优先（排序主键 = 批次
文件名内嵌时间戳降序，文件系统 mtime 仅作无内嵌时间戳批次的兜底）。

AB4 多种子拼接口径（--pool-seeds）：行 task_id 已按批次
provenance.seed 加 `s<seed>__` 前缀——多种子批次（task_id 跨种子
同名是中性化命名的设计使然）按种子分层全量进入配对检验；同种子
重复跑仍按上述去重口径折叠（重跑协议语义保留）。

## 数据概览

| Baseline | 任务数 | 通过数 (passed) | 通过率 | detection 可测数 | detection 率 | repair 可测数 | repair 率 |
|----------|--------|-----------------|--------|------------------|--------------|---------------|-----------|
| aitester | 261 | 143 | 54.8% | 240 | 15.8% | 240 | 0.0% |
| plain_llm | 261 | 229 | 87.7% | 261 | 1.5% | 261 | 0.0% |
| single_agent | 0 | 0 | 0.0% | 0 | 0.0% | 0 | 0.0% |
| plain_llm_df | 261 | 7 | 2.7% | 261 | 44.8% | 261 | 0.0% |

## 诚实指标 McNemar 检验（M1 三指标，gold 独立裁决）

2026-10-05 P0 协议：passed = 系统自产测试在（未修复的）缺陷代码上
通过，为自指指标（奖励写不出能抓 bug 的测试）；detection / repair
由留出 gold 材料独立裁决。**本节为报告的首要结论口径**——与
下方 passed 系列检验并列呈现，解读冲突时以本节为准。

| 指标 | 比较 | 共同任务数 | 不一致对 | χ²（连续性校正） | p值 | 显著性 |
|------|------|-----------|---------|------------------|-----|--------|
| detection（F2P 检出） | AITester vs plain_llm | 240 | 40 | 27.2250 | 0.0000 | *** |
| detection（F2P 检出） | AITester vs plain_llm_df | 240 | 92 | 48.7935 | 0.0000 | *** |
| repair（gold 裁决修复） | AITester vs plain_llm | 240 | 0 | 0.0000 | 1.0000 | n.s. |
| repair（gold 裁决修复） | AITester vs plain_llm_df | 240 | 0 | 0.0000 | 1.0000 | n.s. |

## 配对t检验结果

| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |
|------|--------|---------|-----|--------|-----------|--------|
| AITester vs plain_llm | 261 | -8.7759 | 0.0000 | *** | -0.5432 | medium |
| AITester vs plain_llm_df | 261 | 15.4555 | 0.0000 | *** | 0.9567 | large |

## McNemar 配对检验（passed，自指指标——仅作诊断参考）

R14 协议：二值配对数据（passed 0/1）的检验（Arcuri & Briand,
ICSE 2011）。注意：passed 为系统自产测试在（未修复的）缺陷代码
上的通过（自指口径，false_fix 主批次 89.8% 的直接来源），本节
不作为架构增益主张的依据；与上方 t 检验并列呈现，t 检验表保持
历史口径不变。

| 比较 | 共同任务数 | 不一致对 (n01+n10) | χ²（连续性校正） | p值 | 显著性 |
|------|-----------|-------------------|------------------|-----|--------|
| AITester vs plain_llm | 261 | 124 | 58.2661 | 0.0000 | *** |
| AITester vs plain_llm_df | 261 | 148 | 123.1419 | 0.0000 | *** |

## 多重比较校正（BH-FDR）

对上表各 McNemar p 值做 Benjamini-Hochberg FDR 校正（α=0.05）；
q 为校正后 p 值，拒绝 H0 表示校正后仍显著。

| 比较 | 原始 p（McNemar） | BH-FDR q | 拒绝 H0 |
|------|-------------------|----------|---------|
| AITester vs plain_llm | 0.0000 | 0.0000 | 是 |
| AITester vs plain_llm_df | 0.0000 | 0.0000 | 是 |

## Bootstrap 95% 置信区间

R2 协议：配对差值均值（AITester − 基线，逐任务 0/1 差）的有放回
重采样百分位法 95% CI（默认 10000 次，random.Random(seed=42) 固定，
结果逐位可复现）。CI 不含 0 即方向稳健。

| 比较 | 配对数 | 差值均值 | 95% CI 下界 | 95% CI 上界 | 重采样次数 | seed |
|------|--------|---------|------------|------------|-----------|------|
| AITester vs plain_llm | 261 | -0.3295 | -0.4023 | -0.2567 | 10000 | 42 |
| AITester vs plain_llm_df | 261 | 0.5211 | 0.4559 | 0.5862 | 10000 | 42 |

## 效应量对比（Cohen's d 与 Cliff's δ）

R2 协议：Cliff's δ = (n⁺ − n⁻)/n_pairs（配对差值符号版，非参数）；
阈值 |δ|：0.147 / 0.33 / 0.474（Romano et al. 2006）。

| 比较 | Cohen's d | 效应量 | Cliff's δ | 效应量 |
|------|-----------|--------|-----------|--------|
| AITester vs plain_llm | -0.5432 | medium | -0.3295 | small |
| AITester vs plain_llm_df | 0.9567 | large | 0.5211 | large |

## 贝叶斯配对分析（Z9，Dirichlet 后验——与 NHST 并列）

Z9 协议：配对二值列联表 (n11, n01, n10, n00) 上取均匀先验的
Dirichlet 后验，报告边际差 δ = p(AITester) − p(基线) 的后验均值、
95% 可信区间、P(δ>0) 与 ROPE 概率（|δ| ≤ 0.05 视为实践等价）。
Monte Carlo 20000 次、random.Random(seed=42)（纯 stdlib，逐位可复现）。
结论标签：bayes_pos / bayes_neg（方向稳健）、bayes_equiv（实践等价）、
bayes_inconclusive（证据不足——小样本最常见结局，诚实标注而非
强行二分）。方法学依据：Furia et al., TSE 2019（arXiv:1811.05422）。

### 诚实指标（首要结论口径）

| 指标 | 比较 | δ 后验均值 | 95% CI | P(δ>0) | P(ROPE) | 结论 |
|------|------|-----------|--------|--------|---------|------|
| detection（F2P 检出） | AITester vs plain_llm | 0.1393 | [0.0917, 0.1904] | 1.0000 | 0.0002 | bayes_pos |
| detection（F2P 检出） | AITester vs plain_llm_df | -0.2787 | [-0.3480, -0.2087] | 0.0000 | 0.0000 | bayes_neg |
| repair（gold 裁决修复） | AITester vs plain_llm | 0.0000 | [-0.0122, 0.0125] | 0.5003 | 1.0000 | bayes_equiv |
| repair（gold 裁决修复） | AITester vs plain_llm_df | 0.0000 | [-0.0122, 0.0125] | 0.5003 | 1.0000 | bayes_equiv |

### passed（自指指标，仅作诊断参考）

| 比较 | δ 后验均值 | 95% CI | P(δ>0) | P(ROPE) | 结论 |
|------|-----------|--------|--------|---------|------|
| AITester vs plain_llm | -0.3245 | [-0.3962, -0.2518] | 0.0000 | 0.0000 | bayes_neg |
| AITester vs plain_llm_df | 0.5132 | [0.4464, 0.5784] | 1.0000 | 0.0000 | bayes_pos |

## 显著性标记说明

- `***` p < 0.001
- `**` p < 0.01
- `*` p < 0.05
- `n.s.` p ≥ 0.05 (不显著)

## 效应量解释

- Cohen's d（配对差值口径）：
  - `negligible`: |d| < 0.2
  - `small`: 0.2 ≤ |d| < 0.5
  - `medium`: 0.5 ≤ |d| < 0.8
  - `large`: |d| ≥ 0.8
- Cliff's δ（R2，非参数，Romano et al. 2006）：
  - `negligible`: |δ| < 0.147
  - `small`: 0.147 ≤ |δ| < 0.33
  - `medium`: 0.33 ≤ |δ| < 0.474
  - `large`: |δ| ≥ 0.474

---
*报告生成时间: 2026-10-06 18:06:26*
