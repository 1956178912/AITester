> **Language**: [中文版](CONTRIBUTING.md) | English (this document)
>
> Last updated: 2026-10-06

# Contributing Guide

Thanks for your interest in AITester! This document explains how to participate in the project's development.

> Z5 (2026-10-06 review fix): this English version had drifted ~8 days behind the
> Chinese one (missing the parallel-test notes, still carrying outdated hard-coded
> coverage numbers that violate the single-source rule, and missing the whole
> "Dependency Exemption Registry" section). It has now been resynchronized with
> CONTRIBUTING.md, and the bilingual gate (`scripts/gates/check_bilingual_docs.py
> --strict`) now covers the root-level document pairs.

## Setting Up the Development Environment

```bash
# Clone the repository
git clone <repository-url> && cd AITester

# Create a virtual environment (Python 3.12+; the locked dependency scipy requires >=3.12)
python3 -m venv .venv && source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env           # non-sensitive items
cp config.local.example .env.local   # LLM keys (LLM_N_*, already gitignored; do not commit)
```

## Commit Conventions

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

- `feat:` new feature
- `fix:` bug fix
- `docs:` documentation change
- `refactor:` code refactoring
- `test:` test-related
- `chore:` build/tooling-related

Examples:
```bash
git commit -m "feat: add synthetic dataset generator"
git commit -m "fix: fix incorrect parametrize validation logic"
```

## Code Style

- Python follows [PEP 8](https://peps.python.org/pep-0008/)
- All functions must include a Chinese docstring
- Line length ≤ 120 characters
- Use type annotations (typing module)

## Testing Requirements

New features must be accompanied by unit tests:

```bash
# Run all tests (serial, historical default)
.venv/bin/python -m pytest tests/ -v

# Parallel speed-up (recommended for local dev: -n auto shards by CPU count, full suite ~21s vs ~49s serial)
.venv/bin/python -m pytest tests/ -n auto --dist loadfile

# View coverage
.venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

Notes on parallel runs (introduced in the 2026-10-01 performance batch):
- `pytest-xdist` (locked at 3.8.0 in requirements) provides `-n`; `--dist loadfile`
  shards by file, preserving within-file case order — the isolation semantics
  are unchanged.
- Without `-n`, everything degrades to the historical serial behavior (zero
  change by default).
- CI already runs the full suite with `-n 4 --dist loadfile` (same semantics as
  serial, producing coverage.xml).

Coverage requirements use [BASELINE.yaml](BASELINE.yaml)'s `coverage` section as
the single source of truth (P1-9 fix: this section used to hard-code "core ≥ 92% /
overall ≥ 90%", which had drifted from the measured values and violated the
single-source rule). Merge gates follow the actual CI thresholds: total line
coverage ≥ 85%, total branch coverage ≥ 77%, strict core modules ≥ 90%, other
core routing modules ≥ 85% (the constants in `scripts/gates/check_branch_coverage.py`
are the authoritative values).

## Pull Request Process

1. Fork this repository
2. Create a feature branch (`git checkout -b feat/xxx`)
3. Commit your changes (`git commit -m "feat: xxx"`)
4. Push to your fork (`git push origin feat/xxx`)
5. Create a Pull Request

## Reporting Issues

Please use GitHub Issues to report bugs or propose features, in the following format:

- **Bug report**: reproduction steps, expected behavior, actual behavior, environment information
- **Feature suggestion**: problem description, proposed solution, use cases

## Documentation Organization Conventions

- **Core maintenance docs** (updated with each release): `README.md` / `QUICKSTART.md` / `docs/api_reference.md` / `docs/algorithm_design.md` / `CHANGELOG.md` and their `.en.md` counterparts — must be refreshed after a feature batch lands; CI's `scripts/gates/check_bilingual_docs.py` guards the Chinese/English pairing.
- **Historical archive docs** (`docs/history/`, including `optimization_plan.md` / `optimization_report.md`, etc.): record the decisions and experiment logs of past batches — **not current maintenance docs**; internal reference only, no need to update per release; each doc's header carries an archival note, and the CHANGELOG is the authority on current decisions.

### Hard rule: single source of truth for current baseline numbers (BASELINE.yaml)

- **No core maintenance doc may embed numbers that have been superseded by later batches** (e.g. "1937 passed / 94% coverage / 0 ruff warnings" — snapshots that go stale as batches progress). Current baseline numbers (test count / coverage / ruff / mypy / CI matrix) use the repo-root [`BASELINE.yaml`](BASELINE.yaml) as the **machine-readable single source of truth**; core docs keep only a "link to BASELINE.yaml + one-line summary" and never hard-code the numbers.
- **Expired content is archived as a whole section, never annotated in place**: historical analysis / baseline trajectories superseded by later batches are moved wholesale to `docs/history/` (or the corresponding CHANGELOG entry); they must not be stacked inside core docs as ⚠️ / "historical snapshot" annotations. The archival note in a historical doc's header is the only place where historical annotation is allowed.
- **Maintenance rule**: after any feature batch lands, first run the full `pytest tests/` / `ruff check .` / `mypy` for measured output, then refresh `BASELINE.yaml`'s `last_verified` and numbers; do not cite that batch's numbers in core docs before the refresh.
- **Version-history tables** (CHANGELOG / api_reference version tables) record snapshots at the time — historical narrative, not refreshed with BASELINE.yaml. The boundary is "current baseline" vs "historical version records".

## Dependency Change Checklist (required steps when touching requirements / lock)

`requirements.txt` (top-level deps, pinned with `==`) and `requirements.lock` (full lockfile
including transitive deps) form a **dual-track** scheme: CI guards their sync with
`scripts/gates/check_lock_sync.py` (top-level deps must appear in the lock with matching versions).
When changing any dependency you **must** run this checklist, otherwise you risk "added a package
to requirements but forgot the lock → CI passes yet production / Docker behavior drifts":

1. **Edit `requirements.txt`**: pin top-level deps with `==` (same principle as the CI-pinned
   tool versions, to avoid upstream releases drifting the gate);
2. **Regenerate `requirements.lock`**: on a target Python version (CI matrix 3.12 / 3.13 /
   3.14), rebuild the lock (pip-compile or `pip freeze` caliber, matching the lock's existing
   format — includes transitive deps);
3. **Validate locally**: `python scripts/gates/check_lock_sync.py` exits 0 (rules 1/2 block;
   rule 4's "extra lock entries" are WARNING only, but prompt a lock regeneration);
4. **Docker image**: dependency changes require an image rebuild (`docker build -t
   aitester:latest .`; build-time pre-install uses the same locked versions, see the
   `Dockerfile` comment);
5. **CI matrix validation**: after pushing the PR, confirm all three versions
   (3.12 / 3.13 / 3.14) are green (3.13 is within the locked scipy/pandas support range,
   added to the matrix in the 2026-09-28 batch).

> Before submitting a PR, check the "dependency change checklist" in the PR template
> (`.github/PULL_REQUEST_TEMPLATE.md`). Failure recovery: when `check_lock_sync.py` exits 1,
> use the "rule-1 missing entry / rule-2 version drift" hints to locate whether requirements
> missed a declaration or the lock version drifted; regenerate the lock, then re-validate.

## First Tasks for New Contributors

For first-time participation, start with these low-barrier task types (no full-architecture
knowledge required):

- **Doc gap-filling**: core-doc docstring / comment errata, missing sections (see the
  `check_bilingual_docs.py` pairing-missing items in CI).
- **Regression tests**: add boundary-condition cases under `tests/` (read the target
  module's docstring first to understand the contract).
- **Dependency hygiene**: use of `pip-audit` / `requirements.lock` sync validator
  (`scripts/gates/check_lock_sync.py`).
- **CI debugging**: read the step comments in `.github/workflows/ci.yml` to understand
  each gate's intent.

Larger algorithm / architecture changes (error-classifier expansion, cross-file repair
strategy, etc.) should be discussed in an Issue first; read `docs/algorithm_design.md`
and `CHANGELOG.md` to understand the existing design trade-offs.

## Dependency Exemption Registry (required steps for pip-audit vulnerability exemptions)

Known vulnerabilities hit by `pip-audit` that need an explicit exemption (CI
`--ignore-vuln`) because "no fixed version is available upstream" **must** be
registered in [docs/dependency_exemptions.md](docs/dependency_exemptions.md)
(dependency / locked version / vulnerability ID / exemption reason / re-review
trigger / re-review deadline). Adding `--ignore-vuln` to ci.yml without leaving
a registry entry is not allowed.

- New exemption: register first, then edit ci.yml (both land in the same PR,
  keeping it auditable);
- Upstream releases a fix: follow the registry's "re-review trigger" column to
  upgrade promptly, remove the corresponding `--ignore-vuln` line from ci.yml,
  and move the entry from "current exemptions" to "reviewed & closed";
- Re-review the registry quarterly (entries past their re-review deadline get a
  "exemption expired" note in the CHANGELOG), consistent with the dual-track
  dependency-change checklist (requirements / lock).
