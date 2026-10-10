"""S6 规约 oracle 通道接线测试（2026-10-09 审查报告 §5 路径 A2 / J1 根因）。

锁定三件事：
1. **修复生效**：显式表达式通道（``*_expr``）现在被 ``compile_spec_oracle``
   消费（修复前只读 NL 通道，主批次 10 批 1,997 行臂注入 0 行）；
2. **回退口径零变化**：``*_expr`` 为空时回退 NL 通道，与原实现逐字节一致
   （ADR-0003 默认口径纪律）；
3. **白名单扩展**：``isinstance`` 入白名单（纯类型判定，无副作用），
   且未放宽危险调用（``open``/``eval`` 等仍被拒）。
"""

from __future__ import annotations

import pytest

from src.specs.spec_ir_v2 import (
    _ALLOWED_CALL_NAMES,
    _compile_single_clause,
    _whitelist_check,
    compile_spec_oracle,
)

EXPR_SPEC = {
    "preconditions": ["x 必须为非负整数"],  # NL（中文，不可编译）
    "postconditions": ["结果满足 r*r - x <= 1"],  # NL
    "invariants": [],
    "preconditions_expr": ["x >= 0"],  # 表达式通道
    "postconditions_expr": ["r * r - x <= 1"],
    "invariants_expr": [],
}


class TestExprChannelConsumed:
    """S6 核心：表达式通道被消费。"""

    def test_expr_spec_compiles_with_signature(self) -> None:
        code = compile_spec_oracle(EXPR_SPEC, "mod_x", "isqrt_floor", signature_params=["x"])
        assert code, "S6 修复后表达式通道应产出 oracle（修复前恒空串）"
        assert "def test_specir_v2_oracle" in code
        assert "assert x >= 0" in code
        assert "r = isqrt_floor(x)" in code
        assert "r * r - x <= 1" in code

    def test_expr_channel_preferred_over_nl(self) -> None:
        """两通道同时存在时取表达式通道（NL 中文不可编译，不应污染产物）。"""
        code = compile_spec_oracle(EXPR_SPEC, "mod_x", "isqrt_floor", signature_params=["x"])
        assert "# pre: x >= 0" in code
        assert "NL provenance" not in code.split("assert")[0]

    def test_nl_fallback_byte_identical_when_no_expr(self) -> None:
        """无 *_expr → 回退 NL，与原实现同口径（ASCII 可编译子句仍可编译）。"""
        nl_only = {
            "preconditions": ["x >= 0"],
            "postconditions": ["r >= 0"],
            "invariants": [],
        }
        code = compile_spec_oracle(nl_only, "m", "f", signature_params=["x"])
        assert code
        assert "assert x >= 0" in code
        assert "assert r >= 0" in code

    def test_nl_chinese_only_still_empty(self) -> None:
        """纯中文 NL 子句仍不可编译 → 空串（历史行为不变）。"""
        nl_cn = {"preconditions": ["x 必须为非负整数"], "postconditions": ["结果非负"], "invariants": []}
        assert compile_spec_oracle(nl_cn, "m", "f", signature_params=["x"]) == ""

    def test_empty_spec_returns_empty(self) -> None:
        assert compile_spec_oracle({}, "m", "f") == ""
        assert compile_spec_oracle(None, "m", "f") == ""

    def test_missing_module_or_function_returns_empty(self) -> None:
        assert compile_spec_oracle(EXPR_SPEC, "", "f", signature_params=["x"]) == ""
        assert compile_spec_oracle(EXPR_SPEC, "m", "", signature_params=["x"]) == ""

    def test_expr_channels_not_merged_with_nl(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """两通道不合并——避免同一子句被编译两次产生重复断言。

        **顺序无关性（2026-10-09 修复）**：`SPEC_SMT_ENABLE` 为进程级 env，
        其他测试模块 setenv 后可能泄漏到全量套件（实测开 SMT 时本用例失败），
        届时 SMT 见证测试被追加到主 oracle 之后——同一前件断言会在**每个
        见证**里各出现一次，令全串计数失真。故本用例 (a) 显式关闭 SMT 保证
        确定性；(b) 只在**主 oracle 函数体内**计数（见证块与主 oracle 并存
        是设计使然，不是"重复编译"）。
        """
        monkeypatch.setenv("SPEC_SMT_ENABLE", "false")
        mixed = dict(EXPR_SPEC)
        mixed["preconditions"] = ["x >= 0"]  # NL 通道也含同一条 ASCII 子句
        code = compile_spec_oracle(mixed, "m", "f", signature_params=["x"])
        body = code.split("def test_specir_v2_smt_witness")[0]
        assert body.count("assert x >= 0") == 1


class TestIsinstanceWhitelist:
    """S6b：isinstance 入白名单（实测真实规约高频使用）。"""

    def test_isinstance_allowed(self) -> None:
        assert "isinstance" in _ALLOWED_CALL_NAMES

    def test_isinstance_clause_compiles(self) -> None:
        spec = {
            "preconditions_expr": ["isinstance(x, int)"],
            "postconditions_expr": [],
            "invariants_expr": [],
        }
        code = compile_spec_oracle(spec, "m", "f", signature_params=["x"])
        assert code
        assert "isinstance(x, int)" in code

    def test_isinstance_passes_whitelist_check(self) -> None:
        assert _whitelist_check("isinstance(x, int)") == []

    @pytest.mark.parametrize("bad", ["open('x')", "eval('1')", "exec('x')", "__import__('os')"])
    def test_dangerous_calls_still_rejected(self, bad: str) -> None:
        """白名单扩展不得放宽危险调用。

        拒绝哨兵为 **空串**（`_compile_single_clause` 返回 str，调用方按
        NL 注释处理），非 None。
        """
        assert _whitelist_check(bad) != []
        known = frozenset({"x", "r"})
        assert _compile_single_clause(bad, "precondition", "m", "f", known) == ""

    def test_type_object_name_not_treated_as_attribute(self) -> None:
        """`isinstance(x, int)` 的第二参是 Name，不应被 visit_Attribute 误拒。"""
        assert _whitelist_check("isinstance(x, str)") == []
        assert _whitelist_check("isinstance(x, bool)") == []
