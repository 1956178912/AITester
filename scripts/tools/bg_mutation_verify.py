#!/usr/bin/env python3
"""BG 轮变异验证：静态类型检查 outcome 通道的 8 个锚点 + 1 个中性对照。

纪律（与 BA→BF 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改措辞）必须 0 红。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"

BG_TESTS = "tests/test_bg_static_check_outcome.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-pyright-timeout-gate-off",
        "src/tools/type_repair.py",
        '        if bool(getattr(proc, "timed_out", False)):\n'
        '            _record_static_check_outcome(outcome_sink, "pyright", STATIC_CHECK_ERROR, "pyright_timeout")',
        "        if False:  # mutation: timeout gate off\n"
        '            _record_static_check_outcome(outcome_sink, "pyright", STATIC_CHECK_ERROR, "pyright_timeout")',
        [],
    ),
    (
        "M2-pyright-rc-gate-off",
        "src/tools/type_repair.py",
        "        elif _rc not in (0, 1):",
        "        elif False:  # mutation: rc gate off",
        [],
    ),
    (
        "M3-pyright-empty-output-clean",
        "src/tools/type_repair.py",
        '        if not raw_stdout.strip():\n            report_error = "pyright_empty_output"',
        '        if False:  # mutation: empty output looks clean\n            report_error = "pyright_empty_output"',
        [],
    ),
    (
        "M4-pyright-invalid-json-clean",
        "src/tools/type_repair.py",
        '            except _json.JSONDecodeError:\n                report_error = "pyright_invalid_json"',
        "            except _json.JSONDecodeError:\n"
        '                report_error = ""  # mutation: invalid json accepted',
        [],
    ),
    (
        "M5-pyright-missing-diagnostics-clean",
        "src/tools/type_repair.py",
        '                elif not isinstance(_parsed.get("generalDiagnostics"), list):',
        "                elif False:  # mutation: missing diagnostics accepted",
        [],
    ),
    (
        "M6-mypy-rc-gate-off",
        "src/tools/type_repair.py",
        "            if _exit_code in (0, 1):\n"
        '                _record_static_check_outcome(outcome_sink, "mypy", STATIC_CHECK_OK)',
        "            if True:  # mutation: any rc is ok\n"
        '                _record_static_check_outcome(outcome_sink, "mypy", STATIC_CHECK_OK)',
        [],
    ),
    (
        "M7-mypy-exception-clean",
        "src/tools/type_repair.py",
        '        _record_static_check_outcome(outcome_sink, "mypy", STATIC_CHECK_ERROR, "mypy_exception")',
        '        _record_static_check_outcome(outcome_sink, "mypy", STATIC_CHECK_OK, "mypy_exception")',
        [],
    ),
    (
        "M8-overall-error-hidden",
        "src/tools/type_repair.py",
        "    if STATIC_CHECK_ERROR in statuses:\n        return STATIC_CHECK_ERROR",
        "    if False:  # mutation: errors hidden\n        return STATIC_CHECK_ERROR",
        [],
    ),
    (
        "M9-control-wording",
        "src/tools/type_repair.py",
        "# 现每条返回路径经 outcome_sink 记录 {backend, status, reason}，layer 聚合为",
        "# 现每条返回路径经 outcome_sink 记录检查结果，layer 聚合为（措辞改写）",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BG_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        BG_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bg_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-3:])
    return proc.returncode, tail


def main() -> int:
    rc, tail = run_tests([])
    print(f"[baseline] rc={rc} collected={collect_count([])}\n{tail}")
    if rc != 0:
        print("BASELINE NOT GREEN — abort")
        return 1

    selected = MUTANTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [m for m in MUTANTS if any(m[0].startswith(w) for w in wanted)]
        print(f"[filter] running {len(selected)} of {len(MUTANTS)}")

    results = []
    for name, relpath, old, new, extra in selected:
        path = ROOT / relpath
        original = path.read_bytes()
        sha_before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR"))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR"))
            continue
        expected_collected = collect_count(extra)
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, tail = run_tests(extra)
            mutated_collected = collect_count(extra)
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != expected_collected:
            print(f"[{name}] COLLECTED DRIFT {expected_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT"))
            continue
        red = "FAILED" if rc != 0 else "SURVIVED"
        print(f"[{name}] rc={rc} collected={mutated_collected} {red}\n{tail}")
        results.append((name, red))

    print("\n=== SUMMARY ===")
    for name, verdict in results:
        print(f"{verdict:14s} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
