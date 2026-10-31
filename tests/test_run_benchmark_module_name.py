"""C8 v2：run_benchmark 任务模块名派生的契约锁。

背景：BugsInPy 真实仓库任务的 module_name 若用 task_id 派生名
（sanic_1_app），经 generator 的 import 强制约束进入生成 prompt，LLM
生成的测试在 repo 级判定环境无法收集（C8 v1 构念缺陷，0/13 检出的
主构成）。v2 改用 metadata.file_path 的包内全路径。

锁口径：
- bugsinpy 任务：module_name = file_path 包内全路径（sanic/app.py → sanic.app）
- 其他数据集 / 无 file_path：task_id 末段派生（历史口径逐字节不变）
"""

from __future__ import annotations

from types import SimpleNamespace

from experiments.run_benchmark import _derive_module_name


def _task(task_id: str, metadata: dict) -> SimpleNamespace:
    return SimpleNamespace(task_id=task_id, metadata=metadata)


class TestBugsInPyModulePath:
    def test_bugsinpy_uses_real_package_path(self):
        t = _task(
            "bugsinpy__sanic_1_app",
            {"source": "bugs_in_py", "file_path": "sanic/app.py"},
        )
        assert _derive_module_name(t) == "sanic.app"

    def test_bugsinpy_nested_path_and_no_ext(self):
        t = _task(
            "bugsinpy__PySnooper_1_tracer",
            {"source": "bugs_in_py", "file_path": "pysnooper/tracer.py"},
        )
        assert _derive_module_name(t) == "pysnooper.tracer"

    def test_bugsinpy_without_file_path_falls_back(self):
        t = _task("bugsinpy__x_1_y", {"source": "bugs_in_py"})
        assert _derive_module_name(t) == "x_1_y"


class TestOtherDatasetsUnchanged:
    def test_swe_bench_task_id_derived(self):
        t = _task(
            "instance_django__django-10914",
            {"source": "swe_bench", "file_path": "django/db/models/query.py"},
        )
        # 历史口径：task_id 双下划线后的末段派生（file_path 不消费）
        assert _derive_module_name(t) == "django_10914"

    def test_synthetic_task_id_derived(self):
        t = _task("synthetic__task_ab12", {"source": "synthetic"})
        assert _derive_module_name(t) == "task_ab12"

    def test_legacy_no_metadata(self):
        t = SimpleNamespace(task_id="foo__bar_baz", metadata=None)
        assert _derive_module_name(t) == "bar_baz"
