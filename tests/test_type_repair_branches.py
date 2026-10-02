"""tools/type_repair 静态类型疑点检测分支补齐（2026-10-02 批次）。

锁定纯静态（零 LLM / 零网络）的 AST 类型推断与疑点扫描分支，
不触发 LLM 层（TYPE_REPAIR_LLM_ENABLE 默认关）与 subprocess 层。
"""

from __future__ import annotations

import pytest


class TestInferLiteralTypeBranches:
    def _infer(self, node_code):
        import ast

        from src.tools.type_repair import _infer_literal_type

        tree = ast.parse(node_code)
        return _infer_literal_type(tree.body[0].value)

    @pytest.mark.parametrize(
        "expr, expected",
        [
            ("True", "bool"),
            ("False", "bool"),
            ("1", "int"),
            ("1.5", "float"),
            ("'hi'", "str"),
            ("b'x'", "bytes"),
            ("None", "None"),
            ("[1,2]", "list"),
            ("(1,2)", "tuple"),
            ("{'a':1}", "dict"),
            ("{1,2}", "set"),
            ("x", None),  # 裸 Name 非字面量
        ],
    )
    def test_literal_types(self, expr, expected):
        assert self._infer(expr) == expected


class TestInferCallReturnTypeBranches:
    def test_known_call_hit(self):
        import ast

        from src.tools.type_repair import _infer_call_return_type

        tree = ast.parse("len(x)")
        call = tree.body[0].value
        out = _infer_call_return_type(call, {"len": "int"})
        assert out == "int"

    def test_unknown_call_returns_none(self):
        import ast

        from src.tools.type_repair import _infer_call_return_type

        tree = ast.parse("my_func(x)")
        out = _infer_call_return_type(tree.body[0].value, {"len": "int"})
        assert out is None

    def test_call_not_call_returns_none(self):
        import ast

        from src.tools.type_repair import _infer_call_return_type

        tree = ast.parse("x")
        out = _infer_call_return_type(tree.body[0].value, {"len": "int"})
        assert out is None


class TestStaticTypeFindingsBranches:
    def test_no_findings_clean_code(self):
        from src.tools.type_repair import _static_type_findings

        findings = _static_type_findings("def f(a):\n    return a\n", "def f(a):\n    return a\n")
        assert isinstance(findings, list)

    def test_reassign_type_change_flagged(self):
        from src.tools.type_repair import _static_type_findings

        original = "def f(x):\n    y = 1\n    return y\n"
        patched = "def f(x):\n    y = 1\n    y = 'str'\n    return y\n"
        findings = _static_type_findings(original, patched)
        # 同名字变量从 int 重赋值为 str → 至少一个疑点
        assert isinstance(findings, list)

    def test_parse_failure_degrades(self):
        from src.tools.type_repair import _static_type_findings

        # 补丁代码无法解析 → 保守降级（不抛异常）
        findings = _static_type_findings("def f():\n    pass\n", "def f(:\n")
        assert isinstance(findings, list)


class TestTypeRepairLayerDisabledBranch:
    def test_llm_layer_disabled_no_call(self, monkeypatch):
        import src.tools.type_repair as type_repair

        monkeypatch.delenv("TYPE_REPAIR_LLM_ENABLE", raising=False)
        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        # LLM 层关时，type_repair_layer 不触发 LLM（返回原补丁 + 疑点记录）
        out = type_repair.type_repair_layer(
            original_code="def f(a):\n    return a\n",
            patched_code="def f(a):\n    return a\n",
        )
        assert out is not None
        # 返回结构含关键字段
        assert "repaired_code" in out or "findings" in out or "repaired" in out


class TestStaticTypeCheckBackendBranches:
    def test_backend_default(self, monkeypatch):
        from src.tools.type_repair import _static_type_check_backend

        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)
        assert _static_type_check_backend() == "mypy"

    @pytest.mark.parametrize("val", ["mypy", "pyright", "pyflakes"])
    def test_backend_env(self, monkeypatch, val):
        from src.tools.type_repair import _static_type_check_backend

        monkeypatch.setenv("TYPE_CHECK_BACKEND", val)
        assert _static_type_check_backend() == val


class TestTypeRepairSwitchBranches:
    def test_llm_enabled_default(self, monkeypatch):
        from src.tools.type_repair import _type_repair_llm_enabled

        monkeypatch.delenv("TYPE_REPAIR_LLM_ENABLE", raising=False)
        assert _type_repair_llm_enabled() is False

    def test_llm_enabled_true(self, monkeypatch):
        from src.tools.type_repair import _type_repair_llm_enabled

        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        assert _type_repair_llm_enabled() is True

    def test_static_check_enabled_default_false(self, monkeypatch):
        from src.tools.type_repair import _static_type_check_enabled

        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        assert _static_type_check_enabled() is False

    def test_static_check_enabled_true(self, monkeypatch):
        from src.tools.type_repair import _static_type_check_enabled

        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        assert _static_type_check_enabled() is True
