"""
单元测试：测试 SyntheticDataset 模块。

覆盖范围：
    - 默认/自定义任务数量
    - 相同 seed 的确定性（可复现性）
    - 不同 seed 产生不同结果
    - 任务 ID 唯一性
    - 任务结构完整性（所有字段存在且合法）
    - bug_type 分布（runtime + assertion 两类均有覆盖）
    - BUG_PATTERNS 数据结构完整性（字段、语法合法性）
"""
import pytest
from src.synthetic_dataset import SyntheticDataset, BUG_PATTERNS


# ─── TestSyntheticDataset：合成数据集测试 ──────────────────────────────────────
class TestSyntheticDataset:
    """测试合成数据集加载器。"""

    def test_default_task_count(self):
        """默认生成 100 个合成任务。"""
        ds = SyntheticDataset()
        assert ds.size == 100

    def test_custom_task_count(self):
        """支持自定义任务数量，灵活控制测试规模。"""
        ds = SyntheticDataset(task_count=60, seed=42)
        assert ds.size == 60

    def test_deterministic_seed(self):
        """相同 seed 生成完全相同的任务序列（可复现性）。"""
        ds1 = SyntheticDataset(task_count=10, seed=42)
        ds2 = SyntheticDataset(task_count=10, seed=42)
        ids1 = [t.task_id for t in ds1.tasks]
        ids2 = [t.task_id for t in ds2.tasks]
        assert ids1 == ids2

    def test_different_seeds_produce_different_tasks(self):
        """不同 seed 应产生不同的 noise_seed（进而影响 task_id）。"""
        ds1 = SyntheticDataset(task_count=20, seed=42)
        ds2 = SyntheticDataset(task_count=20, seed=99)
        # noise_seed 不同确保生成差异
        assert ds1.tasks[0].metadata["noise_seed"] != ds2.tasks[0].metadata["noise_seed"]

    def test_task_ids_unique(self):
        """所有任务 ID 必须唯一，避免后续查找冲突。"""
        ds = SyntheticDataset(task_count=60, seed=42)
        task_ids = [t.task_id for t in ds.tasks]
        assert len(task_ids) == len(set(task_ids))

    def test_task_structure(self):
        """每个任务应具备完整的 BenchmarkTask 结构。"""
        ds = SyntheticDataset(task_count=5, seed=42)
        for task in ds.tasks:
            assert task.task_id.startswith("synthetic__")
            assert task.repo_name.startswith("synthetic/")
            assert len(task.problem_statement) > 0
            assert len(task.instance_code) > 0
            assert len(task.test_code) > 0
            assert task.expected_pass_count >= 0
            assert task.total_test_count > 0
            assert "bug_type" in task.metadata
            assert task.metadata["source"] == "synthetic"

    def test_bug_type_distribution(self):
        """bug_type 应同时包含 runtime 和 assertion 两类。"""
        ds = SyntheticDataset(task_count=100, seed=42)
        bug_types = set(t.metadata["bug_type"] for t in ds.tasks)
        assert "runtime" in bug_types
        assert "assertion" in bug_types

    def test_iteration_protocol(self):
        """支持迭代所有任务（for task in ds）。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        tasks = list(ds)
        assert len(tasks) == 20

    def test_filter_by_repo(self):
        """按仓库名称正则过滤。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        filtered = ds.filter_by_repo("divide_by_zero")
        assert len(filtered) > 0
        assert all("divide_by_zero" in t.repo_name for t in filtered)

    def test_get_task_by_id(self):
        """按 ID 查找任务，存在时返回任务，不存在时返回 None。"""
        ds = SyntheticDataset(task_count=10, seed=42)
        first_id = ds.tasks[0].task_id
        found = ds.get_task_by_id(first_id)
        assert found is not None
        assert found.task_id == first_id
        assert ds.get_task_by_id("nonexistent") is None

    def test_all_tasks_have_metadata(self):
        """所有任务的 metadata 必须包含 source、noise_seed、pattern_name。"""
        ds = SyntheticDataset(task_count=50, seed=42)
        for task in ds.tasks:
            assert task.metadata.get("source") == "synthetic"
            assert "noise_seed" in task.metadata
            assert "pattern_name" in task.metadata


# ─── TestBugPatterns：BUG_PATTERNS 数据结构完整性 ─────────────────────────────
class TestBugPatterns:
    """测试预定义 bug 模板库的完整性。"""

    def test_patterns_non_empty(self):
        """BUG_PATTERNS 至少包含一个模板。"""
        assert len(BUG_PATTERNS) > 0

    def test_each_pattern_has_required_fields(self):
        """每个 pattern 必须具备所有必需字段。"""
        required = {"name", "description", "template", "fixed", "test_cases",
                    "bug_type", "expected_pass", "total_tests"}
        for p in BUG_PATTERNS:
            missing = required - set(p.keys())
            assert not missing, f"Pattern {p.get('name', '?')} 缺少字段: {missing}"

    def test_template_is_valid_python(self):
        """每个 template 必须是合法 Python 代码（AST 可解析）。"""
        import ast
        for p in BUG_PATTERNS:
            try:
                ast.parse(p["template"])
            except SyntaxError as e:
                pytest.fail(f"Pattern {p['name']} template 语法错误: {e}")

    def test_fixed_is_valid_python(self):
        """每个 fixed 必须是合法 Python 代码（AST 可解析）。"""
        import ast
        for p in BUG_PATTERNS:
            try:
                ast.parse(p["fixed"])
            except SyntaxError as e:
                pytest.fail(f"Pattern {p['name']} fixed 语法错误: {e}")

    def test_test_cases_are_valid_python(self):
        """每个 test_cases 必须是合法 Python 代码（AST 可解析）。"""
        import ast
        for p in BUG_PATTERNS:
            try:
                ast.parse(p["test_cases"])
            except SyntaxError as e:
                pytest.fail(f"Pattern {p['name']} test_cases 语法错误: {e}")

    def test_fixed_differs_from_template(self):
        """fixed 代码应与 template 不同（否则不是 bug）。"""
        for p in BUG_PATTERNS:
            assert p["fixed"] != p["template"], f"Pattern {p['name']} fixed 与 template 相同"

    def test_expected_pass_less_than_total(self):
        """expected_pass 应小于等于 total_tests（有缺陷时不会全过）。"""
        for p in BUG_PATTERNS:
            assert p["expected_pass"] <= p["total_tests"]
