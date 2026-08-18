"""
单元测试：补充测试 patch_applier 的边界情况。

现有 test_patch_applier.py 覆盖了主要路径，此处补充边界场景：
    - 多函数补丁替换单个函数
    - 补丁含 import 被识别为完整文件模式
    - 原代码无函数定义时不崩溃
    - 补丁函数名在原代码中不存在
"""

from src.tools.patch_applier import _extract_patch_code, apply_patch_to_code


# ─── TestApplyPatchBoundary：补丁应用边界情况 ──────────────────────────────────
class TestApplyPatchBoundary:
    """测试补丁应用的边界场景。"""

    def test_patch_with_import_treated_as_full_file(self):
        """含 import 的补丁被视为完整文件模式。"""
        original = """\
def add(a, b):
    return a + b
"""
        patch = """\
import math

def add(a, b):
    return a + b
"""
        new_code, success = apply_patch_to_code(original, patch)
        # 补丁含 import，应被识别为完整文件模式
        assert success is True
        assert "import math" in new_code

    def test_patch_with_two_functions_on_single_func_original(self):
        """补丁含两个函数但原代码只有一个函数时，按单函数模式处理。"""
        original = """\
def only_one(a):
    return a
"""
        patch = """\
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b
"""
        new_code, success = apply_patch_to_code(original, patch)
        # 原代码只有1个函数，补丁有2个，走单函数模式（替换第一个匹配的）
        # 由于补丁中第一个函数是 add，原代码中没有 add，所以应返回 False
        assert success is False

    def test_empty_original_code(self):
        """原代码为空时不崩溃。"""
        result, success = apply_patch_to_code("", "def foo(): pass")
        assert success is False

    def test_patch_with_only_whitespace(self):
        """补丁仅为空白字符时不替换。"""
        original = "def foo(): pass\n"
        result, success = apply_patch_to_code(original, "   \n  ")
        assert success is False

    def test_patch_function_not_in_original(self):
        """补丁函数名在原代码中不存在时返回原代码。"""
        original = "def existing(): pass\n"
        patch = "def nonexistent(): pass\n"
        result, success = apply_patch_to_code(original, patch)
        assert success is False
        assert result == original

    def test_single_function_patch_replaces_correctly(self):
        """单函数补丁精确替换目标函数。"""
        original = '''\
"""Module doc."""

def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
'''
        patch = "def add(a, b):\n    return a + b + 1"
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return a + b + 1" in new_code
        assert "return a - b" in new_code  # subtract 未受影响


# ─── TestExtractPatchCodeBoundary：补丁代码提取边界 ────────────────────────────
class TestExtractPatchCodeBoundary:
    """测试补丁代码提取的边界情况。"""

    def test_extract_nested_code_blocks(self):
        """嵌套代码块时提取最外层。"""
        patch = "```python\ndef outer():\n    ```inner```\n    return 1\n```"
        result = _extract_patch_code(patch)
        assert "def outer()" in result

    def test_extract_mixed_markers(self):
        """混合使用不同标记格式。"""
        patch = "一些说明\n```python\ndef foo(): pass\n``` 更多说明"
        result = _extract_patch_code(patch)
        assert "def foo(): pass" in result

    def test_extract_python_prefix_with_colon(self):
        """python: 前缀（带冒号）的处理。"""
        patch = "python:\ndef foo(): pass"
        result = _extract_patch_code(patch)
        assert "def foo(): pass" in result

    def test_extract_case_insensitive_python_prefix(self):
        """Python: 大写前缀也应处理。"""
        patch = "Python:\ndef bar(): pass"
        result = _extract_patch_code(patch)
        assert "def bar(): pass" in result
