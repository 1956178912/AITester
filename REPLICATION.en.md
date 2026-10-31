# AITester Replication Guide

Last updated: 2026-10-27

How to reproduce AITester experiments: the zero-LLM recompute path, the LLM-dependent re-run
path, and how mounting and the test gate behave. **Raw LLM responses are not distributed**, so
the LLM path must spend new API quota; only metrics from committed artifacts reproduce offline.

## 1. Prerequisites

- Python 3.12+ (`pyproject.toml` sets `requires-python = ">=3.12"`; CI matrix 3.12/3.13/3.14). Use the repository `.venv`.
- Dependencies: `pip install -r requirements.txt` (or `make install`); wheel installs that
  run the executor also need `pip install "aitester[execution]"`.
- The LLM path needs `LLM_1_API_KEY` / `LLM_1_BASE_URL` / `LLM_1_MODEL` in `.env.local`
  (copied from `config.local.example`); **keys are never committed**; scripts warn when missing.
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
citation checks, and SHA256SUMS verification; L1 adds the hour-scale QuixBugs Mut@k recompute.
Results are tri-state: `ok` / `FAILED` / `skipped` — withdrawn artifacts print `[SKIP]`, and
**skip is not a pass**; the exit code counts only failed commands and checksum failures.

**B. LLM-dependent single-batch re-run (API key required)**:

```bash
bash reproduce.sh --dataset synthetic --full
```

`--full` = 87 tasks / `--max-pattern-repeat 2` / seed 42 / three arms (`aitester`,
`plain_llm`, `plain_llm_df`). One seed per run; the three-seed entry is `experiments/run_main_batch.py`,
and **different-seed batches must not be pooled**. Outputs land in `experiments/results/` (never committed).

**C. Dockerized reproduction**:

```bash
docker build --build-arg GIT_SHA=$(git rev-parse HEAD) -f Dockerfile.repro \
  -t aitester-repro:$(git rev-parse --short HEAD) .
docker run --rm -v $(pwd)/experiments/results:/workspace/experiments/results \
  -v $(pwd)/.env.local:/workspace/.env.local:ro \
  aitester-repro:<sha> bash reproduce.sh --dataset synthetic --full
```

The image has no `.git`; provenance reads `GIT_SHA` from the build-time `.repro_provenance`
marker — with no build-arg it stays `unknown` and is never treated as a commit SHA.

## 3. Historical Input and Mounting

`.dockerignore` excludes `experiments/results`, so the image does **not** contain that
directory. The mounted directory is both **historical input** (the test suite uses archived
artifacts there as fixtures) and output: mount a complete directory with archived results;
starting from an empty directory makes the Step 3 suite fail, so the gate must be skipped explicitly.

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

The historical main batch (n=261/arm) was withdrawn on 2026-10-24; readings come from
`BASELINE.yaml` and rebuilt batches. Gaps: raw LLM responses not archived; no model fingerprint.

## 6. Environment Quadruple (N08, frozen 2026-10-30)

New batches must pin the quadruple — **seed / model alias+fingerprint / temperature /
dataset version content fingerprint** (any missing ⇒ fail-closed; no pooling across quadruples);
details: `docs/design/replication_quadruple_n08.en.md` (archived in the paper repository).