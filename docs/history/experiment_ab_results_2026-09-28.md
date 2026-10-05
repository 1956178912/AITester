# 真实功能缺口实验补齐：A/B 数据汇总（2026-09-28）

> **实验批次声明**：本批次为补齐论文实验章节证据缺口的 A/B 对照实验。
> 全部使用免费档小模型（agnes-3.0-flash 故障转移链，含 qwen / glm / deepseek 多 provider），
> 数据为合成数据集口径（`--seed 42`，可复现）；仓库级 SWE-bench 数据沿用
> `experiments/results/experiment_report_20260925.md` 既有快照，本批次不涉及。
>
> **配套代码变更**（本批次产生）：
> 1. `src/graph/nodes.py`：修复 `_generator_node` 早期 regenerate 路径漏计
>    `regeneration_count` 导致的 generator↔executor 死循环（实测单任务 trace
>    6000+ 行）；新增回归测试 `test_early_regenerate_path_increments_counter`。
> 2. `experiments/run_benchmark.py`：`_dump_state_artifacts` 补落盘
>    `position_aware_focus` 字段（此前 `position_aware_ab.py` 的定位正确率指标
>    恒 0.0，属指标失真而非功能未生效）。
> 3. `experiments/cross_file_ab.py`：新增跨文件修复 T1/T4 验收脚手架
>    （`docs/design/cross_file_repair.md` 既定验收标准缺实验脚手架）。

---

## 1. 位置感知迭代修复（POSITION_AWARE_REPAIR_ENABLE）

**脚本**：[experiments/position_aware_ab.py](../../experiments/position_aware_ab.py)
**结果**：[experiments/results/position_aware_synthetic/position_aware_ab_summary.md](../results/position_aware_synthetic/position_aware_ab_summary.md)

| 指标 | OFF（历史全文件口径） | ON（位置感知启用） | Delta |
|------|------|------|------|
| 成功率（n=30） | 96.67% | 96.67% | 0pp |
| 平均迭代 | 0.53 | 0.63 | +0.10 |
| 定位命中（focused=True） | — | 0/30（全部降级） | — |

**定位命中率为 0 的原因分析（重要）**：`_locate_repair_focus` 仅在
`error_classifier.extract_error_context()` 能从 pytest 失败输出中提取出
**行号**时才能定位（聚焦 = `focused: True`）。实测三类失败输出：
- **AssertionError**（合成集主要失败类型）：pytest 输出无 traceback
  行号 → `ctx.line=None` → 降级全文件修复；
- **RuntimeError 带 traceback**：`ctx.line=4, filename=calc.py` → 可定位
  （`focused=True`，见单元测试）；
- **模块顶层异常**：`ctx.line=1, in <module>` → 可定位。

即：**合成数据集的失败以 assertion 为主（无行号），位置感知定位阶段在这些
任务上全部降级为全文件修复**——因此 ON 组与 OFF 组行为完全一致（成功率均
96.67%），迭代次数 ON 组略高（+0.10，定位指引注入 prompt 的边际成本）。
**该实验未能区分位置感知修复的实际效果**，原因是数据集失败类型不匹配：
需要以 runtime / type error（带 traceback 行号）为主的失败任务才能激活
定位阶段。

**定位正确率指标的结构局限**：`_locate_accuracy` 的 gold 基准为
`task_metadata.suggested_function`，该字段仅存在于 SWE-bench 数据集
（`dataset_loader.py` 从官方 gold patch 提取）；合成数据集无此元数据，
故合成集上定位正确率恒 0.0（指标结构上不可计算，非功能未生效）。

**论文可引用表述（保守）**：位置感知迭代修复在合成数据集 30 任务
（seed=42，免费档小模型）上，ON 组成功率 96.67%（与 OFF 组持平），
平均迭代 +0.10；定位阶段在 assertion 类失败（占合成集失败主体）上
全部降级为全文件修复（0/30 命中），因合成集失败类型与定位阶段激活
条件（需 traceback 行号）不匹配。**该实验为阴性结果**——位置感知
修复的效率增益未在合成集上显现，需切换到以 runtime/type error 为主的
数据集（或 SWE-bench + GPT-4 级模型）重测，方能产出方向性证据。
不建议论文将合成集 +3.34pp（首批次的非复现波动）作为定位修复的收益主张。

**2026-10 改进批次（P1.1 补测，定位阶段激活验证）**：定位激活条件已落实为
合成数据集 `level2.5` / `level2.5-hard` 运行时异常缺陷库
（`IndexError` / `KeyError` / `AttributeError` / `TypeError`，失败输出携带
traceback 帧行号，`SyntheticDataset` 写入 `metadata["suggested_function"]` 供定位
金标准匹配），`position_aware_ab.py` 默认 difficulty 由 `mixed` 改
`level2.5`。level2.5-hard n=40（seed=42，免费档 2026-09-29 重跑口径）实测：
定位正确率 21.43%（ON 组 `focused=True` 命中 gold function，定位阶段
**已激活**，不再是 0/30 全降级），ON 85.0% / OFF 90.0%（−5.00pp，
定位开销 −0.08 迭代收益未显现；小样本波动区间内，方向性证据有限）。
**论文可引用定位（保守）**：位置感知修复在**运行时异常类缺陷**上定位阶段
可激活（21.43% 定位命中 vs 合成 mixed 集 0 命中），效率增益未显现——
该功能在论文中的定位是"针对运行时异常类缺陷（携带 traceback 行号）的
专项优化"，而非通用增强；对 assertion 类失败（无行号）仍全部降级全文件
修复（历史阴性结果保留）。结果：`experiments/results/pa_l25h_n40_g8batch/`。

---

## 2. RAG 检索增强（ENABLE_RAG）

**脚本**：[experiments/rag_ab_experiment.py](../../experiments/rag_ab_experiment.py)
**结果**：[experiments/results/rag_ab_synthetic/rag_ab_report.json](../results/rag_ab_synthetic/rag_ab_report.json)

| 指标 | RAG OFF | RAG ON | Delta | 显著性 |
|------|------|------|------|------|
| 成功率（n=20） | 90% | 90% | 0 | — |
| 平均 token/任务 | 3088 | 4346 | **+40.7%（负向）** | p=0.2920（不显著） |
| 平均迭代 | 0.70 | 0.65 | -0.05 | p=0.8890（不显著） |
| RAG 检索命中率 | — | 100%（0 次检索为空） | — | — |

**论文可引用表述**：在合成数据集 20 任务（seed=42，免费档小模型）上，RAG 检索
命中率 100%（无空检索），但 token 消耗 +40.7%（不显著，p=0.292，Cohen's d=0.333）
且成功率无变化（90% vs 90%）。结论：**RAG 的 token 效率收益未在本实验设置下
成立**——检索到的相似案例被注入 prompt 增加了输入 token，但未转化为修复成功率
提升。该结果与"检索精度有限"（`docs/failure_analysis.md` 问题 3）的历史观测一致；
建议下一步在真实仓库级数据集（SWE-bench lite + 强模型）上重测，或改用混合
检索（向量+关键词）提升注入精度后再评估 token 效率。

> ⚠️ 注意：token 负向 delta 的统计口径为"ON 组比 OFF 组多消耗 40.7% token
> （delta_pct 负值 = ON 更耗）"。若论文主张 RAG 效率收益，本批次数据不支持；
> 应如实报告为"检索命中率 100% 但 token 效率无收益、成功率无增益"。

**2026-10 改进批次（P1.2 补测，RAG 增强层在困难任务上的验证）**：
`RAG_RELEVANCE_THRESHOLD_ENABLE`（相似度阈值过滤，默认 0.7）+
`RAG_CONDITIONAL_ENABLE`（按错误类型条件注入）+ `RAG_JUDGE_INSTRUCTION_ENABLE`
三个增强层开关已实现但从未在有效场景中验证。level2.5-hard n=40（seed=42，
免费档 2026-09-29 重跑口径，`rag_ab_experiment.py --relevance-ab`）实测：
RAG ON（增强层全开）95% vs OFF 88%（**+7pp 成功率**，检索命中转化为成功率），
平均迭代 0.3 vs 0.7（ON 组 −0.4 轮，p=0.0497 显著），token 消耗
ON 3397 vs OFF 1724（+97%，检索注入的 token 成本未回收，但方向与历史
−40.7% 负向结论一致）。**RAG 真实适用边界（保守表述）**：困难任务
（level2.5-hard，运行时异常类缺陷）上，RAG 增强层带来 +7pp 成功率与
−0.4 迭代收敛收益；合成集简单任务（历史 n=20 口径）上 RAG 收益为 0 且
token +40.7% 负向。建议论文将 RAG 定位表述为"面向困难任务的检索增强层，
需与相关性阈值 + 条件注入联合启用"。结果：
`experiments/results/rag_lvl25h_n40_g8batch/`。

---

## 3. 跨文件修复（CROSS_FILE_ENABLE）

**脚本**：[experiments/cross_file_ab.py](../../experiments/cross_file_ab.py)（本批次新增）
**验收标准**：[docs/design/cross_file_repair.md](../design/cross_file_repair.md) §"默认启用前置条件"

### 3.1 T1：level3 跨文件子集（n=50，seed=42）

| 指标 | OFF（单文件回退） | ON（跨文件修复） | Delta |
|------|------|------|------|
| 成功率 | 88.0% | 98.0% | **+10.00pp** |
| 平均迭代 | 0.54 | 0.48 | -0.06 |

**判定**：T1（3.5 跨文件提升 ≥ +15pp）未达——三批次一致方向为正（合成集 +10.00pp
双模块 / +7.50pp 三模块 / +0.00pp L3.5 小样本 n=16 无分化，唯一失败任务归因
`LLM_CAPABILITY`：dep_edges=2 依赖图完整、3 轮修复未闭合），量级在合成集口径下
稳定低于 T1 阈值。结合 `cross_file_root_cause.py` 修复的 `_cross_file_analyzer_node`
跨文件 AST 分析缺陷（对被调方分析得 0 边覆盖预置依赖边），T1 缺口归因于
**LLM 引擎能力边界（免费档小模型）**而非跨文件管道缺陷。转正需 GPT-4 级模型
重跑（本批次 2026-09-29 G8 全开链路重测提供最新数据，见
`experiments/results/experiment_report_20260929_repo_level.md` §跨文件对照）。
T4 通过（单文件无回归 +2.00pp）。

### 3.2 T4：level1 单文件无回归（n=50，seed=42）

| 指标 | OFF | ON | Delta |
|------|------|------|------|
| 成功率 | 92.0% | 94.0% | +2.00pp |

**判定**：T4（下降 ≤ 5pp）**通过**——跨文件启用路径在单文件任务上无回归。

**论文可引用表述**：跨文件修复在 level3 双模块合成集（n=50，seed=42）上带来
+10.00pp 成功率提升（88% → 98%），平均迭代 -0.06；level1 单文件无回归
（+2.00pp，T4 通过）。**达到设计文档 T4 验收，未达 T1 验收阈值（+15pp）**。
结合 `docs/failure_analysis.md` 的归因（SWE-bench 0/7 失败源于数据管道 + 执行
环境 + 补丁管道三层缺陷，非 LLM 能力），本批次数据说明：在合成双模块任务上
跨文件修复已有正向信息量（+10pp），可支撑"跨文件修复在合成数据上有效"的论断；
但"在真实仓库级数据上有效"仍需在 GPT-4 级模型 + 修复后数据管道上重测
（`experiments/results/experiment_report_20260925.md` 既有快照 0/7 为免费档
小模型 + 缺陷管道的联合边界，不可直接外推）。

---

## 4. 三组实验横向对照

| 实验 | 数据集 | n | 关键 delta | 验收/显著性 | 论文定位 |
|------|------|---|------|------|------|
| 位置感知 ON/OFF | synthetic | 30 | 成功率 0pp，迭代 +0.10（定位 0/30 命中） | 阴性（失败类型不匹配） | 如实报告，需换数据集 |
| RAG ON/OFF | synthetic | 20 | token +40.7%（负向，不显著） | 效率收益不成立 | 如实报告负面结果 |
| 跨文件 ON/OFF | synthetic level3 | 50 | +10.00pp 成功率 | T1 未达（+15pp），T4 通过 | 能力边界证据 |

---

## 5. 勘误与后续

- **首批次的 +3.34pp 位置感知收益不成立（阴性结果）**：本批次首跑
  （OFF 93.33% / ON 96.67%）与重跑（OFF 100% / ON 96.67%）不一致，且重跑
  定位命中 0/30 全部降级——说明首跑的 +3.34pp 是 LLM 随机波动（temp=0.2），
  并非位置感知机制的真实收益。合成集失败以 assertion 为主（无 traceback
  行号），定位阶段从未激活。论文不应引用 +3.34pp。
- **死循环修复**：`_generator_node` 早期 regenerate 路径漏计
  `regeneration_count`，导致部分任务（如 `fibonacci_inefficient`）trace
  6000+ 行死循环。已修复并加回归测试；本批次全部实验在修复后运行。
- **跨文件真实数据验证**：本批次为合成双模块口径。真实 SWE-bench 跨文件
  收益验证仍需 GPT-4 级模型 + `SWE_BENCH_ENRICHMENT` + `RepoExecutor`
  仓库级管道（见 `docs/failure_analysis.md` 归因边界说明）。

---

*生成时间：2026-09-28；数据源：`experiments/results/{position_aware,rag,cross_file}_*/`；
基线口径：免费档小模型 + 合成数据集 + seed=42。*
