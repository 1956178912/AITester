"""
错误分类器模块：将测试失败原因归类为五类错误，并支持子类型识别。

分类优先级：SYNTAX > RUNTIME > ASSERTION > TIMEOUT > UNKNOWN
使用正则规则匹配而非 LLM，确保分类速度快且结果稳定。
分类结果用于指导 Debugger 选择合适的修复策略。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional


class ErrorCategory(Enum):
    """
    错误类型枚举，用于分层错误修复策略。

    属性:
        SYNTAX: 语法/编译错误，如导入失败、语法错误
        ASSERTION: 断言失败，期望值与实际返回值不一致
        RUNTIME: 运行时异常，如除零、类型错误、索引越界
        TIMEOUT: 执行超时
        UNKNOWN: 无法识别的错误类型
    """
    SYNTAX = "syntax"
    ASSERTION = "assertion"
    RUNTIME = "runtime"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class SyntaxSubtype(Enum):
    """
    Syntax 错误的子类型枚举，用于更精确的诊断和修复策略。

    属性:
        IMPORT_ERROR: 导入错误，如 ModuleNotFoundError、ImportError
        SYNTAX_ERROR: 语法错误，如 SyntaxError、IndentationError
        UNRECOGNIZED: 无法识别的子类型
    """
    IMPORT_ERROR = "import_error"
    SYNTAX_ERROR = "syntax_error"
    UNRECOGNIZED = "unrecognized"


@dataclass
class ErrorContext:
    """
    错误上下文数据结构，包含从错误信息中提取的关键信息。

    属性:
        filename: 出错的文件名（如 missing_module.py）
        line: 出错行号（如 42）
        column: 出错列号（如 10）
        module_name: 缺失的模块名（如 pandas）
        error_message: 完整的错误消息
        subtype: 错误子类型（仅 SYNTAX 类别有值）
    """
    filename: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    module_name: Optional[str] = None
    error_message: str = ""
    subtype: Optional[SyntaxSubtype] = None


class ErrorPatterns:
    """
    错误分类正则表达式常量类。

    将所有预编译的正则表达式统一存储在此类中，便于维护和扩展。
    每个模式都已预编译为 re.Pattern 对象，避免重复编译开销。
    """

    # ─── Syntax 子类型：Import Error 模式 ─────────────────────────────────────
    IMPORT_ERROR = [
        # ModuleNotFoundError: No module named 'xxx'
        re.compile(
            r"ModuleNotFoundError:\s*No module named\s+'(\w+)'",
            re.IGNORECASE
        ),
        # ImportError: cannot import name 'xxx' from 'yyy'
        re.compile(
            r"ImportError:\s*cannot import name\s+'(\w+)'(?:\s*from\s+'(\w+)')?",
            re.IGNORECASE
        ),
        # ImportError: cannot import name 'xxx'
        re.compile(
            r"ImportError:\s*cannot import name\s+'(\w+)'",
            re.IGNORECASE
        ),
        # ModuleNotFoundError: No module named 'xxx' (带路径)
        re.compile(
            r"ModuleNotFoundError:\s*No module named\s+'(\w+)'",
            re.IGNORECASE
        ),
    ]

    # ─── Syntax 子类型：Syntax Error 模式 ─────────────────────────────────────
    SYNTAX_ERROR = [
        # SyntaxError: invalid syntax
        re.compile(r"SyntaxError.*?(\w+\.py):?(\d+)?:?(\d+)?:?\s*(.+)"),
        # IndentationError: expected an indented block
        re.compile(r"IndentationError.*?(\w+\.py):?(\d+)?:?(\d+)?:?\s*(.+)"),
        # TabError: inconsistent use of tabs and spaces
        re.compile(r"TabError.*?(\w+\.py):?(\d+)?:?(\d+)?:?\s*(.+)"),
        # IncompleteInput
        re.compile(r"IncompleteInput.*?(\w+\.py):?(\d+)?:?(\d+)?:?\s*(.+)"),
        # pytest 格式：E   path/file.py:line:col: syntax error
        re.compile(r"E\s*\S+\.py:(\d+):(\d+):\s*syntax error", re.IGNORECASE),
        # 通用语法错误
        re.compile(r"syntax error", re.IGNORECASE),
    ]

    # ─── Syntax 通用检测模式（用于初步分类） ───────────────────────────────────
    SYNTAX_GENERIC = [
        re.compile(r"SyntaxError", re.IGNORECASE),
        re.compile(r"ImportError", re.IGNORECASE),
        re.compile(r"ModuleNotFoundError", re.IGNORECASE),
        re.compile(r"IndentationError", re.IGNORECASE),
        re.compile(r"TabError", re.IGNORECASE),
        re.compile(r"IncompleteInput", re.IGNORECASE),
        re.compile(r"cannot import name", re.IGNORECASE),
        re.compile(r"No module named", re.IGNORECASE),
    ]

    # ─── Runtime 模式 ──────────────────────────────────────────────────────────
    RUNTIME = [
        re.compile(r"ZeroDivisionError", re.IGNORECASE),
        re.compile(r"TypeError", re.IGNORECASE),
        re.compile(r"ValueError", re.IGNORECASE),
        re.compile(r"KeyError", re.IGNORECASE),
        re.compile(r"IndexError", re.IGNORECASE),
        re.compile(r"AttributeError", re.IGNORECASE),
        re.compile(r"RecursionError", re.IGNORECASE),
        re.compile(r"NameError", re.IGNORECASE),
        # TypeError 的常见子类型描述
        re.compile(r"TypeError.*not support", re.IGNORECASE),
        re.compile(r"TypeError.*takes\s+\d+\s+positional", re.IGNORECASE),
        # NameError 的子类型
        re.compile(r"NameError.*name\s+'\w+' is not defined", re.IGNORECASE),
        re.compile(r"NameError.*name\s+'\w+' is not defined", re.IGNORECASE),
    ]

    # ─── Assertion 模式 ────────────────────────────────────────────────────────
    ASSERTION = [
        re.compile(r"AssertionError", re.IGNORECASE),
        re.compile(r"assert\s+", re.IGNORECASE),
        re.compile(r"Expected.*but got", re.IGNORECASE),
        re.compile(r"assert\s+\w+\s*==", re.IGNORECASE),
        re.compile(r"Expected exception", re.IGNORECASE),
    ]

    # ─── Timeout 模式 ──────────────────────────────────────────────────────────
    TIMEOUT = [
        re.compile(r"timeout", re.IGNORECASE),
        re.compile(r"TimedOut", re.IGNORECASE),
        re.compile(r"Test ran for longer than", re.IGNORECASE),
    ]


class ErrorClassifier:
    """
    测试失败原因分类器。

    根据 pytest 输出文本判断错误类别，为 Debugger 提供结构化输入。
    使用规则匹配而非 LLM，确保分类速度快且结果稳定。

    分类优先级（由高到低）：
    1. SYNTAX - 语法错误：无需语义分析，直接让 LLM 重写整个文件
    2. RUNTIME - 运行时异常：需分析异常栈，定位 bug 所在函数
    3. ASSERTION - 断言失败：判断是代码逻辑错误还是测试预期值错误
    4. TIMEOUT - 执行超时：通常说明被测函数存在死循环
    5. UNKNOWN - 无法识别：交由 LLM 自行分析
    """

    # 错误分类优先级映射（从高到低）
    _PRIORITY_ORDER = [
        (ErrorCategory.SYNTAX, ErrorPatterns.SYNTAX_GENERIC),
        (ErrorCategory.RUNTIME, ErrorPatterns.RUNTIME),
        (ErrorCategory.ASSERTION, ErrorPatterns.ASSERTION),
        (ErrorCategory.TIMEOUT, ErrorPatterns.TIMEOUT),
    ]

    def classify(self, test_output: str, failed_cases: List[dict]) -> ErrorCategory:
        """
        根据测试输出和失败用例分类错误类型。

        分类优先级：SYNTAX > RUNTIME > ASSERTION > TIMEOUT > UNKNOWN
        规则匹配优先于 LLM 兜底分类。

        合并策略：将 test_output 和最多前 3 个 failed_cases 的 error 信息拼接后统一匹配，
        确保能从失败用例的详细错误信息中识别出错误类型。

        Args:
            test_output: pytest 完整输出文本。
            failed_cases: 失败用例列表，每项含 name 和 error 字段。

        Returns:
            最匹配的 ErrorCategory 枚举值。
        """
        # 合并 test_output 和 failed_cases 的 error 信息用于分类
        # 最多取前 3 个失败用例的错误信息，避免过长
        combined = test_output + "\n" + "\n".join(
            case.get("error", "") for case in failed_cases[:3]
        )

        # 按优先级顺序检查各类错误
        for category, patterns in self._PRIORITY_ORDER:
            if self._matches_patterns(combined, patterns):
                return category

        # 默认返回 UNKNOWN，由 Debugger 自行判断
        return ErrorCategory.UNKNOWN

    def classify_with_context(
        self, test_output: str, failed_cases: List[dict]
    ) -> tuple:
        """
        分类错误类型并提取错误上下文。

        这是 classify() 的增强版本，额外返回 ErrorContext 对象，
        包含文件名、行号、列号、缺失模块名等详细信息。

        Args:
            test_output: pytest 完整输出文本。
            failed_cases: 失败用例列表，每项含 name 和 error 字段。

        Returns:
            (category, context) 元组，category 是 ErrorCategory，
            context 是 ErrorContext 对象。
        """
        category = self.classify(test_output, failed_cases)
        context = self.extract_error_context(test_output, failed_cases)
        return category, context

    def extract_error_context(
        self, test_output: str, failed_cases: List[dict]
    ) -> ErrorContext:
        """
        提取错误上下文信息，包括文件名、行号、列号、模块名等。

        分析错误输出文本，提取关键诊断信息，帮助 Debugger 精确定位问题。

        Args:
            test_output: pytest 完整输出文本。
            failed_cases: 失败用例列表。

        Returns:
            ErrorContext 对象，包含提取的上下文信息。
        """
        # 合并所有错误信息
        combined = test_output + "\n" + "\n".join(
            case.get("error", "") for case in failed_cases
        )

        context = ErrorContext(error_message=combined[:500])  # 限制长度

        # 尝试提取模块名称（ImportError/ModuleNotFoundError）
        module_match = re.search(
            r"ModuleNotFoundError:\s*No module named\s+'(\w+)'",
            combined, re.IGNORECASE
        )
        if module_match:
            context.module_name = module_match.group(1)
            context.subtype = SyntaxSubtype.IMPORT_ERROR
            return context

        import_name_match = re.search(
            r"ImportError:\s*cannot import name\s+'(\w+)'",
            combined, re.IGNORECASE
        )
        if import_name_match:
            context.module_name = import_name_match.group(1)
            context.subtype = SyntaxSubtype.IMPORT_ERROR
            return context

        # 尝试提取文件路径、行号、列号（SyntaxError/IndentationError 等）
        # 格式：filename.py:line:col: message 或 filename.py:line: message
        file_line_match = re.search(
            r"(\w+\.py):(\d+):(\d+):\s*(.+)",
            combined
        )
        if file_line_match:
            context.filename = file_line_match.group(1)
            context.line = int(file_line_match.group(2))
            context.column = int(file_line_match.group(3))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # 格式：filename.py:line: message
        file_line_match = re.search(
            r"(\w+\.py):(\d+):\s*(.+)",
            combined
        )
        if file_line_match:
            context.filename = file_line_match.group(1)
            context.line = int(file_line_match.group(2))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # pytest 格式：E   path/file.py:line:col
        pytest_match = re.search(
            r"E\s*\S+\.py:(\d+):(\d+)",
            combined
        )
        if pytest_match:
            context.line = int(pytest_match.group(1))
            context.column = int(pytest_match.group(2))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # 尝试从 traceback 中提取文件名
        traceback_match = re.search(
            r"File\s+\"([^\"]+)\",\s*line\s+(\d+)",
            combined
        )
        if traceback_match:
            context.filename = traceback_match.group(1)
            context.line = int(traceback_match.group(2))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        return context

    @staticmethod
    def _matches_patterns(text: str, patterns: list) -> bool:
        """
        在文本中逐一尝试预编译的正则模式匹配。

        Args:
            text: 待匹配的文本。
            patterns: 已预编译的 re.Pattern 对象列表。

        Returns:
            存在任意匹配时返回 True。
        """
        for pattern in patterns:
            if pattern.search(text):
                return True
        return False


def get_fix_strategy(category: ErrorCategory, context: ErrorContext = None) -> str:
    """
    根据错误类型和上下文返回推荐修复策略描述。

    不同错误类型需要不同的修复策略：
    - SYNTAX：代码无法编译，需重写整个文件
    - RUNTIME：需分析异常栈，修复 bug 所在函数
    - ASSERTION：需判断是代码错还是测试预期值错
    - TIMEOUT：需添加循环/递归终止条件
    - UNKNOWN：通用分析，由 LLM 自行判断

    对于 SYNTAX 类型，根据子类型提供更具针对性的策略：
    - IMPORT_ERROR：建议添加缺失依赖或修复导入路径
    - SYNTAX_ERROR：建议检查语法和缩进

    Args:
        category: 已分类的错误类型。
        context: 错误上下文对象（可选），用于细化策略。

    Returns:
        针对该错误类型的修复策略文字描述，供 Debugger prompt 使用。
    """
    # SYNTAX 类型根据子类型提供不同策略
    if category == ErrorCategory.SYNTAX:
        if context and context.subtype == SyntaxSubtype.IMPORT_ERROR:
            if context.module_name:
                return (
                    f"检测到导入错误：缺少模块 '{context.module_name}'。"
                    f"请检查是否需要在 requirements.txt 中添加该依赖，"
                    f"或确认模块名称是否正确。如果模块已安装，"
                    f"请检查 Python 环境路径是否包含该模块。"
                )
            else:
                return (
                    "检测到导入错误（ImportError/ModuleNotFoundError）。"
                    "请检查是否需要安装缺失的依赖包，"
                    "或确认模块名称是否正确。"
                )
        elif context and context.subtype == SyntaxSubtype.SYNTAX_ERROR:
            location = ""
            if context.filename:
                location = f" 文件 '{context.filename}'"
            if context.line:
                location += f" 第 {context.line} 行"
            if context.column:
                location += f" 第 {context.column} 列"
            return (
                f"检测到语法错误{location}。"
                f"请检查该位置的语法是否正确，"
                f"特别关注括号匹配、缩进、逗号和冒号的使用。"
                f"重新生成完整的修复后代码文件，"
                f"确保语法符合 Python 规范。"
            )
        else:
            return (
                "检测到语法/编译错误（如 ImportError、SyntaxError）。"
                "请重新生成完整的修复后代码文件，确保所有 import 语句正确、"
                "缩进和语法符合 Python 规范。不要只修改单个函数，"
                "而是输出包含所有函数和 import 的完整文件代码。"
            )

    strategies = {
        # 运行时异常：分析异常栈，定位到具体哪行代码引发问题
        ErrorCategory.RUNTIME: (
            "检测到运行时异常（如 ZeroDivisionError、TypeError 等）。"
            "请分析异常发生的具体位置和原因，修复有 bug 的代码函数，"
            "而不是修改测试用例来绕过问题。重点关注边界条件和异常处理。"
        ),
        # 断言失败：期望值计算错误或测试用例设计有问题
        ErrorCategory.ASSERTION: (
            "检测到断言失败（期望值与实际返回值不一致）。"
            "请先判断是代码逻辑错误还是测试用例的预期值错误。"
            "如果代码实现与函数签名/文档字符串描述不符，修复代码；"
            "如果测试用例的预期值不符合函数实际行为，修正测试用例的预期值。"
        ),
        # 超时：死循环或无限递归
        ErrorCategory.TIMEOUT: (
            "检测到执行超时，通常意味着存在死循环或无限递归。"
            "请检查函数中的循环条件和递归终止条件，添加适当的边界检查和退出条件。"
        ),
        # 未知类型：让 LLM 自行分析
        ErrorCategory.UNKNOWN: (
            "错误类型未能自动识别。请仔细分析测试输出，"
            "判断是代码逻辑错误、测试用例问题还是环境问题，"
            "然后给出相应的修复方案。"
        ),
    }
    return strategies.get(category, strategies[ErrorCategory.UNKNOWN])
