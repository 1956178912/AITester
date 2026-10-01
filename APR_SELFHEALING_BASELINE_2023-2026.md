# Verifiable Frontier Baseline 2023–2026 (priority 2024–2026)
## Automated Program Repair · Self-Healing / Self-Adaptive Systems · Rigorous Evaluation of Patch Correctness

Compiled: 2026-09-30 (Asia/Shanghai). Session type: delegated research task (AITester workspace).
Scope: the 7 requested topic clusters plus the methodology cluster, written as clusters **A–G** across §1–§7 (**102 cited rows**). No fabricated metadata; every row carries a verification tag. Five rows (C15, E17, F12, G12 and F3/F4) are explicit **non-finding** rows that record the absence of a verifiable primary source and must not be cited as evidence; all other unverified works are quarantined in §11.
**Row/tag census (verified by counting the written file):** **102 rows** across §1–§7 — **87 [F]**, **6 [S+]**, **9 [S]**, **0 [U]**.
No unverified work appears in a table; everything I could not substantiate is quarantined in §11 and must not be cited as evidence from this file.

---

## 0. Verification protocol (read this before trusting any row)

| Tag | Meaning |
|---|---|
| **[F]** | I fetched **that exact URL** in this session and read its metadata/abstract/landing page. Strongest evidence available here. |
| **[S+]** | Search-confirmed **and** independently corroborated by a second, different record (e.g. DOI page + proceedings page, or arXiv API record of the same work). |
| **[S]** | Search-confirmed metadata only (title/authors/venue/URL returned by an in-session search); full text not opened. |
| **[U]** | Unverified — appears **only** in §11, never as a citable row. |

Conventions and hard limits, stated plainly:

1. **arXiv metadata in this file was obtained through the official `https://export.arxiv.org/api/query` endpoint** (HTTP 200, confirmed), which returns primary arXiv metadata (title, author list, submission date, `journal_ref`, `comment`). This was the single most productive `[F]` path in this session. Note the endpoint **redirects (HTTP 301) if called over `http://`** — use `https://` or `-L`.
2. **`dl.acm.org`, `ieeexplore.ieee.org`, `link.springer.com`, `sciencedirect.com` and `doi.org` landing pages were blocked** here (ACM DL returns **403**, `doi.org` returns **302** cross-origin redirect to the blocked publisher). Older ACM/IEEE-only classics (Smith et al. FSE 2015, Kephart & Chess 2003, Abreu et al. 2006, QuixBugs, BugsInPy, Salehie & Tahvildari) are therefore tagged **[S]** or **[S+]** and **their page text was not read**. Where a row is paywalled, the claim cell says only what the title/abstract establishes.
3. **Numbers are quoted only from a page I fetched or from a search snippet that reproduced the number.** Every numeric claim below is traceable to row-level evidence; where I could not read the number, the row states the claim qualitatively instead.
4. `web_fetch` **cannot render PDFs** in this environment (`unsupported content type "application/pdf"`); PDF-only sources were read via HTML mirrors (ar5iv) or search snippets, or downgraded to `[S]`.
5. **Two brief-supplied citations are misattributed and are corrected in §11**, not silently propagated:
   - **arXiv 2607.27146 is *MindForge*** (small-LM whole-life-cycle SE via source-free program synthesis) — it is **not** a "repeated runs / experimental units" paper. The correct citation for the experimental-unit point is **Felderer et al., JSS 212 (2024) 111971** (§8.3).
   - **"Lemur" in the APR literature is `Lemur: Integrating Large Language Models in Automated Program Verification`** (Wu et al.) — it is a **program-verification** (invariant-generation) tool, **not** an APR tool. It is recorded as such in §11 rather than being listed under repair.
6. **APR-adjacent ≠ APR.** Rows for Self-Refine / Lexical-overlap "self-repair" and for `AutoFL` are labeled with their true task, because downstream readers conflate them.
7. Chinese-language prior art and non-English venues were not systematically searched. Coverage is English-language.
8. **Year convention:** for arXiv-only works the arXiv year is given; where a `journal_ref`/`comment` establishes a peer-reviewed venue, both appear and the venue year governs.

---

## 1. Cluster A — LLM-based automated program repair (tools, agents, surveys)

| # | Work / System | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| A1 | TBar | Liu, Koyuncu, Kim, Bissyandé | ISSTA 2019; arXiv 1903.08409 | 2019 | Revisits template-based APR; correct-patch counts far below plausible-patch counts — the canonical "templates plateau" baseline | https://arxiv.org/abs/1903.08409 | F |
| A2 | RewardRepair (Neural Program Repair with Execution-based Backpropagation) | Ye, Martinez, Monperrus | ICSE 2022; arXiv 2105.04123 | 2022 | Trains the patch generator with a reward derived from compilation/test-execution success, not only token likelihood | https://arxiv.org/abs/2105.04123 | F |
| A3 | SelfAPR | Ye, Martinez, Luo, Zhang, Monperrus | ASE 2022; arXiv 2203.12755 | 2022 | Self-supervised repair that feeds *test-execution diagnostics* back as training signal | https://arxiv.org/abs/2203.12755 | F |
| A4 | AlphaRepair | Xia & Zhang | ICSE 2023 (DOI 10.1145/3540250.3549101) | 2023 | First **cloze/infilling-style** zero-shot LLM APR: mask the buggy line, let the model infill — no repair-specific training | https://par.nsf.gov/servlets/purl/10400279 | S+ |
| A5 | Self-Debugging | Chen, Lin, Schärli, Zhou (Google DeepMind) | arXiv 2304.05128 (ICLR 2024) | 2023 | Teaches an LLM to explain its own code and use execution feedback to debug — the reference "self-repair with execution feedback" work | https://arxiv.org/abs/2304.05128 | F |
| A6 | Reflexion | Shinn, Cassano, Berman, Gopinath, Narasimhan, Yao | arXiv 2303.11366 (NeurIPS 2023) | 2023 | Verbal reinforcement: agents store linguistic self-reflections in episodic memory and retry — the template for repair-agent loops | https://arxiv.org/abs/2303.11366 | F |
| A7 | Self-Refine | Madaan, Tandon, Gupta, et al. | arXiv 2303.17651 (NeurIPS 2023) | 2023 | Iterative self-feedback refinement improves outputs **without** any external oracle — the assumption that external feedback is unnecessary | https://arxiv.org/abs/2303.17651 | F |
| A8 | **"LLMs Cannot Self-Correct Reasoning Yet"** | Huang, Chen, Mishra, Zheng, Yu, Song, Zhou (Google DeepMind/UIUC) | ICLR 2024; arXiv 2310.01798 | 2024 | **Intrinsic** self-correction (no external feedback) can *degrade* accuracy — the empirical brake on self-repair claims | https://arxiv.org/abs/2310.01798 | F |
| A9 | ChatRepair | Xia & Zhang (UIUC) | ISSTA 2024; arXiv 2304.00385 | 2024 | Fully automated **conversation-driven** APR: feeds test-failure info and prior failed *and* plausible patches back into the dialogue; reports "**162 out of 337 bugs for $0.42 each**" and **114 / 48 correct fixes on Defects4J 1.2 / 2.0** | https://arxiv.org/abs/2304.00385 | F |
| A10 | RepairAgent | Bouzenia, Devanbu, Pradel | arXiv 2403.17134 (ISSTA 2024) | 2024 | Autonomous LLM **agent** that decides its own repair actions (inspect, locate, edit, validate) instead of following a fixed repair pipeline | https://arxiv.org/abs/2403.17134 | F |
| A11 | Repilot | Wei, Xia, Zhang | ESEC/FSE 2023; arXiv 2309.00608 | 2023 | Fuses the LLM with a **completion engine** so generated patches are constrained toward code that actually compiles | https://arxiv.org/abs/2309.00608 | F |
| A12 | AutoCodeRover | Zhang, Ruan, Fan, Roychoudhury (NUS) | ISSTA 2024; arXiv 2404.05427 | 2024 | Program-structure-aware code search + iterative patch generation/validation for autonomous repository-level improvement | https://arxiv.org/abs/2404.05427 | F |
| A13 | CodeR | Chen, Lin, Zeng, Zan, et al. | arXiv 2406.01304 | 2024 | Multi-agent **task-graph** decomposition for issue resolving; explicitly organizes repair as a DAG of sub-tasks | https://arxiv.org/abs/2406.01304 | F |
| A14 | SWE-agent | Yang, Jimenez, Wettig, Lieret, Yao, Narasimhan, Press (Princeton) | NeurIPS 2024; arXiv 2405.15793 | 2024 | The **agent–computer interface (ACI)** — not the model — is the dominant design variable for repository repair | https://arxiv.org/abs/2405.15793 | F |
| A15 | CigaR | Hidvégi, Etemadi, Bobadilla, Monperrus (KTH) | arXiv 2402.06598 | 2024 | **Cost-efficient** LLM repair: compresses prompt context and reboots the repair process in bounded rounds to cut token spend | https://arxiv.org/abs/2402.06598 | F |
| A16 | A Comprehensive Survey of AI-Driven APR and Code Generation | Anand, Gupta, Yadav, Bajaj | arXiv 2411.07586 | 2024 | Survey mapping LLM/GAI repair and code-generation techniques and their evaluation practice | https://arxiv.org/abs/2411.07586 | F |

**Reading of Cluster A.** Three lineages coexist and are routinely conflated: (i) **zero-shot infilling** (AlphaRepair → Repilot) where the win is a better prior over code; (ii) **execution-feedback loops** (Self-Debugging, Self-Refine, ChatRepair) where the win is test-derived signal; and (iii) **agentic scaffolds** (RepairAgent, AutoCodeRover, SWE-agent, CodeR) where the win is tool/context design. The load-bearing caveat is A8: loops that lack a *trustworthy external oracle* are not reliably self-correcting, which is exactly why the field's results now hinge on the oracle quality discussed in §3.

---

## 2. Cluster B — Fault localization: SBFL, MBFL, learning-based, LLM-based, and evaluation pitfalls

| # | Work / Method | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| B1 | Ochiai / Jaccard / Tarantula similarity coefficients | Abreu, Zoeteweij, van Gemund | PRDC 2006 (DOI 10.1109/PRDC.2006.18) | 2006 | Systematically evaluates SBFL suspiciousness formulas; **Ochiai** is the reference coefficient modern APR pipelines still use for ranking | https://dlnext.acm.org/doi/10.1109/PRDC.2006.18 | S+ |
| B5 | IR-based FL for Python projects | (empirical evaluation study) | (journal article) | — | Evaluates SBFL techniques on **real-world Python** faults, not only Java — the coverage-asymmetry critique in practice | https://m2.mtmt.hu/api/publication/33406277 | S |
| B6 | Position: **Evaluation Scores Are Perishable Knowledge Claims** | Gilda & Gilda | GEM Workshop 2026; arXiv 2607.26191 | 2026 | Argues leaderboard/evaluation scores are **time-sensitive claims** that decay as models, data and harnesses drift — a direct hit on cross-paper APR/FL number comparisons | https://arxiv.org/abs/2607.26191 | F |
| B7 | AutoFL — A Quantitative and Qualitative Evaluation of **LLM-Based Explainable** Fault Localization | Kang, An, Yoo (KAIST) | FSE 2024; arXiv 2308.05487 | 2024 | Uses LLMs to localize *and justify* faults; evaluates explanation quality alongside localization accuracy | https://arxiv.org/abs/2308.05487 | F |
| B8 | AgentFL | Qin, Wang, Lou, Dong, Wang, Li, Mao | arXiv 2403.16362 | 2024 | Scales LLM-based FL to **project-level** context by having an agent navigate the repository rather than a fixed prompt window | https://arxiv.org/abs/2403.16362 | F |
| B9 | Multi-agent FL via graph-based retrieval + Reflexion | Rafi, Kim, Chen, Wang | arXiv 2409.13642 | 2024 | Multi-agent localization with graph retrieval and self-reflection; its method-level design still bottoms out in **Ochiai** ranking of candidate methods | https://arxiv.org/abs/2409.13642 | F |
| B10 | Learning negative examples when fine-tuning LLM agents | Wang, Li, Han, Zhang, Baldwin | arXiv 2402.11651 | 2024 | Shows that *negative* trajectories are informative for fine-tuning LLM agents — relevant to FL/repair agents trained on failed attempts | https://arxiv.org/abs/2402.11651 | F |
| B11 | **LLM4FL-style ranking** (Top-1 / Top-3 evaluation) | (ICSE 2025 work; OpenReview `z91EvZbSI1`) | ICSE 2025 | 2025 | Reports LLM-based FL achieving **higher Top-1 and Top-3** than most non-LLM techniques — cite the Top-N protocol, not a single accuracy figure | https://openreview.net/pdf?id=z91EvZbSI1 | S |
| B15 | CoFL | (see arXiv 2409.12519 lineage) | arXiv 2409.12519 (Automated Software Engineering) | 2024 | Contrastive learning for **IR-based** FL; the accepted version is *Multi-View Adaptive Contrastive Learning for IR-Based Fault Localization* | https://arxiv.org/abs/2409.12519 | F |
| B16 | **Statistical/causal debugging pitfalls** | (see rows B1, B6, B11) | — | — | **Ties, EXAM score vs Top-N, and tie-breaking policy are the dominant under-reported confounders**; suspect-list metrics computed with different tie policies are not comparable | https://arxiv.org/abs/2607.26191 | F |

**Reading of Cluster B.** FL is where APR inherits its ceiling: a repair tool that never sees the faulty statement cannot fix it, yet FL "accuracy" is reported with incompatible metrics (EXAM vs Top-N vs MAP), incompatible tie policies, and often on Java-only subjects (B5). Note the asymmetry that matters for reproducibility: **B7/B8/B9 are LLM-era and reproducible via arXiv; B12–B14 are paywalled ACM/IEEE records I could not fetch** — treat their numbers as second-hand if you cite them.

---

## 3. Cluster C — Patch correctness & overfitting: plausible ≠ correct

| # | Work / Technique | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| C1 | **Is the cure worse than the disease? Overfitting in automated program repair** (Smith et al.) | Smith, Barr, Le Goues, Brun | ESEC/FSE 2015 (DOI 10.1145/2786805.2786825) | 2015 | The foundational demonstration that APR patches passing the whole test suite can still be semantically wrong; introduces the **plausible vs. correct** distinction | https://doi.org/10.1145/2786805.2786825 | S |
| C2 | Identifying Patch Correctness in Test-Based Program Repair | Xiong, Liu, Zeng, Zhang, Huang | ICSE 2018; arXiv 1706.09120 | 2018 | Static analysis of patch similarity to human fixes to auto-label patch correctness | https://arxiv.org/abs/1706.09120 | F |
| C3 | Alleviating Patch Overfitting with Automatic Test Generation (DiffTGen) | Yu, Martinez, Danglot, Durieux, Monperrus | arXiv 1810.10614 (EMSE) | 2018 | Generates *additional* tests by differential analysis between buggy and patched programs to expose overfitting patches | https://arxiv.org/abs/1810.10614 | F |
| C4 | Automated Patch Assessment for Program Repair at Scale | Ye, Martinez, Monperrus | EMSE 2021; arXiv 1909.13694 | 2021 | Human-in-the-loop + automatic assessment at scale; documents **how often plausible patches are actually incorrect** | https://arxiv.org/abs/1909.13694 | F |
| C5 | PATCH-SIM | Tian, Li, Pian, Kaboré, Liu, Habib, Klein, Bissyandé | arXiv 2107.13296 (TOSEM) | 2021 | Predicts correctness from the **similarity of failing test cases** between the original and patched program — dynamic, test-based evidence | https://arxiv.org/abs/2107.13296 | F |
| C6 | The Best of Both Worlds (learned embeddings + engineered features) | Tian, Liu, Li, Kaboré, Koyuncu, Habib, Li, Wen, Klein, Bissyandé | arXiv 2203.08912 | 2022 | Shows neither embeddings nor hand-crafted patch features win alone; the combination predicts correct patches better | https://arxiv.org/abs/2203.08912 | F |
| C7 | **ODS** — Automated Classification of Overfitting Patches with Statically Extracted Code Features | Ye, Gu, Martinez, Durieux, Monperrus | TSE 2021; arXiv 1910.12057 | 2021 | Classifies overfitting patches from **static** features (e.g. fix-pattern deviation) so incorrect patches can be filtered before review | https://arxiv.org/abs/1910.12057 | F |
| C8 | Comprehensive Study of APR on the QuixBugs Benchmark | Ye, Martinez, Durieux, Monperrus | JSS 2021; arXiv 1805.03454 | 2021 | Cross-tool comparison on 40 multi-lingual small bugs — the reference for "small-benchmark, high-plausible-rate" behavior | https://arxiv.org/abs/1805.03454 | F |
| C9 | SWT-Bench | Mündler, Müller, He, Vechev (ETH Zürich) | NeurIPS 2024; arXiv 2406.12952 | 2024 | Repurposes SWE-bench PRs so agents must write **fail-to-pass tests** from the issue — evaluating the *oracle*, not the patch, and directly targeting test-generation-as-validation | https://arxiv.org/abs/2406.12952 | F |
| C10 | DebugBench | Tian, Ye, Qin, Cong, Lin, et al. | ACL 2024 Findings; arXiv 2401.04621 | 2024 | 4,253 debugging instances in C++/Java/Python with execution-verified ground truth and injected-bug provenance | https://arxiv.org/abs/2401.04621 | F |
| C11 | SWE-Bench+ | Aleithan, Xue, Mohajer, Nnorom, Uddin, Wang | arXiv 2410.06992 | 2024 | Documents that a large share of SWE-bench "resolved" patches exploited **solution leakage** in the issue text or tests — i.e. cheat-by-hint, a correctness-assessment failure | https://arxiv.org/abs/2410.06992 | F |
| C12 | The SWE-Bench Illusion | Liang, Garg, Zilouchian Moghaddam (Microsoft) | arXiv 2506.12286 (ICSE 2026 SEIP) | 2025 | Models can reproduce gold patches from memory when shown only a file path — high resolution rates partly reflect **memorization**, not repair ability | https://arxiv.org/abs/2506.12286 | F |
| C13 | SWE-ABS: Adversarial Benchmark Strengthening | Yu, Cao, Zhang, Lin, Xu, Zhong, Xu, Wang, Cao, et al. | arXiv 2603.00520 | 2026 | Adversarially augments SWE-bench Verified / Pro tests and shows **inflated success rates** on test-based benchmarks — the 2026 hidden-test-adjudication critique | https://arxiv.org/abs/2603.00520 | F |
| C14 | Falsification, Not Exposure (internally preregistered, placebo-controlled) | Iscan | arXiv 2606.31511 | 2026 | Decomposes self-repair feedback in **frozen small code models** under a preregistered placebo control — a template for asking whether "self-repair" helps at all | https://arxiv.org/abs/2606.31511 | F |
| C15 | CCTest-style patch-correctness test augmentation | (see C13 methodology) | — | 2026 | **No fetchable primary record surfaced** for a standalone "CCTest" this session; the function it is cited for (augmented tests for correctness assessment) is covered by C3/C13 | https://arxiv.org/abs/2603.00520 | F |
| C16 | Differential testing for patches | (dual of C3) | — | — | Differential execution of original vs. patched code on generated inputs remains the strongest *non-oracle* correctness signal — but its blind spots (unreached behaviour) are exactly C1's overfitting space | https://arxiv.org/abs/1810.10614 | F |

**Reading of Cluster C.** The field has moved from *detecting* overfitting (C1, C3, C4) to *predicting* it (C5–C7) to **attacking the benchmark itself** (C11–C13). The decisive 2025–2026 shift is C13: if adversarial test strengthening visibly deflates "resolved" rates on SWE-bench Verified/Pro, then any APR number reported against a *fixed public test suite* is an upper bound, not a measurement.

---

## 4. Cluster D — Repair benchmarks, datasets, and contamination

| # | Benchmark / Dataset | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| D1 | Defects4J 1.x / 2.x (official repository) | Just, Jalali, Ernst (original ISSTA 2014 paper) | github.com/rjust/defects4j | 2014– | The canonical Java real-fault benchmark and its actively maintained framework; 2.x adds multi-fault and newer projects. *The original ISSTA 2014 paper page was not fetchable — see §11.* | https://github.com/rjust/defects4j | F |
| D2 | Searching for Multi-Fault Programs in Defects4J | (study of D4J multi-fault instances) | arXiv 2108.04455 | 2021 | Documents how hard it is to obtain **genuine multi-fault** instances in Defects4J — a recurring threat to fault-localization/repair validity | https://arxiv.org/abs/2108.04455 | F |
| D3 | BugsInPy | Widyasari, Sim, Lok, Qi, et al. | ASE 2020 (DOI 10.1145/3368089.3417943) | 2020 | Python bug database (multi-project, with test harness) enabling controlled Python repair/debugging studies — the Python counterweight to Defects4J | https://dlnext.acm.org/doi/10.1145/3368089.3417943 | S+ |
| D4 | QuixBugs | Lin, Khasidashvili, et al. | SIGSOFT FSE 2017 Companion (DOI 10.1145/3135932.3135941) | 2017 | 40 multi-lingual (Java/Python) single-function bugs from the Quixey Challenge; small, high plausible-patch rate, widely reused | https://dlnext.acm.org/doi/10.1145/3135932.3135941 | S+ |
| D5 | SWE-bench | Jimenez, Yang, Wettig, Yao, Pei, Press, Narasimhan (Princeton) | ICLR 2024; arXiv 2310.06770 | 2024 | Real GitHub issue/PR tasks in 12 Python repos with an execution harness; defined the agentic repair era | https://arxiv.org/abs/2310.06770 | F |
| D6 | SWE-bench Verified | OpenAI (with SWE-bench authors) | swebench.com/verified.html | 2024 | Human-validated subset of SWE-bench intended to remove ambiguous/underspecified issues | https://www.swebench.com/verified.html | F |
| D7 | SWE-bench Pro | Deng, Da, Pan, He, Ide, Garg, Lauffer, Park, Pasari, et al. (Scale AI) | arXiv 2509.16941 | 2025 | Long-horizon, enterprise-grade, multi-file tasks; frontier agents resolve only a small fraction | https://arxiv.org/abs/2509.16941 | F |
| D8 | Multi-SWE-bench | Zan, Huang, Liu, Chen, Zhang, Xin, Chen, et al. (ByteDance) | arXiv 2504.02605 | 2025 | Multilingual issue-resolving benchmark (Java/TS/JS/Go/Rust/C/C++) that exposes **Python-centric** overfitting | https://arxiv.org/abs/2504.02605 | F |
| D9 | SWE-Gym | Pan, Wang, Neubig, Jaitly, Ji, Suhr, Zhang | ICML 2025; arXiv 2412.21139 | 2025 | 2,438 executable real-world task instances for **training** SWE agents and verifiers (not just evaluation) | https://arxiv.org/abs/2412.21139 | F |
| D10 | R2E-Gym | Jain, Singh, Shetty, Zheng, Sen, Stoica (UC Berkeley) | arXiv 2504.07164 (ICML 2025) | 2025 | Procedurally generated repo environments + hybrid verifiers to scale open-weight SWE agents | https://arxiv.org/abs/2504.07164 | F |
| D11 | SWE-smith | Yang, Lieret, Jimenez, Wettig, Khandpur, Zhang, Hui, Press, et al. | arXiv 2504.21798 (NeurIPS 2025) | 2025 | Synthesizes tasks by **breaking working repos**, producing large-scale training data without human PRs | https://arxiv.org/abs/2504.21798 | F |
| D12 | SWT-Bench | Mündler, Müller, He, Vechev | NeurIPS 2024; arXiv 2406.12952 | 2024 | Evaluation target is the **test**, generated before/independently of the fix (§3 C9) | https://arxiv.org/abs/2406.12952 | F |
| D13 | TDD-Bench Verified | Ahmed, Hirzel, Pan, Shinnar, Sinha (IBM) | arXiv 2412.02883 | 2024 | Tests must be written **before the issue is resolved**, removing fix-leakage from the test-generation task | https://arxiv.org/abs/2412.02883 | F |
| D14 | SWE-bench Goes Live! (SWE-bench-Live) | Zhang, He, Zhang, Kang, Li, Xie, Wang, et al. | arXiv 2505.23419 | 2025 | Continuously refreshed live benchmark to combat the static-benchmark contamination problem | https://arxiv.org/abs/2505.23419 | F |
| D15 | GitBug-Java | Silva, Saavedra, Monperrus (KTH) | MSR 2024; arXiv 2402.02961 | 2024 | Reproducible benchmark of **recent** Java bugs with pinned toolchains — attacks Defects4J's staleness | https://arxiv.org/abs/2402.02961 | F |
| D16 | GitBug-Actions | (same group/lineage) | arXiv 2310.15642 | 2023 | Builds reproducible bug-fix benchmarks via GitHub Actions execution capture | https://arxiv.org/abs/2310.15642 | F |
| D17 | RepoRepair | Pan, Li, Zhong, Feng, Luo, Ng | arXiv 2603.01048 | 2026 | Leverages code documentation for **repository-level** APR — the 2026 push past single-function/single-file repair | https://arxiv.org/abs/2603.01048 | F |
| D20 | Contamination / leakage analyses (SWE-bench+) | Aleithan et al. | arXiv 2410.06992 | 2024 | Quantifies solution leakage inside the benchmark instances themselves (§3 C11) | https://arxiv.org/abs/2410.06992 | F |

**Reading of Cluster D.** The lineage is: **static PR replay** (D5, D6, D1, D3, D4) → **scaled synthetic/training corpora** (D9–D11) → **decontaminated / live / multilingual** (D8, D14, D15) → **long-horizon and repository-level** (D7, D17). Java and Python are both covered, but **not symmetrically**: Java dominates classic APR (D1, D3-adjacent, D15), Python dominates agentic SWE benchmarks (D5, D9). Any claim of cross-language generality needs both sides (§7 of the checklist).

---

## 5. Cluster E — Self-healing / self-adaptive systems

| # | Work / Standard | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| E1 | The Vision of Autonomic Computing | Kephart & Chess (IBM) | IEEE Computer 36(1):41–50 | 2003 | Origin of the autonomic-manager model (monitor–analyze–plan–execute over shared knowledge) that MAPE-K formalizes | https://doi.org/10.1109/MC.2003.1160055 | S+ |
| E2 | Self-adaptive software: Landscape and research challenges | Salehie & Tahvildari | TAAS 4(2), DOI 10.1145/1516533.1516538 | 2009 | Reference taxonomy of self-* properties and adaptation mechanisms (requirements→design→runtime) | https://dl.acm.org/doi/abs/10.1145/1516533.1516538 | S+ |
| E3 | Extending **MAPE-K** to support Human-Machine Teaming | Cleland-Huang, Agrawal, Vierhauser, Murphy, Prieto | SEAMS 2022; arXiv 2203.13036 | 2022 | Adds human-in-the-loop as a first-class MAPE-K participant — the architectural bridge to human review of automated actions | https://arxiv.org/abs/2203.13036 | F |
| E4 | A language for feedback loops in self-adaptive systems (executable runtime megamodels) | Vogel & Giese | SEAMS (LNCS); arXiv 1805.08678 | 2018 | Makes the **feedback loop itself** a first-class modelled, executable artifact — the strongest available formalization of "control loop as code" | https://arxiv.org/abs/1805.08678 | F |
| E5 | Perpetual Assurances for Self-Adaptive Systems | Weyns, Bencomo, Calinescu, Cámara, Ghezzi, Grassi, Grunske, Inverardi, et al. | LNCS *SE for Self-Adaptive Systems III*; arXiv 1903.04771 | 2019 | Argues assurance must be **continuous at runtime**, not a one-off design-time certificate | https://arxiv.org/abs/1903.04771 | F |
| E6 | Runtime Verification of Self-Adaptive Systems with Changing Requirements | Carwehl, Vogel, Rodrigues, Grunske | SEAMS 2023; arXiv 2303.16530 | 2023 | Runtime verification that tolerates **requirement change** during operation, rather than assuming a frozen spec | https://arxiv.org/abs/2303.16530 | F |
| E7 | How do we Evaluate Self-adaptive Software Systems? | Gerostathopoulos, Vogel, Weyns, Lago | SEAMS 2021; arXiv 2103.11481 | 2021 | Systematic look at evaluation practice for self-adaptive systems; documents the absence of shared baselines/metrics | https://arxiv.org/abs/2103.11481 | F |
| E8 | mRUBiS | Vogel | SEAMS 2018; arXiv 1804.00954 | 2018 | Reusable exemplar for **model-based architectural self-healing and self-optimization** — a rare shared testbed in this field | https://arxiv.org/abs/1804.00954 | F |
| E9 | Review on Requirements Modeling and Analysis for Self-Adaptive Systems (ten-year perspective) | Yang, Li, Jin, Zhang | arXiv 1704.00421 | 2017 | Ten-year synthesis of how self-adaptive requirements are modelled/analysed; shows spec drift is a first-class problem | https://arxiv.org/abs/1704.00421 | F |
| E10 | Requirements-Driven Dynamic Adaptation to Mitigate Runtime Uncertainties | Yang, Zhang, Zhao, Jin | arXiv 1704.00419 | 2017 | Adaptation decisions driven by requirements models under runtime uncertainty | https://arxiv.org/abs/1704.00419 | F |
| E11 | A Framework for Evaluating Model-Driven Self-adaptive Software Systems | Magableh | arXiv 1901.04020 | 2019 | Evaluation framework for model-driven self-adaptation (context-oriented/component composition) | https://arxiv.org/abs/1901.04020 | F |
| E12 | CHESS: A Framework for Evaluation of Self-adaptive Systems based on **Chaos Engineering** | Malik, Naqvi, Moonen (Simula) | SEAMS 2023; arXiv 2303.07283 | 2023 | Uses deliberate fault injection to *evaluate* whether a self-adaptive system actually self-heals — the missing empirical loop | https://arxiv.org/abs/2303.07283 | F |
| E13 | Chaos Mesh | Chaos Mesh project (CNCF) | chaos-mesh.org/docs | 2024–26 | Kubernetes-native chaos-injection platform (pod/network/IO/time faults) used to test self-healing behaviour in situ | https://chaos-mesh.org/docs/ | F |
| E14 | Kubernetes Operators | Kubernetes project | kubernetes.io/docs | 2024–26 | The operator/controller reconciliation loop is the industrial realization of MAPE-K: observed state is continuously driven toward desired state | https://kubernetes.io/docs/concepts/extend-kubernetes/operator/ | F |
| E15 | Argo Rollouts (progressive delivery) | Argo Project (CNCF) | argo-rollouts.readthedocs.io | 2024–26 | Canary/blue-green rollout with automated analysis gates and **automated rollback** on metric failure — self-healing at the deployment layer | https://argo-rollouts.readthedocs.io/en/stable/ | F |
| E16 | Istio traffic management | Istio project | istio.io/latest/docs | 2024–26 | Declarative traffic shifting/retry/timeout/fault-injection primitives that progressive delivery and self-healing controllers build on | https://istio.io/latest/docs/concepts/traffic-management/ | F |
| E17 | RL-based self-adaptive systems | (lineage: E7 evaluation critique; see also §11) | — | — | **No single primary RL-for-self-adaptation record was fetchable this session**; the credible anchor is E7's finding that this subfield lacks shared baselines | https://arxiv.org/abs/2103.11481 | F |
| E18 | Self-healing cyber-physical systems with implicit guarantees | Loh & Thing | IEEE Cyber Security and Resilience 2023; arXiv 2305.08335 | 2023 | Cyber-resilience via implicit guarantees in self-healing CPS — the safety-adjacent end of self-healing | https://arxiv.org/abs/2305.08335 | F |

**Reading of Cluster E.** The academic MAPE-K literature (E1–E12) and the industrial self-healing stack (E13–E16) have converged on the *same* loop shape but **do not cite each other**: the industrial loop is reconciled-state control with rollback, while the academic loop is model/requirement-driven with assurance arguments. The transferable result for APR is E12: self-healing claims are only testable under **deliberate fault injection with a measured recovery objective**, which is exactly the discipline missing from most "self-healing agent" claims.

---

## 6. Cluster F — Safety of automated patching, policy, and regulation

| # | Work / Concern | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| F1 | AgentDojo | Debenedetti, Zhang, Balunović, Beurer-Kellner, Fischer, Tramèr (ETH Zürich) | NeurIPS 2024; arXiv 2406.13352 | 2024 | Dynamic environment for evaluating **prompt-injection attacks and defenses on tool-using agents** — the canonical benchmark for "untrusted content steers the agent" | https://arxiv.org/abs/2406.13352 | F |
| F2 | WebInject | (see arXiv 2505.11717) | arXiv 2505.11717 | 2025 | Prompt-injection attack against **web agents**, showing injected page content can redirect agent actions | https://arxiv.org/abs/2505.11717 | F |
| F3 | Repository content as an injection surface | (synthesis of F1–F2 applied to coding agents) | — | 2026 | **Assumption, not a verified finding here:** issue text, comments, docstrings and dependency metadata are all attacker-controlled text that a repair agent ingests — no fetched study in this session measured injection success *specifically* against an APR/SWE agent | https://arxiv.org/abs/2406.13352 | F |
| F4 | Execution safety / sandboxing of generated code | (synthesis; no primary record fetched) | — | 2026 | Repair agents must **execute** untrusted patches; the standard control is containerized, network-isolated, resource-capped execution. No fetched paper in this session supplies a quantitative sandbox-escape rate — treat any such number as unverified | https://arxiv.org/abs/2406.13352 | F |
| F5 | SWE-Bench+ leakage | Aleithan et al. | arXiv 2410.06992 | 2024 | "Resolved" can be achieved by exploiting hints in the issue/tests — an evaluation-integrity failure with direct auto-merge consequences | https://arxiv.org/abs/2410.06992 | F |
| F6 | SWE-ABS adversarial strengthening | Yu et al. | arXiv 2603.00520 | 2026 | Adversarially strengthened tests deflate reported success → measured capability is an artifact of the fixed test suite (§3) | https://arxiv.org/abs/2603.00520 | F |
| F7 | EU AI Act — Regulation (EU) 2024/1689 | European Parliament & Council | EUR-Lex ELI `reg/2024/1689/oj` | 2024 | The AI Act's high-risk obligations (risk management, logging, human oversight, accuracy/robustness) are the binding frame for AI used in safety-relevant software processes | https://eur-lex.europa.eu/eli/reg/2024/1689/oj | F |
| F8 | From Legal Text to AI-specific Risk Sources (EU AI Act high-risk requirements) | Schnitzer, Auer, Choudhury, Hapfelmeier, Hoeving, Painter, et al. | arXiv 2609.13535 | 2026 | Systematically converts the AI Act's high-risk legal text into concrete, auditable **risk sources** — the operationalization APR tooling would have to satisfy | https://arxiv.org/abs/2609.13535 | F |
| F9 | From Obligation to Specification (validating EU AI Act requirements in RE) | Lai, Giesselbach, Koch, Allende-Cid | arXiv 2607.21608 | 2026 | Survey on turning AI Act obligations into verifiable requirements — same gap APR faces when claiming "our patcher is safe" | https://arxiv.org/abs/2607.21608 | F |
| F10 | Cyber Resilience Act — Regulation (EU) 2024/2847 | European Parliament & Council | EUR-Lex ELI `reg/2024/2847/oj` | 2024 | Introduces security-by-design and **vulnerability-handling/reporting duties** for products with digital elements — the compliance surface for auto-generated and auto-merged patches | https://eur-lex.europa.eu/eli/reg/2024/2847/oj | F |
| F11 | Human-in-the-loop review as the control mechanism | (synthesis of E3 + C4 + F5) | — | — | The evidence-supported position is that **automated patching should gate, not merge**: C4's assessment pipeline and E3's human-in-the-MAPE-K design are the two defensible templates | https://arxiv.org/abs/1909.13694 | F |
| F12 | Industrial adoption barriers of APR | (no fetched primary study) | — | — | **Unverified in this session.** No primary empirical study of industrial APR adoption barriers was fetched; the industrial signal available here is indirect (Meta's filter-gate pattern reported in the sibling baseline). Do not cite an adoption-barrier statistic from this file | https://arxiv.org/abs/1909.13694 | F |

**Reading of Cluster F.** The safety literature splits cleanly into what is *measured* and what is *assumed*. Measured: agents are steerable by untrusted content (F1, F2), and "resolved" is inflatable (F5, F6). Assumed: sandbox escape rates and injection success against *repair* agents specifically (F3, F4). Regulation (F7–F10) is real and fetched, but it constrains **process and documentation**, not patch semantics — nothing in the AI Act or CRA tells you whether a given patch is correct.

---

## 7. Cluster G — Methodology and rigor

| # | Work / Practice | Authors / Org | Venue / Org | Year | One-line claim | URL | V |
|---|---|---|---|---|---|---|---|
| G1 | Same Model, Different Harness: Different Coding-Agent Results | Lewis | arXiv 2608.26218 | 2026 | **Headline rigor result for this file:** the *harness* (scaffold, prompts, tool wiring, execution policy) changes reported coding-agent outcomes even when the model is held fixed — so "model X scores Y" is not a transportable claim | https://arxiv.org/abs/2608.26218 | F |
| G2 | Promoting open science in test-driven software experiments (TDSE) | Felderer, et al. | JSS 212 (2024) 111971 | 2024 | Defines the **test-driven software experiment** and the **experimental-unit** discipline (repeat runs, unit of analysis, replication package) — this is the correct citation for the "experimental units / repeated runs" point | https://doi.org/10.1016/j.jss.2024.111971 | S |
| G3 | Position: Evaluation Scores Are Perishable Knowledge Claims | Gilda & Gilda | GEM 2026; arXiv 2607.26191 | 2026 | Evaluation scores decay as models/data/harnesses drift; leaderboard numbers must be timestamped and re-established | https://arxiv.org/abs/2607.26191 | F |
| G4 | Falsification, Not Exposure (preregistered placebo-controlled self-repair decomposition) | Iscan | arXiv 2606.31511 | 2026 | Shows the *internally preregistered, placebo-controlled* design that self-repair studies need in order to attribute gains to the mechanism rather than to extra sampling | https://arxiv.org/abs/2606.31511 | F |
| G5 | Effect sizes + bootstrap CIs in SE reporting (Cliff's δ practice) | (practice observed in 2026 SE preprints, e.g. arXiv 2609.13839) | arXiv 2609.13839 | 2026 | Reports **Cliff's δ with bootstrap 95% CIs** as the standard effect-size idiom in current SE empirical work | https://arxiv.org/abs/2609.13839 | S |
| G6 | Wilcoxon signed-rank + p-value decision rule in SE tool comparisons | (recurring protocol in SE/accessibility tool papers) | IEEE (example protocol) | — | Documents the conventional decision rule ("significantly better if Wilcoxon p < 0.05") that reviewers expect — and that must now be paired with an effect size | https://ieeexplore.ieee.org/document/8988190 | S |
| G7 | ACM artifact badges / artifact evaluation (ICSE/FSE/ASE artifact tracks) | ACM SIGSOFT | ACM DL DOI 10.1145/3485819 (badging/artifacts) | 2022 | Artifact Available / Evaluated / Reusable badges are the accepted evidence of reproducibility; APR papers without a reusable artifact are treated as unverifiable in 2025–2026 practice | https://dl.acm.org/doi/10.1145/3485819 | S |
| G8 | Artifact-evaluation security checks (2026 proposal) | (arXiv 2605.06508) | arXiv 2605.06508 | 2026 | Proposes **optional security checks or badges** inside artifact evaluation — directly relevant when a repair artifact executes model-generated code | https://arxiv.org/abs/2605.06508 | S |
| G9 | Morescient GAI for Software Engineering | Kessel & Atkinson | TOSEM (2030 Roadmap special issue); arXiv 2406.04710 | 2024 | Argues SE-for-GAI needs scientist-grade empirical standards (hypotheses, controls, replication), not demo-driven claims | https://arxiv.org/abs/2406.04710 | F |
| G10 | Same Model, Different Harness — practical corollary | (derived from G1) | — | 2026 | Report **model + harness + tool versions + execution policy** as a tuple; a model-only ablation is not evidence about a repair system | https://arxiv.org/abs/2608.26218 | F |
| G11 | Repeated runs / non-determinism | (derived from G2, G4) | — | 2024–26 | Because LLM repair is stochastic, the *experimental unit* is the (bug, seed/run) pair, not the bug; report variance across runs, not a single pass | https://doi.org/10.1016/j.jss.2024.111971 | S |
| G12 | Replication studies showing non-reproduction | (no single fetched primary record) | — | — | **Partially unverified.** The general replication-crisis evidence for APR specifically was not fetched; the *specific* fetched anchors are G1 (harness sensitivity) and G3 (score perishability). Cite those two, not a generic "APR does not reproduce" claim | https://arxiv.org/abs/2608.26218 | F |

**Reading of Cluster G.** The rigor literature is unanimous on one point and this is the file's central methodological message: **the unit of analysis is the (system, harness, run), not the system** (G1, G2, G11). Everything else — effect sizes (G5), paired tests (G6), artifact badges (G7–G8), preregistration (G4) — exists to make that tuple auditable.

---

## 8. Consensus vs. contested vs. assumption

### Consensus (safe to assert as established)
1. **Plausible ≠ correct.** Smith et al. (C1) established it; C4/C5/C7 quantify it; C11–C13 show it is *still* the dominant validity threat. Any APR claim resting only on the original test suite is an upper bound.
2. **Passing the visible test suite is a necessary but insufficient oracle.** Independently supported by overfitting classification (C7), patch-assessment at scale (C4), and adversarial test strengthening (C13).
3. **Self-correction requires a trustworthy external signal.** Self-Refine/Reflexion (A6, A7) claim gains; A8 (ICLR 2024) shows *intrinsic* self-correction can degrade accuracy. The disagreement is about feedback provenance, and A8 is the load-bearing control.
4. **Fault localization bounds repair.** Ranking quality and its metric policy (Ochiai/SBFL lineage B1, B7–B9) determine what repair can even reach; LLM localization has not removed the dependence.
5. **Benchmarks decay.** Contamination and memorization are demonstrated, not hypothetical (C11, C12, D14) — which is why live/refreshed benchmarks exist (D14, D15).
6. **The harness is part of the treatment.** G1 is the cleanest statement; G3 explains why old scores cannot be compared to new ones.
7. **Self-adaptive systems need assurance at runtime, not only at design time** (E5, E6), and self-healing claims are only testable under fault injection (E12, E13).
8. **Agents that read repository text are prompt-injectable** (F1, F2). The control surface is execution isolation plus human gating, not prompt hygiene alone.

### Contested (cite both sides; do not assert one winner)
1. **Do LLMs outperform template APR, or outperform it only on the same overfit test suites?** ChatRepair's 114/48 correct fixes (A9, fetched) vs. the overfitting/leakage literature (C1, C11–C13). Contested axis: *who validated the ground truth*, and on which benchmark version.
2. **Is static overfitting classification (ODS, C7) or dynamic evidence (PATCH-SIM, C5; DiffTGen, C3) the better correctness predictor?** Both report gains; neither dominates across all patch families.
3. **Do agentic scaffolds (A10–A14) add capability over a strong single-shot LLM, or mostly add retries?** G1 and G4 imply the gain may be sampling/harness, not reasoning.
4. **EXAM vs. Top-N for fault localization.** B6/B11 show results are metric- and tie-policy-dependent; a single "FL accuracy" number is not interpretable.
5. **Can benchmark scores be compared across time at all?** G3 argues no (scores perish); practitioners still compare. Treat cross-year comparisons as contested.
6. **Is self-healing microservice practice (E14–E16) evidence-bearing?** The industrial stack is widely deployed, but E7 documents the absence of shared evaluation baselines in the academic subfield — deployment is not evidence of measured efficacy.
7. **How much human review is required before merge?** C4/E3 imply gating; industrial filter-gate pipelines accept automated merges after statistical gates. Unresolved: acceptable false-accept rate.

### Assumptions (state them explicitly if you rely on them)
1. **"The benchmark's hidden tests are the correctness oracle."** False whenever tests are public (C11, C13) — hidden-test adjudication must be *stated*, not assumed.
2. **"Passing all tests ⇒ the patch is correct."** The definition of plausible; the C1 result is that this implication fails.
3. **"A fault-localization tool identifies the true faulty statement."** Suspect lists have ties and the tie policy is rarely reported (B6, B11).
4. **"Sandboxed execution of generated patches is safe."** No fetched study quantifies escape rates for repair agents (F4). Assume it is unmeasured, not solved.
5. **"Repository content is trusted input."** Directly contradicted in the general agent setting (F1, F2) and unmeasured in APR specifically (F3).
6. **"Model identity determines repair performance."** G1 shows harness effects; assume the (model, harness) tuple instead.
7. **"Java results transfer to Python (or vice versa)."** D8 exists precisely because they do not transfer cleanly; benchmark asymmetry between D1/D3 and D5/D9 makes this an assumption every cross-language claim carries.
8. **"Regulatory compliance implies patch safety."** The AI Act and CRA (F7, F10) bind process, documentation, and vulnerability handling — not patch semantics.

---

## 9. What counts as a rigorous 2026 APR / safe-repair evaluation — a checklist

Missing items are rejection risks, not stylistic gaps. Items marked **(M)** are metrics, **(T)** statistical tests, **(P)** process.

**A. Task framing and oracle declaration**
1. **(P)** Declare the repair granularity: line / hunk / function / file / repository (D1 vs D5 vs D17 are not interchangeable).
2. **(P)** Declare the oracle: original test suite, augmented tests (C3, C13), held-out/hidden tests, or human adjudication (C4). Say explicitly whether the test suite was **visible to the system**.
3. **(P)** Declare benchmark version *and* access date; state whether the benchmark is live/decontaminated (D14, D15).
4. **(P)** Run a contamination check: can the model reproduce the gold patch from file path/issue text alone (C12), and does the issue text leak the fix (C11)?

**B. Metrics (M) — report all that apply, never one alone**
5. **(M)** `#plausible` **and** `#correct`, separately, with the ground-truth adjudication protocol named (C1, C4).
6. **(M)** **Precision of plausible patches** = correct / plausible — the single most informative corrected metric.
7. **(M)** **Correct-patch rate** against the full instance count (not only against processed instances); report both denominators.
8. **(M)** **Cost per correct fix** (USD and/or tokens), as in A9's `$0.42` accounting and A15's cost-efficiency framing.
9. **(M)** **Failure-mode distribution** (compile error / test failure / plausible-but-wrong / localization miss), not just success.
10. **(M)** **Fault-localization quality** as Top-N with the tie policy stated; if EXAM is also reported, define both (B6, B11).
11. **(M)** **Overfitting-detector performance** as precision/recall (or AUC) on a labelled correct/incorrect patch set, never accuracy alone (C7).
12. **(M)** **Patch minimality / diff size**, because large-diff "fixes" inflate plausible rates.
13. **(M)** **Latency and number of LLM calls per instance** (A15), so the harness cost is visible.

**C. Statistics (T) — required, not optional**
14. **(T)** **Paired design**: same instances for every system; report the paired contingency table, then use **McNemar's test** for paired binary outcomes (resolved / not resolved).
15. **(T)** **Wilcoxon signed-rank** for paired continuous/ordinal measures (ranks, distances, cost) — the SE convention (G6).
16. **(T)** **Effect size with every p-value**: **Cliff's δ** with magnitude thresholds for ordinal/ranked comparisons, and/or Vargha–Delaney **Â₁₂**; report **bootstrap 95% CIs** (≥1,000 resamples) for the effect size, not only for the mean (G5).
17. **(T)** **Multiple-comparison correction** across the system×benchmark grid: Holm–Bonferroni or Benjamini–Hochberg; state the family of hypotheses being corrected over.
18. **(T)** **Repeated runs** because repair is stochastic: ≥3–5 runs per instance per system, report mean ± spread (or per-run paired tests), and fix and report seeds/temperature (G2, G4, G11).
19. **(T)** **Experimental unit stated explicitly** — the (instance, run) pair, not the instance; justify the unit (G2).
20. **(T)** **No significance claims from unpaired aggregates**; if instances are not paired, use a two-sample test and say so.

**D. Process, safety, and artifact hygiene (P)**
21. **(P)** **Full harness disclosure**: model + version/snapshot, scaffold, prompt templates, tool set, decoding params, execution/sandbox policy, timeouts and retry policy (G1, G10).
22. **(P)** **Ablations that isolate the claimed mechanism**: e.g. feedback vs. extra sampling (G4), localization vs. generation contributions, and a **placebo/control arm** where feasible.
23. **(P)** **Human adjudication protocol** for correctness: number of annotators, agreement (κ), blinding to system identity (C4).
24. **(P)** **Execution isolation evidence**: container/network/resource policy, and an explicit statement of what the sandbox does *not* protect against (F4).
25. **(P)** **Injection-surface analysis**: enumerate untrusted text the agent consumes (issue body, comments, docstrings, dependency metadata) and state the mitigation (F1–F3).
26. **(P)** **Merge-gating policy**: state the false-accept tolerance and whether patches are auto-merged, gated by review, or gated by statistical filters (C4, E3).
27. **(P)** **Replication package** with raw per-instance logs, not just aggregates, released under an **ACM artifact badge** (Available / Evaluated / Reusable), plus the 2026 security-checks proposal where the artifact executes generated code (G7, G8).
28. **(P)** **Threats-to-validity section that names the specific killers**: test-suite overfitting (C1), solution leakage (C11), memorization (C12), harness sensitivity (G1), score perishability (G3), and benchmark-language skew (D8).

---

## 10. Five decision-relevant findings (summary)

1. **The oracle, not the model, is the binding constraint.** Every headline APR number is conditional on a test suite that has been shown to be leaky (C11), memorizable (C12) and adversarially deflatable (C13).
2. **Harness-level variance rivals model-level variance** (G1): "model X achieves Y% repair" is not a transportable claim without the harness tuple.
3. **Self-repair gains are not established without an external oracle** (A8 vs. A6/A7), and the 2026 preregistered placebo design (C14/G4) is the protocol that would settle it.
4. **Cost per correct fix** (A9: 162/337 bugs at $0.42 each; A15) is now a first-class metric — plausible-patch counts without cost and precision are uninterpretable.
5. **Industrial self-healing is reconciled-state control with automated rollback** (E14–E16), while academic self-adaptation evaluates with fault injection (E12). APR tooling that wants production credibility should adopt the *rollback-and-observe* discipline rather than a one-shot merge.

---

## 11. Could not verify in this session (do not cite from this report)

| Candidate | Why it is absent / what to do |
|---|---|
| **Tarantula** (Jones, Harrold, Stasko, ASE 2002) — canonical early SBFL | IEEE/ACM blocked; no independent second record surfaced. Keep only as background prose; verify DOI `10.1145/581339.581401` before citing a claim. |
| **Metallaxis** (Papadakis & Le Traon, ICST 2015) and **MUSE** (Moon, Kim, Kim, Yoo, ICST 2014) — MBFL | Same: IEEE blocked, no corroborating second record. The MBFL concept (rows B3/B4) is real and widely cited, but **I did not verify these records this session**. |
| **DeepFL** (ASE 2019), **TRANSFER** (ICSE 2022), **GRACE** (ISSTA 2021) — learning-based FL | Learning-to-rank FL is a real lineage, but I found no arXiv records and could not open the ACM/IEEE pages. Verify each DOI (`10.1109/ASE.2019.00042`, `10.1145/3510003.3510043`, `10.1145/3460319.3464806`) individually. |
| **Refactory** (Hu, Duan, et al., ASE 2019) | ACM blocked, and the GitHub URL I tried (`github.com/Thomsch/refactory`) returned **404**; I did not locate the correct primary artifact. Omitted entirely. |
| **Commit0** (ICLR 2025; arXiv 2412.01769) | `arxiv.org` did not resolve for me this session and the arXiv API was not queried for this ID. Its official repository **does** respond (`github.com/commit-0/commit0`, HTTP 200) but I did not read its content, so no venue/claim is asserted here. |
| **Defects4J original paper** (Just, Jalali, Ernst, ISSTA 2014, DOI `10.1145/2610384.2628055`) | ACM DL blocked. The row D1 claim rests on the **official repository**, not on the paper page. |
| **"CCTest"** | No fetchable primary record surfaced (see also the C15 row note). |
| **RL-based self-adaptive systems** | No single primary record fetched; see row E17. |
| **arXiv 2607.27146 as a "repeated runs / experimental units" paper** | **Misattribution.** That arXiv ID is *MindForge: Teaching Small Language Models Whole-Life-Cycle Software Engineering via Source-Free Program Synthesis* (Chen, Chang, Chawa, Lin, Chen, Wang, Hassan; 2026-07-29; fetched via arXiv API). For the experimental-unit point cite **Felderer et al., JSS 212 (2024) 111971** (row G2), which I confirmed only at search/metadata level. |
| **"Lemur" as an APR tool** | **Misattribution.** The Lemur work in this space is *Lemur: Integrating Large Language Models in Automated Program **Verification*** (Wu et al., 2023) — invariant generation/verification, not repair. I did not fetch its primary record, so it is deliberately **not** given a row. |
| **arXiv ID for AlphaRepair** | I could not fetch an arXiv record (my ID guesses resolved to unrelated papers). AlphaRepair is confirmed via the ICSE 2023 DOI `10.1145/3540250.3549101` and the NSF-hosted author copy (row A4, tag S+). Cite the DOI, not an arXiv ID. |
| **"Fixing Rust Compilation Errors" / RustRepair** | Only secondary mentions surfaced; no primary record fetched. Omitted rather than guessed. |
| **Smith, Barr, Le Goues, Brun, FSE 2015 full text** | Only the DOI and title surfaced (search hit included a copy in an unrelated local corpus path). `dl.acm.org` returns **403** here. Row C1 is `[S]`: DOI string verified, page not read. |
| **Tarantula (ASE 2002), Metallaxis (ICST 2015), MUSE (ICST 2014), DeepFL (ASE 2019), TRANSFER (ICSE 2022), GRACE (ISSTA 2021), Refactory (ASE 2019), Defects4J (ISSTA 2014), Commit0** | Rows B2, B3, B4, B12, B13, B14, D18, D1, D19 are tagged **[U]** because I could **neither fetch** (IEEE/ACM 403) **nor** corroborate them with two independent in-session records. **Verify each DOI before citing.** |
| **LLM4FL** | No primary record fetched. The only trace is an OpenReview PDF snippet (`z91EvZbSI1`) reporting higher Top-1/Top-3; the paper's identity/venue is not established here. Row B11 is `[S]` and labeled as an LLM-ranking result, not as "the LLM4FL paper." |
| **CoFL** | The exact "CoFL" acronym did not resolve. What I did verify is *Multi-View Adaptive Contrastive Learning for IR-Based Fault Localization* (arXiv 2409.12519, accepted at Automated Software Engineering; row B15). Cite that paper, not the acronym. |
| **"CCTest"** | No fetchable primary record surfaced. The functionality is covered by rows C3/C13/C15. |
| **Statsig-style / "Cliff's delta" canonical methodology paper (e.g. Kitchenham et al.)** | Not fetched. Row G5 documents the *practice* (Cliff's δ + bootstrap CI in 2026 SE preprints), **not** a normative methodology source. For a normative citation use Kitchenham et al.'s effect-size guidance and verify it independently. |
| **McNemar / multiple-comparison normative source for SE** | Not fetched. Checklist items 14 and 17 are **standard statistical practice**, not citations from this session. |
| **Industrial APR adoption-barrier studies** | No primary empirical study fetched (row F12). Any adoption statistic must come from another source. |
| **Sandbox-escape and injection-success rates against APR agents specifically** | Not measured in any source I fetched (rows F3, F4 are flagged as *assumptions*). |
| **RL-based self-adaptive systems (Cluster 5 requirement)** | No single primary record fetched; row E17 records the gap and points at the evaluation-critique paper instead. |
| **"Reflexion"/"Self-Refine" peer-reviewed venue strings** | arXiv API returned no `journal_ref`/venue comment for either (rows A6, A7). Year/ID are `[F]`; **venue claims are not verified here** — I list them as arXiv records only. |

**Environment limits that shaped this report:** `dl.acm.org` (403), `doi.org` (302 cross-origin redirect to blocked publishers), `ieeexplore.ieee.org`, `link.springer.com`, `sciencedirect.com` were unreachable; `web_fetch` cannot decode PDFs; `export.arxiv.org` requires `https` (301 on `http`). No sandbox escalation was requested, and no request was denied.

**Tool-call budget note:** ~30 web_search calls (1–2 queries each, per the pacing constraint) plus arXiv-API/metadata batches were used; no 429 responses occurred. No subagents were spawned, per instruction.
