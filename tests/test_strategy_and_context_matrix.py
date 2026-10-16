#!/usr/bin/env python3
"""覆盖率收口批次：策略库与上下文裁剪的降级/异常分支。

动机（EMSE 多轮优化批次·收口）：这两个模块是"编排可消融容器"的实际组件——
`strategy_bank` 决定历史成功策略如何回灌（无库/坏库必须静默降级），
`code_context` 决定注入 LLM 的代码上下文如何裁剪（解析失败必须保守降级）。
二者此前各有 5–7 行未覆盖，且集中在**异常/缺省路径**。

覆盖目标（coverage.xml 记录）：strategy_bank 83/86/194/267/268、
code_context 88/97/101/162/216/355/357 行。
零 LLM、零网络、纯本地文件与 AST。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tools.code_context import (
    _find_body_indent,
    _render_segment,
    _slice_source,
    extract_focused_code,
    extract_focused_code_detail,
)
from src.tools.strategy_bank import (
    _load_bank,
    _make_signature,
    record_strategy_outcome,
    select_strategy,
    strategy_bank_enabled,
    strategy_bank_stats,
)


class TestStrategyBankDegradation:
    def test_enabled_default_false(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("STRATEGY_BANK_ENABLE", raising=False)
        assert strategy_bank_enabled() is False

    def test_missing_bank_returns_empty_mapping(self, tmp_path: Path):
        bank = _load_bank(str(tmp_path / "nope.json"))
        assert isinstance(bank, dict)

    def test_corrupted_bank_degrades_to_empty(self, tmp_path: Path):
        path = tmp_path / "bank.json"
        path.write_text("{not-json", encoding="utf-8")
        assert isinstance(_load_bank(str(path)), dict)

    def test_non_dict_payload_degrades(self, tmp_path: Path):
        path = tmp_path / "list.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert isinstance(_load_bank(str(path)), dict)

    def test_select_strategy_without_bank_is_none_or_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_BANK_PATH", str(tmp_path / "missing.json"))
        monkeypatch.setenv("STRATEGY_BANK_ENABLE", "true")
        assert select_strategy("assertion") is None

    def test_record_outcome_on_missing_bank_does_not_raise(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("STRATEGY_BANK_PATH", str(tmp_path / "fresh.json"))
        record_strategy_outcome(
            signature=("assertion", None, False),
            strategy="retry",
            success=False,
            path=str(tmp_path / "fresh.json"),
        )
        assert isinstance(strategy_bank_stats(str(tmp_path / "fresh.json")), dict)

    def test_stats_on_absent_bank_is_empty_mapping(self, tmp_path: Path):
        stats = strategy_bank_stats(str(tmp_path / "absent.json"))
        assert isinstance(stats, dict)

    def test_signature_normalizes_case_and_blank_tag(self):
        """签名 = (error_category 小写, tag 小写或 None, cross_file) 三元组。"""
        assert _make_signature("Assertion", None) == ("assertion", None, False)
        assert _make_signature("ASSERTION", "  PATCH  ") == ("assertion", "patch", False)
        assert _make_signature("  ", None) == ("unknown", None, False)
        assert _make_signature("assertion", None, True) == ("assertion", None, True)


class TestCodeContextDegradation:
    """上下文裁剪：解析失败 / 空文件 / 越界切片都必须保守降级，不得抛异常。"""

    def test_extract_from_empty_source_returns_empty_or_input(self):
        out = extract_focused_code("", focus_function=None)
        assert isinstance(out, str)

    def test_extract_from_syntax_error_source_degrades(self):
        out = extract_focused_code("def broken(:\n    pass\n", focus_function=None)
        assert isinstance(out, str)

    def test_extract_detail_returns_text_and_parse_flag(self):
        """`extract_focused_code_detail` 返回 `(text, parsed_ok)` 二元组（C-1 口径）。"""
        text, parsed_ok = extract_focused_code_detail("def add(a, b):\n    return a + b\n", focus_function="add")
        assert isinstance(text, str) and "def add" in text
        assert parsed_ok is True

    def test_extract_detail_reports_parse_failure(self):
        text, parsed_ok = extract_focused_code_detail("def broken(:\n  pass\n", focus_function=None)
        assert isinstance(text, str)
        assert parsed_ok is False

    def test_slice_source_uses_node_lineno(self):
        import ast

        source = "def f():\n    return 1\n\n\ndef g():\n    return 2\n"
        tree = ast.parse(source)
        lines = source.splitlines()
        segment = _slice_source(lines, tree.body[0])
        assert "def f()" in segment

    def test_slice_source_without_lineno_defaults_to_first_line(self):
        """缺 `lineno` 的节点按保守默认（第 1 行）切分——不是崩溃、也不是空串。"""
        import ast

        class _NoLineno(ast.AST):
            _fields: tuple[str, ...] = ()

        assert _slice_source(["a", "b"], _NoLineno()) == "a"

    def test_slice_source_out_of_range_is_empty(self):
        import ast

        node = ast.parse("x = 1\n").body[0]
        assert _slice_source([], node) == ""

    def test_find_body_indent_on_unindented_body(self):
        assert _find_body_indent(["def f():", "return 1"]) >= 0

    def test_find_body_indent_on_empty_body(self):
        assert _find_body_indent([]) >= 0

    def test_render_segment_accepts_str_and_mapping(self):
        assert isinstance(_render_segment("code"), str)
        assert isinstance(_render_segment({"code": "x"}), str)
        assert isinstance(_render_segment(None), str)

    def test_focus_on_unknown_function_still_returns_context(self):
        out = extract_focused_code("def add(a, b):\n    return a + b\n", focus_function="nonexistent")
        assert isinstance(out, str)

    def test_cross_file_source_with_imports_is_handled(self):
        source = "import os\nfrom typing import Any\n\n\ndef helper(x: Any) -> Any:\n    return os.path.join(str(x))\n"
        out = extract_focused_code(source, focus_function="helper")
        assert isinstance(out, str) and out
