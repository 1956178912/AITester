"""
示例被测代码：简易计算器模块，包含若干典型 bug 用于演示 AITester 的修复能力。
"""


def add(a: float, b: float) -> float:
    """返回两数之和。"""
    return a + b


def subtract(a: float, b: float) -> float:
    """返回两数之差。"""
    return a - b


def multiply(a: float, b: float) -> float:
    """返回两数之积。"""
    return a * b


def divide(a: float, b: float) -> float:
    """
    返回两数之商。
    BUG: 除零时未抛出异常，而是返回浮点数 inf，应抛出 ValueError。
    """
    # BUG: b == 0 时应抛出 ValueError，但当前直接除法会得到 inf
    return a / b


def factorial(n: int) -> int:
    """
    返回 n 的阶乘。
    BUG: 负数输入未做处理，会递归导致 RecursionError。
    """
    # BUG: 负数输入未检查，递归到系统栈溢出
    if n == 0:
        return 1
    return n * factorial(n - 1)
