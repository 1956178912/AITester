#!/usr/bin/env python3
"""BO 轮变异验证：raw 读侧披露的 23 个锚点 + 1 个中性对照。

纪律（与 BA→BN 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异一律照"改前的折叠行为"来写（把披露退回沉默或退回归因），必须转红；
  中性对照（只改措辞）必须 0 红；
- 收尾做 `# mutation:` 残留扫描，确认还原后源码里一个变异标记都不剩。

锚点面（每处都是 BO 登记的那句披露，不是打分逻辑）：
  S1—S2   `run_benchmark` provenance 的开关态（删键 / 去掉严格布尔）；
  R1—R3   `_classify_root_cause` 三条缺席腿退回 DEP_GRAPH_INCOMPLETE；
  R4—R6   `dep_edges` 的 null 写法、`recorded` 计数、`reachable` 判据；
  R7      `_load_state` 顶层非对象守卫；
  P1—P5   `_locate_stats` 的 null 腿、键缺席腿、`_repaired` 两证据、
          零分母优先级、`_GRADE_TEXT` 的 null 档文本；
  C1—C8   `compare_failures` 的单臂披露（两臂）、真值折叠（两臂）、报告头
          证据面、缺席形态行、损坏件不抛穿、两种缺席不同句；
  W1      `cross_file_ab` 后续命令的 --raw-dir。
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

BO_TESTS = "tests/test_bo_raw_readside_disclosure.py"
RB = "experiments/run_benchmark.py"
CF = "experiments/cross_file_root_cause.py"
PA = "experiments/position_aware_ab.py"
CMP = "experiments/compare_failures.py"
AB = "experiments/cross_file_ab.py"

MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ── S：开关态可复核性 ──────────────────────────────────────────────────
    (
        "S1-provenance-drops-switch-state",
        RB,
        '        "save_state": bool(save_state),\n',
        "",
        [],
    ),
    (
        "S2-switch-state-not-strictly-bool",
        RB,
        '        "save_state": bool(save_state),',
        '        "save_state": save_state,  # mutation: switch state no longer coerced to bool',
        [],
    ),
    # ── R：根因分级与自证 ─────────────────────────────────────────────────
    (
        "R1-file-absence-folds-into-0-edges",
        CF,
        '            return "RAW_UNAVAILABLE"',
        '            return "DEP_GRAPH_INCOMPLETE"  # mutation: file-level absence folds into "0 edges measured"',
        [],
    ),
    (
        "R2-key-absence-folds-into-0-edges",
        CF,
        '            return "DEP_INPUT_ABSENT"',
        '            return "DEP_GRAPH_INCOMPLETE"  # mutation: key-level absence folds into "0 edges measured"',
        [],
    ),
    (
        "R3-null-value-folds-into-0-edges",
        CF,
        '            return "DEP_INPUT_NULL"',
        '            return "DEP_GRAPH_INCOMPLETE"  # mutation: recorded-null folds into "0 edges measured"',
        [],
    ),
    (
        "R4-dep-edges-prints-zero-for-no-evidence",
        CF,
        '                "dep_edges": None if deps is None else len(deps),',
        '                "dep_edges": len(deps or []),  # mutation: "not measured" renders as a measured 0',
        [],
    ),
    (
        "R5-key-presence-counts-as-evidence",
        CF,
        "                    if state[_key] is not None:\n                        recorded[_key] += 1",
        "                    recorded[_key] += 1  # mutation: BN writes the key always, so presence != evidence",
        [],
    ),
    (
        "R6-reachability-reads-key-presence",
        CF,
        '            "reachable": recorded[key] > 0,',
        '            "reachable": inputs[key] > 0,  # mutation: unreachable_rules would never fire',
        [],
    ),
    (
        "R7-non-dict-top-level-passes-as-ok",
        CF,
        '    if not isinstance(state, dict):\n        return None, "unreadable"',
        '    if not isinstance(state, list):\n        return None, "unreadable"  # mutation: a list artifact is served as state',
        [],
    ),
    # ── P：定位读数分档 ───────────────────────────────────────────────────
    (
        "P1-null-focus-enters-the-denominator",
        PA,
        "        if focus is None:\n"
        '            # 未修复行仍按既有"未激活"口径剔除（归档八臂的跳过明细因此逐字节同形：\n'
        "            # 236 行里 156 行该键为 null，这些行全部既无 iterations 也无 patch）；\n"
        "            # **已修复却无记录**的行改前会落到下面进分母、被计成一次实测未命中\n"
        '            # （"没测"折进"测了且跑偏"，压低定位读数），现单独点名。\n'
        '            skipped["not_repaired" if not _repaired else "focus_not_recorded"] += 1\n'
        "            continue\n",
        "        if focus is None:\n"
        "            # mutation: pre-BO fold — a repaired row with null focus joins the denominator\n"
        "            if not _repaired:\n"
        '                skipped["not_repaired"] += 1\n'
        "                continue\n"
        "            focus = {}\n",
        [],
    ),
    (
        "P2-key-absence-joins-the-null-leg",
        PA,
        '        if "position_aware_focus" not in state:\n'
        '            skipped["focus_key_absent"] += 1\n'
        "            continue\n",
        "        # mutation: pre-BO — key absence and recorded-null share one bucket\n",
        [],
    ),
    (
        "P3-repaired-ignores-the-patch-evidence",
        PA,
        '        _repaired = bool(row.get("iterations")) or bool(row.get("patch"))',
        '        _repaired = bool(row.get("iterations"))  # mutation: a patch-only row reads as "never repaired"',
        [],
    ),
    (
        "P4-zero-denominator-priority-reversed",
        PA,
        '            "state_file_absent",\n'
        '            "state_unreadable",\n'
        '            "focus_key_absent",\n'
        '            "focus_not_recorded",\n'
        '            "row_unusable",\n'
        '            "not_repaired",\n',
        '            "not_repaired",\n'
        '            "row_unusable",\n'
        '            "focus_not_recorded",\n'
        '            "focus_key_absent",\n'
        '            "state_unreadable",\n'
        '            "state_file_absent",\n',
        [],
    ),
    (
        "P5-null-grade-text-dropped",
        PA,
        '    "focus_not_recorded": "不可计算（position_aware_focus 落的是 null：定位环节没记录，"\n'
        '    "但该行确有修复轮次/补丁 ⇒ 不能记成实测未命中）",\n',
        "",
        [],
    ),
    # ── C：compare_failures 报告读侧 ──────────────────────────────────────
    (
        "C1-full-arm-silence-restored",
        CMP,
        "        if full_artifact is None:\n"
        '            lines.append(f"- {full_baseline} 环节级工件不可用：{_ABSENCE_TEXT[full_status]}（≠ 该臂无产物）。")\n',
        "",
        [],
    ),
    (
        "C2-base-arm-silence-restored",
        CMP,
        "        if base_artifact is None:\n"
        '            lines.append(f"- {base_baseline} 环节级工件不可用：{_ABSENCE_TEXT[base_status]}（≠ 该臂无产物）。")\n',
        "",
        [],
    ),
    (
        "C3-full-side-truthiness-fold",
        CMP,
        "        if full_artifact is not None:",
        "        if full_artifact:  # mutation: an empty {} artifact reads as if absent",
        [],
    ),
    (
        "C4-base-side-truthiness-fold",
        CMP,
        "        if base_artifact is not None:",
        "        if base_artifact:  # mutation: an empty {} artifact reads as if absent",
        [],
    ),
    (
        "C5-report-header-face-dropped",
        CMP,
        '        (f"- 环节级工件目录: `{raw_dir}`" if raw_dir else "- 环节级工件目录: 未提供（下文环节级对比只能声明缺席）"),\n',
        "",
        [],
    ),
    (
        "C6-absence-shapes-line-dropped",
        CMP,
        "            lines.append(\n"
        '                f"- 缺席形态（BO 披露，不互相折叠）: {full_baseline}={_ABSENCE_TEXT[full_status]}；"\n'
        '                f"{base_baseline}={_ABSENCE_TEXT[base_status]}"\n'
        "            )\n",
        "",
        [],
    ),
    (
        "C7-corrupt-artifact-raises-through",
        CMP,
        '    except (OSError, json.JSONDecodeError, UnicodeDecodeError):\n        return None, "unreadable"',
        "    except (OSError, json.JSONDecodeError, UnicodeDecodeError):\n        raise  # mutation: one broken file aborts the whole report",
        [],
    ),
    (
        "C8-two-absences-share-one-sentence",
        CMP,
        '    "file_absent": "该任务的环节件不存在",',
        '    "file_absent": "未提供 raw 目录（跑批未加 --save-state）",  # mutation: absences collapse',
        [],
    ),
    # ── W：接线 ───────────────────────────────────────────────────────────
    (
        "W1-followup-command-drops-raw-dir",
        AB,
        '            f"--raw-dir {on_dir}/raw --difficulty {args.difficulty}"',
        '            f"--difficulty {args.difficulty}"  # mutation: the printed command loses the evidence face',
        [],
    ),
    # ── 中性对照：只改注释措辞，必须 0 红 ─────────────────────────────────
    (
        "M-control-wording",
        PA,
        '        # 无激活样本：命中率为"不可计算"档（-1.0），grade 点名是哪一种缺席。',
        '        # 无激活样本 ⇒ 命中率落在"不可计算"档（-1.0），由 grade 点名是哪一种缺席。',
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests? collected")
_TOUCHED = sorted({rel for _, rel, *_ in MUTANTS})


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BO_TESTS, *paths, "--collect-only", "-q"]
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
        BO_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bo_mut",
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
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-12:])
    return proc.returncode, tail


def main() -> int:
    print(f"=== 基线全绿核对（{BO_TESTS}）===")
    rc, tail = run_tests([])
    baseline_collected = collect_count([])
    print(f"基线 rc={rc} collected={baseline_collected}\n{tail}")
    if rc != 0:
        print("基线不绿，停止变异验证（红/绿不可归因）")
        return 1

    results: list[tuple[str, str]] = []
    for name, relpath, old, new, extra in MUTANTS:
        path = ROOT / relpath
        original = path.read_bytes()
        sha_before = hashlib.sha256(original).hexdigest()
        text = original.decode("utf-8")
        if text.count(old) != 1:
            print(f"[{name}] ANCHOR NOT UNIQUE ({text.count(old)}) — skip")
            results.append((name, "ANCHOR-ERROR"))
            continue
        if new and text.count(new) != 0:
            print(f"[{name}] MUTATION STRING ALREADY PRESENT — skip")
            results.append((name, "ANCHOR-ERROR"))
            continue
        mutated = text.replace(old, new, 1)
        if path.suffix == ".py":
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

    print("\n=== 残留扫描（还原后源码里不应有变异标记）===")
    residue = []
    for rel in _TOUCHED:
        body = (ROOT / rel).read_text(encoding="utf-8")
        residue += [(rel, line.strip()) for line in body.splitlines() if "# mutation:" in line]
    print(f"# mutation 命中 {len(residue)} 处：{residue or '无'}")

    print("\n=== SUMMARY ===")
    for name, verdict in results:
        print(f"{verdict:14s} {name}")
    control = "M-control-wording"
    mutants = [(n, v) for n, v in results if n != control]
    survivors = [n for n, v in mutants if v != "FAILED"]
    control_verdict = [v for n, v in results if n == control]
    print(f"\n读侧披露锚点 {len(mutants)} 个：击杀 {len(mutants) - len(survivors)}，未击杀/异常 {survivors or '无'}")
    print(f"中性对照（{control}）判读：{control_verdict or '未执行'}——口径要求它 0 红（SURVIVED）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
