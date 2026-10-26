# Threat Model

> Last updated: 2026-10-26 · 中文: [threat_model.md](threat_model.md)

This file maps attack surfaces to guard modules and residual risk. Assumptions: the
operator is trusted; target source may come from public datasets; **LLM-generated
tests and patches are executed automatically in a sandbox** — the core risk source;
LLM APIs require outbound network; no human-subject data is involved.

## 1. Assets

| Asset | Impact if lost or abused |
|-------|--------------------------|
| LLM credentials and host environment variables | API quota theft, cost loss, upstream account restrictions |
| Host filesystem and processes | Generated code reads/writes out of bounds or exhausts resources |
| Evaluation data and readings | Contamination or tampering makes conclusions untrustworthy |
| CI credentials and release artifacts | A malicious PR runs arbitrary commands through the pipeline |
| API quota and disk | Concurrency × cache writes amplify cost and usage |

## 2. Adversaries

| # | Attack surface | Typical vector |
|---|----------------|----------------|
| A1 | Credential leak | Generated code reads all of `os.environ` and exfiltrates it |
| A2 | Supply chain (slopsquatting) | Auto-install pulls a lookalike malicious package |
| A3 | Prompt injection | Instructions embedded in the issue / target source induce key leaks or malicious patches |
| A4 | Sandbox escape | Outbound connections, host file reads, out-of-bounds writes |
| A5 | Data contamination | Training/eval overlap inflates readings |
| A6 | Abuse | Using the system to inject malicious outbound-network tests into a target repo |
| T7 | CI/CD supply chain | A malicious PR runs commands with CI credentials via workflows and scripts |
| T8 | Compound sandbox failure | Default configuration lacks a second filesystem defence layer |
| T9 | Resource exhaustion | Concurrency, caches and background health checks consume quota and disk |

## 3. Controls

| # | Guard | Status |
|---|-------|--------|
| A1 | `src/utils/credential_scrub.py` strips credentials on all three execution chains; sandbox directory isolation; all `.env*` gitignored | Implemented |
| A2 | `src/tools/dependency.py` package whitelist (`PIP_PACKAGE_WHITELIST_ENABLE` default on, unknown names rejected) + `requirements.lock` + `scripts/gates/check_lock_sync.py` | Implemented; whitelist needs manual maintenance |
| A3 | `src/agents/injection_guard.py` input-side scan + `src/agents/deterministic_guard.py` output-side scan + adversarial regression benchmark (recall ≥0.8 / false positives 0) | Implemented (heuristic) |
| A4 | Three tiers: venv sandbox (default) / Docker + egress allowlist / kernel sandbox (Seatbelt, Landlock+bwrap) | Partial: kernel sandbox off by default |
| A5 | `src/tools/contamination_check.py` three-dimensional check + `scripts/gates/check_swe_bench_pro_ready.py` data pre-gate | Implemented; semantic layer is bag-of-words |
| A6 | `src/graph/risk_approval.py` three-factor risk grading human loop + A2/A4 combination | Partial: `RISK_APPROVAL_ENABLE` off by default |
| T7 | All actions pinned to full 40-char SHAs, downloaded artifacts sha256-verified, no `pull_request_target` anywhere, `permissions: contents: read`; gitleaks work-tree scan blocking | Partial: full-history scan non-blocking |
| T8 | `src/agents/executor_runtime.py` five rlimits (CPU / AS / NPROC / FSIZE / NOFILE) + credential-whitelist environment + `AITESTER_PROFILE=safe` preset | Partial: default has only rlimits + credential scrubbing |
| T9 | token / USD / wall-clock budgets + `clean-venv-cache` (`--max-age-days` / `--max-size-mb`) + `API_HEALTH_CHECKER_ENABLE` can be turned off | Partial: no disk daemon, cost budgets default off |

**Fail-closed rule**: when the kernel sandbox is enabled but the platform lacks
sandbox-exec / bwrap, execution is refused (`build_sandbox_command` returns the
fail-closed marker); an unavailable Docker never silently falls back to host
execution; an empty package allowlist degrades to `--network=none`, not full egress.

## 4. Residual Risk

1. **Kernel sandbox off by default** (`KERNEL_SANDBOX_ENABLE=false`, P0-4): both the
   local and venv chains are wired; for production or untrusted targets use
   `AITESTER_PROFILE=safe` or set `KERNEL_SANDBOX_ENABLE=true` explicitly.
2. **Historical key residue** (T7): deleted files in `2e5272a` / `c505f506` retain a
   suspected real key; the full-history gitleaks scan stays non-blocking until
   rotation + history rewrite; see
   [security/history_leak_remediation_runbook.md](security/history_leak_remediation_runbook.md).
3. **Heuristic detection** (A3/A5): injection scanning can be bypassed by adversarial
   samples and the semantic contamination layer is a bag-of-words approximation; the
   benchmark guards against regression, not completeness.
4. **Maintenance gaps** (A2/T9): the whitelist has no auto-update; cost budgets are off
   by default and disk usage needs periodic operator-run `clean-venv-cache`.
5. **Accepted risks**: the LLM file cache is a trusted-domain local artifact (0600, not
   in git); the 5 known chromadb 1.5.9 vulnerabilities are registered as
   [dependency_exemptions.md](dependency_exemptions.md) with quarterly review.
