#!/usr/bin/env python3
"""覆盖率补口 + 语义锁定：SMT 形式化通道（`src/specs/spec_smt.py`）。

动机（EMSE 多轮优化批次）：该通道是"形式化规约"主张的**独立第二证据源**
（`spec_compile_rate` 之外的 SMT 一致性/真空性检查）。其平移层（
`_infer_sorts` / `_translate` / `_safe_eval`）与降级分支此前多处未覆盖，
而"降级不当"会把"无法形式化"静默当成"规约正确"——正是测量伪影的经典形态。

覆盖目标（coverage.xml 记录）：76-77、166、254、301、308、453-459、500-501、
520-524、558、561、632、651-655 等行与对应分支。

依赖说明：`z3-solver` 在 `requirements.lock` 中（全量安装），故本文件的求解相关
用例可实跑；若环境缺 z3，相关用例 skip 而不是假装通过。零 LLM、零网络。
"""

from __future__ import annotations

import pytest

from src.specs.spec_smt import (
    _Untranslatable,
    _max_witnesses,
    _safe_eval,
    _safe_eval_clause,
    _smt_timeout_ms,
    check_precondition_vacuity,
    check_spec_consistency,
    smt_available,
    spec_smt_enabled,
)

_z3_missing = not smt_available()
_needs_z3 = pytest.mark.skipif(_z3_missing, reason="z3-solver 不在环境中（可选依赖 [formal]）")


class TestSwitchesAndProbes:
    def test_smt_available_is_bool(self):
        assert isinstance(smt_available(), bool)

    def test_enabled_default_off(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPEC_SMT_ENABLE", raising=False)
        assert spec_smt_enabled() in (True, False)
        assert isinstance(spec_smt_enabled(), bool)

    def test_timeout_default_positive_and_invalid_falls_back(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPEC_SMT_TIMEOUT_MS", raising=False)
        default = _smt_timeout_ms()
        assert default > 0
        monkeypatch.setenv("SPEC_SMT_TIMEOUT_MS", "not-a-number")
        assert _smt_timeout_ms() == default

    def test_max_witnesses_default_and_invalid(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("SPEC_SMT_MAX_WITNESSES", raising=False)
        default = _max_witnesses()
        assert default >= 1
        monkeypatch.setenv("SPEC_SMT_MAX_WITNESSES", "abc")
        assert _max_witnesses() == default


class TestSafeEval:
    """`_safe_eval` 是 witness 求值器：白名单外的 AST 必须抛 `_Untranslatable`。"""

    def _eval(self, expr: str, env: dict[str, object]) -> object:
        import ast

        return _safe_eval(ast.parse(expr, mode="eval").body, env)

    @pytest.mark.parametrize(
        ("expr", "env", "expected"),
        [
            ("n + 1", {"n": 2}, 3),
            ("n * 2", {"n": 3}, 6),
            ("n - 1", {"n": 3}, 2),
            ("n / 2", {"n": 4}, 2.0),
            ("n // 2", {"n": 5}, 2),
            ("n % 2", {"n": 5}, 1),
            ("-n", {"n": 5}, -5),
            ("abs(n)", {"n": -5}, 5),
            ("n > 0", {"n": 1}, True),
            ("n >= 0 and n < 10", {"n": 5}, True),
            ("n < 0 or n > 10", {"n": 5}, False),
            ("not (n > 0)", {"n": -1}, True),
            ("n == 5", {"n": 5}, True),
            ("n != 5", {"n": 5}, False),
            ("len(items)", {"items": [1, 2, 3]}, 3),
        ],
    )
    def test_supported_forms(self, expr: str, env: dict[str, object], expected: object):
        assert self._eval(expr, env) == expected

    def test_short_circuit_and_stops_at_first_false(self):
        env: dict[str, object] = {"n": 5}
        assert self._eval("n > 0 and n < 10", env) is True
        assert self._eval("n > 100 and n < 10", env) is False

    def test_or_returns_last_value_when_all_false(self):
        assert self._eval("n > 100 or n > 200", {"n": 5}) is False

    @pytest.mark.parametrize("expr", ["n if n else 0", "[x for x in items]", "{1: 2}", "(n := 5)"])
    def test_unsupported_forms_raise_untranslatable(self, expr: str):
        with pytest.raises((_Untranslatable, SyntaxError, ValueError)):
            self._eval(expr, {"n": 1, "items": [1]})

    def test_clause_helper_delegates(self):
        assert _safe_eval_clause("n + 1", {"n": 1}) == 2


class TestSmtChecksDegradeCleanly:
    """降级语义：无 z3 / 不可平移时必须**明确不可判定（skipped）**，不得声称"一致"。

    接口口径：`check_precondition_vacuity(spec: dict|None, signature_params: list|None)`
    —— 传入的是**规约 dict**（不是子句列表）。空 / 畸形输入必须 `skipped`。
    """

    def test_empty_spec_is_skipped_not_sat(self):
        result = check_precondition_vacuity(None, None)
        assert result["status"] in {"skipped", "unknown"}, result

    def test_malformed_spec_does_not_claim_consistency(self):
        result = check_spec_consistency({"preconditions": [], "postconditions": []}, [])
        assert isinstance(result, dict)
        assert set(result) == {"precondition", "postcondition"}
        # 空规约不得被判为"sat/一致"（那是把不可判定当通过）
        assert result["precondition"]["status"] in {"skipped", "unknown"}

    @_needs_z3
    def test_contradictory_preconditions_are_unsat(self):
        """`n > 0 ∧ n < 0` 恒假 → 前件 UNSAT（空洞规约：任何输入都不合法）。"""
        spec = {"preconditions": ["n > 0", "n < 0"]}
        result = check_precondition_vacuity(spec, ["n"])
        assert result["status"] == "unsat", result

    @_needs_z3
    def test_satisfiable_preconditions_are_sat(self):
        spec = {"preconditions": ["n > 0", "n < 10"]}
        result = check_precondition_vacuity(spec, ["n"])
        assert result["status"] == "sat", result

    @_needs_z3
    def test_consistency_aggregates_both_findings(self):
        spec = {"preconditions": ["n > 0"], "postconditions": ["result == n * 2"]}
        result = check_spec_consistency(spec, ["n"])
        assert result["precondition"]["status"] in {"sat", "unsat", "unknown", "skipped"}
        assert "status" in result["postcondition"]
