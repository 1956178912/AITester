"""
PatchApplier 单元测试

测试 patch_applier.py 中的：
- apply_patch_to_code 函数
- apply_multi_function_patch 函数
- safe_apply_patch 函数
- 辅助函数
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.patch_applier import (
    _count_function_defs,
    _extract_function_names,
    _extract_patch_code,
    _find_function_range,
    _is_full_file_patch,
    apply_multi_function_patch,
    apply_patch_to_code,
    generate_diff,
    safe_apply_patch,
)


class TestExtractFunctionNames:
    """测试函数名提取。"""

    def test_extract_single_function(self):
        """提取单个函数名。"""
        code = "def foo(): pass"
        result = _extract_function_names(code)
        assert result == {"foo"}

    def test_extract_multiple_functions(self):
        """提取多个函数名。"""
        code = """
def foo(): pass
def bar(): pass
def baz(): pass
"""
        result = _extract_function_names(code)
        assert result == {"foo", "bar", "baz"}

    def test_extract_no_functions(self):
        """无函数时返回空集合。"""
        code = "x = 1\ny = 2"
        result = _extract_function_names(code)
        assert result == set()

    def test_extract_function_with_args(self):
        """提取带参数的函数名。"""
        code = "def foo(a, b, c): pass"
        result = _extract_function_names(code)
        assert "foo" in result


class TestCountFunctionDefs:
    """测试函数定义计数。"""

    def test_count_single_function(self):
        """计数单个函数。"""
        code = "def foo(): pass"
        assert _count_function_defs(code) == 1

    def test_count_multiple_functions(self):
        """计数多个函数。"""
        code = """
def foo(): pass
def bar(): pass
"""
        assert _count_function_defs(code) == 2

    def test_count_no_functions(self):
        """无函数时计数为 0。"""
        code = "x = 1"
        assert _count_function_defs(code) == 0


class TestIsFullFilePatch:
    """测试完整文件补丁判断。"""

    def test_patch_with_docstring(self):
        """含 docstring 的补丁判定为完整文件。"""
        patch_code = '"""\nModule docstring.\n"""\ndef foo(): pass'
        assert _is_full_file_patch(patch_code, "def foo(): pass") is True

    def test_patch_with_import(self):
        """含 import 的补丁判定为完整文件。"""
        patch_code = "import os\ndef foo(): pass"
        assert _is_full_file_patch(patch_code, "def foo(): pass") is True

    def test_patch_with_multiple_functions(self):
        """含多个函数的补丁判定为完整文件。"""
        patch_code = """
def foo(): pass
def bar(): pass
"""
        original_code = """
def foo(): pass
def bar(): pass
"""
        assert _is_full_file_patch(patch_code, original_code) is True

    def test_single_function_patch(self):
        """单函数补丁判定为非完整文件。"""
        patch_code = "def foo(): return 1"
        original_code = "def foo(): return 0"
        assert _is_full_file_patch(patch_code, original_code) is False


class TestFindFunctionRange:
    """测试函数范围查找。"""

    def test_find_single_function(self):
        """查找单个函数范围。"""
        code = """def foo():
    pass

def bar():
    return 1
"""
        lines = code.split("\n")
        start, end = _find_function_range(lines, "foo", 0)
        assert start == 0
        # end 指向下一个函数定义或文件末尾，包含空行
        assert end == 3

    def test_find_last_function(self):
        """查找最后一个函数范围。"""
        code = """def foo():
    pass
"""
        lines = code.split("\n")
        start, end = _find_function_range(lines, "foo", 0)
        assert start == 0
        assert end == len(lines)  # 到文件末尾

    def test_find_class_after_function(self):
        """函数后跟类时正确结束。"""
        code = """def foo():
    pass

class Bar:
    pass
"""
        lines = code.split("\n")
        start, end = _find_function_range(lines, "foo", 0)
        assert start == 0
        # end 指向 class 定义行
        assert end == 3


class TestExtractPatchCode:
    """测试补丁代码提取。"""

    def test_extract_python_fenced(self):
        """提取 ```python 标记的代码。"""
        patch = "```python\ndef foo(): pass\n```"
        result = _extract_patch_code(patch)
        assert "def foo():" in result

    def test_extract_generic_fenced(self):
        """提取通用 ``` 标记的代码。"""
        patch = "```\ndef foo(): pass\n```"
        result = _extract_patch_code(patch)
        assert "def foo():" in result

    def test_extract_python_prefix(self):
        """提取 python: 前缀的代码。"""
        patch = "python:\ndef foo(): pass"
        result = _extract_patch_code(patch)
        assert "def foo():" in result

    def test_extract_plain_text(self):
        """无标记时直接返回原文。"""
        patch = "def foo(): pass"
        result = _extract_patch_code(patch)
        assert result == "def foo(): pass"

    def test_extract_with_whitespace(self):
        """提取时去除空白。"""
        patch = "  \n```python\ndef foo(): pass\n```  \n"
        result = _extract_patch_code(patch)
        assert result.strip() == "def foo(): pass"


class TestApplyPatchToCode:
    """测试补丁应用。"""

    def test_apply_single_function_patch(self):
        """应用单函数补丁。"""
        original = """
def foo():
    return 0

def bar():
    return 1
"""
        patch_code = """
def foo():
    return 1
"""
        new_code, success = apply_patch_to_code(original, patch_code)
        assert success is True
        assert "return 1" in new_code
        assert "return 0" not in new_code

    def test_apply_patch_missing_function(self):
        """补丁函数不存在时返回原代码。"""
        original = "def foo(): return 0"
        patch_code = "def bar(): return 1"
        new_code, success = apply_patch_to_code(original, patch_code)
        assert success is False
        assert new_code == original

    def test_apply_empty_patch(self):
        """空补丁返回原代码。"""
        original = "def foo(): return 0"
        new_code, success = apply_patch_to_code(original, "")
        assert success is False
        assert new_code == original

    def test_apply_full_file_patch(self):
        """应用完整文件补丁。"""
        original = """
import os
def foo(): return 0
def bar(): return 1
"""
        patch_code = """
import os
def foo(): return 1
def bar(): return 2
"""
        new_code, success = apply_patch_to_code(original, patch_code)
        assert success is True
        assert "return 1" in new_code
        assert "return 2" in new_code

    def test_full_file_patch_missing_function(self):
        """完整文件补丁缺少函数时回退到单函数替换。"""
        original = """
def foo(): return 0
def bar(): return 1
"""
        patch_code = """
def foo(): return 1
"""
        new_code, success = apply_patch_to_code(original, patch_code)
        # 单函数模式会成功替换目标函数
        assert success is True
        assert "return 1" in new_code
        assert "def bar():" in new_code  # bar 保留

    def test_apply_patch_with_markdown(self):
        """应用带 markdown 标记的补丁。"""
        original = "def foo(): return 0"
        patch_code = "```python\ndef foo(): return 1\n```"
        new_code, success = apply_patch_to_code(original, patch_code)
        assert success is True
        assert "return 1" in new_code

    def test_apply_patch_with_python_prefix(self):
        """应用带 python: 前缀的补丁。"""
        original = "def foo(): return 0"
        patch_code = "python:\ndef foo(): return 1"
        new_code, success = apply_patch_to_code(original, patch_code)
        assert success is True


class TestApplyMultiFunctionPatch:
    """测试多函数补丁应用。"""

    def test_apply_multiple_patches(self):
        """应用多个补丁。"""
        original = """
def foo(): return 0
def bar(): return 0
"""
        patches = [
            {"function_name": "foo", "patch": "def foo(): return 1"},
            {"function_name": "bar", "patch": "def bar(): return 2"},
        ]
        new_code, success = apply_multi_function_patch(original, patches)
        assert success is True
        assert "return 1" in new_code
        assert "return 2" in new_code

    def test_apply_partial_patches(self):
        """部分补丁成功时返回当前代码。"""
        original = """
def foo(): return 0
def bar(): return 0
"""
        patches = [
            {"function_name": "foo", "patch": "def foo(): return 1"},
            {"function_name": "baz", "patch": "def baz(): return 2"},  # 不存在的函数
        ]
        new_code, success = apply_multi_function_patch(original, patches)
        assert success is False
        assert "return 1" in new_code

    def test_apply_empty_patches(self):
        """空补丁列表返回原代码。"""
        original = "def foo(): return 0"
        new_code, success = apply_multi_function_patch(original, [])
        assert success is True
        assert new_code == original


class TestSafeApplyPatch:
    """测试安全补丁应用。"""

    def test_safe_apply_valid_patch(self):
        """有效补丁安全应用。"""
        original = "def foo(): return 0"
        patch_code = "def foo(): return 1"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is True
        assert "return 1" in new_code

    def test_safe_apply_invalid_syntax(self):
        """语法错误的补丁回滚。"""
        original = "def foo(): return 0"
        patch_code = "def foo(: return 1"  # 语法错误
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is False
        assert new_code == original

    def test_safe_apply_failed_patch(self):
        """应用失败的补丁返回原代码。"""
        original = "def foo(): return 0"
        patch_code = "def bar(): return 1"  # 函数名不匹配
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is False
        assert new_code == original


class TestGenerateDiff:
    """测试 diff 生成。"""

    def test_generate_diff_basic(self):
        """生成基本 diff。"""
        old_code = "def foo(): return 0"
        new_code = "def foo(): return 1"
        diff = generate_diff(old_code, new_code)
        assert "-return 0" in diff or "return 0" in diff
        assert "+return 1" in diff or "return 1" in diff

    def test_generate_diff_no_change(self):
        """无变化时 diff 为空。"""
        code = "def foo(): return 0"
        diff = generate_diff(code, code)
        assert diff == ""

    def test_generate_diff_multiple_changes(self):
        """多处变化的 diff。"""
        old_code = """
def foo():
    return 0
"""
        new_code = """
def foo():
    return 1
    return 2
"""
        diff = generate_diff(old_code, new_code)
        assert "return 1" in diff
        assert "return 2" in diff


class TestCollapseBlankLines:
    """测试空行压缩（通过 apply_patch_to_code 间接测试）。"""

    def test_collapse_consecutive_blank_lines(self):
        """压缩连续空行。"""
        from src.tools.patch_applier import _collapse_blank_lines
        lines = ["def foo():", "", "", "", "    pass"]
        result = _collapse_blank_lines(lines)
        blank_count = sum(1 for line in result if line.strip() == "")
        assert blank_count <= 1
