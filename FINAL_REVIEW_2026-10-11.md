# AITester 独立评审报告（2026-10-11）

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
