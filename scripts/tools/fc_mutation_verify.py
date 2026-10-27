#!/usr/bin/env python3
"""FC 轮变异验证：champion 守卫「假修复率无观测 ⇒ 读作 0」漏洞的三处回归锚点。

纪律（与 BH→BQ 轮同）：
- 干净树先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 FC 的披露/守卫退回沉默或退回有利判定」。
受影响面 = FC 新锁 + 既有编排搜索锁（合跑基线 collected 以实测为准）。
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PY = ROOT / ".venv" / "bin" / "python3"

SEARCH = "src/graph/orchestration_search.py"
DRIVER = "experiments/run_orchestration_search.py"

FC_TESTS = [
    "tests/test_champion_false_fix_evidence_fc.py",
    "tests/test_orchestration_search.py",
    "tests/test_optimized_mode_guard_fc.py",
    "tests/test_optimized_policy_guard_fb.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "F1-guard-accepts-unmeasured-arm",
        SEARCH,
        '        if n_false_fix < 1:\n            return "假修复率无观测（守卫无法判读，不得读作 0）"',
        '        if False:  # mutation: 无观测也当作 0 放行\n            return "假修复率无观测（守卫无法判读，不得读作 0）"',
        [],
    ),
    (
        "F2-report-hides-sample-count",
        SEARCH,
        '            "n_false_fix": len(false_fix_samples),',
        '            "n_false_fix": 0,  # mutation: 报告不再披露观测数',
        [],
    ),
    (
        "F3-renderer-always-numeric",
        DRIVER,
        '        false_fix_cell = f"{stats[\'mean_false_fix\']:.4f}" if n_false_fix > 0 else "不可测"',
        "        false_fix_cell = f\"{stats['mean_false_fix']:.4f}\"  # mutation: 缺证据照写成 0.0000",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞，不动任何判据 —— 必须 0 红。
        "F4-control-wording",
        SEARCH,
        "**假修复率须有观测**（`n_false_fix ≥ 1`）才谈得上第 3 条的守卫：",
        "假修复率须有观测（`n_false_fix ≥ 1`）才谈得上第 3 条的守卫：",
        [],
    ),
    (
        # 承重守卫退回 assert ⇒ `python -O` 下整条判据消失。
        "F5-cli-guard-back-to-assert",
        "src/cli/app.py",
        '    if final_state is None:\n        raise AssertionError("graph.invoke 未返回状态（非预期）")',
        '    assert final_state is not None, "graph.invoke 未返回状态（非预期）"',
        [],
    ),
    (
        "F6-mysql-guard-back-to-assert",
        "src/db/mysql_client.py",
        '        if self._pool is None:\n            raise AssertionError("MySQLClient 连接池未初始化")',
        '        assert self._pool is not None, "MySQLClient 连接池未初始化"',
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")
_BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _BROKER_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *FC_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *FC_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_fc_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    red = len(re.findall(r"^FAILED ", output, flags=re.MULTILINE))
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, red, tail


def precheck() -> bool:
    ok = True
    for name, relpath, old, _new, _ in MUTANTS:
        text = (ROOT / relpath).read_text(encoding="utf-8")
        counts = text.count(old)
        if counts != 1:
            print(f"[{name}] PRECHECK anchor count={counts} in {relpath}")
            ok = False
    print(f"[precheck] 锚点唯一性 {'全部通过' if ok else '有失败'}（{len(MUTANTS)} 个）")
    return ok


def main() -> int:
    if not precheck():
        return 1
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
    survivors = [n for n, v, _ in results if v != "FAILED" and n != "F4-control-wording"]
    wrong_control = [n for n, v, _ in results if n == "F4-control-wording" and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
