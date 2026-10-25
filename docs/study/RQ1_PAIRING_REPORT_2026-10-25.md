# RQ1 配对统计报告（冻结副本，2026-10-25）

> 本文件是 `experiments/statistical_analysis.py` 输出报告的**冻结副本**：原输出写在
> `/tmp/rq1_new_report.md`，路径不在仓库内、随时可能被系统清理——论文的 `// SRC:` 若指向
> 它，就是「路径存在但工件不可达」。CN 轮把内容原样入库，并在此记录复算命令。
>
> 复算：`python experiments/statistical_analysis.py --results-dir
> experiments/results/spec_ab_scale87_20261024/quixbugs_off --output <report.md>
> --batches benchmark_quixbugs_20261024_183918.json`
>
> 纪律：本副本**只搬运、不改数**。任何重算都必须重新生成并整份替换，不得手改单元格。

## 数据来源

R2 审计：本报告实际纳入 1 个批次文件（--batches 白名单模式）：

- `benchmark_quixbugs_20261024_183918.json`

### 分析集流量（BY：逐层剔除与去重）

| 层 | 文件 | 行 | 说明 |
|---|---:|---:|---|
| 扫描（白名单） | 1 | 100 | 加载器唯一扫描面 |
| 数据集白名单外 | −0 | −0 | 无 |
| schema 不完备（默认剔除） | −0 | −0 | `detection_rate` 全 None；`--allow-schema-mixed` 恢复 |
| 基线未登记 | 0 | −0 | 无 |
| **载入** | **1** | **100** | 实际进入统计（`## 数据来源` 清单） |
| 重复 task_id 折叠 | — | −0 | 最新批次优先；此前只有 DEBUG 日志 |
| **唯一 task 行** | — | **100** | 配对单元（含缺 task_id 剔除） |
| `passed`：None / 可测 | — | 0 / 100 | None 在去重后、配对前剔除；**None ≠ 0** |
| `detection_rate`：None / 可测 | — | 29 / 71 | None 在去重后、配对前剔除；**None ≠ 0** |
| `repair_rate`：None / 可测 | — | 39 / 61 | None 在去重后、配对前剔除；**None ≠ 0** |

> 对账：扫描 100 − 数据集外 0 − schema 0 − 读取/加载失败 0 − 未登记基线 0 = **100**（载入 100）；载入 − 重复 0 − 缺 task_id 0 = **100**（唯一行）。两项均闭合。
> 外部口径（联网核对）：PRISMA 2020 流程图要求逐阶段记录数量与排除理由，且流程图数字必须与正文/结果表逐一对账；Hurlbert（1984）的伪重复定义要求 n 只数独立观测单元——重复 task_id 折叠本身是对的，但折叠量必须披露，否则读者无法判断唯一行数是不是独立单元数。
> 本表只记账：不改任何判定值、不改 passed / repair / 分母，也不回填归档行。

复算命令（工件与代码齐备时数值逐位可复现）：`python experiments/statistical_analysis.py --results-dir experiments/results/spec_ab_scale87_20261024/quixbugs_off --output <report.md> --batches benchmark_quixbugs_20261024_183918.json`

去重口径：同一 task_id 跨批次重复时最新批次优先（排序主键 = 批次
文件名内嵌时间戳降序，文件系统 mtime 仅作无内嵌时间戳批次的兜底）。

## 数据概览

| Baseline | 任务数 | 通过数 (passed) | 通过率 | detection 可测数 | detection 率 | repair 可测数 | repair 率 |
|----------|--------|-----------------|--------|------------------|--------------|---------------|-----------|
| aitester | 50 | 23 | 46.0% | 35 | 60.0% | 20 | 10.0% |
| plain_llm | 0 | 0 | 0.0% | 0 | 0.0% | 0 | 0.0% |
| single_agent | 0 | 0 | 0.0% | 0 | 0.0% | 0 | 0.0% |
| plain_llm_df | 50 | 0 | 0.0% | 36 | 80.6% | 41 | 0.0% |

## 诚实指标 McNemar 检验（M1 三指标，gold 材料独立裁决）

2026-10-05 P0 协议：passed = 系统自产测试在（未修复的）缺陷代码上
通过，为自指指标（奖励写不出能抓 bug 的测试）；detection / repair
由留出 gold 材料独立裁决。**本节为报告的首要结论口径**——与
下方 passed 系列检验并列呈现，解读冲突时以本节为准。

口径说明（EMSE 批次，防止读者误读）：本节'独立裁决'指**判据材料
独立于被测系统**（留出 gold 测试与 gold 补丁），**不含任何人工
裁决**——全流程为零 LLM 的自动化 oracle 判定。人工复核（E7）为
预注册项但尚未执行，不得据此声称人工参与。

多重比较校正（EMSE 批次 2026-10-15）：本节 p 值按**指标族**独立做
BH-FDR 校正（detection 族与 repair 族各自构成 FDR 分母），q 值见
末两列；此前校正只覆盖下方 passed 口径。

| 指标 | 比较 | 共同任务数 | 不一致对 | χ²（连续性校正） | p值 | 显著性 | BH-FDR q值 | FDR后显著 |
|------|------|-----------|---------|------------------|-----|--------|-----------|----------|
| detection（F2P 检出） | AITester vs plain_llm_df | 35 | 11 | 3.2727 | 0.0704 | n.s. | 0.0704 | 否 |
| repair（gold 裁决修复） | AITester vs plain_llm_df | 20 | 2 | 0.5000 | 0.4795 | n.s. | 0.4795 | 否 |

## 配对t检验结果

| 比较 | 配对数 | t统计量 | p值 | 显著性 | Cohen's d | 效应量 |
|------|--------|---------|-----|--------|-----------|--------|
| AITester vs plain_llm_df | 50 | 6.4607 | 4.54e-08 | \*\*\* | 0.9137 | large |

## McNemar 配对检验（passed，自指指标——仅作诊断参考）

R14 协议：二值配对数据（passed 0/1）的检验（Arcuri & Briand,
ICSE 2011）。注意：passed 为系统自产测试在（未修复的）缺陷代码
上的通过（自指口径，false_fix 主批次 89.8% 的直接来源），本节
不作为架构增益主张的依据；与上方 t 检验并列呈现，t 检验表保持
历史口径不变。

| 比较 | 共同任务数 | 不一致对 (n01+n10) | χ²（连续性校正） | p值 | 显著性 |
|------|-----------|-------------------|------------------|-----|--------|
| AITester vs plain_llm_df | 50 | 23 | 21.0435 | 4.49e-06 | \*\*\* |

## 多重比较校正（BH-FDR）

对上表各 McNemar p 值做 Benjamini-Hochberg FDR 校正（α=0.05）；
q 为校正后 p 值，拒绝 H0 表示校正后仍显著。

| 比较 | 原始 p（McNemar） | BH-FDR q | 拒绝 H0 |
|------|-------------------|----------|---------|
| AITester vs plain_llm_df | 4.49e-06 | 4.49e-06 | 是 |

## Bootstrap 95% 置信区间

R2 协议：配对差值均值（AITester − 基线，逐任务 0/1 差）的有放回
重采样百分位法 95% CI（默认 10000 次，random.Random(seed=42) 固定，
结果逐位可复现）。CI 不含 0 即方向稳健。

| 比较 | 配对数 | 差值均值 | 95% CI 下界 | 95% CI 上界 | 重采样次数 | seed |
|------|--------|---------|------------|------------|-----------|------|
| AITester vs plain_llm_df | 50 | 0.4600 | 0.3200 | 0.6000 | 10000 | 42 |

## 效应量对比（Cohen's d 与 Cliff's δ）

R2 协议：Cliff's δ = (n⁺ − n⁻)/n_pairs（配对差值符号版，非参数）；
阈值 |δ|：0.147 / 0.33 / 0.474（Romano et al. 2006）。

| 比较 | Cohen's d | 效应量 | Cliff's δ | 效应量 |
|------|-----------|--------|-----------|--------|
| AITester vs plain_llm_df | 0.9137 | large | 0.4600 | medium |

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
| detection（F2P 检出） | AITester vs plain_llm_df | -0.1795 | [-0.3537, -0.0137] | 0.0175 | 0.0589 | bayes_neg |
| repair（gold 裁决修复） | AITester vs plain_llm_df | 0.0833 | [-0.0674, 0.2539] | 0.8743 | 0.3064 | bayes_inconclusive |

### passed（自指指标，仅作诊断参考）

| 比较 | δ 后验均值 | 95% CI | P(δ>0) | P(ROPE) | 结论 |
|------|-----------|--------|--------|---------|------|
| AITester vs plain_llm_df | 0.4259 | [0.2851, 0.5659] | 1.0000 | 0.0000 | bayes_pos |

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
| aitester | 50 | 373569 | 142717 | 0.0057 | 0.0094 | USD |
| plain_llm | 0 | 0 | 0 | — | — | — |
| plain_llm_df | 50 | 32286 | 49597 | 0.0014 | 0.0017 | USD |
| single_agent | 0 | 0 | 0 | — | — | — |

注：2 个基线未计价——plain_llm（缺: ）；single_agent（缺: ）。

**缓存口径（AJ）**——缓存命中不是记账断裂，也不是免费：
- `aitester`：命中 2 次、避免 5738 tokens（50/50 行带缓存字段，1 行命中）；真实消耗记 0 是对的，但 0 不等于免费——避免的 token 不计入 $/task。
- `plain_llm_df`：命中 0 次、避免 0 tokens（50/50 行带缓存字段，0 行命中）；真实消耗记 0 是对的，但 0 不等于免费——避免的 token 不计入 $/task。

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
| aitester | 0 | 50 | — | 0/0 |
| plain_llm | 0 | 0 | — | 0/0 |
| plain_llm_df | 0 | 50 | — | 0/0 |
| single_agent | 0 | 0 | — | 0/0 |

注：全部臂无可测行——本批该指标不可测（诚实披露，而非 0 检出）。

## pass@k（多轮采样并集解决率——批次 IX / ADR-0023 呈现性增补）

口径：同任务跨批次行 = 采样轮次；成功 = patch_correct（gold 材料独立裁决／自动化 oracle）。
k 上界 = 各任务轮次数的最小值（轮次不足诚实截断为 —）。

| 基线 | 任务数 | 轮次 (min/中位/max) | pass@1 | pass@2 | pass@3 | pass@5 | pass@10 |
|---|---|---|---|---|---|---|---|
| aitester | 50 | 1/1/1 | 0.0400 | — | — | — | — |
| plain_llm | 0 | — | — | — | — | — | — |
| plain_llm_df | 50 | 1/1/1 | 0.0000 | — | — | — | — |
| single_agent | 0 | — | — | — | — | — | — |

> 注：存量批次的 patch_correct 恒 0 系 ADR-0021 围栏伪影——本节
> correct 口径以修复后跑批解读；存量修正数字见 `make repair-replay`。

## $/solved task（每解决一任务成本——批次 IX / ADR-0023）

- aitester: 0.141666
- plain_llm: 未定义（correct=0 / 未计价 / token 记账不可用）——与 $/detection 同口径诚实降级
- plain_llm_df: 未定义（correct=0 / 未计价 / token 记账不可用）——与 $/detection 同口径诚实降级
- single_agent: 未定义（correct=0 / 未计价 / token 记账不可用）——与 $/detection 同口径诚实降级

## 污染视角（contamination_risk_level 按臂聚合——批次 IX / ADR-0023）

| 基线 | high | medium | low | unknown | not_applicable | 含污染 passed 率 | 干净 passed 率 |
|---|---|---|---|---|---|---|---|
| aitester | 0 | 0 | 0 | 0 | 50 | — | — |
| plain_llm | 0 | 0 | 0 | 0 | 0 | — | — |
| plain_llm_df | 0 | 0 | 0 | 0 | 50 | — | — |
| single_agent | 0 | 0 | 0 | 0 | 0 | — | — |

> 口径：行级三维相似度（token Jaccard + AST 骨架 LCS + 语义词袋）
> 综合分级；含污染组成功率显著高于干净组（Δ≥0.2）时，结果归因
> 须剔除含污染样本单独报告（experiments/contamination_check.py）。


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
*报告生成时间: 2026-10-25 12:07:54*
