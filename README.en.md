# AITester

A **detection-first** Python test generation and repair-evaluation (attribution) research system: given a function-level repair task, it generates pytest tests, executes them, diagnoses failures, and applies patches. Multi-agent orchestration is an ablatable container, not the headline claim.

Current version 1.0.0 · [Changelog](CHANGELOG.en.md) · [Documentation index](docs/INDEX.en.md) · [MIT license](LICENSE)

> **As the EMSE replication package**: every number in the paper is reached by the zero-LLM recompute path (`make reproduce-zero-llm`, and `make reproduce-zero-llm-l1` for L1). The quota-consuming entry points in this repository, `reproduce.sh` and `experiments/run_main_batch.py`, only **regenerate a batch** under the pre-registered configuration; they are not on the path from an artifact to a reported number. [INVENTORY.md](INVENTORY.md) answers the six open-science criteria one by one and lists which branches of the chain currently report `skipped` rather than `passed`.

> Last updated: 2026-10-27

## What It Is

AITester is a research system that orchestrates a Planner → Generator → Executor → Debugger → PatchApplier loop with LangGraph:

- **Input**: function-level repair tasks (synthetic dataset, or SWE-bench Lite split tasks).
- **Process**: generate pytest tests → execute in a sandbox → diagnose failures → produce a patch → re-run.
- **Output**: tests, patches, structured traces, and recomputable metric artifacts.

The research question is not "are multiple agents better", but "can detection-first test generation be a reliable prerequisite for repair". Multi-agent orchestration participates only as an ablatable container (ADR-0016).

## What It Is Not (Honest Disclosure)

- **Not "self-repair achieved"**. Self-repair is a **measurable caliber**, not a proven claim.
- The repair metric is **39.31%** (v2, 57/145 replayable rows; independent gold adjudication) after two rounds of measurement-caliber corrections (ADR-0021/0027/0029). The earlier **repair=0** reading was a **measurement artifact** caused by patch-fence residue and unmaterialized cross-file tasks, not a capability reading. Caliber splits and recomputation are documented in the [repair caliber matrix](docs/design/repair_caliber_matrix.md).
- **The E7 human adjudication has not been executed**: the protocol and preregistration are frozen ([preregistration](docs/preregistration.md)); its results appear in no released reading.
- **SWE-bench Lite covers pipeline capability only; there is no citable pass rate.** Quoting its pass_rate is misuse.
- The main batches use a **single model family** (user-configured OpenAI-compatible endpoints; only the official DeepSeek endpoint is built in). Cross-model extrapolation is out of scope.

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
| Test generation + repair loop | `make repro` | Consumes LLM quota; reproduces the main batches |
| Zero-LLM recomputation | `make reproduce-zero-llm` | Statistics, caliber matrix, citation checks |
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
make reproduce-zero-llm   # zero LLM: statistical recomputation + artifact verification
make test                 # test suite (same caliber as CI)
make repro                # main batches (consumes LLM quota; do not trigger automatically)
```

Prerequisites, image mounts, and the evidence index are in [REPLICATION.en.md](REPLICATION.en.md).

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
