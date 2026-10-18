#!/usr/bin/env python3
"""N-1 全功能端到端探针：CLI / workflow / agents / repair / 安全守卫 / 可观测 / 分析。

## 定位

本模块是 `scripts/tools/e2e_probe.py` 的功能清单组之一，覆盖**用户可见主链路**：

- **CLI**：`--help` / `list-examples` / `check-dataset` / `run --json`（单文件）/
  `run` 多文件 `--parallel`（真 LLM，验证 stdout 纯 JSON + 退出码语义）；
- **workflow**：fast / logic 两档的节点集合与边装配（零 LLM 子进程断言）+ logic
  档最小任务真实 invoke（真 LLM，断言 planner/test_plan / generated_test /
  execution_trace / 终态字段齐全）；
- **agents**：planner 结构化计划 / generator 可解析 pytest / executor 沙箱执行；
- **repair**：Debugger → patch_applier → executor 真实修复链（真 LLM 1 次调用；
  区分"功能故障"与"模型未产出"）；
- **safety**：危险 API 守卫 / 命名契约守卫 / 补丁测试黑客检测 / 确定性修复 /
  快照回滚协议（零 LLM，直接调工具层）；
- **observability**：trace JSONL 落盘 + 脱敏；事件总线发布/订阅/开关；
- **analysis**：FL_spectral（Ochiai Top-k）/ fault localizer 反事实定位 /
  multi-candidate 静态筛选（零 LLM / 零网络）。

## 纪律

- 零 LLM 探针默认执行；`requires_llm=True` 的探针仅在
  `AITESTER_E2E_LLM=true` + `--include-llm` 时执行（框架强制 LLM 缓存关闭）。
- LLM 探针每探针**真实调用 ≤2 次**：单文件 CLI 用 `ENABLE_PLANNER=false +
  ENABLE_DEBUGGER=false`（1 次 generator）；多文件 2 个文件各 1 次；
  repair 链只调 debugger 1 次（planner 由 workflow-logic 探针另行覆盖）。
- 所有写盘在 tmp 目录；真实 LLM 探针失败时区分 `model_nonproduction`（skip）
  与 `functional_failure`（fail），证据字段写入 evidence。
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from scripts.tools.e2e_probe import (
    PROJECT_ROOT,
    Probe,
    ProbeOutcome,
    error,
    fail,
    invoke_workflow,
    make_temp_dir,
    ok,
    run_cmd,
    skip,
)

_MAIN = str(PROJECT_ROOT / "main.py")
_LLM_ENV_DEFAULTS: dict[str, str] = {
    "AITESTER_LLM_CACHE": "0",
    "LLM_THINKING_MODE": "disabled",
    "TEMPERATURE": "0.0",
    "PYTHONUNBUFFERED": "1",
}
_LLM_TIMEOUT = 300.0

# ─── 通用辅助 ────────────────────────────────────────────────────────────────


def _llm_env(profile: str | None = None, **overrides: str) -> dict[str, str]:
    """构造真实 LLM 探针的子进程 env 覆盖（显式 temp=0 / thinking=disabled）。"""
    env = dict(_LLM_ENV_DEFAULTS)
    if profile:
        env["AITESTER_PROFILE"] = profile
    env.update(overrides)
    return env


def _usage_metric(usage: dict[str, Any], key: str) -> int:
    """从 token_usage.as_dict() 取整数指标（by_model 为 dict，非目标键 → 0）。"""
    value = usage.get(key)
    return int(value) if isinstance(value, int) and not isinstance(value, bool) else 0


def _usage_evidence() -> dict[str, Any]:
    """本探针进程已发生的 LLM 调用/token 快照（成本审计用；失败静默空）。"""
    try:
        from src.budget.token_usage import get_usage

        usage = get_usage().as_dict()
        return {
            "llm_calls": _usage_metric(usage, "llm_calls"),
            "total_tokens": _usage_metric(usage, "total_tokens"),
            "input_tokens": _usage_metric(usage, "input_tokens"),
            "output_tokens": _usage_metric(usage, "output_tokens"),
        }
    except Exception:  # pragma: no cover - 观测层失败不影响探针判定
        return {}


def _effective_stop_reason(state: dict[str, Any]) -> str | None:
    """读取最终状态终止原因（effective_stop_reason 的 dict 入参适配）。"""
    from typing import cast

    from src.graph.workflow import effective_stop_reason

    return effective_stop_reason(cast("Any", state))


def _tail(text: str | None, limit: int = 240) -> str:
    """截取输出尾部（失败诊断用）。"""
    compact = " ".join((text or "").split())
    return compact[-limit:]


def _rmtree(path: Path | str | None) -> None:
    """尽力清理探针 tmp 目录（失败不报错）。"""
    if path is None:
        return
    shutil.rmtree(str(path), ignore_errors=True)


def _json_objects(text: str) -> list[Any]:
    """解析 stdout 中**连续拼接**的多个 JSON 文档（CLI 多文件 --json 口径）。

    多文件 `run --json` 每个任务各输出一份 pretty JSON（既有测试锁定行为），
    整体不是单一 JSON 文档；这里用 `JSONDecoder.raw_decode` 顺序消费。
    """
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    index = 0
    length = len(text)
    while index < length:
        while index < length and text[index] in " \t\r\n":
            index += 1
        if index >= length:
            break
        obj, end = decoder.raw_decode(text, index)
        objects.append(obj)
        index = end
    return objects


def _write_module(directory: Path, name: str, source: str) -> Path:
    path = directory / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    return path


# ─── 1. CLI 组 ────────────────────────────────────────────────────────────────

_CLI_SUBCOMMANDS = ("run", "list-examples", "check-dataset", "clean-venv-cache")
_SAMPLE_CODE = "def add(a, b):\n    return a + b\n"


def probe_cli_help() -> ProbeOutcome:
    """`python main.py --help`：退出码 0 且列出全部用户子命令。"""
    rc, out, err = run_cmd([sys.executable, _MAIN, "--help"], timeout=120.0)
    if rc != 0:
        return error(f"main.py --help rc={rc}", stderr_tail=_tail(err), stdout_tail=_tail(out))
    missing = [name for name in _CLI_SUBCOMMANDS if name not in out]
    if missing:
        return fail(f"--help 缺少子命令 {missing}", stdout_tail=_tail(out, 600))
    return ok("CLI --help 正常，4 个子命令均在帮助面", subcommands=list(_CLI_SUBCOMMANDS))


def probe_cli_list_examples() -> ProbeOutcome:
    """`list-examples`：列出 examples/ 下示例文件并给出使用示例。"""
    rc, out, err = run_cmd([sys.executable, _MAIN, "list-examples"], timeout=120.0)
    if rc != 0:
        return error(f"list-examples rc={rc}", stderr_tail=_tail(err))
    if "可用示例文件" not in out:
        return fail("list-examples 未输出『可用示例文件』标题", stdout_tail=_tail(out, 600))
    listed = [line.strip(" •\t") for line in out.splitlines() if line.strip().startswith("•")]
    if not {"calculator.py", "buggy_library.py"} <= set(listed):
        return fail("示例清单缺 calculator.py / buggy_library.py", listed=listed[:20])
    dunder = [name for name in listed if name.startswith("_")]
    if dunder:
        # N-1 实测缺陷（已修）：__init__.py 被当作可运行示例列出/建议
        return fail(f"示例清单含不可运行的下划线开头文件 {dunder}", listed=listed[:20])
    if "使用示例" not in out or "python main.py run" not in out:
        return fail("缺少『使用示例』提示", stdout_tail=_tail(out, 600))
    suggested_lines = [line for line in out.splitlines() if "python main.py run examples/" in line]
    if not suggested_lines or "__init__.py" in suggested_lines[-1]:
        return fail("『使用示例』建议了不可运行文件", suggested=suggested_lines[-1:] or None)
    return ok(f"list-examples 正常，列出 {len(listed)} 个示例文件且建议 calculator.py", listed=listed)


def probe_cli_check_dataset() -> ProbeOutcome:
    """`check-dataset quixbugs`：加载 50 任务并给出质量报告。"""
    rc, out, err = run_cmd(
        [sys.executable, _MAIN, "check-dataset", "quixbugs", "--limit", "2"],
        timeout=180.0,
        env=_llm_env(),
    )
    if rc != 0:
        return error(f"check-dataset rc={rc}", stderr_tail=_tail(err))
    if "共加载 50 个任务" not in out:
        return fail("check-dataset 未报告 50 个任务", stdout_tail=_tail(out, 800))
    if "全量质量检查通过" not in out:
        return fail("check-dataset 质量报告未通过", stdout_tail=_tail(out, 800))
    if "quixbugs__bitcount" not in out:
        return fail("前 N 任务详情缺失（期望含 quixbugs__bitcount）", stdout_tail=_tail(out, 800))
    # 观测项（非阻断）：日志脱敏对长路径段的误伤（见 N-1 缺陷报告）
    redactions = out.count("<REDACTED_KEY>")
    return ok(
        "check-dataset quixbugs 正常（50 任务 / 质量通过）",
        task_count=50,
        redacted_path_segments=redactions,
        redaction_note=("检出长路径段被日志脱敏误伤，属诊断可读性缺陷（非本探针功能失败）" if redactions else ""),
    )


def probe_cli_run_json_single() -> ProbeOutcome:
    """`run examples/calculator.py --json`：真 LLM 下 stdout 为**单一合法 JSON**。"""
    target = PROJECT_ROOT / "examples" / "calculator.py"
    if not target.is_file():
        return skip(f"示例文件缺失: {target}")
    cmd = [
        sys.executable,
        _MAIN,
        "run",
        str(target),
        "--json",
        "--verbose",  # N-1 实测缺陷（已修）：--json --verbose 曾污染 stdout
        "--max-iterations",
        "1",
    ]
    env = _llm_env(ENABLE_PLANNER="false", ENABLE_DEBUGGER="false")
    rc, out, err = run_cmd(cmd, timeout=_LLM_TIMEOUT, env=env)
    if rc not in (0, 1):
        return error(f"CLI run --json rc={rc}（期望 0/1）", stderr_tail=_tail(err), stdout_tail=_tail(out))
    stripped = out.strip()
    if not stripped.startswith("{"):
        return fail(
            "--json 模式下 stdout 未以 JSON 开头（被日志/提示污染；--json --verbose 组合回归面）",
            stdout_tail=_tail(out, 800),
        )
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return fail(f"stdout 不是单一合法 JSON: {exc}", stdout_tail=_tail(out, 1200))
    required = {"success", "file", "passed", "coverage", "iterations", "event_bus", "cost_budget"}
    missing = sorted(required - set(payload))
    if missing:
        return fail(f"JSON 结果缺少字段 {missing}", keys=sorted(payload))
    if not str(payload.get("file", "")).endswith("calculator.py"):
        return fail(f"JSON file 字段异常: {payload.get('file')!r}")
    if not isinstance(payload.get("passed"), bool):
        return fail(f"JSON passed 非 bool: {payload.get('passed')!r}")
    return ok(
        f"CLI --json 输出合法 JSON（passed={payload['passed']}, rc={rc}）",
        rc=rc,
        passed=payload["passed"],
        coverage=payload.get("coverage"),
        iterations=payload.get("iterations"),
        event_bus=payload.get("event_bus"),
        cost_budget=payload.get("cost_budget"),
        **_usage_evidence(),
    )


def probe_cli_run_multi_parallel() -> ProbeOutcome:
    """`run A B --parallel 2 --json`：真 LLM 下每个任务各输出一份合法 JSON。

    既有多文件 `--json` 语义 = 每任务一份 JSON 拼接（tests/test_cli_parallel.py
    锁定），故整体不是单一 JSON 文档——探针按 raw_decode 逐份消费断言。
    """
    tmpdir = make_temp_dir("aitester_e2e_cli_multi_")
    try:
        file_a = _write_module(tmpdir, "mod_a", "def inc(x):\n    return x + 1\n")
        file_b = _write_module(tmpdir, "mod_b", "def double(x):\n    return x * 2\n")
        cmd = [
            sys.executable,
            _MAIN,
            "run",
            str(file_a),
            str(file_b),
            "--parallel",
            "2",
            "--json",
            "--max-iterations",
            "1",
        ]
        env = _llm_env(ENABLE_PLANNER="false", ENABLE_DEBUGGER="false")
        rc, out, err = run_cmd(cmd, timeout=_LLM_TIMEOUT, env=env)
        if rc not in (0, 1):
            return error(f"多文件 --parallel rc={rc}（期望 0/1）", stderr_tail=_tail(err), stdout_tail=_tail(out))
        try:
            payloads = _json_objects(out.strip())
        except json.JSONDecodeError as exc:
            return fail(f"多文件 --json 无法逐份解析: {exc}", stdout_tail=_tail(out, 1200))
        if len(payloads) != 2:
            return fail(f"期望 2 份 JSON 结果，实测 {len(payloads)}", stdout_tail=_tail(out, 1200))
        files = {Path(str(item.get("file", ""))).name for item in payloads if isinstance(item, dict)}
        if files != {"mod_a.py", "mod_b.py"}:
            return fail(f"多文件结果 file 集合异常: {sorted(files)}")
        if not all(isinstance(item.get("passed"), bool) for item in payloads):
            return fail("存在 passed 非 bool 的结果", payloads=payloads)
        passed_count = sum(1 for item in payloads if item.get("passed") is True)
        return ok(
            f"多文件 --parallel --json 正常（2 份结果，passed={passed_count}/2，rc={rc}）",
            rc=rc,
            payload_count=len(payloads),
            passed_count=passed_count,
            **_usage_evidence(),
        )
    finally:
        _rmtree(tmpdir)


# ─── 2. workflow 组 ──────────────────────────────────────────────────────────

_WORKFLOW_INSPECT_SCRIPT = r"""
import json
import os

for _key in (
    "ENABLE_PLANNER",
    "ENABLE_DEBUGGER",
    "CROSS_FILE_ENABLE",
    "DIAGNOSIS_NODE_ENABLE",
    "MUTATION_ADVISOR_ENABLE",
    "RISK_APPROVAL_ENABLE",
    "ENABLE_RAG",
):
    os.environ.pop(_key, None)
os.environ.setdefault("AITESTER_LLM_CACHE", "0")

import config
from src.graph.workflow import build_workflow

graph = build_workflow(planner=True, debugger=True)
inspect = graph._graph.get_graph()
print(
    "__E2E_JSON__"
    + json.dumps(
        {
            "active_profile": config.ACTIVE_PROFILE,
            "nodes": sorted(n for n in inspect.nodes if not n.startswith("__")),
            "edges": sorted(f"{e.source}->{e.target}" for e in inspect.edges),
            "flags": {
                "DETECTION_FIRST_ENABLE": os.getenv("DETECTION_FIRST_ENABLE"),
                "FL_SPECTRAL_ENABLE": os.getenv("FL_SPECTRAL_ENABLE"),
                "MUTATION_ADVISOR_ENABLE": os.getenv("MUTATION_ADVISOR_ENABLE"),
                "PATCH_SNAPSHOT_ROLLBACK_ENABLE": os.getenv("PATCH_SNAPSHOT_ROLLBACK_ENABLE"),
                "KERNEL_SANDBOX_ENABLE": os.getenv("KERNEL_SANDBOX_ENABLE"),
            },
        },
        ensure_ascii=False,
    )
)
"""


def _inspect_workflow(profile: str) -> dict[str, Any] | ProbeOutcome:
    """子进程内构建工作流图并回传节点/边/开关快照（隔离 config 导入时序）。"""
    rc, out, err = run_cmd(
        [sys.executable, "-c", _WORKFLOW_INSPECT_SCRIPT],
        timeout=600.0,
        env={"AITESTER_PROFILE": profile, **_llm_env()},
        cwd=str(PROJECT_ROOT),
    )
    if rc != 0:
        return error(f"工作流装配子进程 rc={rc}（profile={profile}）", stderr_tail=_tail(err, 800))
    marker_lines = [line for line in out.splitlines() if line.startswith("__E2E_JSON__")]
    if not marker_lines:
        return error("工作流装配子进程未回传结构化快照", stdout_tail=_tail(out, 800), stderr_tail=_tail(err, 400))
    try:
        return json.loads(marker_lines[-1][len("__E2E_JSON__") :])
    except json.JSONDecodeError as exc:
        return error(f"工作流装配快照 JSON 损坏: {exc}")


_FAST_NODES = {"planner", "generator", "executor", "debugger", "patch_applier"}
_FAST_EDGES = {
    "planner->generator",
    "generator->executor",
    "executor->debugger",
    "debugger->patch_applier",
    "patch_applier->executor",
}


def probe_workflow_fast_assembly() -> ProbeOutcome:
    """fast 档（历史默认）节点/边装配：无 mutation_advisor / diagnosis / cross_file。"""
    snapshot = _inspect_workflow("fast")
    if isinstance(snapshot, ProbeOutcome):
        return snapshot
    nodes = set(snapshot.get("nodes") or [])
    edges = set(snapshot.get("edges") or [])
    if snapshot.get("active_profile") != "fast":
        return fail(f"fast 档 ACTIVE_PROFILE={snapshot.get('active_profile')!r}")
    missing_nodes = sorted(_FAST_NODES - nodes)
    missing_edges = sorted(_FAST_EDGES - edges)
    if missing_nodes or missing_edges:
        return fail(
            f"fast 档装配缺节点 {missing_nodes} / 缺边 {missing_edges}", nodes=sorted(nodes), edges=sorted(edges)
        )
    unexpected = sorted(nodes & {"mutation_advisor", "diagnosis", "cross_file_analyzer"})
    if unexpected:
        return fail(f"fast 档出现不应有的节点 {unexpected}", nodes=sorted(nodes))
    return ok(
        f"fast 档装配正确（{len(nodes)} 节点 / {len(edges)} 边）",
        profile="fast",
        nodes=sorted(nodes),
        edges=sorted(edges),
    )


def probe_workflow_logic_assembly() -> ProbeOutcome:
    """logic 档装配：预设开关实际注入（DETECTION_FIRST/FL_SPECTRAL）+ mutation_advisor 节点。"""
    snapshot = _inspect_workflow("logic")
    if isinstance(snapshot, ProbeOutcome):
        return snapshot
    nodes = set(snapshot.get("nodes") or [])
    edges = set(snapshot.get("edges") or [])
    flags = snapshot.get("flags") or {}
    if snapshot.get("active_profile") != "logic":
        return fail(f"logic 档 ACTIVE_PROFILE={snapshot.get('active_profile')!r}")
    preset_missing = [key for key in ("DETECTION_FIRST_ENABLE", "FL_SPECTRAL_ENABLE") if flags.get(key) != "true"]
    if preset_missing:
        return fail(f"logic 档预设未注入: {preset_missing}", flags=flags)
    if "mutation_advisor" not in nodes:
        return fail("logic 档缺 mutation_advisor 节点（MUTATION_ADVISOR_ENABLE=true 预设未生效）", nodes=sorted(nodes))
    required_edges = {"executor->mutation_advisor", "mutation_advisor->generator", "debugger->patch_applier"}
    missing_edges = sorted(required_edges - edges)
    if missing_edges:
        return fail(f"logic 档缺边 {missing_edges}", edges=sorted(edges))
    return ok(
        f"logic 档装配正确（{len(nodes)} 节点，mutation_advisor 环在场，预设开关已注入）",
        profile="logic",
        nodes=sorted(nodes),
        edges=sorted(edges),
        flags=flags,
    )


def probe_workflow_logic_invoke() -> ProbeOutcome:
    """logic 档最小任务真实 invoke：test_plan / generated_test / trace / 终态字段齐全。

    LLM 调用 = planner 1 + generator 1 = 2 次（debugger=False 显式关闭修复循环）。
    """
    os.environ.update(_llm_env("logic"))
    buggy = 'def add(a, b):\n    """Return the sum of a and b."""\n    return a - b\n'
    try:
        final_state, elapsed = invoke_workflow(
            buggy,
            module_name="e2e_calc",
            target_function="add",
            planner=True,
            debugger=False,
            allow_regeneration=False,
            max_iterations=1,
        )
    except Exception as exc:  # 框架层：workflow 崩溃 = 功能故障（error）
        return error(f"logic 档 invoke 崩溃: {type(exc).__name__}: {exc}")

    from src.graph.workflow import StopReason

    test_plan = final_state.get("test_plan")
    generated = final_state.get("generated_test")
    trace = final_state.get("execution_trace")
    stop_reason = _effective_stop_reason(final_state)
    checks: dict[str, bool] = {
        "test_plan_is_dict": isinstance(test_plan, dict),
        "test_plan_has_structure": isinstance(test_plan, dict)
        and bool(test_plan.get("test_cases") or test_plan.get("function_name")),
        "generated_test_parseable": isinstance(generated, str) and _is_parseable_python(generated),
        "execution_trace_present": isinstance(trace, list) and len(trace) >= 1,
        "test_passed_is_bool": isinstance(final_state.get("test_passed"), bool),
        "iteration_present": isinstance(final_state.get("iteration"), int),
        "stop_reason_present": isinstance(stop_reason, str) and stop_reason in {r.value for r in StopReason},
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {
        "elapsed_s": round(elapsed, 2),
        "stop_reason": stop_reason,
        "test_passed": final_state.get("test_passed"),
        "iteration": final_state.get("iteration"),
        "test_cases": len(test_plan.get("test_cases") or []) if isinstance(test_plan, dict) else None,
        "generated_test_len": len(generated or ""),
        "execution_trace_len": len(trace or []) if isinstance(trace, list) else None,
        "checks": checks,
        **_usage_evidence(),
    }
    try:
        target_path = Path(str(final_state.get("target_file") or ""))
        _rmtree(target_path.parent if target_path.parent.name.startswith("aitester_") else None)
    except OSError:  # pragma: no cover - 清理失败不改变判定
        pass
    if bad:
        return fail(f"logic 档 invoke 终态字段缺失/异常: {bad}", **evidence)
    return ok(
        f"logic 档 invoke 正常（stop_reason={stop_reason}，trace={evidence['execution_trace_len']} 条）", **evidence
    )


def _is_parseable_python(code: str) -> bool:
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


# ─── 3. agents 组 ────────────────────────────────────────────────────────────

_BUGGY_ADD = 'def add(a, b):\n    """Return the sum of a and b."""\n    return a - b\n'


def probe_agents_planner_structured_plan() -> ProbeOutcome:
    """planner 真实 LLM：输出结构化 test_plan（test_cases + logic_analysis）。"""
    os.environ.update(_llm_env())
    try:
        from src.agents.planner import PlannerAgent

        plan = PlannerAgent().plan(_BUGGY_ADD, "add")
    except json.JSONDecodeError as exc:  # 模型输出非 JSON：模型未产出（非功能故障）
        return skip(f"planner 模型未产出合法 JSON（非功能故障）: {exc}", **_usage_evidence())
    except Exception as exc:
        return error(f"planner 崩溃: {type(exc).__name__}: {exc}")
    if not isinstance(plan, dict):
        return fail(f"planner 输出非 dict: {type(plan).__name__}")
    test_cases = plan.get("test_cases")
    if not isinstance(test_cases, list) or not test_cases:
        return skip(
            "planner 未产出 test_cases（模型未产出，非功能故障）",
            logic_degraded=plan.get("logic_degraded"),
            keys=sorted(plan),
            **_usage_evidence(),
        )
    case_keys_ok = all(
        isinstance(case, dict) and {"case_name", "input_args", "expected_output"} <= set(case) for case in test_cases
    )
    logic = plan.get("logic_analysis")
    if not case_keys_ok:
        return fail(
            "planner test_cases 结构不符合契约（缺 case_name/input_args/expected_output）", sample=test_cases[:1]
        )
    if not isinstance(logic, dict):
        return fail(f"planner logic_analysis 缺失/非 dict: {type(logic).__name__}")
    return ok(
        f"planner 结构化计划正常（{len(test_cases)} 用例，logic_degraded={plan.get('logic_degraded')}）",
        test_cases=len(test_cases),
        logic_keys=sorted(logic),
        logic_degraded=plan.get("logic_degraded"),
        **_usage_evidence(),
    )


def probe_agents_generator_parseable() -> ProbeOutcome:
    """generator 真实 LLM：由固定计划生成可解析 pytest 文件（含 import 与断言）。"""
    os.environ.update(_llm_env())
    plan: dict[str, Any] = {
        "function_name": "add",
        "description": "两数加法",
        "logic_analysis": {
            "input_domain": "整数对",
            "output_domain": "和",
            "preconditions": ["a、b 为整数"],
            "postconditions": ["返回值等于 a + b"],
            "edge_cases": ["任一参数为 0"],
        },
        "test_cases": [
            {"case_name": "basic", "input_args": "(2, 3)", "expected_output": "5", "category": "basic"},
            {"case_name": "zero", "input_args": "(0, 5)", "expected_output": "5", "category": "edge"},
        ],
    }
    try:
        from src.agents.generator import GeneratorAgent

        generated = GeneratorAgent().generate(plan, _BUGGY_ADD, module_name="e2e_calc", focus_function="add")
    except Exception as exc:
        return error(f"generator 崩溃: {type(exc).__name__}: {exc}")
    if not generated or not generated.strip():
        return skip("generator 未产出代码（模型未产出，非功能故障）", **_usage_evidence())
    if not _is_parseable_python(generated):
        return fail("generator 输出不是合法 Python", generated_head=generated[:400], **_usage_evidence())
    checks = {
        "has_test_function": "def test" in generated,
        "has_import": "from e2e_calc import" in generated,
        "has_assert": "assert " in generated,
    }
    bad = [name for name, passed in checks.items() if not passed]
    if bad:
        return fail(f"generator 输出缺少 pytest 必要元素: {bad}", generated_head=generated[:600], **_usage_evidence())
    return ok(
        f"generator 生成可解析 pytest（{len(generated)} 字符，{generated.count('def test')} 个测试函数）",
        generated_len=len(generated),
        test_functions=generated.count("def test"),
        **_usage_evidence(),
    )


def probe_agents_executor_run() -> ProbeOutcome:
    """executor 本地沙箱：运行生成测试并回报 passed / coverage / failed_cases（零 LLM）。"""
    from src.agents.executor import ExecutorAgent

    tmpdir = make_temp_dir("aitester_e2e_executor_")
    try:
        target = _write_module(tmpdir, "calc", "def add(a, b):\n    return a + b\n")
        pass_test = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
        fail_test = "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 6\n"
        executor = ExecutorAgent(timeout=60)
        good = executor.execute(pass_test, str(target))
        bad = executor.execute(fail_test, str(target))
    finally:
        _rmtree(tmpdir)
    checks = {
        "pass_case_passed": good.get("passed") is True,
        "pass_case_coverage": isinstance(good.get("coverage"), int | float),
        "fail_case_failed": bad.get("passed") is False,
        "fail_case_has_failed_cases": isinstance(bad.get("failed_cases"), list)
        and len(bad.get("failed_cases") or []) >= 1,
    }
    bad_checks = [name for name, passed in checks.items() if not passed]
    evidence = {
        "pass_case": {"passed": good.get("passed"), "coverage": good.get("coverage")},
        "fail_case": {"passed": bad.get("passed"), "failed_cases": len(bad.get("failed_cases") or [])},
    }
    if bad_checks:
        return fail(f"executor 行为不符合契约: {bad_checks}", **evidence)
    return ok(
        f"executor 沙箱正常（通过用例 passed=True/coverage={good.get('coverage')}，失败用例失败可归因）", **evidence
    )


# ─── 4. repair 组 ────────────────────────────────────────────────────────────


def probe_repair_debugger_patch_chain() -> ProbeOutcome:
    """真实修复链：失败测试 → Debugger(1 次 LLM) → safe_apply_patch → executor 复跑。

    区分三类结果：
    - pass：补丁安全应用且修复后测试通过（功能链路可用）；
    - skip：模型未产出补丁（model_nonproduction，非功能故障）；
    - fail：补丁产出但应用/复跑失败（功能故障，附证据）。
    """
    os.environ.update(_llm_env())
    from src.agents.executor import ExecutorAgent
    from src.tools.patch_applier import dangerous_api_added, safe_apply_patch

    tmpdir = make_temp_dir("aitester_e2e_repair_")
    try:
        target = _write_module(tmpdir, "calc_add", _BUGGY_ADD)
        test_code = "from calc_add import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"
        executor = ExecutorAgent(timeout=60)
        before = executor.execute(test_code, str(target))
        if before.get("passed") is not False:
            return error("修复链前置不成立：缺陷代码上测试未失败（执行器/样例异常）")
        try:
            from src.agents.debugger import DebuggerAgent

            debug_result = DebuggerAgent().debug(
                target_code=_BUGGY_ADD,
                test_output=str(before.get("output") or ""),
                failed_cases=before.get("failed_cases") or [],
                target_module="calc_add",
            )
        except Exception as exc:
            return error(f"Debugger 崩溃: {type(exc).__name__}: {exc}", **_usage_evidence())
        patch = str(debug_result.get("patch") or "")
        if not patch.strip():
            return skip(
                "模型未产出补丁（model_nonproduction，非功能故障）",
                error_category=debug_result.get("error_category"),
                root_cause=debug_result.get("root_cause"),
                **_usage_evidence(),
            )
        applied_code, applied = safe_apply_patch(_BUGGY_ADD, patch)
        added_danger = dangerous_api_added(_BUGGY_ADD, applied_code)
        evidence: dict[str, Any] = {
            "patch_len": len(patch),
            "patch_applied": applied,
            "dangerous_api_added": added_danger,
            "error_category": debug_result.get("error_category"),
            "root_cause": str(debug_result.get("root_cause") or "")[:200],
            **_usage_evidence(),
        }
        if not applied:
            return fail("补丁产出但安全应用失败（功能故障/守卫拒绝，需诊断）", **evidence)
        if added_danger:
            return fail(f"补丁引入危险 API 却未被拦截: {added_danger}", **evidence)
        target.write_text(applied_code, encoding="utf-8")
        after = executor.execute(test_code, str(target))
        evidence["after_passed"] = after.get("passed")
        if after.get("passed") is not True:
            return fail("补丁应用成功但修复后测试仍失败（功能故障）", **evidence)
        return ok("修复链正常：Debugger 产出补丁 → 安全应用 → 修复后测试通过", **evidence)
    finally:
        _rmtree(tmpdir)


def probe_repair_graph_loop() -> ProbeOutcome:
    """真实 graph 修复环：generator → executor → debugger → patch_applier → executor。

    与 `repair-debugger-patch-chain` 的分工：本探针验证**图装配/路由**（executor
    失败 → _should_debug("debug") → debugger → patch_applier → 复跑），以及
    patch_applier 的守卫链与 repair_history 观测字段；planner=False +
    max_iterations=1 控制真实 LLM 调用 ≈2 次（generator 1 + debugger 1）。

    分类纪律（与任务书一致）：模型未产出补丁 → skip（model_nonproduction，
    非功能故障）；补丁产出但未安全应用/复跑失败 → fail（功能故障，附证据）。
    """
    os.environ.update(_llm_env())
    buggy = 'def add(a, b):\n    """Return the sum of a and b."""\n    return a - b\n'
    try:
        final_state, elapsed = invoke_workflow(
            buggy,
            module_name="e2e_repair_loop",
            target_function="add",
            planner=False,
            debugger=True,
            allow_regeneration=False,
            max_iterations=1,
        )
    except Exception as exc:
        return error(f"修复环 invoke 崩溃: {type(exc).__name__}: {exc}", **_usage_evidence())

    from src.graph.workflow import StopReason
    from src.tools.patch_applier import dangerous_api_added

    repair_history = final_state.get("repair_history") or []
    patch = str(final_state.get("patch") or "")
    final_code = str(final_state.get("target_code") or "")
    stop_reason = _effective_stop_reason(final_state)
    applied_rounds = [entry for entry in repair_history if entry.get("patch_applied")]
    added_danger = dangerous_api_added(buggy, final_code) if final_code else []
    evidence: dict[str, Any] = {
        "elapsed_s": round(elapsed, 2),
        "iteration": final_state.get("iteration"),
        "test_passed": final_state.get("test_passed"),
        "stop_reason": stop_reason,
        "debugger_entered": bool(repair_history),
        "repair_rounds": len(repair_history),
        "patch_produced": bool(patch),
        "patch_applied_rounds": len(applied_rounds),
        "target_code_changed": final_code != buggy,
        "dangerous_api_added": added_danger,
        **_usage_evidence(),
    }
    if not repair_history and not patch:
        return skip("修复环未进入 debugger（模型/测试未触发修复路径，非功能故障）", **evidence)
    if stop_reason is None or (isinstance(stop_reason, str) and stop_reason not in {r.value for r in StopReason}):
        return fail(f"修复环终态 stop_reason 异常: {stop_reason!r}", **evidence)
    if added_danger:
        return fail(f"修复环最终代码引入危险 API: {added_danger}", **evidence)
    if not applied_rounds:
        return skip("debugger 已进入但补丁未应用（模型未产出/守卫拒绝，非功能故障）", **evidence)
    if not _is_parseable_python(final_code):
        return fail("修复环最终 target_code 非合法 Python", **evidence)
    if final_state.get("test_passed") is not True:
        return fail("修复环补丁已应用但终态测试未通过（功能故障）", **evidence)
    return ok(
        f"修复环正常：debugger 进入 {len(repair_history)} 轮 → patch_applier 应用 → 复跑通过（stop_reason={stop_reason}）",
        **evidence,
    )


# ─── 5. safety 组（全部零 LLM：直接调工具层）────────────────────────────────

_SAFE_ORIGINAL = "def f(x):\n    return x + 1\n"


def probe_safety_dangerous_api_guard() -> ProbeOutcome:
    """补丁危险 API 守卫：os.system / from-import 别名 / eval 均被拒绝应用。"""
    from src.tools.patch_applier import dangerous_api_added, safe_apply_patch

    cases = {
        "os_system": 'def f(x):\n    import os\n    os.system("echo pwn")\n    return x + 1\n',
        "from_import_alias": 'def f(x):\n    from os import system\n\n    system("echo pwn")\n    return x + 1\n',
        "eval": 'def f(x):\n    eval("1 + 1")\n    return x + 1\n',
    }
    results: dict[str, Any] = {}
    failures: list[str] = []
    for name, danger in cases.items():
        new_code, applied = safe_apply_patch(_SAFE_ORIGINAL, danger)
        results[name] = {"applied": applied, "unchanged": new_code == _SAFE_ORIGINAL}
        if applied or new_code != _SAFE_ORIGINAL:
            failures.append(name)
    clean = "def f(x):\n    return x + 2\n"
    clean_code, clean_applied = safe_apply_patch(_SAFE_ORIGINAL, clean)
    clean_added = dangerous_api_added(_SAFE_ORIGINAL, clean_code)
    if not clean_applied or clean_added:
        failures.append("clean_patch")
    if failures:
        return fail(f"危险 API 守卫未拦截: {failures}", cases=results, clean_applied=clean_applied)
    return ok("危险 API 守卫正常：os.system / from-import 别名 / eval 均拒绝，正常补丁放行", cases=results)


def probe_safety_naming_contract_guard() -> ProbeOutcome:
    """命名契约守卫：删除模块级符号被拒（apply 层 + 契约检查层双重拦截）。"""
    from src.tools.patch_applier import apply_patch_to_code, check_naming_contract

    original = "def f(x):\n    return x + 1\n\n\ndef g(y):\n    return y * 2\n"
    deleting_full_file = "import math\n\n\ndef f(x):\n    return x + 2\n"
    contract_ok, missing = check_naming_contract(original, "def f(x):\n    return x + 2\n")
    applied_code, applied = apply_patch_to_code(original, deleting_full_file)
    checks = {
        "contract_detects_missing": contract_ok is False and missing == ["g"],
        "apply_rejects_full_file_drop": applied is False,
        "original_preserved": applied_code == original,
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {"contract_ok": contract_ok, "missing": missing, "apply_applied": applied}
    if bad:
        return fail(f"命名契约守卫异常: {bad}", **evidence)
    return ok("命名契约守卫正常：删除模块级符号被拒（契约检查 missing=['g'] + apply 保守拒绝）", **evidence)


def probe_safety_test_hacking_detection() -> ProbeOutcome:
    """补丁测试黑客检测：删断言 / 硬编码输入分支 / 新增吞异常 均命中信号。"""
    from src.tools.patch_test_hacking import detect_test_hacking

    base = "def f(x):\n    return x + 1\n"
    cases = {
        "assert_weakened": (
            "def test_a():\n    assert f(1) == 2\n",
            "def test_a():\n    pass\n",
            "assert_weakened",
        ),
        "hardcoded_branch": (
            "def f(x):\n    return x + 1\n",
            "def f(x):\n    if x == 42:\n        return 42\n    return x + 1\n",
            "hardcoded_input_branch",
        ),
        "exception_swallow": (
            "def f(x):\n    return x + 1\n",
            "def f(x):\n    try:\n        return x + 1\n    except Exception:\n        pass\n",
            "exception_swallow_added",
        ),
    }
    results: dict[str, Any] = {}
    failures: list[str] = []
    for name, (original, patched, expected_signal) in cases.items():
        verdict = detect_test_hacking(original, patched)
        raw_signals = verdict.get("signals")
        signals = [str(item) for item in raw_signals] if isinstance(raw_signals, list) else []
        results[name] = {"suspected": verdict.get("suspected"), "signals": signals}
        if verdict.get("suspected") is not True or expected_signal not in signals:
            failures.append(name)
    clean = detect_test_hacking(base, "def f(x):\n    return x + 2\n")
    if clean.get("suspected") is True:
        failures.append("clean_false_positive")
    if failures:
        return fail(f"测试黑客检测异常: {failures}", cases=results, clean=clean)
    return ok("测试黑客检测正常：三类信号全部命中且正常补丁无误报", cases=results)


def probe_safety_deterministic_repair() -> ProbeOutcome:
    """确定性修复：缺失标准库 import 可零 LLM 产出补丁；无匹配时明确 abstain。"""
    from src.tools.deterministic_repair import attempt_deterministic_repair, deterministic_repair_first_enabled

    hit = attempt_deterministic_repair(
        target_code="def f(xs):\n    return math.sqrt(sum(xs))\n",
        test_output="NameError: name 'math' is not defined",
        error_category="LOGIC_ERROR",
    )
    miss = attempt_deterministic_repair(
        target_code="def f(x):\n    return x + 1\n",
        test_output="AssertionError: 1 != 2",
        error_category="ASSERTION",
    )
    patch_code = str(hit.get("patch_code") or "")
    checks = {
        "hit_attempted": hit.get("attempted") is True,
        "hit_method": hit.get("method") == "missing_import_inference",
        "hit_produced_and_parseable": bool(patch_code)
        and _is_parseable_python(patch_code)
        and "import math" in patch_code,
        "miss_abstained": miss.get("attempted") is False and miss.get("reason") == "no_matching_transformer",
        "switch_default_off_reflects_env": deterministic_repair_first_enabled() in (True, False),
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {
        "hit": {k: hit.get(k) for k in ("attempted", "method", "reason")},
        "miss": {k: miss.get(k) for k in ("attempted", "method", "reason")},
        "patch_has_import": "import math" in patch_code,
    }
    if bad:
        return fail(f"确定性修复异常: {bad}", **evidence)
    return ok("确定性修复正常：NameError→import 零 LLM 产出补丁，无匹配场景显式 abstain", **evidence)


def probe_safety_patch_rollback() -> ProbeOutcome:
    """快照回滚协议：P2P 回归失败自动回滚；P2P 通过保留补丁；开关可观测。"""
    from src.tools.patch_rollback import PatchRollbackProtocol, snapshot_rollback_enabled

    os.environ["PATCH_SNAPSHOT_ROLLBACK_ENABLE"] = "true"
    os.environ["PATCH_ROLLBACK_FAIL_CLOSED"] = "true"
    try:
        original = "def f():\n    return 1\n"
        broken_patch = "def f():\n    return 2\n"  # 无法通过 P2P（期望 1）
        good_patch = "def f():\n    return 1\n\n\ndef g():\n    return 3\n"  # 保留原行为 + 新符号
        p2p_test = "from rollback_target import f\n\n\ndef test_p2p():\n    assert f() == 1\n"
        protocol = PatchRollbackProtocol()
        rolled = protocol.run(original, broken_patch, p2p_test, "rollback_target")
        kept = protocol.run(original, good_patch, p2p_test, "rollback_target")
        switch_on = snapshot_rollback_enabled()
    finally:
        os.environ.pop("PATCH_SNAPSHOT_ROLLBACK_ENABLE", None)
        os.environ.pop("PATCH_ROLLBACK_FAIL_CLOSED", None)
    switch_off = snapshot_rollback_enabled()
    checks = {
        "broken_patch_rolled_back": rolled.get("rolled_back") is True and rolled.get("verdict") == "regression_failed",
        "broken_patch_restored_original": rolled.get("applied_code") == original,
        "good_patch_kept": kept.get("success") is True and kept.get("rolled_back") is False,
        "switch_on_when_enabled": switch_on is True,
        "switch_off_by_default": switch_off is False,
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {
        "rolled_back": {k: rolled.get(k) for k in ("verdict", "rolled_back", "success", "p2p_returncode")},
        "kept": {k: kept.get(k) for k in ("verdict", "rolled_back", "success")},
    }
    if bad:
        return fail(f"快照回滚协议异常: {bad}", **evidence)
    return ok("快照回滚协议正常：P2P 失败自动回滚、通过则保留，开关默认关/开启生效", **evidence)


# ─── 6. observability 组 ────────────────────────────────────────────────────


def probe_observability_trace_redaction() -> ProbeOutcome:
    """trace JSONL：落盘 task_start/node/task_end，敏感串脱敏后再写盘。"""
    from src.observability.trace import TraceSession

    tmpdir = make_temp_dir("aitester_e2e_trace_")
    fake_secret = "sk-" + "a" * 32
    try:
        session = TraceSession("e2e_probe_trace", str(tmpdir), {"baseline": "e2e_probe"})
        session.record_node("planner", output_summary="test_plan ok", decision="plan_complete", duration_ms=1.0)
        session.record_task_end(True, token_usage={"total_tokens": 1}, extra={"api_key": fake_secret})
        trace_file = tmpdir / "e2e_probe_trace.trace.jsonl"
        if not trace_file.is_file():
            return fail(f"trace 文件未落盘: {trace_file}")
        raw = trace_file.read_text(encoding="utf-8")
        records = [json.loads(line) for line in raw.splitlines() if line.strip()]
        events = [str(rec.get("event")) for rec in records]
    finally:
        _rmtree(tmpdir)
    checks = {
        "file_parseable_jsonl": bool(records),
        "has_task_start_and_end": "task_start" in events and "task_end" in events,
        "has_node_record": "node" in events,
        "secret_not_leaked": fake_secret not in raw,
        "redaction_marker_present": "REDACTED" in raw,
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {"events": events, "records": len(records), "redacted": "REDACTED" in raw}
    if bad:
        return fail(f"trace 落盘/脱敏异常: {bad}", **evidence)
    return ok("trace 正常：JSONL 三事件落盘且敏感串已脱敏", **evidence)


def probe_observability_event_bus() -> ProbeOutcome:
    """事件总线：发布/订阅/统计可用；EVENT_BUS_ENABLE=false 时 no-op。"""
    from src.graph.event_bus import WorkflowCompleted, get_event_bus, publish_event

    bus = get_event_bus()
    received: list[str] = []

    def _listener(event: Any) -> None:
        received.append(str(getattr(event, "EVENT_NAME", "?")))

    os.environ.pop("EVENT_BUS_ENABLE", None)
    bus.clear()
    bus.subscribe("workflow_completed", _listener)
    publish_event(WorkflowCompleted(task_uuid="e2e", test_passed=True, iteration=1))
    enabled_stats = bus.stats()
    bus.clear()
    os.environ["EVENT_BUS_ENABLE"] = "false"
    try:
        publish_event(WorkflowCompleted(task_uuid="e2e-off", test_passed=False))
        disabled_stats = bus.stats()
    finally:
        os.environ.pop("EVENT_BUS_ENABLE", None)
        bus.clear()
    checks = {
        "listener_invoked": received == ["workflow_completed"],
        "stats_counted": (enabled_stats.get("counts") or {}).get("workflow_completed") == 1,
        "subscribed_listed": "workflow_completed" in (enabled_stats.get("subscribed") or []),
        "disabled_is_noop": disabled_stats.get("counts") == {},
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {"received": received, "enabled_stats": enabled_stats, "disabled_stats": disabled_stats}
    if bad:
        return fail(f"事件总线异常: {bad}", **evidence)
    return ok("事件总线正常：发布→订阅回调/计数一致，关闭开关后 no-op", **evidence)


# ─── 7. analysis 组（零 LLM 分析工具）──────────────────────────────────────

_BUGGY_MAX = "def find_max(nums):\n    best = nums[0]\n    for x in nums:\n        if x < best:\n            best = x\n    return best\n"


def probe_analysis_fl_spectral_topk() -> ProbeOutcome:
    """FL_spectral（Ochiai）：构造失败/通过测试行覆盖，Top-k 命中注入缺陷位置。"""
    from src.agents.fl_spectral import compute_ochiai_scores_from_contexts, rank_top_k

    tree = ast.parse(_BUGGY_MAX)
    buggy_branch_line = next(
        node.body[0].lineno  # type: ignore[attr-defined]
        for node in ast.walk(tree)
        if isinstance(node, ast.If) and node.body
    )
    # 构造：失败测试执行到缺陷分支体（line 5），通过测试不执行该行（line 4 条件不成立）
    failed_contexts = {f"test_fail_{i}": {2, 3, 4, buggy_branch_line, 6} for i in range(2)}
    passed_contexts = {f"test_pass_{i}": {2, 3, 4, 6} for i in range(2)}
    scores = compute_ochiai_scores_from_contexts(failed_contexts, passed_contexts)
    top = rank_top_k(scores, k=3) if scores else []
    top_lines = [item["line"] for item in top]
    if not scores:
        return fail("Ochiai 打分为空（构造的覆盖数据未产生候选行）")
    if not top:
        return fail("Top-k 为空")
    if top[0]["line"] != buggy_branch_line:
        return fail(
            f"Top-1 未命中缺陷分支行（期望 {buggy_branch_line}，实测 {top[0]['line']}）",
            top=top,
        )
    defect_lines = {2, 3, 4, buggy_branch_line, 6}
    if not set(top_lines) <= defect_lines:
        return fail("Top-k 行号越出目标函数范围", top=top)
    return ok(
        f"FL_spectral 正常：Top-1 命中缺陷分支行 {buggy_branch_line}（Top-k={top_lines}）",
        buggy_line=buggy_branch_line,
        top=top,
        candidate_lines=len(scores),
    )


def probe_analysis_fault_localizer_gold() -> ProbeOutcome:
    """fault localizer 反事实定位：gold 变更函数被定位，Hit@1/Hit@3/MRR 正确。"""
    from src.agents.fault_localizer import (
        build_gold_injection_localization,
        localization_hit,
        localization_rank_metrics,
    )

    fixed = _BUGGY_MAX.replace("if x < best:", "if x > best:")
    loc = build_gold_injection_localization(_BUGGY_MAX, fixed)
    if not isinstance(loc, dict):
        return fail("gold injection 定位构造返回 None（无法从 gold 变更定位函数）")
    hit = localization_hit(loc, {"find_max"}) or {}
    rank = localization_rank_metrics(loc, {"find_max"}) or {}
    mrr_value = rank.get("localization_mrr")
    checks = {
        "function_located": loc.get("function_name") == "find_max",
        "line_range_sane": isinstance(loc.get("line_start"), int) and isinstance(loc.get("line_end"), int),
        "hit_function": hit.get("localization_hit_function") is True,
        "hit_at_3": rank.get("localization_hit_function_at_3") is True,
        "mrr": isinstance(mrr_value, int | float) and float(mrr_value) > 0,
        "candidates_nonempty": isinstance(loc.get("candidates"), list) and len(loc.get("candidates") or []) >= 1,
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {
        "function_name": loc.get("function_name"),
        "line_start": loc.get("line_start"),
        "line_end": loc.get("line_end"),
        "hit": hit,
        "rank": rank,
    }
    if bad:
        return fail(f"fault localizer 定位异常: {bad}", **evidence)
    return ok(f"fault localizer 正常：gold 变更函数 find_max 命中（MRR={rank.get('localization_mrr')}）", **evidence)


def probe_analysis_multi_candidate() -> ProbeOutcome:
    """multi-candidate：合法/非法候选静态筛选 + 最小改动择优（零 LLM）。"""
    from src.tools.multi_candidate import CandidateResult, select_best_candidate, static_validate_patch

    original = "def f(x):\n    return x + 1\n"
    ok_flag, reason, applied_code = static_validate_patch(original, "def f(x):\n    return x + 2\n")
    bad_flag, bad_reason, _ = static_validate_patch(original, "def f(x):\n    return x +\n")
    # 候选 0 = 大改动（5 行），候选 1 = 最小改动（2 行）——择优应选 index=1
    big_patch = "def f(x):\n    y = x + 1\n    z = y * 2\n    w = z - 1\n    return w / 2\n"
    big_ok, _, big_code = static_validate_patch(original, big_patch)
    candidates = [
        CandidateResult(index=0, patch=big_patch, new_code=big_code, static_passed=big_ok),
        CandidateResult(index=1, patch="def f(x):\n    return x + 2\n", new_code=applied_code, static_passed=True),
        CandidateResult(index=2, patch="", static_passed=False, static_reason="空补丁"),
    ]
    best = select_best_candidate([item for item in candidates if item.static_passed], original)
    checks = {
        "valid_patch_passes": ok_flag is True and reason == "",
        "invalid_patch_rejected": bad_flag is False and bool(bad_reason),
        "best_selected": best is not None,
        "best_minimal_change": best is not None and best.index == 1,
        "all_rejected_returns_none": select_best_candidate(
            [CandidateResult(index=0, patch="", static_passed=False, static_reason="x")], original
        )
        is None,
    }
    bad = [name for name, passed in checks.items() if not passed]
    evidence = {
        "valid_reason": reason,
        "invalid_reason": bad_reason,
        "best_index": best.index if best is not None else None,
    }
    if bad:
        return fail(f"multi-candidate 异常: {bad}", **evidence)
    return ok(f"multi-candidate 正常：静态筛选通过/拒绝正确，最小改动候选 index={evidence['best_index']}", **evidence)


# ─── PROBES 清单 ─────────────────────────────────────────────────────────────
# name 全局唯一；group 与框架 render_markdown 的功能矩阵分桶对齐。
def probe_cli_doctor():
    """P-3：`python main.py doctor --json` 零 LLM 自检入口可用且不泄漏凭证。"""
    env = {"AITESTER_E2E_LLM": "false", "AITESTER_LLM_CACHE": "0"}
    rc, out, err = run_cmd(
        [sys.executable, "main.py", "doctor", "--groups", "budget", "--json"],
        timeout=180.0,
        env=env,
    )
    if rc != 0:
        return fail(f"doctor --json rc={rc}：{(err or out)[-300:]}")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError as exc:
        return fail(f"doctor --json stdout 不是纯 JSON：{exc}；head={out[:200]!r}")
    checks = {
        "schema": payload.get("schema") == "aitester_doctor/1",
        "zero_llm": (payload.get("command") or {}).get("zero_llm") is True,
        "checks_present": isinstance(payload.get("checks"), list) and len(payload["checks"]) >= 5,
        "matrix_present": isinstance(payload.get("matrix"), dict),
        "conclusion_present": "conclusion" in payload,
        "no_secret_leak": "sk-" not in out and "API_KEY=" not in out and "LLM_1_API_KEY" not in out,
    }
    if not all(checks.values()):
        return fail(f"doctor --json 契约不完整：{checks}", payload_head=out[:400])
    matrix_summary = (payload.get("matrix") or {}).get("summary") or {}
    return ok(
        f"doctor 零 LLM 自检正常（checks={len(payload['checks'])}，matrix pass={matrix_summary.get('pass')}，stdout 纯 JSON）",
        checks=checks,
        matrix_summary=matrix_summary,
    )


PROBES: list[Probe] = [
    # CLI
    Probe(
        name="cli-help",
        group="cli",
        func=probe_cli_help,
        description="python main.py --help：退出码 0 且 4 个子命令在帮助面",
    ),
    Probe(
        name="cli-list-examples",
        group="cli",
        func=probe_cli_list_examples,
        description="list-examples：列出 examples 文件并给出使用示例",
    ),
    Probe(
        name="cli-check-dataset-quixbugs",
        group="cli",
        func=probe_cli_check_dataset,
        description="check-dataset quixbugs：加载 50 任务 + 质量报告",
    ),
    Probe(
        name="cli-run-json-single",
        group="cli",
        func=probe_cli_run_json_single,
        requires_llm=True,
        timeout_s=300.0,
        description="run examples/calculator.py --json --verbose：真 LLM 下 stdout 为单一合法 JSON（1 次调用）",
    ),
    Probe(
        name="cli-run-multi-parallel",
        group="cli",
        func=probe_cli_run_multi_parallel,
        requires_llm=True,
        timeout_s=300.0,
        description="run 两文件 --parallel 2 --json：真 LLM 下每任务一份合法 JSON（2 次调用）",
    ),
    # workflow
    Probe(
        name="workflow-fast-assembly",
        group="workflow",
        func=probe_workflow_fast_assembly,
        timeout_s=240.0,
        description="fast 档 build_workflow：节点/边装配正确（无逻辑档节点）",
    ),
    Probe(
        name="workflow-logic-assembly",
        group="workflow",
        func=probe_workflow_logic_assembly,
        timeout_s=240.0,
        description="logic 档 build_workflow：预设开关注入 + mutation_advisor 环在场",
    ),
    Probe(
        name="workflow-logic-invoke",
        group="workflow",
        func=probe_workflow_logic_invoke,
        requires_llm=True,
        timeout_s=420.0,
        description="logic 档最小任务真实 invoke：test_plan/generated_test/trace/终态字段齐全（2 次调用）",
    ),
    # agents
    Probe(
        name="agents-planner-structured-plan",
        group="agents",
        func=probe_agents_planner_structured_plan,
        requires_llm=True,
        timeout_s=300.0,
        description="planner 真实 LLM 输出结构化 test_plan（1 次调用）",
    ),
    Probe(
        name="agents-generator-parseable-tests",
        group="agents",
        func=probe_agents_generator_parseable,
        requires_llm=True,
        timeout_s=300.0,
        description="generator 真实 LLM 生成可解析 pytest（import/断言齐全，1 次调用）",
    ),
    Probe(
        name="agents-executor-run",
        group="agents",
        func=probe_agents_executor_run,
        timeout_s=180.0,
        description="executor 本地沙箱运行生成测试并回报 passed/coverage/failed_cases",
    ),
    # repair
    Probe(
        name="repair-debugger-patch-chain",
        group="repair",
        func=probe_repair_debugger_patch_chain,
        requires_llm=True,
        timeout_s=360.0,
        description="真实修复链：Debugger(1 次 LLM)→安全应用补丁→修复后测试通过；区分模型未产出",
    ),
    Probe(
        name="repair-graph-loop",
        group="repair",
        func=probe_repair_graph_loop,
        requires_llm=True,
        timeout_s=420.0,
        description="真实 graph 修复环：executor 失败→debugger→patch_applier→复跑通过（≈2 次调用）",
    ),
    # safety
    Probe(
        name="safety-dangerous-api-guard",
        group="safety",
        func=probe_safety_dangerous_api_guard,
        timeout_s=120.0,
        description="补丁危险 API 守卫：os.system / from-import 别名 / eval 均拒绝",
    ),
    Probe(
        name="safety-naming-contract-guard",
        group="safety",
        func=probe_safety_naming_contract_guard,
        timeout_s=120.0,
        description="命名契约守卫：删除模块级符号被 apply 层 + 契约层双重拦截",
    ),
    Probe(
        name="safety-test-hacking-detection",
        group="safety",
        func=probe_safety_test_hacking_detection,
        timeout_s=120.0,
        description="补丁测试黑客检测：删断言/硬编码分支/吞异常命中且正常补丁无 FP",
    ),
    Probe(
        name="safety-deterministic-repair",
        group="safety",
        func=probe_safety_deterministic_repair,
        timeout_s=120.0,
        description="确定性修复：NameError→import 零 LLM 产出补丁；无匹配显式 abstain",
    ),
    Probe(
        name="safety-patch-rollback",
        group="safety",
        func=probe_safety_patch_rollback,
        timeout_s=240.0,
        description="快照回滚协议：P2P 回归失败自动回滚、通过保留、开关可观测",
    ),
    # observability
    # T 轮（2026-10-18）去重：observability-trace-redaction / observability-event-bus
    # 曾同时注册于本模块与 e2e_probes_platform.py —— 运行器按 name 去重时把第二份
    # 记入 load_errors 后静默丢弃（报告仍显示 66/66 pass，注册数实为 68）。
    # 现统一由 platform 模块（observability 专组）注册；本模块保留同名探针函数
    # `probe_observability_trace_redaction` / `probe_observability_event_bus`
    # 供单测直接调用，不再重复注册。
    # analysis
    Probe(
        name="analysis-fl-spectral-topk",
        group="localization",
        func=probe_analysis_fl_spectral_topk,
        timeout_s=120.0,
        description="FL_spectral（Ochiai）：Top-1 命中注入缺陷分支行",
    ),
    Probe(
        name="analysis-fault-localizer-gold",
        group="localization",
        func=probe_analysis_fault_localizer_gold,
        timeout_s=120.0,
        description="fault localizer 反事实定位：gold 变更函数命中 + Hit@1/@3/MRR",
    ),
    Probe(
        name="analysis-multi-candidate",
        group="localization",
        func=probe_analysis_multi_candidate,
        timeout_s=120.0,
        description="multi-candidate：静态筛选通过/拒绝 + 最小改动择优",
    ),
    # cli（P-3 新增：doctor 零 LLM 自检入口）
    Probe(
        name="cli-doctor-json",
        group="cli",
        func=probe_cli_doctor,
        timeout_s=180.0,
        description="main.py doctor --json 零 LLM 自检入口（schema/聚合/不泄漏凭证）",
    ),
]

__all__ = ["PROBES"]
