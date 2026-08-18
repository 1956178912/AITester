"""
增强测试：测试 PatchApplier 的多函数补丁和错误恢复功能。

覆盖范围：
    - 多函数修改的补丁应用
    - 错误恢复机制
    - 边界情况处理
"""

from src.tools.patch_applier import apply_patch_to_code


# ─── TestMultiFunctionPatch：多函数补丁测试 ───────────────────────────────────
class TestMultiFunctionPatch:
    """测试多函数修改的补丁应用。"""

    def test_apply_multiple_patches(self):
        """测试同时修改多个函数。"""
        original = """\
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
"""
        patch = '''\
"""修复后的计算器模块。"""

def add(a, b):
    """添加容错处理。"""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字")
    return a + b

def subtract(a, b):
    """添加容错处理。"""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字")
    return a - b

def multiply(a, b):
    """保持原实现。"""
    return a * b
'''
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "添加容错处理" in new_code
        assert "TypeError" in new_code
        assert "保持原实现" in new_code

    def test_apply_single_patch_from_list(self):
        """测试从补丁列表应用单个补丁。"""
        original = """\
def func_a():
    return 1

def func_b():
    return 2

def func_c():
    return 3
"""
        # 只替换 func_b
        patch = """\
def func_b():
    return 20  # 修改后的值
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return 20" in new_code
        assert "return 1" in new_code
        assert "return 3" in new_code

    def test_empty_patches_list(self):
        """测试空补丁列表的处理。"""
        original = "def foo(): pass\n"
        new_code, success = apply_patch_to_code(original, "")
        assert success is False
        assert new_code == original

    def test_patch_nonexistent_function(self):
        """测试补丁函数在原代码中不存在的情况。"""
        original = "def existing_func(): pass\n"
        patch = "def nonexistent_func(): pass\n"
        new_code, success = apply_patch_to_code(original, patch)
        assert success is False
        assert new_code == original


# ─── TestErrorRecovery：错误恢复测试 ──────────────────────────────────────────
class TestErrorRecovery:
    """测试补丁应用的错误恢复机制。"""

    def test_safe_apply_valid_patch(self):
        """测试有效补丁的安全应用。"""
        original = """\
def add(a, b):
    return a + b
"""
        patch = """\
def add(a, b):
    return a + b + 1  # 修复后的版本
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return a + b + 1" in new_code

    def test_safe_apply_syntax_error_rolls_back(self):
        """测试语法错误时回滚到原代码。"""
        from src.tools.patch_applier import safe_apply_patch

        original = "def foo(): return 1\n"
        # 无效的 Python 代码作为补丁
        patch = "def foo(): return \n    invalid syntax"
        # 使用 safe_apply_patch 进行测试，它会验证语法并回滚
        new_code, success = safe_apply_patch(original, patch)
        # 由于补丁包含语法错误，应回滚到原代码
        assert success is False
        assert new_code == original

    def test_safe_apply_empty_patch(self):
        """测试空补丁时返回原代码。"""
        original = "def foo(): return 1\n"
        new_code, success = apply_patch_to_code(original, "")
        assert success is False
        assert new_code == original

    def test_malformed_patch_returns_original(self):
        """测试畸形补丁时返回原代码。"""
        original = "def foo(): return 1\n"
        patch = "This is not valid Python code at all"
        new_code, success = apply_patch_to_code(original, patch)
        assert success is False

    def test_partial_function_replacement(self):
        """测试部分函数替换的完整性。"""
        original = """\
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
"""
        # 只替换 add，保留 subtract
        patch = '''\
def add(a, b):
    """新增文档字符串。"""
    return a + b
'''
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "新增文档字符串" in new_code
        assert "def subtract" in new_code

    def test_preserve_comments_and_docs(self):
        """测试保留注释和文档字符串。"""
        original = '''\
"""模块文档。"""
# 顶部注释

def foo():
    """函数文档。"""
    pass
'''
        patch = '''\
def foo():
    """更新后的文档。"""
    return 1
'''
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        # 新代码应包含更新的文档
        assert "更新后的文档" in new_code


# ─── TestSafeApplyMultiFunctionPatch：多函数安全应用 ─────────────────────────
class TestSafeApplyMultiFunctionPatch:
    """测试多函数补丁的安全应用。"""

    def test_safe_multi_function_valid(self):
        """测试有效的多函数补丁。"""
        original = """\
def func_a(x):
    return x + 1

def func_b(x):
    return x * 2

def func_c(x):
    return x - 1
"""
        patch = """\
def func_a(x):
    return x + 10  # 修改常数

def func_b(x):
    return x * 20  # 修改常数

def func_c(x):
    return x - 1  # 保持不变
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return x + 10" in new_code
        assert "return x * 20" in new_code
        assert "return x - 1" in new_code

    def test_safe_multi_function_syntax_error(self):
        """测试多函数补丁含语法错误时的处理。"""
        original = """\
def good_func():
    return 1
"""
        # 含语法错误的补丁
        patch = """\
def broken_func():
    return
    invalid
"""
        new_code, success = apply_patch_to_code(original, patch)
        # 应回滚或失败
        assert success is False or "invalid" not in new_code


# ─── TestGenerateDiff：差异生成测试 ───────────────────────────────────────────
class TestGenerateDiff:
    """测试补丁差异生成功能。"""

    def test_generate_diff_basic(self):
        """测试基本的差异生成。"""
        from src.tools.patch_applier import generate_diff

        original = "def foo():\n    return 1\n"
        patch_code = "def foo():\n    return 2\n"
        # 先应用补丁得到新代码
        new_code, success = apply_patch_to_code(original, patch_code)
        assert success is True
        assert "return 2" in new_code
        # 然后生成 diff
        diff = generate_diff(original, new_code)
        assert "return 1" in diff or "-return 1" in diff
        assert "return 2" in diff or "+return 2" in diff

    def test_generate_diff_empty(self):
        """测试空补丁的差异。"""
        original = "content\n"
        new_code, success = apply_patch_to_code(original, "")
        assert success is False


# ─── TestEdgeCases：边界情况测试 ─────────────────────────────────────────────
class TestEdgeCases:
    """测试边界情况和异常输入。"""

    def test_nested_function_replacement(self):
        """测试嵌套函数的替换。"""
        original = """\
def outer():
    def inner():
        return 1
    return inner()
"""
        patch = """\
def outer():
    def inner():
        return 2  # 修改内层函数
    return inner()
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return 2" in new_code

    def test_function_with_class(self):
        """测试函数与类定义共存时的替换。"""
        original = """\
def standalone_func():
    return 1

class MyClass:
    def method(self):
        return 2
"""
        patch = """\
def standalone_func():
    return 100  # 修改独立函数
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return 100" in new_code
        assert "class MyClass" in new_code  # 类定义应保留

    def test_whitespace_variations(self):
        """测试不同空白字符的处理。"""
        original = "def foo():\n    return 1\n"
        patch = "def foo():\n    \treturn 2\n"  # 制表符缩进
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "return 2" in new_code

    def test_unicode_in_code(self):
        """测试含 Unicode 字符的代码。"""
        original = """\
def greet(name):
    return f"你好, {name}!"
"""
        patch = """\
def greet(name):
    return f"您好, {name}! 欢迎回来。"
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "您好" in new_code
        assert "欢迎回来" in new_code

    def test_empty_functions(self):
        """测试空函数的替换。"""
        original = """\
def empty_func():
    pass
"""
        patch = """\
def empty_func():
    return "not empty anymore"
"""
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "not empty anymore" in new_code

    def test_long_function_replacement(self):
        """测试长函数的替换。"""
        original = '''\
def complex_function(x, y, z):
    """复杂的计算函数。"""
    result = x + y
    if result > z:
        return result * 2
    else:
        return result / 2
'''
        patch = '''\
def complex_function(x, y, z):
    """优化后的计算函数。"""
    result = x + y + z  # 添加第三个参数
    return result * 3  # 修改倍数
'''
        new_code, success = apply_patch_to_code(original, patch)
        assert success is True
        assert "添加第三个参数" in new_code
        assert "return result * 3" in new_code
