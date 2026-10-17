"""Q-3 回归测试：批后处理墙钟可观测模块（`experiments/postprocess_wall.py`）。

覆盖（零依赖 / 零网络 / 零 LLM，全部用假时钟/构造数据，不真实跑批）：
1. `StageTimer`：总 wall、逐任务耗时、超时/异常计数、异常不吞、空任务、
   嵌套/复用时序、装饰器、非法输入；
2. 分位算法精确值（已知样本、奇偶样本、单值、乱序、重复值、直接调用）；
3. `build_postprocess_wall` 稳定 JSON 形状 / 可序列化 / dict 子类 warnings；
4. 阈值告警与 env 读取（`AITESTER_POSTPROCESS_WARN_S` 默认/覆盖/坏值回退）；
5. 无任务/全超时/数据不一致/未登记阶段名等边界 fail-fast；
6. 零 numpy 依赖 + hook 集成样例（StageTimer 收集 → build 聚合）。
"""

from __future__ import annotations

import json

import pytest

from experiments.postprocess_wall import (
    POSTPROCESS_WARN_ENV,
    PostprocessWallResult,
    StageTimer,
    _percentile_linear,
    build_postprocess_wall,
    postprocess_warn_s,
    registered_stage_names,
)
from src.utils.env_utils import POSTPROCESS_WARN_ENV as SRC_WARN_ENV
from src.utils.env_utils import postprocess_warn_seconds


class FakeClock:
    """按序返回预设时刻的假时钟（避免真实 sleep，测试确定性）。"""

    def __init__(self, *values: float) -> None:
        self._values = list(values)
        self.calls = 0

    def __call__(self) -> float:
        self.calls += 1
        if not self._values:
            raise AssertionError("FakeClock 预设时刻已用尽")
        return self._values.pop(0)


# ─────────────────────────── 1. StageTimer ───────────────────────────


class TestStageTimer:
    def test_context_manager_measures_wall(self) -> None:
        clock = FakeClock(10.0, 12.5)
        timer = StageTimer("mdo", clock=clock)
        with timer:
            pass
        assert timer.wall_s == pytest.approx(2.5)
        assert timer.snapshot()["wall_s"] == pytest.approx(2.5)
        assert timer.snapshot()["n_tasks"] == 0

    def test_context_manager_accumulates_multiple_blocks(self) -> None:
        clock = FakeClock(0.0, 1.0, 10.0, 12.0)
        timer = StageTimer("m1", clock=clock)
        with timer:
            pass
        with timer:
            pass
        assert timer.wall_s == pytest.approx(3.0)

    def test_record_task_collects_durations_and_timeouts(self) -> None:
        timer = StageTimer("mutation")
        timer.record_task(1.5)
        timer.record_task(2.5, timed_out=True)
        assert timer.durations == [1.5, 2.5]
        assert timer.timed_out_tasks == 1
        assert timer.snapshot() == {
            "stage": "mutation",
            "wall_s": 0.0,
            "n_tasks": 2,
            "timed_out_tasks": 1,
            "exceptions": 0,
        }

    def test_measure_task_records_duration(self) -> None:
        clock = FakeClock(5.0, 5.25)
        timer = StageTimer("mdo", clock=clock)
        with timer.measure_task():
            pass
        assert timer.durations == [pytest.approx(0.25)]

    def test_measure_task_marks_timeout(self) -> None:
        clock = FakeClock(0.0, 60.0)
        timer = StageTimer("mdo", clock=clock)
        with timer.measure_task(timed_out=True):
            pass
        assert timer.durations == [pytest.approx(60.0)]
        assert timer.timed_out_tasks == 1

    def test_measure_task_exception_counted_but_reraised(self) -> None:
        clock = FakeClock(0.0, 0.5)
        timer = StageTimer("m1", clock=clock)
        with pytest.raises(RuntimeError, match="boom"), timer.measure_task():
            raise RuntimeError("boom")
        assert timer.exceptions == 1
        assert timer.durations == [pytest.approx(0.5)]  # 异常任务的耗时也被记录

    def test_context_exception_counted_but_not_swallowed(self) -> None:
        clock = FakeClock(0.0, 1.0)
        timer = StageTimer("mdo", clock=clock)
        with pytest.raises(ValueError, match="bad"), timer:
            raise ValueError("bad")
        assert timer.exceptions == 1
        assert timer.wall_s == pytest.approx(1.0)

    def test_decorator_records_per_call_durations(self) -> None:
        clock = FakeClock(0.0, 0.5, 10.0, 12.0)
        timer = StageTimer("other", clock=clock)

        @timer.measure
        def postprocess_one(value: int) -> int:
            return value * 2

        assert postprocess_one(21) == 42
        assert postprocess_one(1) == 2
        assert timer.durations == [pytest.approx(0.5), pytest.approx(2.0)]

    def test_decorator_exception_counted_but_reraised(self) -> None:
        clock = FakeClock(0.0, 0.1)
        timer = StageTimer("other", clock=clock)

        @timer.measure
        def boom() -> None:
            raise KeyError("k")

        with pytest.raises(KeyError):
            boom()
        assert timer.exceptions == 1
        assert len(timer.durations) == 1

    def test_nested_timers_are_independent(self) -> None:
        outer_clock = FakeClock(0.0, 2.0)
        inner_clock = FakeClock(0.5, 0.75)
        outer = StageTimer("mdo", clock=outer_clock)
        inner = StageTimer("other", clock=inner_clock)
        with outer.measure_task(), inner.measure_task():
            pass
        assert outer.durations == [pytest.approx(2.0)]
        assert inner.durations == [pytest.approx(0.25)]
        assert outer.stage != inner.stage

    def test_empty_stage_has_zero_distribution(self) -> None:
        timer = StageTimer("m1")
        with timer:
            pass
        result = build_postprocess_wall({timer.stage: timer.stage_durations()})
        assert result["m1"]["n_tasks"] == 0
        assert result["m1"]["wall_s"] == 0.0

    def test_double_start_raises(self) -> None:
        timer = StageTimer("mdo")
        timer.start()
        with pytest.raises(RuntimeError, match="已在计时中"):
            timer.start()
        timer.stop()

    def test_stop_without_start_raises(self) -> None:
        with pytest.raises(RuntimeError, match="未开始计时"):
            StageTimer("mdo").stop()

    def test_invalid_stage_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="非空字符串"):
            StageTimer("")

    @pytest.mark.parametrize("bad", [-1, float("nan"), float("inf"), True, "1.5", None])
    def test_record_task_invalid_duration_rejected(self, bad: object) -> None:
        timer = StageTimer("mdo")
        with pytest.raises((TypeError, ValueError)):
            timer.record_task(bad)  # type: ignore[arg-type]

    def test_stage_durations_returns_copy(self) -> None:
        timer = StageTimer("m1")
        timer.record_task(1.0)
        copied = timer.stage_durations()
        copied.append(999.0)
        assert timer.durations == [1.0]

    def test_timed_out_stage_map(self) -> None:
        timer = StageTimer("mdo")
        timer.record_task(1.0, timed_out=True)
        timer.record_task(2.0)
        assert timer.timed_out_stage_map() == {"mdo": 1}


# ─────────────────────────── 2. 分位算法精确值 ───────────────────────────


class TestPercentileAlgorithm:
    def test_empty_returns_zero(self) -> None:
        assert _percentile_linear([], 0.5) == 0.0

    def test_single_value(self) -> None:
        assert _percentile_linear([42.0], 0.5) == 42.0
        assert _percentile_linear([42.0], 0.95) == 42.0

    def test_two_values_linear_interpolation(self) -> None:
        assert _percentile_linear([0.0, 10.0], 0.5) == pytest.approx(5.0)
        assert _percentile_linear([0.0, 10.0], 0.95) == pytest.approx(9.5)

    def test_even_sample_exact_values(self) -> None:
        # n=4：p50 rank=1.5 → 20+0.5*(30-20)=25；p95 rank=2.85 → 30+0.85*10=38.5
        assert _percentile_linear([10.0, 20.0, 30.0, 40.0], 0.50) == pytest.approx(25.0)
        assert _percentile_linear([10.0, 20.0, 30.0, 40.0], 0.95) == pytest.approx(38.5)

    def test_odd_sample_exact_values(self) -> None:
        # n=3：p50 rank=1 → 20；p95 rank=1.9 → 20+0.9*10=29
        assert _percentile_linear([10.0, 20.0, 30.0], 0.50) == pytest.approx(20.0)
        assert _percentile_linear([10.0, 20.0, 30.0], 0.95) == pytest.approx(29.0)


class TestBuildStatistics:
    def test_even_sample_stats(self) -> None:
        result = build_postprocess_wall({"mdo": [40.0, 10.0, 30.0, 20.0]})
        assert result["mdo"] == {
            "wall_s": 100.0,
            "n_tasks": 4,
            "mean_s": 25.0,
            "p50_s": 25.0,
            "p95_s": 38.5,
            "max_s": 40.0,
            "timed_out_tasks": 0,
        }

    def test_odd_sample_stats(self) -> None:
        result = build_postprocess_wall({"m1": [30.0, 10.0, 20.0]})
        assert result["m1"]["p50_s"] == pytest.approx(20.0)
        assert result["m1"]["p95_s"] == pytest.approx(29.0)
        assert result["m1"]["max_s"] == 30.0

    def test_single_task_stats(self) -> None:
        result = build_postprocess_wall({"other": [42.0]})
        stats = result["other"]
        assert stats["wall_s"] == 42.0
        assert stats["n_tasks"] == 1
        assert stats["mean_s"] == 42.0
        assert stats["p50_s"] == 42.0
        assert stats["p95_s"] == 42.0
        assert stats["max_s"] == 42.0

    def test_duplicate_values(self) -> None:
        result = build_postprocess_wall({"mutation": [5.0, 5.0, 5.0]})
        assert result["mutation"]["p50_s"] == 5.0
        assert result["mutation"]["max_s"] == 5.0

    def test_empty_duration_list_is_zero_distribution(self) -> None:
        result = build_postprocess_wall({"mdo": []})
        assert result["mdo"] == {
            "wall_s": 0.0,
            "n_tasks": 0,
            "mean_s": 0.0,
            "p50_s": 0.0,
            "p95_s": 0.0,
            "max_s": 0.0,
            "timed_out_tasks": 0,
        }

    def test_empty_stages_mapping(self) -> None:
        result = build_postprocess_wall({})
        assert dict(result) == {}
        assert result.warnings == []


# ─────────────────────────── 3. JSON 形状 / 序列化 ───────────────────────────


class TestStableJsonShape:
    def test_shape_and_key_set(self) -> None:
        result = build_postprocess_wall({"mdo": [1.0, 2.0], "m1": [0.5]}, timed_out={"mdo": 1})
        assert isinstance(result, dict)
        assert isinstance(result, PostprocessWallResult)
        assert set(result) == {"mdo", "m1"}
        assert set(result["mdo"]) == {
            "wall_s",
            "n_tasks",
            "mean_s",
            "p50_s",
            "p95_s",
            "max_s",
            "timed_out_tasks",
        }
        assert result["mdo"]["timed_out_tasks"] == 1
        assert result["m1"]["timed_out_tasks"] == 0

    def test_json_serializable(self) -> None:
        result = build_postprocess_wall({"mdo": [1.25, 2.5]}, timed_out={"mdo": 1})
        payload = json.dumps({"postprocess_wall": result})
        loaded = json.loads(payload)
        assert loaded["postprocess_wall"]["mdo"]["n_tasks"] == 2
        assert loaded["postprocess_wall"]["mdo"]["timed_out_tasks"] == 1
        assert "warnings" not in loaded["postprocess_wall"]

    def test_to_json_returns_plain_dict(self) -> None:
        result = build_postprocess_wall({"m1": [1.0]})
        plain = result.to_json()
        assert type(plain) is dict
        assert plain["m1"]["n_tasks"] == 1

    def test_stage_order_preserved(self) -> None:
        result = build_postprocess_wall({"mutation": [1.0], "m1": [2.0], "mdo": [3.0]})
        assert list(result) == ["mutation", "m1", "mdo"]

    def test_float_rounding_stable(self) -> None:
        result = build_postprocess_wall({"mdo": [0.1, 0.2]})
        assert result["mdo"]["wall_s"] == 0.3
        assert result["mdo"]["mean_s"] == 0.15


# ─────────────────────────── 4. 阈值告警与 env ───────────────────────────


class TestWarnThreshold:
    def test_no_warning_below_threshold(self) -> None:
        result = build_postprocess_wall({"mdo": [1.0, 2.0]}, warn_s=600.0)
        assert result.warnings == []
        assert result.warn_s == 600.0

    def test_warning_above_threshold(self) -> None:
        result = build_postprocess_wall({"mdo": [400.0, 300.0]}, warn_s=600.0)
        assert len(result.warnings) == 1
        message = result.warnings[0]
        assert "mdo" in message and "700.0" in message and "600.0" in message
        assert POSTPROCESS_WARN_ENV in message

    def test_equal_threshold_does_not_warn(self) -> None:
        result = build_postprocess_wall({"mdo": [600.0]}, warn_s=600.0)
        assert result.warnings == []

    def test_custom_warn_s(self) -> None:
        result = build_postprocess_wall({"m1": [50.0]}, warn_s=10.0)
        assert len(result.warnings) == 1

    def test_multiple_stage_warnings_ordered(self) -> None:
        result = build_postprocess_wall({"mdo": [700.0], "mutation": [800.0]}, warn_s=600.0)
        assert len(result.warnings) == 2
        assert "mdo" in result.warnings[0]
        assert "mutation" in result.warnings[1]

    def test_env_default_600(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(POSTPROCESS_WARN_ENV, raising=False)
        assert postprocess_warn_s() == 600.0

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(POSTPROCESS_WARN_ENV, "1200")
        assert postprocess_warn_s() == 1200.0
        # 显式 warn_s 优先于 env（hook 通常传 postprocess_warn_s()，此处验证参数语义）
        result = build_postprocess_wall({"mdo": [700.0]}, warn_s=1200.0)
        assert result.warnings == []

    @pytest.mark.parametrize("bad", ["abc", "0", "-5", "nan", "inf", "   "])
    def test_env_bad_value_falls_back(self, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
        monkeypatch.setenv(POSTPROCESS_WARN_ENV, bad)
        assert postprocess_warn_s() == 600.0

    def test_env_fallback_custom_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(POSTPROCESS_WARN_ENV, raising=False)
        assert postprocess_warn_s(default=900.0) == 900.0

    @pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True, "600"])
    def test_build_invalid_warn_s_rejected(self, bad: object) -> None:
        with pytest.raises((TypeError, ValueError), match="warn_s"):
            build_postprocess_wall({"mdo": [1.0]}, warn_s=bad)  # type: ignore[arg-type]


# ─────────────────────────── 5. 边界 / 校验 / 全超时 ───────────────────────────


class TestSrcEnvReaderDelegation:
    """Q-3 裁决（方案 a）：env 读取实现在 `src/utils/env_utils.py`（门禁扫描面内）。"""

    def test_env_name_constant_same_source(self) -> None:
        assert POSTPROCESS_WARN_ENV == SRC_WARN_ENV == "AITESTER_POSTPROCESS_WARN_S"

    def test_src_reader_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(SRC_WARN_ENV, raising=False)
        assert postprocess_warn_seconds() == 600.0

    def test_src_reader_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SRC_WARN_ENV, "1500")
        assert postprocess_warn_seconds() == 1500.0

    @pytest.mark.parametrize("bad", ["abc", "0", "-3", "nan", "inf", ""])
    def test_src_reader_bad_value_falls_back(self, monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
        monkeypatch.setenv(SRC_WARN_ENV, bad)
        assert postprocess_warn_seconds() == 600.0

    def test_src_reader_custom_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(SRC_WARN_ENV, raising=False)
        assert postprocess_warn_seconds(default=900.0) == 900.0

    def test_experiments_helper_delegates_to_src_reader(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """实验模块 `postprocess_warn_s` 必须委托 src reader（门禁可见性的关键接线）。"""
        import experiments.postprocess_wall as postprocess_wall_module

        monkeypatch.setattr(postprocess_wall_module, "postprocess_warn_seconds", lambda default=600.0: 42.0)
        assert postprocess_wall_module.postprocess_warn_s() == 42.0


class TestValidationAndEdgeCases:
    def test_unregistered_stage_rejected(self) -> None:
        with pytest.raises(ValueError, match="未登记阶段名"):
            build_postprocess_wall({"md0": [1.0]})

    def test_empty_stage_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="非空字符串"):
            build_postprocess_wall({"": [1.0]})

    def test_stages_not_mapping_rejected(self) -> None:
        with pytest.raises(TypeError, match="映射"):
            build_postprocess_wall([("mdo", [1.0])])  # type: ignore[arg-type]

    def test_durations_not_list_rejected(self) -> None:
        with pytest.raises(TypeError, match="list/tuple"):
            build_postprocess_wall({"mdo": "1,2"})  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf"), True, "2.0"])
    def test_invalid_duration_rejected(self, bad: object) -> None:
        with pytest.raises((TypeError, ValueError)):
            build_postprocess_wall({"mdo": [bad]})  # type: ignore[list-item]

    def test_timed_out_unknown_stage_rejected(self) -> None:
        with pytest.raises(ValueError, match="stages 之外"):
            build_postprocess_wall({"mdo": [1.0]}, timed_out={"m1": 1})

    def test_timed_out_negative_rejected(self) -> None:
        with pytest.raises(ValueError, match="不一致"):
            build_postprocess_wall({"mdo": [1.0]}, timed_out={"mdo": -1})

    def test_timed_out_exceeds_tasks_rejected(self) -> None:
        with pytest.raises(ValueError, match="不一致"):
            build_postprocess_wall({"mdo": [1.0, 2.0]}, timed_out={"mdo": 3})

    def test_timed_out_non_int_rejected(self) -> None:
        with pytest.raises(TypeError, match="整数"):
            build_postprocess_wall({"mdo": [1.0]}, timed_out={"mdo": 1.0})  # type: ignore[dict-item]

    def test_all_tasks_timed_out(self) -> None:
        result = build_postprocess_wall({"mdo": [1.0, 2.0]}, timed_out={"mdo": 2})
        assert result["mdo"]["timed_out_tasks"] == 2
        assert result["mdo"]["n_tasks"] == 2

    def test_zero_tasks_with_zero_timeout_ok(self) -> None:
        result = build_postprocess_wall({"mdo": []}, timed_out={"mdo": 0})
        assert result["mdo"]["timed_out_tasks"] == 0

    def test_zero_tasks_with_positive_timeout_rejected(self) -> None:
        with pytest.raises(ValueError, match="不一致"):
            build_postprocess_wall({"mdo": []}, timed_out={"mdo": 1})


# ─────────────────────────── 6. 常量 / 零依赖 / 集成样例 ───────────────────────────


class TestRegisteredStagesAndZeroDeps:
    def test_registered_stage_names(self) -> None:
        assert registered_stage_names() == ("mutation", "m1", "mdo", "other")
        assert isinstance(registered_stage_names(), tuple)

    def test_no_numpy_dependency(self) -> None:
        import inspect

        from experiments import postprocess_wall

        source = inspect.getsource(postprocess_wall)
        # 允许 docstring 以 numpy 作为分位口径参照；断言无 numpy **导入/依赖**
        assert "import numpy" not in source
        assert "from numpy" not in source

    def test_hook_integration_sample(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """模拟 run_benchmark hook：StageTimer 收集 → build → warnings → JSON 落盘。"""
        monkeypatch.delenv(POSTPROCESS_WARN_ENV, raising=False)
        timers = {name: StageTimer(name) for name in registered_stage_names()}
        fake_times = {name: iter(range(0, 10_000, 10)) for name in timers}

        for name, timer in timers.items():
            clock = fake_times[name]
            timer._clock = lambda clock=clock: float(next(clock))
            with timer, timer.measure_task():
                pass

        wall = build_postprocess_wall(
            {timer.stage: timer.stage_durations() for timer in timers.values()},
            timed_out={timer.stage: timer.timed_out_tasks for timer in timers.values()},
            warn_s=postprocess_warn_s(),
        )
        payload = json.dumps({"postprocess_wall": wall})
        loaded = json.loads(payload)["postprocess_wall"]
        assert set(loaded) == set(registered_stage_names())
        for stage in registered_stage_names():
            assert loaded[stage]["n_tasks"] == 1
            assert loaded[stage]["max_s"] == 10.0
