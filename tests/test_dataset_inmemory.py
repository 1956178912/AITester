"""
InMemoryDataset（内置示例数据集）单元测试。

覆盖 src/datasets/dataset_inmemory.py 的行为：
- create_with_samples 工厂方法
- add_task / add_sample_tasks
- _load_raw_data 留空语义（不抛异常、不依赖外部文件）
- BenchmarkTask 字段完整性
"""

from __future__ import annotations

import pytest


class TestInMemoryDataset:
    def test_create_with_samples_returns_3_tasks(self) -> None:
        """create_with_samples 应预填充 3 个示例任务。"""
        from src.datasets.dataset_loader import load_dataset

        ds = load_dataset("in_memory")
        tasks = list(ds)
        assert len(tasks) == 3
        # 任务 ID 按预定义顺序
        assert [t.task_id for t in tasks] == [
            "examples__calculator_divide",
            "examples__binary_search",
            "examples__is_palindrome",
        ]

    def test_add_task_appends_manually(self) -> None:
        """add_task 应允许手动追加自定义任务。"""
        from src.datasets.dataset_loader import BenchmarkTask, load_dataset

        ds = load_dataset("in_memory")
        custom = BenchmarkTask(
            task_id="custom__task",
            repo_name="custom",
            problem_statement="自定义任务",
            instance_code="def f():\n    return 1\n",
            test_code="def test_f():\n    assert f() == 1\n",
            expected_pass_count=1,
            total_test_count=1,
            metadata={"source": "manual"},
        )
        ds.add_task(custom)
        tasks = list(ds)
        assert len(tasks) == 4
        assert tasks[-1].task_id == "custom__task"

    def test_load_raw_data_is_noop(self) -> None:
        """_load_raw_data 留空：不抛异常、不产生任务（不清空已有任务）。"""
        from src.datasets.dataset_loader import load_dataset

        ds = load_dataset("in_memory")
        before = len(list(ds))
        ds._load_raw_data()  # noqa: SLF001 - 白盒测试内部方法
        assert len(list(ds)) == before  # 无副作用：方法既不清空也不追加

    def test_inmemory_dataset_field_completeness(self) -> None:
        """示例任务的 BenchmarkTask 字段完整性（防回归：字段名拼写漂移）。"""
        from src.datasets.dataset_loader import load_dataset

        ds = load_dataset("in_memory")
        tasks = list(ds)
        for t in tasks:
            assert t.task_id
            assert t.repo_name
            assert t.problem_statement
            assert t.instance_code
            assert t.test_code
            assert t.expected_pass_count == 0
            assert t.total_test_count == 3
            assert t.metadata.get("source") == "examples"

    def test_inmemory_dataset_class_name(self) -> None:
        """DATASET_NAME 类属性与工厂注册名一致（防回归）。"""
        from src.datasets.dataset_inmemory import InMemoryDataset

        assert InMemoryDataset.DATASET_NAME == "in_memory"
