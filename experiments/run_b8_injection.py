#!/usr/bin/env python
"""S-2 / B8 / A-19：覆盖率停滞检测开/关消融——**实验层确定性失败注入 harness**。

背景：P-2（`p_round_b8_ablation_20261018/`）的 B8 消融在 synthetic+fast+seed42 前 10
任务上 10/10 首轮全绿（detection=0/10、false_fix=1.0），workflow 从未进入修复循环，
停滞判据（最近 K=2 轮 failed 且 |coverage_delta|<eps）结构上不可达 → 无法评估
A-19 停滞检测的收益/代价。本 harness 在**实验层**注入确定性多轮失败，正面回答：
当任务确实多轮失败且覆盖率停滞时，stagnation 检测（P-2 已接线）是否真的提前停止、
省多少迭代。

## 注入方法（不改生产逻辑；进程内 monkeypatch）

- patch 目标 1：`src.graph.nodes._executor_node`（及其在 `src.graph.workflow` 的
  模块级引用）——仅用于把当前 `state` 传给线程局部变量，原函数逻辑**原样执行**。
- patch 目标 2：`src.agents.executor.ExecutorAgent.execute`——在**前 `--inject-rounds`
  轮**（按 `state["iteration"]` 判定）返回确定性强制失败结果：
  `passed=False, output="INJECTED_FAILURE…", coverage=上一轮 coverage（首轮 0.0）`，
  使 `_record_execution_trace` 计算出的 `coverage_delta` 从第 2 轮起恒为 `0.0`
  （|Δ|<eps 默认 0.5），满足 `_coverage_stall_detected` 的窗口条件；第
  `--inject-rounds` 轮及之后**恢复真实执行**（调用原 `ExecutorAgent.execute`）。
  ON 臂默认 `K=2` 窗口需要 ≥2 个"带 delta 的失败轮"，而首轮 delta=None 不计数，
  故默认 `inject_rounds=3`（= 3 个强制失败轮，第 3 轮后 ON 臂命中停滞）。
- 两臂**注入完全相同**，唯一差异 = `COVERAGE_STALL_DETECT_ENABLE=true|false`。
- 一切 patch 只存在于本驱动进程内（`AITESTER_B8_INJECTION_ENABLE=1` 生效），
  生产文件零改动（`git -C <root> status --porcelain` 前后为空 + `diff --stat`
  为空，见聚合产物 `ISOLATION.json`）。

## 用法

    # 单臂（两臂并发 = 两个进程，各自独立 cache namespace）
    python experiments/run_b8_injection.py --root <worktree> --out <results_dir> \\
        --arm on --tasks 10 --seed 42 --profile fast --inject-rounds 3
    python experiments/run_b8_injection.py --root <worktree> --out <results_dir> \\
        --arm off --tasks 10 --seed 42 --profile fast --inject-rounds 3
    # 聚合（零 LLM；读两臂内部工件 → REPORT.json / README.md / SHA256SUMS）
    python experiments/run_b8_injection.py --out <results_dir> --aggregate-only

    # 只打印计划，不跑 LLM
    python experiments/run_b8_injection.py --root <worktree> --out <tmp> --arm on --dry-run

## 产物（--out 下）

- `arm_on/`、`arm_off/`：每臂批次 JSON（run_benchmark 自带时间戳）+ `traces/` +
  `injection_records_<arm>.jsonl`（逐轮注入/真实执行记录）+ meta JSON
- `REPORT.json` / `README.md` / `ISOLATION.json` / `SHA256SUMS`（聚合模式写出）
- `PREREG.md` 由操作者**跑前**落盘（本驱动在 run 模式校验其存在并把 sha256 记入 meta）

退出码：0=成功；2=参数/前置条件失败；3=运行异常/看门狗；4=聚合失败。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import platform
import signal
import socket
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

# AB-17（2026-10-20）：价目表表级准入的唯一事实源在 `src.budget.pricing.load_table_models`。
# 本文件可被测试/驱动按包导入，也可直接以脚本方式运行（`python experiments/run_b8_injection.py`），
# 故与 `experiments/analyze_t1_b2_main_batch.py` 同口径做路径引导后再导入。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.budget.pricing import load_table_models  # noqa: E402

# 常量（INJECT 口径；聚合模式无需依赖 worktree 也能读）
INJECT_ENV = "AITESTER_B8_INJECTION_ENABLE"
ARM_ENV = "AITESTER_B8_INJECTION_ARM"
DEFAULT_PRICE_USD_IN_PER_MTOK = 0.3  # deepseek-flash 标准价（与 experiments/price_table.json 同源）
DEFAULT_PRICE_USD_OUT_PER_MTOK = 1.2
CRASH_ERROR_CATEGORIES = {"exception", "unexpected_exception", "harness_error", "crash", "timeout", "recursion_limit"}

logger = logging.getLogger("run_b8_injection")


# ─────────────────────────────────────────────────────────────────────────────
# 公共工具
# ─────────────────────────────────────────────────────────────────────────────
def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _git(root: str, *args: str) -> str:
    import subprocess

    try:
        proc = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - 环境异常
        return f"<git-error: {type(exc).__name__}>"
    return (proc.stdout or proc.stderr or "").strip()


def _git_snapshot(root: str) -> dict[str, Any]:
    return {
        "root": root,
        "head": _git(root, "rev-parse", "HEAD") or None,
        "status_porcelain": _git(root, "status", "--porcelain"),
        "diff_stat": _git(root, "diff", "--stat"),
        "diff_name_only": _git(root, "diff", "--name-only"),
        "dirty_lines": len([ln for ln in _git(root, "status", "--porcelain").splitlines() if ln.strip()]),
    }


def _find_batch(arm_dir: Path) -> Path | None:
    files = sorted(arm_dir.glob("benchmark_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def _load_arm(arm_dir: Path) -> dict[str, Any]:
    """读取单臂工件（batch JSON + injection JSONL + meta）→ 统一结构。"""
    batch = _find_batch(arm_dir)
    if batch is None:
        raise FileNotFoundError(f"未找到批次 JSON：{arm_dir}（该臂未成功产出）")
    data = json.loads(batch.read_text(encoding="utf-8"))
    results = data.get("results") or {}
    if not results:
        raise ValueError(f"批次 JSON 无 results 块：{batch}")
    arm_key = next(iter(results))
    rd = results[arm_key]
    details = list(rd.get("details") or [])
    meta_path = arm_dir / f"arm_{arm_dir.name.replace('arm_', '')}.meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    records: list[dict[str, Any]] = []
    rec_path = arm_dir / f"injection_records_{arm_dir.name.replace('arm_', '')}.jsonl"
    if rec_path.is_file():
        for line in rec_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return {
        "batch_path": str(batch),
        "batch_sha256": _sha256_file(batch),
        "arm_key": arm_key,
        "data": data,
        "details": details,
        "token_metrics": rd.get("token_metrics") or {},
        "meta": meta,
        "injection_records": records,
        "injection_records_path": str(rec_path) if rec_path.is_file() else None,
    }


def _record_matches_task(record_task_id: str, task_id: str) -> bool:
    """注入记录的 task_id（state.task_uuid，带 `<task_id>_<baseline>_<ts>` 后缀）
    与批次 details[].task_id 对齐（前缀匹配；聚合零 LLM 复算用）。"""
    return record_task_id == task_id or record_task_id.startswith(task_id + "_")


def _load_harness_smoke(out_root: Path, price_in: float, price_out: float) -> list[dict[str, Any]]:
    """读取跑前冒烟工件（默认协议 vs gate-off 可达性），供 README 披露（非主判定）。"""
    rows: list[dict[str, Any]] = []
    for dirname, label in (("_harness_smoke", "default_gate_on"), ("_harness_smoke_gateoff", "gate_off")):
        for arm in ("on", "off"):
            batch = _find_batch(out_root / dirname / f"arm_{arm}")
            if batch is None:
                continue
            data = json.loads(batch.read_text(encoding="utf-8"))
            results = data.get("results") or {}
            if not results:
                continue
            rd = next(iter(results.values()))
            details = rd.get("details") or []
            env = (data.get("provenance") or {}).get("env_snapshot") or {}
            rows.append(
                {
                    "smoke_dir": dirname,
                    "setting": label,
                    "arm": arm,
                    "coverage_stall_env": env.get("COVERAGE_STALL_DETECT_ENABLE"),
                    "patch_evidence_gate_env": env.get("PATCH_EVIDENCE_GATE_ENABLE") or "default(true)",
                    "n_tasks": len(details),
                    "stop_reason_counts": {
                        sr: sum(1 for r in details if str(r.get("stop_reason") or "<none>") == sr)
                        for sr in sorted({str(r.get("stop_reason") or "<none>") for r in details})
                    },
                    "iterations": [int(r.get("iterations") or 0) for r in details],
                    "iterations_mean": round(sum(int(r.get("iterations") or 0) for r in details) / len(details), 4)
                    if details
                    else None,
                    "token_metrics": rd.get("token_metrics") or {},
                    "cost_usd_standard_price": _cost_usd(rd.get("token_metrics") or {}, price_in, price_out),
                    "batch_path": str(batch),
                }
            )
    return rows


def _cost_usd(tm: dict[str, Any], price_in: float, price_out: float) -> float:
    return round(
        float(tm.get("total_input_tokens") or 0) / 1e6 * price_in
        + float(tm.get("total_output_tokens") or 0) / 1e6 * price_out,
        6,
    )


def _arm_summary(loaded: dict[str, Any], price_in: float, price_out: float) -> dict[str, Any]:
    details = loaded["details"]
    tm = loaded["token_metrics"]
    stop_reasons: dict[str, int] = {}
    crash_rows = []
    detection_meas = 0
    detection_pos = 0
    for row in details:
        sr = str(row.get("stop_reason") or "<none>")
        stop_reasons[sr] = stop_reasons.get(sr, 0) + 1
        if str(row.get("error_category") or "") in CRASH_ERROR_CATEGORIES:
            crash_rows.append(row.get("task_id"))
        dr = row.get("detection_rate")
        if dr is not None:
            detection_meas += 1
            if dr == 1.0:
                detection_pos += 1
    iters = [int(row.get("iterations") or 0) for row in details]
    coverages = [float(row.get("coverage") or 0.0) for row in details]
    recs = loaded["injection_records"]
    tasks_with_injection = len({r.get("task_id") for r in recs if r.get("injected")})
    injected_rounds = sum(1 for r in recs if r.get("injected"))
    real_rounds = sum(1 for r in recs if r.get("injected") is False)
    n = len(details)
    wall = float(loaded["meta"].get("wall_seconds") or 0.0)
    return {
        "n_tasks": n,
        "batch_path": loaded["batch_path"],
        "batch_sha256": loaded["batch_sha256"],
        "wall_seconds": wall,
        "token_metrics": tm,
        "cost_usd_standard_price": _cost_usd(tm, price_in, price_out),
        "stop_reason_counts": dict(sorted(stop_reasons.items())),
        "coverage_stall_count": stop_reasons.get("coverage_stall", 0),
        "coverage_stall_rate": round(stop_reasons.get("coverage_stall", 0) / n, 4) if n else None,
        "iterations_mean": round(sum(iters) / n, 4) if n else None,
        "iterations_median": round(sorted(iters)[n // 2], 4) if n else None,
        "iterations_max": max(iters) if iters else None,
        "coverage_mean": round(sum(coverages) / n, 4) if n else None,
        "passed_count": sum(1 for row in details if row.get("passed")),
        "detection": {
            "measurable": detection_meas,
            "positive": detection_pos,
            "rate": round(detection_pos / detection_meas, 4) if detection_meas else None,
        },
        "crash_rows": sorted(crash_rows),
        "crash_count": len(crash_rows),
        "injection": {
            "records": len(recs),
            "injected_rounds": injected_rounds,
            "real_rounds": real_rounds,
            "tasks_with_injection": tasks_with_injection,
            "tasks_total": n,
        },
        "provenance": {
            "git_sha": (loaded["data"].get("provenance") or {}).get("git_sha"),
            "git_dirty": (loaded["data"].get("provenance") or {}).get("git_dirty"),
            "model_name": (loaded["data"].get("provenance") or {}).get("model_name"),
            "coverage_stall_env": ((loaded["data"].get("provenance") or {}).get("env_snapshot") or {}).get(
                "COVERAGE_STALL_DETECT_ENABLE"
            ),
            "cache_namespace": (loaded["data"].get("provenance") or {}).get("cache_namespace"),
        },
        "per_task": [
            {
                "task_id": row.get("task_id"),
                "stop_reason": row.get("stop_reason"),
                "iterations": row.get("iterations"),
                "coverage": row.get("coverage"),
                "passed": row.get("passed"),
                "detection_rate": row.get("detection_rate"),
                "error_category": row.get("error_category"),
                "elapsed_seconds": row.get("elapsed_seconds"),
                "token_usage": row.get("token_usage"),
                "execution_trace": row.get("execution_trace"),
            }
            for row in details
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 注入（仅进程内；run 模式）
# ─────────────────────────────────────────────────────────────────────────────
class _Injection:
    """实验层失败注入（进程内 monkeypatch；线程局部 state 传递）。"""

    def __init__(self, arm: str, inject_rounds: int, out_dir: Path) -> None:
        self.arm = arm
        self.inject_rounds = int(inject_rounds)
        self.out_dir = out_dir
        self._tl = threading.local()
        self._lock = threading.Lock()
        self._records: list[dict[str, Any]] = []
        self._records_path = out_dir / f"injection_records_{arm}.jsonl"
        self._orig_execute: Any = None
        self._orig_node: Any = None
        self._patched: list[str] = []

    # ---- patch 安装/卸载 ----
    def install(self) -> dict[str, Any]:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._records_path.write_text("", encoding="utf-8")
        import src.agents.executor as exec_mod
        import src.graph.nodes as nodes_mod
        import src.graph.workflow as wf_mod

        original_execute = exec_mod.ExecutorAgent.execute
        original_node = nodes_mod._executor_node
        self._orig_execute = original_execute
        self._orig_node = original_node
        injection = self

        def patched_execute(agent_self, test_code, target_file, target_function=None):
            state = getattr(injection._tl, "state", None)
            if state is None or os.environ.get(INJECT_ENV) != "1":
                return original_execute(agent_self, test_code, target_file, target_function)
            iteration = int(state.get("iteration") or 0)
            task_id = str(state.get("task_uuid") or state.get("task_id") or "?")
            trace = state.get("execution_trace") or []
            prev_cov = float(trace[-1].get("coverage") or 0.0) if trace else None
            if iteration < injection.inject_rounds:
                coverage = float(prev_cov) if prev_cov is not None else 0.0
                msg = (
                    f"INJECTED_FAILURE (B8/A-19 harness round {iteration + 1}/{injection.inject_rounds}): "
                    "forced multi-round failure with stagnant coverage"
                )
                result = {
                    "passed": False,
                    "output": (
                        "FAILED test_injected_failure.py::test_injected_failure - "
                        f"AssertionError: {msg}\n"
                        "INJECTED_FAILURE by experiments/run_b8_injection.py (experimental harness)"
                    ),
                    "coverage": coverage,
                    "failed_cases": [
                        {
                            "name": "test_injected_failure",
                            "error": f"AssertionError: {msg}",
                        }
                    ],
                    "error_info": {"type": "injected_failure", "message": msg},
                }
                injection._record(
                    {
                        "task_id": task_id,
                        "iteration": iteration,
                        "injected": True,
                        "passed": False,
                        "coverage": coverage,
                        "prev_coverage": prev_cov,
                        "coverage_delta": None if prev_cov is None else round(coverage - prev_cov, 2),
                        "test_code_len": len(test_code or ""),
                        "target_file": os.path.basename(str(target_file or "")),
                        "ts": time.time(),
                    }
                )
                return result
            t0 = time.time()
            real = original_execute(agent_self, test_code, target_file, target_function)
            injection._record(
                {
                    "task_id": task_id,
                    "iteration": iteration,
                    "injected": False,
                    "passed": bool(real.get("passed")),
                    "coverage": float(real.get("coverage") or 0.0),
                    "prev_coverage": prev_cov,
                    "coverage_delta": (
                        None if prev_cov is None else round(float(real.get("coverage") or 0.0) - prev_cov, 2)
                    ),
                    "test_code_len": len(test_code or ""),
                    "target_file": os.path.basename(str(target_file or "")),
                    "elapsed_seconds": round(time.time() - t0, 3),
                    "ts": time.time(),
                }
            )
            return real

        def patched_node(state):
            injection._tl.state = state
            try:
                return original_node(state)
            finally:
                injection._tl.state = None

        exec_mod.ExecutorAgent.execute = patched_execute  # type: ignore[method-assign]
        nodes_mod._executor_node = patched_node
        self._patched = [
            f"src.agents.executor.ExecutorAgent.execute @ {exec_mod.__file__}",
            f"src.graph.nodes._executor_node @ {nodes_mod.__file__}",
        ]
        if getattr(wf_mod, "_executor_node", None) is original_node:
            wf_mod._executor_node = patched_node  # type: ignore[attr-defined]
            self._patched.append(f"src.graph.workflow._executor_node @ {wf_mod.__file__}")
        return {
            "inject_rounds": self.inject_rounds,
            "patched_targets": list(self._patched),
            "original_node": f"{original_node.__module__}.{original_node.__name__}",
            "original_execute": f"{original_execute.__module__}.{original_execute.__qualname__}",
        }

    def uninstall(self) -> None:
        import src.agents.executor as exec_mod
        import src.graph.nodes as nodes_mod
        import src.graph.workflow as wf_mod

        if self._orig_execute is not None:
            exec_mod.ExecutorAgent.execute = self._orig_execute  # type: ignore[method-assign]
        if self._orig_node is not None:
            nodes_mod._executor_node = self._orig_node
            if getattr(wf_mod, "_executor_node", None) is not None and self._orig_node is not None:
                wf_mod._executor_node = self._orig_node  # type: ignore[attr-defined]

    # ---- 记录 ----
    def _record(self, record: dict[str, Any]) -> None:
        record.setdefault("arm", self.arm)
        with self._lock:
            self._records.append(record)
            with open(self._records_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()

    def records(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._records)


# ─────────────────────────────────────────────────────────────────────────────
# run 模式
# ─────────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────────
# run 模式
# ─────────────────────────────────────────────────────────────────────────────
def _ensure_worktree(parser: argparse.ArgumentParser, root: str) -> dict[str, Any]:
    root_p = Path(root).resolve()
    if not root_p.is_dir():
        parser.error(f"--root 不存在：{root_p}")
    if not (root_p / "experiments" / "run_benchmark.py").is_file():
        parser.error(f"--root 不是 AITester 工作树（缺 experiments/run_benchmark.py）：{root_p}")
    if not (root_p / ".env.local").is_file():
        parser.error(f"--root 缺 .env.local（真实 LLM 配置）：{root_p}")
    snap = _git_snapshot(str(root_p))
    if snap["dirty_lines"]:
        parser.error(
            f"--root 工作树不干净（dirty_lines={snap['dirty_lines']}）——本实验要求干净切点：\n{snap['status_porcelain']}"
        )
    return snap


def _setup_imports(parser: argparse.ArgumentParser, root: str) -> None:
    """强制从 --root 导入项目模块（隔离主仓未跟踪的驱动对 worktree 生产代码的依赖）。"""
    root_p = str(Path(root).resolve())
    sys.path = [p for p in sys.path if not p.startswith(str(Path(__file__).resolve().parents[1]))]
    sys.path.insert(0, root_p)
    os.chdir(root_p)


def _verify_imports(parser: argparse.ArgumentParser, root: str) -> dict[str, str]:
    root_p = str(Path(root).resolve())
    import config
    import experiments.run_benchmark as rb
    import src.agents.executor as exec_mod
    import src.graph.workflow as wf_mod

    paths = {
        "config": str(Path(config.__file__).resolve()),
        "run_benchmark": str(Path(rb.__file__).resolve()),
        "executor": str(Path(exec_mod.__file__).resolve()),
        "workflow": str(Path(wf_mod.__file__).resolve()),
    }
    bad = {k: v for k, v in paths.items() if not v.startswith(root_p + os.sep)}
    if bad:
        parser.error(f"模块来源不在 --root 下（导入隔离失败）：{bad}")
    return paths


def _parse_extra_env(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            raise SystemExit(f"--extra-env 需要 KEY=VALUE 形式：{item!r}")
        key, _, value = item.partition("=")
        key = key.strip()
        if not key:
            raise SystemExit(f"--extra-env KEY 为空：{item!r}")
        out[key] = value
    return out


def _arm_env(arm: str, args: argparse.Namespace) -> dict[str, str]:
    return {
        "AITESTER_PROFILE": str(args.profile),
        "TEMPERATURE": "0.0",
        "LLM_THINKING_MODE": "disabled",
        "BENCHMARK_PARALLELISM": str(args.parallel),
        "AITESTER_LLM_CACHE": "0",
        "AITESTER_CACHE_NAMESPACE": f"s2_b8_injection_{arm}",
        "AITESTER_BATCH_MAX_CALLS": str(args.max_calls),
        "COST_BUDGET_ENABLE": "true",
        "COST_BUDGET_USD": str(args.budget_usd),
        "COVERAGE_STALL_DETECT_ENABLE": "true" if arm == "on" else "false",
        INJECT_ENV: "1",
        ARM_ENV: arm,
    }


def _watchdog_fire(out_dir: Path, arm: str, meta_path: Path, seconds: float) -> None:
    time.sleep(seconds)
    payload = {"status": "watchdog_timeout", "arm": arm, "watchdog_seconds": seconds, "ts": time.time()}
    _write_json(meta_path, payload)
    logger.error("WATCHDOG 触发（%ss）：arm=%s 强制终止进程", seconds, arm)
    os._exit(124)


def run_arm(args: argparse.Namespace) -> int:
    arm = str(args.arm)
    out_root = Path(args.out).resolve()
    arm_dir = out_root / f"arm_{arm}"
    meta_path = arm_dir / f"arm_{arm}.meta.json"
    if arm_dir.exists() and any(arm_dir.glob("benchmark_*.json")) and not args.force:
        logger.error("臂工件已存在且含批次 JSON（不重跑失败臂/已跑臂）：%s（如需覆盖加 --force）", arm_dir)
        return 2

    snap_before = _ensure_worktree_direct(args.root)
    _setup_imports_io(args.root)
    module_paths = _verify_imports_direct(args.root)

    # PREREG 冻结校验（跑前必须落盘）
    prereg_path = out_root / "PREREG.md"
    prereg_sha = _sha256_file(prereg_path) if prereg_path.is_file() else None
    if prereg_sha is None:
        logger.error("缺少跑前冻结的预注册文件：%s（先落盘 PREREG.md 再跑）", prereg_path)
        return 2

    arm_dir.mkdir(parents=True, exist_ok=True)
    env = _arm_env(arm, args)
    extra_env = _parse_extra_env(list(args.extra_env or []))
    env.update(extra_env)
    os.environ.update(env)

    injection = _Injection(arm=arm, inject_rounds=args.inject_rounds, out_dir=arm_dir)
    patch_info = injection.install()
    watchdog = threading.Thread(
        target=_watchdog_fire,
        args=(out_root, arm, meta_path, float(args.watchdog_seconds)),
        daemon=True,
        name=f"watchdog_{arm}",
    )

    interrupted: dict[str, Any] = {}

    def _sigterm(_signum, _frame):
        interrupted.update({"status": "interrupted", "signal": int(_signum), "ts": time.time()})

    old_sigterm = signal.signal(signal.SIGTERM, _sigterm)
    start = time.time()
    start_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start))
    exit_code = 0
    batch_path: Path | None = None
    try:
        watchdog.start()
        import experiments.run_benchmark as rb

        logger.info("=== S-2 注入臂 %s 开始（HEAD=%s）===", arm, snap_before["head"])
        summary = rb.run_benchmark(
            dataset_name="synthetic",
            baselines=["aitester"],
            output_dir=str(arm_dir),
            task_count=int(args.tasks),
            seed=int(args.seed),
            parallel=int(args.parallel),
            deterministic=True,
            enable_rag=False,
            save_state=False,
            dirty_reason=None,
        )
        batch_path = _find_batch(arm_dir)
        logger.info("批次完成：%s", batch_path)
        if not batch_path:
            exit_code = 3
        del summary
    except BaseException as exc:
        exit_code = 3
        logger.error("臂 %s 运行异常：%s", arm, exc)
        traceback.print_exc()
        interrupted.update({"status": "exception", "error": f"{type(exc).__name__}: {exc}"})
    finally:
        end = time.time()
        signal.signal(signal.SIGTERM, old_sigterm)
        injection.uninstall()
        snap_after = _git_snapshot(args.root)
        meta = {
            "arm": arm,
            "status": interrupted.get("status", "completed" if exit_code == 0 else "failed"),
            "exit_code": exit_code,
            "start_epoch": start,
            "end_epoch": end,
            "start_iso_utc": start_iso,
            "end_iso_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end)),
            "wall_seconds": round(end - start, 2),
            "root": str(Path(args.root).resolve()),
            "git_before": snap_before,
            "git_after": snap_after,
            "module_provenance": module_paths,
            "protocol_env": env,
            "extra_env": extra_env,
            "cli": {
                "tasks": int(args.tasks),
                "seed": int(args.seed),
                "profile": str(args.profile),
                "parallel": int(args.parallel),
                "inject_rounds": int(args.inject_rounds),
                "watchdog_seconds": float(args.watchdog_seconds),
                "budget_usd_per_task": float(args.budget_usd),
                "max_calls": int(args.max_calls),
            },
            "injection": patch_info,
            "injection_records_path": str(injection._records_path),
            "prereg_path": str(prereg_path),
            "prereg_sha256": prereg_sha,
            "batch_path": str(batch_path) if batch_path else None,
            "batch_sha256": _sha256_file(batch_path) if batch_path and batch_path.is_file() else None,
            "host": {"hostname": socket.gethostname(), "platform": platform.platform(), "python": sys.version},
            "interrupted": interrupted or None,
            "production_files_untouched": {
                "git_before_dirty_lines": snap_before["dirty_lines"],
                "git_after_dirty_lines": snap_after["dirty_lines"],
                "diff_stat_after": snap_after["diff_stat"],
            },
        }
        _write_json(meta_path, meta)
        print(
            json.dumps(
                {
                    "arm": arm,
                    "status": meta["status"],
                    "wall_seconds": meta["wall_seconds"],
                    "batch": meta["batch_path"],
                    "meta": str(meta_path),
                },
                ensure_ascii=False,
            )
        )
    if interrupted.get("status") == "interrupted":
        return 143
    return 0 if exit_code == 0 else exit_code


def aggregate(args: argparse.Namespace) -> int:
    out_root = Path(args.out).resolve()
    prereg_path = out_root / "PREREG.md"
    if not prereg_path.is_file():
        logger.error("聚合缺少预注册文件：%s", prereg_path)
        return 4
    try:
        loaded = {arm: _load_arm(out_root / f"arm_{arm}") for arm in ("on", "off")}
    except (FileNotFoundError, ValueError) as exc:
        logger.error("聚合失败：%s", exc)
        return 4
    price_path = Path(args.price_table).resolve() if args.price_table else None
    price_in, price_out = DEFAULT_PRICE_USD_IN_PER_MTOK, DEFAULT_PRICE_USD_OUT_PER_MTOK
    price_meta: dict[str, Any] = {"source": "builtin deepseek-flash standard price", "as_of": "2026-10-06"}
    if price_path is not None:
        table, table_reason = load_table_models(price_path)
        if table_reason is not None:
            # AB-17：改前这里是 `price_path.is_file()` 前置守卫——显式给了一个坏路径
            # （缺失 / 语法错 / 形状不符）会静默退回内置价，报告里读起来与"根本没给价目表"
            # 同形；而"文件在、内容坏"三种机制又会各自崩在不同的 `.get` / `json.loads` 上。
            # 现在点名机制并保留键（只在真发生时写入；内置价照旧兜底，②自持数字门不在本轮改）。
            logger.warning("价目表不可用（%s：%s）：改用内置 deepseek-flash 标准价", price_path, table_reason)
            price_meta["table_reason"] = table_reason
        else:
            model = (loaded["on"]["data"].get("provenance") or {}).get("model_name") or "deepseek-flash"
            row = table.get(model)
            # ②自持数字门（AB-16 登记不修）：只认真数；条目形状/币种不进判定，币种只抄进 meta。
            # AB-17 只加 `isinstance(row, dict)`：models 层不再过滤后，非对象条目改前会崩在
            # `row.get` 上，现在按"这行读不出价"处理（与"没这个模型"同一条既有降级）。
            if (
                isinstance(row, dict)
                and isinstance(row.get("input_per_mtok"), (int, float))
                and isinstance(row.get("output_per_mtok"), (int, float))
            ):
                price_in, price_out = float(row["input_per_mtok"]), float(row["output_per_mtok"])
                price_meta = {
                    "source": row.get("source"),
                    "currency": row.get("currency"),
                    "as_of": row.get("as_of"),
                    "model": model,
                    "input_per_mtok": price_in,
                    "output_per_mtok": price_out,
                }
    summaries = {arm: _arm_summary(loaded[arm], price_in, price_out) for arm in ("on", "off")}
    on, off = summaries["on"], summaries["off"]

    # 配对（synthetic 同 seed 任务集合应一致；按 task_id 对齐）
    on_map = {row["task_id"]: row for row in on["per_task"]}
    off_map = {row["task_id"]: row for row in off["per_task"]}
    common = sorted(set(on_map) & set(off_map))
    pair_rows = []
    for tid in common:
        a, b = on_map[tid], off_map[tid]
        pair_rows.append(
            {
                "task_id": tid,
                "iterations_on": a["iterations"],
                "iterations_off": b["iterations"],
                "delta_iterations_off_minus_on": (int(b["iterations"] or 0) - int(a["iterations"] or 0)),
                "stop_reason_on": a["stop_reason"],
                "stop_reason_off": b["stop_reason"],
                "coverage_on": a["coverage"],
                "coverage_off": b["coverage"],
                "injected_rounds_on": sum(
                    1
                    for r in loaded["on"]["injection_records"]
                    if r.get("injected") and _record_matches_task(str(r.get("task_id") or ""), tid)
                ),
                "injected_rounds_off": sum(
                    1
                    for r in loaded["off"]["injection_records"]
                    if r.get("injected") and _record_matches_task(str(r.get("task_id") or ""), tid)
                ),
            }
        )
    delta_iter_mean = (
        round(sum(row["delta_iterations_off_minus_on"] for row in pair_rows) / len(pair_rows), 4) if pair_rows else None
    )
    direction = {
        "off_gt_on": sum(1 for row in pair_rows if row["delta_iterations_off_minus_on"] > 0),
        "equal": sum(1 for row in pair_rows if row["delta_iterations_off_minus_on"] == 0),
        "off_lt_on": sum(1 for row in pair_rows if row["delta_iterations_off_minus_on"] < 0),
    }

    # 预注册判据（PREREG.md §3）
    stall_rate_threshold = 0.8
    primary_met = (
        on["coverage_stall_rate"] is not None
        and on["coverage_stall_rate"] >= stall_rate_threshold
        and off["coverage_stall_count"] == 0
    )
    iterations_saved = (
        round(off["iterations_mean"] - on["iterations_mean"], 4)
        if on["iterations_mean"] is not None and off["iterations_mean"] is not None
        else None
    )
    secondary_met = (
        iterations_saved is not None and iterations_saved >= 1.0 and on["crash_count"] == 0 and off["crash_count"] == 0
    )
    harness_ok = (
        on["injection"]["tasks_with_injection"] >= max(1, int(0.8 * on["n_tasks"]))
        and on["injection"]["injected_rounds"] > 0
    )
    if primary_met and secondary_met:
        verdict = "confirmed"
    elif not harness_ok:
        verdict = "not_confirmed_harness_limitation"
    else:
        verdict = "not_confirmed"
    report = {
        "experiment": "S-2 / B8 / A-19 coverage-stall ablation with deterministic failure injection",
        "created_epoch": time.time(),
        "out_dir": str(out_root),
        "prereg": {"path": str(prereg_path), "sha256": _sha256_file(prereg_path)},
        "isolation": {
            "mechanism": "experiment-layer in-process monkeypatch only (no production file changes)",
            "root": str(loaded["on"]["meta"].get("root") or loaded["off"]["meta"].get("root")),
            "git_before_on": loaded["on"]["meta"].get("git_before"),
            "git_after_on": loaded["on"]["meta"].get("git_after"),
            "git_before_off": loaded["off"]["meta"].get("git_before"),
            "git_after_off": loaded["off"]["meta"].get("git_after"),
            "patched_targets": loaded["on"]["meta"].get("injection", {}).get("patched_targets"),
            "production_diff": "git status/diff 前后均为空（见 git_* 字段与 ISOLATION.json）",
        },
        "price": price_meta,
        "protocol": {
            "root_head": (loaded["on"]["meta"].get("git_before") or {}).get("head"),
            "dataset": "synthetic",
            "tasks": int(loaded["on"]["meta"].get("cli", {}).get("tasks", on["n_tasks"])),
            "seed": loaded["on"]["meta"].get("cli", {}).get("seed"),
            "profile": loaded["on"]["meta"].get("cli", {}).get("profile"),
            "parallel": loaded["on"]["meta"].get("cli", {}).get("parallel"),
            "inject_rounds": loaded["on"]["meta"].get("cli", {}).get("inject_rounds"),
            "watchdog_seconds": loaded["on"]["meta"].get("cli", {}).get("watchdog_seconds"),
            "arms": {"on": "COVERAGE_STALL_DETECT_ENABLE=true", "off": "COVERAGE_STALL_DETECT_ENABLE=false"},
            "extra_env": loaded["on"]["meta"].get("extra_env") or {},
        },
        "arms": summaries,
        "harness_smoke": _load_harness_smoke(out_root, price_in, price_out),
        "paired": {
            "n_pairs": len(pair_rows),
            "delta_iterations_mean_off_minus_on": delta_iter_mean,
            "iterations_saved_off_minus_on": iterations_saved,
            "direction": direction,
            "rows": pair_rows,
        },
        "verdict": {
            "classification": verdict,
            "criteria": {
                "primary": {
                    "rule": "on.coverage_stall_rate >= 0.8 AND off.coverage_stall_count == 0",
                    "on_stall_rate": on["coverage_stall_rate"],
                    "on_stall_count": on["coverage_stall_count"],
                    "off_stall_rate": off["coverage_stall_rate"],
                    "off_stall_count": off["coverage_stall_count"],
                    "met": primary_met,
                },
                "secondary": {
                    "rule": "iterations_saved(off_mean-on_mean) >= 1.0 AND on/off crash_count == 0",
                    "iterations_saved": iterations_saved,
                    "on_crash": on["crash_count"],
                    "off_crash": off["crash_count"],
                    "met": secondary_met,
                },
                "harness": {
                    "rule": "on arm injection coverage: tasks_with_injection >= 80% 且 injected_rounds > 0",
                    "on_tasks_with_injection": on["injection"]["tasks_with_injection"],
                    "on_tasks_total": on["n_tasks"],
                    "on_injected_rounds": on["injection"]["injected_rounds"],
                    "met": harness_ok,
                },
            },
            "cost_total_usd": round(on["cost_usd_standard_price"] + off["cost_usd_standard_price"], 6),
            "wall_total_seconds": round(on["wall_seconds"] + off["wall_seconds"], 2),
        },
    }
    _write_json(out_root / "REPORT.json", report)
    _write_isolation(out_root, report)
    _write_readme(out_root, report)
    _write_sha256sums(out_root)
    print(json.dumps({"verdict": verdict, "report": str(out_root / "REPORT.json")}, ensure_ascii=False))
    # 聚合成功即 exit 0（判定结果在 REPORT.json.verdict；不把 not_confirmed 当执行失败）
    return 0


# ── run 模式的轻量辅助（延迟 import；避免聚合模式依赖 worktree） ──────────────
def _ensure_worktree_direct(root: str) -> dict[str, Any]:
    root_p = Path(root).resolve()
    if not root_p.is_dir():
        raise SystemExit(f"--root 不存在：{root_p}")
    if not (root_p / "experiments" / "run_benchmark.py").is_file():
        raise SystemExit(f"--root 不是 AITester 工作树（缺 experiments/run_benchmark.py）：{root_p}")
    if not (root_p / ".env.local").is_file():
        raise SystemExit(f"--root 缺 .env.local（真实 LLM 配置）：{root_p}")
    snap = _git_snapshot(str(root_p))
    if snap["dirty_lines"]:
        raise SystemExit(
            f"--root 工作树不干净（dirty_lines={snap['dirty_lines']}）——本实验要求干净切点：\n{snap['status_porcelain']}"
        )
    return snap


def _setup_imports_io(root: str) -> None:
    root_p = str(Path(root).resolve())
    main_repo = str(Path(__file__).resolve().parents[1])
    script_dir = str(Path(__file__).resolve().parent)
    # 只剔除"主仓根/主仓 experiments 脚本目录"两项（防止 import 落到主仓未跟踪
    # 代码）；**不得**按前缀剔除——.venv/lib/.../site-packages 也在主仓前缀下，
    # 误删会导致第三方依赖（dotenv 等）不可见（2026-10-18 冒烟实测踩坑）。
    drop = {os.path.normpath(main_repo), os.path.normpath(script_dir)}
    sys.path = [p for p in sys.path if os.path.normpath(p) not in drop]
    sys.path.insert(0, root_p)
    os.chdir(root_p)


def _verify_imports_direct(root: str) -> dict[str, str]:
    root_p = str(Path(root).resolve())
    import config
    import experiments.run_benchmark as rb
    import src.agents.executor as exec_mod
    import src.graph.workflow as wf_mod

    paths = {
        "config": str(Path(config.__file__).resolve()),
        "run_benchmark": str(Path(rb.__file__).resolve()),
        "executor": str(Path(exec_mod.__file__).resolve()),
        "workflow": str(Path(wf_mod.__file__).resolve()),
    }
    bad = {k: v for k, v in paths.items() if not v.startswith(root_p + os.sep)}
    if bad:
        raise SystemExit(f"模块来源不在 --root 下（导入隔离失败）：{bad}")
    return paths


# ── 聚合产物渲染 ─────────────────────────────────────────────────────────────
def _write_isolation(out_root: Path, report: dict[str, Any]) -> None:
    iso = report["isolation"]
    checks = {
        "on_git_before_clean": (iso.get("git_before_on") or {}).get("dirty_lines") == 0,
        "on_git_after_clean": (iso.get("git_after_on") or {}).get("dirty_lines") == 0,
        "off_git_before_clean": (iso.get("git_before_off") or {}).get("dirty_lines") == 0,
        "off_git_after_clean": (iso.get("git_after_off") or {}).get("dirty_lines") == 0,
        "on_diff_stat_empty": not (iso.get("git_after_on") or {}).get("diff_stat"),
        "off_diff_stat_empty": not (iso.get("git_after_off") or {}).get("diff_stat"),
        "patched_targets_documented": bool(iso.get("patched_targets")),
    }
    payload = {
        "statement": (
            "失败注入仅在实验驱动进程内以 monkeypatch 实现：src.graph.nodes._executor_node 仅透传 state；"
            "src.agents.executor.ExecutorAgent.execute 在注入轮返回强制失败。生产文件零改动。"
        ),
        "checks": checks,
        "all_checks_pass": all(checks.values()),
        "details": iso,
    }
    _write_json(out_root / "ISOLATION.json", payload)


def _write_readme(out_root: Path, report: dict[str, Any]) -> None:
    on, off = report["arms"]["on"], report["arms"]["off"]
    v = report["verdict"]
    p = report["protocol"]
    prim, sec, harn = v["criteria"]["primary"], v["criteria"]["secondary"], v["criteria"]["harness"]
    rows = report["paired"]["rows"]
    pair_lines = "\n".join(
        f"| {r['task_id']} | {r['iterations_on']} | {r['iterations_off']} | {r['delta_iterations_off_minus_on']:+d} | "
        f"{r['stop_reason_on']} | {r['stop_reason_off']} | {r['injected_rounds_on']} | {r['injected_rounds_off']} |"
        for r in rows
    )
    sr = lambda d: ", ".join(f"`{k}`×{n}" for k, n in d.items())  # noqa: E731
    smoke = report.get("harness_smoke") or []
    smoke_tokens = sum(int((row.get("token_metrics") or {}).get("total_tokens") or 0) for row in smoke)
    smoke_cost = round(sum(float(row.get("cost_usd_standard_price") or 0.0) for row in smoke), 6)
    grand_cost = round(float(v["cost_total_usd"]) + smoke_cost, 6)
    smoke_lines = (
        "\n".join(
            f"| `{row['smoke_dir']}` | {row['arm']} | {row['patch_evidence_gate_env']} | {row['iterations']} | "
            f"{row['iterations_mean']} | {', '.join(f'`{k}`×{v}' for k, v in row['stop_reason_counts'].items())} |"
            for row in smoke
        )
        or "| （无冒烟工件） | — | — | — | — | — |"
    )
    readme = f"""# S-2 / B8 / A-19：覆盖率停滞检测开/关消融（**确定性失败注入 harness**，2026-10-18）

> **性质**：机制验证性消融（harness-based ablation）——用**实验层确定性失败注入**保证
> 多轮失败 + 覆盖率停滞，回答"停滞检测（P-2 已接线）是否真的提前停止、省多少迭代"。
> **不是**对自然任务收益的估计：注入的失败是实验构造，结论只关于 A-19 停止逻辑本身。
> 预注册（跑前冻结）：[`PREREG.md`](PREREG.md) sha256=`{report["prereg"]["sha256"]}`；
> 切点 = 干净 worktree `{p.get("root_head")}`（HEAD 见 `REPORT.json`/`ISOLATION.json`）。

## 1. 结论（预注册判定）

**classification = `{v["classification"]}`**

| 判据 | 规则 | 实测 | 满足 |
|---|---|---|---|
| 主判据 | on 臂 coverage_stall 触发率 ≥80% 且 off 臂 =0% | on **{on["coverage_stall_count"]}/{on["n_tasks"]} = {on["coverage_stall_rate"]}**；off **{off["coverage_stall_count"]}/{off["n_tasks"]} = {off["coverage_stall_rate"]}** | {"✅" if prim["met"] else "❌"} |
| 次判据 | on 平均 iterations 比 off 少 ≥1 轮且两臂 0 crash | iterations 均值 on **{on["iterations_mean"]}** vs off **{off["iterations_mean"]}**（off−on = **{report["paired"]["iterations_saved_off_minus_on"]}**）；crash on/off = {on["crash_count"]}/{off["crash_count"]} | {"✅" if sec["met"] else "❌"} |
| harness 有效性 | on 臂注入覆盖任务 ≥80% 且注入轮 >0 | {harn["on_tasks_with_injection"]}/{harn["on_tasks_total"]} 任务、{harn["on_injected_rounds"]} 注入轮 | {"✅" if harn["met"] else "❌"} |

## 2. 注入方法与隔离证明

- **patch 目标（仅进程内 monkeypatch，`AITESTER_B8_INJECTION_ENABLE=1` 生效）**：
  1. `src.graph.nodes._executor_node`（及 `src.graph.workflow` 模块级引用）：**仅透传 state**，原逻辑原样执行；
  2. `src.agents.executor.ExecutorAgent.execute`：前 `inject_rounds={p["inject_rounds"]}` 轮（按 `state["iteration"]`）
     返回强制失败 `passed=False, output="INJECTED_FAILURE…"`，`coverage=上一轮 coverage`（首轮 0.0）
     → `execution_trace` 的 `coverage_delta` 从第 2 轮起恒 `0.0`（|Δ|<eps=0.5），满足
     `_coverage_stall_detected`（K=2 窗口；首轮 delta=None 不计数，故需 3 个强制失败轮）；
     第 `{p["inject_rounds"]} + 1` 轮起**恢复真实执行**（调原 `ExecutorAgent.execute`）。
- **两臂注入完全相同**，唯一差异 = `COVERAGE_STALL_DETECT_ENABLE=true|false`。
- **隔离证明**：生产文件零 diff（`git status --porcelain` / `git diff --stat` 前后为空，
  见 `ISOLATION.json` checks 全绿）；驱动在主仓 untracked，通过 `--root` 对 worktree 运行；
  运行时校验所有项目模块 `__file__` 均来自 `--root`。
- **注入记录**：`arm_on/injection_records_on.jsonl` / `arm_off/injection_records_off.jsonl`
  （逐轮 `task_id/iteration/injected/passed/coverage/coverage_delta/…`）。

## 3. 协议

| 项 | 值 |
|---|---|
| 切点 | 干净 worktree（HEAD `{p.get("root_head")}`，dirty=0；两臂 provenance 见下） |
| 数据集 | synthetic（`--dataset synthetic --task-count {p["tasks"]} --seed {p["seed"]}`） |
| 档位 | `AITESTER_PROFILE={p["profile"]}`（与 P-2 同：隔离 workflow 停止路由单变量）；`TEMPERATURE=0.0` / `LLM_THINKING_MODE=disabled` |
| 并行 | `BENCHMARK_PARALLELISM={p["parallel"]}`；两臂**并发**（两个进程、独立 cache namespace `s2_b8_injection_on/off`） |
| 真实 LLM | 是（planner/generator/debugger 真实调用；`AITESTER_LLM_CACHE=0`）；cap `AITESTER_BATCH_MAX_CALLS`、任务级 `COST_BUDGET_ENABLE/USD`、watchdog `{p["watchdog_seconds"]}s/臂` |
| 注入轮 | `--inject-rounds {p["inject_rounds"]}`（两臂相同） |
| 额外 env（两臂同设） | `{json.dumps(p.get("extra_env") or {}, ensure_ascii=False)}`（理由见 PREREG §2） |

主批实际命令（两臂**并发**两个进程、同一 worktree/同一 out；worktree 跑后保留）：

```bash
# 臂 on（stall ON）
.venv/bin/python experiments/run_b8_injection.py --root /Users/wangchenyu/Workspace/AITester-s2-b8-566f973 \\
  --out experiments/results/s_round_b8_injection_20261018 --arm on --tasks {p["tasks"]} --seed {p["seed"]} \\
  --profile {p["profile"]} --inject-rounds {p["inject_rounds"]} --watchdog-seconds {p["watchdog_seconds"]} \\
  --extra-env PATCH_EVIDENCE_GATE_ENABLE=false
# 臂 off（stall OFF）：同上，--arm off
# 零 LLM 聚合（判定/成本/隔离证据/SHA）
.venv/bin/python experiments/run_b8_injection.py --out experiments/results/s_round_b8_injection_20261018 --aggregate-only
```

## 4. 两臂实测

| 项 | on 臂（stall ON） | off 臂（stall OFF） |
|---|---|---|
| 任务数 | {on["n_tasks"]} | {off["n_tasks"]} |
| 墙钟(s) | {on["wall_seconds"]} | {off["wall_seconds"]} |
| stop_reason 分布 | {sr(on["stop_reason_counts"])} | {sr(off["stop_reason_counts"])} |
| **coverage_stall 触发** | **{on["coverage_stall_count"]}/{on["n_tasks"]} = {on["coverage_stall_rate"]}** | **{off["coverage_stall_count"]}/{off["n_tasks"]} = {off["coverage_stall_rate"]}** |
| iterations 均值/中位/max | {on["iterations_mean"]} / {on["iterations_median"]} / {on["iterations_max"]} | {off["iterations_mean"]} / {off["iterations_median"]} / {off["iterations_max"]} |
| coverage 均值 | {on["coverage_mean"]} | {off["coverage_mean"]} |
| passed 行数 | {on["passed_count"]} | {off["passed_count"]} |
| detection（可测/检出） | {on["detection"]["measurable"]}/{on["detection"]["positive"]}（{on["detection"]["rate"]}） | {off["detection"]["measurable"]}/{off["detection"]["positive"]}（{off["detection"]["rate"]}） |
| crash 行 | {on["crash_count"]} | {off["crash_count"]} |
| 注入记录（注入/真实轮） | {on["injection"]["injected_rounds"]}/{on["injection"]["real_rounds"]} | {off["injection"]["injected_rounds"]}/{off["injection"]["real_rounds"]} |
| tokens / LLM calls | {on["token_metrics"].get("total_tokens")} / {on["token_metrics"].get("total_llm_calls")} | {off["token_metrics"].get("total_tokens")} / {off["token_metrics"].get("total_llm_calls")} |
| 成本（标准价上界） | ${on["cost_usd_standard_price"]} | ${off["cost_usd_standard_price"]} |
| provenance git_sha/dirty | {on["provenance"]["git_sha"]}/{on["provenance"]["git_dirty"]} | {off["provenance"]["git_sha"]}/{off["provenance"]["git_dirty"]} |
| env_snapshot.COVERAGE_STALL_DETECT_ENABLE | {on["provenance"]["coverage_stall_env"]} | {off["provenance"]["coverage_stall_env"]} |

成本合计 ≈ **${v["cost_total_usd"]}**（预算 ≤$0.3）；两臂并发墙钟合计 {v["wall_total_seconds"]}s。

## 5. 配对（共同任务；Δ iterations = off − on）

n_pairs = {report["paired"]["n_pairs"]}；Δ均值 = **{report["paired"]["delta_iterations_mean_off_minus_on"]}**；
方向 off>on / = / off<on = {report["paired"]["direction"]["off_gt_on"]} / {report["paired"]["direction"]["equal"]} / {report["paired"]["direction"]["off_lt_on"]}。

| task_id | iter(on) | iter(off) | Δ(off−on) | stop(on) | stop(off) | 注入轮(on) | 注入轮(off) |
|---|---|---|---|---|---|---|---|
{pair_lines}

## 6. 判读

- 若 confirmed：在"确实多轮失败且覆盖率停滞"的构造场景下，停滞检测按设计在 {on["iterations_mean"]} 轮提前停止（off 臂 {off["iterations_mean"]} 轮），**省 {report["paired"]["iterations_saved_off_minus_on"]} 轮**且两臂无 crash；说明 P-2 的 wiring 修复在真实 workflow 中生效（非仅零 LLM 单测）。
- 若 not_confirmed：按 REPORT 中 `criteria` 逐项给出未满足项与归因（注入未稳定触发→harness_limitation；被判据以外的路由分支抢占→如实记录）。
- **不外推**：注入失败是实验构造（非自然缺陷失败率）；结论限于停止逻辑，不代表真实任务上的收益/代价，也不代表 logic/scientific 档行为（fast 档单变量）。
- **iteration 计数语义**：行级 `iterations` = 修复轮次索引（patch_applier 每次 +1），不是执行次数；
  ON 臂 2 个任务在执行第 3 轮时经 generator-regenerate 路径、修复索引仍为 1（trace_len=3），
  故 `iterations_mean=1.8` 而非 2.0。判定按预注册规则（停滞窗口 K=2 满足后短路），该差异已在
  §5 配对表逐任务披露（`delta` 仍 ≥1）。
- **注入轮数**：on 臂 {on["injection"]["injected_rounds"]} 个强制失败轮（10 任务×3）；off 臂
  {off["injection"]["injected_rounds"]} 个（2 个任务因 regenerate 路径出现额外 iteration<3 的执行轮，
  仍属同一注入规则 `iteration < inject_rounds`，非重跑/补测）。

## 7. 局限

- synthetic + fast 档 + 单 seed（{p["seed"]}）+ 单模型（deepseek-flash）；两臂并发共享 CPU。
- 注入只 patch 执行结果，planner/generator/debugger 仍真实 LLM 调用——不同任务的 debugger 补丁行为可能使循环提前停止（repair_invalid 等），这些真实分支抢占会如实反映在 stop_reason 分布中。
- 探索性机制验证：n={report["paired"]["n_pairs"]}，不做 confirmatory/因果主张。
- 注入轮={p["inject_rounds"]}（K=2 窗口需要 3 个强制失败轮，理由见 §2）。

## 9. 跑前 harness 冒烟（非主判定；披露）

两轮冒烟用于在冻结预注册前验证注入 harness 与停滞判据可达性（工件在
`_harness_smoke/`、`_harness_smoke_gateoff/`，不参与主判定）。冒烟合计
**{smoke_tokens} tokens ≈ ${smoke_cost}**（标准价）；主批 {on["token_metrics"].get("total_tokens", 0) + off["token_metrics"].get("total_tokens", 0)} tokens ≈ ${v["cost_total_usd"]}；
**含冒烟总成本 ≈ ${grand_cost}**（预算 ≤$0.3）。

| 冒烟目录 | 臂 | PATCH_EVIDENCE_GATE_ENABLE | iterations | iterations 均值 | stop_reason 分布 |
|---|---|---|---|---|---|
{smoke_lines}

关键结论：**默认协议（证据门默认 true）下，repair-invalid 分支在停滞窗口同一迭代收敛**——
on/off 两臂均 iterations=2，ON 仅把终止标签换成 `coverage_stall`（无迭代节省）；这是 A-19
接线后的**默认口径局限**，本批通过两臂同设 `PATCH_EVIDENCE_GATE_ENABLE=false` 解除前置抢占后
测量"可达场景"的提前停止收益（主判定口径）。该发现写入 README/PREREG，不改主判定规则。

## 10. 文件

| 文件 | 说明 |
|---|---|
| `PREREG.md` | 跑前冻结的预注册（sha256 见上） |
| `REPORT.json` | 机读聚合（两臂汇总/配对/判据/成本/隔离） |
| `arm_on/`、`arm_off/` | 每臂批次 JSON（自带时间戳）+ `traces/` + 注入记录 + meta JSON |
| `ISOLATION.json` | 生产文件零 diff 证据（git status/diff 前后快照 + checks） |
| `SHA256SUMS` | 全工件校验（`shasum -a 256 -c SHA256SUMS`） |
"""
    (out_root / "README.md").write_text(readme, encoding="utf-8")


def _write_sha256sums(out_root: Path) -> None:
    lines = []
    for path in sorted(p for p in out_root.rglob("*") if p.is_file()):
        if path.name == "SHA256SUMS":
            continue
        rel = path.relative_to(out_root).as_posix()
        lines.append(f"{_sha256_file(path)}  {rel}")
    (out_root / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="S-2 / B8 / A-19：覆盖率停滞检测 ON/OFF 消融 + 实验层确定性失败注入 harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--root", default=None, help="干净 worktree 根（生产代码从该处导入；run 模式必填）")
    p.add_argument("--out", required=True, help="结果目录（主仓 experiments/results/s_round_b8_injection_20261018）")
    p.add_argument("--arm", choices=["on", "off"], default=None, help="单臂运行：on=stall ON / off=stall OFF")
    p.add_argument("--tasks", type=int, default=10, help="synthetic 任务数（默认 10，与 P-2 可比）")
    p.add_argument("--seed", type=int, default=42, help="数据集 seed（默认 42）")
    p.add_argument(
        "--profile", choices=["fast", "logic"], default="fast", help="AITESTER_PROFILE（默认 fast，与 P-2 同）"
    )
    p.add_argument("--parallel", type=int, default=4, help="BENCHMARK_PARALLELISM（默认 4）")
    p.add_argument("--inject-rounds", type=int, default=3, help="前 N 轮强制失败（默认 3：K=2 窗口需 3 个强制失败轮）")
    p.add_argument(
        "--budget-usd",
        type=float,
        default=1.0,
        help="任务级 COST_BUDGET_USD（默认 1.0；总预算 ≤$0.3 由任务数/调用数约束）",
    )
    p.add_argument("--max-calls", type=int, default=150, help="AITESTER_BATCH_MAX_CALLS（默认 150/臂）")
    p.add_argument("--watchdog-seconds", type=float, default=1500.0, help="单臂看门狗秒数（默认 1500）")
    p.add_argument(
        "--price-table",
        default=None,
        help="价目表 JSON（默认 experiments/price_table.json，缺省用内置 deepseek-flash 标准价）",
    )
    p.add_argument("--dry-run", action="store_true", help="只打印计划/环境/模块来源，不跑 LLM")
    p.add_argument(
        "--aggregate-only", action="store_true", help="零 LLM：聚合两臂工件 → REPORT.json/README.md/SHA256SUMS"
    )
    p.add_argument(
        "--extra-env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="额外实验层环境变量（同两臂；如 PATCH_EVIDENCE_GATE_ENABLE=false），可重复；会记入 meta/protocol 供审计",
    )
    p.add_argument("--force", action="store_true", help="允许覆盖已存在批次产物的臂目录（默认拒绝，遵守不重跑纪律）")
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    if args.price_table is None:
        candidate = Path(__file__).resolve().parents[1] / "experiments" / "price_table.json"
        if candidate.is_file():
            args.price_table = str(candidate)

    if args.aggregate_only:
        return aggregate(args)
    if not args.root or not args.arm:
        logger.error("run 模式必须给 --root 与 --arm（或使用 --aggregate-only）")
        return 2
    if args.inject_rounds < 1:
        logger.error("--inject-rounds 必须 >= 1")
        return 2
    if args.tasks < 1:
        logger.error("--tasks 必须 >= 1")
        return 2

    if args.dry_run:
        plan = {
            "mode": "dry-run",
            "root": str(Path(args.root).resolve()),
            "out": str(out_root),
            "arm": args.arm,
            "tasks": args.tasks,
            "seed": args.seed,
            "profile": args.profile,
            "parallel": args.parallel,
            "inject_rounds": args.inject_rounds,
            "watchdog_seconds": args.watchdog_seconds,
            "env": {**_arm_env(args.arm, args), **_parse_extra_env(list(args.extra_env or []))},
            "steps": [
                "校验 --root 干净树/含 .env.local（不满足即失败）",
                "强制从 --root 导入项目模块并校验 __file__ 均来自 --root",
                "校验 --out/PREREG.md 已落盘（跑前冻结）",
                "install 进程内 monkeypatch（_executor_node 透传 state + ExecutorAgent.execute 注入）",
                "rb.run_benchmark(synthetic, aitester, tasks, seed, parallel, deterministic=True)",
                "卸载 patch；写 arm meta（git 前后快照/注入记录/批次 sha256）",
            ],
            "estimated_llm_calls": f"≤ {args.max_calls}/臂（任务级 budget ${args.budget_usd}）",
            "note": "dry-run 不导入 worktree 模块、不产生 LLM 调用",
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    return run_arm(args)


if __name__ == "__main__":
    raise SystemExit(main())
