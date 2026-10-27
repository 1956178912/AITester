# AITester 模型卡

**检出优先**的 Python 测试生成与修复评估研究系统（归因口径）。本卡描述模型使用、数据来源、评估口径与已知限制。

最后更新：2026-10-27

## 1. 系统概述

给定函数级修复任务（合成数据集或 SWE-bench Lite 拆分任务），系统由 LangGraph 编排
Planner → Generator → Executor → Debugger → PatchApplier 闭环：生成 pytest 测试、执行、
诊断失败并打补丁。

「多智能体编排」是**可消融容器**，不是主断言（ADR-0016；E2 双门后 aitester 对
plain_llm_df δ=−0.3673，结构性劣后）。本系统是科研代码，不是部署产品。

## 2. 模型使用

- **模型来源**：不自研、不微调。全部智能由用户自配的 OpenAI 兼容端点提供
  （`.env.local` 的 `LLM_N_*`：API Key / Base URL / 模型名）；内置 provider 只有
  DeepSeek 官方端点，价目表只登记 deepseek-flash——**单一模型族**，结论不外推到
  其他模型族。
- **模型角色**：Planner（逻辑分析）、Generator（测试生成）、Debugger/Review（根因诊断
  与补丁）、FaultLocalizer（RGFL 式推理定位，只定位不修复）、ExpertPool（可选并行专家）。
- **确定性通道**：SpecIR v2 DSL 断言、SMT 见证、Ochiai 谱系定位、变异评分、P2P 回归
  门禁均为非 LLM 组件；LLM 失败时系统保守降级。
- **故障定位双通道**：谱系通道（Ochiai，非 LLM）+ 推理通道（`FaultLocalizerAgent`，
  消耗 LLM，`FAULT_LOCALIZER_ENABLE` 默认开，失败降级 `None`）。
- **调用配置（ADR-0031）**：`LLM_THINKING_MODE` 默认 off（思考链计入输出计费）；
  `LLM_JSON_MODE` 默认 on（7 处 JSON 契约调用点绑定 `response_format=json_object`）；
  `finish_reason ∈ {length, insufficient_system_resource}` 按可恢复失败重试；JSON
  值位的 Python 数值表达式由限制求值解析层修复（无 `eval`）。

## 3. 数据

- 本项目**不训练模型**，无训练数据。
- 评估数据：`data/swe_bench_lite_*` 来自公开 SWE-bench Lite（SWE-bench 官方仓库以
  Apache-2.0 分发，第三方使用前请复核当期声明）；合成任务由
  `src/datasets/synthetic_dataset.py` 程序化生成（本项目自研，随仓库 MIT 分发）。
- RAG 案例库来自实验自身的历史产出（本地 `rag_data/`，不入库）。
- **已知偏差**：仅 Python 单语言；合成模板以人工编写的边界/异常/契约缺陷为主，与真实
  仓库缺陷分布存在系统性差距；任务以函数级单文件为主，仓库级未覆盖；测试生成与修复
  使用同一 LLM 配置池，自产生/自验证循环（`false_fix` 即其产物）已量化但未消除。

## 4. 指标与口径

- **repair = 39.31%（v2，57/145 可重放行，gold 独立裁决）**。历史「全线 0.0%」是两起
  测量伪影（ADR-0021 patch 字段围栏残留 + ADR-0029 跨文件任务未物化）叠加所致；v1
  口径 35.86% 是跨文件伪影下界。口径矩阵见 `docs/design/repair_caliber_matrix.md`。
- **世代声明**：以「n=261/臂」为口径的多 seed 池已于 2026-10-24 撤回，只作历史记录；
  当前世代读数见 `BASELINE.yaml` 与重建批，单批不混池。
- **检出口径**：E2 双门后 aitester 对 plain_llm_df δ=−0.3673（全系统在强模型下劣于
  纯提示协议）；现有检出收益归因于检出优先提示协议，而非「逻辑驱动」规格链。
- **有效通过口径（BA→BC）**：pytest 对全 skip/xfail/deselect 也返回 `rc==0`，故派生
  读数要求至少 1 个 passed 且 0 个 failed，否则 fail-closed（`None`/`unverifiable`）。
- **spec_compile_rate** 在 logic 档实测恒 0.0（AB1 12/12），规格链未被激活；E1
  （预注册阈值 ≥0.3 保留 / <0.2 放弃）为该主张的生死裁决。
- **成本**：aitester $0.0259 / plain_llm_df $0.0045 每任务（deepseek-flash 峰时价目表）；
  plain_llm_df 为已记账花费**下界**（`cost_caliber="recorded_lower_bound"`），非免费。
- **真实 SWE-bench Lite（n=20 冒烟）**：基础设施故障，**无有效能力结论**——7 次完成
  全部 429 限流、3 次失败、10 次超时（`experiments/results/swebench_20_summary.json`）。
  有效性主张尚未被真实基准支持，该基准在待复跑清单。
- **E7（修复上限分层抽样）已预注册、尚未执行**（`docs/preregistration.md`）：修复上限
  归因待 E7 数据产生后才可主张。

## 5. 已知限制

- 单一模型族、合成数据为主：检出与修复数字不可外推到其他模型或真实仓库分布。
- repair 39.31% 是**已测量读数**，不是「自修复已达成」的主张；修复引擎路线（定位 →
  合成 → 验证）仍在推进。
- 真实基准证据缺位：SWE-bench Lite 冒烟无有效结论，不得引用为能力负结果或正结果。
- E7 未执行，修复上限的归因结论尚未闭环。
- 任意代码执行风险：LLM 生成代码在本机运行；venv 沙箱默认开（`EXECUTOR_USE_VENV`），
  Docker 隔离可选（`--network=none` + `--read-only` + `--cap-drop=ALL`）。API Key 只经
  `.env.local`（不入库），配合 gitleaks 扫描与子进程环境脱敏。
- 不涉人类受试者、不采集个人数据；SWE-bench 任务来自公开仓库历史 issue/PR。
- 代码许可见 `LICENSE`（MIT）；引用规范见 `CITATION.cff`。
