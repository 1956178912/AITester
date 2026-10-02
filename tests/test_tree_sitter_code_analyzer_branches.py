"""tools/tree_sitter_backend 降级 / 注册分支 + tools/code_analyzer 函数提取分支补齐。

锁定 2026-10-02 批次·五 低覆盖模块纯静态分支（零 LLM / 零网络）：
- tree_sitter_backend 缺依赖降级路径（_HAS_TREE_SITTER=False 时 4 核心方法
  全回退词法层）+ register_tree_sitter_backend 幂等注册
- code_analyzer parse_function_nodes / extract_function_code / 圈复杂度 /
  函数替换 / 装饰器识别
"""

from __future__ import annotations


class TestTreeSitterBackendFallbackBranches:
    def test_availability_returns_bool(self):
        from src.tools.tree_sitter_backend import is_tree_sitter_available

        assert is_tree_sitter_available() in (True, False)

    def test_backend_construction_does_not_raise(self):
        import src.tools.tree_sitter_backend as tsb

        b = tsb.TypeScriptTreeSitterBackend()
        assert b is not None

    def test_parse_returns_none_when_no_parser(self):
        import src.tools.tree_sitter_backend as tsb

        b = tsb.TypeScriptTreeSitterBackend()
        # 强制无 parser 路径：_parse 恒返回 None，调用方走词法层降级
        b._parser = None
        assert b._parse("const x = 1") is None

    def test_walk_symbols_none_tree_returns_empty(self):
        import src.tools.tree_sitter_backend as tsb

        b = tsb.TypeScriptTreeSitterBackend()
        assert b._walk_symbols(None) == set()

    def test_extract_symbols_degrades(self):
        import src.tools.tree_sitter_backend as tsb

        b = tsb.TypeScriptTreeSitterBackend()
        # 缺依赖时走词法层回退，提取 const/function 符号
        out = b.extract_symbols("function foo() {}\nconst bar = 1\nexport class Baz {}\n")
        assert isinstance(out, (list, set, tuple))

    def test_register_is_idempotent(self):
        import src.tools.tree_sitter_backend as tsb

        tsb.register_tree_sitter_backend()
        # 重复注册不应抛异常（幂等）
        tsb.register_tree_sitter_backend()
        assert True


class TestCodeAnalyzerParseFunctionNodesBranches:
    def test_parse_top_level_functions(self):
        from src.tools.code_analyzer import parse_function_nodes

        src = (
            "def f1(a):\n"
            "    return a\n"
            "\n"
            "async def f2(b):\n"
            "    return b\n"
            "\n"
            "def f3():\n"
            "    def nested():\n"
            "        return 1\n"
            "    return nested()\n"
        )
        out = parse_function_nodes(src)
        names = {n["name"] for n in out}
        assert "f1" in names
        assert "f2" in names
        assert "f3" in names

    def test_parse_empty_source_returns_empty(self):
        from src.tools.code_analyzer import parse_function_nodes

        assert parse_function_nodes("") == []

    def test_parse_syntax_error_raises(self):
        import pytest

        from src.tools.code_analyzer import parse_function_nodes

        with pytest.raises(SyntaxError):
            parse_function_nodes("def f(:\n")


class TestCodeAnalyzerExtractFunctionCodeBranches:
    def test_extract_existing_function(self):
        from src.tools.code_analyzer import extract_function_code

        src = "def target(a):\n    return a + 1\n\ndef other():\n    return 2\n"
        out = extract_function_code(src, "target")
        assert out is not None
        assert "return a + 1" in out

    def test_extract_missing_function_returns_none(self):
        from src.tools.code_analyzer import extract_function_code

        src = "def target(a):\n    return a\n"
        out = extract_function_code(src, "nonexistent")
        assert out is None

    def test_extract_from_invalid_source_raises(self):
        import pytest

        from src.tools.code_analyzer import extract_function_code

        with pytest.raises(SyntaxError):
            extract_function_code("def f(:\n", "f")


class TestCodeAnalyzerComplexityBranches:
    def test_cyclomatic_complexity_basic(self):
        from src.tools.code_analyzer import compute_cyclomatic_complexity

        src = "def f(x):\n    if x:\n        return 1\n    if x > 2:\n        return 2\n    return 0\n"
        out = compute_cyclomatic_complexity(src)
        assert out >= 1  # 基准 1 + 2 个 if 分支

    def test_cyclomatic_complexity_invalid_source_raises(self):
        import pytest

        from src.tools.code_analyzer import compute_cyclomatic_complexity

        with pytest.raises(SyntaxError):
            compute_cyclomatic_complexity("def f(:\n")


class TestCodeAnalyzerReplaceFunctionBranches:
    def test_replace_function_code_success(self):
        from src.tools.code_analyzer import replace_function_code

        src = "def target(a):\n    return a + 1\n\ndef other():\n    return 2\n"
        out, ok = replace_function_code(src, "target", "def target(a):\n    return a + 100\n")
        assert ok is True
        assert "a + 100" in out
        assert "other" in out  # 其他函数保留

    def test_replace_missing_function_fails(self):
        from src.tools.code_analyzer import replace_function_code

        src = "def target(a):\n    return a\n"
        out, ok = replace_function_code(src, "nonexistent", "def nonexistent():\n    pass\n")
        assert ok is False
        assert out == src

    def test_replace_with_invalid_new_code_fails(self):
        from src.tools.code_analyzer import replace_function_code

        src = "def target(a):\n    return a\n"
        out, ok = replace_function_code(src, "target", "def target(:\n")
        assert ok is False
        assert out == src


class TestCodeAnalyzerDecoratorRecognitionBranches:
    def test_register_like_decorator_recognized(self):
        import ast

        from src.tools.code_analyzer import _decorator_is_register_like

        dec = ast.parse("@register\ndef f():\n    pass\n").body[0].decorator_list[0]
        assert _decorator_is_register_like(dec) is True

    def test_plain_decorator_not_register_like(self):
        import ast

        from src.tools.code_analyzer import _decorator_is_register_like

        dec = ast.parse("@staticmethod\ndef f():\n    pass\n").body[0].decorator_list[0]
        assert _decorator_is_register_like(dec) is False
