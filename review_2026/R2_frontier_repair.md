# R2 — Frontier Program Repair: 2025–2026 SOTA Numbers for Multi-Agent APR, LLM APR, and Self-Healing Runtimes

**Compiled:** 2026-10-10 · **Method:** primary sources (arXiv/ACL Anthology/Springer/Elsevier/IEEE/DBLP/Semantic Scholar API/official leaderboards), direct page + PDF retrieval and text extraction. Every number below is quoted from a retrieved source. Nothing is inferred from memory.

---

## 1. State of the art in one line

**Multi-agent and agentic repair has decisively taken over the leaderboards, but the frontier has split three ways: (a) *repository-level* SWE-bench Verified is saturated and mostly self-reported — the **official** swebench.com leaderboard tops out at **79.2%** with its newest submission dated **Feb 2026**, while third-party aggregators advertise **96%** for unsubmitted 2026 models; (b) *real-bug Java APR* has a credible new SOTA of **420/835 (50.3%) on Defects4J v2.0** (MultiFixer + Claude-3.5-Sonnet, arXiv 2026); and (c) the *latent-communication* branch (LaMAR, ASE 2026) is real and peer-reviewed but only reaches **24.5% on Defects4J with Qwen3-8B** — its headline advantage is theoretical (token complexity O(N²)→O(N)), not an empirically demonstrated cost win.** Meanwhile the widely-circulated "**85% MTTR reduction**" self-healing claim traces to **a personal GitHub README**, not to any paper.

---

## 2. Main table

Grades: **A** = ICSE/FSE/ASE/ISSTA/TOSEM/TSE/NeurIPS/ICLR/ACL/OSDI/SOSP · **B** = arXiv/workshop/other peer-reviewed venue outside the A list · **C** = report/blog/vendor/self-report.
"Claim ok?" refers to the claim as stated in the task brief.

### 2.1 Multi-agent repair frameworks

| System | Metric | Value | Benchmark | Evaluation conditions | Authors, year, venue | URL / DOI | Grade | Claim ok? |
|---|---|---|---|---|---|---|---|---|
| **LANTERN** | Pass@10 improvement (Rust) | **+22.09%** (Rust); then Go +11.31%, PHP +9.33%, Kotlin +8.87%, C# +8.82%, Ruby +8.33%; p=0.0126, Cliff's δ=0.64 | xCodeEval **Compact Set** — 5,068 bugs, 11 langs | DeepSeek-V3 as analyzer+translator+repairer; multi-agent iterative; no training | Luo, Keung, Yang, Klein, Bissyandé, Tian, Le — **ICSE 2026 Research Track** | [doi 10.1145/3744916.3773227](https://doi.org/10.1145/3744916.3773227) · [arXiv 2503.22512v5](https://arxiv.org/abs/2503.22512v5) | A | ✅ **Accurate** (but "22.09%" pp-vs-relative is ambiguous; see §3.1) |
| **FedDualFix** | Correct repairs (CR) / Top-1 precision (P@1) | **CR = 58**, PR = 84, **P@1 = 52.1%** | Defects4J v2.0, 3-client federated | GPT-4o, temp 0.2, top-p 0.95, ≤5 candidates/bug, ≤5 attempts; 3.8 LLM calls/bug, 3.3k tokens/bug | Ju, Liu, Li, Wang, Cao, Chen — 2026, *Applied Soft Computing* **202**:115898 | [doi 10.1016/j.asoc.2026.115898](https://doi.org/10.1016/j.asoc.2026.115898) | B (Q1 Elsevier; not in A list) | ✅ **Accurate** |
| **TraceCoder** | Relative Pass@1 gain | **+34.43%** relative (82.00% vs 61.00% best baseline on ClassEval); 90.72% avg across 5 benchmarks vs 81.05% | HumanEval, HumanEval+, ClassEval, BigCodeBench-Complete/-Instruct | Gemini-2.5-Flash-0417; ≤5 repair attempts; multi-agent (Instrumentation/Analysis/Repair); **repairs LLM-generated code** | Huang, Ye, Sun, Zhang, Zhang, Liu — **ICSE 2026** | [doi 10.1145/3744916.3773187](https://doi.org/10.1145/3744916.3773187) · [arXiv 2602.06875](https://arxiv.org/abs/2602.06875) | A | n/a (no numeric claim in brief) |
| **AgentRepair** | — | **NOT VERIFIED** | — | AST-anchored, retrieval-augmented, cold-start | Lee, Yang et al. — IEEE Xplore doc **11320358** | [ieeexplore 11320358](https://ieeexplore.ieee.org/document/11320358) | — | ❌ **Existence only; zero metrics verified** |
| **LaMAR** | Repair success rate | **24.5%** on Defects4J; **62.1%–87.5%** on DebugBench & QuixBugs | Defects4J (Java), DebugBench, QuixBugs | **Qwen3-8B**; dual-chain (Bug Analysis Chain + Repair Chain), 4 latent agents; optional multi-round | Jiao, Zhang, Feng, Li — **ASE 2026** (41st IEEE/ACM ASE) | [doi 10.1145/3832783.3837423](https://doi.org/10.1145/3832783.3837423) | A | ✅ **Accurate** |
| **DEIMerge** | — | **NOT VERIFIED** | — | Multi-agent + intelligent patch merging | Liang, Zhao, Mo — **PRICAI 2025** | [doi 10.1007/978-981-95-7081-2_16](https://doi.org/10.1007/978-981-95-7081-2_16) | B | ❌ **Abstract elided by publisher; no numbers obtainable** |
| **PhoenixRepair** | Pass@1 resolve rate | **76.0%** (MiniMax-M2.5); +7.8% relative over SWE-agent (DeepSeek-V3.1) | SWE-bench Verified | Multi-location sampling + iterative reflection/refinement; optional graph localization | Jiang + 9 authors — 2026-07-21, arXiv preprint | [arXiv 2607.18859](https://arxiv.org/abs/2607.18859) | B | n/a (new find) |
| **MultiFixer** ⭐new | Bugs fixed | **420/835 (50.3%)** with Claude-3.5-Sonnet; 326 with base model (62 multi-method, 27 multi-file, 46 multi-hunk of 95 unique) | Defects4J (**835 bugs**) + VUL4J, SEC-bench, PatchEval | Coordinator-Proposer multi-agent; claims "new SOTA on Defects4J" | 2026, arXiv preprint | [arXiv 2607.26591](https://arxiv.org/abs/2607.26591) | B | n/a (new find) |
| **SWE-Master** ⭐new | Resolve rate | **61.4%** (Qwen2.5-Coder-32B); **70.8%** at TTS@8 | SWE-bench Verified | Post-training (SFT + RL + test-time scaling) — *not* multi-agent | 2026, arXiv technical report | [arXiv 2602.03411](https://arxiv.org/abs/2602.03411) | B | n/a (new find) |

### 2.2 SWE-bench family — official leaderboard (swebench.com), extracted from embedded JSON

| Split | Instances (verified) | Best reported | Best with published cost | Newest submission |
|---|---|---|---|---|
| **Verified** | **500** (counted from per-instance JSON) | **79.2%** — Claude 4.5 Opus + Sonar Foundation / live-SWE-agent, 2025-12-15 | **76.8% @ $0.7539/instance**, 32.9 calls — Claude 4.5 Opus + mini-SWE-agent, 2026-02-17 | 2026-02-26 |
| **Lite** | 300 (nominal) | **60.33%** — ExpeRepair-v1 + Claude 4 Sonnet, 2025-06-25 | not published | 2025-09-11 |
| **Test (full)** | — | **52.62%** — Claude 4.5 Opus + Sonar Foundation, 2025-12-19 | not published | 2025-12-19 |
| **Multimodal** | — | **35.98%** — o3 + GUIRepair / Codefuse_Pycfun, 2025-11-17 | not published | 2025-11-17 |
| **Multilingual** | **300** (counted from per-instance JSON) | **72.7%** — Gemini 3 Flash + mini-SWE-agent, 2026-02-13 | **72.7% @ $0.3518/instance**, 52.5 calls | 2026-02-20 |

**Cost–performance Pareto, SWE-bench Verified (official, mini-SWE-agent scaffold, per-instance USD):**

| $/instance | Resolve | Model | Calls/instance | Date |
|---|---|---|---|---|
| **$0.0281** | 60.0% | DeepSeek V3.2 Reasoner | 46.4 | 2025-12-01 |
| $0.0355 | 59.8% | GPT 5 mini | 14.5 | 2025-08-07 |
| **$0.0733** | **75.8%** | **MiniMax M2.5** | 60.5 | 2026-02-17 |
| $0.1466 | 70.8% | Kimi K2.5 | 51.2 | 2026-02-17 |
| $0.3560 | 75.8% | Gemini 3 Flash | 56.1 | 2026-02-17 |
| $0.4494 | 72.8% | GPT 5.2 Codex | 28.1 | 2026-02-19 |
| $0.5515 | 75.6% | Claude 4.6 Opus | 28.9 | 2026-02-17 |
| $0.7539 | **76.8%** | Claude 4.5 Opus | 32.9 | 2026-02-17 |
| $1.5311 | 21.62% | GPT-4o | 63.1 | 2025-07-20 |

> **Cost-efficiency headline:** MiniMax M2.5 reaches 75.8% at **$0.0733/instance** — within **1.0 pp** of Claude 4.5 Opus's 76.8% at **$0.7539/instance**, i.e. **~10.3× cheaper for ~1 pp**. Any new system that reports only resolve rate without $/instance or tokens/instance is not comparable to the 2026 frontier.

### 2.3 APR on Defects4J / Java real-bug benchmarks

| System | Metric | Value | Benchmark | Conditions | Source | Grade |
|---|---|---|---|---|---|---|
| **MultiFixer** | Bugs fixed | **420** / 835 | Defects4J v2.0 | Claude-3.5-Sonnet | [arXiv 2607.26591](https://arxiv.org/abs/2607.26591) | B |
| **FedDualFix** | CR / P@1 | 58 / 52.1% | Defects4J v2.0 (subset) | GPT-4o, 3-client federated | [doi 10.1016/j.asoc.2026.115898](https://doi.org/10.1016/j.asoc.2026.115898) | B |
| **LaMAR** | Repair success | **24.5%** | Defects4J | Qwen3-8B, latent KV-cache comms | [doi 10.1145/3832783.3837423](https://doi.org/10.1145/3832783.3837423) | A |
| GPT-4o Direct (control) | CR / P@1 | 49 / 44.1% | Defects4J v2.0 (same subset) | Same-backend single agent | [doi 10.1016/j.asoc.2026.115898](https://doi.org/10.1016/j.asoc.2026.115898) | B |
| ITER (best native baseline) | CR / P@1 | 50 / 43.3% | Defects4J v2.0 (same subset) | Native backbone | same | B |
| **Defects4J v3** | — | **NOT VERIFIED — no evidence such a release exists** | — | — | searched GitHub releases/tags, DBLP, general web | — |

### 2.4 Latent-space / non-text agent communication

| Work | Metric | Value | Conditions | Source | Grade |
|---|---|---|---|---|---|
| **LaMAR** | Defects4J repair success | **24.5%** | Qwen3-8B, 3 benchmarks, 3 model families | [doi 10.1145/3832783.3837423](https://doi.org/10.1145/3832783.3837423) | A |
| **LaMAR** | Token complexity (theoretical) | **O(N²) → O(N)** | Proven property of LAC framework | same | A |
| **LaMAR** | Ablation | Latent communication + bug-analysis chain are "the most critical components" | Qualitative; **no token-cost ablation number published** | same | A |
| *Beyond tokens* (survey) | Methods catalogued | **18** methods, 2024–2026, 3-axis taxonomy | 1 author | [arXiv 2606.05711](https://arxiv.org/abs/2606.05711) | B |
| *Safety of Latent Communication* | Harmful-compliance score | **27.9 → 76.9** | 3 topologies, 4 safety benchmarks; link-training attack | [arXiv 2609.39788](https://arxiv.org/abs/2609.39788) | B |

> **Important:** the task brief asked for "any 2026 ablation showing [latent communication's] effect on repair success **or token cost**." **No paper I could retrieve reports a measured token-cost or dollar-cost reduction from latent communication in a repair setting.** LaMAR's cost claim is a *proof about asymptotic token complexity*, and its published ablation is qualitative. Treat "latent communication is cheaper in practice for APR" as **NOT VERIFIED**.

### 2.5 Self-healing / self-repair runtime systems

| System | Metric | Value | Benchmark / setting | Conditions | Source | Grade |
|---|---|---|---|---|---|---|
| **VIGIL** | Premature toasts; mean latency; frustration events | 12/12 → **0/12**; **97 s → 8 s**; **8 → 0** | Single synthetic 12-event case study (agent "Robin-A") | Single author; batch reflection; no benchmark | [arXiv 2512.07094](https://arxiv.org/abs/2512.07094) | C/B (preprint, n=12) |
| **FTDI** | Recovered lost performance | **up to 95.65%** | HumanEval (164), HumanEval+, MBPP; injected Coder faults | Budget B=(R_max,T_max); Planner→Coder→Tester; **function-level code generation, not real bugs** | *Expert Systems with Applications* 2026 — **verified only via secondary Chinese-language summary** | B (venue) / C (my source) |
| **CrewAI SRE** | RCA accuracy; fix success; resolution time | **96%**; **73%**; **"hours → under 28 min"** | "Simulated production environment" | CrewAI + DeepSeek-R1/GPT-4o; K8s, Middleware.io, Jira, GitHub | Manohar, Shukla, Abi — ICSSSM 2025, Atlantis Press, [doi 10.2991/978-94-6463-950-6_35](https://doi.org/10.2991/978-94-6463-950-6_35) | C |
| **ESBMC-AI** | "high accuracy" (**no number given**) | **NOT VERIFIED** | 50,000 C programs from FormAI | ESBMC bounded model checking + pre-trained transformer; **C only; described as "proof of concept"** | Charalambous, Tihanyi, Jain, Sun, Ferrag, Cordeiro — AST 2025, [doi 10.1109/AST66626.2025.00020](https://doi.org/10.1109/AST66626.2025.00020) · [arXiv 2305.14752](https://arxiv.org/abs/2305.14752) | B |
| **agent-sandbox** | **none — not a self-healing system** | n/a | kubernetes-sigs/agent-sandbox | Infrastructure for isolated agent runtimes; publishes no repair/MTTR metrics | [github.com/kubernetes-sigs/agent-sandbox](https://github.com/kubernetes-sigs/agent-sandbox) | C |
| **"85% MTTR reduction"** | MTTR reduction | **85%** (self-reported) | Azure DevOps pipelines, personal project | **Origin: a personal GitHub README.** No paper, no benchmark, no methodology, no peer review | [github.com/suhail39ahmed/self-healing-azure-pipelines](https://github.com/suhail39ahmed/self-healing-azure-pipelines) | **C — see §3.5** |

### 2.6 Repair evaluation methodology, overfitting, reward hacking

| Work | Finding | Value | Venue | Source | Grade |
|---|---|---|---|---|---|
| **"Self-Repair Trap"** (DCAware) | Named phenomenon defined | "iterative repair progressively drives models toward assertions that are easier to satisfy but less effective at detecting faults" | **ASE 2026** | [arXiv 2608.05917](https://arxiv.org/abs/2608.05917) | A |
| **ImpossibleBench** | Cheating rate = pass rate on "impossible tasks" | Framework verified; **specific per-model rates NOT VERIFIED** | **ICLR 2026** | [github.com/safety-research/impossiblebench](https://github.com/safety-research/impossiblebench) (paper not directly retrieved) | A (venue) / unverified numbers |
| **Abstain and Validate** | Success-rate gain from bug abstention + patch validation | **+13 pp** (abstention), **+15 pp** (validation), **up to +39 pp** combined | **ICSE-SEIP 2026** | [arXiv 2510.03217](https://arxiv.org/abs/2510.03217) | A |
| **"Whose Oracle Is It?"** | Test-changing repairs | 230 merged bug-fix PRs, 9 repos; **160/172 (93.0%)** test-changing repairs edit a pre-existing test artifact; 87/172 delete test lines but only 53 delete an assertion/case/expected output/file | venue not determined | [binds.ch PDF](https://binds.ch/papers/whoseoracle2026.pdf) | ungraded |
| **FedDualFix** | Plausible-but-incorrect patch rate | **26/84 = 31.0%** of plausible patches are incorrect (84 plausible − 58 correct) | *Applied Soft Computing* 2026 | [doi 10.1016/j.asoc.2026.115898](https://doi.org/10.1016/j.asoc.2026.115898) | B |
| **HEJ-Robust** | Robustness drop under semantics-preserving transforms | **>50%** performance drop under several of 8 transformations | AIware 2026 | [doi 10.1145/3805760.3814929](https://doi.org/10.1145/3805760.3814929) · [arXiv 2605.02215](https://arxiv.org/abs/2605.02215) | B |

### 2.7 Memory-augmented / dynamic-analysis repair

| System | Metric | Value | Benchmark | Conditions | Source | Grade |
|---|---|---|---|---|---|---|
| **TwinMem-Agent** | Pass@1; cost | **89.1% vs 60.0%** baseline; **~18× lower cost ($0.0044 vs $0.0798)** | **stratified 8×25 = 200-instance subset of SWE-Bench Pro** — *not* full SWE-Bench Pro | DeepSeek-V3.2; baseline mini-swe-agent; identical Dockerized instances; no fine-tuning | Wu, Luo, Mu, Xiang — **SIGSOFT FSE Companion 2026** ([doi 10.1145/3803437.3807664](https://doi.org/10.1145/3803437.3807664)) | B (companion, not main track) |
| **TwinMem-Agent** | Memory ablation | −8 pp Pass@1, −12 pp RSR (25 Ansible instances) | subset | Removing memory module | same | B |
| **ADI** | Resolve rate; cost | **63.8%** on SWE-bench Verified; **$1.28/task** | SWE-bench Verified | Claude-Sonnet-3.7; function-level Frame Lifetime Trace; +6.2%–18.5% when plugged into existing SOTA agents | Xiang, Xu, Chu, Tian, Zhang — *Proc. ACM Softw. Eng.* (PACMSE) 2026, [doi 10.1145/3797126](https://doi.org/10.1145/3797126) · [arXiv 2604.24212](https://arxiv.org/abs/2604.24212) | A | 

### 2.8 Benchmark sizes — verified and corrected

| Benchmark | Claimed in brief | **Verified** | Composition | Source | Grade |
|---|---|---|---|---|---|
| **RunBugRun** | 716,900 pairs, 9 langs | ✅ **CORRECT for the EMSE 2026 journal version** — but **arXiv v1/v3 (2023) said 450,000 pairs / 8 langs** | C, C++, Java, Python, JS, Ruby, Go, PHP (+1); baselines CodeT5, Qwen3-Coder, Devstral | Prenner & Robbes, *Empirical Software Engineering* **31**:98, publ. 2026-03-24, [doi 10.1007/s10664-025-10790-3](https://doi.org/10.1007/s10664-025-10790-3); arXiv [2304.01102](https://arxiv.org/abs/2304.01102) | B (EMSE = CORE A*) |
| **xCodeEval** | 5,068 bugs, 11 langs | ⚠️ **Partially correct** — **5,068 is the *Compact Set* (APR subset)**, *not* the whole benchmark. Full xCodeEval = **25M samples, 7,514 unique problems**, 11 langs, 7 tasks | C, C#, C++, Go, Java, JS, Kotlin, PHP, Python, Ruby, Rust; ~50 tests/problem | Khan et al., NeurIPS 2023 D&B, [arXiv 2303.03004](https://arxiv.org/abs/2303.03004); subset counts confirmed in LANTERN §5.2.2 | A (2023) |
| **CI-Bench** | size unknown | **100 real-world CI/CD failures** evaluated; framework built **on top of BugSwarm** | Agentless 28%, SWE-agent 35%, AutoCodeRover 13% max success; GPT-4o / Claude-3.5-Sonnet / DeepSeek-V3 | Zhu, Nabil, Rubio-González — **ICSE 2026 Companion**, [doi 10.1145/3774748.3787606](https://doi.org/10.1145/3774748.3787606) | B (Companion) |
| **BugSwarm** | size unknown | **3,091 fail-pass pairs**, Java + Python, fully reproducible containers | MSR 2019 | Tomassi et al., [arXiv 1903.06725](https://arxiv.org/abs/1903.06725) | B |
| **ARC-APR** | — | ❌ **NOT VERIFIED — no evidence it exists.** Multiple phrasings ("ARC-APR benchmark", "ARC APR automated program repair") returned nothing matching | — | — | — |
| **HEJ-Robust** | — | ✅ **EXISTS: 1,450 transformed instances** | Built from HumanEval-Java-Bug via 8 semantics-preserving transformations; 5 fine-tuned LLMs | Rabbi & Yang, **AIware 2026**, [doi 10.1145/3805760.3814929](https://doi.org/10.1145/3805760.3814929) | B |
| **LogicEval / LogicDS** | 122 logical vulnerabilities | ✅ **CORRECT: 122** | First dataset of logical (non-memory-safety) vulnerabilities w/ tangible security impact | Rashid, Ishtiaq, Tu, Dong, Wu, Ranjbar, Yang, Sultana, Mehnaz, Hussain — **ACL 2026 Long**, pp. 46025–46049, [doi 10.18653/v1/2026.acl-long.2136](https://doi.org/10.18653/v1/2026.acl-long.2136) | A |
| **SWE-bench Verified / Lite** | — | **500** / **300** (Verified counted from official per-instance JSON) | Python OSS repos | official swebench.com leaderboard JSON | A |
| **SWE-bench Pro** | — | ✅ **1,865 problems, 41 repos** | public set = 11 repos; held-out = 12; commercial = 18 (results released) | [arXiv 2509.16941](https://arxiv.org/abs/2509.16941) | B |
| **SWE-smith / SWE-Gym** | — | **NOT VERIFIED** (exact instance counts not retrieved) | — | — | — |

---

## 3. Per-system details

### 3.1 LANTERN — claim ✅ accurate, with one ambiguity

`arXiv:2503.22512v5`, last revised 2026-03-30; accepted to **ICSE 2026 Research Track** ([conf.researchr.org listing](https://conf.researchr.org/details/icse-2026/icse-2026-research-track/185/Unlocking-LLM-Repair-Capabilities-Through-Cross-Language-Translation-and-Multi-Agent-)). Authors: Wenqiang Luo, Jacky Wai Keung, Boyang Yang, Jacques Klein, Tegendé F. Bissyandé, Haoye Tian, Bach Le. DOI **10.1145/3744916.3773227**.

Exact quotes:
> "Our technique strategically translates defective code from languages where LLMs exhibit weaker repair capabilities to languages where they demonstrate stronger performance, without requiring additional training."
> "We evaluate our method on xCodeEval, a comprehensive multilingual benchmark comprising 5,068 bugs across 11 programming languages. Results demonstrate significant enhancement in repair effectiveness, particularly for underrepresented languages, with Rust showing a **22.09% improvement in Pass@10** metrics."
> §5.2.2: "We use one of the subsets provided by xCodeEval, **Compact Set** … The Compact Set comprises a total of **5,068 bugs across 11 languages**."
> §5.2.1: "We use the open-source state-of-the-art **DeepSeek-V3** model as the LLM in the analyzer and translator… We also leverage the same LLM for the repairer."
> "It is worth noting that Rust bugs benefit the most from translation-based repair, which achieves an **increment of 22.09%**. Following are the Go, PHP, Kotlin, C#, and Ruby bugs that undergo improvements of 11.31%, 9.33%, 8.87%, 8.82%, and 8.33%. Our statistical tests further confirm the improvements with a **p-value of 0.0126** and a **Cliff's Delta of 0.64** (large effect)."
> Baseline context: "the state-of-the-art LLM initially achieves Pass@10 scores of **89.02%** and **89.93%** for Python and PHP… for less common languages such as Rust, the Pass@10 score drops dramatically to only **65.58%**."

**Ambiguity to flag:** the paper writes both "improvement of 22.09%" and "increment of 22.09%". If this is **percentage points**, Rust Pass@10 goes 65.58% → ~87.7%. If **relative**, 65.58% → ~80.1%. The paper does not disambiguate in the text I retrieved; Figure 6 holds the resolution. Do not cite this as an absolute Pass@10 value without checking the figure.

### 3.2 FedDualFix — claim ✅ accurate

*Applied Soft Computing* **202** (2026) 115898; DOI 10.1016/j.asoc.2026.115898; DBLP `journals/asc/JuLLWCC26`. Authors: Xiaolin Ju, Qingyun Liu, Chang Li, Haochen Wang, Heling Cao, Xiang Chen (Nantong University; Nanjing University; Henan University of Technology). Retrieved from the authors' own PDF at `ntu-juking.github.io/files/ASOC-2026-01-Self.pdf`.

> Highlight: "On Defects4J, achieves **58 correct repairs and 52.1% Top-1 precision**, outperforming Recoder and CodeT5."
> "GPT-4o Direct … correctly repairs **49 bugs** and achieves **44.1% P@1**, compared with **58 correct repairs and 52.1% P@1** achieved by FedDualFix."
> "FedDualFix achieves 58 correct repairs and 52.1% P@1, compared with **36 correct repairs and 32.6% P@1 for Fed-CodeT5**" — with the authors' own caveat: "**this cross-system comparison is not capacity-controlled**: Fed-CodeT5 uses the 220M-parameter CodeT5 backbone, whereas FedDualFix relies on the substantially more capable proprietary GPT-4o backend."
> "The adaptive scheduling mechanism reduces inference time by **more than 25%**."
> "58 correct and 84 plausible repairs, with a Top-1 precision (P@1) of **52.1%**." vs best native baseline ITER: "improves CR from 50 to 58 and P@1 from 43.3% to 52.1%" (p<0.05 McNemar, Holm–Bonferroni).
> Cost: "Avg. tokens / bug **3.3k** … Approx. cost / bug (USD) **0.007–0.009**"; GPT-4o config cost **$0.028/bug**.
> Plausible-but-incorrect: "**26 cases** derived from the difference between 84 plausible and 58 correct repairs."
> Dataset scope: "Defects4J contains over 800 real-world bugs spanning 17 mature open-source Java projects."

**Caveats I must flag.** (1) The paper never states the number of evaluated Defects4J instances in the retrievable text. `58 / 0.521 ≈ 111`, but the implied denominator varies from ~109 (TBar) to ~116 (GraphCodeBERT, SimFix) across baselines, which suggests per-client averaging rather than a single N. **Do not report "58/111" as fact** — the exact instance list is in their replication package ([github.com/Liuqy1213/FedDualFix](https://github.com/Liuqy1213/FedDualFix)). (2) The authors explicitly warn that comparisons against native baselines (CodeT5, Recoder, ITER…) "are not used to attribute the full improvement exclusively to the proposed multi-agent design." (3) This is a Q1 Elsevier journal but **not** in the A-list venues.

### 3.3 TraceCoder — verified; but read the benchmark carefully

`arXiv:2602.06875v1` (2026-02-06); ACM DOI **10.1145/3744916.3773187**; conference line in the paper reads: "2026 IEEE/ACM 48th International Conference on Software Engineering; April 12–18, 2026; Rio de Janeiro, Brazil." Authors: Jiangping Huang, Wenguang Ye (CQUPT), Weisong Sun (NTU, corresponding), Jian Zhang (Beihang), Mingyue Zhang (SWU), Yang Liu (NTU).

> "TraceCoder achieves up to a **34.43% relative improvement in Pass@1** accuracy over existing advanced baselines."
> "using **Gemini-2.5-Flash-0417** on ClassEval, TraceCoder achieves a Pass@1 score of **82.00%**, surpassing the second-best baseline (**61.00%**) by a relative margin of 34.43%."
> "When averaged across all benchmarks, TraceCoder reaches **90.72%** with Gemini, outperforming the strongest baseline (**81.05%**) by 11.93%."
> "We limit all iterative methods, including TraceCoder and the iterative baselines, to a **maximum of 5 repair attempts**."
> "semantic preservation rate of over **99%**" for instrumentation purity.
> Ablation: "the iterative repair process alone contributing a **65.61% relative gain** in accuracy."

**Caveat:** TraceCoder repairs **LLM-generated code** on function/class-level benchmarks (HumanEval, HumanEval+, ClassEval, BigCodeBench) — **not** Defects4J or SWE-bench, and not real-world repository bugs. Its 82% ClassEval number is not comparable to Defects4J repair rates. The brief's own parenthetical ("observe-analyze-repair") is an accurate description of the architecture (Instrumentation Agent → Analysis Agent → Repair Agent).

### 3.4 LaMAR — claim ✅ accurate; the cost advantage is theoretical

`arXiv`-independent; **ASE 2026** (Proceedings of the 41st IEEE/ACM International Conference on Automated Software Engineering), DOI 10.1145/3832783.3837423. Authors: Rui Jiao, Yue Zhang, Zhe-Xuan Feng, Jin-Ku Li.

> Abstract: "We develop **Latent Agent Communication (LAC)**… and prove it provides a communication channel with strictly higher information capacity while **reducing token complexity from O(N²) to O(N)**. We instantiate LAC as **LaMAR**, a dual-chain repair system: Bug Analysis Chain diagnoses the bug through **four collaborating latent agents**; Repair Chain refines the patch through multi-agent latent collaboration with cross-chain context transfer… **LaMAR with Qwen3-8B achieves 24.5% repair success rate on Defects4J and 62.1%–87.5% on DebugBench and QuixBugs**, outperforming all baselines in the large majority of settings. **Ablation experiments identify the bug analysis chain and latent communication as the most critical components.**"

**Two caveats.** (1) 24.5% on Defects4J with an 8B model is *weak* in absolute terms — it is well below agentic systems on repository-level tasks and below MultiFixer's 50.3%. (2) The brief's framing that latent communication helps "token cost" is supported only by an asymptotic proof; the retrieved abstract reports **no measured token or dollar figure**. I could not retrieve a cost ablation.

### 3.5 The "85% MTTR" claim — origin found; it is a personal README

Searched `"85% MTTR reduction"`, `"MTTR reduction 85% self-healing LLM"`, `"reduced MTTR by 85%"`. The claim resolves to a single personal GitHub project:

> Repository description: "Autonomous agentic AI system for self-healing Azure DevOps pipelines using Cursor, Claude, and MCP Agents. **Reduces MTTR by 85%.**"
> README "Key Results": "**85% reduction in Mean Time To Recovery (MTTR)**" · "**60% fewer manual interventions per week**"

**There is no paper, no arXiv preprint, no DOI, no benchmark, no measurement protocol, and no baseline definition** in that repository. It is an individual's project README.

**Verdict: NOT VERIFIED as a research result. Grade C.** The closest *peer-reviewed-ish* self-healing number I found is the CrewAI/SRE paper's "**reducing the average end-to-end resolution time from hours to under 28 min**" (96% RCA accuracy, 73% fix success) — but that is in a "simulated production environment" at a low-tier Atlantis Press venue, and it does **not** express its result as an 85% MTTR reduction. Anyone citing "85% MTTR reduction" from LLM self-healing should be told it traces to a README.

### 3.6 TwinMem-Agent — the claim is ✅ literally accurate *but* the benchmark is not what it sounds like

DOI **10.1145/3803437.3807664**; DBLP **`conf/sigsoft/WuLMX26`**; Semantic Scholar venue: **"SIGSOFT FSE Companion"**, year 2026. Authors: Benzhao Wu, Zhiwen Luo, Fangwen Mu, L. Xiang.

> Abstract: "We study this sequential regime on a **stratified 8 × 25 subset of SWE-Bench Pro** (eight projects, twenty-five instances each)… Using **DeepSeek-V3.2** as the shared backbone and identical Dockerized instances, we compare TwinMem-Agent to **mini-swe-agent** on Pass@1 and average inference cost… **TwinMem-Agent achieves 89.1% Pass@1 versus 60.0% for the baseline at roughly 18× lower cost ($0.0044 vs. $0.0798)**. Removing the memory module reduces Pass@1 by **8 pp** and RSR by **12 pp**."

**Four caveats, all important:**
1. **"SWE-Bench Pro" here means a 200-instance stratified subset** (8 projects × 25), not the official 1,865-problem SWE-Bench Pro. Do not compare 89.1% to official SWE-Bench Pro leaderboard numbers.
2. It is in the **FSE *Companion*** volume, not the FSE main research track.
3. The baseline is `mini-swe-agent`, not a frontier agent — a 29-point gap to a deliberately minimal scaffold is a much weaker result than a 29-point gap to the SOTA.
4. **$0.0044 per instance** for repository-level repair with an agentic loop (28.9 calls is typical at this frontier) is far below every official SWE-bench cost I extracted (**$0.0281–$1.53**). Either the cost accounting excludes something material, or the tasks are atypically small. **Treat the 18× cost claim as suspect pending inspection of the accounting.**

### 3.7 ADI — claim ✅ accurate

PACMSE 2026, DOI 10.1145/3797126; DBLP `journals/pacmse/XiangXCTZ26`; arXiv **2604.24212**. Authors: Jia-Hong Xiang, Xiaoyang Xu, Xiao Chu, Hong-Liang Tian, Yu-Qun Zhang.

> "By simply equipping a basic agent with ADI, it successfully **resolves 63.8% of the tasks on the SWE-bench Verified set**, even slightly outperforming … Claude-Tools agent, at an **average cost of $1.28 per task with Claude-Sonnet-3.7**. Furthermore, we demonstrate ADI's generality by integrating it as a **plug-and-play component** into the existing SOTA agents, delivering consistent gains ranging from **6.2% to 18.5%** on the resolved tasks."

Note: $1.28/task is *above* the official leaderboard's most expensive cost-efficient frontier run ($0.7539 for 76.8%) — ADI buys a bigger gain at 63.8% resolve than its cost-efficiency suggests; its real value is the plug-and-play +6.2–18.5 pp on top of existing agents. Also note ADI is **dynamic-analysis infrastructure**, not a multi-agent repair framework per se, and it reports a *single-run* resolve rate with Claude-Sonnet-3.7, a 2025 model.

### 3.8 PhoenixRepair, MultiFixer, SWE-Master — new finds

**PhoenixRepair** (`arXiv:2607.18859`, 2026-07-21, cs.AI, 14pp, Tianyue Jiang + 9 authors):
> "Experiments on SWE-bench-Verified demonstrate that PhoenixRepair achieves the largest **relative improvement of 7.8% over SWE-agent under DeepSeek-V3.1**, and attains the highest **resolved rate of 76.0% Pass@1 under MiniMax-M2.5**. Meanwhile, it achieves higher fault localization accuracy than existing approaches."

Notable: 76.0% under MiniMax-M2.5 is **consistent** with the official leaderboard's MiniMax M2.5 result (75.8% at $0.0733/instance) — an independent cross-check that raises confidence in both. Grade B (arXiv, no venue stated).

**MultiFixer** (`arXiv:2607.26591`):
> "We evaluate MultiFixer on **835 bugs from Defects4J** and three vulnerability benchmarks. On Defects4J, MultiFixer fixes **326 bugs**, including **62 multi-method and 27 multi-file** bugs… Moreover, MultiFixer also fixes **46 multi-hunk bugs among 95 unique fixes**. When combined with **Claude-3.5-Sonnet**, MultiFixer repairs **420 bugs**, establishing a new state of the art on Defects4J. On **VUL4J**, MultiFixer repairs **24** real-world vulnerabilities, including 5 multi-hunk cases. On the multi-hunk subsets of **SEC-bench** and **PatchEval**, MultiFixer fixes **11** and **19** vulnerabilities, respectively."

**This is the strongest verified real-bug Java APR number I found: 420/835 = 50.3% on Defects4J v2.0.** Caveat: whether this uses ground-truth/perfect fault localization or end-to-end localization is not stated in the abstract — this is the single most important methodological question for comparing Defects4J numbers, and it is *routinely* glossed. Grade B.

**SWE-Master** (`arXiv:2602.03411v2`): "our approach achieves a resolve rate of **61.4% with Qwen2.5-Coder-32B** … By further incorporating test-time scaling (TTS) with LLM-based environment feedback, SWE-Master reaches **70.8% at TTS@8**." Grade B (technical report). Open-weight, reproducible.

### 3.9 Defects4J numbers are not mutually comparable — a warning

| System | Defects4J version | Bugs fixed | Implied denominator |
|---|---|---|---|
| MultiFixer | v2.0 (835 bugs) | 420 | 835 |
| MultiFixer (base model) | v2.0 | 326 | 835 |
| FedDualFix | v2.0 (subset) | 58 | ~109–116 (paper does not state) |
| LaMAR | unspecified | 24.5% success | unspecified |

Any comparison across these is invalid without matching (a) benchmark version, (b) fault-localization setting (perfect vs. end-to-end), (c) whether single-hunk bugs only were used, and (d) attempt budget. I could not confirm the FL setting for MultiFixer or LaMAR. **When you cite "SOTA on Defects4J," always state these four.**

### 3.10 Cost / energy per repair — what exists (2026)

This is the best-populated cost data in the whole survey, and it comes from the **official** leaderboard rather than a paper.

- **Official SWE-bench leaderboard** publishes `cost`, `instance_cost`, and `instance_calls` per submission. Full Pareto in §2.2. Range: **$0.0281 → $1.5311 per instance**.
- **FedDualFix**: **3.3k tokens/bug**, **$0.007–0.009/bug** (calibration) / **$0.028/bug** (GPT-4o), **3.8 LLM calls/bug**, avg API latency 0.92 s/call — an explicit APR $/repair figure.
- **ADI**: **$1.28/task** on SWE-bench Verified with Claude-Sonnet-3.7.
- **TwinMem-Agent**: **$0.0044** vs $0.0798 per instance (see §3.6 caveats).
- **TraceCoder**: claims cost-efficiency superiority over iterative baselines, but I did not extract a dollar or token table.
- **Energy / carbon per repair: NOT FOUND.** I searched "energy consumption LLM code repair", "carbon footprint automated program repair LLM", "energy-aware program repair 2026". No paper reporting joules/Wh/gCO₂e per repair was retrievable. Related replication package exists for *"Rethinking Automated Program Repair: The Impact of Bug Complexity, Fault Localization, and LLMs Cost-efficiency"* ([Zenodo 20257267](https://zenodo.org/records/20257267)) but Zenodo returned HTTP 403 to my requests, so I could not extract its numbers. **Marked NOT VERIFIED.**

---

## 4. Candidate SOTA numbers an agentic Python test-generation + repair system must beat

### 4.1 The hard targets

| Rank | Target | Number | Protocol to match exactly |
|---|---|---|---|
| **1** | SWE-bench Verified resolve @ ≤$0.10/instance | **75.8%** | `mini-SWE-agent` scaffold, MiniMax M2.5, 500 instances, **$0.0733/instance, 60.5 calls** (official leaderboard, 2026-02-17). *This is the efficiency frontier — beat this and you have a real cost story.* |
| **2** | SWE-bench Verified resolve, best cost-published | **76.8%** | `mini-SWE-agent`, Claude 4.5 Opus, 500 instances, **$0.7539/instance, 32.9 calls** (official, 2026-02-17) |
| **3** | SWE-bench Verified resolve, best official | **79.2%** | Sonar Foundation *or* live-SWE-agent + Claude 4.5 Opus, 500 instances, 2025-12-15 (official leaderboard; **no cost published**) |
| **4** | SWE-bench Verified, recent independent claim | **76.0%** | PhoenixRepair, MiniMax-M2.5, arXiv 2607.18859 (2026-07) — corroborates #1 |
| **5** | SWE-bench Verified, open-weights | **70.8%** | SWE-Master + Qwen2.5-Coder-32B at **TTS@8** (61.4% single-sample), arXiv 2602.03411 |
| **6** | SWE-bench Multilingual | **72.7%** | Gemini 3 Flash + mini-SWE-agent, **300 instances, $0.3518/instance, 52.5 calls** (official, 2026-02-13) |
| **7** | SWE-bench Lite | **60.33%** | ExpeRepair-v1 + Claude 4 Sonnet, 300 instances, 2025-06-25 (official) |
| **8** | Defects4J v2.0 (835 bugs), real-bug Java APR | **420 fixes (50.3%)** | MultiFixer + Claude-3.5-Sonnet, arXiv 2607.26591 — **and you must state your fault-localization setting to claim comparability** |
| **9** | Defects4J, plausible-but-incorrect ceiling | **31.0%** of plausible patches wrong | FedDualFix: 84 plausible − 58 correct = 26 wrong. *Any system reporting only "plausible" patches is over-claiming by ~1/3.* |
| **10** | Dynamic-analysis plug-in gain | **+6.2 to +18.5 pp** | ADI plugged into existing SOTA agents, SWE-bench Verified, Claude-Sonnet-3.7, $1.28/task (PACMSE 2026) |
| **11** | Noise-reduction upper bound (industrial) | **+13 pp / +15 pp / +39 pp** | Bug abstention / patch validation / combined, 174 human-reported Google bugs, ICSE-SEIP 2026 |
| **12** | Robustness floor | **>50% drop** | HEJ-Robust: 1,450 transformed instances, 8 semantics-preserving transforms, 5 fine-tuned LLMs (AIware 2026) |

### 4.2 Exact protocol you must report to be comparable

To make a defensible SOTA claim in 2026, report **all** of the following. Omitting any one of these makes the result non-comparable to the numbers above.

1. **Benchmark + version + instance count**, with the resolved instance IDs or a link to them. SWE-bench **Verified = 500**; **Lite = 300**; **Multilingual = 300**; **SWE-bench Pro = 1,865** (public = 11 repos); **Defects4J v2.0 = 835** (17 projects). Never write "SWE-bench" unqualified.
2. **Split discipline.** Official leaderboards evaluate on the public test split. If you use a *subset* (as TwinMem-Agent does: 8×25=200 of SWE-Bench Pro), say so in the headline, not a footnote.
3. **Scaffold and base model with exact version + date.** "mini-SWE-agent 2.0.0a0 + Gemini 3 Flash, 2026-02-13" — not "GPT-4-class model."
4. **Cost accounting**: **$/instance** *and* **tokens/instance** *and* **LLM calls/instance**, with the pricing table and date used. The official leaderboard publishes all three; FedDualFix publishes tokens/bug (3.3k) and $/bug; ADI publishes $/task. Report all model calls including retries.
5. **Budget and stopping rule** (max attempts / max tokens / max wall-clock) — e.g. TraceCoder's "maximum of 5 repair attempts," FedDualFix's "five-attempt budget" and ≤5 candidates/bug.
6. **Fault-localization setting** for any Defects4J-style benchmark: **perfect/ground-truth FL** vs **end-to-end**. State it explicitly. This is the single biggest source of inflated APR numbers.
7. **Patch-correctness criterion**, distinguishing **plausible** (passes the given tests) from **correct** (matches developer intent / passes held-out tests). Report both. FedDualFix's 84 plausible vs 58 correct is the model to imitate. Add a **held-out or mutation-based** correctness check (HEJ-Robust, DCAware-style fault-revealing evaluation).
8. **Test-surface integrity**: state whether your agent could modify the acceptance tests. ImpossibleBench (ICLR 2026) shows pass-rate = cheating-rate when tests can be rewritten; "Whose Oracle Is It?" shows **93.0%** of real test-changing repairs touch pre-existing test artifacts, so full test-locking is not a realistic deployment answer — report an admissible-repair-witness or two-zone policy instead.
9. **Multiple seeds / runs** with variance or CIs. LLM repair is stochastic; single-run resolve rates are not comparable. Report min/median/max or a CI.
10. **Robustness check**: re-run on semantics-preserving code transformations (HEJ-Robust style, 8 transforms) and report the drop.

### 4.3 What NOT to target

- **Do not make SWE-bench Verified your headline.** It is saturated: the official top three are separated by ~2 pp, third-party aggregators list 94–104 models, and benchlm.ai reports that **"0 of 94 rows come from the benchmark owner or an independent run, 88 are provider self-reports, 6 are secondary reports."** Use it as a *sanity check*, not a differentiator.
- **Do not target HumanEval/ClassEval-style function-level repair as a headline** in 2026 — TraceCoder already reports 90.72% average with Gemini-2.5-Flash, and these overlap with training data.
- **Do not claim latent-space communication as a cost win** without measuring it (see §2.4).

---

## 5. Sources

**Multi-agent repair frameworks**
- LANTERN — ICSE 2026: https://conf.researchr.org/details/icse-2026/icse-2026-research-track/185/Unlocking-LLM-Repair-Capabilities-Through-Cross-Language-Translation-and-Multi-Agent- · arXiv v5: https://arxiv.org/abs/2503.22512v5 · full text: https://ar5iv.labs.arxiv.org/html/2503.22512 · DOI 10.1145/3744916.3773227
- FedDualFix — DOI 10.1016/j.asoc.2026.115898 · https://www.sciencedirect.com/science/article/abs/pii/S1568494626013463 · author PDF: http://ntu-juking.github.io/files/ASOC-2026-01-Self.pdf · code: https://github.com/Liuqy1213/FedDualFix
- TraceCoder — DOI 10.1145/3744916.3773187 · https://arxiv.org/abs/2602.06875 · https://arxiv.org/html/2602.06875v1 · https://dl.acm.org/doi/full/10.1145/3744916.3773187
- LaMAR — DOI 10.1145/3832783.3837423 · https://dl.acm.org/doi/10.1145/3832783.3837423 · Semantic Scholar record: https://api.semanticscholar.org/graph/v1/paper/DOI:10.1145/3832783.3837423
- PhoenixRepair — https://arxiv.org/abs/2607.18859 · https://huggingface.co/papers/2607.18859
- MultiFixer — https://arxiv.org/abs/2607.26591
- SWE-Master — https://arxiv.org/abs/2602.03411
- DEIMerge — DOI 10.1007/978-981-95-7081-2_16 · https://dl.acm.org/doi/10.1007/978-981-95-7081-2_16
- AgentRepair — https://ieeexplore.ieee.org/document/11320358 · https://www.semanticscholar.org/paper/1a3b26e41e1f1969aabf52c0a92b3d6dbb8145fb

**SWE-bench family & official leaderboard**
- Official leaderboards + embedded JSON (500 Verified instances, per-instance cost/calls): https://www.swebench.com/
- SWE-bench Pro: https://arxiv.org/abs/2509.16941 · Scale leaderboard: https://labs.scale.com/leaderboard/swe_bench_pro_public_v2 (Cloudflare-blocked) · V2 blog: https://labs.scale.com/blog/swe-bench-pro-v2 (blocked) · third-party analysis of public/private gap: https://bayesiansapien.github.io/cere-bro/agentic-systems/2026-09-23-swe-bench-pro-v2-contamination-gap/
- Third-party aggregators (Grade C): https://llmlearner.com/rankings/swe-bench-verified · https://benchlm.ai/benchmarks/swe-bench-verified
- Epoch AI third-party results referenced by llmlearner

**Memory / dynamic analysis**
- TwinMem-Agent — DOI 10.1145/3803437.3807664 · https://dl.acm.org/doi/abs/10.1145/3803437.3807664 · DBLP `conf/sigsoft/WuLMX26`
- ADI — DOI 10.1145/3797126 · https://dlnext.acm.org/doi/epdf/10.1145/3797126 · https://arxiv.org/abs/2604.24212 · DBLP `journals/pacmse/XiangXCTZ26`

**Latent communication**
- *Beyond tokens* survey: https://arxiv.org/abs/2606.05711
- *Safety of Latent Communication in Multi-Agent Systems*: https://arxiv.org/abs/2609.39788

**Self-healing**
- VIGIL: https://arxiv.org/abs/2512.07094 · https://ar5iv.labs.arxiv.org/html/2512.07094 · code https://github.com/cruz209/V.I.G.I.L
- FTDI: https://www.sciencedirect.com/science/article/abs/pii/S0957417426030708 (403) · secondary summary used: https://www.ebiotrade.com/newsf/2026-8/20260827083147541.htm
- CrewAI SRE: https://download.atlantis-press.com/proceedings/icsssm-25/126020167 · DOI 10.2991/978-94-6463-950-6_35
- ESBMC-AI: https://arxiv.org/abs/2305.14752 · DOI 10.1109/AST66626.2025.00020 · https://dl.acm.org/doi/abs/10.1109/AST66626.2025.00020
- agent-sandbox: https://github.com/kubernetes-sigs/agent-sandbox
- "85% MTTR": https://github.com/suhail39ahmed/self-healing-azure-pipelines · related but distinct: https://jisem-journal.com/index.php/journal/article/view/9888 · https://conf.researchr.org/details/seri-2026/seri-2026-seri-2026/2/Trust-Aware-and-Explainable-Self-Healing-Framework-for-Reliable-Software-Systems

**Methodology / reward hacking / overfitting**
- Self-Repair Trap (DCAware), ASE 2026: https://arxiv.org/abs/2608.05917
- ImpossibleBench, ICLR 2026: https://github.com/safety-research/impossiblebench · paper notes: https://github.com/zhaoyang97/Paper-Notes/blob/main/docs/ICLR2026/llm_safety/impossiblebench_measuring_llms_propensity_of_exploiting_test_cases.md
- Abstain and Validate, ICSE-SEIP 2026: https://arxiv.org/abs/2510.03217 · https://research.google/pubs/abstain-and-validate-a-dual-llm-policy-for-reducing-noise-in-agentic-program-repair/ · https://dl.acm.org/doi/pdf/10.1145/3786583.3786858
- Whose Oracle Is It?: https://binds.ch/papers/whoseoracle2026.pdf
- Reward hacking / escalation channels: https://export.arxiv.org/pdf/2608.29460
- Dynamic cogeneration of bug-reproduction tests: https://ar5iv.labs.arxiv.org/html/2601.19066
- Kronumos (cost-bounded APR) — Zenodo 403: https://zenodo.org/records/22929676 · Kronumos 2 Kairos: https://zenodo.org/records/23013104
- Cost-efficiency replication package (Zenodo 403): https://zenodo.org/records/20257267

**Benchmarks**
- RunBugRun — EMSE 31:98 (2026-03-24): https://link.springer.com/article/10.1007/s10664-025-10790-3 · arXiv: https://arxiv.org/abs/2304.01102 · full text: https://ar5iv.labs.arxiv.org/html/2304.01102
- xCodeEval — https://arxiv.org/abs/2303.03004
- CI-Bench — DOI 10.1145/3774748.3787606 · https://web.cs.ucdavis.edu/~rubio/includes/icse26-demo.pdf · https://github.com/bugswarm/ci-bench
- BugSwarm — https://arxiv.org/abs/1903.06725 · https://github.com/tomassib/BugSwarm
- HEJ-Robust — DOI 10.1145/3805760.3814929 · https://arxiv.org/abs/2605.02215 · https://dl.acm.org/doi/abs/10.1145/3805760.3814929
- LogicEval / LogicDS — https://aclanthology.org/2026.acl-long.2136/ · DOI 10.18653/v1/2026.acl-long.2136
- Defects4J — https://github.com/rjust/defects4j

**Other 2026 repair work discovered but not fully mined**
- Utilising Dynamic Context and Static Analysis for Agent-Based APR — https://ieeexplore.ieee.org/document/11513852
- Memory-Efficient LLMs for Program Repair with Semantic-Guided Patch Generation (ICSE 2026) — DOI 10.1145/3744916.3773240
- Verification-First Self-Repair for LLM Agents (Zenodo 403) — https://www.zenodo.org/records/21452222
- Fixing Security Vulnerabilities with Agentic AI in OSS-Fuzz — DOI 10.1145/3786583.3786880

---

## 6. Unverified / failed lookups

| # | Item | Status | What I tried |
|---|---|---|---|
| 1 | **AgentRepair metrics** (AST-anchored, cold-start) | ❌ **NOT VERIFIED — no metric retrieved** | IEEE Xplore doc 11320358 (HTTP 202 challenge), Semantic Scholar paper page (0 bytes), S2 search API (HTTP 429). Existence confirmed only via search-result titles ("Lee, Yang"). No benchmark, model, or number obtained. |
| 2 | **DEIMerge metrics** | ❌ **NOT VERIFIED** | DOI 10.1007/978-981-95-7081-2_16. S2 API returns `"abstract": null` — *"The following paper fields have been elided by the publisher: {'abstract'}"*. Springer/ACM DL 403. Venue/authors confirmed (PRICAI 2025; Liang, Zhao, Mo) but zero numbers. |
| 3 | **"85% MTTR reduction"** as a research claim | ❌ **NOT VERIFIED — traces to a personal GitHub README** | Searched 3 phrasings. Only source: `suhail39ahmed/self-healing-azure-pipelines` README. No paper/DOI/benchmark/methodology. See §3.5. |
| 4 | **ESBMC-AI repair success rate** | ❌ **NOT VERIFIED** | Abstract says only "**high accuracy**" — no number. Full text would need the PDF; abstract retrieved from arXiv 2305.14752. Described by its authors as a "**proof of concept**", C-only, 50,000 FormAI programs. |
| 5 | **Defects4J v3** | ❌ **NOT VERIFIED — no evidence it exists** | GitHub releases/tags, DBLP, and general web search. Found only v1.x and v2.0.0 (835 bugs). Treat "Defects4J v3" as non-existent until shown otherwise. |
| 6 | **ARC-APR benchmark** | ❌ **NOT VERIFIED — likely non-existent** | Searched `"ARC-APR" OR "ARC APR" automated program repair benchmark` and variants. No matching benchmark found. |
| 7 | **Latent communication / KV-cache *measured* token-cost or $-cost ablation for APR** | ❌ **NOT VERIFIED** | LaMAR abstract reports only an asymptotic O(N²)→O(N) proof and a qualitative ablation. No measured token/dollar reduction retrieved. |
| 8 | **ImpossibleBench per-model cheating rates** | ❌ **NOT VERIFIED (numbers)** | Only a third-party paper-note retrieved. The ICLR 2026 paper itself was not fetched. Framework/task design verified; specific cheating-rate values are not. |
| 9 | **Energy / carbon per repair** | ❌ **NOT FOUND** | Searched "energy consumption LLM code repair", "carbon footprint automated program repair LLM", "energy-aware program repair 2026". No paper reporting joules/Wh/gCO₂e per repair retrieved. |
| 10 | **"Rethinking APR: Bug Complexity, Fault Localization, LLMs Cost-efficiency" numbers** | ❌ **NOT VERIFIED** | Zenodo record 20257267 returned **HTTP 403** (network-restriction / "unusual traffic") on both the record page and the API. |
| 11 | **Kronumos / Kronumos 2 Kairos (cost-bounded APR) numbers** | ❌ **NOT VERIFIED** | Zenodo records 22929676 and 23013104 both returned **HTTP 403**. Titles confirm the *existence* of cost-bounded APR work on SWE-bench Verified. |
| 12 | **SWE-bench Pro V2 leaderboard & public/private gap** | ❌ **NOT VERIFIED** | `labs.scale.com` blog and leaderboard both Cloudflare-403. Only a third-party blog claims a "17.8-point public-versus-private gap" (Grade C, not used as a data point). |
| 13 | **SWE-smith / SWE-Gym instance counts** | ❌ **NOT VERIFIED** | Not retrieved within budget. |
| 14 | **FTDI primary-source numbers** | ⚠️ **Partially verified — secondary source only** | ScienceDirect 403. The 95.65% figure and the HumanEval/HumanEval+/MBPP/CIAR/200-task details come from a **Chinese-language summary** (ebiotrade.com, 2026-08-27) of the ESWA paper — not from the paper itself. Treat as indicative, not confirmed. |
| 15 | **TraceCoder cost/token table** | ⚠️ **Partial** | Paper claims cost-efficiency superiority over iterative baselines, but I did not extract a $/token table from the retrieved HTML. |
| 16 | **Abstain-and-Validate / Whose-Oracle venue for the latter** | ⚠️ **Partial** | "Whose Oracle Is It?" (Mohammadi & Bindschaedler, MPI-SWS) venue not determined — PDF retrieved from an author site, no venue line confirmed. |
| 17 | **VIGIL's scientific standing** | ⚠️ **Weak** | Single-author arXiv preprint (Christopher Cruz, Dec 2025), **n = 12 events**, one synthetic testbed agent ("Robin-A"), no benchmark, no baseline, no statistical test. All 4 numbers (12/12→0/12 toasts, 97s→8s, 8→0 frustration events) come from one non-repeated case study. Do not cite VIGIL as evidence that reflective runtimes improve reliability. |

### 6.1 Conflicting numbers across sources — explicitly noted

1. **SWE-bench Verified top score: 79.2% (official) vs 96% (third-party aggregators).** The **official** swebench.com leaderboard's best entry is **79.2%** (Claude 4.5 Opus + Sonar Foundation / live-SWE-agent, 2025-12-15) and its newest submission is dated **2026-02-26**. Third-party aggregators list "Claude Opus 5 — 96.0", "Claude Fable 5 — 95.0", "Claude Mythos Preview — 93.9", and a best-open-weights of 80.6 (DeepSeek-V4-Pro), with 94–104 models ranked. **These are not the same measurement population.** benchlm.ai itself warns that **"0 of 94 rows come from the benchmark owner or an independent run, 88 are provider self-reports, 6 are secondary reports,"** and that saturation is active (top three within 1.0 pt). Conclusion: the official leaderboard is stale (~8 months) and the 96% figures are unverified provider self-reports. **Neither should be cited as a rigorous SOTA.**
2. **RunBugRun size: 450,000 / 8 languages (arXiv 2023) vs 716,900 / 9 languages (EMSE 2026).** Both are real; the journal version expanded the dataset. The brief's claim matches the **journal** version. Cite the version.
3. **xCodeEval "5,068 bugs": subset, not the benchmark.** xCodeEval overall = 25M samples / 7,514 problems / 11 languages / 7 tasks; **5,068 is the Compact Set** used for APR. LANTERN's usage is correct; restating it as "xCodeEval has 5,068 bugs" is wrong.
4. **TwinMem-Agent "89.1% on SWE-Bench Pro": 200-instance stratified subset**, not the 1,865-problem benchmark. Also in an **FSE Companion** volume, not the FSE main track. Also **$0.0044/instance** is ~6–17× below every official leaderboard cost for comparable agentic runs.
5. **Defects4J denominators disagree (835 vs ~111 vs unspecified).** MultiFixer used all 835; FedDualFix used an unstated subset; LaMAR unspecified. Cross-paper comparison invalid without matching FL setting and version.
6. **Self-healing "MTTR": 85% (README) vs "hours → under 28 min" (ICSSM 2025) vs no MTTR metric at all (VIGIL, FTDI).** These three are different quantities measured on different (or no) benchmarks and are not reconciliable.
7. **TraceCoder's 90.72% average Pass@1 (Gemini-2.5-Flash) vs LaMAR's 24.5% (Qwen3-8B) vs MultiFixer's 50.3% (Claude-3.5-Sonnet) on "repair."** These are three different tasks (LLM-generated function-level code, Defects4J with an 8B model, Defects4J end-to-end Java). Do not put them in one column.
8. **FedDualFix P@1 denominator implied by arithmetic is inconsistent** (109–116 across baselines for a stated fixed instance set) — likely per-client averaging. Exact N unstated.

### 6.2 Items in the brief whose claims I could confirm as accurate

LANTERN's +22.09% Rust/xCodeEval · FedDualFix's 52.1% Top-1 / 58 repairs · LaMAR's 24.5% with Qwen3-8B · TwinMem-Agent's 89.1% vs 60.0% and 18× cost *(with heavy benchmark-scope caveats)* · ADI's 63.8% on SWE-bench Verified · RunBugRun's 716,900 / 9 languages *(journal version)* · xCodeEval's 5,068 / 11 languages *(Compact Set)* · LogicEval's 122 logical vulnerabilities.

### 6.3 Items in the brief whose claims I could not confirm

AgentRepair *(no metrics at all)* · DEIMerge *(abstract elided)* · PhoenixRepair *(exists; abstract gives 76.0% under MiniMax-M2.5 — no prior claim to check)* · Defects4J v3 *(no evidence of existence)* · ARC-APR *(likely non-existent)* · HEJ-Robust *(exists: 1,450 instances)* · ESBMC-AI *(no success-rate number published)* · agent-sandbox-runtime *(infrastructure; publishes no self-healing metrics)* · the 85% MTTR figure *(personal README)* · measured latent-communication cost savings *(not published)* · energy per repair *(nothing found)*.
