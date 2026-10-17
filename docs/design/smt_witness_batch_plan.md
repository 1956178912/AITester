# z3 SMT 见证层最小启用批次设计（A-18 / P2）

> **性质**：设计文档，**不含实现代码、不含实验数据**。定义"逻辑驱动"第二通道
> （`src/specs/spec_smt.py`，`SPEC_SMT_ENABLE=true` + `[formal]` extra 的 z3-solver）
> 的最小启用批次：目标、设计、判定规则、成本与风险。
>
> **背景**：独立评审（2026-10-17）A-18 指出——z3 SMT 见证层实现在场（731 行，
> SpecIR v2 oracle 的前件求解见证）但**无任何启用批次记录**，属"能力在场、
> 评估缺席"。本设计给出最小可判定批次；在 Q7（是否有历史启用记录）澄清前，
> 任何对外材料不得声称该层"已验证"。
>
> **锚点**：2026-10-17，HEAD 本地 main；写入范围仅本文件。

---

## 0. 一页结论

1. **目标不是证明"逻辑驱动有效"，而是证明"见证层在工作"**：最小批次产出
   UN/SAT 见证率与检出的关联描述，作为"规格可编译率→可求解性→检出"
   这条链的**第一环证据**。
2. **零 LLM 优先**：spec 材料（Planner 的 SpecExpr 子句）从 QuixBugs 的
   Planner 缓存物化（与 `emse_spec_anchor_20261016` 锚表同口径——内容寻址、
   零 LLM）；仅当缓存覆盖率不足时小配额补跑。
3. **判定分两层**：机制层（见证率 > 0 且求解超时率有界）= 层在工作；
   关联层（见证行 vs 未见证行的 detection 差异）= **探索性**，预设检验力
   不足，不得作确认性结论。
4. **风险主项**：z3 求解超时（每子句 timeout 必须有界且计 killed 口径，
   与 cosmic-ray 的 timeout=120s 计 killed 同纪律）；UN SAT 的解释必须
   绑定具体子句（不得汇总成"规格不可满足"的无主语陈述）。

## 1. 事实基线（已核验）

| 项 | 值 | 来源 |
|---|---|---|
| 见证层实现 | `src/specs/spec_smt.py`（731 行），可选依赖 `z3-solver>=4.12.0`（`[formal]` extra） | 仓库（评审 §3.3 核验） |
| 开关 | `SPEC_SMT_ENABLE`，默认关（ADR-0003 口径） | `config.py` + `docs/env_budget.yaml` 在册 |
| SpecExpr 可编译率（新门） | QuixBugs 0.7161 / ULT 0.5937 / synthetic 0.6397 | `layered_narrative.md` §0 |
| 启用批次记录 | **无**（Q7 待澄清） | 评审 §3.4 U7 |
| 同类超时纪律先例 | ULT Mut@k：cosmic-ray timeout=120s 计 killed（ULT 官方口径，2026-10-13 裁定） | `ult_bridge_plan.md` |

## 2. 批次设计

| 项 | 设计 |
|---|---|
| 数据集 | QuixBugs 50 任务（41 缺陷程序口径；与 df_spec 同集，便于跨批对照） |
| 臂 | 单臂观测批（不设对照臂——本批次目的是机制验证，不是效应检验） |
| spec 材料 | Planner 缓存物化（内容寻址，零 LLM）；缓存缺口任务登记 `spec_material_missing` 并剔除 |
| 观测字段（per spec 子句） | `smt_status ∈ {sat, unsat, unknown, timeout, error}`；`smt_solve_ms`；子句文本 sha256（前 16 位） |
| 观测字段（per 任务） | `smt_witness_rate`（可求解子句 / 非空子句）；`smt_timeout_rate`；与既有 `detection_rate` 同行落盘 |
| 求解参数 | 每子句 timeout（建议 5s，探测后按实测分布调整）；超时计 `timeout`（不计 unsat——防"慢"被读成"不可满足"） |
| 协议 | `AITESTER_PROFILE=logic` + `SPEC_SMT_ENABLE=true` + `SPEC_ORACLE_EXEC_ENABLE=true`（并列执行口径，R1c）；temp=0 |

## 3. 判定规则（跑批前落盘，防事后解释）

- **机制层通过**（层在工作）：`smt_witness_rate` 全任务均值 > 0 **且**
  `smt_timeout_rate` < 20% **且** 每个 status 桶的归因可逐子句复算；
- **机制层失败**：rate 恒 0（层未接线/材料未达求解器）或 timeout ≥ 20%
  （参数需重标，不得解读结果）；
- **关联层**（探索性，不做确认性判定）：按 `smt_status` 分桶报告 detection，
  预设披露 MDE（n=41 可判定子集上 MDE ≈ 16pp，与 df_spec 同口径）——
  任何差异 < MDE 一律表述为"方向性描述"，不得用"提升/显著"措辞。

## 4. 成本与风险

| 项 | 评估 |
|---|---|
| LLM 配额 | 0（缓存物化优先）；缓存缺口最坏情况 ≈ df_spec 锚表量级（项目先例 ~$0.3-0.5） |
| 算力 | z3 求解 50 任务 × 子句数（QuixBugs 均 ~3-5 非空子句）× ≤5s → 分钟级 |
| 风险 1 | 求解超时漂移 → 参数重标后重跑（新旧工件都入库，参数变更可审计） |
| 风险 2 | UN SAT 的语义误用（"规格不可满足"≠"实现错误"）→ 报告模板强制绑定子句文本与求解上下文 |
| 风险 3 | 与已冻结工件混口径 → 本批次独立目录（`emse_smt_witness_<date>/`）+ SHA256SUMS + 入库守卫覆盖（A-04 后 emse_* 目录扫描自动覆盖新目录） |

## 5. 与既有路线的关系

- 本批次**不服务**于"规格锚增益"主张（该主张的三次检验均阴性，见
  `layered_narrative.md` §9 与评审 §6 P1 的修复方向）；
- 它服务的是**规格质量的过程指标链**：可编译率（已有，0.59-0.72）→
  可求解性（本批次）→ 检出关联（探索性）。即使全链走完只得到"规格可编译
  可求解但与检出无稳定关联"，那也是可发表的阴性机制证据（本项目已有
  四次同类诚实阴性的发表先例：D1/M4/df_spec/SpecExpr 确认性）。
