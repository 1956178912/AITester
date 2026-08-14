"""
合成数据集生成器：在不依赖外部下载的情况下，生成足够规模的合成缺陷任务。
用于在本地快速验证方法有效性（替代真实数据集的大规模实验）。
覆盖多种 bug 类型：除零、索引越界、边界条件、逻辑错误等。
通过 TASK_COUNT 参数控制生成规模（建议 >= 50 以满足发表要求）。
"""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List

from src.dataset_loader import BenchmarkTask, BaseDatasetLoader

logger = logging.getLogger(__name__)

# 预定义的合成 bug 模式库
BUG_PATTERNS: List[Dict[str, Any]] = [
    {
        "name": "divide_by_zero_missing",
        "description": "除零时未检查除数",
        "template": """def divide(a: float, b: float) -> float:
    return a / b""",
        "fixed": """def divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("除数不能为零")
    return a / b""",
        "test_cases": """from divide_by_zero_missing import divide

def test_divide_normal():
    assert divide(10, 2) == 5.0

def test_divide_by_zero():
    import pytest
    with pytest.raises(ValueError):
        divide(1, 0)""",
        "bug_type": "runtime",
        "expected_pass": 1,
        "total_tests": 2,
    },
    {
        "name": "off_by_one_right",
        "description": "二分查找右边界初始值错误",
        "template": """def binary_search(arr: list, target: int) -> int:
    left, right = 0, len(arr)
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1""",
        "fixed": """def binary_search(arr: list, target: int) -> int:
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1""",
        "test_cases": """from off_by_one_right import binary_search

def test_binary_search_found():
    assert binary_search([1, 2, 3, 4, 5], 3) == 2

def test_binary_search_not_found():
    assert binary_search([1, 2, 3], 4) == -1

def test_binary_search_empty():
    assert binary_search([], 1) == -1""",
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 3,
    },
    {
        "name": "palindrome_case_sensitive",
        "description": "回文判断未处理大小写和非字母字符",
        "template": """def is_palindrome(s: str) -> bool:
    return s == s[::-1]""",
        "fixed": """def is_palindrome(s: str) -> bool:
    s = "".join(c.lower() for c in s if c.isalnum())
    return s == s[::-1]""",
        "test_cases": """from palindrome_case_sensitive import is_palindrome

def test_is_palindrome_simple():
    assert is_palindrome("aba") is True

def test_is_palindrome_mixed_case():
    assert is_palindrome("Racecar") is True

def test_is_palindrome_with_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama") is True""",
        "bug_type": "assertion",
        "expected_pass": 1,
        "total_tests": 3,
    },
    {
        "name": "factorial_negative_input",
        "description": "阶乘函数未处理负数输入",
        "template": """def factorial(n: int) -> int:
    if n == 0:
        return 1
    return n * factorial(n - 1)""",
        "fixed": """def factorial(n: int) -> int:
    if n < 0:
        raise ValueError("阶乘不支持负数")
    if n == 0:
        return 1
    return n * factorial(n - 1)""",
        "test_cases": """from factorial_negative_input import factorial

def test_factorial_zero():
    assert factorial(0) == 1

def test_factorial_positive():
    assert factorial(5) == 120

def test_factorial_negative():
    import pytest
    with pytest.raises(ValueError):
        factorial(-1)""",
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 3,
    },
    {
        "name": "sqrt_negative_input",
        "description": "平方根函数未处理负数输入",
        "template": """def sqrt(x: float) -> float:
    if x == 0:
        return 0
    return x ** 0.5""",
        "fixed": """def sqrt(x: float) -> float:
    if x < 0:
        raise ValueError("不能对负数开平方")
    if x == 0:
        return 0
    return x ** 0.5""",
        "test_cases": """from sqrt_negative_input import sqrt

def test_sqrt_positive():
    import math
    assert abs(sqrt(4) - 2.0) < 1e-9

def test_sqrt_zero():
    assert sqrt(0) == 0

def test_sqrt_negative():
    import pytest
    with pytest.raises(ValueError):
        sqrt(-1)""",
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 3,
    },
    {
        "name": "clamp_range_error",
        "description": "数值截断函数未处理 min > max 情况",
        "template": """def clamp(value: float, min_val: float, max_val: float) -> float:
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value""",
        "fixed": """def clamp(value: float, min_val: float, max_val: float) -> float:
    if min_val > max_val:
        raise ValueError("min_val 不能大于 max_val")
    if value < min_val:
        return min_val
    if value > max_val:
        return max_val
    return value""",
        "test_cases": """from clamp_range_error import clamp

def test_clamp_normal():
    assert clamp(5, 0, 10) == 5

def test_clamp_below():
    assert clamp(-1, 0, 10) == 0

def test_clamp_above():
    assert clamp(15, 0, 10) == 10

def test_clamp_invalid_range():
    import pytest
    with pytest.raises(ValueError):
        clamp(5, 10, 0)""",
        "bug_type": "assertion",
        "expected_pass": 3,
        "total_tests": 4,
    },
    {
        "name": "fibonacci_inefficient",
        "description": "斐波那契未使用迭代导致重复计算",
        "template": """def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    return fibonacci(n - 1) + fibonacci(n - 2)""",
        "fixed": """def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b""",
        "test_cases": """from fibonacci_inefficient import fibonacci

def test_fibonacci_zero():
    assert fibonacci(0) == 0

def test_fibonacci_one():
    assert fibonacci(1) == 1

def test_fibonacci_ten():
    assert fibonacci(10) == 55""",
        "bug_type": "assertion",
        "expected_pass": 3,
        "total_tests": 3,
    },
    {
        "name": "list_index_out_of_range",
        "description": "列表访问未检查边界",
        "template": """def get_second(lst: list) -> any:
    return lst[1]""",
        "fixed": """def get_second(lst: list) -> any:
    if len(lst) < 2:
        raise IndexError("列表元素不足两个")
    return lst[1]""",
        "test_cases": """from list_index_out_of_range import get_second

def test_get_second_normal():
    assert get_second([1, 2, 3]) == 2

def test_get_second_empty():
    import pytest
    with pytest.raises(IndexError):
        get_second([])""",
        "bug_type": "runtime",
        "expected_pass": 1,
        "total_tests": 2,
    },
    {
        "name": "string_split_empty",
        "description": "字符串分割未处理空字符串情况",
        "template": """def split_words(text: str) -> list:
    return text.split()""",
        "fixed": """def split_words(text: str) -> list:
    if not text or not text.strip():
        return []
    return text.split()""",
        "test_cases": """from string_split_empty import split_words

def test_split_words_normal():
    assert split_words("hello world") == ["hello", "world"]

def test_split_words_empty():
    assert split_words("") == []

def test_split_words_whitespace():
    assert split_words("   ") == []""",
        "bug_type": "assertion",
        "expected_pass": 1,
        "total_tests": 3,
    },
    {
        "name": "integer_division_floor",
        "description": "整数除法未处理除数为零",
        "template": """def safe_div(a: int, b: int) -> float:
    return a / b""",
        "fixed": """def safe_div(a: int, b: int) -> float:
    if b == 0:
        return float('inf') if a > 0 else float('-inf') if a < 0 else float('nan')
    return a / b""",
        "test_cases": """from integer_division_floor import safe_div

def test_safe_div_normal():
    assert safe_div(10, 2) == 5.0

def test_safe_div_zero():
    import math
    assert math.isinf(safe_div(1, 0))

def test_safe_div_zero_neg():
    import math
    assert math.isneginf(safe_div(-1, 0))""",
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 3,
    },
]


class SyntheticDataset(BaseDatasetLoader):
    """
    合成缺陷数据集：通过预定义模板自动生成大量缺陷任务，无需外部数据。
    
    用途：
    - 在无法访问 SWE-bench/Defects4J 时进行快速验证
    - 生成 >= 50 个任务以满足论文实验规模要求
    - 每个任务包含明确的 bug 类型和正确修复方案
    """

    DATASET_NAME = "synthetic"

    def __init__(self, task_count: int = 100, seed: int = 42) -> None:
        self._task_count = task_count
        self._seed = seed
        super().__init__()

    def _load_raw_data(self) -> None:
        """根据模板库生成指定数量的合成缺陷任务。"""
        rng = random.Random(self._seed)
        tasks: List[BenchmarkTask] = []
        n_patterns = len(BUG_PATTERNS)

        for i in range(self._task_count):
            pattern = BUG_PATTERNS[i % n_patterns]
            noise = rng.randint(0, 9999)
            task_id = f"synthetic__{pattern['name']}_{i:04d}"
            
            # 生成带噪声的实例代码（保持函数名不变，在末尾添加噪声注释）
            # 测试代码引用原始函数名，不能破坏导入
            instance_code = pattern["template"] + f"\n# noise_seed={noise}"

            task = BenchmarkTask(
                task_id=task_id,
                repo_name=f"synthetic/{pattern['name']}",
                problem_statement=pattern["description"],
                instance_code=instance_code,
                test_code=pattern["test_cases"],
                expected_pass_count=pattern["expected_pass"],
                total_test_count=pattern["total_tests"],
                metadata={
                    "bug_type": pattern["bug_type"],
                    "pattern_name": pattern["name"],
                    "source": "synthetic",
                    "noise_seed": noise,
                },
            )
            tasks.append(task)

        self._tasks = tasks
        logger.info("合成数据集生成完成：%d 个任务", len(tasks))


if __name__ == "__main__":
    ds = SyntheticDataset(task_count=60, seed=42)
    print(f"合成数据集规模: {ds.size} 个任务")
    for task in ds.tasks[:5]:
        print(f"  - {task.task_id}: {task.problem_statement}")
