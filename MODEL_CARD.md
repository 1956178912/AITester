# AITester 模型卡（MODEL CARD）

最后更新：2026-10-08（R2 落地批次：叙事对齐 ADR-0016——§1 去"多智能体"主断言，"多智能体编排"降为可消融容器；repair 数字更新为修正口径 v2；此前 2026-10-07 修复引擎批次 I：范式转向"局部化 → 合成 → 验证"——独立 FaultLocalizer 落地〔RGFL 式 LLM 推理定位 + Ochiai 谱系佐证双通道，`FAULT_LOCALIZER_ENABLE` 默认开〕+ 局部化独立指标 `localization_hit_function` 首测）

## 1. 系统概述

AITester 是一个**检出优先的 Python 测试生成与修复评估研究系统**（归因口径）：
给定函数级修复任务（合成数据集或 SWE-bench Lite 拆分任务），由
LangGraph 编排的 Planner → Generator → Executor → Debugger →
PatchApplier 闭环生成 pytest 测试、执行、诊断并打补丁。其中"**多智能体
编排**"定位为**可消融容器**（非主断言——E2 双门后 aitester vs
plain_llm_df δ=−0.3673 结构性劣后，ADR-0016）。三种子主批次 repair 经
ADR-0021/0027/0029 测量口径修正后为 **39.31%（v2，57/145 可重放行；gold
独立裁决）**（v1 35.86%；上限归因见
`experiments/results/main_batch/repair_ceiling_report.md`）；**自修复为可测量
口径而非已证实主张**（AL5 定位收口）。
本卡描述其模型使用、数据来源与风险面（参考 NIST AI RMF 与
模型卡通行条目；本系统当前定位为科研代码，非部署产品）。

## 2. 模型使用

- **模型来源**：本项目不自研/微调模型。全部智能由用户自配的 OpenAI 兼容端点
  提供（`.env.local` 的 `LLM_N_*` 三元组：API Key / Base URL / 模型名，
  支持任意 OpenAI 兼容 provider 与智谱 zai-sdk 端点）。
- **模型角色**：Planner（逻辑分析/规约产出）、Generator（测试代码生成）、
  Debugger/Review（根因诊断与补丁生成）、FaultLocalizer（RGFL 式推理故障
  定位，只定位不修复，2026-10-07 修复引擎批次 I 起）、ExpertPool（可选
  多维度并行专家）。
- **确定性通道**：SpecIR v2 DSL 编译断言、SMT 见证（`[formal]` extra）、
  Ochiai 谱系定位、变异评估、P2P 回归门禁均为**非 LLM** 的确定性组件，
  LLM 失败时系统保守降级（详见各模块 docstring）。注意：故障定位为
  **双通道**——谱系通道（Ochiai，非 LLM）之外，推理通道（RGFL 式
  `FaultLocalizerAgent`，`FAULT_LOCALIZER_ENABLE` 默认开）**消耗 LLM**
  且失败时保守降级 None；`FAULT_LOCALIZER_ENABLE=false` 退回纯谱系消融口径。

## 3. 训练数据与数据来源

- 本项目**不训练模型**，无训练数据。
- 评估数据：`data/swe_bench_lite_*`（SWE-bench Lite 派生，来源为公开
  SWE-bench 数据集；数据许可：SWE-bench 官方仓库以 **Apache License 2.0**
  分发数据（P1-9 补齐，引用以 [官方仓库](https://github.com/SWE-bench/SWE-bench)
  声明为准——第三方使用前请自行复核当期版本）与
  `src/datasets/synthetic_dataset.py` 程序化生成的合成任务（本项目自研，
  随仓库 MIT 许可）。
- RAG 案例库：来自实验自身产出的历史用例（用户本地 `rag_data/`）。

### 3.1 已知偏差（Bias）

- **语言偏差**：仅支持 Python 单语言（多语言为设计未实现，见
  `docs/design/multilanguage_extension.md`），结论不可外推至其他语言生态。
- **任务分布偏差**：合成模板为人工编写的经典缺陷形态（边界/异常/契约类），
  与真实仓库缺陷分布（跨文件、依赖性、语义性缺陷为主）存在系统性差距——
  detection/repair 在合成集上的数字不应外推到真实仓库场景。
- **难度偏差**：模板以函数级单文件为主（Level 3/3.5 跨文件占少数），
  仓库级/工程级任务未覆盖。
- **LLM 同源偏差**：测试生成与修复使用同一 LLM 配置池，自产生/自验证的
  循环（M1 三指标中的 false_fix 即其产物）已量化但未消除。

## 4. 评估口径与已知局限（诚实声明）

- 当前口径 = R-P0-2 生死实验三种子合并（2026-10-06，n=261/臂，logic 档、
  deepseek-flash、McNemar+BH-FDR 全显著；详见 `BASELINE.yaml` benchmark 节
  与 `statistical_report_3seed_pooled.md`）：detection plain_llm_df 44.8% >
  aitester 15.8% > plain_llm 1.5%；aitester vs df **−28pp**——完整系统在
  强模型下显著劣于纯提示协议（编排净负贡献；21 行缺失双界下结论稳健）。
- **repair 经测量口径修正后 = 39.31%（57/145 可重放行）**：历史"全线
  0.0%"系两起测量伪影（ADR-0021 patch 字段围栏残留 + ADR-0029 跨文件任务
  未物化）叠加所致，非修复主张缺证。上限归因
  （`repair_ceiling_report.md`，AK1）：修复循环 154/261 → patch 产出 94.2%
  → plausible 46.8% → correct 39.31%——瓶颈在补丁合理性与 gold 正确性，
  非补丁未产出。2026-10-07 范式转向后 repair 从"诚实测量的结论"转为
  "要优化的目标"（修复引擎路线：局部化 → 合成 → 验证）；v1 口径
  35.86% 系跨文件伪影下界（口径矩阵见 `docs/design/repair_caliber_matrix.md`）。
- 局部化维度：`fl_at_k`（谱系行级 Top-k 命中，R8 起）与
  `localization_hit_function`（LLM 推理定位函数级命中，批次 I 起，与
  gold 变更函数集合比对；未定位/无 gold 材料时键集合同构占位）与
  检出/修复指标并列输出。E2 定案批 FL@1 首度可测 19/53=35.8%
  （gold diff 对齐修复后口径）。
- 成本：aitester $0.0259 / plain_llm_df $0.0045 每任务（价目表 2026-10-06
  官方登记口径：deepseek-flash 峰时价、qwen-long 标准价；agnes 无公开
  官方价未登记）。
- spec_compile_rate 在 logic 档实测恒 0.0（AB1 验证批 12/12）——"逻辑驱动"
  规格链未被激活，当前检出收益归因于检出优先提示协议；E1（预注册阈值
  ≥0.3 保留 / <0.2 放弃）为该主张的生死裁决。
- 真实 SWE-bench Lite（n=20 冒烟）：resolved 0/20。系统的有效性主张
  **尚未被真实基准支持**，数字以 BASELINE.yaml 为单一事实源。
- "逻辑驱动"全链路（SpecIR DSL / 确定性 oracle / 结构化路由）默认关闭，
  需 `AITESTER_PROFILE=logic` 显式启用。

## 5. 风险面与防护

- **任意代码执行**：LLM 生成代码在本机执行。防护：venv 沙箱默认开
  （`EXECUTOR_USE_VENV`）、Docker 隔离可选（默认 `--network=none` +
  `--read-only` + `--cap-drop=ALL`）、内核沙箱（bwrap/Landlock，Linux，
  可选）、路径越界防护、补丁证据门与快照回滚。
- **凭证管理**：API Key 只经 `.env.local`（不入库）+ gitleaks 工作树/全历史
  双扫描 + 子进程环境脱敏（`scrub_os_environ`）。
- **提示注入**：输入侧 `detect_prompt_injection` 特征扫描（默认关，
  `INJECTION_GUARD_ENABLE`），命中只警示不自动阻断（OWASP LLM
  Top 10 口径的"检测+隔离"分层处置）。
- **成本**：任务级 token/USD 预算硬闸（默认关）+ LLM 调用墙钟预算。

## 6. 伦理与合规

- 不涉人类受试者、不采集个人数据；SWE-bench 任务均来自公开仓库的
  历史 issue/PR。
- 按 EU AI Act 口径本系统属软件开发工具（非 GPAI 提供商/部署者义务主体），
  使用第三方 LLM 端点时的合规责任在端点提供方与使用者。
- 生成内容披露：本项目开发流程使用 LLM 辅助，代码与文档按团队规范
  不以 AI 署名、由仓库维护者对全部内容负责。

## 7. 引用与许可

- 本项目代码：见仓库根 `LICENSE`。
- 引用的基准/方法来源：见根目录 5 份 `*_BASELINE_2023-2026.md` 综述
  （引用真实性由 `scripts/gates/check_citations.py` 周检）。
