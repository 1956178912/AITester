# 多智能体 → 单智能体技能库编译路线（R4，2026-10-09 审查落地·S7）

> 状态：**设计文档（探索性，Proposed）**。本文不落任何代码，是后续立项的
> 输入；任何实现批次须另立 ADR 并在预注册文档固化判定阈值。

## 1. 背景与动机

### 1.1 C2 净负发现（项目自身）

E2 双门后 `aitester vs plain_llm_df δ=−0.3673` 结构性劣后（ADR-0016），
"多智能体编排"在本系统检出口径下为**可消融容器**（非主断言）。R4 又获
外部背书：UC Berkeley MAST（NeurIPS 2025，7 框架 41–86.7% 失败率）与
Nature MI 2026（260 配置 MAS 编码全线劣化 −1.3%~−12.8%）——多智能体对
"单链决策类任务（编码/测试生成）"净负已是多方共识。

### 1.2 建设性出路（compilation advantage）

R4 核验的前沿路线：**把 MAS 编译为单智能体技能库**——将各角色的
知识/提示/策略离线蒸馏为一个技能库，推理期单智能体按任务检索技能、
串行执行，省去多智能体的消息编排与上下文膨胀。二手聚合数据（arXiv
2026-01，**正式引用前须核原文**）：−53.7% tokens / −49.5% latency，
精度 ±0。这与项目 C2 的"编排结构 vs 预算混杂"归因（E6 预注册）互补：
若 E6 证实 −28pp 主要来自**编排结构**（而非预算），编译路线是首选出路；
若来自预算，则编译路线仍是成本优化手段。

## 2. 目标与边界

- **目标**：把 Planner / Debugger / PatchApplier 三个角色在现有提示链
  （`src/prompts/templates.py`）与策略库（`src/tools/strategy_bank.py`）
  中的**可复用决策知识**编译为单智能体技能库，使 `plain_llm_df` 式单链
  在"需要时"按技能路由获得角色能力，而不引入多智能体编排。
- **非目标**：不是"删掉多智能体"——多智能体作为**可消融对照臂**保留；
  不是训练/微调（零训练成本）；不是重建一套新框架。

## 3. 编译方案（三阶段）

### 3.1 技能抽取（离线，一次性）

- 输入：`src/prompts/templates.py` 各角色的 prompt 模板 +
  `src/agents/{planner,debugger,generator}.py` 的角色逻辑 +
  `docs/adr/` 中沉淀的决策规则（如 ADR-0016 特异性门、ADR-0020 弃权门、
  ADR-0028 FL 约束门）。
- 输出：`skills/` 技能库，每条技能 = {触发条件, 提示片段, 退出条件}：
  - `detection_first`（先红后绿 CoT，主协议）；
  - `specificity_gate`（过红/抹红判定，ADR-0016）；
  - `fl_constraint`（FL Top-k 定位约束，ADR-0028）；
  - `abstain_gate`（弃权五信号，ADR-0020）；
  - `repair_hierarchy`（确定性优先 → 编辑意图 → 整文件回退，ADR-0019）。
- 人工审核：每条技能须经"无该技能 vs 有该技能"消融验证才入库。

### 3.2 技能路由（推理期，单智能体）

- 单链 `plain_llm_df` 基座上，按任务状态（`state`）动态注入技能提示：
  - 任务开始 → `detection_first`；
  - 首次测试变红 → `specificity_gate` + `fl_constraint`；
  - 修复循环内 → `repair_hierarchy` + `abstain_gate`。
- 复用现有 `state` 通道与 `flags` 开关，不新增执行原语。

### 3.3 对照评估

- 臂：`{plain_llm_df, aitester, df+skills}` × 2 种子 × logic 档 × 双门开，
  与 E6 预算匹配口径对齐（`--per-task-token-caps` 从 E2 实测均值取）。
- 主终点：detection 配对差（McNemar + 贝叶斯 ROPE ±5pp）+ token/latency。

## 4. 与现有架构的接合点

| 现有模块 | 复用方式 |
|---|---|
| `src/prompts/templates.py` | 技能提示的**单一事实来源**（编译输入，不另造模板） |
| `src/tools/strategy_bank.py` | 策略库与技能库合并或映射（避免双源漂移） |
| `src/graph/flags.py` | 技能路由开关沿用现有 `AITESTER_PROFILE` 注入 |
| `src/graph/expert_pool.py` | 专家池可退化为技能库的静态后端 |
| `src/graph/agents_cache.py` | 单智能体复用缓存（编译后不再有多 agent 实例） |

## 5. 风险与停止规则

- **风险 1（技能过拟合）**：技能库在 synthetic 上调优过拟合基准 → 遵循
  预注册"恰好一次"迭代 + 真实基准（QuixBugs）交叉验证。
- **风险 2（编译失真）**：技能抽取丢失角色间的**动态反馈**（如
  contract_reject_feedback 跨轮透传）→ 若 df+skills 未达 aitester 的
  repair 上界，须记录"哪些动态反馈不可编译"，作为反例写入论文。
- **停止规则**：一次性 A/B，无迭代条款（对齐 E6 口径）；技能库 ≥ N 条
  未带来检测增益即记阴性（N 预注册时定，建议 ≥3）。

## 6. 前置与依赖

- 前置：E6 预算归因**先执行**（否则无法区分"编译收益"与"预算变化"）；
- 依赖：`--per-task-token-caps`（已实现，AM 批）、E2 实测均值提取脚本。
- 预算：≈ 4M token（thinking 关口径，与 E6 同量级）。

## 7. 参考

- MAST（NeurIPS 2025）；Nature MI 2026（二手，须核原文）；
- "compilation advantage" arXiv 2026-01（二手，须核原文）；
- 项目 ADR-0016/0019/0020/0024/0028；`docs/preregistration.md` §E6。
