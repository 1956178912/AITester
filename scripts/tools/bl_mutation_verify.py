#!/usr/bin/env python3
"""BL 轮变异验证：消费侧「空值 + status」双读锚点 22 个 + 1 个中性对照。

纪律（与 BA→BH 轮同）：
- 基线先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改措辞）必须 0 红。

锚点分三组：
- 原语（M1–M3）：`status_for_check` 的"该腿没记录 ⇒ None""按腿挑选""缺 status ⇒ error"；
- 消费侧（M4–M8、M14–M22）：披露文本、判定方向不变、开关两分支键集合、调用点取 status、
  S2 守卫、trace 载荷、benchmark 行、state 声明与默认值；
- 读者（M9–M13）：`_UNMEASURABLE_STATUSES` 词表、键集合、模式体、注册表、`_flatten_record`。
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

BL_TESTS = ["tests/test_bl_status_readers_outcome.py"]
CS = "src/utils/check_status.py"
RA = "src/graph/risk_approval.py"
AT = "src/observability/agent_telemetry.py"

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    # ─── 原语：status_for_check ────────────────────────────────────────────
    (
        # "本轮没做这条腿"被读成"做了且可信" ⇒ 空结果白拿"可作证据"资格。
        "M1-leg-absent-defaults-ok",
        CS,
        "    if not leg:\n        return None",
        "    if not leg:\n        return CHECK_OK  # mutation: 没做这条腿当作可信",
        ["tests/test_bi_static_precheck_unmeasurable.py"],
    ),
    (
        # 不分腿 ⇒ "危险 API 腿读不懂"会记到命名契约头上（BL 按腿取 status 的根因）。
        "M2-leg-name-ignored",
        CS,
        '        if isinstance(outcome, dict) and outcome.get("check") == check',
        "        if isinstance(outcome, dict)  # mutation: 不分腿",
        [],
    ),
    (
        "M3-statusless-record-becomes-ok",
        CS,
        '        str(outcome.get("status", ""))',
        '        str(outcome.get("status") or CHECK_OK)  # mutation: 缺 status 当作 ok',
        [],
    ),
    # ─── 消费侧：risk_approval 双读 ────────────────────────────────────────
    (
        "M4-disclosure-never-fires",
        RA,
        '    if not contract_status or contract_status == CHECK_OK:\n        return ""',
        "    if True:  # mutation: 永不披露\n        return",
        [],
    ),
    (
        # 保守边界：None（本轮没这个键 / 历史行）不得被读成"没测成"。
        "M5-legacy-none-counts-as-unmeasurable",
        RA,
        "    if not contract_status or contract_status == CHECK_OK:",
        "    if contract_status == CHECK_OK:  # mutation: None 也算没测成",
        [],
    ),
    (
        # 方向锚点：把 error 翻成拒绝 = 路由方向变更（需 A/B 数据与预注册判据）。
        "M6-disclosure-flips-judgment",
        RA,
        "        note = _contract_disclosure(contract_status)\n        if note:\n            reasons.append(note)",
        "        note = _contract_disclosure(contract_status)\n"
        "        if note:\n            reasons.append(note)\n"
        "            factor = max(factor, 0.9)  # mutation: 翻成拒绝",
        ["tests/test_risk_approval_matrix.py"],
    ),
    (
        # 消费点可见性：reasons 全仓无人读，写在里面等于没写（BL 手册 §3）。
        "M7-consumer-warning-dropped",
        RA,
        '    _unmeasurable = [r for r in reasons if r.startswith("contract_unmeasurable(")]',
        "    _unmeasurable: list[str] = []  # mutation: 消费点不再披露",
        [],
    ),
    (
        "M8-disabled-branch-loses-status-key",
        RA,
        '            "contract_status": contract_status,\n            "pause_requested": False,',
        '            "pause_requested": False,',
        [],
    ),
    (
        # 判定侧仍不取通道值 ⇒ 四行读数继续折叠（本轮缺陷族的原始形状）。
        "M9-callsite-stops-feeding-status",
        "src/graph/debugger.py",
        '            contract_status=state.get("contract_status"),\n',
        "",
        ["tests/test_debugger_node_branches.py"],
    ),
    # ─── 读者：agent_telemetry 失败模式 ────────────────────────────────────
    (
        "M10-unavailable-dropped-from-vocabulary",
        AT,
        "_UNMEASURABLE_STATUSES: tuple[str, ...] = (CHECK_ERROR, CHECK_UNAVAILABLE)",
        "_UNMEASURABLE_STATUSES: tuple[str, ...] = (CHECK_ERROR,)  # mutation",
        [],
    ),
    (
        # 键集合悄悄删一个：读者与词表同源时自证循环恒真，靠字面集合锁抓。
        "M11-channel-key-dropped",
        AT,
        '    "static_check_status",\n',
        "",
        [],
    ),
    (
        "M12-pattern-body-silenced",
        AT,
        '    return any(str(record.get(key, "")).lower() in _UNMEASURABLE_STATUSES for key in _UNMEASURABLE_STATUS_KEYS)',
        "    return False  # mutation: 读者退回沉默",
        ["tests/test_g8_g2_g4_g5_g6_g7_g1.py"],
    ),
    (
        "M13-pattern-unregistered",
        AT,
        '    "check_unmeasurable": _pattern_check_unmeasurable,\n',
        "",
        ["tests/test_g8_g2_g4_g5_g6_g7_g1.py"],
    ),
    (
        "M14-trace-inner-keys-not-lifted",
        AT,
        "    if isinstance(output, dict):\n        for key, value in output.items():\n            flat.setdefault(key, value)",
        "    if False:  # mutation: 不抬 output 内层\n"
        "        for key, value in output.items():\n            flat.setdefault(key, value)",
        ["tests/test_g8_g2_g4_g5_g6_g7_g1.py"],
    ),
    # ─── 发布面与其余消费面 ────────────────────────────────────────────────
    (
        "M15-s2-guard-status-silenced",
        "src/tools/patch_applier.py",
        "        if _guard_status is not None and _guard_status != CHECK_OK:",
        "        if False:  # mutation: 读不懂不再披露",
        ["tests/test_patch_applier.py"],
    ),
    (
        "M16-s2-guard-flips-to-refusal",
        "src/tools/patch_applier.py",
        "        if _guard_status is not None and _guard_status != CHECK_OK:\n            logger.warning(",
        "        if _guard_status is not None and _guard_status != CHECK_OK:\n"
        "            return code, False  # mutation: 把没测成翻成拒绝\n            logger.warning(",
        ["tests/test_patch_applier.py", "tests/test_bi_static_precheck_unmeasurable.py"],
    ),
    (
        # 用多腿聚合冒充单腿 status（BL 按腿取的原语被绕开）。
        "M17-per-leg-replaced-by-aggregate",
        "src/graph/nodes.py",
        '        safety_update["contract_status"] = status_for_check(_safety_now, "naming_contract")',
        '        safety_update["contract_status"] = safety_update["safety_check_status"]  # mutation: 聚合冒充单腿',
        ["tests/test_bi_static_precheck_unmeasurable.py"],
    ),
    (
        "M18-trace-loses-oracle-status",
        "src/graph/nodes.py",
        '        output_summary={"generated_test_len": len(generated_test), "oracle_check_status": oracle_check_status},',
        '        output_summary={"generated_test_len": len(generated_test)},  # mutation: status 不进 trace',
        [],
    ),
    (
        "M19-benchmark-row-loses-status",
        "experiments/run_benchmark.py",
        '            "contract_status": final_state.get("contract_status"),\n',
        "",
        [],
    ),
    (
        "M20-state-channel-not-declared",
        "src/graph/state.py",
        "    contract_status: str | None\n",
        "",
        ["tests/test_bi_static_precheck_unmeasurable.py"],
    ),
    (
        "M21-state-default-not-published",
        "src/graph/state.py",
        "        contract_status=None,\n",
        "",
        [],
    ),
    (
        # state.py 的"读 count 必须结合 status"口径注释重新变成没有实现。
        "M22-static-layer-branch-silenced",
        "src/agents/debugger.py",
        "            elif static_check_status not in (None, CHECK_OK):",
        "            elif False:  # mutation: 退回沉默",
        ["tests/test_closeout_k_debugger.py"],
    ),
    (
        # 中性对照：仅改 docstring 措辞（"地基："→"地基是："），不动任何判据 —— 必须 0 红。
        "M23-control-wording",
        CS,
        "    BL 轮消费侧双读的地基：``worst_check_status`` 把多道独立预检聚合成一个",
        "    BL 轮消费侧双读的地基是：``worst_check_status`` 把多道独立预检聚合成一个",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BL_TESTS,
        *paths,
        "--collect-only",
        "-q",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
    ]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=300)
    match = _COLLECTED_RE.search(proc.stdout + proc.stderr)
    if proc.returncode != 0 or not match:
        raise RuntimeError(f"collect failed rc={proc.returncode}: {(proc.stdout + proc.stderr)[-500:]}")
    return int(match.group(1))


def run_tests(paths: list[str]) -> tuple[int, int, str]:
    cmd = [
        str(PY),
        "-m",
        "pytest",
        *BL_TESTS,
        *paths,
        "-q",
        "-o",
        "addopts=",
        "--no-cov",
        "--basetemp=/tmp/pt_bl_mut",
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
    output = proc.stdout + proc.stderr
    red = len(re.findall(r"^FAILED ", output, flags=re.MULTILINE))
    tail = "\n".join(output.splitlines()[-3:])
    return proc.returncode, red, tail


def main() -> int:
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
        if name.endswith("control-wording"):
            verdict = "OK-NEUTRAL" if rc == 0 else "FALSE-POSITIVE"
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict}\n{tail}")
        results.append((name, verdict, red))

    print("\n=== SUMMARY ===")
    for name, verdict, red in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    killed = sum(1 for _, v, _ in results if v == "FAILED")
    neutral = sum(1 for _, v, _ in results if v == "OK-NEUTRAL")
    bad = [n for n, v, _ in results if v not in ("FAILED", "OK-NEUTRAL")]
    print(f"\n killed={killed}/{len(results)}  中性对照={neutral}  异常={bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
