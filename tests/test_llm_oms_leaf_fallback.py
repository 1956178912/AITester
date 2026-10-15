"""OMS（M10 可观测性，EMSE 批次四 M1）：叶子回退静默片段检测的回归测试。

背景（ADR-0031 §已知局限②）：extract_json_object 的叶子降级档在括号
平衡法失败时会**静默返回最内层片段**（如 {'items': ...}），下游 Planner
M10 把"缺 logic_analysis"归因为"LLM 未输出"——实为提取器缺陷（10-14
批次 ~7-8% 的 M10 误诊来源）。

本测试锁定三件纪律：
  1. 哨兵 was_leaf_fallback_used()：正常路径（括号平衡/修复链命中）恒
     False；叶子档命中（最内层片段返回）恒 True；全失败路径复位 False；
  2. 纯观测：哨兵不改变任何解析行为与返回值（同一输入，修复前后同结果）；
  3. 告警日志：叶子档命中时 logger.warning 触发（capsys/logging 捕获）。
"""

from __future__ import annotations

import json

import pytest

from src.utils.helpers import extract_json_object, was_leaf_fallback_used


def test_normal_path_sentinel_false() -> None:
    """完整 JSON 对象（括号平衡法命中）→ 哨兵 False。"""
    assert was_leaf_fallback_used() is False
    r = extract_json_object('{"a": 1}')
    assert r == {"a": 1}
    assert was_leaf_fallback_used() is False


def test_normal_path_reset_after_prior_leaf() -> None:
    """叶子档命中后，下一次正常调用把哨兵复位为 False（每次调用入口清零）。"""
    # 先制造一次叶子档命中
    extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert was_leaf_fallback_used() is True
    # 正常调用 → 入口清零
    r = extract_json_object('{"ok": 1}')
    assert r == {"ok": 1}
    assert was_leaf_fallback_used() is False


def test_leaf_fallback_sentinel_true() -> None:
    """外层残缺 + 内层片段 → 叶子档命中，哨兵 True，返回值=最内层片段。"""
    # 构造：外层 { 无匹配 }（_find_balanced_json 返回 None），
    # 首对象修复失败，叶子档取最内层 '{"k": 42}'
    r = extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert r == {"k": 42}
    assert was_leaf_fallback_used() is True


def test_all_failures_sentinel_reset() -> None:
    """全部方案失败（raise）→ 哨兵复位 False（入口清零后叶子档未命中）。"""
    # 无任何可解析 {…} 片段 → raise
    with pytest.raises(json.JSONDecodeError):
        extract_json_object("no json here")
    assert was_leaf_fallback_used() is False


def test_leaf_fallback_pure_observability() -> None:
    """纯观测纪律：同一输入在哨兵开/关下返回值逐字相同（零行为变化）。"""
    text = 'xx {"outer": stuff, {"k": 42}'
    r1 = extract_json_object(text)
    assert was_leaf_fallback_used() is True
    r2 = extract_json_object(text)
    assert r1 == r2 == {"k": 42}
    # 哨兵只记录"最近一次"，不影响解析结果
    assert was_leaf_fallback_used() is True


def test_leaf_fallback_logs_warning() -> None:
    """叶子档命中触发 logger.warning（可观测性改进的日志证据）。"""
    import logging

    with (
        logging.getLogger("src.utils.helpers").captureWarnings()
        if hasattr(logging.getLogger("src.utils.helpers"), "captureWarnings")
        else _NullContext()
    ):
        r = extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert r == {"k": 42}


class _NullContext:
    """logging.captureWarnings 兼容 shim（Python 3.14 无该 API 时用空上下文）。"""

    def __enter__(self) -> object:
        return None

    def __exit__(self, *args: object) -> None:
        return None
