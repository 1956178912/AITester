#!/usr/bin/env python3
"""BC 轮变异验证：misguided_metrics 重放判绿的 5 个修复锚点 + 1 个中性对照。

纪律（与 BA/BB 轮同）：
- 每个变异：读取原字节 → 写入变异 → compile() → 跑受影响面 → 记录红数 →
  sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 干净副本先全绿；变异必须转红；中性对照（仅改注释）必须 0 红。
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python"

BC_TESTS = "tests/test_misguided_replay_effective_green_bc.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-replay-detection-guard-off",
        "experiments/misguided_metrics.py",
        """    if not _side_has_effective_pass(fixed_side):
        # F03 同型：fixed 侧 rc==0 但全 skip/xfail/deselect——没有任何
        # 断言通过，F2P 第二段不成立，记 None（不可测），不误报检出。
        return None""",
        "    if False:\n        return None",
        ["tests/test_misguided_metrics.py"],
    ),
    (
        "M2-replay-fixed-green-guard-off",
        "experiments/misguided_metrics.py",
        """        and fixed_side.get("exec_rc") is not None
        and _side_has_effective_pass(fixed_side)
    ):""",
        """        and fixed_side.get("exec_rc") is not None
    ):""",
        ["tests/test_misguided_metrics.py"],
    ),
    (
        "M3-verdict-agreement-guard-off",
        "experiments/misguided_metrics.py",
        """    if int(fixed_side["exec_rc"]) == 0 and not _side_has_effective_pass(fixed_side):
        return "not_applicable", "重放 fixed 侧 rc==0 但无有效通过（全 skip/xfail/deselect）——无法确认绿/红\"""",
        '    if False:\n        return "not_applicable", ""',
        ["tests/test_misguided_metrics.py"],
    ),
    (
        "M4-side-predicate-always-true",
        "experiments/misguided_metrics.py",
        """    outcomes = side.get("outcomes") or {}
    if outcomes:
        return any(status == "pass" for status in outcomes.values()) and not any(
            status == "fail" for status in outcomes.values()
        )
    return _suite_has_effective_pass(side.get("exec_summary_line") or "")""",
        "    return True",
        ["tests/test_misguided_metrics.py"],
    ),
    (
        "M5-skip-reason-preserve-off",
        "experiments/misguided_metrics.py",
        'if record["detection_agreement"] == "replay_none" and not record.get("detection_disagreement_reason"):',
        'if record["detection_agreement"] == "replay_none":',
        ["tests/test_misguided_metrics.py"],
    ),
    (
        "M6-control-comment-wording",
        "experiments/misguided_metrics.py",
        "        # F03 同型：fixed 侧 rc==0 但全 skip/xfail/deselect——没有任何",
        "        # F03 sibling: fixed rc==0 but all skip/xfail/deselect",
        ["tests/test_misguided_metrics.py"],
    ),
]


def run_tests(paths: list[str]) -> tuple[int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        BC_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bc_mut",
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
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        red = "FAILED" if rc != 0 else "SURVIVED"
        print(f"[{name}] rc={rc} {red}\n{tail}")
        results.append((name, red))

    print("\n=== SUMMARY ===")
    for name, verdict in results:
        print(f"{verdict:14s} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
