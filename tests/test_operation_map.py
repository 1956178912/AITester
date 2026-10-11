"""操作图行为锁（build_operation_map，结构接地·SPARC 第 2 阶段，2026-10-10）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.operation_map import build_operation_map, build_operation_map_section


class TestBuildOperationMap:
    def test_function_signature_with_annotations(self) -> None:
        omap = build_operation_map("def add(a: int, b: int = 0) -> int:\n    return a + b\n")
        # ast.unparse 对带默认值的参数不保留等号两侧空格（int=0），匹配其实际输出
        assert omap["functions"] == ["def add(a: int, b: int=0) -> int"]

    def test_class_and_methods(self) -> None:
        omap = build_operation_map(
            "class Stack:\n    def push(self, x: int) -> None:\n        pass\n"
            "    def pop(self) -> int:\n        return 0\n"
        )
        assert omap["classes"][0].startswith("class Stack")
        assert "    def push(self, x: int) -> None" in omap["classes"]
        assert "    def pop(self) -> int" in omap["classes"]

    def test_constants_upper_case_only(self) -> None:
        omap = build_operation_map("MAX_SIZE = 100\nrate = 0.5\nDEFAULT_NAME = 'x'\n")
        names = {c.split(" = ")[0] for c in omap["constants"]}
        assert names == {"MAX_SIZE", "DEFAULT_NAME"}

    def test_imports_collected(self) -> None:
        omap = build_operation_map("import os\nfrom typing import List, Optional\nimport sys as s\n")
        assert "import os" in omap["imports"]
        assert "from typing import List, Optional" in omap["imports"]
        assert "import sys as s" in omap["imports"]

    def test_syntax_error_conservative(self) -> None:
        omap = build_operation_map("def f(:\n    return 1\n")
        assert omap == {"functions": [], "classes": [], "constants": [], "imports": []}

    def test_nested_function_not_top_level(self) -> None:
        """嵌套函数不计入顶层 functions（操作图只列可独立调用的顶层符号）。"""
        omap = build_operation_map("def outer():\n    def inner():\n        return 1\n    return inner()\n")
        assert "inner" not in " ".join(omap["functions"])


class TestBuildOperationMapSection:
    def test_empty_returns_empty(self) -> None:
        assert build_operation_map_section(None) == ""
        assert build_operation_map_section({"functions": [], "classes": [], "constants": []}) == ""

    def test_renders_symbols(self) -> None:
        omap = build_operation_map("def helper(x: int) -> int:\n    return x\n")
        section = build_operation_map_section(omap)
        assert "操作图" in section
        assert "def helper(x: int) -> int" in section
        assert "不得编造" in section
