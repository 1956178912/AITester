#!/usr/bin/env python3
"""BM 轮变异验证：实验/报告读侧 4 个收口面共 9 个锚点 + 1 个中性对照。

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

BM_TESTS = "tests/test_bm_experiments_readside.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M1-crash-leg-folds-to-low",
        "experiments/run_benchmark.py",
        '        logger.debug("污染风险等级计算失败（标记 unknown，不入干净组）: task=%s", task_id, exc_info=True)\n'
        '        return "unknown"',
        '        logger.debug("污染风险等级计算失败（保守标记 low）: task=%s", task_id, exc_info=True)\n'
        '        return "low"  # mutation: crash folds into the favorable grade',
        ["tests/test_2026_10_05_n_batch.py", "tests/test_contamination_multidim.py", "tests/test_batch_ix.py"],
    ),
    (
        "M2-status-not-read-on-experiment-side",
        "experiments/run_benchmark.py",
        '        contract_status=final_state.get("contract_status"),',
        "        contract_status=None,  # mutation: experiment side stops reading the status",
        ["tests/test_bl_status_readers_outcome.py", "tests/test_risk_approval_matrix.py"],
    ),
    (
        "M3-regr-denominator-full-rows",
        "experiments/run_main_batch.py",
        '            round(sum(1 for r in regr_meas if r["regression_rate"] == 1.0) / regr_k * 100, 1) if regr_k else None',
        '            round(sum(1 for r in regr_meas if r["regression_rate"] == 1.0) / n * 100, 1) if regr_k else None',
        [],
    ),
    (
        "M4-regr-unmeasurable-scored-zero",
        "experiments/run_main_batch.py",
        '        regr_meas = [r for r in det if r.get("regression_rate") is not None]',
        "        regr_meas = ["
        '{**r, "regression_rate": r.get("regression_rate") or 0.0} for r in det'
        "]  # mutation: unmeasurable scored as no regression",
        [],
    ),
    (
        "M5-te-unmeasurable-scored-zero",
        "experiments/run_main_batch.py",
        '        te_meas = [r for r in det if r.get("test_error_rate") is not None]',
        "        te_meas = ["
        '{**r, "test_error_rate": r.get("test_error_rate") or 0.0} for r in det'
        "]  # mutation: unmeasurable scored as no test error",
        [],
    ),
    (
        "M6-regr-marker-dropped",
        "experiments/run_main_batch.py",
        '        regr_text = f"{regr_rate}%" if regr_rate is not None else "不可测（无可测行）"',
        '        regr_text = f"{regr_rate}%"  # mutation: unmeasurable printed as a number',
        [],
    ),
    (
        "M7-excluded-rows-not-counted",
        "experiments/analyze_results.py",
        '            excluded = sum(int(s.get("tasks", 0)) for lv, s in by_level.items() if lv not in ("high", "low"))',
        "            excluded = 0  # mutation: uncompared rows stay invisible",
        [],
    ),
    (
        "M8-header-column-dropped",
        "experiments/analyze_results.py",
        '"| 基线 | 高污染任务 | 高污染成功率 | 低污染任务 | 低污染成功率 | 成功率差（高-低） | 未入对照任务 |"',
        '"| 基线 | 高污染任务 | 高污染成功率 | 低污染任务 | 低污染成功率 | 成功率差（高-低） |"',
        [],
    ),
    (
        "M9-note-omits-unknown",
        "experiments/analyze_results.py",
        '            "> 「未入对照任务」= medium/unknown/not_applicable 三档合计（BM 轮，2026-10-22 起显式列示，"',
        '            "> 「未入对照任务」= medium/not_applicable 两档合计（BM 轮，2026-10-22 起显式列示，"',
        [],
    ),
    (
        "M10-control-wording",
        "experiments/run_benchmark.py",
        '    - 检测器抛异常（补丁非文本、依赖导入失败等）→ "unknown"（BM 轮，',
        '    - 检测器抛异常（补丁非文本、依赖导入失败等）→ "unknown"（BM 轮收口，',
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BM_TESTS, *paths, "--collect-only", "-q"]
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
        BM_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bm_mut",
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
