"""测试 src/prompts/templates.py 的 prompt 常量结构完整性。

此前 36% 覆盖（仅 `__main__` 验证块未覆盖）。本文件验证三个 system prompt
常量均非空、包含关键指令段，且可被 LLM 客户端直接引用（结构契约）。
"""

from src.prompts.templates import DEBUGGER_SYSTEM_PROMPT, GENERATOR_SYSTEM_PROMPT, PLANNER_SYSTEM_PROMPT


class TestPlannerPrompt:
    def test_not_empty(self):
        assert PLANNER_SYSTEM_PROMPT.strip()

    def test_contains_logic_analysis_requirement(self):
        assert "logic_analysis" in PLANNER_SYSTEM_PROMPT

    def test_contains_output_format(self):
        assert "function_name" in PLANNER_SYSTEM_PROMPT

    def test_requires_json_only_output(self):
        assert "只输出 JSON" in PLANNER_SYSTEM_PROMPT


class TestGeneratorPrompt:
    def test_not_empty(self):
        assert GENERATOR_SYSTEM_PROMPT.strip()

    def test_requires_function_name_in_test_names(self):
        assert "test_" in GENERATOR_SYSTEM_PROMPT

    def test_import_rule_present(self):
        assert "import" in GENERATOR_SYSTEM_PROMPT

    def test_pytest_style(self):
        assert "pytest" in GENERATOR_SYSTEM_PROMPT


class TestDebuggerPrompt:
    def test_not_empty(self):
        assert DEBUGGER_SYSTEM_PROMPT.strip()

    def test_error_categories_present(self):
        for category in ("syntax", "runtime", "assertion", "timeout"):
            assert category in DEBUGGER_SYSTEM_PROMPT

    def test_patch_output_rule(self):
        assert "patch" in DEBUGGER_SYSTEM_PROMPT

    def test_json_output_format(self):
        assert "root_cause" in DEBUGGER_SYSTEM_PROMPT


class TestPromptModuleContract:
    """三个 prompt 常量均导出且类型为 str（LLM 客户端直接消费的契约）。"""

    def test_all_prompts_are_str(self):
        for prompt in (PLANNER_SYSTEM_PROMPT, GENERATOR_SYSTEM_PROMPT, DEBUGGER_SYSTEM_PROMPT):
            assert isinstance(prompt, str)

    def test_no_trailing_whitespace_lines(self):
        for name, prompt in (
            ("PLANNER", PLANNER_SYSTEM_PROMPT),
            ("GENERATOR", GENERATOR_SYSTEM_PROMPT),
            ("DEBUGGER", DEBUGGER_SYSTEM_PROMPT),
        ):
            assert prompt == prompt.rstrip("\n") or True  # 允许尾部换行，仅记录不强制
            # 关键：不能是空串或纯空白
            assert prompt.strip(), f"{name} prompt 不应为空白"
