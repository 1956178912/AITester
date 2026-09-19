> **Language**: [中文版](optimization_report.md) | English (this document)

> **Archive note (2026-09-15)**: This document was originally `OPTIMIZATION_REPORT.md` at the repository root; it is now archived under `docs/history/` (historical round work records, not a currently maintained document). See the CHANGELOG and the global decision log in the user workspace for current-round optimization decisions.

# AITester Project Optimization Report

> This report is the complete delivery record of the 2026-09-11 optimization round. The Phase 0 baseline and the Phase 1
> optimization points list are detailed in `optimization_plan.md`; Phases 3-5 were completed within the same round;
> Phase 6 push and PR await the user's final confirmation.
>
> **Subsequent rounds**: for the 2026-09-12 round (documentation data alignment batch, N-01~N-04), see the complete
> record in the appendix at the end, "Appendix: 2026-09-12 Round"; for the 2026-09-13 round (documentation data alignment batch, M-01~M-03), see
> "Appendix: 2026-09-13 Round"; for the 2026-09-13 system feature enhancement round (3.1/3.4/4.1/2.3/1.5), see the complete record in
> "Appendix: 2026-09-13 System Feature Enhancement Round". See the same-named sections in `optimization_plan.md` for the points list and implementation batches.
> For the 2026-09-14 improvement checklist batch (G-01~G-04 + 3.4 + 3.5) and the 4.2 half-open probe batch, see the complete records in
> "Appendix: 2026-09-14 Improvement Checklist Batch" and "Appendix: 2026-09-14 4.2 Half-Open Probe Batch".
> For the 2026-09-18 ~ 09-19 code-quality & reliability round (0.1 → 0.2, two atomic commits `9f83197` + `d5f21f6`),
> see "Appendix: 2026-09-18 ~ 09-19 Code-Quality & Reliability Round".
>
> **Current latest baseline (2026-09-19 round 0.2)**: the full-suite tests advanced to
> **1460 passed / 0 failed / 96% coverage**, `ruff check` / `ruff format --check` all green;
> the 1163 (batch ③) / 1225 (improvement checklist batch) / 1158 (F batch) / 1237 (4.2 half-open probe batch) /
> 1247 / 1270 (09-15 convergence round) items below are kept as historical round records and
> do not represent the current latest baseline.

## Phase 0: Baseline Check

### Git Status (measured snapshot at the time of this run)

- **Branch**: `main`, clean working tree
- **Local ahead of**: `origin/main` by 15 commits (the `ahead` count at session start; zeroed after the Phase 6 push)
- **Remote**: `https://github.com/1956178912/AITester.git`

### Project Structure

```
AITester/
├── src/                    # Core package (collected by find_packages)
│   ├── agents/             # Multi-agent (Planner/Generator/Executor/Debugger/ErrorClassifier)
│   ├── api/                # API management and multi-model rotation
│   ├── cli/                # CLI entry (app.py + output.py)
│   ├── config/             # Configuration generation and management (config_manager.py + config_generator.py)
│   ├── datasets/           # SWE-bench/Defects4J loading and synthetic datasets
│   ├── db/                 # MySQL client
│   ├── experiments/        # Experiment analysis and reporting
│   ├── graph/              # LangGraph workflow orchestration
│   ├── prompts/            # Prompt templates
│   ├── rag/                # Retrieval-augmented generation
│   ├── reports/            # Experiment report generation
│   ├── tools/              # Tools (code analysis, patch application, dependency management)
│   └── utils/              # General utilities (helpers, exceptions, logging)
├── tests/                  # ~38 test files
├── examples/               # Sample code
├── experiments/            # Experiment output and intermediate data (partly excluded by .gitignore)
├── scripts/                # Helper scripts
├── docs/                   # Documentation
├── config.py               # Global configuration (centralized management of environment variables)
├── llm_configs.json        # LLM configuration (provider-grouped metadata, no real keys)
├── setup.py                # Package management
├── main.py                 # Thin CLI wrapper (delegates to src/cli/app.py)
├── requirements.txt        # Dependency lock (== versions)
├── requirements.lock       # Full lock file (pip freeze artifact)
├── .env.example            # Environment variable example (template)
├── .env.local.template     # LLM sensitive configuration template
├── .github/workflows/ci.yml  # CI configuration (tests + security scan)
└── ...
```

### Tech Stack & Package Manager

- **Language**: Python 3.14.6 (venv)
- **Frameworks**: langchain 1.3.15, langchain-openai 1.4.3, langgraph 1.2.11
- **Database**: pymysql 1.2.0, DBUtils 3.1.2
- **Testing**: pytest 9.1.1, pytest-cov 7.1.0, pytest-timeout 2.4.0
- **Lint**: ruff 0.16.3
- **Dependency management**: pip (requirements.txt == lock + requirements.lock full lock)
- **Entry point**: `aitester=src.cli.app:cli` (setup.py console_scripts)

### Command Inventory

| Operation | Command |
|-----------|---------|
| Install dependencies | `pip install -r requirements.txt` |
| Build/package | `pip install .` or `python -m build` |
| Run tests | `python -m pytest tests/` |
| Coverage | `python -m pytest tests/ --cov=src --cov-report=term` |
| Lint | `ruff check .` |
| Format | `ruff format --check .` |
| Type check | No explicit mypy/pyright configuration (the project does not use a static type checker) |
| Security scan | `pip-audit -r requirements.txt` (run in CI) |

### Baseline Results

| Check | Command | Result | Notes |
|--------|------|------|------|
| Ruff Lint | `ruff check .` | ✅ passed | All checks passed |
| Ruff format | `ruff format --check .` | ✅ passed | 121 files already formatted |
| Unit tests | `python -m pytest tests/` | ✅ passed | 1020 passed, 2 warnings, 28.4s |
| Coverage | `--cov=src` | ✅ 91% | TOTAL 3536/326 miss = 91% |
| Type check | No mypy config | ⚠️ N/A | The project has not introduced a static type checker |
| Build | `pip install .` | ⚠️ unverified | Not run at baseline; to be covered in Phase 4 |

### Sensitive Information Notes

- `.env`, `.env.local`, `.env.local.bak` are all excluded by `.gitignore` and not tracked by Git
- `config.py` reads LLM sensitive configuration (LLM_N_* variables) from `.env.local`; no hardcoded keys
- `llm_configs.json` records only provider metadata; no real API Keys
- ⚠️ The local `.env` file contains real keys (OPENAI_API_KEY, OPENAI_API_KEY_2, OPENAI_API_KEY_3) but is **not tracked by Git**

---

## Phase 1: Project Search & Optimization Point Identification

For the full points table (16 items, with evidence after deduplication, impact, priority, verification), see the "Phase 1 Optimization Points List" in `optimization_plan.md`.
Key points summary:

- **Stale docs (P2/P3, 4 items)**: README ghost test files 4 rows (D-01), stale case-count/coverage data (D-02/D-08), ablation switch wording inconsistent with .env.example (D-09)
- **Log redaction blind spot (P2, D-07)**: the old regex in `logging_utils.py` covered only the `sk-` prefix + 20+ alphanumeric characters; two types of local real keys — "long sk- type with dotted segments" and "long hex/base64 without sk- prefix" — could bypass redaction → the regex was extended and 14 synthetic placeholder cases were added
- **Sandbox audit (P1 to confirm, T-04)**: the executor subprocess boundary needs a dedicated audit; not done this round (high risk, needs a design doc; listed as a follow-up suggestion)
- **Key leak (P1 notification, D-05)**: local `.env` / `src/.env.local` contain real API keys in plaintext (2 sk- prefixed + 1 long key without sk- prefix), none tracked by Git (verified with `git ls-files`); **out of this round's code change scope**; the user is advised to rotate these keys as soon as possible
- **Test maintainability (P3, T-01)**: each test file repeatedly constructs LLMConfig/APIManager mocks; a common fixture could be extracted — the refactoring scope is large; listed as a follow-up suggestion
- **CLI branch coverage (P2, T-03)**: missing parallel/json boundary cases → 4 argument validation cases added
- **Local config drift (P3, D-04)**: the local `.env`'s `DOCKER_IMAGE=python:3.11-slim` inconsistent with the template/default 3.12-slim → fixed locally (`.env` not in the repo; no commit)

## Phase 2: Optimization Plan

The plan table (batches A/B/C + follow-up suggestions + items to confirm) is in `optimization_plan.md` "Scope of This Implementation".
The user confirmed: ① batch B1 redaction regex extension included this round; ② local .env changed to 3.12-slim along the way; ③ Phase 4 full verification; ④ push main and create a PR.

## Phase 3: Optimization Implementation

All changes are committed (commit history in `git log`); the mapping is:

| Commit | Content |
|------|------|
| `40ef2e7` docs(readme) | Removed 4 non-existent test files from the test status table (A1) |
| `cd058b4` docs(readme) | Case count/coverage aligned to the 0.9.11 baseline (A2, first stage) |
| `4c7e17d` docs(readme) | Ablation experiment switch configuration location wording aligned (A3) |
| `0558090` fix(utils) | Log redaction regex covers dots/keys without sk- prefix + new test_logging_utils.py (B1) |
| `e5252a6` fix(packaging) | setup.py declares py_modules to collect root-level config; CLI argument validation test backfill (B2 + packaging fix) |
| `94433a2` style(tests) | ruff format normalization of new test files |
| `68fb35f` docs(changelog) | Added Unreleased optimization round entry + README case count aligned to 1038 (A2 convergence) |
| `80e2f05` fix(utils) | Real-key shapes in tests and comments replaced with synthetic placeholders (zero tolerance for sensitive info) |
| `ab9edb7` chore(changelog) | CHANGELOG synced to the redaction placeholder baseline |

The local .env DOCKER_IMAGE fix (C1) is an out-of-repo file; no commit.

## Phase 4: Full Testing

Measured results of this run (venv Python 3.14.6, commands aligned with CI):

| Check | Command | Result | Notes |
|--------|------|------|------|
| Unit tests | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 27.7s | The 2 warnings are scipy numerical precision notes, not a code issue |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 (consistent with the lock) |
| Format | `ruff format --check .` | ✅ 124 files already formatted | |
| Lock sync | `python scripts/check_lock_sync.py` | ✅ requirements.txt (19 items) and requirements.lock (130 items) consistent | Same check as CI |
| Build | `python -m build --wheel` | ✅ built aitester-0.9.11-py3-none-any.whl (107 files) | Verified config.py enters the wheel (regression of the fix point) |
| Security scan | `pip-audit -r requirements.txt --no-deps --ignore-vuln ...` | ✅ No known vulnerabilities found, 5 ignored | Exemption list consistent with CI (chromadb has no fixed version yet; see ci.yml comments) |
| Type check | No mypy/pyright config | ⚠️ N/A | The project has not introduced a static type checker; kept as-is |
| Coverage | `pytest --cov=src` | ✅ 91% | Consistent with the CHANGELOG/README baseline |

## Phase 5: Documentation Update

- `CHANGELOG.md`: Unreleased round entry completed (security/packaging/testing/documentation sections; see `68fb35f`, `80e2f05`, `ab9edb7` in `git log`)
- `README.md`: case count 1038 / coverage 91% aligned; ghost test file rows removed; ablation switch wording aligned
- `optimization_plan.md` / `optimization_report.md`: complete record of Phases 0-5 (this file + the plan file), committed together with this round
- Local `.env`: DOCKER_IMAGE → 3.12-slim (not in the repo; no doc impact)

## Phase 6: Upload to GitHub

The user confirmed "push main and create a PR". Actual execution: **the push is still blocked by the network** —
retest at 2026-09-11 19:07: `curl https://github.com` short connection reachable (HTTP 200), but `git push`
failed both times (within the default 60s / 180s timeout windows):
`Failed to connect to github.com port 443 after 75003 ms: Couldn't connect to server`.
Signature: HTTP GET passes, but git's long-connection 443 handshake hangs (the outbound link appears to restrict large packets/long connections of the git protocol).
The working tree is clean; the commit state is intact.

Content to push: all **17 commits** (`bd4de49`…`eaf7931`, one more `eaf7931` docs wrap-up commit than the previous record) that `origin/main` (d42bbdd) is behind (the full list in `git log refs/remotes/origin/main..main --oneline`).

Manual commands (after network/proxy recovery):

```bash
cd /Users/wangchenyu/Workspace/AITester
# 1. Push main (if the 443 handshake hangs again, try falling back first:
#    git config http.version HTTP/1.1
#    or set a proxy: git config http.proxy http://127.0.0.1:<port>)
git push origin main

# 2. Create the PR (gh is not installed; use the GitHub Web UI or install gh first)
gh pr create --base main \
  --title "chore(optimize): 0.9.11 optimization round — doc alignment, log redaction extension, packaging fix, and CI security gate sync" \
  --body-file /dev/stdin <<'EOF'
## Background
An optimization round on the 0.9.11 baseline (1020 cases / 91% coverage / all ruff green): fixed stale README data and ghost entries, log redaction regex blind spots, setup.py packaging missing the root-level config, and pip-audit exemption list drift.

## Changes
- **fix(utils)**: extended the log redaction regex (dotted-segment sk- type / long hex·base64 without sk- prefix) + real-key shapes in test comments replaced with synthetic placeholders (zero tolerance for sensitive info)
- **fix(packaging)**: setup.py `py_modules=["config"]` (the entry no longer raises ModuleNotFoundError after a proper install) + extras completion
- **chore(ci)**: pip-audit exemption list synced to the measured vulnerability IDs (CVE-4583x → PYSEC-2026-3813/3814/3815)
- **fix(datasets / experiments / utils)**: Defects4J O(n²) elimination, significance skipped-entry KeyError, extract_code_block swallowing identifier lines
- **docs(readme / changelog / optimize)**: case count aligned to 1038, ghost test file rows removed, ablation switch wording, OPTIMIZATION_PLAN/REPORT checked in

## Test Results
| Check | Command | Result |
|--------|------|------|
| Unit tests | `pytest tests/ -q` | 1038 passed / 0 failed (27.7s) |
| Lint | `ruff check .` | All checks passed |
| Format | `ruff format --check .` | 124 files already formatted |
| Lock sync | `python scripts/check_lock_sync.py` | passed (19 vs 130 items consistent) |
| Build | `python -m build --wheel` | aitester-0.9.11-py3-none-any.whl (config.py verified in the package) |
| Security scan | `pip-audit` (same exemption list as CI) | No known vulnerabilities found, 5 ignored |
| Coverage | `pytest --cov=src` | 91% (consistent with the README/CHANGELOG baseline) |

## Risks & Rollback
- The redaction regex extension is purely additive matching branches; all old cases passed (1038, no failures) — no collateral regression; roll back with a single `git revert 0558090`
- The setup.py fix is purely a declaration completion; no behavior change for editable installs; roll back with `git revert e5252a6`
- The pip-audit exemption drift is a CI config sync; no runtime impact; roll back with `git revert 3bf75bb`
- This PR contains no sensitive information (real keys exist only in the gitignored local .env; the commit history has been normalized to synthetic placeholders, see 80e2f05)

## Checklist
- [x] build / tests / lint / format / lock sync all green
- [x] full 1038 cases passed; coverage 91% aligned with the docs
- [x] no sensitive information in the repo (git ls-files confirms the .env family is untracked)
- [x] no undocumented breaking changes (setup.py extras additions are incremental)
- [x] docs (README/CHANGELOG/OPTIMIZATION_*) consistent with the code

## Additional Verification This Round (2026-09-11 19:06-19:07)

| Check | Command | Result | Notes |
|--------|------|------|------|
| Unit tests | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 28.07s | 2 warnings are scipy precision notes |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 |
| Format | `ruff format --check .` | ✅ 124 files already formatted | |
| Lock sync | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 items consistent | |
| Build | `python -m build --wheel` | ✅ aitester-0.9.11-py3-none-any.whl | config.py entering the package verified |
| Security scan | `pip-audit` (same exemptions as CI) | ✅ No known vulnerabilities found, 5 ignored | PYSEC-2026-311/3813/3814/3815 exempted |
| Coverage | `pytest --cov=src` | ✅ TOTAL 91% (3536 lines) | Consistent with the doc baseline |
| Push | `git push origin main` | ❌ 443 handshake hung (75s timeout ×2) | 17 commits ready; see the manual commands above |
EOF
```

> If `gh` is unavailable: open `https://github.com/1956178912/AITester/compare/main...main` in the browser (the compare link appears automatically after the push) → Create new pull request, using the content from `## 背景` (Background) to `## 检查清单` (Checklist) above as the body.

## Phase 7: Final Report

### Completion Status
- Phases 0-5: **all completed**, working tree clean, local main 17 commits ahead of origin/main
- Phase 6: **blocked by the network** (retest at 2026-09-11 19:07: HTTP short connection reachable but the git 443 long-connection handshake hangs;
  two push failures; gh not installed). The 17 commits are ready but unpushed; manual commands and the PR body are in the previous section;
  after the network recovers, `git push origin main` completes it

### Optimization Items List and Results
| Item | Result |
|----|------|
| D-01 README ghost test files 4 rows | ✅ removed (40ef2e7) |
| D-02/D-08 stale case count/coverage | ✅ aligned to 1038/91% (cd058b4 + 68fb35f) |
| D-09 ablation switch wording | ✅ aligned (4c7e17d) |
| D-04 local .env DOCKER_IMAGE drift | ✅ fixed locally 3.11→3.12-slim (not in the repo) |
| D-07 log redaction regex blind spot | ✅ extended + 14 synthetic placeholder cases (0558090) |
| D-05 local real keys | ⚠️ notification only, no code change; `80e2f05` normalized real-key shapes in tests/comments to placeholders; **recommend rotating the LLM keys in .env as soon as possible** |
| B2 CLI argument validation gap | ✅ 4 cases added (e5252a6) |
| T-01 common fixture extraction / T-04 executor sandbox audit | 📋 listed as follow-up suggestions (large refactoring scope / needs a design doc) |
| Packaging defect (found during this round's verification) | ✅ setup.py py_modules fixed (e5252a6) |
| CI pip-audit exemption drift | ✅ synced (3bf75bb) |

### Test Results Summary
Full pytest 1038 passed / ruff check·format all green / lock sync passed / wheel build succeeded with config.py in the package / pip-audit no unexempted vulnerabilities / coverage 91%. The detail table is in "Phase 4".

### Documentation Update Summary
CHANGELOG (Unreleased entry), README, OPTIMIZATION_PLAN/REPORT all checked in; no redundant new code comments.

### Risks & Rollback
- All changes can be rolled back per commit via `git revert <hash>` (mostly single-file, no cross-file coupling)
- The redaction regex is purely additive matching branches; zero failures out of 1038 cases is the regression evidence
- setup.py is a declaration completion; the editable dev flow behavior is unchanged
- No sensitive information in the repo; the real keys in the local .env should be rotated (unrelated to this code change)

### Follow-up Suggestions
1. After the network recovers, run the Phase 6 manual commands to push the 17 commits and open the PR (the body is prepared)
2. Rotate the LLM API Keys in the local .env (they were exposed once in the session; under the zero-tolerance principle, replacement is recommended)
3. T-01 common fixture extraction (test maintainability) and T-04 executor sandbox deep audit (needs a design doc) scheduled for the next iteration
4. After a fixed chromadb version is released, upgrade and remove the corresponding `--ignore-vuln` in ci.yml (PYSEC-2026-3813/3814/3815)

---

## Appendix: 2026-09-12 Round (Documentation Data Alignment Batch)

> This round ran on top of the 0.9.11 round's 18 commits pending push and added 4 commits
> (`d1afffc` / `5c7fc80` / `d683741` / `a563d60`). See the "Post-0.9.11 Optimization Round (2026-09-12)" section of `optimization_plan.md` for the points list (N-01~N-04) and
> the search conclusions.

### Phase 0: Baseline Check

- **Git status**: `main`, clean working tree, local 18 commits ahead of `origin/main`
- **New baseline** (venv Python 3.14.6):

| Check | Command | Result |
|--------|------|------|
| Unit tests | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 27.9s |
| Coverage | `--cov=src` | ✅ TOTAL 91% (3536/318 miss) |
| Lint | `ruff check .` | ✅ All checks passed |
| Format | `ruff format --check .` | ✅ 124 files already formatted |
| Lock sync | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 items consistent |
| Build | `python -m build --sdist --wheel` | ✅ aitester-0.9.11.tar.gz + .whl |
| Security scan | `pip-audit` (same exemption list as CI) | ✅ No known vulnerabilities found, 5 ignored |
| Type check | No mypy/pyright config | ⚠️ N/A (consistent with the previous round) |

### Phase 1: Optimization Point Identification (Key Points)

- **N-01 (P2)**: stale core-module coverage data in the README test status table (logging_utils 83%→88%, cli/app.py 61%→64%); not synced after 18 cases were added last round
- **N-02 (P2)**: the README security scan note still says "4 known CVEs"; ci.yml has drifted to the PYSEC exemption baseline
- **N-03 (P3)**: the wording of QUICKSTART step 4 "Verify configuration" does not match the actual behavior (`from config import LLM_CONFIGS` is a load check only, no network call)
- **N-04 (P2)**: `ls`-checked the test files referenced by the README one by one — **all exist**, no fix needed (no commit)
- Search conclusions (dimensions with no points): no eval/exec/os.system dangerous calls in the source; no real key residual in source or tests (re-check passed after the 80e2f05 normalization); all dependencies in sync with the lock, pip-audit no unexempted vulnerabilities; CI structure complete, no drift; no TODO/FIXME residual in src

### Phase 3: Implementation Record

| Commit | Content |
|------|------|
| `d1afffc` docs(readme) | N-01 coverage data aligned to 88%/64% |
| `5c7fc80` docs(readme) | N-02 security scan note aligned to the PYSEC exemption baseline |
| `d683741` docs(quickstart) | N-03 configuration verification step wording fixed |
| `a563d60` docs(changelog) | Added this round's Unreleased entry to the CHANGELOG |

(N-04 check found no drift; no commit; pure documentation changes, source untouched; minimum verification was `ruff check` + the relevant test subset all green.)

### Phase 4: Full Testing (all commands aligned with CI, venv Python 3.14.6)

| Check | Command | Result | Notes |
|--------|------|------|------|
| Unit tests | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 28.6s | The 2 warnings are scipy numerical precision notes, not a code issue |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 |
| Format | `ruff format --check .` | ✅ 124 files already formatted | |
| Lock sync | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 items consistent | |
| Build | `python -m build --sdist --wheel` | ✅ tar.gz + whl both succeeded | |
| Security scan | `pip-audit -r requirements.txt --no-deps --ignore-vuln ...` | ✅ No known vulnerabilities found, 5 ignored | Exemption list consistent with CI |
| Coverage | `pytest --cov=src` | ✅ TOTAL 91% | Consistent with the README/CHANGELOG baseline |
| Type check | No mypy/pyright config | ⚠️ N/A | The project has not introduced a static type checker; kept as-is |

### Phase 5: Documentation Update

- `CHANGELOG.md`: new 2026-09-12 Unreleased round entry (documentation batch + full test results)
- `optimization_plan.md` / `optimization_report.md` (this appendix): this round's complete record checked in
- README/QUICKSTART: the N-01~N-03 alignment changes were committed with the code commits

---

## Appendix: 2026-09-13 Round (Documentation Data Alignment Batch M-01~M-03)

> This round ran on top of the 2026-09-12 round's 4 commits (`d1afffc`/`5c7fc80`/`d683741`/`a563d60`).
> The 09-12 round's 18 commits pending push were completed (clean working tree, local in sync with origin/main);
> this round adds 2 commits (`5553c35` + the plan/report check-in commit).
> See the "Post-0.9.11 Optimization Round (2026-09-13)" section of `optimization_plan.md` for the points list (M-01~M-03) and the search conclusions.

### Phase 0: Baseline Check

- **Git status**: `main`, clean working tree, local in sync with `origin/main` (the 09-12 round backlog fully pushed)
- **New baseline** (venv Python 3.14.6):

| Check | Command | Result |
|--------|------|------|
| Unit tests | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings, 28.1s |
| Coverage | `--cov=src` | ✅ TOTAL 91% (3536/318 miss) |
| Lint | `ruff check .` | ✅ All checks passed |
| Format | `ruff format --check .` | ✅ 124 files already formatted |
| Lock sync | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 items consistent |
| Build | `python -m build --sdist --wheel` | ✅ tar.gz + whl both succeeded |
| Security scan | `pip-audit` (same exemption list as CI) | ✅ No known vulnerabilities found, 5 ignored |
| Type check | No mypy/pyright config | ⚠️ N/A (consistent with the previous round) |

### Phase 1: Optimization Point Identification (Key Points)

- **M-01 (P2)**: the 13 files' case counts in the README "test coverage module" main table drifted from the measured `def test_` counts (not synced after the 0.9.11 batch added 27 regression cases): test_api_manager 62→63, test_cli_app 11→15, test_config_manager 29→32, test_dataset_loader_extended 57→62, test_dependency 27→35, test_error_classifier 56→60, test_executor 35→39, test_experiments_analysis 11→15, test_experiments_scripts 8→10, test_generator 21→30, test_mysql_client 12→13, test_patch_applier 36→38, test_workflow 28→30
- **M-02 (P2)**: README's "41 test files" does not match the actual 44 .py files in tests/; the main table is missing `test_logging_utils.py` (the 14-case redaction test added in the 0.9.11 round) — corrected to 44 and the row added
- **M-03 (P3)**: the CHANGELOG 2026-09-13 Unreleased round entry added (this round's pure doc changes must be traceable)
- Search conclusions (dimensions with no points): no eval/exec/os.system dangerous calls in src (re-check passed); the executor's `_run_pytest_with_retry` subprocess.run is a controlled pytest command (timeout/cwd/env constraints, not user-input concatenation), no escape calls at the sandbox boundary; real keys exist only in the gitignored local .env (2 sk-) and src/.env.local (5 sk-); `git ls-files` tracks only placeholder templates; rotation recommended; all 130 dependencies in sync with the lock; pip-audit no unexempted vulnerabilities; no CI structure drift; no stale data residual in docs/ or QUICKSTART

### Phase 3: Implementation Record

| Commit | Content |
|------|------|
| `5553c35` docs(readme) | M-01 main table 13 rows' case counts synced + M-02 file count 41→44 and the test_logging_utils row added |
| (plan/report check-in commit) docs(optimize) | M-03 CHANGELOG entry + OPTIMIZATION_PLAN/REPORT 09-13 sections |

(The v0.9/v0.10 historical version narrative tables keep their original values; by design they do not follow the baseline; pure doc changes, source untouched.)

### Phase 4: Full Testing (all commands aligned with CI, venv Python 3.14.6)

| Check | Command | Result | Notes |
|--------|------|------|------|
| Unit tests | `python -m pytest tests/ -q` | ✅ 1038 passed, 2 warnings | Pure doc changes; the test suite is unchanged |
| Lint | `ruff check .` | ✅ All checks passed | ruff 0.16.3 |
| Format | `ruff format --check .` | ✅ 124 files already formatted | |
| Lock sync | `python scripts/check_lock_sync.py` | ✅ 19 vs 130 items consistent | |
| Build | `python -m build --sdist --wheel` | ✅ tar.gz + whl both succeeded | |
| Security scan | `pip-audit` (same 4 PYSEC exemptions as CI) | ✅ No known vulnerabilities found, 5 ignored | |
| Coverage | `pytest --cov=src` | ✅ TOTAL 91% | Consistent with the README/CHANGELOG baseline |
| Type check | No mypy/pyright config | ⚠️ N/A | Kept as-is |

### Phase 5: Documentation Update

- `CHANGELOG.md`: new 2026-09-13 Unreleased round entry (M-01/M-02 notes + full-suite test conclusion)
- `optimization_plan.md` / `optimization_report.md` (this appendix): this round's complete record checked in
- `README.md`: main table 13 rows + file count + the test_logging_utils row added (committed with `5553c35`)

### Phase 6: Upload to GitHub

The user confirmed "documentation batch + push; retry if the push fails". Ran `git push origin main` (2 commits this round;
the 09-11/09-12 rounds' 18-commit backlog was pushed earlier). If the 443 handshake hangs (per historical round experience), retry with the fallback
`git config http.version HTTP/1.1` or the proxy approach; if it still fails, output the manual commands + an explanation.

### Phase 7: Follow-up Suggestions

1. Rotate the LLM API Keys in the local .env / src/.env.local (zero-tolerance principle; the suggestion is retained across rounds)
2. T-01 common fixture extraction (test maintainability) and T-04 executor sandbox deep audit (needs a design doc) scheduled for the next iteration
3. After a fixed chromadb version is released, upgrade and remove the corresponding `--ignore-vuln` in ci.yml (PYSEC-2026-3813/3814/3815; the 2 duplicate 311 entries are its alias entries)

---

## Appendix: 2026-09-13 System Feature Enhancement Round (3.1 / 3.4 / 4.1 / 2.3 / 1.5)

### User Checklist Verification (first identify already-implemented items to avoid rework)

The user proposed 20 optimization suggestions; after checking the current code state one by one, **8 are already implemented** (the suggestions predated the code updates):

| User Item | Status | Evidence Location |
|---------|------|---------|
| 1.2 Error classification refinement (import/type/logic) | ✅ implemented | `src/agents/error_classifier.py` (P2 refinement: IMPORT_ERROR/TYPE_ERROR/LOGIC_ERROR split out of the old five categories) |
| 1.3 Dependency isolation | ✅ implemented | `EXECUTOR_USE_VENV` + sandbox venv + `PYTHONPATH` control + automatic dependency installation (`src/tools/dependency.py`) |
| 1.4 Connection pool configurability | ✅ implemented | `MYSQL_POOL_*` read from `config.py` environment variables (`src/db/mysql_client.py`) |
| 2.1 SWE-bench validation | ✅ implemented | `validate_task` / `quality_report` / `_extract_suggested_function` + source supplementation channel (`dataset_loader.py`) |
| 2.2 Token efficiency comparison | ✅ implemented | `src/graph/token_usage.py` + benchmark `token_metrics` aggregation |
| 2.3 RAG retrieval quality | ✅ implemented | `evaluate_retrieval` (Hit Rate/MRR) + `--enable-rag` + `RAG_PERSIST_PATH` (default `rag_data/`) |
| 1.1 Full-chain log redaction | ✅ implemented | `SensitiveFormatter` covers exception stacks + redaction wired into all base_agent LLM paths |
| 4.3 Circuit breaker | ✅ implemented | `APIHealth.max_consecutive_failures` threshold wiring (N consecutive failures mark unhealthy and remove from routing) |

### What This Batch Implemented (the 4 items truly missing + 2 strengthening items, 6 atomic commits)

| # | Goal | Files | Status |
|------|------|------|------|
| F1 | 4.1 structured JSONL trace layer (off by default) | `src/observability/{__init__,trace}.py` + workflow nodes + CLI + benchmark wiring + `tests/test_trace_observability.py` (12 cases) | ✅ |
| F2 | 3.4 cost-aware routing + cost alert | `src/api/api_manager.py` (COST_AWARE strategy + expensive provider WARNING) + `config.py` (LLMConfig.cost_weight) + `tests/test_cost_aware_routing.py` (10 cases) | ✅ |
| F3 | 3.1 multi-candidate patches and verification (off by default; falls back to single patch with no candidate) | `src/tools/multi_candidate.py` + workflow `_patch_applier_node` wiring + `tests/test_multi_candidate.py` (19 cases) | ✅ |
| F4 | 2.3 synthetic dataset RAG on by default + `--no-rag` | `reproduce.sh` (synthetic/examples default `--enable-rag`) + `run_benchmark.py` (`--no-rag` argument) | ✅ |
| F5 | 1.5 CLI parallel/json boundary test backfill + doc alignment | `tests/test_cli_app.py` (`TestRunParallelJsonBoundaries` 6 cases) + `.env.example` / CHANGELOG / README / `QUICKSTART` sync | ✅ |

### Full Verification Results

| Check | Command | Result |
|--------|------|------|
| Ruff Lint | `ruff check .` | ✅ All checks passed |
| Ruff format | `ruff format --check .` | ✅ 130 files already formatted |
| Full suite | `python -m pytest tests/` | ✅ **1085 passed** / 0 failed |
| Coverage | `--cov=src` | ✅ TOTAL 3813 / 348 miss = 91% |
| End-to-end smoke | multi-candidate generate→select + trace persistence | ✅ bad candidate statically filtered out, good candidate selected, JSONL event sequence correct |
| Packaging | `find_packages()` | ✅ both `src.observability` / `src.tools` collected |

### Design Decisions (off-by-default switches)

- **3.1 / 4.1 both off by default** (`ENABLE_MULTI_CANDIDATE_PATCH=false` / `AITESTER_TRACE_DIR` unset), keeping the historical experiment baseline unchanged; enabling is an explicit act, with no implicit behavior change.
- **3.1 automatically falls back to the single patch when no valid candidate exists**: the multi-candidate strategy is "only more, never less", guaranteeing it is never worse than the original path.
- **3.4 cost fields go through `.env.local`** (`LLM_N_COST_WEIGHT`, gitignored, not in the repo); unconfigured default is the 1.0 baseline; to persist, a cost_weight field can be added to `llm_configs.json` (this batch uses the env-var baseline first to avoid changing the JSON structure).

### Phase 6: Upload to GitHub

This batch's 7 atomic commits (6 feature/test + 1 documentation batch) were pushed to
`origin/main` via the proxy `http://127.0.0.1:7891` (when 443 direct is unreachable, http.proxy is configured per historical experience). After the push,
`git filter-repo` was run to rewrite history and remove all paper/privacy-related paths (paper.md, docs/paper/,
TASK_SUMMARY.md, .agent-teams/, SUBMISSION_*, etc.), then a `--force` push of the clean history to GitHub.

### Phase 7: Follow-up Suggestions

1. **3.2 cross-file repair** and **3.3 test case quality mining**: not implemented in this batch (large change scope, involving patch_applier cross-file dependency analysis + test self-verification filtering); recommended as standalone projects with design docs.
2. **4.2 Docker actual enablement**: still the `use_docker=False` reservation (historical D-06 decision); wiring it up requires confirming a Docker daemon in the experimental environment.
3. Before pushing, check the number of commits ahead of `main` and push all of them together (including the 09-13 documentation batch and the system feature enhancement batch).

---

## Appendix: 2026-09-13 Documentation Sync + Privacy Cleanup + GitHub Push Round

### Execution Scope

1. **Full-project documentation sync** (`docs: 全项目文档同步...`):
    - README / QUICKSTART / OPTIMIZATION_REPORT added 3.1/3.4/4.1/2.3/1.5 batch
      new module notes (multi-candidate patches, cost-aware routing, structured tracing, RAG on by default, CLI boundaries);
      test baseline 1038→1085; QUICKSTART added a "7. Optional Advanced Switches" section.
    - Removed paper/manuscript wording: the README "Paper & Documentation" section removed the `paper.md` link and abstract;
      `docs/algorithm_design.md` "for paper writing" changed to "for technical review";
      `docs/failure_analysis.md` and the README experiment data section gained "historical data snapshot" labels.
    - Locally removed `paper.md` and `.private/` (paper source LaTeX/outline/experiment reports; all .gitignore-excluded, never in the git tree).
2. **Privacy and paper content full sweep** (sensitive-info scan script):
    - No tracked md/py/json/sh files contain real keys on disk (all hits are synthetic placeholders in test fixtures);
    - Real keys exist only in the gitignored local `.env` / `src/.env.local` (rotation recommended; the suggestion is retained across rounds).
3. **Git history cleanup** (`git filter-repo`):
    - Removed all historical versions of `paper.md` / `docs/paper/` (8 LaTeX chapters + abstract) / `TASK_SUMMARY.md` /
      `FINAL_PAPER_STATUS.md` / `PAPER_IMPROVEMENT_PLAN.md` /
      `algorithm_paper.md` / `docs/paper_outline.md` / `.agent-teams/` /
      `SUBMISSION_CHECKLIST.md` / `SUBMISSION_PACKAGE.md` /
      `quality_review_report_20260817.md`;
    - 263 commits rewritten, all SHAs changed (old `5ca09a7` → new `f6ac74d`),
      pushed to `origin/main` with `--force`.

### Verification

| Check | Result |
|--------|------|
| Full suite | ✅ 1085 passed / 0 failed (final regression before the push) |
| Remote matches local | ✅ `git ls-remote origin main` = `f6ac74d` |
| No paper/privacy residual in remote history | ✅ `git log --all -- paper.md docs/paper TASK_SUMMARY.md` empty |
| Working tree | ✅ clean |

---

## Appendix: 2026-09-14 Status Refinement + Configurable Threshold + Boundary Test Backfill + Source Export + Redaction Audit Round

### Execution Scope

This batch digested 7 pure code items from the 2026-09-14 improvement checklist (1.1 / 1.4 / 1.5 / 2.1 / 2.3 / 3.2 / 4.1):

| Item | Content | Changed Files | Status |
|----|------|----------|------|
| 1.1 | Error classification adds 2 status-refined categories (PATCH_VALIDATION_FAILED / RAG_RETRIEVAL_EMPTY); `refine_failure_category()` verdict at task wrap-up (patch rejected takes priority over RAG empty) | `src/agents/error_classifier.py` + `src/reports/generator.py` + `experiments/run_benchmark.py` + `src/cli/app.py` + tests | ✅ |
| 3.2 | Cost alert threshold configurable (`APIManagerConfig.cost_alert_threshold`, default 2.0); alert message prints the configured value | `src/api/api_manager.py` + tests | ✅ |
| 1.5 | 3 circuit breaker cooldown boundary tests (expiry return / multi-node simultaneous cooldown degradation / fast failure during cooldown) | `tests/test_api_manager.py` (`TestCircuitCooldownBoundaries` 3 cases) | ✅ |
| 1.4 | CLI parameter exception paths and concurrency behavior test backfill (--timeout end-to-end / invalid dataset degradation / concurrent single-task timeout does not block the batch / glob boundary semantics) | `tests/test_cli_app.py` (3 groups, 8 cases) | ✅ |
| 2.1 | SWE-bench source export automation (`scripts/export_swe_bench_source.py`: patch extracts the first non-test target file + `git show` read-only export + enrichment JSONL output + `--instance-ids`/`--dry-run`); `SWEBenchDataset.tasks_missing_source()` + check-dataset outputs the missing instance_id list | `scripts/export_swe_bench_source.py` (new) + `src/datasets/dataset_loader.py` + `src/cli/app.py` + tests | ✅ |
| 2.3 | RAG metric auto-summary (analyze_results.py adds the by-retrieval-type breakdown + RAG hit × failure-category cross table) | `experiments/analyze_results.py` + tests | ✅ |
| 4.1 | Complete redaction audit (`docs/redaction_audit.md`): fixed 2 real blind spots (APIManager 7 log points in-place `_redact()` + `get_status()` base_url exit redaction); LLM file cache recorded as a known acceptable risk (redaction is mutually exclusive with exact cache hits) | `src/api/api_manager.py` + `docs/redaction_audit.md` (new) + tests | ✅ |

### Full Verification Results

| Check | Result |
|--------|------|
| Full suite | ✅ **1158 passed** / 0 failed (2 warnings are scipy degenerate-data precision notes, not a code issue) |
| New cases | +41 (error classification 9 + cost routing 4 + APIManager 5 + CLI 8 + source export 11 + dataset 2 + experiment scripts 4 + redaction regression 2; the 1.5/1.4 stack on top of the existing suites, and the net increment is judged by the full-suite count) |

### Design Decisions

- **1.1 status-refined categories do not use text regex**: `classify()` keeps the 10-category pure-text classification unchanged; `PATCH_VALIDATION_FAILED` / `RAG_RETRIEVAL_EMPTY` are flow-status categories, determined by `refine_failure_category()` at task wrap-up via `repair_history` / `rag_stats` signals, effective only for failed tasks (successful tasks returned as-is); the benchmark and CLI exits share a consistent baseline.
- **Priority: patch rejected > RAG retrieval empty**: the former is the more specific root cause of "repair not effective"; RAG empty is "retrieval provided no help". When both hold, classify as patch_validation_failed.
- **3.2 default unchanged**: `cost_alert_threshold` defaults to the module constant 2.0, not changing existing alert behavior; tuning is an explicit configuration act.
- **4.1 LLM cache not redacted**: the `base_agent` file cache relies on exact `prompt == user_message` match hits; redacted on-disk values would break read-side matching (the cache would never hit). The cache directory (actually `src/cache/` in code, overridable via `AITESTER_LLM_CACHE_DIR`; already in `.gitignore`, not in git, not uploaded) is recorded as a known acceptable risk in the local trusted domain; a future optional "redaction + dual-field" approach could be a standalone project. (Note: this appendix and redaction_audit previously misrecorded it as `~/.cache/aitester/llm_cache/`; the 2026-09-14 F batch corrected it per the code.)

---

## Appendix: 2026-09-14 Batch ② Wrap-up Round (Documentation Data Alignment)

### Execution Scope

Documentation wrap-up for batch ② (7 pure code items); the user confirmed "execute all + push main":

| Item | Content | Changed Files | Status |
|----|------|----------|------|
| O-01 | README test coverage main table 9 rows' case counts synced with the measured `def test_` counts (test_api_manager 80→77, test_cli_app 30→27, test_cost_aware_routing 14→13, test_dataset_validation 20→22, test_experiments_scripts 23→19, test_swe_bench_source_export 11→13, test_core_modules 29→19, test_executor_sandbox 14→7, test_dataset_loader_extended 73→59) | `README.md` | ✅ |
| O-02 | README "currently 1111 cases" → 1158 (consistent with the status table/full-suite measurement) | `README.md` | ✅ |
| O-03 | docs/api_reference.md error classification "ten categories" → "twelve categories": enumeration table adds the patch_validation_failed / rag_retrieval_empty rows (1.1 status refinement) + the priority note adds the refine_failure_category verdict baseline | `docs/api_reference.md` | ✅ |
| O-04 | docs/failure_analysis.md status note "expanded to 10 categories" → 12 (noting batch ② added the 2 status-refined categories) | `docs/failure_analysis.md` | ✅ |
| O-05 | QUICKSTART.md "advanced switches" section adds 3.2 cost alert threshold configurability (APIManagerConfig.cost_alert_threshold, default 2.0) | `QUICKSTART.md` | ✅ |
| O-06 | Added a "Documentation alignment (batch ② wrap-up)" subsection to the top Unreleased batch ② entry in the CHANGELOG | `CHANGELOG.md` | ✅ |

### Search Conclusions (dimensions with no optimization points)

- No eval/exec/os.system dangerous calls in the source (re-checked, consistent with historical rounds);
- No real key residual in tracked files (`git ls-files` shows only the .env.example / .env.local.template placeholder templates; .env.local / .env are gitignored; the real keys in the local .env should be rotated — the suggestion is retained across rounds);
- CI structure complete (matrix 3.12/3.14, lock check, pinned ruff 0.16.3, 5 pip-audit PYSEC exemptions, test failure diagnostic annotations); no drift;
- Full suite 1158 passed / 0 failed, ruff check all green, coverage TOTAL 91% (3911/354 miss; the src line growth is due to the modules added in batch ②).

### Implementation Record

| Commit | Content |
|------|------|
| `6a423fe` docs | O-01~O-05 documentation data alignment (main table 9 rows + case count + enumeration table + priority note + status note + QUICKSTART) |
| (this commit) docs(optimize) | O-06 CHANGELOG entry + OPTIMIZATION_PLAN/REPORT batch ② wrap-up section |

(Pure documentation changes, source untouched; minimum verification was ruff check + the affected module test subset (test_error_classifier 85 collected / test_cost_aware_routing 13) all green.)

---

## Appendix: 2026-09-14 Full-Project Documentation Sync Round (F Batch)

### Execution Scope

The user directive "update all docs to the latest and upload to GitHub"; on top of the O batch (data alignment), another **full-project** documentation-vs-current-code audit, 10 items in total (F-01~F-10):

| Item | Content | Changed Files | Status |
|----|------|----------|------|
| F-01 | README project structure tree filled in at 4 missing places (src/observability/, src/graph/token_usage.py, 3 in src/tools/, 4 scripts in experiments/) | `README.md` | ✅ |
| F-02 | redaction_audit item C LLM cache path correction: `~/.cache/aitester/llm_cache/` (HOME) → `src/cache/` (inside the repo + gitignored); the trust-level discussion aligned with the actual code | `docs/redaction_audit.md` + `optimization_report.md` (the same misrecord in the 4.1 decision item corrected together) | ✅ |
| F-03 | performance_guide's `rm -rf .chroma_cache/` points to a non-existent directory (chromadb 1.x persists to rag_data/) | `docs/performance_guide.md` | ✅ |
| F-04 | 2 residual "for the paper discussion section" wordings (missed in the 09-13 privacy cleanup round): README structure tree + analyze_failures.py docstring; the latter's `--output` default `docs/paper/` → `experiments/results/` (the directory no longer exists; no test references this script) | `README.md` + `experiments/analyze_failures.py` | ✅ |
| F-05 | README 5.3 cost-aware routing adds the 3.2 threshold configurability baseline (default 2.0 + tuning direction + 0.0=no-information fallback to 1.0) | `README.md` | ✅ |
| F-06 | README adds a 5.7 SWE-bench source export automation subsection (script usage + check-dataset linkage) | `README.md` | ✅ |
| F-07 | api_reference version history adds the Unreleased (batch ②) row (the 0.9.13 row kept as a historical record) | `docs/api_reference.md` | ✅ |
| F-08 | .env.example section 3.4 comment adds 3.2 threshold configurability + LLM_N_COST_WEIGHT numeric baseline aligned to config.py (0.1~1000; unconfigured default 0.0, not 1.0) | `.env.example` | ✅ |
| F-09 | performance_guide (2026-08-16) / usage_examples (2026-09-11) timestamps synced to 2026-09-14 | both files | ✅ |
| F-10 | usage_examples referenced lowercase `contributing.md` (does not exist under docs/) → `../CONTRIBUTING.md` | `docs/usage_examples.md` | ✅ |

### Search Conclusions (dimensions with no optimization points)

- `.env.example` / `config.local.example` placeholders contain no real keys (template baseline cross-checked against config.py's actual parsing);
- Each QUICKSTART step cross-checked against the actual CLI parameters, no drift; docs/algorithm_design.md is algorithm narrative (the "for technical review" baseline), no data drift against the code;
- failure_analysis.md is a historical snapshot and its 09-14 status note already says "take analyze_results.py output as authoritative"; the original text is kept by design;
- The full-project `grep` drift re-check (cache paths / chroma_cache / ten categories / paper wording / 1111 cases / lowercase references) all cleared to zero.

### Full Verification Results

| Check | Result |
|--------|------|
| Full suite | ✅ **1158 passed / 0 failed** (2 warnings are scipy degenerate-data precision notes, not a code issue) |
| Lint / format | ✅ `ruff check` All checks passed + `ruff format --check` 134 files already formatted |
| Sensitive info | ✅ No real keys in tracked files; .env / .env.local / src/cache/ / dist / build all gitignored |

### Design Decisions

- **F-02 cache path**: the redaction_audit item C "known acceptable risk" conclusion is unchanged (local trusted domain; redaction and cache hits are mutually exclusive); only the path and trust-level discussion are aligned with the actual code (`src/cache/` inside the repo and gitignored);
- **F-04 default output path**: the `analyze_failures.py --output` default changed to `experiments/results/failure_analysis.md` (no test references this script; zero regression surface);
- **Phase 6 push**: the user directive "upload to GitHub"; following the historical-rounds main-direct-push (no feature branch, no PR).

---

## Appendix: 2026-09-14 Improvement Checklist Batch (G-01~G-04 + 3.4 + 3.5)

### Execution Scope

The user provided a 5-category 22-item improvement checklist (1.1~1.3 / 2.1~2.3 / 3.1~3.5 / 4.1~4.4 / 5.1~5.3); after checking the repository's actual code state item by item, **most items were confirmed to have been implemented in earlier batches**; the real gaps concentrate in 4 (G-01~G-04), plus 2 research/experimental items that are not pure code changes (3.4 assertion augmentation and 3.5 cross-file repair were landed together as switchable capabilities, off by default to keep the historical baseline).

| Item | Goal | Changed Files | Status |
|----|------|----------|------|
| G-01 | 1.2 test smell detection (Assertion Roulette / Magic Number / assertion weakening / trivial tests) | `experiments/analyze_results.py` (`_test_smell_detection` pure function + Markdown rendering) + `tests/test_experiments_scripts.py` +3 cases | ✅ commit ffb77cf |
| G-02 | 1.3 repair convergence curve (cumulative pass rate per iteration round + repair cost) | `experiments/analyze_results.py` (`_repair_convergence_curve` pure function) + tests | ✅ commit ffb77cf (same batch as G-01) |
| G-03 | 4.4 dependency cache monitoring (hit-rate statistics / cleanup command / multi-version list) | `src/tools/dependency.py` (`get_venv_cache_stats` / `list_venv_cache` / `clear_venv_cache` + `create_venv` records hit/create) + `tests/test_dependency.py` +8 cases | ✅ commit 6b0e64d |
| G-04 | 5.3 failure root-cause classification + case knowledge base | `experiments/analyze_failures.py` (`root_cause_classification` three root causes + `failure_knowledge_base` structured JSON) + `tests/test_analyze_failures.py` (new, 13 cases) | ✅ commit 247fc91 |
| 3.4 | Assertion augmentation strategy (AST-extract existing assert into prompt, off by default) | `src/agents/generator.py` (`_extract_existing_assertions`) + `config.py` (`ASSERTION_AUGMENT_ENABLE`) + `tests/test_generator.py` +6 cases | ✅ commit ed4c237 |
| 3.5 | Cross-file repair (coordinator-proposer architecture, off by default) | `src/tools/cross_file.py` (new; AST dependency analysis + multi-file patch application + single-file fallback) + `src/graph/workflow.py` cross_file_analyzer node + `tests/test_cross_file.py` (new, 27 cases) + design doc `docs/design/cross_file_repair.md` | ✅ commit 670f368 |

### Full Verification Results

| Check | Result |
|--------|------|
| Full suite | ✅ **1225 passed / 0 failed** (net +62 from the 1.1/1.2 first-batch baseline 1163) |
| Lint / format | ✅ `ruff check` / `ruff format --check` all green |
| Doc sync | ✅ 5-file batch entries in CHANGELOG / OPTIMIZATION_PLAN / README / QUICKSTART / api_reference (commits 15cffaa / 1205647) |

### Design Decisions

- **3.4 / 3.5 off by default** (`ASSERTION_AUGMENT_ENABLE` / `CROSS_FILE_ENABLE` both default false), keeping the historical experiment baseline unchanged; enabling is an explicit act, with no implicit behavior change.
- **G-01~G-04 are analysis-layer / tool-layer pure functions only**, zero runtime path changes; when old JSONs lack fields they degrade automatically (skip the section / available=False), no crash.
- **G-03 pitfall fix**: `threading.Lock` is not reentrant; `_record_venv_cache_event` and `_persist_cache_stats` nested self-locking would hang the process — changed to a single lock boundary.

---

## Appendix: 2026-09-14 4.2 Half-Open Probe Batch

### Optimization Points

After the 4.1 circuit breaker cooldown expires, the node directly returns to full routing, so a dead provider is repeatedly hammered by full traffic. This completes the classic circuit breaker three states (closed / open / half-open): after the cooldown expires, the node first enters a "half-open" window carrying only one probe request; on a successful probe the circuit closes and full routing resumes; on failure the circuit reopens with a half cooldown period (`min(cooldown/2, half_open_probe_penalty_cap_seconds)`, default cap 30s), preventing a completely down provider's cooldown from shrinking without bound.

### Changes

| Change | File | Description |
|------|------|------|
| Half-open window verdict + probe consumption | `src/api/api_manager.py` | `APIHealth.in_circuit_half_open` (cooldown expired, probe not completed) + `_probe_circuit_half_open()` (on success close / on failure reopen the half cooldown) |
| Routing candidates include half-open nodes | `src/api/api_manager.py` | `get_healthy_nodes()` / `_build_node_list()` include half-open window nodes as candidates (only when `enable_half_open_probe=True`) |
| Unified probe result consumption | `src/api/api_manager.py` | `call()` and `check_health()`'s success / each exception branch (RateLimit / APIError / generic exception) uniformly call `_probe_circuit_half_open` |
| Three-state observability | `src/api/api_manager.py` | `get_status()` adds a `circuit_state` field (closed / open / half_open) |
| Switch + penalty cap configurable | `src/api/api_manager.py` | `APIManagerConfig.enable_half_open_probe` (default True; set False to fall back to 4.1 pass-through) + `half_open_probe_penalty_cap_seconds` (default 30.0) |
| Half-open probe tests | `tests/test_api_manager_extended.py` | New `TestHalfOpenProbe` 12 cases (window properties / success close / failure reopen / penalty cap / no-op boundaries / switch-off fallback / call and check_health dual-path consumption / get_status three states) |
| Format normalization | `docs/design/cross_file_repair.md` | The 3.5 design doc's python code block comment alignment triggered a ruff format gate drift; normalized uniformly (no logic change) |

### Before/After Test Comparison

| Metric | Before Batch | After Batch |
|------|--------|--------|
| Full suite | 1225 passed / 0 failed | **1237 passed / 0 failed** (net +12, i.e. the 12 TestHalfOpenProbe cases) |
| Lint / format | all green | all green (`ruff check` / `ruff format --check` 138 files) |

### Commit Record

| commit | type | description |
|--------|------|------|
| b0b6352 | style(docs) | ruff format normalization of the python code block drift in cross_file_repair.md |
| b69d811 | feat(api) | 4.2 circuit breaker half-open probe (after the cooldown expires, probe first, then pass; on by default) |
| d41887d | docs(optimize) | 4.2 documentation sync (CHANGELOG / OPTIMIZATION_PLAN / README / QUICKSTART / api_reference) |

### Design Decisions

- **On by default (enable_half_open_probe=True)**: the half-open probe is a stability improvement and is on by default; comparison experiments can set it False to fall back to the 4.1 baseline without code changes.
- **Penalty formula `min(cooldown/2, cap=30s)`**: halving the cooldown makes a "completely dead" provider's cooldown shrink monotonically, but the cap prevents unbounded shrinking (avoiding infinite probing of a dead endpoint).
- **Zero runtime-path breakage**: only new fields / methods / config items; defaults are backward compatible; `get_healthy_nodes` behavior with the switch off is fully consistent with 4.1.

### Follow-up Suggestions

1. **Run a 4.2 comparison experiment**: with the same provider pool, run one benchmark round each with `enable_half_open_probe=True/False`, and use `experiments/analyze_results.py` to compare the fault-recovery round and token waste — verifying the actual gain of the half-open probe (the "comparison experiment not run" note in the OPTIMIZATION_PLAN 4.2 row).
2. **Executor sandbox deep audit (T-04 historical carry-over)**: add the design doc + audit matrix as a standalone project.
3. **CLI module coverage**: `cli/app.py` is still the lowest across the project (~64%); item 5.1 suggests backfilling 10~15 boundary cases next round.

---

## Appendix: 2026-09-15 Full-Project Convergence Round (config centralization + dead code cleanup + off-by-default feature fixes)

> Baseline: 1247 passed / 0 failed / 91% coverage / ruff all green / clean working tree.
> This round ran three-way subagent audits in parallel (direct config/env reads, dead code/redundancy/defects, low-coverage module test backfill points) + manual review;
> landed 11 file changes + 23 new cases, advancing to **1270 passed / 0 failed / 92% coverage**.

### Defect Fixes (3 places, including 2 real bugs)
- 🔴 The hardcoded standard-library list in `executor.py` wrongly listed the third-party `diskcache` and was missing `asyncio`/`importlib`; the 80-item
  frozenset was removed and `dependency.is_standard_library` is reused (the authoritative `sys.stdlib_module_names` list).
- 🔴 The `_patch_applier_node` cross-file fallback path treated the "file-mapping dict" returned by `cross_file_fallback_single_file` as a "code string" assigned to `new_code`; `len(dict)` is always 1 → the fallback patch was forever stuck at the "too short" safety check and could never be written to disk;
  triggered by this round's test backfill; fixed to take the entry_module code from the mapping.
- `_set_thread_api` dropped `api["model"]`; with multi-model rotation the model always fell back to the first config.

### Config Centralization Convergence
- Removed 3 dead constants with no consumers from config.py (CROSS_FILE_ENABLE/CROSS_FILE_MAX_MODULES/ASSERTION_AUGMENT_ENABLE).
- `SWE_BENCH_ENRICHMENT` converged into config (new "dataset configuration" subsection) + entry added to .env.example.
- `MULTI_CANDIDATE_EXEC_VALIDATE` converged into `multi_candidate_exec_validate()`.

### Dead Code Cleanup (4 places) + DRY/Concurrency
- Removed EXECUTOR_SYSTEM_PROMPT / safe_apply_multi_function_patch / _call_llm_with_fallback (+_is_zai_url) /
  the benchmark decorator / cross_file.topo_key.
- RAG retriever extracted a single `_upsert` write point + serialized with threading.Lock; `refine_failure_category` wiring converged into
  `refine_final_error_category`; the cross_file docstring now truthfully describes the "current lexicographic order".

### Coverage Improvement
- `graph/nodes.py` 76%→95%, `config/config_manager.py` 87%→95%, total coverage 91%→92%.
- 23 new cases: off-by-default feature branches (cross_file/multi_candidate), cross-file fallback regression, empty-field validation, write-disk exceptions, env switches, etc.

### Version Convergence
- Version 0.9.11 → 0.9.14; CHANGELOG's 14 Unreleased entries mapped to 0.9.12/0.9.13/0.9.14 by date;
  the docs/api_reference version table synced; the README test count/coverage synced.

---

## Appendix: 2026-09-18 ~ 09-19 Code-Quality & Reliability Round (0.1 → 0.2)

> Baseline (0.1 release, 2026-09-18): full suite 1459 passed / 0 failed / 96% coverage / Ruff all green / clean working tree.
> This round is a pure code-quality pass (no new features), delivered in two atomic commits:
> `9f83197` (structural optimization) + `d5f21f6` (full optimization round 2).
> Post-round state: **1460 passed / 0 failed / 96% coverage / Ruff all green** (+1 regression test case net).
> The complete static-analysis report is at `docs/code_analysis_report.md`
> (30 findings + a "worth doing / not recommended" list + an implementation-status section).

### Commit 1: `9f83197` structural optimization round

| Change | File | Notes |
|------|------|------|
| Lazy-import elimination | `src/agents/base_agent.py` | The in-function lazy imports of `_find_balanced_json` and `extract_focused_code` moved to module top level (neither module has a circular dependency), removing per-call import-mechanism overhead and alias noise |
| Experiment ranking-binding fix | `src/experiments/analysis.py` | `_rank_by_metric` now sorts (name, value) tuples, eliminating the structural risk of position-based zip mis-pairing |
| Ranking-binding regression test | `tests/test_experiments_analysis.py` | New out-of-order-insertion case (full suite 1459→1460) |
| Database name whitelist | `init_db.py` | `MYSQL_DATABASE` is validated against `[A-Za-z0-9_]+` before being interpolated into `CREATE DATABASE`, closing an environment-variable multi-statement SQL injection vector; import ordering normalized |

### Commit 2: `d5f21f6` full optimization round 2 (13 files, +479/-97)

#### Refactors
- **RAG guarded helper extraction** (`graph/rag.py` adds `rag_guarded`): unifies the 4 structurally
  identical "ENABLE_RAG precondition + retriever singleton fetch + try/except degradation" blocks in
  `graph/nodes.py` (generator retrieval / executor ingestion / debugger retrieval / debugger ingestion).
  **Dependency-injection design** (`enabled` / `module_available` / `retriever_cls` / `get_retriever`
  passed as parameters rather than read from module globals), so the historical patch paths
  (`src.graph.nodes.ENABLE_RAG` / `get_rag_retriever`, used by 8 test cases) stay valid and test
  mock behavior does not drift. Future RAG degradation-policy changes (failure counting, circuit
  breakers, etc.) only touch `rag_guarded` in one place.
- **Multi-function patch sort performance** (`tools/patch_applier.py`): the `apply_multi_function_patch`
  sort key changed from "each patch splits the code lines itself" (O(n·m)) to "pre-split lines reused"
  (`_find_function_start_line_in_lines`, O(n+m)); large multi-file patch scenarios benefit directly.
- **Redaction dual-implementation convergence** (`agents/llm_client.py` + `api/api_manager.py`): the
  near-duplicate `_redact` / `_redact_log_text` implementations converge on the same delegation to
  `logging_utils.mask_sensitive_info`, with a comment marking the single implementation entry to prevent drift.

#### Fixes
- **Atomic-write exception narrowing** (`graph/nodes.py`): temp-file cleanup changed from
  `except BaseException` to `except Exception` (PEP 8: KeyboardInterrupt/SystemExit must not enter the
  cleanup path; stray temp files are reaped at process exit).

#### API manager performance & configurability
- `get_status` now reuses one `get_healthy_nodes()` call instead of two full node-pool traversals.
- The hardcoded 0.1s inter-node interval in batch health checks is exposed as
  `APIManagerConfig.batch_health_check_interval` (default 0.1s keeps historical behavior;
  100+ node pools can set 0 or raise it alongside a concurrent probe scheme).

#### Test cleanup
- Fixed 1 tautological assertion (`tests/test_weak_coverage_modules.py` `assert ... or True` — the case
  always passed and was effectively a no-op).
- Ruff auto + manual cleanup of 24 pre-existing test-suite warnings (unused variables / unused imports /
  implicit Optional / bare `open` / redundant monkeypatch aliases, etc.).

### Verification

| Metric | Before round | After round |
|------|--------|--------|
| Full suite | 1459 passed / 0 failed | **1460 passed / 0 failed** (+1, the ranking-binding regression case) |
| Ruff | all green | all green (`ruff check src/ tests/`; 24 pre-existing tests/ warnings cleaned as a side effect) |
| Coverage | 96% | 96% (no new feature paths this round) |
| Performance baseline | `_auto_fix_imports_complex` 2.64ms/op | no regression (re-ran `scripts/performance_benchmark.py` to confirm) |

### Design decisions

- **`rag_guarded` uses dependency injection rather than reading module globals internally**: tests mock
  behavior via `@patch("src.graph.nodes.ENABLE_RAG")` etc. If `rag_guarded` read `rag.py`'s module
  globals directly, those patch paths would break and all 8 affected test cases would fail. The
  dependency-injection design keeps the patch paths intact — the key constraint of this round's refactor.
- **The batch health-check interval was only made configurable, not concurrent**: the serial design is
  intentional ("avoid instant traffic that trips rate limits"); concurrency affects the rate-limiting
  policy (medium risk), so this round only does the low-risk "make the interval configurable" change and
  defers the concurrent scheme to the next round.
- **The redaction dual implementation keeps its module-level aliases rather than deleting them**:
  `tests/test_api_manager.py` imports `from src.api.api_manager import _redact` directly; deleting the
  alias would break the test path. What was converged is the "logic", not the "naming".

### Version convergence
- Version 0.1 → 0.2; CHANGELOG (zh + en) gains the full 0.2 entry; the README (zh + en) test count
  1459→1460 with the "Latest Optimization / Recent Changes" rows synced to this round;
  `docs/code_analysis_report.md` gains an "Implementation Status" section marking 8 items landed,
  4 items still "not recommended", and 2 items deferred to a future round.
