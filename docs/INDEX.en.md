# Documentation Index

> Last updated: 2026-10-27 · 中文版: [INDEX.md](INDEX.md)

This index is the entry point to all repository documentation: shortest reading paths by role,
plus the core document list. Historical batch records live under [history/](history/) and are
not maintained item by item.

## 1. Quick Entry

| You want to… | Start here |
|--------------|------------|
| Understand positioning and claim boundaries | [README.md](../README.md) · [MODEL_CARD.md](../MODEL_CARD.md) |
| Run it | [QUICKSTART.md](../QUICKSTART.md) |
| See architecture and modules | [algorithm_design.en.md](algorithm_design.en.md) · [api_reference.en.md](api_reference.en.md) |
| Reproduce experiments | [REPLICATION.md](../REPLICATION.md) |
| Contribute | [CONTRIBUTING.md](../CONTRIBUTING.md) |

### 1.1 Single Source of Numbers

Before quoting numbers, read: test counts, static checks, and benchmark readings are registered
in [BASELINE.yaml](../BASELINE.yaml); gate-chain and derived readings reconcile against
[PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) §1. **Do not copy drifting counts into
other documents.**

## 2. Reading Paths by Role

### 2.1 New Reader (about 30 minutes)

1. [README.md](../README.md) → 2. [QUICKSTART.md](../QUICKSTART.md) → 3.
   [usage_examples.en.md](usage_examples.en.md)

### 2.2 Reviewer 15-Minute Path

1. [reviews/README.md](reviews/README.md) → [VALIDITY.en.md](VALIDITY.en.md) → [preregistration.en.md](preregistration.en.md)

### 2.4 Batch pre-registration volumes (criteria frozen before data)

[preregistration_q04q07_ab_20261030.en.md](preregistration_q04q07_ab_20261030.en.md) ·
[preregistration_g8_fullstack_20261030.en.md](preregistration_g8_fullstack_20261030.en.md) ·
[preregistration_c8_bugsinpy_draft_20261029.md](preregistration_c8_bugsinpy_draft_20261029.md)

### 2.3 Maintainer

1. [api_reference.en.md](api_reference.en.md) → 2. [performance_guide.en.md](performance_guide.en.md) →
   3. [troubleshooting.en.md](troubleshooting.en.md)

## 3. Core Documents

### 3.1 Positioning and Validity

- [MODEL_CARD.md](../MODEL_CARD.md) · [DATA_CARD.en.md](DATA_CARD.en.md) ·
  [VALIDITY.en.md](VALIDITY.en.md) · [preregistration.en.md](preregistration.en.md) ·
  [EVALUATION_SCOPE.md](EVALUATION_SCOPE.md)
- [MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md) ·
  [COVERAGE_RATCHET_DEVIATION.md](COVERAGE_RATCHET_DEVIATION.md)

### 3.2 System and API

- [algorithm_design.en.md](algorithm_design.en.md) · [api_reference.en.md](api_reference.en.md) ·
  [threat_model.en.md](threat_model.en.md) · [SECURITY.md](../SECURITY.md)

### 3.3 Usage and Operations

- [QUICKSTART.md](../QUICKSTART.md) · [usage_examples.en.md](usage_examples.en.md) ·
  [performance_guide.en.md](performance_guide.en.md) · [COST_MODEL.en.md](COST_MODEL.en.md) ·
  [troubleshooting.en.md](troubleshooting.en.md) · [dependency_exemptions.en.md](dependency_exemptions.en.md)

### 3.4 Evidence and Artifacts

- [REPLICATION.md](../REPLICATION.md) · [failure_analysis.en.md](failure_analysis.en.md) ·
  [BASELINE.yaml](../BASELINE.yaml) · [CITATION.cff](../CITATION.cff)

### 3.5 Governance, Reviews and History

- [PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) ·
  [HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md)
- Review booklets entry: [reviews/README.md](reviews/README.md)
- Archive and topic directories: [adr/](adr/) · [design/](design/) · [study/](study/) · [security/](security/) ·
  [history/](history/)

## 4. Links and Bilingual Maintenance

- **Bilingual pairing**: core documents at the top level of `docs/` need an `.en.md` twin;
  `make docs-check` checks pairing completeness, date sync, and section skeleton.
- **Link integrity**: `make docs-check` also validates internal links; broken links block CI.
  Historical `docs/history/` is excluded and its internal links are not guaranteed to resolve.
- **Archive convention**: stale batches and historical narrative go to `docs/history/`; current
  documents keep only rules that still hold.
- To add a document: put it in the matching section above, add an English twin (or register an
  exemption with a reason), then run `make docs-check`.
