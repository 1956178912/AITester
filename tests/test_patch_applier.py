"""
单元测试：测试 patch_applier 模块的补丁应用逻辑。
覆盖完整文件替换和单函数替换两种模式。
"""

import pytest
from src.tools.patch_applier import apply_patch_to_code, _extract_patch_code


ORIGINAL_CODE = '''\
"""示例模块。"""

def add(a: int, b: int) -> int:
    """返回两数之和。"""
    return a + b

def multiply(a: int, b: int) -> int:
    """返回两数之积。"""
    return a * b
'''


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


class TestApplyPatchToCode:
    """测试补丁应用到原始代码。"""

    def test_full_file_replacement(self):
        """验证完整文件补丁能替换整个代码。"""
        patch = '"""\n修复后的模块。\n"""\n\ndef add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n'
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
