#!/usr/bin/env python3
"""变异生成器的"可执行性/真实性"不变量回归锁（K 轮 2026-10-17）。

## 背景（self-mutation 批次实测发现的两类假变异体）

变异得分（mutation_score）的分母是"生成的变异体数"，分子是"被测试杀死的
变异体数"。以下两类假变异体都会让分母虚增、分子不变 → **mutation_score
系统性偏低**，且缺陷形态会伪装成"测试写得弱"：

1. **identity 变异体**（与源码 AST 完全相同，任何测试都无法杀死）：
   - `_generate_numeric_offset` 对 Compare 中任意 Constant 都登记
     "const X → +1"，但 `_offset_numeric` 只偏移 int/float——`x is None` /
     `s == "abc"` 产出零改动变异体。实测 src/ 语料非数值比较常量 **668 处**；
   - `_generate_string_const_swaps` 的置换值 `"x" * len(original)` 对原文
     `'x'` 恰好仍等于 `'x'`（第 430 行实证）。
2. **语法非法变异体**（unparse 成功但产物不可解析）：
   - `_gen_subscript_negate` 对 Slice 下标产出 `x[-(a:b) - 1]`——实测单个
     文件 5 个；执行期 pytest rc=2（收集失败），而 `_run_mutant_tests` 的
     保守口径把 rc∈{2,5,超时} 记作"存活" → 生成器缺陷被记成"测试未捕获"。
     src/ 语料 Slice 下标 **268 处**。

修复口径（`experiments/mutation_testing.py` K 轮）：
- 数值偏移：仅 int/float（排除 bool）+ AST 级变化校验；
- 字符串置换：置换值必须 ≠ 原值；
- 下标取反：跳过 Slice；
- `_emit` 通用守卫：`ast.parse(new_code)` 失败即丢弃（保证"变异体池 =
  可执行单点改动"这一不变量）。

## 本文件锁定

1. 两个生成器在代表性语料上**零 invalid / 零 identity**（不变量级回归）；
2. 四个具体缺陷点的确定性反例锁；
3. `_emit` 语法守卫本身（构造非法变异 → 丢弃，不进池）。
"""

from __future__ import annotations

import ast

import pytest

from experiments.mutation_testing import ExtendedMutationGenerator, MutationGenerator

#: 代表性语料：覆盖 None/字符串比较、bool、切片、切片赋值、嵌套比较、
#: 文档字符串、异常路径——恰好是上述两类缺陷的触发面。
_CORPUS: tuple[str, ...] = (
    "def f(x):\n    return x is None\n",
    "def f(s):\n    return s == 'x'\n",
    "def f(x):\n    return x > 5\n",
    "def f(flag):\n    return True if flag else False\n",
    "def f(xs):\n    return xs[1:3]\n",
    "def f(xs, i):\n    return xs[i]\n",
    "def f(xs):\n    xs[0:2] = [1]\n    return xs\n",
    "def f(a, b):\n    if a > 1 and b is not None:\n        raise ValueError('bad')\n    return a + b\n",
)


def _mutants(source: str) -> list[tuple[MutationGenerator | ExtendedMutationGenerator, str]]:
    """收集两个生成器在该源码上产出的全部变异体代码。"""
    generators = (MutationGenerator(), ExtendedMutationGenerator(max_per_task=120))
    return [(generator, mutant.code) for generator in generators for mutant in generator.generate(source)]


class TestExecutableAndNonIdentityInvariant:
    """不变量：每个变异体都必须 (a) 语法合法、(b) AST 与源码不同。"""

    @pytest.mark.parametrize("source", _CORPUS)
    def test_all_mutants_parse_and_differ(self, source: str) -> None:
        source_dump = ast.dump(ast.parse(source))
        for generator, code in _mutants(source):
            parsed = ast.parse(code)  # 语法非法会在此抛 SyntaxError → 用例失败
            assert ast.dump(parsed) != source_dump, (
                f"{type(generator).__name__} 产出 identity 变异体（AST 与源码相同）：\n{code}"
            )

    def test_corpus_actually_produces_mutants(self) -> None:
        """语料必须真的产出变异体，否则上面的不变量是空断言。"""
        total = sum(len(_mutants(source)) for source in _CORPUS)
        assert total >= 40, f"语料产出变异体过少（{total}），检查算子是否失效"


class TestNumericOffsetIdentityFix:
    def test_none_and_string_compare_produce_no_numeric_mutant(self) -> None:
        """`x is None` / `s == "abc"` 无数字可偏移 → 不得产出 numeric_offset。"""
        gen = MutationGenerator()
        for source in ("def f(x):\n    return x is None\n", "def f(s):\n    return s == 'abc'\n"):
            types = [m.mutant_type for m in gen.generate(source)]
            assert "numeric_offset" not in types, types

    def test_bool_constant_excluded_from_numeric_offset(self) -> None:
        """True/False 是 int 子类但语义属布尔置换，不得伪装成数字偏移。"""
        gen = MutationGenerator()
        mutants = gen._generate_numeric_offset(ast.parse("def f(x):\n    return x == True\n"), "")
        assert mutants == []

    def test_numeric_compare_still_mutated(self) -> None:
        """修复不得误伤真正的数字偏移（`x > 5` → `x > 6`）。"""
        gen = MutationGenerator()
        mutants = gen._generate_numeric_offset(ast.parse("def f(x):\n    return x > 5\n"), "")
        assert len(mutants) == 1
        assert "6" in mutants[0].code
        assert mutants[0].mutant_type == "numeric_offset"


class TestStringSwapIdentityFix:
    def test_single_char_x_gets_different_replacement(self) -> None:
        """原文 `'x'` 的置换值不得仍是 `'x'`（原缺陷：`"x" * 1 == "x"`）。"""
        source = "def f(s):\n    return s == 'x'\n"
        mutants = MutationGenerator()._generate_string_const_swaps(ast.parse(source), source)
        assert len(mutants) == 1
        assert ast.dump(ast.parse(mutants[0].code)) != ast.dump(ast.parse(source))
        assert "→ 'xx'" in mutants[0].description


class TestSubscriptNegateSliceFix:
    def test_slice_subscript_skipped(self) -> None:
        """Slice 下标（xs[1:3]）不存在定义良好的取反语义 → 不产出变异体。"""
        source = "def f(xs):\n    return xs[1:3]\n"
        mutants = ExtendedMutationGenerator()._gen_subscript_negate(ast.parse(source), source)
        assert mutants == []

    def test_simple_index_mutated_and_valid(self) -> None:
        source = "def f(xs, i):\n    return xs[i]\n"
        mutants = ExtendedMutationGenerator()._gen_subscript_negate(ast.parse(source), source)
        assert len(mutants) == 1
        assert ast.parse(mutants[0].code) is not None
        assert "-i - 1" in mutants[0].code


class TestEmitSyntaxGuard:
    """`_emit` 的通用语法守卫：unparse 成功但源码非法 → 丢弃（不进变异体池）。"""

    def test_invalid_unparse_output_is_dropped(self) -> None:
        source = "def f(xs):\n    return xs[0]\n"
        tree = ast.parse(source)
        target = next(node for node in ast.walk(tree) if isinstance(node, ast.Subscript))

        def _make_invalid(node: ast.AST) -> None:
            # 用非法标识符构造"unparse 成功但产物不可解析"的确定性样例：
            # ast.unparse 对 Name(id="a b") 会原样输出 `a b` → 语法非法。
            # （真实触发形态是 Slice 下标取反，见 TestSubscriptNegateSliceFix）
            assert isinstance(node, ast.Subscript)
            node.slice = ast.Name(id="a b")

        out: list = []
        gen = ExtendedMutationGenerator()
        gen._emit(
            tree,
            target,
            _make_invalid,
            "synthetic_invalid",
            "line 1: 合成非法变异（仅测试守卫）",
            source,
            out,
        )
        assert out == [], "语法非法变异体必须被 _emit 丢弃"
