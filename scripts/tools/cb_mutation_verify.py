#!/usr/bin/env python3
"""CB 轮变异验证：状态通道审计面披露的 18 个锚点 + 1 个中性对照。

纪律（与 BH→CA 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 加星号）必须 0 红。

锚点方向：每一处都是「把本轮补的可观测性退回静默」——update dict 不计、
非声明键被计入覆盖、读/就地写/临时/动态/未声明各不计、未触及键清空、
有字面/零字面的分类失效、成功路径不披露、逐键表不打印、测量装置的自我
排除失效（或其模块名识别失效）、Union/差集属性退回单向、NamedTuple 退回
dataclass（历史加载器不可用）。

受影响面 = `tests/test_state_contract_guard.py`（30 例，含 17 例覆盖锁）。
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

GATE = "scripts/gates/check_state_contract.py"

BASE_TESTS = ["tests/test_state_contract_guard.py"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M01-return-dict-not-counted",
        GATE,
        "            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):",
        "            if False:  # mutation: 节点返回更新 dict 不计",
    ),
    (
        "M02-update-merge-not-counted",
        GATE,
        "                elif node.func.attr in _UPDATE_MERGE_ATTRS:",
        "                elif False:  # mutation: update/merge 实参不计",
    ),
    (
        "M03-foreign-keys-counted-as-coverage",
        GATE,
        "                        else:\n                            foreign += 1\n    return _Usage(",
        "                        else:\n"
        "                            update[key] += 1  # mutation: 非声明键计入覆盖\n"
        "    return _Usage(",
    ),
    (
        "M04-read-sites-not-counted",
        GATE,
        '                if node.func.attr == "get" and _is_state_var(node.func.value):',
        "                if False:  # mutation: state.get 读侧不计",
    ),
    (
        "M05-inplace-writes-not-counted",
        GATE,
        "                    if isinstance(tgt, ast.Subscript) and _is_state_var(tgt.value):",
        "                    if False:  # mutation: 就地赋值不计",
    ),
    (
        "M06-untouched-emptied",
        GATE,
        "    untouched = tuple(sorted(non_temp - touched))",
        "    untouched = ()  # mutation: 未触及键清空",
    ),
    (
        "M07-everything-classified-elsewhere",
        GATE,
        "    elsewhere = tuple(k for k in untouched if f'\"{k}\"' in outside or f\"'{k}'\" in outside)",
        "    elsewhere = untouched  # mutation: 全部算「别处有字面」",
    ),
    (
        "M08-nowhere-emptied",
        GATE,
        "    nowhere = tuple(k for k in untouched if k not in elsewhere)",
        "    nowhere = ()  # mutation: 零字面分类失效",
    ),
    (
        "M09-temp-keys-not-counted",
        GATE,
        '        elif key.startswith("_"):\n            temp[key] += 1',
        "        elif False:  # mutation: 下划线临时键不计\n            temp[key] += 1",
    ),
    (
        "M10-dynamic-keys-not-counted",
        GATE,
        "        if key is None:\n            dynamic += 1",
        "        if False:  # mutation: 动态键不计\n            dynamic += 1",
    ),
    (
        "M11-undeclared-sites-not-counted",
        GATE,
        "            undeclared += 1",
        "            undeclared += 0  # mutation: 未声明站点不计",
    ),
    (
        "M12-success-path-disclosure-dropped",
        GATE,
        "        for line in coverage_lines(channel_coverage()):\n            print(line)",
        "        for _line in coverage_lines(channel_coverage()):  # mutation: 成功路径不披露\n            pass",
    ),
    (
        "M13-coverage-table-dropped",
        GATE,
        '        for key in cov.declared:\n            print(f"  {key}: {usage.read[key]} / {usage.inplace[key]} / {usage.update[key]}")',
        "        for _key in cov.declared:  # mutation: 逐键表不打印\n            pass",
    ),
    (
        "M14-apparatus-not-excluded",
        GATE,
        "    skip = _apparatus_paths()",
        "    skip: set[Path] = set()  # mutation: 测量装置不排除（自指）",
    ),
    (
        "M15-module-name-unresolvable",
        GATE,
        '    return ".".join(rel.parts)',
        '    return ""  # mutation: 点分名失效，装置识别不到测试',
    ),
    (
        "M16-dataclass-instead-of-namedtuple",
        GATE,
        "class ChannelCoverage(NamedTuple):",
        '@__import__("dataclasses").dataclass(frozen=True)  # mutation: 退回 dataclass\nclass ChannelCoverage:',
    ),
    (
        "M17-written-keys-ignore-inplace",
        GATE,
        "        return tuple(sorted(set(self.inplace_write_keys) | set(self.update_write_keys)))",
        "        return tuple(sorted(self.update_write_keys))  # mutation: 漏掉就地写",
    ),
    (
        "M18-unaudited-ignores-inplace-gap",
        GATE,
        "        return tuple(sorted(set(self.update_write_keys) - set(self.inplace_write_keys)))",
        "        return tuple(sorted(self.update_write_keys))  # mutation: 未减就地写",
    ),
    (
        CONTROL,
        GATE,
        '"""P1-6（2026-10-05 独立审查）：LangGraph 状态通道契约静态守卫。',
        '"""**P1-6（2026-10-05 独立审查）：LangGraph 状态通道契约静态守卫。',
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
        "--basetemp=/tmp/pt_cb_mut",
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
