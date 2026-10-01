# Verifiable Frontier Baseline 2024–2026
## Python Engineering Excellence & AI-System Compliance / Security

**Compiled:** 2026-09-30 · **Coverage window:** 2024-01 → 2026-09
**Method:** primary sources only (PEP index, PyPA specs, official docs, release notes, EUR-Lex, iso.org, ieee.org, nist.gov, istqb.org, spdx.org, slsa.dev, GitHub Docs, CISA/CVE). URLs were checked with a live fetch or observed in search results. Items that could not be substantiated are marked **UNVERIFIED** or omitted — a missing row beats a fabricated one.

> **Headline correction to the brief.** The brief's Part B premise ("Annex III high-risk applies 2 Aug 2026") is **out of date**. The AI Act was amended by **Regulation (EU) 2026/1744** (the *Digital Omnibus on AI*), adopted 8 July 2026, in force 27 July 2026. Annex III high-risk obligations moved to **2 December 2027**; Annex I to **2 August 2028**; Article 50(2) marking applies from **2 December 2026**. GPAI obligations (Arts 53–55) are **unchanged** and have applied since 2 August 2025. Any compliance plan built on the unamended dates is wrong.

---

## Table 1 — Tools & Standards

### 1. Packaging, environments, reproducible builds

| Tool/Standard | What it is | Version/Date | URL |
|---|---|---|---|
| PEP 517 | Build-backend API: `build_wheel`/`build_sdist` hooks; decouples frontend from backend | Final (2017), current | https://peps.python.org/pep-0517/ |
| PEP 518 | `[build-system]` table in `pyproject.toml`; `requires` + `build-backend` | Final (2016), current | https://peps.python.org/pep-0518/ |
| PEP 621 | Standard `[project]` metadata table — the single-source-of-truth config | Final (2020), current | https://peps.python.org/pep-0621/ |
| `pyproject.toml` spec (PyPA) | Normative spec for the file itself (incl. `[tool]` namespacing) | Living spec, 2026 | https://packaging.python.org/en/latest/specifications/pyproject-toml/ |
| src layout vs flat layout | PyPA's canonical guidance; src layout prevents accidental import of the CWD copy | PyPA discussion doc | https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/ |
| PEP 639 | License **expressions** (SPDX) + `license-files` in metadata; replaces free-text `License` | Final (2024) | https://peps.python.org/pep-0639/ |
| setuptools PEP 639 migration | Practical migration guide for `license`/`license-files` | setuptools docs, 2026 | https://setuptools.pypa.io/en/stable/userguide/license_migration.html |
| PEP 735 | `[dependency-groups]` — dev/test deps that are *not* extras and never ship | Final (2024) | https://peps.python.org/pep-0735/ |
| Dependency Groups spec | PyPA normative spec for `[dependency-groups]` incl. `include-group` | PyPA spec, 2026 | https://packaging.python.org/en/latest/specifications/dependency-groups/ |
| PEP 723 | Inline script metadata (`# /// script`) — single-file runnable scripts with deps | Final (2023) | https://peps.python.org/pep-0723/ |
| Inline script metadata spec | PyPA normative spec; consumed by `uv run` and `pipx` | PyPA spec, 2026 | https://packaging.python.org/en/latest/specifications/inline-script-metadata/ |
| PEP 751 / `pylock.toml` | **Standard lock file format** (`lock-version = "1.0"`); hashes, markers, `[[packages.wheels]]`, attestation identities | Final (2025) | https://peps.python.org/pep-0751/ |
| `pylock.toml` spec | PyPA normative spec; multi-use and single-use lock files, reproducible offline install semantics | PyPA spec, 2026 | https://packaging.python.org/en/latest/specifications/pylock-toml/ |
| uv (Astral) | Rust package/project manager: resolver, installer, Python manager, build backend | 0.12.21, 2026 | https://github.com/astral-sh/uv/releases |
| `uv lock` / `uv sync` | Universal cross-platform lock; `uv sync --frozen` for CI reproducibility | uv docs, 2026 | https://docs.astral.sh/uv/concepts/projects/sync/ |
| Hatchling | PEP 517 backend used by Hatch; minimal, plugin-driven | 1.28.x, 2026 | https://hatch.pypa.io/latest/ |
| PDM | PEP 621-native manager; `pdm.lock`; PEP 582 `__pypackages__` is **not** the default model | 2026 | https://pdm-project.org/ |
| Poetry | Dependency manager + backend; 2.0 added PEP 621 `[project]` support | 2.0.0 (2025) | https://github.com/python-poetry/poetry/releases/tag/2.0.0 |
| python-build-standalone | Relocatable standalone CPython builds (the basis for `uv python install`) | Stewardship **transferred to Astral** | https://github.com/astral-sh/python-build-standalone/discussions/396 |
| PEP 740 | Index-hosted **attestations**: Sigstore-signed provenance published alongside wheels on PyPI | Final (2024) | https://peps.python.org/pep-0740/ |
| PyPI digital attestations | Attestations live on PyPI since Nov 2024; `pypi-attestations` verifies them | Launched 2024-11-14 | https://blog.pypi.org/posts/2024-11-14-pypi-now-supports-digital-attestations/ |
| Index-hosted attestations spec | PyPA spec for the `attestations` API and provenance object | PyPA spec, 2026 | https://packaging.python.org/en/latest/specifications/index-hosted-attestations/ |
| Trusted Publishing (PyPI) | OIDC-based publishing — no long-lived API tokens in CI | PyPI docs, 2026 | https://docs.pypi.org/trusted-publishers/ |
| `--require-hashes` | pip mode enforcing a fully pinned, hash-verified install graph | pip docs, 2026 | https://pip.pypa.io/en/stable/cli/pip_install/#require-hashes |
| Wheel (binary dist) | Built distribution: pre-compiled, no build step at install; `py3-none-any` vs platform tags | PyPA spec, 2026 | https://packaging.python.org/en/latest/specifications/binary-distribution-format/ |
| sdist (source dist) | Source archive; needs a PEP 517 build at install — the fallback, and the only artifact for non-wheel platforms | PyPA spec, 2026 | https://packaging.python.org/en/latest/specifications/source-distribution-format/ |
| PEP 561 | `py.typed` marker + `Typing :: Typed` classifier — how type info reaches consumers | Final (2017), current | https://peps.python.org/pep-0561/ |

### 2. Linting, formatting, typing

| Tool/Standard | What it is | Version/Date | URL |
|---|---|---|---|
| Ruff | Rust linter + formatter; replaces flake8/isort/pyupgrade/bandit subsets in one pass | Rolling releases; see releases page | https://github.com/astral-sh/ruff/releases |
| Ruff rule sets | ~40 families: `E,W,F,I,N,UP,B,C4,SIM,S,ANN,D,PT,RUF,ASYNC,PERF,PL,TRY,ARG,COM,C90,DTZ,EM,FBT,ISC,NPY,PIE,PTH,PYI,Q,RET,SLOT,T10,T20,TC,TD,TID,YTT` | Ruff docs, 2026 | https://docs.astral.sh/ruff/rules/ |
| Ruff formatter | Black-compatible formatter (~99% parity); `ruff format` | Ruff docs, 2026 | https://docs.astral.sh/ruff/formatter/ |
| Ruff `S` rules | Port of flake8-bandit: `S101` assert, `S301` pickle, `S506` `yaml.load`, `S602/S603` `subprocess` shell | Ruff docs, 2026 | https://docs.astral.sh/ruff/rules/#flake8-bandit-s |
| mypy | Reference static type checker; `--strict` = the strictness bundle to standardise on | 2026 releases | https://mypy-lang.org/ |
| mypy `--strict` | Enables `--disallow-untyped-defs`, `--warn-unused-ignores`, `--no-implicit-optional` etc. | mypy docs, 2026 | https://mypy.readthedocs.io/en/stable/command_line.html#cmdoption-mypy-strict |
| Pyright | Fast type checker (TypeScript impl.); `basic` vs `strict` vs `recommended` `typeCheckingMode` | Pyright docs, 2026 | https://microsoft.github.io/pyright/#/configuration |
| basedpyright | Pyright fork, **strict-by-default**, plus extra checks pyright leaves off | docs, 2026 | https://docs.basedpyright.com/ |
| ty (Astral) | New Rust type checker + language server; still **pre-1.0 / preview** | 0.0.76, 2026 | https://github.com/astral-sh/ty |
| Black | The uncompromising formatter; stable style is annual | 2026 releases | https://black.readthedocs.io/ |
| pre-commit | Git-hook framework; pins each hook by `rev`, runs in isolated envs | 2026 releases | https://pre-commit.com/ |
| actionlint | Static checker for GitHub Actions workflow YAML (incl. shellcheck integration) | 2026 releases | https://github.com/rhysd/actionlint |
| zizmor | Static security auditor for GitHub Actions workflows | docs, 2026 | https://docs.zizmor.sh/ |

### 3. Testing, property-based, mutation, fixtures

| Tool/Standard | What it is | Version/Date | URL |
|---|---|---|---|
| pytest | De-facto Python test runner; fixtures, parametrisation, plugins | 9.0.x (9.0.0 Dec 2025; 9.0.3 2026) | https://docs.pytest.org/en/stable/changelog.html |
| pytest-xdist | Parallel test execution; `-n auto`, `--dist worksteal` for uneven suites | 2026 releases | https://pytest-xdist.readthedocs.io/ |
| coverage.py | Coverage measurement; **branch coverage** via `--cov-branch` / `branch = true` | 7.15.3, 2026 | https://coverage.readthedocs.io/ |
| `COVERAGE_CORE=sysmon` | Uses PEP 669 `sys.monitoring`; materially faster tracing on 3.12+ | coverage.py docs, 2026 | https://coverage.readthedocs.io/en/latest/config.html |
| pytest-cov | pytest integration for coverage.py; `--cov-fail-under` gate | 2026 releases | https://pytest-cov.readthedocs.io/ |
| Hypothesis | Property-based testing; `@given`, shrinking, `settings` profiles, `@example` | 6.151.x, 2026 | https://hypothesis.readthedocs.io/ |
| `RuleBasedStateMachine` | Stateful/model-based testing — the right tool for stateful repair pipelines | Hypothesis docs, 2026 | https://hypothesis.readthedocs.io/en/latest/stateful.html |
| hypothesis-jsonschema | Generates Hypothesis strategies from JSON Schema; round-trips schema-conformant data | 2026 releases | https://github.com/python-jsonschema/hypothesis-jsonschema |
| mutmut | Mutation testing for Python; rewritten v3 with a new workflow and config | mutmut docs, 2026 | https://mutmut.readthedocs.io/ |
| cosmic-ray | Alternative mutation tester; distributed execution, SQLite result store | 2026 releases | https://cosmic-ray.readthedocs.io/ |
| pytest-benchmark | Micro-benchmarking; `--benchmark-compare` for regression gating, `--benchmark-json` for CI | 2026 releases | https://pytest-benchmark.readthedocs.io/ |
| syrupy | Snapshot testing for pytest; `--snapshot-update` to accept changes | 2026 releases | https://syrupy.readthedocs.io/ |
| inline-snapshot | Snapshots stored **inline in the test source** — reviewable in the diff | 2026 releases | https://15r10nk.github.io/inline-snapshot/ |
| time-machine | Clock control via C-level patching; `travel`/`shift`, fast and thread-safe | 2.19.0, 2026 | https://time-machine.readthedocs.io/ |
| freezegun | Older clock-patching library; largely superseded by time-machine | Maintenance mode | https://github.com/spulec/freezegun |
| respx | Mocking for **httpx** / HTTP Core | 2026 releases | https://lundberg.github.io/respx/ |
| responses | Mocking for **requests** | 2026 releases | https://responses.readthedocs.io/ |
| VCR.py | Records real HTTP interactions to cassettes and replays them | 2026 releases | https://vcrpy.readthedocs.io/ |
| testcontainers-python | Throwaway Docker containers (Postgres, Redis, Kafka…) as pytest fixtures | 4.3.3, 2026 | https://testcontainers-python.readthedocs.io/ |
| tox 4 | Declarative multi-env test matrix; `tox-uv` swaps the installer for uv speed | tox 4.x, 2026 | https://tox.wiki/ |
| nox | Programmatic (Python-DSL) test matrix — more flexible than tox for dynamic cases | 2025.2.9, 2026 | https://nox.thea.codes/ |

### 4. Runtime, concurrency, performance, observability

| Tool/Standard | What it is | Version/Date | URL |
|---|---|---|---|
| Python 3.12 | `sys.monitoring` (PEP 669), PEP 695 type params, per-interpreter GIL (PEP 684) | 3.12.0, Oct 2023 | https://docs.python.org/3/whatsnew/3.12.html |
| PEP 669 | Low-overhead monitoring API underpinning fast coverage/profilers | Final (2022) | https://peps.python.org/pep-0669/ |
| PEP 695 | `type X = ...`, `class C[T]`, `def f[T]()` — native generics syntax | Final (2022) | https://peps.python.org/pep-0695/ |
| Python 3.13 | Experimental free-threaded build (`python3.13t`, `--disable-gil`, `PYTHON_GIL=0`); experimental JIT; new REPL | 3.13.0, Oct 2024 | https://docs.python.org/3/whatsnew/3.13.html |
| PEP 703 | Making the GIL optional — the free-threading design that 3.13 shipped experimentally | Final (2023) | https://peps.python.org/pep-0703/ |
| PEP 744 | A copy-and-patch JIT compiler for CPython (experimental, off by default) | Final (2023) | https://peps.python.org/pep-0744/ |
| Python 3.14 | Deferred annotations (PEP 649), free-threaded C API (PEP 741), stdlib multiple interpreters; JIT still opt-in | 3.14.0 Oct 2025; 3.14.7 by 2026-09 | https://docs.python.org/3/whatsnew/3.14.html |
| PEP 779 | Criteria a free-threaded build must meet to become **officially supported** (Phase II gate) | Final (2025) | https://peps.python.org/pep-0779/ |
| PEP 649 | Deferred evaluation of annotations — replaces the `from __future__ import annotations` dance | Final (2024) | https://peps.python.org/pep-0649/ |
| PEP 734 | `concurrent.interpreters` — multiple interpreters in the stdlib (true isolation, own GIL) | Final (2024) | https://peps.python.org/pep-0734/ |
| PEP 768 | `sys.remote_exec()` — safe remote debugging/injection into a running process | Final (2025) | https://peps.python.org/pep-0768/ |
| PEP 745 | PyPI metadata for free-threaded wheels (so resolvers pick the right build) | Final (2024) | https://peps.python.org/pep-0745/ |
| py-free-threading tracker | Community compatibility tracker: which packages ship free-threaded wheels | Live tracker, 2026 | https://py-free-threading.github.io/ |
| asyncio TaskGroup | Structured concurrency in the stdlib; sibling of `asyncio.timeout` / `Runner` | Python 3.11+ | https://docs.python.org/3/library/asyncio-task.html#task-groups |
| anyio | Backend-agnostic async abstraction; runs on asyncio **or** trio; `to_thread.run_sync` | 4.11.x, 2026 | https://anyio.readthedocs.io/ |
| trio | The original structured-concurrency library; nursery model | 2026 releases | https://trio.readthedocs.io/ |
| uvloop | libuv-based drop-in asyncio event loop; large throughput win on Linux | 2026 releases | https://github.com/MagicStack/uvloop |
| py-spy | Sampling profiler that attaches to a **running** process with no code changes; `record`/`top`/`dump` | 0.4.2, 2026 | https://github.com/benfred/py-spy |
| Scalene | CPU + GPU + memory profiler with line-level attribution and low overhead | 2026 releases | https://github.com/plasma-umass/scalene |
| Memray | Bloomberg's memory profiler; flamegraphs, native + Python allocation tracking | 1.19.3, 2026 | https://github.com/bloomberg/memray |
| cProfile / pstats | Stdlib deterministic profiler and its report/statistics module | Python stdlib | https://docs.python.org/3/library/profile.html |
| tracemalloc | Stdlib allocation tracing with tracebacks — best for leak localisation | Python stdlib | https://docs.python.org/3/library/tracemalloc.html |
| structlog | Structured logging: processor pipeline, `contextvars` binding, JSON output | 2026 releases | https://www.structlog.org/ |
| OpenTelemetry Python | OTel SDK: traces, metrics, logs; `opentelemetry-instrument` zero-code auto-instrumentation, OTLP export | 2026 releases | https://opentelemetry.io/docs/languages/python/ |

### 5. Supply chain & application security

| Tool/Standard | What it is | Version/Date | URL |
|---|---|---|---|
| pip-audit | PyPA vulnerability scanner for environments/requirements; `--fix`; PyPI advisory DB + OSV | 2.10.0, 2026 | https://github.com/pypa/pip-audit |
| OSV-Scanner | Google scanner over the OSV database; `osv-scanner scan source`, lockfile + SBOM input, offline mode | 2.4.0, 2026 | https://google.github.io/osv-scanner/ |
| OSV.dev | Open, aggregated vulnerability database (the ecosystem's canonical feed) | Live service | https://osv.dev/ |
| PyPA advisory database | Machine-readable Python vulnerability advisories (source for pip-audit) | Live repo | https://github.com/pypa/advisory-database |
| Dependabot | GitHub-native dependency + Actions updates and security alerts | GitHub docs, 2026 | https://docs.github.com/en/code-security/dependabot |
| Renovate | Configurable, multi-platform dependency updater; `config:recommended` preset | v44, 2026 | https://docs.renovatebot.com/ |
| CycloneDX | SBOM standard with VEX and ML/AI extensions; the de-facto SBOM format for security tooling | spec, 2026 | https://cyclonedx.org/specification/overview/ |
| SPDX | ISO/IEC 5962 SBOM + license-expression standard; v3 is a linked-data model | v3.0.1, 2026 | https://spdx.dev/use/specifications/ |
| Syft | Anchore SBOM generator across many ecosystems incl. Python | 1.48.0, 2026 | https://github.com/anchore/syft |
| cdxgen | OWASP CycloneDX SBOM generator with reachability evidence | v12, 2026 | https://github.com/CycloneDX/cdxgen |
| SLSA | Supply-chain Levels for Software Artifacts: Build Levels 1–3, provenance model | **v1.1**, approved Apr 2025 | https://slsa.dev/spec/v1.1/ |
| slsa-github-generator | Reference GitHub Actions workflows emitting SLSA provenance | 2026 releases | https://github.com/slsa-framework/slsa-github-generator |
| Sigstore / cosign | Keyless signing via OIDC identity + transparency log; signs images and attestations | cosign 2026 releases | https://docs.sigstore.dev/ |
| OpenSSF Scorecard | Automated repo-health checks: `Branch-Protection`, `Pinned-Dependencies`, `Dangerous-Workflow`, `Token-Permissions` | 5.5.0, 2026 | https://github.com/ossf/scorecard |
| Bandit | PyCQA AST-based security linter (B1xx–B7xx test IDs; `B602`/`B603` subprocess, `B301` pickle) | 1.9.3, 2026 | https://bandit.readthedocs.io/ |
| Semgrep | Pattern-based SAST with a large community registry; `semgrep ci` for diff-aware scanning | 2026 releases | https://semgrep.dev/docs/ |
| gitleaks | Fast secret scanner over git history and working trees | 2026 releases | https://github.com/gitleaks/gitleaks |
| detect-secrets | Yelp's secret scanner with **baseline files** to grandfather existing findings | 1.5.0, 2026 | https://github.com/Yelp/detect-secrets |
| TruffleHog | Secret scanner with live credential **verification** (`--only-verified`) — cuts false positives | v3, 2026 | https://github.com/trufflesecurity/trufflehog |
| GitHub secret scanning | Platform-native secret detection plus **push protection** to block secrets pre-commit | GitHub docs, 2026 | https://docs.github.com/en/code-security/secret-scanning |
| Python security docs | Official guidance on `pickle`, `eval`, `subprocess`, `tarfile`, XML and other footguns | Python docs, 2026 | https://docs.python.org/3/library/security_warnings.html |
| `pickle` warning | The stdlib's own explicit statement that pickle is **not secure against malicious data** | Python docs, 2026 | https://docs.python.org/3/library/pickle.html#module-pickle |
| PEP 706 | `tarfile` extraction filters; `filter='data'` becomes the safe default — fixes CVE-2007-4559 class | Final (2023) | https://peps.python.org/pep-0706/ |

### 6. CI/CD, containers, deployment, GenAI telemetry

| Tool/Standard | What it is | Version/Date | URL |
|---|---|---|---|
| GitHub Actions security hardening | Official guidance: script injection, untrusted input, least-privilege `GITHUB_TOKEN` | GitHub Docs, 2026 | https://docs.github.com/en/actions/reference/security/secure-use |
| `pull_request_target` | Dedicated warning page: this trigger runs with secrets + write token on fork PRs | GitHub Docs, 2026 | https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target |
| OIDC in GitHub Actions | Short-lived cloud credentials replacing long-lived secrets (`id-token: write`) | GitHub Docs, 2026 | https://docs.github.com/en/actions/concepts/security/openid-connect |
| `actions/attest-build-provenance` | Emits signed SLSA provenance for build artifacts | v4.2.2, 2026 | https://github.com/actions/attest-build-provenance |
| `actions/setup-python` | Installs Python incl. free-threaded builds; `python-version-file`, built-in pip cache | 2026 releases | https://github.com/actions/setup-python |
| `astral-sh/setup-uv` | Installs uv (and a Python) with caching; the fast path for uv-based CI | 2026 releases | https://github.com/astral-sh/setup-uv |
| Trivy | All-in-one scanner: `trivy fs`, `trivy image`, `trivy config`, SBOM and misconfiguration | 0.69.x, 2026 | https://trivy.dev/ |
| Grype | Anchore vulnerability scanner for images, filesystems and SBOMs | 0.109.1, 2026 | https://github.com/anchore/grype |
| Distroless images | Google's minimal base images (no shell/package manager) — shrinks attack surface | 2026 | https://github.com/GoogleContainerTools/distroless |
| Chainguard Images | Minimal, near-zero-CVE hardened images with SBOMs and signatures | 2026 | https://images.chainguard.dev/ |
| Docker build attestations | `docker buildx build --provenance` / `--sbom` attach signed metadata to images | Docker docs, 2026 | https://docs.docker.com/build/attestations/ |
| Kubernetes | Container orchestration; release cadence ~3/yr, supported skew of 3 minor versions | 1.34.x, 2026 | https://kubernetes.io/releases/ |
| Pod Security Standards | `baseline` and `restricted` profiles: `runAsNonRoot`, `readOnlyRootFilesystem`, drop `ALL` caps | Kubernetes docs, 2026 | https://kubernetes.io/docs/concepts/security/pod-security-standards/ |
| OTel GenAI semantic conventions | Standard attribute names for LLM spans: `gen_ai.system`, `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.operation.name` | **Experimental / development status** | https://opentelemetry.io/docs/specs/semconv/gen-ai/ |

---

## Table 2 — Compliance Items

| Compliance item | Scope | Key obligation | Timeline | URL |
|---|---|---|---|---|
| **Regulation (EU) 2024/1689 (AI Act)** | Providers/deployers placing AI on the EU market | Risk-based regime: prohibitions, GPAI duties, high-risk requirements, transparency | In force 2024-08-01 | https://eur-lex.europa.eu/eli/reg/2024/1689/oj |
| **Regulation (EU) 2026/1744 — "Digital Omnibus on AI"** | Amends the AI Act | Postpones high-risk deadlines; narrows Art. 50(2) grace; bans AI-generated NCII/CSAM | Adopted 2026-07-08, in force 2026-07-27 | https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=OJ:L_202601744 |
| Digital Omnibus — annotated text | Consolidated view of the amendments | Article-by-article comparison of amended AI Act | Published 2026 | https://artificialintelligenceact.eu/ai-act-explorer/digital-omnibus/ |
| AI Act Art. 5 — prohibited practices | All providers/deployers | Bans subliminal manipulation, social scoring, untargeted face scraping, emotion inference at work; **plus** NCII/CSAM generation (new) | 2025-02-02; new bans 2026-12-02 | https://artificialintelligenceact.eu/article/5/ |
| AI Act Art. 4 — AI literacy | Providers/deployers | Take measures to support staff AI literacy; no guaranteed outcome required | **2025-02-02** | https://artificialintelligenceact.eu/article/4/ |
| AI Act Arts 53–55 — GPAI obligations | Providers of general-purpose AI models | Technical documentation, copyright policy, public training-content summary; systemic-risk models (>10²⁵ FLOP) need evals + incident reporting | **2025-08-05; unamended by the Omnibus** | https://artificialintelligenceact.eu/article/53/ |
| GPAI Code of Practice | GPAI model providers | Voluntary code to demonstrate compliance with Arts 53–55; the practical compliance benchmark | Published 2025-07 | https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai |
| AI Act Art. 50 — transparency | Providers of generative/emotion/interaction AI | Disclose AI interaction; **Art. 50(2)**: machine-readable marking of synthetic output | **2026-12-02** (Omnibus grace period) | https://artificialintelligenceact.eu/article/50/ |
| AI Act Annex III — high-risk | Stand-alone high-risk systems (biometrics, education, employment, essential services, law enforcement, migration, justice) | Full Ch. III duties: QMS, risk management, data governance, technical docs, logging, human oversight, conformity assessment | **2 December 2027** (postponed from 2026-08-02) | https://artificialintelligenceact.eu/annex/3/ |
| AI Act Annex I — high-risk in regulated products | Safety components under sectoral harmonisation law | Same high-risk duties, routed through sectoral conformity assessment | **2 August 2028** (postponed from 2027-08-02) | https://artificialintelligenceact.eu/annex/1/ |
| AI Act Annex IV — technical documentation | High-risk providers | Draw up and maintain the Annex IV technical file; keep for 10 years | With high-risk obligations | https://artificialintelligenceact.eu/annex/4/ |
| AI Act Art. 72 — post-market monitoring | High-risk providers | Documented post-market monitoring system proportionate to risk | With high-risk obligations | https://artificialintelligenceact.eu/article/72/ |
| AI Act Art. 73 — serious incident reporting | High-risk providers | Report serious incidents to market surveillance authorities | With high-risk obligations | https://artificialintelligenceact.eu/article/73/ |
| AI Act Art. 27 — fundamental rights impact assessment | Deployers of Annex III high-risk (public bodies etc.) | FRIA before first use, plus notification to the authority | With high-risk obligations | https://artificialintelligenceact.eu/article/27/ |
| **Code generation is not automatically high-risk** | LLM-driven code generation | Code generation is a **GPAI** use case (Arts 53–55) — Annex III does not list software engineering. It becomes high-risk only if deployed as an Annex III use case (e.g. HR screening) or as an Annex I safety component | Ongoing | https://artificialintelligenceact.eu/annex/3/ |
| CEN-CENELEC JTC 21 | European standardisation | Drafting harmonised standards for the AI Act; **not complete** — a stated reason for the delay | Standards expected from late 2026 | https://www.cencenelec.eu/areas-of-work/cen-cenelec-topics/artificial-intelligence/ |
| **NIST AI RMF 1.0** (NIST AI 100-1) | Voluntary risk framework | Govern / Map / Measure / Manage functions | Jan 2023 | https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf |
| **NIST AI 600-1 — Generative AI Profile** | Voluntary; generative AI | 12 GenAI risk categories (incl. confabulation, data privacy, IP, dangerous content) + suggested actions | July 2024 | https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf |
| NIST AI 100-2 — Adversarial ML taxonomy | Voluntary | Taxonomy of evasion, poisoning, privacy attacks against ML | 2024–2025 | https://csrc.nist.gov/pubs/ai/100/2/e2025/final |
| **ISO/IEC 42001:2023** | AI management system (AIMS) | Certifiable management-system standard: AI policy, roles, impact assessment, lifecycle controls | 2023, current | https://www.iso.org/standard/81230.html |
| ISO/IEC 23894:2023 | AI risk management guidance | How to apply risk management to AI across the lifecycle | 2023, current | https://www.iso.org/standard/77304.html |
| ISO/IEC 25059:2023 | Quality model for AI systems | Extends SQuaRE (25010) with AI-specific quality characteristics | 2023, current | https://webstore.ansi.org/standards/iso/isoiec250592023 |
| ISO/IEC 25010:2023 | System/software quality model | The base product-quality model SQuaRE builds on | 2023 | https://www.iso.org/standard/78176.html |
| ISO/IEC 42005:2025 | AI system impact assessment | Guidance on performing and documenting AI impact assessments | 2025 | https://webstore.ansi.org/standards/iso/isoiec420052025 |
| ISO/IEC 42006:2025 | Bodies auditing/certifying AI | Requirements for organisations auditing and certifying AI management systems | 2025 | https://www.din.de/en/getting-involved/standards-committees/nia/publications/wdc-beuth:din21:394021527 |
| **ISO/IEC/IEEE 29119-1:2022** | Software testing — concepts | Vocabulary and concepts underpinning the 29119 family | 2022 | https://webstore.ansi.org/standards/iso/isoiecieee291192022 |
| ISO/IEC/IEEE 29119-2:2021 | Software testing — processes | Organisational, management and dynamic test processes | 2021 | https://webstore.ansi.org/standards/iso/isoiecieee291192021-2455205 |
| ISO/IEC/IEEE 29119-3:2021 | Software testing — documentation | Templates for test plans, test cases, incident reports | 2021 | https://www.iso.org/standard/79429.html |
| ISO/IEC/IEEE 29119-4:2021 | Software testing — techniques | Black-box and white-box test design techniques | 2021 | https://inen.isolutions.iso.org/ru/standard/79430.html |
| **ISO/IEC TR 29119-11:2020** | Testing AI-based systems | The 29119 part that addresses testing AI systems specifically | **2020 — a Technical Report, not a full IS** | https://webstore.ansi.org/preview-pages/ISO/preview_ISO+IEC+TR+29119-11-2020.pdf |
| **ISTQB CT-AI v2.0** | Certification: AI testing | Testing AI systems (ML models, datasets); v2.0 supersedes v1.0 | v2.0 current | http://bstqb.qa/files/syllabus_ct-ai_2.0br.pdf |
| **ISTQB CT-GenAI v1.0** | Certification: Generative AI testing | Specialist syllabus on testing generative AI, incl. LLM outputs, hallucination, prompt and RAG testing | v1.0, released **2025-07-25** | https://istqb.org/wp-content/uploads/sdm-uploads/CT-GenAI-Syllabus-v1.0.pdf |
| IEEE 7000-2021 | Ethical concerns in system design | Model process for embedding ethical values into system engineering | 2021 | https://standards.ieee.org/ieee/7000/6781/ |
| IEEE 7009-2024 | Fail-safe design for AI | Standard for fail-safe design of autonomous and semi-autonomous systems | **2024** | https://store.sfs.fi/en/ieee-7009-2024 |
| IEEE 7001-2021 | Transparency of autonomous systems | Measurable transparency requirements | 2021 | https://standards.ieee.org/ieee/7001/6929/ |
| **OECD AI Principles** | Intergovernmental policy | Human-centred values, transparency, robustness, accountability; supplies the widely-used "AI system" definition | Updated **May 2024** | https://oecd.ai/en/ai-principles |
| US EO 14179 | US federal policy | "Removing Barriers to American Leadership in AI"; revoked EO 14110 | 2025-01-23 | https://www.whitehouse.gov/fact-sheets/2025/01/fact-sheet-president-donald-j-trump-takes-action-to-enhance-americas-ai-leadership/ |
| US EO 14110 (revoked) | Former US federal AI policy | Safe/secure/trustworthy AI duties incl. reporting under the Defense Production Act | Oct 2023 → **revoked Jan 2025** | https://www.federalregister.gov/documents/2023/11/01/2023-24283/safe-secure-and-trustworthy-development-and-use-of-artificial-intelligence |
| OMB M-24-10 / M-24-18 | US federal agencies | Agency AI use and federal AI acquisition | 2024 | https://www.whitehouse.gov/wp-content/uploads/2024/03/M-24-10-Advancing-Governance-Innovation-and-Risk-Management-for-Agency-Use-of-Artificial-Intelligence.pdf |
| OMB M-25-21 / M-25-22 | US federal agencies | Successor memos: accelerating agency AI use; acquisition of AI | 2025 | https://www.cov.com/-/media/files/corporate/publications/2025/04/omb-issues-first-trump-2-0-era-requirements.pdf |
| America's AI Action Plan | US national strategy | Deregulatory AI strategy; deprioritises prior safety framing | July 2025 | https://oecd.ai/en/dashboards/policy-initiatives/americas-ai-action-plan |
| Colorado AI Act (SB 24-205) | US state — CO | Originally algorithmic-discrimination duties for high-risk AI | **Repealed and replaced** by 2026 legislation | https://www.gtlaw.com/-/media/files/insights/alerts/2026/05/gt-alert_colorado-repeals-and-replaces-the-colorado-ai-act.pdf |
| California AB 2013 / SB 942 | US state — CA | Training-data transparency; AI content provenance/labelling | 2024–2026 | https://leginfo.legislature.ca.gov/faces/billNavClient.xhtml?bill_id=202320240AB2013 |
| China Interim Measures for Generative AI | Generative AI services in China | Security assessments, algorithm filing, content labelling, lawful training data | Effective **2023-08-15** | https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm |
| TC260 generative-AI safety requirements | China baseline | Basic safety requirements for generative AI services | TC260-003 | https://www.tc260.org.cn/ |
| CoE Framework Convention on AI (CETS 225) | International treaty | First binding AI treaty; human rights, democracy, rule of law | Opened for signature 2024-09-05 | https://www.coe.int/en/web/artificial-intelligence/the-framework-convention-on-artificial-intelligence |
| UK AI Security Institute | UK national body | Renamed from AI Safety Institute; focuses on security/robustness evaluation | Renamed **Feb 2025** | https://www.gov.uk/government/organisations/ai-security-institute |
| **GDPR Art. 22** | Automated decisions with legal/significant effect | Right not to be subject to solely-automated decisions; safeguards incl. human intervention and contestation | In force since 2018-05-25 | https://eur-lex.europa.eu/eli/reg/2016/679/oj |
| GDPR Arts 13–15, 25, 35 | Transparency, DPbD, DPIA | Inform about automated decision-making; data protection by design; DPIA for high-risk processing | In force | https://eur-lex.europa.eu/eli/reg/2016/679/oj |
| **EDPB Opinion 28/2024** | AI models & personal data | Three-step test for when a model is "anonymous"; legitimate interest for training | Adopted **Dec 2024** | https://www.edpb.europa.eu/our-work-tools/our-documents/opinion-board-art-64/opinion-282024-concerning-certain-data-protection-aspects_en |
| Garante v. OpenAI (€15m fine) | Italian DPA enforcement | Fine for GDPR breaches over ChatGPT | Fined Dec 2024; **annulled by Tribunale di Roma, Mar 2026** | https://www.ansa.it/english/news/technology/2026/03/20/court-annuls-15-mn-garante-fine-for-openai_1e0e0f5f-5b8e-4b0e-9d0e-000000000000.html |
| EU Data Act — Reg. (EU) 2023/2854 | Data access & sharing | Cloud switching, data access rights; interacts with AI training data | Applies from 2025-09-12 | https://eur-lex.europa.eu/eli/reg/2023/2854/oj |
| **EU Cyber Resilience Act — Reg. (EU) 2024/2847** | Products with digital elements (incl. software) | Security-by-design, SBOM, vulnerability handling, CE marking, support period | In force 2024-12-10; **reporting obligations from 2026-09-11**; full application 2027-12-11 | https://eur-lex.europa.eu/eli/reg/2024/2847/oj |
| **NIS2 — Directive (EU) 2022/2555** | Essential/important entities | Cyber risk management, supply-chain security, incident reporting | Transposition deadline **2024-10-17** | https://eur-lex.europa.eu/eli/dir/2022/2555/oj |
| **SPDX License List v3.28.0** | License identifiers | Canonical identifiers used by PEP 639 license expressions and SBOMs | v3.28.0, 2026 | https://github.com/spdx/license-list-XML/releases/tag/v3.28.0 |
| ScanCode Toolkit | License/copyright scanning | Detects licenses and copyrights in source trees | 2026 releases | https://github.com/aboutcode-org/scancode-toolkit |
| OSS Review Toolkit (ORT) | License/security compliance pipeline | Orchestrates dependency analysis, license obligation resolution, SBOM output | 2026 releases | https://github.com/oss-review-toolkit/ort |
| FSFE REUSE | License metadata hygiene | Per-file license headers or a `REUSE.toml`; machine-checkable compliance | Spec v3.3 | https://reuse.software/spec-3.3/ |
| GNU AGPL-3.0 | Network copyleft | Offering a modified AGPL program over a network triggers source-availability duties | Current | https://www.gnu.org/licenses/agpl-3.0.html |
| GitHub Copilot duplication filter | Generated-code IP hygiene | Org setting to block suggestions matching public code; filter is on by default for matching | GitHub docs, 2026 | https://docs.github.com/en/copilot/how-tos/configure-personal-settings/find-matching-code |
| Doe v. GitHub (9th Cir.) | LLM training/code-generation litigation | Ninth Circuit limited the DMCA §1202(b) claim against Copilot but left the AI-training copyright question open | Opinion **2026-09-16** | https://cdn.ca9.uscourts.gov/datastore/opinions/2026/09/16/24-7700.pdf |
| BigCode "Am I in The Stack?" | Training-data opt-out | Lets maintainers check/exclude their repos from the Stack dataset | Live service | https://www.bigcode-project.org/docs/about/the-stack/ |

---

## Table Stakes for a 2026 Python Research System

These are the non-negotiable defaults — a system missing any of these is behind the frontier, not merely imperfect.

1. **`pyproject.toml` as the single source of truth.** `[project]` (PEP 621) for metadata, `[dependency-groups]` (PEP 735) for dev/test deps, `[build-system]` (PEP 518). No `setup.py`, no `requirements.txt` as the primary interface.
2. **A committed lockfile with hashes.** Either a tool lock (`uv.lock`) plus CI `--frozen`, or the standard `pylock.toml` (PEP 751). Reproducibility is a claim you must be able to prove offline.
3. **`src/` layout.** Prevents the test suite from silently testing an accidentally-imported working-directory copy instead of the installed package.
4. **One Rust-fast linter/formatter gate.** `ruff check` with a deliberate rule selection including `S` (bandit), `B`, `UP`, `SIM`, `RUF`, plus `ruff format --check`. Deterministic, sub-second, blocks the PR.
5. **Strict typing on the package, not the tests.** `mypy --strict` (or pyright/basedpyright `strict`) over `src/`, with `py.typed` shipped (PEP 561) so downstream consumers actually get the types.
6. **Branch coverage with a ratchet.** `--cov-branch` with `fail_under` set just below current, raised over time. Line coverage alone hides untested `else`/`except` paths — exactly the paths a repair system breaks.
7. **Property-based tests for every parser/serialiser/normaliser.** Hypothesis, including `RuleBasedStateMachine` for anything with state. Example-based tests cannot find the input that breaks a code-transformation pipeline.
8. **An SBOM emitted per build.** CycloneDX or SPDX, generated in CI, attached to the release artifact — this is now also a CRA expectation, not just good practice.
9. **Provenance + attestations.** Build in a hosted CI with OIDC (no long-lived cloud secrets), publish with PyPI Trusted Publishing, and emit `actions/attest-build-provenance` attestations. Consumers can then verify *how* the artifact was built (SLSA / PEP 740).
10. **Vulnerability and secret scanning that can fail the build.** `pip-audit`/OSV-Scanner over the locked graph; `gitleaks` + GitHub push protection over the repo. Scanning that only warns is decoration.
11. **Free-threaded Python on the test matrix.** Add `3.13t`/`3.14t` legs (PEP 703 → PEP 779). The GIL-free transition is the single largest runtime change in the window, and C-extension bugs surface only there.
12. **Structured logging + OTel traces from day one.** `structlog` with `contextvars` and OTLP export. Retrofitting observability into an LLM pipeline after an incident is far more expensive than emitting spans from the start.
13. **Pinned CI dependencies.** Every third-party Action pinned to a full commit SHA, `GITHUB_TOKEN` least-privilege by default, and `pull_request_target` either banned or used only with a hard review gate.
14. **A documented model-governance artefact set.** Even when not legally required: model card / intended-purpose statement, training-data summary, evaluation results, human-oversight description, and an incident-reporting path. This is what GDPR Art. 22, the AI Act's Art. 50 transparency duty and (for GPAI) Art. 53 documentation all reach for — and it is cheap to maintain continuously, expensive to reconstruct.
15. **A license gate in CI.** SPDX identifiers in metadata, `REUSE`-clean headers, and a scanner (ScanCode/ORT) that fails on new copyleft in a permissively-licensed codebase. Non-trivial once LLM-suggested code enters the tree.

---

## Top 10 Concrete Gates to Add to CI

Ordered by (risk reduced ÷ effort). Each is a discrete, blocking check.

| # | Gate | Concrete implementation | Why it blocks |
|---|---|---|---|
| 1 | **Unpinned CI dependency ban** | `zizmor` + `actionlint`; require full-SHA refs for every `uses:` | The `tj-actions/changed-files` compromise (CVE-2025-30066) leaked secrets via a mutable tag. Tags are attack surface. |
| 2 | **Workflow permission ceiling** | `permissions: {}` at workflow level; grant per-job; ban `pull_request_target` unless justified | A write-scoped `GITHUB_TOKEN` on a fork PR is remote code execution with your repo's credentials. |
| 3 | **Locked, hash-verified install** | `uv sync --frozen` (or `pip install --require-hashes -r requirements.txt`) | Any floating resolution is a supply-chain import of whatever was published five minutes ago. |
| 4 | **Vulnerability gate on the locked graph** | `pip-audit --strict` or `osv-scanner scan source` on the lockfile | Fails on a *known* CVE with an available fix — the cheapest real risk reduction available. |
| 5 | **Secret scan with history** | `gitleaks detect --redact` over full history + GitHub push protection enabled | Secrets committed once are compromised forever; history scanning is the only way to catch pre-existing leaks. |
| 6 | **Static security lint, blocking** | `ruff check --select S` (or Bandit) with an explicit, reviewed ignore list | Catches `pickle.loads`, `yaml.load`, `subprocess(shell=True)`, `eval` at review time, not in production. The `S` rules are free once Ruff is already running. |
| 7 | **Coverage ratchet on branch coverage** | `pytest --cov=src --cov-branch --cov-fail-under=<current>` | Makes coverage monotonic. Without the ratchet, coverage decays silently and the repair system loses its safety net. |
| 8 | **Typed public surface** | `mypy --strict src/` (not tests) + assert `py.typed` is in the built wheel | A repaired signature that type-checks is materially more likely to be correct; a missing `py.typed` silently voids all of it for consumers. |
| 9 | **SBOM + provenance artefact per build** | `syft`/`cdxgen` → SBOM, `actions/attest-build-provenance` → signed provenance, attached to the release | Turns "we believe this artifact is what we built" into a verifiable claim. Directly aligned with the CRA's SBOM expectation and PEP 740. |
| 10 | **Benchmark + free-threaded regression leg** | `pytest-benchmark --benchmark-compare-fail=mean:10%`; add a `3.14t` matrix leg | Catches the two silent regressions that matter for a 2026 research system: performance drift, and GIL-dependency in C extensions. |

**Runner-up (add if you ship containers):** `trivy image --exit-code 1 --severity HIGH,CRITICAL` on the multi-stage distroless build, with `--ignore-unfixed` so you are only gated on things you can actually fix.

---

## Verification Status & Caveats

**Independently verified in this session (fetched or confirmed in search results):**
- The AI Act amendment chain — **Regulation (EU) 2026/1744**, adopted 2026-07-08, in force 2026-07-27; Annex III → 2027-12-02, Annex I → 2028-08-02, Art. 50(2) → 2026-12-02; new NCII/CSAM prohibition from 2026-12-02; GPAI Arts 53–55 unamended. Corroborated by the omnibus text mirror, William Fry (2026-05-12), and multiple law-firm trackers.
- CRA reporting obligations live from **2026-09-11**.
- `pylock.toml` spec **fetched successfully** (HTTP 200) — PEP 751, `lock-version = "1.0"`.
- **Colorado AI Act was repealed and replaced** in 2026 — the commonly-cited SB 24-205 obligations no longer stand as written.
- **Garante's €15m OpenAI fine was annulled** by the Tribunale di Roma (March 2026) — cite the annulment, not the fine.
- Ninth Circuit opinion of **2026-09-16** (case 24-7700) limiting the DMCA claim in the Copilot litigation.
- Version anchors: uv 0.12.21 · ty 0.0.76 · pytest 9.0.3 · coverage.py 7.15.3 · Hypothesis 6.151.x · testcontainers-python 4.3.3 · pip-audit 2.10.0 · osv-scanner 2.4.0 · Bandit 1.9.3 · syft 1.48.0 · Grype 0.109.1 · Trivy 0.69.x · Scorecard 5.5.0 · SPDX License List 3.28.0 · detect-secrets 1.5.0 · time-machine 2.19.0 · py-spy 0.4.2 · memray 1.19.3 · anyio 4.11.0 · Renovate 44 · actions/attest-build-provenance v4.2.2 · SLSA v1.1 · Python 3.14.7 · Kubernetes 1.34.x · cdxgen v12 · Poetry 2.0.0 · nox 2025.2.9 · REUSE spec 3.3.
- Incidents: Ultralytics PyPI compromise (PyPI blog analysis, 2024-12-11) · `xz-utils` CVE-2024-3094 · `tj-actions/changed-files` CVE-2025-30066 + `reviewdog/action-setup` CVE-2025-30154 (CISA alert 2025-03-18) · polyfill.io · Shai-Hulud npm worm.

**Explicitly not verified — do not quote as fact:**
- **Exact current versions** for Ruff, mypy, Pyright, Black, Semgrep, gitleaks, cosign, structlog, OpenTelemetry Python, trio, uvloop, Scalene, mutmut, syrupy, respx, tox, inline-snapshot, VCR.py, pytest-xdist, pytest-benchmark, hypothesis-jsonschema. These are cited to canonical project pages without a pinned number; check the linked release page before quoting one.
- **Rolling ISO years** behind paywalls. ISO/IEC/IEEE 29119-3 and 29119-4 are cited via reseller/store pages because iso.org does not expose the year publicly. `ISO/IEC TR 29119-11` is confirmed to exist and is a **2020 Technical Report** — note that it is a TR, not a full International Standard.
- **NIST AI 100-2** is cited to the CSRC landing page; the publication year/edition marker was not fetched.
- **`predk`/`prek`** (a claimed Rust reimplementation of pre-commit) was **not substantiated** and is omitted.
- **OMB M-25-21 / M-25-22** are cited via a law-firm summary rather than the memos themselves.
- The **ISTQB CT-GenAI PDF** could not be fetched directly (the fetch tool rejects `application/pdf`). Its existence, exact title and 2025-07-25 date come from the publisher URL appearing in search results; **verify the chapter-level contents yourself before relying on specifics of its syllabus**.
- **`ISO/IEC 42006:2025`** is cited via a DIN catalogue page; the ISO catalogue number was not independently confirmed.

**Structural note on Part B for your system.** An LLM-driven *code testing and repair* system is, on the current text, a **GPAI use case, not an Annex III high-risk system** — Annex III does not enumerate software engineering. The binding obligations that actually bite are: AI Act Art. 4 (AI literacy, since 2025-02), Art. 50 transparency if outputs are published, and — if you fine-tune or ship a model — Art. 53 documentation and copyright-policy duties. GDPR Art. 22 matters only if the repair decisions produce legal or similarly significant effects on people without meaningful human review. Annex III high-risk would attach only if the same system were pointed at an Annex III domain (hiring, credit, education, biometrics), so keep the intended-purpose statement narrow and accurate.
