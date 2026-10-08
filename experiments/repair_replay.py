"""repair=0 围栏伪影存量重放（修复引擎批次 VII，ADR-0021，零 LLM）。

背景：
    E2 定案批次的 "repair 全线 0" 系**测量层伪影**——结果行 patch 字段
    保存 LLM JSON 原始值（项目约定可含 `````python`` 围栏 / ``python:``
    前缀，写盘链路负责清理），而 M1 独立裁决（repair_rate）直接消费该
    原始值。E2 存量工件实测 **274/274 带补丁行的 patch 字段以
    "python\\n" 围栏残留开头**，gold 测试在未清理文本上 100% 因
    NameError 失败 → repair_rate 被系统性压零（首测重放：原样 0/106
    通过，清理后 51/106 通过 = 48.1%）。

    本工具对存量批次工件按**修复后口径**（normalize_patch_text 清理，
    与写盘链路同源）重放 gold 测试，产出"原口径 vs 修正口径"的 repair
    对比报告——历史定案无需重跑即可勘误（E2 的 repair 次要终点、
    false_fix 分布、CPR/IDR 的 correct 分母均可由此重估）。

口径（保守、可复算）：
    - 重放对象：patch 非空 ∧ task_metadata.test_cases 非空的结果行；
    - 补丁后代码：整文件形态 → normalize_patch_text(patch) 直接作为模块
      代码（与修复后 _target_code_after_patch 同口径）；unified diff 形态
      → 存量行缺 instance_code 原码不可应用，记 "not_replayable_diff"
      （诚实降级，不臆造原码）；
    - 判定：gold test_cases 在补丁后代码上 pytest rc == 0 → correct；
      超时/IO 异常 → "unverifiable"（不计入分母，与 M1 None 口径一致）；
    - 原口径对照：结果行 patch_correct / repair_rate（历史伪影数字）。

用法：
    python -m experiments.repair_replay experiments/results/main_batch/ \
        --arm aitester [--out replay_report.md] [--timeout 60]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# 批次 JSON 的 diff 形态判别前缀（与 _m1_metrics._target_code_after_patch 同口径）
_DIFF_PREFIXES = ("diff --git", "@@", "---", "+++", "old ", "new ")


def _is_diff_form(patch: str) -> bool:
    return bool(patch) and patch.lstrip().startswith(_DIFF_PREFIXES)


def _iter_batch_files(results_dir: str | Path) -> list[Path]:
    """收集目录下全部批次 JSON（排序确定性：按文件名升序）。"""
    root = Path(results_dir)
    if root.is_file():
        return [root]
    return sorted(p for p in root.glob("benchmark_*.json") if p.is_file())


def _iter_rows(batch: dict[str, Any], arm: str) -> list[dict[str, Any]]:
    """取指定臂的 details 行（臂缺失 / 结构异常 → 空列表，保守跳过）。"""
    arm_data = (batch.get("results") or {}).get(arm) or {}
    details = arm_data.get("details") or []
    return [r for r in details if isinstance(r, dict)]


def replay_row(row: dict[str, Any], timeout: int = 60) -> dict[str, Any]:
    """单行重放判定（纯本地 pytest，零 LLM）。

    Returns:
        {"status": "correct" | "wrong_patch" | "not_replayable_diff" |
                   "unverifiable" | "skipped_no_material",
         "rc": int | None, "old_patch_correct": int | None}
    """
    from experiments._m1_metrics import _run_pytest_in_tmp

    old_correct = row.get("patch_correct")
    patch = str(row.get("patch") or "")
    meta = row.get("task_metadata") or {}
    test_cases = str(meta.get("test_cases") or "")
    if not patch.strip():
        return {"status": "skipped_no_material", "rc": None, "old_patch_correct": old_correct}
    if not test_cases.strip():
        return {"status": "skipped_no_material", "rc": None, "old_patch_correct": old_correct}
    if _is_diff_form(patch):
        # diff 形态补丁需要原码才能应用；存量行不含 instance_code → 不可重放
        return {"status": "not_replayable_diff", "rc": None, "old_patch_correct": old_correct}
    from src.tools.patch_applier import normalize_patch_text

    module_name = str(row.get("task_id", "")).split("__")[-1].replace("-", "_")[:50]
    new_code = normalize_patch_text(patch)
    # R27（2026-10-08 R2）：把任务 metadata 透传执行器，跨文件任务（is_cross_file）
    # 走伴生模块物化分支——否则 module_a/b/c 未物化 → gold 测试收集错误 rc=2 →
    # 跨文件行 repair 被系统性误判为 0（第三起测量伪影）。
    rc = _run_pytest_in_tmp(test_cases, new_code, module_name, timeout=timeout, task_metadata=meta)
    if rc is None:
        return {"status": "unverifiable", "rc": None, "old_patch_correct": old_correct}
    rc_val, _out, _err = rc
    return {
        "status": "correct" if rc_val == 0 else "wrong_patch",
        "rc": rc_val,
        "old_patch_correct": old_correct,
    }


def replay_batch(batch_path: Path, arm: str, timeout: int = 60) -> dict[str, Any]:
    """单批次文件重放汇总（确定性，无随机成分）。"""
    batch = json.loads(batch_path.read_text(encoding="utf-8"))
    rows = _iter_rows(batch, arm)
    counts: dict[str, int] = {}
    old_correct_total = 0
    old_correct_known = 0
    for row in rows:
        verdict = replay_row(row, timeout=timeout)
        counts[verdict["status"]] = counts.get(verdict["status"], 0) + 1
        if verdict.get("old_patch_correct") is not None:
            old_correct_known += 1
            old_correct_total += int(verdict["old_patch_correct"] or 0)
    replayed = counts.get("correct", 0) + counts.get("wrong_patch", 0)
    return {
        "file": batch_path.name,
        "arm": arm,
        "rows": len(rows),
        "counts": counts,
        "replayed": replayed,
        "replay_repair_rate": round(counts.get("correct", 0) / replayed, 4) if replayed else None,
        "old_patch_correct_total": old_correct_total,
        "old_correct_known_rows": old_correct_known,
    }


def build_report(results_dir: str | Path, arm: str, timeout: int = 60) -> str:
    """多批次重放对比报告（Markdown）。"""
    files = _iter_batch_files(results_dir)
    lines = [
        "# repair=0 围栏伪影存量重放报告（ADR-0021，批次 VII）",
        "",
        f"- 重放目录：`{results_dir}`（{len(files)} 个批次文件）",
        f"- 臂：`{arm}`",
        "- 修正口径：normalize_patch_text 清理后整文件补丁 × gold test_cases（pytest rc==0 → correct）；",
        "  原口径：结果行 patch_correct（历史伪影数字，未经清理执行）。",
        "",
        "| 批次文件 | 带补丁行 | 可重放 | 修正 correct | 修正 repair_rate | 原 correct（伪影） |",
        "|---|---|---|---|---|---|",
    ]
    total = {"replayed": 0, "correct": 0, "old": 0, "diff": 0, "skipped": 0, "unver": 0}
    for f in files:
        try:
            summary = replay_batch(f, arm, timeout=timeout)
        except Exception as e:  # —— 单文件异常不阻断整体重放
            lines.append(f"| {f.name} | 读取失败：{e} | — | — | — | — |")
            continue
        c = summary["counts"]
        total["replayed"] += summary["replayed"]
        total["correct"] += c.get("correct", 0)
        total["old"] += summary["old_patch_correct_total"]
        total["diff"] += c.get("not_replayable_diff", 0)
        total["skipped"] += c.get("skipped_no_material", 0)
        total["unver"] += c.get("unverifiable", 0)
        lines.append(
            f"| {summary['file']} | {summary['replayed'] + c.get('not_replayable_diff', 0) + c.get('skipped_no_material', 0)} "
            f"| {summary['replayed']} | {c.get('correct', 0)} | {summary['replay_repair_rate']} "
            f"| {summary['old_patch_correct_total']} |"
        )
    overall = round(total["correct"] / total["replayed"], 4) if total["replayed"] else None
    lines += [
        "",
        f"**合计**：可重放 {total['replayed']} 行，修正 correct = {total['correct']}"
        f"（修正 repair_rate = {overall}）；原口径 correct = {total['old']}（伪影归零）；"
        f"diff 形态不可重放 {total['diff']} 行、无 gold 材料 {total['skipped']} 行、"
        f"执行异常 {total['unver']} 行（不计入分母）。",
        "",
        "> 解读：原口径 repair=0 由 patch 字段围栏残留（'python\\n' 前缀）的测量伪影"
        "贡献；修正口径 = 与写盘链路同口径清理后的 gold 独立裁决。历史批次的"
        "repair / false_fix / CPR 分母应按本报告重估（ADR-0021 勘误注记）。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="repair=0 围栏伪影存量重放（ADR-0021）")
    parser.add_argument("results", help="批次 JSON 文件或所在目录")
    parser.add_argument("--arm", default="aitester", help="重放臂名（默认 aitester）")
    parser.add_argument("--out", default=None, help="报告写盘路径（缺省打印到 stdout）")
    parser.add_argument("--timeout", type=int, default=60, help="单行 pytest 超时（秒）")
    args = parser.parse_args(argv)
    report = build_report(args.results, args.arm, timeout=args.timeout)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8")
        print(f"重放报告已写入：{args.out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
