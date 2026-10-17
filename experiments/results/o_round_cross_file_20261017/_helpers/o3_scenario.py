"""O-3 跨文件场景定义（零 LLM，实验工件 helper）。

场景（确定性首轮失败 + 跨文件依赖）：

- 目标模块 ``o3_target.py``（被调方 / module under test）：
  ``add(a, b)`` 的 docstring 声明"返回 a 与 b 的和"，实现却是 ``a - b``
  ——**任何按意图写断言的测试在缺陷代码上必然失败**（N-1 repair 探针
  同款场景已实证）；这是"预置失败"的确定性来源，不改判分口径。
- 伴生模块 ``o3_caller.py``（调用方）：``from o3_target import add`` 并
  在 ``add_twice`` 中调用 —— 形成真实跨文件依赖边
  ``o3_caller -> o3_target``（benchmark 层 dep_chain 预置）。
- 任务 metadata：``is_cross_file=True`` + ``module_a_code/module_a_name``
  + ``dep_chain`` + ``target_module`` + ``suggested_function`` + gold
  ``test_cases``/``fixed``（供 M1 裁决链路使用，不改变本场景主目标）。

本模块只被 ``experiments/results/o_round_cross_file_20261017/_helpers/``
下的一次性运行脚本 import；正式测试文件自带同构常量（避免测试依赖
gitignored 工件目录）。
"""

from __future__ import annotations

from typing import Any

from src.datasets.dataset_inmemory import InMemoryDataset
from src.datasets.dataset_loader import BenchmarkTask

TARGET_MODULE = "o3_target"
CALLER_MODULE = "o3_caller"

# 缺陷版目标模块：docstring 声明 sum，实现为减法 → 按意图写的测试必然失败
TARGET_CODE = '''\
"""O-3 跨文件场景：被调方模块（预置确定性缺陷：add 实现为减法）。"""


def add(a, b):
    """Return the sum of a and b."""
    return a - b
'''

# 正确版目标模块（gold fixed；仅用于 M1 裁决材料与场景说明）
FIXED_TARGET_CODE = '''\
"""O-3 跨文件场景：被调方模块（gold 正确实现）。"""


def add(a, b):
    """Return the sum of a and b."""
    return a + b
'''

# 调用方模块：真实 import 被调方函数（跨文件依赖边来源）
CALLER_CODE = '''\
"""O-3 跨文件场景：调用方模块（import 被调方 add）。"""

from o3_target import add


def add_twice(a, b):
    return add(a, b) + add(a, b)
'''

# gold 官方测试（P2P / M1 裁决材料；也用于确定性说明"缺陷代码上必失败"）
GOLD_TEST = '''\
from o3_target import add


def test_add_positive():
    assert add(2, 3) == 5


def test_add_zero():
    assert add(0, 5) == 5
'''

# benchmark 层预置依赖边（与 _write_cross_file_state 的 dep_chain 口径一致）
DEP_CHAIN = [CALLER_MODULE, TARGET_MODULE]
DEP_EDGES: list[dict[str, Any]] = [
    {
        "source_module": CALLER_MODULE,
        "target_module": TARGET_MODULE,
        "symbol": "",
        "call_line": 0,
        "source": "benchmark_preset",
        "context": f"dep_chain[0]: {CALLER_MODULE} -> {TARGET_MODULE}",
    }
]


def build_task() -> BenchmarkTask:
    """构造单任务跨文件 benchmark 任务（真实 run_benchmark 装配用）。"""
    return BenchmarkTask(
        task_id=f"synthetic__{TARGET_MODULE}",
        repo_name="o3/cross-file",
        problem_statement=(
            "O-3 跨文件场景：被调方 add 把加法实现成减法，调用方 add_twice 依赖它；"
            "请修复被调方行为使调用链正确。"
        ),
        instance_code=TARGET_CODE,
        test_code=GOLD_TEST,
        expected_pass_count=2,
        total_test_count=2,
        metadata={
            "source": "synthetic",
            "is_cross_file": True,
            "difficulty": 3,
            "target_module": TARGET_MODULE,
            "suggested_function": "add",
            "module_a_name": CALLER_MODULE,
            "module_a_code": CALLER_CODE,
            "dep_chain": list(DEP_CHAIN),
            "num_files": 2,
            "test_cases": GOLD_TEST,
            "fixed": FIXED_TARGET_CODE,
            "o3_injected_scenario": True,
        },
    )


def build_dataset() -> InMemoryDataset:
    """构造单任务 InMemoryDataset（注入 run_benchmark 的 dataset 加载点）。"""
    dataset = InMemoryDataset()
    dataset.add_task(build_task())
    return dataset
