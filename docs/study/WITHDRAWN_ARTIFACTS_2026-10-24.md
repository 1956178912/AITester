# 撤回工件存档说明（2026-10-24 数据清除）

2026-10-24 按指令撤回 `experiments/results/` 全部历史批次（239 批次文件 /
138 traces 目录 / 全部派生报告），并在 DeepSeek 单端点语料上重建证据基座
（重建构成与成本见登记册 §1 与 `paper/draft.typ` §8）。本文档是被撤回工件的
**历史数字存档索引**：论文中以 historical 口径引用的撤回世代数字，其原始
工件不再分发，逐项对账记录冻结在 `PAPER_CONSISTENCY_AUDIT_2026-10-17.md`
（撤回前最后一次全量对账：202 条数字声明、可追溯率 100%）。撤回世代数字
不与重建世代混池。

## 撤回族索引（论文 SRC 以本文件为历史落点）

| 撤回族 | 历史角色 | 重建状态 |
|---|---|---|
| main_batch/（含 3seed_pooled 统计报告） | RQ1 主批（3 seeds × 87 任务 × 3 臂，thinking-on） | 未复刻多 seed 池；单批替代见 spec_ab/b1_lite |
| t_round_b1_protocol_text_20261018 | RQ2 协议文本六格消融 | 精简复刻 b1_lite_20261025（三格） |
| t_round_b2_main_batch_20261018 | 指纹锁定三 seed 复现批 | 未复刻（论文标 historical） |
| t_round_smt_witness(_aliasfix)_20261018 | SMT witness 层 | 未复刻 |
| t_round_oracle_k3 / a19_default_gate / semantic_fixes | K=3 投票 / A-19 门 / 语义修复设计 | 未复刻 |
| r_round_examples_selfcheck / s_round_*（decision/multisample/b8_injection） | Q-R-S 示例与消融轮 | b8 消融已重建（p_round_b8_ablation_20261018） |
| emse_gold_conformance_20261015 / emse_ult_gold_diagnosis_20261015 | gold 物化体检与 ULT gold 诊断 | 未复刻 |
| emse_dsl_diag*/extend_recheck/fix_smoke | DSL 诊断系列 | 未复刻 |
| emse_calib_quixbugs/ult/synth_20261014 | 校准批 | 未复刻 |
| emse_stats_2026-10-15 / emse_stats_extensions_20261016/20261021 | 统计扩展（Wilson/g/OR/CI） | 部分重算（`emse_stats_extensions_20261025/` 只覆盖单批臂，**未复刻 261 行池**；池化成本见下表 W-1） |
| emse_df_spec_20261016 | 规格锚主批 | spec_ab_scale87_20261024（quixbugs replace 臂）替代 |
| emse_docstring_anchor/augment_20261017 的 DF_DOC/DF_AUG_REPORT | 锚/增广裁决报告 | 批次已重建（benchmark_quixbugs_20261024/25_*），报告文件未重生成 |
| emse_oracle_quality/independent_judging/instrument_hardening | oracle 质量轮 | 注入批已重建（16/20） |
| pilot_mdo_full50 / swe_bench_lite_20 / e6_a1_batches / r4_batches | 探索与 E 系批 | 未复刻 |
| docs/reviews/*（82 份分册） | 逐轮评审分册 | 已删除（docs/reviews/README.md 占位） |

## 表 W-1：撤回世代池化成本读数（论文附录 E 的权威落点）

来源：`experiments/results/emse_stats_extensions_20261021/STATS_EXTENSIONS.json`
（2026-10-21 重发版，commit `d5bda23e`；2026-10-24 随全部历史批次撤回）。
口径：3 seeds × 87 任务 = **261 行/臂**；bootstrap n=10000、seed=42；价目加权
（in:out 取各臂自身混合比）。`35/261` = df 臂 `token_usage` 全 0 且
`generated_test` 非空的行数（有产出、无花费记录）⇒ 该臂 tokens/task 与
$/task 是**已记录下界**，不是账单。

| 臂 | tokens/task | 95% CI | $/task | in:out |
|---|---|---|---|---|
| aitester | 26,114.854406130267 | [24,226.31, 28,086.02] | 0.025884977011494247 | 1,581,326:5,234,651 |
| plain_llm | 3,209.44061302682 | [2,964.02, 3,474.23] | 0.003358973563218391 | 142,783:694,881 |
| plain_llm_df | 4,223.103448275862 | [3,822.94, 4,642.52] | 0.004543231034482759 | 152,103:950,127 |

**重建覆盖边界（2026-10-25 实测）**：`emse_stats_extensions_20261025/STATS_EXTENSIONS.json`
只含单批臂（rp02 n=20、e4 n=36/41、e6 n=35/36），**不含 261 行池的成本表**。
因此附录 E 的池化成本行没有被重建世代替代，引用时只能落到本表；论文附录 E
已按 historical 标注。

## 引用纪律

- 撤回世代数字：引用时带 historical 标注 + 指向本文件或
  `PAPER_CONSISTENCY_AUDIT_2026-10-17.md`，不指向已删除路径。
- 重建世代数字：指向 `experiments/results/` 在盘工件。
- 两代不混池；方向性继承（如「历史四行全部负向」）须注明世代。
