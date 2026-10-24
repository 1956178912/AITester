#!/usr/bin/env python3
"""CA 轮变异验证：工件入库门禁的豁免漂移/遮蔽量锚点 16 个 + 1 个中性对照。

纪律（与 BH→BZ 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 加星号）必须 0 红。

锚点方向：每一处都是「把本轮补的可观测性退回静默」——漂移检查不接线、
五类漂移各不记、扫描面判定恒真、遮蔽量算成全部文件 / 恒 0、逐条披露不打印、
汇总披露置零、git 失败当 0 入库、全部文件当已跟踪、豁免跳过失效、登记表
把本轮删掉的两条死条目加回去、模块退回不可被无登记动态加载的 dataclass。

受影响面 = `tests/test_artifacts_tracked_gate.py`（33 例，含 12 例豁免锁）。
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

GATE = "scripts/gates/check_artifacts_tracked.py"

BASE_TESTS = ["tests/test_artifacts_tracked_gate.py"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M01-drift-check-unwired",
        GATE,
        "    drift = exemption_drift_failures(coverage)",
        "    drift = []  # mutation: 漂移检查不接线",
    ),
    (
        "M02-missing-not-recorded",
        GATE,
        '        if row.status == "missing":\n'
        '            failures.append((row.name, "豁免漂移（目录已不存在，登记应移除）"))',
        "        if False:  # mutation: 死条目不记漂移\n"
        '            failures.append((row.name, "豁免漂移（目录已不存在，登记应移除）"))',
    ),
    (
        "M03-fully-tracked-not-recorded",
        GATE,
        '        elif row.status == "fully_tracked":',
        "        elif False:  # mutation: 已全入库不记漂移",
    ),
    (
        "M04-unreadable-not-recorded",
        GATE,
        '        elif row.status == "unreadable":',
        "        elif False:  # mutation: 不可读不记漂移",
    ),
    (
        "M05-empty-not-recorded",
        GATE,
        '        elif row.status == "empty":',
        "        elif False:  # mutation: 空目录不记漂移",
    ),
    (
        "M06-scan-surface-not-checked",
        GATE,
        "        if not row.in_scan_surface:",
        "        if False:  # mutation: 登记名永在扫描面内",
    ),
    (
        "M07-hidden-counts-all-files",
        GATE,
        "        return self.total_files - self.tracked_files",
        "        return self.total_files  # mutation: 全部文件都算遮蔽",
    ),
    (
        "M08-status-never-fully-tracked",
        GATE,
        '        status = "fully_tracked" if len(tracked) == len(files) else "ok"',
        '        status = "ok"  # mutation: 永不判已全入库',
    ),
    (
        "M09-per-entry-disclosure-dropped",
        GATE,
        '    for row in active:\n        print(f"  [EXEMPT] {row.name}: 遮蔽未入库工件 {row.hidden_files}/{row.total_files}")',
        "    for _row in active:  # mutation: 逐条披露不打印\n        pass",
    ),
    (
        "M10-hidden-total-zeroed",
        GATE,
        "    hidden_total = sum(row.hidden_files for row in active)",
        "    hidden_total = 0  # mutation: 汇总遮蔽量置零",
    ),
    (
        "M11-git-failure-counted-as-untracked",
        GATE,
        "        if ls.returncode != 0:\n            rows.append(\n"
        '                ExemptionCoverage(name, "unreadable", surface, len(files), 0, f"git ls-files 失败: {ls.stderr.strip()}")\n'
        "            )\n            continue",
        "        if False:  # mutation: git 失败当作 0 入库\n            pass",
    ),
    (
        "M12-every-file-treated-tracked",
        GATE,
        "        tracked = {line for line in ls.stdout.splitlines() if line.strip()}",
        "        tracked = set(rels)  # mutation: 全部文件当已跟踪",
    ),
    (
        "M13-exemption-no-longer-skips",
        GATE,
        "            if name in EVIDENCE_DIR_EXEMPTIONS:\n                continue",
        "            if False:  # mutation: 豁免不生效\n                continue",
    ),
    (
        "M14-dead-entries-restored",
        GATE,
        'EVIDENCE_DIR_EXEMPTIONS: dict[str, str] = {\n    "emse_d2_profile_smoke_20261013":',
        "EVIDENCE_DIR_EXEMPTIONS: dict[str, str] = {\n"
        '    "emse_jsonmode_smoke_20261013": "JSON mode 冒烟",\n'
        '    "emse_spec_ir_quixbugs_20261013": "SpecIR QuixBugs 初版",\n'
        '    "emse_d2_profile_smoke_20261013":',
    ),
    (
        "M15-scan-surface-always-true",
        GATE,
        "    return any(fnmatch.fnmatchcase(name, pattern) for pattern in EVIDENCE_DIR_GLOBS)",
        "    return True  # mutation: 扫描面恒真",
    ),
    (
        "M16-dataclass-instead-of-namedtuple",
        GATE,
        "class ExemptionCoverage(NamedTuple):",
        '@__import__("dataclasses").dataclass(frozen=True)  # mutation: 退回 dataclass\nclass ExemptionCoverage:',
    ),
    (
        CONTROL,
        GATE,
        '"""AK3（2026-10-06 第十二轮审查 R1）：主批次工件 git 入库守卫。',
        '"""**AK3（2026-10-06 第十二轮审查 R1）：主批次工件 git 入库守卫。',
    ),
]


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_count() -> int:
    cmd = [str(PY), "-m", "pytest", *BASE_TESTS, "--collect-only", "-q"]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300, env=_clean_env())
    match = COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests() -> tuple[int, int, str, list[str]]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BASE_TESTS,
        "-q",
        "--basetemp=/tmp/pt_ca_mut",
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
    for name, relpath, old, _new in MUTANTS:
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
    baseline_collected = collect_count()
    rc, red, tail, _ = run_tests()
    print(f"[baseline] rc={rc} red={red} collected={baseline_collected}\n{tail}")
    if rc != 0 or red != 0:
        print("BASELINE NOT GREEN — abort")
        return 1

    selected = MUTANTS
    if len(sys.argv) > 1:
        wanted = set(sys.argv[1:])
        selected = [m for m in MUTANTS if any(m[0].startswith(w) for w in wanted)]
        print(f"[filter] running {len(selected)} of {len(MUTANTS)}")

    results = []
    for name, relpath, old, new in selected:
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
        path.write_text(mutated, encoding="utf-8")
        try:
            rc, red, tail, failed = run_tests()
            mutated_collected = collect_count()
        finally:
            path.write_bytes(original)
            restored = path.read_bytes()
            assert hashlib.sha256(restored).hexdigest() == sha_before, f"{name}: restore mismatch"
        if mutated_collected != baseline_collected:
            print(f"[{name}] COLLECTED DRIFT {baseline_collected} -> {mutated_collected}")
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
