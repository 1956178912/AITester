# Troubleshooting

Last updated: 2026-10-26 · 中文版: [troubleshooting.md](troubleshooting.md)

Organized as symptom / cause / action. Start with the zero-LLM self-check:
`python3 main.py doctor`.

## 1. Installation and Environment

**Symptom**: `ModuleNotFoundError: No module named 'pytest'`; tasks report
`execution_dependency_missing`.
**Cause**: execution dependencies are missing (wheel installs exclude them by default).
**Action**: `pip install "aitester[execution]"`, or install `requirements.txt`.

**Symptom**: `401` / `403`, or repeated `LLM call failed` retries.
**Cause**: invalid or exhausted `LLM_1_API_KEY`, or `.env.local` was never created.
**Action**: copy `.env.local` from `config.local.example` and fill in the endpoint; check
connectivity with `python3 experiments/run_smoke_llm.py`.

**Symptom**: `429` rate limits or long stalls.
**Cause**: endpoint rate limiting, or `LLM_TIMEOUT` too short for reasoning models.
**Action**: lower concurrency; set `LLM_THINKING_MODE=disabled`; raise `LLM_TIMEOUT` if needed.

**Symptom**: `doctor` reports invalid or missing configuration.
**Cause**: misspelled or out-of-range environment variables.
**Action**: fix against the table in [api_reference.en.md](api_reference.en.md);
`doctor --json` names the offending item.

**Symptom**: `doctor` exits 2 with "usage error" or "unknown group".
**Cause**: `--groups` is empty or commas only, or a group name is misspelled (case-sensitive).
**Action**: run `python3 scripts/tools/e2e_probe.py --list` for available groups; omit
`--groups` to run all of them.

**Symptom**: `doctor` reports the feature matrix as unavailable.
**Cause**: pip-installed wheels do not ship `scripts/`; the matrix only works from a source checkout.
**Action**: environment/config checks still apply; run `python3 main.py doctor` inside a source
checkout when you need the matrix.

**Symptom**: `check-dataset` exits 2 / 1, or `clean-venv-cache` rejects a filter.
**Cause**: the dataset name is not in the registry, the data is not in place (0 tasks loaded),
or a filter value is negative.
**Action**: use one of the names listed on the error line (case- and hyphen-insensitive);
`--limit 0` shows the summary only; for `clean-venv-cache` a `0` filter means "everything is
stale" and only negatives are rejected (a negative filter is true for every entry).

## 2. Runtime and Sandboxes

**Symptom**: `docker_unavailable` / `docker_timeout`.
**Cause**: Docker not installed, daemon stopped, or image not built.
**Action**: set `EXECUTOR_USE_DOCKER=false` to use the venv sandbox, or build the image first.

**Symptom**: missing dependencies inside the sandbox, or results differ between runs.
**Cause**: the venv cache does not match the current dependency fingerprint.
**Action**: `python3 main.py clean-venv-cache --max-age-days 7`; use `--list-only` first when
unsure.

**Symptom**: RAG initialization fails and logs show `rag_retrieval_empty`.
**Cause**: chromadb missing, embedding model download failure, or a corrupt `rag_data/`.
**Action**: install the optional dependency (`pip install chromadb`), or rename `rag_data` and
rebuild; running without RAG is an expected degraded caliber.

**Symptom**: `llm_localization` is always `None`, or `localization_hit_function` is empty.
**Cause**: the reasoning localization channel is disabled (`FAULT_LOCALIZER_ENABLE=false`), or
the LLM localization failed and degraded conservatively.
**Action**: confirm `FAULT_LOCALIZER_ENABLE=true`; for a spectral-only ablation this is the
expected caliber — state it when reporting readings.

**Symptom**: tests still fail after a patch, or no rollback happens.
**Cause**: the patch evidence gate rejected the patch, or P2P regression returned
`regression_error` without fail-closed rollback.
**Action**: inspect `error_info.type` and the patch evidence; set
`PATCH_ROLLBACK_FAIL_CLOSED=true` when strict rollback is required.

## 3. Tests and Gates

**Symptom**: session output quotes a `12,xxx passed` figure that disagrees with `BASELINE.yaml`.
**Cause**: historical narrative or a single run was mistaken for the registered value.
**Action**: treat `BASELINE.yaml` as the single source of truth; refresh via measure → BASELINE →
register §1 → gates.

**Symptom**: `make docs-check` reports a missing English pair, date mismatch, or section drift.
**Cause**: a Chinese document changed without syncing `.en.md`, or the two "last updated" dates
differ.
**Action**: add the English twin and align dates; register a reasoned exemption in
`scripts/gates/check_bilingual_docs.py` for genuinely single-language documents.

**Symptom**: `make doc-commands` reports a missing `make` target or `scripts/*.py`.
**Cause**: the docs reference a renamed or deleted command or script.
**Action**: fix the reported line; do not document capabilities that do not exist.

**Symptom**: `make registration-consistency` reports §1 drift or unregistered booklets.
**Cause**: BASELINE, the register, and INDEX are out of sync, or a new `docs/reviews/` file is
missing from §3.5.
**Action**: refresh the register and [INDEX.en.md](INDEX.en.md) §3.5 as reported; never copy
counts by hand.

**Symptom**: `ruff format --check .` reports Markdown files.
**Cause**: Python snippets inside code fences are formatted too.
**Action**: run `ruff format .` and re-check; do not format only `.py` files.

**Symptom**: pytest exits 0 but the suite was entirely skipped.
**Cause**: `rc==0` is not a pass with executed assertions.
**Action**: derived readings require at least one passed and zero failed; otherwise record
`unverifiable` (see [preregistration.en.md](preregistration.en.md)).

**Still stuck**: open an issue with a minimal reproduction (command, full error,
`python3 main.py doctor --json` output, commit sha). Never report security vulnerabilities via
public issues — see [SECURITY.md](../SECURITY.md).
