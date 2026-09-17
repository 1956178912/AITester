"""
内置示例数据集（InMemoryDataset）。

拆分自 dataset_loader.py（结构优化轮次）：示例任务定义独立成模块，
dataset_loader.py 经 re-export 维持 `from src.datasets.dataset_loader import InMemoryDataset` 的旧导入路径。

适用于离线环境和单元测试，无需外部下载。
"""

from __future__ import annotations

from typing import Any

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask


class InMemoryDataset(BaseDatasetLoader):
    """
    内置示例数据集：无需外部下载，直接提供用于快速验证的测试任务。

    适用于离线环境和单元测试。
    """

    DATASET_NAME = "in_memory"

    def __init__(self, subset: str | None = None, **kwargs: Any) -> None:
        """
        初始化内置示例数据集。

        Args:
            subset: 数据子集名称（保留接口兼容，实际忽略；本数据集无子集概念）。
            **kwargs: 兼容 load_dataset 工厂传递的额外参数（本数据集忽略）。
        """
        super().__init__(subset=subset)

    def _load_raw_data(self) -> None:
        # InMemoryDataset 的数据由 add_sample_tasks() 手动填充，
        # 无需从外部文件读取，因此此处留空。子类覆盖此方法以加载真实数据集。
        return None

    def add_task(self, task: BenchmarkTask) -> None:
        """手动添加一个任务到数据集。"""
        self._tasks.append(task)

    def add_sample_tasks(self) -> None:
        """添加一组预定义的示例任务（用于快速验证）。"""
        self.add_task(
            BenchmarkTask(
                task_id="examples__calculator_divide",
                repo_name="examples/calculator",
                problem_statement="修复 divide 函数的除零 bug",
                instance_code="""\
def add(a: float, b: float) -> float:
    return a + b

def subtract(a: float, b: float) -> float:
    return a - b

def multiply(a: float, b: float) -> float:
    return a * b

def divide(a: float, b: float) -> float:
    # BUG: 除零时未抛出异常
    return a / b

def factorial(n: int) -> int:
    # BUG: 负数输入会递归溢出
    if n == 0:
        return 1
    return n * factorial(n - 1)
""",
                test_code="""\
from calculator import divide, factorial
import pytest

def test_divide_by_zero():
    with pytest.raises(ValueError):
        divide(1, 0)

def test_divide_normal():
    assert divide(10, 2) == 5.0

def test_factorial_negative():
    with pytest.raises(RecursionError):
        factorial(-1)
""",
                expected_pass_count=0,
                total_test_count=3,
                metadata={"source": "examples"},
            )
        )

        self.add_task(
            BenchmarkTask(
                task_id="examples__binary_search",
                repo_name="examples/buggy_library",
                problem_statement="修复二分查找的索引越界 bug",
                instance_code="""\
def binary_search(arr: list, target: int) -> int:
    # BUG: right 初始值应为 len(arr) - 1
    left, right = 0, len(arr)
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1
        else:
            right = mid - 1
    return -1
""",
                test_code="""\
from buggy_library import binary_search

def test_binary_search_found():
    assert binary_search([1, 2, 3, 4, 5], 3) == 2

def test_binary_search_not_found():
    assert binary_search([1, 2, 3], 4) == -1

def test_binary_search_empty():
    assert binary_search([], 1) == -1
""",
                expected_pass_count=0,
                total_test_count=3,
                metadata={"source": "examples"},
            )
        )

        self.add_task(
            BenchmarkTask(
                task_id="examples__is_palindrome",
                repo_name="examples/string_utils",
                problem_statement="修复 is_palindrome 未处理大小写和非字母数字字符的 bug",
                instance_code="""\
def is_palindrome(s: str) -> bool:
    # BUG: 未过滤非字母数字字符和统一大小写
    return s == s[::-1]

def reverse_string(s: str) -> str:
    return s[::-1]
""",
                test_code="""\
from string_utils import is_palindrome

def test_is_palindrome_simple():
    assert is_palindrome("aba") is True

def test_is_palindrome_with_punctuation():
    assert is_palindrome("A man, a plan, a canal: Panama") is True

def test_is_palindrome_mixed_case():
    assert is_palindrome("Racecar") is True
""",
                expected_pass_count=0,
                total_test_count=3,
                metadata={"source": "examples"},
            )
        )

    @classmethod
    def create_with_samples(cls) -> InMemoryDataset:
        """创建并预填充示例任务的数据集实例。"""
        dataset = cls()
        dataset.add_sample_tasks()
        return dataset
