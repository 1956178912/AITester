"""
示例被测代码：简易计算器模块，包含若干典型 bug 用于演示 AITester 的修复能力。
"""


def add(a: float, b: float) -> float:
    """返回两数之和。"""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字类型")
    return a + b


def subtract(a: float, b: float) -> float:
    """返回两数之差。"""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字类型")
    return a - b


def multiply(a: float, b: float) -> float:
    """返回两数之积。"""
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字类型")
    return a * b


def divide(a: float, b: float) -> float:
    """
    返回两数之商。
    注意：当前实现存在除零 bug（应抛出 ValueError）。
    """
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        raise TypeError("参数必须是数字类型")
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b


def factorial(n: int) -> int:
    """
    返回 n 的阶乘。
    注意：当前实现存在负数处理 bug。
    """
    if not isinstance(n, int):
        raise TypeError("参数必须是整数")
    if n < 0:
        raise ValueError("负数没有阶乘")
    if n == 0:
        return 1
    return n * factorial(n - 1)
