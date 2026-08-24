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
    - binary_search: 二分查找（补充缺失函数）
    - count_vowels: 统计字符串中元音字母数量
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


def binary_search(arr: list, target) -> int:
    """在有序列表 arr 中二分查找 target，返回其索引；若不存在则返回 -1。

    Args:
        arr: 已按升序排列的列表。
        target: 要查找的目标值。

    Returns:
        target 在 arr 中的索引，不存在时返回 -1。
    """
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1


def count_vowels(text: str) -> int:
    """统计字符串中元音字母（a, e, i, o, u，不区分大小写）的数量。

    Args:
        text: 待统计的字符串。

    Returns:
        元音字母的个数。
    """
    vowels = set("aeiouAEIOU")
    return sum(1 for char in text if char in vowels)
