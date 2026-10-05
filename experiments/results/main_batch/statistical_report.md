# 统计显著性检验报告

## 数据来源

R2 审计：本报告实际纳入 3 个批次文件（--batches 白名单模式）：

- `benchmark_synthetic_20261001_112528.json`
- `benchmark_synthetic_20261001_112801.json`
- `benchmark_synthetic_20261001_121523.json`

## 数据概览

| Baseline | 任务数 | 通过数 | 通过率 |
|----------|--------|--------|--------|
| aitester | 60 | 54 | 90.0% |
| plain_llm | 60 | 32 | 53.3% |
| single_agent | 50 | 0 | 0.0% |

## 配对t检验结果

| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |
|------|--------|---------|-----|--------|-----------|--------|
| AITester vs plain_llm | 53 | 4.4128 | 0.0001 | *** | 0.6061 | medium |
| AITester vs single_agent | 50 | 21.0000 | 0.0000 | *** | 2.9698 | large |

## McNemar 配对检验（二值指标）

R14 协议：二值配对数据（passed 0/1）的正确检验（Arcuri & Briand,
ICSE 2011）；与上方 t 检验并列呈现，t 检验表保持历史口径不变。

| 比较 | 共同任务数 | 不一致对 (n01+n10) | χ²（连续性校正） | p值 | 显著性 |
|------|-----------|-------------------|------------------|-----|--------|
| AITester vs plain_llm | 53 | 25 | 12.9600 | 0.0003 | *** |
| AITester vs single_agent | 50 | 45 | 43.0222 | 0.0000 | *** |

## 多重比较校正（BH-FDR）

对上表各 McNemar p 值做 Benjamini-Hochberg FDR 校正（α=0.05）；
q 为校正后 p 值，拒绝 H0 表示校正后仍显著。

| 比较 | 原始 p（McNemar） | BH-FDR q | 拒绝 H0 |
|------|-------------------|----------|---------|
| AITester vs plain_llm | 0.0003 | 0.0003 | 是 |
| AITester vs single_agent | 0.0000 | 0.0002 | 是 |

## Bootstrap 95% 置信区间

R2 协议：配对差值均值（AITester − 基线，逐任务 0/1 差）的有放回
重采样百分位法 95% CI（默认 10000 次，random.Random(seed=42) 固定，
结果逐位可复现）。CI 不含 0 即方向稳健。

| 比较 | 配对数 | 差值均值 | 95% CI 下界 | 95% CI 上界 | 重采样次数 | seed |
|------|--------|---------|------------|------------|-----------|------|
| AITester vs plain_llm | 53 | 0.3585 | 0.2075 | 0.5094 | 10000 | 42 |
| AITester vs single_agent | 50 | 0.9000 | 0.8200 | 0.9800 | 10000 | 42 |

## 效应量对比（Cohen's d 与 Cliff's δ）

R2 协议：Cliff's δ = (n⁺ − n⁻)/n_pairs（配对差值符号版，非参数）；
阈值 |δ|：0.147 / 0.33 / 0.474（Romano et al. 2006）。

| 比较 | Cohen's d | 效应量 | Cliff's δ | 效应量 |
|------|-----------|--------|-----------|--------|
| AITester vs plain_llm | 0.6061 | medium | 0.3585 | medium |
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
*报告生成时间: 2026-10-05 12:23:37*
