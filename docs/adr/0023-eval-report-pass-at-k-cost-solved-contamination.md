# ADR-0023: 评估报告口径收口——pass@k / $/solved task / 污染视角三节入统计报告

- 日期：2026-10-07（修复引擎批次 IX，第十七轮审查建议 11/14/22）
- 状态：已采纳（Accepted——呈现性增补，主终点与判定规则零变化）
- 关联：ADR-0021（correct 口径伪影披露义务）、`experiments/statistical_analysis.py`、`experiments/contamination_check.py`

## 背景（Context）

1. 第十七轮审查指出评估可信度三缺口：多候选/多轮采样能力未以 pass@k 报告（建议 14）；成本只报 $/task（repair=0 时无意义，应对齐 SWE-bench 生态 $/resolved——建议 22）；已有三维污染检测但未入统计报告（建议 11）。
2. ADR-0021 后 correct 分母首次非零（存量修正口径 38.7%），$/solved 具备定义条件。

## 决策（Decision）

1. **pass@k（多轮采样并集解决率）**：`pass_at_k_summary`——同 task_id 跨批次行 = 采样轮次（默认加载模式保留全部轮次），HumanEval 官方无偏估计公式 `1 - ∏(1-k/i)`；成功 = `patch_correct`（gold 裁决主口径）；k ∈ {1,2,3,5,10}，k 超过各任务轮次最小值时诚实截断；None 行不入轮次（M1 口径一致）。
2. **$/solved task**：`cost_per_solved`——总成本 ÷ patch_correct=1 行数；correct=0 / 未计价 → None（语义 ∞，与 $/detection 同口径诚实降级）。
3. **污染视角**：`contamination_view_summary`——行级 `contamination_risk_level`（run_benchmark 已算的三维综合分级）按臂聚合五档计数 + 含污染（high/medium）vs 干净（low）passed 率对照；not_applicable/unknown 不入分母。
4. 三节挂入 `run_all_statistics`（mutation 节之后），并随节携带 ADR-0021 披露注记：**存量批次 patch_correct 恒 0 系伪影，correct 口径的 pass@k 与 $/solved 以修复后跑批解读；存量修正数字用 `make repair-replay`**。

## 后果（Consequences）

**正面**：评估面与 SWE-bench 生态对齐（pass@k、$/resolved）；污染影响从"工具存在"升级为"报告可见"；呈现性增补先例（AN2）延续，历史口径零变化。

**负面/风险**：pass@k 的轮次口径依赖"同 task 跨批次 = 独立采样"假设——缓存确定性重放下同种子重跑非独立轮次（temp=0 缓存命中逐位重放，E2 迭代批实证）；多种子池化（pool_seeds）或缓存关闭（AITESTER_LLM_CACHE=0）下才满足独立性，报告解读须注意。

## 验证

- 批次 IX 测试锁 17 项（pass@k 数学边界 / 汇总平均与截断 / $/solved 三态 / 污染聚合 / 接线存在性）；
- 存量冒烟：main_batch 目录 137 任务（aitester，7 轮 max）三节渲染正常；污染视角首测 0 high / 0 medium / 50 low（synthetic 有 gold patch 行可检，609 not_applicable 诚实披露）。

## 修订记录

1. 2026-10-07 首次落地（批次 IX）：`pass_at_k_summary` + `cost_per_solved` + `contamination_view_summary` 三函数 + `run_all_statistics` 三节接线 + 17 项测试。
