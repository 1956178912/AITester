#!/usr/bin/env python3
"""BW 轮变异验证：补丁接收链读侧的 68 个锚点 + 1 个中性对照。

纪律（与 BH→BV 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 强调星号）必须 0 红。

锚点方向：每一处都是「把 BW 补的读侧退回沉默、退回并档、退回同形」：
判定原语（缺席读成 0、无 gold 读成判错、未知档并进已知档、无可抑制对象
并进可抑制、无输入并进未验证）、统计分档（分母/并集/gold/覆盖率/选择性风险、
两处不一致计数、信号域 null 与缺席）、报告披露（三分母、审计句、工件注记、
外部口径）与批次摘要接线。受影响面 = BW 新锁（`tests/test_patch_acceptance_bw.py`）。

外环（判定核）不在本轮变异范围内：BW 只读，不改判定核。
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

PA = "experiments/_patch_acceptance.py"
SA = "experiments/statistical_analysis.py"
AR = "experiments/analyze_results.py"
RM = "experiments/run_main_batch.py"

BASE_TESTS = ["tests/test_patch_acceptance_bw.py"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)
BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 判定原语：折叠 / 缺席 / 三档拆分 ────────────────────────────────
    (
        "F01-flag-false-folded-true",
        PA,
        "        return 1 if value else 0",
        "        return 1  # mutation: False 也折叠成真",
        [],
    ),
    (
        "F02-flag-true-strings-dropped",
        PA,
        '_TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})',
        "_TRUE_STRINGS = frozenset()  # mutation: 字符串真值不再识别",
        [],
    ),
    (
        "F03-flag-false-strings-dropped",
        PA,
        '_FALSE_STRINGS = frozenset({"0", "false", "no", "off"})',
        "_FALSE_STRINGS = frozenset()  # mutation: 字符串假值不再识别",
        [],
    ),
    (
        "F04-plausible-missing-read-as-zero",
        PA,
        "    if PLAUSIBLE_KEY not in row:\n        return None",
        "    if PLAUSIBLE_KEY not in row:\n        return 0  # mutation: 缺键读成 0",
        [],
    ),
    (
        "F05-correct-missing-read-as-zero",
        PA,
        "    if CORRECT_KEY not in row:\n        return None",
        "    if CORRECT_KEY not in row:\n        return 0  # mutation: 缺键读成 0",
        [],
    ),
    (
        "F06-no-gold-read-as-gold-incorrect",
        PA,
        "    if REPAIR_RATE_KEY not in row or row.get(REPAIR_RATE_KEY) is None:\n        return CORRECT_NO_GOLD",
        "    if REPAIR_RATE_KEY not in row or row.get(REPAIR_RATE_KEY) is None:\n"
        "        return CORRECT_GOLD_INCORRECT  # mutation: 没测读成判错",
        [],
    ),
    (
        "F07-precision-accepts-bool",
        PA,
        "    if isinstance(value, bool) or not isinstance(value, int | float):",
        "    if not isinstance(value, int | float):  # mutation: bool 被当成数值",
        [],
    ),
    (
        "F08-precision-zero-denominator-becomes-zero",
        PA,
        "    if denom in (None, 0) or numer is None:\n        return None\n    return numer / denom",
        "    if denom is None or numer is None:\n        return None\n"
        "    return (numer / denom) if denom else 0.0  # mutation: 无分母写成 0",
        [],
    ),
    (
        "F09-mismatch-both-none-reads-consistent",
        PA,
        "    if stored is None or expected is None:\n        return stored is not None or expected is not None",
        "    if stored is None or expected is None:\n        return False  # mutation: 一方缺席也算一致",
        [],
    ),
    (
        "F10-evidence-missing-read-as-no-state",
        PA,
        "    if EVIDENCE_KEY not in row:\n        return EVIDENCE_UNRECORDED",
        "    if EVIDENCE_KEY not in row:\n        return EVIDENCE_NO_STATE  # mutation: 未记录折成无状态",
        [],
    ),
    (
        "F11-evidence-non-mapping-folded",
        PA,
        '        return EVIDENCE_OTHER_PREFIX + "non_mapping"',
        "        return EVIDENCE_NO_PATCH  # mutation: 非映射并进无补丁",
        [],
    ),
    (
        "F12-evidence-plausible-bases-drop-one",
        PA,
        "EVIDENCE_PLAUSIBLE_BASES = frozenset({EVIDENCE_APPLIED, EVIDENCE_APPLIED_THEN_REJECTED})",
        "EVIDENCE_PLAUSIBLE_BASES = frozenset({EVIDENCE_APPLIED})  # mutation: 少一个接受档",
        [],
    ),
    (
        "F13-evidence-mismatch-unknown-counted",
        PA,
        "    if value is None or expected is None:\n        return False",
        "    if value is None or expected is None:\n        return value != expected  # mutation: 未知档也判矛盾",
        [],
    ),
    (
        "F14-invariant-recomputed-uses-or",
        PA,
        "    return numer == 1 and denom == 0",
        "    return numer == 1 or denom == 0  # mutation: 不变量方向放宽",
        [],
    ),
    (
        "F15-invariant-flag-missing-read-as-false",
        PA,
        "    if INVARIANT_KEY not in row:\n        return None",
        "    if INVARIANT_KEY not in row:\n        return 0  # mutation: 键缺席读成未违反",
        [],
    ),
    (
        "F16-patch-presence-ignores-whitespace",
        PA,
        '    return bool(str(row.get(PATCH_KEY) or "").strip())',
        "    return PATCH_KEY in row  # mutation: 空串也算有补丁",
        [],
    ),
    (
        "F17-abstain-passed-no-patch-folded",
        PA,
        "    if passed:\n        return ABSTAIN_PASSED_NO_PATCH",
        "    if passed:\n        return ABSTAIN_PASSED_WITH_PATCH  # mutation: 无补丁并进有补丁",
        [],
    ),
    (
        "F18-abstain-applicable-always-true",
        PA,
        "    return abstain_bucket(row) != ABSTAIN_FAILED_NO_PATCH",
        "    return True  # mutation: 失败且无补丁也算可抑制",
        [],
    ),
    (
        "F19-abstain-signals-non-list-guessed",
        PA,
        "    if not isinstance(raw, list):\n        return []",
        "    if not isinstance(raw, list):\n        return [str(raw)]  # mutation: 非列表也猜一个信号",
        [],
    ),
    (
        "F20-abstain-signals-keep-non-strings",
        PA,
        "    return [str(item) for item in raw]",
        "    return list(raw)  # mutation: 非字符串项不再规整",
        [],
    ),
    (
        "F21-signal-vocab-hardcoded-drops-one",
        PA,
        "    return patch_abstain_signal_names()",
        "    return patch_abstain_signal_names()[:-1]  # mutation: 词表少一项",
        [],
    ),
    (
        "F22-validation-null-level-counted",
        PA,
        "            if value is not None:\n                available.append(name)",
        "            if True:  # mutation: None 也算输入\n                available.append(name)",
        [],
    ),
    (
        "F23-validation-non-mapping-counted",
        PA,
        "        elif isinstance(value, Mapping):",
        "        elif True:  # mutation: 非映射也计入输入",
        [],
    ),
    (
        "F24-verdict-missing-read-as-not-applicable",
        PA,
        '    if VALIDATE_VERDICT_KEY not in row:\n        return "unrecorded"',
        '    if VALIDATE_VERDICT_KEY not in row:\n        return "not_applicable"  # mutation: 未记录折成不适用',
        [],
    ),
    (
        "F25-validated-missing-read-as-zero",
        PA,
        "    if VALIDATED_KEY not in row:\n        return None",
        "    if VALIDATED_KEY not in row:\n        return 0  # mutation: 缺键读成未验证",
        [],
    ),
    # ─── 统计分档：分母 / 并集 / 两处不一致 / 信号域 ─────────────────────
    (
        "S01-acceptance-recorded-by-one-key",
        SA,
        "        if all(key in row for key in (PLAUSIBLE_KEY, CORRECT_KEY, PRECISION_KEY)):",
        "        if PLAUSIBLE_KEY in row:  # mutation: 只凭一个键就算已记录",
        [],
    ),
    (
        "S02-no-gold-folded-into-gold-incorrect",
        SA,
        "            if status == CORRECT_NO_GOLD:",
        "            if False:  # mutation: 无 gold 并进判错",
        [],
    ),
    (
        "S03-invariant-flag-missing-not-split",
        SA,
        '                if flag_value is None:\n                    invariant["flag_missing"] += 1',
        '                if False:  # mutation: 键缺席不再单列\n                    invariant["flag_missing"] += 1',
        [],
    ),
    (
        "S04-invariant-unrecorded-not-counted",
        SA,
        '            if INVARIANT_KEY not in row:\n                invariant["flag_unrecorded"] += 1',
        '            if False:  # mutation: 键未落盘不再计数\n                invariant["flag_unrecorded"] += 1',
        [],
    ),
    (
        "S05-evidence-other-counted-recorded",
        SA,
        '        if basis != EVIDENCE_UNRECORDED and not basis.startswith("other:"):',
        "        if basis != EVIDENCE_UNRECORDED:  # mutation: 词表外档也算已记录",
        [],
    ),
    (
        "S06-plausible-without-evidence-not-counted",
        SA,
        "        if plausible(row) == 1 and basis == EVIDENCE_UNRECORDED:",
        "        if False:  # mutation: 无证据的 plausible 不再点名",
        [],
    ),
    (
        "S07-no-effect-folded-into-actionable",
        SA,
        "                if not abstain_applicable(row):",
        "                if False:  # mutation: 无可抑制对象并进可抑制",
        [],
    ),
    (
        "S08-suppressed-gold-denominator-mixed",
        SA,
        "    n_gold_suppressed = (\n"
        "        n_suppressed - suppressed_status.get(CORRECT_NO_GOLD, 0) - suppressed_status.get(CORRECT_UNRECORDED, 0)\n"
        "    )",
        "    n_gold_suppressed = n_suppressed  # mutation: 分母混进无 gold 与未记录",
        [],
    ),
    (
        "S09-signal-domain-null-read-as-recorded",
        SA,
        '                elif row.get(name) is None:\n                    signal_domain[name]["null"] += 1',
        '                elif False:  # mutation: null 并进已记录\n                    signal_domain[name]["null"] += 1',
        [],
    ),
    (
        "S10-abstain-mismatch-not-counted",
        SA,
        '            if bool(recomputed.get("abstain")) != (abstained_flag == 1):',
        "            if False:  # mutation: 弃权不一致不点名",
        [],
    ),
    (
        "S11-signal-mismatch-not-counted",
        SA,
        '            if list(recomputed.get("signals") or []) != signals:',
        "            if False:  # mutation: 信号不一致不点名",
        [],
    ),
    (
        "S12-no-input-folded-into-unvalidated",
        SA,
        "            if validated_flag == 0 and not inputs:",
        "            if not inputs:  # mutation: 无输入都算未验证且无输入",
        [],
    ),
    (
        "S13-validated-mismatch-not-counted",
        SA,
        '            if bool(recomputed.get("validated")) != (validated_flag == 1):',
        "            if False:  # mutation: 验证不一致不点名",
        [],
    ),
    (
        "S14-verdict-mismatch-not-counted",
        SA,
        '            if verdict != "not_applicable" and recomputed.get("verdict") != verdict:',
        "            if False:  # mutation: 判定不一致不点名",
        [],
    ),
    (
        "S15-filtered-success-drops-conditions",
        SA,
        "                if filtered_success(row):",
        "                if flag(row.get(PASSED_KEY)) == 1:  # mutation: 丢弃弃权与验证",
        [],
    ),
    (
        "S16-union-denominator-drops-corrections",
        SA,
        "                    n_correct / (n_plausible + n_implausible_correct) if (n_plausible + n_implausible_correct) else None",
        "                    n_correct / n_plausible if n_plausible else None  # mutation: 并集退回升集",
        [],
    ),
    (
        "S17-gold-precision-denominator-all-plausible",
        SA,
        '                "gold_value": (n_gold_correct / n_plausible_gold) if n_plausible_gold else None,',
        '                "gold_value": (n_gold_correct / n_plausible) if n_plausible else None,  # mutation: 分母不剔无 gold',
        [],
    ),
    (
        "S18-coverage-denominator-all-rows",
        SA,
        '                "value": (n_plausible / n_acceptance_recorded) if n_acceptance_recorded else None,',
        '                "value": (n_plausible / len(rows)) if rows else None,  # mutation: 分母混进未记录行',
        [],
    ),
    (
        "S19-selective-risk-denominator-gold",
        SA,
        '                "value": (n_plausible_incorrect / n_plausible) if n_plausible else None,',
        '                "value": (n_plausible_incorrect / n_plausible_gold) if n_plausible_gold else None,'
        "  # mutation: 风险分母换成 gold",
        [],
    ),
    (
        "S20-precision-value-uses-correct",
        SA,
        '                "value": (n_plausible_correct / n_plausible) if n_plausible else None,',
        '                "value": (n_correct / n_plausible) if n_plausible else None,  # mutation: 分子换成全部判对',
        [],
    ),
    (
        "S21-correct-rate-mismatch-not-counted",
        SA,
        "            if (value_c == 1 and rate != 1.0) or (value_c == 0 and rate == 1.0):",
        "            if False:  # mutation: 判定与 repair_rate 的不一致不点名",
        [],
    ),
    (
        "S22-precision-mismatch-not-counted",
        SA,
        "            if precision_mismatch(row):",
        "            if False:  # mutation: 行内精确率不一致不点名",
        [],
    ),
    (
        "S23-unknown-signals-counted-as-known",
        SA,
        "    n_unknown_signals = sum(count for name, count in signal_counts.items() if name not in signal_names)",
        "    n_unknown_signals = sum(signal_counts.values())  # mutation: 全部信号都算词表外",
        [],
    ),
    (
        "S24-other-evidence-counted-as-whole",
        SA,
        '    n_other_evidence = sum(count for basis, count in evidence_counts.items() if basis.startswith("other:"))',
        "    n_other_evidence = sum(evidence_counts.values())  # mutation: 全部证据都算其它",
        [],
    ),
    # ─── 报告面：标题 / 表头 / 三分母 / 审计句 / 外部口径 ────────────────
    (
        "P01-heading-renamed",
        AR,
        'lines.append("## 补丁接收链的覆盖率与分母（BW：`patch_precision` / 证据 / 弃权 / 验证的读侧）")',
        'lines.append("## 补丁接收链")  # mutation: 章节名不再区分读侧',
        [],
    ),
    (
        "P02-acceptance-header-drops-column",
        AR,
        '            "| 基线 | 行数 | 接收链已记录 | plausible | correct | 交 | 接受集判错 | 排除集判对 | 接受集无 gold | 精确率 | 并集精确率 | gold 精确率 | 覆盖率 | 选择性风险 |"',
        '            "| 基线 | 行数 | 接收链已记录 | plausible | correct | 交 | 接受集判错 | 排除集判对 | 接受集无 gold | 精确率 | 并集精确率 | gold 精确率 | 覆盖率 |"'
        "  # mutation: 掉选择性风险列",
        [],
    ),
    (
        "P03-selective-risk-denominator-all-rows",
        AR,
        "f\"| {_ratio_text(a.get('n_plausible_incorrect', 0), n_p)} |\"",
        "f\"| {_ratio_text(a.get('n_plausible_incorrect', 0), n_rec)} |\"  # mutation: 风险分母换成已记录",
        [],
    ),
    (
        "P04-three-precisions-phrase",
        AR,
        '"> 三个精确率是三个分母，不是三个估计：`精确率` = 交 / plausible（存储的 `patch_precision` 口径）；"',
        '"> 三个精确率：`精确率` = 交 / plausible（存储的 `patch_precision` 口径）；"  # mutation: 分母口径句消失',
        [],
    ),
    (
        "P05-precision-none-phrase",
        AR,
        '"`patch_precision=None` 当且仅当 `plausible=0`（无分母），**不得读作 0，也不得读作「无 gold」**。"',
        '"`patch_precision=None` 当且仅当 `plausible=0`（无分母），**不得读作 0**。"  # mutation: 无 gold 口径消失',
        [],
    ),
    (
        "P06-correct-zero-not-an-error-phrase",
        AR,
        '"后者是写侧在无 gold 时的保守取值，**不是判错**。`correct=1 ∧ plausible=0` 的 "',
        '"后者也是判错。`correct=1 ∧ plausible=0` 的 "  # mutation: 没测写成判错',
        [],
    ),
    (
        "P07-invariant-absence-phrase",
        AR,
        '"缺席不得读作「未违反」——该布尔键不能当完整性信号用。"',
        '"缺席即未违反——该布尔键可当完整性信号用。"  # mutation: 缺席读成通过',
        [],
    ),
    (
        "P08-legacy-cohort-phrase",
        AR,
        '"（早于 R53），**不等于**「plausible=0」；弃权/证据/验证三组各自的未记录数见下表。"',
        '"（早于 R53），即「plausible=0」；弃权/证据/验证三组各自的未记录数见下表。"  # mutation: 未记录读成 0',
        [],
    ),
    (
        "P09-abstain-two-denominators-phrase",
        AR,
        '"——两个数都要报，后者把 18 行无 gold 材料记为「非错误」。"',
        '"——只报前者。"  # mutation: 第二个分母不再披露',
        [],
    ),
    (
        "P10-unvalidated-not-failed-phrase",
        AR,
        '"不得读作「未验证」）。`unvalidated` ≠ 「验证过且失败」：其中 "',
        '"不得读作「未验证」）。`unvalidated` = 「验证过且失败」：其中 "  # mutation: 未验证读成失败',
        [],
    ),
    (
        "P11-input-reachability-phrase",
        AR,
        '"——两个最强输入在整个归档里**可达域为空**，`validated=True` 全部来自最弱的证据档。"',
        '"——两个最强输入可用，`validated=True` 来自证据档。"  # mutation: 可达域为空不再披露',
        [],
    ),
    (
        "P12-artifact-caveat-phrase",
        AR,
        '"修正口径以 `make repair-replay` 的回放为准（本轮**未重跑**回放，不改写任何行）。"',
        '"修正口径以 `make repair-replay` 的回放为准。"  # mutation: 回放未重跑的事实消失',
        [],
    ),
    (
        "P13-abstention-caliber-phrase",
        AR,
        '            "覆盖率为 0 时风险是**未定义**，不得写成 0。弃权精确率按「弃权决策中确实该弃权的占比」读，"',
        '            "覆盖率为 0 时风险是**未定义**，不得写成 0。"  # mutation: 弃权精确率口径消失',
        [],
    ),
    (
        "P14-ratio-helper-zero-becomes-zero-percent",
        AR,
        '    return f"{numerator / denominator:.1%}" if denominator else "—"',
        '    return f"{numerator / denominator:.1%}" if denominator else "0.0%"  # mutation: 无分母写成 0%',
        [],
    ),
    (
        "P15-signal-domain-drops-one-name",
        AR,
        "                for name, counter in sig_domain.items()",
        "                for name, counter in list(sig_domain.items())[:-1]  # mutation: 信号域少一项",
        [],
    ),
    # ─── 批次摘要接线 ───────────────────────────────────────────────────
    (
        "M01-summary-prefix-renamed",
        RM,
        "f\"    BW 补丁接收链: 已记录 {acc_a['n_recorded']}/{acc['n_rows']}，\"",
        "f\"    BW 补丁接收链: {acc_a['n_recorded']}/{acc['n_rows']}，\"  # mutation: 摘要不再说已记录",
        [],
    ),
    (
        "M02-summary-no-gold-dropped",
        RM,
        "f\"plausible {acc_a['n_plausible']}（无 gold {acc_a['n_plausible_no_gold']}）\"",
        "f\"plausible {acc_a['n_plausible']}\"  # mutation: 无 gold 分母消失",
        [],
    ),
    (
        "M03-summary-filtered-denominator",
        RM,
        "f\"filtered success {acc_va['n_filtered_success']}/{acc_va['n_passed']}\"",
        "f\"filtered success {acc_va['n_filtered_success']}/{acc_va['n_recorded']}\"  # mutation: 分母换成已验证行",
        [],
    ),
    # ─── 中性对照（仅改 docstring，不动任何判据） ─────────────────────────
    (
        CONTROL,
        PA,
        '"""补丁接收链的单一事实源（BW 轮，2026-10-23）。',
        '"""**补丁接收链的单一事实源（BW 轮，2026-10-23）**。',
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
        "--basetemp=/tmp/pt_bw_mut",
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
