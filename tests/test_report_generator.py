"""
错误报告生成器单元测试（src/reports/generator.py）。

本模块此前零测试覆盖（0%）。覆盖内容：
- ErrorReport 数据类的 to_dict / to_text / to_markdown / to_json 各格式与分支
- ReportGenerator.generate 的五大错误分类（SYNTAX/RUNTIME/ASSERTION/TIMEOUT/UNKNOWN）
- 根本原因分析与修复建议生成的各分支（含依赖 ErrorContext 的导入错误分支）
- _parse_failed_cases 从 pytest 输出解析失败用例
- save_report 三种格式的落盘行为
- get_report_generator 单例语义

注意：generate() 已接入 classify_with_context，context 会随分类结果填充
（此前恒为 None，ImportError 根因分支是死代码）；直接调用私有方法构造
ErrorContext 的测试保留，用于覆盖 _analyze_root_cause / _generate_fix_suggestion
的各分支（含非导入类错误的 context 组合）。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.error_classifier import (
    ErrorCategory,
    ErrorContext,
    SyntaxSubtype,
)
from src.reports import generator as report_generator_module
from src.reports.generator import (
    ErrorReport,
    ReportFormat,
    ReportGenerator,
    get_report_generator,
)

# ─── 构造辅助 ─────────────────────────────────────────────────────────────────


def _import_context(module_name="pandas") -> ErrorContext:
    """构造一个导入错误子类型的错误上下文。"""
    return ErrorContext(module_name=module_name, subtype=SyntaxSubtype.IMPORT_ERROR)


def _report(**overrides) -> ErrorReport:
    """构造一个 ErrorReport，允许覆盖任意字段。"""
    base = dict(
        task_id="t-001",
        target_file="examples/calculator.py",
        target_function="divide",
        error_category=ErrorCategory.RUNTIME,
        error_message="ZeroDivisionError: division by zero",
        root_cause="除零错误",
        suggested_fix="添加零值检查",
    )
    base.update(overrides)
    return ErrorReport(**base)


# ─── ErrorReport 序列化 ───────────────────────────────────────────────────────


class TestErrorReportSerialization:
    """ErrorReport 各序列化方法"""

    def test_to_dict_without_context(self):
        """无 error_context 时字典中该字段为 None"""
        data = _report().to_dict()
        assert data["task_id"] == "t-001"
        assert data["error_context"] is None
        # 枚举序列化为其 value
        assert data["error_category"] == "runtime"

    def test_to_dict_with_context(self):
        """有 error_context 时序列化为 context 的 __dict__"""
        report = _report(error_context=ErrorContext(filename="a.py", line=3, column=1))
        data = report.to_dict()
        assert data["error_context"]["filename"] == "a.py"
        assert data["error_context"]["line"] == 3

    def test_to_text_minimal(self):
        """最小化报告（无 context / 无失败用例 / 无历史）包含基础字段"""
        text = _report().to_text()
        assert "任务 ID: t-001" in text
        assert "被测文件: examples/calculator.py" in text
        assert "ZeroDivisionError: division by zero" in text
        # 无对应区块
        assert "错误位置" not in text
        assert "失败测试用例" not in text
        assert "历史修复记录" not in text

    def test_to_text_empty_message_fallbacks(self):
        """空 error_message / root_cause / suggested_fix 使用占位文案"""
        report = _report(error_message="", root_cause="", suggested_fix="")
        text = report.to_text()
        assert "（无错误信息）" in text
        assert "（待分析）" in text
        assert "（暂无建议）" in text

    def test_to_text_with_context(self):
        """带 error_context 时输出错误位置区块"""
        report = _report(error_context=ErrorContext(filename="a.py", line=42, column=7))
        text = report.to_text()
        assert "文件: a.py" in text
        assert "行号: 42" in text
        assert "列号: 7" in text

    def test_to_text_failed_cases_truncation(self):
        """超过 5 个失败用例时截断并提示剩余数量"""
        cases = [{"name": f"test_{i}"} for i in range(8)]
        text = _report(failed_cases=cases).to_text()
        assert "共 8 个失败用例" in text
        assert "  ... 还有 3 个失败用例" in text

    def test_to_text_failed_case_with_error(self):
        """失败用例含 error 字段时输出截断的错误信息"""
        err = "AssertionError: " + "x" * 150
        cases = [{"name": "test_x", "error": err}]
        text = _report(failed_cases=cases).to_text()
        assert "test_x" in text
        # 展示的错误恰好是前 100 字符并追加 "..."（5 空格缩进 + "错误: " 前缀）
        assert f"     错误: {err[:100]}..." in text
        # 完整未截断的错误（含 150 个 x）不出现
        assert err not in text

    def test_to_text_history_shows_last_three(self):
        """历史修复记录只展示最近 3 条，缺失字段有兜底"""
        history = [{"action": f"fix-{i}", "result": "ok"} for i in range(5)]
        # 附加一条无 action 也无 result 的记录
        history.append({})
        text = _report(history=history).to_text()
        assert "共 6 次修复尝试" in text
        # 只展示最近 3 条（第 4、5、6 条）
        assert "第 1 次: fix-3" in text
        assert "第 3 次: unknown" in text
        assert "结果: ok" in text
        # 第 6 条（空 dict）无 action 也无 result
        assert "第 3 次: unknown" in text

    def test_to_markdown_minimal(self):
        """最小化 Markdown 报告包含标题与表格"""
        md = _report().to_markdown()
        assert md.startswith("# AITester 错误诊断报告")
        assert "| 任务 ID | `t-001` |" in md
        assert "## 错误信息" in md

    def test_to_markdown_with_context_and_cases(self):
        """带 context 与失败用例的 Markdown 报告"""
        err = "TypeError: " + "y" * 250
        report = _report(
            error_context=ErrorContext(filename="a.py", line=1, column=1),
            failed_cases=[{"name": "test_x", "error": err}],
        )
        md = report.to_markdown()
        assert "## 错误位置" in md
        assert "`a.py`" in md
        assert "**test_x**" in md
        # 错误信息截断到 200 字符（"   ```python" 代码块内为 err[:200]）
        assert f"   {err[:200]}" in md
        # 完整未截断的错误不出现
        assert err not in md

    def test_to_markdown_many_cases_truncation(self):
        """超过 5 个失败用例时 Markdown 提示剩余数量"""
        cases = [{"name": f"test_{i}"} for i in range(7)]
        md = _report(failed_cases=cases).to_markdown()
        assert "共 7 个" in md
        assert "*... 还有 2 个失败用例*" in md

    def test_to_json_roundtrip(self):
        """to_json 输出可被 json.loads 还原为 to_dict 的结果"""
        report = _report(
            error_context=ErrorContext(filename="a.py", line=2, column=3),
            failed_cases=[{"name": "test_x", "error": "boom"}],
            history=[{"action": "fix", "result": "ok"}],
        )
        data = json.loads(report.to_json())
        assert data == report.to_dict()
        # 默认缩进为 2
        assert '\n  "task_id"' in report.to_json()


# ─── ReportGenerator.generate 分类路径 ────────────────────────────────────────


class TestGenerateClassification:
    """generate() 对各错误分类的判定"""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_generate_syntax_error(self):
        """ModuleNotFoundError → SYNTAX 且 context 随分类结果填充（此前 context 恒为 None）"""
        report = self.gen.generate(
            task_id="t",
            target_file="f.py",
            target_function="fn",
            error_output="ModuleNotFoundError: No module named 'pandas'",
        )
        assert report.error_category == ErrorCategory.SYNTAX
        # ImportError 根因分支现已可达：提取缺失模块名
        assert "缺少依赖模块 'pandas'" in report.root_cause
        assert report.error_subtype == "import_error"
        assert report.error_context is not None
        assert report.error_context.module_name == "pandas"

    def test_generate_plain_syntax_error_subtype(self):
        """纯语法错误（无 traceback 位置）不赋子类型"""
        report = self.gen.generate(
            task_id="t",
            target_file="f.py",
            target_function="fn",
            error_output="SyntaxError: invalid syntax",
        )
        assert report.error_category == ErrorCategory.SYNTAX
        assert report.error_subtype is None

    def test_generate_runtime_zero_division(self):
        """ZeroDivisionError → RUNTIME 且根因为除零"""
        report = self.gen.generate("t", "f.py", "fn", "ZeroDivisionError: division by zero")
        assert report.error_category == ErrorCategory.RUNTIME
        assert "除零" in report.root_cause

    def test_generate_runtime_type_error(self):
        report = self.gen.generate("t", "f.py", "fn", "TypeError: unsupported operand type(s)")
        assert report.error_category == ErrorCategory.RUNTIME
        assert "类型错误" in report.root_cause

    def test_generate_runtime_index_error(self):
        report = self.gen.generate("t", "f.py", "fn", "IndexError: list index out of range")
        assert "索引越界" in report.root_cause

    def test_generate_runtime_attribute_error(self):
        report = self.gen.generate("t", "f.py", "fn", "AttributeError: 'NoneType' object has no attribute 'x'")
        assert "属性错误" in report.root_cause

    def test_generate_runtime_generic(self):
        """RUNTIME 但不含特定异常名时走通用根因（ValueError 命中 runtime 但无专门分支）"""
        report = self.gen.generate("t", "f.py", "fn", "ValueError: invalid literal for int()")
        assert report.error_category == ErrorCategory.RUNTIME
        assert "运行时异常" in report.root_cause

    def test_generate_assertion(self):
        report = self.gen.generate("t", "f.py", "fn", "AssertionError: assert 1 == 2")
        assert report.error_category == ErrorCategory.ASSERTION
        assert "断言失败" in report.root_cause

    def test_generate_timeout(self):
        report = self.gen.generate("t", "f.py", "fn", "execution timeout exceeded (limit 30s)")
        assert report.error_category == ErrorCategory.TIMEOUT
        assert "超时" in report.root_cause

    def test_generate_unknown(self):
        report = self.gen.generate("t", "f.py", "fn", "something went weird")
        assert report.error_category == ErrorCategory.UNKNOWN
        assert "未知错误类型" in report.root_cause

    def test_generate_truncates_long_error_message(self):
        """error_message 被截断到 500 字符"""
        report = self.gen.generate("t", "f.py", "fn", "x" * 600)
        assert len(report.error_message) == 500

    def test_generate_uses_explicit_failed_cases(self):
        """显式传入 failed_cases 时优先使用，不解析输出"""
        explicit = [{"name": "test_explicit", "error": "boom"}]
        report = self.gen.generate(
            "t",
            "f.py",
            "fn",
            "FAILED tests/other.py::test_other [E]",
            failed_cases=explicit,
        )
        assert report.failed_cases == explicit

    def test_generate_parses_failed_cases_from_output(self):
        """未传 failed_cases 时从输出解析"""
        output = "FAILED tests/a.py::test_one [E]\nAssertionError: expected 5, got 4"
        report = self.gen.generate("t", "f.py", "fn", output)
        assert report.failed_cases[0]["name"] == "tests/a.py::test_one"
        assert report.failed_cases[0]["error"] == "AssertionError: expected 5, got 4"

    def test_generate_history_default_and_passthrough(self):
        """history 缺省为空列表，传入时原样保留"""
        assert self.gen.generate("t", "f.py", "fn", "e").history == []
        hist = [{"action": "a", "result": "r"}]
        assert self.gen.generate("t", "f.py", "fn", "e", history=hist).history == hist

    def test_generate_coverage_and_iteration_passthrough(self):
        report = self.gen.generate("t", "f.py", "fn", "e", coverage=72.5, iteration_count=3)
        assert report.coverage == 72.5
        assert report.iteration_count == 3


# ─── 根本原因 / 修复建议（含 context 分支）────────────────────────────────────


class TestRootCauseAndFixSuggestion:
    """直接调用 _analyze_root_cause / _generate_fix_suggestion 覆盖 context 分支"""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_root_cause_import_error_with_module(self):
        """SYNTAX + IMPORT_ERROR context + 模块名 → 提示缺失该模块"""
        text = self.gen._analyze_root_cause(ErrorCategory.SYNTAX, _import_context("pandas"), "ModuleNotFoundError")
        assert "pandas" in text

    def test_root_cause_import_error_unknown_module(self):
        """模块名为 None 时回退到'未知模块'"""
        ctx = _import_context(None)
        text = self.gen._analyze_root_cause(ErrorCategory.SYNTAX, ctx, "ImportError")
        assert "未知模块" in text

    def test_root_cause_syntax_without_context(self):
        """SYNTAX 无 context → 通用语法错误提示"""
        text = self.gen._analyze_root_cause(ErrorCategory.SYNTAX, None, "SyntaxError")
        assert "语法错误" in text

    def test_fix_suggestion_import_error_includes_pip_install(self):
        """导入错误的修复建议包含 pip install 指令"""
        suggestion = self.gen._generate_fix_suggestion(
            ErrorCategory.SYNTAX, _import_context("numpy"), "ModuleNotFoundError"
        )
        assert "pip install numpy" in suggestion

    def test_fix_suggestion_syntax_without_context(self):
        """SYNTAX 无 context → 语法检查建议"""
        suggestion = self.gen._generate_fix_suggestion(ErrorCategory.SYNTAX, None, "SyntaxError")
        assert "检查语法错误位置" in suggestion

    def test_fix_suggestion_runtime_variants(self):
        """RUNTIME 各分支修复建议"""
        gen = self.gen
        assert "零值检查" in gen._generate_fix_suggestion(ErrorCategory.RUNTIME, None, "ZeroDivisionError: x")
        assert "参数类型" in gen._generate_fix_suggestion(ErrorCategory.RUNTIME, None, "TypeError: x")
        assert "索引边界" in gen._generate_fix_suggestion(ErrorCategory.RUNTIME, None, "IndexError: x")
        # 通用 runtime（无特定异常名）
        assert "查看完整错误堆栈" in gen._generate_fix_suggestion(ErrorCategory.RUNTIME, None, "ValueError: x")

    def test_fix_suggestion_assertion_timeout_unknown(self):
        gen = self.gen
        assert "pytest.approx" in gen._generate_fix_suggestion(ErrorCategory.ASSERTION, None, "AssertionError")
        assert "无限循环" in gen._generate_fix_suggestion(ErrorCategory.TIMEOUT, None, "timeout")
        assert "仔细分析错误输出" in gen._generate_fix_suggestion(ErrorCategory.UNKNOWN, None, "weird")


# ─── _parse_failed_cases ──────────────────────────────────────────────────────


class TestParseFailedCases:
    """_parse_failed_cases 从 pytest 输出解析失败用例"""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_parse_multiple_cases_with_errors(self):
        """多个 FAILED 行 + 紧随其后的错误详情行"""
        text = (
            "FAILED tests/a.py::test_one [E]\n"
            "AssertionError: expected 5, got 4\n"
            "FAILED tests/b.py::test_two [E]\n"
            "a normal line"
        )
        cases = self.gen._parse_failed_cases(text)
        assert len(cases) == 2
        assert cases[0]["name"] == "tests/a.py::test_one"
        assert cases[0]["error"] == "AssertionError: expected 5, got 4"
        assert cases[1]["name"] == "tests/b.py::test_two"
        # 第二行普通文本不含 Error，不附加 error
        assert "error" not in cases[1]

    def test_parse_no_failed_lines_returns_empty(self):
        assert self.gen._parse_failed_cases("no failures here") == []

    def test_parse_single_case(self):
        cases = self.gen._parse_failed_cases("FAILED tests/x.py::test_y [E]")
        assert cases == [{"name": "tests/x.py::test_y"}]

    def test_parse_failed_line_without_name_fallback_unknown(self):
        """FAILED 位于行尾、无用例名时，name 兜底为 'unknown'"""
        # "FAILED" 后无空白+非空白字符（\S+ 匹配失败），走 else 分支
        cases = self.gen._parse_failed_cases("[collected] FAILED")
        assert cases == [{"name": "unknown"}]


# ─── save_report ──────────────────────────────────────────────────────────────


class TestSaveReport:
    """save_report 三种格式落盘"""

    def setup_method(self):
        self.gen = ReportGenerator()

    def test_save_text_report(self, tmp_path):
        report = _report()
        filepath = self.gen.save_report(report, output_dir=str(tmp_path / "out"), format=ReportFormat.TEXT)
        assert filepath.suffix == ".txt"
        assert filepath.exists()
        content = filepath.read_text(encoding="utf-8")
        assert "任务 ID: t-001" in content

    def test_save_json_report(self, tmp_path):
        report = _report()
        filepath = self.gen.save_report(report, output_dir=str(tmp_path), format=ReportFormat.JSON)
        assert filepath.suffix == ".json"
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["task_id"] == "t-001"

    def test_save_markdown_report(self, tmp_path):
        report = _report()
        filepath = self.gen.save_report(report, output_dir=str(tmp_path), format=ReportFormat.MARKDOWN)
        assert filepath.suffix == ".md"
        content = filepath.read_text(encoding="utf-8")
        assert content.startswith("# AITester 错误诊断报告")

    def test_save_creates_missing_output_dir(self, tmp_path):
        report = _report()
        nested = tmp_path / "a" / "b" / "c"
        filepath = self.gen.save_report(report, output_dir=str(nested), format=ReportFormat.TEXT)
        assert filepath.parent == nested
        assert nested.is_dir()

    def test_filename_contains_task_id_and_timestamp(self, tmp_path):
        report = _report(task_id="task-999")
        filepath = self.gen.save_report(report, output_dir=str(tmp_path), format=ReportFormat.TEXT)
        assert "task-999" in filepath.name
        # 文件名形如 report_task-999_20260101_120000.txt
        import re

        assert re.match(r"^report_task-999_\d{8}_\d{6}\.txt$", filepath.name)

    def test_task_id_sanitized_in_filename(self, tmp_path):
        """task_id 中的路径分隔符/非法字符被消毒，防止路径穿越（此前原样拼接进文件名）"""
        report = _report(task_id="../../etc/passwd")
        filepath = self.gen.save_report(report, output_dir=str(tmp_path), format=ReportFormat.TEXT)
        # 关键断言：文件必须落在 output_dir 内部（分隔符已清除，".." 不再是路径组件）
        assert filepath.parent == tmp_path
        assert "/" not in filepath.name
        assert "\\" not in filepath.name
        # 报告中原始 task_id 保持不变（只消毒文件名）
        assert report.task_id == "../../etc/passwd"

    def test_task_id_truncated_to_64_chars(self, tmp_path):
        """超长 task_id 截断到 64 字符，避免文件系统路径长度问题"""
        report = _report(task_id="x" * 200)
        filepath = self.gen.save_report(report, output_dir=str(tmp_path), format=ReportFormat.TEXT)
        # report_(7) + 64 + _(1) + 时间戳8+1+6=15 + .txt(4) = 91
        assert len(filepath.name) == 7 + 64 + 1 + 15 + 4


# ─── 单例 ─────────────────────────────────────────────────────────────────────


class TestSingleton:
    """get_report_generator 单例语义"""

    def test_returns_same_instance(self):
        a = get_report_generator()
        b = get_report_generator()
        assert a is b
        assert isinstance(a, ReportGenerator)

    def test_reset_creates_new_instance(self):
        original = get_report_generator()
        report_generator_module._report_generator = None
        new_instance = get_report_generator()
        assert new_instance is not original
        assert isinstance(new_instance, ReportGenerator)
