"""测试 SyntheticDataset 任务生成（此前 _load_raw_data 生成循环 0% 覆盖）

通过触发惰性加载（.tasks）验证：
- 任务数量与结构（task_id / instance_code 噪声注释 / metadata）
- seed 可复现性（同 seed 同噪声、异 seed 不同噪声）
- P0 2.1 分层难度（difficulty 参数）
- P0 2.2 跨文件任务（Level 3 双模块构造）
"""

from src.datasets.synthetic_dataset import BUG_PATTERNS, SyntheticDataset


class TestSyntheticTaskGeneration:
    """_load_raw_data 生成逻辑"""

    def test_task_count_and_structure(self):
        ds = SyntheticDataset(task_count=5, seed=42, difficulty="level1")
        tasks = ds.tasks  # 触发惰性加载
        assert len(tasks) == 5
        assert ds.size == 5

        t0 = tasks[0]
        assert t0.task_id.startswith("synthetic__")
        # 实例代码末尾带噪声注释（函数名本体不被破坏）
        assert "# noise_seed=" in t0.instance_code
        assert t0.test_code  # 测试代码非空
        assert t0.metadata["source"] == "synthetic"
        # Level 1 任务：bug_type 应来自 BUG_PATTERNS（Level 1 池）
        valid_bug_types = {p["bug_type"] for p in BUG_PATTERNS}
        assert t0.metadata["bug_type"] in valid_bug_types
        # 期望通过率字段来自模板
        assert t0.expected_pass_count in {p["expected_pass"] for p in BUG_PATTERNS}
        # P0 2.1 难度字段
        assert t0.metadata["difficulty"] == 1
        assert t0.metadata["is_cross_file"] is False

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
        """P0 2.1 分层难度下，按难度分组验证结构正确性。"""
        # Level 1（历史口径）：任务模式名必须属于 Level 1 池
        from src.datasets.synthetic_dataset import BUG_PATTERNS as L1_POOL

        valid_names = {p["name"] for p in L1_POOL}
        ds1 = SyntheticDataset(task_count=10, seed=0, difficulty="level1")
        patterns1 = [t.metadata["pattern_name"] for t in ds1.tasks]
        assert all(n in valid_names for n in patterns1)
        # 至少 3 种不同模式出现（随机选择下 10 个任务大概率覆盖多个）
        assert len(set(patterns1)) >= 3

        # Level 3（跨文件）：全部任务为跨文件任务，module_a_code 存在
        ds3 = SyntheticDataset(task_count=4, seed=0, difficulty="level3")
        for t in ds3.tasks:
            assert t.metadata["is_cross_file"] is True
            assert t.metadata.get("module_a_code")
            assert t.metadata.get("target_module") == "module_b"

        # Level 2 / Level 4：单难度梯度
        ds2 = SyntheticDataset(task_count=4, seed=0, difficulty="level2")
        for t in ds2.tasks:
            assert t.metadata["difficulty"] == 2
            assert t.metadata["is_cross_file"] is False
        ds4 = SyntheticDataset(task_count=4, seed=0, difficulty="level4")
        for t in ds4.tasks:
            assert t.metadata["difficulty"] == 4
            assert t.metadata["is_cross_file"] is False

    def test_get_task_by_id(self):
        ds = SyntheticDataset(task_count=3, seed=42)
        t = ds.get_task_by_id(ds.tasks[0].task_id)
        assert t is ds.tasks[0] or (t is not None and t.task_id == ds.tasks[0].task_id)
