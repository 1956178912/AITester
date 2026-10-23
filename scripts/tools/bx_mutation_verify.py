#!/usr/bin/env python3
"""BX 轮变异验证：残池两键读侧的 42 个锚点 + 1 个中性对照。

纪律（与 BH→BW 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 强调星号）必须 0 红。

锚点方向：每一处都是「把 BX 补的读侧退回沉默、退回并档、退回同形」：
五层输入域（缺键/材料早退/不可测/暂定池/实测互相并档）、值域（`None` 与 `0`
同形、整数反推的歧义与失败被猜）、两义键 `mdo_pool_floor_ok`、可评估分母与
可评估计数、风险通道的占位（`level` / `pause` / `contract_status` 按真值读）、
报告披露（五层、两义键、全池分母、None≠0、两个口径、外部口径）与批次摘要接线。
受影响面 = BX 新锁（`tests/test_residual_keys_bx.py`）。

外环（判定核 / 写入端）不在本轮变异范围内：BX 只读，`src/` 零改动。
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

RK = "experiments/_residual_keys.py"
AR = "experiments/analyze_results.py"
RM = "experiments/run_main_batch.py"

BASE_TESTS = ["tests/test_residual_keys_bx.py"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)
BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 五层输入域：缺键 / 材料早退 / 不可测 / 暂定池 / 实测 ─────────────────
    (
        "F01-key-absence-folded-into-not-run",
        RK,
        "    if CRASH_KEY not in row:\n        return None",
        "    if CRASH_KEY not in row:\n        return CRASH_NOT_RUN  # mutation: 键缺席并进未跑",
        [],
    ),
    (
        "F02-unavailable-folded-into-measured",
        RK,
        "    if available is False:\n        return CRASH_NOT_MEASURABLE",
        "    if available is False:\n        return CRASH_MEASURED  # mutation: 不可测并进实测",
        [],
    ),
    (
        "F03-material-absent-folded-into-not-run",
        RK,
        "    if isinstance(reason, str) and reason.strip():\n"
        "        return CRASH_MATERIAL_ABSENT\n"
        "    return CRASH_NOT_RUN",
        "    return CRASH_NOT_RUN  # mutation: 材料早退并进未跑",
        [],
    ),
    (
        "F04-provisional-folded-into-measured",
        RK,
        '        return CRASH_PROVISIONAL if row.get("mdo_provisional") is True else CRASH_MEASURED',
        "        return CRASH_MEASURED  # mutation: 暂定池并进实测",
        [],
    ),
    (
        "F05-string-boolean-available-truthy",
        RK,
        "    if available is True:",
        "    if available:  # mutation: 字符串布尔被当成开启",
        [],
    ),
    # ─── 值域：None ≠ 0、整数反推的歧义与失败 ───────────────────────────────
    (
        "F06-pool-size-bool-guard-dropped",
        RK,
        "        isinstance(pool_size, bool)",
        "        isinstance(pool_size, int) and False  # mutation: bool 池规模被当成 1",
        [],
    ),
    (
        "F07-rate-bool-guard-dropped",
        RK,
        "        or isinstance(rate, bool)",
        "        or False  # mutation: bool 速率被当成 1.0",
        [],
    ),
    (
        "F08-ambiguity-takes-first-candidate",
        RK,
        "        if len(cands) != 1:\n            ambiguous += 1\n            continue",
        "        if len(cands) != 1:\n            ambiguous += 1  # mutation: 歧义也取第一个候选",
        [],
    ),
    (
        "F09-failure-counted-as-zero",
        RK,
        "        if cands is None:\n            failed += 1\n            continue",
        "        if cands is None:\n            failed += 1\n            cands = [0]  # mutation: 失败按 0 计入",
        [],
    ),
    (
        "F10-measured-zero-dropped",
        RK,
        "    values = [float(r[CRASH_KEY]) for r in measured if isinstance(r[CRASH_KEY], (int, float))]",
        "    values = [\n"
        "        float(r[CRASH_KEY])\n"
        "        for r in measured\n"
        "        if isinstance(r[CRASH_KEY], (int, float)) and r[CRASH_KEY]\n"
        "    ]  # mutation: 实测 0 被当成未测",
        [],
    ),
    (
        "F11-null-values-counted-zero",
        RK,
        '        "n_value_null": len(present) - len(values),',
        '        "n_value_null": 0,  # mutation: 空值计数抹平',
        [],
    ),
    (
        "F12-empty-value-summary-zeroed",
        RK,
        '        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}',
        '        return {"n": 0, "mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}  # mutation: 空列写成 0',
        [],
    ),
    (
        "F13-mean-precision-coarsened",
        RK,
        '        "mean": round(statistics.mean(values), 6),',
        '        "mean": round(statistics.mean(values), 2),  # mutation: 均值精度降到 2 位',
        [],
    ),
    # ─── 两义键 / 可评估分母 / 输入域计数 ──────────────────────────────────
    (
        "F14-floor-false-other-erased",
        RK,
        '        "floor_false_other": floor_false - floor_false_provisional,',
        '        "floor_false_other": 0,  # mutation: 两义键只剩暂定池',
        [],
    ),
    (
        "F15-reasons-counted-for-all-layers",
        RK,
        "        if layer in CRASH_UNMEASURED_LAYERS:",
        "        if True:  # mutation: 实测/暂定池的 reason 也计数",
        [],
    ),
    (
        "F16-evaluability-recorded-all-rows",
        RK,
        '        "n_evaluability_recorded": sum(1 for r in present if any(k in r for k in MDO_EVALUABILITY_KEYS)),',
        '        "n_evaluability_recorded": len(present),  # mutation: 可评估计数按在场行数',
        [],
    ),
    (
        "F17-provisional-missing-counts-false",
        RK,
        '        "provisional_flag_missing": sum(1 for r in present if r.get("mdo_provisional") is None),',
        '        "provisional_flag_missing": sum(1 for r in present if r.get("mdo_provisional") is not True),'
        "  # mutation: False 也算缺失",
        [],
    ),
    # ─── risk_summary：通道占位与在场判定 ──────────────────────────────────
    (
        "F18-enabled-missing-folded-into-false",
        RK,
        "        elif flag is False:",
        "        elif True:  # mutation: enabled 缺席并进关闭",
        [],
    ),
    (
        "F19-mismatch-drops-factors-and-reasons",
        RK,
        '            if any(doc.get(k) is not None for k in RISK_PLACEHOLDER_FIELDS) or doc.get("factors") or doc.get("reasons"):',
        "            if any(doc.get(k) is not None for k in RISK_PLACEHOLDER_FIELDS):"
        "  # mutation: factors/reasons 的残留不再点名",
        [],
    ),
    (
        "F20-mismatch-double-counted",
        RK,
        "                placeholder_mismatch += 1",
        "                placeholder_mismatch += 2  # mutation: 每行重复计数",
        [],
    ),
    (
        "F21-pause-other-folded-into-false",
        RK,
        '            pause["other"] += 1',
        '            pause["false"] += 1  # mutation: 非布尔 pause 并进 false',
        [],
    ),
    (
        "F22-contract-status-by-truthiness",
        RK,
        "        if RISK_CONTRACT_STATUS_KEY in doc:",
        "        if doc.get(RISK_CONTRACT_STATUS_KEY):  # mutation: 按真值判在场",
        [],
    ),
    (
        "F23-level-on-disabled-read-as-readable",
        RK,
        '    levels_nonnull = sum(1 for doc in docs if doc.get("enabled") is True and doc.get("risk_level") is not None)',
        '    levels_nonnull = sum(1 for doc in docs if doc.get("risk_level") is not None)'
        "  # mutation: 关闭行的残留 level 也算可读",
        [],
    ),
    (
        "F24-schema-shapes-merged",
        RK,
        '        key = "|".join(sorted(doc))',
        '        key = "keys"  # mutation: 形状不再按键集区分',
        [],
    ),
    (
        "F25-distribution-readable-always-true",
        RK,
        '        "distribution_readable": shape["enabled_true"] > 0,',
        '        "distribution_readable": True,  # mutation: 无开启行也算可读',
        [],
    ),
    # ─── 报告面：标题 / 表头 / 披露句 / 外部口径 ────────────────────────────
    (
        "P01-heading-renamed",
        AR,
        '        lines.append("## 写而不读键池的收口（BX：`risk_summary` 与 `mdo_crash_rate` 的读侧）")',
        '        lines.append("## 写而不读键池的收口")  # mutation: 章节名不再区分读侧',
        [],
    ),
    (
        "P02-risk-header-drops-enabled-true",
        AR,
        '            "| 基线 | 行数 | risk 在场 | 键缺席 | enabled=True | enabled=False | 7 键形状 | 6 键形状 | 其它形状 "',
        '            "| 基线 | 行数 | risk 在场 | 键缺席 | enabled=False | 7 键形状 | 6 键形状 | 其它形状 "'
        "  # mutation: 掉 enabled=True 列",
        [],
    ),
    (
        "P03-crash-header-drops-provisional",
        AR,
        '            "| 基线 | 行数 | 未跑 | 材料缺 | 不可测 | 暂定池 | 实测 | 值非空 | 值=0 | 值≠0 "',
        '            "| 基线 | 行数 | 未跑 | 材料缺 | 不可测 | 实测 | 值非空 | 值=0 | 值≠0 "  # mutation: 掉暂定池列',
        [],
    ),
    (
        "P04-level-none-is-not-low-phrase",
        AR,
        "            f\"{risk_totals['level_nonnull']} 行。**`level=None` 不是 `low`**，\"",
        "            f\"{risk_totals['level_nonnull']} 行。\"  # mutation: level=None 与 low 同形",
        [],
    ),
    (
        "P05-pause-is-not-a-judgment-phrase",
        AR,
        '            "`pause_requested=False` 也不是「判定无需暂停」（通道关闭时它恒为 False）。"',
        '            "`pause_requested=False` 即「判定无需暂停」。"  # mutation: 关闭态写成判定',
        [],
    ),
    (
        "P06-nist-caliber-removed",
        AR,
        '            "外部口径（BX 联网核对）：NIST SP 800-30 的风险等级是半定量分箱映射出的"',
        '            "外部口径：风险等级是分箱映射出的"  # mutation: 外部口径来源消失',
        [],
    ),
    (
        "P07-floor-false-two-meaning-phrase",
        AR,
        "            f\"> `mdo_pool_floor_ok=False` 是**两义键**：{mdo_totals['floor_false']} 行 = 暂定池 \"",
        '            f"> `mdo_pool_floor_ok=False` 行 = 暂定池 "  # mutation: 两义键披露消失',
        [],
    ),
    (
        "P08-denominator-claims-evaluable",
        AR,
        '            "> 分母口径：crash 率 = `crashed / 全池 n`（`src/measurement/mdo.py` 的 CRASH 行；"',
        '            "> 分母口径：crash 率 = `crashed / 可评估 n`（`src/measurement/mdo.py` 的 CRASH 行；"'
        "  # mutation: 分母换成可评估",
        [],
    ),
    (
        "P09-none-is-not-zero-phrase",
        AR,
        '            "未测或被出口拦截——**`None` 不是 0**。同一批的逐行均值 "',
        '            "未测或被出口拦截。同一批的逐行均值 "  # mutation: None 与 0 同形',
        [],
    ),
    (
        "P10-raw-values-merged-phrase",
        AR,
        "**不与实测合并**",
        "**与实测合并**  # mutation: 暂定池原始值并进实测",
        [],
    ),
    (
        "P11-google-play-caliber-removed",
        AR,
        '            "外部口径（BX 联网核对）：Google Play `vitals.crashrate` 以去重用户数归一化并明确"',
        '            "外部口径：crash 率按行归一化并明确"  # mutation: 外部口径来源消失',
        [],
    ),
    (
        "P12-ratio-helper-one-decimal",
        AR,
        '    return f"{numerator / denominator:.2%}" if denominator else "—"',
        '    return f"{numerator / denominator:.1%}" if denominator else "—"  # mutation: 千分数降到一位',
        [],
    ),
    (
        "P13-section-renders-without-rows",
        AR,
        "    if residual_rows:",
        "    if True:  # mutation: 无行的基线也渲染章节",
        [],
    ),
    (
        "P14-contract-presence-hardcoded",
        AR,
        "            f\"{risk_totals['contract_present']} 行出现 ⇒「缺失符号为空可不可信」在归档上无证据。\"",
        '            "0 行出现 ⇒「缺失符号为空可不可信」在归档上无证据。"  # mutation: 在场数硬编码 0',
        [],
    ),
    # ─── 批次摘要接线 ────────────────────────────────────────────────────
    (
        "M01-summary-prefix-renamed",
        RM,
        "                f\"    BX 残池: risk 通道开启 {rk['enabled']['enabled_true']}/{rk['n_key_present']}\"",
        "                f\"    BX 残池: {rk['enabled']['enabled_true']}/{rk['n_key_present']}\""
        "  # mutation: 摘要不再说通道",
        [],
    ),
    (
        "M02-summary-raw-count-erased",
        RM,
        "                f\"＋暂定池 {layers['provisional_pool']}（raw {mc['provisional_raw']['n_present']}）；\"",
        "                f\"＋暂定池 {layers['provisional_pool']}（raw 0）；\"  # mutation: 原始值读数抹平",
        [],
    ),
    (
        "M03-summary-key-absence-dropped",
        RM,
        "                f\"不可测 {layers['not_measurable']}；键缺席 {mc['n_key_absent']}\"",
        "                f\"不可测 {layers['not_measurable']}\"  # mutation: 键缺席不再披露",
        [],
    ),
    (
        "M04-summary-never-prints",
        RM,
        '        if res["n_rows"]:',
        "        if False:  # mutation: 摘要行永不打印",
        [],
    ),
    # ─── 中性对照（仅改 docstring，不动任何判据） ─────────────────────────
    (
        CONTROL,
        RK,
        '"""BX 轮（2026-10-23）：写而不读键池最后两键',
        '"""**BX 轮（2026-10-23）：写而不读键池最后两键',
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
        "--basetemp=/tmp/pt_bx_mut",
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
