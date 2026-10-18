#!/usr/bin/env python3
"""T2/B1 跑前闸：工作树/预注册/导入源/CLI/干预开关/旧批基线/预算估算 → PREFLIGHT.json。

用法：
    preflight.py --mode dry-run|real --out <OUT> --wt <WORKTREE> --expect-sha <SHA> --py <VENV_PY>

行为：
- dry-run：执行全部静态检查 + 真实导入探针（零 LLM 调用）→ 写 PREFLIGHT.json（含 6 条待跑命令）；
- real：要求已有 dry-run 全过的 PREFLIGHT.json；重新执行全部检查，把 real_preflight 块写回；
  任一 blocking 非空 → exit 1（不产生任何 LLM 调用）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

OUT = None  # set in main
WT = None
PY = None
EXPECT_SHA = None
PREREG = None
RESUME = False

BASE_ENV = {
    "AITESTER_PROFILE": "logic",
    "TEMPERATURE": "0.0",
    "LLM_THINKING_MODE": "disabled",
    "BENCHMARK_PARALLELISM": "4",
    "AITESTER_LLM_CACHE": "0",
    "COST_BUDGET_ENABLE": "true",
    "COST_BUDGET_TOKENS": "200000",
    "COST_BUDGET_USD": "1.0",
    "AITESTER_BATCH_MAX_CALLS": "4000",
    "AITESTER_BATCH_MAX_USD": "2.0",
    # PREREG_CONTINUATION.md 执行性修订：只关闭批后辅助测量（mutation_score/MDO），
    # 不改变 detection/生成/再生成/提示/预算。C1_seed42 为修订前已跑（保留不重跑）。
    "ENABLE_MUTATION_SCORING": "false",
}

CELLS = [
    ("C1", "plain_llm", "plain_llm", {}),
    ("C2", "rt1", "plain_llm_df", {"DETECTION_FIRST_SECTION_ENABLE": "false"}),
    ("C3", "df_full", "plain_llm_df", {}),
]
SEEDS = (42, 44)

def _build_run_plan(out: str) -> list[dict]:
    """6 跑运行计划（cell-major，seed 固定 42→44；与 PREREG §3 一致）。"""
    plan: list[dict] = []
    for cell, tag, arm, extra in CELLS:
        for seed in SEEDS:
            label = f"{cell}_{tag}_seed{seed}"
            plan.append(
                {
                    "label": label,
                    "cell": cell,
                    "tag": tag,
                    "arm": arm,
                    "seed": seed,
                    "output_dir": f"{out}/staging/{cell}_seed{seed}",
                    "trace_dir": f"{out}/traces/{cell}_seed{seed}",
                    "log_path": f"{out}/logs/{cell}_seed{seed}.log",
                    "meta_path": f"{out}/seed{seed}/meta_{cell}.json",
                    "extra_env": extra,
                }
            )
    return plan


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], *, env_extra: dict | None = None, timeout: int = 180, cwd: Path | None = None) -> dict:
    env = os.environ.copy()
    env.update(BASE_ENV)
    if env_extra:
        env.update(env_extra)
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd or WT),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {"ran": True, "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
    except subprocess.TimeoutExpired as exc:
        return {
            "ran": True,
            "exit_code": 124,
            "stdout": (exc.stdout or "") if isinstance(exc.stdout, str) else "",
            "stderr": f"timeout after {timeout}s",
        }
    except Exception as exc:  # noqa: BLE001
        return {"ran": False, "exit_code": None, "stdout": "", "stderr": str(exc)}


def _git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(cwd or WT), capture_output=True, text=True, timeout=30)


def _load_old_baseline() -> dict:
    """从 2026-10-09 旧批工件直接复算三格基线（不硬编码数字；路径缺失则如实标注）。"""
    base = Path("/Users/wangchenyu/Workspace/AITester/experiments/results/e6_a1_batches")
    paths = {
        "plain_llm": (base / "e6_phase1_standard_coldcache" / "benchmark_synthetic_20261009_190234.json", "plain_llm"),
        "df_full": (base / "e6_phase1_standard_coldcache" / "benchmark_synthetic_20261009_190234.json", "plain_llm_df"),
        "rt1": (base / "rt1_no_reinforcement_seed42" / "benchmark_synthetic_20261009_193509.json", "plain_llm_df"),
    }
    out: dict = {}
    for name, (path, arm) in paths.items():
        item: dict = {"path": str(path), "arm": arm, "present": path.is_file()}
        if path.is_file():
            d = json.loads(path.read_text(encoding="utf-8"))
            rows = ((d.get("results") or {}).get(arm) or {}).get("details") or []
            det = [r.get("detection_rate") for r in rows if isinstance(r.get("detection_rate"), (int, float)) and not isinstance(r.get("detection_rate"), bool)]
            tm = ((d.get("results") or {}).get(arm) or {}).get("token_metrics") or {}
            prov = d.get("provenance") or {}
            item.update(
                {
                    "batch": path.name,
                    "detected": sum(1 for v in det if float(v) >= 1.0),
                    "measurable": len(det),
                    "rows": len(rows),
                    "token_metrics": {
                        "total_input_tokens": tm.get("total_input_tokens"),
                        "total_output_tokens": tm.get("total_output_tokens"),
                        "total_tokens": tm.get("total_tokens"),
                        "total_llm_calls": tm.get("total_llm_calls"),
                    },
                    "provenance": {
                        "git_sha": prov.get("git_sha"),
                        "git_dirty": prov.get("git_dirty"),
                        "has_model_fingerprint": "model_fingerprint" in prov,
                        "cache_namespace": prov.get("cache_namespace"),
                    },
                }
            )
        out[name] = item
    return out


def _estimate(old: dict) -> dict:
    """预算/墙钟估算：旧批 token × 价目表；墙钟按旧批单跑实测外推。"""
    price_path = Path("/Users/wangchenyu/Workspace/AITester/experiments/price_table.json")
    price = json.loads(price_path.read_text(encoding="utf-8")).get("models", {}).get("deepseek-flash", {})
    p_in, p_out = float(price["input_per_mtok"]), float(price["output_per_mtok"])
    per_seed_in = 0.0
    per_seed_out = 0.0
    for name in ("plain_llm", "rt1", "df_full"):
        tm = (old.get(name) or {}).get("token_metrics") or {}
        per_seed_in += float(tm.get("total_input_tokens") or 0)
        per_seed_out += float(tm.get("total_output_tokens") or 0)
    cost_per_seed = (per_seed_in * p_in + per_seed_out * p_out) / 1e6
    # 旧批单跑墙钟：rt1 实测 713.5s（日志）；C1≈0.5×，C3≈1.2× → 每 seed ≈ (0.5+1.0+1.2)*713.5
    wall_per_run_proxy = 713.5
    wall_per_seed = (0.5 + 1.0 + 1.2) * wall_per_run_proxy
    return {
        "price_basis": {"path": str(price_path), "model": "deepseek-flash", "input_per_mtok": p_in, "output_per_mtok": p_out},
        "old_token_metrics_per_seed": {"input": per_seed_in, "output": per_seed_out},
        "cost_per_seed_usd": round(cost_per_seed, 4),
        "cost_2seeds_usd": round(cost_per_seed * 2, 4),
        "cost_upper_bound_usd": round(cost_per_seed * 2 * 1.3, 4),
        "cost_hard_stop_usd": 1.8,
        "wall_per_run_proxy_seconds": wall_per_run_proxy,
        "wall_estimate_minutes": round(2 * wall_per_seed / 60, 1),
        "wall_hard_stop_seconds": 5100,
        "wall_budget_minutes": 90,
        "budget_usd": 2.0,
        "per_run_watchdog_seconds": 1800,
    }


def _probe_switches() -> dict:
    """干预生效性探针（零 LLM）：验证 section 开关只关提示词、不动路由，且段落内容确实切换。"""
    snippet = (
        "import json, os\n"
        "import config as _cfg\n"
        "from src.graph.nodes import (\n"
        "    _detection_first_section, _detection_first_section_enabled,\n"
        "    _detection_first_regenerate_entry,\n"
        ")\n"
        "_cfg.set_detection_first_thread_override(True)\n"
        "state = {'test_passed': True, 'iteration': 0}\n"
        "sec = _detection_first_section(state)\n"
        "out = {\n"
        "  'profile': _cfg.ACTIVE_PROFILE,\n"
        "  'temperature': _cfg.TEMPERATURE,\n"
        "  'max_regenerations': _cfg.MAX_REGENERATIONS,\n"
        "  'section_env': os.environ.get('DETECTION_FIRST_SECTION_ENABLE'),\n"
        "  'section_enabled': _detection_first_section_enabled(),\n"
        "  'regenerate_entry_true': _detection_first_regenerate_entry(state),\n"
        "  'section_is_none': sec is None,\n"
        "  'section_len': len(sec) if sec else 0,\n"
        "  'section_head': (sec or '')[:24],\n"
        "  'mutation_scoring': _cfg.ENABLE_MUTATION_SCORING,\n"
        "}\n"
        "_cfg.set_detection_first_thread_override(None)\n"
        "print(json.dumps(out, ensure_ascii=False))\n"
    )
    probe = {}
    for name, extra in (
        ("default_section_on", {}),
        ("section_off", {"DETECTION_FIRST_SECTION_ENABLE": "false"}),
    ):
        r = _run([PY, "-c", snippet], env_extra=extra, timeout=180)
        rec = {"exit_code": r["exit_code"], "stderr_tail": r["stderr"][-500:]}
        try:
            rec.update(json.loads(r["stdout"].strip().splitlines()[-1]))
        except Exception:
            rec["parse_error"] = True
        rec["ran"] = r["ran"]
        probe[name] = rec
    return probe


def run_checks(mode: str) -> dict:
    run_plan = _build_run_plan(str(OUT))
    checks: list[dict] = []
    blocking: list[str] = []
    warnings: list[str] = []

    def chk(cid: str, ok: bool, detail, *, block: bool = True) -> None:
        checks.append({"id": cid, "ok": bool(ok), "detail": detail, "blocking": bool(block and not ok)})
        if block and not ok:
            blocking.append(cid)

    # 1) 工作树
    wt_exists = WT.is_dir()
    chk("worktree_exists", wt_exists, str(WT))
    head = None
    dirty_lines = None
    dirty_list: list[str] = []
    if wt_exists:
        head = _git(["rev-parse", "HEAD"]).stdout.strip()
        dirty = _git(["status", "--porcelain"]).stdout
        dirty_lines = len([x for x in dirty.splitlines() if x.strip()])
        dirty_list = [x for x in dirty.splitlines() if x.strip()][:20]
    chk("worktree_head_matches_cut", head == EXPECT_SHA, {"head": head, "expected": EXPECT_SHA})
    chk("worktree_clean", dirty_lines == 0, {"dirty_lines": dirty_lines, "sample": dirty_list})
    env_files = {"env": (WT / ".env").is_file(), "env_local": (WT / ".env.local").is_file()}
    chk("worktree_env_files_present", all(env_files.values()), env_files)

    # 2) 预注册冻结
    prereg_exists = PREREG.is_file()
    chk("prereg_present", prereg_exists, str(PREREG))
    prereg_sha = _sha256(PREREG) if prereg_exists else None
    prereg_text = PREREG.read_text(encoding="utf-8") if prereg_exists else ""
    chk("prereg_contains_cut_sha", EXPECT_SHA in prereg_text, EXPECT_SHA)
    chk("prereg_mentions_frozen", "冻结" in prereg_text and "不得事后改动" in prereg_text, "含冻结声明")
    chk("prereg_not_modified_after_freeze" if mode == "real" else "prereg_hashable", prereg_sha is not None, prereg_sha)

    # 3) 导入源（cwd=工作树 → 必须解析到工作树文件）
    src_probe = _run(
        [PY, "-c", "import experiments, config, src.graph.nodes as n; print(experiments.__file__); print(config.__file__); print(n.__file__)"],
        timeout=180,
    )
    src_files = [x for x in src_probe["stdout"].splitlines() if x.strip()]
    import_ok = src_probe["exit_code"] == 0 and all(str(WT) in f for f in src_files)
    chk("import_source_under_worktree", import_ok, {"exit_code": src_probe["exit_code"], "files": src_files, "stderr_tail": src_probe["stderr"][-500:]})

    # 4) CLI 可用
    help_run = _run([PY, "-m", "experiments.run_benchmark", "--help"], timeout=240)
    cli_ok = help_run["exit_code"] == 0 and "--baselines" in help_run["stdout"]
    chk("run_benchmark_cli_ok", cli_ok, {"exit_code": help_run["exit_code"], "help_head": help_run["stdout"][:300]})

    # 5) 臂注册
    reg = _run(
        [PY, "-c", "from experiments.run_benchmark import BASELINE_REGISTRY as R; print(','.join(sorted(R)))"],
        timeout=240,
    )
    arms = reg["stdout"].strip().split(",") if reg["exit_code"] == 0 else []
    chk("baseline_arms_registered", {"plain_llm", "plain_llm_df"}.issubset(set(arms)), {"arms": arms})

    # 6) 干预开关探针（核心：C2 段落关、路由不变）
    probe = _probe_switches()
    on_ok = (
        probe["default_section_on"].get("section_enabled") is True
        and probe["default_section_on"].get("regenerate_entry_true") is True
        and probe["default_section_on"].get("section_is_none") is False
    )
    off_ok = (
        probe["section_off"].get("section_enabled") is False
        and probe["section_off"].get("regenerate_entry_true") is True  # 路由不受 section 开关影响
        and probe["section_off"].get("section_is_none") is True
    )
    profile_ok = probe["default_section_on"].get("profile") == "logic"
    chk("intervention_switch_effective", on_ok and off_ok and profile_ok, probe)
    chk(
        "thinking_mode_disabled",
        probe["default_section_on"].get("temperature") == 0.0,
        {"temperature": probe["default_section_on"].get("temperature")},
    )
    # PREREG_CONTINUATION.md：本批（C1_seed44 起）显式关闭批后 mutation/MDO 辅助测量
    chk(
        "mutation_scoring_disabled_by_amendment",
        probe["default_section_on"].get("mutation_scoring") is False,
        {"ENABLE_MUTATION_SCORING": probe["default_section_on"].get("mutation_scoring")},
    )

    # 7) 输出目录可写 & 位于工作树外
    out_ok = FT = False
    try:
        OUT.mkdir(parents=True, exist_ok=True)
        probe_file = OUT / ".preflight_write_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        out_ok = True
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"输出目录不可写: {exc}")
    chk("output_dir_writable", out_ok, str(OUT))
    inside_wt = str(OUT).startswith(str(WT))
    chk("output_dir_outside_worktree", not inside_wt, {"out": str(OUT), "wt": str(WT)})
    # staging 既有批次 JSON：非续跑模式禁止同格重跑；续跑模式允许（runner 跳过已完成格）
    existing = sorted(str(p.relative_to(OUT)) for p in OUT.glob("staging/*/benchmark_synthetic_*.json"))
    if RESUME:
        chk("staging_resume_aware", True, {"existing_kept": existing, "note": "resume 模式：runner 仅跳过 run_status=ok 的格"}, blocking=False)
    else:
        chk("staging_pristine_before_real_run" if mode == "real" else "staging_pristine", len(existing) == 0, {"existing": existing})

    # 8) 旧批基线工件在场（并排对照的取证基础，缺失不阻断但必须可见）
    old = _load_old_baseline()
    for name, item in old.items():
        chk(
            f"old_baseline_present_{name}",
            item["present"],
            {"path": item["path"]},
            block=False,
        )
    old_expected = {"plain_llm": 9, "rt1": 10, "df_full": 27}
    if all(old[n]["present"] for n in old_expected):
        ok_nums = all(old[n]["detected"] == old_expected[n] for n in old_expected)
        chk("old_baseline_numbers_recomputed", ok_nums, {n: f"{old[n]['detected']}/{old[n]['measurable']}" for n in old_expected}, block=False)
    else:
        chk("old_baseline_numbers_recomputed", False, "旧批工件缺失，无法复算", block=False)
        warnings.append("旧批工件缺失：新旧并排对照不可复算")

    # 9) 预算/墙钟估算 + 硬停止阈值
    estimate = _estimate(old)
    chk("budget_estimate_under_cap", estimate["cost_upper_bound_usd"] <= estimate["budget_usd"], estimate)
    chk("wall_estimate_under_budget", estimate["wall_estimate_minutes"] <= estimate["wall_budget_minutes"], estimate["wall_estimate_minutes"])

    # 10) 无并发同批进程
    ps = subprocess.run(["pgrep", "-fl", "run_t2_b1_protocol_text"], capture_output=True, text=True)
    running = [x for x in ps.stdout.splitlines() if "run_t2_b1_protocol_text.sh" in x and str(os.getpid()) not in x]
    # 自身（bash runner → preflight）会命中一次；只警告，不阻断
    if running:
        warnings.append(f"检测到同行 runner 进程（可能是本脚本自身）：{running[:3]}")

    return {
        "schema": "t2_b1_protocol_text_preflight/1",
        "mode": mode,
        "run_stamp": OUT.name,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "git": {
            "root": str(WT),
            "root_head": head,
            "expected_sha": EXPECT_SHA,
            "dirty_lines_before": dirty_lines,
            "dirty_sample": dirty_list,
        },
        "prereg": {"path": str(PREREG), "sha256": prereg_sha},
        "source_hashes": {
            "experiments/results/t_round_b1_protocol_text_20261018/PREREG.md": prereg_sha,
            "experiments/results/t_round_b1_protocol_text_20261018/_helpers/extract_arm.py": _sha256(OUT / "_helpers" / "extract_arm.py") if (OUT / "_helpers" / "extract_arm.py").is_file() else None,
            "experiments/results/t_round_b1_protocol_text_20261018/_helpers/limited_run.py": _sha256(OUT / "_helpers" / "limited_run.py") if (OUT / "_helpers" / "limited_run.py").is_file() else None,
        },
        "checks": checks,
        "blocking": blocking,
        "warnings": warnings,
        "old_baseline_20261009": old,
        "switch_probe": probe,
        "cli_probe": {"exit_code": help_run["exit_code"], "help_head": help_run["stdout"][:400]},
        "import_source_check": {"exit_code": src_probe["exit_code"], "files": src_files},
        "estimate": estimate,
        "execution_amendment": {
            "file": "PREREG_CONTINUATION.md",
            "scope": "execution-only（判据未改）",
            "resume_mode": RESUME,
            "note": "C1_seed44 起 ENABLE_MUTATION_SCORING=false 关闭批后 mutation/MDO 辅助测量；C1_seed42 为修订前已跑保留不重跑",
        },
        "run_plan": run_plan,
        "shared_env": BASE_ENV,
        "dry_run_commands": [
            {
                "label": p["label"],
                "cwd": str(WT),
                "env": {**BASE_ENV, "AITESTER_CACHE_NAMESPACE": f"t_b1_{p['cell']}_{p['seed']}", "AITESTER_TRACE_DIR": p["trace_dir"], **p["extra_env"]},
                "argv": [
                    PY,
                    "-m",
                    "experiments.run_benchmark",
                    "--dataset",
                    "synthetic",
                    "--task-count",
                    "87",
                    "--max-pattern-repeat",
                    "2",
                    "--seed",
                    str(p["seed"]),
                    "--baselines",
                    p["arm"],
                    "--output-dir",
                    p["output_dir"],
                ],
            }
            for p in run_plan
        ],
    }


def main() -> int:
    global OUT, WT, PY, EXPECT_SHA, PREREG, RESUME
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["dry-run", "real"], required=True)
    ap.add_argument("--resume", action="store_true", help="续跑模式：允许已完成格保留（不重跑）")
    ap.add_argument("--out", required=True)
    ap.add_argument("--wt", required=True)
    ap.add_argument("--expect-sha", required=True)
    ap.add_argument("--py", required=True)
    args = ap.parse_args()

    OUT = Path(args.out).resolve()
    WT = Path(args.wt).resolve()
    PY = args.py
    EXPECT_SHA = args.expect_sha
    PREREG = OUT / "PREREG.md"
    RESUME = bool(args.resume)

    payload = run_checks(args.mode)
    preflight_path = OUT / "PREFLIGHT.json"

    if args.mode == "dry-run":
        payload["dry_run"] = {"ok": not payload["blocking"], "ran_at_utc": datetime.now(UTC).isoformat()}
        preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[preflight] dry-run: checks={len(payload['checks'])} blocking={payload['blocking']} → {preflight_path}")
        return 0 if not payload["blocking"] else 1

    # real：必须已有 dry-run 全过
    if not preflight_path.is_file():
        print("[preflight][FAIL] 缺少 dry-run 的 PREFLIGHT.json：先跑 --dry-run", file=sys.stderr)
        return 1
    prior = json.loads(preflight_path.read_text(encoding="utf-8"))
    dry = prior.get("dry_run") or {}
    if not dry.get("ok"):
        print("[preflight][FAIL] dry-run 未通过，禁止真实跑批", file=sys.stderr)
        return 1
    if prior.get("git", {}).get("root_head") != EXPECT_SHA:
        print("[preflight][FAIL] dry-run 时的 HEAD 与切点不符", file=sys.stderr)
        return 1
    payload["dry_run_ref"] = {"ok": dry.get("ok"), "ran_at_utc": dry.get("ran_at_utc"), "prereg_sha256": prior.get("prereg", {}).get("sha256")}
    payload["real_preflight"] = {
        "ok": not payload["blocking"],
        "ran_at_utc": datetime.now(UTC).isoformat(),
        "mode": "real",
    }
    if payload["prereg"]["sha256"] != prior.get("prereg", {}).get("sha256"):
        payload["blocking"].append("prereg_sha_changed_since_dry_run")
        payload["checks"].append({"id": "prereg_sha_changed_since_dry_run", "ok": False, "detail": {"dry_run": dry.get("prereg_sha256"), "now": payload["prereg"]["sha256"]}, "blocking": True})
    if payload["blocking"]:
        preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[preflight][FAIL] real 前置检查未过：blocking={payload['blocking']}", file=sys.stderr)
        return 1
    preflight_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[preflight] real OK: checks={len(payload['checks'])} → {preflight_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
