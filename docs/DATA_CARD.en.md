> **Language**: [中文版](DATA_CARD.md) | English (this document)

# Data Card

Last updated: 2026-10-06 (AH1: §4 licensing authoritatively verified —
QuixBugs MIT confirmed [L1 precondition lifted], BugsInPy has no SPDX
license [new L2 decision gate registered]; previously AA2: §2 registers the
`max_pattern_repeat` mitigation for the sampling-repetition bias; previously
Z6: closing a data-governance gap — data provenance used to live only in
MODEL_CARD §3 with no standalone card; review item R15)

## 1. Dataset Overview

| Dataset | Loader name | Status | Purpose |
|---------|-------------|--------|---------|
| Synthetic defect template library | `synthetic` | ✅ in use for the main batch (n=50 tasks) | main experiments / ablations |
| QuixBugs (Python subset) | `quixbugs` | loader ready, **never run** | real-defect ladder L1 |
| BugsInPy | `bugsinpy` | loader ready, **never run** | real-defect ladder L2 |
| SWE-bench Lite | `swe_bench` | historical 0/20 smoke run | repo-level (target mismatch, see below) |

## 2. Synthetic Template Library (current main-batch benchmark)

- **Origin**: entirely hand-written by the project author (8 pattern pools,
  50 unique defect patterns after dedup by name; `BASELINE.yaml
  synthetic_templates` is the single source of truth, self-verified by
  `scripts/verify_synthetic_templates.py` against three invariants);
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
   `scripts/power_analysis.py`).

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
  guarded by CI `scripts/check_bilingual_docs.py --strict`);
- pattern totals / main-batch composition numbers use `BASELINE.yaml` as the
  single source of truth; this card describes semantics only and does not
  carry "current numbers";
- every new data source must be registered here: origin, construction method,
  gold-material location, leak-control measures, and license-verification
  conclusion.
