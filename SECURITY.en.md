# Security Policy

Last updated: 2026-10-26

This file defines the **vulnerability disclosure and response process** only; the technical
threat surface lives in [docs/threat_model.md](docs/threat_model.md) (A1–A6 plus T7 supply chain / T8 compound sandbox failure / T9 DoS).

## Supported Versions

| Version | Support Status |
|---------|----------------|
| latest commit on `main` | security fixes |
| historical tags | please upgrade to `main` |

This project is research code (see [MODEL_CARD.md](MODEL_CARD.md)); no LTS security window.

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities via public Issues.**

1. Prefer GitHub private security advisories (Security → Advisories → Report a vulnerability);
2. Or contact the repository owner (see `CODEOWNERS`) with `[security]` in the subject;
3. Include: impact, reproduction steps or PoC, affected files and version (commit sha).

We acknowledge reports within 7 days; fix progress is shared privately, and public credit is given after the fix (unless the reporter requests anonymity).

## Security Baseline

- **CI blocking gates**: gitleaks working-tree scan; bandit (`src/`, exemptions registered in
  `pyproject.toml`); pip-audit (top-level plus all transitive dependencies, exemptions in `docs/dependency_exemptions.md` cross-checked by CI).
- **Pre-commit line of defense**: `.git-hooks/check_secret_leak.sh` scans staged and untracked files for secret patterns.
- **Execution isolation**: LLM-generated code runs in a venv sandbox by default
  (`EXECUTOR_USE_VENV=true`); Docker / kernel-level sandboxes are opt-in and fail closed on unsupported platforms.
- **Credential hygiene**: all three execution paths scrub LLM credentials
  (`credential_scrub.scrub_os_environ`); logs are redacted at three layers; cache directories are 0700 and files 0600.
- **Keys live only in `.env.local`** (never committed); the repository holds no real keys.

## Known Open Items

1. **Legacy secrets in git history**: files deleted in commits `2e5272a` / `c505f506` retain
   suspected real API keys. The full-history gitleaks scan therefore stays **non-blocking**
   (Sunday schedule). Runbook:
   [docs/security/history_leak_remediation_runbook.md](docs/security/history_leak_remediation_runbook.md)
   — it becomes blocking after key rotation and history rewrite. **Until then, do not
   publicly distribute forks or mirrors of this repository.**
2. **Four known vulnerabilities in chromadb 1.5.9**: no fixed version on PyPI; registered as
   exemptions (`docs/dependency_exemptions.md`, quarterly review). RAG is optional and
   degrades transparently when not installed.
