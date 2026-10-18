#!/usr/bin/env python3
"""N 轮全功能 e2e 探针——**规约/逻辑链路组**（logic / oracle）。

覆盖 M 轮与 L 轮的核心能力面：
- SpecIR 解析（NL 通道 + 表达式通道透传）与保守降级；
- SpecExpr 白名单（危险表达式拒绝、可编译子句接受）与 compile_readiness 分通道口径；
- 确定性 oracle 编译（`compile_spec_oracle`：ast 可解析、签名感知绑定、无材料保守返回空）；
- SMT 见证层（`generate_spec_witnesses`：sat/边界见证，不可翻译子句保守返回 []）；
- **spec_anchor → oracle 接线**（N-3 修复点：锚材料臂在没有 planner `test_plan` 时也能尝试注入）；
- oracle 独立判读字段与 replay 工具入口（N-3：`oracle_suite_verdict` / `llm_suite_detection_rate`）；
- 停滞检测开关（COVERAGE_STALL_DETECT_ENABLE + 消融臂互斥）；
- T4：A-19 抢占优先级（repair-invalid 同迭代平局下停滞优先；默认关零变化）与
  回滚 verdict 结果行 schema（patch_rollback_verdict / patch_rolled_back 双分支键集合同构）；
- mutation advisor 环装配（logic 档）与 branch coverage 注入测量；
- logic 档最小真实任务（真 LLM ≤1 调用）：spec 相关状态字段落态。

零 LLM 为主；仅最后一个探针 requires_llm=True。
"""

from __future__ import annotations

import ast
import os
import sys

from scripts.tools.e2e_probe import (
    Probe,
    error,
    fail,
    invoke_workflow,
    llm_enabled,
    make_temp_dir,
    ok,
    skip,
)


def _sample_logic_analysis() -> dict:
    """构造一份真实形态的 Planner logic_analysis（NL + expr 双通道）。"""
    return {
        "function_name": "find_max",
        "input_domain": "非空整数列表",
        "output_domain": "整数（列表最大值）",
        "preconditions": ["arr 非空"],
        "postconditions": ["结果等于 arr 中的最大值"],
        "preconditions_expr": ["len(arr) > 0"],
        "postconditions_expr": ["result >= max(arr)"],
        "invariants_expr": [],
        "edge_cases": ["单元素列表"],
        "spec_source": "logic_analysis",
    }


def _parse_sample():
    from src.specs.spec_ir import parse_logic_analysis

    return parse_logic_analysis(_sample_logic_analysis(), boundary_triplets=[([1], 1, "单元素边界")])


def probe_spec_ir_parse():
    """SpecIR 解析：双通道字段透传 + 边界三元组映射 + 空材料保守降级。"""
    spec = _parse_sample()
    if not spec:
        return fail("parse_logic_analysis 对有效 logic_analysis 返回 None")
    checks = {
        "function_name": spec.get("function_name") == "find_max",
        "preconditions": bool(spec.get("preconditions")),
        "postconditions": bool(spec.get("postconditions")),
        "expr_channel": bool(spec.get("preconditions_expr")) and bool(spec.get("postconditions_expr")),
        "boundaries": bool(spec.get("boundaries")),
    }
    if not all(checks.values()):
        return fail(f"SpecIR 字段缺失：{checks}", spec_keys=sorted(spec.keys()))
    # 负控：空材料必须返回 None（保守降级，不得造空 spec）
    from src.specs.spec_ir import parse_logic_analysis

    if parse_logic_analysis({}) is not None or parse_logic_analysis(None) is not None:
        return fail("空 logic_analysis 未保守降级为 None")
    return ok("SpecIR 双通道解析正常，空材料保守降级", checks=checks, spec_keys=sorted(spec.keys()))


def probe_spec_expr_whitelist():
    """表达式白名单：危险/不可编译子句被拒，可编译子句被接受；readiness 计率一致。"""
    from src.specs.spec_ir_v2 import clause_reject_reason, compile_readiness

    spec = _parse_sample()
    readiness = compile_readiness(spec, ["arr"])
    # 可编译子句：接受
    reason_ok = clause_reject_reason("len(arr) > 0", "precondition", ["arr"])
    # 危险子句：必须拒绝（白名单/形式门不允许调用逃逸）
    risky = ["__import__('os').system('echo pwned')", "open('/etc/passwd').read()", "eval('1+1')"]
    rejected = {}
    for clause in risky:
        rejected[clause] = clause_reject_reason(clause, "precondition", ["arr"])
    if any(not r for r in rejected.values()):
        return fail(f"危险子句未被拒绝：{rejected}", readiness=readiness)
    if reason_ok:
        # 可编译子句不应因白名单被拒（历史口径：len() 在允许内建名单）
        return fail(f"合法子句被误拒：{reason_ok}", risky_rejected=rejected, readiness=readiness)
    if not (0.0 <= readiness <= 1.0):
        return fail(f"compile_readiness 越界：{readiness}")
    return ok(
        f"白名单正常：危险子句拒绝 {len(rejected)}/3，可编译子句接受，readiness={readiness:.2f}",
        readiness=readiness,
        risky_rejected=rejected,
    )


def probe_spec_oracle_compile():
    """确定性 oracle 编译：ast 可解析、含标准 oracle 测试名、签名感知绑定、无材料返回空串。"""
    from src.specs.spec_ir_v2 import compile_spec_oracle

    spec = _parse_sample()
    code = compile_spec_oracle(spec, target_module="target_mod", target_function="find_max", signature_params=["arr"])
    if not code.strip():
        return fail("compile_spec_oracle 对有效 spec 返回空串")
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return fail(f"oracle 产物不是合法 Python：{exc}")
    funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if "test_specir_v2_oracle" not in funcs:
        return fail(f"缺少标准 oracle 测试名：{funcs}")
    assertions = [n for n in ast.walk(tree) if isinstance(n, ast.Assert)]
    # 负控：无模块/无函数/无 spec → 空串（保守，不产"只有注释"的假测试）
    empties = {
        "no_spec": compile_spec_oracle(None, "m", "f", ["x"]),
        "no_module": compile_spec_oracle(spec, "", "find_max", ["arr"]),
        "no_function": compile_spec_oracle(spec, "m", "", ["arr"]),
    }
    bad_empties = {k: bool(v) for k, v in empties.items() if v}
    if bad_empties:
        return fail(f"无材料时未保守返回空串：{bad_empties}")
    return ok(
        f"确定性 oracle 编译正常（{len(code)} 字符，{len(assertions)} 条断言，ast 合法）",
        code_len=len(code),
        assertions=len(assertions),
        funcs=funcs,
    )


def probe_smt_witness():
    """SMT 见证层：sat 模型 + 数值边界见证；不可翻译子句保守返回 []（不是崩溃）。"""
    from src.specs.spec_smt import generate_spec_witnesses, smt_available

    if not smt_available():
        return skip("z3-solver 不可用（可选依赖）")
    spec = {"preconditions": ["x > 0"], "postconditions": ["result >= x"], "function_name": "f"}
    witnesses = generate_spec_witnesses(spec, ["x"])
    if not witnesses:
        return fail("SMT 见证层对可翻译前件未产出见证（z3 可用时应至少 sat）")
    kinds = {w.get("kind") for w in witnesses}
    sat_ok = any(w.get("kind") == "sat" and (w.get("inputs") or {}).get("x", 0) > 0 for w in witnesses)
    if not sat_ok:
        return fail(f"sat 见证不满足前件（x>0）：{witnesses}")
    # 负控：不可翻译前件（含调用/属性）必须保守返回 [] 而非抛异常
    degraded = generate_spec_witnesses({"preconditions": ["parse(x) and obj.attr > 0"]}, ["x"])
    if degraded:
        return fail(f"不可翻译子句未保守降级：{degraded}")
    return ok(
        f"SMT 见证层正常：{len(witnesses)} 个见证（kinds={sorted(kinds)}），不可翻译保守降级", witnesses=witnesses[:3]
    )


def probe_spec_anchor_oracle_wiring():
    """N-3 接线：仅 spec_anchor 材料的臂（无 planner test_plan）也能尝试 oracle 注入。"""
    from src.graph.nodes import _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED, _append_spec_oracle_to_test_with_verdict

    state = {
        "module_name": "target_mod",
        "target_function": "find_max",
        "target_code": "",
        "spec_anchor": {"function_name": "find_max", "logic_analysis": _sample_logic_analysis()},
    }
    test_code = "from target_mod import find_max\n\ndef test_placeholder():\n    assert find_max([1]) == 1\n"
    try:
        merged, injected, verdict = _append_spec_oracle_to_test_with_verdict(test_code, state)
    except Exception as exc:
        return error(f"spec_anchor 接线调用抛异常：{type(exc).__name__}: {exc}")
    if verdict == _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED:
        return fail(
            "接线缺口未修：只有 spec_anchor 材料时 verdict 仍为 not_attempted（N-3 修复点）",
            verdict=verdict,
            injected=injected,
        )
    if injected and "test_specir_v2_oracle" not in merged:
        return fail("verdict 非 not_attempted 但注入产物缺失 oracle 测试名", verdict=verdict)
    # 负控：完全无材料 → not_attempted
    _, injected_empty, verdict_empty = _append_spec_oracle_to_test_with_verdict(
        test_code, {"module_name": "m", "target_function": "f"}
    )
    if verdict_empty != _SPEC_ORACLE_VERDICT_NOT_ATTEMPTED or injected_empty:
        return fail(f"无材料负控失败：verdict={verdict_empty}, injected={injected_empty}")
    return ok(
        f"spec_anchor 接线正常：verdict={verdict}，injected={injected}；无材料负控 not_attempted", verdict=verdict
    )


def probe_oracle_independent_judging():
    """N-3 独立判读：结果行字段 + replay 工具入口 + 默认关零行为差异。"""
    # 1) 结果行走廊：run_benchmark 行构造包含两键（源码级断言，避免跑真批次）
    from pathlib import Path

    rb = Path(__file__).resolve().parents[2] / "experiments" / "run_benchmark.py"
    source = rb.read_text(encoding="utf-8")
    missing = [k for k in ('"llm_suite_detection_rate"', '"oracle_suite_verdict"') if k not in source]
    if missing:
        return fail(f"结果行缺少独立判读字段：{missing}")
    # 2) _m1_metrics 独立判定函数在场且 None 输入 fail-closed
    from experiments._m1_metrics import _compute_llm_suite_detection_rate, _compute_oracle_suite_verdict

    if _compute_llm_suite_detection_rate(None, None) is not None:
        return fail("_compute_llm_suite_detection_rate(None, None) 未返回 None（fail-closed 破坏）")
    verdict = _compute_oracle_suite_verdict(None, None)
    if not isinstance(verdict, str) or not verdict:
        return fail(f"oracle_suite_verdict 空值语义异常：{verdict!r}")
    # 3) replay 工具支持 --independent-judging（N-3 交付入口）
    import subprocess

    proc = subprocess.run(
        [sys.executable, "-m", "experiments.oracle_quality_replay", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parents[2]),
    )
    if "--independent-judging" not in (proc.stdout + proc.stderr):
        return fail("oracle_quality_replay 缺少 --independent-judging 入口（N-3 交付）")
    # 4) 设计文档登记独立判读口径（防文档漂移；缺失仅记录不阻断）
    design = Path(__file__).resolve().parents[2] / "docs" / "design" / "oracle_quality_metric.md"
    documented = design.exists() and "独立判读" in design.read_text(encoding="utf-8")
    return ok(
        "oracle 独立判读字段/函数/replay 入口齐备，None 输入 fail-closed"
        + ("，设计文档已登记" if documented else "（设计文档未见'独立判读'字样，记为观测）"),
        verdict=verdict,
        documented=documented,
    )


def probe_stagnation_switch():
    """停滞检测开关：env 读取、消融臂互斥、默认关。"""
    from src.graph import workflow

    default_value = workflow._coverage_stall_enabled()
    os.environ["COVERAGE_STALL_DETECT_ENABLE"] = "true"
    try:
        enabled = workflow._coverage_stall_enabled()
    finally:
        os.environ["COVERAGE_STALL_DETECT_ENABLE"] = "false"
    disabled = workflow._coverage_stall_enabled()
    os.environ.pop("COVERAGE_STALL_DETECT_ENABLE", None)
    if not (enabled and not disabled):
        return fail(f"停滞开关不生效：enabled={enabled}, disabled={disabled}, default={default_value}")
    # 消融臂互斥（run_benchmark._apply_stagnation_arm fail-closed）
    from experiments.run_benchmark import _apply_stagnation_arm

    try:
        _apply_stagnation_arm(enable=True, disable=True)
    except ValueError:
        mutual_exclusion = True
    else:
        mutual_exclusion = False
        os.environ.pop("COVERAGE_STALL_DETECT_ENABLE", None)
    if not mutual_exclusion:
        return fail("--enable-stagnation 与 --no-stagnation 未互斥（静默取一）")
    return ok(f"停滞开关正常（default={default_value}，env true→{enabled}/false→{disabled}，消融臂互斥）")


def probe_mutation_advisor_assembly():
    """mutation advisor 环装配：logic 档开时在场、关时不在（零 LLM 装配断言）。"""
    from src.graph import workflow

    original = os.environ.get("MUTATION_ADVISOR_ENABLE")
    try:
        os.environ["MUTATION_ADVISOR_ENABLE"] = "true"
        graph_on = workflow.build_workflow(planner=True, debugger=True)
        nodes_on = set(getattr(graph_on, "nodes", {}) or {})
        os.environ["MUTATION_ADVISOR_ENABLE"] = "false"
        graph_off = workflow.build_workflow(planner=True, debugger=True)
        nodes_off = set(getattr(graph_off, "nodes", {}) or {})
    finally:
        if original is None:
            os.environ.pop("MUTATION_ADVISOR_ENABLE", None)
        else:
            os.environ["MUTATION_ADVISOR_ENABLE"] = original
    if "mutation_advisor" not in nodes_on:
        return fail(f"mutation_advisor 开环未装配：nodes={sorted(nodes_on)}")
    if "mutation_advisor" in nodes_off:
        return fail("mutation_advisor 关闭时仍装配（开关无效）")
    return ok(f"mutation advisor 环装配正确（开={len(nodes_on)} 节点 / 关={len(nodes_off)} 节点）")


def probe_branch_coverage_inject():
    """branch coverage 注入测量：真实测出分支覆盖，空测试保守返回 None。"""
    from src.tools.branch_coverage_inject import (
        branch_coverage_inject_enabled,
        build_branch_coverage_prompt_section,
        measure_branch_coverage,
    )

    tmpdir = make_temp_dir("e2e_branch_")
    target = tmpdir / "target_mod.py"
    target.write_text(
        "def classify(n):\n"
        "    if n > 0:\n"
        "        return 'pos'\n"
        "    if n < 0:\n"
        "        return 'neg'\n"
        "    return 'zero'\n",
        encoding="utf-8",
    )
    test_code = "from target_mod import classify\n\ndef test_pos():\n    assert classify(1) == 'pos'\n"
    result = measure_branch_coverage(str(target), test_code, "target_mod", cwd=str(tmpdir))
    if result is None:
        return fail("branch 覆盖测量返回 None（coverage 不可用或测量失败）")
    if not (0.0 <= float(result.get("branch_coverage", -1)) <= 100.0):
        return fail(f"branch_coverage 越界：{result}")
    if not result.get("missing_branches"):
        return fail(f"部分覆盖用例未报告 missing_branches：{result}")
    # 负控：空测试保守 None；prompt 段对 None / 有值两种输入都不崩
    if measure_branch_coverage(str(target), "", "target_mod", cwd=str(tmpdir)) is not None:
        return fail("空测试未保守返回 None")
    section = build_branch_coverage_prompt_section(result)
    if not isinstance(section, str) or not section.strip():
        return fail("branch 覆盖 prompt 段为空")
    return ok(
        f"branch 覆盖测量真实可用（coverage={result['branch_coverage']:.1f}%，missing={len(result['missing_branches'])}，开关默认={branch_coverage_inject_enabled()}）",
        branch_coverage=result["branch_coverage"],
        missing=len(result["missing_branches"]),
    )


def probe_logic_profile_spec_fields():
    """logic 档最小真实任务（真 LLM）：spec 链路状态字段落态（不是 None 丢失）。"""
    _saved = {key: os.environ.get(key) for key in ("AITESTER_PROFILE", "TEMPERATURE", "LLM_THINKING_MODE")}
    os.environ.setdefault("AITESTER_PROFILE", "logic")
    os.environ.setdefault("TEMPERATURE", "0.0")
    os.environ.setdefault("LLM_THINKING_MODE", "disabled")
    target_code = (
        '"""数值工具（带 docstring 规约）。"""\n\n\n'
        "def find_max(arr):\n"
        '    """返回非空整数列表的最大值。\n\n'
        "    前置：arr 非空；后置：返回值等于 arr 中最大元素。\n"
        '    """\n'
        "    arr = list(arr)\n"
        "    return max(arr)\n"
    )
    try:
        state, elapsed = invoke_workflow(
            target_code,
            module_name="spec_target",
            target_function="find_max",
            planner=True,
            debugger=False,
            max_iterations=1,
        )
    finally:
        for _key, _old in _saved.items():
            if _old is None:
                os.environ.pop(_key, None)
            else:
                os.environ[_key] = _old
    required = ("spec_compile_rate", "spec_ir", "test_plan", "generated_test", "stop_reason")
    missing = [key for key in required if key not in state]
    if missing:
        return fail(f"logic 档终态缺字段：{missing}", stop_reason=state.get("stop_reason"))
    spec_ir = state.get("spec_ir")
    compile_rate = state.get("spec_compile_rate")
    # 功能断言：spec 材料在场（planner 有 docstring 可抽）且计率已计算（可为 0.0，不得缺失）
    if spec_ir is None:
        return fail(
            "logic 档 planner 启用但 spec_ir 始终为 None（规约材料未落态）", stop_reason=state.get("stop_reason")
        )
    if compile_rate is None:
        return fail("spec_compile_rate 未计算（应为 float，可为 0.0）", stop_reason=state.get("stop_reason"))
    return ok(
        f"logic 档 spec 链路正常（{elapsed:.1f}s，compile_rate={compile_rate}，generated_test={'有' if state.get('generated_test') else '无'}）",
        compile_rate=compile_rate,
        elapsed_s=round(elapsed, 2),
    )


def probe_oracle_instrument_safety():
    """O-1 仪器加固：oracle 执行期崩溃 → pytest.skip（不是 fail/fp），断言失败仍 fail。"""
    import subprocess
    import sys as _sys

    from src.specs.spec_ir import parse_logic_analysis
    from src.specs.spec_ir_v2 import compile_spec_oracle

    tmpdir = make_temp_dir("e2e_oracle_safety_")
    target = tmpdir / "safe_target.py"
    # 除零函数：边界候选 [0,0] 违反"前置 b!=0"（NL 前件不可机检）→ 调用抛
    # ZeroDivisionError。加固前该 oracle 在 fixed 侧恒红（fp）；加固后应 skip。
    target.write_text("def divide(a, b):\n    return a // b\n", encoding="utf-8")
    la = {
        "function_name": "divide",
        "preconditions": ["b != 0"],
        "postconditions_expr": ["r == a // b"],
        "postconditions": ["r 等于 a 整除 b"],
        "spec_source": "logic_analysis",
    }
    spec = parse_logic_analysis(la, boundary_triplets=[([0, 0], 0, "零除边界")])
    if not spec:
        return fail("spec 解析失败，无法生成 oracle")
    oracle_code = compile_spec_oracle(
        spec, target_module="safe_target", target_function="divide", signature_params=["a", "b"]
    )
    if not oracle_code:
        return fail("oracle 未生成（应生成崩溃安全骨架）")
    static_checks = {
        "has_try": "try:" in oracle_code,
        "has_except": "except Exception" in oracle_code,
        "has_skip": "pytest.skip(" in oracle_code,
        "has_oracle_name": "def test_specir_v2_oracle(" in oracle_code,
    }
    if not all(static_checks.values()):
        return fail(f"崩溃安全 harness 缺失：{static_checks}", oracle_head=oracle_code[:300])
    # 行为验证：把 oracle 写进 tmp 目录真实跑 pytest → 期望 skipped（而非 failed）
    test_file = tmpdir / "test_oracle_generated.py"
    test_file.write_text(oracle_code, encoding="utf-8")
    proc = subprocess.run(
        [_sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_oracle_generated.py"],
        capture_output=True,
        text=True,
        cwd=str(tmpdir),
        timeout=120,
    )
    out = proc.stdout + proc.stderr
    if "1 skipped" not in out and "skipped" not in out.lower():
        return fail(f"崩溃 oracle 未按 skip 收口（rc={proc.returncode}）：{out[-400:]}")
    if "1 failed" in out or "failed" in out.lower():
        return fail(f"崩溃 oracle 被记为失败（应 skip）：{out[-400:]}")
    return ok(f"oracle 仪器加固生效：崩溃→skip（rc={proc.returncode}），静态 harness 齐备", checks=static_checks)


def probe_oracle_replay_instrument_breakdown():
    """O-1 replay 分类细化：fp 拆分 instrument_error、skip 原因单列且旧四分类键保留。"""
    import json
    from pathlib import Path as _Path

    report = (
        _Path(__file__).resolve().parents[2]
        / "experiments"
        / "results"
        / "emse_oracle_instrument_hardening_20261017"
        / "ORACLE_QUALITY_REPORT.json"
    )
    if not report.exists():
        return skip("O-1 加固工件缺失（emse_oracle_instrument_hardening_20261017 未生成）")
    data = json.loads(report.read_text(encoding="utf-8"))
    rep = data.get("report", data)
    cmp_block = rep.get("instrument_hardening_comparison") or {}
    arms = cmp_block.get("arms") or []
    if not arms:
        return fail("加固对比块缺失 arms")
    arm = arms[0]
    after = arm.get("after") or {}
    counts = after.get("counts") or {}
    breakdown = after.get("fp_breakdown") or {}
    skip_reasons = after.get("skip_reason_counts") or {}
    checks = {
        "old_four_keys_kept": all(k in counts for k in ("correct", "fp", "silent", "misguided")),
        "fp_breakdown_present": "fp_assertion_fail" in breakdown and "instrument_error" in breakdown,
        "skip_reasons_present": bool(skip_reasons),
        "fp_reduced": counts.get("fp", 99) <= 2,
        "instrument_quarantined": breakdown.get("instrument_error", 1) == 0,
        "skip_attributed": sum(skip_reasons.values()) >= 20,
    }
    if not all(checks.values()):
        return fail(f"replay 分类细化不完整：{checks}", after=after)
    return ok(
        f"replay 分类细化正常：fp={counts.get('fp')}（断言型）、instrument_error=0、skipped={after.get('skipped_count')}，旧四分类键保留",
        checks=checks,
        skip_reasons=skip_reasons,
    )


def probe_oracle_precondition_input_filter():
    """O-1 前件校验输入选择：违反可机检前件的候选被跳过、选下一个合法候选。"""
    from src.specs.spec_ir import parse_logic_analysis
    from src.specs.spec_ir_v2 import compile_spec_oracle

    la = {
        "function_name": "area",
        "preconditions_expr": ["side > 0"],
        "postconditions_expr": ["r == side * side"],
        "preconditions": ["边长必须为正"],
        "postconditions": ["返回面积"],
        "spec_source": "logic_analysis",
    }
    # 第一个候选 side=0 违反 side>0（可机检）；第二个 side=3 合法
    spec = parse_logic_analysis(la, boundary_triplets=[(0, 0, "零边长"), (3, 9, "正边长")])
    if not spec:
        return fail("spec 解析失败")
    code = compile_spec_oracle(spec, target_module="m", target_function="area", signature_params=["side"])
    if not code:
        return fail("oracle 未生成")
    if "side = 3" not in code or "side = 0" in code:
        return fail(f"前件校验输入选择未生效（应绑 side=3 而非 0）：{code[:300]}")
    return ok("前件校验输入选择生效：跳过违反 side>0 的候选，绑定合法候选 side=3")


def probe_oracle_examples_compile():
    """P-1：规格可执行示例通道——examples 解析后编译为逐示例断言（零 eval/exec）。"""
    from src.specs.spec_ir import parse_logic_analysis
    from src.specs.spec_ir_v2 import compile_spec_oracle

    la = {
        "function_name": "add",
        "preconditions": ["a, b 为整数"],
        "postconditions": ["返回 a + b"],
        "postconditions_expr": ["r == a + b"],
        "spec_source": "logic_analysis",
        "examples": [{"input": [2, 3], "expected": 5}],
    }
    spec = parse_logic_analysis(la)
    if not spec or not spec.get("examples"):
        return fail("parse_logic_analysis 未透传有效 examples", spec=spec)
    code = compile_spec_oracle(spec, target_module="target_mod", target_function="add", signature_params=["a", "b"])
    if not code:
        return fail("含 examples 的 spec 未生成 oracle")
    try:
        import ast as _ast

        _ast.parse(code)
    except SyntaxError as exc:
        return fail(f"含示例 oracle 不是合法 Python：{exc}")
    checks = {
        "expected_literal": "_specir_norm_return(5)" in code or "== 5" in code,
        "assert_present": any(line.strip().startswith("assert") for line in code.splitlines()),
        "crash_safe": "pytest.skip(" in code and "except Exception" in code,
        "audit_marker": "examples=1" in code,
        "no_eval_exec": "eval(" not in code and "exec(" not in code,
    }
    if not all(checks.values()):
        return fail(f"示例断言编译契约不完整：{checks}", code_head=code[:400])
    # 无示例负控：仍按 O-1 路径生成（无示例审计标记/无该期望字面量）
    la_nonex = {k: v for k, v in la.items() if k != "examples"}
    spec2 = parse_logic_analysis(la_nonex)
    code2 = compile_spec_oracle(spec2, target_module="target_mod", target_function="add", signature_params=["a", "b"])
    if code2 and ("_specir_norm_return(5)" in code2 or "examples=" in code2):
        return fail("无示例路径出现示例标记（零差异契约破坏）", code_head=code2[:300])
    return ok(f"示例通道编译正常（{len(code)} 字符、examples=1、崩溃安全、无 eval/exec）", checks=checks)


def probe_oracle_examples_detection():
    """P-1：示例 oracle 的检出能力——buggy 必败、fixed 必过（自含 fixture，真实 pytest）。"""
    import ast as _ast
    import subprocess

    from src.specs.spec_ir import parse_logic_analysis
    from src.specs.spec_ir_v2 import compile_spec_oracle

    tmpdir = make_temp_dir("e2e_oracle_examples_")
    la = {
        "function_name": "add",
        "postconditions_expr": ["r == a + b"],
        "preconditions": [],
        "spec_source": "logic_analysis",
        "examples": [{"input": [2, 3], "expected": 5}],
    }
    spec = parse_logic_analysis(la)
    code = compile_spec_oracle(spec, target_module="target_mod", target_function="add", signature_params=["a", "b"])
    if not code:
        return fail("示例 oracle 未生成")
    if not code.strip():
        return fail("示例 oracle 为空")
    try:
        _ast.parse(code)
    except SyntaxError as exc:
        return fail(f"示例 oracle 非法 Python：{exc}")

    outcomes: dict[str, int] = {}
    for variant, impl in (
        ("buggy", "def add(a, b):\n    return a - b\n"),
        ("fixed", "def add(a, b):\n    return a + b\n"),
    ):
        work = tmpdir / variant
        work.mkdir()
        (work / "target_mod.py").write_text(impl, encoding="utf-8")
        (work / "test_oracle.py").write_text(code, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_oracle.py"],
            capture_output=True,
            text=True,
            cwd=str(work),
            timeout=120,
        )
        outcomes[variant] = proc.returncode
    if outcomes["fixed"] != 0:
        return fail("fixed 实现上示例 oracle 未通过（误报/仪器缺陷）", outcomes=outcomes)
    if outcomes["buggy"] == 0:
        return fail("buggy 实现上示例 oracle 未检出（应至少一例断言失败）", outcomes=outcomes)
    # 对照：无示例 oracle 对同一 buggy 不检出（静默通过）——证明检出由示例通道带来
    la_nonex = {k: v for k, v in la.items() if k != "examples"}
    code_nonex = compile_spec_oracle(
        parse_logic_analysis(la_nonex), target_module="target_mod", target_function="add", signature_params=["a", "b"]
    )
    control_rc = 0
    if code_nonex:
        work = tmpdir / "buggy_control"
        work.mkdir()
        (work / "target_mod.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
        (work / "test_oracle.py").write_text(code_nonex, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_oracle.py"],
            capture_output=True,
            text=True,
            cwd=str(work),
            timeout=120,
        )
        control_rc = proc.returncode
    if control_rc != 0:
        return fail("无示例对照 oracle 竟然在 buggy 上失败（对照不成立）", control_rc=control_rc, outcomes=outcomes)
    return ok(
        f"示例 oracle 检出能力正确：buggy rc={outcomes['buggy']}（检出）/ fixed rc=0 / 无示例对照 rc=0（不检出）",
        outcomes=outcomes,
    )


def probe_oracle_examples_production():
    """Q-1：示例通道生产接线静态/行为契约（双门开关、prompt 段、行字段、env 登记）。"""
    import importlib
    import inspect as _inspect

    planner = importlib.import_module("src.agents.planner")
    run_benchmark = importlib.import_module("experiments.run_benchmark")
    checks: dict[str, bool] = {}
    checks["planner_section_present"] = hasattr(planner, "SPEC_EXPR_EXAMPLES_SECTION")
    section = getattr(planner, "SPEC_EXPR_EXAMPLES_SECTION", "") or ""
    checks["planner_section_mentions_examples"] = "examples" in section
    checks["planner_gate_function"] = hasattr(planner, "spec_oracle_examples_enabled")
    orig = {k: os.environ.get(k) for k in ("SPEC_ORACLE_EXEC_ENABLE", "SPEC_ORACLE_EXAMPLES_ENABLE")}
    try:
        os.environ.pop("SPEC_ORACLE_EXEC_ENABLE", None)
        os.environ.pop("SPEC_ORACLE_EXAMPLES_ENABLE", None)
        checks["default_off"] = planner.spec_oracle_examples_enabled() is False
        os.environ["SPEC_ORACLE_EXEC_ENABLE"] = "true"
        os.environ["SPEC_ORACLE_EXAMPLES_ENABLE"] = "false"
        checks["exec_only_off"] = planner.spec_oracle_examples_enabled() is False
        os.environ["SPEC_ORACLE_EXAMPLES_ENABLE"] = "true"
        checks["both_on"] = planner.spec_oracle_examples_enabled() is True
    finally:
        for key, old in orig.items():
            if old is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old
    src = _inspect.getsource(run_benchmark)
    checks["row_field_source"] = "spec_oracle_examples_source" in src
    checks["row_field_count"] = "spec_oracle_examples_count" in src
    checks["env_snapshot_key"] = "SPEC_ORACLE_EXAMPLES_ENABLE" in src
    if not all(checks.values()):
        return fail(f"Q-1 生产接线契约不完整：{checks}")
    return ok("Q-1 生产接线契约齐备（双门默认关/prompt 段/行字段/env 登记）", checks=checks)


def probe_postprocess_wall_observability():
    """Q-3：后处理墙钟可观测模块（稳定 JSON 形状 / 分位 / env 默认）。"""
    import importlib
    import json as _json

    wall = importlib.import_module("experiments.postprocess_wall")
    payload = wall.build_postprocess_wall(
        {"mutation": [1.0, 2.0, 3.0, 4.0], "m1": [0.5], "mdo": [], "other": []},
        timed_out={"mutation": 1},
        warn_s=3.0,
    )
    checks: dict[str, bool] = {}
    checks["stages"] = set(wall.registered_stage_names()) == {"mutation", "m1", "mdo", "other"}
    checks["shape"] = all(
        key in payload.get("mutation", {})
        for key in ("wall_s", "n_tasks", "mean_s", "p50_s", "p95_s", "max_s", "timed_out_tasks")
    )
    checks["p50"] = abs(float(payload["mutation"]["p50_s"]) - 2.5) < 1e-6
    checks["p95"] = abs(float(payload["mutation"]["p95_s"]) - 3.85) < 1e-6
    checks["n_tasks"] = payload["mutation"]["n_tasks"] == 4
    checks["timeout"] = payload["mutation"]["timed_out_tasks"] == 1
    checks["empty_stage_zero"] = payload["mdo"]["n_tasks"] == 0 and payload["mdo"]["wall_s"] == 0.0
    _json.dumps(payload)
    orig = os.environ.get("AITESTER_POSTPROCESS_WARN_S")
    try:
        os.environ.pop("AITESTER_POSTPROCESS_WARN_S", None)
        checks["env_default_600"] = wall.postprocess_warn_s() == 600.0
        os.environ["AITESTER_POSTPROCESS_WARN_S"] = "123"
        checks["env_override"] = wall.postprocess_warn_s() == 123.0
        os.environ["AITESTER_POSTPROCESS_WARN_S"] = "not-a-number"
        checks["env_bad_fallback"] = wall.postprocess_warn_s() == 600.0
    finally:
        if orig is None:
            os.environ.pop("AITESTER_POSTPROCESS_WARN_S", None)
        else:
            os.environ["AITESTER_POSTPROCESS_WARN_S"] = orig
    # R-3：run_benchmark 接入校验（纯观测字段 + 粒度键 + 警告附加 helper）
    try:
        import importlib as _importlib
        import inspect as _inspect

        rb = _importlib.import_module("experiments.run_benchmark")
        rb_src = _inspect.getsource(rb)
        checks["hook_mounted"] = "postprocess_wall" in rb_src and "_attach_postprocess_wall_to_summary" in rb_src
        checks["hook_granularity"] = "postprocess_wall_granularity" in rb_src
    except Exception as exc:  # pragma: no cover - 仅探针防御
        return fail(f"run_benchmark hook 检查异常：{type(exc).__name__}: {exc}")
    if not all(checks.values()):
        return fail(f"后处理墙钟模块/hook 契约不完整：{checks}")
    return ok("后处理墙钟模块正常（稳定 JSON/线性分位/env 回退）+ run_benchmark hook 已接入", checks=checks)


def probe_examples_self_validation():
    """R-2：示例自校验过滤器（safe-AST 后置子句校验；保守放行；env 开关）。"""
    from src.specs.spec_ir import parse_logic_analysis
    from src.specs.spec_ir_v2 import self_validate_examples

    spec = parse_logic_analysis(
        {
            "function_name": "add",
            "postconditions_expr": ["r == a + b"],
            "preconditions": [],
        }
    )
    examples = [
        {"input": [2, 3], "expected": 5},
        {"input": [2, 3], "expected": 6},  # 与后置子句矛盾 → 丢弃
        {"input": [1, 1], "expected": 2},
    ]
    kept, audit = self_validate_examples(spec, ["a", "b"], examples)
    checks = {
        "dropped_contradiction": audit.get("n_dropped") == 1 and len(kept) == 2,
        "reason": "postcondition_false" in (audit.get("reasons") or {}),
        "kept_valid": [item["expected"] for item in kept] == [5, 2],
        "fully_validated": int(audit.get("n_fully_validated", 0)) >= 2,
        "default_enabled": audit.get("enabled") is True,
    }
    # 安全边界：不可机检/危险子句保守保留（不误杀、不执行）
    unsafe_spec = parse_logic_analysis(
        {"function_name": "f", "postconditions_expr": ["__import__('os').system('echo hi') == r"], "preconditions": []}
    )
    kept_u, audit_u = self_validate_examples(unsafe_spec, ["a"], [{"input": [1], "expected": 1}])
    checks["unsafe_kept"] = len(kept_u) == 1 and int(audit_u.get("n_unevaluable", 0)) == 1
    # env 关闭：全部保留、enabled=False
    orig = os.environ.get("SPEC_EXAMPLES_SELF_VALIDATE")
    try:
        os.environ["SPEC_EXAMPLES_SELF_VALIDATE"] = "false"
        kept_off, audit_off = self_validate_examples(spec, ["a", "b"], examples)
        checks["env_off"] = len(kept_off) == 3 and audit_off.get("enabled") is False and audit_off.get("n_dropped") == 0
    finally:
        if orig is None:
            os.environ.pop("SPEC_EXAMPLES_SELF_VALIDATE", None)
        else:
            os.environ["SPEC_EXAMPLES_SELF_VALIDATE"] = orig
    if not all(checks.values()):
        return fail(f"示例自校验契约不完整：{checks}", audit=audit)
    return ok("示例自校验正常（矛盾示例丢弃/safe-AST 危险子句保留/env 开关）", checks=checks)


def probe_examples_multisample():
    """S-3：多采样示例自一致性（归一化键 + 交集过滤，零 LLM）。"""
    import importlib

    gen = importlib.import_module("experiments.spec_examples_generator")
    checks: dict[str, bool] = {}
    checks["api"] = hasattr(gen, "generate_examples_multisample") and hasattr(gen, "intersect_examples")
    checks["single_api"] = hasattr(gen, "generate_spec_examples")
    if not all(checks.values()):
        return fail(f"多采样 API 缺失：{checks}")
    key = gen.normalize_example_key
    checks["dict_order_insensitive"] = key({"input": [1], "expected": {"a": 1, "b": 2}}) == key(
        {"expected": {"b": 2, "a": 1}, "input": [1]}
    )
    checks["unicode_stable"] = key({"input": ["中文"], "expected": 1}) == key({"input": ["中文"], "expected": 1})
    checks["int_float_distinct"] = key({"input": [1], "expected": 1}) != key({"input": [1], "expected": 1.0})
    checks["list_tuple_equivalent"] = key({"input": [[1, 2]], "expected": 3}) == key({"input": [(1, 2)], "expected": 3})
    samples = [
        [{"input": [1], "expected": 2}, {"input": [3], "expected": 4}],
        [{"input": [1], "expected": 2}, {"input": [5], "expected": 6}],
    ]
    merged, audit = gen.intersect_examples(samples, k=2)
    checks["intersection"] = merged == [{"input": [1], "expected": 2}]
    checks["audit"] = isinstance(audit, dict)
    if not all(checks.values()):
        return fail(f"多采样契约不完整：{checks}", audit=audit)
    return ok("多采样自一致性正常（归一化键/求交/审计/单采样 API 保持）", checks=checks)


def _stagnation_tie_state() -> dict:
    """构造"repair-invalid 与停滞窗口同迭代收敛"的最小桩 state（T 轮 A-19 口径）。

    来源：S-2 默认闸冒烟实测（experiments/results/s_round_b8_injection_20261018/）
    ——证据门默认 true 时 repair_history 连续 patch_applied=False，且
    execution_trace 最近 K=2 轮 coverage_delta≈0，两个终止条件在同一迭代成立。
    """
    return {
        "test_passed": False,
        "iteration": 2,
        "max_iterations": 3,
        "execution_trace": [
            {"iteration": 0, "passed": False, "coverage": 0.0, "coverage_delta": None},
            {"iteration": 1, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
            {"iteration": 2, "passed": False, "coverage": 0.0, "coverage_delta": 0.0},
        ],
        "repair_history": [{"patch_applied": False}, {"patch_applied": False}],
    }


def probe_stagnation_precedence():
    """T 轮 A-19 抢占优先级：repair-invalid 同迭代平局下停滞判定优先（默认关零变化）。

    (a) COVERAGE_STALL_DETECT_ENABLE 未设 → 平局返回/标签与历史一致
        （done + skip_debugger_repair_invalid，零变化）；
    (b) 开关=true 且停滞判定为真 → 返回 done 且 stop_reason=coverage_stall
        （修复后由停滞分支拥有终止决定，而非 determine_stop_reason 标签兜底）。
    """
    from src.graph import workflow

    saved = os.environ.get("COVERAGE_STALL_DETECT_ENABLE")
    try:
        os.environ.pop("COVERAGE_STALL_DETECT_ENABLE", None)
        off_state = _stagnation_tie_state()
        off_detected = workflow._coverage_stall_detected(off_state)
        off_decision = workflow._should_debug(off_state)
        off_stop = off_state.get("stop_reason")

        os.environ["COVERAGE_STALL_DETECT_ENABLE"] = "true"
        on_state = _stagnation_tie_state()
        on_detected = workflow._coverage_stall_detected(on_state)
        on_decision = workflow._should_debug(on_state)
        on_stop = on_state.get("stop_reason")
    finally:
        if saved is None:
            os.environ.pop("COVERAGE_STALL_DETECT_ENABLE", None)
        else:
            os.environ["COVERAGE_STALL_DETECT_ENABLE"] = saved

    evidence = {
        "off_detected": off_detected,
        "off_decision": off_decision,
        "off_stop_reason": off_stop,
        "on_detected": on_detected,
        "on_decision": on_decision,
        "on_stop_reason": on_stop,
        "iteration": 2,
        "max_iterations": 3,
    }
    # (a) 默认关零变化：停滞判定关闭、repair-invalid 历史口径不变
    if off_detected is not False or off_decision != "done" or off_stop != "skip_debugger_repair_invalid":
        return fail(
            f"默认关平局行为漂移：detected={off_detected}, decision={off_decision!r}, stop_reason={off_stop!r}",
            **evidence,
        )
    # (b) ON：停滞判定命中且优先归因 coverage_stall
    if on_detected is not True:
        return fail(f"ON 臂停滞判定未命中：detected={on_detected}", **evidence)
    if on_decision != "done" or on_stop != workflow.StopReason.COVERAGE_STALL.value:
        return fail(
            f"ON 臂停滞未优先：decision={on_decision!r}, stop_reason={on_stop!r}（期望 done/coverage_stall）",
            **evidence,
        )
    return ok(
        "A-19 抢占优先级正常：默认关 repair-invalid 平局历史口径不变；ON 时停滞优先（done/coverage_stall）",
        **evidence,
    )


def probe_rollback_schema_fields():
    """T 轮回滚 verdict schema：结果行两分支键集合同构 + 字段透传/占位语义。

    验证 `experiments.run_benchmark._build_task_result`：
    - 成功/失败两分支键集合完全一致（键集合同构）；
    - 两分支都含 `patch_rollback_verdict` / `patch_rolled_back`；
    - 成功分支从 final_state 透传（True/False/None 三态语义各一例）；
    - 失败分支（无 final_state）占位为 (None, False)；
    - 结果行可 JSON 落盘（json.dumps 往返保真）。
    """
    import json

    from experiments.run_benchmark import _build_task_result
    from src.datasets.dataset_loader import BenchmarkTask

    def _task() -> BenchmarkTask:
        return BenchmarkTask(
            task_id="probe__rollback_schema",
            repo_name="probe/repo",
            problem_statement="fix a bug",
            instance_code="def f():\n    return 1\n",
            test_code="def test_f():\n    assert f() == 1\n",
            expected_pass_count=0,
            total_test_count=1,
            metadata={"source": "e2e_probe"},
        )

    rows = {
        "success_rolled_back": _build_task_result(
            _task(),
            1.0,
            final_state={
                "test_passed": False,
                "patch_rollback_verdict": "regression_failed",
                "patch_rolled_back": True,
            },
        ),
        "success_not_enabled": _build_task_result(
            _task(), 1.0, final_state={"patch_rollback_verdict": "not_enabled", "patch_rolled_back": False}
        ),
        "success_not_executed": _build_task_result(_task(), 1.0, final_state={"test_passed": False}),
        "failure_no_state": _build_task_result(_task(), 0.5, diagnosis="执行异常: probe", error_category="error"),
    }
    keysets = {name: set(row) for name, row in rows.items()}
    evidence = {
        "row_count": len(rows),
        "key_count": len(keysets["success_rolled_back"]),
        "key_set_isomorphic": len({frozenset(v) for v in keysets.values()}) == 1,
        "probed": {
            name: {
                "patch_rollback_verdict": row.get("patch_rollback_verdict"),
                "patch_rolled_back": row.get("patch_rolled_back"),
            }
            for name, row in rows.items()
        },
    }
    missing = [
        name for name, row in rows.items() if "patch_rollback_verdict" not in row or "patch_rolled_back" not in row
    ]
    if missing:
        return fail(f"结果行缺回滚 verdict 键：{missing}", **evidence)
    if not evidence["key_set_isomorphic"]:
        return fail("成功/失败分支键集合不同构（结果行 schema 漂移）", **evidence)
    projected = [
        rows["success_rolled_back"].get("patch_rollback_verdict") == "regression_failed",
        rows["success_rolled_back"].get("patch_rolled_back") is True,
        rows["success_not_enabled"].get("patch_rollback_verdict") == "not_enabled",
        rows["success_not_enabled"].get("patch_rolled_back") is False,
        rows["success_not_executed"].get("patch_rollback_verdict") is None,
        rows["success_not_executed"].get("patch_rolled_back") is None,
        rows["failure_no_state"].get("patch_rollback_verdict") is None,
        rows["failure_no_state"].get("patch_rolled_back") is False,
    ]
    if not all(projected):
        return fail(f"回滚 verdict 投影/占位语义不符：{evidence['probed']}", **evidence)
    try:
        json.loads(json.dumps(rows["success_rolled_back"], ensure_ascii=False))
        json.loads(json.dumps(rows["failure_no_state"], ensure_ascii=False))
    except (TypeError, ValueError) as exc:
        return fail(f"结果行不可 JSON 落盘：{type(exc).__name__}: {exc}", **evidence)
    return ok(
        "回滚 verdict schema 正常：两分支键集合同构、含 patch_rollback_verdict/patch_rolled_back、投影与占位语义正确、可落盘",
        **evidence,
    )


PROBES = [
    Probe(
        name="logic-spec-ir-parse",
        group="logic",
        func=probe_spec_ir_parse,
        timeout_s=60,
        description="SpecIR 双通道解析 + 边界三元组 + 空材料保守降级",
    ),
    Probe(
        name="logic-spec-expr-whitelist",
        group="logic",
        func=probe_spec_expr_whitelist,
        timeout_s=60,
        description="SpecExpr 白名单：危险子句拒绝 / 可编译子句接受 / readiness 计率",
    ),
    Probe(
        name="logic-spec-oracle-compile",
        group="logic",
        func=probe_spec_oracle_compile,
        timeout_s=60,
        description="确定性 oracle 编译：ast 合法 + 标准测试名 + 无材料空串",
    ),
    Probe(
        name="logic-smt-witness",
        group="logic",
        func=probe_smt_witness,
        timeout_s=120,
        description="SMT 见证：sat/边界见证 + 不可翻译保守降级（可选依赖 z3）",
    ),
    Probe(
        name="logic-spec-anchor-oracle-wiring",
        group="logic",
        func=probe_spec_anchor_oracle_wiring,
        timeout_s=90,
        description="N-3 接线：仅 spec_anchor 材料也能注入确定性 oracle",
    ),
    Probe(
        name="logic-oracle-independent-judging",
        group="logic",
        func=probe_oracle_independent_judging,
        timeout_s=120,
        description="N-3 独立判读：结果行字段 + fail-closed 函数 + replay 入口",
    ),
    Probe(
        name="logic-stagnation-switch",
        group="logic",
        func=probe_stagnation_switch,
        timeout_s=60,
        description="覆盖率停滞检测开关 + 消融臂互斥",
    ),
    Probe(
        name="logic-mutation-advisor-assembly",
        group="logic",
        func=probe_mutation_advisor_assembly,
        timeout_s=120,
        description="mutation advisor 环装配随开关变化",
    ),
    Probe(
        name="logic-branch-coverage-inject",
        group="logic",
        func=probe_branch_coverage_inject,
        timeout_s=180,
        description="branch 覆盖注入真实测量（含空测试保守降级）",
    ),
    Probe(
        name="logic-oracle-instrument-safety",
        group="logic",
        func=probe_oracle_instrument_safety,
        timeout_s=180,
        description="O-1：oracle 崩溃安全 harness（崩溃→skip 非 fail，真实 pytest 验证）",
    ),
    Probe(
        name="logic-oracle-replay-instrument-breakdown",
        group="logic",
        func=probe_oracle_replay_instrument_breakdown,
        timeout_s=60,
        description="O-1：replay 分类细化（fp 拆分 instrument_error + skip 原因单列）",
    ),
    Probe(
        name="logic-oracle-precondition-input-filter",
        group="logic",
        func=probe_oracle_precondition_input_filter,
        timeout_s=90,
        description="O-1：前件校验输入选择（跳过违反前件的边界候选）",
    ),
    Probe(
        name="logic-oracle-examples-compile",
        group="logic",
        func=probe_oracle_examples_compile,
        timeout_s=90,
        description="P-1：规格可执行示例 → 逐示例断言编译（零 eval/exec、崩溃安全、审计标记）",
    ),
    Probe(
        name="logic-oracle-examples-detection",
        group="logic",
        func=probe_oracle_examples_detection,
        timeout_s=180,
        description="P-1：示例 oracle 检出能力（buggy 必败/fixed 必过/无示例对照不检出）",
    ),
    Probe(
        name="logic-oracle-examples-production",
        group="logic",
        func=probe_oracle_examples_production,
        timeout_s=90,
        description="Q-1：示例通道生产接线契约（双门开关/prompt 段/行字段/env 登记）",
    ),
    Probe(
        name="observability-postprocess-wall",
        group="observability",
        func=probe_postprocess_wall_observability,
        timeout_s=60,
        description="Q-3：后处理墙钟模块（稳定 JSON/线性分位/env 默认与坏值回退）",
    ),
    Probe(
        name="logic-examples-self-validation",
        group="logic",
        func=probe_examples_self_validation,
        timeout_s=60,
        description="R-2：示例自校验（safe-AST 后置子句校验/矛盾丢弃/不可机检保守放行/env 开关）",
    ),
    Probe(
        name="logic-examples-multisample",
        group="logic",
        func=probe_examples_multisample,
        timeout_s=60,
        description="S-3：多采样示例自一致性（归一化键/交集过滤/审计，零 LLM）",
    ),
    Probe(
        name="logic-profile-spec-fields",
        group="logic",
        func=probe_logic_profile_spec_fields,
        requires_llm=True,
        timeout_s=240,
        description="logic 档最小真实任务：spec 链路状态字段落态（真 LLM ≤1 调用）",
    ),
    Probe(
        name="logic-stagnation-precedence",
        group="logic",
        func=probe_stagnation_precedence,
        timeout_s=60,
        description="T4：A-19 抢占优先级（默认关 repair-invalid 平局零变化 / ON 停滞优先）",
    ),
    Probe(
        name="logic-rollback-schema-fields",
        group="logic",
        func=probe_rollback_schema_fields,
        timeout_s=60,
        description="T4：回滚 verdict 结果行 schema（双分支键集合同构 + 投影/占位语义 + 可落盘）",
    ),
]

_ = llm_enabled  # 保持导入供探针模块扩展使用（静态检查不再报未使用）
