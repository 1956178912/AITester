"""tools/control_flow 纯静态 CFG 分析分支补齐（2026-10-02 批次·六）。

锁定 control_flow.py 零 LLM / 零网络的纯 AST 静态分析分支：
- analyze_control_flow 分支/循环/异常/出口提取 + 不可解析降级
- _function_node 按名取 / None 取首 / 缺失
- _cond_expr_text / _exc_type_name 各形态
- build_cfg_prompt_section 开关 / 空摘要 / 非空
"""

from __future__ import annotations


class TestAnalyzeControlFlowBranches:
    def test_full_function_analysis(self):
        from src.tools.control_flow import analyze_control_flow

        code = "def f(x):\n    if x > 0:\n        return x\n    for i in range(3):\n        x += i\n    return x\n"
        out = analyze_control_flow(code, "f")
        assert out["func_name"] == "f"
        assert len(out["branch_conditions"]) >= 1
        assert len(out["loop_boundaries"]) >= 1
        assert len(out["return_points"]) >= 1
        assert out["cyclomatic_estimate"] >= 2

    def test_unparseable_returns_empty(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("def f(:\n", "f")
        assert out["branch_conditions"] == []
        assert out["cyclomatic_estimate"] == 1

    def test_no_function_returns_empty(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("x = 1\n", "f")
        # 代码可解析但无目标函数 → 全空摘要（cyclomatic 基准 1）
        assert out["branch_conditions"] == []
        assert out["cyclomatic_estimate"] == 1

    def test_exception_paths_captured(self):
        from src.tools.control_flow import analyze_control_flow

        code = "def f(x):\n    try:\n        int(x)\n    except ValueError:\n        return -1\n    return 0\n"
        out = analyze_control_flow(code, "f")
        assert len(out["exception_paths"]) >= 1


class TestFunctionNodeBranches:
    def test_by_name(self):
        from src.tools.control_flow import _function_node

        out = _function_node("def a():\n    pass\n\ndef b():\n    pass\n", "b")
        assert out is not None and out.name == "b"

    def test_none_takes_first(self):
        from src.tools.control_flow import _function_node

        out = _function_node("def a():\n    pass\n", None)
        assert out is not None and out.name == "a"

    def test_missing_returns_none(self):
        from src.tools.control_flow import _function_node

        assert _function_node("def a():\n    pass\n", "zzz") is None


class TestBuildCfgPromptSectionBranches:
    def test_disabled_returns_empty(self, monkeypatch):
        from src.tools.control_flow import build_cfg_prompt_section

        monkeypatch.setenv("CFG_ANALYSIS_ENABLE", "false")
        assert build_cfg_prompt_section({"path_hint": "x", "func_name": "f"}) == ""

    def test_none_cfg_returns_empty(self, monkeypatch):
        from src.tools.control_flow import build_cfg_prompt_section

        monkeypatch.delenv("CFG_ANALYSIS_ENABLE", raising=False)
        assert build_cfg_prompt_section(None) == ""

    def test_non_empty_cfg_produces_section(self, monkeypatch):
        from src.tools.control_flow import build_cfg_prompt_section

        monkeypatch.delenv("CFG_ANALYSIS_ENABLE", raising=False)
        cfg = {"func_name": "f", "path_hint": "控制流摘要"}
        out = build_cfg_prompt_section(cfg)
        assert "控制流摘要" in out
        assert "f" in out


class TestCfgAnalysisEnabledBranches:
    def test_default_true(self, monkeypatch):
        from src.tools.control_flow import cfg_analysis_enabled

        monkeypatch.delenv("CFG_ANALYSIS_ENABLE", raising=False)
        assert cfg_analysis_enabled() is True

    def test_false_values(self, monkeypatch):
        from src.tools.control_flow import cfg_analysis_enabled

        for v in ("false", "0"):
            monkeypatch.setenv("CFG_ANALYSIS_ENABLE", v)
            assert cfg_analysis_enabled() is False


class TestControlFlowDeepBranches:
    """unparse 异常兜底 / except 元组 / return None / 截断等深层分支（2026-10-08 补齐）。"""

    def test_cond_expr_unparse_fallback_to_source(self):
        import ast
        from unittest.mock import patch

        from src.tools.control_flow import _cond_expr_text

        node = ast.parse("x > 0").body[0].value
        with patch("ast.unparse", side_effect=Exception):
            assert _cond_expr_text(node, ["x > 0"]) == "x > 0"

    def test_for_iter_unparse_fallback(self):
        from unittest.mock import patch

        from src.tools.control_flow import analyze_control_flow

        with patch("ast.unparse", side_effect=Exception):
            out = analyze_control_flow("def f():\n    for x in range(10):\n        pass\n")
        assert out["loop_boundaries"][0]["iterator"] == "?"

    def test_except_tuple_types(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow(
            "def f():\n    try:\n        pass\n    except (ValueError, TypeError):\n        pass\n"
        )
        assert out["exception_paths"][0]["types"] == ["ValueError", "TypeError"]

    def test_return_none_value(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("def f():\n    return\n")
        assert out["return_points"][0]["value"] == "None"

    def test_path_hint_truncated(self):
        from unittest.mock import patch

        from src.tools.control_flow import analyze_control_flow

        with patch("src.tools.control_flow._CFG_SUMMARY_MAX_CHARS", 50):
            out = analyze_control_flow(
                "def f(x):\n    if x > 0:\n        return 1\n    elif x < 0:\n        return -1\n    return 0\n"
            )
        assert len(out["path_hint"]) <= 50

    def test_exc_type_name_call(self):
        import ast

        from src.tools.control_flow import _exc_type_name

        node = ast.parse("ValueError()").body[0].value
        assert _exc_type_name(node) == "ValueError"

    def test_exc_type_name_unparse_fallback(self):
        import ast
        from unittest.mock import patch

        from src.tools.control_flow import _exc_type_name

        node = ast.Attribute(value=ast.Name(id="x"), attr="y")
        with patch("ast.unparse", side_effect=Exception):
            assert _exc_type_name(node) == "?"

    def test_cond_expr_unknown_line(self):
        import ast
        from unittest.mock import patch

        from src.tools.control_flow import _cond_expr_text

        node = ast.parse("x > 0").body[0].value
        with patch("ast.unparse", side_effect=Exception):
            assert _cond_expr_text(node, []) == "?"  # line_no 无有效源码行 → "?"

    def test_while_loop_captured(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("def f(x):\n    while x > 0:\n        x -= 1\n    return x\n")
        assert any(lp["kind"] == "while" for lp in out["loop_boundaries"])

    def test_ternary_captured(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("def f(x):\n    return 1 if x > 0 else 0\n")
        assert any("ternary" in b["expr"] for b in out["branch_conditions"])

    def test_raise_captured(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("def f(x):\n    if x < 0:\n        raise ValueError('neg')\n    return x\n")
        assert any(e["kind"] == "raise" for e in out["exception_paths"])

    def test_return_unparse_fallback(self):
        from unittest.mock import patch

        from src.tools.control_flow import analyze_control_flow

        with patch("ast.unparse", side_effect=Exception):
            out = analyze_control_flow("def f(x):\n    return x\n")
        assert out["return_points"][0]["value"] == "?"

    def test_cfg_section_empty_hint(self):
        from src.tools.control_flow import build_cfg_prompt_section

        assert build_cfg_prompt_section({"path_hint": ""}) == ""

    def test_simple_path_hint(self):
        from src.tools.control_flow import analyze_control_flow

        out = analyze_control_flow("def f(x):\n    pass\n")
        assert "控制流简单" in out["path_hint"]
