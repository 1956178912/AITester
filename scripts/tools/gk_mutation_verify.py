#!/usr/bin/env python3
"""GK 轮变异验证：agents 层三处缺陷修复的回归锚点。

纪律（与 FB/FC/FE/FF/GJ 轮同）：
- 干净树先全绿；
- 每个变异：读取原字节 → 写入变异 → compile() → 跑受影响面 → 记录红数 →
  sha256 校验后按**原字节**还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 GK 轮修上的那道守卫退回沉默」——
别名展开又写回错位置、随机族判定退回顶层名切分、探针文件帧又被放行、
早退路径又不清实例级沙箱状态。
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

GUARD = "src/agents/deterministic_guard.py"
DEBUGGER = "src/agents/debugger.py"
EXECUTOR = "src/agents/executor.py"

GK_TESTS = [
    "tests/test_agents_defect_fixes_gk.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "K1-alias-expansion-back-to-wrong-slot",
        GUARD,
        "        parts.append(_IMPORT_ALIASES.get(alias, alias))",
        "        parts[0] = _IMPORT_ALIASES.get(alias, alias)  # mutation: 别名展开又写回最外层属性位",
        [],
    ),
    (
        "K2-random-family-back-to-top-level-split",
        GUARD,
        "                if _is_random_qual(qual):",
        '                if qual.split(".")[0] in _RANDOM_ATTRS:  # mutation: 族判定退回顶层名切分',
        [],
    ),
    (
        "K3-probe-file-frame-accepted-again",
        DEBUGGER,
        '        if probe_file.rsplit("/", 1)[-1].endswith("_probe.py"):\n            return result',
        '        if False and probe_file.rsplit("/", 1)[-1].endswith("_probe.py"):  # mutation: 探针文件帧又被放行\n'
        "            return result",
        [],
    ),
    (
        "K4-early-return-state-not-cleared",
        EXECUTOR,
        "            self._kernel_sandbox_executable = None\n"
        "            self._kernel_sandbox_obs = {}\n"
        "            self._cleanup_temp_file(test_file)  # type: ignore[attr-defined]",
        "            self._cleanup_temp_file(test_file)  # type: ignore[attr-defined]  # mutation: 早退不清状态",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞，不动任何判据 —— 必须 0 红。
        "K5-control-wording",
        GUARD,
        "    「`numpy` 本身」不算（`numpy.array` 不是随机数）。",
        "    「`numpy` 本身」不算（`numpy.array` 不是随机数调用）。",
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
    cmd = [str(PY), "-m", "pytest", *GK_TESTS, *paths, "--collect-only", "-q"]
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
        *GK_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_gk_mut",
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
            path.write_bytes(original)
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR", -1))
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            path.write_bytes(original)
            print(f"[{name}] SYNTAX ERROR after mutation: {exc}")
            results.append((name, "SYNTAX-ERROR", -1))
            continue
        try:
            rc, red, tail = run_tests(extra)
        finally:
            path.write_bytes(original)
        sha_after = hashlib.sha256(path.read_bytes()).hexdigest()
        restored = sha_after == sha_before
        status = "RED" if red > 0 else "GREEN"
        print(f"[{name}] {status} red={red} rc={rc} restored={restored}")
        if not restored:
            print("  !! BYTES NOT RESTORED — abort")
            results.append((name, "RESTORE-FAIL", red))
            return 1
        results.append((name, status, red))

    print("\n=== 汇总 ===")
    failures = 0
    for name, status, red in results:
        if name.endswith("control-wording"):
            ok = status == "GREEN" and red == 0
            print(f"  {'OK  ' if ok else 'FAIL'} {name:44s} {status} red={red}（中性对照须 0 红）")
            failures += 0 if ok else 1
            continue
        ok = status == "RED"
        print(f"  {'OK  ' if ok else 'FAIL'} {name:44s} {status} red={red}")
        failures += 0 if ok else 1
    print(f"\n变异 {len(results) - 1} 个 + 中性对照 1 个；失败 {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
