"""
6.2 改进：trace 可视化脚本（JSONL → HTML 时间线图）+ 回放能力。

背景：
    4.1/4.2 批次后，工作流每次运行产出 <task_uuid>.trace.jsonl（JSONL
    结构化追踪，记录各节点输入输出、决策路径、token 消耗、墙钟耗时）。
    但 trace 文件目前只能 grep/jq 人读，缺少可视化。本模块提供：
    - trace_to_html(trace_paths, out_path)：把一条或多条 trace JSONL 渲染为
      自包含 HTML（无外部依赖，纯内嵌 CSS/JS，可离线打开）：
        * 时间线图：按时间戳排列的节点执行序列（横向时间轴）
        * 每任务详情卡片：节点输入摘要、token 消耗、耗时、决策路径
        * 多任务对比视图（同 HTML 内可折叠展开各任务）
    - replay_trace(trace_path, state_factory)：从 trace JSONL 恢复执行
      能力——把 JSONL 里记录的节点输入重建为"重放剧本"（供离线分析、
      回归对比、RL 备料），**不重跑 LLM**（只重放静态决策路径）。

设计约束（零默认依赖，保守降级）：
    - 纯标准库 + json（不引入 rich/plotly 等重依赖）；
    - JSONL 缺失/损坏 → 返回空 HTML/空剧本（不抛异常，供 CLI 安全接线）；
    - HTML 输出自包含（可邮件附件/归档，无 CDN）。
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _parse_jsonl(path: str) -> list[dict[str, Any]]:
    """读 JSONL → list[dict]（损坏行跳过 + WARNING，保守不崩）。"""
    records: list[dict[str, Any]] = []
    p = Path(path)
    if not p.is_file():
        logger.warning("trace 文件不存在: %s", path)
        return records
    with open(p, encoding="utf-8") as fh:
        for i, raw_line in enumerate(fh):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    records.append(obj)
            except json.JSONDecodeError:
                logger.warning("trace 第 %d 行 JSON 损坏，跳过: %s...", i, line[:80])
    return records


# ── HTML 渲染 ────────────────────────────────────────────────────────────────

_CSS = """
body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:20px;background:#0f1117;color:#e6e6e6}
h1{font-size:1.4rem;margin:0 0 8px}
.meta{color:#888;font-size:.85rem;margin-bottom:16px}
.task{border:1px solid #2a2f3a;border-radius:10px;padding:14px;margin:12px 0;background:#161a22}
.task-head{display:flex;justify-content:space-between;align-items:center;cursor:pointer}
.task-head:hover{color:#8ab4ff}
.badge{padding:2px 10px;border-radius:12px;font-size:.75rem;font-weight:600}
.badge.pass{background:#1d3a2a;color:#7ce0a3}
.badge.fail{background:#3a1d1d;color:#e0a37c}
.timeline{margin:14px 0;overflow-x:auto}
.tl-row{display:flex;gap:2px;margin-bottom:6px}
.node{min-width:90px;padding:8px 6px;background:#1f2430;border:1px solid #2a2f3a;border-radius:6px;font-size:.72rem;text-align:center}
.node .t{color:#888;font-size:.65rem;margin-top:2px}
.node .tok{color:#e0a37c;font-size:.65rem}
.decision{margin-top:8px;font-size:.75rem;color:#888}
.decision code{color:#8ab4ff}
.detail{margin-top:10px;background:#0f1117;border-radius:6px;padding:10px;font-size:.75rem;display:none}
.detail.show{display:block}
.detail pre{margin:4px 0;white-space:pre-wrap;font-size:.72rem;color:#ccc}
.summary{background:#161a22;border:1px solid #2a2f3a;border-radius:10px;padding:14px;margin-bottom:16px}
.summary span{margin-right:18px}
"""

_JS = """
function toggle(id){var d=document.getElementById(id);if(d){d.classList.toggle('show');}}
function expandAll(v){document.querySelectorAll('.detail').forEach(function(d){d.classList.toggle('show',v);});}
"""


def _esc(s: Any) -> str:
    """HTML 转义。"""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def trace_to_html(trace_paths: list[str], out_path: str, title: str = "AITester Trace Timeline") -> int:
    """把一条或多条 trace JSONL 渲染为自包含 HTML 时间线图。

    Args:
        trace_paths: trace JSONL 文件路径列表。
        out_path: 输出 HTML 文件路径（目录不存在时自动创建）。
        title: 页面标题。

    Returns:
        渲染的任务数（0 = 无有效 trace，仍写空 HTML）。

        时间线图：每个任务一张卡片，卡片内按节点时间戳排序的横向时间轴
        （node chip 序列：节点名 + 耗时 + token 消耗 + 决策），
        卡片可展开看各节点原始记录（pre 块 JSONL 原文）。
    """
    all_records: list[tuple[str, list[dict[str, Any]]]] = []
    for tp in trace_paths:
        recs = _parse_jsonl(tp)
        all_records.append((os.path.basename(tp), recs))

    task_cards: list[str] = []
    total_tasks = 0
    total_nodes = 0
    passed = 0
    failed = 0
    for fname, recs in all_records:
        if not recs:
            continue
        total_tasks += 1
        total_nodes += len(recs)
        # 按时间戳排序（ISO 时间戳字符串比较即可）
        recs_sorted = sorted(recs, key=lambda r: str(r.get("ts", r.get("timestamp", ""))))
        passed_flag = any(r.get("event") == "task_end" and r.get("test_passed") for r in recs_sorted)
        if passed_flag:
            passed += 1
        else:
            failed += 1

        # 节点时间轴（只取 node 类事件，过滤 task_start/end）
        node_recs = [
            r
            for r in recs_sorted
            if r.get("event")
            in ("node_start", "node_end", "planner", "executor", "debugger", "patch_applier", "generator")
        ]
        chips: list[str] = []
        for r in node_recs:
            node = _esc(r.get("node") or r.get("event") or "?")
            dur = r.get("duration_ms")
            dur_s = f"{dur}ms" if dur is not None else ""
            tok = r.get("token_delta") or r.get("tokens")
            tok_s = f"{tok} tok" if tok else ""
            decision = r.get("decision", "")
            chip_cls = "node"
            if decision in ("PASS", "done", "written"):
                chip_cls += " pass-node"
            elif decision in ("FAIL", "rejected"):
                chip_cls += " fail-node"
            chips.append(
                f'<div class="{chip_cls}" title="{_esc(json.dumps({k: r.get(k) for k in ("node", "decision", "duration_ms", "token_delta")}, ensure_ascii=False))}">'
                f"<b>{node}</b>{f'<br><code>{_esc(decision)}</code>' if decision else ''}"
                f"{f'<div class=tok>{_esc(tok_s)}</div>' if tok_s else ''}"
                f"{f'<div class=t>{_esc(dur_s)}</div>' if dur_s else ''}</div>"
            )
        timeline_html = (
            '<div class="timeline"><div class="tl-row">' + "".join(chips) + "</div></div>"
            if chips
            else '<div class="timeline"><i style="color:#555">无节点记录</i></div>'
        )
        # 原始记录详情（折叠）
        raw_lines = "\n".join(json.dumps(r, ensure_ascii=False) for r in recs_sorted)
        detail_html = f"<pre>{_esc(raw_lines)}</pre>"

        badge = "pass" if passed_flag else "fail"
        label = "PASS" if passed_flag else "FAIL"
        # U10（2026-10-05 系统性审查落地）：DOM id 白名单净化——此前仅把
        # "." 替换为 "_"，task_id/文件名含引号（'、"）或其他字符时会逃出
        # onclick 字符串/属性边界注入 HTML/JS。现只保留 [A-Za-z0-9_-]，
        # 其余一律替换为 "_"（显示文本仍走 _esc(fname)）。
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", fname)
        task_cards.append(
            f'<div class="task"><div class="task-head" onclick="toggle(\'{safe_id}\')">'
            f"<b>{_esc(fname)}</b> "
            f'<span class="badge {badge}">{label}</span></div>'
            f"{timeline_html}"
            f'<div class="decision">节点数: {len(node_recs)}</div>'
            f'<div id="{safe_id}" class="detail">{detail_html}</div></div>'
        )

    summary_html = (
        f'<div class="summary">'
        f"<span><b>任务数</b>: {total_tasks}</span>"
        f"<span><b>通过</b>: {passed}</span>"
        f"<span><b>失败</b>: {failed}</span>"
        f"<span><b>节点记录</b>: {total_nodes}</span>"
        f'<button style="float:right" onclick="expandAll(true)">展开全部</button>'
        f'<button style="float:right;margin-right:8px" onclick="expandAll(false)">折叠全部</button>'
        f"</div>"
    )
    html = (
        f"<!DOCTYPE html><html><head><meta charset=utf-8>"
        f"<title>{_esc(title)}</title>"
        f"<style>{_CSS}</style></head><body>"
        f"<h1>{_esc(title)}</h1>"
        f'<div class="meta">自包含 HTML（无外部依赖），可离线打开 / 邮件附件 / 归档</div>'
        f"{summary_html}"
        f"{''.join(task_cards)}"
        f"<script>{_JS}</script></body></html>"
    )

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(html, encoding="utf-8")
    logger.info("trace 可视化写入 %s（%d 任务）", out_p, total_tasks)
    return total_tasks


# ── 回放（replay）能力 ────────────────────────────────────────────────────────

_REPLAY_EVENT_KEYS = ("event", "node", "decision", "iteration", "ts")


def replay_trace(
    trace_path: str,
    state_factory: Callable[[], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """从 trace JSONL 恢复"重放剧本"（静态决策路径，不重跑 LLM）。

    Args:
        trace_path: trace JSONL 文件路径。
        state_factory: 初始 state 工厂（可选；默认空 dict）。回放时把
            trace 里记录的节点更新合并进 state（模拟工作流状态演化），
            供离线分析 / 回归对比 / RL 备料。

    Returns:
        重放剧本 list：每步 = {step, event, node, decision, iteration,
        state_snapshot}（state_snapshot 为回放该步后的 state 深拷贝）。
        损坏/缺失 trace 返回 []（保守降级）。
    """
    recs = _parse_jsonl(trace_path)
    if not recs:
        return []
    state: dict[str, Any] = dict(state_factory()) if state_factory else {}
    steps: list[dict[str, Any]] = []
    for i, r in enumerate(recs):
        # 把 trace 里记录的节点输出合并进 state（模拟状态演化）
        for k in ("test_passed", "iteration", "error_category", "coverage_report"):
            if k in r:
                state[k] = r[k]
        snapshot = dict(state)
        steps.append(
            {
                "step": i,
                "event": r.get("event"),
                "node": r.get("node"),
                "decision": r.get("decision"),
                "iteration": r.get("iteration"),
                "ts": r.get("ts"),
                "state_snapshot": snapshot,
            }
        )
    return steps
