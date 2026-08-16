"""
错误分类器模块：将测试失败原因归类为五类错误。

分类优先级：SYNTAX > RUNTIME > ASSERTION > TIMEOUT > UNKNOWN
使用正则规则匹配而非 LLM，确保分类速度快且结果稳定。
分类结果用于指导 Debugger 选择合适的修复策略。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import List


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

    # 语法/编译错误关键字模式：这类错误无需语义分析，直接重写即可
    _SYNTAX_PATTERNS = [
        r"SyntaxError",
        r"ImportError",
        r"ModuleNotFoundError",
        r"IndentationError",
        r"TabError",
        r"IncompleteInput",
        r"cannot import name",
        r"No module named",
        # pytest 格式：E   path/file.py:line:col: syntax error
        r"E\s*\S+\.py:\d+:\d+:\s*syntax error",
    ]

    # 运行时异常关键字模式：需分析异常来源，可能涉及代码修复
    _RUNTIME_PATTERNS = [
        r"ZeroDivisionError",
        r"TypeError",
        r"ValueError",
        r"KeyError",
        r"IndexError",
        r"AttributeError",
        r"RecursionError",
        r"NameError",
        # TypeError 的常见子类型描述
        r"TypeError.*not support",
        r"TypeError.*takes\s+\d+\s+positional",
    ]

    # 断言失败关键字模式：期望值不匹配，需调整测试或代码逻辑
    _ASSERTION_PATTERNS = [
        r"AssertionError",
        r"assert\s+",
        r"Expected.*but got",
        r"assert\s+\w+\s*==",
        r"Expected exception",
    ]

    # 超时时标模式：通常说明被测函数存在死循环或无限递归
    _TIMEOUT_PATTERNS = [
        r"timeout",
        r"TimedOut",
        r"Test ran for longer than",
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

        # 优先检查语法错误（这类错误无需语义分析，直接重写生成即可）
        if self._matches_patterns(combined, self._SYNTAX_PATTERNS):
            return ErrorCategory.SYNTAX

        # 检查运行时异常（需要分析异常来源，可能涉及代码修复）
        if self._matches_patterns(combined, self._RUNTIME_PATTERNS):
            return ErrorCategory.RUNTIME

        # 检查断言失败（期望值不匹配，需调整测试或代码逻辑）
        if self._matches_patterns(combined, self._ASSERTION_PATTERNS):
            return ErrorCategory.ASSERTION

        # 检查超时（通常说明被测函数存在死循环）
        if self._matches_patterns(combined, self._TIMEOUT_PATTERNS):
            return ErrorCategory.TIMEOUT

        # 默认返回 UNKNOWN，由 Debugger 自行判断
        return ErrorCategory.UNKNOWN

    @staticmethod
    def _matches_patterns(text: str, patterns: List[str]) -> bool:
        """
        在文本中逐一尝试正则模式匹配。
        使用 re.IGNORECASE 进行大小写不敏感匹配，兼容不同 pytest 版本输出格式。

        Args:
            text: 待匹配的文本。
            patterns: 正则模式列表。

        Returns:
            存在任意匹配时返回 True。
        """
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False


def get_fix_strategy(category: ErrorCategory) -> str:
    """
    根据错误类型返回推荐修复策略描述。

    不同错误类型需要不同的修复策略：
    - SYNTAX：代码无法编译，需重写整个文件
    - RUNTIME：需分析异常栈，修复 bug 所在函数
    - ASSERTION：需判断是代码错还是测试预期值错
    - TIMEOUT：需添加循环/递归终止条件
    - UNKNOWN：通用分析，由 LLM 自行判断

    Args:
        category: 已分类的错误类型。

    Returns:
        针对该错误类型的修复策略文字描述，供 Debugger prompt 使用。
    """
    strategies = {
        # 语法错误：代码无法编译，直接让 LLM 重新生成完整文件
        ErrorCategory.SYNTAX: (
            "检测到语法/编译错误（如 ImportError、SyntaxError）。"
            "请重新生成完整的修复后代码文件，确保所有 import 语句正确、"
            "缩进和语法符合 Python 规范。不要只修改单个函数，"
            "而是输出包含所有函数和 import 的完整文件代码。"
        ),
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
