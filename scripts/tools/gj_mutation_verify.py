#!/usr/bin/env python3
"""GJ 轮变异验证：稿件外部数字 ↔ 登记册落点机制的回归锚点。

纪律（与 FB/FC/FE/FF 轮同）：
- 干净树先全绿；
- 每个变异：读取原字节 → 写入变异 → compile() → 跑受影响面 → 记录红数 →
  sha256 校验后按**原字节**还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 GJ 轮补上的那一格退回沉默」——
缺登记不再被标出、快照漂移不再报红、登记册侧数字口径收窄、缺登记被渲染成
看似正常的落点。
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
TOOL = "scripts/tools/export_paper_external_numbers.py"

GJ_TESTS = [
    "tests/test_paper_external_numbers_gj.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "H1-unregistered-number-accepted",
        TOOL,
        '                    if number in row["nums"]:',
        "                    if True:  # mutation: 任何数字都被当成已登记",
        [],
    ),
    (
        "H2-snapshot-drift-not-reported",
        TOOL,
        "        if current != rendered:",
        "        if False:  # mutation: 快照与重算不一致不报红",
        [],
    ),
    (
        "H3-register-number-caliber-narrowed",
        TOOL,
        "                nums |= {_norm(n) for n in _ANY_NUM.findall(text)}",
        "                nums |= {_norm(n) for n in _PRECISE.findall(text)}  # mutation: 口径收窄",
        [],
    ),
    (
        "H4-missing-landing-rendered-normal",
        TOOL,
        '        landing = f"`{row[\'landing\']}`" if row["landing"] else "**缺登记**"',
        '        landing = f"`{row[\'landing\'] or sorted(row["keys"])[0]}`"  # mutation: 缺登记渲染成正常落点',
        [],
    ),
    (
        # GJ 轮（fresh clone 模拟实测后补）：无稿件环境（CI）下「快照 ↔ 登记册」的
        # 语义核验被跳过 ⇒ 坏快照 / 空快照判绿。
        "H6-no-draft-register-semantics-skipped",
        TOOL,
        "            problems = verify_snapshot_against_register(rows, reg)",
        "            problems = []  # mutation: 无稿件环境的语义核验被跳过",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞，不动任何判据 —— 必须 0 红。
        "H5-control-wording",
        TOOL,
        "退出码：0 = 快照与重算一致且无缺登记；1 = 不一致 / 有缺登记；2 = 用法或环境错误",
        "退出码：0 = 快照与重算一致且没有缺登记；1 = 不一致 / 有缺登记；2 = 用法或环境错误",
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
    cmd = [str(PY), "-m", "pytest", *GJ_TESTS, *paths, "--collect-only", "-q"]
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
        *GJ_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_gj_mut",
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
