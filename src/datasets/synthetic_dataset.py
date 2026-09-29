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

# 2026-10 改进（A/B 阴性结果驱动）：Level 2.5 运行时异常缺陷库。
# 三组 A/B（position_aware / rag / cross_file）共同揭示的结构性问题：合成集失败
# 模式以 assertion 为主，无 traceback 帧行号 → 位置感知修复定位阶段从未激活
# （定位命中 0/30）。本库构造四类"执行即抛运行时异常"的缺陷：
#   - IndexError（数组/列表越界访问）
#   - KeyError（字典键缺失）
#   - AttributeError（对 None/错误类型对象做属性访问）
#   - TypeError（类型不匹配调用 / 不兼容运算）
# 关键设计：模板代码**可正常 import**（无语法错误、无顶层异常），但被测试
# 用例调用时抛出上述异常 → pytest 失败输出携带完整 traceback 帧
# （File "xxx", line N），使 _locate_repair_focus 能提取到具体行号，激活
# 位置感知修复路径。每个模式附 suggested_function（gold 定位目标，供
# position_aware_ab._locate_accuracy 做定位正确率金标准匹配）。
# 修复态（fixed）：补边界/空值/类型守卫，全部测试通过。
BUG_PATTERNS_LEVEL25: list[dict[str, Any]] = [
    {
        "name": "runtime_index_error_boundary",
        "description": "列表边界访问未检查长度，索引越界抛 IndexError",
        "template": """def get_last_two(items: list) -> list:
    return items[-2:]

def first_and_last(items: list) -> tuple:
    return (items[0], items[-1])

def middle(items: list) -> any:
    return items[len(items) // 2]""",
        "fixed": """def get_last_two(items: list) -> list:
    if not items:
        return []
    return items[-2:]

def first_and_last(items: list) -> tuple:
    if not items:
        return (None, None)
    return (items[0], items[-1])

def middle(items: list) -> any:
    if not items:
        return None
    return items[len(items) // 2]""",
        "test_cases": """from runtime_index_error_boundary import get_last_two, first_and_last, middle

def test_get_last_two_normal():
    assert get_last_two([1, 2, 3, 4]) == [3, 4]

def test_get_last_two_empty():
    assert get_last_two([]) == []

def test_first_and_last_normal():
    assert first_and_last([1, 2, 3]) == (1, 3)

def test_first_and_last_single():
    assert first_and_last([5]) == (5, 5)

def test_first_and_last_empty():
    assert first_and_last([]) == (None, None)

def test_middle_normal():
    assert middle([1, 2, 3, 4]) in (2, 3)

def test_middle_empty():
    assert middle([]) is None""",
        "bug_type": "runtime",
        "expected_pass": 7,
        "total_tests": 7,
        "difficulty": 2,
        "trigger_exception": "IndexError",
        # P0 2026-10（A/B 阴性结果驱动）：定位目标 = 缺陷所在函数
        # （first_and_last 空列表越界）。注意"取最内层帧"语义下定位命中
        # 取决于首个失败测试，此处 gold 供 A/B 定位正确率参考。
        "suggested_function": "first_and_last",
    },
    {
        "name": "runtime_key_error_missing",
        "description": "字典按键取值未处理键缺失，抛 KeyError",
        "template": """def lookup_user(users: dict, user_id: str) -> str:
    return users[user_id]["name"]

def user_age(users: dict, user_id: str) -> int:
    return users[user_id]["age"]

def summary(users: dict, user_id: str) -> str:
    user = users[user_id]
    return "({0}) {1}".format(user["age"], user["name"])""",
        "fixed": """def lookup_user(users: dict, user_id: str) -> str:
    user = users.get(user_id) or {}
    return user.get("name", "unknown")

def user_age(users: dict, user_id: str) -> int:
    user = users.get(user_id) or {}
    return user.get("age", 0)

def summary(users: dict, user_id: str) -> str:
    user = users.get(user_id) or {}
    name = user.get("name", "unknown")
    age = user.get("age", 0)
    return "({0}) {1}".format(age, name)""",
        "test_cases": """from runtime_key_error_missing import lookup_user, user_age, summary

USERS = {"a": {"name": "Alice", "age": 30}, "b": {"name": "Bob", "age": 25}}

def test_lookup_user_found():
    assert lookup_user(USERS, "a") == "Alice"

def test_lookup_user_missing():
    assert lookup_user(USERS, "x") == "unknown"

def test_user_age_found():
    assert user_age(USERS, "b") == 25

def test_user_age_missing():
    assert user_age(USERS, "x") == 0

def test_summary_found():
    assert summary(USERS, "a") == "(30) Alice"

def test_summary_missing():
    assert summary(USERS, "x") == "(0) unknown"

def test_summary_partial_user():
    users = {"c": {"name": "Carol"}}
    assert summary(users, "c") == "(0) Carol"

def test_summary_empty_dict():
    assert summary({}, "a") == "(0) unknown" """
        ,
        "bug_type": "runtime",
        "expected_pass": 8,
        "total_tests": 8,
        "difficulty": 2,
        "trigger_exception": "KeyError",
        "suggested_function": "lookup_user",
    },
    {
        "name": "runtime_attribute_error_none",
        "description": "对 None 返回结果做属性访问，抛 AttributeError",
        "template": """class Config:
    def __init__(self):
        self.settings = None

    def get_option(self, key: str) -> str:
        return self.settings.get(key, "")

    def has_option(self, key: str) -> bool:
        return key in self.settings

    def size(self) -> int:
        return len(self.settings)""",
        "fixed": """class Config:
    def __init__(self):
        self.settings = None

    def get_option(self, key: str) -> str:
        if not self.settings:
            return ""
        return self.settings.get(key, "")

    def has_option(self, key: str) -> bool:
        if not self.settings:
            return False
        return key in self.settings

    def size(self) -> int:
        if not self.settings:
            return 0
        return len(self.settings)""",
        "test_cases": """from runtime_attribute_error_none import Config

def test_config_get_option_unset():
    cfg = Config()
    assert cfg.get_option("theme") == ""

def test_config_has_option_unset():
    cfg = Config()
    assert cfg.has_option("theme") is False

def test_config_size_unset():
    cfg = Config()
    assert cfg.size() == 0

def test_config_get_option_set():
    cfg = Config()
    cfg.settings = {"theme": "dark"}
    assert cfg.get_option("theme") == "dark"

def test_config_get_option_set_missing_key():
    cfg = Config()
    cfg.settings = {"theme": "dark"}
    assert cfg.get_option("lang") == ""

def test_config_has_option_set():
    cfg = Config()
    cfg.settings = {"theme": "dark"}
    assert cfg.has_option("theme") is True
    assert cfg.has_option("lang") is False

def test_config_size_set():
    cfg = Config()
    cfg.settings = {"a": 1, "b": 2}
    assert cfg.size() == 2

def test_config_partial_none_values():
    cfg = Config()
    cfg.settings = {"theme": None, "lang": "en"}
    assert cfg.get_option("theme") is None
    assert cfg.has_option("theme") is True""",
        "bug_type": "runtime",
        "expected_pass": 8,
        "total_tests": 8,
        "difficulty": 2,
        "trigger_exception": "AttributeError",
        "suggested_function": "get_option",
    },
    {
        "name": "runtime_type_error_mismatch",
        "description": "类型不匹配调用：int 列表混入 str，对不可加元素求和/比较抛 TypeError",
        "template": """def total(values: list) -> int:
    return sum(values)

def max_value(values: list) -> any:
    return max(values)

def is_increasing(values: list) -> bool:
    for i in range(1, len(values)):
        if values[i - 1] > values[i]:
            return False
    return True""",
        "fixed": """def total(values: list) -> float:
    return sum(float(v) for v in values if isinstance(v, (int, float)))

def max_value(values: list) -> float:
    numeric = [float(v) for v in values if isinstance(v, (int, float))]
    if not numeric:
        return 0.0
    return max(numeric)

def is_increasing(values: list) -> bool:
    numeric = [float(v) for v in values if isinstance(v, (int, float))]
    for i in range(1, len(numeric)):
        if numeric[i - 1] > numeric[i]:
            return False
    return True""",
        "test_cases": """from runtime_type_error_mismatch import total, max_value, is_increasing

def test_total_normal():
    assert total([1, 2, 3]) == 6

def test_total_mixed():
    assert total([1, 2.5, "x"]) == 3.5

def test_total_all_invalid():
    assert total(["a", "b"]) == 0

def test_total_empty():
    assert total([]) == 0

def test_max_normal():
    assert max_value([3, 1, 2]) == 3

def test_max_mixed():
    assert max_value([1, "x", 5.5]) == 5.5

def test_max_empty():
    assert max_value([]) == 0.0

def test_is_increasing_normal():
    assert is_increasing([1, 2, 3]) is True

def test_is_increasing_mixed():
    assert is_increasing([1, "x", 3]) is True

def test_is_increasing_decreasing():
    assert is_increasing([3, 2, 1]) is False

def test_is_increasing_empty():
    assert is_increasing([]) is True

def test_is_increasing_with_float():
    assert is_increasing([1.5, 2.5, 3.0]) is True""",
        "bug_type": "runtime",
        "expected_pass": 12,
        "total_tests": 12,
        "difficulty": 2,
        "trigger_exception": "TypeError",
        "suggested_function": "total",
    },
]

# 2026-10（第二轮，A/B 统计效力驱动）：Level 2.5-Hard 困难运行时异常缺陷库。
# 背景：BUG_PATTERNS_LEVEL25（4 模式）在 n=40 规模位置感知 A/B 中
# ON/OFF 成功率均 100%（agnes-3.0-flash 首轮生成即修复），定位阶段仍未
# 激活——无区分度，A/B 无信息量。本库 8 个模式按"缺陷藏得更深"设计：
#   - 调用链深处（入口函数委托 helper，缺陷在 helper 的隐蔽分支）；
#   - 缺陷只在特定输入形状下触发（嵌套 dict 缺内层键 / 混合类型 / 空迭代器）；
#   - 正确修复需补守卫 + 类型归一化 + 空值兜底三处联动（单点修复不够）；
#   - 模板代码可正常 import，正常输入路径全绿，仅特定测试用例触发
#     IndexError/KeyError/AttributeError/TypeError → traceback 携带帧行号，
#     位置感知定位阶段可被激活（与 LEVEL25 同口径，但缺陷隐蔽性 +1 档）。
# 每个模式携带 suggested_function（gold 定位目标，缺陷所在函数），供
# position_aware_ab._locate_accuracy 做定位正确率匹配。
BUG_PATTERNS_LEVEL25HARD: list[dict[str, Any]] = [
    {
        "name": "hard_depth_blind_nested",
        "description": "扁平统计器：stats_of 委托 count_items，对嵌套 list 不递归展开，返回 0",
        "template": "def stats_of(data):\n    return count_items(data)\n\ndef count_items(data):\n    if isinstance(data, list):\n        total = 0\n        for x in data:\n            if isinstance(x, int):\n                total += 1\n        return total\n    return 0\n\ndef describe(data):\n    n = count_items(data)\n    return f'items={n}'\n",
        "fixed": "def stats_of(data):\n    return count_items(data)\n\ndef _flatten(data):\n    out = []\n    for x in data:\n        if isinstance(x, (list, tuple)):\n            out.extend(_flatten(x))\n        else:\n            out.append(x)\n    return out\n\ndef count_items(data):\n    if isinstance(data, list):\n        return sum(1 for x in _flatten(data) if isinstance(x, int))\n    return 0\n\ndef describe(data):\n    n = count_items(data)\n    return f'items={n}'\n",
        "test_cases": "from hard_depth_blind_nested import stats_of, count_items, describe\n\ndef test_flat_list():\n    assert count_items([1, 2, 3]) == 3\n\ndef test_nested_list():\n    assert count_items([[1, 2], [3, [4, 5]]]) == 5\n\ndef test_mixed_types():\n    assert count_items([1, \"a\", 2, None, 3]) == 3\n\ndef test_deep_nesting():\n    assert count_items([[[[1]]], [2, [3]]]) == 3\n\ndef test_empty_and_scalars():\n    assert count_items([]) == 0\n    assert count_items(5) == 0\n    assert stats_of([1, [2, 3]]) == 3\n    assert describe([[1, 2]]) == 'items=2'\n",
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 5,
        "difficulty": 2,
        "trigger_exception": "AssertionError",
        "suggested_function": "count_items",
    },
    {
        "name": "hard_chained_dict_lookup",
        "description": "嵌套映射取链路：metric 在 layers 缺失或某层缺 key 时抛 KeyError",
        "template": """def lookup_metric(metrics: dict, layer_name: str, key: str):
    layers = metrics[layer_name]
    return layers[key]

def summarize(metrics: dict, layer_name: str):
    total = 0
    for key in metrics[layer_name]:
        total += lookup_metric(metrics, layer_name, key)
    return total

def rank(metrics: dict, layer_name: str, k: int):
    keys = sorted(metrics[layer_name], key=lambda s: -lookup_metric(metrics, layer_name, s))
    return keys[:k]""",
        "fixed": """def lookup_metric(metrics: dict, layer_name: str, key: str):
    layers = metrics.get(layer_name) or {}
    return layers.get(key, 0.0)

def summarize(metrics: dict, layer_name: str):
    total = 0
    for key in (metrics.get(layer_name) or {}):
        total += lookup_metric(metrics, layer_name, key)
    return total

def rank(metrics: dict, layer_name: str, k: int):
    keys = sorted((metrics.get(layer_name) or {}), key=lambda s: -lookup_metric(metrics, layer_name, s))
    return keys[:k]""",
        "test_cases": """from hard_chained_dict_lookup import lookup_metric, summarize, rank

M = {"a": {"x": 1.0, "y": 2.0}}

def test_metric_found():
    assert lookup_metric(M, "a", "x") == 1.0

def test_metric_missing_key():
    assert lookup_metric(M, "a", "z") == 0.0

def test_metric_missing_layer():
    assert lookup_metric(M, "b", "x") == 0.0

def test_summarize_empty():
    assert summarize({}, "a") == 0

def test_rank_missing_layer():
    assert rank(M, "b", 2) == []

def test_rank_order():
    assert rank(M, "a", 1) == ["y"] """,
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 6,
        "difficulty": 2,
        "trigger_exception": "KeyError",
        "suggested_function": "lookup_metric",
    },
    {
        "name": "hard_polluted_entry_guard",
        "description": "记录池遍历：pool_status 对混入 dict 条目的池抛 TypeError",
        "template": """def pool_status(entries: list) -> dict:
    total = 0
    for e in entries:
        total += len(e)
    return {"total": total, "count": len(entries)}

def merge(a: list, b: list) -> list:
    out = list(a)
    for item in b:
        if item not in out:
            out.append(item)
    return out

def largest(entries: list):
    return max((len(e) for e in entries), default=0)""",
        "fixed": """def pool_status(entries: list) -> dict:
    total = 0
    for e in entries:
        if isinstance(e, dict):
            total += len(e)
        else:
            total += len(e or [])
    return {"total": total, "count": len(entries)}

def merge(a: list, b: list) -> list:
    out = list(a or [])
    for item in b or []:
        if item not in out:
            out.append(item)
    return out

def largest(entries: list):
    sizes = [len(e) for e in entries if isinstance(e, (list, tuple, dict))]
    return max(sizes, default=0)""",
        "test_cases": """from hard_polluted_entry_guard import pool_status, merge, largest

def test_clean_pool():
    assert pool_status([[1, 2], [3]]) == {"total": 3, "count": 2}

def test_polluted_pool():
    assert pool_status([[1], {"k": 1}]) == {"total": 2, "count": 2}

def test_empty_pool():
    assert pool_status([]) == {"total": 0, "count": 0}

def test_merge_disjoint():
    assert merge([1, 2], [3]) == [1, 2, 3]

def test_merge_empty():
    assert merge([], [1]) == [1]
    assert merge(None, None) == []

def test_largest_mixed():
    assert largest([[1, 2], {"a": 1, "b": 2}]) == 2
    assert largest([]) == 0 """,
        "bug_type": "runtime",
        "expected_pass": 5,
        "total_tests": 6,
        "difficulty": 2,
        "trigger_exception": "TypeError",
        "suggested_function": "pool_status",
    },
    {
        "name": "hard_iter_over_none",
        "description": "迭代器展开：expand_regions 对 None 输入抛 TypeError（None 不可迭代）",
        "template": """def expand_regions(regions):
    flat = []
    for region in regions:
        for coord in region:
            flat.append(coord)
    return flat

def region_count(regions):
    return len(expand_regions(regions))

def contains(regions, coord):
    return coord in expand_regions(regions)""",
        "fixed": """def expand_regions(regions):
    flat = []
    for region in regions or []:
        if region is None:
            continue
        for coord in region:
            flat.append(coord)
    return flat

def region_count(regions):
    return len(expand_regions(regions))

def contains(regions, coord):
    return coord in expand_regions(regions)""",
        "test_cases": """from hard_iter_over_none import expand_regions, region_count, contains

def test_normal_regions():
    assert expand_regions([[1, 2], [3]]) == [1, 2, 3]

def test_none_input():
    assert expand_regions(None) == []

def test_none_element():
    assert expand_regions([[1], None, [2]]) == [1, 2]

def test_count_none():
    assert region_count(None) == 0

def test_contains_empty():
    assert contains([], 1) is False
    assert contains(None, 1) is False """,
        "bug_type": "runtime",
        "expected_pass": 1,
        "total_tests": 5,
        "difficulty": 2,
        "trigger_exception": "TypeError",
        "suggested_function": "expand_regions",
    },
    {
        "name": "hard_nested_iter_mixed",
        "description": "深度收集器：collect 不递归展开嵌套列表，且对 dict 元素抛异常",
        "template": """def collect(items):
    out = []
    for item in items:
        if isinstance(item, list):
            out.extend(item)
        else:
            out.append(item)
    return out

def collect_depth(items):
    return len(collect(items))

def first_leaf(items):
    for x in collect(items):
        if not isinstance(x, list):
            return x
    return None""",
        "fixed": """def _flatten(items):
    out = []
    for item in items or []:
        if isinstance(item, (list, tuple)):
            out.extend(_flatten(item))
        else:
            out.append(item)
    return out

def collect(items):
    return _flatten(items)

def collect_depth(items):
    return len(collect(items))

def first_leaf(items):
    for x in collect(items):
        if not isinstance(x, list):
            return x
    return None""",
        "test_cases": """from hard_nested_iter_mixed import collect, collect_depth, first_leaf

def test_flat():
    assert collect([1, 2, 3]) == [1, 2, 3]

def test_nested():
    assert collect([[1, 2], [3]]) == [1, 2, 3]

def test_deep_nested():
    assert collect([[ [1], [2, 3] ], 4]) == [1, 2, 3, 4]

def test_mixed_types():
    assert collect([1, "a", [2, 3], None]) == [1, "a", 2, 3, None]

def test_none_input():
    assert collect(None) == []
    assert collect_depth(None) == 0

def test_first_leaf():
    assert first_leaf([[1, [2]], 3]) == 1
    assert first_leaf([]) is None """,
        "bug_type": "runtime",
        "expected_pass": 4,
        "total_tests": 6,
        "difficulty": 2,
        "trigger_exception": "TypeError",
        "suggested_function": "collect",
    },
    {
        "name": "hard_mixed_numeric_agg",
        "description": "数值聚合：total/max_value/percent_share 对 int-str 混列表抛 TypeError",
        "template": """def total(values: list) -> float:
    return sum(values)

def max_value(values: list) -> float:
    return max(values)

def percent_share(value, values: list) -> float:
    t = total(values)
    return value / t * 100.0""",
        "fixed": """def _numeric(values: list) -> list:
    return [float(v) for v in (values or []) if isinstance(v, (int, float))]

def total(values: list) -> float:
    return sum(_numeric(values))

def max_value(values: list) -> float:
    nums = _numeric(values)
    return max(nums) if nums else 0.0

def percent_share(value, values: list) -> float:
    t = total(values)
    if t == 0:
        return 0.0
    return float(value) / t * 100.0""",
        "test_cases": """from hard_mixed_numeric_agg import total, max_value, percent_share

def test_total_numeric():
    assert total([1, 2, 3]) == 6

def test_total_mixed():
    assert total([1, "x", 2.5]) == 3.5

def test_total_all_invalid():
    assert total(["a", "b"]) == 0

def test_max_mixed():
    assert max_value([1, "x", 5.5]) == 5.5

def test_max_empty():
    assert max_value([]) == 0.0

def test_share_normal():
    assert abs(percent_share(1.0, [1.0, 1.0]) - 50.0) < 1e-9

def test_share_zero_total():
    assert percent_share(1.0, ["a"]) == 0.0 """,
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 7,
        "difficulty": 2,
        "trigger_exception": "TypeError",
        "suggested_function": "total",
    },
    {
        "name": "hard_attribute_chain_guard",
        "description": "配置链：resolve_option 对未初始化 settings / 部分 None 值抛 AttributeError",
        "template": """class Config:
    def __init__(self):
        self.settings = None
        self.override = {}

    def resolve_option(self, key):
        if key in self.override:
            return self.override[key]
        return self.settings.get(key, "")

    def has_option(self, key):
        return key in self.settings

    def dump(self):
        return dict(self.settings)""",
        "fixed": """class Config:
    def __init__(self):
        self.settings = None
        self.override = {}

    def resolve_option(self, key):
        if key in self.override:
            return self.override[key]
        base = self.settings or {}
        value = base.get(key, "")
        return "" if value is None else value

    def has_option(self, key):
        if key in self.override:
            return True
        base = self.settings or {}
        return key in base and base.get(key) is not None

    def dump(self):
        base = dict(self.settings or {})
        base.update(self.override)
        return base""",
        "test_cases": """from hard_attribute_chain_guard import Config

def test_uninitialized_resolve():
    assert Config().resolve_option("theme") == ""

def test_uninitialized_has():
    assert Config().has_option("theme") is False

def test_uninitialized_dump():
    assert Config().dump() == {}

def test_partial_none_values():
    cfg = Config()
    cfg.settings = {"theme": None, "lang": "en"}
    assert cfg.resolve_option("theme") == ""
    assert cfg.resolve_option("lang") == "en"
    assert cfg.has_option("theme") is False
    assert cfg.has_option("lang") is True

def test_override_wins():
    cfg = Config()
    cfg.override = {"theme": "dark"}
    assert cfg.resolve_option("theme") == "dark"

def test_dump_merges():
    cfg = Config()
    cfg.settings = {"lang": "en"}
    cfg.override = {"theme": "dark"}
    assert cfg.dump() == {"lang": "en", "theme": "dark"} """,
        "bug_type": "runtime",
        "expected_pass": 1,
        "total_tests": 6,
        "difficulty": 2,
        "trigger_exception": "AttributeError",
        "suggested_function": "resolve_option",
    },
    {
        "name": "hard_slice_contract",
        "description": "切片契约：entries 长度不定（2/3/4 字段混合），split_entry 对短条目抛 IndexError",
        "template": """def split_entry(entry):
    return {"head": entry[0], "body": entry[1], "tail": entry[2], "flag": entry[3]}

def count_flags(entries):
    n = 0
    for e in entries:
        if split_entry(e)["flag"]:
            n += 1
    return n

def entry_names(entries):
    return [e[0] for e in entries]""",
        "fixed": """def split_entry(entry):
    pad = list(entry) + [None] * (4 - len(entry))
    return {"head": pad[0], "body": pad[1], "tail": pad[2], "flag": pad[3]}

def count_flags(entries):
    n = 0
    for e in entries or []:
        if split_entry(e)["flag"]:
            n += 1
    return n

def entry_names(entries):
    return [e[0] for e in (entries or []) if e]""",
        "test_cases": """from hard_slice_contract import split_entry, count_flags, entry_names

E = [["a", 1, "x", True], ["b", 2, "y"], ["c"], ["d", 4, "w", False]]

def test_full_entry():
    assert split_entry(["a", 1, "x", True]) == {"head": "a", "body": 1, "tail": "x", "flag": True}

def test_short_entry():
    assert split_entry(["c"])["body"] is None

def test_mixed_lengths():
    assert count_flags(E) == 1

def test_empty_entries():
    assert count_flags([]) == 0
    assert entry_names([]) == []

def test_names_skip_empty():
    assert entry_names([["z", 9, "q", True], []]) == ["z"] """,
        "bug_type": "runtime",
        "expected_pass": 2,
        "total_tests": 5,
        "difficulty": 2,
        "trigger_exception": "IndexError",
        "suggested_function": "split_entry",
    },
]

# P0 2.1 Level 3.5：复杂跨文件依赖（3 文件依赖链 module_a → module_b → module_c）。
# 2026-10 改进（A/B 阴性结果驱动）：Level 3 双模块 +10pp 未达 T1 +15pp 阈值，
# 根因之一是依赖图粒度过粗（单入口视角 AST import 分析）。Level 3.5 用 3 文件
# 依赖链把"目标文件导入了谁"与"谁导入了目标文件"都纳入修复视野，验证双向
# 依赖图（CROSS_FILE_BIDIRECTIONAL_ENABLE，默认关）能否覆盖更深的跨模块缺陷。
CROSS_FILE_DEEP_PATTERNS: list[dict[str, Any]] = [
    {
        "name": "cross_file_three_module_chain",
        "description": (
            "module_a → module_b → module_c 三级调用链，缺陷在 module_c 的聚合函数"
            "（空列表未处理导致 IndexError + 类型混用导致求和精度丢失），"
            "修复需理解双向依赖（谁调用 module_c）并修改 module_c 接口实现"
        ),
        "module_a_code": """from module_b import transform_batch
from module_c import doubled

def analyze_dataset(records: list) -> dict:
    cleaned = [r for r in records if r is not None]
    transformed = transform_batch(records)
    return {"count": len(cleaned), "doubled_sum": doubled(cleaned)}""",
        "module_b_code": """from module_c import normalize_values, aggregate, doubled

def transform_batch(records: list) -> list:
    cleaned = [r for r in records if r is not None]
    normalized = normalize_values(cleaned)
    mean = aggregate(normalized) if normalized else 0.0
    return [float(v) for v in normalized]""",
        "module_c_code": """def normalize_values(values: list) -> list:
    return [v * 2 for v in values] + [0]  # 历史 bug：空列表返回 [0] 而非 []

def aggregate(values: list) -> float:
    return sum(values) / len(values)  # 历史 bug：空列表除零

def doubled(values: list) -> float:
    return 2 * sum(values, 0)  # 历史 bug：int 混用未归一化 float""",
        "fixed_module_c_code": """def normalize_values(values: list) -> list:
    if not values:
        return []
    return [float(v) * 2 for v in values]

def aggregate(values: list) -> float:
    if not values:
        return 0.0
    total = 0.0
    for v in values:
        total += float(v)
    return total / len(values)

def doubled(values: list) -> float:
    if not values:
        return 0.0
    return 2.0 * sum((float(v) for v in values), 0.0)""",
        "test_cases": """from module_c import normalize_values, aggregate
from module_a import analyze_dataset
from module_b import transform_batch

def test_aggregate_empty():
    # 置于首位：空列表除零（ZeroDivisionError）展开被测模块帧
    # module_c.py:N: in aggregate，使位置感知定位阶段可被激活
    # （--tb=short 下纯 assertion 失败不展开被测帧，运行时异常才展开）
    assert aggregate([]) == 0.0

def test_normalize_normal():
    assert normalize_values([1, 2, 3]) == [2.0, 4.0, 6.0]

def test_normalize_empty():
    assert normalize_values([]) == []

def test_aggregate_normal():
    assert abs(aggregate([1.0, 2.0, 3.0]) - 2.0) < 1e-9

def test_transform_batch_mixed_types():
    # int/float 混用历史缺陷：sum([1, 2.5]) 旧口径 int*2 丢精度
    assert transform_batch([1, 2.5]) == [2.0, 5.0]

def test_analyze_dataset_normal():
    result = analyze_dataset([1, 2, 3])
    assert result["count"] == 3
    assert abs(result["doubled_sum"] - 12.0) < 1e-9

def test_analyze_dataset_empty():
    result = analyze_dataset([])
    assert result["count"] == 0
    assert result["doubled_sum"] == 0

def test_analyze_dataset_with_none():
    result = analyze_dataset([1, None, 3])
    assert result["count"] == 2
    assert abs(result["doubled_sum"] - 8.0) < 1e-9""",
        "bug_type": "runtime",
        "expected_pass": 8,
        "total_tests": 8,
        "difficulty": 3,
        "target_module": "module_c",
        "num_files": 3,
        "dep_chain": ["module_a", "module_b", "module_c"],
        # P0 2026-10（A/B 阴性结果驱动）：gold 定位目标 = 缺陷所在函数
        # （module_c.aggregate 的除零缺陷），供 position_aware_ab 定位正确率匹配。
        "suggested_function": "aggregate",
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
    {
        "name": "type_mismatch_contract",
        "description": (
            "PAGENT 风格类型缺陷：compute_scores 契约上返回 dict[str, float]，"
            "但 normalize 路径漏了 float() 转换，int 输入混入后 dict 值类型不稳定；"
            "average 对空 dict 除零 + 对 int 值求平均丢精度。修复需补类型转换"
            "（触发 2.1 PAGENT 类型修复层：type_repair_layer 静态识别类型疑点）"
        ),
        "template": """def compute_scores(records: list) -> dict:
    scores = {}
    for record in records:
        key = record.get("name", "unknown")
        value = record.get("value", 0)
        scores[key] = value
    return scores

def average(scores: dict) -> float:
    if not scores:
        return 0.0
    total = sum(scores.values())
    return total / len(scores)

def rank_top(scores: dict, k: int) -> list:
    items = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return items[:k]""",
        "fixed": """def compute_scores(records: list) -> dict:
    scores = {}
    for record in records:
        key = str(record.get("name", "unknown"))
        value = float(record.get("value", 0))
        scores[key] = value
    return scores

def average(scores: dict) -> float:
    if not scores:
        return 0.0
    total = sum(float(v) for v in scores.values())
    return total / len(scores)

def rank_top(scores: dict, k: int) -> list:
    if k <= 0:
        return []
    items = sorted(scores.items(), key=lambda kv: float(kv[1]), reverse=True)
    return items[:k]""",
        "test_cases": """from type_mismatch_contract import compute_scores, average, rank_top

def test_compute_scores_normal():
    records = [{"name": "a", "value": 1}, {"name": "b", "value": 2.5}]
    scores = compute_scores(records)
    assert isinstance(scores, dict)
    assert isinstance(scores["a"], float)
    assert isinstance(scores["b"], float)

def test_compute_scores_mixed_types():
    records = [{"name": "a", "value": 1}, {"name": "b", "value": 2.5}]
    scores = compute_scores(records)
    assert all(isinstance(v, float) for v in scores.values())

def test_average_empty():
    assert average({}) == 0.0

def test_average_normal():
    assert abs(average({"a": 1.0, "b": 2.0}) - 1.5) < 1e-9

def test_rank_top_empty_dict():
    assert rank_top({}, 3) == []

def test_rank_top_k_zero():
    assert rank_top({"a": 1.0}, 0) == []

def test_rank_top_normal():
    result = rank_top({"a": 1.0, "b": 3.0, "c": 2.0}, 2)
    assert result == [("b", 3.0), ("c", 2.0)]""",
        "bug_type": "assertion",
        "expected_pass": 6,
        "total_tests": 7,
        "difficulty": 4,
    },
]

# P0 2.1 Level 4.5：导入链破坏缺陷（命名契约守卫触发场景）。
# 与 type_mismatch_contract 的区别：缺陷不在函数体逻辑，而在模块级契约
# （_TABLE 值类型 + lookup 返回类型），修复需同时改 module 级常量与函数签名，
# 是"命名契约守卫"（patch_applier 符号守卫）拒绝 LLM 误删符号的典型场景。
BUG_PATTERNS_LEVEL45: list[dict[str, Any]] = [
    {
        "name": "import_chain_type_contract",
        "description": (
            "导入链破坏缺陷：lookup 契约上返回 str（_TABLE 值应为字符串），"
            "实际 _TABLE 值被写成 int，lookup 返回 int；调用方 module_a 的 "
            "display 假设 str 调 .strip()/.upper()，TypeError。修复需同时"
            "修正 _TABLE 值类型与 lookup 签名（module 级符号契约 + 函数体）"
        ),
        "template": """_TABLE = {"alpha": 1, "beta": 2, "gamma": 3}

def lookup(key: str) -> int:
    return _TABLE.get(key, 0)

def describe(value: int) -> str:
    return f"value={value}"

def display(name: str) -> str:
    value = lookup(name)
    return f"name={name} " + value.strip().upper()""",
        "fixed": """_TABLE = {"alpha": "one", "beta": "two", "gamma": "three"}

def lookup(key: str) -> str:
    return _TABLE.get(key, "unknown")

def describe(value: str) -> str:
    return f"value={value}"

def display(name: str) -> str:
    value = lookup(name)
    return f"name={name} " + value.strip().upper()""",
        "test_cases": """from import_chain_type_contract import lookup, describe, display, _TABLE

def test_table_values_are_str():
    assert all(isinstance(v, str) for v in _TABLE.values())

def test_lookup_normal():
    assert lookup("alpha") == "one"
    assert isinstance(lookup("alpha"), str)

def test_lookup_missing():
    assert lookup("delta") == "unknown"

def test_describe():
    assert describe("one") == "value=one"

def test_display_normal():
    assert display("alpha") == "name=alpha ONE"

def test_display_missing():
    assert display("delta") == "name=delta UNKNOWN"

def test_display_keeps_contract():
    # 契约守卫：修复后 _TABLE 键集合不变（命名契约不破坏）
    assert set(_TABLE.keys()) == {"alpha", "beta", "gamma"}""",
        "bug_type": "assertion",
        "expected_pass": 7,
        "total_tests": 7,
        "difficulty": 5,
    },
]

# 按 difficulty 分组的模板库索引
_DIFFICULTY_PATTERNS: dict[int, list[dict[str, Any]]] = {
    1: BUG_PATTERNS,
    2: BUG_PATTERNS_LEVEL2,
    25: BUG_PATTERNS_LEVEL25,  # 2026-10：Level 2.5 运行时异常缺陷库（独立整数码 25）
    26: BUG_PATTERNS_LEVEL25HARD,  # 2026-10（第二轮）：Level 2.5-Hard 困难运行时异常库（缺陷更隐蔽）
    3: CROSS_FILE_PATTERNS + CROSS_FILE_DEEP_PATTERNS,
    35: CROSS_FILE_DEEP_PATTERNS,  # 2026-10：Level 3.5 三模块深链（独立整数码 35）
    4: BUG_PATTERNS_LEVEL4,
    5: BUG_PATTERNS_LEVEL45,
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

    _VALID_DIFFICULTIES: frozenset[str] = frozenset(
        {
            "mixed",
            "level1",
            "level2",
            "level2.5",
            "level2.5-hard",
            "level3",
            "level3.5",
            "level4",
            "level4.5",
        }
    )

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
        """生成 n 个任务的难度序列（P0 2.1 + 2026-10 失败模式多样性）。

        mixed：在 [1, 2, 3, 4, 5] 间均匀随机（含 Level 2.5 运行时异常与
        Level 4.5 导入链破坏缺陷，覆盖 4 类运行时异常 + 类型/契约缺陷）；
        levelN / levelN.5：恒为 N（level2.5 → 25，level3.5 → 35，level4.5 → 45，
        level2 → 2，level3 → 3，level4 → 4）。

        2026-10 修正（A/B 阴性结果驱动）：此前 level2.5 → 2，与 level2
        共用 difficulty=2 的 BUG_PATTERNS_LEVEL2 池（assertion 风格缺陷，
        无 traceback 帧）——新定义的 BUG_PATTERNS_LEVEL25（运行时异常缺陷
        库：IndexError/KeyError/AttributeError/TypeError）从未被选中，
        导致位置感知定位阶段永远无法激活（A/B 定位命中 0/30 的根因）。
        现改为 25/35/45 独立整数码，_DIFFICULTY_PATTERNS 据此精确路由。
        """
        if self._difficulty == "mixed":
            return [rng.choice([1, 2, 3, 4, 5]) for _ in range(n)]
        # "level2.5" → 25，"level2.5-hard" → 26，"level3.5" → 35，"level4.5" → 45，"levelN" → N
        level_str = self._difficulty.replace("level", "")
        _FRACTIONAL_MAP = {"2.5": 25, "2.5-hard": 26, "3.5": 35, "4.5": 45}
        level = _FRACTIONAL_MAP.get(level_str)
        if level is None:
            level = int(level_str)
        return [level] * n

    def _pick_pattern(self, difficulty: int, rng: random.Random) -> dict[str, Any]:
        """按难度选模板（Level 3 走跨文件库（含 3.5 深链），Level 5 走契约库，其他走单文件库）。"""
        pool = _DIFFICULTY_PATTERNS.get(difficulty, BUG_PATTERNS)
        return rng.choice(pool)

    def _load_raw_data(self) -> None:
        """根据模板库生成指定数量的合成缺陷任务（P0 2.1 分层难度 + 2026-10 失败模式多样性）。"""
        rng = random.Random(self._seed)
        tasks: list[BenchmarkTask] = []
        seq = self._difficulty_sequence(self._task_count, rng)

        for i, difficulty in enumerate(seq):
            pattern = self._pick_pattern(difficulty, rng)
            noise = rng.randint(0, 9999)
            task_id = f"synthetic__{pattern['name']}_{i:04d}"

            # gold 定位目标（position_aware_ab._locate_accuracy 的金标准匹配键）：
            # 模板自带 suggested_function 时直接采用；跨文件任务取 target_module 的
            # 首个顶层函数（缺陷所在模块）；单文件无标注时留 None（保守口径）。
            suggested_function: str | None = pattern.get("suggested_function")
            # 跨文件任务（difficulty=3 / 35）：双模块（L3）或三模块深链（L3.5）构造
            # 35 = Level 3.5 独立整数码（_FRACTIONAL_MAP 映射 level3.5 → 35），
            # 与 3 同走跨文件分支（CROSS_FILE_DEEP_PATTERNS 无 template 键，
            # 单文件分支会 KeyError）；metadata.difficulty 按 3/35 原值记录
            # （_load_raw_data 的分布日志据此区分 level3 与 level3.5 任务）。
            if difficulty in (3, 35):
                num_files = int(pattern.get("num_files", 2))
                target_module = pattern.get("target_module", "module_b")
                base_modules = {
                    "module_a": pattern.get("module_a_code", ""),
                    "module_b": pattern.get("module_b_code", ""),
                    "module_c": pattern.get("module_c_code", ""),
                }
                # instance_code 是被调方（含缺陷）：双模块取 module_b，三模块取 module_c
                def_module_key = "module_c" if num_files >= 3 else "module_b"
                base_code = base_modules.get(def_module_key, pattern.get("module_b_code", ""))
                fixed_code = base_modules.get(
                    "module_c_fixed", pattern.get("fixed_module_c_code", "")
                ) or pattern.get("fixed_module_b_code", "")
                module_b_code = base_code + f"\n# noise_seed_b={noise}\n"
                task = BenchmarkTask(
                    task_id=task_id,
                    repo_name=f"synthetic/{pattern['name']}",
                    problem_statement=pattern["description"],
                    # 跨文件任务：instance_code 是被调方（含缺陷）模块源码
                    # （双模块 = module_b，三模块 = module_c）。run_benchmark 按
                    # task_id 末段命名为 <task_id 末段>.py 落盘，伴生模块
                    # （module_a/b/c）经 _write_cross_file_modules 物化为
                    # <module_name>.py；测试代码 import module_c 时由
                    # auto_fix_imports 解析到同目录伴生文件。定位/探针的
                    # target_module 经 nodes._resolve_target_module 解析为
                    # cross_file_plan.target_modules（如 module_c），与被调方
                    # 真实文件名口径一致。
                    instance_code=module_b_code,
                    test_code=pattern["test_cases"],
                    expected_pass_count=pattern["expected_pass"],
                    total_test_count=pattern["total_tests"],
                    metadata={
                        "bug_type": pattern["bug_type"],
                        "pattern_name": pattern["name"],
                        "source": "synthetic",
                        "noise_seed": noise,
                        "difficulty": difficulty,
                        "is_cross_file": True,
                        "module_a_code": pattern.get("module_a_code", ""),
                        "module_a_name": "module_a",
                        "module_b_code": pattern.get("module_b_code", ""),
                        "module_b_name": "module_b",
                        "module_c_code": pattern.get("module_c_code", ""),
                        "module_c_name": "module_c",
                        "target_module": target_module,
                        "fixed_module_code": fixed_code,
                        "num_files": num_files,
                        "dep_chain": pattern.get("dep_chain"),
                        "suggested_function": suggested_function,
                    },
                )
            else:
                # 单文件任务（Level 1/2/2.5/4/4.5）：历史口径 + gold 定位目标
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
                        "trigger_exception": pattern.get("trigger_exception"),
                        "suggested_function": suggested_function,
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
