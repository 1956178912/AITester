#!/usr/bin/env python3
"""BT 轮变异验证：验收 oracle 来源与可见性的 48 个锚点 + 1 个中性对照。

纪律（与 BH→BQ 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 措辞）必须 0 红。

锚点方向：每一处都是「把 BT 补的取值/披露退回说反、退回沉默、退回同形」。
受影响面 = BT 新锁 + BQ 键集棘轮 + 两个分析套件。
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

RB = "experiments/run_benchmark.py"
SA = "experiments/statistical_analysis.py"
AR = "experiments/analyze_results.py"
OP = "experiments/_oracle_provenance.py"

BT_TESTS = [
    "tests/test_oracle_provenance_bt.py",
    "tests/test_bq_check_leg_readers.py",
    "tests/test_experiments_analysis.py",
    "tests/test_batch_ix.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 写入端：描述符的六个静态条件 ───────────────────────────────────
    (
        "T01-gold-claims-visible",
        RB,
        "        return ORACLE_TYPE_REPO_GOLD, False",
        "        return ORACLE_TYPE_REPO_GOLD, True  # mutation: 仓库级验收也说成可见",
        [],
    ),
    (
        "T02-gold-label-collapsed",
        RB,
        "        return ORACLE_TYPE_REPO_GOLD, False",
        "        return ORACLE_TYPE_GENERATED, False  # mutation: 仓库级验收说成生成测试",
        [],
    ),
    (
        "T03-baseline-term-widened",
        RB,
        """        baseline == "aitester"
        and bool(REPO_LEVEL_EXECUTION)""",
        """        baseline in ("aitester", "plain_llm")
        and bool(REPO_LEVEL_EXECUTION)  # mutation: 非 aitester 臂也说 gold""",
        [],
    ),
    (
        "T04-exec-switch-ignored",
        RB,
        """        baseline == "aitester"
        and bool(REPO_LEVEL_EXECUTION)
""",
        """        baseline == "aitester"
""",
        [],
    ),
    (
        "T05-source-term-ignored",
        RB,
        """        and metadata.get("source") == "swe_bench"
""",
        "",
        [],
    ),
    (
        "T06-f2p-term-ignored",
        RB,
        """        and bool(metadata.get("fail_to_pass"))
""",
        "",
        [],
    ),
    (
        "T07-repo-url-term-ignored",
        RB,
        """        and bool(metadata.get("repo_url"))
""",
        "",
        [],
    ),
    (
        "T08-base-commit-term-ignored",
        RB,
        """        and bool(metadata.get("base_commit"))
""",
        "",
        [],
    ),
    (
        "T09-metadata-fallback-dropped",
        RB,
        '    metadata = getattr(task, "metadata", None) or {}',
        '    metadata = getattr(task, "metadata", None)  # mutation: 不再兜 metadata=None',
        [],
    ),
    (
        "T10-enhanced-label-collapsed",
        RB,
        "            return ORACLE_TYPE_ENHANCED",
        "            return ORACLE_TYPE_GENERATED  # mutation: 增强档说成生成档",
        [],
    ),
    # ─── 写入端：五个构造点的接线（只改助手不算修好）────────────────────
    (
        "T11-wire-harness-invalid",
        RB,
        """                    harness_invalid=True,
                    oracle=_oracle_descriptor(task, baseline, None),
""",
        """                    harness_invalid=True,
""",
        [],
    ),
    (
        "T12-wire-success",
        RB,
        """                    harness_invalid=_harness_invalid,
                    oracle=_oracle_descriptor(task, baseline, final_state),
""",
        """                    harness_invalid=_harness_invalid,
""",
        [],
    ),
    (
        "T13-wire-retry-success",
        RB,
        """                        harness_invalid=_harness_invalid,
                        oracle=_oracle_descriptor(task, baseline, final_state),
""",
        """                        harness_invalid=_harness_invalid,
""",
        [],
    ),
    (
        "T14-wire-rate-limit",
        RB,
        """                        harness_invalid=_harness_invalid,
                        oracle=_oracle_descriptor(task, baseline, None),
""",
        """                        harness_invalid=_harness_invalid,
""",
        [],
    ),
    (
        "T15-wire-error",
        RB,
        """                    harness_invalid=_harness_invalid,
                    oracle=_oracle_descriptor(task, baseline, None),
""",
        """                    harness_invalid=_harness_invalid,
""",
        [],
    ),
    (
        "T16-success-passes-none",
        RB,
        """                    harness_invalid=_harness_invalid,
                    oracle=_oracle_descriptor(task, baseline, final_state),
""",
        """                    harness_invalid=_harness_invalid,
                    oracle=_oracle_descriptor(task, baseline, None),
""",
        [],
    ),
    (
        "T17-default-fallback-claims-hidden",
        RB,
        "    oracle_type, oracle_visible = oracle if oracle is not None else (_oracle_type_label(final_state), True)",
        "    oracle_type, oracle_visible = oracle if oracle is not None else (_oracle_type_label(final_state), False)  # mutation: 回落行说成不可见",
        [],
    ),
    (
        "T18-default-fallback-hardcodes-label",
        RB,
        "    oracle_type, oracle_visible = oracle if oracle is not None else (_oracle_type_label(final_state), True)",
        "    oracle_type, oracle_visible = oracle if oracle is not None else (ORACLE_TYPE_GENERATED, True)  # mutation: 回落写死常量",
        [],
    ),
    # ─── 结构等式：声明条件与真实验收路由条件同式 ───────────────────────
    (
        "T19-router-term-dropped",
        RB,
        """                    and task.metadata.get("base_commit")
""",
        "",
        [],
    ),
    # ─── 词表：单一事实源缺一档就把该档折进词表外 ───────────────────────
    (
        "T20-vocab-enhanced-dropped",
        OP,
        """    ORACLE_TYPE_GENERATED,
    ORACLE_TYPE_ENHANCED,
    ORACLE_TYPE_REPO_GOLD,
)""",
        """    ORACLE_TYPE_GENERATED,
    ORACLE_TYPE_REPO_GOLD,
)  # mutation: 增强档不在词表""",
        [],
    ),
    (
        "T21-vocab-gold-dropped",
        OP,
        """    ORACLE_TYPE_GENERATED,
    ORACLE_TYPE_ENHANCED,
    ORACLE_TYPE_REPO_GOLD,
)""",
        """    ORACLE_TYPE_GENERATED,
    ORACLE_TYPE_ENHANCED,
)  # mutation: gold 档不在词表""",
        [],
    ),
    # ─── 读端：oracle_provenance_stats 的分档与对账 ─────────────────────
    (
        "T22-recorded-counts-all-rows",
        SA,
        '        if "oracle_type" in row or "test_visible_to_system" in row:',
        "        if True:  # mutation: 缺键行也算记录",
        [],
    ),
    (
        "T23-vocab-check-by-str-only",
        SA,
        "        if isinstance(oracle_type, str) and oracle_type in ORACLE_TYPES:",
        "        if isinstance(oracle_type, str):  # mutation: 词表外也按自身值分档",
        [],
    ),
    (
        "T24-other-merged-into-not-recorded",
        SA,
        '            by_type["not_recorded" if oracle_type is None else "other"] += 1',
        '            by_type["not_recorded"] += 1  # mutation: 词表外并入未记录',
        [],
    ),
    (
        "T25-nonstring-other-value-unnamed",
        SA,
        """            if oracle_type is not None and not isinstance(oracle_type, str):
                other_values[type(oracle_type).__name__] += 1
""",
        """            if False:  # mutation: 非字符串词表外值不点名
                other_values[type(oracle_type).__name__] += 1
""",
        [],
    ),
    (
        "T26-visible-truthy-collapse",
        SA,
        "        if visible is True:",
        '        if visible:  # mutation: 字符串 "false" 也说成可见',
        [],
    ),
    (
        "T27-repo-row-detection-loosened",
        SA,
        "        if isinstance(repo_verification, dict) and repo_verification:",
        "        if repo_verification is not None:  # mutation: 空 dict 也算仓库行",
        [],
    ),
    (
        "T28-unrecorded-folded-into-violation",
        SA,
        "            if oracle_type is None and visible is None:",
        "            if False:  # mutation: 缺声明折成错标（BT 第一版形态）",
        [],
    ),
    (
        "T29-unrecorded-folded-into-consistent",
        SA,
        "                repo_unrecorded += 1",
        "                repo_consistent += 1  # mutation: 缺声明读成声明一致",
        [],
    ),
    (
        "T30-consistent-ignores-visibility",
        SA,
        "            elif oracle_type == ORACLE_TYPE_REPO_GOLD and visible is False:",
        "            elif oracle_type == ORACLE_TYPE_REPO_GOLD:  # mutation: 一致档只查类型",
        [],
    ),
    (
        "T31-consistent-bucket-not-counted",
        SA,
        "                repo_consistent += 1",
        "                pass  # mutation: 一致行不记档（恒等式破裂）",
        [],
    ),
    (
        "T32-half-declared-folded-into-unrecorded",
        SA,
        "            if oracle_type is None and visible is None:",
        "            if oracle_type is None or visible is None:  # mutation: 只缺一键也说成缺声明",
        [],
    ),
    (
        "T33-violation-detail-uncapped",
        SA,
        '        "violations": violations[:20],',
        '        "violations": violations,  # mutation: 明细不设上限',
        [],
    ),
    (
        "T34-consistent-always-true",
        SA,
        '        "consistent": not violations,',
        '        "consistent": True,  # mutation: 不一致也说成一致',
        [],
    ),
    (
        "T35-none-arm-not-tolerated",
        SA,
        "    rows = [r for r in (rows or []) if isinstance(r, dict)]",
        "    rows = [r for r in rows if isinstance(r, dict)]  # mutation: 助手不再兜 None 臂",
        [],
    ),
    # ─── 报告面：章节渲染、点名与口径脚注 ───────────────────────────────
    (
        "T36-zero-row-arm-rendered",
        AR,
        '    prov_rows = [(b, pv) for b, pv in prov.items() if pv.get("n_rows")]',
        "    prov_rows = [(b, pv) for b, pv in prov.items()]  # mutation: 零行臂也渲染全零表",
        [],
    ),
    (
        "T37-violation-line-always",
        AR,
        "        if bad:",
        "        if True:  # mutation: 干净臂也打印不一致",
        [],
    ),
    (
        "T38-bt-other-note-suppressed",
        AR,
        '        other_notes = [f"`{b}` 出现词表外取值 {pv[\'other_values\']}" for b, pv in prov_rows if pv.get("other_values")]',
        "        other_notes = []  # mutation: BT 词表外取值不点名",
        [],
    ),
    (
        "T39-bt-other-note-always",
        AR,
        """        if other_notes:
            lines.append(f"> 词表外取值（单列，不并入任何档）""",
        """        if True:
            lines.append(f"> 词表外取值（单列，不并入任何档）""",
        [],
    ),
    (
        "T40-unrecorded-caliber-dropped",
        AR,
        """            "`未记录` = 该行没有这两个键（批次早于 R52，**不等于**「生成测试验收」）。"
""",
        "",
        [],
    ),
    (
        "T41-repo-double-condition-dropped",
        AR,
        """            "repo 行（有 `repo_verification`）必须同时满足 `gold_fail_to_pass` 与 `False`，否则计入「不一致」。"
""",
        "",
        [],
    ),
    (
        "T42-missing-declaration-caliber-dropped",
        AR,
        """            "> `repo 缺声明` = 有仓库级验收但**两个键都未记录**（早于 R52 的历史批次）——"
            "缺键读作未记录，**不计入不一致**；只记录了一个键属不完整声明，仍计入不一致。"
""",
        '            ""  # mutation: 缺声明口径不写\n',
        [],
    ),
    (
        "T43-repo-rows-cell-zeroed",
        AR,
        """                f"| {pv.get('n_rows', 0)} | {pv.get('repo_rows', 0)} | {pv.get('repo_rows_unrecorded', 0)} \"""",
        """                f"| {pv.get('n_rows', 0)} | 0 | {pv.get('repo_rows_unrecorded', 0)} \"""",
        [],
    ),
    (
        "T44-repo-unrecorded-cell-zeroed",
        AR,
        """                f"| {pv.get('n_rows', 0)} | {pv.get('repo_rows', 0)} | {pv.get('repo_rows_unrecorded', 0)} \"""",
        """                f"| {pv.get('n_rows', 0)} | {pv.get('repo_rows', 0)} | 0 \"""  # mutation: 缺声明列抹零""",
        [],
    ),
    (
        "T45-repo-consistent-cell-zeroed",
        AR,
        """                f"| {pv.get('repo_rows_consistent', 0)} | {pv.get('n_violations', 0)} |\"""",
        """                f"| 0 | {pv.get('n_violations', 0)} |\"  # mutation: 声明一致列抹零""",
        [],
    ),
    (
        "T46-violations-cell-zeroed",
        AR,
        """                f"| {pv.get('repo_rows_consistent', 0)} | {pv.get('n_violations', 0)} |\"""",
        """                f"| {pv.get('repo_rows_consistent', 0)} | 0 |\"  # mutation: 不一致列抹零""",
        [],
    ),
    (
        "T47-wiring-key-computed-but-not-fed",
        AR,
        '            "oracle_provenance": _oracle_provenance(details),',
        '            "oracle_provenance": {},  # mutation: 读侧算了但不接入',
        [],
    ),
    (
        "T48-violation-detail-capped-in-report",
        AR,
        """                f"`{b}` {pv['n_violations']} 行（样例 task_id: {', '.join(pv.get('violations', [])[:5]) or '—'}）\"""",
        """                f"`{b}` {pv['n_violations']} 行（样例 task_id: {'—'}）\"  # mutation: 不一致不点名""",
        [],
    ),
    (
        # 中性对照：仅改 docstring 措辞（去掉一对强调星号），不动任何判据 —— 必须 0 红。
        "T49-control-wording",
        SA,
        "    本助手只做**读侧对账**，不改任何判定：",
        "    本助手只做读侧对账，不改任何判定：",
        [],
    ),
]

CONTROL = "T49-control-wording"
_COLLECTED_RE = re.compile(r"(\d+) tests collected")
_BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _BROKER_VARS}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BT_TESTS, *paths, "--collect-only", "-q"]
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
        *BT_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bt_mut",
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
    survivors = [n for n, v, _ in results if v != "FAILED" and n != CONTROL]
    wrong_control = [n for n, v, _ in results if n == CONTROL and v != "SURVIVED"]
    print(f"\n未杀活的变异 = {survivors}；对照误杀 = {wrong_control}")
    return 0 if not survivors and not wrong_control else 2


if __name__ == "__main__":
    sys.exit(main())
