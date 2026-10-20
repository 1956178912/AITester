> **语言 / Language**：[English](VALIDITY.en.md) | 简体中文（本文）

# 效度威胁报告（Validity Threats Report）

最后更新：2026-10-19（Z 轮第三方审查 F01/F17/F20：① F01 更正 §4 旧非标准 BH 描述为标准 BH
（q_(i)=min(1,min_{j≥i} m·p_(j)/j)）并加 Z 轮 F01 勘误注记；② F17 传播 ADR-0025 的 2026-10-16 一手核验状态与
`citation_allowlist.txt` 零豁免，同时保留 Java→Python 外推限制；③ F20 补全 T-10 匹配子集严格口径键
（pattern×difficulty×seed）与两种口径各自的互补总体，明确 strict 与 loose 是不同总体、不是互补对照）。
此前 2026-10-15（EMSE 批次：首次成体系登记构念 / 内部 / 外部 / 结论四类
效度威胁，逐条给出状态、缓解措施、残余风险；5 项 OPEN 威胁给出未缓解原因、
缓解实验与论文收缩口径）

> **证据纪律**：本文每一个数字都必须在正文内标注可读的源文件路径；未能在仓库内
> 核验的事项一律进入 §7"不可核验与未核验事项"，不得以估计值填充。表内状态取值：
> `open`（未缓解，论文必须收缩口径）/ `reduced`（已定口径标签或已被机制性缓解，
> 但存在需持续披露的残余风险）/ `mitigated`（已定位根因并修复，残余风险已登记）。

---

## 0. 目的、证据纪律与状态定义

本文回答审稿人最可能追问的问题：**这套结论在什么范围内成立、在什么范围内不成立**。
写作口径与项目既有诚实纪律一致——主批次数字以 `BASELINE.yaml` 的 `benchmark` 节为
单一事实来源（`README.md` 基准指标节），但本文只引用**可直接打开并复核**的工件与
决策记录，不引用二手转述。

三条通用纪律（全文适用）：

1. **口径标签强制**：repair / false_fix / detection 的任何数字必须携带口径标签
   （`docs/design/repair_caliber_matrix.md` §3"引用纪律"：repair 为 ①–⑨，false_fix 为
   该文件"false_fix 口径（权威落点）"节的 ⑩⑪）；
2. **派生工件入库纪律**：机器可再生的派生物默认不入库、证据链指向源工件
   （`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §5）；白名单内的 `main_batch/`
   统计报告随证据链入库（`mutation_detection_correlation.md`，2026-10-16 起），
   `emse_swebench_disclosure.md` 维持不入库；
3. **无人工裁决**：全项目"gold 独立裁决"一律指**判据材料独立**（留出 gold 测试 /
   gold 补丁）的自动化 oracle，**不含任何人工裁决**；E7 人工复核为预注册项但**尚未
   执行**，全仓不存在 Kappa 工件（`README.md` 基准指标节；核验见 §7 第 1 条）。

---

## 1. 构念效度（Construct Validity）

| 威胁 | 状态 | 缓解措施 | 残余风险 |
|------|------|----------|----------|
| `detection_rate` 被当作"测试质量"的通用代理 | **open** | ①变异得分交叉验证改为**真算**并内置诚实纪律（饱和阈值 0.98 → 标"无鉴别力"）；②论文强制把 detection 定位为**特定于本基准的检出信号（protocol-level signal）**而非质量代理（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §1.2/§2 结论 3） | 变异得分在合成主批次**高度集中、接近饱和上限**（分层均值 0.87–1.00；饱和阈值 0.98，`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §2 结论 1）→ `plain_llm_df` 判定为**无鉴别力（饱和）**、`plain_llm` 为**近饱和，谨慎解读**，"生成测试质量高"类主张**无指标可支撑**；`plain_llm_df` 臂 Δ均值 = **−0.0098**、判定为**无鉴别力（饱和）**（`experiments/results/main_batch/mutation_detection_correlation.md` 第 17 行），即"检出更多"未伴随"变异覆盖更高" |
| `false_fix_rate` 双口径（边际 59.58% = 143/240 vs 条件 100% = 143/143）并存易被误引 | **reduced** | 双口径由回归测试锁定，禁止单引：`tests/test_emse_optimization.py::TestFalseFixCaliber::test_matrix_against_main_batch_artifacts` 断言 `n_rows=261 / n_passed=143 / n_measurable=240 / n_ff1=143 / marginal_pct=59.58 / conditional_pct=100.0`（同文件另断言 ADR-0027 修正口径 87.16% = 380/436）；口径定义见 `experiments/emse_optimization.py::false_fix_caliber`（边际分母 = 可测行，条件分母 = passed∧可测行） | 分母语义仍易被读者忽略（`README.md` 明示"对外引用必须携带口径标签"）；权威落点已收敛到 `docs/design/repair_caliber_matrix.md` 的"false_fix 口径（权威落点）"节（编号 ⑩⑪）+ 代码 + 锁定测试，该节同时声明被 README 引用的 `docs/design/false_fix_caliber_matrix.md` **从未纳入版本控制、不是可引用路径**；但 `build_false_fix_matrix()` 实测仍返回 `source: 10-13_caliber_fallback`（§7 第 2 条）——数字本身可复算，仓内自动复算路径仍缺 |
| **（新登记）** false-fix 的**跨臂比较**被"声明通过率"混杂：`plain_llm_df` 臂仅 7/261 = 2.68% 任务声明成功 | **open** | 新增**专用敏感性分析**（T-10，零 LLM 只读存量工件）：把"成功声明率"提升为一等指标并给 Wilson CI（aitester 54.79% [48.73, 60.71] / plain_llm 87.74% [83.20, 91.18] / `plain_llm_df` 2.68% [1.31, 5.43]），比较条件口径假修复率，并构造"对照臂成功过的 pattern"匹配子集（`experiments/pass_matched_sensitivity.py`；工件 `experiments/results/emse_stats_2026-10-15/PASS_MATCHED.{md,json}`） | aitester 的 143 条 false-fix 行**即其全部 passed 行**（条件口径 100% = 143/143）；本次核验按 `tests/test_emse_optimization.py` 同口径从三个批次工件复算，三臂条件口径**均为 100%**（aitester 143/143、plain_llm 229/229、`plain_llm_df` 7/7），边际口径分别为 59.58% / 87.74% / 2.68%——**边际差几乎完全由"声明通过率"驱动**；T-10 报告的原文结论是"三臂之间边际 false-fix 的全部差异，只来自成功声明率"，且"二者在本文设计中**不可分离**"（`PASS_MATCHED.md` §1/§5 第 1 条），匹配子集样本量小、且两种口径是**不同总体、不是互补对照**（严格口径键 = pattern×difficulty×seed，对照臂成功 pattern 仅 4 个 / **29 行 / 25 可测**，检出 0；其互补总体 232 行 / **215 可测**，检出 38/215 = **17.67%**；宽松口径键 = 仅 pattern，**62 行 / 55 可测**，检出 0；其互补 199 行 / **185 可测**，检出 38/185 = **20.54%**）故只作方向性证据——**跨臂 false-fix 比较在本设计下仍不可识别** |

---

## 2. 内部效度（Internal Validity）

| 威胁 | 状态 | 缓解措施 | 残余风险 |
|------|------|----------|----------|
| LLM 版本漂移 + 温度口径 | **open** | 温度已在 provenance 记录（本次核验：`experiments/results/main_batch/benchmark_synthetic_20261006_{140906,151907,164357}.json` 三批 `temperature=0.0`）；新增 `scripts/gates/check_model_fingerprint.py` 门禁要求 `provenance.model_fingerprint.pinned is True` 才放行，且指纹已在新批次落地（本次核验：`experiments/results/emse_t08_gates_20261013/benchmark_synthetic_20261013_200729.json` 与 `experiments/results/emse_calib_synth174_20261014/s45/benchmark_synthetic_20261014_161002.json` 的 `provenance.model_fingerprint` 均 `pinned=true`、`returned_model=deepseek-flash`） | 三批 provenance **无 `model_fingerprint` 键**、`git_dirty=true`、`git_sha=b533cff1`、`model_name=deepseek-flash`（同上三文件，本次核验）；`deepseek-flash` 是**浮动别名**，实测同一 87 任务 × 3 seed 的 `plain_llm` 检出率从 1.5%（4/261）漂移到 19.2%（50/261）（`scripts/gates/check_model_fingerprint.py` 模块 docstring；同一漂移陈述亦见 `experiments/run_benchmark.py` 第 2627–2628 行附近注释）→ 历史结论**失去可复现性**；门禁默认 `max_age_days=2.0` 只扫近 2 天修改的批次，历史批次按设计不在扫描面（同文件 `collect_result_files` docstring） |
| SWE-bench Lite 基础设施故障（429 限流 / 超时）被误读为能力信号 | **mitigated** | 结论升级为**结构化判据**：`capability_conclusion = none_valid_infrastructure_failure`、`pass_rate_must_not_be_quoted = true`（`experiments/results/emse_swebench_disclosure.md`）；引用纪律明确该数据集"不得进入任何跨方法能力对比图/表"，只能出现在 Limitations 与复跑清单 | 该数据集仍为**未测**状态（"无结论"≠"负结果"）；复跑前置（配额闸）**已实现**（`src/budget/batch_quota.py` + `scripts/tools/run_preflight.py --strict`；T 轮修复其 `--check-quota` 探针缺陷），但重跑**仍未执行**（T 轮主动不跑：历史失败主因=429/超时基础设施；单批成本/墙钟远高于本批预算）（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §3 表中"SWE-bench Lite 重跑"一行状态为"未执行"）；原始工件 `experiments/results/swebench_20_summary.json` 的 `results_summary.pass_rate = "0/7 (0%)"` 仍是一等字段，只能以"不得引用"规则约束 |
| 测量伪影（意图口径 ≠ 执行口径）污染历史数字 | **mitigated** | 五起伪影全部定案并修复（第⑤起 K-5 变异生成器无效变异体，2026-10-17 补登记）；**主结论方向（编排净负贡献）修复后未变**，但 ①②③ 改变了 repair 数值结论的定性、④ 推翻了"aitester 检出恒 0"这一数值主张（逐起量级见 `docs/MEASUREMENT_INTEGRITY.md`）：ADR-0021（patch 字段围栏残留，`normalize_patch_text()` 单一权威 + 存量重放工具）、ADR-0029（包结构 import + 跨文件任务未物化，显式 dispatch + fail-closed）、ADR-0033（判分树包结构 vs 平铺 import，双布局物化 + 三段判定逐字未改）；配套 M-suite 回归与口径矩阵纪律（`docs/adr/0021-*.md`、`docs/adr/0029-*.md`、`docs/adr/0033-*.md`） | ADR-0033 §"已知局限"：双布局使判分树内同名模块出现两份，不同 import 风格**可能解析到不同文件**——当前同源、未在任何批次触发，但属结构性隐患；ADR-0029 §"已知局限"：metadata 畸形时物化不完整 → rc==2 → repair 侧记 **0.0**（"修复失败"而非"不可测"，前置 fail-closed 校验未实现，列入待立项）；ADR-0033 §"已知局限"第 3 条：修复前批次的 detection 值须一律标注"修复前下界"，**不得与修复后批次混池** |

---

## 3. 外部效度（External Validity）

| 威胁 | 状态 | 缓解措施 | 残余风险 |
|------|------|----------|----------|
| 合成任务 → 真实项目不可外推（出题人 = 判卷人） | **reduced** | ①如实登记强耦合：gold 测试 / fixed 补丁 / 任务模板**同由项目作者手写**，detection / repair 的"真值"与系统面对的题目强耦合（`docs/DATA_CARD.md` §3 第 1 条）；②建立真实缺陷阶梯 L1/L2 并登记许可状态（`docs/DATA_CARD.md` §4）；③QuixBugs 明确定位为 **L1 管道验证而非外部效度主张**（同文件 §4"用途限定"） | 正向证据**不可外推**（`docs/DATA_CARD.md` §3 第 1 条原文口径）；QuixBugs 近饱和（2025–2026 横向坐标 GPT-o1 40/40、GPT-4o 38/40、ThinkRepair / ContrastRepair 40/40）且存在**记忆污染嫌疑**，本项目可测口径 90.2%/87.8%（37/41、36/41）位于"饱和前沿之下、非 SOTA"区间（同文件 §4）；BugsInPy **零实跑**且上游无 SPDX 许可证（同文件 §4）；TestGenEval 为 CC BY-NC 4.0 非清洁许可（同文件 §4） |
| 真实基准的可用性上限与有效性缺口 | **reduced** | 必披露清单强制登记：QuixBugs 本地 = 完整 Python 子集 50 程序（任务集上限）、ULT gold 上游不一致、测试有效性缺口（`docs/emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md` §4 第 7/10/11 条） | 通过率缺口（生成套件在目标代码上）：QuixBugs **60%** / ULT lite46 **19.6%** / probe25 **20%**，失败四分类（相对导入 / 函数名不一致 / 恒红 / 非终止）（同清单 §4 第 10 条）；**ULT gold 参照作废**——官方 `test_list` **71/71** 无法在 `fixed` 通过，已排除包装/物化因素 ⇒"fixed = 正确实现"假设不成立，ULT 侧改以官方 12 模型基线（Mut@k 均值 40.21%）作**描述性**量级对照，本仓物化与官方前置块差异已量化（77 例仅 1 例翻转，1.3%）（同清单 §4 第 11 条）；`fixed` 缺失 53/261（gold 材料缺口，同清单 §4 第 1 条）；ULT 的 detection 口径适配性"另议"——生成测试零检出 0/45、0/24（`docs/DATA_CARD.md` §1 ULT 行）；Mut@k 全变异体口径下 ULT 以健全子集为分母（`docs/design/repair_caliber_matrix.md` §1 第 ⑨ 行） |
| 跨语言泛化（Python vs Java）——**无仓内 Java 实验** | **open** | 仓内只有**设计**与待办：多语言扩展缺口清单（`docs/design/multilanguage_extension.md` 列出 javac / tsc / gopls / clippy 等缺失环节）与未勾选待办"当前仅 Python，可在 Java 生态的 Defects4J 上做初步适配验证"（`docs/failure_analysis.md`）；`data/quixbugs` 内的上游 `java_*` / `correct_java_programs` 目录**未被本项目实验消费**——加载与实验口径均为 Python 子集（`docs/DATA_CARD.md` §4；`docs/emse/EMSE_QUIXBUGS_SPECIR_EXPAND_PREREG_2026-10-14.md` §7 记"QuixBugs 本地即完整 Python 子集（50 程序）"） | 全部结论仅适用于 **Python 函数级任务**；仓外 Java 结果**是他人工作，构成本项目三角互证的效力为零**：`docs/adr/0025-oracle-context-ablation-tier.md` 引用的 ASE 2025 研究已于 **2026-10-16 一手核验**（DOI 10.1109/ASE63991.2025.00031；13,866 条预言 / 135 个 Java 项目 / mutation score 43% vs 人类 45% 与摘要逐位吻合；`docs/citation_allowlist.txt` 已清空、零豁免），且该 ADR §"负面/风险"明示"ASE 研究为 Java 项目，向 Python synthetic 的外推未证"——核验状态已更正；**外部效度限制不因核验而解除**（仓内仍无 Java 实验） |

---

## 4. 结论效度（Conclusion Validity）

| 威胁 | 状态 | 缓解措施 | 残余风险 |
|------|------|----------|----------|
| 因果主张"检出优先 → 更少假修复"未与干预成分解耦 | **reduced**（T 轮 2026-10-18 三格×2 seed 指纹级复现） | 双开关语义：`DETECTION_FIRST_ENABLE`（路由 + 再生成计数 + 强化段落）与 `DETECTION_FIRST_SECTION_ENABLE`（**只控制提示词，不控制路由**；定位以函数名 `_detection_first_regenerate_entry` / `_detection_first_section` / `_over_red_section` 为准，`src/graph/nodes.py`，T 轮起不再引用易漂行号）；**三格消融已执行并指纹级复现**（2026-10-09 RT1 单 seed 批 + T 轮 3 格×2 seed：C1 plain_llm 9/12、C2 RT1 10/10、C3 df 全协议 24/27；**文本效应 C3−C2 = +16.1pp / +19.5pp（McNemar p=0.000519 / 1.5e-05）**，采样效应 C2−C1 = +1.1pp / −2.3pp 不显著 → "+43pp 协议包"归因中"多一次采样"成分可忽略） | 残余：① T2 为单臂逐格、2 seed、synthetic 单数据集、单模型；② 与 R-P0-2 三臂主批次协议不同，不得混池；③ 六格（首跑中止后统一重跑）均关闭了批后 `ENABLE_MUTATION_SCORING`（仅辅助测量，detection 口径不变；执行修订见 `PREREG_CONTINUATION.md`）；④ harness 漂移（logic 档自 R-P0-2 起新增 5 个开关、输出 token 份额差异）的披露位置：B1 见 `t_round_b1_protocol_text_20261018/README.md` 的旧批并排/执行修订节；B2 见其 `ANALYSIS_REPORT.json` 的 `provenance_drift` / `profile_preset_drift` 两段（B2 工件落盘后回填） |
| 多重比较未校正导致假阳性膨胀 | **reduced** | 按**指标族**独立做 BH-FDR（detection 族 / repair 族各自构成 FDR 分母，不跨指标混池），并新增 `fdr_adjusted_p` / `fdr_rejected` 与报告 q 值列（`experiments/statistical_analysis.py` 的 `run_all_statistics` 指标族循环）；实跑三种子合并批次（2026-10-19 按标准 BH 重算，4 位小数下 q 值不变）：detection 两比较 q=0.0000（FDR 后仍显著）、repair 两比较 q=1.0000（零效应如实呈现）（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §1.1 与 §4）；聚类稳健敏感性三组对比校正后方向与显著性全部保持（`experiments/results/main_batch/statistical_report_3seed_pooled.md` §模板聚类稳健敏感性分析：保守 χ²_adj = 33.06 / 6.44 / 9.08，模板级符号检验 p = 4.8e-07 / 0.0018 / 0.0169） | **标准 BH** 实现：q_(i) = min(1, min_{j≥i} m·p_(j)/j)（逆序累积最小、单调化；`experiments/statistical_analysis.py::bh_fdr_correct`）——q 值只由 p 值排序位置决定，不依赖 α 的拒绝位置。**2026-10-19 Z 轮 F01 勘误：旧实现非标准（拒绝集按"最大被拒绝 p"与名次回填、未拒绝集 q=1.0，q 依赖 α 的拒绝位置；例 [0.03,0.20,0.30] 旧 q 与 rejected 矛盾），现行代码已改为标准 BH；主批按标准 BH 重算后 4 位小数下的 q 引用不变、拒绝集合不变**；**次要终点不校正**，按预注册"标注探索性"（`docs/preregistration.md` §统计分析计划："主终点优先呈现；次要终点标注'探索性'；不得因结果切换主终点或事后增删检验"），而 mutation / 成本 / 定位 / 规约等次要读数数量众多；此外"首要口径"从 passed 扩到 detection/repair 族属**见数后**的口径扩展，须按优化记录如实呈现（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §1.1"优化前"列） |
| "三种子"的语义被误读为三次独立模型重复 | **reduced** | 语义在代码内显式登记：`--seed` 只作用于**任务采样**与缓存命名空间（`AITESTER_CACHE_NAMESPACE=seed<N>`），**不传 LLM API**（`experiments/run_benchmark.py` 第 2944–2956 行注释；本次核验三批 provenance `cache_namespace` 分别为 `seed42/43/44`） | "三种子"= 三次任务抽样 × 三个缓存命名空间（**跨种子真实调用、同种子缓存重放**），不是固定任务集上的三次随机模型运行；跨种子的同模板任务为**相关观测**：31 模板簇 vs 261 观测/臂，ICC 0.153–0.299、DEFF 3.42–5.53、n_eff 90.5–152.7（`experiments/results/main_batch/statistical_report_3seed_pooled.md` §模板聚类稳健敏感性分析）→ 逐对 McNemar 的独立性假设**名义偏乐观**，论文须并列报告校正后结果 |

---

## 5. OPEN 项逐条处置（未缓解原因 → 缓解实验 → 论文收缩口径）

### 5.1 `detection_rate` 作为"测试质量"代理（构念效度，open）

- **为何未缓解**：本数据集上唯一可用于"质量"外部校标的变异得分**已饱和**——权威工件 `experiments/results/main_batch/mutation_detection_correlation.md` 聚合 `experiments/results/main_batch/` 下全部 10 个批次 JSON（配对 n 556 / 609 / 571），分层均值 0.87–1.00；`plain_llm_df` 的分层方向甚至为负（Δ均值 = −0.0098，判定"无鉴别力（饱和）"），`aitester` 与 `plain_llm` 仅弱正（Δ均值 = +0.1263 / +0.0232）（同文件第 15–17 行）。**注意口径**：`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §2 此前引用的"R-P0-2 三种子 n=261/臂"表（Δ均值 = +0.0456 / +0.0290 / −0.0036）已被该文件 2026-10-15 修订的口径说明**明确取代并删除**——两表人群不同（10 批次 vs 三种子），本文只引用前者的权威工件。饱和指标无法充当校标，因此"代理"主张缺少可用的收敛证据。
- **什么实验/分析会缓解**：把 detection 与**非饱和**外部信号配对——ULT 全变异体 Mut@k（健全子集口径，`docs/design/repair_caliber_matrix.md` 第 ⑨ 行）已具备可复算入口，但该子集同时存在有效性缺口（生成套件在目标代码上通过率 19.6%/20%，`docs/emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md` §4 第 10 条）与 gold 参照作废（同清单 §4 第 11 条）；可行的下一步是 E7 人工复核建立 detection 的**人工校标**（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §3 明记其为"唯一能建立 detection 外部校标的动作"）。
- **若持续 open，论文必须如何收缩**：detection **只能**被表述为"本基准上的检出信号（protocol-level signal）"，不得作为测试质量的通用代理；与 mutation 相关性的数字必须作为**构念效度的反证证据**如实披露并附"解读纪律"（不得单独引用、须与分层均值并列）（`experiments/results/main_batch/mutation_detection_correlation.md` 第 8–11 行；`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §2 结论 3）。

### 5.2 false-fix 跨臂比较被"声明通过率"混杂（构念效度，open）

- **为何未缓解**：三臂的**条件** false-fix 均为 100%（本次复算：143/143、229/229、7/7；T-10 报告 §2 同值并附 Wilson CI 100% [97.38, 100] / [98.35, 100] / [64.57, 100]），差异全部来自边际分母中的"声明成功"比例（54.79% / 87.74% / 2.68%，`experiments/results/emse_stats_2026-10-15/PASS_MATCHED.md` §1）。`plain_llm_df` 仅有 7 条 passed 行，任何"以 passed 为条件的跨臂比较"都无功效可言。T-10 报告的判定是：**边际 false-fix 的全部差异只来自成功声明率**，"二者在本文设计中**不可分离**"（同报告 §5 第 1 条），因此该报告**直接否证**"detection-first 协议降低了假修复"的因果解读（同报告 §1 关键观察、§5 第 2 条）。
- **什么实验/分析会缓解**：T-10 已交付**描述性**缓解（成功声明率一等指标 + 条件口径 + 模板匹配子集：**严格口径**键 = pattern×difficulty×seed，**29 行 / 25 可测**检出 **0（0.00%）**，其互补总体 232 行 / **215 可测**、检出 38/215 = **17.67%**；**宽松口径**键 = pattern，**62 行 / 55 可测**检出 **0（0.00%）**，其互补 199 行 / **185 可测**、检出 38/185 = **20.54%**；**严格与宽松是不同总体、不是互补对照**，两组数字不可拼成同一 2×2 表；同报告 §3）；但报告自陈"需要 2×2 消融（协议文本开关 × 再生成预算）才能把'文本效应'与'行为效应'分离；本报告不替代该实验"（同报告 §5 第 4 条），即 §5.5 的消融才是根治路径（**T 轮已执行**：3 格×2 seed 指纹级复现见 §5.5）。
- **若持续 open，论文必须如何收缩**：**不得**声称检出优先协议或完整系统在"假修复"上优于对方；只能报告"声明通过率"与"条件 false-fix = 100%"这两个事实，并把边际 false-fix 差异显式归因于声明通过率差异。`README.md` 的 false_fix 引用纪律（必须携带口径标签）是**必要但不充分**的缓解；口径权威落点见 `docs/design/repair_caliber_matrix.md` 的"false_fix 口径（权威落点）"节（⑩⑪）。

### 5.3 LLM 版本漂移 + 温度口径（内部效度，open）

- **为何未缓解**：主批次跑在指纹功能存在之前，provenance 无 `model_fingerprint` 键且 `git_dirty=true`（本次核验三批 JSON），模型为浮动别名 `deepseek-flash`；漂移**已实测发生**（同任务同 seed 的 `plain_llm` 检出 1.5%→19.2%，`scripts/gates/check_model_fingerprint.py` docstring），而门禁对历史批次按设计不设防（默认只扫近 2 天）。指纹功能 2026-10-13/14 批次起已落地（见 §2 表），但**无法回溯**补写主批次——缺口只在 2026-10-06 及更早的结果上。
- **什么实验/分析会缓解**：在指纹门禁下重跑主批次（`pinned=true`），并把新旧批次的差异作为"别名漂移敏感性"单独报告；在此之前，任何 confirmatory 主张都应视为不可复现。仓内已有的替代路径是报告 JSON 的 `env_snapshot`（含开关与温度）与 `git_sha`，但 `git_dirty=true` 意味着 sha 不足以复现代码态（`experiments/results/main_batch/statistical_report_3seed_pooled.md` §AK 勘误 1）。
- **若持续 open，论文必须如何收缩**：把主批次结果表述为**浮动别名在特定时间窗内的快照**；禁止任何"跨运行可复现"的措辞；`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §3"复现包钉 seed/model/temperature/dataset-version"未执行这一事实须进 Limitations。

### 5.4 跨语言泛化（外部效度，open）

- **为何未缓解**：仓库内**不存在** Java（或其他非 Python）实验；只有设计文档（`docs/design/multilanguage_extension.md`）与未勾选待办（`docs/failure_analysis.md`）。QuixBugs 上游自带的 Java 目录未被加载器消费（`docs/DATA_CARD.md` §1 记"QuixBugs（Python 子集，完整 50 程序）"；`docs/emse/EMSE_QUIXBUGS_SPECIR_EXPAND_PREREG_2026-10-14.md` §7 记"QuixBugs 本地即完整 Python 子集（50 程序）"）。
- **什么实验/分析会缓解**：实现一个非 Python 数据集适配器并跑 L1 冒烟（最小可判性验证），或按 `docs/design/multilanguage_extension.md` 的缺口清单补齐工具链后跑 Defects4J；低成本替代是**明确写下不主张**，并把"跨语言"列入 future work（诚实降级优于仓促外推）。
- **若持续 open，论文必须如何收缩**：所有结论限定于"Python 函数级任务"；**不得**引用仓外 Java 研究作为本系统的三角互证（`docs/adr/0025-oracle-context-ablation-tier.md` 的 ASE 2025 引用已于 2026-10-16 一手核验、`docs/citation_allowlist.txt` 零豁免，且同 ADR 明示 Java→Python synthetic 外推未证——外推限制不因核验而解除）；题目 / 摘要 / 贡献列表中的泛化措辞须逐处加限定语。

### 5.5 因果主张"检出优先 → 更少假修复"（结论效度，**reduced**——T 轮 2026-10-18 指纹级三格×2 seed 复现）

- **为何未缓解**：干预是**协议包**而不是单一变量——`DETECTION_FIRST_ENABLE` 同时改变路由（首轮全绿 → 再生成）、再生成计数与提示词段落三者（`src/graph/nodes.py` 的 `_detection_first_regenerate_entry` 与强化段落构造；`docs/adr/0015-detection-first-protocol.md` 决策 2–4；T 轮起以函数名定位，不引用易漂行号）。可用的因子设计是 `DETECTION_FIRST_ENABLE` × `DETECTION_FIRST_SECTION_ENABLE` 的**三格**：第四节"无再生成但有强化段落"在结构上不可达——`_detection_first_section()` 先判 section 开关，再要求 `_detection_first_regenerate_entry(state)` 为真，而后者以 `detection_first_enabled()` 为前提（`src/graph/nodes.py` 的 `_detection_first_section_enabled` / `_detection_first_regenerate_entry` / `_detection_first_section`）。RT1 消融正为此设计（`_detection_first_regenerate_entry` / `_detection_first_section` 附近 docstring）。**勘误：该消融并非未执行**——2026-10-09 已有 RT1 单 seed 批（`experiments/results/e6_a1_batches/rt1_no_reinforcement_seed42/`，并入 BASELINE `benchmark.rt1_sampling_control`），T 轮又以干净切点 + 指纹 + 预注册做了 3 格×2 seed 复现（工件 `experiments/results/t_round_b1_protocol_text_20261018/`）。
- **已执行的缓解**：三格对照（`DETECTION_FIRST_ENABLE` × `DETECTION_FIRST_SECTION_ENABLE`，其余对齐采样次数与调用预算）已两轮执行；主终点 = detection。T 轮结果：文本效应 C3−C2 = **+16.1pp（seed42，b/c=15/1，p=0.000519）/ +19.5pp（seed44，b/c=17/0，p=1.5e-05）**、采样效应 C2−C1 = **+1.1pp / −2.3pp（均不显著）**，2/2 seed 同向 → "多一次采样"不解释 +43pp，协议文本是主导成分。
- **现在的可辩护表述（T 轮起）**：+43pp 的归因可写到"协议包中的**提示词文本**是主导成分（两 seed 文本净效应 +16~+20pp，McNemar 均显著；多一次采样效应 ≤|2.3|pp 不显著）"；仍**不得**主张假修复减少（见 §5.2），也不得把单臂逐格复现外推为 R-P0-2 三臂主批次的等预算结论。

---

## 6. 与 EMSE 五项评审标准的映射

**Relevance（相关性）**：本文档把"负结果 + 归因方法学"作为一等贡献来保护——完整编排在检出口径下显著劣于纯提示协议 −28pp（`experiments/results/main_batch/statistical_report_3seed_pooled.md` §首要结论：δ=−0.279 [−0.348,−0.209]），且该方向在模板聚类校正（χ²_adj=9.08、符号检验 p=0.0169，同文件 §模板聚类稳健敏感性分析）与 21 行缺失双界（最好情形仍 −22.2pp、p=1.7e-08，同文件 §AK 勘误 2）下均保持——这正是 EMSE 读者关心的"多智能体测试生成到底有没有增益"。

**Significance（重要性）**：三类可迁移贡献——①"意图口径 ≠ 执行口径必产伪影"的四次同族复现（`docs/adr/0029-*.md` 表格、`docs/adr/0033-*.md` §后果）；②口径矩阵纪律（`docs/design/repair_caliber_matrix.md` §3）；③"先红后绿"协议在强模型下 +43pp 的检出收益（`experiments/results/main_batch/statistical_report_3seed_pooled.md`）。三者都不依赖任何单一批次的运气。

**Technical quality（技术质量）**：统计侧——McNemar + 贝叶斯 Dirichlet 配对 + 按指标族的 BH-FDR（`experiments/statistical_analysis.py` 的 `run_all_statistics` 指标族循环与标准 BH `bh_fdr_correct`）+ 模板聚类 DEFF 与符号检验 + 缺失行最好/最坏双界；测量侧——fail-closed（rc==5 / 材料缺失记 None，`docs/adr/0029-*.md` 决策 3）、五起伪影的回归锁与 M-suite、指纹门禁（`scripts/gates/check_model_fingerprint.py`）。同时本文档把**未做到的部分**（§5 五条、§7）与做到的部分并列，避免"技术质量"被过度主张。

**Scholarship（学术规范）**：预注册（`docs/preregistration.md`，含"既有结果的诚实声明"节与执行记录表）、ADR 决策账本（`docs/adr/README.md` 索引，含 ADR-0033 作为**补登记**的时间序诚实说明）、派生工件不入库的理由说明（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §5）、以及上游失效的主动披露（ULT gold 71/71 失败 → 参照作废，`docs/emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md` §4 第 11 条）。

**Presentation（可读性/可复核性）**：口径标签 + 分子分母 + 可复算命令三件套（`docs/design/repair_caliber_matrix.md` §1 表头即 schema）；中英双语门禁（`scripts/gates/check_bilingual_docs.py --strict`）；诚实用语在文档层的统一（"gold 材料独立裁决（自动化 oracle，无人工参与）"，`README.md`）。本文档本身即按"一个数字一个源路径"的格式书写，供审稿人逐格抽查。

---

## 7. 不可核验与未核验事项（诚实清单）

1. **E7 未执行、无 Kappa 工件**：全仓 `grep -rin "kappa" --include=*.md docs/ README.md` 在本文档落盘**之前**仅 3 行命中，且全部是"不存在 / 未执行"陈述（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` 2 处、`README.md` 1 处）。本文档与 `docs/HUMAN_ADJUDICATION_PROTOCOL.md` 落盘后该 grep 会新增**说明性**命中（协议如何计算 Kappa），但**没有**任何一行主张 Kappa 工件存在；执行协议见 `docs/HUMAN_ADJUDICATION_PROTOCOL.md`。
2. **false_fix 口径的仓内自动复算路径仍缺**：`README.md` / `README.en.md` / `BASELINE.yaml` 引用的 `docs/design/false_fix_caliber_matrix.md` **在仓库中不存在**（`find docs -name "*caliber*"` 只返回 `docs/design/repair_caliber_matrix.md`；`git log --all -- docs/design/false_fix_caliber_matrix.md` 无输出）——`docs/design/repair_caliber_matrix.md` 新增的"false_fix 口径（权威落点）"节解释了原因：该路径**从未纳入版本控制**（被 `.gitignore` 忽略），故**不是可引用路径**，权威落点改为"该节 + 代码 + 锁定测试"。实测 `experiments/emse_optimization.py::build_false_fix_matrix()` 仍返回 `"source": "10-13_caliber_fallback"`，原因是 `_load_main_batch_rows()` 只接收 `timestamp <= 2026-10-02` 的批次（同文件注释将该批称为"R-P0-2 主批次"），而 R-P0-2 三种子批次的时间戳为 2026-10-06，因此**自动复算分支对 R-P0-2 人群不会触发**。**59.58% / 100% 的两个分母经本次核验可从三个 10-06 工件直接复算得到**（aitester 143/240 与 143/143），但该复算**不经过**仓内矩阵函数。
3. **mutation × detection 的口径已在源文件内改版（本文按新版引用）**：`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §2 于 2026-10-15 修订中把原"R-P0-2 三种子 n=261/臂"表**替换**为"批次文件数 = 10"表（Δ均值 = +0.1263 / +0.0232 / −0.0098），并在口径说明中声明旧表**已被取代、两表人群不同不得互相替换**；该新表与权威工件 `experiments/results/main_batch/mutation_detection_correlation.md` 逐格一致（并有门禁 `scripts/gates/check_artifact_doc_consistency.py` 对账）。本文因此只引用 10 批次口径的 Δ 值；`README.md` / `BASELINE.yaml` 的三种子口径 detection 44.8% / 15.8% / 1.5% 是**另一总体**（任务检测率），不受该表改版影响，但同样**不得**与 mutation 交叉验证的 Δ 值混用。
4. **派生工件未入库（余两项）**：`experiments/results/emse_swebench_disclosure.md` 被 `.gitignore` 第 158 行 `experiments/results/**` 忽略且未被 git 跟踪；T-10 敏感性分析的 `experiments/results/emse_stats_2026-10-15/PASS_MATCHED.{md,json}` 同样位于被忽略目录（`experiments/results/**`）。两者按设计可由源工件零 LLM 再生（`docs/emse/EMSE_OPTIMIZATION_2026-10-15.md` §5 同口径；T-10 再生入口 `experiments/pass_matched_sensitivity.py`）。（`experiments/results/main_batch/mutation_detection_correlation.md` 原列于此；已随 2026-10-16 批次按 `main_batch/` 白名单入库，与同目录既有 11 份报告同口径。）
5. **T-10 匹配子集只作方向性证据**：模板匹配子集样本量小（对照臂成功 pattern 仅 4 个；严格口径 29 行、宽松口径 62 行），报告自陈"仅作方向性证据，**不作因果声明**"（`experiments/results/emse_stats_2026-10-15/PASS_MATCHED.md` §解读纪律与 §5 第 4 条）——本文引用其数字时一律附此限定。
6. **ULT 侧无 gold 锚定结论**：官方 `test_list` 71/71 在 `fixed` 上失败 ⇒ gold 参照作废（`docs/emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md` §4 第 11 条），本报告因此**不引用**任何"相对 gold 的 ULT 上界"数字。
7. **SWE-bench Lite 的 `pass_rate` 不得引用**（`experiments/results/emse_swebench_disclosure.md`"引用纪律"），本报告只引用其结构化判据与计数。
8. **仓外数字的核验状态（两条分开表述）**：① `docs/adr/0025-oracle-context-ablation-tier.md` 引用的 ASE 2025 Java 研究已于 **2026-10-16 一手核验**（DOI 10.1109/ASE63991.2025.00031；13,866 条预言 / 135 个 Java 项目 / 43% vs 45% 与摘要吻合），不再挂"未一手核验"标注——但 Java→Python synthetic 的外推限制仍成立（同 ADR）；② `docs/DATA_CARD.md` §4 QuixBugs 横向坐标中的 `claude-code` 适配器 resolve ≈80.75% 仍是**未一手核验**的仓外聚合数字（该文件自注"聚合来源，个别数字待原文复核"）——引用时仍标注未一手核验。
9. **本次核验所做的最小复算**：三批 JSON 的 provenance 字段读取、三批 JSON 的 false-fix 双口径复算（结果见 §1 第 3 行）——均为只读操作，未改动任何工件。
