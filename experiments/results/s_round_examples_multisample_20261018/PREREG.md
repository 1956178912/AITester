# S-3 预注册（跑批前冻结）：多采样自一致性过滤器（K=2）评估

- 冻结时间：2026-10-18（实现与单测完成、真实采样开始前）
- 性质：**探索性机制验证**（非 confirmatory）
- 输入：同 P-1 的 20 个任务/同一锚材料（`emse_spec_anchor_20261016` +
  `emse_df_spec_20261016` 工件）；**重新做 K=2 次 spec-only 采样**（每任务
  2 次小调用、cache namespace 区分 sample_idx、**关闭 LLM 缓存**、max_tokens
  512、≤3 条/样本）；预算 ≤$0.05（预期 ~$0.01-0.02）
- 处理：`generate_examples_multisample(k=2)`：仅保留**出现于两个采样**的
  (input, expected)（归一化 JSON 键），交集 ≤3 条；淘汰样本内唯一示例。
- 基线：P-1.1 表示归一 `ORACLE_EXAMPLES_REPORT_norm.json`
  （correct 8 / fp 0 / silent 3 / misguided 2 / unavailable 7；分母 13）
- 重放：`oracle_examples_replay --reuse-examples <交集版报告>`（零 LLM；
  `SPEC_ORACLE_EXEC_ENABLE=true SPEC_ORACLE_EXAMPLES_ENABLE=true`），
  输出本目录 `ORACLE_EXAMPLES_REPORT_multisample.json`

## 判定规则（冻结，跑后不得改）

1. **有效过滤（多采样一致）**：P-1 的 2 个 hallucination 期望中**至少 1 个
   不在交集**（即不会进入 oracle）**且** `correct` 损失 ≤1（相对 8）→ 记为
   「有效过滤（多采样一致）」；
2. **高风险，默认关**：交集版 `correct` 相对 8 下降 **≥2** → 记为
   「高风险，默认关」；
3. 其余 → 「未达有效过滤」。

## 预声明口径/风险

- **hallucination 命中定义**：P-1 幻觉示例对
  (`is_valid_parenthesization`: `input=["((("]`, `expected=True`；
  `knapsack`: `input=[5, [[5,10]]]`, `expected=0`) 是否**不在交集**。
  同时报告它在两个新采样中的出现次数，以区分「被交集剔除」与「重采样未再现」。
- **预期**：K=2 自由采样交集可能很稀疏（两样本示例集合近似随机），correct
  可能下降；若下降 ≥2 则按规则记「高风险默认关」——这是多采样一致性的成本，
  如实报告，不粉饰。温度=0 但服务端非严格确定，多采样前提成立但样本相关性未知。
- 次要指标：每任务 2 样本 examples 数、交集大小、丢弃条数、审计
  （`MULTISAMPLE_STATS.json`）；两源臂重放结果（预期相同）；LLM 调用/tokens/成本。
- 限制：n=20、单次 K=2；不重新生成规约；不过滤后处理；非 confirmatory。
