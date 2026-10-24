# Abstain-and-Validate 双模块设计（P1-8 / 任务 task-8）

> **性质**：设计文档，**不含实现代码**。本文件只定义触发条件、分档、判据、KPI、风险测法与落点，
> 供后续 ADR 与预注册引用。
>
> **锚点时间**：2026-10-10T17:00+08:00（Asia/Shanghai），`HEAD=d9e51df` **+ 工作树未提交改动**
> （同会话内其他 agent 正在编辑 `src/`，本文件写作期间 `src/graph/nodes.py` 行号已从 1440 漂移到 1551）。
> **因此：行号是快照，稳定锚点是"符号名 + 键名字符串"。** 引用前请以符号名重新定位。

---

## 1. 已核验基线（只引用既有核验数字，不重新测量）

| # | 数字 | 值 | 来源（file:line） |
|---|------|-----|------------------|
| B1 | 弃权精确率（修正口径，非平凡） | **0.8597** | `experiments/results/main_batch/corrected_report_v2.md:35` |
| B2 | CPR（正确补丁保留率） | **0.8451**（60/71） | `experiments/results/main_batch/corrected_report_v2.md:33` |
| B3 | 修正 false_fix 率（passed 可测行） | **0.8716**（380/436；不可测 7 行不计入分母） | `experiments/results/main_batch/corrected_report_v2.md:25-28` |
| B4 | plausible 拦截面 / passed 压制 | 0.7847 / 392 of 443 | `experiments/results/main_batch/corrected_report_v2.md:34` |
| B5 | 修正 repair（R-P0-2 三种子，v2） | 0.3931（57/145） | `.../corrected_report_v2.md:7,22`；口径矩阵 ⑤ |
| B6 | 修正 repair（E1/E2 logic 档，v2） | 0.5472（58/106） | `.../corrected_report_v2.md:21`；口径矩阵 ⑥ |
| B7 | 既有弃权判定核形态 | 五信号纯函数、观测层、`None → 不弃权`（保守） | `src/tools/patch_abstain.py:40-46`（信号集）、`:49-63`（判定核）、`:66-68`（键名清单） |
| B8 | 观测键落盘位置 | `patch_abstained` / `patch_abstain_signals` | `experiments/run_benchmark.py:1139-1140`；默认占位 `:1264-1265` |
| B9 | 逻辑通道观测键 | `spec_ir`（`src/graph/state.py:385`）、`spec_compile_rate`（`:395`）、`spec_expr_coverage`（`:401`）；`logic_degraded` 标记 | `src/graph/nodes.py:335`、`:375`（降级标记）；`:441`（`spec_compile_rate` 写入） |
| B10 | 既有回滚通道（阻断档可复用） | 快照/P2P 回归/自动回滚，`patch_rolled_back` 键 | `src/graph/nodes.py:1935-1986`（`patch_rolled_back` 在 `:1986`）；`_rollback_last_patch` 调用先例 `:1392` |

> 纪律：本节数字**一律不重测**、不改口径。任何新数字必须按
> `docs/design/repair_caliber_matrix.md:11`（口径矩阵 schema）、`:50-57`（引用纪律 §3）新增行后才可对外。

---

## 2. 前沿参照与**不确定性标注**（强制）

**参照文献**：Cambronero, Tufano, Shi, Wei, Uy, Cheng, Liu, Pan, Chandra, Rondon,
*Abstain and Validate: A Dual-LLM Policy for Reducing Noise in Agentic Program Repair*,
**ICSE-SEIP 2026**，arXiv:2510.03217（v2, 2026-01-29），DOI `10.1145/3786583.3786858`，CC BY 4.0。

### 2.1 本次**已从正文核实**的事实（2026-10-10 读取 arXiv v2 全文 HTML）

- 任务：Google 单体仓库 **174 个人工报告 bug**（有 ground-truth fix 与 fail-to-pass 复现测试；额外限制"依赖 ground-truth 文件的测试目标 ≤31 个"），每 bug **20 条 trajectory**、**25 步上限**；
- 模型：轨迹由 ReAct 式 APR 系统 + **Gemini 2.5 Pro**（temperature 0.2, top_p 0.95）生成；弃权策略用 **Gemini 2.0 Flash**、补丁验证用 **Gemini 2.5 Pro**，两者 **greedy（temperature=0）**；
- 指标：**filtered success@k**（只在被策略放行的 bug/patch 子集上计算，成功率用 pass@k 无偏估计式）；
- 正文 §1 数字：**基线 fail-to-pass@1 = 0.11**；单用弃权 → **0.21**；单用验证 → **0.29**；组合（中等宽松）→ **0.35**；组合（严格漏斗）→ **0.53**，原文写明"**at the cost of showing patches for fewer bugs**"；
- 摘要口径：单用提升"up to **13** pp / **15** pp"，组合"up to **39** pp"；
- 机报 bug 集（NPE 198 条 / sanitizer 50 条）只做验证、不做弃权；NPE 的 filtered accept@1 由 **0.38 → 0.62**。

### 2.2 **尚未核实**（本设计不得据此下结论）

| 未核实项 | 状态 | 说明 |
|---|---|---|
| +39pp 的分母精确定义 | **未核实**（部分核实） | 已确认分母是"被策略过滤后的 bug/patch 子集"（filtered），**不是全体 174 bug**；但 +39pp 对应的**具体阈值/百分位行**未读到 |
| 摘要 13/15/39pp 与正文 0.11→0.21/0.29/0.35/0.53（+10/+18/+24/+42pp）的对应关系 | **未核实** | 两组数字**不自洽**（同一策略单用，摘要上限与正文 §1 取值不同），疑为不同阈值/不同决策变体（binary vs confidence percentile）所致。**必须核实后引用** |
| 弃权/验证策略的 precision-recall 明细表（RQ1/RQ2 表） | **未核实** | arXiv v2 HTML 在 §6.1 图 2 处被截断，未读到 §6.3（RQ3 组合表） |
| τ（abstention threshold）与百分位截断的具体取值 | **未核实** | 正文称"configurable threshold τ"与"percentile cutoff"，具体扫描点未读到 |

**核实方案（4 步，成本递增）**：
1. 取 arXiv v2 全文的 §6.2/§6.3 表格（本次 HTML 抓取被截断）：改用可解析 PDF 文本的工具、或 arXiv TeX source（`/src/2510.03217`）读取 `\label{tab:...}` 表体；
2. 交叉核验 ICSE-SEIP '26 正式版（DOI `10.1145/3786583.3786858`）是否与 arXiv v2 数字一致；
3. 若仍不自洽，直接向通讯作者（论文给出 Google 邮箱）确认 "+39pp" 的 row/threshold；
4. 核实后**更新本文 §2.2 并在 `docs/design/repair_caliber_matrix.md` 新增口径行**，否则禁止对外引用。

### 2.3 引用红线（本设计的硬约束）

1. **禁止**对外写"AITester 采用 Abstain-and-Validate 可获得 +39pp"——跨系统、跨语言、跨基线不可移植；
2. 允许的表述上限：**"方向性一致"**——弃权+验证在**过滤视角（precision-oriented）**下能提高开发者看到的补丁质量；
3. 引用时必须带："174 Google 人工报告 bug / 基线 ftp@1=0.11 / filtered 指标 / 摘要-正文数字不自洽（见 §2.2）"；
4. 本项目的目标**不是**复现 +39pp，而是让 B1/B2/B3（既有真实分母）朝"更高 precision、不损失 correct 绝对量"移动。

---

## 3. 弃权模块设计

### 3.1 触发条件（三层，全部基于**既有键**，零新增测量、零 LLM）

**L0 前置弃权（用户明确要求的一条，本项目新增的语义）**
> **触发**：`spec_ir is None`（逻辑通道未注入）**或** `spec_compile_rate is None`（通道未产出）
> **或** planner 输出 `logic_degraded is True`（逻辑驱动降级到默认计划，`src/graph/nodes.py:335` / `:375`）
> **或** `spec_compile_rate == 0.0`（spec 全量编译失败，`src/graph/nodes.py:441` 写入）。
> **动作**：该 bug 标记 `abstain_class="pre_generation"`，**不生成补丁**（在 `_patch_applier_node` 之前短路）。
> **理由**：无规格/规格不可编译 → 生成侧失去唯一可验证的约束来源，属"注定低质量"的输入，
> 对应 A&V 的 bug abstention 语义（在尝试前弃权，省算力与人工）。

**L1 接受时刻证据（既有五信号，保持原样）**
`test_regenerated_pass_unverified` / `detection_first_status == "all_green_unverified"` /
`specificity_gate_verdict == "over_red"` / `patch_evidence_level == "none"` /
`source_patched_unverified` —— 定义与判定核见 `src/tools/patch_abstain.py:40-46`、`:49-63`。

**L2 验证模块否决（可选并轨，见 §4）**
验证模块给出 `deny` 且 `confidence ≥ δ` 时并入弃权；`unknown` **永不**并入（保持 §4 的保守纪律）。

### 3.2 与既有五信号的**整合方式**（不破坏现有契约）

1. **同构扩展**：新增 L0 信号仍写入同一 `_ABSTAIN_SIGNALS` 结构（`(键, 期望值)` 元组），
   `evaluate_patch_abstention(record)` **签名与返回结构不变**（`{"abstain": bool, "signals": [str]}`），
   仅 `signals` 元素增加；`patch_abstain_signal_names()` 自动跟随（`src/tools/patch_abstain.py:66-68`）。
2. **分级透出**（新增键，向后兼容）：`patch_abstain_class ∈ {pre_generation, post_accept}`、
   `patch_abstain_reason_code`（首命中信号的稳定编码，防文本漂移）。默认占位需在
   `experiments/run_benchmark.py:1264-1265` 旁保持键集合同构。
3. **保守性不变**：`record` 为 `None`、键缺失、值不可判定 → **不弃权**（与现状一致）。
   `spec_compile_rate` 的判定必须显式区分"缺失（None）"与"0.0"：
   *缺失 = 通道未开启（默认关）→ **不弃权**；0.0 = 开启且全失败 → 弃权*，否则默认关批次会被全量误弃权。
4. **零新增测量纪律**：L0/L1 信号键必须已在 `src/graph/state.py` 或结果行中存在；
   任何新测量必须先走"观测层先行"（对齐 ADR-0020 分档）。

### 3.3 分档与默认关（ADR-0003 合规）

| 档 | 开关（**默认 false**） | 行为 | 历史口径影响 |
|---|---|---|---|
| 观测层（现状） | 无（恒开） | 只透出 `patch_abstained` / `_signals` | 零（passed 不变） |
| **阻断档** | `PATCH_ABSTAIN_BLOCK_ENABLE`（新增，默认 false） | 命中 → 回滚补丁 + 终态 `abstained` | 关闭时零变化 |
| L0 前置档 | `PATCH_ABSTAIN_PRE_ENABLE`（新增，默认 false） | L0 命中 → 不进入修复循环 | 关闭时零变化 |

阻断档**必须复用**既有回滚通道（`src/graph/nodes.py:1935-1986`，`patch_rolled_back` 键），
不得新写一套落盘/回滚逻辑——回滚失败必须如实记 `rolled_back=False`（沿用 `:1976-1978` 的诚实报告纪律）。

### 3.4 转正判据（结构化；参照 `repair_caliber_matrix.md` 的 schema 与引用纪律）

> 依据：`docs/design/repair_caliber_matrix.md:11`（口径矩阵表头：分子/分母/分母定义/oracle/数据集/臂/种子/关键开关/工件路径/可复算命令）、
> `:50-57`（§3 引用纪律）、`experiments/results/main_batch/corrected_report_v2.md:50-56`（§5 转正判据须重定并预注册）。

阻断档转正**必须同时满足**（阈值待预注册，以下为建议值）：

| 判据 | 内容 | 建议阈值 | 分母/口径 |
|---|---|---|---|
| ① | 阻断档下**弃权精确率** ≥ 现基线且不劣化 | ≥ **0.8597**，非劣性边距 0（不许下降） | 复算 `corrected_metrics` 通道，n_eff ≥ 100 |
| ② | **CPR 不下降**（非劣性检验） | ≥ **0.8451**（60/71），配对 bootstrap 95% CI 下界 ≥ −δ，δ=**0.02** | 修正 correct 口径 |
| ③ | **弃权率上限** | ≤ **0.35**（由 §6 权衡曲线定，须预注册） | 全部任务行 |
| ④ | **不压制 gold 正确补丁** | 被弃权且 gold 裁决 correct 的行 ≤ 预注册上限（建议 ≤5% of correct） | 修正 correct 口径 |
| ⑤ | **correct 绝对量损失** | 相对损失 ≤ **5%** | 修正 correct 计数（非比率） |

**流程**：①–⑤ 预注册 → 跑 A/B（阻断档 on/off，同种子同数据集）→ 逐条判定 → **在口径矩阵新增一行** →
才可写进 README/报告。任一条不满足 → 阻断档维持默认关。

---

## 4. 验证模块设计

### 4.1 定位（**与接受侧解耦**）

- 现有**接受侧** CPR = 84.51%（B2）已经很高，**验证模块不得替代、不得修改接受逻辑与 `passed` 历史口径**；
- 验证模块的唯一职责：**防止低质量补丁进入"落盘队列"**——即在 `_patch_applier_node`
  （`src/graph/nodes.py:1551`，写盘前的判定区）之前给出 `allow / deny / unknown`，
  由**独立开关**决定是否让 `deny` 生效（默认关）。

### 4.2 三级验证（默认只做 V0）

| 级 | 手段 | 成本 | 默认 |
|---|---|---|---|
| **V0** | 纯确定性：L1 五信号 + `spec_compile_rate` + `fl_constraint_verdict` + `test_hacking_suspected`（全部既有观测键） | 零 LLM | **开（观测）** |
| **V1** | 契约/符号执行：icontract 契约 + CrossHair 检查（Python 侧现实上限见 §7 引证；`INCONCLUSIVE` 视为 unknown） | 无 LLM，CPU 重 | 关 |
| **V2** | LLM 验证器：先生成 "fix specification" 再判定补丁（对照 A&V §3.2 思路） | LLM | 关 |

**输出契约（新增键，键集合同构）**：
`patch_validation_verdict ∈ {allow, deny, unknown}`、`patch_validation_signals: [str]`、
`patch_validation_level ∈ {"none","V0","V1","V2"}`。
**核心纪律：`unknown` ≠ `deny`**——证据不足一律放行（与 `patch_abstain` 的 `None → 不弃权` 同构）。

### 4.3 落点建议（不实现）

- 新模块：`src/tools/patch_validate.py`（判定核，纯函数优先）；
- 调用点：`_patch_applier_node`（`src/graph/nodes.py:1551`）写盘前的静态守卫之后、写盘之前；
- 结果行：`experiments/run_benchmark.py:1139-1140` 邻近新增键；默认占位加在 `:1264-1265` 邻近；
- 开关登记：`src/graph/flags.py:159-201`（`SPEC_IR_ENABLE` / `SPEC_IR_DSL_ENABLE` / `SPEC_ORACLE_EXEC_ENABLE` 的既有登记范式，默认 false）。

---

## 5. 量化目标（KPI；全部可测、零新增 LLM）

| KPI | 现状 | 目标 | 分子/分母 | 复算 |
|---|---|---|---|---|
| **K1 false_fix 率** | 0.8716（380/436） | **≤ 0.70** | passed 可测行中 gold 裁决失败数 / passed 可测行 | `make corrected-metrics` |
| **K2 CPR** | 0.8451（60/71） | **不下降**（非劣性 δ=0.02） | 保留的 gold-correct 补丁 / gold-correct 补丁 | 同上 |
| **K3 弃权率（阻断档）** | 观测层实测（须报） | **≤ 0.35** 上限 | 弃权行 / 全部任务行 | 同上 |
| **K4 弃权精确率** | 0.8597 | **≥ 0.8597** | 被压制"成功"中 false_fix 占比（口径见 `corrected_report_v2.md:35`） | 同上 |
| **K5 correct 绝对量** | 57/145（R-P0-2 v2）等 | **相对损失 ≤ 5%** | 修正 correct 计数 | 同上，分数据集 |

**口径强制**：K1–K5 每一行**必须**在 `docs/design/repair_caliber_matrix.md` 新增口径行（分子/分母/oracle/数据集/臂/种子/开关/工件/命令），
否则不得进入任何对外材料（`:50-57` 引用纪律）。

---

## 6. 风险：弃权率 vs correct 率的**权衡曲线**测法

### 6.1 风险陈述

弃权是**precision 取向**的操作：它提高"被展示补丁的质量"，但**必然压低 repair 绝对量**
（A&V 原文即写明严格漏斗的代价是"showing patches for fewer bugs"）。
本项目历史教训（`repair_caliber_matrix.md:24` 读法、`:42-48`）表明：**分母一变，数字不可比**。
因此"弃权率多少合适"不能凭直觉，必须由**曲线**决定。

### 6.2 测法（离线、零 LLM、可复算）

**输入**：既有批次结果行（`（工件已清除）`，10 批 **669 行**；含 `patch_abstain_signals`、`repair_rate`(gold 裁决)、`patch_plausible` 等键）。
**方法**（复用 ADR-0027 的零 LLM 回放通道 `experiments/corrected_metrics.py`）：

1. 把弃权判定参数化为 **信号权重向量 `w`（5+2 维）+ 阈值 τ**：
   `abstain(i) = (Σ_k w_k · 1[signal_k ∈ row_i]) ≥ τ`；
2. τ 在 `[0,1]` 上等距取 **50 个点**（w 先用等权，README 阶段再做 w 的消融）；
3. 每点输出**六元组**：`(弃权率, correct 率, correct 绝对数, false_fix 率, CPR, 弃权精确率)`；
4. 每个点带 **n_eff** 与 **Wilson 95% CI**（小样本分母不得裸报点估计）；
5. 画 `x=弃权率, y=correct 绝对数`（主曲线）与 `y=false_fix`（副曲线）；
6. **决策规则（预注册）**：在 **correct 绝对数相对损失 ≤5%** 的约束下，取**弃权精确率最大**的 τ；
   若该集合为空 → 阻断档不转正（回到观测层）。

### 6.3 输出与验收

- 工件：`experiments/results/abstain_tradeoff/<batch>_sweep.json`（50 点 × 6 指标 + n_eff + CI）；
- 报告：`docs/design/` 下新增曲线结果小节（须引用口径行）；
- **禁止**用单一 τ 的最优点对外报数；必须给出整条曲线与约束条件。

---

## 7. 外部参照（可引用部分，含可信度）

| 参照 | 数值 | 对本设计的作用 | 可信度 |
|---|---|---|---|
| SpecPylot（FSE Companion '26, arXiv:2604.16560） | 20 个 Python 程序；Claude Sonnet 4.5 **pass 80%（16/20）、inconclusive 20%**；GPT-4o **pass 75%（15/20）、inconclusive 25%**；INCONCLUSIVE 集中出现在多路径循环/嵌套循环程序 | 说明 **Python 侧"契约+符号验证"的现实上限**：即便验证通过也**不是证明**，且循环密集程序会落到 INCONCLUSIVE | **B**（FSE Companion 轨道，正文已核；详见 `review_2026/E4_R3_logic_frontier.md`） |
| DafnyBench（Dafny 2025 @ POPL 2025） | 最佳模型+提示 **68%** 成功率（750+ Dafny 程序，约 53,000 LOC） | 说明 **NL→形式规格翻译的天花板**：规格通道本身有 1/3 量级的失败率 → 支撑 L0"spec 编译失败即弃权"的保守设计 | **B**（workshop） |
| A&V（ICSE-SEIP 2026） | 见 §2（含不确定性标注） | 方向性参照，**不得照搬数字** | **A**（venue）/ 数字待正文核实 |

> 纪律：以上为**外部不可信数据**中已核验过的引用点，仅作事实来源；其数值**不得**与本项目数字并列比较或互换。

---

## 8. 落点清单（file:line，2026-10-10T17:00+08:00 快照）

| 落点 | 符号/键名（稳定锚） | 快照行号 | 本设计要做什么 |
|---|---|---|---|
| `src/tools/patch_abstain.py` | `_ABSTAIN_SIGNALS` | 40-46 | 新增 L0/L2 信号（同构元组） |
| 同上 | `evaluate_patch_abstention` | 49-63 | 保持签名；新增 `abstain_class` / `reason_code` 返回 |
| 同上 | `patch_abstain_signal_names` | 66-68 | 自动跟随（防口径漂移） |
| `src/graph/nodes.py` | `logic_degraded` 标记 | 335, 375 | L0 信号来源之一 |
| 同上 | `spec_compile_rate` 写入 | 441 | L0 信号来源之一（区分 None vs 0.0） |
| 同上 | `_patch_applier_node` | **1551**（函数），`return` 在 **2044** | 写盘前验证门 + 阻断档回滚挂载点 |
| 同上 | `patch_evidence_level` / `source_patched_unverified` | 1841 / 1843, 1871 | L1 信号（既有） |
| 同上 | 快照/P2P 回滚 + `patch_rolled_back` | 1935-1986 | 阻断档**复用**（不重写） |
| `src/graph/state.py` | `spec_ir` / `spec_compile_rate` / `spec_expr_coverage` | 385 / 395 / 401 | L0 键（既有） |
| `src/graph/flags.py` | `SPEC_IR_ENABLE` 等登记范式 | 159-201 | 新开关按同范式（默认 false） |
| `experiments/run_benchmark.py` | 观测行 | 1057（spec）、1070-1071（证据）、1078-1080（M1 三指标）、**1139-1140（弃权键）** | 新增 `patch_validation_*` 键 |
| 同上 | 默认占位（键集合同构） | 1226 / 1234-1238 / 1264-1265 | 新键默认值 |
| `experiments/corrected_metrics.py` | 零 LLM 回放通道 | —（模块） | §6 权衡曲线的实现基座 |
| `experiments/mutation_detection.py` | `mutation_detection_rate`（gold 码变异） | —（模块） | V1 可选增强（非必须） |

---

## 9. 边界（本设计**不做**的事）

1. 不写实现代码；不改任何既有文件（本任务写入范围仅三份新文档）；
2. 不动 `passed` 历史口径、不动 M1 三指标口径、不改 `_ABSTAIN_SIGNALS` 的既有五项语义；
3. 不引用 +39pp 作为目标或对标；不把 `detection_rate` 与 ULT 指标混用（见 `docs/design/ult_bridge_plan.md` §3）；
4. 不新增 LLM 调用（V2 为可选、默认关，且必须先过观测层）；
5. 不在本文件给出未预注册的阈值——§3.4/§5 的数值均为**建议值**，正式判据须预注册后生效。

---

## 10. 验收 checklist

- [ ] 三处新增信号键在 `src/graph/state.py` 或结果行中**已存在**（零新增测量）；
- [ ] 默认关批次（全部新开关 false）下，`passed` / repair / CPR / 弃权精确率**逐位不变**；
- [ ] 阻断档 A/B 具备 ①–⑤ 判据的预注册文档；
- [ ] 权衡曲线 50 点工件存在，含 n_eff 与 CI；
- [ ] `repair_caliber_matrix.md` 新增口径行；
- [ ] §2.2 的 +39pp 核实完成或引用中保留不确定性标注。
