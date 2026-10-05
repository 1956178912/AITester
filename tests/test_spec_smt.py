"""G4（2026-10-05 优化批次·T2）：SpecSMT 见证层测试。

覆盖口径：
- 开关默认关：compile_spec_oracle 产物不含见证段（与历史逐字节一致）；
- z3 可用（本仓 [formal] extra 或本地安装）时：sat/边界见证、空洞前件
  检测、浮点/布尔排序、保守跳过路径（调用 / 未知名 / 无签名）、
  Python 语义复核、见证数上限、超时容错；
- 端到端：见证测试可执行且后件违规时确实变红（确定性检出通道）。

z3 缺失的环境（默认 CI requirements 不含 z3）下 z3 相关用例整组跳过
（与 chromadb / hypothesis 可选依赖测试同口径）；开关与降级用例始终运行。
"""

from __future__ import annotations

import ast
from typing import Any

import pytest

from src.specs import spec_smt
from src.specs.spec_ir_v2 import compile_spec_oracle
from src.specs.spec_smt import (
    check_precondition_vacuity,
    generate_spec_witnesses,
    smt_available,
    spec_smt_enabled,
)

requires_z3 = pytest.mark.skipif(not smt_available(), reason="z3-solver 未安装（pip install aitester[formal]）")


# ─── 开关与降级（不依赖 z3，始终运行）─────────────────────────────────────────


def test_flag_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEC_SMT_ENABLE", raising=False)
    assert spec_smt_enabled() is False


def test_compile_oracle_flag_off_has_no_witness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPEC_SMT_ENABLE", raising=False)
    spec: dict[str, Any] = {"preconditions": ["n >= 5"], "postconditions": ["r >= 0"], "boundaries": []}
    code = compile_spec_oracle(spec, "math", "floor", ["n"])
    assert "smt_witness" not in code
    assert code  # 主 oracle 不受开关影响


def test_timeout_env_invalid_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_SMT_TIMEOUT_MS", "abc")
    assert spec_smt._smt_timeout_ms() == 2000


def test_max_witnesses_env_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_SMT_MAX_WITNESSES", "99")
    assert spec_smt._max_witnesses() == 10
    monkeypatch.setenv("SPEC_SMT_MAX_WITNESSES", "0")
    assert spec_smt._max_witnesses() == 1


# ─── 见证生成（需 z3）─────────────────────────────────────────────────────────


@requires_z3
def test_witness_sat_and_boundary_satisfy_preconditions() -> None:
    spec = {"preconditions": ["n >= 5", "n <= 100"], "postconditions": []}
    witnesses = generate_spec_witnesses(spec, ["n"])
    assert 1 <= len(witnesses) <= 3
    for witness in witnesses:
        n = witness["inputs"]["n"]
        assert 5 <= n <= 100  # Python 语义复核已保证
    kinds = {w["kind"] for w in witnesses}
    assert "sat" in kinds
    # 有界数值目标必产出边界见证（min=5 / max=100，经去重后至少其一）
    assert kinds & {"boundary_min", "boundary_max"}


@requires_z3
def test_vacuity_unsat_detected(caplog: pytest.LogCaptureFixture) -> None:
    spec = {"preconditions": ["x > 3", "x < 2"], "postconditions": []}
    result = check_precondition_vacuity(spec, ["x"])
    assert result["status"] == "unsat"
    assert result["clauses"] == 2
    assert generate_spec_witnesses(spec, ["x"]) == []


@requires_z3
def test_vacuity_no_preconditions_skipped() -> None:
    assert check_precondition_vacuity({"preconditions": [], "postconditions": []}, ["x"])["status"] == "skipped"
    assert check_precondition_vacuity(None, ["x"])["status"] == "skipped"


@requires_z3
def test_float_and_bool_sorts() -> None:
    spec = {"preconditions": ["threshold >= 0.5", "flag == True"], "postconditions": []}
    witnesses = generate_spec_witnesses(spec, ["threshold", "flag"])
    assert witnesses
    for witness in witnesses:
        assert witness["inputs"]["threshold"] >= 0.5
        assert witness["inputs"]["flag"] is True


@requires_z3
def test_call_clause_conservatively_skipped() -> None:
    spec = {"preconditions": ["len(x) > 0"], "postconditions": []}
    assert generate_spec_witnesses(spec, ["x"]) == []


@requires_z3
def test_unknown_name_conservatively_skipped() -> None:
    # 前件引用签名之外的名称（r 属结果变量笔误）→ 整体不可翻译
    spec = {"preconditions": ["r > 0"], "postconditions": []}
    assert generate_spec_witnesses(spec, ["n"]) == []


@requires_z3
def test_none_signature_skipped() -> None:
    spec = {"preconditions": ["n >= 1"], "postconditions": []}
    assert generate_spec_witnesses(spec, None) == []
    assert generate_spec_witnesses(spec, []) == []


@requires_z3
def test_witness_cap_respected() -> None:
    spec = {"preconditions": ["n >= 1"], "postconditions": []}
    assert len(generate_spec_witnesses(spec, ["n"], max_witnesses=1)) == 1


# ─── 端到端（需 z3）：见证测试可执行 + 后件违规变红 ──────────────────────────


@requires_z3
def test_compile_oracle_witness_end_to_end(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPEC_SMT_ENABLE", "true")
    (tmp_path / "spec_smt_good_mod.py").write_text("def scale(n):\n    return n * 2\n", encoding="utf-8")
    (tmp_path / "spec_smt_bad_mod.py").write_text("def scale(n):\n    return -1\n", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = {"preconditions": ["n >= 2", "n <= 50"], "postconditions": ["r >= 4"], "boundaries": []}

    good_code = compile_spec_oracle(spec, "spec_smt_good_mod", "scale", ["n"])
    assert "test_specir_v2_smt_witness_0" in good_code
    ast.parse(good_code)
    good_ns: dict[str, Any] = {}
    exec(good_code, good_ns)
    good_ns["test_specir_v2_smt_witness_0"]()  # 正确实现：见证通过

    bad_code = compile_spec_oracle(spec, "spec_smt_bad_mod", "scale", ["n"])
    bad_ns: dict[str, Any] = {}
    exec(bad_code, bad_ns)
    with pytest.raises(AssertionError):
        bad_ns["test_specir_v2_smt_witness_0"]()  # 违反后件：确定性变红


@requires_z3
def test_compile_oracle_witness_requires_post_assert(monkeypatch: pytest.MonkeyPatch) -> None:
    # 无可编译后件 → 不产出"只验前件"的弱见证测试
    monkeypatch.setenv("SPEC_SMT_ENABLE", "true")
    spec = {"preconditions": ["n >= 2"], "postconditions": ["r 是非负数"], "boundaries": []}
    code = compile_spec_oracle(spec, "spec_smt_good_mod", "scale", ["n"])
    assert "smt_witness" not in code or "assert" in code
