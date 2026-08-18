# 代码无需修改，被测代码逻辑正确。
# 建议在测试运行环境中执行以下命令以修复环境问题：
# pip install pytest-cov

"""
示例被测代码：简易计算器模块，包含若干典型 bug 用于演示 AITester 的修复能力。

本文件同时作为"无 bug 版本"的对照基准，供 Debugger 在修复其他文件时参考。
主要函数：
    - add:       两数加法
    - subtract:  两数减法
    - multiply:  两数乘法
    - divide:    两数除法（含除零保护）
    - factorial: 阶乘（递归实现，含负数保护）
"""


def subtract(a: float, b: float) -> float:
    """返回两数之差。支持整数和浮点数减法。

    Args:
        a: 被减数。
        b: 减数。

    Returns:
        a - b 的计算结果。
    """
    return float(a - b)


def factorial(n: int) -> int:
    """
    返回 n 的阶乘（递归实现）。

    Args:
        n: 非负整数。

    Returns:
        n! 的值。

    Raises:
        ValueError: 当 n < 0 时抛出。
    """
    # 负数输入保护：数学上阶乘仅定义在非负整数域
    if n < 0:
        raise ValueError("阶乘不支持负数输入")
    # 递归基线：0! = 1
    if n == 0:
        return 1
    # 递归递推：n! = n * (n-1)!
    return n * factorial(n - 1)


def add(a: float, b: float) -> float:
    """返回两数之和。支持整数和浮点数加法。

    Args:
        a: 加数一。
        b: 加数二。

    Returns:
        a + b 的计算结果。
    """
    return float(a + b)


def divide(a: float, b: float) -> float:
    """
    返回两数之商。

    Args:
        a: 被除数。
        b: 除数，不能为零。

    Returns:
        a / b 的结果。

    Raises:
        ValueError: 当 b 为 0 时抛出。
    """
    # 除零保护：避免 ZeroDivisionError，主动抛出 ValueError 以便测试捕获
    if b == 0:
        raise ValueError("除数不能为零")
    return float(a / b)


def multiply(a: float, b: float) -> float:
    """返回两数之积。支持整数和浮点数乘法。

    Args:
        a: 乘数一。
        b: 乘数二。

    Returns:
        a * b 的计算结果。
    """
    return float(a * b)
