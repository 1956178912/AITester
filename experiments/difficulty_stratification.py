"""
任务难度分层分析（2.2 数据集深化：按代码复杂度 / 依赖数量 / 文件规模分层）。

背景：
    聚合成功率会掩盖"系统在简单任务上满分、困难任务上全军覆没"的结构性
    差异。本模块把 benchmark 结果按三个维度分层，输出各层成功率对比，
    用于定位"AITester 在什么难度区间下能力衰减"。

维度口径（全部从 benchmark 结果 JSON 可复算，不依赖额外数据源）：
    - code_size:  任务 instance_code 字符数（缺省用 test_code，再缺省 0）分三档；
    - dependency_count: 结果行 import 提取的第三方模块数（经
      src/tools/dependency.extract_imported_modules 提取，缺字段时 0）分三档；
    - complexity_proxy: 结果行 iterations × (1 - passed) 的"修复难度代理"
      （迭代越多且最终失败 = 越难收敛），分三档。

分层边界（保守可解释口径）：
    code_size:        small < 2KB / medium 2-10KB / large > 10KB
    dependency_count: low 0 / medium 1-2 / high >= 3
    complexity_proxy: easy 0 / medium 1 / hard >= 2
"""

from __future__ import annotations

from typing import Any

# 分层边界常量（与模块 docstring 口径一致）
_CODE_SIZE_MEDIUM_THRESHOLD = 2048
_CODE_SIZE_LARGE_THRESHOLD = 10240
_DEP_MEDIUM_THRESHOLD = 1
_DEP_HIGH_THRESHOLD = 3


def _code_size_bucket(instance_code: str, test_code: str) -> str:
    """按被测代码字符数分档（small / medium / large）。"""
    size = len(instance_code or test_code or "")
    if size < _CODE_SIZE_MEDIUM_THRESHOLD:
        return "small"
    if size < _CODE_SIZE_LARGE_THRESHOLD:
        return "medium"
    return "large"


def _dependency_bucket(dep_count: int) -> str:
    """按第三方依赖数分档（low / medium / high）。"""
    if dep_count <= _DEP_MEDIUM_THRESHOLD:
        return "low"
    if dep_count < _DEP_HIGH_THRESHOLD:
        return "medium"
    return "high"


def _complexity_bucket(row: dict[str, Any]) -> str:
    """按"修复难度代理"分档（easy / medium / hard）。

    代理口径：iterations × (1 - passed)；成功任务恒 0（easy），
    失败任务 = 其迭代次数（修复未收敛越久 = 越难）。
    """
    iterations = int(row.get("iterations", 0) or 0)
    proxy = iterations if not row.get("passed") else 0
    if proxy <= 0:
        return "easy"
    if proxy == 1:
        return "medium"
    return "hard"


def stratify_by_dimension(
    details: list[dict[str, Any]],
    dimension: str,
    instance_codes: dict[str, str] | None = None,
    test_codes: dict[str, str] | None = None,
) -> dict[str, Any]:
    """按指定维度对任务分层，统计各层任务数与成功率。

    Args:
        details: benchmark 结果 details 列表。
        dimension: "code_size" / "dependency_count" / "complexity_proxy"。
        instance_codes: task_id → 被测源码（dependency_count 分层必需；
            缺省时该维度全任务按 0 依赖处理，分层退化为单档）。
        test_codes: task_id → 测试代码（code_size 分层在 instance_code 缺失时兜底）。

    Returns:
        {bucket: {"tasks": 任务数, "passed": 成功数, "success_rate": 成功率}}；
        未知维度抛 ValueError。
    """
    buckets: dict[str, dict[str, Any]] = {}
    if dimension == "code_size":

        def key_fn(r: dict[str, Any]) -> str:
            return _code_size_bucket(
                (instance_codes or {}).get(str(r.get("task_id", "")), ""),
                (test_codes or {}).get(str(r.get("task_id", "")), ""),
            )

        order = ["small", "medium", "large"]
    elif dimension == "dependency_count":

        def key_fn(r: dict[str, Any]) -> str:
            source = (instance_codes or {}).get(str(r.get("task_id", "")), "")
            return _dependency_bucket(len(_extract_dep_count(source)))

        order = ["low", "medium", "high"]
    elif dimension == "complexity_proxy":
        key_fn = _complexity_bucket
        order = ["easy", "medium", "hard"]
    else:
        raise ValueError(f"未知分层维度: {dimension}（支持 code_size/dependency_count/complexity_proxy）")

    for row in details:
        bucket = key_fn(row)
        stat = buckets.setdefault(bucket, {"tasks": 0, "passed": 0})
        stat["tasks"] += 1
        if row.get("passed"):
            stat["passed"] += 1

    result: dict[str, Any] = {}
    for name in order:
        stat = buckets.get(name)
        if not stat:
            continue
        total = stat["tasks"]
        result[name] = {
            "tasks": total,
            "passed": stat["passed"],
            "success_rate": round(stat["passed"] / total, 4) if total else 0.0,
        }
    return result


def _extract_dep_count(source_code: str) -> set[str]:
    """提取第三方依赖模块集合（复用 dependency.py 的单一实现，DRY）。

    导入失败（循环依赖 / 未安装）时返回空集，分层退化为 low 档，不崩溃。
    """
    if not source_code:
        return set()
    try:
        from src.tools.dependency import extract_imported_modules

        return extract_imported_modules(source_code)
    except Exception:
        return set()


def render_stratification_section(
    details: list[dict[str, Any]],
    baseline: str,
    instance_codes: dict[str, str] | None = None,
    test_codes: dict[str, str] | None = None,
) -> list[str]:
    """渲染难度分层 Markdown 章节（无数据时返回空列表）。"""
    if not details:
        return []
    lines = [f"## 任务难度分层（2.2，基线 {baseline}）", ""]
    lines.append("| 维度 | 分层 | 任务数 | 成功数 | 成功率 |")
    lines.append("|------|------|--------|--------|--------|")
    for dimension in ("code_size", "dependency_count", "complexity_proxy"):
        strat = stratify_by_dimension(details, dimension, instance_codes, test_codes)
        if not strat:
            continue
        for bucket, stat in strat.items():
            lines.append(f"| {dimension} | {bucket} | {stat['tasks']} | {stat['passed']} | {stat['success_rate']} |")
    lines.append("")
    lines.append(
        "> 解读：若某难度层成功率显著低于其他层（如 large 档 < 30%），说明系统"
        "在该难度区间能力衰减；complexity_proxy hard 档成功率反映'修复不收敛'任务的占比。"
    )
    lines.append("")
    return lines
