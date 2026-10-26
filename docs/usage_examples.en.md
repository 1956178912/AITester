# AITester Usage Examples

Last updated: 2026-10-26 · 中文版: [usage_examples.md](usage_examples.md)

Six common scenarios with commands you can run directly. Numbers come from
[BASELINE.yaml](../BASELINE.yaml); this document embeds no drifting counts.

## 1. Run the Test Suite

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
make test
```

`make test` matches CI (xdist `-n 4 --dist loadfile`). For a zero-LLM environment and feature
probe check:

```bash
python3 main.py doctor
python3 main.py doctor --json
```

`doctor` spends no API quota; `--strict` returns non-zero on warnings or skips; a usage error
(empty `--groups` or an unknown group) returns 2. The feature matrix needs
`scripts/tools/e2e_probe.py` from a source checkout; wheel installs report `unavailable`
while environment checks still apply.

## 2. Zero-LLM Recompute

Recompute metrics from committed artifacts without an API key:

```bash
make reproduce-zero-llm
make reproduce-zero-llm-l1
```

L0 covers statistical extensions, mutation × detection cross-validation, SWE-bench disclosure,
citation checks, and SHA256SUMS verification; L1 adds the full QuixBugs Mut@k run (hours).
Results are tri-state `ok` / `FAILED` / `skipped`: withdrawn source branches print `[SKIP]`,
and **skip is not a pass**. The report lands in `experiments/results/REPRODUCTION_REPORT.md`
(run-produced, never committed).

## 3. Pre-Run Check for a Single Task

Run a bundled example to confirm the chain works:

```bash
python3 main.py run examples/calculator.py --func divide
python3 main.py run examples/buggy_library.py --func binary_search
python3 main.py run examples/calculator.py --json
```

Before a batch, run the preflight gate (quota, model fingerprint, worktree, orphan processes;
zero LLM):

```bash
make preflight
```

For a real LLM batch re-run, see the `reproduce.sh` path in
[REPLICATION.md](../REPLICATION.md).

## 4. Mutation Evaluation

Mutation-test the project's own suite (zero LLM; samples three core modules by default):

```bash
make self-mutation
make self-mutation-ci
```

`self-mutation-ci` is the CI gate caliber (`env_utils` + `atomic_io`, threshold 0.85). To enable
mutation scoring inside a benchmark run, set `ENABLE_MUTATION_SCORING=true` explicitly (off by
default). The mutation × detection cross-validation report is produced by the zero-LLM L0 chain.

## 5. Fix-Coverage Audit

```bash
make test-cov
make fix-coverage
```

`make test-cov` runs the full suite and writes `coverage.xml`; `make fix-coverage` audits code
lines added by repair logic that tests never execute, defaulting the baseline to the latest
commit touching `src/`. Coverage readings and thresholds are registered in
[BASELINE.yaml](../BASELINE.yaml) and
[PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) §1.

## 6. Documentation and Gate Self-Checks

```bash
make docs-check
make doc-commands
make gates
```

- `docs-check`: bilingual pairing, update-date sync, and internal-link integrity (strict,
  blocking in CI).
- `doc-commands`: every `scripts/*.py` and `make <target>` referenced by the docs must exist.
- `gates`: runs the full local gate chain; use it before merging, and never overlap chains.

For docs-only changes, run `docs-check` and `doc-commands` at minimum; after code changes, run
`gates`. Gate readings are refreshed in `BASELINE.yaml`, never copied into prose.
