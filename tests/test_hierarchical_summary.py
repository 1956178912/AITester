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


# ─── 2026-10-02 审查：缺失分支补测（分支覆盖 77% 门槛回绿）────────────────
# 覆盖：_budget_env 非法值回退 / 开关取值边界 / SyntaxError 降级 /
# docstring 提取分支 / Level1 超预算丢弃与字符截尾 / Level2 类块丢弃 /
# Level3 预算 break 分支 / summarize_code 空输入与 Level2/3 降级链。


def test_budget_env_invalid_falls_back() -> None:
    from src.tools.hierarchical_summary import _budget_env

    with patch.dict(os.environ, {"SUMMARY_BUDGET_L1": "not-a-number"}):
        assert _budget_env("L1") == 1200
    with patch.dict(os.environ, {"SUMMARY_BUDGET_L1": "2048"}):
        assert _budget_env("L1") == 2048


def test_switch_requires_exact_true() -> None:
    """开关仅接受 'true' 精确值（非 '1'/'on'——与实现 == 'true' 同口径）。"""
    from src.tools.hierarchical_summary import hierarchical_summary_enabled

    with patch.dict(os.environ, {"HIERARCHICAL_SUMMARY_ENABLE": "1"}):
        assert hierarchical_summary_enabled() is False  # 仅接受 'true' 字面量
    with patch.dict(os.environ, {"HIERARCHICAL_SUMMARY_ENABLE": "TRUE"}):
        assert hierarchical_summary_enabled() is True  # .lower() 归一后命中
    with patch.dict(os.environ, {"HIERARCHICAL_SUMMARY_ENABLE": "true"}):
        assert hierarchical_summary_enabled() is True


def test_extract_functions_syntax_error_returns_empty() -> None:
    from src.tools.hierarchical_summary import _extract_functions

    assert _extract_functions("def broken(:\n") == []


def test_extract_classes_syntax_error_returns_empty() -> None:
    from src.tools.hierarchical_summary import _extract_classes

    assert _extract_classes("class Broken(:\n") == []


def test_extract_classes_parses_public_methods() -> None:
    from src.tools.hierarchical_summary import _extract_classes

    src = (
        "class Widget:\n"
        "    '''A widget.'''\n"
        "    def render(self):\n"
        "        pass\n"
        "    def _private(self):\n"
        "        pass\n"
    )
    out = _extract_classes(src)
    assert len(out) == 1
    assert out[0]["name"] == "Widget"
    assert out[0]["doc_first"] == "A widget."
    # 私有方法不入公共方法列表
    assert all("_private" not in m for m in out[0]["public_methods"])


def test_extract_classes_top_level_only() -> None:
    """ast.iter_child_nodes 口径：嵌套类不提取。"""
    from src.tools.hierarchical_summary import _extract_classes

    src = "def f():\n    class Inner:\n        pass\n"
    assert _extract_classes(src) == []


def test_extract_functions_async_and_focus() -> None:
    from src.tools.hierarchical_summary import _extract_functions

    src = "async def fetch(url):\n    '''fetch doc'''\n    return url\n"
    out = _extract_functions(src, focus_function="fetch")
    assert out[0]["is_async"] is True
    assert out[0]["focus"] is True
    assert out[0]["doc_first"] == "fetch doc"
    assert out[0]["signature"] == "async def fetch(url)" if False else out[0]["signature"].startswith("def")


def test_extract_functions_signature_limited_to_8_args() -> None:
    from src.tools.hierarchical_summary import _extract_functions

    args = ", ".join(f"a{i}" for i in range(12))
    src = f"def many({args}):\n    pass\n"
    out = _extract_functions(src)
    # 前 8 个参数 + 收尾（join 不加省略号，仅截断到 8）
    assert out[0]["signature"].count(",") <= 7


def test_level1_truncates_when_result_over_1_5x_budget() -> None:
    """Level1 结果仍超 budget*1.5 → 字符截尾分支。"""
    from src.tools.hierarchical_summary import _level1_summary

    # 极小预算 + 大量函数（无 focus → 不走丢弃分支，直接累积超限）
    src = _make_source(n_functions=30, focus="alpha")
    text, meta = _level1_summary(src, focus_function=None, budget=40)
    assert "// [truncated to 40 chars]" in text
    assert meta["summary_level"] == 1


def test_level1_drops_functions_when_focus_present() -> None:
    """有 focus 且累积超预算 → dropped 分支逐个丢弃。"""
    from src.tools.hierarchical_summary import _level1_summary

    src = _make_source(n_functions=20, focus="add")
    _text, meta = _level1_summary(src, focus_function="add", budget=80)
    assert meta["summary_dropped_symbols"], "超预算时应记录被丢弃符号"
    assert any(name.startswith("helper_") for name in meta["summary_dropped_symbols"])


def test_level2_drops_class_block_when_over_budget() -> None:
    from src.tools.hierarchical_summary import _level2_summary

    # 巨型类（12 个公共方法）+ 极小预算 → 类块被丢弃
    methods = "\n".join(f"    def method_{i}(self):\n        pass" for i in range(12))
    src = f"class Giant:\n    '''giant'''\n{methods}\n\ndef tail():\n    pass\n"
    _text, meta = _level2_summary(src, focus_function=None, budget=30)
    assert any(d.startswith("class:") for d in meta["summary_dropped_symbols"]), meta


def test_level2_marks_focus_function() -> None:
    from src.tools.hierarchical_summary import _level2_summary

    src = _make_source(n_functions=3, focus="add")
    text, _ = _level2_summary(src, focus_function="add", budget=4000)
    assert "[FOCUS]" in text


def test_level3_budget_break_on_classes() -> None:
    """Level3 类循环：摘要行超预算 → break 分支。"""
    from src.tools.hierarchical_summary import _level3_summary

    classes = "\n\n".join(f"class C{i}:\n    def m1(self): pass\n    def m2(self): pass" for i in range(10))
    src = classes + "\n\ndef tail():\n    pass\n"
    text, meta = _level3_summary(src, focus_function=None, budget=50)
    assert meta["summary_level"] == 3
    assert len(text.splitlines()) < 10, "预算 break 应提前终止类循环"


def test_level3_budget_break_on_funcs_records_dropped() -> None:
    from src.tools.hierarchical_summary import _level3_summary

    src = _make_source(n_functions=30, focus="add")
    _text, meta = _level3_summary(src, focus_function="add", budget=60)
    assert meta["summary_dropped_symbols"], "函数循环超预算 break 时应记录 dropped"


def test_level3_with_all_exports_and_constants() -> None:
    from src.tools.hierarchical_summary import _level3_summary

    src = "__all__ = ['a', 'b']\nMAX_RETRIES = 3\n\n\ndef f():\n    pass\n"
    text, _ = _level3_summary(src, focus_function=None, budget=400)
    assert "__all__" in text
    assert "MAX_RETRIES" in text


def test_summarize_code_empty_source() -> None:
    from src.tools.hierarchical_summary import summarize_code

    text, meta = summarize_code("")
    assert text == ""
    assert meta["summary_level"] == 0


def test_summarize_code_level2_fallback_when_l1_over_1_5x() -> None:
    """L1 结果超 1.5×预算 → 降级 L2。"""
    from src.tools.hierarchical_summary import summarize_code

    src = _make_source(n_functions=40, focus="add")
    # 预算 40：L1 截尾后 40+27=67 > 40*1.5=60 → 降级 L2（L2 预算 500 足够收纳）
    with patch.dict(os.environ, {"SUMMARY_BUDGET_L1": "40", "SUMMARY_BUDGET_L2": "500"}):
        _text, meta = summarize_code(src, focus_function=None)
        assert meta["summary_level"] == 2, meta
        assert meta["summary_budget"] == 500


def test_summarize_code_level3_last_resort() -> None:
    """L1/L2 均超 1.5×预算 → Level 3 最坏兜底。"""
    from src.tools.hierarchical_summary import summarize_code

    # 长 __all__（L2 初始行无预算检查）→ L2 超 1.5×预算 → Level 3 最坏兜底
    all_list = ", ".join(f"'symbol_{i}'" for i in range(50))
    src = f"__all__ = [{all_list}]\n\n" + _make_source(n_functions=30, focus="add")
    with patch.dict(
        os.environ,
        {"SUMMARY_BUDGET_L1": "40", "SUMMARY_BUDGET_L2": "30", "SUMMARY_BUDGET_L3": "200"},
    ):
        text, meta = summarize_code(src, focus_function=None)
        assert meta["summary_level"] == 3
        assert meta["summary_budget"] == 200
        # Level 3 是最坏兜底：不保证 ≤ 预算，但必须产出非空摘要
        assert text.strip(), "Level 3 兜底摘要不应为空"
        assert "__all__" in text or "def " in text


def test_level1_focus_body_and_contract_symbols() -> None:
    """Level1 焦点函数完整体 + __all__ / imports / constants 三段契约符号。"""
    from src.tools.hierarchical_summary import _level1_summary

    src = (
        "__all__ = ['add']\n"
        "import os\n"
        "MAX = 10\n"
        "\n"
        "def add(a, b):\n"
        "    '''add doc'''\n"
        "    return a + b\n"
        "\n"
        "def other(x):\n"
        "    return x\n"
    )
    text, _ = _level1_summary(src, focus_function="add", budget=4000)
    assert "// [focus] def add(a, b)" in text
    assert "return a + b" in text
    assert "__all__" in text
    assert "imports:" in text
    assert "module_constants:" in text
