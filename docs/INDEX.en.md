# AITester Documentation Index

> Last updated: 2026-10-19 (round Y4: authoritative responses to the third round's eight open questions; rounds Y/Y2/Y3 fix-coverage audits — three reports plus the reusable audit tool — registered in the core-document table)
>
> This page is the **navigation entry** for all Markdown documents: shortest reading
> paths by role first, then the core-document list (one line per document). Every link
> on this page is statically validated by `scripts/gates/check_doc_links.py --strict`
> (zero network: file and anchor existence only, external URLs are never fetched).
> Add a row here when you add or rename a core document.
>
> Chinese version: [INDEX.md](INDEX.md)

## 1. Quick entry

| I want to... | Start here |
|---|---|
| Get the system running in 10 minutes | [QUICKSTART.en.md](../QUICKSTART.en.md) |
| Understand positioning and core claims | [README.en.md](../README.en.md) |
| Contribute code / run the gates | [CONTRIBUTING.en.md](../CONTRIBUTING.en.md) |
| Reproduce experiments / check numbers | [REPLICATION.md](../REPLICATION.md) (Chinese) → [BASELINE.yaml](../BASELINE.yaml) |
| Review validity and claim boundaries | [docs/VALIDITY.en.md](VALIDITY.en.md) → [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md) (Chinese) |
| Find EMSE submission material | [docs/study/OPTIMIZATION_2026-10-15.md](emse/OPTIMIZATION_2026-10-15.md) (Chinese; the submission checklist/skeleton are local artifacts, not committed) |

## 2. Reading paths by role

### 2.1 New contributor (about 30 minutes)

1. [README.en.md](../README.en.md): positioning, capability boundaries and quick-start commands.
2. [QUICKSTART.en.md](../QUICKSTART.en.md): zero-LLM smoke test, single-file test, batch benchmark and ablation entry points.
3. [CONTRIBUTING.en.md](../CONTRIBUTING.en.md): branch / commit / gate chain / single-source-of-truth conventions for baseline numbers.
4. [docs/troubleshooting.md](troubleshooting.md) (Chinese): triage table for common blockers (symptom -> root cause -> fix).
5. [docs/adr/README.md](adr/README.md) (Chinese): architecture decision index (why the system is built this way).
6. [docs/api_reference.en.md](api_reference.en.md): module and public-API reference.

### 2.2 Reviewer 15-minute path

1. [docs/VALIDITY.en.md](VALIDITY.en.md): construct / internal / external / statistical-conclusion validity threats and mitigations.
2. [docs/preregistration.en.md](preregistration.en.md): E1-E8 pre-registration (E5 exploratory; E6-E8 added later; decision criteria declared before data collection).
3. [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md) (Chinese): claim -> evidence -> scope reconciliation table, including contradicted claims.
4. [docs/MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md) (Chinese): forms, detection and repair methodology for measurement artifacts.
5. [BASELINE.yaml](../BASELINE.yaml): machine-readable single source of truth for all current numbers.
6. [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md) (Chinese): second independent systematic review with open items and dispositions.
7. [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md) (Chinese): third independent systematic review (14 core claims recomputed bit-for-bit; A-01..A-20 recommendations and same-day close-out status).
8. [docs/reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md](reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md) (Chinese): closure report for the 23 findings of the third-party independent review (Windows): P0 A08 + P1/P2 per-item matrix, M1–M9 rerun and residual risks; §5 appends the second-round residuals A07/A09/A10 (2026-10-19).
9. [docs/reviews/REVIEW_CLARIFICATIONS_2026-10-19.md](reviews/REVIEW_CLARIFICATIONS_2026-10-19.md) (Chinese): the **authoritative response entry** for §15's eight open questions of the third round (five closed, two awaiting a project decision, one not done with an explicit cost); each item gives artifact path + recompute command + capability boundary.

### 2.3 Reproducer

1. [REPLICATION.md](../REPLICATION.md) (Chinese): replication package layout, artifact inventory and restore steps.
2. [reproduce.sh](../reproduce.sh): main-batch reproduction entry point (consumes LLM quota; never trigger automatically).
3. [docs/usage_examples.en.md](usage_examples.en.md): single-file / batch / ablation / cost-budget usage examples.
4. [docs/performance_guide.en.md](performance_guide.en.md): performance parameters, budget calibers and tuning.
5. [docs/troubleshooting.md](troubleshooting.md) (Chinese): environment / dependency / Docker / RAG blockers.
6. [Three-seed main-batch statistical report](../experiments/results/main_batch/statistical_report_3seed_pooled.md) (Chinese): evidence source for the key statistical claims (experiment artifact, not a gated document).

### 2.4 Maintainer

1. [docs/PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) (Chinese): status and decision register (done / open / blocked).
2. [docs/adr/README.md](adr/README.md) (Chinese): ADR index (append one row per new architecture decision).
3. [CHANGELOG.en.md](../CHANGELOG.en.md): per-batch change log (historical snapshot; outside the link gate's scan surface).
4. [docs/HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md) (Chinese): human-adjudication protocol (sampling frame / scale / independent double review / conflict resolution).
5. `docs/study/SUBMISSION_CHECKLIST_2026-10-15.md` (Chinese): submission-material closure checklist (**local artifact, not committed**; recomputable content lives in [OPTIMIZATION_2026-10-15.md](emse/OPTIMIZATION_2026-10-15.md)).
6. [scripts/gates/](../scripts/gates/): gate-script directory (add new gates here and wire them into Makefile / CI).

## 3. Core documents

### 3.1 Positioning, validity and measurement integrity

| Document | One-line description |
|---|---|
| [docs/VALIDITY.en.md](VALIDITY.en.md) | Validity-threat model: construct / internal / external / statistical-conclusion threats with itemised mitigations. |
| [docs/EVALUATION_SCOPE.md](EVALUATION_SCOPE.md) (Chinese) | Claim -> evidence -> scope reconciliation table, including the contradicted-claims list (for editorial triage). |
| [docs/MEASUREMENT_INTEGRITY.md](MEASUREMENT_INTEGRITY.md) (Chinese) | Methodology for four measurement artifacts with a "caliber fork": forked caliber / detection / magnitude / fix / whether the conclusion flips. |
| [docs/preregistration.en.md](preregistration.en.md) | E1-E8 pre-registration (E5 exploratory, E6-E8 added later): decision criteria, sample sizes and stopping conditions declared before data collection. |
| [docs/DATA_CARD.en.md](DATA_CARD.en.md) | Dataset card: provenance, scale, licence, contamination view and applicability boundaries. |
| [MODEL_CARD.en.md](../MODEL_CARD.en.md) | Model card: model versions, fingerprint calibers, cost and known limitations. |

### 3.2 System design and API

| Document | One-line description |
|---|---|
| [docs/algorithm_design.en.md](algorithm_design.en.md) | System architecture and algorithm design overview (graph / nodes / repair loop / detection gates). |
| [docs/api_reference.en.md](api_reference.en.md) | Module and public-API reference (agents / tools / workflow / datasets / configuration). |
| [docs/adr/README.md](adr/README.md) (Chinese) | Architecture decision record index: number, status, one-line summary and related modules for every ADR. |
| [docs/design/](design/) | Design-document directory: pre-registrations, experiment designs, wiring designs and frozen proposals. |
| [docs/design/cross_file_repair.en.md](design/cross_file_repair.en.md) | Cross-file repair design (context construction and landing constraints for multi-file tasks). |
| [docs/design/repair_caliber_matrix.md](design/repair_caliber_matrix.md) (Chinese) | Repair-caliber matrix: repair rates under different decision calibers and the rationale for choosing one. |
| [docs/design/multilanguage_extension.md](design/multilanguage_extension.md) (Chinese) | Multilanguage-extension architecture reservation (language adapter layer and admission criteria). |
| [docs/design/docstring_anchor.md](design/docstring_anchor.md) (Chinese) | P1 independent docstring spec anchor: two-arm design, anchor-table caliber, pre-registration and three-arm verdict (`not_confirmed`). |
| [docs/design/misguided_effective_metric.md](design/misguided_effective_metric.md) (Chinese) | Misguided/effective per-test three-way metric (ISSTA'26 operationalization): class tree, denominators, execution caliber and known limits. |
| [docs/design/oracle_quality_metric.md](design/oracle_quality_metric.md) (Chinese) | Deterministic spec-oracle quality (A-05): four classes, injection fidelity, detection contribution and verdict-coupling limits. |
| [docs/design/e2e_probe_matrix.md](design/e2e_probe_matrix.md) (Chinese) | Full-feature end-to-end probe matrix: feature-checklist verification, zero-LLM default with opt-in real LLM, reporting and boundaries. |
| [docs/design/smt_witness_batch_plan.md](design/smt_witness_batch_plan.md) (Chinese) | Minimal enablement batch for the z3 SMT witness layer: design, decision rules and T-round execution record (mechanism layer pass; pre/post-fix calibers). |
| [docs/design/evaluation_integrity_checklist.md](design/evaluation_integrity_checklist.md) (Chinese) | Evaluation-integrity checklist v1 (P3): IC-1..IC-8 artifact-level static integrity checks plus an executable validator (`experiments/eval_integrity_check.py`); run after each batch / before citation / before cross-batch comparison. |
| [docs/design/cross_file_plan_wiring_prereg.md](design/cross_file_plan_wiring_prereg.md) (Chinese) | D3b cross-file graph-path wiring: downstream consumer localization, two-stage dual-switch plan and preregistration; **Step A implemented (dual switches default-off, OFF/OFF bit-for-bit identical to history)**, Step B / AB1 pending. |
| [docs/COST_MODEL.md](COST_MODEL.md) (bilingual pair) | Cost model: batch post-processing wall observability (StageTimer/percentiles/thresholds), budget caliber and batch guidance. |
| [docs/dependency_exemptions.en.md](dependency_exemptions.en.md) | Dependency-exemption registry: alternative for each exemption and its re-review deadline. |
| [docs/threat_model.en.md](threat_model.en.md) | Threat model: T1-T8 threats, attack surfaces and existing mitigations. |

### 3.3 Usage, operations and security

| Document | One-line description |
|---|---|
| [QUICKSTART.en.md](../QUICKSTART.en.md) | Quick start: install, configure, single-file test, batch benchmark and ablation commands. |
| [docs/usage_examples.en.md](usage_examples.en.md) | Usage examples: basic usage / batch benchmarking / configuration tuning / advanced features / FAQ. |
| [docs/performance_guide.en.md](performance_guide.en.md) | Performance guide: parameters, caching, budgets and tuning calibers. |
| [docs/troubleshooting.md](troubleshooting.md) (Chinese) | Troubleshooting manual: symptom -> root cause -> fix -> prevention. |
| [docs/integration/README.md](integration/README.md) (Chinese) | CI/CD integration guide: invoking the system from an external pipeline. |
| [docs/integration/vendored_quixbugs.md](integration/vendored_quixbugs.md) (Chinese) | QuixBugs external-dataset integration and restore (including nested-repo caveats). |
| [SECURITY.en.md](../SECURITY.en.md) | Security policy: vulnerability reporting, supported versions and response commitments. |
| [docs/security/history_leak_remediation_runbook.md](security/history_leak_remediation_runbook.md) (Chinese) | History-leak remediation runbook: key rotation and git-history rewrite steps. |
| [examples/README.md](../examples/README.md) (Chinese) | Example library: three runnable demos (cost budget / RAG A/B / semantic cache). |
| [examples/cost_budget_demo/README.md](../examples/cost_budget_demo/README.md) (Chinese) | Example: hard per-task cost budget cap (COST_BUDGET_ENABLE). |
| [examples/rag_ab_demo/README.md](../examples/rag_ab_demo/README.md) (Chinese) | Example: RAG A/B comparison experiment (ENABLE_RAG). |
| [examples/semantic_cache_demo/README.md](../examples/semantic_cache_demo/README.md) (Chinese) | Example: semantic-level LLM cache (SEMANTIC_CACHE_ENABLE). |

### 3.4 Evidence and statistical artifacts

| Document | One-line description |
|---|---|
| [BASELINE.yaml](../BASELINE.yaml) | Machine-readable single source of truth for the current baseline (tests / coverage / experiment numbers). |
| [Three-seed main-batch statistical report](../experiments/results/main_batch/statistical_report_3seed_pooled.md) (Chinese) | Statistical conclusions and confidence intervals for the three-seed main batch (n=261). |
| [Main-batch statistical report](../experiments/results/main_batch/statistical_report.md) (Chinese) | Canonical main-batch statistical report. |
| [MAST distribution report](../experiments/results/main_batch/mast_distribution_report.md) (Chinese) | Distribution of MAST-style failure classes and cross-arm comparison. |
| [Repair-ceiling attribution report](../experiments/results/main_batch/repair_ceiling_report.md) (Chinese) | Repair-ceiling attribution: funnel decomposition of patch output / plausible / correct. |
| [Target-quality replay report](../experiments/results/main_batch/target_quality_report.md) (Chinese) | Stock replay of target-code coverage / mutation score / spec compile rate. |
| [Corrected-caliber re-estimation report](../experiments/results/main_batch/corrected_report_v2.md) (Chinese) | false_fix / CPR / abstention-precision conclusions under the corrected caliber with de-confounding. |
| [R4 / QuixBugs batch README](../experiments/results/r4_batches/README.md) (Chinese) | Directory, calibers and landing notes for the R4 and QuixBugs stock batches. |
| [docs/failure_analysis.en.md](failure_analysis.en.md) | Failure-case statistics and typical failure-pattern analysis (by error type / bug pattern). |

### 3.5 Governance, reviews and history

| Document | One-line description |
|---|---|
| [docs/PROJECT_STATUS_REGISTER.md](PROJECT_STATUS_REGISTER.md) (Chinese) | Project status and decision register: done / open / blocked states with verification entry points. |
| [CHANGELOG.en.md](../CHANGELOG.en.md) | Per-batch change log (historical snapshot; current calibers live in BASELINE and the documents linked here). |
| [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-18.md) (Chinese) | Third independent systematic review (2026-10-18): 60+ frontier data points rebuilt from primary sources, 14 core claims recomputed bit-for-bit, A-01..A-20 recommendations and same-day close-out status. |
| [docs/reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md](reviews/THIRD_PARTY_REVIEW_2026-10-18_FIX_CLOSURE.md) (Chinese) | Closure report for the 23 findings of the third-party independent review (Windows, 2026-10-18): P0 A08 credential isolation + P1/P2 per-item matrix, M1–M9 rerun, gates and residual risks; §5 records the second-round residuals A07/A09/A10 (2026-10-19). |
| [docs/reviews/REVIEW_CLARIFICATIONS_2026-10-19.md](reviews/REVIEW_CLARIFICATIONS_2026-10-19.md) (Chinese) | Authoritative responses to the third round's eight open questions: five closed with artifact paths and recompute commands, two awaiting a project decision, one explicitly not done with its cost stated. |
| [docs/reviews/FIX_COVERAGE_AUDIT_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_2026-10-19.md) (Chinese) | Fix-coverage gap audit (round Y): 37 of 552 fix-added lines under `src/` were never executed by any test; five mutation-verified regression locks. |
| [docs/reviews/FIX_COVERAGE_AUDIT_ROUND2_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_ROUND2_2026-10-19.md) (Chinese) | Round-Y2 audit closure: A20 degradation chain, A06 production-entry wiring, A16 flaky evidence; first audit of `experiments/`. |
| [docs/reviews/FIX_COVERAGE_AUDIT_ROUND3_2026-10-19.md](reviews/FIX_COVERAGE_AUDIT_ROUND3_2026-10-19.md) (Chinese) | Round-Y3 wrap-up: two dead functions removed, three A03 provenance degradation paths, and the repo-wide uncovered-line map (637 lines / 83 files). |
| [docs/reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md](reviews/INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md) (Chinese) | Second independent systematic review: findings, evidence and disposition suggestions. |
| [CODE_OPTIMIZATION_2026-10-16.md](../CODE_OPTIMIZATION_2026-10-16.md) (Chinese) | Full code review and optimization report (round C). |
| [PHASE1_PRECHECK_2026-10-12.md](../PHASE1_PRECHECK_2026-10-12.md) (Chinese) | Phase-1 pre-check report for the improvement plan. |
| [SPEC_REPLACE_AB_REPORT_2026-10-12.md](../SPEC_REPLACE_AB_REPORT_2026-10-12.md) (Chinese) | spec_replace A/B phase-1 experiment report (QuixBugs, exploratory caliber). |
| [docs/HUMAN_ADJUDICATION_PROTOCOL.md](HUMAN_ADJUDICATION_PROTOCOL.md) (Chinese) | E7 human-adjudication protocol: sampling frame / five-choice scale / independent double review / conflict resolution. |
| [docs/COVERAGE_RATCHET_DEVIATION.md](COVERAGE_RATCHET_DEVIATION.md) (Chinese) | Coverage-ratchet deviation record: measured vs water line, attribution checks and disposition paths. |
| [docs/study/OPTIMIZATION_2026-10-15.md](emse/OPTIMIZATION_2026-10-15.md) (Chinese) | EMSE submission optimization record: reviewability-closure batch. |
| [REPLICATION.md](../REPLICATION.md) (Chinese) | Replication-package README: directories, artifacts and restore commands. |
| [CITATION.cff](../CITATION.cff) | Citation metadata (software citation format). |
| [LICENSE](../LICENSE) | Open-source licence. |

## 4. Link and bilingual maintenance

- **Link validation**: `python scripts/gates/check_doc_links.py --strict`
  (zero network, purely static: relative file links, line-anchor target existence,
  heading anchors; sample links inside fenced / inline code are ignored; external
  links are counted but never fetched).
- **Bilingual pairing**: `make docs-check` (`scripts/gates/check_bilingual_docs.py --strict`).
- **Exception registry**: [docs/link_check_allowlist.txt](link_check_allowlist.txt),
  one `<source>:<target>  # reason` per line; matches are reported as `[allow]`
  and do not block strict mode, while an exemption without a reason is an error.
- **Maintenance convention**: adding a core document -> add one row under the matching
  group in section 3 (with a one-line description); renaming / archiving a document ->
  search the repository for the old name and update links (never leave dead links).
