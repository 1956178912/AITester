#!/usr/bin/env python3
"""BE 轮变异验证：生产路径 rc==0 判绿点的 8 个锚点 + 1 个中性对照。

纪律（与 BA→BD 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改注释）必须 0 红。
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

BE_TESTS = "tests/test_production_effective_green_be.py"
BA_TESTS = "tests/test_effective_green_ba.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-detection-gate-effective-guard-off",
        "src/tools/detection_gates.py",
        '    if res[0] == 0 and not suite_has_effective_pass(res[1] + "\\n" + res[2]):\n'
        '        return {"green": False, "rc": res[0], "unavailable": True}',
        '    if False:  # mutation: gate guard off\n        return {"green": False, "rc": res[0], "unavailable": True}',
        [],
    ),
    (
        "M2-executor-local-effective-guard-off",
        "src/agents/executor.py",
        "            passed = last_result is not None and run_has_effective_pass(last_result.returncode, output)",
        "            passed = last_result is not None and last_result.returncode == 0  # mutation: rc only",
        [],
    ),
    (
        "M3-executor-sandbox-effective-guard-off",
        "src/agents/executor_modes.py",
        "            passed = last_result is not None and run_has_effective_pass(last_result.returncode, output)",
        "            passed = last_result is not None and last_result.returncode == 0  # mutation: rc only",
        [],
    ),
    (
        "M4-executor-docker-effective-guard-off",
        "src/agents/executor_modes.py",
        "        passed = run_has_effective_pass(result.returncode, output)",
        "        passed = result.returncode == 0  # mutation: rc only",
        [],
    ),
    (
        "M5-repo-node-effective-guard-off",
        "src/agents/executor_repo.py",
        "                if res.returncode == 0 and run_has_effective_pass(0, _node_output):",
        "                if res.returncode == 0:  # mutation: rc only",
        [],
    ),
    (
        "M6-p2p-effective-guard-off",
        "src/tools/patch_rollback.py",
        "            if run_has_effective_pass(rc, output):",
        "            if True:  # mutation: rc only",
        [],
    ),
    (
        "M7-attempt-flaky-evidence-uses-rc",
        "src/agents/executor_runtime.py",
        "        if _attempt_effective_pass(attempt):",
        '        if attempt.get("passed"):  # mutation: rc evidence',
        [],
    ),
    (
        "M8-shared-predicate-always-true",
        "src/utils/pytest_output.py",
        '    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0',
        "    return True  # mutation: always green",
        [BA_TESTS],
    ),
    (
        "M9-control-comment-wording",
        "src/utils/pytest_output.py",
        'F03：pytest 对"没有任何断言执行"的套件同样返回 rc==0（全 skip / xfail /',
        "F03: pytest also returns rc==0 for suites that execute no assertion (all skip / xfail /",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BE_TESTS, *paths, "--collect-only", "-q"]
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
        BE_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_be_mut",
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
