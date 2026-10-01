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

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.patch_applier import (
    _count_function_defs,
    _extract_function_names,
    _find_function_range,
    _is_full_file_patch,
    apply_multi_function_patch,
    apply_patch_to_code,
    generate_diff,
    safe_apply_patch,
)
from src.utils.helpers import extract_code_block


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
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


@pytest.mark.unit
class TestExtractPatchCode:
    """测试补丁代码提取。"""

    def test_extract_python_fenced(self):
        """提取 ```python 标记的代码。"""
        patch = "```python\ndef foo(): pass\n```"
        result = extract_code_block(patch)
        assert "def foo():" in result

    def test_extract_generic_fenced(self):
        """提取通用 ``` 标记的代码。"""
        patch = "```\ndef foo(): pass\n```"
        result = extract_code_block(patch)
        assert "def foo():" in result

    def test_extract_python_prefix(self):
        """提取 python: 前缀的代码。"""
        patch = "python:\ndef foo(): pass"
        result = extract_code_block(patch)
        assert "def foo():" in result

    def test_extract_python_label_variants(self):
        """python 标签的多种形态（冒号/多空白换行/大写）仍正确剥离。"""
        assert "def foo" in extract_code_block("python:\ndef foo(): pass")
        assert "def hello" in extract_code_block("python  \n\ndef hello(): pass")
        assert "def hi" in extract_code_block("PYTHON:\ndef hi(): pass")

    def test_extract_python_identifier_line_preserved(self):
        """以 python 开头的合法标识符行不得被误剥离。

        回归：此前 startswith('python') + re.sub ^python 会把 python_path = 3
        剥成 _path = 3，破坏代码；加 (?!\\w) 后仅剥离独立标签。
        """
        assert extract_code_block("python_path = 3") == "python_path = 3"
        assert extract_code_block("python_version = '3.12'") == "python_version = '3.12'"

    def test_extract_plain_text(self):
        """无标记时直接返回原文。"""
        patch = "def foo(): pass"
        result = extract_code_block(patch)
        assert result == "def foo(): pass"

    def test_extract_with_whitespace(self):
        """提取时去除空白。"""
        patch = "  \n```python\ndef foo(): pass\n```  \n"
        result = extract_code_block(patch)
        assert result.strip() == "def foo(): pass"


@pytest.mark.unit
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
        _new_code, success = apply_patch_to_code(original, patch_code)
        assert success is True


@pytest.mark.unit
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

    def test_not_found_patch_applied_last(self):
        """0.9 回归：未找到的补丁（定位 -1）排在最后应用，不因 reverse=True
        被误当"行序最大"而最先应用（应用本身逐补丁独立定位，行序假设不成立；
        未找到的必失败 → all_success=False，失败时保留的进度与输入序无关）。"""
        original = """
def zeta(): return 0
def alpha(): return 0
"""
        # alpha 行序靠后、zeta 行序靠前；加上一个定位不到的补丁
        patches = [
            {"function_name": "alpha", "patch": "def alpha(): return 1"},
            {"function_name": "zeta", "patch": "def zeta(): return 2"},
            {"function_name": "ghost", "patch": "def ghost(): return 3"},
        ]
        new_code, success = apply_multi_function_patch(original, patches)
        assert success is False
        # 两个找到的补丁均成功应用；ghost 排最后、必失败
        assert "return 1" in new_code
        assert "return 2" in new_code
        assert "ghost" not in new_code

    def test_apply_empty_patches(self):
        """空补丁列表返回原代码。"""
        original = "def foo(): return 0"
        new_code, success = apply_multi_function_patch(original, [])
        assert success is True
        assert new_code == original


@pytest.mark.unit
class TestSafeApplyPatch:
    """测试安全补丁应用。"""

    def test_safe_apply_valid_patch(self, monkeypatch):
        """有效补丁安全应用。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "def foo(): return 0"
        patch_code = "def foo(): return 1"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is True
        assert "return 1" in new_code

    def test_safe_apply_invalid_syntax(self, monkeypatch):
        """语法错误的补丁回滚。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "def foo(): return 0"
        patch_code = "def foo(: return 1"  # 语法错误
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is False
        assert new_code == original

    def test_safe_apply_failed_patch(self, monkeypatch):
        """应用失败的补丁返回原代码。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "def foo(): return 0"
        patch_code = "def bar(): return 1"  # 函数名不匹配
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is False
        assert new_code == original

    def test_safe_apply_rejects_new_dangerous_shell(self, monkeypatch):
        """S2 安全：补丁新引入 os.system 时被拒绝（默认开关 true）。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "def foo():\n    return 0\n"
        patch_code = "def foo():\n    import os\n    os.system('ls')\n    return 1\n"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is False
        assert new_code == original

    def test_safe_apply_allows_preexisting_dangerous_calls(self, monkeypatch):
        """S2 安全差集口径：原代码已有的 subprocess 调用不因修复被拦截。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "import subprocess\n\ndef run():\n    return subprocess.run(['echo', 'hi'])\n"
        patch_code = "def run():\n    return subprocess.run(['echo', 'hello'])\n"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is True
        assert "hello" in new_code

    def test_safe_apply_dangerous_guard_disabled(self, monkeypatch):
        """S2 开关关闭（PATCH_DANGEROUS_API_GUARD=false）时危险调用放行。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "false")
        original = "def foo():\n    return 0\n"
        patch_code = "def foo():\n    import os\n    os.system('ls')\n    return 1\n"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is True
        assert "os.system" in new_code


@pytest.mark.unit
class TestDangerousApiAdded:
    """测试 S2 危险 API 守卫（AST 级差集检查，patch_applier.dangerous_api_added）。"""

    def test_new_shell_call_detected(self):
        from src.tools.patch_applier import dangerous_api_added

        original = "def foo():\n    return 1\n"
        patched = "def foo():\n    import os\n    os.system('ls')\n    return 1\n"
        assert "os.system" in dangerous_api_added(original, patched)

    def test_existing_call_not_flagged(self):
        from src.tools.patch_applier import dangerous_api_added

        original = "import subprocess\n\ndef run():\n    subprocess.run(['x'])\n"
        patched = "import subprocess\n\ndef run():\n    subprocess.run(['y'])\n"
        assert dangerous_api_added(original, patched) == []

    def test_eval_detected(self):
        from src.tools.patch_applier import dangerous_api_added

        original = "def foo():\n    return 0\n"
        patched = "def foo():\n    return eval('1+1')\n"
        assert "eval" in dangerous_api_added(original, patched)

    def test_network_call_detected(self):
        from src.tools.patch_applier import dangerous_api_added

        original = "def exfil():\n    return 0\n"
        patched = "import requests\n\ndef exfil():\n    return requests.post('https://x/y', data={})\n"
        assert "requests.post" in dangerous_api_added(original, patched)

    def test_credential_open_detected(self):
        from src.tools.patch_applier import dangerous_api_added

        original = "def load():\n    return ''\n"
        patched = "def load():\n    with open('.env') as f:\n        return f.read()\n"
        assert any("open" in s for s in dangerous_api_added(original, patched))

    def test_credential_open_preexisting_not_flagged(self):
        from src.tools.patch_applier import dangerous_api_added

        original = "def load():\n    return open('.env').read()\n"
        patched = "def load():\n    return open('.env').read().strip()\n"
        assert dangerous_api_added(original, patched) == []

    def test_unparseable_input_returns_empty(self):
        from src.tools.patch_applier import dangerous_api_added

        assert dangerous_api_added("def foo(:", "def foo(:") == []
        assert dangerous_api_added("", "def foo(): pass") == []

    def test_safe_apply_rejects_new_dangerous_shell(self, monkeypatch):
        """S2 安全：补丁新引入 os.system 时被拒绝（默认开关 true）。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "def foo():\n    return 0\n"
        patch_code = "def foo():\n    import os\n    os.system('ls')\n    return 1\n"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is False
        assert new_code == original

    def test_safe_apply_allows_preexisting_dangerous_calls(self, monkeypatch):
        """S2 安全差集口径：原代码已有的 subprocess 不拦截。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "true")
        original = "import subprocess\n\ndef run():\n    return subprocess.run(['echo', 'hi'])\n"
        patch_code = "def run():\n    return subprocess.run(['echo', 'hello'])\n"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is True
        assert "hello" in new_code

    def test_safe_apply_dangerous_guard_disabled(self, monkeypatch):
        """S2 开关关闭（PATCH_DANGEROUS_API_GUARD=false）时危险调用放行。"""
        monkeypatch.setenv("PATCH_DANGEROUS_API_GUARD", "false")
        original = "def foo():\n    return 0\n"
        patch_code = "def foo():\n    import os\n    os.system('ls')\n    return 1\n"
        new_code, success = safe_apply_patch(original, patch_code)
        assert success is True
        assert "os.system" in new_code


@pytest.mark.unit
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


@pytest.mark.unit
class TestCollapseBlankLines:
    """测试空行压缩（通过 apply_patch_to_code 间接测试）。"""

    def test_collapse_consecutive_blank_lines(self):
        """压缩连续空行。"""
        from src.tools.patch_applier import _collapse_blank_lines

        lines = ["def foo():", "", "", "", "    pass"]
        result = _collapse_blank_lines(lines)
        blank_count = sum(1 for line in result if line.strip() == "")
        assert blank_count <= 1
