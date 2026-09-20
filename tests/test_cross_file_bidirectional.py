"""
2.2 跨文件双向依赖图单元测试。

覆盖：
- analyze_cross_file_deps 单向模式（默认，历史口径）；
- 双向模式（bidirectional=True）：收集"其他模块 → entry_module"的反向边；
- cross_file_bidirectional 环境变量开关；
- _find_symbol_def_line 符号定义行定位（def/class/赋值）。
"""

from __future__ import annotations

from src.tools.cross_file import (
    analyze_cross_file_deps,
    cross_file_bidirectional,
)

# 被测：entry 模块导入 utils 的 helper，并调用它
_ENTRY = """\
from utils import helper

def compute(x):
    return helper(x) + 1
"""
# 被测：utils 模块定义了 helper
_UTILS = """\
def helper(x):
    return x * 2
"""
# 被测：调用者模块 import 了 entry 的 compute（反向依赖）
_CALLER = """\
from entry import compute

def run():
    return compute(5)
"""


class TestUnidirectional:
    """单向模式（历史口径，默认）。"""

    def test_entry_imports_utils_edge(self):
        source_files = {"entry": _ENTRY, "utils": _UTILS}
        deps = analyze_cross_file_deps("entry", source_files)
        # entry → utils（helper 符号）
        assert len(deps) == 1
        assert deps[0].source_module == "entry"
        assert deps[0].target_module == "utils"
        assert deps[0].symbol == "helper"
        # 调用行上下文含 compute
        assert "compute" in deps[0].context or deps[0].call_line > 0

    def test_entry_missing_returns_empty(self):
        deps = analyze_cross_file_deps("nope", {"entry": _ENTRY})
        assert deps == []

    def test_syntax_error_in_entry_returns_empty(self):
        deps = analyze_cross_file_deps("bad", {"bad": "def x(:\n  "})
        assert deps == []

    def test_unidirectional_no_reverse_edges(self):
        """默认模式下不收集"其他模块 → entry"的反向边。"""
        source_files = {"entry": _ENTRY, "utils": _UTILS, "caller": _CALLER}
        deps = analyze_cross_file_deps("entry", source_files, bidirectional=False)
        # 只有 entry → utils 一条（entry 不 import caller，caller → entry 反向边不收集）
        targets = [d.target_module for d in deps]
        assert "caller" not in targets
        assert "utils" in targets


class TestBidirectional:
    """2.2 改进：双向依赖图（bidirectional=True）。"""

    def test_bidirectional_collects_reverse_edges(self):
        source_files = {"entry": _ENTRY, "utils": _UTILS, "caller": _CALLER}
        deps = analyze_cross_file_deps("entry", source_files, bidirectional=True)
        # 正向：entry → utils
        # 反向：caller → entry（caller import 了 entry.compute）
        sources = [d.source_module for d in deps]
        assert "caller" in sources, "双向模式应收集调用方 → entry 的反向边"
        # 找到反向边
        reverse = [d for d in deps if d.source_module == "caller" and d.target_module == "entry"]
        assert len(reverse) >= 1
        # 反向边的符号是 entry 中的 compute
        assert any(d.symbol == "compute" for d in reverse)

    def test_bidirectional_dedup(self):
        """同一 source/target/symbol 不重复出现。"""
        source_files = {"entry": _ENTRY, "utils": _UTILS}
        deps = analyze_cross_file_deps("entry", source_files, bidirectional=True)
        keys = [(d.source_module, d.target_module, d.symbol) for d in deps]
        assert len(keys) == len(set(keys))

    def test_bidirectional_no_caller_only_forward(self):
        """只有正向依赖（无模块 import entry）时，双向 == 单向。"""
        source_files = {"entry": _ENTRY, "utils": _UTILS}
        unidirectional = analyze_cross_file_deps("entry", source_files, bidirectional=False)
        bidirectional = analyze_cross_file_deps("entry", source_files, bidirectional=True)
        # 数量相同（无反向边）
        assert len(bidirectional) == len(unidirectional)


class TestBidirectionalSwitch:
    """环境变量开关。"""

    def test_default_false(self, monkeypatch):
        monkeypatch.delenv("CROSS_FILE_BIDIRECTIONAL", raising=False)
        assert cross_file_bidirectional() is False

    def test_true(self, monkeypatch):
        monkeypatch.setenv("CROSS_FILE_BIDIRECTIONAL", "true")
        assert cross_file_bidirectional() is True

    def test_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("CROSS_FILE_BIDIRECTIONAL", "TRUE")
        assert cross_file_bidirectional() is True

    def test_invalid_value_false(self, monkeypatch):
        monkeypatch.setenv("CROSS_FILE_BIDIRECTIONAL", "yes")
        assert cross_file_bidirectional() is False


class TestFindSymbolDefLine:
    """符号定义行定位（def/class/赋值）。"""

    def test_def_line(self):
        from src.tools.cross_file import _find_symbol_def_line

        source_files = {"m": "import x\n\ndef foo(a):\n    return a\n"}
        assert _find_symbol_def_line("m", source_files, "foo") == 3

    def test_class_line(self):
        from src.tools.cross_file import _find_symbol_def_line

        source_files = {"m": "class Foo:\n    pass\n"}
        assert _find_symbol_def_line("m", source_files, "Foo") == 1

    def test_assignment_line(self):
        from src.tools.cross_file import _find_symbol_def_line

        source_files = {"m": "CONST = 42\n"}
        assert _find_symbol_def_line("m", source_files, "CONST") == 1

    def test_missing_symbol_returns_zero(self):
        from src.tools.cross_file import _find_symbol_def_line

        source_files = {"m": "def foo():\n    pass\n"}
        assert _find_symbol_def_line("m", source_files, "bar") == 0

    def test_missing_module_returns_zero(self):
        from src.tools.cross_file import _find_symbol_def_line

        assert _find_symbol_def_line("nope", {}, "foo") == 0
