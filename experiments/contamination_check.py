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

2.1 改进：多维度污染检测
    在 token 级 Jaccard（_detect_structural_jaccard）之外，增加两个维度的
    相似度信号，三者取最严重者作为最终风险等级：
    1. 结构级：AST 语句骨架相似度（_detect_ast_skeleton_similarity）——
       比较两补丁修改行的"语句类型序列"（如 Expr/Assign/Compare），
       用最长公共子序列（LCS）比率衡量结构相似度。捕获"换了变量名但
       控制流/语句结构相同"的复制（token Jaccard 会因改名而低估）；
    2. 语义级：标识符词频余弦（_detect_semantic_cosine）——对 token 词袋
       做余弦相似度。相比 Jaccard（只数交并比）保留"词频权重"信息，
       与 CodeBERT 嵌入余弦同方向但零依赖（纯标准库，可复算）。
       若系统装有 sklearn 或 CodeBERT（可选依赖），可在此接入真实
       嵌入余弦（_embed_code 钩子，默认返回 None 表示未接入）。

    综合风险等级（_combined_risk_level）：
        - 任一维度 >= HIGH 阈值 → "high"；
        - 任一维度 >= MEDIUM 阈值 → "medium"；
        - 其余 → "low"。
    每个任务额外输出 risk_level 字段（high/medium/low），供汇总统计时
    区分"含污染样本"与"不含污染样本"的结果。
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


# ─── 2.1 改进：多维度污染检测（结构级 + 语义级）──────────────────────────────


def _extract_changed_line_tokens(patch_text: str) -> list[list[str]]:
    """提取补丁每个修改行的 token 序列（保留行边界，供结构/语义分析）。

    与 extract_patch_tokens 同源（丢弃 diff 元数据），但保留"行 → token 列表"
    的结构，供 AST 骨架与词频余弦使用。
    """
    lines_tokens: list[list[str]] = []
    for line in (patch_text or "").splitlines():
        if not line or line.startswith(_DIFF_META_PREFIXES):
            continue
        if line[0] not in "+-":
            continue
        body = line[1:]
        lines_tokens.append(_TOKEN_RE.findall(body))
    return lines_tokens


def _extract_statement_skeleton(patch_text: str) -> list[str]:
    """提取补丁修改代码的 AST 语句类型骨架（结构级相似度用）。

    对补丁修改行做 ast.parse（拼接成可解析片段；失败时退回逐行 tokenize），
    收集每个语句的"顶层类型 + 关键子类型"序列（如 ["Expr:Compare", "Assign", ...]）。
    该骨架对变量名不敏感（只看语句结构），能捕获"换了标识符但控制流/语句
    结构相同"的复制——token Jaccard 会因改名而低估这类污染。
    """
    import ast
    import io
    import tokenize

    changed = [line for line in _extract_changed_line_tokens(patch_text)]
    # 把 token 拼回近似代码（丢失缩进，但 ast.parse 只需序列类型）
    pseudo = " ".join(" ".join(toks) for toks in changed)
    try:
        tree = ast.parse(pseudo)
        skeleton = []
        for node in tree.body:
            kind = type(node).__name__
            # 取语句内的关键子节点类型（进一步细粒度区分）
            sub = []
            for child in ast.walk(node):
                if child is not node and type(child).__name__ in (
                    "Compare",
                    "BoolOp",
                    "BinOp",
                    "Call",
                    "If",
                    "For",
                    "While",
                ):
                    sub.append(type(child).__name__)
                    if len(sub) >= 2:
                        break
            skeleton.append(f"{kind}:{','.join(sub)}" if sub else kind)
        return skeleton
    except (SyntaxError, ValueError):
        # 解析失败退回 tokenize 骨架（更粗，但仍比纯 token Jaccard 保守）
        skeleton = []
        try:
            _stream = io.StringIO(pseudo)
            tokens = tokenize.generate_tokens(_stream.readline)
            for _type, _token, _pos, _end, _line in tokens:
                if _type == tokenize.NAME:
                    skeleton.append("NAME")
                elif _type == tokenize.OP:
                    skeleton.append(f"OP:{_token}")
                elif _type == tokenize.NUMBER:
                    skeleton.append("NUMBER")
        except (tokenize.TokenError, IndentationError, SyntaxError):
            return []
        return skeleton


def _lcs_ratio(seq_a: list, seq_b: list) -> float:
    """最长公共子序列（LCS）比率：LCS 长度 / max(len)（结构相似度，0.0-1.0）。"""
    if not seq_a or not seq_b:
        return 0.0
    # 简单 DP（骨架序列通常很短，O(n*m) 可接受）
    n, m = len(seq_a), len(seq_b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq_a[i - 1] == seq_b[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[n][m]
    return round(lcs_len / max(n, m), 4)


def _token_bag_cosine(tokens_a: list[str], tokens_b: list[str]) -> float:
    """token 词袋余弦相似度（语义级保守代理，纯标准库实现）。

    对两补丁修改行的小写 token 做词袋统计，计算余弦相似度。相比 Jaccard
    保留"词频权重"（某标识符出现多次 → 权重高），是"嵌入余弦"的零依赖
    近似——与 CodeBERT 嵌入余弦同方向但无需模型。
    """
    if not tokens_a or not tokens_b:
        return 0.0
    from collections import Counter

    bag_a = Counter(t.lower() for t in tokens_a)
    bag_b = Counter(t.lower() for t in tokens_b)
    common_keys = set(bag_a) & set(bag_b)
    dot = sum(bag_a[k] * bag_b[k] for k in common_keys)
    norm_a = sum(v * v for v in bag_a.values()) ** 0.5
    norm_b = sum(v * v for v in bag_b.values()) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return round(dot / (norm_a * norm_b), 4)


def _embed_code(code: str) -> list[float] | None:
    """可选钩子：返回代码的语义嵌入向量（如 CodeBERT）。

    默认实现返回 None（表示未接入嵌入模型），此时 _detect_semantic_cosine
    退回 token 词袋余弦。若系统装有 sentence-transformers / 本地 CodeBERT，
    可替换本函数返回真实嵌入向量，与黄金补丁嵌入做余弦。

    设计说明：本钩子刻意不 import 任何嵌入库（保持 experiments 包零外部
    依赖、可复算）；接入方在自己的 site-packages 里 monkeypatch 本函数
    或提供 embedding_utils 模块即可，未接入时全程走词袋余弦保守代理。
    """
    # 默认未接入嵌入模型（保持零外部依赖、可复算）
    return None


def patch_semantic_similarity(generated_patch: str, golden_patch: str) -> dict[str, float | None]:
    """多维度相似度信号（2.1 改进）。

    Returns:
        {"jaccard": float, "structural": float | None,
         "semantic": float | None}
        structural = AST 骨架 LCS 比率；semantic = 嵌入余弦（接入时）
        或 token 词袋余弦（未接入时的保守代理）；任一计算失败对应键为 None。
    """
    jaccard = patch_overlap_score(generated_patch, golden_patch)
    # 结构级：AST 语句骨架 LCS
    skel_a = _extract_statement_skeleton(generated_patch)
    skel_b = _extract_statement_skeleton(golden_patch)
    structural = _lcs_ratio(skel_a, skel_b) if skel_a and skel_b else None
    # 语义级：嵌入余弦（接入时）或 token 词袋余弦（默认保守代理）
    toks_a = [t for line_toks in _extract_changed_line_tokens(generated_patch) for t in line_toks]
    toks_b = [t for line_toks in _extract_changed_line_tokens(golden_patch) for t in line_toks]
    emb_a = _embed_code(" ".join(toks_a))
    emb_b = _embed_code(" ".join(toks_b))
    if emb_a is not None and emb_b is not None:
        # 接入嵌入模型时：向量余弦（embedding_utils 由接入方提供，缺失时退回词袋）
        semantic = None
        try:
            from src.utils.embedding_utils import cosine_similarity

            semantic = round(float(cosine_similarity(list(emb_a), list(emb_b))), 4)
        except Exception:
            semantic = None
        if semantic is None:
            semantic = _token_bag_cosine(toks_a, toks_b)
    else:
        semantic = _token_bag_cosine(toks_a, toks_b)
    return {"jaccard": jaccard, "structural": structural, "semantic": semantic}


def _combined_risk_level(similarities: dict[str, float | None]) -> str:
    """综合多维度相似度得出污染风险等级（取最严重维度）。

    规则：任一维度（jaccard/structural/semantic，非 None）>= HIGH 阈值 → high；
    否则任一 >= MEDIUM → medium；其余 low。
    """
    values = [v for v in similarities.values() if v is not None]
    if not values:
        return "low"
    if any(v >= HIGH_OVERLAP_THRESHOLD for v in values):
        return "high"
    if any(v >= MEDIUM_OVERLAP_THRESHOLD for v in values):
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

    2.1 改进：每个任务同时计算"token Jaccard + 结构骨架 LCS + 语义词袋余弦"
    三个维度的相似度，综合得出 risk_level（high/medium/low），供汇总时
    区分"含污染样本"（high/medium）与"不含污染样本"（low/未检测）的
    成功率。旧 JSON 仅 patch 字段可用时自动退化为单维度 Jaccard。

    Args:
        details: benchmark 结果 details 列表。
        golden_patches: task_id → 官方 patch 文本 的映射（可为 None，
            此时仅当 details 自带 golden_patch 字段时使用）。

    Returns:
        {"checked": 实际计算的任务数,
         "high": [task_id...], "medium": [task_id...],
         "low": [task_id...],
         "scores": {task_id: {"score": float, "level": str,
                                "similarities": {...}, "risk_level": str}},
         "contaminated_tasks": [high + medium 的 task_id],
         "clean_tasks": [low 的 task_id],
         "contamination_summary": {"contaminated": n, "clean": n,
                                    "contaminated_success_rate": float | None,
                                    "clean_success_rate": float | None,
                                    "delta": float | None}}
    """
    scores: dict[str, dict[str, Any]] = {}
    high: list[str] = []
    medium: list[str] = []
    low: list[str] = []
    contaminated_success = 0
    contaminated_total = 0
    clean_success = 0
    clean_total = 0
    for row in details:
        task_id = str(row.get("task_id", ""))
        # 生成补丁：结果行 patch 字段（run_benchmark 0.1 起输出），
        # 旧结果兜底读 task_metadata.generated_patch
        generated = row.get("patch") or (row.get("task_metadata") or {}).get("generated_patch")
        # 黄金补丁：显式映射 > details 自带 golden_patch > task_metadata.golden_patch
        # （dataset_loader 0.1 起将 SWE-bench patch 字段存入 metadata）
        golden = (
            (golden_patches or {}).get(task_id)
            or row.get("golden_patch")
            or (row.get("task_metadata") or {}).get("golden_patch")
        )
        if not generated or not golden:
            continue
        # 2.1 改进：多维度相似度（Jaccard + 结构骨架 LCS + 语义词袋余弦）
        sims = patch_semantic_similarity(str(generated), str(golden))
        score = sims.get("jaccard", 0.0)  # 主分（历史口径：Jaccard 作为 score）
        level = classify_overlap(score)
        risk_level = _combined_risk_level(sims)
        # 综合风险（多维度取最严）可能高于单维度 Jaccard 等级
        if risk_level == "high" and level == "low":
            level = "high"
        elif risk_level == "medium" and level == "low":
            level = "medium"
        scores[task_id] = {"score": score, "level": level, "similarities": sims, "risk_level": risk_level}
        passed = bool(row.get("passed"))
        if level in ("high", "medium"):
            (high if level == "high" else medium).append(task_id)
            contaminated_total += 1
            if passed:
                contaminated_success += 1
        else:
            low.append(task_id)
            clean_total += 1
            if passed:
                clean_success += 1
    contaminated_n = len(high) + len(medium)
    clean_n = len(low)
    contaminated_rate = round(contaminated_success / contaminated_n, 4) if contaminated_n else None
    clean_rate = round(clean_success / clean_n, 4) if clean_n else None
    delta = (
        round(contaminated_rate - clean_rate, 4) if (contaminated_rate is not None and clean_rate is not None) else None
    )
    return {
        "checked": len(scores),
        "high": high,
        "medium": medium,
        "low": low,
        "scores": scores,
        "contaminated_tasks": high + medium,
        "clean_tasks": low,
        "contamination_summary": {
            "contaminated": contaminated_n,
            "clean": clean_n,
            "contaminated_success_rate": contaminated_rate,
            "clean_success_rate": clean_rate,
            "delta": delta,
        },
    }


def render_contamination_section(report: dict[str, Any], baseline: str) -> list[str]:
    """把污染检测结果渲染为 Markdown 章节（无检测数据时返回空列表）。

    章节口径：列出 high/medium/low 任务、重叠度分数（含多维度相似度），
    并附"污染风险解读"提示（建议用 SWE-rebench 等抗污染基准交叉验证）。
    2.1 改进：额外输出"含污染样本 vs 不含污染样本"的成功率对比
    （contamination_summary），直观呈现污染对结果的影响幅度。
    """
    if report.get("checked", 0) == 0:
        return []
    lines = [f"## 数据污染检测（2.1，基线 {baseline}）", ""]
    lines.append("生成补丁与数据集黄金补丁的多维度重叠度分级（token Jaccard + 结构骨架 LCS + 语义词袋余弦）：")
    lines.append("")
    lines.append("| 级别 | 任务数 | 任务列表 |")
    lines.append("|------|--------|---------|")
    lines.append(
        f"| high（≥{HIGH_OVERLAP_THRESHOLD}） | {len(report.get('high', []))} | {', '.join(report.get('high', [])) or '—'} |"
    )
    lines.append(
        f"| medium（≥{MEDIUM_OVERLAP_THRESHOLD}） | {len(report.get('medium', []))} | {', '.join(report.get('medium', [])) or '—'} |"
    )
    low_tasks = report.get("low", [])
    lines.append(
        f"| low（<{MEDIUM_OVERLAP_THRESHOLD}） | {len(low_tasks)} | {(', '.join(low_tasks[:10]) + ('…' if len(low_tasks) > 10 else '')) or '—'} |"
    )
    lines.append("")
    # 2.1 改进：含污染 vs 不含污染的成功率对比
    summary = report.get("contamination_summary") or {}
    if summary:
        lines.append("### 含污染样本 vs 不含污染样本（成功率对比）")
        lines.append("")
        lines.append("| 分组 | 任务数 | 成功率 |")
        lines.append("|------|--------|--------|")
        lines.append(
            f"| 含污染（high/medium） | {summary.get('contaminated', 0)} | {summary.get('contaminated_success_rate')} |"
        )
        lines.append(f"| 不含污染（low/未检测） | {summary.get('clean', 0)} | {summary.get('clean_success_rate')} |")
        lines.append("")
        delta = summary.get("delta")
        if delta is not None:
            if abs(delta) >= 0.2:
                lines.append(
                    f"> 解读：含污染组成功率比不含污染组高 {delta:.2f}（≥0.2），"
                    "提示本批次结果可能受训练数据污染影响——高重叠任务疑似"
                    '"背出"黄金补丁而非真正定位根因。论文中应把含污染样本'
                    "单独标注，并建议补充 SWE-rebench（抗污染基准）交叉验证。"
                )
            else:
                lines.append(
                    f"> 解读：两组成功率差异 {delta:.2f}（<0.2），本批次结果"
                    "受数据污染影响较小；含污染任务的通过更可能来自真实修复能力。"
                )
        lines.append("")
    if report.get("contaminated_tasks"):
        lines.append(
            "> 注：high 级别任务疑似训练数据污染（逐字复现黄金补丁），"
            "相关成功率不可直接归因于系统能力；建议补充 SWE-rebench 等"
            "抗污染基准做交叉验证，并在论文中明确标注受污染影响的任务占比。"
        )
    else:
        lines.append("> 解读：未发现高/中重叠任务，本批次结果受数据污染影响的风险较低。")
    lines.append("")
    return lines


# ─── 2.1 改进：SWE-rebench（抗污染基准）注册表 ────────────────────────────────
# SWE-rebench 是带抗污染特性的 SWE-bench 补充基准（任务在公开训练截止之后
# 构建，从源头降低"背出黄金补丁"风险）。本注册表列出可用的抗污染基准
# 元数据，供实验报告自动标注"已用抗污染基准交叉验证"。
# 新增抗污染基准（如 SWE-bench-Live / Re-SWE-bench）时在此登记即可，
# 渲染层会列出全部已注册基准及其抗污染机制说明。
CONTAMINATION_RESISTANT_BENCHMARKS: dict[str, dict[str, Any]] = {
    "swe-rebench": {
        "display_name": "SWE-rebench",
        "resistance_mechanism": (
            "任务在 LLM 训练数据公开截止之后构建，从源头降低训练污染风险；"
            "建议与主基准（如 SWE-bench Verified）成对报告，取抗污染基准的"
            '结果作为"无污染"口径，主基准结果作"含污染风险"口径。'
        ),
        "recommended_pairing": "swe-bench-verified",
    },
    "swe-bench-live": {
        "display_name": "SWE-bench Live",
        "resistance_mechanism": (
            "持续新增 issue（滚动更新），任何已发布模型的训练截止都早于最新任务，"
            '天然抗污染；适合作为"最新能力"口径补充。'
        ),
        "recommended_pairing": "swe-bench",
    },
}


def render_resistant_benchmark_section() -> list[str]:
    """渲染\"抗污染基准交叉验证建议\"章节（列出已注册的抗污染基准）。"""
    if not CONTAMINATION_RESISTANT_BENCHMARKS:
        return []
    lines = ["## 抗污染基准交叉验证建议（2.1）", ""]
    lines.append("| 基准 | 抗污染机制 | 建议配对基准 |")
    lines.append("|------|-----------|-------------|")
    lines.extend(
        f"| {meta['display_name']} | {meta['resistance_mechanism']} | {meta.get('recommended_pairing', '—')} |"
        for meta in CONTAMINATION_RESISTANT_BENCHMARKS.values()
    )
    lines.append("")
    lines.append(
        '> 用法：在实验报告中成对展示"主基准 + 抗污染基准"的成功率，'
        '并标注主基准结果中"含污染样本"占比（见上方 contamination_summary）。'
    )
    lines.append("")
    return lines
