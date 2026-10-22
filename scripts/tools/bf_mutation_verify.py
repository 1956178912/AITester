#!/usr/bin/env python3
"""BF 轮变异验证：脚本工具链 rc==0 判绿点的 8 个锚点 + 1 个中性对照。

纪律（与 BA→BE 轮同）：
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

BF_TESTS = "tests/test_bf_toolchain_effective_green.py"
BA_TESTS = "tests/test_effective_green_ba.py"
BE_TESTS = "tests/test_production_effective_green_be.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-sm-preflight-rc-only",
        "scripts/tools/self_mutation.py",
        "            green = run_has_effective_pass(returncode, output) and not timed_out",
        "            green = returncode == 0 and not timed_out  # mutation: rc only",
        [],
    ),
    (
        "M2-sm-preflight-reason-alias-off",
        "scripts/tools/self_mutation.py",
        '            elif returncode == 0 and not timed_out:\n                reason = "baseline_no_effective_pass"',
        '            elif False:  # mutation: reason alias off\n                reason = "baseline_no_effective_pass"',
        [],
    ),
    (
        "M3-sm-classify-rc-only",
        "scripts/tools/self_mutation.py",
        '        if run_has_effective_pass(returncode, output):\n            return OUTCOME_SURVIVED, ""',
        '        if True:  # mutation: rc only\n            return OUTCOME_SURVIVED, ""',
        [],
    ),
    (
        "M4-sm-classify-detail-drops-counts",
        "scripts/tools/self_mutation.py",
        '    counts = pytest_summary_counts(output)\n    if not counts:\n        return "unparseable_summary"',
        "    counts: dict[str, int] = {}  # mutation: drop counts\n"
        "    if not counts:\n"
        '        return "unparseable_summary"',
        [],
    ),
    (
        "M5-tpl-fixed-guard-off",
        "scripts/tools/verify_synthetic_templates.py",
        '            elif side == "fixed" and not effective:\n'
        "                problems.append(\n"
        '                    "gold 测试在 fixed 代码上无有效通过（全 skip / xfail / deselect，gold 材料自洽未被证明）"\n'
        "                )",
        "            elif False:  # mutation: fixed guard off\n"
        "                problems.append(\n"
        '                    "gold 测试在 fixed 代码上无有效通过（全 skip / xfail / deselect，gold 材料自洽未被证明）"\n'
        "                )",
        [],
    ),
    (
        "M6-tpl-buggy-variant-flattened",
        "scripts/tools/verify_synthetic_templates.py",
        "                if effective:\n"
        '                    problems.append("gold 测试在 buggy 代码上全绿（缺陷不可检出，模板无信息量）")',
        "                if True:  # mutation: every rc0 looks green\n"
        '                    problems.append("gold 测试在 buggy 代码上全绿（缺陷不可检出，模板无信息量）")',
        [],
    ),
    (
        "M7-tpl-effective-rc-only",
        "scripts/tools/verify_synthetic_templates.py",
        "            effective = run_has_effective_pass(rc, out)",
        "            effective = rc == 0  # mutation: rc only",
        [],
    ),
    (
        "M8-shared-predicate-always-true",
        "src/utils/pytest_output.py",
        '    return int(counts.get("passed", 0)) > 0 and int(counts.get("failed", 0)) == 0',
        "    return True  # mutation: always green",
        [BA_TESTS, BE_TESTS],
    ),
    (
        "M9-control-wording",
        "scripts/tools/self_mutation.py",
        "5. **green baseline 前置校验**：正式执行前在副本上跑一遍**未变异**的测试命令。",
        "5. **green baseline 前置校验**：正式执行前在副本上跑一遍未变异的测试命令（措辞改写）。",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BF_TESTS, *paths, "--collect-only", "-q"]
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
        BF_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bf_mut",
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
