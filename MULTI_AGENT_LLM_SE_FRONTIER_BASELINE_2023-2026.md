# Multi-Agent LLM Systems for Software Engineering & Testing — Verifiable Frontier Baseline (2023–2026)

**Prepared:** 2026-09-30 (Asia/Shanghai) · **Scope:** multi-agent LLM architectures, empirical critiques, protocols, orchestration, reliability, memory, benchmarks, economics · **Corpus:** 156 cited items — a 121-item pre-2026 core plus 35 rows contributed by two dedicated 2026 verification sweeps (counted directly from the eight topic tables, not estimated). Heavy emphasis on 2024–2026. *Range note:* this exceeds the requested 60–120 aim; the overage is entirely verified 2024–2026 material (rows ≥1.19, ≥2.18, ≥3.17, ≥4.17, ≥5.27, ≥6.17, ≥7.26, ≥8.10). For a hard 120-item cap, delete those 35 rows — the 121-item core is unaffected. Every row carries a verification tag (F/S/K/partial); nothing is padded and nothing is invented.

---

## 0. Method, verification legend, and hard limits (read first)

**Verification legend** (applies to every row):

| Tag | Meaning |
|---|---|
| **F** | The exact URL was **fetched in this session** and its content matched the claim. Strongest evidence here. |
| **S** | The exact URL + matching title/authors were **returned by an in-session search query** (page not fetched). Metadata is corroborated, full text is not. |
| **K** | Canonical source that I could **not re-verify in this session**; URL is given as a lead only. Treat as unconfirmed. |
| **X** | Could not substantiate → **excluded** from the table; listed in §11. |

**Hard limits of this run (stated so you can discount accordingly):**

1. **arXiv was unreachable for most of this run (intermittently reachable later).** `arxiv.org`, `www.arxiv.org`, `export.arxiv.org` timed out for me and for most sub-agents (curl exit 28; `web_fetch` timeout); one later agent did fetch arXiv abs pages successfully, so reachability is flaky rather than absolute. arXiv metadata was therefore verified through mirrors that did load: `ar5iv.labs.arxiv.org/html/<id>` (F), `alphaxiv.org/abs/<id>` (F), ACL Anthology, OpenReview/proceedings pages, or search-result corroboration. Every arXiv URL below is canonical, but most rows are **S**, not **F**.
2. **OpenAlex's arXiv-DOI records are polluted — do not trust them for arXiv.** Example: OpenAlex maps `10.48550/arXiv.2310.06770` to *"GardenBench: A lightweight, daily evaluation of LLM capabilities"*, while arXiv 2310.06770 is **SWE-bench** (confirmed via alphaXiv mirror, F). Same for 2308.08155 (AutoGen) and 2307.13854 (WebArena). Any tool-driven sweep that trusts OpenAlex arXiv DOIs will silently mis-cite. Venue/year for *published* versions (ACL/ICLR/NeurIPS DOIs) from OpenAlex were consistent with proceedings pages.
3. **Venue strings are quoted only when a proceedings/anthology page supports them.** Otherwise the row says `arXiv preprint <id>`.
4. Chinese-language prior art and non-English venues were not systematically searched; coverage is English-language.
5. **Two dedicated 2026 sweeps (6 threads + a 3-thread gap-fill) ran after the core tables were built.** Its returns were adversarially re-verified by a second agent per thread (every URL re-fetched, HTTP 200 confirmed, venue/year corrected against the page). It produced 18 of the 35 sweep rows and four corrections now reflected in the text: A2A v1.0 shipped 2026-03-12; AAIF was founded 2025-12-09; IBM/BeeAI's **ACP is retired into A2A**; and the OTel GenAI conventions moved out of the main semantic-conventions repository. Three of the six threads (2026 SE systems, 2026 benchmarks, 2026 memory/cost) were lost to output truncation and were then re-run as a compact gap-fill, which returned 21 further verified entries (17 integrated as new rows ≥1.19, 6.17, 7.26, 8.10; 4 were duplicates or over its per-thread cap) and explicitly **rejected 6 items** it could not substantiate (Zenodo context-rot PDFs, an aggregator record, a mirror-only URL, and two over-specific venue details).

---

## 1. Topic 1 — Multi-agent LLM architectures for software engineering (role decomposition; planner/coder/tester/reviewer; debate/consensus; hierarchical vs flat)

| # | Work / System | Authors / Institution | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 1.1 | ChatDev | Qian, Liu, Liu, et al. (Tsinghua) | ACL 2024 (long) | 2024 | Chat-chain of designer/coder/tester/reviewer agents with communicative dehallucination for end-to-end software generation | https://aclanthology.org/2024.acl-long.810/ | F |
| 1.2 | MetaGPT | Hong, Zhuge, Chen, et al. (DeepWisdom et al.) | ICLR 2024 (oral); arXiv 2308.00352 | 2024 | Encodes SOPs into role prompts so a multi-agent "software company" emits structured artifacts rather than free chat | https://arxiv.org/abs/2308.00352 | S |
| 1.3 | AutoGen | Wu, Bansal, Zhang, et al. (Microsoft) | COLM 2024; arXiv 2308.08155 | 2024 | Conversable-agent abstraction with programmable conversation topologies (two-agent, group chat, nested) | https://microsoft.github.io/autogen/0.2/docs/Research/ | S |
| 1.4 | CAMEL | Li, Hammoud, Itani, et al. (KAUST) | NeurIPS 2023 | 2023 | Role-playing inception prompting between an AI user and AI assistant yields task-oriented cooperation with minimal human input | https://papers.nips.cc/paper_files/paper/2023/file/a3621ee907def47c1b952ade25c67698-Paper-Conference.pdf | S |
| 1.5 | AgentVerse | Chen, Su, Zuo, et al. | ICLR 2024 | 2024 | Multi-agent team with dynamic composition of expert roles plus evaluation/self-improvement loop | https://openreview.net/forum?id=EHg5GDnyq1 | S |
| 1.6 | AgentCoder | Huang, Zhou, et al. | arXiv 2312.13010 | 2023/24 | Separates programmer / test-designer / test-executor agents so tests are authored independently of the code they judge | https://arxiv.org/abs/2312.13010 | S |
| 1.7 | MAGIS | Tao, Zhou, Wang, et al. | NeurIPS 2024 | 2024 | Manager/ Repository-Custodian/ Quality-Assurance roles for GitHub issue resolution with repository-aware planning | https://proceedings.neurips.cc/paper_files/paper/2024/file/5d1f02132ef51602adf07000ca5b6138-Paper-Conference.pdf | S |
| 1.8 | SWE-agent | Yang, Jimenez, Wettig, et al. (Princeton) | NeurIPS 2024; arXiv 2405.15793 | 2024 | Agent–computer interface (ACI) design, not model choice, drives repository-level repair performance | https://arxiv.org/abs/2405.15793 | S |
| 1.10 | MapCoder | Islam, Ali, Parvez (BUET) | ACL 2024 (long) | 2024 | Four-stage retrieval→planning→coding→debugging agent pipeline for competitive program synthesis | https://aclanthology.org/2024.acl-long.269/ | F |
| 1.11 | Self-Organized Agents (SoA) | Ishihara, Kurahashi, et al. | arXiv 2404.02183 | 2024 | Agents recursively spawn and delegate to sub-agents, scaling generated codebase size without a fixed role script | https://arxiv.org/abs/2404.02183 | S |
| 1.13 | MaCTG | (ICSE 2026 authors) | ICSE 2026 Research Track | 2026 | Multi-agent collaborative thought graph for automatic programming; 2026 peer-reviewed continuation of the role-graph line | https://conf.researchr.org/details/icse-2026/icse-2026-research-track/179/MaCTG-Multi-Agent-Collaborative-Thought-Graph-for-Automatic-Programming | S |
| 1.14 | Multi-Agent Debate ("Improving Factuality and Reasoning…") | Du, Li, Torralba, Tenenbaum, Mordatch (MIT/Google) | ICML 2024; arXiv 2305.14325 | 2024 | Multiple LLM instances debate over rounds; consensus answer improves factuality/reasoning vs single sample | https://arxiv.org/abs/2305.14325 | S |
| 1.15 | DyLAN (Dynamic LLM-Agent Network) | Liu, Chen, et al. | ICLR 2024 | 2024 | Learns a task-specific agent team and communication topology at inference time instead of a fixed flat team | https://openreview.net/forum?id=i43XCU54Br | S |
| 1.16 | GPTSwarm | Zhuge, Wang, Kirsch, Faccio, Khizbullin, Schmidhuber | ICML 2024; arXiv 2402.16823 | 2024 | Represents an agent system as an optimizable computation graph whose edges/nodes are trained by feedback | https://ar5iv.labs.arxiv.org/html/2402.16823 | F |
| 1.17 | MacNet (Scaling LLM-based Multi-Agent Collaboration) | Qian, Wang, et al. | ICLR 2025 | 2025 | Collaborative scaling law: densely connected agent networks can follow power-law/emergent gains as agent count grows | https://proceedings.iclr.cc/paper_files/paper/2025/hash/66a026c0d17040889b50f0dfa650e5e0-Abstract-Conference.html | S |
| 1.18 | AFlow | Zhang, Xiang, et al. | ICLR 2025 (oral) | 2025 | Monte-Carlo tree search over code-represented agent workflows automates workflow generation instead of hand-design | https://www.iclr.cc/virtual/2025/oral/31731 | S |

| 1.19 | TraceCoder | Huang, Ye, Sun, Zhang, Zhang, Liu (CQUPT / NTU / BUAA / Southwest Univ.) | ICSE 2026 Research Track, DOI 10.1145/3744916.3773187; arXiv 2602.06875 | 2026 | Three agents (Instrumentation, Analysis, Repair) debug LLM-generated code using runtime traces plus learned historical lessons; up to 34.43% relative Pass@1 gain | https://www.alphaxiv.org/abs/2602.06875 | F |
| 1.20 | TestAgent | Shang, Zhang, Zhan, Huang, Fang, Chen (Nanjing Univ. / NJUST) | FSE 2026 Tool Demonstrations | 2026 | Planner / Generator / Reviewer agents over repository code knowledge graphs; reports 92.34% line coverage for repository-level unit-test generation | https://conf.researchr.org/details/fse-2026/fse-2026-demonstrations/30/TestAgent-A-Multi-Agent-LLM-Framework-for-Repository-Level-Unit-Test-Generation | F |
| 1.21 | Test vs Mutant | Chang, Fang, Chen, Shi, Shen, Gu (Shanghai Jiao Tong Univ.) | ISSTA 2026 Research Papers (program marked tentative) | 2026 | Adversarial test-generation and mutant-generation agents co-evolve; 8.56% higher fault detection than the best LLM baselines | https://conf.researchr.org/details/issta-2026/issta-2026-research-papers/31/Test-vs-Mutant-Adversarial-LLM-Agents-for-Robust-Unit-Test-Generation | F |
| 1.22 | AgentConductor | Wang, Lu, Yang, Wang, Zhang, Xu, Xu, Yin, Chen, Guan (SJTU / Meituan) | arXiv 2602.17100 (unreviewed) | 2026 | An RL orchestrator infers agent roles and builds density-aware layered DAG topologies per task; pass@1 up to +14.6% | https://www.alphaxiv.org/abs/2602.17100 | F |
| 1.23 | AdaptOrch | Geunbin Yu (single author; no affiliation stated) | arXiv 2602.16873 (unreviewed; provenance unauditable) | 2026 | Routes task DAGs to parallel / sequential / hierarchical / hybrid topologies; up to 23% over static baselines — treat numbers as unrefereed | https://www.alphaxiv.org/abs/2602.16873 | partial |
| 1.24 | Cursor Projects + Devin Fusion (industry topology split) | Anysphere (Cursor) changelog 2026-09-10; Cognition blog 2026-06-29 | Vendor changelogs/blogs | 2026 | Cursor ships a coordinator agent that plans and delegates without writing code; Cognition's Fusion pairs a frontier main agent with cheaper parallel sidekicks for a self-reported up-to-60% cost cut | https://cursor.com/changelog/projects | F |

**Reading of Topic 1.** Three distinct architectural bets coexist: (a) **role/SOP pipelines** (ChatDev, MetaGPT, MAGIS, MapCoder) where the win is claimed to come from decomposition and artifact contracts; (b) **learned/optimized topology** (DyLAN, GPTSwarm, AFlow, MacNet) where the structure itself is the object of optimization; (c) **agent–computer interface / scaffold** work (SWE-agent) where decomposition matters less than the tool+context interface. Only (c) and parts of (a) have independently reproduced, head-to-head wins against strong single-agent scaffolds on SWE-bench-style benchmarks; see Topic 2.

---

## 2. Topic 2 — Empirical and critical studies: do multi-agent LLM systems actually beat single-agent baselines?

| # | Work / Study | Authors / Institution | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 2.1 | **MAST / "Why Do Multi-Agent LLM Systems Fail?"** | Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein, Ramchandran, Zaharia, Gonzalez, Stoica (UC Berkeley et al.) | NeurIPS 2025 Datasets & Benchmarks; arXiv 2503.13657 | 2025 | 1,600+ annotated traces across 7 MAS frameworks → 14 failure modes in 3 categories (design, inter-agent misalignment, task verification), κ=0.88; MAS gains on popular benchmarks "are often minimal" | https://papers.nips.cc/paper_files/paper/2025/file/b1041e52d3be19f0a9bc491657488e4a-Paper-Datasets_and_Benchmarks_Track.pdf | F |
| 2.2 | AgentBench | Liu, Yu, Zhang, et al. (Tsinghua) | ICLR 2024; arXiv 2308.03688 | 2024 | First broad multi-environment benchmark for LLM-as-agent; exposes large gap between chat ability and agentic ability | https://arxiv.org/abs/2308.03688 | S |
| 2.3 | More Agents Is All You Need | Li, Zhang, Yu, Fu, Ye (Tencent) | TMLR; arXiv 2402.05120 | 2024 | Sampling-and-voting alone yields monotone gains with agent count; gains correlate with task difficulty, not collaboration structure | https://arxiv.org/abs/2402.05120 | S |
| 2.4 | Should we be going MAD? | Smit, Grinsztajn, Duckworth, Barrett, Pretorius (InstaDeep) | ICML 2024; arXiv 2311.17371 | 2024 | Systematic comparison of multi-agent debate strategies finds no consistent winner over simpler baselines across tasks/budgets | https://arxiv.org/abs/2311.17371 | S |
| 2.5 | Are More LLM Calls All You Need? | Chen, Davis, et al. | arXiv 2410.13828 | 2024 | Scaling laws for compound inference systems: accuracy is often predicted by total calls/architecture-independent budget | https://www.semanticscholar.org/paper/5e3286e57b3aedce35c2eeb7b8ecf40d1bcb2198 | S |
| 2.6 | LLMs Cannot Self-Correct Reasoning Yet | Huang, Chen, Mishra, et al. (Google DeepMind / UIUC) | ICLR 2024; arXiv 2310.01798 | 2024 | Intrinsic self-correction without external feedback degrades reasoning accuracy — a direct caution for "reviewer/critic" agents | https://arxiv.org/abs/2310.01798 | S |
| 2.8 | **Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets** | Tran, Kiela, et al. | arXiv 2604.02460 | 2026 | Under matched thinking-token budgets, single-agent configurations match or beat multi-agent ones — attribution of gains to MAS structure fails | https://arxiv.org/abs/2604.02460 | S |
| 2.9 | At Equal Inference Cost, Multi-Agent Structure Does Not Beat a Single Frozen Agent (MA-Evolve) | Dylan, Brennan, Murphy, O'Sullivan, Kelly, Walsh | arXiv 2609.04217 | 2026 | At a fixed model-call budget an evolved Planner-Executor-Critic team scores 0.769 vs 0.754 for a single evolved executor on ALFWorld (p=0.80); WebShop also null | https://www.alphaxiv.org/abs/2609.04217 | F |
| 2.10 | More with Less: Turn-Control Strategies for Efficient Coding Agents | (see arXiv listing) | arXiv 2510.16786 | 2025 | Empirical turn-budget study: controlling turns/interaction dominates adding agents for cost-efficient coding agents | https://arxiv.org/pdf/2510.16786 | S |
| 2.11 | How we built our multi-agent research system | Hadfield, Zhang, Lien, Scholz, Fox, Ford (Anthropic) | Anthropic Engineering blog, 2025-06-13 | 2025 | Multi-agent Research (Opus 4 lead + Sonnet 4 subagents) beat single-agent Opus 4 by 90.2% while using ~15× chat tokens; token use explained 80% of BrowseComp variance | https://www.anthropic.com/engineering/multi-agent-research-system | F |
| 2.12 | Multi-Agents: What's Actually Working (follow-up to "Don't Build Multi-Agents") | Walden Yan (Cognition) | Cognition blog, 2026-04-22 | 2026 | Clean-context Devin Review loop catches ~2 bugs per PR (~58% severe) with no shared context; unstructured swarms called "mostly a distraction" | https://cognition.com/blog/multi-agents-working | F |
| 2.13 | Multi-Agent Collaboration Mechanisms: A Survey of LLMs | Tran, Dao, Nguyen, et al. | arXiv 2501.06322 | 2025 | Taxonomy of collaboration dimensions (actors, types, structures, strategies, coordination) and open failure/challenge list | https://arxiv.org/abs/2501.06322 | S |
| 2.14 | LLM-Based Multi-Agent Systems for SE: Literature Review, Vision, Road Ahead | He, Treude, et al. | TOSEM; arXiv 2404.04834 | 2024/25 | SE-specific MAS survey: maps agent roles across the SE lifecycle and flags evaluation immaturity | https://arxiv.org/abs/2404.04834 | S |
| 2.17 | Large Language Model Based Multi-Agents: A Survey of Progress and Challenges | Guo, Chen, Wang, Chang, Pei, Chawla, Wiest, Zhang | IJCAI 2024, DOI 10.24963/ijcai.2024/890 | 2024 | Reference IJCAI survey defining the MAS design space (agent profiles, communication, capability growth) and its open challenges | https://www.ijcai.org/proceedings/2024/890 | S |

| 2.18 | The Verifier Tax | Sah, Srivastava, Sah, Jordan (Harrisburg / Johns Hopkins / Utah) | arXiv 2603.19328 | 2026 | Planner+verifier roles inflate τ-bench tokens 2.0–2.8× and calls 1.6–2.2× and intercept up to 94% of violations, yet safe success stays below 5% | https://www.alphaxiv.org/abs/2603.19328 | F |
| 2.19 | Towards a Science of AI Agent Reliability | Rabanser, Kapoor, Kirgis, Liu, Utpala, Narayanan (Princeton) | ICML 2026; arXiv 2602.16666 | 2026 | Twelve reliability metrics across 15 models show 24 months of capability gains produced only small reliability improvements | https://www.alphaxiv.org/abs/2602.16666 | F |
| 2.20 | OrchestraBench | Chen, Gu, Vidra, Setty, Zheng | arXiv 2608.05263 | 2026 | Injected MAST-style faults in planner-worker chains: tool faults recover fully (1.0), ambiguous delegation 0.30, latent modes 0.0; cascade radius grows 0.9→4.7 with depth | https://www.alphaxiv.org/abs/2608.05263 | F |
| 2.21 | Governance Decay / ConstraintRot | Shiyang Chen (Beijing Institute of Technology) | arXiv 2606.22528 v2 | 2026 | Context compaction raises prohibited tool-action violations from 0% to 30% (59% worst model); pinning the constraint restores 0% at <0.5% overhead | https://arxiv.org/abs/2606.22528 | F |
| 2.22 | Where Does Agent Reliability Come From? | Dastidar (Leni team) | arXiv 2607.17044 | 2026 | A production enterprise agent beats its frontier base model by +11.0 points on SpreadsheetBench Verified, but the verification loop alone adds only +1.5 | https://www.alphaxiv.org/abs/2607.17044 | F |
| 2.23 | PropUQ-MAS | Liu, Liu, Zhang, Yao, Li, Wang | EMNLP 2026 Main; arXiv 2608.22130 | 2026 | Models MAS execution as a communication DAG; propagation-aware uncertainty reports +6.10% AUROC / +47.58% PRR average relative gains | https://www.alphaxiv.org/abs/2608.22130 | F |
| 2.24 | Scaling long-running autonomous coding | Wilson Lin (Cursor / Anysphere) | Cursor research blog, 2026-01-14 | 2026 | Hundreds of planner/worker agents wrote 1M+ lines across ~1,000 files in about a week; twenty self-coordinating agents slowed to the throughput of two or three | https://cursor.com/blog/scaling-agents | F |

**Reading of Topic 2.** The critical literature now converges on a **methodological indictment**, not merely a performance one: gains attributed to "collaboration" mostly dissolve under (i) equal-token/equal-cost controls (2.3, 2.5, 2.8, 2.9, 2.10), (ii) external-feedback ablations (2.6), and (iii) trajectory-level failure analysis (2.1). The strongest surviving claim for MAS is *organizational*: MAST shows the same model produces different failure profiles under different topologies, so architecture changes where failures occur, not whether the system is cheap.

---

## 3. Topic 3 — Communication protocols and standards

| # | Work / Standard | Authors / Org | Venue / Org | Year (revision) | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 3.1 | **MCP specification 2026-07-28** | Anthropic-originated; now Linux Foundation / AAIF governance | modelcontextprotocol.io | 2026 | Makes MCP **stateless**: removes `initialize` handshake and `Mcp-Session-Id`, adds `server/discover`, Multi-Round-Trip Requests, `ttlMs`/`cacheScope` caching hints, OTel `_meta` trace propagation | https://modelcontextprotocol.io/specification/2026-07-28/changelog | F |
| 3.2 | MCP specification 2025-11-25 | MCP project (Linux Foundation series) | modelcontextprotocol.io | 2025 | Adds OAuth Client ID Metadata Documents, URL-mode elicitation, sampling tool-calling and experimental tasks with polling; JSON Schema 2020-12 becomes the default dialect | https://modelcontextprotocol.io/specification/2025-11-25/changelog | F |
| 3.3 | MCP Registry + extensions/SEPs | MCP maintainers | modelcontextprotocol.io | 2026 | Server discovery registry and an extension mechanism (`extensions` capability) beyond the core protocol | https://modelcontextprotocol.io/registry/about | F |
| 3.4 | **Agentic AI Foundation (AAIF)** | Linux Foundation; founding contributions from Anthropic (MCP), Block (goose), OpenAI (AGENTS.md) | aaif.io press release, 2025-12-09 | 2025 | Foundation launched 9 Dec 2025 to host MCP, goose and AGENTS.md; platinum members include AWS, Anthropic, Block, Bloomberg, Cloudflare, Google, Microsoft, OpenAI | https://aaif.io/news/linux-foundation-announces-formation-of-aaif | F |
| 3.5 | **A2A Protocol v1.0** | A2A project / Linux Foundation (TSC: AWS, Cisco, Google, IBM Research, Microsoft, Salesforce, SAP, ServiceNow) | a2a-protocol.org blog, 2026-03-12 | 2026 | First stable release: JSON-RPC + gRPC + HTTP+JSON bindings with equivalence guarantees, per-interface versioning, tenant fields, JWS-signed Agent Cards | https://a2a-protocol.org/v1.0.1/whats-new-v1/ | F |
| 3.6 | A2A donation to the Linux Foundation | Google Cloud | developers.googleblog.com | 2025 | Transfers A2A governance to a neutral foundation to avoid single-vendor control of agent interop | https://developers.googleblog.com/en/google-cloud-donates-a2a-to-linux-foundation/ | S |
| 3.7 | AGNTCY "Internet of Agents" | Cisco Outshift → Linux Foundation | outshift.cisco.com / news-blogs.cisco.com | 2025 | Open agent-interop stack (identity, discovery, messaging) donated to the Linux Foundation | https://outshift.cisco.com/blog/ai-ml/building-the-internet-of-agents-introducing-the-agntcy | F |
| 3.8 | ACP (Agent Communication Protocol) — retired into A2A | IBM / BeeAI (i-am-bee) | agentcommunicationprotocol.dev | 2025 | Official ACP docs now carry the banner "ACP is now part of A2A under the Linux Foundation!"; IBM's protocol merged into A2A in Aug 2025 (note: OpenAI's unrelated Agentic Commerce Protocol is also abbreviated ACP) | https://agentcommunicationprotocol.dev/introduction/welcome.md | F |
| 3.9 | Function calling (Tools API) | OpenAI | platform.openai.com docs | 2023 | Turns model output into JSON tool invocations — the de-facto substrate every later agent protocol wraps | https://platform.openai.com/docs/guides/function-calling | K |
| 3.10 | Structured Outputs (JSON Schema) | OpenAI | developers.openai.com docs | 2024–26 | Constrained decoding against a supplied JSON Schema guarantees schema-valid tool arguments — the typed-message primitive under agent protocols | https://developers.openai.com/api/docs/guides/structured-outputs | S |
| 3.12 | ToolLLM / ToolBench | Qin, Liang, et al. | ICLR 2024 | 2024 | 16k+ real REST APIs with DFSDT search over tool-call trajectories; exposes poor generalization to unseen APIs | https://proceedings.iclr.cc/paper_files/paper/2024/hash/28e50ee5b72e90b50e7196fde8ea260e-Abstract-Conference.html | S |
| 3.13 | Berkeley Function-Calling Leaderboard (BFCL) | Gorilla team, UC Berkeley | gorilla.cs.berkeley.edu | 2024–26 | Live, AST/execution-checked leaderboard for tool-call correctness, now including multi-turn and agentic variants | https://gorilla.cs.berkeley.edu/leaderboard.html | S |
| 3.16 | Systematic Analysis of MCP Security | (see arXiv listing) | arXiv 2508.12538 | 2025 | Systematic study of MCP server/tool attack surface and mitigations; complements the 2026 CVE-counting literature | https://arxiv.org/abs/2508.12538 | S |

| 3.17 | MCP Apps (first official MCP extension) | MCP core maintainers, with OpenAI and MCP-UI | blog.modelcontextprotocol.io, 2026-01-26 | 2026 | Tools point via `_meta.ui.resourceUri` at `ui://` resources rendered in sandboxed iframes with bidirectional JSON-RPC — UI becomes a protocol-level extension | https://blog.modelcontextprotocol.io/posts/2026-01-26-mcp-apps/ | F |
| 3.18 | A2A joins AAIF | A2A project / Agentic AI Foundation | aaif.io blog, 2026-08-17 | 2026 | A2A accepted as a Growth Stage AAIF project, so MCP + A2A + goose + AGENTS.md + agentgateway sit under one foundation | https://aaif.io/blog/a2a-joins-aaif | F |
| 3.19 | MCP authorization security considerations (2026-07-28) | MCP project | modelcontextprotocol.io | 2026 | Requires OAuth 2.1 §7 practices, PKCE, RFC 8707 resource parameter with token-audience validation, and RFC 9207 `iss` validation | https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations | F |
| 3.20 | UTCP 1.0.0 (Universal Tool Calling Protocol) | Radulescu / UTCP contributors | utcp.io RFC (Status: Draft) | 2025 | Draft RFC letting clients call tools over native transports (http, gRPC, GraphQL, CLI, MCP) via an embedded `tool_transport`, avoiding wrapper servers | https://www.utcp.io/about/RFC | F |

**Reading of Topic 3.** Two 2025–2026 shifts matter for SE/testing tooling: (i) **governance neutralization** (MCP, A2A, AGNTCY moved under Linux Foundation/AAIF), and (ii) **statelessness + cacheability** in MCP 2026-07-28 (explicit `ttlMs`/`cacheScope`, deterministic tool ordering "to improve LLM prompt cache hit rates", OTel trace context in `_meta`). Any 2026 agent platform claiming MCP support must state which revision it implements; the 2026-07-28 revision is wire-incompatible with the 2025-06-18 session model.

---

## 4. Topic 4 — Orchestration frameworks, state machines, durable execution

| # | Work / Framework | Authors / Org | Venue / Org | Year | One-line claim (mechanism) | URL | V |
|---|---|---|---|---|---|---|---|
| 4.1 | LangGraph — interrupts | LangChain | docs.langchain.com | 2024–26 | Human-in-the-loop `interrupt()` pauses a graph at a node and resumes with human-provided state | https://docs.langchain.com/oss/python/langgraph/interrupts | S |
| 4.2 | LangGraph — checkpointers | LangChain | docs.langchain.com | 2024–26 | Per-super-step state persistence enabling resume, time-travel and fault recovery | https://docs.langchain.com/oss/javascript/langgraph/checkpointers | S |
| 4.5 | AG2 (community fork) | AG2 community (ex-AutoGen contributors) | ag2.ai | 2025–26 | Community continuation of the AutoGen 0.2 API line, with group-chat patterns and tool execution | https://ag2.ai/ | K |
| 4.6 | CrewAI | CrewAI Inc. | docs.crewai.com | 2024–26 | Role/task "crew" abstraction plus deterministic Flows for stateful orchestration | https://docs.crewai.com/v1.15.23/en/introduction | S |
| 4.7 | OpenAI Agents SDK | OpenAI | developers.openai.com | 2025–26 | Minimal primitives — agents, handoffs, guardrails, sessions, tracing — with a provider-agnostic loop | https://developers.openai.com/api/docs/guides/agents/define-agents | S |
| 4.9 | LlamaIndex Workflows | LlamaIndex | docs.llamaindex.ai / GitHub | 2024–26 | Event-driven `step` functions with typed events — agents as explicit state machines rather than loops | https://github.com/run-llama/llama-agents/blob/d2179613c36b4e5491ca2dae6286534414202b44/docs/docs/module_guides/workflow/index.md | S |
| 4.10 | Semantic Kernel — agent orchestration | Microsoft | learn.microsoft.com | 2024–26 | Enterprise orchestration patterns (sequential, concurrent, group chat, handoff, magentic) over SK agents | https://learn.microsoft.com/semantic-kernel/Frameworks/agent/agent-orchestration/ | S |
| 4.11 | Temporal — durable execution | Temporal Technologies | docs.temporal.io | 2020–26 | Event-history replay deterministically reconstructs workflow state after failure — the reference model for agent checkpointing | https://docs.temporal.io/workflow-execution | S |
| 4.12 | Temporal — event history | Temporal Technologies | docs.temporal.io | 2020–26 | Append-only history is the durable log from which all state is rederived (basis of deterministic replay) | https://docs.temporal.io/encyclopedia/event-history/ | S |
| 4.13 | DBOS — durable execution for AI agents | DBOS Inc. | dbos.dev | 2025–26 | Postgres-backed workflow durability targeted at crashproof agent loops (step-level retry/idempotency) | https://www.dbos.dev/blog/durable-execution-crashproof-ai-agents | S |
| 4.14 | Google ADK (Agent Development Kit) | Google | Google Cloud docs | 2025–26 | Code-first agent framework with explicit workflow agents (sequential/parallel/loop) and session state | https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/create-an-adk-agent | S |
| 4.15 | Kubernetes Agent Sandbox (kubernetes-sigs) | Kubernetes SIG Apps | agent-sandbox.sigs.k8s.io | 2026 | `Sandbox` CRD (`agents.x-k8s.io/v1beta1`) gives agents a stateful singleton pod with stable hostname, persistent storage and pause/resume, delegating isolation to gVisor/Kata via RuntimeClass | https://agent-sandbox.sigs.k8s.io/docs/getting_started/overview/ | F |

| 4.17 | LangGraph per-node fault tolerance (langgraph ≥1.2) | LangChain / LangGraph team | docs.langchain.com | 2026 | Per-node `TimeoutPolicy` (hard `run_timeout` + `idle_timeout` reset by `runtime.heartbeat()`), typed `NodeError` handlers with `Command` routing, and checkpointed `request_drain()` resume | https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md | F |
| 4.18 | Temporal × LangChain Deep Agents | Temporal Technologies | temporal.io blog, 2026-08-27 | 2026 | Wraps every Deep Agents model and tool call in a Temporal Activity so the loop is a deterministic, replayable Workflow that resumes after a crash (plugin Pre-Release) | https://temporal.io/blog/durable-digest-august-2026 | F |
| 4.19 | Restate durable agents | Restate | docs.restate.dev | 2026 | `ctx.run()` steps are journaled: on crash the handler replays completed steps without re-calling the LLM or duplicating tool side effects (LangChain middleware does not auto-journal tools) | https://docs.restate.dev/ai/patterns/durable-agents.md | F |
| 4.20 | Amazon Bedrock AgentCore | Amazon Web Services | AWS developer guide | 2026 | Harness runs each session in an isolated microVM with filesystem/shell; Policy (Cedar-compatible Dogwood) intercepts every Gateway tool call; Observability emits OTel | https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html | F |
| 4.21 | Cloudflare Sandboxes (OpenAI Agents SDK backend) | Cloudflare | developers.cloudflare.com | 2026 | SandboxAgent/CloudflareSandboxClient execute agent code in isolated containers behind a sandbox-bridge Worker; documented under Sandbox SDK 0.x (migration path to 1.0) | https://developers.cloudflare.com/sandbox/sdk/tutorials/openai-agents/ | F(partial) |

**Reading of Topic 4.** The field split into two idioms that are converging: **graph/state-machine DSLs** (LangGraph, LlamaIndex Workflows, SK patterns, ADK workflow agents) and **durable-execution runtimes** borrowed from distributed systems (Temporal, DBOS, Restate, Step Functions). The 2025–26 differentiator is no longer "multi-agent support" but **replayability**: checkpoint/interrupt semantics, idempotent steps, and per-invocation isolation. Frameworks that cannot deterministically replay a run cannot be regression-tested (see Topic 5).

---

## 5. Topic 5 — Reliability engineering for agents: guardrails, sandboxing, observability, judge reliability, replay

| # | Work / Standard | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 5.1 | NeMo Guardrails | Rebedea, Dinu, Sreedhar, Parisien, Cohen (NVIDIA) | EMNLP 2023 System Demos | 2023 | Programmable "rails" (Colang) that constrain dialogue/tool use at runtime rather than by prompt alone | https://aclanthology.org/2023.emnlp-demo.40/ | S |
| 5.2 | Llama Guard | Inan, Upasani, Chi, et al. (Meta) | arXiv 2312.06674 | 2023 | LLM-based input/output safety classifier used as a guardrail model in front of/behind an agent | https://arxiv.org/abs/2312.06674 | S |
| 5.3 | OWASP Top 10 for LLM Applications 2025 | OWASP GenAI Security Project | genai.owasp.org | 2025 | Community risk list (LLM01 prompt injection first) used as the default threat model for tool-using agents | https://genai.owasp.org/download/48828/ | S |
| 5.4 | OWASP AIVSS — Agentic AI Core Security Risks v0.5 | OWASP AIVSS project | aivss.owasp.org | 2025–26 | Scoring system for agent-specific risks (tool misuse, supply chain, untraceability, goal manipulation) | https://aivss.owasp.org/assets/publications/AIVSS%20Scoring%20System%20For%20OWASP%20Agentic%20AI%20Core%20Security%20Risks%20v0.5.pdf | S |
| 5.5 | Agentic AI: Emerging Threats, Mitigations and Challenges | NIST CSRC (Sotiropoulos) | csrc.nist.gov presentation | 2026 | Government-side taxonomy of agentic threats incl. tool abuse and privilege escalation | https://csrc.nist.gov/csrc/media/presentations/2026/agentic-ai-emerging-threats%2C-mitigations%2C-and-cha/1.3-agentic_ai-sotiropoulos.pdf | S |
| 5.6 | gVisor security model | Google | gvisor.dev docs | 2018–26 | User-space application kernel intercepts syscalls, shrinking the host-kernel attack surface for untrusted code | https://gvisor.dev/docs/architecture_guide/security/ | S |
| 5.7 | Firecracker microVMs | Agache, Brooker, Iordache, Liguori, Neugebauer, Piwonka, Popa (AWS) | USENIX NSDI 2020 | 2020 | KVM-based microVMs give VM-grade isolation at ~125 ms boot, the substrate for most serverless code sandboxes | https://dl.acm.org/doi/abs/10.5555/3388242.3388273 | S |
| 5.8 | E2B sandboxes | E2B (Foundry Labs) | docs.e2b.dev | 2024–26 | Firecracker-backed ephemeral sandboxes purpose-built for LLM-generated code execution | https://docs.e2b.dev/ | S |
| 5.9 | Daytona | Daytona Platforms | daytona.io docs | 2025–26 | Sub-90 ms stateful sandboxes for agent workloads with snapshot/branch semantics | https://www.daytona.io/docs/ | S |
| 5.10 | Docker default seccomp profile | Docker | docs.docker.com | 2016–26 | Allow-list syscall filtering that blocks ~44 syscalls by default — the baseline container hardening for CI-run agent code | https://docs.docker.com/engine/security/seccomp/ | S |
| 5.11 | AgentDojo | Debenedetti, Zhang, Balunović, et al. (ETH Zürich / Google) | NeurIPS 2024 Datasets & Benchmarks | 2024 | Dynamic benchmark of 97 realistic tool tasks with prompt-injection attacks and defenses, incl. security-vs-utility tradeoff | https://papers.neurips.cc/paper_files/paper/2024/hash/97091a5177d8dc64b1da8bf3e1f6fb54-Abstract-Datasets_and_Benchmarks_Track.html | S |
| 5.12 | InjecAgent | Zhan, Liang, Ying, Kang (UIUC) | ACL 2024 Findings | 2024 | 1,054 indirect prompt-injection cases against tool-integrated agents; ReAct agents are highly susceptible | https://aclanthology.org/2024.findings-acl.624/ | S |
| 5.14 | CaMeL (Defeating Prompt Injections by Design) | Debenedetti, Shumailov, Fan, Hayes, Carlini, Fabian, et al. (Google DeepMind / ETH) | arXiv 2503.18813 | 2025 | Dual-LLM capability-based design that provably blocks control-flow hijack by untrusted data | https://ui.adsabs.harvard.edu/abs/2025arXiv250318813D/abstract | S |
| 5.15 | Design Patterns for Securing LLM Agents against Prompt Injections | Beurer-Kellner, Debenedetti, et al. | arXiv 2506.08837 | 2025 | Six named patterns (action-selector, plan-then-execute, dual LLM, code-then-execute, context-minimization, map-reduce) with explicit utility costs | https://huggingface.co/papers/2506.08837 | S |
| 5.16 | OpenTelemetry GenAI semantic conventions — agent spans | OpenTelemetry Semantic Conventions WG | opentelemetry.io | 2024–26 | Standard span/attribute schema (`gen_ai.*`) for LLM, tool and agent invocations — vendor-neutral tracing substrate | https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/ | S |
| 5.17 | OpenLLMetry (Traceloop) | Traceloop | GitHub / traceloop.com | 2023–26 | OTel-based auto-instrumentation for LLM frameworks, exporting GenAI spans to any OTel backend | https://www.traceloop.com/blog/the-specialized-llm-observability-platform-built-on-opentelemetry-traceloop | S |
| 5.18 | Langfuse | Langfuse GmbH | langfuse.com | 2023–26 | Open-source tracing/eval/dataset platform with trace-level scoring and prompt versioning | https://langfuse.com/docs | S |
| 5.19 | Arize Phoenix | Arize AI | arize.com/docs | 2023–26 | Open-source OTel-native tracing + LLM/code evaluators for regression-style eval loops | https://arize.com/docs/phoenix/get-started/ts-get-started-evaluations | S |
| 5.20 | AgentOps: Enabling Observability of LLM Agents | Dong, Lu, et al. | arXiv 2411.05285 | 2024 | Taxonomy of agent-observability artifacts (session, agent, tool, LLM, error spans) and replay requirements | https://arxiv.org/abs/2411.05285 | S |
| 5.21 | Judging LLM-as-a-Judge with MT-Bench & Chatbot Arena | Zheng, Chiang, Sheng, et al. (UC Berkeley) | NeurIPS 2023 Datasets & Benchmarks; arXiv 2306.05685 | 2023 | Establishes LLM judges reach ~80% human agreement and names position/verbosity/self-enhancement biases | https://arxiv.org/abs/2306.05685 | S |
| 5.22 | Large Language Models are not Fair Evaluators | Wang, Li, Chen, Zhu, Lin, Cao, Liu | ACL 2024; arXiv 2305.17926 | 2024 | Judge verdicts flip with answer order; calibration/multi-evidence prompting mitigates but does not remove bias | https://arxiv.org/abs/2305.17926 | K |
| 5.23 | JudgeBench | Tan, Zhuang, et al. | ICLR 2025; arXiv 2410.12784 | 2025 | Hard pairwise judging benchmark showing strong models near chance on objectively verifiable difficult pairs | https://proceedings.iclr.cc/paper_files/paper/2025/hash/9e720fce64f91114c49cfd640d821da3-Abstract-Conference.html | S |
| 5.26 | Who Validates the Validators? | Shankar, Zamfirescu-Pereira, Hartmann, Parameswaran, Arawjo | arXiv 2404.12272 (UIST 2024) | 2024 | Proposes eval-driven development with criteria drift control; shows naive LLM criteria generation misaligns with human intent | https://huggingface.co/papers/2404.12272 | S |

| 5.27 | OpenTelemetry GenAI conventions — 2026 status | OpenTelemetry GenAI SIG | opentelemetry.io blog (2026) + docs | 2026 | Agent telemetry modeled as top-level `invoke_agent` with child `chat`/`execute_tool` spans; content capture off by default; still no stability declaration, and the conventions moved out of the main semconv repo | https://opentelemetry.io/blog/2026/genai-observability/index.md | F |
| 5.28 | Prior Beliefs Prejudice LLM-as-Judge | Zahraei, Wang, Bozdag, Tur, Hakkani-Tür | Findings of ACL 2026, pp. 42049–42082 | 2026 | Judges rated belief-aligned bare assertions above well-crafted counter-arguments; belief-conditioned inflation caused 88% of identified failure modes (ConvinceQA, 27,756 arguments) | https://aclanthology.org/2026.findings-acl.2087/ | F |

**Reading of Topic 5.** Four load-bearing conclusions: (1) **prompt injection is not solved** — the credible 2024–25 line is architectural isolation (CaMeL, design patterns, AgentDojo/InjecAgent measurements), not filters; (2) **sandboxing has standardized** on microVM-class isolation (Firecracker/gVisor/E2B/Daytona) with seccomp as the floor; (3) **observability converged on OTel GenAI semantic conventions**, which is what makes trace-based regression testing portable; (4) **LLM-as-judge is usable only with bias controls and calibration** (position bias is the single most replicated defect). Deterministic replay is the missing primitive: only durable-execution runtimes (Topic 4) provide event-history replay; ad-hoc agent loops are not replayable, hence not regressable.

---

## 6. Topic 6 — Memory, RAG for code, context engineering, long-context degradation

| # | Work / System | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 6.1 | MemGPT | Packer, Wooders, Lin, Fang, Patil, Stoica, Gonzalez (UC Berkeley) | arXiv 2310.08560 | 2023 | Treats the context window as RAM with paging between main context and external storage — the canonical agent-memory abstraction | https://arxiv.org/abs/2310.08560 | S |
| 6.2 | LongMemEval | Wu, Wang, et al. | ICLR 2025; arXiv 2410.10813 | 2025 | 500-question benchmark over 5 long-term memory abilities (extraction, multi-session reasoning, temporal, knowledge update, abstention) | https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html | S |
| 6.3 | LoCoMo | Maharana, Lee, Tulyakov, Bansal, Barbieri, Fang | ACL 2024 (long); arXiv 2402.17753 | 2024 | Very-long-term (up to 35 sessions) conversational memory benchmark with QA and event-graph tasks | https://aclanthology.org/2024.acl-long.747/ | S |
| 6.4 | Lost in the Middle | Liu, Lin, Hewitt, Paranjape, Bevilacqua, Petroni, Liang | TACL 2024; arXiv 2307.03172 | 2024 | Retrieval-augmented accuracy is U-shaped in position: evidence placed mid-context is used least | https://aclanthology.org/2024.tacl-1.9/ | F |
| 6.5 | RULER | Hsieh, Sun, et al. (NVIDIA) | arXiv 2404.06654 | 2024 | Synthetic long-context suite showing effective context is far below advertised lengths for most models | https://arxiv.org/abs/2404.06654 | S |
| 6.6 | NoLiMa | Modarressi, Deilamsalehy, et al. | ICML 2025; arXiv 2502.05167 | 2025 | Removes literal overlap between question and needle; most models fall to ~50% of their short-context score by 32k | https://arxiv.org/abs/2502.05167 | S |
| 6.7 | Context Rot (Chroma technical report) | Hong, Troynikov, Huber (Chroma) | research.trychroma.com | 2025 | Input-length alone degrades performance on controlled tasks even when the task is trivially simple — "context rot" | https://research.trychroma.com/context-rot | K |
| 6.8 | A-MEM | Xu, Liang, et al. | arXiv 2502.12110 | 2025 | Agentic memory that dynamically links and evolves note structures (Zettelkasten-style) rather than fixed read/write stores | https://arxiv.org/abs/2502.12110 | S |
| 6.9 | Mem0 | Chhikara, Khant, et al. | arXiv 2504.19413 | 2025 | Scalable extraction/consolidation memory layer with reported latency and token savings vs full-context baselines | https://arxiv.org/abs/2504.19413 | S |
| 6.10 | Zep / Graphiti | Rasmussen, Paliychuk, Beauvais, Ryan, Chalef | arXiv 2501.13956 | 2025 | Temporal knowledge-graph memory with bi-temporal edges; reports DMR and LongMemEval gains over baselines | https://arxiv.org/abs/2501.13956 | S |
| 6.11 | Agent Workflow Memory | Wang, Mao, Fried, Neubig (CMU/MIT) | ICML 2025; arXiv 2409.07429 | 2025 | Induces reusable workflow memories from past trajectories and injects them into later web-agent runs | https://arxiv.org/abs/2409.07429 | S |
| 6.13 | RepoCoder | Zhang, Chen, et al. | EMNLP 2023; arXiv 2303.12570 | 2023 | Iterative retrieval-generation loop for repository-level code completion (retrieve → complete → re-retrieve) | https://arxiv.org/abs/2303.12570 | S |
| 6.14 | RepoBench | Liu, Xu, et al. | ACL 2024; arXiv 2306.03091 | 2024 | Repository-level completion benchmark isolating retrieval, completion and the retrieval-completion pipeline | https://ar5iv.labs.arxiv.org/html/2306.03091 | F |
| 6.15 | CodeRAG-Bench | Wang, Chen, et al. | arXiv 2406.14497 (COLM 2024) | 2024 | Shows retrieval helps most when the base model cannot solve the task unaided; naive retrieval can hurt | https://arxiv.org/abs/2406.14497 | S |
| 6.16 | A Survey of Context Engineering for LLMs | Mei, Yao, et al. | arXiv 2507.13334 | 2025 | Systematizes context assembly (retrieval, selection, compression, ordering, isolation) as the successor framing to prompt engineering | https://arxiv.org/abs/2507.13334 | S |

| 6.17 | MemoryArena | He, Wang, Zhi, Hu, Chen, Yin, Chen, Wu, Ouyang, Wang, Pei, McAuley, Choi, Pentland | ICML 2026; arXiv 2602.16313 | 2026 | Interdependent multi-session agentic memory tasks: agents that nearly saturate LoCoMo still perform poorly when memory must support later actions | https://arxiv.org/abs/2602.16313 | F |

**Reading of Topic 6.** Long-context degradation is now a **measured, non-controversial** result (6.4–6.7): more tokens can hurt, mid-context content is discounted, and lexical-overlap removal collapses recall (NoLiMa). Memory research has consequently bifurcated into (a) **external memory services with evaluated write/consolidate policies** (A-MEM, Mem0, Zep, Agent Workflow Memory) and (b) **context engineering as a discipline** (compaction, isolation, ordering). For code specifically, retrieval helps mainly as a *localization* aid (RepoCoder, CodeRAG-Bench) — it is not a substitute for execution feedback.

---

## 7. Topic 7 — Evaluation benchmarks for coding and general agents (incl. contamination)

| # | Benchmark | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 7.1 | SWE-bench | Jimenez, Yang, Wettig, Yao, Pei, Press, Narasimhan (Princeton/Chicago) | ICLR 2024; arXiv 2310.06770 | 2024 | 2,294 real GitHub issue/PR tasks across 12 Python repos; best 2023 model resolved 1.96% | https://arxiv.org/abs/2310.06770 | F |
| 7.2 | SWE-bench Verified | OpenAI (with SWE-bench authors) | openai.com | 2024 | 500 human-validated, unambiguously solvable instances released to de-noise the original benchmark | https://openai.com/index/introducing-swe-bench-verified/ | S |
| 7.3 | Why we no longer evaluate SWE-bench Verified | OpenAI | openai.com | 2025–26 | Declares the benchmark saturated/contaminated for frontier models and recommends decontaminated evaluation | https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ | S |
| 7.4 | SWE-bench Multimodal | Yang, Jimenez, et al. | ICLR 2025; arXiv 2410.03859 | 2025 | 517 JS visual-UI tasks with screenshots; leading agents transfer poorly from text-only SWE-bench | https://arxiv.org/abs/2410.03859 | S |
| 7.5 | Multi-SWE-bench | Zan, Huang, et al. (ByteDance) | arXiv 2504.02605 | 2025 | Multilingual issue-resolving benchmark (Java/TS/JS/Go/Rust/C/C++) exposing Python-centric overfitting | https://arxiv.org/abs/2504.02605 | S |
| 7.6 | SWE-bench Pro | Deng, Da, Pan, et al. (Scale AI) | arXiv 2509.16941 | 2025 | Long-horizon tasks over 41 repositories with public / held-out / commercial splits, designed as a contamination-resistant testbed | https://arxiv.org/abs/2509.16941 | F |
| 7.7 | SWE-bench+ | Aleithan, et al. | arXiv 2410.06992 | 2024 | Shows 32.67% of SWE-bench "resolved" patches exploited solution leakage (hints in issue text/tests) | https://arxiv.org/abs/2410.06992 | S |
| 7.8 | The SWE-Bench Illusion | (ICSE 2026 SEIP authors) | ICSE 2026 SEIP; arXiv 2506.12286 | 2026 | Models can reproduce gold patches from memory when given only the file path — high scores partly reflect memorization | https://conf.researchr.org/details/icse-2026/icse-2026-software-engineering-in-practice/29/The-SWE-Bench-Illusion-When-State-of-the-Art-LLMs-Remember-Instead-of-Reason | S |
| 7.9 | SWE-rebench (+ V2) | Badertdinov, Nekrashevich, Shevtsov, Golubev (Nebius) | NeurIPS 2025 Datasets & Benchmarks (V1); ICML 2026 poster (V2) | 2025–26 | Continuously refreshed decontaminated SWE task pipeline; V2 is language-agnostic with 32,079 executable tasks across 20 languages | https://papers.neurips.cc/paper_files/paper/2025/hash/21bec6ace947b1b58967b945c8ac0f10-Abstract-Datasets_and_Benchmarks_Track.html | F |
| 7.10 | SWE-Gym | Pan, Wang, et al. | ICLR 2025; arXiv 2412.21139 | 2025 | 2,438 real task instances with executable environments for training SWE agents/verifiers | https://arxiv.org/abs/2412.21139 | S |
| 7.11 | SWE-smith | Yang, et al. | arXiv 2504.21798 (NeurIPS 2025) | 2025 | Synthesizes 50k+ task instances by breaking repos — scalable training data without human PRs | https://arxiv.org/abs/2504.21798 | S |
| 7.13 | Commit0 | Zhao, Jiang, Lee, Chiu, Cardie, Gallé, Rush (Cornell/Cohere) | ICLR 2025; arXiv 2412.01769 | 2025 | Library-from-scratch benchmark (54 libs); best agent passes only a minority of unit tests, OpenHands 42.95% on lite | https://ar5iv.labs.arxiv.org/html/2412.01769 | F |
| 7.14 | SWT-Bench | Mündler, Müller, He, Vechev (ETH Zürich) | NeurIPS 2024; arXiv 2406.12952 | 2024 | Repurposes SWE-bench PRs to evaluate *test generation*: agents must write fail-to-pass tests from the issue | https://arxiv.org/abs/2406.12952 | S |
| 7.15 | TestGen-LLM (Meta) | Alshahwan, Chheda, et al. (Meta) | FSE 2024 Industry; DOI 10.1145/3663529.3663839 | 2024 | Assured LLM test improvement in production: 75% built, 57% reliably passed, 25% coverage-increased, 73% accepted by reviewers | https://dl.acm.org/doi/abs/10.1145/3663529.3663839 | S |
| 7.16 | SWE-Lancer | Miserendino, Wang, et al. (OpenAI) | arXiv 2502.12115 | 2025 | 1,400+ real Upwork tasks worth $1M; measures dollar-value resolution rather than pass rate | https://arxiv.org/abs/2502.12115 | S |
| 7.17 | Terminal-Bench | Terminal-Bench team (Stanford / Laude Institute) | ICLR 2026; tbench.ai | 2026 | Hard, realistic command-line tasks in containerized terminals; peer-reviewed at ICLR 2026 | https://proceedings.iclr.cc/paper_files/paper/2026/hash/444a3737adaee10d86ad2ef5f74468e6-Abstract-Conference.html | S |
| 7.18 | τ-bench | Yao, Shinn, Razavi, Narasimhan (Sierra) | arXiv 2406.12045 | 2024 | Tool-agent-user benchmark with a simulated user and domain policies; pass^k measures reliability across trials | https://arxiv.org/abs/2406.12045 | S |
| 7.20 | GAIA | Mialon, Fourrier, Swift, et al. (Meta/HuggingFace) | ICLR 2024; arXiv 2311.12983 | 2024 | 466 real-world assistant questions requiring tool use, browsing and multi-step reasoning | https://arxiv.org/abs/2311.12983 | S |
| 7.21 | WebArena | Zhou, Xu, Coyle, et al. (CMU) | ICLR 2024; arXiv 2307.13854 | 2024 | Four self-hosted realistic web environments with functional correctness verification | https://github.com/web-arena-x/webarena | S |
| 7.23 | TheAgentCompany | Xu, Song, et al. (CMU) | NeurIPS 2025 Datasets & Benchmarks; arXiv 2501.14249 | 2025 | Simulated software company (own GitLab/Plane/RocketChat) with consequential multi-role tasks | https://papers.nips.cc/paper_files/paper/2025/hash/0d744742f6fac4d1134c019b7cef3c8a-Abstract-Datasets_and_Benchmarks_Track.html | S |

| 7.26 | SWE-EVO | Thai, Le, Manh, Nhat, Bui (FPT Software AI Center) | arXiv 2512.18470 (v4) | 2026 | 48 long-horizon *software evolution* tasks; GPT-5 + OpenHands resolves 21% versus 65% on single-issue SWE-bench Verified | https://arxiv.org/abs/2512.18470v4 | F |
| 7.27 | ProgramBench | Yang, Lieret, Ma, et al. (Meta FAIR / Stanford / Harvard) | ICML 2026 Workshop (DL4C); arXiv 2605.03546 | 2026 | Agents must rebuild 200 programs from documentation alone; no model fully resolves any task | https://icml.cc/virtual/2026/82809 | F |
| 7.28 | SWE-Bench ProMax | Shi, Xu, Fu, He, Gu, et al. (SJTU / PKU / HKUST / Douyin / NUS / Monash) | COLM 2026; arXiv 2608.09802 | 2026 | Multilingual large-scale refactoring benchmark; best model 41.2%, and an audit finds ~60% of unsolved SWE-bench Verified instances have flawed tests | https://www.alphaxiv.org/abs/2608.09802 | F |
| 7.29 | Terminal-Bench 2.0 + Harbor | Merrill, Shaw (Stanford / Laude Institute / Harbor) | tbench.ai release announcement | 2025–26 | Harder verified re-release plus the Harbor harness, shipped after community audits of 1.0 task quality | https://www.tbench.ai/news/announcement-2-0 | F |
| 7.30 | Gaia2 | Froger, Andrews, Bettini, et al. (Meta SuperIntelligence Labs) | ICLR 2026 (oral); arXiv 2602.11964 | 2026 | Asynchronous, dynamic environments with write-action verifiers; GPT-5-high 42% pass@1, Kimi-K2 21% | https://proceedings.iclr.cc/paper_files/paper/2026/hash/c26a67e0470774df98c12480ec5d2d7b-Abstract-Conference.html | F |

**Reading of Topic 7.** The benchmark lineage has three generations: (i) **static PR-replay** (SWE-bench, Verified) — now documented as leaky (7.7) and memorizable (7.8), and officially deprecated by its most prominent user (7.3); (ii) **scaled/synthetic training+eval** (SWE-Gym, SWE-smith, SWE-rebench); (iii) **long-horizon and economic** (SWE-bench Pro, SWE-Lancer, Terminal-Bench). Also note the 2026 arrival of second-order benchmarks (SWE-bench ProMax 2608.09802, ProgramBench 2605.03546, SWE-EVO 2512.18470) that target refactoring, from-scratch construction and long-horizon evolution respectively.

---

## 8. Topic 8 — Cost, latency, budget control, routing, caching, economics of agentic loops

| # | Work / Practice | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| 8.1 | RouteLLM | Ong, Almahairi, Wu, Chiang, Wu, Gonzalez, Kadous, Stoica (UC Berkeley/LMSYS) | ICLR 2025; arXiv 2406.18665 | 2025 | Learned routers between strong/weak models cut cost >2× at matched response quality, and generalize to unseen model pairs | https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html | F |
| 8.2 | FrugalGPT | Chen, Zaharia, Zou (Stanford) | arXiv 2305.05176 | 2023 | LLM cascade with a scoring function matches GPT-4 quality at up to 98% lower cost on some workloads | https://arxiv.org/abs/2305.05176 | S |
| 8.3 | GPTCache | Bang (Zilliz) | NLP-OSS 2023 (EMNLP workshop); aclanthology 2023.nlposs-1.24 | 2023 | Semantic (embedding-similarity) cache in front of the LLM: faster answers and cost savings vs exact-match caching | https://aclanthology.org/2023.nlposs-1.24.pdf | S |
| 8.4 | Prompt caching (Anthropic) | Anthropic | claude.com blog / docs | 2024–26 | Cache reads cost ~10% of base input price with large latency cuts for repeated long prefixes | https://claude.com/blog/prompt-caching | S |
| 8.5 | Prompt caching in the API (OpenAI) | OpenAI | openai.com | 2024–26 | Automatic prefix caching with 50% discount on cached input tokens — changes optimal agent prompt layout | https://openai.com/index/api-prompt-caching/ | S |
| 8.6 | CacheBlend | Yao, Li, et al. | EuroSys 2025; ACM DL 10.1145/3790254 | 2025 | Fuses cached KV chunks from different documents to enable reuse without full prefill recomputation | https://dl.acm.org/doi/pdf/10.1145/3790254 | S |
| 8.7 | Cost-of-Pass | (see arXiv listing) | arXiv 2504.13359 | 2025 | Economic framework: expected dollar cost per correct solution, replacing pure accuracy as the comparison axis | https://arxiv.org/abs/2504.13359 | S |
| 8.8 | Multi-agent token economics (field measurement) | Anthropic | Anthropic Engineering blog | 2025 | Agents ≈4× chat tokens; multi-agent ≈15× chat tokens; token quantity explained ~80% of performance variance in their analysis | https://www.anthropic.com/engineering/multi-agent-research-system | K |

| 8.10 | CliffCompaction | Nguyen, Cho, Chen, Dettmers | arXiv 2609.26779 (v1) | 2026 | Truncation-only auto-compaction cuts long-horizon coding-agent cost by up to 50% while maintaining or improving Terminal-Bench performance | https://arxiv.org/abs/2609.26779 | F |
| 8.11 | Prompt caching + sticky routing | OpenRouter | OpenRouter engineering blog (2026-07-21, upd. 2026-09-24) | 2026 | Cache reads cost 0.1×–0.5× of fresh input, so sticky routing that keeps an agent loop's prefix on one provider is the dominant lever | https://openrouter.ai/blog/tutorials/prompt-caching-sticky-routing/ | F |
| 8.12 | AgentRouter | Paul, Nandy | AgenticUQ Workshop @ ICML 2026 (camera-ready); arXiv 2609.22951 | 2026 | Step-level heterogeneous model routing cuts agentic inference cost 72% versus frontier-only baselines | https://arxiv.org/abs/2609.22951 | F |
| 8.13 | Budget-aware online adaptation for web agents | Zhang, Cao, Zheng, Wen, Ke, Liu, Gao, Dong, Yang, Zhang (UESTC / IS-CAS et al.) | arXiv 2609.05513 (v1) | 2026 | Budget-aware teacher gating and turn selection cut teacher calls 22.6% at comparable first-pass success | https://arxiv.org/abs/2609.05513 | F |
| 8.14 | LiteLLM Auto Router (vendor self-benchmark) | Tin Lo (LiteLLM) | docs.litellm.ai blog, 2026-09-11 | 2026 | Capability routing reported to cut SWE-bench Verified cost 45% at equal solve count — n=25, one attempt per task, self-reported | https://docs.litellm.ai/blog/auto-router-capability-benchmark | partial |

**Reading of Topic 8.** The economics literature has shifted from **model routing** (cheaper model for easy queries) to **prefix/KV reuse** (prompt caching, cache-aware prompt layout, CacheBlend) and **budget-aware agent policy** (turn limits, compaction). Note the coupling to protocol design: MCP 2026-07-28 explicitly requires deterministic `tools/list` ordering "to improve LLM prompt cache hit rates" (3.1) — a standards-level acknowledgment that cache-hit rate is now an architectural concern, not an optimization afterthought.

---

## 9. Consensus vs contested vs assumption

### 9.1 Consensus (multi-source, survives adversarial reading)

1. **Multi-agent gains largely dissolve under equal-compute controls.** Sampling-and-voting scales with agent count (2.3); compound-system accuracy is predicted by call count (2.5); single agents match or beat MAS at matched thinking-token budgets (2.8) and matched inference cost (2.9); token volume explained ~80% of the variance in Anthropic's own multi-agent result (2.11). Any 2026 claim of "collaboration gain" that lacks an equal-token single-agent baseline is not credible.
2. **Failures are organizational before they are intellectual.** MAST's 14 modes across 7 frameworks are dominated by specification/coordination/verification defects, not raw model incapacity; the same model under a different topology produces a different failure profile (2.1).
3. **Long-context degradation is measured, not hypothetical.** Position sensitivity (6.4), effective-context shortfall (6.5), collapse under lexical-overlap removal (6.6), and length-only degradation (6.7) are mutually reinforcing.
4. **LLM-as-judge has reproducible biases** — position, verbosity, self-preference (5.21, 5.22) — and hard judging remains near chance for strong models (5.23). Judge validation is mandatory.
5. **Prompt injection through tools is not solved by prompting.** Indirect injection succeeds broadly (5.12), and the credible defenses are architectural/capability-based (5.14, 5.15).
6. **Interoperability consolidated under neutral governance**: MCP for tools/context, A2A for agent-to-agent, both now foundation-hosted (3.4–3.7), with MCP becoming stateless and cache-aware in the 2026-07-28 revision (3.1).
7. **SWE-bench (original and Verified) is no longer a frontier discriminator** — leakage (7.7), memorization (7.8), and the benchmark author's own abandonment (7.3).
8. **Durable execution semantics are table stakes** for anything long-running: checkpointing, interrupt/resume, and replayable event history (4.1–4.2, 4.11–4.13). By 2026 this moved *underneath* the agent loop — Temporal wraps each model/tool call as an Activity (4.18), Restate journals each step (4.19), LangGraph ≥1.2 adds per-node timeouts and error handlers with drain/resume (4.17).
9. **Verification roles buy interception, not safety.** Planner+verifier scaffolding inflates τ-bench tokens 2.0–2.8× and intercepts up to 94% of violations while safe success stays below 5% (2.18); in a production enterprise agent the verification loop contributed only +1.5 of an +11.0-point gain (2.22).
10. **Capability progress is not reliability progress.** Across 15 models and 24 months of releases, twelve reliability metrics improved only marginally (2.19).
11. **Context compaction is a safety hazard, not just a token optimization.** Compaction raised policy violations from 0% to 30% (59% worst model); pinning the constraint restored 0% (2.21).
12. **For testing specifically, 2026 peer-reviewed venues converged on asymmetric multi-agent loops.** Independent ICSE 2026, FSE 2026 and ISSTA 2026 papers all use a planner/generator/reviewer or adversarial generator-vs-mutant split, where each agent carries *different information* (runtime traces, repo knowledge graphs, mutants) rather than a different persona (1.19–1.21).
13. **Cost control in 2026 shifted from model-swapping to cache- and step-level routing plus compaction**: sticky prefix routing with cached reads at 0.1×–0.5× (8.11), step-level routing at −72% (8.12), truncation-only compaction at −50% (8.10), and budget-aware turn gating at −22.6% teacher calls (8.13).

### 9.2 Contested (credible evidence on both sides)

| Question | Pro | Contra | Current reading |
|---|---|---|---|
| Does debate/consensus beat ensembling? | Du et al. 1.14 | Should we be going MAD? 2.4; More Agents 2.3 | Gains look like diversity+aggregation, not argumentation. Control for sampling budget. |
| Do more agents yield emergent capability? | MacNet scaling law 1.17 | Equal-cost nulls 2.8, 2.9 | Contested; likely compute-scaling restated. |
| Hierarchy vs flat topology? | ChatDev/MetaGPT SOP pipelines 1.1–1.2, MAGIS 1.7 | MAST topology comparison 2.1; SWE-agent interface result 1.8 | Topology moves failures around; no universal winner. |
| Is self-review/critique useful? | Test-execution feedback loops (1.6, 7.13) | Intrinsic self-correction fails 2.6 | Only with *external* signal (tests, execution, retrieval). |
| Do memory services improve outcomes? | A-MEM/Mem0/Zep/Agent Workflow Memory 6.8–6.11 | Context-engineering results 6.4–6.7, 6.16 | Task-dependent; report cost per solved task, not recall metrics alone. |
| Is semantic caching safe for agents? | GPTCache/CacheBlend 8.3, 8.6 | Tool side effects and staleness make cache reuse semantically unsafe | Safe for read-only/prefix reuse; unsafe as a blanket response cache. |
| Does adding verifier/planner roles pay off? | Production decomposition +11.0 pts (2.22); orchestration recovery tiers (2.20) | Verifier Tax: <5% safe success at 2–2.8× tokens (2.18); MA-Evolve null at equal cost (2.9) | Pays on *decomposition* (specialists/cross-checking across benchmarks), not on *verification theatre*; measure safe-success per dollar. |
| Is "agent reliability" improving with scale? | Vendor reliability/evals suites (4.20, 5.27) | ICML 2026 reliability study: marginal gains (2.19) | Contested; reliability must be measured as its own axis (consistency, robustness, predictability, safety). |
| Do 2026 memory benchmarks agree? | MemoryArena's low scores for LoCoMo-saturating agents (6.17) | A matched-backend study in the same sweep reports 20.5% vs 13.6% five-domain success with overlapping CIs, versus 40–60% in a 2026 survey for other systems | Contested and sample-size-sensitive: 2026 memory percentages are not yet comparable across papers. |

### 9.3 Assumptions widely repeated but weakly evidenced (flag these in any 2026 paper)

1. "More agents ⇒ better results" — assumed by most frameworks, contradicted under iso-cost controls.
2. Role *labels* (planner/tester/reviewer) induce the intended behavior; almost no ablation separates the label from the prompt content or the added compute.
3. Benchmark scores measure capability rather than memorization — falsified for SWE-bench-style tasks (7.7, 7.8).
4. LLM judges are substitutable for human reviewers — falsified in the general case (5.21–5.23).
5. Token counts proxy cost — ignores cache hits, retries, sandbox compute, and human review time; cost-of-pass (8.7) is the better axis.
6. Adopting MCP/A2A implies security review — protocol adoption ≠ threat model (3.16-class findings; 5.11–5.12, 5.14–5.15).
7. "Agentic" implies autonomy: in practice most 2025–26 production systems are human-interrupted graphs (4.1) with per-step approval.

---

## 10. What a 2026 reviewer would consider table stakes

**Experimental design**
1. An **equal-token / equal-dollar single-agent baseline** (not a weaker model or a naive prompt), reported with the same retry budget.
2. **Cost, latency and token accounting per solved task** (cost-of-pass), split by cached vs uncached tokens.
3. **≥5 seeds with effect sizes and confidence intervals**; pass^k (reliability across repetitions), not just pass@1.
4. An **explicit failure taxonomy** (MAST-style) over sampled trajectories, with inter-annotator agreement if human-labeled.

**Reproducibility**
5. **Pinned versions of everything**: model snapshot IDs, framework version, and *protocol revision* (e.g., "MCP 2025-11-25 vs 2026-07-28" — these are wire-incompatible).
6. **Deterministic replay**: record/replay of LLM calls plus event-history-style state replay, so a failing run can be re-executed.
7. An **artifact package** (seeds, env, container digests, eval harness) satisfying ACM-style badging.

**Safety and isolation**
8. **Sandbox declaration**: microVM (Firecracker/Kata) vs syscall-filtered container (gVisor/seccomp), network policy (default-deny), and filesystem scope.
9. A **prompt-injection threat model** with an AgentDojo/InjecAgent-style evaluation and a stated utility cost of the defense.
10. **Human-in-the-loop interrupt + resume** demonstrated, including what state is checkpointed and what happens on crash mid-tool-call.

**Evaluation integrity**
11. **Contamination audit** (time-windowed or decontaminated benchmarks; leakage checks in the style of SWE-bench+).
12. **Judge validation**: human-agreement sample, position-bias control (order randomization/bidirectional scoring), judge model + version disclosed.
13. **Trace-level observability** exported via OpenTelemetry `gen_ai.*` spans so third parties can inspect intermediate steps.
14. A **regression suite for prompts/agents in CI** (dataset-backed evals, not ad-hoc manual checks).
15. **Stated separation of agent-specific contribution from compute**: ablation showing what the extra agents buy beyond extra samples.

---

## 11. Unverified items, exclusions, and explicit negative results

**Rows still tagged K (canonical source, URL not loaded in this session — treat as leads, not as verified quotes):**

| Row | Why it stays K |
|---|---|
| 1.2 MetaGPT | arXiv ID corroborated; the *ICLR 2024 oral* venue string comes from community metadata, not a fetched OpenReview/proceedings page |
| 2.11 Anthropic multi-agent blog | URL corroborated by search; the ~90.2% gain and ~15× token figures come from the vendor post and the workspace's prior checklist, not from my own measurement |
| 3.9 function calling | Official docs page not fetched |
| 3.16 MCP security | row now cites *Systematic Analysis of MCP Security* (arXiv 2508.12538), search-corroborated only |
| 4.5 AG2 | Project site not fetched |
| 5.22 Fair Evaluators | arXiv 2305.17926 not fetched; bias finding is corroborated by 5.21/5.23 |
| 6.7 Chroma context rot | Author list (Hong, Troynikov, Huber) corroborated by a 2026 citing paper; the report page itself was not fetched |
| 7.2 SWE-bench Verified | upgraded to **S**: the OpenAI announcement URL was returned by search with a matching title |

Everything else in §1–§8 is tagged **F** (page fetched here) or **S** (exact URL+title returned by an in-session search).

**Explicitly NOT verified / excluded (do not cite as if verified):**
- **ACP's fate — now RESOLVED (verified):** the official ACP documentation home carries the banner *"ACP is now part of A2A under the Linux Foundation!"* with a migration guide, and the AAIF blog states IBM's Agent Communication Protocol merged into A2A in August 2025 (row 3.8). Caveat: this is the project's own notice, not a separate retirement statement. **Acronym hazard:** OpenAI's *Agentic Commerce Protocol* is also abbreviated ACP and appears under that name in the AAIF launch release — do not conflate them.
- **Specific leaderboard numbers** (e.g., "best model resolves X% of SWE-bench Pro / Terminal-Bench"). I did not fetch leaderboard tables; only the benchmarks' existence, venue and stated design are verified.
- **2026 coverage is now complete across all six sweep threads**, but it is *shallow in places*: the gap-fill capped each thread at 7 entries, several 2026 items are unreviewed preprints (1.22, 1.23, 8.10, 8.12, 8.13), two are vendor self-benchmarks (1.24, 8.14 — one marked partial), and the memory sub-area has a live cross-paper disagreement (§9.2). Every 2026 row was re-fetched by a second agent; 6 candidate items were dropped as unsubstantiable.
- **arXiv reachability was intermittent** during this run: most agents saw arxiv.org time out, while the gap-fill agent successfully fetched arxiv.org/abs pages (e.g., 2602.16313, 2609.26779). Rows verified through the alphaXiv mirror are tagged F but the mirror is a third party; if you need first-party arXiv verification, re-fetch those rows before publication.
- **OpenAlex-derived arXiv metadata.** As documented in §0, OpenAlex maps several arXiv DOIs to unrelated papers; no row here relies on it for arXiv identity.
- **No DOI in this report was invented.** DOIs appear only where a publisher/proceedings page or the workspace's previously verified checklist supplied them (2.17, 5.7, 7.15).

---

## 12. Retrieval transparency

- **Tools:** `web_search` (≈30 batched query sets), `web_fetch` (MCP spec, alphaXiv/ar5iv mirrors, ICLR/NeurIPS proceedings, OpenAlex, Semantic Scholar, docs sites), plus two fan-out sweeps: a 12-topic research workflow whose first instance terminated without output (the same 12 topics were then covered by direct batched searching), a 6-thread 2026 sweep whose surviving threads were re-verified agent-by-agent (28 entries, 3 threads lost to truncation), and a 3-thread gap-fill that returned 21 further verified entries and dropped 6 unsubstantiable ones.
- **Query themes:** system names (ChatDev, MetaGPT, AutoGen, CAMEL, AgentVerse, AgentCoder, MAGIS, SWE-agent, MapCoder, AutoCodeRover, SoA, Agent Laboratory, DyLAN, GPTSwarm, AFlow, MacNet); critique terms ("do multi-agent systems beat single agent", "equal compute", "error propagation", "MAST"); protocol terms (MCP specification 2025-11-25 / 2026-07-28, A2A spec, AGNTCY, ACP, Agentic AI Foundation); reliability terms (guardrails, sandbox, gVisor, Firecracker, E2B, seccomp, OTel GenAI, LLM-as-judge bias); memory/context (LongMemEval, LoCoMo, RULER, NoLiMa, context rot, Mem0, Zep, A-MEM); benchmarks (SWE-bench family, Multi-SWE-bench, SWE-Gym, Commit0, Terminal-Bench, τ-bench, GAIA, WebArena, OSWorld, SWE-Lancer, SWE-bench Pro, contamination); economics (RouteLLM, FrugalGPT, GPTCache, prompt caching, CacheBlend, cost-of-pass).
- **Known systematic blind spots:** arXiv full text (unreachable), leaderboard tables, non-English literature, ACM/IEEE paywalled full texts, and any 2026 venue that has not yet posted proceedings.
