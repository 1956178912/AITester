#!/usr/bin/env python3
"""BP 轮变异验证：污染级别缺席的分档披露与两消费者对账的 18 个锚点 + 1 个中性对照。

纪律（与 BH→BO 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改措辞）必须 0 红。

锚点方向：每一处都是「把 BP 补的披露退回沉默 / 退回有利判定」，不是随机扰动。
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

CROSS = "experiments/analysis_parts/cross_analysis.py"
STAT = "experiments/statistical_analysis.py"
AR = "experiments/analyze_results.py"

BP_TESTS = [
    "tests/test_bp_contamination_bucket_disclosure.py",
    "tests/test_bm_experiments_readside.py",
    "tests/test_experiments_analysis.py",
    "tests/test_batch_ix.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "P1-key-absent-merged-into-value-null",
        CROSS,
        '            unobserved["key_absent"] += 1',
        '            unobserved["value_null"] += 1  # mutation: 键级缺席并入值级缺席',
        [],
    ),
    (
        "P2-key-presence-check-dropped",
        CROSS,
        '        if "contamination_risk_level" not in row:',
        "        if False:  # mutation: 键不存在与值为 null 同形",
        [],
    ),
    (
        "P3-value-null-not-absent",
        CROSS,
        "        if level is None:",
        "        if False:  # mutation: null 不记缺席",
        [],
    ),
    (
        "P4-empty-string-not-absent",
        CROSS,
        '        if level == "":',
        "        if False:  # mutation: 空串不记缺席",
        [],
    ),
    (
        "P5-reason-collapse",
        CROSS,
        '            "reason": "no_rows" if not details else "no_level_recorded",',
        '            "reason": "no_rows",  # mutation: 两种不可用同形',
        [],
    ),
    (
        "P6-n_details-zero",
        CROSS,
        '    disclosure = {"n_details": len(details), "unobserved": unobserved, "unobserved_total": sum(unobserved.values())}',
        '    disclosure = {"n_details": 0, "unobserved": unobserved, "unobserved_total": 0}  # mutation: 行数与缺席数抹平',
        [],
    ),
    (
        "P7-delta-none-becomes-number",
        CROSS,
        '        result["high_vs_low_success_delta"] = None',
        '        result["high_vs_low_success_delta"] = 0.0  # mutation: 没测成写成数值',
        [],
    ),
    (
        "P8-missing-buckets-unname",
        CROSS,
        '        result["delta_missing_buckets"] = [lv for lv, r in (("high", high_rate), ("low", low_rate)) if r is None]',
        '        result["delta_missing_buckets"] = []  # mutation: 缺失档不点名',
        [],
    ),
    (
        "P9-view-absent-disclosure-zero",
        STAT,
        '            "unknown_of_which_absent": absent_rows,',
        '            "unknown_of_which_absent": 0,  # mutation: unknown 构成不披露',
        [],
    ),
    (
        "P10-view-absent-not-counted",
        STAT,
        "                absent_rows += 1",
        "                absent_rows += 0  # mutation: 缺席行不计数",
        [],
    ),
    (
        "P11-view-report-block-suppressed",
        STAT,
        "    if absent_rows:\n        # BP 轮：",
        "    if False:  # mutation: 构成披露整块消失\n        # BP 轮：",
        [],
    ),
    (
        "P12-view-fold-changed",
        STAT,
        '            level = recorded or "unknown"',
        "            level = recorded  # mutation: 缺席另立一档（改写批次 IX 历史口径）",
        [],
    ),
    (
        "P13-excluded-loses-unobserved",
        AR,
        '            excluded += int(cc.get("unobserved_total", 0))',
        "            excluded += 0  # mutation: 未记录行不计入未入对照",
        [],
    ),
    (
        "P14-silent-arms-dropped-again",
        AR,
        "    if contam_cross_rows or silent_cross_arms:",
        "    if contam_cross_rows:  # mutation: 沉默臂仍整节消失",
        [],
    ),
    (
        "P15-empty-arm-called-unrecorded",
        AR,
        '        (b, cc) for b, cc in contam_cross.items() if cc and not cc.get("available") and cc.get("n_details")',
        '        (b, cc) for b, cc in contam_cross.items() if cc and not cc.get("available")  # mutation: 没有行也说成没记录',
        [],
    ),
    (
        "P16-delta-cell-unlabeled",
        AR,
        '                missing_buckets = "、".join(cc.get("delta_missing_buckets") or [])',
        '                missing_buckets = ""  # mutation: 缺失档名不落到单元格',
        [],
    ),
    (
        "P17-all-na-note-suppressed",
        AR,
        "        if not delta_computable:",
        "        if False:  # mutation: 全表 N/A 仍可被读成「不显著、可信度较高」",
        [],
    ),
    (
        "P18-computable-flag-always-false",
        AR,
        "                delta_computable = True",
        "                delta_computable = False  # mutation: 有数值也当没有",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞（删「恒」字），不动任何判据 —— 必须 0 红。
        "P19-control-wording",
        CROSS,
        "两数因此恒满足",
        "两数因此满足",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BP_TESTS, *paths, "--collect-only", "-q"]
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
        *BP_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bp_mut",
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
    survivors = [n for n, v, _ in results if v != "FAILED" and n != "P19-control-wording"]
    wrong_control = [n for n, v, _ in results if n == "P19-control-wording" and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
