"""AST 级断言一致性检查（Oracle Validator）单元测试。

覆盖：
- 开关默认关（ORACLE_VALIDATE_ENABLE 未设 → oracle_validate_enabled() False）
- 开关开启（monkeypatch 环境变量）
- check_assertions 恒真断言检测（assert True / x is not None）
- check_assertions 魔数检测（assert result == 42）
- check_assertions 类型不一致检测（assert f(x) == "str" 但 f 返回 int）
- check_assertions 空测试代码 → 空列表
- check_assertions 无问题测试 → 空列表
- oracle_validator_stats 观测统计口径
"""

from __future__ import annotations

import os
from unittest.mock import patch

from src.tools.oracle_validator import (
    check_assertions,
    oracle_validate_enabled,
    oracle_validator_stats,
)


def test_oracle_validate_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("ORACLE_VALIDATE_ENABLE", None)
        assert oracle_validate_enabled() is False


def test_oracle_validate_switch_on() -> None:
    with patch.dict(os.environ, {"ORACLE_VALIDATE_ENABLE": "true"}):
        assert oracle_validate_enabled() is True


def test_tautological_assert_true() -> None:
    """assert True → 恒真断言疑点。"""
    test_code = """\
def test_something():
    result = 42
    assert True
"""
    findings = check_assertions(test_code)
    assert any(f["type"] == "tautological" for f in findings)


def test_tautological_assert_not_none() -> None:
    """x is not None（x 刚被赋值）→ 恒真断言疑点。"""
    test_code = """\
def test_something():
    x = 10
    assert x is not None
"""
    findings = check_assertions(test_code)
    assert any(f["type"] == "tautological" for f in findings)


def test_magic_number_detected() -> None:
    """assert result == 42（42 ∉ 白名单）→ 魔数疑点。"""
    test_code = """\
def test_something():
    result = compute()
    assert result == 42
"""
    findings = check_assertions(test_code)
    assert any(f["type"] == "magic_number" for f in findings)


def test_tolerated_ints_no_finding() -> None:
    """assert result == 0 / 1 / 2 / 10 → 白名单，无魔数疑点。"""
    test_code = """\
def test_a():
    assert f() == 0

def test_b():
    assert f() == 1

def test_c():
    assert f() == 2

def test_d():
    assert f() == 10
"""
    findings = check_assertions(test_code)
    assert not any(f["type"] == "magic_number" for f in findings)


def test_type_mismatch_detected() -> None:
    """assert f(1) == "str" 但 f 返回 int → 类型不一致疑点。"""
    target_code = """\
def f(x):
    return x + 1
"""
    test_code = """\
def test_f():
    assert f(1) == "one"
"""
    findings = check_assertions(test_code, target_code)
    assert any(f["type"] == "type_mismatch" for f in findings)


def test_no_findings_clean_test() -> None:
    """断言正确且使用命名常量的测试 → 无疑点。"""
    test_code = """\
EXPECTED_SUM = 10

def test_add():
    result = add(5, 5)
    assert result == EXPECTED_SUM
"""
    findings = check_assertions(test_code)
    # EXPECTED_SUM 是变量非常量 → 无魔数；10 在白名单 → 无魔数
    # 类型一致 → 无类型疑点；非常数断言 → 无恒真
    assert findings == []


def test_empty_test_code() -> None:
    """空测试代码 → 空列表。"""
    assert check_assertions("") == []
    assert check_assertions("   \n  ") == []


def test_syntax_error_test_code() -> None:
    """测试代码语法错误 → 保守返回空列表（不阻断主流程）。"""
    bad_code = """\
def test_bad(
    assert 1 == 1
"""
    assert check_assertions(bad_code) == []


def test_oracle_validator_stats() -> None:
    stats = oracle_validator_stats()
    assert "enabled" in stats
    assert "tolerated_ints" in stats
    assert 0 in stats["tolerated_ints"]
    assert 1 in stats["tolerated_ints"]


def test_multiple_asserts_multiple_findings() -> None:
    """多个断言各有问题 → 多个疑点。"""
    test_code = """\
def test_multiple():
    x = 100
    assert x is not None
    assert result == 99
    assert True
"""
    findings = check_assertions(test_code)
    types = [f["type"] for f in findings]
    assert "tautological" in types
    assert "magic_number" in types
