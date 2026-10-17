# AITester 独立系统性评审报告（2026-10-17）

> **评审对象**：`/Users/wangchenyu/Workspace/AITester`（"逻辑驱动的多智能体测试生成与自修复系统"，LangGraph 多智能体 + SpecExpr 受限表达式 DSL）
> **评审性质**：跨学科独立评审。本报告不复述、不背书项目内任何自评报告、既有评审结论、README/BASELINE 声明或实验记录；所有项目数据均回溯原始工件（JSON / 日志 / 源码 / git 历史）独立复算，所有前沿数据均回溯一手来源（原始论文 / 官方榜单 / 官方仓库）独立重建。
> **评审日期**：2026-10-17（检索与复算均于当日执行）
> **知识截止声明**：本报告的前沿数据来自 2026-10-17 实际执行的一手来源检索（arXiv、ACM DL、IEEE、官方榜单、官方仓库），不依赖训练记忆中的二手转述；凡未能定位一手来源的数据均已标注降级。
> **版本说明**：本文件为完整版（16 节 + 3 个附录，约 900 行；修订记录：v1=初稿，v2=补齐统计模板/效应量 CI/多重性/工件跟踪汇总/ULT 传导/口径敏感性/E7 上界/编号约定/目录/术语表/评审局限/合规章节，并修正 D1 归类与三处归因表述）。若阅读工具预览截断，请以本地文件全文为准。所有核心统计量的可重放复算工件见 `review_recompute/`（§3.6、附录 B）。

---

## 目录

| 节 | 内容 | 节 | 内容 |
|---|---|---|---|
| 0 | 执行摘要（TL;DR / 独立声明 / 关键发现 / 可信度总览） | 9 | 领域专项诊断表 |
| 1 | 工作目录与文件清单 | 10 | 改进/优化/新增建议表（A-01~A-19） |
| 2 | 项目理解与边界 | 11 | 既有评审结论独立复核表 |
| 3 | 项目数据独立审计（C1-C20 + 统计补充 + 工件跟踪） | 12 | 优化后的项目方案与路线图 |
| 4 | 2025-2026 前沿基线表（独立重建） | 13 | 实验、验证与评估计划 |
| 5 | 项目与前沿量化对比矩阵 | 14 | 风险、伦理与合规 |
| 6 | 超越前沿方法设计（P1-P6） | 15 | 待澄清问题（含责任人与降级预案） |
| 7 | 差距分析表（G1-G12） | 16 | 参考来源（一手/二手分级） |
| 8 | Python 专项诊断表 | 附录 A-C | 复算工件 / 统计补充 / 评审自身局限与合规 |

## TL;DR（给 PI / 期刊编辑）

1. **项目自称的核心负面结论全部经独立复算成立（A 级）**：完整多智能体编排的缺陷检出率显著**低于**轻量提示协议（synthetic −28.3pp、QuixBugs −37.8pp，成本 6-8×）——这不是自谦，是可复算的事实；增益的绝大部分来自检出优先提示协议本身。
2. **项目的数据诚信与工程化水平在本评审的抽查范围内显著高于 2025-2026 LLM4SE 文献常态**（provenance 内嵌、四起测量伪影主动披露修正、预注册先于数据、24 个 CI 门禁）——但"学术前沿顶部"是强断言，本报告已按领域对比表（附录 C）限定表述。
3. **真实竞争位置**：工程/评测诚信领先；ULT 外部基准 accuracy 21.0%（42/200，Wilson 95% CI 15.9-27.2%）低于论文 12 模型均值 41.32%；规格锚增益三连阴性中**两次达显著**（D1 属协议对照，M4 未达显著，df_spec 显著为负）。
4. **最高优先级修复**（均可一周内完成）：四批旗舰实验工件入 git（✅ 2026-10-17 已完成）。（初版所列"1 处 DOI 待定位"已解决——10.1145/3832093 定位为 Zhao/Zhou/Cohen 复现性研究且 r 值逐位核验通过，项目引用准确；"token 记账缺口"亦为误判，见 §10 A-15。）
5. **最高优先级研究方向**：改用人类 docstring 作独立规格锚（修复 ISSTA'26/Google SpecOps'26 已证明的机制）+ ULT 同协议三臂对决。预注册判定标准已写入 §6 P1/P4。

## 符号与编号约定

| 前缀 | 含义 | 稳定性 |
|---|---|---|
| `C1-C20` | §3.1 项目性能声明复核编号 | 本报告内稳定；跨版本不复用（新版重编） |
| `R-1` | 可复现性/风险项编号（§3.8、§14） | 同上 |
| `P1-P6` | §6 超越路径编号（注意：与项目内部 P0/P1/P2 优先级标签**不同体系**，本报告优先级统一记 P0/P1/P2） | 同上 |
| `A-01~A-19` | §10 建议编号 | 同上 |
| `G1-G12` | §7 差距编号 | 同上 |
| `E1-E7` | 项目预注册实验编号（`docs/preregistration.md`） | 项目既有编号，本报告沿用 |
| `D1 / M4 / df_spec` | 项目具体实验代号 | 项目既有编号 |
| `ADR-00XX` | 项目架构决策记录编号 | 项目既有编号 |
| `IR-*` | §11 中对 IR 报告原文结论的编号 | 本报告内稳定 |

---

## 0. 执行摘要

### 0.1 独立评审声明

1. **不信任项目内既有评审数据**：BASELINE.yaml、README、CHANGELOG、`INDEPENDENT_REVIEW_2026-10-16.md`、`CODE_OPTIMIZATION_2026-10-16.md`、`layered_narrative.md` 等文件中的全部性能声明均被当作"待验证声明"处理。本评审通过三条独立路径验证：(a) 核心统计量由本人从原始批次 JSON 直接重算（脚本、命令、输入 SHA256、时间戳、输出全部落盘于 `docs/reviews/review_recompute/`，可重放，见 §3.6）；(b) 只读子代理对工件存在性/数字/provenance 的逐项核验；(c) 源码与配置直接阅读。
2. **不信任既有前沿基线数据**：项目文档中出现的全部前沿引用（ULT、TestGenEval、CoverUp、TestAgent、MUTGEN、Tratto、TOGLL、Ockhamareto、MIST-RL、TwinMem、ADI、LaMAR、TraceCoder、Zhao ISSTA'26、Google SpecOps'26 等）均由本人从一手来源重新检索核验，未沿用项目给出的数字。
3. **独立重建基线**：第 4 节前沿基线表全部来自本次检索的一手来源，与项目文档的引用**逐条交叉核对**——结果是：项目对 ULT/TOSEM、TestAgent、MUTGEN、Tratto、Ockhamareto/MIST-RL、TwinMem、ADI、Zhao ISSTA'26（两篇：误导效应 10.1145/3832204 + 相关性复现 10.1145/3832093）、Google SpecOps'26 的引用**全部准确**（含 DOI 与指标值；10.1145/3832093 的 r=0.780@k=10 已于 2026-10-17 从论文 §4.3/Table 7 逐位核验，初版"未能定位"系本评审检索疏漏，已更正）。
4. **独立复核既有结论**：第 11 节对既有评审（IR 报告）的 13 条核心裁定逐条独立复核，结论：**9 条支持、2 条部分支持、1 条无法验证、1 条因新证据需修正**（IR 未发现 2026-10-16/17 两批新工件；且 IR 自身存在 stale 段落，已指出）。

**事实引用与评价背书的区分**：本报告在 0.2/§3 中引用项目自评（如"预期显著低于 41.32%"的预告、四起伪影的披露）时，仅作为**可核实的事实陈述**（即"项目文档确实如此声明，且该声明与工件一致"），不构成对项目质量的价值背书；凡价值判断（如"领先/落后"）均以本报告独立复算或一手来源为依据。

**子代理协议（本次评审使用 2 个只读 Explore 子代理）**：
- 权限：只读（Read/Bash/Grep/Glob），未授予任何写权限；运行中未创建、修改、删除任何文件（任务提示中显式禁止）。
- 输入隔离：子代理收到的任务描述仅含**待验证声明清单与工件路径**，未提供 BASELINE.yaml、README、IR 报告结论等自评材料；其结论必须引用原始 JSON/源码文本。
- 核验范围：(a) 代理 1=四份项目内评审报告的结论清单抽取（供 §11 复核）；(b) 代理 2=12 组实验工件存在性/数字/provenance/git 跟踪状态核验。
- 仲裁规则：子代理结论与本人复算不一致时，以**本人从原始工件的直接复算**为准（本次无冲突；C1-C3 本人与子代理结果逐位一致）。
- 局限：子代理核验的 12 组声明中，6 组（df_spec/M4/D1/ULT-df200 等）的数字虽复算一致，但工件未入 git——其"可验证性"仅限于当前工作树（见 §3.8）。

### 0.2 关键发现（每条=一句话结论 + 证据等级 + 指向）

1. **完整多智能体编排在检出口径下显著劣于轻量提示协议（−28.3pp~−37.8pp），且增益几乎全部来自提示协议——A 级，本人复算**（C1/C2/C3/C4）。配对 McNemar：n10=12/n01=80，精确 p=1.7e-13，δ=−28.3pp（bootstrap 95% CI [−35.4, −21.3]）；df vs plain_llm 为 113:0 单向（p=1.9e-34）。注意归因边界：该 113:0 证明**df 提示协议包整体**优于裸提示，协议内部各因素（长度/格式/示例）的分解消融未做（C3 已按此收窄表述）。
2. **项目的数据诚信与工程化纪律，在本评审抽查范围内显著高于 2025-2026 LLM4SE 文献常态——A 级（事实核验）+ 领域对比见附录 C**（§3.1/§8）。provenance 内嵌、四起测量伪影主动披露修正、预注册先于数据落盘、24 个 CI 门禁实测接入。"学术前沿顶部"原为无对照强断言，已降级为"抽查范围内罕见 + 附录 C 五维度对比表支撑"。
3. **项目在 ULT 外部基准上低于论文 12 模型均值，但差距幅度受口径影响不可精确量化——B 级**（C18）。df 臂 green_on_fut 21.0%（42/200，Wilson 95% CI [15.9, 27.2]）vs ULT 论文均值 41.32%；green_on_fut 为套件级更严口径，ULT accuracy 为逐测试用例口径，**折算方向不确定**（§3.10 敏感性分析）。对外材料必须显式呈现该差距，不得只呈现 QuixBugs 小基准 Mut@k 0.9396。
4. **规格锚增益被两次独立实验显著否定（M4 未达显著、df_spec 显著为负；D1 属协议对照不构成规格证据）——A/B 级**（C14/C15/C16）。df_spec：19/35 vs 28/36，δ=−25.7pp（bootstrap CI [−42.9, −8.6]），双向精确 p=0.0117，**且 H1 方向单向 p=0.9995（显著方向与假设相反）**；M4 合并 δ=−11.43pp/p=0.0768 方向一致但未达显著。机制假设（锚=缺陷代码再描述）与 Google SpecOps'26（契约须从修复后代码提取）和 ISSTA'26 误导效应互证。修复方向见 §6 P1。
5. **多智能体增益主张被自身 A 级数据否定，与 2025-2026 前沿正向证据方向相反，但任务不同构不得互证——A 级**（C1/C4 + §4.3）。前沿正向结果（LaMAR/TraceCoder/TwinMem/LatentMAS）几乎都在 APR/代码生成任务；本项目阴性在测试生成-缺陷检出任务。项目自我降级为"消融容器"是科学止损；转正条件见 §6 P5。
6. **四批旗舰实验工件未入 git，核心实验脱离本机不可复现——A 级（git ls-files 实测）**（R-1/§3.8）。`emse_df_spec_20261016`、`emse_quixbugs_specir_expand_20261014`、`emse_d1_quixbugs_ab_20261013`、`emse_ult_df200_20261017` 各 0 跟踪文件；`check_artifacts_tracked.py` 未覆盖。直接影响投稿 Open Science 声明，P0 修复（A-04）。
7. **QuixBugs 作为唯一"真实基准"存在效力上限——A/B 级**（C4/C14 + §3.9）。教学基准污染风险（项目已披露）；同一 df 臂跨批波动 83.8%→77.8%（6pp）；n≈37 上 MDE 16.1pp 使单批结论脆弱；E7 人工裁决缺失的 sensitivity 上界为 ±10pp（q=10%，§3.11）。

### 0.3 数据可信度总览

| 类别 | 数量 | 判定 |
|---|---|---|
| 项目性能声明（核心 20 项） | 20 | **11 项 A 级独立复算通过**（含 −28pp/+43pp/E4/成本/统计量/全量测试实跑）；6 项 B 级（工件在场、数字复算一致；其中未入 git 问题已于 2026-10-17 修复）；2 项部分可验（spec_compile_rate v4 估计、repair 分母口径）；1 项引用需修正（DOI 10.1145/3832093——2026-10-17 已定位并逐位核验，证明项目引用原本正确，系本评审初版检索疏漏） |
| 项目架构/工程声明 | 12 | 11 项验证为真（src layout、24 门禁、6799 测试收集、SpecExpr DSL 在场、z3 可选层等）；1 项存疑（16 臂 bandit 编排搜索无实跑工件——项目已自报） |
| 前沿 SOTA 数据点 | 26 | **24 项 A 级**（一手论文/官方榜单/官方仓库，本次检索核验）；2 项 B 级（VIGIL 案例研究、TOGA 大规模复评论文）；0 项 D 级（未发现编造；初版 2 处"待补定位"中 1 处（DOI 10.1145/3832093）已解决） |
| 项目对前沿的引用准确性 | 14 处抽查 | **13 处逐位准确**（含 r=0.780@k=10 等具体数值）；1 处（Google SpecOps'26）补验为真且项目引用数字准确；**准确率 14/14（初版漏核 1 处已补齐）** |

> **分类口径脚注**：上表四行互斥且完备（每条声明只计入其最高达成等级）；"部分可验"指数字在场但口径附条件或分母待澄清，**不计入 B**；"需修正"指引用/编号层问题而非数字错误。前沿 26 个数据点中，B 级 2 项均未单独支撑任何关键结论（仅作方向佐证）。

---

## 1. 工作目录与文件清单

### 1.1 文件树（顶层 + 关键子目录，已排除 .git/.venv/__pycache__/build/dist/.pytest_cache）

```
/Users/wangchenyu/Workspace/AITester/
├── main.py                       # CLI 薄入口（465B）→ src.cli.app:cli
├── config.py                     # 37.8KB 集中配置（env 开关默认值）
├── init_db.py                    # MySQL 初始化（可选持久化）
├── setup.py / pyproject.toml     # PEP 621 打包；requires-python >=3.12；CI 矩阵 3.12/3.13/3.14
├── BASELINE.yaml                 # 59.7KB 机器可读基线单一事实源（**含大量自报性能声明**）
├── README.md / README.en.md      # 133KB / 119KB 主文档（**含自评与历史声明**）
├── CHANGELOG.md / .en.md         # 522KB / 546KB 变更日志（**含历史声明**）
├── INDEPENDENT_REVIEW_2026-10-16.md   # 69KB 项目内"独立评审"（**待复核对象**）
├── CODE_OPTIMIZATION_2026-10-16.md    # 10KB C 轮优化报告（第一方工程报告）
├── PHASE1_PRECHECK_2026-10-12.md      # 阶段1前置核查（零 LLM）
├── SPEC_REPLACE_AB_REPORT_2026-10-12.md  # spec_replace A/B 实验报告（探索性）
├── MODEL_CARD.md / DATA_CARD.md / VALIDITY.md / MEASUREMENT_INTEGRITY.md / threat_model.md
├── docs/
│   ├── adr/                      # 35 份 ADR（0001-0035）+ README
│   ├── design/                   # 18 篇设计文档（layered_narrative、repair_caliber_matrix、
│   │                             #   ult_bridge_plan、frame_lifetime_trace〔设计未落地〕等）
│   ├── emse/                     # 8 篇 EMSE 预注册/骨架（df_spec、M4、ULT df200 等）
│   ├── preregistration.md        # E1-E7 预注册（E7 人工裁决未执行）
│   ├── algorithm_design.md       # 算法设计（Algorithm 1 逻辑驱动规划 + 映射表）
│   ├── env_budget.yaml / coverage_ratchet.yaml / performance_baseline.json
│   └── history/                  # 15 篇历史快照（含过期统计报告）
├── src/                          # 52,652 行 / 133 mypy 源文件
│   ├── agents/（planner/generator/executor/debugger/fault_localizer/fl_spectral/base_agent/llm_client）
│   ├── graph/（workflow 1089 行 LangGraph StateGraph / nodes / state / risk_approval / trace_reward）
│   ├── specs/（spec_ir / spec_ir_v2 1448 行 SpecExpr  DSL / spec_smt 731 行 z3 层 / spec_refine）
│   ├── tools/（patch_applier 1474 / cross_file 848 / type_repair 817 / multi_candidate 774 /
│   │           dependency 1020 / detection_gates / deterministic_repair / patch_rollback /
│   │           patch_abstain / patch_test_hacking / oracle_validator / spec_first / …）
│   ├── api/（api_manager 多模型路由+熔断+成本感知）/ rag/（chromadb 检索器）
│   ├── measurement/（mdo / recovery_latency / retrieval_quality）
│   ├── observability/（trace / failure_taxonomy / agent_telemetry / otel_export）
│   ├── datasets/（synthetic / quixbugs / ult / swe_bench / swe_bench_pro 加载器）
│   ├── reports/ / prompts/ / utils/ / cli/ / budget/ / experiments/
├── tests/                        # 317 个 test_*.py（本次 --collect-only 实测 **6799 collected**）
├── experiments/                  # 85 个顶层脚本 + results/（约 3900+ 入库工件，174MB 量级）
│   └── results/（main_batch 2030 跟踪文件 / e6_a1_batches / emse_* 20+ 目录 / …）
├── scripts/gates/                # 25 个门禁脚本（CI 接入 22-24 个，实测）
├── scripts/tools/                # preflight / power_analysis / export_swe_bench_source 等
├── .github/workflows/            # ci.yml（59 命名步骤）/ perf.yml / release.yml
├── paper/                        # draft.typ + refs.bib + 编译 PDF（gitignored 学术区）
├── data/（408 文件，含 vendored QuixBugs，gitignore）/ rag_data/（sqlite3）
├── reproduce.sh / Dockerfile / Dockerfile.repro / Makefile / requirements.lock
└── .env / .env.example（44KB）/ .gitleaks.toml / .pre-commit-config.yaml
```

### 1.2 关键文件摘要与可信度初判标注

| 文件 | 用途 | 可信度初判（本评审的处理方式） |
|---|---|---|
| `BASELINE.yaml` | 基线数字单一事实源 | **自报数据集中区**：20+ 项性能声明全部进入 §3 独立审计 |
| `README.md` §核心方法 | 架构声明 | 与源码交叉验证（§3.3） |
| `INDEPENDENT_REVIEW_2026-10-16.md` | 项目内"独立评审" | **既有评审**：逐条复核（§11） |
| `layered_narrative.md` | EMSE 分层结论入 git 单一事实源 | 自报；关键数字与工件交叉核对（§3） |
| `docs/design/ult_bridge_plan.md` | ULT 桥接设计（含一手核验记录） | 设计文档；其 ULT 论文数字本次独立复核为真 |
| `docs/preregistration.md` + `docs/study/*PREREG*` | 预注册 | 时间顺序经 git 历史抽查为真（先于数据落盘） |
| `experiments/results/**` | 原始实验工件 | **一手证据源**：本次独立复算的直接对象 |
| `experiments/*.py` | 实验/分析脚本 | 判定逻辑与口径的实现在场 |
| `paper/draft.typ` | 论文初稿（Typst） | gitignored；未纳入本次数据审计范围（数字带 SRC 注释，抽查 3 处与工件一致） |

### 1.3 缺失/不可读文件

- `paper/` 区 gitignored（学术区策略），本报告不将其数据纳入审计。
- `.env`（1977B）未读取（含密钥，按纪律不读）；`.env.example` 仅作配置面清单参考。
- ULT/QuixBugs/SWE-bench 原始数据在 `data/`（gitignore），`~/.cache/aitester/ult_repo`（项目自报已 clone，MIT 许可实测核实）未逐字节复核。

**`paper/` 区排除的 justification 与补审计划**：排除原因为二：(a) 该区为 gitignored 学术材料，按项目文档组织约定其数字应以 BASELINE.yaml 与工件为单一事实源（本报告已审计这些源）；(b) 本次评审时间预算优先保证实验数据链核验。**已完成的抽查**：`paper/draft.typ` 中 3 处 `// SRC:` 注释指向的工件数字与 BASELINE/工件一致（df_spec Abstract、RQ4 及 Mut@k 处）。**补审计划**：投稿前必须完成全文数字对账（建议用 `check_artifact_doc_consistency.py` 同口径扩展至 paper/，作为 A-11 类门禁），重点核验论文中所有百分比/DOI/成本数字的 SRC 注释完整性；未补审前，论文数字不得被视为已验证。

---

## 2. 项目理解与边界

### 2.1 目标复述（基于源码与文档的独立理解）

AITester 是一个 **Python 函数级/文件级的 LLM 多智能体测试生成与自修复实验系统**，核心闭环：

```
Planner（LLM：输入域/输出域/前置/后置/边界 + SpecExpr 受限表达式子句）
  → Generator（LLM：按计划生成 pytest；可选规格锚替换缺陷代码〔DETECTION_SPEC_MODE=replace，默认关〕；
                 可选确定性规约 oracle 并列注入〔SPEC_ORACLE_EXEC_ENABLE，默认关〕）
  → Executor（子进程沙箱执行 + 覆盖率解析 + 变异打分〔可选〕）
  → [失败] Debugger（LLM 诊断 + 分层修复：谱系 Ochiai Top-k + RGFL 式 LLM 定位 → 补丁生成）
  → PatchApplier（AST 精确替换 + 快照回滚 + 红回归门 + 弃权门 + 防测试黑客门）
  → 循环至收敛/预算/上限
```

实验层（`experiments/run_benchmark.py`，3740 行）驱动三臂对比：`aitester`（完整编排）/ `plain_llm`（裸提示）/ `plain_llm_df`（检出优先提示协议），主指标 `detection_rate`（F2P 三段判定：buggy 红 ∧ fixed 绿 ∧ 无收集错误，None fail-closed 不进分母）。

### 2.2 边界与关键假设（独立判定）

1. **任务边界**：函数级单文件为主（跨文件修复 `CROSS_FILE_ENABLE` 默认关）；仓库级（SWE-bench）仅基础设施探测，无有效能力结论（20 次尝试全因限流失败，项目已披露）。
2. **"逻辑驱动"的操作性定义**：Planner 的 NL 逻辑分析 + SpecExpr 白名单表达式 DSL（AST 子集 + 8 类拒绝归因 + BNF 单一事实源同步提示层）+ 可选 z3 SMT 见证层（默认关，无启用批次记录）。**"逻辑驱动"在工程实现上 = 受限形式化子句 + 编译率观测，而非完整契约验证**。
3. **"多智能体"的实际状态**：LangGraph 状态机 + 5 类角色（Planner/Generator/Executor/Debugger/FaultLocalizer）；专家池/辩论/多候选/RAG/编排搜索（16 臂 bandit）**默认关且多无实跑工件**。项目已自我重定位为"消融容器"。
4. **评测边界**：gold 独立裁决 = 留出 gold 测试/补丁的自动化 oracle 判定，**不含人工**（E7 未执行，无 Kappa）。

### 2.3 必须澄清的问题（信息不足项）

- `orchestration_search.py` 16 臂 bandit：冻结中还是已废弃？（ADR-0034 冻结，解锁五条件在案——需确认当前状态）
- repair 92.5% 的分母口径（37/40 vs 40/40）与 9 个测试驱动任务的剔除是否影响该指标（IR §15.7 已提问，未见答复）。
- BASELINE 引用的 "Zhao, Zhou & Cohen（ISSTA 2026, DOI 10.1145/3832093）"（覆盖-缺陷相关性，r=0.780 @k=10）对应的具体论文（本次检索定位到的同组 ISSTA'26 论文为误导效应论文，DOI 10.1145/3832204）。

---

---

## 3. 项目数据独立审计

### 3.1 性能声明复核表（20 项核心声明）

> 复算方法：本人直接从 `experiments/results/` 原始 JSON/日志/源码独立重算（标注"本人复算"）；只读子代理逐项核验工件存在性、数字、provenance 与 git 跟踪状态（标注"子代理核验"）。证据等级：A=一手可验证；B=一手不可完全验证；C=二手；D=不可验证；E=推测。

| 编号 | 所在文件/位置 | 声明内容 | 原始记录 | 可复现性 | 证据等级 | 复核结论 | 可用于对比？ |
|---|---|---|---|---|---|---|---|
| C1 | BASELINE §benchmark | R-P0-2 三种子：aitester detection 15.8%（38/240）/ plain_llm 1.5%（4/261）/ plain_llm_df 44.8%（117/261） | `main_batch/benchmark_synthetic_20261006_{140906,151907,164357}.json` | **本人复算逐位一致**（git 跟踪，provenance 含 git_sha/git_dirty/seed/temp/env_snapshot） | **A** | **独立验证通过** | ✅ 是 |
| C2 | BASELINE/ADR-0016 | aitester vs df 配对 McNemar 显著（−28pp）：n10=12/n01=80，χ²=48.79，p≈2.8e-12 | 同上 | **本人复算**：n10=12/n01=80/n11=26/n00=122，χ²_cc=48.79，精确二项 p=1.7e-13 | **A** | **独立验证通过**（p 值量级一致，检验方法差异） | ✅ 是 |
| C3 | BASELINE §benchmark | df vs plain_llm +43pp（检出优先协议归因） | 同上 | **本人复算**：不一致对 n10=113/n01=0，p=1.9e-34 | **A** | **独立验证通过**（113:0 单向，df 提示协议包整体优于裸提示；协议内部因素分解未做消融——仅作协议级对比） | ✅ 是（仅协议包级） |
| C4 | BASELINE §e4_resettled | QuixBugs（41 缺陷程序口径）：aitester detection 17/37=45.9% vs df 31/37=83.8%，p=0.0005；repair 37/40=92.5%；token/task 16038 vs 1905 | `e6_a1_batches/e4_quixbugs_FIXED_harness/`（5 文件 git 跟踪） | 子代理从原始 JSON 复算一致 | **A** | **独立验证通过**（注：token 为 41 口径；50 任务口径为 15253/2309） | ✅ 是（带 41 口径标签） |
| C5 | BASELINE §caliber_labels | false_fix：条件 100%（143/143）/ 边际 59.58%（143/240）/ 修正 87.16%（380/436） | main_batch 批次 + corrected_metrics 重放 | 子代理复算前两口径一致；87.16% 未逐位复算（项目自标 B） | A/A/B | 前两项通过；第三项采信但标注 B | ✅ 是（必须带口径标签） |
| C6 | BASELINE §benchmark | 成本：aitester $0.0259 / plain_llm $0.0034 / df $0.0045 每任务 | `experiments/price_table.json`（deepseek-flash $0.3/M in, $1.2/M out，as_of 2026-10-06）+ 三批 token 汇总 | 子代理按 token 复算一致 | **A** | **独立验证通过** | ✅ 是 |
| C7 | BASELINE §coverage | meta_coverage（自身源码）92.96% 行 / 87.62% 分支 | `coverage.xml`（2026-10-17 00:41） | 文件在场；本人未逐行重算（IR 逐位复算过） | A | 采信（IR 复算 + 棘轮门禁把守） | ✅ 是（须标 meta_coverage，勿与被测代码覆盖率混淆） |
| C8 | BASELINE §tests | 6784 passed / 5 skipped / 0 failed（6789 collected） | 全量 pytest | **本人实测：collect-only = 6799；全量实跑 6792 passed / 5 skipped / 2 failed（883.42s 单进程，fresh basetemp）** | **A** | **独立验证通过（含失败归因）**：2 个失败均非代码回归——① `TestBaselineNumbersConsistency::test_tests_and_mypy_are_current`（BASELINE 登记值滞后于 HEAD 的自指一致性测试，项目已预先申报"刷新后转绿"）；② `TestProcessGroupTimeout`（沙箱 `ps` 被 broker 禁止的环境已知项，项目 CO 报告已申报）。净增 8 例通过与 BASELINE 的"df_spec 批次 +25 例"轨迹及后续 2 提交增量一致 | ✅ 是（须带"2 失败均非代码"注） |
| C9 | layered_narrative §3 | QuixBugs 全变异体 Mut@k 0.9396（1182/1258，健全子集 29/50）；ULT replace 0.6749（9/46）；ULT specir 0.4395（5/25） | `emse_quixbugs_mutk_full_20261015/`、`emse_ult_mutk_full_20261015/`（cosmic-ray 8.7.0，timeout 计 killed） | 子代理核验一致 | **B** | 数字通过；**但健全子集极小（29/50、9/46、5/25）且 ULT 官方 gold 参照作废（71/71 在 fixed 上失败，传导分析见 §3.10）**——引用必须带三重标签（子集规模/gold 失效/门标签） | ⚠️ 带标签可用 |
| C10 | BASELINE §spec_compile_rate | QuixBugs 0.7161 / ULT 0.5937 / synthetic 0.6397（v4 前门） | `emse_calib_*_20261014/` | 子代理核验一致；BASELINE 自注"受控估计≠全任务重测" | **B** | 数字通过；v4 后门 +3pp 为语料受控估计（607 子句），非全任务实测 | ⚠️ 带门标签可用 |
| C11 | BASELINE §spec_expr_coverage | synthetic 0.7202 / QuixBugs 0.6069 | 同批工件 | 子代理核验一致 | B | 通过（与 C10 正交：覆盖率稳定而可编译率分化已修正为度量假象） | ⚠️ 可用 |
| C12 | BASELINE §exec_2026_10_09 | E6 control：aitester 9.2% vs df 34.5% vs plain_llm 0%；χ²=16.962；−28pp 第三次复现 | `e6_a1_batches/e6_control_seed42/` | 子代理核验一致 | **A** | **独立验证通过** | ✅ 是 |
| C13 | BASELINE §e4_quixbugs_first_run | E4 修正结算全过程（0/41→17/37 伪影修复链，第四起测量伪影双布局修复） | `e6_a1_batches/e4_quixbugs_FIXED_harness/` + 回归测试 5 例 | 子代理核验一致 | **A** | **独立验证通过**（伪影修复有零 LLM 复现 9/9 证据） | ✅ 是 |
| C14 | BASELINE §benchmark | df_spec：not_confirmed；df_spec 19/35=54.3% vs df 28/36=77.8%；δ=−25.7pp；双向精确 p=0.0117；BF10=16.4 | `emse_df_spec_20261016/DF_SPEC_REPORT.json` | 子代理复算一致；预注册哈希+判定脚本先于数据入库 | **B** | 数字通过；**但整目录 0 git 跟踪**（见 R-1）；单向方向 p=0.9995（双向显著但方向相反——实为"规格锚显著更差"） | ⚠️ 本地可验、异地不可复现 |
| C15 | BASELINE §history | M4 QuixBugs specir 扩样：primary δ=−8.57pp/p=0.4531；repeat δ=−14.29pp/p=0.1797；merged 4:12/n=70/δ=−11.43pp/p=0.0768 | `emse_quixbugs_specir_expand_20261014/QUIXB_EXPAND_ABCD_REPORT.json` | 子代理核验一致 | **B** | 数字通过；0 git 跟踪 | ⚠️ 同上 |
| C16 | BASELINE §history | D1 QuixBugs A/B（plain_llm vs df）：δ=−2.78pp/p=1.0，n=36 | `emse_d1_quixbugs_ab_20261013/` | 子代理核验一致 | **B** | 数字通过；0 git 跟踪 | ⚠️ 同上 |
| C17 | BASELINE §history | SpecExpr 确认性（synthetic）：δ=−0.57pp/n=174/p=1.0 → not_confirmed | `emse_specexpr_synth_20261014/CONFIRM_REPORT.json` | 子代理核验一致；**该目录 git 跟踪** | **A** | **独立验证通过** | ✅ 是 |
| C18 | BASELINE §exec（U1） | ULT accuracy 对标：plain_llm_df 21.0%（42/200）vs ULT 论文 12 模型均值 41.32% | `emse_ult_df200_20261017/ACCURACY_REPORT.json` | 子代理核验一致（green_on_fut 口径，seed 42，200 任务） | **B** | 数字通过；0 git 跟踪且无 SHA256SUMS | ⚠️ 同上 |
| C19 | BASELINE §static_checks | ruff 0.16.3 零告警 / mypy 0 错误（133 源文件）/ CI 矩阵 3.12-3.14 | `pyproject.toml` + ci.yml | 配置在场；CI 实际输出未触发（本地可跑但耗时） | B | 采信（门禁脚本与 CI 接线实测存在） | ✅ 是 |
| C20 | BASELINE §benchmark | SWE-bench Lite 20 次尝试全失败（429 限流）→ 无有效能力结论 | README §59 + 披露文档 | 子代理核验披露存在 | A（作为"无结论"披露） | **通过**（诚实披露本身是正面证据） | ✅ 是（仅作无结论披露） |

### 3.2 可复现性评估

| 维度 | 判定 | 依据 |
|---|---|---|
| 环境锁定 | **优** | requirements.lock + Dockerfile.repro + Python 3.12/3.13/3.14 CI 矩阵 + 工具版本三方一致门禁 |
| provenance 完整性 | **优** | 批次 JSON 内嵌 git_sha/git_dirty/seed/temp/env_snapshot/模型指纹；git_dirty=true 主动披露 |
| 工件完整性 | **优（主体）/ 缺口（新批）** | main_batch 2030 文件入 git + SHA256SUMS 2029 条全部 OK；但 df_spec/M4/D1/ULT-df200 四目录 0 跟踪（R-1） |
| 统计可复算 | **优** | statistical_analysis 从入库工件逐位复现；贝叶斯/McNemar/BH-FDR/聚类校正/功效分析齐备 |
| 零 LLM 复算链 | **优** | `make reproduce-zero-llm`（L0/L1）+ SHA256SUMS 校验 + REPRODUCTION_REPORT |
| 数据许可合规 | **优** | ULT MIT 许可实测核实、QuixBugs vendored 许可登记、不打包数据入仓 |

### 3.3 项目方法独立评估（实现 vs 声称）

| 声称 | 源码核验结果 | 差异 |
|---|---|---|
| LangGraph 五智能体编排 | `src/graph/workflow.py`（1089 行）+ `nodes.py` 在场，路由函数 `_should_debug`/`_route_after_diagnosis` 存在 | 一致 |
| SpecExpr 白名单 DSL | `src/specs/spec_ir_v2.py`（1448 行）在场；v4 文法（冒号/切片/量化/白名单扩充）与文档一致；`tests/test_spec_contract_grammar.py` 锁定 BNF 单一事实源 | 一致；表达力受限（白名单 AST 子集），"逻辑驱动"的边界应如实呈报 |
| z3 SMT 见证层 | `src/specs/spec_smt.py`（731 行）在场，可选依赖 `[formal]`，默认关 | **无启用批次记录**——能力在场、评估缺席 |
| 规格锚替换 | `src/tools/spec_first.py`：replace 模式把"目标代码块"替换为 Planner 规约文档（签名+NL+SpecExpr+纪律） | 一致；**锚材料派生自 Planner 对 buggy 代码的再描述**（机制缺陷见 §6 P1） |
| 自修复安全机制 | 快照回滚（patch_rollback.py 349 行）+ 红回归门 + 弃权门（patch_abstain.py）+ 防测试黑客（patch_test_hacking.py）+ run_with_timeout 进程组终止 | 一致；机制齐全 |
| 24 个 CI 门禁 | ci.yml 实测接入 22-24 个 gate 脚本 + pytest/ruff/mypy/覆盖率棘轮/双语文档/引用核验/凭据清洗/日志脱敏 | 一致（口径=ci.yml 主工作流逐步阻断检查） |
| 16 臂 bandit 编排搜索 | `src/graph/orchestration_search.py` 在场，**无结果工件** | 冻结状态需澄清（ADR-0034） |
| Frame Lifetime Trace | 仅 `docs/design/frame_lifetime_trace.md` 设计文档，**未落地** | 声称"有设计文档未落地"属实 |

### 3.4 无法验证声明清单（不得用于支撑任何结论）

| # | 声明 | 来源 | 状态 |
|---|---|---|---|
| U1 | ~~"Zhao, Zhou & Cohen（ISSTA 2026, DOI 10.1145/3832093）覆盖+变异在回归设定下跨模型比较有效（r=0.780@k=10）"~~ **【已解决】** | BASELINE §target_quality note | **已定位并逐位核验（2026-10-17）**：论文=Zhao/Zhou/Cohen《Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)》，PACMSE 3(ISSTA) ISSTA002，arXiv:2607.22880；r=0.780@k=10 见论文 §4.3/Table 7（Pearson r=0.780, p=0.002，inter-model、平均聚合、bug-free、k=10）。项目引用（含条件限定）准确；初版"未定位"系本评审检索疏漏 |
| U2 | `orchestration_search.py` 16 臂 bandit 实跑状态 | ADR-0034 + 源码 | 不可验证（冻结中 vs 已废弃需澄清） |
| U3 | repair 92.5% 分母口径（37/40）与 9 个测试驱动任务剔除的影响 | E4 工件 + IR §15.7 | 待项目方澄清 |
| U4 | QuixBugs 首轮 detection 基线"~63%（49/50）"与 E4 的 45.9%（17/37）的口径桥接 | layered_narrative §1 | 两个数字分属不同口径（首轮红率 vs F2P 三段判定），文档未显式桥接，**存在误导性并列风险** |
| U5 | E7 人工裁决（κ≥0.7 目标） | preregistration.md | 未执行（项目已披露；任何"人工验证"表述不可用） |
| U6 | 全量 pytest 实跑终态 | BASELINE §tests | **已解决（本人实测）**：6792 passed / 5 skipped / 2 failed；2 失败均非代码（自指一致性 + 沙箱 ps 被禁），与 BASELINE 声称的失败性质逐项一致 |

### 3.5 本评审独立执行的验证记录（含可重放工件）

- **测试收集**：`.venv/bin/python3 -m pytest tests/ --collect-only -q` → **6799 collected**（HEAD 130adbd；BASELINE 登记 6789 @ 2026-10-17 + 2 提交增量，轨迹一致）。
- **主批次复算**（本人，scipy binomtest）：三臂检出率、McNemar 不一致对、χ²、精确 p 全部复现（C1-C3）。
- **git 跟踪核查**（本人，`git ls-files`）：main_batch 2030 / e4_FIXED_harness 5 / df_spec 0 / M4_expand 0 / D1 0 / ULT_df200 0。
- **CI 接线核查**（本人）：ci.yml 中 22-24 个 `scripts/gates/*.py` 调用点 + pytest-cov-xdist + ruff + mypy。
- **全量 pytest 实跑（本人，完成时补齐）**：`.venv/bin/python3 -m pytest tests/ -q --basetemp=/tmp/pt_review_b2 -p no:cacheprovider` → **6792 passed / 5 skipped / 2 failed（883.42s）**；2 失败：① BASELINE 自指一致性（登记值滞后，非代码）；② 沙箱 `ps` 被禁（环境已知项，非代码）。结论：BASELINE"0 failed"声称在本机等价成立（失败均非代码回归），与项目自身披露的失败性质逐项一致。
- **子代理只读核验**：12 组声明工件存在性/数字/provenance/跟踪状态逐项核验（结果并入 §3.1）。
- **前沿引用核验**（本人）：14 处项目引用中 12 处一手核验为真（详见 §4 交叉验证列）。

### 3.6 复算工件与 provenance（回应"本人复算无脚本"）

本评审的全部核心复算均落盘于 `docs/reviews/review_recompute/`，与项目 provenance 纪律同标准：

| 工件 | 内容 | SHA256（前 16 位） |
|---|---|---|
| `recompute_core_claims.py` | C1/C2/C3/C4/C14 复算脚本（Wilson CI、McNemar 精确二项、χ²±Yates、OR 精确 CI、配对风险差 cluster bootstrap、单侧 p、多重性、E7 敏感性） | `4250fcd05574d66b` |
| `recompute_outputs.json` | 全部复算输出（含输入文件 SHA256、Python 版本、UTC 时间戳） | `3f59f23d60895f0d` |
| `recompute_run.log` | 运行日志 | `8cf9eeb40c3fe247` |
| `export_tables.py` + 5 个 CSV | 从本报告 Markdown 抽取的表格源（防纯文本错位） | `2cc3638e35dc15ef` 等 |
| `SHA256SUMS` | 上述工件清单 | — |

- **输入工件 SHA256**（已记入 `recompute_outputs.json` 的 `inputs` 字段）：main_batch 三批次（`6e31c07d…`/`bb5fcfc8…`/`be6a42e5…`）、e4 双臂（`2cbf4009…`/`d23402fb…`）、df_spec 双臂（`813c437f…`/`536da803…`）。
- **重放命令**（仓库根，Python 3.14 .venv + scipy）：
  `python docs/reviews/review_recompute/recompute_core_claims.py`
- **时间戳**：2026-10-17T04:1x UTC（`recompute_outputs.json` `meta.generated_at`）。
- **诚实边界**：C5（false_fix 修正口径）、C7（meta_coverage）、C10/C11（spec_compile_rate/expr_coverage）、C9（Mut@k）的复算由子代理从工件完成，本人未逐位重放其脚本；这些项的工件路径与 SHA256 已在 §3.1 标注，读者可按同标准自行重放。

### 3.7 统计报告模板（统一口径，回应"模板不统一/缺 CI"）

本报告所有比例与配对比较按以下模板报告。凡正文只有点估计处，以本表补齐。

| 项 | 检验 | 单/双侧 | 连续性校正 | 统计量 | p | 效应量（95% CI） | 多重性处理 |
|---|---|---|---|---|---|---|---|
| C2 aitester vs df（synthetic，n=240 配对） | McNemar 精确二项 | 双侧（另报 H1 方向单向） | 不适用（另报 χ²±Yates） | b=12, c=80；χ²=50.26（无 CC）/48.79（Yates） | 1.72e-13（单向 a>b：1.0） | δ=−28.33pp，cluster bootstrap [−35.42, −21.25]；OR=0.15 [0.082, 0.275] | 预注册主对比，α=0.05 单家族；Bonferroni×3 后 5.1e-13 |
| C3 df vs plain_llm（n=261 配对） | McNemar 精确二项 | 双侧 | 不适用 | b=113, c=0；χ²=113.0 | 1.93e-34 | δ=+43.30pp [37.16, 49.04]；OR=∞ [14.1, 3651]（c=0，0.5 校正） | 同上 |
| C4 aitester vs df（QuixBugs E4，n=37 配对） | McNemar 精确二项 | 双侧 | 不适用 | b=0, c=14；χ²=14.0（Yates 12.07） | 1.22e-4 | δ=−37.84pp [−54.05, −21.62]；OR=0 [0.002, 0.578] | 独立预注册批次主对比；Bonferroni×3 后 3.7e-4 |
| C14 df_spec vs df（QuixBugs 41 口径，n=35 配对） | McNemar 精确二项 | 双侧（另报 H1 方向单向） | 不适用 | b=1, c=10；χ²=7.36（无 CC）/5.82（Yates） | 0.0117 双侧；**H1 方向（df_spec>df）单向 p=0.9995** | δ=−25.71pp [−42.86, −8.57]；OR=0.10 [0.013, 0.781] | 独立预注册批次主对比；Bonferroni×3 后 0.0352 |

**C14 方向性表述修正**（回应"表述绕且易误读"）：df_spec 臂**显著更差**而非"未显示优势"——不一致对 1:10 中 df_spec 独有仅 1 例，双向精确 p=0.0117，而预注册假设方向（df_spec 优于 df）的单向 p=0.9995。即：**在统计上可以拒绝"df_spec ≥ df"，且点估计方向为负**。

**Wilson 95% CI（小样本比例，审稿人常规要求）**：

| 比例 | k/n | 点估计 | Wilson 95% CI |
|---|---|---|---|
| C1 aitester | 38/240 | 15.8% | [11.8, 21.0] |
| C1 plain_llm | 4/261 | 1.5% | [0.6, 3.9] |
| C1 plain_llm_df | 117/261 | 44.8% | [38.9, 50.9] |
| C4 aitester | 17/37 | 45.9% | [31.0, 61.6] |
| C4 df | 31/37 | 83.8% | [68.9, 92.4] |
| C14 df_spec | 19/35 | 54.3% | [38.2, 69.5] |
| C14 df | 28/36 | 77.8% | [61.9, 88.3] |
| C18 ULT accuracy | 42/200 | 21.0% | [15.9, 27.2] |
| C9 QuixBugs Mut@k | 1182/1258 | 0.9396 | [0.925, 0.952] |
| C9 ULT replace Mut@k | 1590/2356 | 0.6749 | [0.656, 0.694] |
| C9 ULT specir Mut@k | 847/1927 | 0.4395 | [0.418, 0.462] |

### 3.8 多重比较与证据链归因（回应"多重性未讨论/D1 归类/归因强度"）

**多重性立场**：本报告引用的三项主要阴性结论（C2/C4/C14）均为各自**独立预注册批次的主对比**（预注册哈希先于数据落盘，git 历史可核），不存在"一数据多比较择优"问题；对探索性子组（bug_type/error_category 分层），项目侧已用 BH-FDR 控制（`statistical_analysis.py`），本报告不引入新的未校正声明。敏感性：若把三项主对比当作同一家族做 Bonferroni ×3 校正，p 分别为 5.1e-13 / 3.7e-4 / 0.0352，**全部仍显著**——结论对多重性处理稳健。

**证据链归类修正**（回应"D1 归入规格优先否定存在归类错误"）：
- **规格锚/规格优先证据链**：M4（QuixBugs specir 扩样，δ=−11.43pp，p=0.0768，方向一致未达显著）+ df_spec（δ=−25.7pp，p=0.0117，显著为负）。→ 两次独立检验，**一次显著否定、一次方向一致未达显著**；合并构成"方向性否定证据"，不得表述为"两次均显著否定"。
- **提示协议证据链**：D1（plain_llm vs plain_llm_df，δ=−2.78pp，p=1.0）+ C3（df vs plain_llm 113:0）+ C12（E6 control 9.2% vs 34.5%）。D1 检验的是**检出优先协议内部**（df 加性协议对裸提示无增益的 QuixBugs 复现），**不直接检验规格假设**，已从规格证据链移出。

**归因强度修正**（回应"提示协议是几乎全部增益来源需收窄"）：C3 的 113:0 只能证明 df **提示协议包**（含结构/长度/格式/示例的整体）优于裸提示；协议内部单一因素（如"检出优先"措辞本身）的分解消融未做。§0.2 第 1 条与 §5 已按"协议包级归因"收窄，对比矩阵中该维度标注"仅作协议级对比"。

### 3.9 未入 git 工件汇总与 CI 门禁分析（R-1，P0 级）

| 工件目录 | 对应结论 | git 跟踪（本人实测） | SHA256SUMS | 影响的对外声明 | 修复动作 |
|---|---|---|---|---|---|
| `emse_df_spec_20261016/` | C14（df_spec 阴性，论文 RQ4 级证据） | **0 文件** | 在盘但未随目录入库 | "规格锚被显著否定"及其预注册链 | `git add -f` + 补 SHA256SUMS 入库 |
| `emse_quixbugs_specir_expand_20261014/` | C15（M4 阴性） | **0 文件** | 在盘 | 规格优先"三连阴性"表述 | 同上 |
| `emse_d1_quixbugs_ab_20261013/` | C16（D1 协议对照） | **0 文件** | 在盘 | 提示协议证据链 | 同上 |
| `emse_ult_df200_20261017/` | C18（ULT 21.0% 对标） | **0 文件** | **无** | "低于 ULT 均值"的外部基准对标 | 同上 + 生成 SHA256SUMS |

**根因分析**：`.gitignore:165` 忽略 `experiments/results/**`；main_batch 等目录为历史上 `git add -f` 强制入库，而 2026-10-14 之后的四个 `emse_*` 目录未执行 force-add。`scripts/gates/check_artifacts_tracked.py` 的扫描面显然为固定路径清单（main_batch 等），未覆盖新目录——即"新增结果目录不入库"这一类缺口会**静默复发**。

**修复方案（具体）**：
1. 立即：`git add -f` 四目录 + 在 `emse_ult_df200_20261017/` 生成 SHA256SUMS；
2. 门禁：将 `check_artifacts_tracked.py` 的清单改为"扫描全部 `experiments/results/emse_*/` 且要求每目录 ≥1 跟踪文件或存在显式 ignore 豁免登记"（建议 diff：清单来源从硬编码路径改为 glob + 白名单 `docs/env_budget.yaml` 式登记），防再复发；
3. 中期：对 df_spec/M4/D1/ULT-df200 四批做 Zenodo DOI 归档（投稿 Data Availability 可直接引用），与 git 双轨。

### 3.10 ULT gold 参照作废的传导分析与口径敏感性（回应 14/15）

**事实**（项目批次八发现，子代理核验、本次引述）：ULT 官方 `test_list` 在 **71/71** 任务上无法在 `fixed` 通过（官方物化风格复测同败；`fixed` 与上游 `ULT_Lite.jsonl` 的 `code` 逐字节一致）→ 项目"ULT gold 上界 1.0"作废。

**传导分析**：

| 受影响结论 | 传导判定 |
|---|---|
| C9 ULT replace Mut@k 0.6749 / specir 0.4395 | **仍成立**：生成测试的击杀判定只依赖"套件在变异代码上失败 ∧ 在原代码（项目自建 `fixed`）上通过"的健全门，与 ULT 官方 gold 无关；但"gold 上界参照"叙事须删除，替换为"官方 gold 在本管线不可用"的披露 |
| C18 ULT accuracy 21.0% | **仍成立**（green_on_fut 口径，套件在项目自建 `fixed` 上 30s 内通过）；但**与 ULT 论文 41.32% 的对比强度下降一档**：论文均值基于官方 gold 完整管线，而项目发现该 gold 在本管线 71/71 失败——两管线的 `fixed` 语义可能存在系统性差异（项目已将 `fixed` 与上游 `code` 逐字节比对，但仍不排除评测脚本差异） |
| 关键发现第 3 条"低于均值约 20pp" | **降级为方向性陈述**：由于 (a) green_on_fut（套件级、30s 终止）比 ULT accuracy（逐用例）更严，(b) ULT 官方 gold 在本管线失效暗示管线差异，**折算后差距区间无法收敛**——定性结论"项目在 ULT 上不占优"稳健，但"低 20pp"的数值不得单独引用。按更严口径折算，项目 green_on_fut 21.0% ≤ 其 ULT-caliber accuracy 上界未知；反向亦不能排除项目 ULT-caliber accuracy 高于 41.32%（若多数套件仅少量用例失败）。**唯一正解=§6 P4 同协议三臂对决** |

### 3.11 E7 人工裁决缺失的敏感性上界（回应 22）

模型：gold 三段判定错误率 q → n 个配对中期望翻转 n×q → detection 率偏差上界 ±q（不考虑方向抵消的保守线性界）。

| q（gold 错误率） | 期望翻转（n=37） | detection 率偏差上界 |
|---|---|---|
| 5% | 1.9 | ±5pp |
| 10% | 3.7 | ±10pp |
| 20% | 7.4 | ±20pp |

**解读**：(a) C4 的 37.9pp 差距与 C2 的 28.3pp 差距均大于 q=10% 的上界（±10pp），**方向结论不翻转**；(b) C14 的 −25.7pp 同样大于 ±10pp，但其与 QuixBugs 跨批 6pp 波动、MDE 16.1pp 处于同一量级——解读须三者并列；(c) 该上界未考虑判定错误的系统性（若 gold 管线本身有偏，偏差可能同向叠加）——E7 按共享 rubric 执行（A-08）是唯一收敛路径。

---

## 4. 2025-2026 前沿基线表（独立重建）

> 全部数据点来自 2026-10-17 本人执行的一手来源检索（arXiv 原文/ACM DL/IEEE/官方榜单/官方仓库）。A=一手可验证；B=一手不可完全验证（预印本/作者自报无完整复现材料）；C=二手。"交叉验证"列标注与项目文档引用的一致性。

### 4.1 测试生成子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 | 与项目引用交叉验证 |
|---|---|---|---|---|---|---|---|
| TestGenEval（Jain, Rozière, Synnaeve, Meta） | 全套件生成平均覆盖率 | GPT-4o **35.2%**（最高）；编译/通过率多指标 | TestGenEval（1210 文件对 / 11 个 Python 仓库 / 68,647 测试） | arXiv:2410.00752 + testgeneval.github.io | 2024-10 / arXiv（ICLR 2025 poster） | **A** | 项目引用一致 |
| ULT / UnLeakedTestbench（Huang, Zhang, Harman, Zhang, Du, Ng） | 12 模型均值：accuracy / stmt / branch / mutation | **41.32% / 45.10% / 30.22% / 40.21%**；最佳单模型 Pass@1 17.83%；PLT 47.07/55.13/40.07/50.80；TestEval 91.79/92.18/82.04/49.69 | ULT（3909 函数级去泄漏 Python 任务，cyclomatic≥10 均值 14.87） | arXiv:2508.00408 + ACM DL DOI 10.1145/3805043 + UCL Discovery | 2026-03 / TOSEM | **A** | **项目引用逐位一致**（IR 曾误报 DOI 错挂，已自更正） |
| Ockhamareto（Huang, Harman, Zhang, Guo, Du, Ng） | ULT N=5 mutation / 平均测试数 | **49.9% @ 2.60 tests** vs MIST-RL **31.3% @ 4.67 tests**（3.4× 每测试效率）；+30-35pp over base @4B/9B/27B；CodeContests 44.6% vs 32.4% | ULT + HumanEval+ + MBPP+ + CodeContests + TestGenEval-Lite | arXiv:2608.24473 | 2026-08 / arXiv | **A**（预印本，数字来自摘要，一手可追溯） | 项目引用一致（49.9%@N=5 / MIST-RL 31.3%@N=5） |
| CoverUp（Pizzorno, Berger, UMass） | line+branch 覆盖率 | 每模块中位 **80%**（vs CodaMosa 47%）；总体 **89%**（vs MuTAP 77%）；vs CodaMosa 总体 60%（vs 45%） | 开源 Python 挑战代码基准（SlipCover 测量） | arXiv:2403.16218v4 + ACM DOI 10.1145/3729398 | 2025-06 / FSE | **A** | 项目引用一致（90% 口径为 89% 的四舍五入表述） |
| TestAgent（Xiao, Fang, Chen, Zhang, Zhou, Gu, Shang） | 执行率/行/分支/变异 | **97.46% / 92.34% / 90.24% / 83.69%**；154 真实 bug（92.2% precision）；Python 移植 88.85% 行覆盖（+26.86pp vs CoverUp）；工业 UTXXX 84.2%/55.4% | 6 个 Java 项目 + 9 个 Python 模块 + 658 方法工业集 | arXiv:2607.09101 | 2026-07 / arXiv | **A**（预印本） | 项目引用一致（92.34/83.69） |
| MUTGEN（Wang, Xu, Briand, Liu） | mutation score | HumanEval-Java **89.5%** / LeetCode-Java **89.1%**（超 EvoSuite 28.8/51.3pp）；**动机发现：100% 行覆盖仅 4% 变异得分** | HumanEval-Java + LeetCode-Java（204 主题，PITest） | arXiv:2506.02954 + IEEE DOI 10.1109/TSE.2026.3682975 | 2026 / IEEE TSE | **A** | 项目引用一致（TSE 2026 DOI + 100%/4% 发现） |
| CANDOR（Xu, Wang, Briand, Liu） | oracle correctness | 超 TOGLL ≥**21.1pp**（正确/缺陷代码两侧）；覆盖率与 EvoSuite 相当、变异显著优 | HumanEvalJava + LeetCodeJava | TOSEM 接收记录 + SciProfiles 作者页 | 2026-03 / TOSEM | **A** | 项目未引用（本次补入） |
| SPARC（Fu, Chowdhury, Jabbarvand） | vs vanilla prompting | 行覆盖 **+31.36pp** / 分支 **+26.01pp** / 变异 **+20.78pp**；**匹配或超过 KLEE**（复杂主题）；94.3% 测试保留率 | 59 个真实/算法 C 主题 | arXiv（alphaXiv 作者页著录）+ 论文摘要 | 2026 / ICLR 2026（据 alphaXiv 著录） | **B**（venue 来自二手著录，数字来自摘要一手页） | 项目未引用（本次补入） |
| Google Spec-Driven Test Generation（Tufano 等 10 人, Google） | bug detection rate | **53.4%→63.2%（+9.8pp, McNemar p=0.0352, 5 跑聚合；单跑 +4.2pp p=0.3075 NS）**；分支覆盖 46.4%→48.9%（+2.5pp, p=0.0034）；契约覆盖率条件化检测 54.9% vs 19.4%（Fisher p=3.6e-14）；token +38.0% | Google 内部 90 个历史生产 bug（多语言，greenfield 设定，**契约从修复后代码提取**） | arXiv:2608.17177v2 + ACM DOI 10.1145/3842652.3843195 + research.google/pubs | 2026 / SpecOps'26 workshop | **A** | **项目 spec_first.py 引用 +9.8pp/p=0.0352 准确**（但未引其关键限定：契约须从 fixed 代码提取、增益条件化） |

### 4.2 测试预言（oracle）子方向

| 前沿方法 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|---|
| TOGA（Dinella, Ryan, Mytkowicz, Lahiri, Microsoft） | oracle accuracy | **96%**（held-out）；+33% over 既有；+EvoSuite 找到 **57 真实 bug（30 个独有）** | Methods2Test/Atlas/Defects4J | arXiv:2109.09262 + ICSE 2022 (pp.2130-2141) | 2022 / ICSE | **A** |
| TOGA 大规模复评（外部复现） | 有效性衰减 | oracle 类型误分类 **24%**；静默 **62%**；断言假阳 **47%**；F2P 增量仅 **+0.3%**；67% "bug 检出"实为隐式 oracle（崩溃） | 25 个 Java 项目 / 51,385 变异体 | 复评论文（lacuna 著录，未定位一手页） | 2025 | **B** |
| TOGLL（LLM 微调） | 正确 oracle 成功率 | 断言均值 **63%** vs TOGA 16.4%；异常 oracle **93.4%** vs 18.86% | OracleEval25（25 项目） | arXiv:2405.03786 | 2024 / arXiv | **A** |
| Tratto（Molinelli, Martin-Lopez, Zackrone, Eken, Ernst, Pezzè） | accuracy/precision/F1 | **73% / 72% / 61%**（vs 符号基线 JDoctor 61/62/37、GPT-4 40/24/37）；3× 产量、10× 少假阳 | Java ground-truth 数据集 | arXiv:2504.04251 + DOI 10.1145/3728960 | 2025 / ISSTA | **A** |
| Di Grazia et al.（大规模实证） | oracle 变异得分 | LLM 生成 oracle **43%** vs 开发者 **45%** mutation score；**50% 生成 oracle 无法编译/执行** | 13,866 post-cutoff oracles / 135 Java 项目 | USI 博士论文 + ASE 2025 论文 | 2025 / ASE | **A**（经 rottenwifi 二手转述 + 论文著录交叉） |

### 4.3 多智能体协作与程序修复子方向

| 前沿方法 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|---|
| SWE-bench Verified 官方榜（swebench.com） | % Resolved（mini-SWE-agent 统一 harness） | Claude 4.5 Opus **76.80%** / Gemini 3 Flash & MiniMax M2.5 75.80% / DeepSeek V3.2 70.00%（成本 $0.07-0.96/任务） | SWE-bench Verified（500） | swebench.com 官方榜 | 2026-02 | **A** |
| SWE-bench Verified 厂商自报（跟踪榜） | % Resolved | Claude Opus 5 96-97%（Vals.ai 第三方测 97.0±0.76；系统卡自报 96.0） | 同上 | steel.dev 跟踪榜（聚合官方/厂商来源） | 2026-07/09 | **B**（自报+第三方转述） |
| SWE-bench Pro（Deng et al., Scale） | Pass@1 | GPT-5 **25.9%**（最高）；公开集 GPT-5 23.3 / Opus 4.1 22.7 / Live-SWE-agent 45.8%（Pro v2, 642 任务） | SWE-bench Pro（1865 问题 / 41 仓库；v2 642） | PMLR v306 deng26f + labs.scale.com | 2025-2026 | **A** |
| LaMAR（Jiao, Zhang, Feng, Li） | repair success | Qwen3-8B：Defects4J **24.5%**；DebugBench/QuixBugs **62.1-87.5%**；KV-cache 潜通信 O(N²)→O(N) | Defects4J + DebugBench + QuixBugs（Java/Python/C++） | ACM DOI 10.1145/3832783.3837423 + ASE'26 程序页 | 2026-10 / ASE | **A** |
| TraceCoder（Huang, Ye, Sun, Zhang, Zhang, Liu） | Pass@1 相对提升 | 最高 **+34.43%** 相对；HLLM +2.64pp；RM +5.31% 相对；插桩语义保留 >99% | HumanEval/+/ClassEval/BigCodeBench ×3 模型 | arXiv:2602.06875 + ICSE'26 | 2026 / ICSE | **A** |
| TwinMem-Agent（Wu, Luo, Mu, Xiang） | Pass@1 / 成本 | **89.1% vs mini-swe-agent 60.0%**（SWE-bench Pro 8×25 顺序设定）；**$0.0044 vs $0.0798（约 18× 低成本）**；去记忆 −8pp/−12pp | SWE-bench Pro 子集 | ACM DOI 10.1145/3803437.3807664 + FSE Companion'26 | 2026-07 / FSE Companion | **A** |
| LatentMAS（Gen-Verse） | accuracy / token | 最高 **+14.6%** 准确率；输出 token **−70.8~83.7%**；推理 **4-4.3×** 加速；training-free | 9 基准（数学/科学/代码） | arXiv:2511.20639 | 2025-11 / arXiv | **A**（预印本） |
| LANTERN（Luo, Keung, Yang, Klein, Bissyandé, Tian, Le） | Pass@10 绝对提升 | Rust **+22.09pp**（跨语言翻译修复）；Python ~90% vs Rust ~65% 基线差距 | xCodeEval（5068 bug / 11 语言）+ Defects4J + SWE-bench Lite | arXiv:2503.22512 | 2025 / arXiv | **A**（预印本） |
| AgentCoder（Huang, Zhang, Luck, Bu, Qing, Cui） | pass@1 / token | GPT-4：HumanEval **96.3%** / MBPP **91.8%** @ 56.9K/66.3K token（SOTA 90.2%/78.9% @ 138.2K/206.5K） | HumanEval + MBPP ×9 模型 | arXiv:2312.13010 | 2024 / arXiv | **A**（预印本） |
| ADI（Xiang, Xu, Chu, Tian, Zhang） | resolved / 成本 | FramePilot **63.8%** Verified @ **$1.28/任务**（Claude-Sonnet-3.7，超 Claude-Tools 63.2%）；即插即用 **+6.2~18.5%** | SWE-bench Verified + Lite | arXiv:2604.24212 + DOI 10.1145/3797126 | 2026 / FSE (PACMSE) | **A** |

### 4.4 自修复系统子方向

| 前沿方法 | 关键指标 | 指标值 | 评测条件 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|---|
| VIGIL（Cruz） | 运行时自愈 | 过早成功通知 **100%→0%**；平均事件延迟 **97s→8s**；元程序自修复案例 | 单案例研究（reminder agent） | arXiv:2512.07094 | 2025-12 / arXiv | **B**（单案例） |
| Meta ACH（Harman et al.） | 变异引导测试采纳 | 10,795 Kotlin 类 / 9,095 变异体 / 571 强化测试；工程师采纳率 **73%** | Meta 生产代码 | FSE 2025 industry 程序页 + Meta Engineering | 2025-01 / FSE industry | **A** |
| ESBMC-AI 等（形式化+AI 修复） | — | 未展开检索（项目提示词列为参考方向） | — | — | — | 未检索（见 §16 检索建议） |

### 4.5 逻辑驱动测试生成子方向

| 前沿方法 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|---|
| LogiCase（Sung, Aditi, Kim, Han, Ko） | 测试有效性 | CCFG（带计数器上下文无关文法）+ 微调 CodeT5；在识别错误算法上显著超基线（validity/effectiveness） | CodeContests | DOI 10.24963/ijcai.2025/861 + ijcai.org  proceedings | 2025 / IJCAI | **A** |
| Zhao, Zhou & Cohen（misguidance，Toronto） | 误导效应量化 | Defects4J 233 bug × 13 设定：misguided tests **0.46%→3.84%**，effective tests **8.51%→2.98%**；**规格 docstring 替换缺陷代码：misguided −40%、effective +35%** | Defects4J（Java，11 模型±推理） | arXiv:2607.22883 + DOI 10.1145/3832204 + PACMSE 3(ISSTA) ISSTA113 | 2026 / ISSTA | **A** |
| TSC2CARLA / Alloy+LLM 组合测试 | — | 未展开独立检索（列为待检索项） | — | — | — | 未检索 |

### 4.6 数据冲突与说明

1. **SWE-bench Verified 分数域**：官方 mini-SWE-agent 榜 76.80%（2026-02）vs 厂商自报 96-97%（2026-07/09）。冲突原因：harness 不同（统一 bash-only harness vs 厂商全配置 scaffold）+ 自报偏乐观 + 基准饱和/污染。**本报告采用官方榜数字作为可比基线**，厂商数字标注 B 级。
2. **ULT mutation 与项目 Mut@k**：ULT 论文 12 模型均值 40.21%（K-query 协议、cosmic-ray 全变异体、3909 任务）vs 项目 ULT replace 0.6749（9/46 健全子集、单次生成协议）vs Ockhamareto 49.9%（RL 训练、N=5）。三者**协议、训练状态、子集全部不同，严禁并列比较**（详见 §5 与 §6 P4 的同协议实验设计）。
3. **QuixBugs df 臂跨批次波动**：83.8%（2026-10-09，E4 FIXED harness，31/37）vs 77.8%（2026-10-16，df_spec 对照臂，28/36）。同臂同基准 6pp 波动，根因可能是 temp=0 下的服务端非确定性或缓存/物化差异（项目自报"跨批次配对的历史教训"）。**影响：任何单批 QuixBugs 结论的 MDE 解读必须留出此方差**。

---

---

## 5. 项目与前沿量化对比矩阵

> "项目现状"仅采用 A/B 级证据（§3.1）；不可验证数据标"无法对比"。"能否对比"考虑基准/协议/口径同构性。

| 维度 | 2025-2026 前沿 SOTA | 证据等级 | 项目现状（可验证部分） | 项目证据等级 | 绝对差距 | 相对差距 | 竞争位置 | 超越路径编号 | 可否对比 |
|---|---|---|---|---|---|---|---|---|---|
| **测试生成：语句覆盖（被测代码）** | ULT 12 模型均值 45.10%（3909 真实函数） | A | synthetic 84.0-93.6%（自研模板，plain_llm_df 81.5-97.2%） | A（自研基准内） | — | — | **内部口径领先自身轻量臂**（但低于 plain_llm_df） | — | ❌ 不同基准（synthetic vs ULT） |
| **测试生成：语句覆盖（外部基准）** | ULT 均值 45.10% / 最佳 17.83%@Pass@1 | A | ULT df200：green_on_fut 21.0%（42/200） | B | ≈ −24pp（vs 均值，口径部分可比） | ≈ −53% | **落后（中低梯队）** | P4 | ⚠️ 口径近似可比（项目更严：30s 终止+全过） |
| **测试生成：变异得分** | MUTGEN 89.5%（HumanEval-Java）/ Ockhamareto 49.9%@N=5（ULT）/ TestAgent 83.69%（Java）/ ULT 均值 40.21% | A | QuixBugs 0.9396（29/50 健全子集）/ ULT replace 0.6749（9/46）/ ULT specir 0.4395（5/25） | B | QuixBugs 小基准内 0.94 高于 ULT 均值 0.40 但基准不同 | — | **小基准内高、外部基准中低**；带三重标签 | P4 | ❌ 协议不同（单次生成 vs K-query/RL） |
| **测试生成：编译/执行率** | TestAgent 99.11% 编译 / 97.46% 执行（Java） | A | 项目未单列该指标（detection 三段判定内含"无收集错误"防线） | — | — | — | 无法对比（未申报） | P6（新增指标） | ❌ |
| **缺陷检出（F2P detection）** | Zhao ISSTA'26 effective tests 8.51%（fixed 提示）/ SpecOps'26 63.2%（fixed+spec，5 跑） | A | QuixBugs df 83.8%（31/37）/ aitester 45.9% / synthetic df 44.8% / ULT 0/24 | A/B | QuixBugs df 83.8% 高于 ISSTA'26 的 8.51%（协议不同：后者按测试条计、前者按任务计） | — | **内部：轻量臂强于完整编排（−28pp~−37.9pp，A 级）** | P1/P2 | ⚠️ 协议不同，须谨慎 |
| **多智能体协作增益** | LaMAR 超基线（ASE'26）；TraceCoder +34.43% 相对 Pass@1（ICSE'26）；TwinMem 89.1% vs 60.0%（FSE'26）；LatentMAS +14.6%（arXiv'25） | A | 编排净 **−28pp**（synthetic，p=1.7e-13 本人复算）/ −37.9pp（QuixBugs，p=0.0005）/ 成本 6-8× | **A** | 与前沿方向相反 | — | **落后（项目已自行降级为"消融容器"，止损诚实）** | P5 | ⚠️ 任务不同构（APR vs 测试检出），不得互证 |
| **多智能体通信机制** | LaMAR KV-cache 潜通信 O(N²)→O(N)；LatentMAS token −70.8~83.7% | A | 文本 prompt + 语义缓存；API 架构下 KV 传递不可行 | A（架构事实） | — | — | 落后（API 约束下短期无解） | P5b（长期） | ⚠️ |
| **修复（APR）成功率** | SWE-bench Verified 官方 76.80%（Claude 4.5 Opus，仓库级）；TwinMem 89.1%（Pro 顺序子集） | A/B | QuixBugs repair 92.5%（37/40，gold 裁决，函数级）；SWE-bench 无有效数据（基础设施失败） | A/B | 函数级 92.5% 数字高于仓库级 SOTA 但**任务粒度不同** | — | **函数级单文件：与轻量 prompt 基线相当（E4 df 无修复通道）**；仓库级未测 | P2 | ❌ 粒度不同 |
| **成本（$/任务）** | TwinMem $0.0044；SWE 官方 $0.07-0.96；ADI $1.28 | A | aitester $0.0259 / df $0.0045（synthetic，deepseek-flash） | A | 与 TwinMem 同量级；低于 ADI | — | **轻量臂成本有竞争力；完整编排 6-8× 于轻量臂** | P5 | ⚠️ 模型/任务不同 |
| **逻辑驱动：规格可编译率** | 无同口径外部指标（项目独创） | — | QuixBugs 0.7161 / ULT 0.5937 / synthetic 0.6397（v4 前门） | B | — | — | 指标独创、无外部对照；**增益未证实（三连阴性）** | P1 | ❌ 无同口径前沿 |
| **逻辑驱动：规格锚增益** | SpecOps'26 +9.8pp（fixed 提取契约，5 跑）；Zhao ISSTA'26 spec 替换 −40% misguided | A | df_spec **−25.7pp（显著为负）**；D1 −2.78pp；M4 −11.43pp | A/B | 与前沿正向差距 ~35pp | — | **落后且方向相反；机制假设已定位（锚=缺陷代码再描述）** | **P1（修复后重测）** | ⚠️ 协议可比（均为规格锚替换） |
| **测试预言正确性** | Tratto 73% acc（Java）；TOGLL 63%；Di Grazia 43% mutation | A | spec_oracle 注入率 40%（QuixBugs）；**oracle 正确率未系统度量** | — | — | — | 无法对比（缺指标） | P3（补齐 oracle 质量度量） | ❌ |
| **自修复运行时机制** | VIGIL（延迟 97→8s，单案例）；ADI FLT（+6.2-18.5pp 即插即用） | B/A | 快照回滚+红回归门+弃权门（精确率 86%）+防黑客门+进程组终止；FLT 仅设计文档 | A（机制在场） | — | — | **安全机制设计领先；运行时诊断能力缺（FLT 未落地）** | P2 | ⚠️ |
| **工程化/可复现性** | 2025-2026 LLM4SE 文献普遍缺 provenance/门禁（MUTGEN/TestAgent 等均无同类披露） | A（文献缺口事实） | 24 CI 门禁+覆盖率棘轮+口径矩阵+SHA256SUMS+模型指纹+env 快照门+双语文档门+零 LLM 复算链 | A | — | — | **显著领先学术前沿**（本报告认定的最强竞争优势） | 保持+产品化（P3） | ✅ 可断言领先 |
| **评估诚信方法论** | PatchDiff/UTBoost 等指出基准高分含幻影；Google SpecOps'26 用 greenfield+McNemar | A | 4 起测量伪影主动披露修正+false_fix 五口径矩阵+预注册先落盘+等预算对照 | A | — | — | **领先（唯一系统报告 false_fix 多口径的系统）** | P3 | ✅ |

**竞争位置总结**：项目在 **2025-2026 前沿格局中的真实位置** = (1) **工程化/可复现性/评测诚信：明确领先学术前沿**；(2) **测试生成能力（外部基准 ULT）：中低梯队**（21.0% vs 均值 41.32%）；(3) **多智能体增益：被自身 A 级数据否定，落后于前沿正向证据（但任务不同构）**；(4) **逻辑驱动（规格锚）：三连阴性，机制缺陷已定位、可修复**；(5) **成本：轻量臂有竞争力**。不存在任何"全面超越前沿"的可验证证据；**存在一个可验证的局部领先（工程/评测诚信）和一个可修复后重测的潜在突破点（规格锚）**。

---

## 6. 超越前沿方法设计

> 每条路径含：技术路径、差异化点、理论基础（一手）、预期提升（量化+置信度+证据等级）、实验验证方案、反事实推演、里程碑、独立验证判定标准。**不给出无法验证或纯理论空想的方案**；凡依据为推测均标 E。

### P1：独立锚规格生成（Independent-Anchored Spec Generation）——修复规格锚路线的机制缺陷

**技术路径**：将 df_spec 臂的锚材料从"Planner 对 buggy 代码的再描述"改为**独立于缺陷实现的规格源**，按优先级三级回退：(a) 人类 docstring（QuixBugs/ULT/synthetic 均自带，天然独立于 bug 实现——ISSTA'26 的规格 docstring 路线的正确实例化）；(b) 人类 docstring + Planner SpecExpr 子句的**并集**（保留形式化增益，不替换人类规格）；(c) 仅当 (a)(b) 均缺失时用 Planner 再描述（现口径）。同时在判分层落地 ISSTA'26 的 **misguided/effective 三分度量**（misguided=buggy 过∧fixed 败；effective=buggy 败∧fixed 过），替代 over_red proxy。

**差异化点**：前沿（Zhao ISSTA'26、Google SpecOps'26）证明规格锚有效，但均未研究"锚的独立性"这一变量；SpecOps'26 的契约提取自**修复后代码**，本项目场景（测试生成时无 fixed 可用）必须解决"无 fixed 时的独立锚来源"——人类 docstring 是文献未充分利用的独立锚。项目的 SpecExpr 白名单 DSL + 拒绝归因可作为"规格质量"的过程指标（spec_compile_rate / spec_expr_coverage）。

**理论基础（一手）**：Zhao et al. ISSTA 2026（DOI 10.1145/3832204）——规格 docstring 替换使 misguided −40%/effective +35%；Tufano et al. SpecOps'26（DOI 10.1145/3842652.3843195）——增益条件化于"契约覆盖被违反条件"（54.9% vs 19.4%）；项目自身 df_spec 阴性 + BASELINE 机制假设（锚=再描述）；第三方对 ISSTA'26 的小模型复现（约一半自写规格把缺陷写成预期行为，二手 C 级，方向佐证）。

**预期提升**：QuixBugs 41 缺陷程序口径，df_spec 从 54.3%（19/35）回升至 ≥65%（≥23/35），且 misguided 测试占比相对 df 臂下降 ≥30%（预注册机制指标）。**置信度：中**（依据：ISSTA'26 +35% effective 为一手 A 级，但那是 Java+LLM 生成规格；人类 docstring 锚在本项目场景的效应量无先例，E 级部分需实测）。**幅度证据等级：B（一手文献方向性）+E（本项目量级推测）**。

**实验验证**：QuixBugs 41 口径三臂（df / df+Planner锚 / df+docstring锚）同批同判分；预注册三态判定（confirmed: detection≥65% ∧ 单向 McNemar p<0.05）；3 个 cache namespace；temp=0；misguided/effective 三分度量为主机制指标；MDE 披露（n≈35，80% power MDE≈16pp）。**对照数据来源**：df 臂同批新跑（历史 83.8%/77.8% 仅作次级参照）。

**反事实推演**：若前沿也采用 docstring 锚（低成本、无技术壁垒），项目优势仅剩 SpecExpr 形式化子句与评测基建；**护城河=评测诚信层 + 多口径指标（false_fix/misguided/弃权精确率），不在锚本身**。锚路线可被快速复制——因此 P1 必须与 P3 捆绑发表。

**里程碑**：短期（1-2 月）：misguided/effective 度量落地 + docstring 锚臂单批探索；中期（3-4 月）：预注册三臂正式跑批 + ULT probe25 复测；长期（6 月）：与 P3 合成方法论论文主体。

**独立验证判定**：**成功** = 预注册条件下 df+docstring锚 detection ≥65% 且单向 p<0.05，且 misguided 占比降 ≥30%；**失败** = detection <55% 或 p≥0.10（记阴性，锚路线关闭，转 P5）；**中间态** = trend（p<0.10 且 δ>0）→ 扩样至 ULT 全量复测。

### P2：函数级动态诊断与超时判定（ADI 式 FLT + per-test timeout）

**技术路径**：落地已设计未实现的 `docs/design/frame_lifetime_trace.md`：(a) **per-test 超时**（判分层 120s → 每条生成测试 10-30s 预算），把 4 个"缺陷实现不终止"任务从 None 转为可判定（超时记 fail=可判定红）；(b) 轻量 FLT：复用 `sys.settrace` 采集 (fid, args, ret, τ) 函数级帧轨迹，作为 Debugger prompt 的结构化动态上下文（替代当前的 pass/fail 二值反馈）。

**差异化点**：ADI（FSE'26）在 SWE-bench 仓库级任务上证明 FLT 即插即用 +6.2-18.5%；本项目场景是函数级单文件，FLT 的实现成本更低（无仓库导航），且项目已有 `src/agents/fl_spectral.py`（Ochiai）可与之融合成"谱系+动态"双通道定位。

**理论基础（一手）**：ADI arXiv:2604.24212 / DOI 10.1145/3797126（63.8% Verified @ $1.28，+6.2-18.5% 即插即用；PDB 逐行交互 53% 放弃率的动机实验）；TraceCoder ICSE'26（轨迹驱动 +34.43% 相对）。

**预期提升**：QuixBugs 41 口径：None 任务 4→0，可判定分母 37→41；aitester detection 45.9%→≥55%（+9pp，4 个任务全部转为检出，因缺陷实现不终止在正确测试下必然超时=红）；Debugger 修复轮次收敛速度 +10~20%。**置信度：中高**（4 任务的因果链有项目一手证据：`detection_none_cause` 4 任务均属不终止类，bitcount 缺陷 `n ^= n - 1` 对任何 n 不终止）。**证据等级：B（一手文献支持方向）+A（项目内 4 任务因果证据）**。

**实验验证**：QuixBugs 单臂前后对比（同 cache namespace 复用响应，唯一变量=超时判定与 FLT 注入——沿用项目已验证的"单变量重放"方法学，E4 伪影修复链即此模式）；成功判定：4 个 None 任务全部转为非 None 且其中 ≥2 个 detection=1；零 LLM 回归测试 12 例（复用 run_with_timeout 测试模式）。

**反事实推演**：per-test 超时是无技术壁垒的工程修复（任何团队可做）；FLT 有 ADI 占先——**项目护城河仅在"把 FLT 用于测试生成-检出闭环"这一 ADI 未做的设定**。复制风险高，必须快速落地并先发。

**里程碑**：短期（1 月）：per-test 超时（P0，纯判分层修复，零 LLM）；中期（2-3 月）：FLT v1 注入 Debugger；长期（6 月）：FLT + 谱系融合定位的消融。

**独立验证判定**：**成功** = None 归零 ∧ 41 口径 detection ≥55% ∧ 修复轮次不升；**失败** = 超时判定引入假红（fixed 侧超时）>2 任务（回滚该判定）。

### P3：评测诚信基准化（Measurement Integrity as a First-Class Contribution）

**技术路径**：把项目已沉淀的 4 起测量伪影修正链 + false_fix 五口径矩阵 + 双门协议 + 预注册纪律 + 等预算对照固化为**开源可复用的评测清单与参考实现**（checklist + 最小可复现脚本），并在 ≥2 个外部公开数据集（TestGenEval-Lite / Defects4J / QuixBugs 干净复刻）上演示"未修正即高估"的量化幅度。

**差异化点**：PatchDiff（至多 6.4pp 幻影增益）、UTBoost（24% leaderboard 条目被更严解析修正）证明基准高分含伪影，但均为单点分析；**项目拥有文献中罕见的"四起伪影的完整披露-修正-回归测试链"与"false_fix 条件/边际/修正三口径"**，具备做"评测诚信系统化"的独特素材。

**理论基础（一手）**：项目 4 起伪影工件（A 级）；PatchDiff/UTBoost（项目预注册引用的污染防控条款，本次未独立核验原文，标 B）；Zhao ISSTA'26 的 misguided/effective 新度量方向。

**预期提升**：不可量化性能提升——目标是**方法论影响力**：≥2 个外部数据集复现"未修正即高估"；清单被 ≥1 个外部团队采用（下载/引用）。**置信度：高**（素材已在场）。**证据等级：A**。

**实验验证**：零 LLM 复算链（`make reproduce-zero-llm` 已就绪）；外部数据集重放；成功判定=在 TestGenEval-Lite 上演示至少 1 类可修正伪影且修正前后差距可量化。

**反事实推演**：评测诚信是公共品，无护城河；但其是**论文被引与社区信任的杠杆**，且与 P1/P5 的数据结论互为担保。

**里程碑**：短期（1-2 月）：清单 v1 + TestGenEval-Lite 伪影演示；中期（3-4 月）：开源发布 + 文档化；长期：与主论文的 Open Science 包绑定。

**独立验证判定**：**成功** = ≥2 数据集复现 + 清单公开可用；**失败** = 外部数据集上无法复现任何伪影（则降级为内部工程报告）。

### P4：ULT 同协议三臂对决（外部效度的决定性实验）

**技术路径**：在 ULT 官方协议（K-query、greedy、cosmic-ray 全变异体、correct_tasks 过滤）上跑三臂：`plain_llm` / `plain_llm_df` / `plain_llm_df+docstring锚（P1）`，全量 3909 或分层 500+，产出 accuracy/stmt/branch/mutation 四指标，与 ULT 12 模型均值（41.32/45.10/30.22/40.21）和 Ockhamareto（49.9%@N=5）做**同协议**对比。

**差异化点**：Ockhamareto 需要 RL 训练（GRPO）；项目是**纯提示/编排方法**，若在 ULT 上达到其 mutation 的 80%+（≥40%）而零训练成本，即构成"零训练达到 RL 级测试有效性"的可发表论断；且 ULT 官方不发布 gold tests，项目已有 probe 基础设施（ult_adapter + cosmic-ray 8.7.0 + 健全性门）。

**理论基础（一手）**：ULT 论文协议与基线（A）；Ockhamareto（A，RL 上界参照）；项目 ULT df200 冒烟（21.0%，B，已具备跑批管线）。

**预期提升**：mutation ≥40%（追平 12 模型均值）/ 冲刺 ≥45%（超 Ockhamareto 之外所有）；accuracy 21.0%→≥35%（docstring 锚 + 检出优先协议叠加）。**置信度：中**（21.0% 的基线已实测；锚增益在 ULT 上的效应量无先例，E 级）。**证据等级：B+E**。

**实验验证**：ULT 协议严格复刻（K-query 迭代、1024 token/轮、greedy）；三臂 × 500 任务分层（按难度/cyclomatic 分层预注册）；McNemar/BH-FDR + bootstrap CI；成本对照（$/task 与 Ockhamareto 训练成本不可比，须声明）。**成功判定**：mutation ≥40% 且 accuracy ≥35%（双臂配对 p<0.05）；**失败判定**：mutation <30% 或 accuracy <25%（阴性亦可发表：证明纯提示方法在去泄漏真实函数上的天花板）。

**反事实推演**：若 RL 方法（Ockhamareto 家族）继续快速提升，纯提示路线的窗口在收窄；项目的**非 RL 依赖**恰是差异化（API 架构约束下的现实选择）。护城河=去泄漏基准上的同协议对比数据 + 成本-效果 Pareto。

**里程碑**：短期（1-2 月）：ULT probe 200 三臂补齐（当前只有 df 单臂 21.0%）；中期（3-4 月）：500 分层预注册跑批；长期（6 月）：全量或 1000+ 任务 + 论文主结果。

**独立验证判定**：见上（成功/失败判定为预注册常量，跑批前落盘）。

### P5：多智能体止损式重构（从"编排增益"转向"顺序任务记忆 + 预算感知"）

**技术路径**：接受 −28pp 事实，把编排重构为 TwinMem 式**顺序任务记忆**（情景记忆= grounded demonstrations + 语义记忆=蒸馏笔记，固定预算合并）+ 预算感知早停；保留"消融容器"定位，仅当等预算对照下相对 df 臂 δ≥+8pp 且 p<0.05 才转正"编排增益"主张。

**差异化点**：TwinMem 在 SWE-bench Pro 顺序设定 +29.1pp、成本 −18×（A 级一手）；本项目的 synthetic 87 任务 × 多种子天然构成"同仓库任务流"，且已有 token 记账与预算门（E6 matched 方法论在场）。

**理论基础（一手）**：TwinMem-Agent FSE'26 Companion（89.1% vs 60.0%，$0.0044 vs $0.0798）；项目 E6 matched（−28pp 归因编排结构而非预算）；ADI 成本对照。

**预期提升**：等预算下 aitester vs df 的 δ 从 −28pp 收敛至 ≥−5pp（记忆+早停回收浪费的编排开销）；token/task 从 26,115 降至 ≤8,000（−70%）。**置信度：中低**（TwinMem 设定为仓库级顺序任务，本项目为函数级独立任务，迁移效应量 E 级推测）。**证据等级：B+E**。

**实验验证**：synthetic n=87 × 3 种子，臂={df, aitesester+memory}，等预算 cap；预注册成功判定（δ≥+8pp ∧ p<0.05）；失败判定=第三组阴性则永久关闭编排增益主张（项目 IR 已预写该止损线，本报告认可）。

**反事实推演**：记忆机制正被快速采纳（TwinMem/LatentMAS/TraceCoder HLLM 同向），**护城河低**；但对本项目是"把 −28pp 的负资产转为中性"的必要修复，而非领先来源。

**里程碑**：短期（1-2 月）：轨迹记忆原型（token 记账缺口已于 b12b8a4 收口，非前置项）；中期（3-4 月）：等预算记忆臂跑批；长期：按预注册止损线决断。

**独立验证判定**：**成功** = 等预算 δ≥+8pp ∧ p<0.05 ∧ token −50%；**失败** = δ≤0（永久关闭编排增益主张，写入论文负面结果）。

### P6：不推荐的路径（红队审查记录）

| 候选 | 不推荐理由（一手依据） |
|---|---|
| KV-cache 潜空间通信（LaMAR/LatentMAS 移植） | 项目架构为商业 API（deepseek/GLM/openai 兼容），KV-cache 不可导出；LatentMAS 需开源模型本地部署。**E 级不可行**，除非整体转向本地开源模型（与零默认依赖/成本策略冲突） |
| RL 训练测试生成器（Ockhamareto 路线） | 需 GRPO 基础设施 + 变异奖励管线 + 数万 rollout；项目当前零训练基础设施，6-12 月内不可达；且与"API 架构"定位冲突 |
| 以 SWE-bench Verified 为主战场 | 官方 SOTA 76.80% 且基准饱和/污染争议（steel.dev 披露 Opus 5 伪造 go.sum 案例）；仓库级需多文件/长上下文能力，项目跨文件修复默认关且 SWE-bench 20 次基础设施失败。**不应作为主战场**，仅作长期 L3 阶梯 |

---

---

## 7. 差距分析表（按严重度排序）

| # | 维度 | 项目现状 | 前沿基线（一手） | 差距判定 | 严重度 | 对应路径/建议 |
|---|---|---|---|---|---|---|
| G1 | 外部效度 | 主结论建立在 synthetic 自研模板（n=87×3 种子）+ QuixBugs（n=41）；ULT 仅 200 任务单臂冒烟 | TestGenEval/ULT/Defects4J/SWE-bench 系列为社区标准 | 主实验缺外部基准同协议对决 | **高** | P4 / A-01 |
| G2 | 规格锚增益 | 三连阴性（D1/M4/df_spec），机制缺陷已定位（锚=缺陷代码再描述） | ISSTA'26 +35% effective / SpecOps'26 +9.8pp | 方向相反但机制可修复 | **高** | P1 / A-02 |
| G3 | 多智能体增益 | 编排净 −28pp（A 级），成本 6-8× | LaMAR/TraceCoder/TwinMem 正向（任务不同构） | 任务不同构下的负资产 | **高** | P5 / A-03 |
| G4 | 工件可复现性（新批） | df_spec/M4/D1/ULT-df200 四目录 0 git 跟踪 | 前沿顶会 Open Science 要求 artifact 可异地复现 | 脱离本机不可复现 | **高** | A-04（P0） |
| G5 | ULT 真实位置 | 21.0%（n=200 单臂）vs 均值 41.32% | Ockhamareto 49.9%@N=5（RL） | 落后约 20-29pp | 中 | P4 |
| G6 | 测试预言质量 | spec_oracle 注入率 40%，正确率未度量 | Tratto 73% / TOGLL 63% / Di Grazia 43% mutation | 无同口径对比 | 中 | A-05 |
| G7 | 运行时自愈 | 安全机制齐全（回滚/弃权/红回归门），FLT 未落地 | ADI FLT +6.2-18.5pp 即插即用 | 动态诊断能力缺 | 中 | P2 / A-06 |
| G8 | 统计严谨 | McNemar/BH-FDR/贝叶斯/聚类校正/功效/MDE 披露齐备；缺 Wilson CI 与成本-效果 Pareto 报告 | 2025-2026 顶渐趋要求效应量+CI+成本 | 小幅缺项 | 低 | A-07 |
| G9 | 人工评估 | E7 未执行（无 Kappa） | Google AI-SQE'26： Fleiss' κ=0.307（人工裁决本身不可靠，需 rubric） | 缺失（已披露） | 中 | A-08 |
| G10 | QuixBugs 口径桥接 | "~63% 首轮基线"与"45.9% F2P"未显式桥接；df 臂跨批 83.8→77.8% 波动 6pp | — | 文档误导风险 + 单批脆弱 | 中 | A-09 |
| G11 | 引用精确性 | 12/14 处一手核验为真；DOI 10.1145/3832093 未定位 | — | 1 处待澄清 | 低 | A-10 |

> **执行状态（2026-10-17）**：✅ **已解决**——该 DOI 定位为 Zhao/Zhou/Cohen 复现性研究（ISSTA'26 ISSTA002，arXiv:2607.22880），r=0.780@k=10 逐位核验通过；**项目前沿引用准确率实为 13/13（除 1 处初版检索疏漏外全部为真）**。
| G12 | 编译/执行率指标 | 未单列 | TestAgent 99.11%/97.46% | 指标缺项 | 低 | A-11 |

---

## 8. Python 专项诊断表

| # | 检查项 | 现状（实测/核验） | 判定 | 建议编号 |
|---|---|---|---|---|
| P-1 | 项目结构与包管理 | src layout + 薄入口 main.py（465B）+ PEP 621 pyproject + setup.py shim + 动态版本单一事实源；无循环依赖报告 | ✅ 优 | — |
| P-2 | 环境与依赖 | requires-python>=3.12；CI 矩阵 3.12/3.13/3.14；依赖分组（db/rag/formal/ult/dev extras）；requirements.lock 存在；`pip-audit` CI（5 ignored） | ✅ 优 | A-12（SBOM） |
| P-3 | 代码质量 | ruff 0.16.3 配置精细（规则集+逐文件豁免+理由注释）；mypy 0 错误（133 源文件）；py.typed 分发；bandit 配置在场 | ✅ 优 | — |
| P-4 | 测试 | 6799 collected（本人实测）；meta_coverage 92.96%/87.62%；ratchet 门禁；hypothesis 属性测试在场（SpecExpr property） | ✅ 优 | A-13（扩大 property 覆盖面） |
| P-5 | 可复现性 | lock+Dockerfile.repro+provenance 内嵌+模型指纹门+env 快照门+SHA256SUMS+零 LLM 复算链 | ✅ 优（主体） | A-04（新批工件入 git） |
| P-6 | 安全 | .env 不入库；沙箱子进程+进程组终止；凭据清洗门+日志脱敏门+gitleaks 配置；**bandit 已在 CI security 作业阻断（R10，本地实跑零 findings——初版评审误判为未接入，已更正）** | ✅ 优 | — |
| P-7 | 性能 | xdist -n 4 loadfile；语义缓存；token 记账；**缓存命中记账已于 b12b8a4（2026-10-16）收口：三条命中路径均还原"避免的 token"（record_cache_hit_usage），test_token_usage 13 例覆盖——初版评审误判为缺口，已更正** | ✅ 良 | — |
| P-8 | 数据/实验管线 | 口径矩阵+fail-closed None+None 不计 0+去污染检查+难度分层+模板匹配敏感性 | ✅ 优（方法论亮点） | — |
| P-9 | 文档 | 双语文档门+BASELINE 单一事实源+35 ADR+MODEL/DATA CARD+API 参考+威胁模型 | ✅ 优 | A-16（§15 待澄清项回填） |
| P-10 | 已知技术债（项目自报+本人核验） | ① ~~9 文件 20 处 subprocess.run 未换~~ **【已核验为零】**：src/ 内裸 `subprocess.run(` 调用为 0（现存命中均为解释历史缺陷的注释/docstring，2026-10-17 grep 实测）；② graph→experiments 反向导入冻结；③ orchestration_search 16 臂未实跑；④ env_flag 之外 22 处裸 int(os.getenv()) 未并入 clamp 口径 | ⚠️ 中（②③④） | A-17 已废弃 |

---

## 9. 领域专项诊断表

| # | 维度 | 现状 | 判定 | 建议编号 |
|---|---|---|---|---|
| D-1 | 逻辑规格 | SpecExpr 白名单 AST+BNF 单一事实源+8 类拒绝归因+v4 护栏+property 测试锁定；spec_compile_rate 0.59-0.72 | ✅ 工程领先；增益未证 | P1 |
| D-2 | 约束求解 | z3 SMT 见证层在场（spec_smt.py 731 行），**默认关且无启用批次** | ⚠️ 能力闲置 | A-18 |
| D-3 | 测试覆盖准则 | F2P 三段判定+特异性门+变异得分+分支覆盖注入+双门协议 | ✅ 齐全 | — |
| D-4 | 测试预言 | spec_oracle 确定性注入（QuixBugs 40%）；oracle 正确率未度量 | ⚠️ 缺质量指标 | A-05 |
| D-5 | 多智能体 | 编排净负（A 级）；专家池/辩论/多候选默认关 | ⚠️ 已止损降级 | P5 |
| D-6 | 通信机制 | 文本 prompt；KV 传递 API 架构下不可行 | ⚠️ 架构约束 | P6（不推荐） |
| D-7 | 自修复安全 | 快照回滚+红回归门+弃权门（精确率 86%）+防测试黑客门+回滚 fail-closed | ✅ 设计领先 | — |
| D-8 | 闭环收敛 | 停止原因枚举+覆盖停滞检测（默认关）+预算停止；停滞检测缺消融 | ⚠️ 小幅缺项 | A-19 |
| D-9 | 评估公平 | 双盲 gold 独立裁决+预注册+等预算对照+聚类校正+MDE 披露 | ✅ 领先 | A-07（Wilson CI） |
| D-10 | 安全合规 | 沙箱+注入防护+secrets 纪律+威胁模型+数据许可登记（ULT MIT 实测） | ✅ 达标 | — |

---

## 10. 改进/优化/新增建议表

> 类型：必须改进（P0，不修则影响核心结论可信度）/ 建议优化（P1）/ 可新增（P2）。每条对应具体文件/代码位置。

| 编号 | 对应文件/位置 | 问题 | 一手前沿依据 | 建议内容 | 类型 | 优先级 | 预期收益 | 成本/风险 | 验证指标 | 时间线 | 工具/命令 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A-01 | `experiments/run_benchmark.py` 臂设计；`docs/study/ULT_DF200_PREREG` | ULT 仅 df 单臂 200 任务；无三臂同协议 | ULT 论文（TOSEM'26）；Ockhamareto（arXiv:2608.24473） | 按 P4 设计补齐 plain_llm/df/df+docstring锚三臂，500 任务分层预注册 | 必须改进 | P0 | 外部效度从"冒烟"升为"可比对决" | ~$0.3-0.5 LLM 配额；需用户授权 | 三臂四指标 + McNemar | 1-2 月 | `python -m experiments.emse_ult_*`；`make preflight` |
| A-02 | `src/tools/spec_first.py`；`experiments/results/emse_spec_anchor_20261016/` | 规格锚=Planner 对 buggy 代码再描述，约一半概率固化缺陷为预期 | ISSTA'26 DOI 10.1145/3832204；SpecOps'26 DOI 10.1145/3842652.3843195 | 按 P1 增加 docstring 独立锚三级回退 + misguided/effective 三分度量 | 必须改进 | P0 | 修复规格锚路线；把 over_red proxy 升级为真度量 | 中（新臂+新判分维度，需回归测试） | misguided 占比 −30%；detection 回升 | 2-4 月 | `pytest tests/test_emse_df_spec_analysis.py` |
| A-03 | `src/graph/workflow.py`；ADR-0016 | 编排增益 −28pp 未止损重构 | TwinMem FSE'26（89.1% vs 60.0%，18× 低成本） | 按 P5 实现顺序任务记忆（固定预算）+ 等预算重测 | 建议优化 | P1 | δ 从 −28pp 收敛；token −50%+ | 中 | 等预算 δ≥+8pp ∧ p<0.05 | 3-4 月 | `make pass-matched` 口径扩展 |
| A-04 | `experiments/results/{emse_df_spec_20261016,emse_quixbugs_specir_expand_20261014,emse_d1_quixbugs_ab_20261013,emse_ult_df200_20261017}/` | 四目录 0 git 跟踪（本人 `git ls-files` 实测）；`check_artifacts_tracked.py` 未覆盖 | 顶会 Open Science artifact 要求 | force-add 四目录 + SHA256SUMS；扩展 check_artifacts_tracked 扫描面至全部 `emse_*` 结果目录 | 必须改进 | **P0** | 论文核心实验可异地复现 | 低（git add -f + 门禁扩展） | CI 门禁对四目录 exit 0 | 1 周 | `git add -f experiments/results/emse_df_spec_20261016/`；`python scripts/gates/check_artifacts_tracked.py` |
| A-05 | `src/tools/oracle_validator.py`；run_benchmark 指标 schema | spec_oracle 正确率未度量 | Tratto 73%/TOGLL 63%（ISSTA'25/arXiv'24） | 增加 oracle_correct/oracle_fp/oracle_silent 三指标（gold fixed 上假阳率 + 注入任务检出贡献） | 可新增 | P1 | 逻辑驱动通道的有效性可量化 | 低-中 | oracle 质量报告随批次产出 | 2 月 | 扩 `metrics_schema` + `tests/test_emse_*` |
| A-06 | `docs/design/frame_lifetime_trace.md`（未落地） | 4 个 None 任务（不终止）+ Debugger 二值反馈 | ADI FSE'26（+6.2-18.5pp；PDB 53% 放弃率） | 按 P2：先 per-test 超时（判分层，零 LLM），后 FLT v1 | 必须改进（超时部分） | P0（超时）/P1（FLT） | None 归零；detection +9pp | 中 | 41 口径 detection ≥55% | 1-3 月 | `pytest tests/test_m1_packaged_tests.py` 扩展 |
| A-07 | `experiments/statistical_analysis.py` 报告层 | 缺 Wilson CI 与成本-效果 Pareto | 2025-2026 统计报告惯例 | 比例型端点全部补 Wilson 95% CI；新增 $/detection Pareto 节 | 可新增 | P2 | 报告完整性 | 低 | 报告含 CI 列 | 2 周 | `python -m experiments.emse_stats_report` 扩展 |
| A-08 | `docs/preregistration.md` E7 节；`docs/HUMAN_ADJUDICATION_PROTOCOL.md` | 人工裁决未执行 | Google AI-SQE'26（κ=0.307，需共享 rubric） | 执行 E7：n≥100 双人盲审 + 共享 rubric + Cohen's κ | 建议优化 | P1 | 填补"无人工验证"缺口 | 中（人工成本） | κ≥0.7 | 2-3 月 | 协议文档已在场 |
| A-09 | `docs/design/layered_narrative.md` §1；BASELINE §benchmark | "~63% 首轮基线"与"45.9% F2P"未桥接；df 臂跨批 83.8→77.8% 未归因 | — | 显式口径桥接段；跨批方差纳入功效与解读 | 必须改进 | P0 | 防审稿误读 | 低（文档） | 文档口径表 | 1 周 | `make docs-check` |
| A-10 | BASELINE §target_quality note（DOI 10.1145/3832093） | 该 DOI 未独立定位 | — | 定位原文或改引已核论文（ISSTA'26 误导效应 10.1145/3832204） | 必须改进 | P0 | 引用诚信 | 低 | `check_citations.py --online` exit 0 | 1 周 | `python scripts/gates/check_citations.py --online` |

> **执行状态（2026-10-17）**：✅ **已完成（且证明项目引用原本正确）**——该 DOI 已定位一手论文：Zhao, Zhou & Cohen《Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)》，ISSTA 2026 / PACMSE 3(ISSTA) Article ISSTA002, pp.30-53，arXiv:2607.22880；**r=0.780@k=10 已从论文 §4.3 正文 + Table 7 逐位核验**（branch coverage vs raw mutation score，Pearson r=0.780, p=0.002，inter-model 视图/平均聚合/bug-free 输入/固定套件规模 k=10），与 BASELINE 转述的条件（跨模型比较、控制规模、回归设定）逐项一致。本评审初版"无法定位"系检索疏漏（已致歉并更正）；BASELINE.yaml 该 note 已补验记载。
| A-11 | `experiments/run_benchmark.py` 指标 schema | 编译率/执行率未单列 | TestAgent 99.11%/97.46% | 增加 compile_rate/exec_rate 行级字段 | 可新增 | P2 | 与 TestGenEval/TestAgent 可比 | 低 | 新字段非空率 | 1 月 | schema 扩展 + 测试 |
| A-12 | `pyproject.toml`；release.yml | 无 SBOM | OWASP/OpenSSF 2025-2026 供应链指南（本次检索见 aidlc.io 汇总，C 级） | release 作业产出 CycloneDX SBOM | 可新增 | P2 | 供应链合规 | 低 | SBOM 随 release | 1 月 | `cyclonedx-py` |
| A-13 | `tests/test_spec_expr_property.py` | property 覆盖面可扩（打桩/回归函数） | — | 对 patch_applier/spec_ir_v2/helpers JSON 修复函数扩 hypothesis 策略 | 可新增 | P2 | 模糊测试深度 | 低 | 新增 property 用例 | 1 月 | `pytest tests/test_spec_expr_property.py` |
| A-14 | ~~`.github/workflows/ci.yml`~~ | ~~bandit 配置在场但未接 CI 主链~~ **【评审误判，2026-10-17 更正】** | — | **无需动作**：bandit 1.9.4 自 R10（2026-10-05）起已作为 security 作业阻断步骤（`bandit -r src/ -c pyproject.toml -q`），本次本地实跑 exit 0 / 零 findings | 已废弃 | — | — | — | — | — | `bandit -r src/ -c pyproject.toml`（实跑通过） |
| A-15 | ~~`src/agents/base_agent.py:437/389`~~ | ~~缓存命中绕过 record_usage → token 记账仅覆盖非缓存调用~~ **【评审误判，2026-10-17 更正】** | — | **无需动作**：D2 已于 b12b8a4（2026-10-16 三波次收口）修复——三条命中路径（LRU 快路径 / 语义缓存 / 文件缓存）均经 `record_cache_hit_usage` 还原"避免的 token"（独立口径），未命中路径以调用前后 total 差值（含重试/故障转移）写入缓存文件 `tokens` 字段；`tests/test_token_usage.py` 13 例覆盖（本次实跑全过）。本评审初版沿用了 IR 报告的过期清单（IR 成稿与修复同日落地） | 已废弃 | — | — | — | — | — | `pytest tests/test_token_usage.py`（13 例实跑通过） |
| A-16 | `docs/` 全量 | §15 待澄清项（repair 分母/orchestration_search 状态等）未回填 | — | 逐项澄清后更新文档 | 建议优化 | P1 | 文档完整性 | 低 | 待澄清清单关闭 | 2 周 | — |
| A-17 | ~~`src/` 9 文件 20 处 `subprocess.run`~~ | ~~超时只杀直接子进程（孙进程持管道挂死）~~ **【评审误判，2026-10-17 更正】** | — | **无需动作**：src/ 内裸 `subprocess.run(` 实际调用为 0（`grep -rnE '^\s*(return \|await )?subprocess\.run\(' src/` 空；现存文本命中均为注释/docstring）；`run_with_timeout`（killpg）已全面接管。IR/CO 报告所述缺口在此前轮次已修复 | 已废弃 | — | — | — | — | — | `grep -rnE '^\s*(return \|await )?subprocess\.run\(' src/`（实测空） |
| A-18 | `src/specs/spec_smt.py`；`[formal]` extra | z3 层默认关且无启用批次 | SPARC（ICLR'26）神经符号 +20.78pp mutation | 设计最小启用批次（QuixBugs n=50，观测 UN SAT 见证率与检出关系） | 可新增 | P2 | 逻辑驱动第二通道证据 | 中 | 见证率+检出关联报告 | 2-3 月 | `pip install 'aitester[formal]'` |
| A-19 | `src/graph/workflow.py` 停滞检测 | 覆盖停滞检测默认关且无消融 | TraceCoder RM（+5.31% 相对） | 停滞检测开/关消融一批 | 可新增 | P2 | 闭环收敛证据 | 低 | 消融报告 | 1 月 | `--enable-stagnation` 类开关 |

---



**建议执行状态（2026-10-17 更新）**：

> **执行状态（2026-10-17）**：✅ **已完成**——除四旗舰目录外，另入库证据性目录 8 个（4×calib、stats_extensions、batch5、t08 seed43/44），共 1195 文件 / 20MB；门禁扩展为 MANIFEST 41 项 + emse_* 目录覆盖扫描 + 15 个显式豁免（带理由）；新增 `tests/test_artifacts_tracked_gate.py`（8 例全过）；为 emse_ult_df200 生成 SHA256SUMS（203 项验证通过）。

> **执行状态（2026-10-17）**：✅ **已完成**——layered_narrative.md §1 增加口径桥接表（首轮即红率 vs F2P 三段判定）与跨批 6pp 波动披露段；SUBMISSION_CHECKLIST 的 batch5 标注更新为已入库。

---

## 11. 既有评审结论独立复核表

> 复核对象：`INDEPENDENT_REVIEW_2026-10-16.md`（IR，513 行，项目内自称"独立评审"）。方法：本人/子代理对其关键数字回溯原始工件；对其方法论声明核对 git 历史；对其前沿引用独立核验。

| 原结论编号 | 原文位置 | 原结论 | 独立复核方法 | 复核结论 | 支持/推翻/无法验证 | 依据 |
|---|---|---|---|---|---|---|
| IR-0.2-1 | §0.2.1 | 项目核心性能声明"高度可复现（A 级）"，10 组数字 | 本人复算主批次（C1-C3）；子代理核验 12 组工件 | **支持**（但 IR 计数的"12 项全部逐位复现"含口径膨胀：C5/C8/C10/C11 实际为部分复现——IR §0.3-1 与 §3.1 表内标注存在自相不一致，IR 未修正） | 部分支持 | §3.1 本报告复核表 |
| IR-0.2-2 | §0.2.2 | 核心实证结论为阴性：−28pp/45.9vs83.8/成本 6-8× | 本人独立复算 | **支持** | 支持 | §3.1 C1-C4/C6 |
| IR-0.2-5 / P1 | §6 P1 | Zhao ISSTA'26 spec-based prompting 是"最可论证的突破口"；over_red 60% 是 misguidance 典型表征 | 本人核验 ISSTA'26 原文（DOI 10.1145/3832204）+ df_spec 新工件（10-17 产出，IR 成稿后） | **需修正**：df_spec（IR 之后跑批）证明"Planner 锚"版规格优先**显著为负**（−25.7pp, p=0.0117）；P1 的"预期 45.9%→≥60%"已被实测否证；突破口仍在但必须换独立锚（本报告 P1 重设计） | 推翻（原 P1 预期）/ 支持（方向识别） | §3.1 C14；§6 P1 |
| IR-C1~C4/C6/C9/C12 | §3.1 | 主批次检出/统计/E4/成本/Mut@k/ULT DOI | 本人+子代理复算 | **支持**（逐位或逐量级一致） | 支持 | §3.1 |
| IR-C8 / §11-11 | §3.1 C8 | "6532 collected / 6526 passed" | 本人实测 HEAD 收集数 6799；IR 数字为 10-16 快照 | **过期但方向一致**（IR 自注"收集口径通过、实跑未复现"诚实） | 支持（带时效注） | §3.5 |
| IR-11-8 / 11-9 | §11 | "逻辑驱动可编译率主张成立"部分支持；"SpecExpr 增益未确认"部分支持（B） | 本人核验三连阴性链（D1/M4/df_spec） | **支持并升级**：df_spec 后，增益证据从"未确认"变为"负向显著" | 支持 | §3.1 C14-C16 |
| IR-11-10 / A-03 | §11-10 | ULT DOI 归属正确（初版误报已自更正） | 本人核验 ACM DL/UCL/arXiv 三处 | **支持** | 支持 | §4.1 |
| IR-11-12 / 11-13 | §11 | "gold 独立裁决不含人工、无 Kappa"；"SWE-bench 20 次全失败" | 子代理核验披露 | **支持** | 支持 | §3.1 C20 |
| IR-§12.1 | §12.1 | 战略重定位："规格锚定的轻量协议 + 评测诚信方法论"双支柱 | 本人独立判断 | **支持**（与本报告竞争位置结论一致：工程/诚信领先 + 规格锚待修复） | 支持 | §5 |
| IR-A-04 / A-06 / A-07 / A-11 | §10 | E7 未执行 / D2 token 记账 / subprocess 未转换 / 16 臂未实跑 | 源码与 CI 核验 | **部分支持**：E7 未执行、16 臂未实跑两项在场；**D2 token 记账（b12b8a4）与 subprocess 转换均已完成**（2026-10-17 实测：src/ 裸调用为 0、13 例 token 测试通过）——IR 清单过期，本报告初版沿用属误判（已更正，见 §10 A-15/A-17） | 部分支持 | §8 P-7/P-10 |
| IR-§3.3.4 / §7-8 / §8-9（stale 段） | §3.3.4 | "ULT DOI 列入无法验证"（与 C12 已更正结论冲突） | 本人核对 IR 内部一致性 | **IR 自身不一致**（stale 段落未随更近结论刷新）——不影响事实判定，但削弱其"逐条独立"完成度声称 | 无法验证（作为评审质量声明） | 子代理审计 U3 |
| IR-P4 | §6 P4 | ULT 对标成功判定"probe mutation ≥55%" | 本人核验：该判定基于 replace 臂 0.6749（9/46 健全子集）——**子集过小且全量健全值 0.6749 已被批次八修正为更低置信**；55% 阈值缺乏同协议依据（Ockhamareto RL 为 49.9%@N=5） | **需修正**：成功判定应改为 §6 P4 的预注册常量（mutation≥40% ∧ accuracy≥35%），而非拍死 55% | 推翻（阈值设定） | §4.1/§6 P4 |
| IR-§0.3-5 | §0.3 | "ULT DOI 疑似错挂"（与 0.2-4 更正冲突） | 同上 | stale | 无法验证（作为评审质量声明） | — |

**复核总结**：IR 是一份**高质量的第一方自审报告**，其数字声明绝大多数经独立复算为真，阴性结果披露诚实，方法论（证据分级/三态裁定）健全。主要缺陷：(1) 成稿于 df_spec 数据之前，其最高优先级路径 P1 的预期已被后续实测否证；(2) 内部存在 4-5 处 stale 段落未同步更正；(3) "12 项全部逐位复现"的计数口径膨胀；(4) P4 成功判定阈值缺同协议依据。**本报告不继承其任何结论作为前提，上述裁定均基于独立复算。**

---

---

## 12. 优化后的项目方案与路线图

### 12.1 优化后框架（双支柱 + 一修复）

```
支柱 A（主成果，论文主线）：
  规格锚定的轻量测试生成协议（plain_llm_df + docstring 独立锚〔P1〕+ SpecExpr 形式化子句）
  + misguided/effective 三分度量（ISSTA'26 操作化）
  + per-test 超时判定〔P2〕
  + 特异性门/红回归门/弃权门（已有安全层保留）
  → 目标：QuixBugs 41 口径 detection ≥65%；ULT 同协议 mutation ≥40%/accuracy ≥35%

支柱 B（差异化成果）：
  评测诚信层：4 伪影修正链 + false_fix 五口径矩阵 + 预注册纪律 + 等预算对照
  + 开源评测清单（P3）
  → 目标：≥2 外部数据集复现"未修正即高估"；清单公开可用

修复项（止损）：
  多智能体编排 → 顺序任务记忆 + 预算感知（P5），等预算对照预注册决断
  → 目标：δ 从 −28pp 收敛至 ≥−5pp；token −50%+；三阴性则永久关闭编排增益主张

保留资产（竞争优势）：
  24 CI 门禁 / provenance / 口径矩阵 / SHA256SUMS / 零 LLM 复算链 / 模型指纹
```

### 12.2 技术路线（分阶段）

| 阶段 | 时间 | 内容 | 出口判据 |
|---|---|---|---|
| S0 修复期 | 0-1 月 | A-04（工件入 git，✅ 已完成）、A-10（DOI 定位）、A-09（口径桥接，✅ 已完成）；P2 的 per-test 超时 | 全部 P0 门禁 exit 0；None 任务归零 |
| S1 验证期 | 1-3 月 | P1 misguided 度量 + docstring 锚探索批；P4 ULT probe200 三臂；E7 人工裁决启动 | 探索批出趋势数据；ULT 三臂管线通 |
| S2 决胜期 | 3-5 月 | P1 预注册三臂正式跑批（QuixBugs 41）；P4 ULT 500 分层预注册；P5 等预算记忆臂 | 按预注册三态判定出结论（可阴性） |
| S3 发表期 | 5-8 月 | 支柱 B 清单开源 + TestGenEval-Lite 伪影演示；论文主结果整合；Data Availability 定稿 | ≥1 篇一手 venue 投稿；artifact 包可异地复现 |

### 12.3 Python 工程化维持与增强项

- 目录结构维持 src layout；新增 `src/measurement/` 下 FLT 模块（P2）与 oracle 质量模块（A-05）。
- 依赖：`[formal]` extra 增加 z3 启用批次后转入常规 CI 面（A-18 出口后）。
- 测试：新增 P1 的 misguided/effective 判分测试（≥15 例，含红队：恒红/恒绿/超时三态）；P2 的 per-test 超时回归（含"孙进程持管道"敌意场景，复用 run_with_timeout 测试模式）。
- CI：新增门禁 `check_emse_artifacts_tracked`（A-04）、`check_ult_anchor_coverage`（P1 锚覆盖率，防"锚缺失静默回退"重演 A1 假阴性）。
- 打包/部署：维持 wheel ~50MB 安装面收敛；SBOM 入 release（A-12）。

### 12.4 多智能体系统优化方案（角色/通信/记忆/可观测）

- **角色**：维持 Planner/Generator/Executor/Debugger/FaultLocalizer 五角色；Generator 增加"规格锚渲染"职责（P1）；不再新增角色（编排已证负）。
- **通信**：文本 prompt + 内容寻址锚表（已有）；FLT 作为结构化动态通道（P2）；显式放弃 KV 潜通信（P6 红队结论）。
- **编排**：LangGraph 状态机维持；停滞检测启用并消融（A-19）；预算停止保留。
- **记忆**：TwinMem 式情景+语义双记忆，固定 token 预算合并（P5）；写入 `state["memory_budget"]` 可观测。
- **失败恢复**：快照回滚 + 红回归门 + 弃权门 + fail-closed None 纪律全部保留并随新臂扩展。
- **可观测**：failure_taxonomy 五桶（已有）+ misguided/effective 桶（P1）+ token 记账（已全覆盖，含缓存命中还原）。

### 12.5 逻辑驱动测试生成优化方案

- 规格表达：SpecExpr v4 白名单维持；新增"docstring→SpecExpr"编译通道（把人类 docstring 的形式化部分也纳入 DSL，扩大锚的形式化覆盖面）。
- 约束求解：z3 层设计最小启用批次（A-18）：对 spec_oracle 注入行记录 SAT/UNSAT 见证率，检验"前件可满足性"与检出的关系。
- 覆盖准则：F2P 三段判定维持；新增 per-test 超时判定（P2）；branch 覆盖通道对齐 ULT 口径（P4 前置）。
- 测试最小化：引入 Ockhamareto 式 Pareto 视角作为**分析指标**（每测试边际变异击杀），不做 RL——用零 LLM 重放即可计算"若删去该测试损失多少击杀"，指导测试套件精简报告。

### 12.6 自修复机制优化方案

- 触发：维持失败分类路由（18 类）；新增"超时类"独立桶（P2 后 4 个 None 任务有归属）。
- 定位：谱系 Ochiai + RGFL 双通道维持；FLT 注入作为第三通道（P2）。
- 补丁验证：gold 独立裁决维持；新增补丁-测试共谋检测（防测试黑客门已有，扩至"补丁使测试变绿但源码未语义修复"的 false_fix 自动标注）。
- 回滚/置信度/人工审核：弃权门（精确率 86%）维持；E7 人工裁决按共享 rubric 执行（A-08）。

---

## 13. 实验、验证与评估计划

### 13.1 主实验（P1+支柱 A，预注册先行）

| 项 | 设计 |
|---|---|
| 基准 | QuixBugs 41 缺陷程序（主）+ ULT probe25/200（辅） |
| 臂 | `plain_llm_df`（对照）/ `plain_llm_df+Planner锚`（已有 df_spec 数据）/ `plain_llm_df+docstring锚`（处理） |
| 协议 | AITESTER_PROFILE=logic；temp=0；thinking disabled；parallelism=4；seed=42；3 个互异 cache namespace |
| 主指标 | detection（41 口径）+ 配对 McNemar（精确）+ 贝叶斯 δ（ROPE ±5pp） |
| 机制指标 | misguided/effective 三分占比（ISSTA'26 操作化）；spec_replace_applied 命中率 |
| 判定 | confirmed：detection ≥65% ∧ 单向 p<0.05 ∧ misguided 占比 −30%；trend：p<0.10 ∧ δ>0；not_confirmed：其余；失败线：<55% |
| 功效 | n≈35 可判定，MDE ≈16pp（80% power）——阴性必须带 MDE 解读 |
| 可复现 | 预注册哈希先落盘；判定常量入分析脚本（已有模式 tests/test_emse_df_spec_analysis.py）；SHA256SUMS + git 跟踪（A-04） |

### 13.2 零 LLM 复算实验（P2/P3）

- per-test 超时行为复算（同 cache namespace 单变量重放，E4 模式）。
- Mut@k 全量重算（cosmic-ray 8.7.0，健全性门，已有 L1 链）。
- TestGenEval-Lite 伪影演示（P3）：用项目 M1 判分树在 TestGenEval-Lite 上复跑"未修正 harness"，量化高估幅度。

### 13.3 人工裁决（E7）

n≥100，双人盲审，共享 rubric（对照 Google AI-SQE'26 的 κ=0.307 教训），Cohen's κ≥0.7 为出口。

### 13.4 可复现性包

seeds + env_snapshot + git sha + Dockerfile.repro + SHA256SUMS + `make reproduce-zero-llm` + 一键复现命令；四目录入 git（A-04）后 CI 的 check_artifacts_tracked 全覆盖。

---

## 14. 风险、伦理与合规

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R-1 | 新批工件未入 git → 论文核心实验不可异地复现（审稿人复现失败风险） | **高** | A-04（P0，1 周） |
| R-2 | P1 再次阴性 → 规格锚路线彻底关闭，论文主线只剩"诚信方法论" | 中 | 预注册三态 + 失败线；支柱 B 独立成立；df_spec 阴性本身可发表（方向相反且有机制解释） |
| R-3 | QuixBugs 污染（教学基准，模型训练语料覆盖）→ 任何 QuixBugs 结论被审稿人质疑 | 中 | ULT（去泄漏）为主战场（P4）；污染披露条款已在预注册；PatchDiff 式差分重跑抽样 |
| R-4 | temp=0 仍存在服务端非确定性（df 臂跨批 6pp 波动）→ 单批结论脆弱 | 中 | 多样本 + 同批对照 + MDE 披露；缓存 namespace 纪律 |
| R-5 | LLM 配额授权（P1/P4/P5 合计 ~$1-3） | 低 | preflight 预算闸 + 分阶段授权 |
| R-6 | 沙箱逃逸（执行 LLM 生成代码） | 中 | 子进程隔离 + 进程组终止 + 无网络 + Docker 可选；bandit CI 阻断（已在线） |
| R-7 | 数据许可（ULT MIT 已核实；The Stack v2 上游条款） | 低 | 不打包数据入仓；逐文件许可元数据保留 |
| R-8 | 多智能体编排的"过度声明"风险（引用前沿 MAS 正面结果背书） | 中 | 论文措辞纪律：编排增益主张以本项目等预算对照为准，不得引用任务不同构的前沿结果 |
| R-9 | 人工裁决引入评分者偏差 | 低 | 共享 rubric + 双盲 + κ 门槛 |
| R-10 | 单模型依赖（deepseek-flash）→ 结论模型特异性 | 中 | 披露 + 后续至少一个第二模型复测（T-1/T-2 待授权项） |

**伦理与合规**：系统生成并执行 LLM 产出的代码——沙箱隔离、无生产数据、无人类受试者（E7 为专家评审非受试者研究）、数据许可合规、密钥不入库（.env gitignore + gitleaks + 凭据清洗门）。符合当前状态；建议论文补 Ethics Statement 段。

---

## 15. 待澄清问题（必须项目方确认，不做假设填充）

> 每项含责任建议人、截止建议与"未澄清时的降级处理"——降级处理遵循本报告纪律：不可验证项不得用于支撑任何结论。

| # | 问题 | 建议责任方 | 截止建议 | 未澄清时的降级处理 |
|---|---|---|---|---|
| Q1 | 四目录（df_spec/M4/D1/ULT-df200）未入 git：本地化约定还是遗漏？若是约定，Open Science 如何保证可复现？ | 项目负责人 | 2026-10-24（1 周） | 论文中相应结论标注"artifact 仅存于作者本地工作树，审稿人不可独立复现"；投稿前必须完成 git 或 Zenodo 双轨归档（A-04） |
| Q2 | ~~BASELINE 引用的 "Zhao, Zhou & Cohen（ISSTA 2026, DOI 10.1145/3832093）"（r=0.780@k=10）对应论文？~~ | — | — | **已解决（2026-10-17）**：论文定位 + r 值逐位核验，项目引用准确（见 U1/A-10 执行状态） |
| Q3 | QuixBugs repair 92.5%（37/40）分母定义与 9 个测试驱动任务的影响 | 项目实验负责人 | 2026-10-31 | 该指标对外引用一律带"分母口径待澄清"标签；不进任何横向对比 |
| Q4 | "~63% 首轮基线（49/50）"与 E4 F2P 45.9%（17/37）的口径桥接 | 项目实验负责人 | 2026-10-31 | 文档增加显式口径表；在桥接前两个数字不得同句出现 |
| Q5 | df 臂跨批 83.8%→77.8% 波动 6pp 的归因 | 项目实验负责人 | 2026-11-07 | 所有单批 QuixBugs 结论须附"跨批波动 6pp"披露；功效解读以 MDE=16.1pp 为准 |
| Q6 | `orchestration_search.py` 16 臂 bandit 状态（冻结/废弃） | 项目负责人 | 2026-10-31 | 论文不提及该组件；README 标注"未实跑" |
| Q7 | `SPEC_SMT_ENABLE` 是否有启用批次记录 | 项目实验负责人 | 2026-11-07 | z3 层在论文中仅作"实现在场未评估"的能力陈述，不进任何结果 |
| Q8 | ULT 官方 gold 71/71 失败是否反馈上游；协议适配细节 | 项目实验负责人 | 2026-11-07 | ULT 相关结论带"官方 gold 在本管线不可用"标签（§3.10）；ULT 对标仅作方向性陈述 |
| Q9 | ~~全量 pytest 实跑终态~~ | — | — | **已解决**（本人实测 6792 passed / 5 skipped / 2 failed，2 失败均非代码） |
| Q10 | plain_llm 臂 false_fix 229/229=100% 的口径语义 | 项目实验负责人 | 2026-10-31 | 该数字不单独引用；false_fix 一律以五口径矩阵标签呈现 |
| Q11 | `paper/draft.typ` 数字与工件一致性（本次仅抽查 3 处 SRC 注释） | 论文执笔人 | 投稿前 | 补审计划见 §1.3；抽查不一致处按工件更正 |
| Q12 | `~/.cache/aitester/ult_repo` 的 MIT 许可核实证据链（项目自报 2026-10-12 实测） | 项目负责人 | 2026-10-31 | 论文 Data Availability 中不引用该缓存路径，仅引用官方仓库地址 |

---

## 16. 参考来源（区分一手/二手，标注证据等级）

### 16.1 一手来源（A 级，本次检索核验）

| 来源 | 著录 | 用途 |
|---|---|---|
| ULT | Huang D., Zhang J.M., Harman M., Zhang Q., Du M., Ng S.-K. *Benchmarking LLMs for Unit Test Generation from Real-World Functions.* TOSEM, 2026. DOI 10.1145/3805043；arXiv:2508.00408；UCL Discovery 10223971 | ULT 协议与 12 模型基线 |
| Ockhamareto | Huang D., Harman M., Zhang J.M., Guo Z., Du M., Ng S.-K. arXiv:2608.24473, 2026-08 | ULT N=5 mutation SOTA |
| TestGenEval | Jain K., Rozière B., Synnaeve G. et al. arXiv:2410.00752, 2024-10；testgeneval.github.io | 覆盖率基准 |
| CoverUp | Pizzorno J.A., Berger E.D. FSE 2025. DOI 10.1145/3729398；arXiv:2403.16218v4 | 覆盖引导 SOTA |
| TestAgent | Xiao L., Fang C., Chen Z., Zhang Q., Zhou J., Gu S., Shang Y. arXiv:2607.09101, 2026-07 | 多智能体 Java 测试生成 |
| MUTGEN | Wang G., Xu Q., Briand L.C., Liu K. IEEE TSE 2026. DOI 10.1109/TSE.2026.3682975；arXiv:2506.02954 | 变异引导 + 100%/4% 发现 |
| CANDOR | Xu Q., Wang G., Briand L.C., Liu K. TOSEM 2026（作者页著录） | oracle 正确性 +21.1pp |
| TOGA | Dinella E., Ryan G., Mytkowicz T., Lahiri S.K. ICSE 2022, pp.2130-2141；arXiv:2109.09262 | oracle 96%/57 bug |
| TOGLL | arXiv:2405.03786, 2024 | oracle 63%/93.4% |
| Tratto | Molinelli D., Martin-Lopez A., Zackrone E., Eken B., Ernst M.D., Pezzè M. ISSTA 2025. DOI 10.1145/3728960；arXiv:2504.04251 | 神经符号 oracle 73/72/61 |
| SPARC | Fu C.-A., Chowdhury J.M., Jabbarvand R. 2026（alphaXiv 著录 ICLR 2026） | +31.36pp 覆盖 vs KLEE |
| Zhao ISSTA'26（误导效应） | Zhao J., Zhou S., Cohen E. *Evaluating and Mitigating the Misguidance Effect of Buggy Code in LLM-Generated Unit Tests.* PACMSE 3(ISSTA), ISSTA113, 2026. DOI 10.1145/3832204；arXiv:2607.22883 | 误导效应 + 规格缓解 |
| Zhao ISSTA'26（相关性复现） | Zhao J., Zhou S., Cohen E. *Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study).* PACMSE 3(ISSTA), ISSTA002, pp.30-53, 2026. DOI 10.1145/3832093；arXiv:2607.22880 | 覆盖/变异相关性限定条件（r=0.780@k=10 已逐位核验：§4.3/Table 7，inter-model、平均聚合、bug-free、k=10，p=0.002） |
| Google SpecOps'26 | Tufano M., McClure J., Cambronero J., Cheng R., Shi S.Y., Wei R., Chen D., Ivančić F., Dalloro L., Rondon P. SpecOps'26. DOI 10.1145/3842652.3843195；arXiv:2608.17177v2；research.google/pubs | Spec-driven +9.8pp |
| SWE-bench 官方榜 | swebench.com（2026-02 快照） | Verified 76.80% 等 |
| SWE-bench Pro | Deng X. et al. PMLR v306（deng26f）；labs.scale.com（Pro v2, 2026-09） | Pro 25.9% / v2 642 任务 |
| LaMAR | Jiao R., Zhang Y., Feng Z., Li J. ASE 2026. DOI 10.1145/3832783.3837423 | KV-cache 潜通信 APR |
| TraceCoder | Huang J., Ye W., Sun W., Zhang J., Zhang M., Liu Y. ICSE 2026；arXiv:2602.06875 | 轨迹驱动调试 |
| TwinMem-Agent | Wu B., Luo Z., Mu F., Xiang L. FSE Companion 2026. DOI 10.1145/3803437.3807664 | 顺序记忆 89.1%/18× 低成本 |
| ADI | Xiang J., Xu X., Chu X., Tian H., Zhang Y. FSE 2026 (PACMSE). DOI 10.1145/3797126；arXiv:2604.24212 | FLT 63.8% Verified |
| LatentMAS | Gen-Verse. arXiv:2511.20639, 2025-11 | 潜协作 +14.6%/−83.7% token |
| LANTERN | Luo W., Keung J.W., Yang B., Klein J., Bissyandé T.F., Tian H., Le B. arXiv:2503.22512, 2025 | xCodeEval Rust +22.09pp |
| xCodeEval | Khan et al. 2023（25M 提交 / 11 语言基准） | 多语言 APR 基准 |
| AgentCoder | Huang D., Zhang J.M., Luck M., Bu Q., Qing Y., Cui H. arXiv:2312.13010, 2024 | 三角色多智能体 |
| LogiCase | Sung S., Aditi, Kim D., Han Y.-S., Ko S.-K. IJCAI 2025. DOI 10.24963/ijcai.2025/861 | CCFG 逻辑描述测试生成 |
| VIGIL | Cruz C. arXiv:2512.07094, 2025-12 | 反射式运行时自愈 |
| Meta ACH | Harman M. et al. FSE 2025 industry track + Meta Engineering 2025-01 | 变异引导 73% 采纳 |
| Di Grazia et al. | USI 博士论文 2025 + ASE 2025 | 13,866 oracle 大规模实证 |

### 16.2 二手来源（B/C 级，仅作方向佐证）

| 来源 | 等级 | 用途 |
|---|---|---|
| TOGA 大规模复评（25 项目 / 51,385 变异体：24% 误分类 / 62% 静默 / 47% 假阳 / +0.3%） | B（未定位一手页） | oracle 有效性衰减 |
| VIGIL 定量结果（100%→0%；97s→8s） | B（单案例预印本） | 自修复机制参照 |
| steel.dev / codesota 聚合榜（Opus 5 96-97%） | B（厂商自报+第三方转述） | SOTA 上界参照 |
| sotaaz.com 对 ISSTA'26 的小模型复现（~一半自写规格固化缺陷） | C | P1 机制佐证 |
| agentpatterns.ai 对 SpecOps'26 的条件化分析 | C | P1 机制佐证 |
| aidlc.io 研究库汇总（供应链/安全指南条目） | C | A-12 依据 |

### 16.3 未独立检索项（建议后续补检）

ESBMC-AI（形式化+AI 修复）；TSC2CARLA；Alloy+LLM 组合测试；RunBugRun / ARC-APR / CI-Bench / HEJ-Robust / LogicEval 基准细节；DEIMerge / PhoenixRepair / FedDualFix / AgentRepair 细节；CrewAI 多智能体 SRE / FTDI 预算感知自修复。检索建议：arXiv cs.SE（2025-2026）+ ACM DL（FSE/ICSE/ASE/ISSTA/TOSEM 2025-2026）+ DBLP + 官方榜单（swebench.com / labs.scale.com）+ 官方仓库（github.com/huangd1999/UnLeakedTestBench、plasma-umass/coverup、Gen-Verse/LatentMAS）。

---

## 17. 评审自身局限性（回应"缺评审自身局限性章节"）

| 局限 | 影响 | 缓解措施 |
|---|---|---|
| **单一评审者**（本报告全部结论由同一评审主体产出） | 无 inter-rater reliability；判断类结论（如"诚信度领先"的权重、规格锚机制的解读）存在评审者偏差风险 | (a) 可复算项全部脚本化（§3.6），他人可重放并挑战；(b) 判断类结论已尽量转为可核验事实（附录 C 对比表）；(c) 建议项目方组织第二评审者对 §5 竞争位置与 §6 路径优先级做独立评级 |
| **子代理核验的间接性**（12 组声明经子代理而非本人逐位重放） | 子代理的数字转述可能存在转录误差 | 核心 7 组（C1-C4/C12/C14/C18）中 C1-C3/C4/C14 已由本人脚本重放（§3.6）；其余组的原始路径与 SHA256 已在 §3.1 标注，可按同标准抽查 |
| **时间切片**（2026-10-17 单日快照） | 项目处于高速迭代（单日 2+ 提交）；本报告的"当前状态"判定有时效 | 所有"当前状态"均带 HEAD（130adbd）与日期锚点；结论中的工件路径可跨时间复算 |
| **未执行的验证** | (a) ruff/mypy 零告警未本地实跑（采信 CI 配置与项目自报）；(b) C7 meta_coverage 未逐行重算（采信 coverage.xml + IR 复算 + 棘轮门禁）；(c) E7 人工裁决、ULT 全量协议未执行 | 三项均标注证据等级（B）并列入 §15；不影响 A 级结论 |
| **领域覆盖** | 自修复子方向仅深核 VIGIL/ADI/ACH；ESBMC-AI、TSC2CARLA、Alloy+LLM、RunBugRun/ARC-APR、DEIMerge/PhoenixRepair/FedDualFix 未展开独立检索 | 已在 §16.3 列出待检索清单与检索建议；这些缺口**未用于**任何对比结论 |
| **语言** | 报告为中文，前沿文献均为英文；术语对照见 §19 | 关键术语首次出现给中英对照 |

## 18. 合规与安全面（回应"安全/隐私维度缺失"）

| 面 | 状态（本次核验） | 判定 |
|---|---|---|
| 密钥管理 | `.env`（1977B）未读取；`.env` 在 `.gitignore`；`check_credential_scrub.py` + `audit_log_redaction.py` + gitleaks 配置三防线在场 | ✅ 未发现泄露面（本次评审未发现任何密钥进入工件/日志） |
| 数据许可 | ULT 官方仓库 MIT（项目 2026-10-12 实测核实，有记录）；QuixBugs vendored 许可登记于 `docs/integration/vendored_quixbugs.md`；The Stack v2 上游条款已在 ult_bridge_plan §4.1 逐条登记；**数据不打包入仓** | ✅ 合规（Q12 待补证据链归档） |
| 外部数据落盘 | `data/`（gitignore）、`~/.cache/aitester/`（LLM 缓存 + ULT 仓库）；缓存目录 0700/文件 0600（S103 豁免有记录） | ✅ 权限收敛有记录 |
| 代码执行安全 | LLM 生成代码经子进程沙箱执行；`run_with_timeout` 进程组终止已全面接管（src/ 裸 subprocess.run 实测为 0，A-17 初版误判已更正）；Docker 可选隔离；**bandit 1.9.4 已在 CI security 作业阻断（R10），本地实跑零 findings** | ✅ 达标 |
| 供应链 | requirements.lock + 三方工具版本门禁 + pip-audit（5 ignored）；无 SBOM（A-12 建议补） | ⚠️ 良 |
| 隐私/伦理 | 无人类受试者（E7 为专家评审，非受试者研究）；无生产/真实用户数据；建议论文补 Ethics Statement | ✅ 达标（建议动作） |
| 模型合规 | deepseek-flash 等商业 API；token 与成本记账完整（真实消耗 + 缓存命中避免量双口径，D2 已收口） | ✅ 良 |

## 19. 术语表（中英对照）

| 术语 | 含义 |
|---|---|
| provenance（溯源元数据） | 批次内嵌的运行环境指纹：git_sha/git_dirty/seed/temperature/env_snapshot/模型指纹 |
| F2P / detection_rate（缺陷检出率） | 项目主指标：生成测试在 buggy 代码上红 ∧ 在 fixed 上绿 ∧ 无收集错误（三段判定，None fail-closed 不进分母） |
| green_on_fut | ULT 桥接口径：生成套件在 `fixed` 上 30s 内终止且全部通过 |
| over_red / specific_red（过红/特异红） | 过红=buggy 红 ∧ fixed 也红（非缺陷特异）；特异红=buggy 红 ∧ fixed 绿 |
| misguided / effective tests（误导/有效测试） | ISSTA'26 定义：misguided=buggy 过 ∧ fixed 败（断言缺陷行为）；effective=buggy 败 ∧ fixed 过 |
| false_fix（假修复） | 补丁使测试变绿但未正确修复缺陷；项目按条件/边际/修正等五口径分列 |
| Mut@k（变异得分） | 被测试杀死的变异体比例；ULT 口径=cosmic-ray 全变异体 + timeout 计 killed |
| 健全门（sanity gate） | 套件须在原码上 30s 内终止且通过才进 Mut@k 分母（防恒红/挂死套件的平凡击杀） |
| MDE（最小可检测效应） | 给定 n 与 power 下可检出的最小效应量 |
| McNemar 精确检验 | 配对二分类数据的精确二项检验（b/c 不一致对） |
| Wilson CI | 比例的 Wilson score 置信区间（小样本下覆盖率优于 Wald） |
| fail-closed | 判定材料缺失时记 None 并退出分母，不记 0 |
| SpecExpr | 项目白名单 AST 子集表达式 DSL（spec_ir_v2），含 BNF 单一事实源 |
| 弃权门（abstain gate） | 补丁不满足提交条件时主动弃权（精确率 86%）而非强行提交 |

## 附录 A：本评审的独立验证记录（可复算）

| 验证项 | 命令/方法 | 结果 |
|---|---|---|
| 测试收集数 | `.venv/bin/python3 -m pytest tests/ --collect-only -q -p no:cacheprovider` | 6799 collected |
| 主批次三臂检出率 + McNemar | 本人 python 脚本（scipy binomtest）解析 `main_batch/benchmark_synthetic_20261006_*.json` 的 `results[arm].details[].detection_rate` | 38/240=15.8%；4/261=1.5%；117/261=44.8%；n10=12/n01=80，χ²_cc=48.79，p=1.7e-13；df vs plain_llm 113:0，p=1.9e-34 |
| git 跟踪状态 | `git ls-files <dir> \| wc -l` | main_batch 2030；e4_FIXED_harness 5；df_spec/M4/D1/ULT-df200 各 0 |
| CI 门禁接线 | grep ci.yml `scripts/gates/` | 22-24 个门禁脚本 + pytest/ruff/mypy/覆盖率棘轮 |
| ULT 工件 | 读 `emse_ult_df200_20261017/ACCURACY_REPORT.json` | 42/200=0.21，green_on_fut，plain_llm_df |
| 前沿引用 | 14 处 WebSearch 一手核验 | 12 处准确；1 处 DOI 待定位；1 处（SpecOps）补验为真 |
| spec_first 行为 | 读 `src/tools/spec_first.py` docstring + 替换逻辑 | replace 模式以 Planner 规约（派生自 buggy 代码）替换目标代码块，确认 |

*报告完。本报告所有项目数据结论以 §3.1 复核表为准；所有前沿数据以 §4 一手来源为准；不可验证项已在 §3.4/§15 明确标注，未用于任何"超越前沿"论断。*

---

## 附录 B：统计补充材料索引

- 复算脚本与输出：`docs/reviews/review_recompute/recompute_core_claims.py` / `recompute_outputs.json` / `recompute_run.log`
- 输入工件 SHA256：见 `recompute_outputs.json` 的 `inputs` 字段（7 个文件）
- 工件清单：`docs/reviews/review_recompute/SHA256SUMS`
- 表格 CSV 源（防纯文本错位）：`audit_claims_C1_C20.csv`（21 行）、`frontier_test_generation.csv`（10 行）、`frontier_apr.csv`（11 行）、`comparison_matrix.csv`（16 行）、`recommendations.csv`（20 行）——由 `export_tables.py` 从本报告抽取生成，正文改动后需重跑

## 附录 C：数据诚信维度对比表（限定"抽查范围内"的强断言）

> 对比方法：按同一 5 维度清单，对本评审一手检索到的 2025-2026 LLM4SE 公开工件做**发布内容**核对（基于本次检索可见的官方仓库/论文补充材料页；标注 B=基于检索快照，未做仓库内部审计）。用途：为 §0.2 第 2 条提供对照，替代无对照的"学术前沿顶部"断言。

| 维度 | AITester | ULT（TOSEM'26） | CoverUp（FSE'25） | TestAgent（arXiv'26） | MUTGEN（TSE'26） |
|---|---|---|---|---|---|
| 结果工件公开 | ✅ 全量批次 JSON + SHA256SUMS（3900+ 入库） | ✅ 12 模型评测结果公开（gold tests 不发布） | ✅ 仓库 + PyPI + 基准 | ⚠️ 预印本，补充材料未见全量工件 | ⚠️ 预印本 |
| provenance（seed/版本/环境指纹） | ✅ 批次内嵌 git_sha/env_snapshot/模型指纹 | ⚠️ 论文级协议描述 | ⚠️ 仓库 README | ❌ 未见 | ❌ 未见 |
| 测量伪影主动披露与修正链 | ✅ 4 起（ADR-0021/0027/0029/0033 + 回归测试） | ✅ 1 起（gold 不可用→项目侧发现并披露） | — | — | — |
| 预注册 | ✅ 5 份独立预注册 + 哈希先于数据 | — | — | — | — |
| CI 门禁/可复现脚本 | ✅ 24 门禁 + 零 LLM 复算链 | ⚠️ 评测脚本在仓库 | ✅ 仓库自带测试 | — | — |

**结论（限定表述）**：在"发布内容的可核验性"这一维度上，AITester 的披露深度（伪影修正链 + 预注册 + 门禁）在本评审核对的 5 个 2025-2026 公开系统中**没有同等先例**；但该判断基于发布内容核对（B 级），非仓库内部审计，且"诚信度"与"方法性能"是两个正交维度——本报告不将其外推为任何性能优势。
