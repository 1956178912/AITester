#!/usr/bin/env python3
"""BJ 轮变异验证：AST 断言一致性检查可测量性的 23 个锚点 + 1 个中性对照。

纪律（与 BA→BI 轮同）：
- 干净副本先全绿且 collected 数一致；
- 每个变异：读取原字节 → 写入变异 → compile() → 收集数核对 → 跑受影响面 →
  记录红数 → sha256 校验后按原字节还原（绝不用 git checkout / git stash）；
- 变异必须转红；中性对照（仅改注释措辞）必须 0 红。

锚点分五类：
- **披露类**（M1–M8、M14–M17、M19）：把"读不懂/没跑过"记成 ok、删掉逐腿记录、
  让明细不返回或不进 state 通道 ⇒ 必须红，证明 status/outcomes 不是装饰；
- **归因类**（M9–M11）：改围栏判据或 reason 归属 ⇒ 必须红，证明"传输层伪影 vs
  产物缺陷"这条分界与逐腿明细都被锁住；
- **聚合类**（M12、M13、M18、M20）：改可解析性判定面、worst-of 次序、聚合值硬写
  ok 或删通道默认值 ⇒ 必须红，证明"独立检查取最差"的方向、`parses_as_module`
  的 ValueError 面与 None 基准都被锁住；
- **判定类**（M21–M23）：反向改 `check_assertions` 的**返回值**（剥围栏、抛穿、
  把 sink 当判定返回）⇒ 必须红，证明 `TestJudgmentInvariance` 不是空断言
  （本轮承诺判定值与判定方向逐字节不变）。
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

OV = "src/tools/oracle_validator.py"
CS = "src/utils/check_status.py"
ND = "src/graph/nodes.py"
ST = "src/graph/state.py"

BJ_TESTS = [
    "tests/test_bj_oracle_unmeasurable.py",
    "tests/test_oracle_validator.py",
    "tests/test_oracle_validator_branches.py",
    "tests/test_nodes_j4_generator_sections.py",
    "tests/test_nodes_refactor_20261019_contracts.py",
    "tests/test_2026_10_05_review_batch.py",
    "tests/test_branch_coverage_fill.py",
    "tests/test_effective_green_ba.py",
    "tests/test_m1_metric_semantics.py",
    "tests/test_scientific_claims.py",
    "tests/test_state_contract_guard.py",
    "tests/test_bg_static_check_outcome.py",
    "tests/test_bh_testless_validation_status.py",
    "tests/test_bi_static_precheck_unmeasurable.py",
]

_BLIND_RECORD = (
    '        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_ERROR, '
    "_unparseable_test_reason(test_code))"
)

# (锚点名, 文件, 原串, 变异串, 额外受影响测试)
MUTANTS: list[tuple[str, str, str, str, list[str]]] = [
    (
        # 披露类：测试文本读不懂 ⇒ 从未扫描，却记成"量过了"。
        "M1-blind-test-looks-measured",
        OV,
        _BLIND_RECORD,
        _BLIND_RECORD.replace("CHECK_ERROR", "CHECK_OK") + "  # mutation",
        [],
    ),
    (
        # 披露类：空输入（压根没有产物）被记成可测量。
        "M2-empty-input-looks-ok",
        OV,
        '        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_DISABLED, "empty_input")',
        '        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_OK, "empty_input")  # mutation',
        [],
    ),
    (
        # 披露类：读不懂时整条不点名（回到 BJ 前的沉默）。
        "M3-blind-test-not-disclosed-at-all",
        OV,
        f"{_BLIND_RECORD}\n        return []",
        "        return []  # mutation: 读不懂不记腿",
        [],
    ),
    (
        # 披露类：抹掉"扫过了但一条 assert 都没有"与"扫过且有断言"的区分。
        "M4-no-assert-reason-collapsed",
        OV,
        '        "assertions_checked" if assert_nodes else "no_assert_statements",',
        '        "assertions_checked",  # mutation: 两种 ok 归因合一',
        [],
    ),
    (
        # 披露类：真扫过了却记 disabled ⇒ 下游把"无疑点"读成"没检查"。
        "M5-measured-leg-looks-unmeasured",
        OV,
        '        "assertion_consistency",\n        CHECK_OK,\n        "assertions_checked" if assert_nodes else "no_assert_statements",',
        '        "assertion_consistency",\n        CHECK_DISABLED,\n        "assertions_checked" if assert_nodes else "no_assert_statements",',
        [],
    ),
    (
        # 披露类：被测侧读不懂 ⇒ 类型推断通道哑火，却记 ok。
        "M6-blind-target-looks-measured",
        OV,
        '        record_check_outcome(outcome_sink, "target_type_inference", CHECK_ERROR, "unparseable_target")',
        '        record_check_outcome(outcome_sink, "target_type_inference", CHECK_OK, "unparseable_target")  # mutation',
        [],
    ),
    (
        # 披露类：没给被测代码被记成"类型推断量过了"。
        "M7-no-target-looks-ok",
        OV,
        '        record_check_outcome(outcome_sink, "target_type_inference", CHECK_DISABLED, "target_not_provided")',
        '        record_check_outcome(outcome_sink, "target_type_inference", CHECK_OK, "target_not_provided")  # mutation',
        [],
    ),
    (
        # 披露类：未提供被测码时不记第二条腿（通道键只剩一条 ⇒ 读成"没有这层"）。
        "M8-target-leg-dropped-when-absent",
        OV,
        '    if not target_code:\n        record_check_outcome(outcome_sink, "target_type_inference", CHECK_DISABLED, "target_not_provided")',
        "    if not target_code:\n        pass  # mutation: 未提供被测码时不记腿",
        [],
    ),
    (
        # 归因类：围栏归因并入泛化 syntax ⇒ "传输层伪影 vs 产物缺陷"分界消失。
        "M9-fence-attribution-lost",
        OV,
        "    if stripped.startswith(_FENCE_MARKER):",
        "    if False:  # mutation: 围栏不再单独归因",
        [],
    ),
    (
        # 归因类：判据放宽成"正文里出现过围栏"⇒ 把产物缺陷误报成传输伪影。
        "M10-fence-attribution-too-broad",
        OV,
        "    stripped = test_code.lstrip()\n    if stripped.startswith(_FENCE_MARKER):",
        "    stripped = test_code.lstrip()\n    if _FENCE_MARKER in test_code:  # mutation: 正文中间的围栏也算伪影",
        [],
    ),
    (
        # 归因类：消费侧降级 warning 的逐腿明细丢失。
        "M11-warning-reason-dropped",
        ND,
        """            ", ".join(f"{o['check']}={o['status']}:{o['reason'] or '-'}" for o in oracle_outcomes),""",
        """            ", ".join(f"{o['check']}={o['status']}" for o in oracle_outcomes),  # mutation: 不报归因""",
        [],
    ),
    (
        # 聚合类：ValueError（孤立代理位）抛穿 ⇒ "读不懂"判定面收窄（BH/BI 同型）。
        "M12-parsability-narrows-to-syntax-error",
        CS,
        "    except (SyntaxError, ValueError):",
        "    except SyntaxError:  # mutation: ValueError 抛穿",
        [],
    ),
    (
        # 聚合类：独立检查必须最差者优先，改成 ok 优先即 BG 的方向。
        "M13-precedence-ok-wins",
        CS,
        "CHECK_STATUS_PRECEDENCE = (CHECK_ERROR, CHECK_UNAVAILABLE, CHECK_DISABLED, CHECK_OK)",
        "CHECK_STATUS_PRECEDENCE = (CHECK_OK, CHECK_ERROR, CHECK_UNAVAILABLE, CHECK_DISABLED)",
        [],
    ),
    (
        # 消费侧：开关关闭时不再点名（读成"本轮没做过任何检查"）。
        "M14-switch-off-not-disclosed",
        ND,
        '    if not _oracle_validate_enabled():\n        record_check_outcome(oracle_outcomes, "assertion_consistency", CHECK_DISABLED, "oracle_validate_disabled")',
        "    if not _oracle_validate_enabled():\n        pass  # mutation: 开关关时不记腿",
        [],
    ),
    (
        # 消费侧：无生成内容与开关关共用一个 reason（成因再次合流）。
        "M15-no-generated-reason-merged",
        ND,
        '        record_check_outcome(oracle_outcomes, "assertion_consistency", CHECK_DISABLED, "no_generated_test")',
        '        record_check_outcome(oracle_outcomes, "assertion_consistency", CHECK_DISABLED, "oracle_validate_disabled")  # mutation',
        [],
    ),
    (
        # 消费侧：整体降级不再发 warning（读数仍在，但运维看不见）。
        "M16-degradation-warning-dropped",
        ND,
        "    if oracle_status != CHECK_OK:",
        "    if False:  # mutation: 降级不告警",
        [],
    ),
    (
        # 消费侧：逐腿明细不并入返回值（通道只剩一个聚合标量）。
        "M17-leg-details-not-returned",
        ND,
        '        "oracle_check_outcomes": list(oracle_outcomes),',
        "",
        [],
    ),
    (
        # 消费侧：聚合恒报 ok（把 worst-of 结果硬写死为可测量）。
        "M18-aggregate-hardcoded-ok",
        ND,
        '        "oracle_check_status": oracle_status,',
        '        "oracle_check_status": "ok",  # mutation: 恒报可测量',
        [],
    ),
    (
        # 通道发布：`_generator_node` 不把明细写进 state 更新（LangGraph 侧看不见）。
        "M19-channel-details-not-published",
        ND,
        '    update["oracle_check_outcomes"] = oracle_check_outcomes',
        "",
        [],
    ),
    (
        # state 侧：通道默认值缺失（未运行时无 None 基准，键直接不存在）。
        "M20-channel-default-dropped",
        ST,
        "        oracle_check_outcomes=None,\n        oracle_check_status=None,",
        "        oracle_check_outcomes=None,  # mutation: 通道默认值缺失",
        [],
    ),
    (
        # 判定类：剥离围栏 ⇒ 盲区产物开始产出疑点（本轮明确不改判定）。
        "M21-judgment-flip-strip-fence",
        OV,
        f"{_BLIND_RECORD}\n        return []",
        f"{_BLIND_RECORD}\n"
        '        test_code = test_code.replace("```python\\n", "").replace("```\\n", "")\n'
        "        if not parses_as_module(test_code):\n"
        "            return []\n"
        "        tree = ast.parse(test_code)",
        [],
    ),
    (
        # 判定类：读不懂改为抛穿 ⇒ "不阻断主流程"这条判定方向被翻转。
        "M22-judgment-flip-blind-raises",
        OV,
        f"{_BLIND_RECORD}\n        return []",
        f'{_BLIND_RECORD}\n        raise SyntaxError("mutation: 读不懂改为抛穿（阻断主流程）")',
        [],
    ),
    (
        # 判定类：把披露列表当判定返回 ⇒ sink 污染返回值契约。
        "M23-judgment-flip-returns-sink",
        OV,
        "    if not test_code or not test_code.strip():\n"
        '        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_DISABLED, "empty_input")\n'
        "        return []",
        "    if not test_code or not test_code.strip():\n"
        '        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_DISABLED, "empty_input")\n'
        "        return list(outcome_sink or [])  # mutation: 把披露当判定返回",
        [],
    ),
    (
        # 中性对照：仅改注释措辞（测试代码→测试文本），不动任何判据 —— 必须 0 红。
        "M24-control-wording",
        OV,
        "        # 测试代码本身读不懂 → 从未做过任何 assert 扫描，保守返回空（不阻断主流程）。",
        "        # 测试文本本身读不懂 → 从未做过任何 assert 扫描，保守返回空（不阻断主流程）。",
        [],
    ),
]

_COLLECTED_RE = re.compile(r"(\d+) tests collected")


def collect_count(paths: list[str]) -> int:
    cmd = [str(PY), "-m", "pytest", *BJ_TESTS, *paths, "--collect-only", "-q"]
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
        *BJ_TESTS,
        *paths,
        "-q",
        "--basetemp=/tmp/pt_bj_mut",
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
