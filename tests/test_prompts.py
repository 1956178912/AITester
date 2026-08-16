"""
单元测试：测试 Prompt 模板的完整性。

覆盖范围：
    - 所有 prompt 非空且长度合理
    - PLANNER 包含 logic_analysis/test_cases 要求
    - GENERATOR 包含 pytest/import 约束
    - DEBUGGER 包含分层修复规则（5类错误）
    - EXECUTOR 为非空占位符
"""

import pytest
from src.prompts.templates import (
    PLANNER_SYSTEM_PROMPT,
    GENERATOR_SYSTEM_PROMPT,
    EXECUTOR_SYSTEM_PROMPT,
    DEBUGGER_SYSTEM_PROMPT,
)


# ─── TestPromptTemplates：Prompt 模板完整性 ────────────────────────────────────
class TestPromptTemplates:
    """测试所有 System Prompt 的完整性。"""

    def test_all_prompts_non_empty(self):
        """所有 prompt 不应为空（EXECUTOR 为占位符，允许较短）。"""
        prompts = {
            "PLANNER_SYSTEM_PROMPT": PLANNER_SYSTEM_PROMPT,
            "GENERATOR_SYSTEM_PROMPT": GENERATOR_SYSTEM_PROMPT,
            "EXECUTOR_SYSTEM_PROMPT": EXECUTOR_SYSTEM_PROMPT,
            "DEBUGGER_SYSTEM_PROMPT": DEBUGGER_SYSTEM_PROMPT,
        }
        for name, prompt in prompts.items():
            if name == "EXECUTOR_SYSTEM_PROMPT":
                assert len(prompt) > 0, f"{name} 为空"
            else:
                assert len(prompt) > 50, f"{name} 过短（{len(prompt)} 字符）"

    def test_planner_includes_logic_analysis(self):
        """PLANNER prompt 应包含 logic_analysis 字段说明。"""
        assert "logic_analysis" in PLANNER_SYSTEM_PROMPT
        assert "input_domain" in PLANNER_SYSTEM_PROMPT
        assert "edge_cases" in PLANNER_SYSTEM_PROMPT

    def test_planner_includes_test_cases(self):
        """PLANNER prompt 应包含 test_cases 字段说明。"""
        assert "test_cases" in PLANNER_SYSTEM_PROMPT
        assert "case_name" in PLANNER_SYSTEM_PROMPT

    def test_planner_requires_json_format(self):
        """PLANNER prompt 应要求 JSON 格式输出。"""
        assert "JSON" in PLANNER_SYSTEM_PROMPT or "json" in PLANNER_SYSTEM_PROMPT

    def test_generator_requires_pytest_style(self):
        """GENERATOR prompt 应要求 pytest 风格。"""
        assert "pytest" in GENERATOR_SYSTEM_PROMPT.lower()

    def test_generator_requires_import_constraint(self):
        """GENERATOR prompt 应约束 import 来源模块。"""
        assert "import" in GENERATOR_SYSTEM_PROMPT
        assert "module_name" in GENERATOR_SYSTEM_PROMPT

    def test_generator_mentions_parametrize(self):
        """GENERATOR prompt 应涉及 parametrize 最佳实践。"""
        assert "parametrize" in GENERATOR_SYSTEM_PROMPT

    def test_generator_warns_against_redefining_function(self):
        """GENERATOR prompt 应禁止重新定义被测函数。"""
        assert "不要重新定义" in GENERATOR_SYSTEM_PROMPT or "重新定义" in GENERATOR_SYSTEM_PROMPT

    def test_debugger_includes_all_error_categories(self):
        """DEBUGGER prompt 应包含全部五类错误的修复规则。"""
        categories = ["syntax", "runtime", "assertion", "timeout", "unknown"]
        for cat in categories:
            assert cat in DEBUGGER_SYSTEM_PROMPT.lower(), f"缺少 {cat} 修复规则"

    def test_debugger_includes_root_cause_field(self):
        """DEBUGGER prompt 应要求 root_cause 字段。"""
        assert "root_cause" in DEBUGGER_SYSTEM_PROMPT

    def test_debugger_includes_patch_field(self):
        """DEBUGGER prompt 应要求 patch 字段。"""
        assert "patch" in DEBUGGER_SYSTEM_PROMPT

    def test_executor_is_placeholder(self):
        """EXECUTOR prompt 应为占位符（不使用 LLM）。"""
        assert "LLM" in EXECUTOR_SYSTEM_PROMPT or "does not use" in EXECUTOR_SYSTEM_PROMPT.lower()

    def test_planner_requires_logic_coverage(self):
        """PLANNER prompt 应要求 logic_coverage 字段关联逻辑分析。"""
        assert "logic_coverage" in PLANNER_SYSTEM_PROMPT

    def test_debugger_requires_complete_file_patch(self):
        """DEBUGGER prompt 应要求完整文件代码作为 patch。"""
        assert "完整" in DEBUGGER_SYSTEM_PROMPT or "完整文件" in DEBUGGER_SYSTEM_PROMPT
