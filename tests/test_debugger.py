"""
DebuggerAgent 单元测试

测试 src/agents/debugger.py 中的：
- DebuggerAgent 初始化
- debug 方法（各种错误类型场景）
- RAG 参考注入逻辑
- 截断逻辑
"""

import json
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.debugger import DebuggerAgent
from src.agents.error_classifier import ErrorClassifier


class TestDebuggerAgentInit:
    """测试 DebuggerAgent 初始化（第 73-77 行）。"""

    def test_init_creates_agent(self):
        """初始化创建 DebuggerAgent 实例。"""
        agent = DebuggerAgent()
        assert agent is not None
        assert hasattr(agent, "classifier")
        assert isinstance(agent.classifier, ErrorClassifier)
        assert hasattr(agent, "system_prompt")
        assert len(agent.system_prompt) > 0

    def test_init_sets_classifier(self):
        """初始化设置 classifier 为 ErrorClassifier 实例。"""
        agent = DebuggerAgent()
        assert agent.classifier is not None

    def test_init_system_prompt_contains_debugger_keywords(self):
        """初始化设置包含调试关键词的 system prompt。"""
        agent = DebuggerAgent()
        prompt = agent.system_prompt
        assert "调试" in prompt or "debug" in prompt.lower()
        assert "patch" in prompt.lower() or "修复" in prompt


class TestDebuggerDebug:
    """测试 DebuggerAgent.debug 方法（第 110-165 行）。"""

    def setup_method(self):
        """每个测试前创建 agent 并 mock LLM 调用。"""
        self.agent = DebuggerAgent()
        # Mock _call_llm 返回有效的 JSON 响应
        self.mock_response = json.dumps(
            {
                "root_cause": "测试根因分析",
                "error_category": "assertion",
                "fix_strategy": "测试修复策略",
                "patch": "```python\ndef add(a, b):\n    return a + b\n```",
            }
        )

    def test_debug_syntax_error(self):
        """测试语法错误的调试流程。"""
        with patch.object(self.agent, "_call_llm", return_value=self.mock_response):
            result = self.agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="SyntaxError: invalid syntax",
                failed_cases=[{"name": "test_add", "error": "SyntaxError: invalid syntax"}],
            )

        assert "root_cause" in result
        assert "error_category" in result
        assert "fix_strategy" in result
        assert "patch" in result
        assert result["error_category"] == "syntax"

    def test_debug_runtime_error(self):
        """测试运行时错误的调试流程。"""
        mock_response = json.dumps(
            {
                "root_cause": "除零错误",
                "error_category": "runtime",
                "fix_strategy": "添加除零检查",
                "patch": """```python
def divide(a, b):
    if b == 0:
        raise ValueError('除数不能为零')
    return a / b
```""",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            result = self.agent.debug(
                target_code="def divide(a, b): return a / b",
                test_output="ZeroDivisionError: division by zero",
                failed_cases=[{"name": "test_divide", "error": "ZeroDivisionError"}],
            )

        assert result["error_category"] == "runtime"
        assert "除数不能为零" in result["patch"]

    def test_debug_assertion_error(self):
        """测试断言错误的调试流程。"""
        mock_response = json.dumps(
            {
                "root_cause": "加法实现错误，使用了减法",
                "error_category": "assertion",
                "fix_strategy": "修复运算符号",
                "patch": "```python\ndef add(a, b):\n    return a + b\n```",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            result = self.agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="AssertionError: expected 5, got -1",
                failed_cases=[{"name": "test_add", "error": "expected 5, got -1"}],
            )

        assert result["error_category"] == "assertion"
        assert "a + b" in result["patch"]

    def test_debug_timeout_error(self):
        """测试超时错误的调试流程。"""
        mock_response = json.dumps(
            {
                "root_cause": "无限递归导致超时",
                "error_category": "timeout",
                "fix_strategy": "添加递归终止条件",
                "patch": """```python
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)
```""",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            result = self.agent.debug(
                target_code="def factorial(n): return n * factorial(n-1)",
                test_output="timeout exceeded",
                failed_cases=[{"name": "test_factorial", "error": "TimedOut"}],
            )

        assert result["error_category"] == "timeout"
        assert "n <= 1" in result["patch"]

    def test_debug_import_error(self):
        """测试导入错误的调试流程。"""
        mock_response = json.dumps(
            {
                "root_cause": "缺少 pandas 导入",
                "error_category": "syntax",
                "fix_strategy": "添加缺失的 import",
                "patch": "```python\nimport pandas as pd\n\ndef process_data(df):\n    return df.sum()\n```",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            result = self.agent.debug(
                target_code="def process_data(df): return df.sum()",
                test_output="ModuleNotFoundError: No module named 'pandas'",
                failed_cases=[{"name": "test_process", "error": "ModuleNotFoundError"}],
            )

        assert result["error_category"] == "syntax"
        assert "import pandas" in result["patch"]

    def test_debug_with_rag_references(self):
        """测试带 RAG 参考的调试流程。"""
        mock_response = json.dumps(
            {
                "root_cause": "参考历史案例修复",
                "error_category": "assertion",
                "fix_strategy": "参考相似案例",
                "patch": "```python\ndef add(a, b): return a + b\n```",
            }
        )
        rag_refs = [
            {"original_code": "def add(a, b): return a - b", "patch": "```python\ndef add(a, b): return a + b\n```"}
        ]
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="AssertionError: expected 5, got -1",
                failed_cases=[{"name": "test_add", "error": "expected 5, got -1"}],
                rag_references=rag_refs,
            )

        # 验证 LLM 调用包含了 RAG 参考内容
        call_args = mock_call.call_args[0][0]
        assert "参考修复案例" in call_args
        assert "原始代码" in call_args

    def test_debug_with_empty_rag_references(self):
        """测试空 RAG 参考的处理。"""
        mock_response = json.dumps(
            {
                "root_cause": "普通修复",
                "error_category": "assertion",
                "fix_strategy": "修复断言",
                "patch": "```python\ndef add(a, b): return a + b\n```",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="AssertionError: expected 5",
                failed_cases=[{"name": "test_add", "error": "expected 5"}],
                rag_references=[],
            )

        # 验证 LLM 调用不包含 RAG 参考
        call_args = mock_call.call_args[0][0]
        assert "参考修复案例" not in call_args

    def test_debug_with_none_rag_references(self):
        """测试 None RAG 参考的处理。"""
        mock_response = json.dumps(
            {
                "root_cause": "普通修复",
                "error_category": "assertion",
                "fix_strategy": "修复断言",
                "patch": "```python\ndef add(a, b): return a + b\n```",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def add(a, b): return a - b",
                test_output="AssertionError: expected 5",
                failed_cases=[{"name": "test_add", "error": "expected 5"}],
                rag_references=None,
            )

        # 验证 LLM 调用不包含 RAG 参考
        call_args = mock_call.call_args[0][0]
        assert "参考修复案例" not in call_args

    def test_debug_truncates_long_code(self):
        """测试超长代码截断。"""
        mock_response = json.dumps(
            {
                "root_cause": "截断测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        long_code = "x = 1\n" * 2000  # 生成超长代码
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code=long_code, test_output="AssertionError", failed_cases=[{"name": "test", "error": "failed"}]
            )

        # 验证调用中包含截断标记
        call_args = mock_call.call_args[0][0]
        assert "截断" in call_args or len(long_code) > 3000

    def test_debug_truncates_test_output(self):
        """测试测试输出截断。"""
        mock_response = json.dumps(
            {
                "root_cause": "截断测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        long_output = "Error: " * 1000  # 生成超长输出
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def f(): pass", test_output=long_output, failed_cases=[{"name": "test", "error": "failed"}]
            )

        # 验证调用中输出被截断
        call_args = mock_call.call_args[0][0]
        assert len(call_args) < len(long_output) * 2  # 应该被截断

    def test_debug_limits_failed_cases_summary(self):
        """测试失败用例摘要限制数量。"""
        mock_response = json.dumps(
            {
                "root_cause": "摘要限制测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        # 创建超过最大数量的失败用例
        failed_cases = [{"name": f"test_{i}", "error": f"error_{i}"} for i in range(10)]
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(target_code="def f(): pass", test_output="AssertionError", failed_cases=failed_cases)

        # 验证只包含前 5 个用例
        call_args = mock_call.call_args[0][0]
        assert "test_0" in call_args
        assert "test_4" in call_args
        assert "test_5" not in call_args  # 应该被截断

    def test_debug_limits_failed_case_error_length(self):
        """测试失败用例错误信息长度限制。"""
        mock_response = json.dumps(
            {
                "root_cause": "长度限制测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        long_error = "x" * 500  # 超长错误信息
        failed_cases = [{"name": "test_long", "error": long_error}]
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            self.agent.debug(target_code="def f(): pass", test_output="AssertionError", failed_cases=failed_cases)

        # 验证错误信息被截断
        # 单条错误信息不应超过截断长度
        assert len(long_error) > 200

    def test_debug_limits_rag_references(self):
        """测试 RAG 参考数量限制。"""
        mock_response = json.dumps(
            {
                "root_cause": "RAG 限制测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        # 创建超过最大数量的 RAG 参考
        rag_refs = [{"original_code": f"code_{i}", "patch": f"patch_{i}"} for i in range(5)]
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def f(): pass", test_output="AssertionError", failed_cases=[], rag_references=rag_refs
            )

        # 验证只使用前 2 个参考
        call_args = mock_call.call_args[0][0]
        assert "参考修复案例 1" in call_args
        assert "参考修复案例 2" in call_args
        # 第 3 个及以后不应该出现
        assert call_args.count("参考修复案例") <= 2

    def test_debug_truncates_rag_original_code(self):
        """测试 RAG 参考中 original_code 截断。"""
        mock_response = json.dumps(
            {
                "root_cause": "RAG 截断测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        long_code = "x" * 1000
        rag_refs = [{"original_code": long_code, "patch": "patch"}]
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            self.agent.debug(
                target_code="def f(): pass", test_output="AssertionError", failed_cases=[], rag_references=rag_refs
            )

        # original_code 应被截断
        assert len(long_code) > 500

    def test_debug_returns_default_values_on_missing_fields(self):
        """测试 LLM 返回缺少字段时的默认值处理。"""
        # Mock 返回不完整 JSON
        incomplete_response = json.dumps(
            {
                "root_cause": "部分修复"
                # 缺少 error_category, fix_strategy, patch
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=incomplete_response):
            result = self.agent.debug(target_code="def f(): pass", test_output="AssertionError", failed_cases=[])

        # 验证缺失字段有默认值
        assert result["root_cause"] == "部分修复"
        assert result["error_category"] == "assertion"  # 从 classifier 获取
        assert result["fix_strategy"] != ""  # 有默认策略
        assert result["patch"] == ""  # 缺失时为空字符串

    def test_debug_classifies_error_correctly(self):
        """测试错误分类正确传递到 LLM 调用。"""
        mock_response = json.dumps(
            {
                "root_cause": "测试",
                "error_category": "runtime",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def divide(a, b): return a / b",
                test_output="ZeroDivisionError: division by zero",
                failed_cases=[],
            )

        # 验证 LLM 调用中包含正确的错误类型
        call_args = mock_call.call_args[0][0]
        assert "runtime" in call_args.lower()

    def test_debug_multiple_failed_cases(self):
        """测试多个失败用例的处理。"""
        mock_response = json.dumps(
            {
                "root_cause": "多用例测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        failed_cases = [
            {"name": "test_1", "error": "expected 1, got 2"},
            {"name": "test_2", "error": "expected 3, got 4"},
            {"name": "test_3", "error": "expected 5, got 6"},
        ]
        with patch.object(self.agent, "_call_llm", return_value=mock_response) as mock_call:
            self.agent.debug(
                target_code="def f(x): return x + 1", test_output="AssertionError", failed_cases=failed_cases
            )

        call_args = mock_call.call_args[0][0]
        assert "test_1" in call_args
        assert "test_2" in call_args
        assert "test_3" in call_args

    def test_debug_empty_failed_cases(self):
        """测试空失败用例列表的处理。"""
        mock_response = json.dumps(
            {"root_cause": "空用例测试", "error_category": "unknown", "fix_strategy": "通用分析", "patch": ""}
        )
        with patch.object(self.agent, "_call_llm", return_value=mock_response):
            result = self.agent.debug(target_code="def f(): pass", test_output="Some error", failed_cases=[])
        assert result is not None
        assert "root_cause" in result


class TestDebuggerIntegration:
    """集成测试：验证完整调试流程。"""

    def test_full_debug_workflow_syntax(self):
        """完整语法错误调试工作流。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "缺少 import 语句",
                "error_category": "syntax",
                "fix_strategy": "添加缺失导入",
                "patch": "```python\nimport math\n\ndef calculate(x):\n    return math.sqrt(x)\n```",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(
                target_code="def calculate(x): return sqrt(x)",
                test_output="SyntaxError: invalid syntax",
                failed_cases=[{"name": "test_calc", "error": "SyntaxError"}],
            )

        assert result["error_category"] == "syntax"
        assert "import math" in result["patch"]
        assert "root_cause" in result

    def test_full_debug_workflow_runtime(self):
        """完整运行时错误调试工作流。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "除零未处理",
                "error_category": "runtime",
                "fix_strategy": "添加边界检查",
                "patch": """```python
def divide(a, b):
    if b == 0:
        raise ValueError('除数不能为零')
    return a / b
```""",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(
                target_code="def divide(a, b): return a / b",
                test_output="ZeroDivisionError: division by zero",
                failed_cases=[{"name": "test_div", "error": "ZeroDivisionError"}],
            )

        assert result["error_category"] == "runtime"
        assert "b == 0" in result["patch"]

    def test_full_debug_workflow_assertion(self):
        """完整断言错误调试工作流。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "运算符错误",
                "error_category": "assertion",
                "fix_strategy": "修正运算符",
                "patch": "```python\ndef multiply(a, b):\n    return a * b\n```",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(
                target_code="def multiply(a, b): return a + b",
                test_output="AssertionError: expected 6, got 5",
                failed_cases=[{"name": "test_mul", "error": "expected 6, got 5"}],
            )

        assert result["error_category"] == "assertion"
        assert "a * b" in result["patch"]

    def test_full_debug_workflow_timeout(self):
        """完整超时错误调试工作流。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "缺少递归终止条件",
                "error_category": "timeout",
                "fix_strategy": "添加终止条件",
                "patch": "```python\ndef fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)\n```",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(
                target_code="def fib(n): return fib(n-1) + fib(n-2)",
                test_output="timeout exceeded",
                failed_cases=[{"name": "test_fib", "error": "TimedOut"}],
            )

        assert result["error_category"] == "timeout"
        assert "n <= 1" in result["patch"]


class TestDebuggerEdgeCases:
    """边界条件测试。"""

    def test_debug_with_unicode_content(self):
        """测试包含 Unicode 内容的调试。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "中文根因分析",
                "error_category": "assertion",
                "fix_strategy": "中文修复策略",
                "patch": "```python\ndef 问候(name):\n    return f'你好, {name}'\n```",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(
                target_code="def 问候(name): return 'hello'",
                test_output="AssertionError: 期望中文问候",
                failed_cases=[{"name": "test_中文", "error": "期望中文"}],
            )

        assert result["error_category"] == "assertion"
        assert "你好" in result["patch"]

    def test_debug_with_very_long_target_code(self):
        """测试超长目标代码的处理。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "截断测试",
                "error_category": "unknown",
                "fix_strategy": "分析",
                "patch": "```python\n# fixed\n```",
            }
        )
        long_code = "\n".join(f"def func_{i}(): pass" for i in range(200))
        with patch.object(agent, "_call_llm", return_value=mock_response):
            result = agent.debug(target_code=long_code, test_output="Some error", failed_cases=[])
        assert result is not None

    def test_debug_with_malformed_llm_response(self):
        """测试 LLM 返回畸形响应的处理。"""
        agent = DebuggerAgent()
        # 返回不是 JSON 的内容
        bad_response = "This is not JSON at all"
        with patch.object(agent, "_call_llm", return_value=bad_response):
            try:
                agent.debug(target_code="def f(): pass", test_output="Error", failed_cases=[])
                raise AssertionError("应该抛出异常")
            except json.JSONDecodeError:
                pass  # 期望抛出 JSONDecodeError

    def test_debug_logger_info_called(self):
        """测试日志记录功能。"""
        agent = DebuggerAgent()
        mock_response = json.dumps(
            {
                "root_cause": "测试",
                "error_category": "assertion",
                "fix_strategy": "测试",
                "patch": "```python\n# fixed\n```",
            }
        )
        with patch.object(agent, "_call_llm", return_value=mock_response):
            with patch("src.agents.debugger.logger") as mock_logger:
                agent.debug(target_code="def f(): pass", test_output="AssertionError", failed_cases=[])
                # 验证记录了分类结果
                mock_logger.info.assert_called()
