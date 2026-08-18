"""
错误报告生成器模块：将测试失败信息转化为结构化、可读的诊断报告。

本模块提供以下功能：
1. 将原始错误信息分类整理
2. 生成包含问题定位、修复建议的结构化报告
3. 支持多种输出格式（文本、JSON、Markdown）
4. 集成 RAG 检索，提供历史相似案例参考
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from src.agents.error_classifier import ErrorCategory, ErrorClassifier, ErrorContext


class ReportFormat(Enum):
    """报告输出格式枚举。"""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class ErrorReport:
    """
    错误报告数据结构。

    属性:
        task_id: 任务唯一标识
        target_file: 被测文件路径
        target_function: 被测函数名
        error_category: 错误分类
        error_subtype: 错误子类型（如 import_error, syntax_error）
        error_message: 原始错误消息
        error_context: 错误上下文（文件名、行号、列号等）
        root_cause: 根本原因分析
        suggested_fix: 建议修复方案
        failed_cases: 失败的测试用例列表
        iteration_count: 已修复迭代次数
        coverage: 当前覆盖率
        created_at: 报告生成时间
        history: 历史修复记录列表
    """

    task_id: str
    target_file: str
    target_function: str
    error_category: ErrorCategory
    error_subtype: str | None = None
    error_message: str = ""
    error_context: ErrorContext | None = None
    root_cause: str = ""
    suggested_fix: str = ""
    failed_cases: list[dict[str, Any]] = field(default_factory=list)
    iteration_count: int = 0
    coverage: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """将报告转换为字典格式。"""
        return {
            "task_id": self.task_id,
            "target_file": self.target_file,
            "target_function": self.target_function,
            "error_category": self.error_category.value,
            "error_subtype": self.error_subtype,
            "error_message": self.error_message,
            "error_context": self.error_context.__dict__ if self.error_context else None,
            "root_cause": self.root_cause,
            "suggested_fix": self.suggested_fix,
            "failed_cases": self.failed_cases,
            "iteration_count": self.iteration_count,
            "coverage": self.coverage,
            "created_at": self.created_at,
            "history": self.history,
        }

    def to_text(self) -> str:
        """生成纯文本格式报告。"""
        lines = [
            "=" * 60,
            "AITester 错误诊断报告",
            "=" * 60,
            "",
            f"任务 ID: {self.task_id}",
            f"被测文件: {self.target_file}",
            f"被测函数: {self.target_function}",
            f"错误分类: {self.error_category.value}",
            f"迭代次数: {self.iteration_count}",
            f"当前覆盖率: {self.coverage:.1f}%",
            "",
            "--- 错误信息 ---",
            self.error_message or "（无错误信息）",
            "",
        ]

        if self.error_context:
            lines.extend(
                [
                    "--- 错误位置 ---",
                    f"文件: {self.error_context.filename}",
                    f"行号: {self.error_context.line}",
                    f"列号: {self.error_context.column}",
                    "",
                ]
            )

        lines.extend(
            [
                "--- 根本原因 ---",
                self.root_cause or "（待分析）",
                "",
                "--- 修复建议 ---",
                self.suggested_fix or "（暂无建议）",
                "",
            ]
        )

        if self.failed_cases:
            lines.extend(
                [
                    "--- 失败测试用例 ---",
                    f"共 {len(self.failed_cases)} 个失败用例",
                ]
            )
            for i, case in enumerate(self.failed_cases[:5], 1):  # 最多显示5个
                lines.append(f"  {i}. {case.get('name', 'unknown')}")
                if case.get("error"):
                    lines.append(f"     错误: {case['error'][:100]}...")
            if len(self.failed_cases) > 5:
                lines.append(f"  ... 还有 {len(self.failed_cases) - 5} 个失败用例")
            lines.append("")

        if self.history:
            lines.extend(
                [
                    "--- 历史修复记录 ---",
                    f"共 {len(self.history)} 次修复尝试",
                ]
            )
            for i, record in enumerate(self.history[-3:], 1):  # 显示最近3次
                lines.append(f"  第 {i} 次: {record.get('action', 'unknown')}")
                if record.get("result"):
                    lines.append(f"         结果: {record['result']}")
            lines.append("")

        lines.extend(
            [
                "=" * 60,
                f"报告生成时间: {self.created_at}",
                "=" * 60,
            ]
        )

        return "\n".join(lines)

    def to_markdown(self) -> str:
        """生成 Markdown 格式报告。"""
        lines = [
            "# AITester 错误诊断报告",
            "",
            "| 字段 | 值 |",
            "|------|-----|",
            f"| 任务 ID | `{self.task_id}` |",
            f"| 被测文件 | `{self.target_file}` |",
            f"| 被测函数 | `{self.target_function}` |",
            f"| 错误分类 | {self.error_category.value} |",
            f"| 迭代次数 | {self.iteration_count} |",
            f"| 当前覆盖率 | {self.coverage:.1f}% |",
            f"| 生成时间 | {self.created_at} |",
            "",
            "## 错误信息",
            "",
            "```",
            self.error_message or "（无错误信息）",
            "```",
            "",
        ]

        if self.error_context:
            lines.extend(
                [
                    "## 错误位置",
                    "",
                    f"- **文件**: `{self.error_context.filename}`",
                    f"- **行号**: {self.error_context.line}",
                    f"- **列号**: {self.error_context.column}",
                    "",
                ]
            )

        lines.extend(
            [
                "## 根本原因",
                "",
                self.root_cause or "（待分析）",
                "",
                "## 修复建议",
                "",
                self.suggested_fix or "（暂无建议）",
                "",
            ]
        )

        if self.failed_cases:
            lines.extend(
                [
                    f"## 失败测试用例（共 {len(self.failed_cases)} 个）",
                    "",
                ]
            )
            for i, case in enumerate(self.failed_cases[:5], 1):
                lines.append(f"{i}. **{case.get('name', 'unknown')}**")
                if case.get("error"):
                    lines.append("   ```python")
                    lines.append(f"   {case['error'][:200]}")
                    lines.append("   ```")
            if len(self.failed_cases) > 5:
                lines.append(f"\n*... 还有 {len(self.failed_cases) - 5} 个失败用例*")
            lines.append("")

        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """生成 JSON 格式报告。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


class ReportGenerator:
    """
    错误报告生成器。

    根据测试执行结果和错误信息，生成结构化的诊断报告。
    支持文本、JSON、Markdown 三种输出格式。
    """

    def __init__(self) -> None:
        """初始化报告生成器。"""
        self._classifier = ErrorClassifier()
        self._report_counter = 0

    def generate(
        self,
        task_id: str,
        target_file: str,
        target_function: str,
        error_output: str,
        failed_cases: list[dict[str, Any]] | None = None,
        coverage: float = 0.0,
        iteration_count: int = 0,
        history: list[dict[str, Any]] | None = None,
    ) -> ErrorReport:
        """
        生成错误报告。

        Args:
            task_id: 任务唯一标识
            target_file: 被测文件路径
            target_function: 被测函数名
            error_output: 测试执行错误输出
            failed_cases: 失败的测试用例列表（可选）
            coverage: 代码覆盖率（可选，默认 0.0）
            iteration_count: 已修复迭代次数（可选，默认 0）
            history: 历史修复记录（可选）

        Returns:
            ErrorReport: 生成的错误报告对象
        """
        self._report_counter += 1

        # 分类错误（传入空列表，由 classify 内部处理）
        category = self._classifier.classify(error_output, [])
        context: ErrorContext | None = None

        # 分析根本原因
        root_cause = self._analyze_root_cause(category, context, error_output)

        # 生成修复建议
        suggested_fix = self._generate_fix_suggestion(category, context, error_output)

        # 解析失败用例
        parsed_cases = failed_cases or self._parse_failed_cases(error_output)

        return ErrorReport(
            task_id=task_id,
            target_file=target_file,
            target_function=target_function,
            error_category=category,
            error_subtype=context.subtype.value if context else None,
            error_message=error_output.strip()[:500],  # 截断过长消息
            error_context=context,
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            failed_cases=parsed_cases,
            iteration_count=iteration_count,
            coverage=coverage,
            created_at=datetime.now().isoformat(),
            history=history or [],
        )

    def _analyze_root_cause(
        self,
        category: ErrorCategory,
        context: ErrorContext | None,
        error_output: str,
    ) -> str:
        """
        分析错误根本原因。

        Args:
            category: 错误分类
            context: 错误上下文
            error_output: 原始错误输出

        Returns:
            str: 根本原因描述
        """
        if category == ErrorCategory.SYNTAX:
            if context and context.subtype.name == "IMPORT_ERROR":
                module = context.module_name or "未知模块"
                return f"缺少依赖模块 '{module}'，请检查是否已安装或导入路径是否正确"
            return "代码存在语法错误，请检查冒号、缩进、括号配对等基础语法"

        if category == ErrorCategory.RUNTIME:
            if "ZeroDivisionError" in error_output:
                return "除零错误：被除数可能为 0，需要添加边界条件检查"
            if "TypeError" in error_output:
                return "类型错误：参数类型不匹配，请检查函数调用的参数类型"
            if "IndexError" in error_output:
                return "索引越界：列表/字符串索引超出范围，需要添加边界检查"
            if "AttributeError" in error_output:
                return "属性错误：对象没有指定属性，请检查对象类型和方法名"
            return "运行时异常：请根据具体错误信息检查代码逻辑"

        if category == ErrorCategory.ASSERTION:
            return "断言失败：测试期望值与实际返回值不一致，可能是逻辑 bug 或测试用例设计问题"

        if category == ErrorCategory.TIMEOUT:
            return "执行超时：函数可能存在死循环或性能问题，需要优化算法复杂度"

        return "未知错误类型：请检查错误输出并手动分析原因"

    def _generate_fix_suggestion(
        self,
        category: ErrorCategory,
        context: ErrorContext | None,
        error_output: str,
    ) -> str:
        """
        生成修复建议。

        Args:
            category: 错误分类
            context: 错误上下文
            error_output: 原始错误输出

        Returns:
            str: 修复建议文本
        """
        suggestions: list[str] = []

        if category == ErrorCategory.SYNTAX:
            if context and context.subtype.name == "IMPORT_ERROR":
                module = context.module_name or "目标模块"
                suggestions.append(f"1. 安装缺失模块：`pip install {module}`")
                suggestions.append("2. 检查导入语句是否正确")
                suggestions.append("3. 确认模块名大小写是否正确")
            else:
                suggestions.append("1. 检查语法错误位置（文件名:行号）")
                suggestions.append("2. 确认冒号、括号、引号配对")
                suggestions.append("3. 检查缩进是否一致")

        elif category == ErrorCategory.RUNTIME:
            if "ZeroDivisionError" in error_output:
                suggestions.append("1. 在被除数使用前添加零值检查")
                suggestions.append("2. 使用 try-except 捕获除零异常")
                suggestions.append("3. 添加测试用例覆盖除数为 0 的场景")
            elif "TypeError" in error_output:
                suggestions.append("1. 检查函数调用时的参数类型")
                suggestions.append("2. 添加类型注解和参数校验")
                suggestions.append("3. 使用 isinstance() 进行类型检查")
            elif "IndexError" in error_output:
                suggestions.append("1. 检查列表/字符串索引边界")
                suggestions.append("2. 使用 len() 或 try-except 防止越界")
                suggestions.append("3. 添加空列表/字符串的边界测试")
            else:
                suggestions.append("1. 查看完整错误堆栈定位问题")
                suggestions.append("2. 添加调试日志输出中间变量")
                suggestions.append("3. 逐步排查变量状态变化")

        elif category == ErrorCategory.ASSERTION:
            suggestions.append("1. 检查被测函数的实际返回值")
            suggestions.append("2. 确认测试用例的预期值是否正确")
            suggestions.append("3. 检查是否存在浮点数精度问题")
            suggestions.append("4. 考虑使用 pytest.approx() 处理浮点比较")

        elif category == ErrorCategory.TIMEOUT:
            suggestions.append("1. 检查是否存在无限循环")
            suggestions.append("2. 优化算法复杂度（考虑使用更高效的数据结构）")
            suggestions.append("3. 添加递归深度限制或使用迭代代替递归")
            suggestions.append("4. 考虑使用超时装饰器隔离慢函数")

        else:
            suggestions.append("1. 仔细分析错误输出信息")
            suggestions.append("2. 检查代码逻辑是否符合预期")
            suggestions.append("3. 添加更多调试信息辅助定位")

        return "\n".join(suggestions)

    def _parse_failed_cases(self, error_output: str) -> list[dict[str, Any]]:
        """
        从错误输出中解析失败的测试用例。

        Args:
            error_output: 测试执行错误输出

        Returns:
            list[dict]: 失败用例列表，每个字典包含 name 和 error 字段
        """
        cases: list[dict[str, Any]] = []
        lines = error_output.split("\n")

        current_case: dict[str, str] = {}
        for line in lines:
            # 匹配 FAILED 测试用例
            if "FAILED" in line and "[" in line:
                if current_case:
                    cases.append(current_case)
                # 提取用例名
                match = re.search(r"FAILED\s+(\S+)", line)
                if match:
                    current_case = {"name": match.group(1)}
                else:
                    current_case = {"name": "unknown"}
            # 匹配错误详情
            elif current_case and ("AssertionError" in line or "Error" in line):
                current_case["error"] = line.strip()

        if current_case:
            cases.append(current_case)

        return cases

    def save_report(
        self,
        report: ErrorReport,
        output_dir: str = "reports",
        format: ReportFormat = ReportFormat.TEXT,
    ) -> Path:
        """
        保存报告到文件。

        Args:
            report: 要保存的报告对象
            output_dir: 输出目录
            format: 输出格式

        Returns:
            Path: 报告文件路径
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{report.task_id}_{timestamp}"

        if format == ReportFormat.JSON:
            filepath = output_path / f"{filename}.json"
            filepath.write_text(report.to_json(), encoding="utf-8")
        elif format == ReportFormat.MARKDOWN:
            filepath = output_path / f"{filename}.md"
            filepath.write_text(report.to_markdown(), encoding="utf-8")
        else:
            filepath = output_path / f"{filename}.txt"
            filepath.write_text(report.to_text(), encoding="utf-8")

        return filepath


# 模块级单例
_report_generator: ReportGenerator | None = None


def get_report_generator() -> ReportGenerator:
    """
    获取报告生成器单例。

    Returns:
        ReportGenerator: 报告生成器实例
    """
    global _report_generator
    if _report_generator is None:
        _report_generator = ReportGenerator()
    return _report_generator
