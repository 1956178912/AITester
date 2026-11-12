# AITester 模型卡

**检出优先**的 Python 测试生成与修复评估研究系统（归因口径）。本卡描述模型使用、数据来源、评估口径与已知限制。

最后更新：2026-11-12（按现行权威批次刷新）

> **口径声明**：本卡的当前口径 = `experiments/results/RESULTS_DATA_PACK_20261111.json`
> （50 格零 LLM 聚合，逐指标 n_obs）+ 稿件 `paper/tex/manuscript.tex`（38 页 / 86 文献）。
> 派生判定行与 50 格聚合已随 DOI `10.5281/zenodo.24136905` 版本锁定公开（不含原始
> trace 与模型转录）。凡标注「历史读数」的数字属已退役协议代，**不与现稿混池**、不作为
> 当前能力结论；旧代逐轮记录见 `CHANGELOG.md` 与 `docs/design/repair_caliber_matrix.md`。

## 1. 系统概述

给定五个基准（QuixBugs、BugsInPy、SWE-bench、TestGenEval、ULT；逐面规模与可用性见
`docs/DATA_CARD.md`），系统由 LangGraph 编排 Planner → Generator → Executor →
Debugger → PatchApplier 闭环：生成 pytest 测试、执行、诊断失败并打补丁。

「多智能体编排」是**可消融容器**，不是主断言。现行稿件的中心主张是「声明通过 ≠
裁决真实通过」的 false-fix 配对报告（RQ2）与 harness 排除披露（RQ3）；编排不承载
独立的能力主张。本系统是科研代码，不是部署产品。

## 2. 模型使用

- **模型来源**：不自研、不微调。全部智能由用户自配的 OpenAI 兼容端点提供
  （`.env.local` 的 `LLM_N_*`：API Key / Base URL / 模型名）；`PROVIDER_TEMPLATES`
  内置两家 provider（DeepSeek 与 xiaomi MiMo）。现行权威批次逐格对比两个端点
  `deepseek-flash` 与 `mimo-v2.6-pro`，并发按厂商额度决议；价目表与额度登记在
  `MODEL_RATE_LIMITS`，**跨模型读数按「模型 × 臂 × 面」分格，不混池**。
- **模型角色**：Planner（逻辑分析）、Generator（测试生成）、Debugger/Review（根因诊断
  与补丁）、FaultLocalizer（RGFL 式推理定位，只定位不修复）、ExpertPool（可选并行专家）。
- **确定性通道**：SpecIR v2 DSL 断言、SMT 见证、Ochiai 谱系定位、变异评分、P2P 回归
  门禁均为非 LLM 组件；LLM 失败时系统保守降级。
- **故障定位双通道**：谱系通道（Ochiai，非 LLM）+ 推理通道（`FaultLocalizerAgent`，
  消耗 LLM，`FAULT_LOCALIZER_ENABLE` 默认开，失败降级 `None`）。
- **调用配置（ADR-0031）**：`LLM_THINKING_MODE` 默认 off（跨模型对比固定在同一推理
  档位；思考链计入输出计费）；`LLM_JSON_MODE` 默认 on（7 处 JSON 契约调用点绑定
  `response_format=json_object`）；`finish_reason ∈ {length,
  insufficient_system_resource}` 按可恢复失败重试；JSON 值位的 Python 数值表达式由
  限制求值解析层修复（无 `eval`）。

## 3. 数据

- 本项目**不训练模型**，无训练数据。
- 评估数据：现行权威批次为 `test_run_20261106T101605Z` 主批（50 格）+
  `rerun_swebench_20261110` + `rerun_testgeneval_20261110_v5`；三目录来源白名单由
  `scripts/tools/results_data_pack_20261111.py` 钉死，防止冒烟批次污染底稿。
  逐面许可、泄漏控制与未核实项见 `docs/DATA_CARD.md`。
- RAG 案例库来自实验自身的历史产出（本地 `rag_data/`，不入库）。
- **已知偏差**：仅 Python 单语言；函数级单文件任务与仓库级任务的执行层差异显著；
  测试生成与修复使用同一 LLM 配置池，自产生/自验证循环由 held-out gold 独立裁决
  拦截；SWE-bench 面的 `harness_invalid` 是协议层结构性排除，逐行留痕且不进判定
  分母（稿件 RQ3 如实披露）。

## 4. 指标与口径

- **现行权威口径**：每条声明通过对 held-out gold 材料做独立裁决；pass rate 必须与
  false-fix rate 配对报告（稿件 RQ2 的 QuixBugs 逐格 adjudicated real passes）。50 格
  全部指标由 `RESULTS_DATA_PACK_20261111.json` 派生，逐指标带 `n_obs`，观测不到不计
  0 分母；首过判定读数（4,458 判定 / 711 passed）**不是**论文最终口径，换数须按预
  注册口径另行重算（`RESULTS_DIGEST_20261111.json` 已写死该警示）。
- **有效通过口径（BA→BC）**：pytest 对全 skip/xfail/deselect 也返回 `rc==0`，故派生
  读数要求至少 1 个 passed 且 0 个 failed，否则 fail-closed（`None`/`unverifiable`）。
- **E7-r2（2026-11-12 设计修订）**：人工校标的抽样框换为现行权威批次 QuixBugs 的
  **89 条 declared-pass 判定行普查**（= 稿件 tab:falsefix 全部判定行）：补丁轨 42 行
  五分类审计、套件轨 47 行结构确认 + 形态标注。备料包与交接 zip 已生成，**裁决动作
  仍待人工**（两名独立裁决人 + 第三方合并，Cohen's κ 主口径不变）；旧框（72 行
  `patch_plausible` 分层抽样）作废。
- **历史读数（已退役协议代，不可与现稿混池）**：repair 39.31%（v2，57/145 可重放行）、
  v1 35.86%、「n=261/臂」三 seed 池、E2 双门 δ=−0.3673、`spec_compile_rate` 恒 0.0、
  aitester $0.0259 / plain_llm_df $0.0045 每任务、n=20 SWE-bench Lite 冒烟（429 限流，
  无有效能力结论）。这些数字仅为当时事实，逐轮出处见 CHANGELOG 与口径矩阵。
- **现行 SWE-bench 面**：2,197 行中 1,919 行 `harness_invalid`（结构性排除）、278 行
  可判；不得把排除行折进分母，也不得把冒烟批的限流记录读成能力结论。

## 5. 已知限制

- 现行读数限于两端点 × 五臂 × 五基准的这一批次，不外推到未测端点或任务集；
  **跨批次不混池**，引用任何历史读数必须带批次标签。
- 现行稿件以判定口径为中心（declared pass vs adjudicated real pass），**不主张**
  「自修复已达成」；修复引擎路线（定位 → 合成 → 验证）仍在推进。
- E7-r2 的人类裁决动作未执行，外部校标尚未闭环；全仓仍不存在 Kappa 工件。
- 任意代码执行风险：LLM 生成代码在本机运行；venv 沙箱默认开（`EXECUTOR_USE_VENV`），
  Docker 隔离可选（`--network=none` + `--read-only` + `--cap-drop=ALL`）。API Key 只经
  `.env.local`（不入库），配合 gitleaks 扫描与子进程环境脱敏。
- 不涉人类受试者、不采集个人数据；SWE-bench 任务来自公开仓库历史 issue/PR。
- 代码许可见 `LICENSE`（MIT）；引用规范见 `CITATION.cff`。
