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
| `kim2026scaling` | 180 配置；39--70% / 80.8% / 17.2x / 4.4x / 45% / 0.524 | "we perform a controlled evaluation spanning 180 configurations"；"for sequential reasoning tasks, every multi-agent variants degraded performance by 39-70%"；"Centralized coordination improves performance by 80.8% on parallelizable tasks"；"independent agents amplify errors 17.2x, while centralized coordination contains this to 4.4x"；"coordination yields diminishing or negative returns once single-agent baselines exceed ~45%"；"achieves cross-validated R^2=0.524" | arXiv:2512.08296（v1 2025-12-09，v3 2026-04-08），Google Research / DeepMind / MIT，19 位作者，DOI 10.48550/arXiv.2512.08296 |
| `jwalapuram2026illusion` | 10x | "automatic MAS consistently underperform CoT-SC despite being up to 10x more expensive"；"these comparisons rarely control for inference budgets such as number of LLM calls, total cost, retries, or sampled paths" | arXiv:2606.13003（2026-06-11），Salesforce Research / HKUST(GZ) / UBC / NTU，DOI 10.48550/arXiv.2606.13003 |
| `shin2026rag` | 6.5% / 28 / 24 / 10 | "While RAG does not enhance correctness, RAG improves line coverage by 6.5% on average"；"28 bugs were detected, 24 unique bugs were reported to developers, ten were confirmed" | ICSE 2026（48th ICSE）Research Track，pp. 767--779，DOI 10.1145/3744916.3773163，arXiv:2409.12682 |

**版本冲突（必须留存）**：`kim2026scaling` 的**配置数与基准数在二手来源之间不一致**——
论文当前版本（arXiv v3 摘要）写的是 **180 configurations / four benchmarks**
（Finance-Agent、BrowseComp-Plus、PlanCraft、Workbench），而多篇中文/英文二手博客写
「260 配置 / 6 个基准」。本登记册与正文一律采用 **arXiv 摘要的一手读数**；引用该文时
不要采信博客数字。这是本项目「二手来源只作线索、读数必须回原文」的又一例。

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
| `hamidi2026criteria` | ~99% | "traditional test criteria fail to trigger and detect almost all faults examined (approximately miss approximately 99% of them)" | arXiv:2609.09315 |
| `hamidi2026criteria` | 6,000+ | "We collect 6,000+ faulty program instances" | 同上 |
| `liu2026testexplora` | 16.06 | "state-of-the-art models achieve a maximum Fail-to-Pass (F2P) rate of only 16.06%" | ICML 2026, PMLR v306 |
| `liu2026testexplora` | 2,389 / 482 | "2,389 tasks across 482 repositories" | 同上 |

## 3. 规格锚点与「先测试后编码」（RQ4 的外部对照）

| 键 | 读数 | 原文表述 | 出处 |
|---|---|---|---|
| `tufano2026specops` | 9.8 / 53.4 / 63.2 | "a 9.8 percentage points (p = 0.0352) improvement in bug detection rate" over a 53.4% baseline, reaching 63.2% | SpecOps '26（DOI 10.1145/3842652.3843195；arXiv:2608.17177） |
| `tufano2026specops` | 2.5 | "a 2.5 percentage point (p = 0.0034) improvement in branch coverage" | 同上 |
| `tufano2026specops` | 0.0352 / 0.0034 | "a 9.8 percentage points (p = 0.0352) improvement in bug detection rate"；"a 2.5 percentage point (p = 0.0034) improvement in branch coverage" | 同上 |
| `tufano2026specops` | 90 | "a dataset of 90 historical production bugs from Google's Issue Tracking System" | 同上 |
| `konstantinou2026coding` | 25 / 14 | "a fault detection rate of 25% for a test-driven workflow versus approximately 14% when tests follow code generation" | arXiv:2607.05139 |
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
