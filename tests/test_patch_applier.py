"""
单元测试：测试 patch_applier 模块的补丁应用逻辑。

覆盖两种补丁模式：
    - 完整文件模式：补丁含 docstring/import/多函数时，直接替换整个文件
    - 单函数模式：补丁仅含单个函数定义时，精确替换对应函数
    - 多函数模式：同时修改多个函数
    - 递归函数模式：处理包含递归调用的函数
    - 安全应用模式：失败时自动回滚

边界情况：
    - 空补丁、不存在的函数名、连续空行压缩等
"""

from src.tools.patch_applier import (
    _extract_patch_code,
    apply_multi_function_patch,
    apply_patch_to_code,
    generate_diff,
    safe_apply_multi_function_patch,
    safe_apply_patch,
)

# 测试用原始代码：两个简单函数
ORIGINAL_CODE = '''\
"""示例模块。"""

def add(a: int, b: int) -> int:
    """返回两数之和。"""
    return a + b

def multiply(a: int, b: int) -> int:
    """返回两数之积。"""
    return a * b
'''


# 递归函数测试用例
RECURSIVE_CODE = '''\
def factorial(n: int) -> int:
    """计算阶乘。"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fibonacci(n: int) -> int:
    """计算斐波那契数。"""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
'''


# 多函数测试用例
MULTI_FUNC_CODE = '''\
def func_a(x: int) -> int:
    """函数A。"""
    return x + 1

def func_b(x: int) -> int:
    """函数B。"""
    return x * 2

def func_c(x: int) -> int:
    """函数C。"""
    return x - 1
'''


# ─── TestExtractPatchCode：从 LLM 输出中提取补丁代码 ──────────────────────────
class TestExtractPatchCode:
    """测试从 LLM 输出中提取补丁代码。"""

    def test_markdown_python_block(self):
        """验证能正确提取 ```python 包裹的代码块。"""
        patch = "```python\ndef foo(): pass\n```"
        result = _extract_patch_code(patch)
        assert "def foo(): pass" in result

    def test_markdown_generic_block(self):
        """验证能正确提取 ``` 包裹的通用代码块。"""
        patch = "```\ndef foo(): pass\n```"
        result = _extract_patch_code(patch)
        assert "def foo(): pass" in result

    def test_plain_python_prefix(self):
        """验证能处理 python: 前缀格式。"""
        patch = "python:\ndef foo(): pass"
        result = _extract_patch_code(patch)
        assert "def foo(): pass" in result

    def test_plain_code_without_markers(self):
        """验证无标记时直接返回原文。"""
        patch = "def foo(): pass"
        result = _extract_patch_code(patch)
        assert result == "def foo(): pass"


# ─── TestApplyPatchToCode：补丁应用到原始代码 ─────────────────────────────────
class TestApplyPatchToCode:
    """测试补丁应用到原始代码。"""

    def test_full_file_replacement(self):
        """验证完整文件补丁能替换整个代码。"""
        patch = (
            '"""\n修复后的模块。\n"""\n\ndef add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n'
        )
        new_code, success = apply_patch_to_code(ORIGINAL_CODE, patch)
        assert success is True
        assert "修复后的模块" in new_code

    def test_single_function_replacement(self):
        """验证单函数补丁只替换目标函数。"""
        patch = 'def add(a: int, b: int) -> int:\n    """修复后的加法。"""\n    return a + b + 1'
        new_code, success = apply_patch_to_code(ORIGINAL_CODE, patch)
        assert success is True
        assert "return a + b + 1" in new_code
        assert "return a * b" in new_code  # multiply 未受影响

    def test_empty_patch_returns_original(self):
        """验证空补丁不改变原代码。"""
        new_code, success = apply_patch_to_code(ORIGINAL_CODE, "")
        assert success is False
        assert new_code == ORIGINAL_CODE

    def test_no_func_match_returns_original(self):
        """验证补丁中函数名在原代码中不存在时不替换。"""
        patch = "def nonexistent(): pass"
        new_code, success = apply_patch_to_code(ORIGINAL_CODE, patch)
        assert success is False
        assert new_code == ORIGINAL_CODE

    def test_blanket_replacement(self):
        """验证包含全部原函数的完整文件补丁直接替换。"""
        patch = '"""New module."""\n\ndef add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n'
        new_code, success = apply_patch_to_code(ORIGINAL_CODE, patch)
        assert success is True
        assert "New module" in new_code

    def test_recursive_function_replacement(self):
        """验证递归函数可以正确替换。"""
        patch = '''def factorial(n: int) -> int:
    """修复后的阶乘函数。"""
    if n <= 1:
        return 1
    return n * factorial(n - 1) * 2'''
        new_code, success = apply_patch_to_code(RECURSIVE_CODE, patch)
        assert success is True
        assert "return n * factorial(n - 1) * 2" in new_code
        assert "def fibonacci" in new_code  # 其他函数未受影响

    def test_multiline_function_replacement(self):
        """验证多行函数可以正确替换。"""
        patch = '''def add(a: int, b: int) -> int:
    """修复后的加法。"""
    result = a + b
    if result < 0:
        return 0
    return result'''
        new_code, success = apply_patch_to_code(ORIGINAL_CODE, patch)
        assert success is True
        assert "result = a + b" in new_code
        assert "if result < 0:" in new_code
        assert "return result" in new_code


# ─── TestMultiFunctionPatch：多函数修改 ───────────────────────────────────────
class TestMultiFunctionPatch:
    """测试多函数同时修改。"""

    def test_apply_multiple_patches(self):
        """验证可以同时修改多个函数。"""
        patches = [
            {"function_name": "func_a", "patch": "def func_a(x: int) -> int:\n    return x + 10"},
            {"function_name": "func_b", "patch": "def func_b(x: int) -> int:\n    return x * 3"},
        ]
        new_code, success = apply_multi_function_patch(MULTI_FUNC_CODE, patches)
        assert success is True
        assert "return x + 10" in new_code
        assert "return x * 3" in new_code
        assert "return x - 1" in new_code  # func_c 未受影响

    def test_apply_single_patch_from_list(self):
        """验证单元素补丁列表正常工作。"""
        patches = [{"function_name": "func_a", "patch": "def func_a(x: int) -> int:\n    return x + 100"}]
        new_code, success = apply_multi_function_patch(MULTI_FUNC_CODE, patches)
        assert success is True
        assert "return x + 100" in new_code
        assert "return x * 2" in new_code  # func_b 未受影响

    def test_empty_patches_list(self):
        """验证空补丁列表返回原代码。"""
        new_code, success = apply_multi_function_patch(MULTI_FUNC_CODE, [])
        assert success is True
        assert new_code == MULTI_FUNC_CODE

    def test_patch_nonexistent_function(self):
        """验证修改不存在的函数时返回失败。"""
        patches = [{"function_name": "nonexistent", "patch": "def nonexistent(): pass"}]
        new_code, success = apply_multi_function_patch(MULTI_FUNC_CODE, patches)
        assert success is False
        assert new_code == MULTI_FUNC_CODE


# ─── TestSafeApplyPatch：安全应用补丁 ───────────────────────────────────────
class TestSafeApplyPatch:
    """测试安全应用补丁（失败时自动回滚）。"""

    def test_safe_apply_valid_patch(self):
        """验证有效补丁成功应用。"""
        patch = "def add(a: int, b: int) -> int:\n    return a + b + 1"
        new_code, success = safe_apply_patch(ORIGINAL_CODE, patch)
        assert success is True
        assert "return a + b + 1" in new_code

    def test_safe_apply_syntax_error_rolls_back(self):
        """验证语法错误的补丁自动回滚。"""
        # 故意构造语法错误的补丁
        # 这个补丁本身语法正确，但测试语法错误回滚
        syntax_error_patch = "def broken():\n    if True\n        pass"
        new_code, success = safe_apply_patch(ORIGINAL_CODE, syntax_error_patch)
        assert success is False
        assert new_code == ORIGINAL_CODE

    def test_safe_apply_empty_patch(self):
        """验证空补丁返回原代码。"""
        new_code, success = safe_apply_patch(ORIGINAL_CODE, "")
        assert success is False
        assert new_code == ORIGINAL_CODE


# ─── TestSafeApplyMultiFunctionPatch：安全多函数应用 ──────────────────────────
class TestSafeApplyMultiFunctionPatch:
    """测试安全多函数补丁应用。"""

    def test_safe_multi_function_valid(self):
        """验证有效的多函数补丁成功应用。"""
        patches = [
            {"function_name": "func_a", "patch": "def func_a(x: int) -> int:\n    return x + 10"},
            {"function_name": "func_b", "patch": "def func_b(x: int) -> int:\n    return x * 3"},
        ]
        new_code, success = safe_apply_multi_function_patch(MULTI_FUNC_CODE, patches)
        assert success is True
        assert "return x + 10" in new_code
        assert "return x * 3" in new_code

    def test_safe_multi_function_syntax_error(self):
        """验证包含语法错误的多函数补丁自动回滚。"""
        patches = [
            {"function_name": "func_a", "patch": "def func_a(x: int) -> int:\n    return x + 10"},
            {
                "function_name": "func_b",
                "patch": "def func_b(x: int) -> int:\n    if True\n        pass",  # 语法错误
            },
        ]
        new_code, success = safe_apply_multi_function_patch(MULTI_FUNC_CODE, patches)
        # 由于包含语法错误，应该回滚
        assert success is False
        assert new_code == MULTI_FUNC_CODE


# ─── TestGenerateDiff：生成 diff ───────────────────────────────────────────
class TestGenerateDiff:
    """测试 diff 生成功能。"""

    def test_generate_diff_basic(self):
        """验证能生成基本的 diff。"""
        old = "def foo():\n    return 1\n"
        new = "def foo():\n    return 2\n"
        diff = generate_diff(old, new)
        assert "---" in diff
        assert "+++" in diff
        assert "-    return 1" in diff
        assert "+    return 2" in diff

    def test_generate_diff_empty(self):
        """验证相同代码生成空 diff。"""
        code = "def foo():\n    return 1\n"
        diff = generate_diff(code, code)
        assert diff == ""


# ─── 边界情况测试 ───────────────────────────────────────────────────────────
class TestEdgeCases:
    """测试边界情况。"""

    def test_nested_function_replacement(self):
        """验证嵌套函数不会被误替换。"""
        code = """\
def outer():
    def inner():
        return 42
    return inner()

def other():
    return 1
"""
        patch = """def other():
    return 2"""
        new_code, success = apply_patch_to_code(code, patch)
        assert success is True
        assert "return 42" in new_code  # inner 未受影响
        assert "return 2" in new_code  # other 已修改

    def test_function_with_class(self):
        """验证包含类的代码可以正确替换。"""
        code = """\
class MyClass:
    def method(self):
        return 1

def standalone():
    return 2
"""
        patch = """def standalone():
    return 3"""
        new_code, success = apply_patch_to_code(code, patch)
        assert success is True
        assert "return 1" in new_code  # 类方法未受影响
        assert "return 3" in new_code  # 独立函数已修改

    def test_whitespace_variations(self):
        """验证不同缩进格式的处理。"""
        code = """\
def func(x):
    if x > 0:
      return x
    else:
        return -x
"""
        patch = """def func(x):
    return abs(x)"""
        new_code, success = apply_patch_to_code(code, patch)
        assert success is True
        assert "return abs(x)" in new_code
