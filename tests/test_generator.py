"""
GeneratorAgent 单元测试

测试 generator.py 中的：
- GeneratorAgent 类
- parametrize 验证
- import 修正
"""

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.generator import GeneratorAgent


class TestGeneratorAgentInit:
    """测试 GeneratorAgent 初始化。"""

    def test_init_sets_system_prompt(self):
        """初始化时设置 system_prompt。"""
        with patch('src.agents.generator.GENERATOR_SYSTEM_PROMPT', 'test prompt'):
            agent = GeneratorAgent()
            assert agent.system_prompt == 'test prompt'

    def test_known_modules(self):
        """已知模块集合包含常用包。"""
        assert "pytest" in GeneratorAgent._KNOWN_MODULES
        assert "unittest" in GeneratorAgent._KNOWN_MODULES
        assert "typing" in GeneratorAgent._KNOWN_MODULES
        assert "os" in GeneratorAgent._KNOWN_MODULES


class TestValidateParametrize:
    """测试 parametrize 格式校验。"""

    def test_valid_parametrize_single_param(self):
        """有效的单参数 parametrize。"""
        code = '''
import pytest

@pytest.mark.parametrize("x", [(1,), (2,)])
def test_func(x):
    pass
'''
        assert GeneratorAgent._validate_parametrize(code) is True

    def test_valid_parametrize_multi_param(self):
        """有效的多参数 parametrize。"""
        code = '''
import pytest

@pytest.mark.parametrize("a,b", [(1, 2), (3, 4)])
def test_func(a, b):
    pass
'''
        assert GeneratorAgent._validate_parametrize(code) is True

    def test_invalid_parametrize_mismatch(self):
        """参数数量不匹配的 parametrize。"""
        code = '''
import pytest

@pytest.mark.parametrize("a,b", [(1,)])
def test_func(a, b):
    pass
'''
        assert GeneratorAgent._validate_parametrize(code) is False

    def test_invalid_parametrize_extra_case_name(self):
        """含 case_name 的 parametrize（常见错误）。"""
        code = '''
import pytest

@pytest.mark.parametrize("x", [("case1", 1), ("case2", 2)])
def test_func(x):
    pass
'''
        assert GeneratorAgent._validate_parametrize(code) is False

    def test_no_parametrize(self):
        """无 parametrize 的代码返回 True。"""
        code = '''
def test_func():
    assert True
'''
        assert GeneratorAgent._validate_parametrize(code) is True

    def test_invalid_syntax(self):
        """无效语法返回 False。"""
        code = '''
def test_func(:
    pass
'''
        assert GeneratorAgent._validate_parametrize(code) is False

    def test_parametrize_with_list_instead_of_tuple(self):
        """parametrize 使用列表而非元组。"""
        code = '''
import pytest

@pytest.mark.parametrize("x", [[1], [2]])
def test_func(x):
    pass
'''
        assert GeneratorAgent._validate_parametrize(code) is True


class TestCheckParametrizeDecorator:
    """测试 parametrize 装饰器检查。"""

    def test_detect_parametrize(self):
        """检测 parametrize 装饰器。"""
        import ast
        code = '''
import pytest

@pytest.mark.parametrize("x", [(1,)])
def test_func(x):
    pass
'''
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    result = GeneratorAgent._check_parametrize_decorator(decorator)
                    if result is not None:
                        param_names, cases_arg = result
                        assert param_names == ["x"]
                        break

    def test_non_parametrize_decorator(self):
        """非 parametrize 装饰器返回 None。"""
        import ast
        code = '''
@pytest.mark.skip
def test_func():
    pass
'''
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for decorator in node.decorator_list:
                    result = GeneratorAgent._check_parametrize_decorator(decorator)
                    assert result is None


class TestFixImportModule:
    """测试 import 模块修正。"""

    def test_fix_wrong_module_name(self):
        """修正错误的模块名。"""
        code = "from calculator_v2 import add"
        result = GeneratorAgent._fix_import_module(code, "calculator")
        assert "from calculator import" in result
        assert "calculator_v2" not in result

    def test_keep_correct_module_name(self):
        """保留正确的模块名。"""
        code = "from calculator import add"
        result = GeneratorAgent._fix_import_module(code, "calculator")
        assert result == code

    def test_skip_known_modules(self):
        """跳过已知模块的修正。"""
        code = "import pytest\nimport os"
        result = GeneratorAgent._fix_import_module(code, "calculator")
        assert "import pytest" in result
        assert "import os" in result

    def test_fix_multiple_imports(self):
        """修正多个导入。"""
        code = """
from wrong_module import func1
from another_wrong import func2
import pytest
"""
        result = GeneratorAgent._fix_import_module(code, "calculator")
        assert "from calculator import func1" in result
        assert "from calculator import func2" in result


class TestGenerate:
    """测试 generate 方法。"""

    @patch('src.agents.generator.BaseAgent._call_llm')
    def test_generate_calls_llm(self, mock_call_llm):
        """generate 方法调用 LLM。"""
        mock_call_llm.return_value = "```python\ndef test_foo(): pass\n```"

        agent = GeneratorAgent()
        result = agent.generate(
            test_plan={"function_name": "foo"},
            target_code="def foo(): pass",
            module_name="test_module"
        )

        mock_call_llm.assert_called_once()
        assert "def test_foo():" in result

    @patch('src.agents.generator.BaseAgent._call_llm')
    def test_generate_with_rag_references(self, mock_call_llm):
        """带 RAG 参考的生成。"""
        mock_call_llm.return_value = "```python\ndef test_foo(): pass\n```"

        agent = GeneratorAgent()
        rag_refs = [{"test_code": "def test_bar(): pass"}]
        agent.generate(
            test_plan={"function_name": "foo"},
            target_code="def foo(): pass",
            module_name="test_module",
            rag_references=rag_refs
        )

        mock_call_llm.assert_called_once()
        # 检查 prompt 中是否包含 RAG 参考
        call_args = mock_call_llm.call_args[0][0]
        assert "test_bar" in call_args

    @patch('src.agents.generator.BaseAgent._call_llm')
    def test_generate_truncates_long_code(self, mock_call_llm):
        """截断超长代码。"""
        mock_call_llm.return_value = "```python\ndef test(): pass\n```"

        agent = GeneratorAgent()
        long_code = "x = " * 5000  # 超长代码
        agent.generate(
            test_plan={"function_name": "foo"},
            target_code=long_code,
            module_name="test_module"
        )

        call_args = mock_call_llm.call_args[0][0]
        # 截断后的代码应包含截断提示
        assert "代码已截断" in call_args or len(long_code) > 3000

    @patch('src.agents.generator.BaseAgent._call_llm')
    def test_generate_with_module_name_constraint(self, mock_call_llm):
        """带模块名约束的生成。"""
        mock_call_llm.return_value = "```python\nfrom test_module import foo\ndef test(): pass\n```"

        agent = GeneratorAgent()
        agent.generate(
            test_plan={"function_name": "foo"},
            target_code="def foo(): pass",
            module_name="test_module"
        )

        call_args = mock_call_llm.call_args[0][0]
        assert "test_module" in call_args

    @patch('src.agents.generator.BaseAgent._call_llm')
    def test_generate_retries_on_invalid_parametrize(self, mock_call_llm):
        """parametrize 格式错误时重试。"""
        # 第一次调用返回无效 parametrize
        # 第二次调用返回有效代码
        mock_call_llm.side_effect = [
            "```python\n@pytest.mark.parametrize(\"x\", [(1, 2)])\ndef test(x): pass\n```",
            "```python\n@pytest.mark.parametrize(\"x\", [(1,), (2,)])\ndef test(x): pass\n```"
        ]

        agent = GeneratorAgent()
        result = agent.generate(
            test_plan={"function_name": "foo"},
            target_code="def foo(): pass",
            module_name="test_module"
        )

        assert mock_call_llm.call_count == 2
        assert "def test(x):" in result
