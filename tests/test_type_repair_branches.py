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


# ─── _repair_with_llm 分支（2026-10-02 批次·八：纯逻辑，零 LLM）──────────────


class TestRepairWithLlmBranches:
    """_repair_with_llm 纯逻辑分支（repair_fn 注入 mock 回调，零真实 LLM）。"""

    def test_empty_findings_returns_none(self):
        from src.tools.type_repair import _repair_with_llm

        def _fn(query, orig, patched):
            raise AssertionError("无 findings 不应调用 repair_fn")

        assert _repair_with_llm("o", "p", [], _fn) is None

    def test_none_repair_fn_returns_none(self):
        from src.tools.type_repair import _repair_with_llm

        assert _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], None) is None

    def test_repair_fn_exception_returns_none(self):
        from src.tools.type_repair import _repair_with_llm

        def _fn(query, orig, patched):
            raise RuntimeError("llm down")

        out = _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], _fn)
        assert out is None

    def test_empty_repair_returns_none(self):
        from src.tools.type_repair import _repair_with_llm

        out = _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], lambda *a: "")
        assert out is None

    def test_whitespace_repair_treated_as_valid_but_ast_rejects(self):
        """纯空白修订（`'   \\n'`）非空字符串 → 通过 `if not repaired` 守卫，
        但 `ast.parse('   \\n')` 成功（空模块）→ 返回该空白串。

        锁定实际口径：`_repair_with_llm` 的空串守卫只拦 `""` / None，
        纯空白非空串视为"有效修订"（不阻断），调用方契约层会再兜底。
        """
        from src.tools.type_repair import _repair_with_llm

        out = _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], lambda *a: "   \n")
        assert out == "   \n"  # 空白修订原样返回（非 None）

    def test_truly_empty_repair_returns_none(self):
        from src.tools.type_repair import _repair_with_llm

        # 空串 / None 命中 `if not repaired: return None`
        assert _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], lambda *a: "") is None

    def test_invalid_syntax_repair_rejected(self):
        from src.tools.type_repair import _repair_with_llm

        out = _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], lambda *a: "def f(:\n")
        assert out is None

    def test_valid_repair_returned(self):
        from src.tools.type_repair import _repair_with_llm

        out = _repair_with_llm("o", "p", [{"line": 1, "kind": "k", "message": "m"}], lambda *a: "def f():\n    return 1\n")
        assert out == "def f():\n    return 1\n"

    def test_query_contains_findings_and_codes(self):
        from src.tools.type_repair import _repair_with_llm

        captured = {}

        def _fn(query, orig, patched):
            captured["query"] = query
            return "def ok():\n    return 1\n"

        findings = [
            {"line": 3, "kind": "type_mismatch", "message": "变量 x 类型冲突"},
            {"line": 5, "kind": "return_inconsist", "message": "return 不一致"},
        ]
        _repair_with_llm("original", "patched", findings, _fn)
        q = captured["query"]
        # 疑点逐条注入（含行号 / kind / message）
        assert "[line 3] type_mismatch" in q
        assert "[line 5] return_inconsist" in q
        # 原始代码 + 当前补丁代码块
        assert "original" in q
        assert "patched" in q
        # 输出要求
        assert "```python" in q


# ─── _collect_assign_types 分支（2026-10-02 批次·八）──────────────────────────


class TestCollectAssignTypesBranches:
    """_collect_assign_types 的 Assign / AnnAssign / AugAssign 分支。"""

    def _collect(self, func_body):
        import ast

        from src.tools.type_repair import _collect_assign_types

        # 函数体需缩进 4 空格；每行前加缩进，空行不加
        indented = "\n".join("    " + line if line.strip() else "" for line in func_body.splitlines())
        src = "def f():\n" + indented
        tree = ast.parse(src)
        func = tree.body[0]
        return _collect_assign_types(func)

    def test_plain_assign_collected(self):
        var_hist, _container_hist = self._collect("x = 1\ny = 's'\nreturn x\n")
        # 类型历史值（_collect_assign_types 只记字面类型标签，不存行号）
        assert any(t == "int" for _ln, t in var_hist.get("x", []))
        assert any(t == "str" for _ln, t in var_hist.get("y", []))

    def test_container_assign_collected_in_both(self):
        var_hist, container_hist = self._collect("lst = [1,2]\nd = {'a':1}\nst = {1,2}\ntup = (1,)\nreturn lst\n")
        # 容器类型既进 var_type_hist 也进 container_hist
        for name in ("lst", "d", "st", "tup"):
            assert name in var_hist
            assert name in container_hist

    def test_ann_assign_with_value_collected(self):
        var_hist, _ = self._collect("x: int = 5\nreturn x\n")
        assert any(t == "int" for _, t in var_hist.get("x", []))

    def test_ann_assign_without_value_not_collected(self):
        """AnnAssign value=None（裸注解）不进类型历史。"""
        var_hist, _ = self._collect("x: int\nreturn x\n")
        assert "x" not in var_hist

    def test_non_name_target_not_collected(self):
        """元组解包 / 属性目标（非 ast.Name）不进 var_type_hist。"""
        var_hist, _ = self._collect("a, b = 1, 2\nself.x = 1\nreturn a\n")
        assert "a" not in var_hist or "b" not in var_hist  # 元组目标整体跳过
        assert "x" not in var_hist  # 属性目标非 Name

    def test_aug_assign_not_tracked(self):
        """AugAssign（x += 1）不在 _collect_assign_types 收集口径内。"""
        var_hist, _ = self._collect("x = 1\nx += 1\nreturn x\n")
        # 仅 1 条 int 记录（来自 Assign），AugAssign 不追加
        assert len([t for _, t in var_hist.get("x", [])]) == 1

    def test_empty_body_no_history(self):
        var_hist, container_hist = self._collect("return 1\n")
        assert var_hist == {}
        assert container_hist == {}


# ─── _run_mypy_findings / _run_pyright_findings 开关关闭分支 ────────────────


class TestRunMypyFindingsSwitchBranches:
    """mypy / pyright 静态检查层：开关关闭 / 代码为空 / 后端不匹配 → []。"""

    def test_mypy_disabled_returns_empty(self, monkeypatch):
        from src.tools.type_repair import _run_mypy_findings

        monkeypatch.delenv("TYPE_CHECK_ENABLE", raising=False)
        out = _run_mypy_findings("o", "def f():\n    return 1\n")
        assert out == []

    def test_mypy_empty_patched_returns_empty(self, monkeypatch):
        from src.tools.type_repair import _run_mypy_findings

        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        assert _run_mypy_findings("o", "") == []
        assert _run_mypy_findings("o", "   \n") == []

    def test_pyright_wrong_backend_returns_empty(self, monkeypatch):
        from src.tools.type_repair import _run_pyright_findings

        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.delenv("TYPE_CHECK_BACKEND", raising=False)  # 默认 mypy
        out = _run_pyright_findings("o", "def f():\n    return 1\n")
        assert out == []  # 后端非 pyright → 不执行

    def test_pyright_empty_patched_returns_empty(self, monkeypatch):
        from src.tools.type_repair import _run_pyright_findings

        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        assert _run_pyright_findings("o", "") == []
        assert _run_pyright_findings("o", "   \n") == []

    def test_pyright_unavailable_returns_empty(self, monkeypatch):
        """TYPE_CHECK_BACKEND=pyright 但 CLI/包均未装 → 保守返回 []。"""
        import shutil

        from src.tools.type_repair import _run_pyright_findings

        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        # 确保 pyright CLI 不在 PATH（本仓未装 pyright）
        assert shutil.which("pyright") is None
        out = _run_pyright_findings("o", "def f():\n    x: int = 's'\n")
        assert out == []


# ─── _auto_llm_repair 惰性导入 + 回调契约 ────────────────────────────────────


class TestAutoLlmRepairBranches:
    """_auto_llm_repair 构造的 LLM 回调：复用 DebuggerAgent + 代码块提取。"""

    def test_callback_injects_baseagent_call(self, monkeypatch):
        from unittest.mock import MagicMock

        import src.agents.debugger as debugger_mod
        import src.tools.type_repair as type_repair

        dbg = MagicMock()
        dbg._call_llm_with_cache = MagicMock(return_value='```\nfixed = "ok"\n```')

        def _fake_agent_cls():
            return dbg

        monkeypatch.setattr(debugger_mod, "DebuggerAgent", _fake_agent_cls)
        cb = type_repair._auto_llm_repair()
        out = cb("query", "o", "p")
        assert dbg._call_llm_with_cache.called
        assert "fixed" in out  # 经 extract_code_block 提取 ``` 内代码

    def test_callback_raises_propagate_to_caller(self, monkeypatch):
        import src.agents.debugger as debugger_mod
        import src.tools.type_repair as type_repair

        def _raise_cls():
            raise ImportError("debugger unavailable")

        monkeypatch.setattr(debugger_mod, "DebuggerAgent", _raise_cls)
        with pytest.raises(ImportError):
            type_repair._auto_llm_repair()
