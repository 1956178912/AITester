#!/usr/bin/env python3
"""D3 过度脱敏最小复现：长 base64 模式误伤文件系统路径（N-1 上报，零 LLM）。

用法（仓库根）::

    nice -n 15 .venv/bin/python \
        experiments/results/e2e_probe_platform_20261017/repro_over_redaction.py \
        | tee experiments/results/e2e_probe_platform_20261017/before_check_dataset_over_redaction.log

修复前预期：
    mask_sensitive_info('/tmp/.cache/aitester/quixbugs/correct_python_programs')
    → '/tmp/.<REDACTED_KEY>'（点号后长路径段被当成 base64 密钥）
    且 `main.py check-dataset quixbugs` 的日志行
    `gold 修复版目录：/Users/<user>/.<REDACTED_KEY>`（路径不可读）。

修复后预期：路径原样保留；真实密钥族（sk-/ghp_/AKIA/长 hex/长 base64）仍脱敏。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.chdir(_REPO_ROOT)
sys.path.insert(0, _REPO_ROOT)

from src.utils.logging_utils import fallback_mask_sensitive_info, mask_sensitive_info  # noqa: E402

#: 真实症状形态的路径（绝对路径 + 点号目录 + 长目录段）。
_PATH_SAMPLES = [
    "/tmp/.cache/aitester/quixbugs/correct_python_programs",
    "/Users/someuser/Workspace/AITester/.venv/bin/python",
    "/var/folders/pj/xxxx/T/aitester_m1_bitcount_07q05sj_",
    "/Users/someuser/.cache/aitester/quixbugs/correct_python_programs/python_programs",
]

#: 真实密钥族（占位假值；修复后必须仍被脱敏）。
_KEY_SAMPLES = {
    "sk-": "sk-aBcDeFgHiJkLmNoPqRsTuVwXyZ1234567890",
    "ghp_": "ghp_" + "aB3dE5fG7hI9jK1lM3nO5pQ7rS9tU1vW3xY5zA7bC9dE1fG3hI5",
    "AKIA": "AKIAPLACEHOLDERXXXXX",
    "hex40": "0123456789abcdef0123456789abcdef0123456789abcdef",
    "base64_56": "AbCdEfGhIjKlMnOpQrStUvWxYz123AbCdEfGhIjKlMnOpQrStUvWxYz01",
}

print("== D3 过度脱敏复现（mask_sensitive_info）==")
for path in _PATH_SAMPLES:
    masked = mask_sensitive_info(path)
    status = "OK(原样)" if masked == path else "OVER-REDACTED"
    print(f"[{status}] {path}\n    -> {masked}")

print("\n== 降级路径 fallback_mask_sensitive_info（路径应原样）==")
for path in _PATH_SAMPLES:
    masked = fallback_mask_sensitive_info(path)
    status = "OK(原样)" if masked == path else "OVER-REDACTED"
    print(f"[{status}] {path}\n    -> {masked}")

print("\n== 真实密钥族（必须仍被脱敏）==")
for label, key in _KEY_SAMPLES.items():
    masked = mask_sensitive_info(f"token {key} end")
    leaked = key in masked
    print(f"[{'LEAK' if leaked else 'OK(已脱敏)'}] {label}: {masked}")

print("\n== 真实症状：main.py check-dataset quixbugs 的 gold 路径可读性 ==")
proc = subprocess.run(
    [sys.executable, "main.py", "check-dataset", "quixbugs"],
    capture_output=True,
    text=True,
    timeout=180,
    cwd=_REPO_ROOT,
)
combined = f"{proc.stdout}\n{proc.stderr}"
gold_lines = [line for line in combined.splitlines() if "gold 修复版目录" in line or "correct_python_programs" in line]
over_redacted_lines = [line for line in gold_lines if re.search(r"\.<REDACTED", line)]
print(f"check-dataset rc={proc.returncode}")
if gold_lines:
    for line in gold_lines[:5]:
        print("  " + line.strip()[:300])
else:
    print("  (未找到 gold 路径行——QuixBugs 数据可能未就位)")
print(f"\nOVER_REDACTED_LINES = {len(over_redacted_lines)}")
print(f"VERDICT = {'FAIL(过度脱敏)' if over_redacted_lines else ('OK' if proc.returncode == 0 else 'CLI_FAIL')}")
sys.exit(1 if over_redacted_lines or proc.returncode != 0 else 0)
