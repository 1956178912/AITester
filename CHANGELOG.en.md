# Changelog

> Last updated: 2026-11-02

This file records externally visible changes only; round-by-round history is archived below.

## [Unreleased]

### Added
- Overnight experiment-pipeline batch (2026-11-01/02): incremental checkpoint-resume in `experiments/run_benchmark.py` (per-task flush+fsync into `INCREMENTAL_RESULTS.jsonl`, restarts only complete missing tasks, `AITESTER_SKIP_TASK_IDS` filters stuck tasks); judge family — `scripts/tools/judge_b3_docker.py` (B3 docker equivalent rebuild: daocloud x86 image + worktree mount + Tsinghua deps, direct connection without proxy) and clone-fixed `_v2` (environment markers passed as an in-container file parsed by pip, avoiding the shell nested-quote breakage that wiped the line build), `scripts/tools/judge_g8_docker.py` (G8 M3-gate per-instance verification: host-side git apply + repo-bundled requirements + ghproxy rewrite for in-container GitHub deps; smoke passed `harness_valid` on all three repos: ansible/qutebrowser/openlibrary); overnight watchdog `experiments/watch_g8_off_20261101.sh` (stall kill + auto-restart, capped total time/attempts, lock idempotency).
- G8 full178 both arms closed: on 178/178 (177 `harness_invalid` + 1 `patch_validation_failed`, passed=0), off 177/178 + 1 explicitly skipped stuck task — **effective denominator = 0 confirmed at full-pool scale**, upgrading the four-switch comparison ran_unmeasurable from a 10-task qualification to the full-pool caliber; the per-instance gate-verification channel (step 1, LLM-free) is built and pending full run to recover the real effective denominator (step 2 regeneration would need separate authorization).
- H1 amended (r2) three arms + REF rebuild completed: `env_snapshot` three-arm validation and `SHA256SUMS` passed; criterion frozen at ≤10pp (`payload_equivalence_prereg_amendment_20261101.md`), superseding the original-caliber "forced inconclusive" closure (REF artifacts unrecoverable after AITester-w-head deletion).
- Expanded-sample judging final statistics (`experiments/results/JUDGE_REPORT_20261101.md`): C8 post-fix aitester 1/166=0.60%, df 2/109=1.83% (judge_exception 39+34 cleared); TGE first pass 1.1% vs 2.1%; rescue31 + luigi33 detection 0; 502 valid verdicts across all batches with 6 detections ≈1.2%, dominated by fix_not_green (54.5%).

### Fixed
- Runaway restart of the queue scripts (2026-11-02 incident): `scripts/b3_queue.sh` / `scripts/recovery_queue.sh` were managed by launchd with `KeepAlive=true`, so each normal exit triggered a relaunch (observed 6,425 / 772 relaunches); the non-idempotent judging step accumulated 983 orphan judge processes at load 747. Both LaunchAgents were unloaded and disabled, all residual processes terminated, and the scripts hardened with a **re-entrancy lock + completion marker + idempotent judging**. The idle batch over-wrote `b3_lite_20261031/B3_JUDGE.json` (298 rows, all `env_error`); it is renamed to `.INVALID-20261102-env_error298` and quarantined. Handling and rollback: `docs/checkpoints/incident-queue-runaway-20261102.md`.

### Changed
- B3 Lite judging caliber update (docker v2 final): the 78 `env_error` rows were re-diagnosed as **cold-start resource contention** — `judge_b3_docker_v2.py` discarded the `docker run` return code, so a container that never started was folded into an environment failure; all 78 fell in the first batch (s1–s3, while s4–s6 had zero). Re-run converted **78/78 to `red`** (22m55s, zero LLM), raising the effective denominator **222 → 300**, driving `env_error` to zero, with **detection 0/300**. The judge gained return-code validation plus one retry (`58e0c41d`). The older calibration (py3.8/py3.14/conda baselines, env_error 246→281→286) is historical and **must not be pooled with v2**.
- off-arm stuck-task handling caliber: attempts 29–33 stalled at the same task five times with watchdog progress extraction failing (`progress=?`) ⇒ the two-round cross-check skip never triggered; closed via explicit `AITESTER_SKIP_TASK_IDS`. Two-arm caliber disclosed as on 178/178 vs off 177/178+1skip; the skipped task's gate reading will be supplied by the per-instance channel.
- Per-round entry archive: all `[Unreleased]` entries predating the 2026-11-02 batch (128 lines verbatim) moved into [docs/history/CHANGELOG_2026-11-02_batches.en.md](docs/history/CHANGELOG_2026-11-02_batches.en.md) (**verbatim, unedited**; Chinese counterpart in the same directory).

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
