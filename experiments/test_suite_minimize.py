"""
N5（2026-09-29 审查 P2）：测试套件最小化 + 失败优先排序 + 断言去重
（delta debugging 原语）。

历史口径：基准跑批对整批测试串行全量执行（失败任务全量重跑），
单任务内 LLM 生成的测试套件常含大量恒真断言（O4 已识别但无去重），
且执行顺序为代码书写顺序（失败用例排在后面时前 N 条全过就终止）。

本模块提供三个纯数据原语（零 LLM / 零 subprocess，可在 experiments/
层按需消费）：

1. `dedup_assertions(test_code)` — 断言去重：AST 级识别语义相同的
   重复断言（同行文本去重 + 浅层比较归一化），返回精简后的测试代码
   与被移除的重复项清单。

2. `failure_first_order(test_names, failure_history)` — 失败优先排序：
   按历史失败次数降序（最近失败优先），无历史时保持原序（稳定排序，
   确定性口径）。

3. `minimize_suite(test_names, failure_signal_fn, max_minimize_rounds)` —
   delta debugging 最小化：从全量套件出发，二分删除"不影响失败信号"
   的用例子集，返回最小失败复现子集（delta-debugging 经典 d3 算法，
   纯数据 + 调用方提供的失败判定函数）。

验收指标（N5）：
- 断言去重：恒真率（O4 口径）下降 ≥ 20%（实验层对照）；
- 失败优先排序：首次失败发现轮次（失败用例出现的 iteration 序号）
  中位数下降；
- 套件最小化：失败复现子集大小 ≤ 全量的 30%（delta-debugging 理论界）。

用法：
    from experiments.test_suite_minimize import (
        dedup_assertions,
        failure_first_order,
        minimize_suite,
    )

    # 断言去重
    cleaned, removed = dedup_assertions(llm_generated_test_code)

    # 失败优先排序
    ordered = failure_first_order(
        test_names=["test_a", "test_b", "test_c"],
        failure_history={"test_b": 3, "test_c": 1},
    )
    # → ["test_b", "test_c", "test_a"]

    # delta-debugging 最小化（failure_signal_fn 为调用方提供的
    # "子集 → 是否仍复现失败" 判定函数，通常经 executor 实测）
    minimal = minimize_suite(
        test_names=ordered,
        failure_signal_fn=lambda subset: _run_pytest_subset(subset),
        max_minimize_rounds=5,
    )
"""

from __future__ import annotations

import ast
from collections.abc import Callable
from typing import Any

__all__ = [
    "dedup_assertions",
    "failure_first_order",
    "minimize_suite",
    "optimize_test_suite",
]


# ─── 1. 断言去重 ─────────────────────────────────────────────────────────────


def _normalize_assert_text(source: str, line_no: int, node: ast.Assert) -> str:
    """把断言行归一化为可比较键（去空白 + 浅层常量排序）。

    归一化口径（保守，避免误删语义不同的断言）：
    - 取该行的 ast.unparse 结果（AST 级，`a == b` 与 `b == a` 不同
      键——不跨交换律归一，避免误删）；
    - 空白归一化（`assert x ==1` 与 `assert x == 1` 同键）。
    """
    _src = ast.unparse(node)
    # 浅层归一：多重空格 → 单空格（不改变 AST 语义）
    return " ".join(_src.split())


def dedup_assertions(test_code: str) -> tuple[str, list[dict[str, Any]]]:
    """N5：AST 级断言去重——移除同一测试函数内语义相同的重复断言。

    去重键 = 归一化后的 ast.unparse(assert 行)（保守口径：不跨交换律 /
    类型归一，仅"同文本断言"去重，避免误删语义不同的断言）。

    Args:
        test_code: LLM 生成的测试代码全文。
        (无额外参数；默认全量去重，不去重 setup/teardown 函数。)

    Returns:
        (去重后的代码, 被移除项清单)。
        被移除项清单每项：
        - {"line": int, "text": str, "func": str}
        语法不合法时返回 (原代码, [])（保守：语法失败由
        executor 的 ast.parse 校验先行拦截，本守卫只做去重）。
    """
    try:
        tree = ast.parse(test_code)
    except (SyntaxError, ValueError):
        return test_code, []

    # 按函数分组（仅处理 test_* 函数，setup/teardown 不去重）
    _removed: list[dict[str, Any]] = []
    _seen_keys: dict[str, set[str]] = {}  # func_name → set(normalized assert)

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        _seen_keys.setdefault(node.name, set())
        for child in node.body:
            if isinstance(child, ast.Assert):
                key = _normalize_assert_text(test_code, child.lineno, child)
                if key in _seen_keys[node.name]:
                    _removed.append({"line": child.lineno, "text": key, "func": node.name})
                else:
                    _seen_keys[node.name].add(key)

    if not _removed:
        return test_code, _removed

    # 从源码中移除被标记的行（行号倒序 splice，避免行号偏移）
    _lines = test_code.splitlines(keepends=True)
    _removed_lines = sorted({r["line"] for r in _removed}, reverse=True)
    for _ln in _removed_lines:
        if 0 < _ln <= len(_lines):
            del _lines[_ln - 1]
    return "".join(_lines), _removed


# ─── 2. 失败优先排序 ──────────────────────────────────────────────────────────


def failure_first_order(
    test_names: list[str],
    failure_history: dict[str, int] | None = None,
) -> list[str]:
    """N5：按历史失败次数降序排序测试用例（最近/最多失败者优先执行）。

    确定性口径（stable sort）：
    - 有失败历史的用例按失败次数降序；
    - 无失败历史（或次数相同）的用例保持原序（Python sorted 稳定性）；
    - 全空历史 → 原序不变（历史行为零变化）。

    收益：失败用例排在前 → 首轮执行即发现失败（省去 N 条全过后的
    全量重跑），迭代轮次缩短。

    Args:
        test_names: 测试用例名列表（如 "test_foo" / "test_bar"）。
        failure_history: 用例名 → 历史失败次数（可选；None = 全 0）。

    Returns:
        排序后的用例名列表（与 test_names 同长度，元素顺序重排）。
    """
    _history = failure_history or {}
    # 稳定排序：-count 降序；无历史（0）的用例保持原序
    return sorted(test_names, key=lambda name: -_history.get(name, 0))


# ─── 3. Delta-debugging 套件最小化 ───────────────────────────────────────────


def minimize_suite(
    test_names: list[str],
    failure_signal_fn: Callable[[list[str]], bool],
    max_minimize_rounds: int = 5,
) -> list[str]:
    """N5：delta-debugging（d3 算法）最小化失败复现子集。

    从全量套件出发，二分删除"不影响失败信号"的用例子集，
    返回最小失败复现子集（经典 delta-debugging d3：
    先试"删一半"，若仍复现则递归删子集，否则保留子集再删另一半）。

    终止条件（任一满足即停止，返回当前子集）：
    - 子集大小 == 1（单用例，无法再二分）；
    - 当前子集删除任一用例后失败信号消失（已是最小）；
    - 达到 max_minimize_rounds 上限（防止执行次数爆炸）。

    保守口径：failure_signal_fn 调用失败（异常）时视为"仍复现"
    （不扩张子集），最终子集偏大（宁可多保留，不误删）。

    Args:
        test_names: 全量测试用例名列表。
        failure_signal_fn: 子集 → 是否仍复现失败（True = 复现）。
            调用方通常经 executor 在 venv 内跑 pytest 子集实测。
        max_minimize_rounds: 最大二分轮次（默认 5，2^5=32 次
            failure_signal_fn 调用上界）。

    Returns:
        最小（或近似最小）失败复现子集（test_names 的子序列，
        保持原相对顺序）。
    """
    if not test_names:
        return []

    current: list[str] = list(test_names)
    rounds = 0

    def _still_fails(subset: list[str]) -> bool:
        try:
            return failure_signal_fn(subset)
        except Exception:
            # 保守：判定异常 → 视为仍复现（不扩张）
            return True

    while len(current) > 1 and rounds < max_minimize_rounds:
        mid = len(current) // 2
        first_half = current[:mid]
        second_half = current[mid:]
        rounds += 1

        # d3：删掉后半，看前半是否仍复现
        if _still_fails(first_half):
            current = first_half
            continue
        # 删掉前半，看后半是否仍复现
        if _still_fails(second_half):
            current = second_half
            continue
        # 两半都不复现 → 交错合并（奇数下标 + 偶数下标各取）
        if len(current) <= 2:
            break
        current = [current[i] for i in range(len(current)) if i % 2 == (len(current) % 2)]
        rounds += 1

    # 单用例兜底
    if len(current) == 1 and rounds < max_minimize_rounds:
        rounds += 1
        if not _still_fails(current):
            # 单用例不复现 → 返回空（无最小复现子集）
            return []
    return current


# ─── 4. 便捷组合入口 ──────────────────────────────────────────────────────────


def optimize_test_suite(
    test_names: list[str],
    test_code: str = "",
    failure_history: dict[str, int] | None = None,
) -> dict[str, Any]:
    """N5 便捷组合入口：断言去重 + 失败优先排序（纯数据，零 LLM）。

    Args:
        test_names: 测试用例名列表。
        test_code: LLM 生成的测试代码全文（非空时做断言去重）。
        failure_history: 用例名 → 历史失败次数（可选）。

    Returns:
        {
            "deduped_code": str,          # 去重后的测试代码
            "removed_assertions": list,   # 被移除的重复断言清单
            "ordered_names": list[str],   # 失败优先排序后的用例名
            "removed_count": int,          # 去重移除数
            "reordered": bool,             # 排序是否改变顺序
        }
    """
    _deduped, _removed = dedup_assertions(test_code) if test_code else (test_code, [])
    _ordered = failure_first_order(test_names, failure_history)
    return {
        "deduped_code": _deduped,
        "removed_assertions": _removed,
        "ordered_names": _ordered,
        "removed_count": len(_removed),
        "reordered": _ordered != list(test_names),
    }
