#!/usr/bin/env python3
"""BU 轮变异验证：Self-Repair Trap 输入可达域的 61 个锚点 + 1 个中性对照。

纪律（与 BH→BT 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 强调星号）必须 0 红。

锚点方向：每一处都是「把 BU 补的分档/可达域/对账披露退回沉默、退回并档、退回同形」，
其中判定核（`src/tools/self_repair_trap.py`）的三个门槛字面量是 BU 阈值同源锁的靶子。
受影响面 = BU 新锁 + BQ/BT 棘轮 + 表体完整性 + 判定核原有批次锁 + 两个分析套件。
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

ID = "experiments/_trap_input_domain.py"
SA = "experiments/statistical_analysis.py"
AR = "experiments/analyze_results.py"
JU = "src/tools/self_repair_trap.py"
RB = "experiments/run_benchmark.py"

BU_TESTS = [
    "tests/test_trap_input_domain_bu.py",
    "tests/test_bq_check_leg_readers.py",
    "tests/test_oracle_provenance_bt.py",
    "tests/test_markdown_table_integrity.py",
    "tests/test_batch_xiv.py",
    "tests/test_small_gaps_closeout.py",
    "tests/test_experiments_analysis.py",
    "tests/test_batch_ix.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 单一事实源：三档门槛与判定核字面量同源 ─────────────────────────
    (
        "U01-declining-threshold-3to2",
        ID,
        '    "assert_count_declining": 3,',
        '    "assert_count_declining": 2,  # mutation: declining 门槛说成 2',
        [],
    ),
    (
        "U02-collapse-threshold-2to3",
        ID,
        '    "assertion_collapse": 2,',
        '    "assertion_collapse": 3,  # mutation: collapse 门槛说成 3',
        [],
    ),
    (
        "U03-score-threshold-2to3",
        ID,
        '    "mutation_score_declining": 2,',
        '    "mutation_score_declining": 3,  # mutation: score 门槛说成 3',
        [],
    ),
    (
        "U04-global-floor-taken-as-max",
        ID,
        "GLOBAL_MIN_POINTS = min(SIGNAL_MIN_POINTS.values())",
        "GLOBAL_MIN_POINTS = max(SIGNAL_MIN_POINTS.values())  # mutation: 全局门槛取最大",
        [],
    ),
    # ─── 四档分档：每处都是「并档」或「把有记录说成没记录」 ───────────────
    (
        "U05-verdict-false-read-as-unrecorded",
        ID,
        "    if not isinstance(row, dict) or TRAP_VERDICT_KEY not in row:",
        "    if not isinstance(row, dict) or row.get(TRAP_VERDICT_KEY) is not True:  # mutation: False 也说成未记录",
        [],
    ),
    (
        "U06-malformed-merged-into-below-floor",
        ID,
        "        return BUCKET_MALFORMED",
        "        return BUCKET_BELOW_FLOOR  # mutation: 形状不符折进点数不足",
        [],
    ),
    (
        "U07-below-floor-merged-into-floor-reached",
        ID,
        "        return BUCKET_BELOW_FLOOR",
        "        return BUCKET_FLOOR_REACHED  # mutation: 点数不足也说成够",
        [],
    ),
    (
        "U08-floor-reached-merged-into-below",
        ID,
        "    return BUCKET_FLOOR_REACHED",
        "    return BUCKET_BELOW_FLOOR  # mutation: 够点数的也说成不够",
        [],
    ),
    # ─── 取数口径与判定核同源 ─────────────────────────────────────────
    (
        "U09-last-unparsable-snapshot-no-longer-exempts",
        ID,
        """    if not points or points[-1].get("parse_ok") is not True:
        return []""",
        """    if False:  # mutation: 末点不可解析也照算
        return []""",
        [],
    ),
    (
        "U10-counts-ignore-parse-ok",
        ID,
        '    return [int(h.get("assert_count") or 0) for h in points if h.get("parse_ok") is True]',
        "    return [int(h.get('assert_count') or 0) for h in points]  # mutation: 不可解析点也计入",
        [],
    ),
    (
        "U11-bool-counts-as-mutation-score",
        ID,
        "        if isinstance(v, (int, float)) and not isinstance(v, bool):",
        "        if isinstance(v, (int, float)):  # mutation: 布尔也算变异分",
        [],
    ),
    (
        "U12-unreadable-count-folds-into-zero",
        ID,
        '    return [int(h.get("assert_count") or 0) for h in points if h.get("parse_ok") is True]',
        '    return [\n        int(h["assert_count"]) if isinstance(h.get("assert_count"), (int, float)) else 0\n        for h in points\n        if h.get("parse_ok") is True\n    ]  # mutation: 读不懂折成 0',
        [],
    ),
    # ─── 可达域：够不够被判定，说宽/说窄/重打字面量 ──────────────────────
    (
        "U13-declining-domain-widened-to-collapse",
        ID,
        '        "assert_count_declining": len(counts) >= SIGNAL_MIN_POINTS["assert_count_declining"],',
        '        "assert_count_declining": len(counts) >= SIGNAL_MIN_POINTS["assertion_collapse"],  # mutation: 两档并成一档',
        [],
    ),
    (
        "U14-collapse-domain-narrowed-to-declining",
        ID,
        '        "assertion_collapse": len(counts) >= SIGNAL_MIN_POINTS["assertion_collapse"],',
        '        "assertion_collapse": len(counts) >= SIGNAL_MIN_POINTS["assert_count_declining"],  # mutation: collapse 也要 3 点',
        [],
    ),
    (
        "U15-declining-domain-retypes-literal",
        ID,
        '        "assert_count_declining": len(counts) >= SIGNAL_MIN_POINTS["assert_count_declining"],',
        '        "assert_count_declining": len(counts) >= 3,  # mutation: 读侧重打字面量',
        [],
    ),
    # ─── 域外下降：证据判据 ───────────────────────────────────────────
    (
        "U16-flat-count-read-as-decline",
        ID,
        '    return 2 <= len(counts) < SIGNAL_MIN_POINTS["assert_count_declining"] and counts[-1] < counts[-2]',
        '    return 2 <= len(counts) < SIGNAL_MIN_POINTS["assert_count_declining"] and counts[-1] <= counts[-2]  # mutation: 持平也算下降',
        [],
    ),
    (
        "U17-two-point-lower-bound-dropped",
        ID,
        '    return 2 <= len(counts) < SIGNAL_MIN_POINTS["assert_count_declining"] and counts[-1] < counts[-2]',
        '    return len(counts) < SIGNAL_MIN_POINTS["assert_count_declining"] and counts[-1] < counts[-2]  # mutation: 丢掉 2 点下界',
        [],
    ),
    # 注：`two_point_decline_outside_domain` 开头的 `input_bucket(...) != FLOOR_REACHED` 门
    # 不设锚点——首轮实测把它改成 `if False` 后 338 例全绿：`2 <= len(counts)` 的下界已让
    # 未达档的行（0/1 个可解析点）短路为 False，该门是冗余防御、没有任何断能消费它。
    # ─── 判定核字面量：阈值同源锁的靶子（临时改 src/，按原字节还原）──────
    (
        "U19-judge-declining-literal-lowered",
        JU,
        "        if len(counts) >= 3 and counts[-2] < counts[-3] and counts[-1] < counts[-2]:",
        "        if len(counts) >= 2 and counts[-2] < counts[-3] and counts[-1] < counts[-2]:  # mutation: 门槛降到 2",
        [],
    ),
    (
        "U20-judge-collapse-literal-raised",
        JU,
        "        if len(counts) >= 2 and counts[-1] == 0 and any(c > 0 for c in counts[:-1]):",
        "        if len(counts) >= 3 and counts[-1] == 0 and any(c > 0 for c in counts[:-1]):  # mutation: 门槛升到 3",
        [],
    ),
    (
        "U21-judge-score-literal-raised",
        JU,
        "    if len(scores) >= 2 and scores[-1] < scores[0]:",
        "    if len(scores) >= 3 and scores[-1] < scores[0]:  # mutation: 变异分门槛升到 3",
        [],
    ),
    (
        "U22-judge-collapse-gate-reads-another-sequence",
        JU,
        "        if len(counts) >= 2 and counts[-1] == 0 and any(c > 0 for c in counts[:-1]):",
        "        if len(parsed) >= 2 and counts[-1] == 0 and any(c > 0 for c in counts[:-1]):  # mutation: 门槛看的序列换了名",
        [],
    ),
    # ─── 写侧：判定核结论必须逐字透出（BU 不动写入端，此锁防回退）─────────
    (
        "U23-write-side-verdict-hardcoded",
        RB,
        '            "self_repair_trap_suspected": _trap["suspected"],',
        '            "self_repair_trap_suspected": False,  # mutation: 判定核结论不再透出',
        [],
    ),
    (
        "U24-write-side-signals-hardcoded",
        RB,
        '            "self_repair_trap_signals": _trap["signals"],',
        '            "self_repair_trap_signals": [],  # mutation: 信号不再透出',
        [],
    ),
    # ─── 读侧统计：分母、并档、单列 ────────────────────────────────────
    (
        "U25-with-verdict-counts-unrecorded-rows",
        SA,
        '        "n_with_verdict": len(rows) - buckets[BUCKET_NOT_RECORDED],',
        '        "n_with_verdict": len(rows),  # mutation: 缺键行也说成有判定',
        [],
    ),
    (
        "U26-signal-domain-not-preseeded",
        SA,
        "    domain: Counter[str] = Counter({name: 0 for name in SIGNAL_MIN_POINTS})",
        "    domain: Counter[str] = Counter()  # mutation: 空臂不再给出三档零计数",
        [],
    ),
    (
        "U27-verdict-true-never-counted",
        SA,
        """        if bool(row.get(TRAP_VERDICT_KEY)):
            n_verdict_true += 1""",
        """        if False:  # mutation: 开火行数恒报 0
            n_verdict_true += 1""",
        [],
    ),
    (
        "U28-empty-signals-read-as-nonempty",
        SA,
        "        if row.get(TRAP_SIGNALS_KEY):",
        "        if row.get(TRAP_SIGNALS_KEY) is not None:  # mutation: 空列表也说成有信号",
        [],
    ),
    (
        "U29-clean-rows-named-in-mismatch-detail",
        SA,
        "        if flagged:",
        "        if True:  # mutation: 每行都点名",
        [],
    ),
    (
        "U30-mismatch-detail-uncapped",
        SA,
        '        "mismatches": mismatches[:20],',
        '        "mismatches": mismatches,  # mutation: 明细不设上限',
        [],
    ),
    (
        "U31-judge-exception-folded-into-consistent",
        SA,
        """        except Exception:  # —— 判定核抛错 ≠ 与归档一致（同批抛错是调用方 bug 信号）
            n_rerun_error += 1
            continue""",
        """        except Exception:  # mutation: 判定核抛错也说成一致
            continue""",
        [],
    ),
    (
        "U32-judge-unavailable-silenced",
        SA,
        """        if detect_self_repair_trap is None:
            n_rerun_error += 1
            continue""",
        """        if detect_self_repair_trap is None:
            continue  # mutation: 判定核不可导入时整臂沉默""",
        [],
    ),
    (
        "U33-unmeasurable-merged-into-rerun-error",
        SA,
        """        except Exception:  # —— 输入读不懂 ⇒ 单列，不折进任何可达域档
            n_unmeasurable += 1""",
        """        except Exception:  # mutation: 读不懂折进对账异常
            n_rerun_error += 1""",
        [],
    ),
    (
        "U34-reconciled-always-true",
        SA,
        '        "reconciled": detect_self_repair_trap is not None and not n_rerun_error and not n_unmeasurable,',
        '        "reconciled": True,  # mutation: 对账没跑成也说成一致',
        [],
    ),
    (
        "U35-non-dict-rows-enter-bucketing",
        SA,
        """    rows = [r for r in (rows or []) if isinstance(r, dict)]
    buckets: Counter[str] = Counter()""",
        """    rows = list(rows or [])  # mutation: 非 dict 行也进分档
    buckets: Counter[str] = Counter()""",
        [],
    ),
    (
        "U36-domain-counts-rows-outside-domain",
        SA,
        """            for name, in_domain in signal_domains(history).items():
                if in_domain:
                    domain[name] += 1""",
        """            for name in signal_domains(history):
                domain[name] += 1  # mutation: 够不够都计入""",
        [],
    ),
    (
        "U37-outside-domain-never-counted",
        SA,
        """            if two_point_decline_outside_domain(row):
                n_decline2 += 1""",
        """            if False:  # mutation: 域外下降不再披露
                n_decline2 += 1""",
        [],
    ),
    (
        "U38-arms-no-longer-sorted",
        SA,
        "    return {baseline: self_repair_trap_domain_stats(data.get(baseline) or []) for baseline in sorted(data)}",
        "    return {baseline: self_repair_trap_domain_stats(data.get(baseline) or []) for baseline in data}  # mutation: 臂序不再稳定",
        [],
    ),
    # ─── 报告面：接入、渲染、点名、口径脚注 ────────────────────────────
    (
        "U39-wiring-computed-but-not-fed",
        AR,
        '            "self_repair_trap_domain": _trap_domain(details),',
        '            "self_repair_trap_domain": {},  # mutation: 读侧算了但不接入',
        [],
    ),
    (
        "U40-wiring-key-dropped",
        AR,
        '            "self_repair_trap_domain": _trap_domain(details),\n',
        "",
        [],
    ),
    (
        "U41-section-does-not-read-the-key",
        AR,
        '    trap = {b: m.get("self_repair_trap_domain", {}) for b, m in per.items()}',
        "    trap = {}  # mutation: 报告面不接这一路",
        [],
    ),
    (
        "U42-zero-row-arm-rendered",
        AR,
        '    trap_rows = [(b, t) for b, t in trap.items() if t.get("n_rows")]',
        "    trap_rows = list(trap.items())  # mutation: 零行臂也渲染全零表",
        [],
    ),
    (
        "U43-silent-arm-note-always",
        AR,
        "        if silent_arms:",
        "        if True:  # mutation: 没有静默臂也说有",
        [],
    ),
    (
        "U44-silent-arm-note-suppressed",
        AR,
        "        if silent_arms:",
        "        if False:  # mutation: 全臂没落盘也不点名",
        [],
    ),
    (
        "U45-empty-domain-note-suppressed",
        AR,
        '        if not totals["assert_count_declining"]:',
        "        if False:  # mutation: 空集事实不点名",
        [],
    ),
    (
        "U46-empty-domain-note-always",
        AR,
        '        if not totals["assert_count_declining"]:',
        "        if True:  # mutation: 有可达行也说成空集",
        [],
    ),
    (
        "U47-rerun-error-note-suppressed",
        AR,
        '        if totals["n_rerun_error"]:',
        "        if False:  # mutation: 对账异常不披露",
        [],
    ),
    (
        "U48-rerun-error-note-always",
        AR,
        '        if totals["n_rerun_error"]:',
        "        if True:  # mutation: 干净语料也说成有异常",
        [],
    ),
    (
        "U49-arm-row-outside-domain-cell-zeroed",
        AR,
        '''                f"| {dom.get('mutation_score_declining', 0)} | {t.get('n_decline2_outside_domain', 0)} "''',
        """                f"| {dom.get('mutation_score_declining', 0)} | 0 "  # mutation: 臂内域外下降抹零""",
        [],
    ),
    (
        "U50-total-row-outside-domain-cell-zeroed",
        AR,
        """            f"| {totals['mutation_score_declining']} | {totals['n_decline2_outside_domain']} \"""",
        """            f"| {totals['mutation_score_declining']} | 0 "  # mutation: 合计域外下降抹零""",
        [],
    ),
    (
        "U51-arm-row-mismatch-cell-zeroed",
        AR,
        """                f"| {t.get('n_suspected_mismatch', 0)}/{t.get('n_signals_mismatch', 0)} |\"""",
        """                f"| 0/0 |\"  # mutation: 臂内不一致抹零""",
        [],
    ),
    (
        "U52-total-row-mismatch-cell-zeroed",
        AR,
        """            f"| {totals['n_verdict_true']} | {totals['n_suspected_mismatch']}/{totals['n_signals_mismatch']} |\"""",
        """            f"| {totals['n_verdict_true']} | 0/0 |\"  # mutation: 合计不一致抹零""",
        [],
    ),
    (
        "U53-arm-row-fired-cell-zeroed",
        AR,
        """                f"| {t.get('n_verdict_true', 0)} \"""",
        """                f"| 0 "  # mutation: 开火列抹零""",
        [],
    ),
    (
        "U54-table-header-drops-a-column",
        AR,
        """            "| 基线 | 行数 | 有判定 | 未记录 | 历史 null | <2 点 | ≥2 点 | declining 可达 | collapse 可达 | score 可达 | 域外下降 | 开火 | 不一致（判定/信号） |\"""",
        """            "| 基线 | 行数 | 有判定 | 未记录 | 历史 null | <2 点 | ≥2 点 | declining 可达 | collapse 可达 | score 可达 | 开火 | 不一致（判定/信号） |\"  # mutation: 少一列表头""",
        [],
    ),
    (
        "U55-unrecorded-caliber-dropped",
        AR,
        """            "> 口径：`未记录` = 行内没有 `self_repair_trap_suspected` 键（批次早于 ADR-0028），\"""",
        '            ""  # mutation: 未记录口径不再解释',
        [],
    ),
    (
        "U56-malformed-caliber-dropped",
        AR,
        """            "判定核走「结构异常 ⇒ 不怀疑」分支；`<2 点` / `≥2 点` = 历史快照点数。\"""",
        '            ""  # mutation: 形状不符档口径不再解释',
        [],
    ),
    (
        "U57-input-sufficiency-caliber-dropped",
        AR,
        """            "> 三个「可达」列回答的是**输入够不够**，不是判没判出来：\"""",
        '            ""  # mutation: 「输入够不够」口径不再写',
        [],
    ),
    (
        "U58-outside-domain-caliber-dropped",
        AR,
        """            "`域外下降` = 历史确有连续下降但点数低于 declining 门槛（证据存在、判据看不见）。\"""",
        '            ""  # mutation: 域外下降口径不再写',
        [],
    ),
    (
        "U59-footnote-declining-threshold-retyped",
        AR,
        """            f"`declining 可达` 需 ≥{SIGNAL_MIN_POINTS['assert_count_declining']} 个可解析点、\"""",
        """            f"`declining 可达` 需 ≥3 个可解析点、\"  # mutation: 门槛写死""",
        [],
    ),
    (
        "U60-footnote-collapse-threshold-retyped",
        AR,
        """            f"`collapse 可达` 需 ≥{SIGNAL_MIN_POINTS['assertion_collapse']} 个可解析点、\"""",
        """            f"`collapse 可达` 需 ≥2 个可解析点、\"  # mutation: 门槛写死""",
        [],
    ),
    (
        "U61-footnote-score-threshold-retyped",
        AR,
        """            f"`score 可达` 需 ≥{SIGNAL_MIN_POINTS['mutation_score_declining']} 个非 `None` 变异分数。\"""",
        """            f"`score 可达` 需 ≥2 个非 `None` 变异分数。\"  # mutation: 门槛写死""",
        [],
    ),
    (
        "U62-empty-domain-note-threshold-retyped",
        AR,
        """                f"没有任何一行给出 ≥{SIGNAL_MIN_POINTS['assert_count_declining']} 个可解析断言计数\"""",
        """                f"没有任何一行给出 ≥3 个可解析断言计数\"  # mutation: 门槛写死""",
        [],
    ),
    (
        # 中性对照：仅改 docstring 的一处强调星号，不动任何判据 —— 必须 0 红。
        "U63-control-wording",
        SA,
        "    - `n_rerun_error` 单列（重跑抛异常**不算**一致——一批同样的抛错是调用方 bug 信号）；",
        "    - `n_rerun_error` 单列（重跑抛异常不算一致——一批同样的抛错是调用方 bug 信号）；",
        [],
    ),
]

CONTROL = "U63-control-wording"
_COLLECTED_RE = re.compile(r"(\d+) tests collected")
_FAILED_RE = re.compile(r"^FAILED (\S+)", flags=re.MULTILINE)
_BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _BROKER_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BU_TESTS, *paths, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str, list[str]]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BU_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bu_mut",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=900, env=_clean_env())
    output = proc.stdout + proc.stderr
    failed = _FAILED_RE.findall(output)
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
