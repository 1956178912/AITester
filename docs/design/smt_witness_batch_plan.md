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

---

## 6. 执行记录（T 轮 2026-10-18，**数据产生后追加，设计/判定规则未改**）

> 本节在 §3 冻结规则之后追加；§1–§5 的设计与判定规则逐字未改。执行由 T3b 完成
> （零 LLM），随后由 T3c 修复其错误归因暴露的 `result`/`r` 别名缺口并复跑。

### 6.1 T3b 首跑（pre-fix 基线）

- 数据集：QuixBugs 50 任务（主判定集 = 41 缺陷程序，与 df_spec 同集）；锚表内容寻址
  50/50 命中、缺口 0；z3-solver 5.1.0；per-clause timeout 5s（公开 API 映射见下）。
- 主判定集非空评估子句 D1=184；status 桶：**sat 19 / unsat 0 / unknown 0 / timeout 0 / error 165**。
- `smt_witness_rate` 全任务均值 **0.088531**（>0 ✔）、`smt_timeout_rate`（pooled
  timeout/reached）**0.0**（<20% ✔）、每 status 桶可逐子句重聚合（0 mismatch ✔）
  → **机制层判 `pass`（层在工作）**。
- **reach_rate 仅 0.103261**：到达求解器的 19 条 19/19 全 sat（0 unsat/unknown/timeout，
  求解器无异常），瓶颈是"材料未达求解器"。错误归因（启发式文本，逐子句可复算）：
  `result_alias_not_reached`=110（66%）、`untranslatable_call`=51、其他=5。
- **关联层：不做**。预注册的中位数二分在本数据上退化（median=0，28/41 任务 witness_rate=0
  → 低桶为空），按 §3 只报告"无对照"；MDE≈16.57pp 已披露，未做 detection 比较/检验。
- 工件：`（工件已清除）`（7 项 SHA verify，只读保留为
  pre-fix 基线）。

### 6.2 T3c 别名修复 + 复跑（post-fix）

- 根因定位：`src/specs/spec_smt.py::_collect_post_constraints` 的后件自由变量域只有
  `{"r"}`，而 SpecIR 表达式通道后件普遍引用 `result` → 110 条子句**保守未达求解器**
  （不是求解失败）。修复：token 感知 AST 归一（仅当 `result` 不在签名参数中时把
  后件/不变式 `Name(id="result")` → `r`；解析失败保守回退；参数名确为 `result` 时不归一；
  前件路径零变化；`usable_bool` 保留原始文本）。
- 复跑（同任务/材料/通道/超时/API，差异仅 src 修复）：**reached 19→27、sat 19→27、
  error 165→157（unsat/unknown/timeout 均 0→0）**；`smt_witness_rate` 0.088531→**0.125116**、
  `reach_rate` 0.103261→**0.146739**、有见证任务 13/41→16/41。
- 110 条旧 alias 子句去向：matched=110；→ sat 8、error 102（primary 96 =
  `unsupported_call` 84 + `unsupported_is_in_operator` 6 + `unsupported_subscript` 6）。
  纯别名桶 13→8 reached；余 5 条受 `is`/`in` 算子集限制（非别名问题）。
- 语义安全：solver_exception=0；单子句 unsat 0→0；全组一致性探针新增 unsat 任务 **0**
  （expr 通道 skipped 39→sat 2/skipped 37；NL 生产通道 41/41 不变）；未触发停止条件。
- 工件：`（工件已清除）`（9 项 SHA verify）；
  预注册 `PREREG_ALIASFIX.md` 跑前冻结（含 C1–C5 与风险 guard；预注册预期 reach≈32、
  实测 27 的偏差已披露，仅偏差披露不参与判定）。

### 6.3 口径与后续

- **T3b 与 T3c 并列引用**：T3b = pre-fix 基线，T3c = post-fix 新配置；不得混池、不得删除旧批。
- 剩余能力边界（翻译层算子集不支持 Call/Subscript/Attribute/Is/In）未变——即使别名修复后，
  reach 仍受该层限制；引用"见证率"必须同时给 reach_rate 与"error 归因"。
- 下一步候选：① 扩展翻译层算子集（先白名单评估）；② 关联层需另立新批另预注册
  （本批不得回读做确认性推断）。
