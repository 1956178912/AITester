#!/usr/bin/env python3
"""全功能端到端探针框架（N 轮，2026-10-17）：对项目**所有用户可见功能**做一次真实验证。

## 定位（与既有测试/门禁的分工）

- 单元测试（`tests/`，7994 条）验证**模块契约**；
- 集成/端到端脚本（`experiments/`）验证**单条研究链路**；
- 本框架补的是第三层：**功能清单级的 e2e 可达性验证**——"这个功能在真实
  装配（CLI / workflow / 真实 LLM / 真实子进程）下到底能不能用、有没有静默失效"。
  每个探针 = 一段可执行断言 + 证据字段；报告给出功能矩阵（按 group）。

## 探针纪律

1. **零 LLM 默认**：只有 `requires_llm=True` 的探针需要 `--include-llm` 且
   `AITESTER_E2E_LLM=true` 才执行；否则状态 = skip（不隐蔽地失败）。
2. **省钱**：LLM 探针自身限制 ≤2 次调用 / 探针（prompt 极小、max_tokens 小）；
   运行器强制 `AITESTER_LLM_CACHE=0`（真实调用而非缓存重放），单次全量 LLM
   探针成本应 < $0.05。
3. **不改仓库状态**：所有文件写入 tmp 目录；LLM 探针使用独立 cache namespace；
   不写入 `experiments/results/`（报告由 `--json-out/--md-out` 显式指定）。
4. **失败即证据**：探针异常返回 error（含 traceback 末行）；断言失败返回 fail
   （含实测值）；skip 必须带原因。

## 探针模块（按组拆分，互不依赖）

    scripts/tools/e2e_probes_workflow.py   # CLI / workflow / agents / repair / 安全守卫
    scripts/tools/e2e_probes_platform.py   # 预算 / 缓存 / RAG / 安全 / 执行器 / 数据集 / 可观测
    scripts/tools/e2e_probes_logic.py      # 规约 / DSL / SMT / oracle / 停滞检测

每个模块导出 `PROBES: list[Probe]`。新增功能时同步新增探针（功能矩阵即清单）。

## 用法

    python scripts/tools/e2e_probe.py --list
    python scripts/tools/e2e_probe.py --all                       # 零 LLM 子集
    AITESTER_E2E_LLM=true python scripts/tools/e2e_probe.py --all --include-llm
    python scripts/tools/e2e_probe.py --group repair --strict
    python scripts/tools/e2e_probe.py --all --json-out /tmp/e2e.json --md-out /tmp/e2e.md

退出码：0 = 无 fail/error（skip 不算失败；`--strict` 时 LLM 探针缺配额也计入失败）；
1 = 存在 fail/error（--strict 下含必跑探针被 skip）；2 = 用法/发现错误。
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# `python scripts/tools/e2e_probe.py` 以 __main__ 运行时，注册同名模块别名，
# 使探针模块 `from scripts.tools.e2e_probe import Probe, ok` 与本进程共享同一
# 类对象（否则 isinstance 会因两个类对象而失败——子进程隔离执行的坑）。
if __name__ == "__main__":  # pragma: no cover - 仅脚本入口
    sys.modules.setdefault("scripts.tools.e2e_probe", sys.modules["__main__"])

DEFAULT_PROBE_MODULES: tuple[str, ...] = (
    "scripts.tools.e2e_probes_workflow",
    "scripts.tools.e2e_probes_platform",
    "scripts.tools.e2e_probes_logic",
)
_REPORT_SCHEMA = "e2e_probe_report/1"


@dataclass
class Probe:
    """一个功能探针。

    Attributes:
        name: 全局唯一名（kebab-case，报告/CLI filter 用）。
        group: 功能组（cli / workflow / agents / repair / localization / safety /
            budget / cache / rag / security / executor / dataset / observability /
            logic / oracle）。
        func: 零参可调用；返回 `ProbeOutcome` 或含 status/detail/evidence 的 dict。
        requires_llm: 是否必须真实 LLM（默认 False；无配额 → skip）。
        timeout_s: 探针级墙钟上限（运行器在**子进程**内执行探针以隔离崩溃/挂死）。
        description: 一句话说明（`--list`/报告展示）。
    """

    name: str
    group: str
    func: Callable[[], Any]
    requires_llm: bool = False
    timeout_s: float = 180.0
    description: str = ""
    module: str = ""  # 探针定义所在模块（子进程隔离执行时用于重新发现）


@dataclass
class ProbeOutcome:
    """探针结果（status ∈ pass/fail/skip/error）。"""

    status: str
    detail: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)


# ─── 探针作者辅助函数（被各 probes_*.py import）─────────────────────────────


def ok(detail: str = "", **evidence: Any) -> ProbeOutcome:
    """探针通过。"""
    return ProbeOutcome("pass", detail, dict(evidence))


def fail(detail: str, **evidence: Any) -> ProbeOutcome:
    """探针失败（断言不成立；detail 必须含实测值）。"""
    return ProbeOutcome("fail", detail, dict(evidence))


def skip(detail: str, **evidence: Any) -> ProbeOutcome:
    """探针跳过（如可选依赖缺失；必须给出原因，不得静默通过）。"""
    return ProbeOutcome("skip", detail, dict(evidence))


def error(detail: str, **evidence: Any) -> ProbeOutcome:
    """探针执行异常（保留 traceback 供诊断）。"""
    return ProbeOutcome("error", detail, dict(evidence))


def llm_enabled() -> bool:
    """真实 LLM 是否可用（配置层至少一个非占位端点）。"""
    try:
        import config

        return bool(getattr(config, "LLM_CONFIGS", None) or getattr(config, "LLM_APIS", None))
    except Exception:  # pragma: no cover - 配置导入失败按不可用处理
        return False


def make_temp_dir(prefix: str = "aitester_e2e_") -> Path:
    """创建探针专用临时目录（探针负责清理；运行器不跟踪）。"""
    return Path(tempfile.mkdtemp(prefix=prefix))


def invoke_workflow(
    target_code: str,
    *,
    module_name: str = "target_mod",
    target_function: str | None = None,
    planner: bool | None = None,
    debugger: bool | None = None,
    allow_regeneration: bool = False,
    max_iterations: int = 2,
    problem_statement: str | None = None,
) -> tuple[dict[str, Any], float]:
    """用真实 workflow 装配跑一次最小任务（供 workflow/agents/repair 类探针复用）。

    Args:
        target_code: 被测代码全文（写入 tmp 文件；执行沙箱据此导入）。
        module_name: 模块名（generated test 的 import 名）。
        target_function: 目标函数（None = 自动推断/全函数）。
        planner / debugger: build_workflow 开关（None = 由 config 默认决定）。
        allow_regeneration: 是否允许检出优先再生成。
        max_iterations: 最大修复迭代。
        problem_statement: 任务描述（注入扫描探针用）。

    Returns:
        (final_state, elapsed_seconds)。target_file 在 tmp 目录（调用方清理）。
    """
    from src.graph.state import create_initial_state
    from src.graph.workflow import build_workflow

    tmpdir = make_temp_dir("aitester_e2e_wf_")
    target_file = tmpdir / f"{module_name}.py"
    target_file.write_text(target_code, encoding="utf-8")
    stamp = int(time.time() * 1000)
    state = create_initial_state(
        f"e2e_{module_name}_{stamp}",
        str(target_file),
        target_code,
        max_iterations,
        module_name=module_name,
        target_function=target_function,
        problem_statement=problem_statement,
    )
    graph = build_workflow(planner=planner, debugger=debugger, allow_regeneration=allow_regeneration)
    started = time.perf_counter()
    final_state = graph.invoke(state)
    elapsed = time.perf_counter() - started
    return dict(final_state or {}), elapsed


def run_cmd(
    cmd: list[str],
    *,
    timeout: float = 120.0,
    env: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> tuple[int, str, str]:
    """跑子进程（真实 CLI/脚本探针用）；返回 (rc, stdout, stderr)，不抛异常。"""
    merged_env = {**os.environ, **(env or {})}
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=merged_env,
            cwd=str(cwd) if cwd else None,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired as exc:  # 超时按 rc=124 返回（POSIX 惯例）

        def _as_text(value: Any) -> str:
            if value is None:
                return ""
            if isinstance(value, bytes):
                return value.decode("utf-8", "replace")
            return str(value)

        return 124, _as_text(exc.stdout), f"TIMEOUT>{timeout}s: {_as_text(exc.stderr)}"


# ─── 运行引擎 ────────────────────────────────────────────────────────────────


def _coerce_probe(candidate: Any) -> Probe | None:
    """把 duck-typed 探针对象/mapping 规范化为 Probe；不可用 → None。

    支持探针模块**零依赖**定义（不 import 本框架）：只要对象带
    name/group/func（可选 requires_llm/timeout_s/description）即可。
    """
    if isinstance(candidate, dict):
        name, group, func = candidate.get("name"), candidate.get("group"), candidate.get("func")
        extra = candidate
    else:
        name = getattr(candidate, "name", None)
        group = getattr(candidate, "group", None)
        func = getattr(candidate, "func", None)
        extra = candidate
    if not (isinstance(name, str) and name and isinstance(group, str) and callable(func)):
        return None

    def _get(key: str, default: Any) -> Any:
        if isinstance(extra, dict):
            return extra.get(key, default)
        return getattr(extra, key, default)

    try:
        timeout_s = float(_get("timeout_s", 180.0))
    except (TypeError, ValueError):
        timeout_s = 180.0
    return Probe(
        name=name,
        group=group,
        func=func,
        requires_llm=bool(_get("requires_llm", False)),
        timeout_s=timeout_s,
        description=str(_get("description", "")),
    )


def discover_probes(modules: list[str] | None = None) -> tuple[list[Probe], list[str]]:
    """导入探针模块并收集 `PROBES`；返回 (probes, 加载错误列表)。"""
    import scripts  # noqa: F401  确保父包可导入

    probes: list[Probe] = []
    errors: list[str] = []
    seen: set[str] = set()
    for mod_name in modules or DEFAULT_PROBE_MODULES:
        try:
            module = importlib.import_module(mod_name)
        except ModuleNotFoundError as exc:
            errors.append(f"{mod_name}: 模块不存在（{exc}）")
            continue
        except Exception as exc:  # pragma: no cover - 导入期异常即探针层缺陷
            errors.append(f"{mod_name}: 导入失败 {type(exc).__name__}: {exc}")
            continue
        for probe in getattr(module, "PROBES", []) or []:
            if not isinstance(probe, Probe):
                coerced = _coerce_probe(probe)
                if coerced is None:
                    errors.append(f"{mod_name}: PROBES 含非 Probe 元素 {probe!r}")
                    continue
                probe = coerced
            if not callable(getattr(probe, "func", None)):
                errors.append(f"{mod_name}: 探针 {probe.name} 的 func 不可调用")
                continue
            if probe.name in seen:
                errors.append(f"{mod_name}: 探针名重复 {probe.name}")
                continue
            seen.add(probe.name)
            probe.module = mod_name if not getattr(probe, "module", "") else probe.module
            probes.append(probe)
    return probes, errors


def _run_probe_isolated(probe: Probe, include_llm: bool) -> ProbeOutcome:
    """在子进程里跑单个探针（崩溃/挂死/污染与主进程隔离）。

    通过 `--run-probe` 自调用实现：父进程收集 JSON 结果。
    """
    cmd = [sys.executable, str(Path(__file__).resolve()), "--run-probe", probe.name]
    module_name = getattr(probe, "module", "") or ""
    if module_name:
        cmd.extend(["--module", module_name])
    if include_llm:
        cmd.append("--include-llm")
    rc, out, err = run_cmd(cmd, timeout=probe.timeout_s + 30.0)
    payload: dict[str, Any] | None = None
    for line in reversed(out.strip().splitlines()):
        if line.startswith("{") and '"status"' in line:
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if payload is None:
        detail = (
            f"子进程 rc={rc} 且无结构化结果；stderr 末行：{err.strip().splitlines()[-1] if err.strip() else '(空)'}"
        )
        return ProbeOutcome("fail" if rc != 124 else "error", detail)
    return ProbeOutcome(
        str(payload.get("status", "error")),
        str(payload.get("detail", "")),
        payload.get("evidence") or {},
    )


def run_probes(
    probes: list[Probe],
    *,
    include_llm: bool,
    strict: bool = False,
    fail_fast: bool = False,
) -> list[dict[str, Any]]:
    """执行探针集合，返回逐探针结果（含耗时）。"""
    rows: list[dict[str, Any]] = []
    for probe in probes:
        if probe.requires_llm and not include_llm:
            rows.append(_row(probe, ProbeOutcome("skip", "未启用 --include-llm（LLM 探针默认不跑）"), 0.0))
            continue
        started = time.perf_counter()
        try:
            outcome = _run_probe_isolated(probe, include_llm)
        except Exception as exc:  # pragma: no cover - 运行器自身异常
            outcome = ProbeOutcome("error", f"运行器异常 {type(exc).__name__}: {exc}")
        duration = time.perf_counter() - started
        rows.append(_row(probe, outcome, duration))
        print(
            f"[{outcome.status.upper():5s}] {probe.group:14s} {probe.name:36s} {duration:6.1f}s  {outcome.detail[:110]}",
            flush=True,
        )
        if fail_fast and outcome.status in ("fail", "error"):
            print("[e2e] --fail-fast：停止后续探针", flush=True)
            break
    return rows


def _row(probe: Probe, outcome: ProbeOutcome, duration: float) -> dict[str, Any]:
    return {
        "name": probe.name,
        "group": probe.group,
        "requires_llm": probe.requires_llm,
        "status": outcome.status,
        "detail": outcome.detail,
        "evidence": outcome.evidence,
        "duration_s": round(duration, 2),
        "description": probe.description,
    }


def render_markdown(rows: list[dict[str, Any]], *, include_llm: bool) -> str:
    """渲染功能矩阵 Markdown 报告。"""
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(row)
    lines = [
        "# AITester 全功能端到端探针报告（N 轮）",
        "",
        f"> 引擎：`scripts/tools/e2e_probe.py`；LLM 探针：{'已启用（真实调用，缓存关闭）' if include_llm else '未启用（零 LLM 子集）'}",
        f"> 汇总：**{counts.get('pass', 0)} pass / {counts.get('fail', 0)} fail / "
        f"{counts.get('error', 0)} error / {counts.get('skip', 0)} skip**（共 {len(rows)} 探针）",
        "",
        "## 功能矩阵",
        "",
        "| 组 | 探针 | 状态 | LLM | 耗时(s) | 说明/证据 |",
        "|---|---|---|---|---|---|",
    ]
    for group in sorted(groups):
        for row in groups[group]:
            detail = (row["detail"] or "").replace("|", "\\|")[:160]
            lines.append(
                f"| {group} | `{row['name']}` | **{row['status']}** | {'是' if row['requires_llm'] else '否'} | "
                f"{row['duration_s']} | {detail} |"
            )
    failed = [r for r in rows if r["status"] in ("fail", "error")]
    lines += ["", "## 失败/异常明细", ""]
    if not failed:
        lines.append("（无）")
    else:
        for row in failed:
            lines += [
                f"### `{row['name']}`（{row['group']}，{row['status']}）",
                "",
                f"{row['detail']}",
                "",
                "```json",
                json.dumps(row.get("evidence") or {}, ensure_ascii=False, indent=2)[:2000],
                "```",
                "",
            ]
    return "\n".join(lines) + "\n"


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AITester 全功能端到端探针（N 轮）")
    parser.add_argument("--list", action="store_true", help="列出全部探针后退出")
    parser.add_argument("--all", action="store_true", help="运行全部探针（默认行为）")
    parser.add_argument("--group", action="append", default=None, help="只跑指定功能组（可多次）")
    parser.add_argument("--name", action="append", default=None, help="只跑指定探针名（可多次）")
    parser.add_argument(
        "--include-llm", action="store_true", help="包含需要真实 LLM 的探针（另需 AITESTER_E2E_LLM=true）"
    )
    parser.add_argument("--strict", action="store_true", help="fail/error 或必需探针 skip → 非零退出")
    parser.add_argument("--fail-fast", action="store_true", help="首个 fail/error 即停止")
    parser.add_argument("--json-out", default=None, help="JSON 报告输出路径")
    parser.add_argument("--md-out", default=None, help="Markdown 报告输出路径")
    parser.add_argument("--module", action="append", default=None, help="只加载指定探针模块（测试用）")
    parser.add_argument("--run-probe", default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    # 子进程模式：只跑单个探针并把结构化结果打到 stdout（运行器解析末行 JSON）
    if args.run_probe:
        probes, _ = discover_probes(args.module)
        match = next((p for p in probes if p.name == args.run_probe), None)
        if match is None:
            print(json.dumps({"status": "error", "detail": f"探针未找到: {args.run_probe}"}, ensure_ascii=False))
            return 2
        if match.requires_llm and not (args.include_llm and os.getenv("AITESTER_E2E_LLM", "").lower() == "true"):
            print(json.dumps({"status": "skip", "detail": "LLM 未启用"}, ensure_ascii=False))
            return 0
        try:
            raw = match.func()
            if isinstance(raw, ProbeOutcome):
                outcome = raw
            elif isinstance(raw, dict) and "status" in raw:
                outcome = ProbeOutcome(str(raw["status"]), str(raw.get("detail", "")), dict(raw.get("evidence") or {}))
            else:
                outcome = ProbeOutcome("error", f"探针返回类型非法: {type(raw).__name__}")
        except Exception as exc:
            outcome = ProbeOutcome(
                "error",
                f"{type(exc).__name__}: {exc}",
                {"traceback_tail": traceback.format_exc().splitlines()[-3:]},
            )
        print(
            json.dumps(
                {"status": outcome.status, "detail": outcome.detail, "evidence": outcome.evidence}, ensure_ascii=False
            )
        )
        return 0

    if not (args.all or args.group or args.name or args.list):
        parser.print_help()
        return 2

    probes, load_errors = discover_probes(args.module)
    for item in load_errors:
        print(f"[e2e] ⚠️ 探针模块加载问题：{item}", file=sys.stderr)
    if args.group:
        probes = [p for p in probes if p.group in set(args.group)]
    if args.name:
        probes = [p for p in probes if p.name in set(args.name)]
    if not probes:
        print("[e2e] 没有匹配的探针（检查 --group/--name/模块加载）", file=sys.stderr)
        return 2
    if args.list:
        for probe in probes:
            llm = "LLM" if probe.requires_llm else "零LLM"
            print(f"{probe.group:14s} {probe.name:36s} {llm:5s} {probe.timeout_s:5.0f}s  {probe.description}")
        return 0

    include_llm = bool(args.include_llm and os.getenv("AITESTER_E2E_LLM", "").lower() == "true")
    if args.include_llm and not include_llm:
        print("[e2e] ⚠️ 已给 --include-llm 但 AITESTER_E2E_LLM != true：LLM 探针将 skip（防误烧配额）", file=sys.stderr)

    # 探针进程统一关闭 LLM 缓存（避免把缓存重放当成真实功能验证），并隔离 cache namespace。
    # N 轮（2026-10-17）：**保存/恢复**这两个 env——本函数也会被 tests 在同进程内调用，
    # 不恢复会把 AITESTER_LLM_CACHE=0 / 探针 namespace 泄漏给后续测试文件（导致
    # test_closeout_k_base_agent 的缓存命中断言在全量套件里静默失败）。
    _env_saved = {key: os.environ.get(key) for key in ("AITESTER_LLM_CACHE", "AITESTER_CACHE_NAMESPACE")}
    os.environ.setdefault("AITESTER_LLM_CACHE", "0")
    os.environ.setdefault("AITESTER_CACHE_NAMESPACE", f"e2e_probe_{int(time.time())}")

    print(f"[e2e] 运行 {len(probes)} 个探针（LLM={'on' if include_llm else 'off'}）…", flush=True)
    try:
        rows = run_probes(probes, include_llm=include_llm, strict=args.strict, fail_fast=args.fail_fast)
    finally:
        for _key, _old in _env_saved.items():
            if _old is None:
                os.environ.pop(_key, None)
            else:
                os.environ[_key] = _old
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(
        f"[e2e] 汇总：pass={counts.get('pass', 0)} fail={counts.get('fail', 0)} "
        f"error={counts.get('error', 0)} skip={counts.get('skip', 0)}（共 {len(rows)}）"
    )
    report = {
        "schema": _REPORT_SCHEMA,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "include_llm": include_llm,
        "probes": rows,
        "summary": counts,
        "load_errors": load_errors,
    }
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
        print(f"[e2e] JSON 报告：{args.json_out}")
    if args.md_out:
        Path(args.md_out).write_text(render_markdown(rows, include_llm=include_llm), encoding="utf-8")
        print(f"[e2e] Markdown 报告：{args.md_out}")
    failed = counts.get("fail", 0) + counts.get("error", 0)
    if failed:
        return 1
    if args.strict and counts.get("skip", 0):
        print("[e2e] --strict：存在 skip 探针 → 非零退出")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
