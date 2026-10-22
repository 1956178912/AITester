#!/usr/bin/env python3
"""BQ 轮变异验证：四通道报告读侧披露的 16 个锚点 + 1 个中性对照。

纪律（与 BH→BP 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 BQ 补的读侧披露退回沉默 / 退回有利判定 / 退回同形」。
受影响面 = BQ 新锁 + BP/BM 既有锁 + 两个分析套件（合跑基线 collected=219）。
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

HELPER = "experiments/analysis_parts/check_leg_analysis.py"
AR = "experiments/analyze_results.py"
RMB = "experiments/run_main_batch.py"

BQ_TESTS = [
    "tests/test_bq_check_leg_readers.py",
    "tests/test_bp_contamination_bucket_disclosure.py",
    "tests/test_bm_experiments_readside.py",
    "tests/test_experiments_analysis.py",
    "tests/test_batch_ix.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 助手：七档分档与恒等式 ─────────────────────────────────────────
    (
        "Q1-absent-merged-into-null",
        HELPER,
        '        if channel not in row:\n            counts["absent"] += 1\n            continue',
        '        if False:  # mutation: 键缺席折成 null\n            counts["absent"] += 1\n            continue',
        [],
    ),
    (
        "Q2-null-not-counted",
        HELPER,
        '        if value is None:\n            counts["null"] += 1',
        '        if False:  # mutation: null 不记档（落进 other）\n            counts["null"] += 1',
        [],
    ),
    (
        "Q3-other-grade-not-counted",
        HELPER,
        '            counts["other"] += 1',
        "            pass  # mutation: 词表外值不计数（恒等式破裂）",
        [],
    ),
    (
        "Q4-other-values-detail-dropped",
        HELPER,
        "            if value not in other_values:\n                other_values.append(value)",
        "            if False:  # mutation: 词表外明细不记录\n                other_values.append(value)",
        [],
    ),
    (
        "Q5-recorded-rows-counts-all-rows",
        HELPER,
        "    recorded_rows = sum(1 for row in details if any(channel in row for channel in CHECK_LEG_CHANNELS))",
        "    recorded_rows = sum(1 for row in details)  # mutation: 未记录行也算记录",
        [],
    ),
    (
        "Q6-unmeasurable-set-widened-to-vocab",
        HELPER,
        "        1 for row in details if any(row.get(channel) in CHECK_LEG_UNMEASURABLE for channel in CHECK_LEG_CHANNELS)",
        "        1 for row in details if any(row.get(channel) in CHECK_LEG_VOCAB for channel in CHECK_LEG_CHANNELS)  # mutation: disabled 也算没测成",
        [],
    ),
    (
        "Q7-reason-collapse",
        HELPER,
        '        result["reason"] = "no_channel_recorded"',
        '        result["reason"] = "no_rows"  # mutation: 两种不可用同形',
        [],
    ),
    (
        "Q8-available-flipped",
        HELPER,
        '        "available": recorded_rows > 0,',
        '        "available": n_rows > 0,  # mutation: 没有记录也算可读',
        [],
    ),
    # ─── 渲染层：沉默臂点名与表格分档 ───────────────────────────────────
    (
        "Q9-silent-leg-arms-dropped-again",
        AR,
        "    if leg_rows or silent_leg_arms:",
        "    if leg_rows:  # mutation: 全未记录时节整段消失",
        [],
    ),
    (
        "Q10-zero-row-arm-called-unrecorded",
        AR,
        '    silent_leg_arms = [(b, lg) for b, lg in leg_map.items() if lg and not lg.get("available") and lg.get("n_rows")]',
        '    silent_leg_arms = [(b, lg) for b, lg in leg_map.items() if lg and not lg.get("available")]  # mutation: 没有行也说成没记录',
        [],
    ),
    (
        "Q11-not-clean-sentence-removed",
        AR,
        '            "**不是「四腿都干净」，也不是「没有任务」**——上表只对有记录的臂给分档。（BQ 轮）"',
        '            "上表只对有记录的臂给分档。（BQ 轮）"  # mutation: 沉默臂可被读成干净',
        [],
    ),
    (
        "Q12-off-vocabulary-note-suppressed",
        AR,
        "        if other_notes:",
        "        if False:  # mutation: 词表外取值不点名",
        [],
    ),
    (
        "Q13-unmeasurable-column-zeroed",
        AR,
        "f\"| {ch.get('error', 0) + ch.get('unavailable', 0)} | {ch.get('disabled', 0)} \"",
        "f\"| 0 | {ch.get('disabled', 0)} \"  # mutation: 没测成列抹零",
        [],
    ),
    (
        "Q14-null-and-absent-merged",
        AR,
        "f\"| {ch.get('null', 0)} | {ch.get('absent', 0)} | {lg.get('n_rows', 0)} |\"",
        "f\"| {ch.get('null', 0) + ch.get('absent', 0)} | 0 | {lg.get('n_rows', 0)} |\"  # mutation: 值级/键级缺席同形",
        [],
    ),
    # ─── 批次摘要行 ────────────────────────────────────────────────────
    (
        "Q15-unrecorded-batch-prints-zero-table",
        RMB,
        '        if leg["recorded_rows"]:',
        "        if True:  # mutation: 未记录也按零表打印（读成干净）",
        [],
    ),
    (
        "Q16-batch-unmeasurable-column-zeroed",
        RMB,
        "没测成={ch['error'] + ch['unavailable']}",
        "没测成=0  # mutation: 摘要行没测成列抹零",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞（去掉一对强调星号），不动任何判据 —— 必须 0 红。
        "Q17-control-wording",
        HELPER,
        "本模块只补**读侧披露**：分档计数 + 恒等式",
        "本模块只补读侧披露：分档计数 + 恒等式",
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
    cmd = [str(PY), "-m", "pytest", *BQ_TESTS, *paths, "--collect-only", "-q"]
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
        *BQ_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bq_mut",
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
    survivors = [n for n, v, _ in results if v != "FAILED" and n != "Q17-control-wording"]
    wrong_control = [n for n, v, _ in results if n == "Q17-control-wording" and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
