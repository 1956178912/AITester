# Changelog archive (2026-10-27, FC round): the DI–DL round-by-round entries of [Unreleased]

> These four rounds' entries were moved out of the `[Unreleased]` section of `CHANGELOG.en.md` on
> 2026-10-27 (**kept verbatim, nothing edited**) so the concision ratchet
> (`tests/test_doc_concision.py`: CHANGELOG.en.md ≤ 160 lines) keeps headroom and the facade shows
> only recent rounds. The Chinese version is in
> [CHANGELOG_2026-10-27_batches.md](CHANGELOG_2026-10-27_batches.md).

## Archived entries (rounds DI–DL)

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
- Every gate-chain subprocess now carries a timeout budget (DI round): ten `subprocess` calls had no `timeout`, so a stuck git lock, ruff, mypy or pytest collection could hang `make gates` / CI forever — no readings, no failure line, just a job reclaimed by the platform limit.
  Budgets are in place and the timeout semantics are pinned: registration reconciliation raises `RuntimeError` (a `None` return would be read as `[SKIP]` and silently pass), baseline collection degrades to `None`, repo hygiene raises `RuntimeError`, the artifacts gate synthesizes rc=124, and the static snapshot records `(124, timeout)`.
  The dead `_run` helper in `check_invocation_caliber` was removed, and an AST structural lock covers `scripts/gates/*.py` plus both tool scripts (7 tests, red first).
