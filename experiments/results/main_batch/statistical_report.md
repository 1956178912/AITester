# 统计显著性检验报告

## 数据来源

R2 审计：本报告实际纳入 1 个批次文件（--batches 白名单模式）：

- `main_batch/benchmark_synthetic_20261001_121523.json`

复算命令（工件与代码齐备时数值逐位可复现）：`python experiments/statistical_analysis.py --results-dir experiments/results --output <report.md> --batches main_batch/benchmark_synthetic_20261001_121523.json`

去重口径：同一 task_id 跨批次重复时最新批次优先（排序主键 = 批次
文件名内嵌时间戳降序，文件系统 mtime 仅作无内嵌时间戳批次的兜底）。

## 数据概览

| Baseline | 任务数 | 通过数 (passed) | 通过率 | detection 可测数 | detection 率 | repair 可测数 | repair 率 |
|----------|--------|-----------------|--------|------------------|--------------|---------------|-----------|
| aitester | 50 | 45 | 90.0% | 49 | 2.0% | 50 | 0.0% |
| plain_llm | 50 | 26 | 52.0% | 49 | 2.0% | 50 | 0.0% |
| single_agent | 50 | 0 | 0.0% | 50 | 0.0% | 50 | 0.0% |

## 诚实指标 McNemar 检验（M1 三指标，gold 独立裁决）

2026-10-05 P0 协议：passed = 系统自产测试在（未修复的）缺陷代码上
通过，为自指指标（奖励写不出能抓 bug 的测试）；detection / repair
由留出 gold 材料独立裁决。**本节为报告的首要结论口径**——与
下方 passed 系列检验并列呈现，解读冲突时以本节为准。

| 指标 | 比较 | 共同任务数 | 不一致对 | χ²（连续性校正） | p值 | 显著性 |
|------|------|-----------|---------|------------------|-----|--------|
| detection（F2P 检出） | AITester vs plain_llm | 48 | 2 | 0.5000 | 0.4795 | n.s. |
| detection（F2P 检出） | AITester vs single_agent | 49 | 1 | 0.0000 | 1.0000 | n.s. |
| repair（gold 裁决修复） | AITester vs plain_llm | 50 | 0 | 0.0000 | 1.0000 | n.s. |
| repair（gold 裁决修复） | AITester vs single_agent | 50 | 0 | 0.0000 | 1.0000 | n.s. |

## 配对t检验结果

| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |
|------|--------|---------|-----|--------|-----------|--------|
| AITester vs plain_llm | 50 | 4.7349 | 0.0000 | *** | 0.6696 | medium |
| AITester vs single_agent | 50 | 21.0000 | 0.0000 | *** | 2.9698 | large |

## McNemar 配对检验（passed，自指指标——仅作诊断参考）

R14 协议：二值配对数据（passed 0/1）的检验（Arcuri & Briand,
ICSE 2011）。注意：passed 为系统自产测试在（未修复的）缺陷代码
上的通过（自指口径，false_fix 主批次 89.8% 的直接来源），本节
不作为架构增益主张的依据；与上方 t 检验并列呈现，t 检验表保持
历史口径不变。

| 比较 | 共同任务数 | 不一致对 (n01+n10) | χ²（连续性校正） | p值 | 显著性 |
|------|-----------|-------------------|------------------|-----|--------|
| AITester vs plain_llm | 50 | 23 | 14.0870 | 0.0002 | *** |
| AITester vs single_agent | 50 | 45 | 43.0222 | 0.0000 | *** |

## 多重比较校正（BH-FDR）

对上表各 McNemar p 值做 Benjamini-Hochberg FDR 校正（α=0.05）；
q 为校正后 p 值，拒绝 H0 表示校正后仍显著。

| 比较 | 原始 p（McNemar） | BH-FDR q | 拒绝 H0 |
|------|-------------------|----------|---------|
| AITester vs plain_llm | 0.0002 | 0.0002 | 是 |
| AITester vs single_agent | 0.0000 | 0.0001 | 是 |

## Bootstrap 95% 置信区间

R2 协议：配对差值均值（AITester − 基线，逐任务 0/1 差）的有放回
重采样百分位法 95% CI（默认 10000 次，random.Random(seed=42) 固定，
结果逐位可复现）。CI 不含 0 即方向稳健。

| 比较 | 配对数 | 差值均值 | 95% CI 下界 | 95% CI 上界 | 重采样次数 | seed |
|------|--------|---------|------------|------------|-----------|------|
| AITester vs plain_llm | 50 | 0.3800 | 0.2200 | 0.5400 | 10000 | 42 |
| AITester vs single_agent | 50 | 0.9000 | 0.8200 | 0.9800 | 10000 | 42 |

## 效应量对比（Cohen's d 与 Cliff's δ）

R2 协议：Cliff's δ = (n⁺ − n⁻)/n_pairs（配对差值符号版，非参数）；
阈值 |δ|：0.147 / 0.33 / 0.474（Romano et al. 2006）。

| 比较 | Cohen's d | 效应量 | Cliff's δ | 效应量 |
|------|-----------|--------|-----------|--------|
| AITester vs plain_llm | 0.6696 | medium | 0.3800 | medium |
| AITester vs single_agent | 2.9698 | large | 0.9000 | large |

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
*报告生成时间: 2026-10-05 20:12:09*
