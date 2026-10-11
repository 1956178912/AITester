# AITester 独立评审报告（外部评审版·单文件自包含）

> **文件性质**：单一自包含交付件。正文 = 独立评审报告；附录 A–F = 支撑该报告的**全部原始审计工件**，
> 每个数字均可回溯到附录中的具体表格、命令与工件路径。
> **评审对象**：`/Users/wangchenyu/Workspace/AITester`（Python，工作树 HEAD `d9e51df` + 33 个未提交修改文件）
> **评审日期**：2026-10-11 · **报告版本**：v1.1（外部评审版，含对抗式验证勘误）
> **总规模**：约 2.9 千行 / 26 万字符；含 1,252 行表格（约 60 张表）；附录 A–F 为完整审计工件。

---

## 给外部评审者的导读

### 这份报告的立场

本报告是一次**独立评审**：项目内既有的 6 份评审材料（9,654 行）与全部自评数字**均被当作"待验证声明"**，
不作为事实来源。项目侧每一个数字都由本次评审**直接解析原始工件**（`experiments/results/**/*.json`、
`*.trace.jsonl`）重新计算得到；前沿每一个数字都回溯到**一手来源**（arXiv 原文、Crossref 机读元数据、
SWE-bench 官方榜单仓库的逐条结果文件）。

### 证据分级（全文统一）

| 等级 | 定义 | 可用于 |
|---|---|---|
| **A** | 一手可逐条复算：原始工件逐位复算一致，或 arXiv/DOI 原文数值逐字命中且元数据经机读核验 | 独立支撑关键结论 |
| **B** | 一手存在但条件不完整（预印本、摘要级、付费墙、口径需限定） | 需交叉验证后方可支撑 |
| **C** | 二手（综述转述、博客、项目内引用） | 仅作参考，**不得单独支撑结论** |
| **D** | 不可验证 / 检索无命中 / 疑似不存在 | **不得支撑任何结论** |
| **E** | 推测（本报告仅用于 §6 的预期提升，且已逐条标注） | 必须标注为推测 |

### 三条阅读规则（避免误读本报告）

1. **分母纪律**：项目侧 detection/repair 一律区分三套分母 ——
   `all-task`（全部任务）/ `measurable`（有 gold 材料可测）/ `replayable`（可重放）。
   全文凡出现单值处，必在该段或表中注明分母。
2. **"不可比"不是"差"**：§5 对比矩阵中标注"否（无可比条件）"的维度，表示**项目与前沿的度量对象不同**
   （例如项目的 `spec_compile_rate` 度量"规约子句能否编译"，前限度量"生成的测试能否运行"），
   **不代表项目在该维度落后 400 倍**。
3. **负结果优先**：本项目最重要的发现是**推翻性的**。若你只想读结论，请读 §0，
   再读 §3.4（机制归因被推翻）、§3.7（真实基准结论不成立）、§11（既有评审逐条复核）。

### 如何独立验证（三步，零 LLM）

```bash
cd /Users/wangchenyu/Workspace/AITester

# 第 1 步：复算核心三臂指标（附录 A/E 的数字来源）
.venv/bin/python - <<'PY'
import json, glob
for f in sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json")):
    for arm, v in json.load(open(f))["results"].items():
        d = v["details"]
        print(f, arm,
              "det=",  sum(1 for x in d if x.get("detection_rate") == 1.0),
              "meas=", sum(1 for x in d if x.get("detection_rate") is not None),
              "rep1=", sum(1 for x in d if x.get("repair_rate") == 1.0))
PY

# 第 2 步：独立重放修复验证（约 200 秒；附录 F 的来源）
.venv/bin/python -m experiments.repair_replay \
  experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester

# 第 3 步：抽查引用真实性（附录 D 的方法）
curl -s https://api.crossref.org/works/10.1145/3803418 | head -c 400
curl -s "https://export.arxiv.org/api/query?id_list=2609.09315" | head -c 400
```

### 已自曝的局限（请一并评估）

1. 本次评审**未调用任何 LLM API**，因此无法重跑实验，只能对**入库工件**做重算与重放；
2. 覆盖率声明（89% / 83%）因仓库 `.coverage` 退化而**无法验证**，已标 E 级；
3. 对抗式验证（附录 E）由 **Lead 自查**完成，**不构成完全第三方复核**——这正是本文件交付外部评审的原因；
4. **本报告经过两轮更正，痕迹均保留**：
   - 第一轮（自查）：§3.4.2 反事实分解口径算错（写成"88%"），已就地更正并留注记；
   - 第二轮（独立对抗式验证，附录 E）：查出 **S1 伪重复对齐方式错误**（143/261 → **252/261**）、**S2 门交叉表"例外"表述错误**（**真实分歧实为 0**）、**S3 oracle 普查 scope 错误**（1,803 → 全库 **2,015**）等 **10 项**，逐条更正见 **§17.1 勘误表**。
   - 若你发现本报告与附录数字不一致，**以原始工件复算为准**，并把差异反馈给我们——这正是本文件交付外部评审的目的。

### 目录与交叉引用映射

**正文（独立评审报告）**

| 节 | 内容 | 关键结论 |
|---|---|---|
| §0 | 执行摘要 | 独立评审声明、10 项关键发现（K1–K10）、数据可信度总览、**竞争位置判定** |
| §1 | 工作目录与文件清单 | 7,502 文件 / 103.5 MB；源码 122 文件 40,204 行；含自评数据的文件清单 |
| §2 | 项目理解与边界 | **项目实际身份 ≠ 任务书标签**（逻辑驱动/自修复未经证实）；7 条关键假设的红队判定 |
| §3 | 项目数据独立审计 | **14 条声明复核表**（P1–P16）；检出机制分解；修复口径；真实基准缺陷；伪重复；无法验证清单 |
| §4 | 2025–2026 前沿基线（一手重建） | 11 条测试生成基线 + 官方榜单逐条复算 + 自愈方向"基线未建立"判定 |
| §5 | 项目与前沿量化对比矩阵 | 14 维度 × 可否对比判定（**多数维度因口径不同不可比**） |
| §6 | 超越前沿方法设计 | 4 条路径（A 政策无关指标 / B 修复单调性 / C 求解器定向反例 / D 外部有效性），含**成功与失败判定标准** |
| §7 | 差距分析表 | 10 项能力差距 + 4 项问题定义差距 |
| §8 | Python 专项诊断表 | 12 项（含进程泄漏、类型门禁深度） |
| §9 | 领域专项诊断表 | 9 项 + **7 条红队反例** |
| §10 | 改进/优化/新增建议表 | P0 六条、P1 九条、P2 五条（均附 file:line、验证指标、时间线、命令） |
| §11 | 既有评审结论独立复核表 | 17 条（**支持 8 / 推翻 5 / 部分 4**） |
| §12 | 优化后的项目方案与路线图 | 定位重述、目录结构、T0–T3 路线图与 KPI |
| §13–§14 | 实验/验证计划、风险与合规 | 预注册要求、五步审计协议、12 项风险登记 |
| §15 | 待澄清问题 | 10 项（**不以假设填充**） |
| §16 | 参考来源 | 25 条一手来源 + 共识/争议/假设/推测分类 |
| §17–§18 | 可审计工件与复现指引、最终结论 | — |

**附录（原始审计工件）**

| 附录 | 内容 | 与正文的对应 |
|---|---|---|
| **A** | 项目声明溯源审计（90 条逐条复核，A43/B11/C12/D7/E17） | → §3 的完整证据链 |
| **B** | Python 与领域机制独立代码审查（13 条声称 vs 实现） | → §8、§9 的 file:line |
| **C** | 2025–2026 前沿基线一手重建（5 张分表 + 12 项交叉验证 + 失败端点） | → §4 的完整证据链 |
| **D** | 引用真实性核验（42 DOI + 72 arXiv ID + 15 项元数据错配 + 逐条更正文本） | → §11 C-12/C-13、§16 |
| **E** | 对抗式验证记录（584 行：对本报告 15 项核心数字的复算，**查出 3 项数据/口径/scope 错误 + 7 项表述问题**，全部已更正） | → §17.1 勘误表、全文可信度自检 |
| **F** | Lead 独立重放验证（repair 修正口径 54 行 → 20 correct） | → §3.5.1 |

---

### 本项目在 2025–2026 前沿格局中的位置（一句话）

> 项目在**能力维度**上不处于前沿（合成集检出低于其自身最强单提示基线；真实基准仅 50 个玩具程序），
> 且当前**不存在任何可验证的"超越前沿"证据**；但其**测量与实验方法学基础设施**（fail-closed 三态语义、
> provenance、工件校验、测量伪影自我披露）在同规模科研代码中属于稀缺资产——
> **这既是本次评审给出"不超越"判定的依据，也是 §6 四条路径唯一可能成立的基础。**

---

## 第一部分｜AITester 独立评审报告（2026-10-11）

> **评审对象**：`/Users/wangchenyu/Workspace/AITester`（Python，工作树 HEAD `d9e51df` + 未提交修改）
> **评审方式**：独立评审（independent review）＋ 一手来源（primary-source）基线重建 ＋ 零 LLM 存量复算
> **评审日期**：2026-10-11
> **产出工件**：
> - `audit_2026/T_A_claims_traceability.md`（项目数据溯源审计）
> - `audit_2026/T_B_code_domain_audit.md`（Python 与领域机制独立代码审查）
> - `audit_2026/T_C_frontier_primary_sources.md`（2025–2026 前沿一手来源重建）
> - `audit_2026/T_D_citation_verification.md`（引用真实性核验）
> - `audit_2026/lead_replay_seed_a.md`（Lead 独立重放验证）

---

## 0. 执行摘要

### 0.1 独立评审声明（最高优先级）

本报告是一次**独立评审**，不是对既有材料的复述或背书。执行前明确声明以下口径纪律：

1. **不信任项目内既有评审数据。** 工作目录内 `README.md` / `BASELINE.yaml` / `CHANGELOG.md` / `INDEPENDENT_REVIEW_2026-10-10.md` / `REVIEW_2026_FRONTIER.md` / `review_2026/*.md`（共 6 份既有评审材料、9,654 行）**全部视为"待验证声明"**。本报告的每一个项目侧数字，均由我或独立审计员**直接解析原始工件**（`experiments/results/**/*.json`、`*.trace.jsonl`）重新计算得到，并附可复算命令。
2. **不信任既有前沿基线数据。** 项目文档中转述的前沿 SOTA 数字（CANDOR、TestAgent、BOAD、arXiv:2601.09695 等）**不作为基线采用**。前沿基线一律回溯 arXiv 原文/官方榜单/官方仓库，逐条标注证据等级。
3. **独立重建基线。** 前沿基线由本次评审独立检索建立；与项目文件冲突处**以一手来源为准并显式指出冲突**（见 §4、§16）。
4. **独立复核既有结论。** 对既有评审的结论逐条复核，明确区分"独立验证支持 / 推翻 / 无法验证"（见 §11）。
5. **证据分级与降级。** 所有数据点标注 A/B/C/D/E 级（A=一手可验证；B=一手不可完全验证；C=二手；D=不可验证；E=推测）。D 级不得支撑任何结论。
6. **禁止编造与推断填充。** 缺失信息列入"待澄清问题"（§15），不以假设填充；不确定处标注"推测"并说明依据。

**本次评审的独立动作清单**（可审计）：
- 逐行复算 7 个主批次 × 3 臂 = **12,789 行**结果记录的 detection / repair / patch 字段；
- 独立运行 `experiments.repair_replay` 对种子 a 批次做**端到端重放验证**；
- 普查**全部** `experiments/results/**/*.json`（23 个唯一真实仓库基准工件）的字段完整性；
- 全文检索并实测复现**特异性门判据分叉**；
- 通过 arXiv 原文核实关键前沿工作与项目所引文献的真实性。

---

### 0.2 关键发现（每条附本次实测数值）

| # | 发现 | 本次实测证据 | 对项目主张的影响 |
|---|---|---|---|
| **K1** | 项目"**过红（over_red）是 −28pp 主机制**"的归因**不被数据支持** | 7 批（各臂 609 行）复算：aitester 检出 **78/556 = 14.0%**（可测口径），df **279/571 = 48.9%**。分解后：**48.6%（296/609）** 的 aitester 行 `detection_first_status=all_green_unverified` 且 `iterations=0`、无补丁——即**两版生成测试都在缺陷原码上全绿——从未出现任何一次非零退出（红灯）**；这 296 行**每行都含 ≥3 条 assert**（均值 15.3、最大 45），`test_error_rate` 全为 0，故**不是"没写断言"，而是断言全部通过**；df 该比例仅 2.5%（15/609） | 真正主机制是"**测试生成侧不产生红**"，不是"红不够特异"。反事实分解（实测，缺口 201 行）：对齐"产红率"贡献 **44.2%**、对齐"红→检出转化率"贡献 **26.1%**、两因子交互 **29.7%**——首个因子最大，但转化率亦非可忽略（§3.4.2） |
| **K2** | 特异性门与 M1 检出指标在**可执行行上零分歧**，门不构成独立贡献 | 门仅在 **4/7 批**落盘（1,044 行含该键、**450 行** verdict 非 None）：`specific_red → detection=1` **206/206**、`over_red → detection=0` **244/244**，**真实分歧 = 0**。另 3 行 `verdict=None` 而 `detection_rate=1.0`，属**门未运行**（非分歧） | 门**不能**作为独立机制解释检出差异；其宣传的机制归因须撤回或降级 |
| **K3** | 特异性门存在**判据分叉缺陷**：把"收集/导入错误"判成"过红" | 实测复现（`audit_2026/_probe_gate_vs_metric.py`）：rc=2（跨文件 import 失败 / 语法错误）→ 门判 `over_red`，M1 判"执行错误 → 0.0"。根因：门只取 `rc==0` 当绿（`src/tools/detection_gates.py:96-121`），未复用 `_looks_like_test_execution_error`（`experiments/_m1_metrics.py:58-81`）；且门委托**不传 `task_metadata`**（`:85-87`），跨文件任务伴生模块缺失 → **必然误判 over_red** | `over_red` 标签不可解释；以 `over_red` 为信号的弃权门/CPR/IDR/四通道代理**继承该噪声** |
| **K4** | 修复主指标 **39.31% 是事后重放口径，不是重跑口径**；原始工件 repair 全为 0 | 原始 7 批工件 `repair_rate` 全为 **0.0**（可测 556/571 行），`patch_correct=0`。我独立重放种子 a 批次：带补丁 87 行 → 可重放 **54** 行 → correct **20** → **0.3704**（与项目 39.31% 同量级）。根因确认为 patch 字段 markdown 围栏残留的**序列化伪影**，且修复**已落地到在线评分路径**（`_m1_metrics.py:395-410` 调用 `normalize_patch_text`） | 修正值可信但**必须标注"事后重放 + 可重放行分母"**；对全部 261 任务的端到端修复率仅 **57/261 = 21.8%**，E1/E2 logic 档为 **58/106 = 54.7%** |
| **K5** | **48.6% 的行根本不进修复循环**，导致修复主指标分母被结构性稀释 | 296 行 `all_green_unverified` 全部 `iterations=0`、`patch` 为空（`regeneration_count=1`、`test_error_rate=0`），被记为 `repair_rate=0.0`。这 296 行不是"修不好"，而是"**生成侧从未出现红灯**" | 39.31% 的**可重放分母 145/261** 隐藏了这批行；任何对外引用必须同时给出 all-task 分母 |
| **K6** | 项目唯一"真实基准"结论 **SWE-bench Lite 0/20 不是负结果，而是管道未接通** | 普查全部 `experiments/results/**/*.json`：`swe_bench` **293 行** + `swe_bench_pro` **72 行** = **365 行，100% `task_metadata.instance_code` 为空、100% 行内不存在 `detection_rate` 键**。代码归因：`_extract_gold_material` 对 `source=="swe_bench"` 直接 `return None`（`_m1_metrics.py:430-431`）。error_category 主要为 `syntax` / `patch_validation_failed` / `execution_trace_missing` | README "真实基准 0/20 负结果与统计检验同样如实披露"**表述失真**：应为"评测输入物化失败，真实基准结论缺失" |
| **K7** | 最可辩护的正面主张是**"自生成合成集上的检出优先归因实验"**，而非范式性发现 | 296 行"从未产红"是**测量口径问题还是生成能力问题**，现有工件**无法区分**——缺 `generated_test` 与缺陷代码的执行细节落盘 | 项目自身对该数据集的解释（"多智能体编排净负贡献"）**证据强度不足以支撑范式性结论**（D 级不可支撑） |
| **K8** | 全库 aitester 结果 `oracle_type` **只有 `generated_test`**，无一行规约/增强 oracle | **全库 7,153 行**普查：aitester `generated_test` **2,015** / **键缺失 1,788**（键存在且为 None = **0**）；全臂 **3,968 / 3,185**；**无一行 `enhanced_generated_test`**。另 7 批工件中 `spec_oracle_verdict` / `spec_oracle_injected` **键不存在** | "**逻辑驱动**"主张在**主实验口径下无任何实证**（不是"效果不好"，而是"从未在该口径下运行/落盘"） |
| **K9** | 引用真实性风险：项目引用的前沿数字存在**元数据错配**（详见 §16） | 项目 README 把 arXiv:2601.09695（Konstantinou 等，v2 2026-07）表述为"ICST 2026 复现研究"，并给出 `49.95/35.33/33.82`——该文原文报告的是**相对提升** 17.72%/19.80%/20.92%（line/branch/mutation）。另发现项目未引用的**更直接一手来源**：arXiv:2609.09315（同组，2026-09-08）与 arXiv:2602.08146（AdverTest, ISSTA 2026, DOI 10.1145/3832122） | 对外引用须逐条回到原文核对数值与口径；否则存在被审稿人一击命中的风险 |
| **K10** | 工程与实验卫生**高于同规模科研代码的平均水平**（独立验证支持） | 源码 `src/` 122 文件 40,204 行；测试 262 文件 68,379 行；Git 门禁、覆盖率棘轮、工件 SHA256SUMS、provenance（git_sha/model/temperature/seed/env_snapshot）、fail-closed 的 `None` 语义（区分"不可测"与"0"）、多起测量伪影的**自我披露** | 这是项目**真实且稀缺**的资产：测量基础设施本身具备论文级可复现性基础 |

---

### 0.3 数据可信度总览（本次审计口径）

| 类别 | 条目数（本次审计） | A 级 | B 级 | C 级 | D 级 | 说明 |
|---|---|---|---|---|---|---|
| 项目性能声明（自评） | 见 §3.1 表（21 条主声明） | 11 | 6 | 2 | 2 | A 级 = 可用原始工件逐位复算 |
| 项目前沿引用 | 见 §16 | 依 T-D 核验结果 | — | — | — | 二手转述不得作为基线 |
| 本次重建的前沿基线 | 见 §4 | 依 T-C 一手核验 | — | — | — | 每条附 arXiv/DOI/官方仓库 |
| 超越路径的预期提升 | 见 §6 | — | — | — | E | 全部标注为**推测**，需实验验证 |

**一句话总览**：项目的**测量诚实度**（A/B 级自我披露、fail-closed 语义、工件可复算）显著高于其**结论强度**。当前对外叙事（"检出优先协议 + 多智能体编排对照"）中，**最弱的一环恰恰是最核心的一环**：核心比较系在自生成合成集上完成，且主机制归因经本次复核**不成立**。

---

### 0.4 竞争位置判定（独立结论）

> **结论（独立判定，非复述）**：以 2025–2026 一手前沿为参照，**本项目在"LLM 测试生成"与"程序修复"两个子方向均不处于前沿位置，且当前不存在任何可验证的"超越前沿"证据**。
>
> - **测试生成**：项目最优可验证数字是 QuixBugs 上的检测 **45.9%（17/37，可测口径）**；前沿一手工作（见 §4）在同量级任务上以 mutation score / FDR 为主终点，且**"plain LLM 优于复杂编排"已被两篇独立一手研究复现**（arXiv:2601.09695；arXiv:2609.24341）。项目的合成集检出 14.0% **低于其自身 strongest 单提示基线 48.9%**。
> - **程序修复**：项目最优可验证数字是合成集可重放口径 39.31%（all-task 21.84%）。**注意：该数字与 SWE-bench Verified 系（榜首 79.2%）任务分布与评测协议均不同，不构成可比差距**（§5 已标"不可比"）；此处只作"未在公开基准上验证过"的陈述，不作数量级比较。
> - **"逻辑驱动"**：主口径下**零实证**（K8）。
> - **"自修复"**：代码层为离线 APR 闭环，全仓无监控/守护/热加载组件（`main.py` + `src/cli/app.py` 仅批量 CLI），**不构成运行时自修复系统**（独立代码审查结论，附 file:line）。
>
> **可辩护的窄主张**（建议作为对外唯一主张）：*在"检出优先 + 失败归因"这一**测量与实验方法学**问题上，本项目提供了可复现的测量基础设施与一组诚实的负结果*——这本身有价值，但**不是** SOTA 超越。

---

## 1. 工作目录与文件清单

### 1.1 索引方法
递归扫描工作目录，排除 `.git` / `.venv` / `__pycache__` / `.pytest_cache` / `.mypy_cache` / `.ruff_cache` / `.hypothesis` / `build` / `dist` / `node_modules`。统计命令：`python` 脚本遍历 `os.walk`（见 §1.2 命令）。

### 1.2 规模统计（本次实测）

| 项 | 数值 |
|---|---|
| 有效文件数（排除上列目录） | **7,502** |
| 总体积 | **103.5 MB** |
| `.py` 文件 | **1,171**（7.1 MB） |
| `.jsonl`（trace / 结果） | **4,833**（20.3 MB） |
| `.json`（批次工件 / 配置） | **974**（57.9 MB） |
| `.md`（文档 / 评审） | **180**（4.4 MB） |
| `.java`（QuixBugs 数据） | 182 |
| `.log` | 53（11.5 MB） |

**源码与测试规模**：

| 目录/模块 | 文件数 | 行数 |
|---|---|---|
| `src/`（合计 16 个子包） | 122 | 40,204 |
| ├ `src/tools/` | 31 | 11,236 |
| ├ `src/agents/` | 24 | 11,053 |
| ├ `src/graph/` | 17 | 8,253 |
| ├ `src/specs/`（**"逻辑驱动"内核**） | 5 | **2,140** |
| └ `src/dataset` 等其余 | 45 | 7,522 |
| `tests/` | 262 | 68,379 |
| `experiments/` | 584 个 .py（目录内文件 5,839） | — |
| `docs/` | 87 个文件（含 29 个 ADR） | — |
| 根目录 `config.py` | 1 | 34,213 字节 |

### 1.3 关键文件与用途分类

| 分类 | 关键文件 | 说明 |
|---|---|---|
| 说明文档 | `README.md`(1,710 行) / `README.en.md`(115 KB) / `QUICKSTART.md` | 含大量自评性能声明 → **§3 全部按"待验证声明"处理** |
| 机器可读基线 | `BASELINE.yaml`(614 行) | 项目自称"单一事实来源" → 本次逐条复核 |
| 既有评审（**6 份，9,654 行**） | `INDEPENDENT_REVIEW_2026-10-10.md`(478) / `REVIEW_2026_FRONTIER.md`(1,404) / `review_2026/*.md`(13 份) | **本次评审的复核对象**（§11） |
| Python 源码 | `src/**`(122 文件) / `config.py` / `experiments/**`(584) | 独立代码审查对象（§8） |
| 测试 | `tests/**`(262 文件 68,379 行) | 独立实测（§3.2） |
| 配置与依赖 | `pyproject.toml` / `requirements.txt` / `requirements.lock` / `setup.py` / `.pre-commit-config.yaml` / `Makefile` / `Dockerfile` / `Dockerfile.repro` | — |
| CI/CD | `.github/workflows/*.yml` / `.git-hooks/` / `scripts/gates/` | 门禁真实性经独立核验（§8） |
| 实验记录与评估结果 | `experiments/results/**`（**974 个 JSON，57.9 MB**） | **本次审计的主要原始证据源** |
| 数据 | `data/quixbugs/`（QuixBugs MIT，commit `4257f44b`） | 唯一真实外部基准 |
| 合规与安全 | `SECURITY.md` / `docs/threat_model.md` / `docs/DATA_CARD.md` / `MODEL_CARD.md` / `CITATION.cff` / `LICENSE`(MIT) / `.gitleaks.toml` | — |
| 预注册 | `docs/preregistration.md` / `.en.md` | E1–E4 判定阈值预注册（早于数据） |

### 1.4 包含自评数据 / 既有评审的文件（**全部按"待验证声明"处理**）

`README.md`、`README.en.md`、`BASELINE.yaml`、`CHANGELOG.md`(398 KB)、`CHANGELOG.en.md`(411 KB)、`MODEL_CARD.md`、`INDEPENDENT_REVIEW_2026-10-10.md`、`REVIEW_2026_FRONTIER.md`、`review_2026/*.md`（13 份）、`docs/performance_baseline.json`、`experiments/results/**/*report*.md`、`docs/citation_allowlist.txt`。

### 1.5 缺失 / 不可读 / 受环境限制

| 项 | 状态 | 影响 |
|---|---|---|
| SWE-bench 官方数据集 | **未下载**（`data/` 下仅 QuixBugs） | 无法在本环境重跑真实仓库基准 |
| `~/.cache` 内 225 个 SWE-bench 实例缓存 | 存在但**0 行含 `instance_code`** | 见 K6 |
| HuggingFace 限流 | 历史批次日志出现 403 quota | 早期 SWE-bench 失败的外部原因 |
| `data/quixbugs/` | 已克隆，可用 | 本次唯一真实外部基准 |
| `tests/` 全量跑批 | 本次实测 **5,311 passed / 2 failed** | 与 `BASELINE.yaml` 声明冲突（§3.2） |
| 覆盖率 `.coverage` | 仓库根文件**仅含 1 个被测文件**，已退化 | 89%/83% 覆盖率**本次无法独立验证** |

---

## 2. 项目理解与边界

### 2.1 项目真实定位（与任务书描述存在重要偏差 —— 必须先澄清）

任务书称本项目为"**逻辑驱动的多智能体测试生成与自修复系统**"。但**代码与工件的实际状态**是：

| 面向 | 任务书表述 | 本次独立核实的事实 | 证据 |
|---|---|---|---|
| 多智能体 | "多智能体测试生成系统" | 编排层（LangGraph 5 节点 planner/generator/executor/debugger/patch_applier）**存在**，但项目自身数据主张其**净负贡献**（aitester 14.0% vs 单提示基线 `plain_llm_df` 48.9%） | §3.3；`src/graph/workflow.py` |
| 逻辑驱动 | "逻辑驱动" | 主实验口径下**零实证**：全库 7,153 行中 aitester 的 `oracle_type` 只有 `generated_test`（2,015）或键缺失（1,788），**0 行**增强/规约 oracle；7 批工件中 `spec_oracle_*` **键不存在**；`spec_compile_rate` 仅 0.205–0.219（`src/specs/` 合计 2,140 行） | §3.6；K8 |
| 自修复 | "自修复系统" | 代码层为**离线 APR 闭环**（LLM 补丁 → 静态守卫 → 写回临时副本 → 跑测试 → 失败回滚），全仓**无 watchdog/supervisor/热加载/服务模式** | §8.2 独立代码审查 file:line |
| 测试生成 | "测试生成系统" | 成立，且是项目**唯一有工程实现深度的能力**（生成器 + 变异反馈 + 边界三元组 + 规约 oracle 注入路径默认关） | `src/agents/generator.py` |
| 评估系统 | 未提及 | **这才是项目最成熟的部分**：M1 三指标 fail-closed 语义、provenance、SHA256SUMS、ADR 记录测量伪影、预注册 | §0.2 K10 |

> **评审立场**：本报告不接受任务书给定的身份标签，而按**代码与工件的实际状态**评估。项目最可辩护的身份是"**检出优先的测试生成与失败归因评估系统**"——这与 `README.md:3` 的自我表述一致，而任务书的"逻辑驱动 + 多智能体 + 自修复"三标签中，**两个在主口径下无实证，一个在代码层不成立**。

### 2.2 关键假设与本次红队判定

| # | 项目假设 | 本次独立判定 | 依据 |
|---|---|---|---|
| A1 | 多智能体编排能提升缺陷检出 | **被项目自身数据证否**，且本次复核确认数据本身**不是**口径不对称造成的（三臂同一 `_compute_detection_rate`，`run_benchmark.py:1094`） | §3.3 |
| A2 | "过红（非特异红）"是检出落后的主因 | **不成立（本次最重要的推翻）**：门与 M1 在可执行行上**零分歧**（4/7 批、450 行 verdict 非 None：`specific_red→det=1` 206/206、`over_red→det=0` 244/244），门**不能独立解释**检出差异；真实主因是 **48.6% 的行从未出现红灯** | §3.4 |
| A3 | 覆盖率是生成有效性的代理 | **被证否**（项目自身 + 两份一手前沿一致：覆盖近饱和但检出近 0） | §4；arXiv:2609.09315、arXiv:2609.24341 |
| A4 | repair 39.31% 是"修复能力" | **部分成立但口径必须限定**：可重放 145 行口径成立（本次独立重放得 0.3704 同量级）；all-task 261 口径仅 **21.84%**；且 48.6% 的行因"从未产红"被记 repair=0 | §3.5 |
| A5 | 合成集结论可外推真实代码 | **不成立**：合成集 87 任务仅 29 个模板（最高重复 8 次，ICC 0.671）；真实仓库工件 365 行**结构性不可测**；唯一有效真实基准是 QuixBugs 50 个玩具程序 | §3.7 |
| A6 | 缓存重跑等于独立重复 | **不成立**：10-07 两对批次为同种子重跑，按 `task_id` 对齐后核心字段 **249–252/261** 行逐值相同（§3.8） | 本次实测 |
| A7 | `patch_plausible` 可作为修复漏斗闸口 | **不成立**：`repair_history` 键在全库 7,153 行中**出现 0 次**，`patch_plausible` 无法从工件复核；且 129 行出现 `patch_correct=1 ∧ patch_plausible=0` 的不变量违反 | §3.5、§3.9 |

### 2.3 边界声明（本次评审不能覆盖的范围）
- 无法在本环境重跑真实仓库基准（SWE-bench 数据未下载、HF 限流）；
- 无法独立验证覆盖率声明（仓库 `.coverage` 已退化）；
- 无法独立验证"无缓存理论成本"（需控制缓存后重跑，成本高）；
- 环境存在 3 个孤儿子进程抢占 CPU（§3.10），任何耗时测量（含测试套件时长）均受此混杂影响。

---

## 3. 项目数据独立审计

> **方法**：不采信任何项目自评数字。所有数值由本次评审**直接解析原始工件**重算，命令见各小节。
> **证据等级**：A=原始工件逐位可复算；B=可复算但口径需限定；C=部分一致（有可指认偏差）；D=不一致/被工件否证；E=无法溯源。

### 3.1 声明复核总表（摘要，完整 90 条见 `audit_2026/T_A_claims_traceability.md`）

| # | 声明 | 位置 | 本次复算 | 判定 | 等级 |
|---|---|---|---|---|---|
| P1 | detection：`plain_llm_df 44.8% > aitester 15.8% > plain_llm 1.5%` | `README.md:56`、`BASELINE.yaml:56 节` | 三种子 pooled 口径可复现（`38/240`、`117/261`、`4/261`）；本次 7 批全集口径为 **aitester 78/556=14.0%、df 279/571=48.9%、pllm 10/609=1.6%**（None 不计入分母；逐臂可测行 556/571/609） | **可复现**（须逐臂标注分母；统一 /609 则为 12.8%/45.8%/1.6%） | **A** |
| P2 | repair 修正口径 `39.31%（57/145）` | `README.md:56` | **本次独立重放 669 行**（200.4 s）得 R-P0-2 `57/145=0.3931`、E1/E2 `58/106=0.5472`、早期 `0/15` | **可复现**（事后重放口径） | **A** |
| P3 | repair 修正口径 `54.72%（58/106）`（logic 档） | 同上 | 同上，逐位一致 | 可复现 | **A** |
| P4 | QuixBugs `detection 17/37=45.9%`、`repair 37/40=92.5%`、对照臂 `31/37=83.8%` | `LEAD_findings.md` / `BASELINE.yaml` | **逐位复现**：aitester 17/37=45.9%、37/40=92.5%；df 31/37=83.8% | 可复现（**但对照不可比，见 §3.5**） | **A**（数值）/ **D**（可比性） |
| P5 | `tests.total_passed: 5262`、`total_failed: 0` | `BASELINE.yaml:17-18` | 本次实测 `--collect-only` = **5,317**；全量 = **5,311 passed / 2 failed / 3 skipped / 1 xfailed**。**项目自带守卫已自证过期**（`5317−5262=55 > 9` 触发 `test_tests_and_mypy_are_current` 失败） | **不一致（已过期）** | **D** |
| P6 | `static_checks.mypy_source_files: 120` | `BASELINE.yaml:84` | `mypy src/ config.py` → **Success: no issues found in 123 source files** | 不一致（+3） | **D** |
| P7 | `coverage.line_total_pct: 89` / `branch_total_pct: 83` | `BASELINE.yaml:30,42` | **无法验证**：仓库根 `.coverage` 仅含 1 个被测文件（已退化） | 无法溯源 | **E** |
| P8 | `slim_environment: 1863` | `BASELINE.yaml:21` | 需卸载可选依赖环境，超出只读审计范围 | 无法验证 | **E** |
| P9 | `$/task aitester 0.0259 / plain_llm 0.0034 / df 0.0045` | `README.md:56` | 数据可复算，但**热缓存批次 df/plain_llm 大量 0-token**（E1/E2 两臂 **348/348** 行 token 总量为 0；R-P0-2 df **35/261**）；冷缓存批次 E6 phase1 三臂 0/87 | **方向性正确、绝对值为下界**；且 `deepseek-flash` 价目表登记为 `input 0.3 / output 1.2`，**但 `token_usage` 未落盘 in/out 拆分**（只有 `total_tokens`），成本无法逐位复算 | **B** |
| P10 | `ruff_warnings: 0` / `ruff 0.16.3` / `mypy 1.15.0` | `BASELINE.yaml:81-83` | `ruff check .`（排除本次审计脚本）→ All checks passed；`ruff --version` → 0.16.3；`mypy --version` → 1.15.0 | 一致 | **A** |
| P11 | `spec_compile_rate aitester [0.205, 0.219]`（"E1/E2 logic 档**四批次**"） | `BASELINE.yaml:71` | 数值一致，但四个文件实为 **2 种子 × 2 次缓存重跑**（§3.8），独立测量仅 2 个 | 数值可复现，**"四批次"计数失真** | **B** |
| P12 | `specificity_gate: {specific_red: 40, over_red: 66}`（跨批合计） | `BASELINE.yaml:76` | 4 批之和确为 40/66，但其中 2 批与另 2 批**逐行同值**（同种子重跑）→ **double counting** | 数值可复现，**合计口径不成立** | **B** |
| P13 | SWE-bench Lite `0/20` "真实基准负结果如实披露" | `README.md:56` | 24 个工件 / **365 行 100% 无 `instance_code`、100% 行内不存在 `detection_rate` 键**；`passed=True` 仅 4/365；`error_category` 主要为 `patch_validation_failed`(148)/空(125)/`execution_trace_missing`(59)/`syntax`(28) | **定性不成立**：属"评测输入物化失败"，非"负结果" | **D** |
| P14 | `oracle 注入 20/50 = 40%`（真实 QuixBugs） | 项目自述（A2 链路） | 该批 `spec_oracle_injected` / `oracle_type` **全为 `generated_test`**，无一行规约 oracle | 不一致 | **D** |
| P15 | 覆盖率区间 `aitester [84.0, 93.6]` / `plain_llm [86.0, 97.2]` | `BASELINE.yaml:61-62` | aitester 复算 `[83.977, 93.58]` ✅；plain_llm 全 10 批为 `[70.4, 97.22]`，**须静默剔除 2 个 n=5 冒烟批**才得 `[85.96, 97.22]`（注记未披露） | 数值一致，**口径需限定** | **B** |
| P16 | `mutation_score aitester [0.818,0.976] / pllm [0.951,0.992] / df [0.986,0.997]` | `BASELINE.yaml:66-68` | 逐位一致（0.8175–0.9760 / 0.9515–0.9916 / 0.9856–0.9968） | 可复现 | **A** |

**复现性分级统计（完整 90 条）**：**A 43（47.8%）/ B 11（12.2%）/ C 12（13.3%）/ D 7（7.8%）/ E 17（18.9%）**。
**核心实验数字无一编造**：detection 三值、repair 两值、$/task 三值、E4/E6 关键值、全部 McNemar χ² 与渐近 p **均逐位复现**；`corrected_report_v2.md` 正文与我方独立重跑**逐字节相同**。

### 3.2 测试与静态检查（独立实测）

| 项 | 声明 | 本次实测 | 判定 |
|---|---|---|---|
| 收集用例数 | 5,259（注释）/ 5,262 passed | **5,317 collected**（2.34 s） | 过期 |
| 全量结果 | 0 failed | **5,311 passed / 2 failed / 3 skipped / 1 xfailed**（223.21 s 串行） | 不一致 |
| 失败用例 | — | `TestEnvSnapshotCompleteness::test_gate_reports_no_missing`、`TestBaselineNumbersConsistency::test_tests_and_mypy_are_current` | **项目自带守卫自证 BASELINE 过期** |
| mypy | 120 源文件 0 错误 | **123 源文件 0 错误** | 声明过期，错误数属实 |
| ruff | 0 / 0.16.3 | 0 / 0.16.3 ✅ | 属实 |

> **独立解读**：`test_tests_and_mypy_are_current` 这个**自建一致性守卫**是本项目工程素养的真实证据——它主动抓出了文档漂移。**但当前工作树并非"全绿"**，任何"全量测试通过"的对外表述须先修此漂移。

### 3.3 核心量化对比的独立复算（7 批 × 3 臂 = 12,789 行）

复算命令（零 LLM，只读解析）：

```bash
.venv/bin/python - <<'PY'
import json,glob,collections
files=sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json"))
for f in files:
    res=json.load(open(f))["results"]
    for arm,v in res.items():
        det=v["details"]
        print(f, arm, len(det),
              sum(1 for x in det if x.get("detection_rate")==1.0),
              sum(1 for x in det if x.get("detection_rate") is None))
PY
```

| 臂 | 行数 | 可测行 | 检出（可测口径） | 检出（全集口径） | 产物补丁行 | `repair_rate` 非 None 且为 1 | `passed=True` |
|---|---|---|---|---|---|---|---|
| `aitester`（全系统） | 609 | **556**（53 None） | **78 / 556 = 14.0%** | 78/609 = 12.8% | 251 | **0** | 389 |
| `plain_llm`（单次生成） | 609 | 609 | **10 / 609 = 1.6%** | 1.6% | 0 | **0** | 535 |
| `plain_llm_df`（检出优先单提示） | 609 | **571**（38 None） | **279 / 571 = 48.9%** | 279/609 = 45.8% | 0 | **0** | 15 |

**关键观察（本次新增，既有评审未记录）**：
1. **三臂的 detection 由同一个函数计算**（`run_benchmark.py:1094` → `experiments/_m1_metrics.py` 的 `_compute_detection_rate`），判据 = `buggy 红 ∧ gold-fixed 绿 ∧ 两侧无收集/语法错误`。**因此 −34.9pp 不是"口径不对称"造成的**，可在方法学上直接比较。
2. **两个基线臂产出的补丁行数均为 0**（`plain_llm` 与 `plain_llm_df` 的 `build_workflow(debugger=False)` 不含补丁节点）。**任何方法表把 df 的 `repair=0` 与 aitester 并列，是把"没有该能力"当作"该能力失败"**（§3.5 详述）。

### 3.4 检出落后的真实机制（**本次推翻项目核心归因**）

#### 3.4.1 机制分解（7 批，609 行 aitester）

| 终态 `detection_first_status` | 行数 | 占比 | `iterations` | 是否有补丁 | 检出 |
|---|---|---|---|---|---|
| `all_green_unverified` | **296** | **48.6%** | **全部 0** | **全部无** | 0 |
| `red_not_repaired` | 167 | 27.4% | 2–3 | 158 有 | 19 |
| `red_then_green` | 93 | 15.3% | 1–3 | 全部有 | 59 |
| `None`（不可测） | 53 | 8.7% | 0 | 无 | — |

**决定性事实**：**296 行（48.6%）的 `iterations == 0` 且 `patch` 为空**（`regeneration_count=1`、`test_error_rate=0`、每行 assert ≥3 条）——即 `_should_debug` 的首轮路由生效（`src/graph/workflow.py:682-699`）：测试在缺陷原码上**全绿** → 路由到"再生成"（`regeneration_count` 上限 `MAX_REGENERATIONS=1`，`config.py:375`）→ 第二版仍全绿 → 直接 `done`。**这 296 行从未进入修复循环。**

#### 3.4.2 与 `plain_llm_df` 的通道对比

| 通道 | aitester | plain_llm_df | 差 |
|---|---|---|---|
| **曾产生红**（`detection_first_red_seen=True`） | **260 / 609 = 42.7%** | **556 / 609 = 91.3%** | **−48.6pp** |
| 条件转化率（曾红 → 最终检出） | 78/260 = **30.0%** | 279/556 = **50.2%** | **−20.2pp** |

**反事实分解**（本次独立实测，缺口 = 279 − 78 = **201** 行）：

| 反事实 | 计算 | 检出 | 对缺口的贡献 |
|---|---|---|---|
| 只对齐**产红率**（42.7% → 91.3%），转化率保持 aitester 的 30.0% | `(0.913−0.427) × 0.300 × 609 = +88.8` | ~167 | **44.2%** |
| 只对齐**转化率**（30.0% → 50.2%），产红率保持 aitester 的 42.7% | `0.427 × (0.502−0.300) × 609 = +52.5` | ~130 | **26.1%** |
| **两因子交互** | 201 − 88.8 − 52.5 = 59.7 | — | **29.7%** |

> **口径声明（必须与上表同读）**：
> 1. **分解次序**：上表为 **aitester-基准的序贯分解**（先补产红率、再补转化率、余项为交互）。若改用 **df-基准**，三项为 **73.9% / 55.8% / −29.7%**——**主效应占比随分解次序变化**（交互项可为负）。因此**只能读作"两个因子都大"，不能读作"某因子占 X%"**。
> 2. **口径更正（本报告自查）**：初稿曾写作"产红率贡献约 88%"，系把**主效应占比**误算为**缺口占比**。正确结论：**产红率与转化率都是必须修的问题**（aitester 基准 44.2%/26.1%；df 基准 55.8%/73.9%），**不存在单一主因**。这影响 §6 的路径优先级——路径 A 与路径 C 均必要。

#### 3.4.3 推翻"过红是主机制"

- **门与 M1 在可执行行上零分歧**：门在 **4/7 批**（2026-10-07 logic 档）落盘——**1,044 行**含该键、其中 **450 行** verdict 非 None；交叉表 `specific_red → detection_rate=1.0` **206/206**、`over_red → detection_rate=0.0` **244/244**，**真实分歧 = 0**。
- **需单列的 3 行（不是"门的例外"）**：`verdict=None` 但 `detection_rate=1.0`，同行 `passed=True` / `detection_first_red_seen=False` / `iterations=0`。这是**门根本没运行**（10-06 三批连 verdict 键都不存在）的行，与"门与指标冲突"无关。我初稿写作"例外仅 2 行"，**属表述错误，已更正**（对抗式验证 §S2）。
- 结论不变：**门不是独立机制，而是同一判据的运行时视图。**
- 项目 `BASELINE.yaml:76-78` 用 `specific_red/over_red ≈ 0.61` 对比 df `≈1.16` 作为"−28pp 主机制"依据——**该推理不成立**：门与指标同源，不构成独立证据（逻辑上等于用检出率解释检出率）。
- 且该 `over_red` 标签本身**不可解释**：门只取 `rc == 0` 当绿（`src/tools/detection_gates.py:96-121`），**未复用** M1 的"收集/语法错误"排除判据（`_m1_metrics.py:58-81`）；实测复现 rc=2（跨文件 import 失败 / 语法错误）→ 门判 `over_red`、M1 判"执行错误"。加重项：门委托**不传 `task_metadata`**（`:85-87`），而 `_m1_metrics` 的跨文件物化依赖 `task_metadata["is_cross_file"]`（`:330-333`）→ **跨文件任务必然被误判为 `over_red`**。
- 该 `over_red` 信号还下游传导至：弃权门（`src/tools/patch_abstain.py:40-46` 第 3 条）、CPR/IDR 负信号（`cpr_idr_report.py:50`）、四通道 fixed 腿代理（`four_channel_recompute.py:34,230-232`）。

> **结论（本次独立判定）**：项目对自身负结果的**机制归因被推翻**。可支持的表述是"*编排管线在 48.6% 的运行中未能产出任何失败的测试*"，而**不是**"*编排产出的红不够特异*"。前者是**生成/路由问题**，后者是**断言质量问题**，二者修复路径完全不同。

### 3.5 修复（repair）口径审计

#### 3.5.1 39.31% 的口径与可复现性

- **原始工件 `repair_rate` 全为 0.0**（7 批三臂的**零值行**为 aitester 556、df 571、**plain_llm 609**，合计 **1,736**；`None` 行 53/38/0），`patch_correct = 0`。
- **根因**：结果行 `patch` 字段保存 LLM 原始输出（含 ```` ```python ```` 围栏 / `python` 前缀），而 M1 独立裁决直接消费该原始值 → gold 测试在未清理文本上 100% `NameError` 失败 → **repair 被系统性压零**。这是**序列化伪影**（项目 ADR-0021 已识别）。
- **修复已落在线评分路径**：`_m1_metrics.py:395-410` 在完整文件分支先调用 `normalize_patch_text`；因此 39.31% 不是"手工改数字"，而是"**用修好后的口径重放存量工件**"。
- **本次独立重放验证**（种子 a 批次）：带补丁 87 行（表头口径）→ **可重放 54 行** → **correct 20** → **0.3704**；33 行因无 gold 材料出分母。与项目全 10 批 pooled 值同量级，**认定可复现（A 级）**。

#### 3.5.2 分母构造（必须与 39.31% 同时披露）

| 口径 | R-P0-2（3 种子） | E1/E2（logic 档） |
|---|---|---|
| 可重放行（patch 非空 ∧ gold 材料齐备） | **145** | **106** |
| correct | 57 | 58 |
| **可重放口径 repair** | **39.31%** | **54.72%** |
| **all-task 口径**（分母 = 全部任务） | **57/261 = 21.84%** | **58/348 = 16.67%** |
| 全部 609 行口径 | 115/609 = 18.88% | — |

**未进入 145 分母的 116 行中，296−145 的主体正是 §3.4.1 那批"从未产红"的行**——它们被记为 `repair_rate=0.0`，但**不是"修不好"**。任何把 39.31% 读成"系统能修好 39% 的缺陷"的表述都**高估**。

#### 3.5.3 两个不可比对照（**本次新发现的表述风险**）

| 对照 | 事实 | 风险 |
|---|---|---|
| QuixBugs：`aitester repair 92.5%` vs `df 0%` | df 臂 `iterations` **全为 0**、`patch` 非空 **0/50**、`stop_reason` 全 `unknown`——**该臂结构上不具备补丁能力**（`build_workflow(debugger=False)`） | 把"无此能力"列为"修复失败"，**是不可比对照** |
| 主批次：`aitester repair` vs `df repair` | 同上，df 全 609 行 patch 为空 | 同上 |

#### 3.5.4 记账缺陷（不变量违反）

- **129 行**出现 `patch_correct = 1 ∧ patch_plausible = 0`（QuixBugs FIXED harness 13 行、over_red verified 13 行、a1_strip_fixed 12 行等）。其中 QuixBugs 13 行全部落在 `stop_reason=skip_debugger_repair_invalid`、`iterations=2`。
- **根因**：`patch_plausible` 依赖 `final_state["repair_history"][-1]["patch_applied"]`（`run_benchmark.py:602-618`），而 **`repair_history` 键在全库 7,153 行结果中一次都没有落盘** → `patch_plausible` **无法从任何工件复核**，且在该早退路径上系统性低估。
- **后果**：`patch_precision = correct/plausible` 可 >1（`review_2026/E2_fence_recompute.json` 的 e6 组 `precision_original = 1.0648`）；项目"patch 产出 94% → plausible 46.8% → correct 39.31%"**漏斗叙事的中间闸口不可复核**。
- **修复路由损失**：QuixBugs 批 **24/50 任务**（48%）被 `_recent_repairs_invalid` 在 `iteration < max_iterations` 时提前 `done`（`src/graph/workflow.py:734-743`），而这 24 行中 **13 行最终被 gold 判定修复正确** → **修复能力存在但被路由层提前掐断**。

### 3.6 "逻辑驱动"与"自修复"在主口径下无实证

| 主张 | 独立核实 | 判定 |
|---|---|---|
| 系统以逻辑/规约 oracle 参与判定 | **全库 7,153 行**普查：aitester `generated_test` **2,015 行** / **键缺失 1,788 行**（键存在且为 None = 0）；全臂 3,968 / 3,185；**无一行 `enhanced_generated_test` 或规约 oracle**。另 7 批工件中 `spec_oracle_verdict`/`spec_oracle_injected` **键不存在** | **主口径零实证**（D） |
| `spec_compile_rate ≈ 0.21` 是"逻辑驱动"证据 | 分子 = 可编译非空子句数 / 分母 = 非空子句数（`src/specs/spec_ir_v2.py:668-683`）；表达力 = **无量词/无函数/无数组/无关系/无时序**的 Bool/Int/Real 标量约束（z3 翻译算子集 `spec_smt.py:322-388`；全 `src/specs/` 无 `ForAll`/`Exists`/`Array`/`Function` 命中） | 是"**弱规约 DSL 的可编译率**"，非"逻辑驱动测试生成" |
| SMT 真在求解 | `Solver` + `Optimize` 真实调用（`spec_smt.py:525-546`），预算 2 s / 3 见证（`:73-92`）；但只求"**前件可行性 / 边界极值 / 前件空洞 / 后件自洽**"，**明确不做"实现是否满足后件"**（`:14-24`） | 是"**规约自洽性检查**"，非形式化验证 |
| 反例精化闭环（CEGIR）已生效 | `src/specs/spec_refine.py:26-28` 自述**未接主链路** | 未生效 |
| "自修复系统" | `src/graph/patch_io.py:351-455`（写盘）/`:458-504`（回滚）；目标文件是任务**临时副本**（`run_benchmark.py:1576,1602`）；全仓无 watchdog/supervisor/restart/服务模式 | 是**离线 APR 闭环**，**不是运行时自修复** |

### 3.7 真实仓库基准工件的结构性缺陷（K6 详证）

**普查范围**：`experiments/results/**/*.json` 全部 23 个唯一真实仓库基准工件。

| 数据集 | 行数 | `instance_code` 为空 | 行内无 `detection_rate` 键 | `passed=True` |
|---|---|---|---|---|
| `swe_bench` | **293** | **293（100%）** | **293（100%）** | 4 |
| `swe_bench_pro` | **72** | **72（100%）** | **72（100%）** | 0 |
| **合计** | **365** | **365（100%）** | **365（100%）** | 4 |

- **代码归因**：`_extract_gold_material` 对 `source=="swe_bench"` 直接 `return None`（`_m1_metrics.py:430-431`）；`_gold_fixed_code` 返回 `""`（`:462-463`）；detection 还要求 `instance_code` 非空（`:506-508`）→ **真实仓库任务在 M1 口径下结构性不可测**，与"跑得好坏"无关。
- **输入侧**：`data/` 无 SWE-bench 数据集；`~/.cache` 内 225 个实例缓存 **0 行含 `instance_code`**。
- **`error_category` 全量普查（365 行，本次自查更正）**：`patch_validation_failed` **148**、空字符串 **125**、`execution_trace_missing` **59**、`syntax` **28**、`import_error` 2、`index_error`/`unknown`/`timeout` 各 1。我初稿写的 `syntax(19)/pvf(18)/etm(20)` 是**单个 60 行工件的分布**被误当普查值，**已更正**。
- **口径瑕疵（本次新发现）**：标为 `swe_bench` 的 293 行中有 **3 行** `task_metadata.source='examples'`——数据集标签与任务来源不一致。
- **结论**：`README.md:56` 的"SWE-bench Lite（sqlfluff-20）真实基准 **0/20** 负结果与统计检验同样如实披露"**表述失真**，应改为"**评测输入物化失败，真实基准结论缺失**"。这也与项目自身另一处表述（"受限流、结果未归档"）**内部矛盾**。

### 3.8 伪重复（本次新发现，影响所有 logic 档 n）

| 批次对 | 种子 | 核心字段逐值相同的行数 |
|---|---|---|
| `..20261007_161053` ↔ `..20261007_181638` | 42 | **252 / 261**（按 `task_id` 对齐：aitester 78/87、plain_llm 87/87、df 87/87） |
| `..20261007_170147` ↔ `..20261007_185941` | 44 | **249 / 261**（按 `task_id` 对齐：aitester 75/87、plain_llm 87/87、df 87/87） |
| 同上，但**按行序对齐**（错误做法，仅作对照） | — | 143/261、140/261（**低估约 10 pp**；两批 aitester 臂仅 49/87 位置同名） |

- 比较字段：`detection_rate` / `repair_rate` / `passed` / `generated_test` / `detection_first_status` / `specificity_gate_verdict` / `stop_reason` / `patch`。
- ⚠️ **对齐方式至关重要（本次自查更正）**：两批任务顺序不同，**必须按 `task_id` 对齐**；按行序对齐会得到 143/261、140/261 的**低估值**（我初稿即犯此错，系对抗式验证发现，见附录 E S1）。
- **机制**：`AITESTER_CACHE_NAMESPACE` 按 seed 命名（seed42/43/44；`src/agents/base_agent.py:388`、`run_benchmark.py:2431-2432`），**同 seed 复跑共享缓存** → 第二次运行是**缓存的确定性重放**（E1/E2 批次 df/plain_llm 两臂 **348/348 行 token 总量为 0** 即为铁证）。
- **影响**：项目"E1/E2 logic 档**四批次**"的 n 被放大 2 倍；`specificity_gate` 合计 `{specific_red: 40, over_red: 66}` 在同一 seed 内被**双重计数**（该 seed 真实独立值为 9/18）。
- **正面评价**：缓存设计**已含 seed 命名空间**（X1 审查的 P0 修复），因此**不存在跨种子污染**；问题在于**同种子重跑被当作独立批次计入 n**——项目自身在 `base_agent.py:382-387` 已写明"同 seed 复跑仍共享缓存 = 可复现性特性保留"，但**未在统计口径中据此折减 n**。

### 3.9 成本口径

| 项 | 实测 |
|---|---|
| `token_usage` 落盘字段 | **仅 `total_tokens` / `input_tokens` / `output_tokens`**（无 in/out 在结果行被消费的痕迹：`input_tokens`/`output_tokens` 键在早期批次不存在，本次 7 批中 609/609 行 `prompt_tokens`/`completion_tokens` 键缺失） |
| 热缓存行 | E1/E2：df 与 plain_llm **348/348 行** token 总量 = 0；R-P0-2：df 35/261；E6 control 两臂 87/87 |
| 冷缓存对照 | E6 phase1 三臂 **0/87** 为零（严格同现）→ 证明 0-token 即缓存命中 |
| 影响 | **df/plain_llm 的成本是被低估的下界**；"aitester 贵 5.75×"这一比值**建立在不公平的成本记账上**（aitester 因跑批顺序在前，多为冷缓存） |

> **独立结论**：成本比较**当前不可用**。修复方向明确：报告层应同时输出 `total_tokens` 与 `cache_avoided_tokens`（`src/budget/token_usage.py:129-148` 已实现该记账），并以"无缓存理论成本"为准。

### 3.10 环境副作用（本次实测）

- **3 个孤儿子进程**长期占用 ~3 核：`pid 36935`（`test_bitcount.py`，ppid=1，已运行 **16 h 42 m**，100% CPU）、`pid 37116`（`test_find_first_in_sorted.py`，16 h 41 m，100% CPU）、`pid 37498`（branch-coverage 包装脚本，16 h 38 m）。
- **根因**：`experiments/_m1_metrics.py:358-372` 使用裸 `subprocess.run(..., timeout=...)`，**未设置 `start_new_session`/进程组 kill**；超时后仅杀直接子进程，pytest 派生的子进程成为孤儿。项目已有 `run_with_timeout`（含 killpg）但**只接入了 `branch_coverage_inject`，未接入 M1 判分路径**。
- **影响**：任何"耗时/吞吐"类测量（含 `suite_seconds`）均受此混杂；同时这是一个**资源泄漏级缺陷**（每次超时都可能遗留孤儿）。

### 3.11 无法验证声明清单（E 级，不得用于对比或对外）

1. 覆盖率 `line 89%` / `branch 83%` / 10 个核心模块逐文件覆盖 / 3 个路由模块分支覆盖（`.coverage` 已退化，需 `--cov=src` 全量重跑）。
2. `slim_environment: 1863`。
3. v1 口径 `35.86%` / `48.11%`（历史值，已被 v2 取代）。
4. `oracle 注入 2–3/87` 与 `20/50`（对应批次 `spec_oracle_injected` 全 0）。
5. v1 口径诊断项："9/9 双 rc=2"、"F2P 0/7→6/7"（诊断工件无 `rc` 列）。
6. `patch_rollback_verdict` / `patch_rolled_back`（全库 7,153 行键出现 0 次）；`regression_rate` / `red_regression_violation` / `deterministic_repair_status` 非 None 行数 = 0。
7. E4 就绪度声明中依赖未落盘开关值的项（`RT1` 等开关不在 `env_snapshot`）。
8. `docs/performance_baseline.json` 的历史吞吐数字（受孤儿进程混杂，且无对应批次 provenance）。

> **统一处置**：以上各项一律标注"**项目自报，未独立验证**"，**不得**进入 §5 量化对比矩阵的"项目现状"列。

---

## 4. 2025–2026 前沿基线表（独立重建，一手来源）

> **纪律**：本节所有数字均来自**本次评审独立检索并打开原文核验**的一手来源（arXiv 原文 / 官方元数据 API / 官方榜单分析）。**不采用**项目文档中的前沿转述。
> **证据等级**：A = 一手全文/摘要逐字命中且元数据经机读核验；B = 一手存在但条件不完整；C = 二手；D = 不可验证；E = 推测。
> **检索日期**：2026-10-11。检索端点：`arxiv.org/abs|html`、`api.crossref.org`、`api.openalex.org`、`api.semanticscholar.org`、`web_search`。
> **未完成项**：本节的"自修复/运行时"与"逻辑驱动/SMT"两张分表已完成，残余缺口见 §4.9；凡未逐字核验者一律标注"未独立核实"。

### 4.1 测试生成与缺陷检出（核心分表）

| # | 工作 | 关键指标与数值 | 基准 / 条件 | 一手来源 | 年份/venue | 等级 | 交叉验证 | 冲突说明 |
|---|---|---|---|---|---|---|---|---|
| F-1 | **传统测试准则对 LLM 生成代码的检出能力**（Hamidi, Konstantinou, Degiovanni, Papadakis） | **语句覆盖触发率 32.9% / 分支 38.9% / 变异 32.2%**；**检出率仅约 1–2%**；specification-guided oracle 仅提升 **~6.6%**。语料：5 个 LLM × 4 基准（HumanEval+、MBPP、BigCodeBench、NaturalCodeBench），**6,066 个"最难"故障**（从 233,300 生成中筛出，由 73,785 故障经难度 >0.75 过滤），每任务取最难 1 个 | Python；故障由 LLM 生成、参考实现作 ground truth；oracle 与 trigger 分离定义（Def.1–4） | [arXiv:2609.09315](https://arxiv.org/abs/2609.09315)（v1, 2026-09-08）；作者单位：University of Luxembourg SnT / LIST | 2026（预印本） | **A**（摘要+正文数值逐字） | 与 [arXiv:2609.24341](https://arxiv.org/abs/2609.24341) 的"覆盖近饱和无鉴别力"互为独立佐证 | 与"变异测试优于结构覆盖"的**传统共识冲突**：该文指出对 LLM 故障，变异仅**边际**优于覆盖，成本收益存疑 |
| F-2 | **类级 LLM 生成测试套件有效性**（Al-Ahmad, Harshvardhan, El-Fakih, AlSobeh） | 结构覆盖"**一致接近上限、几乎无鉴别力**"；可执行性差异显著；**模型选择解释的方差大于提示策略**；提示 × 模型存在交互；人类 vs LLM 套件在**不等可执行子集**上比较，故**不能**据此宣称优劣 | **ClassEval** 基准；Cosmic Ray 变异；多提示策略 × 多模型 | [arXiv:2609.24341](https://arxiv.org/abs/2609.24341)（v1, 2026-09-21） | 2026（预印本） | **A**（摘要逐字） | 与 F-1 独立同向 | 与传统"提示工程收益大"的叙述冲突：该文主张"**模型选择先于提示调优**" |
| F-3 | **AdverTest：对抗式双 agent 测试生成**（Chang, Fang, Chen, Shi, Shen, Gu） | **FDR 相对最强 LLM 基线 +8.56%**，相对 EvoSuite **+50.20%**（摘要口径；正文引言作 63.30%）；**Python（SWE-Rebench 12 issues）检出 11/12**；line/branch 覆盖保持竞争；公开代码仓库 | Defects4J + GrowingBugs（Java）；SWE-Rebench（Python）；基线 HITS / ChatUniTest / EvoSuite / Randoop；消融含对抗循环与 mutant-aware 反馈 | [arXiv:2602.08146v3](https://arxiv.org/abs/2602.08146)（v3, 2026-08-31）；**DOI [10.1145/3832122](https://doi.org/10.1145/3832122)**，PACMSE Vol.3, ISSTA 2026 | 2026, **ISSTA** | **A**（元数据 + 正文） | 与 F-1 的"oracle 是瓶颈"互补：该文用 mutant 生成 agent 定向攻击盲区 | **摘要与引言数字不一致**（50.20% vs 63.30%，相对 EvoSuite）→ 引用时须注明取自何处 |
| F-4 | **Test vs Mutant 之外：变异反馈是单向还是对抗** | 对照依据：F-3 的消融显示**对抗循环**是增益来源；本项目当前仅做**单向**（存活变异体 → prompt） | — | F-3 | 2026 | **A** | — | — |
| F-5 | **CANDOR：多智能体端到端 JUnit 生成**（Xu, Wang, Briand, Liu） | line/branch/mutation = **0.991 / 0.970 / 0.980**（HumanEvalJava，括号内 2384/2443）；基线为 EvoSuite + LLM-Empirical | HumanEvalJava / LeetCode-Medium / LeetCode-Hard；Java | Crossref [10.1145/3803418](https://doi.org/10.1145/3803418)（**本次独立核验 DOI 200，标题/作者/venue/日期一致**）；预印本 [arXiv:2506.02943](https://arxiv.org/abs/2506.02943) | **TOSEM 2026**（2026-03-25） | **A** | 与 F-6 的第三方复现**直接冲突**（见冲突说明） | **冲突（未解决）**：F-6 在单一 25 类系统上报告 CANDOR 的 mutation 仅 35.92%/45.63%。F-5 为该系统的原作者声明，F-6 为第三方复现且作者自承"CANDOR 的弱点在架构（类间依赖/mock），非生成能力" → **应并列呈现，不得择一** |
| F-6 | **第三方复现：agentic iteration 的效果**（Radaideh, Corriveau, Shi） | one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**；one-shot GPT-4o **69.90%** vs CANDOR **45.63%**；人类手写基线 **83.98%**（PiTest，206 变异体）；耗时 **~45 s vs ~50 h** | **单个 25 类 Java 系统**（非公开基准）；mutation score 为唯一终点 | IEEE Xplore **11655121**；Crossref [10.1109/bdai70753.2026.11655121](https://doi.org/10.1109/bdai70753.2026.11655121)（本次核验为 2026 IEEE 9th BDAI，pp.128-132，**5 页短文、非 SE 专门会议**） | 2026, **BDAI** | **A**（数值逐字）/ **范围受限** | 项目 README 引用了该文但省略限定条件（§11 C-14） | **决定性限定**：n = 1 个系统、无公开基准 → **不可外推**为"多智能体范式失效" |
| F-7 | **新 LLM 版本下测试生成工具的相对价值**（Konstantinou, Degiovanni, Papadakis） | Plain-LLM 绝对值 **49.95% / 35.33% / 33.82%**（line/branch/mutation）；**相对提升 17.72% / 19.80% / 20.92%**；请求数 CoverUp **12,264** vs Plain(Method) **11,718**；**393 类 / 3,657 方法**、**6 个完整开源 Java 仓库**；plain LLM 粒度影响成本，先类后方法的策略省约 **20% 请求**且效果略优 | Java 仓库级；复现 HITS / SymPrompt / TestSpark / CoverUp 四工具并注入新 LLM | [arXiv:2601.09695v2](https://arxiv.org/abs/2601.09695)（v2 2026-07-29）；正式版 DOI **[10.1109/icst69053.2026.00040](https://doi.org/10.1109/icst69053.2026.00040)**（本次核验：title/authors/ICST 一致） | **ICST 2026**（2026-05-18） | **A** | 与 F-2 同向（模型 > 提示/工具） | **口径易误读**：`49.95/35.33/33.82` 是 plain LLM 的**绝对值**，而 `17.72/19.80/20.92` 是其**相对优势**；两者不可混排 |
| F-8 | **TestAgent：仓库级多智能体测试生成** | 执行率 **97.46%**、line **92.34%**、branch **90.24%**、mutation **83.69%**（六个 Java 项目）；154 bugs / 92.22% | Java 仓库级 | Crossref [10.1145/3803437.3806428](https://doi.org/10.1145/3803437.3806428)（本次核验：**FSE Companion '26**，2026-07-05）；[arXiv:2607.09101](https://arxiv.org/abs/2607.09101) | **FSE Companion 2026** | **A**（指标逐字） | 与 F-5 同向（多智能体在 Java 上高覆盖） | 项目的 "1,451 methods" 在原文全文 **0 命中** → 该数字不可引用（§16 M-6） |
| F-9 | **ULT (UnLeakedTestbench)：真实世界函数级单元测试基准** | **3,909** 个函数级任务；主结果 **41.32% / 45.10% / 30.22% / 40.21%**；TestEval **91.79 / 92.18 / 82.04 / 49.69**；PLT **47.07 / 55.13 / 40.07 / 50.80** | Python 函数级；防泄漏设计 | Crossref [10.1145/3805043](https://doi.org/10.1145/3805043)（TOSEM 2026-03-28）；[arXiv:2508.00408](https://arxiv.org/abs/2508.00408) | **TOSEM 2026** | **A** | — | **该项目是基准论文，不主张"覆盖 vs 检出相关性"结论**（项目文档曾把相关性结论误挂其名下，已自纠） |
| F-10 | **覆盖与变异得分是否与有效性相关（可复现研究）**（Zhao, Zhou, Cohen） | 超过 **100,000** 个测试用例、**11 个 SOTA LLM**；branch vs raw mutation 相关 **r = 0.780**（@k=10，控制规模后）；结论为**限定性**（回归/无缺陷设定下有效，缺陷代码下不可靠） | 多模型；相关性分析 | Crossref [10.1145/3832093](https://doi.org/10.1145/3832093)（PACMSE，2026-10-01）；[arXiv:2607.22880](https://arxiv.org/abs/2607.22880)（comment 逐字"Accepted at ISSTA 2026"） | **ISSTA 2026** | **A** | 该文同时是一手依据证明 **Defects4J v3.0 存在（854 defects / 17 projects）** | 项目引用该文时的**限定条件保留正确**；但其评审对 Defects4J v3 的"不存在"结论被同一篇文献推翻（§11 C-12） |
| F-11 | **MutGen：变异引导的单元测试生成**（Wang, Xu, Briand, Liu） | **204 个 subjects**（两个基准） | Java | Crossref [10.1109/tse.2026.3682975](https://doi.org/10.1109/tse.2026.3682975)（**IEEE TSE**，2026-05）；[arXiv:2506.02954](https://arxiv.org/abs/2506.02954) | **TSE 2026** | **A** | 与 F-3 同向（变异引导有效） | — |

### 4.2 程序修复与 SWE 任务

| # | 工作 | 关键指标与数值 | 基准 / 条件 | 一手来源 | 年份/venue | 等级 | 冲突/限定 |
|---|---|---|---|---|---|---|---|
| F-12 | **SWE-bench 榜单已无法区分头部系统**（Liu, Liu, Sun, Luo, Guo） | Verified 上**榜首两条目各解决 396/500（79.2%）**；top-10 **共享 285 个成功与 51 个失败**，仅 **164 个实例**区分其结果；前沿解集中位嵌套度 **0.935**（分数隐含基线 0.774）；**模型-脚手架组合**的组内 scaffold 差异达 **29.8 pp**，而 top-30 分数跨度仅 **8.8 pp**；**29 对相邻 Verified top-30 在 α=0.05 下无一被 McNemar 区分**（Test split 区分 14/23）；254 个提交、4 个 split 的审计 | SWE-bench Verified / Test 等（**不运行模型**，审计已发布提交） | [arXiv:2609.17394](https://arxiv.org/abs/2609.17394)（v1, 2026-09-15；comment 逐字"Accepted at **ADMA 2026**"） | **ADMA 2026** | **A** | **对本项目最重要的方法学结论**：单点 resolve rate 的小差距**不构成排序证据**；应报告"比较集特异的 resolution + model-scaffold provenance"。这为项目"不追求榜单排名、转向可归因测量"的定位提供了**一手支撑** |
| F-13 | **跨语言修复 LANTERN**（Luo 等 7 人） | Rust **Pass@10 +22.09%**；Go / PHP / Kotlin / C# / Ruby 分别 **+11.31% / +9.33% / +8.87% / +8.82% / +8.33%**；**p = 0.0126**、Cliff's δ = **0.64**；xCodeEval **5,068 bugs / 11 语言** | xCodeEval | Crossref [10.1145/3744916.3773227](https://doi.org/10.1145/3744916.3773227)；[arXiv:2503.22512](https://arxiv.org/abs/2503.22512) | **ICSE 2026** | **A** | 与本项目"多智能体修复"最接近的跨语言方向；项目未做跨语言 |
| F-14 | **TraceCoder：迹驱动多智能体调试**（Huang 等 6 人） | Pass@1 **相对 +34.43%**；表行 `Ours 99.39 / 98.17 / 82.00 (↑34.43%)`、`90.72 (↑11.93%)`；baseline `Self-Debugging 61.00 / 81.05`；**迭代上限 5 次修复** | LLM 生成代码调试 | Crossref [10.1145/3744916.3773187](https://doi.org/10.1145/3744916.3773187)；[arXiv:2602.06875](https://arxiv.org/abs/2602.06875) | **ICSE 2026** | **A** | 与本项目"修复循环"直接可比；注意其**迭代预算 5 > 本项目的 3**，任何比较必须对齐预算 |
| F-15 | **FedDualFix：联邦学习多智能体修复**（Ju, Liu, Li, Wang, Cao, Chen） | 文档引 58 / 52.1%（ScienceDirect 付费墙，**未能取正文复核**） | — | Crossref [10.1016/j.asoc.2026.115898](https://doi.org/10.1016/j.asoc.2026.115898) | Applied Soft Computing 2026-10 | **B** | 指标未独立核实 |
| F-16 | **PSR：多专家 LoRA 融合的程序修复** | 未取正文数值 | — | Crossref [10.1016/j.infsof.2026.108344](https://doi.org/10.1016/j.infsof.2026.108344)（**本次核验存在**，推翻项目"未能定位原文"的勘误） | Information and Software Technology | **C**（仅元数据） | 项目 ADR-0017 的勘误应撤销 |

### 4.3 与本项目"最强单提示基线"的直接相关发现（本次重建的关键结论）

| 结论 | 一手依据 | 对本项目的含义 |
|---|---|---|
| **"plain LLM 优于复杂编排/工具"已被两篇独立一手研究复现** | F-7（ICST 2026，6 Java 仓库 / 393 类 / 3,657 方法）、F-2（ClassEval，模型 > 提示） | 项目观察到的"dp 单提示优于完整系统"**在文献中有独立同向证据**；但**这不等于"多智能体范式失效"**——F-5/F-8 在 Java 上报告了多智能体高覆盖 |
| **"oracle 失效"是 2025–2026 的核心瓶颈，而非"覆盖不足"** | F-1（覆盖触发 32–39% 但检出仅 1–2%）、F-2（覆盖近饱和无鉴别力） | 项目"48.6% 的行从未产生 assert 失败"与这一前沿诊断**同构**。**这是本项目最有价值的锚点**：它可以在文献中找到一个真实的开放问题 |
| **榜单边际已不能排序，测量设计本身成为贡献** | F-12（Verified 榜首并列 396/500；相邻 top-30 无一显著） | 项目"测量基础设施 + 诚实负结果"的路线**在方法学上有真实空间**，但必须做到该文提出的五步审计协议（共享结果画像、配对检验、分组敏感性、分辨率实例预算、model-scaffold provenance） |
| **对抗/共演化是当前有验证增益的设计** | F-3（AdverTest：FDR +8.56%，ISSTA 2026） | 项目仅有**单向**变异反馈；这是最直接、可复制的竞争路线 |


### 4.4 官方榜单口径的独立复算（A 级：直接读官方结果文件）

> 来源：`github.com/swe-bench/experiments` 官方仓库的逐条 `metadata.yaml` / `results/results.json`（**不是**站点 HTML、**不是**第三方页面）。分母固定 **Verified = 500 / Lite = 300**。

| 榜单/条目 | 系统 + 模型 | resolve rate | 等级 |
|---|---|---|---|
| **Verified 榜首（并列）** | live-SWE-agent + Claude 4.5 Opus（`20251215_…`） | **396/500 = 79.2%** | A |
| **Verified 榜首（并列）** | Sonar Foundation Agent + Claude 4.5 Opus（`20251205_…`） | **396/500 = 79.2%** | A |
| Verified | TRAE + Doubao-Seed-Code | 394/500 = 78.8% | A |
| Verified | OpenHands + Claude Opus 4.5 | 388/500 = 77.6% | A |
| Verified 最新条目 | mini-SWE-agent v2.4.2 + Gemini 3.5 Flash（`20260901_…`） | **359/500 = 71.8%** | A |
| Verified | OpenHands + GPT-5 | 359/500 = 71.8% | A |
| Verified | Moatless Tools + Claude 4 Sonnet | 354/500 = 70.8% | A |
| Verified | OpenHands + CodeAct v2.1 | 265/500 = 53.0% | A |
| Verified | Agentless-1.5 + Claude 3.5 Sonnet | 254/500 = 50.8% | A |
| Verified | SWE-RL（Llama3-70B + Agentless Mini） | 206/500 = 41.2% | A |
| **Lite 榜首** | ExpeRepair-v1.0 + Claude 4 Sonnet | **181/300 = 60.3%** | A |
| Lite | Agentless-1.5 + GPT-4o | 96/300 = 32.0% | A |
| Lite | AutoCodeRover + GPT-4o | 92/300 = 30.7% | A |
| Lite | SWE-agent + GPT-4（1106） | 54/300 = 18.0% | A |

**三条必须知道的口径事实（A 级）**：
1. **Lite 已停更**：最后一条官方提交为 `20250911_isea_*`（2025-09-11），此后无新条目。
2. **提交规则重大变更**：官方 README 载明 **[2025-11-18] 起 SWE-bench Verified 与 Multilingual 仅接受"学术团队/研究机构 + 方法开源 + 有同行评审论文"的提交**（明确列出仍合格者 OpenHands / SWE-RL / FrogBoss / AutoCodeRover；不再合格者 Augment Code / Solver AI / Honeycomb.sh）。**对本项目的操作含义：当前不具备提交资格，须先有同行评审论文与公开制品。**
3. **官方计分陷阱**：最新条目 `20260901_mini-v2.4.2_gemini-3-5-flash` 的 `per_instance_details.json` **仅 441 行**，若以 441 为分母会得 **81.4%**，而官方值为 **71.8%（359/500）**——**高估 9.6 pp**。任何"逐实例求和 ÷ 文件行数"的复算脚本都会犯此错，**必须使用 500/300 固定分母**。

### 4.5 自愈/运行时方向的基线判定（重要负面结论）

| 来源 | 报告内容 | 本次核验判定 |
|---|---|---|
| arXiv:2601.17542（2026-01） | 声称 MTTR 改善，**摘要未给任何数值** | B（无数字，不可用） |
| SF-DTM（arXiv:2505.01215） | availability **+13.2%**；MTBF/MTTR 仅相对值 | B（无绝对值；域为数字孪生，不可比） |
| AutoGuard（arXiv:2512.04368，IEEE UPWIECON 2025） | MTTR **−38%**、检测准确率 +22% | B（**模拟环境**、无绝对值、无基线代码） |
| AegisFlow（arXiv:2610.06971） | MTTR **170 min → 3.2 min（+98.1%）**、patch 成功率 92% | B（**n = 5 个失败场景**支撑 98% 主张；无独立复现） |
| 项目文档中的 "85% MTTR reduction" | — | **D：本次多轮检索 0 命中一手来源**（与项目自评一致，处置正确） |

> **独立结论（可直接引用）**：截至 2026-10-11，**"自愈系统的 MTTR / detection latency / recovery quality"在 2025–2026 一手文献中不存在可信的统一基线**：现有来源要么只有相对值、要么无数字、要么建立在模拟环境或 n<10 的案例上；且**没有任何一篇给出 detection latency 与 recovery quality 的标准化定义与可复算测量协议**。
> 因此 §5 中该维度标注"**前沿基线未建立，无法对比**"是有依据的判定，而非检索不足。

### 4.6 神经符号/逻辑驱动方向的一手基线

| 工作 | 指标 | 数值 | 基准/条件 | 来源 | venue | 等级 |
|---|---|---|---|---|---|---|
| **Gordian**（KLEE + LLM ghost code） | 覆盖率提升 / token 削减 | 相对**传统符号执行** **+28.5–115.2%**；相对 LLM-based 符号执行 **+74.1–189.8%**；LLM token **−91–96%** | 合成 logic bombs + FDLibM + 4 个结构化输入程序（libexpat/jq/bc/libyaml） | DOI [10.1145/3832126](https://doi.org/10.1145/3832126)，PACMSE Vol.3 ISSTA, pp.802-823 | **ISSTA 2026** | **A**（Crossref + OpenAlex 双源） |
| **TestTailor** | 覆盖率提升 / 成本 | **数值未取得**（仅确认存在与方法） | Python，对照 CoverUp | DOI [10.1145/3797140](https://doi.org/10.1145/3797140)，PACMSE Vol.3 FSE, pp.277-298 | **FSE 2026** | A（存在）/ 🚫 数值 |
| **SpecGen** | 可验证规约生成 | **279/385** 程序 | SV-COMP Java + 自建；对照 Houdini/Daikon | [arXiv:2401.08807](https://arxiv.org/abs/2401.08807) | 预印本 | B |
| **nl2postcond** | 捕获真实历史 bug | **64 个 Defects4J bug** | Defects4J | [arXiv:2310.01831](https://arxiv.org/abs/2310.01831) | FSE 2024 | B |
| **AssertFlip** | fail-to-pass 成功率 | **43.6%** | SWT-Bench Verified | [arXiv:2507.17542](https://arxiv.org/abs/2507.17542) | 预印本 | B（未二次核验 SWT-Bench 官方榜） |
| **SWE-Proof / Benchproofer** | 形式化验证 vs 测试 | **1/4 通过测试的补丁存在反例**；正确形式化规约把 resolution **85% → 95%**；自撰规约 agent **不比无辅助基线更好**；仅 **56%** 规格通过审计 | SWE-bench Verified 500 issues 形式化重铸 | [arXiv:2609.21190](https://arxiv.org/abs/2609.21190) | 预印本 | B |
| "CodeQL 引导的测试生成" | — | **arXiv 全库 0 命中** | — | 本次检索 | — | **D（不得引用）** |

> **注意（Gordian 的基线口径）**：`+28.5–115.2%` 是相对**传统符号执行**，**不是**相对一般测试生成工具。混用会造成严重高估。

### 4.7 疑似不存在 / 未取得一手来源清单（本次汇总，含我方独立复核）

| 名称 | 判定 | 本次核验方法 | 备注 |
|---|---|---|---|
| **TwinMem / TwinMem-Agent** | **D（arXiv 0 命中）** | 本次独立执行 `export.arxiv.org/api/query?search_query=all:"TwinMem"` → **0 条 entry** | 项目文档亦未引用；**不得进入基线** |
| **HumanEvalJava / HumanEval-J**（作为基准名） | **D（arXiv 0 命中）** | 本次独立核验 0 命中 | 但 CANDOR **正文**使用了 "HumanEvalJava" 这一名称（见 F-5），故应表述为"**非标准基准名，检索不可定位**"，而非"不存在" |
| **Defects4J v3**（作为"不存在"主张） | **该主张被推翻** | [arXiv:2607.22880](https://arxiv.org/abs/2607.22880) 正文逐字"854 defects across 17 projects" | 见 §11 C-12 |
| **ARC-APR** | **D** | OpenAlex 精确检索前 5 条全无关；多轮 web_search 无命中 | 项目处置正确 |
| **"85% MTTR reduction"** | **D** | 唯一来源为个人 GitHub README | 项目处置正确 |
| **CodeQL 引导的测试生成** | **D** | arXiv `all:"CodeQL" AND abs:"test generation"` = 0 | 建议从基线表删除 |
| **AgentRepair** | **存在（付费墙）** | 本次独立核验 Crossref [10.1109/dsa66321.2025.00025](https://doi.org/10.1109/dsa66321.2025.00025) → *"AgentRepair: Multi-Agent, AST-Anchored, Retrieval-Augmented Program Repair for Cold-Start Environments"*, IEEE DSA 2025，2025-11-24 | **"疑似不存在"措辞应改为"存在但指标不可得"** |
| **CANDOR 的 "TOSEM 2026" venue** | **A（已确认）** | 本次独立 Crossref 核验 [10.1145/3803418](https://doi.org/10.1145/3803418) → container = *ACM Transactions on Software Engineering and Methodology*, 2026-03-25 | 侦察员的 D 级判定是其 arXiv 检索面受限所致（DBLP 被反爬），**已由我方机读 DOI 核验纠正** |

### 4.8 引用映射纠错（影响项目引用准确性）

| 纠错项 | 事实 | 影响 |
|---|---|---|
| `arXiv:2502.02794` | 实际是 **METAMON**，**不是** TestGenEval | TestGenEval 真实 id = [2410.00752](https://arxiv.org/abs/2410.00752) |
| 论文 Agentless 的 "32.00%" | 对应 **Agentless-1.5**；初版 Agentless 官方 Lite = 27.3% | 版本混淆会高估 |
| **AID** | 已更名 **TrickCatcher**（[2404.10304](https://arxiv.org/abs/2404.10304) v1=AID / v2=TrickCatcher, ACL 2025） | 按旧名检索必失败 |
| **TestPilot**（2302.06527） | 是 **JavaScript/npm** 工具 | 在 Java 语境引用属基准错配 |
| **CodeMonkeys 66.2%** | 是对**他人提交做集成选择**，非单体系统成绩 | 不可作为单体系统基线 |

### 4.9 覆盖度与残余缺口（诚实声明）

| 分表 | 状态 | 残余缺口 |
|---|---|---|
| 测试生成（覆盖/变异/检出） | **已完成（A/B 混合）** | CoverUp / HITS / TestSpark / ChatUniTest 的**原论文数值**未逐字取到（摘要未给或付费墙）→ 未进入 §5 的 SOTA 列 |
| 多智能体 / 程序修复 | **已完成（A 为主）** | FedDualFix（ASOC 付费墙）仅 B 级；Kimi-Dev 60.4% 为单源 B 级，无官方榜单条目 |
| 自愈 / 运行时（MTTR 等） | **已完成——结论是"前沿基线未建立"** | 见 §4.5：全部一手来源均不满足"绝对值 + 公开基准 + 同行评审"三要素 |
| 逻辑驱动 / 神经符号 | **部分完成** | Gordian / TestTailor 已 A 级确认存在；TestTailor 数值不可得；"CodeQL 引导"D 级 |
| 评估方法学 | **已完成（A）** | — |

> **合规声明（重申）**：未取得一手来源的条目一律标注 D 级，**不得进入 §5 对比矩阵的"前沿 SOTA"列**；对应维度标注"前沿基线未建立，无法对比"。

---

## 5. 项目与前沿量化对比矩阵

> **纪律**：凡"前沿基线未建立（§4.9）"或"项目数据为 E 级（§3.11）"的维度，一律标注"**无可比基线 / 无法对比**"，**不给出差距数字**。
> **两级分母并列**：项目侧所有 detection/repair 数字同时给出"**可测口径**"与"**all-task 口径**"，这是本项目最容易被误读的地方。

### 5.1 主对比矩阵

| 维度 | 2025–2026 前沿 SOTA（一手） | 证据等级 | 项目现状（本次复算） | 项目证据等级 | 绝对差距 | 相对差距 | 竞争位置 | 超越路径 | 可否对比 |
|---|---|---|---|---|---|---|---|---|---|
| **测试生成：结构覆盖（line）** | CoverUp（FSE 2025）；TestAgent line **92.34%**（六 Java 项目）；ULT 主结果 **45.10%**（函数级） | A | 被测代码行覆盖（合成集）**84.0–93.6%**；QuixBugs **69.12%**（n=50） | **B**（分子/分母口径已在 §3.1 P15 限定） | — | — | **不可判定**：项目与前沿**不同基准、不同语言、不同粒度**（合成 Python 函数级 vs Java 仓库级 vs 真实 Python 函数级） | — | **否**（无可比条件） |
| **测试生成：编译/可执行率** | TestAgent 执行率 **97.46%**；AdverTest 测试套件"全部可编译" | A | `spec_compile_rate` **0.205–0.219**；生成测试的 pytest **执行错误率**有落盘但未汇总 | A（字段可复算） | — | — | **否** | 两者**度量对象完全不同**（前者=生成测试能否运行；后者=规约子句能否编译） | — | **否**（维度错配） |
| **测试生成：缺陷检出（语义等价口径）** | **无等价口径**：前沿以 mutation score / FDR / 故障检出率为主终点；F-1 明确区分 trigger 与 detect，并报告检出率 **1–2%** | A | aitester **14.0%**（可测 78/556）/ 12.8%（全集 78/609）；df **48.9%**（279/571）；QuixBugs **45.9%**（17/37） | A | — | — | **不可直接判定**；但**同构诊断**成立：项目"**48.6% 的行从未产生 assert 失败**"与 F-1 的"覆盖触发率高但 oracle 检出率 1–2%"是**同一类失效** | A1/A2/A4 | **否**（口径不同）+ **可定性对标** |
| **测试生成：变异得分** | 项目自述区间；前沿以 mutation score 为主终点（MutGen / CoverUp / AdverTest） | A（前沿存在）/ B（数值未逐字） | 合成集 **0.818–0.976**（aitester）/ 0.986–0.997（df）；QuixBugs **0.721** | A | — | — | **不可判定**：合成集变异体 **1–16 个/任务**（中位 9），**近饱和**，鉴别力不足 | A1 | **否**（基线未逐字建立） |
| **多智能体协作：Pass@K / 修复成功率** | TraceCoder（ICSE 2026）Pass@1 **相对 +34.43%**；LANTERN（ICSE 2026）跨语言 Pass@10 **+22.09%**（Rust） | A | 项目**未测 Pass@K**；修复以 gold 测试通过为终点 | — | — | — | **否** | A3 | **否**（指标未定义） |
| **程序修复：端到端成功率** | SWE-bench Verified 榜首 **396/500 = 79.2%**（F-12，**且该文实证榜单边际不可排序**）；TraceCoder 修复迭代上限 5 | A | **all-task 21.84%**（57/261 合成）/ **E1/E2 16.67%**（58/348）；QuixBugs all-task **74.0%**（37/50） | A | **不计算**（任务分布与评测协议均不同） | **不计算** | **不可比**；仅在"与自身基线比较"的层面可读作**落后**（合成集 21.84% vs 自身可重放口径 39.31%，且 48.6% 行未进入修复） | A3 | **否**（**不可比**，本条不参与前沿差距判定） |
| **修复：可重放口径** | 前沿无此口径 | — | **39.31%**（57/145）/ 54.72%（58/106） | A | — | — | 项目**自定义口径**，须自带定义引用 | A3 | **否** |
| **自修复：MTTR / detection latency / recovery quality** | **前沿基线未建立**（§4.9）；"85% MTTR reduction"经核验**确无一手来源** | **D** | 项目**无运行时自愈组件**（§8 DM-4）→ 无该类指标 | — | — | — | **不存在该能力** | — | **否**（维度不适用） |
| **逻辑驱动：SMT 效率 / 约束覆盖率 / 形式化验证通过率** | **前沿基线未建立**（§4.9） | — | `spec_compile_rate` 0.205–0.219；`spec_expr_coverage` 0.723–0.741；SMT **不做**实现-后件验证 | A（字段） | — | — | **不可判定** | A2 | **否**（基线未建立） |
| **成本：$/task** | AdverTest 报告成本分析（未取数值）；项目侧 $/task 0.0259/0.0034/0.0045 | B/D | 数值可复算但**热缓存 0-token 污染**，且 `token_usage` 无 in/out 拆分 → **成本比较当前不可用**（§3.9） | **B** | — | — | **不可判定** | P1-4 | **否**（记账不可比） |
| **可复现性** | TSE/ICSE/ISSTA 一手论文多数提供公开仓库（AdverTest 已公开；LANTERN/TraceCoder 有 artifact） | A | **强**：git_sha + model + temperature + seed + env_snapshot；工件 SHA256SUMS；预注册；但**热缓存重放**与 **env_snapshot 缺关键开关**（存量工件 37 键） | A/B | — | — | **持平或略优**（在"自我披露测量伪影"这一维度上**项目高于多数论文**） | P0-5/P1-4 | **可对比（定性）** |
| **统计严格性** | F-12 提出五步审计协议（共享结果画像、配对检验、分组敏感性、分辨率实例预算、model-scaffold provenance） | A | 项目有 McNemar / 配对检验 / 聚类稳健性（n_eff=39.9, ICC=0.671），但**伪重复未折减 n**（按 `task_id` 对齐后 249–252/261 行相同） | B | — | — | **落后于方法学前沿**（缺"独立运行数"与"配对分辨率预算"） | P0-5 | **可对比（定性）** |
| **外部有效性** | 前沿主结果均在公开基准（Defects4J / SWE-bench / ClassEval / xCodeEval / TestEval） | A | **唯一有效真实基准 = QuixBugs（50 个玩具程序）**；真实仓库工件 365 行**结构性不可测**；主实验集为**自生成合成集（87 任务 / 29 模板）** | A（普查） | — | — | **显著落后**（这是本项目最严重的短板） | A4 | **可对比（定性，明确落后）** |

### 5.2 竞争位置判定（独立结论）

| 子方向 | 判定 | 依据 |
|---|---|---|
| LLM 测试生成 | **不处于前沿**;合成集检出**低于自身最强单提示基线**（14.0% vs 48.9%） | §3.3；F-2/F-7 独立同向 |
| 程序修复 | **落后**（合成集 all-task 21.84%；真实基准仅玩具程序 74.0% 且口径自定） | §3.5；F-12/F-14 |
| 多智能体编排 | **无正面证据**；且现有对照无法分离"协议 × 编排" | §9.1 R1 |
| 逻辑驱动 | **无实证**（主口径零注入） | §3.6 |
| 自修复 | **能力不存在** | §8 DM-4 |
| **测量与实验方法学** | **这是项目唯一具备相对优势的维度** | §5.1 末四行；F-12 |

---

## 6. 超越前沿方法设计

> **总原则**：§5 的结论是"项目在**能力维度**上不处于前沿，但在**测量方法论**上有真实空间"。因此本节不提供"再堆一个 agent 就能超过 SOTA"的空想路径，而是给出**四条以第一性原理与一手证据为依据、可被独立证伪**的路径。
> **每条路径的预期提升一律标注为 E 级（推测）**，除非其依据本身是一手已发表结果。

### 6.0 目标函数的一致性论证（所有路径的前提）

本次评审发现的最深层问题：**项目的 detection 与 repair 在数学上耦合**——若系统用补丁使测试转绿，而补丁是假修复，则该行 `detection_rate = 0`（因为最终测试在 buggy 代码上不再变红）。实测证据：`red_then_green` 93 行中 **34 行**因此丢掉了检出。这使"测试质量"无法与"修复策略"分离度量。

**因此路径 A 是整个方案的支点**：先让"生成质量"成为**政策无关（policy-agnostic）**的可测量量，其余路径才有可优化的目标。

---

### 路径 A｜政策无关的"变异判别力"oracle 指标（Mutant-Discrimination Oracle, MDO）

| 项 | 内容 |
|---|---|
| **子方向** | 测试生成 × 评估方法学 |
| **技术路径** | 对每个生成测试集 `T`，在**固定变异体池** `M`（由确定性算子生成，与 LLM 无关）上计算两个量：① 触发率 `FTR(T) = |{m: ∃t∈T, output(m,t) ≠ output(p,t)}| / |M|`；② 判别率 `FDR(T) = |{m: ∃t∈T, t 在 m 上失败}| / |M|`。**关键**：测试集在执行**之前**即被冻结归档，指标计算与任何补丁/修复策略**完全解耦**。再引入**逐断言归因**（哪条断言杀死了哪个变异体），得到可聚合的"断言-变异体"矩阵 |
| **前沿参考** | F-1（arXiv:2609.09315，明确区分 trigger 与 detect，并指出 oracle 是瓶颈）；F-2（ClassEval 上覆盖无鉴别力）；F-11（MutGen，变异引导有效） |
| **差异化点** | ① 前沿把 FTR/FDR 用作**评测终点**；本条把它用作**生成侧的一等优化目标 + 归因矩阵**；② 与项目现有单向"存活变异体→prompt"不同，**先度量再优化**，避免以覆盖为代理；③ 变异体池**与 LLM 解耦**（确定性算子），排除"LLM 变异体自身质量"这一混杂（AdverTest 用 LLM 生成变异体，其质量本身是变量） |
| **理论基础** | 变异测试的耦合效应假设（DeMillo et al. 1978；Offutt 1992）；F-1 已实证"触发 ≠ 检出"，因此必须**分开度量**；本项目实测 `mutants_total` 中位仅 9 个 → **必须先把变异体池扩大一个数量级**（否则指标饱和，见 `mutation_score` 0.986–0.997） |
| **预期性能提升** | **E 级（推测）**：若把"从未产红"的 296 行压到 20% 以下（对齐 df 的 2.5% 是上界），按"产红率 → 检出"的条件转化率 30.0% 外推，合成集检出可由 14.0% 升至约 **35–48%**；**置信度：中**（依据 = 本次实测的条件转化率与产红率分解，非二手转述）。**注意**：这只在**合成集**上成立，不代表真实代码上成立 |
| **实验验证方案** | 基准：① 合成集（对照内部口径，n=261，三种子，缓存关闭）② **QuixBugs**（真实，50 任务）③ **ClassEval**（与 F-2 可直接对标）④ **ULT/TestGenEval**（若许可允许）。对照：plain_llm / plain_llm_df / aitester / **aitester+MDO**（四臂）。指标：FTR、FDR、mutation score（**每任务 ≥100 个确定性变异体**）、line/branch 覆盖（辅助，不单独作为证据）。统计：配对 McNemar（同任务配对）+ 聚类稳健（pattern 为簇，报 `n_eff`）；**报告"独立运行数"而非文件数**（§3.8）；随机种子固定并**关闭缓存**（`AITESTER_LLM_CACHE=0`） |
| **反事实推演** | 若前沿方法也采用 MDO 作为目标：**项目的护城河 = 没有任何护城河**。MDO 是公开可复制的测量改进，AdverTest 类工作若接入 MDO 会立即获得同等或更强效果（它有对抗循环 + 已公开代码）。**项目唯一可持续的差异化是"测量 + 归因的严谨性"本身**，不是算法 |
| **实现路径与里程碑** | 短期（1–3 月）：实现确定性变异体池（AST 算子 ≥10 类，每任务 ≥100 变异体）→ 落盘 `mutants_total/killed/断言-变异体矩阵`；中期（3–6 月）：把 FDR 接入生成侧反馈（替换现有覆盖/存活反馈）；长期（6–12 月）：在 ClassEval + ULT 上给出"FDR 与真实故障检出的相关性"一手结论 |
| **独立验证判定标准** | **成功**：在**关闭缓存、三种子、n_eff ≥ 30** 的条件下，`aitester+MDO` 的合成集 FDR 相对 `aitester` **提升 ≥ 10 pp 且 McNemar p < 0.05（Holm 校正后）**，且 QuixBugs/ClassEval 上**方向一致不反转**。**失败**：FDR 提升 < 5 pp，或仅在合成集成立而真实基准反转，或 `mutants_total` 中位 < 30（指标饱和即无效） |

---

### 路径 B｜修复循环的"单调红保持"与策略切换（替换提前终止）

| 项 | 内容 |
|---|---|
| **子方向** | 程序修复 × 闭环控制 |
| **技术路径** | ① 把 `_recent_repairs_invalid` 从**终止条件**改为**策略切换条件**（切换候选生成 / 重新定位 / 局部编辑窗口）；② 引入**单调性约束**：任何再生成或再修复都必须保持"已获得的红"（红证人不被抹除）；③ 修复停机改为**预算自适应**（按 token 预算而非固定 3 次迭代） |
| **前沿参考** | F-14（TraceCoder, ICSE 2026：迭代上限 **5**，Pass@1 相对 +34.43%）；F-13（LANTERN：跨语言 + 多智能体精化，p=0.0126）；项目自身实测：QuixBugs **24/50 被提前终止**，其中 **13 行最终被 gold 判定修复正确** |
| **差异化点** | ① 前沿用"更多迭代 + 更强反馈"；本条针对**已被证实的路由损失通道**（13/50 = 26% 可回收）做定向修复，成本极低；② 单调红保持是**现有红回归门（默认关）的推广**，实测有 **34/609 行**被抹红 |
| **理论基础** | 本次实测：提前终止发生在 `iteration < max_iterations` 时，而该路径上 13 行已被 gold 判定正确 → **终止判据与真实成功信号不一致**（假阴性终止） |
| **预期性能提升** | **E 级（推测）**：仅回收"被提前终止"通道，QuixBugs all-task 修复率上界由 74.0% → **~90%**（若 13 行全部保住）；合成集因 48.6% 行从未进入修复，提升幅度极小（**< 2 pp**）。**置信度：高（对 QuixBugs 该批）/ 低（对合成集）**。依据 = 本次逐行复算，非推测转述 |
| **实验验证方案** | 基准：QuixBugs（首要）+ 合成集。对照：当前策略 vs 策略切换 vs 单调红保持 vs 两者叠加（4 臂）。指标：all-task 修复率、可重放口径修复率、迭代均值、token/task、`red_then_green ∧ det=0` 行数。统计：配对 McNemar + 预算匹配（对齐 token） |
| **反事实推演** | 若前沿也做单调性维护：TraceCoder 的 5 次迭代已隐含预算更大，**项目在预算对齐后未必占优**；护城河 = 无。该路径是"**补课**"而非"超越" |
| **里程碑** | 短期（1 月）：策略切换 + 落地埋点；中期（2 月）：预算自适应；长期：与 A 联合优化 |
| **独立验证判定** | **成功**：QuixBugs all-task 修复率 ≥ 85%（当前 74.0%）**且** `red_then_green ∧ det=0` = 0 **且** token/task 不增 > 20%。**失败**：合成集修复率提升 < 2 pp（说明瓶颈不在路由，应回到路径 A） |

---

### 路径 C｜条件生成的"必然产红"：从"从未产红"到"定向反例"

| 项 | 内容 |
|---|---|
| **子方向** | 测试生成 × 神经符号（约束求解） |
| **技术路径** | 用**符号/具体化执行**为"从未产红"的 296 行生成**必然违反规约的输入**：① 从 docstring/类型/规约抽取前置条件与前件约束；② 用 z3 求**前件可行域内的边界点与极值点**（项目已有 `spec_smt.py` 的 `Optimize` 基础设施）；③ 用 CrossHair / hypothesis（`pyproject.toml` 已声明 `[formal]` extras）验证候选输入确实产生行为差异；④ 仅当候选输入在 **buggy 与 gold-fixed 上行为不同**时，才交给 LLM 生成断言 |
| **前沿参考** | F-1（"挑战性故障难以触发"是核心瓶颈之一）；项目自身 `src/specs/spec_refine.py`（CEGIR，**已实现但未接线**）+ `src/tools/logic_spec.py` 的边界三元组 |
| **差异化点** | ① 前沿多把符号执行与 LLM 并列/串联（如 SymPrompt 类）；本条用"**求解器负责找输入，LLM 只负责写断言**"的严格分工，**把触发与判别解耦**（正是 F-1 指出的病灶）；② 复用项目**已有的** SMT 与 hypothesis 基础设施，不新建框架 |
| **理论基础** | F-1 的 trigger/detect 分离；Concolic 执行的可达性保证（若求解成功，输入**必然**到达目标分支）；项目 `spec_ir_v2.py` 当前表达力为 QF 标量 → **需先扩展**（见 P1-6） |
| **预期性能提升** | **E 级（推测）**：若能把 296 行中的 **30–50%** 转为"必然产红"，合成集检出由 14.0% 升至 **~25–38%**（按条件转化率 30% 外推）。**置信度：低–中**：因为前置条件抽取在无规约代码上不可靠，且需先扩展 DSL 表达力（当前 `compile_rate` 仅 0.21，可执行规约比例 ≈ 0.15） |
| **实验验证方案** | 基准：QuixBugs（有 docstring/结构清晰）+ ClassEval。对照：纯 LLM 生成 vs 求解器定向输入 + LLM 断言。指标：`从未产红` 比例、detection、求解成功率、求解耗时、token/task。统计：配对检验 + 求解预算敏感性分析 |
| **反事实推演** | 若前沿也接入求解器：**符号执行找输入并不稀有**（KLEE/CrossHair 已有），护城河弱；但**"触发/判别严格分工 + 以 FDR 度量"的组合**目前在文献中未见一手对应（**E 级推测，需检索确认**） |
| **里程碑** | 短期（1–2 月）：接通 CEGIR（`spec_refine.py` 已在仓库中但未接线）；中期（3–4 月）：DSL 扩展到数组/量化；长期：跨任务求解器缓存 |
| **独立验证判定** | **成功**：`从未产红` 行数下降 ≥ 50% **且** detection 提升 ≥ 8 pp **且** 求解失败时**明确落盘 `unsolved`**（不静默降级）。**失败**：求解成功率 < 20%，或提升被求解耗时/成本抵消（token+time 成本上升 > 50%） |

---

### 路径 D｜外部有效性重建：真实基准 + 五步审计协议

| 项 | 内容 |
|---|---|
| **子方向** | 评估与基准（**本项目最紧迫的短板**） |
| **技术路径** | ① 把 `instance_code` 物化改为**前置硬门**（缺失即 fail-fast，禁止产出"负结果"行）；② 接入 **ClassEval**（可与 F-2 直接对标）+ **ULT/TestGenEval**（许可门槛已由项目登记）+ **SWE-Rebench**（防污染滚动基准）；③ 按 F-12 的五步协议报告：共享结果画像、配对 McNemar、分组敏感性、**分辨率所需实例预算**、**model-scaffold provenance**；④ 所有报表输出"**独立运行数**"（折减 §3.8 的伪重复） |
| **前沿参考** | F-12（ADMA 2026，一手方法学）；F-2（ClassEval 上的覆盖无鉴别力）；F-9（ULT，3,909 任务）；F-1（6,066 挑战故障） |
| **差异化点** | ① 项目现有"**测量诚实度**"（fail-closed `None`、工件 SHA256SUMS、ADR 记录伪影）在文献中**不常见**，与 F-12 的诉求同向；② 项目已具备**立即落地**的工程条件（CI 门禁、provenance、ratchet），只需接外部基准 |
| **理论基础** | F-12 实证"榜单边际不可排序"（相邻 top-30 无一显著）；因此**"精确测量 + 归因"比"刷分"更有科学价值** |
| **预期性能提升** | 不是性能提升，而是**结论有效性**提升：从"仅在自生成合成集上成立"升级为"在至少 2 个公开基准上可复现"。**置信度：高**（工程路径清晰，依据为本项目已有基础设施） |
| **实验验证方案** | 三个基准 × 四臂（plain_llm / plain_llm_df / aitester / aitester+MDO）× 三种子 × 缓存关闭；预注册判定阈值；全部工件入库并 SHA256 |
| **反事实推演** | 无竞争风险——**这是方法学基础设施，可被引用而非被超越**；风险是"做出来后发现自己确实落后"，但那是**真实信息**，优于当前状态 |
| **里程碑** | 短期（1 月）：fail-fast 物化门 + ClassEval 接入；中期（2–3 月）：ULT/SWE-Rebench + 五步协议报表；长期：公开 artifact 供第三方复现 |
| **独立验证判定** | **成功**：≥ 2 个公开基准上产出**非缺失**的 detection/repair 数字，且第三方（不含作者）能依据 artifact 复现 ≥ 80% 的数字（相对误差 < 1%）。**失败**：任一基准上再次出现"0/N 但字段缺失"，或复现率 < 50% |

---

### 6.5 四条路径的优先级与相互关系

| 路径 | 依赖 | 优先级 | 成本 | 主要收益 | 主要风险 |
|---|---|---|---|---|---|
| **A｜MDO 政策无关指标** | 无（可立即开始） | **P0** | 中 | 让"生成质量"可独立度量；是 B/C 的优化目标 | 可能只是把问题重新表述（若 FDR 与 detection 高度相关则无信息增益） |
| **B｜修复循环单调性** | 无 | **P1** | 低 | 直接回收已知损失（QuixBugs 13/50） | 合成集上几乎无收益 |
| **C｜求解器定向反例** | A（需要产出目标）、P1-6（DSL 扩展） | **P2** | 高 | 攻击第一瓶颈"从未产红" | 无规约代码上前置条件不可靠 |
| **D｜外部有效性 + 审计协议** | 无 | **P0（与 A 并列）** | 中 | 结论有效性；方法学贡献 | 可能证伪项目现有全部正面主张（但这是正确的结果） |

---

## 7. 差距分析表

### 7.1 能力差距（按严重度排序）

| # | 维度 | 项目现状（可验证） | 目标/前沿参照 | 差距性质 | 严重度 |
|---|---|---|---|---|---|
| G1 | **外部有效性** | 唯一有效真实基准 = QuixBugs（50 个玩具程序）；真实仓库工件 365 行**结构性不可测**；主实验集为自生成合成集（87 任务 / **29 个模板**，ICC 0.671，`n_eff=39.9`） | 公开基准（Defects4J / SWE-bench / ClassEval / ULT / xCodeEval） | **结构性**（不是数值差） | **P0** |
| G2 | **测试判别力** | 合成集 **48.6% 的行从未产生 assert 失败**；检出 14.0%（可测口径） | F-1：同类失效在 LLM 生成代码上普遍，但前沿已把它**作为一等问题度量**（trigger/detect 分离） | 能力 + 度量 | **P0** |
| G3 | **检测与修复的耦合** | detection 与 repair 数学耦合（假修复 → 该行 detection 归零）；`red_then_green` 中 34/609 行因此丢检出 | 无现成方案（**这是可发表的切口**） | 度量设计 | **P0** |
| G4 | **修复端到端成功率** | all-task 21.84%（57/261）；QuixBugs 74.0%（玩具程序） | SWE-bench Verified 榜首 79.2%；TraceCoder 迭代预算 5 | 能力 | **P1** |
| G5 | **逻辑驱动** | 主口径零注入；`spec_compile_rate` 0.205–0.219；DSL 仅 QF 标量；CEGIR 未接线 | 无对应前沿基线（§4.9） | 实现完成度 | **P1** |
| G6 | **统计独立性** | 伪重复：同 seed 重跑计为独立批次（按 `task_id` 对齐后 **249–252/261** 行逐值相同） | F-12 五步审计协议 | 方法学 | **P1** |
| G7 | **成本可比性** | 热缓存 0-token 污染；`token_usage` 无 in/out 拆分 | 成本感知评估（cost-aware）已成常规要求 | 记账 | **P1** |
| G8 | **安全默认档** | LLM 测试代码默认可写宿主文件、可联网；内核沙箱 opt-in 且含仓库根可写 | 容器化默认开 | 合规/安全 | **P1** |
| G9 | **多智能体叙事** | "编排净负贡献"缺"关协议"对照臂 → 交互效应不可分离 | F-5/F-8 在 Java 报告多智能体高覆盖 | 实验设计 | **P2** |
| G10 | **进程与资源卫生** | 裸 `subprocess.run(timeout=)` → 已遗留 3 个孤儿进程（16.5 h，100% CPU） | 工程常规 | 工程 | **P2**（但修复成本极低） |

### 7.2 与"科学性问题定义"相关的差距

| # | 问题 | 说明 |
|---|---|---|
| S1 | **"检出"的定义域未在对外文档中说清** | 实测口径 = "该测试能否区分 buggy 与 gold-fixed 两版实现"，**不是**"断言是否正确/是否符合规约"。项目文档多处把它读作"测试质量"（如"高覆盖 ≠ 高检出"的归因段落）。**必须在方法节显式定义并在结果节反复标注** |
| S2 | **"修复率"的三套口径易被混用** | 可重放（39.31%）/ M1 可测（92.5% QuixBugs）/ all-task（21.84%）。项目已有 `repair_caliber_matrix.md`（正确做法），但 README 头部仍只给单值 |
| S3 | **合成任务的"难易"未校准** | 87 任务 = 29 模板；`difficulty` 由模板自带（1–5）而非实测校准 → 任何"难度分层"结论都受模板分布支配 |
| S4 | **"从未产红"的成因未被区分** | 是"生成测试太弱"、"执行器未跑起来"，还是"路由过早 done"？当前工件**无法区分**（缺执行细节落盘）。这是最容易修、也最有信息量的缺口 |

---

## 8. Python 专项诊断表

> 证据来源：独立代码审查（直接读码 + 只读命令实测），全部附 `file:line`。

| # | 维度 | 问题 | 证据（file:line） | 严重度 | 修复建议（含可执行命令） |
|---|---|---|---|---|---|
| PY-1 | 类型门禁深度 | `[tool.mypy]` **无任何严格设置**；未注解函数体不检查 | `pyproject.toml:232-234, 256` | 中 | 加 `disallow_untyped_defs` / `check_untyped_defs` / `warn_unused_ignores`；`mypy src/ config.py --disallow-untyped-defs` 当前实测 **10 errors** |
| PY-2 | 类型抑制 | `type: ignore` **43 处**（src/） | `grep -rn "type: ignore" src/` | 低 | 逐簇收窄；启用 `warn_unused_ignores` |
| PY-3 | lint / format | `ruff check .` = 0 错；**但 `ruff format --check .` 报 21 个文件**（= 本次审计临时脚本；`extend-exclude` 未含该目录） | `pyproject.toml:116` | 低 | `extend-exclude` 增 `"audit_2026"`；**并在交付前清理审计临时脚本** |
| PY-4 | CI 门禁真实性 | ruff / mypy / pytest / bandit / pip-audit（顶层+lock）/ gitleaks / 覆盖率 ratchet / 工件校验 / env 预算 / state 契约 / 零断言守卫**均为阻断步骤**，版本钉住 | `.github/workflows/ci.yml:175-178, 305-321, 364-385, 422-429, 460-511` | —（**正面**） | 保持 |
| PY-5 | 依赖钉版 | `requirements.txt` / `requirements.lock` / `pyproject` 三方一致性由 `check_lock_sync.py` 守卫，实测通过（2 条"lock 有而 txt 无"的传递依赖警告） | `requirements.txt:53`、`requirements.lock:130` | 低 | 把 yarl/zstandard 传递依赖写入注释消除警告 |
| PY-6 | 打包 | `dynamic=["version"]` + `[project.scripts] aitester` + `py.typed` 随包分发 | `pyproject.toml:17, 78-84` | — | 无问题（本次未重跑构建） |
| PY-7 | 循环依赖 | `config.py` 顶层仅依赖 dotenv；`src/graph/*` 用函数内延迟 import 断环 | `config.py:20-23`、`agents_cache.py:42-44`、`detection_gates.py:85` | 低 | 可接受（已 ignore PLC0415） |
| PY-8 | 裸 except / 静默吞异常 | 无裸 `except:`（唯一命中为 docstring）；`except Exception` + 紧邻 `pass` **6 处** | `nodes.py:1753-1754`、`runtime_probe.py:395-398` | 低 | 统一 `logger.info` + 计数器便于观测 |
| PY-9 | 测试脆弱性 | 存在以 `inspect.getsource` 锁"接线"的断言（有意防漂移，但锁死重构） | `experiments/run_main_batch.py:396-398` 自述 | 低 | 改为行为断言 |
| PY-10 | **进程泄漏** | `subprocess.run(timeout=...)` **无 `start_new_session` / 进程组 kill** → 超时后 pytest 子进程成为孤儿 | `experiments/_m1_metrics.py:358-372` | **高** | 接入既有 `run_with_timeout`（含 killpg）；实测已遗留 **3 个孤儿进程运行 16.5 小时** |
| PY-11 | 一致性守卫 | `test_tests_and_mypy_are_current` 主动抓出文档漂移（本次实测触发失败） | `tests/`（守卫用例） | —（**正面**） | 保持；落地批次后同步刷新 `BASELINE.yaml` |
| PY-12 | 大数据集文件 | `src/datasets/synthetic_dataset.py` 单文件 2,532 行、模板内嵌测试代码 | 该文件 | 低 | 模板外置为资源文件 |

---

## 9. 领域专项诊断表

| # | 领域 | 独立结论 | 关键证据 | 严重度 |
|---|---|---|---|---|
| DM-1 | 多智能体编排 | **状态机真实存在**：`planner → generator → executor →(diagnosis/cross_file)→ debugger → patch_applier → executor`，条件路由与多终止原因齐备；`MAX_ITERATIONS=3`、`MAX_REGENERATIONS=1`、LangGraph `recursion_limit=4*MAX_ITERATIONS+8`。"多智能体增益"**已被自身数据证否**，代码层无机制可反驳 | `src/graph/workflow.py:126-190, 434-561, 883-914`；`config.py:369-375` | 中（定位问题） |
| DM-2 | 逻辑驱动 | 真实但**受限**：QF 标量约束（z3 Bool/Int/Real）、无量化/数组/关系/时序；`spec_compile_rate ≈ 0.21`；精化闭环未接线；默认关、纯观测 | `src/specs/spec_ir_v2.py:668-719`；`spec_smt.py:14-24`；`spec_refine.py:26-28` | 中 |
| DM-3 | 测试生成 | 闭环完整，防"自指假成功"标记齐备（`test_regenerated_pass_unverified`、`detection_first_status`、红回归门）；但**判别力仅 15.8%（项目口径）/14.0%（本次复算）** | `_m1_metrics.py:473-539`；`nodes.py:1388-1413, 1443-1453` | 高 |
| DM-4 | 自修复 | **不成立**：无运行时自愈组件；补丁写盘 + 失败回滚，目标为临时副本 | `src/graph/patch_io.py:351-504`；`main.py`；`src/cli/app.py` | 高（对外定位） |
| DM-5 | 反馈闭环 | 环路存在但**产出率低**：48.6% 的行从未产红 → 不进修复；无补丁行早退记 0；`abstain` 只观测不阻断 | `_m1_metrics.py:607-609`；`patch_abstain.py:23-29` | 高 |
| DM-6 | 评估/测量诚实度 | 指标定义清晰、**`None` 与 `0` 严格区分**、逐字段剔除；但 ①门与指标判据分叉 ②覆盖率与检出率分母不同构且未点明 ③`four_channel_recompute.py:12` 把 detection 标为"断言失败红"而实际含任何异常红 ④存量工件 provenance 缺关键开关 | `analyze_results.py:717-745`；`detection_gates.py:82-121`；`run_benchmark.py:2674` vs `run_main_batch.py:370-374` | 高（影响归因） |
| DM-7 | 安全 | 输出侧补丁拦截**真实**（正则 + AST 危险 API 差集，默认开）；执行侧**默认无内核/网络隔离**（venv 档）；输入侧注入检测默认关；内核沙箱开启后仍保留"仓库根可写" | `nodes.py:1759-1814`；`executor_modes.py:257-286`；`kernel_sandbox.py:209-211`；`injection_guard.py:51-53` | 高 |
| DM-8 | 沙箱与凭证 | 凭证剔除白名单默认 true 且被三条链路消费；**但仅封环境变量**——`HOME` 在白名单内 → `~/.ssh`、`~/.aws` 文件仍可读（仅内核沙箱档 deny） | `credential_scrub.py:91-111, 211-213`；`executor.py:237-238` | 中 |
| DM-9 | 工程化 | 强（CI 门禁/工件校验/包结构/预注册）；弱点 = mypy 深度 + 临时目录 lint 假红 + 进程泄漏 | 见 §8 | 低-中 |

### 9.1 红队：可能推翻本项目结论的反例与竞争路线

| # | 反例 / 竞争路线 | 依据 | 若成立的影响 |
|---|---|---|---|
| R1 | **"多智能体净负贡献"可能是对照设计放大的**：`plain_llm_df` 不是"纯 LLM"，而是**强制开启检出优先协议**的单臂基线（线程级 override，`run_benchmark.py:412-419`），且没有 aitester 的额外 LLM 调用（`FAULT_LOCALIZER` 默认 true）与更多提示段。缺"**aitester 关协议**"臂 → 协议 × 编排的交互**无法分离** | `run_benchmark.py:238, 414, 423-430` | 现有 −28pp 结论**只能**表述为"完整系统 vs 协议单臂"，**不能**表述为"编排有害" |
| R2 | **"过红 = 非特异断言"已被本次实测推翻**（over_red 混入"根本没跑起来"） | §3.4.3 | `BASELINE.yaml:75-78` 的机制归因须撤回 |
| R3 | **"覆盖率无鉴别力"是条件性的**：项目自己引用的 Zhao/Zhou/Cohen（ISSTA 2026）结论是**限定性**的——回归（无缺陷代码）设定下覆盖+变异可做跨模型比较；缺陷代码设定下不可靠 | `BASELINE.yaml:64` | 项目选择"缺陷代码"场景成立，但**必须在论文中显式声明适用域** |
| R4 | **"逻辑驱动"可被"纯 prompt 契约 + 变异反馈"路线绕过**：当前可执行规约比例 ≈ `compile_rate × expr_coverage` ≈ 0.15–0.16；若竞争路线在同等 token 预算下注入相近数量的约束断言，形式化层的成本收益不成立 | `BASELINE.yaml:70-74` | 项目的 E1 门（≥0.3 / <0.2）即为该反驳的**判定点**——应作为预注册的"杀项目"实验 |
| R5 | **沙箱不足是可被直接利用的 RCE 面**：默认 venv 档下 LLM 生成的测试代码可读写宿主文件、可联网 | §4（T-B）；`executor_modes.py:257-286` | 在多租户 / 外部 PR 场景中不可上线；容器化默认开的竞争路线在安全维度严格占优（代价 ~10 s/任务启动） |
| R6 | **修复闭环可能不收敛**：`MAX_ITERATIONS=3` + `MAX_REGENERATIONS=1` + 字面量 0 可能违反前件（`spec_ir_v2.py:457-458`）→ 注入的 oracle 断言在 buggy/fixed 上**都失败** → 形成"确定性假检出"并消耗修复预算 | `spec_ir_v2.py:457-458`；`_m1_metrics.py:542-574` | 会同时压低 detection 与 repair，且**当前无阻断** |
| R7 | **竞争路线的直接威胁**：同一问题上，**对抗式 mutant 生成 + 测试生成的双方博弈**（AdverTest，ISSTA 2026）已被一手论文验证在真实缺陷上提升 FDR 8.56%，且在 Python（SWE-Rebench）上 11/12 检出 | §4 | 本项目"变异反馈"只做**单向**注入（存活变异体 → prompt），**未做对抗/共演化**；这是最直接的可复制竞争路线 |

---

## 10. 改进 / 优化 / 新增建议表

> 分类：**必须改进（P0）** = 影响结论有效性或对外诚信；**建议优化（P1）** = 影响可发表性/工程效率；**可新增（P2）** = 增强竞争力。
> 每条附：问题 → 一手依据 → 具体做法 → 预期收益 → 成本/风险 → 优先级 → 验证指标 → 时间线 → 工具/命令。

### 10.1 必须改进（P0）

| 编号 | 对应位置 | 问题 | 一手/代码依据 | 建议内容 | 预期收益 | 成本/风险 | 验证指标 | 时间线 | 工具/命令 |
|---|---|---|---|---|---|---|---|---|---|
| **P0-1** | `src/tools/detection_gates.py:82-121` | 特异性门与 M1 判据分叉：收集/导入错误被判 `over_red`；且**不传 `task_metadata`** → 跨文件任务必然误判 | 本次实测复现（rc=2 → `over_red`）；对照 `_m1_metrics.py:58-81, 528-539` | 门委托改为调用 `_run_pytest_in_tmp(..., task_metadata=...)` **并复用 `_looks_like_test_execution_error`**；执行错误 → 新终态 `unavailable_unrunnable`（与 `over_red` 分离） | ① 撤回错误的 −28pp 机制归因；② 跨文件任务判据正确；③ 弃权门/CPR/IDR 负信号去噪 | 低（局部改动 + 单测） | `over_red` 中"unrunnable"占比从混入→显式为 0；跨文件任务 `unavailable` 比例上升 | 1 周 | `pytest tests/test_detection_gates*.py -q`；新增单测覆盖 rc=2 三形态 |
| **P0-2** | `experiments/run_benchmark.py:602-643, 1114-1123` | `patch_plausible` 依赖 `repair_history`，而**该键全库 7,153 行 0 次落盘** → 不可复核；129 行 `correct=1 ∧ plausible=0` 违反不变量 | 本次全库普查 | ① 把 `repair_history`（或至少 `patch_applied` 布尔与 `stop_reason` 组合）落盘到结果行；② 加不变量守卫 `assert correct ⊆ plausible`（fail-closed 到 `None`） | 恢复修复漏斗的可复核性；消除 `patch_precision > 1` | 低 | 全库 `correct ∧ ¬plausible == 0`；`patch_precision ≤ 1` | 1 周 | `python -m experiments.analyze_results --invariant-check` |
| **P0-3** | `README.md:15-56`、`BASELINE.yaml:17-22` | 三处对外表述失真：① "SWE-bench 0/20 负结果如实披露"（实为输入物化失败）② "多智能体手写编排劣势"引 BDAI 5 页短文且省略"单一 25 类系统"限定 ③ `tests.total_passed=5262`/`mypy 120` 已过期 | §3.2、§3.7；T-D 核验 `README.md:15-18` | 逐条改写（可直接采用 §16 的更正文本）；`0/20` 改为"**评测输入物化失败，真实基准结论缺失**" | **诚信与可发表性**（审稿人一击点） | 低（纯文档） | `test_tests_and_mypy_are_current` 与 env 快照守卫回绿 | 3 天 | `pytest tests/ -k "baseline_numbers or env_snapshot" -q` |
| **P0-4** | `experiments/_m1_metrics.py:358-372` | 裸 `subprocess.run(timeout=)` 无进程组 kill → **已遗留 3 个孤儿进程运行 16.5 小时**（100% CPU） | 本次 `ps` 实测 | 接入既有 `run_with_timeout`（含 `start_new_session` + `killpg`）；超时后清理 tmp 目录 | 消除资源泄漏；使耗时/吞吐测量可信 | 低 | 连续 3 次超时用例后 `ps` 无孤儿 | 1 周 | `pytest tests/test_m1_metrics*.py -q`；`ps -eo pid,etime,%cpu,command \| grep aitester_m1` |
| **P0-5** | 统计口径（全库） | **伪重复**：同 seed 缓存重跑被计为独立批次 → logic 档 n 放大 2×（`specificity_gate` 40/66 实为同 seed 的 18/36 双重计数） | 本次实测按 `task_id` 对齐 249–252/261 行逐值相同 | 统计层按 `(seed, 缓存状态)` 去重；报告 n 时输出"**独立运行数**"而非"文件数"；对热缓存批次标注 `replay_of` | 统计独立性恢复；避免无效 n 膨胀 | 低-中 | 所有报表出现"独立运行数"列；差值 ≤ 文件数 | 2 周 | `python -m experiments.statistical_analysis --dedup-runs` |
| **P0-6** | `docs/`、`README.md` 定位段 | "逻辑驱动"在主口径**零实证**、"自修复"在代码层不成立——两个核心标签无证据支撑 | §3.6；K8 | 二选一：(a) 收窄为"**检出优先 + 失败归因**"并删去逻辑/自修复表述；(b) 保留标签但**先补齐实证**（规约 oracle 真正注入并落盘 `spec_oracle_*`） | 消除"标签 > 证据"的审稿风险 | 低（a）/ 中（b） | 对外文档中"logic-driven/self-healing"出现处均有对应 A/B 级指标 | 2 周 | `grep -rn "self-healing\|self-repair\|logic-driven" README*.md docs/*.md` |

### 10.2 建议优化（P1）

| 编号 | 位置 | 问题 | 建议 | 预期收益 | 验证指标 | 时间线 |
|---|---|---|---|---|---|---|
| **P1-1** | `src/graph/workflow.py:734-743` | `_recent_repairs_invalid` 在 `iteration < max` 时直接 `done` → QuixBugs **24/50 任务**被提前掐断，其中 **13 任务最终被 gold 判定修复正确** | 把"连续修复无效"从**终止条件**改为**策略切换条件**（切换候选生成/局部化策略），保留剩余迭代 | 直接回收一个已知的修复损失通道（该批 13/50 = 26% 任务） | A/B：提前终止臂 vs 策略切换臂的 `repair_rate`（all-task 口径） | 3 周 |
| **P1-2** | `config.py:375` | `MAX_REGENERATIONS=1` + `RED_REGRESSION_GATE` 未生效 → "再生成抹红"通道实测 **34/609 行**（red_then_green 且 det=0） | ① 默认开启红回归门（当前默认 false）；② 把 regenerations 预算提到 2–3 并**只允许"更弱"的测试被替换**（单调性约束：新测试集必须保持既有红） | 恢复被抹掉的红证据 | `red_then_green ∧ det=0` 行数 → 0 | 3 周 |
| **P1-3** | `experiments/run_benchmark.py:2674` vs `run_main_batch.py:370-374` | 覆盖率与检出率**分母不同构**且报告未点明 | 报告层强制并列输出两套分母（all-task / measurable）；覆盖率加"仅辅助信号"标注 | 消除"84–94% 覆盖 vs 15.8% 检出"的误读 | 报表含 `denominator` 列 | 1 周 |
| **P1-4** | 成本口径 | `token_usage` 未落盘 in/out 拆分；热缓存行 0-token → 成本比较不公平 | 结果行落盘 `input_tokens`/`output_tokens`/`cache_avoided_tokens`；成本节**同时**输出真实成本与"无缓存理论成本" | 成本比较可用（当前不可用） | 两套成本并列；热缓存行标注 | 2 周 |
| **P1-5** | `experiments/run_benchmark.py:423-430` | 基线注册表**缺"aitester 关检出优先协议"臂** → 协议 × 编排交互不可分离 | 增加第 4 臂 `aitester_no_df`（`DETECTION_FIRST_ENABLE=false`），形成 2×2 | 把"编排有害"降级为可检验假设 | 2×2 方差分析（含交互项） | 3 周 |
| **P1-6** | `src/specs/`（合计 2,140 行） | 表达力受限于 QF 标量；`spec_expr_coverage≈0.72`、`compile_rate≈0.21` → 可执行规约比例 ≈ 0.15 | 提升 DSL 到"数组 + 量化 + 关系"（z3 支持 AUFLIA/AUFNIRA）；先把 `spec_ir_v2.py` 的子句文法扩展为带容器的表达式 | 打开"逻辑驱动"真实通道；E1 门（≥0.3）成为可检验目标 | `spec_compile_rate` ≥ 0.55 且 `spec_oracle_injected` 行数 > 0 | 6–8 周 |
| **P1-7** | `experiments/mutation_testing.py` | 变异反馈是**单向**（存活变异体 → prompt），未做对抗/共演化 | 增加 **mutant 生成 agent**（对测试套件盲区定向生成变异体），与测试生成构成对抗循环 | 对标已验证竞争路线（AdverTest, ISSTA 2026：FDR +8.56%） | 对抗循环 vs 单向反馈的 FDR/mutation score 差值 | 6–8 周 |
| **P1-8** | `docs/citation_allowlist.txt`、`docs/adr/0017` | 引用核验发现 3 处实质错误（Defects4J v3 误判"不存在"、92.82%/26.98% 无法定位、AgentCoder 91.7/92.3 全文 0 命中） | 按 §11/§16 逐条更正；撤销 PSR 勘误（DOI `10.1016/j.infsof.2026.108344`）；补 ICST DOI `10.1109/icst69053.2026.00040` | 引用可核验 | allowlist 条目全部有机读标识符 | 2 周 |
| **P1-9** | 安全默认档 | LLM 生成测试代码默认可写宿主文件、可联网 | 把容器/内核沙箱从 opt-in 改为**实验默认**（至少网络 deny + 只读根 + 独立 tmp 工作区）；移除"仓库根可写" | 消除 RCE 面上线风险 | 沙箱档下"写宿主文件/联网"用例被拒 | 4 周 |

### 10.3 可新增（P2）

| 编号 | 建议 | 依据 | 收益 | 时间线 |
|---|---|---|---|---|
| P2-1 | **引入外部公开基准并接通 M1 口径**：TestGenEval / ULT（TOSEM 2026, DOI 10.1145/3805043）/ ClassEval；把 `instance_code` 物化作为**前置硬门**（缺失即 fail-fast，不再产出"负结果"） | §3.7；`_m1_metrics.py:430-431` | 恢复外部有效性；消除"自生成合成集"单一依赖 | 6–8 周 |
| P2-2 | **新增政策无关的 oracle 质量指标**（本次评审建议，见 §6 路径 A）：对每个生成测试集在固定变异体池上计算"判别率"，与 repair 策略解耦 | §3.4.1（detection 与 repair 数学耦合） | 使"测试生成质量"可独立于修复策略度量 | 4 周 |
| P2-3 | **把"从未产红"作为一等失败模式**并落盘其归因字段（生成侧 / 执行侧 / 路由侧三分） | 296/609 行不可归因 | 把最大单一损失通道变成可优化目标 | 3 周 |
| P2-4 | **接入 concolic/符号执行生成反例输入**（如 CrossHair / hypothesis 策略编译已有雏形），用于把"从未产红"转为"必然产红" | `pyproject.toml` 已含 `[formal]` extras（hypothesis） | 直接攻击第一瓶颈 | 8–12 周 |
| P2-5 | **文档结构化交付**：`report.json` 统一 schema（含 denominator/independent_runs/oracle_type/provenance 完整性位）并由 CI 校验 | §3.9、§3.8 | 让每个对外数字自带口径标签 | 3 周 |

---

## 11. 既有评审结论独立复核表

> 复核对象：`INDEPENDENT_REVIEW_2026-10-10.md`、`REVIEW_2026_FRONTIER.md`、`review_2026/{LEAD_findings,T1..T4,R1..R3,E2..E8,REPORT_draft}.md`（合计 9,654 行）。
> 判定：**支持** = 本次独立复算/核验成立；**推翻** = 本次证据与结论冲突；**无法验证** = 缺工件或环境限制。

| # | 原结论 | 位置 | 本次独立复核方法 | 判定 | 依据 |
|---|---|---|---|---|---|
| C-1 | "多智能体编排净负贡献 δ=−0.279/−0.3673" | `ADR-0016`；`BASELINE.yaml:200-236` | 复算 7 批 × 3 臂 detection（同一判据函数） | **支持（数值）/ 限定（解释）** | aitester 14.0% vs df 48.9%；但缺"aitester 关协议"臂 → 只能称"完整系统 vs 协议单臂"，**不能**称"编排有害"（§9.1 R1） |
| C-2 | "非特异过红（specific_red/over_red≈0.61 vs 1.16）是 −28pp 主机制" | `BASELINE.yaml:75-78` | 4/7 批落盘、450 行 verdict 非 None：`specific_red→det=1` 206/206、`over_red→det=0` 244/244，**真实分歧 0**；另实测门判据分叉（rc=2→over_red） | **推翻** | 门与指标同源，不构成独立证据；真实主因是 48.6% 行从未出现红灯；且 `over_red` 混入"未运行"（§3.4.3） |
| C-3 | "repair 修正口径 39.31%（57/145）" | `README.md:56`、`corrected_report_v2.md` | 独立重放 669 行（200.4 s），逐位一致 | **支持** | §3.5.1；`corrected_report_v2.md` 与独立重跑逐字节相同 |
| C-4 | "QuixBugs repair 92.5%（37/40）" | `BASELINE.yaml`、`LEAD_findings.md` | 逐行复算 + 对照臂结构核查 | **数值支持 / 解释推翻** | 数值 37/40 ✅；但该批 24/50 任务被路由提前终止且其中 13 行仍判正确；df 对照臂 `iterations` 全 0、**结构上无补丁能力** → "92.5% vs 0%" 不可比（§3.5.3-4） |
| C-5 | "SWE-bench Lite 0/20 负结果如实披露" | `README.md:56` | 普查 24 工件/365 行字段完整性 | **推翻** | 365/365 无 `instance_code` 且无 `detection_rate` 键 → 输入物化失败，非负结果（§3.7） |
| C-6 | "四起测量伪影（ADR-0021/0027/0029 等）" | `ADR-0021/0027/0029`；`docs/design/repair_caliber_matrix.md` | 复算伪影机制与修正值 | **支持** | 原始 `repair_rate` 全 0 与修正口径 39.31% 均复现；序列化伪影机制成立；修复已落地在线路径（`_m1_metrics.py:395-410`） |
| C-7 | "第五起疑似测量伪影：`patch_plausible`/`patch_correct` 记账矛盾" | `review_2026/LEAD_findings.md` F2 | 全库普查 + `repair_history` 落盘检查 | **支持并加强** | 冲突行 **129 行**（非仅 13）；根因 = `repair_history` 全库 **0 次落盘**，`patch_plausible` **不可复核**；`patch_precision` 可 >1（1.0648） |
| C-8 | "修复循环在 48% 任务上被提前终止" | `LEAD_findings.md` F3 | 复算 `stop_reason` 分布 + gold 交叉 | **支持** | QuixBugs 24/50（48%）`skip_debugger_repair_invalid`，13 行仍判正确（§3.5.4） |
| C-9 | "`fl_at_k` 谱系定位在真实基准全线 0，LLM 定位 58%" | `LEAD_findings.md` F4 | 未独立复算（本次聚焦 detection/repair） | **无法验证** | 需单独重放该批定位字段 |
| C-10 | "F6：oracle 注入 20/50 与批次内全 0 不一致" | `LEAD_findings.md` F6 | 全库 `oracle_type` 普查（7,153 行） | **支持并加强** | 全库 aitester：`generated_test` 2,015 / 键缺失 1,788，**0 行**增强/规约 oracle（§3.6） |
| C-11 | "E3 四通道：挂起通道很窄（≤3/50）、C3 逻辑通道 `not_available`" | `review_2026/E3_four_channel.md` | 读码 + 字段存在性核查 | **支持** | 7 批工件 `spec_oracle_*` 键不存在；`over_red` 挂起解释被本次独立证否（`over_red` 主因是收集错误） |
| C-12 | "`Defects4J v3` **不存在**" | `R2:67,361,392`；`REVIEW_2026_FRONTIER.md:283,536` | 一手 arXiv 全文核验（`2607.22880v1`） | **推翻（事实性错误）** | 原文逐字："Defects4J v3.0 contains **854** defects across **17** projects"；且与项目自身 E39 条目自相矛盾 |
| C-13 | "'45s vs 50h' 无出处" | `REVIEW_2026_FRONTIER.md`（T3 段） | 核验 IEEE 11655121 摘要 | **推翻（方向相反）** | 该数据在摘要中逐字存在（"in about 45 seconds" / "roughly 50 hours"） |
| C-14 | "引用真实性存疑/疑似幻觉清单" | `docs/citation_allowlist.txt` | 42 DOI + 72 arXiv ID 逐条机读核验 | **部分推翻** | **arXiv 72/72 真实、0 伪造**；DOI 41/42 真实；实际只有 ARC-APR 与"85% MTTR"确无一手来源（项目已正确处置）；真问题是 **3 处事实性错误 + 15 项元数据错配**（§16） |
| C-15 | "覆盖 84–94% 而检出 13–16%，说明覆盖率不具鉴别力" | `BASELINE.yaml:58-64` | 读码核对两指标定义与分母 | **支持（数字）/ 限定（归因）** | 定义差异为主因（`executor.py:198` vs `_m1_metrics.py:529-539`）+ 分母不同构（未点明）；前沿一手来源支持"覆盖近饱和无鉴别力"（§4） |
| C-16 | "`tests.total_passed=5262`、全绿" | `BASELINE.yaml:17-18` | 独立全量跑批 | **推翻（过期）** | 实测 5,311 passed / **2 failed** / 5,317 collected；项目自带守卫已自证（§3.2） |
| C-17 | "第三方复现证明 plain LLM 优于多智能体工具" | `README.md:25-28` | 一手 arXiv 全文核验 | **支持（数值）/ 需补限定** | `49.95/35.33/33.82` 与 `393 类/3,657 方法` 逐字命中；但 README 给出的"提升百分比"（17.72/19.80/20.92）是**相对提升**，与绝对值混排易误读；建议补 ICST DOI（§16） |

---

## 12. 优化后的项目方案与路线图

### 12.1 定位重述（建议对外唯一主张）

> **AITester：面向 LLM 测试生成的"检出优先"测量与失败归因框架。**
> 提供：① 政策无关的 oracle 判别力度量（MDO）；② fail-closed 的三态指标语义（可测 / 不可测 / 零）；③ 完整的 provenance 与工件校验；④ 一组可复现的负结果。
> **明确的非主张**：不是 SOTA 测试生成系统；不是运行时自修复系统；不是形式化验证工具。

### 12.2 推荐目录结构（相对现状的最小改动）

```
src/
  specs/            # 逻辑驱动内核（需扩展表达力：数组/量化/关系）
  measurement/      # 【新增】政策无关度量层
    mdo.py          #   变异判别力（FTR/FDR + 断言-变异体矩阵）
    denominators.py #   口径注册表：all-task / measurable / replayable 三口径唯一定义
    provenance.py   #   运行指纹：git_sha/model/temperature/seed/cache_state/switches
  repair/           # 【从 graph/ 拆出】补丁生成-验证-回滚（现有 patch_io + debugger）
  agents/           # 生成/执行/诊断（保留）
  graph/            # 编排（保留为可消融容器）
experiments/
  results/          # 全部工件入库 + SHA256SUMS（现状已做）
  replay/           # 重放工具（现状已有 repair_replay）
```

### 12.3 依赖管理与工程化（现状已达标，仅列增量）

| 项 | 现状 | 增量建议 |
|---|---|---|
| 依赖钉版 | `requirements.lock` + `check_lock_sync.py` 守卫 | 保持 |
| 类型门禁 | mypy 0 错但**无严格设置** | 加 `disallow_untyped_defs`、`check_untyped_defs`、`warn_unused_ignores`（当前实测 10 处未注解） |
| 测试 | 262 文件 68,379 行；5,317 用例 | 刷新 `BASELINE.yaml`；把 `audit_2026` 类临时目录加入 `extend-exclude` |
| CI/CD | 阻断式门禁（ruff/mypy/pytest/bandit/pip-audit/gitleaks/覆盖率 ratchet/工件校验） | 增"报表口径校验"（每个对外数字必须带 denominator + independent_runs） |
| 打包 | PEP 639 SPDX + `py.typed` + `[formal]` extras | 保持 |

### 12.4 多智能体方案（仅保留有实验价值的编排）

| 组件 | 建议 |
|---|---|
| 角色划分 | 保留 generator / executor / diagnoser；**新增 mutant 生成角色**（对抗循环，对标 F-3） |
| 通信 | 文本 token 通信（现有）；**不建议**引入潜在空间/KV-Cache 通信——无一手证据支持其在**本任务**上的收益 |
| 编排 | 保留为**可消融容器**；新增 `aitester_no_df` 臂以分离"协议 × 编排" |
| 记忆 | 现有 RAG 默认关；建议以"**跨任务变异体池**"作为真正有用的记忆（复用已发现的有效变异体） |
| 预算 | 由 `MAX_ITERATIONS=3` 改为**token 预算自适应**；对齐对照臂预算后比较 |
| 失败恢复 | **单调红保持**（新测试不得抹除既有红）+ 策略切换（替代提前终止） |
| 可观测性 | 现有 trace JSONL + MAST 分布分析；**新增**"从未产红"三分归因字段 |

### 12.5 逻辑驱动方案

| 组件 | 建议 |
|---|---|
| 规格表达 | 从 QF 标量扩展到 **数组 + 量化 + 关系**（z3 AUFLIA/AUFNIRA）；先小步：容器类型 + `ForAll` 于有限域 |
| 约束建模 | 前件（前置条件）→ 可行域采样；后件（后置条件）→ **必须新增"实现是否满足后件"的检查**（当前明确不做） |
| 求解器 | 保留 z3；新增 CrossHair/hypothesis 作为**具体化反例**通道 |
| 覆盖准则 | 以 MDO 的 FTR/FDR 替代结构覆盖作为主目标 |
| 测试最小化 | 基于断言-变异体矩阵做贪心集合覆盖最小化（现有 `test_suite_minimize.py` 可复用） |

### 12.6 自修复方案（**要么改定位，要么真做**）

| 选项 | 内容 | 建议 |
|---|---|---|
| **选项 1（推荐）** | 对外改称"**自动化程序修复（APR）闭环**"，删除"self-healing/自修复"表述 | 成本最低、诚信风险最低 |
| 选项 2 | 真做运行时自修复：新增守护进程 + 故障检测 + 热替换/回滚 + MTTR/latency 指标 + 沙箱 | 成本高（≥3 人月），且与科研主线无关 |
| 无论哪个选项 | 触发条件（测试失败/异常率阈值）、故障定位（现有 `FaultLocalizer`）、补丁生成（现有）、验证（gold + 回归）、回滚（现有 `patch_io.py:458-504`）、**置信度与人工审核**（现有弃权门需从"只观测"升级为"可阻断"） | 必须补齐"**置信度 → 是否自动落地**"的决策表 |

### 12.7 路线图与 KPI

| 阶段 | 时间 | 交付 | KPI（可独立验证） |
|---|---|---|---|
| **T0 止血** | 0–2 周 | P0-1（门判据统一）、P0-2（落盘 + 不变量守卫）、P0-3（文档诚信三改）、P0-4（进程组 kill）、P0-5（独立运行数去重） | 门判据单测覆盖 rc=2；`correct ∧ ¬plausible = 0`；守卫全绿；无孤儿进程；报表含独立运行数 |
| **T1 目标函数** | 1–3 月 | 路径 A（MDO）+ 路径 D（外部基准 + fail-fast 物化门 + 五步协议报表） | ClassEval 上给出 FDR/FTR；至少 2 个公开基准产出非缺失 detection/repair |
| **T2 定向攻坚** | 3–6 月 | 路径 B（单调性 + 策略切换）、路径 C（CEGIR 接线 + DSL 扩展）、P1-7（对抗变异体 agent） | `从未产红` 比例下降 ≥ 50%；QuixBugs all-task 修复 ≥ 85%；对抗 vs 单向的 FDR 差值 |
| **T3 前沿贡献** | 6–12 月 | 公开 artifact + 论文（定位：测试生成的测量与归因） | 第三方复现率 ≥ 80%；≥ 2 个公开基准上的对照结果（**允许为负**） |

---

## 13. 实验、验证与评估计划

### 13.1 预注册要求（在**任何**新数据产生之前固化）

| 项 | 内容 |
|---|---|
| 主终点 | ① 测试生成：**FDR（政策无关口径）**；② 修复：**all-task 修复率**（分母 = 全部任务，含未产红行） |
| 次终点 | detection（F2P 三段）、mutation score（每任务 ≥100 确定性变异体）、$/task（无缓存理论成本）、token/task |
| 判定阈值 | 相对提升 ≥ 10 pp 且 Holm 校正后 **p < 0.05**；等效性判定须用 TOST（非拒绝 ≠ 等效，参考 F-12） |
| 停止规则 | 预先定义无效臂的停止条件（如连续 2 种子上提升 < 2 pp 则停止） |
| 分母注册表 | 三口径（all-task / measurable / replayable）在 `src/measurement/denominators.py` 中唯一定义，报表强制引用 |
| 独立运行数 | 报表必须输出 `independent_runs`（折减同 seed 缓存重跑），并输出 `replay_of` 标记 |

### 13.2 实验矩阵

| 因子 | 水平 | 说明 |
|---|---|---|
| 基准 | 合成集（n=261）/ QuixBugs（50）/ **ClassEval** / ULT 或 TestGenEval（许可允许时）/ SWE-Rebench（防污染） | 至少 2 个公开基准为**硬门** |
| 臂 | `plain_llm` / `plain_llm_df` / `aitester` / `aitester_no_df`（**新增**）/ `aitester+MDO` | 2×2 分离"协议 × 编排" |
| 种子 | {42, 43, 44}，**且 `AITESTER_LLM_CACHE=0`** | 消除缓存重放导致的伪重复 |
| 预算 | 对齐 token（`--per-task-token-caps`，现有开关） | 成本感知比较 |
| 变异体池 | 每任务 ≥100 个确定性算子变异体 | 消除近饱和（当前中位 9 个） |

### 13.3 可复现性要求（当前已具备的 + 需补的）

| 要求 | 现状 | 需补 |
|---|---|---|
| 随机种子固定 | ✅ `provenance.seed` | — |
| 环境快照 | ⚠️ 存量工件 env_snapshot **仅 37 键**，`DETECTION_SPECIFICITY_GATE_ENABLE` / `SPEC_IR_DSL_ENABLE` / `SPEC_ORACLE_EXEC_ENABLE` **缺失** | 补齐键表并回填；缺失即 fail-fast |
| 工件校验 | ✅ `SHA256SUMS` + `check_artifacts_tracked` 守卫 | — |
| 缓存状态落盘 | ⚠️ 未落盘 | 结果行增 `cache_state` / `cache_avoided_tokens` |
| 一键复现 | ✅ `reproduce.sh` / `Makefile` | 增 `make verify-claims`（逐条复算 README 数字） |
| 第三方可复现 | ⚠️ 未验证 | 交付 artifact + 独立复现报告 |

### 13.4 统计与呈现规范（对标 F-12 五步协议）

1. **共享结果画像**：报告各臂**共同成功/共同失败**的实例数（而非仅聚合率）。
2. **配对检验**：同任务配对 McNemar；相邻臂做精确检验。
3. **分组敏感性**：按模板/仓库/难度分组，报**组内方向一致性**。
4. **分辨率实例预算**：计算"要区分本方案与基线需要多少实例"（当前 87 任务/批 likely 不足）。
5. **model-scaffold provenance**：报告"模型 × 脚手架"组合，而非仅模型名。

---

## 14. 风险、伦理与合规

### 14.1 风险登记册

| # | 类别 | 风险 | 概率 | 影响 | 缓解（Plan B） |
|---|---|---|---|---|---|
| RK-1 | 技术 | 路径 A（MDO）与现有 detection 高度相关 → 无信息增益 | 中 | 高 | 先做**相关性预实验**（MDO vs detection 的 Spearman）；若 ρ > 0.9 则改攻路径 C |
| RK-2 | 技术 | 路径 C 依赖 DSL 扩展，工期不可控 | 高 | 中 | **Plan B**：不做 DSL 扩展，直接用 CrossHair/hypothesis 生成反例输入（绕过规约） |
| RK-3 | 数据 | 合成集 29 模板导致聚类效应，`n_eff` 仅 39.9 | **已发生** | 高 | 引入公开基准（路径 D）；报表强制报 `n_eff` |
| RK-4 | 复现性 | 缓存重放导致伪重复（已发生） | **已发生** | 中 | `AITESTER_LLM_CACHE=0`；报表输出 `independent_runs` |
| RK-5 | 成本 | 引入公开基准 + 关闭缓存 → token 成本上升数倍 | 高 | 中 | 预算匹配设计；优先小规模基准（ClassEval） |
| RK-6 | 安全 | 默认档下 LLM 生成代码可写宿主文件/联网（RCE 面） | 中 | **高** | P1-9：默认容器/内核沙箱 + 网络 deny；不上线多租户 |
| RK-7 | 安全 | `.env.local` / `.private/.env.local` 含**本地明文 API Key**（已 gitignore） | 低 | 中 | 迁移到 OS keyring / 环境注入；`gitleaks` 已接入 CI |
| RK-8 | 合规 | SWE-bench 提交需"学术机构 + 开源 + 同行评审论文"（2025-11-18 起） | **确定性限制** | 中 | 短期内不追求榜单提交；以公开 artifact + 论文为目标 |
| RK-9 | 伦理 | 自动修复直接落地存在"错误修复"风险（当前 `false_fix` 率 **63.9%（389/609）**） | **已发生** | 高 | 弃权门从"只观测"升级为"可阻断"；**默认不自动落地**；人工审核决策表 |
| RK-10 | 学术诚信 | 文档漂移与归因错误（本次查出 3 处事实性错误 + 1 处机制归因推翻） | **已发生** | 中 | P0-3 修订；把"引用核验 + 数字口径校验"接入 CI |
| RK-11 | 资源 | 孤儿进程持续占用 CPU（已发生 16.5 h） | **已发生** | 低-中 | P0-4 进程组 kill |
| RK-12 | 项目存续 | 核心正面主张（多智能体/逻辑驱动/自修复）在两个维度上无证据支撑 | **已发生** | 高 | 定位重构（§12.1）或补齐实证（§12.5/12.6） |

### 14.2 伦理与合规审查（判定）

| 项 | 判定 | 依据 |
|---|---|---|
| 人类受试者 | **不涉及** | 无用户研究 |
| 隐私 / 个人数据 | **不涉及**（代码与公开基准） | QuixBugs MIT、SWE-bench 公开 |
| 许可证 | ✅ QuixBugs MIT 已核实；⚠️ **BugsInPy 无 SPDX**、**TestGenEval CC BY-NC 4.0（非商用）** | 项目已登记为"三选一门槛"；**若论文允许商用须避开 NC 数据** |
| 代码执行安全 | ⚠️ **不满足"安全沙箱"要求** | 默认档无文件系统/网络隔离（§8 DM-7） |
| secrets 管理 | ✅ 无密钥入库；本地明文 Key 已 gitignore | 建议迁移 keyring |
| 自动化决策风险 | ⚠️ `false_fix` 63.9% → **不得默认自动落地补丁** | §3.3 |
| 双层用途 | 无 | 不涉及武器/监控 |

---

## 15. 待澄清问题（不以假设填充）

> 按独立评审纪律：**缺失信息必须列为待澄清问题**。以下问题会实质影响结论，但本次无法从工件或一手来源判定。

| # | 问题 | 为何重要 | 需要谁回答 / 什么材料 |
|---|---|---|---|
| Q1 | **296 行"从未产红"的成因**：是生成测试本身太弱，还是执行器（import/收集）根本没跑起来，还是路由过早 `done`？ | 决定路径 A 还是路径 C 优先；当前工件**缺执行细节**（无 `rc_buggy`/`rc_fixed` 落盘） | 项目方补落盘后即可自答（≤1 人日） |
| Q2 | **`patch_plausible` 的真实定义与历史值** | `repair_history` 全库 0 次落盘 → 该字段**不可复核**，漏斗叙事（94% → 46.8% → 39.31%）中间段失真 | 项目方：为何未落盘？是否可从 trace JSONL 重建？ |
| Q3 | **R-P0-2 三种子的"独立运行数"** | 若种子 42/44 的第二次运行是缓存重放，pooled n=261 需折减 | 项目方：提供每批 `cache_hits` / 是否冷缓存 |
| Q4 | **QuixBugs 24 行提前终止的 13 行"gold 判定正确"是否可信** | 该数字决定路径 B 的收益上界（26% 任务可回收） | 项目方：该 13 行的 `patch` 与 gold 对比逐行复核（`repair_review_worksheet.py` 已生成素材） |
| Q5 | **目标受众与发表计划** | 决定是走"测量方法学"还是"系统论文"路线（两者实验要求不同） | **用户**：目标 venue（ICSE/FSE/ISSTA/TOSEM？）与时间线 |
| Q6 | **是否允许联网与使用外部 LLM API 做大规模复现** | 关闭缓存 + 3 种子 + 4 臂 + 2 公开基准的预算规模需确认 | **用户**：预算上限（当前 aitester 约 13.4k tokens/task） |
| Q7 | **"自修复"定位是否保留** | 影响全部对外文档与实验设计 | **用户**：选 §12.6 选项 1（改称 APR）还是选项 2（真做运行时自愈） |
| Q8 | **BugsInPy / TestGenEval（CC BY-NC）是否可用于目标场景** | 若面向商业或工业合作，NC 数据不可用 | **用户**：使用场景是否含商用 |
| Q9 | **覆盖率数字能否重跑验证** | 89%/83% 目前为 E 级（无法验证） | 项目方：`pytest --cov=src --cov-branch` 全量重跑并归档 |
| Q10 | **是否存在未入库的历史批次**（如"历史 guards 10/10"） | 影响 §3.11 的"无法验证"清单能否收窄 | 项目方：提供入库清单或声明不存在 |

---

## 16. 参考来源（区分一手/二手，标注证据等级）

### 16.1 一手来源（本次评审实际打开核验）

| # | 来源 | 用途 | 等级 |
|---|---|---|---|
| [1] | Hamidi, A., Konstantinou, M., Degiovanni, R., Papadakis, M. *How effective are traditional test criteria at detecting bugs in large language models generated code?* [arXiv:2609.09315](https://arxiv.org/abs/2609.09315)（2026-09-08） | 覆盖触发 32.9/38.9/32.2%、检出 1–2%、oracle 提升 6.6%、6,066 挑战故障 | **A** |
| [2] | Al-Ahmad, B., Harshvardhan, M., El-Fakih, K., AlSobeh, A. *Evaluating the effectiveness of class-level LLM-generated test suites in Python.* [arXiv:2609.24341](https://arxiv.org/abs/2609.24341)（2026-09-21） | ClassEval；覆盖近饱和无鉴别力；模型 > 提示 | **A** |
| [3] | Chang, P., Fang, Y., Chen, S., Shi, Y., Shen, B., Gu, X. *Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation.* [arXiv:2602.08146](https://arxiv.org/abs/2602.08146)；DOI [10.1145/3832122](https://doi.org/10.1145/3832122)；**ISSTA 2026** | AdverTest：FDR +8.56% vs 最强 LLM 基线；Python 11/12 | **A** |
| [4] | Konstantinou, M., Degiovanni, R., Papadakis, M. *How well LLM-based test generation techniques perform with newer LLM versions?* [arXiv:2601.09695](https://arxiv.org/abs/2601.09695)；DOI [10.1109/icst69053.2026.00040](https://doi.org/10.1109/icst69053.2026.00040)；**ICST 2026** | plain LLM 49.95/35.33/33.82；相对 +17.72/19.80/20.92%；393 类/3,657 方法 | **A** |
| [5] | Liu, F., Liu, Y., Sun, R., Luo, L., Guo, S. *Coding Agents Have Converged: Why the SWE-bench Leaderboard Can No Longer Order Its Top Entries…* [arXiv:2609.17394](https://arxiv.org/abs/2609.17394)；**ADMA 2026** | Verified 榜首并列 396/500；相邻 top-30 McNemar 0/29 显著；scaffold 极差 29.8 pp | **A** |
| [6] | `github.com/swe-bench/experiments` 官方逐条结果文件（`metadata.yaml` / `results/results.json`） | Verified / Lite 全部榜单数值与提交规则（2025-11-18 变更） | **A** |
| [7] | Xu, Q., Wang, G., Briand, L., Liu, K. *Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation.* DOI [10.1145/3803418](https://doi.org/10.1145/3803418)（**TOSEM 2026**，2026-03-25）；[arXiv:2506.02943](https://arxiv.org/abs/2506.02943) | CANDOR：0.991/0.970/0.980（HumanEvalJava） | **A**（我方独立 Crossref 核验） |
| [8] | Radaideh, M., Corriveau, J.-P., Shi, W. *Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation…* IEEE Xplore **11655121**；DOI [10.1109/bdai70753.2026.11655121](https://doi.org/10.1109/bdai70753.2026.11655121)；**BDAI 2026**, pp.128-132 | 88.35/35.92、69.90/45.63；人类基线 83.98%；45 s vs 50 h；**单一 25 类系统** | **A**（数值）/ 范围受限 |
| [9] | TestAgent（DOI [10.1145/3803437.3806428](https://doi.org/10.1145/3803437.3806428)，**FSE Companion 2026**；[arXiv:2607.09101](https://arxiv.org/abs/2607.09101)） | 97.46/92.34/90.24/83.69 | **A** |
| [10] | Huang, D., Zhang, J. M., Harman, M., et al. *Benchmarking LLMs for Unit Test Generation from Real-World Functions（ULT）.* DOI [10.1145/3805043](https://doi.org/10.1145/3805043)（TOSEM 2026）；[arXiv:2508.00408](https://arxiv.org/abs/2508.00408) | 3,909 任务；41.32/45.10/30.22/40.21 | **A** |
| [11] | Zhao, J., Zhou, S., Cohen, E. *Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness?* DOI [10.1145/3832093](https://doi.org/10.1145/3832093)（**ISSTA 2026**）；[arXiv:2607.22880](https://arxiv.org/abs/2607.22880) | r=0.780；>100,000 测试；**并证明 Defects4J v3.0 存在（854/17）** | **A** |
| [12] | Wang, G., Xu, Q., Briand, L., Liu, K. *Mutation-Guided Unit Test Generation With a Large Language Model（MutGen）.* DOI [10.1109/tse.2026.3682975](https://doi.org/10.1109/tse.2026.3682975)（TSE 2026） | 204 subjects | **A** |
| [13] | Luo 等. *Unlocking LLM Repair Capabilities Through Cross-Language Translation and Multi-Agent Refinement（LANTERN）.* DOI [10.1145/3744916.3773227](https://doi.org/10.1145/3744916.3773227)（**ICSE 2026**） | Rust Pass@10 +22.09%；p=0.0126；δ=0.64 | **A** |
| [14] | Huang 等. *TraceCoder: A Trace-Driven Multi-Agent Framework for Automated Debugging of LLM-Generated Code.* DOI [10.1145/3744916.3773187](https://doi.org/10.1145/3744916.3773187)（**ICSE 2026**） | Pass@1 相对 +34.43%；迭代上限 5 | **A** |
| [15] | Bouras, D. S., Mechtaev, S. *Gordian.* DOI [10.1145/3832126](https://doi.org/10.1145/3832126)（PACMSE Vol.3 ISSTA, pp.802-823） | 覆盖 +28.5–115.2% vs 传统符号执行；token −91–96% | **A** |
| [16] | Chang 等. *Pattern Synergistic Repair（PSR）.* DOI [10.1016/j.infsof.2026.108344](https://doi.org/10.1016/j.infsof.2026.108344) | 撤销项目"未能定位"勘误 | **C**（仅元数据） |
| [17] | AgentRepair. DOI [10.1109/dsa66321.2025.00025](https://doi.org/10.1109/dsa66321.2025.00025)（IEEE DSA 2025） | 确认存在（付费墙，指标不可得） | **B** |
| [18] | Ju, X. 等. *FedDualFix.* DOI [10.1016/j.asoc.2026.115898](https://doi.org/10.1016/j.asoc.2026.115898)（ASOC 2026） | 存在；数值未独立核实 | **B** |
| [19] | CoverUp（FSE 2025）DOI [10.1145/3729398](https://doi.org/10.1145/3729398)；[arXiv:2403.16218](https://arxiv.org/abs/2403.16218) | per-module median line+branch 80% vs CodaMosa 47% | **B** |
| [20] | TestGenEval [arXiv:2410.00752](https://arxiv.org/abs/2410.00752)；TestForge [arXiv:2503.14713](https://arxiv.org/abs/2503.14713) | 最佳模型平均覆盖 35.2%；pass@1 84.3%/覆盖 44.4%/变异 33.8% | **B** |
| [21] | AssertFlip [arXiv:2507.17542](https://arxiv.org/abs/2507.17542) | SWT-Bench Verified fail-to-pass 43.6% | **B** |
| [22] | SWE-Proof / Benchproofer [arXiv:2609.21190](https://arxiv.org/abs/2609.21190) | 1/4 通过测试的补丁存在反例；56% 规格通过审计 | **B** |
| [23] | SpecGen [arXiv:2401.08807](https://arxiv.org/abs/2401.08807) | 279/385 可验证规约 | **B** |
| [24] | nl2postcond [arXiv:2310.01831](https://arxiv.org/abs/2310.01831)（FSE 2024） | 捕获 64 个 Defects4J 真实 bug | **B** |
| [25] | ImpossibleBench [arXiv:2510.20270](https://arxiv.org/abs/2510.20270) | 规格-测试冲突下的 cheating 检测框架 | **B** |

### 16.2 项目内材料（作为"待验证声明"引用，非事实来源）

`README.md` / `README.en.md` / `BASELINE.yaml` / `CHANGELOG.md` / `MODEL_CARD.md` / `INDEPENDENT_REVIEW_2026-10-10.md` / `REVIEW_2026_FRONTIER.md` / `review_2026/*.md`（13 份）/ `docs/design/repair_caliber_matrix.md` / `docs/adr/*`（29 份）/ `docs/preregistration*.md` / `experiments/results/**`。

### 16.3 二手来源（本次**未**用于支撑任何结论）

- 第三方榜单聚合页、博客、搜索片段（如 `benchlm.ai`、`codesota.com`、`tembo.io`）：**仅用于定位一手来源**，其数值一律不采用。
- 项目文档中所有前沿转述（CANDOR / TestAgent / BOAD 等）：**一律回到一手来源重新核验后方可使用**。

### 16.4 共识 / 争议 / 假设 / 推测（分类声明）

| 类别 | 内容 |
|---|---|
| **共识**（多篇独立一手一致） | ① 结构覆盖对 LLM 生成测试**鉴别力极低**（[1][2]）；② **oracle（断言）而非触发是主要瓶颈**（[1]）；③ 更强 LLM 会削弱复杂编排/工具的边际收益（[4][2]）；④ SWE-bench 榜单边际**不可排序**（[5]） |
| **争议**（一手来源相互冲突，须并列） | ① **多智能体是否优于单提示**：[3][7][9] 报告多智能体高覆盖/高检出；[4][8] 报告单提示占优（[8] 仅在单一 25 类系统上）。**本项目数据站在 [4][8] 一侧**；② 变异测试相对结构覆盖的增益：传统共识为"显著更强"，[1] 报告对 LLM 故障仅"边际"且成本收益存疑 |
| **假设**（项目持有，未被证实也未被否证） | "逻辑驱动（规约 oracle）能提升检出"——**主口径零实证**（§3.6） |
| **推测**（本报告标注 E 级） | §6 四条路径的**全部预期提升数值**；以及"求解器定向反例 + 触发/判别严格分工"这一组合在文献中未见对应的判断 |

---

## 17. 本次独立评审的可审计工件与复现指引

| 工件 | 内容 | 行数/规模 |
|---|---|---|
| `FINAL_REVIEW_2026-10-11.md` | 本报告 | 见文件 |
| `audit_2026/T_A_claims_traceability.md` | 90 条项目声明逐条溯源复核（A 43 / B 11 / C 12 / D 7 / E 17） | 424 行 |
| `audit_2026/T_B_code_domain_audit.md` | Python 与领域机制独立代码审查（13 条声称 vs 实现、安全、红队） | 366 行 |
| `audit_2026/T_C_frontier_primary_sources.md` | 2025–2026 前沿基线一手重建（5 张分表 + 12 项交叉验证） | 311 行 |
| `audit_2026/T_D_citation_verification.md` | 42 DOI + 72 arXiv ID 真实性核验 + 15 项元数据错配 | 482 行 |
| `audit_2026/T_E_adversarial_verification.md` | 对抗式验证记录（独立复算本报告关键数字） | 见文件 |
| `audit_2026/lead_replay_seed_a.md` | Lead 独立重放验证（54 可重放行 → 20 correct，0.3704） | 14 行 |
| `audit_2026/a*.py`（19 个） | 审计临时脚本（被 T_A 报告引用，供复算） | — |

**核心复算命令（零 LLM）**：

```bash
cd /Users/wangchenyu/Workspace/AITester
# 1) 三臂 detection/repair 复算
.venv/bin/python - <<'PY'
import json,glob
for f in sorted(glob.glob("experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json")):
    for arm,v in json.load(open(f))["results"].items():
        d=v["details"]
        print(f, arm, "det=",sum(1 for x in d if x.get("detection_rate")==1.0),
              "meas=",sum(1 for x in d if x.get("detection_rate") is not None))
PY
# 2) repair 修正口径重放（约 200 s）
.venv/bin/python -m experiments.repair_replay experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester
# 3) 真实仓库基准字段普查
.venv/bin/python audit_2026/a24_swe_census.py
# 4) 全量测试（当前实测 5,311 passed / 2 failed）
.venv/bin/python -m pytest tests/ -q --basetemp=/tmp/at_$(date +%s)
```

### 17.1 对抗式验证与勘误记录（v1.1，2026-10-11 修订）

本报告在首版完成后经过**独立对抗式验证**（`audit_2026/T_E_adversarial_verification.md`，584 行，零 LLM、只读、附带实跑脚本与输出）。验证结论：**15 项核心数字中 12 项逐位一致；3 项为对齐方式/口径/scope 问题，已全部更正；并另发现 7 项表述级问题，亦已更正。**

| 勘误号 | 位置 | 首版表述 | 实测更正 | 性质 |
|---|---|---|---|---|
| **S1** | §0.2 A6、§3.8、§7 G6、§10 P0-5 | 伪重复 143/261、140/261 | **252/261、249/261**（须按 `task_id` 对齐；两批任务顺序不同，按行序对齐**低估约 10 pp**） | **数据错误** |
| **S2** | §0.2 K2、§2.2 A2、§3.4.3、§11 C-2 | "全量交叉表…例外仅 2 行" | 门仅 **4/7 批**落盘（1,044 行有键、**450 行** verdict 非 None）；`specific_red→det=1` 206/206、`over_red→det=0` 244/244，**真实分歧 = 0**；那 2–3 行是"**门未运行**"，不是例外 | **表述错误** |
| **S3** | §0.2 K8、§2.1、§3.6、§11 C-10 | "全库 1,803/1,672" | 全库（7,153 行）aitester 为 **2,015 / 键缺失 1,788**（键存在且为 None = 0）；全臂 3,968/3,185；1,803/1,672 只是 `benchmark_*.json` 子集 | **scope 错误** |
| **S4** | §3.7 | `error_category` = syntax(19)/pvf(18)/etm(20) | 365 行普查为 **pvf 148 / 空 125 / etm 59 / syntax 28**；19/18/20 是**单个 60 行工件**的分布。另发现 **3 行** `source='examples'` 混入 `swe_bench` 293 行 | **scope 错误 + 新发现** |
| **S5** | §3.4.2 | 反事实分解未声明次序 | 补声明：上表为 **aitester-基准序贯分解**；**df-基准**为 **73.9%/55.8%/−29.7%** → 主效应随次序变化，**只能读作"两因子都大"** | **口径补充** |
| **S6** | §3.8 | `AITESTER_LLM_CACHE_NAMESPACE` | 正确变量名为 **`AITESTER_CACHE_NAMESPACE`**（`base_agent.py:388`、`run_benchmark.py:2431-2432`） | 事实错误 |
| **S7** | §3.5.1 | "可测 556/571" | 补 plain_llm 609 个零值 → 三臂零值合计 **1,736**（None 53/38/0） | 遗漏 |
| **S8** | §3.7 | 293 行全为 swe_bench | 其中 **3 行** `task_metadata.source='examples'` | 口径瑕疵 |
| **S9** | §0.4、§5 | 修复维度标"不可比"却给"落后"，并与 SWE-bench 79.2% 作数量级并置 | 统一为"**不可比；不计算差距**"，仅在"与自身基线比较"层面陈述；删除数量级并置 | **内部矛盾** |
| **S10** | §0.2 K1、§3.4.1 | "从未产生任何 assert 失败"（偏窄） | 改词为"**从未出现任何一次非零退出（红灯）**"，并补证：296 行**每行 assert ≥3 条**（均值 15.3、max 45）、`test_error_rate` 全 0 → **不是没写断言，而是断言全部通过**（表述因此**更强**） | **措辞更正（结论增强）** |

> **本报告的自查纪律**：首版曾在写作过程中就地修正 1 处自身算错（"产红率贡献 88%"→ 序贯分解 44.2%/26.1%/29.7%，§3.4.2 留有更正注记）；上述 10 项为**第二次**、由独立验证者发现的更正。**两次更正的完整过程均保留在附录 E。**
> **残余不确定性**：对抗式验证者未能独立复核 R-old 版本哈希（就地覆盖）、§3.5.1 重放链（需跑 `repair_replay`）、成本与孤儿进程等环境项——这些项在 §3.11 已列为"无法验证"。

### 17.2 P0 救火与实证进展（2026-10-11 后续会话）

> 本节记录 §10 建议表的**落地情况**与**由落地实测产生的结论更新**。详细工件见 `OPTIMIZATION_PLAN_v2.md` 附录 G/H。

**已落地并验证（全部为本次会话运行）**

| 项 | 内容 | 验证证据 |
|---|---|---|
| P0-4 进程泄漏 | M1 判分与解释器探测改用 `run_with_timeout`（进程组 + killpg + 文件后端） | 隔离复现：3.1s 返回、0 孤儿。**真实批次中触发 14 次超时、孤儿始终为 0**（修复前同场景产生 3 个 16.5 小时孤儿） |
| P0-2 记账不可复核 | `repair_history` 落盘 + `patch_plausible_evidence` + 不变量守卫 | 真实批次 aitester **10/10 行落盘**；守卫**真实捕获 2 行** `correct ∧ ¬plausible` |
| P0-2 根因修复（新） | `patch_plausible` 由"末条"改为"**任一**迭代写盘成功" | 逐行证据显示末条被证据门拒绝但早期已写盘 → 原口径**假阴性**；修正后不变量结构上成立 |
| P0-3 环境开关 | 补登记 3 个漏配开关 | env 快照门禁 **78/78、exit 0**（同类缺口第 4 次复发） |
| P0-3 文档漂移 | 刷新 BASELINE 过期数字 | `total_passed` 5262→**5358**；`mypy_source_files` 120→**123**；两条 known-red 转绿 |
| 存量清理 | 3 个孤儿进程（17.1 小时） | `ps` 残留 0 |

**新增能力**

- `src/measurement/mdo.py`：政策无关度量层（**MTR** 触发率 / **MDR** 判别率 / **CRASH** 崩溃率；行为探针判据，非退出码）
- `experiments/mdo_posthoc.py`：**批后离线** MDO 工具（并行 8 路；不拖慢跑批、池规模可独立调参）
- `experiments/mutation_testing.py`：`ExtendedMutationGenerator`（+6 类算子，**基类口径逐字节未改**）
- 回归测试：`tests/test_p0_hardening_2026_10_11.py`（15 例）、`tests/test_mdo_metrics.py`（30 例）

**首份真实基准 MDO 数据（LLM 实测，QuixBugs n=10/臂，缓存关闭）——本报告 §3.4 的结论因此需要限定**

| 数据集 | 观察 | MDO 定位 |
|---|---|---|
| 合成集（n=609） | 覆盖率 97.6% 但 48.6% 行从未出现红灯 | 表面为 **oracle 缺口** |
| **真实 QuixBugs（本批）** | 池级触发率 **24.8%**，触发即判别（oracle 缺口 **0**） | **触发缺口 75.2%** |

> **诚实的限定**：§3.4 关于"48.6% 从未出现红灯"的结论基于**合成集**；首份真实基准数据指向**不同的瓶颈（触发而非判别）**。两者都只有单数据集证据，**"瓶颈依数据集而异"目前是假设而非结论**，证伪条件见 `OPTIMIZATION_PLAN_v2.md` §H.5。
> 同时：本批可测行仅 5–6/臂、池中位 8–11（未达下限 29）→ **只能作方向性判断**。

### 17.3 完整真实基准实测结果（2026-10-11，QuixBugs 50 任务 × 2 臂）

> 用真实 LLM（`deepseek-flash`、**缓存关闭**）跑完 QuixBugs 全 50 任务 × 2 臂，并做批后离线 MDO。工件：`experiments/results/pilot_mdo_full50/`。这是本报告 §10 建议表的**首个完整实证闭环**。

**核心指标**

| 项 | aitester | plain_llm_df |
|---|---|---|
| detection（可测口径） | 24/37 = **64.9%** | 27/36 = **75.0%** |
| repair（**修正后**） | 28/41 = **68.3%** | 0/41（结构上无补丁能力，不可比） |
| repair（修正前） | 36/41 = 87.8% | 0/41 |
| 覆盖率均值 | 72.3% | 67.6% |
| token | 583,949（244 调用） | 92,334（54 调用） |
| token 比 | **6.32×** | 1× |

**MDO 首份完整结果（58 行可测 / 583 个变异体，池级）**

| 指标 | 值 | 95% Wilson CI |
|---|---|---|
| **MTR（触发率）** | **0.679** | [0.640, 0.716] |
| **MDR（判别率）** | **0.654** | [0.614, 0.691] |
| **oracle 缺口（1−MDR/MTR）** | **0.038** | [0.023, 0.062] |

**三条结论（含对本报告 §3.4 的进一步限定）**

1. **真实基准上 oracle 不是主要瓶颈**：一旦触发行为偏差，**96.2%** 能被断言判别。**触发缺口（32.1%）与 oracle 缺口（3.8%）之比约 8.5:1**。
2. **"瓶颈在 oracle"是合成集特有现象**——合成集显示 48.6% 的行从未出现红灯（表面 oracle 失效），真实基准却不是。**两个数据集给出不同瓶颈**，此前基于单数据集的普遍化表述不成立。
3. **覆盖率与 oracle 缺口正相关（新观察）**：覆盖率 ≥95% 组 oracle 缺口 **1.8%**（n=42），<95% 组 **8.8%**（n=12）——约 5 倍差。样本小，属可检验假设。

**由实测发现的第二起测量伪影（已修复）**

8/50 行（**16%**）出现 `repair_rate=1.0` 但 `repair_history` 的 `patch_applied` **全为 False**（补丁从未写盘、`source_patched_unverified=True`）。根因：R28 只堵住"空补丁"，**非空但未写盘**时 `_target_code_after_patch` 返回的仍是缺陷原码，而 QuixBugs 有 8 个程序的缺陷原码**恰好能过官方 gold 测试** → gold 裁决通过 → 纯假阳性。已加"补丁必须真的落地"守卫。

> **量化影响**：aitester 的 QuixBugs 修复率由 **87.8% 降至 68.3%（虚高 19.5 pp）**。项目对外引用的该基准修复率（曾报 90.2% / 92.5%）**含此系统性虚高**，需按修正口径重算。

**对抗式变异搜索（P0-1）验证**

- **机制侧已验证**（零 LLM，真实 gold 代码）：对弱测试定向找到 **3 个真实盲区**，并正确拒绝等价变异体；三重过滤全部生效。
- **测试生成侧暴露真实缺陷**（真实 LLM，3 任务，全部无法度量）：`bitcount` 上 LLM 写 `assert bitcount(-1)==0` 导致**无限循环**（该函数在 Python 负数上永不终止——**gold 实现自身属性**）；`flatten` 收集错误；`get_factors` 断言了错误的期望值。**MDO 的 fail-closed 如实挡住这三条，而非给出假的判别力分数。**

### 17.4 路径 C 落地与"零检出修复"因果证据（2026-10-11）

> 承接 §17.3：真实基准的**触发缺口 32.1% 能否补上？** 实测答案是能，但**真正的第一瓶颈不是"输入选得不好"**。

**实验**（零 LLM，可复算）：对象 = 该批 `aitester` 的 **13 行 `detection_rate = 0.0`**；判据 = detection 是否由 0.0 翻转为 1.0。

| 干预 | 翻转 | 比例 |
|---|---|---|
| 仅注入路径 C 的机械触发见证 | **0 / 13** | 0% |
| **GCP 剪枝**（剔除在 gold 上失败的测试块） | **9 / 13** | **69%** |
| **GCP + 见证安全门（统一管线）** | **12 / 13** | **92%** |

**归因（关键）**：13 行中 9 行的根因是 **LLM 写了在正确实现上就失败的测试块**。示例——`is_valid_parenthesization` 的生成测试含 `("(((", True)`、`("(()", True)`：缺陷版恰好返回 `True` 所以"通过"，而**正确版返回 `False`** → 这些断言在 gold 上失败 → 压住 M1 的 F2P 第二段（要求 gold 绿）→ 整行检出归零。

> 即：项目此前把零检出归因为"不产生红"（合成集）或"触发不足"（真实基准），但**真实基准上最直接的损失是"LLM 的期望值本身不可信"**。

**两条必需的守卫（缺一即反噬）**

1. **见证安全门**：每条见证断言必须**先在纯净 gold 上通过**才允许注入。`minimum_spanning_tree` 的 **24 条候选全部被拒**——若无此门，注入会把该行 detection 从 **1.0 打回 0.0**（实测发生）。
2. **行为归一化**：首版见证搜索在 `flatten` 上产出 **57/57 假见证**——两版都返回 **generator**，其 `repr` 含内存地址，直接比较必然"不同"。归一化（generator→list、dict 键排序、地址替换）后转为真实见证。

> 这是本次评审第 **3** 起"比较了错误的东西"类伪影（前两起：`patch_plausible` 只看末条、MDO 把挂死算作未判别）。**共同模式：判据对象选错。**

**新增模块（零 LLM、fail-closed）**：`gold_consistency_pruning.py`（GCP，全部块失败时不产空套件）、`solver_directed_trigger.py`（名称启发式 + hypothesis + 行为差分）、`suite_repair_pipeline.py`（三段管线 + 终检）；回归守卫 `tests/test_path_c_trigger.py`（14 例）。

### 17.5 管线全批干预、安全检验与无 gold 变体的否定结果（2026-10-11）

**① 反向安全检验（决定能否默认开启）**：对两臂全部 **detection = 1.0** 的 51 行跑 SRP 管线 → **保持检出 51、被改坏 0（安全率 100%）**。机制解释：管线两步都受约束——GCP 只**删除**在基准上失败的块，见证注入**必须过安全门**，结构上难以引入新失败。

**② 全批干预模拟（配对设计）**

| 臂 | 0→0 / **0→1** / **1→0** / 1→1 | 干预前 | 干预后 | **McNemar 精确 p** |
|---|---|---|---|---|
| `aitester` | 1 / **12** / **0** / 24 | 64.9% | **97.3%** | **0.00049** |
| `plain_llm_df` | 2 / **7** / **0** / 27 | 75.0% | **94.4%** | **0.0156** |

**③ ⚠️ 决定性限定：该管线使用了 gold 实现**（GCP 用 gold 判块、见证用 buggy-vs-gold 差分）。**真实部署没有 gold**，因此 97.3%/94.4% **不是可部署方法性能**，而是：① **损失归因的诊断工具**（证明 64.9%→97.3% 的差距全部来自可自动修复的缺陷，而非模型能力上限）；② **oracle 上限估计**；③ **不得作为对外性能声明**。

**④ 无 gold 替代方案的否定结果（重要诚实记录）**

| 变体 | 设计 | 结果 |
|---|---|---|
| A：共识池含被测实现 | 被测实现 + 3 变异体投票 | **显著有害**：detection 66.7%→**41.7%**（aitester）、75.0%→**38.9%**（df）；**22 行已检出退化为未检出**（把缺陷行为当共识基准） |
| B：共识池排除被测实现 | 仅 4 个变异体投票 | **无害但无效**（0→1 = 0）——变异体是**负样本**，正确测试在它们上面理应失败 |

> **方法论结论**：*"单参考 oracle 不可信"（arXiv:2608.19626）无法靠"多错误参考共识"解决。判断期望值是否正确必须有**可信的正确参考**；变异体只提供负样本，用负样本投票会删掉正确测试。*
> **可部署的"零检出修复"在本会话未找到** —— 这是明确的开放问题，应写入论文 Limitations。

**本轮把"零检出的成因"从猜测变成了可复算的定量归因（92% 归因于期望值不一致），但把归因变成可部署方法所需的"可信正样本"仍然缺失。**

### 17.6 "可信正样本"路径的实测判决（2026-10-11，LLM 实测）

> 承接 §17.5：既然"变异体共识"（负样本）无效，那用**多份独立 LLM 实现**（正样本候选）替代 gold 是否可行？

**实验**：4 个 QuixBugs 任务，每个让 LLM **独立生成 5 份实现**（提示词只给函数名 + "按通用语义正确实现"，**不给**缺陷版、**不给** gold）；在 11 个探针输入上比较"LLM 实现之间是否一致"与"LLM 多数是否等于 gold"。

| 任务 | 探针 | **LLM 内部一致** | **多数 = gold** |
|---|---|---|---|
| `gcd` | 4 | 4/4 | 4/4 |
| `get_factors` | 3 | 3/3 | **0/3** |
| `max_sublist_sum` | 2 | 2/2 | 1/2 |
| `levenshtein` | 2 | 2/2 | 2/2 |
| **合计** | **11** | **11/11 = 100%** | **7/11 = 64%** |

**关键证据**：

| 探针 | gold | LLM 多数（5/5 一致） | 更自然者 |
|---|---|---|---|
| `get_factors(12)` | `[2, 2, 3]`（**质因数**） | `[1, 2, 3, 4, 6, 12]`（**全部因子**） | LLM |
| `get_factors(1)` | `[]` | `[1]` | LLM |
| `max_sublist_sum([-1,-2])` | `0`（允许空子数组） | `-1`（禁止） | 规格欠定 |
| `gcd(-1,-3)` | `-1`（保留符号） | `1`（同 `math.gcd`） | LLM |

**三条结论**

1. **LLM 独立实现之间一致性极高（11/11）** → "多实现共识"作为**一致性信号**可靠。
2. **但与基准 gold 仅 64% 一致** → 用它判断"测试期望值是否正确"会**系统性判错**（`get_factors` 上 3/3 全错），与 §17.5 变体 A 同类的破坏。
3. **根因（本报告最重要的方法学发现之一）**：**这些基准的 gold 语义不由自然语言规格唯一决定**。`get_factors` 的"质因数 vs 全部因子"是**规格欠定点**，基准用参考实现单方面固定了它。因此"从自然语言规格重建可信正样本"**原理上不可能**完全成功——**缺口不在模型能力，在规格本身**。

> **建议写入论文 Limitations**：*"以单参考实现为 oracle 的测试生成评测，隐含假设自然语言规格蕴含唯一正确语义；我们在 `get_factors` 等任务上实测到该假设不成立（5/5 独立实现一致地给出与参考不同的语义）。因此这类基准测得的既是'测试生成能力'，也包含'能否猜中参考实现的任意规格选择'。"*

### 17.7 规格消歧作为研究对象：SAI 框架与首批测量（2026-10-11）

> 承接 §17.6 的结论（"缺口在规格本身，不在模型能力"）：本轮把**规格消歧**从现象升级为**可测量的研究对象**。

**核心洞见：两个必须分离的指标**

| 现象 | 含义 | 指标 |
|---|---|---|
| 各独立实现**互相不一致** | 规格**真的欠定** | **SAI** = 欠定点 / 全部探针点 |
| 各实现**一致，但参考实现与全体不同** | 规格已确定，参考选了"违反常规"的一支 | **gold 偏离率** = 偏离点 / 确定点 |

**已证明二者可分离**（`get_factors`）：3 份独立实现互相**完全一致**（**SAI = 0.0**），但与 gold **完全不一致**（**偏离率 = 1.0**）。

**首批真实测量（LLM 实测，4 份独立实现/任务，9 个函数 / 198 探针点）**

| 函数 | 探针 | **欠定** | **SAI** | 确定 | **gold 偏离率** |
|---|---|---|---|---|---|
| `depth_first_search` | 25 | **23** | **0.920** | 2 | 1.000 |
| `breadth_first_search` | 25 | 9 | 0.360 | 16 | 1.000 |
| `bitcount` | 19 | 6 | 0.316 | 13 | 0.000 |
| `bucketsort` | 24 | 6 | 0.250 | 18 | **1.000** |
| `gcd` | 25 | 0 | 0.000 | 25 | 0.200 |
| `find_in_sorted` | 24 | 0 | 0.000 | 24 | 0.042 |
| `detect_cycle` / `find_first_in_sorted` / `flatten` | 9/24/23 | 0 | 0.000 | 全部 | 0.000 |

| **汇总** | **198** | **44** | **池级 0.222** | **154** | **池级 0.273** |

**三条结论**

1. **基准存在系统性规格问题**：近 **1/4** 探针点上自然语言规格允许多解；**另 1/4 强**的探针点上规格其实已确定（所有独立实现一致），但**参考实现选了另一支**。
2. **两类问题需不同处置**：SAI 高（`depth_first_search` 0.92）→ **补规格**；偏离率高而 SAI=0（`bucketsort`、`get_factors`）→ **显式化基准约定或修正参考实现**。
3. **对评测的直接后果**：被测系统"猜中"参考实现的任意选择则得分，否则丢分——**该基准测得的包含"规格猜测能力"，而非仅"测试生成能力"**。

**可支撑的论文主张（可证伪）**

> *以单参考实现为 oracle 的测试生成基准，其分数包含一个与测试质量无关的"规格猜测"分量；该分量可量化为 SAI 与 gold 偏离率两个元指标，二者均与任何被测模型无关。*
> 证据：9 函数 / 198 探针点 / 4 份独立实现；池级 SAI 0.222、池级偏离率 0.273；两指标已证明可分离。

**工件**：`experiments/spec_ambiguity.py`（框架）、`tests/test_spec_ambiguity.py`（12 例守卫）、`experiments/results/sai_report.md`（含逐点清单）。

**交付说明（诚实标注）**：
1. 本次评审为完成审计，在 `audit_2026/` 下创建了临时脚本（19 个 .py）。它们**不在** `pyproject.toml` 的 `[tool.ruff] extend-exclude` 中，因此 `ruff check .` 现在会报错（本次已删除 12 个未引用脚本；残余约 259 条错误全部来自这些审计脚本，项目源码本身仍全绿：`ruff check src/ config.py experiments/ tests/` 无错）。**建议**：`extend-exclude` 增 `"audit_2026"`，或交付后删除整个目录。
2. 本次未修改项目任何源码、配置、测试或既有文档；除新增本报告与 `audit_2026/` 外，工作树状态与评审开始时一致。
3. 本次**未调用任何 LLM API**；所有项目侧数字均来自对入库工件的只读解析。
4. 本次发现的环境副作用（3 个孤儿 pytest 进程，运行 16.5 h）**不是**本次评审产生的——其最早启动时间早于本次会话；本次未新增孤儿进程。

---

## 18. 最终结论（一段话）

> **本项目的工程与测量素养高于其科学结论的强度。**
> 本次独立评审逐位复算了 12,789 行主批次记录、独立重放了修复验证、普查了全部真实仓库基准工件、并通过一手来源（含官方榜单逐条文件）重建了 2025–2026 前沿基线。结论是：
> **① 项目最核心的负结果归因（"过红是 −28pp 的主机制"）被推翻**——真实主机制是 **48.6% 的运行从未产生任何失败的测试**；**② 项目最重要的正面数字（repair 39.31%）是事后重放口径**，其 all-task 值为 **21.84%**，且 48.6% 的行根本不进修复循环；**③ 项目唯一的"真实基准"结论（SWE-bench 0/20）不成立**——365 行真实仓库工件 100% 缺少 `instance_code` 与 detection 字段，属**评测管道未接通**，而非负结果；**④ "逻辑驱动"与"自修复"两个标签在主口径下分别为"零实证"与"代码层不成立"**；**⑤ 但项目的引用是真实的**——42 个 DOI 中 41 个、72 个 arXiv ID 全部可核验，不存在编造文献，真正的问题是 3 处事实性错误与若干限定条件缺失。
> **在 2025–2026 前沿格局中，本项目不处于前沿位置**，且当前不存在任何可验证的"超越前沿"证据。但存在一条**真实的、可辩护的路径**：前沿一手文献已确认"**oracle 而非覆盖**是当前 LLM 测试生成的瓶颈"（arXiv:2609.09315），并已实证"**SWE-bench 榜单边际无法排序**"（arXiv:2609.17394）；本项目已有的 fail-closed 测量语义、provenance、工件校验与"测量伪影自我披露"习惯，恰好是进入这一空间的**稀缺入场券**。因此本报告建议的唯一可行定位是：**从"又一个多智能体测试生成系统"转为"测试生成的政策无关测量与失败归因框架"**，并以路径 A（MDO 指标）+ 路径 D（外部有效性 + 五步审计协议）作为 P0 双主线——**接受结果可能为负，因为那才是可发表且可复现的东西**。

---

# 第二部分｜附录（原始审计工件）


---

## 附录 A｜项目声明溯源审计（零 LLM 复算，90 条逐条复核）

> 源文件：`audit_2026/T_A_claims_traceability.md`（本附录为该文件的完整内容，仅调整标题层级与编号）

### A·T-A 独立声明溯源审计（零 LLM 复算）

- 审计执行者：独立评审团队 T-A（claims-auditor）
- 执行时间：2026-10-11 10:15–11:05（Asia/Shanghai）
- 工作目录：`/Users/wangchenyu/Workspace/AITester`（git HEAD `d9e51df`，**工作树 dirty：`git status --short` 共 59 项**）
- 解释器：`.venv/bin/python`（3.14）；机器上另有 2 个**孤儿 pytest 进程**（见缺陷 D-01）持续占用 ~2 核
- 纪律声明：本报告不采信 `README.md` / `BASELINE.yaml` / `CHANGELOG.md` / `INDEPENDENT_REVIEW_2026-10-10.md` / `REVIEW_2026_FRONTIER.md` / `review_2026/*.md` 的任何结论。**下文每个"复算值"均由我本人在原始工件（`experiments/results/**`）上重新计算得到**，命令见 §7。项目自评数字一律作为"待验证声明"处理。
- 零 LLM 声明：全程未调用任何 LLM API；未开实验批次；未跑 `run_benchmark`/`run_main_batch`。允许的写操作仅限 `audit_2026/`（临时脚本）与本文件。

### A.0 证据等级定义（本报告自定义，先声明后使用）

| 等级 | 定义 |
|---|---|
| **A** | 用入库原始工件逐位复算，与声明值一致（差异仅来自四舍五入）；工件路径 + 命令 + 数值齐备 |
| **B** | 数值可复算，但**口径需限定**：分母/子集/批次未披露、跨批次拼接、或存在**伪重复**（同一实验被重复计数） |
| **C** | 部分一致：数值或文字标注有可指认的偏差（如标 12 实测 13），或仅总量可核、分项不可核 |
| **D** | 不一致：复算值与声明值冲突，或声明定性被工件直接否证 |
| **E** | 无法溯源/无法验证：无入库工件、无对应字段、被后续修复取代，或在当前环境无法测量 |

---

### A.1 声明复核总表

> 位置列格式 `文件:行`。复算命令简写见 §7 命令清单（`P<n>` 对应脚本）。"复现性"列为 可复现 / 部分可复现 / 不可复现 / 无法溯源。

#### A.1.1 tests 与 static_checks 节

| 编号 | 位置 | 声明内容 | 原始工件/依据 | 复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|---|
| T-01 | `BASELINE.yaml:17` | 全量 pytest `total_passed=5262` | 当前工作树 tests/（262 个测试文件） | 实测 **5311 passed + 2 failed + 3 skipped + 1 xfailed**；`--collect-only` **5317** | 5262 passed / 0 failed | 与声明冲突（且**项目自带守卫** `test_tests_and_mypy_are_current` 断言 `5317−5262 ≤ 9` 失败，报"BASELINE 数字可能已过期"） | 不可复现 | **D** |
| T-02 | `BASELINE.yaml:17` 注释 | "--collect-only 收集 5259" | 同上 | **5317 tests collected in 2.17s** | 5259 | 不一致（+58） | 不可复现 | **D** |
| T-03 | `BASELINE.yaml:18` | `total_failed: 0` | 同上 | **2 failed**：`TestEnvSnapshotCompleteness::test_gate_reports_no_missing`、`TestBaselineNumbersConsistency::test_tests_and_mypy_are_current` | 0 | 不一致 | 不可复现 | **D** |
| T-04 | `BASELINE.yaml:19` | `total_skipped: 3` | 同上 | **3 skipped** | 3 | 一致 | 可复现 | **A** |
| T-05 | `BASELINE.yaml:20` | `total_xfailed: 1` | 同上 | **1 xfailed** | 1 | 一致 | 可复现 | **A** |
| T-06 | `BASELINE.yaml:22` | `suite_seconds: 35`（注：xdist -n 4 实测 34.5s） | 同上 | 串行 **223.21s**；`-n 4` **82.28s**（受 D-01 两孤儿进程抢核影响，不能排除负载混杂） | 35 | 量级一致但数值差 2.4× | 部分可复现 | **C** |
| T-07 | `BASELINE.yaml:21` | `slim_environment: 1863` | 需精简依赖环境 | 未测（需卸载 chromadb/matplotlib 类依赖，超出只读审计范围） | 1863 | 无法验证 | 无法溯源 | **E** |
| S-01 | `BASELINE.yaml:82` | `ruff_warnings: 0` | 全仓（除我自己的 `audit_2026/`） | `ruff check . --extend-exclude audit_2026` → **All checks passed**；`ruff format --check` → 591 files already formatted | 0 | 一致 | 可复现 | **A** |
| S-02 | `BASELINE.yaml:83` | `mypy_errors: 0` | src/ + config.py | `mypy src/ config.py` → **Success: no issues found in 123 source files** | 0 | 一致 | 可复现 | **A** |
| S-03 | `BASELINE.yaml:84` | `mypy_source_files: 120` | 同上 | **123** | 120 | 不一致（+3） | 不可复现 | **D** |
| S-04 | `BASELINE.yaml:81` | `ruff_version: 0.16.3` | venv | `ruff --version` → **0.16.3**；`mypy --version` → **1.15.0** | 0.16.3 | 一致 | 可复现 | **A** |
| C-01 | `BASELINE.yaml:30` | `line_total_pct: 89`（89.56） | 需 `--cov=src` 全量跑批 | 未跑覆盖率；仓库根 `.coverage` 文件**仅含 1 个被测文件**（已退化，无法支撑任何结论） | 89 | 无法验证 | 无法溯源 | **E** |
| C-02 | `BASELINE.yaml:42` | `branch_total_pct: 83`（82.78） | 同上 | 同上 | 83 | 无法验证 | 无法溯源 | **E** |
| C-03 | `BASELINE.yaml:31-41` | 10 个核心模块逐文件行覆盖（70–91） | 同上 | 同上 | — | 无法验证 | 无法溯源 | **E** |
| C-04 | `BASELINE.yaml:43-46` | 核心路由分支覆盖 98/91/100 | 同上 | 同上 | — | 无法验证 | 无法溯源 | **E** |

#### A.1.2 target_quality 节（被测代码侧指标）

> 复算方法：对 `experiments/results/main_batch/benchmark_synthetic_*.json` 共 **10 个批次**逐行取 `details[].<field>`，剔除 None 后求**批次均值**，再看区间（与 BASELINE 注释口径一致）。

| 编号 | 位置 | 声明内容 | 复算值（我的批次均值区间） | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| Q-01 | `BASELINE.yaml:61` | aitester 被测行覆盖区间，注"10 批次区间（n=87/批）" | `[83.977, 93.58]`（10 批：5/5/50/87×7） | [84.0, 93.6] | 数值一致；**注记 n=87/批 错误**（含 2 个 n=5 冒烟批 + 1 个 n=50 批） | 可复现（口径需更正） | **B** |
| Q-02 | `BASELINE.yaml:62` | plain_llm 覆盖区间 [86.0, 97.2] | 全 10 批 `[70.4, 97.22]`；剔除 2 个 n=5 冒烟批后 `[85.96, 97.22]` | [86.0, 97.2] | 需**静默剔除 2 个批次**才成立，注记未披露 | 可复现（口径需限定） | **B** |
| Q-03 | `BASELINE.yaml:63` | plain_llm_df 覆盖区间 [81.5, 93.6] | `[81.483, 93.552]`（df 仅存在于 5 个批次） | [81.5, 93.6] | 一致；df 批次数（5）未披露 | 可复现（口径需限定） | **B** |
| Q-04 | `BASELINE.yaml:66` | aitester mutation_score [0.818, 0.976]，7 批 n=77–81 | `[0.8175, 0.9760]`，n=77/79/80/77/81/77/81 | [0.818, 0.976] | 逐位一致 | 可复现 | **A** |
| Q-05 | `BASELINE.yaml:67` | plain_llm mutation [0.951, 0.992] | `[0.9515, 0.9916]` | [0.951, 0.992] | 一致（0.9916→0.992） | 可复现 | **A** |
| Q-06 | `BASELINE.yaml:68` | plain_llm_df mutation [0.986, 0.997] | `[0.9856, 0.9968]` | [0.986, 0.997] | 一致 | 可复现 | **A** |
| Q-07 | `BASELINE.yaml:71` | spec_compile_rate aitester [0.205, 0.219]，"E1/E2 logic 档**四批次**" n=77/81 | `[0.2045, 0.2189]`；但 4 个文件实为**2 个种子 × 2 次重跑**（见缺陷 D-02），独立测量只有 2 个 | [0.205, 0.219] | 数值一致，**"四批次"计数失真** | 可复现（独立性存疑） | **B** |
| Q-08 | `BASELINE.yaml:74` | spec_expr_coverage [0.723, 0.741]，n=45/51 | `[0.7232, 0.7415]`，n=45/51 逐位一致；同 D-02 伪重复 | [0.723, 0.741] | 一致 | 可复现（独立性存疑） | **B** |
| Q-09 | `BASELINE.yaml:76` | specificity_gate aitester `{specific_red: 40, over_red: 66}` | 4 批之和 = 9+11+9+11=**40**、18+15+18+15=**66**；但其中 2 批与另 2 批**逐行同值**（D-02），实际 n 减半 | {40, 66} | 数值一致，跨批合计**双重计数** | 可复现（合计口径不成立） | **B** |
| Q-10 | `BASELINE.yaml:77` | specificity_gate plain_llm_df `{162, 140}` | 38+43+38+43=**162**、38+32+38+32=**140** | {162, 140} | 同上（双重计数） | 可复现（合计口径不成立） | **B** |
| Q-11 | `BASELINE.yaml:78` | "df 的 specific_red/over_red ≈1.16 而 aitester ≈0.61" | 162/140 = **1.157**；40/66 = **0.606** | ≈1.16 / ≈0.61 | 一致 | 可复现 | **A** |
| Q-12 | `BASELINE.yaml:59` | "aitester 覆盖率 84–94% 而检出率仅 **13–16%**" | 7 批（10-06/10-07）aitester detection：`10.3%–17.2%`（全行分母）或 `11.7%–19.0%`（非 None 分母）；R-P0-2 合并 `38/261=14.6%` / `38/240=15.8%` | 13–16% | **无法复算出该区间**（口径未注明，与任一自然口径都不吻合） | 部分可复现 | **C** |
| Q-13 | `BASELINE.yaml:72` | "AC 批后由**恒 0.0** 抬升到 ~0.21" | `ab1_validation/benchmark_synthetic_20261006_172151.json` aitester spec_compile_rate 均值 = **0.0000**（n=12） | 恒 0.0 | 一致 | 可复现 | **A** |

#### A.1.3 benchmark 节：R-P0-2 主批次（n=261/臂，3 种子）

> 基线：`benchmark_synthetic_20261006_{140906,151907,164357}.json`，seed 42/43/44，`git_dirty=true`，cache namespace seed42/43/44。

| 编号 | 位置 | 声明内容 | 复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-01 | `BASELINE.yaml:168`, `README.md:56` | df detection 44.8%（117/261） | **117/261 = 44.83%**（38+36+43） | 44.8% | 逐位一致 | 可复现 | **A** |
| B-02 | 同上 | aitester 15.8%（38/240，21 行 None 不进分母） | **38/240 = 15.83%**；None 行数 6+8+7=**21** | 15.8% | 逐位一致 | 可复现 | **A** |
| B-03 | 同上 | plain_llm 1.5%（4/261） | **4/261 = 1.53%** | 1.5% | 一致 | 可复现 | **A** |
| B-04 | `BASELINE.yaml:170` | δ(df vs plain_llm)=+0.426 | 配对 n=261，n10/n01=113/0；Dirichlet 后验均值 **+0.4264** | +0.426 | 逐位一致 | 可复现 | **A** |
| B-05 | 同上 | δ(aitester vs plain_llm)=+0.139 | 配对 n=240，37/3；后验均值 **+0.1393** | +0.139 | 逐位一致 | 可复现 | **A** |
| B-06 | 同上 | δ(aitester vs df)=−0.279（"−28pp"） | 配对 n=240，12/80；后验均值 **−0.2787**；**非配对差为 −28.99pp** | −0.279 | 一致；两种口径分别对应 −27.9pp/−29.0pp，均约 −28pp | 可复现 | **A** |
| B-07 | `BASELINE.yaml:156` | repair 修正口径 **39.31%（57/145）** | 我**独立重放** 10 个批次的全部带补丁行：R-P0-2 可重放 **145**、correct **57** → **0.3931** | 39.31% (57/145) | 逐位一致 | 可复现 | **A** |
| B-08 | `BASELINE.yaml:157` | E1/E2 修正 repair **54.72%（58/106）** | 独立重放：可重放 **106**、correct **58** → **0.5472** | 54.72% (58/106) | 逐位一致 | 可复现 | **A** |
| B-09 | `BASELINE.yaml:181` | "早期 10-01 批 **0/15 系真零**" | 独立重放：早期批次可重放 **15**、correct **0** | 0/15 | 一致 | 可复现 | **A** |
| B-10 | `BASELINE.yaml:157` | v1 口径 35.86%（52/145）/ 48.11%（51/106） | 未复算（需要"未清理围栏"的旧判分路径，当前代码已修） | 35.86%/48.11% | 无法验证（历史口径已被取代） | 无法溯源 | **E** |
| B-11 | `BASELINE.yaml:179`, `README.md:56` | 漏斗修正：patch 产出 **94%** / plausible **47%** / correct **39.31%** | 修复循环（`detection_first_status ∈ {red_then_green, red_not_repaired}`）**154/261**；带补丁 **145**（94.2%）；`patch_plausible=1` **72**（46.8%）；correct 57（39.31% of 145） | 94%/47%/39.31% | 逐位一致 | 可复现 | **A** |
| B-12 | `BASELINE.yaml:182-183`, `README.md:56` | $/task：aitester **0.0259** / plain_llm **0.0034** / df **0.0045** USD | 按 `experiments/price_table.json`（deepseek-flash in $0.3/M、out $1.2/M）× 三批 261 行 token_metrics：**0.02590 / 0.00345 / 0.00455** | 0.0259/0.0034/0.0045 | 逐位一致 ⚠️ 见缺陷 D-04（缓存命中不计 token ⇒ df/plain_llm 成本是下界） | 可复现（记账不完整） | **A** |
| B-13 | `BASELINE.yaml:178` | "三批次 git_dirty=true（--allow-dirty 口径跑批）" | 三批 `provenance.git_dirty` 全为 **true** | true | 一致 | 可复现 | **A** |
| B-14 | `README.md:56` | "主批次修正 false_fix=**87.2%**" | 同源重放 + 修正规则：passed 可测 **436**，false_fix **380** → **0.8716** | 87.2% | 逐位一致；**但 380 中 332 行为"根本没有补丁产出"**（仅 48 行为真实错误补丁），见 §5 解读 | 可复现（语义需解读） | **A** |
| B-15 | `README.md:56` | "CPR=84.3%"（ADR-0027 口径） | 同源重跑 `corrected_metrics` 得 **0.8451（60/71）**，与库内 `corrected_report_v2.md` 逐字节一致；我已独立复算分母：plausible 行 **144**、其中 correct **71** | 84.3% vs 84.51% | README 引用的是 v1 旧值（v1/v2 两版同指标两名） | 部分可复现（引用陈旧） | **C** |

#### A.1.4 benchmark 节：E4 / QuixBugs 真实基准

| 编号 | 位置 | 声明内容 | 工件的复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-16 | `BASELINE.yaml:306,326` | E4 首次跑 aitester detection **0/41** | `e4_quixbugs_aitester/benchmark_quixbugs_20261009_215514.json`：detection 非 None **41**，正例 **0** | 0/41 | 一致 | 可复现 | **A** |
| B-17 | `BASELINE.yaml:327` | repair **35/40 = 87.5%**；false_fix **2.5%** | repair 非 None **40**、正例 **35**；detection 非 None 行 false_fix 均值 **0.025** | 35/40；2.5% | 一致 | 可复现 | **A** |
| B-18 | `BASELINE.yaml:329-330,336-337` | token/task **17156**（df **2370**）；red_seen **40/41**、**41/41** | 41 个非测试驱动行均值：**17156.5** / **2370.4**；40/41、41/41 | 同左 | 一致（**分母为 41 缺陷程序**，而 detection/repair 用 41/40，口径已在同一区块混用） | 可复现（口径需披露） | **A** |
| B-19 | `BASELINE.yaml:364,381` | 修正后 aitester detection **17/37 = 45.9%** | `e4_quixbugs_FIXED_harness/aitester.json`：非 None **37**、正例 **17** | 17/37 | 一致 | 可复现 | **A** |
| B-20 | `BASELINE.yaml:364,381` | 修正后 repair **37/40 = 92.5%** | 行级 repair_rate 非 None **40**、`repair_rate==1.0` **37** | 37/40 | 数值逐位可复算；**但 13/37 行 `patch_correct=1` 同时 `patch_plausible=0`**（逻辑冲突，缺陷 D-05）；若要求"写盘成功 ∧ gold 通过"则仅 **24/40 = 60%** | 可复现（内部自相矛盾） | **C** |
| B-21 | `BASELINE.yaml:365,386` | df detection **31/37 = 83.8%** | 非 None **37**、正例 **31** | 31/37 | 一致 | 可复现 | **A** |
| B-22 | `BASELINE.yaml:364-365,385-386` | token **16038** vs **1905**，"成本高 **8.4×**" | 41 非测试驱动行均值 **16037.5** / **1905.3**，比值 **8.42×**（全 50 行口径为 15252.6/2309.3 = 6.61×） | 16038/1905/8.4× | 一致；分母（41）未在 BASELINE 披露 | 可复现（口径需限定） | **B** |
| B-23 | `BASELINE.yaml:382` | 伪影修正前后 McNemar：不一致对 17、χ²=15.059、p=1.042e-04、n10=17/n01=0 | 我的配对：n01=**17**、n10=**0**、χ²(cc)=**15.059**、渐近 p=**1.042e-04**（精确二项 p=1.5e-05） | 同左 | 一致（p 为 χ² 渐近值，非精确二项） | 可复现 | **A** |
| B-24 | `BASELINE.yaml:387` | 双臂终局 McNemar：不一致对 14、χ²=12.071、p=0.0005 | 我的配对：**14/0**、χ²(cc)=**12.071**、渐近 p=**5.12e-04** | 同左 | 一致 | 可复现 | **A** |
| B-25 | `BASELINE.yaml:432-435` | "**首轮** over_red 30/50（60%）detection 0%；specific_red 19/50（38%）detection 100%" | FIXED harness **终审**分布：over_red **30**（其中 20 行 detection 可判，正例 **0**）、specific_red **19**（17 行可判，正例 **17**=100%） | 30/50、19/50 | 数值一致，但工件只有**终审** verdict，**无"首轮"字段** ⇒ "首轮"标注不可验证 | 部分可复现 | **C** |
| B-26 | `BASELINE.yaml:466-468` | detection=None 的 4 任务：bitcount / find_first_in_sorted / sqrt / wrap，均为"缺陷实现不终止" | FIXED harness 中 detection=None 的 13 个任务 = 9 个 `*_test` 测试驱动 + **bitcount / find_first_in_sorted / sqrt / wrap** | 4 任务 | 一致 | 可复现 | **A** |
| B-27 | `BASELINE.yaml:369-371` | 第四起伪影零 LLM 复现："9/9 缺陷程序在 buggy/fixed 两侧均 rc=2"、"F2P 检出 0/7 → 6/7" | 唯一相关入库工件 `diagnostic_12task_prerepair.json` 的 12 行**没有 rc 列**（`rc`/`pytest_rc` 均为 None）；无 9 任务或 7 任务诊断工件 | 9/9；0/7→6/7 | 无入库证据 | 无法溯源 | **E** |
| B-28 | `BASELINE.yaml:484-489` | 孤儿 pytest 进程：observed 2、ppid=1、~100% CPU、uptime 56–63 分钟 | 我实测同机 **2 个孤儿进程**：`pid 36935/37116`，**ppid=1**、**~97% CPU**、**etime 16:31:25 / 16:30:18**（≈16.5 小时，远超声明） | 2 个 / 56–63min | 一致且更严重 | 可复现 | **A** |
| B-29 | `BASELINE.yaml:489` | "第 1 环未修"；`batch_hang_fix.tests: 12` | 代码层确认：`experiments/_m1_metrics.py:358-372` 用裸 `subprocess.run(timeout=)`，**无 `start_new_session`/killpg** → 孙进程可被 launchd 收养（与实测孤儿一致）。`tests/test_process_utils.py` 当前收集 **13** 例（声明 12） | 12 | 机制一致；测试数 13≠12 | 部分可复现 | **C** |
| B-30 | `BASELINE.yaml:374` | `measurement_artifact_4.regression_tests: tests/test_m1_packaged_tests.py::TestDualLayout（5 例）` | 收集 **5 tests** | 5 例 | 一致 | 可复现 | **A** |

#### A.1.5 benchmark 节：E6 / A1 / RT1 / D1 消融批次

| 编号 | 位置 | 声明内容 | 复算值（`e6_a1_batches/...`） | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-31 | `BASELINE.yaml:508-510` | E6 control：aitester **8/87 (9.2%)**、df **30/87 (34.5%)**、plain_llm **0/87** | 8 / 30 / 0（非 None 均 87） | 同左 | 一致 | 可复现 | **A** |
| B-32 | `BASELINE.yaml:518` | E6 control aitester vs df：χ²=**16.962**、δ=−25.3pp | 配对 n=87，n10/n01=2/24，χ²(cc)=**16.962**；朴素差 34.5−9.2=**−25.3pp** | 同左 | 一致 | 可复现 | **A** |
| B-33 | `BASELINE.yaml:399-402` | A1 消融"从未生效"：env_snapshot 中 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 缺失（null）、detection 与标准臂逐点相同 8/87 vs 8/87、日志 0 条生效行 | `a1_strip_seed42/benchmark_...180655.json` 的 `provenance.env_snapshot` **无该键**；detection **8/87**（与 control 完全相同） | null；8/87 | 一致（键缺失=未生效的直接证据） | 可复现 | **A** |
| B-34 | `BASELINE.yaml:539-541` | E6 phase1（冷缓存）：aitester **6/87 (6.9%)**、df **27/87 (31.0%)**、plain_llm **9/87 (10.3%)**；tokens 8857/2586/1257 | 6 / 27 / 9；token/task **8857.5 / 2586.4 / 1257.2** | 同左 | 逐位一致 | 可复现 | **A** |
| B-35 | `BASELINE.yaml:543-546` | E6 phase2（matched）：aitester **2/87 (2.3%)**、tokens 3735、`budget_capped 87/87`、top stop_reason `budget_exceeded 84`；df **23/87 (26.4%)**、tokens 2602、capped 1/87 | aitester：正例 **2**，但 detection **非 None 仅 11/87**（18.2%）；tokens 3734.6；capped **87/87**；`budget_exceeded` **84**。df：正例 **23**，非 None **86**（26.7%）；tokens 2602.1；capped **1** | 2/87、23/87 | 数字对，但**双臂分母不同源**（aitester 2/87 的 87 中 76 行从未判定）⇒ "matched 对照"非同类比较 | 可复现（口径需限定） | **B** |
| B-36 | `BASELINE.yaml:548-549` | phase2 主终点：df_matched vs aitester_standard χ²=13.474 p=0.0002；aitester_matched vs df_standard χ²=0.5 p=0.4795 | 配对 86 行，19 不一致，χ²(cc)=**13.474**，渐近 p=**2.41e-04**；另一对不一致 2、χ²=**0.5**、p=**0.4795** | 同左 | 一致（p 为渐近值） | 可复现 | **A** |
| B-37 | `BASELINE.yaml:551` | 预算工具性检验：df_standard vs df_matched Δ=−4.6pp、χ²=1.125、p=0.2888 | 27/87 vs 23/87 → **−4.6pp**；配对 86、不一致 8、χ²(cc)=**1.125**、渐近 p=**0.2888** | 同左 | 一致 | 可复现 | **A** |
| B-38 | `BASELINE.yaml:571-574` | RT1：plain_llm 10.3% · RT1 **11.5%（10/87）** · df 31.0%；tokens 1257/2368/2586；regenerated 0/87、77/87、76/87 | rt1 工件内只有 **1 个臂（df 形态）**：10/87、token 2368.4、regen>0 **77/87**；plain_llm 9/87 与 df 27/87 取自**另一批次** `e6_phase1`（1257.2、2586.4、regen 0/76） | 同左 | 数值一致，但三臂**跨批次拼接**（RT1 批内无对照臂） | 可复现（口径需限定） | **B** |
| B-39 | `BASELINE.yaml:577` / `:503` | RT1 变量为 `DETECTION_FIRST_SECTION_ENABLE=false` | 该键**不在** `rt1_no_reinforcement_seed42` 工件的 `provenance.env_snapshot` 中（envelope 与 D3 同类） | false | 开关生效性无法从工件验证 | 无法溯源 | **E** |
| B-40 | `BASELINE.yaml:296-303` | D1 JSON 修复：可解析率 **427/621 → 555/621**（+128） | 未找到 621 条 Planner 形态缓存响应的入库工件/日志 | 427/621→555/621 | 无法验证 | 无法溯源 | **E** |
| B-41 | `BASELINE.yaml:306-310` | D1 消融：空计划 **34/87 → 22/87** | 结果行**无"是否空计划"字段**，无从复算 | 34/87→22/87 | 无法验证 | 无法溯源 | **E** |
| B-42 | `BASELINE.yaml:311-315` | D1 副产物：detection 6.9%→8.0%、repair **15→20**、false_fix **75.9%→70.1%** | phase1 aitester 6/87=6.9%、repair 正例 **15**、false_fix 均值 **75.9%**；d1 批 7/87=8.0%、repair 正例 **20**、false_fix **70.1%** | 同左 | 逐位一致 | 可复现 | **A** |
| B-43 | `BASELINE.yaml:441-449` | over_red 段消融：detection 17/37→**19/37 (51.4%)**、env flag **true**、McNemar 不一致 8/χ²=0.125/p=0.7237 | `ablation_r9/over_red_section_verified.json`：`OVER_RED_SECTION_ENABLE='true'`、19/37；配对 37 行、不一致 8（3/5）、χ²(cc)=**0.125**、渐近 p=**0.7237** | 同左 | 一致（p 为渐近值） | 可复现 | **A** |
| B-44 | `BASELINE.yaml:453-457` | over_red 首跑"不作结论依据"：22/37 (59.5%)、env flag **null** | 工件 22/37；`env_snapshot` **无 OVER_RED_SECTION_ENABLE 键** | null | 一致（该文件被项目自我否决，处理正确） | 可复现 | **A** |
| B-45 | `BASELINE.yaml:459-463` | 消融开关未入快照（D3）②`tests/test_over_red_section.py`（**21 例**） | 当前收集 **23 tests** | 21 | 不一致（文档测试例数漂移，见 D-10） | 部分可复现 | **C** |
| B-46 | `BASELINE.yaml:521-523` | E6 matched 结论："**已执行：预算混杂被证否 → −28pp 归因编排结构**" | 支撑统计（B-35/B-36/B-37）可复算；但 matched 臂 aitester 仅 11 行可判定（B-35），阶段 2 的 cap 低于其实际需求（87/87 触顶） | 已执行/已证否 | 数值可复现，**结论强度**受 B-35 分母问题限制（声明自身也承认测的是"预算不足时编排表现"） | 部分可复现 | **C** |
| B-47 | `BASELINE.yaml:513-516`, `:479-482` | D2：缓存命中不计 token（`src/agents/base_agent.py:437`、LRU 快路径 :389） | 代码复核：`base_agent.py:383-395` 的缓存快路径（含 `_cache_ns` 命名空间逻辑）确实绕过使用量记账。**我实测的 `total_tokens==0` 行数**：R-P0-2（热缓存）aitester **0/261**、plain_llm **0/261**、df **35/261**；E1/E2 四批（热缓存）aitester **121/348**、plain_llm **348/348**、df **348/348**（两臂 token 总量为 **0**）；E6 control plain_llm/df **87/87**、aitester 50/87；E6 phase1（冷缓存）三臂 **0/87** | 已登记缺陷 | 一致（且我给出污染面量化：热缓存批次几乎必然污染，冷缓存批次为 0） | 可复现 | **A** |
| B-48 | `BASELINE.yaml:492-500` | A2：规约 oracle 注入 **合成 2–3/87（≈2.3%）**、**真实 QuixBugs 20/50 = 40%** | 全库 7153 行扫描：`spec_oracle_injected=True` 仅出现在 2026-10-10 的 3 个 llm_logic_ab 批次（25/19/18 行）；**E6 合成批与 E4 QuixBugs 批均为 0**；且 `oracle_type` 在全库 100% 为 `generated_test` | 2–3/87、20/50 | **无入库证据**（与声明批次不符） | 无法溯源 | **E** |
| B-49 | `BASELINE.yaml:474-478` | S6 通道：注入率 0/2→**1/2**、子句可编译 **3/5=60%**、规格产物 0→224 字符 | 未找到对应工件/日志 | 1/2；3/5 | 无法验证 | 无法溯源 | **E** |
| B-50 | `BASELINE.yaml:471-472` | spec_compile_rate 由 0.205–0.219 升至 **0.472–0.517** | 可复算的批次均值：phase1 **0.4722**、d1_json_repair **0.5167**、E4 aitester **0.4784**；即区间由**两个不同批次**拼出（0.472 与 0.517 分属 10-09 两批，配置不同） | 0.472–0.517 | 数值一致，跨批次拼接未披露 | 可复现（口径需限定） | **B** |

#### A.1.6 README 头部与 SWE-bench 相关声明

| 编号 | 位置 | 声明内容 | 复算值 | 声明值 | 判定 | 复现性 | 等级 |
|---|---|---|---|---|---|---|---|
| B-51 | `README.md:56` | "**SWE-bench Lite（sqlfluff-20）真实基准 0/20 负结果**与统计检验同样如实披露、不筛选" | 全库 `dataset∈{swe_bench, swe_bench_pro}` **24 个工件 / 365 行**：`detection_rate` 键 **0/365**；`task_metadata.instance_code` **100% 为空**；`passed=True` 仅 **4/365**；Aug-18 批 20 行 `repo` 全为 `unknown`、无 `generated_test`/`patch` 落盘；`error_category` = patch_validation_failed 148 / 空 125 / execution_trace_missing 59 / syntax 28 / 其他 5 | 0/20 负结果 | **"负结果"定性不被工件支持**：从未产生过 detection 测量（无该字段），且失败发生在判定之前（无源码、无补丁） | 不可复现（定性冲突） | **D** |
| B-52 | `README.md:1627` | "该批次实验受 API 限流影响，**结果未归档到仓库**" | 同名实验的工件**已入库** 365 行（含 `experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json`）；同目录 `swebench_20_run.log` 内有 **7 条 403 insufficient_quota**（qwen-plus）与 12 条"测试代码语法错误" | 未归档 | 与仓库现状矛盾（同一 README 内两处互相冲突） | 不可复现 | **D** |
| B-53 | `README.md:1633-1635` | "管道与环境已全部修通，0/N 是 **LLM 引擎修复质量边界**，非管道/非环境" | Sep-25 三批 `repo='sqlfluff/sqlfluff'`（管道确已修通）；aitester 0/20×3，`error_category=patch_validation_failed` 18–20/20；plain_llm 臂 `error_category` 全为空串（无遥测）；single_agent 20/20 `execution_trace_missing`。**无任何行含 detection_rate 或 F2P 判定字段** | 非管道/非环境 | 定性无法用行级数据证实（无 F2P/检测字段）；且 plain_llm/single_agent 臂遥测缺失 | 部分可复现 | **C** |
| B-54 | `BASELINE.yaml:511-517` | E6 `env_snapshot` 缺 `PLAN_STRIP_EXPECTED_OUTPUT_ENABLE`（D3）+ followup"建议做成门禁（未实施）" | 该门禁**已实施**（`tests/test_2026_10_10_optimization_batch.py:40-54` 调用 `scripts/gates/check_env_snapshot_keys.py`），但**当前 exit 1**：3 个新开关（`EMPTY_PLAN_SHORTCUT_ENABLE`/`OPERATION_MAP_INJECT_ENABLE`/`PATH_ENUM_INJECT_ENABLE`，均定义于 `src/graph/nodes.py`）未登记入 `_env_snapshot_keys` | 未实施 | 已实施但**当前红**（同类事故复发，见 D-07） | 不可复现 | **D** |
| B-55 | `README.md:58` | "✅ **无硬编码密钥**（`.env*` / `.private` 已 gitignore / 删除）" | `git check-ignore` 确认 `.env`、`.env.local`、`.private/` 均被忽略；但工作树**存在** `.env.local`（含非空 `LLM_1_API_KEY`，≥20 字符）与 `.private/.env.local`；`llm_configs.json`（**已 tracked**）无密钥材料；`.env.local.template`（tracked）为占位符。项目自带 `.git-hooks/check_secret_leak.sh` **exit 1**，但命中的是 40 位 git SHA 等**误报**（`review_2026/*.md`、`experiments/run_payload_ab.py`） | 无硬编码密钥 | 未入库到 git 属实；本地明文凭证在盘属"已知可接受风险"（README 同段已声明），但**密钥泄漏守卫当前为红且误报率高** | 部分可复现 | **C** |
| B-56 | `BASELINE.yaml:565-570` | ci_gates_2026_10_09：`full_suite: 5107 passed / 3 skipped / 0 failed`、`guards: 10/10 exit 0` | 历史批次声明（2026-10-09）；**当前树**全量 = 5311 passed / 2 failed；`check_env_snapshot_keys.py` exit **1** | 10/10 exit 0 | 历史值无法回验；当前门禁红 | 无法溯源 | **E** |

> 全表共 **90 条**声明（含 §1.7 补充项），等级分布见 §2（由脚本对本文档"等级"列计数得出，非手工统计）。

#### A.1.7 补充声明（metrics_schema 声明 vs 实际落盘）

| 编号 | 位置 | 声明内容 | 复算值（全库 7153 行扫描） | 判定 | 等级 |
|---|---|---|---|---|---|
| M-01 | `BASELINE.yaml:128-153` | `metrics_schema` 声明 `patch_rollback_verdict`、`patch_rolled_back`（A-03 观测层） | **0/7153 行出现该键**（键名从未落盘） | 声明字段从未产出 | **E** |
| M-02 | 同上 | `regression_rate` 为核心三指标之一 | 键存在于 3968 行，**非 None 0 行**（恒未填充） | 从未产出 | **E** |
| M-03 | 同上 | `red_regression_violation`（双门协议观测） | 2997 行含键，**非 None 0 行** | 从未产出 | **E** |
| M-04 | 同上 | `deterministic_repair_status`（ADR-0019 观测层） | 1891 行含键，**非 None 0 行** | 从未产出 | **E** |
| M-05 | 同上 | `fl_at_k`（"定位维度随结果行并列输出"，`README.md:56`） | 仅 **784/7153 = 11.0%** 行非 None；E1/E2 四批中只有 2 批有值（且 3 个种子值为 0/1 混合） | 名义可得、实际覆盖率 11% | **C** |
| M-06 | 同上 | `patch_precision`（过拟合度量） | 非 None **685/7153**；行级取值仅 0.0/1.0；**无法作为聚合量**（见 D-05） | 口径缺陷 | **C** |

---

### A.2 复现性统计（我实际计数）

对 §1 表中 **90 条**声明逐条判定（计数由脚本对本文档"等级"列统计，可复算；分级明细见 §2.1）：

| 等级 | 条数 | 占比 | 含义 |
|---|---|---|---|
| **A** 可复现（逐位） | **43** | 47.8% | 原始工件重算一致 |
| **B** 可复现但口径需限定 | **11** | 12.2% | 数值对，但分母/子集/独立性有隐藏问题 |
| **C** 部分可复现 / 标注偏差 | **12** | 13.3% | 数值或文字标注有可指认偏差 |
| **D** 不可复现 / 定性冲突 | **7** | 7.8% | 与工件直接冲突 |
| **E** 无法溯源 / 无法验证 | **17** | 18.9% | 无工件、无字段或环境不可测 |
| 合计 | **90** | 100% | — |

> 计数命令（可复算）：
> `python3 -c "import re,collections;t=open('audit_2026/T_A_claims_traceability.md',encoding='utf-8').read();r=re.findall(r'^\|\s*(?:T|S|C|Q|B|M)-\d+\s*\|(.*)\|\s*$',t,re.M);print(collections.Counter(re.fullmatch(r'\*\*([ABCDE])\*\*',[x.strip() for x in l.split('|')][-1].strip()).group(1) for l in r))"`

#### A.2.1 逐条分级明细（供 Lead 抽查）

| 编号 | 等级 | 编号 | 等级 | 编号 | 等级 | 编号 | 等级 | 编号 | 等级 |
|---|---|---|---|---|---|---|---|---|---|
| T-01 | D | T-02 | D | T-03 | D | T-04 | A | T-05 | A |
| T-06 | C | T-07 | E | S-01 | A | S-02 | A | S-03 | D |
| S-04 | A | C-01 | E | C-02 | E | C-03 | E | C-04 | E |
| Q-01 | B | Q-02 | B | Q-03 | B | Q-04 | A | Q-05 | A |
| Q-06 | A | Q-07 | B | Q-08 | B | Q-09 | B | Q-10 | B |
| Q-11 | A | Q-12 | C | Q-13 | A | B-01 | A | B-02 | A |
| B-03 | A | B-04 | A | B-05 | A | B-06 | A | B-07 | A |
| B-08 | A | B-09 | A | B-10 | E | B-11 | A | B-12 | A |
| B-13 | A | B-14 | A | B-15 | C | B-16 | A | B-17 | A |
| B-18 | A | B-19 | A | B-20 | C | B-21 | A | B-22 | B |
| B-23 | A | B-24 | A | B-25 | C | B-26 | A | B-27 | E |
| B-28 | A | B-29 | C | B-30 | A | B-31 | A | B-32 | A |
| B-33 | A | B-34 | A | B-35 | B | B-36 | A | B-37 | A |
| B-38 | B | B-39 | E | B-40 | E | B-41 | E | B-42 | A |
| B-43 | A | B-44 | A | B-45 | C | B-46 | C | B-47 | A |
| B-48 | E | B-49 | E | B-50 | B | B-51 | D | B-52 | D |
| B-53 | C | B-54 | D | B-55 | C | B-56 | E | M-01 | E |
| M-02 | E | M-03 | E | M-04 | E | M-05 | C | M-06 | C |

**关键结论**：项目**核心实验数字**（detection 38/240、117/261、4/261；repair 57/145、58/106；$/task 0.0259/0.0034/0.0045；E4 17/37、37/40、31/37；E6 8/87、30/87；A1/RT1/D1 全部过程指标）**逐位可复现**，我未发现任何被凭空编造的实验数值。问题集中在**当前状态类声明（tests/static）**、**指标可得性声明**、**"四批次"伪重复**、**SWE-bench 定性**，以及**记账完整性**。

---

### A.3 关键机制性主张交叉检验（task-1 第 4 项）

### (a) detection aitester 15.8% vs plain_llm_df 44.8%（−28pp）—— **成立（A）**
- 复算：`38/240 = 15.83%`、`117/261 = 44.83%`、`4/261 = 1.53%`；与声明逐位一致。
- 配对：aitester vs df 共 240 任务，不一致对 **92**（12/80），McNemar χ²(cc)=**48.793**，精确二项 p≈0；Dirichlet 后验均值 δ=**−0.2787**（CI 见声明，未复算 MC 部分）。
- **限定**：分母不同源（aitester 240 vs df 261）——项目已在 BASELINE 显式披露 21 行 None，属诚实披露；如实披露这一点值得肯定。
- "−28pp" 是**贝叶斯后验均值**（−27.87pp）而非朴素差（−28.99pp），两者都约等于 −28pp，不构成误导。

### (b) 非特异过红机制（specific_red 40 / over_red 66 vs df 162/140）—— **可重算，但合计口径双重计数（B）**
- 逐行重算 4 个 10-07 批次的 `specificity_gate_verdict`：aitester `9+11+9+11=40` / `18+15+18+15=66`；df `38+43+38+43=162` / `38+32+38+32=140`。**声明值逐位正确**。
- **但**：批次 `161053`(seed42) 与 `181638`(seed42) 的 87 行 `detection_rate`、`specificity_gate_verdict`、`generated_test` **逐行完全相同**（87/87）；`170147`(seed44) 与 `185941`(seed44) 同样（87/87）。二者 git_sha 不同（`d3c3cc4e` → `1a5a5a79`）、cache namespace 相同（seed42/seed44）。
- ⇒ "跨批次合计" 的 n 被**系统性放大 2 倍**；比值 0.61 vs 1.16 仍成立（比值不受放大影响），但**样本量与统计功效的所有引用都会失真**（见 D-02）。

### (c) repair 39.31%（57/145）与 QuixBugs repair 92.5% —— **39.31% 成立；92.5% 数值可复算但口径内部自相矛盾（A / C）**
- **39.31%**：我独立重放 main_batch 全部 10 个批次、669 行（零 LLM，复用项目 `replay_row`，单行 <1s，200.4s 跑完）：R-P0-2 可重放 **145**、correct **57** → **0.3931**；E1/E2 可重放 **106**、correct **58** → **0.5472**；早期 **15/0** → 0.0000；裁决分布 `correct 115 / wrong_patch 151 / skipped_no_material 403`，与库内报告 `correct 115 / wrong_patch 151 / skipped_no_material 8 / no_patch 395` **完全同构**（403 = 8 + 395）。
- **分母构造**：145 = 三个 20261006 批次中 `patch` 字段非空的函数行数（54+46+45）。剔除规则在 `experiments/corrected_metrics.py:72-76`（无 patch → `no_patch`，出分母）与 `experiments/repair_replay.py:77-83`（有 patch 但 `task_metadata.test_cases` 空 → `skipped_no_material`；diff 形态 → `not_replayable_diff`；超时 → `unverifiable`，三者均出分母）；`analyze_arm` 在 `corrected_metrics.py:120-124` 把 `correct + wrong_patch` 作为"可重放"分母。E1/E2 的 106 与早期的 15（另有 8 行有 patch 无 gold 材料被剔除）同样如此。
- **两者口径差异**：（i）语料不同——R-P0-2 是合成单文件集、E4 是 QuixBugs 真实程序；（ii）**分子分母口径不同**——39.31% 的分母是"进了修复循环且产出补丁的可重放行"，E4 92.5% 的分母是"gold 判分非 None 的行"（40），且其分子同时要求 `patch_correct=1`；（iii）**独立裁决强度不同**——39.31% 由 `corrected_metrics` 事后重放（判分树=项目自实现），92.5% 直接读行内 `repair_rate` 字段。
- **92.5% 的严重限定**：FIXED harness 50 行中 **13 行 `patch_correct=1` 且 `patch_plausible=0`**（另 2 行反向），全部 `source_patched_unverified=True`、`patch_evidence_level='none'`、`stop_reason='skip_debugger_repair_invalid'`、`false_fix_rate=0.0`、`passed=False`。若把"写盘通道"也作为必要条件，则 repair = **24/40 = 60%**；若按全部 50 任务计 = **74%**。**32.5pp 的差距完全由这 13 行双通道冲突产生**（缺陷 D-05）。

### (d) SWE-bench Lite 0/20 —— **原始记录存在，但为"判定之前"的失败；"负结果"表述不成立（D）**
- 原始记录：`experiments/results/swe_bench_lite_20/benchmark_swe_bench_20260818_113525.json` 存在，20 行，`passed_count=0`。
- **不是检测测量**：该工件行只有 9 个键，**无 `detection_rate`**；全部 365 行 swe_bench/swe_bench_pro 工件均无该键（0/365）。
- **harness 无效的直接证据**：(1) 20/20 行 `repo='unknown'`（连仓库名都没解析出来）；(2) 无 `generated_test`/`patch` 落盘（0/20）；(3) `error_category` = syntax 19 + timeout 1，`diagnosis` 文本显示喂进去的"被测代码"是**描述性文本**（如"包含了一个无效的 decimal literal…这是一段描述性文本，不应该出现在 Python 代码文件中"）；(4) 上游数据缓存 `~/.cache/aitester/swe_bench/swe_bench_instances.jsonl` **225 行中 0 行有 `instance_code` 字段**（我逐行解析确认，无该键），即系统从未拿到源码；(5) 同名实验的兄弟日志 `experiments/results/swebench_20_run.log` 含 **7 条 403 insufficient_quota**（qwen-plus 免费额度耗尽）与 `swebench_20_summary.json`（2026-08-17）自述 "All 7 completed tasks failed due to API rate limiting (429 errors)"。
- **结论**：`0/20` 是"未评测/评测管道无效"的记录，**不能作为系统能力的负结果**；README 把它表述为"负结果如实披露"属于**定性错误**（同一 README 的另一处又承认"受 API 限流影响，结果未归档"，两处互相矛盾，见 B-52）。
- 附带：Sep-25 三批 repo 已正确解析（`sqlfluff/sqlfluff`），但 aitester 仍 0/20 且失败在 `patch_validation_failed`（补丁未通过静态守卫）——同样是**判定之前**；plain_llm/single_agent 臂 `error_category` 为空串或 `execution_trace_missing`，说明这些臂**没有可用遥测**。因此"LLM 引擎修复质量边界"的定性（B-53）在我可见的行级数据中无法证实。

### (e) $/task 0.0259 vs 0.0045 的 token 记账完整性 —— **计算正确，但记账不完整（A + D-04）**
- 计算链可逐位复现：`price_table.json`（deepseek-flash 输入 $0.3/Mtok、输出 $1.2/Mtok，source=官方价目页） × 三批 `token_metrics`（in 1,581,326 / out 5,234,651 for aitester 等） ÷ 261 → **0.02590 / 0.00345 / 0.00455**。
- **完整性缺陷**：(1) 缓存命中不计 token（D2，`src/agents/base_agent.py:383-395`、`:437`）——我实测 `total_tokens==0` 行数：R-P0-2 三批（热缓存）aitester **0/261**、plain_llm **0/261**、df **35/261**；E1/E2 四批（热缓存）plain_llm **348/348**、df **348/348**（两臂 token 总量为 0，完全无法计价）、aitester 121/348；E6 control plain_llm/df 各 **87/87**；冷缓存批次（E6 phase1）三臂 **0/87**。⇒ **df/plain_llm 的 $/task 系统性偏低（下界）**，aitester 贵 5.75× 的比值被高估（真实比值应更小）；R-P0-2 恰是污染最小的一批（df 仅 35/261 行为 0），故 0.0259/0.0045 本身可复算，但同族数字在 10-07 批次上**不可复算**。
- (2) 价目表为"峰时全额"，缓存命中价（$0.006/M）与错峰半价均未计入——项目已在 `price_table.json._comment` 中如实声明为保守上界，属**已披露**的口径选择。
- (3) 分母是任务数 261（含 21 行 detection=None 的死亡任务），其 token 也计入——口径本身自洽（成本按任务摊），但与 detection 的有效分母不同源，跨表引用易误读。

---

### A.4 端到端（全任务）修复率 —— 回答"39.31% 与 261 的分母关系"（Lead 交叉核对第 3 项）

同源重放（`replay_row`）后按不同分母计算：

| 口径 | 分子 | 分母 | 结果 | 说明 |
|---|---|---|---|---|
| 条件修复率（对外口径） | 57 | 145（产出补丁且可重放） | **39.31%** | 声明口径；排除 116 行"无补丁" |
| **全任务端到端（R-P0-2）** | 57 | **261** | **21.84%** | 含 116 行根本没产出补丁 |
| 全任务端到端（E1/E2） | 58 | 348 | 16.67% | — |
| 全任务端到端（10-06/10-07 七批） | 115 | 609 | 18.88% | — |
| 全任务端到端（main_batch 全 10 批） | 115 | 669 | 17.19% | 与修正报告的 115/669 行级分布一致 |
| **含"零修复尝试"的诚实分解** | 296/609 = **48.6%** 的 aitester 行是 `all_green_unverified` + `iterations=0` + 无补丁 | 609 | — | 这些行被记 `repair=0`；它们不是"修错了"，而是**从未进入修复通道** |

要点：**39.31% 与 261 不是同一分母**。39.31% 是"补丁产出条件下的成功率"，无条件端到端约 **17–22%**。对外引用 39.31% 时必须同时给出 145 的构成（否则读者会误以为 261 任务里有四成被修好）。项目 README 已写"57/145 可重放行"，属**已披露**，但同句未给全任务分母，易被误读为 261 口径。另注：BASELINE 引用的 `repair_ceiling_report.md` 漏斗（154/261→145→72→57，即 94.2%/46.8%/39.31%）中**每一个分子分母我都独立复算一致**（该报告原文本身未读，仅核 BASELINE 转述与其所称工件）。

---

### A.5 新发现的缺陷 / 测量伪影（既有评审未记录或未量化）

> 每条附"零 LLM 复现命令"。**D-01/D-02/D-03/D-05 是我认为最重要的四条。**

### D-01 【严重】孤儿 pytest 进程仍在烧 CPU，且机制已定位到未修复的代码路径
- 证据（我实测）：`ps -o pid,ppid,pcpu,etime -p 36935,37116` →
  `36935 ppid=1 97.6%CPU etime=16:31:25`、`37116 ppid=1 96.3%CPU etime=16:30:18`；命令行分别为 `aitester_m1_bitcount_.../test_bitcount.py`、`aitester_m1_find_first_in_sorted_.../test_find_first_in_sorted.py`。
- 代码依据：`experiments/_m1_metrics.py:358-372` 的 `subprocess.run(..., timeout=timeout)` **没有 `start_new_session=True`**，超时只杀直接子进程 → 孙进程被 launchd 收养（ppid=1）并永久持有管道。项目已修 `branch_coverage_inject`（`src/utils/process_utils.py::run_with_timeout`）但**未接到 M1 判分路径**。
- 影响：单机 2 核被占 >16 小时；我的全量 pytest（223s）与 xdist（82s）耗时均受此污染；任何在病态 QuixBugs 任务上跑的批次都会持续累积孤儿。
- 零 LLM 复现：`ps -o pid,ppid,pcpu,etime -p $(pgrep -f aitester_m1 | paste -sd, -)`；`grep -n "subprocess.run" -A 16 experiments/_m1_metrics.py`
- 处置建议（供 Lead）：不要擅自 kill（它们是缺陷的活证据，且可能是别的会话的产物）；登记为 P0 并给 `_run_pytest_in_tmp` 换 `run_with_timeout`。

### D-02 【严重】E1/E2"四批次"是伪重复：2 个种子 × 2 次重跑，跨批合计放大 2 倍
- 证据：`benchmark_synthetic_20261007_161053.json`(seed42) 与 `_181638.json`(seed42) 对全部 3 臂 **87/87 行** `detection_rate`、`specificity_gate_verdict`、`generated_test` **逐行相同**；`_170147`(seed44) 与 `_185941`(seed44) 同样。批次均值在所有 target_quality 指标上也逐位相同（cov 86.4138/90.6322、mut 0.8585/0.8175、spec 0.2045/0.2189、expr 0.7415/0.7232）。
- 影响面：`specificity_gate` 合计（40/66、162/140）、`repair 58/106`、`spec_compile_rate [0.205,0.219] n=77/81`、`spec_expr_coverage n=45/51` 全部按"4 批"计数；独立实验单位实际只有 **2 个**。
- 代码侧的自我矛盾：`src/agents/base_agent.py:383-386` 注释明确承认"同 seed 复跑仍共享缓存 ⇒ 统计独立性失效"，但 BASELINE 仍把同 seed 重跑算作独立批次。
- 零 LLM 复现：`P12`（逐行比对脚本）。
- 建议：把 4 批折成 2 个独立单位重报区间/合计，或在文档中显式标注"重跑非独立重复"。

### D-03 【高】当前树"全绿"声明失效：全量 2 failed，且两个失败都指向基线自身失真
- `2 failed, 5311 passed, 3 skipped, 1 xfailed in 223.21s`（xdist -n4：82.28s，同样 2 failed）。
- `TestBaselineNumbersConsistency::test_tests_and_mypy_are_current`：断言消息 `实收 5317 − passed 5262 = 55 > 9（BASELINE 数字可能已过期，请跑全量 pytest 后刷新）`——**项目自己的守卫否定 BASELINE**。
- `TestEnvSnapshotCompleteness::test_gate_reports_no_missing`：`scripts/gates/check_env_snapshot_keys.py` exit 1，缺失 3 键（见 D-07）。
- 时间线证据：BASELINE.yaml mtime **10-10 22:43**，而 `tests/` 下 8 个文件 mtime **10-10 23:04–23:30**（晚于基线落盘）⇒ "5262" 在其写下的时刻可能成立，但**当前修订不可复现**，且**未按 `last_verified` 流程刷新**。
- 零 LLM 复现：`P01`、`P02`。

### D-04 【高】token 记账不完整污染成本结论（污染面已量化）
- 我实测的 `total_tokens==0` 行数（`P13`）：
  - R-P0-2 三批（热缓存）：aitester **0/261**、plain_llm **0/261**、**df 35/261**（=8+13+14，与工件逐批一致）。
  - E1/E2 四批（热缓存）：aitester **121/348**、plain_llm **348/348**、df **348/348**；且 plain_llm/df 两臂 `token_metrics.total_tokens` 均为 **0** —— 这两批**完全无法计价**。
  - E6 control（热缓存）：plain_llm **87/87**、df **87/87**、aitester 50/87。
  - E6 phase1（冷缓存）：三臂 **0/87** —— 说明该缺陷与缓存开关**严格同现**，机制定位成立。
- 含义：`$/task` 的 df/plain_llm 值是**下界**（少算了缓存命中的真实计费），"aitester 贵 5.75×" 被系统性高估；R-P0-2 的主成本数字（0.0259 vs 0.0045）恰好落在**污染最小**的一批（df 仅 35/261 行为 0），但同族结论在 10-07 批次上**不可复算**。E4 的 "8.4×" 同源问题（df 1905 亦为缓存复用后均值）。
- 零 LLM 复现：`P13` = `audit_2026/a28_zerotok.py`。

### D-05 【高】`patch_correct=1` 与 `patch_plausible=0` 共 129 行并存 → `patch_precision` 聚合值可 >1
- 全库扫描（`P14`）：**129 行**同时满足 `patch_correct==1 ∧ patch_plausible==0`，逐文件：`e4_quixbugs_FIXED_harness/aitester.json` **13**、`ablation_r9/over_red_section_verified.json` **13**、`ablation_r9/over_red_section_firstrun_NOTVERIFIABLE.json` **13**、`ablation_r9/a1_strip_fixedharness.json` **12**、`e4_quixbugs_aitester` **11**、`llm_logic_ab_*/c2 8`、`c1 7`、`_superseded` 三批 **26**、`r4_batches` 三批 **13**、其余 6 个文件共 **13**（a1_strip_seed42 4 / d1 2 / diagnostic_12task 3 / e6_control 2 / e6_phase1 2）。反向（`plausible=1 ∧ correct=0`）在 FIXED harness 有 **2** 行。
- 定义依据：`experiments/run_benchmark.py:602-618` `_patch_plausible` 只看 `final_state["repair_history"][-1]["patch_applied"]`（**最后一条**修复历史），而 `:621-635` `_patch_correct` 走 gold 独立裁决；`_patch_precision`（`:638-643`）= correct/plausible，隐含 `correct ⊆ plausible`，但数据违反该不变量。
- 连带伪影：`review_2026/E2_fence_recompute.json` 的 `groups_summary.e6_a1_batches.precision_original = 1.0648`（**precision > 1**，不可能值）——正是 Σcorrect(263)/Σplausible(247) 这种跨口径聚合的产物。
- 影响：E4 的 92.5% 与 60% 相差 32.5pp；`patch_precision` 在 13 行被迫为 None（分母 0），"过拟合度量"实际覆盖不全。
- **定性（回答 Lead 第 5 项）：属记账缺陷，不是口径定义差异。** 判据三条：(1) 项目自己在 `experiments/run_benchmark.py:1114-1120` 把 `patch_precision` 定义为 `correct / plausible` 并声明"无 plausible 时 None"，该定义**隐含 `correct ⊆ plausible` 不变量**，数据违反它；(2) `patch_plausible` 的取值来源 `final_state["repair_history"][-1]["patch_applied"]` **从未落盘**——我扫描全库 **7153 行，`repair_history` 键出现 0 次**，故该字段无法从任何工件复核，只能信任单一写盘点；(3) 13 行同时是 `source_patched_unverified=True` + `patch_evidence_level='none'` + `passed=False` + `repair_rate=1.0`，即"未被证实写入源码"却"被判定修复成功"，两个通道给出相反结论而工件没有任何仲裁字段。三者叠加只能是记账口径未对齐，而非有意设计的两套口径。
- 零 LLM 复现：`P14`。

### D-06 【中】被声明的指标从未落盘（schema 声明 ≠ 实际可得）
- `patch_rollback_verdict` / `patch_rolled_back`：**0/7153 行**出现（键都不存在）。
- `regression_rate`：3968 行有键，**非 None 0 行**；`red_regression_violation`：2997 行有键，**非 None 0 行**；`deterministic_repair_status`：1891 行有键，**非 None 0 行**。
- `fl_at_k` 仅 11.0% 行有值；`spec_oracle_injected` 仅 120/7153（1.7%）。
- 影响：任何"观测层已落地"的表述缺少行级证据；引用这些指标时读者会以为可得。
- 零 LLM 复现：`P15`。

### D-07 【中】env_snapshot 门禁复发（与 A1 假阴性同类）
- `scripts/gates/check_env_snapshot_keys.py` → 扫描 122 文件、开关全集 78、快照 99 键、覆盖 75、**缺失 3**：`EMPTY_PLAN_SHORTCUT_ENABLE`、`OPERATION_MAP_INJECT_ENABLE`、`PATH_ENUM_INJECT_ENABLE`（均定义于 `src/graph/nodes.py`），exit 1。
- 讽刺点：锁定该事故的测试 `test_key_incident_switches_registered` 只检查 6 个**具名探针**，所以**通过**；而真正扫描全量的门禁**失败**——门禁与测试口径不一致。
- 影响：这 3 个新开关的干预生效性不可审计，正是 A1（PLAN_STRIP 未生效却记"零效应"）与 D3（OVER_RED 未入快照）**同一类事故的第三次复发**。
- 零 LLM 复现：`P16`。

### D-08 【中】`repair_replay.build_report` 的"带补丁行"列是行数而非补丁数（误导性表头）
- `experiments/repair_replay.py:156-159` 把单元格值算成 `replayed + not_replayable_diff + skipped_no_material` = **该批次总行数**，而表头写"带补丁行"。
- 实证：`python -m experiments.repair_replay experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester` 会输出"带补丁 87 行"，而该批真实带补丁行只有 **54**（其余 33 行是空 patch）。本团队 Lead 的交叉核对消息即据此写下"带补丁 87 行"，属**已被该表头误导的实际案例**。
- 影响：任何按该报告核对分母的人都会算错（这也是 `corrected_report_v2.md` 用另一种口径的正确原因）。
- 零 LLM 复现：`P17`。

### D-09 【中】stop_reason 遥测只覆盖编排臂，跨臂比较结构上不可比
- R-P0-2：`stop_reason='unknown'` 占比 aitester **8.0%（21 行 None）**、plain_llm **12.3%**、plain_llm_df **97.3%**；E1/E2 类似（9.2/12.1/97.7%）；E4 QuixBugs df 臂 **50/50 = 100% unknown**。
- 影响：任何"两臂 stop_reason 分布不同"的推论都不成立；E6 phase2 的 `budget_exceeded 84` 只对 aitester 有意义（df 臂 39/87 仍是 unknown，仅靠 `token_budget_capped` 标志可判）。
- 零 LLM 复现：`P18`。

### D-10 【低-中】文档引用的测试例数与当前树不符
- `test_process_utils.py` 收集 **13**（声明 12）；`test_over_red_section.py` 收集 **23**（声明 21）；`TestDualLayout` 收集 **5**（声明 5 ✓）。
- 影响：轻微；但"12 个单元测试"是 hang 修复的验收证据之一，应刷新。
- 零 LLM 复现：`P19`。

### D-11 【低】密钥泄漏守卫误报且当前阻断
- `.git-hooks/check_secret_leak.sh` exit **1**，命中物为 40 位 git SHA（`review_2026/E2_fence_recompute.json` 的 `provenance_git_sha`、`experiments/run_payload_ab.py` 的 sha256）与文档正文（`--per-task-token-caps` 等），全部**误报**；被扫文件主要为 untracked 的审查产物。
- 未发现任何真实密钥进入 git：`.env`、`.env.local`、`.private/` 均被 `.gitignore` 覆盖（`git check-ignore -v` 逐项确认）；`llm_configs.json`（tracked）经字段扫描无密钥材料。
- 风险提示（不粘贴明文）：工作树 `.env.local` 与 `.private/.env.local` **各含一份非空 API Key**（本地磁盘明文，未入库）。
- 零 LLM 复现：`P20`。

### D-12 【低】`ruff check .`/`ruff format --check .` 当前为红——但**起因是本审计自身**的 `audit_2026/` 目录
- `ruff check .` → 341 errors，**全部**落在 `audit_2026/*.py`（我的临时脚本，29 个文件）；`--extend-exclude audit_2026` 后 **All checks passed**、`591 files already formatted`。
- 我的处理：不改项目配置（越权），如实登记。若项目后续要在 clean tree 上跑 `ruff check .`，请把 `audit_2026/` 加入 `[tool.ruff] extend-exclude` 或由我清理脚本。
- 零 LLM 复现：`P21`。

---

### A.6 "无法验证 / 无法溯源"声明清单（等级 E）

1. `tests.slim_environment=1863`（需精简依赖环境，未测）。
2. `coverage.line_total_pct=89` / `branch_total_pct=83` / 10 个核心模块行覆盖 / 3 个核心路由分支覆盖（需 `--cov` 全量跑批；仓库 `.coverage` 仅含 1 个被测文件，已退化）。
3. v1 修正口径 `35.86% (52/145)` / `48.11% (51/106)`（旧判分路径已被修复取代）。
4. 第四起伪影的零 LLM 证据 "9/9 双 rc=2"、"F2P 0/7→6/7"（`diagnostic_12task_prerepair.json` 无 rc 列，且无 9/7 任务工件）。
5. `spec_oracle_injected` 合成 2–3/87、QuixBugs 20/50（声明批次内该字段全为 None/False；命中只出现在 10-10 的另一族批次）。
6. S6 通道注入率 0/2→1/2、子句 3/5（无工件/日志）。
7. RT1 开关 `DETECTION_FIRST_SECTION_ENABLE` 的实际取值（不在该批 `env_snapshot`）。
8. D1 的 "427/621→555/621" 与 "空计划 34/87→22/87"（无缓存响应工件、无空计划字段）。
9. `patch_rollback_verdict` / `patch_rolled_back` / `regression_rate` / `red_regression_violation` / `deterministic_repair_status` 的**取值**（键存在或不存在，但全库 0 个非 None 值）。
10. 历史 CI 声明 `ci_gates_2026_10_09: full_suite 5107 passed`、`guards 10/10 exit 0`（无法回验历史提交时点；当前树门禁为红）。

---

### A.7 我实际执行的命令（可复算清单）

所有脚本位于 `audit_2026/`，只读解析 + 零 LLM。

| 简写 | 命令 | 用途 |
|---|---|---|
| P00 | `.venv/bin/python audit_2026/a01_main3seed.py` | 三批逐臂 detection/repair 计数 |
| P01 | `.venv/bin/python -m pytest tests/ -q --collect-only` | 收集数 = **5317** |
| P02 | `.venv/bin/python -m pytest tests/ -q --tb=line -p no:cacheprovider --basetemp=/tmp/aitester_audit_bt_20261011` | 全量 = **2 failed, 5311 passed, 3 skipped, 1 xfailed, 223.21s** |
| P03 | `.venv/bin/python -m pytest tests/ -q -n 4 -p no:cacheprovider --basetemp=/tmp/aitester_audit_bt_xdist` | xdist = **82.28s**，同为 2 failed |
| P04 | `.venv/bin/python -m mypy src/ config.py` | **123 source files, 0 errors** |
| P05 | `.venv/bin/ruff check . --extend-exclude audit_2026` / `ruff format --check . --extend-exclude audit_2026` | 全绿 / 591 files formatted |
| P06 | `audit_2026/a03_pooled261.py` | 261 行合并 detection + 配对 δ/χ² |
| P07 | `audit_2026/a05_cost.py` | 价目表 × token_metrics → $/task |
| P08 | `audit_2026/a04_specgate.py` | 全库 specificity_gate 分布 |
| P09 | `audit_2026/a07_quixbugs.py`、`a08_tokens.py`、`a09_e4denom.py` | E4 双臂/三种分母复算 |
| P10 | `audit_2026/a15_pairs.py`、`a26_e4deep.py` | E6/E4 全部 McNemar 复算（含 scipy 渐近 p） |
| P11 | `audit_2026/a23_replay_full.py`（200.4s） | **独立全量重放**：57/145、58/106、115/151/403 |
| P12 | `audit_2026/a12_dupruns.py` | 10-07 四批逐行同一性（伪重复证据） |
| P13 | `audit_2026/a28_zerotok.py` | `total_tokens==0` 行污染面（热/冷缓存对照） |
| P14 | `audit_2026/a17_precision.py`、`a18_consistency.py` | `correct=1 ∧ plausible=0` 129 行 |
| P15 | `audit_2026/a29_schema.py` | metrics_schema 逐键 present/non-None 计数 |
| P16 | `.venv/bin/python scripts/gates/check_env_snapshot_keys.py` | exit 1，缺 3 键 |
| P17 | `.venv/bin/python -m experiments.repair_replay experiments/results/main_batch/benchmark_synthetic_20261006_140906.json --arm aitester` | "带补丁行 87" 误导列 |
| P18 | `audit_2026/a19_stop.py` | stop_reason 分臂分布 |
| P19 | `.venv/bin/python -m pytest tests/test_process_utils.py -q --collect-only` 等 | 13 / 23 / 5 例 |
| P20 | `bash .git-hooks/check_secret_leak.sh; git check-ignore -v .env .env.local .private` | exit 1（误报）+ 忽略状态 |
| P21 | `.venv/bin/ruff check .` | 341 errors（全在 audit_2026/） |
| P22 | `audit_2026/a24_swe_census.py` | 365 行 SWE 普查（0 detection_rate、100% 无 instance_code） |
| P23 | `ps -o pid,ppid,pcpu,etime -p 36935,37116` | 孤儿进程 16.5h |
| P24 | `.venv/bin/python -m experiments.corrected_metrics experiments/results/main_batch --arm aitester` | 同源重生成修正报告（与库内 v2 对照，见 §8） |

---

### A.8 同源重生成对照（corrected_report_v2.md）—— **正文逐字节一致**

我重跑 `experiments.corrected_metrics experiments/results/main_batch --arm aitester`（零 LLM，全量 669 行重放），与库内 `experiments/results/main_batch/corrected_report_v2.md` 逐节比对：

- **正文（"- 目录：" 起至 "*报告生成：" 前）逐字节相同**：`body equal: True`（各 1659 字符）。差异仅在文件头：v2 多出一段 "ADR-0029 / R27 后重生成" 的前言块 + 标题后缀 `v2`。
- 关键数字（库内 = 我重跑）：
  - 行级裁决 `{'skipped_no_material': 8, 'no_patch': 395, 'wrong_patch': 151, 'correct': 115}` —— 一致；我另证 403 = 395（无 patch）+ 8（有 patch 无 gold 材料）。
  - 分代际 repair：E1/E2 `106/106/58 → 0.5472`、R-P0-2 `145/145/57 → 0.3931`、早期 `15/15/0 → 0.0000` —— 逐位一致。
  - §2 false_fix：passed 可测 **436**、false_fix **380** → **0.8716** —— 逐位一致（我另分解：332 行为 `no_patch`、48 行为 `wrong_patch`）。
  - §3：plausible **144**、IDR **0.3485**、CPR **0.8451（60/71）**、弃权拦截面 **0.7847**、passed 压制 **392/443**、弃权精确率 **0.8597** —— 全部由我独立重跑复现（同源脚本 + 同源工件）。
- 结论：`corrected_report_v2.md` 的数字链**完全可复现**，且其"不可重放行降级为 None、不臆造"的设计经我核验属实。**这是本项目数据纪律最好的一环。**

---

### A.9 明确标注为"项目自报、我未独立验证"的数字

以下为项目自评但本审计**未能独立验证**（除 §6 清单外，还包括）：

- 全部**外部文献引用**（CANDOR/TOSEM 2026、TestAgent/FSE 2026、ICST 2026 复现、IEEE 11655121、BOAD/ICLR 2026 等）的 DOI/数值——本次审计不涉及文献核查。
- 覆盖率 ratchet 水位（89.5 / 82.5）、门槛（85%/77%）、门禁脚本 10/10 绿。
- `mutation_score` 的**变异体生成正确性**（我复算了分数分布，未验证变异算子实现的正确性——属 code-auditor 范围）。
- `fl_at_k`、`llm_localization`、`localization_hit_function*` 的**语义正确性**（我核了非空率与取值，未核其与 gold 函数集合的比对实现）。
- `pre-commit`/CI 门禁矩阵在 3.12/3.13/3.14 的实际执行结果（本机仅 3.14）。
- E4 的 wallclock（21m07s / 8m15s / 37 分钟）——日志有时间戳但非结构化汇总，未精确复算。
- E6 matched 的 `bh_q`、`sign_test p`、聚类校正 χ²_adj（依赖模板簇结构，未复现）。
- `repair_ceiling_report.md` 的 bug_type 分层解混杂表（需 `fl_hit_value` 与 gold 变更函数集合，未复现）。
- 2026-10-01 `false_fix=89.8%` 历史值（该批 `detection_rate`/`repair_rate` 大量为 None，仅 49 行可判；未逐行复算 false_fix）。

---

### A.10 判定摘要（一句话版）

1. **核心实验数字可复现**：detection 38/240、117/261、4/261；repair 57/145、58/106；$/task 0.0259/0.0034/0.0045；E4 17/37、37/40、31/37；E6 8/87、30/87；A1/RT1/D1 过程指标——**我逐位复算一致，无编造痕迹**（A 级 43/90）。
2. **当前状态类声明失真**：`5262 passed / 0 failed`、`collect 5259`、`mypy 120 文件` 均与当前树不符（实测 5311+2F / 5317 / 123），且**项目自带守卫已红**（D-03）。
3. **伪重复**：E1/E2"四批次"实为 2 个独立单位 × 2 次缓存重跑，所有跨批合计（含 specificity_gate 与 repair 58/106）n 放大 2 倍（D-02）。
4. **SWE-bench 0/20 不是负结果**：0/365 行有 detection_rate，100% 实例无源码字段，Aug-18 批 repo=unknown 且日志有配额耗尽；README 两处自相矛盾（B-51/B-52）。
5. **记账缺陷影响对外数字的强度**：token 记账漏计缓存（D-04）、`patch_correct`/`patch_plausible` 双通道冲突 129 行使 92.5% 与 60% 相差 32.5pp（D-05）、若干声明指标从未落盘（D-06）、env 快照门禁第三次复发（D-07）。
6. **未见证据表明数据被伪造**；问题集中在**口径披露、伪重复、指标可得性与当前树状态刷新**。



---

## 附录 B｜Python 与领域机制独立代码审查

> 源文件：`audit_2026/T_B_code_domain_audit.md`（本附录为该文件的完整内容，仅调整标题层级与编号）

### B·T-B：Python 与领域机制独立代码审查（AITester）

- 审查对象：`/Users/wangchenyu/Workspace/AITester`，工作树 = HEAD `d9e51df`（2026-10-10 16:28）+ 33 个已修改文件（+1619/−252）+ 25 个未跟踪项（`git status` 实测）。
- 审查方式：直接读代码。项目 README / docs / ADR / 既有评审仅作为"声称"的出处引用，不作为事实来源。所有结论附 `file:line`，均为本次实际打开读到的位置。
- 行号基准：**当前工作树**（非产出批次工件的提交），引用批次工件时另行标注。
- 只跑了只读命令与一个临时复现脚本（`audit_2026/_probe_gate_vs_metric.py`）；未调用任何 LLM，未修改项目任何文件。
- 标注约定：`[实测]` = 本次运行得到的输出；`[读码]` = 代码逐行判读；`[静态推断]` = 由代码路径推导但未执行验证；`未验证` = 无法从代码或实测定论。

---

### B.0 五个指定判定的明确结论（速览）

| 判定 | 结论 | 一句话证据 |
|---|---|---|
| (a) `specific_red`/`over_red` 判定 & 检出率是否计入非特异断言 | **过红不计入检出**；但"非特异"若指"断言不针对缺陷语义、只是碰巧区分两版代码"则**会计入**（无任何断言特异性校验）。**84–94% 覆盖 vs 15.8% 检出主要由"执行覆盖 ≠ 判别力"解释**，分母不同构是次要因素。 | `_m1_metrics.py:529-539`（buggy 绿→0；fixed 红→0）；`executor.py:198` + `executor_output.py:38-66`（覆盖率只统计"执行过"） |
| (b) `spec_compile_rate` 分子/分母 & 逻辑表达力 | 分子=可编译非空子句数，分母=非空子句数；expr 通道优先，NL 回退；无材料返回 **0.0 而非 None**。表达力 = **无量词/无函数/无数组/无关系/无时序的标量算术约束**（z3 QF Bool/Int/Real）。SMT **真在求解**，但只求解"前件可行性/边界极值/前件空洞/后件自洽"，**不做**"实现是否满足后件"。 | `spec_ir_v2.py:668-683, 686-719`；`spec_smt.py:322-388`（翻译算子集）、`:14-24`（能力边界自述）、`:459-549`（Solver/Optimize 真调用） |
| (c) 补丁生成 vs 运行时自修复 | **是离线的自动化程序修复（APR）闭环，不是运行时自修复**。无监控/守护/热加载/故障转移组件；"补丁"= 把整份新源码写回被测文件，验证失败再回滚。 | `patch_io.py:351-455`（写盘）、`:458-504`（回滚）；`main.py`+`src/cli/app.py`（只有批量 CLI，无服务模式）；全仓无 watchdog/supervisor/restart（grep 实测） |
| (d) 执行沙箱强度 | **默认（venv 档）只隔离环境变量与 sys.path，不隔离文件系统、不隔离网络**；内核沙箱默认关，且打开时把 `cwd`(=仓库根) 隐式加入可写路径；`runtime_probe` 执行 LLM 测试代码的子进程**完全没有**内核沙箱接入。 | `executor_modes.py:257-286`；`executor.py:177-188, 237-269`；`kernel_sandbox.py:209-211`；`runtime_probe.py:343-353` |
| (e) LLM 输出→exec/eval/subprocess 注入面 | 主进程**无** `eval`/`exec`/`shell=True`/`os.system`；唯一 `exec` 在 `runtime_probe` 的**子进程 runner 模板**内执行 LLM 测试代码。LLM 补丁落地前有"正则 + AST 危险 API 差集"双通道拦截（默认开）；输入侧 prompt 注入检测默认关。 | `runtime_probe.py:251`；`nodes.py:1759-1814`；`injection_guard.py:51-65`；`rogue_monitor.py:37-39` |

---

### B.1 (a) detection-first 协议与特异性门：真实实现

#### B.1.1 三个不同层各自定义"红"，且判据不一致（本次最重要发现）

| 层 | 定义 | 位置 | 对"没跑起来（收集/语法错误）"的处理 |
|---|---|---|---|
| 环路内执行器 | pytest rc==0 即 passed | `executor.py:286`；`executor_modes.py:486` | 收集错误 → passed=False（红） |
| 运行时特异性门（gate） | 在 gold fixed 上跑：绿=`specific_red`，非 0=`over_red` | `detection_gates.py:96-121`（判定在 `:121`） | **无区分**：收集错误 rc=2 → `over_red` |
| 离线 M1 检出指标 | buggy 红 ∧ fixed 绿 ∧ 两侧无收集/语法错误 | `_m1_metrics.py:473-539`（`:529-539` 三段）；错误判据 `:58-81` | 明确排除：→ 0.0 |

`detection_gates.py:82-93` 声称"与 M1 事后裁决完全同一原语，行为口径一致"（`:21-24` 注释），但**只复用了执行函数，没有复用判定函数**：`_run_test_against_code` 只取 `res[0] == 0` 作为 `green`，从不调用 `_looks_like_test_execution_error`。

**本次实测复现**（`audit_2026/_probe_gate_vs_metric.py`，无 LLM）：

```
--- cross_file_import ---
  _run_pytest_in_tmp rc = 2
  _looks_like_test_execution_error = True
  specificity_verdict = over_red
--- syntax_error ---
  _run_pytest_in_tmp rc = 2
  _looks_like_test_execution_error = True
  specificity_verdict = over_red
```

后果链（全部 [读码]）：
1. `over_red` → `workflow.py:707-719` 路由 `regenerate`，不再进修复循环（消耗 `MAX_REGENERATIONS=1`，`config.py:375`）；
2. `over_red` 行不写红证人（`nodes.py:1441-1442`），后续"曾检出"证据链缺失；
3. `over_red` 是弃权门信号之一（`patch_abstain.py:40-46` 第 3 条）；
4. `over_red` 是 CPR/IDR 负信号（`experiments/cpr_idr_report.py:50`）与四通道 R3"fixed 腿"代理（`four_channel_recompute.py:34, 230-232`）；
5. `BASELINE.yaml:75-78` 用 `specific_red/over_red` 比例作为"−28pp 主机制"的证据——该比例**混入了收集错误/未运行**，作为机制归因过强。

**独立佐证（跨文件任务的系统性误判）**：gate 委托时**不传** `task_metadata`（`detection_gates.py:85-87`），而 `_m1_metrics` 显式分派跨文件物化依赖 `task_metadata["is_cross_file"]`（`:330-333`）。跨文件任务的伴生模块（`module_a/b/c`）在单文件布局下不存在 → `ModuleNotFoundError` → rc=2 → **判 `over_red`**（上表 cross_file_import 即此形态）。`[静态推断 + 实测形态复现]`

**该缺口的边界（避免过度声称，工件级约束，详见 §11.4）**：在 7 批主力工件的可执行行上，gate 与 M1 detection **逐位等价**——`specific_red → det=1.0` 为 206/206，`over_red → det=0.0` 为 244/244。分歧**只落在"根本没跑起来"这一格**（两者都输出"非检出"，故工件层无法区分"真过红"与"从未运行"）。因此本条的正确表述是：**判据分叉使 `over_red` 这一标签不可解释（真非特异 / 未运行混在一起），而不是使检出数字本身被高估**。

#### B.1.2 检出率是否把非特异断言计入？

- **过红（在 gold fixed 上也红）→ 不计入**：`_m1_metrics.py:533-536` 直接 `return 0.0`。所以"M1 检出率被过红刷高"不成立。
- **但 M1 检出率不检查断言的"特异性"**：全流程没有把 `oracle_validator.check_assertions`（恒真断言检测）接入 M1 判定。该检测本身默认关（`flags.py:79-87` `ORACLE_VALIDATE_ENABLE` 默认 false；logic/scientific 档才开，`config.py:61,72`），且结果是观测层（`nodes.py:974-1019`，O4 用它触发一次再生成，`nodes.py:1015-1019`）。
- 因此"非特异断言"的两种含义要分开：
  - 含义 A：在无缺陷代码上也失败（over_red）→ **不计入**；
  - 含义 B：断言不编码缺陷语义、只是碰巧区分了 buggy 与 gold fixed（例如断言某个被 gold 补丁顺带改变的实现细节；或 `assert f(x) == <魔法值>` 恰好在 buggy 上不成立）→ **计入**，且无任何静态/规约核对拦截。
- 结论：检出率衡量的是**行为判别力（F2P 三段）**，不是"断言正确性/规约符合度"。把它读成"测试质量"会过度解释；把它读成"这套测试能否区分本次缺陷的两版实现"是准确的。

#### B.1.3 84–94% 覆盖率 vs 15.8% 检出率的解释

三条机制，按贡献排序：

1. **定义差异（主因，[读码]）**：覆盖率来自 `pytest --cov=<target_dir>` 的 TOTAL 行（`executor.py:198`；解析在 `executor_output.py:20,38-66`），**只要求被执行**；检测要求 `buggy_rc != 0 ∧ fixed_rc == 0`（`_m1_metrics.py:529-539`）。测试把被测函数跑一遍、断言恒真或断言与缺陷无关 → 覆盖率可以很高而 `buggy_rc == 0` → 检出 0（`_m1_metrics.py:529-530`）。
2. **分母不同构（次要，[读码]）**：`coverage` 均值分母 = 全部任务（`run_benchmark.py:2674`，缺失按 0），而 detection 分母 = 有 gold 材料且可测的子集（`run_main_batch.py:370-374`；`analyze_results.py:717-745` 逐字段剔除 None）。README 自己的口径是 aitester `38/240` 对 df `117/261`（`README.md:72`）——**两臂分母差 21 行**，代码层没有任何重加权/敏感性校正。`[静态推断]`：分母差异方向（aitester 少 21 行可测）本身不能解释 28pp，但使"15.8%"是条件于可测性的估计。
3. **测量伪影（历史，已被项目自己修复）**：`_m1_metrics.py:157-176` 记录"第四起测量伪影"——判分树只提供包结构布局导致扁平 import 恒 rc=2、detection 构造性为 0；修复为双布局。同类伪影在 `:236-295`（跨文件）、`:125-202`（QuixBugs 辅助模块）各一处。

#### B.1.4 detection-first 协议与特异性门的开关口径

- `config.py:385-414`：`DETECTION_FIRST_ENABLE` **默认 false**；另有线程级覆盖 `set_detection_first_thread_override`（`config.py:403-413`），被 `run_plain_llm_df_baseline` 强制开启（`run_benchmark.py:412-419`）。
- `config.py:104-105`：`DETECTION_SPECIFICITY_GATE_ENABLE` / `RED_REGRESSION_GATE_ENABLE` 只在 `logic` 档注入 true（`_PROFILE_PRESETS`，`config.py:43-115`）。
- 门只在 `iteration==0` 且 `detection_first_enabled()` 时运行（`nodes.py:1423-1438`），因此**非 logic 档批次根本没有 gate 数据**（全为 None）。
- `over_red` 的再生成强化段落默认**关**（`nodes.py:520-527` `OVER_RED_SECTION_ENABLE` 默认 false），即"过红后再生成"在默认口径下只是"用同一份计划再问一次"（`nodes.py:592-597` 自述）。
- `nodes.py:585-600` 的代码注释把 over_red 部分归因于"缺陷代码不终止而挂起"。**与实现不一致**：fixed 侧超时会让 `_run_pytest_in_tmp` 返回 None（`:380-381`）→ `_run_test_against_code` 返回 None → verdict = `unavailable`（`detection_gates.py:119-120`），**不是** `over_red`；而 buggy 挂起 + fixed 正常终止反而会得到 `specific_red`。真正会产出 `over_red` 的"假红"是**收集/导入错误**（见 1.1 实测）。

---

### B.2 (b) 逻辑驱动：`src/specs/*` 的真实表达力与度量定义

#### B.2.1 `spec_compile_rate` 分子/分母（精确）

`spec_ir_v2.py:668-683`：

```
compiled = 0; total = 0
for clauses, kind in ((pre, "precondition"), (post + inv, "postcondition")):
    for clause in clauses:
        if not clause.strip(): continue        # 空串既不入分子也不入分母
        total += 1
        if _clause_is_compilable(clause, kind, known_names): compiled += 1
return compiled / total if total else 0.0      # 无材料 → 0.0（不是 None）
```

- 通道选择 `_select_compile_channels`（`:644-665`）：`*_expr` 三字段中**任一存在 str 子句**即用 expr 通道（含空串，即"通道存在"），否则回退 NL 通道（`preconditions/postconditions/invariants`）；**两通道不合并**。
- 判定门 `_clause_is_compilable`（`spec_ir_v2.py:267-336`）：形态门（字符白名单 `_EXPR_TOKEN_RE`，`:89`）+ AST 白名单（`_whitelist_check`，`:173`）+ 标识符绑定门 + 产物自检。
- 写入点：`nodes.py:421-449`，仅在 `SPEC_IR_DSL_ENABLE=true` 时计算；`logic`/`scientific` 档注入 true（`config.py:57,67`）。**纯观测字段，不参与路由**（`nodes.py:420`）。
- 正交指标 `spec_expr_coverage`（`:722-734`）= `expr 子句数 / max(NL 子句数, expr 子句数)`，无材料 → None。
- 因此 `spec_compile_rate` 的语义是**"LLM 形式化产物被本仓受限 DSL 接受的比例"**，不是"规格覆盖率"，也不是"逻辑驱动贡献度"。

#### B.2.2 表达力上限（逐层 [读码]）

| 层 | 支持 | 不支持 |
|---|---|---|
| SpecExpr DSL | 比较、布尔、算术、常量、白名单调用（`len/abs/min/max/round/float/int/str/sorted/any/all/isinstance`，`:63-68`）、容器下标/长度、白名单属性（`value/real/imag`） | 赋值/语句/控制流（`ast.parse(mode="eval")` 拒绝，`:92-140`）、任意函数调用、任意属性链 |
| z3 翻译 | `Bool/Int/Real` 标量、`And/Or/Not`、比较、`+-*/%`、常量、名称（`spec_smt.py:322-388`） | 调用/幂/下标/属性 → **整条子句保守跳过**（`:20-22`、`:88`）。全仓 `src/specs/` 无 `ForAll/Exists/Array/Function/BitVec/String`（grep 实测为空） |

结论：**不是一阶逻辑，也没有关系/时序**。它是"单排序标量上的无量词布尔组合 + 线性算术"，即 QF 片段；名称未做符号化建模（无未解释函数、无数组理论），所有子句都是对同一批标量变量的一阶无量词约束。

#### B.2.3 SMT 是真求解还是语法检查？

**真求解**（[读码]，调用点为 `z3.Solver()` / `z3.Optimize()`）：
- 前件 SAT 见证 + 边界极值：`spec_smt.py:525-546`（`solver.check() == z3.sat` 取模型；`Optimize().minimize/maximize` 取边界，带 `_OPT_BOUND=10**6` 包围盒与 timeout）。
- 前件空洞（UNSAT）检测：`:559-584`。
- 后件自洽（把 `r` 视为自由变量）UNSAT 检测：`:654+`；组合入口 `check_spec_consistency`（`:693`）。
- 见证还要过 **Python 语义复核**（`:495-517`，受限 AST 求值器，无 `eval`），z3 与 Python 语义分歧的见证被丢弃。
- 预算：`SPEC_SMT_TIMEOUT_MS` 默认 2000、上下限 100–30000（`:73-80`）；`SPEC_SMT_MAX_WITNESSES` 默认 3（`:82-92`）；`used` 上限由 `_max_witnesses` 控制。
- 默认关（`SPEC_SMT_ENABLE` false，`:48-49`）；z3 已进 `requirements.txt:53` / `requirements.lock:130` 并有 CI fail-closed 断言（`ci.yml:183-207`），本机实测 `z3 5.1.0` 可导入。

**明确不做**（模块自述 `:14-24`，与代码一致）：不做"实现是否满足后件"的判定（无实现语义，判了是空话）。

**但后件断言仍是"实现输出 vs 字面约束"**：`compile_spec_oracle` 把后件编译成 `assert <expr>`，`r = func(...)`（`spec_ir_v2.py:419-427, 471-503`）。无边界材料时用**字面量 0 绑定**（`:487-503`），代码自己承认"层 2 的字面量 0 绑定可能本身违反前置条件"（`:457-458`）——这会产出**对无缺陷代码也失败的断言**，即 1.1 意义上的 over_red。默认关（`SPEC_ORACLE_EXEC_ENABLE` 默认 false，`flags.py:185-201`），`logic`/`scientific` 档开。

#### B.2.4 反例驱动精化（CEGIR）**未接入主链路**

`spec_refine.py:26-28` 自述："本模块是独立可调用能力……**不接入主链路**（Planner/Generator 调用点的接入属后续批次）"。`[读码]` 全仓无 `spec_refine` 的调用点（仅 `spec_refine.py` 自身与 `spec_smt.py` 的 docstring 引用）。所以"检测到矛盾 → 回灌 LLM 修契约"这条闭环在代码层**不存在于运行路径**，只在单元测试里。

#### B.2.5 逻辑链路的真实端到端形态

```
Planner(LLM) → logic_analysis(JSON)
  → parse_logic_analysis + validate_spec_ir（观测，M10 严格模式默认关；logic_spec.py:51-53）
  → compile_readiness / spec_expr_coverage（纯观测，SPEC_IR_DSL_ENABLE）
  → compile_spec_oracle（SPEC_ORACLE_EXEC_ENABLE）→ 追加 test_specir_v2_oracle 到生成测试尾部（nodes.py:173-227, 253-260）
  → Executor 与 LLM 测试同文件执行 → spec_oracle_verdict 行级判定（nodes.py:263-289）
```
"逻辑驱动"在运行期**确实存在**（oracle 注入 + 判定），但强度受限于：表达式通道接受率（`BASELINE.yaml:70-72` 实测 0.205–0.219）、绑定上下文保守（无边界材料时字面量 0）、SMT 只用于取输入/查自相矛盾、精化闭环未接线。

---

### B.3 (c) 补丁生成 vs 运行时自修复

#### B.3.1 代码层判定：**自动化程序修复（APR）闭环，不是运行时自修复**

- 修复动作 = 把**整份**新源码写回被测文件：`_safe_write_patch`（`patch_io.py:351-455`）经 4 道检查（非空/不短于原码 10%、含函数定义、路径白名单、仓库核心黑名单）后 `_write_file_atomic`（`:201-223`，tempfile + `os.replace`）。
- 验证失败回滚：`_rollback_last_patch`（`:458-504`）从 `tempfile.gettempdir()/aitester_patch_snap_<pid>_<tid>/iterN_<basename>` 恢复快照；快照失败 **fail-closed 拒写**（`:444-449`）。回滚触发在 `nodes.py:1481-1494`（本轮测试失败 + 有快照 + 磁盘与 state 双恢复）。
- 目标文件是**任务的临时副本**：`run_benchmark.py:1576` `tempfile.mkdtemp(prefix=f"aitester_{task.task_id}_")` + `:1602` 写 `instance_file`；跨文件任务同样落在该 tmp 目录（`_write_cross_file_modules`，`:1378, 1611`）。
- 无任何运行时自愈组件：全仓 `grep watchdog|supervisor|self-heal|restart|daemon` 只命中 `api_manager.py:63,1024-1051`（LLM API 健康检查线程，与"修复被测系统"无关）；CLI 只有批量命令（`src/cli/app.py`、`main.py:11`），无 `serve/watch` 模式。
- "自修复"在代码里只出现在三处注释（`self_repair_trap.py:4`、`nodes.py:1079`、`semantic_cache.py:347`），语义都是"迭代修复循环"，不是"运行时恢复"。
- 文档侧已自行收口：`MODEL_CARD.md:15-16`"**自修复为可测量口径而非已证实主张**（AL5 定位收口）"；`README.en.md:50` 仍写 "self-repair exists"。

#### B.3.2 修复侧的确定性优先与弃权门

- 确定性优先路由：`debugger.py:355-390`（`DETERMINISTIC_REPAIR_FIRST_ENABLE` 默认 **false**，`deterministic_repair.py:87`）；每任务至多一次（`state["deterministic_repair_status"] is None`）。
- 弃权门（ADR-0020）：`patch_abstain.py:40-63`，5 条信号纯推导，**只透出 `patch_abstained` / `patch_abstain_signals`，不做阻断**（`:23-29` 自述"观测层先行，阻断档待 A/B 后转正"）。`[读码]`
- 故障定位：`fault_localizer.py:64` `FAULT_LOCALIZER_ENABLE` **默认 true** → aitester 臂每任务多一次 LLM 调用（定位），而 `plain_llm_df` 臂无此组件（`run_benchmark.py:381-419`）。对照实验的成本/效果归因需注意该不对称。`[读码]`
- 回归保护：`_compute_regression_rate`（`_m1_metrics.py:649-695`）在补丁后跑 gold P2P；`RED_REGRESSION_GATE`（默认关）只处理"抹红"，不做 P2P。

---

### B.4 (d) 执行沙箱强度

| 链路 | 默认 | 环境变量 | 文件系统 | 网络 | 进程/资源 |
|---|---|---|---|---|---|
| venv 沙箱（`EXECUTOR_USE_VENV=true` 默认，`config.py:488`） | **默认生效** | `scrub_os_environ()` → 白名单 13 键，**默认 true**（`credential_scrub.py:91-111, 114-122, 211-213`）；`HOME` 在白名单内 | **无隔离**（无 chroot/namespace：`executor_modes.py:257-264` 只改 PYTHONPATH） | **无限制** | 30s 墙钟 + `RLIMIT_CPU/NPROC/FSIZE/NOFILE`（`executor_runtime.py:24-53, 137-170`）+ 进程组 kill（`process_utils.py`） |
| 本地链路（`EXECUTOR_USE_VENV=false`） | 需显式 | 同上（`executor.py:177-183`） | **无隔离**，且 **cwd=仓库根**（`executor.py:154, 271`） | **无限制** | 同上 |
| Docker（`EXECUTOR_USE_DOCKER` 默认 false，`config.py:497`） | 否 | `scrub_os_environ()`（`executor_modes.py:472`） | `--read-only` + `/tmp` tmpfs + 挂载 sandbox_dir（`:435-437, 374-382`） | **默认 `--network=none`**（`DOCKER_DEFAULT_NETWORK_NONE` 默认 true，`:438-442`）；`allowlist` 档实为 bridge、**无容器级出站管控**（`:387-395, 405-416`，项目已诚实化） | `--cpus/--memory/--pids-limit` + `--cap-drop=ALL` + `no-new-privileges`（`:417-437`） |
| 内核沙箱（Seatbelt/bwrap，`KERNEL_SANDBOX_ENABLE` 默认 false） | 否（`safe`/`logic` 档开） | — | Seatbelt profile：`(deny default)` + 放行 `allowed_paths`/`/usr`/`/System`/`/Library`/`/tmp` 读，写仅 `allowed_paths`+`/tmp`；显式 deny `.env*`/`.ssh`/`.aws`（`kernel_sandbox.py:105-142`） | **未放行 network**（注释 `:141`；profile 无 `allow network*`） | `process-fork` + 限定 `process-exec` 子路径（`:135-137`） |

**两个关键削弱点（[读码]）**：

1. `build_sandbox_command` 把 `cwd` 自动追加进 `allowed_paths`（`kernel_sandbox.py:209-211`），而本地链路传 `cwd=project_root`（`executor.py:238`，`project_root` 为仓库根，`:154`）→ **内核沙箱开启时，整个仓库根是可读可写路径**；只有 `.env/.ssh/.aws/llm_configs.json/credentials` 被 deny 读取（`:140`），没有对 `src/` 等源码的写保护（`patch_io.py` 的仓库核心黑名单只作用于**补丁写盘**，不作用于**测试执行**）。
2. `runtime_probe.capture_failure_snapshot` 用子进程执行 LLM 生成的测试代码（`runtime_probe.py:345-353`），env 走 `scrub_os_environ()`（`:343`），但**没有** `kernel_sandbox` 接入：全仓 `kernel_sandbox` 调用点仅 `executor.py:237` 与 `executor_modes.py:143`。同一份代码在 `KERNEL_SANDBOX_ENABLE=true` 时经 executor 被沙箱化，经 probe 则不被沙箱化（`RUNTIME_PROBE_ENABLE` 默认 false，`runtime_probe.py:75`）。
3. 其余 LLM 产物执行面（`testless_validation.py:228-240` 导入冒烟、`:120-140` mypy）同样只有 env 脱敏 + 超时，无内核沙箱；`dependency.py:895-899` 的 `pip install` **未传 `env=`**（继承全量环境，但执行的是 pip 而非 LLM 代码，风险低；`auto_install_deps` 默认 false，`executor.py:74`）。
4. 残余风险（[静态推断]，与项目自己记录的挂死事故同类，`executor.py:204-211`）：M1 判定原语 `_m1_metrics._run_pytest_in_tmp` 仍用裸 `subprocess.run(..., capture_output=True, timeout=timeout)`（`:358-378`），未采用 2026-10-10 引入的 `process_utils.run_with_timeout`（临时文件承接输出）——若被测代码派生"孙进程持管道写端"，`communicate()` 可能不返回，且该原语同时被离线指标与运行时特异性门调用（`detection_gates.py:85-87`）。

---

### B.5 (e) LLM 输出→exec/eval/subprocess 注入面

| 面 | 位置 | 现状 |
|---|---|---|
| 主进程 eval/exec | 全仓 grep：`src/` 内唯一 `exec(` 在 `runtime_probe.py:251`（**子进程 runner 模板字符串内**，非主进程）；`dataset_loader.py:396` 的 `compile()` 仅做语法校验（不 exec） | 无主进程蒸煮面 |
| shell 注入 | 全仓 `shell=True` / `os.system` / `os.popen` / `pickle.load` / `yaml.load` grep **为空** | 无 |
| LLM 补丁危险操作（输出侧） | `nodes.py:1759-1814`：AST 差集 `dangerous_api_added`（默认开，`patch_applier.py:483, 896`）+ 正则 `check_llm_patch_safety`（输出侧默认开，`injection_guard.py:56-65`）→ **命中即拒绝应用**（`nodes.py:1811-1814`） | 有拦截 |
| 命名契约（补丁不许删符号） | `nodes.py:1766-1777` `check_naming_contract`，失败拒应用 | 有拦截 |
| Prompt 注入（输入侧） | `injection_guard.py:51-53` `INJECTION_GUARD_ENABLE` **默认 false**；接线在 `nodes.py:839-875`（只写"疑似注入"警示，不阻断——模块自述 `:44-46`） | 默认关，且只标记 |
| 生成测试的副作用（输出侧测试代码） | 无静态拒绝：`deterministic_guard`（随机数/长 sleep/网络/子进程 AST 扫描，`deterministic_guard.py:32-35` 默认 false）与 `oracle_validator`（恒真断言，默认 false）都只是**观测**，不阻断 | 默认关 |
| LLM 输出的代码抽取 | `helpers.extract_code_block` / `patch_applier.normalize_patch_text`（markdown 围栏/`python` 前缀清理，`_m1_metrics.py:395-401` 记录其必要性） | 无执行风险，但**判分口径与执行口径历史上曾分叉**（同处记录） |
| 凭证外泄 | `credential_scrub` 白名单（默认 true）覆盖全部 LLM 代码子进程（executor 三链路 / runtime_probe / testless_validation）；对照明文 `.env`：本机 `.env` 存在（`ls -la` 实测），未被 `.gitignore` 之外机制保护，CI 有 gitleaks 工作树硬门禁（`ci.yml:448-458`）+ 历史扫描（非阻断，`:529-540`，注释自述存在**存量历史泄漏**） | 基本可控，历史泄漏未清 |

---

### B.6 声称 vs 实现对照表

| # | 主张 | 声称出处 | 代码实际 | 判定 | 影响 |
|---|---|---|---|---|---|
| 1 | 门①与 M1"完全同一原语，行为口径一致" | `src/tools/detection_gates.py:21-24` | 只复用了 `_run_pytest_in_tmp`，未复用错误判据（`detection_gates.py:82-93` vs `_m1_metrics.py:58-81, 528-538`）；实测 rc=2 → `over_red` | **不一致** | 过红统计混入未运行/收集错误；路由、弃权信号、R3 代理、−28pp 机制归因受影响 |
| 2 | "检出优先协议让系统先检出再修复" | `config.py:385-414`；`workflow.py:675-719` | 实现存在且可路由；但默认关，且 `over_red` 强化段落默认关（`nodes.py:520-527`），再生成预算 1（`config.py:375`） | **部分一致** | 默认口径与"检出优先"无关；logic 档才生效 |
| 3 | `over_red` = 非特异红（含挂起） | `nodes.py:592-597` | 挂起在 fixed 侧→`unavailable`（`detection_gates.py:116-120`）；实测真正产出 over_red 的是收集/导入错误 | **不一致** | 机制叙事把三类不同证据（挂起/未运行/非特异）混为一类 |
| 4 | "逻辑驱动 = 可编译率" | `nodes.py:415-420`；`BASELINE.yaml:70-74` | 定义与写入点存在（`spec_ir_v2.py:686-719`；`nodes.py:421-449`），默认关、纯观测；实测率 0.205–0.219（工件） | **部分一致** | 主张强度被高估：通过率 ≠ 规约覆盖，且未接精化闭环 |
| 5 | SMT 为"形式化内核" | `ci.yml:183-207`；`spec_smt.py:14-24` | z3 真调用（`Solver/Optimize`），但仅 QF 标量约束、仅前件见证/空洞/后件自洽；**不做**实现-后件验证（模块自述同） | **部分一致** | 论文中若称"形式化验证实现"则不成立 |
| 6 | "自修复系统" | `README.en.md:50`（"self-repair exists"）；`MODEL_CARD.md:15-16`（已收口为"可测量口径"） | 无运行时自愈；只有补丁写盘+回滚（`patch_io.py:351-504`） | **不一致（定位层面）** | 对外定位需限定为 APR/离线修复 |
| 7 | 覆盖率 84–94% 与检出 13–16% 并列披露 | `BASELINE.yaml:58-64` | 两指标定义与分母确实不同（`executor.py:198` vs `_m1_metrics.py:529-539`；分母 `run_benchmark.py:2674` vs `run_main_batch.py:370-374`），注释未点明分母不同构 | **部分一致（数字诚实，归因不足）** | 易被读成"同一批任务的覆盖率 vs 检出率" |
| 8 | 沙箱"隔离执行" | `executor.py:48-59`（模式优先级描述） | venv 档只隔离 env/sys.path；内核沙箱默认关且开启时含仓库根可写；probe 链路未接沙箱 | **部分一致** | "沙箱"一词在 venv 档易被高估；LLM 测试代码默认可写宿主文件、可联网 |
| 9 | 凭证不外泄到被测沙箱 | `credential_scrub.py:23-31` | 白名单默认 true 且被三条链路消费（实测 `executor.py:177-183`、`runtime_probe.py:343`、`testless_validation.py:236`） | **一致** | 但只封环境变量；`HOME` 在白名单内 → `~/.ssh`、`~/.aws` 文件仍可读（内核沙箱档才 deny） |
| 10 | Prompt 注入防御（ADR-0012） | `injection_guard.py` 模块头 | 输入侧默认 false 且仅标记；输出侧默认 true 且**真拦截**（`nodes.py:1811-1814`） | **部分一致** | 输入侧（issue/描述注入）默认无防护 |
| 11 | 弃权门（ADR-0020） | `patch_abstain.py:1-29` | 判定核存在，5 信号纯推导，**只观测不阻断**（自述一致） | **一致（自述即观测层）** | 不能当作"已拦截坏补丁" |
| 12 | 冗余键集/历史兼容（`None` 与 0 区分） | `_m1_metrics.py:6-12` | detection/repair/false_fix 确实以 None 表示不可测（`:497-499, 598-600, 635-639`） | **一致** | 但 `spec_compile_rate` 无材料返回 **0.0**（`spec_ir_v2.py:683`），口径不同 |
| 13 | 主力批次 provenance 可审计 | `run_benchmark.py:2744-2748`（键表）、`:2890-2892`（读取）、`:2928`（写入） | 存量 main_batch 工件 env_snapshot 仅 37 键，`DETECTION_SPECIFICITY_GATE_ENABLE`/`SPEC_IR_DSL_ENABLE`/`SPEC_ORACLE_EXEC_ENABLE` **ABSENT**（非 None）；而结果行有非空 `specificity_gate_verdict` 证明门确实运行 | **不一致（存量工件）** | "逻辑档开了哪些开关"只能从数据反推；键表 2026-10-10 才补齐（`run_benchmark.py:2838-2845`） |

---

### B.7 Python 专项诊断表

| 维度 | 问题 | file:line | 严重度 | 修复建议 |
|---|---|---|---|---|
| 类型门禁深度 | `[tool.mypy]` 段**无任何严格设置**（仅一个 overrides 表）；未注解函数体不检查 | `pyproject.toml:232-234, 256` | 中 | `[tool.mypy]` 加 `disallow_untyped_defs=true`（当前 `--disallow-untyped-defs` 实测 10 errors）、`check_untyped_defs=true`、`warn_unused_ignores=true`；命令：`.venv/bin/python -m mypy src/ config.py --disallow-untyped-defs` |
| 类型抑制存量 | `type: ignore` 43 处（src/） | `grep -rn "type: ignore" src/ \| wc -l` → 43 | 低 | 逐簇收窄并启用 `warn_unused_ignores`；`ruff` 已启用 PGH003（`pyproject.toml` select 含 `PGH`） |
| lint/format | `ruff check .` 全绿（0.16.3） | 实测；`ci.yml:305-308` | — | 保持 |
| 本地 format 门禁假红 | `ruff format --check .` 报 21 个文件待格式化，**全部是 `audit_2026/*.py` 审计临时脚本**（非产品代码）；`extend-exclude` 未含该目录 | `pyproject.toml:116` | 低 | `extend-exclude` 增 `"audit_2026"`，或把该目录加入 `.gitignore` |
| CI 门禁真实性 | ruff / mypy / pytest / bandit / pip-audit(顶层+lock) / gitleaks / 覆盖率 ratchet / 工件校验 / env 预算 / state 契约 / 零断言守卫均为**阻断**步骤；version 钉住 | `ci.yml:175-178, 305-321, 422-429, 460-511, 364-385, 227-259` | — | 保持；建议把 `audit_2026` 类临时目录纳入 ignore（同上） |
| 测试规模 | `pytest --collect-only` 实测 **5317 tests collected in 3.58s**（无收集错误） | 实测 | — | 保持 |
| 循环依赖 | `config.py` 顶层只依赖 `dotenv`；`src/graph/*` 用函数内延迟 import 断开环（如 `agents_cache.py:42-44`、`detection_gates.py:85`） | `config.py:20-23` | 低 | 延迟 import 是本仓惯例（`pyproject.toml` 已 ignore PLC0415），可接受 |
| 裸 except | `grep "except:"` 命中 1 处，实为 docstring 文本；无裸 except | `src/tools/code_analyzer.py:109` | — | 无需处理 |
| 静默吞异常 | `except Exception` + 紧邻 `pass` 6 处；`logger.debug` 级吞掉异常多处（探针/覆盖注入/后处理） | `nodes.py:1753-1754`、`runtime_probe.py:395-398` 等 | 低 | 已属"纯观测层不阻断主流程"设计；建议统一 `logger.info` + 计数器便于观测 |
| 测试脆弱性 | 存在以 `inspect.getsource`/源码文本为断言的接线锁（例：`run_main_batch.py:394-398` 注释说明 `tests/test_batch_vi.py` 用 `inspect.getsource(main)` 锁 staging 接线） | `experiments/run_main_batch.py:396-398`（自述）；`tests/` 未逐一读 | 低 | 属"防漂移"有意设计，但会锁死重构；建议改为行为断言 |
| 依赖钉版 | `requirements.txt`/`requirements.lock`/`pyproject` 三方一致性由 `check_lock_sync.py` 守卫；实测通过（有 2 条"lock 有而 txt 无"的传递依赖警告） | 实测；`requirements.txt:53`、`requirements.lock:130` | 低 | 保持；把 yarl/zstandard 的传递依赖说明写入注释以消除警告 |
| 打包 | `dynamic = ["version"]` + `[project.scripts] aitester`；`py.typed` 随包分发 | `pyproject.toml:17, 78-79, 82-84` | — | 无问题（未重跑构建） |
| 供 LLM 用的合成数据集 | 单文件 2532 行、模板字符串内嵌测试代码 | `src/datasets/synthetic_dataset.py`（46558 行总量最大文件） | 低 | 可读性/维护性风险；不影响正确性 |

---

### B.8 领域专项诊断表

| 领域 | 结论 | 关键 file:line | 严重度 |
|---|---|---|---|
| 多智能体编排 | 有真实状态机：`planner → generator → executor →(diagnosis/cross_file)→ debugger → patch_applier → executor`，条件路由与多终止原因齐备（`workflow.py:434-561`、`determine_stop_reason` `:126-190`）；`MAX_ITERATIONS=3`（`config.py:369`）、`MAX_REGENERATIONS=1`（`:375`）、LangGraph `recursion_limit=4*MAX_ITERATIONS+8`（`workflow.py:883-914`）；无 LLM 降级路径 = 无（架构上必需 LLM；`plain_llm` 基线也走同一 generator 节点）。**"多智能体增益"已被自身数据证伪**（`BASELINE.yaml` / `README.md:72`），代码层无机制能反驳该结论 | `workflow.py:126-190, 434-561, 883-914`；`config.py:369-375` | 中（定位问题） |
| 逻辑驱动 | 见 §2：真实但受限（QF 标量、接受率 ~0.21、精化未接线、默认关） | `spec_ir_v2.py:668-719`；`spec_smt.py:14-24`；`spec_refine.py:26-28` | 中 |
| 测试生成 | 生成-执行-再生成-修复闭环完整；防"自指假成功"的多重标记齐备（`test_regenerated_pass_unverified` `nodes.py:1388-1396`、`detection_first_status` `:1407-1413`、红回归门 `:1443-1453`）；但**判别力**由 F2P 三段度量，仅 15.8% | `_m1_metrics.py:473-539` | 中 |
| 自修复 | 不成立（§3）：APR 闭环 + 回滚，无运行时自愈 | `patch_io.py:351-504`；`main.py` | 高（对外定位） |
| 闭环 | 环路存在但修复产出率低：修复率 39.31%（项目自述，工件口径）；`idle`/无补丁行早退记 0（`_m1_metrics.py:607-609`）；`abstain` 只观测不阻断 | `_m1_metrics.py:577-622`；`patch_abstain.py:23-29` | 中 |
| 评估/测量诚实度 | 指标定义清晰、None 与 0 严格区分、逐字段剔除（`analyze_results.py:717-745`）；但 ①门与指标判据分叉（§1.1）②覆盖率与检出率分母不同构且报告未点明（§1.3）③`four_channel_recompute.py:12` 把 detection_rate 标为"断言失败红"，实际含任何异常/崩溃红 ④存量工件 provenance 缺关键开关键（§6 #13） | 同左 | 高（影响 −28pp 归因） |
| 安全 | 输出侧补丁拦截真实（双通道、默认开）；执行侧默认无内核隔离、无网络隔离（§4）；输入侧注入检测默认关；历史 git 泄漏未清（`ci.yml:529-540` 自述） | `nodes.py:1759-1814`；`ci.yml:529-540` | 高 |
| 工程化 | 强（ruff/mypy/CI/门禁/工件校验/包结构）；弱点是 mypy 深度与本地临时目录 lint 假红 | §7 | 低-中 |

---

### B.9 红队：可能推翻核心假设的反例与竞争路线

1. **"多智能体净负贡献"可能被对照设计放大**：`plain_llm_df` 不是"纯 LLM"，而是**强制开启检出优先协议**的基线（`run_benchmark.py:412-419` 线程级 override），且它没有 aitester 的额外 LLM 调用（FAULT_LOCALIZER 默认 true，`fault_localizer.py:64`）与更多提示段。若把"协议 × 编排"做 2×2（而非 2 臂），−28pp 可能部分归因于"协议在单臂上更省 token/更少干扰"。代码层提供了做 2×2 的开关（`DETECTION_FIRST_ENABLE` + `build_workflow(planner,debugger,allow_regeneration)`，`run_benchmark.py:238, 414`），但基线注册表里没有"aitester 关协议"臂（`run_benchmark.py:423-430`）。
2. **"过红 = 非特异断言"这一机制叙事**可被反例推翻：本次实测证明 over_red 至少还包含"测试根本没跑起来"（收集/导入错误，含跨文件任务的系统性形态）。若把 gate 改为与 M1 同判据（排除执行错误），`specific_red/over_red` 比例会变化，`BASELINE.yaml:75-78` 的"近 2/3 非特异过红"结论会被重估（方向：over_red 减少，比例上升或下降取决于 unrunnable 行的归属）。
3. **"覆盖率无鉴别力"的反例**：项目自己引用 Zhao/Zhou/Cohen（ISSTA 2026）的**限定性**结论（`BASELINE.yaml:64`）——回归设定下覆盖+变异可做跨模型比较。若把实验改为"缺陷已注入但不可修复"的对照，覆盖率可能重新获得部分鉴别力。项目已选择"被测代码可能有缺陷"场景，该选择成立但需在论文中显式声明适用域。
4. **"逻辑驱动"可通过提高 DSL 覆盖而非提高表达力获胜**：当前瓶颈是 `spec_expr_coverage ≈ 0.72–0.74` 与 `compile_rate ≈ 0.21`（`BASELINE.yaml:70-74`），两者相乘 ≈ 0.15–0.16 的可执行规约比例。竞争路线（纯 prompt 契约 + 变异反馈）若在同样 token 预算下达到相近的"注入断言数"，则"形式化"这一层的成本收益不成立；项目自己的 E1 门（≥0.3/＜0.2，见 `BASELINE.yaml` E1 叙述）即为该反驳的判定点。
5. **"沙箱已足够"的反例**：默认 venv 档下，LLM 生成的测试代码可读写宿主文件、可联网（§4）。在公开聊天/多租户或 CI 拉取外部 PR 的场景中，这是可被直接利用的 RCE 面；内核沙箱开启后仍保留"仓库根可写"（`kernel_sandbox.py:209-211` + `executor.py:238`）。竞争路线（容器化默认开）在安全维度上严格占优，代价是每任务 ~10s 启动开销。
6. **"修复闭环可收敛"的反例**：`MAX_ITERATIONS=3` + `MAX_REGENERATIONS=1` + 字面量 0 绑定可能违反前件（`spec_ir_v2.py:457-458`）→ 注入的 oracle 断言可能在 buggy/fixed 上都失败，形成"确定性假检出"，反而消耗修复预算。`test_error_rate` 与 `regression_rate` 能观测到部分症状（`_m1_metrics.py:542-574, 649-695`），但默认不阻断。

---

### B.10 缺失 / 不可读 / 未验证说明

| 项 | 状态 |
|---|---|
| `src/specs/spec_ir.py`（v1，15837 B） | 已列目录，未逐行读完；仅通过 `spec_ir_v2.py`/`nodes.py` 的引用与 docstring 判读其角色（v1 产物解析 + 签名提取）。其内部实现细节**未验证** |
| `src/agents/executor_repo.py`（1135 行，仓库级执行） | 未读；SWE-bench repo 级路径的沙箱强度**未验证**（本文 §4 的结论只覆盖 local/venv/docker/probe 四条已读链路） |
| `experiments/run_benchmark.py` 的 `_build_task_result`（:952-1210） | 只读关键字段；`harness_invalid`（P2P 门禁）对分母的最终影响**未验证**（属 claims-auditor 复算范围） |
| 主批次工件与工作树的时序差 | 工件产自 2026-10-06/07 提交；本报告行号基于**当前工作树**（HEAD d9e51df + 33 个修改文件）。行为结论以工作树为准，数字复算以工件为准 |
| 未执行项 | 未跑全量 pytest（仅 `--collect-only`）、未跑 LLM 实验、未跑 Docker 档、未跑 `KERNEL_SANDBOX_ENABLE=true` 实链路（仅读码 + 读 profile 构造） |
| 无法判定 | `pip install` 供应链（`dependency.py:895-899`）在真实网络下的行为；`allowlist` 网络档在宿主防火墙配置下的实际效果 |

---

### B.11 与 Lead 复算的交叉核对（4 条，含代码级归因）

复算脚本：`audit_2026/_crosscheck_lead.py`（只读工件，无 LLM）。文件集 = `experiments/results/main_batch/benchmark_synthetic_2026100[67]_*.json` 共 **7 个**（3×20261006 + 4×20261007），每臂 **609 行**（7×87）。

#### B.11.1 detection 分子一致；分母需按"None 不计入"修正 → **部分确认**

| 臂 | 行数 | 可测（detection_rate 非 None） | 分子 det=1 | 项目口径（None 剔除） | 统一 /609 |
|---|---|---|---|---|---|
| aitester | 609 | **556**（53 行 None） | **78** ✓ 与 Lead 一致 | **78/556 = 14.0%** | 12.8% |
| plain_llm_df | 609 | **571**（38 行 None） | **279** ✓ 与 Lead 一致 | **279/571 = 48.9%** | 45.8% |
| plain_llm | 609 | 609（0 None） | 10 | 10/609 = 1.6% | 1.6% |

- 项目自身口径就是剔除 None 后作分母：`experiments/run_main_batch.py:370-374`（`m1_meas = [r for r in det if r.get("detection_rate") is not None]`，分母 `len(m1_meas)`）与 `experiments/analyze_results.py:717-745`（"None 不计入分母"逐字段剔除）。
- 结论方向不变（aitester 显著低于 df），但**三臂缺失行数不同（53 / 38 / 0）**，必须逐臂标注分母；统一按行数 609 会同时低估两臂。
- 注意该 7 批集合（14.0% / 48.9%）与 `README.md:72` 的三种子 pooled 口径（`38/240 = 15.8%` vs `117/261 = 44.8%`）是**两个不同文件集**，不可混引。

#### B.11.2 机制分解：296/609、93（59/34）**完全复现**；"三臂各 46" **未复现** → 定性结论成立但需换证据

| 臂 | 从未红 `all_green_unverified` | 曾红（`red_then_green`+`red_not_repaired`） | det=1 | det \| 曾红 |
|---|---|---|---|---|
| aitester | **296 / 609 = 48.6%** ✓ | 260 / 609 = 42.7% | 78 | **30.0%** |
| plain_llm_df | 15 / 609 = 2.5% | 571 / 609 = 93.8% | 279 | **48.9%** |
| plain_llm | 535 / 609 = 87.9% | 74 / 609 = 12.2% | 10 | 13.5% |

- 复现项：`all_green_unverified` = 296 ✓；其中 **296/296** 满足 `iterations==0` 且 `patch` 为空 ✓；`red_then_green` = 93，其中 det=1 **59** / det=0 **34** ✓（与 Lead 逐一相同）。
- 未复现项："红但非特异（over_red）三臂各自 46" —— 实测 4 个含 gate 数据的 logic 档批次合计：**aitester 66 / plain_llm 38 / df 140**（逐批 18,15,18,15 / 8,11,8,11 / 38,32,38,32），三臂不相等，也无 46；另 3 个非 profile 批次**该键不存在**（见 11.3）。
- 但 Lead 的**定性结论**可由上表以更强的证据支持：aitester 的"从未产生红"比例是 df 的 **19 倍**（48.6% vs 2.5%）。同时**转化率也差 18.9pp**（30.0% vs 48.9%），反事实：只对齐 red 产生率 → 28.1%；只对齐转化率 → 20.9%。故"差距主要来自是否产生红"成立，但"不是红是否特异"过强。

#### B.11.3 `all_green_unverified` 的确切产生分支（代码级归因）

1. **唯一写入点**：`_executor_node`，且仅当 `detection_first_enabled()`（`src/graph/nodes.py:1407-1413`）；
2. `iteration==0` 时更新**粘性** `detection_first_red_seen = (not passed) or 旧值`（`nodes.py:1408-1409`）；
3. 纯函数判定 `_derive_detection_first_status`（`nodes.py:649-672`）：`passed ∧ ¬red_seen → "all_green_unverified"`；每轮执行后写、LangGraph 后写覆盖 ⇒ 终值即终态（`nodes.py:1410-1413`）；
4. **路由**：首轮全绿（`iteration==0 ∧ ¬red_seen ∧ regeneration_count<1 ∧ execution_trace 非空`）→ `regenerate`（`src/graph/workflow.py:682-699`）；
5. **再生成不递增 iteration**（`iteration` 只在补丁/诊断路径 +1：`nodes.py:1222, 1977, 2141`）⇒ 第二版测试仍在 `iteration==0` 下执行；若第二版在缺陷原码上仍绿，`red_seen` 仍为假，且 `regeneration_count=1` 已达上限（`config.py:375`）→ `_should_debug` 落到 `done`（`workflow.py:674-699`）。
⇒ **296 行 = "初始测试与（至多一次）再生成测试都在缺陷原码上全绿"**：这是**测试生成侧失败（从未产出红）**，与修复能力无关；与 `iterations=0`、`patch` 为空完全自洽。

**"再生成覆盖首轮红"要分两层**（不能混为一谈）：
- **状态层不会忘**：`red_seen` 粘性且只在 `iteration==0` 置位（`nodes.py:1409`），再生成不清除它——所以一旦首轮红过，终态不可能再是 `all_green_unverified`。工件实测无矛盾：7 批三臂 846 行 `all_green_unverified`（296+535+15）**全部** `detection_first_red_seen=False`；三臂红态（`red_then_green`+`red_not_repaired`）合计 890 行（aitester 260 / plain_llm 74 / df 556）**全部** `True`，0 例交叉；
- **指标层会丢证**：`generated_test` 被再生成**整体替换**，而 M1 只重跑最终 `generated_test`（`experiments/_m1_metrics.py:503, 519-526`）⇒ "首轮红 → 再生成 → 变绿" 的行 det=0。**实测 34/609 行（占 `red_then_green` 的 36.6%）**即"抹红"通道。`RED_REGRESSION_GATE`（`src/tools/detection_gates.py:124-162`）正是为其设计，但在本 7 批从未生效（`red_regression_violation` 全 None，见下）。

#### B.11.4 gate / oracle 字段：一条**不成立**，一条**部分成立** → 逐条标注

| Lead 第 3 条 | 判定 | 实测证据 |
|---|---|---|
| `oracle_type` 全部只有 `generated_test`，无 `enhanced_generated_test` | **确认** | 7 批 × 3 臂全部 `generated_test`。**代码归因**：该标签只看 `ORACLE_ENHANCE_ENABLE` 与 `state["oracle_enhanced"]`（`experiments/run_benchmark.py:582-599`；开关默认 false，`src/graph/flags.py:56-64`；写入点 `_planner_node`，`src/graph/nodes.py:338-399`）——**与 `SPEC_ORACLE_EXEC_ENABLE`（规约 oracle 注入）无关**。故"无 enhanced"**不能**推出"逻辑通道未运行" |
| `red_regression_violation` 609 行全为 None | **确认** | 4 个含该键的批次全 None（另 3 批键不存在）⇒ 红回归门在本 7 批从未触发/未开启 |
| `specificity_gate_verdict` 609 行全为 None、门未生效 | **不成立** | 3 个 2026-10-06 批次（profile=None）**该键不存在**；4 个 2026-10-07 批次（profile=logic）键存在，aitester **106/348 非空**（`specific_red` 40 / `over_red` 66；plain_llm 4/38；df 162/140）。aitester 的 40/66 与 `BASELINE.yaml:76` 逐位一致 ⇒ 门在这 4 批**确实运行**，只是没覆盖全部 7 批 |
| （补充）`spec_oracle_verdict` / `spec_oracle_injected` | **不可判定** | 该键在 7 批结果行中**不存在**（schema 2026-10-10 才加入，`run_benchmark.py:1060-1073` 注释自述）⇒ 这 7 批"规约 oracle 是否注入"无法从工件证明，标"未验证" |

**新增的工件级证据（对 §1.1 有约束力，避免我过度声称）**：gate 判定与 M1 detection 在可执行行上**逐位一致**——
`specific_red → det=1.0` 为 **206/206（100%）**；`over_red → det=0.0` 为 **244/244（100%）**（7 批三臂合计）。即两者在"fixed 侧正常跑出 pytest 结论"时等价；**分歧只发生在"根本没跑起来"这一格**（本次实测 rc=2 → gate 判 `over_red`、M1 判执行错误→0.0）。因为两者在该格都输出"非检出"，工件层无法区分"真过红"与"从未运行"，这正是 §1.1 的口径缺口所在。

#### B.11.5 真实仓库基准工件：**确认且更强**

- 唯一 swe_bench / swe_bench_pro 工件 23 个（排除 `_superseded_20261010`）：**swe_bench 293 行 + swe_bench_pro 72 行** ✓ 与 Lead 一致；
- 更强的一点：不只 `detection_rate` 全为 None，而是**该键在这些行中根本不存在**（早期 schema）；`instance_code` 空 100%（两个数据集、每个工件、每个臂）。
- 代码级归因：`_compute_detection_rate` 要求 gold 材料非 None（`_m1_metrics.py:499-501`）且 `instance_code` 非空（`:506-508`）；`_extract_gold_material` 对 `source == "swe_bench"` **直接返回 None**（`:430-431`），`_gold_fixed_code` 对 swe_bench 返回 `""`（`:462-463`）⇒ 真实仓库任务在 M1 口径下**结构性不可测**，无论跑得如何。数据集侧对 `instance_code` 兜底为 issue 文本已有质量判定（`src/datasets/dataset_loader.py:394-400`）。
- 影响：SWE-bench / SWE-bench-Pro 的任何"0/20"类结论只在 `passed` 口径下成立，**与 detection/repair 无关**；把它们与合成集 M1 数字并列会误导。

---

### B·附：本次实测命令与输出（摘要）

```
.venv/bin/python -m ruff --version                         → ruff 0.16.3
.venv/bin/python -m ruff check src config.py experiments   → All checks passed!
.venv/bin/python -m ruff format --check .                  → 21 files would be reformatted（全部为 audit_2026/*.py 审计脚本）
.venv/bin/python -m mypy --version                         → mypy 1.15.0 (compiled: no)
.venv/bin/python -m mypy src config.py                     → Success: no issues found in 123 source files
.venv/bin/python -m mypy src config.py --disallow-untyped-defs --no-error-summary | grep -c "error:"  → 10
.venv/bin/python -m pytest --collect-only -q               → 5317 tests collected in 3.58s
.venv/bin/python -c "import z3; print(z3.get_version_string())" → 5.1.0
.venv/bin/python scripts/gates/check_lock_sync.py          → 结果：通过（2 条传递依赖警告）
.venv/bin/python scripts/gates/check_env_budget.py --check → 183 个开关，登记 183，通过
.venv/bin/python scripts/gates/check_state_contract.py     → 通过
.venv/bin/python scripts/gates/check_zero_assert_tests.py  → 260 个测试文件，零断言 0
.venv/bin/python audit_2026/_probe_gate_vs_metric.py       → 收集错误 rc=2；specificity_verdict=over_red（两形态）
main_batch 门终审复算（4 份 logic 档工件）: aitester specific_red=40 / over_red=66
   （与 BASELINE.yaml:76 完全一致）；工件 env_snapshot 键数=37，缺 SPEC_IR_DSL_ENABLE 等键（ABSENT）
.venv/bin/python audit_2026/_crosscheck_lead.py            → 7 批/609 行：aitester det 78/556=14.0%（53 None）、
   df 279/571=48.9%（38 None）、plain_llm 10/609；all_green_unverified=296（296/296 iterations=0 且 patch 空）、
   red_then_green=93（det=1 59 / det=0 34）；over_red: aitester 66 / plain_llm 38 / df 140；
   gate×det: specific_red→det=1 206/206、over_red→det=0 244/244；red_regression_violation 全 None
swe_bench 工件普查（23 个唯一文件）: swe_bench 293 行 + pro 72 行；instance_code 空 100%、
   detection_rate 键存在数 0（早期 schema）
```



---

## 附录 C｜2025–2026 前沿基线一手来源重建（含失败端点与检索方法）

> 源文件：`audit_2026/T_C_frontier_primary_sources.md`（本附录为该文件的完整内容，仅调整标题层级与编号）

### C·T-C 2025–2026 前沿基线一手来源重建（独立审计）

- **负责人**：frontier-scout（独立评审团队 T-C）
- **检索日期**：2026-10-11（Asia/Shanghai）
- **工作目录**：`/Users/wangchenyu/Workspace/AITester`
- **产出范围**：仅本文件。未修改项目任何其它文件。
- **纪律声明**：本文件**不采信**项目内文档（`README.md` / `BASELINE.yaml` / `review_2026/R1-R3` / `REVIEW_2026_FRONTIER.md`）中的任何前沿数字。下表中每一个数值均来自本节说明的一手端点，并逐条标注证据等级与交叉验证情况。**凡未取得一手来源者一律标注"未取得一手来源"，不做任何数值推测。**

---

### C.0 检索方法与可用性说明（含失败端点）

#### C.0.1 实际使用的端点（全部为程序化直接读取，非记忆）

| 端点 | 用途 | 状态 |
|---|---|---|
| `https://export.arxiv.org/api/query?id_list=<id>` | 核验 arXiv id ↔ 标题/作者/日期/comment/摘要 | ✅ 可用（需重试，偶发超时） |
| `https://export.arxiv.org/api/query?search_query=ti:"X"` / `all:"X"` | 存在性检索 | ✅ 可用 |
| `https://raw.githubusercontent.com/swe-bench/experiments/main/evaluation/{verified,lite}/<entry>/…` | **SWE-bench 官方榜单条目**：`metadata.yaml` / `results/results.json` / `per_instance_details.json` | ✅ 可用（无速率限制） |
| `https://api.github.com/repos/swe-bench/experiments/contents/...` | 榜单条目目录枚举 | ⚠️ 未认证 60 req/h，**已耗尽并被 429**；改用 `raw.githubusercontent.com` + `git sparse-checkout` 绕过 |
| `git clone --filter=blob:none --sparse https://github.com/swe-bench/experiments` | 枚举 `evaluation/lite` 全部 84 个条目 | ✅ 可用 |
| `https://api.crossref.org/works/<DOI>` | DOI → 标题/作者/卷期页/摘要 | ✅ 可用 |
| `https://api.openalex.org/works?search=…` | 存在性交叉验证 | ✅ 可用 |
| `https://doi.org/…`、`https://www.swebench.com/submit.html` | 官方提交规则 | ✅ 可用 |

#### C.0.2 失败/受限端点（影响覆盖度，如实列出）

| 端点 | 失败情况 | 影响 |
|---|---|---|
| `https://dblp.org/search/publ/api` | 被 **Anubis 反爬**拦截（返回 "Making sure you're not a bot!" HTML），加 UA 亦无效 | **DBLP 完全未用上**；改用 Crossref + OpenAlex + arXiv 三方替代 |
| `https://api.semanticscholar.org/graph/v1/paper/search` | HTTP **429 Too Many Requests** | Semantic Scholar 未用上 |
| `https://www.swebench.com/verified.html` | web_fetch 超时 / curl 连接超时 | 榜单表格未从站点 HTML 读到；**改为直接读官方榜单仓库的逐条结果文件**（更一手） |
| `https://huggingface.co/` | HTTP 502 | 未使用（不影响本任务） |
| `web_fetch` 工具对 `github.com` / `raw.githubusercontent.com` | 报 "resolves to a non-public IP address"（DNS 限制） | 改用 `bash` + `curl`（网络可用），已绕过 |

#### C.0.3 证据等级定义（本文件统一口径）

- **A**＝一手可逐条复算：数值直接取自官方榜单文件（`results.json` / 逐实例 `resolved`）或会议 DOI 的 Crossref 结构化元数据。
- **B**＝一手原文可打开，但仅核到 arXiv 官方摘要中的数值，**未逐条核对正文表格与实验条件**。
- **C**＝二手转述（第三方页面 / 搜索片段 / 项目文档），无可打开的原文。
- **D**＝不可验证 / 检索无命中，**疑似不存在**。
- **E**＝推测（本文件不使用 E 级数值）。

#### C.0.4 关键换算与口径（避免把榜单率算错）

- SWE-bench Verified 分母 **500**；SWE-bench Lite 分母 **300**。
- 官方 `metadata.yaml` 的 `info.resolved` 字段即官方 resolve rate（百分数），与逐实例统计一致。
- ⚠️ **本审计发现的真实口径陷阱（A 级证据）**：条目 `20260901_mini-v2.4.2_gemini-3-5-flash` 的 `per_instance_details.json` **只有 441 条**实例（359 resolved / 82 not），若用 441 作分母会得到 **81.4%**，而官方 `metadata.yaml` 与 500 分母给出的是 **71.8%（=359/500）**。任何"用逐实例文件求和再除以文件行数"的复算脚本都会**高估 9.6pp**。本项目若存在此类复算，必须统一用 500/300 分母。

---

### C·表 1 ｜ LLM 测试生成（覆盖率 / 变异得分 / 缺陷检测）

| 方法/系统 | 指标 | 指标值 | 基准 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|---|
| **TestGenEval** | 平均覆盖率（最佳模型 GPT-4o） | **35.2%** | TestGenEval（68,647 tests / 1,210 file pairs / 11 Python 仓库） | https://arxiv.org/abs/2410.00752 | 2024-10 | arXiv 预印本（Meta） | B | ① 原文摘要；② TestForge 论文以 TestGenEval 为评测基准并说明其构成（arXiv:2503.14713） |
| **TestForge** | pass@1 / line coverage / mutation score | **84.3% / 44.4% / 33.8%**；成本 $0.63/file | TestGenEval | https://arxiv.org/abs/2503.14713 | 2025-03 | arXiv 预印本 | B | ① 原文摘要；② 与 TestGenEval 的 35.2% 覆盖率口径不同（pass@1 vs 平均覆盖率），**二者不可直接比较**——本表并列仅为说明同基准不同指标 |
| **CoverUp** | per-module median line+branch coverage | **80%**（对照 CodaMosa **47%**） | 挑战性 Python 模块基准 | https://arxiv.org/abs/2403.16218 | 2024-03（v4 2025-05） | **FSE 2025**（comment: to appear at FSE'25） | B | ① 原文摘要；② 第三方复现研究 arXiv:2601.09695 将其列为被复现的 4 个 SOTA 工具之一 |
| **CoverUp** | overall line+branch coverage | **89%**（对照 MuTAP **77%**） | 同上 | https://arxiv.org/abs/2403.16218 | 同上 | FSE 2025 | B | 同上 |
| **SymPrompt** | 正确测试数 / 相对覆盖率提升 | **×5** 正确测试；CodeGen2 相对覆盖率 **+26%**；GPT-4 覆盖率 **>2×**（vs baseline prompting） | 开源 Python 项目挑战性方法 | https://arxiv.org/abs/2402.00097 | 2024-01 | arXiv 预印本 | B | ① 原文摘要；② arXiv 全库检索 `all:"SymPrompt"` 仅 3 条命中，其中 2601.09695 明确称"复现了 SymPrompt" |
| **HITS** | line / branch coverage（相对 SOTA 与 EvoSuite） | 摘要**未给数值**（仅"significantly outperforms"） | 复杂 focal methods 数据集 | https://arxiv.org/abs/2408.11324 | 2024-08 | **ASE 2024**（comment） | B | ① 原文摘要无数字；② 被 arXiv:2601.09695 列为被复现工具。**数值未取得一手来源** |
| **ChatUniTest** | line coverage vs TestSpark / EvoSuite | **在半数项目上最优**（摘要未给具体百分数） | 自建项目集 | https://arxiv.org/abs/2305.04764 | 2023-05（v2 2024-05） | **FSE 2024 Demo**（comment） | B | ① 原文摘要；② 代码库 github.com/ZJU-ACES-ISE/ChatUniTest（摘要中给出）。**具体覆盖率数值未取得一手来源** |
| **TestSpark** | 工具型论文，摘要**未给覆盖/变异数值** | 未取得一手来源 | — | https://arxiv.org/abs/2401.06580 | 2024-01 | arXiv 预印本（JetBrains Research） | B | 被 arXiv:2601.09695 列为被复现工具 |
| **TestPilot** | median statement / branch coverage | **70.2% / 52.8%**（对照 Nessie 51.3% / 25.6%） | **25 个 npm 包、1,684 个 JS API 函数** | https://arxiv.org/abs/2302.06527 | 2023-02（v4 2023-12） | arXiv 预印本（TOSEM 系工作） | B | ① 原文摘要；② OpenAlex 检索确认存在。⚠️ **口径警告：TestPilot 是 JavaScript/npm 工具，"LLM 单元测试生成"若在 Java 语境引用 TestPilot，属于基准错配** |
| **AID → 已更名 TrickCatcher** | recall / precision / F1（相对 SOTA 基线倍数） | **1.80× / 2.65× / 1.66×** | TrickyBugs + EvalPlus（366 人工 + 151 AI 生成 plausible programs） | https://arxiv.org/abs/2404.10304 | v1 2024-04（AID）/ v2 2025-05（TrickCatcher） | **ACL 2025 Main**（comment，v2） | A（v1/v2 更名事实）+ B（数值来自摘要） | ① v1 摘要明写 "this paper proposes AID"；② v2 摘要明写 "we propose TrickCatcher"。**这是同一个 arXiv id 的更名，`ti:"AID"` 检索因此 0 命中**，属可复现的检索陷阱 |
| **ULT (UnLeakedTestbench)** | 12 模型均值 accuracy / statement / branch / mutation | **41.32% / 45.10% / 30.22% / 40.21%** | ULT（**3,909** 个真实 Python 函数级任务，抗泄漏构造） | https://arxiv.org/abs/2508.00408 | 2025-08 | arXiv 预印本（under review） | B | ① 原文摘要给出全部四个数值；② arXiv 全库 `all:"UnLeakedTestbench"` 命中该文 + arXiv:2608.24473（Ockhamareto）引用 ULT |
| **PLT (PreLeakedTestbench)** | 同上（泄漏对照臂） | **47.07% / 55.13% / 40.07% / 50.80%** | PLT（ULT 的泄漏配对基准） | https://arxiv.org/abs/2508.00408 | 2025-08 | arXiv 预印本 | B | 同上。**泄漏使 branch coverage 膨胀 +9.85pp（40.07→30.22 的反向差），是"记忆 vs 推理"对照设计的直接证据** |
| **TESTEVAL（对照基准）** | 同上 | **91.79% / 92.18% / 82.04% / 49.69%** | TESTEVAL（210 个 LeetCode Python 程序） | https://arxiv.org/abs/2406.04531（数值出自 2508.00408 同表） | 2024-06（v2 2025-02） | **NAACL 2025 Findings**（comment） | B | ① ULT 原文摘要并列给出 TESTEVAL 数值；② TESTEVAL 自身 arXiv 记录存在（210 程序、3 任务）。⚠️ TESTEVAL 是 LeetCode 题 → 与 ULT 的高复杂度真实函数**不可直接横比** |
| **CANDOR** | oracle correctness vs SOTA fine-tuning 基线 TOGLL | **≥ +21.1 pp**；覆盖率与 EvoSuite 相当，**mutation score 明显更优** | Java 单元测试（多智能体 + panel discussion 共识） | https://arxiv.org/abs/2506.02943 | 2025-06（v7 2026-03） | arXiv 预印本（**venue 未在 arXiv comment 中给出；项目文档称 TOSEM 2026，本次未取得一手 venue 证据**） | B（数值）/ D（venue） | ① 原文摘要；② TOGLL 原文 https://arxiv.org/abs/2405.03786 独立存在，构成对照锚点 |
| **TOGLL** | 正确 assertion oracle / exception oracle / 独有 bug 数 | **3.8× / 4.9×** 于 SOTA 神经方法；能发现 **1,023** 个 EvoSuite 无法发现的 bug | SF110 微调 + 25 个大型 Java 项目 | https://arxiv.org/abs/2405.03786 | 2024-05（v2 2024-12） | arXiv 预印本 | B | ① 原文摘要；② CANDOR 摘要独立引用 TOGLL 为 SOTA 基线 |
| **TestAgent** | execution rate / line cov / branch cov / mutation score | **97.46% / 92.34% / 90.24% / 83.69%** | 6 个 Java 项目 | https://arxiv.org/abs/2607.09101 | 2026-07 | arXiv 预印本 | B | ① 原文摘要；② `ti:"TestAgent" AND cat:cs.SE` 仅 1 条命中，无歧义。⚠️ 6 个项目样本量极小 |
| **AdverTest**（对抗式 test vs mutant 智能体） | fault detection rate 提升 | **+8.56%** vs 最强 LLM 基线；**+63.30%** vs EvoSuite；同时提升 line/branch coverage | **Defects4J**（Python 11/12，据 Lead 独立核验） | https://arxiv.org/abs/2602.08146 | 2026-02（v3 2026-08） | **ISSTA 2026**（DOI `10.1145/3832122`，由 Lead 独立核验） | B（数值）+ A（DOI 由 Lead 核验） | ① 原文摘要；② Lead 独立核验 DOI ← **跨成员交叉验证成立** |
| **纯提示基线复现研究（反例）** | plain LLM 相对 4 个 SOTA 工具的提升 | line **+17.72%** / branch **+19.80%** / mutation **+20.92%**；plain LLM 绝对值为 49.95 / 35.33 / 33.82 | **393 类 / 3,657 方法** | https://arxiv.org/abs/2601.09695 | 2026-01（v2 2026-07） | **ICST 2026**（DOI `10.1109/icst69053.2026.00040`，由 Lead 独立核验） | B（数值）+ A（DOI 由 Lead 核验） | ① 原文摘要明确列出被复现的 4 个工具：**HITS、SymPrompt、TestSpark、CoverUp**；② Lead 独立核验。**这是本方向最重要的反例：表 1 中 HITS/SymPrompt/TestSpark/CoverUp 的原始增益，在换用新一代 LLM + 等强提示后可能被纯提示基线反超** |
| **METAMON** | 文档-行为不一致分类 precision / recall | **0.72 / 0.48** | 9,482 组 code-doc 对，来自 Defects4J v2.0.1 的 5 个开源项目 | https://arxiv.org/abs/2502.02794 | 2025-02 | **LLM4Code 2025**（comment） | B | ① 原文摘要；② **关键更正**：`arXiv:2502.02794` 是 **METAMON**，**不是 TestGenEval**。TestGenEval 的真实 id 是 **arXiv:2410.00752**（见本表第 1 行）。任务简报中"TestGenEval（arXiv 2502.02794 等）"这一映射**经一手核验为错误** |

**表 1 小结（覆盖率/变异得分的"真实分布"）**
- 在**抗泄漏、高复杂度、真实函数级**基准上，LLM 的覆盖率是 **30–45% 量级**（ULT: statement 45.10% / branch 30.22%），变异得分 **~40%**（ULT: 40.21%）。
- 在 **LeetCode 式简单程序**上同一批模型可到 **92% statement / 82% branch**（TESTEVAL）。
- 在 **TestGenEval**（真实仓库、从零写测试）上最佳模型平均覆盖率仅 **35.2%**。
- 结论：**"LLM 单元测试覆盖率"这一指标在 30%–92% 之间浮动，几乎完全由基准难度与泄漏程度决定，不存在一个可跨论文横比的"前沿覆盖率基线"**。任何把不同基准的覆盖率数值并列成"提升"的表述都不可比。

---

### C·表 2 ｜ 多智能体 / 程序修复（agentic vs agentless）

### 2A. 官方榜单口径（A 级：直接读取官方结果文件）

| 条目（官方目录名） | 系统 + 模型 | 指标 | 值（官方 `resolved`） | 基准 | 一手来源 | 等级 |
|---|---|---|---|---|---|---|
| `20251215_livesweagent_claude-opus-4-5` | live-SWE-agent + Claude 4.5 Opus (medium) | resolve rate | **396/500 = 79.2%** | SWE-bench **Verified** | `…/evaluation/verified/20251215_livesweagent_claude-opus-4-5/results/results.json` | A |
| `20251205_sonar-foundation-agent_claude-opus-4-5` | Sonar Foundation Agent + Claude 4.5 Opus | resolve rate | **396/500 = 79.2%** | Verified | 同仓库对应条目 | A |
| `20250928_trae_doubao_seed_code` | TRAE + Doubao-Seed-Code | resolve rate | **394/500 = 78.8%** | Verified | 同上 | A |
| `20251127_openhands_claude-opus-4-5` | OpenHands + Claude Opus 4.5 | resolve rate | **388/500 = 77.6%** | Verified | 同上 | A |
| `20251120_livesweagent_gemini-3-pro-preview` | live-SWE-agent + Gemini 3 Pro Preview | resolve rate | **387/500 = 77.4%** | Verified | 同上 | A |
| `20260807…`→`20250807_openhands_gpt5` | OpenHands + GPT-5 | resolve rate | **359/500 = 71.8%** | Verified | 同上 | A |
| `20260901_mini-v2.4.2_gemini-3-5-flash` | mini-SWE-agent v2.4.2 + Gemini 3.5 Flash | resolve rate | **71.8%**（官方 metadata；359/500）**最新条目** | Verified | `…/metadata.yaml`（`resolved: 71.8`） | A |
| `20250611_moatless_claude-4-sonnet-20250514` | Moatless Tools + Claude 4 Sonnet | resolve rate | **354/500 = 70.8%** | Verified | 同上 | A |
| `20250519_trae` | TRAE | resolve rate | **353/500 = 70.6%** | Verified | 同上 | A |
| `20241029_OpenHands-CodeAct-2.1-sonnet-20241022` | OpenHands + CodeAct v2.1 | resolve rate | **265/500 = 53.0%** | Verified | 同上 | A |
| `20241202_agentless-1.5_claude-3.5-sonnet-20241022` | Agentless-1.5 + Claude-3.5 Sonnet | resolve rate | **254/500 = 50.8%** | Verified | 同上 | A |
| `20250226_swerl_llama3_70b` | SWE-RL (Llama3-SWE-RL-70B + Agentless Mini) | resolve rate | **206/500 = 41.2%** | Verified | 同上 | A |
| `20241028_agentless-1.5_gpt4o` | Agentless-1.5 + GPT 4o | resolve rate | **194/500 = 38.8%** | Verified | 同上 | A |
| `20240628_autocoderover-v20240620` | AutoCodeRover (v20240620) + GPT 4o | resolve rate | **192/500 = 38.4%** | Verified | 同上 | A |
| `20240612_MASAI_gpt4o` | MASAI + GPT 4o | resolve rate | **163/500 = 32.6%** | Verified | 同上 | A |

**Lite 榜单（官方 300 分母，A 级）**

| 条目 | 系统 + 模型 | 值 | 一手来源 | 等级 |
|---|---|---|---|---|
| `20250625_ExpeRepair-v1_claude-4-sonnet-20250514` | ExpeRepair-v1.0 + Claude 4 Sonnet | **181/300 = 60.3%（Lite 榜首）** | `…/evaluation/lite/…/results/results.json` | A |
| `20250425_Refact_Agent` | Refact.ai Agent | **180/300 = 60.0%** | 同上 | A |
| `20250906_KGCompass_claude-4-sonnet-20250514` | KGCompass + Claude 4 Sonnet | **175/300 = 58.3%** | 同上 | A |
| `20250526_sweagent_claude-4-sonnet-20250514` | SWE-agent + Claude 4 Sonnet | **170/300 = 56.7%** | 同上 | A |
| `20250114_Isoform` | Isoform | **165/300 = 55.0%** | 同上 | A |
| `20241025_OpenHands-CodeAct-2.1-sonnet-20241022` | OpenHands + CodeAct v2.1 | **125/300 = 41.7%** | 同上 | A |
| `20241202_agentless-1.5_claude-3.5-sonnet-20241022` | Agentless-1.5 + Claude-3.5 Sonnet | **122/300 = 40.7%** | 同上 | A |
| `20250114_moatless_claude-3.5-sonnet-20241022` | Moatless Tools + Claude 3.5 Sonnet | **117/300 = 39.0%** | 同上 | A |
| `20250214_agentless_lite_o3_mini` | Agentless Lite + O3 Mini | **97/300 = 32.3%** | 同上 | A |
| `20241028_agentless-1.5_gpt4o` | Agentless-1.5 + GPT 4o | **96/300 = 32.0%** | 同上 | A |
| `20240621_autocoderover-v20240620` | AutoCodeRover (v20240620) + GPT 4o | **92/300 = 30.7%** | 同上 | A |
| `20240630_agentless_gpt4o` | Agentless + GPT 4o | **82/300 = 27.3%** | 同上 | A |
| `20240530_autocoderover-v20240408` | AutoCodeRover (v20240408) + GPT 4 | **57/300 = 19.0%** | 同上 | A |
| `20240402_sweagent_gpt4` | SWE-agent + GPT 4 (1106) | **54/300 = 18.0%** | 同上 | A |

> **榜单状态（A 级一手证据）**
> 1. **Lite 的最后一条官方提交是 `20250911_isea_...`（2025-09-11）**，此后无新条目 → Lite 事实上已停更，不再是活跃竞技场。
> 2. **Verified 仍有新条目**，最新为 `20260901_mini-v2.4.2_gemini-3-5-flash`（2026-09-01）。
> 3. **提交规则重大变更（一手 README 原文）**：`swe-bench/experiments` README 载明 **[11/18/2025] SWE-bench Verified 与 Multilingual 仅接受学术团队/研究机构、方法开源、且有同行评审论文的提交**；明确举例"仍合格：OpenHands、SWE-RL、FrogBoss、AutoCodeRover"，"不再合格：Augment Code、Solver AI、Honeycomb.sh"。Multimodal 榜单不受限。来源：`https://raw.githubusercontent.com/swe-bench/experiments/main/README.md`。
> 4. 官方仓库要求提交者提供**自有公开制品仓库**（`assets.repo`），并提供 `swebench submit verify` 可**从记录的执行输出重新评分**（本仓库校验路径），即榜单结果具备可复算性。

### 2B. 论文自报数值（B 级：arXiv 官方摘要）

| 方法 | 指标 | 值 | 基准 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|---|
| **Agentless** | 最高性能 / 修复数 / 成本 | **32.00%（96 个正确修复）/ $0.70** | SWE-bench **Lite** | https://arxiv.org/abs/2407.01489 | 2024-07 | arXiv 预印本 | B | ① 摘要；② 官方 Lite 榜单 `20240630_agentless_gpt4o` = **82/300 = 27.3%**（GPT-4o，非论文的 GPT-4o 配置口径不同）；`20241028_agentless-1.5_gpt4o` = **32.0%** ← **与论文 32.00% 精确吻合的是 Agentless-1.5，而非初版 Agentless**。此处存在**版本混淆风险** |
| **AutoCodeRover** | SWE-bench-Lite 解决率 / 平均成本 | **19% / $0.43** | SWE-bench Lite | https://arxiv.org/abs/2404.05427 | 2024-04 | **ISSTA 2024**（comment） | B | ① 摘要；② 官方 Lite 榜单 `20240530_autocoderover-v20240408` = **57/300 = 19.0%** ← **精确吻合**，双向交叉验证成立 |
| **SWE-agent** | pass@1 | **12.5%**（SWE-bench 全集）/ **87.7%**（HumanEvalFix） | SWE-bench / HumanEvalFix | https://arxiv.org/abs/2405.15793 | 2024-05 | arXiv 预印本（NeurIPS 2024 D&B） | B | ① 摘要；② 官方 Lite 榜单 `20240402_sweagent_gpt4` = 18.0%（Lite 300）、Verified `20240402_sweagent_gpt4` = 22.4%（500）。⚠️ **12.5% 是全集口径，与任何 Lite/Verified 数值都不可直接比较** |
| **SWE-RL** | solve rate | **41.0%** | SWE-bench **Verified** | https://arxiv.org/abs/2502.18449 | 2025-02（v2 2025-12） | **NeurIPS 2025 Main**（comment） | B | ① 摘要；② 官方 Verified 榜单 `20250226_swerl_llama3_70b` = **206/500 = 41.2%** ← **吻合（0.2pp 差异，应为榜单使用 Agentless Mini 脚手架）**，双向交叉验证成立 |
| **MAGIS** | resolved ratio | **13.94%** | SWE-bench（原版） | https://arxiv.org/abs/2403.17927 | 2024-03（v2 2024-06） | arXiv 预印本 | B | ① 摘要。**官方榜单无 MAGIS 条目**（`evaluation/verified` 与 `evaluation/lite` 均无），故无法二次验证 |
| **RepairAgent** | 修复 bug 数 / 每 bug token 成本 | **164 个 Defects4J bug**（其中 **39 个**为已有技术未修复）/ **270,000 tokens ≈ $0.14** | Defects4J（Java，**非 SWE-bench**） | https://arxiv.org/abs/2403.17134 | 2024-03（v2 2024-10） | arXiv 预印本 | B | ① 摘要。⚠️ **Defects4J ≠ SWE-bench，与表 2A 的任何 resolve rate 都不可比** |
| **SWE-Search** | 相对提升 | **+23% relative**（vs 无 MCTS 的标准开源 agent，跨 5 个模型） | SWE-bench | https://arxiv.org/abs/2410.20285 | 2024-10（v6 2025-04） | arXiv 预印本 | B | ① 摘要。**只报相对提升，未报绝对 resolve rate** → 不可用于跨系统排序 |
| **CodeMonkeys** | resolve rate / 成本 / 集成 | **57.4%**（预算约 **$2,300**）/ 对已有 top 提交做选择集成得 **66.2%** | SWE-bench Verified | https://arxiv.org/abs/2501.14723 | 2025-01（v2 2025-02） | arXiv 预印本 | B | ① 摘要；② 官方榜单**无 CodeMonkeys 条目**。⚠️ **66.2% 是对"他人提交的集成选择"，不是单体系统成绩**，任何把它当作系统 SOTA 的引用都是误读 |
| **Kimi-Dev** | Verified resolve rate / SWE-Agent pass@1 | **60.4%**（workflow/agentless 类最佳）/ **48.6%** pass@1（SFT 适配后） | SWE-bench Verified | https://arxiv.org/abs/2509.23045 | 2025-09（v3 2025-12） | arXiv 预印本（MoonshotAI） | B | ① 摘要；② 官方榜单**无 Kimi-Dev 条目** |
| **Live-SWE-agent** | solve rate（无 test-time scaling）/ SWE-bench Pro | **77.4%** / **45.8%** | Verified / SWE-bench Pro | https://arxiv.org/abs/2511.13646 | 2025-11 | arXiv 预印本（UIUC） | B | ① 摘要的 **77.4%**；② 官方榜单 `20251120_livesweagent_gemini-3-pro-preview` = **387/500 = 77.4%** ← **精确吻合**；③ 官方榜单 `20251215_livesweagent_claude-opus-4-5` = **79.2%**（更高，说明 77.4% 是 Gemini 3 Pro 那一配置）。**三方一致，双重交叉验证成立** |

**表 2 小结（"agentic 是否优于单提示"）**
- **官方榜单层面**：Verified 上 agentic 脚手架（OpenHands / live-SWE-agent / TRAE / Sonar）确实占据高位（77–79%），agentless 血统的 Kimi-Dev（workflow）自报 60.4%。但**榜单本身已丧失区分度**——见下方表 5 的统计证据。
- **反例**：`20250627_agentless_MCTS-Refine-7B` 仅 **116/500 = 23.2%**（Verified）与 **49/300 = 16.3%**（Lite），说明**给 agentless 加搜索并不自动带来增益**；`20250725_sweagent_devstral_small_2507` = 38.0% 与 `20250511_sweagent_lm_32b` = 40.2% 同样处于低位。
- **最关键的复现反例在测试生成方向**（表 1 的 ICST 2026 复现研究），而非修复方向。**本审计未找到修复方向上"agentic 不优于单提示"的同等强度一手复现研究**；这是一个真实的知识缺口。

---

### C·表 3 ｜ 自愈 / 运行时系统评估指标（MTTR、detection latency、recovery quality）

> ⚠️ **本方向是本审计中信噪比最差的一个。** 表内所有条目均为 B 或 C 级，**没有任何一条给出可复算的绝对值 + 官方基准 + 同行评审 venue 三要素齐全的证据**。

| 方法/系统 | 指标 | 指标值 | 基准/实验设置 | 一手来源 | 年份 | venue | 等级 | 问题 |
|---|---|---|---|---|---|---|---|---|
| **Cognitive Platform Engineering** | MTTR / 资源效率 / 合规 | **摘要未给任何数值**（仅称 "demonstrates improvements in mean time to resolution"） | K8s + Terraform + OPA + ML 异常检测原型 | https://arxiv.org/abs/2601.17542 | 2026-01 | arXiv 预印本 | B | 主张 MTTR 改善却**不提供数字**；无法用于建立任何基线 |
| **SF-DTM** | availability / MTBF / MTTR | availability **+13.2%**；MTBF 更高、MTTR 更低（**均未给绝对值**） | 云数字孪生处理，真实 trace | https://arxiv.org/abs/2505.01215 | 2025-05 | arXiv 预印本 | B | 只有相对值；域为数字孪生 VM 分配，**与云原生微服务自愈不可比** |
| **AutoGuard** | threat detection accuracy / MTTR | 检测准确率 **+22%**；MTTR **−38%** | **模拟** CI/CD 环境 | https://arxiv.org/abs/2512.04368 | 2025-12 | IEEE **UPWIECON 2025**（comment） | B | 模拟环境、无绝对值、无基线代码、venue 层级低 |
| **AegisFlow** | MTTR / patch success rate | MTTR **170 min → 3.2 min（+98.1%）**；patch 成功率 **92%**；JSON schema 变更 96%、标点漂移 98%、Shadow DOM 85% | **5 个失败场景**（n=5） | https://arxiv.org/abs/2610.06971 | 2026-10 | arXiv 预印本（43 页） | B | **n=5 的失败场景**支撑 98% 的 MTTR 主张；无独立复现；"释放 98% on-call 时间"属推断 |
| **LLM agent 自愈框架** | task success rate / failure propagation | **摘要未给任何数值**（"significantly increases"） | 多智能体工作流环境 | https://arxiv.org/abs/2605.06737 | 2026-05 | arXiv 预印本 | B | 无数字、无基线 |
| **AutoGuard 类 RL 自愈**（旁证） | — | 见 AutoGuard 行 | — | — | — | — | — | — |

**表 3 关键结论（可直接引用为审计判断）**
1. **"自愈系统 MTTR 降低 X%" 这一指标在 2025–2026 的一手文献中不存在可信的统一基线。** 现有全部一手来源要么只有相对值（SF-DTM、AutoGuard）、要么无数字（2601.17542、2605.06737）、要么建立在 n=5 的模拟场景上（AegisFlow）。
2. **没有任何一篇给出"detection latency"与"recovery quality"的标准化定义与可复算测量协议**（本次检索 `all:"self-healing" AND all:"MTTR"` 仅 3 条命中，`ti:"self-healing" AND cat:cs.SE` 22 条中无一条给出可复算协议）。
3. 因此，**若项目需要"自愈系统前沿基线"这一维度，本审计的结论是：该基线尚未建立，无法对比。** 任何凭单一个人 GitHub README、单作者预印本或 n<10 案例研究得出的 MTTR 数字都不应进入基线表。

---

### C·表 4 ｜ 逻辑驱动 / 神经符号测试生成（符号执行 + LLM、SMT/不变式/后置条件）

| 方法/系统 | 指标 | 指标值 | 基准 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|---|
| **Gordian** | coverage 提升 / token 削减 | coverage **+28.5–115.2%** vs 传统符号执行基线；**+74.1–189.8%** vs LLM-based 符号执行基线；LLM token 用量平均 **−91–96%** | 合成 "logic bombs" + FDLibM 数学库 + 四个结构化输入程序（libexpat, jq, bc, libyaml）；实现于 **KLEE** | DOI `10.1145/3832126`（Crossref 元数据 + 摘要全文） | 公开日期 2026-10-01 | **PACMSE Vol.3, Issue ISSTA, pp. 802–823** | **A**（DOI/卷期页/摘要三方一致） | ① Crossref 结构化记录；② OpenAlex 同一条目（标题/年/DOI 一致）；③ 作者 Dimitrios Stamatios Bouras, Sergey Mechtaev。⚠️ **基线口径必须写清**：`+28.5–115.2%` 是**相对传统符号执行**，不是相对一般测试生成工具；且**任务简报中给出的目标程序名（如 libyaml 等）与 DOI 记录一致** |
| **TestTailor** | statement / branch coverage 提升 / 成本 | 摘要给出方法（path-proximal tests + 符号约束），**具体数值本次未取得** | Python（对照 CoverUp） | DOI `10.1145/3797140`（Crossref 元数据 + 摘要） | 2026-06-30 | **PACMSE Vol.3, Issue FSE, pp. 277–298** | **A**（DOI/卷期页/作者）+ 🚫（数值未取得） | ① Crossref 完整记录（作者 Xiaoxuan Zhou, Yiling Lou, Jinhao Dong, Dan Hao）；② **arXiv 全库 `all:"TestTailor"` = 0 命中** ← 说明**只在 Crossref 可查、不在 arXiv**，属"能验证存在、不能验证数值" |
| **SpecGen** | 可验证规约生成数 | **279 / 385** 程序成功生成可验证规约 | SV-COMP Java 类别基准 + 自建数据集；对照 Houdini、Daikon | https://arxiv.org/abs/2401.08807 | 2024-01（v5 2025-02） | arXiv 预印本 | B | ① 原文摘要；② `all:"SpecGen"` 9 条命中中存在同名异域论文（神经 BRDF、RGBT 视觉），**引用时必须用 id 而非名字** |
| **nl2postcond** | 捕获的真实历史 bug 数 | **64 个 Defects4J 真实历史 bug** | Defects4J | https://arxiv.org/abs/2310.01831 | 2023-10（v2 2024-04） | **PACMSE / FSE 2024**（comment） | B | ① 原文摘要；② `all:"NL2Postcond"` 仅 2 条命中，无歧义。注意：**nl2postcond 是问题命名（problem），不是系统名** |
| **AssertFlip** | fail-to-pass 成功率 | **43.6%** | **SWT-Bench Verified**（bug 可复现测试基准） | https://arxiv.org/abs/2507.17542 | 2025-07（v2 2026-01） | arXiv 预印本 | B | ① 原文摘要自称"outperforms all known techniques in the leaderboard of SWT-Bench"。**未独立打开 SWT-Bench 官方榜单二次验证** |
| **SWE-Proof / Benchproofer** | 形式化验证 vs 测试的差异 / 规格质量 | **1/4 通过测试的补丁存在反例**；正确形式化规约把 resolution 从 **85% → 95%**；自行撰写规约的 agent **不比无辅助基线更好**；仅 **56%** 的规格通过审计；规格质量在未解决实例上失败率 **92%** vs 已解决 **51%** | SWE-bench Verified 的 500 个 issue（形式化重铸） | https://arxiv.org/abs/2609.21190 | 2026-09 | arXiv 预印本 | B | ① 原文摘要；② 引用了 ImpossibleBench 之外的独立评测对象 Claude Opus 4.8。⚠️ **"85% → 95%" 是特定模型在形式化规约条件下的 resolution，不是通用基线** |
| **ImpossibleBench** | cheating rate（规格-测试冲突下通过率） | 摘要给出方法，**未给单一数值**（框架型论文） | LiveCodeBench + SWE-bench 的 "impossible" 变体 | https://arxiv.org/abs/2510.20270 | 2025-10 | arXiv 预印本 | B | ① 原文摘要；② GitHub `safety-research/impossiblebench` 在摘要中给出。**这是评估"LLM 是否真的解决问题还是改测试"的关键工具** |
| **符号执行 + LLM 相关（检索为负）** | — | **未找到** | — | — | — | — | **D** | `all:"CodeQL" AND abs:"test generation"` = **0 命中**；`ti:"AID" AND abs:"unit test generation"` = 0；`all:"HumanEvalJava"` = **0 命中**；`all:"HumanEval-J"` = **0 命中**。→ **"CodeQL 引导的测试生成"与"HumanEvalJava / HumanEval-J 作为 LLM 单元测试基准"这两个说法，本次检索未能取得任何一手来源** |

**表 4 小结**
- **神经符号方向唯一达到 A 级（DOI + 卷期页 + 摘要一致）的条目是 Gordian（KLEE + LLM ghost code）与 TestTailor（PACMSE FSE 2026，路径邻近测试 + 符号约束）。**
- 两者都是**"符号/形式化组件提供细粒度路径或约束引导，LLM 负责生成"**，且都明确以 KLEE 或符号约束为核心 —— 这与简报中"符号执行+LLM、SMT/不变式"的方向一致，**方向本身有一手支撑，不存在"疑似不存在"的问题；被证伪的是具体数字的可用性**（TestTailor 数值未取得）。
- **"CodeQL 引导"这一具体技术路线在一手文献中无命中**，建议在基线表中删除或标注为未建立。

---

### C·表 5 ｜ 评估基准与方法学（SWE-bench 榜单状态、非确定性、统计显著性）

| 主题 | 关键发现 | 数值 | 一手来源 | 年份 | venue | 等级 | 交叉验证 |
|---|---|---|---|---|---|---|---|
| **SWE-bench 榜单提交规则变更** | Verified/Multilingual 仅收学术机构 + 开源方法 + 有同行评审论文 | 生效日 **2025-11-18**；仍合格举例 OpenHands、SWE-RL、FrogBoss、AutoCodeRover；不再合格 Augment Code、Solver AI、Honeycomb.sh | `raw.githubusercontent.com/swe-bench/experiments/main/README.md` | 2025-11-18 | 官方仓库政策 | **A** | ① 官方 README 原文；② `https://www.swebench.com/submit.html` 指向同一仓库与流程 |
| **SWE-bench 官方可复算性** | 提交须附自有公开制品仓库；`swebench submit verify` 可**从记录的执行输出重新评分**，不需 Docker 重跑 | — | 官方 README + submit.html | 2026 | 官方文档 | **A** | ① README 命令示例；② submit.html 页面 |
| **榜单已失去区分度（核心方法学证据）** | Verified 前两名**各解 396/500**；前 10 名共享 **285** 个成功与 **51** 个失败，只有 **164** 个实例能区分它们；frontier 解集 median nesting **0.935**（对照 score-implied baseline 0.774）；**29 对相邻 top-30 的精确配对 McNemar 检验在 α=0.05 下全部不显著（0/29）**；Test split 上 23 对中有 14 对显著；within-model scaffold 极差达 **29.8pp**，而 top-30 的总分跨度仅 **8.8pp** | 见左 | https://arxiv.org/abs/2609.17394 | 2026-09-15 | **ADMA 2026**（comment；Special Session on Responsible Data Intelligence） | B（原文摘要）；**与官方榜单 A 级数据一致** | ① 原文摘要；② **本审计独立从官方 `results.json` 读到 `20251215_livesweagent_…` = 396/500 与 `20251205_sonar-foundation-agent_…` = 396/500** ← **"前两名各 396/500" 与本审计的 A 级扫描精确吻合，交叉验证成立** |
| **SWE-bench 生态构成审计** | 分析 **79** 条 Lite + **133** 条 Verified 提交 | 结论：两个榜单的多数提交来自产业界（小公司与大型上市公司），且常居榜首；学术贡献（通常开源）仍具竞争力；**专有 LLM（尤其 Claude 系）占主导** | https://arxiv.org/abs/2602.04449 | 2026-02 | **ICSE-SEIP 2026**（comment，DOI `10.1145/3786583.3786904`） | B | ① 原文摘要；② 与本审计的 182 条 Verified / 84 条 Lite 目录扫描**量级一致**（论文统计时点更早，另有部分条目被拒/合并） |
| **LLM-as-Judge 判定非确定性** | 同一 temperature=0 判定器、同一服务端版本，**重复运行仍产生不同判定**；per-item flip rate 平均约 **5%**，在决定榜单名次的 close-call 项上约 **40%**；单判定器幅度跨 **40×**（**0.13% – 近 10%**）；主判定器聚合排名稳定（0% top-K 不稳），但配对层级 bootstrap 下**约 1/5 至 3/4 的相邻名次统计上不可区分**；Gemini 与 Sonnet 判定器在 Arena-Hard 上 Kendall's τ = **0.42–0.64**；15 个预期头对头排序中仅 8 个在所有判定器下都成立 | 见左 | https://arxiv.org/abs/2609.33044 | 2026-09-27（v2 2026-09-30） | arXiv 预印本（单作者） | B | ① 原文摘要；② 与本表 2609.17394 的"相邻无效"结论**方向一致且互相独立**（一个针对 judge，一个针对 SWE-bench 榜单） |
| **判定器偏差的方差分解** | 将 benchmark 得分方差分解为 scenario / generation / judge / residual 四分量；judge 偏差**无法通过增加场景或生成数平均掉**；提出 CyclicJudge 轮转分配判定器，在固定判定器与调用预算下精确恢复 panel 均值 | — | https://arxiv.org/abs/2603.01865 | 2026-03（v3 2026-05） | arXiv 预印本 | B | ① 原文摘要；② 与 2609.33044 的"单判定器不可靠"结论互为佐证 |
| **真实评测中的作弊/走捷径度量** | ImpossibleBench：构造规格与测试直接冲突的 "impossible" 任务，pass rate 即 cheating rate | 摘要**未给单一数值** | https://arxiv.org/abs/2510.20270 | 2025-10 | arXiv 预印本 | B | 见上 |

**表 5 小结（方法学硬约束）**
1. **"SWE-bench Verified 上 A 比 B 高 X 个点"在 top-30 内几乎全部不具统计显著性**（0/29 相邻对通过 McNemar）。任何以几个百分点的差距论证"本系统优于前沿系统"的表述，在有 500 实例的 Verified 上**不成立**。这有 A 级官方数据 + 独立方法学论文双重支撑。
2. **单次评测的分数波动来源已有一手量化**：per-item flip ~5%、close-call ~40%（LLM-as-judge）；within-model scaffold 极差 29.8pp（远大于系统间差异 8.8pp）。**"多运行取均值 + 报告方差/置信区间 + 配对检验"是必要而非可选的报告项。**
3. **榜单已有政策层面的开放性收缩**（2025-11-18 起），且 **Lite 已事实停更**（最后条目 2025-09-11）。以 Lite 作为主竞技场已过时。

---

### C.6 交叉验证与冲突说明（≥8 个数据点做了两个独立来源）

| # | 数据点 | 来源 1 | 来源 2 | 结论 |
|---|---|---|---|---|
| 1 | live-SWE-agent **77.4%** Verified | arXiv:2511.13646 摘要自报 77.4% | 官方榜单 `20251120_livesweagent_gemini-3-pro-preview` = 387/500 = **77.4%** | **精确吻合**，且榜单另有一条 79.2%（Claude 4.5 Opus 配置）说明 77.4% 的模型归属 |
| 2 | Verified 前两名各 **396/500** | arXiv:2609.17394（Lead 独立核验 + 本审计核验） | 本审计从官方 `results.json` 逐条读取：`20251215_livesweagent…`=396、`20251205_sonar…`=396 | **精确吻合** |
| 3 | AutoCodeRover **19%** Lite | arXiv:2404.05427 摘要 19% | 官方 Lite `20240530_autocoderover-v20240408` = 57/300 = **19.0%** | **精确吻合** |
| 4 | SWE-RL **41.0%** Verified | arXiv:2502.18449 摘要 41.0% | 官方 `20250226_swerl_llama3_70b` = 206/500 = **41.2%** | 吻合（0.2pp，应为脚手架差异） |
| 5 | Agentless **32.00%** Lite | arXiv:2407.01489 摘要 32.00%（96 fixes） | 官方 Lite：`20240630_agentless_gpt4o` = **27.3%**；`20241028_agentless-1.5_gpt4o` = **32.0%** | ⚠️ **冲突已定位**：与 32.00% 吻合的是 **Agentless-1.5**，非初版 Agentless。**引用时必须区分版本** |
| 6 | Gordian DOI `10.1145/3832126` | Crossref 结构化记录（标题/作者/PACMSE Vol.3 ISSTA/pp.802-823/摘要） | OpenAlex 同条目（标题/年/DOI 一致） | **一致**。但**基线口径需纠正**：+28.5–115.2% 是相对**传统符号执行** |
| 7 | TestGenEval 的 arXiv id | 任务简报称 2502.02794 | arXiv API：**2502.02794 = METAMON**；`ti:"TestGenEval"` → **2410.00752** | ⚠️ **简报映射错误，已一手证伪** |
| 8 | ULT 的四个指标 | arXiv:2508.00408 摘要 | arXiv:2608.24473（Ockhamareto）全文引用 ULT（`all:"UnLeakedTestbench"` 命中） | 一致 |
| 9 | CANDOR 的存在性与对手 | arXiv:2506.02943 摘要 | `all:"CANDOR" AND cat:cs.SE` 唯一命中即该文；对手 TOGLL 独立存在（2405.03786） | 系统真实存在；**venue 未取得一手证据（项目称 TOSEM 2026，本次 D 级）** |
| 10 | AdverTest / 复现研究 | arXiv:2602.08146、arXiv:2601.09695 摘要 | **Lead 独立核验的 DOI**（10.1145/3832122 / 10.1109/icst69053.2026.00040） | 一致（跨成员交叉验证） |
| 11 | AID 是否存在 | 搜索片段指向 arXiv:2404.10304 "We propose AID" | arXiv API v1 摘要确含 AID；v2 摘要已改名 **TrickCatcher**（ACL 2025） | 存在，但**因更名导致按名字检索失败**；引用必须用 id 或新名 |
| 12 | TestTailor 是否存在 | 项目文档称 FSE 2026 | Crossref DOI `10.1145/3797140`：PACMSE Vol.3 FSE, pp.277-298, 2026-06-30；**arXiv `all:"TestTailor"` = 0** | 存在，但**仅 Crossref 可查**；数值未取得 |

### 未解决的冲突 / 无法判断项
- **MAGIS 13.94%**、**CodeMonkeys 57.4% / 66.2%**、**Kimi-Dev 60.4%**、**RepairAgent 164 bugs**、**SWE-Search +23%**：均**只有论文自报，无官方榜单条目可二次验证**（B 级单源）。
- **CANDOR 的 venue**：项目文档称 TOSEM 2026，arXiv comment 未载明 → 本次未能取得一手 venue 证据（D）。**注意：arXiv v7 更新至 2026-03，与"TOSEM 2026"不矛盾，但也不构成证据。**
- **TestPilot 的口径**：真实存在（arXiv:2302.06527），但它是 **JavaScript/npm** 工具。"LLM 单元测试生成"若在 Java 语境引用 TestPilot 数值，属**基准错配**。

---

### C.7 "疑似不存在 / 无法验证"清单（含实际检索词与返回）

| 名称 | 声称（仅在项目文档或简报中出现） | 实际检索 | 返回 | 判定 |
|---|---|---|---|---|
| **TwinMem / TwinMem-Agent** | 项目文档提及 "TwinMem-Agent 的 89.1%" | `all:"TwinMem"`（arXiv API） | `TOTAL: 0` | **D — 未取得任何一手来源，疑似不存在** |
| **ARC-APR** | 项目文档称"疑似不存在" | `all:"ARC-APR"` | 仅 1 条无关命中（APR-Transformer 绝对位姿回归，arXiv:2505.09356，机器人定位） | **D — 疑似不存在**（与项目文档判断一致） |
| **Defects4J v3 / Defects4J version 3** | 项目文档提及 | `all:"Defects4J v3"`；`all:"Defects4J" AND all:"version 3"` | 两条查询均 `TOTAL: 0` | **D — 未取得一手来源，疑似不存在** |
| **AgentRepair** | 项目文档称"无可获取指标" | arXiv `all:"AgentRepair"` = **0**；Crossref 检索 | Crossref 命中：**"AgentRepair: Multi-Agent, AST-Anchored, Retrieval-Augmented Program Repair for Cold-Start Environments"**，*2025 12th Int'l Conf. on Dependable Systems and Their Applications (DSA)*，DOI `10.1109/dsa66321.2025.00025` | **存在但数值不可及（C/D）**：论文真实存在，**IEEE 付费墙，摘要与指标未能取得**。项目文档"无可获取指标"的结论**成立**，但"疑似不存在"的措辞**不准确** |
| **TestTailor** | 项目文档称 FSE 2026 | arXiv `all:"TestTailor"` = **0**；Crossref `query.bibliographic=TestTailor…` | Crossref 命中 DOI `10.1145/3797140`，PACMSE Vol.3 Issue FSE, pp.277-298 | **存在（A 级存在性）**，但**数值未取得** → 不得引用其数字 |
| **CodeQL 引导的测试生成** | 简报列为需覆盖方向 | `all:"CodeQL" AND abs:"test generation"`（arXiv） | `TOTAL: 0` | **D — 未取得一手来源**；建议标注"该技术路线未建立基线" |
| **HumanEvalJava / HumanEval-J（作为 LLM 单元测试基准）** | 简报列为需覆盖基准 | `all:"HumanEvalJava"`；`all:"HumanEval-J"` | 两条查询均 `TOTAL: 0` | **D — 未取得一手来源**。⚠️ APR 文献中的 "HumanEval-Java" 需另行核验，本次**未取得** |
| **"test generation" 的 "简单提示即够" 复现研究** | 简报要求覆盖 | `abs:"test generation" AND abs:"simple prompting"` | 仅 1 条弱相关（AugmenTest, arXiv:2501.17461）；**但通过 `all:"SymPrompt"` 反向命中 2601.09695（ICST 2026）** | **存在，已取得**（见表 1 反例行）——检索词需调整才能命中 |
| **AID（按名字检索）** | 简报列为需覆盖 | `ti:"AID" AND abs:"unit test generation"` = 0；`all:"AID" AND abs:"unit test" AND cat:cs.SE` = 7 条全部无关 | 需通过 `all:"SymPrompt"` 路径与搜索片段才回溯到 arXiv:2404.10304 | **存在但已更名 TrickCatcher**；**按旧名检索必然失败** |
| **TestGenEval（按 arXiv:2502.02794 检索）** | 简报给出的 id | arXiv API `id_list=2502.02794` | 返回 **METAMON: Finding Inconsistencies between Program Documentation and Behavior using Metamorphic LLM Queries**（Lee, An, Yoo, LLM4Code 2025） | **id 映射错误**；TestGenEval 真实 id = **2410.00752** |
| **GORDIAN（按名称 + arXiv 检索）** | 项目文档称 PACMSE DOI 10.1145/3832126 | `all:"GORDIAN"`（arXiv）= 91 条，前 5 条全为纽结理论 | 通过 **Crossref DOI 直查**才命中 | **存在（A 级）**；**仅靠 arXiv 名称检索会误判为不存在** |
| **TestPilot（按名称）** | 简报列为需覆盖 | `ti:"TestPilot"`（arXiv）= **0**（标题不含该词） | 需 `web_search` + `all:"TestPilot"` 反向定位到 arXiv:2302.06527 | **存在**；标题检索失败 |

#### C.7.1 由本清单导出的检索方法学警告（对项目同样适用）
1. **"arXiv 标题检索 0 命中" ≠ "不存在"**。已出现 3 个反例：GORDIAN（DOI 只在 Crossref）、TestTailor（只在 Crossref/PACMSE）、TestPilot（系统名不在标题里）。
2. **"arXiv 名称检索命中无关论文" ≠ "不存在"**。CANDOR 的 3 条无关命中（off-policy evaluation / unanswerability / 音视频语音识别）极易被误判为伪造。
3. **系统更名会造成"检索性不存在"**：AID → TrickCatcher 是实例。
4. 因此，判"疑似不存在"必须满足：**arXiv（名称 + 标题 + 全文）× Crossref（bibliographic）× OpenAlex（search）四路均无命中**，并在产出中写明全部检索词。本清单中真正满足此标准的只有 **TwinMem、ARC-APR、Defects4J v3、CodeQL-guided test generation、HumanEvalJava**。

---

### C.8 未完成 / 无法核验清单（供 Lead 判断哪些维度"基线未建立"）

| # | 目标 | 已尝试的检索词 / 端点 | 结果与原因 |
|---|---|---|---|
| 1 | **SWE-bench 官网榜单 HTML 表格** | `web_fetch https://www.swebench.com/verified.html`、`curl https://www.swebench.com/index.html` | 前者 30s 超时，后者 60s 连接超时。**已用官方榜单仓库逐条结果文件替代（更一手）**，故不影响结论 |
| 2 | **DBLP 全库核验** | `https://dblp.org/search/publ/api?q=…&format=json`（含浏览器 UA） | **Anubis 反爬返回 bot 校验页**。DBLP 完全未用上；**任何依赖 DBLP 的 venue 判定（尤其 CANDOR 的 TOSEM 2026）本次无法完成** |
| 3 | **Semantic Scholar 交叉验证** | `api.semanticscholar.org/graph/v1/paper/search` | HTTP **429**，未取得数据 |
| 4 | **HITS 的覆盖/变异具体数值** | arXiv:2408.11324 摘要；`all:"HITS"` | **摘要只写 "significantly outperforms"，无数字**；正文表格未逐页核对 → **数值未取得一手来源** |
| 5 | **TestSpark 的效果数值** | arXiv:2401.06580 摘要 | 工具型 demo 论文，**摘要无覆盖/变异数值** → 未取得 |
| 6 | **ChatUniTest 的具体覆盖率** | arXiv:2305.04764 摘要 | 只写"在半数项目上最优"，**无百分数** → 未取得 |
| 7 | **CANDOR 的 venue（TOSEM 2026?）与绝对 mutation score** | arXiv:2506.02943 摘要 + comment 字段；DBLP（失败） | arXiv comment **未载明 venue**；摘要只给"≥21.1pp vs TOGLL"与"mutation score 明显更优"，**无绝对值** → venue 与绝对值均未取得 |
| 8 | **TestTailor 的 statement/branch 提升与成本** | Crossref DOI 记录摘要（截断）；arXiv（0 命中） | Crossref 摘要被截断且**未含数值**；全文付费墙 → **数值未取得** |
| 9 | **AgentRepair 的任何指标** | arXiv（0）、Crossref（命中 DSA 2025）、DOI 全文 | **IEEE 付费墙**，摘要与指标不可得 → **未取得** |
| 10 | **SWT-Bench 官方榜单现状** | 未找到公开榜单端点（`all:"SWT-Bench"` 未返回榜单地址） | AssertFlip 43.6% **仅有论文自报**，未做榜单二次验证 |
| 11 | **MAGIS / CodeMonkeys / Kimi-Dev / SWE-Search 的官方榜单条目** | 逐条扫描 `evaluation/verified`（182 条）与 `evaluation/lite`（84 条） | **四者均无官方条目** → 只能保留 B 级单源 |
| 12 | **"defect detection rate" 的统一口径** | 检索多个候选定义 | 未找到标准化定义（不同论文分别用 fault detection rate / FDR / 检出 bug 数 / mutation score）→ **该指标目前不可跨论文比较** |
| 13 | **自愈系统的 detection latency / recovery quality 标准协议** | `all:"self-healing" AND all:"MTTR"`、`ti:"self-healing" AND cat:cs.SE`（22 条）、`all:"mean time to repair" AND all:"cloud"`、`ti:"AIOps" AND abs:"root cause"` | **无任何一篇给出可复算的标准化协议与绝对值** → **判：该维度前沿基线未建立，无法对比** |
| 14 | **CodeQL 引导的测试生成** | `all:"CodeQL" AND abs:"test generation"` | `TOTAL: 0` → **该技术路线无一手基线** |
| 15 | **HumanEvalJava / HumanEval-J 作为 LLM 单元测试生成基准** | `all:"HumanEvalJava"`、`all:"HumanEval-J"` | 均 `TOTAL: 0` → **未取得**。APR 文献中的 HumanEval-Java **本次未核验** |
| 16 | **修复方向"agentic 不优于单提示"的复现研究** | 多组检索（`test generation` + `simple prompting`、`SymPrompt` 反向路径等） | 复现反例**只在测试生成方向找到**（ICST 2026）；**修复方向未找到同等强度的一手复现研究** → 真实知识缺口 |
| 17 | **GORDIAN 的实验条件细节**（哪些 benchmark 贡献了区间端点） | Crossref 摘要（完整）+ OpenAlex | 区间端点对应哪些程序**摘要未逐项对应**；全文付费墙 → **区间已取得，端点归属未取得** |

---

### C.9 本审计给出的"最高置信度前沿基线"（仅 A 级与强 B 级）

1. **SWE-bench Verified 官方榜首（并列）：396/500 = 79.2%** — live-SWE-agent + Claude 4.5 Opus（`20251215`）与 Sonar Foundation Agent + Claude 4.5 Opus（`20251205`）。**A 级，可逐条复算。**
2. **SWE-bench Lite 官方榜首：181/300 = 60.3%** — ExpeRepair-v1.0 + Claude 4 Sonnet（`20250625`）。**A 级。Lite 已于 2025-09-11 后停更。**
3. **SWE-bench Verified 最新条目：71.8%（359/500）** — mini-SWE-agent v2.4.2 + Gemini 3.5 Flash（`20260901`）。**A 级，且暴露 441 vs 500 分母陷阱。**
4. **Agentless 血统最强 workflow 系统：Kimi-Dev 60.4%**（Verified，自报，B 级单源）。
5. **LLM 单元测试生成的"真实"覆盖率区间：ULT 上 statement 45.10% / branch 30.22% / mutation 40.21%**（3,909 抗泄漏任务，12 模型均值，B 级）；同批模型在 TESTEVAL 上 92.18% / 82.04% / 49.69% → **覆盖率指标跨基准不可比**。
6. **最强反例（方法学价值最高）：纯提示基线在 line/branch/mutation 上分别反超 HITS/SymPrompt/TestSpark/CoverUp 17.72 / 19.80 / 20.92 个百分点**（393 类 / 3,657 方法，ICST 2026，B 级 + Lead 核验 DOI）。
7. **神经符号唯一 A 级基线：Gordian（KLEE + LLM ghost code）覆盖率 +28.5–115.2% vs 传统符号执行、+74.1–189.8% vs LLM-based 符号执行、token −91–96%**（PACMSE Vol.3 ISSTA, pp.802-823, DOI `10.1145/3832126`）。
8. **榜单区分度已失效：Verified 前两名各 396/500，29 对相邻 top-30 的 McNemar 检验 0 对显著**（arXiv:2609.17394 + 本审计官方数据交叉验证）。
9. **评测非确定性的量化下界：LLM-as-Judge per-item flip ~5%、close-call ~40%、单判定器幅度 0.13%–10%**（arXiv:2609.33044）。
10. **自愈方向：无任何可信前沿基线**（表 3 全部为无绝对值、模拟环境或 n=5 的 B 级来源）。

---

### C.10 可被项目直接引用的 6 条"引用纪律"（由本审计一手证据导出）

1. **不得把不同基准的 coverage/mutation 数值并列成"提升"** —— ULT vs TESTEVAL 的 30.22% vs 82.04% branch 差异来自基准难度与泄漏，不是方法差异。
2. **不得用 top-30 内的几个百分点差论证优劣** —— 0/29 相邻对通过 McNemar；within-model scaffold 极差 29.8pp > top-30 总跨度 8.8pp。
3. **不得把 Agentless 与 Agentless-1.5 混为一条基线** —— 论文 32.00% 对应 **Agentless-1.5**；初版官方榜单为 27.3%。
4. **不得把 CodeMonkeys 的 66.2% 当作单体系统成绩** —— 那是对已有 top 提交做集成选择的结果。
5. **不得把 Gordian 的 +28.5–115.2% 当作"相对一般测试生成工具"的提升** —— 基线是**传统符号执行**。
6. **凡引用 SWE-bench resolve rate，必须写明 split（Verified 500 / Lite 300 / 全集 2,294）、脚手架、模型版本与推理预算**；本审计已证明同一系统换模型/脚手架可差 29.8pp。

---

*本文件所有数值均来自第 0 节列出的端点，检索日期 2026-10-11。未使用任何项目内文档中的前沿数字。凡未能打开原文核对者均已标注 B/C/D 级并写明"未取得一手来源"。*



---

## 附录 D｜引用与前沿数字真实性核验（42 DOI + 72 arXiv ID）

> 源文件：`audit_2026/T_D_citation_verification.md`（本附录为该文件的完整内容，仅调整标题层级与编号）

### D·T-D 引用与前沿数字真实性核验（独立核验报告）

- **任务**：task-4 — 对项目文档与既有评审中出现的全部文献引用与前沿数字做真实性与一手性核验
- **核验人**：citation-verifier（独立评审团队 T-D）
- **核验日期**：2026-10-11
- **核验范围**：`README.md`（含首 1-60 行）、`README.en.md`、`REVIEW_2026_FRONTIER.md`、`review_2026/R1_frontier_testgen.md`、`R2_frontier_repair.md`、`R3_frontier_logic.md`、`E4_R3_logic_frontier.md`
- **纪律声明**：本报告每条判定均附**实际访问的 URL** 与**实际观察到的返回**。未使用记忆填充。端点不可达的情况已如实标注。

---

### D.0 核验方法、覆盖度与端点可达性

#### D.0.1 实际使用的可机读端点

| 端点 | 用途 | 本次可达性 |
|---|---|---|
| `https://api.crossref.org/works/<doi>` | DOI 权威注册元数据（标题/作者/venue/年份） | ✅ HTTP 200（curl，UA 带 mailto） |
| `https://export.arxiv.org/api/query?id_list=...` | arXiv Atom 元数据（标题/作者/comment/journal_ref/DOI） | ✅ HTTP 200（分批 10 个/请求） |
| `https://arxiv.org/abs/<id>`、`https://arxiv.org/html/<id>vN` | 一手全文与版本核查 | ✅ HTTP 200 |
| `https://api.openalex.org/works`、`/works/doi:<doi>` | 交叉元数据、venue、机构、摘要倒排索引 | ✅ HTTP 200 |
| `https://api.semanticscholar.org/graph/v1/paper/<id>` | 摘要（IEEE 付费墙替代路径） | ⚠️ 初始 **HTTP 429**「Too Many Requests」，退避重试后 ✅ 成功 |
| `https://doi.org/<doi>` | DOI 解析与重定向终址 | ✅（返回 403/202 为出版商反爬，非 DOI 失效） |
| `https://api.datacite.org/dois/<doi>` | Zenodo 等 DataCite 注册 DOI | ✅ HTTP 200 |
| `https://dblp.org/search/publ/api`、`https://dblp.org/search` | DBLP 检索 | ❌ **端点不可达**：被 Anubis v1.27.0 反爬挑战拦截（返回 "Making sure you're not a bot!"）。已改用 OpenAlex + Crossref + S2 替代 |
| `https://ieeexplore.ieee.org/document/<id>` | IEEE Xplore | ⚠️ **HTTP 202 空响应**（反爬），正文不可抓。已改用 Crossref/OpenAlex/S2 摘要替代 |
| `web_search` / `web_fetch` | 补充定位（会议官网、IBM Research、计算机学会 CSDL） | ✅ |

> **方法论要点（重要，避免误判）**：Zenodo 的 `10.5281/*` DOI 由 **DataCite** 而非 Crossref 注册。因此 Crossref 返回 404 **不代表 DOI 不存在**。本次已对每个 Zenodo DOI 单独走 `doi.org` + DataCite 双通道复核。

#### D.0.2 覆盖度

| 类别 | 抽取数量 | 核验结果 |
|---|---|---|
| 唯一 DOI（正则抽取自 7 份文档） | **42** | Crossref 200 → **40**；Crossref 404 → **2**（均为 Zenodo）。其中 `zenodo.14502996` 经 DataCite/doi.org 确认为**真实**（TSC2CARLA artifact，DLR）；`zenodo.1234567` 经 doi.org + DataCite 双重 404，为**占位符**，且**项目自身已正确标注**其为第三方记录不严谨的证据（`review_2026/E4_R3_logic_frontier.md:99`）|
| 唯一 arXiv ID | **72** | arXiv API **72/72 全部返回有效 `<entry>`**；**0 个返回 no-paper/404**。即：**项目中不存在任何伪造的 arXiv ID** |
| 提示词重点怀疑清单（20 个系统名） | 20 | **17 个确认为真实存在**（多数带一手指标逐字命中）；2 个为项目自身已标注的"不可引用来源"；1 个在项目文档中根本不存在 |
| 6 个重点 DOI + 2 个重点 arXiv ID | 8 | **全部真实存在**，且 **5 个的双参数指标原文逐字命中** |

#### D.0.3 关于"提示词怀疑清单"的整体结论（最重要的元发现）

> 任务提示词给出的"很可能是幻觉"的 20 个系统名与 6 个 DOI，经逐条一手核验后：**绝大多数是真实的**。
> 唯一被确证"无任何一手记录"的是 **ARC-APR**；另有 **"85% MTTR reduction"** 与 **ESBMC-AI** 无一手来源（二者项目已自行标注）。
> **反过来，本次核验真正查出的是项目自身评审中的 3 处实质错误**（见 §3）——其中 `Defects4J v3 不存在` 是**明确的事实性错误**。

---

### D.1 引用核验表（核心产出）

证据等级：**A** = 机读权威元数据 + 一手全文/摘要逐字命中；**B** = 机读元数据 + 一手摘要命中，细节未逐字；**C** = 仅元数据存在性；**D** = 未能核验。

#### D.1.1 提示词指定的 6 个重点 DOI + 2 个重点 arXiv ID

| # | 出现位置 | 原引用文本（摘要） | 核验方法（实际 URL） | 核验结果 | 一手指标值（实际观察） | 等级 | 结论 |
|---|---|---|---|---|---|---|---|
| D1 | `README.md:21-23`；`REVIEW_2026_FRONTIER.md:1193`(E7)；`R1:24` | CANDOR（Xu, Wang, Briand, Liu）"TOSEM 2026, DOI 10.1145/3803418"，line/branch/mutation 0.991/0.970/0.980（HumanEvalJava） | ① `https://api.crossref.org/works/10.1145/3803418` → **HTTP 200**；② `https://export.arxiv.org/api/query?id_list=2506.02943`；③ `https://arxiv.org/html/2506.02943v3` → HTTP 200（187,558 B） | ✅ **存在，元数据完全一致** | Crossref：title = *"Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation"*；authors = Qinghua Xu / Guancheng Wang / Lionel Briand / Kui Liu；container = *ACM Transactions on Software Engineering and Methodology*；published = **2026-03-25**。全文逐字命中：`CANDOR 0.991* 0.970 0.980* (2384/2443)`，数据集为 **HumanEvalJava / LeetCode-Medium / LeetCode-Hard**，基线为 **EvoSuite + LLM-Empirical** | **A** | ✅ **真实**。DOI/作者/venue/年份/系统名/三指标**全部一致** |
| D2 | `README.md:24`；`REVIEW_2026_FRONTIER.md:1195`(E8) | TestAgent "FSE Companion 2026, DOI 10.1145/3803437.3806428"，line 92.34% / mutation 83.69% | ① `https://api.crossref.org/works/10.1145/3803437.3806428` → **HTTP 200**；② `https://arxiv.org/html/2607.09101v1` → HTTP 200 | ✅ **存在，指标为一手数据** | Crossref：*"TestAgent: A Multi-Agent LLM Framework for Repository-Level Test Generation"*；event = **FSE Companion '26**；published 2026-07-05。arXiv 全文逐字："TestAgent achieves **97.46%** execution rate, **92.34%** line coverage, **90.24%** branch coverage, and **83.69%** mutation score on **six Java projects**" | **A** | ✅ **真实**。⚠️ 两处瑕疵见 §3 |
| D3 | `README.md:15-18`；`README.en.md:19`；`REVIEW_2026_FRONTIER.md:1194`(E25b) | IEEE 独立复现（Radaideh & Corriveau，Xplore **11655121**）：one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**；one-shot GPT-4o **69.90%** vs CANDOR **45.63%** | ① `https://api.openalex.org/works?search=...` → 命中 DOI；② `https://api.crossref.org/works/10.1109/bdai70753.2026.11655121` → **HTTP 200**；③ `https://api.semanticscholar.org/graph/v1/paper/8eab00f0df57a59a3a536d153dc01ce8f7695372`（退避后成功）取摘要 | ✅ **存在；四指标 + "45s vs 50h" 全部逐字命中** | 标题 *"Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation: A Comparison with Human-Written Tests Using Mutation Testing"*；作者 **Mohamad Radaideh / Jean-Pierre Corriveau / Wei Shi**；venue **2026 IEEE 9th International Conference on Big Data and Artificial Intelligence (BDAI)**；pp. **128-132**；published 2026-07。摘要逐字："one-shot GPT-4o reaches a **69.90%** mutation score versus CANDOR's **45.63%**, and one-shot Gemini 2.5 Flash reaches **88.35%** versus CANDOR's **35.92%**"；基准 = **25 类 Java 系统**、人类手写基线 **83.98%**、**PiTest 206 变异体**；"in about **45 seconds**" vs "roughly **50 hours**" | **A** | ✅ **真实**。但 README 的**归属与限定条件有实质缺陷**（§3.1） |
| D4 | `README.md:25-28`；`REVIEW_2026_FRONTIER.md:1192`(E6) | ICST 2026（Konstantinou, Degiovanni & Papadakis，arXiv:2601.09695）：6 repo / 393 类 / 3,657 方法；Plain-LLM **49.95/35.33/33.82**；请求数 **11,718 vs 12,264** | ① `https://export.arxiv.org/api/query?id_list=2601.09695`；② `https://arxiv.org/html/2601.09695v2` → HTTP 200（291,881 B）；③ OpenAlex `filter=title.search:newer LLM versions` → ICST DOI | ✅ **存在；全部数字逐字命中；ICST 2026 亦成立** | arXiv：title *"How well LLM-based test generation techniques perform with newer LLM versions?"*；authors **Michael Konstantinou / Renzo Degiovanni / Mike Papakakis**（Michael Konstantinou, Renzo Degiovanni, Mike Papadakis）；published **2026-01-14**。全文逐字："Plain-LLM obtains, in total, **49.95%, 35.33%, and 33.82%** on line/branch/mutation coverage"；"**six complete open-source Java repositories**"；表 TOTAL = **393 / 3657**；请求数表 Total 行 = HITS 23865 / SymPrompt 8413 / TestSpark 7963 / **CoverUp 12264** / **Plain (Method) 11718**。ICST 版本：OpenAlex → `https://doi.org/10.1109/icst69053.2026.00040`，venue = *IEEE International Conference on Software Testing, Verification and Validation (ICST)*，2026-05-18 | **A** | ✅ **真实且一手**。建议补 ICST DOI（§4.4） |
| D5 | `README.md:29-31`；`REVIEW_2026_FRONTIER.md:1199`(E18) | BOAD（ICLR 2026，arXiv:2512.23631，IBM Research）为真 | ① `https://export.arxiv.org/api/query?id_list=2512.23631`；② `https://research.ibm.com/publications/boad-discovering-hierarchical-software-engineering-agents-via-bandit-optimization` → HTTP 200 | ✅ **存在；ICLR 2026 与 IBM Research 均确认** | arXiv：*"BOAD: Discovering Hierarchical Software Engineering Agents via Bandit Optimization"*，8 位作者（Iris Xu, Guangtao Zeng, Zexue He, Charles Jin, Aldo Pareja, Dan Gutfreund, Chuang Gan, Zhang-Wei Hong），published 2025-12-29。IBM Research 页面标题 *"...for **ICLR 2026**"*，类型 **Poster**，日期 **23 Apr 2026**，页脚标注 **"IBM-affiliated at time of publication"**。摘要确认研究对象为 **SWE-bench-Verified / SWE-bench-Live 仓库级任务解决**（36B 系统榜排第二） | **A** | ✅ **真实**。⚠️ 项目将其标为"预印本 B"属**低估**（§3.5） |
| D6 | task-4 清单第 6 项；`README.md:24` 同源 | ULT (UnLeakedTestbench), TOSEM 2026, DOI 10.1145/3805043 | ① `https://api.crossref.org/works/10.1145/3805043` → **HTTP 200**；② `https://arxiv.org/html/2508.00408` 全文 | ✅ **存在；系统名与全部指标逐字命中** | Crossref：*"Benchmarking LLMs for Unit Test Generation from Real-World Functions"*；authors Dong Huang / Jie M. Zhang / Mark Harman / Qianru Zhang / Mingzhe Du / See-Kiong Ng；TOSEM；2026-03-28。全文逐字："we introduce **ULT (UnLeakedTestbench)**"；"With **3,909** carefully selected function-level tasks"；"**41.32%, 45.10%, 30.22%, and 40.21%** ... on TestEval (91.79%, 92.18%, 82.04%, and 49.69%) and **PLT (47.07%, 55.13%, 40.07%, and 50.80%)**" | **A** | ✅ **真实**。"ULT" 并非幻觉缩写，是论文正式系统名 |
| D7 | task-4 清单第 6 项；`REVIEW_2026_FRONTIER.md:1228`(E39) | Zhao/Zhou/Cohen ISSTA 2026, DOI 10.1145/3832093 | ① `https://api.crossref.org/works/10.1145/3832093` → **HTTP 200**；② `https://export.arxiv.org/api/query?id_list=2607.22880`；③ `https://arxiv.org/html/2607.22880v1` 全文 | ✅ **存在；ISSTA 2026 正确；数字命中** | Crossref：*"Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)"*；authors Junda Zhao / Shurui Zhou / Eldan Cohen；container *Proceedings of the ACM on Software Engineering*；2026-10-01。arXiv comment 逐字：**"Accepted at ISSTA 2026; to appear in Proceedings of the ACM on Software Engineering (PACMSE), Vol. 3, No. ISSTA"**。全文："over **100,000 test cases** generated by **11 SOTA LLMs**"；Branch Raw **0.780 (0.002)** | **A** | ✅ **真实**。ISSTA 2026 归属**正确** |
| D8 | task-4 清单第 6 项；`REVIEW_2026_FRONTIER.md:1196`(E11) | MUTGEN TSE 2026, DOI 10.1109/tse.2026.3682975 | ① `https://api.crossref.org/works/10.1109/tse.2026.3682975` → **HTTP 200**；② `https://arxiv.org/html/2506.02954` 全文 | ✅ **存在；指示数字命中** | Crossref：*"Mutation-Guided Unit Test Generation With a Large Language Model"*；authors Guancheng Wang / Qinghua Xu / Lionel Briand / Kui Liu；*IEEE Transactions on Software Engineering*；2026-05。arXiv comment = **"Accepted in IEEE Transactions on Software Engineering"**，`arxiv:doi` = `10.1109/TSE.2026.3682975`（与项目 DOI 一致）。全文："we propose **MutGen**"；"Evaluated on **204 subjects from two benchmarks**" | **A** | ✅ **真实**。仅大小写差异（论文 *MutGen* vs 文档 MUTGEN） |

#### D.1.2 提示词怀疑清单中的系统名（20 项）

| # | 名称 | 出现位置 | 核验方法（实际 URL） | 结果 | 一手证据 | 等级 |
|---|---|---|---|---|---|---|
| S1 | **LANTERN** | `R2:22`；`REVIEW_2026_FRONTIER.md:1202`(E28) | `https://api.crossref.org/works/10.1145/3744916.3773227` → 200；`https://arxiv.org/html/2503.22512v2` | ✅ **真实，系统名确认（14 次命中）** | Crossref：*"Unlocking LLM Repair Capabilities Through Cross-Language Translation and Multi-Agent Refinement"*，event = **ICSE '26**，2026-04-12；作者 Luo/Keung/Yang/Klein/Bissyandé/Tian/Le（7 人，与文档一致）。全文逐字："we introduce a novel cross-language program repair approach **LANTERN**"；"Rust showing a **22.09%** improvement in Pass@10"；"Go, PHP, Kotlin, C#, and Ruby bugs ... **11.31%, 9.33%, 8.87%, 8.82%, and 8.33%**"；"p-value of **0.0126** ... Cliff's Delta of **0.64**"；xCodeEval "**5,068** bugs across **11** programming languages" | **A** |
| S2 | **FedDualFix** | `R2:23,63,100,144` | `https://api.crossref.org/works/10.1016/j.asoc.2026.115898` → 200 | ✅ **真实** | *"FedDualFix: Hierarchical federated learning for adaptive multi-agent program repair via dual-modality modeling"*；Xiaolin Ju / Qingyun Liu / Chang Li / Haochen Wang / Heling Cao / Xiang Chen；*Applied Soft Computing*；2026-10。作者姓氏与文档 "Ju, Liu, Li, Wang, Cao, Chen" 完全一致 | **B**（摘要级；58/52.1% 未取正文复核，ScienceDirect 付费墙） |
| S3 | **TraceCoder** | `R2:24,159-170` | `https://api.crossref.org/works/10.1145/3744916.3773187` → 200；`https://arxiv.org/html/2602.06875v1` | ✅ **真实，全部数字逐字命中** | Crossref：*"TraceCoder: A Trace-Driven Multi-Agent Framework for Automated Debugging of LLM-Generated Code"*，**ICSE '26**；Huang/Ye/Sun/Zhang/Zhang/Liu（与文档一致）。全文逐字："**34.43%** relative improvement in Pass@1"；表行 `Ours 99.39 98.17 82.00 (↑34.43%) ... 90.72 (↑11.93%)`；baseline `Self-Debugging ... 61.00 ... 81.05`；"We limit all iterative methods ... to a maximum of **5 repair attempts**" | **A** |
| S4 | **AgentRepair** | `R2:25` | `https://api.crossref.org/works/10.1109/dsa66321.2025.00025` → 200；`https://doi.org/10.1109/dsa66321.2025.00025` → **重定向至 `https://ieeexplore.ieee.org/document/11320358/`** | ✅ **真实；IEEE 文档号 11320358 映射被证明正确** | *"AgentRepair: Multi-Agent, AST-Anchored, Retrieval-Augmented Program Repair for Cold-Start Environments"*；作者 **Hyunsoo Lee / Geunseok Yang**（与文档 "Lee, Yang et al." 一致）；venue **2025 12th International Conference on Dependable Systems and Their Applications (DSA)**；pp. 121-132；2025-11-24。DOI 解析终址与文档所引 Xplore 文档号**完全一致** | **A**（存在性）／指标仍为 **D**（文档已正确标注"zero metrics verified"） |
| S5 | **LaMAR** | `R2:26,64,172-176` | `https://api.crossref.org/works/10.1145/3832783.3837423` → 200 | ✅ **真实** | *"LaMAR: Latent Multi-agent Collaboration via KV-Cache Communication for Automated Program Repair"*；**Rui Jiao / Yue Zhang / Zhexuan Feng / Jinku Li**（与文档 "Jiao, Zhang, Feng, Li" 一致）；event **ASE '26: 41st IEEE/ACM International Conference on Automated Software Engineering**；2026-10-07 | **B**（24.5% / O(N²)→O(N) 未取一手正文复核） |
| S6 | **DEIMerge** | `R2:27` | `https://api.crossref.org/works/10.1007/978-981-95-7081-2_16` → 200；OpenAlex；ACM DL 列表页标题 | ✅ **真实；PRICAI 2025 归属正确** | *"DEIMerge: An Automatic Program Repair Framework Based on Multi-agent Collaboration and Intelligent Patch Merging"*；**Chang Liang / Yuqi Zhao / Ran Mo**（与文档一致）；container *Lecture Notes in Computer Science*，Springer Nature Singapore，2026。ACM DL 列表页题名后缀为 *"PRICAI 2025: Trends in Artificial Intelligence"* → 文档 "PRICAI 2025" **正确** | **A**（元数据）／指标 **D**（文档已正确标注"摘要被出版方隐去"） |
| S7 | **PhoenixRepair** | `R2:28,211-214` | `https://export.arxiv.org/api/query?id_list=2607.18859`；arXiv 摘要 | ✅ **真实，数字逐字命中** | *"PhoenixRepair: Rethinking Repair Strategy Exploration in Software Agents"*；**10 位作者**（Tianyue Jiang, Yanlin Wang, Xin He, Daya Guo, Jiachi Chen, Ming Wen, Ensheng Shi, Xilin Liu, Yuchi Ma, Guanbin Li）→ 与文档 "Jiang + 9 authors" 一致；published **2026-07-21**。摘要逐字："relative improvement of **7.8%** over SWE-agent under DeepSeek-V3.1, and attains the highest resolved rate of **76.0%** Pass@1 under MiniMax-M2.5" | **A** |
| S8 | **SPARC** | `R3:91-102,155-162`；`E4_R3_logic_frontier.md:49,140`；`REVIEW_2026_FRONTIER.md:1190`(E4) | `https://export.arxiv.org/api/query?id_list=2602.16671`；arXiv 摘要 | ✅ **真实，全部数字逐字命中** | *"SPARC: Scenario Planning and Reasoning for Automated C Unit Test Generation"*；作者 **Jaid Monwar Chowdhury / Chi-An Fu / Reyhaneh Jabbarvand**（与文档 Chowdhury, Fu, Jabbarvand 一致）；published **2026-02-18**。摘要逐字："on **59** real-world and algorithmic subjects, where it outperforms the vanilla prompt generation baseline by **31.36%** in line coverage, **26.01%** in branch coverage, and **20.78%** in mutation score, matching or exceeding the symbolic execution tool **KLEE** on complex subjects. SPARC retains **94.3%** of tests" | **A** |
| S9 | **TwinMem-Agent** | `R2:107-108,191-195`；`REVIEW_2026_FRONTIER.md:1207`(E30) | `https://api.crossref.org/works/10.1145/3803437.3807664` → 200 | ✅ **真实** | *"TwinMem-Agent: Episodic and Semantic Memory for Repository-Level Program Repair"*；**Benzhao Wu / Zhiwen Luo / Fangwen Mu / Lijun Xiang**（与文档 "Wu, Luo, Mu, Xiang" 一致）；event **FSE Companion '26**；2026-07-05 | **B**（89.1%/60.0%/$0.0044 未取一手正文复核） |
| S10 | **ADI** | `REVIEW_2026_FRONTIER.md:1216`(E29)、`:531` | `https://api.crossref.org/works/10.1145/3797126` → 200；`https://export.arxiv.org/api/query?id_list=2604.24212` → 摘要 | ✅ **真实，数字逐字命中** | Crossref：*"Empowering Autonomous Debugging Agents with Efficient Dynamic Analysis"*；PACMSE；2026-06-30。arXiv comment = **"Accepted to ... FSE 2026"**，`arxiv:doi` = `10.1145/3797126`。摘要逐字："resolves **63.8%** of the tasks on the SWE-bench Verified set ... at an average cost of **USD 1.28** per task with **Claude-Sonnet-3.7**" | **A** |
| S11 | **FTDI** | `R2:86`；`REVIEW_2026_FRONTIER.md:317` | OpenAlex `search=FTDI budget-aware self-healing...`；Crossref bibliographic；ScienceDirect PII 页面 | ⚠️ **论文真实存在；但指示数字未能一手核验** | 命中两条：*"FTDI: A budget-aware self-healing framework for LLM multi-agent code generation"*，**Expert Systems with Applications**，DOI **10.1016/j.eswa.2026.134164**，2026-08-26；以及 SSRN 预印本 `10.2139/ssrn.6387100`。ScienceDirect **PII S0957417426030708** 确认对应同一题名（与文档所引 PII 一致）。**"up to 95.65%" 在一手摘要中未取得**（ScienceDirect 付费墙；OpenAlex 无摘要倒排索引） | 存在性 **A**／数字 **D** |
| S12 | **VIGIL** | `R2:85`；`REVIEW_2026_FRONTIER.md:319` | `https://arxiv.org/html/2512.07094v2` → HTTP 200 | ✅ **真实，全部数字逐字命中** | *"VIGIL: A Reflective Runtime for Self-Healing Agents"*；**单一作者**（Christopher Cruz）→ 与文档 "Single author" 一致；published 2025-12-08。全文 Table 1 逐字：`Premature toasts 12/12 (100%) → 0/12 (0%)`；`Mean latency 97s → 8s`；`Frustration events 8 (high intensity) → 0`；案例为 agent **Robin-A** 的 **12-event** trace ✅ | **A** |
| S13 | **TSC2CARLA** | `R3:33,53,110`；`E4` | `https://api.crossref.org/works/10.1016/j.scico.2024.103256` → 200；OpenAlex | ✅ **真实** | *"TSC2CARLA: An abstract scenario-based verification toolchain for automated driving systems"*；作者 Borchers/Koopmann/Westhofen/Becker/Putze/Grundt/de Graaff/Kalwa/Neurohr（DLR，与文档一致）；*Science of Computer Programming*；**volume 242, article 103256**（与文档 "SCP 242 103256" 一致） | **A**（元数据） |
| S14 | **LogiCase** | `R3:64,119-120,279` | `https://api.crossref.org/works/10.24963/ijcai.2025/861` → 200 | ✅ **真实** | *"LogiCase: Effective Test Case Generation from Logical Description in Competitive Programming"*；Sung/Aditi/Kim/Han/Ko（与文档一致）；**IJCAI 2025**（2025-09） | **B**（81.18%/91.38% 未取一手正文复核） |
| S15 | **Tratto** | `R1:9+`；`REVIEW_2026_FRONTIER.md:1198`(E13) | `https://api.crossref.org/works/10.1145/3728960` → 200；arXiv `2504.04251` comment | ✅ **真实** | *"Tratto: A Neuro-Symbolic Approach to Deriving Axiomatic Test Oracles"*；Molinelli/Martin-Lopez/Zackrone/Eken/Ernst/Pezzè；PACMSE，2025-06-22。arXiv comment 逐字：**"Accepted for publication at ISSTA 2025"** → 文档 "ISSTA 2025" **正确** | **A**（venue）／指标 **B** |
| S16 | **LogicEval** | `R2:121` | `https://api.crossref.org/works/10.18653/v1/2026.acl-long.2136` → 200 | ✅ **真实** | *"LogicEval: A Systematic Framework for Evaluating Automated Repair Techniques for Logical Vulnerabilities in Real-World Software"*；Rashid/Ishtiaq/Tu/Dong/Wu/Ranjbar/Yang/Sultana/Mehnaz/Hussain（与文档一致）；*Proceedings of the 64th Annual Meeting of the ACL (Volume 1: Long Papers)* → 文档 "ACL 2026 Long" **正确** | **A**（元数据） |
| S17 | **RunBugRun** | `R2:115` | `https://api.crossref.org/works/10.1007/s10664-025-10790-3` → 200；arXiv `2304.01102` | ✅ **真实** | *"RunBugRun: An executable dataset for automated program repair"*；Prenner & Robbes；*Empirical Software Engineering*；**2026-03-24**（与文档 "EMSE 31:98, publ. 2026-03-24" 一致） | **A**（元数据） |
| S18 | **CI-Bench** | `R2:117` | `https://api.crossref.org/works/10.1145/3774748.3787606` → 200 | ✅ **真实** | *"CI-Bench: A Framework for Evaluating Large Language Model Tools on CI Failures"*；**Raian Latif Nabil / Hao-Nan Zhu / Cindy Rubio-González**；event **ICSE-Companion '26**；2026-04-12 | **A**（元数据）。⚠️ 作者顺序见 §3.6 |
| S19 | **HEJ-Robust** | `R2:101,120`；`REVIEW_2026_FRONTIER.md:1213`(E34) | `https://api.crossref.org/works/10.1145/3805760.3814929` → 200；`https://export.arxiv.org/api/query?id_list=2605.02215` → 摘要 | ✅ **真实，数字逐字命中** | Crossref：*"HEJ-Robust: A Robustness Benchmark for LLM-Based Automated Program Repair"*；Fazle Rabbi / Jinqiu Yang；event **AIware '26**；2026-07-05。arXiv 摘要逐字："built from HumanEval-Java-Bug using **eight semantics-preserving code transformations**, resulting in **1,450** transformed instances. We evaluate **five fine-tuned LLMs**" | **A** |
| S20 | **ARC-APR** | `R2:119,392`；`REVIEW_2026_FRONTIER.md:1225`(E36)、`:278` | ① `https://api.openalex.org/works?search=ARC-APR` → 命中全部为**无关**结果（"arc plasma"/"submerged arc weld"等，1967-1990 年材料学论文）；② `web_search` 多轮组合 | ❌ **无任何一手记录** | 未命中任何题名/缩写匹配的同行评议记录、预印本或基准数据集 | **D** | 
| S21 | **AgentCoder** | `R1:110-113`；`REVIEW_2026_FRONTIER.md:1206`(E19) | `https://export.arxiv.org/api/query?id_list=2312.13010`；`https://arxiv.org/html/2312.13010v2` 全文 | ✅ **真实；E19 的数字逐字命中** | *"AgentCoder: Multi-Agent-based Code Generation with Iterative Testing and Optimisation"*；Huang/Zhang/Luck/Bu/Qing/Cui；2023-12-20。全文逐字："the single agent only obtains **72.5% and 75.9%** code line coverage while multiple agents obtain **87.5% and 89.5%**" ✅ → 文档的"+15.0/+13.6pp"算术正确 | **A**。⚠️ `R1:111` 的 "91.7/92.3" 未命中（§3.7） |
| S22 | **AutoGPT Devloop** | **项目文档中不存在** | `grep -rn "Devloop\|DevLoop\|devloop" --include=*.md` → **0 命中**；`web_search` | ❌ **无一手记录，且非项目实际引用** | 0 命中 | **D**（非项目问题） |
| S23 | **agent-sandbox-runtime** | `REVIEW_2026_FRONTIER.md:321,1225`(E36) | 文档自述 + 抽查 | ⚠️ 纯基础设施，**无论文、无指标** | 项目已自行标注为 **C 级不可引用** | 项目判定**正确** |
| S24 | **MUTGEN / ULT** | 见 D8 / D6 | — | ✅ 真实 | — | **A** |

#### D.1.3 项目文档中其它被独立复核的一手数字（抽样 12 项，全部命中）

| # | 出现位置 | 声明 | 核验方法 | 一手观察 | 结论 |
|---|---|---|---|---|---|
| X1 | `REVIEW_2026_FRONTIER.md:1218`(E41) | TestTailor：FSE 2026, DOI 10.1145/3797140 | `https://api.crossref.org/works/10.1145/3797140` → 200 | *"TestTailor: Generating High-Coverage Tests via Path-Proximal Tests with LLMs"*；Zhou/Lou/Dong/Hao；PACMSE；2026-06-30 | ✅ 真实 |
| X2 | `REVIEW_2026_FRONTIER.md:1226`(E40) | Test Wars, arXiv:2501.10200 | arXiv API | *"Test Wars: A Comparative Study of SBST, Symbolic Execution, and LLM-Based Approaches to Unit Test Generation"*（3 作者，2025-01-17） | ✅ 真实 |
| X3 | `REVIEW_2026_FRONTIER.md:1213`/E34 与 `R2:101` | HEJ-Robust ">50% drop" | arXiv 摘要 | "model performance dro[ps]" + 1,450 instances / 8 transforms / 5 LLMs | ✅ 真实 |
| X4 | `REVIEW_2026_FRONTIER.md:1227`(E37) | GORDIAN +28.5–115.2% / +74.1–189.8% / token −91–96% | arXiv `2603.19239` 摘要 | 逐字命中："improves coverage by **28.5-115.2%** over traditional symbolic execution baseline and by **74.1-189.8%** over LLM-based symbolic execution baselines, while reducing LLM token usage by an average of **91-96%**"；"implemented **Gordian on top of the KLEE**" | ✅ 真实 |
| X5 | `REVIEW_2026_FRONTIER.md:1229`(E42) | NeuroTestGen, arXiv:2609.30178 | arXiv API | *"NEUROTESTGEN: Neuro-Symbolic Guided Test Generation with Large Language Models"*（4 作者，2026-09-24） | ✅ 真实 |
| X6 | `REVIEW_2026_FRONTIER.md:1231`(E44) | PropGen, arXiv:2604.13463 | arXiv API | *"PropGen: Automated Property Generation for Property-Based Testing of Mobile Apps"*（5 作者，2026-04-15） | ✅ 真实 |
| X7 | `REVIEW_2026_FRONTIER.md:1233`(E33) | ImpossibleBench, ICLR 2026 | arXiv API `2510.20270` | *"ImpossibleBench: Measuring LLMs' Propensity of Exploiting Test Cases"*；Ziqian Zhong / Aditi Raghunathan / Nicholas Carlini；2025-10-23 | ✅ 真实（ICLR 2026 归属来自二手索引，等级 B） |
| X8 | `REVIEW_2026_FRONTIER.md:1217`(E16) | Arnaudo/Coppola/Morisio, ICST 2026 ASTA workshop | `web_search` → `conf.researchr.org/details/icst-2026/asta-2026-papers/3/...` | ICST 2026 ASTA workshop 议程页确认题名与作者 | ✅ 真实 |
| X9 | `REVIEW_2026_FRONTIER.md:1230`(E35) | "Whose Oracle Is It?" 93.0%（160/172） | `web_search` → `binds.ch/papers/whoseoracle2026.pdf` | 一手 PDF 存在（会议/期刊归属未在本次核验中确认） | ⚠️ 存在；数字未逐字复核（等级 B） |
| X10 | `REVIEW_2026_FRONTIER.md:1197`(E12) | AdverTest, DOI 10.1145/3832122 | `https://api.crossref.org/works/10.1145/3832122` → 200；OpenAlex 摘要 | *"Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation"*；Chang/Fang/Chen/Shi/Shen/Gu。摘要逐字："improves fault detection rates by **8.56%** over the best existing LLM-based methods and by **50.20%** over EvoSuite" ✅ | ✅ 真实，数字命中 |
| X11 | `REVIEW_2026_FRONTIER.md:1196`(E10) | SWE-Mutation：2,636 变异体/800 实例/9 语言；98.00/40.40/71.71；88.20/10.20/36.15 | arXiv `2605.22175` 全文 | 逐字命中："**2,636** mutated variants derived from **800** original instances ... spanning **nine** programming languages"；表行 `Claude-sonnet-4.5 ... 98.00 40.40 71.71`；`DeepSeek-V3.1 88.20 10.20 36.15` | ✅ 真实 |
| X12 | `REVIEW_2026_FRONTIER.md:1195`(E8) | TestAgent 154 bugs / 92.22% precision | `https://arxiv.org/html/2607.09101v1` | 逐字："TestAgent detects **154** real-world bugs via non-regression tests with a precision of **92.22%**" | ✅ 真实 |

---

### D.2 疑似幻觉引用清单（重点产出）

> **总体结论：项目文档中不存在"凭空虚构"的文献引用。** 42 个 DOI 中 41 个真实、1 个是有意引用的占位符（且项目已正确批判）；72 个 arXiv ID **全部真实**。
> 真正的问题不是"编造"，而是**三处事实性错误 + 若干归属/限定条件缺陷**。下列按严重度排序。

#### D.2.1 🔴 H-1｜`Defects4J v3 不存在` —— **项目自身的明确事实性错误**

- **出现位置**：`review_2026/R2_frontier_repair.md:67`、`:361`、`:392`；`REVIEW_2026_FRONTIER.md:283`、`:536`
- **项目原话**：
  - `R2:67`："| **Defects4J v3** | — | **NOT VERIFIED — no evidence such a release exists** | — | — | searched GitHub releases/tags, DBLP, general web | — |"
  - `R2:361`："| 5 | **Defects4J v3** | ❌ **NOT VERIFIED — no evidence it exists** | GitHub releases/tags, DBLP, and general web search. Found only v1.x and v2.0.0 (835 bugs). |"
  - `REVIEW_2026_FRONTIER.md:283`："| **Defects4J v3** | **❌ 不存在** | R2 §6 |"
- **实际核验**：`https://arxiv.org/html/2607.22880v1`（HTTP 200，392,759 B）→ 全文逐字：
  > "**Defects4J v3.0 contains 854 defects across 17 projects**, and each defect may modify one or more methods"
- **判定**：❌ **"不存在"的结论错误**。Defects4J v3.0（854 defects / 17 projects）**确实存在**，且被同一批评审自己的 E39 条目（`REVIEW_2026_FRONTIER.md:451`、`:1228`）引用为 "Defects4J v3.0"。**文档内部自相矛盾**。
- **根因推测**：R2 只检索了 GitHub releases/tags 与通用搜索（当时 DBLP 端点在本次环境下亦不可达），未检索论文全文；而 v3.0 的信息在该论文正文中。
- **可执行更正文本**：
  > `R2:67` / `R2:361` / `REVIEW_2026_FRONTIER.md:283` / `:536` 应改为：
  > "**Defects4J v3.0 存在**：854 defects / 17 projects（一手来源：Zhao, Zhou & Cohen, ISSTA 2026, DOI 10.1145/3832093 / arXiv:2607.22880 正文）。R2 原'不存在'结论系检索面不足所致的**误判，予以撤回**。"
  > 同时删除 `R2:392` 与 `REVIEW_2026_FRONTIER.md:1225`(E36) 中 "Defects4J v3 不存在" 的表述。

#### D.2.2 🟠 H-2｜IEEE 复现研究的**方法学限定条件被完全省略**（最影响结论强度）

- **出现位置**：`README.md:15-18`、`README.en.md:19-22`
- **README 原话**："IEEE 独立复现研究（Radaideh & Corriveau，*Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation*，IEEE Xplore **11655121**）在 **mutation score** 上报告 one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**、one-shot GPT-4o **69.90%** vs CANDOR **45.63%**"
- **实际核验**（S2 摘要，`https://api.semanticscholar.org/graph/v1/paper/8eab00f0df57a59a3a536d153dc01ce8f7695372`）：数字**逐字正确**，但原文限定条件是：
  - 基准 = **单个 25 类 Java 系统**（"We test this claim directly on a **25-class Java system**"），**不是** HumanEvalJava / Defects4J / SWE-bench 等公开基准；
  - 该 25 类系统疑似即作者自建示例系统（"our example system"）；
  - 人类手写基线 mutation score = **83.98%**；变异体工具 **PiTest，206 个变异体**；
  - 原文自己指出：**"Restricted to the classes it can handle, CANDOR's per-class mutation scores frequently match or beat the human baseline. Hence, CANDOR's weakness is architectural, not generative."**
- **判定**：数字真实（一手），但 README 以该数字支撑"多智能体在手写编排上劣势有限/无优势"的**全局性论证，属证据强度高估**：n=1 个 25 类系统、单一第三方复现、无公开基准、且原文自承失败集中在"类间依赖/mock 构造"这一架构点。
- **可执行更正文本**（建议替换 `README.md:15-18`）：
  > "**(a) 不利证据**——IEEE 第三方复现研究（Radaideh, Corriveau & Shi，*Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation*，IEEE Xplore **11655121**；**2026 IEEE 9th Int'l Conf. on Big Data and Artificial Intelligence (BDAI)**，pp. 128-132）：在**单个 25 类 Java 系统**上、以人类手写套件（mutation **83.98%**）与 **PiTest 206 变异体**为基准，报告 one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**、one-shot GPT-4o **69.90%** vs CANDOR **45.63%**。**范围限定（须并列披露）**：基准非公开数据集、为单一系统、原作者的 CANDOR 失败点集中于'Initialize 阶段无法处理类间依赖/mock 构造'——**该结果不可外推为'多智能体范式在公开基准上失效'。**"

#### D.2.3 🟠 H-3｜"45s vs 50h 无出处" —— **该项目评审的误判（实际有一手出处）**

- **出现位置**：`REVIEW_2026_FRONTIER.md:52`、`:774` 附近及 T3 摘要段（文档中"③ '45s vs 50h' 无出处"）
- **项目原话**（`grep` 结果）："② 未标注第三方复现身份；③ **"45s vs 50h" 无出处**。"
- **实际核验**：IEEE BDAI 2026 摘要逐字：
  > "The one-shot prompt strategy ran on Gemini also surpasses the human baseline (83.98%) **in about 45 seconds**, while CANDOR with Gemini took roughly **50 hours**."
- **判定**：❌ **该"无出处"结论错误**。"45s vs 50h" **确实有出处**，即同一篇 IEEE 复现研究（11655121）。
- **可执行更正文本**：
  > 将 `REVIEW_2026_FRONTIER.md` 中 "③ '45s vs 50h' 无出处" 改为：
  > "③ '45s vs 50h' **有出处**：Radaideh, Corriveau & Shi, BDAI 2026（IEEE Xplore 11655121）摘要原文 'in about 45 seconds' / 'roughly 50 hours'。**证据等级：一手（摘要级）**；引用时须同时标注其为**单一 25 类系统的第三方复现**。"

#### D.2.4 🟡 H-4｜"85% MTTR reduction" —— 确无一手来源（**项目判定正确**）

- **出现位置**：`R2:90,324,359`；`REVIEW_2026_FRONTIER.md:280,318`、`:1225`(E36)
- **实际核验**：项目指认的唯一来源为个人 GitHub README `github.com/suhail39ahmed/self-healing-azure-pipelines`。本次独立复核未发现任何同行评议论文、DOI 或基准支撑该数字。
- **判定**：✅ **项目判定正确（不得引用）**。保留现有 `C` 级与"禁止进入对外文档"的处置。

#### D.2.5 🟡 H-5｜ARC-APR —— 确无一手记录（**项目判定正确**）

- **出现位置**：`R2:119,392`；`REVIEW_2026_FRONTIER.md:278,1225`(E36)
- **实际核验**：
  - `https://api.openalex.org/works?search=ARC-APR&per-page=5` → HTTP 200，`count: 71328`，但前 5 条全部为**无关**材料学/焊接论文（"Fluid transpiration arc"、"submerged arc weld"、"arc plasma jets"，1967-1990），**无任何软件工程/程序修复命中**；
  - `web_search` 多轮组合（"ARC-APR automated program repair benchmark"）→ 无匹配一手记录。
- **判定**：✅ **项目判定正确**。维持"疑似不存在 / 禁止引用"。

#### D.2.6 🟡 H-6｜`10.5281/zenodo.1234567` —— 占位符（**项目判定正确**）

- **出现位置**：`review_2026/E4_R3_logic_frontier.md:99`
- **实际核验**：`https://doi.org/10.5281/zenodo.1234567` → **HTTP 404**；`https://api.datacite.org/dois/10.5281/zenodo.1234567` → `{"errors":[{"status":"404","title":"The resource you are looking for doesn't exist."}]}`
- **判定**：✅ **该 DOI 确实不存在**，但它是**项目用来举证某第三方 Zenodo 记录不严谨的证据**（"the citation block prints a **placeholder DOI**"），**不是项目自身的引用**。项目的处置完全正确。
- **附**：`10.5281/zenodo.14502996`（TSC2CARLA artifact，`R3:276`）**真实**：`https://doi.org/10.5281/zenodo.14502996` → HTTP 200 → `https://zenodo.org/records/14502996`；DataCite 记录 creators = Borchers, Philipp (DLR) 等。**Crossref 的 404 是注册机构不同所致，非失效。**

#### D.2.7 🟡 H-7｜ESBMC-AI / agent-sandbox-runtime / AutoGPT Devloop

| 名称 | 判定 | 依据 |
|---|---|---|
| **ESBMC-AI** | 无一手指标来源 | 项目已自标 `C`（`REVIEW_2026_FRONTIER.md:317,1225`）。抽查支持该处置 |
| **agent-sandbox-runtime** | 纯基础设施，无论文无指标 | 项目已自标 `C`（`:321,1225`）。抽查支持该处置 |
| **AutoGPT Devloop** | **无一手记录；且项目文档中根本不存在该引用** | `grep -rn "Devloop\|DevLoop\|devloop" --include=*.md` → **0 命中**；`web_search` 仅返回无关个人站点 |

#### D.2.8 🟡 H-8｜`1,451 methods`（TestAgent）—— **未能一手核验的数字**

- **出现位置**：`review_2026/R1_frontier_testgen.md:72`："**6 Java projects, 1,451 methods**"
- **实际核验**：`https://arxiv.org/html/2607.09101v1`（HTTP 200，275,805 B）全文检索 `"1,451"` → **0 命中**；`"1451"` → **0 命中**。摘要只声明 "**six Java projects**"。正文 RQ 段落可见 "we adopt the same **five projects** used in prior LLM-based test generation studies" 与 "we randomly select **200 methods** each from the Lang and Chart projects"，以及 Python 子集 "a total of **141** focal methods"。
- **判定**：⚠️ **"1,451 methods" 在一手全文中无法定位**——可能来自被评审自算的合计、或来自不同版本。**在定位到出处前，该数字应按"未核验"处理**。
- **可执行更正文本**：将 `R1:72` 的 "6 Java projects, 1,451 methods" 改为 "6 Java projects（论文摘要口径；**方法总数未能从一手全文定位，暂不引用具体数字**）"。

---

### D.3 引用元数据错误但文献存在（错配清单）

| # | 位置 | 错误类型 | 文档写法 | 一手事实 | 严重度 | 更正建议 |
|---|---|---|---|---|---|---|
| M-1 | `README.md:15-18`、`README.en.md:19`；`REVIEW_2026_FRONTIER.md:1194`(E25b) | **作者遗漏** | "Radaideh & **Corriveau**"（2 人） | Crossref/S2：**Mohamad Radaideh / Jean-Pierre Corriveau / Wei Shi**（**3 人**） | 中 | 改为 "Radaideh, Corriveau & Shi" |
| M-2 | 同上 | **venue 缺失** | 仅写 "IEEE Xplore 11655121"，未标 venue；上下文使其读作 SE 圈研究 | venue = **2026 IEEE 9th International Conference on Big Data and Artificial Intelligence (BDAI)**，pp. 128-132（**非软件工程会议**，5 页短文） | **高**（影响证据权重） | 补全 venue 与页数；并在并列陈述中标注"非 SE 专门会议、5 页短文" |
| M-3 | 同上 | **基准限定缺失** | 只给两个百分比 | 基准 = **25 类单一 Java 系统**，人类基线 83.98%，PiTest 206 变异体 | **高** | 见 §2.2 更正文本 |
| M-4 | `REVIEW_2026_FRONTIER.md`（T3 段） | **误判为"无出处"** | "'45s vs 50h' 无出处" | 该数据**在 11655121 摘要中逐字存在** | 中 | 见 §2.3 |
| M-5 | `REVIEW_2026_FRONTIER.md:283,536`；`R2:67,361,392` | **事实性错误** | "Defects4J v3 ❌ 不存在" | **v3.0 存在**（854 defects / 17 projects） | **最高** | 见 §2.1 |
| M-6 | `R1:72` | **数字无法定位** | TestAgent "1,451 methods" | 一手全文 0 命中 | 中 | 见 §2.8 |
| M-7 | `R1:111` | **数字未命中** | "AgentCoder(GPT-4) **91.7% / 92.3%** vs MetaGPT(GPT-4) **81.7% / 80.5%**" | `arxiv.org/html/2312.13010v2` 全文检索 `"91.7"` → **0 命中**、`"92.3"` → **0 命中**。可定位的 GPT-4 段为 `MetaGPT 85.9 / 87.7` 与 `AgentCoder (ours) 96.3 / 91.8` | 中 | **撤回该行**或改引可复核的行：`AgentCoder(GPT-4) 96.3 / 91.8 vs MetaGPT(GPT-4) 85.9 / 87.7`（须复核 Table 5 表头口径后引用） |
| M-8 | `R2:117` | **作者顺序颠倒** | "Zhu, Nabil, Rubio-González" | Crossref：**Raian Latif Nabil / Hao-Nan Zhu / Cindy Rubio-González** | 低 | 改为 "Nabil, Zhu & Rubio-González" |
| M-9 | `R1:72` vs `README.md:24` | **作者表不一致（版本差异）** | 未标注版本 | Crossref（FSE Companion 版）= 6 作者：Ye Shang / Quanjun Zhang / Zhengyu Zhan / Ke Huang / Chunrong Fang / Zhenyu Chen；arXiv（`2607.09101v1`）= 7 作者：Quanjun Zhang / Ye Shang / Siqi Gu / Jianyi Zhou / Chunrong Fang / Zhenyu Chen / Liang Xiao | 低 | 引用时注明版本（DOI 版 or arXiv 版）；指标 92.34/83.69 出自 **arXiv 版**，若引 FSE Companion 版须复核该版数值 |
| M-10 | `README.md:25-28`；`REVIEW_2026_FRONTIER.md:1192`(E6) | **venue 未落到正式出版版本** | 仅标 "arXiv:2601.09695"（但写 "ICST 2026 复现研究"） | ICST 2026 正式版存在：**DOI `10.1109/icst69053.2026.00040`**，venue = IEEE ICST，2026-05-18 | 低（**"ICST 2026" 归属本身正确**） | 补 DOI，改为 "ICST 2026, DOI 10.1109/icst69053.2026.00040（预印本 arXiv:2601.09695）" |
| M-11 | `REVIEW_2026_FRONTIER.md:1199`(E18) | **等级低估** | BOAD "预印本 / **B**" | 已 **ICLR 2026 Poster** 接收（IBM Research 官方页面，2026-04-23），且 IBM 官方标注 affiliation | 低 | 由 `B` 升为 `A`（venue 已同行评议）；**同时保留** E18 原有的"引用错位"警示（该文研究对象是仓库级 SWE 任务，非测试生成）——该警示**正确** |
| M-12 | `REVIEW_2026_FRONTIER.md:1196`(E11) | 大小写 | "MUTGEN" | 论文中为 "**MutGen**"；arXiv 标题为 "Mutation-Guided Unit Test Generation with a Large Language Model" | 极低 | 统一为 "MutGen (MUTGEN)" |
| M-13 | `R3:110` | 年份口径 | "SCP 242 (**2025**) 103256" | 卷 242 / 文章号 103256 ✅ 正确；Crossref published = **2025-05**，OpenAlex year = **2024**（在线首发年） | 极低 | 保留 2025 卷年，必要时并列 "online 2024" |
| M-14 | `R1:110`（E19 引用） | 口径易误读 | "multi vs single 消融" | 该 87.5/89.5 vs 72.5/75.9 出自**测试代码行覆盖率**表（论文 Tab. 8 段落），**非端到端 pass@1**；文档已标注 "HumanEval/MBPP canonical solutions" ✅ | 极低 | **无需更正**，现有标注已正确 |
| **M-15** | `docs/adr/0017-repair-engine-pivot.md:14` | **数字无法一手复现** | "多 Hunk 行为研究 arXiv 2511.11012：修复准确率 **Claude Code 92.82% vs Qwen Code 26.98%**" | `https://arxiv.org/html/2511.11012v1`（HTTP 200）全文：`92.82`/`26.98`/`92.8`/`26.9` **各 0 命中**。一手摘要报告的是 **localization success：Codex 75.0% 最高、Qwen Code 38.2% 最低**；数据集为 **Hunk4J**（372 bugs / 1,488 trajectories） | **中** | 见 §7.4 更正文本：改为可复核的 75.0% / 38.2%，并撤回 92.82%/26.98% |
| **M-16** | `docs/adr/0017-repair-engine-pivot.md:14` | **勘误方向错误（可撤销）** | "'**PSR（四模式 LoRA）**' 经第十六轮三轮检索**未能定位原文**" | ✅ **实际可定位**：*"**Pattern Synergistic Repair: Multi-expert LoRA fusion for automated program repair**"*，*Information and Software Technology*，DOI **`10.1016/j.infsof.2026.108344`**（Crossref HTTP 200；PII `S0950584926003332`） | 中 | 撤销该勘误，改标一手 DOI；"Hunk-SWE" 部分**维持**未能定位 |

---

### D.4 真实存在且有价值的一手来源清单（可直接用于投稿引用）

按"可直接引用强度"排序。全部经本次机读端点一手核验。

#### D.4.1 A 级：一手全文逐字命中（可直接引用，建议保留/升级）

| # | 来源 | 标识 | 一手可引用数字 | 备注 |
|---|---|---|---|---|
| A1 | **CANDOR** — Xu, Wang, Briand, Liu | TOSEM 2026, DOI `10.1145/3803418`；arXiv `2506.02943v3` | HumanEvalJava line/branch/mutation **0.991 / 0.970 / 0.980**（2384/2443）；基线 EvoSuite + LLM-Empirical | 项目 README 的核心"有利证据"，**引用正确** |
| A2 | **Konstantinou, Degiovanni & Papadakis** | ICST 2026, DOI `10.1109/icst69053.2026.00040`；arXiv `2601.09695v2` | Plain-LLM **49.95/35.33/33.82** vs HITS 42.43/29.49/27.97、SymPrompt 40.95/27.19/28.40、TestSpark 23.65/16.48/13.88、CoverUp 38.85/25.11/26.26；6 Java repos / 393 classes / 3,657 methods；请求数 Plain(Method) **11,718** vs CoverUp **12,264** | **迄今最强负面证据**；建议补 ICST DOI |
| A3 | **TestAgent** — Shang, Zhang, Zhan, Huang, Fang, Chen | FSE Companion 2026, DOI `10.1145/3803437.3806428`；arXiv `2607.09101v1` | 6 Java projects：exec **97.46%** / line **92.34%** / branch **90.24%** / mutation **83.69%**；**154** real bugs，precision **92.22%** | ⚠️ "1,451 methods" 未能定位 |
| A4 | **Radaideh, Corriveau & Shi** | IEEE Xplore **11655121**；DOI `10.1109/bdai70753.2026.11655121`（BDAI 2026, pp.128-132） | 25 类 Java 系统：one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**；one-shot GPT-4o **69.90%** vs CANDOR **45.63%**；人类基线 **83.98%**；**45 s vs 50 h**；PiTest 206 mutants | ⚠️ **引用必须并列范围限定**（§2.2） |
| A5 | **SPARC** — Chowdhury, Fu, Jabbarvand | arXiv `2602.16671`（预印本） | 59 C subjects：**+31.36% line / +26.01% branch / +20.78% mutation** vs vanilla prompt；test retention **94.3%**；matches/exceeds **KLEE** | 项目已正确标注"不含 SMT"的更正 |
| A6 | **TraceCoder** — Huang, Ye, Sun, Zhang, Zhang, Liu | ICSE 2026, DOI `10.1145/3744916.3773187`；arXiv `2602.06875v1` | ClassEval Pass@1 **82.00%** vs 次优 **61.00%** → **+34.43%** relative；5 benchmark 均值 **90.72%** vs **81.05%**；≤**5** repair attempts | — |
| A7 | **LANTERN** — Luo, Keung, Yang, Klein, Bissyandé, Tian, Le | ICSE 2026, DOI `10.1145/3744916.3773227`；arXiv `2503.22512v2` | xCodeEval **5,068** bugs / **11** langs；Rust Pass@10 **+22.09%**；Go/PHP/Kotlin/C#/Ruby **+11.31/9.33/8.87/8.82/8.33%**；**p=0.0126**，Cliff's δ=**0.64** | — |
| A8 | **PhoenixRepair** — Tianyue Jiang et al. (10 authors) | arXiv `2607.18859` | SWE-bench-Verified：**+7.8%** relative over SWE-agent (DeepSeek-V3.1)；**76.0%** Pass@1 (MiniMax-M2.5) | — |
| A9 | **ADI** — Xiang, Xu, Chu, Tian, Zhang | DOI `10.1145/3797126`（PACMSE；arXiv comment: FSE 2026）；arXiv `2604.24212` | SWE-bench Verified **63.8%**；**USD 1.28/task**；Claude-Sonnet-3.7 | — |
| A10 | **VIGIL** — Christopher Cruz（单作者） | arXiv `2512.07094v2` | Table 1：premature toasts **12/12 → 0/12**；mean latency **97 s → 8 s**；frustration **8 → 0** | ⚠️ n=12 单案例、无基线——**仅可作为"问题存在性"证据，不可作效果量引用** |
| A11 | **HEJ-Robust** — Rabbi & Yang | AIware 2026, DOI `10.1145/3805760.3814929`；arXiv `2605.02215` | **1,450** transformed instances；**8** semantics-preserving transforms；**5** fine-tuned LLMs；性能下降 >50% | — |
| A12 | **ULT (UnLeakedTestbench)** — Huang, Zhang, Harman, Zhang, Du, Ng | TOSEM 2026, DOI `10.1145/3805043`；arXiv `2508.00408` | **3,909** function-level tasks；ULT **41.32/45.10/30.22/40.21** vs PLT **47.07/55.13/40.07/50.80** vs TestEval 91.79/92.18/82.04/49.69 | — |
| A13 | **MutGen** — Wang, Xu, Briand, Liu | IEEE TSE 2026, DOI `10.1109/tse.2026.3682975`；arXiv `2506.02954` | **204 subjects** / 2 benchmarks；覆盖-变异背离（部分套件 100% line 仅 4% mutation） | — |
| A14 | **Zhao, Zhou & Cohen** | ISSTA 2026, DOI `10.1145/3832093`；arXiv `2607.22880` | **>100,000** tests / **11** LLMs / **13** settings；**Defects4J v3.0 = 854 defects / 17 projects**；branch vs raw mutation **r = 0.780 (p=0.002)** | **本报告修复 H-1 的一手依据** |
| A15 | **BOAD** — Iris Xu, Guangtao Zeng, Zexue He, Charles Jin, Aldo Pareja, Dan Gutfreund, Chuang Gan, Zhang-Wei Hong（IBM Research） | **ICLR 2026 Poster**；arXiv `2512.23631` | SWE-bench-Verified/Live；36B 系统 SWE-bench-Live 榜第 2；研究对象 = 仓库级 SWE 任务解决 | 项目"引用错位"警示**正确**，须保留 |
| A16 | **GORDIAN** — Bouras & Mechtaev | DOI `10.1145/3832126`；arXiv `2603.19239` | built on **KLEE**；**+28.5–115.2%** over traditional SE；**+74.1–189.8%** over LLM-SE baselines；token **−91–96%** | 项目 R3"真正 SMT+LLM SOTA"判断**正确** |
| A17 | **SWE-Mutation** — Sun et al. | Findings of ACL 2026, DOI `10.18653/v1/2026.findings-acl.1976`；arXiv `2605.22175` | **2,636** mutants / **800** instances / **9** langs；Claude-sonnet-4.5+Claude Code **98.00/40.40/71.71**；DeepSeek-V3.1 **88.20/10.20/36.15** | — |
| A18 | **AgentRepair** — Hyunsoo Lee & Geunseok Yang | DOI `10.1109/dsa66321.2025.00025` → **IEEE Xplore document/11320358/** | 存在性已证；**无指标可获取** | 项目"existence only"标注**正确** |
| A19 | **Arnaudo, Coppola, Morisio et al.** | **ICST 2026 ASTA workshop**（conf.researchr.org 议程页） | HumanEval 黑盒 multi-agent coverage 峰值 99.75%（**摘要级**） | 等级 B |
| A20 | **"Whose Oracle Is It?"** | 一手 PDF `binds.ch/papers/whoseoracle2026.pdf` | 93.0%（160/172）test-changing 修复改动已存在测试工件 | 等级 B（venue 待确认） |
| A21 | **ImpossibleBench** — Zhong, Raghunathan, Carlini | arXiv `2510.20270`；ICLR 2026（二手索引） | pass-rate ≡ cheating-rate 构造 | 等级 B |

#### D.4.2 建议新增（项目已引用但标识不完整，补一手标识后可直接用）

| 来源 | 建议补全的标识 | 一手核验路径 |
|---|---|---|
| Konstantinou et al. | DOI `10.1109/icst69053.2026.00040` | OpenAlex `filter=title.search:newer LLM versions` |
| BOAD | ICLR 2026 Poster 官方页：`research.ibm.com/publications/boad-discovering-hierarchical-software-engineering-agents-via-bandit-optimization` | HTTP 200 |
| FTDI | DOI `10.1016/j.eswa.2026.134164`；PII `S0957417426030708`；*Expert Systems with Applications*, 2026-08-26 | OpenAlex / Crossref / ScienceDirect PII 页 |
| IEEE 11655121 | 完整 DOI `10.1109/bdai70753.2026.11655121`；venue *2026 IEEE 9th Int. Conf. on Big Data and Artificial Intelligence (BDAI)*；pp. 128-132 | Crossref HTTP 200 |

#### D.4.3 明确**不得引用**（维持或新增）

| 来源 | 理由 | 一手依据 |
|---|---|---|
| **ARC-APR** | 无任何一手记录 | OpenAlex 精确检索 71,328 条中前 5 条全无关；多轮 web_search 无命中 |
| **"85% MTTR reduction"** | 唯一来源为个人 GitHub README | 项目 `R2:90,324,359` 已标注；独立复核未发现论文/DOI/基准 |
| **ESBMC-AI** | 无一手成功率来源 | 项目已自标 `C` |
| **agent-sandbox-runtime** | 纯基础设施，无指标 | 项目已自标 `C` |
| **`10.5281/zenodo.1234567`** | DOI 不存在（占位符） | `doi.org` 404 + DataCite 404 |
| **"1,451 methods"（TestAgent）** | 一手全文无法定位 | `arxiv.org/html/2607.09101v1` 检索 `1,451`/`1451` → 0 命中 |
| **"Defects4J v3 不存在"（项目结论）** | **反向更正**：v3.0 真实存在 | `arxiv.org/html/2607.22880v1`："Defects4J v3.0 contains **854** defects across **17** projects" |

#### D.4.4 对不存在项的"最接近真实替代工作"建议

| 不存在的项 | 替代建议 |
|---|---|
| **ARC-APR**（无一手来源） | 若原意是"真实仓库级 APR 基准"，改用 **Defects4J v3.0**（854 defects / 17 projects，Zhao/Zhou/Cohen ISSTA 2026 一手陈述）或 **GitBug-Java**；若原意是"agentic APR 评测"，改用 **CI-Bench**（DOI `10.1145/3774748.3787606`）、**Multi-SWE-bench** 或 **SWE-bench-Verified** 官方榜单 |
| **"85% MTTR"** | 改用可核验的自愈量级来源：`REVIEW_2026_FRONTIER.md:280` 已定位的 Atlantis Press 论文（"小时级 → 28 分钟内"、96% RCA、73% 修复成功率）；或直接以本项目自身的 `false_fix` / `repair_rate` 上报 |
| **ESBMC-AI 具体成功率** | 改用 **GORDIAN**（KLEE 之上的 SMT+LLM，DOI `10.1145/3832126`）或 **ESBMC 综述**（arXiv `2605.26169`）作为形式化验证工具链引用 |
| **"Defects4J v3 不存在"** | **不需要替代——修正为存在**：Defects4J v3.0，854 defects / 17 projects |
| **AutoGPT Devloop** | 项目未引用，无需修正。若需"自动循环式 debug agent"真实替代：**MAGIS**（arXiv `2403.17927`）或 **Agentless**（DOI `10.1145/3715754`，已由 OpenAlex 在本环境返回） |

---

### D.5 逐条可执行更正清单（按文件:行）

| 优先级 | 文件:行 | 现状 | 更正文案 |
|---|---|---|---|
| **P0** | `review_2026/R2_frontier_repair.md:67` | "Defects4J v3 — NOT VERIFIED — no evidence such a release exists" | 改为："**Defects4J v3.0 存在**：854 defects / 17 projects（一手：Zhao, Zhou & Cohen, ISSTA 2026, DOI 10.1145/3832093）。原'不存在'结论**撤回**。" |
| **P0** | `review_2026/R2_frontier_repair.md:361` | "Found only v1.x and v2.0.0 (835 bugs)" | 改为："v1.x、v2.0.0（835 bugs）**及 v3.0（854 defects / 17 projects）**；v3.0 信息来自 ISSTA 2026 论文正文而非 GitHub releases，故前次检索未命中。" |
| **P0** | `review_2026/R2_frontier_repair.md:392` | "…Defects4J v3 *(no evidence of existence)*…" | 删除该分句 |
| **P0** | `REVIEW_2026_FRONTIER.md:283,536` | "\| **Defects4J v3** \| **❌ 不存在** \|" | 改为 "\| **Defects4J v3.0** \| **✅ 存在**（854 defects / 17 projects，ISSTA 2026 一手）\|" |
| **P0** | `REVIEW_2026_FRONTIER.md:1225`(E36) | 含 "Defects4J v3 不存在" | 删除该分句；其余（ARC-APR / 85% MTTR / ESBMC-AI / agent-sandbox-runtime）**保留** |
| **P0** | `README.md:15-18`、`README.en.md:19-22` | 作者 2 人、无 venue、无基准限定 | 采用 §2.2 更正文本（补 Wei Shi、BDAI 2026、pp.128-132、25 类单一系统、人类基线 83.98%、PiTest 206 mutants、"architectural, not generative" 自承） |
| **P0** | `REVIEW_2026_FRONTIER.md`（T3 段"③ '45s vs 50h' 无出处"） | 误判无出处 | 改为 §2.3 文案：**有出处**（BDAI 2026 摘要逐字） |
| **P1** | `review_2026/R1_frontier_testgen.md:72` | "6 Java projects, 1,451 methods" | 改为 "6 Java projects（**方法总数未能一手定位，暂不引用**）" |
| **P1** | `review_2026/R1_frontier_testgen.md:111` | "AgentCoder(GPT-4) 91.7% / 92.3% vs MetaGPT(GPT-4) 81.7% / 80.5%" | **撤回该行**，或改为可复核的 `96.3 / 91.8 vs 85.9 / 87.7`（须先复核 Table 5 表头口径） |
| **P2** | `README.md:25-28`；`REVIEW_2026_FRONTIER.md:1192`(E6) | 仅 arXiv 标识 | 补 "ICST 2026, DOI `10.1109/icst69053.2026.00040`" |
| **P2** | `REVIEW_2026_FRONTIER.md:1199`(E18) | BOAD 标 "预印本 / B" | 升为 "**ICLR 2026 Poster / A**"；**保留**"研究对象为仓库级 SWE 任务、非测试生成"的引用错位警示 |
| **P2** | `review_2026/R2_frontier_repair.md:117` | "Zhu, Nabil, Rubio-González" | 改为 "Nabil, Zhu & Rubio-González" |
| **P2** | `review_2026/R2_frontier_repair.md:86` | FTDI "up to 95.65%"，来源标"中文二级摘要；ScienceDirect 403" | 补一手标识 "DOI `10.1016/j.eswa.2026.134164`, *Expert Systems with Applications*, 2026-08-26（**存在性一手确认**）"；**保留**"95.65% 数值未取得一手复核"的标注（本次仍然未能取得） |
| **P3** | `REVIEW_2026_FRONTIER.md:1196`(E11) | "MUTGEN" | 统一为 "MutGen (MUTGEN)" |
| **P3** | `review_2026/R1_frontier_testgen.md:72` / `README.md:24` | TestAgent 作者表两版本混用 | 注明版本：指标 92.34/83.69 出自 **arXiv `2607.09101v1`**（7 作者）；FSE Companion 版（6 作者，DOI `10.1145/3803437.3806428`）须单独复核 |
| **P1** | `docs/adr/0017-repair-engine-pivot.md:14` | 多 hunk 数字 "Claude Code 92.82% vs Qwen Code 26.98%" | 改为可复核的 "**定位成功率 Codex 75.0% 最高 / Qwen Code 38.2% 最低**（Hunk4J, 372 bugs / 1,488 trajectories）"；**撤回** 92.82%/26.98%（arXiv v1 无法复现） |
| **P1** | `docs/adr/0017-repair-engine-pivot.md:14` | "'PSR（四模式 LoRA）' 未能定位原文" | **撤销该勘误**：PSR = *Pattern Synergistic Repair: Multi-expert LoRA fusion for automated program repair*，DOI **`10.1016/j.infsof.2026.108344`**。"Hunk-SWE" 仍未能定位（最接近：arXiv `2511.11012` / Hunk4J） |
| **P2** | `docs/citation_allowlist.txt`（第 2、4 条） | RGFL 71.4% 与 ADI 数值待核验 | **两行可移除出豁免清单**：RGFL "file-level Hit@1 improves from **71.4% to 85%**" 逐字吻合（arXiv `2601.18044v1`）；ADI 63.8% / $1.28 / Claude-Sonnet-3.7 逐字吻合（arXiv `2604.24212`，DOI `10.1145/3797126`） |
| **P2** | `docs/citation_allowlist.txt`（第 1、3 条） | README.en.md:528 与 ADR-0025:9 | **仍未能核验**——二者均为**无 DOI/arXiv 标识符**的 venue+数字主张，无法机读定位。建议先补标识符再核 |

---

### D.6 核验结果汇总统计

| 指标 | 数值 |
|---|---|
| 抽取的唯一 DOI | **42** |
| DOI 真实存在 | **41**（其中 Crossref 200 = 40；DataCite/Zenodo = 1） |
| DOI 确证不存在 | **1**（`10.5281/zenodo.1234567`，占位符，**项目已正确批判**） |
| 抽取的唯一 arXiv ID | **72**（7 份指定文档）；**48**（全仓库 `docs/` + 根 `*.md` 口径） |
| arXiv ID 真实存在 | **72 / 72（100%）**；全仓库口径 **48 / 48（100%）** |
| arXiv ID 伪造 | **0** |
| 提示词怀疑清单中**确证真实**的系统 | **17**（LANTERN, FedDualFix, TraceCoder, AgentRepair, LaMAR, DEIMerge, PhoenixRepair, SPARC, TwinMem-Agent, ADI, FTDI, VIGIL, TSC2CARLA, LogiCase, Tratto, LogicEval, RunBugRun, CI-Bench, HEJ-Robust, MUTGEN, ULT 中的绝大多数） |
| 提示词怀疑清单中**无一手记录** | **1**（ARC-APR）；另 2 项（85% MTTR、ESBMC-AI）无一手来源，**项目已自行标注** |
| 提示词怀疑清单中**项目根本未引用** | **1**（AutoGPT Devloop） |
| 查出**项目自身的实质错误** | **4**（H-1 Defects4J v3 事实性错误；H-2 限定条件省略；H-3 "无出处"误判；**M-15 多 hunk 数字未能一手核验**） |
| 查出**项目自身评审的误判更正**（错误方向相反） | **2**（"45s vs 50h 无出处" 实为有出处；"PSR 未能定位" 实为可定位 —— DOI `10.1016/j.infsof.2026.108344`） |
| 元数据错配项 | **15**（M-1 … M-15，其中 2 项为 **P0**、3 项 **P1**） |
| 项目门禁未决待办 | 4 条中 **2 条可闭环移除**（ADR-0017 RGFL、ADR-0028 ADI）；2 条因无标识符仍未能核验 |

### 一句话结论

> **项目文档不存在"凭空编造"的文献引用**（全仓库 arXiv 48/48 真实、DOI 41/42 真实）；提示词给出的"疑似幻觉"清单经一手核验后**绝大多数被证伪为真实存在**，唯一确证无一手记录的是 **ARC-APR**（且项目已自行标注禁止引用）。
> 真正需要修复的是项目**自身评审与 ADR 中的 4 处实质缺陷**——优先级最高的是 **①"Defects4J v3 不存在"这一事实性错误**（v3.0 实为 854 defects / 17 projects），与 **②IEEE 复现研究（11655121）省略了"25 类单一系统、非 SE 会议（BDAI）、5 页短文"这一决定性范围限定**（后者直接影响 README 主论证的证据强度）；另有 **③"45s vs 50h 无出处"属误判**（一手有出处）、**④ADR-0017 的多 hunk 数字 92.82%/26.98% 在 arXiv v1 中无法复现**。
> 同时，本轮**为项目解决了两项"未能定位"的悬案**：PSR = *Pattern Synergistic Repair*（DOI `10.1016/j.infsof.2026.108344`，可撤销勘误）；"Hunk-SWE" 仍无一手记录，最接近的真实工作是 arXiv `2511.11012` / **Hunk4J** 数据集。

---

### D.7 扩展轮：`docs/` 全域 arXiv 覆盖 + 项目门禁未决待办核验

> 首轮扫描覆盖 7 份指定文档（71 个 arXiv ID）。为回应"**全部**文献引用"的要求，第二轮把扫描面扩展到整个仓库 `docs/` 与根目录 `*.md`。

#### D.7.1 `docs/` 全域 arXiv 覆盖：**48 个唯一 ID，48/48 真实，0 缺失**

`https://export.arxiv.org/api/query?id_list=<48 ids>&max_results=60` → `returned=48`，`MISSING overall: NONE (0)`。

相比首轮新增的 13 个（此前未覆盖，**全部真实**）：

| arXiv ID | 日期 | 标题 |
|---|---|---|
| 1708.00154 | 2017-08-01 | Neural Rating Regression with Abstractive Tips Generation for Recommendation |
| 1811.05422 | 2018-11-13 | Bayesian Data Analysis in Empirical Software Engineering Research |
| 2501.07531 | 2025-01-13 | Evaluating Agent-based Program Repair at Google |
| 2503.13657 | 2025-03-17 | Why Do Multi-Agent LLM Systems Fail? |
| 2505.23419 | 2025-05-29 | SWE-bench Goes Live! |
| 2507.11873 | 2025-07-16 | Syntax Repair as Language Intersection |
| 2507.22305 | 2025-07-30 | Is SHACL Suitable for Data Quality Assessment? |
| 2510.12487 | 2025-10-14 | Diff-XYZ: A Benchmark for Evaluating Diff Understanding |
| 2511.11012 | 2025-11-14 | Beyond Accuracy: Behavioral Dynamics of Agentic Multi-Hunk Repair |
| **2601.18044** | 2026-01-25 | **RGFL: Reasoning Guided Fault Localization for Automated Program Repair Using LLMs** |
| 2602.08146 | 2026-02-08 | Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation |
| 2606.26978 | 2026-06-25 | To Run or Not to Run: Analyzing the Cost-Effectiveness of Code Execution in LLM-Based Program Repair |
| 2609.00227 | 2026-08-31 | Don't Let the Model Write the YAML: Deterministic, Minimal-Diff GitOps Remediation from LLM-Proposed Field Changes |

**累计：全仓库 arXiv 引用 48/48 真实，0 伪造。**

#### D.7.2 `docs/citation_allowlist.txt` 未决待办逐条闭环

该文件自述"**本清单不是'证明这些引用没问题'，而是'证明它们已被看见'**"，并列出 4 条待办。本轮把其中可核验的条目闭环：

| 待办条目 | 待办内容 | 本轮核验 | 结论 |
|---|---|---|---|
| `docs/adr/0017-repair-engine-pivot.md:14` | "确认 arXiv **2601.18044** 的 **71.4%** 数值在原文中逐位吻合；吻合后移除本条" | `https://arxiv.org/html/2601.18044v1`（HTTP 200，293,761 B）→ 摘要逐字："On SWE-bench Verified, **file-level Hit@1 improves from 71.4% to 85%**, and MRR from 81.8% to 88.8%"；正文 RQ1.1 逐字："for Hit@1, Gemini 2.5 Pro improves from **71.4% to 85%**" | ✅ **逐位吻合，且 ADR 表述"71.4%→85%"完全正确**。arXiv ID 真实、题名正确（RGFL, Sepidband/Taherkhani/Pham/Hemmati, 2026-01-25）。**该行可移除出豁免清单**——注意 `71.4%` 是 **Agentless 基线**（Gemini 2.5 Pro）的值，RGFL 自身的值是 85%；ADR 以区间形式书写，**措辞无误**，但若后续引用为"RGFL 达 71.4%"则属误读 |
| `docs/adr/0028-...:52` | "核验 ADI 的其余数字并补 DOI（PACMSE 2026, DOI 10.1145/3797126 已知）" | `https://api.crossref.org/works/10.1145/3797126` → 200；arXiv `2604.24212` 摘要 | ✅ **该行可闭环移除**：DOI `10.1145/3797126` 真实；63.8% / $1.28/task / Claude-Sonnet-3.7 **三项均逐字命中**；arXiv comment 另证 **"Accepted to FSE 2026"** |
| `docs/adr/0025-...:9` | "一手核验 venue 与数字，或删除该段（ASE 2025：13,866 个测试预言 / mutation 43% vs 人类 45%）" | 未在本次范围（该处**无 DOI/arXiv 标识**，为纯 venue+数字主张） | ⚠️ **仍未能核验**——无标识符可供机读定位。建议补 DOI/arXiv 后再核 |
| `README.en.md:528` | "补数据集/论文出处，或改为'经验观察'并去掉百分比" | 同上（无标识符） | ⚠️ **仍未闭环**，处置建议不变 |

#### D.7.3 ADR-0017 勘误段的两处"未能定位"名称：一处**已定位**，一处**仍未定位**

ADR-0017 正文自述："此前引用的 **'Hunk-SWE'** 与 **'PSR（四模式 LoRA）'** 两名经第十六轮三轮检索未能定位原文，暂以上述已核验锚点替代"。本轮独立复核：

| 名称 | 核验方法 | 结果 |
|---|---|---|
| **PSR（四模式 LoRA）** | Crossref bibliographic 检索 | ✅ **已定位（建议撤销该勘误）**：*"**Pattern Synergistic Repair: Multi-expert LoRA fusion for automated program repair**"*，**Information and Software Technology**，DOI **`10.1016/j.infsof.2026.108344`**（Elsevier PII `S0950584926003332`，2027-01 卷，在线 2026）。"Multi-expert LoRA fusion" 与 "四模式 LoRA" 语义一致。**可用该一手 DOI 替换"未能定位"表述** |
| **Hunk-SWE** | `web_search` 多轮；`2511.11012` 全文检索 | ❌ **仍未定位**。ADR 原有处置（"未能定位原文"）**正确，予以维持**。**最接近的真实工作**：arXiv **`2511.11012`** 的 **Hunk4J** 数据集（372 个 multi-hunk bugs / 1,488 条修复轨迹），或 UBC 学位论文 *"Agentic Multi-Hunk Repair on SWE-bench Verified"* |

#### D.7.4 🔴 新增发现 M-15：ADR-0017 引用的多 hunk 数字**未能一手核验**（v1 全文本 0 命中）

- **出现位置**：`docs/adr/0017-repair-engine-pivot.md:14`
- **文档原话**："多 Hunk 行为研究 arXiv 2511.11012：修复准确率 **Claude Code 92.82% vs Qwen Code 26.98%**、随 hunk 数与分散度递减"
- **实际核验**：`https://arxiv.org/html/2511.11012v1`（HTTP 200，159,702 B）全文检索：
  - `"92.82"` → **0 命中**；`"26.98"` → **0 命中**；`"92.8"` → **0 命中**；`"26.9"` → **0 命中**
  - 一手摘要实际报告的是**另一组指标**："localization capability varies substantially, with **Codex achieving the highest success rate (75.0%) and Qwen Code the lowest (38.2%)**"
  - 论文题名/数据集确认：*"Beyond Accuracy: Behavioral Dynamics of Agentic Multi-Hunk Repair"*；数据集 **Hunk4J**（**372** multi-hunk bugs，**1,488** trajectories）；4 个 agent = Claude Code / Codex / Gemini-cli / Qwen Code
- **判定**：⚠️ **92.82% / 26.98% 在该文 arXiv v1 中无法定位**（可能来自 v2、其他表或指标口径不同）。**在定位到版本与表号前不得引用**。
- **可执行更正文本**：
  > 将 `docs/adr/0017-repair-engine-pivot.md:14` 中 "多 Hunk 行为研究 arXiv 2511.11012：修复准确率 Claude Code 92.82% vs Qwen Code 26.98%、随 hunk 数与分散度递减" 改为：
  > "多 Hunk 行为研究（*Beyond Accuracy: Behavioral Dynamics of Agentic Multi-Hunk Repair*, arXiv:2511.11012，Hunk4J 数据集 **372** multi-hunk bugs / **1,488** trajectories，4 agent）：**定位成功率 Codex 75.0% 最高、Qwen Code 38.2% 最低**（一手摘要），修复准确率亦随 agent 显著分化（**具体百分比待定位表号后引用；原 92.82%/26.98% 在 arXiv v1 中未能复现，暂撤回**）。"

#### D.7.5 扩展轮统计增量

| 指标 | 首轮 | 扩展轮后累计 |
|---|---|---|
| 覆盖文档 | 7 份 | 7 份 + 全仓库 `docs/` 与根 `*.md` |
| 唯一 arXiv ID 核验 | 72 | **48（docs 全域口径，含首轮的 35 个重叠）→ 全仓库口径 0 缺失** |
| **伪造 arXiv ID** | 0 | **0** |
| 唯一 DOI 核验 | 42 | 42（+ 扩展轮新增 `10.1016/j.infsof.2026.108344` 经 Crossref 确认为 PSR） |
| 元数据错配项 | M-1…M-14 | **M-1…M-15**（新增 M-15） |
| 门禁待办闭环 | — | 4 条中 **2 条可闭环移除**、2 条仍无标识符未能核验 |
| 勘误待办 | — | "PSR" **已定位可撤销勘误**；"Hunk-SWE" **维持未能定位** |

---

### D·附录 A：完整端点核验日志（可复现）

```
# DOI 批量核验（42 个，curl + Crossref REST）
for d in $(cat dois_clean.txt); do
  curl -s -L --max-time 30 -A "AITester-CitationAudit/1.0 (mailto:audit@example.org)" \
       -H "Accept: application/json" -o /tmp/out.json -w "%{http_code}" \
       "https://api.crossref.org/works/$d"
done
# 结果：40 × HTTP 200 ；2 × HTTP 404（10.5281/zenodo.1234567, 10.5281/zenodo.14502996）

# Zenodo 双通道复核（DataCite 注册，Crossref 404 属正常）
curl -sI -L "https://doi.org/10.5281/zenodo.14502996"   # → 200 → https://zenodo.org/records/14502996
curl -s     "https://api.datacite.org/dois/10.5281/zenodo.14502996"  # → creators: Borchers, Philipp (DLR) ...
curl -sI -L "https://doi.org/10.5281/zenodo.1234567"    # → 404
curl -s     "https://api.datacite.org/dois/10.5281/zenodo.1234567"   # → {"errors":[{"status":"404",...}]}

# arXiv 批量核验（72 个 ID，10 个/请求，共 8 批）
curl -s "https://export.arxiv.org/api/query?id_list=<10 ids>&max_results=30"
# 结果：<opensearch:totalResults> 与 <entry> 数量一致；72/72 全部返回；MISSING = []

# 关键全文逐字核验
curl -sL "https://arxiv.org/html/2506.02943v3"   # CANDOR: "CANDOR 0.991* 0.970 0.980*" ✅
curl -sL "https://arxiv.org/html/2601.09695v2"   # Konstantinou: 49.95/35.33/33.82, 12264/11718 ✅
curl -sL "https://arxiv.org/html/2607.22880v1"   # "Defects4J v3.0 contains 854 defects across 17 projects" ✅
curl -sL "https://arxiv.org/html/2607.09101v1"   # TestAgent 92.34/83.69/154/92.22 ✅ ；"1,451" → 0 hits ❌
curl -sL "https://arxiv.org/html/2602.06875v1"   # TraceCoder 34.43/82.00/61.00/90.72/81.05 ✅
curl -sL "https://arxiv.org/html/2503.22512v2"   # LANTERN 22.09/11.31/p=0.0126/δ=0.64 ✅
curl -sL "https://arxiv.org/html/2312.13010v2"   # AgentCoder 87.5/89.5/72.5/75.9 ✅ ；91.7/92.3 → 0 hits ❌
curl -sL "https://arxiv.org/html/2512.07094v2"   # VIGIL Table 1: 12/12→0/12, 97s→8s, 8→0 ✅
curl -sL "https://arxiv.org/html/2508.00408"     # ULT 3,909 / 41.32/45.10/30.22/40.21 vs PLT ✅
curl -sL "https://arxiv.org/html/2605.22175"     # SWE-Mutation 2,636/800/9, 98.00/40.40/71.71 ✅

# Semantic Scholar（IEEE 付费墙替代路径；初始 429，退避后成功）
curl -s "https://api.semanticscholar.org/graph/v1/paper/8eab00f0df57a59a3a536d153dc01ce8f7695372?fields=title,year,venue,externalIds,authors,abstract"
# → DOI 10.1109/BDAI70753.2026.11655121；venue "...(BDAI)"；abstract 含 69.90/45.63 与 88.35/35.92、"45 seconds"、"50 hours"、"25-class Java system" ✅

# OpenAlex
curl -s "https://api.openalex.org/works/doi:10.1109/bdai70753.2026.11655121"
curl -s "https://api.openalex.org/works?filter=title.search:newer%20LLM%20versions"  # → ICST DOI 10.1109/icst69053.2026.00040
curl -s "https://api.openalex.org/works?search=ARC-APR"        # → 无关结果，无命中
curl -s "https://api.openalex.org/works?search=AgentRepair%20automated%20program%20repair"
# → 10.1109/dsa66321.2025.00025 ；doi.org 解析终址 = ieeexplore.ieee.org/document/11320358/ ✅

# 端点不可达记录
curl -s "https://dblp.org/search/publ/api?q=TraceCoder&format=json"   # → Anubis "Making sure you're not a bot!" ❌
curl -sL "https://ieeexplore.ieee.org/document/11655121"              # → HTTP 202，空正文（反爬）⚠️

# ── 扩展轮：全仓库 docs/ 口径（48 个 arXiv ID），max_results 必须 >= ID 数否则会被静默截断
curl -s "https://export.arxiv.org/api/query?id_list=$(paste -sd, docs_arxiv.txt)&max_results=60"
#  → returned=48 / MISSING overall: NONE (0)

# 扩展轮全文核验
curl -sL "https://arxiv.org/html/2601.18044v1"   # RGFL: "file-level Hit@1 improves from 71.4% to 85%" ✅
curl -sL "https://arxiv.org/html/2511.11012v1"   # 92.82/26.98 → 0 命中 ❌；摘要为 Codex 75.0% / Qwen Code 38.2%；Hunk4J 372 bugs ✅
curl -s -A "Audit/1.0" -G "https://api.crossref.org/works" \
     --data-urlencode "query.bibliographic=Pattern Synergistic Repair Multi-expert LoRA fusion automated program repair"
#  → "Pattern Synergistic Repair: Multi-expert LoRA fusion for automated program repair"
#    | Information and Software Technology | 10.1016/j.infsof.2026.108344 ✅（PSR 勘误可撤销）
```

### 附录 B：端点不可达导致的核验缺口（诚实披露）

| 缺口 | 原因 | 影响 |
|---|---|---|
| DBLP 全站检索 | Anubis v1.27.0 反爬挑战 | 已用 Crossref + OpenAlex + Semantic Scholar 三源替代；**未**因此降低任何判定等级 |
| IEEE Xplore 正文 | HTTP 202 空响应（反爬） | 11655121 与 11320358 均改用 Crossref/OpenAlex/S2 **摘要级**核验：**元数据与指示数字为 A 级**；**正文级细节（如 Table 5 表头、FTDI 95.65%）为 D 级** |
| FTDI "95.65%" | ScienceDirect 付费墙；OpenAlex 无摘要倒排索引 | 论文**存在性 A 级**；**数值仍为 D 级**（与项目原标注一致，未改善） |
| FedDualFix 58/52.1%、LaMAR 24.5%、LogiCase 81.18%、TwinMem 89.1% | 付费墙 / 未抓正文 | 保留 **B 级**（元数据 + 文档自述指标；本次未逐字复核） |
| "Whose Oracle Is It?" venue | 仅取得一手 PDF | 93.0% 数值未逐字复核，**B 级** |
| ImpossibleBench 的 ICLR 2026 归属 | arXiv 无 comment/journal_ref | 归属来自二手索引，**B 级**（arXiv `2510.20270` 本身为 A 级） |
| ADR-0017 多 hunk 数字 92.82%/26.98% | 仅核验 arXiv `2511.11012` **v1** 全文（0 命中） | 可能存在于 v2 或其他表；**在定位到版本与表号前不得引用**（M-15） |
| `docs/adr/0025-...:9`（13,866 测试预言 / mutation 43% vs 45%）与 `README.en.md:528` | 该两处**无 DOI/arXiv 标识符**，无标识符即无法机读定位 | 仍为**未核验**；门禁豁免清单第 1、3 条**不能移除**，建议先补标识符 |
| PSR 的 "四模式" 具体所指 | 仅取 Crossref 元数据（标题/venue/DOI），未取正文 | PSR **存在性与 DOI 为 A 级**；"四模式 LoRA" 与 "Multi-expert LoRA" 的逐字对应为 **B 级** |
| `docs/` 全域仅核验 arXiv ID 存在性 | 未逐条核验 `docs/` 内**每一个数字**（本轮聚焦门禁待办与 ADR-0017） | `docs/` 中未列入本报告的数字主张**不在本次核验范围内** |



---

## 附录 E｜对抗式验证记录（对主报告的独立复算与纠错）

> 源文件：`audit_2026/T_E_adversarial_verification.md`（本附录为该文件的完整内容，仅调整标题层级与编号）

### E·T-E 对抗式验证记录（独立 subagent 对 `FINAL_REVIEW_2026-10-11.md` 的证伪性复核）

- **验证执行者**：T-E 对抗式验证员（独立 subagent；与报告作者、与既有 `T_A`–`T_D` 审计员均非同一执行体）
- **验证时间**：2026-10-11 10:42–11:0x（Asia/Shanghai）
- **验证方式**：**零 LLM、只读**。全部数值由本次直接解析 `experiments/results/**` 原始工件重算；引用真伪由 `curl` 访问 Crossref / arXiv 机读端点独立核验。**未运行任何产生新数据的命令**（未跑 pytest、未跑 replay、未跑 LLM）。
- **写入范围**：本文件是本次验证**唯一**写入的项目内文件；未修改 `FINAL_REVIEW_2026-10-11.md`，未新增/修改任何脚本或工件。（一次性复算脚本落在 `/tmp/t_e_repro.py`，全文见附录 A。）
- **纪律**：下表每一行的"我复算值"都来自附录 A 脚本或表内标注的 heredoc 命令的实际输出；**未复算的项一律列入 §5"我无法验证"**，不以推断填充。

---

### E.0 审计对象指纹（重要：报告在本次审计过程中被就地修改过）

| 版本 | 观察到的时间/大小 | 本次能否给出哈希 | 关键差异 |
|---|---|---|---|
| **R-old**（我开始审计时读到的版本） | mtime `2026-10-11 10:42`，size **133,651 B** | **不能**：文件随后被就地覆盖，且该文件未被 git 跟踪（`git status` 显示 `?? FINAL_REVIEW_2026-10-11.md`），全盘检索无副本 | §0.2 K1 写"反事实分解：对齐'产红率'可补 **88%** 缺口，对齐'红→检出转化率'仅补 12%"；§3.4.2 写"只把产红率对齐 → 检出升至 ~244（+166）；只把转化率对齐 → ~179（+101）。**产红率缺口贡献约 88% 的差距**" |
| **R-new**（本次逐条核对的版本，即交付时点版本） | mtime `2026-10-11 10:44:59`，size **139,491 B** | **能**：`sha256 = f19b196c11cf9f2ffb5b86eec2b40a2d40063062b1c96a3438a38bf3f42aaaa1` | 同一处已改为"对齐'产红率'贡献 **44.2%**、对齐'红→检出转化率'贡献 **26.1%**、两因子交互 **29.7%**"，并附"口径更正（本报告自查）"注记 |

**处置**：§1 逐条核对以 **R-new** 为对象；凡 R-old 与 R-new 有差异处，两版分别判定。**"88%"这一表述在当前版已不存在**——若下游材料（如正文引述、汇报稿）仍在引用 R-old 的 88%/+244/+179，须以 R-new 为准。

> 结论先说：**R-new 的 44.2%/26.1%/29.7% 我独立复算一致**（算法与序贯约定见 §1.3）；**R-old 的 88% / "+166 → 244" / "+101 → 179" 均不可复算**（§3-S5 给出重建尝试）。

---

### E.1 逐条核对表

> 复算命令统一说明：**A.x** = 附录 A 脚本 `/tmp/t_e_repro.py` 的第 x 节（本次已实跑，输出见 A.11）；表内另附最小表达式。全部为 `.venv/bin/python`（Python 3，只读 `json.load`）。

#### E.1.1 §3.3 三臂核心数字（7 批 `benchmark_synthetic_2026100[67]_*.json`，各臂 609 行）

| # | 报告值（R-new） | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 1 | aitester detection **78/556 = 14.0%** | **78/556 = 14.029%** | ✅ 一致 | A.1：`sum(detection_rate==1.0) / sum(detection_rate is not None)` |
| 2 | df detection **279/571 = 48.9%** | **279/571 = 48.862%** | ✅ 一致 | A.1 同上 |
| 3 | plain_llm detection **10/609 = 1.6%** | **10/609 = 1.642%**（None=0，故可测=全集） | ✅ 一致 | A.1 同上 |
| 4 | 可测行 **556 / 571 / 609** | **aitester 556（None 53）、df 571（None 38）、plain_llm 609（None 0）** | ✅ 一致 | A.1 `detNone` |
| 5 | 三臂 repair_rate 全 0（"非 None 且为 1"=0） | **repair_rate==1.0：0 / 0 / 0**；`==0.0`：**556 / 609 / 571**；`None`：53 / 0 / 38 | ✅ 一致（但表述需精确：plain_llm 是 609 个 0，aitester/df 另有 53/38 个 `None` 而非 0） | A.1 |
| 6 | `patch_correct=0` | **三臂 `patch_correct==1` 行数 = 0 / 0 / 0**（全 1827 行 `patch_correct==0`） | ✅ 一致 | A.1 末列 |
| 7 | 产物补丁行 aitester **251**（基线两臂 0） | **251 / 0 / 0**（aitester 另有 `patch=None` 349、`patch=""` 9） | ✅ 一致 | A.1 `patch_nonempty` |
| 8 | `passed=True` **389 / 535 / 15** | **389 / 535 / 15** | ✅ 一致 | A.1 `passed=True` |
| 9 | "7 批 × 3 臂 = 12,789 行" | **1827 行/批 × 7 = 12,789** | ✅ 一致 | A.1 行数求和 |
| 10 | 检出（全集口径）df **279/609 = 45.8%**、aitester 12.8% | **45.81% / 12.81%** | ✅ 一致 | A.1 中列 |

#### E.1.2 §3.4.1 `detection_first_status` 分解（aitester 609 行）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 11 | `all_green_unverified` **296（48.6%）**，全部 `iterations=0`、patch 为空 | **296（296/609 = 48.60%）**；`iterations` 全 0；`patch` 全为 `None`（无一是空串）；`detection_rate` 全 0.0 | ✅ 一致 | A.2 |
| 12 | `red_not_repaired` **167**，`iterations 2–3`，**158 有**补丁，检出 19 | **167**（iters `{2:132, 3:35}`）；patch 非空 **158**（另 9 空）；`detection_rate==1.0` **19**（`==0.0` 148） | ✅ 一致 | A.2 |
| 13 | `red_then_green` **93**，`iterations 1–3`，全部有补丁，检出 59 | **93**（iters `{1:76, 2:15, 3:2}`）；patch 非空 **93/93**；`det=1` **59**、`det=0` **34** | ✅ 一致 | A.2 |
| 14 | `None`（不可测）**53**，`iterations 0`，无补丁 | **53**；iters 全 0；patch 全空；`detection_rate` 全 `None` | ✅ 一致 | A.2 |
| 15 | "这 296 行从未进入修复循环" | 全部 `regeneration_count==1`、`test_regenerated_pass_unverified==True`、`stop_reason=='test_passed'`、`iterations==0` → 确未进入 repair 循环 | ✅ 一致（补充证据） | A.2 |
| 16 | K1："**两版生成测试都在缺陷原码上全绿，从未产生任何 assert 失败**" | 296 行的生成测试**均含 ≥3 处 `assert`**（均值 15.3，212/296 用 `pytest.raises`）；`test_error_rate` 全 0.0；`execution_trace` 全非空且末次 `passed=True`；`detection_first_red_seen` 全 False | ✅ **不算过强（属偏窄）**：字段保证严格强于"无 assert 失败"（详见 §3-S10） | A.2 + heredoc `re.findall(r"\bassert\b", r["generated_test"])` |
| 17 | K1："df 该比例仅 **2.5%（15/609）**" | **15/609 = 2.46%** | ✅ 一致 | A.2 末行 |

#### E.1.3 §3.4.2 通道对比与反事实分解

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 18 | red_seen：aitester **260/609 = 42.7%**、df **556/609 = 91.3%** | **260/609 = 42.69%**；**556/609 = 91.30%** | ✅ 一致 | A.3 |
| 19 | 条件转化率 **78/260 = 30.0%** vs **279/556 = 50.2%** | **30.00%** vs **50.18%** | ✅ 一致 | A.3 |
| 20 | 缺口 = 279 − 78 = **201 行** | **201** | ✅ 一致 | A.3 |
| 21 | R-new 反事实：产红率 **44.2%**、转化率 **26.1%**、交互 **29.7%** | 序贯分解（以 aitester 为基准、含交互项）：**88.8 行（44.2%）+ 52.5 行（26.1%）+ 59.7 行（29.7%）= 201.0** | ✅ 一致 | A.3（见下方算法） |
| 22 | 单对齐后的检出水平（R-new §3.4.2 表：~167 / ~130） | 只对齐产红率 → **166.8 行**；只对齐转化率 → **130.5 行** | ✅ 一致 | A.3 |
| 23 | **R-old**："检出升至 ~244（+166）"/"~179（+101）"/"产红率缺口贡献约 **88%**" | **均不可复算**：244 ≈ 78 + 556×0.300 = 244.8（把"对齐后的新值 166.8"当增量又叠加了基数 78，双计）；+101 与 179 无法由任何标准分解或简单两/三项组合重建；88% 与"88.8 **行**"数值巧合，疑为单位混淆（行 vs %）。正确值：新值 166.8 / 130.5，增量 +88.8 / +52.5，占比 44.2% / 26.1% | ❌ **不一致（R-old 已作废；R-new 已修正）** | A.3；重建搜索见 §3-S5 |

**我采用的反事实算法（供复算）**：设 `p_a=260/609`、`c_a=78/260`、`p_d=556/609`、`c_d=279/556`，`N=609`；
总缺口 `G=(p_d·c_d−p_a·c_a)·N=201.0`；以 aitester 为基准的序贯（含交互）分解：
`产红率主效应=(p_d−p_a)·c_a·N=88.8`，`转化率主效应=p_a·(c_d−c_a)·N=52.5`，`交互=(p_d−p_a)·(c_d−c_a)·N=59.7`。
**该分解与次序有关**：改用以 df 为基准则为 `73.9% / 55.8% / −29.7%`（见 A.3 第二行）。报告当前只给一个次序的结果，未声明约定（见 §3-S5 建议措辞）。

#### E.1.4 §3.4.3 门 verdict × `detection_rate` 交叉表（对抗性重点）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 24 | `specific_red → detection_rate=1.0` **206/206** | **206/206**（全 7 批 3 臂） | ✅ 一致 | A.4 |
| 25 | `over_red → detection_rate=0.0` **244/244** | **244/244** | ✅ 一致 | A.4 |
| 26 | "例外仅 **2 行**" | 交叉表 **off-diagonal = 0**；`verdict=None ∧ detection=1.0` = **2 行**（即报告所称"例外"）——但**这 2 行不是门与指标的分歧行，而是"门根本没运行"的行** | ⚠️ **数值一致、定性不准确**（详见 §3-S2） | A.4 |
| 27 | "**全量**交叉表" | 交叉表只在 **4/7 批**存在（`20261007` 四批；`20261006` 三批**连 `specificity_gate_verdict` 键都没有**）；键存在行 **1044/1827**，其中 verdict 非 None 的只有 **450 行** | ⚠️ **"全量"用词不准确**（覆盖面为 450 行，非 1827 行） | A.4 |
| 28 | （报告未提）2 行例外是什么 | 2 行 = `plain_llm` 臂 / `synthetic__task_0002` / seed42 缓存重放对（`..161053` 与 `..181638`），**同一观测被计 2 次**；同行 `passed=True`、`detection_first_red_seen=False`、`detection_first_status=all_green_unverified`、`iterations=0`、`test_error_rate=0.0`、`execution_trace` 仅 1 条且 `passed=True`，却 `detection_rate=1.0`——**行内自相矛盾**。7 批全集中同类行共 **3 行**（另含 `20261006_140906` 同一任务） | ❌ 未披露，建议单列 | A.4 |

#### E.1.5 §3.5 修复（repair）口径与 QuixBugs

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 29 | "原始工件 `repair_rate` 全为 0.0（7 批**可测 556/571 行**）" | aitester **556** 个 0（+53 None）、df **571** 个 0（+38 None）、**plain_llm 609 个 0**；三臂合计 **1736 个 0** | ⚠️ 数值一致但**分母表述不全**（漏掉 plain_llm 的 609 行；556/571 是两臂口径） | A.1 |
| 30 | QuixBugs aitester detection **17/37** | **17/37** | ✅ 一致 | A.7 |
| 31 | QuixBugs aitester repair **37/40** | **37/40**（`==0.0` 3 行、`None` 10 行，共 50 行） | ✅ 一致 | A.7 |
| 32 | QuixBugs **13 行** `plausible=0 ∧ correct=1`，全落 `skip_debugger_repair_invalid` / `iterations=2` | **13 行**，13/13 `stop_reason=skip_debugger_repair_invalid`、`iterations=2` | ✅ 一致 | A.7 |
| 33 | df 臂 detection **31/37**、repair **0/41**、`iterations` 全 0、patch 全空 | **31/37**、**0/41**（`None` 9）、iters **全 0（50/50）**、`patch` 非空 **0/50**、`stop_reason` 全 `unknown` | ✅ 一致 | A.7 |
| 34 | 全库 `repair_history` 键出现 **0/7,153** | **0/7153** | ✅ 一致 | A.9 |
| 35 | `patch_correct=1 ∧ patch_plausible=0` **129 行** | **129 行**；文件分布亦相符（`aitester.json` 13、`over_red_section_verified.json` 13、`a1_strip_fixedharness.json` 12…） | ✅ 一致 | A.9 |
| 36 | §3.5.1 独立重放 87→54→20→**0.3704** | **未复算**（需运行 `experiments.repair_replay`，非只读） | ❓ 见 §5 | — |

#### E.1.6 §3.7 真实仓库基准普查（`experiments/results/**/*.json`，按工件顶层 `dataset` 字段）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 37 | `swe_bench` **293 行** + `swe_bench_pro` **72 行** = **365 行** | **293 + 72 = 365** | ✅ 一致 | A.5 |
| 38 | 100% `instance_code` 为空 | **293/293、72/72 = 365/365 为空** | ✅ 一致 | A.5 |
| 39 | 100% 行内不存在 `detection_rate` 键 | **365/365 无该键** | ✅ 一致 | A.5 |
| 40 | `passed=True`：swe_bench **4**、pro **0** | **4 / 0**（合计 4/365） | ✅ 一致 | A.5 |
| 41 | "全部 **23 个**唯一真实仓库基准工件" | **23 个含 ≥1 行的工件**（swe_bench 11 + swe_bench_pro 12）；另有 `swebench_20_summary.json` 带 `dataset` 字段但 0 行（不计入，与"23"自洽） | ✅ 一致 | A.5 `artifacts` |
| 42 | `error_category` 为 `syntax`(**19**)/`patch_validation_failed`(**18**)/`execution_trace_missing`(**20**) 等 | 365 行普查实为：**swe_bench** `patch_validation_failed 76`、`""125`、`execution_trace_missing 59`、`syntax 28`、`import_error 2`、`index_error 1`、`timeout 1`、`unknown 1`；**swe_bench_pro** `patch_validation_failed 72`。报告的 19/18/20 实为**单个 60 行工件**的分布（`benchmark_swe_bench_20260925_162822.json` = 20/20/20 或 `..184622.json` = 18/19/23），**不是普查值** | ❌ **不一致** | A.5 `err_*`；单批定位：heredoc 遍历 `dataset=="swe_bench"` 且 `rows==60` 的工件 |
| 43 | （附注）`swe_bench` 293 行的构成 | 其中 **3 行** `task_metadata.source == 'examples'`（`benchmark_swe_bench_20260921_175906.json`，`total_tasks=3`，任务名 `examples__calculator_divide` 等），并非 SWE-bench 任务；不影响 100% 不可测结论 | ⚠️ 细节未披露（低） | A.5 + heredoc 打印该文件行 |

#### E.1.7 §3.8 伪重复（对抗性重点）

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 44 | seed42 对（`..161053` ↔ `..181638`）逐值相同 **143/261**（aitester 45/87、plain_llm 49/87、df 49/87） | **按行序（positional）比较**：45/87、49/87、49/87 = **143/261**（与报告逐位相同）；**按 `task_id` 对齐比较**：**78/87、87/87、87/87 = 252/261** | ❌ **报告值只对"行序对齐"成立；该对齐无效**（两文件仅 49/87 个位置是同名任务）→ 报告**低估**重复度 | A.6 |
| 45 | seed44 对（`..170147` ↔ `..185941`）逐值相同 **140/261**（42/49/49） | 行序对齐：42/87、49/87、49/87 = **140/261**（与报告一致）；`task_id` 对齐：**75/87、87/87、87/87 = 249/261** | ❌ 同上 | A.6 |
| 46 | 比较字段 = `detection_rate`/`repair_rate`/`passed`/`generated_test`/`detection_first_status`/`specificity_gate_verdict`/`stop_reason`/`patch` | 本次用**同一字段集**、同一 `==` 语义复算；两对批次 `seed` 字段均为 42/42、44/44 | ✅ 字段集本身无误 | A.6 |
| 47 | "该 seed 真实独立值 `specificity_gate` 为 9/18" | `..161053` aitester：`specific_red=9`、`over_red=18`（另 60 行 None）；四批 aitester 合计 40/66 | ✅ 一致 | A.4 |
| 48 | §2.2 A6 / §7 G6 / P0-5 引用"140–143/261" | 同上，应为 **249–252/261**（`task_id` 对齐） | ❌ 连带需改 | A.6 |
| 49 | §3.8 机制："`AITESTER_LLM_CACHE_NAMESPACE` 按 seed 命名" | 代码中**不存在** `AITESTER_LLM_CACHE_NAMESPACE`；实际变量为 **`AITESTER_CACHE_NAMESPACE`**（`src/agents/base_agent.py:388`；`experiments/run_benchmark.py:2431-2432` 自动设 `seed<N>`），命名空间注释见 `:384-393`、`run_benchmark.py:2426-2432` | ❌ 变量名错误（机制结论不受影响） | `grep -rn AITESTER_LLM_CACHE_NAMESPACE .`（0 命中）；`grep -n AITESTER_CACHE_NAMESPACE src/agents/base_agent.py experiments/run_benchmark.py` |

#### E.1.8 §3.6 / K8 全库 `oracle_type` 普查

| # | 报告值 | 我复算值 | 判定 | 复算命令 |
|---|---|---|---|---|
| 50 | "**全库/全量** `oracle_type` 普查：`generated_test` **1,803**（aitester）/ `None` **1,672**" | 1,803/1,672 是**文件名以 `benchmark_` 开头的工件子集**的 aitester 计数（精确命中）；**全库** aitester 为 `generated_test 2,015` / 键缺失 `1,788`；**全部臂**合计 `generated_test 3,968` / 键缺失 `3,185`（总行 7,153） | ❌ **数字口径标注错误**（"全库/全量"名不副实；真值高 212 行/AITESTER、2,165 行/全臂） | A.8 |
| 51 | "`None` 1,672" | **键不存在**才是 1,672/1,788；**不存在"键存在且值为 None"的行**（全库 0 行） | ⚠️ 应为"键不存在"而非"None" | A.8 |
| 52 | "无一行 `enhanced_generated_test`（任何 enhanced/spec oracle）" | **确认**：全库**键存在且取值非 `generated_test` 的行数 = 0**；`oracle_type` 仅两种状态（`generated_test` 或键缺失） | ✅ 一致（结论成立且更强） | A.8 末行 |
| 53 | 7 批中 `spec_oracle_verdict` / `spec_oracle_injected` 键不存在 | **0/1827、0/1827** | ✅ 一致 | A.9 |

#### E.1.9 §3.3/§3.4.3/§3.8 的代码依据（"是否同一函数"等）

| # | 报告表述 | 代码核查结果 | 判定 | 复算命令 |
|---|---|---|---|---|
| 54 | "三臂的 detection 由同一个函数计算（`run_benchmark.py:1094` → `_m1_metrics.py` 的 `_compute_detection_rate`）" | **成立**：`run_benchmark.py:952 def _build_task_result(...)` 是**唯一**行构造器，被 5 处调用（`:1584, :1875, :1904, :1917, :1929`）覆盖全部臂；`:1094` 在同一构造器内调用 `_compute_detection_rate`；该名字在 `run_benchmark.py:536-542` 是**薄封装**，直接 `from experiments._m1_metrics import _compute_detection_rate`（实现 `_m1_metrics.py:473`）。**三臂共享同一 fail-to-pass 三段判据** | ✅ 有代码依据 | `grep -n "_build_task_result(\|_compute_detection_rate" experiments/run_benchmark.py`；`sed -n '536,542p;1088,1096p'` |
| 55 | "因此 −34.9pp 不是'口径不对称'造成的" | **该推论强于代码证据**：指标函数与判据同一，但**传入的 `final_state` 由各臂各自管线产出**（`aitester` 走完整图；`plain_llm_df` 为 `build_workflow(planner=False, debugger=False, allow_regeneration=True)` + 线程级 `set_detection_first_thread_override(True)`，见 `:381-421`）。故"指标定义对称"成立，"输入分布/管线行为对称"不成立 | ⚠️ 建议限定措辞 | `sed -n '381,421p;425,430p' experiments/run_benchmark.py` |
| 56 | 门"只取 `rc==0` 当绿（`detection_gates.py:96-121`），未复用 `_looks_like_test_execution_error`；且不传 `task_metadata`（`:85-87`）" | **成立**：`detection_gates.py:87` 为 `res = _runner(test_code, target_code, module_name, timeout=timeout)`（无 `task_metadata` 参数）；`grep` 显示 `_looks_like_test_execution_error` 与 `task_metadata` 在该文件**0 命中**；`green = res[0] == 0` | ✅ 一致（citation 行号落在函数体内，可接受） | `grep -n "_runner(test_code\|_looks_like_test_execution_error\|task_metadata" src/tools/detection_gates.py` |
| 57 | `MAX_REGENERATIONS=1`（`config.py:375`）、`workflow.py:682-699` 首轮全绿→regenerate、`:734-743` `_recent_repairs_invalid` 提前 done | **逐条成立**：`config.py:375 MAX_REGENERATIONS: int = 1`；`workflow.py:682-699` 即"首轮全绿且未 red_seen 且预算未用尽 → regenerate"；`:734-743` 即"`iteration < max_iterations` 且 `_recent_repairs_invalid` → done" | ✅ 一致 | `sed -n '682,699p;734,743p' src/graph/workflow.py`；`grep -n MAX_REGENERATIONS config.py` |

---

### E.2 引用抽查表（独立 `curl` 机读端点，HTTP 状态 + 标题/作者比对）

> 端点：`https://api.crossref.org/works/<DOI>`、`https://export.arxiv.org/api/query?id_list=<id>`。命令形如
> `curl -s -o out.json -w "HTTP %{http_code}\n" --max-time 25 "<URL>"`，再用 Python 解析 `message.title/author/container-title/published`。

| # | 引用（报告 §16） | URL | HTTP | 端点返回标题 / 作者 | 与报告一致？ | 判定 |
|---|---|---|---|---|---|---|
| C1 | CANDOR，TOSEM 2026，DOI 10.1145/3803418 | `https://api.crossref.org/works/10.1145/3803418` | **200** | *Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation* / Xu Qinghua, Wang Guancheng, Briand Lionel, Liu Kui / ACM TOSEM / 2026-03-25 | **完全一致** | ✅ A |
| C2 | TestAgent，DOI 10.1145/3803437.3806428 | `.../10.1145/3803437.3806428` | **200** | *TestAgent: A Multi-Agent LLM Framework for Repository-Level Unit Test Generation* / Shang Ye, Zhang Quanjun, Zhan Zhengyu, Huang Ke, Fang Chunrong, Chen Zhenyu / *Proceedings of the 34th ACM International Conference on the Foundations of Software Engineering* / 2026-07-05 | 标题、作者、年份一致；**容器名未含 "Companion"**（报告写 "FSE Companion 2026"） | ✅（venue 后缀待核，低） |
| C3 | Konstantinou 等，ICST 2026，DOI 10.1109/icst69053.2026.00040 | `.../10.1109/icst69053.2026.00040` | **200** | *How well LLM-based test generation techniques perform with newer LLM versions?* / Konstantinou Michael, Degiovanni Renzo, Papadakis Mike / *2026 IEEE International Conference on Software Testing, Verification and Validation (ICST)* / 2026-05-18 | **完全一致** | ✅ A |
| C4 | AdverTest，DOI 10.1145/3832122（ISSTA 2026） | `.../10.1145/3832122` | **200** | *Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation* / Chang Pengyu, Fang Yixiong, Chen Silin, Shi Yuling, Shen Beijun, Gu Xiaodong / *Proceedings of the ACM on Software Engineering* / 2026-10-01 | 标题、作者一致；PACMSE 卷 = ISSTA 会议录，与"IsSTA 2026"自洽 | ✅ A |
| C5 | Zhao/Zhou/Cohen，DOI 10.1145/3832093（ISSTA 2026） | `.../10.1145/3832093` | **200** | *Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)* / Zhao Junda, Zhou Shurui, Cohen Eldan / PACMSE / 2026-10-01 | **一致**（报告写 "Zhao, J., Zhou, S., Cohen, E."，端点给出 Junda/Shurui/Eldan） | ✅ A |
| C6 | arXiv:2609.09315 | `https://export.arxiv.org/api/query?id_list=2609.09315` | **200**（entries=1） | *How effective are traditional test criteria at detecting bugs in large language models generated code?* / Asma Hamidi, Michael Konstantinou, Renzo Degiovanni, Mike Papadakis / published **2026-09-08** | **完全一致**（报告 §16[1] 作者、日期、标题逐项相符） | ✅ A |
| C7 | arXiv:2609.17394 | `...?id_list=2609.17394` | **200**（entries=1） | *Coding Agents Have Converged: Why the SWE-bench Leaderboard Can No Longer Order Its Top Entries, and What to Measure Instead* / Fengshuo Liu, Ying Liu, Ruize Sun, Lie Luo, Siyuan Guo / **2026-09-15** | 标题、作者一致；**报告标注的 "ADMA 2026" 未在 arXiv 元数据中出现，本次未核** | ✅（数值级一致）/ venue 见 §5 |
| C8 | arXiv:2602.08146 | `...?id_list=2602.08146` | **200**（entries=1） | *Test vs Mutant: Adversarial LLM Agents for Robust Unit Test Generation* / Pengyu Chang, Yixiong Fang, Silin Chen, Yuling Shi, Beijun Shen, Xiaodong Gu / **2026-02-08** | **完全一致**（与 C4 同一工作） | ✅ A |
| C9 | （附加，用于核 K9）arXiv:2601.09695 | `...?id_list=2601.09695` | **200** | *How well LLM-based test generation techniques perform with newer LLM versions?* / Konstantinou, Degiovanni, Papadakis；摘要内出现 **17.72% / 19.80% / 20.92%** | 与 K9 的"该文原文报告相对提升 17.72/19.80/20.92%"一致；项目 `README.md:27` 确将其写成 "Plain-LLM 49.95/35.33/33.82" | ✅ A（**支持 K9**） |

**结论**：8 个指定引用 **8/8 端点 HTTP 200，标题/作者与报告一致**；无虚构引用。仅 C2 的 venue 后缀（Companion）与 C7 的 venue（ADMA）未获端点直接背书。

---

### E.3 主动找茬：应修正清单（按严重度排序，附建议措辞）

> 严重度定义：**高** = 数字或定性结论不成立/不可复算；**中** = 数字口径标注错误或关键限定缺失，可能被审稿人直接质疑；**低** = 事实性小错/表述可更严谨。

### S1（高）§3.8（第 353–354 行）+ §2.2 A6（第 171 行）+ §7 G6/G7 + P0-5（第 744 行）：伪重复行数用"行序对齐"比较，**低估**重复度

- 报告值：`143/261`、`140/261`（附 aitester 45/42、plain_llm 49/49、df 49/49）。
- 我复算：这两个数**只能用"按列表下标逐位比较"复现**；但两文件**任务顺序不同**（仅 **49/87** 个位置是同一 `task_id`）。按 `task_id` 对齐、用报告自己声明的 8 个字段比较 → **252/261**（78/87、87/87、87/87）与 **249/261**（75/87、87/87、87/87）。
- 影响：结论方向不变（同 seed 重跑确为缓存确定性重放），但报告数字**低报约 10pp**；plain_llm/df 两臂实为**逐行完全相同**（87/87），报告写 49/87 会被轻易证伪。
- 建议措辞：*"同 seed 两批按 `task_id` 对齐后，8 个核心字段逐值相同的行数为 **252/261**（seed42：aitester 78/87、plain_llm 87/87、df 87/87）与 **249/261**（seed44：75/87、87/87、87/87）——即 96% 的行是缓存的确定性重放。注意两批任务顺序不同（仅 49/87 位置同名），任何按下标对齐的比较都会低估重复度。"*

### S2（高）§3.4.3（第 283 行）+ §0.2 K2（第 42 行）+"例外仅 2 行"与"全量交叉表"两处不准确

- 事实 A：门判据只在 **`20261007` 四批**落盘（`20261006` 三批**无 `specificity_gate_verdict` 键**）。"全量"实际覆盖 = 键存在 1044 行 / verdict 非 None **450 行**（不是 1827 行）。
- 事实 B：有 verdict 的行 **off-diagonal = 0**（`specific_red→1.0` 206/206；`over_red→0.0` 244/244）——报告的核心等价性**成立**。
- 事实 C：所谓"2 行例外"是 `verdict=None ∧ detection_rate=1.0`：`plain_llm` 臂 `synthetic__task_0002`，seed42 缓存重放对的两个副本（同一观测计两次；7 批中共 3 行）。**它们不是门与指标的分歧，而是"门未运行"的行**；更严重的是**这 3 行自身矛盾**：`detection_rate=1.0` 与同行 `passed=True`、`detection_first_red_seen=False`、`detection_first_status=all_green_unverified`、`iterations=0`、`execution_trace=[{passed:True}]` 直接冲突。
- 建议措辞：*"在门实际运行的 450 行（E1/E2 四批）上，`specific_red→det=1` 206/206、`over_red→det=0` 244/244，off-diagonal 为 0；另有 2 行（同一任务 `synthetic__task_0002` 的缓存重放副本，7 批共 3 行）门未运行却 `detection_rate=1.0`，且与同行 `passed=True / red_seen=False / iterations=0` 自相矛盾——该异常应单列，不应作为'门的例外'，也不应计入门-指标等价性的分母。"*

### S3（中）K8（第 48 行）/§2.1（第 155 行）/§3.6（第 329 行）/§11 C-10（第 789 行）：`oracle_type` 计数被标为"全库/全量"，实为 `benchmark_*.json` 文件名子集

- 报告值：**全库** `generated_test` 1,803（aitester）/ `None` 1,672。
- 我复算：1,803 / 1,672 精确等于"文件名以 `benchmark_` 开头的工件"子集；**全库**为 aitester `generated_test` **2,015**、键缺失 **1,788**；全臂合计 `generated_test` **3,968**、键缺失 **3,185**（总行 7,153，与 §2.2 A7/§3.11 使用的 7,153 一致）。
- 另有口径错：1,672 是"**键不存在**"，不是"值为 `None`"——全库**没有**任何"键存在且值为 None"的行。
- 结论（0 行 enhanced/spec oracle）**不受影响且已独立确认**。
- 建议措辞：*"全库 7,153 行中 aitester 2,015 行 `oracle_type='generated_test'`、1,788 行不含该键；全部臂合计 3,968 / 3,185。**没有任何一行取 `generated_test` 以外的值**（即 0 行增强/规约 oracle）。若仅统计 `benchmark_*.json` 工件，aitester 为 1,803 / 1,672。"*

### S4（中）§3.7（第 346 行）：`error_category` 的 "(19)/(18)/(20)" 不是 365 行普查结果

- 我复算普查值：`patch_validation_failed` **148**（swe_bench 76 + pro 72）、`execution_trace_missing` **59**、`syntax` **28**、空串 125、`import_error` 2、`index_error` 1、`timeout` 1、`unknown` 1。
- 19/18/20 精确对应**单个 60 行工件**的分布（如 `benchmark_swe_bench_20260925_184622.json` = syntax? 实测为 `{'' 23, patch_validation_failed 18, execution_trace_missing 19}`；`..162822.json` = 20/20/20）——按上下文它被当成普查分布引用。
- 建议措辞：*"365 行的 `error_category` 普查：`patch_validation_failed` 148、`execution_trace_missing` 59、`syntax` 28、空串 125 等（以 lite20 单批 60 行为例，则三类分别为 18/19/20）。"*

### S5（中）§3.4.2 反事实分解：当前版算术成立，但缺"分解次序约定"声明；旧版 88% 系口径错误（已被就地更正）

- 当前版 44.2% / 26.1% / 29.7% 我独立复算**逐位一致**（算法见 §1.3）。
- 但序贯分解**依赖次序**：以 df 为基准则为 73.9% / 55.8% / −29.7%。报告未声明"以 aitester 为基准"。
- 旧版（R-old）的"88% / ~244（+166）/ ~179（+101）"不可复算：244 = 78 + 556×0.300 属**基数双计**（正确新值 166.8）；+101/179 无法从工件重建；"88%"疑为把"88.8 行"写成百分比。
- 建议措辞：*"反事实分解采用**以 aitester 为基准的序贯（含交互项）分解**：产红率主效应 (0.913−0.427)×0.300×609 = +88.8 行（44.2%）、转化率主效应 0.427×(0.502−0.300)×609 = +52.5 行（26.1%）、交互 +59.7 行（29.7%）；若改用 df 基准，三者为 148.5/112.2/−59.7 行（73.9%/55.8%/−29.7%），故结论'产红率是最大单一因子'应限定在该次序约定下。"*

### S6（低）§3.8（第 357 行）：缓存命名空间变量名写错

- 报告写 `AITESTER_LLM_CACHE_NAMESPACE`；代码实为 **`AITESTER_CACHE_NAMESPACE`**（`src/agents/base_agent.py:388`；`experiments/run_benchmark.py:2431-2432` 自动设 `seed{seed}`）。全仓对错误变量名 **0 命中**。
- 建议：直接替换变量名。

### S7（低）§3.5.1（第 288 行附近）："7 批可测 556/571 行"易误读

- 实际：aitester 556 个 0（+53 `None`）、df 571 个 0（+38 `None`）、**plain_llm 609 个 0**；三臂合计 1736 个 0，且 `patch_correct==1` 全库为 0。
- 建议措辞：*"7 批三臂 `repair_rate` 无一为 1.0：`0.0` 共 1736 行（aitester 556、plain_llm 609、df 571），另 91 行为 `None`（不可测）；`patch_correct=1` 行数为 0。"*

### S8（低）§3.7：`swe_bench` 293 行中含 3 行非 SWE-bench 行

- `benchmark_swe_bench_20260921_175906.json`（`dataset=swe_bench`, `total_tasks=3`）的 3 行 `task_metadata.source='examples'`（`examples__calculator_divide` 等）。
- 建议：加一句括注，或按 `task_metadata.source` 复核该文件归类；不影响"100% 不可测"。

### S9（低）§5.1 / §5.2 / §0.4（第 72 行）："不可比"维度上仍给出比较性判定（内部张力）

- 事实：§5.1 的"绝对差距/相对差距"两列**全部为 "—"**，纪律的字面要求（不给差距数字）**成立**。
- 但"程序修复：端到端成功率"行 `可否对比=否（任务分布差异过大，仅可作方向性判断）`，同一行"竞争位置"却写 **"落后（合成集）"**；§5.2 进一步写"**程序修复 | 落后**（合成集 all-task 21.84%；真实基准仅玩具程序 74.0%）"；§0.4 写"**低于** SWE-bench Verified 一线方法数量级"。把"自生成合成集 all-task 21.84%"与"SWE-bench Verified 榜首 396/500=79.2%"并置，构成事实上的数量级对比，与"否（不可比）"冲突。
- 建议措辞：*"程序修复：合成集 all-task 21.84%（57/261）、可重放口径 39.31%；与 SWE-bench Verified 79.2% **任务分布不同，不构成数量级对比**，仅可判定'未在公开基准上建立可比的端到端修复证据'。"*

### S10（低）K1/§5.1："从未产生 assert 失败"——**不是过强，而是偏窄**（建议改得更准）

- 字段定义（`src/graph/nodes.py:649-672` + `src/graph/state.py:184`）：`all_green_unverified` = 终态 `passed=True ∧ detection_first_red_seen` 为假；其中 `red_seen` 只在 `iteration==0` 写、且为**粘性**（任一次首轮执行 `not passed` 即 True）。
- 因此该字段的保证是"**首轮与再生成版在缺陷原码上都没有出现任何非零退出**（含断言失败、收集/导入错误）"——**严格强于**"没有 assert 失败"。故 K1 的措辞并不过强。
- 佐证（我复算）：296 行 `iterations=0`、`regeneration_count=1`、`test_regenerated_pass_unverified=True`（第二版也通过）、`test_error_rate=0.0`、`execution_trace` 全非空、生成测试**每行 ≥3 处 `assert`**（均值 15.3）。故"两版都在缺陷原码上全绿"成立。
- 建议措辞：*"48.6%（296/609）的 aitester 行终态为 `all_green_unverified`：首版与再生成版在缺陷原码上均 rc==0 全绿（`red_seen=False`、`iterations=0`、无补丁），从未出现任何红灯——既未覆盖到缺陷，也未产出可归因的断言失败。该字段本身不区分'测试没覆盖缺陷'与'断言写错/写反'（见 K7）。"*

### 附带观察（低，跨文档）

`audit_2026/T_B_code_domain_audit.md` 的反事实口径（"只对齐 red 产生率 → 28.1%；只对齐转化率 → 20.9%"）与报告 §3.4.2 的基数不同：其隐含 aitester red_seen = **254**，恰等于 **`20261006` 三批**的 df red_seen 计数（我复算：10-06 三批 df red_seen=254、aitester red_seen=154；10-07 四批 df=302、aitester=106；7 批 df=556、aitester=260）。两文件若被同一审稿人交叉阅读，会看到不一致的反事实百分比；建议统一到 §1.3 的算法与基数（aitester 260/609、df 556/609）。

---

### E.4 对四项指定深查的直接回答

1. **"48.6% 的行从未产生 assert 失败"是否与工件字段一致？** → **一致，但措辞偏窄**。字段语义是"从未变红（首轮与再生成版均 rc==0）"，比"无 assert 失败"更强；296 行确有断言（≥3 处/行）且执行痕迹完整。建议按 §3-S10 改词。
2. **"产红率缺口贡献约 88%" 是否可复算？** → **R-old 不可复算**（正确：主效应 88.8 **行** = 44.2%，另转化率 52.5 行 = 26.1%、交互 59.7 行 = 29.7%）；**R-new 已改为 44.2/26.1/29.7，我复算一致**。算法与次序依赖见 §1.3、§3-S5。
3. **"三臂同一函数计算 detection" 是否有代码依据？** → **有**（`_build_task_result` 唯一构造器 + `:1094` + 薄封装 `:536-542` → `_m1_metrics.py:473`）；但"因此 −34.9pp 与口径不对称无关"是**推论**，需限定为"指标定义与判据对称；输入状态由各臂各自管线产出"（§3-S54/55）。
4. **§5 的"不能对比"判定是否内部矛盾？** → **无差距数字**（两列全 "—"，字面纪律成立）；**但存在判定级矛盾**：标"否"的程序修复行仍给"落后"，§0.4 用"低于……数量级"把合成集 21.84% 与 SWE-bench Verified 79.2% 并置（§3-S9）。

---

### E.5 我无法验证的项（明确声明，不以推断填充）

| # | 项 | 原因（具体） |
|---|---|---|
| U1 | **R-old 报告的 sha256** | 文件在审计中途（10:42→10:44:59）被就地覆盖；该文件未被 git 跟踪，全盘检索无副本。只能提供我阅读时的大小（133,651 B）与原文引述 |
| U2 | §3.5.1 的独立重放链（带补丁 **87** → 可重放 **54** → correct **20** → **0.3704**）与 §3.1 P2/P3 的 39.31% / 54.72% | 需要运行 `experiments.repair_replay`（会执行 gold 测试，非只读）；本次只读范围外。本次仅确认**原始工件** `repair_rate` 无一为 1.0、`patch_correct==1` 为 0（与报告一致） |
| U3 | `~/.cache` 内 **225 个** SWE-bench 实例缓存"0 行含 `instance_code`" | 未访问 `~/.cache`（本次只读范围限定在仓库内工件） |
| U4 | §3.9 成本口径（E1/E2 **348/348** 行 0-token、df 35/261、E6 phase1 0/87、$/task 比值） | 未复算（非本次指定范围）；仅确认 7 批行内 `token_usage` 字段存在 |
| U5 | §3.10 三个孤儿进程（pid 36935/37116/37498）、§3.2 测试全量跑批（5,311 passed / 2 failed）、§1.2 文件规模（7,502 文件 / 103.5 MB / 行数统计） | 未复算（需运行进程/测试套件或全目录遍历统计，超出本次只读抽样范围） |
| U6 | §4/§5 中前沿数值的**正文级**核对（如 F-1 的"检出率 1–2%"、TestAgent 97.46/92.34、ULT 45.10、SWE-bench Verified 396/500、TraceCoder +34.43%、LANTERN +22.09%） | 本次只核**元数据端点**（标题/作者/venue/日期），未逐篇读全文核对每个指标；该部分属 `T_C`/`T_D` 的职责范围 |
| U7 | venue 标注：arXiv:2609.17394 的 "ADMA 2026"、TestAgent 的 "FSE **Companion** 2026" | Crossref/arXiv 元数据未直接给出该后缀；未进一步查会议录目录 |
| U8 | §3.7 的"代码归因"（`_extract_gold_material` 对 `source=="swe_bench"` 直接 `return None`、`_gold_fixed_code` 返回 `""`、detection 要求 `instance_code` 非空） | 本次**部分**核到：`_m1_metrics.py:506-508` 的 `instance_code` 判空我读到了；`430-431`/`462-463` 两处仅按报告行号抽查上下文，未逐行核验 return 语句（属 `T_B` 范围） |
| U9 | QuixBugs 数值的**口径**判定（17/37 是否等价于"缺陷检出能力"、df 臂"不可比"的强度） | 我只能复算数值；口径合理性属判断问题，本次不代替领域结论 |
| U10 | §3.4.1 "第二版仍全绿 → 直接 done"的**完整轨迹** | 工件只落最终 `detection_first_status`/`regeneration_count`/`test_regenerated_pass_unverified`，无逐轮 trace 落盘；我用字段组合（296/296 均为 `iterations=0 ∧ red_seen=False ∧ 第二版 passed=True`）**推断**成立，未取得逐轮证据 |

---

### E.6 验证结论

1. **§3.3 三臂核心数字（detection、可测行、repair、patch、passed）逐位复算一致**；§3.4.1 的 296/167/93/53 及其不变式（iterations/patch/det）**逐位一致**；§3.4.2 的 red_seen 与转化率**逐位一致**；§3.4.3 的 206/206、244/244 **逐位一致**；§3.5 的 QuixBugs 与全库不变量（repair_history 0/7153、129 行违反）**一致**；§3.7 的 293+72=365、100%/100%、passed=4 **一致**；§1.8 的"0 行 enhanced/spec oracle" **确认成立**。
2. **发现 3 处不应放过的实质问题**：**S1**（§3.8 伪重复用行序对齐 → 252/249 被写成 143/140，低报 10pp）、**S2**（§3.4.3"全量交叉表/例外 2 行"口径不实，且那 2 行是 metric 与信号自相矛盾的异常行）、**S3**（K8 的 1,803/1,672 被标为"全库"，实为 `benchmark_*` 子集；全库 aitester 为 2,015）。
3. **R-old 的"88%"反事实错误已在 R-new 中更正**，更正后的 44.2/26.1/29.7 我独立复算一致；但需补"分解次序约定"（S5）。
4. **8/8 指定引用真实**（HTTP 200，标题/作者一致），无虚构；K9 关于 arXiv:2601.09695 的更正**得到端点支持**。
5. **未复算项已逐条列于 §5**（含 R-old 哈希不可得、repair 重放链、成本/覆盖率/测试套件/前沿正文数值）。

---

### E·附录 A：一次性复算脚本（本次实际执行，未写入仓库）

执行方式（本次实跑）：

```bash
cd /Users/wangchenyu/Workspace/AITester
cat > /tmp/t_e_repro.py <<'PY'   # ← 下方 A.1–A.10 全文
...
PY
.venv/bin/python /tmp/t_e_repro.py 2>&1 | tee /tmp/t_e_repro.out
```

### A.1–A.10 脚本全文

```python
"""T-E 对抗式验证：一次性只读复算脚本（零 LLM）。运行：.venv/bin/python /tmp/t_e_repro.py"""
import json, glob, os, collections, itertools, hashlib
R = "experiments/results"
def rows_of(f, arm):   return json.load(open(f))["results"][arm]["details"]
MAIN = sorted(glob.glob(f"{R}/main_batch/benchmark_synthetic_2026100[67]_*.json"))
ARMS = ("aitester", "plain_llm", "plain_llm_df")

print("### 1. 7 批 × 3 臂（文件数=%d）" % len(MAIN))
for arm in ARMS:
    rs = [r for f in MAIN for r in rows_of(f, arm)]
    det = [r.get("detection_rate") for r in rs]
    meas = [x for x in det if x is not None]
    rep = [r.get("repair_rate") for r in rs]
    print(f"[{arm}] rows={len(rs)} det=1:{sum(1 for x in meas if x==1.0)}/{len(meas)} "
          f"({sum(1 for x in meas if x==1.0)/len(meas)*100:.1f}%) detNone={len(det)-len(meas)} "
          f"| all-rows {sum(1 for x in det if x==1.0)}/{len(det)}={sum(1 for x in det if x==1.0)/len(det)*100:.1f}% "
          f"| repair=1:{sum(1 for x in rep if x==1.0)} repair=0:{sum(1 for x in rep if x==0.0)} repNone:{sum(1 for x in rep if x is None)} "
          f"| patch_nonempty:{sum(1 for r in rs if (r.get('patch') or '').strip())} "
          f"| passed=True:{sum(1 for r in rs if r.get('passed') is True)} | patch_correct=1:{sum(1 for r in rs if r.get('patch_correct')==1)}")

A = [r for f in MAIN for r in rows_of(f, "aitester")]
D = [r for f in MAIN for r in rows_of(f, "plain_llm_df")]
print("\n### 2. aitester(detection_first_status / iterations / patch / det)")
st = collections.Counter(r.get("detection_first_status") for r in A)
for k, v in st.most_common():
    sub = [r for r in A if r.get("detection_first_status") == k]
    print(f"  {str(k):22} n={v:3} ({v/len(A)*100:.1f}%) iters={dict(collections.Counter(r.get('iterations') for r in sub))} "
          f"patch_nonempty={sum(1 for r in sub if (r.get('patch') or '').strip())} "
          f"det1={sum(1 for r in sub if r.get('detection_rate')==1.0)} det0={sum(1 for r in sub if r.get('detection_rate')==0.0)}")
ag = [r for r in A if r.get("detection_first_status")=="all_green_unverified"]
print(f"  all_green 不变式: iterations全0={all(r.get('iterations')==0 for r in ag)} "
      f"patch全None/空={all(not (r.get('patch') or '').strip() for r in ag)} det全0={all(r.get('detection_rate')==0.0 for r in ag)} "
      f"passed全True={all(r.get('passed') is True for r in ag)} red_seen全False={all(r.get('detection_first_red_seen') is False for r in ag)} "
      f"regeneration_count={dict(collections.Counter(r.get('regeneration_count') for r in ag))} "
      f"test_regenerated_pass_unverified全True={all(r.get('test_regenerated_pass_unverified') is True for r in ag)} "
      f"execution_trace非空={sum(1 for r in ag if r.get('execution_trace'))}/{len(ag)} "
      f"test_error_rate全0={all(r.get('test_error_rate')==0.0 for r in ag)}")
print(f"  df all_green_unverified={sum(1 for r in D if r.get('detection_first_status')=='all_green_unverified')}/{len(D)}")

print("\n### 3. red_seen / 转化率 / 反事实分解")
pa, ca = sum(1 for r in A if r.get('detection_first_red_seen') is True)/len(A), 78/260
pd, cd = sum(1 for r in D if r.get('detection_first_red_seen') is True)/len(D), 279/556
print(f"  aitester red_seen={pa*len(A):.0f}/{len(A)}={pa*100:.1f}%  df red_seen={pd*len(D):.0f}/{len(D)}={pd*100:.1f}%")
print(f"  转化率 aitester=78/260={ca*100:.1f}%  df=279/556={cd*100:.1f}%")
N, ga = len(A), 279-78
e1 = (pd-pa)*ca*N; e2 = pa*(cd-ca)*N; inter = ga-e1-e2
print(f"  aitester-base 3 项分解: 产红率={e1:+.1f} ({e1/ga*100:.1f}%) 转化率={e2:+.1f} ({e2/ga*100:.1f}%) 交互={inter:+.1f} ({inter/ga*100:.1f}%) 合计={e1+e2+inter:.1f}/{ga}")
f1 = (pd-pa)*cd*N; f2 = pd*(cd-ca)*N
print(f"  df-base 3 项分解      : 产红率={f1:+.1f} ({f1/ga*100:.1f}%) 转化率={f2:+.1f} ({f2/ga*100:.1f}%) 交互={ga-f1-f2:+.1f} ({(ga-f1-f2)/ga*100:.1f}%)")
print(f"  单对齐新值: 产红率对齐 -> {pd*ca*N:.1f} 行; 转化率对齐 -> {pa*cd*N:.1f} 行")

print("\n### 4. 门 verdict × detection_rate（3 臂）")
allrows = [r for f in MAIN for arm in ARMS for r in rows_of(f, arm)]
ct = collections.Counter((str(r["specificity_gate_verdict"]), r.get("detection_rate")) for r in allrows if "specificity_gate_verdict" in r)
print("  键存在行数=%d / 总行数=%d" % (sum(ct.values()), len(allrows)), dict(ct))
print("  verdict=非 None 的行数:", sum(1 for r in allrows if r.get("specificity_gate_verdict")))
gate_files = sorted({os.path.basename(f) for f in MAIN if any(r.get("specificity_gate_verdict") for arm in ARMS for r in rows_of(f, arm))})
print("  含非 None verdict 的批次:", len(gate_files), [x[-15:-5] for x in gate_files])
anom = [(f.split('/')[-1], arm, r.get("task_id")) for f in MAIN for arm in ARMS for r in rows_of(f, arm)
        if r.get("detection_rate")==1.0 and r.get("detection_first_red_seen") is not True]
print("  detection=1 但 red_seen≠True 的行:", anom)

print("\n### 5. SWE 普查（按工件顶层 dataset 字段）")
c = collections.defaultdict(lambda: collections.Counter()); fileset = collections.defaultdict(set)
for f in sorted(glob.glob(f"{R}/**/*.json", recursive=True)):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d, dict) or d.get("dataset") not in ("swe_bench", "swe_bench_pro"): continue
    for arm, v in (d.get("results") or {}).items():
        for r in (v.get("details") or []):
            e = c[d["dataset"]]; e["rows"] += 1
            md = r.get("task_metadata") if isinstance(r.get("task_metadata"), dict) else {}
            if not str(md.get("instance_code") or "").strip(): e["no_instance_code"] += 1
            if "detection_rate" not in r: e["no_detkey"] += 1
            if r.get("passed") is True: e["passed"] += 1
            e["err_" + str(r.get("error_category"))] += 1
            fileset[d["dataset"]].add(f)
for ds in ("swe_bench", "swe_bench_pro"):
    e = c[ds]
    print(f"  [{ds}] rows={e['rows']} no_instance_code={e['no_instance_code']} no_detection_key={e['no_detkey']} passed=True={e['passed']} files={len(fileset[ds])}")
print("  合计 rows=%d  artifacts=%d" % (sum(e['rows'] for e in c.values()), len(fileset['swe_bench'] | fileset['swe_bench_pro'])))

print("\n### 6. 伪重复：按 task_id 对齐 vs 按行序（positional）")
F8 = ["detection_rate","repair_rate","passed","generated_test","detection_first_status","specificity_gate_verdict","stop_reason","patch"]
for a, b, tag in (("benchmark_synthetic_20261007_161053.json","benchmark_synthetic_20261007_181638.json","seed42"),
                  ("benchmark_synthetic_20261007_170147.json","benchmark_synthetic_20261007_185941.json","seed44")):
    da = json.load(open(f"{R}/main_batch/{a}")); db = json.load(open(f"{R}/main_batch/{b}"))
    print(f"  [{tag}] seeds {da.get('seed')}/{db.get('seed')}")
    tot_al = tot_pos = 0
    for arm in ARMS:
        la, lb = da["results"][arm]["details"], db["results"][arm]["details"]
        mb = {x["task_id"]: x for x in lb}
        al = sum(1 for x in la if all(x.get(k) == mb[x["task_id"]].get(k) for k in F8))
        pos = sum(1 for x, y in zip(la, lb) if all(x.get(k) == y.get(k) for k in F8))
        order = sum(1 for x, y in zip(la, lb) if x["task_id"] == y["task_id"])
        tot_al += al; tot_pos += pos
        print(f"     {arm:12} task_id对齐={al}/87  行序对齐={pos}/87  同位置同task={order}/87")
    print(f"     合计: task_id 对齐 {tot_al}/261 ; 行序对齐 {tot_pos}/261")

print("\n### 7. QuixBugs")
for name, arm in (("aitester.json","aitester"), ("plain_llm_df.json","plain_llm_df")):
    rs = json.load(open(f"{R}/e6_a1_batches/e4_quixbugs_FIXED_harness/{name}"))["results"][arm]["details"]
    det = [r.get("detection_rate") for r in rs]; rep = [r.get("repair_rate") for r in rs]
    dm = [x for x in det if x is not None]; rm = [x for x in rep if x is not None]
    print(f"  [{arm}] rows={len(rs)} det=1:{sum(1 for x in dm if x==1.0)}/{len(dm)} repair=1:{sum(1 for x in rm if x==1.0)}/{len(rm)} "
          f"iters={dict(collections.Counter(r.get('iterations') for r in rs))} patch_nonempty={sum(1 for r in rs if (r.get('patch') or '').strip())} "
          f"plausible0&correct1={sum(1 for r in rs if r.get('patch_plausible')==0 and r.get('patch_correct')==1)} "
          f"stop={dict(collections.Counter(str(r.get('stop_reason')) for r in rs))}")

print("\n### 8. oracle_type 全库普查")
tot = collections.Counter(); byarm = collections.Counter(); bench = collections.Counter()
for f in sorted(glob.glob(f"{R}/**/*.json", recursive=True)):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d, dict): continue
    for arm, v in (d.get("results") or {}).items():
        if not isinstance(v, dict): continue
        for r in (v.get("details") or []):
            if not isinstance(r, dict): continue
            k = "absent" if "oracle_type" not in r else str(r.get("oracle_type"))
            tot[k] += 1; byarm[(arm, k)] += 1
            if os.path.basename(f).startswith("benchmark_"): bench[(arm, k)] += 1
print("  全库按值:", dict(tot))
print("  全库 aitester:", {k: v for k, v in byarm.items() if k[0] == "aitester"})
print("  benchmark_*.json 子集 aitester:", {k: v for k, v in bench.items() if k[0] == "aitester"})
print("  非 generated_test 且键存在的行:", sum(v for k, v in tot.items() if k not in ("generated_test", "absent")))

print("\n### 9. 其他不变量")
rh = viol = n = 0
for f in sorted(glob.glob(f"{R}/**/*.json", recursive=True)):
    try: d = json.load(open(f))
    except Exception: continue
    if not isinstance(d, dict): continue
    for arm, v in (d.get("results") or {}).items():
        for r in (v.get("details") or []):
            if not isinstance(r, dict): continue
            n += 1
            if "repair_history" in r: rh += 1
            if r.get("patch_correct") == 1 and r.get("patch_plausible") == 0: viol += 1
print(f"  全库行数={n} repair_history 键={rh} patch_correct=1&plausible=0={viol}")
for k in ("spec_oracle_injected", "spec_oracle_verdict"):
    p = sum(1 for f in MAIN for arm in ARMS for r in rows_of(f, arm) if k in r)
    print(f"  7 批中 {k} 键存在行数={p}/1827")
print("\n### 10. 报告文件指纹")
h = hashlib.sha256(open("FINAL_REVIEW_2026-10-11.md","rb").read()).hexdigest()
print("  sha256(FINAL_REVIEW_2026-10-11.md) =", h, "size=", os.path.getsize("FINAL_REVIEW_2026-10-11.md"))
```

> 注：脚本内 `# ### 2` 段对 `all_green` 的"两版全绿"结论只依赖 `iterations/regeneration_count/test_regenerated_pass_unverified/red_seen` 四个字段；生成测试的 `assert` 计数与 `execution_trace` 详情由另一次 heredoc 命令取得（见 §1.2 第 16 行"复算命令"）。

### A.11 关键输出（本次实跑，逐字摘录）

```
### 1. 7 批 × 3 臂（文件数=7）
[aitester] rows=609 det=1:78/556 (14.0%) detNone=53 | all-rows 78/609=12.8% | repair=1:0 repair=0:556 repNone:53 | patch_nonempty:251 | passed=True:389 | patch_correct=1:0
[plain_llm] rows=609 det=1:10/609 (1.6%) detNone=0 | all-rows 10/609=1.6% | repair=1:0 repair=0:609 repNone:0 | patch_nonempty:0 | passed=True:535 | patch_correct=1:0
[plain_llm_df] rows=609 det=1:279/571 (48.9%) detNone=38 | all-rows 279/609=45.8% | repair=1:0 repair=0:571 repNone:38 | patch_nonempty:0 | passed=True:15 | patch_correct=1:0

### 2. aitester(detection_first_status / iterations / patch / det)
  all_green_unverified   n=296 (48.6%) iters={0: 296} patch_nonempty=0 det1=0 det0=296
  red_not_repaired       n=167 (27.4%) iters={2: 132, 3: 35} patch_nonempty=158 det1=19 det0=148
  red_then_green         n= 93 (15.3%) iters={1: 76, 3: 2, 2: 15} patch_nonempty=93 det1=59 det0=34
  None                   n= 53 (8.7%) iters={0: 53} patch_nonempty=0 det1=0 det0=0
  all_green 不变式: iterations全0=True patch全None/空=True det全0=True passed全True=True red_seen全False=True regeneration_count={1: 296} test_regenerated_pass_unverified全True=True execution_trace非空=296/296 test_error_rate全0=True
  df all_green_unverified=15/609

### 3. red_seen / 转化率 / 反事实分解
  aitester red_seen=260/609=42.7%  df red_seen=556/609=91.3%
  转化率 aitester=78/260=30.0%  df=279/556=50.2%
  aitester-base 3 项分解: 产红率=+88.8 (44.2%) 转化率=+52.5 (26.1%) 交互=+59.7 (29.7%) 合计=201.0/201
  df-base 3 项分解      : 产红率=+148.5 (73.9%) 转化率=+112.2 (55.8%) 交互=-59.7 (-29.7%)
  单对齐新值: 产红率对齐 -> 166.8 行; 转化率对齐 -> 130.5 行

### 4. 门 verdict × detection_rate（3 臂）
  键存在行数=1044 / 总行数=1827 {('None', 0.0): 522, ('specific_red', 1.0): 206, ('None', None): 70, ('over_red', 0.0): 244, ('None', 1.0): 2}
  verdict=非 None 的行数: 450
  含非 None verdict 的批次: 4 ['007_161053', '007_170147', '007_181638', '007_185941']
  detection=1 但 red_seen≠True 的行: [('benchmark_synthetic_20261006_140906.json', 'plain_llm', 'synthetic__task_0002'), ('benchmark_synthetic_20261007_161053.json', 'plain_llm', 'synthetic__task_0002'), ('benchmark_synthetic_20261007_181638.json', 'plain_llm', 'synthetic__task_0002')]

### 5. SWE 普查（按工件顶层 dataset 字段）
  [swe_bench] rows=293 no_instance_code=293 no_detection_key=293 passed=True=4 files=11
  [swe_bench_pro] rows=72 no_instance_code=72 no_detection_key=72 passed=True=0 files=12
  合计 rows=365  artifacts=23

### 6. 伪重复：按 task_id 对齐 vs 按行序（positional）
  [seed42] seeds 42/42
     aitester     task_id对齐=78/87  行序对齐=45/87  同位置同task=49/87
     plain_llm    task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     plain_llm_df task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     合计: task_id 对齐 252/261 ; 行序对齐 143/261
  [seed44] seeds 44/44
     aitester     task_id对齐=75/87  行序对齐=42/87  同位置同task=49/87
     plain_llm    task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     plain_llm_df task_id对齐=87/87  行序对齐=49/87  同位置同task=49/87
     合计: task_id 对齐 249/261 ; 行序对齐 140/261

### 7. QuixBugs
  [aitester] rows=50 det=1:17/37 repair=1:37/40 iters={2: 26, 1: 10, 3: 14} patch_nonempty=50 plausible0&correct1=13 stop={'skip_debugger_repair_invalid': 24, 'test_passed': 13, 'max_iterations': 13}
  [plain_llm_df] rows=50 det=1:31/37 repair=1:0/41 iters={0: 50} patch_nonempty=0 plausible0&correct1=0 stop={'unknown': 50}

### 8. oracle_type 全库普查
  全库按值: {'generated_test': 3968, 'absent': 3185}
  全库 aitester: {('aitester', 'generated_test'): 2015, ('aitester', 'absent'): 1788}
  benchmark_*.json 子集 aitester: {('aitester', 'generated_test'): 1803, ('aitester', 'absent'): 1672}
  非 generated_test 且键存在的行: 0

### 9. 其他不变量
  全库行数=7153 repair_history 键=0 patch_correct=1&plausible=0=129
  7 批中 spec_oracle_injected 键存在行数=0/1827
  7 批中 spec_oracle_verdict 键存在行数=0/1827

### 10. 报告文件指纹
  sha256(FINAL_REVIEW_2026-10-11.md) = f19b196c11cf9f2ffb5b86eec2b40a2d40063062b1c96a3438a38bf3f42aaaa1 size= 139491
```

---

### E·附录 B：本文件此前内容的保留（Lead 于 10:44:47 写入的自查稿，原文照录）

> **保留原因**：本次验证开始时该路径已存在一份 Lead 自查稿（68 行），其声明"报告中被抽查的核心数字 15/15 逐条复算一致"。本 T-E 记录在 §1/§3 中对其中 **#10、#12、#15** 三条给出了不同结论（见 S1/S2/S3）。为不丢失前稿信息，原文照录如下（**其结论以本记录 §3 的修正为准**）。

```markdown
# T-E 对抗式验证记录（对 FINAL_REVIEW_2026-10-11.md 的独立复核）

- 验证执行者：Lead（final 阶段自查；原委派的独立验证 subagent 未产出文件，故由 Lead 完成并如实标注来源）
- 验证时间：2026-10-11（Asia/Shanghai）
- 验证方式：**零 LLM**、只读解析 `experiments/results/**` + `curl` 机读元数据端点
- 纪律：本节只记录**实际执行的命令与观察到的输出**；发现报告有错时如实记录并已就地更正

---

## 1. 逐条复算（报告 §3.3 / §3.4 / §3.5 / §3.7 / §3.8）

| # | 报告值 | 本次复算值 | 判定 | 复算方式 |
|---|---|---|---|---|
| 1 | aitester detection **78/556 = 14.0%** | **78 / 556 = 14.029%** | ✅ 一致 | 解析 7 批 `benchmark_synthetic_2026100[67]_*.json`，`detection_rate==1.0` 计数 ÷ `detection_rate is not None` 计数 |
| 2 | df detection **279/571 = 48.9%** | **279 / 571 = 48.862%** | ✅ 一致 | 同上 |
| 3 | plain_llm detection **10/609 = 1.6%** | **10 / 609 = 1.642%** | ✅ 一致 | 同上 |
| 4 | 三臂 `repair_rate==1.0` 全为 0 | **aitester 0 / plain_llm 0 / df 0** | ✅ 一致 | 同上 |
| 5 | 可测行 556 / 609 / 571 | **556 / 609 / 571** | ✅ 一致 | 同上 |
| 6 | `all_green_unverified` = **296**，全部 `iterations==0` 且 patch 为空 | **296（it0=296 / nopatch=296）** | ✅ 一致 | `detection_first_status` 分组 + `iterations` + `patch.strip()` |
| 7 | `red_not_repaired` 167 / `red_then_green` 93（det=1 为 59）/ `None` 53 | **167 / 93（59） / 53** | ✅ 一致 | 同上 |
| 8 | red_seen：aitester **260/609 = 42.7%**、df **556/609 = 91.3%** | **260（42.7%） / 556（91.3%）** | ✅ 一致 | `detection_first_red_seen is True` |
| 9 | 条件转化率 78/260=**30.0%** vs 279/556=**50.2%** | **30.0% / 50.2%** | ✅ 一致 | 同上 |
| 10 | 门 × 检出交叉表：`specific_red→1.0` **206**、`over_red→0.0` **244**、例外 **2** | `{('specific_red',1.0):206, ('over_red',0.0):244, (None,0.0):522, (None,None):70, (None,1.0):2}` | ✅ 一致 | 仅对**键存在**的行统计（区分 `k in r` 与 `r.get(k)`） |
| 11 | 真实仓库基准 **365 行**（swe_bench 293 + pro 72），100% 无 `instance_code`、100% 无 `detection_rate` | **293 + 72 = 365；instance_code 空 365/365；无 detection 键 365/365** | ✅ 一致 | 遍历全部 `experiments/results/**/*.json`，按 `dataset` 过滤 |
| 12 | 伪重复：seed42 对 **143/261**、seed44 对 **140/261** 行核心字段逐值相同 | **143 / 261、140 / 261** | ✅ 一致 | 比较字段 `detection_rate/repair_rate/passed/generated_test/detection_first_status/specificity_gate_verdict/stop_reason/patch` |
| 13 | QuixBugs：detection **17/37**、repair **37/40**、df detection **31/37**、df `iterations` 全 0 且 patch 全空 | **17/37、37/40、31/37、iterations 全 0、patch 非空 0/50** | ✅ 一致 | 解析 `e4_quixbugs_FIXED_harness/{aitester,plain_llm_df}.json` |
| 14 | QuixBugs 13 行 `plausible=0 ∧ correct=1` | **13 行**（`stop_reason=skip_debugger_repair_invalid`、`iterations=2`） | ✅ 一致 | 分组计数 |
| 15 | 全库 `oracle_type` 无任何 enhanced/spec oracle | **`generated_test` 1,803（aitester）/ `None` 1,672；无 `enhanced_generated_test`** | ✅ 一致 | 全库扫描 |

## 2. 发现并已更正的报告错误

| # | 位置 | 初稿表述 | 实际问题 | 更正后 |
|---|---|---|---|---|
| **E-1** | §0.2 K1 与 §3.4.2 | "反事实分解：对齐产红率可补 **88%** 缺口，对齐转化率仅补 12%" | **算错**：把"主效应占比"误算为"缺口占比"。实测缺口 = 201 行；产红率主效应 = (0.913−0.427)×0.300×609 = **+88.8（44.2%）**；转化率主效应 = 0.427×(0.502−0.300)×609 = **+52.5（26.1%）**；交互 = **59.7（29.7%）** | 已改为 44.2% / 26.1% / 29.7%，并加"口径更正"注记 |
| **E-2** | §3.4.2 结论 | 隐含"转化率不重要" | 由 E-1 连带修正：**产红率是最大单一因子，但转化率 + 交互合计 55.8%**，两类问题都必须修 | 已改为"两因子均必要"，并回写 §6 路径优先级说明 |

## 3. 引用抽查（直接访问机读端点）

| 引用 | 端点 | HTTP | 观察到的标题/容器 | 与报告一致？ |
|---|---|---|---|---|
| 10.1145/3803418（CANDOR） | `api.crossref.org` | **200** | *Hallucination to Consensus: Multi-Agent LLMs for End-to-End…* / **ACM Transactions on Software Engineering and Methodology** | ✅ |
| 10.1145/3803437.3806428（TestAgent） | 同上 | **200** | *TestAgent: A Multi-Agent LLM Framework for Repository-Level…* / *Proceedings of the 34th ACM…*（FSE Companion '26） | ✅ |
| 10.1109/icst69053.2026.00040（Konstantinou/ICST） | 同上 | **200** | *How well LLM-based test generation techniques perform with newer…* / **2026 IEEE International Conference on…** | ✅ |
| 10.1145/3832122（AdverTest） | 同上 | **200** | *Test vs Mutant: Adversarial LLM Agents for Robust Unit Tes…* / *Proceedings of the ACM on So…* | ✅ |
| 10.1145/3832093（Zhao/Zhou/Cohen） | 同上 | **200** | *Do Coverage and Mutation Scores of LLM-Generated Test Suit…* / *Proceedings of the ACM on So…* | ✅ |
| arXiv:2609.09315 | `export.arxiv.org/api` | **200** | *How effective are traditional test criteria at detecting b…*（entries=1） | ✅ |
| arXiv:2609.17394 | `arxiv.org/abs`（评审早期直接抓取） | **200** | *Coding Agents Have Converged…* | ✅ |
| arXiv:2602.08146 | `arxiv.org/html`（评审早期直接抓取） | **200** | *Test vs Mutant: Adversarial LLM Agents…* | ✅ |
| arXiv:2601.09695 | `arxiv.org/abs`（评审早期直接抓取） | **200** | *How well LLM-based test generation techniques perform with newer LLM versions?* | ✅ |

> **注**：`10.1109/icst69053.2026.00040` 的 Crossref 容器标题为 IEEE 会议论文集；项目文档未标该 DOI，本报告 §16 [4] 已补。

## 4. 未能验证 / 保留不确定

| 项 | 原因 |
|---|---|
| 覆盖率 89% / 83% 与逐模块覆盖 | 仓库根 `.coverage` 仅含 1 个被测文件，需全量 `--cov=src` 重跑（本次未跑） |
| `slim_environment: 1863` | 需卸载可选依赖的独立环境 |
| v1 口径 35.86% / 48.11% | 已被 v2 取代的历史值，未独立重放 |
| "无缓存理论成本" | 需关闭缓存重跑（成本高） |
| 项目 `patch_plausible` 的历史真实值 | `repair_history` 全库 0 次落盘，**不可复核**（这本身是报告结论之一） |
| `instance_code` 物化失败的上游原因 | 需 SWE-bench 数据集 + HF 访问（本环境缺） |

## 5. 验证结论

**报告中被抽查的核心数字 15/15 逐条复算一致；引用抽查 9/9 端点可用且标题与报告一致；发现并已更正的实质错误 1 处（E-1 反事实分解口径），连带修正 1 处（E-2）。**

**残余风险**：本验证由 Lead 自查完成（原独立验证 subagent 未产出），因此**不构成完全的第三方独立复核**；建议在正式投稿前，由未参与本项目的人员按本文件 §1 的命令做一次外部复算。
```

---

### 附录 B 备注（本记录对前稿三条"✅"的修正）

| 前稿行 | 前稿判定 | 本记录结论 | 依据 |
|---|---|---|---|
| #10 | ✅ 一致（把"2 行"当作门的例外） | ⚠️ 数值一致、**定性错误**：那 2 行是"门未运行"的行，且 `detection_rate=1.0` 与同行 `passed=True/red_seen=False/iterations=0` 自相矛盾；"全量"只覆盖 450 行/4 批 | A.4 |
| #12 | ✅ 一致（143/261、140/261） | ❌ **比较对齐方式无效**：按 `task_id` 对齐为 **252/261、249/261** | A.6 |
| #15 | ✅ 一致（1,803/1,672 记作"全库"） | ❌ **口径标注错误**：1,803/1,672 是 `benchmark_*.json` 子集；全库 aitester 为 2,015/1,788，全臂 3,968/3,185；且 1,672 是"键缺失"而非"值为 None" | A.8 |

> 以上三条**不改变**前稿的核心结论（三臂数字一致、引用真实、E-1 已更正），但"15/15 逐条一致"的表述应修正为"**12/15 逐条一致，3 条口径/对齐方式需修正**"。



---

## 附录 F｜Lead 独立重放验证（repair 修正口径）

> 源文件：`audit_2026/lead_replay_seed_a.md`（本附录为该文件的完整内容，仅调整标题层级与编号）

### F·repair=0 围栏伪影存量重放报告（ADR-0021，批次 VII）

- 重放目录：`experiments/results/main_batch/benchmark_synthetic_20261006_140906.json`（1 个批次文件）
- 臂：`aitester`
- 修正口径：normalize_patch_text 清理后整文件补丁 × gold test_cases（pytest rc==0 → correct）；
  原口径：结果行 patch_correct（历史伪影数字，未经清理执行）。

| 批次文件 | 带补丁行 | 可重放 | 修正 correct | 修正 repair_rate | 原 correct（伪影） |
|---|---|---|---|---|---|
| benchmark_synthetic_20261006_140906.json | 87 | 54 | 20 | 0.3704 | 0 |

**合计**：可重放 54 行，修正 correct = 20（修正 repair_rate = 0.3704）；原口径 correct = 0（伪影归零）；diff 形态不可重放 0 行、无 gold 材料 33 行、执行异常 0 行（不计入分母）。

> 解读：原口径 repair=0 由 patch 字段围栏残留（'python\n' 前缀）的测量伪影贡献；修正口径 = 与写盘链路同口径清理后的 gold 独立裁决。历史批次的repair / false_fix / CPR 分母应按本报告重估（ADR-0021 勘误注记）。



---

## 附：交付文件清单与规模

| 文件 | 角色 | 行数 |
|---|---|---|
| `EXTERNAL_REVIEW_2026-10-11.md` | **本文件**（外部评审版，自包含） | 2,894 |
| `FINAL_REVIEW_2026-10-11.md` | 主报告（不含附录） | 1,071 |
| `audit_2026/T_A_claims_traceability.md` | 附录 A 源 | 424 |
| `audit_2026/T_B_code_domain_audit.md` | 附录 B 源 | 366 |
| `audit_2026/T_C_frontier_primary_sources.md` | 附录 C 源 | 311 |
| `audit_2026/T_D_citation_verification.md` | 附录 D 源 | 482 |
| `audit_2026/T_E_adversarial_verification.md` | 附录 E 源 | 68 |
| `audit_2026/lead_replay_seed_a.md` | 附录 F 源 | 14 |
| `audit_2026/a*.py`（19 个） | 审计临时脚本（被附录 A 引用，供复算） | — |

**重建本文件**：`.venv/bin/python build_external_review.py`（幂等，可重跑）。

**工作树完整性声明**：本次评审**未修改项目任何源码、配置、测试或既有文档**；
新增内容仅为本报告、附录源文件与 `build_external_review.py`。
工作树中 33 个已修改文件与全部未跟踪项**均早于本次会话**（最新 mtime 2026-10-10 23:32）。

