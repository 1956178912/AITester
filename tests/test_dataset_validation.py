"""
SWEBenchDataset 加载质量校验测试（P0：数据集加载正确性排查工具）。

覆盖：
- _extract_suggested_function 从 patch hunk 头提取目标函数
- validate_task 的四类检查项
- quality_report 聚合
- JSONL 加载后 suggested_function 写入 metadata
"""

import json
import os

from src.datasets.dataset_loader import BenchmarkTask, SWEBenchDataset

# ─── _extract_suggested_function ──────────────────────────────────────────────


class TestExtractSuggestedFunction:
    """patch hunk 头解析。"""

    def test_def_context(self):
        patch = """@@ -10,7 +10,7 @@ def divide(self, a, b):
-        return a / b
+        return a // b
"""
        assert SWEBenchDataset._extract_suggested_function(patch) == "divide"

    def test_async_def_context(self):
        patch = "@@ -1,1 +1,1 @@ async def fetch_data():\n-x=1\n"
        assert SWEBenchDataset._extract_suggested_function(patch) == "fetch_data"

    def test_no_def_context(self):
        patch = "@@ -10,3 +10,3 @@ some_class = SomeClass()\n+x=1\n"
        # hunk 上下文是类属性行（非 def）→ 提取不到函数名
        assert SWEBenchDataset._extract_suggested_function(patch) is None

    def test_empty_patch(self):
        assert SWEBenchDataset._extract_suggested_function("") is None
        assert SWEBenchDataset._extract_suggested_function(None) is None


# ─── validate_task ─────────────────────────────────────────────────────────────


def _make_task(**overrides) -> BenchmarkTask:
    base = dict(
        task_id="t__1",
        repo_name="r/repo",
        problem_statement="fix the bug",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        expected_pass_count=0,
        total_test_count=1,
        metadata={},
    )
    base.update(overrides)
    return BenchmarkTask(**base)


class TestValidateTask:
    """validate_task 检查项。"""

    def test_healthy_task(self):
        assert SWEBenchDataset.validate_task(_make_task()) == []

    def test_fallback_instance_code_flagged(self):
        """官方 SWE-bench 无源码字段 → instance_code 兜底为 issue 文本，必须标记。"""
        task = _make_task(problem_statement="issue text", instance_code="issue text")
        issues = SWEBenchDataset.validate_task(task)
        assert any("兜底" in i for i in issues)

    def test_invalid_python_instance_code(self):
        task = _make_task(instance_code="def broken(:\n")
        issues = SWEBenchDataset.validate_task(task)
        assert any("不是合法 Python" in i for i in issues)

    def test_empty_test_code(self):
        task = _make_task(test_code="   ")
        issues = SWEBenchDataset.validate_task(task)
        assert any("test_code 为空" in i for i in issues)

    def test_test_code_without_cases(self):
        task = _make_task(test_code="x = 1\n")
        issues = SWEBenchDataset.validate_task(task)
        assert any("未包含测试用例" in i for i in issues)

    def test_zero_total_tests(self):
        task = _make_task(total_test_count=0)
        issues = SWEBenchDataset.validate_task(task)
        assert any("total_test_count 为 0" in i for i in issues)


# ─── quality_report + JSONL 加载 ──────────────────────────────────────────────


class TestQualityReportAndLoading:
    """quality_report 与 JSONL 加载的 metadata 注入。"""

    def _loader_with_data(self, tmp_path, rows: list[dict]) -> SWEBenchDataset:
        loader = SWEBenchDataset(subset=None)
        loader.data_dir = str(tmp_path)
        jsonl_path = os.path.join(tmp_path, "swe_bench_instances.jsonl")
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row) + "\n")
        return loader

    def test_suggested_function_in_metadata(self, tmp_path):
        rows = [
            {
                "instance_id": "repo__repo-1",
                "repository": "repo/repo",
                "problem_statement": "issue",
                "patch": "@@ -1,2 +1,2 @@ def foo():\n-1\n+2\n",
            }
        ]
        loader = self._loader_with_data(tmp_path, rows)
        tasks = loader.tasks
        assert len(tasks) == 1
        assert tasks[0].metadata["suggested_function"] == "foo"

    def test_missing_suggested_function_is_none(self, tmp_path):
        rows = [
            {
                "instance_id": "repo__repo-2",
                "repository": "repo/repo",
                "problem_statement": "issue",
            }
        ]
        loader = self._loader_with_data(tmp_path, rows)
        assert loader.tasks[0].metadata["suggested_function"] is None

    def test_enrichment_file_merges_source(self, tmp_path):
        """P0：SWE_BENCH_ENRICHMENT 补充文件按 instance_id 补全源码字段。"""
        rows = [
            {
                "instance_id": "repo__repo-3",
                "repository": "r/r",
                "problem_statement": "issue",
            }
        ]
        self._loader_with_data(tmp_path, rows)  # 副作用：把 JSONL 写入 tmp_path
        enrichment = tmp_path / "enrich.jsonl"
        enrichment.write_text(
            json.dumps(
                {
                    "instance_id": "repo__repo-3",
                    "instance_code": "def f():\n    return 1\n",
                    "test_code": "def test_f():\n    assert f() == 1\n",
                    "n_tests_after": 1,
                }
            ),
            encoding="utf-8",
        )
        import os

        os.environ["SWE_BENCH_ENRICHMENT"] = str(enrichment)
        try:
            loader2 = SWEBenchDataset(subset=None)
            loader2.data_dir = str(tmp_path)
            tasks = loader2.tasks
            assert tasks[0].instance_code == "def f():\n    return 1\n"
            assert "def test_f" in tasks[0].test_code
            # 补全后任务应通过质量校验
            assert SWEBenchDataset.validate_task(tasks[0]) == []
        finally:
            os.environ.pop("SWE_BENCH_ENRICHMENT", None)

    def test_quality_report_flags_unhealthy_tasks(self, tmp_path):
        healthy = {
            "instance_id": "ok__1",
            "repository": "r/r",
            "problem_statement": "p",
            "instance_code": "def f():\n    return 1\n",
            "test_code": "def test_f():\n    assert f() == 1\n",
            "n_tests_after": 1,
        }
        # 官方格式：无 instance_code/test_code 字段 → 兜底 issue 文本 + 空测试
        official_style = {
            "instance_id": "official__2",
            "repository": "r/r",
            "problem_statement": "issue text",
        }
        loader = self._loader_with_data(tmp_path, [healthy, official_style])
        report = loader.quality_report()
        assert "ok__1" not in report
        assert "official__2" in report
        assert any("兜底" in i for i in report["official__2"])
        assert any("test_code 为空" in i for i in report["official__2"])
