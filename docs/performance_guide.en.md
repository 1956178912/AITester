> **Language**: [中文版](performance_guide.md) | English (this document)

# AITester Performance Tuning Guide

> This document describes AITester's performance optimization mechanisms, configuration methods, and common troubleshooting.
> Last updated: 2026-09-26 (full-review & conservative-optimization round: §10.5 credential-stripping P0 hardening — numbered-variant wildcards + provider intermediate vars, coupled with `config_generator` `PROVIDER_TEMPLATES` keys; the 2026-09-25 0.10 deep-review round (negative-cache TTL / path-whitelist root normalization / trace summary elimination / stat no-rescan) and 0.9 LRU fast-path are in §7.3)

---

## 1. RAG Retriever Singleton

### 1.1 Background

Initializing a ChromaDB client involves:
- Loading the embedding model (bge-small-zh-v1.5, ~100MB)
- Opening the vector database index file
- Establishing the HNSW index memory mapping

A single initialization takes about **1-3 seconds**. If every node creates a new instance, one round of repair can waste **2-6 seconds**.

### 1.2 Implementation

The system implements a **lazy-loading singleton pattern** in `src/graph/rag.py` (`workflow.py` re-exports via `from src.graph.rag import get_rag_retriever` to preserve the old import path):

```python
# Module-level cache
_rag_retriever = None


def get_rag_retriever():
    """Get the RAG retriever singleton instance."""
    global _rag_retriever
    if _rag_retriever is None and RAG_MODULE_AVAILABLE:
        try:
            _rag_retriever = TestCaseRetriever()
            logger.info("RAG retriever singleton initialized")
        except Exception as e:
            logger.warning("Failed to initialize RAG retriever: %s", e)
            _rag_retriever = None
    return _rag_retriever
```

**Key characteristics**:
- Initializes on first call; subsequent calls return the cached instance directly
- Marked as unavailable on exception, avoiding repeated attempts
- Enabled/disabled via the `ENABLE_RAG` switch

### 1.3 Usage

Configure in the `.env` file:

```bash
ENABLE_RAG=true          # Enable RAG retrieval augmentation
```

> **Note**: Enabling RAG requires installing the `chromadb` dependency, and the first run will download the embedding model.

---

## 2. LLM Timeout Configuration

### 2.1 Background

LLM API calls may hang for a long time due to network issues or excessive model load, causing tasks to stall.

### 2.2 Configuration Items

| Config | Description | Default | Recommended Range |
|--------|-------------|---------|-------------------|
| `LLM_TIMEOUT` | Timeout per LLM call (seconds) | 60 | 30-300 |
| `LLM_RETRY_WAIT` | LLM retry wait time (seconds) | 30 | 10-60 |
| `EXECUTION_TIMEOUT` | pytest execution timeout (seconds) | 30 | 10-300 |
| `MAX_ITERATIONS` | Maximum number of repair iterations | 3 | 1-10 |

### 2.3 Configuration

Set in the `.env` file:

```bash
# LLM call timeout (prevents unresponsive API)
LLM_TIMEOUT=60

# LLM retry wait time (base for exponential backoff)
LLM_RETRY_WAIT=30

# pytest execution timeout
EXECUTION_TIMEOUT=30

# Maximum number of repair iterations
MAX_ITERATIONS=3
```

### 2.4 Retry Strategy

The system uses an **exponential backoff + automatic API switching** strategy:

```python
# Retry logic in base_agent.py
for attempt in range(max_retries):
    try:
        response = llm.invoke(messages, timeout=LLM_TIMEOUT)
        return response
    except APIReachLimitError:
        wait_time = 2**attempt * LLM_RETRY_WAIT
        time.sleep(wait_time)
        continue
    except Exception:
        # Switch to fallback API
        continue
```

**Characteristics**:
- Rate-limit errors: wait time grows as `2^attempt * base_wait`
- Status errors: exponential backoff retry
- All APIs failing: automatically switch to the next configuration

---

## 3. Concurrent Execution (BENCHMARK_PARALLELISM)

### 3.1 Background

In batch benchmark runs, N tasks executed serially take a total time = N × single-task time. Multi-threaded parallelism significantly reduces total time.

### 3.2 Configuration

```bash
# Run in parallel with 4 threads
BENCHMARK_PARALLELISM=4 python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 50 \
    --baselines aitester,plain_llm,single_agent

# Serial execution (default)
BENCHMARK_PARALLELISM=0 python experiments/run_benchmark.py ...
```

### 3.3 Multi-thread Configuration Isolation

The system achieves thread-level LLM configuration isolation via `threading.local()`:

```python
# base_agent.py
_thread_local = threading.local()


def set_thread_llm_config(api_key, base_url, model_name):
    """Set the LLM configuration for the current thread."""
    _thread_local.api_key = api_key
    _thread_local.base_url = base_url
    _thread_local.model_name = model_name
```

**API Key configuration during concurrent execution**:

```bash
# Configure multiple API Keys; the system rotates them automatically
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com
LLM_2_MODEL_NAME=model-2
```

### 3.4 Performance Comparison

| Task Count | Serial Time (est.) | 4-thread Parallel Time (est.) | Speedup |
|------------|--------------------|-------------------------------|---------|
| 10 | ~500s | ~130s | 3.8x |
| 50 | ~2500s | ~650s | 3.8x |
| 100 | ~5000s | ~1300s | 3.8x |

> Actual speedup depends on CPU core count, memory bandwidth, and API rate-limiting conditions.

---

## 4. Common Troubleshooting

### 4.1 RAG Initialization Failure

**Symptom**: `Failed to initialize RAG retriever` appears in the logs

**Possible causes**:
1. `chromadb` not installed
2. Embedding model download failed
3. Vector database directory permission issues

**Solution**:
```bash
# Check if chromadb is installed
pip list | grep chromadb

# Reinstall (if needed)
pip install chromadb

# Clear the RAG vector store and reinitialize (the RAG retrieval store is persisted in rag_data/, overridable via RAG_PERSIST_PATH;
# chromadb itself does not use a .chroma_cache directory; the old command is deprecated)
rm -rf rag_data/
```

### 4.2 LLM Call Timeout

**Symptom**: The task is unresponsive for a long time and eventually raises `TimeoutError`

**Possible causes**:
1. Slow API response (high model load)
2. Unstable network
3. `LLM_TIMEOUT` set too small

**Solution**:
```bash
# Increase the timeout
LLM_TIMEOUT=120

# Increase retry count (indirectly controlled via MAX_ITERATIONS)
MAX_ITERATIONS=5
```

### 4.3 Concurrent Execution Slower Than Expected

**Symptom**: Total time actually increases after setting `BENCHMARK_PARALLELISM > 1`

**Possible causes**:
1. API rate-limiting (multiple concurrent requests rejected)
2. CPU memory contention
3. Insufficient API Key configuration

**Solution**:
```bash
# Reduce the parallelism
BENCHMARK_PARALLELISM=2

# Add more API Keys to reduce rate-limiting probability
# Configure more LLM_N_* settings in .env.local

# Add a retry interval (exponential backoff is built in)
LLM_RETRY_WAIT=60
```

### 4.4 Coverage Consistently Below Threshold

**Symptom**: Tests run repeatedly but never reach `COVERAGE_THRESHOLD`

**Possible causes**:
1. `COVERAGE_THRESHOLD` set too high
2. Poor quality of LLM-generated tests
3. Complexity of the code under test exceeds LLM capability

**Solution**:
```bash
# Lower the coverage threshold
COVERAGE_THRESHOLD=70.0

# Increase iteration count
MAX_ITERATIONS=5

# Enable RAG augmentation (if there are historical successful cases)
ENABLE_RAG=true
```

---

## 5. Performance Tuning Best Practices

### 5.1 Quick Verification (Small-Scale Test)

```bash
# Serial execution, limit task count
python experiments/run_benchmark.py \
    --dataset examples \
    --task-limit 2 \
    --baselines aitester
```

### 5.2 Medium-Scale Test (Recommended Configuration)

```bash
# 4-thread parallel, synthetic dataset
BENCHMARK_PARALLELISM=4 \
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 20 \
    --baselines aitester,plain_llm,single_agent
```

### 5.3 Large-Scale Test (Publication-Grade Experiment)

```bash
# 8-thread parallel, large sample
BENCHMARK_PARALLELISM=8 \
LLM_TIMEOUT=90 \
LLM_RETRY_WAIT=45 \
python experiments/run_benchmark.py \
    --dataset synthetic \
    --task-count 100 \
    --baselines aitester,plain_llm,single_agent
```

### 5.4 Ablation Experiment Configuration

```bash
# Enable Planner only
ENABLE_PLANNER=true ENABLE_DEBUGGER=false \
python experiments/run_benchmark.py --dataset examples

# Enable Debugger only
ENABLE_PLANNER=false ENABLE_DEBUGGER=true \
python experiments/run_benchmark.py --dataset examples

# Pure LLM baseline (no Planner, no Debugger)
ENABLE_PLANNER=false ENABLE_DEBUGGER=false \
python experiments/run_benchmark.py --dataset examples
```

---

## 6. Monitoring & Diagnostics

### 6.1 Enable Debug Logging

```bash
# View detailed logs
PYTHONUNBUFFERED=1 python experiments/run_benchmark.py \
    --verbose \
    --log-level DEBUG
```

### 6.2 Key Metrics Monitoring

| Metric | Meaning | Normal Range |
|--------|---------|--------------|
| `avg_llm_latency` | Average LLM response time | < 30s |
| `llm_timeout_count` | LLM timeout count | < 5% |
| `retry_rate` | API retry rate | < 20% |
| `coverage_improvement` | Coverage improvement | > 10%/round |
| `max_iterations_reached` | Number of tasks hitting max iterations | < 30% |

**APIManager circuit breaker and cost-aware configuration items (4.1/4.2/3.4, monitored via `get_status()`)**:

| Config Item (`APIManagerConfig`) | Default | Monitoring Field (`get_status().nodes[*]`) | Description |
|------|---------|--------------------------------------------|-------------|
| `circuit_cooldown_seconds` | 60.0 | `circuit_open_remaining_s` | 4.1 circuit breaker cooldown: after consecutive failures reach `max_consecutive_failures`, the node enters a cooldown period and is skipped by the routing layer |
| `enable_half_open_probe` | True | `circuit_state` (closed/open/half_open) | 4.2 half-open probe: after cooldown expires, the node first enters the half-open window carrying only one probe request; on success it closes / on failure it reopens with a half cooldown of `min(cooldown/2, cap)` |
| `half_open_probe_penalty_cap_seconds` | 30.0 | (penalty duration cap, no independent monitoring field) | 4.2 half-open probe failure penalty cap, preventing infinite cooldown shortening for a dead provider |
| `cost_alert_threshold` | 2.0 | (logs WARNING when failover lands on an expensive node) | 3.4 cost alert: warn when failover goes to an expensive provider with `cost_weight >= threshold` |

| Metric | Meaning | Interpretation |
|--------|---------|----------------|
| `repair_convergence_metrics.first_attempt_success_rate` | Share of tasks that succeeded on the first attempt (iterations==0) | High = the task is friendly to the current model/strategy; low = multiple repair rounds needed, more pressure on the Debugger |
| `repair_convergence_metrics.success_iteration_stats.avg/median` | Average/median iteration count of successful tasks | Characterizes convergence speed; median is more robust than mean (resistant to long tail) |
| `quality_proxy_metrics.coverage_proxy` / `runtime_proxy` | Coverage and runtime proxies for successful/failed tasks | A conservative signal for observing "did the repair introduce a performance regression" |
| `quality_proxy_metrics.assertion_proxy` | If `details[].generated_test` exists, count `assert` lines per task | A proxy for assertion strength, detecting "assertion weakening" trends; old JSONs automatically N/A |

### 6.3 Profiling Scripts

```python
# Use cProfile to analyze a single task's time
python -m cProfile -s cumtime \
    -o profile.prof \
    main.py run examples/calculator.py --func divide

# View the profiling report
snakeviz profile.prof
```

---

## 7. LLM Client Reuse (Connection Pool Sharing)

### 7.1 Background

Before optimization, every LLM call created a new client instance (`ChatOpenAI` / `ZhipuAiClient`), meaning the underlying HTTP connection pool was created repeatedly. With high iteration counts (`MAX_ITERATIONS=3` × many tasks), the connection-establishment overhead accumulates significantly.

### 7.2 Implementation

`src/agents/base_agent.py` provides two client caches that reuse by configuration key:

| Path | Cache Key | Limit | Eviction Policy |
|------|-----------|-------|-----------------|
| OpenAI-compatible (`ChatOpenAI`) | `(model_name, temperature, api_key, base_url)` | 16 | FIFO |
| zai SDK (`ZhipuAiClient`) | `(api_key, base_url)` | 16 | FIFO |

Entry functions: `_get_or_create_chat_client()` and `_get_or_create_zai_client()`. Multiple calls under the same configuration share the same client (and its connection pool); different configurations do not affect each other.

### 7.3 Notes

- Cache limit of 16: normal usage (a small number of model configurations) will never reach it; when many different API Keys are rotated, eviction happens one by one in FIFO order — predictable behavior.
- Client reuse does not affect the LLM file cache or the in-process LRU fast path (the 0.9 round removed the standalone `src/graph/llm_cache.py` module; the in-process LRU fast path for the LLM file cache now lives inside `base_agent._call_llm_with_cache` — both operate at the response level, orthogonal to client lifetime).

---

## 8. Appendix: Configuration Quick Reference

```bash
# ==================== Basic configuration ====================
TEMPERATURE=0.2
COVERAGE_THRESHOLD=80.0

# ==================== Timeout configuration ====================
LLM_TIMEOUT=60              # LLM call timeout
LLM_RETRY_WAIT=30           # LLM retry wait
EXECUTION_TIMEOUT=30        # pytest execution timeout
MAX_ITERATIONS=3            # Maximum repair iterations

# ==================== Concurrency configuration ====================
BENCHMARK_PARALLELISM=4     # Number of parallel threads (0 = serial)

# ==================== Ablation switches ====================
ENABLE_PLANNER=true         # Enable Planner
ENABLE_DEBUGGER=true        # Enable Debugger
ENABLE_RAG=false            # Enable RAG

# ==================== LLM Provider configuration ====================
# Multiple API Key groups are supported; the system rotates them automatically
LLM_1_API_KEY=sk-key-1
LLM_1_BASE_URL=https://api.provider1.com
LLM_1_MODEL_NAME=model-1

LLM_2_API_KEY=sk-key-2
LLM_2_BASE_URL=https://api.provider2.com
LLM_2_MODEL_NAME=model-2
```

---

*Document version: v1.1 (added LLM client reuse section)*  
*Maintainer: aiterster-maintenance-team*

---

## 9. Performance Profiling Baseline (2026-09-12 measurements)

> Summarized from cProfile / tracemalloc measurements in `scripts/performance_profile.py`.

### 9.1 Runtime Logic Is Efficient, No CPU Hotspots

- **ErrorClassifier classification**: 2500 calls in just 0.025s (~10μs each); regexes are pre-compiled (`re.Pattern.search` instead of `re.compile` each time), no "repeated compilation" overhead
- **CodeAnalyzer AST analysis**: 50 loops in 0.132s; `ast.walk` / `iter_child_nodes` are normal AST-traversal overhead with no room for optimization
- **BaseAgent JSON/code extraction**: parsing logic is near zero cost; all time comes from the module's first import

### 9.2 Main Overhead Is Third-Party Library Import (Intrinsic Cost)

| Library | Time | Trigger Chain |
|---------|------|---------------|
| chromadb | ~0.6s | import workflow → retriever → chromadb |
| pandas + datasets | ~0.53s | import dataset_loader → datasets → pandas |
| openai + pydantic | ~0.9s | import base_agent/llm_client → langchain_openai → openai |

These libraries are all core dependencies of the project (RAG / dataset / LLM calls); import cost is intrinsic overhead that cannot be eliminated by code refactoring.

**Evaluation of optimization opportunities**: lazily importing chromadb / datasets only saves 0.5-0.6s startup in the "RAG disabled / dataset not loaded" scenario, but requires changing the availability checks of multiple node functions in the workflow. The gain is limited and the risk is high, so it is not implemented at this time.

### 9.3 Memory

tracemalloc measurements show memory deltas of all three tested modules are < 0.01 MB, nothing abnormal, no dedicated optimization needed.

### 9.4 Conclusion

The project currently has **no low-hanging-fruit performance optimizations**; the performance direction is to keep the status quo. The startup-time bottleneck is the intrinsic cost of third-party library import; at runtime there are no CPU hotspots and no memory leaks.

---

## 10. Docker Isolated Execution and Dependency Cache (4.3 + 4.4)

### 10.1 Background

The venv sandbox (`EXECUTOR_USE_VENV=true`) creates an isolated venv per dependency combination under `~/.cache/aitester/venvs/`. The first run requires `pip install` of missing dependencies (network + install time); subsequent runs with the same combination hit the disk cache (venv creation only, no dependency reinstall). But venv creation still has a fixed cost (`python -m venv` initialization + pip metadata resolution), and the cache hit rate drops when dependency combinations differ widely across tasks.

Docker isolated execution (`EXECUTOR_USE_DOCKER=true`) caches dependency pre-installation in the image build phase (Docker layer cache reuse) and passes the code under test via `docker run --rm -v <sandbox>:/workspace` volume mount at runtime, with zero per-task install cost.

### 10.2 Choosing an Execution Mode

| Mode | Suitable For | First-Time Cost | Steady-State Cost | Dependency Isolation | Credential Isolation |
|------|-------------|----------------|-------------------|--------------------|--------------------|
| Local (default) | Quick validation, single task | None | Low | ❌ | ❌ (subprocess already strips LLM API credentials) |
| venv sandbox | Experiments with third-party deps | High (pip install) | Medium (venv creation) | ✅ | ✅ |
| Docker | Publication-grade batch experiments | High (one-time image build) | Low (volume mount) | ✅ | ✅ (container-level isolation) |

**Selection criteria**: single task / fast iteration → local; SWE-bench with third-party deps → venv; large-scale parallel runs (`BENCHMARK_PARALLELISM > 1`) with stable dependencies → Docker.

### 10.3 Docker Configuration

```bash
# Build the image (one-time; dependency pre-installation completed at build time, layer cache reused)
docker build -t aitester:latest .

# Enable Docker isolated execution
EXECUTOR_USE_DOCKER=true python main.py run examples/calculator.py

# Specify a custom image (e.g. a version with specific dependencies pre-installed)
EXECUTOR_USE_DOCKER=true EXECUTOR_DOCKER_IMAGE=aitester:with-pandas \
    python main.py run examples/calculator.py
```

**Diagnostic behavior**: when the docker CLI is unavailable (not installed / daemon not running), the task returns a `docker_unavailable` diagnostic (`error_info.type`) **without silently falling back to local execution** — this avoids mixing experiment baselines (Docker-vs-local environment differences affect failure attribution).

**Execution time comparison**:
```bash
# Run the same task under both Docker and venv modes; outputs a Markdown comparison table
python scripts/compare_executor_modes.py \
    --tasks examples/calculator.py examples/string_utils.py
```

### 10.4 Dependency Cache Monitoring (4.4)

Venv cache hit-rate statistics and cleanup are now integrated into the analysis layer:

```bash
# List existing caches with hit rate (--list-only is read-only)
python main.py clean-venv-cache --list-only

# Clean up by age (venvs older than 30 days)
python main.py clean-venv-cache --max-age-days 30

# Clean up by size (venvs larger than 512MB)
python main.py clean-venv-cache --max-size-mb 512

# Fetch hit rate programmatically (analyze_results.py auto-renders the "Dependency Cache Hit Statistics (4.4)" section)
python -c "from src.tools.dependency import get_venv_cache_stats; print(get_venv_cache_stats())"
# → {"hits": N, "creates": M, "hit_rate": R}
```

**Cache directory override**: default `~/.cache/aitester/venvs/`; in container/CI isolation, point `AITESTER_VENV_CACHE_DIR` at a mounted volume (e.g. `/workspace/.venv_cache`) so the cache does not disappear with container teardown.

**Reading the hit rate**: `hit_rate = hits / (hits + creates)`. A low rate on a new experiment (first run of a dependency combination) is expected; it should approach 1.0 when re-running the same combination. A persistently low rate means checking whether `AITESTER_VENV_CACHE_DIR` points at a persistent volume.

### 10.4b Multi-Version venv Cache (4.4)

Binary packages for different Python versions are incompatible (e.g. numpy / pandas C extensions). venv_cache_dir includes the first two digits of sys.version_info in the cache key by default, isolating venvs of different versions (py3.10 / py3.12 prefixes) to avoid cross-reuse causing ImportError / segfaults:

```python
from src.tools.dependency import venv_cache_dir

# Default: uses the current interpreter version (e.g. 3.14 -> py3.14 prefix)
d = venv_cache_dir(["pandas"])
# -> ~/.cache/aitester/venvs/py3.14_<digest>_pandas

# Explicitly specify Python version (container / multi-version coexistence)
d_310 = venv_cache_dir(["pandas"], python_version="3.10")
d_312 = venv_cache_dir(["pandas"], python_version="3.12")
# All three are different; venvs are stored in isolated directories
```

**Behavior**:
- Same dependency combo + same Python version: reuse the same venv (cache hit)
- Different Python versions: different directories, zero cross-contamination
- create_venv reuses an existing venv directory if the python_version matches (no rebuild)

### 10.5 Subprocess Environment Credential Stripping (4.1 security hardening, 2026-09-24 dynamic-pattern)

In all three modes (local / venv / Docker), ExecutorAgent strips LLM API credentials from the subprocess environment. This closes the "generated code inherits host environment credentials" leak path — the code under test and the generated test code cannot access LLM keys via `os.environ`.

All three paths funnel through `scrub_os_environ()` in `src/utils/credential_scrub.py` (single implementation, no list drift):
- **Dynamic pattern**: `LLM_\d+_API_KEY` / `LLM_\d+_BASE_URL` (N = 1-32, aligned with the LLM-provider scan range in `config.py`) — covers every numbered provider such as `LLM_1_API_KEY`. Previously the venv/Docker paths inherited the host `os.environ` verbatim and the local path popped only 7 hard-coded vars (missing the `LLM_N_*` family); now scrubbed dynamically across all three.
- **Common SDK credentials (fixed list, historical)**: `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `ANTHROPIC_API_KEY` / `API_KEY` / `LLM_API_KEY` / `LLM_CONFIG_API_KEY`.
- **P0 hardening (2026-09-26 review round)**: the fixed names anchored to the full string (`^OPENAI_API_KEY$`) missed the multi-endpoint numbered naming actually present in `.env` (`OPENAI_API_KEY_2/3`, `OPENAI_BASE_URL_2/3`), so those credentials reached the code-under-test subprocess verbatim (an execution vector + leak surface). Now widened with numbered-variant wildcards `OPENAI_(API_KEY|BASE_URL)_\d+` plus provider intermediate vars (`ALIYUN_BAILIAN_API_KEY` / `AGNES_{DOMESTIC|INTERNATIONAL}_API_KEY` / `BIGMODEL_API_KEY` / `DEEPSEEK_API_KEY`, keys coupled with `PROVIDER_TEMPLATES` in `config_generator.py` to prevent list drift), covering the batch-script derivation surface.

## 11. SWE-bench repo-level verification venv isolation (P1, 2026-09-25)

### 11.1 Background: cross-commit global-python pollution

RepoExecutor (`src/agents/executor_repo.py`) caches repo environments by
`(repo, commit12)`. All repo_envs share the global `sys.executable` by
default; after `pip install -e .`, the global site-packages editable install
(`.pth` / `__editable__.sqlfluff-0.9.1.pth`) points at the "most recently
installed" commit's source. When running pytest on a cross-commit task,
`import <repo_pkg>` resolves to the wrong version:

- Measured with sqlfluff: the `BaseSegment._log_apply_fixes_check_issue`
  method exists at commit `8e724ef` but not at commit `38cff664`
  (renamed/removed). When global python points at `38cff664`, running
  conftest on the `8e724ef` env that references the old method →
  `AttributeError`, unrelated to the LLM patch.
- Same class: `ImportError while loading conftest` (an old commit's
  conftest fails to import under a newer commit's dependencies).

**This is one of the environment-layer root causes behind the 184622-round
SWE-bench 0/20 being misdiagnosed as "LLM engine cannot produce
applicable patches"** (the other layer is the difflib corrupt diff, see
§11.3).

### 11.2 venv isolation approach (`SWE_REPO_VENV_ISOLATION=true`, default off)

Build an independent venv beside each commit environment:

- `RepoExecutor._create_venv(env_dir)`: `python -m venv` inside
  `<env_dir>/venv/`; cache-hit detection via the `.venv_pip_installed`
  marker (distinct from global-mode `.pip_installed`).
- `RepoExecutor._venv_pip_install(repo_dir, env_dir)`:
  `<venv>/bin/python -m pip install -e .` (deps into the venv, no global
  pollution).
- `_run_test_nodes`: pytest runs with `<venv>/bin/python`; in venv mode
  **no host PYTHONPATH injection** (measured: injecting it actually
  produces ImportError — the editable install's `.pth` already puts this
  commit's src into the venv site-packages, and the host PYTHONPATH
  mixes other-commit paths into the search order, breaking isolation);
  `PATH` prepends `<venv>/bin` (so subprocess-internal python/pip calls
  point at the venv rather than falling back to the host).
- Global mode (`SWE_REPO_VENV_ISOLATION=false`, default): all repo_envs
  share the global python; `PYTHONPATH` puts `<repo>/src` first (so the
  current commit's source takes precedence over the global editable
  install), preserving compatibility with cached repo_envs (the
  `.pip_installed` marker).

```bash
# Repo-level SWE-bench verification + venv isolation (P1 calibration)
REPO_LEVEL_EXECUTION=true SWE_REPO_VENV_ISOLATION=true \
  SWE_BENCH_ENRICHMENT=./swe_bench_enrichment.jsonl \
  python experiments/run_benchmark.py --dataset swe_bench --task-limit 10 --baselines aiterster
```

### 11.3 Patch-pipeline fix (difflib corrupt diff → git diff --no-index)

The other layer of root cause behind 184622's all-False `llm_applied`:
`_diff_codes` originally hand-joined with `difflib.unified_diff`; in the
"LLM whole-file rewrite" scenario (where old and new line counts differ
widely), the produced diff's line counts disagree with git's parser, and
`git apply --check` reports `corrupt patch` — 5/5 non-empty LLM patches
were rejected.

Fix: `_diff_codes` now uses `git diff --no-index` (comparing two
worktree files `original` and `modified` inside a minimal git repo),
producing a unified diff with strictly correct line-count / trailing-newline
semantics; the `--- / +++` headers are rewritten to the gold target file's
repo path (`_extract_gold_target_relpath` takes the first non-test source
file's b/ side path from the official gold patch). After the fix, 5/5
non-empty LLM patches pass `git apply` cleanly.

### 11.4 Impact on experiment performance

- **Increased first-setup cost**: each commit env adds one
  `python -m venv` (~2-5s) + an in-venv `pip install -e .` (~30-90s,
  including dependency installation). Same-repo multi-task setups happen
  only once (cache reuse), so the per-task increment after amortization is
  negligible.
- **Verification-stage speedup**: venv isolation eliminates the false
  failures from cross-commit pollution (conftest ImportError);
  FAIL_TO_PASS runs straight to the functional-assertion layer without
  re-running to rule out environment pollution, and single-task verify
  time is stable (measured sqlfluff single-node FAIL_TO_PASS ~1-3s).
- **Disk cost**: ~200-500MB per commit venv (deps installed into the
  venv's site-packages), 20 commits ~4-10GB. Point `SWE_REPO_ENVS_DIR`
  at a larger disk; clean up with
  `rm -rf <SWE_REPO_ENVS_DIR>/sqlfluff/<commit>`.
