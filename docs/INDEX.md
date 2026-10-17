# AITester 文档索引（Documentation Index）

> 最后更新：2026-10-17
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
| 查投稿材料（EMSE） | [docs/emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md](emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md) |

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
2. [docs/preregistration.md](preregistration.md)：E1–E4 预注册（判定口径先声明后取数）。
3. [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md)：声明 → 证据 → 范围对账表（含被反驳声明）。
4. [docs/MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md)：测量伪影的形态、检测与修复方法论。
5. [BASELINE.yaml](../BASELINE.yaml)：全部当前数字的机器可读单一来源。
6. [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md)：独立系统性评审（含遗留项与处置）。

### 2.3 复现者

1. [REPLICATION.md](../REPLICATION.md)：复现包构成、工件清单与还原步骤。
2. [reproduce.sh](../reproduce.sh)：主批次复现入口（消耗 LLM 配额，勿自动触发）。
3. [docs/usage_examples.md](usage_examples.md)：单文件 / 批量 / 消融 / 成本预算的完整用法。
4. [docs/performance_guide.md](performance_guide.md)：性能参数、预算口径与调优。
5. [docs/troubleshooting.md](troubleshooting.md)：环境 / 依赖 / Docker / RAG 卡点。
6. [三种子主批次统计报告](../experiments/results/main_batch/statistical_report_3seed_pooled.md)：关键统计结论的证据源（实验工件，非门禁文档）。

### 2.4 维护者

1. [docs/PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md)：状态与决策登记册（已完成 / 遗留 / 阻断）。
2. [docs/adr/README.md](adr/README.md)：ADR 索引（新增架构决策时在此追加一行）。
3. [CHANGELOG.md](../CHANGELOG.md)：逐批变更日志（历史快照，不作链接门禁的扫描面）。
4. [docs/HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md)：人工裁决协议（抽样框 / 量表 / 双人独立 / 冲突解决）。
5. [docs/emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md](emse/EMSE_SUBMISSION_CHECKLIST_2026-10-15.md)：投稿材料收口清单。
6. [scripts/gates/](../scripts/gates/)：全部门禁脚本目录（新增门禁在此目录，并接 Makefile / CI）。

## 3. 核心文档清单

### 3.1 定位、效度与测量完整性

| 文档 | 一句话说明 |
|---|---|
| [docs/VALIDITY.md](VALIDITY.md) | 效度威胁模型：构念 / 内部 / 外部 / 统计结论四类威胁与逐项缓解。 |
| [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md) | 声明 → 证据 → 范围对账表；含 contradicted 声明清单（编辑初筛用）。 |
| [docs/MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md) | 四起测量伪影的"口径分叉"方法论：逐起给分叉口径 / 检测 / 量级 / 修复 / 结论是否翻转。 |
| [docs/preregistration.md](preregistration.md) | E1–E4 验证实验预注册：判定口径、样本量与停止条件先声明后取数。 |
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
| [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md) | 独立系统性评审报告：发现、证据与处置建议。 |
| [INDEPENDENT_REVIEW_2026-10-16.md](../INDEPENDENT_REVIEW_2026-10-16.md) | 独立评审报告（根目录批次交付物）。 |
| [CODE_OPTIMIZATION_2026-10-16.md](../CODE_OPTIMIZATION_2026-10-16.md) | 代码全面审查与优化报告（C 轮）。 |
| [PHASE1_PRECHECK_2026-10-12.md](../PHASE1_PRECHECK_2026-10-12.md) | 改进方案阶段 1 前置核查报告。 |
| [SPEC_REPLACE_AB_REPORT_2026-10-12.md](../SPEC_REPLACE_AB_REPORT_2026-10-12.md) | spec_replace A/B 阶段 1 实验报告（QuixBugs，探索性口径）。 |
| [docs/HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md) | E7 人工裁决操作协议：抽样框 / 五选一量表 / 双人独立 / 冲突解决。 |
| [docs/EMSE_COVERAGE_RATCHET_DEVIATION.md](EMSE_COVERAGE_RATCHET_DEVIATION.md) | 覆盖率棘轮偏差登记：实测 vs 水位、归因核验与处置路径。 |
| [docs/emse/EMSE_OPTIMIZATION_2026-10-15.md](emse/EMSE_OPTIMIZATION_2026-10-15.md) | EMSE 投稿优化记录：审稿可判性收口批次。 |
| [docs/emse/EMSE_SUBMISSION_SKELETON_2026-10-16.md](emse/EMSE_SUBMISSION_SKELETON_2026-10-16.md) | EMSE 投稿骨架（章节结构、证据映射与待补项）。 |
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
