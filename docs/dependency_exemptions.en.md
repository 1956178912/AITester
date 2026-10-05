> Last updated: 2026-09-28 (registry established with the frontier-recommendation batch (chromadb PYSEC exemptions))

# Dependency Exemption Registry

> This file records the explicit exemptions for known vulnerabilities in the
> `pip-audit` security scan: why each exemption exists, which vulnerability
> IDs are exempted, and the re-review trigger conditions and deadlines.
> It stays in sync with the CI `--ignore-vuln` exemption list and the locked
> versions in `requirements.lock`; any dependency change or new fixed release
> must update this table.
>
> **Maintenance convention** (see `CONTRIBUTING.md`, "Dependency change
> checklist"):
> - New exemptions must be registered in this table (dependency / version /
>   vulnerability ID / exemption reason / re-review trigger / re-review
>   deadline);
> - After an upstream fix release, promptly upgrade and remove the matching
>   CI `--ignore-vuln` exemption and this table's entry, following the
>   "re-review trigger" column;
> - Re-review this table quarterly; entries past their re-review deadline are
>   marked "exemption expired" in the CHANGELOG.

## Current Exemptions

| Dependency | Locked Version | Vulnerability ID | Exemption Reason | Re-review Trigger | Re-review Deadline | Notes |
|---|---|---|---|---|---|---|
| chromadb | 1.5.9 | PYSEC-2026-311 (two duplicate entries) + PYSEC-2026-3813 / 3814 / 3815 | No fixed release available on PyPI yet; chromadb 1.5.9 is an optional RAG embedding backend (transparently degrades when missing, not on the git runtime path) | chromadb upstream releases a fixed version (a new version whose advisory covers any of CVEs 3813/3814/3815); or the chromadb version in `requirements.lock` changes | Quarterly, or immediately upon a fix release | After upgrading, synchronously remove the matching `--ignore-vuln` lines in `ci.yml` + this table's entry |

## Closed Historical Exemptions

(none yet)

> Historical exemptions (e.g. the early CVE-4583x series) were closed after
> the chromadb version upgrade and the CI exemption IDs drifted to the PYSEC
> caliber; see the corresponding batch entries in `CHANGELOG.md`.
