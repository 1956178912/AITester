# 外部文献读数登记（EXTERNAL READINGS REGISTER）

> 生成：2026-10-25（CN 轮）；用途 = 论文在 Related Work / Discussion 中引用的**外部**
> 数字，逐条登记出处与原文读数，供 `scripts/tools/audit_paper_numbers.py` 的
> 「数字存在性」判据核对。

## 0. 这份登记册验证什么、不验证什么

- **验证**：论文里写的这个数字，与登记册里抄录的原文读数一致；登记册里同时给出
  出处（DOI/arXiv 号）与检索日期，人可以逐条回查。
- **不验证**：这些数字**不是本仓库复算出来的**。内部数字的 SRC 指向
  `experiments/results/` 或 `BASELINE.yaml`，可零 LLM 复算；外部数字只能登记，
  不能复算。审计器对两者的判据形式相同，**证据强度不同**，正文与附录不得把
  二者混为一谈。
- 登记纪律：只登记**能从原文（摘要/正文）直接抄到**的读数；版本间读数不一致时，
  登记**会议/期刊定稿**并注明版本差异，不取「看起来更好」的那个。
- **行级判据（CP 轮新增，可执行）**：每行「读数」列里的**多位数与小数**必须在同行
  「原文表述」列里逐字出现（千分位逗号不计），「原文表述」不得写成自指（"quoted above"
  一类必须内联原句）。该判据由 `tests/test_external_readings_rows.py` 执行（按文件名
  `EXTERNAL_READINGS_*.md` 发现登记册，**要求恰有一份**；新开一份即红）；英文数词
  （`ten` / `thirteen`）按名豁免且豁免表只允许变短。**读数出自全文而引文抄摘要**，锁当场红。
- 检索日期：2026-10-25。

## 1. 编排 vs 单提示（RQ2 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `konstantinou2026icst` | +17.72 / +19.80 / +20.92 | "a plain LLM approach outperforms all of them on line coverage (+17.72%), branch coverage (+19.80%), and mutation score (+20.92%) at comparable query cost" | ICST 2026（DOI 10.1109/ICST65540.2026.00012，见 `refs.bib`） |
| `arna2026icstw` | 3–4× | "they yield an ESR comparable to single-agent frameworks ... at the expense of a threefold to fourfold increase in token expenditure" | ICSTW 2026, pp. 29–36（DOI 10.1109/ICSTW72326.2026.00018） |
| `radaideh2026bdai` | 69.90 / 45.63 | "one-shot GPT-4o reaches a 69.90% mutation score versus CANDOR's 45.63%" | BDAI 2026（DOI 10.1109/BDAI70753.2026.11655121，Crossref 2026-10-25 核验） |
| `radaideh2026bdai` | 88.35 / 35.92 | "one-shot Gemini 2.5 Flash reaches 88.35% versus CANDOR's 35.92%" | 同上 |
| `radaideh2026bdai` | 45 s / 50 h | "in about 45 seconds, while CANDOR with Gemini took roughly 50 hours" | 同上 |

**版本差异（必须留存）**：`arna2026icstw` 的 ESR 读数在不同版本里不一致——
POLITO 机构库与 IEEE CSDL 摘要写 "96.88% versus 96.89%"，ResearchR 会议页写
"97.31% versus 97.25%"，覆盖率峰值亦有 99.54% / 99.75% 两版。正文因此**只取
跨版本稳定的定性结论**（执行成功率无可测差异、token 三到四倍），不引用这两组
小数。这是「同一结论、不同快照」的典型，登记在此以免日后被当成新数据。

## 1b. 编排与上下文增强（CO 轮补登记，2026-10-25 一手核验）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `kim2026scaling` | 260 配置 / 6 基准 / 5 架构 / 3 族；R² 0.373 / 0.413 | "Across 260 configurations spanning six agentic benchmarks, five canonical architectures (Single-Agent and four Multi-Agent: Independent, Centralized, Decentralized, Hybrid), and three LLM families"；"The resulting model achieves a cross-validated R^2=0.373 across all six benchmarks (R^2=0.413 with a task-grounded capability metric)" | arXiv:2512.08296v3（2026-04-08 最新版），Google Research / DeepMind / MIT，DOI 10.48550/arXiv.2512.08296 |
| `kim2026scaling` | 180 配置（**成本追踪子集**） | "Data from BrowseComp-Plus, Finance Agent, PlanCraft, and Workbench (180 configurations with full cost tracking; SWE-bench Verified and Terminal-Bench use Docker-based evaluation with different cost structures)"（**v3 全文**；v1/v2 摘要把这 4 个基准写成整个研究面） | 同上（arXiv:2512.08296v3） |
| `kim2026scaling` | −39%…−70% / +80.8% / 17.2x / 4.4x / 45% | "all multi-agent variants universally degrade performance on tasks requiring sequential constraint satisfaction (planning: −39% to −70%)"；"+80.8% on decomposable financial reasoning"；"Independent systems amplify trace-level errors 17.2× through unchecked error propagation"；"Centralized coordination, however, contains this to 4.4×"；"tasks where single-agent performance already exceeds 45% accuracy experience negative returns from additional agents"（v3 全文，β=−0.236, p=0.004；v2 为 β=−0.408） | 同上（arXiv:2512.08296v3） |
| `kim2026scaling` | 0.524（**v2 读数，v3 已改**） | "achieves cross-validated R^2=0.524"（v2 摘要；v3 改为 R^2=0.373 / 0.413，见本表第一行——**引用 0.524 必须同时标明 v2**） | arXiv:2512.08296v2（2025-12-17） |
| `jwalapuram2026illusion` | 10x | "automatic MAS consistently underperform CoT-SC despite being up to 10x more expensive"；"these comparisons rarely control for inference budgets such as number of LLM calls, total cost, retries, or sampled paths" | arXiv:2606.13003v2（2026-06-11 / v2 2026-06-13），Salesforce Research / HKUST(GZ) / UBC / NTU，DOI 10.48550/arXiv.2606.13003 |
| `shin2026rag` | 6.5% / 28 / 24 / 10 | "While RAG does not enhance correctness, RAG improves line coverage by 6.5% on average"；"28 bugs were detected, 24 unique bugs were reported to developers, ten were confirmed" | ICSE 2026（48th ICSE）Research Track，pp. 767--779，DOI 10.1145/3744916.3773163，arXiv:2409.12682 |

**版本与来源冲突（必须留存）**：`kim2026scaling` 的**配置数与基准数在 v1/v2 与 v3 之间换过**——
v1（2025-12-09）/v2（2025-12-17）摘要写 **180 configurations / four benchmarks**
（Finance-Agent、BrowseComp-Plus、PlanCraft、Workbench）与 **R²=0.513 / 0.524**；v3（2026-04-08）
把研究面扩到 **260 configurations / six benchmarks**（新增 SWE-bench Verified 与 Terminal-Bench），
R² 重估为 **0.373 / 0.413**，并把 180/4 降为"带完整成本追踪的子集"。**CP→CQ 轮的更正**：本册
上一版把「260 配置 / 6 基准」记成二手博客的错数字、把「180 / 4」记成 arXiv 一手读数——方向
反了：那是读了 v2（或更早）的摘要后当成"当前版本"。处置：本表按版本分行登记（v3 为主，
v2 的 0.524 单列并标注"v3 已改"），正文同步改写。**教训：版本也是一种口径——"一手"必须
连版本一起说**，「最新版里没有」既不等于「论文里没有」（45% / 17.2x / 4.4x 在 v3 全文仍在），
也不等于「旧版里有」。

## 1c. 编排与协作上限（CP 轮补登记，2026-10-25 一手核验）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `yang2026dualcontrol` | 7,950 / 6 模型 / 3 族 | "over about 7,950 simulated conversations, with one completion-token ledger per episode per system"；"for six models from three families" | arXiv:2610.27655v1（2026-10-20），DOI 10.48550/arXiv.2610.27655 |
| `yang2026dualcontrol` | 12/13 负 / 1 平 | "the MAS is worse in 12 of the 13 valid cells and tied in the thirteenth" | 同上 |
| `yang2026dualcontrol` | -28 / [-44, -12] | "the fitted gain is negative across the observed capability range (weighted mean -28 points, 95% CI [-44, -12])" | 同上 |
| `yang2026dualcontrol` | 13 / 22 / 5.5x | "On the two cells where the rule predicts a benefit, the MAS loses by 13 and 22 points, and without a budget ceiling it at best draws level at 5.5 times the SAS's token spend" | 同上 |
| `yang2026dualcontrol` | 45% / -0.41 | "the crossing near 45% single-agent accuracy"；"slope -0.41, 95% CI [-1.51, +0.68]"（能力衰减方向未定） | 同上 |
| `yang2026dualcontrol` | 预注册 + 1 项有效性未达标 | "The study was pre-registered with a public change log; the MAS is reported as built, with one validity bar unmet (its planner never saw the tool schemas)" | 同上 |
| `yang2026dualcontrol` | 结论 | "For agents that serve people, the SAS is the default; a multi-agent design must show compute-matched evidence from the setting itself" | 同上 |
| `shu2026agentworld` | 100 + 100 变体 / 3–20 智能体 / 50+ 轮 | "a benchmark of 100 human-annotated tasks (with 100 augmented variants)"；"require 3-20 agents"；"Tasks span 50+ interaction rounds" | arXiv:2609.31590v1（2026-09-25），DOI 10.48550/arXiv.2609.31590 |
| `shu2026agentworld` | 52.0% | "even the best model achieves only 52.0% task success" | 同上 |
| `shu2026agentworld` | CCE 0.320 / 0.125–0.320 | "CCE ranges from 0.125 (DeepSeek) to 0.320 (Gemini), indicating that less than a third of all agent actions causally contribute to success even for the best model"（**全文** §3 与 Table 2；摘要只给指标定义与 52.0%，**不含**本读数——见下注 2） | 同上 |
| `tabassum2026vibecheck` | 15 仓库 / 3 代理 / 5 维度 | "an empirical study of unit test generation across 15 student-developed Python and JavaScript/TypeScript repositories"；"We evaluate Kiro, Antigravity, and Cursor with Claude Sonnet 4.5"；"a five-dimensional rubric" | POVC '26（ACM，DOI 10.1145/3843779.3844632），arXiv:2609.05978v2（2026-09-05 / v2 2026-09-14） |
| `tabassum2026vibecheck` | execution-adequacy gap | "Results show a clear execution-adequacy gap: generated tests are often runnable but frequently lack strong assertions and meaningful behavioral coverage"；"Weak assertions and missing edge cases occur more often than blocking failures" | 同上 |

**版本与来源冲突（必须留存）**

1. `shu2026agentworld` 的**录用信息**：多篇二手来源（中文技术站、agihunt、dair.ai 解读）称
   "COLM 2026 录用"。**一手复核（CP 轮）**：arXiv 元数据的 Comments 字段写
   "Accepted at COLM 2026"（作者提交的元数据，与项目主页 `agentworld.io` 同址声明一致）；
   OpenReview 以标题检索**无对应记录**。处置：`refs.bib` 仍以 arXiv 版本（`@misc` + eprint）
   登记，**不写 `booktitle`**——会议名只有 arXiv 元数据一处来源，缺独立第二源时不生成正式
   会议条目；正文按 2026-09-25 的 v1 引用。**教训**：把「OpenReview 查不到」当成「未录用」
   是把**单一索引的缺席**当成事实缺席（同族于 A4 的「路径存在 ≠ 数字在工件里」）——
   **索引缺席 ≠ 事实缺席**。
2. `shu2026agentworld` 的 **CCE 0.320**：arXiv **摘要**只给 CCE 的**定义**与 52.0% 任务成功率，
   **不含** 0.320；0.320 出自**全文** §3 与 Table 2（"CCE ranges from 0.125 (DeepSeek) to
   0.320 (Gemini)"），附录 Table 6 给跨 judge 的稳健性（0.320 / 0.338 / 0.330）。处置：本册登记
   **全文读数并标明定位**；正文由 "peaks at 0.320" 改为「四模型区间 0.125–0.320、最佳模型
   0.320」——原文并未主张峰值，只给区间与最佳模型。**教训**：摘要级检索只能回答「摘要里有没有」，
   不能回答「原文里有没有」——**摘要缺席 ≠ 原文缺席**（与上一条同族）。本册同轮的
   `tufano2026specops` p 值行也属同类：读数在，引文写成自指 "quoted above"，已改为内联原句。
3. `yang2026dualcontrol` 的 **-0.41 斜率**：原文明确写 "Whether the gain declines with
   capability is unresolved (slope -0.41, 95% CI [-1.51, +0.68])"。本登记册与正文都
   不把该斜率当作结论（区间跨零），只登记「该方向未定」这一事实本身。
4. `yang2026dualcontrol` 的 **45% 拐点**：原文写的是「最系统的既有研究给出的
   capability-saturation rule，拐点在单智能体准确率 45% 附近」——即该规则**来自
   Kim et al.（本册 §1b 已登记）**，本条只引用该规则的出处，不重复登记其读数。

## 2. 评测任务族与检出上限（RQ1 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `sun2026swemutation` | 10.20 / 36.15 | "even DeepSeek-V3.1 achieves only 10.20% verification and 36.15% detection rates" | Findings of ACL 2026, pp. 39651–39674（DOI 10.18653/v1/2026.findings-acl.1976） |
| `sun2026swemutation` | 71.04 / 39.81 | "reducing average detection rates from 71.04% to 39.81% compared to conventional methods" | 同上 |
| `sun2026swemutation` | 2,636 / 800 | "2,636 mutated variants derived from 800 original instances" | 同上 |
| `hamidi2026criteria` | ~99% | "traditional test criteria fail to trigger and detect almost all faults examined (approximately miss approximately 99% of them)" | arXiv:2609.09315v1（2026-09-08） |
| `hamidi2026criteria` | 6,000+ | "We collect 6,000+ faulty program instances" | 同上 |
| `liu2026testexplora` | 16.06 | "state-of-the-art models achieve a maximum Fail-to-Pass (F2P) rate of only 16.06%" | ICML 2026, PMLR v306 |
| `liu2026testexplora` | 2,389 / 482 | "2,389 tasks across 482 repositories" | 同上 |
| `liu2026testexplora` | 17.27 / 29.7 | "SWEAgent instantiated with GPT-5-mini achieves an F2P of 17.27% and an F2P@5 of 29.7%" | 同上（PMLR v306 页面摘要逐字，2026-10-25 一手核验） |

## 3. 规格锚点与「先测试后编码」（RQ4 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `tufano2026specops` | 9.8 / 53.4 / 63.2 | "a 9.8 percentage points (p = 0.0352) improvement in bug detection rate" over a 53.4% baseline, reaching 63.2% | SpecOps '26（DOI 10.1145/3842652.3843195；arXiv:2608.17177） |
| `tufano2026specops` | 2.5 | "a 2.5 percentage point (p = 0.0034) improvement in branch coverage" | 同上 |
| `tufano2026specops` | 0.0352 / 0.0034 | "a 9.8 percentage points (p = 0.0352) improvement in bug detection rate"；"a 2.5 percentage point (p = 0.0034) improvement in branch coverage" | 同上 |
| `tufano2026specops` | 90 | "a dataset of 90 historical production bugs from Google's Issue Tracking System" | 同上 |
| `konstantinou2026coding` | 25 / 14 | "a fault detection rate of 25% for a test-driven workflow versus approximately 14% when tests follow code generation" | arXiv:2607.05139v1（2026-07-06） |
| `konstantinou2026coding` | 13.2 | "Providing both sources reduces fault detection by 13.2% on average relative to the description alone" | 同上 |
| `konstantinou2026coding` | 15.1 | "providing only the implementation reduces it by 15.1%" | 同上 |

## 4. 论文中已存在、此前未登记的外部读数（本轮补登记）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `zhao2026misguidance` | 0.46 / 3.84 | "raises misguided tests from 0.46% to 3.84% of generated tests" | ISSTA 2026（见 `refs.bib`） |
| `zhao2026misguidance` | 8.51 / 2.98 | "reducing effective tests from 8.51% to 2.98%" | 同上 |
| `zhao2026coverage` | 13 | "Across thirteen model setups on Defects4J" | 同上（`refs.bib` 记为 ISSTA 2026 复现研究） |

## 5. 未采用的候选（登记为「查过但不用」，防止重复检索）

| 候选 | 为什么不引入正文 |
|---|---|
| SWT-Bench 榜单 2026 读数（Lite 89.1% / Verified 84.0%） | 榜单是滚动更新的运行产物，不是同行评审定稿；引用即过期。正文只把 SWT-Bench 作为**任务族**引用，不引榜首数字。 |
| 「多智能体没有更好」的博客/论坛实测（如 20 任务三组对比） | 非同行评审、无工件，不能作为证据。 |
| ICLR 2026 CAO workshop 的 prompt-drift 结果 | 与本稿 RQ2 的机制不同（协议漂移 vs 编排预算），且为 workshop poster；不扩范围。 |

## 6. 2026-10 新出前沿（CR 轮一手核验，2026-10-25）

> **核验方式**：`export.arxiv.org/api/query` 官方 Atom 响应的 `summary` 字段逐字取回，
> 作者名取自 Atom `author/name`，日期取自 `published`，主分类取自 `arxiv:primary_category`。
> 四篇均**无出版商 DOI**（`arxiv:doi` 缺席），故按 arXiv 口径逐条写明版本。
>
> **抓取面错位（本轮实测事故，必读）**：首次核验用 `arxiv.org/html/<id>v1`（**全文**页）
> 抓「摘要」，抄回的文本混入 `longtable`/`latex` 等 LaTeX 宏名——那是全文不是摘要。
> 官方 API 的 `summary` 才是本节逐字来源。**教训：arXiv 的「摘要」有三处**
> （abs 页 HTML、abs 页 PDF、API 的 summary），抓错面会抄进不存在的句子；
> 登记前必须确认取到的是 `summary` 字段。
>
> **来源冲突（留存）**：`charoosaei2026risks` 的二手中文解读（bytenote.net，
> 2026-10 抓取）给出另一组数字——「60,780 个突变」「官方套件能杀 58.6% / 54.0% / 16.0%」
> 「真抓到 2.6% / 2.4% / 4.8%」「假错误 16.9% / 8.4% / 16.9%」「异常预言占假错误的 37%–57%」。
> 官方摘要 v1 里**没有** 60,780 / 58.6% / 54.0% / 16.0% / 16.9% 这一组；
> 摘要的 2.4%-4.8% 与二手解读的真抓到区间一致，但两者的**指标定义不同**
> （摘要：reveal faults；二手：真抓到）。本册只登记官方摘要读数；二手那组数字
> **不入正文、不入登记册**，以免把「全文/其它批次读数」挂到摘要句子上。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `egashira2026testsuitebench` | 165 / 74 / 73 / 60 / 88 / 82 | "a benchmark of 165 open-source applications, each with a structured and detailed specification of intended behavior, a reference implementation, a reference test suite, and on average 74 mutants. Each mutant is generated from a single requirement of the specification and refined to isolate that behavior: 73\% are killed by exactly one reference test and, on average, by only 0.2\% of the remaining tests"；"even frontier coding agents struggle to generate strong test suites given our specifications, achieving mutation scores below 60\%, despite their suites being largely valid and 88\% of their tests passing on the reference implementation"；"implementations generated for the same specifications pass 82\% of the reference tests" | arXiv:2610.13065v1（2026-10-09；Egashira / Mündler-Sasahara / Müller / Vechev；cs.SE；无出版商 DOI） |
| `charoosaei2026risks` | 145 / 8%-17% / 2.4%-4.8% / 83%-91% / 83%-92% / 14%-30% | "Across 145 pull requests from SciPy, Qiskit, and pandas, 8%-17% of the generated tests are fault-enforcing, while only 2.4%-4.8% reveal faults. Fault-enforcing tests persist over time: after several subsequent commits, 83%-91% of them are still relevant and pass. They also accumulate: when the faults of all pull requests are combined in one codebase, 83%-92% remain enforced at the end of the commit history, and the developer-written test suite detects only 14%-30% of them" | arXiv:2610.11835v1（2026-10-08；Charoosaei / Richter / Papadakis；cs.SE；无出版商 DOI） |
| `israel2026verifies` | 46 / 0.006 | "a verifier in a fresh context detected more of the 46 seeded faults than the builder's tests (Holm-corrected p = 0.006) and surfaced the ambiguities of the specification, at the price of rare false oracles" | arXiv:2610.28667v1（2026-10-16；Israel Sion / April；cs.SE；无出版商 DOI） |
| `banik2026allsmoke` | 86,156 / 33,596 / 2,807 / 80.2 / 1.28 | "We conduct an empirical study of 86,156 test-file patches from 33,596 agent-authored PRs across 2,807 GitHub repositories produced by five coding agents"；"Applied at scale, 80.2% of test patches contain weak or no explicit oracle signals"；"strong oracles significantly improve merge likelihood (OR = 1.28, p < 0.001)" | arXiv:2606.18168v1（2026-06-16；Banik / Chowdhury / Shamim；cs.SE；comment: Accepted at the 8th IEEE International Conference on Artificial Intelligence Testing, 2026；无出版商 DOI） |

**口径提醒（引用这四行时必带）**：`egashira2026testsuitebench` 的 mutation score 是
「agent 生成的测试杀死 mutant 的比例」；本稿的 false-fix 边际率是「声明修复中实际未修的比例」。
两者数值区间接近但**指标不同、方向相反**，正文不得把两者并列成同一件事。
`charoosaei2026risks` 的 8%-17% 是「生成的测试中固化缺陷的比例」，也不是 false-fix 率。

## 7. 2026-10-08～10-22 新出（CS 轮第二次前沿对账，2026-10-26 一手核验）

> **核验方式**：`export.arxiv.org/api/query` 的 `summary` 字段 + arXiv abs 页逐字；
> 作者名取自 Atom `author/name`，日期取自 `published`。**11 月窗口为空集**——arXiv API
> 查 `id:2611*` 返回 `totalResults=0`（feed updated 2026-10-25T16:22:36Z），故本轮
> 「10 月中下旬至 11 月」在 11 月侧无文献可查。五篇均无出版商 DOI，逐条写明版本。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `lu2026swepatchtest` | 619 / 82,579 / 9.21 / 59.29 | "a test-generation benchmark with 619 tasks from SWE-bench Pro, SWE-bench Multilingual, and DeepSWE and 82,579 candidate patches collected from coding-agent trajectories"；"the best-performing configuration achieves only 9.21% JVR despite reproducing the reference transition on 59.29% of tasks" | arXiv:2610.18004v1（2026-10-13；Lu / Wang / Li / Tian / Chen / He / Chen；cs.SE；无出版商 DOI） |
| `li2026testprism` | 300 / 3000 / 28.00 / 59.67 / 8.67 to 9.00 | "comprising 300 test tasks from 17 sources and 3000 candidate implementations, evenly split between valid and invalid solutions"；"Joint Success Function reaches only 28.00%, whereas single reference success reaches 59.67%"；"TestHelix improves Joint Success Function by 8.67 to 9.00 percentage points" | arXiv:2610.12289v1（2026-10-08；Li / Hu / Huang / Jiang / Luo / Gao / Tan / Wang / Liu；cs.SE；无出版商 DOI） |
| `tuzikov2026robobugbench` | 33 / 24.2%-36.4% / 66.7 / 22.2 / 0.0027 / 11/11 / 4 | "a benchmark of 33 real, execution-validated defects in a pinned ROS 2 navigation stack"；"Three frontier models, each given 1 attempt per instance, repair 24.2%-36.4%"；"at 66.7% on instances graded by process survival against 22.2% on those graded by what the robot did (instance-level p = 0.0027)"；"counterfeit patches which suppress a failure without repairing the defect are accepted by the shipped rule 11/11, while a distributional rule over the same data rejects 4 at no cost in false rejects" | arXiv:2610.16369v1（2026-10-12；Tuzikov；cs.RO；已接收为 NeurIPS 2026 Verify-Agents workshop 非存档论文；无出版商 DOI） |
| `chen2026oraclefailures` | 4,194 / 4,320 / 2,883 / 94.3 / 65.5 / 24 to 34 / 57 / 54 / 3,240 | "recorded labels report 4,194 database passes over 4,320 episodes, replay gives 2,883, and success falls from 94.3% to 65.5%"；"it removes 24 to 34 points from each agent and changes which agent this matrix measures as strongest"；"on the 57 separable variant-target combinations it detects 54"；"a 3,240-episode ablation" | arXiv:2610.16067v2（2026-10-12 提交 / 2026-10-21 v2；Chen；cs.SE; cs.AI；abs 页 Comments：Submitted to Empirical Software Engineering；无出版商 DOI） |
| `ding2026specoracle` | 89.2 / 92.9 / 98 / 35 / 25 / 80.6 / 48.4 / 126 of 128 | "build a static audit for five languages that classifies every name-, path- and literal-level dependency of every scored test (held-out precision 89.2%, recall 92.9%)"；"On SWE-Milestone (98 graded milestones, 35 published runs), 25 milestones contain a test that depends on an unstated, non-inferable name or path"；"Build units with such a dependency fail in 80.6% of runs, against 48.4% for comparable units without one"；"withholding a single hidden name from the reference stops its unit's tests from compiling in 126 of 128 cases" | arXiv:2610.30635v1（2026-10-22；Ding；cs.CL；无出版商 DOI） |

**口径提醒（三处，引用这些行时必带）**：

1. `lu2026swepatchtest` 的 **9.21% vs 59.29%** 与本稿 false-fix 边际率 **59.58%** 数字相近但
   **方向相反、指标不同**：前者是「能复现参考补丁转换、但三重联合校验（JVR）不通过」的任务比例，
   后者是「声明修复中实际未修的比例」。**不得并列成同一件事**。
2. `chen2026oraclefailures` 与本稿**同投 EMSE**（abs 页 Comments 自陈 Submitted to Empirical
   Software Engineering），且其结论（评测装置本身是需要被审计的软件）**与本稿的方法学主张同向**
   ——投稿差异化须正面处理，不可回避。
3. `tuzikov2026robobugbench` 的 counterfeit patch（抑制症状而未修复缺陷）是**本稿 false-fix
   现象的机器人域外部对应物**，其「11/11 被现有规则接受」与「判别力受观测通道约束（observability
   bound）」两条，对本稿「检出优先协议的能力上限」构成**外部限定证据**（部分反驳「协议设计得当即可检出」）。

**未列入正文的备选（已核验，仅登记索引）**：`arXiv:2610.10619` TestJack（34.4% 被判正确的试验违反任务要求）、
`arXiv:2610.10150`（PoC 通过 ≠ 开发者测试通过）、`arXiv:2610.29143` VeeReview（EMSE 在审 + 负结果）、
`arXiv:2610.21570`（coverage 只证明到达状态）、`arXiv:2610.03080` MintEval、`arXiv:2610.27272`
（450 个注入缺陷只检出 47.6%）。

## 8. CU 轮第二批前沿（六篇，2026-10-26 一手核验）

> **核验方式**：`export.arxiv.org/api/query` 的 `summary` 字段逐字取回（作者名取自 Atom
> `author/name`，日期取自 `published`）；本批含**上两轮检索窗口遗漏**的 2026-09/10 早期工作
> （检索时窗与召回策略的盲区，与「11 月窗口为空集」是同一族问题）。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `bai2026silentfailures` | 95 / 3,684 / 93 / 5 / 14 of 19 | "We evaluate SAGE on 95 confirmed silent failures drawn from 3,684 repair traces produced by six agent frameworks and six base models on SecurityEval and CVEfixes. SAGE assigned an origin in 93 cases. Most origins were an unaddressed security requirement or an inadequate defence choice, and only five coincided with the code change itself. When the agent introduced the vulnerable code, the origin preceded the write in 14 of 19 cases" | arXiv:2610.06163v1（2026-10-05；Bai / Waseem / Rasheed / Peltonen / Abrahamsson；cs.SE；无出版商 DOI） |
| `liang2026testevidence` | 95 / 29 September 2026 | "A test that increases implementation coverage, a test that agrees with a reference program, and a test that detects a requirements violation therefore provide distinct kinds of evidence"；"Drawing on 95 curated source records through 29 September 2026"；"derive a research agenda for independent oracle assessment, budget-aware generation, repository-scale evaluation, and test maintenance" | arXiv:2610.05001v1（2026-10-04；Liang / Gan / Ying / Wei / Cui / Ni；cs.SE；无出版商 DOI） |
| `hegde2026detectionnotenough` | 0.741 / 1,319 / 71.0 / 60.6 / 31.6 / 45.5 / 66 | "Checking a trace against itself reaches an AUROC of 0.741 and stops there for a structural reason: two thirds of wrong traces state no false equation"；"Valid perturbations exist for 937 of 1,319 test questions (71.0%); among the 847 that also have a parseable first trace, supported traces are correct 60.6% of the time against a 31.6% base rate, although the probe also refutes 45.5% of correct traces"；"even a perfect detector would recover an estimated 66 of 1,319 questions. Repair, not detection, is the open problem" | arXiv:2610.30200v1（2026-10-21；Hegde；cs.SE；abs 页 Comments：17 pages, 8 figures, 9 tables；无出版商 DOI） |
| `adeniji2026tracedetectors` | 67/67 / 19/19 / 18/18 / 67/81 / 14 / 21/30 → 27/30 | "agrees perfectly with the automated labels for final correctness (67/67), fault impact (19/19), and fault relevance (18/18), but only 67/81 for verification; all 14 disagreements fall into four recurring patterns"；"one ranges from 21/30 to 27/30 correct as step and token budgets change" | arXiv:2610.30491v1（2026-10-21；Adeniji / Shilpika / Papka；cs.SE；无出版商 DOI） |
| `xiong2026shallowtests` | 75.95% / 84.76% / 69.89% / 122 / 88 / 69 | "with less than half of its lines and branches covered by existing tests"；"achieving 75.95%/84.76% larger line/branch coverage gains and 69.89% larger mutation-score gains"；"detects 122 real-world harness bugs in widely-used agentic systems (e.g., OpenClaw), among which, 88 bugs are previously-unknown bugs and 69 bugs have been confirmed by agent developers" | arXiv:2610.04921v1（2026-10-04；Xiong / Ge / Chen / Lou；cs.SE；无出版商 DOI） |
| `liang2026oracleconversion` | 506 / 142 / 28.59 / 42.54 / 24.06 / 25.27 / 12.23 / 14.15 / 21.60 | "On an audited TC-Bench split with 506 training and 142 evaluation tasks, three independently trained Qwen3.5-9B runs at step 75 increase full-test correctness from 28.59\% to 42.54\%, input kill from 24.06\% to 25.27\%, and effective full kill from 12.23\% to 14.15\%"；"removing kill rewards yields higher correctness and slightly higher full kill, but lowers input kill to 21.60\%" | arXiv:2609.05879v1（2026-09-05；Liang / Gan / Ying / Wei / Cui / Ni；cs.SE；无出版商 DOI） |

**四处置顶纪律（引用本节时必带）**：

1. **`liang2026testevidence` 是综述，直接把本稿的核心口径表述成了领域共识**：「覆盖率 / 与参考一致 /
   检出需求违反 = 三类不同证据」，且其研究议程首项即「independent oracle assessment」。⇒ 本稿
   **不能**再把「检出优先优于覆盖率」写成新发现；可主张的差异化只有：**函数级 + 预注册 + 阴性
   结果 + 零 LLM 复算包 + 测量装置自身的审计**（综述不含这些）。
2. **`hegde2026detectionnotenough` 与本稿协议存在张力**：它论证「检出不是终点，修复才是」并给出
   检出的结构性天花板（AUROC 0.741）。**但问题设置不同**——它判「无参考解的推理轨迹是否正确」，
   本稿判「已声明的修复在已知 bug–fix 对上是否真修复」（有 gold 参考、执行式裁决）⇒ 它的
   天花板论证**不覆盖**本稿的测量对象，但本稿也**不得**主张「检出优先能解决修复问题」。
3. **`bai2026silentfailures` 是本稿 false-fix 现象在安全域的外部对应物**：95 例 silent failure
   中**只有 5 例**的起因与代码改动本身重合 ⇒ 本稿「声明修复里有多少不是修复」这个问题**已被
   别人在不同域实证过**，本稿的增量是**口径**（条件率 / 边际率 / 声明率扰动）而非现象的首次发现。
4. **`adeniji2026tracedetectors` 与本稿同向**（自动标签是测量产物、须带轨迹证据与执行预算说明），
   但审计对象不同：他们审计 agent 评测的 trace detector，本稿审计**自家流水线报告出的数字**。

**未列入正文的备选（已核验，仅登记索引，避免下轮重复检索）**：`arXiv:2610.30924` REGATTA、
`arXiv:2610.30495` ARATest、`arXiv:2610.06366` VERA、`arXiv:2610.14443` LEST、
`arXiv:2610.30499` ARC-AGI-3、`arXiv:2610.14808` Testuary、`arXiv:2610.29549` 快照测试、
`arXiv:2610.19447` BenchChecker。
