"""v3（2026-10-12 独立评审落地·P0-B）：ULT/PiTest 标准变异算子测试。

锁定新增 5 类算子（回应独立评审 S-08"变异体过弱、无外部可比性"）：
    8. unary_minus_remove  一元负号移除（-X → X）
    9. unary_not_insert    比较前插 not（X → not X）
   10. string_const_swap   字符串常量置换（"abc" → "xxx"，跳过 docstring）
   11. stmt_delete         语句删除（函数体直接语句，删除后非空）
   12. break_continue_swap break ↔ continue 互换

每类算子的验收口径（与 AdverTest / SWE-Mutation 的单行约束一致）：
    - 单点改动：变异代码 != 原代码；
    - 语法有效：ast.parse 通过（无效变异会虚增杀死率）；
    - 类型标签正确、行号定位正确；
    - 保守边界：docstring 不变异 / 删除后函数体非空。
"""

from __future__ import annotations

import ast

from experiments.mutation_testing import (
    ExtendedMutationGenerator,
    MutationGenerator,
    _find_deletable_statements,
    _find_mutable_string_constants,
)

# 覆盖全部新算子的被测源码（含 docstring / 字符串常量 / 循环 / 负号 / raise / not）
_SOURCE = '''\
"""模块 docstring——不得被字符串常量算子变异。"""


def clamp(x: int, lo: int = 0, hi: int = 10) -> int:
    """把 x 限制在 [lo, hi]——函数 docstring 同样不得变异。"""
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x


def first_positive(items: list) -> int:
    """返回首个正数；无正数返回 -1。"""
    if not items:
        return -1
    for i in items:
        if i > 0:
            return i
        if i < 0:
            continue
        break
    return -1


def parse_int(text: str) -> int:
    """把文本解析为 int；非法输入抛 ValueError。"""
    try:
        return int(text)
    except ValueError:
        raise ValueError("bad int")


def label(prefix: str) -> str:
    if prefix == "":
        return "empty"
    return prefix + "-tag"
'''


def _mutants_of_type(mutant_type: str) -> list:
    gen = MutationGenerator()
    return [m for m in gen.generate(_SOURCE) if m.mutant_type == mutant_type]


class TestUnaryMinusRemove:
    def test_generates_valid_mutant(self) -> None:
        mutants = _mutants_of_type("unary_minus_remove")
        assert mutants, "源码含 return -1，应产出一元负号移除变异"
        m = mutants[0]
        assert m.code != _SOURCE
        ast.parse(m.code)  # 语法有效
        assert "return 1" in m.code  # -1 → 1
        assert "一元负号移除" in m.description

    def test_no_unary_minus_no_mutant(self) -> None:
        gen = MutationGenerator()
        src = "def f(a):\n    return a + 1\n"
        assert [m for m in gen.generate(src) if m.mutant_type == "unary_minus_remove"] == []


class TestUnaryNotInsert:
    def test_generates_valid_mutant(self) -> None:
        mutants = _mutants_of_type("unary_not_insert")
        assert mutants, "源码含比较，应产出 not 插入变异"
        m = mutants[0]
        assert m.code != _SOURCE
        ast.parse(m.code)
        assert "not " in m.code
        # 语义翻转可证：插入后条件取反
        assert "not x < lo" in m.code or "not x > hi" in m.code or "not i > 0" in m.code


class TestStringConstSwap:
    def test_generates_mutant_outside_docstrings(self) -> None:
        # 聚焦源码：单字符串常量 + 函数 docstring（轮转取样下用大源码会把
        # 特定实例挤出 20 上限，故单算子验证用小源码）
        src = 'def tag(prefix: str) -> str:\n    """函数 docstring 不得变异。"""\n    return prefix + "-tag"\n'
        mutants = [m for m in MutationGenerator().generate(src) if m.mutant_type == "string_const_swap"]
        assert len(mutants) == 1, "应且仅应产出 1 个（docstring 跳过）"
        m = mutants[0]
        assert m.code != src
        ast.parse(m.code)
        # "-tag" → "xxxx"（等长 x 串；ast.unparse 统一单引号字形）
        assert "return prefix + 'xxxx'" in m.code
        # docstring 恒未被变异
        assert "函数 docstring 不得变异。" in m.code

    def test_docstrings_never_mutated(self) -> None:
        """docstring 变异恒存活、污染反馈信噪比——必须跳过。"""
        for m in _mutants_of_type("string_const_swap"):
            assert "模块 docstring" in m.code, "模块 docstring 被变异"
            assert "把 x 限制在" in m.code, "函数 docstring 被变异"
            assert "返回首个正数" in m.code, "函数 docstring 被变异"

    def test_finder_skips_docstrings(self) -> None:
        consts = _find_mutable_string_constants(ast.parse(_SOURCE))
        values = [c.value for c in consts]
        assert "模块 docstring——不得被字符串常量算子变异。" not in values
        assert "把 x 限制在 [lo, hi]——函数 docstring 同样不得变异。" not in values
        assert "-tag" in values  # 普通字符串字面量收编


class TestStmtDelete:
    def test_generates_valid_mutant(self) -> None:
        mutants = _mutants_of_type("stmt_delete")
        assert mutants, "函数体多语句，应产出语句删除变异"
        for m in mutants:
            assert m.code != _SOURCE
            ast.parse(m.code)  # 删除后语法恒有效

    def test_single_statement_function_not_deletable(self) -> None:
        """单语句函数删后空体——保守不产无效变异。"""
        gen = MutationGenerator()
        src = 'def f(a):\n    """doc"""\n    return a\n'
        assert [m for m in gen.generate(src) if m.mutant_type == "stmt_delete"] == []

    def test_finder_requires_nonempty_after_delete(self) -> None:
        tree = ast.parse(_SOURCE)
        stmts = _find_deletable_statements(tree)
        # label() 现为 If + Return 两语句（docstring 后有效语句=2）→ 可删；
        # 但"删除 label 的 return"后 If 仍在，语法有效——断言的是 clamp 类
        # 多语句函数有候选、且无 docstring 泄漏进候选
        line_nos = {s.lineno for s in stmts}
        assert 5 not in line_nos  # clamp docstring 行不进候选
        assert any(ast.unparse(s).startswith("return prefix") for s in stmts)


class TestBreakContinueSwap:
    def test_generates_both_directions(self) -> None:
        # 聚焦源码：循环内同时含 break 与 continue（大源码轮转取样会挤出实例）
        src = (
            "def f(items):\n"
            "    for i in items:\n"
            "        if i > 0:\n"
            "            break\n"
            "        continue\n"
            "    return items\n"
        )
        mutants = [m for m in MutationGenerator().generate(src) if m.mutant_type == "break_continue_swap"]
        assert len(mutants) == 2, "break 与 continue 各应产出 1 个互换变异"
        descriptions = {m.description for m in mutants}
        assert any("break → continue" in d for d in descriptions)
        assert any("continue → break" in d for d in descriptions)
        for m in mutants:
            ast.parse(m.code)
        # 语义可证：互换后代码确实含另一控制语句
        codes = {m.code for m in mutants}
        assert any("continue" in c and "break" not in c for c in codes)
        assert any("break" in c and "continue" not in c for c in codes)

    def test_no_loop_control_no_mutant(self) -> None:
        gen = MutationGenerator()
        src = "def f(a):\n    return a\n"
        assert [m for m in gen.generate(src) if m.mutant_type == "break_continue_swap"] == []


class TestOperatorSetIntegration:
    def test_base_generator_now_covers_ult_pitest_operators(self) -> None:
        """基类算子集 7 → 12（ULT/PiTest 标准类目对齐，评审 S-08）。"""
        types = {m.mutant_type for m in MutationGenerator().generate(_SOURCE)}
        for expected in (
            "operator_flip",
            "boolean_negation",
            "numeric_offset",
            "boundary_shift",
            "return_void",
            "return_empty",
            "exception_remove",
            "unary_minus_remove",
            "unary_not_insert",
            "string_const_swap",
            "stmt_delete",
            "break_continue_swap",
        ):
            assert expected in types, f"基类缺少算子 {expected}"

    def test_extended_generator_includes_new_operators(self) -> None:
        """扩展池（MDO 测量层）同步含新算子，且总量大于基类轮转池。"""
        ext_types = {m.mutant_type for m in ExtendedMutationGenerator().generate(_SOURCE)}
        for expected in (
            "unary_minus_remove",
            "unary_not_insert",
            "string_const_swap",
            "stmt_delete",
            "break_continue_swap",
        ):
            assert expected in ext_types, f"扩展池缺少算子 {expected}"
        assert len(ExtendedMutationGenerator().generate(_SOURCE)) > len(MutationGenerator().generate(_SOURCE))

    def test_pool_cap_respected(self) -> None:
        """基类上限纪律不变（≤ _MAX_MUTANTS_PER_TASK，类型轮转）。"""
        gen = MutationGenerator()
        assert len(gen.generate(_SOURCE)) <= gen._MAX_MUTANTS_PER_TASK

    def test_all_mutants_syntactically_valid(self) -> None:
        """全部变异体语法有效（无效变异会虚增杀死率——测量纪律）。"""
        for m in MutationGenerator().generate(_SOURCE):
            ast.parse(m.code)
