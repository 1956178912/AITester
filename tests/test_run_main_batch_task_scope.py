"""L 轮（2026-10-17）：主批次 runner 的 --task-count / --task-limit 语义修复测试。

缺陷来源（pilot 实测，证据工件
``experiments/results/l_round_pilot_20261017/defect_repro/``）：
``run_main_batch.py --task-count 3 --dataset quixbugs`` 实际跑满 50 任务——
``task_count`` 在 run_benchmark 里只对合成数据集生效（生成 N 个任务），真实
数据集的"限制任务数"参数是 ``task_limit``，而脚手架没有暴露它、且原样透传
``task_count`` 造成**静默忽略**（操作者以为限了 3 个，实际全量）。

修复口径（见 ``experiments/run_main_batch.py::resolve_task_scope``）：
- ``--task-count`` 默认 None（不显式给 = 历史默认行为）；
- 合成数据集缺省仍为 ``DEFAULT_TASK_COUNT=50``（历史口径不变）；
- 真实数据集显式 ``--task-count`` 按任务上限生效（等价 ``--task-limit``）；
- 新增 ``--task-limit`` 显式入口，优先于 ``--task-count``；
- <1 的非法值归一为 None 并给出 notice（不静默改变任务数）。
"""

from __future__ import annotations

import json
import sys
import types

import pytest


@pytest.fixture()
def rmb():
    """导入被测模块（导入仅 stdlib 依赖，不触发 LLM 配置校验）。"""
    import experiments.run_main_batch as module

    return module


# ─── resolve_task_scope：合成数据集（历史口径不变） ────────────────────────────


class TestSyntheticScope:
    def test_default_task_count_preserved(self, rmb):
        """未显式给 --task-count 时合成数据集仍生成 DEFAULT_TASK_COUNT 个任务。"""
        count, limit, notices = rmb.resolve_task_scope("synthetic", None, None)
        assert count == rmb.DEFAULT_TASK_COUNT == 50
        assert limit is None
        assert notices == []

    def test_explicit_count_used(self, rmb):
        count, limit, notices = rmb.resolve_task_scope("synthetic", 17, None)
        assert (count, limit, notices) == (17, None, [])

    def test_synth_alias(self, rmb):
        count, _, _ = rmb.resolve_task_scope("synth", 7, None)
        assert count == 7

    def test_both_flags_passthrough(self, rmb):
        """合成数据集可叠加：先生成 count 个，再按 limit 截断。"""
        count, limit, _ = rmb.resolve_task_scope("synthetic", 20, 5)
        assert (count, limit) == (20, 5)

    def test_dataset_name_case_and_whitespace_insensitive(self, rmb):
        count, _, _ = rmb.resolve_task_scope("  SYNTHETIC ", 9, None)
        assert count == 9


# ─── resolve_task_scope：真实数据集（缺陷修复核心面） ──────────────────────────


class TestRealDatasetScope:
    def test_default_keeps_full_dataset_behavior(self, rmb):
        """不显式给任何参数 → 全量（与历史行为一致，避免历史命令语义漂移）。"""
        count, limit, notices = rmb.resolve_task_scope("quixbugs", None, None)
        assert (count, limit, notices) == (None, None, [])

    def test_explicit_task_count_now_limits(self, rmb):
        """核心修复：真实数据集上显式 --task-count 不再被静默忽略。"""
        count, limit, notices = rmb.resolve_task_scope("quixbugs", 3, None)
        assert count is None
        assert limit == 3
        assert len(notices) == 1 and "--task-count=3" in notices[0]

    def test_explicit_task_limit(self, rmb):
        count, limit, notices = rmb.resolve_task_scope("quixbugs", None, 3)
        assert (count, limit, notices) == (None, 3, [])

    def test_task_limit_wins_over_task_count(self, rmb):
        count, limit, notices = rmb.resolve_task_scope("quixbugs", 10, 3)
        assert (count, limit) == (None, 3)
        assert len(notices) == 1 and "--task-limit=3" in notices[0]

    def test_equal_both_flags_no_noise(self, rmb):
        count, limit, notices = rmb.resolve_task_scope("quixbugs", 3, 3)
        assert (count, limit, notices) == (None, 3, [])

    def test_ult_real_dataset_family(self, rmb):
        """ULT 等真实数据集同口径（防止只对 quixbugs 生效的窄修复）。"""
        _, limit, _ = rmb.resolve_task_scope("ult", 25, None)
        assert limit == 25


# ─── 非法值归一（与 run_benchmark.task_limit 口径一致） ────────────────────────


class TestInvalidValues:
    @pytest.mark.parametrize("bad", [0, -1, -100])
    def test_invalid_task_count_normalized(self, rmb, bad):
        count, limit, notices = rmb.resolve_task_scope("quixbugs", bad, None)
        assert (count, limit) == (None, None)
        assert any("--task-count" in n and "无效" in n for n in notices)

    @pytest.mark.parametrize("bad", [0, -5])
    def test_invalid_task_limit_normalized(self, rmb, bad):
        count, limit, notices = rmb.resolve_task_scope("quixbugs", None, bad)
        assert (count, limit) == (None, None)
        assert any("--task-limit" in n and "无效" in n for n in notices)

    def test_invalid_count_falls_back_to_no_limit_not_silent_zero(self, rmb):
        """坏值不得把批次缩成 0 任务（静默改变任务数是历史缺陷形态）。"""
        _, limit, _ = rmb.resolve_task_scope("synthetic", 0, None)
        assert limit is None


# ─── CLI 解析与 main 接线（回归锁：两个入参分别透传） ─────────────────────────


class TestCliWiring:
    def test_cli_defaults_are_none(self, rmb, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run_main_batch.py"])
        args = rmb._parse_args()
        assert args.task_count is None
        assert args.task_limit is None

    def test_cli_parses_both_flags(self, rmb, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["run_main_batch.py", "--task-count", "12", "--task-limit", "8"])
        args = rmb._parse_args()
        assert (args.task_count, args.task_limit) == (12, 8)

    def _run_main_with_fake_benchmark(self, rmb, monkeypatch, tmp_path, argv_extra):
        """跑 main() 但用假 run_benchmark 捕获透传参数（不触网、不跑测试）。

        L 轮回归（本测试首版在全量套件中会误跑真实基准）：`main()` 里写的是
        `import experiments.run_benchmark as rb`——当**其它测试已先导入过真模块**时，
        `experiments` 包对象上的 `run_benchmark` 属性指向真模块，仅替换
        `sys.modules` 条目不足以让 `import ... as` 取到假模块（IMPORT_FROM 优先包属性），
        于是 main() 会真的启动基准（实测在全量套件中触发真实 LLM 跑批/嵌套 m1 挂死）。
        因此必须**同时**替换 sys.modules 与 `experiments` 包属性。
        """
        import experiments as _experiments_pkg

        captured: dict[str, object] = {}

        def fake_run_benchmark(**kwargs):
            captured.update(kwargs)
            (tmp_path / "benchmark_fake.json").write_text(json.dumps({"provenance": {}}), encoding="utf-8")
            return {}

        fake_module = types.SimpleNamespace(run_benchmark=fake_run_benchmark)
        monkeypatch.setitem(sys.modules, "experiments.run_benchmark", fake_module)
        # 关键：包属性优先于 sys.modules 的 IMPORT_FROM 回退路径（见 docstring）
        monkeypatch.setattr(_experiments_pkg, "run_benchmark", fake_module, raising=False)
        monkeypatch.setattr(rmb, "_check_repo_clean", lambda: None)
        monkeypatch.setattr(rmb, "_warn_llm_cache_if_enabled", lambda: None)
        monkeypatch.setattr(rmb, "_print_r4_summary", lambda _p: None)
        monkeypatch.setattr(rmb, "_assert_provenance_dirty", lambda *_a, **_k: None)
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "run_main_batch.py",
                "--dataset",
                "quixbugs",
                "--output-dir",
                str(tmp_path),
                "--skip-stats",
                "--allow-dirty",
                "--dirty-reason",
                "unit-test",
                *argv_extra,
            ],
        )
        rmb.main()
        return captured

    def test_main_real_dataset_count_becomes_limit(self, rmb, monkeypatch, tmp_path):
        captured = self._run_main_with_fake_benchmark(rmb, monkeypatch, tmp_path, ["--task-count", "3"])
        assert captured["task_count"] is None
        assert captured["task_limit"] == 3

    def test_main_real_dataset_no_flag_keeps_full(self, rmb, monkeypatch, tmp_path):
        captured = self._run_main_with_fake_benchmark(rmb, monkeypatch, tmp_path, [])
        assert captured["task_count"] is None
        assert captured["task_limit"] is None

    def test_main_synthetic_default_preserved(self, rmb, monkeypatch, tmp_path):
        captured = self._run_main_with_fake_benchmark(rmb, monkeypatch, tmp_path, ["--dataset", "synthetic"])
        assert captured["task_count"] == 50
        assert captured["task_limit"] is None
