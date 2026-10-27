# AITester Replication Guide

Last updated: 2026-10-27

How to reproduce AITester experiments: the zero-LLM recompute path, the LLM-dependent re-run
path, and how mounting and the test gate behave. **Raw LLM responses are not distributed**, so
the LLM path must spend new API quota; only metrics from committed artifacts reproduce offline.

## 1. Prerequisites

- Python 3.12+ (`pyproject.toml` sets `requires-python = ">=3.12"`; CI matrix
  3.12/3.13/3.14). Use the repository `.venv`.
- Dependencies: `pip install -r requirements.txt` (or `make install`); wheel installs that
  run the executor also need `pip install "aitester[execution]"`.
- The LLM path needs `LLM_1_API_KEY` / `LLM_1_BASE_URL` / `LLM_1_MODEL` in `.env.local`
  (copied from `config.local.example`); **keys are never committed**, and scripts warn when
  they are missing.
- Optional: Docker (`Dockerfile.repro`); sandboxes are controlled by switches such as
  `EXECUTOR_USE_VENV`, with the venv sandbox on by default.

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local   # only the LLM path needs it filled in
```

## 2. Three Reproduction Paths

**A. Zero-LLM recompute (no API key)**:

```bash
make reproduce-zero-llm
make reproduce-zero-llm-l1
```

L0 runs statistical extensions, mutation × detection cross-validation, SWE-bench disclosure,
citation checks, and per-directory SHA256SUMS verification; L1 adds the full QuixBugs Mut@k
recompute (hours). Results are tri-state: `ok` / `FAILED` / `skipped` — branches whose source
artifacts were withdrawn print `[SKIP]`, and **skip is not a pass**. The exit code depends only on failed commands plus SHA256SUMS failures.

**B. LLM-dependent single-batch re-run (API key required)**:

```bash
bash reproduce.sh --dataset synthetic --full
```

`--full` = 87 tasks / `--max-pattern-repeat 2` / seed 42 / three arms (`aitester`,
`plain_llm`, `plain_llm_df`). This script runs one seed; the full three-seed protocol entry
point is `experiments/run_main_batch.py`, and **batches from different seeds must not be pooled**. Outputs land in `experiments/results/` (run-produced, never committed).

**C. Dockerized reproduction**:

```bash
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -f Dockerfile.repro -t aitester-repro:$(git rev-parse --short HEAD) .
docker run --rm \
  -v $(pwd)/experiments/results:/workspace/experiments/results \
  -v $(pwd)/.env.local:/workspace/.env.local:ro \
  aitester-repro:<sha> bash reproduce.sh --dataset synthetic --full
```

The image has no `.git`, so provenance reads `GIT_SHA` from the build-time
`.repro_provenance` marker; when no build-arg is passed the value stays `unknown` and is never treated as a commit SHA.

## 3. Historical Input and Mounting

`.dockerignore` excludes `experiments/results`, so the image does **not** contain that
directory. The mounted directory is both **historical input** (the full test suite uses
archived artifacts there as fixtures) and output (this run's results): mount a complete
directory with archived results; starting from an empty directory makes the Step 3 test
suite fail, so the test gate must be skipped explicitly.

## 4. Test-Gate Escapes

Step 3 of `reproduce.sh` runs `python3 -m pytest tests/ -v --tb=short` by default, and test
failures **fail hard** (non-zero exit). Two explicit escapes:

| Variable | Behavior |
|----------|----------|
| `REPRODUCE_ALLOW_TEST_FAILURES=1` | warn and continue on test failures |
| `REPRODUCE_SKIP_TESTS=1` | skip the whole test gate with a prominent WARN |

When skipped, conclusions **exclude test verification** — that is a disclosure, not a pass. Setting nothing keeps the default fail-closed behavior.

## 5. Evidence Index

| Content | Location |
|---------|----------|
| Single source of truth for numbers (test counts, static checks, benchmark readings) | `BASELINE.yaml` |
| Data provenance and licenses (synthetic templates / SWE-bench / QuixBugs) | `docs/DATA_CARD.md` |
| Preregistered protocol (E1–E7) | `docs/preregistration.md` |
| Measurement caliber matrix and repair readings | `docs/design/repair_caliber_matrix.md` |
| Withdrawn-artifact mapping (2026-10-24) | `docs/study/WITHDRAWN_ARTIFACTS_2026-10-24.md` |
| Artifact checksums | `experiments/results/**/SHA256SUMS` |
| License and citation | `LICENSE`, `CITATION.cff` |

The historical main batch (n=261/arm) was withdrawn with the 2026-10-24 data purge and is
historical only; current readings come from `BASELINE.yaml` and the rebuilt batches, one
batch at a time. Known gaps: no raw LLM responses are archived, so re-runs are subject to server-side drift; the historical batch had `git_dirty=true` and no model fingerprint.
