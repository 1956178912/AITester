#!/usr/bin/env python3
"""BN 轮变异验证：状态通道落盘归位的 22 个锚点 + 1 个门禁面 + 1 个接线面 + 1 个中性对照。

纪律（与 BA→BM 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改措辞）必须 0 红；
- 收尾做 `# mutation:` 残留扫描（标记带冒号，避免命中仓内既有的 mutation 字样），
  确认还原后源码里一个变异标记都不剩。

锚点面（每处都是"登记动作本身"，不是判定逻辑）：
  D1—D10  `_dump_state_artifacts` 白名单的十个通道（读错源键 ⇒ 通道恒 None）；
  R1—R6   `_build_task_result` 成功分支的六键；
  F1—F6   `_build_task_result` 失败分支的六键（整键删除 ⇒ 键集合漂移）；
  G1      门禁声明面（只认 `_status` ⇒ 三个 `_outcomes` 通道脱离审计）；
  W1      Makefile `gates` 依赖（摘掉 status-persistence ⇒ 说好的阻断项不在链里）。
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

BN_TESTS = "tests/test_bn_status_persistence.py"
RB = "experiments/run_benchmark.py"

#: 十个通道在 raw 白名单里的登记行（8 空格缩进；结果行同键是 12 空格，天然可分）
_DUMP_CHANNELS: tuple[str, ...] = (
    "contract_status",
    "static_check_status",
    "static_check_outcomes",
    "safety_check_status",
    "safety_check_outcomes",
    "oracle_check_status",
    "oracle_check_outcomes",
    "detection_first_status",
    "edit_intent_status",
    "deterministic_repair_status",
)
#: 本轮补进结果行的六键
_ROW_CHANNELS: tuple[str, ...] = _DUMP_CHANNELS[1:7]


def _dump_mutant(key: str) -> tuple[str, str, str, str]:
    # 前置换行把锚点钉在行首：结果行同键是 12 空格缩进，纯子串匹配会命中 2 次。
    old = f'\n        "{key}": final_state.get("{key}"),'
    new = f'\n        "{key}": final_state.get("{key}_mutated"),  # mutation: raw whitelist reads a nonexistent key'
    return f"D-{key}", RB, old, new


def _row_success_mutant(key: str) -> tuple[str, str, str, str]:
    old = f'            "{key}": final_state.get("{key}"),'
    new = f'            "{key}": final_state.get("{key}_mutated"),  # mutation: result row stops carrying the channel'
    return f"R-{key}", RB, old, new


def _row_failure_mutant(key: str) -> tuple[str, str, str, str]:
    old = f'        "{key}": None,\n'
    new = ""  # 整键删除：模拟"只登记成功分支、忘了失败分支"
    return f"F-{key}", RB, old, new


MUTANTS: list[tuple[str, str, str, str, list[str]]] = (
    [(*_dump_mutant(key), []) for key in _DUMP_CHANNELS]
    + [(*_row_success_mutant(key), []) for key in _ROW_CHANNELS]
    + [(*_row_failure_mutant(key), []) for key in _ROW_CHANNELS]
    + [
        (
            "G1-declared-surface-drops-outcomes",
            "scripts/gates/check_status_persistence.py",
            'CHANNEL_SUFFIXES: tuple[str, ...] = ("_status", "_outcomes")',
            'CHANNEL_SUFFIXES: tuple[str, ...] = ("_status",)  # mutation: outcomes channels leave the audit surface',
            [],
        ),
        (
            "W1-gate-missing-from-chain",
            "Makefile",
            "zero-assert ast-guards status-persistence  ##",
            "zero-assert ast-guards  ##",
            [],
        ),
        (
            "M-control-wording",
            RB,
            "        # 本轮只做归位：判定值与判定方向逐字节不变，历史工件一个字节不动，",
            "        # BN 本轮只做归位：判定值与判定方向逐字节不变，磁盘上的历史工件一个字节不动，",
            [],
        ),
    ]
)

_COLLECTED_RE = re.compile(r"(\d+) tests collected")
_TOUCHED = sorted({rel for _, rel, *_ in MUTANTS})


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", BN_TESTS, *paths, "--collect-only", "-q"]
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
        BN_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bn_mut",
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
    print(f"=== 基线全绿核对（{BN_TESTS}）===")
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
    print(f"\n归位锚点 {len(mutants)} 个：击杀 {len(mutants) - len(survivors)}，未击杀/异常 {survivors or '无'}")
    print(f"中性对照（{control}）判读：{control_verdict or '未执行'}——口径要求它 0 红（SURVIVED）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
