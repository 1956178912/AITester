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
      （迭代越多且最终失败 = 越难收敛），分三档；
    - difficulty_level（4.3）：任务显式难度等级标签（来自合成任务生成器的
      level 字段 / 结果行 task_metadata.difficulty_level），分 Level 1-4 档。
      未标注难度的任务归入 "unlabeled" 档。

4.3 改进：新增 difficulty_level 维度，消费 experiments/synthetic_difficulty.py
生成的多层难度任务标签（Level 1 单函数简单缺陷 / Level 2 多函数交互 /
Level 3 跨文件依赖 / Level 4 边界异常隐蔽缺陷），使"跨文件修复的 A/B 对比"
有明确的难度分层口径（只有构造了 Level 3 任务，跨文件修复的对比才有意义）。

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


def _difficulty_level_bucket(row: dict[str, Any]) -> str:
    """4.3 按任务显式难度等级分档（Level 1-4，未标注归 "unlabeled"）。

    等级来源（优先级）：
    1. 结果行 task_metadata.difficulty_level（合成任务生成器写入）；
    2. 结果行 difficulty_level（benchmark 顶层字段）；
    3. 均未标注 → "unlabeled"。
    """
    level = (row.get("task_metadata") or {}).get("difficulty_level")
    if level is None:
        level = row.get("difficulty_level")
    # 2026-09-26 修复：JSON 反序列化 / 数值计算后 level 可能不是 int 形态
    # （纯数字 str "3"、整数值 float 3.0），直接 `in (1, 2, 3, 4)` 落不到
    # 任何档 → 该维度全部分层退化为 "unlabeled"（4.3 难度分层指标失真）。
    # 保守归一：仅「数值语义明确」的形态转 int——int 直通；纯数字 str
    # （允许正负号）转 int；整数值 float（3.0）转 int。其余形态（非数字
    # str、带小数 float 如 3.5、bool——bool 虽为 int 子类但难度等级语义
    # 上不接受 True/False、复合类型）保持 "unlabeled"（难度等级语义上
    # 必须是整数档位）。
    if isinstance(level, bool):
        level = None
    elif isinstance(level, str):
        s = level.strip()
        # 纯数字（含正负号前缀）归一为 int；其余保持 "unlabeled"
        level = int(s) if s.isdigit() or (s[:1] in "+-" and s[1:].isdigit()) else None
    elif isinstance(level, float):
        level = int(level) if level.is_integer() else None
    if level in (1, 2, 3, 4):
        return f"level_{level}"
    return "unlabeled"


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
    elif dimension == "difficulty_level":
        key_fn = _difficulty_level_bucket
        order = ["level_1", "level_2", "level_3", "level_4", "unlabeled"]
    else:
        raise ValueError(
            f"未知分层维度: {dimension}（支持 code_size/dependency_count/complexity_proxy/difficulty_level）"
        )

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
    """渲染难度分层 Markdown 章节（无数据时返回空列表）。

    2026-09-26 round9（P2 口径修复）：instance_codes / test_codes 均未提供
    （或全部缺失）时，code_size / dependency_count 维度退化为单档
    （全部 small / 全部 low），在章节末尾追加退化标注，避免读者误读
    "所有任务都是小代码 / 零依赖"。
    """
    if not details:
        return []
    lines = [f"## 任务难度分层（2.2，基线 {baseline}）", ""]
    lines.append("| 维度 | 分层 | 任务数 | 成功数 | 成功率 |")
    lines.append("|------|------|--------|--------|--------|")
    _degraded: list[str] = []
    for dimension in ("code_size", "dependency_count", "complexity_proxy", "difficulty_level"):
        strat = stratify_by_dimension(details, dimension, instance_codes, test_codes)
        if not strat:
            continue
        # 退化判定：该维度仅有单一分档 → 数据缺失（缺 instance_code / 依赖源）
        if len(strat) == 1:
            _degraded.append(dimension)
        for bucket, stat in strat.items():
            lines.append(f"| {dimension} | {bucket} | {stat['tasks']} | {stat['passed']} | {stat['success_rate']} |")
    lines.append("")
    lines.append(
        "> 解读：若某难度层成功率显著低于其他层（如 large 档 < 30%），说明系统"
        "在该难度区间能力衰减；complexity_proxy hard 档成功率反映'修复不收敛'任务的占比。"
        "4.3 difficulty_level 维度：Level 3（跨文件依赖）成功率与 Level 1（单函数）"
        "对比，才有意义的跨文件修复 A/B 口径；unlabeled 档为未标注难度的历史任务。"
    )
    # 2026-09-26 round9：退化维度标注（缺 instance_code 源时 code_size /
    # dependency_count 全部落 small/low 单档，无分层区分度，需明确告知）
    if _degraded:
        lines.append("")
        lines.append(
            f"> ⚠️ 退化标注：维度 {', '.join(_degraded)} 因结果行缺少 instance_code / "
            "被测源码来源，全部任务落入单一分档（"
            + " / ".join(f"{d}=单档" for d in _degraded)
            + "），分层成功率无区分度，请补充 instance_code 源后重跑。"
        )
    lines.append("")
    return lines
