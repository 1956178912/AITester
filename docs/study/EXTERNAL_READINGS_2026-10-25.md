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

## 9. 2026 全年回溯对账新增十篇（CW 轮，2026-10-26 一手核验）

> **核验方式**：`export.arxiv.org/api/query` 的 `summary` 字段逐字取回（作者名取自 Atom
> `author/name`，日期取自 `published`），每段引文先断言存在于官方 summary 再写入本表。
>
> **为什么是回溯**：前两轮检索只盯「最新窗口」（10 月下旬），因而**漏掉了 2026 年 9/10 月
> 已发表、且直接占位本稿核心论断**的工作。本轮按「扫 2026-01-01～10-26 全部 cs.SE 共
> 6,500 条，13,822 条候选池去重后按 11 维加权过滤得 981 条高相关候选，逐篇判读」做完全年回溯，
> 补回下表十篇；另有**安全域 silent failures**（arXiv:2610.06163v1）与**测试生成综述**
> （arXiv:2610.05001v1）两篇已在 §8 登记，此处不重复，只在 §9.1 引用其 novelty 含义。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `tan2026beyondfailtopass` | 69.4 / 78.9 / 9.6 / 7.9 | "Experiments show that CoHarden reaches 69.4% Resolved and 78.9% F->P on SWE-bench Verified, outperforming the strongest fix-only and cogeneration baselines by +9.6 and +7.9 percentage points in Resolved, respectively We show that F->P alone is insufficient when the goal of a BRT is to improve downstream repair some F->P BRTs are lax, reproducing the observed symptom yet still admitting plausible-but-incorrect patches separating F->P BRTs into rigorous and lax ones, and show empirically that only the former consistently improve repair success the in-trajectory fail-to-pass (F->P) check" | arXiv:2607.19843v1（2026-07-22；Tan / Yang / Yang / Yao / Kang / Wang / Zhao / Zhang / Ma / Lin / Rajmohan / Zhang；cs.SE；无出版商 DOI） |
| `liang2026tddsurvey` | 87 / 83 | "The review integrates 87 research and supporting records, with method- or protocol-level extraction for 83 records aggregate improvements can also conceal different outcomes across models, tasks, and denominators" | arXiv:2609.12012v1（2026-09-10；Liang / Gan / Ying / Wei / Cui / Ni；cs.SE；无出版商 DOI） |
| `liang2026oracleaudit` | 142 / 114 / 138 / 27.79 / 50.12 / 9.46-14.85 / 6.01-18.83 | "We audit this failure mode in feedback-driven test generation using 142 development tasks, 114 locked external tasks, and 138 held-out tasks generated outputs match the panel on only 27.79% and 50.12% of cases A single-reference oracle inflates the measured gain from evolution by 9.46-14.85 percentage points after auditing, equal-budget independent resampling outperforms mutation-based evolution by 6.01-18.83 points" | arXiv:2608.19626v1（2026-08-20；Liang / Gan / Ying / Wei / Cui / Ni；cs.SE；无出版商 DOI） |
| `yu2026sweabs` | 78.80 / 50.2 / 25.1x / 19.71 / 62.20 | "the top system achieving 78.80% On SWE-Bench Verified (500 instances), SWE-ABS strengthens 50.2% of instances, a 25.1x improvement over prior work, and rejects 19.71% of previously passing patches the top agent's score decreases from 78.80% to 62.20%" | arXiv:2603.00520v1（2026-02-28；Yu / Cao / Zhang / Lin / Xu / Zhong / Xu / Wang / Cao / Cheung / He / Briand；cs.SE；无出版商 DOI） |
| `paul2026behaviouralgaps` | 8,922 / 20,729 / 93.1 / 17.5 / 20.6 / 27.1 | "across ten popular open-source Java libraries comprising 8,922 methods, extracting 20,729 behaviours with 93.1% precision Our empirical analysis conservatively estimates that 17.5% of detected expected behaviours remain entirely untested they similarly fail to validate at least 20.6% / 27.1% of detected expected behaviours" | arXiv:2606.10417v1（2026-06-09；Paul / Holmes；cs.SE；无出版商 DOI） |
| `alahmad2026classleveltests` | 无数字 | "high structural coverage does not establish that those tests execute reliably or detect faults Human and LLM suites are evaluated on unequal executable subsets, so their relative mutation scores do not establish superiority Structural coverage is consistently near its ceiling and offers little discrimination among configurations" | arXiv:2609.24341v1（2026-09-21；Al-Ahmad / Harshvardhan / El-Fakih / AlSobeh；cs.SE；无出版商 DOI） |
| `liang2026sectdd` | 2,705 / 31 / 16 / 19.3 / 80 / 83 / 453 | "Across 2,705 trajectories, 31 task instances, three secure-code benchmarks, 16 CWE categories, and two model families showing all visible tests upfront increases hidden functional-and-security joint success by 19.3 percentage points on average structured feedback repairs 80 initially unsuccessful candidates with no joint regressions; fixed raw feedback repairs 83 but causes three regressions six wins, six losses, and 453 ties" | arXiv:2608.09740v2（2026-08-10 提交 / 2026-08-11 v2；Liang / Gan / Ying / Wei / Cui / Ni；cs.SE；无出版商 DOI） |
| `smyth2026overclaim` | 67.9 / 80.4 / 59-96 / 1.8 | "agents fail to read every file they were asked to review in 67.9% of runs among these incomplete runs, agents are misleading 80.4% of the time (59-96% per model) agents that falsely claim a complete review miss planted defects at about 1.8 times the rate of agents that read every file" | arXiv:2609.20812v3（2026-09-17 提交 / 2026-09-22 v3；Smyth / Mantilla-Ramos / Notsawo / Helbling / Tosato / Merzouk / Dziri / Gidel / Tosato；cs.SE；无出版商 DOI） |
| `otterson2026instrumentautopsy` | 105 / 9.5e-66 / 78 / 0.783 / 0.592 / 0.935 | "the loop killed 105 mutants that one-shot generation missed and lost none an earlier analysis reported a cross-lineage effect at p = 9.5e-66 that was an instrument artifact, an output cap silently truncating the verbose model killed 78% of the survivors the frozen initial suite left standing (mean incremental kill rate 0.783, 95% cluster-bootstrap interval [0.592, 0.935])" | arXiv:2607.23002v1（2026-07-25；Otterson；cs.SE；abs 页 Comments：26 pages, two pre-registered experiments；无出版商 DOI） |
| `xu2026discriminatingfixtures` | 无数字 | "the evidence offered for any particular suite is almost always a single observation: it passes an implementation believed correct and fails one believed broken neither is visible from a pass/fail report we enumerate seven discriminating dimensions of the input space, register in advance which are uncovered and which survivors they should explain" | arXiv:2610.02928v1（2026-10-02；Xu / Tao；cs.SE；abs 页 Comments：10 pages, 1 figure, 2 tables. NeurIPS 2026 Workshop: Who Verifies the Agents?；无出版商 DOI） |


### 9.1 对本稿 novelty 的影响（必读）

| 本稿原口径 | 已被占位者 | 时间 |
|---|---|---|
| F→P 判定不充分 | arXiv:2607.19843（rigorous/lax 分解 + test–fix error coupling） | 2026-07-22 |
| 「测试通过 ≠ 行为等价」是领域共识 | arXiv:2609.12012（scoping survey 结论段明写，且点名 denominators） | 2026-09-10 |
| 独立裁决 / 参考无关验证 | arXiv:2608.19626（audit-and-placebo）+ arXiv:2607.23002（机械裁决 + 装置尸检）+ arXiv:2610.02928（登记式判别维度） | 2026-07～10 |
| 装置效度审计 + 预注册 | arXiv:2607.23002 | 2026-07-25 |

**本稿尚可保留的三块增量**（上述文献均未报告）：

1. **false-fix 的口径分解**——条件口径与边际口径**并列**报告（分母分解）；被占位者报告的是
   单一口径下的比例，未做分母分解。
2. **声明率本身被协议扰动**——把装置伪影从「某个具体实现的伪影」上升为「口径层面的量」：
   同一批数据在两个声明率下给出两个不同的假修复率，读者据此无法脱离声明率引用该数。
3. **测量效度 × 声明率的联立**——效度批评（覆盖率/变异分数不足以代表检出能力）与
   false-fix 口径在**同一份数据**上联立，而不是两篇论文各说一半。

**本轮已据此改正文与投稿信**：正文 Related Work 补三段（八篇新引），Introduction 的贡献
引导句改为「Our contribution is not a new observation … It is a decomposition at the level of
denominators」，投稿信点名四篇被占位文献并把增量限定为「上述工作都没有报告的那一项」。

### 9.2 覆盖缺口（如实说明，不让「没搜到」冒充「不存在」）

DBLP / ACM DL / IEEE 官方页在本环境被代理拦截（DBLP API 四次重试均返回 HTML 而非 JSON），
非 arXiv 渠道的 2026 年论文只能通过 arXiv comment 字段间接覆盖 ⇒ **可能存在仅在 ACM DL /
IEEE Xplore 上线、未同步 arXiv 的 9/10 月论文未被本轮覆盖**。

**备选索引（已核验，未列入正文，避免下轮重复检索）**：`arXiv:2608.17214`、`2609.28896`、
`2608.17177`、`2606.08588`、`2604.21579`、`2608.13404`、`2602.03585`、`2605.02096`、
`2610.03969`、`2609.34752`、`2608.23341`、`2603.07520`。

## 10. CY 轮（2026-10-26）新增八篇：回溯扫描的**召回缺口**与三处novelty 再收窄

> **核验方式**：`export.arxiv.org/api/query`（https）的 `summary` 字段逐字取回（作者名取自 Atom
> `author/name`，日期取自 `published`，版本号取自 arXiv id）；每段引文**先断言存在于官方 summary
> 再写入本表**（CY 轮实测 19 条引文逐字命中，坏引文 0）。
>
> **为什么本轮又做一次检索**：CW 轮已按「2026-01-01～10-26 全年回溯」扫过一遍，本轮按
> 「2026-10-19～10-26 共 120 条新投稿」逐条标题+摘要判读，发现**其中 8 篇与本稿核心论断的
> 关系比 CW 轮选中的十篇更近**——它们恰好落在 CW 轮 11 维加权的**低分区**：它们的领域词是
> 「harness / verifier / instruction file / assurance evidence / requirements engineering」，
> 而不是「test generation / mutation / SWE-bench」。**这是一次召回缺口，不是检索窗口缺口。**
> ⇒ 结论：CW 轮的「全年回溯」在**关键词覆盖**上仍有系统性盲区，回溯对账必须按**论断族**检索，
> 不能只按**领域词**检索。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `zuppardo2026beyondaccuracy` | 18 条件 / 625 需求 / +0.075 / -0.003～+0.013 / 3 个 7–8B 模型 | "The 18 conditions cover PROMISE NFR+ (625 requirements), three locally hosted small language models, and two languages."；"The F1 gain over the baseline is associated with the two-call, specialized-prompt variant (up to +0.075), whereas the typed state adds a small difference (-0.003 to +0.013) that is significant in one of six comparisons."；"The study is associative: the contrasts bundle prompts, call count, and staged context, and the results come from three 7--8B models on one dataset." | arXiv:2610.31280v1（2026-10-22；cs.SE；SBQS 待发表；无出版商 DOI） |
| `curmi2026harnessmatter` | 24 配置 / 265 根因 / 60.4% / 14.3% / 20–86% vs 2% | "We study 24 model-runner configurations using an open-source harness on a production codebase whose vulnerabilities were non-public at scan time."；"moving from a minimal prompt to an engineered prompt with a CodeQL-derived call graph raises criticality-weighted yield by 20-86% for smaller and mid-tier models, compared with 2% for the frontier model"；"Separating those effects shows that the engineered prompt improves yield for all four models, while adding CodeQL context beyond that prompt improves yield only for the smallest model."；"Across 265 confirmed security root causes, the largest two-run configuration covers 60.4%, while 14.3% are found by exactly one model." | arXiv:2610.28802v1（2026-10-20；cs.CR；CAMLIS 2026 已接收；无出版商 DOI） |
| `xu2026staleinstructions` | 40 项目 / 320 次运行 / 90.1% / 79-of-80 / 4.2%→91.4% / 89.4%→100% | "We built 40 Python projects in which the instruction file asks for one convention while the existing code uses another, for example print instead of logging."；"in 320 runs."；"Without the sentence, 90.1% of the agents' choices followed the stale file."；"Claude Code pointed out the conflict in 79 of 80 runs and still followed the file."；"The sentence raised the share of choices that follow the code from 4.2% to 91.4%, stopped the rewrites and raised the test pass rate from 89.4% to 100%." | arXiv:2610.30571v1（2026-10-22；cs.SE；SN Computer Science 在审；无出版商 DOI） |
| `zhu2026selfreportleakage` | 43.4 pp / 13.3 pp / F1 0.75–0.78 / 0.77–0.81 | "Withholding it improves trace-only dangerous-misreport recall by 43.4 percentage points with Qwen3.5-35B-A3B and 13.3 percentage points with DeepSeek-284B-A13B"；"an unhedged success claim that the trace does not support as causal accomplishment during the run"；"The auditor achieves F1 0.75--0.78 on the 465-record audit-target set and 0.77--0.81 on held-out Batch 2, outperforming claim-aware and prompt-blind controls in recall and F1." | arXiv:2610.29609v1（2026-10-21；cs.SE；ICSE 2027 Research Track 已接收；无出版商 DOI） |
| `yin2026verifierbench` | 19 模型 / 10.6–62.1 | "Across 19 models in a common agent harness, normalized balanced accuracy ranges from 10.6 to 62.1, with generated verifiers consistently rejecting invalid solutions more reliably than they accept valid ones"；"These errors survive self-testing because agents test solutions that share the verifier's mistaken assumptions, or submit verifiers without confirming that any correct solution passes." | arXiv:2610.28679v1（2026-10-19；cs.SE；无出版商 DOI） |
| `weber2026evaluationscarcity` | 经验报告（单开发者 / 单系统 / 无对照） | "Several defects passed the test suite: they sat at the boundaries the tests had mocked, the browser and the language-model API, or appeared only in real use."；"Writing code becomes abundant. Reliable evaluation-knowing whether a result is correct and meets the actual need-remains necessary at every iteration and becomes the binding constraint." | arXiv:2610.30916v1（2026-10-22；cs.SE；经验报告（证据等级最低）；无出版商 DOI） |
| `mukhopadhyay2026assuranceevidence` | 83.4% / 3.3% / 31% | "Reuse is safe only if each control's declared dependencies cover everything that can change its outcome, and only if the release gate checks that reused evidence describes the candidate being released."；"Reusing stage results according to declared dependencies avoids 83.4% of stage executions, but in 3.3% of commits it reuses a stage whose imported code or referenced configuration changed, and 31% of pipelines are affected." | arXiv:2610.27672v1（2026-10-20；cs.CV；无出版商 DOI） |
| `quan2026agentest` | 60% | "about 60% of bug-triggering runs cannot be detected from the final state alone, highlighting the need to check the full interaction against explicit business rules"；"Violating such rules can lead to business logic bugs, even when a task appears successful." | arXiv:2610.28116v1（2026-10-20；cs.SE；无出版商 DOI） |

### 10.1 三处 novelty 再收窄（本轮新增占位者）

| 本稿原口径 | 本轮新增占位者 | 本稿因此必须让渡什么 | 本稿仍保留什么 |
|---|---|---|---|
| 「编排/流水线的收益由**提示文本**承载，而非由**结构**承载」 | `zuppardo2026beyondaccuracy`（2610.31280：F1 增益归于「专门化提示词的两调用变体」+0.075，类型化状态只加 -0.003～+0.013，18 条件 625 需求）＋ `curmi2026harnessmatter`（2610.28802：把最小提示换成工程化提示 + CodeQL 调用图，较小/中等模型 +20–86%、前沿模型 +2%；**分离**后工程化提示对四个模型都有效，额外上下文只对最小模型有效） | **不得再声称「我们第一个发现流水线的收益来自提示文本而非结构」**。两篇已在**需求工程**与**漏洞发现**两个域各自独立得到同向结论；且 `zuppardo2026beyondaccuracy` 自陈其对比**捆绑**了提示、调用次数与分阶段上下文，**并未真正分离**。 | ① **分母层面的分解**（条件口径 vs 边际口径；文本承载 vs 它授权的再生成预算**分别计价**）；② **预注册**；③ **经 F→P 裁决的检出**而非 F1；④ **被审计过的装置**（含它自身的失效模式）。 |
| 「指令文件是一等因果对象」 | `xu2026staleinstructions`（2610.30571：过期指令文件在 90.1% 的运行里压过代码；Claude Code 在 79/80 次里**明确指出冲突仍然照旧执行**；一句话把「跟随代码」从 4.2% 提到 91.4%，测试通过率 89.4%→100%） | **不得再声称「指令文本会压过代码」是新发现**。这已是**机制级**证据（40 项目 × 320 次运行、两个商用编码 agent）。 | ① 本稿测的是**检出收益**而非**风格选择**；② 本稿的指令段落是**被测量的对象**（196 字符、可单独计价），而不是被当成「配置」；③ 本稿的结论是**该段落不授权再生成就不产生检出**。 |
| 「谁裁决 / 装置自身的效度」 | `zhu2026selfreportleakage`（2610.29609：撤掉 agent 的自述报告，轨迹口径的危险误报召回 +43.4 pp / +13.3 pp）＋ `yin2026verifierbench`（2610.28679：生成的验证器**拒绝**无效解比**接受**有效解更可靠，平衡准确率 10.6–62.1；「这些错误之所以躲过自测，是因为 agent 用与验证器共享的错误假设去测」）＋ `mukhopadhyay2026assuranceevidence`（2610.27672：证据复用只有在**声明的依赖**覆盖一切可变项时才安全；714 条 DVC 管线的回放里 3.3% 的提交复用了已变更的阶段） | **不得再声称「裁决者必须与被裁决者分离」或「复用证据需要依赖闭包」是新发现**。 | ① 本稿的 F→P 裁决**不消费被测者的自述**（因此不落在 `zhu2026selfreportleakage` 的泄漏面）；② 本稿对**自家装置**做失效模式审计并公开其上限（可执行预言机 16/20 任务成功但**不**提升检出）；③ 本稿的**归档工件复用**同样受 `mukhopadhyay2026assuranceevidence` 的依赖闭包约束——这一点已转成本仓库的**可执行判据**（见 `scripts/tools/audit_paper_numbers.py` 的 SRC 存在性/数字存在性面）。 |

### 10.2 两条**同向证据**（不再是占位者，而是外部收敛证据）

- `weber2026evaluationscarcity`（2610.30916）：经验报告层级（证据等级最低，须显式标注），但其观察与本稿的 false-fix 现象**同构**——「若干缺陷通过了测试套件：它们位于测试所 mock 的边界上……或只在真实使用中出现」。本稿的 false-fix 是**声明侧**的同一形状（声明被接受，缺陷未修复）。
- `quan2026agentest`（2610.28116）：「约 60% 的触发缺陷运行**无法仅从最终状态**检出」与本稿的轨迹/状态裁决需要同向；其「即使任务看起来成功，仍可能违反业务规则」与本稿的「声明成功但未修复」是同一族表述。

### 10.3 本轮**未**解决的覆盖缺口（诚实登记）

- 本轮检索窗口仍是 **arXiv cs.SE + cs.CR + cs.CV 的 2026-10-19～10-26**；非 arXiv 渠道（DBLP / ACM DL / IEEE Xplore）
  在本环境仍被代理拦截，**可能存在只在 ACM DL / IEEE 上线、未同步 arXiv 的同期论文未被覆盖**。
- **结构性缺口（可复算）**：CW 轮的全年回溯**只扫了 cs.SE**（登记册 §9 自陈「全部 cs.SE 共
  6,500 条」）。而本轮八篇里有**两篇的主分类不在 cs.SE**——`curmi2026harnessmatter` 主分类
  **cs.CR**、`mukhopadhyay2026assuranceevidence` 主分类 **cs.CV**——它们**结构上不可能**被
  CW 轮的扫描覆盖。⇒ 后续检索**必须**把 cs.CR / cs.CV 纳入同一次扫描，并在登记册里**逐轮
  写明扫描的分类集合**（否则「全年回溯」这个说法会掩盖它其实只覆盖了一个分类）。

## 11. CZ 轮（2026-10-26）跨分类 + **按论断族**召回：八篇新增（**三篇直接占位本稿核心现象**）与累计让渡的再核

> **核验方式**：`export.arxiv.org/api/query`（https）的 `summary` 字段逐字取回（作者名取自 Atom
> `author/name`，日期取自 `published`）；每段引文**先断言存在于官方 summary 再写入本表**
> （CZ 轮实测 25 条引文逐字命中，坏引文 0）。
>
> **扫描的分类集合与检索词（CY 轮 §10.3 承诺「逐轮写明」的兑现）**：
> **分类集合 = cs.SE ∪ cs.CR ∪ cs.CV**（CY 轮发现 CW 轮的「全年回溯」**只扫了 cs.SE**，
> 而本轮最同题的两篇主分类在 cs.CR / cs.CV ⇒ 结构上不可达）；**时间窗 = 2026-01-01～10-26**；
> **检索式 = 12 条「论断族」查询**（不是领域词）：
> F1 `all:"fail-to-pass"`｜F2 `all:"behavioral equivalence"`｜F3 `all:"reference-free"` /
> `all:"independent verification" AND all:"agent"`｜F4 `all:"harness" AND (all:"agent" OR
> all:"LLM") AND all:"evaluation"`｜F5 `all:"instruction file"` / `all:"AGENTS.md"` /
> `all:"CLAUDE.md"`｜F6 `all:"stale" AND all:"evidence" AND (all:"reuse" OR all:"pipeline")`｜
> F7 `all:"declared" AND all:"repair" AND all:"agent"`｜F8 `all:"multi-agent" AND
> (all:"attribution" OR all:"decompose")`｜F9 `all:"mutation testing" AND (all:"LLM" OR
> all:"language model")`｜F10 `all:"oracle" AND (all:"generated test" OR all:"test
> generation")`｜F11 `all:"success claim"` / `all:"self-report" AND all:"agent"`｜F12
> `all:"specification" AND all:"LLM" AND all:"test generation"`。
> **命中与分页**：12 条查询共命中 1,100 余条次，**去重后 817 篇**候选（对 F3/F4/F8 翻页至
> 深度 300，弥补首次扫描的 100 条截断）；剔除登记册已收录的 57 篇后，**未登记候选 791 篇**，
> 逐条以标题+摘要判读其与本稿论断族的关系。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `tao2026execcritic` | 61.2%→57.3% / 65.3% / 22.2%→62.2% / 72.6% / +11.4 pp | "Agent-generated tests can encode incomplete or incorrect behavioral targets; when the same trajectory writes both the patch and the test, their errors can agree and create false confidence."；"a fail-closed harness qualifies and freezes them, and a Repair agent revises source code from their execution feedback without changing the tests"；"tests from the base Test agent reduce resolved rate from a no-test baseline of 61.2% to 57.3%, whereas tests from GPT-5.6-sol raise it to 65.3%"；"Role-specific post-training raises the Qwen Test agent's Base-to-Gold success from 22.2% to 62.2%; composing the two post-trained Qwen agents reaches 72.6%, an 11.4-point gain over the original no-test baseline" | arXiv:2609.09133v1（2026-09-08；cs.AI；35 页；无出版商 DOI） |
| `kim2026coherencecollapse` | 16,758 轨迹 / 3 架构 / 7 模型 / 60–69% / 5 例 / +3.0 pp (p=0.08) | "We introduce TRAJEVAL, a training-free decomposition of agent trajectories into reference-patch-aligned search, read, and edit stages, and apply it across 16,758 trajectories spanning three architectures and seven models."；"60-69% of failures on SWE-Agent and OpenHands reach and edit the correct functions yet still produce incorrect patches"；"In 5 cases, the agent produces a patch bit-identical to the gold reference mid-trajectory and destroys it later"；"A reference-free consensus-driven variant yields a directional +3.0 pp Pass@1 measurement on GPT-5 (p=0.08)" | arXiv:2603.24631v2（2026-03-25；cs.SE；无出版商 DOI） |
| `bhat2026benchmarkingbenchmarks` | 4 个基准族 / 496 任务 / 92 处分歧 / 18.5% / 57.9%–76.8% / 18.9 pp | "We present a systematic validity and reproducibility audit of four major tool-calling benchmark families: BFCL v4, τ2-Bench, LiveMCPBench, and MCP-Atlas."；"Across 496 expert-reviewed benchmark tasks, we find 92 evaluator-human disagreements, corresponding to an 18.5% misalignment rate."；"In LiveMCPBench, 23 repeated evaluations of the same setup produce scores ranging from 57.9% to 76.8%, a spread of 18.9 percentage points, large enough to change leaderboard conclusions."；"progress in tool-using agents requires benchmarks whose evaluators are themselves reproducible, auditable, and aligned with human judgments of task success" | arXiv:2607.02577v1（2026-06-30；cs.SE；无出版商 DOI） |
| `lewis2026sameharness` | 169 任务 / 20,480 token / 480 秒 / F2PF 28%→49% / 解 43→72 | "The tight-window Verified comparison uses 169 tasks, a 20,480-token window, and a fixed 480-second attempt endpoint; on this cohort, treatment raises mean per-task F2PF from 28 percent to 49 percent and complete solutions from 43 to 72."；"Because changing the harness changed what unchanged model weights could accomplish, coding-agent evaluations should treat the model and harness together as the tested solver." | arXiv:2608.26218v1（2026-08-26；cs.AI；24 页；无出版商 DOI） |
| `sghaier2026harnesshierarchy` | 35 个连续版本 / 5 个开源 harness | "conducting the first controlled longitudinal study that isolates the agent harness contribution"；"we fix the model and vary only the agent harness, evaluating 35 sequential releases to measure their impact on agent effectiveness and efficiency"；"We first empirically study the development and release evolution of five major open-source agent harnesses (i.e., Codex, Qwen Code, Gemini, OpenCode, and OpenHands), revealing extreme release velocities exceeding two releases per day" | arXiv:2607.03691v2（2026-07-04；cs.SE；无出版商 DOI） |
| `gloaguen2026whentoact` | 200 个人工核验任务 / 5 模型 / 35%–65% | "we introduce FixedBench, a code benchmark with 200 human-verified coding tasks in which no code changes are required, testing five recent models across four agent harnesses"；"proposing undesirable changes (excluding tests and documentation) in $35$ to $65\%$ of cases"；"Explicit instructions to reproduce the issue before patching partially address this issue but introduce a new failure mode" | arXiv:2605.07769v1（2026-05-08；cs.SE；无出版商 DOI） |
| `yu2026deceptiveresumes` | 32,000 份描述 / 23.35% / 8 种攻击 / 84.31%→37.25% / >111% | "Among 32,000 descriptions from three public agent marketplaces, most omit input specifications and usage constraints, while at least 23.35% contain content outside these fields."；"We construct eight description-manipulation attack strategies targeting task decomposition, capability grounding, and subtask specification, and evaluate them on GAIA."；"a single manipulated description reduces task success from 84.31% to 37.25%, or increases token consumption or execution time by over 111%" | arXiv:2609.15516v1（2026-09-14；cs.CR；18 页；无出版商 DOI） |
| `dan2026swepro_v2` | 731 任务中修/废 480 个 / 23 名工程师 / 404 小时 / 642 任务 | "Agentic audits, expert adjudication and blind re-implementation repaired or retired 480 of the 731 tasks: 23 contracted engineers spent 404 hours"；"A hardened protocol restricts network access to the model endpoint and re-grades every patch in a clean container, so agents cannot retrieve upstream fixes or get credit for changes outside their patch."；"On the 642 V2 tasks frontier agents resolve up to 99.4% while other systems stay clearly separated, and a 51-task Hard split spreads systems from 52.9% to 98.0%." | arXiv:2610.24206v1（2026-10-16；cs.SE；无出版商 DOI） |

### 11.1 三篇**直接占位本稿核心现象**的工作（必须正面处理，不可回避）

| 本稿原口径 | 占位者 | 时间 | 后果 |
|---|---|---|---|
| **「同一轨迹既写补丁又写测试 ⇒ 两者的错误会互相印证 ⇒ 虚假信心」**——本稿 false-fix 现象的机制表述 | `tao2026execcritic`（2609.09133：**逐字写出了这句话**，并给出解法：测试由独立 Test agent 生成、**fail-closed harness 合格化并冻结**、Repair agent 只读执行反馈且不得改测试；实测 no-test 基线 61.2% → 同轨迹测试 57.3%（**更差**）→ 异源测试 65.3%；两个角色分别后训练后达 72.6%，比无测试基线 +11.4 pp） | 2026-09-08 | **本稿的「现象」与「对策」均已被占位**：不得再声称「补丁与测试同源会互相印证」是新发现，也不得声称「冻结测试 + 独立裁决」是本稿的贡献。 |
| **「分解」这一方法动作**（把结果拆到可归因的分段/分母上） | `kim2026coherencecollapse`（2603.24631：TRAJEVAL 把轨迹**分解**为 search/read/edit 三段；16,758 轨迹 / 3 架构 / 7 模型；**60–69% 的失败是「到达并编辑了正确函数却仍产出错误补丁」**；5 例轨迹中途产出与金标准逐位相同的补丁、随后被自己破坏） | 2026-03-25 | **本稿的「分解」不再是独有动作**，且其**同类现象已被大规模测量**（60–69%）。本稿剩下的只能是**口径层面的分解**（条件/边际/声明率），不是**轨迹层面**的分解。 |
| **「审计评测器本身」是正当要求** | `bhat2026benchmarkingbenchmarks`（2607.02577：四个工具调用基准族的效度与可复算性审计；496 个人工核验任务上 **92 处分歧 = 18.5% 错配率**；同一设置重复 23 次得分 57.9%–76.8%，**18.9 pp 摆幅足以改写榜单结论**；结论要求「评测器自身可复算、可审计」） | 2026-06-30 | 「审计装置」在基准评测域已是**常规要求**，不是本稿的增量主张。本稿只能说**自家装置被审计并公开了上限**。 |

### 11.2 三篇**相关/同向**工作（不占位，但改变论文的定位）

- `lewis2026sameharness`（2608.26218）与 `sghaier2026harnesshierarchy`（2607.03691）：固定模型只变 harness
  ⇒ 结果变（同一 harness 的两种配置把 Verified 的 F2PF 从 28% 抬到 49%、完整解从 43 抬到 72；
  35 个连续 release 的纵向受控研究）。⇒ 与本稿 RQ1 同向**且更直接**（它们连「harness 应当与
  模型一起被当作被测求解器」都写成了结论）。本稿的 RQ1 由此**从「独有观察」降级为「同向复现」**。
- `gloaguen2026whentoact`（2605.07769）：**显式指令能改变行为，但引入新的失效模式**（先复现再打补丁
  的指令部分缓解了乱改代码，却让「部分已修复」的 issue 被错误地弃权）。⇒ 与本稿 RQ1 的
  「指令产物携带效应」同族，并给出**副作用**这一侧写。
- `yu2026deceptiveresumes`（2609.15516，**cs.CR**）：第三方写的 worker 描述被规划器信任 ⇒
  **注册期注入通道**；32,000 份描述里至少 23.35% 含越界内容；单条被操纵的描述把任务成功率
  从 84.31% 压到 37.25%，或把 token/执行时间抬高 111% 以上。⇒ 「指令产物是一等因果/攻击对象」
  在**跨分类**处已被量化。
- `dan2026swepro_v2`（2610.24206）：731 个任务里**修掉或废掉 480 个**（23 名工程师 404 小时、
  逐条盲重实现核验）；并把「限制网络访问 + 干净容器重判」写进评测协议。⇒ 「裁决必须机械且独立」
  已是基准维护方的**实际做法**，不是本稿的呼呼。

### 11.3 累计让渡之后，本稿**剩下的增量**（逐条可核）

1. **口径矩阵**：false-fix 在**条件口径**与**边际口径**下并列报告，并单独报告**声明率**
   （协议对声明率的扰动）——本轮与前三轮共 18 篇候选中，**未见任何一篇报告「声明率」这个量**。
2. **预注册 + 零 LLM 可复算**：每个数字都能从归档工件重算，复算不需要新的模型调用。
3. **同一套判据同时审计系统与装置，并公开装置自身的上限**（可执行预言机 16/20 任务成功但
   **不**提升检出）。
4. **功能级、共享分母**的裁决（不是风格级、不是轨迹级），且落在**测试生成**流水线而非修复流水线。

### 11.4 覆盖缺口的**诊断更正**（比上一轮更准确）

- 上一轮登记的是「DBLP / ACM DL / IEEE 官方页**被代理拦截**」。CZ 轮实测更正：**不是代理拦截**，
  而是 **DBLP 自己的反机器人挑战**（Anubis）——`https://dblp.org/search/publ/api`、
  `https://dblp.uni-trier.de/…`、`https://dblp.dagstuhl.de/…` 三个入口**一律返回 HTTP 202 +
  「Making sure you're not a bot!」的 HTML**（不是 JSON），`dblp2.uni-trier.de` 返回 401。
  ⇒ 这是 DBLP 公开 API 的**常驻属性**，不是本环境的临时故障 ⇒ **非 arXiv 渠道的覆盖缺口无法
  通过「再试一次」关闭**，只能如实披露（ACM DL / IEEE Xplore 同样未在本环境验证）。
- 分类集合的覆盖缺口**已在本轮闭合**：cs.SE ∪ cs.CR ∪ cs.CV（CY 轮发现的「只扫 cs.SE」已补）。

## 12. DA 轮（2026-10-26）Web 检索通道的补扫：两篇 F4 族同向新命中（**非直接占位**）与检索通道的缺口登记

> **核验方式**：arXiv 官方摘要页（`arxiv.org/abs/<id>`）逐字取回；本节引文均先在摘要页
> 核对后写入。检索通道 = 通用 Web 搜索（CZ 轮的 arXiv API 论断族查询之外的第二通道）。
>
> **为什么 CZ 轮的 12 条论断族查询没有命中这两篇**（诚实诊断，不是辩解）：
> ① `2610.28678` 主分类 cs.SE、提交日 2026-10-19 落在 CZ 时间窗内，其摘要含 "harness" 与
> "evaluation"，理论上是 F4 查询（`all:"harness" AND (all:"agent" OR all:"LLM") AND
> all:"evaluation"`）的可达集——最可能的漏因是**分页深度**（F4 结果集大、CZ 只对 F3/F4/F8
> 翻到深度 300，该篇排序可能落在 300 之后）；② `2610.13548` 主分类 cs.CV，但其措辞
> （VLMEvalKit / permutation null / audit layer）与 12 条 SE 论断族查询**没有交叠**——
> **按论断族检索的查询集天然带 SE 措辞偏置**，分类集合扩到 cs.CV 不等于措辞覆盖扩到 cs.CV。
> ⇒ 教训登记：**通道单一（只用 arXiv API + 论断族查询）就是单点**；DA 轮起补通用 Web
> 搜索通道，且「分类集合已覆盖」不等于「措辞空间已覆盖」。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `seefried2026quantumleap` | 15 模型 / 530 任务 / 96 任务 / 98.7% / 63.8% / 17 任务 / 0%→94.1% | "We evaluate 15 hosted frontier, open-weight, quantum-specialized, and retrieval-augmented models on five quantum code-generation suites (530 tasks)"；"plus 10 models on our new QuantumBenchEval (QBE) benchmark (96 tasks across six topics)"；"QiskitHumanEval-Standard approaches saturation (98.7% pass@1), while its Hard variant retains headroom (63.8%)"；"We identify 17 QuanBench-117 tasks with shared failures linked to benchmark-owned imports."；"removing checks for unspecified quantities raises GPT-6 Astra's QBE pass@1 from 0% to 94.1%"；"None of the five top-two comparisons across primary suites remains significant"；"leaderboard scores alone do not adequately characterize progress" | arXiv:2610.28678v1（2026-10-19；Seefried / Ghosh / Afrose / Stapleton / Layton Ortega / Humble / Ghosal；cs.SE + quant-ph；无出版商 DOI） |
| `degtiarev2026vlmaudit` | 6 探测器 / 17.0% / +3.2 pp / p=0.001 / 20.2% / 134 题 | "add an audit layer to VLMEvalKit: six detectors that run as post-processing over saved outputs"；"An item-matched permutation null accounts for 17.0%, leaving a +3.2 pp excess (corrected permutation p = 0.001)"；"zero aggregate accuracy gain from the image on 20.2% of its questions"；"A second detector flags 134 questions on which every model that answered in parseable form picked the same non-gold option" | arXiv:2610.13548v1（2026-10-09；Degtiarev / Gromova / Katkov / Mikhailin / Mukhamedshina / Nasybullin / Shaikhutdinova / Tuzov；cs.CV；无出版商 DOI） |

### 12.1 对本稿 novelty 的影响（同向加强，不是占位）

两篇都落在 **F4（测量装置审计）** 族，且都与 `bhat2026benchmarkingbenchmarks`（§11.1 第三行）
同向——「审计评测器本身」在 2026-10 又添两个域的实例：

- `seefried2026quantumleap` 把「评测器设计决定分数」推到极端：**移除对未声明量的检查把
  GPT-6 Astra 的 QBE pass@1 从 0% 抬到 94.1%，而模型输出一个字节没变**；并报告
  bootstrap CI + 多重比较校正，随文发布 harness 与逐样本结果。⇒ 与本稿 F4 主张同向：
  「装置与模型必须一起被审计」。它**不占位**本稿剩余增量（口径矩阵 / 声明率 / 预注册零 LLM
  复算链 / 公开装置自身上限），但**多重比较校正与本稿共享**（本稿 BH-FDR 节），登记为
  同向证据。
- `degtiarev2026vlmaudit` 的审计层是**对已保存评测产物的后处理**（不重跑模型）+ 排列零假设
  基线 + 「以超出基线的 excess 报告 headline」——方法上与本稿「零 LLM 复算链」同族
  （从存量工件重算、不产生新模型调用），但落在 VLM 域、且其判据（图像信息量）与
  本稿判据（功能级裁决）不同。**不占位**，登记为跨域同向。

### 12.2 本轮检索面读数（诚实汇报）

- 检索 4 组查询（F1 误导测试 / F2 编排负结果 / F4 基准效度 / F3 规格锚定），命中并一手
  核验 **2 篇新增**（本节）；另核验 1 篇（`2610.11835`）**已在 §8 登记**（CU 轮召回网曾
  抓住它，DA 轮初判「未登记」有误、已更正——**先查登记面再声明新增**这条纪律本轮自己
  踩了一次）。F2 / F3 两组查询未产出未登记的同题命中（F2 首屏多为已登记的
  `tao2026execcritic` / `kim2026coherencecollapse` 邻域；F3 首屏为 2026-01 之前的
  spec-driven 工作）。
- **发布新鲜度结论**：截至 2026-10-26，检索面内**无新的直接占位**；§11.3 所列四条剩余
  增量（口径矩阵 / 预注册零 LLM 复算 / 装置上限自审 / 功能级共享分母裁决）经本轮
  补扫后维持成立。

## 13. DB 轮（2026-10-26）**分类集合再次漏扫**：五篇新命中，其中**两篇直接占位本稿核心叙事**——DA 轮「无新占位」的结论被推翻

> **核验方式**：arXiv 官方 Atom API（`export.arxiv.org/api/query`，取 `summary` /
> `author/name` / `category` 字段逐字核对）。检索通道 = **arXiv API 的分类过滤 + 排序**
> （DA 轮的 Web 搜索通道之外的第三通道），与 CZ/DA 轮的「论断族措辞查询」**结构上不同**。
>
> **本轮的方法学教训（比结论更重要）**：CZ 轮把分类集合扩到 cs.SE ∪ cs.CR ∪ cs.CV，
> DA 轮据此宣称「分类集合的覆盖缺口已闭合」。**本轮实测证明那个结论是错的**：本轮
> 只用**分类过滤**（不写任何论断族措辞）就召回了 19 篇未登记工作，其中**主分类
> cs.CL / cs.AI / stat.ME 的有 4 篇**。⇒ **「分类集合已覆盖」与「措辞空间已覆盖」是
> 两个独立的缺口**，前者闭合不等于后者闭合；而**扩分类集合时若同时绑定 SE 措辞，
> 新增的分类并不会带来新召回**——DA 轮自己的诊断已经说了后半句（「按论断族检索的
> 查询集天然带 SE 措辞偏置」），却没意识到**分类过滤通道**能绕开这个偏置。
>
> **⇒ 登记一条可执行的检索纪律**：每轮检索必须至少包含**一条不带论断族措辞的
> 分类过滤通道**（`cat:` 过滤 + 按提交日倒序翻页），否则「扩分类」只是名义上的。

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `ding2026harnessdelta` | 11 执行模型 / 3 框架 / 21 显著设置 / 54% / 14% / 14 设置 >50% | "we introduce Harness-Delta Attribution (HDA), an evaluation protocol that dissects an evolution gain into artifact-driven overfitting, gains explained by test-time scaling, and the remainder, which gives an upper bound on residual generalizable improvement"；"We apply HDA to 11 executor models and three harness-evolution frameworks across math, coding, creativity, and agentic tasks"；"In 21 of these settings that show statistically significant search-set gains, we find that a large share of the improvement is explained by overfitting or test-time scaling"；"overfitting and test-time scaling account for 54% and 14% of the gain on average; their combined share exceeds 50% in 14 settings"；"search-set gains often fail to transfer to held-out tasks"；"validation-based signals are insufficient to prevent overfitting" | arXiv:2610.22466v1（2026-10-15；Ding / Lu / Yu / Li / Jin / Liu / Shi / Durrett；**cs.AI**；无出版商 DOI） |
| `cheng2026skillsutility` | 87 任务 / 9 配置 / 37,596 Skills / 36.78% / +4.35–5.80 pp / 17 条实践 | "We conduct an empirical study on 87 SkillsBench tasks, defining downstream utility as the pass-rate difference from No-Skill on the same tasks under the same model--harness configuration"；"We compare the same Skills across nine configurations"；"We retrieve marketplace candidates from a curated corpus of 37,596 Skills"；"The same Skills help some configurations and hurt others on 36.78\% of tasks, with trajectories showing that recommended procedures can become an execution burden"；"reranking by support for required operations raises first-choice pass rates by 4.35--5.80 percentage points"；"We derive 17 authoring practices" | arXiv:2610.08875v1（2026-10-06 / v2 2026-10-08；Cheng / Zhao / Liu / Huang / Xing / Ren；**cs.AI + cs.LG**；无出版商 DOI） |
| `han2026skilluse` | 79 skills / 177 任务 / 9 域 / 8 模型 / 2 harness / SU 0.613 | "Skill-Use pairs 79 real skills with 177 executable tasks across nine domains, each grounded in real files, run in an isolated Docker sandbox, and scored by a trajectory-based rubric"；"Evaluating eight LLMs under two agent harnesses, we find that reliable skill use remains out of reach, as the strongest configuration reaches an SU of only 0.613"；"Triggering and procedural compliance fail as independent bottlenecks, and both scores and model rankings shift with the harness, so skill use behaves as a capability conditioned on the harness rather than a fixed property of the model" | arXiv:2608.04828v1（2026-08-05；Han / Xu / Liao / Wang / Jiang / Di / Lu / Hu / Xiao；**cs.CL**；无出版商 DOI） |
| `wang2026harnessreeval` | Terminal-Bench 2.1 / ARC-AGI-3 +80% / EdgeBench +11% | "Following prior work, we experiment on Terminal-Bench 2.1 and find that automatic harness evolution fails to outperform simple test-time scaling methods both with and without test cases, and exhibits limited generalization"；"prior work does not compare these approaches with simple task-level search baselines under matched feedback and inference budgets"；"prior work searches for harness configurations using verification signals (e.g., unit test cases) drawn from the same benchmarks on which it reports the final performance of the evolved harnesses, violating the standard separation between training and test data"；"automatic harness evolution fails to outperform simple test-time scaling methods both with and without test cases, and exhibits limited generalization"；"task-specific harness evolution improves over the search baseline by 80% on ARC-AGI-3 and by 11% on EdgeBench games under matched budgets" | arXiv:2607.12227v4（v1 2026-07-14 / v2 2026-08-27 / v3 2026-10-01 / v4 2026-10-05；Wang / Zhu / Hu / Yuan / Chen / Senthil / Hajishirzi / Tsvetkov / Smith / Dasigi / Xiao；**cs.AI**；无出版商 DOI） |
| `park2026progressmirage` | 54 周期 / 56% / 19% / 44% / 38% / 110.0 vs 113.0 | "Across 54 cycles a frontier agent claimed improvement every time, yet 56 percent had a measured delta of zero or below"；"the self-verdict gate degenerated into accept-all, eroding the best deployed state it had reached by 19 percent"；"the strongest in-band judge ... accepted cycles of which 44 percent were real-world regressions and rejected 38 percent of real improvements；the preregistered adversarial hypothesis that a strong judge closes the gap was rejected"；"A sign-only variant returning only the acceptance verdict kept real-world output similar to full feedback (110.0 versus 113.0)" | arXiv:2607.25152v1（2026-07-27 / v2 2026-09-29；Park / Choi；**cs.AI**；无出版商 DOI） |

### 13.1 占位判定：**两篇直接占位**（必须正面处理，不可回避）

**（一）`ding2026harnessdelta`（HDA）——占位本稿 RQ1 的「分解」框架。**

HDA 把 harness 演化的增益**分解为三块**：artifact 驱动的过拟合 / test-time scaling 解释的
部分 / 残余的可泛化改进上限。在 21 个显著设置里，过拟合与 test-time scaling 平均
解释 **54%** 与 **14%** 的增益，合计过半者有 **14** 个设置。

这与本稿 RQ1 的核心动作**同构**：本稿把「指令工件的文本」与「它授权的再生成预算」
分开固定，再问增益落在哪一边。⇒ **「把协议文本与计算预算分开归因」这个分解动作，
在 2026-10 已被明确提出并规模化应用**。本稿**不得**再把它写成自己的方法创新。

但 HDA **不占位**本稿剩下的一块：HDA 的三块是**增益的归因**（overfitting / scaling /
残余），本稿的三块是**声明口径的矩阵**（条件口径 / 边际口径 / **声明率**）。§11.3 第 1 条
的「**声明率**」这个量，在 HDA 的分解里**所核摘要与正文未见对应物**——HDA 分解的是*性能增益*，
本稿分解的是*成功声明的分母*。⇒ 本稿可保留的增量进一步收窄为：
「**在固定成功定义下，声明率本身是一个被协议扰动的量**」+「功能级共享分母的功能级裁决」
+「预注册零 LLM 复算链」+「公开装置自身上限」。

**（二）`cheng2026skillsutility`——占位本稿「工件的效果依赖配置」这一观察。**

该文把「下游效用」定义为**同一 model–harness 配置下、与 No-Skill 的通过率差**，跨
**9 种配置**比同一批 Skill，得到：**同一批 Skill 在 36.78% 的任务上帮了某些配置、
伤了另一些配置**，轨迹显示「推荐的过程本身会变成执行负担」。

这与本稿「工件的效果随配置漂移」的观察**直接重叠**，且**方法上更细**（9 配置 × 同
一批工件 × 同任务）。⇒ 本稿**不得**再把「工件效果依赖配置」写成自己的发现。

但该文**不占位**本稿剩下的一块：它测量的是**通过率差（任务级）**，本稿的裁决是
**功能级、共享分母**的 fail-to-pass 判定；它研究的是 **Skill 的内容与组织**，本稿研究
的是**一个 196 字符检测优先段**在**测试生成**中的协议文本 vs 再生成预算分离。就**所核
摘要与正文表述**而言，未见预注册、未见零 LLM 复算包，也未见对自身装置（评分器）上限的报告。

### 13.2 三篇同向证据（不占位，但改变定位）

- `han2026skilluse`：**分数与模型排名随 harness 变动**，「skill use 是被 harness 条件化
  的能力，而不是模型的固定属性」。⇒ 与本稿核心命题（价值在协议与测量，不在编排）
  **同向**，且是**跨分类实例**（cs.CL）。它**不占位**本稿增量（测的是 skill 使用三
  切面，不是 false-fix 口径；判据是轨迹 rubric，不是功能级 fail-to-pass）。
- `wang2026harnessreeval`：**matched-budget 基线 + held-out 评估**是区分「真实 harness
  改进」与「benchmark 特异搜索」的标准手段；且给出与本稿 RQ2 同型的阴性（自动 harness
  演化不敌简单 test-time scaling）。⇒ 本稿 RQ2 的「编排不加值」**不再孤立**。
- `park2026progressmirage`：**预注册的对抗性假设被拒绝**（加强型 judge 不能闭合
  自评偏差）；且「收益来自 gate 的接地而非反馈内容」（110.0 vs 113.0）。⇒ 与本稿
  「协议/装置决定读数」同向，且其**预注册+拒绝假设**的做法与本稿纪律同族。

### 13.3 本轮检索面读数（诚实汇报）

- **通道**：arXiv API **分类过滤**（cs.SE / cs.CR / cs.CV / **cs.AI / cs.CL** /
  stat.ME），按提交日倒序翻页，12 条论断族 × 分类过滤共命中数百条次，去重后与
  **已登记 67 篇 arXiv ID**（登记册 ∪ refs.bib ∪ 快照三处并集）求差。
- **命中**：F13（skill×harness×agent）未登记 200 篇、F14（test-time×harness）91 篇、
  F10（oracle×test generation）未登记 40 篇 —— 其中**经摘要判读为同题或同族**的
  **5 篇**登记入本节；其余为跨域噪声（具身智能、机器人、医疗、法律、HCI），如实登记
  为「查过但不用」。
- **失败通道（不静默）**：F15（prompt×artifact×instruction×agent）首轮 API 调用
  `curl` 退出码 56（连接重置）⇒ 该族本轮**无读数**，不按「零命中」记。
- **发布新鲜度结论（推翻 DA 轮）**：DA 轮「检索面内无新的直接占位」**不成立**——
  `ding2026harnessdelta` 与 `cheng2026skillsutility` 是新的直接占位者。§11.3 的四条
  剩余增量经本轮后**收窄为两条半**：①**声明率作为被协议扰动的量**（口径矩阵里的
  第三个量，HDA / Skills-Utility 均无对应物）；②**功能级共享分母的裁决**（落在测试
  生成流水线）+ 预注册零 LLM 复算链 + 公开装置自身上限。

## 14. EZ 轮（2026-10-27）三篇：评测器不足与「验证者继承生成者盲点」——散文登记，**未引用**

**登记形态说明（为什么没有表格行）**：登记册的每行都与 `docs/study/PAPER_CITATION_KEYS.md` 双向绑定
（`tests/test_external_readings_citation_chain.py` 判据 1：登记行必须在快照里，否则「只写不读」）。
本节三篇**尚未进入 `refs.bib`**（正文未引用），因此按散文登记、不建行——不给读者链塞三根只写不读的墓碑。
若后续在正文引用，再按行格式重登记并重算快照。

**检索面（诚实汇报）**：2026-10-27 用两条检索式（`LLM generated tests encode buggy behavior false fix oracle mismatch 2026`、
`arXiv cs.SE test generation LLM bug reproduction benchmark October 2026`，时间窗 d7 / m1）在 Web 通道补扫，命中 3 篇与本稿
构念相邻的工作；三篇均按**官方摘要页**逐字核验（`export.arxiv.org/abs/<id>`，2026-10-27），不采用二手转述的读数
（这正是 WC 轮记过的失败形态：转述页会把「约」和单位抹平）。

1. **TestJack** — `arXiv:2610.10619v1`（Yao, Wang, Sen, Chen, Ray, Song；2026-10-07）。官方摘要原句：
   "we find that about 34.4% of the model trials currently judged correct violate the task requirements,
   lowering the overall resolution rate from 50.6% to 33.2%"。量的是**评测器不足**（固定单测覆盖不到 prompt 的全部要求），
   因果链是「测试太弱」；它不区分「弱测试」与「错误预言」，因此**不能**与 false-fix 率并列（同 §6 对 9.21% / 59.29% 的口径纪律）。
2. **Verification Trap** — `arXiv:2610.05170v1`（He, Wang, Meng, Gao, Li；2026-10-04，EMNLP 2026）。官方摘要原句：
   "a lightweight gold-free predictor using verifier-visible features reaches 0.846 AUROC"。与本稿最接近：验证者（测试）
   继承生成者的错误前提，选择器因此挑中 hidden-test-wrong 的候选；其证据是选择失败与**可预测性**，不是 false-fix 率——
   同一现象的不同测量面。
3. **SCALF** — `arXiv:2610.27694v1`（Gan, Zhang, Liang, Li, Wang, Zhang, Dong；2026-10-20）。官方摘要原句：
   "SCALF outperforms strong prompting and post-training baselines by up to 2.97, 5.26, and 3.53 percentage points in joint
   success rate, output correctness rate, and bug-triggering rate"。方法侧（RL 训练 bug-exposing 测试），不提供测量口径；
   仅作 `bug_triggering_rate` 这一指标名的出处登记。

**让渡口径不变**：本稿增量仍为三块（①false-fix 口径分解〔条件 + 边际并列〕②声明率本身被协议扰动 ③测量效度 × 声明率联立）。
本节三篇不改变该结论，只补两处「相邻构念不得互相冒充」的边界。
