#!/usr/bin/env python3
"""BH 轮变异验证：testless 验证四层 status 通道的 11 个锚点 + 1 个中性对照。

纪律（与 BA→BG 轮同）：
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

SRC = "src/tools/testless_validation.py"
BH_TESTS = ["tests/test_bh_testless_validation_status.py", "tests/test_testless_validation.py"]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        # 假干净主锚点：不可信 rc 恢复旧口径 passed = (疑点行数 == 0) 且自称 ok。
        "M1-mypy-untrusted-rc-looks-clean",
        SRC,
        '            "passed": False,\n'
        '            "status": VALIDATION_ERROR,\n'
        '            "reason": f"mypy_rc_{exit_code}",',
        '            "passed": not error_lines,  # mutation: 恢复假干净\n'
        '            "status": VALIDATION_OK,\n'
        '            "reason": f"mypy_rc_{exit_code}",',
        [],
    ),
    (
        # 根因锚点：argv 换回 mypy 已移除的旧拼写 ⇒ 该层恒 rc=2 不可测量。
        "M2-mypy-legacy-flag-restored",
        SRC,
        '                "--follow-imports=silent",',
        '                "--silent-imports",  # mutation: 旧拼写',
        [],
    ),
    (
        "M3-mypy-rc1-empty-report-accepted",
        SRC,
        "            if not error_lines:",
        "            if False:  # mutation: rc1 空报告被接受",
        [],
    ),
    (
        "M4-ast-guard-unparseable-looks-comparable",
        SRC,
        "    if unparseable is not None:\n"
        '        side = "原始代码" if unparseable == "unparseable_original" else "补丁代码"\n'
        "        return {\n"
        '            "passed": False,\n'
        '            "status": VALIDATION_ERROR,\n'
        '            "reason": unparseable,\n'
        '            "detail": f"AST 符号守卫不可测量（{side}无法解析，未做任何符号比较）",',
        "    if False:  # mutation: 不可解析当作可比较\n"
        '        side = "原始代码" if unparseable == "unparseable_original" else "补丁代码"\n'
        "        return {\n"
        '            "passed": False,\n'
        '            "status": VALIDATION_ERROR,\n'
        '            "reason": unparseable,\n'
        '            "detail": f"AST 符号守卫不可测量（{side}无法解析，未做任何符号比较）",',
        [],
    ),
    (
        "M5-naming-contract-unparseable-looks-passed",
        SRC,
        "    if unparseable is not None:\n"
        '        side = "原始代码" if unparseable == "unparseable_original" else "补丁代码"\n'
        "        return {\n"
        '            "passed": False,\n'
        '            "status": VALIDATION_ERROR,\n'
        '            "reason": unparseable,\n'
        '            "detail": f"命名契约回归不可测量（{side}无法解析，未做任何符号比较）",',
        "    if False:  # mutation: 不可解析当作契约通过\n"
        '        side = "原始代码" if unparseable == "unparseable_original" else "补丁代码"\n'
        "        return {\n"
        '            "passed": False,\n'
        '            "status": VALIDATION_ERROR,\n'
        '            "reason": unparseable,\n'
        '            "detail": f"命名契约回归不可测量（{side}无法解析，未做任何符号比较）",',
        [],
    ),
    (
        "M6-patch-contract-switch-off-undisclosed",
        SRC,
        '    if not env_flag("PATCH_CONTRACT_CHECK", True):',
        "    if False:  # mutation: 恒放行不披露",
        [],
    ),
    (
        # 聚合方向锚点：四层相互独立必须最差者优先，改成 ok 优先即 BG 的方向。
        "M7-aggregator-ok-wins",
        SRC,
        "_STATUS_PRECEDENCE = (VALIDATION_ERROR, VALIDATION_UNAVAILABLE, VALIDATION_DISABLED, VALIDATION_OK)",
        "_STATUS_PRECEDENCE = (VALIDATION_OK, VALIDATION_ERROR, VALIDATION_UNAVAILABLE, VALIDATION_DISABLED)",
        [],
    ),
    (
        "M8-unknown-status-defaults-ok",
        SRC,
        "            return candidate\n    return VALIDATION_ERROR",
        "            return candidate\n    return VALIDATION_OK  # mutation: 未知 status 当作可测量",
        [],
    ),
    (
        "M9-degradation-not-disclosed",
        SRC,
        "    if degraded:",
        "    if False:  # mutation: 降级不发 warning",
        [],
    ),
    (
        "M10-import-smoke-refusal-looks-measured",
        SRC,
        '            "status": VALIDATION_DISABLED,\n            "reason": "refused_dangerous_api",',
        '            "status": VALIDATION_OK,\n            "reason": "refused_dangerous_api",',
        [],
    ),
    (
        "M11-import-smoke-spawn-failure-looks-ok",
        SRC,
        '            "status": VALIDATION_UNAVAILABLE,\n            "reason": "import_smoke_exception",',
        '            "status": VALIDATION_OK,\n            "reason": "import_smoke_exception",',
        [],
    ),
    (
        # 中性对照：仅改注释措辞（删「早」字），不动任何判据 —— 必须 0 红。
        "M12-control-wording",
        SRC,
        "                # BH（2026-10-21）：--silent-imports 是 mypy 早已移除的旧拼写，",
        "                # BH（2026-10-21）：--silent-imports 是 mypy 已移除的旧拼写，",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BH_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BH_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bh_mut",
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
    output = proc.stdout + proc.stderr
    red = len(re.findall(r"^FAILED ", output, flags=re.MULTILINE))
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, red, tail


def main() -> int:
    rc, red, tail = run_tests([])
    print(f"[baseline] rc={rc} red={red} collected={collect_count([])}\n{tail}")
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
            results.append((name, "ANCHOR-ERROR", -1))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR", -1))
            continue
        expected_collected = collect_count(extra)
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail = run_tests(extra)
            mutated_collected = collect_count(extra)
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != expected_collected:
            print(f"[{name}] COLLECTED DRIFT {expected_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT", red))
            continue
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict}\n{tail}")
        results.append((name, verdict, red))

    print("\n=== SUMMARY ===")
    for name, verdict, red in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
