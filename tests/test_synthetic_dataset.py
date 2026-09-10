"""测试 SyntheticDataset 任务生成（此前 _load_raw_data 生成循环 0% 覆盖）

通过触发惰性加载（.tasks）验证：
- 任务数量与结构（task_id / instance_code 噪声注释 / metadata）
- seed 可复现性（同 seed 同噪声、异 seed 不同噪声）
- 循环取模覆盖多 bug 模式
"""

from src.datasets.synthetic_dataset import BUG_PATTERNS, SyntheticDataset


class TestSyntheticTaskGeneration:
    """_load_raw_data 生成逻辑"""

    def test_task_count_and_structure(self):
        ds = SyntheticDataset(task_count=5, seed=42)
        tasks = ds.tasks  # 触发惰性加载
        assert len(tasks) == 5
        assert ds.size == 5

        t0 = tasks[0]
        assert t0.task_id.startswith("synthetic__")
        # 实例代码末尾带噪声注释（函数名本体不被破坏）
        assert "# noise_seed=" in t0.instance_code
        assert t0.test_code  # 测试代码非空
        assert t0.metadata["source"] == "synthetic"
        assert t0.metadata["bug_type"] == BUG_PATTERNS[0]["bug_type"]
        # 期望通过率字段来自模板
        assert t0.expected_pass_count == BUG_PATTERNS[0]["expected_pass"]

    def test_seed_determinism(self):
        a = SyntheticDataset(task_count=10, seed=7).tasks
        b = SyntheticDataset(task_count=10, seed=7).tasks
        # 同 seed → 完全相同的噪声序列
        assert [t.metadata["noise_seed"] for t in a] == [t.metadata["noise_seed"] for t in b]

    def test_different_seed_differs(self):
        a = SyntheticDataset(task_count=10, seed=1).tasks
        b = SyntheticDataset(task_count=10, seed=2).tasks
        assert [t.metadata["noise_seed"] for t in a] != [t.metadata["noise_seed"] for t in b]

    def test_covers_all_bug_patterns_by_modulo(self):
        n = len(BUG_PATTERNS)
        ds = SyntheticDataset(task_count=n, seed=0)
        patterns = [t.metadata["pattern_name"] for t in ds.tasks]
        assert len(set(patterns)) == n  # 每个模式恰好命中一次

    def test_get_task_by_id(self):
        ds = SyntheticDataset(task_count=3, seed=42)
        t = ds.get_task_by_id(ds.tasks[0].task_id)
        assert t is ds.tasks[0] or (t is not None and t.task_id == ds.tasks[0].task_id)
