# Changelog

> Last updated: 2026-10-27

This file records externally visible changes only; round-by-round history is archived below.

## [Unreleased]

### Added
- Dependency-exemption expiry gate (DF round): `make dependency-audit` and CI run pip-audit
  **without** `--ignore-vuln` — a fix version appearing, an unregistered advisory, or a
  version drift from `requirements.lock` turns the gate red; the rationale is locked by a
  static scan of `src/`. Offline runs disclose `[SKIP]`; `--require-audit` turns "cannot
  verify" red (37 test locks).

### Changed
- Regenerated the paper citation-key snapshot (DG round): the manuscript changed after the
  snapshot, so `docs/study/PAPER_CITATION_KEYS.md` was recomputed (64 lines, six corrected
  per-form counts); the snapshot and citation-chain tests are green.
- Rebuilt the submission PDFs (DE round): 70 pages, `refs.bib` 79 entries ↔ 79 `\bibitem`s, 0 undefined citations;
  the old page/entry counts in `docs/study/PAPER_BUILD.md` and `paper/tex/README.md` now match the measured artifacts.
- Documentation facade rewrite (DD round): README / QUICKSTART / CONTRIBUTING / MODEL_CARD /
  REPLICATION and the docs core now use a concise structure, synchronized across languages;
  the old narrative is archived under `docs/history/`.
- Documentation test locks moved to structural criteria (positioning preamble / disclosure
  section / line ceilings / index completeness); round markers and line-window locks retired.

### Fixed
- Trace visualization and replay now read the writer's vocabulary (EC round): traces only contain `node` events,
  the tri-state `passed` field and `token_usage`, but the viewer read `node_end` / `test_passed` / `token_delta` —
  all 100 real traces rendered as "no node records + FAIL" (the writer recorded 100/100 passes). Node timeline,
  PASS/FAIL/CRASH verdicts, per-node tokens and counts, and replay state evolution now key off the written fields. 12 new locks; the state-channel in-place write census is re-registered from 2/11 to 3/12.
- The release-freshness gate's exception register is no longer "register and pass" (EB round): the header's two promises
  (a reason per entry, entry must name the latest tag) were checked only when the latest tag was unregistered; a registered
  tag, tag == HEAD or no `v*` tag let stale or reasonless entries pass. Both classes now exit 1 before any green branch. 9 locks.
- Exported span intervals no longer sit in the future (EA round): node / task_end records are appended when the
  operation **ends**, but the exporter used that timestamp as the start, pushing every interval forward (a real session measured the task_end span ending one task-duration after the export moment). Starts are now `ts − duration`; a duration longer than `ts` is clipped to `[0, ts]` with `span_interval_clamped`. 14 new locks.
- The OTel export no longer loses the whole-task duration (DZ round): `record_task_end` writes `duration_s`, but the
  exporter only read `duration_ms`, so the task_end span was always 0 ns with no disclosure. Units now follow the field (`duration_s` wins); bad values report `duration_s_*`. 7 new locks.
- Trace sessions no longer turn tasks into crashes when the trace directory cannot be created (DY round): a path under a
  regular file raised `NotADirectoryError` and `run` rewrote every task as crashed; it now degrades to memory-only snapshots. 4 new locks.
- Diagnostic dump arguments and concurrency no longer distort the export (DX round): `limit=0` exported every
  snapshot and negatives sliced backwards; concurrent dumps shared one file. `0`/negatives now raise
  `ValueError`, and `O_EXCL` + numbered retry never overwrites an existing snapshot. 11 new locks.
- `--dump-trace-on-failure` no longer goes silent or corrupts results (DW round): directory creation ran
  outside the `try`, so a blocked path rewrote a completed task as crashed, and empty buffers / write
  failures were silent. The three states are now distinct (`trace_dump_path` / `trace_dump_error` + stderr reason). 9 new locks.
- Doctor's `dataset-check-cli` probe no longer requires removed output (DV round): QuixBugs prints
  "loaded N tasks" plus an explicit skip; the probe now accepts verified-pass or explicit-skip (missing verdict is red). 4 net-new locks (6 in all).
- `check-dataset` no longer exits 0 after finding loading problems (DU round): a non-empty report only warned
  while the docstring promised "0 = no problems". It now lists them and exits 1; a missing `quality_report` stays a disclosure. 11 new locks.
- `doctor --json` keeps one 13-key schema on every exit (DT round): an internal exception emitted 4 keys
  against 12 on success. The exception path now reports `matrix.status: internal` / `null` aggregates. 13 new locks.
- A crashed task no longer has a different result shape (DS round): 5 keys vs 14 on success (`jq '.coverage_ok'` failed),
  and human mode hid the reason and fabricated iteration 0. Both paths now share all keys, reasons go to stderr. 9 new locks.
- Blank option values are no longer read as "not provided" (DR round): an unset shell variable (`--func "$FUNC"`)
  arrives as `""` and silently widened the scope to every function (LLM spend) or the full dataset while exiting 0;
  both are now usage errors (rc=2) before any load or task start, and omitting the option still means "all". 8 new locks.
- `check-dataset` icons now come from the helpers alone (DQ round): six call sites stacked a
  second glyph on the helper prefix and successes printed as info; `success_msg` plus an AST
  lock now keep one icon per line. 15 new locks.
- `run` no longer treats directories or duplicate files as tasks (DP round): a usage error (rc=2) before any task starts; duplicates dedupe by absolute path. 11 new locks.
- `run`'s help/docs now match reality (DO round): help no longer leaks rich/Markdown markup; detection / repair /
  false_fix are benchmark-only (`experiments/_m1_metrics.py`, gold required); coverage reads met/missed/unmeasured and the threshold never changes rc. 16 new locks.
- `check-dataset --subset` no longer silently ignores or substitutes the request (DN round):
  datasets without a subset concept accepted `--subset lite`, exited 0 and loaded the full data;
  ULT also fell back silently when the subset file was missing. Such requests now exit 2
  (unsupported/unknown subset) or 1 with the fallback reason; `load_dataset` keeps its ULT fallback. 14 locks.
- `clean-venv-cache` no longer reports a disk state that does not exist (DM round):
  `shutil.rmtree(..., ignore_errors=True)` swallowed every deletion failure, so a read-only
  cache still printed "✓ removed 1 venv (freed 0.0 MB)" and exited 0. Deletions are now
  classified by whether the directory actually disappeared (`removed` vs `failed`): failures
  exit 1 and freed space counts only real removals; `--list-only` shares the same predicate
  instead of ignoring the filters (8 real-filesystem locks, red first; the old mock lock was rewritten).
- `check-dataset` no longer reports "no validator" as a pass (DL round): only the SWE-bench
  family implements `quality_report`; other datasets fell through to `report = {}` and printed
  "✓ full quality check passed (N tasks with no issues)" although no full check ever ran (N can
  exceed what `--limit` shows), and a missing `tasks_missing_source` stayed silent. Both missing
  capabilities now print "not provided — skipped" (exit stays 0, like `doctor`'s unavailable),
  while a present `quality_report` with an empty report still yields the verified pass. 5 locks.
- CLI usage errors and runtime failures no longer share an exit code (DK round): an unknown
  dataset name degraded to built-in examples and reported "quality check passed" (rc=0);
  `--limit -5` hit negative slicing; a load exception printed an error yet exited 0; 0 loaded
  tasks was reported as passing. `run` with no valid target or an invalid numeric option
  returned 1, indistinguishable from "task failed"; `clean-venv-cache --max-age-days -5` was
  true for every entry (`age_days > -5`), so it exited 0 after deleting the entire cache in
  our reproduction. Usage errors now exit 2 (unknown dataset name with the valid list printed,
  negative `--limit`, negative cache filters, no valid target, `--coverage-threshold=nan`),
  runtime failures exit 1 (load error / 0 tasks), and a `0` filter keeps the explicit
  "everything is stale" semantics. Dataset names now derive from a module-level registry
  (new `normalize_dataset_name` and `_DATASET_REGISTRY`, removing the hand-maintained parallel
  list); the `load_dataset` factory still degrades unknown names by contract (21 locks, red first).
- `doctor` usage errors and a missing install surface no longer masquerade as system
  failures (DJ round): a misspelled group or an empty `--groups` used to report
  `matrix.status="error"` (or silently run the full matrix), and pip-installed wheels
  made `aitester doctor` red forever because they ship no `scripts/tools/e2e_probe.py`.
  The probe framework now rejects unknown `--group`/`--name` values before filtering
  and lists valid choices (rc=2); `doctor` maps subprocess rc=2 to `usage` (exit 2,
  no fabricated error row) and a missing script to `unavailable` (not a failure;
  exit 1 under `--strict`); an empty `--groups` short-circuits to the usage path
  without collecting checks or running the matrix (10 test locks, red before green).
- Every gate-chain subprocess now carries a timeout budget (DI round): ten
  `subprocess` calls had no `timeout`, so a stuck git lock, ruff, mypy or pytest
  collection could hang `make gates` / CI forever — no readings, no failure line,
  just a job reclaimed by the platform limit. Budgets are in place and the timeout
  semantics are pinned: registration reconciliation raises `RuntimeError` (a
  `None` return would be read as `[SKIP]` and silently pass), baseline collection
  degrades to `None`, repo hygiene raises `RuntimeError`, the artifacts gate
  synthesizes rc=124, and the static snapshot records `(124, timeout)`. The dead
  `_run` helper in `check_invocation_caliber` was removed, and an AST structural
  lock covers `scripts/gates/*.py` plus both tool scripts (7 tests, red first).
- CI job budgets completed (DH round): `smoke-llm` in `ci.yml` was the only job without
  `timeout-minutes` (a hung endpoint would hit the platform's 360-minute default); it now
  declares 15 minutes, and `tests/test_ci_job_timeouts.py` locks every job's budget and (0, 60] range (3 tests, red first).
- The citation-key snapshot generator undercounted multi-key citations (DG round): a single-key
  regex missed keys inside `\citep{a,b}` groups — four multi-key groups (nine slots) hid six registered keys
  (konstantinou2026icst / arna2026icstw / radaideh2026bdai / zuppardo2026beyondaccuracy /
  curmi2026harnessmatter / sghaier2026harnesshierarchy). Counting now splits groups, with one regression test written red first.
- Optional embedding backends now degrade on load failure (DG round): the sentence-transformers
  branch caught only `ImportError`, so download/cache failures escaped `embed_text()` instead of returning `None`; now mirrored and warned (3 tests, red first).
- Comment semantics are now parsed per file type (DE round): TeX `%` with backslash parity, Typst `//`
  and nestable block comments, BibTeX by brace depth; fixes a false CJK failure from `refs.bib` comments.
- The paper build script's pre-flight audit now uses `--pre-build`: it skips only artifact page reconciliation and
  still blocks on source-side defects, so editing a source file no longer makes the build script impossible to run.
- The external-readings register corrects `wang2026harnessreeval` to arXiv v4 with the full
  v1–v4 history and hedges two strong negatives to "not seen in the checked abstract and body".

## [1.0.0] - 2026-10-25

### Added
- Replication package `REPLICATION.md`, the explicit `REPRODUCE_SKIP_TESTS` escape hatch,
  and the zero-LLM recomputation chain.
- Release criteria ADR-0036; release freshness guard.

### Changed
- The repair reading uses corrected caliber v2 (39.31%, 57/145 replayable rows, independent
  gold adjudication); historical calibers are in `docs/design/repair_caliber_matrix.md`.
- Model calls disable thinking by default and enable JSON mode by default (ADR-0031).

### Fixed
- Fixed two `repair=0` measurement artifacts: patch-fence residue and unmaterialized
  cross-file tasks.
- Added gates for documentation command executability and BibTeX compilability.

### Security
- Sensitive/private paths are covered by the repository hygiene gate; `.env*` files and
  private directories must not be tracked.
- Git history leak remediation is documented in `docs/security/history_leak_remediation_runbook.md`.

## Earlier Versions

The 0.8 / 0.9 series and earlier round-by-round records are archived (kept verbatim; links
are not guaranteed to resolve):

| Archive | Content |
|---|---|
| [README_2026-10-26_full.md](docs/history/README_2026-10-26_full.md) | README before the rewrite (Chinese) |
| [README_2026-10-26_full.en.md](docs/history/README_2026-10-26_full.en.md) | README before the rewrite (English) |
| [CHANGELOG_2026-10-26_full.md](docs/history/CHANGELOG_2026-10-26_full.md) | CHANGELOG before the rewrite (Chinese) |
| [CHANGELOG_2026-10-26_full.en.md](docs/history/CHANGELOG_2026-10-26_full.en.md) | CHANGELOG before the rewrite (English) |
