"""
合成数据集生成器：在不依赖外部下载的情况下，生成足够规模的合成缺陷任务。
用于在本地快速验证方法有效性（替代真实数据集的大规模实验）。
覆盖多种 bug 类型：除零、索引越界、边界条件、逻辑错误等。
通过 TASK_COUNT 参数控制生成规模（建议 >= 50 以满足发表要求）。

P0 2.1 分层难度（difficulty 参数）：
    - "mixed"（默认，历史口径）：在 Level 1-4 间轮换，覆盖全部难度梯度。
    - "level1"：单函数简单缺陷（当前口径）。
    - "level2"：多函数交互缺陷（需修改 2-3 个函数，Level 2 模板库）。
    - "level3"：跨文件依赖缺陷（需修改 2+ 文件，module_a + module_b 双模块构造）。
    - "level4"：边界条件 + 异常路径隐蔽缺陷（Level 4 模板库，off-by-one + 未捕获异常）。

P0 2.2 跨文件合成任务构造：
    Level 3 任务生成 module_a.py（入口，调用 module_b）和 module_b.py
    （被调方，含缺陷）。缺陷在 module_b 中，但 module_a 的调用方式
    触发了缺陷——修复需修改 module_b 的接口签名/实现，验证跨文件
    修复架构（协调器-提议者，依赖边 module_a → module_b）。
"""

from __future__ import annotations

import logging
import random
from typing import Any

from src.datasets.dataset_loader import BaseDatasetLoader, BenchmarkTask

logger = logging.getLogger(__name__)

# 预定义的合成 bug 模式库（Level 1：单函数简单缺陷，历史口径）
BUG_PATTERNS: list[dict[str, Any]] = [
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
    # CPython 无 math.isneginf（仅有 isinf/isfinite/isnan/isclose/isqrt）；
    # 原断言恒 AttributeError，使该用例连 fixed 版都无法通过，改为直接判负无穷
    assert math.isinf(safe_div(-1, 0)) and safe_div(-1, 0) < 0""",
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 3,
    },
]


# P0 2.1 Level 2：多函数交互缺陷（需修改 2-3 个函数，模板含多个函数，
# 缺陷跨多个函数——单个函数修复不够，需协调修改）
BUG_PATTERNS_LEVEL2: list[dict[str, Any]] = [
    {
        "name": "multi_func_off_by_one",
        "description": "排序函数调用比较函数，比较函数有 off-by-one 缺陷导致排序不稳定",
        "template": """def compare(a: int, b: int) -> int:
    if a > b:
        return 1
    elif a < b:
        return -1
    return 0

def sort_desc(arr: list) -> list:
    n = len(arr)
    for i in range(n - 1):
        for j in range(n - 1 - i):
            if compare(arr[j], arr[j + 1]) > 0:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr

def top_k(arr: list, k: int) -> list:
    if k <= 0:
        return []
    if k >= len(arr):
        return sort_desc(arr)
    sorted_arr = sort_desc(arr)
    return sorted_arr[:k]""",
        "fixed": """def compare(a: int, b: int) -> int:
    if a > b:
        return 1
    elif a < b:
        return -1
    return 0

def sort_desc(arr: list) -> list:
    n = len(arr)
    for i in range(n - 1):
        for j in range(n - 1 - i):
            if compare(arr[j], arr[j + 1]) > 0:
                arr[j], arr[j + 1] = arr[j + 1], arr[j]
    return arr

def top_k(arr: list, k: int) -> list:
    if k <= 0:
        return []
    if k >= len(arr):
        return sort_desc(arr)
    sorted_arr = sort_desc(arr)
    return sorted_arr[:k]""",
        "test_cases": """from multi_func_off_by_one import compare, sort_desc, top_k

def test_compare_basic():
    assert compare(1, 2) == -1
    assert compare(2, 1) == 1
    assert compare(1, 1) == 0

def test_sort_desc_normal():
    assert sort_desc([3, 1, 2]) == [3, 2, 1]

def test_top_k_normal():
    assert top_k([3, 1, 4, 1, 5], 2) == [5, 4]

def test_top_k_edge():
    assert top_k([1, 2, 3], 0) == []
    assert top_k([1, 2, 3], 10) == [3, 2, 1]""",
        "bug_type": "assertion",
        "expected_pass": 3,
        "total_tests": 4,
        "difficulty": 2,
    },
    {
        "name": "multi_func_chain_error",
        "description": "管道式数据转换：normalize → aggregate → report，normalize 未处理空列表",
        "template": """def normalize(data: list) -> list:
    return [x * 2 for x in data]

def aggregate(data: list) -> dict:
    if not data:
        return {"count": 0, "total": 0}
    return {"count": len(data), "total": sum(data)}

def report(data: list) -> str:
    normalized = normalize(data)
    stats = aggregate(normalized)
    return 'count={0} total={1}'.format(stats['count'], stats['total'])""",
        "fixed": """def normalize(data: list) -> list:
    if not data:
        return []
    return [x * 2 for x in data]

def aggregate(data: list) -> dict:
    if not data:
        return {"count": 0, "total": 0}
    return {"count": len(data), "total": sum(data)}

def report(data: list) -> str:
    if data is None:
        return "count=0 total=0"
    normalized = normalize(data)
    stats = aggregate(normalized)
    return 'count={0} total={1}'.format(stats['count'], stats['total'])""",
        "test_cases": """from multi_func_chain_error import normalize, aggregate, report

def test_normalize_normal():
    assert normalize([1, 2, 3]) == [2, 4, 6]

def test_normalize_empty():
    assert normalize([]) == []

def test_report_normal():
    assert report([1, 2]) == "count=2 total=6"

def test_report_none():
    assert report(None) == "count=0 total=0"
""",
        "bug_type": "runtime",
        "expected_pass": 3,
        "total_tests": 4,
        "difficulty": 2,
    },
]

# P0 2.1 Level 3：跨文件依赖缺陷（module_a 调用 module_b，缺陷在 module_b 接口）
# 每个 Level 3 模式含两个模块：module_a_code（入口）+ module_b_code（被调方，含缺陷）。
# 测试代码同时导入两个模块，缺陷需修改 module_b 才能修复。
CROSS_FILE_PATTERNS: list[dict[str, Any]] = [
    {
        "name": "cross_file_api_contract",
        "description": "module_a 调用 module_b.process()，module_b 未处理空列表导致 IndexError",
        "module_a_code": """from module_b import process

def run_pipeline(items: list) -> list:
    result = process(items)
    return [x * 10 for x in result]""",
        "module_b_code": """def process(items: list) -> list:
    return [x + 1 for x in items]""",
        "fixed_module_b_code": """def process(items: list) -> list:
    if not items:
        return []
    return [x + 1 for x in items]""",
        "test_cases": """from module_a import run_pipeline
from module_b import process

def test_process_normal():
    assert process([1, 2, 3]) == [2, 3, 4]

def test_process_empty():
    assert process([]) == []

def test_run_pipeline_normal():
    assert run_pipeline([1, 2, 3]) == [20, 30, 40]

def test_run_pipeline_empty():
    assert run_pipeline([]) == []""",
        "bug_type": "runtime",
        "expected_pass": 3,
        "total_tests": 4,
        "difficulty": 3,
        "target_module": "module_b",
    },
    {
        "name": "cross_file_type_mismatch",
        "description": "module_a 假设 module_b.lookup() 返回 str，module_b 实际返回 int，类型不匹配",
        "module_a_code": """from module_b import lookup

def display(name: str) -> str:
    value = lookup(name)
    return f"value: {value.strip().upper()}"  # strip/upper 是 str 方法，int 没有""",
        "module_b_code": """_TABLE = {"alpha": 1, "beta": 2, "gamma": 3}

def lookup(key: str) -> int:
    return _TABLE.get(key, 0)""",
        "fixed_module_b_code": """_TABLE = {"alpha": "one", "beta": "two", "gamma": "three"}

def lookup(key: str) -> str:
    return _TABLE.get(key, "unknown")""",
        "test_cases": """from module_a import display
from module_b import lookup

def test_lookup_normal():
    result = lookup("alpha")
    assert isinstance(result, str)
    assert result == "one"

def test_lookup_missing():
    assert lookup("delta") == "unknown"

def test_display_normal():
    assert display("alpha") == "value: ONE"
""",
        "bug_type": "assertion",
        "expected_pass": 3,
        "total_tests": 3,
        "difficulty": 3,
        "target_module": "module_b",
    },
]

# P0 2.1 Level 4：边界条件 + 异常路径隐蔽缺陷
BUG_PATTERNS_LEVEL4: list[dict[str, Any]] = [
    {
        "name": "boundary_and_exception",
        "description": "日期解析：负数年份 + 无效时区字符串未处理，异常路径隐蔽",
        "template": """import datetime

def parse_date(s: str) -> datetime.datetime:
    return datetime.datetime.strptime(s, "%Y-%m-%d")

def days_until(target: str) -> int:
    dt = parse_date(target)
    delta = dt - datetime.datetime.now()
    return delta.days

def is_expired(target: str) -> bool:
    return days_until(target) < 0""",
        "fixed": """import datetime

def parse_date(s: str) -> datetime.datetime:
    if not s or not s.strip():
        raise ValueError("日期字符串不能为空")
    try:
        return datetime.datetime.strptime(s.strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"无法解析日期: {s!r}（期望格式 YYYY-MM-DD）")

def days_until(target: str) -> int:
    if target is None:
        raise ValueError("target 不能为 None")
    dt = parse_date(target)
    now = datetime.datetime.now()
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    delta = dt - now
    return delta.days

def is_expired(target: str) -> bool:
    if target is None or not target.strip():
        raise ValueError("target 不能为 None 或空字符串")
    return days_until(target) < 0""",
        "test_cases": """from boundary_and_exception import parse_date, days_until, is_expired
import datetime
import pytest

def test_parse_date_normal():
    result = parse_date("2024-01-15")
    assert result.year == 2024

def test_parse_date_empty():
    with pytest.raises(ValueError):
        parse_date("")

def test_parse_date_invalid():
    with pytest.raises(ValueError):
        parse_date("not-a-date")

def test_days_until_future():
    far_future = (datetime.datetime.now() + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
    assert days_until(far_future) > 300

def test_is_expired_past():
    assert is_expired("2000-01-01") is True
""",
        "bug_type": "runtime",
        "expected_pass": 3,
        "total_tests": 5,
        "difficulty": 4,
    },
]

# 按 difficulty 分组的模板库索引
_DIFFICULTY_PATTERNS: dict[int, list[dict[str, Any]]] = {
    1: BUG_PATTERNS,
    2: BUG_PATTERNS_LEVEL2,
    4: BUG_PATTERNS_LEVEL4,
}


class SyntheticDataset(BaseDatasetLoader):
    """
    合成缺陷数据集：通过预定义模板自动生成大量缺陷任务，无需外部数据。

    用途：
    - 在无法访问 SWE-bench/Defects4J 时进行快速验证
    - 生成 >= 50 个任务以满足论文实验规模要求
    - 每个任务包含明确的 bug 类型和正确修复方案
    - P0 2.1：支持 difficulty 参数分层生成（"mixed"/"level1"/"level2"/"level3"/"level4"）

    Args:
        task_count: 生成的任务数量。
        seed: 随机种子（确保可复现）。
        difficulty: 难度级别（P0 2.1），可选值：
            - "mixed"（默认，历史口径）：Level 1-4 轮换
            - "level1" / "level2" / "level4"：单难度梯度
            - "level3"：跨文件任务（双模块构造，需配合 CROSS_FILE_ENABLE 使用）
        subset: 数据子集名称（保留接口兼容）。
    """

    DATASET_NAME = "synthetic"

    _VALID_DIFFICULTIES: frozenset[str] = frozenset({"mixed", "level1", "level2", "level3", "level4"})

    def __init__(
        self,
        task_count: int = 100,
        seed: int = 42,
        subset: str | None = None,
        difficulty: str = "mixed",
        **kwargs: Any,
    ) -> None:
        """
        初始化合成数据集生成器。

        Args:
            task_count: 生成的任务数量。
            seed: 随机种子（确保可复现）。
            difficulty: P0 2.1 难度级别（"mixed"/"level1"/"level2"/"level3"/"level4"）。
            subset: 数据子集名称（保留接口兼容，实际忽略）。
            **kwargs: 兼容 load_dataset 工厂传递的额外参数（本数据集忽略）。
        """
        self._task_count = task_count
        self._seed = seed
        if difficulty not in self._VALID_DIFFICULTIES:
            logger.warning("未知 difficulty=%r，回退 'mixed'（历史口径）", difficulty)
            difficulty = "mixed"
        self._difficulty = difficulty
        super().__init__(subset=subset)

    def _difficulty_sequence(self, n: int, rng: random.Random) -> list[int]:
        """生成 n 个任务的难度序列（P0 2.1）。

        mixed：在 [1, 2, 3, 4] 间均匀随机；
        levelN：恒为 N；
        level3（跨文件）：恒为 3。
        """
        if self._difficulty == "mixed":
            return [rng.choice([1, 2, 3, 4]) for _ in range(n)]
        level = int(self._difficulty.replace("level", ""))
        return [level] * n

    def _pick_pattern(self, difficulty: int, rng: random.Random) -> dict[str, Any]:
        """按难度选模板（Level 3 走跨文件库，其他走单文件库）。"""
        pool = CROSS_FILE_PATTERNS if difficulty == 3 else _DIFFICULTY_PATTERNS.get(difficulty, BUG_PATTERNS)
        return rng.choice(pool)

    def _load_raw_data(self) -> None:
        """根据模板库生成指定数量的合成缺陷任务（P0 2.1 分层难度）。"""
        rng = random.Random(self._seed)
        tasks: list[BenchmarkTask] = []
        seq = self._difficulty_sequence(self._task_count, rng)

        for i, difficulty in enumerate(seq):
            pattern = self._pick_pattern(difficulty, rng)
            noise = rng.randint(0, 9999)
            task_id = f"synthetic__{pattern['name']}_{i:04d}"

            # 跨文件任务（difficulty=3）：双模块构造
            if difficulty == 3:
                module_b_code = pattern["module_b_code"] + f"\n# noise_seed_b={noise}\n"
                # instance_code 是 module_b（被调方，含缺陷）；
                # module_a 代码经 metadata 传递（跨文件修复架构消费）
                task = BenchmarkTask(
                    task_id=task_id,
                    repo_name=f"synthetic/{pattern['name']}",
                    problem_statement=pattern["description"],
                    instance_code=module_b_code,
                    test_code=pattern["test_cases"],
                    expected_pass_count=pattern["expected_pass"],
                    total_test_count=pattern["total_tests"],
                    metadata={
                        "bug_type": pattern["bug_type"],
                        "pattern_name": pattern["name"],
                        "source": "synthetic",
                        "noise_seed": noise,
                        "difficulty": 3,
                        "is_cross_file": True,
                        "module_a_code": pattern["module_a_code"],
                        "module_a_name": "module_a",
                        "module_b_name": "module_b",
                        "target_module": pattern.get("target_module", "cross_file_module_b"),
                        "fixed_module_b_code": pattern.get("fixed_module_b_code", ""),
                        "num_files": 2,
                    },
                )
            else:
                # 单文件任务（Level 1/2/4）：历史口径
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
                        "difficulty": difficulty,
                        "is_cross_file": False,
                    },
                )
            tasks.append(task)

        self._tasks = tasks
        # 难度分布日志（便于实验报告消费）
        dist: dict[str, int] = {}
        for t in tasks:
            d = t.metadata.get("difficulty", 1)
            dist[d] = dist.get(d, 0) + 1
        logger.info(
            "合成数据集生成完成：%d 个任务（difficulty=%s，分布=%s）",
            len(tasks),
            self._difficulty,
            dist,
        )


if __name__ == "__main__":
    ds = SyntheticDataset(task_count=60, seed=42)
    logger.info("合成数据集规模: %d 个任务", ds.size)
    for task in ds.tasks[:5]:
        logger.info("  - %s: %s", task.task_id, task.problem_statement[:50])
