"""
src/tools/code_context.py 单元测试（P0：AST 智能截取）。

覆盖：
- 焦点函数 + 直接依赖的保留
- import 语句保留
- 超预算时按优先级丢弃无关函数
- 超长函数体首尾截断
- 无法解析源码时的原样返回
- 与 BaseAgent.truncate_code 的集成
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.code_context import extract_focused_code


class TestExtractFocusedCode:
    """extract_focused_code 核心行为。"""

    def test_focus_function_kept_with_deps(self):
        """焦点函数及其直接依赖被保留，无关函数被丢弃。"""
        source = (
            "import os\nimport math\n"
            "def _helper(x):\n"
            "    return x * 2\n"
            "def divide(a, b):\n"
            "    if b == 0:\n"
            "        raise ValueError\n"
            "    return _helper(a) / _helper(b)\n"
            "def unrelated_1():\n"
            "    pass\n"
            "def unrelated_2():\n"
            "    pass\n"
        )
        result = extract_focused_code(source, focus_function="divide", max_chars=3000)
        assert "def divide" in result
        assert "def _helper" in result
        assert "def unrelated_1" not in result
        assert "def unrelated_2" not in result
        # import 保留
        assert "import os" in result
        assert "import math" in result

    def test_no_focus_keeps_all_functions(self):
        """无焦点时保留全部顶层函数。"""
        source = "def f1():\n    pass\n\ndef f2():\n    pass\n"
        result = extract_focused_code(source, focus_function=None, max_chars=3000)
        assert "def f1" in result
        assert "def f2" in result

    def test_focus_function_over_budget_drops_unrelated(self):
        """超预算时优先丢弃与焦点无关的函数。"""
        # 构造大量无关函数使整体超出预算
        filler = "".join(f"def filler_{i}():\n    x = '{'x' * 40}'\n" for i in range(30))
        source = (
            "import os\n"
            "def target():\n"
            "    return 1\n"
            + filler
        )
        result = extract_focused_code(source, focus_function="target", max_chars=500)
        assert "def target" in result
        assert "def filler_5" not in result
        assert "import os" in result
        assert len(result) <= 500

    def test_invalid_python_returns_source_unchanged(self):
        """无法解析的源码原样返回（交由字符级截断兜底）。"""
        bad = "def broken(:\n"
        result = extract_focused_code(bad, focus_function="broken", max_chars=100)
        assert result == bad

    def test_empty_source(self):
        """空源码原样返回。"""
        assert extract_focused_code("", focus_function="x", max_chars=100) == ""
        assert extract_focused_code("   ", focus_function="x", max_chars=100) == "   "

    def test_module_without_functions(self):
        """无函数模块返回原文（交字符级截断控制长度）。"""
        source = "X = 1\nY = 2\n"
        assert extract_focused_code(source, focus_function="nope", max_chars=100) == source

    def test_missing_focus_name_falls_back_to_all_functions(self):
        """焦点名不存在时退化为保留全部顶层函数。"""
        source = "def a():\n    pass\ndef b():\n    pass\n"
        result = extract_focused_code(source, focus_function="not_there", max_chars=3000)
        assert "def a" in result and "def b" in result


class TestLongBodyTruncation:
    """超长函数体的首尾截断。"""

    def test_long_function_body_trimmed(self):
        """超长焦点函数体被首尾截断，保留签名与省略标记。"""
        # 单个焦点函数体超预算：50 行，预算 200 字符
        body = "\n".join(f"    v{i} = {i}" for i in range(50))
        source = "import os\n\ndef big():\n" + body + "\n"
        result = extract_focused_code(source, focus_function="big", max_chars=300)
        assert "def big" in result
        assert "# ... (truncated)" in result
        # 首行保留
        assert "v0 = 0" in result
        # 尾部保留
        assert "v49 = 49" in result
        # 中间行被丢弃
        assert "v25 = 25" not in result
        assert len(result) <= 300

    def test_class_method_focus(self):
        """类体内方法可作为焦点。"""
        source = (
            "class Calc:\n"
            "    def add(self, a, b):\n"
            "        return a + b\n"
            "    def sub(self, a, b):\n"
            "        return a - b\n"
        )
        result = extract_focused_code(source, focus_function="add", max_chars=3000)
        assert "def add" in result
        assert "def sub" not in result


class TestTruncateCodeIntegration:
    """BaseAgent.truncate_code 与 AST 截取的集成。"""

    def test_large_file_focus_function_kept(self):
        """大文件（>3000 字符）按焦点截取，目标函数不丢失。"""
        from src.agents.base_agent import BaseAgent

        filler = "".join(f"def noise_{i}():\n    return {'x' * 60}\n" for i in range(40))
        source = "import os\n" + filler + "def divide(a, b):\n    if b == 0:\n        raise ValueError\n    return a / b\n"
        assert len(source) > 3000
        result = BaseAgent.truncate_code(source, focus_function="divide")
        assert len(result) <= 3000
        assert "def divide" in result
        # 无关噪声函数被丢弃（大文件适配 SWE-bench 的关键断言）
        assert "def noise_5" not in result
        assert "import os" in result

    def test_char_level_fallback_still_markers(self):
        """无函数体长文本仍走字符级截断并带提示标记。"""
        from src.agents.base_agent import BaseAgent

        code = "# " + "x" * 5000  # 纯注释，无函数
        result = BaseAgent.truncate_code(code, max_chars=500)
        assert len(result) <= 500
        assert "[代码已截断" in result
