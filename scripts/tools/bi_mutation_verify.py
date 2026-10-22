#!/usr/bin/env python3
"""BI 轮变异验证：写盘前静态预检可测量性的 19 个锚点 + 1 个中性对照。

纪律（与 BA→BH 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改注释措辞）必须 0 红。

锚点分三类：
- **披露类**（M1–M8、M13–M17）：把"读不懂/没跑过"重新记成 ok、删掉点名或
  不并入通道键 ⇒ 必须红，证明状态通道不是装饰；
- **聚合类**（M9–M12）：改可解析性判定面、词表次序或聚合方向 ⇒ 必须红，证明
  "独立检查取最差、可替换后端取任一 ok"两个方向都被锁住；
- **判定类**（M18、M19）：反向改守卫的**返回值** ⇒ 必须红，证明
  `test_judgment_invariance_*` 不是空断言（本轮承诺判定值逐字节不变）。
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

PA = "src/tools/patch_applier.py"
CS = "src/utils/check_status.py"
ND = "src/graph/nodes.py"
TR = "src/tools/type_repair.py"
ST = "src/graph/state.py"

BI_TESTS = [
    "tests/test_bi_static_precheck_unmeasurable.py",
    "tests/test_patch_applier.py",
    "tests/test_patch_applier_remaining_branches.py",
    "tests/test_patch_applier_dynamic_bypass.py",
    "tests/test_nodes_j4_patch_applier.py",
    "tests/test_type_repair_more_branches.py",
    "tests/test_improvements_1_2_2_1_2_2_4_3.py",
    "tests/test_round8_contract_ref_findings.py",
    "tests/test_roadmap_gaps_g1_g2_g3.py",
    "tests/test_bg_static_check_outcome.py",
    "tests/test_bh_testless_validation_status.py",
    "tests/test_testless_validation.py",
    "tests/test_batch_iv.py",
    "tests/test_mdo_20261019_branches.py",
]

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        # 披露类：原文读不懂 ⇒ 从未做符号比较，却记成"量过了"。
        "M1-contract-original-blind-looks-measured",
        PA,
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_ERROR, unparseable)\n'
        '        logger.warning("命名契约检查不可测量（原始代码无法解析，未做任何符号比较，保守放行）")',
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_OK, unparseable)  # mutation\n'
        '        logger.warning("命名契约检查不可测量（原始代码无法解析，未做任何符号比较，保守放行）")',
        [],
    ),
    (
        # 披露类：补丁读不懂导致的拒绝，被当成"已完成测量"的正常契约失败。
        "M2-contract-patched-blind-rejection-looks-measured",
        PA,
        "        status = CHECK_ERROR if unparseable is not None else CHECK_OK",
        "        status = CHECK_OK  # mutation: 拒绝即视为已测量",
        [],
    ),
    (
        # 误归因类：恢复旧措辞"补丁删除了 N 个模块级符号"（补丁从未被解析）。
        "M3-patched-blind-misattributed-as-deletion",
        PA,
        '                "命名契约检查不可测量（补丁代码无法解析）：%d 个模块级符号无法确认仍存在，拒绝应用（未做任何符号比较）",',
        '                "命名契约检查失败：补丁删除了 %d 个模块级符号（P0 1.3）",',
        [],
    ),
    (
        # 披露类：原文读不懂时改走"无模块级符号"通道 ⇒ 空符号集被读成契约成立。
        "M4-original-blind-merged-into-no-symbols",
        PA,
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_ERROR, unparseable)\n'
        '        logger.warning("命名契约检查不可测量（原始代码无法解析，未做任何符号比较，保守放行）")\n'
        "        return True, []",
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_OK, "no_module_level_symbols")\n'
        "        return True, []",
        [],
    ),
    (
        "M5-no-symbols-disclosure-reason-dropped",
        PA,
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_OK, "no_module_level_symbols")',
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_OK)',
        [],
    ),
    (
        # 危险 API 侧：补丁读不懂 ⇒ 差集恒空放行，但不再点名。
        "M6-dangerous-api-blind-not-disclosed",
        PA,
        "    if unparseable is not None:\n"
        '        record_check_outcome(outcome_sink, "dangerous_api", CHECK_ERROR, unparseable)\n'
        "    else:\n"
        '        record_check_outcome(outcome_sink, "dangerous_api", CHECK_OK)',
        "    if False:  # mutation: 读不懂不点名\n"
        '        record_check_outcome(outcome_sink, "dangerous_api", CHECK_ERROR, unparseable)\n'
        "    else:\n"
        '        record_check_outcome(outcome_sink, "dangerous_api", CHECK_OK)',
        [],
    ),
    (
        "M7-dangerous-api-empty-input-looks-ok",
        PA,
        '        record_check_outcome(outcome_sink, "dangerous_api", CHECK_DISABLED, "empty_input")',
        '        record_check_outcome(outcome_sink, "dangerous_api", CHECK_OK, "empty_input")  # mutation',
        [],
    ),
    (
        "M8-contract-switch-off-looks-ok",
        PA,
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_DISABLED, "patch_contract_check_disabled")',
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_OK, "patch_contract_check_disabled")',
        [],
    ),
    (
        # 聚合类：ValueError（孤立代理位）抛穿 ⇒ "读不懂"判定面收窄。
        "M9-parsability-narrows-to-syntax-error",
        CS,
        "    except (SyntaxError, ValueError):",
        "    except SyntaxError:  # mutation: ValueError 抛穿",
        [],
    ),
    (
        # 聚合类：独立检查必须最差者优先，改成 ok 优先即 BG 的方向。
        "M10-precedence-ok-wins",
        CS,
        "CHECK_STATUS_PRECEDENCE = (CHECK_ERROR, CHECK_UNAVAILABLE, CHECK_DISABLED, CHECK_OK)",
        "CHECK_STATUS_PRECEDENCE = (CHECK_OK, CHECK_ERROR, CHECK_UNAVAILABLE, CHECK_DISABLED)",
        [],
    ),
    (
        "M11-unknown-status-defaults-ok",
        CS,
        "        if any(status == candidate for status in values):\n"
        "            return candidate\n"
        "    return CHECK_ERROR",
        "        if any(status == candidate for status in values):\n"
        "            return candidate\n"
        "    return CHECK_OK  # mutation: 未知 status 当作可测量",
        [],
    ),
    (
        "M12-any-measurable-loses-ok-shortcut",
        CS,
        "    if CHECK_OK in values:\n        return CHECK_OK",
        "    if False:  # mutation: 与 BG 口径脱钩\n        return CHECK_OK",
        [],
    ),
    (
        # 消费侧：整体降级不再发 warning（读数仍在，但运维看不见）。
        "M13-nodes-degradation-warning-dropped",
        ND,
        "        if _safety_status != CHECK_OK:",
        "        if False:  # mutation: 降级不告警",
        [],
    ),
    (
        # 消费侧：临时键不并入通道键（LangGraph 侧读不到任何披露）。
        "M14-channel-keys-not-published",
        ND,
        "    if _safety_now:",
        "    if False:  # mutation: 通道键不发布",
        [],
    ),
    (
        "M15-channel-defaults-dropped",
        ST,
        "        safety_check_outcomes=None,\n        safety_check_status=None,",
        "        safety_check_outcomes=None,  # mutation: 通道默认值缺失",
        [],
    ),
    (
        "M16-type-repair-default-looks-measured",
        TR,
        '        "contract_status": CHECK_DISABLED,',
        '        "contract_status": CHECK_OK,  # mutation: 未评估当作已评估',
        [],
    ),
    (
        "M17-type-repair-exception-not-disclosed",
        TR,
        '                    record_check_outcome(_contract_outcomes, "naming_contract", CHECK_ERROR, "contract_check_exception")\n'
        '                    result["contract_status"] = CHECK_ERROR\n'
        '                    result["contract_reason"] = "contract_check_exception"',
        '                    result["contract_status"] = CHECK_OK  # mutation: 异常不点名\n'
        '                    result["contract_reason"] = ""',
        [],
    ),
    (
        # 判定类：把"保守放行"翻成"保守拒绝" ⇒ 判定值不变性锁必须红。
        "M18-judgment-flip-original-blind-rejects",
        PA,
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_ERROR, unparseable)\n'
        '        logger.warning("命名契约检查不可测量（原始代码无法解析，未做任何符号比较，保守放行）")\n'
        "        return True, []",
        '        record_check_outcome(outcome_sink, "naming_contract", CHECK_ERROR, unparseable)\n'
        '        logger.warning("命名契约检查不可测量（原始代码无法解析，未做任何符号比较，保守放行）")\n'
        "        return False, sorted(original_symbols | patched_symbols)",
        [],
    ),
    (
        # 判定类：危险差集改成"只比对补丁侧" ⇒ 既有危险调用被算成新增。
        "M19-judgment-flip-dangerous-diff-drops-baseline",
        PA,
        "    before = _collect_dangerous_calls(original_code)\n"
        "    after = _collect_dangerous_calls(patched_code)\n"
        "    added = sorted(after - before)",
        "    before = _collect_dangerous_calls(original_code)\n"
        "    after = _collect_dangerous_calls(patched_code)\n"
        "    added = sorted(after)  # mutation: 差集不减基准",
        [],
    ),
    (
        # 中性对照：仅改注释措辞（基准→原文），不动任何判据 —— 必须 0 红。
        "M20-control-wording",
        PA,
        '    # 基准读不懂 ⇒ 没有可比对的符号集：保守放行口径不变，但不得记成"契约通过"。',
        '    # 原文读不懂 ⇒ 没有可比对的符号集：保守放行口径不变，但不得记成"契约通过"。',
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BI_TESTS, *paths, "--collect-only", "-q"]
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
        *BI_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bi_mut",
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
        print(f"[{name}] rc={rc} red={red} collected={mutated_collected} {verdict}\n{tail}")
        results.append((name, verdict, red))

    print("\n=== SUMMARY ===")
    for name, verdict, red in results:
        print(f"{verdict:14s} red={red:<3d} {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
