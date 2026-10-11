# R1 — Frontier SOTA for LLM / Multi-Agent Unit & Integration Test Generation (2025–2026)

**Compiled:** 2026-10-10 · **Method:** primary-source web retrieval (arXiv abs/HTML, ACL Anthology, Crossref, OpenAlex, DBLP, conference program pages, publisher abstract pages). Every number below was read from a fetched source. Anything that could not be confirmed is explicitly marked **NOT VERIFIED**.

---

## 1. One-line summary of the state of the art

On the only large, real-repo Python benchmark with all three metrics (TestGenEval, 1,210 file pairs), the verifiable frontier is **TestForge (GPT-4o, 25 agentic iterations): pass@1 84.3%, line coverage 44.4%, mutation score 33.8%** — versus **35.2% coverage / 18.8% mutation for the best single-shot model (GPT-4o)** in the benchmark paper itself; meanwhile the JVM ecosystem is far ahead (TestAgent 92.34% line / 83.69% mutation on 6 Java projects) because Java benchmarks are method/class-level, and the single most consequential 2026 result is a **negative** one for hand-engineered orchestration: **Konstantinou, Degiovanni & Papadakis (ICST 2026) show a plain single-prompt LLM beats HITS, SymPrompt, TestSpark and CoverUp on all three metrics** (49.95%/35.33%/33.82% vs CoverUp 38.85%/25.11%/26.26%) on 393 Java classes / 3,657 methods.

---

## 2. Main data-point table

All values are **percentages** unless noted. "Grade": **A** = top peer-reviewed venue (ICSE/FSE/ASE/ISSTA/ICST/TOSEM/TSE/PACMSE/NeurIPS/ICLR/ACL/APSEC), **B** = arXiv preprint / workshop / companion track, **C** = tech report / vendor / news.

### 2.1 Python ecosystems — TestGenEval family (the primary AITester-relevant protocol)

| System | Metric | Value | Benchmark / dataset (size) | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **TestGenEval** (benchmark) | dataset size | **68,647 tests / 1,210 code-test file pairs / 11 Python repos** (3,523–78,287 stars); median gold coverage 60.4% | TestGenEval | SWE-bench-derived; dockerized; tests >60 s filtered out | Jain, Synnaeve, Rozière; 2024-10 (v2 2025-03); **ICLR 2025** | arXiv:2410.00752 | **A** |
| TestGenEval (Lite) | dataset size | **160 code-test file pairs** | TestGenEvalLite | sampled to be representative | same | arXiv:2410.00752 App. A.2 | **A** |
| TestGenEval (paper, file-length stat) | avg code / test file length | **1,157 LOC / 943 LOC** (v1 text) vs **782 LOC / 677 LOC** (v2 text) | TestGenEval | — | same | arXiv:2410.00752 v1 vs v2 | **A** — **source conflict, see §6** |
| **GPT-4o** (single-shot) | any-pass@1 / coverage / mutation | **64.0% / 35.2% / 18.8%** | TestGenEval full, 1,210 programs | single-shot, temperature 0.2, max context | Jain et al. 2025 | arXiv:2410.00752 Table 2 | **A** |
| GPT-4o (single-shot) | all-pass@1 | **7.5%** | TestGenEval full | same | same | same | **A** |
| **Llama 3.1 405B** (single-shot) | all-p@1 / any-p@1 / cov / mut | **17.7% / 73.1% / 35.0% / 16.4%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| **Codestral 22B** (single-shot) | all-p@1 / any-p@1 / cov / mut | **26.8% / 72.7% / 33.0% / 14.2%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| DeepSeekCoder 16B | all-p@1 / any-p@1 / cov / mut | **23.0% / 63.7% / 28.2% / 12.1%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| Llama 3.1 70B | all-p@1 / any-p@1 / cov / mut | **7.8% / 60.7% / 30.6% / 15.4%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| Gemma 27B | all-p@1 / any-p@1 / cov / mut | **7.4% / 57.7% / 30.1% / 14.6%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| Gemma 9B | all-p@1 / any-p@1 / cov / mut | **3.5% / 42.1% / 20.2% / 9.0%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| Llama 3.1 8B | all-p@1 / any-p@1 / cov / mut | **3.1% / 30.5% / 14.1% / 6.8%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| CodeLlama 70B | all-p@1 / any-p@1 / cov / mut | **14.0% / 22.7% / 7.0% / 2.5%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| CodeLlama 7B | all-p@1 / any-p@1 / cov / mut | **3.2% / 4.1% / 1.2% / 0.5%** | TestGenEval full | single-shot, temp 0.2 | same | same | **A** |
| **Codestral 22B** (test *completion*) | first: p@1/p@5/+cov · last: p@1/p@5 | **38.3% / 61.7% / +24.0% · 50.4% / 74.3%** | TestGenEval completion | temp 0.2 (p@1), 0.8 (p@5) | same | arXiv:2410.00752 Table 3 | **A** |
| *Top models, last-test completion* | coverage added | **< 1%** | TestGenEval completion | — | same | same | **A** |
| **TestForge** | **pass@1 / line cov / mutation** | **84.3% / 44.4% / 33.8%** | **TestGenEval full (1,210)** | **GPT-4o, agentic, 25 iterations, ≤447 s/data point, $0.63/file** | Jain & Le Goues; 2025; arXiv preprint + CMU-S3D-25-100 tech report | arXiv:2503.14713 | **B** |
| GPT-4o 0-shot (TestForge's own baseline) | pass@1 / cov / mut | **64.0% / 34.8% / 18.4%** | TestGenEval full | single-shot, temp 0.2 (TestGenEval prompt) | same | arXiv:2503.14713 Table 1 | **B** |
| TestForge | pass@1 / cov / mut | **100.0% / 60.0% / 31.6%** | TestGenEval Python-3.10 subset (45 programs) | GPT-4o, 25 iter | same | same | **B** |
| GPT-4o 0-shot | pass@1 / cov / mut | **97.8% / 54.0% / 27.3%** | 45-program subset | single-shot | same | same | **B** |
| Pynguin | pass@1 / cov / mut | **60.0% / 24.0% / 4.2%** | 45-program subset | SBST, 600 s | same | same | **B** |
| CodaMosa | pass@1 / cov / mut | **62.2% / 30.2% / 2.7%** | 45-program subset | SBST+LLM (GPT-4o), 600 s | same | same | **B** |
| TestForge | CodeBLEU / ROUGE / Edit Sim | **32.1 / 23.0 / 27.0** | TestGenEval full | lexical metrics | same | arXiv:2503.14713 Table 2 | **B** |
| **CovQValue** ("Planning to Explore") | branch coverage vs greedy selection | **+51–77% (relative) higher branch coverage; wins on 77–84% of targets** | **TestGenEval Lite** | greedy-vs-Q-value plan selection, 3 LLMs (unspecified in abstract) | Amayuelas, Laakom, Piękos, Wang, Xu, Wang, Schmidhuber, Wang; 2026 | arXiv:2604.05159 | **B** |
| CovQValue | success rate | **40–74%** | RepoExploreBench (new, built by the authors) | iterative test generation | same | same | **B** |
| **TestForge / CoverUp non-comparability** | — | TestForge **explicitly could not run CoverUp on TestGenEval**: cost ≈ **$2/data point** ⇒ **$2,400** for the benchmark vs $762 for TestForge | TestGenEval | stated resource limit | Jain & Le Goues 2025 | arXiv:2503.14713 §4.2 | **B** |

### 2.2 Python ecosystems — CoverUp's own benchmark suite (CM/PY/MT)

| System | Metric | Value | Benchmark / dataset (size) | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **CoverUp** | overall line / branch / line+branch | **63.8% / 49.2% / 60.3%** | **CM suite: 425 Python modules, ≈100,000 LOC, 35 projects** | **GPT-4o, agentic (coverage-feedback loop, ≤2 continued prompts)** | Pizzorno & Berger; **FSE 2025** (PACMSE vol. 2) | DOI 10.1145/3729398 · arXiv:2403.16218 | **A** |
| CoverUp | median per-module line / branch / L+B | **82.4% / 66.7% / 79.6%** | CM suite | same | same | Table 1 | **A** |
| CodaMosa (codex) | overall / median L+B | **48.7% / 55.1%** | CM suite | original CodaMosa config 0.8-uninterp | same | Table 1 | **A** |
| CodaMosa (GPT-4o) | overall / median L+B | **45.2% / 47.2%** | CM suite | 10 min/module | same | Table 1 | **A** |
| CoverUp (ablated — LLM only) | overall / median L+B | **34.0% / 38.5%** | CM suite | prompt without coverage info/tools/continued chat | same | Table 1 | **A** |
| CoverUp | overall line / branch / L+B | **97.0% / 99.2% / 97.1%** | **PY suite: 84 modules, ≈5,000 LOC** | GPT-4o, agentic | same | Table 1 | **A** |
| **CoverUp** | overall line / branch / L+B | **89.2% / 88.7% / 89.0%** | **MT suite: 163 HumanEval-derived functions, ≈2,000 LOC** | GPT-4o, agentic | same | Table 2 | **A** |
| MuTAP (codex few-shot) | overall line / branch / L+B | **80.8% / 71.7% / 77.7%** | MT suite | few-shot | same | Table 2 | **A** |
| MuTAP (codex zero-shot) | overall L+B | **77.0%** | MT suite | zero-shot | same | Table 2 | **A** |
| MuTAP (GPT-4o zero-shot) | overall L+B | **76.8%** | MT suite | zero-shot | same | Table 2 | **A** |
| MuTAP (GPT-4o few-shot) | overall L+B | **10.4%** | MT suite | few-shot (reproduced failure) | same | Table 2 | **A** |
| CoverUp | cost / time | **$399, 4.0 h, 28,690 prompts** on CM suite | CM suite | GPT-4o pricing at time of writing | same | Table 3 | **A** |
| CodaMosa (GPT-4o) | cost / time | **$265, 71.0 h, 30,368 prompts** | CM suite | — | same | Table 3 | **A** |
| CoverUp | contribution of continued dialogue | **60.3% of successes from prompt 1, 27.2% from prompt 2, 12.5% from prompt 3 (≈40% from refinement)** | CM suite | log analysis | same | §4.4 | **A** |
| SymPrompt (for reference, as cited by CoverUp) | line coverage | **74%** | undisclosed subset of 897 functions | GPT-4, path-constrained prompting | Ryan et al. 2024, **cited in** CoverUp §2 | arXiv:2403.16218 §2 | **A** (as cited) |

### 2.3 JVM / Java ecosystems

| System | Metric | Value | Benchmark / dataset (size) | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **TestAgent** | execution rate / **line cov / branch cov / mutation** | **97.46% / 92.34% / 90.24% / 83.69%** | **6 Java projects, 1,451 methods** | multi-agent (Planner+Generator+Reviewer), repository-level Code Knowledge Graph, tool APIs | Shang, Zhang, Zhan, Huang, Fang, Chen; **FSE Companion 2026** | DOI 10.1145/3803437.3806428 · arXiv:2607.09101 | **A** (companion) / **B** (arXiv) |
| TestAgent | bug detection | **154 real-world bugs, precision 92.22%** | same 6 projects | same | same | same | **A**/**B** |
| **Plain-LLM (method-level, single prompt)** | **line / branch / mutation** | **49.95% / 35.33% / 33.82%** | **6 complete Java repos; 393 classes; 3,657 methods** | gpt-4o-mini / Llama 3.3 70B / DeepSeek V3; temp 0.1; ≤5 repair iterations | Konstantinou, Degiovanni, Papadakis; **ICST 2026 Research Papers** | arXiv:2601.09695 | **A** |
| **HITS** | line / branch / mutation | **42.43% / 29.49% / 27.97%** | same 393 classes | same models, tool default config | same | same | **A** |
| **SymPrompt** | line / branch / mutation | **40.95% / 27.19% / 28.40%** | same | same | same | same | **A** |
| **CoverUp** (Java replication) | line / branch / mutation | **38.85% / 25.11% / 26.26%** | same | same | same | same | **A** |
| **TestSpark** | line / branch / mutation | **23.65% / 16.48% / 13.88%** | same | LLM configuration only | same | same | **A** |
| Plain-LLM (class-level) | line / branch / mutation | **33.53% / 21.05% / 22.08%** (only 1,562 requests) | same | class as prompt unit | same | same | **A** |
| Plain-LLM (class+method combined) | line / branch / mutation | **53.67% / 38.74% / 36.55%** | same | merged passing suites | same | same | **A** |
| Plain-LLM hybrid (class→uncovered methods) | line / branch / mutation | **52.30% / 38.84% / 36.76%** (10,548 requests, −≈20%) | same | hybrid granularity | same | same | **A** |
| LLM request counts | requests | **HITS 23,865 · SymPrompt 8,413 · TestSpark 7,963 · CoverUp 12,264 · Plain(method) 11,718** | same | API calls | same | Table III | **A** |
| Compile/pass rates | — | **≈20% of generated tests do not compile; ≈43% do not pass**; class-level pass 50.53% (3,232 tests), method-level pass 53.40% (12,158 tests) | same | uniform post-processing | same | §V-C | **A** |
| **CANDOR** | line / branch / mutation | **0.991 / 0.970 / 0.980** (mutation 2384/2443) | **HumanEvalJava, 160 Java programs** | multi-agent, prompt-only, **Llama 3.1 70B (basic) + DeepSeek R1 Llama-distilled 70B (reasoning)**, 3 Panelist+Interpreter pipelines, max_attempts=3, 3 runs averaged | Xu, Wang, Briand, Liu; **TOSEM 2026** | DOI 10.1145/3803418 · arXiv:2506.02943 | **A** |
| CANDOR | line / branch / mutation | **0.990 / 0.949 / 0.939** (574/611) | Leetcode-Medium (50 sampled programs) | same | same | same | **A** |
| CANDOR | line / branch / mutation | **0.989 / 0.980 / 0.937** (805/859) | Leetcode-Hard (50 sampled programs) | same | same | same | **A** |
| LLM-Empirical (SOTA prompt baseline) | line / branch / mutation | **0.885 / 0.930 / 0.910** | HumanEvalJava | prompt-engineering, Codex/GPT-3.5 (reported from original paper) | Siddiq et al. 2024, **via CANDOR** | arXiv:2506.02943 Table 1 | **A** (as reported) |
| EvoSuite | line / branch / mutation | **0.961 / 0.942 / 0.858** | HumanEvalJava | SBST, regression oracles | Fraser & Arcuri, **via CANDOR** | same | **A** (as reported) |
| CANDOR | oracle correctness | **0.971 / 0.993 / 0.961** | HumanEvalJava / LeetCode-Med / LeetCode-Hard | correct source code | Xu et al. 2026 | same §5.2 | **A** |
| CANDOR | oracle correctness (faulty code via PiTest mutants) | **0.942 / 0.977 / 0.952** | same | mutated source | same | same | **A** |
| CANDOR | oracle-correctness margin over LLM-Empirical | **+0.158 … +0.251** (correct code); **+0.168 … +0.186** (faulty code) | same | Wilcoxon p<0.05, A₁₂=0.875 / 0.960 | same | same | **A** |
| CANDOR (TOSEM version) | oracle correctness vs TOGLL | **≥ +21.1 percentage points** | HumanEvalJava + LeetCodeJava | vs fine-tuning-based TOGLL | same, **TOSEM abstract** | DOI 10.1145/3803418 | **A** |
| CANDOR ablation | Δ from removing Planner | **line −0.099, branch −0.130, mutation −0.111** | same | ablation | same | same | **A** |
| CANDOR ablation | Δ from removing panel discussion | **oracle correctness −0.158** | same | ablation | same | same | **A** |
| **AdverTest** | fault detection rate | **+8.56% over best existing LLM-based methods; +50.20% over EvoSuite**; competitive line/branch | **Defects4J** | adversarial two-agent loop (test-gen agent T ↔ mutant-gen agent M), guided by coverage + mutation score | Chang, Fang, Chen, Shi, Shen, Gu; **PACMSE vol. 3, ISSTA issue, pp. 710–733, 2026** | DOI 10.1145/3832122 | **A** |
| **MUTGEN** | mutation score | outperforms EvoSuite and vanilla prompting (exact deltas **NOT VERIFIED** — abstract only) | **204 subjects from two benchmarks** | mutation-guided prompts + iterative generation | Wang, Xu, Briand, Liu; **TSE 2026** | DOI 10.1109/tse.2026.3682975 | **A** |
| MUTGEN (motivating finding) | coverage-vs-mutation gap | **some test suites reach 100% line coverage but only 4% mutation score** | — | reported finding | same | same | **A** |
| **IntTestGen** | Δ line / Δ branch / Δ mutation | **+19.99 / +24.90 / +13.67 pp** (Defects4J) · **+22.69 / +15.78 / +0.17 pp** (Deps4J) | **Defects4J + Deps4J** (new post-cutoff Java repos) | LLM + context enrichment + constraint-enforced fixing; vs **PANTA** (LLM) and **EvoSuite** | Xu, Wang, Briand, Guo, Liu; 2026 | arXiv:2605.26851 | **B** |
| IntTestGen | extra dependency lines covered | **378 (Defects4J) / 55 (Deps4J)** | same | — | same | same | **B** |
| **SCATE** | Δ line / Δ branch over agent-only baseline | **+32.3% / +30.9% (Gemini CLI)** · **+6.0% / +5.9% (Claude Code)** | **120 complex classes across 14 Defects4J projects** (WMC ≥ 35 or RFC ≥ 55; median 416.5 LOC / 68.0 WMC / 80.5 RFC) | contextual-bandit supervisor over coding agents; relative improvements | Gu, Nashid, Mesbah (UBC); 2026 | arXiv:2607.08983 | **B** |
| **TestGen-LLM (Meta)** | build / pass / coverage-improving | **75% built · 57% passed reliably · 25% increased coverage** | Meta Reels & Stories (Instagram), **Kotlin** | deployed tool; filtered generation, human review | Alshahwan et al.; **FSE 2024 Industry** | DOI 10.1145/3663529.3663839 · arXiv:2402.09171 | **A** |
| TestGen-LLM (Meta) | deployment outcome | **improved 11.5% of all classes applied to; 73% of recommendations accepted into production** | Meta Instagram + Facebook test-a-thons | industrial deployment | same | same | **A** |
| **Spec-driven test generation** (Google) | Δ bug detection / Δ branch coverage | **+9.8 pp (p = 0.0352) / +2.5 pp (p = 0.0034)** | **production bugs from Google** (n not stated in abstract) | agent prompted to first write pre/post-conditions/undefined behaviours; vs traditional test-gen agent baseline | Tufano, McClure, Cambronero, Cheng, Shi, Wei, Chen, Ivancic, Dalloro, Rondon (Google); **SpecOps '26 workshop** | DOI 10.1145/3842652.3843195 | **B** |
| Spec-driven test generation | LLM-as-judge superiority | **superior to baseline in 77.8% of cases; superior to human-authored tests in 56.7%** | same | LLM-as-a-Judge | same | same | **B** |

### 2.4 Multi-agent framing — what each paper actually claims

| System | Claim direction | Metric | Value | Baseline | Benchmark | Conditions | Venue | Grade |
|---|---|---|---|---|---|---|---|---|
| **AgentCoder** | **POSITIVE** multi-agent | test line coverage (HumanEval / MBPP) | **multi 87.5% / 89.5% vs single 72.5% / 75.9%** → **+15.0 / +13.6 pp** | single agent doing code+tests | HumanEval, MBPP (function-level, canonical solutions) | GPT-3.5-turbo, 5 refinement iterations | arXiv:2312.13010 Tables 5, 8 | **B** |
| AgentCoder | POSITIVE | test line coverage | **AgentCoder(GPT-4) 91.7% / 92.3% vs MetaGPT(GPT-4) 81.7% / 80.5%** | MetaGPT | same | GPT-4 | same Table 5 | **B** |
| AgentCoder | POSITIVE | test-case accuracy | **multi 87.8% / 89.9% vs single 61.0% / 51.8%** | single agent | same | GPT-3.5 / GPT-4 | same Table 6 | **B** |
| AgentCoder | POSITIVE | end-to-end pass@1 | **multi 79.9 / 77.4 / 89.9 / 89.1 vs single 71.3 / 61.6 / 79.4 / 59.1** | single agent | HumanEval / HE-ET / MBPP / MBPP-ET | GPT-3.5-turbo | same Table 7 | **B** |
| **MUATC** | **POSITIVE** multi-agent | coverage vs CoverUp | **+4.8% – +5.5%** | CoverUp | "benchmark dataset" (not further specified in the abstract) | multi-agent + CoT + RAG + MTCRA repair; gains claimed independent of model family and language | Ma, Liu, Dong, Liu, Zhang; **APSEC 2025** | **A** |
| MUATC | POSITIVE | coverage | **+12.7%** on ChatUniTest's benchmark dataset | ChatUniTest, TestPilot, CoverUp | ChatUniTest dataset | same | same | **A** |
| MUATC | POSITIVE | readability | significantly more readable than Pynguin | Pynguin | HumanEval-platform readability study | same | same | **A** |
| **CANDOR** | **POSITIVE** multi-agent | line coverage | **0.991 vs 0.885** (LLM-Empirical) | single-prompt baseline | HumanEvalJava | Llama 3.1 70B + DeepSeek R1 70B | TOSEM 2026 | **A** |
| **Konstantinou et al.** | **NEGATIVE** for engineered orchestration | line / branch / mutation | **Plain-LLM 49.95 / 35.33 / 33.82 vs HITS 42.43/29.49/27.97, SymPrompt 40.95/27.19/28.40, CoverUp 38.85/25.11/26.26, TestSpark 23.65/16.48/13.88** | 4 SOTA engineered tools | 6 Java repos, 393 classes, 3,657 methods | same newer LLMs injected into every tool; Mann-Whitney U, p<0.05 | **ICST 2026** | **A** |
| **ASTA 2026 (Arnaudo, Coppola, Morisio et al.)** | **MIXED** — coverage positive, ESR null, cost 3–4× | coverage / ESR | multi-agent coverage **peaks 99.75%**; ESR **97.31% multi vs 97.25% single**; **3–4× token cost** | single-agent | **HumanEval**, black-box testing | rule-augmented few-shot prompting is the main driver (+20–30% coverage & ESR over zero-shot/few-shot) | **ICST 2026 ASTA workshop** | **B** |
| Plain-LLM granularity | — | line / branch / mutation | class-level 33.53/21.05/22.08 → method-level 49.95/35.33/33.82 | — | 393 Java classes | 3 LLMs | ICST 2026 | **A** |

### 2.5 Benchmark-construction and leakage papers

| Benchmark | Size / scope | Key finding | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|
| **ULT (UnLeakedTestbench)** | **3,909 function-level Python tasks**; avg cyclomatic complexity 14.87 (all ≥ 10) | **LLM avg over 12 models: accuracy 41.32%, statement coverage 45.10%, branch coverage 30.22%, mutation score 40.21%** | Huang, Zhang, Harman, Zhang, Du, Ng; **TOSEM 2026** | DOI 10.1145/3805043 · arXiv:2508.00408 | **A** |
| **PLT (PreLeakedTestbench)** | **18,169 tasks** (ULT ⊂ PLT, plus leaked functions) | **47.07% / 55.13% / 40.07% / 50.80%** — leakage inflates branch coverage most | same | same | **A** |
| **TestEval** (control) | 210 LeetCode-style Python programs | **91.79% / 92.18% / 82.04% / 49.69%** | same | same | **A** |
| ULT leakage finding | correlation between code-gen and test-gen Pass@1 | **ULT ρ = 0.79 (p = 0.002) vs TestEval 0.56 (p = 0.059) vs PLT 0.52 (p = 0.080)** | same | same | **A** |
| ULT per-model (best) | Pass@1 | **17.83% (gemma-3-27b-it and Qwen2.5-Coder-32B-Instruct); Qwen2.5-Coder-14B 15.32%** on ULT vs **68–78% on TestEval** | same | same | **A** |
| ULT eval protocol | — | function-level, **K-query iterative** (round 1 = FUT only; round *i* = FUT + all prior tests, asked for a *distinct* test); **greedy temp 0.0**, max 1024 new tokens | same | same | **A** |
| ULT mutation protocol | — | **Cosmic-Ray**, all mutants per function, timeout = 120 s; mutant killed if suite fails on mutated code and passes on original | same | same | **A** |
| **SWE-Mutation** | **2,636 mutated variants from 800 original instances**; multilingual subset: **9 languages** (C, C++, Java, TypeScript, JavaScript, Rust, Go, PHP, Ruby) | **DeepSeek-V3.1: Pass@1 88.20%, VRR 10.20%, RDR 36.15%** (Mini-Swe-Agent, test *generation*); best: Claude-sonnet-4.5 + Claude Code **98.00 / 40.40 / 71.71** | Sun, Zhao, Wang, Du, Ma, Wang, Zhang, Zhang, Huang; **Findings of ACL 2026, pp. 39651–39674** | DOI 10.18653/v1/2026.findings-acl.1976 · arXiv:2605.22175 | **A** |
| SWE-Mutation | agentic-mutation realism effect | **average detection rate drops 71.04% → 39.81%** when moving from conventional to agentic mutants | same | same | **A** |
| SWE-Mutation | comparison table | TestGenEval = "File / Python / ✗ agentic loop / Rule-based mutation"; SWT-bench = "Repository / Python / ✓ / None" | same | same Table 1 | **A** |
| **SWT-Bench** | **1,762 instances** (per TestGenEval's comparison table) | Code agents designed for repair exceed systems designed for test generation; generated tests double SWE-Agent's patch precision | Mündler, Müller, He, Vechev; 2024; **NeurIPS 2024 D&B** | arXiv:2406.12952 | **A** |
| **TAM-Eval** | **1,539 scenarios** (Python, Java, Go), test-file level, full-repo context | "state-of-the-art LLMs have limited capabilities in realistic test maintenance" and yield "only marginal improvements in test effectiveness"; metrics: pass rate, coverage, mutation | 2026 | arXiv (TAM-Eval) · github.com/trndcenter/TAM-Eval | **B** |
| **Multi-SWT-Bench** | **1,963 instances, 8 languages** (Python, Java, TypeScript, JavaScript, Go, Rust, C, C++) | systematic language gap: Python success > aggregate; C++ worst; methods: MSWE-agent, MOpenHands, Codex, Claude Code | 2026 | arXiv:2609.34752 | **B** |
| **XREPOTEST** | Rust, Go, Julia, PHP, Ruby; 14 LLMs incl. Claude 4.5, GPT-5.2, DeepSeek V4-Pro | large standalone-vs-repository gap; new **Invocation Rate (IR)** metric | 2026 | arXiv:2608.25939 | **B** |
| **TEBench** | **314 instances from 10 Defects4J projects** | project-level *test evolution*; 7 agent configs converge on identification **F1 45.7–49.4%**; Test-Stale averages **F1 ≈ 36%** | 2026 | arXiv:2605.06125 | **B** |

### 2.6 Test oracle / assertion generation

| System | Metric | Value | Benchmark / dataset | Conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **Tratto** | accuracy / precision / F1 | **73% / 72% / 61%** | ground-truth dataset of axiomatic oracles over Java projects (Javadoc-derived) | neuro-symbolic, **fine-tuned Code Llama 7B** + symbolic token-space restriction | Molinelli, Martin-Lopez, Zackrone, Eken, Ernst, Pezzè; **ISSTA 2025, pp. 1887–1909** | DOI 10.1145/3728960 · arXiv:2504.04251 | **A** |
| Tratto | recall | **52%** (vs GPT-4 89%, Jdoctor 16%) | same | — | same | same | **A** |
| **Jdoctor** (symbolic SOTA) | accuracy / precision / F1 / recall | **61% / 62% / 25% / 16%** | same | pattern/lexical/semantic matching | Blasi et al. 2018, **via Tratto** | same | **A** (as reported) |
| **GPT-4** (few-shot + CoT) | accuracy / precision / F1 / recall | **40% / 24% / 37% / 89%** | same | few-shot + chain-of-thought | OpenAI, **via Tratto** | same | **A** (as reported) |
| Tratto | oracles generated / false positives | **3× more than Jdoctor; 10× fewer FPs than GPT-4** | same | — | same | same | **A** |
| Tratto | robustness to doc variations | **195/220 correct (89%)** vs GPT-4 **208/220 (95%)**, Jdoctor **49/220 (22%)** | 55 original descriptions × 4 variation types (synonyms/order/typos/explicitness) | — | same Table 3 | same | **A** |
| Tratto | Δ mutation score on EvoSuite suites | **implicit oracles: 25% → 32%** (Jdoctor 26%); **implicit+regression: 55% → 56%** (Jdoctor 55%) | 6 projects (commons-cli, commons-codec, commons-compress, commons-csv, gson, joda-time) | oracles appended to EvoSuite-generated tests | same Table 4 | same | **A** |
| GPT-4 | non-compilable oracles | **552 of 1,213 (45.5%)** — could not be auto-inserted | same | — | same §5 | same | **A** |
| **CANDOR** | oracle correctness | **0.971 / 0.993 / 0.961** | HumanEvalJava / LeetCode-Med / LeetCode-Hard | multi-agent panel discussion + consensus | Xu et al.; TOSEM 2026 | DOI 10.1145/3803418 | **A** |
| **RESTOR** | assertion generation | exact numbers **NOT VERIFIED** (abstract only) | RESTful APIs, single request-response pair, black-box | fine-tuned lightweight LLM via GRPO | 2026; **PACMSE** | DOI 10.1145/3832185 | **A** (numbers unverified) |

---

## 3. Per-system detail paragraphs (evaluation conditions)

### 3.1 TestGenEval — the benchmark AITester should adopt (Python, file-level, real repos)

TestGenEval is built by adapting SWE-bench docker images: filename-heuristic pairing of code and test files, installation of coverage and mutation dependencies, filtering of tests that take > 60 s, and validation that gold tests cover some of the code under test. It comprises **68,647 tests from 1,210 code–test file pairs across 11 well-maintained Python repositories**. Two tasks exist: **full-file test generation** (given the file under test, generate a whole suite) and **test completion** (first / last / extra test given an existing suite).

Metrics: **pass@1** comes in two flavours — *all pass@1* (the entire generated suite passes) and *any pass@1* (at least one generated test passes); **coverage** is the share of lines in the code under test executed by *passing* tests only (failing tests are excluded from coverage); **mutation score** is the share of synthetic bugs (Cosmic-Ray, default operator set) detected, where a mutant counts as killed only if the suite passes on the original code and fails on the mutated code. All figures in the paper are at **temperature 0.2**, single-shot, with the maximum context window each model supports.

The headline result stands: **the best single-shot model, GPT-4o, reaches only 35.2% coverage and 18.8% mutation**, and models add **less than 1% coverage** when asked to generate the final test of an almost-complete suite. This is the paper's own framing of the difficulty: models "struggle to reason about execution" and produce "frequent assertion errors when addressing complex code paths."

### 3.2 TestForge — the verifiable agentic frontier on TestGenEval

TestForge reframes test generation as an **iterative, file-level** agentic process: it starts from a zero-shot suite (GPT-4o) and then refines it using execution feedback (compile/runtime/assertion errors) *and* the full set of uncovered lines from a `coverage` report. It runs in an OpenHands/CodeAct-style loop with navigate/write/edit/view/bash tools, caps at **25 iterations** (or an explicit `exit`), and averages **447 s per data point at $0.63 per file** — $762 for the whole benchmark.

Results (GPT-4o, full 1,210 programs): **pass@1 84.3%, line coverage 44.4%, mutation score 33.8%**. Its own zero-shot GPT-4o baseline under the same prompt gets **64.0% / 34.8% / 18.4%**, i.e. agentic iteration buys **+9.6 pp coverage and +15.0 pp mutation**. On the 45-program Python-3.10 subset (the only programs where Pynguin and CodaMosa run), TestForge reaches **100% / 60.0% / 31.6%** versus Pynguin **60% / 24.0% / 4.2%** and CodaMosa **62.2% / 30.2% / 2.7%**.

**Critical caveat for benchmarking:** TestForge **could not compare against CoverUp** on TestGenEval. The published reason is cost — CoverUp operates at the method level, costing ≈ **$2 per data point** in TestGenEval, i.e. ≈ $2,400 for the full benchmark, which the authors state was "out of our price range." Consequently **no single paper contains head-to-head TestForge-vs-CoverUp numbers on TestGenEval.** Any claim of the form "X beats CoverUp on TestGenEval" must be separately reproduced. TestForge is currently an **arXiv preprint + CMU S3D tech report (CMU-S3D-25-100)**, not a peer-reviewed venue paper — grade B.

### 3.3 CoverUp — FSE 2025, but on a different benchmark

CoverUp (Pizzorno & Berger, **PACMSE vol. 2, FSE 2025**, DOI 10.1145/3729398) uses SlipCover to measure coverage, segments the file by AST into units that lack coverage, prompts GPT-4o per segment with the uncovered line/branch numbers, offers a `get_info` tool function for extra context, and **continues the chat** (up to two extra prompts by default) when tests fail to compile, fail, or fail to raise coverage. It also performs an integration check and flaky-test handling, and can be re-run to refocus on missed segments.

Benchmarks: **CM** (425 Python modules, ≈100,000 LOC, from 35 BugsInPy/Pynguin projects where Pynguin plateaus), **PY** (84 modules, ≈5,000 LOC, where Pynguin already does well), and **MT** (163 HumanEval-derived functions, ≈2,000 LOC, from MuTAP's evaluation). On CM, CoverUp achieves **63.8% line / 49.2% branch / 60.3% line+branch overall** and **82.4% / 66.7% / 79.6% median per-module**, versus CodaMosa's 48.7% / 55.1% (overall L+B / median L+B). An ablated LLM-only CoverUp gets **34.0% / 38.5%** — a **~26 pp overall L+B gap**, which is CoverUp's core claim. Cost on CM: **$399 / 4.0 h / 28,690 prompts**, ~18× faster than CodaMosa (71 h) at 48% more tokens.

**Read the numbers carefully:** these are **coverage of the target module achieved by generated regression tests** measured with SlipCover, on suites where only *coverage-increasing* tests are accepted. They are **not** comparable to TestGenEval's coverage (which excludes failing tests and uses whole SWE-bench files averaging ~10k tokens) and they are **not** TestGenEval numbers.

### 3.4 ULT / UnLeakedTestbench — the contamination reality check

ULT (Huang, Zhang, Harman, Zhang, Du, Ng; **TOSEM 2026**, DOI 10.1145/3805043; arXiv:2508.00408) is built from **The Stack v2** with three filters: **cyclomatic complexity ≥ 10** (retained functions average 14.87), **self-containment** (no dependence on non-standard user-defined code), **testability guarantee** (≥3 executable inputs, GPT-4o-assisted debug up to 3 attempts), and finally **decontamination** — function names searched for `def test_<name>` / `assert <name>` in The Stack v2. Functions with no matching test form **ULT (3,909 tasks)**; the superset including leaked functions is **PLT (18,169 tasks)**, giving a controlled memorisation-vs-reasoning contrast.

Evaluation is **function-level, K-query**, with a distinctive protocol: round 1 gives only the FUT and asks for one test; round *i* gives the FUT plus all previously generated tests and asks for a **new, distinct** test. Decoding is **greedy (temperature 0.0)**, max **1,024 new tokens**, 12 models from CodeLlama-7B to Qwen2.5-Coder-32B. Mutation uses **Cosmic-Ray** over all mutants per function with a **120 s timeout**.

Averages over all 12 LLMs:

| Benchmark | Accuracy (Pass@k) | Statement cov. | Branch cov. | Mutation score |
|---|---|---|---|---|
| **ULT** (decontaminated) | **41.32%** | **45.10%** | **30.22%** | **40.21%** |
| **TestEval** (contaminated, easy) | **91.79%** | **92.18%** | **82.04%** | **49.69%** |
| **PLT** (leaked) | **47.07%** | **55.13%** | **40.07%** | **50.80%** |

**Leakage finding, stated precisely:** the gap between PLT and ULT is **+5.75 pp accuracy, +10.03 pp statement coverage, +9.85 pp branch coverage, +10.59 pp mutation score** — i.e. **branch coverage is the metric most inflated by contamination**, and **PLT's mutation score (50.80%) actually exceeds TestEval's (49.69%)**, showing that mutation score is not immune to leakage either. The paper's own summary is that ULT "shows a strong correlation between test generation performance and code generation performance" (ρ = 0.79, p = 0.002 on ULT vs 0.56/0.52 on TestEval/PLT), which they interpret as evidence that ULT measures generalisation rather than memorisation. Best single model on ULT is only **17.83% Pass@1** (gemma-3-27b-it and Qwen2.5-Coder-32B-Instruct), against 68–78% on TestEval.

**Important scoping note:** ULT is **function-level, self-contained, stdlib/third-party-only** code — deliberately *not* repository- or file-level. It is therefore a **complement** to TestGenEval, not a substitute: ULT controls for leakage and complexity, TestGenEval controls for realism and scale.

### 3.5 Multi-agent test generation — a genuinely split 2026 literature

This is the area where the task brief's framing needs correcting.

**Positive multi-agent results.**

- **AgentCoder** (Huang, Zhang, Luck, Bu, Qing, Cui; arXiv:2312.13010) has three agents — *programmer*, *test designer*, *test executor* — where the test designer deliberately generates tests **without seeing the generated code** to avoid bias. It is primarily a **code-generation** framework whose test component is instrumental. Its coverage table (Table 5) is on the **canonical solutions** of HumanEval/MBPP, not on real repositories: GPT-3.5-turbo 70.2/61.3, CodeCoT 77.2/82.9, AgentCoder (GPT-3.5) 87.5/89.5, MetaGPT (GPT-4) 81.7/80.5, AgentCoder (GPT-4) 91.7/92.3. Its **single-vs-multi ablation (Table 8)** is the source of the widely-quoted "13–15%" figure: **single agent 72.5% / 75.9% vs multi-agent 87.5% / 89.5% line coverage = +15.0 / +13.6 pp**. So the claim is real *in magnitude* but it is **not** "coverage gain on a real benchmark vs a single-agent test generator"; it is AgentCoder's own multi-vs-single ablation on **function-level HumanEval/MBPP canonical solutions**. The paper's claim direction is unambiguously **positive** for multi-agent.
- **MUATC** (Ma, Liu, Dong, Liu, Zhang; **APSEC 2025**, DOI 10.1109/APSEC66846.2025.00028) is the strongest explicitly-coverage-driven multi-agent test generator: multi-agent collaboration + **Chain-of-Thought + RAG** + a repair algorithm **MTCRA**. Claims: **+4.8% to +5.5% coverage over CoverUp**, gains "independent of model architecture and programming languages", and **+12.7% test coverage on ChatUniTest's benchmark dataset** against ChatUniTest/TestPilot/CoverUp. Readability beats Pynguin. **Caveat: these are abstract-level numbers only.** The paper is paywalled on IEEE Xplore and computer.org; the per-system table, the exact benchmark, and the model used are **NOT VERIFIED**.
- **CANDOR** (Xu, Wang, Briand, Liu; **TOSEM 2026**, DOI 10.1145/3803418) is an end-to-end Java JUnit framework with *Initializer*, *Planner*, *Tester*, *Inspector*, *Requirement Engineer*, multiple *Panelist+Interpreter* dual-LLM pipelines and a *Curator*. It runs on **Llama 3.1 70B (basic LLM) + DeepSeek R1 Llama-distilled 70B (reasoning LLM)**, `max_attempts = 3`, **3 Panelist+Interpreter pipelines**, 3 repeated runs with Wilcoxon signed-rank tests. Results: line/branch/mutation **0.991/0.970/0.980** on HumanEvalJava (160 programs), **0.990/0.949/0.939** on 50 LeetCode-Medium, **0.989/0.980/0.937** on 50 LeetCode-Hard; oracle correctness **0.971/0.993/0.961**. Every headline claim is **multi-agent beating baselines**.
- **TestAgent** (Shang, Zhang, Zhan, Huang, Fang, Chen; **FSE Companion 2026**, DOI 10.1145/3803437.3806428; arXiv:2607.09101) is currently the strongest Java number found: three agents (requirement **Planner**, **Generator**, **Reviewer**) over a repository-level **Code Knowledge Graph**, evaluated on **1,451 methods across 6 Java projects**, reaching **97.46% execution rate, 92.34% line coverage, 90.24% branch coverage, 83.69% mutation score**, plus **154 detected real bugs at 92.22% precision**.

**Negative / null results for hand-engineered orchestration.**

- **Konstantinou, Degiovanni & Papadakis — ICST 2026 Research Papers** (arXiv:2601.09695) is the decisive paper. They **replicated four SOTA engineered tools** (HITS, SymPrompt, TestSpark, CoverUp), injected **newer LLMs** (gpt-4o-mini, Llama 3.3 70B, DeepSeek V3) into all of them, and compared against **Plain-LLM** — a single generation prompt plus **at most 5 uniform repair iterations**, temperature 0.1, with only minimal parsing (package/import/class-name alignment). Dataset: **6 complete Java repositories, 393 classes, 3,657 methods** — the largest dataset in Java LLM test-generation studies to date, with half the projects post-cutoff (after 2023-10-01) to control contamination. Result totals (line / branch / mutation): **Plain-LLM(method) 49.95 / 35.33 / 33.82** > HITS 42.43/29.49/27.97 > SymPrompt 40.95/27.19/28.40 > **CoverUp 38.85/25.11/26.26** > TestSpark 23.65/16.48/13.88. Plain-LLM also needed **fewer LLM requests than CoverUp (11,718 vs 12,264) and far fewer than HITS (23,865)**. Their stated conclusion: *"LLM-based test generation methods have comparable test effectiveness (in fact, Plain-LLM is slightly superior) with Plain-LLM"* and *"with new, relatively strong LLMs, test generation methods provide a limited or no advantage to the generation process."* They also note ~**20% of generated tests do not compile** and ~**43% do not pass**.
- **ASTA 2026 at ICST** (Arnaudo, Coppola, Morisio, Giobergia, Nguyen, Chen, Mai, Ji, Ma — Politecnico di Torino) is a **more nuanced** result than is often quoted. On **HumanEval** black-box testing: multi-agent architectures achieve the **highest coverage (peaking at 99.75%)**, but their **Execution Success Rate is essentially identical to single-agent (97.31% vs 97.25%)**, at **3–4× the token cost**. The paper's actual conclusion is that **prompt engineering is the primary driver** — Rule-augmented Few-shot prompting yields **+20–30% in both coverage and ESR** over zero-shot/conventional few-shot — and that a single agent with optimised rule-augmented few-shot prompting gives the **best accuracy/coverage/cost balance**. This is a **cost-effectiveness** verdict, not a blanket "single beats multi".

**Bottom line on the direction of the evidence:** the credible 2026 negative result targets **hand-engineered, tool-specific orchestration** (HITS/SymPrompt/TestSpark/CoverUp-style pipelines) versus a **plain strong-LLM prompt with a uniform repair loop** — not multi-agent collaboration per se. Meanwhile CANDOR, MUATC, TestAgent and AgentCoder all report multi-agent wins, and ASTA finds multi-agent wins on coverage but not on execution success at 3–4× cost.

### 3.6 The "CANDOR ICST 2026" claim in the AITester README — **NOT VERIFIED, and the evidence contradicts it**

The AITester README (`README.en.md`, 2026-10-09 entry) states:

> "one-shot prompting beats hand-designed multi-agent orchestration (CANDOR, ICST 2026 [to verify]: one-shot Gemini 88.35% vs CANDOR 35.92%, 45s vs 50h)"

**Verification result: this cannot be confirmed from any source, and the pieces that *are* verifiable point the other way.**

1. **No CANDOR paper exists in the ICST 2026 program.** I fetched the full ICST 2026 Research Papers track listing and searched the whole page for "CANDOR" — **zero hits**. The ICST 2026 "LLM-Assisted Test Generation" session (Mon 18 May 2026, Room 101) contains: *Consistency Meets Verification: Enhancing Test Generation Quality in LLMs Without Ground-Truth Solutions* (Taherkhani, Daghighfarsoodeh, Chowdhury, Pham, Hemmati — York), *How well LLM-based test generation techniques perform with newer LLM versions?* (Konstantinou, Degiovanni, Papadakis), *Improving Automated Patch Correctness Assessment by Designing LLM-Based Oracles* (Jang, Kim), and *Developer vs. DSpot vs. ChatGPT: A Comparative Study of JUnit Test Amplification* (Owuor, Jha). No CANDOR.
2. **The real CANDOR is TOSEM 2026, not ICST 2026.** "Hallucination to Consensus: Multi-Agent LLMs for End-to-End JUnit Test Generation" — Xu, Wang, Briand, Liu — **ACM TOSEM**, DOI **10.1145/3803418** (arXiv:2506.02943). Its reported results are **positive for multi-agent**: CANDOR reaches **line coverage 0.991 / 0.990 / 0.989** and **mutation score 0.980 / 0.939 / 0.937** on HumanEvalJava / LeetCode-Medium / LeetCode-Hard, and **oracle correctness 0.971 / 0.993 / 0.961**, beating the prompt-based SOTA baseline LLM-Empirical and EvoSuite. There is **no 35.92% figure anywhere in the paper** for CANDOR.
3. **The "88.35%" is suspiciously close to a number CANDOR beats.** In CANDOR's Table 1, the *baseline* **LLM-Empirical achieves line coverage 0.885** on HumanEvalJava. The claimed "one-shot Gemini 88.35%" therefore looks like a **rounded/garbled inversion of the baseline that CANDOR outperforms (0.991 > 0.885)**, relabelled as a Gemini result. CANDOR is not evaluated with Gemini at all — it uses Llama 3.1 70B and DeepSeek R1 Llama-distilled 70B.
4. **"45s vs 50h" is unattested.** CANDOR's paper does not report a 45-second figure, a 50-hour figure, or any wall-clock comparison of that shape. Targeted searches for `"88.35"` + test generation, `"35.92"` + CANDOR, and `CANDOR 50 hours` returned **no matching source**.

**Recommendation to the parent agent: remove or explicitly retract this citation from `README.en.md` and `README.md`.** The defensible 2026 citation for the same design point is **Konstantinou, Degiovanni & Papadakis, ICST 2026** (arXiv:2601.09695), which *is* peer-reviewed at ICST 2026, *is* in the same session as the other test-generation papers, and *does* support "a plain LLM approach beats engineered tooling" — with numbers I verified line-by-line from the paper's own Table II.

Separately, the README's other "[to verify]" citation, **BOAD (ICLR 2026)**, **is real**: "BOAD: Discovering Hierarchical Software Engineering Agents via Bandit Optimization", arXiv:2512.23631 (IBM Research; v1 2025-12-29, v2 2026-01-01), which formulates hierarchy discovery as a multi-armed bandit problem. **But it is about repository-level SWE issue resolution (localization/editing/validation sub-agents), not test generation** — so it supports "discovered orchestration can beat monolithic agents *on SWE tasks*", not any claim about test generation.

### 3.7 Mutation score and fault detection as the stricter bar

The 2026 literature converges on the position that **coverage is a weak proxy and mutation score is the metric that matters**. Two data points make this concrete: **MUTGEN** (Wang, Xu, Briand, Liu; **TSE 2026**, DOI 10.1109/tse.2026.3682975) reports test suites that reach **100% line coverage with only a 4% mutation score**, and evaluates on **204 subjects from two benchmarks**, beating EvoSuite and vanilla prompting by injecting mutation feedback into the prompt with an iterative generation mechanism. **AdverTest** (Chang, Fang, Chen, Shi, Shen, Gu; **PACMSE vol. 3, ISSTA issue, pp. 710–733, 2026**, DOI 10.1145/3832122) pairs a test-generation agent with a **mutant-generation agent** that specifically hunts the blind spots of the current suite, guided jointly by coverage and mutation score, improving **fault detection by 8.56% over the best existing LLM methods and 50.20% over EvoSuite on Defects4J** while staying competitive on line/branch coverage.

At the repository level, **SWE-Mutation** (Findings of ACL 2026) reframes evaluation: instead of asking "do the tests pass?", it injects **agentically-generated complex mutants that try to fool the suite** and measures **VRR (Verification Rate — does the generated suite accept a *correct* solution)** and **RDR (Relative Detection Rate — how many mutants does it catch)**. Best result on the test-generation task is Claude-sonnet-4.5 with Claude Code: **Pass@1 98.00%, VRR 40.40%, RDR 71.71%**; DeepSeek-V3.1 with Mini-Swe-Agent gets **88.20% / 10.20% / 36.15%**. The headline caution is that **swapping conventional rule-based mutants for agentic mutants drops the average detection rate from 71.04% to 39.81%** — i.e. **roughly 44% of measured "fault detection" under weak mutants is illusory**.

For oracle quality specifically, the reference numbers are **Tratto's 73% accuracy / 72% precision / 61% F1** (ISSTA 2025) against **GPT-4 few-shot+CoT at 40% accuracy but 89% recall and 552/1,213 (45.5%) non-compilable oracles** — a precision/recall trade-off that makes **precision and false-positive count the operative metrics** for oracle work, not accuracy alone. Tratto's own downstream effect is modest: appending its oracles to EvoSuite suites moves mutation score from **25% → 32%** (implicit oracles only) and **55% → 56%** (implicit + regression oracles) across 6 projects.

---

## 4. Candidate SOTA numbers AITester must beat, with the exact benchmark protocol

The AITester README's own primary metrics are the **M1 triple** (`detection_rate` / `repair_rate` / `false_fix_rate`) on an internal 261-task / 3-seed pooled caliber: **detection `plain_llm_df` 44.8% > `aitester` 15.8% > `plain_llm` 1.5%** (aitester −28 pp vs `plain_llm_df`), **corrected repair 39.31%** (57/145 replayable), **corrected false_fix 87.2%**, **$0.0259 vs $0.0045 per task**. Because those are internal, non-comparable numbers, the externally defensible bars to beat are:

### Tier 1 — must-beat bars on a public, adoptable protocol

| # | Bar | Exact protocol | Source |
|---|---|---|---|
| **B1** | **TestGenEval full, 1,210 programs: pass@1 ≥ 84.3%, line coverage ≥ 44.4%, mutation score ≥ 33.8%** | Full-file test generation; GPT-4o-class model; agentic loop ≤ 25 iterations; coverage over **passing tests only**; mutation via **Cosmic-Ray** default operators; report all three together | TestForge, arXiv:2503.14713 Table 1 |
| **B2** | **Beat the single-shot floor convincingly: GPT-4o 0-shot on TestGenEval full = 64.0% pass@1 / 34.8% coverage / 18.4% mutation** | Same benchmark, temperature 0.2, TestGenEval's own prompt | TestGenEval, arXiv:2410.00752 Table 2 + TestForge Table 1 |
| **B3** | **TestGenEval-Lite (160 file pairs): branch-coverage improvement over greedy selection** — CovQValue reports **+51–77% relative** branch coverage and wins on **77–84% of targets** | TestGenEval Lite, iterative generation, greedy-vs-Q-value planner | CovQValue, arXiv:2604.05159 |
| **B4** | **Cost ceiling: ≤ $0.63 per file on TestGenEval full** (TestForge); CoverUp's method-level approach costs ≈ **$2/file** — a $/coverage-point efficiency claim must be stated at one of these anchors | Same as B1 | TestForge §5 / §4.2 |

### Tier 2 — must-beat bars if AITester adopts a leakage-controlled Python protocol

| # | Bar | Exact protocol | Source |
|---|---|---|---|
| **B5** | **ULT (3,909 function-level Python tasks): beat the 12-model average of accuracy 41.32% / statement coverage 45.10% / branch coverage 30.22% / mutation score 40.21%** — and **beat the best single model's 17.83% Pass@1** | Function-level, K-query iterative (round *i* gets FUT + all prior tests, must be distinct); **greedy temp 0.0**; ≤1,024 new tokens; **Cosmic-Ray** with 120 s timeout; cyclomatic complexity ≥ 10 | ULT, TOSEM 2026, DOI 10.1145/3805043 / arXiv:2508.00408 |
| **B6** | **Demonstrate the number is not leakage-inflated:** report the same system's ULT vs PLT delta and show it is smaller than PLT−ULT = **+5.75 pp accuracy / +10.03 pp statement / +9.85 pp branch / +10.59 pp mutation** | Same protocol on both splits | same |
| **B7** | **Guard against the trivial-benchmark illusion:** any contamination-sensitive claim must be accompanied by the TestEval comparison (accuracy 91.79%, statement 92.18%, branch 82.04%, mutation 49.69%) to show the system is not riding an easy benchmark | TestEval, 210 LeetCode-style programs | same |

### Tier 3 — must-beat bars for detection/fault-finding claims (AITester's actual thesis)

| # | Bar | Exact protocol | Source |
|---|---|---|---|
| **B8** | **Mutation-score honesty bar:** any coverage claim must be paired with mutation score, because **100% coverage co-occurs with 4% mutation score** in published suites; MUTGEN's bar is "beat EvoSuite and vanilla prompting on mutation score over 204 subjects from two benchmarks" | 204 subjects, two benchmarks, mutation-guided prompting + iterative generation | MUTGEN, TSE 2026, DOI 10.1109/tse.2026.3682975 |
| **B9** | **Adversarial-mutant bar (repository level): +8.56% fault detection over the best existing LLM-based method and +50.20% over EvoSuite on Defects4J**, while remaining competitive on line/branch coverage | Defects4J; adversarial test-gen ↔ mutant-gen loop guided by coverage **and** mutation score | AdverTest, PACMSE vol. 3 (ISSTA), DOI 10.1145/3832122 |
| **B10** | **Strong-mutant bar: use agentic mutants, not rule-based ones.** With weak (conventional) mutants the average detection rate is **71.04%**; with agentic mutants it is **39.81%**. AITester's `detection_rate` must be reported against agentic mutants to be credible | SWE-Mutation protocol: 2,636 mutated variants / 800 original instances / 9 languages; report **VRR** and **RDR** alongside Pass@1 | SWE-Mutation, Findings of ACL 2026, DOI 10.18653/v1/2026.findings-acl.1976 |
| **B11** | **If a Java/large-scale comparison is wanted: TestAgent's 97.46% execution / 92.34% line / 90.24% branch / 83.69% mutation on 1,451 methods across 6 Java projects**; or **IntTestGen's +19.99 pp line / +24.90 pp branch / +13.67 pp mutation over PANTA+EvoSuite on Defects4J** | TestAgent: repository-level, 3 agents + Code Knowledge Graph. IntTestGen: low-level integration tests against PANTA and EvoSuite | TestAgent FSE Companion 2026 / arXiv:2607.09101; IntTestGen arXiv:2605.26851 |

### Tier 4 — the protocol-integrity bars

| # | Bar | Why it matters for AITester | Source |
|---|---|---|---|
| **B12** | **Report compile rate and pass rate explicitly.** The ICST 2026 replication measures **≈20% non-compiling and ≈43% non-passing** generated tests across every tool studied. AITester's `success` metric ("generated tests pass on the final code") must never be quoted alone — consistent with the project's own rule | Cross-tool invariant | Konstantinou et al., ICST 2026 |
| **B13** | **Budget-match every multi-agent claim.** The defensible negative result is that a plain LLM prompt with ≤5 uniform repair iterations matches or beats engineered pipelines **at comparable or lower request cost** (Plain-LLM 11,718 requests vs CoverUp 12,264 vs HITS 23,865). ASTA 2026 shows multi-agent wins coverage (99.75%) but ties on ESR (97.31% vs 97.25%) at **3–4× tokens** | Directly supports the project's ADR-0016 "budget-matched positive detection delta" promotion criterion | Konstantinou et al. ICST 2026; Arnaudo et al. ICST 2026 ASTA |
| **B14** | **Do not cite a "45 s vs 50 h" or "88.35% vs 35.92%" CANDOR result.** Unverifiable; contradicted by the actual TOSEM 2026 CANDOR paper, where the multi-agent system reaches **0.991 line coverage** and the baseline it beats sits at **0.885** | Citation integrity | see §3.6 |

---

## 5. Sources (all fetched during this review)

**Benchmarks & leaderboard-style papers**
- TestGenEval — Jain, Synnaeve, Rozière — ICLR 2025: https://arxiv.org/abs/2410.00752 · https://arxiv.org/html/2410.00752v2 · https://proceedings.iclr.cc/paper_files/paper/2025/hash/26ded5c8ee8ec1bc4caced4e1c9b1584-Abstract-Conference.html · slides https://ICLR.cc/media/iclr-2025/Slides/30800.pdf
- TestForge — Jain & Le Goues, 2025: https://arxiv.org/abs/2503.14713 · https://ar5iv.labs.arxiv.org/html/2503.14713 · CMU S3D tech report: http://reports-archive.adm.cs.cmu.edu/anon/anon/usr/ftp/usr/ftp/home/ftp/s3d2025/CMU-S3D-25-100.pdf
- ULT / UnLeakedTestbench — TOSEM 2026, DOI 10.1145/3805043: https://arxiv.org/abs/2508.00408 · https://ar5iv.labs.arxiv.org/html/2508.00408 · https://dl.acm.org/doi/abs/10.1145/3805043 · code https://github.com/huangd1999/UnLeakedTestBench
- SWT-Bench — NeurIPS 2024 D&B: https://arxiv.org/abs/2406.12952
- Multi-SWT-Bench, 2026: https://arxiv.org/abs/2609.34752
- XREPOTEST, 2026: https://arxiv.org/abs/2608.25939
- TEBench, 2026: https://arxiv.org/abs/2605.06125
- TAM-Eval, 2026: https://github.com/trndcenter/TAM-Eval
- SWE-Mutation — Findings of ACL 2026, pp. 39651–39674: https://aclanthology.org/2026.findings-acl.1976/ · PDF https://aclanthology.org/2026.findings-acl.1976.pdf · DOI https://doi.org/10.18653/v1/2026.findings-acl.1976 · arXiv:2605.22175
- TestGenEval-related coverage-comparison benchmark: "Benchmarking LLMs for Unit Test Generation from Real-World Functions" TOSEM DOI 10.1145/3805043 (same as ULT)

**Python test generation systems**
- CoverUp — FSE 2025 / PACMSE vol. 2, DOI 10.1145/3729398: https://arxiv.org/abs/2403.16218 · https://arxiv.org/html/2403.16218v4 · https://dl.acm.org/doi/full/10.1145/3729398 · FSE 2025 listing https://conf.researchr.org/details/fse-2025/fse-2025-research-papers/112/CoverUp-Effective-High-Coverage-Test-Generation-for-Python
- CovQValue / "Planning to Explore" — 2026: https://arxiv.org/abs/2604.05159
- Spec-driven test generation (Google) — SpecOps '26, DOI 10.1145/3842652.3843195: https://doi.org/10.1145/3842652.3843195

**JVM systems**
- Konstantinou, Degiovanni, Papadakis — ICST 2026: https://arxiv.org/abs/2601.09695 · https://ar5iv.labs.arxiv.org/html/2601.09695 · ICST 2026 listing https://conf.researchr.org/details/icst-2026/icst-2026-research/22/How-well-LLM-based-test-generation-techniques-perform-with-newer-LLM-versions-
- CANDOR — TOSEM 2026, DOI 10.1145/3803418: https://arxiv.org/abs/2506.02943 · https://ar5iv.labs.arxiv.org/html/2506.02943 · https://dlnext.acm.org/doi/10.1145/3803418
- TestAgent — FSE Companion 2026, DOI 10.1145/3803437.3806428: https://arxiv.org/abs/2607.09101 · https://dl.acm.org/doi/pdf/10.1145/3803437.3806428 · code https://github.com/iSEngLab/TestAgent-VSCode-Extension
- MUATC — APSEC 2025, DOI 10.1109/APSEC66846.2025.00028: https://www.computer.org/csdl/proceedings-article/apsec/2025/665300a184/2emQP5zcBXO · https://xplorestaging.ieee.org/document/11396580
- AdverTest — PACMSE vol. 3 (ISSTA), pp. 710–733, 2026, DOI 10.1145/3832122: https://doi.org/10.1145/3832122
- MUTGEN — TSE 2026, DOI 10.1109/tse.2026.3682975: https://doi.org/10.1109/tse.2026.3682975
- IntTestGen — 2026: https://arxiv.org/abs/2605.26851
- SCATE — 2026: https://arxiv.org/abs/2607.08983
- TestGen-LLM (Meta) — FSE 2024 Industry, DOI 10.1145/3663529.3663839: https://arxiv.org/abs/2402.09171 · https://discovery.ucl.ac.uk/id/eprint/10199775/
- AgentCoder — arXiv:2312.13010: https://ar5iv.labs.arxiv.org/html/2312.13010
- ASTA 2026 / ICST 2026 — Arnaudo, Coppola, Morisio et al.: https://conf.researchr.org/details/icst-2026/asta-2026-papers/3/Automated-Black-Box-Testing-A-Comparative-Study-of-LLM-Agent-Architectures-and-Promp

**Oracle generation**
- Tratto — ISSTA 2025, pp. 1887–1909, DOI 10.1145/3728960: https://homes.cs.washington.edu/~mernst/pubs/axiomatic-oracles-issta2025-abstract.html · PDF https://homes.cs.washington.edu/~mernst/pubs/axiomatic-oracles-issta2025.pdf · https://arxiv.org/abs/2504.04251 · https://dl.acm.org/doi/10.1145/3728960
- RESTOR — PACMSE 2026, DOI 10.1145/3832185: https://doi.org/10.1145/3832185

**Surveys / venues / metadata**
- "Enhancing Automated Unit Test Generation with Large Language Models: A Systematic Literature Review" TOSEM 35(9), 2026, DOI 10.1145/3802827 (116 papers: 69 venue papers across 25 venues + 47 preprints)
- ICST 2026 Research Papers program: https://conf.researchr.org/track/icst-2026/icst-2026-research
- BOAD — arXiv:2512.23631 (IBM Research; hierarchy discovery via multi-armed bandits): https://arxiv.org/abs/2512.23631 · https://research.ibm.com/publications/boad-discovering-hierarchical-software-engineering-agents-via-bandit-optimization
- Crossref REST API (`api.crossref.org/works/<DOI>`) and OpenAlex (`api.openalex.org/works?search=`) used to resolve every DOI, venue, author list and year recorded above.
- Secondary/unreliable source encountered and **flagged**: https://quantumzeitgeist.com/percent-models-llm-test-generation-achieves-coverage/ (grade **C**). Its headline "**20.92% coverage**" mis-states the source paper: 20.92% is the **mutation-score improvement** of Plain-LLM over SOTA in Konstantinou et al., not a coverage value. Its quoted coverage figures (49.95/35.33/33.82, 53.67/38.74/36.55, 52.30/38.84/36.76) do match the primary source.

---

## 6. Open questions and things I could NOT verify

1. **"CANDOR, ICST 2026: one-shot Gemini 88.35% vs CANDOR 35.92%, 45s vs 50h" — NOT VERIFIED. I believe this citation is erroneous and should be retracted.** Evidence: (a) "CANDOR" does not appear anywhere in the fetched ICST 2026 Research Papers program; (b) the real CANDOR is TOSEM 2026 (DOI 10.1145/3803418) and reports the **opposite** direction (multi-agent line coverage 0.991 vs baseline 0.885); (c) 88.35% ≈ the baseline LLM-Empirical's 0.885 line coverage in CANDOR's own Table 1, which CANDOR beats; (d) CANDOR never uses Gemini; (e) targeted searches for `"88.35"` and `"35.92"` in a test-generation context, and for a `45 s`/`50 h` CANDOR cost comparison, returned **no source at all**. I did **not** find any *other* paper named CANDOR at any venue reporting those numbers.
2. **MUATC's per-system table is NOT VERIFIED.** Only the abstract is publicly reachable (IEEE Xplore and computer.org are paywalled/403). Verified from the abstract: **+4.8%–5.5% coverage over CoverUp**, **+12.7% coverage on ChatUniTest's dataset**. **Not verified:** which dataset the 4.8–5.5% figure refers to, its absolute baseline, the LLM used, and the number of modules/classes evaluated.
3. **MUTGEN's exact per-system numbers are NOT VERIFIED.** TSE 2026 abstract only; the "100% coverage / 4% mutation" example is quoted from the abstract without stating which subject it came from.
4. **RESTOR's numbers are NOT VERIFIED** (PACMSE 2026, DOI 10.1145/3832185) — abstract only, no values extractable.
5. **No 2026 system reporting full-TestGenEval numbers above TestForge's was found.** Searches for 2026 TestGenEval results returned only TestForge, the CovQValue paper (TestGenEval **Lite**, branch-coverage deltas only), and SWE-Mutation's benchmark-comparison table (which lists TestGenEval as "File / Python / Rule-based mutation"). **I could not locate an official, actively maintained TestGenEval leaderboard** — no such page surfaced. The best available "leaderboard" is TestForge's Table 1 plus the original TestGenEval Table 2.
6. **Source conflict inside TestGenEval itself:** arXiv v1 states code files average **1,157 LOC** and test files **943 LOC**; v2 states **782 LOC** and **677 LOC**. Both are from the same authors; v2 is later. I report both rather than picking one. Note that TestForge's paper (written against v1) repeats the 1,157/943 figures.
7. **Minor internal inconsistency in TestForge's cost accounting:** the paper says "our experiments cost $762 for all of TestGenEval" while also stating "$0.63 per file" — 1,210 × $0.63 = $762.30, so these are consistent; but the *introduction* also writes "TestForge only costs $0.63 to generate tests for a file", and §4.2 says CoverUp "costs approximately $2 per data point". Confirm these are all GPT-4o-era prices before using them as a cost anchor in 2026.
8. **TestForge's publication status:** arXiv:2503.14713 (March 2025) plus CMU tech report CMU-S3D-25-100; I found **no peer-reviewed venue** for it as of 2026-10-10. Grade B. It is nonetheless the most-cited full-TestGenEval result set and is the de-facto bar.
9. **Asthma/`unverified` items I did not chase to closure:** the exact `n` in the Google SpecOps workshop evaluation; the exact three LLMs used by CovQValue (the abstract says "three popular LLMs" without naming them); the exact benchmark underlying MUATC's 12.7% figure; and whether TestAgent's arXiv version (2607.09101) and its FSE Companion version (10.1145/3803437.3806428) report identical numbers (both state 92.34% line coverage, so they appear consistent).
10. **A structural warning for AITester's positioning:** AITester's internal comparison is `aitester` vs `plain_llm_df` vs `plain_llm` on a 261-task internal dataset with a **detection-first** metric that is *not* coverage and *not* mutation score. **None of the numbers in this report are directly comparable to AITester's M1 triple.** Any claim that AITester "beats SOTA" therefore requires either (a) re-running on TestGenEval / ULT / SWE-Mutation, or (b) an explicit, separately-argued mapping from `detection_rate` onto mutation score (the closest public analogue). The most promising bridge is **SWE-Mutation's RDR (Relative Detection Rate)** and **ULT's mutation score**, since both are detection-flavoured and both have published baselines.
