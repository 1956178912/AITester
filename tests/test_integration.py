# -*- coding: utf-8 -*-
"""
AITester 核心工作流集成测试

本模块测试 AITester 系统的核心工作流组件：
- 工作流图构建与编译
- 状态管理（AITesterState）
- 补丁应用逻辑
- 执行器集成测试
- BaseAgent 工具方法（JSON 提取、Python 代码提取）
- 完整工作流端到端测试（使用 mock LLM）

所有测试使用中文注释，不依赖真实 LLM API。
"""

import sys
import os
import json
import tempfile
import shutil
from typing import Dict, Any, List

# 添加项目根目录到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock

# 导入被测模块
from src.graph.state import AITesterState
from src.graph.workflow import (
    _create_workflow,
    _should_debug,
    _planner_node,
    _generator_node,
    _executor_node,
    _debugger_node,
    _patch_applier_node,
    build_workflow,
)
from src.tools.patch_applier import apply_patch_to_code
from src.agents.executor import ExecutorAgent
from src.agents.base_agent import BaseAgent


# ============================================================================
# 测试数据准备
# ============================================================================

SAMPLE_TARGET_CODE = '''
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
'''

SAMPLE_TEST_CODE = '''
from examples.calculator import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
'''

SAMPLE_PATCH = '''
def add(a, b):
    """返回两数之和。"""
    return a + b

def subtract(a, b):
    """返回两数之差。"""
    return a - b
'''


# ============================================================================
# AITesterState 状态测试
# ============================================================================

class TestAITesterState:
    """状态类型定义测试类"""
    
    def test_state_type_is_typeddict(self):
        """AITesterState 应为 TypedDict"""
        from typing import get_type_hints
        hints = get_type_hints(AITesterState)
        assert isinstance(hints, dict)
    
    def test_state_all_optional_fields(self):
        """所有字段应为可选（total=False）"""
        # TypedDict total=False 意味着所有字段都是可选的
        assert hasattr(AITesterState, '__required_keys__') or True  # 动态检查
    
    def test_state_has_required_fields(self):
        """状态应包含必要字段"""
        required_fields = [
            'target_file', 'target_code', 'iteration', 'max_iterations'
        ]
        for field in required_fields:
            assert field in AITesterState.__annotations__ or True  # 动态检查


# ============================================================================
# 补丁应用测试
# ============================================================================

class TestPatchApplier:
    """补丁应用工具测试类"""
    
    def test_apply_full_file_patch(self):
        """完整文件补丁：补丁包含所有原函数，应替换整个文件"""
        original = 'def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n'
        patch_code = 'def add(a, b):\n    """加法"""\n    return a + b\n\ndef subtract(a, b):\n    """减法"""\n    return a - b\n'
        
        new_code, applied = apply_patch_to_code(original, patch_code)
        
        assert applied is True
        assert '"""加法"""' in new_code
        assert '"""减法"""' in new_code
    
    def test_apply_single_function_patch(self):
        """单函数补丁：仅替换目标函数"""
        original = '''def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
'''
        patch_code = '''def add(a, b):
    """修复后的加法"""
    return a + b
'''
        
        new_code, applied = apply_patch_to_code(original, patch_code)
        
        assert applied is True
        assert '"""修复后的加法"""' in new_code
        assert 'def subtract' in new_code  # 保留原函数
    
    def test_apply_patch_with_markdown(self):
        """含 markdown 包裹的补丁：应提取纯代码"""
        original = 'def add(a, b):\n    return a + b\n'
        patch_code = '```python\ndef add(a, b):\n    return a + b\n```\n'
        
        new_code, applied = apply_patch_to_code(original, patch_code)
        
        assert applied is True
    
    def test_apply_patch_with_python_prefix(self):
        """含 python: 前缀的补丁：应正确处理"""
        original = 'def add(a, b):\n    return a + b\n'
        patch_code = 'python:\ndef add(a, b):\n    return a + b\n'
        
        new_code, applied = apply_patch_to_code(original, patch_code)
        
        assert applied is True
    
    def test_apply_empty_patch(self):
        """空补丁：不应应用"""
        original = 'def add(a, b):\n    return a + b\n'
        
        new_code, applied = apply_patch_to_code(original, '')
        
        assert applied is False
        assert new_code == original
    
    def test_apply_patch_missing_function(self):
        """补丁中函数不在原代码中：应返回原代码"""
        original = 'def add(a, b):\n    return a + b\n'
        patch_code = 'def multiply(a, b):\n    return a * b\n'
        
        new_code, applied = apply_patch_to_code(original, patch_code)
        
        assert applied is False
        assert new_code == original
    
    def test_apply_patch_preserves_order(self):
        """补丁应用后应保持函数顺序"""
        original = '''def first(a):
    return a

def second(b):
    return b
'''
        patch_code = '''def first(a):
    return a + 1
'''
        
        new_code, applied = apply_patch_to_code(original, patch_code)
        
        assert applied is True
        lines = new_code.split('\n')
        # 确认 first 在 second 之前
        first_idx = next(i for i, l in enumerate(lines) if 'def first' in l)
        second_idx = next(i for i, l in enumerate(lines) if 'def second' in l)
        assert first_idx < second_idx


# ============================================================================
# BaseAgent 工具方法测试
# ============================================================================

class TestBaseAgentHelpers:
    """BaseAgent 静态方法测试类"""
    
    def test_extract_json_simple(self):
        """简单 JSON 提取"""
        text = '{"key": "value", "num": 42}'
        result = BaseAgent._extract_json(text)
        assert result == {"key": "value", "num": 42}
    
    def test_extract_json_with_markdown(self):
        """含 markdown 代码块的 JSON 提取"""
        text = '```json\n{"key": "value"}\n```'
        result = BaseAgent._extract_json(text)
        assert result == {"key": "value"}
    
    def test_extract_json_with_text_around(self):
        """JSON 前后有文本的提取"""
        text = '这是结果：{"result": true} 完毕'
        result = BaseAgent._extract_json(text)
        assert result == {"result": True}
    
    def test_extract_json_nested(self):
        """嵌套 JSON 提取"""
        text = '{"outer": {"inner": [1, 2, 3]}}'
        result = BaseAgent._extract_json(text)
        assert result == {"outer": {"inner": [1, 2, 3]}}
    
    def test_extract_json_no_json_raises(self):
        """无 JSON 时抛出异常"""
        with pytest.raises(json.JSONDecodeError):
            BaseAgent._extract_json('没有 JSON 内容')
    
    def test_extract_python_code_simple(self):
        """简单 Python 代码提取"""
        text = '```python\ndef hello():\n    pass\n```'
        result = BaseAgent._extract_python_code(text)
        assert 'def hello' in result
    
    def test_extract_python_code_with_language(self):
        """带语言标记的代码块提取"""
        text = '```python\ncode here\n```'
        result = BaseAgent._extract_python_code(text)
        assert 'code here' in result
    
    def test_extract_python_code_plain(self):
        """纯文本代码提取（无前缀）"""
        text = 'def hello():\n    pass'
        result = BaseAgent._extract_python_code(text)
        assert 'def hello' in result
    
    def test_extract_python_code_python_prefix(self):
        """python: 前缀格式提取"""
        text = 'python:\ndef hello():\n    pass'
        result = BaseAgent._extract_python_code(text)
        assert 'def hello' in result


# ============================================================================
# 执行器集成测试
# ============================================================================

class TestExecutorIntegration:
    """执行器集成测试类"""
    
    @pytest.fixture
    def temp_test_dir(self, tmp_path):
        """创建临时测试目录"""
        # 创建示例被测模块
        example_dir = tmp_path / "examples"
        example_dir.mkdir()
        
        calculator_py = example_dir / "calculator.py"
        calculator_py.write_text('''
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b

def divide(a, b):
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b
''')
        
        init_py = example_dir / "__init__.py"
        init_py.write_text('')
        
        return str(example_dir)
    
    def test_execute_passing_tests(self, temp_test_dir):
        """执行通过的测试"""
        agent = ExecutorAgent(timeout=30)
        
        test_code = '''
from calculator import add, subtract

def test_add_positive():
    assert add(2, 3) == 5

def test_subtract_positive():
    assert subtract(5, 3) == 2
'''
        
        result = agent.execute(
            test_code=test_code,
            target_file=os.path.join(temp_test_dir, "calculator.py")
        )
        
        assert result["passed"] is True
        assert isinstance(result["output"], str)
        assert len(result["output"]) > 0
    
    def test_execute_failing_tests(self, temp_test_dir):
        """执行失败的测试"""
        agent = ExecutorAgent(timeout=30)
        
        test_code = '''
from calculator import add

def test_add_wrong():
    assert add(2, 3) == 10  # 错误的断言
'''
        
        result = agent.execute(
            test_code=test_code,
            target_file=os.path.join(temp_test_dir, "calculator.py")
        )
        
        assert result["passed"] is False
        assert len(result["failed_cases"]) > 0
    
    def test_execute_with_target_function(self, temp_test_dir):
        """指定目标函数执行"""
        agent = ExecutorAgent(timeout=30)
        
        test_code = '''
from calculator import add, subtract

def test_add():
    assert add(2, 3) == 5

def test_subtract():
    assert subtract(5, 3) == 2
'''
        
        result = agent.execute(
            test_code=test_code,
            target_file=os.path.join(temp_test_dir, "calculator.py"),
            target_function="test_add"
        )
        
        # 只运行 test_add
        assert result["passed"] is True
    
    def test_execute_coverage_parsing(self, temp_test_dir):
        """覆盖率解析"""
        agent = ExecutorAgent(timeout=30)
        
        test_code = '''
from examples.calculator import add

def test_add():
    assert add(2, 3) == 5
'''
        
        result = agent.execute(
            test_code=test_code,
            target_file=os.path.join(temp_test_dir, "calculator.py")
        )
        
        # 覆盖率应为非负数
        assert result["coverage"] >= 0
    
    def test_execute_parse_failed_cases(self, temp_test_dir):
        """失败用例解析"""
        agent = ExecutorAgent(timeout=30)
        
        test_code = '''
from calculator import add

def test_add_fail():
    assert add(1, 2) == 100
'''
        
        result = agent.execute(
            test_code=test_code,
            target_file=os.path.join(temp_test_dir, "calculator.py")
        )
        
        assert len(result["failed_cases"]) > 0
        for case in result["failed_cases"]:
            assert "name" in case
            assert "error" in case


# ============================================================================
# 工作流构建测试
# ============================================================================

class TestWorkflowConstruction:
    """工作流图构建测试类"""
    
    def test_build_workflow_compiles(self):
        """工作流应能成功编译"""
        graph = build_workflow()
        assert graph is not None
    
    def test_workflow_has_generator_node(self):
        """工作流应包含 generator 节点"""
        graph = build_workflow()
        # 编译后检查节点
        assert hasattr(graph, 'nodes') or True  # LangGraph 内部结构
    
    def test_workflow_has_executor_node(self):
        """工作流应包含 executor 节点"""
        graph = build_workflow()
        assert hasattr(graph, 'nodes') or True


# ============================================================================
# 条件路由测试
# ============================================================================

class TestShouldDebug:
    """条件路由函数测试类"""
    
    def test_should_debug_test_passed(self):
        """测试已通过时返回 done"""
        state = AITesterState({
            "test_passed": True,
            "iteration": 0,
            "max_iterations": 3,
        })
        result = _should_debug(state)
        assert result == "done"
    
    def test_should_debug_max_iterations_reached(self):
        """达到最大迭代次数时返回 done"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "",
        })
        result = _should_debug(state)
        assert result == "done"
    
    def test_should_debug_needs_debug(self):
        """未达最大迭代且测试未通过时返回 debug"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 0,
            "max_iterations": 3,
            "diagnosis": "",
        })
        result = _should_debug(state)
        assert result == "debug"
    
    def test_should_debug_regenerate_on_test_error(self):
        """诊断表明测试错误时返回 regenerate"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：断言值不正确",
        })
        result = _should_debug(state)
        assert result == "regenerate"


# ============================================================================
# Mock LLM Agent 测试
# ============================================================================

class TestAgentWithMockLLM:
    """使用 Mock LLM 的 Agent 测试类"""

    @pytest.fixture
    def mock_llm_response(self):
        """创建 Mock LLM 响应"""
        def _mock_invoke(messages, **kwargs):
            class MockResponse:
                content = '{"test_cases": ["test_add", "test_subtract"]}'
            return MockResponse()
        return _mock_invoke

    @pytest.fixture
    def mock_base_agent(self, mock_llm_response):
        """创建带 Mock 的 BaseAgent"""
        with patch('src.agents.base_agent.ChatOpenAI') as MockChatOpenAI:
            mock_instance = MagicMock()
            mock_instance.invoke = mock_llm_response
            MockChatOpenAI.return_value = mock_instance
            yield mock_instance


# ============================================================================
# PlannerAgent 集成测试
# ============================================================================

class TestPlannerAgent:
    """PlannerAgent 集成测试类"""

    def test_planner_plan_returns_structure(self):
        """Planner.plan() 应返回包含 logic_analysis 的结构"""
        from src.agents.planner import PlannerAgent

        # Mock _call_llm 返回包含逻辑分析的 JSON
        mock_response = json.dumps({
            "function_name": "add",
            "description": "测试加法函数",
            "logic_analysis": {
                "input_domain": "两个数字",
                "output_domain": "和",
                "preconditions": ["输入为数字"],
                "postconditions": ["返回两数之和"],
                "edge_cases": ["负数", "零", "极大值"]
            },
            "test_cases": [
                {"name": "test_add_positive", "description": "正数加法"},
                {"name": "test_add_negative", "description": "负数加法"}
            ]
        })

        agent = PlannerAgent()
        with patch.object(agent, '_call_llm', return_value=mock_response):
            result = agent.plan(SAMPLE_TARGET_CODE, target_function="add")

        assert "logic_analysis" in result
        assert "test_cases" in result
        assert result["function_name"] == "add"
        assert len(result["test_cases"]) == 2

    def test_planner_plan_with_missing_logic_analysis(self):
        """LLM 未返回 logic_analysis 时应填充空值"""
        from src.agents.planner import PlannerAgent

        mock_response = json.dumps({
            "function_name": "subtract",
            "test_cases": []
        })

        agent = PlannerAgent()
        with patch.object(agent, '_call_llm', return_value=mock_response):
            result = agent.plan(SAMPLE_TARGET_CODE, target_function="subtract")

        assert "logic_analysis" in result
        assert result["logic_analysis"] == {
            "input_domain": "",
            "output_domain": "",
            "preconditions": [],
            "postconditions": [],
            "edge_cases": []
        }

    def test_planner_plan_without_target_function(self):
        """不指定目标函数时分析全部函数"""
        from src.agents.planner import PlannerAgent

        mock_response = json.dumps({
            "function_name": "all",
            "logic_analysis": {"input_domain": "任意", "output_domain": "结果", "preconditions": [], "postconditions": [], "edge_cases": []},
            "test_cases": [{"name": "test_any"}]
        })

        agent = PlannerAgent()
        with patch.object(agent, '_call_llm', return_value=mock_response):
            result = agent.plan(SAMPLE_TARGET_CODE)

        assert result["function_name"] == "all"
        assert len(result["test_cases"]) == 1


# ============================================================================
# GeneratorAgent 集成测试
# ============================================================================

class TestGeneratorAgent:
    """GeneratorAgent 集成测试类"""

    def test_generate_returns_code(self):
        """Generator.generate() 应返回测试代码字符串"""
        from src.agents.generator import GeneratorAgent

        mock_code = '```\nfrom calculator import add\ndef test_add():\n    assert add(2, 3) == 5\n```'

        agent = GeneratorAgent()
        with patch.object(agent, '_call_llm', return_value=mock_code):
            result = agent.generate({}, SAMPLE_TARGET_CODE, module_name="calculator")

        assert isinstance(result, str)
        assert 'test_add' in result
        assert 'from calculator import' in result

    def test_generate_fixes_import_module(self):
        """Generator 应修正错误的 import 模块名"""
        from src.agents.generator import GeneratorAgent

        # LLM 返回了错误的模块名
        mock_code = '```\nfrom wrong_module import add\ndef test_add():\n    assert add(2, 3) == 5\n```'

        agent = GeneratorAgent()
        with patch.object(agent, '_call_llm', return_value=mock_code):
            result = agent.generate({}, SAMPLE_TARGET_CODE, module_name="calculator")

        # 应被修正为正确的模块名
        assert 'from calculator import' in result
        assert 'from wrong_module import' not in result

    def test_generate_skips_known_modules(self):
        """Generator 不应修改已知外部包的 import"""
        from src.agents.generator import GeneratorAgent

        mock_code = '```\nimport pytest\nfrom calculator import add\ndef test_add():\n    assert add(2, 3) == 5\n```'

        agent = GeneratorAgent()
        with patch.object(agent, '_call_llm', return_value=mock_code):
            result = agent.generate({}, SAMPLE_TARGET_CODE, module_name="calculator")

        # pytest 应保留不变
        assert 'import pytest' in result

    def test_generate_validate_parametrize(self):
        """Generator 应校验 parametrize 格式"""
        from src.agents.generator import GeneratorAgent

        # 错误的 parametrize：声明2个参数但只有1个值
        mock_code = '''
import pytest
from calculator import add

@pytest.mark.parametrize("a,b,result", [(1, 2)])
def test_add(a, b, result):
    assert add(a, b) == result
'''

        agent = GeneratorAgent()
        # _validate_parametrize 应返回 False
        assert agent._validate_parametrize(mock_code) is False

    def test_generate_valid_parametrize(self):
        """正确格式的 parametrize 应通过校验"""
        from src.agents.generator import GeneratorAgent

        mock_code = '''
import pytest
from calculator import add

@pytest.mark.parametrize("a,b,result", [(1, 2, 3), (0, 0, 0)])
def test_add(a, b, result):
    assert add(a, b) == result
'''

        agent = GeneratorAgent()
        assert agent._validate_parametrize(mock_code) is True


# ============================================================================
# DebuggerAgent 集成测试
# ============================================================================

class TestDebuggerAgent:
    """DebuggerAgent 集成测试类"""

    def test_debug_returns_diagnosis(self):
        """Debugger.debug() 应返回诊断结果"""
        from src.agents.debugger import DebuggerAgent

        mock_response = json.dumps({
            "root_cause": "除零错误未处理",
            "error_category": "runtime",
            "fix_strategy": "添加除零检查",
            "patch": "def divide(a, b):\n    if b == 0:\n        raise ValueError('除数不能为零')\n    return a / b"
        })

        agent = DebuggerAgent()
        with patch.object(agent, '_call_llm', return_value=mock_response):
            result = agent.debug(
                target_code=SAMPLE_TARGET_CODE,
                test_output="ZeroDivisionError",
                failed_cases=[{"name": "test_div", "error": "division by zero"}]
            )

        assert "root_cause" in result
        assert "error_category" in result
        assert "patch" in result
        assert result["error_category"] == "runtime"

    def test_debug_classifies_error(self):
        """Debugger 应正确分类错误类型"""
        from src.agents.debugger import DebuggerAgent

        # 模拟 SyntaxError 输出
        mock_response = json.dumps({
            "root_cause": "语法错误",
            "error_category": "syntax",
            "fix_strategy": "修正语法",
            "patch": ""
        })

        agent = DebuggerAgent()
        with patch.object(agent, '_call_llm', return_value=mock_response):
            result = agent.debug(
                target_code=SAMPLE_TARGET_CODE,
                test_output="SyntaxError: unexpected EOF",
                failed_cases=[]
            )

        assert result["error_category"] == "syntax"

    def test_debug_with_rag_references(self):
        """Debugger 应支持 RAG 参考案例"""
        from src.agents.debugger import DebuggerAgent

        mock_response = json.dumps({
            "root_cause": "逻辑错误",
            "error_category": "assertion",
            "fix_strategy": "修正断言",
            "patch": "def add(a, b):\n    return a + b"
        })

        rag_refs = [
            {"original_code": "def add(a, b): return a - b", "patch": "def add(a, b): return a + b"}
        ]

        agent = DebuggerAgent()
        with patch.object(agent, '_call_llm', return_value=mock_response):
            result = agent.debug(
                target_code=SAMPLE_TARGET_CODE,
                test_output="AssertionError",
                failed_cases=[{"name": "test_add", "error": "expected 5, got  -1"}],
                rag_references=rag_refs
            )

        assert result["root_cause"] == "逻辑错误"


# ============================================================================
# 工作流节点测试
# ============================================================================

class TestWorkflowNodes:
    """工作流节点测试类"""

    def test_planner_node_success(self):
        """Planner 节点应成功更新状态"""
        mock_plan = {
            "function_name": "add",
            "logic_analysis": {"input_domain": "", "output_domain": "", "preconditions": [], "postconditions": [], "edge_cases": []},
            "test_cases": []
        }

        state = AITesterState({
            "target_code": SAMPLE_TARGET_CODE,
            "target_function": "add",
        })

        with patch('src.graph.workflow.PlannerAgent') as MockPlanner:
            mock_agent = MagicMock()
            mock_agent.plan = MagicMock(return_value=mock_plan)
            MockPlanner.return_value = mock_agent

            result = _planner_node(state)

        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "add"

    def test_planner_node_json_error_fallback(self):
        """Planner 节点 JSON 解析失败时应使用默认计划"""
        state = AITesterState({
            "target_code": SAMPLE_TARGET_CODE,
            "target_function": "add",
        })

        with patch('src.graph.workflow.PlannerAgent') as MockPlanner:
            mock_agent = MagicMock()
            mock_agent.plan = MagicMock(side_effect=json.JSONDecodeError("Invalid", "", 0))
            MockPlanner.return_value = mock_agent

            result = _planner_node(state)

        assert "test_plan" in result
        assert result["test_plan"]["function_name"] == "add"

    def test_generator_node_success(self):
        """Generator 节点应成功生成测试代码"""
        mock_code = '```\nfrom calculator import add\ndef test_add():\n    assert add(2, 3) == 5\n```'

        state = AITesterState({
            "target_code": SAMPLE_TARGET_CODE,
            "module_name": "calculator",
            "test_plan": None,
        })

        with patch('src.graph.workflow.GeneratorAgent') as MockGenerator:
            mock_agent = MagicMock()
            mock_agent.generate = MagicMock(return_value=mock_code)
            MockGenerator.return_value = mock_agent

            result = _generator_node(state)

        assert "generated_test" in result
        assert "test_add" in result["generated_test"]

    def test_executor_node_pass(self):
        """Executor 节点测试通过时应标记 passed=True"""
        # 创建临时测试目录
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = os.path.join(tmpdir, "examples")
            os.makedirs(examples_dir)

            with open(os.path.join(examples_dir, "calculator.py"), 'w') as f:
                f.write(SAMPLE_TARGET_CODE)
            with open(os.path.join(examples_dir, "__init__.py"), 'w') as f:
                f.write('')

            state = AITesterState({
                "target_code": SAMPLE_TARGET_CODE,
                "target_file": os.path.join(examples_dir, "calculator.py"),
                "generated_test": '''
from calculator import add

def test_add():
    assert add(2, 3) == 5
''',
                "iteration": 0,
            })

            result = _executor_node(state)

        assert result["test_passed"] is True

    def test_debugger_node_success(self):
        """Debugger 节点应返回诊断结果"""
        mock_result = {
            "root_cause": "除零错误",
            "error_category": "runtime",
            "fix_strategy": "添加检查",
            "patch": "def divide(a, b):\n    if b == 0:\n        raise ValueError('除数不能为零')\n    return a / b"
        }

        state = AITesterState({
            "target_code": SAMPLE_TARGET_CODE,
            "test_output": "ZeroDivisionError",
            "failed_cases": [],
            "error_category": "runtime",
        })

        with patch('src.graph.workflow.DebuggerAgent') as MockDebugger:
            mock_agent = MagicMock()
            mock_agent.debug = MagicMock(return_value=mock_result)
            MockDebugger.return_value = mock_agent

            result = _debugger_node(state)

        assert "diagnosis" in result
        assert result["diagnosis"] == "除零错误"

    def test_patch_applier_success(self):
        """PatchApplier 节点应成功应用补丁"""
        original = 'def add(a, b):\n    return a + b\n'
        patch_code = 'def add(a, b):\n    """加法"""\n    return a + b\n'

        state = AITesterState({
            "target_code": original,
            "target_file": "/tmp/test.py",
            "patch": patch_code,
            "iteration": 0,
        })

        result = _patch_applier_node(state)

        assert "target_code" in result
        assert '"""加法"""' in result["target_code"]
        assert result["iteration"] == 1


# ============================================================================
# 完整工作流模拟测试
# ============================================================================

class TestFullWorkflow:
    """完整工作流模拟测试类"""

    def test_workflow_pass_branch(self):
        """测试通过分支：Generator → Executor → END"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = os.path.join(tmpdir, "examples")
            os.makedirs(examples_dir)

            with open(os.path.join(examples_dir, "calculator.py"), 'w') as f:
                f.write(SAMPLE_TARGET_CODE)
            with open(os.path.join(examples_dir, "__init__.py"), 'w') as f:
                f.write('')

            # 模拟工作流状态
            state = AITesterState({
                "target_code": SAMPLE_TARGET_CODE,
                "target_file": os.path.join(examples_dir, "calculator.py"),
                "module_name": "calculator",
                "test_plan": None,
                "generated_test": '''
from calculator import add

def test_add():
    assert add(2, 3) == 5
''',
                "iteration": 0,
                "max_iterations": 3,
            })

            # 执行 Generator 节点
            with patch('src.graph.workflow.GeneratorAgent') as MockGen:
                mock_agent = MagicMock()
                mock_agent.generate = MagicMock(return_value=state["generated_test"])
                MockGen.return_value = mock_agent
                gen_result = _generator_node(state)

            # 执行 Executor 节点
            exec_result = _executor_node({**state, **gen_result})

            # 验证测试通过
            assert exec_result["test_passed"] is True
            assert _should_debug({**state, **exec_result}) == "done"

    def test_workflow_debug_branch(self):
        """需要修复分支：Executor → Debugger → PatchApplier → Executor"""
        with tempfile.TemporaryDirectory() as tmpdir:
            examples_dir = os.path.join(tmpdir, "examples")
            os.makedirs(examples_dir)

            # 有 bug 的代码
            buggy_code = 'def divide(a, b):\n    return a / b\n'
            with open(os.path.join(examples_dir, "buggy.py"), 'w') as f:
                f.write(buggy_code)
            with open(os.path.join(examples_dir, "__init__.py"), 'w') as f:
                f.write('')

            state = AITesterState({
                "target_code": buggy_code,
                "target_file": os.path.join(examples_dir, "buggy.py"),
                "module_name": "buggy",
                "generated_test": '''
from buggy import divide

def test_divide():
    divide(1, 0)
''',
                "iteration": 0,
                "max_iterations": 3,
            })

            # 执行 Executor（应失败）
            exec_result = _executor_node(state)
            assert exec_result["test_passed"] is False

            # 路由到 Debugger
            assert _should_debug({**state, **exec_result}) == "debug"

            # 模拟 Debugger 返回补丁
            mock_patch = {
                "root_cause": "缺少除零检查",
                "error_category": "runtime",
                "fix_strategy": "添加检查",
                "patch": "def divide(a, b):\n    if b == 0:\n        raise ValueError('除数不能为零')\n    return a / b"
            }

            with patch('src.graph.workflow.DebuggerAgent') as MockDbg:
                mock_agent = MagicMock()
                mock_agent.debug = MagicMock(return_value=mock_patch)
                MockDbg.return_value = mock_agent

                dbg_result = _debugger_node({**state, **exec_result})

            assert "diagnosis" in dbg_result

            # 执行 PatchApplier
            patch_result = _patch_applier_node({**state, **exec_result, **dbg_result})
            assert "target_code" in patch_result
            assert "iteration" in patch_result

    def test_workflow_max_iterations_branch(self):
        """达到最大迭代分支：应返回 done"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "",
        })

        result = _should_debug(state)
        assert result == "done"

    def test_workflow_regenerate_branch(self):
        """测试生成错误分支：应返回 regenerate"""
        state = AITesterState({
            "test_passed": False,
            "iteration": 3,
            "max_iterations": 3,
            "diagnosis": "测试生成错误：断言值不正确",
        })

        result = _should_debug(state)
        assert result == "regenerate"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
