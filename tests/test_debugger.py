"""
单元测试：测试 DebuggerAgent。

覆盖范围：
    - debug() 正常流程、failed_cases 截断、RAG 注入
"""

from unittest.mock import patch

import pytest

from src.agents.debugger import DebuggerAgent


# ─── TestDebuggerAgent：调试修复师 ────────────────────────────────────────────
class TestDebuggerAgent:
    """测试 DebuggerAgent.debug() 方法。"""

    def _make_agent(self):
        """工厂方法：创建 DebuggerAgent 实例。"""
        return DebuggerAgent()

    @patch.object(DebuggerAgent, "_call_llm")
    @patch.object(DebuggerAgent, "_extract_json")
    def test_debug_normal_flow(self, mock_extract, mock_llm):
        """正常流程：分类 → 构建 prompt → LLM 调用 → 返回结构化结果。"""
        mock_llm.return_value = '{"root_cause": "除零错误", "fix_strategy": "添加边界检查", "patch": "def foo(x): return 1 if x != 0 else 0"}'
        mock_extract.return_value = {
            "root_cause": "除零错误",
            "fix_strategy": "添加边界检查",
            "patch": "def foo(x): return 1 if x != 0 else 0",
        }
        agent = self._make_agent()
        target = "def foo(x): return 1/x"
        output = "ZeroDivisionError: division by zero"
        failed = [{"name": "test_foo", "error": "ZeroDivisionError"}]
        result = agent.debug(target, output, failed)
        assert result["error_category"] == "runtime"
        assert result["root_cause"] == "除零错误"
        assert "patch" in result
        mock_llm.assert_called_once()

    @patch.object(DebuggerAgent, "_call_llm")
    @patch.object(DebuggerAgent, "_extract_json")
    def test_debug_failed_cases_truncated(self, mock_extract, mock_llm):
        """failed_cases 超过 5 个时被截断，只展示前 5 个。"""
        mock_llm.return_value = '{"root_cause": "测试通过", "fix_strategy": "无需修改", "patch": ""}'
        mock_extract.return_value = {"root_cause": "测试通过", "fix_strategy": "无需修改", "patch": ""}
        agent = self._make_agent()
        # 构造 8 个失败用例
        failed = [{"name": f"test_{i}", "error": f"错误信息 {i}"} for i in range(8)]
        target = "def foo(): pass"
        output = "FAILED"
        result = agent.debug(target, output, failed)
        # 验证 LLM 调用中包含截断后的用例（最多 5 个）
        call_args = mock_llm.call_args[0][0]
        # 不应包含第 6 个及以后的用例名
        assert "test_5" not in call_args
        assert "test_4" in call_args

    @patch.object(DebuggerAgent, "_call_llm")
    @patch.object(DebuggerAgent, "_extract_json")
    def test_debug_rag_injected(self, mock_extract, mock_llm):
        """RAG 参考案例被注入 prompt（最多取 2 个，original_code 截断到 500 字符）。"""
        mock_llm.return_value = '{"root_cause": "参考修复", "fix_strategy": "应用补丁", "patch": "patched_code"}'
        mock_extract.return_value = {"root_cause": "参考修复", "fix_strategy": "应用补丁", "patch": "patched_code"}
        agent = self._make_agent()
        # 构造 5 个 RAG 参考（应只取前 2 个）
        rag = [
            {"original_code": "A" * 600, "patch": "patch_a"},
            {"original_code": "B" * 600, "patch": "patch_b"},
            {"original_code": "C" * 600, "patch": "patch_c"},
        ]
        target = "def foo(): pass"
        output = "AssertionError"
        failed = [{"name": "test_1", "error": "assert False"}]
        result = agent.debug(target, output, failed, rag_references=rag)
        call_args = mock_llm.call_args[0][0]
        # 前两个参考应出现在 prompt 中
        assert "patch_a" in call_args
        assert "patch_b" in call_args
        # 第三个不应出现（超过 2 个限制）
        assert "patch_c" not in call_args
        # original_code 截断到 500 字符
        # original_code 截断到 500 字符，600 字符不应完整出现
        assert "A" * 501 not in call_args  # 原始 600 字符应被截断

    @patch.object(DebuggerAgent, "_call_llm")
    @patch.object(DebuggerAgent, "_extract_json")
    def test_debug_llm_failure_raises(self, mock_extract, mock_llm):
        """LLM 调用失败时抛出异常。"""
        agent = self._make_agent()
        mock_llm.side_effect = RuntimeError("API 超时")
        with pytest.raises(RuntimeError, match="API 超时"):
            agent.debug("def foo(): pass", "error", [{"name": "t", "error": "err"}])

    @patch.object(DebuggerAgent, "_call_llm")
    @patch.object(DebuggerAgent, "_extract_json")
    def test_debug_missing_fields_default_values(self, mock_extract, mock_llm):
        """LLM 返回缺少字段时用默认值填充。"""
        mock_llm.return_value = '{"patch": "修复代码"}'
        mock_extract.return_value = {"patch": "修复代码"}
        agent = self._make_agent()
        result = agent.debug("def foo(): pass", "error", [{"name": "t", "error": "err"}])
        assert result["root_cause"] == "未知"
        assert result["fix_strategy"] != ""  # 使用分类器提供的策略作为默认
        assert result["patch"] == "修复代码"
