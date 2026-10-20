"""覆盖率补口：`spec_ir_v2.py` 的见证绑定与受限求值边界（2026-10-19）。

目标分支均为**可达的保守降级路径**：
- `_precondition_witness_binding` 对求解层异常 / 空见证 / 结构非法的
  fail-closed 回退（任何异常都不得阻断 oracle 生成）；
- `evaluate_guarded_expression` / `_eval_guarded_node` 对白名单外算子的拒绝；
- `_example_input_env` 的示例映射边界（非 dict / 签名未知 / 0 参元数）；
- `_coerce_boundary_literal` 的"字面量解析为非数值"保守保留；
- `_compile_smt_witness_tests` 对"见证输入与签名无交集"的跳过。

零 LLM、零 z3 依赖：求解层用 monkeypatch 注入确定性返回值。
"""

from __future__ import annotations

import ast
import logging
from typing import ClassVar

import pytest

from src.specs import spec_ir_v2 as m
from src.specs import spec_smt


def _patch_smt(monkeypatch: pytest.MonkeyPatch, *, result: object = None, raises: Exception | None = None) -> None:
    """把 spec_smt 的两个入口替换为确定性替身（被测函数内部 import 生效）。"""
    monkeypatch.setattr(spec_smt, "spec_smt_enabled", lambda: True)
    if raises is not None:

        def _boom(*_args: object, **_kwargs: object) -> object:
            raise raises

        monkeypatch.setattr(spec_smt, "generate_spec_witnesses", _boom)
    else:
        monkeypatch.setattr(spec_smt, "generate_spec_witnesses", lambda *_a, **_k: result)


class TestAsComments:
    def test_blank_line_preserved_and_clause_commented(self) -> None:
        """空行保持空行（不产出孤立 `#`），非空行保留缩进并加 provenance 前缀。"""
        assert m._as_comments(["", "  x == 1  "]) == ["", "  # [未断言·无满足前件的见证] x == 1"]


class TestPreconditionWitnessBinding:
    def test_solver_exception_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smt(monkeypatch, raises=RuntimeError("solver down"))
        assert m._precondition_witness_binding(["x > 0"], ["x"]) is None

    def test_empty_witnesses_fall_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smt(monkeypatch, result=[])
        assert m._precondition_witness_binding(["x > 0"], ["x"]) is None

    def test_non_dict_witness_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smt(monkeypatch, result=[None])
        assert m._precondition_witness_binding(["x > 0"], ["x"]) is None

    def test_non_dict_inputs_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smt(monkeypatch, result=[{"inputs": "x=1"}])
        assert m._precondition_witness_binding(["x > 0"], ["x"]) is None

    def test_missing_parameter_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """见证未覆盖全部签名参数 → 不部分绑定（避免一半 SMT 一半 0）。"""
        _patch_smt(monkeypatch, result=[{"inputs": {"a": 1}}])
        assert m._precondition_witness_binding(["a > 0", "b > 0"], ["a", "b"]) is None

    def test_container_value_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """容器见证值无法安全写成源码字面量 → 放弃。"""
        _patch_smt(monkeypatch, result=[{"inputs": {"a": [1]}}])
        assert m._precondition_witness_binding(["a"], ["a"]) is None

    def test_full_scalar_witness_returns_binding(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_smt(monkeypatch, result=[{"inputs": {"a": 1, "b": "x"}}])
        assert m._precondition_witness_binding(["a > 0", "b"], ["a", "b"]) == {"a": 1, "b": "x"}


class TestGuardedEvaluation:
    def test_or_all_falsy_returns_last_value(self) -> None:
        assert m.evaluate_guarded_expression("0 or 0", {}) == (True, 0)

    def test_unsupported_unary_op_rejected(self) -> None:
        with pytest.raises(TypeError, match="unsupported_unary_op"):
            m._eval_guarded_node(ast.parse("~1", mode="eval").body, {})

    def test_unsupported_bin_op_rejected(self) -> None:
        with pytest.raises(TypeError, match="unsupported_bin_op"):
            m._eval_guarded_node(ast.parse("1 & 2", mode="eval").body, {})

    def test_unsupported_node_rejected(self) -> None:
        with pytest.raises(TypeError, match="unsupported_ast_node"):
            m._eval_guarded_node(ast.parse("f(1)", mode="eval").body, {})


class TestExampleInputEnv:
    def test_non_dict_example_rejected(self) -> None:
        assert m._example_input_env("bad", ["a"]) is None

    def test_unknown_signature_rejects_container_input(self) -> None:
        assert m._example_input_env({"input": [1, 2], "expected": 3}, None) is None

    def test_zero_arity_rejects_non_empty_input(self) -> None:
        assert m._example_input_env({"input": [1], "expected": 3}, []) is None

    def test_zero_arity_accepts_empty_input(self) -> None:
        assert m._example_input_env({"input": [], "expected": 3}, []) == {"r": 3, "result": 3}


class TestBoundaryCoercion:
    def test_literal_that_parses_to_bool_keeps_original(self) -> None:
        """`"True"` 解析为 bool（非数值）→ 保留原串，不臆测成 1。"""
        assert m._coerce_boundary_literal("True") == "True"


class TestSmtWitnessCompilation:
    def test_witness_without_signature_overlap_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """见证输入与签名无交集 → 不产出只验前件的弱测试，整体返回空串。"""
        _patch_smt(monkeypatch, result=[{"inputs": {"b": 1}, "kind": "sat"}])
        code = m._compile_smt_witness_tests(
            {"preconditions": ["a > 0"]},
            ["a"],
            ["    assert a > 0"],
            ["    assert r > 0"],
            "f",
        )
        assert code == ""


@pytest.mark.unit
class TestProductSelfCheckGuards:
    """AB-3：产物自检是**注入防线**，必须真跑过一次才算数（2026-10-19 行级 trace 定位）。

    oracle / SMT 见证两条链在把生成的代码交出去之前都做一次 `ast.parse` 自检，
    失败即**保守丢弃并返回空串**——这是"坏代码不得进入执行链路"的唯一拦截点。
    自检分支若从未被执行，它就只是一段看起来安全的代码；本类用**对抗性
    `target_function`**（名字里带换行与引号，使渲染产物语法非法）把它触发到行级：
    oracle 侧命中 1920/1921/1922，见证侧命中 2023/2024/2025/2026。
    """

    SPEC: ClassVar[dict[str, object]] = {
        "function_name": "f",
        "preconditions_expr": ["x >= 0"],
        "postconditions_expr": ["r >= 0"],
    }

    def test_oracle_self_check_discards_unparseable_product(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="src.specs.spec_ir_v2"):
            code = m.compile_spec_oracle(self.SPEC, target_module="mod", target_function='f"\n', signature_params=["x"])
        assert code == "", "自检失败的产物必须整段丢弃，不得返回半截代码"
        assert "oracle 产物自检失败" in caplog.text, "必须留下可审计的丢弃原因"

    def test_witness_self_check_discards_unparseable_product(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        _patch_smt(monkeypatch, result=[{"inputs": {"x": 3}, "kind": "sat"}])
        with caplog.at_level(logging.WARNING, logger="src.specs.spec_ir_v2"):
            code = m._compile_smt_witness_tests(self.SPEC, ["x"], ["    assert x >= 0"], ["    assert r >= 0"], 'f"\n')
        assert code == ""
        assert "SMT 见证产物自检失败" in caplog.text

    def test_postcondition_guard_shadows_the_later_assert_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """反面锁定：后件无 assert 在**入口**就被拒（1989），故循环内的同类检查（2013/2014）不可达。

        这条不是补覆盖，是把"2014 恒不执行"钉住：若将来有人放宽 1989 的入口门，
        本用例仍返回空串，但 `spec_ir_v2` 的未覆盖行会多出 2014 —— 那时才说明
        循环内那道门真的活着，需要单独评估。
        """
        _patch_smt(monkeypatch, result=[{"inputs": {"x": 3}, "kind": "sat"}])
        assert m._compile_smt_witness_tests(self.SPEC, ["x"], ["    a = 1"], ["    # 只有注释"], "f") == ""
