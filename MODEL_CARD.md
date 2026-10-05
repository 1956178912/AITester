# AITester 模型卡（MODEL CARD）

最后更新：2026-10-05（优化批次 T6）

## 1. 系统概述

AITester 是一个逻辑驱动的多智能体测试生成与自修复研究系统：给定函数级修复任务
（合成数据集或 SWE-bench Lite 拆分任务），由 LangGraph 编排的 Planner →
Generator → Executor → Debugger → PatchApplier 闭环生成 pytest 测试、执行、
诊断并打补丁。本卡描述其模型使用、数据来源与风险面（参考 NIST AI RMF 与
模型卡通行条目；本系统当前定位为科研代码，非部署产品）。

## 2. 模型使用

- **模型来源**：本项目不自研/微调模型。全部智能由用户自配的 OpenAI 兼容端点
  提供（`.env.local` 的 `LLM_N_*` 三元组：API Key / Base URL / 模型名，
  支持任意 OpenAI 兼容 provider 与智谱 zai-sdk 端点）。
- **模型角色**：Planner（逻辑分析/规约产出）、Generator（测试代码生成）、
  Debugger/Review（根因诊断与补丁生成）、ExpertPool（可选多维度并行专家）。
- **确定性通道**：SpecIR v2 DSL 编译断言、SMT 见证（`[formal]` extra）、
  Ochiai 谱系定位、变异评估、P2P 回归门禁均为**非 LLM** 的确定性组件，
  LLM 失败时系统保守降级（详见各模块 docstring）。

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

- 当前主批次（合成 n=50，seed 42）：detection_rate=2.0% / repair_rate=0.0% /
  false_fix_rate=89.8%（详见 `BASELINE.yaml` benchmark 节）；
  真实 SWE-bench Lite（n=20 冒烟）：resolved 0/20。系统的有效性主张
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
  （引用真实性由 `scripts/check_citations.py` 周检）。
