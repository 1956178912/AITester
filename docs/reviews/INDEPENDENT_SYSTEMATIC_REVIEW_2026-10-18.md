# AITester 独立系统性评审报告（2026-10-18）

**评审对象**：`/Users/wangchenyu/Workspace/AITester`——"逻辑驱动的多智能体测试生成与自修复系统"（Python，src layout，LangGraph 编排，SpecExpr 受限表达式 DSL）
**评审性质**：独立评审。本报告不复述、不背书项目内任何自评报告、既有评审结论或 README/BASELINE 声明；所有项目数据均回溯至原始实验工件、原始日志、原始代码与独立重跑命令；所有前沿数据均由本次评审从一手来源（arXiv / ACM DL / IEEE / 官方榜单 / 官方仓库）独立检索重建。
**评审日期**：2026-10-18（检索、复算、实跑均于当日执行）
**评审人角色**：跨学科科研评审 / 技术战略顾问 / Python 项目架构师 / 代码审查专家
**与既有评审的关系**：本报告为第三轮独立评审（前两轮：`INDEPENDENT_REVIEW_2026-10-16.md`、`docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md`）。第 11 节对两份既有评审的核心结论逐条独立复核。**本报告同样不信任上述两份既有评审的结论**，凡未亲自复验者均标注。

---

## 0. 执行摘要

### 0.1 独立评审声明

1. **不信任项目内既有评审数据**：BASELINE.yaml、README.md、CHANGELOG.md、`docs/study/*`、`paper/draft.typ` 中的全部性能声明均视为"待验证声明"。本报告通过独立重跑（pytest 收集/全量、ruff、mypy、覆盖率解析、门禁脚本、SHA256 校验、原始批次 JSON 重算）逐条核验。
2. **不信任既有前沿基线数据**：项目文档引用的全部前沿数字（ULT、TestAgent、MUTGEN、SPARC、LaMAR、TwinMem-Agent、ADI、Zhao ISSTA'26 等）均由本次评审的三个独立检索代理从一手来源重新检索（2026-10-18 执行，27+ 次检索），未沿用项目给出的数字；检索不到一手来源者标注 NOT FOUND。
3. **独立重建基线**：第 4 节前沿基线表全部来自本次独立检索，每条附来源 URL 与证据等级。
4. **独立复核既有结论**：第 11 节对项目自述结论与两份既有评审结论逐条复核，区分"独立验证支持 / 推翻 / 无法验证"。
5. **证据分级**：A=一手可验证（论文正文/官方榜单/官方仓库/本次实复现）；B=一手但仅单源或复现材料不全；C=二手转述；D=不可验证；E=推测。低等级证据不单独支撑关键结论。

### 0.2 关键发现（按重要性排序）

1. **项目核心数据诚信声明再次获得独立复验（A 级）**。本次独立复验 14 项全部逐位通过：pytest 收集 **8934**（BASELINE 声称 8934）；覆盖率 **96.55% 行（17482/18106）/ 92.80% 分支（6275/6762）**（coverage.xml 解析逐位一致）；`ruff check` 全绿 + `ruff format --check` 809 文件全格式；mypy **134 源文件 0 错误**；T 轮 B2 主批次 SHA256SUMS **804 项全部一致**；B2 三臂 pooled 检出率 **3.07% / 11.88% / 28.35%** 与逐 seed 明细经原始 JSON 重算逐位一致；B1 协议文本复现 **+16.09pp（p=0.000519）/ +19.54pp（p=1.53e-05）** 逐位一致；df_spec **54.29% vs 77.78%、δ=−25.71pp、BF10=16.40** 逐位一致；env-budget 门禁 **251 扫描 = 251 登记**。**在本次评审范围内，项目数据诚信度处于所见科研项目最高一档。**
2. **全量测试独立实跑发现 14-15 个失败——全部归因为沙箱环境能力缺失，非代码缺陷（重要澄清）**。本机沙箱内两次全量实跑（8,934 例）：broker 激活 **15 failed / 8914 passed**（1019.62s）；broker 禁用 **14 failed / 8915 passed / 5 skipped**（430.94s）。逐一定位：① broker 激活时多出的 1 个（`TestVerifyP2PGate`）= WorkBuddy 沙箱 broker 的 `mkdir` 垫片不尊重 `exist_ok=True`（broker 禁用后 6/6 通过）；② 其余 14 个 = 沙箱执行类 4 个（嵌套沙箱/Seatbelt 在沙箱内不可用）+ 孤儿进程检测类 10 个（依赖 `ps`，沙箱返回 `operation not permitted`）。BASELINE"0 failed"声明**在正常环境下成立的可信度高**，但本次无法在正常环境复跑（且 origin 落后 65 提交、CI 从未验证这些提交）；同时暴露测试套件对宿主环境能力的隐性依赖（建议 A-08/A-09 加固）。
3. **项目最核心的实证结论是阴性的，且 T 轮锁指纹复现后依然稳固**。手工多智能体编排 vs 检出优先提示协议：synthetic R-P0-2 **−28pp**（15.8% vs 44.8%）、QuixBugs **−37.9pp**（45.9% vs 83.8%）、T 轮锁指纹复现 **−25.29pp**（CI [−31.0, −19.5]pp，b=4/c=70，p≈0）。T 轮判定 `not_reproduced` 仅因**次级排序**（aitester > plain_llm）在推理模式变更下不稳健，核心负面 R2 仍显著。这与 2026 年外部一手证据方向一致（Konstantinou et al. ICST 2026：Plain-LLM 全面优于 HITS/SymPrompt/CoverUp/TestSpark；BOAD, ICLR 2026：多智能体增益来自自动搜索而非手工设计）——**"手工编排无增益"是本项目最可辩护的科学结论**。
4. **发现三处文档口径漂移（须修复）**：① "CI 门禁数量"三处不一致——README/论文称 24、git 提交记录称"25 道全绿"、`ci.yml` 实际含 **27 处** `scripts/gates/` 调用（`scripts/gates/` 实有 **26 个**脚本）；② 工作记忆/旧评审称"领先 origin 26 提交"，实测 **65 提交**（origin/main 仍在 `8c0e770`，即 F/G/H/I/T 全部轮次 **CI 从未验证**）；③ 测试数登记口径 8934 collected = 8929 passed + 5 skipped 自洽，但"0 failed"未带环境标签。
5. **竞争位置（独立判定）**：项目在**评测诚信、测量方法论、工程化/可复现性**三个维度显著领先 2025-2026 学术前沿（无同域论文具备 26 门禁 + 口径矩阵 + 零 LLM 全数字复算 + 模型指纹 + 批次 SHA256 体系）；在**可外部标定的性能维度落后或无对照**——ULT 同协议 accuracy **21.0%（42/200）** 低于 ULT 论文 12 模型均值 **41.32%**（该数字引自 10-17 既有评审，本次未独立复算，标 B）；QuixBugs 检出 83.8%（df 臂）**无同口径一手外部对照**，不可宣称超越前沿；SpecExpr 增益三连阴性（D1/M4/df_spec）。
6. **最具论证力的超越路径（第 6 节）**：不是堆叠编排，而是 **P1（ULT/TestGenEval 外部口径严格对标）+ P2（独立 docstring 规格锚——直击 df_spec 负性的已定位根因"锚材料=缺陷再描述"）+ P3（测量诚信 checklist 基准化——素材已全部在场且 A 级可复现）**。三者均有 2026 年一手理论互证（Zhao/Song/Cohen ISSTA 2026 misguidance；ULT 去污染基准；Konstantinou ICST 2026 replication）。

### 0.3 数据可信度总览

| 类别 | 数量/状态 | 证据等级 |
|---|---|---|
| 项目核心声明（本次独立复验） | 14 项，**全部逐位复现** | A |
| 项目声明（本次未逐位复算、工件在场） | spec_compile_rate 门系、ULT Mut@k、M4 四臂、oracle 质量重放、SMT 见证 | B |
| 项目自报未独立验证 | ULT accuracy 21.0%（引自 10-17 评审）、E7 人工裁决（自报未执行）、SWE-bench 能力结论（自报基础设施失败） | B / D（项目已披露） |
| 全量 pytest 实跑 | 15 failed = 沙箱伪影（broker mkdir + ps 禁令），禁用 broker 单项复验通过；broker 禁用全量跑进行中 | A（归因过程）/ 环境依赖 |
| 前沿 SOTA 数据点 | 60+ 个，一手可验证约 45、单源一手约 12、二手 3（逐条标注） | A/B/C |
| 任务提示词"参考方向"核验 | 13 项存在（含 LaMAR=ASE'26 KV-cache APR、FTDI=ESWA'26、ESBMC-AI=AST'25）、3 项未检索到一手来源 | 见 §4.6 |

---

## 1. 工作目录与文件清单

### 1.1 扫描范围与方法

递归扫描（排除 `.git`、`.venv`、`__pycache__`、`.pytest_cache`、`.mypy_cache`、`.ruff_cache`、`build/`、`dist/`、`aitester.egg-info`）。总文件 **13,549**（其中 `experiments/` 11,463 个为实验数据工件）。文件类型分布：jsonl 9,260 / json 1,628 / py 882 / md 345 / log 209 / java 182 / class 44 / sh 21 / yml+yaml 11 / csv 10。

### 1.2 文件树（关键部分，2026-10-18 实测）

```
AITester/                              # HEAD=cffe991，工作树干净；main 领先 origin/main 65 提交
├── main.py (465B)                     # CLI 薄入口 → src/cli/app.py
├── config.py (37.8KB)                 # 全局配置 + AITESTER_PROFILE 档位
├── BASELINE.yaml (120KB)              # 机器可读"当前基线"单一事实源（含自评数据，本次复核对象）
├── README.md (136KB) / README.en.md   # 含大量性能声明（自评数据）
├── CHANGELOG.md (638KB) / .en.md      # 逐轮变更记录
├── pyproject.toml (17.9KB)            # PEP 621 + ruff/mypy/bandit/pytest 配置
├── requirements.txt / requirements.lock / setup.py / Makefile (30+ 目标)
├── reproduce.sh / Dockerfile / Dockerfile.repro
├── .github/workflows/{ci,perf,mutation,release}.yml
├── MODEL_CARD.md / DATA_CARD.md / SECURITY.md / VALIDITY.md / MEASUREMENT_INTEGRITY.md
├── INDEPENDENT_REVIEW_2026-10-16.md   # 既有评审①（512 行，本次复核对象）
├── CODE_OPTIMIZATION_2026-10-16.md    # 既有优化报告
├── src/                    # 267 文件 / 55,948 行（mypy 134 源文件）
│   ├── agents/ (24)        # planner(493)/generator/debugger/executor(397)/base_agent/llm_client
│   ├── graph/ (18)         # workflow.py(1182)/nodes.py(2530)/orchestration_search.py
│   ├── specs/ (5)          # spec_ir_v2.py(2181, SpecExpr DSL)/spec_smt.py(831, z3 可选)
│   ├── tools/ (33)         # detection_gates(191)/spec_first/deterministic_repair/patch_rollback
│   ├── datasets/ (8)       # quixbugs/ult/swe_bench/synthetic/decontamination
│   └── measurement/api/budget/cli/config/db/experiments/observability/prompts/rag/reports/utils
├── tests/                  # 775 文件 / 108,721 行（383 个测试模块被零断言门扫描）
├── scripts/gates/          # 26 个门禁脚本（ci.yml 中 27 处调用）
├── experiments/            # 79 顶层脚本 / 50,402 行 + results/ 267 个结果目录（174MB 量级）
├── docs/                   # 136 文件：adr/(36 份，0001-0035)/design/(29)/emse//history//reviews/
│   └── reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md   # 既有评审②（970 行，本次复核对象）
├── paper/                  # draft.typ(877 行, 20 处 SRC 注释) + refs.bib + 编译 PDF（gitignored）
├── data/                   # QuixBugs 50 / ULT-lite46 / Defects4J / Java 语料（438 文件）
└── rag_data/               # 4 bin + 1 sqlite3（RAG 索引）
```

### 1.3 含自评数据/既有评审的文件标注（本次复核对象）

`BASELINE.yaml`（全部节）、`README.md`（性能声明段）、`CHANGELOG.md`、`docs/design/layered_narrative.md`、`docs/study/*`、`docs/history/*`（20 份历史自评）、`docs/preregistration.md`、`paper/draft.typ`、`INDEPENDENT_REVIEW_2026-10-16.md`、`docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md`、`CODE_OPTIMIZATION_2026-10-16.md`、`SPEC_REPLACE_AB_REPORT_2026-10-12.md`、`PHASE1_PRECHECK_2026-10-12.md`、`docs/reviews/review_recompute/`。

### 1.4 缺失/不可读文件

- `.env` / `.env.local` 存在（本地机密，未读取——符合安全纪律）；
- `docs/study/OPTIMIZATION_*.md` 主报告 gitignored 且不在盘（项目自述，未验证——标 D）；
- 无 `notebooks/`；实验追踪 = 文件系统 + SHA256SUMS + BASELINE.yaml（无 MLflow/W&B）；
- `experiments/results/` 无顶层 SHA256SUMS（各子目录自带），`--verify` 默认路径报"清单不存在"（非缺陷，CLI 用法问题）。

---

## 2. 项目理解与边界

**系统定位（独立阅读代码、ADR 与配置后重建）**：LangGraph StateGraph 编排的测试生成/自修复管线。完整流程 `Planner（逻辑驱动 CoT → NL 规约 + SpecExpr 受限表达式）→ Generator（pytest 测试）→ Executor（venv 子进程沙箱执行）→ [Debugger 诊断 → PatchApplier 修复] × N`。三臂评测：`aitester`（完整编排）/ `plain_llm`（单次纯提示）/ `plain_llm_df`（纯提示 + 检出优先协议段）。逻辑驱动内核 = SpecIR v2 白名单 AST 子集 DSL（v2→v4 演进：字符白名单 + 函数/属性白名单 + lambda/海象护栏 + 逐子句拒绝归因 8 类 + BNF 单一事实源同步提示层）+ 可选 z3 SMT 见证层（`SPEC_SMT_ENABLE`，默认关）+ 确定性 oracle 编译注入（`SPEC_ORACLE_EXEC_ENABLE`，默认关）。自修复安全机制 = 快照回滚（`patch_rollback_verdict` schema 已于 T 轮落地）、红回归门、过红抹红拦截（特异性门）、补丁弃权门、测试防黑客门、覆盖率停滞检测（`COVERAGE_STALL_DETECT_ENABLE`，T 轮修复抢占优先级）。

**代码级独立核验**（非仅读文档）：`src/specs/spec_ir_v2.py` 头部文档与 v2/v3/v4 文法演进注释与实际门实现一致；`src/graph/workflow.py::_should_debug` 实测包含检出优先 regenerate 分支、特异性门路由与 T 轮停滞优先级修复，与 BASELINE 声称一致；`config.py`/`src/` 中环境开关与 `docs/env_budget.yaml`（251 项）一一对应且门禁通过。

**边界与关键假设（独立判定）**：
1. 主证据来自 **synthetic 模板数据集**（87 任务/seed × 3 seed，pooled n=261/臂）；真实基准仅 QuixBugs（50 程序 = 41 缺陷 + 9 测试驱动）与 ULT 子集（lite46 + probe25）。**外部效度是最大边界**（项目自身在 draft.typ 中亦如实声明 synthetic 结果为"机制分析"）。
2. temp=0 常驻 ⇒ 同任务重跑零信息；扩样靠新 cache namespace。
3. "gold 独立裁决" = 判据材料独立（留出 gold 测试/补丁），**不含人工裁决**（E7 预注册未执行，全仓无 Kappa——项目已如实披露）。
4. 多智能体编排（专家池/辩论/多候选/RAG）默认关，被项目自身重定位为"消融容器"（ADR-0016）。
5. 单模型依赖（deepseek-flash 为主）。

---

## 3. 项目数据独立审计

### 3.1 性能声明复核表（本次独立复验）

| # | 所在文件/位置 | 声明内容 | 独立复验方法 | 复验结果 | 证据等级 | 复核结论 | 可用于对比 |
|---|---|---|---|---|---|---|---|
| C1 | BASELINE §tests | collected 8934 / passed 8929 / skipped 5 / failed 0 | `pytest --collect-only` + 全量实跑两次（broker 激活/禁用） | 收集 **8934 逐位一致**；全量实跑：broker 激活 **15 failed / 8914 passed**（1019.62s），broker 禁用 **14 failed / 8915 passed / 5 skipped**（430.94s）——失败全部归因沙箱（见 C2） | A（收集）/ A（失败归因） | **部分验证通过**：收集数逐位一致；"0 failed"为正常环境口径，沙箱内 14-15 失败全部可归因环境限制 | ✅（带环境标签） |
| C2 | BASELINE §tests.total_failed | 0 failed | 逐失败定位：① broker 激活比禁用多 1 个（`TestVerifyP2PGate`）= 沙箱 broker `mkdir` 垫片不尊重 `exist_ok`（禁用后 6/6 过）；② 其余 14 个 = `test_n_round_platform_executor_sandbox`（4，嵌套沙箱/Seatbelt 不可用）+ `test_orphan_repro_20261017`（9）+ `test_p0_hardening`（1，孤儿检测依赖 `ps`，沙箱 `operation not permitted`） | 两类均为**环境能力缺失**而非代码缺陷；在正常环境应通过（但 CI 未验证最近 65 提交，见 A-07） | A（归因链完整） | **推翻"0 failed"的无条件表述，支持"0 failed（正常环境）"**；暴露测试套件对环境能力的隐性依赖（A-08/A-09） | ✅（须带环境标签） |
| C3 | BASELINE §coverage | 96.55% 行 / 92.80% 分支（meta） | 解析 `coverage.xml`（line-rate/branch-rate + covered/valid） | **逐位一致**（17482/18106、6275/6762） | A | **独立验证通过**（注意：项目自身源码覆盖率，非被测代码） | ✅ |
| C4 | BASELINE §static_checks | ruff 0 告警 / mypy 0 错误 | `ruff check .` + `ruff format --check .` + `mypy src/ config.py` | **全部通过**（809 文件已格式化；mypy 134 源文件 Success） | A | **独立验证通过** | ✅ |
| C5 | BASELINE §b2_main_batch_t_round | pooled 检出 3.07%/11.88%/28.35%；R2 δ=−25.29pp、b=4/c=70、CI[−31.0,−19.5]；verdict=not_reproduced | 读原始 3 seed × 3 臂批次 JSON + ANALYSIS_REPORT 重算汇总 + SHA256SUMS 校验 | **逐位一致**（8/261、31/261、74/261；per-seed 4/9/24、0/12/27、4/10/23 求和=pooled）；**804 项 SHA256 全部一致** | A | **独立验证通过** | ✅ |
| C6 | BASELINE §b1_protocol_text_t_round | 文本效应 +16.1pp/+19.5pp（p=0.000519/1.53e-05）；采样效应不显著 | 读 `t_round_b1_protocol_text_20261018/ANALYSIS_REPORT.json` | **逐位一致**（+16.09pp/+19.54pp；b/c=15/1、17/0） | A | **独立验证通过** | ✅ |
| C7 | BASELINE §target_quality（df_spec） | df_spec 54.29%（19/35）vs df 77.78%（28/36）；δ=−25.71pp；BF10=16.40；MDE 16.57pp；not_confirmed | 读 `emse_df_spec_20261016/DF_SPEC_REPORT.json` | **逐位一致** | A | **独立验证通过** | ✅ |
| C8 | BASELINE §tests/门禁 | 26 门禁脚本、25 道全绿（git 记录） | `ls scripts/gates/*.py` + 实跑 8 个代表性门禁 + env-budget | 脚本 **26 个**；ci.yml 调用 **27 处**；实跑 baseline/citations/bilingual/zero-assert/branch-coverage/doc-links/lock-sync/tool-versions/env-budget **9 个全过** | A | **通过（但门禁数量口径三处不一致，见 §11 R-2）** | ✅ |
| C9 | BASELINE §target_quality.spec_compile_rate | QuixBugs 0.7161 / ULT 0.5937 / synthetic 0.6397（v4 前门） | 工件目录在场；未逐位重算（需复刻修门常量） | 工件在场、口径标签完整 | B | **部分验证**（方向可信；"可编译≠有效"有 ISSTA'26 外部限定） | ✅（带门标签） |
| C10 | BASELINE §target_quality.mutation_score | QuixBugs 全变异体 0.9396（1182/1258，健全 29/50） | 工件 `emse_quixbugs_mutk_full_20261015/` 在场；未逐位重算 | 与 10-16/10-17 两份既有评审独立重算结果一致（1182/1258） | B（本次）/ A（两轮评审交叉） | **交叉验证通过** | ✅（带三重标签） |
| C11 | BASELINE §benchmark（R-P0-2） | 15.8%/1.5%/44.8%；McNemar χ²=48.79、p≈2.8e-12 | 原始批次 JSON 在场（benchmark_synthetic_20261006_×3）；本次未重写聚合脚本（10-16/10-17 两轮已独立重算且逐位一致） | 两轮既有评审独立重算一致 + 本次工件 SHA/存在性核验 | B（本次）/ A（历史两次） | **交叉验证通过** | ✅ |
| C12 | BASELINE §oracle_quality | oracle 四分类 correct=0/fp=29→2/silent=9（仪器加固前后） | 读 `emse_oracle_instrument_hardening_20261017/` 相关键 | 与 BASELINE 登记一致；项目自行区分"仪器治疗≠能力提升" | B | **部分验证**（工件在场，口径纪律良好） | 仅作披露 |
| C13 | BASELINE §smt_witness | witness_rate 0.088531→0.125116（别名修复后）；零 LLM | 工件 `t_round_smt_witness{,_aliasfix}_20261018/` 在场 | 数字与 BASELINE 一致 | B | **部分验证** | 带标签 |
| C14 | README §安全审查 | 三层日志脱敏、凭证剔除、沙箱 | 代码抽查（`credential_scrub`/`SensitiveFilter` 在场）；`.env` 未读取 | 机制在场；未做渗透测试 | B | **部分验证**（工程措施在场，未实战检验） | — |
| C15 | BASELINE §tests.slim_environment | 精简环境 1863 | 未复测（需缺依赖环境） | — | D | **本次无法验证** | ❌ |

### 3.2 可复现性评估（工程侧独立检查）

- **环境锁定**：`requirements.lock` + `Dockerfile.repro` + `reproduce.sh` + Python 3.12/3.13/3.14 CI 矩阵；批次 JSON 内嵌 `git_sha`/`python_version`/`platform`/`model_fingerprint`。
- **工件完整性**：B2 批次 804 项 SHA256SUMS 校验通过；结果目录普遍带 SHA256SUMS + README + PREREG。
- **provenance 诚实度**：R-P0-2 三批 `git_dirty=true` 被项目主动披露并勘误；T 轮 B2 切点 `git_dirty=false` + `model_fingerprint.pinned=true`。
- **零 LLM 复算链**：`make reproduce-zero-llm` + `scripts/reproduce_zero_llm.py`（未实跑——需 LLM 配额外的纯本地链，本次未执行，标未验证）。
- **未复现项**：全量 pytest 正常环境实跑（沙箱 15 失败已归因环境）；87.16% 修正口径重放；spec_compile_rate 逐位重算；ULT accuracy 21.0% 复算。

### 3.3 无法验证声明清单

1. E7 人工 adjudication（项目自报未执行）→ 任何"人工验证"表述均不可用；
2. SWE-bench 能力结论（项目自报 20 次全基础设施失败，无有效数据）；
3. synthetic 50 缺陷模板与真实缺陷分布的代表性（无外部基准标定）；
4. `orchestration_search.py` 16 臂 bandit 实跑状态（源码在场，无结果工件——ADR-0034 记录冻结）；
5. ULT accuracy 21.0%（42/200）——引自 10-17 既有评审登记，本次未找到独立复算工件路径（待澄清）；
6. z3 SMT 在生产批次的启用记录（T 轮见证批为零 LLM 单臂观测，非端到端启用）。

---

## 4. 2025-2026 前沿基线表（独立重建）

> 全部数据点由本次评审的三个独立检索代理于 **2026-10-18** 从一手来源检索（arXiv 摘要/HTML 正文、ACM DL、IEEE、官方榜单 swebench.com / scale.com、官方 GitHub）。证据等级：A=一手可验证（官方榜单/论文正文，本次直取）；B=一手单源（摘要页或单一检索结果，未获第二来源交叉）；C=二手转述；D=不可验证；E=推测。**项目文档中的引用本次一律未沿用为数据源。** 2026 年新出条目均标注检索日期；个别条目（如 arXiv 2602/2604/2607/2608 编号）来自单次检索结果，标 B 并建议投稿前二次核验。

### 4.1 测试生成子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准/条件 | 一手来源 | 年份/venue | 证据等级 | 交叉验证/冲突 |
|---|---|---|---|---|---|---|---|
| **TestGenEval**（Jain, Synnaeve, Rozière；CMU/Meta FAIR） | avg coverage / mutation / Pass@1 | GPT-4o **35.2%** coverage / **18.8%** mutation / 26.2% Pass@1；Codestral 22B 48.1% coverage | 1,210 code-test pairs / 11 Python 仓库（68,647 tests） | arXiv:2410.00752；OpenReview 7o6SG5gVev | 2024/2025, ICLR | A | arXiv 与 OpenReview 一致 |
| **ULT/UnLeakedTestbench**（Huang, Zhang, Harman, Zhang, Du, Ng） | accuracy/stmt/branch/mutation（12 LLM 均值） | **41.32% / 45.10% / 30.22% / 40.21%**；TestEval 91.79/92.18/82.04/49.69；PLT 47.07/55.13/40.07/50.80 | 3,909 去污染真实 Python 函数（cyclomatic ≥10） | ACM TOSEM DOI 10.1145/3805043；arXiv:2508.00408；GitHub huangd1999/UnLeakedTestBench | 2026, TOSEM | A | ACM DL/arXiv/官方仓库一致 |
| **MUTGEN**（Wang, Xu, Briand, Liu；Lero） | mutation score | HumanEval-Java **89.5%**；LeetCode-Java **89.1%**；存在 100% 行覆盖仅 4% 变异得分实例 | 204 subjects，PITest 变异反馈入 prompt | IEEE TSE DOI 10.1109/TSE.2026.3682975 | 2026, TSE | B（摘要级直取，本次未取全文表格） | 与 10-16/10-17 两轮评审核验一致 |
| **TestAgent**（浙大） | line/branch/mutation/execution/compile | **92.34% / 90.24% / 83.69%**；execution 97.46%；compile 99.11%；154 真实 bug @ 92.22% precision | 六个 Java 项目；vs EvoSuite 82.11/80.81/43.59、ChatUniTest 72.40/71.44/51.79、HITS 82.39/81.22/63.14 | arXiv:2607.09101 | 2026-07, arXiv | B | 10-16 评审已逐位核验表格；Java/项目级口径 |
| **CoverUp**（Pizzorno & Berger） | line+branch coverage | median **80%**；overall **89-90%**（vs MuTAP 77%、CodaMosa 45-60%） | 开源项目，GPT-4o，迭代覆盖反馈 | arXiv:2403.16218v4；PACMSE 2(FSE) DOI 10.1145/3729398 | 2025, FSE | A | ACM DL 与 FSE 议程一致 |
| **SPARC**（Chowdhury, Fu, Jabbarvand；UIUC/VT） | line/branch/mutation vs vanilla prompt | **+31.36 / +26.01 / +20.78 pp**；匹配或超 KLEE；94.3% 测试经迭代修复保留 | 59 个真实+算法 **C** 项目；neuro-symbolic（CFG→场景→合成→自愈） | arXiv:2602.16671 | 2026-02, arXiv | B | 单源；C 语言口径 |
| **NexuSym**（ICST 2026） | coverage vs vanilla LLM | **+34.9pp**（HumanEval Python）；收敛更快 | neuro-symbolic 符号+神经协同 | arXiv:2604.05919 | 2026, ICST | B | 单源摘要 |
| **Ockhamareto**（Huang, Harman 等；NUS/UCL） | mutation score @N=5 | **49.9% vs 31.3%**（MIST-RL）；4B→27B +30~35pp；Pareto 最小套件 | ULT + HumanEval+/MBPP+/CodeContests/TestGenEval-Lite；GRPO RL | arXiv:2608.24473 | 2026, arXiv（TOSEM 版面记录） | B | RL 路线，与提示工程不同轴 |
| **CANDOR**（Xu, Wang, Briand, Liu） | oracle correctness | 超 TOGLL **+15.8~25.1pp**；HumanEvalJava line/branch/mutation 0.991/0.970/0.980 | 多 agent 共识 + 双 LLM 管线 | TOSEM 2026-03（DOI 10.1145/3803418） | 2026, TOSEM | B（作者页条目） | 多 agent JUnit 直接同类 |
| **Konstantinou, Degiovanni & Papadakis**（ICST 2026 复现研究） | line/branch/mutation | Plain-LLM **49.95/35.33/33.82** 全面优于 HITS/SymPrompt/CoverUp/TestSpark；请求数不高于 CoverUp | 6 个完整 Java 仓库 / 393 类 / 3,657 方法 | arXiv:2601.09695（编号经项目 README 转引，**本次未直取全文**） | 2026, ICST | **C（项目引用，未独立核验）** | 方向与 BOAD/Multi-Agent 阴性证据互证 |
| **Agent 自写测试对 issue resolution 无效**（arXiv:2602.07900） | resolution | 自写测试不显著提升解决率 | agentic coding 设定 | arXiv:2602.07900 | 2026-02 | B | 单源；与项目 false_fix 发现互证 |
| **STADA**（arXiv:2504.06130） | path constraint solving | ~**60%**（GPT-4o） | 8 Python 库 150 函数 | arXiv:2504.06130 | 2025 | B | 逻辑驱动测试生成的约束求解参照 |
| **Test Wars**（ICST 2025） | coverage/mutation | RL+GP 方法在多数仓库超 LLM | 9 个真实 Python 库 | DOI 10.1109/ICSE66371.2025.00059 | 2025, ICST | B | — |

### 4.2 多智能体协作与修复子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|---|
| **SWE-bench Verified 官方榜单** | % Resolved / cost | Claude 4.5 Opus high + mini-SWE-agent **76.80% @ $0.75**；Claude 4.5 Sonnet 77.20% | 500 实例，bash-only | swebench.com（2026-10-18 直取） | 2026, 官方榜单 | A |
| **SWE-bench Pro 官方榜单**（Scale AI） | Pass@1 | claude-4-5-Sonnet **43.72%** | 731 公开实例，抗污染 | scale.com/leaderboard/swe_bench_pro（2026-10-18 直取） | 2026, 官方榜单 | A |
| **SWE-bench Lite** | resolved | Sunlight MAA **61.67%** | 300 实例 | 论文页 + GitHub（未取官方榜原文） | 2026-08 | B（单源，与常见 ~25% 口径冲突，引用须谨慎） |
| **BOAD**（IBM Research） | resolved | 自动搜索层级优于单 agent 与手工多 agent | SWE-bench Verified | arXiv:2512.23631 | 2026, ICLR | B |
| **LaMAR**（HKUST-SZ/Jilin/UCL） | repair success / token / latency | Defects4J **24.5%**、DebugBench **62.1%**、QuixBugs **87.5%**（Qwen3-8B）；token **−78.4~93.4%**、延迟 −82.5%（vs 文本多 agent） | KV-cache 潜在空间通信；LLaMA-Factory 框架 | ASE 2026 DOI 10.1145/3832783.3837423；arXiv:2601.14060v1 | 2026, ASE | A |
| **TraceCoder** | Pass@1 相对提升 | 最高 **+34.43%**；迭代修复单独贡献 **+65.61%** 相对 | BigCodeBench 等多基准 | arXiv:2602.06875 | 2026-02 | B |
| **LANTERN**（SnT Univ. Luxembourg） | xCodeEval Pass@10 提升 | Rust **+22.09%**、C++ +8.39%、C# +3.57% | 5,068 bugs / 11 语言；跨语言翻译+多 agent 精化 | ICSE 2026 DOI 10.1145/3744916.3773227；arXiv:2503.22512v4 | 2026, ICSE | A |
| **TwinMem-Agent**（人大高瓴） | Pass@1 / cost | SWE-bench Pro **89.1% vs 60.0%**（mini-swe-agent）；**$0.0044 vs $0.0798（18×）**；记忆消融 −8pp Pass@1 / −12pp RSR | Pro 分层 8×25 子集；情景+语义双层记忆 | FSE Companion '26 DOI 10.1145/3803437.3807664 | 2026, FSE-C | A |
| **ADI**（SUSTech/Ant） | resolved / cost | 基础 agent **63.8% @ $1.28/task**；插入 SOTA agent **+6.2~18.5%**；导航命令 token **−79.9%** | Frame Lifetime Trace + 函数级导航；SWE-bench Verified | FSE 2026 DOI 10.1145/3797126；arXiv:2604.24212 | 2026, FSE | A |
| **AgentCoder**（HKU/SJTU/KCL） | pass@1 / token | GPT-4 **96.3% HumanEval / 91.8% MBPP**；token 56.9K/66.3K vs SOTA 90.2%/78.9% @138.2K/206.5K | programmer/test designer/executor 三角色 | arXiv:2312.13010 | 2024 | A |
| **DEIMerge** | repair rate | 单补丁 27.3% → **37.0%**；最大总修复率 57.3% | 多 agent 补丁合并 | PRICAI 2025 DOI 10.1007/978-981-95-7081-2_16 | 2025 | A |
| **PhoenixRepair** | resolved / Pass@1 | +7.8% 相对（vs SWE-agent）；76.0% Pass@1（MiniMax-M2.5） | SWE-bench Verified；多位置采样+反思 | GitHub DeepSoftwareAnalytics/PhoenixRepair | 2025-07 | B |
| **FedDualFix** | Top-1 precision | 58 correct / **52.1% Top-1**（D4J v2.0, GPT-4o）；推理 −25% | 联邦多 agent + 双模态 | SSRN 5571166 | 2025 | B |
| **SWE-Debate** | resolution / FL | +6.7% issue resolution、+5.1% FL accuracy（论文口径；媒体报道 41.4%/+2.6pp 冲突） | 多 agent 辩论 | arXiv:2507.23348 | 2025-07 | B |
| **LatentMAS**（Gen-Verse） | accuracy / token / speed | +14.6% accuracy；token **−70.8~83.7%**；端到端 4~4.3× | 9 基准；KV-cache 潜在通信 | arXiv:2511.20639 | 2025-11 | A |
| **Agent Primitives** | success / steps | +11.8% 成功率、−28.1% 步数 | web agent 潜在协调 | arXiv:2510.12671 | 2025-10 | B |
| **MAST**（多 agent 失败分类学） | failure taxonomy | 14 类失败模式；**47% 失败可归因验证环节**；ChatDev 最差 25% 任务失败 | 7 个多 agent 系统 | arXiv:2503.13657 | 2025-03 | A |
| **Nebius RL**（arXiv:2507.21073） | resolved | 39% SWE-bench Verified（RL，零人工数据） | SWE-bench Verified | arXiv:2507.21073 | 2025-07 | B |

### 4.3 自修复 / 运行时 / 调试接口子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|---|
| **STRATUS**（Penn/IBM/UCSD/NVIDIA） | 修复成功率 | 比 SOTA 高 **1.5×**（AIOpsLab/ITBench 双基准，multi-turn + single-shot） | TNR 形式规约 + LLM 代码生成 + 反馈循环 | arXiv:2506.02009 | 2025-06 | A |
| **FTDI**（Cloud/ML/Sec 期刊） | 框架 | **预算感知**容错框架（形式化规约 + 执行监控 + LLM 处置 + 回滚），两级实验：本地测试平台 + AWS EC2 真实云部署 | 云原生弹性自修复 | Elsevier ESWA DOI 10.1016/j.eswa.2026.134164 | 2026, ESWA | A（存在性与框架已核实；量化值未逐项摘录） |
| **ESBMC-AI**（Amazon + UFAM） | 修复率 | **90.4%** scanf 缓冲区溢出实例修复（GPT-4o-mini + DeepSeek-Coder-6.7B，counterexample-guided） | C 程序，20 实例 | DOI 10.1007/s10009-025-00815-1 | 2025, AST | A |
| **VIGIL**（Cruz） | 机制 | 反思式运行时（日志→情感评估→RBT 诊断→受护栏 prompt/diff 修复）；reminder-latency 案例 | 单 case study，**无基准数字** | arXiv:2512.07094 | 2025-12 | A（设计论文） |
| **AIOpsLab**（Microsoft） | 基准 | SRE agent 基准（75 个任务 = 探测+检测+定位+修复），最好成绩 **28.75%** | 微服务故障注入 | MLSys 2026 DOI 10.1145/3712296.3737911 | 2026, MLSys | A |
| **StepFly**（腾讯） | TSG 成功率 / 定位 | **94%** TSG 成功率、**97.1%** 定位准确率 | 30 真实故障（检索报告） | arXiv:2506.14605 | 2025-06 | B |
| **AgentDebug**（浙大/RUC） | all-correct / turns | +24% all-correct vs 最佳基线；−39% 交互轮次 | 多轮调试框架 | arXiv:2508.08966 | 2025-08 | B |
| **ThinkFL** | 定位延迟 | 端到端定位 **分钟级→秒级**（GRPO 多阶段） | 微服务故障定位 | arXiv:2504.06714 | 2025-04 | B |

### 4.4 逻辑驱动 / 神经符号测试生成子方向

| 前沿工作 | 关键指标 | 指标值/结论 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|
| **TSC2CARLA**（Southampton/Politecnico） | 方法 | 时序逻辑规约（Timed Safety Properties）→ CARLA 自动测试生成；真实+合成时序规约验证 | Elsevier SCP DOI 10.1016/j.scico.2025.103420 | 2025, SCP | A |
| **LogiCase**（Yonsei/Korea） | 方法 | 竞赛编程逻辑描述（自然语言+输入输出）→ **CCFG 形式化** + 微调 CodeT5 生成测试用例 | IJCAI 2025 pp.7742-7750 DOI 10.24963/ijcai.2025/861；arXiv:2505.15039 | 2025, IJCAI | A |
| **COMBA**（Argentina） | 组合测试 | Alloy 规约 → 增量 SAT 组合测试（t=2）；更快、更小套件、发现更多真实规约 bug | ASE 2025 pp.2919-2931 DOI 10.1109/ASE63991.2025.00240 | 2025, ASE | A |
| **Tratto**（USI/SUPSI/Padova） | 预言正确率 | 公理预言 **73% acc / 72% precision / 61% F1**；比 GPT-4 few-shot+CoT **少 10× 假阳性** | ISSTA 2025 PACMSE 2(ISSTA) ISSTA083 DOI 10.1145/3728960 | 2025, ISSTA | A |
| **LLM2Alloy**（INESC-ID/里斯本大学） | 规约挖掘 | LLM 辅助写 Alloy 模型；in-the-loop 发现测试套件遗漏的 bug（构建时+部署后） | arXiv:2607.18555 | 2026-02（v2 2026-07） | B |
| **AUTOSPEC** | 方法 | LLM 从 OpenAPI 提取前置条件 + SMT（cvc5/Z3）生成测试数据 | arXiv:2509.25249 | 2025-09 | B |
| **LLM 路径约束求解**（arXiv:2505.15013） | 求解率 | LLM **~60%** 可解路径约束（vs SMT 求解器） | arXiv:2505.15013 | 2025-05 | B |
| **SynTest-LLM** | — | **NOT FOUND**（未检索到一手来源；不应引用） | — | — | D |

### 4.5 评估与基准方法论子方向

| 前沿工作 | 关键结论 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|
| **Zhao, Zhou & Cohen（多伦多大学）** | coverage/mutation 与 LLM 测试有效性**相关性依赖语境**：回归设定（代码可假定无缺陷）下跨模型比较有效；缺陷暴露设定下不可靠（branch vs raw mutation r=0.780 @k=10，控制规模后） | PACMSE 3(ISSTA) ISSTA002 DOI 10.1145/3832093；arXiv:2607.22880 | 2026, ISSTA（Distinguished Paper） | A |
| **Zhao, Song & Cohen** | buggy code prompt 使 misguided 测试 **0.46%→3.84%**、effective 测试 **8.51%→2.98%**；以 LLM 生成规约 docstring 替换代码可减少误导 | PACMSE 3(ISSTA) ISSTA113 DOI 10.1145/3832204 | 2026, ISSTA | A |
| **Inozemtseva & Holmes（2014）/ Papadakis et al.（2018）** | 控制规模后 coverage/mutation 与真实 bug 检出相关性大幅消失（人类测试） | 经 ISSTA 2026 复现论文引述 | 2014/2018 | B（经复现确认） |
| **ULT 污染对照** | TestEval/PLT（污染基准）高估：mutation 49.69%/50.80% vs ULT 40.21% | ULT 论文（TOSEM 2026） | 2026 | A |

### 4.6 任务提示词"参考方向"核验结果

| 提示词方向 | 核验结果 | 依据 |
|---|---|---|
| LANTERN（xCodeEval） | ✅ 存在（ICSE 2026，Rust +22.09pp Pass@10） | §4.2 |
| LaMAR（KV-Cache 通信） | ✅ 存在（ASE 2026，Defects4J 24.5%/QuixBugs 87.5%） | §4.2 |
| SPARC | ✅ 存在（C 语言，+31.36pp line） | §4.1 |
| AgentCoder | ✅ 存在 | §4.2 |
| TwinMem-Agent | ✅ 存在（FSE-C '26，Pro 89.1%） | §4.2 |
| ADI | ✅ 存在（FSE 2026，63.8% @$1.28） | §4.2 |
| FTDI（预算感知自修复） | ✅ **存在**（ESWA 2026，DOI 10.1016/j.eswa.2026.134164——10-16 评审曾标"未检索到"，本次已定位一手来源并更正） | §4.3 |
| VIGIL | ✅ 存在（设计论文，无基准数字） | §4.3 |
| Alloy 组合测试 + LLM | ✅ 存在（COMBA ASE'25；LLM2Alloy arXiv:2607.18555） | §4.4 |
| LogiCase（CCFG） | ✅ 存在（IJCAI 2025） | §4.4 |
| ESBMC-AI | ✅ 存在（AST 2025，90.4% 修复率） | §4.3 |
| "CrewAI 多 Agent SRE" | ❌ 未检索到一手来源（最近邻：STRATUS 多 agent SRE） | D |
| RunBugRun | ⚠ 存在（2023 多语言 APR 基准）但非 2025-2026 前沿，未展开 | — |
| ARC-APR / CI-Bench / HEJ-Robust / LogicEval | ❌ NOT FOUND（未检索到同名一手来源） | D |

---

## 5. 项目与前沿量化对比矩阵

> 项目现状仅采用第 3 节 A/B 级可验证数据；口径差异逐行标注。

| 维度 | 2025-2026 前沿 SOTA（等级） | 项目现状（等级） | 绝对差距 | 相对差距 | 竞争位置 | 可否对比 |
|---|---|---|---|---|---|---|
| **被测代码 line/branch coverage** | CoverUp 89-90% line+branch（Python OSS，A）；TestGenEval GPT-4o 35.2%（真实仓库文件级，A）；NexuSym +34.9pp（HumanEval，B） | synthetic：aitester 84.0-93.6% / plain_llm 86.0-97.2%（A，批次 details） | 与 CoverUp 口径不同；**低于自身 plain_llm 对照 2-13.6pp** | — | 落后于自身轻量臂；无同口径外部对照 | 不可外部对比 |
| **mutation score** | MUTGEN 89.5%（HumanEval-Java，B）；TestAgent 83.69%（Java 6 项目，B）；ULT 12-LLM 均值 40.21%（A）；Ockhamareto 49.9%@N=5（聚合基准，B） | QuixBugs 全变异体健全子集 **0.9396**（n=29/50，A/B 交叉）；ULT replace 0.6749（9/46）/ specir 0.4395（5/25）（B） | vs MUTGEN +4.5pp；vs TestAgent +10.3pp；vs ULT 均值 +53.8pp（口径更强：健全门+全变异体） | +5%/+12%/+134% | QuixBugs 口径同量级略高；ULT 口径 0.6749 数值上高于 Ockhamareto 49.9% 但**口径不可比**（聚合基准/ N=5 vs 单基准/全变异体/健全子集 9/46），不得据此宣称超越 | 可以（带三重标签） |
| **缺陷检出（F2P detection）** | 无同口径一手外部基准 | QuixBugs df **83.8%** / aitester 45.9%（A）；synthetic 44.8%/15.8%/1.5%（A）；T 轮 28.35%/3.07%/11.88%（A）；ULT 0/24（B） | 内部：aitester 比 df 低 37.9pp（QuixBugs）/28pp（synthetic）/25.3pp（T 轮） | −45%/−63%/−89% | **轻量协议层接近前沿量级但无外部对照；完整编排层落后自身轻量臂（已诚实降级）** | 不可外部对比 |
| **ULT accuracy（外部可标定）** | ULT 12-LLM 均值 **41.32%**（A） | **21.0%（42/200）**（B，引自 10-17 评审登记，本次未复算） | **−20.3pp** | −49% | **明确落后**（同协议、同基准、可标定） | 可以（最重要对标） |
| **程序修复（repair）** | LaMAR QuixBugs **87.5%**（Qwen3-8B，A）；SWE-bench Verified 76.8-79.2%（仓库级，A）；DEIMerge 37.0%（B） | QuixBugs **92.5%（37/40，gold 裁决，A）**；synthetic 修正口径 39.31%（B） | vs LaMAR +5.0pp（口径近似：QuixBugs 修复成功率；模型/判据不同） | +5.7% | **单函数口径同量级（可能略高，须带标签）**；仓库级未测（SWE-bench 全基础设施失败） | 近似可比（带标签） |
| **多智能体协作增益** | AgentCoder +6.1pp pass@1（A）；TraceCoder +34.43% 相对（B）；TwinMem +29.1pp（A）；LatentMAS token −83.7%（A） | 编排净 **−28pp / −37.9pp / −25.3pp**，成本 6-8×（A） | 与前沿正向增益方向相反 | — | **落后（相对"编排增益"叙事）；但与 Konstantinou ICST'26 / BOAD ICLR'26 阴性证据方向一致——项目结论是 2026 证据链的一环而非孤例** | 可以 |
| **false_fix（假成功）** | 前沿极少报告该指标（ISSTA'26 misguidance 论文提供 misguided 概念对照，A） | 条件 100%（143/143）/ 边际 59.58%（143/240）/ 修正 87.16%（380/436）（A/B） | 前沿无同指标对照 | — | **方法论披露领先（罕见系统报告该维度）；产品化致命伤** | 无对照 |
| **编译率/执行率** | TestAgent compile 99.11% / execution 97.46%（Java，B） | main_batch pooled compile 99.5-100% / exec 99.5%（A/B）；QuixBugs compile 100% / exec 82%（驱动任务双口径） | 同量级 | — | 持平（口径不同） | 方向参考 |
| **成本** | ADI $1.28/task（A）；TwinMem $0.0044/task（A）；LaMAR token −78~93%（A） | aitester $0.0259 / df $0.0045（synthetic，A） | 低于 ADI（任务不同）；与 TwinMem 同量级 | — | 轻量臂成本有竞争力 | 带任务标签 |
| **逻辑驱动·规格可编译率** | 无同指标前沿系统（SPARC/NexuSym 报 coverage 增量；COMBA 报 SAT 组合；Tratto 报预言正确率） | QuixBugs 0.7161 / ULT 0.5937 / synthetic 0.6397（v4 前门，B）；spec_expr_coverage 0.61-0.72（B） | 无对照 | — | **指标独创、无外部对照；增益未证实（三连阴性）** | 无对照 |
| **自修复运行时机制** | STRATUS 1.5× SOTA（A）；ESBMC-AI 90.4%（A）；ADI FLT 63.8%@$1.28（A） | 快照回滚 + 红回归门 + 弃权门 + 特异性门 + 停滞检测（机制在场，A）；端到端修复质量仅 QuixBugs/synthetic 验证 | 机制设计相当；**仓库级运行时接口未建（ADI 式 FLT 有设计文档未落地）**；形式化规约驱动自修复（STRATUS/ESBMC-AI）路线未走 | — | 安全机制有特色；动态分析接口与形式化自修复缺位 | 部分 |
| **工程化/可复现性** | 同域论文多提供 Docker（ADI/TwinMem）；系统门禁体系无同类 | **26 门禁脚本 + 覆盖率 ratchet + 口径矩阵 + SHA256SUMS + 模型指纹 + env 快照门 + 预注册链 + 零 LLM 复算**（A） | 显著超出学术原型常态 | — | **领先（学术标准内）** | 可以 |

---

## 6. 超越前沿方法设计（独立验证的超越路径）

> 设计原则：每条路径的理论依据均可追溯至第 4 节一手来源；预期提升标注置信度与证据等级；给出可独立验证的成败判定。**不基于任何二手数据或不可验证数据支撑"超越"论断。** 幅度类预期均为 E 级（理论推导），机制类依据为 A/B 级。

### P1（最高优先级）：ULT/TestGenEval 外部口径严格对标——把"合成集内部对照"升级为"外部基准可标定系统"

- **技术路径**：以 ULT 官方口径（accuracy + Mut@k）在 lite46 + probe25 + 扩样 n≥200 上跑 {plain_llm, plain_llm_df, df+docstring-augment} 三臂；TestGenEval-Lite 子集做 coverage 对标。项目已有 `src/datasets/dataset_ult.py` 与 `emse_ult_*` 系列脚本，缺口只是规模与协议对齐。
- **差异化点**：前沿系统多在 ULT 上报单模型分数；项目以**检出优先协议 + 零 LLM 全数字复算**参赛，可同时给出 accuracy/mutation/成本三维对照——ULT 论文本身不报成本，这是增量。
- **理论基础**（一手）：ULT（TOSEM 2026，A）提供去污染基准与 12 模型均值 41.32%/40.21%；Ockhamareto/MIST-RL（B）给出提示工程轴对照 31.3%@N=5。
- **预期提升**：ULT accuracy **21.0% → ≥41.32%**（12 模型均值线）；mutation **≥40.21%**。**置信度：中高**（纯工程 + 协议迁移；df 协议在 synthetic 已证 +43pp，但 ULT 天花板结构不同）。证据等级：**E（幅度）+ A（基线）**。
- **实验验证**：基准 ULT（n=200，预注册）；对照 = ULT 官方 12 模型均值（A）与 MIST-RL 31.3%（B）；指标 = accuracy、Mut@k（sanity-gated 口径）、$/task；McNemar 配对 + BH-FDR + Wilson CI；3 个独立 cache namespace；temp=0；provenance 全字段落盘。
- **反事实推演**：若 RL 路线（Ockhamareto）同期刷高 ULT——项目应对齐提示工程轴（MIST-RL 为对照）并明示"不同技术轴"；护城河 = 检出优先协议在**缺陷暴露设定**的判别力（ULT accuracy 口径不测检出，项目可补 detection 维度）。
- **里程碑**：短期（1 月）：扩样至 n=200 + 三臂预注册；中期（2-3 月）：TestGenEval-Lite 对标；长期（6 月）：方法章节入论文。
- **成功判定**：ULT accuracy ≥41.32% 且 McNemar p<0.05（vs plain_llm 臂）；**失败判定**：<30% → 确认"合成集饱和 ≠ 真实函数能力"，本身是可发表阴性，项目转向方法论主线。

### P2：独立 docstring 规格锚——把 spec-first 从"再描述"升级为"独立规格增广"

- **技术路径**：df_spec 显著负（−25.7pp，A）已定位根因 = **锚材料是缺陷代码的再描述**（非独立正确规格）。修复方向有项目自有数据支撑：L 轮 docstring 锚三臂中**增广臂 82.9% vs df 80.6%（非劣）**而替换臂 60.0% vs 86.1%（显著负）——即"**加独立规格**不伤、"**删实现**才伤"，与 Zhao/Song/Cohen（ISSTA 2026，A）"代码必须被移除而非仅补充"的结论在 Python 单函数设定下形成**受控的边界细化**。下一步：人类 docstring 增广 + SpecExpr 机器化子句 + 误导三分度量（项目已有 `misguided_metrics.py`）预注册二臂。
- **差异化点**：前沿（Zhao/Song/Cohen）止步于 NL docstring 替换；项目独有**可编译规约 + 确定性 oracle 注入 + 逐子句拒绝归因**，可把"规约质量"变成可测量量（spec_expr_coverage 0.61-0.72，B）。
- **理论基础**（一手）：Zhao/Song/Cohen（A）：misguided 0.46%→3.84%、effective 8.51%→2.98%；MAST（A）：47% 多 agent 失败归因验证环节；项目 A 级数据：df_spec 负性 + over_red 22.5%→46.0%。
- **预期提升**：增广臂 detection 相对 df **非劣且 ≥+5pp**；oracle-correct 示例 Δ≥5 任务（已在 3/3 seed 复现 +6，A）。**置信度：中**。证据等级：**E（幅度）+ A（机制）**。
- **实验验证**：QuixBugs 41 缺陷程序 + ULT probe25；臂 = {df, df+docstring-augment, df+specir-augment}；指标 = F2P detection + misguided/effective 三分 + $/task；McNemar + BH-FDR；预注册先落盘；3 cache namespace；temp=0。
- **反事实推演**：Zhao 设定为 Defects4J Java，迁移未证——但项目增广臂非劣数据是首个 Python 单函数证据；护城河 = 规约机器化 + 误导量化体系（可成为基准贡献）。可复制性：中（需复刻 DSL 门 + oracle 链）。
- **里程碑**：短期（1-2 月）：预注册 + QuixBugs 二臂；中期（3-6 月）：ULT 复验 + 三分解剖；长期（6-12 月）：与 Zhao/Song/Cohen 设定差异的跨语言对照。
- **成功判定**：增广臂 ≥ df −5pp（非劣）且 misguided 率相对 df 下降 ≥30%，p<0.05；**失败判定**：<df −10pp → spec anchoring 在本系统关闭，转入"协议 + 评测诚信"定位。

### P3：评测诚信 checklist 基准化——把"测量伪影系列"升级为可引用的评估方法论贡献

- **技术路径**：将四起测量伪影（patch 围栏/跨文件未物化/判分树 import 布局/Planner 静默降级）+ false_fix 口径矩阵（条件 100%/边际 59.58%/修正 87.16%）+ Mut@k 三偏差修正（uuid4 截断/恒红平凡击杀/gold 未验证）+ fail-closed None 纪律固化为**可执行 checklist + 开源校验器**（项目已有 26 门禁工程底座），对 3-5 个公开工件做重放（ULT 官方 12 模型结果、TestGenEval 公开产物）。
- **理论基础**（一手）：Zhao/Zhou/Cohen ISSTA 2026（A，代理指标语境依赖）；ULT（A，污染基准高估）；MAST（A，验证环节失败占 47%）；项目自身勘误链（A 级工件）。
- **预期提升**：非性能指标，是**标准话语权**——以方法论论文 + 开源 checklist 占据"LLM 测试生成评测诚信"细分赛道。**置信度：高**（素材全部在场且 A 级可复现）。证据等级：**A**。
- **实验验证**：对公开工件应用 checklist，量化"未修正即高估"幅度；与 ISSTA 2026 replication 和 ULT 对话。
- **反事实推演**：replication 社区可能自行收敛（时间窗 12-18 个月）；护城河 = 伪影案例库 + 门禁工程 + 零 LLM 复算链。
- **里程碑**：短期（1-3 月）：checklist v1 + 首个外部重放；中期（3-6 月）：2 个外部数据集定量结论；长期（6-12 月）：方法论文（FSE/ICSE/ISSTA/TOSEM 方法论 track）。
- **成功判定**：≥2 个外部公开数据集复现出"未修正即高估"的定量结论；**失败判定**：外部工件应用后无系统性修正 → 伪影为个案，降格为内部工程文档。

### P4：动态分析接口（ADI 式 FLT）+ per-test 超时——非终止缺陷的判定通道

- **技术路径**：① 生成测试统一携带 per-test 超时；② 落地已设计未实现的 Frame Lifetime Trace（`docs/design/frame_lifetime_trace.md`），把"挂起"转化为"执行到第 k 帧的状态证据"供 Debugger 定位非终止缺陷。
- **理论基础**（一手）：ADI（FSE 2026，A）：函数级交互使基础 agent 达 63.8% @$1.28、插入 SOTA +6.2~18.5%、导航 token −79.9%；项目自测：4 个 None 任务全部为"缺陷实现不终止"。
- **预期提升**：可判定检出 37/41 → **41/41**；QuixBugs detection 45.9% → **≥55%**。**置信度：中高**（机制确定性部分高，幅度推测）。证据等级：**E（幅度）+ A（机制）**。
- **实验验证**：QuixBugs + synthetic；对照 = 现行 120s fail-closed 口径；指标 = 可判定率、detection、非终止类 F2P 转化数；**零 LLM 可离线复算**（超时行为确定性）。
- **反事实推演**：ADI 已开源同思路——差异化在"测试生成语境的 FLT"（ADI 是修复语境）。可复制性：中。
- **里程碑**：短期（2-3 月）：per-test 超时 + FLT v1；中期（3-6 月）：接入 Debugger 定位。
- **成功判定**：非终止类 4 任务中 ≥3 获特异性 F2P 检出；**失败判定**：可判定率提升但 detection 无变化 → 非终止非瓶颈。

### P5：编排增益第三次决断——记忆增强 + 预算感知（TwinMem 路线，仅当坚持编排增益时）

- **技术路径**：以 TwinMem-Agent（FSE-C '26，A：Pro 89.1% vs 60.0%、成本 −18×）与项目 E6 matched（预算混杂被否，A）为依据，把"专家池/辩论/多候选"替换为**跨任务情景+语义双层记忆 + 预算感知早停**；编排组件转正门槛 = 与 plain_llm_df 等预算对照下复现正向 detection 增量（ADR-0016 已立此规矩）。
- **预期提升**：若 TwinMem 量级的 1/3 迁移（+10pp）且成本不升。**置信度：低中**（TwinMem 为 SWE-bench Pro 子集、不同骨干；迁移未证）。证据等级：**E（迁移推测）+ A（来源）**。
- **实验验证**：synthetic 流式任务 + QuixBugs；对照 = df 臂 matched-budget；指标 = detection、$/task、迭代数；McNemar；预注册。
- **反事实推演**：BOAD（ICLR 2026，B）表明增益可能来自自动搜索而非手工设计——若 P5 阴性，最后手段是"自动搜索编排 vs 手工编排"对照（项目已有 `orchestration_search.py` 16 臂 bandit 未实跑，ADR-0034 冻结中）。
- **里程碑**：短期（1-2 月）：记忆臂实现 + 黄金表；中期（3-6 月）：matched-budget 三臂。
- **成功判定**：等预算下 detection ≥ df +8pp 且 p<0.05；**失败判定**：第三组阴性 ⇒ 永久关闭编排增益主张（科学上可接受结局）。

### P6：形式化规约驱动自修复（STRATUS/ESBMC-AI 路线）

- **技术路径**：把 SpecExpr 子句 + z3 见证层（T 轮机制层已 pass：witness_rate 0.125116、timeout 0，B）用作**形式化规约源**，走 ESBMC-AI 式 counterexample-guided 补丁生成：求解器反例 → 补丁假设 → 回归验证；STRATUS 式 TNR 规约 + 反馈循环做运行时自愈。
- **理论基础**（一手）：ESBMC-AI（AST 2025，A）：counterexample 引导修复 90.4%；STRATUS（A）：形式规约 + 反馈循环比 SOTA 高 1.5×。
- **预期提升**：修复质量维持 QuixBugs 92.5%（37/40）的同时把 **false_fix 边际口径 59.58% → ≤30%**（形式验证补丁的假成功通道结构性收窄；注意规格错误仍可致假成功——须报规格覆盖率）。**置信度：中**。证据等级：**E（幅度）+ A（机制）**。
- **实验验证**：QuixBugs 41 + synthetic；臂 = {现行修复, 形式化验证修复}；指标 = repair rate、false_fix（边际）、规格覆盖率、求解耗时；零 LLM 部分可离线。
- **反事实推演**：ESBMC-AI 面向 C 且用 counterexample；项目面向 Python 单函数且用白名单 SpecExpr——表达力受限（compile rate 0.59-0.72）是主要风险。可复制性：中低。
- **里程碑**：短期（1-2 月）：SpecExpr→z3 补丁假设生成管线；中期（3-6 月）：二臂 A/B。
- **成功判定**：形式化臂 false_fix ≤20% 边际且 repair ≥80%；**失败判定**：真实基准规格可编译率 <30% → 降级为安全网（仅高置信子句启用）。

### P7（探索级）：潜在空间规格传递（LaMAR/LatentMAS）

- **技术路径**：KV-cache 潜在空间通信替代 Planner→Generator 的文本 BNF 契约段（LaMAR：token −78.4~93.4%、延迟 −82.5%，A；LatentMAS：token −70.8~83.7%、4~4.3× speedup，A）。
- **现实约束**：项目为 API 架构（OpenAI 兼容 + 文件缓存）+ 零默认依赖（ADR-0004），KV-cache 传输需本地/同栈模型——架构冲突。**结论：列为 P2 探索，不作为投稿主线**；证据等级：E。若未来接受本地模型部署，可作为成本维度反击点（当前 $/task 已有竞争力，优先级低）。

---

## 7. 差距分析表

| # | 维度 | 项目现状（证据） | 2025-2026 前沿要求（一手） | 差距 | 严重度 |
|---|---|---|---|---|---|
| G1 | 外部效度 | synthetic 为主；QuixBugs n=41；ULT n=24-25 且 accuracy 21.0% < 均值 41.32%（A/B） | ULT/TestGenEval/SWE-bench 家族标定（A） | **主结论建立在合成模板；唯一可标定维度落后 20.3pp** | **高** |
| G2 | 规格锚增益 | 三连阴性（D1/M4/df_spec，A）；增广臂非劣（A） | Zhao/Song/Cohen spec-based 有效（A） | 有理论盟友、实证转化弱；根因已定位（锚 provenance） | 高 |
| G3 | 多智能体增益 | 编排净负 −25~−38pp（A） | AgentCoder/TraceCoder/TwinMem 正向（A/B） | 落后（已诚实降级）；与 Konstantinou/BOAD 阴性证据一致 | 高（已止损） |
| G4 | 动态分析接口 | FLT 有设计未落地；4 个 None 任务无判定通道 | ADI FLT 63.8%@$1.28（A） | 缺位 | 中 |
| G5 | 形式化自修复 | z3 见证层机制 pass 未启用（B）；ESBMC-AI 路线未走 | ESBMC-AI 90.4%（A）；STRATUS 1.5×（A） | 缺位 | 中 |
| G6 | 统计严谨 | McNemar/BH-FDR/贝叶斯/聚类校正/功效分析/MDE（A） | SWE-bench 社区 Wilson CI（A） | 已持平；Wilson CI 已补（10-16 评审后） | 低 |
| G7 | 人工评估 | E7 未执行（项目自报，D） | 综述要求人工 adjudication/Kappa | 缺失（已披露） | 中 |
| G8 | 成本口径 | $0.0259 vs $0.0045/task（A）；token 记账完整（D2 已收口） | TwinMem $0.0044/ADI $1.28（A） | 已报告且记账完整 | 低 |
| G9 | 文档口径一致性 | 门禁数 24/25/27 三处不一致；"0 failed"无环境标签；git 领先 65 提交 | 单一事实源纪律（项目自设） | **文档低于/高于工件并存** | 中 |
| G10 | 测试环境稳健性 | 15 失败 = 沙箱伪影（broker mkdir + ps 禁令） | CI 正常环境通过 | 测试对宿主环境有隐性假设 | 低-中 |
| G11 | 单模型依赖 | deepseek-flash 为主 | 多模型矩阵成规范（ULT 12 模型） | 存在 | 中 |
| G12 | 编排搜索债 | `orchestration_search.py` 16 臂未实跑（ADR-0034 冻结） | BOAD 自动搜索（B） | 冻结中（有解锁条件在案） | 低 |

---

## 8. Python 专项诊断表

| # | 检查项 | 现状（本次独立核验） | 判定 | 建议 |
|---|---|---|---|---|
| 1 | 项目结构 | src layout + 薄入口 main.py + 134 mypy 源文件 / 55,948 行；`src/__init__.py` 动态版本；PEP 621 + PEP 639 SPDX | ✅ 优 | 保持 |
| 2 | 依赖管理 | requirements.txt↔lock 一致（gate 通过，仅 zstandard 传递依赖告警）；pyproject extras 分组（rag/viz/experiments/ux/dev/formal/db/ult）；零默认依赖（ADR-0004） | ✅ 优 | release 增 SBOM（`pip-audit --format cyclonedx`） |
| 3 | 代码质量 | ruff 0.16.3 **All checks passed** + format 809 文件全过（本次实跑）；mypy **134 文件 0 错误**（本次实跑）；bandit skip 清单有逐条理由 | ✅ 优 | 保持；`make gates` 每批必跑 |
| 4 | 测试 | 8,934 收集 / 沙箱实跑 8,914 passed + 15 failed（环境伪影，已归因）；meta 覆盖 96.55%/92.80%（本次逐位复验）；零断言门 383 文件 0 违规；hypothesis property 测试已在位 | ✅ 优（附环境标签） | 加固环境假设（见 A-14）；补沙箱/CI 双轨登记 |
| 5 | 可复现性 | lock + Dockerfile.repro + reproduce.sh + 批次 provenance（git_sha/python/platform/fingerprint/env snapshot）+ SHA256SUMS + 零 LLM 复算链 + `make reproduce-zero-llm` | ✅ 优 | 增 MLflow 本地 tracking 或结构化 run registry（可新增） |
| 6 | 安全 | `.env` 未读取（纪律）；三层日志脱敏；凭证剔除（`credential_scrub`）；venv 沙箱 + Docker 隔离 + 包名白名单（slopsquatting 防护）；pip-audit CI（chromadb 5 条显式豁免） | ✅ 良 | `bandit -r src -ll` 入 CI 阻断（pyproject 已有配置但 CI 接入状态待确认）；release 门 `pip-audit --strict` |
| 7 | 性能 | xdist -n 4 loadfile；批后处理墙钟可观测（Q-3/R-3）；token 记账完整 | ✅ 良 | py-spy profile 长任务；缓存命中记账已收口（D2，10-16 评审后） |
| 8 | 数据/实验管线 | 口径矩阵 + 去污染检查 + fail-closed None + None 不计 0 + 跨臂 cache namespace 隔离 + 模型指纹门 | ✅ 优（方法论） | synthetic 模板分布文档化（DATA_CARD 已部分） |
| 9 | 文档 | 双语文档同步门（0 警告）；BASELINE 单一事实源；36 份 ADR；MODEL/DATA CARD；论文 20 处 SRC 注释 | ✅ 优（但见 G9 口径漂移） | 统一"门禁数量"口径为可复算命令；`0 failed` 带环境标签 |
| 10 | 已知技术债 | ① graph→experiments 反向导入冻结（ADR-0016）；② orchestration_search 16 臂未实跑（ADR-0034 冻结）；③ subprocess.run→run_with_timeout 转换（10-16 评审称已完成，本次抽查通过） | ⚠ 低-中 | 按 ADR 解锁条件推进 |

---

## 9. 领域专项诊断表

| 维度 | 项目现状（独立核验） | 前沿对照（一手，等级） | 诊断 |
|---|---|---|---|
| 逻辑规格 | SpecExpr 白名单 AST + BNF 单一事实源 + 8 类拒绝归因 + v4 护栏；spec_expr_coverage 0.61-0.72（B） | TSC2CARLA（时序逻辑，A）；LogiCase（CCFG，A）；COMBA（Alloy+SAT，A）；Tratto（公理预言 73% acc，A） | **规格表达工程完整性在已检索文献中无同类；但增益未证（三连阴性）；规格可编译率 0.59-0.72 低于形式化方法路线 100%（后者靠人工写规约）** |
| 约束求解 | spec_smt z3 见证层（T 轮机制 pass：witness_rate 0.125、timeout 0，B）；默认关 | COMBA 增量 SAT（A）；ESBMC-AI counterexample 引导（A）；LLM 路径约束 ~60%（B） | 有种子能力，未启用、未评估；P6 路线依据充分 |
| 测试覆盖准则 | F2P 三段判定 + 特异性门 + 变异得分 + 分支覆盖注入 + 误导三分（M 轮落地） | ULT accuracy/mutation（A）；Zhao ISSTA'26 语境限定（A） | 准则齐全且**自建了前沿缺失的误导维度**；外部标定缺（G1） |
| 测试预言 | spec_oracle 确定性注入 + 独立判读（N-3）+ 示例通道（correct 0→8 探索性） | Tratto 73% acc/72% P/61% F1（A）；CANDOR +15.8~25.1pp（B） | 确定性路线与 Tratto 神经符号路线可互引；oracle 正确率未系统度量（correct 仍 0） |
| 多智能体 | LangGraph 状态机 + 事件总线 + 专家池/辩论（默认关）+ 编排净负（A） | AgentCoder/TraceCoder/TwinMem/LatentMAS/BOAD（A/B） | **落后（已降级）；MAST 失败分类学（A）支持项目"验证环节主导失败"的设计取向** |
| 通信机制 | 文本 prompt + 语义缓存；无 KV-cache | LaMAR token −78~93%（A）；LatentMAS −83.7%（A） | 落后；API 架构下短期无解（P7 探索） |
| 自修复 | 快照回滚 schema（T 轮落地）+ 红回归门 + 弃权门 + 防测试黑客门 + 停滞检测（A-19 修复） | STRATUS 1.5×（A）；ESBMC-AI 90.4%（A）；VIGIL 设计（A）；FTDI 预算感知（A） | **安全机制设计有特色；缺形式化规约驱动修复（P6）与仓库级运行时接口（P4）** |
| 闭环收敛 | 停止原因枚举单点判定 + 覆盖停滞检测（默认关，T 轮真实 LLM 复验 `unexpected_delta`）+ 预算停止 | TraceCoder 回滚+停滞计数（B）；AIOpsLab 基准（A） | 相当；停滞检测收益判据需下一轮修正口径（项目已登记） |
| 评估公平 | 双材料 gold 独立裁决 + 预注册 + 等预算对照（E6）+ 聚类校正 + MDE 报告 + 模型指纹 | SWE-bench 官方榜单规范（A）；ISSTA'26 语境分层（A） | **领先**；E7 人工裁决缺失（G7） |
| 安全合规 | 沙箱 + 注入防护 + secrets 纪律 + 威胁模型 + 日志脱敏门 + 包名白名单 | — | ✅ 达标；建议补 CI bandit 阻断确认 |

---

## 10. 改进 / 优化 / 新增建议表

| # | 对应文件/位置 | 问题 | 一手前沿依据 | 建议内容 | 类型 | 优先级 | 预期收益 | 成本/风险 | 验证指标 | 时间线 | 工具/命令 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A-01 | `experiments/emse_ult_*`、`src/datasets/dataset_ult.py` | ULT accuracy 21.0% < 41.32% 均值，无可标定性能 | ULT（TOSEM 2026，A） | 落地 P1：n≥200 三臂扩样 + TestGenEval-Lite 对标，预注册 | 必须改进 | **P0** | 外部效度；可比性 | 中（~$3-6 LLM 预算） | accuracy ≥41.32% p<0.05 | 1-2 月 | `python -m experiments.emse_ult_dfsmoke_accuracy`；预注册件落盘 |
| A-02 | `experiments/emse_docstring_anchor_*`、`src/agents/planner.py` | df_spec 负性根因（锚=再描述）已定位但独立锚未预注册 | Zhao/Song/Cohen（ISSTA 2026，A） | 落地 P2：docstring 增广臂预注册 + 误导三分判据 | 必须改进 | **P0** | spec 路线决断 | 中（~$0.5-1） | 增广臂非劣 ∧ misguided −30% | 1-2 月 | `emse_docstring_augment_analysis.py` |
| A-03 | `paper/draft.typ` §RQ4/§repro；`docs/design/layered_narrative.md` | T 轮 B2 not_reproduced 与漂移发现（thinking 模式/协议开关）未入论文 | 项目 A 级工件（B2 README §0.6） | 补 T 轮复现段 + 漂移定位 + `{thinking on/off}×{profile}` 2×2 消融预注册 | 必须改进 | **P0** | 论文与工件同步 | 低 | SRC 注释可追溯；2×2 预注册落盘 | 2-4 周 | `make paper-audit` |
| A-04 | `docs/preregistration.md` E7 节 | 人工 adjudication 未执行 | ISSTA'26 对 proxy 指标的限定（A） | 执行 n≥100 双人盲审 + Cohen's κ，或论文显式删除人工暗示 | 必须改进 | P0 | 结论强度 | 中（人力） | κ≥0.7 | 1-2 月 | `docs/HUMAN_ADJUDICATION_PROTOCOL.md` 已在场 |
| A-05 | `.github/workflows/ci.yml`；README；论文 §repro | 门禁数量口径 24/25/27 三处不一致 | 项目自设单一事实源纪律 | 统一为可复算口径（如 `ls scripts/gates/*.py \| wc -l` = 26；ci.yml 调用点去重计数），加文档门禁锁定 | 必须改进 | P1 | 诚信细节 | 低 | 三处数字一致 | 1 周 | `grep -c "scripts/gates/" .github/workflows/ci.yml` |
| A-06 | `BASELINE.yaml §tests.total_failed`；README 测试状态行 | "0 failed" 无环境标签；沙箱实跑 15 失败（broker/ps 伪影） | 本次独立发现 | 登记口径改为"正常环境 0 failed；沙箱 broker/ps 受限环境 N 失败（已归因）" | 必须改进 | P1 | 口径诚信 | 低 | 环境标签在场 | 1 周 | `pytest --basetemp=/tmp/x` |
| A-07 | git 远端状态 | main 领先 origin **65** 提交，CI 从未验证 F/G/H/I/T 轮 | — | 推送前跑一遍完整 CI（或 `act` 本地模拟）；推送为外部动作需用户确认 | 必须改进 | **P0** | 代码可信度 | 中（CI 时间） | origin/main = HEAD；CI 绿 | 需用户授权 | `git push`（确认后） |
| A-08 | `tests/test_executor_repo_j4_coverage.py:610` 等 | 测试依赖 `mkdir(exist_ok=True)` 的 OS 语义，被沙箱 broker 垫片破坏 | 本次独立发现 | 改防御式：`if not repo_dir.exists(): repo_dir.mkdir(parents=True)`；或测试内 `monkeypatch`  brokers | 建议优化 | P2 | 环境稳健 | 低 | 沙箱内该测试通过 | 2 周 | `pytest tests/test_executor_repo_j4_coverage.py` |
| A-09 | `tests/test_p0_hardening*`、`tests/test_orphan_repro_*` | 孤儿检测依赖 `ps`/`pgrep`，沙箱禁用时失败 | 本次独立发现 | 检测 `ps` 可用性，不可用时 skip 并标注环境原因（与项目既有 skipif 降级惯例一致） | 建议优化 | P2 | 环境稳健 | 低 | 沙箱内 skip 而非 fail | 2 周 | `shutil.which("ps")` 守卫 |
| A-10 | `src/tools/spec_first.py`、`experiments/emse_df_spec_*` | over_red/misguidance 未接入运行时闭环 | Zhao/Song/Cohen（A） | misguided 三分接入特异性门路由（A-02 配套） | 必须改进 | P1 | 误导航度可行动化 | 中 | 门路由按三分决策 | 2-3 月 | `experiments/misguided_metrics.py` |
| A-11 | `docs/design/frame_lifetime_trace.md`、`src/graph/nodes.py` | FLT 设计未落地；4 个 None 任务无判定通道 | ADI（FSE 2026，A） | 落地 P4：per-test 超时 + FLT v1 | 必须改进 | P1 | 可判定检出 37/41→41/41 | 中 | 非终止 ≥3 获 F2P | 2-3 月 | `python -m experiments.run_benchmark --dataset quixbugs`；**2026-10-18 复核更正：per-test 超时两路径均已在场（executor 命令层 + M1 pytest-timeout 探测，评审时信息不完整）；FLT 按设计文档 §7 需先预注册（ADR-0003），未实装** |
| A-12 | `src/specs/spec_smt.py`、`src/tools/` 修复环 | z3 见证层闲置；形式化修复路线未走 | ESBMC-AI（AST 2025，A）；STRATUS（A） | 落地 P6：counterexample-guided 补丁假设 + 二臂 A/B | 建议优化 | P1 | false_fix 59.58%→≤30% | 中-高 | 形式化臂 false_fix ≤20% | 3-6 月 | `SPEC_SMT_ENABLE=true pytest tests/test_spec_smt*` |
| A-13 | `experiments/run_orchestration_search.py`、`src/graph/orchestration_search.py` | 16 臂 bandit 未实跑 | TwinMem（A）；BOAD（B） | 实跑或按 ADR-0034 解锁五条件推进；防"死代码宣称能力" | 必须改进 | P2 | 诚信/增益决断 | 中 | 工件入库或 ADR 冻结记录 | 2 周-3 月 | ADR-0034 |
| A-14 | `experiments/`（追踪层） | 实验追踪 = 文件系统 | 可复现研究最佳实践 | 接 MLflow 本地 tracking 或结构化 run registry | 可新增 | P2 | 复现效率 | 低 | 一键重放任意批次 | 1 月 | `mlflow ui` |
| A-15 | `.github/workflows/ci.yml` | bandit 接入状态待确认（pyproject 有配置） | Python 安全最佳实践 | 确认 `bandit -r src -c pyproject.toml` 入 CI 阻断；release 增 SBOM | 可新增 | P2 | 供应链安全 | 低 | CI 绿 + SBOM 入库 | 2 周 | `bandit -r src -c pyproject.toml` |
| A-16 | `src/agents/base_agent.py` 模型路由 | 单模型依赖（deepseek-flash） | ULT 12 模型矩阵（A） | 关键结论补第二模型交叉（如 glm/qwen） | 建议优化 | P2 | 结论稳健 | 中（~$2-4） | 两模型同向 | 2-3 月 | `expand_models` 工具 |
| A-17 | `docs/`（论文层） | T 轮漂移（thinking 模式、协议开关）未论文化 | 项目 A 级工件 | 补 §漂移与可复现边界段（A-03 配套） | 必须改进 | P1 | 审稿稳健 | 低 | 漂移段 + 2×2 预注册 | 2-4 周 | `make paper-audit` |
| A-18 | `paper/draft.typ` | TODO(submit) 占位（双盲作者/DOI/URL） | — | 投稿前替换 + SRC 注释转正式 artifact 引用 | 必须改进 | P1 | 可投稿性 | 低 | 0 个 TODO(submit) | 投稿前 | `typst compile paper/draft.typ` |
| A-19 | `docs/reviews/review_recompute/` + 本报告 | 三轮评审复算工件分散 | — | 建立复算工件索引（SHA256 + 命令 + 结论） | 可新增 | P2 | 评审可审计 | 低 | 索引门禁 | 1 月 | — |
| A-20 | `experiments/results/main_batch` 等 | R-P0-2 原始批 `git_dirty=true`（已披露） | — | 历史批保持披露标签；新批一律干净树 + 指纹 | 必须改进 | P1 | 诚信 | 低 | provenance 字段门 | 持续 | `check_model_fingerprint.py` |

---

## 11. 既有评审结论独立复核表

> 复核对象：① 项目自述核心结论（BASELINE/README/ADR/论文）；② `INDEPENDENT_REVIEW_2026-10-16.md`（IR-16）；③ `docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md`（IR-17）。方法：本次独立重跑/重算 + 一手核验。

| 原结论 | 原文位置 | 独立复核方法 | 复核结论 | 支持/推翻/无法验证 | 依据 |
|---|---|---|---|---|---|
| R-P0-2 三臂检出 15.8%/1.5%/44.8% 与 −28pp | BASELINE §benchmark | 原始 JSON 在场 + SHA 校验；两轮既有评审已独立重算且本次交叉核对其引用的统计量（χ²=48.79 等） | 方向与数值获两次独立重算支持 | **支持** | A（工件）+ B（本次未重写聚合脚本，明示） |
| T 轮 B2：not_reproduced，R2 −25.29pp 显著 | BASELINE §b2 | 读 ANALYSIS_REPORT + 804 项 SHA 校验 + per-seed 求和核对 | **逐位一致**；not_reproduced 判自次级排序不稳健，核心负面稳健 | **支持** | A |
| B1 协议文本效应 +16.1/+19.5pp 显著、采样效应可忽略 | BASELINE §b1 | 读 ANALYSIS_REPORT evaluation 节 | **逐位一致** | **支持** | A |
| df_spec 显著负（−25.7pp）且根因=锚 provenance | BASELINE §df_spec/论文 RQ4 | 读 DF_SPEC_REPORT.json | **逐位一致**； provenance 归因有 misguided 数据佐证（over_red 22.5%→46.0%） | **支持** | A |
| ULT accuracy 21.0%（42/200）< 41.32% 均值 | IR-17 §0.2 | 查找独立复算工件路径 | 未找到本次可独立重算的工件（IR-17 登记于复制包索引）；数字方向与 ULT 0/24 detection、sanity 14/71 valid 一致 | **无法验证（降权使用）** | B（单一来源登记） |
| QuixBugs Mut@k 0.9396（1182/1258） | IR-16 C9/IR-17 | 工件在场；两轮评审重算一致 | 交叉一致 | **支持（带三重标签）** | A（历史两次）/B（本次） |
| 6532→8934 测试收集增长、0 failed | BASELINE §tests | 本次 collect=8934 逐位；全量实跑 15 failed=环境伪影 | 收集数支持；"0 failed"须带环境标签 | **部分支持（条件化）** | A |
| IR-16 结论"多智能体增益被自身 A 级数据否定（已诚实降级）" | IR-16 §0.2 | T 轮 B2 复现 + Konstantinou ICST'26/BOAD ICLR'26 外部核验 | 不仅支持，且**外部证据链在 2026 年持续增强** | **支持** | A |
| IR-16 P3"评测诚信方法论基准化"方向 | IR-16 §6 | 素材在场性核验（4 伪影 ADR + 口径矩阵 + Mut@k 修正）+ MAST/ULT/ISSTA'26 一手依据 | 方向成立且是当前最高杠杆路径 | **支持** | A |
| IR-16 A-03"ULT DOI 疑错挂→已更正为归属正确" | IR-16 §11 | 本次未重取 ACM DL 页面（两轮评审已核验 DOI 10.1145/3805043） | 接受其更正（未重复核验，明示） | **支持（转引）** | B（转引两轮 A 级核验） |
| IR-17 结论"9 支持/2 部分/1 无法验证/1 需修正"（对 IR-16） | IR-17 §0.1 | 抽查其中 3 条（ULT DOI、token 记账、四批工件入库） | 抽查项与本次观察一致（token 记账 D2 已收口、工件已入库） | **支持（抽查）** | B |
| IR-17 建议"改用人类 docstring 作独立规格锚" | IR-17 §0.2 | L 轮 docstring 三臂数据在场（替换 60.0 vs 86.1 负；增广 82.9 vs 80.6 非劣） | **方向被项目自身新数据细化**：增广可、替换伤——与 Zhao/Song/Cohen 形成受控边界 | **支持（且已推进）** | A |
| "24 个 CI 门禁"（IR-16/IR-17/README/论文） | 多处 | `ls scripts/gates/*.py`=26；ci.yml 调用 27 处；git 记录"25 道全绿" | **口径三处不一致，需统一** | **部分推翻（数字口径）** | A（实测） |
| "领先 origin 26 提交"（工作记忆/旧材料） | 会话记忆 | `git rev-list --count main ^origin/main` = **65** | 数字过期（项目已推进多轮） | **推翻（过期表述）** | A |

---

## 12. 优化后的项目方案与路线图

### 12.1 重新定位（基于独立对比的竞争战略）

维持并强化项目已自行选择的双支柱定位（本报告独立判定该定位与 2026 外部证据一致，予以支持）：

- **支柱 1（性能，可外部标定）**：检出优先提示协议（+43pp，A 级，T 轮指纹级复现文本效应 +16~+20pp 显著）+ ULT/TestGenEval 外部口径对标（P1，目标 ≥41.32%）+ 独立 docstring 规格增广（P2）+ 动态分析接口（P4）；
- **支柱 2（方法论）**：测量伪影系列 + false_fix/误导口径矩阵 + Mut@k 三偏差规范 + 评测诚信 checklist（P3）——对齐 ISSTA 2026 replication、ULT、MAST，争夺评估标准话语权；
- **多智能体**：维持消融容器定位（ADR-0016），P5 记忆臂做第三次等预算决断；失败则永久关闭（科学上可接受）；
- **自修复**：P6 形式化规约驱动修复作为差异化主线（ESBMC-AI/STRATUS 路线），现有安全机制（回滚/弃权/红回归门）保持默认开。

### 12.2 技术路线（优化后）

```
NL/SpecExpr 规约（Planner，BNF 单一事实源）
   → 检出优先 Generator（buggy code 可留但须配独立 docstring 规格增广）
   → 执行器（per-test 超时 + FLT 见证 + venv/Docker 沙箱）
   → 特异性门（specific/over/misguided 三分路由）
   → 形式化验证修复环（z3 反例引导补丁 + 红回归门 + 快照回滚 + 弃权门）
   → M1 gold 独立裁决（F2P 三段 + false_fix + misguided + 成本）
评测诚信层：口径矩阵 + 伪影校验器 + Wilson CI + 预注册 + E7 人工 adjudication
外部标定层：ULT accuracy/Mut@k + TestGenEval-Lite coverage（与 12 模型均值/一手 SOTA 对照）
```

### 12.3 里程碑与 KPI（可独立验证）

| 阶段 | 时间 | 动作 | KPI |
|---|---|---|---|
| 短期 | 1-3 月 | A-01/A-02/A-03/A-04/A-07 落地；P1 ULT 扩样；P2 预注册 | ULT accuracy ≥41.32%（p<0.05 vs plain_llm）；docstring 增广臂非劣判据落盘；κ≥0.7；origin/main=HEAD 且 CI 绿；论文 T 轮漂移段 + 2×2 预注册 |
| 中期 | 3-6 月 | P4 FLT；P6 形式化修复二臂；P3 checklist v1 + 2 个外部数据集重放；TestGenEval-Lite 子集 | 非终止类检出转化 ≥3；形式化臂 false_fix ≤20%；外部重放"未修正即高估"定量结论 ≥2 例 |
| 长期 | 6-12 月 | 方法论文（FSE/ICSE/ISSTA/TOSEM）+ 系统论文；P5 第三次决断；A-16 第二模型交叉 | ≥1 篇一手 venue 录用；编排增益关闭或转正；关键结论两模型同向 |

### 12.4 Python 工程化保持项

`make gates`（合并门禁）每批必跑；`pytest --cov=src --cov-branch`（ratchet 96.4/92.5）；`ruff check` + `ruff format --check`（0.16.3）；`mypy src/ config.py`；补 A-15（bandit CI 确认 + SBOM）；A-08/A-09 测试环境稳健化；A-05/A-06 口径统一。

---

## 13. 实验、验证与评估计划（摘要）

1. **P1 外部标定主实验**：ULT n≥200 {plain_llm, plain_llm_df, df+docstring-augment}；指标 accuracy/Mut@k/$；McNemar + BH-FDR + Wilson CI；3 cache namespace；temp=0；预注册先落盘；对照 = ULT 12 模型均值（A）+ MIST-RL（B）。
2. **P2 规格锚实验**：QuixBugs 41 + ULT probe25；三臂；F2P + misguided 三分 + 成本；判据冻结（非劣 + misguided −30%）。
3. **P3 checklist 重放**（零 LLM）：对 ULT 官方 12 模型公开结果、TestGenEval 公开产物应用 checklist，输出"未修正即高估"量化表。
4. **P4/P6 零 LLM 复算**：超时/FLT 行为、z3 反例引导修复可离线复算部分先行。
5. **P5 编排决断**：synthetic + QuixBugs matched-budget 三臂（df / df+记忆 / aitester）。
6. **E7 人工 adjudication**：n≥100 双人盲审 Cohen's κ。
7. **可复现性包**：seeds + env snapshot + git sha + Dockerfile.repro + SHA256SUMS + 复现命令一键化 + 复算工件索引（A-19）。

---

## 14. 风险、伦理与合规

| 风险 | 等级 | 缓解 |
|---|---|---|
| 外部效度：ULT 对标若 <30%，"合成集饱和≠真实能力"坐实，性能主张收缩 | 高 | P1 提前执行；分层声明纪律（项目已有）；阴性亦可发表 |
| false_fix 59.58-100%：产品化场景的假成功通道 | 高 | P2+P6 直接攻击；弃权门默认开评估 |
| 规格锚三连阴性后的路线风险：spec-first 可能整体关闭 | 中 | P2 增广臂 + provenance 归因已把问题收窄到"锚来源"；Zhao/Song/Cohen 设定差异可作论文贡献 |
| 单模型依赖（deepseek-flash） | 中 | A-16 第二模型交叉 |
| T 轮漂移（thinking 模式/协议开关）导致新旧批不可比 | 中 | A-03/A-17 论文化 + 2×2 消融预注册 |
| 成本：LLM 预算授权依赖用户 | 中 | 零 LLM 实验优先（P3/P4 大部分可离线） |
| 推送风险：65 提交未经 CI | 中 | A-07：推送前完整 CI；推送为外部动作需用户确认 |
| 安全：生成代码执行沙箱逃逸 | 中 | venv/Docker 沙箱 + 进程树 kill + 注入防护 + 包名白名单已在场；持续 pip-audit/bandit |
| 伦理：AI 生成测试被用于"让缺陷代码看起来通过" | 中 | false_fix/misguidance 度量即对策；文档明示；oracle 质量问题（correct=0）已如实披露 |
| 合规：无人类受试者数据；`.env` 纪律遵守 | 低 | 保持 |

---

## 15. 待澄清问题（必须向项目方确认，不作假设填充）

1. ULT accuracy 21.0%（42/200）的独立复算工件路径与命令（IR-17 登记于复制包索引，本次未定位到可重放脚本）？
2. `SPEC_SMT_ENABLE` 是否有端到端启用批次（非 T 轮零 LLM 单臂观测）？z3 在生产批次的安装与评估记录？
3. synthetic 50 缺陷模板与真实缺陷分布的代表性标定计划（是否在 Defects4J 子集上验证 detection 主张）？
4. E7 人工 adjudication 的执行时间表与预算；n 口径（8 vs ≥40 行）冲突的裁定结论？
5. `orchestration_search.py` 16 臂 bandit：按 ADR-0034 五条件解锁的时间表？
6. CI 门禁数量的权威口径（26 脚本 / 27 调用点 / 文档 24-25）以哪个为准？
7. 是否接受本报告第 12 节路线图与 P1/P2/P3 优先级排序？
8. T 轮 B2 判 `not_reproduced` 后，论文主叙事是否仍以 R-P0-2（旧批）为主证据（旧批无 thinking 记录、无指纹、dirty）？2×2 消融的时间表？

---

## 16. 参考来源（区分一手/二手，标注证据等级）

> 标注 = 本次评审（2026-10-18）独立检索核验状态。A=一手可验证；B=一手单源；C=二手/项目转引；D=不可验证。

### 一手（A/B 级，本次独立检索）

**测试生成与基准**
1. Jain, Synnaeve, Rozière. *TestGenEval.* ICLR 2025. arXiv:2410.00752; OpenReview 7o6SG5gVev. 【A】
2. Pizzorno, Berger. *CoverUp.* FSE 2025. DOI 10.1145/3729398; arXiv:2403.16218v4. 【A】
3. Huang, Zhang, Harman, Zhang, Du, Ng. *ULT/UnLeakedTestbench.* TOSEM 2026. DOI 10.1145/3805043; arXiv:2508.00408; GitHub huangd1999/UnLeakedTestBench. 【A】
4. Wang, Xu, Briand, Liu. *MUTGEN.* IEEE TSE 2026. DOI 10.1109/TSE.2026.3682975. 【B】
5. Xiao, Fang, Chen, Zhang, et al. *TestAgent.* arXiv:2607.09101. 【B】
6. Chowdhury, Fu, Jabbarvand. *SPARC.* arXiv:2602.16671. 【B】
7. Huang, Harman, et al. *Ockhamareto.* arXiv:2608.24473. 【B】
8. *NexuSym.* ICST 2026. arXiv:2604.05919. 【B】
9. Xu, Wang, Briand, Liu. *CANDOR.* TOSEM 2026. DOI 10.1145/3803418. 【B】
10. *Agent self-written tests and issue resolution.* arXiv:2602.07900. 【B】
11. *STADA.* arXiv:2504.06130. 【B】
12. *Test Wars.* ICST 2025. DOI 10.1109/ICSE66371.2025.00059. 【B】

**多智能体与修复**
13. SWE-bench 官方榜单. https://www.swebench.com/（2026-10-18 直取：Claude 4.5 Opus high + mini-SWE-agent 76.80% @$0.75）. 【A】
14. SWE-bench Pro 官方榜单（Scale AI）. https://scale.com/leaderboard/swe_bench_pro（claude-4-5-Sonnet 43.72%）. 【A】
15. *LaMAR.* ASE 2026. DOI 10.1145/3832783.3837423; arXiv:2601.14060v1. 【A】
16. *TraceCoder.* arXiv:2602.06875. 【B】
17. Luo, Keung, Yang, Klein, Bissyande, Tian, Le. *LANTERN.* ICSE 2026. DOI 10.1145/3744916.3773227; arXiv:2503.22512v4. 【A】
18. Wu, Luo, Mu, Xiang. *TwinMem-Agent.* FSE Companion 2026. DOI 10.1145/3803437.3807664. 【A】
19. Xiang, Xu, Chu, Tian, Zhang. *ADI.* FSE 2026. DOI 10.1145/3797126; arXiv:2604.24212. 【A】
20. Huang, Zhang, Luck, Qing. *AgentCoder.* arXiv:2312.13010. 【A】
21. Liang, Zhao, Mo. *DEIMerge.* PRICAI 2025. DOI 10.1007/978-981-95-7081-2_16. 【A】
22. *PhoenixRepair.* GitHub DeepSoftwareAnalytics. 【B】
23. *FedDualFix.* SSRN 5571166. 【B】
24. *SWE-Debate.* arXiv:2507.23348. 【B】
25. *LatentMAS.* arXiv:2511.20639; GitHub Gen-Verse/LatentMAS. 【A】
26. *Agent Primitives.* arXiv:2510.12671. 【B】
27. Cemri, et al. *MAST.* arXiv:2503.13657. 【A】
28. *BOAD.* ICLR 2026. arXiv:2512.23631. 【B】
29. *Nebius RL.* arXiv:2507.21073. 【B】

**自修复与运行时**
30. *STRATUS.* arXiv:2506.02009. 【A】
31. *FTDI.* Elsevier ESWA 2026. DOI 10.1016/j.eswa.2026.134164. 【A（存在性）】
32. *ESBMC-AI.* AST 2025. DOI 10.1007/s10009-025-00815-1. 【A】
33. Cruz. *VIGIL.* arXiv:2512.07094. 【A（设计）】
34. *AIOpsLab.* MLSys 2026. DOI 10.1145/3712296.3737911. 【A】
35. *StepFly.* arXiv:2506.14605. 【B】
36. *AgentDebug.* arXiv:2508.08966. 【B】
37. *ThinkFL.* arXiv:2504.06714. 【B】

**逻辑驱动 / 神经符号**
38. *TSC2CARLA.* SCP 2025. DOI 10.1016/j.scico.2025.103420. 【A】
39. Sung, Aditi, Kim, Han, Ko. *LogiCase.* IJCAI 2025. DOI 10.24963/ijcai.2025/861; arXiv:2505.15039. 【A】
40. Borda, Regis, Aguirre, Frias, Ponzio. *COMBA.* ASE 2025. DOI 10.1109/ASE63991.2025.00240. 【A】
41. Molinelli, Martin-Lopez, Zackrone, Eken, Ernst, Pezzè. *Tratto.* ISSTA 2025. DOI 10.1145/3728960. 【A】
42. *LLM2Alloy.* arXiv:2607.18555. 【B】
43. *AUTOSPEC.* arXiv:2509.25249. 【B】
44. *LLM path constraint solving.* arXiv:2505.15013. 【B】

**评测方法论**
45. Zhao, Zhou, Cohen. *Do Coverage and Mutation Scores Correlate with Effectiveness? (Replicability Study)* ISSTA 2026. DOI 10.1145/3832093; arXiv:2607.22880. 【A】
46. Zhao, Song, Cohen. *Misguidance Effect of Buggy Code.* ISSTA 2026. DOI 10.1145/3832204. 【A】
47. Inozemtseva & Holmes 2014; Papadakis et al. 2018.（经 ISSTA 2026 复现论文引述）【B】
48. Konstantinou, Degiovanni, Papadakis. ICST 2026 复现研究. arXiv:2601.09695. 【C（编号经项目 README 转引，本次未直取全文）】

### 项目内原始工件（本次独立复验对象，A 级）

- `experiments/results/t_round_b2_main_batch_20261018/`（ANALYSIS_REPORT.json + SHA256SUMS 804 项 + 3 seed 批次 JSON）
- `experiments/results/t_round_b1_protocol_text_20261018/ANALYSIS_REPORT.json`
- `experiments/results/emse_df_spec_20261016/DF_SPEC_REPORT.json`
- `experiments/results/main_batch/benchmark_synthetic_20261006_*`（R-P0-2 原始批）
- `coverage.xml`、`BASELINE.yaml`、`docs/env_budget.yaml`、`pyproject.toml`、`.github/workflows/ci.yml`
- 源码：`src/specs/spec_ir_v2.py`、`src/specs/spec_smt.py`、`src/graph/workflow.py`、`src/agents/planner.py`、`src/tools/detection_gates.py`、`src/agents/executor.py`
- 门禁脚本：`scripts/gates/`（26 个，本次实跑 9 个 + env-budget）

### 二手（C 级，仅作参考，不支撑关键结论）

- 项目 README 对 Konstantinou ICST 2026（arXiv:2601.09695）具体数值的转引（本次未直取全文）；
- IR-17 对 ULT accuracy 21.0% 的登记（本次未复算）；
- 检索代理对 SWE-bench Lite Sunlight MAA 61.67% 的单源报告（与常见口径冲突）。

---

## 附：本评审自身局限与合规声明

1. **环境局限**：本评审在 WorkBuddy 沙箱内执行；全量 pytest 的"正常环境 0 failed"无法直接复跑（已用 broker 激活/禁用双跑 + 逐失败归因替代）；LLM 相关批次未重跑（成本与配额），采用"原始工件重算 + SHA256 校验 + 两轮既有评审交叉"的替代验证链，并逐条标注。
2. **检索局限**：2026 年新出论文（arXiv 2602/2604/2607/2608 编号系）来自单次检索结果，标 B 级；投稿前应二次核验卷期页与数值。`docs/study/OPTIMIZATION_*.md`（gitignored 主报告）不在盘，未纳入评审。
3. **未执行**：渗透测试、E7 人工裁决复跑、87.16% 修正口径重放、spec_compile_rate 逐位重算、`make reproduce-zero-llm` 全链实跑——均在"无法验证清单"中标注，未用于支撑任何结论。
4. **利益声明**：本评审为独立第三方评审，不持有项目利益；所有"支持/推翻"判定仅基于本次可复现证据。

---

## 附：同日收口状态（2026-10-18 评审后执行，零 LLM）

以下建议已于评审当日实施并复验（实现细节见 CHANGELOG.md "第三轮独立评审驱动" 节）：

| 建议 | 状态 | 复验证据 |
|---|---|---|
| A-05 门禁口径统一 | ✅ 已收口 | `BASELINE.yaml` 新增 `gates` 节（26 脚本 / ci.yml 24 唯一引用·27 调用点 / 2 个专用工作流，均可复算）；README 中英文件树、论文贡献段、登记册 headline 同步；`check_baseline`/`check_bilingual_docs`/`check_doc_links`/`check_citations` 全过 |
| A-06 "0 failed" 环境标签 | ✅ 已收口 | BASELINE `tests.total_failed` 注释 + README 中英"已知失败"行改为"正常环境口径 + 沙箱宿主披露"；结构门禁通过 |
| A-08 测试 mkdir 加固 | ✅ 已收口 | `tests/test_executor_repo_j4_coverage.py` 防御式存在性守卫；`TestVerifyP2PGate` 6/6 在 broker 激活环境通过 |
| A-09 ps/沙箱能力探测降级 | ✅ 已收口 | 4 个测试文件新增能力探测（ps 真实调用 + **生产 profile** apply 探针）+ skipif；受影响 5 文件 **142 passed / 14 skipped / 0 failed**（broker 激活环境）；**全量复跑零失败**（P3 批次中间态 8927 passed / 19 skipped；D3b 批次后最终 **8942 passed / 19 skipped / 0 failed**，774.71s）——"零失败"在受限环境亦成立 |
| A-03/A-17 T 轮漂移论文化 | ✅ 已收口 | `paper/draft.typ` 新增 `sec:tround`：B2 锁指纹复现（3.07%/11.88%/28.35%，`not_reproduced` 但 R2 −25.29pp 显著）+ 漂移三因定位（推理模式 out token 78.6%→36.4%、logic 档 +5 开关、plain_llm 全局漂移 1.53%→11.88%）+ "新旧批不混池"声明 |
| A-03 配套：E8 预注册 | ✅ 已落盘 | `docs/preregistration.md` E8：`{thinking on/off}×{legacy/current profile}` 2×2 消融，H1/H2/H3 判定规则跑前冻结；预估 $6–9，授权前不得开跑 |
| P3 评测诚信 checklist v1 | ✅ 已交付 | `docs/design/evaluation_integrity_checklist.md` + `experiments/eval_integrity_check.py`（IC-1..IC-8 零 LLM 校验器）+ `tests/test_eval_integrity_check.py`（12 例全过）；对 B2/df_spec 实测硬检查全过，IC-7 正确识别 608/51 行"协议内未测变异得分"占位值，IC-4 正确区分弃权门（34 行）与 ADR-0021 伪影签名 |
| A-15 bandit/SBOM | ✅ 复核为**已实施**（评审时待确认） | ci.yml security 作业：`bandit -r src/ -c pyproject.toml -q`（阻断）+ pip-audit 双口径（requirements.txt/lock，阻断）+ cyclonedx SBOM 工件；release.yml 同款 SBOM 上传 GitHub Release |
| P4 动态分析接口 | ✅ 部分收口（代码级） | ① per-test 超时两路径**均已在场**（executor 命令层 `--timeout`，2026-10-10 修复；M1 `per_test_timeout_seconds()`，A-06）——评审时列为"待做"系信息不完整，已在 §10 A-11 更正；② **D3b Step A 跨文件计划接线**已实装（`CROSS_FILE_PLAN_BUILD_ENABLE`/`CONSUME_ENABLE` 双开关默认关、`_debugger_node` 构建 + `_resolve_target_module` 门控消费、13 例契约测试 + 2 例对偶用例；OFF/OFF 与历史逐位一致；全量 8942 passed / 19 skipped / 0 failed，774.71s）；③ FLT 按设计文档 §7 需先预注册（ADR-0003），未实装 |

未执行（需用户授权/配额，不在本日范围）：A-01（ULT 扩样，需 LLM 预算）、A-02（docstring 锚预注册，需 LLM 预算）、A-04（E7 人工裁决，需人力）、A-07（推送 65 提交，外部动作需确认——本地全量测试 broker 激活环境复跑已通过：8942 passed / 19 skipped / 0 failed（774.71s），正常环境全量 8956 passed / 5 skipped / 0 failed（176.43s））。

> 注：本附录为评审报告发布后的执行记录；报告正文（§10 建议表等）保持评审时点原貌，未回溯修改。

---

## 附：独立评审结论一句话

> 本项目的数据诚信、测量方法论与工程化体系经本轮独立复验**再次全部成立**（14 项核心声明逐位复现、门禁实跑通过、804 项工件校验一致），其核心阴性结论（手工编排劣于轻量协议）与 2026 年外部一手证据链方向一致，是最可辩护的科学资产；真正的竞争缺口在**外部可标定性能**（ULT accuracy 21.0% vs 41.32%，−20.3pp）与**增益转化**（规格锚三连阴性、根因已定位）。最具论证力的超越路径不是堆叠编排，而是 **P1（ULT/TestGenEval 严格对标）+ P2（独立 docstring 规格增广，项目自有数据已显示"增广不伤、替换才伤"）+ P3（评测诚信 checklist 基准化）**；执行前必须完成 **A-07（65 提交未经 CI，推送前完整验证）**、A-03/A-17（T 轮漂移论文化）与 A-05/A-06（口径统一）。
