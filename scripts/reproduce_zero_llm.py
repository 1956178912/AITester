#!/usr/bin/env python3
"""reproduce_zero_llm.py — 零 LLM 复算链编排器（EMSE Open Science 复制包 L0/L1）。

用途：
    一键复现论文主数字（零 LLM），产出 consolidated `REPRODUCTION_REPORT.md`
    与 `REPRODUCTION_REPORT.json`，并校验关键工件目录的 SHA256SUMS 完整性。
    面向 EMSE Open Science Board 四维度之「可执行性 / 完整性」的机械化入口。

分层（对齐 `experiments/results/REPLICATION_PACKAGE.md` §3）：
    L0（五分钟级，默认）   统计扩展 + 统计报告补口 + mutation×detection +
                           SWE-bench 披露 + 通过率混淆敏感性 + 引用可追溯性；
    L1（小时级，--level l1）Mut@k 全量重算（cosmic-ray 本地确定性执行，
                           耗时数小时，默认不跑）。

设计纪律：
    - 每条命令独立运行并记录 exit code 与输出尾；任一失败即整体返回非零
      （报告仍完整写出，供排查）；
    - 报告内嵌 git sha + 时间戳 + Python 版本，跨版本串味可检测；
    - 本脚本只读归档工件 + 执行零 LLM 复算脚本，不调用 LLM、不写实验状态。

用法：
    python scripts/reproduce_zero_llm.py            # L0
    python scripts/reproduce_zero_llm.py --level l1 # L0 + L1（小时级）
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable  # 本脚本运行所用的解释器（venv python）

OUT_DIR = REPO / "experiments" / "results"
REPORT_MD = OUT_DIR / "REPRODUCTION_REPORT.md"
REPORT_JSON = OUT_DIR / "REPRODUCTION_REPORT.json"

# (显示名, 命令 argv, 输出尾保留行数)
_L0_COMMANDS: list[tuple[str, list[str], int]] = [
    (
        "统计扩展（Wilson CI / Cohen's g / OR / bootstrap Δ CI）",
        ["-m", "experiments.emse_stats_extensions"],
        12,
    ),
    (
        "统计报告补口（MDE / 功效 / 比例型 bootstrap CI）",
        ["-m", "experiments.emse_stats_report"],
        6,
    ),
    (
        "mutation × detection 交叉验证",
        [
            "-m",
            "experiments.emse_optimization",
            "--mutation-correlation",
            "experiments/results/main_batch",
            "--out",
            str(OUT_DIR / "main_batch" / "mutation_detection_correlation.md"),
        ],
        6,
    ),
    (
        "SWE-bench Lite 基础设施失败披露",
        [
            "-m",
            "experiments.emse_optimization",
            "--swebench-disclosure",
            "--out",
            str(OUT_DIR / "emse_swebench_disclosure.md"),
        ],
        6,
    ),
    (
        "通过率混淆敏感性分析",
        ["-m", "experiments.pass_matched_sensitivity"],
        6,
    ),
    (
        "引用可追溯性核验",
        ["scripts/gates/check_citations.py", "--traceability"],
        6,
    ),
]

_L1_COMMANDS: list[tuple[str, list[str], int]] = [
    (
        "QuixBugs 全量 Mut@k 重算（cosmic-ray，小时级）",
        ["-m", "experiments.emse_quixbugs_mutk_full"],
        6,
    ),
]

# 需校验 SHA256SUMS 的工件目录（存在即校验，缺失则标记 skipped）
_CHECKSUM_DIRS: list[str] = [
    "experiments/results/main_batch",
    # AZ（2026-10-21）：20261016 为 F01/F02 修正前的历史归档（只校验、不重写）；
    # 当前代码默认重发到 20261021。
    "experiments/results/emse_stats_extensions_20261016",
    "experiments/results/emse_stats_extensions_20261021",
    "experiments/results/emse_quixbugs_mutk_full_20261015",
    "experiments/results/emse_ult_mutk_full_20261015",
]


def _run(cmd: list[str]) -> tuple[int, str]:
    """运行命令，返回 (exit code, 输出尾)。超时 1800s（L1 cosmic-ray 上限）。"""
    proc = subprocess.run(
        [PY, *cmd],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    tail = (proc.stdout or "").strip().splitlines()[-8:]
    if proc.stderr and proc.returncode != 0:
        tail += ["[stderr]", *((proc.stderr or "").strip().splitlines()[-3:])]
    return proc.returncode, "\n".join(tail)


def _verify_checksums() -> list[dict[str, Any]]:
    """校验关键工件目录 SHA256SUMS。"""
    out: list[dict[str, Any]] = []
    for rel in _CHECKSUM_DIRS:
        d = REPO / rel
        sums = d / "SHA256SUMS"
        if not sums.is_file():
            out.append({"dir": rel, "status": "skipped", "detail": "无 SHA256SUMS 文件"})
            continue
        proc = subprocess.run(
            ["shasum", "-a", "256", "-c", "SHA256SUMS"],
            cwd=str(d),
            capture_output=True,
            text=True,
            timeout=300,
        )
        ok = proc.returncode == 0
        out.append(
            {
                "dir": rel,
                "status": "ok" if ok else "FAILED",
                "detail": (proc.stdout or proc.stderr or "").strip().splitlines()[-1][:120] if not ok else "全部通过",
            }
        )
    return out


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return (proc.stdout or "").strip() or "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--level", choices=["l0", "l1"], default="l0", help="复算层级：l0（默认，五分钟级）/ l1（含小时级 Mut@k）"
    )
    args = ap.parse_args()

    commands = list(_L0_COMMANDS)
    if args.level == "l1":
        commands += _L1_COMMANDS

    sha = _git_sha()
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results: list[dict[str, Any]] = []
    for name, cmd, _ in commands:
        print(f"[repro] ▶ {name}", flush=True)
        rc, tail = _run(cmd)
        status = "ok" if rc == 0 else "FAILED"
        print(f"[repro]   {status}（rc={rc}）", flush=True)
        results.append({"name": name, "command": " ".join(cmd), "status": status, "rc": rc, "tail": tail})

    checksums = _verify_checksums()
    print("[repro] ▶ SHA256SUMS 校验", flush=True)
    for c in checksums:
        print(f"[repro]   {c['status']} {c['dir']}", flush=True)

    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_total = len(results)
    cs_ok = sum(1 for c in checksums if c["status"] == "ok")
    cs_fail = sum(1 for c in checksums if c["status"] == "FAILED")

    # 写 markdown 报告
    lines = [
        "# AITester 零 LLM 复算报告（REPRODUCTION_REPORT）",
        "",
        f"> 生成时间：{started}；git sha：`{sha}`；Python：{sys.version.split()[0]}；",
        f"> 层级：{args.level.upper()}；**{n_ok}/{n_total} 条命令通过**；"
        f"SHA256SUMS：{cs_ok} 通过 / {cs_fail} 失败 / {len(checksums) - cs_ok - cs_fail} 跳过。",
        "",
        "本报告由 `scripts/reproduce_zero_llm.py` 生成，零 LLM 逐位复算论文主数字。",
        "每条命令的输出尾供审稿人核对复现值。",
        "",
        "## 复算命令",
        "",
        "| 命令 | 状态 | 输出尾 |",
        "|---|---|---|",
    ]
    for r in results:
        tail_md = (r["tail"] or "（无输出）").replace("|", "\\|").replace("\n", "<br>")
        mark = "✅" if r["status"] == "ok" else "❌"
        lines.append(f"| {r['name']} | {mark}（rc={r['rc']}） | {tail_md} |")

    lines += [
        "",
        "## 工件完整性（SHA256SUMS）",
        "",
        "| 目录 | 状态 | 明细 |",
        "|---|---|---|",
    ]
    for c in checksums:
        mark = {"ok": "✅", "FAILED": "❌", "skipped": "⬜"}[c["status"]]
        lines.append(f"| {c['dir']} | {mark} {c['status']} | {c['detail']} |")

    lines += [
        "",
        "## 复现入口",
        "",
        "```bash",
        "python scripts/reproduce_zero_llm.py            # L0（五分钟级）",
        "python scripts/reproduce_zero_llm.py --level l1 # L0 + L1（小时级 Mut@k）",
        "```",
        "",
    ]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")

    payload = {
        "generated_at": started,
        "git_sha": sha,
        "python": sys.version.split()[0],
        "level": args.level,
        "summary": {"commands_ok": n_ok, "commands_total": n_total, "checksums_ok": cs_ok, "checksums_failed": cs_fail},
        "commands": results,
        "checksums": checksums,
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    print(f"\n[repro] 报告 → {REPORT_MD}")
    print(f"[repro] JSON  → {REPORT_JSON}")
    print(f"[repro] 结论：{n_ok}/{n_total} 命令通过；SHA256SUMS {cs_ok} 通过 / {cs_fail} 失败")

    return 0 if (n_ok == n_total and cs_fail == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
