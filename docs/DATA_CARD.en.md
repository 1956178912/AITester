> **Language**: [中文版](DATA_CARD.md) | English (this document)

# Data Card

Last updated: 2026-10-15 (§6 adds the Data Availability Statement:
included artifacts, per-source licensing citations, items not included
(raw LLM responses), and the deposit placeholder. Previously 2026-10-14 (§1 dataset overview refreshed: new ULT row
(real benchmark, mutation main-metric scenario; subset in use since
2026-10-13/14, n=25–46) + QuixBugs status updated to multi-batch usage
(D1 A/B / spec_ir pilot / recalibration n=50; positioning remains L1, the
R20 near-saturation and memorization-contamination statements stand).
Previously 2026-10-08 R20: §4 adds the QuixBugs positioning downgrade —
near-saturation (citing 2025–2026 cross-model coordinates) + memorization-
contamination risk, limited to L1 pipeline validation; §1 status column
updated to "single-arm rerun (not the formal E4 execution)". Earlier:
2026-10-07 AN1: §4 registers the TestGenEval L2-candidate evaluation —
CC BY-NC 4.0, verified against the LICENSE text; joins BugsInPy in the
non-clean-license gate; AH1: §4 licensing authoritatively verified —
QuixBugs MIT confirmed [L1 precondition lifted], BugsInPy has no SPDX
license [new L2 decision gate registered]; AA2: §2 registers the
`max_pattern_repeat` mitigation; Z6: standalone data card created (R15)))

## 1. Dataset Overview

| Dataset | Loader name | Status | Purpose |
|---------|-------------|--------|---------|
| Synthetic defect template library | `synthetic` | ✅ in use for the main batch (n=50 tasks; parameterized 87/120 variants used by confirmatory/recalibration batches) | main experiments / ablations |
| QuixBugs (Python subset, complete 50 programs) | `quixbugs` | ✅ multi-batch in use (D1 A/B / spec_ir pilot / recalibration n=50; positioning remains L1 — near-saturation + memorization statements in §4) | real-defect ladder L1 |
| ULT (UnLeakedTestBench, local clone) | `ult` | ✅ subset in use (ult_lite46 / specir probe / recalibration / Mut@k subset, n=25–46; **detection-caliber fitness under review** — generated tests show zero detections 0/45, 0/24 while gold assertions demonstrably fail on the buggy code, i.e. "LLM tests produce no red") | real benchmark (mutation main metric Mut@k / cyclomatic ≥10 filter) |
| BugsInPy | `bugsinpy` | loader ready, **never run** | real-defect ladder L2 |
| SWE-bench Lite | `swe_bench` | historical 0/20 smoke run (**2026-10-13 erratum: an API 429 rate-limit infrastructure failure, no valid capability conclusion**) | repo-level (target mismatch, see below) |

## 2. Synthetic Template Library (current main-batch benchmark)

- **Origin**: entirely hand-written by the project author (8 pattern pools,
  50 unique defect patterns after dedup by name; `BASELINE.yaml
  synthetic_templates` is the single source of truth, self-verified by
  `scripts/tools/verify_synthetic_templates.py` against three invariants);
- **Construction**: each pattern carries a buggy `template` / `fixed` / gold
  `test_cases` triple; instantiation only appends a noise comment
  (`# noise_seed=<0-9999>`) and neutralizes task ids (`task_0000..`, the P1-4
  leak fix — the file name used to embed the pattern name, which equals the
  answer); gold-test imports are rewritten in sync (`_neutralize_gold_imports`);
- **Main-batch composition**: n=50, seed=42, 3 baselines; difficulty L1–L5
  distribution {15,10,10,8,7}; 8 cross-file tasks; bug types: assertion 30 /
  runtime 20; patterns are sampled with repetition (e.g.
  `import_chain_type_contract` appears 10 times) — mitigated as of AA2
  (2026-10-06) via `SyntheticDataset(max_pattern_repeat=...)` /
  `run_benchmark --max-pattern-repeat` (opt-in; legacy behavior and seed=42
  reproducibility unchanged); enabling it for future main-batch reruns is
  recommended;
- **Gold-material schema**: `metadata["test_cases"]` (gold tests),
  `metadata["fixed"]` (single-file gold patch), `fixed_module_code`
  (cross-file), `pass_to_pass` (P2P regression set). Gold material only enters
  the result rows' `task_metadata` and **never enters any LLM prompt**.

## 3. Known Biases and Limitations (honest statement)

1. **Question author = grader**: the gold tests / gold patches / task templates
   are all hand-written by the project author, so the "ground truth" for
   detection / repair is strongly coupled with the tasks the system faces —
   internal validity is limited and positive results must not be extrapolated
   (the ladder plan in `docs/design/real_benchmark_upgrade.md` exists for
   exactly this reason);
2. **Distribution bias**: function-level Python only; template defect types
   concentrate in assertion / runtime categories and do not represent the
   real-repository defect distribution;
3. **Leak-channel status**: `problem_statement` (= the pattern description,
   literally the defect answer) is currently only consumed by the
   injection scanner and never enters any prompt — this "no-prompt-consumer"
   invariant is **now locked by a static guard test** (AF-D, 2026-10-06:
   tests/test_af_batch.py; any new prompt-side consumption must explicitly
   update this card and that test);
4. **Statistical power**: at n=50 with a 2% detection baseline, the test has
   insufficient power for a 10pp difference (recomputable via
   `scripts/tools/power_analysis.py`).

## 4. Real-Defect Ladder (L1/L2)

- **QuixBugs**: parsed from local directories (`python_programs/` buggy +
  `correct_python_programs/` fixed + `python_testcases/` official tests);
  missing directories degrade gracefully to an empty dataset with a warning;
  the data directory is injected via `AITESTER_QUIXBUGS_DATA` (not distributed
  with the repository — fetch the upstream data yourself);
- **BugsInPy**: manifest-JSONL format (project / bug_id / buggy_code /
  fixed_code / test_code); the last task-id segment is a ≤30-char neutral
  module name (to avoid leaking defect semantics); injected via
  `AITESTER_BUGSINPY_DATA`;
- **TestGenEval (L2-candidate evaluation registration, AN1, 2026-10-07;
  not loaded, never run)**: `facebookresearch/testgeneval` (Jain et al.,
  ICLR 2025, arXiv:2410.00752) — a real-repository-context unit-test
  generation/completion benchmark (1,210 code/test file pairs / 68,647
  tests / 11 actively maintained Python repos, adapted from SWE-bench),
  same-domain with this project's "test generation" thesis and a closer fit
  than BugsInPy's "defect repair" framing; **license: CC BY-NC 4.0** (the
  GitHub API license field reports `spdx_id=NOASSERTION`; the LICENSE text,
  verified 2026-10-07, is Attribution-NonCommercial 4.0 International) —
  usable for non-commercial academic research with attribution, but
  commercial use and redistribution of derived artifacts are restricted;
  it joins BugsInPy in the "non-clean-license" gate (the three-way choice
  below applies equally), to be decided side by side when L2 is chartered;
- **Licensing** (AH1, authoritatively verified via the GitHub API on
  2026-10-06 and recorded here):
  - **QuixBugs: MIT License (verified — the L1/E4 precondition is lifted)**
    — the `license` field of `api.github.com/repos/jkoppel/QuixBugs`
    reports `spdx_id=MIT` (verified 2026-10-06); **data fetched** (batch
    AJ, 2026-10-06): local `data/quixbugs` (gitignored, not committed),
    commit `4257f44b0ff1181dedaedee6a447e133219fcebf`; zero-LLM loader
    smoke measured 50 programs loaded and 41 with the complete gold
    triplet (the 9 tasks without official tests get detection=None per the
    M1 rule and stay out of the denominator);
  - **QuixBugs positioning downgrade (R20, 2026-10-08 R2) — near-saturation +
    memorization-contamination risk; positioned for L1 pipeline validation
    rather than external-validity claims**:
    - **Near-saturation**: 2025–2026 cross-model coordinates show frontier
      models near the ceiling — GPT-o1 40/40, GPT-4o 38/40, ThinkRepair /
      ContrastRepair 40/40 (40 = the full QuixBugs Python subset),
      claude-code adapter resolve ≈80.75% (**aggregated sources; individual
      figures pending primary-source verification**); this project's
      measurable caliber 90.2%/87.8% (37/41, 36/41) sits below the
      saturation frontier and is not SOTA;
    - **Memorization-contamination risk**: QuixBugs is a small public
      benchmark (40 programs) and is suspected of training-set contamination
      (consistent with this project's hygiene stance on retiring SWE-bench
      Verified);
    - **Use limited to** "pipeline-usability validation" (verifying that the
      real-benchmark path runs, and that gold material / package structure /
      evidence-gate behavior are observable); **external-validity claims
      migrate** to BugsInPy (license pending, below) or TestGenEval (CC BY-NC
      gate).
    - Citation discipline: citing its numbers requires noting "M1 measurable
      caliber + near-saturated + no external-validity claim" (see
      `docs/design/repair_caliber_matrix.md`).
  - **BugsInPy: no SPDX-detectable license (new compliance gate — a user
    decision is required before L2 runs)** — the `license` field of
    `api.github.com/repos/google/bugsinpy` is null (verified 2026-10-06),
    i.e. the upstream repository declares no license and default copyright
    applies; mitigation: local research-only use (gitignored, not
    distributed with the repository), but **this does not constitute full
    compliance**. Before chartering L2, pick one: ① contact upstream for
    written permission; ② switch to a licensed real-defect benchmark
    (e.g. the MIT-licensed SWE-bench family / Multi-SWE-bench); ③ accept
    the risk with dual registration in this card and the global decision
    log. QuixBugs L1 (E4) is unaffected and can proceed.

## 5. Maintenance Conventions

- This card is updated together with dataset changes (bilingual pairing is
  guarded by CI `scripts/gates/check_bilingual_docs.py --strict`);
- pattern totals / main-batch composition numbers use `BASELINE.yaml` as the
  single source of truth; this card describes semantics only and does not
  carry "current numbers";
- every new data source must be registered here: origin, construction method,
  gold-material location, leak-control measures, and license-verification
  conclusion.

## 6. Data Availability Statement

- **Included with the repository**:
  - Synthetic defect template library (`synthetic`): 8 pattern pools holding
    the buggy / `fixed` / gold `test_cases` triple of 50 unique defect
    patterns after dedup by name, defined in
    `src/datasets/synthetic_dataset.py`; the pattern total uses
    `BASELINE.yaml`'s `synthetic_templates` as the single source of truth
    (see §2);
  - Aggregated result artifacts (partially committed): `experiments/results/`.
    The batch JSONs, statistical reports and `SHA256SUMS` under
    `experiments/results/main_batch/` are committed (2,029 files measured with
    `git ls-files`); the remaining batch directories are ignored by
    `.gitignore` line 158 (`experiments/results/**`) and only selected
    artifacts/checksum files were force-added (18 of the 24 `SHA256SUMS*`
    files under `experiments/results/` are git-tracked);
  - Replication notes: `REPLICATION.md` at the repository root (environment,
    zero-LLM recomputation path, expected artifacts and known deviations).
- **Not included with the repository**:
  - **Raw LLM responses**: LLM responses are only written to the local file
    cache, whose default directory is the user cache directory
    (`XDG_CACHE_HOME` or `~/.cache/aitester/llm`, `src/agents/llm_client.py`);
    the historical in-tree cache directory `src/cache/` is excluded by
    `.gitignore` lines 66–67 (verbatim: `# LLM 文件缓存（本地优化产物，
    避免重复提交）` / `src/cache/`). That is, **the repository contains no raw
    LLM responses**, so the original executions cannot be replayed offline —
    only the metrics can be recomputed offline;
  - Upstream third-party dataset bodies (QuixBugs / BugsInPy / TestGenEval)
    are not distributed here; users fetch them under the upstream licenses:
    QuixBugs is injected via `AITESTER_QUIXBUGS_DATA` and the local
    `data/quixbugs` directory is gitignored (see §4).
- **Licensing status** (quoted from §4 of this card and the repository
  `LICENSE`, verbatim):
  - This repository's software: `MIT License` (`LICENSE` line 1),
    `Copyright (c) 2026 AITester Contributors` (`LICENSE` line 3);
  - QuixBugs: "**QuixBugs: MIT License (verified — the L1/E4 precondition is
    lifted)**" (§4);
  - BugsInPy: "**BugsInPy: no SPDX-detectable license (new compliance gate —
    a user decision is required before L2 runs)**" (§4);
  - TestGenEval (L2 candidate, not loaded, never run): "**license: CC BY-NC
    4.0**" (§4);
  - Synthetic defect template library: hand-written by the project author
    (§2); this card does not declare a separate redistribution license for the
    synthetic templates. [TO BE COMPLETED: redistribution license statement
    for the synthetic template library]
- **Deposit and contact**: [TO BE COMPLETED: Zenodo DOI / archival plan];
  [TO BE COMPLETED: corresponding author and contact email]. Citation
  metadata lives in `CITATION.cff` at the repository root (which already
  records the pending DOI as a YAML comment).
