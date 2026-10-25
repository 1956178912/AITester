> **Language**: [中文版](README.md) | English (this document)
>
> **Current version 1.0.0** (2026-10-25): the measurement-surface close-out release — published after every criterion in `docs/adr/0036-v1-release-criteria.md` group A (measurement frontier, 7 items) and group C (release mechanics, 5 items) was closed: the paper audit gains a read-side check that a declared number must exist in the artifact it points at (Appendix E's cost table was re-pointed from a live artifact that does not contain those numbers to a historical label plus table W-1 in the withdrawal index; A/B: wrong pointer rc=1, fixed rc=0), replication integrity moved from "zero files checked still green" to four states (8 directories / 401 files verified, 5 absent disclosed, a missing manifest is red), the paper now discloses three mandatory limitations (53/261 fixed-material gap, synthetic-generator drift, scale87 replace ≠ SpecExpr), and README / MODEL_CARD / REPLICATION match the repository. Gate and test readings live in `BASELINE.yaml`; round details in `CHANGELOG.en.md` [1.0.0].
>
> Last updated: 2026-10-26 (**CU round: a document-command executability gate (landing the CS round's lesson) + cover-letter/body frontier synchronisation** --- (1) turning "the document points at a non-existent artefact" into an executable criterion: new gate `scripts/gates/check_doc_commands.py` (in the blocking CI chain, 9 new cases) --- every `scripts/....py` path in the documentation must exist and every `make <target>` must be a real Makefile target; the criterion **pins two classes of false positive** (English prose such as "make the same direction" is not a command; a `> ` blockquote is not a shell prompt) ｜ (2) the first full census (39 documents, 124 references) found **zero** breakages --- a negative result no artifact had recorded before; now every commit re-runs it ｜ (3) `paper/cover_letter.tex` still said "Three independent studies... reach the same direction" while the body cites **nine** frontier papers (including two independent formalisations and one **submitted to the same venue**) ⇒ replaced with an accurate statement matching the body (three primary works cited by arXiv id only, no new numbers), and the contribution located as "not the direction but the resolution and the unit of analysis" and "we measure *declared* repairs" ｜ (4) the new gate moves seven census numbers by +1, and the self-check notes "on disk 33 / index 32, one untracked => CI's clone will not have these" --- **writing a gate is not the same as CI enforcing it**; Previously **CT round: an abstract three words from the submission limit + stale word/page counts in the submission files + a criterion whose caliber must be explicit** --- (1) a genuine submission-blocking risk: both submission files claimed "236 words" against the journal's 150-250 limit; under the strict reading (hyphenated compounds split) the abstract measured **247 words, three words of headroom** --- a different tokeniser rejects it ⇒ compressed to **225 / 240** (redundancy only, number set identical item by item) with the **dual-caliber limit** now a criterion (strict > 250 red; headroom < 5 disclosed) ｜ (2) `paper/title_page.tex` was stale on both counts ("236 words", "54 pages" vs 225 words / 55 pages in the `xdv` log), and the CS round's submission-package criterion **only inspected `SUBMISSION.md`, not the title page a reviewer reads first** ⇒ the criterion now covers the title page and the package's word count; 5 new cases, four mutants red ｜ (3) a criterion whose caliber is unspoken gets counted differently by everyone: two computations of the same abstract gave 231 and 244 because the **`% SRC:` provenance comment inside the abstract block** was counted as prose (29 extra words) ⇒ the caliber is now stated in the criterion and pinned by tests ｜ (4) two first impressions overturned and recorded as such: the chromadb CVEs are **not "running bare in CI"** (my BSD-grep `\|` mistake; re-checked with the Grep tool, `pip-audit==2.10.1` is in the security job and matches the exemption register item by item ⇒ registered exemptions, no new findings), and the cover letter's numbers are **fully consistent** with the manuscript; Previously **CS round: snapshot generation path committed + submission-package coherence check + the fix-coverage tool's baseline revived** — (1) the citation-key snapshot created in the CR round says "re-run the export script" while **no such script exists** (the same shape as the CK-round CITATION.cff false statement) ⇒ the new committed tool `scripts/tools/export_paper_citation_keys.py` makes the snapshot a **pure-function output** (no generation date — a date would break byte-wise comparison by construction), with a `--check` mode that verifies without writing, wired into `make paper-citation-keys` and the script inventory; (2) measured: `paper/SUBMISSION.md` — the last human checklist before submission, and exactly what a reviewer sees — had **drifted in four places**: page count 54 (measured xdv 55 / PDF 57), table count 22 (measured 19 — already 19 in the CN round), TODO markers 14 (measured 18), and a refs.bib identifier caliber missing `publisher={PMLR}` — with **nothing able to detect its own staleness** ⇒ the auditor gains a submission-package coherence surface (declared values must equal measured source values), 7 new cases, three mutants red each, neutral control green; (3) `scripts/tools/audit_fix_coverage.py` pinned its default `--base` to the V-round start (50+ rounds ago) ⇒ the default output is whole-tree "uncovered" noise, the main reason nobody ran it ⇒ the default is now `auto` (the latest commit touching the audited scope), 5 new cases, wired into `make fix-coverage`; (4) tool reader census: 39 tools have no execution-side reader (32 are per-round one-shot mutation scripts — evidence retention); (5) ADR-0036 de-hardcoded (A1 read "gate chain 20 steps" — a number that drifts as gates are added is a silent expiry point for the criterion); Previously **CR round: register→manuscript→bib citation chain + compile-time CJK check + four 2026-10 frontier papers** — four new frontier references registered and cited in Related Work: TestSuiteBench (arXiv:2610.13065, mutants generated per requirement, agent mutation scores below 60%), the fault-enforcement risk of LLM-generated regression tests (arXiv:2610.11835, 8%-17% of generated tests assert faulty behaviour), the independent assurance plane (arXiv:2610.28667) and oracle signals in agent-authored tests (arXiv:2606.18168, 80.2% of test patches weak or without an explicit oracle signal); all four were taken verbatim from the arXiv Atom API `summary` field (**not** the HTML full-text page — the first fetch mixed in LaTeX macro names, and a secondary source offered a conflicting set of numbers; both are registered). The round also surfaced a submission-grade defect: two `refs.bib` entries put Chinese text in `note`, which flows into the `.bbl` and is typeset verbatim while Latin Modern has no CJK glyphs — missing characters in the PDF references, **with a compile exit code of 0**, so no one had seen it in 180 rounds. The auditor now rejects CJK in typeset text and accepts `publisher={PMLR}` (PMLR assigns no DOI). A new three-way citation-chain lock requires every registered reading to be cited in the manuscript; the committed snapshot makes that check run in CI (4/4 mutants red, neutral control green).; Previously **CN round: the submission manuscript is native LaTeX + 2026 frontier literature reconciliation** — `paper/tex/manuscript.tex` is no longer generated, and four classes of defects that had been printed into the PDF are fixed (20 `// SRC:` comments typeset as body text, 22 Typst list markers, two captions broken by embedded SRC fragments, five tables overflowing by up to 215pt); the audit now reads the `.tex` (`% SRC:`, `\%`, `\citet`, `\_` unescaping, draft-selection precedence; six new locks) and measures **218 claims / 100.0% traceable / 0 invalid references / 0 strict failures**. Retrieval (2026-10-25) added three groups of independent convergent results — Arnaudo ICSTW'26, Radaideh BDAI'26, Tufano SpecOps'26, SWE-Mutation ACL'26, Hamidi arXiv 2609.09315, SWT-Bench NeurIPS'24, TestExplora ICML'26, Konstantinou arXiv 2607.05139; external readings are registered separately in `docs/study/EXTERNAL_READINGS_2026-10-25.md`, and the four `/tmp` SRC pointers are frozen into the repo. Previously **CM round: 1.0.0 release close-out + a read-side number-existence check in the paper audit + four-state replication integrity** — Appendix E's cost table pointed at `emse_stats_extensions_20261025/`, which does not contain the 261-row readings it claims (26,114.9 / 0.025885 / 35-of-261): **the path existed, the numbers did not, and the audit still reported 100% traceability**. Fix = historical label + table W-1 in `WITHDRAWN_ARTIFACTS` (frozen values) + `// SRC-CHECK: strict` per-number checking; the audit gains a block-level existence criterion (derived statistics are disclosure only, strict blocks block), A/B: wrong pointer rc=1, fixed rc=0; 11 new locks. Replication integrity is now four-state (ok / FAILED / missing manifest = FAILED / absent disclosed), measured at **8 directories / 401 files verified / 0 failed / 5 absent**, with 4 new locks. README/MODEL_CARD carry the 1.0.0 known limitations). Previously **CL round: the remote CI red on all three versions attributed — a snapshot step that ran before pytest shifted the formatted-file count by one and knocked the registration gate over** — the "Generate static-check snapshot" step originally ran *before* pytest; the written `docs/history/static_report_<date>.md` counts toward ruff's formatting surface ⇒ the registration gate's recompute read 976 against BASELINE's 975 ⇒ both real-tree locks inside pytest went red on all three versions while the local fresh clone stayed green; fix = move the snapshot steps to the very end of the job (after pytest and the diagnostic re-run) + make the diagnostic grep tolerate xdist prefixes + a step-order regression lock (mutation check: restore the old order ⇒ the lock turns red). Previously **CK round: the replication package reconciled with the withdrawn corpus + the 1.0.0 criteria landed in ADR-0036** — REPLICATION.md carried 15 dead references (main_batch / charts / analysis, withdrawn with the 2026-10-24 data purge), its §6 checksum inventory registered 69 files / 7,048 entries against a measured **4 files / 181 entries**, and its §7 CITATION.cff version and line numbers were stale; CITATION.cff line 5's "archival metadata is prepared" pointed at a file that is not on disk and has no git history — an in-repo false claim, now corrected to an honest pending item. ADR-0036 operationalizes "frontier-leading 1.0.0" into A measurement 7 items / B research 4 items (user authorization required, non-blocking) / C release mechanics 5 items. Previously **CJ round: the citation exemption register gains readers + the repro chain makes withdrawn-source branches explicit [SKIP] + the citation gate's out-of-repo crash fixed** — the 12 exemption keys registered during the v0.8.0 data turnover were **filed twice** (24 rows; `load_allowlist` returns a set, so duplicate keys merge silently and the duplication was invisible to every reader) and the in-file "zero exemptions" claim was never updated; new lock file `tests/test_citations_gate.py` (**13 cases**: real-tree register 5 — no duplicate raw rows / well-formed keys / all load-bearing with no stale entries / sufficiency / claimed count == actual; synthetic 8 — neighborhood caliber / self-metric exemption / targeted exemption / silent set-merge semantics / exclusion surface / out-of-repo two states), mutation 3+1 (duplicate key 2 red / stale line number 3 red / reverting `_rel` 3 red / neutral control 0 red); `check_citations.py` raised an **uncaught `ValueError`** on out-of-repo `--files` absolute paths (`collect_files` tolerates them, the scan segment did not) ⇒ `_rel()` fallback fix; `reproduce_zero_llm.py` withdrawn-source branches now emit an explicit `[SKIP]` (three-state ok/FAILED/skipped; exit code driven only by FAILED commands + SHA256SUMS failures). Two stale registrations corrected: `798d8c72`'s measured 12,491/254 never reached BASELINE (the consistency guard's slack absorbed the split drift) and the AO3 line lock was **falsely green for two rounds** (pinned `**CH round:` while the head had already moved to the CI round, satisfied via the historical chain's `Previously **CH round:`) — advanced to `**CJ round:`. Full confirmation run **12,490 passed / 268 skipped / 0 failed** (collected 12758). Previously **CI round: a closing statement and the tree split apart — "12,749 passed closing measurement" was written before the closing run happened, and that run would have shown 4 failures** — a full regression run over the uncommitted CA–CH batch measured **12,745 passed / 5 skipped / 4 failed** (collected 12754, 224.78s), while BASELINE and §1 claimed a "CH-round closing measurement 12,749 / 0 failed" that never happened (the `suite_seconds: 221` note still opens with "this key takes the CG-round closing run", the CH booklet §3 says "backfilled after the closing run" with no backfill anywhere, and there is no paired-`date` fingerprint); four CG real-tree locks (`tests/test_invocation_caliber_cg.py` r01/r03/r04/r05) hardcoded CG-round denominator literals (on-disk 31 / chain 17 / declared 71 / registered 9 / structure 28-30-29-30 / register 15 rows), CH moved every one on the write side (new `check_flag_effect.py` + one stale register row removed ⇒ 32 / 18 / 73 / 8 / 29-31-30-31 / 14 rows) while refreshing only BASELINE and §1 — the gate chain stayed green throughout (the gates reconcile against the refreshed BASELINE) — **gates green ≠ tests green**, and the full pytest run is the locks' only reader. Disposition = the four locks now read BASELINE as their single source of truth (`gates`/`invocation` sections via the CG gate's `load_baseline_yaml`; r01 keeps the CF/CG dual-implementation rendezvous assertion) + property literals kept (faces 5 / ghosts 0 / bottoming+dynamic 1-1 / zero unread criterion flags) + r05's register-total literal swapped for the "flag-diff count == `invocation.flag_diffs`" cross-check + errata appended to the BASELINE annotation chain and §1 (history not rewritten); verification = `pytest tests/test_invocation_caliber_cg.py` **66 passed** (collected constant 66) + CG mutation **70 anchors all red + control 0 red** (no `# mutation:` residue); zero gate changes, zero `src/` changes, zero LLM, $0; see CLOSING_TREE_SPLIT_CI_2026-10-24（分册已删除）. Previously **CH round: two flags CI passes on every run were never read by their own gate — "zero unread criterion flags" was a true green that misled** — a new read-only gate `scripts/gates/check_flag_effect.py` (553 lines / 23 top-level functions) judges **dest liveness**: CG asks whether anybody passes a flag (reader liveness), this gate asks whether the flag is wired inside the source, one `(gate, flag)` denominator recomputed by two independent implementations and then reconciled, with four mutually exclusive and exhaustive states `live / proxy / dead / opaque` plus the identity `declared = live + proxy + dead + opaque`. On the pre-fix tree (working tree minus this round's four new files with its wiring reverted): 31 gates on disk / 24 with argparse / **71** declared instances, of which **2** never read their dest = 1 dead (`check_docs_history_drift --warn-only`, dispatch reads only `args.strict`) + 1 proxy (`checksum_results --verify`, dispatch reads only `args.write`; behaviourally equivalent to dispatching on `--verify` today, but the equivalence is guaranteed by its `required=True` mutually exclusive group — exactly **1** such group repo-wide — not by the flag itself); **both are criterion-grade and both really passed by ci.yml** (before: lines 744 / 298), which is why CG's "zero unread criterion flags" is a true green that misleads: the token has readers, the flag has no effect path. The same flag name is live in one gate and dead in another (`--verify` read 3 times in `check_baseline`, 0 in `checksum_results`; the 71 instances dedupe to **51** names across **11** duplicate groups), so the denominator has to be combinations rather than names. Escape forms (`vars(args)` / `getattr(args, …)` / `**args` unpacking / `args.__dict__` / `parse_known_args()` / passing the whole Namespace) hit **0** recomputed by AST structure, and a hit makes the whole gate **opaque** and counts red — a substring search would condemn any gate whose docstring merely discusses those forms, which is exactly what this gate's first version did to itself. The gate ships **no waiver table**: a decorative flag has only two legitimate end states, wired or deleted. After the two write-side wirings the current tree reads on disk **32** / argparse **25** / declared **73** / live **73** / proxy **0** / dead **0** / opaque **0** with **1** required mutually exclusive group, CG-side numbers move with the wiring (31→32, 17→18, 71→73, code-locked 26→29, registered-unread 9→8, the other eight unchanged) and both identities hold separately (CG `73 = 14 + 29 + 8 + 0 + 22`, CH `73 = 73 + 0 + 0 + 0`). **99** new locks ⇒ collected **12754** = **12749 passed + 5 skipped**; the harness `scripts/tools/ch_mutation_verify.py` kills **75 anchors with 1 neutral control at 0 red** (collected steady **99** per anchor, sha256 byte-exact restore, wall clock 334s; all three round-1 survivors dispositioned — M38 exposed the "unreadable ⇒ silence" defect inside this round's own gate, repaired fail-closed with M76 added, M68 was an ambiguous assertion sharing a substring between the `[OK]` line and the pass line, one assertion pins one line, M06 re-verified as an **equivalent mutant** and recorded in the equivalence list instead of the anchor count, **6** such zones in total; maximum fan-out M53 turns **32** red, mostly `KeyError` ⇒ the red count is fan-out, not criteria); pre-registration run **12,742 passed / 5 skipped / 7 failed, 231.20s**, rc=2 (the seven reds = the baseline guard + four CG real-tree locks + two CF locks, all pre-registration state); coverage lines **19522/20036 = 97.4346%**, branches **7159/7590 = 94.3215%** (**0** of the 136 `src/**/*.py` files has an mtime later than 2026-10-24 00:00 and the newest epoch 1792766822 equals CG's ⇒ inherited state; −1 line / −1 branch versus CG sits inside the ±2 jitter band and matches CE digit-for-digit); zero LLM, $0; rules registered at `docs/MEASUREMENT_INTEGRITY.md` §79; see the CH booklet（分册已删除） (Chinese). Previously **CG round: a gate being on the chain is not a gate running with the same caliber** — a new read-only gate `scripts/gates/check_invocation_caliber.py` puts the `make` chain and `.github/workflows/{ci,perf}.yml` side by side for the first time, with the pre-fix measurements bound to **two rebuildable trees** (pre-fix = working tree minus this round's four new files and its wiring; intermediate = pre-fix + the gate script itself): ① the non-blocking criterion searched step bodies by **substring**, so CF's recompute gave **3 non-blocking / 26 blocking** while YAML structure (step-level key at indentation 8, comment lines excluded) gives **2 / 27** (intermediate **2 / 28**) — the extra one is the sentence "switch to `continue-on-error: true`" inside a ci.yml comment being read as a live key, and that number had already entered `BASELINE.yaml` and register §1; ② the same script's flags across call faces were never reconciled — comparing only `make gates` ↔ ci.yml yields **1** asymmetry, all faces pairwise yields **3**, two of the reasons existing only in Makefile and perf.yml **comments** (comments are never recomputed); ③ `check_prompt_artifacts` is absent from the `make gates` chain while CI runs it bare without the strict flag ⇒ "wired" true, "enforced" false; ④ a third non-blocking layer: the shell fallback `|| echo` of a `::warning` message and block-level `set +e` **active regions** (state advanced line by line through `set ±e`); ⑤ `$STRICT_FLAG` injected from a `workflow_dispatch` input ⇒ a static sweep cannot see the effective caliber; ⑥ every on-disk gate must answer "who runs me" (pre-fix 30: 16 on the chain / 28 in ci.yml / 1 in perf.yml / 1 imported only from `experiments/` / 0 unattributed); ⑦ flag readers classified in four liveness classes (passed on a face / code-locked / registered / unread): on the pre-fix tree **31** of **69** declared flags never had a reader (**9** caliber + **22** range & presentation), on the intermediate tree **33** of **71** (**10** caliber) — the gap being this gate's own `--list` (caliber) and `--quiet` (presentation). A lax reader rule ("the token appears somewhere in the file") reports "0 unread", which is not cleanliness but the judged surface being cancelled. Disposition, five conventions: judge by structure not substring / flag equality by **effective value** (`add_argument`'s `default=` recomputed in place with `ast`, `--f=v` parsed like `--f v`) / differences land in the machine-readable register `docs/invocation_caliber_allowlist.txt` (15 rows over 5 kinds; no reason, malformed, duplicate, stale, not found on the face and unclaimed in §1 each get their own red line) / an unread *caliber* flag is red while range and presentation flags are only counted / a denominator self-check (close-out **71 = 14 passed + 26 locked + 9 registered + 0 caliber-unread + 22 presentation**), plus explicit `[SKIP]` with a cause for missing repo-level preconditions, the gate judging its own wiring, and six `[SURFACE]` caliber lines; register §1 gains a 13-key "调用口径（CG 轮）" row and BASELINE gains 13 `invocation:` keys. Zero LLM, $0; 66 new locks (all but the 6 real-tree cases run on a synthetic call surface in `tmp_path`) ⇒ collected **12655 = 12650 passed + 5 skipped**; mutation **70 anchors all killed + 1 neutral control 0 red** (three disposition rounds: round 1 left 12 survivors = 2 criterion gaps + 9 criteria-without-locks + 1 recorded equivalent mutant, round 2 left 1, red distribution 36×1 / 11×2 / maximum fan-out 33, wall clock 424s, collected steady 66 per anchor); see the CG booklet（分册已删除） (Chinese). Previously **CF round: the numbers on the registration face and the booklet manifest had no reader at all** — `docs/PROJECT_STATUS_REGISTER.md` §1 hand-wrote **999** formatted files while a clean HEAD tree (`00e8c24d`) recomputes `ruff format --check .` to **1037** (drift **+38**, working tree **1050**); the gate-count row named `BASELINE.yaml` `gates` as the authority, yet those keys had **0** readers in the whole-repo Python (`check_baseline.py` only looks at the two zeros under `static_checks`); **5** of the **78** booklets on disk were absent from the §3.5 manifests (the dead-link direction always had a gate, the reverse direction got its first reader this round), and zh §2.2 numbering `[6…20, 22, 21, 23]` was not consecutive while readers treat it as a count; disposition: a new read-only gate `scripts/gates/check_registration_consistency.py` (823 lines) that recomputes 15 numbers in place, requires a machine-parseable current-caliber declaration, reads every BASELINE key it points at (absent, non-integer or unequal all red), reconciles the booklet lists in both directions and audits owner liveness plus its own chain wiring, while the **830** bare numbers outside the declaration stay disclosed but unjudged (811 when the §1 brackets landed); +46 locks (46 passed), 38 mutation anchors all red + neutral control 0 red (zero LLM, $0); Previously **CE round: the model-fingerprint gate called `pinned=true` "comparable" and called a window count a corpus verdict** — before this round `scripts/gates/check_model_fingerprint.py` judged only `pinned is True`, and three gaps were measured on the same tree: (1) nothing on the gate side read `alias_mismatch` (**0** readers at HEAD, while the writer registered it at three places `experiments/run_benchmark.py:3838/3840/3852`; the stored corpus holds 85 `False` + 2 `None`), yet "alias unchanged, returned model changed" is exactly the original S29/F13 drift shape, so a batch pinned=true still returned rc=0; (2) a `requested_alias` no longer in the runtime model set still returned rc=0 (first decidable after the CD round collapsed the runtime surface to the single alias `deepseek-flash`); (3) the success line "passed: 1/1 checked artifact" used a denominator taken from the 2-day mtime window (measured: 2 in window / 1 exempt ⇒ 1 actually checked), while the benchmark corpus is 239 files recursive on disk / 107 tracked / 64 top-level non-recursive, with 122 provenance / 87 fingerprint / 85 pinned structures (⇒ the 2 unpinned ones outside the window were never judged at all) — "this one file is clean" and "the whole corpus is clean" were the same output. Disposition: two comparability fences (`alias_mismatch is True` as a strict boolean; `requested_alias` reconciled against the **imported runtime authority** `src.config.config_generator.COMMON_MODELS` rather than a copied constant, with an explicit `[SKIP]` naming one of three causes when unavailable) plus four `[SURFACE]` caliber lines disclosed on all four output paths (success, blocking, empty window, `--allow-empty`; corpus-side alias readings are disclosed, never judged). **The pinned verdict and its direction are byte-for-byte unchanged.** Process incident: the first version of the fence imported fine inside the test process but under `make model-fingerprint` the script caliber sets `sys.path[0] = scripts/gates` ⇒ `ModuleNotFoundError` ⇒ the whole fence silently degraded into a skip; after `sys.path.insert(0, PROJECT_ROOT)` both calibers agree and the fence and the skip each carry their own anchor. Zero LLM, $0; 19 new locks (35 → 54) ⇒ collected **12543**, full suite **12538 passed / 5 skipped / 0 failed**, coverage 19522/20036 lines = **97.43%** and 7159/7590 branches = **94.32%**, mutation 33 anchors all red + 1 neutral control 0 red. See the CE booklet（分册已删除）. Previously **CD round: runtime and documentation surfaces converge on "DeepSeek official only", and derived readings are recomputed against the on-disk corpus after the historical archives were deleted** - the provider registry (`PROVIDER_TEMPLATES`) now holds only `deepseek`, `COMMON_MODELS` holds only `deepseek-flash`, and the third-party SDK call path (domain detection / client cache / double retry / temperature passthrough) is removed together with its price-table and `.env` template entries; 330 tracked historical result files (3 batch JSONs + 327 traces, all recording non-DeepSeek models) were deleted and `SHA256SUMS` was recomputed (1869 entries verified, 20,895,308 bytes); derived readings were recomputed on the surviving corpus: the mutation x detection table drops from 10 to 7 batches, detectable n falls back to paired n (605->556, 658->609) and rates become 14.03% / 1.64% / 48.86% (stratum means, delta and correlations unchanged cell by cell); the trace-corpus locks move from 9086 to 8763 files, 129058 to 126408 spans and 27135 to 26166 token attributes, while the corpus-guard caliber re-measures at 239 / 138 / 8216. Two categories stay outside the purge, with reasons stated: third-party literature citations (papers, leaderboards, external adapters) and the credential-scrub deny-list (`OPENAI_API_KEY` etc., because DeepSeek is consumed over the OpenAI-compatible protocol). Zero LLM, $0; collected 12524, full run 12519 passed / 5 skipped / 0 failed, coverage 19523/20036 lines = 97.44%, 7160/7590 branches = 94.33%. Previously **CC round: patch resampling could never take effect against a real LLM - `DebuggerAgent`'s system prompt mandates JSON output, so a live call returns a `{"root_cause":...,"patch":"```python...```"}` envelope, while the resample callback applied `extract_code_block` to the whole envelope. JSON-escaped newlines are literal `\n`, the fence regex never matches, the entire JSON is treated as the patch, and `check_naming_contract` necessarily rejects it, so `resampled` stayed False (reproduced with one live call; every existing test mocked plain code blocks, hence no lock). Fix: unwrap the envelope with `extract_json_object` and take a non-empty `patch` field, falling back to raw extraction for plain code; 2 new regression tests + 3 mutation anchors all red / control survived; after the fix all 19 surfaces rerun with `resampled=True / success=True` (19 calls / 12,212 in / 4,344 out / $0.00888); the pre-registration run was 12,553 passed / 5 skipped / 1 failed in 225.11s, the final in-chain run (`make gates`) was **12,554 passed / 5 skipped / 0 failed in 222.37s (rc=0, 234.07s wall clock)**, and the baseline moved 12,552 -> 12,554 (lines 19572/20086 = 97.4414%, branches 7169/7600 = 94.3289%)**. Previously **CB round: the state-channel gate's success sentence was wider than its judgment surface - the gate judged only in-place writes (2 keys / 11 sites) and literal reads (57 keys / 353 sites), while LangGraph's canonical write path (a node returning an update dict) measured 45 keys / 95 sites entirely outside it, which is exactly the silent-drop path behind M14 / O35 named in the gate's own docstring. Of 118 declared keys, 35 were never touched, and one of them (`failure_frequency_applied`) has zero literals anywhere in the repo: its declaration promises "`_debugger_node` writes True", but the node only builds a prompt section, and `None` is documented to mean "flag off", so "feature off" and "never written" are indistinguishable in the data. Disposition is read-side only: `channel_coverage()` three-way coverage, four disclosure lines after the success sentence, and a per-key `--coverage` table; update dicts are disclosed but never judged, `src/` untouched. A self-reference defect was fixed too (the gate's own docstring and its guard test had been counted as "literal elsewhere", erasing the one zero-literal key). 17 new locks (13 -> 30) plus 18 mutation anchors all red / control survived; the pre-registration run was 12,551 passed / 5 skipped / 1 failed in 226.95s, the final in-chain run (`make gates`) was 12,552 passed / 5 skipped / 0 failed in 226.42s (rc=0), and the baseline moved 12,535 -> 12,552**). Previously **CA round: gate-waiver staleness and the number of artifacts hidden behind waivers were never disclosed - the 16 `EVIDENCE_DIR_EXEMPTIONS` registrations were only queried while suppressing a warning, never audited: 2 had gone dead (`emse_jsonmode_smoke_20261013` directory gone; `emse_spec_ir_quixbugs_20261013` 53/53 already tracked, and deleting both left the gate output byte-identical), leaving 14 registrations that hid 155 of 158 untracked files - "no waivers at all" and "waivers hiding 155" looked identical on success**. Disposition is read-side plus fail-closed: one `ExemptionCoverage` source of truth (hidden = total - tracked, all registrations resolved in a single `git ls-files` call) + five drift classes (missing / fully tracked / empty / unreadable / name outside the scan surface) decoupled from the empty-surface path and blocking + per-waiver `[EXEMPT]` lines and a one-line total on success; the scan verdict caliber, values and denominators are untouched and `src/` has zero changes; 12 new locks (21 -> 33) + 16 mutation anchors all red / control 0 red). Previously **BZ round: attributing and fixing the three historical CI red families - 29 tests referenced gitignored archive artifacts (fresh-clone FileNotFoundError), 45 transitive-dependency vulnerabilities cleared by upgrade, cross-platform libm last-ULP tolerance**. Measured: run 39905189493 (head 5eb51607) - test 3.12/3.13 failed at the "Run tests with coverage (parallel)" step, the 3.14 job hit the 30-minute cap and was cancelled, and Security failed at the pip-audit lock audit step; the failure list was taken verbatim from the check-run annotations API (publicly readable), and a fresh-clone simulation (shallow + the same CI environment variables) reproduced 31 failures - the local full suite stayed green only because the artifacts were on disk but ignored. Fixes: 408 contract-locked artifacts committed (5.9 MB, layer-by-layer negations), three classes of missing preconditions (corpus census / history cut points / double-blind files) converted to explicit named skips with measured readings (folded neither into pass nor into fail), the pillow / aiohttp / certifi / otel families upgraded (all 45 vulnerabilities had upstream fixes; lock 132 → 133), and the test job timeout raised 30 → 60. Verified: fresh-clone rounds closed 31 red → 9 red → **0 red** (12453 passed / 46 skipped, every skip reason checked), pip-audit "No known vulnerabilities found, 5 ignored", and the local full suite identical to the pre-upgrade run. Previously **BY round: the report's analysis-set flow was never disclosed - `## 数据来源` lists included files only, while before that list the loader drops 886 rows for unsupported datasets, 2,463 for schema incompleteness and 300 untracked-baseline rows, and the 7,010 loaded rows are then collapsed by task-id dedup into 6,449 duplicates (91.997%), leaving 561 unique task rows as the pairing unit**. Archive-wide (scan face 246 files / 10,659 rows; unsupported datasets 77 / 886; schema 59 / 2,463; read/load failures 0 / 0; untracked 300 rows; loaded 110 / 7,010; duplicates 6,449; unique 561; field None: `passed` 0 / `detection_rate` 45 / `repair_rate` 52; all JSON files carrying `results` 257 / 11,197, of which 13 / 538 are not benchmark-named; mixed mode 169 / 9,473, duplicates 8,494, unique 979). Read-side only: single source `experiments/_analysis_flow.py` + `statistical_analysis.analysis_flow_stats` + a new `## 数据来源` subsection (flow table + three-clause reconciliation + external-caliber footnotes) + one console line; no judgment value or direction moved, `src/` untouched; **27 new locks + 46 mutation anchors = 45 mutants all red / control 0 red**. Previously **BX round: the last two write-only keys' read sides were never disclosed - every `risk_summary` row carries the `enabled=False` placeholder (`enabled=True` 0, non-null level 0, key absent 2,333, `contract_status` present 0), so "the channel never opened" looks like "everything is low risk"; the five `mdo_crash_rate` input layers (not run / material absent / not measurable / provisional pool / measured) share one `None`, and `mdo_pool_floor_ok=False` is a two-meaning key on 1,516 rows (provisional pool 530 + default 986)**. Archive-wide (257 batch files / 11,197 rows): risk present 8,864; crash layers 2,312 / 122 / 986 / 530 / 94, with 94 canonical values (79 zero / 15 nonzero, pooled 15/3,200 = 0.46875%) and 530 provisional raw values (12/7,190 = 0.1669%) never merged with measurements. Read-side only: single source `experiments/_residual_keys.py` + a two-table report section + one summary line, no judgment value or direction moved, `src/` untouched; **102 new locks + 44 mutation anchors = 43 mutants all red / control 0 red**; pool closure 41,545 + 22,035 + 12,908 = 76,488, zero-reader pool empty. Previously **BW round: the patch acceptance chain's coverage and denominators were never disclosed - `patch_precision` (preregistered E3), `patch_plausible_evidence` / `patch_plausible_invariant_violation`, `patch_abstain_signals`, and `patch_validated` / `patch_validate_verdict` had zero report-side readers (the abstention and validation families had test-only readers), so `None` "not computable" and `0.0` "computed as zero" were indistinguishable**. Across 257 batch files / 11,197 rows: accepted set 1,331 (16.61%), stored precision 45.60% vs union 50.75% vs gold 57.92%, selective risk 54.40% (gold 42.08%), suppression precision 93.98% (gold denominator) / 93.11% (all), and only `patch_evidence_level` had reachable validation input (1,007 rows; `repo_verification` / `deterministic_repair_status` were empty archive-wide). Read-side only: a single source `experiments/_patch_acceptance.py`, a four-table report section and two summary lines; no judgment value or direction moved; **94 new locks + 68 mutation anchors all red / control 0 red**. Previously **BV round: the silence of two batch-VIII/XIV judges was never disclosed - 20 of 5935 archived rows are test-hacking positives and 4442 FL constraint rows were never evaluated, none of which appears in any report**. `test_hacking_suspected` / `_signals` (batch VIII, ADR-0022) and `fl_constraint_verdict` / `_hit_rank` / `_changed_functions` (batch XIV, ADR-0028) have had **0** readers in the report surface since they were written; the judge returns `suspected=False, signals=[]` on "no original code / no patch / either side unparseable", which is **indistinguishable** from "all three signals ran and hit nothing" (5915 rows cannot be told apart), while the FL gate folds six early exits into one `not_evaluable` (4442/5935). Archive-wide (257 batch files / 11197 rows): hack judged True **20** (`hardcoded_input_branch` 12 + `exception_swallow_added` 8) never appeared in any report; FL hit 1487 / miss 6 / not_evaluable 4442 => hit ratio **99.60%**, while the 3+ changed-functions bucket is only 29/1493 = **1.9%** => **the whole-file-rewrite cause recorded in ADR-0028 does not explain that ratio**. Fix: the judge now returns `status` (five tiers, the two parse sides get separate `try` blocks) + result rows carry `test_hacking_status` / `fl_constraint_reason` (each of the six early exits has its own reason) + single source of truth `experiments/_verdict_silence.py` + a `detector_silence_stats` reader (recorded / inferred / not-applicable / no-verdict-key sources kept separate, inferred marked as a lower bound) + a new report section (hack 9 columns / FL 11 columns + discriminative-power note + two footnotes) + one batch-summary line; **verdict values and directions unchanged**. **87 new locks + 2 old contracts rewritten**; **mutation: all 58 anchors red + neutral control N01 0 red** (first-run survivors V04 / P11 / S03 all fixed in place); sandbox confirmation run **12257 passed / 19 skipped / 0 failed, 218.94s / rc=0** (normal caliber 12271 / 5 / 0, collected 12276); coverage lines **19538/20052 = 97.4367%**, arcs **7150/7584 = 94.2774%**. See DETECTOR_SILENCE_BV_2026-10-23（分册已删除）. Previously **BU round: the Self-Repair Trap judge's input reachability domain was never disclosed - all 5935 archived verdicts read "not suspected" while two of its three signals received 0 rows of input archive-wide.** `self_repair_trap_suspected` / `self_repair_trap_signals` were written on 5935 rows since batch XIV (ADR-0028), always `False` / `[]`, with **0** readers in the report; the judge's three per-signal minimum point counts (3 / 2 / 2) never reached the report, so "**3200** rows carry a single point and enter no gate", "**2723** rows reach the collapse gate and really read clean" and "declining and score received **0** rows" render as one and the same number - plus **531** rows with a genuine two-point decline that structurally cannot enter the >=3 gate and **12** rows whose `oracle_quality_history` is `None`. Re-running the judge in-process over the archived histories disagrees **0** times, so neither the judge nor any stored value moved - only disclosure was added: the single source `experiments/_trap_input_domain.py`, the `self_repair_trap_domain_stats` reader and a 13-column report section (silent-arm / empty-domain / re-run-error notes plus two caliber footnotes, every threshold rendered from the constant). **79 new locks** across eight classes + **all 61 mutation anchors red with the neutral control U63 at 0 red** (collected steady at 339, `# mutation: ` residue 0, rc=0); the first run's three survivors (U18 / U30 / U54) and three illegal anchor literals (U49 / U50 / U53) were dispositioned in place. Confirmation run **12184 passed / 5 skipped / 0 failed, 194.81s / rc=0** (collected 12189; pre-registration 12183 + 5 + 1 with only the baseline guard red); coverage 19526/20040 = 97.4351% lines and 7150/7582 = 94.3023% arcs, bit-identical to BT (`src/` untouched). See TRAP_INPUT_DOMAIN_BU_2026-10-23（分册已删除）. Previously **BT round: the acceptance-oracle provenance and visibility fields were stated backwards and had zero readers.** `oracle_type` / `test_visible_to_system` were written on **8012** rows since R52 with no reader anywhere; the writer also labelled SWE-bench repo-level acceptance (gold FAIL_TO_PASS, tests **hidden** from the system) as `generated_test` + visible. Fix: labels consolidated in `experiments/_oracle_provenance.py` (new `gold_fail_to_pass`), `_oracle_descriptor(task, baseline, state)` derives the real acceptance path, and all **five result-construction sites** pass it; the report gains an "acceptance oracle provenance and visibility" section (repo rows must be gold + hidden, violations named row by row). Archive: all 8012 rows are `generated_test/True`; the 50 repo rows predate R52 (`(None,None)`, i.e. not mislabelled); historical artifacts are not rewritten and paper numbers do not move. **12 new locking tests**; collected **12082** = passed **12077** + skipped 5 (sandbox 12062 / 19 / 1; the single failure was the baseline guard, green after backfill); coverage unchanged at 19526/20040 = 97.4351% / 7148/7582 = 94.2759%. See ORACLE_PROVENANCE_BT_2026-10-22（分册已删除）. Previously **BS round: the coverage workflow did not run locally - the branch caliber was only carried by the `--cov-branch` CLI flag.** `pytest --cov=src --cov-branch -n 4` failed with `DataError: Can't combine branch coverage data with statement data`: `.coverage` (controller) had 1 line / 0 arcs while the four workers had 2.4k-23k arcs - same command line, two calibers. Fix: pin `[tool.coverage.run] branch=true` in `pyproject.toml` plus one packaging test lock, so non-CLI entry points can no longer write statement data. Re-run under the CI command: **19526/20040 = 97.4351%** lines and **7148/7582 = 94.2759%** branches; the ratchet (96.40/92.50) is green with 1.04 / 1.78pp headroom (AA-4: water levels are not raised from a local macOS run). collected **12070** = passed **12065** + skipped 5 (sandbox run 12051 / 19 / 0, 202.70s, rc=0). See COVERAGE_CONFIG_BS_2026-10-22（分册已删除）. Previously **BR round: all 27 items of the third-party central review confirmed and closed, zero LLM / $0.** Report HEAD `53bbbbd4`, closure HEAD `f49959b2`; P1=14 / P2=13, P0=0, **zero false positives**. Code: the runtime probe no longer re-executes on the host after Docker/kernel-sandbox refusal or under a stronger backend (N01), and target-module frames survive filtering by real path (N09); bad token accounting under an effective budget (env **or** per-task cap) latches `budget.exceeded` and raises non-retryable `BudgetAccountingError`, so retries/failover/instance caps cannot bypass it (N02); E7 validates candidate-to-task identity before merging, so swapped sheets no longer score kappa=1 (N03); cost attribution is checked per row and unknown tokens are never priced with another row's rate (N04, full `None` plus an attributed subtotal); `paired_contrast` uses the shared latest-row rule (N05); non-0.5 binomial ties (N06), zero-baseline MDE (N07), standard unified-diff detection plus fallback prefixes (N08), OTel non-object line isolation (N10), and call-scoped cache accounting for concurrent experts (N11); `sys.path` injection now yields to docstring/`__future__` (F04), P2P baseline and post-patch regression are measured separately (F05), pass@k groups by program identity (F06), batch loading is atomic (F07), `--json` emits an error line for crashed tasks (F11), and the ineffective `ALLOW_UNSANDBOXED` recovery hint is removed (F12). Process: the release gate now requires `ci.yml` + `head_sha` + all jobs green and excludes its own in-progress run (F08). Docs: ICST'26 restated as relative +17.72%/19.80%/20.92% vs HITS (absolute +7.52/+5.84/+5.85pp, F09), ADR0030 drops the field-level extrapolation (F10), redistribution scope stated field by field (F14), df cost ratio 6.2x (F15), n=41 bounds 7.3/8.6/12.6% (F16), replication note aligned to 87 tasks (F17), CANDOR v7 >=21.1pp (F18), false_fix measurable definition (F19), bilingual API examples matched to real signatures (F20). **77 new locking tests**; collected 12069 = passed 12064 + skipped 5 (sandbox confirmation run 12050 / 19 / 0, 537.77s, rc=0). See BR_ROUND_CENTRAL_REVIEW_2026-10-22（分册已删除）. Previously **BQ round: the report read side treated the four status channels as if they did not exist - the four result-row keys persisted by BN had zero row readers.** BM wired `contract_status` on the production side only (a `final_state` to result-row passthrough); the report faces (`build_analysis`'s 30 metric helpers, the `run_main_batch` summary block, `statistical_analysis`) read **none** of the four keys (probe measurement: **row readers = 0** across the 184 `.py` files under `experiments/` + `scripts/`; the control key `contract_missing_symbols` does have one real row reader, `scripts/tools/refresh_patch_field.py:201`, whose `or []` folds null / absence into an empty list - a same-family fold registered but not fixed this round). Consequence: "this leg ran and came back clean (ok)" and "it crashed (error) / was switched off by design (disabled) / had no material (unavailable) / was never recorded (null / absent)" were indistinguishable on every report face - the seven-round disclosure chain from BG to BN broke at its last step on the experiment side. Across 1,702 archived JSON files the four keys appear **0** times (no batch has run since BN; the 8,865 `contract_missing_symbols` occurrences are pre-BL history). The fix is read-side disclosure only, with **no change to any judgment value or direction**: a new helper `experiments/analysis_parts/check_leg_analysis._check_leg_measurability` (four channels x seven grades plus three identities) + a new `analyze_results` section "Check-leg measurability" (silent arms are named "**not "all four legs clean"**" instead of an all-zero table) + a `run_main_batch` summary line (unrecorded is stated as such, never as a zero table that reads as clean). **65 new locks + 0 existing assertions rewritten** (five suites together: 219 passed / 0 failed); mutation **16/16 anchors red** + neutral control 0 red (collection face constant at 219); no new gates this round. **Pre-existing red closed along the way**: the two lenient `json.dumps` write points in `scripts/tools/bo_raw_readside_fold_probe.py` (committed with the BD-BP batch b44a1aad) made the strict-JSON gate red at HEAD (the gate scans **tracked** files only via `git ls-files`, so a gate run before commit could not see it - the BP closure's "all gates green" statement had diverged from the actual artifact; registered, not rewritten) - after adding `allow_nan=False` in two places (synthetic payloads, zero behavior change) the gate is green again and the full gate chain on a clean tree is 19/19 rc=0. collected **11992** = passed 11987 + skipped 5 (this session's sandbox confirmation run measured 11973 / 19 / 0, 198.25s / rc=0; sandbox and normal readings are never mixed). `src/` untouched, so line coverage is bit-identical to BP (19393/19904 = 97.4327%); branch coverage 7103/7532 = 94.3043% (-2 vs BP, attributed three ways: the sandbox skip set + xdist reshuffling - neither is an `src/` change). See CHECK_LEG_READERS_BQ_2026-10-22（分册已删除）. Previously **BP round: the statistical comparison side folded "this row never recorded a contamination level" into silence - and the same absence went two different ways in two consumers.** BO closed the raw read side; this round read the same `details` rows where they are actually compared: `analysis_parts/cross_analysis` did `if not level: continue`, recording **nothing** for an unrecorded row, while `statistical_analysis.contamination_view_summary` did `recorded or "unknown"`, folding those rows into `unknown` - the same number as "the check ran but could not decide" - and section 5.3 added the first count to "not in the comparison" while explaining it with the second. Measured on the archive (**159** batch files carrying the key / **320** arms): `key_absent` **2093** rows, value null **0**, exact empty string **0**; **122** arms have no field at all, so `available=False` and **section 5.3 disappears from the report entirely - the same shape as "this section never ran"**; and when a bucket is missing, `high_vs_low_success_delta` used to be **absent as a key**, so "never computed" and "computed as zero" read alike. Disposition: parallel disclosure only, **no judgement value and no judgement direction moves** - the four absence legs `key_absent` / `value_null` / `value_blank` / `other_falsy` with `n_details` / `unobserved_total`, `available=False` split into `no_rows` / `no_level_recorded`, the delta made an **explicit `None`** with `delta_missing_buckets` naming the missing bucket (of **198** comparable arms in the archive **0** carry a delta: 157 missing both, 41 missing high), section 5.3 adds the unrecorded row count, names silent arms per arm, spells out which bucket is missing inside each `N/A` cell, appends "the ≥0.2 / ≤0.2 criterion cannot be applied on this data" when no arm yields a delta, and the second consumer gains `unknown_of_which_absent`; the cross-consumer identity (`view.unknown` = real unknown rows + `cross.unobserved_total`) holds on **320/320** arms. One caliber fix: `value_blank` counts only the **exact empty string** - a whitespace string is truthy on the batch-IX side and forms its own bucket, so counting it as absent would break the identity by 1 on any corpus containing one, and the archive happens to contain **0** such rows, **so probe and real corpus share the blind spot**. **62 new locks** (per-class counts from `--collect-only`) + **0 of the existing 92 rewritten** (four suites together 1415 passed / 3 skipped / 0 failed) + **mutation 18/18 anchors red, collected pinned to 154 at every anchor, neutral control 0 red, `# mutation:` residue 0**; no new gate; `src/` and `config.py` write-surface hits **0**, so coverage is bit-identical to BO/BN/BM (identical readings do not prove `src/` is untouched - the write census does). Confirming run **11922 passed / 5 skipped / 0 failed, 195.48s, rc=0** (collected **11927**). See the BP booklet（分册已删除）. Previously **BO round: the raw-artifact read side folded "never written / key absent / value null / unreadable file" into a measurement - while the switch that decides whether raw exists was itself never recorded.** BN put the four-valued `status` on disk; this round measured the `experiments/` read side that consumes those artifacts, five sites that share one idiom: `x = state.get(key) or []` and then `len(x) == 0`, so "read an empty" and "never read" live in the same `if`. (1) `--save-state` decides whether `raw/` exists at all, yet the census over **246** archived batch JSONs shows the value **0** times and none of the 15 provenance keys is it, while the disk holds **34** `raw/` directories but only **88** raw files are tracked, over **6** batch dirs (`.gitignore:172` ignores `experiments/results/**`) - so "never switched on", "switched on but not archived" and "switched on and kept" collapse into one observation. Disposition: provenance now records `"save_state": bool(save_state)`, new batches only, **the default is not flipped**. (2) `cross_file_root_cause` folded the three absences into `DEP_GRAPH_INCOMPLETE`, i.e. "the dependency graph really had zero edges"; the two-arm replay over real batches (9 arms, 29 multi-file failures) shows **14 judgements flipping on whether `raw/` is passed before this round and 18 after** (the extra 4 are key-level absences that folded identically in both arms, so they could not flip before), and the `level1` arms flip **0**. The legs are now `RAW_UNAVAILABLE` / `DEP_INPUT_ABSENT` / `DEP_INPUT_NULL`, `dep_edges` goes back from `0` to `null`, and the report self-certifies via `raw_coverage` / `rule_evidence` / `unreachable_rules`: reachability keys off a **non-null value**, because since BN the whitelist always writes the key, so "key present" is no longer evidence; `ROLLBACK_CONSERVATIVE` / `TOPOLOGICAL_ORDER` are zero-evidence by construction and the report says so instead of the distribution being read as "no such root cause". (3) In `position_aware_ab` the four non-computable legs (missing `raw/`, missing task artifact, missing `position_aware_focus` key, unusable `details`) were numerically AND textually identical to "measured, zero hits" - all `0.0`, all printed `0.0%`; `0.0` was not a conservative value but a reading manufactured from absence. Grades now name ten cases while the existing `-1.0` "not computable" slot is kept (no new value domain), and one narrower fold closed: a `focus=null` row that does carry repair iterations or a patch used to enter the denominator as a real miss. (4) `compare_failures` disclosed only when **both** arms were missing, let a corrupt JSON abort the whole report and rendered an empty artifact `{}` exactly like a missing file; now each arm is named, corrupt artifacts become `unreadable` without raising, and an empty artifact gets its own block. (5) The root-cause command that `cross_file_ab` prints after a run did not pass `--raw-dir`, so **copying the hint re-folded 14 cases** into the structural bucket; the parameter is added. **Judgements and their direction are unchanged** (absence discloses, it does not attribute or reject). Zero impact on archived readings, measured: the eight arms recompute bit-identically to the archive (21.43 / 0.0 / 0.0 / 0.0 / 25.0 / 0.0 / -1.0 / -1.0), the 236 details rows split into **156** key-present-but-null, **80** with content, **0** key absent, and the 311 `aitester.json` artifacts split into **216** key absent / **95** non-empty lists / **0** null, so `DEP_INPUT_NULL` has 0 archived instances (that leg is prepared for batches from BN onwards). **70 new locks** (per-class counts harvested from `--collect-only`) plus 2 existing assertions rewritten to the new caliber ("conservative `0.0`" -> `-1.0` + grade, case count unchanged) and **23/23 mutation anchors red with collected pinned to 70 at every anchor, neutral control 0 red, `# mutation:` residue 0**; no new gate this round; the write-surface census hits `src/` and `config.py` **0** times, so coverage matches BN/BM digit for digit. See the BO manual（分册已删除） (Chinese). Previously **BN round: the status channels were disclosed at runtime and appeared 0 times in archived artifacts - "the check crashed / never ran" stayed byte-identical to "the check found nothing".** The four-valued `status` that BH→BM built only ever lived in memory: the read-only probe shows `experiments/run_benchmark._dump_state_artifacts` folding 5 runtime states (`ok` / `error` / `unavailable` / `disabled` / key absent) into one 558-byte shape, while the result row's "5 states -> 5 shapes" was propped up by the single `contract_status` leg BM had just connected - only a **per-channel** measurement exposes that the static / safety / oracle pairs fold at both boundaries; a census of the archive (1700 JSON files, 1121 raw, plus 9096 JSONL rows) finds those 7 keys **0 times in 0 files**. The disposition is pure filing-back: +10 whitelist keys, +6 keys in each result-row branch (the failure branch keeps both key sets isomorphic with `None` placeholders), plus a new BK-family gate `scripts/gates/check_status_persistence.py` whose exemption quota is deliberately **empty** (the 10 `_status`/`_outcomes` channels declared in `AITesterState` must be a subset of every persistence surface; an unresolvable `**helper(...)` spread is not credited - a false red beats a false green), wired into `make gates` and an independent blocking CI step. **Judgment values and directions are byte-for-byte unchanged** and no historical artifact is rewritten (the archive keeps its 0 occurrences; this round only buys reviewability for future batches). **54 new locks + 24/24 mutation anchors red (collection face constant at collected=54) + the neutral control, which only rewords a comment, 0 red, `# mutation:` residue 0**; the confirming run is green (readings in BASELINE.yaml); `src/` was untouched so coverage matches BM item for item (identical readings do not prove `src/` was untouched - that claim rests on the change list). See the BN manual（分册已删除）. Previously **BM round: the experiment and report read sides folded "the check never ran / the check crashed" into the most favourable value of their domain — a crash filed into the "clean" group, an unmeasured row filed into "zero regressions"**. BL closed the double-read caliber inside `src/` and its registered boundary said `experiments/` was not done — this round is that piece. The crash leg of `run_benchmark._compute_contamination_risk_level` returned `"low"`, the most **favourable** value in the domain, and downstream `low` **is** the clean group (`statistical_analysis.contamination_view_summary.clean_n`, the baseline of `analysis_parts/cross_analysis.high_vs_low_success_delta`); `contract_status` reached the experiment-side result row but nobody read it, so BL's `contract_unmeasurable(...)` disclosure never appears in the `risk_summary` the experiments emit; `run_main_batch._print_r4_summary` divided a `== 1.0` numerator by **every** row, so unmeasured rows scored as "no regression / no test error" and `0.0%` read as "zero regressions". All four dispositions sit on the disclosure / bucketing side: the crash leg returns `unknown` (**a missed half-fix, not a new design** — the inner `_combined_risk_level` gained `unknown` back in O22 with a docstring that literally says "exceptions all fail open into low", while the wrapper was never updated), `contract_status` is forwarded to `build_risk_summary` (score / level / factors byte-identical), R4/N1 divide by the measurable row count and print "measurable k/n" (`k=0` prints unmeasurable instead of `0.0%`), and section 5.3 gains a "rows not in the comparison" column. **Judgment values and directions are unchanged**: `unknown` triggers no rejection and does not touch `passed`, it only leaves the clean group; the numerator in ③ is still the count of `== 1.0` rows. Three corpus readings: the 15-input reachability grid moved from `{'high': 1, 'medium': 2, 'low': 12, 'unknown': 0}` — where 5/15 legs crashed and **all five folded into `low`** — to `{'high': 1, 'medium': 2, 'low': 7, 'unknown': 5}`; across **8865** archived `contamination_risk_level` values (7843 `not_applicable` + 1022 `low`) non-string patches are **0**, so the crash leg has 0 real instances and ①② change no published number; of 11197 rows `regression_rate` is measurable in **0** (8012 `None` + 3185 key-absent) and `test_error_rate` in 7206 ⇒ 7.3% under the old denominator vs **11.3%** measurable (`single_agent` 6.7% vs **94.0%** — a number produced by switching the denominator, never to be differenced against the historical value). **32 new locks + mutation 9 anchors all red (red counts 8/3/1/2/2/1/2/1/1) + neutral control M10 at 0 red**; confirming run 11736 passed / 5 skipped / 0 failed at 209.76s / rc=0 (37 warnings; collected 11741); `src/` untouched, so coverage is digit-identical to BL (19393/19904 lines = 97.4327% / 7105/7532 arcs = 94.3309%, 511 uncovered lines, 427 missing arcs). **`make gates` full chain rc=0** (first run before the backfill, final run after it, each executed alone with no overlapping pytest run or documentation edit: both runs rc=0, all 18 commands over 16 targets green, wall **211s / 213s** from paired `date +%s`; the in-chain pytest is xdist `-n 4 --dist loadfile` **without `--cov`** and gave the same verdict twice, **11736 passed / 5 skipped / 0 failed** in 205.60s / 207.07s, `4 workers [11741 items]` — the same collected face as the confirming run; warning totals 50 / 54, the gap sitting only in the `test_spec_expr_property` hypothesis `invalid decimal literal` group, with no per-entry attribution ⇒ only the two observed totals are registered); the per-step tail readings were byte-identical across the two runs and `ast-guards` matches BK digit for digit. Lessons: a red count must be registered together with the collection face that produced it (M1=83 / M2=91 — the earlier "collected always 32" claim was falsified by re-measurement); two denominators inside one print block is the morphological source of this defect; differencing `94.0%` against `6.7%` is a caliber error. See the BM manual（分册已删除）. Previously **BL round: the publish side already carried a status, the judgment side still read the empty value — closing the "written but never read" face**. Rounds BH→BK wrote "unreadable" into observability keys, but nobody had checked whether the judgment side reads them: this round's census found `assess_task_risk` had no `contract_status` parameter at all, and the key-name judgment reads of the four status channels were all **0** before the change. The disposition has three layers. Per-leg status: the new primitive `status_for_check(outcomes, check)` — `safety_check_status` is a worst-of aggregate over two independent pre-checks and must not impersonate the contract leg, and a leg with no record yields `None`. Double reads on the consumer side (four sites in `risk_approval` + the call site at `graph/debugger.py:918` + the static layer at `agents/debugger.py:795` + S2 at `patch_applier.py:507` — **the text is only appended to the note; `factor` and the G2 verdict stay byte-for-byte unchanged**). And status≠ok becomes a failure pattern: the **12th** detector `check_unmeasurable` (5 status channels × `error`/`unavailable` → MAST `Inadequate verification`), with `_flatten_record` now lifting the inner `output` keys of trace records. Four publish sites completed (`nodes.py` per-leg channel and trace payload, the `run_benchmark.py` row, the `state.py` declaration). **`None` and `error` are different readings**: across 1702 archive files `contract_missing_symbols` appears 8865 times, **8853 of them `None`** — treating "not recorded" as "failed to measure" would re-judge history wholesale; all five status keys appear **0** times there ⇒ zero impact on prior readings. **32 new locks + mutation 22 anchors all red (red counts 2/3/1/2/1/3/1/1/1/1/1/3/2/1/1/1/1/1/1/1/1/1) + neutral control 0 red** (wall 86s, green baseline at collected=32, sha256 byte-exact restore, `# mutation:` residue 0); confirming run 11704 passed / 5 skipped / 0 failed at 209.29s / rc=0 (39 warnings; collected 11709); coverage **19393/19904 lines = 97.4327%** / **7105/7532 arcs = 94.3309%**, with 511 uncovered lines and 427 missing arcs digit-for-digit identical to BK (this round only recovers its own new lines and arcs). **`make gates` ran green end to end: rc=0 twice** (first run before this backfill, second run after it, each executed alone; 18 commands green both times, wall clock **213s / 214s**; the chain's pytest used xdist `-n 4 --dist loadfile` and **no `--cov`**, and both runs returned the same verdict - **11704 passed / 5 skipped / 0 failed** (207.16s / 208.34s, 54 / 46 warnings, collected 11709) - with the per-step tail readings byte-identical between runs; at the head ruff reported 974 files already formatted and mypy 0 errors over 137 source files; `ast-guards` inside the chain reproduced BK's out-of-chain readings 136/78/20/0/20/19 digit for digit). Lessons: swapping the instrument mid-round contaminates the before/after delta (register present values only, or re-measure before); a lock that iterates the set under test is a self-validating loop (deleting a key shortens it instead of turning red — M11 survived); an unreachable corpus combination fakes survivorship ("contract ok + dangerous-API error" cannot trigger behind `safe_apply_patch`'s `ast.parse` pre-gate — M17 survived; the reachable shape is `disabled` plus an aggregate `error`); and inherited four-decimal figures must be re-divided (BK's 97.4300% / 94.3200% divide to 97.4288% / 94.3218%; two-decimal readings unchanged). See the BL manual（分册已删除）. Previously **BK round: a capture-surface ratchet for the `ast.parse` guards — “unreadable” has two exception faces, and point-by-point convergence never finishes**. A single-leg guard (catching only `SyntaxError`) cannot catch the `UnicodeEncodeError` that Python 3.14.6 raises for lone-surrogate text (a `ValueError` subclass; a null byte still raises `SyntaxError` itself, so it is not a new leg), so the exception escapes the “unreadable ⇒ degrade” branch all the way to the caller — the clearest case was `static_validate_patch`, where a candidate patch carrying a surrogate crashed the whole `_debugger_node`. Branches that did degrade folded “unreadable” into judgment-bearing empty results (`[]` / `set()` / the original code / `ok=True`). This round converged **13 sites** across 5 modules onto the shared constant `AST_UNREADABLE_ERRORS`, attributed shapes through `unparseable_shape()` (fenced_block / git_diff / undecodable / syntax), disclosed all 13 through the `outcome_sink` side channel with three publishers writing `check_status` / `check_outcomes`, and added a CI-blocking gate, `scripts/gates/check_ast_parse_guards.py` (a new `ast-guards` target in `make gates`) — **the same ruler re-measured the HEAD tree** at 79 sites / 35 single-leg / 15 violations (exactly 13 BK + 2 BJ), while the current tree reads 136 files / 78 sites / 20 uncovered / 0 violations, the 20 survivors registered as a shrinking quota of (site count, fold shape). **Judgment values are byte-identical**: 11 decision surfaces × 14607 inputs = 160677 comparisons with `identical=160636 / escape_fixed=41 / both_raised=0 / UNEXPECTED=0`, and all 41 escape legs came from the hand-built shape grid (0 from the 14596 archive strings). **55 new locks + all 13 mutation anchors killed (24/15/1/2/1/5/2/2/1/1/1/5/1) + a neutral control at 0 red, zero `# bk-mutation` residue**; the confirming run is **11672 passed / 5 skipped / 0 failed in 191.76s at rc=0** (collected 11677, no `--cov`); the `make gates` full chain is **rc=0** (first run 242s wall from a paired `date +%s`; in-chain pytest **11672 passed / 5 skipped / 0 failed in 193.90s**, 47 warnings, collected 11677 — the same collection face as the confirming run; the new `ast-guards` gate reads bit-for-bit identical to its out-of-chain self-test; the final run — started only after these gate sentences were backfilled — is rc=0 at 198s wall / 192.95s in-chain / 44 warnings, its 47-line gate-reading tail byte-identical to the first run). Lessons: the two survey denominators (125 sites / 64 and 60 single-leg) were not reproducible, so registration follows the gate's own self-test; HEAD is not “before this round” (seven uncommitted rounds sit beneath it), so baseline attribution needs a per-file check; and this round's own +19 lines invalidated the Prompt Card — editing a prompt-bearing source file means re-running the generator in the same batch. See the BK manual（分册已删除）. Previously **BJ round:  closing the “unreadable ⇒ no findings” path in the AST assertion-consistency checker — `check_assertions` now reports a status per leg, so an empty finding list is no longer free evidence**. The checker folded “scanned and nothing found”, “input empty”, “the test text could not be parsed so nothing was ever scanned” and “the code under test could not be parsed so the type-inference channel went mute” into one return value. Replaying HEAD through the real consumer proved the reachability: **a fully fenced artefact, a genuine syntax-error artefact and an empty artefact each produce readings byte-identical to a real clean scan** (`oracle_findings=[] / tautological_count=0 / o4_triggered=False`), while O4 — the tautological-assertion route that marks `test_defect` and sends the task back to the Generator, the only write-side path on that side — **never fires for an unreadable artefact**; when the target cannot be parsed the type-inference leg goes mute yet reads the same as “all types agree”; and an artefact carrying a lone surrogate makes `ast.parse` raise `UnicodeEncodeError` (a `ValueError` subclass, not a `SyntaxError`), which the old `except` clause let escape through the observation layer. Disposition: `check_assertions` takes an optional `outcome_sink` appending `{check, status, reason}` per leg (four-valued `ok / disabled / unavailable / error`, the vocabulary BI hoisted into the single source of truth `src/utils/check_status.py`, of which this round is the 4th consumer), with three implementation rules each carrying a directional lock: **a blind early exit does not record the second leg**; **the fence attribution test is “starts with three backticks after stripping leading whitespace”**, not “three backticks appear somewhere in the body” — the two spellings differ by exactly **1** site over the real corpus, cross-checked by `scripts/tools/bj_discriminator_crosscheck.py`, which deliberately does not import `src` (`sites=10855 / unparsable=76 / strict=72 / loose=73 / loose_only=1`); and **parsing is funnelled through `parses_as_module`**, the only behavioural change this round. `_run_generator_postchecks` rolls the legs up **worst-of** (they are independent, so the direction is opposite to BG’s “any backend ok ⇒ ok” — both directions are locked) and publishes `oracle_check_status` / `oracle_check_outcomes` as declared graph-state keys defaulted to `None` — undeclared keys are silently dropped by LangGraph — with the key names chosen after a grep found `experiments/oracle_quality_replay.py:1254` already using `oracle_status` for the *contract* oracle, and a lock asserting the two fields are not the same thing. **Judgment values and their directions are byte-identical**: no fence is stripped and the conservative “unreadable ⇒ zero findings” is *not* turned into a rejection — the old-vs-new `repr(findings)` diff over all **10855** corpus artefacts shows **0 differences** (`crashes_old=0 / crashes_new=0`) — and three judgment-flip mutants sit in the harness precisely to keep anyone from “improving” the verdict along the way. **63 new locks + mutation 23 anchors all red (9/2/9/1/11/5/3/3/3/1/2/8/8/2/1/2/50/8/1/1/7/20/1) + neutral control 0 red** (collected 501 throughout); real corpus: **10855** `generated_test` sites = 10671 genuinely scanned + 77 empty input + 72 fenced blocks + 31 assertion-free + 4 syntax errors, the 76 “unreadable” ones byte-identical to a genuine clean scan under the old reading, while the second leg records only `disabled:target_not_provided = 10702` = 10855 − 153 ⇒ `error:unparseable_target` is **0 instances** in the corpus (registered by name, not written off as “excluded”); among the **57** archives declaring the switch enabled there is exactly **1** blind site; `oracle_findings` / `tautological_count` / `o4_triggered` appear **0** times across the 1594 parseable archives ⇒ the new channels carry no historical readings and zero backfill; pre-registration run **11616 passed / 1 failed / 5 skipped, 197.48s** (collected 11622; the single failure = the baseline guard: collected 11622 − declared 11554 = 68 > 6 slack); confirmation run **11617 passed / 5 skipped / 0 failed, 192.77s, rc=0** (xdist `-n 4 --dist loadfile`, collected 11622 = 11617 + 5 + 0, the same collection face as pre-registration; 63 warnings; the serial single-process control on the same tree took 521.41s / rc=0, so elapsed times are only comparable at the same worker count); coverage at the registered caliber **19272/19793 lines = 97.3678%** / **7072/7504 arcs = 94.2431%** (uncovered 523 → 521, exactly at the edge of the documented ±2 jitter, and missing arcs 432 → 432 unchanged bit-for-bit); mypy reports zero issues across **137** source files; `make gates` full chain **rc=0** (first run 198s wall, in-chain **11617 passed / 5 skipped / 0 failed, 192.51s**, 54 warnings, collected 11622; re-verification run 198s wall, in-chain 192.46s, 13 warnings; the 90 step-reading lines of both runs diff empty once timings and warning counts are normalised; the terminal run (executed after this backfill) came in rc=0, 197s wall, in-chain 192.06s, 66 warnings, and its 88 gate step-reading lines (excluding pytest warning noise) match the first two; the earlier attempt stopped at the lint step with `rc=2` and offers no gate reading to cite). See the BJ manual（分册已删除）. Previously **BI round: closing the “unreadable ⇒ passed” path in the two write-time static prechecks — `check_naming_contract` and `dangerous_api_added` now report a status, so an empty result is no longer free evidence**. Both guards folded “compared and nothing was deleted / nothing new appeared” and “the input could not be parsed, so no comparison ever ran” into the same return value. Replaying HEAD through the real consumer proved the reachability: with a pre-patch source the current interpreter rejects (a py2 `print` statement) and a patch that deletes the module-level constant `CONST`, `_check_patch_safety` returned `applied=True`, the constant vanished from the code headed for disk, and nothing was logged — `contract_missing_symbols` stayed `null`, the same value a genuine clean comparison produces; when only the *patch* was unreadable the guard reported “the patch deleted 2 module-level symbols”, a statement about a comparison that never happened. Disposition: each guard takes an optional `outcome_sink` appending `{check, status, reason}` (four-valued `ok / disabled / unavailable / error`, BG's vocabulary verbatim, now hoisted into a single source of truth `src/utils/check_status.py`), `_check_patch_safety` rolls the two guards up **worst-of** (they are independent checks, so the direction is opposite to BG's “any backend ok ⇒ ok”) and publishes `safety_check_status` / `safety_check_outcomes` as declared graph-state keys defaulted to `None` — undeclared keys are silently dropped by LangGraph — and `type_repair_layer` pairs its historic `contract_ok` with `contract_status` / `contract_reason` / `contract_outcomes`. **Judgment values and their directions are byte-identical**: this round turns silence into disclosure, it does *not* turn the conservative “unreadable ⇒ allow” into a rejection, and two judgment-flip mutants sit in the harness precisely to keep anyone from “improving” the verdict along the way. **50 new locks + mutation 19 anchors all red (4/2/1/5/1/5/1/1/4/4/1/2/1/1/1/2/1/4/7) + neutral control 0 red** (collected 452 throughout); real corpus: `contract_missing_symbols` sits at **8865** sites in **172** archived JSON files, **8853** of them `null` — the footprint of the four-way fold — while archives keep no pre-patch source (`target_code` **1** site against `patch` **11101**) ⇒ nothing can be recomputed backwards, zero backfill; pre-registration run 11553 passed / 1 failed / 5 skipped, 213.52s (collected 11559; the single failure = the baseline guard: collected 11559 − declared 11504 = 55 > 6 slack); confirmation run **11554 passed / 5 skipped / 0 failed, 212.07s, rc=0** (collected 11559 = 11554 + 5 + 0, the same collection face as pre-registration); coverage at the registered caliber **19247/19770 lines = 97.3546%** / **7064/7496 arcs = 94.2369%**; mypy reports zero issues across **137** source files; `make gates` full chain **rc=0** (217s wall, in-gate pytest 11554 passed / 5 skipped / 0 failed, 212.22s; the verification run took 208s with 202.03s in-gate, a third run 200s / 195.21s and the final run 201s / 195.73s — all four rc=0, every other gate reading identical line by line). See the BI manual（分册已删除）. Previously **BH round: closing the “unmeasurable ⇒ verified” path in the four testless validation layers — each layer now reports a status and the roll-up takes the worst layer, so `passed=True` is no longer free evidence**. The four layers of `src/tools/testless_validation.py` (AST symbol guard / mypy / naming contract / import smoke) folded “this layer never measured” into the same `passed=True` as “this layer finished with zero findings”. **Root cause found by running it**: the mypy layer had been passing `--silent-imports`, which mypy 1.15.0 no longer accepts (live run: `rc=2`), so a clean patch, a type error and a syntax error all returned the byte-identical “mypy 发现 1 处问题” and the layer had never checked any code; this round switches to `--follow-imports=silent` and locks it with argv assertions plus three real-mypy end-to-end cases. Each layer now carries a four-valued `status` (`ok / disabled / unavailable / error`) and the roll-up adds `validation_status` taking the worst layer (error > unavailable > disabled > ok — opposite to BG's “any ok ⇒ ok”, since these four layers are independent checks) plus `degraded_layers`, warning with `layer=status:reason`; only undisclosed fake-clean became fail-closed, while already-disclosed degradations (switch off, not installed, timeout, OSError) keep their `passed`, and the `nodes.py` consumer now records that the result “is not evidence that validation passed”. Real corpus: `TESTLESS_VALIDATION_ENABLE` appears at 107 sites in 100 archived JSON files, all `null` ⇒ zero impact on historical readings. **52 new locks + 1 assertion rewritten to the new caliber + mutation 11 anchors all red (7/4/1/5/2/1/8/2/1/1/1) + neutral control 0 red**; pre-registration run 11503 passed / 1 failed / 5 skipped, 218.93s (collected 11509); confirmation run **11504 passed / 5 skipped / 0 failed, 212.17s, rc=0**; `make gates` full chain **rc=0** (263s wall, in-gate pytest 11504 passed / 5 skipped / 0 failed, 213.22s; the post-backfill verification run, 219s, also rc=0). See the BH manual（分册已删除）. Previously **BG round: closing the "unmeasurable ⇒ fake clean" path in static type checking — mypy/pyright outcomes are now four-valued, so an empty finding list is evidence only when the checker produced a trustworthy report**. `_run_mypy_findings` / `_run_pyright_findings` previously returned `[]` for switch-off, not-installed, timeout, crash, an unexpected exit code and a corrupt report — all indistinguishable from a completed clean check — and `mypy_findings_count=0` folded four states into one 0. Each attempt now records `{backend,status,reason}` through `outcome_sink` with `ok / disabled / unavailable / error`; `type_repair_layer` aggregates them into `static_check_status` / `static_check_outcomes` (any `ok` ⇒ `ok`, otherwise `error` > `unavailable` > `disabled`), emits a warning naming backend and reason on `error`, and passes both keys through the debugger into graph state (declared in the TypedDict, mirrored by deterministic repair). pyright treats empty stdout, invalid JSON, a missing `generalDiagnostics` key, timeout and rc outside 0/1 as `error`; already-parsed findings are kept, but a text fallback never promotes empty output to `ok`. Real corpus: `TYPE_CHECK_ENABLE` is off by default and all 170/170 archived result files record it as `null`, with only the experiment env snapshot listing the key ⇒ zero impact on historical readings, zero backfill. **25 new locks + mutation 8 anchors all red (1/3/1/2/1/1/3/2) + neutral control 0 red**; pre-registration run **11449 passed / 3 failed / 5 skipped, 202.57s** (collected 11457; failures = baseline guard + debug key-set contract + prompt card, the latter two fixed); line 97.32% (19111/19637) / branch 94.14% (7006/7442). See the BG manual（分册已删除）. Previously **BF round: closing the rc==0 verdict in the script toolchain — self-mutation and the template verifier wired to "effective pass", empty suites no longer recorded as survived / self-consistent**. After BA–BE closed M1 / experiments / MDO and the production paths layer by layer, `scripts/tools/` still judged green on bare `rc==0` at two sites: `self_mutation.py`'s preflight baseline gate (an all-skip baseline recorded green, so no later mutant can be genuinely killed) and its mutant classification (an all-skip / xfail / deselect mutant recorded as `survived`, depressing the mutation score without evidence), plus both sides of `verify_synthetic_templates.py` (an all-skip fixed side recorded "gold self-consistent", so the template enters the detection-rate denominator with fake evidence). Fix: all four sites go through `run_has_effective_pass(rc, output)` (`rc==0` with at least 1 real passed and 0 failed; partial skip remains valid; an unparseable summary is fail-closed), with a timeout still outranking an effective pass; a baseline without one records `baseline_no_effective_pass` and blocks by default (`--allow-red-baseline` continues and marks `measurement_valid=false`), the mutant classifier `classify_result(rc, timed_out, output)` records `invalid` + `no_effective_pass:<counts>` (excluded from the mutation-score denominator), and both template sides report "no effective pass". Real corpus: all 80 self-mutation mutant rows identical (score 0.7467 unchanged) and 50/50 templates pass ⇒ zero impact on historical readings and zero backfill. **20 new locks + 8 mutation anchors all red (2/2/5/1/1/1/2/42) + neutral control 0 red**; pre-registration run **11426 passed / 1 failed / 5 skipped, 201.04s** (collected 11432; the only failure = baseline guard); lines 97.31% / branches 94.12%, bit-identical to BE. See the BF manual（分册已删除）. Previously **BE round: closing the rc==0 verdict on production paths — six green points wired to "effective pass", empty suites no longer recorded as a correct fix**. After BA–BD closed M1 / experiments / MDO layer by layer, six production sites still judged green on bare `rc==0`: the detection gate `_run_test_against_code`, the local executor, the venv sandbox, Docker, repo test nodes, and P2P regression. An all-skip / xfail / deselect suite also returns rc 0, and the old code recorded it as "correct fix / safe patch": the detection gate misread defect specificity, the executor carried a false `passed` into the next iteration, an empty `failed_cases` fooled F2P/P2P, and P2P did not roll back even in fail-closed mode. Fix: new `run_has_effective_pass(rc, output)` (`src/utils/pytest_output.py`) is the single execution-level green entry (`rc==0` with at least 1 real passed and 0 failed; partial skip remains valid; an unparseable summary is fail-closed), wired into all six sites; the detection gate records `unavailable` (not over_red), executors add `error_info.type=no_effective_pass`, repo nodes record a failed case, and P2P records `regression_error` (`regression_failed` under fail-closed); the A16 attempt record gains `effective_pass`, and fail→pass only honors an effective pass (an all-skip re-run no longer fabricates flakiness). Real corpus: 11197 rows / 5884 passed / zero statically all-skip / all 50 `repo_verification` rows failed / no archived P2P verdicts ⇒ zero impact on historical readings and zero backfill. **40 new locks + 8 mutation anchors all red (3/1/1/1/2/2/1/33) + neutral control 0 red**; confirmation run **11407 passed / 5 skipped / 0 failed, 199.06s, rc=0** (collected 11412); lines 97.31% / branches 94.12%; `make gates` full chain rc=0. See the BE manual（分册已删除）. Previously **BD round: closing the rc==0 verdict inside the measurement module itself — MDO baseline and mutants wired to "effective pass", predicate moved to a single source of truth**. After BA–BC closed the experiments side layer by layer, `src/measurement/mdo.py` still judged green on bare rc==0: an all-skip / xfail / deselect baseline also returns rc==0, and without short-circuiting every mutant would end in rc==0 too → measured with MDR=0 (recording "it never ran" as discrimination power); a mutant-side rc==0 without an effective pass was recorded as "not discriminated", depressing MDR without evidence. Fix: the baseline short-circuits to not_measurable after the rc!=0 and execution-error criteria and before the probes (`test_not_green_on_base(no_effective_pass)`); a mutant without an effective pass is tracked as `no_effective_pass` and excluded from the MTR/MDR denominator (disclosed as `mdo_no_effective_pass`; all excluded ⇒ `mutant_runs_no_effective_pass`); the count parser and predicate moved to `src/utils/pytest_output.py` as the single source of truth, with `_m1_metrics` keeping same-object aliases so ~20 consumers and existing locks are unchanged. Real corpus: 4044 rows carrying MDO, 624 available, 0 available rows with MDR=0, 0 module-level all-skip ⇒ zero impact on archived readings. **15 new locks + 6 mutation anchors all red (8/2/24/21/2/1) + neutral control 0 red**; confirmation run **11367 passed / 5 skipped / 0 failed, 222.87s, rc=0** (collected 11372); lines 97.31% / branches 94.11%; `make gates` full chain rc=0. See the BD manual（分册已删除）. Previously **BC round: closing the rc==0 verdict in the replay reconciliation tool — three task-level criteria in misguided_metrics wired to "effective pass"**. This module's per-test four-class taxonomy has long listed skip as "no pass/fail signal", yet its task-level replay verdict looked only at rc (an internal inconsistency): `replay_detection`'s fixed side with no effective pass ⇒ `None` (criterion order aligned with `_m1_metrics`); `replay_fixed_green` with no effective pass ⇒ stays `None` ("green not demonstrated" is not False); `_verdict_agreement` with no effective pass ⇒ `not_applicable` (never record mismatch against the archive without evidence); new `_side_has_effective_pass` (outcomes first + summary-line fallback + fail-closed). Real corpus: 350 task rows / 700 sides with zero all-skip-at-runtime ⇒ zero impact on archived readings. **35 new locks + 5 mutation anchors all red (5/3/4/14/1) + neutral control 0 red**; confirmation run **11352 passed / 5 skipped / 0 failed, 195.47s, rc=0** (collected 11357); `make gates` full chain rc=0. See the BC manual（分册已删除）. Previously **round BB: closing the remaining rc==0 verdict consumers — 11 sites in experiments/ wired to the shared effective-pass predicate**. After the BA round introduced `_suite_has_effective_pass`, this round propagates the same predicate to every remaining pytest-suite verdict point in `experiments/` (repo-wide census: 11 sites): the gold self-consistency audit / over-red P4 reruns (new P5 mode) / GCP block pruning / testlevel task-level criterion / ULT gold diagnosis attribution / SRP witness safety gate / four sanity gates / mutation_testing baseline diagnosis — suites that are all skip / xfail / deselect (rc==0 but passed==0) no longer count as effective green; everything is fail-closed. The three `misguided_metrics` reconciliation points and the `src/` production path keep their original calibers pending a dedicated round. Real corpus: 246 archives contain zero module-level all-skip suites ⇒ zero impact on archived readings. **60 new locks + 11 mutation anchors all red (2/2/2/1/2/2/2/2/2/2/1) + neutral control 0 red**; confirmation run **11317 passed / 5 skipped / 0 failed, 243.69s, rc=0** (collected 11322); `make gates` full chain rc=0. See the BB manual（分册已删除）. Previously **BA round**: **rc==0 is not an effective pass — an all-skip / xfail suite executes no assertion**. pytest also returns `rc==0` for a suite that runs no assertion; the old code read only `rc`: detection's fixed side and repair's gold side each had a false-positive channel (all-skip counted as 1.0), the replay tool said `correct`, and mutation detection misread "the tests did not run" as "the tests have no detection power" (rate=0.0). A shared predicate `_suite_has_effective_pass` (at least 1 passed and 0 failed; partial skip with a real pass remains valid; an unparseable summary is False) is wired into four consumers, all fail-closed without an effective pass (None / unverifiable / skipped). Real corpus 246 benchmark files / 9358 generated tests / 114 marked / 12 with detection=1.0 (all conditional, none module-wide all-skip), 736 gold suites / 2 marked / 0 all-skip, 4895 mutation rows / 1376 measured / 132 marked. **35 new locks + 6 anchors red (14/1/3/3/1/2) + neutral control 0 red**; pre-run 11256 passed / 1 failed / 5 skipped, coverage 19002/19528 = 97.3064% / 6960/7396 = 94.1049% (`src/` untouched); confirmation run **11257 passed / 5 skipped / 0 failed, 204.07s, rc=0**. See the BA booklet（分册已删除）. Previously **AZ round**: **no implementation may silently rewrite a scale or a tail — Cohen's g is 0–0.5, not 2g, and an exact p must not be lifted by an epsilon**. `emse_stats_extensions.cohens_g` returned `abs(n10−n01)/(n10+n01)` (2g, 0–1), a scale mismatch with the Cohen's g it claims (0–0.5); `binom_exact_two_sided` compared floats with a `1e-12` tolerance for `p=0.5`, lifting the 113/0 tail of **1.926e-34** to ~1.93e-12. The fix makes g use the effectsize definition `abs(n10−n01)/(2*(n10+n01))` and the exact tail use integer `math.comb` weights (the non-0.5 branch keeps probability ordering); real-batch readings are corrected to g 0.370 / 0.500 / 0.423 / 0.500 (was 0.739 / 1.000 / 0.846 / 1.000) and p 1.716e-13 / 1.926e-34 (12/80 and 113/0). The protected 20261016 archive is untouched (sha256 re-verified OK) and corrected values are reissued under 20261021; paper / EMSE skeleton / replication package / X-round errata updated in the same batch; 21 new locks + mutation M1 11 red / M2 4 red; confirmation run 11222 passed / 5 skipped / 0 failed, 187.56s, rc=0. See the AZ manual（分册已删除）. Previously **AY round**: **preserve at the read layer, judge at the decision layer — `run_b8` must not rewrite the payload shape with `or {}`, and a falsy non-object is not free**. After AX closed the three summary read points, `run_b8`'s payload assembly still folded with `or {}`: `_load_arm` rewrote falsy non-objects (`[]` / `""` / `0` / `False`) to `{}` — "the payload is broken" posing as "there are no metrics" — and `_arm_summary` then reported **$0.0 with no mechanism**; `_load_harness_smoke` priced the cost from the raw payload but stored the rewritten `{}` in the row, so the amount and its evidence came from two different payloads. Fix: the read layer preserves the payload verbatim (absence / `null` stays `None`), and cost judgement stays at the single `_cost_usd` point — historical 0 only for absence / `null`, while falsy and truthy non-objects take the same rejection path (`None` + `token_metrics_not_object:<T>`). Real corpus 14 JSON files / 6 benchmark files / 12 `token_metrics` keys all dicts with zero bad values; both arm costs and all four smoke amounts are bit-identical and protected artifacts are not rewritten; **27 new locks + 6/6 mutation anchors red** (red counts 13/6/8/5/6/8); confirmation run 11201 passed / 5 skipped / 0 failed. See RUN_B8_PAYLOAD_AY_2026-10-21（分册已删除）. Previously **AX round**: **the benchmark/full-stack summary presentation and aggregation read points have a value domain too — presentation may fold absent to the historical 0, averaging may not**. After AW closed the per-arm statistics, three summary sites still passed aggregate `token_metrics` through raw: the terminal Token-efficiency lines formatted with `%d` / `%.2f`, so a legitimate upstream `None` made a completed benchmark raise `TypeError` at wrap-up; the G8 table's total-token cell used `bl.get("token_metrics", {})`, which cannot hold `null` / non-objects and printed bad values into Markdown; `summarize_full_stack` averaged with `or {}` + `float()`, aborting the whole summary on a truthy non-object, silently skipping a falsy one, and folding bool/string/negative/non-finite values into the mean. Fix: all three sites use the shared `token_metric_reading` — presentation keeps absent / null at the AE2 historical 0 and renders present-but-unreadable as `不可读` plus mechanism names (the terminal also logs a warning and never aborts); the mean skips absent blocks historically and makes that baseline `None` + `avg_total_tokens_reason` if any present block is unreadable, never a partial mean, without poisoning task statistics or other baselines. Real corpus: 64 top-level benchmark files / 324 recursive `token_metrics` keys (246 `results.<baseline>` summary blocks + 78 nested shapes) with zero bad values; the 246 summary blocks' terminal texts, the clean full-stack row and all four baseline means are bit-for-bit unchanged (6 nested PREFLIGHT blocks lack `avg_tokens_per_task` and are excluded from the terminal comparison); 48 new lock examples + 8/8 mutation anchors red; confirmation run 11174 passed / 5 skipped / 0 failed. See SUMMARY_TOKEN_READERS_AX_2026-10-21（分册已删除）. Previously **AW round**: **the T1/B2 per-arm statistics' `token_metrics` shape and event count have a value domain too — a bad shape does not abort the analysis, and an event count is not a check-free pass-through**. After AV closed `add_cost`, `arm_stats` still fell back with `res.get("token_metrics") or {}`: truthy non-objects (`"abc"` / `True`) raised `AttributeError` on `.get`, aborting the whole analysis, while falsy non-objects (`[]` / `""` / `0`) were silently rewritten to `{}`; `"calls": tm.get("total_llm_calls")` passed event counts through raw, so bool / numeric strings / decimals / negatives contradicted the pooled column in the same report. The fix preserves `token_metrics` verbatim for the downstream shared readers and routes `calls` through `token_metric_reading` — absent / null metrics / absent field stay historical 0 (AE2), present-but-unreadable ⇒ `None` + `calls_reason` (deduplicated, vertical-bar-joined, written only when non-empty); event counts and token money do not contaminate each other. Real corpus 324/324 arms clean; the stored report reproduces 18/18 and new raw arms 9/9 bit-for-bit, the recomputed `ANALYSIS_REPORT.json` is byte-identical (35542 bytes), protected artifacts untouched; 22 new locks + 6/6 mutation anchors red (0 escapes). Confirmation run 11126 passed / 5 skipped / 0 failed, 179.21s, rc=0; lines 19002/19528 = 97.3064% / branches 6960/7396 = 94.1049% (`src/` unchanged). Zero LLM, $0. Previously **AV round**: **the T1/B2 analysis-side cost entry has a value domain too — a one-sided unknown is not a partial sum, and unknown money is not the string `None`**. After AU closed the three experiment-side aggregators, `analyze_t1_b2_main_batch.add_cost` still priced with `stats.get("token_metrics") or {}` + `tm.get(...) or 0`: `token_metrics=None` folded to 0, a `None` input still priced the output side alone, `True` counted as 1, decimals multiplied through, negatives produced negative amounts, `nan`/`inf` entered the report, strings raised `TypeError`, non-objects raised `AttributeError`; the fragment renderer printed unknown money as the YAML string `None`. The fix routes both token fields through the shared `token_metric_reading`: wholly absent / `null` / `{}` metrics stay historical 0 (AE2), present-but-unreadable fields make `cost_usd=None` with deduplicated `|`-joined mechanisms and no partial sum; unknown YAML money is `null`, unknown tokens render as “unreadable”. Real batch 18/18 per-seed costs reproduce bit-for-bit and the stored fragment is byte-identical; **19 new locks + 6/6 mutation anchors red**; confirmation run 11104 passed / 5 skipped / 0 failed; lines 97.31% / branches 94.10%. Previously **AU round**: **experiment-side cost/usage aggregators treat unknown as zero too — no number when unreadable, and partial sums never pose as full sums**. After AI–AT closed the shared readers and report-side reading layer, `estimate_cost_usd` / `generation_summary` / `usage_totals` / `run_b8._cost_usd` still folded with `int/float(... or 0)`: `None` became free, bool/float/numeric strings were rewritten, negatives and non-finite values entered amounts, AT write-rejection markers vanished from totals, a total could add one unknown side to the other side's amount, and the README printed `$None`. The fix routes amounts and counts through the shared value domain: absence is historical 0, unreadable is `None` + mechanism name, and any unreadable field blocks the whole amount/group; event counters stay independent; the hits column depends only on its own column; `cost_total_usd` and the smoke-inclusive total are `None` when either side is unknown, with merged reasons; the README renders “unreadable / cannot estimate (mechanism)”. Real corpus: 37/37 b8 costs and 6/6 generation costs reproduce read-only; **62 new locks + 7/7 mutation anchors red**; confirmation run 11085 passed / 5 skipped / 0 failed; lines 97.31% / branches 94.10%. Previously **AT round**: **token counting on the write side has a value domain too — a rejected write is not zero, and every rejection must be traceable**. After rounds AI–AS separated "zero / absent / unreadable" on the read side layer by layer, the write side still coerced bad values silently with `int(... or 0)`: bool became 1, floats were truncated, numeric strings were accepted, negatives entered the totals, and `nan`/`inf` or unparsable strings crashed; a bad cache-file `tokens` value could even turn a genuine cache hit into a genuine LLM call. The fix routes `record_usage` / `record_cache_hit_usage` through the shared `count_reason` predicate — a rejected write records no counts but still increments the `llm_calls` / `cache_hits` events, and mechanism names are written to `token_write_reasons` / `cache_write_reasons` only when non-empty; readers treat `token_write_rejected:<mech>` / `cache_write_rejected:<mech>` as unreadable, `otel_export` exports no token attributes, and `write_rejection_count` separates a cache `tokens: null` "unknown" from historical absence. Real corpus 1701 trace files / 10629 `token_usage` rows with zero bad values, existing readings bit-identical; **62 new locks + 19/19 mutation anchors red**; confirmation run 11023 passed / 5 skipped / 0 failed; lines 97.31% / branches 94.10%. Previously **AS round**: **the producer must write legal identifiers first — 32/16 hex, root, parent links**. After AR added canonicalisation and derivation at the export boundary, `TraceSession` still wrote a 16-hex `run_id`, a 12-hex `span_id`, no identifiers on `task_start`/`task_end`, and `parent_span_id` never appeared anywhere in the corpus; real corpus 9086 files / 110926 nodes: 61188 with 16/12-hex identifiers, 49738 without (all before O7), 9085 `task_start` / 9046 `task_end` events with none, 0 parent fields. The fix: a 32-hex `run_id`, a 16-hex root and child spans, `task_start` producing a root in both file and memory modes, node/task_end parents pointing at the root, and an exact name + shape exemption for structural identifier fields from the generic 32+ hex redaction (ordinary long hex in text is still redacted). A producer trace now exports directly as one trace with no synthetic root and no disclosures, and two exports are byte-identical; **10 new locks + 18/18 mutation anchors red**; confirmation run 10961 passed / 5 skipped / 0 failed; lines 97.29% / branches 94.06%. Previously **AR round**: **the OTel export's identifiers must be legal before they can be stable — one trace, 32/16 hex, deterministic derivation**. `otel_export` used to use `run_id` verbatim as `trace_id` (real corpus: 16 hex chars) and export `span_id` verbatim (12 hex chars), neither meeting OTel; missing identifiers fell back to a fresh uuid on every export, and nodes overwrote the file-level trace with their `run_id`, so **8002 files carried two traces, 61188 parent links were broken and 9086/9086 files exported unstable identifiers**. The fix canonicalises identifiers to 32/16 lowercase hex (short hex left-padded, case folded; non-str/empty/non-hex/too-long/all-zero rejected), keeps one trace_id per file, derives missing/invalid values deterministically from SHA-256, re-derives duplicate span ids within a trace with a `span_id_duplicate` disclosure, and exports only `str` string attributes; the real 9086 files / 129058 spans all have a single trace, compliant identifiers, in-file parents, zero disclosures and byte-identical repeat exports; **48 new locks + 16/16 mutation anchors red**. Previously **AQ round**: **the OTel export boundary also needs a numeric value domain — bad tokens must not leak, bad timestamps must not abort a whole file, silent drops must be disclosed**. `otel_export` used to write record numbers into spans verbatim: bool/str/decimals/negatives/nan/inf/containers all reached `gen_ai.usage.*`, a non-finite `ts`/`duration_ms` made `int()` raise and aborted the whole file, and a non-object `token_usage` was silently degraded to "no token attributes". The fix reuses the shared `count_reason` for token counts, accepts only finite non-negative time/duration/budget values (bad ones fall back to the 0 sentinel and are named), reuses the count predicate for iteration, and writes mechanism names into `aitester.export_value_reasons`; the real 9086 files / 129058 spans have zero disclosures and 18 stable files are bit-identical; 61 new locks + 12/12 mutation anchors red. Previously **AP round**: **five report-side aggregate token summarisers also held loose folds — pooling, smoke, A/B, group averages and the cost table must not each fold their own**. t1_b2 pooling's `tm.get(...) or 0` folded a present `None` to 0, read bool as 1, crashed on `"100"`, dragged totals down with negatives, propagated nan/inf and crashed on non-objects; the b8 README's `int(... or 0)` accepted str/bool, truncated floats and crashed on `"10.7"`/nan/inf, while the table printed a literal `None` and §9's sum raised `TypeError`; rag_ab fed `None`/str into `_mean`, counted bool/negatives as numbers, and nan made `p<0.05` false so it reported “no significant difference”; RAG group `_safe_float` accepted `"100"` as 100.0, `True` as 1.0, folded `"abc"` to 0 and let negatives/nan into the mean; the cost table printed a present `None` as `None`. The fix adds **aggregate-metric** shared readers `token_metric_reading` + `sum_token_metric_values` (absence is historical 0, a present `None` is upstream refusal, counts go through `count_reason`, derived averages accept only finite non-negative int/float) and wires the five consumers; unreadable yields no partial sum and tables/README/interpretation say “unreadable”. Real artifact readings are bit-identical; **67 new locks + 33/33 mutation anchors red**; close-out 10842 passed / 5 skipped / 0 failed; lines 97.28% / branches 93.98%. Previously **round AO**: **three report-level token total readers also held loose folds — tier totals, flip comparison and convergence curves must not each sum their own**. `model_gradient`'s `int(... or 0)` skipped non-dicts, read bool as 1, truncated floats, accepted strings and negatives, crashed on nan/inf, and read in/out-only rows as 0; `compare_failures`'s `(row.get("token_usage") or {}).get(...)` + `sum` crashed on truthy non-objects and string totals, folded bad values into totals, and showed `?`/0 for in/out-only rows; `convergence_analysis`'s `_safe_float(... or 0)` accepted per-round str/bool/negative/nan, clamped negative increments while dragging the cumulative down, and crashed on truthy non-objects. The fix adds total-oriented shared readers `row_total_token_reading` + `aggregate_row_token_totals` (the cost-triple reader keeps AN semantics; the value domain is still `count_reason` alone): total-only legacy schema stays readable, non-object/present bad values => `None` + mechanism names, absence/`null` stays historical 0, split contradictions are disclosed only, and any unreadable row blocks the aggregate's partial sum; an unreadable convergence curve gets `available=False` + `rounds={}` + mechanism names; rendering maps "unreadable"/`?`/`0` to three distinct causes and does not judge cost inversion when a total is unreadable. Real batches: 244 files / 322 arms / 10659 rows with zero instances and zero 9-arm old-vs-new total differences, so real output is bit-identical. Previously **AN round**: **three token aggregation readers held their own `or 0` too — unreadable is not zero, and a partial sum is not a total**. `run_benchmark._aggregate_token_metrics`, `trusted_verification.arm_trusted_metrics` and `rag_analysis._token_metrics_from_details` each summed `(r.get("token_usage") or {}).get(..., 0)`: a truthy non-object crashed the write path, a falsy non-object became 0, bool/float/str/negative/nan were folded in as counts (`cache_hits=-3` produced a −300% hit rate), a `total_tokens` disagreeing with `in+out` left consumers disagreeing (110 vs 999), a missing `total_tokens` printed 0, a half cache schema produced partial sums, and the old CLI used the literal "调用 X + 真实" as its denominator. `row_token_reading` moved into the producer module `src/budget/token_usage.py` with a new `aggregate_row_token_usage`: whole-key absence / `null` ⇒ historical 0 (AE2, `n_absent_rows`); present bad values or a partial positive triple ⇒ the whole triple `None` + `n_unreadable_rows` / `reading_reasons` (no partial sums); `llm_calls` judged independently; a split mismatch is disclosed only (`n_token_split_mismatch_rows`; there is no money at this layer); cache via `cache_totals` (old schema ⇒ historical 0; half schema / bad values ⇒ both `None`); three consumers wired and `_row_cost_tokens` aliased. All 783 real-batch rows across 9 arms recompute the five-key `token_metrics` bit-identically; repo-wide census 11197 rows / 337 arms / 1218 absent / 0 bad; **38 new locks + 15/15 mutation anchors red** (neutral control 0 red, collected constant 210); full suite 10723 passed / 5 skipped / 0 failed, coverage 18662/19186 lines = 97.27%, 6765/7202 arcs = 93.93% (missing arcs 437; `coverage report`'s 383 partial arcs is a different caliber), numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AM round**: **row-level token reads in the cost aggregate have a value domain too — the rendering layer must not cover for the aggregator**. `statistical_analysis.cost_analysis` used `tu.get(...) or 0`, folding present-but-invalid values (bool/float/str/negative/nan/inf) into priceable numbers, pricing positive-token rows with a missing input/output split as $0, accepting `by_model` keys/values without a value domain and summing mismatched totals, and letting S11 treat non-counts as accounting evidence. It now uses the shared `row_token_counts`: unreadable rows (non-object `token_usage`, present non-counts, positive partial triples) make that arm's token totals, attribution and money `None` (`n_token_unreadable_rows` + `token_reading_reasons`); split/attribution inconsistencies keep token totals readable and block money only (`n_token_money_blocked_rows` + `token_money_reasons`); attribution moved into `src/budget/token_usage.by_model_reason` and the report delegates to it; S11 evidence goes through `count_reason`. All 783 real-batch rows are int and self-consistent, so the three arm readings and return domains are unchanged; **64 new locks + 10/10 mutation anchors red** (neutral control 0 red); full suite 10685 passed / 5 skipped / 0 failed, coverage 18585/19109 lines = 97.2579%, 6727/7164 arcs = 93.9001%, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AL round**: **row-level token arithmetic in the report has a value domain too — an unreadable row is not zero**. `cost_effectiveness_block` used to keep its own second copy of the arithmetic: `usage.get("input_tokens") or 0` folded absent/null/string/bool/negative/nan/inf into priceable numbers; rows with missing or non-dict `token_usage` were `continue`d before detection counting, so `n_detections` shrank with token readability; positive-token rows with no `by_model` attribution, `input+output != total`, or `Σby_model != total` silently escaped or priced contradictory numbers; and cache-explained zero rows were counted into the AK lower bound. The report now reads the producer's shared reader `src/budget/token_usage.row_token_counts` (ext keeps aliases, so existing AI locks are untouched): an unreadable triple makes `total_tokens` / total $ / both ratios `None` with `n_token_unreadable_rows` + `token_reading_reasons`; a split or attribution inconsistency blocks money only (token total and tokens/detection stay readable, `n_token_money_blocked_rows` + `token_money_reasons`); detections depend on `detection_rate` alone; cache-zero rows no longer enter the AK lower-bound counters. All 783 real-batch rows are clean (0 bad splits / attributions), the three arm totals 6.755979 / 0.876692 / 1.185783 are bit-identical, and protected artifacts are not rewritten; 57 locks + 6/6 mutation anchors; full suite 10621 passed / 5 skipped / 0 failed, coverage 18575/19099 lines = 97.2564%, 6719/7156 arcs = 93.8932%, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AK round**: **a minority of unrecorded rows is neither "free" nor an exact value — the dollar reading is a recorded-spend lower bound**. The main-batch plain_llm_df arm has 35/261 rows with an explicit all-zero token triple and `llm_calls=0` but a non-empty `generated_test` (3 of them `detection_rate=1.0`); S11 saw 13.4% < 50% and kept `computable=True`, so the cost table printed `$/task=0.004543…` as if exact while report §4.1 still said "226 rows priced / 0 unpriceable". Now `token_accounting_sanity` adds the `n_zero_output_rows` subset (only when >0), and `cost_analysis` writes `cost_caliber="recorded_lower_bound"` plus `token_zero_output_rows` whenever cost is computable with `0 < token_zero_rows`; the cost table, $/solved, report §4 / §4.1 and the ext note all state "recorded lower bound, not free" (denominator stays all tasks, numerator is recorded spend only — row-level math unchanged, AE2-locked); ≥50% broken arms remain `NOT_COMPUTABLE`; fully-accounted arms and legacy batches keep their return domains and report text byte-identical; 21 locks + 4/4 mutation anchors; full suite 10564 passed / 5 skipped / 0 failed, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AJ round**: **a cache hit is a third accounting state — neither broken accounting nor "free"**. The producer `record_cache_hit_usage` has always written `cache_hits` / `cache_avoided_tokens`, but no cost reader consumed them: the QuixBugs df arm (50/50 rows hit) was flagged `NOT_COMPUTABLE` by S11, the pure-cache ULT df arm rendered an unexplained "（缺: ）", and the examples df arm was rejected the same way. A shared reader now lives in `src/budget/token_usage` (`cache_caliber` / `cache_totals`; `count_reason` moved from ext as the single value-domain predicate), feeding S11 / `cost_analysis` / both report layers / ext `_cost_per_task`: valid positive cache evidence counts as "has accounting"; a hit row's real spend of 0 is correct, but 0 is not free; invalid or half-schema fields yield `None` plus named mechanisms (`token_field_absent` / `token_not_count` / `token_not_finite` / `token_negative`) with no partial sums; a pure-cache arm gets `cache_hit_no_api_spend`; avoided tokens are never converted into dollars. Real arms QuixBugs 64 hits / 123644 avoided, ULT 39 / 89249, examples 2 / 3387 all become computable and disclosed; the legacy main batch's return domains and protected artifacts stay byte-identical; 68 locks + 19/19 mutation anchors; full suite 10543 passed / 5 skipped / 0 failed, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AI round**: **a token count has a value domain too — an incomplete token sum is not a token reading** — every row's token accounting must be three non-negative integers (`total_tokens` / `input_tokens` / `output_tokens`); non-object `token_usage`, non-numeric / bool / non-finite / negative fields now yield `tokens/task = None` with a named mechanism (`token_usage_absent` / `token_usage_not_object` / `token_field_absent` / `token_not_count` / `token_not_finite` / `token_negative`) and the same read feeds the bootstrap CI (no more `inf`/`nan` leaking into an interval); row-level `input+output != total_tokens` and unreadable `by_model` keep the token total readable but make `$/task = None` (`token_split_mismatch` / `by_model_not_object` / `by_model_key_not_string`); 63 locks + 18/18 mutation anchors; real-batch readings bit-identical and protected artifacts untouched; full suite 10475 passed / 5 skipped / 0 failed, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AH round**: **a per-task dollar amount exists only when the price table covers every `by_model` token and token attribution closes** — all-unregistered, mixed partial sums, missing `by_model`, total mismatch and zero-task denominators now render as `—（无金额）` with a named mechanism (`model_unregistered` / `no_model_attribution` / `token_attribution_mismatch`); the three real-batch readings are bit-identical (`by_model` totals equal `total_tokens`, delta 0) and protected artifacts are not rewritten; 15 locks + 6/6 mutation anchors; full suite 10412 passed / 5 skipped / 0 failed, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **AG round**: **unpriced attribution closed to a single mechanism index** — `cost_analysis`'s `missing_models` no longer swallows bad price domains or shape codes (real batch: 522 rows, 0 changed); shared predicate `model_entry_reason` unifies "not registered vs unreadable" across `run_b8` and the report; the renderer gives mechanism-specific advice (entry shape / price domain / currency / row level), while pure-unregistered and no-token-observation text stays line-for-line unchanged; 46 locks + 15/15 mutation anchors; full suite green, numbers in [BASELINE.yaml](BASELINE.yaml). Previously **round AF**: **what lands on disk is a contract -- no token outside RFC 8259 may leave any controlled write path**. New strict serialization primitive (path naming + fail-closed + no silent null coercion), four central write paths + 41 direct write sites in 39 source files given `allow_nan=False`, new repo-wide gate (7273 artifacts, 0 violations + 0 source sink violations) wired into `make gates` / CI; also corrects AE section 5.6's "68 files with bare NaN" to a text-grep false positive; 28 locks + 9/9 mutation anchors. Previously round AE: price **entry-level** admission delegated to the shared predicate — the `run_b8` aggregator no longer holds its own digit gate: bool/nan/inf/negative prices/CNY/string prices/unregistered models are all rejected with a named mechanism and a builtin-price-ceiling disclosure — + test-side price-table schema domain closed + the registered e2 report stale diff updated (86/88 → 94/100, caused by AD-1 rendering; protected artifacts not rewritten) — zero LLM, full suite green. Previously the AD round: statistical-quantity rendering now preserves magnitude (p=5.89e-26 no longer prints as 0.0000) + the normal-tail complement pattern eliminated + a repo-wide census of silent precision-loss patterns. Previously the AC round: fix for the McNemar p `1−cdf` floating-point underflow — the exact values quoted in the Z-round erratum are now reproducible from the production code path for the first time; also includes an E7 toolchain dry run and an AB-17 seven-read-site wiring audit. Previously the Z→AB batch: closure of 20 findings from the fourth third-party full static review + round-AA coverage audit and the E7 adjudication executable surface + rounds AB-1~17 "absence / zero / price-table admission" criterion chain. See the Latest Optimization row and [CHANGELOG](CHANGELOG.en.md))

# AITester: A Detection-First Python Test Generation and Repair (Attribution) Evaluation System

> **Navigation**: [Documentation index (reading paths by role)](docs/INDEX.en.md) | [Quick start](QUICKSTART.en.md) | [Contributing](CONTRIBUTING.en.md) | [Replication guide (Chinese)](REPLICATION.md) | [Baseline numbers (single source)](BASELINE.yaml)

> AITester is a Python automation system for **attribution-aware** evaluation of test
> generation and repair, with the detection-first protocol as the primary success
> criterion. Core innovations: **Detection-first Chain-of-Thought ("red before
> green")** + **Hierarchical Repair Mechanism**. **Multi-agent orchestration** is an
> **ablatable container** (not a primary claim; E2 δ=−0.3673, ADR-0016/R26).
> **Why we do not use *hand-crafted* multi-agent orchestration (revised 2026-10-10:
> three sources listed side by side; the earlier "consensus" wording is retracted):**
> beyond the project's own n=261 decisive experiment (−28pp vs the detection-first
> prompt protocol `plain_llm_df`), the 2026 external evidence points in
> **different directions and must be presented side by side — it is not a consensus**:
> **(a) Unfavourable evidence** — a Carleton University honours-project replication
> (Radaideh & Corriveau, *Comparing Automated Unit Test Generation Approaches for a
> Java Library Management System*, **not peer-reviewed**,
> report-hub.scs.carleton.ca/projectPage/2872) reports, on **mutation score**, one-shot
> Gemini 2.5 Flash **88.35%** vs CANDOR **35.92%**, and one-shot GPT-4o **69.90%**
> vs CANDOR **45.63%**; the authors note the effect is a **configuration effect
> rather than evidence that iteration harms**.
> *(Correction note: this paragraph previously attributed those figures to
> "CANDOR, ICST 2026" and mislabelled the source as an "IEEE third-party replication,
> IEEE Xplore 11655121" (that document number is unverifiable). The source is in fact
> a self-reported Carleton University honours-project repository (not peer-reviewed),
> and CANDOR is not an ICST 2026 paper.)*
> **(b) Favourable evidence** — the CANDOR paper itself (Xu, Wang, Briand, Liu,
> **TOSEM 2026**, DOI 10.1145/3803418) reports multi-agent line/branch/mutation of
> **0.991/0.970/0.980** on HumanEvalJava; TestAgent (**FSE Companion 2026**,
> DOI 10.1145/3803437.3806428) reports line **92.34%** / mutation **83.69%**.
> **(c) Strongest negative evidence to date** — the ICST 2026 replication study
> (Konstantinou, Degiovanni & Papadakis, arXiv:2601.09695) shows that across
> **6 complete Java repositories / 393 classes / 3,657 methods**, with newer LLMs
> injected into every tool, **Plain-LLM scores 49.95/35.33/33.82, outperforming
> HITS/SymPrompt/CoverUp/TestSpark**, at no higher request count than CoverUp
> (the exact request counts appear in two conflicting versions, 11,718/12,264 and
> 11,815/12,741, and are withheld until the full paper settles them).
> Note also: BOAD (**ICLR 2026**, arXiv:2512.23631, IBM Research) is real, but it
> studies **repository-level SWE issue resolution** (localization/editing/validation
> sub-agents), so it does **not** support arguments about test generation.
> **The defensible narrow claim is therefore**: *hand-crafted, tool-specific
> orchestration offers limited or no advantage over a plain strong-LLM prompt with a
> uniform repair loop* — **not** "the multi-agent paradigm has been defeated". The
> orchestration layer is kept as an ablatable research container under the ADR-0016
> promotion criterion (budget-matched positive detection delta); future exploration
> targets "automated orchestration search vs hand-crafted orchestration".
> Honest disclosure (AL5; 2026-10-08 R2 errata: two measurement artifacts
> — ADR-0021 patch-field fence residue + ADR-0029 cross-file tasks not
> materialized): across the three-seed main batch (n=261, gold
> adjudication) the detection-first protocol yields a decisive detection
> gain; **repair, after the measurement-caliber correction, replays at
> 39.31%** (correct=57 of 145 replayable rows; E1/E2 logic batches
> 54.72%) — self-repair exists but is far from the frontier and remains
> the optimization mainline (v1 calibers 35.86% / 48.11% are artifact
> lower bounds; caliber matrix in `docs/design/repair_caliber_matrix.md`;
> corrected via `make corrected-metrics` / ADR-0027/0029; ceiling
> attribution in `repair_ceiling_report.md` / ADR-0016).

## Test Status

> **The current baseline is the [BASELINE.yaml](BASELINE.yaml) file** (the machine-readable
> single source of truth). Current numbers — full-suite pass counts, static checks
> (ruff / mypy) and line/branch coverage — are **never hardcoded in this table**; they
> always come from the matching BASELINE.yaml section (`tests` / `coverage` /
> `static_checks`), which the maintenance process refreshes after each batch (see
> `CONTRIBUTING.md`, "documentation conventions"). The table below only describes the
> *status semantics*; every concrete value points at BASELINE.yaml so multiple documents
> can't drift apart.

| Metric | Status |
|------|------|
| **Total Tests** | ✅ Full collected (full dependencies) / slim environment (when chromadb/matplotlib are missing, RAG/visualization cases are auto-skipped) — current values: see the `tests` section of [BASELINE.yaml](BASELINE.yaml) (`total_passed` / `slim_environment`) |
| **Unit Tests** | ✅ Full suite: all pass, zero failures (suite duration and case count: see `tests` section of [BASELINE.yaml](BASELINE.yaml), `suite_seconds` / `total_passed` / `total_failed`); slim environment degrades gracefully via `skipif`/`importorskip` — no false-positive ERROR |
| **Code Coverage** | Total line and branch coverage: see the `coverage` section of [BASELINE.yaml](BASELINE.yaml) (`line_total_pct` / `branch_total_pct`); per-core-module coverage follows the latest CI `term-missing` output |
| **Benchmark Metrics (honest reporting)** | ⚠️ **Terminology scope (EMSE batch 2026-10-15, to prevent reviewer misreading)**: everywhere in this project, "gold adjudication" / "independent adjudication" means **independence of the adjudicating material** (held-out gold tests / gold patches) and **never human adjudication** — the entire pipeline is a zero-LLM **automated oracle verdict**. Human review (E7) is preregistered but **has not been executed** (see the E7 section of `docs/preregistration.md`), so no claim of human participation or inter-rater agreement (no Kappa) may be made anywhere. ⚠️ Main-batch numbers: the [BASELINE.yaml](BASELINE.yaml) `benchmark` section is the single source of truth. The legacy `success` metric ("generated tests pass on the final code") **must never be quoted alone** — always present it alongside the M1 triple (`detection_rate` / `repair_rate` / `false_fix_rate`). Current caliber = R-P0-2 three-seed pooled (261 tasks/arm): detection plain_llm_df 44.8% > aitester 15.8% > plain_llm 1.5%, **aitester vs df −28pp (net-negative orchestration contribution, robust under dual bounds for the 21 missing rows)**; **repair 39.31% under the corrected caliber** (ADR-0021/0029: the historical "0.0% across all arms" was two stacked measurement artifacts — patch-field fence residue and cross-file tasks not materialized; corrected replay 57/145 replayable rows; E1/E2 logic-profile batches 54.72%; the early 10-01 batch is a true zero at 0/15; corrected funnel: patch produced 94% / plausible 47% / correct 39.31%; the v1 calibers 35.86%/48.11% are artifact lower bounds, caliber matrix in `docs/design/repair_caliber_matrix.md`, ceiling attribution in `repair_ceiling_report.md` + ADR-0021/0027/0029); $/task 0.0259 vs 0.0045 (officially sourced price table); localization metrics ship alongside the result rows — `fl_at_k` (spectral Top-k line-level hit) and `localization_hit_function` (LLM reasoning localization function-level hit, since repair-engine batch I 2026-10-07, compared against the gold changed-function set, schema-isomorphic placeholder when unlocalized). Historical batch (2026-10-01, n=50) false_fix=90.0% (45/50, marginal caliber, artifact recompute; historical citation 89.8%) stands as evidence of the false-success channel (ADR-0027 re-estimation: that batch's corrected repair is a true zero at 0/15 — the evidence holds); **false_fix caliber matrix** (authoritative landing point = `docs/design/repair_caliber_matrix.md` section "false_fix 口径（权威落点）" + `experiments/emse_optimization.py::false_fix_caliber` + locking test `tests/test_emse_optimization.py`, zero-LLM recompute; the historically cited path `docs/design/false_fix_caliber_matrix.md` was never version-controlled and is NOT citable): R-P0-2 main batch marginal 59.58% (143/240) / conditional 100% (143/143), 10-batch ADR-0027 corrected caliber 87.16% (380/436, passed-measurable replay) — every external citation must carry a caliber tag; SWE-bench Lite (sqlfluff-20): of 20 attempts, 7 completed and all 7 errored out on API 429 rate limiting, 3 ended in task-level failure, 10 hit timeouts — **infrastructure failure with no valid capability conclusion** (not negative-result evidence; on the re-run list), disclosed as-is alongside statistical tests without cherry-picking (rate-limit signal count = 2 under the de-duplicated all-structured-source caliber run_notes/notes/issues = 1 each; the 404 endpoint-misconfiguration entry is booked separately — see `（工件已清除）`) |
| **Known Failures** | ✅ 0 (**normal-environment caliber**: local clean-tree 20-step gate chain rc=0, full suite failure-free (current passed / skipped / collected readings in [BASELINE.yaml](BASELINE.yaml) `tests` section). **CI status disclosed honestly (CL round, 2026-10-25)**: the 2026-10-25 push runs (the v0.8.0 sequence through e5817c0f) went red on test 3.12/3.13/3.14 — attributed to the CI "Generate static-check snapshot" step running *before* pytest: the written `docs/history/static_report_<date>.md` shifts ruff's formatted-file count by one (+1), the registration gate's recompute drifted (975 vs 976) and knocked over the two real-tree locks inside pytest; fixed (snapshot steps moved to the very end of the job + diagnostic grep tolerating xdist prefixes + a step-order regression lock), **remote confirmation rests on the new run after the CL-round fix push**; **CM round (2026-10-25) adds**: three consecutive runs after CL (`798d8c72` / `e5817c0f` / `251af095`) were still red on the 3.14 leg, at "Verify experiment artifact checksums" — that step verified `experiments/results/main_batch`, a directory withdrawn on 2026-10-24 and therefore absent in a fresh clone; locally the artifacts were on disk, so it looked green. The step now verifies three current, registered directories that carry manifests (fresh clone: **127 / 3 / 34 items match**); the new run after this push is authoritative. The three-version annotation list and the A/B evidence are in the CHANGELOG's CL-round section; RAG / dataset-download tests fixed; with optional dependencies missing the related cases `skipif`-skip rather than error. Sandbox-host caliber: 14-15 environment-capability failures under broker/ps/nested-sandbox restrictions were all attributed on 2026-10-18 and hardened with `skipif`/defensive patterns — re-runs inside the sandbox are failure-free since (counts in [BASELINE.yaml](BASELINE.yaml) `tests`; see the `tests.total_failed` note) |
| **Known Limitations (1.0.0)** | ⚠️ ① **No human adjudication**: every gold judgment is an automated oracle; the E7 human-review protocol exists but was not executed, so no claim of human scoring or Kappa may be made; ② **Single model family** (one `deepseek-flash` endpoint) — no cross-model extrapolation; ③ **The multi-seed pool was not rebuilt**: the withdrawn 261-rows-per-arm pool (2026-10-24) has no successor, so every number at that caliber is labelled historical in the paper (frozen readings: `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`, table W-1); ④ **Synthetic template drift** (30→50 patterns, six templates' gold material repaired) — archived mutation values are recomputable only from the archived artifacts; ⑤ **The scale87 `replace` arm is not the full SpecExpr specification-first route**; its null contrasts bound the document-replacement variant only; ⑥ **No capability conclusion for SWE-bench Lite** (all 20 attempts failed on API 429 / timeouts, i.e. infrastructure); ⑦ Research-side items awaiting authorisation (LLM-budget experiments / full D3 Mut@k / submission and DOI) are listed in `docs/adr/0036-v1-release-criteria.md` §3 and do not block 1.0.0. |
| **Security Audit** | ✅ No hardcoded secrets (`.env*` / `.env.local.bak` / `.private` are gitignored / removed); three-layer log redaction defense (Handler-layer SensitiveFilter/Formatter + entry-point wiring + trace JSONL side-channel redaction); APIManager log points use in-place `_redact()` (independent of entry wiring, embedded-safe); `get_status()` redacts base_url at the exit; **all three execution paths (local/venv/Docker) now uniformly scrub LLM credentials via `credential_scrub.scrub_os_environ` (dynamic pattern covering the entire `LLM_N_API_KEY` family, closing the leak path where generated code inherits host credentials)**; P0 scrub hardening (2026-09-26: numbered variants `OPENAI_(API_KEY\|BASE_URL)_\d+` + provider intermediate vars, coupled with `PROVIDER_TEMPLATES` keys to prevent list drift); redaction blind spots fixed (`APIManager.call` all-node-failure exception exit uniformly `_redact`-ed, `config_manager.add_llm_config` rejects newline/`#` var-value injection, `retry_with_backoff` log lazy-redacted, `SensitiveFormatter` fallback takes the pure-regex path first); LLM file cache logging is a known acceptable risk (local trusted domain, not committed to git; cache writes are now atomic replace) |
| **Latest Optimization** | ✅ **2026-10-26 CU round (zero LLM, $0; a document-command executability gate + cover-letter/body frontier synchronisation; readings in [BASELINE.yaml](BASELINE.yaml))** --- (1) **criterionised** "the document points at a non-existent artefact": new gate `scripts/gates/check_doc_commands.py` (blocking CI chain, 9 new cases; the caliber pins two classes of false positive) ｜ (2) the first full census found **zero** breakages (39 documents / 124 references) --- a negative result no artifact had recorded ｜ (3) cover letter and body frontier synchronisation (local artifact): the letter now matches the body's nine frontier papers, citing three primary works by arXiv id only ｜ (4) seven census numbers move by +1, and the self-check notes that an uncommitted gate is invisible to CI's clone --- **writing a gate is not the same as CI enforcing it** ｜ full-suite and gate readings in BASELINE
| **Core Module Coverage** | ✅ Per-module line coverage / branch coverage / core routing gates use [BASELINE.yaml](BASELINE.yaml) `coverage.line_core_modules`, `coverage.branch_core_routing`, `coverage.line_total_pct` and `branch_total_pct` as the single source of truth (this row no longer hardcodes numbers — the previously hardcoded values had drifted from the artifacts and were already stale in round K) |
| **Code Style** | ✅ Ruff checks all pass (`ruff check` + `ruff format --check`, CI pinned to 0.16.3) + mypy 0 errors across the repo (source-file count and version pinning: see [BASELINE.yaml](BASELINE.yaml) `static_checks` section, `mypy_source_files`); historical lint-cleanup narratives are archived in [CHANGELOG.en.md](CHANGELOG.en.md) |
| **Historical Milestone (2026-10-07)** | ✅ repair-engine batch XIV (historical snapshot, not the current baseline; for current status see the "Latest optimization" row above and [BASELINE.yaml](BASELINE.yaml)) (external-report net-new harvest per ADR-0028 — FL Top-k constraint gate [`patch_changed_functions` with insert anchoring × Top-3 localization candidates intersection, hit_rank; result rows emit `fl_constraint_verdict`/`fl_constraint_hit_rank`/`fl_constraint_changed_functions`; ADR-0024's generation-side dominance becomes row-level verifiable] + Self-Repair Trap observer [`oracle_quality_history` per-generation quality snapshots + `detect_self_repair_trap` three-signal core; three result-row keys] + Frame Lifetime Trace design input [docs/design/frame_lifetime_trace.md, activation gated on the Debugger-split batch] + BASELINE test-chain errata [pre-written count distortions for batches VII–XIII reconciled]); previously the same day batches VII–XIII (repair=0 measurement-artifact resolution [corrected calibers 35.9%/48.1%] + test-hacking guard + statistical-report trio + counterfactual FL upper bound + ORACLE_CONTEXT_TIER ablation tier + interaction-centric attribution + corrected-caliber re-estimation closure, see CHANGELOG); previously the same day batch VI (--staging-dir batch-run operations — snapshot before the run, move new artifacts out afterwards so sequential multi-seed runs no longer trip the clean-tree gate [codifying the twice-manual E2 workaround; --skip-stats early exit also stages out; path-traversal defense]; plus `make cpr-idr` as the IDR/CPR + abstention-view report entry); previously the same day batch V (ADR-0020: patch abstention gate observability layer — five-signal decision core; result rows emit `patch_abstained`/`patch_abstain_signals`; the CPR/IDR abstention view replayed over existing artifacts shows 392 of the 443 passing rows [88.5%] would be suppressed with precision 1.0; blocking tier Proposed pending A/B); previously the same day batch IV (ADR-0019: deterministic-first repair routing — three zero-LLM conservative transformers + AST validation gate, skipping the LLM round on a hit with a retry sentinel); previously the same day batch III (ADR-0018: structured edit intents + deterministic landing + the AC2 over-red counter fix); previously the same day batch II (Top-3 ranked localization + Hit@3/MRR + the offline CPR/IDR caliber [IDR=27.78%] + ADR-0017 citation fixes); previously the same day batch I (paradigm pivot to the repair-engine route; standalone FaultLocalizer; `localization_hit_function` first measured); previously the same day batch AS (first end-to-end release-build verification + PEP 639); earlier batches see CHANGELOG; test counts: see the `tests` section of [BASELINE.yaml](BASELINE.yaml) |

For more details, see [CHANGELOG.md](CHANGELOG.md), [QUICKSTART.md](QUICKSTART.md), [docs/api_reference.md](docs/api_reference.md), [docs/usage_examples.md](docs/usage_examples.md).

## Development Tools

### Lint and Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) for code checking and formatting (CI pinned to `0.16.3`, consistent with `requirements.lock`, to avoid upstream releases drifting the formatting gate):

```bash
# Install ruff (pin the same version as CI)
pip install "ruff==0.16.3"

# Check code
ruff check .

# Auto-fix fixable issues
ruff check --fix .

# Format code
ruff format .

# Check formatting (without modifying)
ruff format --check .
```

### Pre-commit Hooks

Pre-commit hooks are recommended to run checks automatically before commits:

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Manually run all hooks
pre-commit run --all-files
```

### CI/CD

The project is configured with GitHub Actions continuous integration, supporting:
- Multi-Python-version testing (3.12 / 3.13 / 3.14, matching the `python_ci_matrix` in [BASELINE.yaml](BASELINE.yaml); the lower bound is determined by locked dependencies: scipy requires ≥3.12)
- Ruff lint checks
- pytest tests + coverage reports
- Dependency security scanning (pip-audit; chromadb 1.5.9 hits 5 known vulnerabilities (PYSEC-2026-311 counted twice + PYSEC-2026-3813/3814/3815), explicitly exempted because no fixed version is yet available on PyPI; see the ci.yml comments and CHANGELOG for details)
- Consistency validation between requirements and requirements.lock (scripts/gates/check_lock_sync.py)
- Test failure diagnostic annotations: when a test step fails, the list of FAILED/ERROR cases is automatically written as GitHub annotations (readable via the check-runs annotations API, no need for admin to download logs)

### Test Commands

```bash
# Run all unit tests (see BASELINE.yaml `tests` for current totals; when chromadb/matplotlib are missing, RAG/visualization cases are auto-skipped)
.venv/bin/python -m pytest tests/ -v

# Run tests with coverage
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run only workflow integration tests (end-to-end orchestration)
.venv/bin/python -m pytest tests/test_workflow.py tests/test_workflow_extended.py -v

# Run only dataset loader tests
.venv/bin/python -m pytest tests/test_dataset_loader.py tests/test_dataset_loader_extended.py -v
```

## Quick Start

```bash
# 0. Create a virtual environment (Python 3.12+ recommended; the locked dependency scipy requires ≥3.12)
python3 -m venv .venv
source .venv/bin/activate

# 1. Install dependencies
pip install -r requirements.txt
# Wheel / non-repo installs only: install the execution extra to run the Executor and benchmarks
# pip install "aitester[execution]"   # pytest + pytest-cov + pytest-timeout
# A default `pip install aitester` does NOT include execution tools; when modules are missing the
# Executor returns error_info.type=execution_dependency_missing and points to this command

# 2. Configure environment variables
cp .env.example .env
# Edit .env and fill in the API Key and other information

# 2.5 Zero-LLM self-check (environment/config + zero-LLM subset of the feature matrix; no API quota consumed)
#     Also supports --json (pure JSON on stdout) / --groups budget,executor / --strict
python main.py doctor

# 3. Initialize the database (optional, if you need to persist experiment data)
python init_db.py

# 4. Run a single-file test
python main.py run examples/calculator.py --func divide

# 5. Batch benchmark (built-in example dataset, three baseline comparisons)
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. Run the full system only + limit task count
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. Ablation experiment: enable Planner only
ENABLE_PLANNER=true ENABLE_DEBUGGER=false python experiments/run_benchmark.py --dataset examples

# 8. Run synthetic dataset benchmark (no external download needed, customizable scale)
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --baselines aitester,plain_llm,single_agent

# 9. Visualize experiment results (with statistical significance tests)
python experiments/visualize_results.py
python experiments/visualize_results.py --results-dir experiments/results/synthetic_full

# 10. Run the benchmark in parallel (speeds up multi-task processing)
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 20

# 11. Specify parallelism with the --parallel option
python experiments/run_benchmark.py --dataset examples --parallel 4

# 12. Set a global timeout with the --timeout option
python main.py run examples/calculator.py --func divide --timeout 120

# 13. Benchmark results are emitted as JSON (structured JSON goes directly to stdout, no extra option needed)
python experiments/run_benchmark.py --dataset examples
```

## Performance Optimization Notes

### RAG Retriever Singleton

The system implements a **lazy-loading singleton pattern** for the RAG retriever, initializing the ChromaDB client only once during the entire workflow execution, avoiding the overhead of repeatedly loading the embedding model (~100MB) and opening the vector index.

**Performance gain**: saves 2-6 seconds of initialization time per task.

**Technical implementation**: the `get_rag_retriever()` function in `src/graph/rag.py` (re-exported via `workflow.py` to preserve the legacy import path).

### LLM File Cache (saves tokens)

The LLM calls in `base_agent` are wired to a **persistent file cache** (`*.json` files in the cache directory, named by `md5(prompt + system_prompt)`). Identical input hits the cache from the second call onward, consuming no more tokens — for model providers that "stop once the free quota is used up", this significantly extends usable time.

- **Enabled by default**; set the environment variable `AITESTER_LLM_CACHE=0` to disable it; the cache directory can be overridden with `AITESTER_LLM_CACHE_DIR`.
- **Cache directory** (since the 2026-10-05 review batch): defaults to `~/.cache/aitester/llm/` (`XDG_CACHE_HOME` takes precedence) — the runtime cache no longer writes into the source tree `src/cache/`; set `AITESTER_LLM_CACHE_DIR=<repo>/src/cache` explicitly if you need to keep using a legacy cache.
- **Only successful responses are cached**: failed calls (e.g. 403 quota exhausted) are not written to the cache.
- The cache is a local optimization artifact and is not committed to version control (directory mode 0700 / file mode 0600, guarding against cross-user cache poisoning).

```bash
export AITESTER_LLM_CACHE=0      # Temporarily disable the cache (when you need to "regenerate with a different approach")
rm -rf ~/.cache/aitester/llm     # Clear the cache so all prompts call the LLM again
```

### LLM Client Reuse (shared connection pool)

The LLM clients in `base_agent` are now **reused** per configuration, avoiding a new client (including its underlying HTTP connection pool) on every call:

- **OpenAI-compatible path** (`ChatOpenAI`): cached by `(model_name, temperature, api_key, base_url)`, capped at 16 entries (FIFO eviction).

**Performance gain**: multiple LLM calls with the same configuration share a connection pool, eliminating repeated connection-establishment overhead; under concurrent multi-task execution the connection pool state is consistent and behavior is more predictable.

**Technical implementation**: `_get_or_create_chat_client()` in `src/agents/base_agent.py`.

### Model Quota Probing (scripts/tools/check_quota.py)

Probes whether each configured model is currently "alive / free quota exhausted (403) / rate-limited / key invalid / model not found"; each model receives only a 1-token request, and **no secret is ever printed**:

```bash
.venv/bin/python scripts/tools/check_quota.py                      # Probe all LLMs configured in .env.local
.venv/bin/python scripts/tools/check_quota.py --provider deepseek  # Scan all models in a provider directory
.venv/bin/python scripts/tools/check_quota.py --provider deepseek --models deepseek-flash
.venv/bin/python scripts/tools/check_quota.py --dry-run           # Only list the targets to be probed, send no requests
```

### LLM Call Timeout Configuration

The `LLM_TIMEOUT` configuration item controls the timeout for a single LLM call, preventing a task from hanging when the API responds too slowly.

```bash
# .env file configuration
LLM_TIMEOUT=60          # Single LLM call timeout (seconds), default 60
LLM_RETRY_WAIT=30       # LLM retry wait time (seconds), default 30
EXECUTION_TIMEOUT=30    # pytest execution timeout (seconds), default 30
```

### LLM Structured-Output Hardening (JSON Output and parse-layer repair, 2026-10-14)

Structured-output hardening configured per DeepSeek official docs (ADR-0031;
log triage shows most "execution failures/timeouts" are executor retries and
test-side guards — the real defect class is structured-output parse failure):

- **`LLM_JSON_MODE` (on by default)**: seven JSON-contract call sites (Planner
  plan / Debugger patch·strict-retry·critic·break-cases·defect-classification /
  FaultLocalizer localization) bind the official JSON Output (`response_format={"type":"json_object"}`,
  guaranteeing valid JSON strings); set `off` for the historical
  byte-identical caliber (old-batch replay). Recorded in per-batch provenance
  `env_snapshot` (auditable).
- **Numeric-expression parse repair**: Python numeric expressions in JSON
  value positions (`10**18` / `10**18+1` / `10_000`) are converted to
  equivalent JSON numbers by the parse layer via bounded evaluation (no eval,
  exponent/digit bounds, in-string guard) — fixing the "leaf fallback
  silently returns a wrong fragment" M10 misdiagnosis (the LLM did emit
  complete JSON).
- **`finish_reason` guard**: responses with `length` (truncation) /
  `insufficient_system_resource` are retried as recoverable failures instead
  of feeding truncated content downstream.

### Parallel Execution (BENCHMARK_PARALLELISM)

Multi-threaded parallel execution of multiple benchmark tasks is supported, significantly reducing total wall time for large test batches.

```bash
# Run in parallel with 4 threads (environment variable approach)
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py --dataset synthetic --task-count 50

# Use the --parallel option (command-line approach)
python experiments/run_benchmark.py --dataset synthetic --task-count 50 --parallel 4

# Serial execution (default)
python experiments/run_benchmark.py --dataset synthetic --task-count 50
```

**Note**: parallel execution requires a dedicated API Key per thread; API Key rotation can be implemented through multiple configuration groups such as `LLM_1_*`, `LLM_2_*`, etc.

See the [Performance Tuning Guide](docs/performance_guide.md) for more details.

### Timeout Control (--timeout)

The timeout for a single test execution is controlled by the `--timeout` option or the `EXECUTION_TIMEOUT` environment variable, preventing tasks from hanging.

```bash
# Specify a timeout (seconds) on the command line
python main.py run examples/calculator.py --func divide --timeout 120

# Or via environment variable
EXECUTION_TIMEOUT=120 python main.py run examples/calculator.py --func divide
```

On timeout the test is force-terminated, its status is marked `timeout`, and the Debugger can perform targeted repair for timeout scenarios.

### JSON Output (default behavior for benchmark results)

`run_benchmark.py` always prints the summary results to stdout as structured JSON on exit (it also writes `benchmark_<dataset>_<timestamp>.json` under `--output-dir`; with `--save-state`, per-stage state is additionally saved to `raw/<task_id>/`). It can be piped directly to tools like `jq` for programmatic processing. Note: this script has no `--json` switch — JSON output is the default and only result output form.

```bash
# Structured JSON results go directly to stdout
python experiments/run_benchmark.py --dataset examples

# Combine with --output-dir to save the result JSON to a directory
python experiments/run_benchmark.py --dataset examples --output-dir ./results
```

The JSON output contains complete result statistics, per-baseline detailed data, and performance metrics, ready for downstream analysis scripts.

See the [Performance Tuning Guide](docs/performance_guide.md) for more details.

## Project Structure

```
AITester/
├── src/                              # Core source code
│   ├── agents/                       # Multi-agent modules
│   │   ├── base_agent.py             # Agent base class (LLM calls + file cache + JSON parsing; client factory split out to llm_client.py)
│   │   ├── llm_client.py             # LLM client utility functions (ChatOpenAI factory + module-level connection pool cache, split in 0.1)
│   │   ├── planner.py                # Test planner (includes logic-driven chain of thought)
│   │   ├── generator.py              # Test code generator (with RAG augmentation support)
│   │   ├── executor.py               # Test executor (class body + local execution orchestration; import fix / result parsing / sandbox & Docker modes / subprocess runtime split out into executor_* submodules)
│   │   ├── executor_imports.py       # Import-path auto-fixing (module-name extraction / sys.path injection / similar-name replacement, split in 0.1)
│   │   ├── executor_modes.py         # venv sandbox + Docker isolation execution modes (split in 0.1)
│   │   ├── executor_repo.py          # P0 repo-level executor RepoExecutor (SWE-bench official criterion: clone+checkout+pip install -e env cache + venv isolation + gold test_patch before/after FAIL_TO_PASS/PASS_TO_PASS measurement, off by default)
│   │   ├── executor_output.py        # Result parsing (coverage / failed cases / error info, split in 0.1)
│   │   ├── executor_runtime.py       # Subprocess running, retry & temp resource cleanup (split in 0.1)
│   │   ├── debugger.py               # Debugging repair agent (hierarchical error repair)
│   │   ├── fl_spectral.py            # Ochiai spectral fault localization (zero LLM, Top-k suspicious-line corroboration; since R8)
│   │   ├── fault_localizer.py        # RGFL-style LLM reasoning fault localization (repair-engine phase one, localization-only; FAULT_LOCALIZER_ENABLE on by default)
│   │   └── error_classifier.py       # Error type classifier (rule-based matching)
│   ├── api/                          # API configuration management
│   │   ├── api_manager.py            # Multi-LLM config CRUD (.env.local / llm_configs.json) + circuit breaker/routing
│   │   └── api_health.py             # API health status and routing strategy data models (APIHealth/APIManagerConfig/RotationStrategy)
│   ├── config/                       # Configuration management
│   │   ├── config_manager.py         # LLM config add/remove/query
│   │   └── config_generator.py       # .env / llm_configs template generation
│   ├── datasets/                     # Dataset loading layer
│   │   ├── dataset_loader.py         # SWE-bench loader + data model / abstract base / factory (Defects4J & InMemory subclasses split out)
│   │   ├── dataset_defects4j.py      # Defects4J-Python loader (split in 0.1)
│   │   ├── dataset_inmemory.py       # Built-in sample dataset (split in 0.1)
│   │   └── synthetic_dataset.py      # Synthetic dataset generator (local generation)
│   ├── cli/                          # Command-line interface (click command groups + rich output)
│   │   ├── app.py                    # CLI command definitions and task execution
│   │   └── output.py                 # ANSI/Rich terminal output utilities
│   ├── utils/                        # Shared utilities
│   │   ├── exceptions.py             # Unified exception hierarchy
│   │   ├── helpers.py                # Regex / JSON / code-block extraction utilities
│   │   └── logging_utils.py          # Logging utilities
│   ├── tools/                        # Tool function modules
│   │   ├── code_analyzer.py          # AST code analysis (exact replacement, avoids regex false matches)
│   │   ├── patch_applier.py          # Patch application (supports whole-file and single-function modes)
│   │   ├── code_context.py           # AST smart extraction (P0 large-file context optimization)
│   │   ├── dependency.py             # Dependency detection and venv cache management (P1 execution isolation) + 4.4 hit-rate stats/cleanup
│   │   ├── multi_candidate.py        # Multi-candidate patch generation and validation filtering (3.1, off by default)
│   │   └── cross_file.py             # 3.5 cross-file repair (coordinator-proposer architecture, off by default)
│   ├── graph/                        # Workflow orchestration modules
│   │   ├── workflow.py               # LangGraph workflow graph (supports ablation switches; node registration and RAG wiring)
│   │   ├── nodes.py                  # Node function implementations (_planner/_generator/_executor/_cross_file_analyzer + orchestration nodes; large
│   │   │                               clusters split out per batches S7/S4 into trace_reward/flags/agents_cache/debugger/patch_io,
│   │   │                               all re-exported to preserve historical import paths)
│   │   ├── trace_reward.py           # R3 S7: 6 pure trajectory/reward/iteration-strategy functions (split from nodes.py, re-export preserved)
│   │   ├── flags.py                  # R3 S7: switch-reading function cluster (split from nodes.py, re-export preserved)
│   │   ├── agents_cache.py           # R3 S7: Executor / generic Agent instance-reuse cache (split from nodes.py, re-export preserved)
│   │   ├── debugger.py               # R3 S7: _diagnosis_node/_debugger_node node implementations (split from nodes.py, re-export preserved)
│   │   ├── patch_io.py               # R4 S4: patch-application safety core (path allowlist + atomic write + multi-candidate selection + safe write + snapshot rollback, split from nodes.py, re-export preserved)
│   │   ├── rag.py                    # RAG retriever singleton management (get_rag_retriever, re-exported via workflow.py)
│   │   ├── tracing.py                # Tracing layer wiring (task-level JSONL sessions, re-exported via workflow.py)
│   │   ├── state.py                  # Global state definitions (TypedDict) + create_initial_state factory (single construction point)
│   │   ├── token_usage.py            # Thread-local LLM token usage stats (P0 efficiency metric)
│   │   └── llm_cache.py             # LLM in-memory LRU cache (optional, with hit statistics)
│   ├── observability/                # Structured observability (4.1)
│   │   └── trace.py                  # JSONL node-level tracing (off by default, enabled via AITESTER_TRACE_DIR)
│   ├── prompts/                      # Prompt templates
│   │   └── templates.py              # Planner/Generator/Debugger system prompts (PLANNER_SYSTEM_PROMPT, etc.)
│   ├── db/                           # Database module
│   │   └── mysql_client.py           # MySQL singleton client (tasks, tests, repair records)
│   ├── rag/                          # Retrieval-augmented generation module
│   │   └── retriever.py              # ChromaDB vector retriever (test cases and repair cases)
│   ├── reports/                      # Report generation
│   │   └── generator.py             # Experiment result reports
│   └── experiments/                  # Experiment analysis
│       └── analysis.py               # Statistical tests and result analysis
├── experiments/                      # Experiment script modules
│   ├── run_benchmark.py              # Batch benchmark (multi-baseline comparison + ablation experiments + fairness token output)
│   ├── visualize_results.py          # Result visualization (bar charts + detailed tables + statistical tests)
│   ├── analyze_results.py            # Result analysis script (4.3 + 1.1/1.2/1.3/3.2/4.4: Markdown summary + RAG auto-summary + repair convergence/quality proxy + smell detection + mutation score + boundary coverage + execution trace + cache hit rate, legacy JSON fallback)
│   ├── compare_failures.py           # Failure-flip task comparison (Planner/Debugger/environment attribution + 5.3 cross-batch failure-mode comparison)
│   ├── analyze_failures.py           # Failure case clustering report (for technical review)
│   ├── mutation_testing.py           # 1.2 built-in mutation generator (AST-level 7 mutant classes + mutation_score_from_details aggregation; kill judging per official pytest exit codes, 2026-09-26)
│   ├── contamination_check.py        # 2.1 SWE-bench data contamination check (token-level Jaccard overlap)
│   ├── difficulty_stratification.py # 2.2 task difficulty stratification analysis
│   ├── run_large_scale.py            # Large-scale experiment entry point
│   ├── run_statistical_test.py       # Statistical test entry point
│   └── statistical_analysis.py       # Statistical analysis utilities
├── reproduce.sh                    # One-click experiment reproduction script (quick/full modes)
├── tests/                            # Unit tests
│   ├── test_code_analyzer.py
│   ├── test_error_classifier.py
│   ├── test_patch_applier.py
│   └── test_dataset_loader.py        # Dataset loader tests (new)
├── docs/                             # Documentation
│   ├── algorithm_design.md           # Algorithm design and theoretical description
│   ├── api_reference.md              # API reference
│   ├── usage_examples.md             # Usage examples
│   ├── performance_guide.md          # Performance tuning guide (including profiling benchmarks)
│   ├── failure_analysis.md           # Failure case analysis (historical snapshot)
│   └── history/                      # Archived historical round work records
│       ├── optimization_plan.md
│       └── optimization_report.md
├── examples/                         # Example code under test (with known bugs)
│   ├── calculator.py                 # Calculator example (division by zero, negative factorial bugs)
│   ├── buggy_library.py              # Algorithm library example (binary search, sort-merge, etc.)
│   └── string_utils.py               # String utilities example (palindrome, Caesar cipher, etc.)
├── scripts/                          # Repository-level scripts (see scripts/README.md)
│   ├── gates/                        # CI / pre-commit blocking checks (27 scripts, recompute via `ls scripts/gates/*.py | wc -l`; 25 unique scripts / 28 call sites wired into ci.yml, the other 2 in dedicated workflows such as perf.yml)
│   │   ├── check_baseline.py         # BASELINE.yaml sanity
│   │   ├── check_lock_sync.py        # requirements.txt ↔ requirements.lock sync
│   │   ├── check_branch_coverage.py  # Core routing branch-coverage gate
│   │   └── ...                       # Bilingual pairing / citations / artifact tracking / coverage ratchet, etc.
│   └── tools/                        # Ops / generators / experiment helpers (17; non-blocking)
│       ├── bootstrap_dev.sh          # Developer environment bootstrap
│       ├── smoke_test.sh             # Pre-release smoke test
│       └── performance_benchmark.py  # Performance benchmark
├── main.py                           # CLI entry point (thin wrapper, implementation in src/cli/)
├── config.py                         # Global configuration (includes ablation experiment switches)
├── init_db.py                        # Database initialization script
├── setup.py                          # Package management configuration
├── requirements.txt                  # Python dependency list
├── Dockerfile                        # Docker image definition
└── .env.example                      # Environment variable template
```

## Core Methods

### 1. Logic-driven Chain-of-Thought
Before outputting the test plan, the Planner performs explicit analysis of the function's **input domain, output domain, preconditions, postconditions, and boundary cases**, guiding the Generator to produce test cases with logic coverage.

**Technical implementation**:
- The `PlannerAgent.plan()` method in [src/agents/planner.py](src/agents/planner.py)
- The `PLANNER_SYSTEM_PROMPT` in [src/prompts/templates.py](src/prompts/templates.py)

### 2. Hierarchical Error Repair Strategy
**Localization first (2026-10-07 repair-engine paradigm shift)**: the repair pipeline is upgraded to the three stages "**localization → synthesis → verification**", with localization promoted from a Debugger by-product to an independently quantifiable first stage — the spectral channel (Ochiai Top-k, zero LLM) supplies line-level suspiciousness corroboration while the reasoning channel (RGFL-style structured LLM localization: function / line range / confidence / rationale) localizes without repairing; the fused result is injected into the Debugger prompt side by side with the spectral section. LLM failure / JSON parse failure degrade conservatively to None — no fabricated localization, no blocking of repair. Localization quality is quantified by standalone metrics: `localization_hit_function` (the LLM-localized function ∈ the gold changed-function set) and `fl_at_k` (spectral line-level Top-k hit).

**Technical implementation**:
- `FaultLocalizerAgent.localize()` (reasoning localization) plus `gold_changed_functions()` / `localization_hit()` (gold-caliber extraction and function-level hit adjudication) in [src/agents/fault_localizer.py](src/agents/fault_localizer.py)
- The spectral localization measurement layer (Ochiai Top-k) in [src/agents/fl_spectral.py](src/agents/fl_spectral.py)
- `_debugger_node` in [src/graph/nodes.py](src/graph/nodes.py) (dual-channel fusion wiring; the localization result is written to `state["llm_localization"]` for consumption by the experiment layer)

Test failures are classified into seventeen categories: **LLM response format anomaly (llm_format_error), LLM empty response (llm_empty_response, P0 4.1 sub-class), LLM JSON parse failure (llm_json_parse_failed, P0 4.1 sub-class), import failure (import_error), syntax error (syntax), type mismatch (type_error), index out of range (index_error), assertion failure (assertion), test logic error (logic_error), runtime exception (runtime), timeout (timeout), unknown (unknown), patch rejected by safety guard (patch_validation_failed), all-empty RAG retrieval (rag_retrieval_empty), missing execution trace (execution_trace_missing), all multi-candidate patches rejected by static screening (multi_candidate_all_rejected), and patch syntactically invalid after resampling (patch_syntax_invalid, resample-exhaustion marker added in the 2026-09-27 round-11 batch)**. Each category uses a differentiated repair strategy (P2 refinement: the import/type/logic categories were split out from the older five-category set; 1.2 residual: LLM_FORMAT_ERROR and INDEX_ERROR split out of UNKNOWN; 1.1 status refinement: PATCH_VALIDATION_FAILED and RAG_RETRIEVAL_EMPTY are flow-status categories; 5.2 ongoing refinement: EXECUTION_TRACE_MISSING and MULTI_CANDIDATE_ALL_REJECTED are multi-candidate/trace flow categories; P0 4.1 sub-class split: LLM_EMPTY_RESPONSE and LLM_JSON_PARSE_FAILED are precise sub-classes of LLM_FORMAT_ERROR, classified by `ErrorClassifier.classify_llm_response()` after the LLM response arrives and before JSON parsing — a strict-prompt retry is triggered on hit and the raw response snippet is recorded, without going through `classify()` text regex; successful tasks are returned as-is).

**Technical implementation**:
- The `ErrorClassifier` class in [src/agents/error_classifier.py](src/agents/error_classifier.py) (rule-based matching)
- The `DebuggerAgent.debug()` method in [src/agents/debugger.py](src/agents/debugger.py)
- The `DEBUGGER_SYSTEM_PROMPT` in [src/prompts/templates.py](src/prompts/templates.py)

### 3. AST-Based Precise Code Replacement
The `ast` module is used for function parsing and replacement, avoiding false matches from regex in scenarios with nested functions or same-named functions.

**Technical implementation**:
- The `replace_function_code()` function in [src/tools/code_analyzer.py](src/tools/code_analyzer.py)
- The `apply_patch_to_code()` function in [src/tools/patch_applier.py](src/tools/patch_applier.py)

### 4. Retrieval-Augmented Generation (RAG)
ChromaDB stores historically successful test cases and repair patches; before the Generator and Debugger produce output, similar cases are retrieved as reference.

**Technical implementation**:
- The `TestCaseRetriever` class in [src/rag/retriever.py](src/rag/retriever.py)
- Enabled/disabled via the `ENABLE_RAG` flag in [src/graph/workflow.py](src/graph/workflow.py)

### 5. Multi-Baseline Comparison and Ablation Experiments (new)
Four experiment configurations are supported for one-click comparison of individual component contributions:

| Baseline Name | Configuration | Description |
|---------|------|------|
| `aitester` | Both Planner+Debugger enabled | Full multi-agent system |
| `plain_llm` | Both Planner+Debugger disabled | Pure LLM single-call baseline |
| `single_agent` | Planner+Debugger merged into a single call | Single-agent comparison baseline |

**Ablation switches** (defaults are read from [config.py](config.py) and can be overridden via environment variables injected through `.env`; `.env` is already in `.gitignore` and not committed):
```bash
ENABLE_PLANNER=true      # Enable Planner (default true)
ENABLE_DEBUGGER=true     # Enable the Debugger repair loop (default true)
ENABLE_RAG=false         # Enable RAG retrieval augmentation (default false)
```

### 5.1 Multi-Candidate Patches and Validation (3.1, off by default)
The "one bad step and every step after is wrong" risk of single-patch repair: when the LLM occasionally emits syntactically incomplete patches, deletes functions by mistake, or edits the wrong lines, the bad patch pollutes target_code and carries an incorrect diagnosis into the next round, wasting the repair budget. The multi-candidate patch strategy generates N candidates within the same round (perspective-perturbed prompts steer each candidate down a different repair path: minimal change / root-cause fix / defensive fix), a static filter (`ast.parse` syntax + function integrity + 10% length safety) eliminates bad candidates, optional execution validation runs tests per candidate and picks the one with the highest pass rate/coverage, and only a selected candidate that strictly beats the original code is committed.

**Technical implementation**:
- `generate_candidates()` / `select_best_candidate()` / `static_validate_patch()` in [src/tools/multi_candidate.py](src/tools/multi_candidate.py)
- Wired in via `_patch_applier_node` in [src/graph/workflow.py](src/graph/workflow.py); `ENABLE_MULTI_CANDIDATE_PATCH` defaults to false to preserve historical experiment semantics; when no valid candidate exists it automatically falls back to a single patch

### 5.2 Structured Observability (4.1, off by default)
Append-only JSONL records each agent node's input/output, decision path (debug/done/regenerate), token consumption, and wall-clock time per task, enabling per-agent replay for experiment analysis (logs are for human reading, get redaction-sampled, and cannot support structured replay). When `AITESTER_TRACE_DIR` is unset, everything is a no-op with zero performance tax; when set, traces are written as `<task_uuid>.trace.jsonl` and pass through redaction.

**Technical implementation**:
- The `TraceSession` class in [src/observability/trace.py](src/observability/trace.py)
- Per-node recording in the workflow nodes (planner/generator/executor/debugger/patch_applier/_should_debug); the benchmark entry point and CLI record task_end in a finally block

### 5.3 Cost-Aware Routing (3.4 + 3.2 configurable threshold)
The `COST_AWARE` strategy in `APIManager` ranks by a composite score of "success rate 50% + 1/cost 50%", so failover avoids shifting the full traffic onto expensive providers; when failing over to an expensive node with `cost_weight >= threshold` (`APIManagerConfig.cost_alert_threshold`, default 2.0, configurable in 3.2 — if the threshold is too low and false alarms are frequent, raise it to e.g. 3.0/5.0; if you are more cost-sensitive, lower it; no code changes needed) a WARNING cost alert is logged (`cost_alert_enabled` can turn it off; the alert message prints the configured threshold to avoid misleading tuning). `LLMConfig.cost_weight` is read via `LLM_N_COST_WEIGHT` (0.1~1000; unset defaults to 0.0 = no information, APIManager falls back to the 1.0 baseline; `APIManagerConfig.node_cost_weights` supports an explicit mapping override).

**Technical implementation**:
- `RotationStrategy.COST_AWARE` / `_select_node_cost_aware()` / the cost alert branch in [src/api/api_manager.py](src/api/api_manager.py)

### 5.4 RAG Included in Main Experiments (2.3)
`reproduce.sh` now defaults RAG to **off** after **W7 (2026-10-05 review landing, negative-evidence-driven)** (RAG A/B measured token +40.7% negative with no success-rate gain; see `docs/experiment_ab_results_2026-09-28.md`); run a comparison explicitly with `--enable-rag`. The `--no-rag` / `--enable-rag` flags of `run_benchmark.py` both override `config.ENABLE_RAG`.

### 5.5 Result Analysis Script (4.3 + 1.1/1.2 first-round metric extensions)
`experiments/analyze_results.py` extracts from the benchmark JSON: success rate / coverage / iteration count distribution / token efficiency / per-baseline failure-reason distribution (1.2 refined categories counted separately) / RAG retrieval quality / repair convergence efficiency (first-attempt success rate, iteration and time statistics for successful vs failed tasks) / multi-dimensional quality proxies (coverage and time proxies, optional `generated_test` assertion-line-count proxy, failure category Top N); it prints a Markdown summary to the terminal and writes `analysis_summary.md`; when legacy JSON lacks `token_metrics`/`rag_metrics`/`generated_test` keys, it automatically falls back or degrades gracefully without crashing.

```bash
# Analyze the most recent benchmark results
python experiments/analyze_results.py --results-dir experiments/results

# Analyze a specific file
python experiments/analyze_results.py --input experiments/results/benchmark_xxx.json
```

### 5.6 Circuit Breaker Cooldown + Half-Open Probing (4.1 + 4.2)
The `APIManager`'s circuit breaker enters a cooldown period (`APIManagerConfig.circuit_cooldown_seconds`, default 60s) after a node's consecutive failures reach `max_consecutive_failures`. During the cooldown, even if the health-check thread flips `is_healthy` back to True, the routing layer (`get_healthy_nodes()` and the backup candidates in `_build_node_list`) still skips that node, avoiding re-hitting a dead provider with traffic (wasting time and tokens); `mark_success` resets the circuit breaker, and `get_status()` exposes `circuit_open_remaining_s` and `circuit_state` (closed / open / half_open) fields for monitoring.

The 4.2 half-open probe (on by default, `APIManagerConfig.enable_half_open_probe=True`): when the cooldown expires, the node does not immediately resume full routing but enters a "half-open" window — the node becomes a routing candidate (`in_circuit_half_open`) carrying one probe request; a successful probe closes the circuit breaker and restores full routing, while a failed one re-opens a half-cooldown (`min(cooldown/2, half_open_probe_penalty_cap_seconds)`, default cap 30s), preventing a dead provider from being repeatedly hit. The success and exception branches of `call()` and `check_health()` uniformly consume the probe result; setting `enable_half_open_probe=False` reverts to the 4.1 pass-through behavior, for comparison experiments.

### 5.7 SWE-bench Source Export Automation (2.1)
The official SWE-bench JSONL has no `instance_code` field (a task only contains patch text). A new `scripts/tools/export_swe_bench_source.py` automates the fill-in: it reads the downloaded JSONL, extracts the first non-test target file from the patch's `+++ b/<path>`, and exports it read-only via `git show <base_commit>:<path>` (without polluting the working tree), producing an enrichment JSONL in `SWE_BENCH_ENRICHMENT` format; it supports `--instance-ids` (comma-separated or @file, combined with the missing-list output of check-dataset for batch fill-in), `--dry-run`, and `--limit`. `SWEBenchDataset` adds `tasks_missing_source()` (identifies tasks whose instance_code falls back to issue text); the `check-dataset` quality report outputs the list of instance_ids missing source code and fill-in guidance.

```bash
# Fill in all missing source (requires the SWE-bench repo cache + git)
python scripts/tools/export_swe_bench_source.py --dry-run          # Inspect the export plan first
python scripts/tools/export_swe_bench_source.py --instance-ids @missing_ids.txt
# Load the enrichment (auto-merged into tasks' instance_code)
python main.py check-dataset swe_bench
```

### 5.8 Cross-File Repair (3.5, off by default)
Empirical observation (**not first-hand verified**; see `docs/citation_allowlist.txt`): a non-trivial share of tasks in real datasets (SWE-bench / Defects4J) require multi-file changes — this project does not rely on that share as evidence. Coordinator-proposer architecture: the `cross_file_analyzer` node (enabled with `CROSS_FILE_ENABLE=true`) is inserted between `executor → debugger`, performing AST cross-file import dependency analysis (single-entry view) and writing the dependency edges into `state["cross_file_deps"]`; the cross-file branch of `_patch_applier_node` applies patches to multiple modules in topological order (callee first, caller later), and if any file's application fails the whole thing rolls back (same semantics as single-file `safe_apply_patch`). Single-file projects degrade automatically (when there are no dependency edges, `cross_file_plan=None`, taking the single-file path).

```bash
# Enable cross-file repair (set the environment variables explicitly)
CROSS_FILE_ENABLE=true CROSS_FILE_MAX_MODULES=5 python main.py run examples/calculator.py
# Off by default (the historical single-file semantics are unchanged)
```

Design document: [docs/design/cross_file_repair.md](docs/design/cross_file_repair.md)

### 5.9 Assertion Augmentation Strategy (3.4, off by default)
Before generating, `GeneratorAgent` extracts existing `assert` statements in the code under test via AST (deduplicated, at most 10) and injects them into the prompt as "anchor assertions", steering the LLM away from code smells such as assertion weakening / tautological assertions / unnamed magic numbers. The default `false` preserves historical generation semantics; enabling it requires an explicit `ASSERTION_AUGMENT_ENABLE=true`.

### 5.10 Dependency Cache Monitoring (4.4)
The `venv` cache is upgraded from "reuse without monitoring" to "observable hit rate + cleanable":
- `get_venv_cache_stats()`: in-process cumulative hit/create events + on-disk JSON cross-process aggregation, returning `hit_rate = hits/(hits+creates)`
- `list_venv_cache()`: lists every venv in the cache directory (name/path/size_mb/created_at)
- `clear_venv_cache(max_age_days, max_size_mb)`: filters and cleans by age/size; when both are None, clears everything

### 5.11 Test Smell / Convergence Curve / Convergence Failure Mode / Boundary Coverage / Mutation Score / Assertion-Strength AST (1.2/1.3)
Six new conservative, re-computable sections in `experiments/analyze_results.py` (all "field-missing → skip", legacy JSON never crashes):
- **Test smell detection (1.2)**: an AST scan over `details[].generated_test` identifying four smell types: Assertion Roulette / Magic Number / assertion weakening / trivial tests
- **Repair convergence curve (1.3)**: aggregates cumulative pass rate and average time by iteration round 0/1/2/3+, showing "how the pass rate changes as iterations increase"
- **Convergence failure-mode attribution (1.2)**: for tasks that still fail at MAX_ITERATIONS, distinguishes "cannot pinpoint root cause" (repeated identical diagnosis, patch never written) vs "cannot produce an effective patch" (patch written but still failing, or repeatedly rejected by safety guards)
- **Boundary case coverage (1.3)**: AST-based conservative check of `generated_test` for coverage of None / empty string / empty collection / 0 / -1 / >= / <= boundary conditions; reports per-type hit counts and coverage rate
- **Mutation score (1.3)**: collects `details[].mutation_score` (produced by an external mutation tester such as mutmut); aggregates mean / high (>=0.7) / low (<0.4) distribution; skips the section when the field is absent
- **Assertion-strength AST enhancement (1.3)**: in addition to the original `assert` line-count metric, adds an AST basis (`ast.parse` + `ast.Assert` node counting), outputting `ast_avg_assertions` and `ast_parse_failed_tasks`

When legacy JSON lacks `generated_test` / `mutation_score` fields, it degrades gracefully without crashing.

### 5.12 Failure Root-Cause Classification and Case Knowledge Base (5.3)
Additions in `experiments/analyze_failures.py`:
- **Failure root-cause classification**: three root causes (`llm_capability` / `dependency` / `framework`) conservatively and heuristically classified by `error_category` + `diagnosis` keywords
- **Case knowledge base**: typical failure cases selected with diversity priority over `error_category`, structured into `（工件已清除）` (containing task_id / root_cause / reproducible_steps / suggested_fix; generated by this script's `-k` option, an offline derivative that is not committed by default)

A new CLI option `--knowledge-base/-k` controls the output path.

### 5.13 Execution Feedback Trace Collection (3.2)
`state.py` adds an `execution_trace` field (list, default `[]`; `create_initial_state` keeps it in sync). `_executor_node` in `nodes.py` appends one record to `state["execution_trace"]` on every execution:

```
{
  "iteration": int,
  "passed": bool,
  "coverage": float,
  "coverage_delta": float | None,   # None for the first round
  "elapsed_seconds": float,
  "reward_signals": {               # conservative linear normalization, recorded only, never used for routing
    "correctness": 0.0 | 1.0,
    "efficiency": 0.0~1.0,          # 1 - elapsed / EXECUTION_TIMEOUT
    "simplicity": 0.0~1.0           # 1 - elapsed / (EXECUTION_TIMEOUT * 2)
  }
}
```

A pure observability layer, enabled by default (does not affect repair routing). `run_benchmark.py` result rows carry `execution_trace` (failure branch falls back to `None` to keep key-set parity); `analyze_results.py` adds an "Execution Feedback Trace Summary (3.2)" section: observed task count / total executions / average rounds / first-round pass rate / last-round correctness & efficiency means / first-vs-last coverage trend (delta). Legacy JSON without the field skips the section.

> Purpose: preparing data for future execution-feedback-driven fine-tuning (BoostAPR-style methods) — every benchmark automatically writes "pass/fail, coverage change, elapsed time, multi-dimensional reward signals" into the result JSON; no extra trace-collection script needed.

### 5.19 Error Classification System Extension (5.2 + P0 4.1 + 2.2 subcategories, 17 categories)
`ErrorCategory` expanded from 12 to 17 categories: the 5.2 batch added `EXECUTION_TRACE_MISSING` (task failed but `execution_trace` empty = executor exception path) and `MULTI_CANDIDATE_ALL_REJECTED` (all multi-candidates rejected by static screening); the P0 4.1 batch (2026-09-25 follow-up) split two precise subcategories out of `LLM_FORMAT_ERROR` — `LLM_EMPTY_RESPONSE` (LLM empty response) and `LLM_JSON_PARSE_FAILED` (non-empty but JSON extraction failed) — classified directly by `classify_llm_response()` after the Debugger receives the LLM response and before JSON parsing (one of the roots of the 75% UNKNOWN failure sample); the 2.2 batch (2026-09-27 round 11) added `PATCH_SYNTAX_INVALID` (a patch that remains syntactically invalid / fails AST parsing after 2.2 resampling up to 2 times, written to `state["error_category"]` by `apply_patch_with_resample` stats via `_patch_applier_node`), identifying the "patch syntax repeatedly corrupted" scenario; `refine_failure_category` gains `execution_trace` / `multi_candidate_stats` / `patch_syntax_invalid` parameters, precedence `patch_rejected > rag_empty > trace_missing > multi_rejected > patch_syntax_invalid`; `refine_final_error_category` wires the new fields; `get_fix_strategy` documents fix strategies per category.

```python
from src.agents.error_classifier import refine_final_error_category

category = refine_final_error_category(final_state)  # → one of 17 categories
```

#### 5.19.1 Patch post-processing resampling (2.2, `PATCH_RESAMPLE_ENABLE`, default off)
When the application fails (target function not located / AST parse fails), `_patch_applier_node` in `src/graph/nodes.py` triggers `apply_patch_with_resample` (in `src/tools/patch_applier.py`) if `PATCH_RESAMPLE_ENABLE=true`: feeds "negative feedback" (AST error info + 1.3 downgrade-chain tier temperature) back to the Debugger to regenerate the patch, up to `PATCH_RESAMPLE_MAX` (default 2) times; if still failing, marks `patch_syntax_invalid` (consumed by `refine_failure_category`, normalized to `PATCH_SYNTAX_INVALID`) and keeps the original code. Default-off produces no extra LLM calls (zero regression to the historical single-patch path).

```bash
# Enable patch post-processing resampling (default off, explicit enable)
PATCH_RESAMPLE_ENABLE=true PATCH_RESAMPLE_MAX=2 python main.py run examples/calculator.py
```

#### 5.19.2 Layered-compression downgrade-chain propagation (1.3, `CONTEXT_TIER_DOWNGRADE_ENABLE`, default off)
When the naming-contract symbol guard (`check_naming_contract`) in `_patch_applier_node` rejects a patch, if `CONTEXT_TIER_DOWNGRADE_ENABLE=true` then `advance_context_tier()` advances the context tier (`full_context` → `patch_ingredients` → `minimal`) and writes `(tier_name, missing_symbols)` as `contract_reject_feedback` into `state` (a new `AITesterState` key), propagated via the LangGraph channel to the next-round `_debugger_node` — which regenerates at a "higher-constraint" context tier + lower temperature (`_build_downgrade_context` + `_downgrade_tier_temperature`), reducing the probability of "creative rewrites" re-breaking the naming contract. Default-off only records the missing symbols (`state["contract_missing_symbols"]`), does not advance the tier (historical single-patch path).

```bash
# Enable the 1.3 layered-compression downgrade chain (default off, explicit enable)
CONTEXT_TIER_DOWNGRADE_ENABLE=true python main.py run examples/calculator.py
```

#### 5.19.3 Multi-dimensional contamination detection (V, `run_benchmark._build_task_result`)
`experiments/run_benchmark.py`'s `_build_task_result` adds a `contamination_risk_level` field (high/medium/low): per task it calls `patch_semantic_similarity` (in `experiments/contamination_check.py`) for multi-dimensional detection (token Jaccard + AST statement-skeleton LCS + embedding-cosine / bag-of-words-cosine conservative proxy; with `EMBEDDING_BACKEND` wired to a real embedding library it auto-upgrades to CodeBERT-style semantic cosine), combining into a risk_level (taking the most severe dimension); without a golden patch it conservatively returns "low" (no overlap evidence, not "identical"). Consumed by `analyze_results`'s `_contamination_cross_analysis` (separates "contaminated-sample" vs "uncontaminated-sample" results). `rag_ab_experiment.compare_ab` adds `token_saving.delta_pct` (RAG ON vs OFF token-consumption reduction percentage, denominator `max(_mean(off_tokens), 1)` against division by zero).

**〔2026-10-22 BM-round erratum: the paragraph above is the O-round draft; four claims have since been rewritten — quote this erratum rather than the draft〕** ① **The domain has five grades, not three**: `high / medium / low / unknown / not_applicable` (single source of truth: `experiments/contamination_check.py`). ② **Without a golden patch (or with either side empty) the result is `not_applicable`**, not a conservative `"low"` — N7 (2026-10-05 review) measured that synthetic datasets were always labelled `low`, mixing "the check never ran" with "checked, and no overlap evidence". ③ **A detector exception (non-string patch, failed dependency import) returns `unknown`** (BM round, 2026-10-22; it previously folded into `low`, filing crashes into the `statistical_analysis.contamination_view_summary` clean group); per ADR-0023 `unknown` / `not_applicable` **stay out of the denominators**. ④ **Since E8 (2026-10-10) the combination rule is corroboration, not "take the most severe dimension"**: `structural` is weak evidence (on its own it upgraded the grade in 38.5% of 200 unrelated patch pairs) and may not upgrade by itself; max-taking is restored only under `AITESTER_CONTAMINATION_STRICT_MAX=true`. See the BM manual（分册已删除）.

#### 5.19.4 mypy static type-check layer (2.1, `TYPE_CHECK_ENABLE`, default off)
`src/tools/type_repair.py` adds `_run_mypy_findings`: when `TYPE_CHECK_ENABLE=true`, runs mypy repo-level static type analysis on the "patched code" (the "repo-level static analysis" part of PAGENT's hybrid architecture), identifying "undefined names / argument-type mismatches / return-value type inconsistent with declaration / container-type misuse" — the PAGENT "type / data-structure management errors" (27.19% of failing patches); transparently degrades to an empty list when mypy is not installed (does not block the ast static layer); consumes only high-confidence error categories (`[name-defined, arg-type, return-value, dict-item, list-item, assignment, operator, index, has-type]`), filtering out "inference-failed / incomplete-type" low-confidence warnings. `debugger.py`'s `debug()` adds the observation field `mypy_findings_count` (0 when not enabled / not installed). **BG (2026-10-21)**: `mypy_findings_count=0` is evidence of "no type findings" only when `static_check_status="ok"` (the checker really finished with a trustworthy report); switch-off / not-installed / timeout / crash / rc anomaly / corrupt report are recorded as `disabled` / `unavailable` / `error`, with per-attempt reasons in `static_check_outcomes` passed through the debugger into graph state. The pyright backend (`TYPE_CHECK_BACKEND=pyright`) follows the same contract. Independent switch from `TYPE_REPAIR_LLM_ENABLE` (the LLM layer); can be enabled together (mypy yields more findings, wider LLM-layer repair surface).

```bash
# Enable the mypy static type-check layer (default off, explicit enable)
TYPE_CHECK_ENABLE=true python main.py run examples/calculator.py
```

#### 5.19.5 Detection-first protocol (W3, `DETECTION_FIRST_ENABLE`, default off; ADR-0015)
The historical main batch (2026-10-01, n=50) `false_fix_rate=89.8%` stems from a **self-referential reward**: the success signal "self-generated tests pass" has no link to "the defect was detected". The detection-first protocol ("red-before-green") aligns the two:

- **First-round red observation** (`_executor_node`): executions at iteration==0 (unrepaired code) write `detection_first_red_seen` (task-level sticky — True once any round went red);
- **Routing** (`_should_debug`): an all-green first round with regeneration budget left no longer counts as success — routes `regenerate` (reason=detection_first_all_green), and Generator receives a strengthened prompt section (expected values must come from problem semantics; no weakening assertions to pass, no reimplementing the function);
- **Terminal annotation**: on final pass writes `detection_first_status` — `red_then_green` (detect then repair) / `all_green_unverified` (weak-test false success — **evaluation must not count it as detection/repair success**); both keys are surfaced in result rows (None when off, key-set isomorphic).

"Red-on-original" is the "buggy red" half of F2P and works online without gold material — the minimal-change path to turn `detection_rate` from an evaluation metric into a runtime reward signal.

```bash
# Enable the detection-first protocol (default off, explicit enable)
DETECTION_FIRST_ENABLE=true python experiments/run_benchmark.py --dataset synthetic --task-count 10 --baselines aitester
```

### 5.20 SWE-bench Repo-Level Verification (P0/P1, default off)
The official SWE-bench verification criterion is "apply the gold `test_patch` to
the `base_commit` checkout, then run `FAIL_TO_PASS` (fails pre-fix, must all
pass post-fix) + `PASS_TO_PASS` (no regression)". A single temporary-file
executor cannot hold repo-level code (broken module names / missing deps /
multi-source-file patches), so `src/agents/executor_repo.py` carries repo-level
execution independently (default off; zero change to synthetic/examples
calibration):

- **Env setup**: `git clone --no-checkout --filter=blob:none` +
  `checkout <base_commit>` + `pip install -e .` (repo pyproject deps only),
  cached by `(repo, commit12)` under `~/.cache/aitester/repo_envs/`
  (overridable via `SWE_REPO_ENVS_DIR`); same-repo multi-task clones/pips only
  once.
- **venv isolation** (`SWE_REPO_VENV_ISOLATION=true`, default off): each
  commit env builds an independent venv beside it; `pip install -e` goes into
  the venv and pytest runs with the venv's python, decoupled from global
  `sys.executable`. When repo_envs share the global python, the global
  site-packages editable install points at the "last pip install -e" commit's
  source → cross-commit tasks `import <repo_pkg>` resolve to the wrong version
  (measured sqlfluff `BaseSegment` methods inconsistent across adjacent
  commits → AttributeError, unrelated to LLM patches). In venv mode no host
  PYTHONPATH is injected (measured: injecting it actually causes ImportError);
  PATH prepends venv/bin.
- **LLM patch mapping**: `_normalize_llm_patch` strips LLM output fences
  (triple-backtick wrap or a leading 'python' marker) back to the pure code
  body; `_diff_codes` generates a strict unified diff via `git diff --no-index`
  (difflib hand-join produced corrupt patches in the "whole-file rewrite"
  scenario due to line-count mismatch with git's parser — fixed); `---`/`+++`
  headers rewritten to the gold target file's repo path
  (`_extract_gold_target_relpath` takes the first non-test source file's b/
  side path from the official gold patch) → mapped into the real repo;
  identical strings (LLM made no change) return empty, and `FAIL_TO_PASS`
  is adjudicated as a no-patch measurement — no false pass.
- **Apple Git 2.54 new-file bug fallback**: local `git apply` reports clean
  on a new-file patch but produces an empty file; `_apply_patch_robust`
  manually backfills the new-file section so test files are complete.
- **Routing**: `REPO_LEVEL_EXECUTION=true` +
  `task.metadata.source=="swe_bench"` + `fail_to_pass/repo_url/base_commit`
  present → only the aiterster baseline routes to `RepoExecutor.verify`,
  overwriting `test_passed` and writing a `repo_verification` diagnostic;
  plain_llm / single_agent keep the original LLM-generated-test calibration
  (no repo env dependency).
- **Unit tests**: `tests/test_executor_repo.py` 17 cases (setup cache /
  verify pass / verify fail / base_not_failing / test_patch_apply_failed /
  baseline restore / venv isolation / LLM patch helpers / git diff
  applicability).

```bash
# Repo-level SWE-bench verification (opt-in, default off)
REPO_LEVEL_EXECUTION=true SWE_REPO_VENV_ISOLATION=true \
  SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10 --baselines aiterster
```

### 5.22 Frontier-recommendation batch (2026-09-28: gap_report P0/P1/P2 gaps G1–G8 + 2026-09-29 review/optimization round, default off)

#### 5.22.1 P0 runtime probe (`RUNTIME_PROBE_ENABLE`, default off)
`src/agents/runtime_probe.py`: at exception-raise time, directly reads the
`exc.__traceback__` frame chain to capture the precise failure-time frame
stack (zero trace overhead, replacing the historical `sys.settrace`
exception-event approach — when an exception is raised inside the function
body, the exception event does not propagate to the called frame, measured
frames were permanently empty, so the probe never actually worked since
introduction). Synchronously fixed single-character-variable mis-filtering
(x/y/z at assertion-failure time are the most critical observation variables
and are no longer filtered as "loop-variable noise"), line-number error
(exited frames' `f_lineno` stops at the function-body tail, now uses
`tb_lineno`), module-filter never matching (probe file named
`"{target_module}_probe.py"` did not match the historical filter condition
`"{target_module}.py"` substring — when a target_module was specified, all
frames were discarded), and child-thread unhandled-exception leak (top-level
call exceptions were not intercepted → "Exception in thread" noise).
When `RUNTIME_PROBE_ENABLE=false` (default), zero difference. Tests:
`tests/test_runtime_probe.py` (full suite passed / 0 failed / 0
warnings, `-W error::ResourceWarning` caliber; totals in BASELINE.yaml).

#### 5.22.2 G2 risk-tiered human approval loop (`RISK_APPROVAL_ENABLE`, default off)
`src/graph/risk_approval.py`: three-factor weighted scoring (confidence
0.4 + patch impact 0.4 + budget ratio 0.2) → low/medium/high tiering →
auto_merge / human_confirm / force_review approval actions; thresholds are
configurable (`RISK_THRESHOLD_MEDIUM=0.35` / `RISK_THRESHOLD_HIGH=0.65`),
weights are configurable (`RISK_WEIGHT_CONFIDENCE` / `RISK_WEIGHT_IMPACT` /
`RISK_WEIGHT_BUDGET`); `experiments/run_benchmark.py` result rows gain a
`risk_summary` field (when default off, placeholder `enabled=False`,
key-set isomorphism, does not change the historical experiment caliber).
Tests: `tests/test_risk_approval_matrix.py`.

#### 5.22.3 G3 kernel-level sandbox (`KERNEL_SANDBOX_ENABLE`, default off)
`src/agents/kernel_sandbox.py`: macOS Seatbelt (`sandbox-exec`) / Linux
Landlock (`bwrap`) dual backend; platform-unsupported → fail-closed
rejection (does not silently degrade to un-isolated local, same policy as
Docker-unavailable). Wired into the local execution chain
(`src/agents/executor.py` `_kernel_sandbox_executable` /
`_kernel_sandbox_obs`). Tests: `tests/test_kernel_sandbox.py`.

#### 5.22.4 G4 AgentTelemetry failure-detection benchmark (`AGENT_TELEMETRY_ENABLE`, default off)
`src/observability/agent_telemetry.py`: 10 built-in failure-pattern regex
matches (zero LLM cost, pure observation layer), outputs a Markdown report
for experimental-analysis consumption.

#### 5.22.5 G5 testless execution-irrelevant validation (`TESTLESS_VALIDATION_ENABLE`, default off)
`src/tools/testless_validation.py`: four independently toggleable layers
(AST symbol guard / mypy static check / naming-contract regression / import
smoke); any layer failure → overall fail (conservative fail-closed
caliber), complementary to G7 "with-test" scenario defect-validity
determination.

#### 5.22.6 G6 multi-agent debate convergence (`EXPERT_POOL_DEBATE_ENABLE`, default off)
New `debate_round()` method in `src/graph/expert_pool.py`: top-K (default 2,
`EXPERT_POOL_DEBATE_TOP_K` [2,4]) candidate debate convergence produces one
`debate_revise` revised candidate (requires `EXPERT_POOL_ENABLE=true`); on
LLM failure, conservatively degrades back to the original verified list
(do not block the main chain).

#### 5.22.7 G7 defect-report generation (`ErrorReport.oracle_stats`)
`src/reports/generator.py`'s `ErrorReport` gains an `oracle_stats` field +
a `with_oracle_stats()` method: the "Oracle validity (Oracle augmentation,
G7)" section is rendered only when `total_oracles > 0`.

#### 5.22.8 G8 full-stack SWE-bench Pro re-test
`experiments/run_full_stack_swe_bench_pro.py` (one-key seven-switches:
`RUNTIME_PROBE_ENABLE` / `STRATEGY_BANK_ENABLE` / `EXPERT_POOL_ENABLE` /
`CROSS_FILE_ENABLE` / `CROSS_FILE_BIDIRECTIONAL` / `REPO_LEVEL_EXECUTION` /
`SWE_REPO_VENV_ISOLATION`) + `scripts/gates/check_swe_bench_pro_ready.py`
(data pre-gate: JSONL existence + `instance_code` / `test_patch` /
`FAIL_TO_PASS` / `base_commit` completeness check, blocks with `exit 1`
when missing) + `experiments/summarize_full_stack.py` (ON/OFF contrast
analysis: success rate / error buckets `assertion` / `runtime` /
`import_error` / `syntax` / `unknown` / `other` + conservative verdict;
when the ON group is all zeros, "no positive information" — do not
force a positive claim). Tests: `tests/test_g8_g2_g4_g5_g6_g7_g1.py`.

#### 5.22.9 G1 Tree-sitter precise AST backend (optional dependency)
`src/tools/tree_sitter_backend.py`: implements the 4 core methods of
`LanguageBackend` (precise AST caliber, fewer false positives);
`tree_sitter` is an optional dependency — when missing, transparently
degrades back to the lexical layer, does not block the Python main path;
`pyproject.toml` mypy configuration declares
`tree_sitter` / `tree_sitter_typescript` ignore_missing_imports.

#### 5.22.10 Doc-consistency P2
New `docs/dependency_exemptions.md` (chromadb 1.5.9 hits 5 known
vulnerabilities PYSEC-2026-311 / PYSEC-2026-3813 / PYSEC-2026-3814 /
PYSEC-2026-3815 exemption registry: dependency / version / vulnerability ID /
exemption reason / re-review trigger condition / re-review deadline) +
`scripts/gates/check_dependency_exemptions.py` (CI gate: when the `--ignore-vuln`
list is not registered in the registry, `exit 1` blocks merging) +
`scripts/gates/check_docs_history_drift.py` (warning-only: detects when
`docs/history/*.md` baseline numbers drift beyond the threshold and
suggests archiving; non-blocking gate) + `CONTRIBUTING.md` "Dependency
exemption registry" section. Full 2502 tests passed (baseline 2499, +3
new regression cases) / ruff 0 warnings / mypy 0 errors (86 source files,
+5 new: risk_approval / agent_telemetry / kernel_sandbox /
testless_validation / tree_sitter_backend).

### 6. Standard Dataset Integration (new)
Multiple datasets are supported through the `src/datasets/` subpackage (`dataset_loader.py` + `synthetic_dataset.py`):

```python
from src.datasets import SWEBenchDataset, load_dataset
from src.datasets import SyntheticDataset

# Load the built-in example dataset (no download needed, 3 predefined bug tasks)
dataset = load_dataset("examples")

# Load SWE-bench (data must be downloaded first)
dataset = SWEBenchDataset(subset="lite")  # 500 tasks
SWEBenchDataset.download_from_huggingface(subset="mini")

# Generate a synthetic dataset (local generation, no external data needed)
dataset = SyntheticDataset(task_count=50, seed=42)
```

## Experiment Reproduction

### Environment Requirements
- Python 3.12+ (the locked dependency scipy requires ≥3.12)
- MySQL 5.7/8.0 (optional, for persisting experiment data)
- LLM API Key (e.g. OpenAI, DeepSeek, etc.)

### Reproduction Steps
```bash
# 1. Clone the repository
git clone <repository-url>
cd AITester

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
cp .env.example .env
# Edit .env and fill in the API Key and other information

# 4. Initialize the database (optional)
python init_db.py

# 5. Run the benchmark (built-in example dataset, three baseline comparisons)
python experiments/run_benchmark.py --dataset examples --baselines aitester,plain_llm,single_agent

# 6. Limit the task count (quick validation)
python experiments/run_benchmark.py --dataset examples --task-limit 2

# 7. Inspect results
ls experiments/results/
python experiments/visualize_results.py
```

### Running the SWE-bench Benchmark (requires data download)
```bash
# Method 1: download the lite subset from HuggingFace (~500 tasks)
python -c "from src.datasets import SWEBenchDataset; SWEBenchDataset.download_from_huggingface(subset='lite')"

# Method 2: download manually and place into ~/.cache/aitester/swe_bench/swe_bench_instances.jsonl

# Run the benchmark
python experiments/run_benchmark.py --dataset swe_bench --subset lite --task-limit 10
```

### SWE-bench Repo-Level Verification Results (P0/P1, 2026-09-25)
With `RepoExecutor` (`REPO_LEVEL_EXECUTION=true`), the lite-20 run was
verified on the official SWE-bench criterion (gold `test_patch` before/after
FAIL_TO_PASS/PASS_TO_PASS measurement); results in
`（工件已清除）` §7:

- After the data pipeline fix (`SWE_BENCH_ENRICHMENT` injecting real source) +
  execution environment fix (RepoExecutor repo-level clone + pip install -e +
  venv isolation) + patch pipeline fix (applicable unified diff via
  `git diff --no-index`), SWE-bench is still 0/20.
- P1 diagnosis (single-source tasks 0/7, after venv isolation + fixed
  pipeline) failure categorization: 5/7 `LLM_BREAKS_IMPORT` (LLM rewrite of
  the target file broke sqlfluff's plugin naming contract, e.g. renaming the
  `Rule_L027` class → entire import chain crashed) + 2/7 `EMPTY_LLM_PATCH`
  (LLM produced no fix). **Pipeline and environment are fully fixed; 0/N is
  the LLM engine's fix-quality boundary** (free-tier small model on real
  repo-level code), not a pipeline or environment issue.
- Multi-file tasks (13/20 multi-source) have no positive signal before the
  engine-capability breakthrough (ON/OFF both 0/N); cross-file gain
  validation requires a stronger model + full-repo source context.

Paper positioning: SWE-bench 0/N is written into the "Limitations" section
(engine fix-quality boundary); the main experiments still use the synthetic
dataset (88% vs 60% vs 8%, p=0.002 significant).

### SWE-bench Loading Quality Validation and Source Enrichment (P0)

The official SWE-bench JSONL **does not include a source-code-under-test field** (only issue text + repair patch);
running the benchmark directly means the LLM never sees the real code, so results can only validate the workflow and produce no effective repair comparison.
Diagnose/fill in with the following two steps:

```bash
# 1. Validate loading quality (per-task instance_code/test_code completeness + full quality report)
python main.py check-dataset swe_bench --subset lite

# 2. Provide a source enrichment file (JSONL, keyed by instance_id):
#    {"instance_id": "r/r-1", "instance_code": "def f(): ...", "test_code": "def test_f(): ..."}
#    Can be generated by exporting target file contents via git checkout <base_commit>
SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

Target function localization: the loader automatically extracts the target function name
from the hunk headers of the official `patch`
(`metadata["suggested_function"]`; measured extraction rate 96% on a local cache of 225 tasks);
the benchmark uses it to initialize `target_function`, driving the
**AST focused extraction** of the Planner/Generator/Debugger — large source files are no longer hard-truncated "half head, half tail", but instead
keep the import + target function + the helper functions it calls directly (see `src/tools/code_context.py`).

### Result Files

Benchmark results are saved in the `experiments/results/` directory as JSON:
```
experiments/results/benchmark_<dataset>_<timestamp>.json  # e.g. benchmark_examples_20260814_120000.json, benchmark_synthetic_20260814_120000.json
```
This directory is already in `.gitignore` and will not be committed to version control.

---

## Synthetic Dataset and Statistical Tests

### Synthetic Dataset
AITester ships a built-in `SyntheticDataset` that generates defect tasks of any scale without relying on SWE-bench/Defects4J:
- 10 predefined bug patterns (division by zero, boundary conditions, logic errors, etc.)
- Task count controlled by `--task-count` (≥ 50 recommended to meet publication requirements)
- A fixed seed guarantees reproducible results

### Statistical Significance Testing
`visualize_results.py` automatically outputs:
- **Paired t-test**: compares the statistical significance of pass rates between baselines
- **Mann-Whitney U test**: a non-parametric test as a supplement
- **Cohen's d**: quantifies effect size
- **p-value heatmap**: visualizes significance differences

Output files:
- `（工件已清除）`
- `（工件已清除）`

---

## Execution Isolation and Dependency Management (P1)

Local execution by default runs under the system Python: when a third-party library imported by the code under test is missing, the test fails immediately,
and it is impossible to distinguish "code bug" from "missing environment dependency"; dependencies of different tasks also conflict with each other.
With the venv sandbox enabled, each task executes in a temp directory + an isolated venv cached by dependency combination,
with `PYTHONPATH` pointing only at the sandbox directory:

```bash
# Isolated venv execution (missing dependencies are only detected and logged; test results are still produced normally)
EXECUTOR_USE_VENV=true python experiments/run_benchmark.py --dataset swe_bench --task-limit 10

# Auto pip install missing dependencies before execution (installed only into the venv, the system environment stays clean)
EXECUTOR_USE_VENV=true EXECUTOR_AUTO_INSTALL_DEPS=true \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10
```

- venvs are disk-cached by "missing package combination" (`~/.cache/aitester/venvs/`); tasks with the same dependencies are reused;
- missing dependencies are written into the result's `error_info.missing_dependencies` and classified by the error
  classifier into a distinct `import_error` category (as opposed to `syntax`, where the code itself has wrong syntax);
- when dependency installation fails, it returns `dependency_install_failed` early, so test results do not mislead analysis.

## RAG Retrieval Augmentation and Quality Metrics (P1)

RAG is off by default (`ENABLE_RAG=false`). Once enabled, the Generator/Debugger retrieve
similar historical cases; the retrieval corpus is persisted to `rag_data/` (configurable via `RAG_PERSIST_PATH`),
**reusable across experiment runs**, with a default TTL of 7 days (`RAG_TTL_SECONDS`):

```bash
# Explicitly enable RAG for an ablation experiment (the retrieval corpus accumulates across runs)
python experiments/run_benchmark.py --dataset synthetic --enable-rag

# Inspect RAG retrieval quality metrics (results.<baseline>.rag_metrics in the result JSON:
# retrievals / hits / hit_rate / avg_max_similarity; JSON is the default output, no switch needed)
python experiments/run_benchmark.py --dataset synthetic --enable-rag
```

Evaluate retrieval corpus quality standalone (Hit Rate@k / MRR, against known labeled queries):

```python
from src.rag.retriever import TestCaseRetriever

retriever = TestCaseRetriever(persist_path="rag_data")
metrics = retriever.evaluate_retrieval(
    [{"query": "def add(a, b): ...", "expected_id": "<doc_id at ingest time>"}],
    top_k=5,
)
# → {"num_queries": 1, "hits": 1, "hit_rate": 1.0, "mrr": 1.0}
```

## Efficiency Metrics and Baseline Comparison Diagnostics (P0)

Every benchmark run automatically records token consumption (`results.<baseline>.token_metrics`
and per-task `token_usage` in the result JSON), used for "full system vs plain LLM cost-effectiveness" comparison.
If you find a baseline overtaking the full system, use the comparison tool to locate the diverging stage:

```bash
# 1. Run two baselines and persist per-stage artifacts (test plan / generated code / diagnosis / patch)
python experiments/run_benchmark.py --dataset synthetic \
    --baselines aitester,plain_llm --save-state

# 2. Find tasks where "plain_llm succeeded but aitester failed", compare stage by stage + output a Markdown report
python experiments/compare_failures.py \
    --results experiments/results/benchmark_synthetic_<ts>.json \
    --raw-dir experiments/results/raw --max-tasks 5 \
    --report experiments/results/failure_analysis.md
```

For each flipped task the report gives a "suspected stage" hint (Planner noise / Debugger not converging /
environment dependency failure) and summarizes the token comparison.

---

## Docker One-Click Reproduction

Using Docker fully isolates the execution environment and avoids local dependency conflicts.

```bash
# Build the image (first time takes ~5 minutes, depending on network speed)
docker build -t aitester:latest .

# Run the benchmark
# LLM keys are mounted into the container together with .env.local in $(pwd); no -e needed (the old OPENAI_API_KEY variable is deprecated)
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python experiments/run_benchmark.py --dataset examples --task-limit 1

# Run a single-file test
docker run --rm \
  -v $(pwd):/workspace \
  aitester:latest \
  python main.py run examples/calculator.py
```

## Unit Tests

```bash
# Run all tests (current totals: BASELINE.yaml `tests`; optional dependencies missing → auto-skip degradation)
.venv/bin/python -m pytest tests/ -v

# Run tests and generate a coverage report
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing

# Run tests for a specific module
.venv/bin/python -m pytest tests/test_dataset_loader.py -v
```

**Tested modules** (file list below; current case counts and coverage are in [BASELINE.yaml](BASELINE.yaml) `tests` / `coverage` — no hard-coded totals here):

| Test File | Test Function Count | Coverage Scope |
|---------|-------|---------|
| `test_api_manager.py` | 79 | API manager (rotation/weighted-random/health-aware strategies, health thread switch, failure threshold config wiring, 4.1 circuit breaker cooldown state machine and routing filter, 1.5 cooldown boundary 3 cases, 4.1 redaction wiring 2 cases) |
| `test_api_circuit_breaker.py` | 16 | 4.4/0.6 circuit-breaker exponential backoff (`API_CIRCUIT_BACKOFF` on/off dual paths) + Prometheus export (`API_PROMETHEUS_EXPORT` default empty string) |
| `test_api_manager_extended.py` | 74 | API manager extended paths (health recovery, rate-limit marking, 4.2 half-open probe TestHalfOpenProbe 12 cases) |
| `test_base_agent.py` | 40 | JSON extraction, code block extraction, client reuse, AST smart extraction |
| `test_base_agent_extended.py` | 46 | Exponential backoff retry, LLM cache, LLM client reuse |
| `test_cli_app.py` | 36 | CLI commands (list-examples/--version/argument validation/parallel/json edge cases + 1.4 timeout pass-through/concurrency fault tolerance/check-dataset edge cases/glob concurrency + 4.4 clean-venv-cache 4 cases + 5.1 concurrent interrupt/signal handling 3 cases) |
| `test_cli_output.py` | 10 | CLI output layer regression (colorize TTY dual branch, success/error/warning/info icons and stdout/stderr routing, print_rich_table empty list/missing key fallback/coverage=0.0 not misjudged as N/A, O-01 batch) |
| `test_cli_parallel.py` | 10 | Concurrent dispatcher `_dispatch_parallel_tasks` and `run` concurrent branch regression (rich/no-rich dual paths, per-task fault tolerance, CI gate exit 1) (0.1) |
| `test_cli_run.py` | 6 | run command orchestration (timeout/coverage threshold pass-through) |
| `test_cli_console_output.py` | 8 | run non-JSON console summary (success/failure/diagnosis/suggestions) + _dispatch_concurrent rich/fallback/JSON-silent branches (0.1) |
| `test_code_analyzer.py` | 17 | AST parsing, cyclomatic complexity, code replacement |
| `test_code_context.py` | 18 | AST smart extraction (P0 large-file context) |
| `test_complex_logic.py` | 12 | Complex business logic (email validation, etc.) |
| `test_config_generator.py` | 26 | LLM config generator templates |
| `test_config_manager.py` | 35 | Config manager (LLM config add/remove, incl. P0 write-disk validation: reject newline/`#` var-value injection, 5 cases) |
| `test_config.py` | 15 | config.py defaults and tolerant parsing |
| `test_core_modules.py` | 19 | Core module smoke tests (multiple classes of BenchmarkTask / InMemoryDataset / Planner / Executor / DatasetLoader) |
| `test_cost_aware_routing.py` | 13 | Cost-aware routing and expensive-provider cost alerts (3.4 + 3.2 configurable threshold 4 cases) |
| `test_credential_scrub.py` | 5 | New in 2026-09-26: P0 credential-scrub hardening regression (numbered variants `OPENAI_(API_KEY\|BASE_URL)_\d+` / provider intermediate vars / high-number boundary / input immutability, 5 cases) |
| `test_dataset_loader.py` | 76 | Dataset loader (InMemory/SWEBench, O(1) `get_task_by_id` index) |
| `test_dataset_loader_extended.py` | 59 | Dataset loader extended paths (raw loading/field validation) |
| `test_dataset_validation.py` | 16 | SWE-bench loading quality validation and source enrichment (P0) + tasks_missing_source (2.1) |
| `test_debugger.py` | 38 | Error diagnosis, RAG injection, classification pass-through |
| `test_contamination_check.py` | 15 | 2.1 data contamination detection (token extraction / Jaccard overlap / grading / detect scan / rendered section) |
| `test_contamination_multidim.py` | 25 | 2.1 multi-dimensional contamination detection (structural AST-skeleton LCS + semantic token-bag cosine, three-dimensional similarity / combined risk level / full detect flow / resistant-benchmark registry) |
| `test_dependency.py` | 43 | Dependency detection and venv management (P1) + 4.4 cache monitoring (hit-rate stats/listing/cleanup, 8 cases) |
| `test_dependency_edge_cases.py` | 18 | Dependency edge branches (stdlib fallback / find_spec exception / venv creation timeout / OSError silent degradation, new in 0.1) |
| `test_error_classifier.py` | 89 | Seventeen-category error classification and repair strategy mapping (P2 refinement + 1.2 residual + 1.1 status refinement + 5.2 ongoing refinement + P0 4.1 sub-classes + 2.2 `PATCH_SYNTAX_INVALID`: refine_failure_category / test_seventeen_categories_total 1 case) |
| `test_error_classifier_new_categories.py` | 16 | 5.2 two new error-category determinations (`EXECUTION_TRACE_MISSING` / `MULTI_CANDIDATE_ALL_REJECTED`, priority / fix-strategy description / final_state wiring) |
| `test_exceptions.py` | 33 | Custom exception classes and decorators |
| `test_executor.py` | 41 | Coverage parsing, failed case parsing |
| `test_executor_docker.py` | 11 | 4.3 Docker execution mode (unavailable diagnostics / mode flag / docker precedence over venv / subprocess env credential stripping + TestDockerExecutionFlow in-container execution 6 cases + sandbox cleanup fallback) |
| `test_executor_sandbox.py` | 7 | Sandbox execution path and dependency installation (P1, including install failure short-circuit / target file missing edge case) |
| `test_executor_repo.py` | 17 | P0 repo-level executor RepoExecutor (setup cache / verify pass/fail / base_not_failing / test_patch_apply_failed / baseline restore / venv isolation / LLM patch helpers / git diff applicability) |
| `test_experiments_analysis.py` | 43 | Experiment result analysis (ranking/statistics) + 5.1 statistical-test boundary 5 cases (sample <3 / partial pairing missing / single baseline / dirty data) |
| `test_experiments_scripts.py` | 43 | visualize result selection / normalized experiment return keys / benchmark parallelism regression (0.1) + 4.3 analyze_results pure functions + 2.3 RAG auto-summary + 1.1/1.2 repair convergence and quality proxy metrics + 1.2 test smell detection + 1.3 repair convergence curve + 4.4 dependency cache hit stats + 1.2 convergence failure mode attribution / 1.3 boundary case coverage / 1.3 mutation score / 3.2 execution trace summary (14 cases) |
| `test_generator.py` | 27 | parametrize validation, import fixing, LLM calls + 3.4 assertion augmentation (TestAssertionAugmentation: AST extraction of existing assert, off by default, 9 cases) |
| `test_llm_file_cache.py` | 8 | LLM file cache hit/miss + temperature key non-interhit + system_prompt in cache key (0.9 deep-audit regression) |
| `test_logging_utils.py` | 38 | Log redaction regexes (sk- prefix / dotted-segment / prefix-less long hex·base64, three forms; 0.1 redaction extension regression) + 5.1 redaction boundary 5 cases (format failure / exc_info stack redaction / nested dict criteria lock / idempotence / mask exception fallback) + 2026-09-26 redact_dict string-input 2 cases (str input redacted then wrapped `{"value":...}` contract + other scalar fallback to empty dict) |
| `test_mysql_client.py` | 13 | MySQL client singleton/transaction/connection pool parameters |
| `test_multi_candidate.py` | 33 | Multi-candidate patch generation and static/execution validation filtering (3.1; boundary_shift case synced to the 2026-09-26 mutant-location key upgrade) |
| `test_packaging.py` | 3 | Packaging integrity (subpackage __init__ all present) |
| `test_patch_applier.py` | 39 | Patch application (whole-file/single-function modes) + multi-function patch ordering (0.9 regression) |
| `test_planner.py` | 5 | PlannerAgent planning logic serialization |
| `test_prompts_templates.py` | 14 | Structural contract of the three system-prompt constants (key instruction sections/error categories/JSON output format, 0.1) |
| `test_rag_metrics.py` | 5 | RAG retrieval quality metrics Hit Rate/MRR (P1) |
| `test_rag_retriever.py` | 31 | RAG retriever add/remove/query/clear and persistence |
| `test_report_generator.py` | 50 | Error report generator (incl. seventeen-category branches; 2026-09-26 `_parse_failed_cases` pytest short-output pattern matching 2 cases: short-format inline error suffix + detailed-format exception class line) |
| `test_run_benchmark.py` | 10 | Benchmark result construction and exception path regression (0.1 deduplication refactor + 2.1 patch field key-set isomorphism guard) |
| `test_swe_bench_source_export.py` | 13 | SWE-bench source export script (patch target file extraction / enrichment persistence / dry-run, 2.1) |
| `test_state.py` | 8 | AITesterState single-construction-point factory (create_initial_state key-set guard / module_name derivation / mutable container isolation, deep-refactor batch; 2026-09-26 adds `repo_verification` field declaration) |
| `test_viz_significance.py` | 6 | Statistical significance convergence (visualize_results reuses statistical_analysis paired primitives / NaN placeholder / primitive reference lock, deep-refactor batch) |
| `test_string_utils.py` | 10 | String utilities |
| `test_synthetic_dataset.py` | 5 | Synthetic dataset generation and determinism verification |
| `test_token_usage.py` | 9 | Token consumption stats (P0 efficiency metric) |
| `test_trace_observability.py` | 12 | Structured JSONL tracing layer (4.1) |
| `test_venv_cache_monitoring.py` | 11 | 4.4 venv cache capacity monitoring (`get_venv_cache_size_mb` / `check_venv_cache_size` 5GB threshold alert / stats file path dynamic-ization / hit-rate / cleanup) |
| `test_workflow.py` | 38 | Workflow graph construction and routing + 3.5 cross-file repair (CROSS_FILE_ENABLE enabled/disabled paths, 2 cases) + 3.2 execution feedback trace (TestExecutionTrace 3 cases: first round / second round delta / missing key tolerance) + 2026-09-26 generator LLM-failure degradation regression 1 case |
| `test_workflow_extended.py` | 44 | Workflow extended paths (RAG initialization singleton, planner default plan deduplication, etc.) + 2026-09-26 early-iteration diagnosis-keyword routing regenerate regression 1 case |
| `test_cross_file.py` | 45 | 3.5 cross-file repair (AST dependency analysis / coordinator-proposer / multi-file patch application / single-file fallback / serialization / phase-2 multi-entry deps / topological application / repair plan cache; 2026-09-26 CF-3 fix adds source_files per-module own-source 3 cases: per-module / fallback / legacy None behavior) |
| `test_cross_file_bidirectional.py` | 16 | 2.2 cross-file bidirectional dependency graph (single-direction / bidirectional baselines / `CROSS_FILE_BIDIRECTIONAL` env-var switch / symbol definition-line localization) |
| `test_analyze_failures.py` | 20 | 5.3 failure root-cause classification (three root causes: LLM/dependency/framework) + case knowledge base + CLI --knowledge-base |
| `test_weak_coverage_modules.py` | 16 | 5.1 weak-coverage module hardening round 1 (cli_output print_rich_table edge cases / error_classifier new classification paths / executor_runtime cleanup and retry exception branches) |
| `test_weak_coverage_modules2.py` | 10 | 5.1 weak-coverage module hardening round 2 (config_generator main entry / prompts_templates constant structure / synthetic_dataset edge generation) |
| `test_weak_coverage_modules3.py` | 13 | 5.1 weak-coverage module hardening round 3 (trace disk-write failure degradation / analysis statistical-test edge cases / error_classifier branches / cli_output non-rich degradation / prompts __main__) |
| `test_smell_detection_v2.py` | 25 | 1.1 smell-detection hardening (Eager Test / Lack of Cohesion trigger and no-trigger cases + syntax-error fallback) + 1.2 mutation test generator (TestMutationGenerator 9 cases; 2026-09-26 kill-judging criteria tightened, import name fixed) + 1.3 mutation score (mutation_score_from_details) |
| `test_failure_kb.py` | 14 | 5.3 failure case knowledge base + cross-batch failure pattern comparison (failure_knowledge_base structured JSON / cross_batch_comparison batch trends / three major failure root causes) |
| `test_defects4j_smoke.py` | 5 | 3.4 Defects4J-Python loader smoke test (graceful degradation without data directory / full-directory parsing / field integrity) |

## Configuration

All configuration items are managed uniformly in [config.py](config.py) and injected via `.env` and `.env.local` files:

| Config Item | Description | Default |
|--------|------|--------|
| `LLM_N_API_KEY` | LLM API key (multi-config support, see `config.local.example`) | required |
| `LLM_N_BASE_URL` | LLM Base URL | - |
| `LLM_N_MODEL_NAME` | LLM model name | deepseek-flash |
| `MODEL_NAME` | Backward compatible: default LLM model name | deepseek-flash |
| `MAX_ITERATIONS` | Maximum number of repair iterations | 3 |
| `COVERAGE_THRESHOLD` | Coverage threshold | 80.0 |
| `CROSS_FILE_ENABLE` | 3.5 cross-file repair switch (coordinator-proposer architecture, off by default) | false |
| `CROSS_FILE_MAX_MODULES` | 3.5 cross-file dependency analysis max module count | 5 |
| `ASSERTION_AUGMENT_ENABLE` | 3.4 assertion augmentation strategy (AST extraction of existing assert into prompt, off by default) | false |

| `EXECUTION_TIMEOUT` | pytest execution timeout (seconds) | 30 |
| `LLM_TIMEOUT` | Single LLM call timeout (seconds) | 60 |
| `LLM_JSON_MODE` | JSON Output (DeepSeek official; seven JSON-contract call sites bind `response_format=json_object`; **on by default since 2026-10-14**, set off for the historical byte-identical caliber; ADR-0031) | on |
| `LLM_RETRY_WAIT` | LLM retry wait time (seconds) | 30 |
| `ENABLE_PLANNER` | Enable Planner (ablation switch) | true |
| `ENABLE_DEBUGGER` | Enable the Debugger repair loop (ablation switch) | true |
| `ENABLE_RAG` | Enable RAG retrieval augmentation | false |
| `RAG_PERSIST_PATH` | RAG persistence path (empty = in-memory mode, default project-root rag_data/) | rag_data |
| `RAG_COLLECTION_NAME` | RAG ChromaDB collection name | aitester_cases |
| `RAG_TTL_SECONDS` | RAG cache TTL (seconds; default 7 days in persistence mode) | 604800 |
| `EXECUTOR_USE_VENV` | venv sandbox isolated execution (dependency isolation, P1; **on by default since R10**; set false to fall back to running directly on the host environment, debugging only) | true |
| `FL_SPECTRAL_ENABLE` | O2 spectral fault localization (Ochiai Top-k, zero LLM cost; on by default since R8, set false as the ablation control) | true |
| `FAULT_LOCALIZER_ENABLE` | Repair-engine phase-one RGFL-style LLM reasoning fault localization (localization → synthesis → verification paradigm, batch I 2026-10-07; structured localization [function / line range / confidence] injected into the Debugger prompt and surfaced as the `localization_hit_function` metric; conservative None degradation never blocks repair; **on by default**, set false to fall back to the pure-spectral ablation caliber) | true |
| `EXECUTOR_AUTO_INSTALL_DEPS` | Auto pip install missing dependencies before execution (P1) | false |
| `EXECUTOR_DEP_INSTALL_TIMEOUT` | Dependency installation timeout (seconds) | 120 |
| `MYSQL_POOL_MIN_CACHED` | Minimum reserved connections in the pool | 5 |
| `MYSQL_POOL_MAX_CACHED` | Maximum idle connections in the pool | 10 |
| `MYSQL_POOL_MAX_CONNECTIONS` | Maximum total connections in the pool | 20 |
| `MYSQL_POOL_TIMEOUT` | Connection acquisition wait timeout (seconds) | 30 |
| `LLM_N_COST_WEIGHT` | Relative cost multiplier of the Nth LLM (3.4 cost-aware routing; 0.0 = unset, APIManager falls back to the 1.0 baseline) | 1.0 |
| `SWE_BENCH_ENRICHMENT` | SWE-bench source enrichment JSONL path (P0, optional) | none |
| `REPO_LEVEL_EXECUTION` | P0 repo-level verification: SWE-bench tasks routed to RepoExecutor (clone + checkout + pip install -e env cache + gold test_patch before/after FAIL_TO_PASS/PASS_TO_PASS measurement); default off | false |
| `SWE_REPO_SETUP_TIMEOUT` | Repo-level env setup subprocess timeout (seconds, clone + checkout + pip install -e) | 600 |
| `SWE_REPO_ENVS_DIR` | Repo env cache root (per (repo, commit) dir reuse; default `~/.cache/aitester/repo_envs`) | unset |
| `SWE_REPO_VENV_ISOLATION` | P1 repo-level venv isolation (each commit env builds its own venv; pip install -e into the venv; pytest with the venv's python; default off to keep cached repo_envs compatible) | false |
| `BENCHMARK_PARALLELISM` | Batch test parallelism (0 = serial) | 0 |
| `TEMPERATURE` | LLM sampling temperature | 0.2 |

## Advanced Switches (all off by default, enable as needed)

The following switches are all provided as environment variables; defaults preserve historical experiment semantics unchanged; enabling them is an explicit act.

| Switch | Default | Effect when enabled | Related section |
|------|------|---------|----------|
| `ENABLE_MULTI_CANDIDATE_PATCH` | false | Multi-candidate patch generation and validation filtering (3.1) | 5.1 |
| `AITESTER_TRACE_DIR` | unset (no-op) | Structured JSONL tracing layer (4.1) | 5.2 |
| `ENABLE_MUTATION_SCORING` | false | 1.2 mutation-score evaluation: after the benchmark run, computes `mutation_score` per task from "generated test vs source under test" (built-in lightweight mutation generator, ≤ `MUTATION_MAX_MUTANTS` mutants per task). Significantly longer runtime; off by default to preserve the historical baseline. | 5.14 |
| `MUTATION_MAX_MUTANTS` | 10 | 1.2 cap on mutants evaluated per task (takes effect together with `ENABLE_MUTATION_SCORING=true`) | 5.14 |
| `CROSS_FILE_ENABLE` | false | Cross-file repair (coordinator-proposer architecture, 3.5) | 5.8 |
| `REPO_LEVEL_EXECUTION` | false | P0 SWE-bench repo-level verification: SWE-bench tasks routed to RepoExecutor (clone + checkout + pip install -e env cache + gold test_patch before/after FAIL_TO_PASS/PASS_TO_PASS measurement); default off keeps synthetic/examples calibration unchanged | 5.20 |
| `SWE_REPO_VENV_ISOLATION` | false | P1 repo-level venv isolation: each commit env builds its own venv (pip install -e into the venv, pytest with the venv's python), fixing cross-commit global-python pollution (measured sqlfluff BaseSegment methods inconsistent across adjacent commits → AttributeError, unrelated to LLM patches) | 5.20 |
| `ASSERTION_AUGMENT_ENABLE` | false | Assertion augmentation strategy (AST extraction of existing assert, 3.4) | 5.9 |
| `RUNTIME_PROBE_ENABLE` | false | P0 runtime probe: at exception-raise time, captures the `exc.__traceback__` frame chain and local variable snapshots (zero trace overhead; 2026-09-29 core-defect fix makes it actually functional) | 5.22.1 |
| `KERNEL_SANDBOX_ENABLE` | false | G3 kernel-level sandbox: macOS Seatbelt (`sandbox-exec`) / Linux Landlock (`bwrap`) dual backend; platform-unsupported → fail-closed (does not silently degrade to un-isolated local, same policy as Docker-unavailable) | 5.22.3 |
| `AGENT_TELEMETRY_ENABLE` | false | G4 AgentTelemetry failure-detection benchmark: 10 built-in failure-pattern regex matches (zero LLM cost, pure observation), outputs Markdown report for experimental analysis consumption | 5.22.4 |
| `TESTLESS_VALIDATION_ENABLE` | false | G5 testless execution-irrelevant validation: four independently toggleable layers (AST symbol guard / mypy static check / naming-contract regression / import smoke); any layer failure → overall fail (conservative fail-closed policy) | 5.22.5 |
| `EXPERT_POOL_DEBATE_ENABLE` | false | G6 multi-agent debate convergence: top-K candidate debate convergence produces one `debate_revise` revised candidate (requires `EXPERT_POOL_ENABLE=true`; on LLM failure conservatively degrades back to the original verified list, does not block the main chain) | 5.22.6 |
| `RISK_APPROVAL_ENABLE` | false | G2 risk-tiered human approval loop: three-factor weighted scoring (confidence + patch impact + budget ratio) → low/medium/high → auto_merge / human_confirm / force_review | 5.22.2 |
| `DETECTION_FIRST_ENABLE` | false | W3 detection-first protocol (ADR-0015, "red-before-green" success criterion: an all-green first round means no defect detected and triggers one strengthened regeneration; terminal annotation red_then_green / all_green_unverified — evaluation must not count all_green_unverified as detection/repair success) | 5.19.5 |

See [QUICKSTART.md](QUICKSTART.md) and [.env.example](.env.example) for details.

### Multi-LLM Configuration Support

The system supports configuring multiple LLM providers, enabling API Key rotation and high availability:

```bash
# .env.local configuration example
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com/v1
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com/v1
LLM_2_MODEL_NAME=model-2
```

Usage in code:
```python
from config import LLM_CONFIGS, DEFAULT_LLM_CONFIG

# Get all configurations
all_configs: list[LLMConfig] = LLM_CONFIGS
# Get the default configuration (the first one)
default_config: LLMConfig | None = DEFAULT_LLM_CONFIG
```

For more configuration details, see [docs/api_reference.md](docs/api_reference.md) and [config.local.example](config.local.example).

---

## CLI Command Reference

### `python main.py run` — Run a single test task

```
python main.py run <target_file> [OPTIONS]

Arguments:
  target_file    Path to the Python file under test (must exist)

Options:
  --func, -f          Name of the function under test; omit to test all functions
  --max-iterations    Maximum number of repair iterations, default 3
  --coverage-threshold  Coverage threshold percentage, default 80.0
  --timeout           pytest execution timeout (seconds), overrides the EXECUTION_TIMEOUT config
  --json              Output results in JSON format (stdout carries pure JSON only; logs/progress go to stderr, making piping to jq easy)
```

> **Exit codes**: when any test task fails (including task crash), the process exits with `1`; when all pass, it exits with `0`, so it can be used as a gate in CI/scripts.

**Examples:**
```bash
# Test a single function
python main.py run examples/calculator.py --func divide

# Specify a maximum iteration count
python main.py run examples/buggy_library.py --func binary_search --max-iterations 5

# Output results as JSON
python main.py run examples/string_utils.py --func is_palindrome --json
```

### `python experiments/run_benchmark.py` — Batch benchmark

```
python experiments/run_benchmark.py [OPTIONS]

Options:
  --dataset, -d       Dataset name (examples/synthetic/swe_bench/defects4j_py)
  --subset, -s        Data subset (e.g. swe_bench_lite)
  --baselines, -b     Comma-separated list of baseline methods (default: aitester,plain_llm,single_agent)
  --output-dir, -o    Result output directory (default: experiments/results)
  --verbose, -v       Verbose log output
  --task-limit, -n    Limit the number of tasks to run
  --task-count, -c    Number of synthetic dataset tasks
  --parallel, -p      Number of parallel tasks (replaces the BENCHMARK_PARALLELISM environment variable)
  --timeout           Global execution timeout (seconds)
  --json              Output results in JSON format
  --enable-rag        Explicitly enable RAG retrieval augmentation (P1 ablation experiment; defaults to config.ENABLE_RAG)
  --save-state        Persist per-stage state to <output-dir>/raw/ (for P0 baseline comparison diagnostics)
```

**Examples:**
```bash
# Quick validation (2 tasks, single baseline)
python experiments/run_benchmark.py --dataset examples --task-limit 2 --baselines aitester

# Parallel execution (4 threads, 100 synthetic tasks)
python experiments/run_benchmark.py --dataset synthetic --task-count 100 \
    --baselines aitester,plain_llm,single_agent --parallel 4

# Run the aitester full system only (JSON is the default output, no --json switch needed)
python experiments/run_benchmark.py --dataset examples --baselines aitester
```

### `python main.py list-examples` — List example files

```
python main.py list-examples
```

## Datasets

| Dataset Name | Data Source | Task Count | Download Requirement |
|-----------|---------|-------|---------|
| `examples` | Built-in examples (calculator/buggy_library/string_utils) | 3 | No download needed |
| `synthetic` / `synth` | Locally generated, customizable scale | Configurable | No download needed |
| `swe_bench` | HuggingFace SWE-bench | 500 (lite) | Requires calling download_from_huggingface() |
| `defects4j_python` | Defects4J-Python dataset | Variable | Requires manual download |

For more details, see the [Performance Tuning Guide](docs/performance_guide.md), [API Reference](docs/api_reference.md), and [Usage Examples](docs/usage_examples.md).

## Tech Stack

- **LLM framework**: LangChain + LangGraph
- **Database**: MySQL (pymysql driver)
- **Vector database**: ChromaDB (RAG module)
- **Test framework**: pytest + pytest-cov
- **Command line**: Click
- **Datasets**: SWE-bench / Defects4J-Python (loaded via the HuggingFace datasets library)
- **Visualization**: matplotlib + pandas

## Benchmark Results

### Built-in Example Dataset (examples, 3 tasks)

| Task | Status | Coverage | Iteration Count | LLM Call Count |
|------|------|--------|----------|-------------|
| `calculator.py::divide` | ✅ PASS | 100% | 0 | 1 |
| `buggy_library.py::binary_search` | ✅ PASS | 100% | 1 | 2 (including retry) |
| `string_utils.py::is_palindrome` | ✅ PASS | 75% | 0 | 1 |

**Summary**: success rate **100%**, average coverage **91.7%**, average time **30.1s/task**.

### Synthetic Dataset Experiment (50 tasks, 3-baseline comparison, historical data snapshot)

> A data snapshot from one 50-task run (3-baseline comparison), used to demonstrate the multi-baseline methodology; not a performance commitment of the current version.

| Baseline Method | Success Rate (%) | Avg Coverage (%) | Avg Iteration Count | Avg Time (s) |
|---------|-----------|---------------|-------------|-------------|
| **AITester** | **68.0** | **98.0** | 1.26 | 47.2 |
| Plain LLM | 68.0 | 95.2 | 1.10 | 348.3 |
| Single Agent | 22.0 | 71.1 | 0.62 | 17.3 |

**Key findings**:
- AITester's success rate is on par with Plain LLM, but coverage is higher (98.0% vs 95.2%)
- AITester is **7.4x faster** (47.2s vs 348.3s), demonstrating multi-agent collaboration efficiency
- The Single Agent baseline performs significantly worse (22.0%), validating the necessity of the multi-agent architecture
- Statistical tests show the AITester vs Single Agent difference is significant (p < 0.001, Cohen's d = 0.848)

See `（工件已清除）` for detailed results (kept locally, not committed; the repo's `experiments/results/` only tracks a placeholder note, historical artifacts are excluded via .gitignore).

### SWE-bench Lite Experiment (20 tasks)

This batch of experiments was affected by API rate limits, and results were not archived to the repository; subsequent re-run data is kept in a local private directory (not committed).

**Repo-level verification (P0/P1, 2026-09-25)**: With `RepoExecutor`
(`REPO_LEVEL_EXECUTION=true`) on the official SWE-bench criterion (gold
`test_patch` before/after FAIL_TO_PASS/PASS_TO_PASS measurement), lite-20
results are in `（工件已清除）` §7:

- After data pipeline fix (`SWE_BENCH_ENRICHMENT` injecting real source) +
  execution environment fix (RepoExecutor repo-level clone + pip install -e +
  venv isolation) + patch pipeline fix (applicable unified diff via
  `git diff --no-index`), SWE-bench is still 0/20.
- P1 diagnosis (single-source tasks 0/7, after venv isolation + fixed
  pipeline) failure categorization: 5/7 `LLM_BREAKS_IMPORT` (LLM rewrite of
  the target file broke sqlfluff's plugin naming contract, e.g. renaming the
  `Rule_L027` class → entire import chain crashed) + 2/7 `EMPTY_LLM_PATCH`
  (LLM produced no fix). **Pipeline and environment are fully fixed; 0/N is
  the LLM engine's fix-quality boundary** (free-tier small model on real
  repo-level code), not a pipeline or environment issue.
- Multi-file tasks (13/20 multi-source) have no positive signal before the
  engine-capability breakthrough (ON/OFF both 0/N); cross-file gain
  validation requires a stronger model + full-repo source context.

Paper positioning: SWE-bench 0/N is written into the "Limitations" section
(engine fix-quality boundary); the main experiments still use the synthetic
dataset (88% vs 60% vs 8%, p=0.002 significant).

### Key Repair Records

- `_validate_parametrize` switched from regex to ast parsing, resolving the parameter misjudgment problem caused by nested lists
- Safety guards added to `_patch_applier_node` (non-empty, ≥10% length, contains a function definition)
- Secondary parametrize validation in the Generator, avoiding the LLM repeatedly generating the same wrong code


## FAQ

### Q: `ModuleNotFoundError` at runtime

**Cause**: the test file and the module are not in the same directory; Python cannot find the module under test.
**Fix**: make sure the `target_file` path is correct, or check the `module_name` configuration.

### Q: LLM returns non-JSON output

**Cause**: the model output does not match the expected format.
**Fix**: check the `LLM_N_*` settings in `.env.local` (model name, Base URL) and ensure the API Key is valid.

### Q: Coverage is always 0%

**Cause**: the coverage statistics file was not generated or has a wrong path.
**Fix**: check that `pytest-cov` is installed correctly and that the `--cov` argument is being passed.

### Q: Synthetic dataset success rate is low (< 10%)

**Cause**: the synthetic dataset's bug patterns are relatively complex; a single repair round may not cover all scenarios.
**Fix**:
1. Increase `MAX_ITERATIONS` (default 3, can be raised to 5)
2. Enable RAG augmentation: `ENABLE_RAG=true`
3. Switch to a stronger model tier (set `LLM_1_MODEL_NAME`; the built-in default is the official DeepSeek `deepseek-flash`)

---

## Technical Documentation

- [Algorithm Design Document](docs/algorithm_design.md): formal description of the core algorithm
- [Failure Case Analysis](docs/failure_analysis.md): root-cause analysis of failure rates and an improvement roadmap (historical data snapshot)
- [Performance Tuning Guide](docs/performance_guide.md): parallel execution, RAG singleton, timeout configuration, profiling benchmarks
- [API Reference](docs/api_reference.md): module interface documentation
- [Usage Examples](docs/usage_examples.md): programming interfaces and CLI usage
- [Review Round Records](CHANGELOG.md): rounds 6–11 audit & conservative optimization (P1/P2 defect fixes + regression guards; see the 2026-09-26 comprehensive-audit batch in CHANGELOG)
- [Advanced Switches](QUICKSTART.md): structured tracing / multi-candidate patches / cost-aware routing (all off by default, enable as needed)
- [Historical Optimization Records](docs/history/optimization_plan.md): archived historical round optimization plans and reports (`docs/history/`, not currently maintained)

---

## Contribution Guide

Contributions are welcome! Read the [Contributing Guide](CONTRIBUTING.md) to learn how to participate in project development.

---

## Iteration records

> Archived to [docs/history/README.en_iteration_log.md](docs/history/README.en_iteration_log.md)
> (P1-9: historical snapshots with stale baseline numbers moved out of core docs).

## License

MIT License
