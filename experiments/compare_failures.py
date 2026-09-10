"""
基线对比分析工具：定位"AITester 失败但 Plain LLM 成功"的任务，逐环节找根因（P0-2）。

背景：
    合成数据集实验中若 Plain LLM 成功率高于完整多智能体系统，需排查：
    - Planner 是否引入噪声（错误/保守的测试计划限制 Generator）；
    - Debugger 是否破坏正确代码（修复补丁引入新问题）；
    - Token 性价比（完整系统消耗远多于基线，性能不占优则性价比倒挂）。

使用方法：
    # 1. 先跑一次双基线 benchmark（--save-state 落盘环节级产物）
    python experiments/run_benchmark.py \\
        --dataset synthetic --baselines aitester,plain_llm \\
        --save-state -o experiments/results

    # 2. 用本工具对比
    python experiments/compare_failures.py \\
        --results experiments/results/benchmark_synthetic_<ts>.json \\
        --raw-dir experiments/results/raw \\
        --full-baseline aitester --base-baseline plain_llm \\
        --max-tasks 5 \\
        --report experiments/results/failure_analysis.md

输出：
    - 控制台摘要：翻转任务（base 成功 / full 失败）清单 + token 对比；
    - Markdown 报告：每个任务的环节级对比（测试计划/生成代码/诊断/补丁），
      并给出"差异环节"的自动判定提示（planner 噪声 / debugger 破坏 / 环境失败）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any


def load_summary(summary_path: str) -> dict[str, Any]:
    """加载 benchmark 汇总 JSON。"""
    with open(summary_path, encoding="utf-8") as f:
        return json.load(f)


def find_inverted_tasks(
    summary: dict[str, Any],
    full_baseline: str,
    base_baseline: str,
) -> list[dict[str, Any]]:
    """找出"基线成功、完整系统失败"的翻转任务。

    Args:
        summary: benchmark 汇总（含各基线 details）。
        full_baseline: 完整系统基线名（如 "aitester"）。
        base_baseline: 简单基线名（如 "plain_llm"）。

    Returns:
        翻转任务详情列表（每项含 task_id 与两个基线的结果子集）。
    """
    full_details = summary.get("results", {}).get(full_baseline, {}).get("details", [])
    base_details = summary.get("results", {}).get(base_baseline, {}).get("details", [])
    if not full_details or not base_details:
        return []

    full_by_task = {r.get("task_id"): r for r in full_details}
    base_by_task = {r.get("task_id"): r for r in base_details}

    inverted = []
    for task_id, base_result in base_by_task.items():
        full_result = full_by_task.get(task_id)
        if full_result is None:
            continue
        # 翻转：基线通过 且 完整系统未通过
        if base_result.get("passed") and not full_result.get("passed"):
            inverted.append(
                {
                    "task_id": task_id,
                    "full": full_result,
                    "base": base_result,
                }
            )
    return inverted


def load_state_artifact(raw_dir: str | None, task_id: str, baseline: str) -> dict[str, Any] | None:
    """加载环节级状态落盘文件（--save-state 产物），不存在时返回 None。"""
    if not raw_dir:
        return None
    path = os.path.join(raw_dir, task_id, f"{baseline}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _truncate(text: Any, limit: int = 600) -> str:
    """报告展示用的文本截断。"""
    if not text:
        return "（空）"
    s = str(text)
    return s if len(s) <= limit else s[:limit] + f"\n…（截断，全文 {len(s)} 字符）"


def _suspected_stage(full_result: dict[str, Any], base_result: dict[str, Any]) -> str:
    """基于结果字段的启发式"差异环节"判定（供人工排查参考）。

    判定规则（按优先级）：
    1. 完整系统的 error_category 为环境类（import/依赖）→ 环境问题，
       与智能体逻辑无关（需检查依赖隔离/自动安装）；
    2. 完整系统迭代 > 0 且最终失败 → Debugger 修复循环未收敛
       （可能补丁破坏了原本正确的代码）；
    3. 完整系统 0 迭代直接失败 → Generator/Planner 环节问题
       （测试计划噪声或生成质量问题）；
    4. 其余 → 需人工查看环节级产物。
    """
    category = (full_result.get("error_category") or "").lower()
    iterations = full_result.get("iterations", 0) or 0
    if "import" in category or "rate_limit" in category or "error" == category:
        return "环境/执行失败（缺依赖或 API 异常）——与 Planner/Debugger 逻辑无关"
    if iterations > 0:
        return "Debugger 修复循环未收敛（修复补丁可能破坏正确代码，或迭代次数不足）"
    if iterations == 0:
        return "Planner/Generator 环节（测试计划噪声或生成质量问题，首轮即失败）"
    return "需人工查看环节级产物"


def build_report(
    inverted: list[dict[str, Any]],
    full_baseline: str,
    base_baseline: str,
    raw_dir: str | None,
) -> str:
    """生成 Markdown 对比报告。"""
    lines: list[str] = [
        "# 基线对比失败分析报告",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 完整系统基线: `{full_baseline}`，简单基线: `{base_baseline}`",
        f"- 翻转任务数（{base_baseline} 通过 / {full_baseline} 失败）: {len(inverted)}",
        "",
    ]

    if not inverted:
        lines.append("未发现翻转任务（完整系统未落后于简单基线），无需排查。")
        return "\n".join(lines)

    # ── 总览表 + token 对比 ──────────────────────────────────────────────────
    lines += [
        "## 总览",
        "",
        f"| 任务 | {full_baseline} 结果 | {base_baseline} 结果 | 迭代 | token({full_baseline}) | token({base_baseline}) | 疑似环节 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]
    for item in inverted:
        task_id = item["task_id"]
        full_r, base_r = item["full"], item["base"]
        full_tokens = (full_r.get("token_usage") or {}).get("total_tokens", "?")
        base_tokens = (base_r.get("token_usage") or {}).get("total_tokens", "?")
        lines.append(
            f"| {task_id} | FAIL（{full_r.get('error_category', '?')}）"
            f" | PASS | {full_r.get('iterations', 0)} | {full_tokens} | {base_tokens}"
            f" | {_suspected_stage(full_r, base_r)} |"
        )

    # token 汇总
    full_total = sum((i["full"].get("token_usage") or {}).get("total_tokens", 0) for i in inverted)
    base_total = sum((i["base"].get("token_usage") or {}).get("total_tokens", 0) for i in inverted)
    lines += [
        "",
        f"**翻转任务 token 对比**：{full_baseline} 合计 {full_total}，{base_baseline} 合计 {base_total}"
        + (
            f"（完整系统多消耗 {full_total - base_total}，性价比倒挂需关注）"
            if full_total > base_total
            else "（完整系统消耗未倒挂）"
        ),
        "",
    ]

    # ── 逐任务环节级对比 ─────────────────────────────────────────────────────
    lines.append("## 逐任务环节级对比")
    for idx, item in enumerate(inverted, start=1):
        task_id = item["task_id"]
        full_r, base_r = item["full"], item["base"]
        lines += [
            "",
            f"### {idx}. {task_id}",
            "",
            f"- **{full_baseline} 诊断**: {_truncate(full_r.get('diagnosis') or '（无）', 300)}",
            f"- **{full_baseline} 错误类别**: {full_r.get('error_category') or '（无）'}；迭代 {full_r.get('iterations', 0)} 次",
            f"- **疑似环节**: {_suspected_stage(full_r, base_r)}",
        ]

        full_artifact = load_state_artifact(raw_dir, task_id, full_baseline)
        base_artifact = load_state_artifact(raw_dir, task_id, base_baseline)
        if full_artifact is None and base_artifact is None:
            lines.append("- 环节级产物缺失：请重跑 benchmark 时加 `--save-state`。")
            continue

        if full_artifact:
            lines += [
                "",
                f"**{full_baseline} 环节产物**：",
                "",
                f"- 测试计划: `{_truncate(json.dumps(full_artifact.get('test_plan'), ensure_ascii=False) if full_artifact.get('test_plan') else '（无 Planner）', 300)}`",
                f"- 生成测试代码: {_truncate(full_artifact.get('generated_test'), 400)}",
                f"- 修复补丁: {_truncate(full_artifact.get('patch') or '（未触发）', 400)}",
            ]
        if base_artifact:
            lines += [
                "",
                f"**{base_baseline} 环节产物**：",
                "",
                f"- 生成测试代码: {_truncate(base_artifact.get('generated_test'), 400)}",
            ]

        # RAG 检索指标（若启用）
        rag_stats = full_artifact.get("rag_stats") if full_artifact else None
        if rag_stats:
            lines.append(f"- RAG 检索记录: {json.dumps(rag_stats, ensure_ascii=False)}")

    lines += [
        "",
        "---",
        "",
        "**排查建议**（对应 P0-2 三个假设）：",
        "1. **Planner 噪声**：对比翻转任务的测试计划是否过于保守（边界用例缺失、预期值错误），",
        "   可用 `--baselines aitester` + 消融开关 `ENABLE_PLANNER=false` 重跑验证；",
        "2. **Debugger 破坏**：查看 patch 是否修改了基线本来正确的代码路径（对比基线生成代码与完整系统最终代码）；",
        "3. **性价比**：总览表 token 列对比，若完整系统 token 多且成功率不占优，",
        "   论文实验需报告 tokens/task 效率指标（本工具已内置）。",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="AITester 基线对比失败分析（P0-2 排查工具）")
    parser.add_argument("--results", required=True, help="benchmark 汇总 JSON 路径")
    parser.add_argument("--raw-dir", default=None, help="环节级产物目录（--save-state 输出，<dir>/<task_id>/<baseline>.json）")
    parser.add_argument("--full-baseline", default="aitester", help="完整系统基线名（默认 aitester）")
    parser.add_argument("--base-baseline", default="plain_llm", help="简单基线名（默认 plain_llm）")
    parser.add_argument("--max-tasks", type=int, default=5, help="最多分析多少个翻转任务（默认 5）")
    parser.add_argument("--report", default=None, help="Markdown 报告输出路径（默认打印到 stdout）")
    args = parser.parse_args()

    summary = load_summary(args.results)
    inverted = find_inverted_tasks(summary, args.full_baseline, args.base_baseline)
    # 按用户排查方法：先取 5 个逐个对比（完整报告仍包含全部翻转任务）
    analyzed = inverted[: args.max_tasks] if args.max_tasks > 0 else inverted
    report = build_report(analyzed, args.full_baseline, args.base_baseline, args.raw_dir)

    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"报告已写入: {args.report}（翻转任务 {len(inverted)} 个，详析 {len(analyzed)} 个）")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
