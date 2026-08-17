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


# ─── 预编译正则表达式（避免重复编译开销）─────────────────────────────────────
# Import Error 检测模式
_RE_MODULE_NOT_FOUND = re.compile(
    r"ModuleNotFoundError:\s*No module named\s+'(\w+)'",
    re.IGNORECASE
)
_RE_IMPORT_ERROR = re.compile(
    r"ImportError:\s*cannot import name\s+'(\w+)'",
    re.IGNORECASE
)
# Syntax Error 检测模式
_RE_SYNTAX_ERROR_FILE_LINE = re.compile(
    r"(\w+\.py):(\d+):(\d+):\s*(.+)"
)
_RE_PYTEST_SYNTAX = re.compile(
    r"E\s*\S+\.py:(\d+):(\d+)",
    re.IGNORECASE
)
_RE_TRACEBACK = re.compile(
    r'File\s+"([^"]+)",\s*line\s+(\d+)'
)
# Runtime Error 检测模式
_RE_RUNTIME_ERRORS = [
    re.compile(r"ZeroDivisionError", re.IGNORECASE),
    re.compile(r"TypeError", re.IGNORECASE),
    re.compile(r"ValueError", re.IGNORECASE),
    re.compile(r"KeyError", re.IGNORECASE),
    re.compile(r"IndexError", re.IGNORECASE),
    re.compile(r"AttributeError", re.IGNORECASE),
    re.compile(r"RecursionError", re.IGNORECASE),
    re.compile(r"NameError", re.IGNORECASE),
]
# Assertion Error 检测模式
_RE_ASSERTION_ERRORS = [
    re.compile(r"AssertionError", re.IGNORECASE),
    re.compile(r"assert\s+", re.IGNORECASE),
    re.compile(r"Expected.*but got", re.IGNORECASE),
]
# Timeout Error 检测模式
_RE_TIMEOUT_ERRORS = [
    re.compile(r"timeout", re.IGNORECASE),
    re.compile(r"TimedOut", re.IGNORECASE),
    re.compile(r"Test ran for longer than", re.IGNORECASE),
]
# ───────────────────────────────────────────────────────────────────────────


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
        # 1. 检查 Syntax 错误
        if self._is_syntax_error(combined):
            return ErrorCategory.SYNTAX
        # 2. 检查 Runtime 错误
        if self._is_runtime_error(combined):
            return ErrorCategory.RUNTIME
        # 3. 检查 Assertion 错误
        if self._is_assertion_error(combined):
            return ErrorCategory.ASSERTION
        # 4. 检查 Timeout 错误
        if self._is_timeout_error(combined):
            return ErrorCategory.TIMEOUT
        
        # 默认返回 UNKNOWN
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

        # 清理错误消息：去除首尾空白，避免空消息包含换行符
        cleaned_message = combined.strip()[:500]
        context = ErrorContext(error_message=cleaned_message)

        # 尝试提取模块名称（ImportError/ModuleNotFoundError）
        module_match = _RE_MODULE_NOT_FOUND.search(combined)
        if module_match:
            context.module_name = module_match.group(1)
            context.subtype = SyntaxSubtype.IMPORT_ERROR
            return context

        import_name_match = _RE_IMPORT_ERROR.search(combined)
        if import_name_match:
            context.module_name = import_name_match.group(1)
            context.subtype = SyntaxSubtype.IMPORT_ERROR
            return context

        # 尝试提取文件路径、行号、列号（SyntaxError/IndentationError 等）
        file_line_match = _RE_SYNTAX_ERROR_FILE_LINE.search(combined)
        if file_line_match:
            context.filename = file_line_match.group(1)
            context.line = int(file_line_match.group(2))
            context.column = int(file_line_match.group(3))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # pytest 格式：E   path/file.py:line:col
        pytest_match = _RE_PYTEST_SYNTAX.search(combined)
        if pytest_match:
            context.line = int(pytest_match.group(1))
            context.column = int(pytest_match.group(2))
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        # 尝试从 traceback 中提取文件名
        # 使用 findall 获取所有匹配，取最后一个（最深的调用栈）
        traceback_matches = _RE_TRACEBACK.findall(combined)
        if traceback_matches:
            # 取最后一个匹配（最深处的文件）
            context.filename = traceback_matches[-1][0]
            context.line = int(traceback_matches[-1][1])
            context.subtype = SyntaxSubtype.SYNTAX_ERROR
            return context

        return context

    @staticmethod
    def _is_syntax_error(text: str) -> bool:
        """检查是否为 Syntax 错误（导入错误或语法错误）。"""
        # 检查导入错误
        if _RE_MODULE_NOT_FOUND.search(text) or _RE_IMPORT_ERROR.search(text):
            return True
        # 检查语法错误关键词
        syntax_keywords = ['SyntaxError', 'ImportError', 'ModuleNotFoundError',
                          'IndentationError', 'TabError', 'IncompleteInput']
        if any(kw in text for kw in syntax_keywords):
            return True
        # 检查 pytest 冒号格式：file.py:line:col: error
        if _RE_SYNTAX_ERROR_FILE_LINE.search(text):
            return True
        # 检查 E prefix 格式：E   file.py:line:col
        if _RE_PYTEST_SYNTAX.search(text):
            return True
        return False

    @staticmethod
    def _is_runtime_error(text: str) -> bool:
        """检查是否为 Runtime 错误。"""
        return any(pattern.search(text) for pattern in _RE_RUNTIME_ERRORS)

    @staticmethod
    def _is_assertion_error(text: str) -> bool:
        """检查是否为 Assertion 错误。"""
        return any(pattern.search(text) for pattern in _RE_ASSERTION_ERRORS)

    @staticmethod
    def _is_timeout_error(text: str) -> bool:
        """检查是否为 Timeout 错误。"""
        return any(pattern.search(text) for pattern in _RE_TIMEOUT_ERRORS)


def get_fix_strategy(category: ErrorCategory, context: ErrorContext = None) -> str:
    """
    根据错误类型和上下文返回推荐修复策略描述。

    不同错误类型需要不同的修复策略：
    - SYNTAX：代码无法编译，需重写整个文件
    - RUNTIME：需分析异常栈，定位 bug 所在函数
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
