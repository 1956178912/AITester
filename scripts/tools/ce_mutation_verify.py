#!/usr/bin/env python3
"""CE 轮变异验证：模型指纹门禁的可比性围栏 / 受检面披露锚点 33 个 + 1 个中性对照。

纪律（与 BH→CD 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 加星号）必须 0 红。

锚点方向：每一处都是「把本轮补的可观测性退回静默」——两条围栏各不判、围栏
结果不进阻断、报红不打印、四条输出路径各不披露受检面、语料面的递归口径/
结构层/alias 双读数各退回写死的 0、注册表取不到时冒充"可用"或静默 skip、
脚本执行口径不补 sys.path、成功语句分母退回窗口内文件数、通过计数不累加。

**pinned 判定面刻意不设锚点**：本轮纪律是"判定值与方向一处不动"，由
`test_pinned_judgment_values_are_untouched` 与既有 pinned 锁共同守；变异面只
覆盖新增观测。

受影响面 = `tests/test_model_fingerprint.py`（54 例，其中 CE 轮 19 例）。
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

GATE = "scripts/gates/check_model_fingerprint.py"

BASE_TESTS = ["tests/test_model_fingerprint.py"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M01-alias-mismatch-fence-off",
        GATE,
        """    findings: list[str] = []
    if fingerprint.get("alias_mismatch") is True:
        findings.append(""",
        """    findings: list[str] = []
    if False:  # mutation: alias_mismatch 围栏不判
        findings.append(""",
    ),
    (
        "M02-registry-alias-fence-off",
        GATE,
        """    if aliases:
        alias = fingerprint.get("requested_alias")""",
        """    if False:  # mutation: 运行时模型集对账不判
        alias = fingerprint.get("requested_alias")""",
    ),
    (
        "M03-registry-unavailable-flags-all",
        GATE,
        """    if aliases:
        alias = fingerprint.get("requested_alias")""",
        """    if True:  # mutation: 前提缺失冒充工件不合规
        alias = fingerprint.get("requested_alias")""",
    ),
    (
        "M04-fences-not-wired-into-block",
        GATE,
        """        findings = comparability_findings(extract_fingerprint(payload) or {}, aliases)
        if findings:""",
        """        findings = []  # mutation: 围栏结果不进阻断
        if findings:""",
    ),
    (
        "M05-comparability-red-not-printed",
        GATE,
        '            print(f"[FAIL] {path}: 模型版本已锁定（pinned=true）但可比性不成立——{detail}")',
        "            pass  # mutation: 可比性报红不打印",
    ),
    (
        "M06-surface-lines-empty",
        GATE,
        "    surface_lines = surface_disclosure(files, exempt_count)",
        "    surface_lines = []  # mutation: 受检面披露不打印",
    ),
    (
        "M07-failure-path-surface-dropped",
        GATE,
        """        for line in surface_lines:
            print(line, file=sys.stderr)
        return 1""",
        "        return 1",
    ),
    (
        "M08-success-path-surface-dropped",
        GATE,
        """    for line in surface_lines:
        print(line)
    return 0""",
        "    return 0",
    ),
    (
        "M09-empty-window-surface-dropped",
        GATE,
        """        print(f"{msg}——近期无新批次可验（S29 只要求新批次已锁定），通过；审计历史请用 --all-history")
        for line in surface_disclosure([], 0):
            print(line)""",
        """        print(f"{msg}——近期无新批次可验（S29 只要求新批次已锁定），通过；审计历史请用 --all-history")""",
    ),
    (
        "M10-allow-empty-surface-dropped",
        GATE,
        """            print(f"{msg}——--allow-empty，不阻断")
            for line in surface_disclosure([], 0):
                print(line)""",
        """            print(f"{msg}——--allow-empty，不阻断")""",
    ),
    (
        "M11-alias-reconciliation-line-dropped",
        GATE,
        """        (
            f"[SURFACE] alias 对账：运行时模型集 "
            f"{sorted(runtime_model_aliases()[0]) or '不可用'}；全语料 unsupported_alias "
            f"{surface['unsupported_alias']} / alias_mismatch_true {surface['alias_mismatch_true']}（只披露，历史批次不重判）"
        ),
""",
        "        # mutation: alias 对账披露不打印\n",
    ),
    (
        "M12-scanned-surface-line-dropped",
        GATE,
        """        (
            f"[SURFACE] 受检面：窗口内 {len(files)}（豁免 {exempt_count} ⇒ 实检 {checked}，"
            f"口径 = 默认目录非递归 + 近 2 天 mtime）"
        ),
""",
        "        # mutation: 受检面行不打印\n",
    ),
    (
        "M13-corpus-glob-non-recursive",
        GATE,
        '    on_disk = sorted(root.rglob("benchmark_*.json"))',
        '    on_disk = sorted(root.glob("benchmark_*.json"))  # mutation: 语料面退回目录单层',
    ),
    (
        "M14-top-level-count-recursive",
        GATE,
        '        sorted(p for p in root.iterdir() if p.is_file() and p.name.startswith("benchmark_") and p.suffix == ".json")',
        '        sorted(root.rglob("benchmark_*.json"))  # mutation: 顶层口径退回递归',
    ),
    (
        "M15-tracked-failure-counted-zero",
        GATE,
        """    except Exception:
        return -1""",
        """    except Exception:
        return 0  # mutation: git 失败当 0 入库""",
    ),
    (
        "M16-tracked-count-ignores-pattern",
        GATE,
        '    names = [line for line in out.splitlines() if Path(line).name.startswith("benchmark_") and line.endswith(".json")]',
        "    names = [line for line in out.splitlines() if line.strip()]  # mutation: 全部入库文件都算",
    ),
    (
        "M17-tracked-unavailable-note-prints-number",
        GATE,
        '    tracked_note = str(surface["tracked"]) if surface["tracked"] >= 0 else "不可用（git 失败）"',
        '    tracked_note = str(surface["tracked"])  # mutation: 不可用冒充计数',
    ),
    (
        "M18-pinned-layer-count-off",
        GATE,
        """        if fingerprint.get("pinned") is True:
            counts["pinned_true"] += 1""",
        """        if False:  # mutation: 结构层 pinned 读数不记
            counts["pinned_true"] += 1""",
    ),
    (
        "M19-mismatch-layer-count-off",
        GATE,
        """        if fingerprint.get("alias_mismatch") is True:
            counts["alias_mismatch_true"] += 1""",
        """        if False:  # mutation: 语料 mismatch 读数不记
            counts["alias_mismatch_true"] += 1""",
    ),
    (
        "M20-mismatch-layer-truthy",
        GATE,
        """        if fingerprint.get("alias_mismatch") is True:
            counts["alias_mismatch_true"] += 1""",
        """        if fingerprint.get("alias_mismatch"):  # mutation: 严格 is True 退回真值
            counts["alias_mismatch_true"] += 1""",
    ),
    (
        "M21-unsupported-alias-count-off",
        GATE,
        """        if aliases and isinstance(alias, str) and alias and alias not in aliases:
            counts["unsupported_alias"] += 1""",
        """        if False:  # mutation: 语料 alias 对账不记
            counts["unsupported_alias"] += 1""",
    ),
    (
        "M22-provenance-layer-unconditional",
        GATE,
        """        if isinstance(provenance, dict):
            counts["with_provenance"] += 1""",
        """        if True:  # mutation: 有 provenance 恒计数
            counts["with_provenance"] += 1""",
    ),
    (
        "M23-fingerprint-layer-count-off",
        GATE,
        '        counts["with_fingerprint"] += 1\n',
        "        pass  # mutation: 指纹层读数不记\n",
    ),
    (
        "M24-script-mode-syspath-not-fixed",
        GATE,
        """        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
""",
        "        pass  # mutation: 脚本执行口径不补仓库根\n",
    ),
    (
        "M25-import-failure-reported-as-available",
        GATE,
        '        return frozenset(), f"运行时模型集不可用：import `{RUNTIME_REGISTRY_ORIGIN}` 失败（{type(e).__name__}: {e}）"',
        "        return frozenset(), None  # mutation: import 失败冒充可用",
    ),
    (
        "M26-empty-or-drifted-registry-uncaused",
        GATE,
        "    if not isinstance(COMMON_MODELS, list) or not COMMON_MODELS:",
        "    if False:  # mutation: 空/类型漂移不报成因",
    ),
    (
        "M27-nameless-registry-treated-as-available",
        GATE,
        '    if not names:\n        return frozenset(), f"运行时模型集不可用：`{RUNTIME_REGISTRY_ORIGIN}` 内无带 name 的条目"',
        '    if False:  # mutation: 无 name 条目当作可用空集\n        return frozenset(), f"运行时模型集不可用：`{RUNTIME_REGISTRY_ORIGIN}` 内无带 name 的条目"',
    ),
    (
        "M28-registry-skip-line-silenced",
        GATE,
        '        print(f"[SKIP] alias 对账未执行：{registry_reason}（`pinned` 判定不受影响）")',
        "        pass  # mutation: 前提缺失静默放行",
    ),
    (
        "M29-success-denominator-is-window",
        GATE,
        '        f"\\n[model-fingerprint] 通过：{comparable}/{total - exempt_count} 个受检工件"',
        '        f"\\n[model-fingerprint] 通过：{comparable}/{total} 个受检工件"  # mutation: 分母退回窗口内文件数',
    ),
    (
        "M30-comparable-counter-off",
        GATE,
        """        comparable += 1
        print(f"[PASS] {path}: model_fingerprint.pinned=true + 可比性围栏通过")""",
        """        pass  # mutation: 通过计数不累加
        print(f"[PASS] {path}: model_fingerprint.pinned=true + 可比性围栏通过")""",
    ),
    (
        "M31-pass-line-drops-fence-name",
        GATE,
        '        print(f"[PASS] {path}: model_fingerprint.pinned=true + 可比性围栏通过")',
        '        print(f"[PASS] {path}: model_fingerprint.pinned=true")  # mutation: 围栏跑过不声明',
    ),
    (
        "M32-block-summary-drops-comparability",
        GATE,
        '            f"（未锁定 + 已锁定但可比性不成立）{exempt_note}。"',
        '            f"{exempt_note}。"  # mutation: 汇总不点名可比性',
    ),
    (
        "M33-checked-count-ignores-exemption",
        GATE,
        "    checked = len(files) - exempt_count",
        "    checked = len(files)  # mutation: 实检数不扣豁免",
    ),
    (
        CONTROL,
        GATE,
        '"""S29（2026-10-11 独立评审落地）门禁：模型版本指纹核验。',
        '"""**S29（2026-10-11 独立评审落地）门禁：模型版本指纹核验。',
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
        "--basetemp=/tmp/pt_ce_mut",
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
