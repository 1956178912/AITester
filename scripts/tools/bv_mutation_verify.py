#!/usr/bin/env python3
"""BV 轮变异验证：两份判定核「沉默分档」的 58 个锚点 + 1 个中性对照。

纪律（与 BH→BU 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 强调星号）必须 0 红。

锚点方向：每一处都是「把 BV 补的求值状态 / 早退成因 / 分档 / 推断口径 / 报告披露
退回沉默、退回并档、退回同形」，其中判定核（`src/tools/patch_test_hacking.py`）的
五个求值状态与 `experiments/_verdict_silence.py` 的词表是「同源锁」的靶子。

受影响面 = BV 新锁 + BQ 键集棘轮 + 判定核原有批次锁（VIII / XIV）。
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

ID = "experiments/_verdict_silence.py"
PT = "src/tools/patch_test_hacking.py"
RB = "experiments/run_benchmark.py"
SA = "experiments/statistical_analysis.py"
AR = "experiments/analyze_results.py"
RM = "experiments/run_main_batch.py"

BASE_TESTS = [
    "tests/test_verdict_silence_bv.py",
    "tests/test_bq_check_leg_readers.py",
    "tests/test_patch_test_hacking.py",
    "tests/test_batch_viii.py",
    "tests/test_batch_xiv.py",
]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)
BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 单一事实源：词表与判定核同源 ─────────────────────────────────────
    ("V01-id-ok-renamed", ID, 'HACK_STATUS_OK = "ok"', 'HACK_STATUS_OK = "OK"  # mutation: ok 改名', []),
    (
        "V02-id-empty-patch-renamed",
        ID,
        'HACK_STATUS_EMPTY_PATCH = "empty_patch"',
        'HACK_STATUS_EMPTY_PATCH = "empty"  # mutation: 状态名漂移',
        [],
    ),
    (
        "V03-id-signal-vocab-drops-one",
        ID,
        '    "assert_weakened",\n    "exception_swallow_added",',
        '    "exception_swallow_added",  # mutation: 信号词表少一项',
        [],
    ),
    (
        "V04-id-candidate-reason-renamed",
        ID,
        'FL_REASON_NO_CANDIDATES = "no_candidates"',
        'FL_REASON_NO_CANDIDATES = "no_candidate"  # mutation: 成因名漂移',
        [],
    ),
    (
        "V05-id-fl-vocab-order",
        ID,
        "FL_REASON_VOCAB: tuple[str, ...] = (\n    FL_REASON_OK,",
        "FL_REASON_VOCAB: tuple[str, ...] = (\n    FL_REASON_NO_STATE,  # mutation: ok 不再居首",
        [],
    ),
    (
        "V06-id-inferred-vocab-leaks-recorded",
        ID,
        "    FL_INFERRED_UNATTRIBUTED,\n)",
        "    FL_INFERRED_UNATTRIBUTED,\n    FL_REASON_NO_PATCH,  # mutation: 推断词表混入记录档\n)",
        [],
    ),
    # ─── 读侧分类器：每一处都是「折档 / 并档 / 不点名」 ──────────────────
    (
        "C01-hack-unrecorded-read-as-ok",
        ID,
        "    if HACK_STATUS_KEY not in row:\n        return HACK_STATUS_UNRECORDED",
        "    if HACK_STATUS_KEY not in row:\n        return HACK_STATUS_OK  # mutation: 未记录读成 ok",
        [],
    ),
    (
        "C02-hack-absent-read-as-unrecorded",
        ID,
        '    if HACK_SUSPECTED_KEY not in row:\n        return "no_verdict"',
        "    if HACK_SUSPECTED_KEY not in row:\n        return HACK_STATUS_UNRECORDED  # mutation: 缺键折成未记录",
        [],
    ),
    (
        "C03-hack-other-prefix-dropped",
        ID,
        '    return f"other:{value}"\n\n\ndef hack_evaluated',
        '    return f"{value}"  # mutation: 词表外取值不再单列\n\n\ndef hack_evaluated',
        [],
    ),
    (
        "C04-hack-signals-keep-non-strings",
        ID,
        "    return [s for s in raw if isinstance(s, str)]\n\n\ndef fl_verdict",
        "    return list(raw)  # mutation: 非字符串项不再丢弃\n\n\ndef fl_verdict",
        [],
    ),
    (
        "C05-infer-no-patch-branch-dead",
        ID,
        '    if _is_blank(row.get("patch")):',
        "    if False:  # mutation: 无补丁不再单独成档",
        [],
    ),
    (
        "C06-inferred-no-patch-folds-to-unattributed",
        ID,
        "        return FL_INFERRED_NO_PATCH",
        "        return FL_INFERRED_UNATTRIBUTED  # mutation: 无补丁并进不归因",
        [],
    ),
    (
        "C07-fl-hit-basis-recorded",
        ID,
        '    if verdict in {"hit", "miss"}:\n        return (FL_REASON_OK, FL_BASIS_NOT_APPLICABLE)',
        '    if verdict in {"hit", "miss"}:\n        return (FL_REASON_OK, FL_BASIS_RECORDED)  # mutation: 已求值说成有成因键',
        [],
    ),
    (
        "C08-recorded-reason-ignored",
        ID,
        "    if FL_REASON_KEY in row:\n        reason = row.get(FL_REASON_KEY)",
        "    if False:  # mutation: 记录值不读，一律推断\n        reason = row.get(FL_REASON_KEY)",
        [],
    ),
    (
        "C09-fl-evaluated-accepts-not-evaluable",
        ID,
        '    if fl_verdict(row) not in {"hit", "miss"}:\n        return False',
        '    if fl_verdict(row) not in {"hit", "miss", "not_evaluable"}:  # mutation: 不可评估也算求值过\n        return False',
        [],
    ),
    (
        "C10-mismatch-always-false",
        ID,
        "    if FL_REASON_KEY not in row:\n        return False",
        "    if True:  # mutation: 矛盾永不点名\n        return False",
        [],
    ),
    (
        "C11-mismatch-not-evaluable-ok-ignored",
        ID,
        '    if verdict == "not_evaluable":\n        return reason == FL_REASON_OK',
        '    if verdict == "not_evaluable":\n        return False  # mutation: not_evaluable+ok 不再算矛盾',
        [],
    ),
    # ─── 判定核：五个求值状态各钉一次（归属错一格就红） ──────────────────
    (
        "D01-empty-original-misattributed",
        PT,
        '"status": STATUS_EMPTY_ORIGINAL}',
        '"status": STATUS_EMPTY_PATCH}  # mutation',
        [],
    ),
    (
        "D02-empty-patch-misattributed",
        PT,
        '"status": STATUS_EMPTY_PATCH}',
        '"status": STATUS_EMPTY_ORIGINAL}  # mutation',
        [],
    ),
    (
        "D03-orig-parse-error-blamed-on-patch",
        PT,
        '"status": STATUS_PARSE_ERROR_ORIGINAL}',
        '"status": STATUS_PARSE_ERROR_PATCHED}  # mutation',
        [],
    ),
    (
        "D04-patch-parse-error-blamed-on-orig",
        PT,
        '"status": STATUS_PARSE_ERROR_PATCHED}',
        '"status": STATUS_PARSE_ERROR_ORIGINAL}  # mutation',
        [],
    ),
    (
        "D05-clean-folded-into-silence",
        PT,
        'return {"suspected": bool(signals), "signals": signals, "status": STATUS_OK}',
        'return {"suspected": bool(signals), "signals": signals, "status": STATUS_EMPTY_PATCH}  # mutation: 判干净折成没看',
        [],
    ),
    # ─── 写侧接线：状态 / 成因逐档 ───────────────────────────────────────
    (
        "R01-no-state-misattributed",
        RB,
        '    empty = {"suspected": False, "signals": [], "status": "empty_patch"}',
        '    empty = {"suspected": False, "signals": [], "status": "empty_original"}  # mutation',
        [],
    ),
    (
        "R02-empty-original-misattributed",
        RB,
        '        return {"suspected": False, "signals": [], "status": "empty_original"}',
        '        return {"suspected": False, "signals": [], "status": "empty_patch"}  # mutation',
        [],
    ),
    (
        "R03-error-folded",
        RB,
        '        return {"suspected": False, "signals": [], "status": "detector_error"}',
        '        return {"suspected": False, "signals": [], "status": "empty_patch"}  # mutation: 异常折成没补丁',
        [],
    ),
    (
        "R04-fl-no-state-folded",
        RB,
        "        return _empty(FL_REASON_NO_STATE)",
        "        return _empty(FL_REASON_NO_PATCH)  # mutation",
        [],
    ),
    (
        "R05-fl-no-localization-folded",
        RB,
        "        return _empty(FL_REASON_NO_LOCALIZATION)",
        "        return _empty(FL_REASON_NO_PATCH)  # mutation",
        [],
    ),
    (
        "R06-fl-no-changed-folded",
        RB,
        "            return _empty(FL_REASON_NO_CHANGED_FUNCTIONS)",
        "            return _empty(FL_REASON_NO_CANDIDATES)  # mutation",
        [],
    ),
    (
        "R07-fl-no-candidates-folded",
        RB,
        "            return _empty(FL_REASON_NO_CANDIDATES)",
        "            return _empty(FL_REASON_NO_CHANGED_FUNCTIONS)  # mutation",
        [],
    ),
    (
        "R08-fl-error-folded",
        RB,
        "        return _empty(FL_REASON_ERROR)",
        "        return _empty(FL_REASON_NO_CHANGED_FUNCTIONS)  # mutation: 异常折成变更集合为空",
        [],
    ),
    (
        "R09-fl-ok-reason-changed",
        RB,
        '        return {**verdict, "reason": "ok"}',
        '        return {**verdict, "reason": FL_REASON_NO_STATE}  # mutation',
        [],
    ),
    (
        "R10-fl-changed-guard-removed",
        RB,
        "        if not changed:",
        "        if False:  # mutation: 变更集合为空不再单列",
        [],
    ),
    (
        "R11-row-status-crossed",
        RB,
        '            "test_hacking_status": _hack["status"],',
        '            "test_hacking_status": _hack["signals"],  # mutation: 十字串接',
        [],
    ),
    (
        "R12-default-status-clean",
        RB,
        '        "test_hacking_status": "empty_patch",',
        '        "test_hacking_status": "ok",  # mutation: 失败分支说成判干净',
        [],
    ),
    (
        "R13-default-reason-changed",
        RB,
        '        "fl_constraint_reason": FL_REASON_NO_STATE,',
        '        "fl_constraint_reason": FL_REASON_NO_PATCH,  # mutation',
        [],
    ),
    # ─── 统计与恒等式 ───────────────────────────────────────────────────
    (
        "S01-silent-counts-evaluated",
        SA,
        "    n_hack_silent = sum(hack_status_counts.get(k, 0) for k in HACK_STATUS_VOCAB if k != HACK_STATUS_OK)",
        "    n_hack_silent = sum(hack_status_counts.get(k, 0) for k in HACK_STATUS_VOCAB if k == HACK_STATUS_OK)  # mutation",
        [],
    ),
    (
        "S02-unrecorded-counted-as-contradiction",
        SA,
        "            if status not in {HACK_STATUS_OK, HACK_STATUS_UNRECORDED}:",
        "            if status != HACK_STATUS_OK:  # mutation: 历史行也算写侧矛盾",
        [],
    ),
    (
        "S04-hit-ratio-denominator",
        SA,
        '            "hit_ratio": (fl_verdict_counts.get("hit", 0) / n_fl_evaluated) if n_fl_evaluated else None,',
        '            "hit_ratio": (fl_verdict_counts.get("hit", 0) / (n_fl_evaluated + n_fl_not_evaluable))'
        " if n_fl_evaluated else None,  # mutation: 分母混进不可评估",
        [],
    ),
    (
        "S05-samples-uncapped",
        SA,
        "            if len(suspected_samples) < 20:",
        "            if len(suspected_samples) < 200:  # mutation: 封顶失效",
        [],
    ),
    (
        "S07-changed-3plus-bucket-renamed",
        SA,
        '    if n >= 3:\n        return "3+"',
        '    if n >= 3:\n        return "3"  # mutation: 3+ 档改名',
        [],
    ),
    (
        "S08-unknown-signals-dropped",
        SA,
        '            "unknown_signals": unknown_signals,',
        '            "unknown_signals": [],  # mutation: 词表外信号不点名',
        [],
    ),
    (
        "S09-recorded-reasons-not-counted",
        SA,
        "        if basis == FL_BASIS_RECORDED and FL_VERDICT_KEY in row:",
        "        if False:  # mutation: 记录成因不计数",
        [],
    ),
    (
        "S10-inferred-reasons-not-counted",
        SA,
        "        elif basis == FL_BASIS_INFERRED:",
        "        elif False:  # mutation: 推断成因不计数",
        [],
    ),
    (
        "S11-fl-not-recorded-zeroed",
        SA,
        '            "n_not_recorded": fl_verdict_counts.get("no_verdict", 0),',
        '            "n_not_recorded": 0,  # mutation: 未记录行当成没有',
        [],
    ),
    (
        "S12-status-recorded-formula",
        SA,
        '            "n_status_recorded": len(rows) - n_hack_not_recorded - n_hack_status_unrecorded,',
        '            "n_status_recorded": len(rows),  # mutation: 未记录也算已记录',
        [],
    ),
    # ─── 报告面：标题 / 表体 / 合计 / 注 / 脚注 ──────────────────────────
    (
        "P01-heading-renamed",
        AR,
        'lines.append("## 批次 VIII/XIV 判定核的沉默分档（BV：`test_hacking_*` / `fl_constraint_*` 的读侧）")',
        'lines.append("## 判定核分档")  # mutation: 章节名不再区分 BV 读侧',
        [],
    ),
    (
        "P02-hack-header-drops-column",
        AR,
        '            "| 基线 | 行数 | hack 有判定 | 状态已记录 | 已求值（ok） | 没看 | 状态未记录 | 判 True | 信号非空 |"',
        '            "| 基线 | 行数 | hack 有判定 | 状态已记录 | 已求值（ok） | 没看 | 状态未记录 | 判 True |"  # mutation: 掉一列',
        [],
    ),
    (
        "P03-totals-rows-zeroed",
        AR,
        '                    "n_rows": s.get("n_rows", 0),',
        '                    "n_rows": 0,  # mutation: 合计行不再取数',
        [],
    ),
    (
        "P04-silent-arm-note-text",
        AR,
        'f"> {len(silent_arms)} 个臂的结果行没有 `test_hacking_*` 判定键："',
        'f"> {len(silent_arms)} 个臂缺判定键："  # mutation: 不再点名缺哪个键',
        [],
    ),
    (
        "P05-silent-note-always",
        AR,
        '        if hack_totals["n_silent"]:',
        "        if True:  # mutation: 没看注常开",
        [],
    ),
    (
        "P06-suspected-note-always",
        AR,
        '        if hack_totals["n_suspected"]:',
        "        if True:  # mutation: 判 True 注常开（零也说）",
        [],
    ),
    (
        "P07-hit-ratio-threshold",
        AR,
        'if total_ratio is not None and fl_totals["n_evaluated"] and total_ratio >= 0.99:',
        'if total_ratio is not None and fl_totals["n_evaluated"] and total_ratio >= 1.01:  # mutation: 判别力注永不触发',
        [],
    ),
    (
        "P08-share3-inverted",
        AR,
        "            if share3 > 0.5:",
        "            if share3 < 0.5:  # mutation: 两种解释互换",
        [],
    ),
    (
        "P09-footnote-ok-phrase",
        AR,
        "**不得读作 ok**",
        "**不得读作 okk**  # mutation: 口径句被改写",
        [],
    ),
    (
        "P10-mismatch-note-conditional",
        AR,
        '        if fl_totals["n_reason_mismatch"]:',
        "        if False:  # mutation: 矛盾注永不渲染",
        [],
    ),
    (
        "P11-fl-reason-columns-swapped",
        AR,
        "f\"| {sum(f.get('reason_recorded', {}).values())} | {sum(f.get('reason_inferred', {}).values())} \"",
        "f\"| {sum(f.get('reason_inferred', {}).values())} | {sum(f.get('reason_recorded', {}).values())} \"  # mutation: 两列互换",
        [],
    ),
    # ─── 批次摘要接线 ───────────────────────────────────────────────────
    (
        "M01-summary-prefix-renamed",
        RM,
        "f\"    BV 判定核沉默: hack 已求值 {hack['n_evaluated']}/{hack['n_verdict_recorded']}\"",
        "f\"    BV 判定核: hack 已求值 {hack['n_evaluated']}/{hack['n_verdict_recorded']}\"  # mutation: 摘要不再说沉默",
        [],
    ),
    (
        "M02-summary-hit-ratio-dropped",
        RM,
        "f\"FL 已求值 {flc['n_evaluated']}（hit {flc['n_hit']}/miss {flc['n_miss']}，hit 比 {ratio}）\"",
        "f\"FL 已求值 {flc['n_evaluated']}（hit {flc['n_hit']}/miss {flc['n_miss']}）\"  # mutation: 判别力读数消失",
        [],
    ),
    # ─── 中性对照（仅改 docstring，不动任何判据） ─────────────────────────
    (
        CONTROL,
        ID,
        '"""批次 VIII / XIV 观测层「判定核沉默」的单一事实源（BV 轮，2026-10-23）。',
        '"""**批次 VIII / XIV 观测层「判定核沉默」的单一事实源（BV 轮，2026-10-23）**。',
        [],
    ),
]


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in BROKER_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BASE_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str, list[str]]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BASE_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bv_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    failed = FAILED_RE.findall(output)
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, len(failed), tail, failed


def precheck() -> bool:
    ok = True
    seen: set[str] = set()
    for name, relpath, old, _new, _ in MUTANTS:
        if name in seen:
            print(f"[{name}] DUPLICATE ANCHOR NAME")
            ok = False
        seen.add(name)
        counts = (ROOT / relpath).read_text(encoding="utf-8").count(old)
        if counts != 1:
            print(f"[{name}] PRECHECK anchor count={counts} in {relpath}")
            ok = False
    print(f"[precheck] 锚点唯一性 {'全部通过' if ok else '有失败'}（{len(MUTANTS)} 个）")
    return ok


def main() -> int:
    if not precheck():
        return 1
    rc, red, tail, _ = run_tests([])
    print(f"[baseline] rc={rc} red={red} collected={collect_count([])}\n{tail}")
    if rc != 0 or red != 0:
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
            results.append((name, "ANCHOR-ERROR", -1, []))
            continue
        mutated = text.replace(old, new, 1)
        try:
            compile(mutated, str(path), "exec")
        except SyntaxError as exc:
            print(f"[{name}] MUTATION SYNTAX ERROR: {exc}")
            results.append((name, "SYNTAX-ERROR", -1, []))
            continue
        expected_collected = collect_count(extra)
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail, failed = run_tests(extra)
            mutated_collected = collect_count(extra)
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != expected_collected:
            print(f"[{name}] COLLECTED DRIFT {expected_collected} -> {mutated_collected}")
            results.append((name, "COLLECTED-DRIFT", red, failed))
            continue
        verdict = "FAILED" if rc != 0 else "SURVIVED"
        killers = [f.rsplit("::", 1)[-1] for f in failed[:4]]
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict} 红名={killers}")
        results.append((name, verdict, red, failed))

    print("\n=== SUMMARY ===")
    for name, verdict, red, _failed in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    survivors = [n for n, v, _r, _f in results if v != "FAILED" and n != CONTROL]
    wrong_control = [n for n, v, _r, _f in results if n == CONTROL and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
