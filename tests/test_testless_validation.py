"""testless_validation 单元测试（2026-10-08，83% → 95%+）。

此前无专门测试文件（仅被集成间接覆盖 83%）。补齐四层验证
（AST 符号守卫 / mypy / 命名契约 / 导入冒烟）的降级与边界分支：
超时坏值 / 语法错误 / 显式关闭 / 依赖缺失三态化 / 危险 API 拒跑 /
subprocess 超时与失败。mypy/导入冒烟的 subprocess 均 mock，零真实执行。
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from src.tools.testless_validation import (
    _import_smoke_timeout,
    _run_ast_symbol_guard,
    _run_import_smoke_layer,
    _run_mypy_layer,
    _run_naming_contract_layer,
    run_testless_validation,
    testless_validation_enabled,
)

# ═══ 1. 超时解析 + 开关 ══════════════════════════════════════════════════════


class TestTimeoutAndSwitch:
    def test_timeout_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_TIMEOUT", "abc")
        assert _import_smoke_timeout() == 10

    def test_switch_default_off(self, monkeypatch):
        monkeypatch.delenv("TESTLESS_VALIDATION_ENABLE", raising=False)
        assert testless_validation_enabled() is False


# ═══ 2. AST 符号守卫 ═════════════════════════════════════════════════════════


class TestAstSymbolGuard:
    def test_syntax_error_degrades(self):
        # 原始代码解析失败 → 无符号可比较 → 通过（保守）
        result = _run_ast_symbol_guard("def f(:", "def g(): pass")
        assert result["passed"] is True

    def test_added_symbols_detail(self):
        result = _run_ast_symbol_guard("def f(): pass", "def f(): pass\ndef g(): pass")
        assert result["passed"] is True
        assert "新增" in result["detail"]

    def test_removed_symbols_rejected(self):
        result = _run_ast_symbol_guard("def f(): pass\ndef g(): pass", "def f(): pass")
        assert result["passed"] is False
        assert "g" in result["detail"]


# ═══ 3. mypy 层 ══════════════════════════════════════════════════════════════


class TestMypyLayer:
    def test_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("TESTLESS_MYPY_ENABLE", "false")
        result = _run_mypy_layer("def f(): pass", "mod")
        assert result["passed"] is True
        assert "跳过" in result["detail"]

    def test_mypy_unavailable(self):
        import sys

        with patch.dict(sys.modules, {"mypy": None}):
            result = _run_mypy_layer("def f(): pass", "mod")
        assert result["passed"] is True
        assert result.get("infra_degraded") is True

    def test_mypy_passes(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = ""
        proc.stderr = ""
        with patch("subprocess.run", return_value=proc):
            result = _run_mypy_layer("def f(): pass", "mod")
        assert result["passed"] is True
        assert "通过" in result["detail"]

    def test_mypy_execution_failure(self):
        with patch("subprocess.run", side_effect=OSError("no mypy")):
            result = _run_mypy_layer("def f(): pass", "mod")
        assert result["passed"] is True
        assert result.get("infra_degraded") is True

    def test_mypy_finds_errors(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stdout = "file.py:1: error: x [name-defined]"
        proc.stderr = ""
        with patch("subprocess.run", return_value=proc):
            result = _run_mypy_layer("def f():\n    return x\n", "mod")
        assert result["passed"] is False
        assert "mypy 发现" in result["detail"]


# ═══ 4. 命名契约层 ═══════════════════════════════════════════════════════════


class TestNamingContractLayer:
    def test_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("TESTLESS_NAMING_CONTRACT_ENABLE", "false")
        result = _run_naming_contract_layer("def f(): pass", "def g(): pass")
        assert result["passed"] is True
        assert "跳过" in result["detail"]

    def test_passes(self):
        result = _run_naming_contract_layer("def f(): pass", "def f(): pass\ndef g(): pass")
        assert result["passed"] is True

    def test_failed_on_removed_symbol(self):
        result = _run_naming_contract_layer("def f(): pass\ndef g(): pass", "def f(): pass")
        assert result["passed"] is False
        assert "缺失" in result["detail"]


# ═══ 5. 导入冒烟层 ═══════════════════════════════════════════════════════════


class TestImportSmokeLayer:
    def test_dangerous_api_rejected(self):
        original = "def f():\n    return 1\n"
        patched = "import os\nos.system('ls')\n"
        result = _run_import_smoke_layer(original, patched, "mod")
        assert result["passed"] is False
        assert "危险" in result["detail"]

    def test_timeout(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=10)):
            result = _run_import_smoke_layer("def f(): pass", "def g(): pass", "mod")
        assert result["passed"] is False
        assert "超时" in result["detail"]

    def test_os_error_infra_degraded(self):
        with patch("subprocess.run", side_effect=OSError("boom")):
            result = _run_import_smoke_layer("def f(): pass", "def g(): pass", "mod")
        assert result["passed"] is True
        assert result.get("infra_degraded") is True

    def test_import_failure(self):
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "ImportError: no module"
        proc.stdout = ""
        with patch("subprocess.run", return_value=proc):
            result = _run_import_smoke_layer("def f(): pass", "def g(): pass", "mod")
        assert result["passed"] is False
        assert "失败" in result["detail"]

    def test_import_success(self):
        proc = MagicMock()
        proc.returncode = 0
        proc.stderr = ""
        proc.stdout = ""
        with patch("subprocess.run", return_value=proc):
            result = _run_import_smoke_layer("def f(): pass", "def g(): pass", "mod")
        assert result["passed"] is True
        assert "通过" in result["detail"]

    def test_explicitly_disabled(self, monkeypatch):
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        result = _run_import_smoke_layer("def f(): pass", "def g(): pass", "mod")
        assert result["passed"] is True
        assert "跳过" in result["detail"]


# ═══ 6. run_testless_validation 主链路 ═════════════════════════════════════════


class TestRunTestlessValidation:
    def test_all_layers_pass(self, monkeypatch):
        monkeypatch.setenv("TESTLESS_MYPY_ENABLE", "false")
        monkeypatch.setenv("TESTLESS_NAMING_CONTRACT_ENABLE", "false")
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        result = run_testless_validation("def f(): pass", "def f(): pass\ndef g(): pass", "mod")
        assert result["passed"] is True
        assert "ast_symbol_guard" in result["layers"]
        assert result["failed_layers"] == []

    def test_failed_layer_reported(self, monkeypatch):
        monkeypatch.setenv("TESTLESS_MYPY_ENABLE", "false")
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        # 命名契约层：删除 g → 失败
        result = run_testless_validation("def f(): pass\ndef g(): pass", "def f(): pass", "mod")
        assert result["passed"] is False
        assert "naming_contract" in result["failed_layers"]
