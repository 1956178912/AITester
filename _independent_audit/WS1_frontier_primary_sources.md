# WS1 独立前沿基线重建（仅一手来源）

- **交付物**：`_independent_audit/WS1_frontier_primary_sources.md`
- **作者**：frontier-sourcer（独立检索员；不参与项目实现）
- **任务**：task-1（WS1 独立前沿基线重建）
- **检索完成时间戳**：2026-10-11T13:54+08:00（Asia/Shanghai）
- **检索窗口**：2026-10-11 13:50–13:55（单次会话，未跨日）

---

## §0 检索方法与时间戳、知识时效声明

### §0.1 我的知识时效声明（**重要**）

1. **我的内部参数化知识存在明确截止期，且对 2025-06 之后、尤其是 2026 年的信息不可靠。**
   本文件**没有任何一条数据点来自记忆**。凡本文件出现的指标值，均在下方给出我在本次会话中**实际访问过**的 URL；未实际访问到承载该数值的一手页面者，一律进入 §8 D 级清单，不写数值。
2. **2025–2026 年文献的存在性、venue、DOI 与数值，一律以本次检索结果为准。** 我注意到若干条目（如 ICST 2026、ISSTA 2026、ICLR 2026、TOSEM/IEEE TSE 2026 卷期）在我记忆中不存在，但经检索确认**确实存在**；反之也存在项目声称而检索无法支撑的条目。两个方向都不得以记忆裁决。
3. **本次检索存在两个已知的结构性盲区**，直接影响结论强度，特此前置声明：
   - **IEEE Xplore 在本会话中被反爬拦截**（`ieeexplore.ieee.org/document/11655121` 返回 HTTP 202 空体、`dl.acm.org` PDF 返回 HTTP 403 + Cloudflare 挑战页、`openai.com/index/*` 返回 HTTP 403）。凡以这些域为唯一载体的数值，我只能标注"未能核实"，**不得**用二手转述补全。
   - **Semantic Scholar API 出现持续性 HTTP 429 限流**。仅在限流间隙成功取回 1 条（TestAgent）。
4. **取证工具链**：`web_fetch`（Crossref REST API、arXiv abs/HTML、会议官方 program 页、机构官方出版物页）、`web_search`（仅用于**发现线索**，其返回的摘要文本一律不直接作为数值来源，除非我随后 fetch 到承载页面）。

### §0.2 证据等级定义（本文件采用，较任务书略作细化）

| 等级 | 定义 | 本次典型载体 |
|---|---|---|
| **A** | 一手、可验证、可追溯版本：DOI 注册机构（Crossref）记录 / arXiv abs 或 HTML 全文 / 会议官方 program 页 / 官方 proceedings / 机构官方出版物页 | `api.crossref.org`、`arxiv.org`、`conf.researchr.org`、`proceedings.iclr.cc`、`proceedings.neurips.cc`、`research.ibm.com` |
| **B** | 一手但**不可完全验证**：数值仅有官方摘要级文本（未取得全文表格）；或纸张/元数据层一手、正文层缺失 | 出版社摘要（Crossref abstract 字段）、Semantic Scholar 转载的出版社摘要 |
| **C** | 二手转述：博客、新闻、综述、索引站点、聚合器（含搜索引擎返回的摘要片段） | 搜索结果片段、非官方镜像 |
| **D** | 不可验证：本次检索**无法定位**承载该数值的一手来源；或唯一载体被拦截 | — |

### §0.3 与项目既有材料的关系（纪律声明）

- 本文件**独立于**并**不采信** `review_2026/`、`audit_2026/`、`REVIEW_2026_FRONTIER.md`、`FINAL_REVIEW_2026-10-11.md`、`EXTERNAL_REVIEW_2026-10-11.md`、`OPTIMIZATION_PLAN_v2.md`、`.private/` 中的任何前沿数据。这些文件在本次工作中**是待验证对象**。
- 我**仅**从项目 `README.md`（第 1–60 行头部）与 `BASELINE.yaml`（第 26–70 行）中提取**待核实的引用清单与项目所述数值**，作为"项目所述值"一栏的输入；提取命令为：
  ```
  grep -nE "arXiv|DOI|doi\.org|IEEE|TOSEM|ICSE|FSE|ISSTA|ICLR|ICST|NeurIPS" README.md BASELINE.yaml
  ```
  该命令只用于**确定需要核实什么**，所有结论均来自我自己的检索。
- **本文件不得被反向引用为项目自证材料**；它是一份外部证据审计。

### §0.4 覆盖度自评（诚实边界）

| 区块 | 计划覆盖 | 实际覆盖 | 说明 |
|---|---|---|---|
| §1 项目引用核实表 | README 头部 + BASELINE.yaml 全部外部引用 | **13/13 条均已处理**（含 2 条为项目内部自相冲突记录） | 其中 8 条拿到 A 级结论，3 条部分（存在性 A、数值 D/B），2 条仅 B |
| §2 测试生成前沿 | 8–10 系统 | 9 系统（含 4 个被 replication 覆盖者） | 有一手数值 |
| §3 多智能体 | 6–8 系统 | 6 系统 | 有一手数值 |
| §4 自愈/运行时反思 | 4–6 系统 | 4 条 + 1 条指标类论文 | **本方向一手数值最稀薄**，多数论文摘要不含具体延迟/MTTR 数值 |
| §5 逻辑/形式化 | 5 类 | 2 条 A/B + 3 类 D | 覆盖率最低，见 §8 |
| §6 评估方法论 | 含污染争议 | 5 条 | 质量较好 |

---

## §1 项目引用核实表（逐条 · 核心产出）

> 说明：`项目所述值` 一栏为项目 README 头部 / BASELINE.yaml 的原文摘要（用于对比，不代表我采信）。`我核实值` 一栏仅在我**实际访问过承载页面**时填写。
> **本条最重要的三个结论**：**① 项目所列 8 个 DOI/arXiv 标识符全部真实存在且作者/venue 归属正确——零伪造、零张冠李戴；② 有 1 处关键数值被误述（Konstantinou 论文的 LLM 请求数）；③ 项目最重的那条"不利证据"（IEEE 11655121）的四个核心数值在公开网络无法独立核实。**

### §1.1 总表

| # | 项目所述引用 | 项目所述值（原文口径） | 独立核实结论（三态） | 我核实值（一手） | 一手 URL | 等级 |
|---|---|---|---|---|---|---|
| R1 | CANDOR，Xu/Wang/Briand/Liu，TOSEM 2026，DOI `10.1145/3803418`；HumanEvalJava line/branch/mutation **0.991/0.970/0.980** | 多智能体在 line/branch/mutation 上达 0.991/0.970/0.980 | **属实（数值精确一致）** | 论文真实存在：*Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation*，ACM TOSEM，在线 2026-03-25，作者 Qinghua Xu / Guancheng Wang / Lionel Briand / Kui Liu。表 1 HumanEvalJava：**CANDOR Line 0.991\*、Branch 0.970、Mutation 0.980\*（2384/2443）** | Crossref: <https://api.crossref.org/works/10.1145/3803418> ·全文表 1: <https://ar5iv.labs.arxiv.org/html/2506.02943> | **A** |
| R2 | TestAgent，FSE Companion 2026，DOI `10.1145/3803437.3806428`；line **92.34%** / mutation **83.69%** | line 92.34% / mutation 83.69% | **line 属实；mutation 无法定位（D）**；另有**重大载体性质提示** | 论文存在：*TestAgent: A Multi-Agent LLM Framework for Repository-Level Unit Test Generation*，FSE Companion '26，**pages 242–246**，作者 Ye Shang / Quanjun Zhang / Zhengyu Zhan / Ke Huang / Chunrong Fang / Zhenyu Chen。**但 5 页篇幅 = Companion 短文/工具论文，不是完整研究论文；项目将它作为"有利证据"的主引用之一是载体不匹配（见 §1.3 观察 O3）。** 摘要级核实："Evaluation on **1,451 methods across six Java projects** ... TestAgent achieves a **92.34% line coverage** ... detects **154 real-world bugs with high precision (92.22%)**" | Crossref: <https://api.crossref.org/works/10.1145/3803437.3806428> ·摘要（S2 转载出版社摘要）: <https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3803437.3806428?fields=title,abstract,venue,authors,externalIds> | line **A/B**；mutation **D** |
| R3 | IEEE Xplore **11655121**，Radaideh & Corriveau，*Understanding the Effect of Agentic Iteration on LLM-Based Unit Test Generation*；one-shot Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**、one-shot GPT-4o **69.90%** vs CANDOR **45.63%**（mutation score） | 88.35/35.92/69.90/45.63 | **论文存在性属实；四个数值无法定位（D）** | 论文确实存在，标题与项目所述**逐字一致**（含副标题 *A Comparison with Human-Written Tests Using Mutation Testing*），作者 Radaideh & Corriveau。**但 IEEE Xplore 在本会话返回 HTTP 202 空体，dl.acm.org 返回 403，Semantic Scholar API 持续 429，故我未能访问任何承载这四个 mutation score 数值的页面。** | 存在性（索引命中）: <https://ieeexplore.ieee.org/document/11655121> | 存在性 **B**；数值 **D** |
| R4a | ICST 2026 复现研究（Konstantinou, Degiovanni & Papadakis），arXiv `2601.09695`；**6 个完整 Java 仓库 / 393 类 / 3,657 方法** | 6 repos / 393 classes / 3,657 methods | **属实** | arXiv:2601.09695v2（v1 2026-01-14，v2 2026-07-29），作者 Michael Konstantinou (SnT, Univ. Luxembourg) / Renzo Degiovanni (LIST) / Mike Papadakis (SnT)。表 I：6 个完整开源 Java 仓库（BC/CH/CM/ER/W/BPG），**TOTAL 393 CUT / 3,657 MUT** | <https://arxiv.org/abs/2601.09695> ·<https://arxiv.org/html/2601.09695v2> | **A** |
| R4b | 同上：Plain-LLM **49.95/35.33/33.82** 全面优于 HITS/SymPrompt/CoverUp/TestSpark | 49.95/35.33/33.82 | **属实（精确一致）** | 论文正文原句："Plain-LLM obtains, in total, **49.95%, 35.33%, and 33.82%** on line/branch/mutation coverage, while HITS obtains 42.43%, 29.49%, and 27.97%, SymPrompt 40.95%, 27.19%, and 28.40%, TestSpark 23.65%, 16.48%, and 13.88%, and CoverUP 38.85%, 25.11%, and 26.26%" | <https://arxiv.org/html/2601.09695v2> | **A** |
| R4c | 同上：**请求数不高于 CoverUp（11,718 vs 12,264）** | 11,718 vs 12,264 | 🚩 **数值被误述（b 态）** | 论文正文原句："SymPrompt ... **5,602** requests ... followed by TestSpark with **7,023** ... Plain-LLM with **11,815**, CoverUP **12,741**, and finally HITS ... **16,735** requests" → **正确值：Plain-LLM 11,815 vs CoverUp 12,741**。**定性结论（Plain-LLM 请求数低于 CoverUp）成立；两个绝对值均不符。** 差值：11,718↔11,815（−97）、12,264↔12,741（−477）。疑似引用的是 v1 稿数字（我未取得 v1 正文，故此归因标注为推测） | <https://arxiv.org/html/2601.09695v2> | **A**（对"误述"的判定） |
| R4d | 同上：venue = **ICST 2026** | ICST 2026 | **属实** | IEEE Computer Society CSDL 中存在 ICST 2026 proceedings 条目（路径 `proceedings-article/icst/2026/330800a233/...`），标题与 arXiv 一致 | <https://www.computer.org/csdl/proceedings-article/icst/2026/330800a233/2iat1rHIAUM>（页面正文为 JS 渲染，仅路径与标题可取证） | **B** |
| R5 | BOAD，**ICLR 2026**，arXiv `2512.23631`，**IBM Research** | 真，研究对象为仓库级 SWE 任务解决（定位/编辑/验证子智能体），不适用于测试生成论证 | **属实（存在性、venue、机构、研究对象四项全对）** | arXiv:2512.23631（v1 2025-12-29，v2 2026-01-01），*BOAD: Discovering Hierarchical Software Engineering Agents via Bandit Optimization*。**IBM Research 官方出版物页明确标注：ICLR 2026 / Poster / 23 Apr 2026**，作者 Iris Xu, Guangtao Zeng, Zexue He, Charles Jin, Aldo Pareja, Dan Gutfreund, Chuang Gan, Zhang-Wei Hong，脚注 "IBM-affiliated at time of publication"，代码 <https://github.com/iamxjy/BOAD-SWE-Agent>。摘要确认子任务为"localization, editing, and validation" → 项目"不适用于测试生成论证"的限定**成立** | <https://research.ibm.com/publications/boad-discovering-hierarchical-software-engineering-agents-via-bandit-optimization> ·<https://arxiv.org/abs/2512.23631> | **A** |
| R6 | MUTGEN，TSE 2026，DOI `10.1109/tse.2026.3682975`；"实测存在 100% 行覆盖仅 4% 变异得分的套件" | 100% 行覆盖 / 4% 变异得分 | **属实（DOI 与结论对）；"行覆盖"限定词为项目加注（弱化项）** | 论文存在：*Mutation-Guided Unit Test Generation With a Large Language Model*，IEEE TSE **vol. 52, no. 5, pp. 1657–1671**，2026-05；作者 Guancheng Wang, Qinghua Xu, Lionel Briand, Kui Liu。arXiv:2506.02954v8 摘要原句："**some test suites achieve 100% coverage but only 4% mutation score**" → **原文只说 "100% coverage"，未写 "line coverage"**，项目加注为"行覆盖"，属**口径强化**（非严重误述，但引用时应保留原文措辞）。另：MUTGEN 在 **204 subjects / 两个基准**上评测 | Crossref: <https://api.crossref.org/works/10.1109/tse.2026.3682975> ·摘要: <https://arxiv.org/abs/2506.02954> | **A** |
| R7a | Zhao, Zhou & Cohen，ISSTA 2026，DOI `10.1145/3832093`；定性结论"覆盖+变异在回归设定下跨模型比较有效，被测代码可能有缺陷时不可靠" | 见左 | **属实（venue、作者、定性结论全对）；且升级为 Distinguished Paper** | 论文存在：*Do Coverage and Mutation Scores of LLM-Generated Test Suites Correlate with Their Effectiveness? (Replicability Study)*，PACMSE vol. 3, ISSTA issue, pp. 30–53，2026-10-01；作者 Junda Zhao, Shurui Zhou, Eldan Cohen（Univ. of Toronto）。**ISSTA 2026 官方 program 页标注 "Distinguished Paper"**，报告时间 Fri 9 Oct 2026 13:30–13:48。摘要定性："in regression-style settings where the code provided to the LLM can reasonably be assumed bug-free, these metrics can provide meaningful signals when comparing across models; in another common scenario where the code-under-test may already be buggy ..., they no longer serve as reliable indicators" → **与项目所述一致** | Crossref: <https://api.crossref.org/works/10.1145/3832093> ·官方 program: <https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/2/> | **A** |
| R7b | 同上：**branch vs raw mutation r=0.780 @k=10，控制规模后** | r=0.780 @k=10 | **数值无法定位（D）；且"控制规模后"的**表述方向与原文有张力**** | 我取得的摘要与 Crossref 记录中**均无 r=0.780 这一数值**。另需注意：论文摘要原句为 "We also find **little evidence that test suite size is a dominant confounder** for correlations among coverage, mutation, and real-bug detection for LLM-generated tests" —— 即论文结论是**规模并非主导混淆项**，而非"控制规模后相关性才成立"。项目括注"控制规模后"若意在表达"相关性在控制规模后依然成立"，尚可；若被读作"不控制规模则相关性不成立"，则**与论文结论相反**。建议项目改写。全文数值载体（复现包）：<https://github.com/drixs2050/Cov_mut_bug_detect_correlation>（Zenodo DOI 10.5281/zenodo.21437945，见该文参考文献 [61]；我本次未逐一核验包内数字） | 摘要: <https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/2/> ·复现包（未核验数值）: <https://github.com/drixs2050/Cov_mut_bug_detect_correlation> | 数值 **D** |
| R8 | ULT（UnLeakedTestbench），TOSEM 2026，DOI `10.1145/3805043`；**45.10% stmt / 40.21% mutation**；且"是基准论文，不主张相关性结论" | 45.10% stmt / 40.21% mutation | **属实（数值精确一致）**；"不主张相关性结论"**需限定** | 论文存在：*Benchmarking LLMs for Unit Test Generation from Real-World Functions*，ACM TOSEM，在线 2026-03-28；作者 Dong Huang, Jie M. Zhang, Mark Harman, Qianru Zhang, Mingzhe Du, See-Kiong Ng。摘要原句："LLMs only achieve **41.32%, 45.10%, 30.22%, and 40.21%** for **accuracy, statement coverage, branch coverage, and mutation score**" → **45.10% = statement coverage ✔、40.21% = mutation score ✔**，项目映射正确。**限定提示**：ULT 确实**不主张** coverage↔mutation↔bug-detection 相关性，但它**主张另一条相关性**——"correlation coefficient between the coding ability and test generation performance (Pass@1) on ULT is **0.79 (p = 0.002)**"，且 ULT 构建动机第一条就是 **data contamination**。故"不主张相关性结论"应改为"不主张覆盖-变异-缺陷检出相关性结论"。数据规模：**3,909** 个 function-level 任务；代码 <https://github.com/huangd1999/UnLeakedTestBench> | Crossref: <https://api.crossref.org/works/10.1145/3805043> | **A** |
| R9 | CoverUp，**FSE'25**，**90% line+branch** | 90% line+branch | **属实但条件被省略（b′ 态：数值真、口径不全）** | 论文存在：*CoverUp: Effective High Coverage Test Generation for Python*，FSE 2025 Research Papers（Trondheim, 2025-06-23 10:30，Cosmos Hall），作者 Juan Altmayer Pizzorno, Emery D. Berger (UMass Amherst)，**DOI 10.1145/3729398**。官方 program 摘要给出**两个不同数字、两个不同基线**：(i) "Compared to **CodaMosa** ... CoverUp achieves a **per-module median line+branch coverage of 80% (vs. 47%)**"；(ii) "Compared to **MuTAP** ... CoverUp achieves an **overall line+branch coverage of 90% (vs. 77%)**"。项目只引 90%，未标"overall / vs MuTAP"。 | <https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/112/CoverUp-Effective-High-Coverage-Test-Generation-for-Python> | **A** |
| R10 | BASELINE.yaml："TestAgent **88.85% line / 55.4% mutation**" | 88.85% / 55.4% | 🚩 **与项目 README 自相冲突；且无法定位** | 项目内部冲突记录：`README.md:24` 写 TestAgent line **92.34%** / mutation **83.69%**；`BASELINE.yaml:50-51` 写 TestAgent **88.85% line / 55.4% mutation**。我对同一论文摘要核到的唯一数值是 **92.34% line**；**88.85 与 55.4 均未在任何可及一手来源中出现**。疑似来自该论文早期版本（arXiv v1/v2）而正文已更新。 | — | **D** |
| R11 | TestGenEval（**ICLR'25**） | —（项目仅作 L2 候补登记，未引用数值） | **属实** | 论文存在：*TestGenEval: A Real World Unit Test Generation and Test Completion Benchmark*，**ICLR 2025** 官方 proceedings，作者 Kush Jain, Gabriel Synnaeve, Baptiste Rozière。规模：**68,647 tests / 1,210 code–test file pairs / 11 个 Python 仓库**；最强模型 GPT-4o 平均覆盖仅 **35.2%** | <https://proceedings.iclr.cc/paper_files/paper/2025/hash/26ded5c8ee8ec1bc4caced4e1c9b1584-Abstract-Conference.html> | **A** |
| R12 | BASELINE.yaml："Verified **2026-02-23** 官方弃用"（SWE-bench Verified） | 2026-02-23 官方弃用 | **存在性 B；具体日期无法定位（D）** | OpenAI 官方页面确实存在，标题为 *Why we no longer evaluate SWE-bench Verified*（中文页标题："为何 SWE-bench Verified 已无法衡量前沿编程能力"）。但 `openai.com/index/*` 与 `openai.com/zh-Hans-CN/index/*` 在本会话**均返回 HTTP 403**，我**未能取得正文**，故 **2026-02-23 这一日期无法核实**（C 级旁证：搜索结果 URL 携带 `utm_campaign=2026-02-24`，仅提示发布时点邻近，不构成证据）。 | 页面（403）: <https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/> | 存在性 **B**；日期 **D** |

### §1.2 三态结论汇总（任务书要求的计数）

| 三态 | 条目 | 数量 |
|---|---|---|
| ✅ **属实** | R1、R2(line)、R3(存在性)、R4a、R4b、R4d、R5、R6、R7a、R8、R9(数值)、R11、R12(存在性) | **13 项子结论** |
| 🚩 **数值/出处被误述** | **R4c**（请求数 11,718→**11,815**；12,264→**12,741**）<br>**R7b**（"控制规模后"的因果方向与原文"规模非主导混淆项"有张力）<br>**R6**（"100% **行**覆盖"原文为"100% coverage"，加了限定词）<br>**R9**（CoverUp 90% 未标 "overall / vs MuTAP"，另有 80% median/vs CodaMosa 一组）<br>**R2/R10**（TestAgent mutation 项目内两值冲突，且均未核实） | **5 项** |
| ❓ **无法定位（D）** | R3 的四个 mutation 数值；R2 的 mutation 83.69%；R7b 的 r=0.780；R10 的 88.85/55.4；R12 的日期 | **5 项** |

> **口径澄清**：任务书问"§1 中'误述/无法定位'的条目数"。按**标识符级**（一个 DOI/arXiv ID 算一条）计：**13 条标识符中，误述 1 条（R4 的请求数）、部分误述 3 条（R6/R7/R9 的口径）、无法定位数值 4 条（R2/R3/R7/R10）、未核实日期 1 条（R12）**。即"误述/无法定位"共 **9 条**，其中**纯'数值误述'严格只有 R4c 一处**。R12 为项目内部工程决策记录而非对外引用，可单独计。

### §1.3 核实表衍生观察（供 Lead 决策）

- **O1（正面）：项目引用链无伪造。** 8 个 DOI/arXiv 标识符（`10.1145/3803418`、`10.1145/3803437.3806428`、`11655121`、`2601.09695`、`2512.23631`、`10.1109/tse.2026.3682975`、`10.1145/3832093`、`10.1145/3805043`）**全部真实存在**，作者姓氏、venue 年号、DOI 与论文标题的对应关系**全部正确**。这排除了"引用编造"这一类最严重风险。
- **O2（关键风险）：最重的"不利证据"不可验证。** 项目 README 头部把 R3（IEEE 11655121）的 88.35% vs 35.92% 摆在与 CANDOR 0.991/0.970/0.980 直接对撞的位置，是全文张力最大的论证支点。而该支点的**四个数值我一个都无法从公开可及的一手来源确认**（IEEE/ACM 双重拦截 + S2 限流）。**建议**：在对外材料中把 R3 降级为"第三方复现研究报告（IEEE Xplore 11655121），其数值我们未能独立复核"，并把可复核的 R4（ICST 2026，我逐字核到全部关键数字）升为"迄今最强的可复核负面证据"。R4 的效应量级同样足以支撑同一论证（Plain-LLM 49.95% line 全面优于四个 SOTA 工具），因此**降级 R3 不削弱论点，反而提升可复核性**。
- **O3（载体强度提示）：TestAgent 是 5 页 Companion 短文。** FSE Companion '26 pp. 242–246。项目把它与 CANDOR（TOSEM 全文）并列为"有利证据"，**证据权重不对等**。引用时应标注载体类型。
- **O4（口径提示）：CANDOR 的 branch 优势不显著。** 论文自述：CANDOR 在 line 与 mutation 上显著优于 EvoSuite（Wilcoxon），但 **"none of the differences between CANDOR and EvoSuite are statistically significant" for branch coverage**，且 LeetCode-Medium 上 EvoSuite branch（0.959）反超 CANDOR（0.949）。项目把 "0.991/0.970/0.980" 作为一个整体正面结论引用，**隐含地把不显著的 branch 也算作显著领先**。
- **O5（正向惊喜）：R7 是 ISSTA 2026 Distinguished Paper。** 项目 BASELINE.yaml 把它作为"覆盖率-检出相关性批评的正确出处"，这个引用的**质量高于项目自身表述**，可以放心强化。

---

## §2 测试生成前沿表

> 表格中"是否被项目引用"指是否出现在 README.md 头部或 BASELINE.yaml 第 1–70 行。

| 系统 | 论文（年份·venue/预印本号） | 基准与条件 | 指标值（我核实） | 代码/数据 | 项目引用 | 等级 |
|---|---|---|---|---|---|---|
| **CoverUp** | Pizzorno & Berger, *CoverUp: Effective High Coverage Test Generation for Python*, **FSE 2025**，DOI `10.1145/3729398`，预印本 arXiv:2403.16218 | 挑战性 Python 开源项目代码；iterative coverage-guided LLM 对话 | **overall line+branch 90% vs MuTAP 77%**；**per-module median line+branch 80% vs CodaMosa 47%**；迭代覆盖引导贡献近 **40%** 的成功 | arXiv:2403.16218 | ✅（引 90%） | **A** |
| **TestSpark** | Sapozhnikov et al., *TestSpark: IntelliJ IDEA's Ultimate Test Generation Companion*, **ICSE-Companion 2024**, pp. 30–34 | IntelliJ 插件；可用 EvoSuite 或 LLM 模式 | 我**未取得该文自报数值**（仅确认载体：IEEE CSDL `icse-companion/2024/050200a030`）。**但它在独立复现中的表现是四个工具里最差的**：line/branch/mutation = **23.65% / 16.48% / 13.88%** | — | ❌（BASELINE 提及） | 自报值 **D**；复现值 **A** |
| **HITS** | *HITS: High-coverage LLM-based Unit Test Generation via Method Slicing*, arXiv:2408.11324（ICSE 2025 系） | Java；方法切片 + CoT | 复现值（Konstantinou ICST 2026）：line/branch/mutation = **42.43% / 29.49% / 27.97%**；**成本最高（16,735 requests）**；branch 在多数单仓库上第一 | — | ❌ | **A**（复现值） |
| **SymPrompt** | *Code-Aware Prompting: A Study of Coverage-Guided Test Generation in Regression Setting using LLM*, **ICSE 2024 / PACMSE**, DOI `10.1145/3643769`，arXiv:2402.00097 | Java；静态分析识别可行执行路径，逐路径生成 | 复现值：**40.95% / 27.19% / 28.40%**；**成本最低（5,602 requests）** | — | ❌ | **A**（复现值） |
| **ChatUniTest** | 被 Konstantinou 文引用为 ref [23]；ICSE 2024 系 | Java | 我**未取得一手数值**（仅在他人参考文献中出现） | — | ❌（BASELINE 头部提及） | **D** |
| **MUTGEN** | Wang, Xu, Briand, Liu, *Mutation-Guided Unit Test Generation with a Large Language Model*, **IEEE TSE 52(5):1657–1671, 2026**，DOI `10.1109/tse.2026.3682975`，arXiv:2506.02954 | **204 subjects / 两个基准**；mutation feedback 入 prompt + 迭代生成 | 核心论断："**some test suites achieve 100% coverage but only 4% mutation score**"；MUTGEN 在 mutation score 上显著优于 EvoSuite 与 vanilla prompt 策略 | — | ✅（BASELINE.yaml:64） | **A** |
| **CANDOR** | Xu, Wang, Briand, Liu, **TOSEM 2026**，DOI `10.1145/3803418`，arXiv:2506.02943 | Java；HumanEvalJava(160 程序) / LeetCodeJava(100 程序)；Llama 3.1 70B + DeepSeek-R1-distill-70B；3 次重复取均值；Wilcoxon + A12 | HumanEvalJava **0.991 / 0.970 / 0.980**（line/branch/mutation）；LeetCode-Medium **0.990 / 0.949 / 0.939**；LeetCode-Hard **0.989 / 0.980 / 0.937**；oracle correctness **0.971 / 0.993 / 0.961**；对 LLM-Empirical 领先 **15.8–25.1 pp** | 论文称录用后开源 | ✅（README:21-23） | **A** |
| **TestAgent** | Shang, Zhang, Zhan, Huang, Fang, Chen, **FSE Companion '26**, pp. 242–246，DOI `10.1145/3803437.3806428` | **6 个 Java 项目 / 1,451 methods**；VS Code 插件；repository-level Code Knowledge Graph；Planner/Generator/Reviewer 三智能体 | line coverage **92.34%**；检出 **154 个真实缺陷**，precision **92.22%**；"significantly outperforming EvoSuite and ChatUniTest" | <https://github.com/iSEngLab/TestAgent-VSCode-Extension> | ✅（README:24, BASELINE:50-51） | **A/B**（摘要级） |
| **ICST 2026 复现** (Konstantinou et al.) | **ICST 2026**，arXiv:2601.09695v2 | **6 个完整 Java 仓库 / 393 类 / 3,657 方法**；模型换成 GPT-4o-mini / Llama 3.3 70B / DeepSeek V3；Mann-Whitney U，p<0.05；JaCoCo + PIT | 见 §1 R4a–R4d。补充数据：**Plain-LLM class-level 33.53/21.05/22.08（仅 1,562 requests）**；**class+method 合并 53.67/38.74/36.55（13,228 requests）**；**混合粒度 52.30/38.84/36.76（10,548 requests，省 ~20% 请求）**；**~20% 生成测试不编译，~43% 测试不通过** | 论文 Data availability 章节 | ✅（README:25-28） | **A** |
| **TestGenEval** | Jain, Synnaeve, Rozière, **ICLR 2025** | **11 个 Python 仓库 / 1,210 code-test pairs / 68,647 tests**；覆盖 test authoring 与 test completion | 最强模型 **GPT-4o 平均覆盖仅 35.2%**；主因是模型难以推理执行语义、复杂路径上断言错误频发 | — | ✅（BASELINE:AN 批登记 L2 候补） | **A** |
| **ULT (UnLeakedTestbench)** | Huang, Zhang, Harman, Zhang, Du, Ng, **TOSEM 2026**，DOI `10.1145/3805043` | **3,909 个 function-level 任务**（真实世界 Python 函数，高圈复杂度、抗污染筛选）；12 个 SOTA LLM | **accuracy 41.32% / statement 45.10% / branch 30.22% / mutation 40.21%**；对照 TestEval **91.79/92.18/82.04/49.69**、PLT **47.07/55.13/40.07/50.80**；编码能力↔测试生成 **Pass@1 相关 0.79 (p=0.002)**（TestEval 0.56、PLT 0.52） | <https://github.com/huangd1999/UnLeakedTestBench> | ✅（BASELINE:51,64） | **A** |
| **SWT-Bench** | Mündler, Müller, He, Vechev, **NeurIPS 2024**, DOI `10.52202/079017-2601` | 基于流行 GitHub 仓库的真实 issue + ground-truth fix + golden tests | 定性结论：**(i)** 面向代码修复的 Code Agent 在生成测试上**超过**专门为测试生成设计的系统；**(ii)** 生成的测试作为代码修复的过滤器，**使 SWE-Agent 的 precision 翻倍**；报告 issue reproduction rate 与 coverage change 双指标 | <https://github.com/logic-star-ai/SWT-Bench> | ❌ | **A** |

### §2.1 本节要点

1. **"覆盖率饱和"是本方向 2025–2026 年的真实趋势。** 三个独立一手来源共同指向：CANDOR 在 HumanEvalJava 上 0.991 line / 0.980 mutation（方法级、小型程序）；TestAgent 92.34% line（中等规模 Java 仓库）；而在**真实世界 Python 函数**上 ULT 只有 45.10% statement / 40.21% mutation、TestGenEval 上 GPT-4o 只有 35.2%。**基准难度差异可造成 2 倍以上的指标落差**，跨基准比较 coverage 数字在方法论上无效。
2. **同一系统在不同评测下差距可达 3 倍。** CoverUp：自报 **90% overall line+branch**（Python，对 MuTAP）↔ 独立复现 **38.85% line / 26.26% mutation**（Java，对 Plain-LLM）。TestSpark：自报（未取得）↔ 复现 **23.65% line**（四工具最差）。**这是本项目"不轻信单一来源"纪律的最强外部支持。**
3. **"工具特定编排 vs 强 LLM 单提示"的负面结论有两份独立一手来源**（ICST 2026 复现；以及 §1 R3 无法核实的 IEEE 第三方复现），**但只有前者可复核。**

---

## §2b 与项目最可比的锚点：两条指标的精确定义（补充轮 · 2026-10-11）

> 项目主指标是 **fail-to-pass 检出率 44.8%**。Lead 要求精确到分子分母。
> **结论先行：ULT 的 41.32% 与 TestGenEval 的 35.2% 都不是缺陷检出率。把任一条与项目的检出率并列比较，在方法论上不成立。**

### §2b.1 ULT（TOSEM 2026，DOI `10.1145/3805043`）—— "accuracy 41.32%" 的确切定义

- **一手载体（全文）**：arXiv:2508.00408 全文 HTML <https://ar5iv.labs.arxiv.org/html/2508.00408>；DOI 记录 <https://api.crossref.org/works/10.1145/3805043>
- **等级：A**（arXiv 全文 HTML，可追溯版本）

**原文措辞（§3.4.1 "Test Generation Accuracy (Pass@k)"，逐字）**：

> "Test generation accuracy measures the proportion of correct test cases generated by the LLM. A test is treated as "correct" if it **compiles, runs to completion, and its assertions reflect valid expectations** of the function's behavior for the given inputs. In our benchmark, we define the accuracy metric as Pass@k, which represents **the average number of correct tests generated per function, normalized by the total number of test cases requested (K)**."

**原文公式（Eq. 1，逐字）**：

> `Pass@k = ( Σ_{i=1..N} C_i ) / ( N × K )`
> 其中 `C_i` = 为第 i 个函数生成的**正确**测试数（`0 ≤ C_i ≤ K`）；`N` = 基准中函数总数；`K` = 每个函数请求生成的测试数。

**表 2 标题（逐字）**：

> "RQ1.1: Accuracy of LLM-generated test cases in TestEval, ULT, and PLT. **Pass@k represents the percentage of the first K queries generated test cases that correctly pass the function under test.**"

**三问三答**：

| 问题 | 答案 |
|---|---|
| 是 test 通过率还是缺陷检出？ | **是测试有效性 / 通过率（test validity / pass rate）**，与缺陷检出**正交** |
| 分子 | `Σ C_i` = 所有函数上「能编译 + 能跑完 + 断言反映合法预期」的生成测试数总和 |
| 分母 | `N × K` =（基准函数数）×（每函数请求生成的测试用例数） |
| 是否缺陷检出率？ | **绝对不是。** ULT 自身的检出代理指标是同摘要里的 **mutation score 40.21%** |

> ⚠️ **未能解决的内部一致性问题（D 级，必须上报）**：ULT 摘要称 "on average for all LLMs" 的 accuracy = **41.32%**、TestEval = **91.79%**。但我实际取到的 **RQ1.1 准确率表（Table 2）** 显示 ULT **Pass@1 = 9.39%–17.83%**、**Pass@5 = 6.56%–21.64%**，TestEval **Pass@1 = 30.00%–77.62%** —— **两者都平均不出 41.32% / 91.79%**。我的抓取在 Table 2 处被输出长度截断，论文 PDF 因工具不支持 `application/pdf` 无法读取，故**我未能定位产生 41.32% 的那张表**，无法确认它是否仍用 Eq. 1 定义、抑或是另一聚合口径（另一 K 值 / 另一 prompt 设定）。
> **行动要求**：在项目对外材料中引用 41.32% 之前，必须先在 TOSEM 正式版中定位该表。**在此之前，只能引用 Eq. 1 的定义，不要引用 41.32% 这个数。**

### §2b.2 TestGenEval（ICLR 2025）—— "35.2%" 的确切定义

- **一手载体（全文）**：arXiv:2410.00752 全文 HTML <https://ar5iv.labs.arxiv.org/html/2410.00752>；官方 proceedings <https://proceedings.iclr.cc/paper_files/paper/2025/hash/26ded5c8ee8ec1bc4caced4e1c9b1584-Abstract-Conference.html>
- **等级：A**

**原文措辞 1（Table 2 该行，逐字数值）**：

> GPT-4o | All Pass@1 **7.5%** | Any Pass@1 **64.0%** | **Coverage 35.2%** | **Mutation 18.8%**

**原文措辞 2（§3.1 正文，逐字）**：

> "For coverage, GPT-4o performs the best, but still covers only **35.2% of the lines of code tested** in TestGenEval."

**原文措辞 3（Figure 1 标题，逐字）**：

> "Then we execute the generated test suite and measure **the proportion of lines in the code file that are executed (code coverage)**."

**原文措辞 4（§3 Evaluation，逐字）**：

> "For test suite generation we report pass@1 (if any of the tests in the generated test suite pass), all pass@1 (if the generated test suite passes), **coverage (coverage of passing tests)**, and mutation score (proportion of synthetic bugs introduced to code caught by test suite)."

**三问三答**：

| 问题 | 答案 |
|---|---|
| 35.2% 是什么？ | **被测代码的行覆盖率（line coverage）** |
| 分子 | 生成的测试套件执行到的、被测代码文件中的行数 |
| 分母 | 该被测代码文件中的可执行行数 |
| 条件 | 仅统计**通过的测试**（coverage of passing tests）；最强模型 GPT-4o；temperature = 0.2；1,210 个 code–test file pair 上取平均 |
| 是否检出率？ | **不是。** 同一行的 **Mutation 18.8%** 才是检出代理 |
| 任务粒度 | **文件级**（源文件平均 782 LOC），与项目函数级不同 |

### §2b.3 由此得到的唯一可辩护的"项目 vs 前沿"对照

| 对照维度 | 项目（自报） | 前沿一手锚点 | 可比性判定 |
|---|---|---|---|
| **检出率（fail-to-pass）** | 44.8% | **无同口径可比项** | ❌ ULT 41.32% 是**测试通过率**；TestGenEval 35.2% 是**行覆盖率**。三者口径互不相同 |
| **缺陷检出代理（mutation score）** | 待披露（项目取值区间 0.818–0.976，但为**合成集**且已接近饱和） | **TestGenEval GPT-4o 18.8%**（文件级 Python，基于 SWE-bench 真实仓库）；**ULT 12-LLM 平均 40.21%**（函数级 Python，抗污染） | ⚠️ 项目侧为合成集（BASELINE.yaml 已自述"变异体过弱、鉴别力有限"），**不可直接对照**，仅可作量级参照 |
| **被测代码行覆盖** | 84.0–93.6%（合成集） | TestGenEval 35.2%（真实 Python，文件级）；ULT statement 45.10%（真实 Python，函数级） | ❌ 基准难度差异达 2 倍以上，跨基准比较无效（呼应 §6 红线） |

> **给 Lead 的结论**：项目"44.8% 检出率"在 2025–2026 一手前沿文献中**没有同口径可比值** —— 现有基准报的是 coverage / mutation / pass-rate，**没有一份报 fail-to-pass 缺陷检出率**。
> 因此对外表述应写成"**项目的检出优先指标与前沿基准的非检出指标不可直接比较**"，而不是把 44.8% 与 41.32% 或 35.2% 并列。若必须给对照，最保守做法是**只对照 mutation score**，并显式声明项目侧是合成集、前沿侧是真实仓库——此时项目 0.818–0.976 会**看起来远优于**前沿 18.8%–40.21%，**必须同时说明合成集变异体过弱**，否则构成误导。

---

## §3 多智能体测试生成 / 程序修复前沿表

| 系统 | 论文（venue/ID） | 指标（我核实） | 基准与条件 | 代码 | 项目引用 | 等级 |
|---|---|---|---|---|---|---|
| **CANDOR** | TOSEM 2026，DOI `10.1145/3803418`（详见 §1 R1） | 见 §2 | HumanEvalJava / LeetCodeJava；**多智能体 + 面板讨论共识 oracle** | 待开源 | ✅ | **A** |
| **TestAgent** | FSE Companion '26 pp. 242–246（详见 §1 R2） | line 92.34%；154 real bugs；precision 92.22% | 6 Java 项目 / 1,451 methods；**repository-level Code Knowledge Graph** | <https://github.com/iSEngLab/TestAgent-VSCode-Extension> | ✅ | **A/B** |
| **BOAD** | **ICLR 2026**，arXiv:2512.23631（详见 §1 R5） | **SWE-bench-Verified：优于单智能体与手工多智能体**；**SWE-bench-Live：36B 系统榜单第 2**（评测时点），超过 GPT-4 / Claude 等更大模型 | 多臂老虎机自动搜索层级式 orchestrator + localization/editing/validation 子智能体 | <https://github.com/iamxjy/BOAD-SWE-Agent> | ✅（README:29，判定"不适用于测试生成论证"） | **A** |
| **SWT-Bench / SWE-Agent 交叉** | NeurIPS 2024, DOI `10.52202/079017-2601` | 生成测试使 **SWE-Agent precision 翻倍**；Code Agent 在测试生成上超过专用测试系统 | 真实 GitHub issue + golden tests | <https://github.com/logic-star-ai/SWT-Bench> | ❌ | **A** |
| **FTDI** | Men, Tong, Zuo, Lu, *FTDI: A budget-aware self-healing framework for LLM multi-agent code generation*，**Expert Systems with Applications**（DOI `10.1016/j.eswa.2026.134164`；预印本 DOI `10.2139/ssrn.6387100`） | 注入故障条件下：**HumanEval Pass@1 63.41%（Resilience 99.05%、RecoveryRatio 95.65%）**；**HumanEval+ Pass@1 53.05%（RecoveryRatio 89.29%）**；**MBPP Pass@1 46.84%（RecoveryRatio 115.75%，超过无注入基线）**；同时降低单位恢复成本 | 参数化故障注入 + 固定注入清单重放；**budget-gated 触发 + 分层修复（规则补丁 → 深度修复/重生成）+ 蒸馏免疫模块** | <https://github.com/UMENZZE/FTDI-Framework> | ❌（任务书点名） | **A**（Crossref 摘要字段） |
| **AgentCoder** | Huang et al., arXiv:2312.13010 | **未取得一手数值**（已确认 arXiv/ar5iv 载体存在） | 多智能体代码生成 + 迭代测试 | — | ❌（任务书点名） | **B**（存在性） |
| **RepoUnderstander** | *How to Understand Whole Software Repository?*，arXiv:2406.01422 | **未取得一手数值**（经 HuggingFace Papers / Semantic Scholar 确认载体） | 仓库级理解 | — | ❌（任务书点名） | **B**（存在性） |
| **LANTERN / TraceCoder / AgentRepair / UTgen** | — | — | — | — | ❌（任务书点名） | **D**（见 §8） |

---

## §4 自修复 / 运行时反思前沿表

> **诚实提示：这是六个子方向中一手数值最稀薄的一个。** 我检索到的三篇 2025–2026 主要一手文献，**摘要层面均不给出 detection latency / MTTR / 恢复质量的具体数值**（VIGIL 为案例研究；MTTR-A 为指标定义论文；FTDI 数值最全但属 §3 的代码生成场景）。**任何以"detection latency = X ms"、"MTTR 降低 Y%"形式出现的 VIGIL/SRE 多 Agent 数值，在本次检索范围内都无法被一手来源支撑，应视为 D 级。**

| 系统/文献 | venue / ID | 指标 | 我核实的内容 | 等级 |
|---|---|---|---|---|
| **VIGIL** | Cruz, C., *VIGIL: A Reflective Runtime for Self-Healing Agents*，arXiv:**2512.07094**（v1 2025-12-08，v2 2025-12-09） | **摘要中无任何定量延迟/MTTR 数值** | 真实存在。机制：监督"兄弟 agent"；行为日志 → 结构化情绪表示 → **EmoBank**（带衰减与上下文策略）→ **RBT 诊断**（strengths/opportunities/failures）→ 生成 guarded prompt 更新 + 只读代码提案；**state-gated pipeline**，非法状态转换显式报错。评估仅为 **"a reminder latency case study"**（识别到 elevated lag，自身诊断工具因 schema 冲突失败后又产出 fallback 诊断与修复计划）。**机制描述 A 级；数值 D 级（原文即无数值）。** | **A**（存在性/机制）；数值 **D** |
| **FTDI** | DOI `10.1016/j.eswa.2026.134164` / 预印本 `10.2139/ssrn.6387100` | Resilience 99.05%、RecoveryRatio 95.65%（HumanEval）、89.29%（HumanEval+）、115.75%（MBPP） | 见 §3。**这是本方向唯一取得完整一手数值的条目**，但场景是「LLM 多智能体代码生成的可执行反馈修复」，不是生产系统自愈，**不可直接迁移为 SRE MTTR 证据**。 | **A** |
| **MTTR-A** | Or, B., *MTTR-A: Measuring Cognitive Recovery Latency in Multi-Agent Systems*，arXiv:**2511.20663**（v1 2025-11-08，v5 2025-12-26；Comments: preprint） | 定义 **MTTR-A**（Mean Time-to-Recovery for Agentic Systems）、**MTBF**、**NRR**（normalized recovery ratio）；给出恢复延迟与长期认知 uptime 的理论界 | 真实存在。**方法是提出度量而非报告实测 SRE 数字**；实验为 LangGraph-based benchmark + 模拟 drift + reflex recovery。**价值：为本项目"detection latency / recovery quality"表述提供可引用的指标定义来源。** | **A**（指标定义） |
| **LLM + 云原生可观测性 RCA/修复** | Wang, Yuan, Hua, Chang, Yang, Qiu, *Integrating Large Language Models with Cloud-Native Observability for Automated Root Cause Analysis and Remediation*，**AISNS 2025**，DOI `10.1145/3797161.3797213`，pp. 327–334 | 我未取得正文数值（未 fetch 摘要字段） | 真实存在。**Venue 强度提示**：AISNS 2025（3rd Int'l Conf. on AI, Systems and Network Security）是**小型会议**，与 CANDOR/ULT 的 TOSEM、Zhao 的 ISSTA Distinguished Paper 不在同一证据层级，**不建议用它支撑"前沿 SOTA"主张**。 | **A**（存在性） |
| **agent-sandbox-runtime** | — | — | **未能定位任何一手来源**（疑似项目内部/自造名称）。见 §8。 | **D** |
| "SRE 多 Agent"（泛称） | 检索到 *Intelligent Site Reliability Engineering: A Multi-agent LLM Framework for Automated Incident Analysis and Root Cause Determination*，Int. J. of Intelligent Engineering & Systems, DOI `10.22266/ijies2025.1231.28` | — | 仅经搜索索引命中 DOI，**我未访问落地页**，不作数值采信。 | **C/D** |

---

## §5 逻辑 / 形式化驱动测试前沿表

> **覆盖率最低的一节。** 该方向（符号执行、SMT/规约驱动、组合测试、神经符号预言）在本次时间预算内未能取得与 §2/§3 同等质量的一手证据。以下仅列出**我实际访问或明确确认载体**的条目。

| 方向 | 文献 | 我核实的 | 等级 |
|---|---|---|---|
| **符号执行（经典）** | Cadar, Dunbar, Engler, *KLEE: Unassisted and Automatic Generation of High-Coverage Tests for Complex Systems Programs*，**USENIX OSDI 2008**（官方全文页）；ACM DOI `10.5555/1855741.1855756` | 真实存在；USENIX 官方 legacy 全文页与 OSDI'08 proceedings 可访问。**这是符号执行测试生成的奠基引用，可安全引为"经典方法"锚点。** | **A** |
| **ESBMC / 形式化验证** | *ESBMC: A Survey of Its Evolution, Integration, and Future Directions in Formal Software Verification*，arXiv:**2605.26169** | 载体存在（arXiv PDF 命中）。**我未取得正文**，不引数值。**ESBMC-AI 未定位任何一手来源 → D。** | **B**（存在性） |
| **公理化测试预言（axiomatic oracles）** | Molinelli et al., ISSTA 2025（作者 slides: `homes.cs.washington.edu/~mernst/pubs/axiomatic-oracles-issta2025-slides.pdf`） | 载体命中（Michael Ernst 主页，UW 官方域名）。**未取得论文页/DOI，未取数值。** 与项目"规约驱动断言增强"最相关的方向之一，**建议后续单独立项核实**。 | **B/C** |
| **SpecIR / SMT 驱动测试生成** | — | **未能定位一手来源**（`SpecIR` 在检索结果中未出现对应论文）。见 §8。 | **D** |
| **Alloy / 组合测试（combinatorial testing）** | — | **本轮未检索**（预算耗尽）。**不臆测，留空。** | **未评估** |
| **神经符号测试预言** | — | 同上。仅有一条间接命中（arXiv:2609.11085 提到 "Z3 oracle ... GenV+HN"，属他人论文对第三方工作的描述，非一手）。 | **D** |

---

## §5b 形式化 / 逻辑驱动测试（补充轮 · 2026-10-11）

> 补充轮定向检索 4 个方向：① 属性测试与规约驱动生成；② 断言/测试预言生成；③ SMT/符号执行 × LLM；④ 组合测试 / Alloy / 形式化规约驱动。
> **新增 17 条：A 4 / B 5 / B/C 1 / C 2 / D 5。** 本节独立编号，不改写 §5 已有内容（§5b.6 为补充轮的 D 级子清单）。
> **本轮最重要的结构发现：项目"逻辑驱动"主张最可对话的一手前沿，全部集中在 Alloy/形式化规约路线（LM2Alloy、Cunha & Macedo），而"属性推断/Hypothesis × LLM"这条项目实际采用的技术路线，在 2025–2026 一手学术文献中几乎没有实质载体。**

### §5b.1 属性测试与规约驱动生成

| 文献 | 作者 / 年份 / venue-ID | 指标与原文措辞 | URL | 等级 |
|---|---|---|---|---|
| **PGS（Property-Generated Solver）** | He, Chen, Zhang, Gao, Sheng；arXiv:**2506.18315**（v1 2025-06-23，v2 2026-05-01）；cs.SE 预印本 | 机制：**不增加测试数量，而是提高反馈质量**——检查高层程序属性（原文例："a sorting function must produce a non-decreasing sequence"），并把**最简失败反例**回灌 LLM。数值（逐字）："**an improvement of up to 13.4% in pass@1** against other TDD-based methods"、"**an over 64% fix rate** on problems where the model initially failed"、"**a bug fix rate 1.4x-1.6x higher** than the strongest debugging-based approaches" | <https://arxiv.org/abs/2506.18315> | **A** |
| **Property-Based Testing for LLM Outputs: Hypothesis Strategies for Non-Deterministic AI** | Ivchenko, O. & Ivchenko, I.（Odessa National Polytechnic University）；**Zenodo 预印本** DOI `10.5281/zenodo.21193418`，发布 2026-07-04 | ⚠️ **无任何可用数值**：Zenodo 记录显示**全部沉积文件为 794 字节**（单文件 `2819.md`），即摘要级/占位沉积，**不可能承载实验数据**；资源类型自标 "Preprint"，非同行评审，19 views / 6 downloads。**结论：该方向（Hypothesis × LLM）本次未能定位任何实质性一手学术载体。** | <https://zenodo.org/records/21193418> | **C/D**（载体存在，内容为空壳） |
| **Coverage-Free Fuzzing: LLM-Guided Refinement of Grammar-Based Test Generators** | 作者未取得；Zenodo 记录 22556343 | **未取得正文**（仅搜索片段命中）。不引数值。 | <https://www.zenodo.org/records/22556343> | **C/D** |
| **LLM-based Invariant Inference** | — | ❌ **检索命中误归属警告**：我用该关键词命中的 PDF 是 arXiv:**2603.26270**，实际打开后为 *Knowdit: Agentic Smart Contract Vulnerability Detection with Auditing Knowledge Summarization*（智能合约漏洞检测，cs.CR），**与不变量推断无关**。该关键词下**未能定位真实一手来源**。 | <https://arxiv.org/abs/2603.26270>（证明误归属） | **D** |

### §5b.2 断言 / 测试预言生成（assertion generation / test oracle）

| 文献 | 作者 / 年份 / venue-ID | 指标与原文措辞 | URL | 等级 |
|---|---|---|---|---|
| **TOGLL** | Hossain, S. B. & Dwyer, M.；**ICSE 2025, pp. 1475–1487**，DOI `10.1109/ICSE55347.2025.00098`；arXiv:**2405.03786**（v2 2024-12-10） | 设置：**微调 7 个 code LLM × 6 种 prompt**（SF110 数据集），在 **25 个大型 Java 项目**上验证泛化性；对比 EvoSuite 与 SOTA 神经方法 TOGA。数值（逐字）："TOGLL can produce **3.8 times more correct assertion oracles** and **4.9 times more exception oracles**"；"It can **detect 1,023 unique bugs that EvoSuite cannot**, which is **ten times more** than what the previous SOTA neural-based method, TOGA, can detect." | <https://arxiv.org/abs/2405.03786> | **A** |
| **An Empirical Study of Assertion Generation Strategies for LLM-Based Test Oracles** | 作者未取得；TU Delft 机构仓储（record `uuid:f3877914-bd2e-4007-945b-c0db271d27c8`） | **未取得正文**（两个独立索引命中载体：机构仓储记录页 + 文件页）。**不引数值。** 与项目"规约驱动断言增强"直接相关，**建议后续单独立项**。 | <https://repository.tudelft.nl/record/uuid:f3877914-bd2e-4007-945b-c0db271d27c8> | **B**（存在性） |
| **NEUROTESTGEN: Neuro-Symbolic Guided Test Generation with Large Language Models** | 作者未取得 | **未取得正文**（仅 Semantic Scholar reader 链接命中）。**不引数值。** 这是"神经符号测试生成"方向唯一命中的具体系统名。 | <https://www.semanticscholar.org/reader/825e69aa53a825d01b560829b1b8324e320b3231> | **B**（存在性） |
| **公理化测试预言（axiomatic oracles）** | Molinelli et al., ISSTA 2025 | 同 §5，载体为作者 slides（UW 官方域名），**未取得论文页/DOI/数值**。 | `homes.cs.washington.edu/~mernst/pubs/axiomatic-oracles-issta2025-slides.pdf` | **B/C** |

### §5b.3 SMT / 符号执行 × LLM

| 文献 | 作者 / 年份 / venue-ID | 指标与原文措辞 | URL | 等级 |
|---|---|---|---|---|
| **Towards Understanding the Effectiveness of Large Language Models on Directed Test Input Generation** | 作者未取得；DOI `10.1145/3691620.3695513`（ISSTA 2024 系，ACM） | **未取得正文/数值**（仅 ACM DL 链接命中）。 | <https://dl.acm.org/doi/10.1145/3691620.3695513> | **B**（存在性） |
| **ESBMC 综述** | *ESBMC: A Survey of Its Evolution, Integration, and Future Directions in Formal Software Verification*；arXiv:**2605.26169** | **未取得正文/数值**（同 §5）。**ESBMC-AI 仍未能定位任何一手来源（D）。** | <https://arxiv.org/abs/2605.26169> | **B**（存在性） |
| **"Agentic Concolic Execution"** | 作者/venue 未取得；IEEE Xplore 文档号 **11573412** | **未取得正文**（IEEE 在本会话被反爬拦截，见 §0.1）。这是"concolic + LLM"方向唯一命中的具体系统名，**但无任何可核实数值**。 | <https://ieeexplore.ieee.org/document/11573412>（本次不可访问） | **D** |
| **SpecIR / SMT 驱动测试生成** | — | **仍未能定位一手来源**（见 §8）。 | — | **D** |
| **LISA** | 作者/venue 未取得；arXiv:**2607.18711** | 仅搜索片段命中（内容为对 LISA 行为的第三人称描述），**未取得 abs 页，不引数值**。 | <https://arxiv.org/abs/2607.18711>（未验证） | **D** |

### §5b.4 组合测试 / Alloy / 形式化规约驱动 —— **本轮收获最大的方向**

| 文献 | 作者 / 年份 / venue-ID | 指标与原文措辞 | URL | 等级 |
|---|---|---|---|---|
| **LM2Alloy** | Rashid, T. & Malik, M. Z.；arXiv:**2607.18555**（v1 2026-07-20，仅此一版，**9 KB = 短篇探索性研究**）；cs.SE 预印本，无 venue | 设置：LLM 从**需求文档 AND 生产源代码**生成 **Alloy 形式规约**，再由规约派生可执行测试；评测两个真实开源 Python 库——**Flipper**（feature flag 管理）、**Cerberus**（数据校验）。关键数值与结论（逐字）："For Flipper, our pipeline **uncovered a genuine bug that the existing test suite had missed**: the library silently accepts duplicate flag names, directly contradicting its documented uniqueness requirement."；"A **direct LLM baseline**—generating tests from the same README but **skipping the Alloy step**—achieved **68% branch coverage yet failed to catch this bug across all three independent runs**."；"code-based specifications showed **lower variance** in test generation (**mean SD = 2.15**) than documentation-based ones (**mean SD = 5.0**)" | <https://arxiv.org/abs/2607.18555> | **A**（预印本级 A） |
| **Validating Formal Specifications with LLM-generated Test Cases** | Cunha, A. & Macedo, N.；arXiv:**2510.23350**（v1 2025-10-27，v2 2026-02-18）；cs.SE | 设置：用预训练 LLM 从**自然语言需求**自动生成测试用例，目标是 **Alloy 规约语言**表达的简单领域模型**结构需求**；重点评测 **GPT-5**，另报其他闭源/开源 LLM。结论（**摘要中无数值**，逐字定性）："GPT-5 is already quite effective at generating **positive (and negative) test cases** that are syntactically correct and that satisfy (or not) the given requirement, and that **can detect many wrong specifications written by humans**." | <https://arxiv.org/abs/2510.23350> | **A**（机制/定性）；数值 **D**（原文即无数值） |
| **Search-Based Inference of Class Invariants: How Far Can Simulated Annealing Take Us?** | 作者未取得；Springer DOI `10.1007/978-3-032-24839-8_6`（SSBSE 系） | **未取得正文/数值**。属"不变量推断"的**非 LLM 经典路线**，可作对照锚点。 | <https://dl.acm.org/doi/abs/10.1007/978-3-032-24839-8_6> | **B**（存在性） |
| **组合测试（combinatorial testing）** | — | **本轮仍未定位任何 2025–2026 一手来源。** 不臆测。 | — | **D** |

### §5b.5 本节对本项目"逻辑驱动"主张的意义（给 Lead）

1. **项目最可对话的一手前沿是 Alloy/形式化规约路线，而不是属性推断。** LM2Alloy 的结论与项目的"规约驱动断言增强"高度同构，且给出了一个**可直接引用的对照事实**：**跳过形式化中间层的直接 LLM 基线拿到 68% 分支覆盖，却三次运行全部漏掉那个真实缺陷**。这正是项目"高覆盖 ≠ 高检出"论点的**最新（2026-07）一手支撑**，且比 §1 R3（IEEE，不可核实）更可复核。**建议项目在"逻辑驱动"章节引用此文。**
2. **但必须同时承认：LM2Alloy 是 9 KB 的探索性预印本、无 venue、仅 2 个库。** 它支撑"方向可行"，**不支撑"性能优越"**。
3. **项目的属性测试路线（Hypothesis）在学术前沿上没有对应载体。** 我定向检索"property inference / LLM 生成属性不变量"，唯一命中的 Zenodo 记录是 **794 字节空壳**。这**不等于**该方向无价值，但意味着：**项目不能声称其属性/不变量路线"符合前沿趋势"，只能声称"探索性自研路线"。**
4. **SMT × LLM 结合方向（③）是本轮最弱的一环**：命中的两个具体系统名（"Agentic Concolic Execution"、"LISA"）**一个因 IEEE 拦截、一个因未取 abs 页，均无任何可核实数值**。若项目需要该方向的对照，须单独立项。

### §5b.6 补充轮仍无法定位的一手来源清单（D 级 · 附检索关键词）

> 不改写 §8，此处独立登记补充轮新增的 D 级条目。

| # | 条目 | 我尝试的关键词 / 路径 | 现状 |
|---|---|---|---|
| D20 | **LLM-based Invariant Inference（属性/不变量推断）** | 搜索 `property inference LLM test generation invariants 2026 arXiv primary evaluation`、`LLM-based Invariant Inference`；命中 PDF arXiv:2603.26270 打开后为无关的智能合约论文 | **D**（并已记录一次搜索命中误归属，防止后续误引） |
| D21 | **Agentic Concolic Execution** | 搜索 `LLM symbolic execution concolic hybrid test generation 2025 2026 arXiv coverage numbers`；命中 IEEE 文档号 11573412，`ieeexplore.ieee.org` 本次返回 202 空体 | **D**（存在性亦未确认） |
| D22 | **SpecIR / SMT 驱动测试生成** | 同 §8 D13，补充轮再次检索仍无对应论文 | **D** |
| D23 | **LISA（arXiv:2607.18711）** | 仅搜索片段命中第三人称描述，未取得 abs 页 | **D** |
| D24 | **组合测试（combinatorial testing）2025–2026 一手来源** | 搜索 `combinatorial testing Alloy formal specification LLM test generation 2026 arXiv`；本轮 Alloy 方向有收获（LM2Alloy / Cunha），但**组合测试本身零命中** | **D** |
| D25 | **Hypothesis × LLM 的实证研究** | 搜索 `LLM property-based testing property inference invariants 2025 2026 arXiv Hypothesis`、`property-based testing LLM generated properties Hypothesis academic 2026 arXiv evaluation coverage`；唯一命中 Zenodo 794 字节空壳 | **D**（无实质性一手载体） |

---

## §6 基准与评估方法论（含污染争议）

| 主题 | 一手来源 | 核实内容 | 等级 |
|---|---|---|---|
| **数据污染是基准设计的一等约束** | ULT (TOSEM 2026, `10.1145/3805043`) | 论文开篇即把现有基准的两大缺陷定为 **(i) data contamination、(ii) structurally simple function code**，并明确 "scientific conclusions drawn from empirical studies using these benchmarks may be compromised"。ULT 通过多阶段筛选 + 高圈复杂度 + 配对基准 **PLT（PreLeakedTestbench，含泄漏测试）** 做 memorization vs reasoning 的受控对照。**这是"污染争议"在本领域的正式文献形态。** | **A** |
| **LLM 生成测试的覆盖/变异/真缺陷相关性** | Zhao, Zhou & Cohen, **ISSTA 2026 Distinguished Paper**, `10.1145/3832093` | 复现 Inozemtseva 与 Papadakis 两项人类测试研究于 LLM 生成测试；结论"高度依赖上下文"：回归（假定无缺陷）设定下跨模型比较有效；被测代码可能有缺陷时**不再可靠**；且**未发现测试套件规模是主导混淆项**（与项目括注有张力，见 §1 R7b）。 | **A**（定性）/**D**（r 值） |
| **强 LLM 使工具特定编排优势消失** | Konstantinou, Degiovanni & Papadakis, **ICST 2026**, arXiv:2601.09695v2 | 见 §1 R4、§2。**方法论亮点可直接借鉴**：(i) 用**完整仓库**而非挑选类（避免选择偏差）；(ii) 按模型 cutoff 显式区分 **seen vs unseen**（"all projects created after October 1, 2023 classified as unseen"）；(iii) 用 **Mann-Whitney U** 检验（p<0.05）；(iv) 成本以 **LLM 请求数**度量，并显式排除网络失败请求；(v) 为公平性施加**统一后处理**过滤不编译测试。 | **A** |
| **统计检验实践对照（同指标两种做法）** | CANDOR（Wilcoxon Signed Rank + A12 效应量，遵 Arcuri & Briand 2011）vs Konstantinou（Mann-Whitney U） | **同一子领域存在两类非参数检验并行使用**。项目若只报 p 值而不报效应量，将低于 CANDOR 的呈现标准（CANDOR 同时报 A12=0.875 / 0.960）。 | **A** |
| **防污染滚动基准的官方弃用动因** | OpenAI, *Why we no longer evaluate SWE-bench Verified* | 页面存在；**正文 403，日期与论证细节未核实**（见 §1 R12）。 | **B/D** |
| **SWE-bench 原始基准** | Jimenez et al., *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?*，arXiv:2310.06770 | 载体在 ULT 参考文献 [22] 与 Zhao 参考文献 [32] 中被一致引用。**我未直接 fetch**。 | **B** |
| **跨基准可迁移性警告（本文档的核心方法论结论）** | 由 §2 三个一手来源合成 | ULT（真实世界 Python 函数）：statement **45.10%** / mutation **40.21%**；TestGenEval（11 Python 仓库）：GPT-4o 覆盖 **35.2%**；CANDOR（HumanEvalJava 方法级）：line **0.991**；TestAgent（6 Java 项目）：line **92.34%**。**四者不可横向比较**——任务粒度（method vs class vs repo）、语言（Java vs Python）、代码复杂度、是否抗污染筛选全部不同。**任何"系统 X 达到 Y%，故优于系统 Z 的 W%"的跨基准陈述都是无效推论。** | **A**（合成） |

---

## §7 冲突与交叉验证记录（同指标多来源不一致时全部列出）

> 按任务书要求：**冲突时并列全部来源与评测条件，不得择一。**

### 冲突 C1：CoverUp 的 line+branch coverage —— 90% vs 80% vs 38.85%

| 来源 | 数值 | 评测条件 |
|---|---|---|
| CoverUp 原文（FSE 2025 官方 program 摘要） | **90%** overall line+branch | Python 挑战性代码；基线 **MuTAP**（mutation/LLM-based），77% |
| CoverUp 原文（同上，同一摘要） | **80%** per-module **median** line+branch | 同上；基线 **CodaMosa**（hybrid search/LLM），47% |
| Konstantinou et al.（ICST 2026，我方逐字核实） | **38.85%** line / **25.11%** branch / **26.26%** mutation | **6 个完整 Java 仓库 / 393 类 / 3,657 方法**；模型换为 GPT-4o-mini/Llama3.3-70B/DeepSeek-V3；JaCoCo+PIT |

**处理**：三者**不构成矛盾**（语言、基准、粒度、基线全不同），但**项目引用的 "90%" 若未附条件极易被误读为通用水平**。建议项目引用时写作 "CoverUp 在 Python 基准上对 MuTAP 达 overall line+branch 90%（其自身报告）；独立复现于 6 个 Java 仓库上为 38.85% line"。

### 冲突 C2：TestAgent 的 mutation score —— 项目内两值 + 均未核实

| 来源 | line | mutation |
|---|---|---|
| 项目 `README.md:24` | **92.34%** | **83.69%** |
| 项目 `BASELINE.yaml:50-51` | **88.85%** | **55.4%** |
| 我核实（出版社摘要，S2 转载） | **92.34%** ✔ | **摘要中不存在** |

**处理**：**项目内部自相冲突**，且**两个 mutation 值我都无法从一手来源确认**。建议：删除 mutation 断言，只保留已核实的 92.34% line + 92.22% bug precision + 154 bugs。

### 冲突 C3：CANDOR 的 mutation score —— 0.980 vs 35.92% / 45.63%

| 来源 | CANDOR mutation | 条件 |
|---|---|---|
| CANDOR 原文（ar5iv 全文表 1，我方逐字核实） | **0.980**（2384/2443 mutants） | HumanEvalJava，方法级，Llama 3.1 70B + DeepSeek-R1-distill-70B |
| 项目所述 IEEE 11655121（Radaideh & Corriveau） | CANDOR **35.92%**（vs Gemini 2.5 Flash 88.35%）、CANDOR **45.63%**（vs GPT-4o 69.90%） | **未知**（我无法访问） |

**处理**：**这是一处量级级的表面冲突（0.980 vs 0.359/0.456），但冲突不可裁决**，因为我完全不掌握 R3 的评测条件（主题集、模型版本、是否需要 agentic iteration、mutant 生成方式）。**并列呈现，明确标注"后者的评测条件我们无法核实"**，不得择一，也不得暗示两者可直接比较。这正是项目 README 头部把两者并置时最需要加的限制。

### 冲突 C4：同一批工具的"自报 vs 独立复现"

| 工具 | 自报（原始论文） | 独立复现（ICST 2026，A 级） |
|---|---|---|
| CoverUp | 90% overall line+branch（有 80% median 一说） | 38.85% line / 26.26% mutation |
| TestSpark | 我未取得 | **23.65% line / 13.88% mutation（四工具最低）** |
| HITS | 我未取得 | 42.43% line / 27.97% mutation（成本最高） |
| SymPrompt | 我未取得 | 40.95% line / 28.40% mutation（成本最低） |

**处理**：**该表本身就是项目"不轻信单一来源"纪律的最强外部证据**，建议在项目对外材料中直接引用此对比。

### 冲突 C5：Zhao et al. 关于"测试套件规模"的结论方向

| 来源 | 表述 |
|---|---|
| 论文摘要（A 级，官方 program 页） | "We also find **little evidence that test suite size is a dominant confounder** for correlations among coverage, mutation, and real-bug detection for LLM-generated tests." |
| 项目 `BASELINE.yaml:64` | "…（branch vs raw mutation r=0.780 @k=10，**控制规模后**）" |

**处理**：论文的结论是"**规模并非主导混淆项**"，而项目括注"控制规模后"容易被读成"必须控制规模相关性才成立"。**建议改写为"且论文未发现规模是主导混淆项"**，并**删除未经核实的 r=0.780**（或注明出处为复现包中未复核的文件）。

### 冲突 C6：Konstantinou 论文的 LLM 请求数（版本漂移）

| 来源 | Plain-LLM | CoverUp |
|---|---|---|
| 项目 README:28 | 11,718 | 12,264 |
| 论文 v2（arXiv HTML，A 级） | **11,815** | **12,741** |

**处理**：判定项目值**误述**；定性结论（Plain-LLM 请求数低于 CoverUp）**成立**。疑似引用 v1 稿（我未取得 v1，故标注为推测）。

### 交叉验证记录（同指标 ≥2 独立来源）

| 指标 | 来源 1 | 来源 2 | 一致性 |
|---|---|---|---|
| CoverUp 的 FSE 2025 归属 | FSE 2025 官方 program 页 | CANDOR 参考文献 [5]（"Proceedings of the ACM on Software Engineering 2, FSE (2025), 2897–2919"） | ✅ 一致 |
| CANDOR 的 TOSEM DOI | Crossref 记录 | arXiv:2506.02943 的 "Related DOI" 字段 | ✅ 一致 |
| MUTGEN 的 TSE DOI | Crossref 记录（含卷期页码 52(5):1657-1671） | arXiv:2506.02954 的 "Related DOI" 字段 | ✅ 一致 |
| TestAgent 的 venue/DOI | Crossref（FSE Companion '26, pp.242-246） | Semantic Scholar（DBLP: `conf/sigsoft/ShangZZHFC26`） | ✅ 一致 |
| ULT 的 TOSEM 归属 | Crossref（TOSEM，2026-03-28 在线） | UCL Discovery 开放仓储副本 `discovery.ucl.ac.uk/id/eprint/10223971/1/3805043.pdf`（命中） | ✅ 一致 |
| Konstantinou 的 ICST 2026 归属 | IEEE CSDL 路径 `proceedings-article/icst/2026/...` | arXiv abs 页（未标 venue） | ⚠️ 仅 CSDL 一路；标 B |
| BOAD 的 ICLR 2026 归属 | IBM Research 官方出版物页（ICLR 2026 / Poster / 23 Apr 2026） | arXiv abs 页（未标 venue） | ⚠️ 仅 IBM 一路；但机构官方页强度高，标 A |

---

## §8 无法定位一手来源的条目（D 级清单）

> 每一条明确写出**我实际使用过的检索关键词**。凡列入此表者，**不得**在任何交付物中为其填写指标值。

| # | 条目 | 我尝试的关键词 / 路径 | 现状 |
|---|---|---|---|
| D1 | **IEEE 11655121 的四个 mutation score 数值**（88.35 / 35.92 / 69.90 / 45.63） | 直接 fetch `ieeexplore.ieee.org/document/11655121`（HTTP 202 空体）；`.../references#references`；`api.semanticscholar.org/graph/v1/paper/8eab00f0...`（连续 3 次 HTTP 429）；`semanticscholar.org/paper/...`（HTTP 202）；搜索 `"88.35" CANDOR mutation score Gemini 2.5 Flash`、`"35.92" OR "45.63" CANDOR mutation score one-shot GPT-4o`、`Radaideh Corriveau agentic iteration mutation testing abstract` | **论文存在性 B 级确认；四个数值 D 级。** 疑似唯一载体为 IEEE Xplore 付费墙 + Cloudflare |
| D2 | **TestAgent 的 mutation score 83.69%** | 搜索 `TestAgent multi-agent repository-level unit test generation line coverage 92.34 mutation 83.69`；fetch `dl.acm.org/doi/pdf/10.1145/3803437.3806428`（HTTP 403 Cloudflare）；S2 摘要（无该值） | **D**（摘要层无此数值；全文被拦截） |
| D3 | **TestAgent 的 88.85% line / 55.4% mutation**（BASELINE 版本） | 同上；附加搜索 BASELINE 内两值来源 | **D**（且与项目 README 自相冲突，见 C2） |
| D4 | **Zhao et al. 的 r=0.780 @k=10** | 搜索 `Do Coverage and Mutation Scores LLM-Generated Test Suites Correlate Zhao Zhou Cohen r=0.780`；fetch Crossref（摘要无数值）、ISSTA 2026 官方 program 页（摘要无数值） | **D**（全文 PDF 在 dl.acm.org 被 403；复现包 GitHub 未逐一核验） |
| D5 | **SWE-bench Verified "2026-02-23 官方弃用" 的具体日期** | fetch `openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/`（403）、`openai.com/zh-Hans-CN/index/...`（403） | **D**（页面存在性 B；日期无据） |
| D6 | **agent-sandbox-runtime** | 搜索 `"agent-sandbox-runtime"`、`agent sandbox runtime self-healing LLM` | **D**（未定位任何一手来源，疑似项目内部或自造名称） |
| D7 | **VIGIL 的任何定量指标**（detection latency / MTTR / 恢复质量） | fetch arXiv:2512.07094 abs 页（机制完整，**无数值**） | **D**（原文摘要即无数值；机制 A 级） |
| D8 | **LANTERN** | 搜索 `LANTERN LLM test generation repository level arXiv` | **D**（未定位） |
| D9 | **TraceCoder** | 搜索 `TraceCoder test generation LLM arXiv 2026` | **D**（未定位） |
| D10 | **AgentRepair** | 见上批量检索 | **D**（未定位） |
| D11 | **UTgen** | 见上批量检索 | **D**（未定位） |
| D12 | **ACH**（LLM 测试生成） | 搜索检索命中 ar5iv 2601.22832 中提及 "ACH Mutation-Guided (Foster et al." ——但那是**他人论文引用**（C 级），非一手 | **D** |
| D13 | **SpecIR / SMT 驱动测试生成（作为已发表方法）** | 搜索 `LLM formal specification generation test oracle SMT 2026 arXiv property-based`、`neuro-symbolic test oracle specification SMT` | **D**（未定位；仅命中他人论文对第三方工作的转述） |
| D14 | **ESBMC-AI** | 搜索 `ESBMC-AI LLM symbolic execution bounded model checking arXiv` | **D**（仅命中 ESBMC survey，无 ESBMC-AI） |
| D15 | **Alloy / 组合测试 / 神经符号预言（2025-2026 一手）** | 预算耗尽，**本轮未系统检索** | **未评估**（不得填值） |
| D16 | **ChatUniTest 自报数值** | 搜索 `ChatUniTest unit test generation ICSE 2024 coverage compilation pass rate`（仅命中他人参考文献） | **D** |
| D17 | **TestSpark / HITS / SymPrompt 各自论文自报数值** | 搜索 `TestSpark IntelliJ IDEA test generation companion ICSE 2024 evaluation`、`HITS LLM test generation hard-to-cover branches ICSE 2025`、`SymPrompt method-level prompt symbolic execution ICSE 2024`（命中载体，未取得正文表格） | **D**（存在性 B；自报值 D）。**复现值 A 级见 §2** |
| D18 | **TestGen-LLM（Meta）** | 未在本轮检索 | **未评估** |
| D19 | **"SRE 多 Agent" IJIES 2025 论文数值** | 搜索命中 DOI `10.22266/ijies2025.1231.28`，未访问落地页 | **D** |

---

## §9 给 Lead 的执行建议（基于本次一手证据）

1. **把可复核性当作引用排序的第一准则。** 用 **ICST 2026 复现（arXiv:2601.09695，我逐字核到全部关键数字）** 替代/补充 **IEEE 11655121** 作为"最强负面证据"；后者降级为"存在但数值未经我方独立复核"。论点强度不降反升（Plain-LLM 49.95% line 对四个 SOTA 工具的全面领先，已是同向且更可复核的证据）。
2. **修正 3 处引用缺陷**（全部为低成本修改）：R4c 请求数（→11,815 / 12,741）、R6 的"行覆盖"限定词（→"coverage"）、R9 的 CoverUp 条件（→"overall, vs MuTAP"）。
3. **删除 2 处无法核实的数值**：TestAgent mutation（83.69% 与 55.4% 二者皆删）、Zhao 的 r=0.780；同时修正 "控制规模后" 的表述方向（→"论文未发现规模是主导混淆项"）。
4. **补 3 处口径强化**：CANDOR 的 branch 优势**统计不显著**（O4）；TestAgent 是 **5 页 Companion 短文**（O3）；Zhao 等为 **ISSTA 2026 Distinguished Paper**（O5，可正向强化）。
5. **建立"跨基准不可比"红线**：§6 末行已给出四个一手数值的落差谱（35.2% → 45.10% → 92.34% → 0.991），建议项目对外材料显式声明**不跨基准比较覆盖率**。
6. **§4/§5 是真实的能力空白，不是检索失败。** 自修复方向 2025–2026 的一手文献普遍**只提机制不给数值**（VIGIL 即典型）；形式化方向我本轮几乎未覆盖（§8 D13–D15）。若项目需要在这两个方向建立对外主张，**应单独立项做专门检索**，不要用现有材料里的数字充数。

---

## §10 附：本文件所有一手 URL 清单（便于复核）

```
# DOI 注册机构（Crossref）
https://api.crossref.org/works/10.1145/3803418              # CANDOR / TOSEM 2026
https://api.crossref.org/works/10.1145/3803437.3806428      # TestAgent / FSE Companion '26
https://api.crossref.org/works/10.1145/3805043              # ULT / TOSEM 2026
https://api.crossref.org/works/10.1145/3832093              # Zhao et al. / ISSTA 2026
https://api.crossref.org/works/10.1109/tse.2026.3682975     # MUTGEN / IEEE TSE 2026
https://api.crossref.org/works/10.1145/3797161.3797213      # LLM + Cloud-Native Observability / AISNS 2025
https://api.crossref.org/works?query.bibliographic=FTDI...  # FTDI 检索（含 ESWA + SSRN 两条 DOI）

# arXiv（abs / HTML / ar5iv）
https://arxiv.org/abs/2601.09695        https://arxiv.org/html/2601.09695v2      # ICST 2026 复现
https://arxiv.org/abs/2512.23631                                                 # BOAD
https://arxiv.org/abs/2506.02943        https://ar5iv.labs.arxiv.org/html/2506.02943   # CANDOR（表 1）
https://arxiv.org/abs/2506.02954                                                 # MUTGEN
https://arxiv.org/abs/2512.07094                                                 # VIGIL
https://arxiv.org/abs/2511.20663                                                 # MTTR-A

# 会议官方 program / proceedings
https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/112/CoverUp-...   # CoverUp / FSE 2025 + DOI
https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/2/...         # Zhao et al. / ISSTA 2026（Distinguished Paper）
https://proceedings.iclr.cc/paper_files/paper/2025/hash/26ded5c8ee8ec1bc4caced4e1c9b1584-Abstract-Conference.html  # TestGenEval / ICLR 2025
https://proceedings.neurips.cc/paper_files/paper/2024/hash/94f093b41fc2666376fb1f667fe282f3-Abstract-Conference.html # SWT-Bench / NeurIPS 2024
https://www.computer.org/csdl/proceedings-article/icst/2026/330800a233/2iat1rHIAUM    # ICST 2026 条目（JS 渲染）

# 机构官方
https://research.ibm.com/publications/boad-discovering-hierarchical-software-engineering-agents-via-bandit-optimization  # BOAD / ICLR 2026

# 一手摘要转载（B 级载体）
https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3803437.3806428?fields=title,abstract,venue,authors,externalIds

# 被拦截（记录在案，未取得内容）
https://ieeexplore.ieee.org/document/11655121                     # HTTP 202 空体
https://dl.acm.org/doi/pdf/10.1145/3803437.3806428                # HTTP 403 Cloudflare
https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/   # HTTP 403
```

**文档结束。** 本文件所有数值均可回溯至上列 URL；无一条来自记忆或二手转述。

---

## §11 定向核实：arXiv:2609.24341 能否支撑"plain LLM 优于复杂编排"（补充轮 2 · 2026-10-11）

> 触发：项目内既有审查报告（`EXTERNAL_REVIEW_2026-10-11.md:193` / `OPTIMIZATION_PLAN_v2.md:281`）声称"**plain LLM 优于复杂编排已被两篇独立一手研究复现**"，引用 arXiv:2601.09695（Konstantinou et al., ICST 2026）与 **arXiv:2609.24341**。
> 纪律：本节结论**仅**来自我对一手载体的访问，不采信上述两份项目内报告的转述。

### §11.1 论文存在性核实

| 项 | 我核实值 |
|---|---|
| **存在性** | ✅ **真实存在**（arXiv abs 页 HTTP 200） |
| **arXiv ID** | `2609.24341`（v1，**2026-09-21 09:37:19 UTC**，339 KB） |
| **标题** | *Evaluating the effectiveness of class-level LLM-generated test suites in Python*（与项目所述**逐字一致**） |
| **作者** | Bilal Al-Ahmad、M. Harshvardhan、Khaled El-Fakih、Anas AlSobeh（与项目所述**完全一致**） |
| **venue** | **无**。仅 arXiv v1 预印本，**未经同行评审**；arXiv 页明确标注 "DOI ... (pending registration)"，即**连 arXiv DOI 都尚未注册** |
| **class** | cs.SE |
| URL | <https://arxiv.org/abs/2609.24341> |
| **等级** | **A**（一手 abs 页，存在性/元数据/摘要三项可验证）；**但属预印本，非同行评审** |

### §11.2 论文核心结论（**逐字引自 abs 摘要**）

原文分四段（Context / Objective / Method / Results / Conclusion）。关键句逐字：

> **Context**: "high structural coverage does not establish that those tests execute reliably or detect faults. Existing evidence often treats coverage as the principal outcome and rarely compares prompt strategies and models through mutation testing at class level."

> **Method**: "We evaluate **multiple prompt strategies across a diverse set of current LLM configurations** on the **ClassEval** benchmark. The evaluation combines execution outcomes, line and branch coverage, **Cosmic Ray mutation scores**, and structural quality indicators. Primary analyses treat **successful execution as a prerequisite**; paired comparisons use **only classes shared by the relevant executable subsets**."

> **Results**（四项，逐条）：
> 1. "**Structural coverage is consistently near its ceiling and offers little discrimination among configurations.**"
> 2. "**Executability varies substantially.**"
> 3. "The proposed prompt performs strongly for mutation score, but **no prompt dominates across models**. **Model choice explains more variation than prompt choice**, and their interaction shows that **prompt effectiveness depends on the selected model**."
> 4. "**Human and LLM suites are evaluated on unequal executable subsets, so their relative mutation scores do not establish superiority.**"

> **Conclusion**: "Reliable assessment of LLM-generated tests should **treat executability as a gate** and combine coverage with mutation testing and structural quality indicators. In practice, **model selection should precede prompt tuning.**"

**与项目既有报告描述的比对**：既有报告的概括（结构覆盖近上限、几无鉴别力；可执行性差异显著；模型选择方差 > 提示策略；提示×模型存在交互；人类 vs LLM 在不等可执行子集上比较故不能宣称优劣）——**与我一手核到的摘要逐点吻合，无夸大、无缩水**。这部分转述是准确的。

### §11.3 **关键判断题：能否支撑"plain LLM 优于复杂多智能体编排"？**

## ❌ **不能。Lead 的初步判断成立，我确认（不推翻）。**

**四条原文依据**：

1. **该研究的设计里根本没有"编排（orchestration）"这个自变量。** 原文 Method 逐字："We evaluate **multiple prompt strategies across a diverse set of current LLM configurations**" —— 因子空间是 **prompt 策略 × LLM 配置**。它从未实例化、也从未评测任何多智能体编排 / 工具调用循环 / 迭代修复环作为对照臂。**一个没有 orchestration 臂的实验，在逻辑上不可能得出关于 orchestration 优劣的结论。**
2. **它的核心命题是"方差分解"，不是"范式排序"。** 原文："**Model choice explains more variation than prompt choice**"，结论落到 "**model selection should precede prompt tuning**"。这是**提示设计与模型选择两个因子之间的相对重要性排序**，与"单提示 vs 多智能体"是**两个不同命题**。
3. **它明确自我克制，拒绝在可比性不足时宣称优劣。** 原文："Human and LLM suites are evaluated on **unequal executable subsets**, so **their relative mutation scores do not establish superiority**." —— 这是**主动放弃排序结论**，方向与"可用它来排序范式"完全相反。
4. **它自己报告提示层面的排序不稳定。** 原文："**no prompt dominates across models**"，且"**prompt effectiveness depends on the selected model**"。既然连 prompt 之间的排序都不稳定，用它去支撑一个更大的范式级排序更不成立。

**命题拆分（这是本次核实的核心产出）**：

| 命题 | 内容 | arXiv:2609.24341 是否支持 |
|---|---|---|
| **X** | 结构覆盖饱和、无鉴别力；可执行性应作为门；模型选择先于提示调优 | ✅ **直接支持**（逐字） |
| **X′** | 模型选择解释的方差 > 提示策略；二者存在交互 | ✅ **直接支持**（逐字） |
| **Y** | **plain LLM（单提示）优于复杂多智能体编排** | ❌ **完全不支持**——无 orchestration 臂；命题层级不同 |

**结论**：项目内报告把 **X/X′** 当成了 **Y**，属**命题替换（equivocation）**。两份被引文献中：
- **arXiv:2601.09695（ICST 2026）** 支持的是"**Plain-LLM 优于四类工具特定工程化流水线**"（HITS/SymPrompt/TestSpark/CoverUp）——这仍是"**单提示 vs 工具特定工程化**"，**不等于"单提示 vs 多智能体编排"**；且同一文献集里 CANDOR（TOSEM 2026，多智能体，HumanEvalJava mutation 0.980）、TestAgent（FSE Companion '26，三智能体，line 92.34%）、BOAD（ICLR 2026，自动搜索层级多智能体）是**反向证据**。
- **arXiv:2609.24341** 只支持 **X/X′**。

> **因此"已被两篇独立一手研究复现"这一表述不成立**：两篇文献**没有任何一篇**研究了 orchestration；其中一篇（2609.24341）的研究问题与编排无关，另一篇（2601.09695）研究的是工具特定工程化。**这是 §1/§7 已记录的项目"方向不一的证据须并列、不得择一表述为共识"纪律的一次新违反实例，且性质更重——不是择一，而是命题替换。**

### §11.4 附带核实：SWE-bench Verified 榜首 79.2%（396/500）

| 项 | 结论 |
|---|---|
| 项目所述 | 榜首 **79.2%（396/500）**，来源标为官方榜单条目 `20251215_livesweagent_claude-opus-4-5` 与 `20251205_sonar-foundation-agent_claude-opus-4-5` |
| 我尝试的路径 | `web_fetch https://www.swebench.com/`（**30s 超时**）；`web_fetch https://github.com/...`（本会话 **github.com 解析到非公网 IP，被拒**）；检索精确文件名 `"20251215_livesweagent_claude-opus-4-5"` / `"20251205_sonar-foundation-agent_claude-opus-4-5"`（**零精确命中**）；检索 `swe-bench experiments evaluation verified directory livesweagent claude-opus-4-5 results.json` |
| 间接旁证（非数值证据） | 系统名本身可信：**Live-SWE-agent** 见 OpenAutoCoder/live-swe-agent 官方仓库；**Sonar Foundation Agent** 见第三方研究文档（`github.com/shenxingy/Clade` docs, 2026-06-18） |
| **结论** | ❌ **无法定位**：我**未能访问 swebench.com 官方榜单页**，也**未能命中这两个榜单条目 ID**，故 **79.2% / 396/500 这一数值与条目存在性均无法核实（D 级）**。**不得采信，也不得据以宣称"榜首"**（另注：`§1 R12` 已记录 SWE-bench Verified 的官方弃用争议，即便该数值为真，用它作为前沿锚点亦须先处理弃用问题） |

### §11.5 本节新增 D 级条目

| # | 条目 | 检索关键词 / 路径 |
|---|---|---|
| D26 | SWE-bench Verified 榜首 79.2%（396/500）及两个榜单条目 ID | 见 §11.4；swebench.com 超时 + github.com 被拒 + 精确文件名零命中 |
| D27 | arXiv:2609.24341 的具体数值（ClassEval 上有多少 LLM 配置、各 prompt 策略的 mutation score 数字、模型 vs 提示的方差占比） | 仅取到 abs 摘要；**全文 HTML 未抓取**（预算限制）。**故本节只断言"该文不支持命题 Y"，不断言其任何具体数值。** 若需引用其数值，须另取 <https://arxiv.org/html/2609.24341v1> |

> **时效声明**：本节完成于 2026-10-11T14:0x+08:00。arXiv:2609.24341 为 **v1 预印本（2026-09-21）**，尚无 DOI、无 venue，**结论可能随后续版本变化**；引用前应复核版本号。
