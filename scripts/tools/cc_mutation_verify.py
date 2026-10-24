#!/usr/bin/env python3
"""CC 轮变异验证：补丁重采样 JSON 信封解包的 3 个锚点 + 1 个中性对照。

背景：DebuggerAgent 的 system prompt 要求 JSON 输出，真跑时
``_call_llm_with_cache`` 返回 ``{"root_cause":...,"patch":"```python..."}``
信封；JSON 转义换行是字面 ``\\n``，对整段信封调用 ``extract_code_block``
匹配不到围栏，整段 JSON 被当作补丁 → 契约检查必然拒绝 → 重采样结构上
永远不生效。全部既有用例都 mock 成裸代码块，因此该缺陷无锁。

纪律（与 BH→CC 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数与首批红名 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改 docstring 加星号）必须 0 红。

锚点方向：
- M01 不解信封（回到缺陷原状）；
- M02 非信封回退被异常打断（裸代码块路径回归）；
- M03 信封类型判断失效。

受影响面 = ``tests/test_nodes_callbacks.py::TestPatchApplierOnResample``（10 例）。
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

GATE = "src/graph/nodes.py"

BASE_TESTS = ["tests/test_nodes_callbacks.py::TestPatchApplierOnResample"]

COLLECTED_RE = re.compile(r"(\d+) tests collected")
FAILED_RE = re.compile(r"^FAILED (\S+)", re.MULTILINE)

CONTROL = "N01-control-docstring"

# (锚点名, 文件, 原串, 变异串)
MUTANTS: list[tuple[str, str, str, str]] = [
    (
        "M01-envelope-not-unwrapped",
        GATE,
        "                    if isinstance(_patch_field, str) and _patch_field.strip():",
        "                    if False:  # mutation: 不解 JSON 信封（回到缺陷原状）",
    ),
    (
        "M02-plain-code-fallback-aborted",
        GATE,
        "                except ValueError:\n                    _payload = None",
        "                except ValueError:\n                    raise  # mutation: 非信封回退被异常打断",
    ),
    (
        "M03-envelope-type-check-broken",
        GATE,
        "                if isinstance(_payload, dict):",
        "                if isinstance(_payload, list):  # mutation: 信封类型判断失效",
    ),
    (
        CONTROL,
        GATE,
        '    """2.2 补丁后处理重采样（自 `_patch_applier_node` 提取，行为等价）。',
        '    """**2.2 补丁后处理重采样（自 `_patch_applier_node` 提取，行为等价）。',
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
        "--basetemp=/tmp/pt_cc_mut",
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
