# mutation × detection 交叉验证（EMSE 构念效度辅助证据，零 LLM）

来源：已归档批次 JSON 的 `results[arm].details[]`；detection_rate 与
mutation_score 均非 None 的行才进配对（None = 不可测，遵循保守口径，
不计为 0）。变异得分饱和阈值 0.98（与 `experiments/target_quality_replay.py`
同口径）——饱和即标注**无鉴别力**，不得作为测试有效性证据。

**解读纪律**：detection 为强不平衡二值（合成主批次检出率低），与连续
mutation_score 的 Pearson 对少数类不敏感、Spearman 受 ties 支配；本表
**只作收敛效度的辅助证据**，须与分层均值并列阅读，不得单独用于主张
detection_rate 是有效质量代理。

| 臂 | 批次文件数 | 配对 n | detection 可测 n | detection 率 | mean(MS\|det=1) | mean(MS\|det=0) | Δ均值 | Pearson | Spearman | 饱和判定 |
|----|-----------|--------|------------------|--------------|------------------|------------------|--------|---------|----------|----------|
| aitester | 10 | 556 | 605 | 13.06% | 0.9968 | 0.8705 | 0.1263 | 0.1805 | 0.1892 | 可鉴别 |
| plain_llm | 10 | 609 | 658 | 1.67% | 1.0000 | 0.9768 | 0.0232 | 0.0263 | 0.0365 | 近饱和，谨慎解读 |
| plain_llm_df | 10 | 571 | 571 | 48.86% | 0.9857 | 0.9954 | -0.0098 | -0.0562 | -0.0730 | **无鉴别力（饱和）** |

退化与不可测说明：Spearman 在 n<3 或任一侧零方差时记 None（不臆造）；
退化原因字符串由 `experiments/emse_optimization.py::mutation_correlation()` 的返回体
键 `mutation_score.spearman_reason` 承载（本报告为派生物，不额外落盘 JSON）。

**方向性发现（须与上表同读，不得单独引用）**：Δ均值（det=1 组减 det=0 组）
为正表示「检出组变异得分更高」（收敛），为负表示**不一致**——负号出现时须
如实披露，不得以 Pearson 的弱正号掩盖分层方向。
