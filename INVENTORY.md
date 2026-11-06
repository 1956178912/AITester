# Replication package inventory

This file is the open-science checklist map. It states, for each of
the six review questions, what the package can and cannot do as it ships.

**The headline numbers of the study are recomputed without a model call.** Two
paths in the package do consume LLM quota, and both are *regeneration*, not
evidence for a reported number: `reproduce.sh --dataset synthetic --full` reruns
one pre-registered batch under seed 42, and `experiments/run_main_batch.py` reruns
the three-seed protocol. Neither is on the path from an archived artifact to a
reported number. The zero-LLM path is `make reproduce-zero-llm` (L0) and
`make reproduce-zero-llm-l1` (L0 plus the hour-scale cosmic-ray `Mut@k`
re-execution). Both write `experiments/results/REPRODUCTION_REPORT.md`, which
prints the outcome of every command instead of only the passing ones.

## The six criteria

| Criterion | Status | Evidence in the package |
| --- | --- | --- |
| Downloadable | yes | One archive. Every verdict is stored as JSON or Markdown and is readable without executing anything: per-task rows under `experiments/results/`, the measurement-integrity notes `docs/MEASUREMENT_INTEGRITY.md`. |
| Archived | not yet | No DOI exists at the time of writing. The archival deposit is a submission action the authors take; until then the review mirror is the only copy, and it is anonymized. |
| Documented | yes | This file, `REPLICATION.md` (three reproduction paths, prerequisites, calibers), Appendix A of the manuscript (artifact-to-claim map with markers for what is distributed as data versus as a command), and the gate inventory in the repository itself (`scripts/gates/` with the `Makefile` targets that invoke them). |
| Complete | pending the rerun | The batch artifacts this checklist described were deleted on 2026-11-04 (see "Corpus state" below); the recomputation chain is intact but has nothing to read until the rerun lands. See "What does not recompute" below. |
| Exercisable | yes for the tracked subset | `make install` then `make reproduce-zero-llm`. Only public modules and the shipped configuration are used. A fresh clone exercises the corpus that is tracked in git; the heavier per-task records travel with the archive rather than with the clone. |
| Licensed | code yes, data stated here | Code: MIT, `LICENSE`. Our own artifacts: dedicated to CC0-1.0, which is recorded in this file rather than in a second license text, and belongs in the deposit. Third-party benchmarks (QuixBugs, ULT, SWE-bench) stay under their upstream licenses, and only derived outputs are redistributed. |

## Corpus state: measured, not inherited

`git clone` and "the archive we hand to reviewers" are not the same corpus, so
both counts are reported rather than blended. The 2026-11-04 direction reset
deleted every archived batch artifact, so the historical row below is kept only
as the provenance of the numbers the paper no longer prints.

| Caliber | Batch files | Trace directories | Trace records | Checksum manifests |
| --- | --- | --- | --- | --- |
| Working tree, as measured 2026-11-04 after the purge | 0 | 0 | 0 | 1 (`prompt_artifacts_2026-10-15/SHA256SUMS`) |
| Historical, before the purge (working tree / tracked) | 34 / 16 | 21 / 14 | 1,456 / 760 | 9 / 4 |

The four files that remain under `experiments/results/` are the instruction
artifact manifest (`PROMPT_ARTIFACTS.json/.md`, `PROMPT_CARD.md`, `SHA256SUMS`),
which `prompt-artifacts-check --strict` reads; it is a documentation lock, not
experiment data. All other readings are **[Pending rerun]**.

Counts come from `git ls-files experiments/results` for the tracked row and the
glob in `tests/_corpus_guard.py` for the working-tree row. The guard's
`_FULL_CORPUS_*` constants (34/21/1456) are **skip floors for corpus presence**,
not a composition count: with the corpus absent the guard reports
`全归档语料不在场` and skips rather than failing, so a green suite here says
nothing about corpus completeness.

## What the zero-LLM chain does as the package ships

Measured on 2026-11-04 after the corpus purge: `python scripts/reproduce_zero_llm.py`
reports **2/6 commands passing with 4 explicit `[SKIP]`** and
**SHA256SUMS 0 directories passing (0 files) / 0 failures / 13 absent**. The chain
is intact; it simply has nothing to read until the rerun lands, and a command with
nothing to read is reported as skipped, never folded into a pass.

One branch was fixed to degrade like its siblings rather than crash:
`experiments/emse_stats_extensions.py` had no precondition probe, so with the
regenerated three-arm batches absent it exited `rc=1` on a `FileNotFoundError`
instead of `[SKIP]`. The probe now keys on the files that script actually reads.

| Command | Recomputes | State measured 2026-11-04 |
| --- | --- | --- |
| `experiments/emse_stats_extensions.py` | Wilson intervals, effect sizes, exact tests, bootstrap delta intervals | skipped (reconstructed three-arm batches absent) |
| SWE-bench Lite infrastructure disclosure | the disclosure note that bounds the SWE-bench claim | passes |
| citation traceability audit | that every numeric external citation carries a DOI or arXiv identifier | passes |
| `experiments/emse_stats_report.py` | MDE and power report | skipped (`main_batch` withdrawn) |
| `experiments/emse_optimization.py` | mutation by detection cross-check, over-red classification | skipped (`main_batch` withdrawn) |
| `experiments/pass_matched_sensitivity.py` | declaration rate and false-fix calibers | skipped (`main_batch` withdrawn) |

## What does not recompute

1. The pooled pairing of the protocol-matched comparison: the per-arm batch files
   it reads are no longer in the package, and no aggregator script ships for them.
   This is a standing gap, not a purge artifact.
2. Aggregation behind `tab:protocol` ships its per-arm rows but no aggregator script
   (rows regenerate, the table does not).

Numbers that previously appeared here (a 3-pass reading, "489 files across 8
directories verified", "5 absent") describe the pre-purge corpus and are withdrawn
rather than restated.

## Entry points named by the manuscript

All of the following files exist in the package. `experiments/` scripts are
zero-LLM unless stated otherwise.

| Entry point | Reads | Writes or reports |
| --- | --- | --- |
| `scripts/reproduce_zero_llm.py` | archived batch JSON | `REPRODUCTION_REPORT.md` and `.json` |
| `experiments/statistical_analysis.py` | batch JSON, `--pool-seeds` for pooled rows | RQ1 pairing reports; the frozen 2026-10-25 transcription now lives in `docs/history/` (batch-generation reading), and both copies are regenerable from the rerun |
| `experiments/emse_stats_extensions.py` | three-arm regenerated batches | `experiments/results/emse_stats_extensions_20261025/STATS_EXTENSIONS.json` |
| `experiments/emse_quixbugs_mutk_full.py`, `experiments/emse_ult_mutk_full.py`, `experiments/emse_test_sanity_audit.py` | archived suites, cosmic-ray mutants (L1) | `*\_mutk_full_20261015/`, `emse_test_sanity_20261015/` (absent from the mirror until run) |
| `experiments/emse_dsl_extend_recheck.py` (`--from-corpus`) | the archived 607-clause corpus | compilability re-score without the author-side cache |
| `experiments/emse_gold_conformance_audit.py`, `experiments/emse_ult_gold_diagnosis.py` | benchmark material, executed locally in a temporary directory | gold-side material claims |
| `experiments/oracle_quality_replay.py`, `experiments/smt_witness_batch.py` | archived oracle responses | oracle quality and SMT witness readings |
| `experiments/emse_docstring_anchor_analysis.py`, `experiments/emse_docstring_augment_analysis.py` | anchor and augment arms | the specification-anchor tables |
| `scripts/run_all_tests.py` | the whole test surface (gates chain, pytest collection, LLM faces) | `REPORT.json`, `PROGRESS.json`, `SMOKE_GATE.json`, `DONE.json` in its run directory |

### One command, two profiles (`scripts/run_all_tests.py`)

Both profiles cover **the same set of faces**; they differ only in how much of each face
runs. `smoke` takes one item per face — one node id per pytest file (collected with
`--collect-only -qq`), one task per "model × arm × dataset face", plus every non-`test`
gate target of the chain — and answers only "is the assembly intact". `full` runs the
maximum: `make test-cov` (whole suite plus `coverage.xml`), `make gates` (the whole chain),
and every dataset face to completion. The default profile `both` sequences them and will
not start the full profile without a passing `SMOKE_GATE.json` whose fingerprint matches
the matrix shape, protocol values, `HEAD`, the working-tree digest and the **per-model
concurrency resolution** used by that run, so an edited file — or a different `-p` —
invalidates an earlier smoke run instead of letting it vouch for the change.

Face names come from the dataset loader registry at run time, with four guards: an
unregistered name is refused (the loader degrades unknown names to a three-item built-in
face, which would fake "every face run"); faces that resolve to the same data are
deduplicated by task count plus first/last task id, so one batch is never paid for twice;
a face with no data on disk is dropped with disclosure; and the zero-cost pre-spend
dataset gate now feeds face selection — a face the gate judges unable to produce a verdict
is dropped by name instead of being paid for anyway. Measured on this machine after
dedupe: `bugsinpy` 8 + `quixbugs` 50 + `swebench` 225 + `testgeneval` 160 + `ult` 200 =
643 tasks per model-arm cell (under the batch strict calibers, `swebench` keeps 217 of its
225 — see below).

`AITESTER_DATASET_STRICT_INSTANCE_CODE` and `AITESTER_DATASET_STRICT_TEST_CODE` drop,
respectively, tasks whose source falls back to the issue text and tasks whose official test
material can never decide a verdict, so the denominator counts only what can be judged; the
same helper sets `PATCH_EVIDENCE_OFFICIAL_TESTS_ENABLE`, which lets the evidence gate run a
task's official tests against the patched source inside the loop and release a
gold-backed patch instead of rolling it back. Counting the faces, running the gate and
executing the batch all read that one helper, so a face cannot be counted under one
caliber and paid under another.

Unattended operation: `RUNNING.lock` refuses a concurrent run (and is taken over when the
recorded pid is gone), `PROGRESS.json` is rewritten atomically on every tick with stage
index, done-of-total, ETA, overall share and silent seconds, and `DONE.json` records the
terminal state. A stage that goes silent past `--stall-after` or overruns its wall clock
has its **whole process group** terminated and counts as one failed attempt; run-level
caps `--max-wall-hours` and `--max-stalls` stop opening new stages and record a named
failed stage, so a shortened run can never read as a complete one. Parallelism is capped
at 75% of physical cores and each run gets its own empty temp root, because the inner
pytest puts that directory on `sys.path`.

LLM parallelism per cell is no longer a constant: each "model × arm" stage resolves
provider allowance ∩ machine allowance ∩ an explicit `--llm-parallel`, taking 80% of the
registered allowance (`MODEL_RATE_LIMITS` — `deepseek-flash` 2500 in-flight requests,
`deepseek-v4-pro` 500, `mimo-v2.6-pro` 100 requests/min and 10M tokens/min), where an
in-flight allowance caps concurrency directly but a requests-per-minute allowance only
caps the launch rate and leaves concurrency to the machine side
(min(cores × 2.4, memory term, 40), floor 2, conservative on sampling failure). The
resolution is printed per stage, hashed into the smoke fingerprint, and an explicit
`--llm-parallel` above the provider line is clamped to it with a note — oversending buys
429s, not throughput.

## Model-consuming paths, kept separate

| Path | What it costs | Why it is not evidence for a reported number |
| --- | --- | --- |
| `bash reproduce.sh --dataset synthetic --full` | 87 tasks, three arms, seed 42 | it regenerates a batch under the pre-registered configuration |
| `python experiments/run_main_batch.py` | three seeds of the main protocol | same, at the pooled scale |
| `Dockerfile.repro` build and run | the above, containerized and provenance-stamped | it demonstrates the pipeline, it does not recompute a table |

Credentials are never part of the package. `.env.local` is not distributed, and
scripts that need it warn and stop rather than silently substituting a default.

## Preregistrations and protocol text

`docs/preregistration.md` plus six study-level preregistrations under
`docs/study/` (`DF_SPEC_PREREG_2026-10-16.md`,
`DOCSTRING_ANCHOR_PREREG_2026-10-17.md`,
`DOCSTRING_AUGMENT_PREREG_2026-10-17.md`,
`QUIXBUGS_SPECIR_EXPAND_PREREG_2026-10-14.md`,
`ULT_DF200_PREREG_2026-10-17.md`, `ULT_DFSMOKE_PREREG_2026-10-17.md`).
The instruction artifacts measured in the study are extracted verbatim from
source and pinned by SHA-256, so the exact prompt text is checkable from the
archive.

## Open items before the archival deposit

1. Reserve the DOI and attach the deposit, then replace the placeholder in the
   data-availability statement of the title page and the manuscript.
2. Carry the CC0 dedication for the artifacts into the deposit as its own
   statement rather than as a line in this file.
