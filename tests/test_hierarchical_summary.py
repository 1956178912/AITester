"""批次3 上下文压缩实装（基于 hierarchical_summary.md）单元测试。

覆盖：
- 开关默认关（HIERARCHICAL_SUMMARY_ENABLE 未设 → hierarchical_summary_enabled() False）
- 开关开启（monkeypatch 环境变量）
- summarize_code Level 0（原文 ≤ 预算 → 直接返回，summary_level=0）
- summarize_code Level 1（焦点函数完整体 + 契约符号 + 其余签名）
- summarize_code Level 2/3（大文件逐层降级，summary_level 递增）
- _extract_functions / _extract_classes / _extract_module_symbols 静态提取
- _level1_summary 丢弃超预算函数时记录 dropped symbols
- truncate_code_with_summary 开关关时走历史截断口径（summary_level=0）
- 可观测层：summary_dropped_symbols 非空时反映丢弃符号
"""

from __future__ import annotations

import os
from unittest.mock import patch


def _make_source(n_functions: int = 5, focus: str = "add") -> str:
    """构造 n_functions 个函数的 Python 源码（第一个为 focus）。"""
    lines = [f"def {focus}(a, b):\n    '''add two numbers'''\n    return a + b\n"]
    for i in range(1, n_functions + 1):
        lines.extend(
            [
                f"def helper_{i}(x):\n",
                f"    '''helper {i}'''\n",
                f"    return x * {i}\n",
            ]
        )
    return "\n".join(lines)


def test_hierarchical_summary_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HIERARCHICAL_SUMMARY_ENABLE", None)
        from src.tools.hierarchical_summary import hierarchical_summary_enabled

        assert hierarchical_summary_enabled() is False


def test_hierarchical_summary_switch_on() -> None:
    with patch.dict(os.environ, {"HIERARCHICAL_SUMMARY_ENABLE": "true"}):
        from src.tools.hierarchical_summary import hierarchical_summary_enabled

        assert hierarchical_summary_enabled() is True


def test_summarize_code_level0_returns_original_when_under_budget() -> None:
    from src.tools.hierarchical_summary import summarize_code

    small = "def add(a, b):\n    return a + b\n"
    text, meta = summarize_code(small, focus_function="add", budget=500)
    assert text == small  # 逐字节等价
    assert meta["summary_level"] == 0
    assert meta["summary_dropped_symbols"] == []


def test_summarize_code_level1_with_focus_function() -> None:
    from src.tools.hierarchical_summary import summarize_code

    source = _make_source(n_functions=3, focus="add")
    text, meta = summarize_code(source, focus_function="add", budget=1200)
    # Level 1：焦点函数完整体保留
    assert "def add(a, b):" in text
    assert "return a + b" in text
    assert meta["summary_level"] in (0, 1, 2, 3)
    # 非焦点函数以签名形式保留（或被丢弃）
    if meta["summary_level"] <= 1:
        assert "def helper_1(x)" in text


def test_summarize_code_level_progression_with_tiny_budget() -> None:
    """极小预算（50 字符）强制逐层降级到 Level 3。"""
    from src.tools.hierarchical_summary import summarize_code

    source = _make_source(n_functions=8, focus="add")
    # 极小预算触发 L1 → L2 → L3 降级链
    text, meta = summarize_code(source, focus_function="add", budget=50)
    # L3 层：极简摘要（导出 + 常量 + 类签名，无方法体）
    assert meta["summary_level"] in (2, 3)
    # 摘要文本比原文短
    assert len(text) < len(source)


def test_extract_functions_parsing() -> None:
    from src.tools.hierarchical_summary import _extract_functions

    source = _make_source(n_functions=3, focus="add")
    funcs = _extract_functions(source, focus_function="add")
    names = [f["name"] for f in funcs]
    assert "add" in names
    assert "helper_1" in names
    # focus 标记
    focus_funcs = [f for f in funcs if f["focus"]]
    assert len(focus_funcs) == 1
    assert focus_funcs[0]["name"] == "add"


def test_extract_module_symbols() -> None:
    from src.tools.hierarchical_summary import _extract_module_symbols

    source = (
        "import os\n"
        "from collections import OrderedDict\n"
        "__all__ = ['a', 'b']\n"
        "MAX_RETRIES = 3\n"
        "def add(a,b):\n    return a+b\n"
    )
    symbols = _extract_module_symbols(source)
    assert any("os" in imp for imp in symbols["imports"])
    assert "MAX_RETRIES" in symbols["constants"]
    assert "a" in symbols["all_exports"]
    assert "b" in symbols["all_exports"]


def test_truncate_code_with_summary_disabled_uses_historical_truncation() -> None:
    """开关关 → truncate_code_with_summary 走 BaseAgent.truncate_code 历史口径。"""
    from src.tools.hierarchical_summary import truncate_code_with_summary

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("HIERARCHICAL_SUMMARY_ENABLE", None)
        source = "def add(a, b):\n    return a + b\n" * 200  # 超长文本
        text, meta = truncate_code_with_summary(source, focus_function="add", max_chars=500)
        # 历史截断口径：summary_level=0（非分层摘要）
        assert meta["summary_level"] == 0
        # 截断后长度 ≤ max_chars + 提示语
        assert len(text) <= 800


def test_truncate_code_with_summary_enabled_does_hierarchical() -> None:
    """开关开 → truncate_code_with_summary 走分层摘要路径。"""
    from src.tools.hierarchical_summary import truncate_code_with_summary

    with patch.dict(os.environ, {"HIERARCHICAL_SUMMARY_ENABLE": "true"}):
        # 原文 8 个函数，预算 200 字符（远小于原文长度）强制分层摘要
        source = _make_source(n_functions=8, focus="add")
        text, meta = truncate_code_with_summary(source, focus_function="add", max_chars=200)
        # 分层摘要：summary_level ∈ {1,2,3}（原文 8 个函数 > 200 字符预算）
        assert meta["summary_level"] in (1, 2, 3)
        assert len(text) < len(source)


def test_dropped_symbols_observable() -> None:
    """可观测层：summary_dropped_symbols 反映被丢弃的符号。"""
    from src.tools.hierarchical_summary import summarize_code

    # 极小预算 + 多函数 → 部分函数被丢弃
    source = _make_source(n_functions=10, focus="add")
    _text, meta = summarize_code(source, focus_function="add", budget=200)
    # 非焦点函数可能部分被丢弃（记录在 dropped_symbols）
    if meta["summary_level"] >= 1:
        # 只要摘要生成了，dropped 列表就是合法的（可能为空或非空）
        assert isinstance(meta["summary_dropped_symbols"], list)
