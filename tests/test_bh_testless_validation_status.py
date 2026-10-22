"""BH（2026-10-21）：testless 验证四层的「不可测量 ≠ 验证通过」收口锁。

缺陷族（与 BA–BG 的 `rc==0` 判绿同族，落在 G5 testless 验证器上）。改前
`src/tools/testless_validation.py` 把多条"根本没测成"的路径折成与"测过且
干净"逐字相同的读数，实测（mypy 1.15.0 / Python 3.14.6）：

1. **mypy 层恒不可测量（根因）**：argv 传 `--silent-imports`，该拼写现代
   mypy 已移除 ⇒ 每次调用 rc=2 用法错误；旧代码把
   `mypy: error: unrecognized arguments` 当作**被测代码的疑点**，于是干净
   代码 / 类型错误 / 语法错误三者返回逐字节相同的
   `{"passed": False, "detail": "mypy 发现 1 处问题…"}`。
2. **mypy 层假干净**：`passed = len(error_lines) == 0`，故 rc ∉ {0,1} 且输出
   无 `error:`/`note:` 行时判通过——实测可达路径：读不到目标文件
   （rc=2，`mypy: can't read file …`）、被信号杀死（rc=-9，空输出）。
3. **AST 符号守卫假干净**：原文不可解析 ⇒ 原符号集为空 ⇒ 差集恒空 ⇒
   "AST 符号守卫通过"；补丁不可解析时还把它误报成"补丁删除了符号 ['f']"。
4. **命名契约层假陈述**：`check_naming_contract` 的 `(True, [])` 同时表示
   "比较过没删符号" / "不可解析没得比" / "PATCH_CONTRACT_CHECK=false 恒
   放行"，旧 detail 一律写"命名契约回归通过（无被删模块级符号）"。
5. **整体无可测量性维度**：result 只有 `passed` / `layers` / `failed_layers`，
   四层全部降级时顶层与"四层都测过且干净"逐字相同。

修复口径：每层带 `status`（ok / disabled / unavailable / error，取值与 BG 轮
`type_repair` 逐字一致）+ `reason`；mypy 按 rc 语义分类（0/1 可信，其余
error）并修回 `--follow-imports=silent`；AST 两层前置判可解析性并
fail-closed；顶层聚合 `validation_status`（**最差者优先**，与 BG 的"任一后端
ok ⇒ ok"方向相反，因四层相互独立）+ `degraded_layers` + warning 点名。
"""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.tools.testless_validation import (
    VALIDATION_DISABLED,
    VALIDATION_ERROR,
    VALIDATION_OK,
    VALIDATION_UNAVAILABLE,
    _run_ast_symbol_guard,
    _run_import_smoke_layer,
    _run_mypy_layer,
    _run_naming_contract_layer,
    _worst_layer_status,
    run_testless_validation,
)

_CLEAN = "def f() -> int:\n    return 1\n"
_TYPE_ERR = "def f() -> int:\n    return 'nope'\n"
_SYNTAX_ERR = "def f(:\n"


def _proc(
    stdout: str = "",
    *,
    stderr: str = "",
    returncode: int | None = 0,
    timed_out: bool = False,
) -> MagicMock:
    """构造 run_with_timeout 的返回值替身（形状与 CompletedProcess 兼容）。"""
    proc = MagicMock()
    proc.stdout = stdout
    proc.stderr = stderr
    proc.returncode = returncode
    proc.timed_out = timed_out
    return proc


def _mypy_with_proc(proc: MagicMock) -> dict[str, object]:
    with patch("src.utils.process_utils.run_with_timeout", return_value=proc):
        return _run_mypy_layer(_CLEAN, "mod")


# ═══ 1. mypy rc 语义分类（核心：不可测量不得读成 0 处问题）══════════════════


class TestMypyRcClassification:
    def test_rc0_is_ok_and_passed(self):
        result = _mypy_with_proc(_proc("", returncode=0))
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is True
        assert "通过" in result["detail"]

    def test_rc1_with_findings_is_ok_and_failed(self):
        result = _mypy_with_proc(_proc("/tmp/x.py:1: error: Incompatible types  [assignment]", returncode=1))
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is False
        assert "mypy 发现 1 处问题" in result["detail"]

    def test_rc1_without_findings_is_error(self):
        # rc=1 声称有疑点却解析不出疑点行 ⇒ 报告不可信，不得读成"0 处问题"。
        result = _mypy_with_proc(_proc("", returncode=1))
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "mypy_rc1_no_findings"
        assert result["passed"] is False

    @pytest.mark.parametrize("rc", [2, 3, -9, 137, None])
    def test_untrusted_rc_is_error_not_clean(self, rc):
        # 改前：这些 rc 且输出无 error:/note: 行时 passed=True +
        # "mypy 发现 0 处问题"（实测 rc=-9 空输出即命中）。
        result = _mypy_with_proc(_proc("", returncode=rc))
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == f"mypy_rc_{rc}"
        assert result["passed"] is False
        assert "发现 0 处问题" not in result["detail"]

    def test_unreadable_target_file_is_error(self):
        # 实测 rc=2 且输出为 `mypy: can't read file …`（无 error: 行）。
        result = _mypy_with_proc(_proc("", stderr="mypy: can't read file '/tmp/x.py': No such file", returncode=2))
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "mypy_rc_2"
        assert result["passed"] is False

    def test_usage_error_is_not_attributed_to_code(self):
        # 改前把工具链用法错误记成"被测代码有 1 处问题"（缺陷 1）。
        result = _mypy_with_proc(
            _proc("", stderr="usage: mypy [-h]\nmypy: error: unrecognized arguments: --silent-imports", returncode=2)
        )
        assert result["status"] == VALIDATION_ERROR
        assert result["passed"] is False
        assert "发现 1 处问题" not in result["detail"]
        assert "rc=2" in result["detail"]


# ═══ 2. 根因锁：mypy argv 必须是现代拼写 ════════════════════════════════════


class TestMypyInvocationFlags:
    def _captured_argv(self) -> list[str]:
        proc = _proc("", returncode=0)
        with patch("src.utils.process_utils.run_with_timeout", return_value=proc) as mocked:
            _run_mypy_layer(_CLEAN, "mod")
        return list(mocked.call_args[0][0])

    def test_uses_modern_follow_imports_spelling(self):
        # `--silent-imports` 已被 mypy 移除，沿用会让本层恒 rc=2 不可测量。
        argv = self._captured_argv()
        assert "--follow-imports=silent" in argv
        assert "--silent-imports" not in argv

    def test_targets_current_interpreter_and_temp_file(self):
        argv = self._captured_argv()
        assert argv[0] == sys.executable
        assert argv[1:3] == ["-m", "mypy"]
        assert argv[-1].endswith(".py")


# ═══ 3. 真 mypy 端到端（证明该层现在真的在测）═══════════════════════════════


class TestMypyRealRun:
    @pytest.fixture(autouse=True)
    def _require_mypy(self):
        pytest.importorskip("mypy", reason="mypy 未安装时本层按设计 unavailable，真跑锁不适用")

    def test_clean_module_is_measurable_and_passes(self):
        result = _run_mypy_layer(_CLEAN, "mod")
        assert result["status"] == VALIDATION_OK, result["detail"]
        assert result["passed"] is True

    def test_real_type_error_is_discriminated(self):
        # 改前：真实类型错误与干净代码返回逐字节相同的"发现 1 处问题"
        # （那 1 处是 mypy 的用法错误，不是代码缺陷）。改后 detail 携带真实
        # 诊断（实测 mypy 1.15.0：`error: Incompatible return value type
        # (got "str", expected "int")  [return-value]`）。
        result = _run_mypy_layer(_TYPE_ERR, "mod")
        assert result["status"] == VALIDATION_OK, result["detail"]
        assert result["passed"] is False
        assert "[return-value]" in result["detail"]
        assert "unrecognized arguments" not in result["detail"]

    def test_clean_and_type_error_no_longer_identical(self):
        assert _run_mypy_layer(_CLEAN, "mod") != _run_mypy_layer(_TYPE_ERR, "mod")


# ═══ 4. mypy 已披露降级路径（passed 口径不变，只补 status）══════════════════


class TestMypyDegradedPaths:
    def test_layer_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TESTLESS_MYPY_ENABLE", "false")
        result = _run_mypy_layer(_CLEAN, "mod")
        assert result["status"] == VALIDATION_DISABLED
        assert result["reason"] == "mypy_layer_disabled"
        assert result["passed"] is True

    def test_mypy_not_installed_is_unavailable(self):
        with patch.dict(sys.modules, {"mypy": None}):
            result = _run_mypy_layer(_CLEAN, "mod")
        assert result["status"] == VALIDATION_UNAVAILABLE
        assert result["reason"] == "mypy_not_installed"
        assert result["passed"] is True
        assert result["infra_degraded"] is True

    def test_timeout_is_error_but_keeps_passed(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("TESTLESS_MYPY_ENABLE", raising=False)
        with patch(
            "src.utils.process_utils.run_with_timeout",
            side_effect=subprocess.TimeoutExpired(cmd="mypy", timeout=60),
        ):
            result = _run_mypy_layer(_CLEAN, "mod")
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "mypy_timeout"
        assert result["passed"] is True
        assert result["infra_degraded"] is True

    def test_os_error_is_error_but_keeps_passed(self):
        with patch("src.utils.process_utils.run_with_timeout", side_effect=OSError("no mypy")):
            result = _run_mypy_layer(_CLEAN, "mod")
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "mypy_exception"
        assert result["passed"] is True
        assert result["infra_degraded"] is True

    def test_timed_out_flag_maps_to_timeout_reason(self):
        # 生产路径：run_with_timeout 不抛异常而返回 timed_out=True。
        result = _mypy_with_proc(_proc("", returncode=-9, timed_out=True))
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "mypy_timeout"


# ═══ 5. AST 符号守卫：不可解析 ⇒ 不可测量（fail-closed）═════════════════════


class TestAstSymbolGuardStatus:
    def test_unparseable_original_is_error(self):
        result = _run_ast_symbol_guard(_SYNTAX_ERR, "def g():\n    return 1\n")
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "unparseable_original"
        assert result["passed"] is False

    def test_unparseable_patched_is_error_not_removed_symbol(self):
        # 改前把解析失败误报成"补丁删除了原代码的模块级定义 ['f']"。
        result = _run_ast_symbol_guard(_CLEAN, _SYNTAX_ERR)
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "unparseable_patched"
        assert result["passed"] is False
        assert "删除" not in result["detail"]

    def test_both_unparseable_is_error(self):
        result = _run_ast_symbol_guard(_SYNTAX_ERR, "def g(:\n")
        assert result["status"] == VALIDATION_ERROR
        assert result["passed"] is False

    def test_removed_symbol_is_ok_and_failed(self):
        result = _run_ast_symbol_guard("def f(): pass\ndef g(): pass", "def f(): pass")
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is False
        assert "g" in result["detail"]

    def test_clean_comparison_is_ok(self):
        result = _run_ast_symbol_guard(_CLEAN, _CLEAN + "\ndef g(): pass\n")
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is True
        assert "新增" in result["detail"]


# ═══ 6. 命名契约层：三种 (True, []) 必须可区分 ══════════════════════════════


class TestNamingContractStatus:
    def test_unparseable_original_is_error_not_passed(self):
        # 改前 detail 为假陈述："命名契约回归通过（无被删模块级符号）"。
        result = _run_naming_contract_layer(_SYNTAX_ERR, "def g(): pass")
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "unparseable_original"
        assert result["passed"] is False
        assert "无被删模块级符号" not in result["detail"]

    def test_contract_check_switch_off_is_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("PATCH_CONTRACT_CHECK", "false")
        result = _run_naming_contract_layer("def f(): pass\ndef g(): pass", "def f(): pass")
        assert result["status"] == VALIDATION_DISABLED
        assert result["reason"] == "patch_contract_check_disabled"
        assert result["passed"] is True
        assert "无被删模块级符号" not in result["detail"]

    def test_layer_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TESTLESS_NAMING_CONTRACT_ENABLE", "false")
        result = _run_naming_contract_layer(_CLEAN, _CLEAN)
        assert result["status"] == VALIDATION_DISABLED
        assert result["reason"] == "naming_contract_layer_disabled"
        assert result["passed"] is True

    def test_genuine_removal_is_ok_and_failed(self):
        result = _run_naming_contract_layer("def f(): pass\ndef g(): pass", "def f(): pass")
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is False
        assert "缺失" in result["detail"]

    def test_no_removal_is_ok(self):
        result = _run_naming_contract_layer(_CLEAN, _CLEAN + "\ndef g(): pass\n")
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is True


# ═══ 7. 导入冒烟层 status ═══════════════════════════════════════════════════


class TestImportSmokeStatus:
    def test_layer_disabled(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        result = _run_import_smoke_layer(_CLEAN, _CLEAN, "mod")
        assert result["status"] == VALIDATION_DISABLED
        assert result["reason"] == "import_smoke_layer_disabled"

    def test_dangerous_api_refusal_is_disabled_not_ok(self):
        # 拒跑 = 按设计未执行导入，不能记成"导入验证过"。
        result = _run_import_smoke_layer(_CLEAN, "import os\nos.system('ls')\n", "mod")
        assert result["status"] == VALIDATION_DISABLED
        assert result["reason"] == "refused_dangerous_api"
        assert result["passed"] is False

    def test_timeout_is_error(self):
        with patch("src.utils.process_utils.run_with_timeout", return_value=_proc("", returncode=-9, timed_out=True)):
            result = _run_import_smoke_layer(_CLEAN, _CLEAN, "mod")
        assert result["status"] == VALIDATION_ERROR
        assert result["reason"] == "import_smoke_timeout"
        assert result["passed"] is False

    def test_os_error_is_unavailable(self):
        with patch("src.utils.process_utils.run_with_timeout", side_effect=OSError("boom")):
            result = _run_import_smoke_layer(_CLEAN, _CLEAN, "mod")
        assert result["status"] == VALIDATION_UNAVAILABLE
        assert result["reason"] == "import_smoke_exception"
        assert result["passed"] is True
        assert result["infra_degraded"] is True

    def test_import_success_is_ok(self):
        with patch("src.utils.process_utils.run_with_timeout", return_value=_proc("", returncode=0)):
            result = _run_import_smoke_layer(_CLEAN, _CLEAN, "mod")
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is True

    def test_import_failure_is_ok_and_failed(self):
        with patch(
            "src.utils.process_utils.run_with_timeout",
            return_value=_proc("", stderr="ImportError: no module", returncode=1),
        ):
            result = _run_import_smoke_layer(_CLEAN, _CLEAN, "mod")
        assert result["status"] == VALIDATION_OK
        assert result["passed"] is False


# ═══ 8. 聚合器：最差者优先（与 BG 的方向相反）═══════════════════════════════


class TestWorstLayerStatus:
    @pytest.mark.parametrize(
        ("statuses", "expected"),
        [
            (("ok", "ok", "ok", "ok"), VALIDATION_OK),
            (("ok", "disabled", "ok", "ok"), VALIDATION_DISABLED),
            (("ok", "unavailable", "disabled", "ok"), VALIDATION_UNAVAILABLE),
            (("ok", "unavailable", "disabled", "error"), VALIDATION_ERROR),
            (("error", "ok", "ok", "ok"), VALIDATION_ERROR),
        ],
    )
    def test_precedence(self, statuses, expected):
        layers = {f"layer{i}": {"status": s} for i, s in enumerate(statuses)}
        assert _worst_layer_status(layers) == expected

    def test_error_beats_ok_regardless_of_order(self):
        # 四层相互独立：任一层不可测量 ⇒ 整体验证不完整（不是"任一 ok ⇒ ok"）。
        forward = {"a": {"status": "ok"}, "b": {"status": "error"}}
        backward = {"b": {"status": "error"}, "a": {"status": "ok"}}
        assert _worst_layer_status(forward) == VALIDATION_ERROR
        assert _worst_layer_status(backward) == VALIDATION_ERROR

    def test_missing_status_is_error(self):
        # 未知/缺失 status 保守按 error（fail-closed），不得默认 ok。
        assert _worst_layer_status({"a": {"passed": True}}) == VALIDATION_ERROR
        assert _worst_layer_status({"a": {"status": "weird"}}) == VALIDATION_ERROR

    def test_empty_layers_is_error(self):
        assert _worst_layer_status({}) == VALIDATION_ERROR


# ═══ 9. 顶层可测量性（核心假干净锁）════════════════════════════════════════


class TestRollUpStatus:
    def _all_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("TESTLESS_MYPY_ENABLE", raising=False)
        monkeypatch.delenv("TESTLESS_NAMING_CONTRACT_ENABLE", raising=False)
        monkeypatch.delenv("TESTLESS_IMPORT_SMOKE_ENABLE", raising=False)
        monkeypatch.delenv("PATCH_CONTRACT_CHECK", raising=False)

    def test_all_measurable_reports_ok(self, monkeypatch: pytest.MonkeyPatch):
        self._all_ok(monkeypatch)
        fake_layers = {
            "ast_symbol_guard": {"passed": True, "status": "ok"},
            "mypy": {"passed": True, "status": "ok"},
            "naming_contract": {"passed": True, "status": "ok"},
            "import_smoke": {"passed": True, "status": "ok"},
        }
        with (
            patch("src.tools.testless_validation._run_ast_symbol_guard", return_value=fake_layers["ast_symbol_guard"]),
            patch("src.tools.testless_validation._run_mypy_layer", return_value=fake_layers["mypy"]),
            patch(
                "src.tools.testless_validation._run_naming_contract_layer",
                return_value=fake_layers["naming_contract"],
            ),
            patch("src.tools.testless_validation._run_import_smoke_layer", return_value=fake_layers["import_smoke"]),
        ):
            result = run_testless_validation(_CLEAN, _CLEAN, "mod")
        assert result["passed"] is True
        assert result["validation_status"] == VALIDATION_OK
        assert result["degraded_layers"] == []

    def test_passed_true_with_unmeasurable_layers_is_disclosed(self, monkeypatch: pytest.MonkeyPatch, caplog):
        # 核心锁：改前这一跑的顶层读数与"四层都测过且干净"逐字相同
        # （passed=True / failed_layers=[]）。mypy 超时（已披露降级，passed
        # 仍为 True）+ 导入冒烟层关闭 ⇒ 整体必须报 error 并点名，否则
        # "没有一层报告缺陷"会被读成"验证通过"。
        self._all_ok(monkeypatch)
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        with (
            patch(
                "src.utils.process_utils.run_with_timeout",
                side_effect=subprocess.TimeoutExpired(cmd="mypy", timeout=60),
            ),
            caplog.at_level("WARNING", logger="src.tools.testless_validation"),
        ):
            result = run_testless_validation(_CLEAN, _CLEAN, "mod")
        assert result["passed"] is True
        assert result["failed_layers"] == []
        assert result["validation_status"] == VALIDATION_ERROR
        assert "mypy" in result["degraded_layers"]
        assert "可测量性降级" in caplog.text
        assert "mypy=error:mypy_timeout" in caplog.text

    def test_unparseable_patch_makes_overall_error(self, monkeypatch: pytest.MonkeyPatch):
        self._all_ok(monkeypatch)
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        with patch("src.tools.testless_validation._run_mypy_layer", return_value={"passed": True, "status": "ok"}):
            result = run_testless_validation(_CLEAN, _SYNTAX_ERR, "mod")
        assert result["validation_status"] == VALIDATION_ERROR
        assert result["passed"] is False
        assert set(result["degraded_layers"]) >= {"ast_symbol_guard", "naming_contract"}

    def test_all_layers_switched_off_is_disabled_not_ok(self, monkeypatch: pytest.MonkeyPatch):
        self._all_ok(monkeypatch)
        monkeypatch.setenv("TESTLESS_MYPY_ENABLE", "false")
        monkeypatch.setenv("TESTLESS_NAMING_CONTRACT_ENABLE", "false")
        monkeypatch.setenv("TESTLESS_IMPORT_SMOKE_ENABLE", "false")
        result = run_testless_validation(_CLEAN, _CLEAN, "mod")
        assert result["passed"] is True
        assert result["validation_status"] == VALIDATION_DISABLED
        assert set(result["degraded_layers"]) == {"mypy", "naming_contract", "import_smoke"}

    def test_every_layer_carries_a_status(self, monkeypatch: pytest.MonkeyPatch):
        self._all_ok(monkeypatch)
        with patch("src.tools.testless_validation._run_mypy_layer", return_value={"passed": True, "status": "ok"}):
            result = run_testless_validation(_CLEAN, _CLEAN, "mod")
        for name, layer in result["layers"].items():
            assert "status" in layer, f"{name} 缺 status"
            assert layer["status"] in {
                VALIDATION_OK,
                VALIDATION_DISABLED,
                VALIDATION_UNAVAILABLE,
                VALIDATION_ERROR,
            }

    def test_legacy_keys_unchanged(self, monkeypatch: pytest.MonkeyPatch):
        # passed / layers / failed_layers 三键口径不变，新键只增不改。
        self._all_ok(monkeypatch)
        with patch("src.tools.testless_validation._run_mypy_layer", return_value={"passed": True, "status": "ok"}):
            result = run_testless_validation(_CLEAN, _CLEAN, "mod")
        assert set(result) == {
            "passed",
            "layers",
            "failed_layers",
            "validation_status",
            "degraded_layers",
        }
        assert set(result["layers"]) == {"ast_symbol_guard", "mypy", "naming_contract", "import_smoke"}


# ═══ 10. 消费点披露（nodes.py 不得把降级读成验证通过）══════════════════════


class TestConsumerDisclosure:
    def test_passed_but_degraded_is_logged(self, monkeypatch: pytest.MonkeyPatch, caplog):
        from src.graph.nodes import _maybe_run_testless_validation

        monkeypatch.setenv("TESTLESS_VALIDATION_ENABLE", "true")
        degraded = {
            "passed": True,
            "layers": {},
            "failed_layers": [],
            "validation_status": VALIDATION_ERROR,
            "degraded_layers": ["mypy", "import_smoke"],
        }
        with (
            patch("src.tools.testless_validation.run_testless_validation", return_value=degraded),
            caplog.at_level("INFO", logger="src.graph.nodes"),
        ):
            update = _maybe_run_testless_validation({"module_name": "mod"}, _CLEAN, _CLEAN, True)
        assert update == {"testless_validation": degraded}
        assert "可测量性降级" in caplog.text
        assert "不构成'验证通过'的证据" in caplog.text

    def test_fully_measurable_pass_logs_no_degradation(self, monkeypatch: pytest.MonkeyPatch, caplog):
        from src.graph.nodes import _maybe_run_testless_validation

        monkeypatch.setenv("TESTLESS_VALIDATION_ENABLE", "true")
        measurable = {
            "passed": True,
            "layers": {},
            "failed_layers": [],
            "validation_status": VALIDATION_OK,
            "degraded_layers": [],
        }
        with (
            patch("src.tools.testless_validation.run_testless_validation", return_value=measurable),
            caplog.at_level("INFO", logger="src.graph.nodes"),
        ):
            _maybe_run_testless_validation({"module_name": "mod"}, _CLEAN, _CLEAN, True)
        assert "可测量性降级" not in caplog.text
