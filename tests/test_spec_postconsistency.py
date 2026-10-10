"""R4（2026-10-09 审查落地·S1）：后件一致性检测测试。

覆盖口径：
- 后件自洽（sat）：存在 (inputs, r) 满足全部后件 → 规约自洽；
- 后件矛盾（unsat）：后件同时要求互斥约束（如 r>0 且 r<0）→ 自相矛盾；
- 后件 + invariant 混合、签名参数 + 结果变量联合约束；
- 保守跳过：无后件 / None spec / 无签名 / 白名单违例（调用/属性）/ 未知名 /
  非 Bool 子句；
- check_spec_consistency 联合检测（前件空洞 + 后件矛盾两 finding 汇总）；
- 开关与降级用例（z3 缺失时跳过）。

z3 缺失环境（默认 CI requirements 不含 z3）下 z3 相关用例整组跳过
（与 test_spec_smt.py 同口径）；降级路径始终运行。
"""

from __future__ import annotations

import pytest

from src.specs import spec_smt
from src.specs.spec_smt import (
    check_postcondition_consistency,
    check_spec_consistency,
    smt_available,
)

requires_z3 = pytest.mark.skipif(not smt_available(), reason="z3-solver 未安装（pip install aitester[formal]）")


# ─── 降级路径（不依赖 z3，始终运行）─────────────────────────────────────────


def test_postcondition_z3_missing_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spec_smt, "smt_available", lambda: False)
    result = check_postcondition_consistency({"postconditions": ["r > 0"]}, ["n"])
    assert result["status"] == "skipped"
    assert result["clauses"] == 0


def test_spec_consistency_z3_missing_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(spec_smt, "smt_available", lambda: False)
    result = check_spec_consistency({"preconditions": ["n > 0"]}, ["n"])
    assert result["precondition"]["status"] == "skipped"
    assert result["postcondition"]["status"] == "skipped"


# ─── 后件一致性检测（需 z3）─────────────────────────────────────────────────


@requires_z3
def test_postcondition_consistent_sat() -> None:
    spec = {"postconditions": ["r > 0"]}
    result = check_postcondition_consistency(spec, ["n"])
    assert result["status"] == "sat"
    assert result["clauses"] == 1
    assert "r" in result["variables"]


@requires_z3
def test_postcondition_contradiction_unsat() -> None:
    # 后件同时要求 r>0 且 r<0 → 无论实现如何都无解（规约自相矛盾）
    spec = {"postconditions": ["r > 0", "r < 0"]}
    result = check_postcondition_consistency(spec, ["n"])
    assert result["status"] == "unsat"
    assert result["clauses"] == 2


@requires_z3
def test_postcondition_with_invariant() -> None:
    # invariant 与 postcondition 共用后件口径（r 自由变量）
    spec = {"postconditions": ["r >= 0"], "invariants": ["r < 100"]}
    result = check_postcondition_consistency(spec, ["n"])
    assert result["status"] == "sat"
    assert result["clauses"] == 2


@requires_z3
def test_postcondition_binding_input_and_result() -> None:
    # 后件把结果变量 r 与签名参数 n 关联（r == n * 2）
    spec = {"postconditions": ["r == n * 2"]}
    result = check_postcondition_consistency(spec, ["n"])
    assert result["status"] == "sat"
    assert result["variables"] == ["n", "r"]


@requires_z3
def test_postcondition_no_clauses_skipped() -> None:
    assert check_postcondition_consistency({"postconditions": []}, ["n"])["status"] == "skipped"
    assert check_postcondition_consistency(None, ["n"])["status"] == "skipped"
    assert check_postcondition_consistency({"postconditions": ["r > 0"]}, None)["status"] == "skipped"
    assert check_postcondition_consistency({"postconditions": ["r > 0"]}, [])["status"] == "skipped"


@requires_z3
def test_postcondition_call_clause_skipped() -> None:
    # 调用子句（len(r)>0）→ 白名单/翻译层保守跳过
    spec = {"postconditions": ["len(r) > 0"]}
    assert check_postcondition_consistency(spec, ["n"])["status"] == "skipped"


@requires_z3
def test_postcondition_non_bool_clause_skipped() -> None:
    # 纯算术后件（r + 1）非 Bool → 保守跳过（无有效后件约束）
    spec = {"postconditions": ["r + 1"]}
    assert check_postcondition_consistency(spec, ["n"])["status"] == "skipped"


@requires_z3
def test_postcondition_unknown_name_skipped() -> None:
    # 后件引用签名与 r 之外的名称（z）→ 整体不可翻译
    spec = {"postconditions": ["r > z"]}
    assert check_postcondition_consistency(spec, ["n"])["status"] == "skipped"


# ─── 联合检测入口（需 z3）───────────────────────────────────────────────────


@requires_z3
def test_spec_consistency_combined() -> None:
    # 前件空洞（x>3 且 x<2）+ 后件矛盾（r>0 且 r<0）双 finding 汇总
    spec = {"preconditions": ["x > 3", "x < 2"], "postconditions": ["r > 0", "r < 0"]}
    result = check_spec_consistency(spec, ["x"])
    assert result["precondition"]["status"] == "unsat"
    assert result["postcondition"]["status"] == "unsat"


@requires_z3
def test_spec_consistency_both_sat() -> None:
    spec = {"preconditions": ["x > 0"], "postconditions": ["r > 0"]}
    result = check_spec_consistency(spec, ["x"])
    assert result["precondition"]["status"] == "sat"
    assert result["postcondition"]["status"] == "sat"
