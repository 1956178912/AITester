"""测试 Dataset Loader 核心功能"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from src.datasets.dataset_loader import (
    BaseDatasetLoader,
    BenchmarkTask,
    Defects4JPYDataset,
    InMemoryDataset,
    SWEBenchDataset,
    get_available_datasets,
    load_dataset,
)

# =============================================================================
# BenchmarkTask
# =============================================================================


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
            metadata={"difficulty": "medium"},
        )
        assert task.metadata["difficulty"] == "medium"

    def test_task_equality(self):
        """任务相等性"""
        t1 = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        t2 = BenchmarkTask("t1", "repo", "prob", "code", "test", 1, 1)
        assert t1 == t2

    # ── passed_count ─────────────────────────────────────────────────────────

    def test_passed_count_default_zero(self):
        """默认 passed_count 为 0"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 1)
        assert task.passed_count == 0

    def test_passed_count_from_metadata(self):
        """从 metadata 读取 passed_count"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 1, metadata={"passed_count": 5})
        assert task.passed_count == 5

    # ── pass_rate ────────────────────────────────────────────────────────────

    def test_pass_rate_normal(self):
        """正常通过率计算"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 10, metadata={"passed_count": 7})
        assert task.pass_rate == 70.0

    def test_pass_rate_zero_total(self):
        """total_test_count 为 0 时返回 0.0"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 0)
        assert task.pass_rate == 0.0

    def test_pass_rate_full(self):
        """全部通过返回 100.0"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 5, metadata={"passed_count": 5})
        assert task.pass_rate == 100.0

    # ── mark_passed ──────────────────────────────────────────────────────────

    def test_mark_passed_updates_metadata(self):
        """mark_passed 更新 metadata 中的 passed_count"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 5)
        task.mark_passed(3)
        assert task.passed_count == 3

    def test_mark_passed_multiple_calls(self):
        """多次调用 mark_passed 覆盖之前的值"""
        task = BenchmarkTask("t1", "r", "p", "c", "t", 0, 5)
        task.mark_passed(2)
        task.mark_passed(4)
        assert task.passed_count == 4


# =============================================================================
# BaseDatasetLoader
# =============================================================================


class TestBaseDatasetLoader:
    """测试 BaseDatasetLoader 抽象基类"""

    def test_subclass_without_implementation_raises(self):
        """未实现 _load_raw_data 的子类调用 tasks 应抛 NotImplementedError"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "fake"

            def _load_raw_data(self):
                raise NotImplementedError

        loader = FakeLoader()
        with pytest.raises(NotImplementedError):
            _ = loader.tasks

    def test_init_defaults(self):
        """初始化默认值"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "my_ds"

            def _load_raw_data(self):
                self._tasks = [BenchmarkTask("t1", "r", "p", "c", "t", 0, 1)]

        loader = FakeLoader()
        assert loader.subset is None
        assert loader.data_dir == os.path.join(os.path.expanduser("~"), ".cache", "aitester", "my_ds")
        assert loader._tasks == []
        assert loader._loaded is False

    def test_init_with_subset(self):
        """带 subset 参数初始化"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "my_ds"

            def _load_raw_data(self):
                self._tasks = [BenchmarkTask("t1", "r", "p", "c", "t", 0, 1)]

        loader = FakeLoader(subset="lite")
        assert loader.subset == "lite"

    def test_ensure_loaded_lazy(self):
        """惰性加载：_loaded 初始为 False，访问 tasks 后变为 True"""
        load_called = []

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "lazy"

            def _load_raw_data(self):
                load_called.append(1)
                self._tasks = [BenchmarkTask("t1", "r", "p", "c", "t", 0, 1)]

        loader = FakeLoader()
        assert loader._loaded is False
        _ = loader.tasks
        assert loader._loaded is True
        assert len(load_called) == 1  # 只加载一次

    def test_tasks_triggers_load(self):
        """tasks 属性触发加载"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "trig"

            def _load_raw_data(self):
                self._tasks = [BenchmarkTask("t1", "r", "p", "c", "t", 0, 1)]

        loader = FakeLoader()
        assert loader.size == 1
        assert loader._loaded is True

    def test_len(self):
        """__len__ 返回 size"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "len"

            def _load_raw_data(self):
                self._tasks = [
                    BenchmarkTask("t1", "r", "p", "c", "t", 0, 1),
                    BenchmarkTask("t2", "r", "p", "c", "t", 0, 1),
                ]

        loader = FakeLoader()
        assert len(loader) == 2

    def test_iter(self):
        """__iter__ 返回迭代器"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "iter"

            def _load_raw_data(self):
                self._tasks = [
                    BenchmarkTask("t1", "r", "p", "c", "t", 0, 1),
                    BenchmarkTask("t2", "r", "p", "c", "t", 0, 1),
                ]

        loader = FakeLoader()
        tasks = list(loader)
        assert len(tasks) == 2
        assert tasks[0].task_id == "t1"
        assert tasks[1].task_id == "t2"

    def test_get_task_by_id_found(self):
        """找到任务时返回对应对象"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "find"

            def _load_raw_data(self):
                self._tasks = [
                    BenchmarkTask("t1", "r", "p", "c", "t", 0, 1),
                    BenchmarkTask("t2", "r", "p", "c", "t", 0, 1),
                ]

        loader = FakeLoader()
        task = loader.get_task_by_id("t2")
        assert task is not None
        assert task.task_id == "t2"

    def test_get_task_by_id_not_found(self):
        """未找到任务时返回 None"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "nfound"

            def _load_raw_data(self):
                self._tasks = [BenchmarkTask("t1", "r", "p", "c", "t", 0, 1)]

        loader = FakeLoader()
        assert loader.get_task_by_id("nonexistent") is None

    def test_filter_by_repo_regex_case_insensitive(self):
        """filter_by_repo 使用正则且忽略大小写"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "filter"

            def _load_raw_data(self):
                self._tasks = [
                    BenchmarkTask("t1", "Django", "p", "c", "t", 0, 1),
                    BenchmarkTask("t2", "Flask", "p", "c", "t", 0, 1),
                    BenchmarkTask("t3", "django-rest", "p", "c", "t", 0, 1),
                ]

        loader = FakeLoader()
        results = loader.filter_by_repo("django")
        assert len(results) == 2
        ids = {r.task_id for r in results}
        assert ids == {"t1", "t3"}

    def test_filter_by_repo_no_match(self):
        """无匹配时返回空列表"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "nomatch"

            def _load_raw_data(self):
                self._tasks = [BenchmarkTask("t1", "django", "p", "c", "t", 0, 1)]

        loader = FakeLoader()
        assert loader.filter_by_repo("flask") == []

    def test_filter_by_repo_full_regex(self):
        """完整正则匹配"""

        class FakeLoader(BaseDatasetLoader):
            DATASET_NAME = "regex"

            def _load_raw_data(self):
                self._tasks = [
                    BenchmarkTask("t1", "proj-a", "p", "c", "t", 0, 1),
                    BenchmarkTask("t2", "proj-b", "p", "c", "t", 0, 1),
                ]

        loader = FakeLoader()
        results = loader.filter_by_repo(r"^proj-a$")
        assert len(results) == 1
        assert results[0].task_id == "t1"


# =============================================================================
# SWEBenchDataset
# =============================================================================


class TestSWEBenchDataset:
    """测试 SWEBenchDataset"""

    def test_dataset_name(self):
        """DATASET_NAME 正确"""
        assert SWEBenchDataset.DATASET_NAME == "swe_bench"

    def test_subset_map(self):
        """SUBSET_MAP 包含预期子集"""
        assert "lite" in SWEBenchDataset.SUBSET_MAP
        assert "mini" in SWEBenchDataset.SUBSET_MAP
        assert "full" in SWEBenchDataset.SUBSET_MAP
        assert SWEBenchDataset.SUBSET_MAP["lite"] == 500
        assert SWEBenchDataset.SUBSET_MAP["mini"] == 50
        assert SWEBenchDataset.SUBSET_MAP["full"] == 2294

    def test_load_raw_data_file_not_found(self, caplog):
        """JSONL 文件不存在时记录 warning 并返回空列表"""
        ds = SWEBenchDataset()
        # 重置 _loaded 标志，确保 _load_raw_data 会被调用
        ds._loaded = False
        with patch.object(ds, "data_dir", "/nonexistent/path"):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size 访问重新加载真实缓存
        assert ds.size == 0

    def test_load_raw_data_valid_file(self, tmp_path):
        """正常 JSONL 文件加载"""
        jsonl = tmp_path / "swe_bench_instances.jsonl"
        records = [
            {
                "instance_id": "django__django-12345",
                "repository": "django/django",
                "problem_statement": "Fix bug",
                "test_before_patches": "def test_x(): pass",
                "n_tests_before": 5,
                "pass_num_before": 3,
                "pass_num_after": 5,
            },
            {
                "instance_id": "flask__flask-67890",
                "repository": "pallets/flask",
                "problem_statement": "Another bug",
                "test_before_patches": "",
                "n_tests_before": 0,
                "pass_num_before": 0,
                "pass_num_after": 0,
            },
        ]
        jsonl.write_text("\n".join(json.dumps(r) for r in records) + "\n")

        ds = SWEBenchDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size/get_task_by_id 访问重新加载真实缓存

        assert ds.size == 2
        t1 = ds.get_task_by_id("django__django-12345")
        assert t1 is not None
        assert t1.repo_name == "django/django"
        assert t1.problem_statement == "Fix bug"
        assert t1.test_code == "def test_x(): pass"
        assert t1.total_test_count == 5
        assert t1.expected_pass_count == 3
        assert t1.metadata["source"] == "swe_bench"

        # 第二条：pass_num_after=0 时 fallback 到 n_tests_before
        t2 = ds.get_task_by_id("flask__flask-67890")
        assert t2 is not None
        assert t2.total_test_count == 0  # pass_num_after=0, n_tests_before=0

    def test_load_raw_data_empty_lines_skipped(self, tmp_path):
        """空行被跳过"""
        jsonl = tmp_path / "swe_bench_instances.jsonl"
        jsonl.write_text('{"instance_id": "t1", "repository": "r1"}\n\n\n{"instance_id": "t2", "repository": "r2"}\n')

        ds = SWEBenchDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size 访问重新加载真实缓存

        assert ds.size == 2

    def test_load_raw_data_json_decode_error_logged(self, tmp_path, caplog):
        """JSON 解析失败时记录 warning 并跳过该行"""
        import logging

        jsonl = tmp_path / "swe_bench_instances.jsonl"
        # 第二行是非法 JSON
        jsonl.write_text('{"instance_id": "t1"}\n{bad json\n')

        ds = SWEBenchDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            with caplog.at_level(logging.WARNING):
                ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size 访问重新加载真实缓存

        assert ds.size == 1  # 只加载第一行
        assert "JSON 解析失败" in caplog.text

    def test_load_raw_data_missing_fields_uses_defaults(self, tmp_path):
        """字段缺失时使用默认值"""
        jsonl = tmp_path / "swe_bench_instances.jsonl"
        jsonl.write_text(json.dumps({}) + "\n")

        ds = SWEBenchDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size/tasks 访问重新加载真实缓存

        assert ds.size == 1
        t = ds.tasks[0]
        assert t.task_id == "swe_1"  # line_num fallback
        assert t.repo_name == "unknown"
        assert t.problem_statement.startswith("Fix bug in unknown")

    def test_download_from_huggingface_import_error(self):
        """datasets 库未安装时抛 ImportError"""
        with patch("src.datasets.dataset_loader._datasets", None):
            with pytest.raises(ImportError, match="pip install datasets"):
                SWEBenchDataset.download_from_huggingface()

    def test_download_from_huggingface_success(self, tmp_path):
        """成功下载并写入子集专属 JSONL（文件名带子集标识，避免互相覆盖）"""
        mock_dataset = MagicMock()
        mock_dataset.__iter__ = lambda self: iter(
            [
                {"instance_id": "t1", "repository": "r1"},
                {"instance_id": "t2", "repository": "r2"},
            ]
        )

        mock_datasets = MagicMock()
        mock_datasets.load_dataset.return_value = mock_dataset

        with patch("src.datasets.dataset_loader._datasets", mock_datasets):
            output = SWEBenchDataset.download_from_huggingface(cache_dir=str(tmp_path), subset="mini")

        assert output == str(tmp_path / "swe_bench_mini_instances.jsonl")
        content = (tmp_path / "swe_bench_mini_instances.jsonl").read_text()
        lines = [line for line in content.strip().split("\n") if line]
        assert len(lines) == 2

    def test_download_from_huggingface_runtime_error(self):
        """下载失败时抛 RuntimeError"""
        mock_datasets = MagicMock()
        mock_datasets.load_dataset.side_effect = Exception("network error")

        with patch("src.datasets.dataset_loader._datasets", mock_datasets):
            with pytest.raises(RuntimeError, match="SWE-bench 下载失败"):
                SWEBenchDataset.download_from_huggingface()

    def test_download_split_mapping(self):
        """split 映射关系正确"""
        # mini→lite, lite→dev, full→full
        captures = []

        def fake_load(*args, **kwargs):
            captures.append(kwargs.get("split"))
            m = MagicMock()
            m.__iter__ = lambda self: iter([])
            return m

        mock_datasets = MagicMock()
        mock_datasets.load_dataset.side_effect = fake_load

        with patch("src.datasets.dataset_loader._datasets", mock_datasets):
            SWEBenchDataset.download_from_huggingface(subset="mini")
            SWEBenchDataset.download_from_huggingface(subset="lite")
            SWEBenchDataset.download_from_huggingface(subset="full")
            SWEBenchDataset.download_from_huggingface(subset="unknown")

        assert captures == ["lite", "dev", "full", "dev"]

    def test_download_default_dir_aligns_with_loader(self, tmp_path, monkeypatch):
        """回归锁：默认目录必须与加载器 data_dir（DEFAULT_CACHE_DIR/swe_bench/）一致，
        此前下载写到 ~/.cache/aitester/ 而加载器读 ~/.cache/aitester/swe_bench/，下载完永远找不到"""
        home_cache = str(tmp_path / "home_cache")
        monkeypatch.setattr(SWEBenchDataset, "DEFAULT_CACHE_DIR", home_cache)
        mock_dataset = MagicMock()
        mock_dataset.__iter__ = lambda self: iter([{"instance_id": "t1"}])
        mock_datasets = MagicMock()
        mock_datasets.load_dataset.return_value = mock_dataset

        with patch("src.datasets.dataset_loader._datasets", mock_datasets):
            output = SWEBenchDataset.download_from_huggingface(subset="mini")

        assert output == f"{home_cache}/swe_bench/swe_bench_mini_instances.jsonl"

    def test_load_raw_data_subset_reads_subset_file(self, tmp_path):
        """指定 subset 时读取子集专属文件 swe_bench_<subset>_instances.jsonl"""
        subset_file = tmp_path / "swe_bench_mini_instances.jsonl"
        subset_file.write_text(json.dumps({"instance_id": "t_mini", "repository": "r"}) + "\n")

        ds = SWEBenchDataset(subset="mini")
        ds.data_dir = str(tmp_path)
        ds._load_raw_data()

        assert ds.size == 1
        assert ds.tasks[0].task_id == "t_mini"

    def test_load_raw_data_no_subset_merges_and_dedups(self, tmp_path):
        """未指定 subset 时合并 data_dir 下所有子集文件，按 instance_id 去重"""
        legacy = tmp_path / "swe_bench_instances.jsonl"
        legacy.write_text(
            json.dumps({"instance_id": "t1", "repository": "r"})
            + "\n"
            + json.dumps({"instance_id": "t2", "repository": "r"})
            + "\n"
        )
        mini = tmp_path / "swe_bench_mini_instances.jsonl"
        mini.write_text(
            json.dumps({"instance_id": "t2", "repository": "r"})
            + "\n"
            + json.dumps({"instance_id": "t3", "repository": "r"})
            + "\n"
        )

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._load_raw_data()

        assert ds.size == 3
        assert [t.task_id for t in ds.tasks] == ["t1", "t2", "t3"]

    def test_instance_code_prefers_explicit_source_fields(self, tmp_path):
        """instance_code 优先取显式源码字段（instance_code > base_code），兜底才是 problem_statement"""
        jsonl = tmp_path / "swe_bench_instances.jsonl"
        jsonl.write_text(
            json.dumps({"instance_id": "a", "repository": "r", "instance_code": "def f(): pass"})
            + "\n"
            + json.dumps({"instance_id": "b", "repository": "r", "base_code": "def g(): pass"})
            + "\n"
            + json.dumps({"instance_id": "c", "repository": "r", "problem_statement": "bug text"})
            + "\n"
        )

        ds = SWEBenchDataset()
        ds.data_dir = str(tmp_path)
        ds._load_raw_data()

        by_id = {t.task_id: t for t in ds.tasks}
        assert by_id["a"].instance_code == "def f(): pass"
        assert by_id["b"].instance_code == "def g(): pass"
        assert by_id["c"].instance_code == "bug text"


# =============================================================================
# Defects4JPYDataset
# =============================================================================


class TestDefects4JPYDataset:
    """测试 Defects4JPYDataset"""

    def test_dataset_name(self):
        """DATASET_NAME 正确"""
        assert Defects4JPYDataset.DATASET_NAME == "defects4j_python"

    def test_known_projects(self):
        """KNOWN_PROJECTS 包含预期项目"""
        assert "requests" in Defects4JPYDataset.KNOWN_PROJECTS
        assert "pytest" in Defects4JPYDataset.KNOWN_PROJECTS

    def test_load_raw_data_dir_not_found(self, caplog):
        """projects 目录不存在时返回空列表"""
        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", "/nonexistent"):
            ds._load_raw_data()
        assert ds.size == 0

    def test_load_raw_data_valid_structure(self, tmp_path):
        """正常目录结构加载"""
        # 构造目录：projects/requests/v1/buggy/*.py, tests/*.py, info.json
        proj_dir = tmp_path / "projects" / "requests" / "v1"
        proj_dir.mkdir(parents=True)

        (proj_dir / "info.json").write_text(
            json.dumps(
                {
                    "description": "Request bug",
                    "expected_pass": 3,
                    "bug_type": "logic",
                }
            )
        )
        (proj_dir / "buggy").mkdir()
        (proj_dir / "buggy" / "main.py").write_text("def fetch(): pass\n")
        (proj_dir / "buggy" / "helper.py").write_text("def helper(): pass\n")
        (proj_dir / "tests").mkdir()
        (proj_dir / "tests" / "test_main.py").write_text("def test_a(): pass\n")
        (proj_dir / "tests" / "test_b.py").write_text("def test_b(): pass\n")
        (proj_dir / "tests" / "helper.py").write_text("# not a test\n")  # 不以 test_ 开头

        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size/tasks 访问重新加载（真实缓存为空）

        assert ds.size == 1
        t = ds.tasks[0]
        assert t.task_id == "requests__v1"
        assert t.repo_name == "requests"
        assert t.problem_statement == "Request bug"
        assert "def fetch" in t.instance_code
        assert "def helper" in t.instance_code
        assert "def test_a" in t.test_code
        assert "def test_b" in t.test_code
        assert t.total_test_count == 2  # 只算 test_*.py
        assert t.expected_pass_count == 3
        assert t.metadata["bug_type"] == "logic"

    def test_load_raw_data_info_json_decode_error(self, tmp_path):
        """info.json 解析失败时跳过该版本"""
        proj_dir = tmp_path / "projects" / "req" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "info.json").write_text("{bad json}")

        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()

        assert ds.size == 0

    def test_load_raw_data_no_info_json_skipped(self, tmp_path):
        """没有 info.json 的目录被跳过"""
        proj_dir = tmp_path / "projects" / "req" / "v1"
        proj_dir.mkdir(parents=True)
        # 不写 info.json

        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()

        assert ds.size == 0

    def test_load_raw_data_multiple_projects(self, tmp_path):
        """多项目多版本合并加载"""
        for proj in ("requests", "pytest"):
            vdir = tmp_path / "projects" / proj / "v1"
            vdir.mkdir(parents=True)
            (vdir / "info.json").write_text(json.dumps({"description": f"{proj} bug"}))

        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size/tasks 访问重新加载（真实缓存为空）

        assert ds.size == 2
        ids = {t.task_id for t in ds.tasks}
        assert "requests__v1" in ids
        assert "pytest__v1" in ids

    def test_load_raw_data_non_dir_entry_skipped(self, tmp_path):
        """projects 目录下的非目录条目被跳过"""
        (tmp_path / "projects").mkdir(parents=True)
        # 放一个普通文件
        (tmp_path / "projects" / "readme.txt").write_text("not a dir")

        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()

        assert ds.size == 0

    def test_load_raw_data_empty_test_code_total_zero(self, tmp_path):
        """无测试文件时 total_test_count 为 0"""
        proj_dir = tmp_path / "projects" / "empty_proj" / "v1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "info.json").write_text("{}")

        ds = Defects4JPYDataset()
        with patch.object(ds, "data_dir", str(tmp_path)):
            ds._load_raw_data()
            ds._loaded = True  # 阻止后续 size/tasks 访问重新加载（真实缓存为空）

        assert ds.size == 1
        assert ds.tasks[0].total_test_count == 0


# =============================================================================
# InMemoryDataset
# =============================================================================


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

    def test_load_raw_data_returns_none(self):
        """_load_raw_data 对 InMemoryDataset 返回 None（不抛异常）"""
        ds = InMemoryDataset()
        result = ds._load_raw_data()
        assert result is None

    def test_add_sample_tasks(self):
        """add_sample_tasks 添加 3 个示例任务"""
        ds = InMemoryDataset()
        ds.add_sample_tasks()
        assert ds.size == 3

        ids = [t.task_id for t in ds.tasks]
        assert "examples__calculator_divide" in ids
        assert "examples__binary_search" in ids
        assert "examples__is_palindrome" in ids

    def test_create_with_samples(self):
        """create_with_samples 类方法创建并填充示例"""
        ds = InMemoryDataset.create_with_samples()
        assert ds.size == 3
        assert ds.tasks[0].task_id == "examples__calculator_divide"

    def test_subset_passed_to_init(self):
        """__init__ 接受并存储 subset 参数"""
        ds = InMemoryDataset(subset="mini")
        assert ds.subset == "mini"

    def test_multiple_add_task(self):
        """多次 add_task 累积任务"""
        ds = InMemoryDataset()
        for i in range(5):
            ds.add_task(BenchmarkTask(f"t{i}", "r", "p", "c", "t", 0, 1))
        assert ds.size == 5

    def test_add_sample_tasks_idempotent(self):
        """多次调用 add_sample_tasks 会累积（非幂等）"""
        ds = InMemoryDataset()
        ds.add_sample_tasks()
        first_size = ds.size
        ds.add_sample_tasks()
        assert ds.size == first_size * 2

    def test_task_properties_on_sample_tasks(self):
        """示例任务的 passed_count / pass_rate / mark_passed 正常工作"""
        ds = InMemoryDataset.create_with_samples()
        task = ds.tasks[0]
        assert task.passed_count == 0
        assert task.pass_rate == 0.0
        task.mark_passed(2)
        assert task.passed_count == 2
        assert task.pass_rate == pytest.approx(66.6667)


# =============================================================================
# load_dataset 工厂函数
# =============================================================================


class TestLoadDataset:
    """测试 load_dataset 工厂函数"""

    def test_swe_bench(self):
        """swe_bench 名称返回 SWEBenchDataset 实例"""
        ds = load_dataset("swe_bench")
        assert isinstance(ds, SWEBenchDataset)
        # 将 data_dir 指向不存在的目录，确保加载 0 个任务（避免依赖本地缓存，环境无关）
        with patch.object(ds, "data_dir", "/nonexistent/path"):
            ds._load_raw_data()
            ds._loaded = True
        assert ds.size == 0

    def test_swebench_alias(self):
        """swebench（无下划线）别名也返回 SWEBenchDataset"""
        ds = load_dataset("swebench")
        assert isinstance(ds, SWEBenchDataset)

    def test_defects4j_python(self):
        """defects4j_python 名称返回 Defects4JPYDataset"""
        ds = load_dataset("defects4j_python")
        assert isinstance(ds, Defects4JPYDataset)

    def test_d4j_py_alias(self):
        """d4j_py 别名返回 Defects4JPYDataset"""
        ds = load_dataset("d4j_py")
        assert isinstance(ds, Defects4JPYDataset)

    def test_in_memory(self):
        """in_memory 返回 InMemoryDataset（带示例）"""
        ds = load_dataset("in_memory")
        assert isinstance(ds, InMemoryDataset)
        assert ds.size == 3  # add_sample_tasks 被自动调用

    def test_examples_alias(self):
        """examples 别名返回 InMemoryDataset（带示例）"""
        ds = load_dataset("examples")
        assert isinstance(ds, InMemoryDataset)
        assert ds.size == 3

    def test_unknown_returns_in_memory(self):
        """未知名称默认返回 InMemoryDataset"""
        ds = load_dataset("nonexistent_dataset")
        assert isinstance(ds, InMemoryDataset)
        assert ds.size == 3

    def test_case_insensitive(self):
        """名称大小写不敏感"""
        ds1 = load_dataset("SWE_BENCH")
        ds2 = load_dataset("swe_bench")
        assert type(ds1) is type(ds2)

    def test_hyphen_and_space_normalized(self):
        """连字符和空格被规范化为下划线"""
        ds = load_dataset("swe-bench")
        assert isinstance(ds, SWEBenchDataset)
        ds2 = load_dataset("defects4j python")
        assert isinstance(ds2, Defects4JPYDataset)

    def test_subset_passed_through(self):
        """subset 参数正确传递给构造函数"""
        ds = load_dataset("in_memory", subset="mini")
        assert ds.subset == "mini"

    def test_kwargs_passed_through(self):
        """额外 kwargs 传递给构造函数"""
        ds = load_dataset("in_memory", subset="full", extra_kwarg="test")
        # 只要不抛异常即视为通过（InMemoryDataset 接受 **kwargs）
        assert isinstance(ds, InMemoryDataset)

    def test_synthetic_lazy_load(self):
        """synthetic/synth 名称触发懒加载 SyntheticDataset"""
        from src.datasets.synthetic_dataset import SyntheticDataset

        # 验证可以导入（避免循环导入错误）
        ds = load_dataset("synthetic")
        assert isinstance(ds, SyntheticDataset)

        ds2 = load_dataset("synth")
        assert isinstance(ds2, SyntheticDataset)

    def test_synthetic_with_kwargs(self):
        """synthetic 携带 kwargs 也能正确传递"""
        from src.datasets.synthetic_dataset import SyntheticDataset

        ds = load_dataset("synthetic", subset="lite", foo="bar")
        assert isinstance(ds, SyntheticDataset)


# =============================================================================
# get_available_datasets
# =============================================================================


class TestGetAvailableDatasets:
    """测试 get_available_datasets"""

    def test_returns_list_of_names(self):
        """返回数据集名称列表"""
        names = get_available_datasets()
        assert isinstance(names, list)

    def test_contains_expected_names(self):
        """包含所有已知名称（与 load_dataset 的 dataset_map 同步，含别名）"""
        names = get_available_datasets()
        expected = {
            "swe_bench",
            "swebench",
            "defects4j_python",
            "d4j_py",
            "in_memory",
            "examples",
            "synthetic",
            "synth",
        }
        assert set(names) == expected

    def test_no_duplicates(self):
        """无重复名称（集合去重）"""
        names = get_available_datasets()
        assert len(names) == len(set(names))


# =============================================================================
# __main__ 块
# =============================================================================


class TestMainBlock:
    """测试 __main__ 执行块（通过 import 验证无错误）"""

    def test_main_block_runs_without_error(self, caplog):
        """直接运行模块不抛异常"""
        import logging

        with caplog.at_level(logging.INFO):
            # 模拟 __main__ 逻辑
            ds = InMemoryDataset.create_with_samples()
            assert ds.size == 3
