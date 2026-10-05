"""A-01（2026-10-04 系统审查 P0）：SpecIR v2 受限表达式 DSL 层测试。

锁定内容（纯静态，无 LLM / 无子进程 / 无 hypothesis 依赖）：
- is_expression_clause 双通道判定（字符白名单 + ast eval）
- 白名单验证（危险调用 / 属性逃逸 / 未知标识符）
- compile_readiness 可编译率（"逻辑驱动"主张的可测量内核）
- compile_spec_oracle 三层保守绑定（boundaries / a-b / 无材料）
- spec_provenance NL 溯源清单
- spec_ir_dsl_enabled 开关口径（默认关）
"""

from __future__ import annotations

import ast

from src.specs.spec_ir_v2 import (
    compile_readiness,
    compile_spec_oracle,
    is_expression_clause,
    spec_ir_dsl_enabled,
    spec_provenance,
)


class TestIsExpressionClause:
    def test_simple_compare_expressions(self):
        assert is_expression_clause("r > 0")
        assert is_expression_clause("a == b + 1")
        assert is_expression_clause("len(x) >= 2")
        assert is_expression_clause("x <= 10")

    def test_natural_language_rejected(self):
        # 中文 NL 子句必含字符白名单外字符（通道 1 快判排除）
        assert not is_expression_clause("x 是正整数")
        assert not is_expression_clause("结果必须为正")
        assert not is_expression_clause("返回前保证输入非空")

    def test_assignment_statement_rejected(self):
        # eval 模式下 Assign 为语句，parse(mode="eval") 失败
        assert not is_expression_clause("r = f(x)")

    def test_non_str_rejected(self):
        assert not is_expression_clause(123)
        assert not is_expression_clause(None)
        assert not is_expression_clause(["a > 0"])

    def test_empty_and_long_rejected(self):
        assert not is_expression_clause("")
        assert not is_expression_clause("   ")
        assert not is_expression_clause("a > 0" * 60)  # > 200 字符保守拒绝

    def test_dangerous_calls_rejected_by_whitelist_not_channel1(self):
        # 危险调用经通道 1（字符白名单）或白名单层拦截，口径：
        # is_expression_clause=False 或 _whitelist_check 非空 → 不可执行。
        assert is_expression_clause("os.system('ls')") is False  # 通道 1 含 '
        from src.specs.spec_ir_v2 import _whitelist_check

        wl = _whitelist_check("os.system('ls')")
        assert any("attr_escape" in v or "dangerous_call" in v for v in wl)
        assert _whitelist_check("open('/etc/passwd')")  # open 不在白名单
        assert _whitelist_check("x.__class__")  # 属性逃逸


class TestWhitelistCheck:
    def test_clean_expressions_pass(self):
        from src.specs.spec_ir_v2 import _whitelist_check

        assert _whitelist_check("x >= 0") == []
        assert _whitelist_check("r > 0") == []
        assert _whitelist_check("r <= abs(x)") == []
        assert _whitelist_check("len(s) > 0") == []

    def test_parse_failed_marker_or_unicode_identifier(self):
        from src.specs.spec_ir_v2 import _whitelist_check

        # "x 不能为负" 在 py3 Unicode 标识符下：含中文 + 空格，ast.parse
        # eval 模式会 SyntaxError → ["parse_failed"]（若上游行为变化，
        # 只要非空即视为"不可编译"，口径保守不变）
        assert _whitelist_check("x 不能为负")

    def test_dangerous_attributes(self):
        from src.specs.spec_ir_v2 import _whitelist_check

        assert any("attr_escape" in v for v in _whitelist_check("x.real_part"))


class TestCompileReadiness:
    def test_mixed_spec(self):
        spec = {
            "preconditions": ["x >= 0", "x 不能为负"],
            "postconditions": ["r > 0", "结果必须为正"],
            "invariants": ["r <= abs(x)"],
        }
        # 可编译 3 / 非空 5（通道 1 排除 2 条 NL）
        assert compile_readiness(spec) == 3 / 5

    def test_all_nl_spec_zero(self):
        assert compile_readiness({"preconditions": ["x 为正"], "postconditions": ["结果非空"]}) == 0.0

    def test_no_spec_or_empty(self):
        assert compile_readiness(None) == 0.0
        assert compile_readiness({}) == 0.0
        assert compile_readiness({"preconditions": []}) == 0.0

    def test_full_machine_spec_one(self):
        spec = {"preconditions": ["x >= 0"], "postconditions": ["r > 0"], "invariants": ["r <= abs(x)"]}
        assert compile_readiness(spec) == 1.0

    def test_dangerous_call_not_counted_compiled(self):
        # 可解析但白名单违例 → 保守不计入可编译（非"可执行"）
        spec = {"preconditions": ["os.system('x') == 0"]}
        assert compile_readiness(spec) == 0.0


class TestCompileSpecOracle:
    def _spec_with_boundaries(self) -> dict:
        return {
            "preconditions": ["x >= 0", "x 不能为负"],
            "postconditions": ["r > 0", "结果必须为正"],
            "invariants": ["r <= abs(x)"],
            "boundaries": [{"input": 0, "expected": "r == 0", "rationale": "t"}],
        }

    def test_layer1_boundaries(self):
        code = compile_spec_oracle(self._spec_with_boundaries(), "mymod", "f")
        assert "x = 0" in code
        assert "assert x >= 0" in code
        assert "assert r > 0" in code
        assert "assert r <= abs(x)" in code
        assert "NL provenance" in code  # 不可编译子句保留为溯源注释
        assert "from mymod import f" in code
        ast.parse(code)  # 产物恒可执行
        # 无占位 assert True（v1 假通过防线）
        assert "assert True" not in code

    def test_layer2_ab_params(self):
        code = compile_spec_oracle({"preconditions": ["a == b"], "postconditions": ["r > 0"]}, "m", "f")
        assert "a, b = 0, 0" in code
        assert "assert r > 0" in code
        ast.parse(code)

    def test_layer3_no_input_material_returns_empty(self):
        # 无 boundaries / 无 a-b-y 引用的 pre → 无绑定不臆测 → 空串
        # （防"只有注释无断言"的空测试假通过）
        assert (
            compile_spec_oracle(
                {"preconditions": ["x >= 0"], "postconditions": ["r > 0"]},
                "m",
                "f",
            )
            == ""
        )

    def test_all_nl_spec_returns_empty(self):
        assert compile_spec_oracle({"preconditions": ["x 为正"]}, "m", "f") == ""
        assert compile_spec_oracle(None, "m", "f") == ""
        assert compile_spec_oracle(self._spec_with_boundaries()) == ""  # 缺 module 名

    def test_no_executable_assertion_returns_empty(self):
        # 有 boundaries 但子句全不可编译 → 函数体只有注释 → 保守空串
        spec = {
            "preconditions": ["x 不能为负"],
            "postconditions": ["结果必须为正"],
            "boundaries": [{"input": 0, "expected": "r == 0", "rationale": "t"}],
        }
        assert compile_spec_oracle(spec, "m", "f") == ""


class TestSpecProvenance:
    def test_extracts_nl_clauses_only(self):
        spec = {
            "preconditions": ["x >= 0", "x 不能为负"],
            "postconditions": ["r > 0", "结果必须为正"],
            "invariants": ["r <= abs(x)"],
        }
        prov = spec_provenance(spec)
        assert len(prov) == 2
        assert any("x 不能为负" in p for p in prov)
        assert any("结果必须为正" in p for p in prov)
        assert not any("r > 0" in p for p in prov)

    def test_empty_and_none(self):
        assert spec_provenance(None) == []
        assert spec_provenance({}) == []

    def test_non_str_clauses_skipped(self):
        assert spec_provenance({"preconditions": [123, "x 为正"]}) == ["preconditions: x 为正"]


class TestDslGate:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("SPEC_IR_DSL_ENABLE", raising=False)
        assert spec_ir_dsl_enabled() is False

    def test_on_variants(self, monkeypatch):
        for v in ("true", "1", "on", "TRUE"):
            monkeypatch.setenv("SPEC_IR_DSL_ENABLE", v)
            assert spec_ir_dsl_enabled() is True

    def test_off_variants(self, monkeypatch):
        for v in ("false", "0", "off", "no", "x"):
            monkeypatch.setenv("SPEC_IR_DSL_ENABLE", v)
            assert spec_ir_dsl_enabled() is False
