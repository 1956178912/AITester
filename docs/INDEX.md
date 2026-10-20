# AITester 文档索引（Documentation Index）

> 最后更新：2026-10-20（AB-17 轮：价目表**表级读侧准入**分册入库——**"这个文件读出来算不算一张表"一处写一遍**（AB-16 两谓词的共同上游「文件 → `models` 层」）：同一份坏表七个读点读出七种记法（`src` 缓存包装七种坏读同一句「结构不符（缺 models dict）」并写"键在值为 null"；`emse_stats_extensions` 七种坏**全部直接崩**；`emse_stats_report` 六个中文短语只在 stderr、归因全落 `model_unregistered`；`spec_examples_generator` 文件级只进日志且 `models` 层 pass-through；`statistical_analysis` 文件路径全程无痕；`run_b8_injection` 的 `is_file()` 前置守卫静默退回内置价；检索层 `.get` 的 `is None` 让"键缺席"与"值 null"共用一句）。处置为 `table_read_reason` / `load_table_json` / `models_layer` / `load_table_models` 四共享助手收口、七处读点全部接线、检索层四处改 `not in`，两处设计性读法差异记录在案；真批次读数零改变；**26 例锁 + 8 处锚点逐处转红**（collected 恒 484、sha256 字节还原），五处既有锁改写净 0 例；全量 10283 passed / 5 skipped / 0 failed，行 97.24% / 分支 93.84%（+20 行 / +15 弧，未覆盖 524 与偏弧 437）；此前 AB-16 轮：价目条目的准入域分册入库——**"什么算一个价格数字、什么算一张合格条目"一处写一遍**（AB-15 §5.2 交来的一族）：五套准入域改前实测（生产 `_as_non_negative_float` 收下 `nan`/`inf`、spec/report 的 `float()` 直收把 `True` 当 1 / 编出 `-1.0` 负数金额 / `[1.0]` 抛 `TypeError`、ext 对空条目/`null` 价折成 0.0 部分和、analyze 的本地拒绝词汇不管非有限、statistical 的 `p >= 0` 收下 `inf`），同一张条目四处四种结论、spec 真值非对象 `models` 还抛 `AttributeError`；处置为 `price_block_reason` + `entry_block_reason` 两谓词收口、六处消费点全部接过去，真批次读数零改变；此前 AB-15 轮：成本拒绝的呈现与归因分册入库——**被拒绝的金额不得披着金额的形状出现**（`$None` / 折叠出来的 `$0.0` / 部分和冒充全额），且**"为什么没有金额"必须与判定同源**；三种"拒绝穿金额衣服"的通道与四套归因词汇由前置实测坐实，处置为共享机制词汇 + `_price_admission` 判定/归因同源 + 六处接线（共享词汇 + 五个消费站点），真批次读数零改变；此前 AB-14 轮：币种判定收口为单一谓词并让五站点全部接过去的实测与处置分册入库——"同一个『这笔钱是不是美元』的判断仓内写了四遍且四遍互不相同、第五遍根本没写"由前置普查坐实，本轮首次改动 `src/`；此前 AB-13 轮：价目表与币种口径的实测与处置分册入库——`total_usd` 声明美元而实现不看币种这类"字段名声称、实现不判定"的缺陷由前置复测新坐实；此前 AB-12 轮：AB-12b/AB-12c/AB-12d/AB-12e 四份分册入库（行集折叠、非对象 trace 行、缺席按机制点名、价目表 `None` 哨兵），该行当时未随本册头部刷新，属同一类存量漂移；此前 AB-11 轮："缺席有三种，挤在一个桶里就只剩一种"这一族的实测与处置报告入库，AB-10 余下 3 处登记全部处置、其中两行原文共留四件机制继续登记（站点 a 三件本轮 0 件处置、站点 c 一件）；此前 AB-10 轮："缺席 / 读不动不得报成零命中 / 一致 / 未要求"这一族在分析侧的实测与处置报告入库，AB-9 普查余下 5 处登记站点处置 2 处、仍留 3 处；此前 AB-9 轮：`experiments/` 层 68 处 `json.loads` 按解析器返回域的普查报告入库，撤销 AB-8 边界登记中的"未普查"一项；此前 AB-8 轮：JSONL 非对象行与主键域崩溃类收口报告入库；此前 Z 轮：第四轮第三方全量静态审查 20 项修复收口报告入库；Y4 轮：第三轮评审 §15 八项待澄清问题的权威回应入库；Y/Y2/Y3 三轮修复覆盖率审计报告与可复用审计工具登记入核心文档清单。AB-1 / AB-5 两份报告入库时本行未随之刷新，属存量漂移，此处一并登记）
>
> 本页是全部 Markdown 文档的**导航入口**：先按角色给最短阅读路径，再给核心文档清单
>（每份一句话说明）。本页的全部链接由 `scripts/gates/check_doc_links.py --strict`
> 做静态校验（零网络：只验证文件与锚点存在性，不请求外链）。新增或改名核心文档时，
> 请同步更新本页。
>
> 英文版：[INDEX.en.md](INDEX.en.md)

## 1. 快速入口

| 我想…… | 从这里开始 |
|---|---|
| 10 分钟跑通系统 | [QUICKSTART.md](../QUICKSTART.md) |
| 了解项目定位与核心主张 | [README.md](../README.md) |
| 参与贡献 / 跑门禁 | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| 复现实验 / 核对数字 | [REPLICATION.md](../REPLICATION.md) → [BASELINE.yaml](../BASELINE.yaml) |
| 审阅效度与声明边界 | [docs/VALIDITY.md](VALIDITY.md) → [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md) |
| 查投稿材料（EMSE） | [docs/study/OPTIMIZATION_2026-10-15.md](emse/OPTIMIZATION_2026-10-15.md)（投稿清单/骨架为本地工件，不入库） |

## 2. 按角色阅读路径

### 2.1 新贡献者（约 30 分钟）

1. [README.md](../README.md)：系统定位、能力边界与快速开始命令。
2. [QUICKSTART.md](../QUICKSTART.md)：零 LLM 冒烟、单文件测试、批量基准与消融入口。
3. [CONTRIBUTING.md](../CONTRIBUTING.md)：分支 / 提交 / 门禁链 / 基线数字单一来源约定。
4. [docs/troubleshooting.md](troubleshooting.md)：常见卡点分诊表（按症状 → 根因 → 解决步骤）。
5. [docs/adr/README.md](adr/README.md)：架构决策索引（为什么这样设计）。
6. [docs/api_reference.md](api_reference.md)：模块与公共 API 速查。

### 2.2 审稿人 15 分钟路径

1. [docs/VALIDITY.md](VALIDITY.md)：构念 / 内部 / 外部 / 统计结论四类效度威胁与缓解。
2. [docs/preregistration.md](preregistration.md)：E1–E8 预注册（E5 探索性；E6–E8 增补，判定口径先声明后取数）。
3. [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md)：声明 → 证据 → 范围对账表（含被反驳声明）。
4. [docs/MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md)：测量伪影的形态、检测与修复方法论。
5. [BASELINE.yaml](../BASELINE.yaml)：全部当前数字的机器可读单一来源。
6. [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md)：第二轮独立系统性评审（含遗留项与处置）。
7. [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md)：第三轮独立系统性评审（14 项核心声明逐位复验；A-01..A-20 建议与同日收口状态）。
8. [docs/reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md](reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md)：第三方独立审查（Windows）23 项修复收口报告（P0 A08 + P1/P2 逐项矩阵、M1–M9 复跑与残余风险）；§5 追加第二轮复核残留 A07/A09/A10 补修记录（2026-10-19）。
9. [docs/reviews/REVIEW_CLARIFICATIONS_2026-10-19.md](reviews/REVIEW_CLARIFICATIONS_2026-10-19.md)：第三轮评审 §15 八项待澄清问题的**权威回应入口**（5 项已闭合、2 项待项目方裁定、1 项未做且有明确代价；每项给工件路径 + 复算命令 + 能力边界）。
10. [docs/reviews/THIRD_PARTY_REVIEW_2026-10-19_FIX_CLOSURE.md](reviews/THIRD_PARTY_REVIEW_2026-10-19_FIX_CLOSURE.md)：**第四轮第三方全量静态审查（2026-10-19，Windows，提交 `55bb711`）20 项（P0=0/P1=14/P2=6）修复收口**——逐项矩阵、报告 §M1–M9/M11 验收复跑、独立复算、日期化勘误纪律与残余风险。

### 2.3 复现者

1. [REPLICATION.md](../REPLICATION.md)：复现包构成、工件清单与还原步骤。
2. [reproduce.sh](../reproduce.sh)：主批次复现入口（消耗 LLM 配额，勿自动触发）。
   数据集分支 fail-closed：`--dataset examples|swe_bench|synthetic` 之外的值直接报错退出；
   主批合成数据集复现用 `bash reproduce.sh --dataset synthetic --full`
   （= 87 任务 / `--max-pattern-repeat 2` / seed 42 / 主批三臂；
   三种子协议见 `experiments/run_main_batch.py`，详见 REPLICATION.md §5）。
3. [docs/usage_examples.md](usage_examples.md)：单文件 / 批量 / 消融 / 成本预算的完整用法。
4. [docs/performance_guide.md](performance_guide.md)：性能参数、预算口径与调优。
5. [docs/troubleshooting.md](troubleshooting.md)：环境 / 依赖 / Docker / RAG 卡点。
6. [三种子主批次统计报告](../experiments/results/main_batch/statistical_report_3seed_pooled.md)：关键统计结论的证据源（实验工件，非门禁文档）。

### 2.4 维护者

1. [docs/PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md)：状态与决策登记册（已完成 / 遗留 / 阻断）。
2. [docs/adr/README.md](adr/README.md)：ADR 索引（新增架构决策时在此追加一行）。
3. [CHANGELOG.md](../CHANGELOG.md)：逐批变更日志（历史快照，不作链接门禁的扫描面）。
4. [docs/HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md)：人工裁决协议（抽样框 / 量表 / 双人独立 / 冲突解决）。
5. `docs/study/SUBMISSION_CHECKLIST_2026-10-15.md`：投稿材料收口清单（**本地工件，不入库**；可复算内容以 [OPTIMIZATION_2026-10-15.md](emse/OPTIMIZATION_2026-10-15.md) 为准）。
6. [scripts/gates/](../scripts/gates/)：全部门禁脚本目录（新增门禁在此目录，并接 Makefile / CI）。

## 3. 核心文档清单

### 3.1 定位、效度与测量完整性

| 文档 | 一句话说明 |
|---|---|
| [docs/VALIDITY.md](VALIDITY.md) | 效度威胁模型：构念 / 内部 / 外部 / 统计结论四类威胁与逐项缓解。 |
| [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md) | 声明 → 证据 → 范围对账表；含 contradicted 声明清单（编辑初筛用）。 |
| [docs/MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md) | 五起测量伪影的"口径分叉"方法论：逐起给分叉口径 / 检测 / 量级 / 修复 / 结论是否翻转；另有 §5–§10 六则按轮附录（L / M / T / AA / AB-7 / AB-8）。 |
| [docs/preregistration.md](preregistration.md) | E1–E8 验证实验预注册（E5 探索性，E6–E8 增补）：判定口径、样本量与停止条件先声明后取数。 |
| [docs/DATA_CARD.md](DATA_CARD.md) | 数据集卡：来源、规模、许可、污染视角与适用边界。 |
| [MODEL_CARD.md](../MODEL_CARD.md) | 模型卡：模型版本、指纹口径、成本与已知局限。 |

### 3.2 系统设计与 API

| 文档 | 一句话说明 |
|---|---|
| [docs/algorithm_design.md](algorithm_design.md) | 系统架构与算法设计总览（图 / 节点 / 修复循环 / 检测门）。 |
| [docs/api_reference.md](api_reference.md) | 模块与公共 API 参考（智能体 / 工具 / 工作流 / 数据集 / 配置）。 |
| [docs/adr/README.md](adr/README.md) | 架构决策记录索引：每条 ADR 的编号、状态、一句话摘要与关联模块。 |
| [docs/design/](design/) | 设计文档目录：预注册、实验设计、链路设计与已冻结方案。 |
| [docs/design/cross_file_repair.md](design/cross_file_repair.md) | 跨文件修复设计（多文件任务的上下文构造与落盘约束）。 |
| [docs/design/repair_caliber_matrix.md](design/repair_caliber_matrix.md) | repair 口径矩阵：不同判定口径下的修复率对比与选择依据。 |
| [docs/design/multilanguage_extension.md](design/multilanguage_extension.md) | 多语言扩展架构预留（语言适配层与准入条件）。 |
| [docs/design/docstring_anchor.md](design/docstring_anchor.md) | P1 独立 docstring 规格锚：两臂设计、锚表口径、预注册与三臂实测结论（`not_confirmed`）。 |
| [docs/design/misguided_effective_metric.md](design/misguided_effective_metric.md) | misguided/effective 逐测试三分度量（ISSTA'26 操作化）：分类树、分母、执行口径与已知限制。 |
| [docs/design/oracle_quality_metric.md](design/oracle_quality_metric.md) | 确定性规约 oracle 质量度量（A-05）：四分类、注入 fidelity、检出贡献与判分耦合限制。 |
| [docs/design/e2e_probe_matrix.md](design/e2e_probe_matrix.md) | 全功能端到端探针矩阵：功能清单化验证、零 LLM 默认与真 LLM 按需、报告与边界。 |
| [docs/design/smt_witness_batch_plan.md](design/smt_witness_batch_plan.md) | z3 SMT 见证层最小启用批次：设计、判定规则与 T 轮执行记录（机制层 pass；pre/post-fix 口径）。 |
| [docs/design/evaluation_integrity_checklist.md](design/evaluation_integrity_checklist.md) | 评测诚信 checklist v1（P3）：IC-1..IC-8 工件级静态诚信检查 + 可执行校验器（`experiments/eval_integrity_check.py`），跑批后/引用前/跨批对比前必跑。 |
| [docs/design/cross_file_plan_wiring_prereg.md](design/cross_file_plan_wiring_prereg.md) | D3b 跨文件图通路接线：下游消费点定位、两阶段双开关方案与预注册；**Step A 已实装（双开关默认关，OFF/OFF 与历史逐位一致）**，Step B / AB1 待做。 |
| [docs/COST_MODEL.md](COST_MODEL.md) | 成本模型：批后处理墙钟可观测（StageTimer/分位/阈值）、预算口径与批跑建议。 |
| [docs/dependency_exemptions.md](dependency_exemptions.md) | 依赖豁免登记表：每个豁免的替代方案与到期复核条件。 |
| [docs/threat_model.md](threat_model.md) | 威胁模型：T1–T8 威胁、攻击面与现有缓解措施。 |

### 3.3 使用、运维与安全

| 文档 | 一句话说明 |
|---|---|
| [QUICKSTART.md](../QUICKSTART.md) | 快速开始：安装、配置、单文件测试、批量基准与消融命令。 |
| [docs/usage_examples.md](usage_examples.md) | 用法示例：基础使用 / 批量基准 / 配置调整 / 高级特性 / FAQ。 |
| [docs/performance_guide.md](performance_guide.md) | 性能指南：参数、缓存、预算与调优口径。 |
| [docs/troubleshooting.md](troubleshooting.md) | 故障排查手册：症状 → 根因 → 解决步骤 → 预防措施。 |
| [docs/integration/README.md](integration/README.md) | CI/CD 集成指南：在外部流水线中调用本系统。 |
| [docs/integration/vendored_quixbugs.md](integration/vendored_quixbugs.md) | 外部数据集 QuixBugs 的本地集成与还原（含嵌套仓库注意事项）。 |
| [SECURITY.md](../SECURITY.md) | 安全策略：漏洞报告流程、支持版本与响应承诺。 |
| [docs/security/history_leak_remediation_runbook.md](security/history_leak_remediation_runbook.md) | 历史泄漏清理 Runbook：密钥轮换与 git 历史重写步骤。 |
| [examples/README.md](../examples/README.md) | 示例库：成本预算 / RAG A/B / 语义缓存三个可运行示例。 |
| [examples/cost_budget_demo/README.md](../examples/cost_budget_demo/README.md) | 示例：任务级成本预算硬上限（COST_BUDGET_ENABLE）。 |
| [examples/rag_ab_demo/README.md](../examples/rag_ab_demo/README.md) | 示例：RAG A/B 对比实验（ENABLE_RAG）。 |
| [examples/semantic_cache_demo/README.md](../examples/semantic_cache_demo/README.md) | 示例：语义级 LLM 缓存（SEMANTIC_CACHE_ENABLE）。 |

### 3.4 证据与统计工件

| 文档 | 一句话说明 |
|---|---|
| [BASELINE.yaml](../BASELINE.yaml) | 当前基线的机器可读单一事实来源（测试 / 覆盖率 / 实验数字均以它为准）。 |
| [三种子主批次统计报告](../experiments/results/main_batch/statistical_report_3seed_pooled.md) | 三种子主批次（n=261）的统计结论与置信区间。 |
| [主批次统计报告](../experiments/results/main_batch/statistical_report.md) | canonical 主批次统计报告。 |
| [MAST 分布报告](../experiments/results/main_batch/mast_distribution_report.md) | MAST 式失败分类的分布与跨臂对比。 |
| [修复上限归因报告](../experiments/results/main_batch/repair_ceiling_report.md) | repair 上限归因：patch 产出 / plausible / correct 的漏斗分解。 |
| [目标质量存量重放](../experiments/results/main_batch/target_quality_report.md) | 被测代码覆盖率 / 变异得分 / 规约可编译率的存量重放。 |
| [修正口径重估报告](../experiments/results/main_batch/corrected_report_v2.md) | false_fix / CPR / 弃权精确率与解混杂后的修正口径结论。 |
| [R4 / QuixBugs 批次说明](../experiments/results/r4_batches/README.md) | R4 与 QuixBugs 存量批次的目录、口径与入库说明。 |
| [docs/failure_analysis.md](failure_analysis.md) | 失败案例统计与典型失败模式分析（按错误类型 / Bug 模式分层）。 |

### 3.5 治理、评审与历史

| 文档 | 一句话说明 |
|---|---|
| [docs/PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) | 项目状态与决策登记册：已完成 / 遗留 / 阻断三类状态与验证入口。 |
| [CHANGELOG.md](../CHANGELOG.md) | 逐批变更日志（历史快照；当前口径以 BASELINE 与本索引指向的文档为准）。 |
| [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md) | 第三轮独立系统性评审报告（2026-10-18）：60+ 前沿数据点一手重建、14 项核心声明逐位复验、A-01..A-20 建议与同日收口状态。 |
| [docs/reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md](reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md) | 第三方独立审查（Windows，2026-10-18）23 项修复收口报告：P0 A08 凭证隔离 + P1/P2 逐项矩阵、M1–M9 复跑、门禁与残余风险；§5 为第二轮复核残留 A07/A09/A10 补修记录（2026-10-19）。 |
| [docs/reviews/REVIEW_CLARIFICATIONS_2026-10-19.md](reviews/REVIEW_CLARIFICATIONS_2026-10-19.md) | 第三轮评审 §15 八项待澄清问题的**权威回应入口**：5 项已闭合（给工件路径 + 复算命令 + 能力边界）、2 项待项目方裁定、1 项未做且代价明确。 |
| [docs/reviews/THIRD_PARTY_REVIEW_2026-10-19_FIX_CLOSURE.md](reviews/THIRD_PARTY_REVIEW_2026-10-19_FIX_CLOSURE.md) | 第四轮第三方全量静态审查 20 项修复收口（F01–F20 逐项矩阵、M1–M11 复跑、独立复算与残余风险；零 LLM）。 |
| [docs/reviews/FIX_COVERAGE_AUDIT_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_2026-10-19.md) | Y 轮修复覆盖率缺口审计：`src/` 552 行修复新增中 37 行从未被测试执行；5 例变异验证的回归锁。 |
| [docs/reviews/FIX_COVERAGE_AUDIT_ROUND2_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_ROUND2_2026-10-19.md) | Y2 轮审计收口：A20 三级降级链、A06 生产入口接线、A16 flaky 证据；`experiments/` 首次审计。 |
| [docs/reviews/FIX_COVERAGE_AUDIT_ROUND3_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_ROUND3_2026-10-19.md) | Y3 轮收尾：清理 2 个死函数、补 A03 provenance 三条降级路径、产出全仓未覆盖行地图（637 行 / 83 文件）。 |
| [docs/reviews/FIX_COVERAGE_AUDIT_ROUND4_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_ROUND4_2026-10-19.md) | AA 轮覆盖率收口：9 例确定性回归锁（含变异验证）+ 9 处"构造上不可达"防御线的证据登记；明确不加 `# pragma: no cover`、不删冗余档、不刷水位。 |
| [docs/reviews/TIER2_REAL_CORPUS_REPLAY_2026-10-19.md](reviews/TIER2_REAL_CORPUS_REPLAY_2026-10-19.md) | AB-1：用 7,565 条真实 LLM 响应重放判定 `helpers.py` 首对象修复档冗余性——AA-5 的"恒不可达"论证被否证，返回分支实测 0 次触发；保留决定改站在真实工件上，含隐私（只出聚合计数）与结构性和救不活论证。 |
| [docs/reviews/DATASET_ADAPTER_TOLERANCE_AB5_2026-10-19.md](reviews/DATASET_ADAPTER_TOLERANCE_AB5_2026-10-19.md) | AB-5：否证"数据集适配层分支需本地数据集才可达"前提；47 行 → 36 条变异验证容错锁 + 9 行按机制登记；顺带修复补充文件无主键行静默丢弃，并记录 3 条"绿着但空转"的自写空锁。 |
| [docs/reviews/JSONL_NON_OBJECT_ROW_AB8_2026-10-20.md](reviews/JSONL_NON_OBJECT_ROW_AB8_2026-10-20.md) | AB-8：`json.loads` 有六种合法返回而 AB-5 只测了两种形状——容错面改按**解析器返回域**枚举后抓到 6 处位置（产品侧 4 处 + 门禁侧 2 处，其中 1 处是对象内主键非标量）整批崩溃或静默零生效；47 例形状域回归锁含 7 处守卫的变异验证，另登记一处被探测否证的路径推断，以及验证脚本自身因 `-k` 匹配零条而报"七处全红"的空转。 |
| [docs/reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md](reviews/EXPERIMENTS_JSON_DOMAIN_AB9_2026-10-20.md) | AB-9：把 AB-8 登记的"`experiments/` 层未普查"补成实测——68 处 `json.loads` 逐处按返回域读数（42 响亮崩溃 / 9 已 fail-closed / 5 崩溃被上层吞掉但留痕 / **12 静默丢数据**），并写明分析层判据与产品侧相反：**响亮崩溃可接受，静默让分母消失才是缺陷**。本轮只处置 12 处里"数字正被引用且属复现入口"的 1 处（`make target-quality` 改为跳过计数 + 报告新增自我披露节 + stderr 告警，退出码与既有数值一个不动；14 例变异验证锁，当前入库报告逐字节复现），其余 11 处逐处列名登记、42 处响亮崩溃点判为不改（判据选择而非遗漏清单）。 |
| [docs/reviews/ABSENT_VS_ZERO_AB10_2026-10-20.md](reviews/ABSENT_VS_ZERO_AB10_2026-10-20.md) | AB-10：把 AB-9 登记里剩下的同一机制收成判据——**缺席 / 读不动不得报成"零命中 / 一致 / 未要求"**。实测坐实三处：上游读不到时脚本把本地 gold 包装后与本地 gold 归一比对，`upstream_bodies_equal` **恒真**（此时零份上游数据被读到）；`_load_json_array` 顶层非列表时静默返回空列表，调用方把它读成"上游没有该行"；README 的 4c / 4d 节按"某工件在不在输出目录"整段消失且不留消息。处置 2 处登记站点（`emse_ult_gold_diagnosis.py`：新增 `_load_upstream_array` / `_official_tests_for` / `_load_supplement` 与两节渲染器，非对象行改为 stderr 报数），一致性由 True / False 扩成含"无法核验"的三态。改前先实测真路径（200 / 3909 行全保留丢 0、71/71 任务命中上游分支、0 条走包装分支），因此受 `SHA256SUMS` 保护的入库报告**逐字节复现**两次成立。35 例合成 `tmp_path` 锁 + 10 处锚点变异验证逐处转红；AB-9 余下 3 处继续登记，本轮不动（**AB-11 后续：这 3 处已处置，但其中两行的原文各有一项机制仍未处置，见下一行**）。 |
| [docs/reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md](reviews/ABSENT_VS_ZERO_AB11_2026-10-20.md) | AB-11：把 AB-10 剩下的 3 处登记处置完，判据再窄一层——**同一个字段被三种事实共用时，缺席就只剩一种读数**。实测三处塌缩：`spec_augment_applied` 让"生产者写下的 `null`（真的没触发）/ 详情行没这个键 / 第二遍读不动"同落 `none` 桶，报告只会说"增广零命中"（盘上 df 臂 50/50 行为键在且为 `null`，故三态改造后入库读数逐字节不变、新桶 0 实例）；`_profile_presets` 四种失败机制（git show / ast.parse / literal_eval / 找不到赋值）全返回同一个 `{}`，调用方把原因**写死**成"git show 失败"，披露形对了但内容是假的，且 `old.get(profile) or {}` 让"档位不存在"与"两边一致"同形报成"无漂移"；`parse_trace_file` 损坏即返回 `None`，把 `meta.baseline` 明确写着臂名的文件整体归入 `unknown`，坏行前已解析的 **44 条记录无痕作废**（全仓普查 148 个 `*/traces` / 9086 个文件 / 5 个损坏）。处置为值域三态 + 命名 WARN、原因由机制拼 + 新增档名缺席分支、归臂口径与完好文件一致 + 作废量披露；5 个损坏目录"改前 vs 改后"复刻证明判定分母不变。另登记一条**因输入增长而失效的入库声明**（`mast_distribution_report.md` 说 963 个文件可逐位复算，同目录今天 2007 个），只锁不改写。31 例新锁 + 2 例改写 + 18 处锚点变异逐处转红（含一条变异脚本自身教训：锚点写坏致 `ImportError`、收集数 86→41，靠"收集数相等"前置检查识破）。 |
| [docs/reviews/SITE_C_MAST_NONOBJECT_AB12C_2026-10-20.md](reviews/SITE_C_MAST_NONOBJECT_AB12C_2026-10-20.md) | AB-12c：处置 AB-11 站点 c 剩下的另一半——**能解析但不是对象的 trace 行原先计入"有效文件数"**，把 MAST 分布报告的分母撑大、命中率压低。改造为按类型计数、"整份都是非对象行"的文件独占一档不进分母，披露行只在真出现时写入（0 实例时入库报告逐字节不变，由锁执行而非措辞承诺）。32 例锁 + 14 处锚点变异逐处转红。本轮另自捕获一条**测量工具缺陷**：前置探针取 trace 目录的父目录当扫描根，把 `main_batch/traces` 的 2007 个文件整个漏掉，报出"0 实例"的覆盖面实为 783 文件；修正后 138 目录 / 8539 文件 / 125270 行，非对象行仍为 0。教训（0 实例要连覆盖面一起锁）入 `docs/MEASUREMENT_INTEGRITY.md` §15。 |
| [docs/reviews/ARM_ROW_COLLAPSE_AB12D_2026-10-20.md](reviews/ARM_ROW_COLLAPSE_AB12D_2026-10-20.md) | AB-12d：处置 AB-11 §6⑤ 登记的共享 loader 缺口——`emse_df_spec_analysis.load_arm_rows` 里 `out[tid] = ...` 让**后出现的同 `task_id` 行静默覆盖前一行**，41 缺陷程序口径与配对检验的分母跟着缩；`row.get("task_id", "")` 又把键缺席与空串折成同一个键。改为返回域一字不动 + 只在真折叠时打命名 WARN，无主键行按五种机制分开计（五桶互斥，一行只进一桶）。普查按桶记账并锁死等式：glob 命中 246 份批次中 242 份（320 臂、10659 行）提供证据，另 4 份是 2 份空 details 与 2 份 `.mdo.json` 非臂形状，只点名不充数——实测 0 例折叠。26 例锁 + 14 锚点变异，其中两桶在真语料上 0 例、等式只能由合成语料压。顺带更正 AB-11 与 AB-12c 把定义处写成 `emse_docstring_anchor_analysis` 的归属错误。 |
| [docs/reviews/PRICE_TABLE_SENTINEL_AB12E_2026-10-20.md](reviews/PRICE_TABLE_SENTINEL_AB12E_2026-10-20.md) | AB-12e：处置 AB-9 登记的价目表两处——`load_price_table` 只拦 `OSError` 与语法错，六种合法非对象顶层**原样返回**，崩溃落在调用方 `table.get` 而该调用点在 `oracle_examples_replay.py:1030` 的**整轮付费 LLM 重放之后**（钱花完、报告一行没有）；`estimate_cost_usd` 用 `price_table=None` 兼作"未提供"哨兵，而 `None` 恰是 `json.loads` 的合法返回，实测显式传 `None` 会回头重读盘上真表给出金额。按仓内先例（`statistical_analysis.py:859`、`src/budget/pricing.py:71`）改为空表加留痕、哨兵拆三态，成本为 `None` 明写"不是 0"。真表读数一字不变。26 例锁 + 8 锚点变异全红。同族两处（`emse_stats_report.py:453` 读取点与 `:473` 同形哨兵）本轮实测坐实但**只登记不修**，转 AB-13。 |
| [docs/reviews/PRICE_TABLE_CURRENCY_AB13_2026-10-20.md](reviews/PRICE_TABLE_CURRENCY_AB13_2026-10-20.md) | AB-13：处置 AB-12 转来的价目表两处，并在前置复测中新坐实第三处——`total_usd` 的字段名声称美元而实现从不读 `currency`（一条 CNY 价目行实测被累加成 2.5 且账面正常）、六种合法非对象顶层原样返回并把崩溃留给调用方、`price_table=None` 与省略形参给出同一金额；处置为按机制点名 + `_UnsetPriceTable` 三态 + 只收 USD 的币种闸门 + 七桶互斥披露，51 例锁 + 15 处锚点逐处转红 + 中性对照 0 红；真批次三臂 783 行只用 USD 已登记模型 ⇒ 入库读数 0 行改变、六个受保护成本读数逐位复现。两套币种口径并存，本轮不统一。 |
| [docs/reviews/CURRENCY_SINGLE_SOURCE_AB14_2026-10-20.md](reviews/CURRENCY_SINGLE_SOURCE_AB14_2026-10-20.md) | AB-14：把 AB-13 那句"仓内另有口径、本轮不统一"展开成实测表——**同一个"这笔钱是不是美元"的判断仓内写了四遍且四遍互不相同，第五遍根本没写**（键缺席在 `pricing.py` 默认成美元并计价、同站点 `null` 却不计价；`or "USD"` 让缺席 / null / 空串三种事实一律印成 `USD`；另两处反向一律剔除且不 strip，`" USD "` 也被剔；币种集合大小写敏感使整臂成本降为 `None` 而报告落一行无归因的"未计价——（缺: ）"；`["USD"]` 让集合推导抛 `TypeError`、CLI 退出码 1 整份报告不产出；第五处 `add_cost` 一行都不读 `currency`）。处置为 `currency_status` 单一事实源（值域七族、13 输入落 9 个互不相同读数）+ 计价准入与可呈现标签分开 + 五站点全部接线 + 形状三通道点名（返回值口径不变）；站点差异只允许出现在"有没有地方写单位"。124 例锁 + 19 处锚点逐处转红（一处第一版 0 红，补混臂观测面后才算锁）+ 中性对照 0 红；本轮首次改动 `src/`（币种键缺席不再当美元），真表每条目都登记币种 ⇒ 三份受保护报告快照逐字节相同、`SHA256SUMS` 2040 条全 OK。六处同族站点未处置转 AB-15；分册 §5 初稿的函数名与形状域两处写错，收口前经复算推翻并就地下。 |
| [docs/reviews/COST_REJECTION_RENDERING_AB15_2026-10-20.md](reviews/COST_REJECTION_RENDERING_AB15_2026-10-20.md) | AB-15：把 AB-14 留下的"成本拒绝"一族收成判据——**被拒绝的金额不得披着金额的形状出现，且"为什么没有金额"必须与判定同源**。前置实测三种通道：`oracle_examples_replay.render_readme` 把未登记模型与 CNY 模型都印成 `$None`、真零印成 `$0.0`；`analyze_t1_b2_main_batch` 的池化用 `or 0.0` 把逐 seed 的 `None` 折回金额形状；`emse_stats_extensions._cost_per_task` 是 AB-14 漏掉的**第六处**币种盲点（改标 CNY 后 `usd_per_task` 逐位不变）。另有四套归因词汇各写各的、spec 的判定与归因是两段可漂移代码。处置为 `currency_block_reason` + `CURRENCY_UNDETERMINED_STATUSES` 单一机制词汇、`_price_admission` 判定/归因同源、拒绝不落 `$` / 不折 `0.0` / 部分和不冒充全额、披露键只在真拒绝时写入。**109 例锁 + 27 处锚点逐处转红**（collected 恒 109、中性对照 0 红、sha256 字节还原）；真批次读数零改变；全量 10109 passed / 5 skipped / 0 failed，行 97.23% / 分支 93.80%（+12 行 / +8 弧，未覆盖 525 与偏弧 438 不变）。十项边界只登记不修见分册 §5。 |
| [docs/reviews/TABLE_ADMISSION_AB17_2026-10-20.md](reviews/TABLE_ADMISSION_AB17_2026-10-20.md) | AB-17：处置 AB-16 两谓词的共同上游「文件 → `models` 层」一族——**"这个文件读出来算不算一张表"一处写一遍**。前置普查实测七处读点各写一套：`src` 缓存包装七种坏（顶层 list / null / 空对象 / 缺键 / `models` 为 list·str·null）读同一句「结构不符（缺 models dict）」并写"键在值为 null"；ext 七种坏**全部直接崩**（是七处里唯一连空表降级都没有的）；report 六个互不相同的中文短语只在 stderr、归因全落 `model_unregistered`；spec 文件级只进日志、`models` 层 pass-through；statistical 文件路径全程无痕而参数路径另一套短语；run_b8 的 `is_file()` 前置守卫静默退回内置价；检索层 `.get` 的 `is None` 让"键缺席"与"值 null"共用一句。处置为四个共享助手——`table_read_reason`（文件级失败按事实分族）、`load_table_json`（`(None, None)` 是合法读数）、`models_layer`（顶层/键/值三层形状逐一点名；`{}` 与 `{"models": {}}` 静默"空对象没有形状可说"；可用则原样交出）、`load_table_models`——七处读点全部接线，检索层四处改 `not in`；两处设计性读法差异（spec pass-through、ext `is_file()` 守卫）记录在案由锁锁定。**26 例锁 + 8 处锚点逐处转红**（collected 恒 484、写盘前 `compile()`、sha256 字节还原），五处既有锁改写净 0 例；真批次与受保护工件零改变（run_b8 真表聚合的 `price` 元数据与受保护 `REPORT.json` 逐字段相等，聚合一律在 tmp 副本上跑）；全量 10283 passed / 5 skipped / 0 failed，行 97.24% / 分支 93.84%（+20 行 / +15 弧，未覆盖 524 = 525 − 1、偏弧 437 = 438 − 1）。九项边界只登记不修见分册 §5。 |
| [docs/reviews/PRICE_ADMISSION_AB16_2026-10-20.md](reviews/PRICE_ADMISSION_AB16_2026-10-20.md) | AB-16：处置 AB-15 §5.2 交来的数字域与形状域一族——**"什么算一个价格数字、什么算一张合格条目"一处写一遍**。前置普查实测准入域在六处各写各的：spec / report / ext 三站点各自 `float()` 直收（`True` 当 1、`"1.0"` 收下、`-1.0` 编出金额、`[1.0]` 抛 `TypeError`、`nan` / `inf` 累成非有限金额），空条目与 `null` 价从"拒绝"退成 0.0 部分和，同一条目四站点四种结论（spec/ext/analyze 读 `currency_unreachable:int`、report 读 `entry_not_object:int`）；生产 `_as_non_negative_float` 收下 `nan`/`inf` 记账 `(nan, "price_table:m")`；statistical 的 `inf >= 0` 把非有限价当"已计价"。处置为两条共享谓词——`price_block_reason`（缺席 > 类型 > 负数 > 非有限；`bool` 单列、同族聚合）与 `entry_block_reason`（形状 → 空 → 币种 → 数字）——六处消费点全部接线并删两处本地词汇，spec 真值非对象 `models` 从抛 `AttributeError` 改为 `models_not_object:<T>`。**148 例锁 + 21 处锚点逐处转红**（collected 恒 148、中性对照 2 处 0 红、sha256 字节还原）；真批次读数零改变；全量 10257 passed / 5 skipped / 0 failed，行 97.23% / 分支 93.81%（+16 行 / +12 弧，未覆盖 525 与偏弧 438 不变）。十一项边界只登记不修见分册 §5。 |
| [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md) | 第二轮独立系统性评审报告：发现、证据与处置建议。 |
| [CODE_OPTIMIZATION_2026-10-16.md](../CODE_OPTIMIZATION_2026-10-16.md) | 代码全面审查与优化报告（C 轮）。 |
| [PHASE1_PRECHECK_2026-10-12.md](../PHASE1_PRECHECK_2026-10-12.md) | 改进方案阶段 1 前置核查报告。 |
| [SPEC_REPLACE_AB_REPORT_2026-10-12.md](../SPEC_REPLACE_AB_REPORT_2026-10-12.md) | spec_replace A/B 阶段 1 实验报告（QuixBugs，探索性口径）。 |
| [docs/HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md) | E7 人工裁决操作协议：抽样框 / 五选一量表 / 双人独立 / 冲突解决。 |
| [docs/COVERAGE_RATCHET_DEVIATION.md](COVERAGE_RATCHET_DEVIATION.md) | 覆盖率棘轮偏差登记：实测 vs 水位、归因核验与处置路径。 |
| [docs/study/OPTIMIZATION_2026-10-15.md](emse/OPTIMIZATION_2026-10-15.md) | EMSE 投稿优化记录：审稿可判性收口批次。 |
| [REPLICATION.md](../REPLICATION.md) | 复现包说明：目录、工件与还原命令（中文）。 |
| [CITATION.cff](../CITATION.cff) | 引用元数据（软件引用格式）。 |
| [LICENSE](../LICENSE) | 开源许可证。 |

## 4. 链接与双语维护

- **链接校验**：`python scripts/gates/check_doc_links.py --strict`
  （零网络、纯静态：校验相对文件链接、行锚目标存在性、标题锚点；
  忽略 fenced / inline code 中的示例链接；外链只统计不请求）。
- **双语配对**：`make docs-check`（`scripts/gates/check_bilingual_docs.py --strict`）。
- **例外登记**：[docs/link_check_allowlist.txt](link_check_allowlist.txt)，
  每行 `<源文件>:<链接目标>  # 理由`；命中记 `[allow]` 但不阻断 strict，
  无理由的豁免会被判为 error。
- **维护约定**：新增核心文档 → 在本页 §3 对应分组登记一行（含一句话说明）；
  改名 / 归档文档 → 全仓搜索旧名并更新链接，勿留死链。
