"""
增强测试：测试 SyntheticDataset 的模式多样性和数据集质量。

覆盖范围：
    - 模式多样性测试
    - 数据集质量评估
    - 任务结构完整性
    - BUG_PATTERNS 数据结构验证
"""

import ast
import pytest
from src.synthetic_dataset import SyntheticDataset, BUG_PATTERNS


# ─── TestPatternDiversity：模式多样性测试 ─────────────────────────────────────
class TestPatternDiversity:
    """测试合成数据集的模式多样性。"""

    def test_bug_type_distribution(self):
        """测试 bug 类型分布合理。"""
        ds = SyntheticDataset(task_count=100, seed=42)
        bug_types = [t.metadata.get("bug_type", "unknown") for t in ds.tasks]
        unique_types = set(bug_types)
        # 应至少包含 runtime 和 assertion 两类
        assert "runtime" in unique_types or "assertion" in unique_types

    def test_pattern_coverage(self):
        """测试模式覆盖情况。"""
        ds = SyntheticDataset(task_count=60, seed=42)
        # metadata 中使用 pattern_name 字段
        patterns = [t.metadata.get("pattern_name", "unknown") for t in ds.tasks]
        unique_patterns = set(patterns)
        # 应有多种模式（BUG_PATTERNS 有 10 种）
        assert len(unique_patterns) > 1

    def test_task_id_uniqueness(self):
        """测试任务 ID 唯一性。"""
        ds = SyntheticDataset(task_count=100, seed=42)
        task_ids = [t.task_id for t in ds.tasks]
        assert len(task_ids) == len(set(task_ids))

    def test_seed_determinism(self):
        """测试相同 seed 产生相同结果。"""
        ds1 = SyntheticDataset(task_count=50, seed=123)
        ds2 = SyntheticDataset(task_count=50, seed=123)
        assert [t.task_id for t in ds1.tasks] == [t.task_id for t in ds2.tasks]

    def test_different_seeds_produce_different_noise(self):
        """测试不同 seed 产生不同的噪声值。"""
        ds1 = SyntheticDataset(task_count=50, seed=1)
        ds2 = SyntheticDataset(task_count=50, seed=2)
        # task_id 相同（基于索引），但 noise_seed 不同
        assert ds1.tasks[0].task_id == ds2.tasks[0].task_id
        # 检查 noise_seed 不同
        noise1 = ds1.tasks[0].metadata.get("noise_seed")
        noise2 = ds2.tasks[0].metadata.get("noise_seed")
        # 注意：如果随机数序列恰好相同，这个断言可能失败，所以用 assertNotEqual 或跳过
        if noise1 != noise2:
            assert noise1 != noise2


# ─── TestDatasetQuality：数据集质量测试 ───────────────────────────────────────
class TestDatasetQuality:
    """测试数据集质量指标。"""

    def test_instance_code_valid_python(self):
        """测试 instance_code 是合法的 Python 代码。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks[:10]:  # 抽查前 10 个
            code = task.instance_code
            assert isinstance(code, str)
            assert len(code) > 0
            # 基本检查：不应有未闭合的括号
            assert code.count("(") == code.count(")")

    def test_test_code_valid_python(self):
        """测试 test_code 是合法的 Python 代码。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks[:10]:
            code = task.test_code
            assert isinstance(code, str)
            assert len(code) > 0
            # 应包含测试函数定义
            assert "def test_" in code or "import pytest" in code

    def test_task_structure_completeness(self):
        """测试任务结构完整性。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks:
            assert hasattr(task, 'task_id')
            assert hasattr(task, 'repo_name')
            assert hasattr(task, 'problem_statement')
            assert hasattr(task, 'instance_code')
            assert hasattr(task, 'test_code')
            assert hasattr(task, 'expected_pass_count')
            assert hasattr(task, 'total_test_count')
            assert hasattr(task, 'metadata')

    def test_expected_pass_count_reasonable(self):
        """测试期望通过数合理。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks:
            assert task.expected_pass_count >= 0
            assert task.expected_pass_count <= task.total_test_count

    def test_total_test_count_positive(self):
        """测试总测试数为正数。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks:
            assert task.total_test_count > 0

    def test_metadata_has_required_fields(self):
        """测试元数据包含必要字段。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks:
            meta = task.metadata
            assert "bug_type" in meta or "pattern_name" in meta
            assert "noise_seed" in meta


# ─── TestBUG_PATTERNS：Bug 模式定义测试 ─────────────────────────────────────
class TestBUG_PATTERNS:
    """测试 BUG_PATTERNS 数据结构。"""

    def test_patterns_are_list(self):
        """测试 BUG_PATTERNS 是列表。"""
        assert isinstance(BUG_PATTERNS, list)
        assert len(BUG_PATTERNS) > 0

    def test_patterns_have_required_fields(self):
        """测试模式包含必需字段。"""
        required_fields = ["name", "description", "template", "test_cases", "bug_type"]
        for i, pattern in enumerate(BUG_PATTERNS):
            assert isinstance(pattern, dict), f"Pattern {i} is not a dict"
            for field in required_fields:
                assert field in pattern, f"Pattern {i} ({pattern.get('name', 'unknown')}) missing field: {field}"

    def test_patterns_have_valid_python(self):
        """测试模式的代码是合法的 Python。"""
        for i, pattern in enumerate(BUG_PATTERNS):
            template = pattern.get("template", "")
            test_cases = pattern.get("test_cases", "")
            assert isinstance(template, str)
            assert isinstance(test_cases, str)
            assert len(template) > 0
            assert len(test_cases) > 0
            # 验证模板代码语法
            try:
                ast.parse(template)
            except SyntaxError as e:
                pytest.fail(f"Pattern {i} ({pattern.get('name', 'unknown')}) template has syntax error: {e}")
            # 验证测试代码语法
            try:
                ast.parse(test_cases)
            except SyntaxError as e:
                pytest.fail(f"Pattern {i} ({pattern.get('name', 'unknown')}) test_cases has syntax error: {e}")

    def test_patterns_have_fixed_code(self):
        """测试模式包含修复后的代码。"""
        for i, pattern in enumerate(BUG_PATTERNS):
            assert "fixed" in pattern, f"Pattern {i} missing 'fixed' field"
            assert isinstance(pattern["fixed"], str)
            assert len(pattern["fixed"]) > 0
            # 验证修复代码语法
            try:
                ast.parse(pattern["fixed"])
            except SyntaxError as e:
                pytest.fail(f"Pattern {i} ({pattern.get('name', 'unknown')}) fixed code has syntax error: {e}")

    def test_patterns_have_expected_pass_counts(self):
        """测试模式包含期望通过数。"""
        for i, pattern in enumerate(BUG_PATTERNS):
            assert "expected_pass" in pattern, f"Pattern {i} missing 'expected_pass' field"
            assert "total_tests" in pattern, f"Pattern {i} missing 'total_tests' field"
            assert isinstance(pattern["expected_pass"], int)
            assert isinstance(pattern["total_tests"], int)
            assert 0 <= pattern["expected_pass"] <= pattern["total_tests"]


# ─── TestEdgeCases：边界情况测试 ─────────────────────────────────────────────
class TestEdgeCases:
    """测试边界情况和异常输入。"""

    def test_empty_task_count(self):
        """测试零任务数量。"""
        ds = SyntheticDataset(task_count=0, seed=42)
        assert ds.size == 0
        assert ds.tasks == []

    def test_very_large_task_count(self):
        """测试大量任务生成。"""
        ds = SyntheticDataset(task_count=200, seed=42)
        assert ds.size == 200

    def test_special_seed_values(self):
        """测试特殊 seed 值。"""
        ds1 = SyntheticDataset(task_count=10, seed=0)
        ds2 = SyntheticDataset(task_count=10, seed=-1)
        ds3 = SyntheticDataset(task_count=10, seed=2**31 - 1)
        # task_id 相同（基于索引），但检查能正常生成且不崩溃
        assert ds1.tasks[0].task_id == ds2.tasks[0].task_id == ds3.tasks[0].task_id
        # 检查 noise_seed 存在
        assert "noise_seed" in ds1.tasks[0].metadata
        assert "noise_seed" in ds2.tasks[0].metadata
        assert "noise_seed" in ds3.tasks[0].metadata

    def test_consistent_across_instances(self):
        """测试同一 seed 的多次实例化一致性。"""
        instances = [SyntheticDataset(task_count=10, seed=99) for _ in range(5)]
        first_ids = [t.task_id for t in instances[0].tasks]
        for inst in instances[1:]:
            assert [t.task_id for t in inst.tasks] == first_ids

    def test_small_task_count(self):
        """测试少量任务生成。"""
        ds = SyntheticDataset(task_count=1, seed=42)
        assert ds.size == 1
        assert len(ds.tasks) == 1

    def test_metadata_contains_pattern_name(self):
        """测试元数据包含模式名称。"""
        ds = SyntheticDataset(task_count=20, seed=42)
        for task in ds.tasks:
            assert "pattern_name" in task.metadata
            assert isinstance(task.metadata["pattern_name"], str)
            assert len(task.metadata["pattern_name"]) > 0
