"""tools/oracle_validator 恒真 / 魔数 / 类型不一致断言检查分支补齐。

锁定 2026-10-02 批次 oracle_validator 低覆盖分支（纯静态，零 LLM / 零网络）：
- check_assertions 空 / 语法错误降级
- 恒真断言 6 类识别（assert True / x is not None / 自反比较 / 逻辑恒真 /
  范围恒真 / 自包含）
- 魔数白名单 / 非白名单魔数识别
- 类型不一致（== str 但 LHS 推断为 int）
- _infer_constant_type 各常量类型
"""

from __future__ import annotations


class TestCheckAssertionsEmptyBranch:
    def test_empty_code_returns_empty(self):
        from src.tools.oracle_validator import check_assertions

        assert check_assertions("") == []
        assert check_assertions("   ") == []

    def test_syntax_error_returns_empty(self):
        from src.tools.oracle_validator import check_assertions

        assert check_assertions("def f(:\n") == []

    def test_no_asserts_returns_empty(self):
        from src.tools.oracle_validator import check_assertions

        assert check_assertions("def f(x):\n    return x\n") == []


class TestTautologicalAssertBranches:
    def test_assert_true_tautological(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    assert True\n")
        types = [f["type"] for f in findings]
        assert "tautological" in types

    def test_x_is_not_none_tautological(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    x = 5\n    assert x is not None\n")
        assert "tautological" in [f["type"] for f in findings]

    def test_reflexive_compare_tautological(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    x = 5\n    assert x == x\n")
        assert "tautological" in [f["type"] for f in findings]

    def test_x_is_x_reflexive(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    x = 5\n    assert x is x\n")
        assert "tautological" in [f["type"] for f in findings]

    def test_logical_tautology_x_or_not_x(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    x = 1\n    assert x or not x\n")
        assert "tautological" in [f["type"] for f in findings]

    def test_len_nonnegative_tautology(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    x = []\n    assert len(x) >= 0\n")
        assert "tautological" in [f["type"] for f in findings]

    def test_self_contained_in_tautology(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    x = [1]\n    assert x in x\n")
        assert "tautological" in [f["type"] for f in findings]

    def test_meaningful_assert_not_tautological(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    assert add(1,2) == 3\n")
        assert "tautological" not in [f["type"] for f in findings]


class TestMagicNumberBranches:
    def test_tolerated_int_not_flagged(self):
        from src.tools.oracle_validator import check_assertions

        # 0/1/2/-1/10/100/256/1000 白名单
        for val in (0, 1, 2, 10, 100, 1000):
            findings = check_assertions(f"def test_x():\n    assert add(1,2) == {val}\n")
            assert "magic_number" not in [f["type"] for f in findings], f"val={val}"

    def test_non_whitelist_int_flagged(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    assert add(1,2) == 42\n")
        assert "magic_number" in [f["type"] for f in findings]

    def test_non_whitelist_float_flagged(self):
        from src.tools.oracle_validator import check_assertions

        findings = check_assertions("def test_x():\n    assert f() == 3.14159\n")
        assert "magic_number" in [f["type"] for f in findings]


class TestTypeMismatchBranches:
    def test_type_mismatch_flagged(self):
        from src.tools.oracle_validator import check_assertions

        target = "def f(x):\n    return 1\n"
        test = "def test_x():\n    assert f(1) == 'hello'\n"
        findings = check_assertions(test, target_code=target)
        assert "type_mismatch" in [f["type"] for f in findings]

    def test_no_mismatch_when_types_align(self):
        from src.tools.oracle_validator import check_assertions

        target = "def f(x):\n    return 1\n"
        test = "def test_x():\n    assert f(1) == 2\n"
        findings = check_assertions(test, target_code=target)
        assert "type_mismatch" not in [f["type"] for f in findings]


class TestInferConstantTypeBranches:
    def test_infer_constant_types(self):
        import ast

        from src.tools.oracle_validator import _infer_constant_type

        def _infer(code):
            return _infer_constant_type(ast.parse(code).body[0].value)

        assert _infer("True") == "bool"
        assert _infer("5") == "int"
        assert _infer("1.5") == "float"
        assert _infer("'s'") == "str"
        assert _infer("b'b'") == "bytes"
        assert _infer("None") == "None"
        assert _infer("x") is None  # 非常量


class TestOracleValidateSwitchBranch:
    def test_default_false(self, monkeypatch):
        from src.tools.oracle_validator import oracle_validate_enabled

        monkeypatch.delenv("ORACLE_VALIDATE_ENABLE", raising=False)
        assert oracle_validate_enabled() is False

    def test_true(self, monkeypatch):
        from src.tools.oracle_validator import oracle_validate_enabled

        monkeypatch.setenv("ORACLE_VALIDATE_ENABLE", "true")
        assert oracle_validate_enabled() is True

    def test_stats_structure(self, monkeypatch):
        from src.tools.oracle_validator import oracle_validator_stats

        monkeypatch.delenv("ORACLE_VALIDATE_ENABLE", raising=False)
        out = oracle_validator_stats()
        assert isinstance(out, dict)
        assert "enabled" in out
