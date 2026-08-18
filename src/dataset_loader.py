"""
数据集加载模块：支持 SWE-bench 和 Defects4J-Python 格式的标准数据集。

提供统一的数据集接口，将不同基准测试的数据加载为 AITester 可消费的 Task 对象。

使用方式：
    from src.dataset_loader import SWEBenchDataset, Defects4JPYDataset, load_dataset
    dataset = SWEBenchDataset("full")
    for task in dataset.tasks:
        result = run_single_task(task)
"""

from __future__ import annotations

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── 数据模型 ─────────────────────────────────────────────────────────────────


@dataclass
class BenchmarkTask:
    """
    基准测试任务标准模型。

    所有数据集加载器均输出此格式的任务，便于 AITester 统一消费。

    属性:
        task_id: 任务唯一标识（如 "django__django-12345"）。
        repo_name: 仓库名称（如 "django/django"）。
        problem_statement: 问题描述 / bug 报告文本。
        instance_code: 有缺陷的原始代码（将被 AITester 分析并修复）。
        test_code: 对应的测试代码（用于验证修复结果）。
        expected_pass_count: 期望通过的最小测试用例数。
        total_test_count: 总测试用例数。
        metadata: 附加元数据（如 GitHub issue 链接、commit hash 等）。
    """

    task_id: str
    repo_name: str
    problem_statement: str
    instance_code: str
    test_code: str
    expected_pass_count: int
    total_test_count: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed_count(self) -> int:
        """已通过的测试数（初始为 0，随修复过程更新）。"""
        return self.metadata.get("passed_count", 0)

    @property
    def pass_rate(self) -> float:
        """通过率（0.0 - 100.0）。"""
        if self.total_test_count == 0:
            return 0.0
        return (self.passed_count / self.total_test_count) * 100.0

    def mark_passed(self, count: int) -> None:
        """记录本轮修复后通过的测试数。"""
        self.metadata["passed_count"] = count
        logger.debug(
            "任务 %s: 通过 %d/%d 测试，通过率 %.1f%%",
            self.task_id,
            count,
            self.total_test_count,
            self.pass_rate,
        )


# ─── 抽象基类 ─────────────────────────────────────────────────────────────────


class BaseDatasetLoader(ABC):
    """
    数据集加载器抽象基类。

    所有具体数据集实现均应继承此类，实现 _load_raw_data() 方法。

    属性:
        data_dir: 数据集根目录（默认为 ~/.cache/aitester/<dataset_name>/）。
        subset: 数据子集名称（如 "full", "lite", "mini"），None 表示全部。
    """

    DATASET_NAME: str = "base"
    DEFAULT_CACHE_DIR: str = os.path.join(os.path.expanduser("~"), ".cache", "aitester")

    def __init__(self, subset: str | None = None) -> None:
        """
        初始化数据集加载器。

        Args:
            subset: 数据子集名称。None 表示加载全部数据。
        """
        self.subset = subset
        self.data_dir = os.path.join(self.DEFAULT_CACHE_DIR, self.DATASET_NAME)
        self._tasks: list[BenchmarkTask] = []
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """确保数据已加载（惰性加载模式）。"""
        if not self._loaded:
            self._load_raw_data()
            self._loaded = True

    @property
    def tasks(self) -> list[BenchmarkTask]:
        """返回所有任务列表（惰性加载）。"""
        self._ensure_loaded()
        return self._tasks

    @property
    def task_ids(self) -> list[str]:
        """返回所有任务 ID 列表。"""
        return [t.task_id for t in self.tasks]

    @property
    def size(self) -> int:
        """数据集规模（任务总数）。"""
        return len(self.tasks)

    @abstractmethod
    def _load_raw_data(self) -> None:
        """
        加载原始数据并填充 self._tasks。

        子类必须实现此方法。加载失败时应抛出 RuntimeError 而非静默忽略。
        """
        raise NotImplementedError

    def __len__(self) -> int:
        return self.size

    def __iter__(self) -> Iterator[BenchmarkTask]:
        self._ensure_loaded()
        return iter(self._tasks)

    def get_task_by_id(self, task_id: str) -> BenchmarkTask | None:
        """
        按 task_id 查找任务。

        Args:
            task_id: 任务唯一标识。

        Returns:
            匹配的任务对象，未找到时返回 None。
        """
        self._ensure_loaded()
        for task in self._tasks:
            if task.task_id == task_id:
                return task
        return None

    def filter_by_repo(self, repo_pattern: str) -> list[BenchmarkTask]:
        """
        按仓库名称正则过滤任务。

        Args:
            repo_pattern: 正则表达式模式（如 "django" 匹配所有 django 相关任务）。

        Returns:
            匹配的任务列表。
        """
        self._ensure_loaded()
        pattern = re.compile(repo_pattern, re.IGNORECASE)
        return [t for t in self._tasks if pattern.search(t.repo_name)]


# ─── SWE-bench 数据集加载器 ───────────────────────────────────────────────────


class SWEBenchDataset(BaseDatasetLoader):
    """
    SWE-bench 风格数据集加载器。

    SWE-bench（Software Engineering Bench）是业界标准的大模型代码修复基准，
    包含来自真实开源仓库的 bug-fix 配对数据。

    数据格式说明：
        每个任务对应一个 JSON 文件，包含以下字段：
        - instance_id: 任务唯一标识（如 "django__django-12345"）
        - repository: 仓库路径（如 "django/django"）
        - problem_statement: GitHub issue 描述
        - test_before_patches: 原始测试代码
        - patch: 官方修复补丁（用于验证）

    注意：由于 SWE-bench 需要大量手动下载和数据准备，
    本加载器默认从本地缓存目录加载 JSON 文件。
    若缓存目录不存在，会尝试从 HuggingFace 自动下载（需网络连接）。

    使用方式：
        dataset = SWEBenchDataset(subset="full")
        for task in dataset.tasks:
            logger.info("%s: %s", task.task_id, task.problem_statement[:50])
    """

    DATASET_NAME = "swe_bench"

    # 可选子集及其对应的任务数量（用于快速预览）
    SUBSET_MAP: dict[str, int] = {
        "lite": 500,  # Lite 子集：500 个任务，适合快速验证
        "mini": 50,  # Mini 子集：50 个任务，适合开发调试
        "full": 2294,  # 完整数据集：2294 个任务
    }

    def _load_raw_data(self) -> None:
        """
        从本地缓存加载 SWE-bench 数据。

        优先从 data_dir 读取 JSONL 文件；
        若文件不存在，打印提示并返回空列表（允许 gracefully degrade）。
        """
        # 清空任务列表，避免重复加载时数据累积
        self._tasks.clear()

        jsonl_path = os.path.join(self.data_dir, "swe_bench_instances.jsonl")

        if not os.path.exists(jsonl_path):
            logger.warning(
                "SWE-bench 数据未找到: %s\n"
                "请先下载数据集（参考 README.md 中的复现步骤），"
                "或从 HuggingFace 下载后放入 %s/",
                jsonl_path,
                self.data_dir,
            )
            return

        loaded = 0
        with open(jsonl_path, encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning("JSON 解析失败（第 %d 行）: %s", line_num, e)
                    continue

                # 构建 BenchmarkTask
                task_id = data.get("instance_id", f"swe_{line_num}")
                repo_name = data.get("repository", "unknown")
                problem_statement = data.get(
                    "problem_statement",
                    f"Fix bug in {repo_name} ({task_id})",
                )
                test_code = data.get("test_before_patches", "")
                instance_code = data.get("problem_statement", "")

                total_tests = data.get("n_tests_before", 0) or data.get("n_tests_after", 0)
                expected_pass = data.get("pass_num_before", 0) or 0
                total_pass = data.get("pass_num_after", 0) or total_tests

                task = BenchmarkTask(
                    task_id=task_id,
                    repo_name=repo_name,
                    problem_statement=problem_statement,
                    instance_code=instance_code,
                    test_code=test_code,
                    expected_pass_count=expected_pass,
                    total_test_count=total_pass if total_pass > 0 else total_tests,
                    metadata={
                        "repository": repo_name,
                        "instance_id": task_id,
                        "original_pass_num": expected_pass,
                        "final_pass_num": total_pass,
                        "source": "swe_bench",
                    },
                )
                self._tasks.append(task)
                loaded += 1

        logger.info("SWE-bench 加载完成：%d 个任务", loaded)

    @classmethod
    def download_from_huggingface(
        cls,
        cache_dir: str | None = None,
        subset: str = "lite",
    ) -> str:
        """
        从 HuggingFace 下载指定子集的 SWE-bench 数据到本地缓存。

        Args:
            cache_dir: 缓存目录，默认为 ~/.cache/aitester/swe_bench/。
            subset: 子集名称（"lite"/"mini"/"full"），默认 "lite"。

        Returns:
            下载完成后的本地路径。

        Raises:
            ImportError: datasets 库未安装时抛出。
            RuntimeError: 网络下载失败时抛出。
        """
        try:
            from datasets import load_dataset
        except ImportError:
            raise ImportError("请下载 HuggingFace datasets 库: pip install datasets")

        target_dir = cache_dir or cls.DEFAULT_CACHE_DIR
        os.makedirs(target_dir, exist_ok=True)

        split_map = {"mini": "lite", "lite": "dev", "full": "full"}
        split = split_map.get(subset, "dev")

        logger.info("正在从 HuggingFace 下载 SWE-bench [%s] 子集 ...", subset)
        try:
            dataset = load_dataset("princeton-nlp/SWE-bench", split=split, streaming=False)
        except Exception as e:
            raise RuntimeError(f"SWE-bench 下载失败: {e}") from e

        output_path = os.path.join(target_dir, "swe_bench_instances.jsonl")
        with open(output_path, "w", encoding="utf-8") as f:
            for item in dataset:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info("SWE-bench [%s] 下载完成，已保存至: %s", subset, output_path)
        return output_path


# ─── Defects4J-Python 数据集加载器 ────────────────────────────────────────────


class Defects4JPYDataset(BaseDatasetLoader):
    """
    Defects4J-Python 风格数据集加载器。

    Defects4J 是 Java 生态中最著名的缺陷基准，Defects4J-Python 是其 Python 移植版本，
    提供真实项目中的历史缺陷修复配对数据。

    本加载器从本地目录解析，若无数据则返回空列表并提示用户。
    """

    DATASET_NAME = "defects4j_python"

    KNOWN_PROJECTS = [
        "requests",
        "pytest",
        "httpie",
        "matplotlib",
        "numpy",
        "pandas",
        "scikit-learn",
    ]

    def _load_raw_data(self) -> None:
        """
        从本地目录加载 Defects4J-Python 数据。

        目录结构:
            defects4j_python/projects/<project_name>/<version>/
                buggy/      # 有缺陷的代码
                fixed/      # 修复后的代码
                tests/      # 测试套件
                info.json   # 元数据
        """
        # 清空任务列表，避免重复加载时数据累积
        self._tasks.clear()

        projects_dir = os.path.join(self.data_dir, "projects")

        if not os.path.exists(projects_dir):
            logger.warning(
                "Defects4J-Python 数据未找到: %s\n请从 https://github.com/rustcodex/defects4jpython 下载数据",
                projects_dir,
            )
            return

        loaded = 0
        for project_name in os.listdir(projects_dir):
            project_dir = os.path.join(projects_dir, project_name)
            if not os.path.isdir(project_dir):
                continue
            for version_dir in os.listdir(project_dir):
                version_path = os.path.join(project_dir, version_dir)
                info_path = os.path.join(version_path, "info.json")
                if not os.path.exists(info_path):
                    continue
                try:
                    with open(info_path, encoding="utf-8") as f:
                        info = json.load(f)
                except json.JSONDecodeError:
                    continue

                buggy_code = ""
                buggy_dir = os.path.join(version_path, "buggy")
                if os.path.isdir(buggy_dir):
                    for fname in os.listdir(buggy_dir):
                        if fname.endswith(".py"):
                            with open(os.path.join(buggy_dir, fname), encoding="utf-8") as ff:
                                buggy_code += ff.read() + "\n"

                test_code = ""
                tests_dir = os.path.join(version_path, "tests")
                if os.path.isdir(tests_dir):
                    for fname in sorted(os.listdir(tests_dir)):
                        if fname.startswith("test_") and fname.endswith(".py"):
                            with open(os.path.join(tests_dir, fname), encoding="utf-8") as ff:
                                test_code += ff.read() + "\n"

                task_id = f"{project_name}__{version_dir}"
                test_funcs = re.findall(r"def test_\w+", test_code)
                total_tests = len(test_funcs)
                expected_pass = info.get("expected_pass", total_tests)

                task = BenchmarkTask(
                    task_id=task_id,
                    repo_name=project_name,
                    problem_statement=info.get("description", f"Bug in {project_name}"),
                    instance_code=buggy_code,
                    test_code=test_code,
                    expected_pass_count=expected_pass,
                    total_test_count=total_tests,
                    metadata={
                        "project": project_name,
                        "version": version_dir,
                        "bug_type": info.get("bug_type", "unknown"),
                        "source": "defects4j_python",
                    },
                )
                self._tasks.append(task)
                loaded += 1

        logger.info("Defects4J-Python 加载完成：%d 个任务", loaded)


# ─── 内置示例数据集 ────────────────────────────────────────────────────────────


class InMemoryDataset(BaseDatasetLoader):
    """
    内置示例数据集：无需外部下载，直接提供用于快速验证的测试任务。

    适用于离线环境和单元测试。
    """

    DATASET_NAME = "in_memory"

    def __init__(self, subset: str | None = None) -> None:
        super().__init__()

    def _load_raw_data(self) -> None:
        # InMemoryDataset 的数据由 add_sample_tasks() 在 __init__ 中手动填充，
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


# ─── 便捷工厂函数 ─────────────────────────────────────────────────────────────


def load_dataset(
    name: str,
    subset: str | None = None,
    **kwargs: Any,
) -> BaseDatasetLoader:
    """
    根据数据集名称创建对应的加载器实例（工厂函数）。

    支持的名称：
        - "swe_bench" 或 "swebench": SWE-bench 数据集
        - "defects4j_python" 或 "d4j_py": Defects4J-Python 数据集
        - "in_memory": 内置示例数据集
        - 其他名称返回 InMemoryDataset（允许 graceful degradation）

    Args:
        name: 数据集名称。
        subset: 数据子集名称（可选）。
        **kwargs: 其他传递给构造函数的关键字参数。

    Returns:
        对应的数据集加载器实例。
    """
    name_lower = name.lower().replace("-", "_").replace(" ", "_")

    dataset_map: dict[str, type] = {
        "examples": InMemoryDataset,
        "swe_bench": SWEBenchDataset,
        "swebench": SWEBenchDataset,
        "defects4j_python": Defects4JPYDataset,
        "d4j_py": Defects4JPYDataset,
        "in_memory": InMemoryDataset,
        # "synthetic": SyntheticDataset,  # 使用懒加载避免循环导入
        # "synth": SyntheticDataset,  # 使用懒加载避免循环导入
    }

    # 懒加载 synthetic 以避免循环导入
    if name_lower in ("synthetic", "synth"):
        from src.synthetic_dataset import SyntheticDataset

        return SyntheticDataset(subset=subset, **kwargs)

    loader_class = dataset_map.get(name_lower, InMemoryDataset)
    instance = loader_class(subset=subset, **kwargs)
    # InMemoryDataset（含 "examples" 别名）需要预填充示例任务
    if isinstance(instance, InMemoryDataset):
        instance.add_sample_tasks()
    return instance


def get_available_datasets() -> list[str]:
    """
    返回当前支持的所有数据集名称列表。

    Returns:
        数据集名称列表。
    """
    return list(
        {
            "swe_bench",
            "swebench",
            "defects4j_python",
            "d4j_py",
            "in_memory",
        }
    )


if __name__ == "__main__":
    # 快速验证：加载内置示例数据集
    ds = InMemoryDataset.create_with_samples()
    logger.info("内置示例数据集规模: %d 个任务", ds.size)
    for task in ds.tasks:
        logger.info("  - %s: %s", task.task_id, task.problem_statement)
