"""J-4（2026-10-17）：`_patch_applier_node` 守卫链 / 降级链 / 重采样 / 证据门补测。

纪律：零 LLM、零真实重采样调用——`DebuggerAgent` 整类被 mock，
`apply_patch_with_resample` 换成受控替身（由测试自己回调 `_on_resample`）；
写盘走 `tmp_path` 真实文件（`_safe_write_patch` 的路径白名单含系统临时顶层）。

判别性口径：每条"开关开启"腿都配"开关默认关"对照腿；契约守卫（1.3）与
危险 API 守卫（S2）用**真实** `check_naming_contract` / `dangerous_api_added`
产出拒绝，不用 mock 造一个"看起来被拒"的补丁——只有真实拒绝才能证明
下游档位推进 / 写盘阻断确实发生。
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import src.tools.patch_applier as patch_applier_mod
from src.graph import nodes as nodes_mod

# 原码含模块级常量 CONST——"整文件补丁"只校验函数名子集，删掉 CONST 后
# 真实的 check_naming_contract 必然拒绝（1.3 守卫的确定性触发方式）
_ORIG_WITH_CONST = '"""Module doc."""\n\n\ndef f():\n    return 1\n\n\nCONST = 3\n'
_PATCH_FULLFILE_DROPS_CONST = '"""Module doc."""\n\n\ndef f():\n    return 2\n'

_ORIG = "def f():\n    return 1\n"
_PATCH = "def f():\n    return 2\n"
_PATCH_SANITIZED = "def f():\n    return 3\n"
# 仅作"被守卫拦截的补丁文本"，全程不执行
_PATCH_DANGEROUS = "def f():\n    return os.system('ls')\n"


def _state(tmp_path: Any, *, original: str = _ORIG, patch_text: str | None = _PATCH, **extra: Any) -> dict[str, Any]:
    """构造 patch_applier 入参 state：target_file 落在 tmp_path（白名单内，真实可写）。"""
    target = tmp_path / "mod.py"
    target.write_text(original, encoding="utf-8")
    state: dict[str, Any] = {
        "target_code": original,
        "patch": patch_text,
        "target_file": str(target),
        "module_name": "mod",
        "iteration": 0,
        "error_category": "RUNTIME",
        "diagnosis": "off-by-one",
    }
    state.update(extra)
    return state


def _run(monkeypatch: pytest.MonkeyPatch, state: dict[str, Any], **env: str) -> dict[str, Any]:
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    with (
        patch.object(nodes_mod, "_trace_node"),
        patch.object(nodes_mod, "publish_patch_applied"),
    ):
        return nodes_mod._patch_applier_node(state)  # type: ignore[arg-type]


def _disk(tmp_path: Any) -> str:
    return (tmp_path / "mod.py").read_text(encoding="utf-8")


@pytest.mark.unit
class TestPostprocessReapply:
    """1.1 后处理层：P2/P3 生效时用卫生化补丁**重新应用**（nodes.py:1921）。"""

    def _stub_pp(
        self, monkeypatch: pytest.MonkeyPatch, *, flags: dict[str, bool], sanitized: str, labels: list[str]
    ) -> MagicMock:
        import src.tools.patch_postprocess as pp_mod

        spy = MagicMock(return_value=(sanitized, labels))
        monkeypatch.setattr(pp_mod, "postprocess_enabled_flags", lambda: flags)
        monkeypatch.setattr(pp_mod, "sanitize_patch", spy)
        return spy

    def test_p2_import_repair_reapplies_sanitized_patch(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """import_repair 开 + 标签含 imports_repaired → 落盘的是卫生化版（return 3）。"""
        self._stub_pp(
            monkeypatch,
            flags={"empty_patch_guard": True, "import_repair": True, "contract_alias": False},
            sanitized=_PATCH_SANITIZED,
            labels=["imports_repaired"],
        )
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert "return 3" in _disk(tmp_path), "P2 生效后磁盘必须是卫生化补丁的结果"
        assert "return 3" in update["target_code"]
        assert update["postprocess_labels"] == ["imports_repaired"]

    def test_p1_label_alone_does_not_reapply(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：开关关 + 标签非修复类 → 不重应用（磁盘仍是原补丁 return 2）。"""
        self._stub_pp(
            monkeypatch,
            flags={"empty_patch_guard": True, "import_repair": False, "contract_alias": False},
            sanitized=_PATCH_SANITIZED,
            labels=["empty_patch"],
        )
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert "return 2" in _disk(tmp_path)
        assert "return 2" in update["target_code"]
        assert update["postprocess_labels"] == ["empty_patch"]

    def test_p3_contract_alias_alone_also_reapplies(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """contract_alias 单开关也须触发重应用（1917 的 or 条件，非仅 import_repair）。"""
        self._stub_pp(
            monkeypatch,
            flags={"empty_patch_guard": True, "import_repair": False, "contract_alias": True},
            sanitized=_PATCH_SANITIZED,
            labels=["contract_aliases_restored"],
        )
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert "return 3" in update["target_code"]

    def test_postprocess_exception_is_conservatively_skipped(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """sanitize_patch 抛异常 → 走历史口径（补丁照常应用），且不留 postprocess_labels 键。"""
        import src.tools.patch_postprocess as pp_mod

        flags = {"empty_patch_guard": True, "import_repair": False, "contract_alias": False}
        monkeypatch.setattr(pp_mod, "postprocess_enabled_flags", lambda: flags)
        monkeypatch.setattr(pp_mod, "sanitize_patch", MagicMock(side_effect=RuntimeError("boom")))
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert "return 2" in update["target_code"], "异常不应连带阻断本轮补丁"
        assert "postprocess_labels" not in update, "异常路径 postprocess_update 保持为空"


@pytest.mark.unit
class TestContextTierDowngrade:
    """1.3 降级链：符号守卫拒绝后推进档位并把反馈透传下一轮（nodes.py:1953-1962 / 2177）。"""

    def _pin_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """钉住进程内档位起点（advance_context_tier 写全局 + os.environ，须可还原）。"""
        monkeypatch.setattr(patch_applier_mod, "_CONTEXT_TIER_INDEX", 0)
        monkeypatch.setenv("CONTEXT_TIER", "0")

    def test_guard_reject_advances_tier_and_emits_feedback(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._pin_tier(monkeypatch)
        state = _state(tmp_path, original=_ORIG_WITH_CONST, patch_text=_PATCH_FULLFILE_DROPS_CONST)
        update = _run(monkeypatch, state, CONTEXT_TIER_DOWNGRADE_ENABLE="true")
        # 真实 check_naming_contract 判缺 → 本轮拒绝写盘
        assert update["target_code"] == _ORIG_WITH_CONST
        assert _disk(tmp_path) == _ORIG_WITH_CONST
        assert update["contract_missing_symbols"] == ["CONST"]
        assert update["contract_reject_feedback"] == {"tier": "patch_ingredients", "missing_symbols": ["CONST"]}
        assert patch_applier_mod._CONTEXT_TIER_INDEX == 1, "降级链必须真正推进进程内档位"

    def test_downgrade_disabled_keeps_tier(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：同一份真实被拒补丁，开关关 → 档位不变、无 contract_reject_feedback 键。"""
        self._pin_tier(monkeypatch)
        state = _state(tmp_path, original=_ORIG_WITH_CONST, patch_text=_PATCH_FULLFILE_DROPS_CONST)
        update = _run(monkeypatch, state)
        assert update["contract_missing_symbols"] == ["CONST"], "缺失符号观测与开关无关"
        assert "contract_reject_feedback" not in update
        assert patch_applier_mod._CONTEXT_TIER_INDEX == 0, "未启用降级链不得推进档位"


@pytest.mark.unit
class TestDangerousApiGuard:
    """S2 危险操作双保险：AST 差集 + 正则 findings 任一非空即拒（nodes.py:1982-1984）。"""

    def test_patch_adding_dangerous_api_is_rejected(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        state = _state(tmp_path, patch_text=_PATCH_DANGEROUS)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert _disk(tmp_path) == _ORIG, "危险补丁不得落盘"
        assert update["target_code"] == _ORIG
        assert update["repair_history"][-1]["patch_applied"] is False

    def test_benign_patch_passes_the_same_guard(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：同一道守卫跑在无危险 API 的补丁上必须放行（否则上一条是假绿）。"""
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert _disk(tmp_path) == _PATCH
        assert update["repair_history"][-1]["patch_applied"] is True


@pytest.mark.unit
class TestResampleCallback:
    """2.2 `_on_resample` 回调的拒绝腿 + 接受腿（nodes.py:2007/2030/2048/2049）。"""

    def _drive(
        self,
        monkeypatch: pytest.MonkeyPatch,
        state: dict[str, Any],
        *,
        llm_return: Any,
        args: tuple,
        exc: Exception | None = None,
    ) -> dict[str, Any]:
        """让受控的 apply_patch_with_resample 回调一次 _on_resample 并返回其结果。

        进入 2.2 分支的前置条件是 `not applied`，故所有用例的 state 都不带补丁
        （patch=None → apply_patch_to_code 返回 False），否则重采样整段被跳过。
        """
        import src.agents.debugger as debugger_mod
        import src.tools.patch_applier as pa_mod

        resampler = MagicMock()
        if exc is not None:
            resampler._call_llm_with_cache.side_effect = exc
        else:
            resampler._call_llm_with_cache.return_value = llm_return
        captured: dict[str, Any] = {}

        def _fake(original_code: str, patch: str, resample_fn: Any = None, max_resamples: int = 1):
            captured["outcome"] = resample_fn("q", original_code, *args)
            return original_code, False, {"resampled": False, "resample_count": 0, "success": False}

        monkeypatch.setattr(pa_mod, "apply_patch_with_resample", _fake)
        monkeypatch.setattr(debugger_mod, "DebuggerAgent", MagicMock(return_value=resampler))
        update = _run(monkeypatch, state, PATCH_RESAMPLE_ENABLE="true")
        return {"update": update, "captured": captured, "resampler": resampler}

    def test_on_resample_gives_up_without_patch_or_ast_error(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        r = self._drive(monkeypatch, _state(tmp_path, patch_text=None), llm_return="irrelevant", args=("", ""))
        assert r["captured"]["outcome"] is None
        assert r["resampler"]._call_llm_with_cache.call_count == 0, "放弃腿不得产生 LLM 调用"

    def test_on_resample_rejects_unextractable_llm_output(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        r = self._drive(
            monkeypatch,
            _state(tmp_path, patch_text=None),
            llm_return="",
            args=("def f(): pass", "SyntaxError: bad"),
        )
        assert r["captured"]["outcome"] is None
        assert r["resampler"]._call_llm_with_cache.call_count == 1

    def test_on_resample_rejects_contract_breaking_candidate(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import src.tools.patch_applier as pa_mod

        # safe_apply_patch 内部也调 check_naming_contract；把它换成"语法/危险 API
        # 通过"的确定性替身，才能让 2048 这条腿单独归因到 _on_resample 自己的契约复核。
        monkeypatch.setattr(pa_mod, "safe_apply_patch", lambda _orig, cand: (cand, True))
        contract = MagicMock(return_value=(False, ["CONST"]))
        monkeypatch.setattr(pa_mod, "check_naming_contract", contract)
        r = self._drive(
            monkeypatch,
            _state(tmp_path, patch_text=None),
            llm_return="```python\ndef f():\n    return 9\n```",
            args=("def f():\n    return 1\n", "SyntaxError: bad"),
        )
        assert r["captured"]["outcome"] is None
        assert contract.call_count == 1, "重采样候选必须过命名契约（J-3 注释纠错所锁的保护）"

    def test_on_resample_accepts_valid_candidate(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：语法 + 契约都过 → 返回提取后的代码（前三条拒绝腿的可信度依赖本腿）。"""
        import src.tools.patch_applier as pa_mod

        monkeypatch.setattr(pa_mod, "safe_apply_patch", lambda _orig, cand: (cand, True))
        r = self._drive(
            monkeypatch,
            _state(tmp_path, patch_text=None),
            llm_return="```python\ndef f():\n    return 9\n```",
            args=("def f():\n    return 1\n", "SyntaxError: bad"),
        )
        assert r["captured"]["outcome"] == "def f():\n    return 9"

    def test_on_resample_swallows_llm_exception(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        r = self._drive(
            monkeypatch,
            _state(tmp_path, patch_text=None),
            llm_return=None,
            args=("def f(): pass", "SyntaxError: bad"),
            exc=RuntimeError("network"),
        )
        assert r["captured"]["outcome"] is None


@pytest.mark.unit
class TestResampleOutcomes:
    """2.2 重采样结果处理：契约复核拒写盘 / 耗尽标记（nodes.py:2072-2075 / 2079 / 2191 / 2197）。"""

    def _stub_resample(self, monkeypatch: pytest.MonkeyPatch, result: tuple[str, bool, dict[str, Any]]) -> None:
        import src.tools.patch_applier as pa_mod

        monkeypatch.setattr(pa_mod, "apply_patch_with_resample", lambda *a, **k: result)

    def test_post_resample_contract_recheck_blocks_write(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_resample(
            monkeypatch,
            (_PATCH_FULLFILE_DROPS_CONST + "\n", True, {"resampled": True, "resample_count": 1, "success": True}),
        )
        state = _state(tmp_path, original=_ORIG_WITH_CONST, patch_text=_PATCH_FULLFILE_DROPS_CONST)
        update = _run(monkeypatch, state, PATCH_RESAMPLE_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert update["target_code"] == _ORIG_WITH_CONST, "契约复核失败必须回到原代码"
        assert _disk(tmp_path) == _ORIG_WITH_CONST
        assert update["contract_missing_symbols"] == ["CONST"]

    def test_resample_exhausted_marks_patch_syntax_invalid(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub_resample(
            monkeypatch,
            (_ORIG_WITH_CONST, False, {"resampled": True, "resample_count": 2, "success": False}),
        )
        state = _state(tmp_path, original=_ORIG_WITH_CONST, patch_text=_PATCH_FULLFILE_DROPS_CONST)
        update = _run(monkeypatch, state, PATCH_RESAMPLE_ENABLE="true")
        assert update["error_category"] == "patch_syntax_invalid"
        assert update["patch_syntax_invalid_flag"] is True, "TypedDict 通道键须与字符串口径双写"
        assert update["patch_resample_stats"]["resample_count"] == 2
        assert "tiered_context" in update["patch_resample_stats"]

    def test_resample_disabled_by_default_makes_no_call(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：同一份失败补丁，PATCH_RESAMPLE_ENABLE 未设 → 无 stats、无 flag。"""
        import src.tools.patch_applier as pa_mod

        spy = MagicMock()
        monkeypatch.setattr(pa_mod, "apply_patch_with_resample", spy)
        state = _state(tmp_path, patch_text=None)
        update = _run(monkeypatch, state)
        assert spy.call_count == 0, "默认关不得进入重采样路径（零额外 LLM 调用）"
        assert "patch_resample_stats" not in update
        assert "patch_syntax_invalid_flag" not in update

    def test_resample_success_with_intact_contract_writes(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：resampled=True + applied=True + 契约通过 → 补丁落盘（拒绝腿的非假绿证明）。"""
        self._stub_resample(
            monkeypatch, (_PATCH + "\n", True, {"resampled": True, "resample_count": 1, "success": True})
        )
        state = _state(tmp_path, patch_text=None)
        update = _run(monkeypatch, state, PATCH_RESAMPLE_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert update["target_code"] == _PATCH + "\n"
        assert _disk(tmp_path) == _PATCH + "\n"
        assert "contract_missing_symbols" not in update


@pytest.mark.unit
class TestEvidenceGateRestoreFailure:
    """P0 证据门真阻断：恢复原文件失败时如实降级（nodes.py:2112-2113 / 2129）。"""

    def test_restore_failure_downgrades_to_after_the_fact_flag(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _boom(*_a: Any, **_k: Any) -> None:
            raise OSError("disk full")

        # 只 mock nodes 侧绑定：_safe_write_patch 用 patch_io 自己的 _write_file_atomic，
        # 真实写盘仍成功，仅证据门的"恢复原文件"调用失败
        monkeypatch.setattr(nodes_mod, "_write_file_atomic", _boom)
        state = _state(tmp_path)
        update = _run(monkeypatch, state)  # 证据门默认开，state 无 sbfl/gold 证据 → 等级 none

        assert update["patch_evidence_level"] == "none"
        assert update["source_patched_unverified"] is True
        assert update["target_code"] == _PATCH, "恢复失败时磁盘与状态必须同口径（C6 教训）"
        assert _disk(tmp_path) == _PATCH, "恢复失败不得虚报已恢复"
        assert update["repair_history"][-1]["patch_applied"] is True
        assert "_last_patch_snapshot" in update, "阻断未生效，快照仍可回滚"

    def test_gate_off_keeps_patch_without_unverified_flag(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：PATCH_EVIDENCE_GATE_ENABLE=false → 不触发恢复分支，source_patched_unverified=False。"""
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert update["source_patched_unverified"] is False
        assert _disk(tmp_path) == _PATCH
        assert update["patch_evidence_level"] == "none", "opt-out 时等级仍记录（消融对照）"


@pytest.mark.unit
class TestTestlessValidation:
    """O6 testless 验证层：纯观测、不阻断（nodes.py:2272-2279 / 2283-2287）。"""

    def _stub(self, monkeypatch: pytest.MonkeyPatch, *, ret: Any = None, exc: Exception | None = None) -> MagicMock:
        import src.tools.testless_validation as tlv_mod

        spy = MagicMock(return_value=ret, side_effect=exc)
        monkeypatch.setattr(tlv_mod, "run_testless_validation", spy)
        return spy

    def test_failed_layers_recorded_as_observation(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        spy = self._stub(monkeypatch, ret={"passed": False, "failed_layers": ["mypy"]})
        state = _state(tmp_path)
        with caplog.at_level(logging.INFO, logger="src.graph.nodes"):
            update = _run(monkeypatch, state, TESTLESS_VALIDATION_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert update["testless_validation"] == {"passed": False, "failed_layers": ["mypy"]}
        assert update["target_code"] == _PATCH, "testless 失败不阻断主流程"
        kwargs = spy.call_args.kwargs
        assert kwargs["patched_code"] == _PATCH and kwargs["target_module"] == "mod"
        # 2278 假腿的可观测出口：失败层信息必须进日志，否则"未通过"只落在
        # state 里、跑批现场无法从 trace 定位是哪一层拦下的
        assert any("testless 验证未通过" in r.getMessage() for r in caplog.records)

    def test_passed_validation_logs_no_failure(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """nodes.py:2278 的真腿（通过）：结果照记，但不打"未通过"日志。

        `.get("passed", True)` 的默认值也是口径的一部分——验证层返回缺 passed
        键（旧版本/异常返回体）时按"通过"处理，不得虚报失败。两种形态同腿，
        与上一条（passed=False 必打日志）成对提供判别性。
        """
        self._stub(monkeypatch, ret={"passed": True, "failed_layers": []})
        with caplog.at_level(logging.INFO, logger="src.graph.nodes"):
            update = _run(
                monkeypatch, _state(tmp_path), TESTLESS_VALIDATION_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false"
            )
        assert update["testless_validation"] == {"passed": True, "failed_layers": []}
        assert not any("testless 验证未通过" in r.getMessage() for r in caplog.records)

    def test_missing_passed_key_defaults_to_pass(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        """`.get("passed", True)` 默认腿：返回体无 passed 键 → 不判失败。"""
        self._stub(monkeypatch, ret={"detail": "shape from an older validator"})
        with caplog.at_level(logging.INFO, logger="src.graph.nodes"):
            update = _run(
                monkeypatch, _state(tmp_path), TESTLESS_VALIDATION_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false"
            )
        assert update["testless_validation"] == {"detail": "shape from an older validator"}
        assert not any("testless 验证未通过" in r.getMessage() for r in caplog.records)

    def test_validation_exception_keeps_history_shape(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub(monkeypatch, exc=RuntimeError("mypy blew up"))
        state = _state(tmp_path)
        update = _run(monkeypatch, state, TESTLESS_VALIDATION_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert "testless_validation" not in update
        assert update["target_code"] == _PATCH

    def test_disabled_by_default_makes_no_call(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._stub(monkeypatch, ret={"passed": True, "failed_layers": []})
        state = _state(tmp_path)
        update = _run(monkeypatch, state, PATCH_EVIDENCE_GATE_ENABLE="false")
        assert spy.call_count == 0
        assert "testless_validation" not in update

    def test_skipped_when_write_was_blocked(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：written=False（证据门阻断）→ 验证层不启动。"""
        spy = self._stub(monkeypatch, ret={"passed": True, "failed_layers": []})
        state = _state(tmp_path)
        _run(monkeypatch, state, TESTLESS_VALIDATION_ENABLE="true")  # 门默认开 → 等级 none → 阻断
        assert spy.call_count == 0


@pytest.mark.unit
class TestMultiCandidateRepairStash:
    """C10：多候选胜出补丁进 last_applied_repair（nodes.py:2296）。"""

    def _stub_selector(self, monkeypatch: pytest.MonkeyPatch, stats: dict[str, Any]) -> None:
        monkeypatch.setattr(
            nodes_mod,
            "_select_multi_candidate_patch",
            lambda *_a, **_k: (_PATCH, True, {"multi_candidate_stats": stats}),
        )

    def test_winning_candidate_patch_overrides_debugger_patch(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        winner = "def f():\n    return 7\n"
        self._stub_selector(monkeypatch, {"applied_patch": winner, "candidates": 3})
        state = _state(tmp_path)
        update = _run(monkeypatch, state, ENABLE_MULTI_CANDIDATE_PATCH="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert update["last_applied_repair"]["patch"] == winner
        assert update["multi_candidate_stats"]["candidates"] == 3

    def test_missing_applied_patch_falls_back_to_state_patch(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """对照腿：stats 里没有胜出文本 → 仍用 state["patch"]（不臆造空补丁入库）。"""
        self._stub_selector(monkeypatch, {"candidates": 3})
        state = _state(tmp_path)
        update = _run(monkeypatch, state, ENABLE_MULTI_CANDIDATE_PATCH="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert update["last_applied_repair"]["patch"] == _PATCH

    def test_stash_cleared_when_write_blocked(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        self._stub_selector(monkeypatch, {"applied_patch": "def f():\n    return 7\n"})
        state = _state(tmp_path)
        update = _run(monkeypatch, state, ENABLE_MULTI_CANDIDATE_PATCH="true")  # 证据门默认开 → 阻断
        assert update["last_applied_repair"] is None


@pytest.mark.unit
class TestCrossFileSkipsPostprocess:
    """3.5 跨文件分支与 1.1 卫生化互斥：多文件候选各有独立静态筛选。"""

    def _stub_pp(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        import src.tools.patch_postprocess as pp_mod

        spy = MagicMock(return_value=(_PATCH_SANITIZED, ["imports_repaired"]))
        monkeypatch.setattr(
            pp_mod, "postprocess_enabled_flags", lambda: {"import_repair": True, "contract_alias": False}
        )
        monkeypatch.setattr(pp_mod, "sanitize_patch", spy)
        return spy

    def test_cross_file_path_skips_postprocess(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        spy = self._stub_pp(monkeypatch)
        state = _state(
            tmp_path,
            cross_file_deps=[{"source_module": "mod", "target_module": "calculator", "symbol": "add", "call_line": 1}],
        )
        with patch("src.tools.cross_file.apply_multi_file_patch", return_value=({"mod": _PATCH}, True)):
            update = _run(monkeypatch, state, CROSS_FILE_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert spy.call_count == 0, "跨文件分支不重复卫生化"
        assert "postprocess_labels" not in update
        assert update["target_code"] == _PATCH

    def test_single_file_path_runs_postprocess(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：同一 stub、cross_file_deps 为空 → 卫生化必须执行（否则上一条是假绿）。"""
        spy = self._stub_pp(monkeypatch)
        state = _state(tmp_path, cross_file_deps=[])
        _run(monkeypatch, state, CROSS_FILE_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert spy.call_count == 1

    def test_cross_file_branch_without_patch_text_sends_no_candidate(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """nodes.py:1879 的 False 腿：跨文件分支里 state["patch"] 为空 → 候选表保持空。

        锁的是"没有补丁文本就不构造候选"——把 None/"" 塞进 `patches[entry]`
        等于交给多文件应用器一份空补丁，多文件口径下比单文件更难察觉（拓扑
        序里它会"成功应用"成空文件）。这里 stub 掉 apply_multi_file_patch，
        只观察它收到的 patches。
        """
        self._stub_pp(monkeypatch)
        captured: dict[str, Any] = {}

        def _fake(original_files, patches, entry, deps=None):
            captured["patches"] = dict(patches)
            captured["entry"] = entry
            return {"mod": _PATCH}, True

        state = _state(
            tmp_path,
            patch_text=None,
            cross_file_deps=[{"source_module": "mod", "target_module": "calculator", "symbol": "add", "call_line": 1}],
        )
        with patch("src.tools.cross_file.apply_multi_file_patch", _fake):
            update = _run(monkeypatch, state, CROSS_FILE_ENABLE="true", PATCH_EVIDENCE_GATE_ENABLE="false")
        assert captured["patches"] == {}
        assert captured["entry"] == "mod"
        assert update["target_code"] == _PATCH
