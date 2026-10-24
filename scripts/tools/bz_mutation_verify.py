#!/usr/bin/env python3
"""BZ 轮补遗变异验证：模型指纹门禁的豁免/漂移锚点 12 个 + 1 个中性对照。

纪律（与 BH→BY 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 加星号）必须 0 红。

锚点方向：每一处都是「把本轮补的可观测性退回静默」——豁免条目被当普通批次
照检、豁免只跳一半、[EXEMPT] 不带理由、豁免掩盖同目录其他未锁定批次、
漂移三种失效（文件消失 / 已 pinned / 坏工件）不记、空扫描面吞掉漂移、
漂移检查整体不接线、相对键口径改错、登记表清空、登记键写错文件名。

受影响面 = `tests/test_model_fingerprint.py`（34 例，含 7 例豁免锁）。
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
BROKER_VARS = ("CODEBUDDY_SANDBOX_BROKER_IPC_ADDRESS", "CODEBUDDY_SANDBOX_HOST_FILE_OPERATION_COMMAND")

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        "M01-exempt-lookup-off",
        GATE,
        "        if key in _PRE_FINGERPRINT_EXEMPT:",
        "        if False:  # mutation: 豁免表不生效",
        [],
    ),
    (
        "M02-exempt-skips-only-marker",
        GATE,
        "            continue\n        checked.append(path)",
        "            pass  # mutation: 豁免只打标记，仍照检\n        checked.append(path)",
        [],
    ),
    (
        "M03-exempt-count-not-incremented",
        GATE,
        "            exempt_count += 1\n",
        "            pass  # mutation: 豁免数不记\n",
        [],
    ),
    (
        "M04-exempt-marker-without-reason",
        GATE,
        '            print(f"[EXEMPT] {path}: {_PRE_FINGERPRINT_EXEMPT[key]}")',
        "            pass  # mutation: 豁免不打标记",
        [],
    ),
    (
        "M05-drift-missing-not-recorded",
        GATE,
        '            failures.append(f"{key}: 豁免漂移（文件已不存在：{reason}）")\n            continue',
        "            continue  # mutation: 文件消失不记漂移",
        [],
    ),
    (
        "M06-drift-pinned-not-recorded",
        GATE,
        '        if passed:\n            failures.append(f"{key}: 豁免漂移（已 pinned=true，应移除豁免登记：{reason}）")',
        "        if False:  # mutation: 已 pinned 不记漂移\n"
        '            failures.append(f"{key}: 豁免漂移（已 pinned=true，应移除豁免登记：{reason}）")',
        [],
    ),
    (
        "M07-drift-unreadable-not-recorded",
        GATE,
        "        except (json.JSONDecodeError, OSError) as e:\n"
        '            failures.append(f"{key}: 豁免漂移（工件不可审计：{type(e).__name__}: {e}）")\n'
        "            continue",
        "        except (json.JSONDecodeError, OSError):\n            continue  # mutation: 坏工件不记漂移",
        [],
    ),
    (
        "M08-empty-surface-swallows-drift",
        GATE,
        '        print(f"{msg}——近期无新批次可验（S29 只要求新批次已锁定），通过；审计历史请用 --all-history")\n'
        "        return 0 if not failures else 1",
        '        print(f"{msg}——近期无新批次可验（S29 只要求新批次已锁定），通过；审计历史请用 --all-history")\n'
        "        return 0  # mutation: 空扫描面吞掉漂移",
        [],
    ),
    (
        "M09-drift-check-unwired",
        GATE,
        "    failures: list[str] = exemption_drift_failures()",
        "    failures: list[str] = []  # mutation: 漂移检查不接线",
        [],
    ),
    (
        "M10-rel-key-wrong-root",
        GATE,
        "        return path.resolve().relative_to(PROJECT_ROOT).as_posix()",
        "        return path.resolve().relative_to(PROJECT_ROOT.parent).as_posix()  # mutation: 相对键根改错",
        [],
    ),
    (
        "M11-registry-key-typo",
        GATE,
        '"experiments/results/benchmark_examples_20260813_125502.json": (',
        '"experiments/results/benchmark_examples_20260813_125503.json": (  # mutation: 登记键写错文件名',
        [],
    ),
    (
        "M12-registry-emptied",
        GATE,
        "_PRE_FINGERPRINT_EXEMPT: dict[str, str] = {\n"
        '    "experiments/results/benchmark_examples_20260813_125502.json": (\n'
        '        "2026-08-13 跑批的 examples 数据集历史批次（指纹功能上线前，无 provenance 块）；"\n'
        '        "为 BY 轮分析集流量测试契约入库（PINNED_BATCHES 的 unsupported_dataset 层样例），"\n'
        '        "非新跑批"\n'
        "    ),\n"
        "}",
        "_PRE_FINGERPRINT_EXEMPT: dict[str, str] = {}  # mutation: 登记表清空",
        [],
    ),
    (
        CONTROL,
        GATE,
        '"""S29（2026-10-11 独立评审落地）门禁：',
        '"""**S29（2026-10-11 独立评审落地）门禁：',
        [],
    ),
]


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    for var in BROKER_VARS:
        env.pop(var, None)
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
        "--basetemp=/tmp/pt_bz_mut",
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
