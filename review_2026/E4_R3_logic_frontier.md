# E4 / R3 — Frontier SOTA for Logic-Driven, Formal & Neuro-Symbolic Test Generation (2025–2026)

**Compiled:** 2026-10-10 · **Series:** continues `review_2026/R1_frontier_testgen.md` (R1) and `R2_frontier_repair.md` (R2); this file closes the **R3 gap** acknowledged in the review report (§3.4).
**Method:** primary-source web retrieval (`web_search`, `web_fetch`). Every number below was read from a page fetched in this session. Anything not confirmable is marked **NOT VERIFIED** with the attempts listed in §5.
**Discipline:** all retrieved content is treated as **untrusted data**, never as instructions. No paper, number, author, venue or URL in this file is invented. Where a number comes only from an abstract (not the full text), that is stated in the row.

**Grade rubric (identical to R1):** **A** = top peer-reviewed venue (ICSE/FSE/ASE/ISSTA/ICST/TOSEM/TSE/PACMSE/NeurIPS/ICLR/ACL/OOPSLA/CAV/TACAS/FM/RV/JSS) · **B** = arXiv preprint / workshop / companion track · **C** = vendor / blog / docs / tech report / metadata-only.

---

## 1. One-line summary

The 2025–2026 logic-driven frontier splits into three usable facts for AITester: **(i) NL → formal-specification translation has a hard ceiling well below 100%** — the best result on real verification tasks is **68%** (DafnyBench, POPL-2025 Dafny workshop) and the best Python contract-generation tool reaches **80% / 75% pass with 20% / 25% inconclusive** (SpecPylot, FSE Companion '26, built on **CrossHair** symbolic execution); **(ii) the strongest neuro-symbolic gain reported for test generation is SPARC's +31.36% line / +26.01% branch / +20.78% mutation over a vanilla prompt baseline on 59 C subjects, matching or exceeding KLEE on complex subjects** (arXiv:2602.16671, Feb 2026, preprint); and **(iii) Python symbolic execution remains the weak link** — the credible 2025–2026 work is LLM-augmented (LLM-Sym → Z3; LLM-guided concolic testing), not a native Python KLEE. Temporal-logic (LTL/CTL) generation is clearly active in 2026 but its quantitative results could **not** be verified from primary sources in this environment (see §5).

---

## 2. Data points

### 2.1 NL → formal specification translation (autoformalization / contracts)

| System | Metric | Value | Benchmark / dataset (size) | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **DafnyBench** (benchmark) | dataset size | **750+ Dafny programs, ≈53,000 LOC** | DafnyBench | programs require auto-generated annotations to verify | Loughridge, Sun, Ahrenbach, Cassano, Sun, Sheng, Mudide, Misu, Amin, Tegmark; **Dafny 2025 @ POPL 2025** | [popl25.sigplan.org/details/dafny-2025-papers/15](https://popl25.sigplan.org/details/dafny-2025-papers/15/DafnyBench-A-Benchmark-for-Formal-Software-Verification) | **B** |
| **DafnyBench** | best success rate (LLM auto-annotation) | **68%** | DafnyBench (750+ programs) | "best model and prompting scheme"; GPT-4 / Claude 3 tested; retrying with **error-message feedback** improves the rate; deteriorates with required code+annotation volume | same | same | **B** |
| **SpecPylot** | pass rate / inconclusive rate | **80% (16/20) pass, 20% (4/20) inconclusive** | 20 Python programs (16 randomly selected SpecGenBench programs translated Java→Python + 4 sequential programs; 5 control-flow types) | **Claude Sonnet 4.5**; icontract annotations checked by **CrossHair**; Apple M4 / 24 GB; refinement budget configurable | Ayon & Ahmed; **FSE Companion '26**; arXiv 2026-04-17 | [arXiv:2604.16560](https://arxiv.org/abs/2604.16560) · DOI [10.1145/3803437.3806427](https://doi.org/10.1145/3803437.3806427) | **B** |
| **SpecPylot** | pass rate / inconclusive rate | **75% (15/20) pass, 25% (5/20) inconclusive** | same 20 programs | **GPT-4o**; same pipeline | same | same | **B** |
| **SpecPylot** | avg paths explored in INCONCLUSIVE cases | **91.5 CONFIRMED / 11.2 UNKNOWN** (Sonnet) vs **42.0 / 4.8** (GPT-4o) | same 20 programs | "bounded symbolic exploration"; INCONCLUSIVE cases were add_loop, binary_search, mysqrt, digit_root (both models) + calculator (GPT-4o) | same | same | **B** |
| **SpecPylot** | cost & token use | **5,480 tokens/issue** (Sonnet) / **4,756** (GPT-4o); **$1.09** / **$0.80** total for 20 programs; **1.02 refinement iterations** avg | same 20 programs | end-to-end incl. contract generation, refinement, CrossHair analysis | same | same | **B** |
| **SpecPylot** (limitation, explicit) | — | **PASSED ≠ proof**: "only means that no counterexample was found within the chosen exploration limits"; results degrade with deep loops/complex branching; quality depends on type precision | same | author-stated limitations | same | same | **B** |
| **SpecGen** (as cited by SpecPylot §2) | JML spec generation | **no numbers verified** | SpecGenBench (Java) | few-shot prompting + mutation-based heuristics; JML checked by a verifier | Ma et al. 2025, **as cited in** SpecPylot §2 | via arXiv:2604.16560 §2 | **C** (as cited) |
| **FormalBench** (as cited by SpecPylot §2) | robustness/consistency of LLM specs | **no numbers verified** | — | evaluation rather than generation | Le-Cong et al. 2025, **as cited** | via arXiv:2604.16560 §2 | **C** (as cited) |
| **AutoReSpec** (Java/JML) | multi-LLM + verifier feedback | **no numbers verified** | — | Java + JML; "combining multiple LLMs with verifier feedback to improve robustness" | Ayon & Ahmed; **FORGE '26** | DOI [10.1145/3793655.3793731](https://doi.org/10.1145/3793655.3793731) (as cited in SpecPylot §2) | **C** (metadata + as-cited) |

> **Reading:** the two independent numbers (68% Dafny, 80%/75% Python) agree on the order of magnitude: **specification generation is a ~70–80% activity at best, on small, curated benchmarks**. This is the empirical basis for AITester treating "spec not injected / spec compile failed" as an abstention condition rather than as a rare error path.

### 2.2 Contract / property-based testing for Python

| System | Metric | Value | Benchmark / dataset (size) | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **CrossHair** (via SpecPylot) | verification outcome taxonomy | **PASSED / REFUTED / INCONCLUSIVE**; 20–25% of programs land INCONCLUSIVE on 20-program benchmark | 20 Python programs | bounded symbolic execution; per-condition / per-path / overall timeouts configurable; `crosshair check` on icontract annotations | Schanely (tool); evaluation in SpecPylot (FSE Companion '26) | [arXiv:2604.16560](https://arxiv.org/abs/2604.16560) | **B** |
| **CrossHair** (via SpecPylot) | counterexample-driven repair loop | refinement triggered only on **REFUTED**; **1.02** iterations avg; refinements overlapped on only 2 of 20 programs | 20 Python programs | contracts revised, program left untouched | same | same | **B** |
| **Hypothesis / icontract / deal** | any 2025–2026 measured data | **NOT VERIFIED** — no primary-source quantitative study found (see §5) | — | — | — | — | — |
| *("Property-Based Testing for LLM Outputs…")* | — | **EXCLUDED — low credibility**, see §4 | — | — | Ivchenko (Zenodo preprint, 2026-07-05) | [zenodo.org/records/21198691](https://zenodo.org/records/21198691) | **C−** |

### 2.3 SMT / symbolic execution + LLM hybrids

| System | Metric | Value | Benchmark / dataset (size) | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **SPARC** | line / branch / mutation gain **vs vanilla prompt baseline** | **+31.36% line, +26.01% branch, +20.78% mutation** | **59 real-world and algorithmic C subjects** | 4-stage neuro-symbolic: CFG analysis → Operation Map → path-targeted test synthesis → iterative self-correction with compiler/runtime feedback; **matches or exceeds KLEE on complex subjects**; retains **94.3%** of tests through iterative repair | Chowdhury, Fu, Jabbarvand; arXiv 2026-02-18 | [arXiv:2602.16671](https://arxiv.org/abs/2602.16671) | **B** |
| **ESBMC-AI** | qualitative (no rate in abstract) | evaluated on **50,000 C programs** randomly selected from the **FormAI** dataset with vulnerability classifications; automates detection+repair of buffer overflow, arithmetic overflow, pointer dereference | FormAI (50,000 C programs) | BMC finds vulnerability + counterexample → prompt = source + stack trace + counterexample (line number, error type) → LLM fixes → **BMC re-verifies** | Tihanyi, Charalambous, Jain, Ferrag, Cordeiro; **AST 2025 @ ICSE 2025** | [conf.researchr.org AST 2025](https://conf.researchr.org/details/ast-2025/ast-2025-papers/1/A-New-Era-in-Software-Security-Towards-Self-Healing-Software-via-Large-Language-Mode) · DOI [10.1109/AST66626.2025.00020](https://doi.org/10.1109/AST66626.2025.00020) | **B** |
| **LLM-Sym** | qualitative | LLM agent translates complex Python path constraints into **Z3** code; "capable of solving path constraints on Leetcode problems with complicated control flows and **list** data structures, which is **impossible for the backbone symbolic execution engine**" | Leetcode-style problems | multi-step pipeline: type inference → retrieval → self-refine; backbone engine is an introductory-level Python symbolic executor | Wang, Liu, Chen, Li, Jin, Huang, Ma; 2024 | [arXiv:2409.09271](https://arxiv.org/abs/2409.09271) | **B** |
| **Hybrid Concolic Testing with LLMs** | qualitative | "significantly outperforms traditional concolic testing, random testing, and genetic algorithm-based methods in terms of **branch coverage, path coverage, and time-to-coverage**" (no numbers in abstract) | synthetic + real-world Fintech applications | LLM guides path exploration, prioritises paths, assists constraint solving | Eslamimehr; arXiv 2026-01-18 | [arXiv:2601.12274](https://arxiv.org/abs/2601.12274) | **B** |
| **SymLLM**, **ChatTCG** | any primary source | **NOT VERIFIED** — no primary paper located (see §5) | — | — | — | — | — |

### 2.4 Temporal-logic (LTL/CTL/MTL) monitoring & test generation, 2026

| System | Metric | Value | Benchmark / dataset | Evaluation conditions | Authors, year, venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| *Automated LTL Specification Generation from Industrial Aerospace Requirements* | LTL-generation accuracy | **NOT VERIFIED** | industrial aerospace requirements | Springer chapter; page not retrievable (see §5) | **Formal Methods 2026** (Springer LNCS) | DOI [10.1007/978-3-032-26220-2_33](https://doi.org/10.1007/978-3-032-26220-2_33) | **C** (metadata only) |
| *Automatic translation of natural language requirements into CTL specifications using LLMs: a multi-approach evaluation* | CTL-translation agreement/accuracy | **NOT VERIFIED** | NL requirements (size unknown) | "multi-approach evaluation" | **Journal of Systems and Software 2026** | DOI [10.1016/j.jss.2026.112941](https://doi.org/10.1016/j.jss.2026.112941) | **C** (metadata only) |
| *Cross-Model Evaluation of LLMs for Generating Formal Specification of Distributed Industrial Control Systems* | cross-model spec quality | **NOT VERIFIED** | distributed industrial control systems | Procedia CS (open access) | 2025 | [ScienceDirect S1877050925033861](https://www.sciencedirect.com/science/article/pii/S1877050925033861) | **C** (metadata only) |

> **Honest assessment:** this direction is **the weakest part of R3**. Two 2026 venues (FM, JSS) demonstrably publish on LLM→temporal-logic translation, so the direction is live, but **every quantitative result I located was behind a fetch failure** (403 / auth redirect / PDF-only). Do **not** cite any LTL/CTL accuracy number from this file — there are none.

### 2.5 Python symbolic execution — 2026 status

| Question | Finding | Evidence | Grade |
|---|---|---|---|
| Is there a native Python KLEE? | **No such system verified in this session.** The credible Python-side work is LLM-augmented: LLM-Sym (LLM→Z3 constraint translation), LLM-guided concolic testing, and CrossHair (bounded, contract-driven, via SpecPylot) | §2.2, §2.3 rows | **B** |
| Practical ceiling of Python symbolic execution | Bounded search returns **INCONCLUSIVE** on loop-heavy/multi-path programs (20–25% of a 20-program benchmark); author-explicit "PASSED is not a proof" | SpecPylot §4.1/§6 | **B** |
| PyEx / Nagini / Pynguin / Z3 concolic engines — 2025–2026 measured data | **NOT VERIFIED** — no primary-source 2025–2026 evaluation located in this session | §5 | — |
| *Agentic Concolic Execution* (IEEE Xplore doc 11573412) | **NOT VERIFIED** — surfaced in search only; IEEE page not fetched | §5 | — |

### 2.6 For completeness: the directly-relevant benchmark (owned by the ULT bridge plan, not a logic-driven system)

| System | Metric | Value | Benchmark | Conditions | Venue | URL / DOI | Grade |
|---|---|---|---|---|---|---|---|
| **ULT / UnLeakedTestbench** | 4 metrics, 12-model mean | **41.32 / 45.10 / 30.22 / 40.21** (acc / stmt / branch / mutation); PLT **47.07 / 55.13 / 40.07 / 50.80**; TestEval **91.79 / 92.18 / 82.04 / 49.69** | 3,909 leaked-free function-level Python tasks (cyclomatic ≥10, mean 14.87) + PLT pair | K-query iteration, greedy temp 0.0, ≤1,024 new tokens/round, cosmic-ray + 120 s; best single model **Pass@1 17.83%** | **TOSEM 2026** | DOI [10.1145/3805043](https://doi.org/10.1145/3805043) · [arXiv:2508.00408](https://arxiv.org/abs/2508.00408) | **A** (venue) / B (numbers from abstract) |

> Full bridging analysis, licence verification and execution plan live in [`docs/design/ult_bridge_plan.md`](../docs/design/ult_bridge_plan.md).

---

## 3. What this means for AITester (actionable, cross-referenced)

1. **`spec_compile_rate` is not an implementation bug — it is the frontier norm.** 68% (DafnyBench) and 75–80% (SpecPylot) bound what any spec channel can achieve. → Treat "spec compile failed / logic channel not injected" as an **abstention trigger** (see `docs/design/abstain_validate_design.md` §3.1 **L0**), not as an error to be silently retried.
2. **CrossHair-style verification must model `unknown` explicitly.** The three-valued outcome (PASSED / REFUTED / INCONCLUSIVE) is the correct contract; collapsing INCONCLUSIVE into PASS is what makes "verified" patches untrustworthy. → Abstain/validate design §4.2: `unknown ≠ deny`, conservative pass-through.
3. **SPARC gives the direction of the gain, not a transferable number.** +31.36/+26.01/+20.78 is C-only, over a *vanilla prompt* baseline, on 59 subjects, preprint. → usable as motivation for a neuro-symbolic channel, **never** as a target for the Python pipeline.
4. **BMC-as-oracle loops exist and are peer-reviewed (ESBMC-AI, AST 2025)** — counterexample + stack trace → LLM fix → re-verify. This is architecturally the same shape as AITester's "gold adjudication" loop and is the closest published precedent for a *verification-gated* patch queue.
5. **The `mutation` metric is the least leak-robust and the least saturated** (TestEval 49.69 vs ULT 40.21 — an 9.5 pp gap, while accuracy collapses 91.79 → 41.32). → When adding ULT-style reporting, report all four metrics; a coverage-only or accuracy-only story will not survive review.
6. **Do not build on the "PBT for LLMs" literature yet** — the one item found is not credible (§4).

---

## 4. Excluded as low credibility (documented so it is not re-imported)

| Item | Why excluded |
|---|---|
| *Property-Based Testing for LLM Outputs: Hypothesis Strategies for Non-Deterministic AI* (Ivchenko, Zenodo record 21198691, "published" 2026-07-05, CC-BY-4.0) | Unrefereed Zenodo "preprint" (19.4 kB, 9 views, 3 downloads). Internal evidence of non-rigour: the citation block prints a **placeholder DOI** (`10.5281/zenodo.1234567`); the reference list is explicitly **illustrative** ("generated automatically from inline anchors … for illustration") with items `[2]`, `[4‑7]` unexpanded; the claims ("87% vs 54% failure detection", "5,000 test cases per model", "12 invariants") are unreproducible; the prototype is built on `fast-check` (a **JavaScript** library) while the title promises Hypothesis (Python) strategies. **Numbers from this record must not be cited.** |

---

## 5. NOT VERIFIED register (with what was attempted)

| Target | Status | Attempts made |
|---|---|---|
| **Clover** (closed-loop verifiable code generation, Dafny) — any quantitative result | **NOT VERIFIED** | `web_search` ×3 with title/author phrasing; only PDF at `wisdom.weizmann.ac.il/~padon/clover-saiv2024.pdf` was indexed → `web_fetch` rejects `application/pdf`; no arXiv abs page found |
| **LTL aerospace requirements** (FM 2026) numbers | **NOT VERIFIED** | `link.springer.com/chapter/10.1007/978-3-032-26220-2_33` → cross-origin redirect to `idp.springer.com` (auth wall); `dl.acm.org/doi/abs/10.1007/…` → **HTTP 403** (Cloudflare) |
| **CTL from NL requirements** (JSS 2026) numbers | **NOT VERIFIED** | `dl.acm.org/doi/10.1016/j.jss.2026.112941` → **403**; `https://doi.org/10.1016/j.jss.2026.112941` → cross-origin redirect to `linkinghub.elsevier.com`; `sciencedirect.com` direct → **403** |
| **SymLLM**, **ChatTCG** primary sources | **NOT VERIFIED** | 2 search rounds with exact-name queries; only unrelated vendor/doc pages returned |
| **Agentic Concolic Execution** (IEEE doc 11573412) | **NOT VERIFIED** | Search-index hit only; IEEE Xplore page not fetched in this session |
| **Hypothesis / icontract / deal** 2025–2026 measured data | **NOT VERIFIED** | 3 search rounds; only the excluded Zenodo record and unrelated pages returned |
| **PyEx / Nagini / Pynguin** 2025–2026 evaluations | **NOT VERIFIED** | 2 search rounds; no 2025–2026 primary evaluation surfaced |
| **ESBMC survey** (arXiv:2605.26169) contents | **NOT VERIFIED** | Indexed only as `export.arxiv.org/pdf/...` → PDF unsupported |
| **ULT / PLT** in-paper tables (per-model breakdown, K value, timeout details) | **NOT VERIFIED** | UCL AAM PDF (`discovery.ucl.ac.uk/…/3805043.pdf`) → `application/pdf` unsupported; arXiv abs + UCL landing abstract cross-checked and consistent, but body tables unread |
| **Abstain-and-Validate** §6.2/§6.3 tables (the `+39 pp` configuration) | **Partially verified** | arXiv **v2 full-text HTML was fetched** (intro numbers 0.11 → 0.21 / 0.29 / 0.35 / 0.53, 174 bugs, 20 trajectories, Gemini 2.5 Pro / 2.0 Flash, greedy); fetch truncated at §6.1 → **RQ3 table unread**; abstract's 13/15/39 pp is **not consistent** with the intro's +10/+18/+24/+42 pp. See `docs/design/abstain_validate_design.md` §2.2 for the verification plan |

### Environment limitations encountered (for reproducibility of this retrieval)

- `web_fetch` cannot parse **PDF** (`unsupported content type "application/pdf"`) → all PDF-only sources are unreachable.
- `github.com`, `raw.githubusercontent.com`, `huggingface.co` resolve to **non-public IPs** in this sandbox and are refused; `hf-mirror.com` **does** work (used for dataset/licence metadata), and `cdn.jsdelivr.net` redirects to the blocked `raw.githubusercontent.com`.
- `dl.acm.org` returned **HTTP 403** (Cloudflare interstitial) on every attempt; `link.springer.com` redirects to an auth IdP.
- `export.arxiv.org/api/query` was unreachable (`fetch failed`); `arxiv.org/abs/*` and `arxiv.org/html/*` work, and the HTML **truncates** long papers mid-body.
- `doi.org` links that redirect off-origin are not followed.

---

## 6. Relationship to R1 / R2 (no duplication)

- **R1** covers LLM/multi-agent unit & integration test generation (TestGenEval, TestForge, CoverUp, MuTAP, JVM systems, ICST 2026 negative result). **This file does not repeat those rows**; where R1 and R3 touch the same system (e.g. coverage/mutation baselines), R1 remains authoritative.
- **R2** covers frontier program-repair work; the A&V (ICSE-SEIP 2026) row that R2-adjacent review used is **re-verified here** (§5 last row) with an explicit uncertainty statement.
- **R3 (this file)** is scoped to: spec translation, contracts/property testing, SMT/symbolic+LLM hybrids, temporal logic, and Python symbolic execution.

---

## 7. Strongest three data points (for the reviewer's shortlist)

1. **DafnyBench — 68% best success on 750+ programs / ≈53,000 LOC** (Loughridge et al., **Dafny 2025 @ POPL 2025**; [program page](https://popl25.sigplan.org/details/dafny-2025-papers/15/DafnyBench-A-Benchmark-for-Formal-Software-Verification)) — **Grade B**. The single most citable number for "spec translation is not solved".
2. **SpecPylot — 80% (Claude Sonnet 4.5) / 75% (GPT-4o) pass with 20% / 25% inconclusive, on 20 Python programs verified by CrossHair; PASSED explicitly ≠ proof** (Ayon & Ahmed, **FSE Companion '26**; [arXiv:2604.16560](https://arxiv.org/abs/2604.16560)) — **Grade B**. The only Python-side, contract+solver, costed data point found.
3. **SPARC — +31.36% line / +26.01% branch / +20.78% mutation vs vanilla prompt, on 59 C subjects, matching/exceeding KLEE on complex subjects, 94.3% test retention** (Chowdhury, Fu, Jabbarvand; [arXiv:2602.16671](https://arxiv.org/abs/2602.16671), 2026-02) — **Grade B** (preprint, C-only, vanilla baseline). Strongest *neuro-symbolic test-generation* gain located; not transferable to Python.
