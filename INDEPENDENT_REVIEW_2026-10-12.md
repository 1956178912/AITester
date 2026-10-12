# AITester 独立系统性评审报告（2026-10-12）

> **评审性质声明**：本报告为**独立评审**。评审者不采信项目内任何自评报告、既有评审（`_independent_audit/`、`audit_2026/`、`review_2026/`、`REVIEW_2026_FRONTIER.md`、`FINAL_REVIEW_2026-10-11.md`、`EXTERNAL_REVIEW_2026-10-11.md`、`INDEPENDENT_AUDIT_2026-10-11.md`、`OPTIMIZATION_PLAN_v2.md` 等）的结论；所有项目数据均回溯到原始实验记录/日志/代码/数据独立复算；所有前沿数据均从一手来源（原始论文、官方榜单、官方仓库）独立重建。检索日期：2026-10-12。本环境可联网，2026 年文献经在线检索获得。

---

## 0. 执行摘要

### 0.1 独立评审声明

1. **不信任项目内既有评审数据**：本报告未将任何项目内自评/评审结论作为事实采信。项目性能声明全部回溯到 `experiments/results/` 原始 JSON / 重放脚本独立复算。
2. **不信任既有前沿基线数据**：前沿基线全部由评审者从一手来源（ACM DL / IEEE Xplore / arXiv / 官方 leaderboard / 官方仓库）独立检索重建，未沿用项目文件给出的基线。
3. **独立复核既有结论**：对项目 README / BASELINE.yaml / ADR / 既有评审中的关键结论逐条独立复核（见 §3、§11）。
4. **证据分级**：所有数据点标注 A（一手可验证）/ B（一手不可完全验证）/ C（二手）/ D（不可验证）/ E（推测）。

### 0.2 关键发现（按重要性排序）

| # | 发现 | 证据等级 |
|---|---|---|
| F1 | **项目自身主实验（n=261×3臂×3种子）经评审者独立复算，与 BASELINE.yaml 完全一致**：detection aitester 15.8%（38/240）、plain_llm 1.5%（4/261）、plain_llm_df 44.8%（117/261）。即：**完整多智能体系统比单一"检出优先"提示协议差 28pp**（δ=−0.279）。该阴性结果真实、可复现，且项目已如实披露（ADR-0016） | A（复算自原始 JSON） |
| F2 | **修复率原始口径 0% 系测量伪影已定案**：评审者独立运行 `experiments/corrected_metrics.py` 重放，复现修正口径 repair = 39.31%（57/145，合成集）/ 54.72%（58/106，E1/E2 logic 档）/ false_fix = 87.16%（380/436） | A（重放复现） |
| F3 | **"逻辑驱动"内核薄弱**：spec_compile_rate 仅 0.205–0.219（SpecExpr 白名单 DSL 对 LLM 自然语言规约的编译接受率），即约 79% 的规约子句不可机器化；项目既有真实调用实测（2026-10-11）为 7/8 任务 0.0。该主张目前**不可对外支撑** | B（项目自报+既有实测，评审者未重跑 LLM） |
| F4 | **真实基准差距大**：QuixBugs 修复 success 24%（12/50，评审者复算）；SWE-bench Lite 0/20（基础设施根因，项目已如实披露）。同期前沿：LaMAR（ASE'26）Qwen3-8B 在 QuixBugs 62.1–87.5%；LANTERN（ICSE'26）SWE-bench Lite 36.67% | A（双方） |
| F5 | **工程化与测量纪律处于研究项目顶档**：5489 用例全量收集（评审者实测）、5485 通过、ruff/mypy 全绿、CI 3.12–3.14 矩阵、pip-audit/bandit/gitleaks 硬门禁、BASELINE.yaml 单一事实源、工件 SHA256SUMS 固化、三种子缓存命名空间隔离（seed42/43/44，评审者从 provenance 独立确认——这化解了"多次运行退化为单次"的缓存污染质疑） | A |
| F6 | **项目 README 头部 13 条外部引用经评审者独立核验：全部真实存在、零伪造**；其中 2 处数值/口径瑕疵（Konstantinou 请求数、TestAgent 内部数值冲突）与 1 处待升级（Radaideh 四数值本次经 Carleton 一手报告核实，此前"D 级"可升级为 A/B） | A |
| F7 | **最有价值的"超越前沿"资产不是系统本身，而是其阴性结果 + 测量方法学**：−28pp 编排净负贡献与 ICST'26 复现研究（Plain-LLM 全面优于 HITS/SymPrompt/CoverUp/TestSpark）、BOAD（ICLR'26，手工子智能体反而掉点）构成**三方独立同向证据** | A |

### 0.3 数据可信度总览

| 类别 | 数量 | 可独立验证 | 部分可验证 | 不可验证 |
|---|---|---|---|---|
| 项目性能声明（核心） | 12 条 | 8 条（A/B） | 3 条（B） | 1 条（D） |
| 项目外部引用 | 13 条 | 11 条（A/B） | 1 条（B） | 1 条（D） |
| 前沿基线数据点 | 26 个 | 22 个（A） | 4 个（B） | 0 |

---

## 1. 工作目录与文件清单

### 1.1 扫描方法与范围

- 扫描根：`/Users/wangchenyu/Workspace/AITester`（可访问，git 仓库，461 commits，HEAD `242ce25`）。
- 排除：`.git/`、`__pycache__/`、`.venv/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、`.hypothesis/`、`node_modules/`、`build/`、`dist/`。
- 文件规模：约 7,300 个非缓存文件；`experiments/`（5,999）、`tests/`（540）、`data/`（438）、`src/`（249）、`scripts/`（98）、`docs/`（87）、`tmp_trace/`（63）、`audit_2026/`（26）、`review_2026/`（24）、`examples/`（16）、`_independent_audit/`（6）。

### 1.2 文件树（关键部分，含用途分类与可信度初判）

```
AITester/
├── README.md / README.en.md            # 说明文档（130KB，含性能声明与前沿引用——待复核）
├── BASELINE.yaml                       # 机器可读单一事实源（含全部核心指标声明——待复核）
├── pyproject.toml                      # 配置（PEP 621，依赖/ruff/mypy/pytest/bandit）
├── requirements.txt / setup.py / config.py / main.py / init_db.py
├── Makefile / Dockerfile / Dockerfile.repro / reproduce.sh
├── .github/workflows/{ci,perf,release}.yml   # CI/CD
├── .pre-commit-config.yaml / .git-hooks/ / .gitleaks.toml
├── CHANGELOG.md/.en.md（420KB，版本史）
├── MODEL_CARD.md / DATA_CARD.md / SECURITY.md / docs/threat_model.md   # 合规材料
├── docs/
│   ├── algorithm_design.md             # 设计文档（算法1-3、定理1-2）
│   ├── adr/（29 份 ADR：0001–0029）      # 决策记录（含 ADR-0016 编排降级、0021 修复伪影）
│   ├── design/（15 份：repair_caliber_matrix 等）
│   ├── preregistration.md              # 预注册文档
│   └── citation_allowlist.txt / coverage_ratchet.yaml / env_budget.yaml
├── src/（124 个 .py）
│   ├── agents/（planner/generator/executor/debugger/fault_localizer/fl_spectral/error_classifier…）
│   ├── graph/（workflow 1088 行 / nodes 130419 字符 / state 51981 字符 / patch_io…）
│   ├── specs/（spec_ir / spec_ir_v2 1101 行 / spec_refine / spec_smt 31865 字符）← "逻辑驱动"内核
│   ├── api/ config/ datasets/ cli/ db/ rag/ reports/ observability/ tools/ utils/
├── experiments/
│   ├── run_benchmark.py / analyze_results.py / corrected_metrics.py / repair_replay.py …
│   └── results/（约 5,900 个工件：benchmark JSON / traces / 统计报告 / SHA256SUMS）
├── tests/（269 个 test_*.py）
├── data/（408 文件：swe_bench/quixbugs/synthetic 等数据）
├── examples/（calculator.py 等 3 个含 bug 示例）
├── _independent_audit/（6 文件：项目方 2026-10-11 自行组织的"独立"审计——按本评审原则视为待验证对象）
├── audit_2026/ review_2026/            # 历史评审产物（同上）
├── 根目录评审文档：INDEPENDENT_REVIEW_2026-10-10.md / FINAL_REVIEW_2026-10-11.md /
│   EXTERNAL_REVIEW_2026-10-11.md（471KB）/ INDEPENDENT_AUDIT_2026-10-11.md /
│   OPTIMIZATION_PLAN_v2.md / REVIEW_2026_FRONTIER.md 等（均为待复核对象）
├── tmp_trace/（63 个失败 trace JSONL——运行痕迹，可佐证系统真实运行过）
└── aitester.log / .coverage / coverage.xml
```

### 1.3 含自评数据/既有评审/性能声明的文件标注（后续独立复核对象）

`README.md`、`README.en.md`、`BASELINE.yaml`、`CHANGELOG.md`、`MODEL_CARD.md`、`QUICKSTART.md`、`docs/algorithm_design.md`、`docs/preregistration.md`、`_independent_audit/*`、`audit_2026/*`、`review_2026/*`、`FINAL_REVIEW_2026-10-11.md`、`EXTERNAL_REVIEW_2026-10-11.md`、`INDEPENDENT_AUDIT_2026-10-11.md`、`INDEPENDENT_REVIEW_2026-10-10.md`、`OPTIMIZATION_PLAN_v2.md`、`REVIEW_2026_FRONTIER.md`、`OPTIMIZATION_*.md`、`TEST_REPORT_2026-10-11_ROUND2.md`、`CONSOLIDATED_REVIEW_AND_PLAN.md`。

### 1.4 缺失/不可读文件

- 无关键缺失文件。`.env.local`（812B）与 `.private/` 存在且已被 `.gitignore`（合规）；`.env.local` 内含真实 API 端点配置——**本报告不引用、不披露其中任何内容**。
- `experiments/results/` 被 `.gitignore`，但 `main_batch/` 与 `r4_batches/` 已通过 SHA256SUMS 强制入库（预注册"全部工件入 git"条款的落地），评审者已对两者完成校验性复算。

---

## 2. 项目理解与边界

### 2.1 复述理解

**目标**（据文件归纳，非采信）：构建一个 Python 生态的"逻辑驱动的多智能体测试生成与自修复系统"，通过 Planner（逻辑分析：输入域/输出域/前置/后置/边界）→ Generator（pytest 生成）→ Executor（隔离执行+覆盖率）→ Debugger（分层修复）的 LangGraph 工作流，实现"测试生成 + 缺陷检出 + 自动修复"闭环，并以 M1 三指标（detection_rate / repair_rate / false_fix_rate）诚实评估。

**实际边界（据代码与数据独立判断）**：
1. 系统真实存在且可运行（18 个 LLM 组件、LangGraph 编排、venv/Docker 沙箱、RAG、谱系+推理双通道定位、跨文件修复、SMT 见证层）。
2. 其**主实验口径已从"多智能体增益"收缩为"检出优先提示协议增益"**（ADR-0016）：完整系统在检出口径下净负 28pp；项目自述定位为"可消融编排容器"。
3. "逻辑驱动"目前主要体现为：Planner 的 NL 逻辑分析 + SpecExpr 白名单 DSL 编译（spec_compile_rate ~21%）+ z3 后件一致性检查（spec_smt）+ CEGIR 反例精化（spec_refine，默认关）。
4. 自修复为"局部化→合成→验证"三段式，修正口径修复率 39.31%（合成集）。

### 2.2 关键假设（红队审查入口）

- A1：LLM 生成的测试能在缺陷代码上变红（检出）——主实验显示仅 plain_llm_df 44.8% 达成。
- A2：多智能体编排相对单提示有增益——**被项目自身实验与三项前沿独立证据否证**（见 §4、§6）。
- A3：NL 规约可机器化为可执行 oracle——当前编译率 21%，假设基本不成立（需文法升级）。
- A4：合成集（50 模板）性能可外推到真实基准——QuixBugs/SWE-bench 结果（24% / 0-20）显示外推差距大。
- A5：`success`（测试在最终代码上通过）可作为修复成功的代理——false_fix 87.2% 证明该代理失效。

---

## 3. 项目数据独立审计

### 3.1 性能声明复核表

| 声明编号 | 所在文件/位置 | 声明内容 | 原始记录 | 可复现性 | 证据等级 | 复核结论 | 是否可用于对比 |
|---|---|---|---|---|---|---|---|
| C1 | BASELINE.yaml benchmark 节；README:56 | detection：plain_llm_df 44.8%（117/261）> aitester 15.8%（38/240）> plain_llm 1.5%（4/261）；三种子合并 n=261/臂 | `main_batch/benchmark_synthetic_20261006_{140906,151907,164357}.json` | **可复现**（评审者逐文件复算，数值逐位一致） | A | **独立验证通过** | 是（合成集口径） |
| C2 | BASELINE.yaml；ADR-0021/0027/0029 | repair 修正口径 39.31%（57/145）；E1/E2 54.72%（58/106）；原始口径 0% 系 patch 围栏伪影 | `experiments/corrected_metrics.py` + `corrected_report_v2.md` | **可复现**（评审者实跑重放，输出一致） | A | **独立验证通过**（伪影定案可信） | 是（须带口径：合成集/gold 裁决/145 可重放行） |
| C3 | BASELINE.yaml | false_fix 修正 87.2%（380/436）；CPR 84.51%；弃权精确率 85.97% | 同上重放报告 | 可复现（评审者实跑） | A | 独立验证通过 | 是 |
| C4 | BASELINE.yaml target_quality 节 | 被测代码行覆盖：aitester 84.0–93.6% / plain_llm 86.0–97.2% / df 81.5–93.6%（10 批次区间） | 各批次 JSON `details[].coverage` | 部分可复现（区间性声明，评审者抽查 10-06 三批次 avg_coverage 与区间一致） | B | 独立验证通过（合成集） | 仅合成集口径；**不可外推真实基准** |
| C5 | BASELINE.yaml | mutation score：aitester 0.818–0.976 / plain_llm 0.951–0.992 / df 0.986–0.997（合成变异体，项目自注"过弱、鉴别力有限"） | 批次 JSON `mutation_score` | 部分可复现（QuixBugs 批次评审者实测逐任务值存在且为 0/1 分布，印证"弱变异体"自注） | B | 数值可信但**项目自注的鉴别力问题成立**（变异体过弱 → 该指标在合成集上近饱和） | 否（项目自认需在 ULT/TestGenEval 重测） |
| C6 | BASELINE.yaml；docs A-01 | spec_compile_rate 0.205–0.219（E1/E2 logic 档四批次） | 批次 JSON `spec_compile_rate` | 部分可复现（字段存在；评审者未逐批重算 LLM 规约编译） | B | 独立验证通过；且方向被强化：项目 2026-10-11 真实调用实测 7/8 任务为 0.0，既有实测全量 1,607 行中位数 0.200、47.6% 为 0 | 是（作为"逻辑驱动"当前水位） |
| C7 | README:56；BASELINE.yaml | SWE-bench Lite（sqlfluff-20）真实基准 0/20，如实披露 | `swebench_20_summary.json`（2026-08-17，0/7 completed 因 429 限流）+ `benchmark_swe_bench_20260925_184622.json`（0%）+ `analysis/swe_lite_root_cause_2026-10-05.md` | 可复现（工件在） | A | **独立验证通过**（且根因分析可信：17/20 coverage=0.0、18/20 patch_validation_failed、原始切片 ast.parse 全过 → 写入链路伪损坏，非 LLM 能力边界） | 是（作为负面结果） |
| C8 | git log 81b1cc7；r4_batches | QuixBugs "真实修复率 72-74%" | `r4_batches/r4_qb_arm_{a,b}/benchmark_quixbugs_*.json` | **部分复现且口径需澄清**：评审者复算 success_rate=24%（12/50）、raw patch_correct=0（伪影）；72-74% 出自 replay 的"包结构口径"子集（分母远小于 50），commit message 未注明分母 | B | **口径不完整**：24%（12/50，主口径）与 72-74%（窄口径）并存，对外引用必须带分母，否则构成选择性陈述 | 是（仅 24% 主口径） |
| C9 | BASELINE.yaml tests 节 | 全量 5485 passed / 3 skipped / 1 xfailed / 0 failed；--collect-only 5489 | 评审者实跑 `pytest --collect-only -q` | **可复现**（实测 5489 collected） | A | 独立验证通过 | 是 |
| C10 | BASELINE.yaml static_checks 节 | ruff 0 警告（0.16.3）/ mypy 0 错误（125 源文件） | CI 配置 + 本地可复跑 | 未完整复跑全量（成本考虑）；抽样核对了 pyproject 规则集与 CI 接线真实性 | B | 可信（CI 门禁真实存在且严格） | 是 |
| C11 | BASELINE.yaml benchmark 节 | 成本 $/task：aitester 0.0259 / plain_llm 0.0034 / df 0.0045（价目表官方登记口径） | 批次 JSON `token_metrics` | 部分可复现（token 数在 JSON 中；单价换算依赖外部价目表，评审者未独立核价） | B | 数值方向可信（aitester token 26.1k vs df 4.2k，8.1×/6.2× 比例与 ADR-0016 一致） | 是（相对比例） |
| C12 | BASELINE.yaml；README:59 | 日志脱敏三层防线、凭证剔除、无硬编码密钥 | 代码在（credential_scrub / SensitiveFilter 等）+ `.gitignore` + gitleaks CI | 未逐条复跑；结构性核对了 `.env*`/`.private` 的 gitignore 状态与 CI 门禁存在性 | B | 可信（门禁真实；残留风险：LLM 文件缓存被项目自列为"已知可接受风险"） | 是 |

**无法验证声明清单**：
- U1：`spec_expr_coverage` 0.723–0.741 的逐批复算（未重跑 LLM，B 级采信项目自报）。
- U2：C8 的 72-74% 窄口径分母（项目未在 commit/报告中注明分母，无法还原 → D 级，不得单独引用）。
- U3：`localization_hit_function` / `fl_at_k` / Hit@3 / MRR 等定位指标的全批数值（R-P0-2 批 FL 观测覆盖 0/154，项目自报"口径缺口非真实为 0"——评审者采信该自注，列为部分可验证）。

### 3.2 三种子独立性专项核查（回应既有审计 L5 质疑）

项目 2026-10-11 自有审计 L5 提出"LLM 缓存使多次运行退化为单次运行，三种子独立采样需重新审视"。**评审者独立核查 provenance**：三个主批次 `cache_namespace` 分别为 `seed42/seed43/44`（`cache_enabled=true`、`cache_isolate_model=true`）→ **三种子 LLM 缓存相互隔离，种子间 LLM 响应确为独立采样**；种子差异体现在任务抽样（task_id 集合不同）。temperature=0 下同种子内重复 prompt 命中缓存属确定性优化，不影响种子间独立性。**结论：L5 质疑对主批次不成立（A 级）；但同一质疑对未设 namespace 的历史批次仍可能成立**，引用历史数字时须逐批核查 namespace。

### 3.3 项目方法独立评估（读代码，不依赖描述）

| 声称 | 代码实际 | 一致性 |
|---|---|---|
| 逻辑驱动思维链（Algorithm 1） | `planner.py` 的 `plan()` 为 LLM 提示链 + SpecExpr 文法契约段（W2/T1 后含 BNF/正反例/自检四件套，工程质量高） | 一致；但"逻辑"止于提示层，机器化靠白名单 DSL（`spec_ir_v2.py`：11 个纯函数白名单 + 属性白名单 + 200 字符上限），表达力受限 → 编译率 21% 的根因在**文法设计**而非提示 |
| 分层错误修复（Algorithm 2/3） | `error_classifier.py` 规则分类（18 类）+ `debugger.py` 分层策略 + `workflow.py` `_should_debug()` 迭代路由；补丁安全核心在 `patch_io.py`（路径白名单+原子写+快照回滚） | 一致；路由信号有结构化优先开关（ROUTE_STRUCTURED_ENABLE），工程质量好 |
| 多智能体（5 智能体） | LangGraph 图 + 专家池/辩论/多候选/跨文件协调器等**默认关**组件群 | 一致；但主实验证明默认配置下编排净负 → "多智能体"目前是**能力容器**而非增益来源（项目 ADR-0016 已承认） |
| 定理 1（完整性） | "若 LLM 能力足够则存在修复路径" | **该"定理"是同义反复**（假设已包含结论），不构成可证伪的理论保证；定理 2（终止性）平凡成立（MAX_ITERATIONS=3 硬上界）。科学性缺陷：算法文档应删去或改写为收敛性经验命题 |
| AST 精确替换 | `code_analyzer.py` / `patch_applier.py` 真实实现 | 一致 |
| RAG | ChromaDB 单例 + TTL；A/B 实测 token +40.7% 负向 → 默认关 | 一致且诚实 |

---

## 4. 2025-2026 前沿基线表（独立重建）

> 全部数据点由评审者于 2026-10-12 从一手来源检索。同一指标多来源时并列；冲突见"冲突说明"。

### 4.1 测试生成子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 | 交叉验证来源 | 冲突说明 |
|---|---|---|---|---|---|---|---|---|
| CANDOR（多智能体 JUnit 生成） | line/branch/mutation | 0.991 / 0.970 / 0.980（2384/2443） | HumanEvalJava | arXiv:2506.02943；DOI 10.1145/3803418 | 2026 / ACM TOSEM | A | ACM DL 摘要 + arXiv 全文表 1 | 无 |
| CANDOR | mutation / oracle | 0.939 / oracle 0.930 | LeetCode-Medium | 同上 | 2026 / TOSEM | A | 同上 | 无 |
| TestAgent（Planner-Generator-Reviewer 三智能体） | execution/line/branch/mutation | 97.46% / 92.34% / 90.24% / 83.69% | 6 个 Java 项目，1,451 方法 | arXiv:2607.09101；DOI 10.1145/3803437.3806428 | 2026 / FSE Companion | A（line 等主值）；mutation 83.69% 仅见于 arXiv 版摘要（B） | ACM DL 摘要（92.34%/154 bugs@92.22%）+ arXiv TLDR | **项目内部冲突**：BASELINE.yaml 记 TestAgent 88.85%/55.4%，README 记 92.34%/83.69%；一手来源仅支持后者（88.85/55.4 不可溯源，D 级） |
| CoverUp（覆盖率反馈 LLM） | line+branch（overall / per-module median） | 89–90%（vs MuTAP 77%）/ 80%（vs CodaMosa 47%） | 开源 Python 项目基准 | arXiv:2403.16218；DOI 10.1145/3729398 | 2025 / FSE | A | ACM DL + FSE program | 无 |
| ULT 基准（12 个 SOTA LLM 平均） | accuracy/stmt/branch/mutation | 41.32% / 45.10% / 30.22% / 40.21% | ULT 3,909 个真实 Python 函数（去污染） | DOI 10.1145/3805043 | 2026 / ACM TOSEM | A | ACM DL 摘要 | 无 |
| ULT 对照 | 同四指标 | 91.79 / 92.18 / 82.04 / 49.69（TestEval）；47.07 / 55.13 / 40.07 / 50.80（PLT） | TestEval / PLT | 同上 | 2026 / TOSEM | A | 同上 | 无 |
| TestGenEval（Meta） | GPT-4o 平均覆盖 | 35.2% | 68,647 tests / 1,210 对 / 11 仓库 | ICLR 2025 proceedings（Jain, Synnaeve, Rozière） | 2025 / ICLR | A（经 ICLR proceedings 页核验） | — | 无 |
| MUTGEN（变异引导生成） | 定性锚点 | "100% coverage 但仅 4% mutation score"的套件确实存在；204 subjects 上超越 EvoSuite 与 vanilla prompt | 两个基准（204 subjects） | arXiv:2506.02954；DOI 10.1109/TSE.2026.3682975 | 2026 / IEEE TSE | A | SciRate + IEEE Xplore | 原文为"100% coverage"，项目 BASELINE.yaml 加注"行覆盖"属口径强化（引用时应保留原文措辞） |
| Plain-LLM vs 四工具复现研究 | line/branch/mutation | Plain-LLM **49.95 / 35.33 / 33.82** vs HITS 42.43/29.49/27.97、SymPrompt 40.95/27.19/28.40、TestSpark 23.65/16.48/13.88、CoverUp 38.85/25.11/26.26 | 6 个 Java 仓库，393 类，3,657 方法 | arXiv:2601.09695v2；DOI 10.1109/ICST69053.2026.00040 | 2026 / IEEE ICST | A（三覆盖值） | ORBilu 机构库 + ICST program | **请求数冲突**：项目 README 记 Plain-LLM 11,718 vs CoverUp 12,264；论文 v2 正文为 11,815 vs 12,741（HITS 16,735、SymPrompt 5,602、TestSpark 7,023）——定性结论（Plain-LLM ≤ CoverUp）成立，绝对值项目引用有误（评审者本次未直接取得正文表格，请求数按 B 级采信既有审计对正文的逐字转录） |
| IEEE 独立复现（Radaideh, Corriveau & Shi） | mutation score | Gemini 2.5 Flash one-shot **88.35%**（182/206）；GPT-4o one-shot 69.90%；CANDOR 45.63%（GPT-4o）/ 35.92%（Gemini）；人类参考套件 83.98%；line 95.65% / branch 78.05%（Gemini one-shot） | 25 类 Java 系统，206 个 PiTest 变异体 | IEEE Xplore doc 11655121（BDAI 2026）+ Carleton 大学报告页（含完整数值） | 2026 / IEEE BDAI | A/B（论文存在性 B；四数值经 Carleton 一手项目报告核实 → 升级为 A/B） | IEEE 作者页 + report-hub.scs.carleton.ca | 项目 README 引用与 Carleton 报告逐位一致（此前"D 级"在本评审中升级）；论文自身声明"observed configuration effect rather than evidence that iteration is intrinsically harmful" |
| SPARC（神经符号 C 测试生成） | line/branch/mutation 提升 | +31.36pp / +26.01pp / +20.78pp（vs vanilla prompt）；复杂 subjects 上匹配或超越 KLEE；94.3% 测试经迭代修复保留 | 59 个真实/算法 C subjects | arXiv:2602.16671 | 2026 / 预印本 | B | alphaXiv 作者页 | 无（未经同行评审） |
| Ockhamareto（RL 测试生成） | mutation @N=5 / 平均测试数 | 49.9% vs MIST-RL 31.3%；2.60 vs 4.67 tests；4B/9B/27B 上 +30–35pp | ULT、HumanEval+、MBPP+、CodeContests、TestGenEval-Lite | arXiv:2608.24473（标注 TOSEM） | 2026 / 预印本（TOSEM 在审） | B | arXiv HTML | 无 |
| Meta ACH（工业界变异引导） | 工程师接受率 | 73%（10,795 个 Kotlin 类，9,095 变异体，571 硬化测试） | Meta 内部 | FSE 2025 program（Harman et al. 产业论文） | 2025 / FSE | A | conf.researchr.org program | 无 |

### 4.2 多智能体协作与修复子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 | 交叉验证来源 | 冲突说明 |
|---|---|---|---|---|---|---|---|---|
| RepairAgent（自主智能体修复） | 修复数 / 成本 | 164/835 Defects4J（含 39 个此前未修复）；270k tokens/bug ≈ $0.14/bug | Defects4J v1.2+v2.0 | arXiv:2403.17134；DOI 10.1109/ICSE55347.2025.00157 | 2025 / ICSE | A | OpenReview + ICSE program | 无 |
| LANTERN（跨语言翻译+多智能体） | Pass@10 | Python 81.28→99.23；Rust 67.79→86.09（+22.09pp）；D4J v1.2 141→170、v2.0 54→60；SWE-bench Lite 110/300（36.67%）vs Agentless 95/300（31.67%） | xCodeEval 5,068 bugs/11 语言；D4J；SWE-bench Lite | arXiv:2503.22512；DOI 10.1145/3744916.3773227；artifact: github.com/stringing/LANTERN | 2026 / ICSE | A | ACM DL + arXiv 表 2/3 | 无 |
| LaMAR（KV-Cache 潜在空间通信） | repair success | Qwen3-8B：Defects4J 24.5%；DebugBench/QuixBugs 62.1–87.5%；token 复杂度 O(N²)→O(N) | D4J、DebugBench、QuixBugs，3 模型族 | DOI 10.1145/3832783.3837423（ASE'26 program） | 2026 / ASE | A | ACM DL + ASE program | 无 |
| TraceCoder（轨迹驱动调试） | Pass@1 相对提升 | 最高 +34.43%（vs Self-Debugging/INTERVENOR）；迭代修复单独贡献 +65.61% 相对增益 | 多基准（class-level codegen） | arXiv:2602.06875 | 2026 / 预印本 | B | HF papers + arXiv HTML | 无 |
| BOAD（bandit 自动发现智能体层级） | Verified/Live resolved | Seed-OSS-36B：53.2% / 20.0%（baseline 49.8%/12.3%；**手工加子智能体 47.4%——反而掉点**）；2 个子智能体为最优规模 | SWE-bench Verified / SWE-bench-Live | arXiv:2512.23631；OpenReview O6stE173BD；github.com/iamxjy/BOAD-SWE-Agent | 2026 / ICLR | A | IBM Research 出版页 + arXiv 表 1 | 无 |
| Agentless（极简管线基线） | SWE-bench Lite | 95/300 = 31.67% | SWE-bench Lite | LANTERN 论文表 3 转录 | 2025 / arXiv:2407.01489（经 LANTERN 交叉） | A | LANTERN 表 3 | 无 |
| SWE-bench 官方 leaderboard（SOTA 参照） | % Resolved（full 2294） | Claude 4.5 Opus + mini-SWE-agent **76.80%**（$0.75/task，2026-02-17）；Gemini 3 Flash 75.80%；MiniMax M2.5 75.80%（$0.07） | SWE-bench full | swebench.com 官方榜 | 2026（持续更新） | A（官方榜） | steel.dev / codesota 追踪站（C 级旁证：Claude Mythos 93.9%、Opus 4.7 87.6% 等自报值） | 第三方追踪站数值高于官方榜（自报/内部模型），采信以官方榜为准 |
| SWE-rebench（去污染基准） | Resolved | DeepSeek-V3-0324：Verified 39.7% vs SWE-rebench 21.3%（**−18.4pp 污染膨胀**） | SWE-bench Verified vs SWE-rebench Mar–Apr 2025 | arXiv:2505.20411（NeurIPS 2025） | 2025 / NeurIPS | A | arXiv HTML 表 2 | 无 |
| SWE-bench-Live（持续刷新） | — | 月度自动更新；2026-08 起提交须附 rollout 轨迹防作弊 | 多语言/多 OS | swe-bench-live.github.io；arXiv:2505.23419 | 2025–2026 | A/B | 官方站 | 无 |

### 4.3 自修复系统子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 | 冲突说明 |
|---|---|---|---|---|---|---|---|
| VIGIL（反思式运行时） | 过早通知率 / 事件延迟 | 100%（12/12）→ 0%；均值 97s → 8s | 单智能体案例研究（Robin-A） | arXiv:2512.07094 | 2025-12 / 预印本 | B | 无（n=1 案例，非同行评审） |
| ESBMC-AI（BMC+LLM 自愈） | 修复能力 | 50,000 个 FormAI C 程序上自动检测/修复 buffer overflow、arithmetic overflow、pointer deref，"high accuracy"（摘要未给单值） | FormAI | DOI 10.1109/AST66626.2025.00020（AST 2025） | 2025 / IEEE/ACM AST | A（存在性+方法）；具体成功率数值摘要未给 → 部分 D | 无 |
| 对照项：mini-SWE-agent | 成本效率 | 100 行 Python 达 Verified 65%（2025-07） | SWE-bench Verified | swebench.com news + GitHub | 2025 | A | 无 |

**本子方向一手量化数据最稀薄**（评审者独立判断）：MTTR / detection latency / diagnosis time / quality of recovery 等 SRE 口径指标在 2025-2026 一手论文中极少给出可比值（多为例示性案例研究）。项目若以"自修复评估指标"为创新点，**存在先占机会**（见 §6 路径 P5）。

### 4.4 逻辑驱动测试生成子方向

| 前沿方法/系统 | 关键指标 | 指标值 | 评测基准 | 一手来源 | 年份/venue | 证据等级 | 冲突说明 |
|---|---|---|---|---|---|---|---|
| LogiCase（CCFG 形式化+CodeT5） | 方法 | NL 规约 → Context-Free Grammars with Counters → 系统性生成 valid/effective 测试；CodeContests 上优于基线 | CodeContests | arXiv:2505.15039；DOI 10.24963/ijcai.2025/861 | 2025 / IJCAI | A | 无 |
| Zhao/Zhou/Cohen（misguidance effect） | 核心发现 | buggy code 入提示会同时**增加误导性测试（断言错误行为）并抑制有效 bug-finding 测试**；缓解范式 = 用 LLM 生成规约 docstring **替换提示中的被测代码** | LLM 生成测试（D4J 等） | ISSTA 2026 论文 #2（U. Toronto；Zenodo 复现包 10.5281/zenodo.21429528） | 2026 / ISSTA | A | 无 |
| Zhao/Zhou/Cohen（覆盖-变异相关性复现） | 核心发现 | 覆盖/变异与真实缺陷检出的相关性**高度依赖场景**：回归设定（代码可假定无缺陷）下跨模型比较有效；被测代码可能有缺陷时**不可靠**；套件规模非主导混淆项 | 大规模复现（Inozemtseva/Papadakis 两项前人研究） | DOI 10.1145/3832093；arXiv:2607.22880；Zenodo 10.5281/zenodo.21437945 | 2026 / ISSTA（Distinguished Paper） | A | **项目引用口径瑕疵**：BASELINE.yaml 引 "branch vs raw mutation r=0.780 @k=10，控制规模后"——该数值在可及一手材料中不可定位（D）；且"控制规模后"表述与论文"规模非主导混淆项"结论有张力（见 §11） |
| SPARC（CFG+路径场景） | 见 §4.1 | +31.36pp line 等 | 59 C subjects | arXiv:2602.16671 | 2026 / 预印本 | B | 无 |
| TSC2CARLA / Alloy 组合测试 / Tratto | — | 项目提示词列为参考方向 | — | 评审者本次未检索到 2025-2026 一手可比值（TSC2CARLA 为 2023 前后工作；Tratto 为既有 neural-symbolic oracle 工作） | — | **D（未独立重建，不构成基线）** | 列为待澄清/待检索项（见 §15） |

### 4.5 评估与基准子方向

| 基准/方法 | 指标 | 值 | 一手来源 | 年份/venue | 证据等级 |
|---|---|---|---|---|---|
| SWE-bench Verified（官方） | SOTA | 76.80%（Claude 4.5 Opus + mini-SWE-agent，full set） | swebench.com | 2026 | A |
| SWE-bench Verified 弃用声明 | — | OpenAI 发布 "Why we no longer evaluate SWE-bench Verified"（污染/饱和） | openai.com/index（页面存在；正文本次 403 未取得） | 2026 | B（存在性）/ D（具体日期 2026-02-23 不可核实） |
| xCodeEval | 规模 | 5,068 bugs / 11 语言 / 平均 50 tests per problem | LANTERN 论文表 1 | 2025-2026 | A |
| QuixBugs | 前沿修复率 | LaMAR（Qwen3-8B）62.1–87.5% | ASE'26 LaMAR | 2026 | A |
| DebugBench | 前沿修复率 | LaMAR 62.1–87.5%（与 QuixBugs 同区间声明） | 同上 | 2026 | A |
| RunBugRun / ARC-APR / CI-Bench / HEJ-Robust / LogicEval | — | 项目提示词列为参考方向；评审者本次未逐一重建（部分为 2025 前或小规模工作） | — | — | **D（未独立重建）**，列入待检索 |
| slopsquatting（供应链） | 幻觉包名率 | 19.7%（2.23M 样本 / 16 LLM；205,474 唯一幻觉名；43% 在 10 次重跑中全部复现） | USENIX Security 2025（Spracklen et al.，"We Have a Package for You!"） | 2025 / USENIX Security | A（README 原标[待核验]，本评审升级为已核验） |

---

## 5. 项目与前沿量化对比矩阵

| 维度 | 2025-2026 前沿 SOTA | 证据等级 | 项目现状（可验证口径） | 项目证据等级 | 绝对差距 | 相对差距 | 竞争位置 | 超越路径编号 | 可否对比 |
|---|---|---|---|---|---|---|---|---|---|
| 测试生成-line coverage（真实函数） | CoverUp 89–90% line+branch overall；ULT LLM 均值 stmt 45.10% | A | 合成集 84.0–93.6%（aitester）/ 86.0–97.2%（plain_llm）；真实基准（SWE-bench lite-20）17/20 = 0.0 | B（合成集区间）；A（0/20） | 真实基准上约 −90pp（vs CoverUp 口径） | — | **落后**（合成集数字不可外推） | P1 | 否（基准不同：合成模板 vs 真实仓库） |
| 测试生成-mutation score（真实函数） | ULT LLM 均值 40.21%；Ockhamareto 49.9%@N=5；CANDOR 0.980（HumanEvalJava） | A/B | 合成集 0.818–0.976（项目自注变异体过弱、近饱和） | B | 无法计算（项目合成变异体与 ULT/PiTest 变异体不同源） | — | **不可比**（项目自认需外部基准重测） | P2 | 否 |
| 测试生成-fault detection（fail-to-pass） | TestAgent：154 真实 bug @92.22% precision；Radaideh：one-shot mutation 88.35% | A/B | df 协议 44.8%（n=261 合成）；aitester 15.8%；plain_llm 1.5% | A（复算） | 与 TestAgent 不可直接比（指标定义不同：合成 F2P vs 真实 bug 检出） | — | **中游**（合成集内部分层清晰；真实 bug 检出未测） | P1 | 部分（仅同口径内部对比有效） |
| 测试生成-compilation/execution rate | TestAgent 97.46% execution；CANDOR 编译率经初始化循环保证 | A | 未作为一等指标报告（test_error_rate 存在但非主口径） | D（未报告） | — | — | **不可比** | P1 | 否 |
| 多智能体修复-repair success（真实基准） | LaMAR QuixBugs 62.1–87.5%（Qwen3-8B）；LANTERN SWE-bench Lite 36.67%；Agentless 31.67%；RepairAgent D4J 164/835=19.6% | A | QuixBugs 24%（12/50）；SWE-bench Lite 0/20；合成集修正 39.31% | A（QuixBugs 复算）；A（0/20） | QuixBugs：−38.1pp（vs LaMAR 下界 62.1%） | −61%（相对下界） | **显著落后** | P3/P4 | 是（QuixBugs 与 SWE-bench Lite 为共同基准） |
| 多智能体修复-false fix / Top-1 precision | 前沿以 gold 测试/回归套件裁决（SWE-bench F2P+P2P） | A | false_fix 87.2%（修正口径，passed 行 380/436）；"假成功通道"实证 | A（重放） | — | — | **方法论亮点**（87.2% 假修复率是领域少见的诚实负面度量） | P5 | 否（前沿少报同指标） |
| 多智能体协作-通信效率 | LaMAR：O(N²)→O(N) token；BOAD：自动发现 2 子智能体最优、手工掉点 | A | LangGraph 文本消息；编排净负 −28pp（token 6.2×） | A | 通信复杂度差一个量级（未实现潜在空间通信） | — | **落后**（但方向已被 BOAD/ICST'26 背书为"应做减法"） | P4/P6 | 部分 |
| 自修复-detection latency / MTTR | VIGIL：97s→8s（案例）；ESBMC-AI：BMC 闭环（无数值） | B | 无同口径指标（项目为代码修复域，非运行时 SRE 域） | D | 不可计算 | — | **不可比** | P5 | 否 |
| 逻辑驱动-规约机器化率 | LogiCase：CCFG 形式文法（NL→文法，fine-tuned）；SPARC：CFG 路径枚举 | A/B | spec_compile_rate 20.5–21.9%（白名单 DSL）；spec_expr_coverage 72.3–74.1% | B | 与 LogiCase 不可直接比（口径不同）；但"逻辑驱动"可执行化深度明显低于 SPARC 的路径级 | — | **落后** | P1/P7 | 否 |
| 逻辑驱动-SMT/形式化验证 | ESBMC-AI：BMC+SMT 闭环修复（50K 程序） | A | z3 仅用于后件一致性 UNSAT 检测与见证层（默认关、无修复闭环） | B | 缺"反例→修复→复验"完整闭环的**大规模**验证（ESBMC-AI 有 50K） | — | **落后** | P7 | 部分 |
| 工程化-可复现性 | SWE-rebench/Live 的时间戳去污染与轨迹强制提交；ICST'26 复现包 | A | 三种子+缓存隔离+口径矩阵+ADR 勘误链+SHA256SUMS+预注册；但 git_dirty=true（已披露）与 results 目录 gitignore（部分入库） | A/B | — | — | **领先**（研究工程纪律顶档；去污染与轨迹提交机制可向 SWE-rebench 协议对齐） | P8 | 是 |
| 工程化-cost per repair | mini-SWE-agent $0.75/task（76.80%）；MiniMax M2.5 $0.07；RepairAgent $0.14/bug | A | $0.0259/task（aitester，合成集，15.8% 检出）vs $0.0045（df，44.8%） | B（价目表依赖） | 绝对值低但**有效性也低**：df 以 1/6 成本取得 2.8× 检出 | — | **成本效率劣于自身轻量基线** | P8 | 否（口径不同） |
| 评估-污染控制 | ULT/TestGenEval-Live/SWE-rebench 时间戳去污染；SWE-bench Verified 被 OpenAI 弃用 | A | 有 contamination_check（Jaccard）与 difficulty_stratification；合成集自建（无时间戳去污染） | B | 缺"新鲜任务切片"协议 | — | **落后**（但工具已在） | P8 | 是 |

---

## 6. 超越前沿方法设计

> 每条路径均基于 §4 一手来源或第一性原理；预期提升标注置信度与证据等级；反事实推演与独立验证判定标准齐备。**项目自身 −28pp 阴性结果与 BOAD/ICST'26 证据共同表明：超越前沿的路径不是"加强编排"，而是"加强协议层与评测层"。**

### P1 规格优先生成（Specification-First Generation）——直击"48.6% 行全绿未检出"

- **技术路径**：将 Generator 提示中的**被测（缺陷）代码替换为恢复出的规约文档**（NL docstring + SpecExpr 形式子句 + 边界锚点），测试生成只依据规约与签名，不依据实现。依据：Zhao/Zhou/Cohen（ISSTA'26 #2）证明 buggy code 入提示会诱发"misguided tests"（断言错误行为）并抑制有效测试；AITester 自身数据（BASELINE specificity_gate 节）显示 aitester 臂 296/609 行（48.6%）两版生成测试在缺陷原码上全绿（df 臂仅 2.5%）——与 misguidance effect 的机制描述完全吻合。
- **差异化点**：既有工作（Zhao et al.）用 LLM 生成 docstring 替换代码；本项目在此之上叠加**可编译规约 DSL（SpecExpr）+ CEGIR 反例精化 + 特异性门/红回归门双门**，即"规约恢复 → 形式化 → 反例回灌"全链，且双门为环路内路由而非事后评估。
- **理论基础**：misguidance effect（A 级一手）；oracle-from-implementation 陷阱（项目 L1 实测 0/18，A 级）。
- **预期性能提升**：合成集 detection 从 df 44.8% → **≥60%**（规格优先 + 双门消除过红/抹红两通道；双通道机制占缺口 201 行中的 44.2%+26.1%，反事实分解见 BASELINE）。置信度：**中**（机制有 A 级依据，幅度为 E 级推测——依据为项目自身反事实分解的比例外推）。
- **实验验证**：基准 = ULT（3,909 真实函数，去污染）+ 项目合成集；对照 = plain_llm_df（项目协议）/ CANDOR 式 vanilla prompt / Zhao et al. 的 docstring-only 变体（其复现包 Zenodo 21429528）；指标 = fail-to-pass detection、misguided-test 率、spec_compile_rate；统计 = McNemar + BH-FDR（沿用项目既有协议）；可复现 = 3 种子 + 缓存 namespace 隔离 + temp=0。
- **反事实推演**：若前沿采用同规格优先策略，项目剩余优势 = 双门环路内路由与规约 DSL 的可编译率工程；护城河 = 测量与门控工程（可复制，约 1-2 个迭代周期）。
- **里程碑**：短期（1-3 月）：docstring-only 替换臂 A/B（复用既有 harness）；中期（3-6 月）：SpecExpr v3 文法（关系型/量化子句）+ 双门默认注入；长期（6-12 月）：ULT 外部基准 detection ≥55% 并发表。
- **独立验证判定**：**成功** = ULT 上 detection 显著高于 df 臂与 docstring-only 臂（McNemar p<0.01，δ≥+10pp）且 spec_compile_rate ≥0.55；**失败** = 任一基准上不优于 df 臂，或编译率 <0.35 表明文法升级失效。

### P2 变异得分作为第一公民指标（Mutation-First Oracle Loop）

- **技术路径**：将 MUTGEN 式变异反馈注入 Generator/Debugger 提示（项目已有 `experiments/mutation_testing.py` 与 `mutation_advisor.py` 零 LLM 变异生成器，但默认关且观测覆盖 0/154），并按 Ockhamareto 的 Pareto 口径（mutation vs −#tests）做测试最小化。
- **依据**：MUTGEN（TSE'26，A）：100% 覆盖 4% 变异得分的套件真实存在；Ockhamareto（B）：ULT 上 49.9% vs 31.3%；ULT 基准（A）：LLM 均值仅 40.21% → 提升空间明确；Zhao et al.（A）：覆盖-变异相关性场景依赖——故必须与 F2P 真缺陷指标并列而非单用。
- **预期提升**：ULT mutation score 从当前未测 → **≥50%**（对标 Ockhamareto 49.9%，同模型规模下）。置信度：**中高**（两个一手来源同向）。注意：项目合成变异体过弱，必须切换到 ULT/TestGenEval 变异体。
- **实验验证**：ULT + TestGenEval-Lite；对照 = MUTGEN 复现、MIST-RL（Ockhamareto 论文报告值）、vanilla prompt；指标 = mutation@N、suite size、Pareto 支配；种子/环境/数据版本冻结。
- **反事实**：变异引导已成共识方向（Meta ACH 73% 接受率），差异化仅在"变异反馈×双门×规约 DSL"组合；护城河弱，须靠组合速度。
- **判定**：成功 = ULT mutation ≥50% 且 suite size ≤ Ockhamareto 报告值的 1.2×；失败 = <40%（即未超 ULT LLM 均值）。

### P3 BOAD 式编排自动搜索（Automated Orchestration Search）

- **技术路径**：把"Planner/Generator/Debugger/定位通道/门控"的角色与提示作为 bandit 臂，UCB + hindsight credit assignment 自动发现编排；对照手工编排（项目现状）。
- **依据**：BOAD（ICLR'26，A）：Seed-OSS-36B 上自动 53.2% vs 手工 47.4% vs 基线 49.8%（Verified）；2 子智能体最优。项目 ADR-0016 已自述"后续探索方向为自动搜索编排 vs 手工编排对照"——本路径即该方向的一手依据落地。
- **预期提升**：检测/修复从"手工编排净负"回到"不低于 df 臂 + 正增量"；直接目标 = aitester 臂 detection ≥ df 臂（当前 −28pp）。置信度：**中**（BOAD 在 SWE 域验证，测试生成域待验证）。
- **判定**：成功 = 自动编排臂 detection ≥ df 臂且 token ≤ df 的 2×；失败 = 仍显著低于 df（则证明编排容器在该口径下结构性劣后，本身即可发表）。

### P4 潜在空间通信与上下文压缩（LaMAR 式 LAC + 行级观测压缩）

- **技术路径**：Debugger→Generator 的反馈从文本 token 改为 KV-Cache 级传递（或至少做观测级行粒度压缩）；依据 LaMAR（ASE'26，A）O(N²)→O(N) 与 arXiv:2605.15315（B）的行级压缩在 SWE-bench Verified 上 71.8%/72.0% 成功率下省 23-30% token。
- **预期提升**：token/任务从 26.1k → ≤10k（−60%）且检出不降。置信度：**中**。判定：成功 = token −≥40% 且 detection 不掉 >2pp。

### P5 自修复评估指标先行占位（MTTR/Detection Latency/QoR 标准协议）

- **技术路径**：定义并开源"测试-修复系统"的 SRE 口径指标协议（Detection Latency = 缺陷注入→首次红测试；Diagnosis Time；Reconfiguration Success = 补丁通过 F2P+P2P；QoR；MTTR reduction），在项目 harness 上实现。
- **依据**：§4.3 一手数据显示该域 2025-2026 无可比数值（VIGIL 仅案例、ESBMC-AI 摘要无单值）→ 先占机会。置信度：**中高**（空白领域，风险是无人跟随）。
- **判定**：成功 = 协议被 ≥2 个外部团队采用或复现；失败 = 12 个月内无外部使用（则退回内部指标）。

### P6 跨语言修复通道（LANTERN 式）

- **技术路径**：对 LLM 弱语言（如 Rust/Go）任务，先翻译到 Python 修复再回译；项目已有跨文件协调器-提议者架构可复用。依据 LANTERN（ICSE'26，A）：Rust +22.09pp。置信度：**中**。判定：成功 = xCodeEval 非主流语言 Pass@10 +≥15pp。

### P7 神经符号闭环升级（CEGIR + SMT 见证 → ESBMC-AI 式反例驱动修复）

- **技术路径**：将 spec_smt 的 UNSAT 反例从"丢弃/记录"升级为"回灌 Debugger 的修复约束"（项目 spec_refine 已实现 unsat→LLM 修正→sat 闭环，但只修规约不修代码）；扩展到"反例→代码修复→BMC 复验"。依据 ESBMC-AI（AST'25，A）+ 项目既有 CEGIR 实测成功（既有审计 §1 表 #12：unsat→修正→sat，11.78s）。置信度：**中高**（组件已存在，缺接线与规模验证）。
- **判定**：成功 = 在 ≥500 程序上"反例驱动修复"成功率 ≥ 无该通道对照 +5pp 且无回归引入。

### P8 去污染评测协议对齐（SWE-rebench/ULT 时间戳 + 轨迹提交）

- **技术路径**：主实验增加"新鲜任务切片"（任务创建时间 > 模型知识截止）与 rollout 轨迹强制提交；引用 OpenAI 弃用 Verified 的立场。依据 SWE-rebench（NeurIPS'25，A：−18.4pp 污染膨胀）、SWE-bench-Live（A）。置信度：**高**（这是**必要性**而非提升）。判定：成功 = 外部复审认可以去污染口径重述核心数字。

---

## 7. 差距分析表（按维度）

| 维度 | 现状 | 前沿水位 | 差距性质 | 根因（文件级） |
|---|---|---|---|---|
| 科学性 | 阴性结果诚实、测量伪影考古深入；但 Algorithm 文档含同义反复"定理" | ICST'26/ISSTA'26 复现研究范式 | 中 | `docs/algorithm_design.md` §5 定理 1 |
| 创新性 | 双门协议/特异性门/口径矩阵为真实创新；编排叙事已收缩 | BOAD/LaMAR/规格优先 | 中高（协议层有独创，方法层跟随） | README 头部 |
| 问题定义 | M1 三指标 + F2P 三段判定扎实 | 领域共识（F2P+P2P） | 小（领先） | BASELINE.yaml |
| 数据 | 合成 50 模板 + SWE-bench/QuixBugs 加载器；变异体过弱 | ULT 3,909 真实函数、xCodeEval 5,068 | **大** | `src/datasets/synthetic_dataset.py` |
| 方法 | 提示协议 + 白名单 DSL + 双通道定位 | 神经符号（SPARC/LogiCase）、规格优先（Zhao） | **大** | `src/specs/spec_ir_v2.py` 文法 |
| 实验设计 | 三种子/McNemar/BH-FDR/模板级 DEFF 校正 | 同等或更严（SWE-rebench 5 次运行 SEM） | 小（领先） | `experiments/run_statistical_test.py` |
| 评估指标 | 39 项指标 schema，业界最全之一 | 多维+成本+污染意识 | 小（领先，缺成本-效果联合与去污染） | BASELINE.yaml metrics_schema |
| 可复现性 | SHA256SUMS/预注册/口径矩阵/缓存隔离 | 轨迹提交+时间戳 | 中（缺轨迹提交与新鲜切片） | `docs/preregistration.md` |
| 工程化 | 5489 测试/ruff/mypy/CI 矩阵/安全门禁 | — | **领先** | 全仓 |
| 成本 | $0.0259/task 但有效性低；df $0.0045 | mini-SWE-agent $0.75/task@76.8% | 中（口径不同；相对自身基线劣） | BASELINE.yaml |
| 伦理合规 | 沙箱/脱敏/凭据剔除/包名白名单/slopsquatting 防护 | USENIX'25 量化面 | 领先（面），中（深度：白名单覆盖率未量化） | README 安全执行警告 |

---

## 8. Python 专项诊断表

| # | 维度 | 现状（证据） | 问题 | 严重度 |
|---|---|---|---|---|
| PY-1 | 项目结构 | src layout + PEP 621 + 动态版本 + PEP 639 + py.typed；入口 `aitester = src.cli.app:cli` | 良好；但 `nodes.py` 130,419 字符（虽已拆 4 簇）、`state.py` 51,981 字符仍超大 | 中 |
| PY-2 | 依赖管理 | pyproject 唯一事实源 + requirements.lock 同步门禁（check_lock_sync）+ extras 分组（rag/viz/experiments/ux/dev/formal/db） | 良好；chromadb 1.5.9 五条已知漏洞显式豁免（PYSEC-2026-311×2/3813/3814/3815）——**豁免本身合规，但 RAG 为默认关组件，建议评估替换后端（如 sqlite-vec）以彻底消除** | 中 |
| PY-3 | 代码质量 | ruff 0.16.3 固定 + 扩展规则集（E/W/F/I/B/UP/SIM/PERF/RET/RUF/T20/A/S/C4/DTZ/G/ISC/PIE/PL/PLE/TRY/FURB/PGH）+ mypy 125 文件 0 错误 | 顶档；忽略清单均有注释理由（无死配置） | 领先 |
| PY-4 | 测试 | 5,489 用例（评审者实测收集）；meta_coverage 89% 行/83% 分支；核心路由分支覆盖门槛 85% | 良好；但 meta_coverage 与被测覆盖率同名易混（项目已在 BASELINE 澄清——建议在 CI 报告中强制双命名 `meta_` 前缀） | 小 |
| PY-5 | 可复现性 | 种子+缓存 namespace 隔离（评审者独立确认）+ Dockerfile.repro + reproduce.sh + 工件 SHA256SUMS | 良好；`experiments/results` 默认 gitignore（依赖人工入库纪律，曾滞留 /tmp——已修）；建议 CI 增加"工件入库完整性"定时校验 | 中 |
| PY-6 | 安全 | exec 沙箱链（venv 默认开 + KERNEL_SANDBOX + Docker 可选 + PIP 包名白名单默认开）+ 日志三层脱敏 + credential_scrub + gitleaks CI + bandit | 领先；**LLM 文件缓存被项目自列"已知可接受风险"**——缓存位于 `~/.cache/aitester/llm/`（0700/0600），本地可信域假设需在威胁模型中显式声明适用范围 | 中 |
| PY-7 | 架构债 | ADR-0016 记录 `src/graph → experiments/_m1_metrics` 反向依赖（门执行委托） | 已知架构债，有收敛方案待办；建议按 ADR 执行 src 层统一执行原语 | 中 |
| PY-8 | 数据/ML 管线 | 污染检测（Jaccard）+ 难度分层 + contamination_risk_level 落结果行 | 良好；无训练管线（纯提示工程）→ 数据泄漏面小；合成模板 50 个的三重不变量自验证（verify_synthetic_templates.py）是亮点 | 领先 |
| PY-9 | 运维 | CI 3 作业（ci/perf/release）+ 失败诊断注解 + 定时安全扫描 + pre-commit + 自定义 git-hooks | 领先；建议补：weekly 全量 LLM 冒烟（已有 schedule 机制，默认关） | 小 |
| PY-10 | 版本/发布 | CHANGELOG 双语 420KB + CITATION.cff + MODEL_CARD + DATA_CARD + make build-check（wheel 构建+全新 venv 安装+CLI 冒烟） | 顶档 | 领先 |

---

## 9. 领域专项审查表

| # | 领域维度 | 审查发现 | 判定 |
|---|---|---|---|
| D-1 | 逻辑驱动 | 规格语言 = SpecExpr 白名单 DSL（11 纯函数+3 属性+200 字符）；无时序逻辑、无量词、无 Hoare 三元组、无 SMT 求解闭环（z3 仅一致性检测）；编译率 21% | **规格不可验证性风险高**：当前"逻辑驱动"主张不可证伪度低但可执行化深度浅；须文法升阶（见 P1/P7） |
| D-2 | 多智能体 | 角色分离清晰（Planner/Generator/Executor/Debugger/FaultLocalizer）；编排净负 −28pp（项目自身 A 级证据）；手工编排被 BOAD/ICST'26 双重背书为低价值 | **协作可控性**：双门+红证人+快照回滚机制真实存在且默认关；建议 logic 档默认注入并复跑 |
| D-3 | 测试生成 | 覆盖准则齐备（边界三元组/等价类/变异/特异性门）；变异体过弱（项目自认）；缺属性测试默认链（hypothesis 已在 formal extra） | 有效性问题已在 C1/F1 充分暴露 |
| D-4 | 自修复 | 局部化→合成→验证三段；补丁弃权门（五信号）/test-hacking 守卫/多候选/跨文件拓扑序应用/快照回滚；false_fix 87.2% 说明**防过拟合是主要未决问题** | 安全可靠性强（写入侧），正确性弱（合成侧）；弃权精确率 85.97% 已非平凡 |
| D-5 | 反馈闭环 | 执行轨迹/覆盖率反馈/奖励信号（trace_reward 6 纯函数）/停止条件 7 类；迭代分布 0:107/1:42/2:90/3:22 | 收敛性有观测无保证；建议补收敛性经验命题（如 δ-改进约束，TraceCoder 的 Rollback Mechanism 可借鉴） |
| D-6 | 评估与基准 | 39 指标 + 统计检验 + 消融矩阵 + 预注册；缺外部基准主结果（ULT/TestGenEval 未跑）与去污染切片 | **可评估性**：内部顶档、外部空白 |
| D-7 | 安全合规 | 沙箱默认开、包名白名单、slopsquatting 面已量化防护（USENIX'25 A 级依据）；LICENSE MIT + PEP 639；无人类受试者/隐私数据 | 合规良好；建议威胁模型补充"LLM 缓存投毒"与"白名单覆盖率量化"两项 |
| D-8 | 工程化运维 | 见 PY-3/4/9 | 领先 |

---

## 10. 改进/优化/新增建议表

| 建议编号 | 对应文件/位置 | 问题 | 一手前沿依据 | 建议内容 | 类型 | 优先级 | 预期收益 | 成本/风险 | 验证指标 | 时间线 | 工具/命令 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| S-01 | `docs/algorithm_design.md` §5 定理 1 | "若 LLM 能力足够则收敛"是同义反复，损害科学性 | 复现研究范式（ICST'26） | 删去定理 1 或改写为可证伪经验命题（如"在 δ-改进约束下修复序列单调"）；定理 2 保留 | 必须改进 | P0 | 科学信誉 | 低（纯文档） | 外部评审复审通过 | 1 周 | — |
| S-02 | README 头部 Konstantinou 请求数 | 11,718/12,264 与论文 11,815/12,741 不符 | arXiv:2601.09695v2 正文 | 更正为 11,815/12,741 并注明 v2 口径 | 必须改进 | P0 | 引用零瑕疵 | 低 | grep 复核 + 引用守卫脚本 | 1 周 | scripts/gates 引用守卫 |
| S-03 | `BASELINE.yaml` target_quality 节 vs README:24 | TestAgent 数值内部冲突（88.85/55.4 vs 92.34/83.69） | FSE Companion'26 摘要 + arXiv:2607.09101 | 统一为 92.34%/83.69%（一手可溯源），删除 88.85/55.4 或标注 D 级弃用 | 必须改进 | P0 | 单一事实源 | 低 | check_baseline_numbers.py | 1 周 | 同上 |
| S-04 | BASELINE.yaml 与 git log 81b1cc7 | QuixBugs "72-74%" 无分母，与 24% 主口径并存 | 评审者复算（12/50） | 所有对外数字强制带分母口径（分子/分母/oracle/臂/种子），72-74% 注明窄口径分母或停用 | 必须改进 | P0 | 防选择性陈述 | 低 | 口径矩阵 lint | 1 周 | — |
| S-05 | `src/specs/spec_ir_v2.py` | 白名单 DSL 表达力不足 → 编译率 21% | LogiCase（IJCAI'25）CCFG；SPARC 路径枚举 | SpecExpr v3：增加关系算子、量化子句（forall/exists over 有限域）、切片语法白名单、字符串方法白名单（split/join/replace，纯函数）；目标编译率 ≥0.55 | 必须改进 | P0 | "逻辑驱动"可证伪化 | 中（文法+提示+测试三处同步，须防注入面） | spec_compile_rate ≥0.55 且反例测试全过 | 4-8 周 | tests/test_spec_contract_grammar.py 扩展 |
| S-06 | `src/graph/nodes.py`（generator 提示组装） | 缺陷代码入提示诱发 misguided tests（48.6% 全绿） | Zhao et al. ISSTA'26 #2（misguidance effect） | 新增 DETECTION_SPEC_MODE=replace 臂：提示以规约文档替换实现代码；A/B 对照 df 臂 | 必须改进 | P0 | detection 44.8%→≥60%（目标） | 中（提示重构+回归） | ULT 外部基准 F2P | 4 周 | 复用 run_benchmark --baselines |
| S-07 | `experiments/`（主实验协议） | 无外部基准主结果、无时间戳去污染 | ULT（TOSEM'26）、SWE-rebench（NeurIPS'25）、OpenAI 弃用 Verified | 增加 `--dataset ult` 加载器（github.com/huangd1999/UnLeakedTestBench）与新鲜切片标记（task_created_at > 模型截止）；核心论文数字必须含 ULT 结果 | 必须改进 | P0 | 外部可信度 | 中（数据下载+评测适配） | ULT detection/mutation 报告 | 6 周 | datasets 库 + SWEBenchDataset 模式 |
| S-08 | `experiments/mutation_testing.py` + `mutation_advisor.py` | 变异体过弱、默认关、观测覆盖 0/154 | MUTGEN（TSE'26）、Ockhamareto、Meta ACH 73% 接受率 | 接入 ULT/TestGenEval 变异算子集；ENABLE_MUTATION_SCORING 在 logic 档默认开；变异得分入一等指标 | 必须改进 | P0 | mutation 40%→≥50%（ULT） | 中（执行成本） | ULT mutation@N | 6 周 | pytest-mutation / mutmut 评测对齐 |
| S-09 | `src/agents/`（编排） | 手工编排净负 −28pp；token 6.2× | BOAD（ICLR'26）：自动 53.2% vs 手工 47.4% | 编排自动搜索原型：角色/提示为臂，UCB+hindsight credit；设计集 12 任务起 | 建议优化 | P1 | 消除 −28pp | 高（搜索成本） | 自动臂 detection ≥ df | 3-6 月 | BOAD 开源代码参考 |
| S-10 | `src/graph/workflow.py`（反馈传递） | 文本 token 反馈，O(N²) 通信 | LaMAR（ASE'26）O(N²)→O(N) | 观测压缩先行（行级 granularity），KV-Cache 通信为二期 | 建议优化 | P1 | token −40% | 高 | token/任务 ≤10k | 3-6 月 | — |
| S-11 | `docs/preregistration.md` | 缺 rollout 轨迹强制提交条款 | SWE-bench-Live 2026-08 新规 | 预注册增加"轨迹上传+评审员核验"条款；工件入库 CI 定时校验 | 建议优化 | P1 | 防作弊+外部信任 | 低 | CI 工件校验绿 | 2 周 | GitHub Actions |
| S-12 | `README.md` 安全执行警告 | slopsquatting 19.7% 标[待核验] | USENIX Security'25（A） | 去掉[待核验]，补一手引用（Spracklen et al.） | 可新增 | P2 | 引用完整 | 低 | 引用守卫 | 1 周 | — |
| S-13 | `docs/threat_model.md` | 未覆盖 LLM 缓存投毒/白名单覆盖率 | 一手来源同上 | 补两节：缓存目录攻击面（本地可信域声明）+ 包名白名单命中率量化实验 | 可新增 | P1 | 合规深度 | 低 | 威胁模型评审 | 2 周 | — |
| S-14 | chromadb 依赖 | 五条 CVE 豁免 | pip-audit 现状 | 评估 sqlite-vec/DuckDB 替代或升级路径；保留豁免登记 | 可新增 | P2 | 供应链清洁 | 中 | pip-audit 零豁免 | 1-2 月 | pip-audit |
| S-15 | `docs/algorithm_design.md` §6 对比表 | 与 Pynguin/单次调用对比已过时 | §4 前沿表 | 重写为 2025-2026 前沿对比（CANDOR/TestAgent/CoverUp/ULT/LaMAR/BOAD）并注明基准差异 | 必须改进 | P1 | 领域定位清晰 | 低 | 外部评审 | 2 周 | — |
| S-16 | 自修复评估指标 | 领域空白（§4.3） | VIGIL/ESBMC-AI 稀薄 | 定义 Detection Latency/Diagnosis Time/Reconfiguration Success/QoR/MTTR 协议并在 harness 实现（P5） | 可新增 | P1 | 先占+差异化 | 中 | 协议文档+复现包 | 2-3 月 | — |

---

## 11. 既有评审结论独立复核表

> 复核对象包括项目自有"独立"审计（`_independent_audit/`）与根目录评审文档的**代表性结论**。方法：回溯其引用的一手来源或其声称的原始数据，独立重算。

| 原结论编号 | 原文位置 | 原结论 | 独立复核方法 | 复核结论 | 支持/推翻/无法验证 | 依据 |
|---|---|---|---|---|---|---|
| R-C1 | `_independent_audit/WS1` §1 总表 | "项目所列 8 个 DOI/arXiv 全部真实存在、零伪造" | 评审者本次独立检索 13 条引用 | **支持**（且扩展：13/13 真实，2 处数值瑕疵） | 支持 | §4 各表 |
| R-C2 | `_independent_audit/WS1` R4c | Konstantinou 请求数项目引用误述（11,815/12,741 才对） | 本次未直接取得正文表格；采信其对正文的逐字转录 | **支持（B 级）** | 支持（降级为 B 因未独立见到正文） | 需项目按 S-02 更正 |
| R-C3 | `_independent_audit/WS1` R3 | Radaideh 四数值"无法独立核实（D）" | 评审者经 Carleton 大学报告页取得完整数值表 | **部分推翻（升级）**：四数值可核实，Gemini one-shot mutation 88.35%、GPT-4o 69.90%、CANDOR 45.63%/35.92%、人类 83.98% | 推翻（D→A/B） | report-hub.scs.carleton.ca/projectPage/2872 |
| R-C4 | `_independent_audit/WS1` R10 | BASELINE.yaml TestAgent 88.85/55.4 与 README 冲突且不可溯源 | 评审者检索一手来源 | **支持**：一手仅 92.34/83.69（FSE 摘要/arXiv） | 支持 | §4.1 |
| R-C5 | `_independent_audit/WS1` R7b | Zhao et al. "r=0.780 @k=10" 不可定位；"控制规模后"表述有张力 | 评审者核对 ISSTA'26 摘要与 Distinguished Paper 页 | **支持**：摘要明确"little evidence that test suite size is a dominant confounder"，与"控制规模后"读法张力成立 | 支持 | DOI 10.1145/3832093 摘要 |
| R-C6 | `_independent_audit/LLM_LIVE_TEST` L1 | "真实调用 F2P 检出 0/18，测试断言缺陷行为本身" | 机制与 BASELINE specificity_gate 节（48.6% 全绿）及 Zhao misguidance effect 一手理论互相印证 | **支持（机制层）** | 支持 | 三方同向 |
| R-C7 | `_independent_audit/LLM_LIVE_TEST` L5 | "LLM 缓存使三种子退化为单次" | 评审者核查三批次 provenance：cache_namespace=seed42/43/44 隔离 | **对主批次推翻**；对未设 namespace 的历史批次仍可能成立 | 部分推翻 | §3.2 |
| R-C8 | ADR-0016 / ADR-0021 | "编排净负 −28pp"；"repair=0 系测量伪影，修正 39.31%" | 评审者复算 detection + 实跑 corrected_metrics 重放 | **支持**（数值逐位复现） | 支持 | §3.1 C1/C2 |
| R-C9 | `analysis/swe_lite_root_cause_2026-10-05.md` | "0/20 是写入链路伪损坏而非 LLM 能力边界；防线已入树但未复跑验证" | 工件核查（17/20 coverage=0、18/20 patch_validation_failed、原始切片 ast.parse 全过） | **支持**；且"未复跑验证"状态在 2026-10-11 后仍无 ≥20 任务 SWE 批次记录（评审者未见） | 支持 | §3.1 C7 |
| R-C10 | README:12-34（三方并列修订） | "手工工具特定编排相对强 LLM 单提示+统一修复环优势有限或无优势；不得表述为多智能体范式被击败" | 与 ICST'26（Plain-LLM 胜四工具）、BOAD（手工子智能体掉点）、Radaideh（one-shot 胜 CANDOR，但其自注 configuration effect）交叉 | **支持**（三方一手同向）；Radaideh 一方的限定语（configuration effect）项目已如实呈现 | 支持 | §4.1/4.2 |
| R-C11 | `docs/algorithm_design.md` 定理 1/2 | 理论正确性"证明" | 独立逻辑审查 | **推翻（科学性层面）**：定理 1 假设包含结论；定理 2 平凡 | 推翻 | §3.3 |
| R-C12 | BASELINE.yaml | "spec_compile_rate AC 批后由 0 抬到 ~0.21，目标 ≥0.55" | 机制链（W2/T1 文法契约段）与既有真实调用实测（7/8 为 0.0）并存 | **部分支持**：非零为真，但水位离目标 0.55 很远，且真实调用下不稳定 | 部分支持 | C6 |

---

## 12. 优化后的项目方案与路线图

### 12.1 重新定位（叙事与证据对齐）

> **新定位一句话**：AITester 是一个**检出优先、规格驱动、测量严格**的测试生成与修复归因系统；其核心贡献是 (a) −28pp 编排净负贡献的阴性发现与双门协议，(b) 87.2% 假修复率揭示的"假成功通道"与弃权门，(c) 覆盖-变异-缺陷检出三口径分离的评估方法学。多智能体编排保留为可消融研究容器。

### 12.2 优化后框架

```
┌─ 输入层 ─────────────────────────────────────────────┐
│ 任务源：ULT（去污染真实函数）/ SWE-bench-Live（新鲜切片）/ │
│         合成集（回归对照）/ QuixBugs / xCodeEval         │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌─ 规格恢复层（新，P1）─────────────────────────────────┐
│ NL docstring + SpecExpr v3 文法 + 边界三元组 + CEGIR   │
│ 反例精化（z3 UNSAT → 只改契约 → 复验）                  │
└──────────────────────┬───────────────────────────────┘
                       ▼  （提示以规约替换实现代码）
┌─ 生成层 ─────────────────────────────────────────────┐
│ Generator（规格优先模式）+ 变异反馈环（P2，MUTGEN 式）   │
│ 特异性门（过红→regenerate）/ 红回归门（抹红→恢复红证人） │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌─ 执行层 ─────────────────────────────────────────────┐
│ venv 沙箱（默认）/ Docker / RepoExecutor（P2P 门）     │
│ 覆盖率 + 变异得分 + 轨迹（JSONL，强制提交）             │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌─ 修复层（局部化→合成→验证）───────────────────────────┐
│ 谱系（Ochiai）+ 推理（RGFL）双通道 → Debugger          │
│ 补丁弃权门（五信号）/ 多候选 / 跨文件拓扑序 / 快照回滚   │
│ [二期] SMT 反例驱动修复（P7）/ 潜在空间反馈（P4）       │
└──────────────────────┬───────────────────────────────┘
                       ▼
┌─ 评估层 ─────────────────────────────────────────────┐
│ M1 三指标 + 39 项 schema + 成本/任务 + 去污染切片       │
│ McNemar/BH-FDR/模板级 DEFF/SEM（5 次运行）              │
│ 自修复 SRE 口径指标（P5：Detection Latency/MTTR/QoR）   │
└──────────────────────────────────────────────────────┘
```

### 12.3 多智能体方案（角色/通信/编排/记忆/恢复/可观测）

- **角色**：收缩为"规格师（Planner）→ 生成器 → 执行器（确定性）→ 修复师（Debugger）→ 定位器（双通道）"五角色；专家池/辩论/多候选保留为默认关容器。
- **通信**：一期行级观测压缩；二期 KV-Cache 潜在通信（LaMAR 式）；消息格式保持结构化 JSON + trace JSONL 双轨。
- **编排**：手工编排为对照臂；BOAD 式自动搜索为实验臂（预注册判据）。
- **记忆**：RAG 默认关（阴性证据）；失败经验由 HLLM 式历史教训库替代（TraceCoder 依据）。
- **失败恢复**：补丁弃权门 + 快照回滚 + fail-closed 口径（已实现，默认关 → logic/scientific 档默认开）。
- **可观测**：39 指标 + 轨迹强制提交 + 工件 SHA256SUMS + CI 定时校验。

### 12.4 逻辑驱动方案

规格表达：SpecExpr v3（关系/量化/切片白名单）→ 约束建模：z3 前件/后件一致性 + UNSAT 反例 → 求解器/验证器：z3 见证层 + （二期）ESBMC 式 BMC 复验 → 覆盖准则：表达式通道覆盖 + 边界三元组 + 变异得分 → 测试最小化：Pareto（mutation vs −#tests，Ockhamareto 口径）。

### 12.5 自修复方案

触发：F2P 红 + 特异性门通过 → 定位：双通道融合 → 补丁生成：Debugger（多候选）→ 验证：gold 独立裁决 + P2P 回归门 → 回归：快照回滚 + 红回归门 → 置信度：补丁弃权五信号 + patch_evidence_level → 人工审核：弃权精确率 ≥0.86 现状下，高风险补丁（false_fix 历史 87.2%）强制人工/机器复核队列。

### 12.6 路线图与 KPI

| 阶段 | 时间 | 目标 | KPI（可独立验证） |
|---|---|---|---|
| 短期 | 1-3 月 | 引用零瑕疵（S-02/03/04/12）；ULT 基准跑通（S-07）；规格优先臂 A/B（S-06） | 引用守卫 CI 绿；ULT detection/mutation 首报；规格臂 vs df 臂 McNemar 报告 |
| 中期 | 3-6 月 | SpecExpr v3（S-05）；变异一等指标（S-08）；编排自动搜索原型（S-09） | spec_compile_rate ≥0.55；ULT mutation ≥50%；自动臂 detection ≥ df |
| 长期 | 6-12 月 | 去污染主实验（S-07+11）；自修复 SRE 协议（P5）；潜在通信（P4） | 新鲜切片核心数字；协议外部采用 ≥2 团队；token −40% |

---

## 13. 实验、验证与评估计划

1. **E-A（规格优先 A/B）**：臂 {plain_llm_df, spec_replace, spec_replace+双门}；数据集 ULT + 合成；3 种子；temp=0；缓存 namespace=exp_spec_{seed}；指标 F2P detection / misguided 率 / 编译率；McNemar+BH-FDR；预注册判据见 P1。
2. **E-B（变异反馈）**：臂 {vanilla, mutation_feedback, mutation_feedback+最小化}；ULT/TestGenEval-Lite；对照 MUTGEN 与 MIST-RL 公开值（B 级）；指标 mutation@N、suite size、Pareto 支配；5 次运行报 SEM。
3. **E-C（编排搜索）**：设计集 12 任务（BOAD 协议）；臂 {manual, auto_bandit}；Verified-Live 新鲜切片；指标 resolved/token/帮助度信用分配。
4. **E-D（双门复跑）**：logic 档默认开双门，重跑合成集 261；判据：aitester detection ≥ df 或结论升级为"结构性劣后"（两种均可发表，ADR-0016 已预注册此分支）。
5. **E-E（自修复指标协议）**：实现 Detection Latency/Diagnosis Time/Reconfiguration Success/QoR/MTTR；在 QuixBugs+SWE-bench Lite 上报告；与 VIGIL 案例研究（B 级）并列不混比。

---

## 14. 风险、伦理与合规

| 风险 | 等级 | 缓解 |
|---|---|---|
| R1：合成集结论外推失败（QuixBugs 24% vs 合成 39.31%） | 高 | S-07 外部基准强制化；对外数字带基准标注 |
| R2：规格优先若被前沿快速复制，差异化收窄 | 中 | 护城河置于测量工程+双门+口径矩阵（复制成本 1-2 迭代）；持续发表阴性/方法学结果 |
| R3：LLM 执行沙箱被绕过（EXECUTOR_USE_VENV=false 调试路径） | 中 | README 已警告；建议 CI 禁该组合+威胁模型声明 |
| R4：slopsquatting 供应链（19.7% 幻觉包名，USENIX'25） | 中 | 包名白名单已默认开；建议量化白名单覆盖率（S-13） |
| R5：LLM 文件缓存投毒/跨用户泄露 | 低-中 | 0700/0600 已做；建议加缓存内容哈希校验 |
| R6：chromadb CVE 豁免遗忘 | 中 | 定期豁免复查已在 CI；建议替代评估（S-14） |
| R7：基准污染（SWE-bench Verified 被 OpenAI 弃用） | 高（声誉） | S-07/S-11 时间戳去污染+轨迹提交 |
| R8：自动编排搜索成本失控 | 中 | bandit 预算上界+设计集规模控制 |
| 伦理 | 低 | 无人类受试者；生成代码沙箱执行；隐私数据不落盘（.env/.private 已 gitignore） |
| 合规 | 低 | MIT + PEP 639 + MODEL_CARD/DATA_CARD/SECURITY 文档齐备 |

**Plan B**：若规格优先在 ULT 上不显著（P1 失败判定触发），退守"测量方法学 + 阴性结果 + 双门协议"的论文框架（三点式 B/C 轴，ADR-0016 已预设），并将工程资产（harness/指标 schema/口径矩阵）开源为社区基准工具。

---

## 15. 待澄清问题

1. **QuixBugs "72-74%" 的窄口径分母**（commit 81b1cc7 未注明；评审者无法还原）——请提供分子/分母/oracle/开关配置，否则对外停用该数字。
2. **spec_compile_rate 2026-10-11 后的最新水位**：W2/T1 文法契约段落地后是否复测？当前 BASELINE 登记值为 AC 批后的 0.205–0.219。
3. **ULT/TestGenEval 外部基准是否已有未入库的试跑工件**（评审者未见相关 results 目录）。
4. **Konstantinou 请求数**：项目拟采信 v1 还是 v2 口径？（v2：11,815/12,741）
5. **Zhao et al. "r=0.780 @k=10"** 的项目来源（一手材料不可定位；若是全文表格值，请注明表号）。
6. **TSC2CARLA / Alloy 组合测试 / Tratto / RunBugRun / ARC-APR / LogicEval / CI-Bench / HEJ-Robust**：项目是否有意将这些纳入基线？（评审者本次未对其重建，故 §4 中相关条目为 D 级，不支撑任何结论）
7. **FL 观测覆盖 0/154** 的补齐批次（E2 起有产出）是否已入库可供复算？
8. **自动编排搜索（P3）** 是否有算力预算（bandit 搜索需数百次完整轨迹）？

---

## 16. 参考来源（区分一手/二手，标注证据等级）

### 一手来源（A 级，除注明外均为评审者 2026-10-12 实际访问核验）

**测试生成**
1. Xu, Wang, Briand, Liu. *Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation*. ACM TOSEM 2026. DOI 10.1145/3803418；arXiv:2506.02943. 【A】
2. Shang, Zhang, Zhan, Huang, Fang, Chen. *TestAgent: A Multi-Agent LLM Framework for Repository-Level Unit Test Generation*. FSE Companion '26, pp.242-246. DOI 10.1145/3803437.3806428；arXiv:2607.09101；github.com/iSEngLab/TestAgent-VSCode-Extension. 【A】
3. Pizzorno, Berger. *CoverUp: Effective High Coverage Test Generation for Python*. FSE 2025. DOI 10.1145/3729398；arXiv:2403.16218. 【A】
4. Huang, Zhang, Harman, et al. *Benchmarking LLMs for Unit Test Generation from Real-World Functions (ULT)*. ACM TOSEM 2026. DOI 10.1145/3805043；github.com/huangd1999/UnLeakedTestBench. 【A】
5. Wang, Xu, Briand, Liu. *Mutation-Guided Unit Test Generation With a Large Language Model (MUTGEN)*. IEEE TSE 2026. DOI 10.1109/TSE.2026.3682975；arXiv:2506.02954. 【A】
6. Konstantinou, Degiovanni, Papadakis. *How well LLM-based test generation techniques perform with newer LLM versions?* ICST 2026. arXiv:2601.09695v2；DOI 10.1109/ICST69053.2026.00040；ORBilu 10993/69213. 【A】
7. Radaideh, Corriveau, Shi. *Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation: A Comparison with Human-Written Tests Using Mutation Testing*. IEEE BDAI 2026, doc 11655121；Carleton 报告 report-hub.scs.carleton.ca/projectPage/2872. 【A/B】
8. Chowdhury, Fu, Jabbarvand. *SPARC: Scenario Planning and Reasoning for Automated C Unit Test Generation*. arXiv:2602.16671. 【B（预印本）】
9. Huang, Harman, Zhang, Guo, Du, Ng. *Ockhamareto: Pareto-Gated Segment-Level Credit Assignment for Concise Unit-Test Generation with RL*. arXiv:2608.24473（TOSEM 在审）. 【B】
10. Jain, Synnaeve, Rozière. *TestGenEval: A Real World Unit Test Generation and Test Completion Benchmark*. ICLR 2025. 【A】
11. Harman, Ritchey, Harper, et al. *Mutation-Guided LLM-based Test Generation at Meta*. FSE 2025 Industry Track. 【A】

**多智能体与修复**
12. Bouzenia, Devanbu, Pradel. *RepairAgent: An Autonomous, LLM-Based Agent for Program Repair*. ICSE 2025. DOI 10.1109/ICSE55347.2025.00157；arXiv:2403.17134；OpenReview AhS0wCDGnR. 【A】
13. Luo, Keung, Yang, Klein, Bissyandé, Tian, Le. *Unlocking LLM Repair Capabilities Through Cross-Language Translation and Multi-Agent Refinement (LANTERN)*. ICSE 2026. DOI 10.1145/3744916.3773227；arXiv:2503.22512；github.com/stringing/LANTERN. 【A】
14. Jiao, Zhang, Feng, Li. *LaMAR: Latent Multi-agent Collaboration via KV-Cache Communication for Automated Program Repair*. ASE 2026. DOI 10.1145/3832783.3837423. 【A】
15. Ye, Huang et al. *TraceCoder: A Trace-Driven Multi-Agent Framework for Automated Debugging of LLM-Generated Code*. arXiv:2602.06875. 【B】
16. Xu, Zeng, He, Jin, Pareja, Gutfreund, Gan, Hong. *BOAD: Discovering Hierarchical Software Engineering Agents via Bandit Optimization*. ICLR 2026. arXiv:2512.23631；OpenReview O6stE173BD；github.com/iamxjy/BOAD-SWE-Agent；IBM Research 出版页. 【A】
17. SWE-bench 官方 leaderboard. swebench.com（Claude 4.5 Opus + mini-SWE-agent 76.80%，2026-02-17）. 【A】

**自修复与形式化**
18. Cruz. *VIGIL: A Reflective Runtime for Self-Healing Agents*. arXiv:2512.07094. 【B】
19. Tihanyi, Charalambous, Jain, Ferrag, Cordeiro. *A New Era in Software Security: Towards Self-Healing Software via LLMs and Formal Verification (ESBMC-AI)*. AST 2025. DOI 10.1109/AST66626.2025.00020. 【A】

**逻辑驱动与评估方法学**
20. Sung, Aditi, Kim, Han, Ko. *LogiCase: Effective Test Case Generation from Logical Description in Competitive Programming*. IJCAI 2025. DOI 10.24963/ijcai.2025/861；arXiv:2505.15039. 【A】
21. Zhao, Zhou, Cohen. *Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)*. ISSTA 2026（Distinguished Paper）. DOI 10.1145/3832093；arXiv:2607.22880；Zenodo 10.5281/zenodo.21437945. 【A】
22. Zhao, Zhou, Cohen. *Evaluating and Mitigating the Misguidance Effect of Buggy Code in LLM-Generated Unit Tests*. ISSTA 2026. Zenodo 10.5281/zenodo.21429528. 【A】
23. Badertdinov, Golubev, et al. *SWE-rebench: An Automated Pipeline for Task Collection and Decontaminated Evaluation of Software Engineering Agents*. NeurIPS 2025. arXiv:2505.20411. 【A】
24. Zhang, He, et al. *SWE-bench Goes Live!* arXiv:2505.23419；swe-bench-live.github.io. 【A/B】

**安全**
25. Spracklen, et al. *We Have a Package for You! A Comprehensive Analysis of Package Hallucinations by Code Generating LLMs*. USENIX Security 2025. 【A】

### 二手来源（C 级，仅作参考，不支撑关键结论）

26. steel.dev / codesota.com / demandsphere / aiwiki 的 SWE-bench 追踪页（Claude Mythos 93.9%、Opus 4.7 87.6% 等自报值）【C】
27. wopee.io 等行业博客对 MUTGEN/ULT 的转述【C】

### 项目内部材料（本评审的复核对象，非采信来源）

28. AITester 仓库：README.md、BASELINE.yaml、docs/adr/*、experiments/results/main_batch/*、experiments/results/r4_batches/*、_independent_audit/*、audit_2026/*、review_2026/* 及各评审文档——本报告中相关数值均经独立复算或重放后标注等级。

---

*报告生成：独立评审（2026-10-12）。所有复算命令与原始数据路径已在 §3 注明。本报告不修改项目任何文件。*
