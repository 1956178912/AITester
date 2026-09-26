"""
任务复杂度评估器（P0 1.2 模型路由按任务复杂度分级）。

设计口径：
    模型固定为 Agnes 3.0-flash（同一 provider 的多 LLM_N 实例），按任务复杂度
    路由到不同复杂度档位（低档 = 简单任务省钱，高档 = 复杂仓库级任务用更多
    上下文/更多迭代）。复杂度分数由以下维度加权计算：

        score = w_lines * min(1.0, lines / _LINES_NORM)
              + w_files * min(1.0, files / _FILES_NORM)
              + w_deps  * min(1.0, deps  / _DEPS_NORM)
              + w_cc    * min(1.0, cc    / _CC_NORM)

    四维度各自归一化到 [0, 1] 后加权求和，得分范围 [0, 1]：
        - score < 0.35  → 简单任务（单函数 / 低复杂度，低成本档）
        - 0.35 <= score < 0.7 → 中等任务（多函数 / 中等依赖，中成本档）
        - score >= 0.7  → 复杂任务（仓库级 / 多文件 / 高圈复杂度，高成本档）

    档位决定"路由标签"（complexity_class），供 APIManager 选择对应
    LLM 实例（同模型不同 provider 端点，或同 provider 不同 cost_weight）。
    模型名不变（仍为 agnes-3.0-flash），变的是实例档位与上下文预算。

环境变量：
    MODEL_ROUTING_STRATEGY: "complexity_aware"（默认）| "fixed"（历史口径，
        忽略复杂度始终用默认档位）
    ROUTING_COMPLEXITY_LINES_NORM / _FILES_NORM / _DEPS_NORM / _CC_NORM:
        各维度归一化基准（默认 500 / 5 / 20 / 25）
"""

from __future__ import annotations

import ast
import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ─── 归一化基准（环境变量可覆盖）──────────────────────────────────────────
_LINES_NORM_DEFAULT = 500  # 500 行以上视为"大文件"维度满分
_FILES_NORM_DEFAULT = 5  # 5 个模块以上视为"多文件"维度满分
_DEPS_NORM_DEFAULT = 20  # 20 个依赖以上视为"重依赖"维度满分
_CC_NORM_DEFAULT = 25  # 圈复杂度 25 以上视为"高复杂度"维度满分


def _norm_lines() -> float:
    raw = os.getenv("ROUTING_COMPLEXITY_LINES_NORM", "").strip()
    try:
        return float(raw) if raw else _LINES_NORM_DEFAULT
    except ValueError:
        return _LINES_NORM_DEFAULT


def _norm_files() -> float:
    raw = os.getenv("ROUTING_COMPLEXITY_FILES_NORM", "").strip()
    try:
        return float(raw) if raw else _FILES_NORM_DEFAULT
    except ValueError:
        return _FILES_NORM_DEFAULT


def _norm_deps() -> float:
    raw = os.getenv("ROUTING_COMPLEXITY_DEPS_NORM", "").strip()
    try:
        return float(raw) if raw else _DEPS_NORM_DEFAULT
    except ValueError:
        return _DEPS_NORM_DEFAULT


def _norm_cc() -> float:
    raw = os.getenv("ROUTING_COMPLEXITY_CC_NORM", "").strip()
    try:
        return float(raw) if raw else _CC_NORM_DEFAULT
    except ValueError:
        return _CC_NORM_DEFAULT


@dataclass(frozen=True)
class ComplexityScore:
    """任务复杂度评分结果。

    score: [0, 1] 综合复杂度分数（四维度加权归一化）。
    complexity_class: "simple" | "medium" | "complex"。
    breakdown: 各维度归一化分量（供日志 / trace 分析）。
    """

    score: float
    complexity_class: str
    breakdown: dict[str, float] = field(default_factory=dict)


def routing_strategy() -> str:
    """当前路由策略（MODEL_ROUTING_STRATEGY，默认 complexity_aware）。"""
    return os.getenv("MODEL_ROUTING_STRATEGY", "complexity_aware").strip().lower()


def routing_enabled() -> bool:
    """复杂度感知路由是否启用（strategy=complexity_aware 时 True）。"""
    return routing_strategy() == "complexity_aware"


def count_imports(source_code: str) -> int:
    """统计模块级 import 数量（Import + ImportFrom，含 from X import Y）。"""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return 0
    count = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            count += 1
    return count


def compute_complexity_score(
    lines: int,
    num_files: int = 1,
    num_deps: int = 0,
    cyclomatic_complexity: int = 1,
) -> ComplexityScore:
    """计算任务复杂度分数（P0 1.2）。

    四维度归一化到 [0, 1] 后等权（各 0.25）求和：
        score = 0.25 * (lines/L_norm + files/F_norm + deps/D_norm + cc/CC_norm) / 4 * 4
        （实际公式：各维度 min(1, x/norm) 求平均）

    复杂度分档：
        < 0.35  → "simple"  （单函数 / 低复杂度，低成本档：省 token 档路由）
        < 0.70  → "medium"  （多函数 / 中等依赖，中成本档）
        >= 0.70 → "complex" （仓库级 / 多文件 / 高圈复杂度，高成本档：
                              更大上下文预算 + 多候选 + 更多迭代）

    Args:
        lines: 被测代码总行数（跨文件求和）。
        num_files: 模块数（跨文件任务 >1，单文件 = 1）。
        num_deps: import 数量（count_imports 口径）。
        cyclomatic_complexity: 圈复杂度（code_analyzer.compute_cyclomatic_complexity 口径）。

    Returns:
        ComplexityScore（score, complexity_class, breakdown）。
    """
    l_norm = _norm_lines()
    f_norm = _norm_files()
    d_norm = _norm_deps()
    cc_norm = _norm_cc()

    comp_lines = min(1.0, lines / l_norm) if l_norm > 0 else 0.0
    comp_files = min(1.0, num_files / f_norm) if f_norm > 0 else 0.0
    comp_deps = min(1.0, num_deps / d_norm) if d_norm > 0 else 0.0
    comp_cc = min(1.0, cyclomatic_complexity / cc_norm) if cc_norm > 0 else 0.0

    # 等权平均（四维度各占 25%）
    score = (comp_lines + comp_files + comp_deps + comp_cc) / 4.0

    if score < 0.35:
        complexity_class = "simple"
    elif score < 0.70:
        complexity_class = "medium"
    else:
        complexity_class = "complex"

    breakdown = {
        "lines": round(comp_lines, 4),
        "files": round(comp_files, 4),
        "deps": round(comp_deps, 4),
        "cyclomatic": round(comp_cc, 4),
        "raw_lines": lines,
        "raw_files": num_files,
        "raw_deps": num_deps,
        "raw_cc": cyclomatic_complexity,
    }

    logger.debug(
        "P0 1.2 复杂度评分：score=%.3f class=%s breakdown=%s",
        score,
        complexity_class,
        breakdown,
    )
    return ComplexityScore(score=round(score, 4), complexity_class=complexity_class, breakdown=breakdown)


def complexity_class_to_routing_hints(complexity_class: str) -> dict[str, object]:
    """把复杂度档位映射为路由提示（供 APIManager / 工作流消费）。

    simple  → 单候选、低迭代、小上下文（省 token）
    medium  → 单候选、默认迭代、默认上下文
    complex → 多候选（3-5）、高迭代（+1）、大上下文预算（CODE_MAX_CHARS 上调）

    Returns:
        {"complexity_class": str, "max_candidates": int, "extra_iteration": int,
         "context_budget": int, "hint_text": str}
    """
    if complexity_class == "complex":
        return {
            "complexity_class": complexity_class,
            "max_candidates": 3,
            "extra_iteration": 1,
            "context_budget": 6000,  # 大上下文预算（CODE_MAX_CHARS 可调）
            "hint_text": "复杂任务：启用多候选 + 大上下文预算 + 额外迭代轮",
        }
    if complexity_class == "medium":
        return {
            "complexity_class": complexity_class,
            "max_candidates": 2,
            "extra_iteration": 0,
            "context_budget": 3000,
            "hint_text": "中等任务：双候选 + 默认上下文",
        }
    return {
        "complexity_class": complexity_class,
        "max_candidates": 1,
        "extra_iteration": 0,
        "context_budget": 3000,
        "hint_text": "简单任务：单候选 + 小上下文（省 token）",
    }
