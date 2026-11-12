# AITester

A **detection-first** Python test generation and repair-evaluation (attribution) research system: given a function-level repair task, it generates pytest tests, executes them, diagnoses failures, and applies patches. Multi-agent orchestration is an ablatable container, not the headline claim.

Current version 1.0.0 · [Changelog](CHANGELOG.en.md) · [Documentation index](docs/INDEX.en.md) · [MIT license](LICENSE)

> **Result reproducibility**: the current manuscript's tables are aggregated with zero model calls by `scripts/tools/results_data_pack_20261111.py` over the three registered batch directories (recomputable once the DOI snapshot below is present). `make reproduce-zero-llm` (and `make reproduce-zero-llm-l1` for L1) is the recompute chain of the **earlier corpus**; some of its branches report `skipped` because the old main batch was withdrawn — a skip is not a pass. The quota-consuming entry points `reproduce.sh` and `experiments/run_main_batch.py` only **regenerate a batch** under the retired pre-registered configuration; they are not on the path from an artifact to a current manuscript number. [INVENTORY.md](INVENTORY.md) answers the six open-science criteria one by one.

> **Archived data DOI**: [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24136905.svg)](https://doi.org/10.5281/zenodo.24136905) — the DOI-locked 2026-11-11 derived-verdict-row snapshot is published as `10.5281/zenodo.24136905`, CC0-1.0, with no raw execution traces or model transcripts; combined with this repository it reproduces the 50-cell aggregate byte for byte with zero model calls.

> Last updated: 2026-11-12

## What It Is

AITester is a research system that orchestrates a Planner → Generator → Executor → Debugger → PatchApplier loop with LangGraph:

- **Input**: tasks from five benchmarks (QuixBugs, BugsInPy, SWE-bench, TestGenEval, ULT; function-level single-file and repository-level).
- **Process**: generate pytest tests → execute in a sandbox → diagnose failures → produce a patch → re-run.
- **Output**: tests, patches, structured traces, and recomputable metric artifacts.

The current manuscript's central claim is not "are multiple agents better" but the false-fix paired reporting of "declared pass ≠ adjudicated real pass" (RQ2) and the harness-exclusion disclosure (RQ3). Multi-agent orchestration participates only as an ablatable container and carries no independent capability claim.

## What It Is Not (Honest Disclosure)

- **Not "self-repair achieved"**. Self-repair is a **measurable caliber**, not a proven claim.
- **Historical readings (retired protocol generation, never pooled with the current manuscript)**: the repair metric is **39.31%** (v2, 57/145 replayable rows; independent gold adjudication) after two rounds of measurement-caliber corrections (ADR-0021/0027/0029). The earlier **repair=0** reading was a **measurement artifact** caused by patch-fence residue and unmaterialized cross-file tasks, not a capability reading. Caliber splits and recomputation are documented in the [repair caliber matrix](docs/design/repair_caliber_matrix.md).
- **E7-r2 human calibration has not been executed**: the sampling frame is now a **census of the 89 declared-pass verdict rows** behind manuscript tab:falsefix (42 patch-track rows + 47 suite-track rows); the preparation pack is generated, adjudication is still pending human execution. Protocol: [preregistration](docs/preregistration.md). Its results appear in no released reading, and no Kappa artifact exists anywhere in the repository.
- **The SWE-bench face is a structural exclusion, not a pass rate**: of 2,197 rows, 1,919 are `harness_invalid` and 278 are judgeable; excluded rows never enter the verdict denominator (disclosed in RQ3). Quoting its pass_rate is misuse.
- **Readings are limited to this batch**: the current authoritative batch compares two endpoints cell by cell (`deepseek-flash` × `mimo-v2.6-pro`, 5 arms × 5 faces); cross-model readings are split by model × arm × face and never pooled, with no extrapolation to untested endpoints or task sets and no cross-batch pooling. The smoke profile of `scripts/run_all_tests.py` runs one task per cell to prove assembly only, with per-cell concurrency resolved per model from provider allowance ∩ machine cap ∩ `--llm-parallel` and hashed into the smoke fingerprint — smoke is not a capability reading.

## Quick Start

```bash
python3 -m venv .venv && source .venv/bin/activate
make install
cp config.local.example .env.local   # fill values only; variable names are in QUICKSTART
make test
```

Full steps (including the venv sandbox being on by default, a first task, and troubleshooting) are in [QUICKSTART.en.md](QUICKSTART.en.md).
LLM endpoints are configured through `LLM_1_API_KEY` / `LLM_1_BASE_URL` / `LLM_1_MODEL_NAME` in `.env.local` (`1` may be replaced by another index).

## Capabilities

| Capability | Entry point | Notes |
|---|---|---|
| Current manuscript tables | `python scripts/tools/results_data_pack_20261111.py` | Zero LLM; needs the verdict rows from the DOI snapshot |
| Test generation + repair loop | `make repro` | Consumes LLM quota; regenerates a batch (retired synthetic protocol) |
| Zero-LLM recomputation (earlier corpus) | `make reproduce-zero-llm` | Statistics, caliber matrix, citation checks |
| Full gate chain | `make gates` | lint / format / typecheck / tests / docs and registry gates |
| Code quality | `make lint` / `make format` / `make typecheck` | [Ruff](https://docs.astral.sh/ruff/) + mypy |
| Mutation evaluation | `make self-mutation` | Mutation testing of this test suite (zero LLM) |
| Repair coverage audit | `make fix-coverage` | Finds repair code never executed by tests |

Deterministic channels: SpecIR v2 compiled assertions, SMT witnesses, Ochiai spectrum,
mutation evaluation, and P2P regression gates.
Fault localization has two channels: Ochiai spectrum (non-LLM) and RGFL-style reasoning
(`FaultLocalizerAgent`, consumes LLM, degrades conservatively on failure).

## Documentation Map

| To learn about | Read |
|---|---|
| Overview and reading paths | [docs/INDEX.en.md](docs/INDEX.en.md) |
| Design and algorithms | [docs/algorithm_design.en.md](docs/algorithm_design.en.md) |
| Modules / CLI / configuration | [docs/api_reference.en.md](docs/api_reference.en.md) |
| Runnable examples | [docs/usage_examples.en.md](docs/usage_examples.en.md) |
| Measurement calibers and cost | [docs/performance_guide.en.md](docs/performance_guide.en.md) |
| Data sources and licenses | [docs/DATA_CARD.en.md](docs/DATA_CARD.en.md) |
| Validity and limitations | [docs/VALIDITY.en.md](docs/VALIDITY.en.md) |
| Known limitations and risks | [MODEL_CARD.en.md](MODEL_CARD.en.md) |
| Security and threat model | [SECURITY.en.md](SECURITY.en.md) · [docs/threat_model.en.md](docs/threat_model.en.md) |
| Common failures | [docs/troubleshooting.en.md](docs/troubleshooting.en.md) |
| Replication package | [REPLICATION.en.md](REPLICATION.en.md) |
| Decision records | [docs/adr/](docs/adr/) |

## Reproduction

Three paths, from cheapest to most expensive:

```bash
make reproduce-zero-llm   # zero LLM: earlier-corpus statistical recomputation + artifact verification
make test                 # test suite (same caliber as CI)
make repro                # regenerate a batch (retired synthetic protocol; consumes LLM quota, do not trigger automatically)
```

The current manuscript's tables take a different zero-LLM path: `python scripts/tools/results_data_pack_20261111.py` (needs the verdict rows from the DOI snapshot).
Prerequisites, image mounts, and the evidence index are in [REPLICATION.en.md](REPLICATION.en.md).

`experiments/manifests/` holds small derived manifests that are not on the Zenodo
deposit's field whitelist and are therefore tracked in the repository. The current
one is `spec_replace_applied_20261111.csv`: the fallback flag of the `+df_spec` arm
for every task row, 1,276 rows after lineage deduplication (894 `attempted_fallback`
and 382 harness-invalid rows with no generation). The manuscript's Limitations and
Appendix C cite this path and its SHA-256 prefix as the re-derivable entry point for
the fallback.

## Test Status

Numbers are maintained in one place: the `tests` / `coverage` / `static_checks` sections of
[BASELINE.yaml](BASELINE.yaml). Re-run locally and in CI with `make test` / `make test-cov`.

Supported: Python 3.12 / 3.13 / 3.14 (CI matrix `3.12/3.13/3.14`, see BASELINE.yaml `python_ci_matrix`).

## Security and Contributing

- Vulnerability disclosure is in [SECURITY.en.md](SECURITY.en.md); do not open a public issue.
- Development setup, pre-submit checks, and documentation conventions are in [CONTRIBUTING.en.md](CONTRIBUTING.en.md).
- Run `make gates` before merging (single chain, not concurrently with other tests).

## License and Citation

MIT, see [LICENSE](LICENSE). The academic citation format is in [CITATION.cff](CITATION.cff).
