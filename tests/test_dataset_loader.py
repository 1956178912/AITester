"""测试 Dataset Loader 核心功能"""
from src.dataset_loader import BenchmarkTask, InMemoryDataset


class TestBenchmarkTask:
    """测试 BenchmarkTask"""

    def test_task_creation(self):
        """创建任务"""
        task = BenchmarkTask(
            task_id="t1",
            repo_name="test-repo",
            problem_statement="Test problem",
            instance_code="def foo(): pass",
            test_code="def test_foo(): assert True",
            expected_pass_count=1,
            total_test_count=1,
        )
        assert task.task_id == "t1"
        assert task.repo_name == "test-repo"
        assert task.expected_pass_count == 1

    def test_task_with_metadata(self):
        """带元数据创建任务"""
        task = BenchmarkTask(
            task_id="t2",
            repo_name="repo",
            problem_statement="Problem",
            instance_code="code",
            test_code="test",
            expected_pass_count=2,
            total_test_count=3,
            metadata={"difficulty": "medium"}
        )
        assert task.metadata["difficulty"] == "medium"

    def test_task_equality(self):
        """任务相等性"""
        t1 = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        t2 = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        assert t1 == t2


class TestInMemoryDataset:
    """测试内存数据集"""

    def test_create_dataset(self):
        """创建设置"""
        ds = InMemoryDataset()
        assert ds is not None

    def test_size_property(self):
        """数据集大小属性"""
        ds = InMemoryDataset()
        assert ds.size == 0

    def test_add_and_get_task(self):
        """添加和获取任务"""
        ds = InMemoryDataset()
        task = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        ds.add_task(task)
        retrieved = ds.get_task_by_id("t1")
        assert retrieved is not None
        assert retrieved.task_id == "t1"

    def test_task_ids_property(self):
        """获取任务 ID 列表属性"""
        ds = InMemoryDataset()
        task1 = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        task2 = BenchmarkTask("t2", "repo", "prob", "code", "test", 1, 1)
        ds.add_task(task1)
        ds.add_task(task2)
        ids = ds.task_ids
        assert "t1" in ids
        assert "t2" in ids

    def test_filter_by_repo(self):
        """按仓库过滤"""
        ds = InMemoryDataset()
        task1 = BenchmarkTask("t1", "repo1", "prob", "code", "test", 1, 1)
        task2 = BenchmarkTask("t2", "repo2", "prob", "code", "test", 1, 1)
        ds.add_task(task1)
        ds.add_task(task2)
        filtered = ds.filter_by_repo("repo1")
        assert len(filtered) == 1
        assert filtered[0].task_id == "t1"

    def test_tasks_property(self):
        """获取所有任务属性"""
        ds = InMemoryDataset()
        task = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        ds.add_task(task)
        tasks = ds.tasks
        assert len(tasks) == 1
