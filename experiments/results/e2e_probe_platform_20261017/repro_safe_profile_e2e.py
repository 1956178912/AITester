#!/usr/bin/env python3
"""safe 档最小任务端到端验证（N-2 追加修复证据；真实 LLM ≤2 次调用）。

目的：验证 `AITESTER_PROFILE=safe` 注入的 `KERNEL_SANDBOX_ENABLE=true` 下：
1. 执行器本地沙箱链路真实可用（零 LLM 小测试直接跑 ExecutorAgent）；
2. 最小 workflow 任务（generator 1 次真实 LLM + executor）端到端通过，
   test_passed=True 且无沙箱错误归因（kernel_sandbox_unavailable 不出现）。

用法（仓库根；真实 LLM 1 次，成本可忽略）::

    AITESTER_LLM_CACHE=0 .venv/bin/python \
        experiments/results/e2e_probe_platform_20261017/repro_safe_profile_e2e.py \
        | tee experiments/results/e2e_probe_platform_20261017/safe_profile_e2e.log

注意：`AITESTER_PROFILE=safe` 必须在 import config/executor 之前设置（profile 预设
在 config import 期注入）。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, _REPO_ROOT)
os.chdir(_REPO_ROOT)

# ── 环境协议（在 import 项目模块之前）──────────────────────────────────────
os.environ["AITESTER_PROFILE"] = "safe"
os.environ.setdefault("TEMPERATURE", "0.0")
os.environ.setdefault("LLM_THINKING_MODE", "disabled")
os.environ.setdefault("AITESTER_LLM_CACHE", "0")
os.environ.setdefault("BENCHMARK_PARALLELISM", "1")

_TINY_TARGET = "def add(a, b):\n    return a + b\n"
_TINY_TEST = "from tinymod import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"

import config  # noqa: E402
from src.agents.executor import ExecutorAgent  # noqa: E402
from src.budget.token_usage import get_usage, reset  # noqa: E402
from scripts.tools.e2e_probe import invoke_workflow  # noqa: E402

print("== safe 档开关生效检查 ==")
print("ACTIVE_PROFILE =", config.ACTIVE_PROFILE)
print("KERNEL_SANDBOX_ENABLE =", os.environ.get("KERNEL_SANDBOX_ENABLE"))
print("PATCH_SNAPSHOT_ROLLBACK_ENABLE =", os.environ.get("PATCH_SNAPSHOT_ROLLBACK_ENABLE"))
print("INJECTION_GUARD_ENABLE =", os.environ.get("INJECTION_GUARD_ENABLE"))
print("ROGUE_MONITOR_ENABLE =", os.environ.get("ROGUE_MONITOR_ENABLE"))

# ── 1. 执行器本地沙箱链路（零 LLM）────────────────────────────────────────
tmpdir = tempfile.mkdtemp(prefix="n2_safe_exec_")
target_file = os.path.join(tmpdir, "tinymod.py")
with open(target_file, "w", encoding="utf-8") as f:
    f.write(_TINY_TARGET)
exec_result = ExecutorAgent(timeout=120, use_docker=False, use_venv=False).execute(_TINY_TEST, target_file)
print("\n== 执行器（safe 档沙箱）==")
print(
    json.dumps(
        {
            "passed": exec_result.get("passed"),
            "coverage": exec_result.get("coverage"),
            "error_info": exec_result.get("error_info"),
            "kernel_sandbox_obs": exec_result.get("kernel_sandbox_obs"),
        },
        ensure_ascii=False,
        indent=2,
    )
)

# ── 2. 最小 workflow 任务（真 LLM 1 次）────────────────────────────────────
reset()
final_state, elapsed = invoke_workflow(
    _TINY_TARGET,
    module_name="tinymod",
    target_function="add",
    planner=False,
    debugger=False,
    max_iterations=1,
)
usage = get_usage().as_dict()
summary = {
    "elapsed_s": round(elapsed, 2),
    "test_passed": final_state.get("test_passed"),
    "error_category": final_state.get("error_category"),
    "stop_reason": final_state.get("stop_reason"),
    "generated_test_len": len(final_state.get("generated_test") or ""),
    "injection_findings": final_state.get("injection_findings"),
    "token_usage": usage,
    "active_profile": config.ACTIVE_PROFILE,
    "kernel_sandbox_enable": os.environ.get("KERNEL_SANDBOX_ENABLE"),
}
print("\n== 最小任务（真 LLM）==")
print(json.dumps(summary, ensure_ascii=False, indent=2))
print("\n== 判定 ==")
ok_local = bool(exec_result.get("passed")) and bool((exec_result.get("kernel_sandbox_obs") or {}).get("supported"))
ok_workflow = bool(final_state.get("test_passed"))
print("executor_sandbox_pass =", ok_local)
print("workflow_pass =", ok_workflow)
print("VERDICT =", "PASS" if (ok_local and ok_workflow) else "FAIL")
sys.exit(0 if (ok_local and ok_workflow) else 1)
