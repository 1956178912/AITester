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


# (显示名, 命令 argv, 输出尾保留行数, 前提探针 | None)
# 前提探针：源工件撤回（2026-10-24 数据清除）的支路在缺席时显式 [SKIP]——
# 不硬红（可复算性受损是事实，不是失败）也不谎报 ok。
def _skip_main_batch() -> str | None:
    from pathlib import Path as _P

    if not (
        _P("experiments/results/main_batch").is_dir()
        and list(_P("experiments/results/main_batch").glob("benchmark_*.json"))
    ):
        return "源批次 main_batch 已随 2026-10-24 数据清除撤回，本支路待主批重建后恢复"
    return None


_L0_COMMANDS: list[tuple[str, list[str], int, object]] = [
    (
        "统计扩展（Wilson CI / Cohen's g / OR / bootstrap Δ CI）",
        ["-m", "experiments.emse_stats_extensions"],
        12,
        None,
    ),
    (
        "统计报告补口（MDE / 功效 / 比例型 bootstrap CI）",
        ["-m", "experiments.emse_stats_report"],
        6,
        _skip_main_batch,
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
        _skip_main_batch,
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
        None,
    ),
    (
        "通过率混淆敏感性分析",
        ["-m", "experiments.pass_matched_sensitivity"],
        6,
        _skip_main_batch,
    ),
    (
        "引用可追溯性核验",
        ["scripts/gates/check_citations.py", "--traceability"],
        6,
        None,
    ),
]

_L1_COMMANDS: list[tuple[str, list[str], int]] = [
    (
        "QuixBugs 全量 Mut@k 重算（cosmic-ray，小时级）",
        ["-m", "experiments.emse_quixbugs_mutk_full"],
        6,
        None,
    ),
]

# 需校验 SHA256SUMS 的工件目录（存在即校验；缺席登记为 absent 披露）
#
# CM 轮（2026-10-25）修正两处「清单比现实长、现实比清单空」：
#   ① 原清单 6 条里 5 条已随 2026-10-24 数据清除消失，只剩 20261025 一条在盘，
#      而它没有清单 ⇒ 完整性校验长期是「0 通过 / 0 失败 / 6 跳过」，报告仍读作
#      「通过」。缺席是事实（披露即可），**存在却没有清单**才是不可复算的缺陷。
#   ② 论文当前引用的批次（b1_lite / spec_ab_scale87 / 锚与增广批）不在清单里，
#      等于主数字的载体从未被完整性覆盖。
_CHECKSUM_DIRS: list[str] = [
    # 当前重建世代（论文 v0.5/v0.6 的数字载体）
    "experiments/results/emse_stats_extensions_20261025",
    "experiments/results/spec_ab_scale87_20261024",
    "experiments/results/b1_lite_20261025",
    "experiments/results/emse_docstring_anchor_20261017",
    "experiments/results/emse_docstring_augment_20261017",
    "experiments/results/emse_misguided_augment_20261017",
    "experiments/results/p_round_b8_ablation_20261018",
    "experiments/results/emse_spec_anchor_20261016",
    # 已撤回世代：保留在册，缺席要被看见（不得静默从清单消失）
    "experiments/results/main_batch",
    "experiments/results/emse_stats_extensions_20261016",
    "experiments/results/emse_stats_extensions_20261021",
    "experiments/results/emse_quixbugs_mutk_full_20261015",
    "experiments/results/emse_ult_mutk_full_20261015",
]

# 完整性清单的受检面：除原始 trace 外的全部文件。
# 论文数字来自 benchmark / stats / raw 工件；trace 是 LLM 原始响应的旁路记录，
# 体积与条数都大两个数量级，纳入清单会把「完整性」稀释成「日志归档」。
_CHECKSUM_EXCLUDED_PARTS = frozenset({"traces"})


def _checksum_files(directory: Path) -> list[str]:
    """列出受检文件（相对路径，排序稳定，排除 trace / 隐藏文件 / 清单自身）。"""
    files: list[str] = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(directory)
        if _CHECKSUM_EXCLUDED_PARTS.intersection(rel.parts):
            continue
        if any(part.startswith(".") for part in rel.parts):
            continue  # 运行时标记（.arm_*.pid/.rc/.start）不是分发工件
        if rel.name in {"SHA256SUMS", "SHA256SUMS.tmp"}:
            continue
        files.append(rel.as_posix())
    return files


def write_checksums() -> list[dict[str, Any]]:
    """为**尚无清单**的在盘目录生成 SHA256SUMS（原子写）。

    已有清单一律不覆盖：既有清单是历史归档的一部分（可能由
    `scripts/gates/checksum_results.py` 以不同受检面生成），生成器改写它
    等于改写归档——CM 轮首版实测把两份既有清单改写（一份 100 行被删），
    已回退并改为「只补缺、不重写」。
    """
    import hashlib

    written: list[dict[str, Any]] = []
    for rel in _CHECKSUM_DIRS:
        directory = REPO / rel
        if not directory.is_dir():
            continue
        if (directory / "SHA256SUMS").is_file():
            continue
        files = _checksum_files(directory)
        if not files:
            continue
        lines = [f"{hashlib.sha256((directory / name).read_bytes()).hexdigest()}  {name}" for name in files]
        tmp = directory / "SHA256SUMS.tmp"
        tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
        tmp.replace(directory / "SHA256SUMS")
        written.append({"dir": rel, "files": len(files)})
    return written


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
    """校验关键工件目录 SHA256SUMS。

    四态（CM 轮）：`ok` 全通过 / `FAILED` 校验失败 / `FAILED` 存在但无清单 /
    `absent` 目录缺席（撤回或未生成，披露不判红）。「无清单」必须判红——
    把「没清单」读成「跳过」会让完整性声明在 0 份受检文件时也是绿的。
    """
    out: list[dict[str, Any]] = []
    for rel in _CHECKSUM_DIRS:
        d = REPO / rel
        if not d.is_dir():
            out.append({"dir": rel, "status": "absent", "detail": "目录缺席（已撤回或未生成）", "files": 0})
            continue
        files = _checksum_files(d)
        sums = d / "SHA256SUMS"
        if not sums.is_file():
            out.append(
                {
                    "dir": rel,
                    "status": "FAILED",
                    "detail": f"在盘 {len(files)} 个受检文件，但无 SHA256SUMS 清单",
                    "files": len(files),
                }
            )
            continue
        proc = subprocess.run(
            ["shasum", "-a", "256", "-c", "SHA256SUMS"],
            cwd=str(d),
            capture_output=True,
            text=True,
            timeout=300,
        )
        ok = proc.returncode == 0
        listed = len([ln for ln in (sums.read_text(encoding="utf-8").splitlines()) if ln.strip()])
        out.append(
            {
                "dir": rel,
                "status": "ok" if ok else "FAILED",
                "detail": ("全部通过" if ok else (proc.stdout or proc.stderr or "").strip().splitlines()[-1][:120]),
                "files": listed,
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
    ap.add_argument(
        "--write-checksums",
        action="store_true",
        help="先为在盘工件目录生成/刷新 SHA256SUMS 再校验（发布轮用；不改变校验口径）",
    )
    args = ap.parse_args()

    if args.write_checksums:
        for item in write_checksums():
            print(f"[repro] ▶ 清单已写 {item['dir']}（{item['files']} 个受检文件）", flush=True)

    commands = list(_L0_COMMANDS)
    if args.level == "l1":
        commands += _L1_COMMANDS

    sha = _git_sha()
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    results: list[dict[str, Any]] = []
    for name, cmd, _, probe in commands:
        print(f"[repro] ▶ {name}", flush=True)
        if probe is not None:
            skip_reason = probe()
            if skip_reason:
                print(f"[repro]   [SKIP] {skip_reason}", flush=True)
                results.append(
                    {"name": name, "command": " ".join(cmd), "status": "skipped", "rc": None, "tail": skip_reason}
                )
                continue
        rc, tail = _run(cmd)
        status = "ok" if rc == 0 else "FAILED"
        print(f"[repro]   {status}（rc={rc}）", flush=True)
        results.append({"name": name, "command": " ".join(cmd), "status": status, "rc": rc, "tail": tail})

    checksums = _verify_checksums()
    print("[repro] ▶ SHA256SUMS 校验", flush=True)
    for c in checksums:
        print(f"[repro]   {c['status']} {c['dir']}（{c.get('files', 0)} 文件）", flush=True)

    n_ok = sum(1 for r in results if r["status"] == "ok")
    n_total = len(results)
    n_skipped = sum(1 for r in results if r["status"] == "skipped")
    cs_ok = sum(1 for c in checksums if c["status"] == "ok")
    cs_fail = sum(1 for c in checksums if c["status"] == "FAILED")
    cs_absent = sum(1 for c in checksums if c["status"] == "absent")
    cs_files = sum(c.get("files", 0) for c in checksums if c["status"] == "ok")

    # 写 markdown 报告
    lines = [
        "# AITester 零 LLM 复算报告（REPRODUCTION_REPORT）",
        "",
        f"> 生成时间：{started}；git sha：`{sha}`；Python：{sys.version.split()[0]}；",
        f"> 层级：{args.level.upper()}；**{n_ok}/{n_total} 条命令通过**（{n_skipped} 条源工件缺席 [SKIP]）；"
        f"SHA256SUMS：{cs_ok} 个目录通过（{cs_files} 个受检文件）/ {cs_fail} 失败 / {cs_absent} 目录缺席。",
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
        if r["status"] == "skipped":
            mark, state = "⬜", "skipped（前提缺席，显式披露）"
        elif r["status"] == "ok":
            mark, state = "✅", f"rc={r['rc']}"
        else:
            mark, state = "❌", f"rc={r['rc']}"
        lines.append(f"| {r['name']} | {mark} {state} | {tail_md} |")

    lines += [
        "",
        "## 工件完整性（SHA256SUMS）",
        "",
        "| 目录 | 状态 | 受检文件 | 明细 |",
        "|---|---|---|---|",
    ]
    for c in checksums:
        mark = {"ok": "✅", "FAILED": "❌", "absent": "⬜"}[c["status"]]
        lines.append(f"| {c['dir']} | {mark} {c['status']} | {c.get('files', 0)} | {c['detail']} |")

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
        "summary": {
            "commands_ok": n_ok,
            "commands_total": n_total,
            "checksums_ok": cs_ok,
            "checksums_failed": cs_fail,
            "checksums_absent": cs_absent,
            "checksums_files": cs_files,
        },
        "commands": results,
        "checksums": checksums,
    }
    REPORT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    print(f"\n[repro] 报告 → {REPORT_MD}")
    print(f"[repro] JSON  → {REPORT_JSON}")
    print(
        f"[repro] 结论：{n_ok}/{n_total} 命令通过（{n_skipped} skipped）；"
        f"SHA256SUMS {cs_ok} 目录通过（{cs_files} 文件）/ {cs_fail} 失败 / {cs_absent} 缺席"
    )

    # v0.8.0：源工件缺席的 [SKIP] 支路不算失败——退出码由「FAILED 命令数 +
    # SHA256SUMS 失败数」决定（skip 是显式披露的可复算性边界，不是红灯）。
    n_failed = sum(1 for r in results if r["status"] == "FAILED")
    return 0 if (n_failed == 0 and cs_fail == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
