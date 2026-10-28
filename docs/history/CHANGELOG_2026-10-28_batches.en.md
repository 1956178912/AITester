# Changelog archive (older entries moved out by the GJ round, 2026-10-28)

> Moved verbatim out of the `CHANGELOG.en.md` facade: **nothing edited** (same treatment as the FC round).
> The facade keeps only a pointer line; see the `[Unreleased]` section of `CHANGELOG.en.md`.

- CI job budgets completed (DH round): `smoke-llm` in `ci.yml` was the only job without
  `timeout-minutes` (a hung endpoint would hit the platform's 360-minute default); it now
  declares 15 minutes, and `tests/test_ci_job_timeouts.py` locks every job's budget and (0, 60] range (3 tests, red first).
- The citation-key snapshot generator undercounted multi-key citations (DG round): a single-key regex missed keys inside `\citep{a,b}` groups — four multi-key groups (nine slots) hid six registered keys (konstantinou2026icst / arna2026icstw / radaideh2026bdai / zuppardo2026beyondaccuracy / curmi2026harnessmatter / sghaier2026harnesshierarchy). Counting now splits groups, with one regression test written red first.
- Optional embedding backends now degrade on load failure (DG round): the sentence-transformers branch caught only `ImportError`, so download/cache failures escaped `embed_text()` instead of returning `None`; now mirrored and warned (3 tests, red first).
- Comment semantics are now parsed per file type (DE round): TeX `%` with backslash parity, Typst `//` and nestable block comments, BibTeX by brace depth; fixes a false CJK failure from `refs.bib` comments.
- The paper build script's pre-flight audit now uses `--pre-build`: it skips only artifact page reconciliation and still blocks on source-side defects, so editing a source file no longer makes the build script impossible to run.
- The external-readings register corrects `wang2026harnessreeval` to arXiv v4 with the full v1–v4 history and hedges two strong negatives to "not seen in the checked abstract and body".
