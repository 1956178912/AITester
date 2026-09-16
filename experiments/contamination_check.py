"""
SWE-bench 数据污染检测（2.1 数据污染风险应对）。

背景：
    部分前沿模型在 SWE-bench 上的高分可能来自训练数据污染——
    模型从训练语料中"背出"官方黄金补丁，而非真正定位根因。
    本模块提供静态重叠度检测：比较"系统生成的补丁"与"数据集官方
    黄金补丁"的 token 级 Jaccard 相似度，标记高度重叠的任务，
    供实验报告标注"结果可能受污染影响"。

设计口径（保守、可复算）：
    - 相似度 = Jaccard(生成补丁 token 集合, 黄金补丁 token 集合)，
      token 为小写化的单词/标识符切分（保留数字与下划线，丢弃 diff 头）；
    - 仅统计黄金补丁的"修改行"（+/- 行内容），忽略 diff 元数据；
    - 阈值分级：>= 0.85 高重叠（疑似逐字复现）、>= 0.6 中重叠（值得人工复核）；
    - 检测器为纯函数，不碰文件系统；输入由调用方（analyze_results /
      run_benchmark）从 raw 状态产物或结果 JSON 提取。
"""

from __future__ import annotations

import re
from typing import Any

# 重叠度分级阈值（保守口径，见模块 docstring）
HIGH_OVERLAP_THRESHOLD = 0.85
MEDIUM_OVERLAP_THRESHOLD = 0.6

# diff 头与元数据行（@@ hunk 头、文件路径行等不参与相似度计算）
_DIFF_META_PREFIXES = ("diff --git", "index ", "--- ", "+++ ", "@@", "new file", "deleted file")

# 切分 token：标识符（含下划线/点）与数字
_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*|\d+")


def extract_patch_tokens(patch_text: str) -> set[str]:
    """从 git diff 格式补丁中提取"修改行"的 token 集合（丢弃 diff 元数据）。

    修改行 = 以 + / - 开头（不含 +++/--- 文件头）的行；
    行内容去掉前缀后按标识符/数字切分并小写化。

    Args:
        patch_text: git diff 格式的补丁文本（可为空）。

    Returns:
        token 集合（去重，小写）；空补丁返回空集合。
    """
    tokens: set[str] = set()
    for line in (patch_text or "").splitlines():
        if not line or line.startswith(_DIFF_META_PREFIXES):
            continue
        if line[0] not in "+-":
            continue
        body = line[1:]
        # 忽略空白行残留
        for tok in _TOKEN_RE.findall(body):
            tokens.add(tok.lower())
    return tokens


def patch_overlap_score(generated_patch: str, golden_patch: str) -> float:
    """计算生成补丁与黄金补丁的 token 级 Jaccard 相似度。

    两个补丁均为空时返回 0.0（无重叠证据，非"完全相同"）。

    Args:
        generated_patch: 系统生成的补丁文本。
        golden_patch: 数据集官方黄金补丁文本。

    Returns:
        [0.0, 1.0] 的相似度分数。
    """
    gen_tokens = extract_patch_tokens(generated_patch)
    golden_tokens = extract_patch_tokens(golden_patch)
    if not gen_tokens or not golden_tokens:
        return 0.0
    intersection = len(gen_tokens & golden_tokens)
    union = len(gen_tokens | golden_tokens)
    return round(intersection / union, 4) if union else 0.0


def classify_overlap(score: float) -> str:
    """按阈值分级重叠度（high / medium / low）。

    Args:
        score: patch_overlap_score 的输出。

    Returns:
        "high"（>= 0.85，疑似逐字复现）/ "medium"（>= 0.6，建议人工复核）/ "low"。
    """
    if score >= HIGH_OVERLAP_THRESHOLD:
        return "high"
    if score >= MEDIUM_OVERLAP_THRESHOLD:
        return "medium"
    return "low"


def detect_contamination(
    details: list[dict[str, Any]],
    golden_patches: dict[str, str] | None = None,
) -> dict[str, Any]:
    """扫描结果 details，标记与黄金补丁高度重叠的任务。

    重叠度计算所需的两类输入（任一缺失则跳过该任务）：
    - 生成补丁：details[].patch（raw 状态产物经 run_benchmark 合并进结果）；
    - 黄金补丁：golden_patches[task_id]（SWE-bench 数据集官方 patch 字段）。

    Args:
        details: benchmark 结果 details 列表。
        golden_patches: task_id → 官方 patch 文本 的映射（可为 None，
            此时仅当 details 自带 golden_patch 字段时使用）。

    Returns:
        {"checked": 实际计算的任务数,
         "high": [task_id...], "medium": [task_id...],
         "scores": {task_id: {"score": float, "level": str}},
         "contaminated_tasks": [high + medium 的 task_id]}
    """
    scores: dict[str, dict[str, Any]] = {}
    high: list[str] = []
    medium: list[str] = []
    for row in details:
        task_id = str(row.get("task_id", ""))
        # 生成补丁：结果行 patch 字段（run_benchmark 0.9.19 起输出），
        # 旧结果兜底读 task_metadata.generated_patch
        generated = row.get("patch") or (row.get("task_metadata") or {}).get("generated_patch")
        # 黄金补丁：显式映射 > details 自带 golden_patch > task_metadata.golden_patch
        # （dataset_loader 0.9.19 起将 SWE-bench patch 字段存入 metadata）
        golden = (
            (golden_patches or {}).get(task_id)
            or row.get("golden_patch")
            or (row.get("task_metadata") or {}).get("golden_patch")
        )
        if not generated or not golden:
            continue
        score = patch_overlap_score(str(generated), str(golden))
        level = classify_overlap(score)
        scores[task_id] = {"score": score, "level": level}
        if level == "high":
            high.append(task_id)
        elif level == "medium":
            medium.append(task_id)
    return {
        "checked": len(scores),
        "high": high,
        "medium": medium,
        "scores": scores,
        "contaminated_tasks": high + medium,
    }


def render_contamination_section(report: dict[str, Any], baseline: str) -> list[str]:
    """把污染检测结果渲染为 Markdown 章节（无检测数据时返回空列表）。

    章节口径：列出 high/medium 任务、重叠度分数，并附"污染风险解读"
    提示（建议用 SWE-rebench 等抗污染基准交叉验证）。
    """
    if report.get("checked", 0) == 0:
        return []
    lines = [f"## 数据污染检测（2.1，基线 {baseline}）", ""]
    lines.append("生成补丁与数据集黄金补丁的 token 级 Jaccard 重叠度分级：")
    lines.append("")
    lines.append("| 级别 | 任务数 | 任务列表 |")
    lines.append("|------|--------|---------|")
    lines.append(
        f"| high（≥{HIGH_OVERLAP_THRESHOLD}） | {len(report.get('high', []))} | {', '.join(report.get('high', [])) or '—'} |"
    )
    lines.append(
        f"| medium（≥{MEDIUM_OVERLAP_THRESHOLD}） | {len(report.get('medium', []))} | {', '.join(report.get('medium', [])) or '—'} |"
    )
    lines.append("")
    if report.get("contaminated_tasks"):
        lines.append(
            "> 解读：high 级别任务疑似训练数据污染（逐字复现黄金补丁），"
            "相关成功率不可直接归因于系统能力；建议补充 SWE-rebench 等"
            "抗污染基准做交叉验证，并在论文中明确标注受污染影响的任务占比。"
        )
    else:
        lines.append("> 解读：未发现高/中重叠任务，本批次结果受数据污染影响的风险较低。")
    lines.append("")
    return lines
