#!/usr/bin/env python3
"""BB 轮变异验证：11 个判绿消费点的修复锚点 + 1 个中性对照。

纪律（与 BA 轮同）：
- 每个变异：读取原字节 → 写入变异 → compile() → 跑受影响面 → 记录红数 →
  sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 干净副本先全绿；变异必须转红；中性对照（仅改 docstring）必须 0 红。
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"

BB_TESTS = "tests/test_effective_green_consumers_bb.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-gold-conformance-guard-off",
        "experiments/emse_gold_conformance_audit.py",
        '    if rc == 0 and not _suite_has_effective_pass(out + "\\n" + err):',
        "    if False:",
        [],
    ),
    (
        "M2-optimization-p5-off",
        "experiments/emse_optimization.py",
        "        if rc == 0 and not _suite_has_effective_pass(output):",
        "        if False:",
        ["tests/test_emse_optimization.py"],
    ),
    (
        "M3-pruning-block-guard-off",
        "experiments/gold_consistency_pruning.py",
        "        if run is not None and run[0] == 0 and _suite_has_effective_pass(run[1]):",
        "        if run is not None and run[0] == 0:",
        [],
    ),
    (
        "M4-testlevel-reproduced-off",
        "experiments/emse_testlevel_detection.py",
        "            elif not _fixed_side_effective_pass(fixed):",
        "            elif False:",
        ["tests/test_emse_testlevel_detection.py"],
    ),
    (
        "M5-gold-diagnosis-status-off",
        "experiments/emse_ult_gold_diagnosis.py",
        '        status = "pass" if n_passed > 0 else "unverifiable"',
        '        status = "pass"',
        ["tests/test_emse_ult_gold_diagnosis.py"],
    ),
    (
        "M6-suite-repair-green-off",
        "experiments/suite_repair_pipeline.py",
        '        return res.returncode == 0 and _suite_has_effective_pass((res.stdout or "") + "\\n" + (res.stderr or ""))',
        "        return res.returncode == 0",
        [],
    ),
    (
        "M7-mutk-sanity-guard-off",
        "experiments/emse_ult_mutk_full.py",
        '        if proc.returncode == 0 and _suite_has_effective_pass((proc.stdout or "") + "\\n" + (proc.stderr or ""))',
        "        if proc.returncode == 0",
        [],
    ),
    (
        "M8-quixbugs-sanity-guard-off",
        "experiments/emse_quixbugs_mutk_full.py",
        '        if proc.returncode == 0 and _suite_has_effective_pass((proc.stdout or "") + "\\n" + (proc.stderr or ""))',
        "        if proc.returncode == 0",
        [],
    ),
    (
        "M9-sanity-audit-guard-off",
        "experiments/emse_test_sanity_audit.py",
        '            "pass" if _suite_has_effective_pass((proc.stdout or "") + "\\n" + (proc.stderr or "")) else "unverifiable"',
        '            "pass"',
        [],
    ),
    (
        "M10-dfsmoke-guard-off",
        "experiments/emse_ult_dfsmoke_accuracy.py",
        '            "pass" if _suite_has_effective_pass((proc.stdout or "") + "\\n" + (proc.stderr or "")) else "unverifiable"',
        '            "pass"',
        [],
    ),
    (
        "M11-mutation-baseline-diagnosis-off",
        "experiments/mutation_testing.py",
        '        if _baseline_detail and not _baseline_detail[-1].get("effective_pass"):',
        "        if False:",
        [],
    ),
    (
        "M12-control-comment-wording",
        "experiments/emse_gold_conformance_audit.py",
        "        # BB（2026-10-21，F03 同型）：gold 套件全 skip/xfail/deselect 时",
        "        # BB (2026-10-21, F03 sibling): gold suite all skip/xfail/deselect",
        [],
    ),
]


def run_tests(paths: list[str]) -> tuple[int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        BB_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bb_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=900,
        env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-3:])
    return proc.returncode, tail


def main() -> int:
    # 0) 干净副本基线
    rc, tail = run_tests([])
    print(f"[baseline] rc={rc}\n{tail}")
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
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, tail = run_tests(extra)
        finally:
            # sha256 校验后按原字节还原
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        red = "FAILED" if rc != 0 else "SURVIVED"
        n_failed = sum(1 for ln in tail.splitlines() if ln.startswith("FAILED"))
        print(f"[{name}] rc={rc} {red} (failed~{n_failed})\n{tail}")
        results.append((name, red))

    print("\n=== SUMMARY ===")
    for name, verdict in results:
        print(f"{verdict:14s} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
