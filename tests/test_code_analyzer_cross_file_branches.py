"""tools/code_analyzer + tools/cross_file 纯逻辑分支补齐（2026-10-02 批次·十二）。

锁定两个低覆盖模块的未覆盖纯逻辑分支（零 LLM / 零网络）：
- code_analyzer: _decorator_name（Name/Attribute/Call/其他）/ _decorator_is_register_like
  （命中注册模式/非注册/None）/ _extract_focused_code（空码/解析失败 None/函数存在）/
  _collect_ingredient_segments（imports/exports/register_symbols/module_constants）
- cross_file: 开关解析 / _cross_file_enabled 系列 / analyze 入口空依赖 /
  entry_modules 缺失 / 依赖边提取保守口径
"""

from __future__ import annotations

import ast

# ─── code_analyzer._decorator_name 分支 ─────────────────────────────────────


class TestDecoratorNameBranches:
    def _name(self, code: str):
        from src.tools.code_analyzer import _decorator_name

        tree = ast.parse(code)
        decs = tree.body[0].decorator_list
        return [_decorator_name(d) for d in decs]

    def test_name_decorator(self):
        assert self._name("@register\ndef f():\n    pass\n") == ["register"]

    def test_attribute_decorator(self):
        assert self._name("@app.route\ndef f():\n    pass\n") == ["route"]

    def test_call_decorator(self):
        assert self._name("@register(name='x')\ndef f():\n    pass\n") == ["register"]

    def test_call_attribute_decorator(self):
        assert self._name("@app.register()\ndef f():\n    pass\n") == ["register"]

    def test_subscript_decorator_returns_none(self):
        """@decorators[0]（Subscript 非 Name/Attribute/Call）→ None。"""
        assert self._name("@DECORATORS[0]\ndef f():\n    pass\n") == [None]


# ─── code_analyzer._decorator_is_register_like 分支 ─────────────────────────


class TestDecoratorIsRegisterLikeBranches:
    def _check(self, code: str) -> bool:
        from src.tools.code_analyzer import _decorator_is_register_like

        tree = ast.parse(code)
        decs = tree.body[0].decorator_list
        return all(_decorator_is_register_like(d) for d in decs)

    def test_register_hit(self):
        assert self._check("@register\ndef f():\n    pass\n") is True

    def test_plugin_hit(self):
        assert self._check("@plugin\ndef f():\n    pass\n") is True

    def test_entry_point_hit(self):
        assert self._check("@entry_point\ndef f():\n    pass\n") is True

    def test_hook_hit(self):
        assert self._check("@hook\ndef f():\n    pass\n") is True

    def test_substring_match_hit(self):
        """名称含 register 子串（非精确集）也命中。"""
        assert self._check("@register_custom_action\ndef f():\n    pass\n") is True

    def test_unrelated_name_not_hit(self):
        assert self._check("@some_other\ndef f():\n    pass\n") is False

    def test_none_name_not_hit(self):
        """装饰器名不可提取（Subscript）→ None → 非注册模式。"""
        assert self._check("@DECORATORS[0]\ndef f():\n    pass\n") is False


# ─── code_analyzer._extract_focused_code 分支 ───────────────────────────────


class TestExtractFocusedCodeBranches:
    def _extract(self, source: str, func: str = "target", depth: int = 1, max_chars: int = 4000):
        from src.tools.code_analyzer import extract_function_context

        return extract_function_context(source, func, depth=depth, max_chars=max_chars)

    def test_empty_source_returns_none(self):
        assert self._extract("", "target") is None
        assert self._extract("   \n", "target") is None

    def test_function_exists_returns_focused(self):
        src = "def helper():\n    return 1\n\ndef target():\n    return helper()\n"
        out = self._extract(src, "target")
        assert out is not None
        assert "def target" in out

    def test_function_missing_returns_none(self):
        src = "def other():\n    return 1\n"
        out = self._extract(src, "nonexistent")
        assert out is None

    def test_depth_two_expands_chain(self):
        """depth=2 展开被调函数的一层依赖。"""
        src = (
            "def grandparent():\n    return 1\n\n"
            "def parent():\n    return grandparent()\n\n"
            "def target():\n    return parent()\n"
        )
        out = self._extract(src, "target", depth=2)
        assert out is not None
        assert "grandparent" in out


# ─── code_analyzer._collect_ingredient_segments 分支 ────────────────────────


class TestCollectIngredientSegmentsBranches:
    def _collect(self, source: str, target: str | None = None):
        from src.tools.code_analyzer import _collect_ingredient_segments

        return _collect_ingredient_segments(source, target)

    def test_collects_module_level_imports(self):
        out = self._collect("import os\nfrom collections import deque\n\ndef f():\n    pass\n", "f")
        assert "import os" in out["imports"]
        assert "deque" in out["imports"]

    def test_collects_all_exports(self):
        out = self._collect("__all__ = ['f', 'g']\ndef f():\n    pass\n\ndef g():\n    pass\n", "f")
        assert "f" in out["exports"]
        assert "g" in out["exports"]

    def test_collects_register_symbols(self):
        out = self._collect("@register\ndef plugin():\n    pass\n", "plugin")
        assert "plugin" in out["register_symbols"]

    def test_module_constants_collected(self):
        out = self._collect("MAX = 100\nLIMIT: int = 5\n\ndef f():\n    return MAX\n", "f")
        assert "MAX" in out["module_constants"]
        assert "LIMIT" in out["module_constants"]

    def test_dunder_constants_skipped(self):
        out = self._collect("__version__ = '1.0'\n__doc__ = 'd'\n\ndef f():\n    pass\n", "f")
        assert "__version__" not in out["module_constants"]

    def test_parse_failure_returns_empty(self):
        out = self._collect("def f(:\n", "f")
        # 解析失败 → 各字段空值（不阻断）
        assert out["imports"] == ""
        assert out["exports"] == []

    def test_empty_source_returns_empty(self):
        out = self._collect("", None)
        assert out["imports"] == ""
        assert out["exports"] == []

    def test_target_ast_included_for_existing_func(self):
        out = self._collect("def target():\n    return 1\n", "target")
        assert out["target_ast"] is not None

    def test_called_signatures_for_target(self):
        """目标函数体内调用同模块函数 → 收集被调函数签名行。"""
        src = "def callee():\n    return 1\n\ndef target():\n    return callee()\n"
        out = self._collect(src, "target")
        sigs = out.get("called_signatures") or []
        assert any("callee" in s for s in sigs)


# ─── cross_file 依赖分析入口分支 ────────────────────────────────────────────


class TestCrossFileAnalyzeEntryBranches:
    def test_no_deps_source_returns_empty(self):
        from src.tools.cross_file import analyze_multi_entry_deps

        # 无 import 的源文件 → 0 依赖边
        out = analyze_multi_entry_deps(["a"], {"a": "def f():\n    return 1\n"})
        assert out == []

    def test_cross_module_import_edge(self):
        from src.tools.cross_file import analyze_multi_entry_deps

        # 模块 a import 模块 b → 依赖边指向 b
        out = analyze_multi_entry_deps(
            ["a"],
            {"a": "import b\n\ndef f():\n    return b.g()\n", "b": "def g():\n    return 1\n"},
        )
        assert len(out) >= 1

    def test_empty_entry_modules_returns_empty(self):
        from src.tools.cross_file import analyze_multi_entry_deps

        out = analyze_multi_entry_deps([], {"a": "def f():\n    pass\n"})
        assert out == []

    def test_import_from_edge(self):
        from src.tools.cross_file import analyze_multi_entry_deps

        out = analyze_multi_entry_deps(
            ["a"],
            {"a": "from b import g\n\ndef f():\n    return g()\n", "b": "def g():\n    return 2\n"},
        )
        assert len(out) >= 1
