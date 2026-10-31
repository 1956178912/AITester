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
| Downloadable | yes | One archive. Every verdict is stored as JSON or Markdown and is readable without executing anything: per-task rows under `experiments/results/`, the withdrawal ledger `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md`, the measurement-integrity notes `docs/MEASUREMENT_INTEGRITY.md`. |
| Archived | not yet | No DOI exists at the time of writing. The archival deposit is a submission action the authors take; until then the review mirror is the only copy, and it is anonymized. |
| Documented | yes | This file, `REPLICATION.md` (three reproduction paths, prerequisites, calibers), Appendix A of the manuscript (artifact-to-claim map with markers for what is distributed as data versus as a command), and Appendix F (gate inventory and commands). |
| Complete | with three disclosed gaps | See "What does not recompute" below. |
| Exercisable | yes for the tracked subset | `make install` then `make reproduce-zero-llm`. Only public modules and the shipped configuration are used. A fresh clone exercises the corpus that is tracked in git; the heavier per-task records travel with the archive rather than with the clone. |
| Licensed | code yes, data stated here | Code: MIT, `LICENSE`. Our own artifacts: dedicated to CC0-1.0, which is recorded in this file rather than in a second license text, and belongs in the deposit. Third-party benchmarks (QuixBugs, ULT, SWE-bench) stay under their upstream licenses, and only derived outputs are redistributed. |

## Two corpus counts, because they differ

`git clone` and "the archive we hand to reviewers" are not the same corpus.
Heavy per-task records are kept out of version control on purpose, so both
counts are reported here rather than blended into one.

| Caliber | Batch files | Trace directories | Trace records | Checksum manifests |
| --- | --- | --- | --- | --- |
| Working tree, which is what the review archive is built from | 34 | 21 | 1,456 | 9 |
| Tracked in the repository, which is what a fresh clone yields | 16 | 14 | 760 | 4 |

Counts are `git ls-files experiments/results` for the tracked row and the glob in
`tests/_corpus_guard.py` for the working-tree row. The guard pins the
working-tree reading as a floor that only rises.

## What the zero-LLM chain does as the package ships

The chain runs six L0 commands and reports each of them separately. Three pass,
and three report `skipped` because their source batch is the withdrawn main
batch. A skip is printed as a skip; it is never folded into a pass. Checksums
verify 8 directories covering 489 files with no failures, and list 5 directories
as absent.

| Command | Recomputes | State in the shipped package |
| --- | --- | --- |
| `experiments/emse_stats_extensions.py` | Wilson intervals, effect sizes, exact tests, bootstrap delta intervals | passes |
| SWE-bench Lite infrastructure disclosure | the disclosure note that bounds the SWE-bench claim | passes |
| citation traceability audit | that every numeric external citation carries a DOI or arXiv identifier | passes |
| `experiments/emse_stats_report.py` | MDE and power report | skipped, source batch withdrawn |
| `experiments/emse_optimization.py` | mutation by detection cross-check, over-red classification | skipped, source batch withdrawn |
| `experiments/pass_matched_sensitivity.py` | declaration rate and false-fix calibers | skipped, source batch withdrawn |

## What does not recompute

1. The three historical tables above. Their per-task rows live in the withdrawn
   archive, so they recompute only against a corpus that is no longer
   distributed. The paper labels every such number historical, and the labels
   are the reader's protection.
2. The pooled pairing of the protocol-matched comparison. Its seven per-arm
   batch files ship under `experiments/results/b1_lite_20261025/`, and the
   pairing is recomputable from those rows, but the package carries no aggregator
   script for them.
3. The exclusion recompute behind the gold-material impact table. No stored
   artifact of it survived the cleanup, and there is no standalone entry point.

## Entry points named by the manuscript

All of the following files exist in the package. `experiments/` scripts are
zero-LLM unless stated otherwise.

| Entry point | Reads | Writes or reports |
| --- | --- | --- |
| `scripts/reproduce_zero_llm.py` | archived batch JSON | `REPRODUCTION_REPORT.md` and `.json` |
| `experiments/statistical_analysis.py` | batch JSON, `--pool-seeds` for pooled rows | RQ1 pairing reports, including the frozen copy `docs/study/RQ1_PAIRING_REPORT_2026-10-25.md` |
| `experiments/emse_stats_extensions.py` | three-arm regenerated batches | `experiments/results/emse_stats_extensions_20261025/STATS_EXTENSIONS.json` |
| `experiments/emse_quixbugs_mutk_full.py`, `experiments/emse_ult_mutk_full.py`, `experiments/emse_test_sanity_audit.py` | archived suites, cosmic-ray mutants (L1) | `*\_mutk_full_20261015/`, `emse_test_sanity_20261015/` (absent from the mirror until run) |
| `experiments/emse_dsl_extend_recheck.py` (`--from-corpus`) | the archived 607-clause corpus | compilability re-score without the author-side cache |
| `experiments/emse_gold_conformance_audit.py`, `experiments/emse_ult_gold_diagnosis.py` | benchmark material, executed locally in a temporary directory | gold-side material claims |
| `experiments/oracle_quality_replay.py`, `experiments/smt_witness_batch.py` | archived oracle responses | oracle quality and SMT witness readings |
| `experiments/emse_docstring_anchor_analysis.py`, `experiments/emse_docstring_augment_analysis.py`, `experiments/emse_df_spec_analysis.py` | anchor and augment arms | the specification-anchor tables |
| `experiments/analyze_t1_b2_main_batch.py` | main-batch rows | the regenerated-generation comparison |

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
3. Decide whether the withdrawn generation stays out of the deposit. Keeping it
   out is the current choice, and it is why the historical tables are labelled
   rather than re-estimated.
