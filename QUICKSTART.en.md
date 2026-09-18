> **Language**: [中文版](QUICKSTART.md) | English (this document)

# AITester Quick Start Guide

## 1. Clone the Repository

```bash
git clone https://github.com/1956178912/AITester.git
cd AITester
```

## 2. Install Dependencies

```bash
# Create a virtual environment (Python 3.12+; the locked dependency scipy requires >=3.12)
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## 3. Configure Environment Variables

> Both steps are required: Step 1 configures non-sensitive items, Step 2 configures LLM keys (you may skip Step 1 and use the defaults, but the keys must be set).

### Step 1: Non-sensitive configuration (.env)

```bash
# Copy the non-sensitive configuration template
cp .env.example .env

# Adjust as needed (e.g. TEMPERATURE)
vim .env
```

### Step 2: LLM keys (.env.local, required)

```bash
# Copy the sensitive configuration template
cp config.local.example .env.local

# Edit the .env.local file and fill in LLM_N_API_KEY, etc.
vim .env.local
```

## 4. Verify the Configuration Is Loaded

```bash
# Only verify that configuration loads (no network calls): success prints the number of loaded LLM configs
python3 -c "from config import LLM_CONFIGS; print(f'Loaded {len(LLM_CONFIGS)} LLM configs')"

# To actually probe each model's API connectivity and quota (1 token each), use the script in step 6:
# python scripts/check_quota.py
```

## 5. Run Tests

```bash
# List example files
python3 main.py list-examples

# Test a single file
python3 main.py run examples/calculator.py --func add

# Test multiple files in parallel
python3 main.py run examples/calculator.py examples/string_utils.py --parallel=2
```

## 6. Optional: Model Quota Probing and Token-Saving Cache

LLM calls enable the file cache by default (`src/cache/`; a cache hit on the same prompt consumes no further tokens). This extends the usable time under "stop when the free quota is exhausted" providers.

```bash
# Probe which of the configured models are still alive and which have exhausted their 403 quota (1 token each, keys are not printed)
python scripts/check_quota.py

# Disable the cache / clear the cache
export AITESTER_LLM_CACHE=0
rm -rf src/cache
```

## 7. Optional: Advanced Switches (all off by default; no impact on normal use)

All of the following switches are off by default; enable them as needed (see the comments in `.env.example` for details):

```bash
# Structured JSONL tracing (4.1): write <task_uuid>.trace.jsonl per task,
# recording the decisions/tokens/latency of each agent node, for replaying in experimental analysis. When unset, everything is a no-op.
export AITESTER_TRACE_DIR=./trace_out

# Multi-candidate patches (3.1): the Debugger generates N candidate patches in one round; static + execution verification picks the best.
export ENABLE_MULTI_CANDIDATE_PATCH=true
export MULTI_CANDIDATE_COUNT=3
export MULTI_CANDIDATE_EXEC_VALIDATE=true   # Run tests per candidate to filter (higher cost)

# Cost-aware routing (3.4): the COST_AWARE strategy avoids failover switching the full traffic to an expensive provider.
# The relative cost multiplier for each provider is configured in .env.local as LLM_N_COST_WEIGHT.
# The cost alert threshold is configurable (3.2): a WARNING is logged when failing over to an expensive node with cost_weight >= threshold (default 2.0).
# Raise the threshold if it's too low and produces many false alarms (e.g. 3.0/5.0); lower it when cost sensitivity is high; no code changes needed:
from src.api.api_manager import APIManager, APIManagerConfig
manager = APIManager(config=APIManagerConfig(cost_alert_threshold=3.0))

# Circuit breaker cooldown + half-open probe (4.1 + 4.2): when an APIManager node reaches
# the max_consecutive_failures threshold of consecutive failures, it automatically enters a cooldown period (circuit_cooldown_seconds, default 60s).
# During the cooldown, the routing layer keeps skipping that node even if the health check flips is_healthy back to True.
# 4.2: after the cooldown expires, the node enters a "half-open" window that carries only a single probe request;
# a successful probe closes the circuit breaker and restores full routing; a failure reopens a half-length cooldown (min(cooldown/2, cap=30s)).
# Half-open probing is on by default (enable_half_open_probe=True); comparative experiments can fall back to 4.1's direct pass-through:
from src.api.api_manager import APIManager, APIManagerConfig
manager = APIManager(config=APIManagerConfig(
    circuit_cooldown_seconds=120.0,
    # Optional: disable half-open probing to revert to 4.1 behavior (default True)
    enable_half_open_probe=False,
    # Optional: upper bound on the half-open probe failure penalty duration (default 30.0s)
    # half_open_probe_penalty_cap_seconds=60.0,
))

# RAG (retrieval augmentation): can be explicitly enabled for synthetic/built-in dataset experiments
python experiments/run_benchmark.py --dataset synthetic --enable-rag

# 3.5 Cross-file repair (off by default): when enabled, the workflow inserts a
# cross_file_analyzer node between the executor and the debugger, analyzes the cross-file import
# dependencies of the code under test, and applies multi-file patches in topological order
# (the callee is modified first, the caller later); failures roll back as a whole.
# Single-file projects degrade automatically (when there are no dependency edges, the single-file path is taken).
export CROSS_FILE_ENABLE=true
export CROSS_FILE_MAX_MODULES=5

# 3.4 Assertion augmentation (off by default): before generating, the Generator uses AST to extract
# existing assert statements in the code under test and injects them into the prompt as "anchor assertions",
# avoiding assertion weakening / always-true assertions / magic-number smells.
export ASSERTION_AUGMENT_ENABLE=true

# Result analysis (4.3 + 1.1/1.2/1.3 metric enhancements + 2.1 contamination detection
# + 2.2 difficulty stratification + 4.4 dependency cache): after running the benchmark,
# generate a Markdown summary including success rate / token efficiency / iteration
# distribution / failure-cause distribution / RAG quality / repair convergence efficiency /
# repair convergence curve / test smell detection / multi-dimensional quality proxies /
# convergence failure-mode attribution (1.2, distinguishing "cannot pinpoint root cause"
# vs "cannot produce an effective patch") / boundary case coverage (1.3, AST conservative
# detection of None / empty collection / 0 / -1 / >= / <= boundary conditions) /
# mutation score (1.3, produced by external mutation testers; skipped when the field is
# absent) / assertion-strength AST enhancement (1.3, ast.parse + ast.Assert node
# counting, outputting ast_avg_assertions) /
# data contamination detection (2.1, token-level Jaccard overlap of SWE-bench golden
# patches, high >= 0.85 / medium >= 0.6) / task difficulty stratification (2.2,
# code_size / dependency_count / complexity_proxy) /
# execution feedback trace summary (3.2, observed task count / total executions /
# first-round pass rate / last-round reward signals / coverage trend) /
# dependency cache hit statistics (4.4).
# When corresponding keys are missing from an old JSON, it automatically falls back or
# degrades without crashing.
python experiments/analyze_results.py --results-dir experiments/results
# Optional: explicitly pass a golden-patch mapping ({task_id: patch_text}, JSON object)
# to override contamination detection
python experiments/analyze_results.py --results-dir experiments/results \
    --golden-patches /path/to/golden_patches.json

# 3.2 Execution feedback trace: the executor node is enabled by default; on every execution
# it appends passed / coverage_delta / elapsed / reward_signals {correctness, efficiency,
# simplicity} to state.execution_trace. To inspect a task's trace (details[].execution_trace
# in the result JSON):
python -c "import json; d=json.load(open('experiments/results/benchmark_xxx.json')); [print(r['task_id'], r.get('execution_trace')) for r in d['results']['aitester']['details'][:3]]"

# Failure root-cause classification + case knowledge base (5.3): attribute causes to the three major root causes
# (LLM capability / dependencies / frameworks); structured cases are written to failure_knowledge_base.json
# (including task_id / root_cause / reproduction steps / suggested fix).
python experiments/analyze_failures.py --results-dir experiments/results
python experiments/analyze_failures.py -r experiments/results -k experiments/results/failure_knowledge_base.json

# 4.4 Dependency cache monitoring: venv cache hit-rate statistics + cleanup
python main.py clean-venv-cache --list-only           # List existing caches with hit rate
python main.py clean-venv-cache --max-age-days 30     # Remove venvs older than 30 days
python main.py clean-venv-cache --max-size-mb 512     # Remove venvs larger than 512MB
# Hit rate is also auto-rendered in the analysis layer ("Dependency Cache Hit Statistics (4.4)" section of analyze_results.py)
python -c "from src.tools.dependency import get_venv_cache_stats; print(get_venv_cache_stats())"

# 4.3 Docker isolated execution (requires local docker + built image; dependency pre-install cache baked into image build)
docker build -t aitester:latest .
EXECUTOR_USE_DOCKER=true python main.py run examples/calculator.py
# Docker vs venv execution time comparison (Markdown table output, basis for choosing execution environment)
python scripts/compare_executor_modes.py --tasks examples/calculator.py examples/string_utils.py
# 1.2 Built-in mutation generator: AST-level three mutant classes
# (boundary-value replacement / operator flip / boolean negation),
# up to 20 per task, no mutmut dependency required
python -c "
from experiments.mutation_testing import MutationGenerator
gen = MutationGenerator()
mutants = gen.generate('def check(x): return x > 5 and not x')
print(f'{len(mutants)} mutants: {[(m.mutant_type, m.line_no) for m in mutants]}')
"

# 5.3 Cross-batch failure-mode comparison: track new / resolved / regressed
# failure-category trends across multiple benchmark JSON batches
python experiments/compare_failures.py     --results experiments/results/benchmark_synthetic_new.json     --cross-batch experiments/results/benchmark_synthetic_old.json     --cross-batch-baseline aitester

# 4.4 Multi-version venv cache: venv_cache_dir includes the Python version
# prefix in the cache key by default, isolating venvs of different versions
python -c "from src.tools.dependency import venv_cache_dir; print(venv_cache_dir(['pandas'], python_version='3.10'))"


# 4.1 Log redaction audit (scans all logger call sites; exit 0 = no suspicious points, can be wired into CI)
python scripts/audit_log_redaction.py
```

## Configuration File Description

| File | Description | Git Status |
|------|-------------|------------|
| `.env.example` | Non-sensitive configuration template | ✅ Committed |
| `config.local.example` | Sensitive configuration template (API Key) | ✅ Committed |
| `.env` | Actual configuration (create it yourself) | ❌ Excluded |
| `.env.local` | Actual sensitive configuration (create it yourself) | ❌ Excluded |

## Notes

1. **Do not commit `.env` and `.env.local` to Git**
2. Create your configuration files from `.env.example` and `config.local.example`
3. Store your API keys securely and do not share them with others
