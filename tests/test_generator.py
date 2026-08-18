"""
单元测试：测试 GeneratorAgent。

覆盖范围：
    - _validate_parametrize：正常、参数不匹配、语法错误
    - _fix_import_module：修正错误模块名、保留已知外部包
    - generate()：mock LLM 调用
"""

from unittest.mock import patch

from src.agents.generator import GeneratorAgent


# ─── TestValidateParametrize：parametrize 格式校验 ────────────────────────────
class TestValidateParametrize:
    """测试 GeneratorAgent._validate_parametrize 静态方法。"""

    def test_valid_parametrize_single_param(self):
        """单参数 parametrize 正常。"""
        code = """
import pytest

@pytest.mark.parametrize("x", [1, 2, 3])
def test_foo(x):
    assert x > 0
"""
        assert GeneratorAgent._validate_parametrize(code) is True

    def test_valid_parametrize_two_params(self):
        """双参数 parametrize 正常。"""
        code = """
import pytest

@pytest.mark.parametrize("a,b", [(1, 2), (3, 4)])
def test_add(a, b):
    assert a + b > 0
"""
        assert GeneratorAgent._validate_parametrize(code) is True

    def test_parametrize_param_mismatch(self):
        """参数数量不匹配时返回 False。"""
        code = """
import pytest

@pytest.mark.parametrize("a,b", [(1,)])
def test_add(a, b):
    pass
"""
        assert GeneratorAgent._validate_parametrize(code) is False

    def test_parametrize_missing_cases_arg(self):
        """parametrize 缺少第二参数时跳过（不报错）。"""
        code = """
import pytest

@pytest.mark.parametrize("x")
def test_foo(x):
    pass
"""
        # 缺少 cases 参数，不应触发参数不匹配检查
        result = GeneratorAgent._validate_parametrize(code)
        # 因为没有第二个 arg，代码跳过校验，返回 True（语法合法即可）
        assert result is True

    def test_syntax_error_returns_false(self):
        """代码有语法错误时返回 False。"""
        code = "def foo(:\n    pass"
        assert GeneratorAgent._validate_parametrize(code) is False

    def test_no_parametrize_decorator(self):
        """无 parametrize 装饰器的代码视为合法。"""
        code = """
def test_simple():
    assert 1 == 1
"""
        assert GeneratorAgent._validate_parametrize(code) is True


# ─── TestFixImportModule：import 模块名修正 ────────────────────────────────────
class TestFixImportModule:
    """测试 GeneratorAgent._fix_import_module 静态方法。"""

    def test_fix_wrong_module_name(self):
        """错误的模块名被修正为期望模块名。"""
        code = "from wrong_module import foo"
        result = GeneratorAgent._fix_import_module(code, "target_mod")
        assert "from target_mod import foo" in result
        assert "wrong_module" not in result

    def test_keep_known_external_packages(self):
        """已知外部包（pytest、unittest 等）不被替换。"""
        code = "import pytest\nfrom unittest import TestCase\nimport json"
        result = GeneratorAgent._fix_import_module(code, "target_mod")
        assert "import pytest" in result
        assert "from unittest" in result
        assert "import json" in result

    def test_already_correct_module_unchanged(self):
        """模块名已正确时不做修改。"""
        code = "from target_mod import foo"
        result = GeneratorAgent._fix_import_module(code, "target_mod")
        assert result == code

    def test_multiple_wrong_modules_fixed(self):
        """多个错误模块名全部被修正。"""
        code = "from mod_a import x\nfrom mod_b import y"
        result = GeneratorAgent._fix_import_module(code, "target_mod")
        assert "from target_mod import x" in result
        assert "from target_mod import y" in result


# ─── TestGeneratorAgent：生成器智能体 ─────────────────────────────────────────
class TestGeneratorAgent:
    """测试 GeneratorAgent.generate() 方法。"""

    def _make_agent(self):
        """工厂方法：创建 GeneratorAgent 实例。"""
        return GeneratorAgent()

    @patch.object(GeneratorAgent, "_call_llm")
    @patch.object(GeneratorAgent, "_extract_python_code")
    def test_generate_with_mock_llm(self, mock_extract, mock_llm):
        """正常流程：mock LLM 返回代码，generate 返回修正后的代码。"""
        mock_llm.return_value = "```python\ndef test_foo(): pass\n```"
        mock_extract.return_value = "def test_foo(): pass"
        agent = self._make_agent()
        test_plan = {"function_name": "foo", "test_cases": []}
        result = agent.generate(test_plan, "def foo(x): return x", module_name="my_mod")
        assert "def test_foo(): pass" in result
        mock_llm.assert_called_once()

    @patch.object(GeneratorAgent, "_call_llm")
    @patch.object(GeneratorAgent, "_extract_python_code")
    def test_generate_with_rag_references(self, mock_extract, mock_llm):
        """RAG 参考案例被注入 prompt。"""
        mock_llm.return_value = "```python\ndef test_bar(): pass\n```"
        mock_extract.return_value = "def test_bar(): pass"
        agent = self._make_agent()
        test_plan = {"function_name": "bar", "test_cases": []}
        rag = [{"test_code": "参考代码1"}, {"test_code": "参考代码2"}]
        agent.generate(test_plan, "def bar(): pass", rag_references=rag)
        # 验证 LLM 被调用（prompt 中含 RAG 内容）
        call_args = mock_llm.call_args[0][0]
        assert "参考代码1" in call_args

    @patch.object(GeneratorAgent, "_call_llm")
    @patch.object(GeneratorAgent, "_extract_python_code")
    def test_generate_parametrize_retry(self, mock_extract, mock_llm):
        """parametrize 校验失败时触发重试。"""
        # 第一次返回非法 parametrize，第二次返回合法代码
        bad_code = '@pytest.mark.parametrize("a,b")\n@pytest.mark.parametrize("a,b", [(1,)])\ndef test_x(a, b): pass'
        good_code = "def test_y(): assert True"
        mock_llm.side_effect = [bad_code, good_code]
        # _extract_python_code 第一次返回 bad，第二次返回 good
        mock_extract.side_effect = [bad_code, good_code]
        agent = self._make_agent()
        test_plan = {"function_name": "x", "test_cases": []}
        agent.generate(test_plan, "def x(): pass", module_name="m")
        # 第二次调用 LLM 应被触发（重试）
        assert mock_llm.call_count == 2
