"""R4（2026-10-09 审查落地·S1）：反例驱动精化（CEGIR）测试。

覆盖口径：
- 开关默认关 → 不触发 LLM，返回原 spec；
- 无冲突（前件/后件均 sat）→ 0 轮收敛，LLM 未调用；
- 前件空洞 / 后件自相矛盾 → 回灌 LLM 修正契约 → SMT 复验收敛；
- LLM 非 JSON 输出 / 无有效子句 → 保守停止（converged=False，不臆造）；
- max_rounds 耗尽 → 不收敛；
- spec None / 无签名 / 无代码 → 早退不精化。

z3 缺失环境（默认 CI requirements 不含 z3）下 z3 相关用例整组跳过
（与 test_spec_smt.py 同口径）；开关/降级用例始终运行。LLM 调用一律经
可注入回调 mock，零真实 LLM 成本。
"""

from __future__ import annotations

import pytest

from src.specs import spec_refine
from src.specs.spec_refine import refine_spec_with_counterexample
from src.specs.spec_smt import smt_available

requires_z3 = pytest.mark.skipif(not smt_available(), reason="z3-solver 未安装（pip install aitester[formal]）")


def _seq_refine(responses: list[str]):
    """构造按顺序返回的 mock 精化回调（每次调用弹出一个响应）。"""
    idx = {"i": 0}

    def _fn(_prompt: str) -> str:
        r = responses[min(idx["i"], len(responses) - 1)]
        idx["i"] += 1
        return r

    return _fn


# ─── 开关与降级（不依赖 z3）─────────────────────────────────────────────────


def test_disabled_returns_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEC_REFINE_ENABLE", raising=False)
    spec = {"preconditions": ["x > 0"], "postconditions": ["r > 0"]}
    called: list[str] = []
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return x", _llm_refine=lambda p: called.append(p) or "{}"
    )
    assert result["spec"] is spec  # 原 spec 引用不变
    assert result["rounds"] == 0
    assert called == []  # LLM 未调用


def test_none_spec_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    result = refine_spec_with_counterexample(None, ["x"], target_code="def f(x): return x")
    assert result["spec"] is None
    assert result["rounds"] == 0


def test_missing_signature_or_code_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 3", "x < 2"]}
    assert refine_spec_with_counterexample(spec, None, target_code="def f(x): return x")["spec"] is spec
    assert refine_spec_with_counterexample(spec, [], target_code="def f(x): return x")["spec"] is spec
    assert refine_spec_with_counterexample(spec, ["x"], target_code="")["spec"] is spec


def test_max_rounds_env_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_MAX_ROUNDS", "99")
    assert spec_refine._max_refine_rounds() == 5
    monkeypatch.setenv("SPEC_REFINE_MAX_ROUNDS", "-3")
    assert spec_refine._max_refine_rounds() == 0


# ─── 反例精化（需 z3）─────────────────────────────────────────────────────────


@requires_z3
def test_no_conflict_converges_zero_rounds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 0"], "postconditions": ["r > 0"]}
    called: list[str] = []
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return x", _llm_refine=lambda p: called.append(p) or "{}"
    )
    assert result["converged"] is True
    assert result["rounds"] == 0
    assert called == []


@requires_z3
def test_precondition_conflict_refined(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 3", "x < 2"], "postconditions": ["r > 0"]}
    refined_json = '{"preconditions": ["x > 3"], "postconditions": ["r > 0"], "invariants": []}'
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return x + 1", _llm_refine=_seq_refine([refined_json])
    )
    assert result["converged"] is True
    assert result["rounds"] == 1
    # 修正后的前件不再互相矛盾
    assert result["spec"]["preconditions"] == ["x > 3"]
    assert result["spec"]["postconditions"] == ["r > 0"]
    # 首轮 findings 记录前件 unsat
    assert result["initial_findings"]["precondition"]["status"] == "unsat"
    assert result["final_findings"]["precondition"]["status"] == "sat"


@requires_z3
def test_postcondition_conflict_refined(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 0"], "postconditions": ["r > 0", "r < 0"]}
    refined_json = '{"preconditions": ["x > 0"], "postconditions": ["r > 0"], "invariants": []}'
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return abs(x)", _llm_refine=_seq_refine([refined_json])
    )
    assert result["converged"] is True
    assert result["rounds"] == 1
    assert result["final_findings"]["postcondition"]["status"] == "sat"


@requires_z3
def test_invalid_json_stops_conservatively(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 3", "x < 2"]}
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return x", _llm_refine=_seq_refine(["这不是 JSON"])
    )
    assert result["converged"] is False
    assert result["spec"] is spec  # 保留原 spec，不臆造


@requires_z3
def test_empty_refinement_keeps_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 3", "x < 2"], "postconditions": []}
    # LLM 返回空 JSON（无有效子句）→ _apply_refinement 保持原字段
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return x", _llm_refine=_seq_refine(["{}"])
    )
    assert result["spec"]["preconditions"] == ["x > 3", "x < 2"]


@requires_z3
def test_max_rounds_exhausted_not_converged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_REFINE_ENABLE", "true")
    spec = {"preconditions": ["x > 3", "x < 2"]}
    # LLM 一直返回同样矛盾的规约 → 迭代耗尽仍 unsat
    persistent = '{"preconditions": ["x > 3", "x < 2"], "postconditions": [], "invariants": []}'
    result = refine_spec_with_counterexample(
        spec, ["x"], target_code="def f(x): return x", max_rounds=2, _llm_refine=_seq_refine([persistent, persistent])
    )
    assert result["converged"] is False
    assert result["rounds"] == 2
    assert len(result["history"]) == 3  # 0（初始）+ 2（两轮迭代）
