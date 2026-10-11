"""路径枚举行为锁（enumerate_paths，结构接地·SPARC 第 1 阶段，2026-10-10）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tools.control_flow import build_paths_prompt_section, enumerate_paths


class TestEnumeratePaths:
    def test_no_branch_single_path(self) -> None:
        result = enumerate_paths("def f(x):\n    return x + 1\n")
        assert result["func_name"] == "f"
        assert result["truncated"] is False
        assert len(result["paths"]) == 1
        assert result["paths"][0]["conditions"] == []

    def test_single_if_two_paths(self) -> None:
        result = enumerate_paths("def f(x):\n    if x > 0:\n        return 1\n    return 0\n")
        assert len(result["paths"]) == 2
        conds = [tuple(p["conditions"]) for p in result["paths"]]
        assert ("满足 x > 0",) in conds
        assert ("不满足 x > 0",) in conds

    def test_if_else_two_paths(self) -> None:
        result = enumerate_paths("def f(x):\n    if x:\n        return 1\n    else:\n        return 2\n")
        assert len(result["paths"]) == 2

    def test_elif_chain_three_paths(self) -> None:
        result = enumerate_paths(
            "def f(x):\n"
            "    if x > 0:\n        return 1\n"
            "    elif x == 0:\n        return 0\n"
            "    else:\n        return -1\n"
        )
        assert len(result["paths"]) == 3

    def test_nested_if_four_paths(self) -> None:
        result = enumerate_paths(
            "def f(a, b):\n"
            "    if a:\n"
            "        if b:\n            return 1\n"
            "        else:\n            return 2\n"
            "    else:\n"
            "        if b:\n            return 3\n"
            "        else:\n            return 4\n"
        )
        # 外层 a 真/假，内层 b 真/假 → 4 条独立路径
        assert len(result["paths"]) == 4

    def test_loop_three_boundaries(self) -> None:
        result = enumerate_paths("def f(xs):\n    for x in xs:\n        print(x)\n    return 0\n")
        assert len(result["paths"]) == 3
        labels = {p["conditions"][0] for p in result["paths"]}
        assert labels == {"循环 0次迭代", "循环 1次迭代", "循环 N次迭代"}

    def test_truncation_at_limit(self) -> None:
        # 3 个连续 if → 8 条路径，max_paths=3 应截断
        result = enumerate_paths(
            "def f(a, b, c):\n"
            "    if a:\n        x = 1\n"
            "    if b:\n        x = 2\n"
            "    if c:\n        x = 3\n    return x\n",
            max_paths=3,
        )
        assert result["truncated"] is True
        assert len(result["paths"]) == 3

    def test_syntax_error_conservative(self) -> None:
        result = enumerate_paths("def f(:\n    return 1\n")
        assert result["paths"] == []
        assert result["truncated"] is False

    def test_missing_function_conservative(self) -> None:
        result = enumerate_paths("x = 1\n", func_name="nonexistent")
        assert result["paths"] == []


class TestBuildPathsPromptSection:
    def test_single_path_returns_empty(self) -> None:
        result = enumerate_paths("def f(x):\n    return x\n")
        assert build_paths_prompt_section(result) == ""

    def test_multi_path_renders(self) -> None:
        result = enumerate_paths("def f(x):\n    if x > 0:\n        return 1\n    return 0\n")
        section = build_paths_prompt_section(result)
        assert "独立执行路径" in section
        assert "路径 1" in section and "路径 2" in section

    def test_none_returns_empty(self) -> None:
        assert build_paths_prompt_section(None) == ""
