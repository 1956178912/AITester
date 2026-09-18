"""
3.4 Defects4J 初步适配验证（端到端冒烟测试）。

验证：
1. Defects4JPYDataset 加载器可正确实例化；
2. 无数据目录时优雅降级（返回空任务列表，不崩溃）；
3. 有完整目录结构时正确解析 info.json + buggy/tests 代码；
4. BenchmarkTask 字段完整性。

运行：
    pytest tests/test_defects4j_smoke.py -v
"""

from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)


class TestDefects4JPYDatasetSmoke:
    """3.4 Defects4J-Python 加载器冒烟验证。"""

    def test_instantiation_no_data_dir(self, tmp_path: pytest.TempPathFactory):
        """无数据目录时：实例化成功、tasks 为空、不抛异常。"""
        from src.datasets.dataset_loader import load_dataset

        loader = load_dataset("defects4j_python", data_dir=str(tmp_path.resolve()))
        assert loader is not None
        tasks = list(loader)
        assert tasks == []

    def test_load_with_valid_project_structure(self, tmp_path: pytest.TempPathFactory):
        """构造完整目录结构，验证加载器正确解析。"""
        from src.datasets.dataset_loader import load_dataset, BenchmarkTask

        # 构造 projects/requests/1.0/ 目录
        project_dir = tmp_path / "projects" / "requests" / "1.0"
        buggy_dir = project_dir / "buggy"
        fixed_dir = project_dir / "fixed"
        tests_dir = project_dir / "tests"
        for d in [buggy_dir, fixed_dir, tests_dir]:
            d.mkdir(parents=True)

        # 写入 buggy 代码
        (buggy_dir / "utils.py").write_text(
            "def add(a, b):\n    return a - b\n", encoding="utf-8"
        )

        # 写入测试
        (tests_dir / "test_utils.py").write_text(
            "from utils import add\n"
            "def test_add_normal():\n    assert add(2, 3) == 5\n"
            "def test_add_zero():\n    assert add(0, 0) == 0\n",
            encoding="utf-8",
        )

        # 写入 info.json
        info = {
            "description": "requests 1.0 中 add 函数逻辑错误",
            "bug_type": "logic_error",
            "expected_pass": 2,
        }
        (project_dir / "info.json").write_text(json.dumps(info), encoding="utf-8")

        # 加载
        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        tasks = list(loader)
        assert len(tasks) == 1, f"应加载 1 个任务，实际 {len(tasks)}"

        task = tasks[0]
        assert task.task_id == "requests__1.0"
        assert task.repo_name == "requests"
        assert "add" in task.instance_code
        assert "test_add_normal" in task.test_code
        assert task.total_test_count == 2
        assert task.metadata.get("bug_type") == "logic_error"
        assert task.metadata.get("source") == "defects4j_python"

    def test_invalid_info_json_skipped(self, tmp_path: pytest.TempPathFactory):
        """info.json 损坏时：跳过该项目版本，不崩溃。"""
        from src.datasets.dataset_loader import load_dataset

        project_dir = tmp_path / "projects" / "broken" / "1.0"
        (project_dir / "buggy").mkdir(parents=True)
        (project_dir / "tests").mkdir(parents=True)
        (project_dir / "info.json").write_text("not valid json", encoding="utf-8")

        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        tasks = list(loader)
        assert tasks == []

    def test_multiple_projects_sorted(self, tmp_path: pytest.TempPathFactory):
        """多项目多版本时：按 sorted 顺序加载（确定性可复现）。"""
        from src.datasets.dataset_loader import load_dataset

        for proj in ["alpha", "zeta"]:
            for ver in ["1.0", "2.0"]:
                pdir = tmp_path / "projects" / proj / ver
                (pdir / "buggy").mkdir(parents=True)
                (pdir / "tests").mkdir(parents=True)
                (pdir / "buggy" / "mod.py").write_text(
                    f"def {proj}_{ver}():\n    return 1\n", encoding="utf-8"
                )
                (pdir / "tests" / "test_mod.py").write_text(
                    f"def test_{proj}_{ver}():\n    assert {proj}_{ver}() == 1\n",
                    encoding="utf-8",
                )
                (pdir / "info.json").write_text(
                    json.dumps({"description": f"{proj} {ver}", "expected_pass": 1}),
                    encoding="utf-8",
                )

        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        tasks = list(loader)
        assert len(tasks) == 4
        # sorted 顺序：alpha__1.0, alpha__2.0, zeta__1.0, zeta__2.0
        assert [t.task_id for t in tasks] == [
            "alpha__1.0",
            "alpha__2.0",
            "zeta__1.0",
            "zeta__2.0",
        ]

    def test_benchmark_task_fields_complete(self, tmp_path: pytest.TempPathFactory):
        """BenchmarkTask 所有必要字段非空。"""
        from src.datasets.dataset_loader import load_dataset

        pdir = tmp_path / "projects" / "check" / "1.0"
        (pdir / "buggy").mkdir(parents=True)
        (pdir / "tests").mkdir(parents=True)
        (pdir / "buggy" / "mod.py").write_text(
            "def compute(x):\n    return x * 2\n", encoding="utf-8"
        )
        (pdir / "tests" / "test_mod.py").write_text(
            "def test_compute():\n    assert compute(5) == 10\n", encoding="utf-8"
        )
        (pdir / "info.json").write_text(
            json.dumps({"description": "compute bug", "expected_pass": 1}),
            encoding="utf-8",
        )

        loader = load_dataset("defects4j_python", data_dir=str(tmp_path))
        task = next(iter(loader))
        assert task.task_id
        assert task.problem_statement
        assert task.instance_code
        assert task.test_code
        assert task.expected_pass_count == 1
        assert task.total_test_count == 1
