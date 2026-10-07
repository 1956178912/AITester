# 统计显著性检验报告

## 数据来源

R2 审计：本报告实际纳入 2 个批次文件（--batches 白名单模式）：

- `main_batch/benchmark_synthetic_20261007_185941.json`
- `main_batch/benchmark_synthetic_20261007_181638.json`

复算命令（工件与代码齐备时数值逐位可复现）：`python experiments/statistical_analysis.py --results-dir experiments/results --output <report.md> --batches main_batch/benchmark_synthetic_20261007_185941.json,main_batch/benchmark_synthetic_20261007_181638.json --pool-seeds`

去重口径：同一 task_id 跨批次重复时最新批次优先（排序主键 = 批次
文件名内嵌时间戳降序，文件系统 mtime 仅作无内嵌时间戳批次的兜底）。

AB4 多种子拼接口径（--pool-seeds）：行 task_id 已按批次
provenance.seed 加 `s<seed>__` 前缀——多种子批次（task_id 跨种子
同名是中性化命名的设计使然）按种子分层全量进入配对检验；同种子
重复跑仍按上述去重口径折叠（重跑协议语义保留）。

## 数据概览

| Baseline | 任务数 | 通过数 (passed) | 通过率 | detection 可测数 | detection 率 | repair 可测数 | repair 率 |
|----------|--------|-----------------|--------|------------------|--------------|---------------|-----------|
| aitester | 174 | 122 | 70.1% | 158 | 12.7% | 158 | 0.0% |
| plain_llm | 174 | 153 | 87.9% | 174 | 1.7% | 174 | 0.0% |
| single_agent | 0 | 0 | 0.0% | 0 | 0.0% | 0 | 0.0% |
| plain_llm_df | 174 | 4 | 2.3% | 155 | 52.3% | 155 | 0.0% |

## 诚实指标 McNemar 检验（M1 三指标，gold 独立裁决）

2026-10-05 P0 协议：passed = 系统自产测试在（未修复的）缺陷代码上
通过，为自指指标（奖励写不出能抓 bug 的测试）；detection / repair
由留出 gold 材料独立裁决。**本节为报告的首要结论口径**——与
下方 passed 系列检验并列呈现，解读冲突时以本节为准。

| 指标 | 比较 | 共同任务数 | 不一致对 | χ²（连续性校正） | p值 | 显著性 |
|------|------|-----------|---------|------------------|-----|--------|
| detection（F2P 检出） | AITester vs plain_llm | 158 | 21 | 12.1905 | 0.0005 | *** |
| detection（F2P 检出） | AITester vs plain_llm_df | 143 | 62 | 45.3065 | 0.0000 | *** |
| repair（gold 裁决修复） | AITester vs plain_llm | 158 | 0 | 0.0000 | 1.0000 | n.s. |
| repair（gold 裁决修复） | AITester vs plain_llm_df | 143 | 0 | 0.0000 | 1.0000 | n.s. |

## 配对t检验结果

| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |
|------|--------|---------|-----|--------|-----------|--------|
| AITester vs plain_llm | 174 | -4.4861 | 0.0000 | *** | -0.3401 | small |
| AITester vs plain_llm_df | 174 | 18.6091 | 0.0000 | *** | 1.4108 | large |

## McNemar 配对检验（passed，自指指标——仅作诊断参考）

R14 协议：二值配对数据（passed 0/1）的检验（Arcuri & Briand,
ICSE 2011）。注意：passed 为系统自产测试在（未修复的）缺陷代码
上的通过（自指口径，false_fix 主批次 89.8% 的直接来源），本节
不作为架构增益主张的依据；与上方 t 检验并列呈现，t 检验表保持
历史口径不变。

| 比较 | 共同任务数 | 不一致对 (n01+n10) | χ²（连续性校正） | p值 | 显著性 |
|------|-----------|-------------------|------------------|-----|--------|
| AITester vs plain_llm | 174 | 53 | 16.9811 | 0.0000 | *** |
| AITester vs plain_llm_df | 174 | 120 | 114.0750 | 0.0000 | *** |

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
| AITester vs plain_llm | 174 | -0.1782 | -0.2529 | -0.1034 | 10000 | 42 |
| AITester vs plain_llm_df | 174 | 0.6782 | 0.6092 | 0.7471 | 10000 | 42 |

## 效应量对比（Cohen's d 与 Cliff's δ）

R2 协议：Cliff's δ = (n⁺ − n⁻)/n_pairs（配对差值符号版，非参数）；
阈值 |δ|：0.147 / 0.33 / 0.474（Romano et al. 2006）。

| 比较 | Cohen's d | 效应量 | Cliff's δ | 效应量 |
|------|-----------|--------|-----------|--------|
| AITester vs plain_llm | -0.3401 | small | -0.1782 | small |
| AITester vs plain_llm_df | 1.4108 | large | 0.6782 | large |

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
| detection（F2P 检出） | AITester vs plain_llm | 0.1049 | [0.0522, 0.1630] | 0.9999 | 0.0209 | bayes_pos |
| detection（F2P 检出） | AITester vs plain_llm_df | -0.3673 | [-0.4552, -0.2785] | 0.0000 | 0.0000 | bayes_neg |
| repair（gold 裁决修复） | AITester vs plain_llm | 0.0000 | [-0.0185, 0.0187] | 0.4989 | 0.9999 | bayes_equiv |
| repair（gold 裁决修复） | AITester vs plain_llm_df | 0.0000 | [-0.0205, 0.0206] | 0.4983 | 0.9997 | bayes_equiv |

### passed（自指指标，仅作诊断参考）

| 比较 | δ 后验均值 | 95% CI | P(δ>0) | P(ROPE) | 结论 |
|------|-----------|--------|--------|---------|------|
| AITester vs plain_llm | -0.1742 | [-0.2511, -0.0982] | 0.0000 | 0.0008 | bayes_neg |
| AITester vs plain_llm_df | 0.6629 | [0.5879, 0.7326] | 1.0000 | 0.0000 | bayes_pos |

## 成本口径（$/task，价目表驱动——AE2）

成本口径：$/task = (Σ输入 token × 输入单价 + Σ输出 token × 输出单价) / 任务数；
价目来自 experiments/price_table.json（模型级登记，含来源与生效日期）；
token 行级来源 = 结果行 token_usage（input_tokens / output_tokens）；
多模型异价的基线无法按 in/out 拆分归属，成本诚实降级为未计价（—）。
$/detection（成本/检出）= $/task ÷ 检出率——AN5 呈现性推导（两次已登记
测量的商，非独立测量；领域口径对齐 SWE-bench 生态 $/resolved）。检出率
0% 的基线该列为 —（语义上趋于无穷，不得显示为有限数字）。

| Baseline | 任务数 | 输入 token | 输出 token | 成本/任务 | 成本/检出 | 币种 |
|----------|--------|-----------|-----------|-----------|-----------|------|
| aitester | 174 | 144326 | 31263 | 0.0005 | 0.0037 | USD |
| plain_llm | 174 | 0 | 0 | — | — | — |
| plain_llm_df | 174 | 0 | 0 | — | — | — |
| single_agent | 0 | 0 | 0 | — | — | — |

注：3 个基线未计价——plain_llm（缺: ）；plain_llm_df（缺: ）；single_agent（缺: ）。

## 测试套件可靠性（mutation_detection_rate 按臂聚合——AN2 呈现性增补）

口径：mutation_detection_rate = 生成的测试在 gold 修复代码上全绿、且在其
AST 变异体上变红的比例（ENABLE_MUTATION_SCORING 写回；None = 不可测，
按不可测跳过不进分母——保守不误报 0）。领域口径与 SWE-Mutation（2026）
的测试套件可靠性主信号同向：检出优先协议下，测试有效性需要独立于
detection 的客观测量（变异检出提供该测量，纯子进程零 LLM）。
**呈现性增补（AN2，2026-10-07）**：本节为报告呈现口径，非预注册主终点
变更；主终点仍为 detection 配对差（见预注册）。增补时点早于 E2 数据产生。

| Baseline | 可测行 | 总行 | 均值 (%) | 杀灭/变异体合计 |
|----------|--------|------|----------|-----------------|
| aitester | 31 | 174 | 76.69 | 168/238 |
| plain_llm | 13 | 174 | 76.11 | 85/114 |
| plain_llm_df | 81 | 174 | 92.56 | 411/467 |
| single_agent | 0 | 0 | — | 0/0 |

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
*报告生成时间: 2026-10-07 19:02:45*
