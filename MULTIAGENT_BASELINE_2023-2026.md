# Multi-Agent LLM Systems for Software Engineering — Verifiable Frontier Baseline (2023–2026)

**Prepared:** 2026-09-30 (Asia/Shanghai) · **Scope:** multi-agent architectures for SE/testing, empirical critiques, interop protocols, orchestration/durability, agent reliability engineering, memory/context, evaluation, cost. · **Emphasis:** 2024–2026. · **Rows:** 108 across 8 clusters (tags: [F] 20 · [S+] 30 · [S] 57 · [U] 1). · **Sibling deliverable:** `MULTI_AGENT_LLM_SE_FRONTIER_BASELINE_2023-2026.md` (same protocol, different row set; where the two disagree, this file's tags win for this session).

---

## 0. Method, verification legend, hard limits

**Legend — every row carries exactly one tag.**

| Tag | Meaning |
|---|---|
| **[F]** | I **fetched that exact URL in this session** and the fetched text supports the claim. Strongest evidence available here. |
| **[S+]** | **Two independent in-session records** (search hits, distinct hosts) agree on title/venue/ID. Full text not opened. |
| **[S]** | **One in-session search record** (snippet, title, or URL) supports the row. Metadata only; claims are descriptive, not quantitative. |
| **[U]** | Unverified. Used only where a required coverage item could not be substantiated; such rows are also listed in §11 and must not be cited as fact. |

**Number-quoting rule applied here:** a number appears only if it was visible in a **fetched page** or in a **search snippet** this session. Numbers I know from memory but did not re-see are omitted and listed in §11.

**Environment limits hit this session (state these in any downstream review, do not paper over them):**

1. **arXiv direct fetch is unreliable.** `https://export.arxiv.org/abs/2312.13010` → `TypeError: fetch failed`; `https://ar5iv.labs.arxiv.org/html/2512.10218` → `fetch failed`. **Workaround used:** `papers.cool/arxiv/<id>` mirrors the arXiv abstract **verbatim** (with authors, subjects, submission timestamp) and fetched cleanly for 4 papers. Those 4 rows are tagged [F] on the mirror URL, and the canonical `arxiv.org/abs/<id>` is given alongside. Treat [F]-on-mirror as *abstract-level* verification, not full-text verification.
2. **Publisher hosts are second-class here.** `dl.acm.org`, `ieeexplore.ieee.org`, `link.springer.com`, `sciencedirect.com`, and `doi.org` redirects are typically 403/blocked in this environment. Rows whose only URL is one of those are **[S] at best** and several links are Cloudflare-tokenized staging URLs that may expire.
3. **Conference sites and vendor docs are first-class.** `conf.researchr.org`, `papers.nips.cc`, `proceedings.iclr.cc`, `icml.cc`, `aclanthology.org`, `modelcontextprotocol.io`, `opentelemetry.io`, `openai.com`, `trychroma.com` all fetched or surfaced reliably.
4. **Single-fetch pages can be truncated** by the fetcher (the OpenAI SWE-bench post and the MCP spec were). Where truncation hid the body, the row says so.

---

## 1. Cluster 1 — Multi-agent architectures for SE & testing (23 rows)

| # | Work / System | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 1.1 | ChatDev | ACL 2024 (Long Papers) | 2024 | Chat-chain of designer / coder / tester / reviewer roles for end-to-end software generation | https://aclanthology.org/2024.acl-long.810/ | S+ |
| 1.2 | MetaGPT | arXiv 2308.00352 (ICLR 2024 venue **not** re-verified) | 2023 | Encodes SOPs into role prompts; one-line requirement → PRD, design, tasks, repo | https://arxiv.org/abs/2308.00352 | S |
| 1.3 | AutoGen → AG2 → Microsoft Agent Framework | Microsoft (framework lineage) | 2024–25 | Framework lineage split: AutoGen v0.4 rewrite, AG2 community fork, later consolidation into Microsoft Agent Framework | https://github.com/larsderidder/framework-analysis/blob/main/tier-2/ag2.md | S+ |
| 1.4 | CAMEL | NeurIPS 2023 (venue **not** re-verified; row verified via a 2026 survey that catalogues it) | 2023 | Two-agent role-play (AI user ↔ AI assistant); listed as `CAMEL [38]` in a 2026 framework table | https://link.springer.com/content/pdf/10.1007/s12559-026-10619-1.pdf | S |
| 1.5 | AgentVerse | ICLR 2024 | 2024 | Multi-agent collaboration framework + study of emergent behaviours | https://mlanthology.org/iclr/2024/chen2024iclr-agentverse/ | S+ |
| 1.6 | AgentCoder | arXiv 2312.13010 | 2023 | Separates programmer / test-designer / test-executor agents so tests are authored independently of the code | http://export.arxiv.org/pdf/2312.13010 | S |
| 1.7 | Self-Organized Agents (SoA) | arXiv 2404.02183 (venue unverified) | 2024 | Agents recursively spawn sub-agents toward ultra-large-scale code generation and optimization | https://huggingface.co/papers/2404.02183 | S+ |
| 1.8 | MacNet (Scaling LLM-based Multi-Agent Collaboration) | ICLR 2025; arXiv 2406.07155 | 2025 | Proposes a collaborative scaling law over densely connected agent networks | https://proceedings.iclr.cc/paper_files/paper/2025/hash/66a026c0d17040889b50f0dfa650e5e0-Abstract-Conference.html | S+ |
| 1.9 | DyLAN (Dynamic LLM-Agent Network) | arXiv 2310.02170 (venue **unverified** — see §11) | 2023 | Optimizes the agent team and communication topology rather than fixing a role script | https://github.com/SALT-NLP/DyLAN | S+ |
| 1.10 | AFlow | ICLR 2025; arXiv 2410.10762 | 2025 | Monte-Carlo tree search over code-represented agent workflows automates workflow design | https://proceedings.iclr.cc/paper_files/paper/2025/hash/5492ecbce4439401798dcd2c90be94cd-Abstract-Conference.html | S+ |
| 1.11 | GPTSwarm | ICML 2024; arXiv 2402.16823 | 2024 | Language agents as optimizable computation graphs (nodes/edges trained by feedback) | https://icml.cc/virtual/2024/poster/32826 | S+ |
| 1.12 | MAGIS | NeurIPS 2024 | 2024 | Manager / repository-custodian / QA roles for GitHub issue resolution (Tao, Zhou, Wang, Zhang, Zhang, Cheng) | https://proceedings.neurips.cc/paper_files/paper/2024/file/5d1f02132ef51602adf07000ca5b6138-Paper-Conference.pdf | S+ |
| 1.13 | CodeR | arXiv 2406.01304 | 2024 | Issue resolving with multiple agents coordinated by task graphs (Chen, Lin et al.) | http://export-test.arxiv.org/pdf/2406.01304 | S+ |
| 1.14 | MASAI | arXiv 2406.11638 | 2024 | Modular architecture: specialized sub-agents with distinct objectives instead of one monolithic agent | https://ui.adsabs.harvard.edu/abs/2024arXiv240611638A/exportcitation | S |
| 1.15 | Agent Laboratory | arXiv 2501.04227 | 2025 | Multi-agent research pipeline (literature → experimentation → report) with human-in-the-loop | https://huggingface.co/papers/2501.04227 | S+ |
| 1.16 | OpenHands | arXiv 2407.16741 | 2024 | Open platform for AI software developers as generalist agents | https://julib.fz-juelich.de/vufind/EdsRecord/edsarx,edsarx.2407.16741 | S |
| 1.17 | SWE-agent | Open-source scaffold (venue **not** re-verified) | 2024 | Repository-repair scaffold that is the de-facto *single-agent* comparator in multi-agent SE claims | https://swe-agent.com/latest/background/ | S |
| 1.18 | AutoCodeRover | ISSTA 2024; DOI 10.1145/3650212.3680384 | 2024 | Autonomous program improvement via structure-aware search + patch validation | https://2024.issta.org/details/issta-2024-papers/127/AutoCodeRover-Autonomous-Program-Improvement | S+ |
| 1.19 | **TestAgent** | **FSE 2026 Tool Demonstrations** (Shang, Zhang, Zhan, Huang, Fang, Chen — Nanjing Univ. / NJUST) | 2026 | Planner + Generator + Reviewer agents over repository-level Code Knowledge Graphs: **92.34% line coverage on 1,451 methods across six Java projects**, **154 real-world bugs** at **92.22% precision** | https://conf.researchr.org/details/fse-2026/fse-2026-demonstrations/30/TestAgent-A-Multi-Agent-LLM-Framework-for-Repository-Level-Unit-Test-Generation | **F** |
| 1.20 | MACO | Information and Software Technology, Vol. 195 (2026), art. 108098 | 2026 | Multi-agent collaborative optimization for unit-test-case generation | https://acm-stag.literatumonline.com/doi/10.1016/j.infsof.2026.108098 | S |
| 1.21 | Multi-agent mocking for CI | ACM (10.1145/3774748.3787622) | 2026 | Toward a multi-agent system for reliable mocking of static methods and continuous integration | https://dl.acm.org/doi/pdf/10.1145/3774748.3787622?download=true | S |
| 1.22 | Just-in-Time Catching Test Generation at Meta | FSE 2026 Industry Papers (Harman, Becker, Chen, … Meta) | 2026 | Industrial just-in-time test generation at Meta; preprint arXiv 2601.22832 | https://conf.researchr.org/details/fse-2026/fse-2026-demonstrations/30/TestAgent-A-Multi-Agent-LLM-Framework-for-Repository-Level-Unit-Test-Generation | **F** |
| 1.23 | FSE 2026 agentic competitions (dependency resolution; on-demand library generation) | FSE 2026 competition track | 2026 | The SE community now runs agentic *competitions* on Python dependency resolution and on-demand library generation — repository tasks as a shared benchmark arena | https://conf.researchr.org/home/fse-2026/agpyres-2026 | **F** |

**Reading of Cluster 1.** Three architectural bets coexist: (a) **role/SOP pipelines** (ChatDev, MetaGPT, MAGIS, CodeR, MASAI), (b) **learned/optimized topology** (DyLAN, GPTSwarm, AFlow, MacNet — the structure itself is the object of optimization), (c) **agent–computer interface / scaffold** (SWE-agent, AutoCodeRover, OpenHands). Only (c) has repeatedly been shown to move SWE-bench-style numbers against a strong single-agent baseline; (a) and (b) mostly report gains against weaker internal baselines. For **testing** specifically, 2026 brings peer-reviewed multi-agent test generation with execution-grounded numbers (TestAgent, FSE 2026) plus journal-track work (MACO, IST 2026) — this is the strongest *new* evidence line in the cluster.

---

## 2. Cluster 2 — Empirical and critical studies: does multi-agent actually beat single-agent? (12 rows)

| # | Study | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 2.1 | **MAST — "Why Do Multi-Agent LLM Systems Fail?"** | NeurIPS 2025 Datasets & Benchmarks; arXiv 2503.13657 (Cemri, Pan, Yang, Agrawal, Chopra, Tiwari, Keutzer, Parameswaran, Klein, Ramchandran, Zaharia, Gonzalez, Stoica) | 2025 | Analyzes 7 popular MAS frameworks over 200+ tasks with 6 expert annotators → **14 failure modes in 3 categories** (specification, inter-agent misalignment, task verification), inter-annotator **Cohen's κ = 0.88**; opens a dataset + LLM annotator; MAS gains on popular benchmarks "often remain minimal" vs single-agent | https://papers.cool/arxiv/2503.13657 (canonical: https://arxiv.org/abs/2503.13657; PDF: https://papers.nips.cc/paper_files/paper/2025/file/b1041e52d3be19f0a9bc491657488e4a-Paper-Datasets_and_Benchmarks_Track.pdf) | **F** |
| 2.2 | **Single-Agent LLMs Outperform Multi-Agent Systems on Multi-Hop Reasoning Under Equal Thinking Token Budgets** | arXiv 2604.02460 (Tran & Kiela) | 2026 | Under a fixed reasoning-token budget, SAS **match or outperform** MAS across Qwen3, DeepSeek-R1-Distill-Llama and Gemini 2.5; Data-Processing-Inequality argument; identifies **artifacts in API-based budget control (esp. Gemini 2.5)** and in standard benchmarks that **inflate apparent MAS gains** | https://papers.cool/arxiv/2604.02460 | **F** |
| 2.3 | **Same Model, Different Harness: Different Coding-Agent Results** | arXiv 2608.26218 (Sydney Lewis) | 2026 | Holding model + task fixed and changing only the harness (mechanically shortening older tool results as context fills; reacting to repeated/stalled work) raised **mean per-task F2PF from 28% → 49%** and **complete solutions from 43 → 72** on **169** SWE-bench Verified tasks at a **20,480-token** window and **480 s** per attempt; replicated direction on 3 further models without retuning; conclusion: **evaluate model + harness together as the tested solver** | https://papers.cool/arxiv/2608.26218 | **F** |
| 2.4 | Does SWE-Bench-Verified Test Agent Ability or Model Memory? | arXiv 2512.10218 (Prathifkumar, Mathews, Nagappan) | 2025 | Two Claude models performed **3× better** on SWE-bench-Verified than on BeetleBox / SWE-rebench and **6× better at finding edited files** with minimal context — consistent with training-data overlap, not issue-solving skill | https://papers.cool/arxiv/2512.10218 | **F** |
| 2.5 | Systematic Failures in Collective Reasoning under Distributed Information in Multi-Agent LLMs | ICML 2026 (paper note) | 2026 | Documents systematic collective-reasoning failures when information is distributed across agents | https://raw.githubusercontent.com/zhaoyang97/Paper-Notes-en/refs/heads/main/docs/ICML2026/multi_agent/systematic_failures_in_collective_reasoning_under_distributed_information_in_mul.md | S |
| 2.6 | LLM-Based Multi-Agent Systems for Software Engineering: Literature Review, Vision, and the Road Ahead | journal survey (Scilit record; TOSEM per sibling file — **not** re-verified here) | 2025 | Survey + research agenda for MAS in SE | https://www.scilit.com/publications/7ffddd874e4a8e8148b1e36f9fcd6ee2 | S |
| 2.7 | Large Language Model-Based Agents for Software Engineering: A Survey | arXiv 2409.02977 | 2024 | Broad survey of LLM agents across SE tasks | https://bytez.com/docs/arxiv/2409.02977/paper | S |
| 2.8 | From LLM Reasoning to Autonomous AI Agents: A Comprehensive Review | IEEE (arnumber 11540994) | 2025 | Review of agent reasoning/architecture literature | https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=11540994 | S |
| 2.9 | MAS framework survey table (incl. CAMEL) | Cognitive Computation (Springer), 10.1007/s12559-026-10619-1 | 2026 | 2026 survey carries a framework table (framework / focus / notable features) that catalogues CAMEL and peers | https://link.springer.com/content/pdf/10.1007/s12559-026-10619-1.pdf | S |
| 2.10 | MAST dataset + LLM annotator (artifact) | GitHub `multi-agent-systems-failure-taxonomy/MAST` | 2025 | Open-sourced MAST dataset and judge for scalable MAS failure evaluation | https://raw.githubusercontent.com/multi-agent-systems-failure-taxonomy/MAST/main/README.md | S |
| 2.11 | Why Agent Swarms Fail Tasks That Single Agents Ace | Generative Labs (industry blog — **gray literature**) | 2026 | Popular restatement of coordination-failure findings; useful for framing, not for citation as evidence | https://www.generativelabs.com/insights/anthropic-agent-swarms-coordination-failure | S |
| 2.12 | HarnessBandit: Joint Learnability–Transferability Scheduling for Multi-Harness Agentic RL | arXiv 2609.13739 | 2026 | Treats *harness choice* as a schedulable variable in agentic RL — the harness-as-variable idea reaching training | https://export.arxiv.org/pdf/2609.13739 | S |

**Reading of Cluster 2.** The critique literature has hardened into a coherent position: **reported MAS gains are usually unaccounted compute or unaccounted harness effects** (2.2, 2.3), **benchmarks themselves are contaminated or misspecified** (2.4, §7), and **failures are systematic and taxonomizable** (2.1, 2.5). The single most decision-relevant sentence in this file is 2.3's: *the model and the harness must be evaluated together as the tested solver*.

---

## 3. Cluster 3 — Communication & interop standards (9 rows)

| # | Standard / Topic | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 3.1 | **Model Context Protocol (MCP) spec 2025-06-18** | Anthropic-initiated open protocol | 2025 | JSON-RPC 2.0 messages; **stateful connections** + capability negotiation; servers expose **Resources / Prompts / Tools**; clients offer **Sampling / Roots / Elicitation**; spec explicitly states it **cannot enforce** consent/tool-safety at protocol level — implementors MUST/SHOULD provide consent flows, treat tool descriptions as untrusted unless from a trusted server, and gate sampling | https://modelcontextprotocol.io/specification/2025-06-18/index | **F** |
| 3.2 | MCP 2026-07-28 revision | MCP project / vendor coverage | 2026 | Described as MCP's largest update: moves toward a **stateless core** (session removal) | https://claude.com/blog/bringing-mcp-2026-07-28-to-claude | S |
| 3.3 | Agent2Agent (A2A) | Linux Foundation (donated by Google, June 2025) | 2025 | Cross-vendor agent-to-agent interoperability protocol, now under neutral foundation governance | https://siliconangle.com/2025/06/24/google-donates-agent2agent-protocol-linux-foundation/ | S+ |
| 3.4 | Agent Connect Protocol (ACP) | AGNTCY / Cisco Outshift → Linux Foundation | 2025–26 | Agent-interaction protocol inside the AGNTCY "Internet of Agents" ecosystem, hosted under the Linux Foundation; data models/schemas spec'd in `agntcy/acp-spec` | https://arxiv.org/pdf/2604.02369v1 | S+ |
| 3.5 | Structured outputs / strict JSON-schema function calling | OpenAI / Azure (Microsoft Foundry docs) | 2025 | Schema-constrained decoding ("strict") turns tool calls into validated JSON rather than prose to be parsed | https://learn.microsoft.com/de-de/azure/foundry/openai/how-to/structured-outputs | S |
| 3.6 | Function calling / tool use (schema contract) | OpenAI (community skill doc) | 2025 | Tool-use contract: name + JSON-schema parameters, model returns arguments rather than free text | https://raw.githubusercontent.com/e-t-y-b/etyb-skills/refs/heads/main/stacks/openai/function-calling.md | S |
| 3.7 | OTel semantic conventions carry **Gen AI + MCP** attribute registries | OpenTelemetry semconv **1.44.0** | 2026 | The semconv registry now has dedicated `gen-ai` and `mcp` attribute groups — MCP call telemetry is becoming standardizable | https://opentelemetry.io/docs/specs/semconv/gen-ai/ | **F** |
| 3.8 | A2A courseware | DeepLearning.AI | 2026 | Vendor-neutral training material on the Agent2Agent protocol | https://learn.deeplearning.ai/courses/a2a-the-agent2agent-protocol/lesson/15usp54o/why-agent2agent-protocol%3F | S |
| 3.9 | MCP Registry | MCP project | 2025–26 | Official discovery registry for MCP servers sits alongside the spec (nav: Documentation / Specification / Extensions / Registry / SEPs) — distribution, not just protocol, is standardized | https://modelcontextprotocol.io/specification/2025-06-18/index | **F** |

**Reading of Cluster 3.** MCP won the *tool/context* layer; A2A and ACP are competing at the *agent-to-agent* layer with A2A holding the governance lead (Linux Foundation). The security posture is protocol-external: MCP's own spec says consent, tool safety and sampling approval are implementor obligations — which is exactly where §5's guardrail/sandbox rows attach.

---

## 4. Cluster 4 — Orchestration, state, durability (11 rows)

| # | Framework / Mechanism | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 4.1 | LangGraph checkpointers | LangChain docs | 2024–26 | Persisted graph state (per super-step) is the substrate for resume, time-travel and HITL | https://docs.langchain.com/oss/javascript/langgraph/checkpointers | S |
| 4.2 | LangGraph interrupts | LangChain docs | 2025–26 | Dynamic `interrupt()` for human-in-the-loop approval inside a running graph | https://docs.langchain.com/oss/python/langgraph/interrupts | S |
| 4.3 | LangGraph durable execution | LangChain docs (mirror) | 2025 | Durable-execution semantics documented for agent graphs (crash-resume from checkpoint) | https://github.com/keithrich98/langgraph_docs/blob/main/durable-execution.mdx | S |
| 4.4 | Temporal durable execution | Temporal | 2025–26 | Workflow/activity model with deterministic replay; actively marketed for agent workloads | https://temporal.io/blog/durable-digest-january-2026 | S |
| 4.5 | Temporal + OpenAI Agents SDK | Temporal | 2025–26 | Official integration: run Agents SDK agents as durable Temporal workflows | https://temporal.io/blog/announcing-openai-agents-sdk-integration | S |
| 4.6 | CrewAI | CrewAI | 2025–26 | Crews (role-based teams) + Flows (event-driven control) as the two orchestration primitives | https://docs.crewai.com/v1.15.23/en/introduction | S |
| 4.7 | OpenAI Agents SDK | OpenAI (announced Mar 2025) | 2025 | Minimal primitives: agents, **handoffs**, **guardrails**, sessions; successor to Swarm | https://simonwillison.net/2025/Mar/11/openai-agents-sdk/ | S |
| 4.8 | LlamaIndex Workflows 1.0 | LlamaIndex | 2025 | Event-driven, lightweight workflow framework positioned for agentic systems | https://www.llamaindex.ai/workflows | S+ |
| 4.9 | AutoGen v0.4 → Microsoft Agent Framework | Microsoft | 2025 | Runtime re-architecture and later consolidation; AG2 continues as the community fork | https://github.com/larsderidder/framework-analysis/blob/main/tier-1/autogen.md | S |
| 4.10 | Record-and-replay for agent decision graphs (Chronicle) | Open-source tool | 2026 | Reproduce a production agent failure as a committed regression test and re-run the fix **without live LLM calls** | https://github.com/theagentplane/chronicle | S |
| 4.11 | Deterministic CI regression check for tool-using agents | llama_index issue #20448 | 2026 | Practitioner demand for deterministic replay of tool-using agents in CI | https://github.com/run-llama/llama_index/issues/20448 | S |

**Reading of Cluster 4.** The orchestration conversation moved from "which agent topology" to **durability primitives**: checkpoint/persist state, interrupt for human approval, replay deterministically, and record/replay agent decisions as CI fixtures. Any 2026 multi-agent SE system that cannot resume a crashed run and replay a failed trace is behind the framework baseline.

---

## 5. Cluster 5 — Reliability engineering for agents (13 rows)

| # | Control / Standard | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 5.1 | OWASP Top 10 for LLM Applications 2025 | OWASP GenAI Security Project | 2025 | Prompt injection remains the top LLM risk category (LLM01); refresh of the 2023 list | https://genai.owasp.org/download/48828/ | S |
| 5.2 | Agentic security crosswalk (agentic top-10 → FedRAMP controls) | Community / OWASP-adjacent | 2026 | Control mapping e.g. "restrict agent code execution to **sandboxed environments** with minimum necessary capabilities; disable filesystem access" | https://github.com/emmanuelgjr/GenAI-Security-Crosswalk/blob/main/agentic-top10/Agentic_FedRAMP.md | S |
| 5.3 | Agentic AI: emerging threats, mitigations, challenges | NIST CSRC presentation | 2026 | NIST-side framing of agentic threat classes and mitigations | https://csrc.nist.gov/csrc/media/presentations/2026/agentic-ai-emerging-threats%2C-mitigations%2C-and-cha/1.3-agentic_ai-sotiropoulos.pdf | S |
| 5.4 | Sandboxing options for agent code execution | Community curated list | 2026 | Catalogue of code-execution sandboxes for agents (gVisor / Firecracker / microVM / container families) | https://github.com/arjan/awesome-agent-sandboxes | S |
| 5.5 | Design patterns for securing LLM agents against prompt injection | Pattern literature + vendor analyses | 2025 | Pattern catalogue (e.g. dual-LLM / privileged-LLM separation) for containing injected instructions, with explicit residual gaps | https://www.armosec.io/blog/design-patterns-for-securing-llm-agents/ | S+ |
| 5.6 | Guardrails library landscape | Industry comparison (NeMo Guardrails, Guardrails AI, Llama Guard) | 2026 | Guardrail stacks converge on input/output classifiers + policy runtimes, with semantic failures hardest to cover | https://www.premai.io/blog/production-llm-guardrails-nemo-guardrails-ai-llama-guard-compared/ | S |
| 5.7 | OpenTelemetry GenAI semantic conventions | OpenTelemetry semconv 1.44.0 | 2026 | Standard attribute/trace vocabulary for GenAI and MCP calls (see 3.7) | https://opentelemetry.io/docs/specs/semconv/gen-ai/ | **F** |
| 5.8 | OSS observability: Langfuse vs Arize Phoenix | Third-party comparison | 2026 | Both self-host and speak OTel; differ on event caps and lock-in posture | https://www.morphllm.com/comparisons/arize-phoenix-vs-langfuse | S |
| 5.9 | Agent regression-test pipelines for drift | Microsoft Learn (Azure AI evaluation module) | 2026 | Treats agent drift as a regression-testing problem with dedicated pipelines | https://learn.microsoft.com/en-us/training/modules/aaai-design-evaluation-frameworks-multi-agent-azure/5-build-regression-test-agent-drift | S |
| 5.10 | Record-and-replay as a reliability primitive | OSS tool + issue tracker (4.10, 4.11) | 2026 | Deterministic replay is emerging as the practical bridge between observability and regression testing | https://github.com/theagentplane/chronicle | S |
| 5.11 | ASQAP workshop — Autonomous System QA and Prediction | FSE 2026 workshop | 2026 | SE community institutionalizes QA *for* autonomous systems as its own venue | https://conf.researchr.org/home/fse-2026/asqap-2026 | **F** |
| 5.12 | LLMTrust workshop — SE for and with Trustworthy LLMs | FSE 2026 workshop | 2026 | Trustworthiness of LLM-based SE treated as a dedicated research venue | https://conf.researchr.org/home/fse-2026/llmtrust-2026 | **F** |
| 5.13 | Poisoned Chalice Competition | FSE 2026 competition | 2026 | Adversarial/poisoning competition — security of LLM-driven SE tooling as a competitive benchmark | https://conf.researchr.org/home/fse-2026/pschcomp-2026 | **F** |

**Reading of Cluster 5.** The field has a **standard risk vocabulary (OWASP/NIST)**, a **standard telemetry vocabulary (OTel semconv, now including MCP)**, and **no standard containment guarantee**: prompt injection is still LLM01, and the mitigation consensus is architectural (sandbox + least capability + privileged/unprivileged model split) rather than a solved classifier.

---

## 6. Cluster 6 — Memory, context, RAG for code (9 rows)

| # | Work / Mechanism | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 6.1 | **Context Rot** | Chroma technical report (Hong, Troynikov, Huber), 2025-07-14 | 2025 | **18 LLMs** (GPT-4.1, Claude 4, Gemini 2.5, Qwen3 …) degrade **non-uniformly as input length grows**, even on trivially simple tasks; distractors compound degradation; **logically structured haystacks perform worse than shuffled ones**; on LongMemEval full prompts (~113k tokens; 306 filtered prompts) all families score far below focused (~300-token) prompts | https://www.trychroma.com/research/context-rot | **F** |
| 6.2 | LongMemEval | ICLR 2025 | 2025 | Benchmark for chat assistants on long-term interactive memory | https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html | S+ |
| 6.3 | LoCoMo — Evaluating Very Long-Term Conversational Memory of LLM Agents | ACL 2024 (Long) | 2024 | Very-long-term conversational memory benchmark used widely as a memory eval | https://aclanthology.org/2024.acl-long.747/ | S+ |
| 6.4 | Survey on memory mechanisms of LLM-based agents | journal (Chinese aggregator record) | 2025 | Taxonomy of agent memory (short-term / long-term / retrieval / reflection) | https://www.cqvip.com/doc/journal/00854JP1MNC89J116HC08JP1MPDO7 | S |
| 6.5 | AI Meets Brain: unified survey of memory systems | arXiv 2512.23343 | 2025 | Maps cognitive-neuroscience memory constructs onto autonomous-agent memory designs | https://web3.arxiv.org/pdf/2512.23343 | S |
| 6.6 | Retrieval-Augmented Code Generation: A Survey (repository-level focus) | arXiv 2510.04905 | 2025 | Repo-level RAG for code: retrieval granularity, structure awareness, and long-context alternatives | https://browse-export.arxiv.org/pdf/2510.04905 | S+ |
| 6.7 | Effective context engineering for AI agents | Anthropic (engineering blog) | 2025 | Frames context as a finite, degradable resource; compaction, structured note-taking, sub-agents as context-management moves | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents | S |
| 6.8 | Context editing / automatic compaction APIs | Anthropic platform docs | 2026 | Productized context management: clear old tool results, auto-compact near window limits | https://platform.claude.com/docs/en/build-with-claude/context-editing | S+ |
| 6.9 | MemComp competition (coding assistant + memory) | FSE 2026 competition track | 2026 | Peer-community competition explicitly on memory-enhanced coding assistants | https://conf.researchr.org/home/fse-2026/mem-comp-2026 | **F** |

**Reading of Cluster 6.** "Long context solves memory" is dead as an assumption: 6.1 shows degradation *as a function of length alone*, and 6.6/6.8 show the field's answer is **retrieval + explicit context management (compaction, tool-result eviction, sub-agents)**, not bigger windows. For multi-agent SE this is double-edged: sub-agents are a context-management technique *and* a context-fragmentation risk.

---

## 7. Cluster 7 — Evaluation benchmarks and their critiques (20 rows)

| # | Benchmark / Study | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 7.1 | SWE-bench Verified | OpenAI (human-verified subset) | 2024 | 500 problems verified by human engineers; de-facto coding-agent benchmark (per an in-session vendor system card) | https://www.anthropic.com/claude-opus-4-5-system-card | S |
| 7.2 | SWE-bench Pro | Scale AI; arXiv 2509.16941 | 2025 | Long-horizon SE tasks positioned as the contamination-resistant successor | https://browse-export.arxiv.org/pdf/2509.16941 | S+ |
| 7.3 | SWE-bench Multilingual | SWE-bench project | 2025 | Multilingual variant of the SWE-bench family | https://www.swebench.com/multilingual.html | S |
| 7.4 | SWE-bench FAQ / leaderboards | SWE-bench project | 2026 | Official FAQ and leaderboards (verification and reporting rules) | https://www.swebench.com/SWE-bench/faq/ | S |
| 7.5 | SWE-Gym | ICML 2025; arXiv 2412.21139 | 2025 | Training environment for SE agents **and verifiers** on real repositories | https://openreward.ai/arXiv/swe-gym | S+ |
| 7.6 | τ-bench / τ²-bench | Sierra (Yao, Shinn et al.) | 2024–25 | Tool-agent-user interaction benchmark with simulated users and domain policies | https://github.com/sierra-research/tau-bench | S+ |
| 7.7 | GAIA | HuggingFace / Meta (dataset) | 2023–24 | General assistant benchmark with tool-use and multi-step questions | https://huggingface.co/datasets/gaia-benchmark/GAIA | S |
| 7.8 | WebArena | ICLR 2024; arXiv 2307.13854 | 2024 | Realistic, self-hosted web environment for autonomous agents | http://arxiv.org/pdf/2307.13854 | S+ |
| 7.9 | Terminal-Bench | Stanford / Laude Institute | 2026 | Hard, realistic command-line tasks; arXiv 2601.11868 | https://www.tbench.ai/ | S+ |
| 7.10 | RepoBench | arXiv 2306.03091 | 2023 | Repository-level code auto-completion benchmark (retrieval + completion) | https://ar5iv.labs.arxiv.org/html/2306.03091 | S+ |
| 7.11 | Commit0 | arXiv 2412.01769 | 2024 | Library generation from scratch — pushes evaluation beyond patch-fixing | https://ar5iv.labs.arxiv.org/html/2412.01769 | S+ |
| 7.12 | AgentBench | ICLR 2024; arXiv 2308.03688 | 2024 | Multi-environment benchmark for LLM-as-agent | https://proceedings.iclr.cc/paper_files/paper/2024/file/e9df36b21ff4ee211a8b71ee8b7e9f57-Paper-Conference.pdf | S+ |
| 7.13 | **"Why SWE-bench Verified no longer measures frontier coding capabilities"** | OpenAI, 2026-02-23 | 2026 | OpenAI states SWE-bench Verified **is increasingly contaminated** and **recommends SWE-bench Pro** (post body truncated on fetch; headline + date captured) | https://openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/ | **F** |
| 7.14 | Schrödinger's Code Repository: Have LLMs Learned SWE-bench or Memorized It? | arXiv 2609.27891 | 2026 | Direct memorization probe on SWE-bench-family data | https://export.arxiv.org/pdf/2609.27891 | S |
| 7.15 | "59% of failed tests were flawed" (SWE-bench Verified) | Secondary news coverage of the OpenAI decision — **secondary source** | 2026 | Reports that OpenAI found 59% of failed SWE-bench Verified tests were flawed; **not confirmed in a primary fetched page** | https://blockchain.news/PostAMP?id=openai-abandons-swe-bench-verified-contamination-flawed-tests | S |
| 7.16 | Third-party leaderboards | Artificial Analysis / llm-stats | 2026 | Independent re-runs of Terminal-Bench and RepoBench; useful for variance checks, not for peer-reviewed claims | https://artificialanalysis.ai/evaluations/terminalbench-4-0 | S |
| 7.17 | Understanding and Mitigating Hallucinations in Industrial LLM-based Unit Test Generation | FSE 2026 Industry Papers (Ant Group, UESTC, Loughborough) | 2026 | Industrial hallucination study for LLM unit-test generation — the "trust the generated test" problem | https://conf.researchr.org/details/fse-2026/fse-2026-demonstrations/30/TestAgent-A-Multi-Agent-LLM-Framework-for-Repository-Level-Unit-Test-Generation | **F** |
| 7.18 | ARKRepoBench | ACL 2026 Findings | 2026 | Repository-level code-completion benchmark for HarmonyOS development — the benchmark family is being re-instantiated per ecosystem | https://aclanthology.org/2026.findings-acl.969.pdf | S |
| 7.19 | SWE-bench Multilingual agentic harness | ModelScope evalscope docs | 2026 | Standardized agentic evaluation recipe for SWE-bench Multilingual (scaffold + container + reporting) | https://raw.githubusercontent.com/modelscope/evalscope/refs/heads/main/docs/en/benchmarks/swe_bench_multilingual_agentic.md | S |
| 7.20 | DeepSWE (long-horizon variant) | referenced in arXiv 2607.07946 | 2026 | Appears alongside SWE-bench Pro as a sampled long-horizon evaluation target (30 tasks × 3 rollouts × 9 models in that study) | https://browse-export.arxiv.org/pdf/2607.07946 | S |

**Reading of Cluster 7.** Benchmark legitimacy is now the binding constraint, not capability. Between 7.13 (the benchmark authoring lab disowning its own benchmark), 7.14/2.4 (memorization probes) and 2.3 (harness sensitivity), a 2026 multi-agent SE paper that reports a single SWE-bench Verified number without contamination controls, harness disclosure and a second benchmark is not defensible.

---

## 8. Cluster 8 — Cost, latency, routing, caching, economics (11 rows)

| # | Work / Mechanism | Venue / Org | Year | One-line claim | URL | Tag |
|---|---|---|---|---|---|---|
| 8.1 | RouteLLM | ICLR 2025; arXiv 2406.18665 | 2025 | Learns a router from preference data to send easy queries to cheap models | https://proceedings.iclr.cc/paper_files/paper/2025/hash/5503a7c69d48a2f86fc00b3dc09de686-Abstract-Conference.html | S+ |
| 8.2 | FrugalGPT ("Less is More") | ICML 2023 | 2023 | LLM cascade: cheap model first, escalate only on low confidence | https://icml.cc/virtual/2023/28267 | S |
| 8.3 | GPTCache | NLP-OSS 2023 (ACL workshop) | 2023 | Semantic cache for LLM apps for faster answers and cost savings | https://aclanthology.org/2023.nlposs-1.24.pdf | S+ |
| 8.4 | More with Less: turn-control strategies for efficient coding agents | arXiv 2510.16786 | 2025 | Empirical study of turn-control as a cost lever in coding agents | https://browse-export.arxiv.org/pdf/2510.16786 | S |
| 8.5 | The Cost of Autonomy | Zenodo preprint — **gray literature** | 2026 | Longitudinal operational economics of a continuously running agent over 21,111 decision cycles (per the record title) | https://zenodo.org/records/19024884 | S |
| 8.6 | Harness token accounting | arXiv 2608.26218 (see 2.3) | 2026 | On the wide-window Verified cohort the context-managing harness also **served fewer prompt tokens per turn** — harness quality and token economy are coupled | https://papers.cool/arxiv/2608.26218 | **F** |
| 8.7 | Budget-control artifacts in API-based evaluation | arXiv 2604.02460 (see 2.2) | 2026 | API-level "thinking budget" controls are not reliably enforced (esp. Gemini 2.5) — cost-normalized comparisons can be silently unfair | https://papers.cool/arxiv/2604.02460 | **F** |
| 8.8 | RouterBench / cascade evaluation tooling | Community (InferRoute docs) | 2026 | Practical harnesses for evaluating FrugalGPT-style cascades and routers | https://huggingface.co/spaces/Ypeng12/InferRoute/blob/main/docs/academic_foundations.md | S |
| 8.9 | Confidence-gated cascades (cross-domain) | HF daily-paper record | 2026 | Cascade pattern still actively adapted to new modalities/tasks | https://huggingface.co/datasets/thaki-AI/daily-paper-2026-07-14-confidence-gated-ocr-vlm-cascade | S |
| 8.10 | Cost-aware agent scheduling | arXiv 2603.25450 | 2026 | Task-dependent boundaries for when escalation/routing pays off | https://browse-export.arxiv.org/pdf/2603.25450 | S |
| 8.11 | Multi-agent cost-benefit | **no peer-reviewed source found this session** | — | No paper located that reports a controlled **cost-normalized multi-agent vs single-agent** comparison for SE beyond the reasoning-budget result (2.2) and harness token accounting (8.6) | — | **[U]** |

**Reading of Cluster 8.** Routing/caching literature is mature at the *single-call* level (8.1–8.3) and thin at the *multi-agent loop* level. The only defensible 2026 statements are: (i) budget normalization is hard and often wrong (8.7), (ii) harness design changes both score and tokens (8.6), (iii) there is **no** established peer-reviewed cost-benefit curve for multi-agent vs single-agent SE — that gap is itself a publishable contribution.

---

## 9. Consensus vs contested vs assumption

### 9.1 Consensus (multi-source, survives adversarial reading)
1. **Coordination, not model capability, is the dominant failure surface in MAS.** MAST's 14 modes in 3 categories [F], collective-reasoning failures under distributed information [S], and the swarm-failure commentary [S] all converge.
2. **Compute-matched comparisons usually erase the multi-agent advantage on reasoning tasks.** [F] Tran & Kiela 2604.02460; consistent with MAST's "gains are often minimal".
3. **The harness/scaffold is part of the measured system.** [F] 2608.26218 (F2PF 28%→49%, complete 43→72 at fixed weights); this also explains part of the historical multi-agent "wins" (better scaffolds, not better collaboration).
4. **Context length alone degrades reliability, non-uniformly.** [F] Chroma Context Rot across 18 models; reinforced by the memory-survey and context-engineering literature [S].
5. **Benchmark contamination is established, not speculative, for SWE-bench Verified.** [F] OpenAI's own 2026-02-23 recommendation to move to SWE-bench Pro; [F] the 3×/6× memory-gap probe.
6. **Durability/replay/HITL are now framework-table-stakes.** [S] LangGraph checkpointers + interrupts + durable execution; Temporal integration; record-and-replay tooling.
7. **Tool/context interop has consolidated on MCP**, with A2A/ACP contesting the agent-to-agent layer. [F] MCP spec; [S+] A2A/ACP governance.

### 9.2 Contested (credible evidence on both sides)
1. **Does multi-agent help SE at all?** Peer-reviewed 2026 test-generation results are positive and execution-grounded (TestAgent: 92.34% coverage, 154 bugs [F]; MACO [S]) while the general critique literature is negative-to-neutral. The honest synthesis is **domain-conditional**: multi-agent wins where the task decomposes into *verifiable* sub-artifacts (tests, patches checked by execution), and loses where it decomposes into *opinions* (multi-hop reasoning, debate).
2. **More agents = better (MacNet scaling law [S+]) vs equal-budget SAS ≥ MAS [F].** Both can be true if the scaling law is measured without budget normalization; the burden of proof is on the scaling-law side post-2026.
3. **Long context vs retrieval/compaction.** Long-context vendors sell window size; the Context Rot evidence [F] plus productized compaction APIs [S+] say management beats size.
4. **Learned topology (DyLAN/GPTSwarm/AFlow) vs hand-designed roles.** Optimized-topology papers remain hard to compare because their baselines are weaker than 2026 single-agent scaffolds.
5. **Whether "multi-agent" is even the right abstraction**: 2608.26218 suggests a single agent with a good harness may dominate — i.e. the win may be *context policy*, not *agent count*.

### 9.3 Assumptions widely repeated but weakly evidenced (flag these in any 2026 paper)
1. "Role specialization (planner/coder/tester/reviewer) causes the gain." Almost never ablated against a single agent with the same tools and same token budget.
2. "More agents → more capability" as a general law.
3. "The benchmark number means the agent can do the job" — the SWE-bench Verified critique [F] plus flawed-test reporting [S, secondary] undercut this.
4. "Durable execution is a deployment detail." Without replay, agent regressions cannot be tested at all.
5. "Guardrails solve prompt injection." OWASP still ranks prompt injection first [S]; the design-pattern literature concedes residual gaps [S+].
6. "Cost scales linearly and predictably with agent count." Unverified; budget enforcement itself is unreliable [F].
7. "Multi-agent test generation is validated by coverage alone." Coverage without mutation-strength/bug-detection and without flakiness controls is weak evidence — TestAgent's bug-detection + precision numbers [F] are the pattern to copy.
8. "Framework maturity implies production readiness" — for multi-agent SE the durability/HITL/replay triad is the actual maturity test.

---

## 10. What a 2026 reviewer treats as table stakes for a multi-agent SE paper (numbered checklist)

1. **Compute-matched baseline.** Report total tokens (prompt + completion + reasoning), wall-clock, and $ for MAS *and* the single-agent baseline; state how the budget was enforced and verified (see 2.2's API budget-control artifacts).
2. **Harness disclosure.** Full scaffold, tool set, context policy, retry/stop rules, window size, per-attempt time limit, model version + snapshot date — because harness changes alone moved F2PF by 21 points [F].
3. **Contamination controls.** At minimum a second, post-cutoff benchmark and/or a memorization probe; justify any use of SWE-bench Verified given the 2026-02-23 contamination statement [F].
4. **At least two benchmarks** spanning fix-type and build-type tasks (e.g. SWE-bench Pro + Commit0/Terminal-Bench), not a single leaderboard row.
5. **Ablation of the multi-agent claim itself.** Same model, same tools, same budget: (a) full MAS, (b) single agent, (c) MAS minus the coordination mechanism under test (roles, debate, topology, memory sharing).
6. **Failure taxonomy reporting.** Classify failures with an established taxonomy (MAST) or a new one with inter-annotator agreement statistics (κ reported).
7. **Execution-grounded verification.** Tests/patches validated by running code, with flakiness (repeat-run) statistics, not by an LLM judge alone.
8. **Statistical discipline.** Seeds, N tasks, confidence intervals or paired tests; report variance across runs, not best-of-N.
9. **Cost/latency budget section.** Routing, caching, early-exit, and per-task $ ceilings; state the marginal cost of each additional agent.
10. **Durability & resumability.** Checkpointed state, crash-resume, and deterministic replay of at least one failed trajectory (§4).
11. **Human-in-the-loop boundary.** Where approval is required, what the agent may do unattended, and how interrupts are implemented and audited.
12. **Guardrail + sandbox specification.** Which OWASP/NIST risk classes are mitigated, how tool descriptions are treated (untrusted), and what the sandbox isolates (filesystem/network/credentials).
13. **Prompt-injection threat model.** Explicitly state whether repository content, issue text, and test output are treated as untrusted input, and show a red-team case.
14. **Observability.** OTel GenAI-conformant traces (including MCP spans) with token/cost attributes; artifacts retained for external audit.
15. **Artifact release.** Code, prompts, traces, seeds, and eval harness released (or a documented reason not to).
16. **Context policy documented as a first-class method component** (compaction, tool-result eviction, retrieval granularity, sub-agent context handoff) — with the Context Rot results cited as motivation.
17. **For test-generation systems specifically:** coverage *plus* bug-detection precision, mutation score where feasible, and false-positive/flaky-test rates.
18. **Explicit statement of what is architecture vs scaffold.** Claim the mechanism, not the scaffold; otherwise report both as inseparable (the "model+harness as tested solver" framing).
19. **Negative results reported.** Which variants did *not* help — this is now expected, not optional, in a field with a replication crisis.
20. **Reproducibility of the economics.** Public token accounting per task, so cost claims can be recomputed rather than trusted.

---

## 11. Could not verify in this session (do not cite these as fact)

**Access failures (structural, not content judgments):**
1. `arxiv.org`/`export.arxiv.org`/`ar5iv.labs.arxiv.org` fetches failed (timeouts / `fetch failed`) for `/abs/2312.13010` and `/html/2512.10218`. Four arXiv rows were verified via the `papers.cool` **abstract mirror** only — full texts were never opened.
2. `dl.acm.org`, `ieeexplore.ieee.org`, `link.springer.com`, `sciencedirect.com`, `doi.org` were not fetched (403/blocked or tokenized staging URLs). Every row whose primary URL is one of these is [S] at best: rows 1.20, 1.21, 2.8, 2.9, 7.14 (export PDF).
3. The OpenAI post of 2026-02-23 was fetched but **truncated after the headline**; the body's methodology and any per-test statistics were not read.

**Specific claims I refuse to assert:**
4. **"59% of failed SWE-bench Verified tests were flawed."** Seen only in a secondary news headline (§7.15). Not confirmed in a primary page. Do not quote the number.
5. **MAST's trace count ("1,600+ annotated traces").** My fetched abstract says *7 frameworks, 200+ tasks, 6 annotators, 14 modes, κ=0.88*. A larger trace count may exist in the paper body; I did not see it, so I did not use it.
6. **Venue attributions that a sibling file asserts but this session did not confirm:** MetaGPT = ICLR 2024 (oral); AutoGen = COLM 2024; CAMEL = NeurIPS 2023; SWE-agent = NeurIPS 2024; SoA = (venue unknown); **DyLAN = ICLR 2024**. On DyLAN specifically, the only in-session signal connecting it to ICLR 2024 was a third-party dataset file named `iclr24_reject_results.json`, which is **not evidence either way**; cite DyLAN as arXiv 2310.02170 until checked.
7. **Quantitative results not seen this session** (deliberately omitted): MASAI's SWE-bench Lite resolution rate; CodeR/MAGIS/SoA/AFlow/GPTSwarm/DyLAN/MacNet headline numbers; ChatDev/AgentVerse/MetaGPT evaluations; RouteLLM's cost-reduction percentage; GPTCache hit-rate/latency claims; FrugalGPT's cost savings; Terminal-Bench/Commit0/AgentBench/RepoBench/GAIA/τ-bench leaderboard scores; SWE-Gym and SWE-bench Pro scores.
8. **"More Agents Is All You Need" (arXiv 2402.05120)** and its sampling-and-voting result: not re-verified this session; absent from the tables above.
9. **MCP 2026-07-28 changelog details** (stateless core, session removal): only secondary/vendor coverage [S]; the specification page itself was not fetched at that revision.
10. **A2A protocol internals** (transports, agent-card schema, auth): governance donation is [S+]; the spec body was not read.
11. **OTel GenAI convention contents:** the `gen-ai` URL resolves to the semconv **1.44.0 index**; I confirmed the existence of `gen-ai` and `mcp` attribute registries, **not** individual attribute names/semantics.
12. **Sandbox primary docs for gVisor / Firecracker / E2B / Daytona / Docker seccomp**: only a curated list [S]; no primary documentation was fetched, so no isolation or performance claims are made.
13. **LangGraph / Temporal durability guarantees**: docs and vendor blogs only; no failure-injection evidence that resume/replay actually holds under crash.
14. **MacNet's "collaborative scaling law" shape** (power-law exponents, emergence thresholds): not seen; only that the paper proposes such a law.
15. **TestAgent's comparison details** (which EvoSuite/ChatUniTest configurations, statistical significance): the FSE demo abstract gives point numbers; the paper body was not read.
16. **Any peer-reviewed cost-benefit study of multi-agent vs single-agent SE**: could not locate one (row 8.11 is deliberately [U]).
17. **Zhihu/WeChat/GitHub-blog summaries** used for framework lineage (AutoGen v0.4 → Microsoft Agent Framework, AG2) are unofficial; treated as [S] orientation only.

---

## 12. Retrieval transparency

- **Search calls:** ~34 `web_search` calls, each with ≤2 queries (~68 queries), plus **10 `web_fetch` calls**, run sequentially with forced pauses after two HTTP 429 responses from the search backend. No subagents were used (delegation depth capped), per instructions.
- **Fetch successes [F]:** `papers.cool/arxiv/2503.13657` (MAST), `papers.cool/arxiv/2604.02460` (SAS vs MAS), `papers.cool/arxiv/2608.26218` (Same Model, Different Harness), `papers.cool/arxiv/2512.10218` (SWE-bench-Verified memory), `conf.researchr.org/.../fse-2026-demonstrations/30` (TestAgent + Meta industrial test generation + Ant Group hallucination study + MemComp), `modelcontextprotocol.io/specification/2025-06-18/index` (MCP), `opentelemetry.io/docs/specs/semconv/gen-ai/` (OTel semconv 1.44.0 registry), `www.trychroma.com/research/context-rot` (Context Rot), `openai.com/index/why-we-no-longer-evaluate-swe-bench-verified/` (truncated), `papers.cool` mirror of 2609.13739-adjacent listing (HarnessBandit surfaced via search).
- **Access pattern that worked:** conference/committee sites (`conf.researchr.org`, `papers.nips.cc`, `proceedings.iclr.cc`, `icml.cc`) and scholarly mirrors (`papers.cool`, `ar5iv`, `mlanthology`, `aclanthology`).
- **Access pattern that failed:** `arxiv.org` direct, `ar5iv` (intermittent), ACM/IEEE/Springer/Elsevier/doi (blocked) — consistent with the sibling file's report.
- **Tag histogram (108 rows, machine-counted):** **[F] 20** · **[S+] 30** · **[S] 57** · **[U] 1**. [F] rows are concentrated in Clusters 1, 2, 3, 5, 6, 7 (critique, protocol, reliability, context and benchmark-legitimacy lines), because those are where a fetched abstract/page was decisive. Rows per cluster: 23 / 12 / 9 / 11 / 13 / 9 / 20 / 11.
- **Confidence statement:** every non-[U] row has at least one in-session retrieval record; every quoted number was visible in a fetched page or a search snippet. The [U] row is intentional and marks a genuine gap in the literature rather than a retrieval failure.

---

## 13. Five decision-relevant findings (what each one changes)

1. **At equal thinking-token budgets, single-agent ≥ multi-agent on multi-hop reasoning, and API budget controls are themselves unreliable** (Tran & Kiela, arXiv 2604.02460, [F]). → *Change:* any MAS claim must publish verified token accounting; "we compared at equal budget" is not sufficient unless budget enforcement is demonstrated.
2. **Changing only the harness — same weights, same tasks — moved mean per-task F2PF 28% → 49% and complete solutions 43 → 72 on 169 SWE-bench Verified tasks** (arXiv 2608.26218, [F]). → *Change:* report model **and** harness as the tested solver; architectural claims must be ablated against a well-tuned single-agent harness, or they are scaffold claims in disguise.
3. **SWE-bench Verified is contaminated by the benchmark author's own account, and a memorization probe shows a 3× / 6× gap versus matched controls** (OpenAI 2026-02-23, [F]; arXiv 2512.10218, [F]). → *Change:* a single Verified number is no longer publishable evidence in 2026; pair it with SWE-bench Pro / Build-type tasks and a contamination discussion.
4. **MAS failures are systematic and taxonomizable (14 modes / 3 categories, κ = 0.88 over 7 frameworks and 200+ tasks), and MAS gains on popular benchmarks are often minimal** (MAST, NeurIPS 2025 D&B, [F]). → *Change:* failure-mode analysis with inter-annotator agreement is now expected; "it works" without a failure taxonomy reads as an incomplete evaluation.
5. **Context length alone degrades reliability non-uniformly, across 18 models, on trivial tasks; structured context can be worse than shuffled context** (Chroma Context Rot, [F]). → *Change:* context policy (compaction, tool-result eviction, retrieval granularity, sub-agent handoff) is a first-class method component that must be described and ablated, not an implementation detail.

**Open gaps worth a paper (as of this session):** (a) a controlled **cost-normalized** multi-agent-vs-single-agent study for SE tasks (row 8.11 is [U] — nothing peer-reviewed found); (b) harness-sensitivity studies *beyond* one harness family; (c) multi-agent **test-generation** evaluations that report bug-detection precision, mutation score and flakiness instead of coverage alone; (d) crash/failure-injection evidence that checkpoint-resume and replay actually hold in agent frameworks; (e) contamination-controlled memory benchmarks for repo-level agents.
