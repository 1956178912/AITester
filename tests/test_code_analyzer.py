"""
单元测试：测试 code_analyzer 模块的核心功能。

覆盖范围：
    - parse_function_nodes:        AST 函数节点解析
    - extract_function_code:       按名称提取函数代码
    - compute_cyclomatic_complexity: 圈复杂度计算
    - replace_function_code:       基于 AST 的代码替换

所有测试使用同一段 SAMPLE_CODE（含 add、divide、factorial 三个函数）。
"""

from src.tools.code_analyzer import (
    compute_cyclomatic_complexity,
    extract_function_code,
    parse_function_nodes,
    replace_function_code,
)

# ─── 公共测试样本 ──────────────────────────────────────────────────────────────
# 包含三个函数：add（简单）、divide（含条件分支）、factorial（含递归调用）
SAMPLE_CODE = '''\
"""示例模块。"""

import os


def add(a: int, b: int) -> int:
    """返回两数之和。"""
    return a + b


def divide(a: float, b: float) -> float:
    """
    返回两数之商。
    注意：除数为零时抛出 ValueError。
    """
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b


def factorial(n: int) -> int:
    """返回 n 的阶乘。"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)
'''


# ─── TestParseFunctionNodes：函数节点解析 ──────────────────────────────────────
class TestParseFunctionNodes:
    """测试函数节点解析功能。"""

    def test_parse_returns_all_functions(self):
        """验证能解析出所有函数定义。"""
        funcs = parse_function_nodes(SAMPLE_CODE)
        names = [f["name"] for f in funcs]
        assert "add" in names
        assert "divide" in names
        assert "factorial" in names
        assert len(funcs) == 3

    def test_parse_function_fields(self):
        """验证每个函数节点包含必要字段。"""
        funcs = parse_function_nodes(SAMPLE_CODE)
        add_func = next(f for f in funcs if f["name"] == "add")
        assert add_func["args"] == ["a", "b"]
        assert add_func["lineno"] == 6
        assert add_func["end_lineno"] == 8
        assert add_func["docstring"] == "返回两数之和。"

    def test_parse_empty_code(self):
        """验证空代码不抛出异常。"""
        funcs = parse_function_nodes("x = 1")
        assert funcs == []


# ─── TestExtractFunctionCode：函数代码提取 ─────────────────────────────────────
class TestExtractFunctionCode:
    """测试函数代码提取功能。"""

    def test_extract_existing_function(self):
        """验证能提取已存在的函数代码。"""
        code = extract_function_code(SAMPLE_CODE, "add")
        assert code is not None
        assert "return a + b" in code

    def test_extract_nonexistent_function(self):
        """验证提取不存在的函数返回 None。"""
        code = extract_function_code(SAMPLE_CODE, "nonexistent")
        assert code is None

    def test_extract_divide_includes_guard(self):
        """验证提取 divide 函数包含除零保护逻辑。"""
        code = extract_function_code(SAMPLE_CODE, "divide")
        assert "if b == 0" in code
        assert "raise ValueError" in code


# ─── TestComputeCyclomaticComplexity：圈复杂度计算 ─────────────────────────────
class TestComputeCyclomaticComplexity:
    """测试圈复杂度计算功能。"""

    def test_simple_function(self):
        """简单函数（无分支）复杂度为 1。"""
        code = "def f(x): return x + 1"
        assert compute_cyclomatic_complexity(code) == 1

    def test_function_with_if(self):
        """含一个 if 的函数复杂度为 2。"""
        code = "def f(x):\n    if x > 0:\n        return x\n    return -x"
        assert compute_cyclomatic_complexity(code) == 2

    def test_function_with_and(self):
        """含 and 运算符的函数复杂度正确累加。"""
        code = "def f(x, y):\n    if x > 0 and y > 0:\n        return x + y"
        # 1 (base) + 1 (if) + 1 (and) = 3
        assert compute_cyclomatic_complexity(code) == 3

    def test_factorial_complexity(self):
        """阶乘函数的圈复杂度为 2（含一个 if 判断）。"""
        assert compute_cyclomatic_complexity(SAMPLE_CODE) >= 2


# ─── TestReplaceFunctionCode：基于 AST 的代码替换 ───────────────────────────────
class TestReplaceFunctionCode:
    """测试基于 AST 的代码替换功能。"""

    def test_replace_simple_function(self):
        """验证能正确替换简单函数。"""
        new_body = "    return a * b\n"
        new_code, success = replace_function_code(
            SAMPLE_CODE, "add", "def add(a: int, b: int) -> int:\n    return a * b"
        )
        assert success is True
        assert "return a * b" in new_code
        assert "return a + b" not in new_code

    def test_replace_nonexistent_function(self):
        """验证替换不存在的函数不改变原代码。"""
        new_code, success = replace_function_code(SAMPLE_CODE, "nonexistent", "def nonexistent(): pass")
        assert success is False
        assert new_code == SAMPLE_CODE

    def test_replace_preserves_other_functions(self):
        """验证替换后其他函数代码保持不变。"""
        new_code, success = replace_function_code(
            SAMPLE_CODE, "add", "def add(a: int, b: int) -> int:\n    return a * b"
        )
        assert "return a / b" in new_code  # divide 未受影响
        assert "return n * factorial" in new_code  # factorial 未受影响

    def test_replace_invalid_syntax(self):
        """验证新代码语法错误时返回原代码。"""
        new_code, success = replace_function_code(SAMPLE_CODE, "add", "def add(a: int) -> int\n    return a")
        assert success is False
