#!/usr/bin/env python3
"""FE 轮变异验证：沉默零修复与引文核验机制的四处回归锚点。

纪律（与 FB/FC/FD 轮同）：
- 干净树先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 FE 轮补上的判决退回沉默」——
未测量被读成零缺口、引文核验被跳过、版本化取摘要被退回最新版。
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

AUDIT = "scripts/tools/audit_fix_coverage.py"
VERIFY = "scripts/tools/verify_citation_quotes.py"

FE_TESTS = [
    "tests/test_citation_quote_verification_fe.py",
    "tests/test_audit_fix_coverage_registry_fd.py",
    "tests/test_audit_unmeasured_scope_fe.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "G1-audit-unmeasured-becomes-zero-gap",
        AUDIT,
        '    if result.get("total_unmeasured_files"):',
        "    if False:  # mutation: 未测量不再判红（「没测」被读成「测得 0」）",
        [],
    ),
    (
        "G2-audit-unmeasured-files-not-tracked",
        AUDIT,
        "            unmeasured_files.append(rel)\n            unmeasured_added_lines += len(lines)",
        "            pass  # mutation: 未测量文件不再被统计",
        [],
    ),
    (
        "G3-verify-skips-unverified-status",
        VERIFY,
        '                    "status": "unverified",',
        '                    "status": "abstract",  # mutation: 未核引文被当成已核',
        [],
    ),
    (
        "G4-verify-ignores-versioned-abstract",
        VERIFY,
        '                version = _version_of(row["source"], pid)',
        '                version = ""  # mutation: 不按版本取摘要（v2/v3 混用）',
        [],
    ),
    (
        # FE 收口轮：去版本键退回「最后处理的 entry 覆盖」（2512.08296 实测缺陷）。
        "G6-refresh-bare-key-entry-order",
        VERIFY,
        "            if pid not in latest or vernum > latest[pid][0]:",
        "            if True:  # mutation: 去版本键退回「最后处理的 entry 覆盖」",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞，不动任何判据 —— 必须 0 红。
        "G5-control-wording",
        VERIFY,
        "退出码：0 = 全部引文可核（摘要命中或已标注正文来源）；1 = 存在未命中且未标注的引文；",
        "退出码：0 = 全部引文可核（摘要命中或已显式标注正文来源）；1 = 存在未命中且未标注的引文；",
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
    cmd = [str(PY), "-m", "pytest", *FE_TESTS, *paths, "--collect-only", "-q"]
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
        *FE_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_fe_mut",
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
        if name.startswith("G") and name.endswith("control-wording"):
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
