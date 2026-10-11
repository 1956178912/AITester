# T-D 引用与前沿数字真实性核验（独立核验报告）

- **任务**：task-4 — 对项目文档与既有评审中出现的全部文献引用与前沿数字做真实性与一手性核验
- **核验人**：citation-verifier（独立评审团队 T-D）
- **核验日期**：2026-10-11
- **核验范围**：`README.md`（含首 1-60 行）、`README.en.md`、`REVIEW_2026_FRONTIER.md`、`review_2026/R1_frontier_testgen.md`、`R2_frontier_repair.md`、`R3_frontier_logic.md`、`E4_R3_logic_frontier.md`
- **纪律声明**：本报告每条判定均附**实际访问的 URL** 与**实际观察到的返回**。未使用记忆填充。端点不可达的情况已如实标注。

---

## 0. 核验方法、覆盖度与端点可达性

### 0.1 实际使用的可机读端点

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

### 0.2 覆盖度

| 类别 | 抽取数量 | 核验结果 |
|---|---|---|
| 唯一 DOI（正则抽取自 7 份文档） | **42** | Crossref 200 → **40**；Crossref 404 → **2**（均为 Zenodo）。其中 `zenodo.14502996` 经 DataCite/doi.org 确认为**真实**（TSC2CARLA artifact，DLR）；`zenodo.1234567` 经 doi.org + DataCite 双重 404，为**占位符**，且**项目自身已正确标注**其为第三方记录不严谨的证据（`review_2026/E4_R3_logic_frontier.md:99`）|
| 唯一 arXiv ID | **72** | arXiv API **72/72 全部返回有效 `<entry>`**；**0 个返回 no-paper/404**。即：**项目中不存在任何伪造的 arXiv ID** |
| 提示词重点怀疑清单（20 个系统名） | 20 | **17 个确认为真实存在**（多数带一手指标逐字命中）；2 个为项目自身已标注的"不可引用来源"；1 个在项目文档中根本不存在 |
| 6 个重点 DOI + 2 个重点 arXiv ID | 8 | **全部真实存在**，且 **5 个的双参数指标原文逐字命中** |

### 0.3 关于"提示词怀疑清单"的整体结论（最重要的元发现）

> 任务提示词给出的"很可能是幻觉"的 20 个系统名与 6 个 DOI，经逐条一手核验后：**绝大多数是真实的**。
> 唯一被确证"无任何一手记录"的是 **ARC-APR**；另有 **"85% MTTR reduction"** 与 **ESBMC-AI** 无一手来源（二者项目已自行标注）。
> **反过来，本次核验真正查出的是项目自身评审中的 3 处实质错误**（见 §3）——其中 `Defects4J v3 不存在` 是**明确的事实性错误**。

---

## 1. 引用核验表（核心产出）

证据等级：**A** = 机读权威元数据 + 一手全文/摘要逐字命中；**B** = 机读元数据 + 一手摘要命中，细节未逐字；**C** = 仅元数据存在性；**D** = 未能核验。

### 1.1 提示词指定的 6 个重点 DOI + 2 个重点 arXiv ID

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

### 1.2 提示词怀疑清单中的系统名（20 项）

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

### 1.3 项目文档中其它被独立复核的一手数字（抽样 12 项，全部命中）

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

## 2. 疑似幻觉引用清单（重点产出）

> **总体结论：项目文档中不存在"凭空虚构"的文献引用。** 42 个 DOI 中 41 个真实、1 个是有意引用的占位符（且项目已正确批判）；72 个 arXiv ID **全部真实**。
> 真正的问题不是"编造"，而是**三处事实性错误 + 若干归属/限定条件缺陷**。下列按严重度排序。

### 2.1 🔴 H-1｜`Defects4J v3 不存在` —— **项目自身的明确事实性错误**

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

### 2.2 🟠 H-2｜IEEE 复现研究的**方法学限定条件被完全省略**（最影响结论强度）

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

### 2.3 🟠 H-3｜"45s vs 50h 无出处" —— **该项目评审的误判（实际有一手出处）**

- **出现位置**：`REVIEW_2026_FRONTIER.md:52`、`:774` 附近及 T3 摘要段（文档中"③ '45s vs 50h' 无出处"）
- **项目原话**（`grep` 结果）："② 未标注第三方复现身份；③ **"45s vs 50h" 无出处**。"
- **实际核验**：IEEE BDAI 2026 摘要逐字：
  > "The one-shot prompt strategy ran on Gemini also surpasses the human baseline (83.98%) **in about 45 seconds**, while CANDOR with Gemini took roughly **50 hours**."
- **判定**：❌ **该"无出处"结论错误**。"45s vs 50h" **确实有出处**，即同一篇 IEEE 复现研究（11655121）。
- **可执行更正文本**：
  > 将 `REVIEW_2026_FRONTIER.md` 中 "③ '45s vs 50h' 无出处" 改为：
  > "③ '45s vs 50h' **有出处**：Radaideh, Corriveau & Shi, BDAI 2026（IEEE Xplore 11655121）摘要原文 'in about 45 seconds' / 'roughly 50 hours'。**证据等级：一手（摘要级）**；引用时须同时标注其为**单一 25 类系统的第三方复现**。"

### 2.4 🟡 H-4｜"85% MTTR reduction" —— 确无一手来源（**项目判定正确**）

- **出现位置**：`R2:90,324,359`；`REVIEW_2026_FRONTIER.md:280,318`、`:1225`(E36)
- **实际核验**：项目指认的唯一来源为个人 GitHub README `github.com/suhail39ahmed/self-healing-azure-pipelines`。本次独立复核未发现任何同行评议论文、DOI 或基准支撑该数字。
- **判定**：✅ **项目判定正确（不得引用）**。保留现有 `C` 级与"禁止进入对外文档"的处置。

### 2.5 🟡 H-5｜ARC-APR —— 确无一手记录（**项目判定正确**）

- **出现位置**：`R2:119,392`；`REVIEW_2026_FRONTIER.md:278,1225`(E36)
- **实际核验**：
  - `https://api.openalex.org/works?search=ARC-APR&per-page=5` → HTTP 200，`count: 71328`，但前 5 条全部为**无关**材料学/焊接论文（"Fluid transpiration arc"、"submerged arc weld"、"arc plasma jets"，1967-1990），**无任何软件工程/程序修复命中**；
  - `web_search` 多轮组合（"ARC-APR automated program repair benchmark"）→ 无匹配一手记录。
- **判定**：✅ **项目判定正确**。维持"疑似不存在 / 禁止引用"。

### 2.6 🟡 H-6｜`10.5281/zenodo.1234567` —— 占位符（**项目判定正确**）

- **出现位置**：`review_2026/E4_R3_logic_frontier.md:99`
- **实际核验**：`https://doi.org/10.5281/zenodo.1234567` → **HTTP 404**；`https://api.datacite.org/dois/10.5281/zenodo.1234567` → `{"errors":[{"status":"404","title":"The resource you are looking for doesn't exist."}]}`
- **判定**：✅ **该 DOI 确实不存在**，但它是**项目用来举证某第三方 Zenodo 记录不严谨的证据**（"the citation block prints a **placeholder DOI**"），**不是项目自身的引用**。项目的处置完全正确。
- **附**：`10.5281/zenodo.14502996`（TSC2CARLA artifact，`R3:276`）**真实**：`https://doi.org/10.5281/zenodo.14502996` → HTTP 200 → `https://zenodo.org/records/14502996`；DataCite 记录 creators = Borchers, Philipp (DLR) 等。**Crossref 的 404 是注册机构不同所致，非失效。**

### 2.7 🟡 H-7｜ESBMC-AI / agent-sandbox-runtime / AutoGPT Devloop

| 名称 | 判定 | 依据 |
|---|---|---|
| **ESBMC-AI** | 无一手指标来源 | 项目已自标 `C`（`REVIEW_2026_FRONTIER.md:317,1225`）。抽查支持该处置 |
| **agent-sandbox-runtime** | 纯基础设施，无论文无指标 | 项目已自标 `C`（`:321,1225`）。抽查支持该处置 |
| **AutoGPT Devloop** | **无一手记录；且项目文档中根本不存在该引用** | `grep -rn "Devloop\|DevLoop\|devloop" --include=*.md` → **0 命中**；`web_search` 仅返回无关个人站点 |

### 2.8 🟡 H-8｜`1,451 methods`（TestAgent）—— **未能一手核验的数字**

- **出现位置**：`review_2026/R1_frontier_testgen.md:72`："**6 Java projects, 1,451 methods**"
- **实际核验**：`https://arxiv.org/html/2607.09101v1`（HTTP 200，275,805 B）全文检索 `"1,451"` → **0 命中**；`"1451"` → **0 命中**。摘要只声明 "**six Java projects**"。正文 RQ 段落可见 "we adopt the same **five projects** used in prior LLM-based test generation studies" 与 "we randomly select **200 methods** each from the Lang and Chart projects"，以及 Python 子集 "a total of **141** focal methods"。
- **判定**：⚠️ **"1,451 methods" 在一手全文中无法定位**——可能来自被评审自算的合计、或来自不同版本。**在定位到出处前，该数字应按"未核验"处理**。
- **可执行更正文本**：将 `R1:72` 的 "6 Java projects, 1,451 methods" 改为 "6 Java projects（论文摘要口径；**方法总数未能从一手全文定位，暂不引用具体数字**）"。

---

## 3. 引用元数据错误但文献存在（错配清单）

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

## 4. 真实存在且有价值的一手来源清单（可直接用于投稿引用）

按"可直接引用强度"排序。全部经本次机读端点一手核验。

### 4.1 A 级：一手全文逐字命中（可直接引用，建议保留/升级）

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

### 4.2 建议新增（项目已引用但标识不完整，补一手标识后可直接用）

| 来源 | 建议补全的标识 | 一手核验路径 |
|---|---|---|
| Konstantinou et al. | DOI `10.1109/icst69053.2026.00040` | OpenAlex `filter=title.search:newer LLM versions` |
| BOAD | ICLR 2026 Poster 官方页：`research.ibm.com/publications/boad-discovering-hierarchical-software-engineering-agents-via-bandit-optimization` | HTTP 200 |
| FTDI | DOI `10.1016/j.eswa.2026.134164`；PII `S0957417426030708`；*Expert Systems with Applications*, 2026-08-26 | OpenAlex / Crossref / ScienceDirect PII 页 |
| IEEE 11655121 | 完整 DOI `10.1109/bdai70753.2026.11655121`；venue *2026 IEEE 9th Int. Conf. on Big Data and Artificial Intelligence (BDAI)*；pp. 128-132 | Crossref HTTP 200 |

### 4.3 明确**不得引用**（维持或新增）

| 来源 | 理由 | 一手依据 |
|---|---|---|
| **ARC-APR** | 无任何一手记录 | OpenAlex 精确检索 71,328 条中前 5 条全无关；多轮 web_search 无命中 |
| **"85% MTTR reduction"** | 唯一来源为个人 GitHub README | 项目 `R2:90,324,359` 已标注；独立复核未发现论文/DOI/基准 |
| **ESBMC-AI** | 无一手成功率来源 | 项目已自标 `C` |
| **agent-sandbox-runtime** | 纯基础设施，无指标 | 项目已自标 `C` |
| **`10.5281/zenodo.1234567`** | DOI 不存在（占位符） | `doi.org` 404 + DataCite 404 |
| **"1,451 methods"（TestAgent）** | 一手全文无法定位 | `arxiv.org/html/2607.09101v1` 检索 `1,451`/`1451` → 0 命中 |
| **"Defects4J v3 不存在"（项目结论）** | **反向更正**：v3.0 真实存在 | `arxiv.org/html/2607.22880v1`："Defects4J v3.0 contains **854** defects across **17** projects" |

### 4.4 对不存在项的"最接近真实替代工作"建议

| 不存在的项 | 替代建议 |
|---|---|
| **ARC-APR**（无一手来源） | 若原意是"真实仓库级 APR 基准"，改用 **Defects4J v3.0**（854 defects / 17 projects，Zhao/Zhou/Cohen ISSTA 2026 一手陈述）或 **GitBug-Java**；若原意是"agentic APR 评测"，改用 **CI-Bench**（DOI `10.1145/3774748.3787606`）、**Multi-SWE-bench** 或 **SWE-bench-Verified** 官方榜单 |
| **"85% MTTR"** | 改用可核验的自愈量级来源：`REVIEW_2026_FRONTIER.md:280` 已定位的 Atlantis Press 论文（"小时级 → 28 分钟内"、96% RCA、73% 修复成功率）；或直接以本项目自身的 `false_fix` / `repair_rate` 上报 |
| **ESBMC-AI 具体成功率** | 改用 **GORDIAN**（KLEE 之上的 SMT+LLM，DOI `10.1145/3832126`）或 **ESBMC 综述**（arXiv `2605.26169`）作为形式化验证工具链引用 |
| **"Defects4J v3 不存在"** | **不需要替代——修正为存在**：Defects4J v3.0，854 defects / 17 projects |
| **AutoGPT Devloop** | 项目未引用，无需修正。若需"自动循环式 debug agent"真实替代：**MAGIS**（arXiv `2403.17927`）或 **Agentless**（DOI `10.1145/3715754`，已由 OpenAlex 在本环境返回） |

---

## 5. 逐条可执行更正清单（按文件:行）

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

## 6. 核验结果汇总统计

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

## 7. 扩展轮：`docs/` 全域 arXiv 覆盖 + 项目门禁未决待办核验

> 首轮扫描覆盖 7 份指定文档（71 个 arXiv ID）。为回应"**全部**文献引用"的要求，第二轮把扫描面扩展到整个仓库 `docs/` 与根目录 `*.md`。

### 7.1 `docs/` 全域 arXiv 覆盖：**48 个唯一 ID，48/48 真实，0 缺失**

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

### 7.2 `docs/citation_allowlist.txt` 未决待办逐条闭环

该文件自述"**本清单不是'证明这些引用没问题'，而是'证明它们已被看见'**"，并列出 4 条待办。本轮把其中可核验的条目闭环：

| 待办条目 | 待办内容 | 本轮核验 | 结论 |
|---|---|---|---|
| `docs/adr/0017-repair-engine-pivot.md:14` | "确认 arXiv **2601.18044** 的 **71.4%** 数值在原文中逐位吻合；吻合后移除本条" | `https://arxiv.org/html/2601.18044v1`（HTTP 200，293,761 B）→ 摘要逐字："On SWE-bench Verified, **file-level Hit@1 improves from 71.4% to 85%**, and MRR from 81.8% to 88.8%"；正文 RQ1.1 逐字："for Hit@1, Gemini 2.5 Pro improves from **71.4% to 85%**" | ✅ **逐位吻合，且 ADR 表述"71.4%→85%"完全正确**。arXiv ID 真实、题名正确（RGFL, Sepidband/Taherkhani/Pham/Hemmati, 2026-01-25）。**该行可移除出豁免清单**——注意 `71.4%` 是 **Agentless 基线**（Gemini 2.5 Pro）的值，RGFL 自身的值是 85%；ADR 以区间形式书写，**措辞无误**，但若后续引用为"RGFL 达 71.4%"则属误读 |
| `docs/adr/0028-...:52` | "核验 ADI 的其余数字并补 DOI（PACMSE 2026, DOI 10.1145/3797126 已知）" | `https://api.crossref.org/works/10.1145/3797126` → 200；arXiv `2604.24212` 摘要 | ✅ **该行可闭环移除**：DOI `10.1145/3797126` 真实；63.8% / $1.28/task / Claude-Sonnet-3.7 **三项均逐字命中**；arXiv comment 另证 **"Accepted to FSE 2026"** |
| `docs/adr/0025-...:9` | "一手核验 venue 与数字，或删除该段（ASE 2025：13,866 个测试预言 / mutation 43% vs 人类 45%）" | 未在本次范围（该处**无 DOI/arXiv 标识**，为纯 venue+数字主张） | ⚠️ **仍未能核验**——无标识符可供机读定位。建议补 DOI/arXiv 后再核 |
| `README.en.md:528` | "补数据集/论文出处，或改为'经验观察'并去掉百分比" | 同上（无标识符） | ⚠️ **仍未闭环**，处置建议不变 |

### 7.3 ADR-0017 勘误段的两处"未能定位"名称：一处**已定位**，一处**仍未定位**

ADR-0017 正文自述："此前引用的 **'Hunk-SWE'** 与 **'PSR（四模式 LoRA）'** 两名经第十六轮三轮检索未能定位原文，暂以上述已核验锚点替代"。本轮独立复核：

| 名称 | 核验方法 | 结果 |
|---|---|---|
| **PSR（四模式 LoRA）** | Crossref bibliographic 检索 | ✅ **已定位（建议撤销该勘误）**：*"**Pattern Synergistic Repair: Multi-expert LoRA fusion for automated program repair**"*，**Information and Software Technology**，DOI **`10.1016/j.infsof.2026.108344`**（Elsevier PII `S0950584926003332`，2027-01 卷，在线 2026）。"Multi-expert LoRA fusion" 与 "四模式 LoRA" 语义一致。**可用该一手 DOI 替换"未能定位"表述** |
| **Hunk-SWE** | `web_search` 多轮；`2511.11012` 全文检索 | ❌ **仍未定位**。ADR 原有处置（"未能定位原文"）**正确，予以维持**。**最接近的真实工作**：arXiv **`2511.11012`** 的 **Hunk4J** 数据集（372 个 multi-hunk bugs / 1,488 条修复轨迹），或 UBC 学位论文 *"Agentic Multi-Hunk Repair on SWE-bench Verified"* |

### 7.4 🔴 新增发现 M-15：ADR-0017 引用的多 hunk 数字**未能一手核验**（v1 全文本 0 命中）

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

### 7.5 扩展轮统计增量

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

## 附录 A：完整端点核验日志（可复现）

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
