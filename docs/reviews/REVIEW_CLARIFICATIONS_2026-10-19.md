# 第三轮独立评审「待澄清事项」逐条回应（2026-10-19，零 LLM）

> **性质**：对 `docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md` §15
> 八项待澄清问题的集中回应。此前答案散落在登记册、ADR、论文与各轮审计报告中，
> 评审方需跨 4+ 份文档拼合，故此处收敛为单一入口。
>
> **纪律**：凡已有工件/文档证据的，给出**路径 + 复算命令 + 数字**；属项目管理
> 决策的，明确标注「待项目方裁定」，不代为假设填充。
>
> **结论**：8 项中 **5 项已闭合**（1/2/5/6/8）、**2 项待项目方裁定**（4/7）、
> **1 项未做且有明确代价**（3）。

## 1. 逐条总览

| # | 问题 | 状态 | 一句话答复 |
|---|---|---|---|
| 1 | ULT accuracy 21.0%（42/200）的复算路径 | ✅ **已闭合**（X 轮） | 脚本 `experiments/emse_ult_dfsmoke_accuracy.py` 已入库；工件 `emse_ult_df200_20261017/ACCURACY_REPORT.json` |
| 2 | `SPEC_SMT_ENABLE` 是否有端到端批次 | ✅ **已闭合**（T 轮 T-3b/T-3c） | 首个专项批已执行（QuixBugs 41 程序、零 LLM）；**能力边界**：仅"层在工作" |
| 3 | synthetic 50 模板的代表性标定计划 | ❌ **未做**（有明确代价） | 需 Defects4J 子集 + LLM 预算；当前以"合成缺陷"为范围边界披露 |
| 4 | E7 时间表与 n 口径（8 vs ≥40）裁定 | ⏳ **待项目方裁定** | n 口径已有统计依据（见 §4）；执行时间表未定 |
| 5 | `orchestration_search` 解锁时间表 | ✅ **已记录**（ADR-0034） | 五条件 a–e 在案；优先级排在 B1/T-1/P1 之后 |
| 6 | CI 门禁数量的权威口径 | ✅ **已闭合**（X 轮） | **26 脚本 / 24 唯一路径 / 27 调用点**，权威 = `BASELINE.yaml#gates` |
| 7 | 是否接受报告第 12 节路线图与优先级 | ⏳ **待项目方裁定** | 项目方未作正式答复 |
| 8 | B2 `not_reproduced` 后主叙事与 2×2 时间表 | ✅ **已闭合**（论文 §sec:tround） | 双批并列、**永不混池**；2×2 已预注册为 E8 |

## 2. 已闭合项的证据与复算

### 2.1 ULT accuracy 21.0%（问题 1）

**工件**：`experiments/results/emse_ult_df200_20261017/ACCURACY_REPORT.json`

```
benchmark        : .../benchmark_ult_20261017_110803.json
arm              : plain_llm_df
caliber          : green_on_fut（生成套件在 task_metadata.fixed 上 30s 内通过）
counts           : pass=42, fail=158, nonterminate=0, material_missing=0
denominator      : 200
accuracy         : 0.21
records          : 200
```

**复算命令**（零 LLM，脚本已于 X 轮入库）：

```bash
python experiments/emse_ult_dfsmoke_accuracy.py \
    --benchmark experiments/results/emse_ult_df200_20261017/benchmark_ult_20261017_110803.json \
    --arm plain_llm_df \
    --out /tmp/ACCURACY_REPORT.json
```

**口径说明**：`accuracy = pass / (pass + fail + nonterminate)`，`material_missing`
单列不进分母（预注册 `ULT_DFSMOKE_PREREG_2026-10-17.md` §3）。X 轮复算 200 条
记录的语义字段逐位一致（仅计时字段有差异）。

**重要边界**：库内有两个 ULT accuracy 工件，口径相同但批次规模不同——

| 工件 | counts | 分母 | accuracy |
|---|---|---|---|
| `emse_ult_dfsmoke_20261017` | pass=2 / fail=18 | **20** | **10.0%** |
| `emse_ult_df200_20261017` | pass=42 / fail=158 | **200** | **21.0%** |

**评审问的是后者（42/200 = 21.0%）**。引用时必须带批次标签，不得混用。

### 2.2 `SPEC_SMT_ENABLE` 端到端批次（问题 2）

**状态**：T 轮 T-3b/T-3c 已执行首个专项批，登记册 Q7 已收口。

**工件**：`experiments/results/t_round_smt_witness_20261018/`、
`experiments/results/t_round_smt_witness_aliasfix_20261018/`

**已记录结果**（QuixBugs 41 缺陷程序、零 LLM，权威字段见 `BASELINE.yaml` §smt_witness）：

| 阶段 | witness_rate_mean | tasks_with_witness | reach_rate | reached | verdict |
|---|---|---|---|---|---|
| pre-fix（T3b） | 0.088531 | 13/41 | 0.103261 | 19 | **pass**（机制层） |
| post-fix（T3c，`result`/`r` 别名修复） | 0.125116 | 16/41 | **0.146739** | 27（+8） | — |

`timeout = 0`、桶可逐子句复算。

**能力边界（必须一并引用，不得单独摘取）**：

> 仅证明"该层在工作"，**关联层因中位数二分退化无对照**（median=0，28/41 任务
> `witness_rate=0` → 低桶为空，按预注册只报告无对照；`MDE ≈ 16.57pp` 已披露；
> 未做 detection 比较/检验）。引用时必须给出 `reach_rate` 与 error 归因，
> **不得**表述为"见证提升检出"。

**z3 安装记录**：`pip install "aitester[formal]"`（`pyproject.toml` 的 `formal`
extra）；`SPEC_SMT_ENABLE` 默认关（ADR-0003 口径），在 `docs/env_budget.yaml` 在册。

### 2.3 `orchestration_search` 解锁条件（问题 5）

**依据**：`docs/adr/0034-orchestration-search-freeze-and-unblock.md`

**五条解锁条件**（全部满足方可排批）：

| 条件 | 内容 |
|---|---|
| a | **预注册先落盘**：臂函数评估预算 / token 硬顶 / 主终点（M1 detection，gold 独立裁决）/ 停止规则 / 多重比较校正方案 |
| b | **等预算纪律**（E6 教训）：champion 必须与 `plain_llm_df` 在**匹配预算**下对照 |
| c | 前置闸全绿：`run_preflight`（配额 / 指纹 / 干净树）+ `batch_quota` 硬上限 |
| d | 奖励口径跑批前后一致 = M1 `detection_rate`（不得事后更换终点） |
| e | 16 臂多重比较须带校正（BH-FDR 或预注册层级检验） |

**时间表**：**未排期**。ADR-0034 §3 明确当前 LLM 预算排序中 B1 2×2 消融 /
T-1 ULT accuracy / P1（df_spec 规格锚臂）实跑均优先于本项。
**决断期限**：若至下一投稿周期仍未实跑，二选一——删除模块，或降格为
`experimental/` 标注 + 论文明确"未执行"。

**冻结期禁令**：任何文档 / 论文 / README / BASELINE 不得出现"bandit 自动搜索
提升 X"类表述；允许的最强表述是"已实现并测试、待预注册实跑的搜索机制"。

### 2.4 门禁数量口径（问题 6）

| 口径 | 数值 | 来源 |
|---|---|---|
| 磁盘脚本数 | **26** | `ls scripts/gates/*.py \| wc -l` |
| `ci.yml` 唯一引用路径 | **24** | `.github/workflows/ci.yml` |
| 调用点（含重复调用） | **27** | 同上 |

**权威来源**：`BASELINE.yaml#gates`。三者差异的原因是两个脚本由专用工作流
（非 `ci.yml`）调用、且存在同一脚本多调用点，**不是矛盾**。

### 2.5 B2 `not_reproduced` 后的主叙事（问题 8）

**依据**：论文 `paper/draft.typ` §`sec:tround`（"A fingerprint-locked replication,
and what drifted"）与 §"Model and inference settings"。

**论文的三条明确处置**：

1. **双批并列、永不混池**：原文 "we report both batches side by side with batch
   labels and **never pool them**"；
2. **旧批的证据等级披露**：主批在 provider 默认推理模式（thinking on）下运行，
   锁定指纹批及之后的确证性运行均 `LLM_THINKING_MODE=disabled`；"a batch without
   a pinned fingerprint is excluded from confirmatory claims"；
3. **核心负向对比仍显著**：`aitester` vs detection-first prompt δ = −25.29pp
   （b=4, c=70, exact McNemar p≈0, bootstrap 95% CI [−31.0, −19.5] pp）；而
   *次序*复现（`plain_llm_df > aitester > plain_llm`）在 0/3 seed 成立。

**2×2 消融**：已预注册为 **E8**（`docs/preregistration.md`），
`{thinking on/off} × {legacy/current profile}`，判据在任何运行前冻结。
**时间表**：属 LLM 配额项，未排期（需项目方授权预算）。

## 3. 未做项：synthetic 代表性标定（问题 3）

**现状**：主实验在 synthetic 数据集上运行（50 缺陷模板族）。项目**未**在
Defects4J 子集上验证 detection 主张的代表性。

**代价与理由**：

- Defects4J 子集验证需要真实 LLM 调用（配额项），不属于零 LLM 可完成范围；
- 项目的范围主张已通过披露而非回避处理：论文把 synthetic 作为**范围边界**明示，
  且 ULT-lite46 的结果（detection 全 0，无判别力）已作为"跨数据集迁移不可假定"
  的负面证据在案。

**建议**（待项目方定）：若审稿要求迁移性证据，最小可行方案是在 Defects4J 的
`Lang` 或 `Chart` 子集上跑 10–15 个任务的 detection 对照（单一子集、单一基线臂），
预算量级与 B1 2×2 相当。

## 4. 待裁定项：E7 时间表与 n 口径（问题 4）

### 4.1 n 口径的统计依据（已可判定，Y 轮补入）

`docs/HUMAN_ADJUDICATION_PROTOCOL.md` §2.2 已给出「0 个 equivalent 观察下的真零
上界」：

| 样本量 | 0 observed 上界（rule of 3） | 0 observed 上界（Wilson） | 1 observed 上界（Wilson） | 人工成本 |
|---|---|---|---|---|
| n=8（路径 A） | 37.5% | 32.4% | 47.1% | ~1 小时 |
| n=41（路径 B） | 7.3% | 8.6% | 12.6% | ~4–7 小时 |
| n=72（全框普查） | 4.2% | 5.1% | 7.5% | ~6–12 小时 |

**统计结论（可不依赖项目管理决策）**：n=8 的 0 观察只能把真实等价率压到 32%
以下，**不足以支撑论文"repair=0 为真零"的定量表述**；n=41 压到 9% 以下。

### 4.2 仍未定的两件事（**待项目方裁定**）

1. **走哪条路径**：A（n=8，1 小时）/ B（n=41，4–7 小时）/ 全框普查（n=72，6–12 小时）；
2. **执行时间表**：需人工逐条判读，无法由零 LLM 流程代劳。

**备料状态**：两条路径的候选清单与复核工作表均已生成（`e7_repair_sample_candidates{,_n41}.md`
与 `e7_review_worksheet{,_n41}.md`），且已验证 n=8 ⊆ n=41（前 8 行完全一致），
升级路径 B 时零返工。

## 5. 待裁定项：路线图接受与否（问题 7）

评审报告第 12 节给出 P1/P2/P3 优先级排序与路线图。**项目方未作正式答复**，
本节不代为表态。

**可供决策的事实基线**（截至 2026-10-19）：

- P1 中已完成的：B1 协议文本复现（T 轮，+16.1/+19.5pp confirmed）、评测诚信
  checklist（P3，U 轮）；
- P1 中受预算约束未排期的：B1 2×2、ULT accuracy 扩样、TestGenEval-Lite、B2 指纹重跑；
- 已冻结的：`orchestration_search`（ADR-0034）。

## 6. 后续维护约定

- 本文件为**八项问题的权威回应入口**；后续任何一项状态变化（如 E7 完成、
  2×2 实跑），须同步更新本表并追记日期；
- 新增评审轮次如提出重复问题，应先查本文件再向项目方提问；
- 本文件不含任何未经工件支撑的数字。

## 附录：证据索引

| 项 | 路径 |
|---|---|
| ULT accuracy 工件 | `experiments/results/emse_ult_df200_20261017/ACCURACY_REPORT.json` |
| ULT 复算脚本 | `experiments/emse_ult_dfsmoke_accuracy.py` |
| SMT 专项批 | `experiments/results/t_round_smt_witness{,_aliasfix}_20261018/` |
| 编排搜索冻结 | `docs/adr/0034-orchestration-search-freeze-and-unblock.md` |
| 门禁口径 | `BASELINE.yaml#gates` |
| B2 与漂移 | `paper/draft.typ` §`sec:tround`、§"Model and inference settings" |
| E7 口径与备料 | `docs/HUMAN_ADJUDICATION_PROTOCOL.md` §2.1–2.2 |
| 预注册（含 E8） | `docs/preregistration.md` |
