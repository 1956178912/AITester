"""
单元测试：测试 dataset_loader 模块的核心功能。
覆盖 BenchmarkTask、BaseDatasetLoader、InMemoryDataset、load_dataset 工厂函数。
"""
import pytest
from src.dataset_loader import (
    BenchmarkTask,
    BaseDatasetLoader,
    SWEBenchDataset,
    Defects4JPYDataset,
    InMemoryDataset,
    load_dataset,
    get_available_datasets,
)


# ─── BenchmarkTask 测试 ────────────────────────────────────────────────────────


class TestBenchmarkTask:
    """测试 BenchmarkTask 数据模型。"""

    def test_task_creation(self):
        """验证任务对象可正常创建。"""
        task = BenchmarkTask(
            task_id="test__123",
            repo_name="test/repo",
            problem_statement="Fix bug",
            instance_code="def f(): pass",
            test_code="def test_f(): pass",
            expected_pass_count=0,
            total_test_count=2,
        )
        assert task.task_id == "test__123"
        assert task.passed_count == 0
        assert task.pass_rate == 0.0

    def test_mark_passed_updates_state(self):
        """验证 mark_passed 正确更新状态。"""
        task = BenchmarkTask(
            task_id="t1", repo_name="r", problem_statement="",
            instance_code="", test_code="", expected_pass_count=0, total_test_count=5,
        )
        task.mark_passed(3)
        assert task.passed_count == 3
        assert abs(task.pass_rate - 60.0) < 0.01

    def test_zero_total_tests_returns_zero_rate(self):
        """总测试数为 0 时通过率应为 0。"""
        task = BenchmarkTask(
            task_id="t2", repo_name="r", problem_statement="",
            instance_code="", test_code="", expected_pass_count=0, total_test_count=0,
        )
        assert task.pass_rate == 0.0


# ─── InMemoryDataset 测试 ──────────────────────────────────────────────────────


class TestInMemoryDataset:
    """测试内置内存数据集。"""

    def test_create_with_samples(self):
        """验证 create_with_samples 创建含示例任务的数据集。"""
        ds = InMemoryDataset.create_with_samples()
        assert ds.size == 3

    def test_iterate_tasks(self):
        """验证可迭代所有任务。"""
        ds = InMemoryDataset.create_with_samples()
        task_ids = [t.task_id for t in ds.tasks]
        assert len(task_ids) == 3
        assert "examples__calculator_divide" in task_ids

    def test_get_task_by_id(self):
        """验证按 ID 查找任务。"""
        ds = InMemoryDataset.create_with_samples()
        task = ds.get_task_by_id("examples__binary_search")
        assert task is not None
        assert task.repo_name == "examples/buggy_library"

    def test_get_nonexistent_task(self):
        """查找不存在任务应返回 None。"""
        ds = InMemoryDataset.create_with_samples()
        assert ds.get_task_by_id("nonexistent_task") is None

    def test_add_task_manually(self):
        """验证手动添加任务。"""
        ds = InMemoryDataset()
        task = BenchmarkTask(
            task_id="custom__1", repo_name="custom", problem_statement="test",
            instance_code="x=1", test_code="def test_x(): pass",
            expected_pass_count=0, total_test_count=1,
        )
        ds.add_task(task)
        assert ds.size == 1
        assert ds.tasks[0].task_id == "custom__1"

    def test_filter_by_repo(self):
        """验证按仓库过滤任务。"""
        ds = InMemoryDataset.create_with_samples()
        filtered = ds.filter_by_repo("calculator")
        assert len(filtered) == 1
        assert "calculator" in filtered[0].task_id


# ─── load_dataset 工厂函数测试 ─────────────────────────────────────────────────


class TestLoadDataset:
    """测试 load_dataset 工厂函数。"""

    def test_load_examples(self):
        """加载示例数据集。"""
        ds = load_dataset("examples")
        assert isinstance(ds, InMemoryDataset)

    def test_load_in_memory(self):
        """显式加载 in_memory。"""
        ds = load_dataset("in_memory")
        assert isinstance(ds, InMemoryDataset)

    def test_load_unknown_returns_inmemory(self):
        """未知数据集名称回退到 InMemoryDataset。"""
        ds = load_dataset("unknown_dataset_xyz")
        assert isinstance(ds, InMemoryDataset)

    def test_get_available_datasets(self):
        """验证可用数据集列表非空。"""
        names = get_available_datasets()
        assert "swe_bench" in names
        assert "in_memory" in names
        assert len(names) > 0


# ─── SWEBenchDataset 测试（无数据时 graceful degrade）───────────────────────────


class TestSWEBenchDataset:
    """测试 SWE-bench 数据集加载器（无数据时不崩溃）。"""

    def test_load_without_data_returns_empty(self):
        """未安装数据时返回空列表，不抛出异常。"""
        ds = SWEBenchDataset()
        # 故意设置一个不存在的缓存目录
        ds.data_dir = "/tmp/aitester_nonexistent_swe_bench_xyz"
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 0

    def test_subset_map(self):
        """验证子集映射包含预期的键。"""
        assert "lite" in SWEBenchDataset.SUBSET_MAP
        assert "mini" in SWEBenchDataset.SUBSET_MAP
        assert "full" in SWEBenchDataset.SUBSET_MAP
