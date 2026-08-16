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


class ErrorPatterns:
    """
    错误分类正则表达式常量类。

    将所有预编译的正则表达式统一存储在此类中，便于维护和扩展。
    每个模式都已预编译为 re.Pattern 对象，避免重复编译开销。
    """

    # 语法/编译错误关键字模式
    SYNTAX = [
        re.compile(r"SyntaxError", re.IGNORECASE),
        re.compile(r"ImportError", re.IGNORECASE),
        re.compile(r"ModuleNotFoundError", re.IGNORECASE),
        re.compile(r"IndentationError", re.IGNORECASE),
        re.compile(r"TabError", re.IGNORECASE),
        re.compile(r"IncompleteInput", re.IGNORECASE),
        re.compile(r"cannot import name", re.IGNORECASE),
        re.compile(r"No module named", re.IGNORECASE),
        # pytest 格式：E   path/file.py:line:col: syntax error
        re.compile(r"E\s*\S+\.py:\d+:\d+:\s*syntax error", re.IGNORECASE),
    ]

    # 运行时异常关键字模式
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
    ]

    # 断言失败关键字模式
    ASSERTION = [
        re.compile(r"AssertionError", re.IGNORECASE),
        re.compile(r"assert\s+", re.IGNORECASE),
        re.compile(r"Expected.*but got", re.IGNORECASE),
        re.compile(r"assert\s+\w+\s*==", re.IGNORECASE),
        re.compile(r"Expected exception", re.IGNORECASE),
    ]

    # 超时时标模式
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
        (ErrorCategory.SYNTAX, ErrorPatterns.SYNTAX),
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
