"""测试 src/tools/code_analyzer.py（此前 0% 覆盖、无调用方）

覆盖四个公开函数的正常/边界/异常路径：
- parse_function_nodes：普通/异步/嵌套/方法（self 保留在 args）
- extract_function_code：同步/异步/未找到
- compute_cyclomatic_complexity：线性=1、if/循环/except/三目/and-or 计数
- replace_function_code：同步/异步替换成功、新代码非法、函数不存在、替换后语法错误回滚
"""

from src.tools.code_analyzer import (
    compute_cyclomatic_complexity,
    extract_function_code,
    parse_function_nodes,
    replace_function_code,
)


class TestParseFunctionNodes:
    """parse_function_nodes"""

    def test_sync_function(self):
        nodes = parse_function_nodes("def f(a, b=1):\n    '''doc'''\n    return a + b\n")
        assert len(nodes) == 1
        n = nodes[0]
        assert n["name"] == "f"
        assert n["args"] == ["a", "b"]
        assert n["docstring"] == "doc"
        assert n["lineno"] == 1 and n["end_lineno"] == 3

    def test_async_function_detected(self):
        nodes = parse_function_nodes("async def g():\n    return 1\n")
        assert len(nodes) == 1 and nodes[0]["name"] == "g"

    def test_nested_and_class_methods(self):
        src = "class C:\n    def m(self, x):\n        return x\n"
        nodes = parse_function_nodes(src)
        assert nodes[0]["name"] == "m"
        # 首个参数 self 保留在 args 中（调用方自行判断是否剔除）
        assert nodes[0]["args"] == ["self", "x"]

    def test_invalid_syntax_raises(self):
        import pytest

        with pytest.raises(SyntaxError):
            parse_function_nodes("def broken(:")


class TestExtractFunctionCode:
    """extract_function_code"""

    def test_sync(self):
        src = "def f(x):\n    return x\n\nOTHER = 1\n"
        assert extract_function_code(src, "f") == "def f(x):\n    return x"

    def test_async(self):
        src = "async def g():\n    return 1\n"
        assert extract_function_code(src, "g") == "async def g():\n    return 1"

    def test_not_found_returns_none(self):
        assert extract_function_code("def f():\n    pass\n", "h") is None


class TestComputeCyclomaticComplexity:
    """compute_cyclomatic_complexity"""

    def test_linear_code_is_one(self):
        assert compute_cyclomatic_complexity("x = 1\ny = 2\n") == 1

    def test_if_and_elif(self):
        src = "def f(a):\n    if a:\n        pass\n    elif a == 2:\n        pass\n"
        # 1 + if + elif(嵌套 If) = 3
        assert compute_cyclomatic_complexity(src) == 3

    def test_loops_and_except(self):
        src = (
            "def f(items):\n"
            "    for i in items:\n"
            "        while i:\n"
            "            i -= 1\n"
            "    try:\n"
            "        pass\n"
            "    except ValueError:\n"
            "        pass\n"
        )
        # 1 + for + while + ExceptHandler = 4
        assert compute_cyclomatic_complexity(src) == 4

    def test_ternary_counts(self):
        # 1(基线) + 1(IfExp) = 2
        assert compute_cyclomatic_complexity("x = 1 if a else 2\n") == 2

    def test_bool_op_chained(self):
        # CPython 将 a and b and c 折叠为单个 BoolOp(3 值) → 1 + 2 = 3
        assert compute_cyclomatic_complexity("return a and b and c") == 3


class TestReplaceFunctionCode:
    """replace_function_code"""

    def test_replace_sync(self):
        src = "def f(x):\n    return x\nZ = 9\n"
        new_code, ok = replace_function_code(src, "f", "def f(x):\n    return x * 2\n")
        assert ok is True
        assert "return x * 2" in new_code and "Z = 9" in new_code

    def test_replace_async(self):
        """回归：AsyncFunctionDef 不是 FunctionDef 子类，旧版会静默漏配 async def"""
        src = "async def g():\n    return 1\nZ = 9\n"
        new_code, ok = replace_function_code(src, "g", "async def g():\n    return 2\n")
        assert ok is True
        assert "return 2" in new_code and "Z = 9" in new_code

    def test_invalid_new_code_refused(self):
        src = "def f():\n    return 1\n"
        new_code, ok = replace_function_code(src, "f", "def f(:\n")
        assert ok is False
        assert new_code == src  # 原码不变

    def test_missing_function_refused(self):
        src = "def f():\n    return 1\n"
        new_code, ok = replace_function_code(src, "h", "def h():\n    return 2\n")
        assert ok is False
        assert new_code == src

    def test_broken_result_rolls_back(self):
        """新代码自身可解析，但拼回原位置后语法冲突 → 回滚原码。

        f 定义在 class 内（4 空格缩进），新代码按模块级 0 缩进写：
        单独 ast.parse 合法，拼回后 class C: 体变空且缩进断裂 → SyntaxError。
        """
        src = "class C:\n    def f(self):\n        return 1\nX = 1\n"
        new_code, ok = replace_function_code(src, "f", "def f(self):\n    return 1\n")
        assert ok is False
        assert new_code == src
