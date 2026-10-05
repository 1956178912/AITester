"""测试 src/prompts/templates.py 的 prompt 常量结构完整性。

此前 36% 覆盖（仅 `__main__` 验证块未覆盖）。本文件验证四个 system prompt
常量（含 OracleEnhancer）均非空、包含关键指令段，且可被 LLM 客户端直接引用
（结构契约）。
"""

from src.prompts.templates import (
    DEBUGGER_SYSTEM_PROMPT,
    GENERATOR_SYSTEM_PROMPT,
    ORACLE_ENHANCER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    log_prompt_char_counts,
)


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


class TestOracleEnhancerPrompt:
    """OracleEnhancer 预言增强 prompt（默认关，结构契约锁定）。"""

    def test_not_empty(self):
        assert ORACLE_ENHANCER_SYSTEM_PROMPT.strip()

    def test_oracle_source_enum_present(self):
        for source in ("postcondition", "edge_case", "invariant", "unknown"):
            assert source in ORACLE_ENHANCER_SYSTEM_PROMPT

    def test_requires_pytest_raises_for_exception(self):
        assert "pytest.raises" in ORACLE_ENHANCER_SYSTEM_PROMPT

    def test_json_array_output(self):
        assert "JSON 数组" in ORACLE_ENHANCER_SYSTEM_PROMPT


class TestPromptModuleContract:
    """四个 prompt 常量均导出且类型为 str（LLM 客户端直接消费的契约）。"""

    def test_all_prompts_are_str(self):
        for prompt in (
            PLANNER_SYSTEM_PROMPT,
            GENERATOR_SYSTEM_PROMPT,
            DEBUGGER_SYSTEM_PROMPT,
            ORACLE_ENHANCER_SYSTEM_PROMPT,
        ):
            assert isinstance(prompt, str)

    def test_no_trailing_whitespace_lines(self):
        """四个 prompt 每行不含尾随空白（尾部单个换行允许）。

        此前断言写成 `prompt == prompt.rstrip("\\n") or True`——`or True`
        使比较恒真（无论 prompt 是否带尾随换行都通过，2026-10-02 审查
        修复消除恒真断言）。
        """
        for name, prompt in (
            ("PLANNER", PLANNER_SYSTEM_PROMPT),
            ("GENERATOR", GENERATOR_SYSTEM_PROMPT),
            ("DEBUGGER", DEBUGGER_SYSTEM_PROMPT),
            ("ORACLE_ENHANCER", ORACLE_ENHANCER_SYSTEM_PROMPT),
        ):
            for i, line in enumerate(prompt.split("\n"), start=1):
                assert line == line.rstrip(), f"{name} prompt 第 {i} 行含尾随空白"
            # 关键：不能是空串或纯空白
            assert prompt.strip(), f"{name} prompt 不应为空白"


class TestLogPromptCharCounts:
    """log_prompt_char_counts 可测试函数（2026-10-02 批次·七 抽自 __main__ 块）。"""

    def test_callable_no_side_effect(self):
        """纯观测函数：可被 import 调用，不抛异常（只写日志）。"""
        # U3（2026-10-05 系统性审查落地）：补断言——无返回值（纯观测副作用）
        assert log_prompt_char_counts() is None

    def test_logs_all_four_prompts(self, caplog):
        import logging

        with caplog.at_level(logging.INFO):
            log_prompt_char_counts()
        logged_msgs = [r.getMessage() for r in caplog.records]
        for name in (
            "PLANNER_SYSTEM_PROMPT",
            "GENERATOR_SYSTEM_PROMPT",
            "DEBUGGER_SYSTEM_PROMPT",
            "ORACLE_ENHANCER_SYSTEM_PROMPT",
        ):
            assert any(name in m for m in logged_msgs), f"{name} 未出现在日志中"
            assert "字符" in next(m for m in logged_msgs if name in m), f"{name} 日志缺字符数"
