"""type_repair 深层分支补齐（2026-10-08，78% → 90%+）。

补齐 test_type_repair_branches.py 未覆盖的深层分支：
- _static_type_findings 的 undefined_attr 检测全链路（顶层名/import/局部名收集）；
- _run_mypy_findings 的 mypy 输出解析（高置信度类别过滤 + 异常降级）；
- type_repair_layer 的完整流程（pyright 回退 / 去重 / LLM 自动注入失败 / 契约回环）。
零真实 LLM / 零网络（mypy.api.run 用 mock）。
"""

from __future__ import annotations

import ast
import json
from unittest.mock import MagicMock, patch

from src.tools.type_repair import (
    _infer_call_return_type,
    _infer_literal_type,
    _run_mypy_findings,
    _run_pyright_findings,
    _static_type_findings,
    type_repair_layer,
)

# ═══ 1. undefined_attr 检测全链路（_static_type_findings 顶层可见名收集）══════


class TestUndefinedAttrDetection:
    def test_undefined_attr_detected(self):
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"  # helper 未定义/未导入
        findings = _static_type_findings(original, patched)
        assert any(f["kind"] == "undefined_attr" for f in findings)

    def test_orig_top_assign_is_visible(self):
        # 原代码顶层赋值名（非 __ 开头）是可见名，补丁引用它不报 undefined_attr
        original = "CONST = 1\ndef f():\n    return CONST\n"
        patched = "CONST = 1\ndef f():\n    return CONST\n"
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}

    def test_orig_top_annassign_is_visible(self):
        original = "x: int = 1\ndef f():\n    return x\n"
        patched = original
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}

    def test_imported_name_not_flagged(self):
        original = "import os\ndef f():\n    return os.path\n"
        patched = original
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}

    def test_from_import_not_flagged(self):
        original = "from math import sqrt\ndef f():\n    return sqrt(4)\n"
        patched = original
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}

    def test_patched_locals_not_flagged(self):
        # 函数内局部名（参数/vararg/kwarg/赋值/for/with/except）不报 undefined_attr
        original = "def f():\n    return 1\n"
        patched = (
            "def f(*args, **kwargs):\n"
            "    x = args[0] if args else 0\n"
            "    y = kwargs.get('k', 0)\n"
            "    for i in [1, 2]:\n"
            "        pass\n"
            "    with open('f') as fp:\n"
            "        pass\n"
            "    try:\n"
            "        pass\n"
            "    except Exception as e:\n"
            "        pass\n"
            "    return x\n"
        )
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}

    def test_builtin_name_not_flagged(self):
        # open/len 等内置名不报 undefined_attr（_builtin_allow 白名单）
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return len([])\n"
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}


# ═══ 2. _infer_literal_type 边界（complex 等未知常量）══════════════════════════


class TestInferLiteralTypeEdge:
    def test_complex_constant_returns_none(self):
        node = ast.parse("1j").body[0].value  # complex 字面量
        assert _infer_literal_type(node) is None


# ═══ 3. mypy 输出解析（_run_mypy_findings，mock mypy.api.run）══════════════════


class TestRunMypyFindingsParse:
    def test_mypy_output_parsed(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        out = "patched_code.py:2:1: error: Name 'x' is not defined [name-defined]\n"
        with patch("mypy.api.run", return_value=(1, out, "")):
            findings = _run_mypy_findings("o", "def f():\n    return x\n")
        assert len(findings) == 1
        assert findings[0]["kind"] == "mypy_name_defined"
        assert findings[0]["line"] == 2

    def test_mypy_warning_and_low_confidence_filtered(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        out = (
            "patched_code.py:1:1: warning: low [name-defined]\n"  # warning 跳过
            "patched_code.py:2:1: error: low [no-any-return]\n"  # 低置信度类别跳过
            "patched_code.py:3:1: error: Name 'x' is not defined [name-defined]\n"  # 命中
        )
        with patch("mypy.api.run", return_value=(1, out, "")):
            findings = _run_mypy_findings("o", "def f():\n    return x\n")
        assert len(findings) == 1
        assert findings[0]["kind"] == "mypy_name_defined"

    def test_mypy_exception_degrades_to_empty(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        with patch("mypy.api.run", side_effect=RuntimeError("boom")):
            findings = _run_mypy_findings("o", "def f():\n    return 1\n")
        assert findings == []

    def test_mypy_unmatched_lines_skipped(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        out = (
            "some random non-mypy line\n"  # 不匹配正则 → continue
            "patched_code.py:2:1: error: Name 'x' is not defined [name-defined]\n"
        )
        with patch("mypy.api.run", return_value=(1, out, "")):
            findings = _run_mypy_findings("o", "def f():\n    return x\n")
        assert len(findings) == 1


# ═══ 4. type_repair_layer 完整流程（LLM 层 + 契约回环 + 回退 + 去重）══════════


class TestTypeRepairLayerFullFlow:
    def test_llm_repair_contract_ok(self, monkeypatch):
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"

        def repair_fn(query, original_code, patched_code):
            return "def f():\n    return 1\n"  # 修复后保留 f

        out = type_repair_layer(original, patched, llm_repair=repair_fn)
        assert out["repaired"] is True
        assert out["contract_ok"] is True

    def test_llm_repair_contract_broken(self, monkeypatch):
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"

        def repair_fn(query, original_code, patched_code):
            return "def g():\n    return 1\n"  # 删除了 f → 契约破坏

        out = type_repair_layer(original, patched, llm_repair=repair_fn)
        assert out["repaired"] is False
        assert out["contract_ok"] is False
        assert out["missing_symbols"]  # 缺失符号非空

    def test_llm_repair_no_contract_check(self, monkeypatch):
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"

        def repair_fn(query, original_code, patched_code):
            return "def f():\n    return 1\n"

        out = type_repair_layer(original, patched, llm_repair=repair_fn, enforce_contract=False)
        assert out["repaired"] is True

    def test_llm_auto_inject_failure_static_only(self, monkeypatch):
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"
        with patch("src.tools.type_repair._auto_llm_repair", side_effect=RuntimeError("no agent")):
            out = type_repair_layer(original, patched, llm_repair=None)
        assert out["repaired"] is False  # 注入失败 → 仅静态层

    def test_pyright_backend_falls_back_to_mypy(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"
        with (
            patch("src.tools.type_repair._run_pyright_findings", return_value=[]),
            patch(
                "src.tools.type_repair._run_mypy_findings",
                return_value=[{"file": "patched", "line": 1, "message": "m", "kind": "mypy_x"}],
            ),
        ):
            out = type_repair_layer(original, patched)
        assert out["mypy_findings_count"] == 1  # pyright 空 → 回退 mypy

    def test_mypy_findings_dedup(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"
        # mypy 产出与 ast 层同 (file, line, kind) 的疑点 → 去重后不重复
        # （ast 层 undefined_attr 的 line 恒为 0，须对齐才能触发去重）
        dup = {"file": "patched", "line": 0, "message": "m", "kind": "undefined_attr"}
        with patch("src.tools.type_repair._run_mypy_findings", return_value=[dup]):
            out = type_repair_layer(original, patched)
        # 去重：同 file+line+kind 只保留一条（ast 层优先）
        kinds = [f["kind"] for f in out["findings"]]
        assert kinds.count("undefined_attr") == 1


# ═══ 5. return 不一致 + 局部名完整收集（_static_type_findings 剩余分支）══════


class TestStaticTypeFindingsMoreBranches:
    def test_return_type_inconsistent_flagged(self):
        original = "def f():\n    return 1\n"
        patched = "def f(x):\n    if x:\n        return 1\n    return 'a'\n"  # int 与 str 不一致
        findings = _static_type_findings(original, patched)
        assert any(f["kind"] == "return_inconsist" for f in findings)

    def test_patched_locals_augassign_for_tuple_with(self):
        # AugAssign / AnnAssign / for 元组目标 / with 目标均为局部可见名
        original = "def f():\n    return 1\n"
        patched = (
            "def f():\n"
            "    x = 0\n"
            "    x += 1\n"
            "    for a, b in [(1, 2)]:\n"
            "        pass\n"
            "    with open('f') as fp:\n"
            "        pass\n"
            "    with open('g') as (f1, f2):\n"
            "        pass\n"
            "    return x\n"
        )
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}

    def test_with_no_target_not_flagged(self):
        # with 无 as 目标（optional_vars None）→ continue，不报 undefined_attr
        original = "def f():\n    return 1\n"
        patched = "def f():\n    with open('f'):\n        pass\n    return 1\n"
        findings = _static_type_findings(original, patched)
        assert "undefined_attr" not in {f["kind"] for f in findings}


# ═══ 6. _infer_call_return_type 非 Call 边界 ═══════════════════════════════════


class TestInferCallReturnTypeEdge:
    def test_non_call_returns_none(self):
        node = ast.parse("x").body[0].value  # 非 Call 表达式
        assert _infer_call_return_type(node, {"x": "int"}) is None

    def test_attribute_func_call_returns_none(self):
        # Call 但 func 是 Attribute（如 obj.method()）→ 不查表 → None
        node = ast.parse("obj.method()").body[0].value
        assert _infer_call_return_type(node, {"method": "int"}) is None


# ═══ 7. pyright 后端（_run_pyright_findings，mock CLI/subprocess）═════════════


class TestRunPyrightFindingsParse:
    def test_pyright_cli_json_parsed(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        proc = MagicMock()
        proc.stdout = json.dumps(
            {
                "generalDiagnostics": [
                    {
                        "severity": "error",
                        "rule": "reportUndefinedVariable",
                        "message": "x not defined",
                        "range": {"start": {"line": 1}},
                    }
                ]
            }
        )
        with (
            patch("shutil.which", return_value="/usr/bin/pyright"),
            patch("subprocess.run", return_value=proc),
        ):
            findings = _run_pyright_findings("o", "def f():\n    return x\n")
        assert len(findings) == 1
        assert findings[0]["kind"] == "pyright_reportUndefinedVariable"
        assert findings[0]["line"] == 2  # 0-based + 1

    def test_pyright_json_parse_failure_falls_to_text(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        proc = MagicMock()
        proc.stdout = "path:2:3 - error: x not defined [reportUndefinedVariable]\n"
        with (
            patch("shutil.which", return_value="/usr/bin/pyright"),
            patch("subprocess.run", return_value=proc),
        ):
            findings = _run_pyright_findings("o", "def f():\n    return x\n")
        assert len(findings) == 1
        assert findings[0]["kind"] == "pyright_error"

    def test_pyright_exception_degrades_to_empty(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        with (
            patch("shutil.which", return_value="/usr/bin/pyright"),
            patch("subprocess.run", side_effect=RuntimeError("boom")),
        ):
            findings = _run_pyright_findings("o", "def f():\n    return 1\n")
        assert findings == []

    def test_pyright_severity_and_rule_filtered(self, monkeypatch):
        monkeypatch.setenv("TYPE_CHECK_ENABLE", "true")
        monkeypatch.setenv("TYPE_CHECK_BACKEND", "pyright")
        proc = MagicMock()
        proc.stdout = json.dumps(
            {
                "generalDiagnostics": [
                    # warning 跳过（severity != error）
                    {
                        "severity": "warning",
                        "rule": "reportUndefinedVariable",
                        "message": "w",
                        "range": {"start": {"line": 0}},
                    },
                    # rule 不在白名单跳过
                    {
                        "severity": "error",
                        "rule": "reportLowConfidence",
                        "message": "low",
                        "range": {"start": {"line": 0}},
                    },
                    # 命中
                    {
                        "severity": "error",
                        "rule": "reportUndefinedVariable",
                        "message": "x",
                        "range": {"start": {"line": 1}},
                    },
                ]
            }
        )
        with (
            patch("shutil.which", return_value="/usr/bin/pyright"),
            patch("subprocess.run", return_value=proc),
        ):
            findings = _run_pyright_findings("o", "def f():\n    return x\n")
        assert len(findings) == 1
        assert findings[0]["kind"] == "pyright_reportUndefinedVariable"


# ═══ 8. 契约回环检查异常（type_repair_layer 763-764）══════════════════════════


class TestContractCheckException:
    def test_contract_check_exception_keeps_original(self, monkeypatch):
        monkeypatch.setenv("TYPE_REPAIR_LLM_ENABLE", "true")
        original = "def f():\n    return 1\n"
        patched = "def f():\n    return helper()\n"

        def repair_fn(query, original_code, patched_code):
            return "def f():\n    return 1\n"

        with patch("src.tools.patch_applier.check_naming_contract", side_effect=RuntimeError("boom")):
            out = type_repair_layer(original, patched, llm_repair=repair_fn)
        assert out["repaired"] is False  # 契约检查异常 → 保守保留原补丁
