> **Language**: [中文版](SECURITY.md) | English (this document)
>
> Last updated: 2026-10-06

# Security Policy

> W8 (landed 2026-10-05 review): this file previously did not exist (community
> health file gap). The full technical threat model lives in
> [docs/threat_model.md](docs/threat_model.md) (attack surfaces A1–A6 plus
> T7 CI supply chain / T8 compound sandbox failure / T9 DoS); this file only
> defines the **disclosure and response process**.

## Supported Versions

| Version | Support Status |
|---------|----------------|
| latest commit on `main` | ✅ security fixes |
| historical tags | ❌ please upgrade to `main` |

This project is research code (as positioned in MODEL_CARD.md); no LTS
security-maintenance window is provided.

## Reporting a Vulnerability

**Please do NOT report security vulnerabilities via public Issues.**

1. Prefer GitHub private security advisories
   (Security → Advisories → Report a vulnerability);
2. Or contact the repository owner (see CODEOWNERS) with `[security]` in the
   subject;
3. Please include: impact description, reproduction steps / PoC, affected
   files and version (commit sha).

We commit to acknowledging reports within 7 days; fix progress is shared in a
private channel, and public credit is given after the fix (unless the reporter
requests anonymity).

## Security Baseline (currently in place)

- **CI blocking gates**: gitleaks working-tree scan (blocking on push/PR, binary
  verified by SHA256), bandit (src/, with per-entry exemptions registered in
  pyproject `[tool.bandit]`), pip-audit (top-level + all transitive deps in the
  lock; exemptions must be registered in `docs/dependency_exemptions.md` and are
  cross-checked by CI);
- **Pre-commit line of defense**: `.git-hooks/check_secret_leak.sh` (secret-pattern
  scan over staged + untracked files);
- **Execution isolation**: LLM-generated code runs in a venv sandbox by default
  (`EXECUTOR_USE_VENV=true`); Docker / kernel-level sandbox (Seatbelt/bwrap) are
  opt-in, and fail closed (refuse to execute) on unsupported platforms;
- **Credential hygiene**: all three execution paths scrub LLM credentials
  (`credential_scrub.scrub_os_environ`), three-layer log redaction
  (Handler/Formatter/entry wiring), cache directories/files at 0700/0600.

## Known Open Items (honest disclosure)

1. **Legacy leaks in git history**: files deleted in history commits
   (2e5272a / c505f506) retain suspected real API keys; the full-history
   gitleaks scan therefore stays **non-blocking** (Sunday schedule). Remediation
   runbook:
   [docs/security/history_leak_remediation_runbook.md](docs/security/history_leak_remediation_runbook.md)
   — it will be switched to blocking after key rotation + history rewrite.
   **Until then, please do NOT publicly distribute forks/mirrors of this repository.**
2. **Four known vulnerabilities in chromadb 1.5.9**: no fixed version on PyPI;
   explicitly registered as exemptions (`docs/dependency_exemptions.md`,
   quarterly review). RAG is an optional dependency and degrades transparently
   when not installed.
