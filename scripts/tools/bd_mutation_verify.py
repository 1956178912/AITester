#!/usr/bin/env python3
"""BD 轮变异验证：MDO 两个 rc==0 判绿点 + 共享谓词的 6 个锚点 + 1 个中性对照。

纪律（与 BA/BB/BC 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 跑受影响面 → 记录红数 →
  sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
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

BD_TESTS = "tests/test_mdo_effective_green_bd.py"
BA_TESTS = "tests/test_effective_green_ba.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-baseline-effective-pass-guard-off",
        "src/measurement/mdo.py",
        "    if not suite_has_effective_pass(base_out):",
        "    if False:  # mutation: baseline guard off",
        [],
    ),
    (
        "M2-shared-predicate-ignores-failed",
        "src/utils/pytest_output.py",
        '    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0',
        '    return int(counts.get("passed", 0)) > 0  # mutation: failed ignored',
        [BA_TESTS],
    ),
    (
        "M3-shared-predicate-always-true",
        "src/utils/pytest_output.py",
        '    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0',
        "    return True  # mutation: always green",
        [BA_TESTS],
    ),
    (
        "M4-shared-predicate-ignores-passed",
        "src/utils/pytest_output.py",
        '    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0',
        '    return int(counts.get("failed", 0)) == 0  # mutation: passed ignored',
        [BA_TESTS],
    ),
    (
        "M5-mutant-effective-pass-guard-off",
        "src/measurement/mdo.py",
        """            if suite_has_effective_pass(out):
                outcome.ran = True
            else:
                outcome.no_effective_pass = True""",
        "            outcome.ran = True  # mutation: mutant guard off",
        [],
    ),
    (
        "M6-denominator-keeps-no-effective-pass",
        "src/measurement/mdo.py",
        "    denom = [o for o in outcomes if not o.non_terminating and not o.probe_invalid and not o.no_effective_pass]",
        "    denom = [o for o in outcomes if not o.non_terminating and not o.probe_invalid]",
        [],
    ),
    (
        "M7-control-comment-wording",
        "src/measurement/mdo.py",
        "    # 前置：测试套件必须在基准实现上**全绿**，否则 MDR 语义不成立",
        "    # precondition: suite must be green on base, otherwise MDR undefined",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BD_TESTS, *paths, "--collect-only", "-q"]
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
        BD_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bd_mut",
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
