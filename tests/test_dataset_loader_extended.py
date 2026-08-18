"""
补充测试：dataset_loader.py 未覆盖路径的本地数据测试。

覆盖范围：
    - BenchmarkTask：passed_count、pass_rate 属性计算、mark_passed
    - InMemoryDataset：add_task、add_sample_tasks、__len__/__iter__
    - SWEBenchDataset：空 JSONL、只有一行、字段缺失 defaults、下载失败
    - Defects4JPYDataset：info.json 含 bug_type、版本目录命名、UTF-8 编码
    - load_dataset：各别名、错误名称回退
    - BaseDatasetLoader：抽象行为、get_task_by_id、filter_by_repo
"""

import json
from unittest.mock import patch

import pytest


class TestBenchmarkTaskProperties:
    """测试 BenchmarkTask 的属性计算逻辑。"""

    def test_passed_count_defaults_to_zero(self):
        """未设置 passed_count 时默认返回 0。"""
        from src.dataset_loader import BenchmarkTask

        task = BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=5,
        )
        assert task.passed_count == 0

    def test_pass_rate_calculation(self):
        """通过率按公式 (passed_count / total_test_count) * 100 计算。"""
        from src.dataset_loader import BenchmarkTask

        task = BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=10,
        )
        task.mark_passed(7)
        assert task.pass_rate == 70.0

    def test_pass_rate_with_fraction(self):
        """通过率可为浮点数（非整除场景）。"""
        from src.dataset_loader import BenchmarkTask

        task = BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=3,
        )
        task.mark_passed(1)
        assert abs(task.pass_rate - 33.3333) < 0.01

    def test_mark_passed_updates_metadata(self):
        """mark_passed 将计数写入 metadata。"""
        from src.dataset_loader import BenchmarkTask

        task = BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=5,
        )
        task.mark_passed(3)
        assert task.metadata["passed_count"] == 3

    def test_metadata_isolation_between_tasks(self):
        """不同任务的 metadata 相互独立。"""
        from src.dataset_loader import BenchmarkTask

        t1 = BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=5,
        )
        t2 = BenchmarkTask(
            task_id="t2",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=5,
        )
        t1.mark_passed(2)
        assert t2.passed_count == 0

    def test_pass_rate_zero_when_total_is_zero(self):
        """total_test_count 为 0 时通过率为 0.0（避免除零）。"""
        from src.dataset_loader import BenchmarkTask

        task = BenchmarkTask(
            task_id="t1",
            repo_name="r",
            problem_statement="",
            instance_code="",
            test_code="",
            expected_pass_count=0,
            total_test_count=0,
        )
        assert task.pass_rate == 0.0


class TestInMemoryDatasetMethods:
    """测试 InMemoryDataset 方法。"""

    def test_init_without_subset(self):
        """不传 subset 时也能正常初始化。"""
        from src.dataset_loader import InMemoryDataset

        ds = InMemoryDataset()
        assert ds.subset is None
        assert ds._tasks == []

    def test_add_task_appends(self):
        """add_task 将任务追加到 _tasks 列表。"""
        from src.dataset_loader import BenchmarkTask, InMemoryDataset

        ds = InMemoryDataset()
        task = BenchmarkTask(
            task_id="custom__1",
            repo_name="custom",
            problem_statement="test",
            instance_code="x=1",
            test_code="def test_x(): pass",
            expected_pass_count=0,
            total_test_count=1,
        )
        ds.add_task(task)
        assert len(ds._tasks) == 1
        assert ds._tasks[0].task_id == "custom__1"

    def test_create_with_samples_populates_three_tasks(self):
        """create_with_samples 生成三个示例任务。"""
        from src.dataset_loader import InMemoryDataset

        ds = InMemoryDataset.create_with_samples()
        assert len(ds._tasks) == 3
        task_ids = [t.task_id for t in ds._tasks]
        assert "examples__calculator_divide" in task_ids
        assert "examples__binary_search" in task_ids
        assert "examples__is_palindrome" in task_ids

    def test_len_after_add_task(self):
        """add_task 后 _tasks 长度正确递增。"""
        from src.dataset_loader import BenchmarkTask, InMemoryDataset

        ds = InMemoryDataset()
        assert len(ds._tasks) == 0
        ds.add_task(
            BenchmarkTask(
                task_id="t1",
                repo_name="r",
                problem_statement="",
                instance_code="",
                test_code="",
                expected_pass_count=0,
                total_test_count=1,
            )
        )
        assert len(ds._tasks) == 1

    def test_iter_over_empty_dataset(self):
        """空数据集迭代返回空列表。"""
        from src.dataset_loader import InMemoryDataset

        ds = InMemoryDataset()
        assert list(ds._tasks) == []


class TestSWEBenchDatasetLocal:
    """测试 SWEBenchDataset 的本地文件加载（不涉及网络）。"""

    def test_load_empty_jsonl(self, tmp_path):
        """空 JSONL 文件加载后大小为 0。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        jsonl_path.write_text("", encoding="utf-8")

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 0

    def test_load_single_minimal_entry(self, tmp_path):
        """单行极简数据加载后字段有默认值。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        jsonl_path.write_text(json.dumps({"instance_id": "single__task"}) + "\n", encoding="utf-8")

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 1
        task = ds.tasks[0]
        assert task.repo_name == "unknown"
        assert task.problem_statement.startswith("Fix bug in unknown")
        assert task.instance_code == ""
        assert task.test_code == ""
        assert task.total_test_count == 0
        assert task.expected_pass_count == 0

    def test_load_skips_invalid_json_lines(self, tmp_path):
        """JSON 解析失败的行被跳过。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        lines = [
            json.dumps({"instance_id": "valid__1"}),
            '{"instance_id": "broken",',
            json.dumps({"instance_id": "valid__2"}),
        ]
        jsonl_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 2
        task_ids = [t.task_id for t in ds.tasks]
        assert "valid__1" in task_ids
        assert "valid__2" in task_ids

    def test_n_tests_after_used_as_fallback(self, tmp_path):
        """n_tests_after 作为 total_tests 的后备字段。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        data = {
            "instance_id": "test__1",
            "repository": "repo/test",
            "n_tests_before": 5,
            "n_tests_after": 8,
            "pass_num_before": 3,
            "pass_num_after": 6,
        }
        jsonl_path.write_text(json.dumps(data) + "\n", encoding="utf-8")

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        task = ds.tasks[0]
        assert task.total_test_count == 6

    def test_download_missing_datasets_library(self):
        """缺少 datasets 库时抛出 ImportError。"""
        from src.dataset_loader import SWEBenchDataset

        with patch.dict("sys.modules", {"datasets": None}):
            with pytest.raises(ImportError, match="pip install datasets"):
                SWEBenchDataset.download_from_huggingface()

    def test_download_network_error(self):
        """下载时网络错误抛出 RuntimeError。"""
        from src.dataset_loader import SWEBenchDataset

        with patch("src.dataset_loader.load_dataset", side_effect=Exception("network timeout")):
            with pytest.raises(RuntimeError, match="SWE-bench 下载失败"):
                SWEBenchDataset.download_from_huggingface()

    def test_load_missing_jsonl_returns_empty(self, tmp_path):
        """JSONL 文件不存在时返回空列表不抛异常。"""
        from src.dataset_loader import SWEBenchDataset

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path / "nonexistent")
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 0


class TestDefects4JPYDatasetLocal:
    """测试 Defects4JPYDataset 的本地目录加载。"""

    def test_load_info_with_bug_type(self, tmp_path):
        """info.json 含 bug_type 时正确写入 metadata。"""
        from src.dataset_loader import Defects4JPYDataset

        proj_dir = tmp_path / "projects" / "mylib" / "v1.0"
        proj_dir.mkdir(parents=True)
        (proj_dir / "info.json").write_text(
            json.dumps({"description": "Fix null pointer", "bug_type": "null_safety"}),
            encoding="utf-8",
        )

        ds = Defects4JPYDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 1
        assert ds.tasks[0].metadata["bug_type"] == "null_safety"

    def test_load_version_with_dashes(self, tmp_path):
        """版本目录名含连字符时 task_id 正确。"""
        from src.dataset_loader import Defects4JPYDataset

        proj_dir = tmp_path / "projects" / "requests" / "v1-0-0"
        proj_dir.mkdir(parents=True)
        (proj_dir / "info.json").write_text("{}", encoding="utf-8")

        ds = Defects4JPYDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 1
        assert ds.tasks[0].task_id == "requests__v1-0-0"

    def test_load_with_utf8_buggy_file(self, tmp_path):
        """buggy 目录中的 UTF-8 中文代码正确读取。"""
        from src.dataset_loader import Defects4JPYDataset

        proj_dir = tmp_path / "projects" / "cnlib" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "info.json").write_text("{}", encoding="utf-8")
        buggy_dir = proj_dir / "buggy"
        buggy_dir.mkdir()
        (buggy_dir / "main.py").write_text(
            "# 注释：修复中文bug\ndef hello():\n    return '你好'",
            encoding="utf-8",
        )

        ds = Defects4JPYDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert "你好" in ds.tasks[0].instance_code

    def test_expected_pass_exceeds_total(self, tmp_path):
        """expected_pass 大于 total_tests 时仍能正常加载。"""
        from src.dataset_loader import Defects4JPYDataset

        proj_dir = tmp_path / "projects" / "edge" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "info.json").write_text(
            json.dumps({"description": "test", "expected_pass": 100}),
            encoding="utf-8",
        )

        ds = Defects4JPYDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 1
        assert ds.tasks[0].total_test_count == 0
        assert ds.tasks[0].expected_pass_count == 100

    def test_load_missing_projects_dir(self, tmp_path):
        """projects 目录不存在时返回空列表。"""
        from src.dataset_loader import Defects4JPYDataset

        ds = Defects4JPYDataset()
        ds.data_dir = str(tmp_path / "nonexistent")
        ds._loaded = False
        ds._load_raw_data()
        assert ds.size == 0


class TestLoadDatasetFactory:
    """测试 load_dataset 工厂函数。"""

    def test_load_by_full_name(self):
        """使用完整名称加载数据集。"""
        from src.dataset_loader import Defects4JPYDataset, InMemoryDataset, SWEBenchDataset, load_dataset

        assert isinstance(load_dataset("swe_bench"), SWEBenchDataset)
        assert isinstance(load_dataset("defects4j_python"), Defects4JPYDataset)
        assert isinstance(load_dataset("in_memory"), InMemoryDataset)

    def test_load_by_alias(self):
        """使用别名加载数据集。"""
        from src.dataset_loader import Defects4JPYDataset, SWEBenchDataset, load_dataset

        assert isinstance(load_dataset("swebench"), SWEBenchDataset)
        assert isinstance(load_dataset("d4j_py"), Defects4JPYDataset)

    def test_unknown_name_returns_inmemory(self):
        """未知名称回退到 InMemoryDataset。"""
        from src.dataset_loader import InMemoryDataset, load_dataset

        ds = load_dataset("nonexistent_xyz")
        assert isinstance(ds, InMemoryDataset)

    def test_get_available_datasets_non_empty(self):
        """get_available_datasets 返回非空列表。"""
        from src.dataset_loader import get_available_datasets

        names = get_available_datasets()
        assert len(names) >= 3
        assert "swe_bench" in names
        assert "in_memory" in names


class TestBaseDatasetLoaderAbstract:
    """测试 BaseDatasetLoader 抽象基类行为。"""

    def test_cannot_instantiate_abstract(self):
        """不能直接实例化抽象基类。"""
        from src.dataset_loader import BaseDatasetLoader

        with pytest.raises(TypeError):
            BaseDatasetLoader()

    def test_subclass_without_impl_raises(self):
        """未实现 _load_raw_data 的子类调用时抛出 NotImplementedError。"""
        from src.dataset_loader import BaseDatasetLoader

        class IncompleteLoader(BaseDatasetLoader):
            pass

        loader = IncompleteLoader()
        with pytest.raises(NotImplementedError):
            loader._load_raw_data()

    def test_get_task_by_id_not_found(self, tmp_path):
        """找不到任务时返回 None。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        jsonl_path.write_text(json.dumps({"instance_id": "real__task"}) + "\n", encoding="utf-8")
        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.get_task_by_id("not_exist") is None

    def test_filter_by_repo_case_insensitive(self, tmp_path):
        """filter_by_repo 大小写不敏感。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        jsonl_path.write_text(
            json.dumps({"instance_id": "t1", "repository": "Django/django"}) + "\n",
            encoding="utf-8",
        )
        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        filtered = ds.filter_by_repo("django")
        assert len(filtered) == 1
        assert filtered[0].task_id == "t1"

    def test_task_ids_property(self, tmp_path):
        """task_ids 属性返回正确的 ID 列表。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        jsonl_path.write_text(
            json.dumps({"instance_id": "id1"}) + "\n" + json.dumps({"instance_id": "id2"}) + "\n",
            encoding="utf-8",
        )
        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert ds.task_ids == ["id1", "id2"]

    def test_len_dunder(self, tmp_path):
        """__len__ 返回数据集大小。"""
        from src.dataset_loader import SWEBenchDataset

        jsonl_path = tmp_path / "swe_bench_instances.jsonl"
        jsonl_path.write_text(json.dumps({"instance_id": "t1"}) + "\n", encoding="utf-8")
        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._loaded = False
        ds._load_raw_data()
        assert len(ds) == 1
