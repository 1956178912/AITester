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
- Regenerated the paper citation-key snapshot (DG round): the manuscript changed after the snapshot, so `docs/study/PAPER_CITATION_KEYS.md` was recomputed (64 lines, six corrected counts).
- Rebuilt the submission PDFs (DE round): 70 pages, `refs.bib` 79 entries ↔ 79 `\bibitem`s, 0 undefined citations;
  the old counts in `PAPER_BUILD.md` and `paper/tex/README.md` now match the artifacts.
- Documentation facade rewrite (DD round): README / QUICKSTART / CONTRIBUTING / MODEL_CARD / REPLICATION
  and the docs core use a concise structure, synchronized across languages; the old narrative is under `docs/history/`.
- Documentation test locks moved to structural criteria (positioning preamble / disclosure section / line ceilings / index completeness); round markers and line-window locks retired.

### Fixed
- The MySQL pool's constructor contract is no longer certified only by mocks (EV round): `MySQLClient.__init__` passed `timeout` and `idle_timeout` to `PooledDB`, but DBUtils 3.1.2 has neither parameter — extra keywords are forwarded to `pymysql.connect` (which rejects them too), so real construction/checkout always raised `TypeError`; the existing test mocked the whole `PooledDB` and only asserted that the mock received `idle_timeout`, certifying a constructor that could never run. The two invalid parameters are removed, `MYSQL_POOL_TIMEOUT` now maps to the driver's supported `connect_timeout` (fulfilling "connection establishment timeout" and disclosing that `blocking=True` has no acquisition timeout when the pool is exhausted), and dead-connection probing is declared explicitly with `ping=1`; 5 new locks (4 red→green + 1 negative control), and the old mock assertion that certified the defect is deleted.
- Complexity-aware routing no longer activates only inside the benchmark harness (EU round): `MODEL_ROUTING_STRATEGY=complexity_aware` is the default, but `complexity_class` was written only by a post-hoc block in `experiments/run_benchmark.py`, while `create_initial_state` (the shared entry of the CLI `aitester run`, orchestration search, and the e2e probe) initialized all four routing fields to `None` — so `APIManager._build_node_list`'s complexity branch and `BaseAgent._reorder_api_groups_by_complexity` never fired under the CLI, and `fixed` was indistinguishable from `complexity_aware`. Scoring now lives in `complexity_router.score_source_complexity` / `score_task_complexity` (a single implementation); `create_initial_state` writes the four fields according to the strategy (`fixed` keeps the historical `medium`), the benchmark passes only `task_metadata` (preserving `num_files` and the `cyclomatic_complexity` fallback for unparseable sources) and drops its inline duplicate, and orchestration search passes metadata too. 12 new locks (red-first) + 8 tests in the migrated file (the original 6 now drive the real shared entry, plus 2 new: source precedence and import-counter exception fallback).
- Complexity-aware routing no longer idles with multiple provider endpoints per model (ET round): `src/agents/base_agent.py::_reorder_api_groups_by_complexity` built its cost table keyed by `model_name` alone — when one model is served by several provider endpoints with different `cost_weight`, the last write won, every group got the same weight, and the stable `sorted` fell back to configuration order, so simple / medium / complex all idled. That is exactly the shape `complexity_router.py` promises ("same model, different provider endpoints, or same provider, different cost_weight"), and A15's `APIManager._cost_weight_for` already selects by instance, so the two routing calibers had split. The table is now keyed by `(base_url, model_name)`, with a model-level fallback for injected configs without `base_url` and a 1.0 baseline for unknown endpoints (no inheritance from another endpoint of the same model). 5 new locks (4 red→green + 1 caliber guard); the local `.env.local` has a single LLM instance (`len(all_configs) > 1` is false, so the reorder function is never called), which means the defect is only active in the multi-endpoint shape the docs promise.
- The bilingual docs gate's "H2 skeleton alignment" no longer idles on translated pairs (ES round): the P2 structural check compared **literal** H2 titles after normalization, but translated titles never match — across the 20 doc pairs only CHANGELOG has 2 cross-language identical titles, so the other 19 could never trigger. Two synthetic cases (“numbered chapters swapped” and “one chapter missing with a count delta of 1, inside the ±2 tolerance”) were both reported as no drift by the old implementation. The check now uses a language-independent skeleton fingerprint: H2 ordinal sequences (“一、” / “1.” folded to integers) must match position by position, and when the H2 counts are equal, per-section H3 subsection counts must match. On the real corpus 13 pairs carry ordinals and 20/20 skeletons agree (strict mode: zero warnings); 6 new locks (including a “comparable denominator ≥ 10” anti-idle lock), and no `src/` change means coverage readings are unchanged.
- Boolean switches no longer declare an unreachable off state (ER round): `--pool-seeds` in `e7_evidence_prepass` / `repair_ceiling_analysis` / `repair_review_worksheet` / `repair_sample_selection` and `--with-generated` in `emse_ult_gold_diagnosis` were all `store_true, default=True` — passing the flag changed nothing, no `--no-*` existed, yet the help said "on by default". The former is the pre-registered multi-seed pooling caliber; the latter's off state would render misleading zeros in README §2c (`n_tasks_with_generated=0`). Following EQ, the five flags are removed and the defaults pinned at the call sites (`pool_seeds=True`, generated gate always on); the four scripts' `main()` now accepts `argv` so the parser surface is testable. 20 new locks (16 red→green + 4 caliber guards, including a neighbor guard for `statistical_analysis`'s real switch); no `src/` change means coverage readings are unchanged.
- The model-catalog `add` subcommand and the replay script's `--repeat` no longer disagree with their implementations (EQ round): `scripts/tools/expand_models.py add --name/--url/--key` declared those three required flags, but `cmd_add` read `args.model_name/base_url/api_key` — the documented command crashed with `AttributeError` (rc=1) on every invocation; `experiments/oracle_examples_replay.py --repeat N` was accepted and never read, so users believed they had run an N-times determinism check (three sibling replay scripts implement repeat + body-digest comparison; this one copied only the flag). The three flags now map to the names `cmd_add` uses (CLI surface unchanged), and the never-implemented `--repeat` is removed (the same defect in `emse_batch5_orchestrator.py --skip-rerun` does not ship: that file is gitignored and outside the tracked surface). 5 new locks (2 red→green + 3 caliber guards).
- The batch config script no longer overwrites real credentials with placeholders (EP round): the generated `scripts/tools/generate_batch_config.py` guarded only the empty-model-list case; when a provider's `*_API_KEY` was missing it still wrote `your-<provider>-api-key-here` over an existing `.env.local` with rc=0, and the advertised `--template` flag was never read. It now validates every entry's provider and API key before writing, exits 1 with the missing names, and leaves the output untouched (one missing key refuses the whole batch); the phantom flag is gone; the tracked script is byte-compared with its generator. 7 new locks (5 red→green + 2 guards).
- Cache switches' explicit-off spellings no longer apply only at runtime (EO round): `AITESTER_LLM_CACHE` / `AITESTER_CACHE_ISOLATE_MODEL` are opt-out switches parsed by `env_flag_opt_out` (`false` / `0` / `off` off), but three sites in `experiments/run_benchmark.py` still hand-rolled `!= "0"` — the X1 namespace auto-set, `cache_enabled`, and `cache_isolate_model` all treated `false` / `off` / case-whitespace variants as on. One artifact could simultaneously carry `env_snapshot="false"`, `cache_enabled=true`, and `cache_namespace="seed42"`. All three now use `env_flag_opt_out`, so no namespace is invented while cache is off; 19 new locks (12 red→green + 7 caliber guards), archived artifacts untouched, and no `src/` change means coverage readings are unchanged.
- Harness self-description no longer parses switches differently from runtime (EN round): `provenance.harness` used raw `os.environ.get(...).lower() == "true"` for eight runtime switches plus one runtime-unread phantom key while runtime uses `env_flag` / `env_flag_opt_out` — eight measured scenarios (`EXECUTOR_USE_VENV=yes`, `KERNEL_SANDBOX_ENABLE=on`, `COST_BUDGET_ENABLE=1`, …) disclosed the opposite of the effective value, and `--enable-rag` produced one artifact whose top-level `enable_rag=true` contradicted `harness.rag_enabled=false`. The block now uses the same parsers and discloses the effective `_apply_rag_setting` value for RAG; the runtime-unread `truncation_first` phantom key is gone. 21 new locks (16 red→green + 5 caliber guards); no `src/` change, so coverage readings are unchanged.
- Batch provenance no longer declares a stale stop-reason vocabulary (EM round): the harness disclosure block promises auditable stop rules, but `retry_stop_rules.stop_reasons` was a hand-written 7-value literal while the `StopReason` enum has 13 — six real stop reasons (`recursion_limit`, reachable since EJ; `coverage_stall`, P2-4; plus four diagnosis/convergence variants) never appeared in any artifact's self-description, so readers would conclude the harness only stops for the old seven.
  The list is now derived from the enum (single source of truth) and new values reach new batches automatically; archived artifacts are untouched. 6 new locks (3 red→green + 3 caliber guards); no `src/` change, so coverage readings are unchanged.
- P2P-gate rejects no longer masquerade as runtime crashes in the failure distribution (EL round): the batch summary promises to exclude `harness_invalid` instances (baseline P2P below threshold) from statistics, but `_aggregate_failure_buckets` only checked whether `failure_bucket` was empty — gate-skipped rows (which never entered the workflow) were counted in `unclassified_rows` exactly like real crashes, and the report labelled them "no workflow terminal state (runtime exception / rate limit)".
  They are now counted in `harness_invalid_rows` and excluded from the bucket denominator (identity: total + unclassified_rows + harness_invalid_rows == total_rows), and `render_markdown` discloses the two exclusion causes separately; the per-row four keys stay `None` (no invented bucket). 10 new locks (8 red→green + 2 caliber guards); the denominator change is disclosed in `MEASUREMENT_INTEGRITY` §105.
- Known crash causes no longer contradict the attribution columns (EK round): after EJ stored `stop_reason="recursion_limit"` on crash rows, the failure branch still hardcoded the four attribution keys to `None` — "reason known, attribution unknown" in one row; batch aggregation kept counting these deterministic harness crashes as `unclassified_rows`, so ADR-0026's harness attribution remained unreadable in production artifacts. `_failure_attribution_for_result` now accepts the known `stop_reason` (used only when `final_state=None`) and the failure branch takes the four keys from it; crashes without a known cause stay `None` and unclassified. 7 new locks (4 red-to-green + 3 caliber guards); the denominator change is disclosed in `MEASUREMENT_INTEGRITY` §104.
- Workflow-cap crashes no longer collapse to "no terminal state" (EJ round): `StopReason.RECURSION_LIMIT` and the failure taxonomy's `recursion_limit → harness/harness_side` mapping (ADR-0026) both existed, but nothing ever wrote the label — the benchmark exception branches hardcoded the row's `stop_reason` to `None`, so a graph-recursion cap hit degraded into "missing state information" and the promised harness attribution never matched. New `stop_reason_for_exception` maps only `GraphRecursionError` → `recursion_limit` (a plain `RecursionError` is a node-code defect and must not masquerade as a harness bound); both exception branches persist the label, while the bucket denominator is unchanged (rows without a terminal state stay in `unclassified_rows`). 10 new locks (8 red-to-green + 2 caliber guards).
- The per-call LLM budget can no longer be bypassed by a clock rollback (EH round): `LLM_CALL_BUDGET_SECONDS` (default 600 s) computed its deadline with `time.time()`, so an NTP step correction or a VM snapshot restore pushed the deadline forward and the budget never fired; the check also ran only when switching models, so the retry ladder (1/2/4 s) and the 429 backoff (up to 30 s) kept sending requests past the budget (contradicting `COST_MODEL`'s "without further requests").
  The deadline now uses `time.monotonic`, is re-checked before every real request, clamps the 429 wait to the remaining budget, and surfaces `LlmCallBudgetExceeded`. 6 new locks.
- The time-budget exception is no longer invisible to the budget-cap readers (EI round): `LlmCallBudgetExceeded` was a sibling of `RuntimeError` while planner / generator / debugger and `determine_stop_reason` only recognise `BudgetExceededError` — a timeout degraded as usual but never set `budget_exceeded`, so `BUDGET_EXCEEDED` was unreachable and `.env.example`'s "5.4 budget cap" promise was not kept. It now subclasses `BudgetExceededError` (`unit="seconds"`, `consumed=None` for unknown), so all three nodes and the stop reason treat it identically without changes. 7 new locks.
- Default-on safety/quality guards no longer obey unrecognised values (EG round): venv sandboxing, credential and pip whitelists, the dangerous-API guard, naming contract, injection output scan, evidence gate, P2P gate, container read-only/network isolation — 10 switches (11 reads) used `env_flag(name, True)`; values like `yes` / `enabled` / a typo / the empty string turned the guard **off** — reproduced as a dangerous patch being accepted, `MYSQL_PASSWORD` returning to the child environment, and containers losing `--read-only` and `--network=none`.
  All now use `env_flag_opt_out`: only `false`/`0`/`off` disable a guard; unrecognised values keep it on. Default-off feature/cost switches keep positive-set semantics (a typo must not enable them). 31 new locks (24 red first, 7 boundary controls).
- Optional integrations that are installed but broken no longer break the degradation contract (ED round): 12 `try: import … except ImportError` guards only caught a missing package, so ABIs / transitive-dependency conflicts raising RuntimeError/OSError escaped (a broken chromadb failed the whole CLI start). Any import-time
  exception now degrades with a warning; the datasets entry keeps ImportError and chains the cause (12 locks + 1 control).
- Readers no longer treat "corrupt" as JSON syntax only (EE round): 15 JSON/JSONL readers caught only `json.JSONDecodeError` (decoded text), so byte-level corruption (truncated multi-byte writes, GBK saves) raised `UnicodeDecodeError` during decoding — one bad line killed the whole file and whole-file readers raised instead of degrading.
  Line readers now read binary and decode strictly per line; whole-file readers degrade alike; the bank write stays fail-closed. 15 new locks.
- Non-finite float env values no longer silently rewrite control flow (EF round): 6 local parsers caught only `ValueError`,
  which `float("nan")` never raises; NaN/inf were clamped to a bound, so the semantic cache returned an unrelated entry, coverage
  stalls always fired, risk approval was bypassed, failure-KB ranking fell back to insertion order and `long_sleep` vanished.
  Parsing now delegates to `env_float` (warning + default); finite clamping unchanged. 49 new locks.
- Trace visualization and replay now read the writer's vocabulary (EC round): traces only contain `node` events,
  the tri-state `passed` field and `token_usage`, but the viewer read `node_end` / `test_passed` / `token_delta` —
  all 100 real traces rendered as "no node records + FAIL". Verdicts, per-node tokens and replay evolution now key off the written fields. 12 new locks; the state-channel census is re-registered from 2/11 to 3/12.
- The release-freshness gate's exception register is no longer "register and pass" (EB round): the header's two promises
  (a reason per entry, entry must name the latest tag) were checked only when the latest tag was unregistered; a registered
  tag, tag == HEAD or no `v*` tag let stale or reasonless entries pass. Both classes now exit 1 before any green branch. 9 locks.
- Exported span intervals no longer sit in the future (EA round): node / task_end records are appended when the
  operation **ends**, but the exporter used that timestamp as the start, pushing every interval forward (a real session measured the task_end span ending one task-duration after the export moment). Starts are now `ts − duration`; a duration longer than `ts` is clipped to `[0, ts]` with `span_interval_clamped`. 14 new locks.
- The OTel export no longer loses the whole-task duration (DZ round): `record_task_end` writes `duration_s`, but the
  exporter only read `duration_ms`, so the task_end span was always 0 ns with no disclosure. Units now follow the field (`duration_s` wins); bad values report `duration_s_*`. 7 new locks.
- Trace sessions no longer turn tasks into crashes when the trace directory cannot be created (DY round): a path under a regular file raised `NotADirectoryError` and `run` rewrote every task as crashed; it now degrades to memory-only snapshots. 4 new locks.
- Diagnostic dump arguments and concurrency no longer distort the export (DX round): `limit=0` exported every
  snapshot and negatives sliced backwards; concurrent dumps shared one file. `0`/negatives now raise
  `ValueError`, and `O_EXCL` + numbered retry never overwrites an existing snapshot. 11 new locks.
- `--dump-trace-on-failure` no longer goes silent or corrupts results (DW round): directory creation ran
  outside the `try`, so a blocked path rewrote a completed task as crashed, and empty buffers / write
  failures were silent. The three states are now distinct (`trace_dump_path` / `trace_dump_error` + stderr reason). 9 new locks.
- Doctor's `dataset-check-cli` probe no longer requires removed output (DV round): QuixBugs prints
  "loaded N tasks" plus an explicit skip; the probe now accepts verified-pass or explicit-skip (missing verdict is red). 4 net-new locks (6 in all).
- `check-dataset` no longer exits 0 after finding loading problems (DU round): a non-empty report only warned while the docstring promised "0 = no problems". It now lists them and exits 1; a missing `quality_report` stays a disclosure. 11 new locks.
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
- Every gate-chain subprocess now carries a timeout budget (DI round): ten `subprocess` calls had no `timeout`, so a stuck git lock, ruff, mypy or pytest collection could hang `make gates` / CI forever — no readings, no failure line, just a job reclaimed by the platform limit.
  Budgets are in place and the timeout semantics are pinned: registration reconciliation raises `RuntimeError` (a `None` return would be read as `[SKIP]` and silently pass), baseline collection degrades to `None`, repo hygiene raises `RuntimeError`, the artifacts gate synthesizes rc=124, and the static snapshot records `(124, timeout)`.
  The dead `_run` helper in `check_invocation_caliber` was removed, and an AST structural lock covers `scripts/gates/*.py` plus both tool scripts (7 tests, red first).
- CI job budgets completed (DH round): `smoke-llm` in `ci.yml` was the only job without
  `timeout-minutes` (a hung endpoint would hit the platform's 360-minute default); it now
  declares 15 minutes, and `tests/test_ci_job_timeouts.py` locks every job's budget and (0, 60] range (3 tests, red first).
- The citation-key snapshot generator undercounted multi-key citations (DG round): a single-key regex missed keys inside `\citep{a,b}` groups — four multi-key groups (nine slots) hid six registered keys (konstantinou2026icst / arna2026icstw / radaideh2026bdai / zuppardo2026beyondaccuracy / curmi2026harnessmatter / sghaier2026harnesshierarchy). Counting now splits groups, with one regression test written red first.
- Optional embedding backends now degrade on load failure (DG round): the sentence-transformers branch caught only `ImportError`, so download/cache failures escaped `embed_text()` instead of returning `None`; now mirrored and warned (3 tests, red first).
- Comment semantics are now parsed per file type (DE round): TeX `%` with backslash parity, Typst `//` and nestable block comments, BibTeX by brace depth; fixes a false CJK failure from `refs.bib` comments.
- The paper build script's pre-flight audit now uses `--pre-build`: it skips only artifact page reconciliation and still blocks on source-side defects, so editing a source file no longer makes the build script impossible to run.
- The external-readings register corrects `wang2026harnessreeval` to arXiv v4 with the full v1–v4 history and hedges two strong negatives to "not seen in the checked abstract and body".

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

The 0.8 / 0.9 series and earlier round-by-round records are archived (kept verbatim; links are not guaranteed to resolve):
[README (Chinese)](docs/history/README_2026-10-26_full.md) · [README (English)](docs/history/README_2026-10-26_full.en.md) · [CHANGELOG (Chinese)](docs/history/CHANGELOG_2026-10-26_full.md) · [CHANGELOG (English)](docs/history/CHANGELOG_2026-10-26_full.en.md).
