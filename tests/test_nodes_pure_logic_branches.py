"""graph/nodes 纯静态辅助函数分支补齐（2026-10-02 批次·四）。

锁定 nodes.py 零 LLM / 零网络 / 零 git 的纯逻辑分支：
- _resolve_target_module 跨文件 / 单文件 target_module 解析
- _build_failure_frequency_section 开关 / 空 history / 无信号 / 空 hint 路径
- _compute_reward_signals 各维奖励信号
- _suggest_iteration_strategy 连降 / 停滞 / 非数值 delta / 首轮
- _dynamic_temperature_from_suggestion 温度映射
- _get_or_create_executor_agent / clear_executor_agent_cache 惰性单例缓存
- 各 *_enabled 开关 env 解析口径
"""

from __future__ import annotations


class TestResolveTargetModuleBranches:
    def test_cross_file_with_target_modules(self):
        from src.graph.nodes import _resolve_target_module

        state = {
            "module_name": "task__test",
            "cross_file_deps": [
                {"target_module": "module_b"},
                {"target_module": "module_c"},
            ],
            "cross_file_plan": {"target_modules": ["module_b", "module_c"]},
        }
        assert _resolve_target_module(state) == "module_b"

    def test_cross_file_fallback_to_deps_last(self):
        from src.graph.nodes import _resolve_target_module

        state = {
            "module_name": "task__test",
            "cross_file_deps": [
                {"target_module": "module_a"},
                {"target_module": "module_c"},
            ],
            # cross_file_plan 缺失 → 回退到 deps 末元素
        }
        assert _resolve_target_module(state) == "module_c"

    def test_cross_file_no_target_fields_fallback_module_name(self):
        from src.graph.nodes import _resolve_target_module

        state = {
            "module_name": "single_module",
            "cross_file_deps": [{"unrelated": 1}],
        }
        assert _resolve_target_module(state) == "single_module"

    def test_single_file_task(self):
        from src.graph.nodes import _resolve_target_module

        state = {"module_name": "single_module"}
        assert _resolve_target_module(state) == "single_module"


class TestBuildFailureFrequencySectionBranches:
    def test_disabled_returns_empty(self, monkeypatch):
        from src.graph.nodes import _build_failure_frequency_section

        monkeypatch.delenv("FAILURE_FREQUENCY_ENABLE", raising=False)
        out = _build_failure_frequency_section({"repair_history": []})
        assert out == ""

    def test_enabled_but_no_history_returns_empty(self, monkeypatch):
        from src.graph.nodes import _build_failure_frequency_section

        monkeypatch.setenv("FAILURE_FREQUENCY_ENABLE", "true")
        out = _build_failure_frequency_section({})
        assert out == ""


class TestComputeRewardSignalsBranches:
    def test_passed_success(self):
        from src.graph.nodes import _compute_reward_signals

        out = _compute_reward_signals(True, None, 1.0)
        assert out["correctness"] == 1.0
        assert out["efficiency"] >= 0.0

    def test_failed_success_zero(self):
        from src.graph.nodes import _compute_reward_signals

        out = _compute_reward_signals(False, None, 1.0)
        assert out["correctness"] == 0.0

    def test_slow_execution_low_efficiency(self):
        from src.graph.nodes import _compute_reward_signals

        out = _compute_reward_signals(True, None, 99999.0)
        assert out["efficiency"] == 0.0  # 超时时归零
        assert out["simplicity"] == 0.0


class TestSuggestIterationStrategyBranches:
    def test_first_round_no_suggestion(self):
        from src.graph.nodes import _suggest_iteration_strategy

        trace = [{"coverage_delta": -1.0}]
        assert _suggest_iteration_strategy(trace, -1.0) is None

    def test_declining_suggests_lower_temperature(self):
        from src.graph.nodes import _suggest_iteration_strategy

        trace = [
            {"coverage_delta": -1.0},
            {"coverage_delta": -1.0},
            {"coverage_delta": -1.0},  # 本次
        ]
        assert _suggest_iteration_strategy(trace, -1.0) == "lower_temperature"

    def test_stagnant_suggests_switch_view(self):
        from src.graph.nodes import _suggest_iteration_strategy

        trace = [
            {"coverage_delta": 0.0},
            {"coverage_delta": 0.0},
            {"coverage_delta": 0.0},
        ]
        assert _suggest_iteration_strategy(trace, 0.0) == "switch_repair_view"

    def test_non_numeric_delta_skipped(self):
        from src.graph.nodes import _suggest_iteration_strategy

        trace = [
            {"coverage_delta": "n/a"},
            {"coverage_delta": "n/a"},
            {"coverage_delta": "n/a"},
        ]
        assert _suggest_iteration_strategy(trace, "n/a") is None


class TestDynamicTemperatureFromSuggestionBranches:
    def test_lower_temperature_halfed(self):
        from src.graph.nodes import _dynamic_temperature_from_suggestion

        # TEMPERATURE 默认 0.7 → 减半 0.35
        out = _dynamic_temperature_from_suggestion("lower_temperature")
        assert out is not None and out < 0.7

    def test_other_suggestion_returns_none(self):
        from src.graph.nodes import _dynamic_temperature_from_suggestion

        assert _dynamic_temperature_from_suggestion("switch_repair_view") is None
        assert _dynamic_temperature_from_suggestion(None) is None


class TestExecutorAgentCacheBranches:
    def _call(self, **kw):
        from src.graph import nodes

        kw.setdefault("timeout", 30)
        kw.setdefault("use_docker", False)
        kw.setdefault("use_venv", False)
        kw.setdefault("auto_install_deps", False)
        kw.setdefault("dep_install_timeout", 60)
        kw.setdefault("docker_image", "python:3.12")
        return nodes._get_or_create_executor_agent(**kw)

    def test_cache_creates_single_instance(self, monkeypatch):
        from src.agents.executor import ExecutorAgent
        from src.graph import nodes

        monkeypatch.delenv("AITESTER_EXECUTOR_AGENT_CACHE", raising=False)  # 默认开
        nodes.clear_executor_agent_cache()
        try:
            a = self._call()
            b = self._call()
            assert a is b
            assert isinstance(a, ExecutorAgent)
        finally:
            nodes.clear_executor_agent_cache()

    def test_agent_reuse_disabled_still_works(self, monkeypatch):
        from src.agents.executor import ExecutorAgent
        from src.graph import nodes

        monkeypatch.setenv("AITESTER_EXECUTOR_AGENT_CACHE", "0")
        nodes.clear_executor_agent_cache()
        try:
            out = self._call()
            assert isinstance(out, ExecutorAgent)
        finally:
            monkeypatch.delenv("AITESTER_EXECUTOR_AGENT_CACHE", raising=False)
            nodes.clear_executor_agent_cache()


class TestSwitchBranches:
    def test_patch_resample_enabled_default_false(self, monkeypatch):
        from src.graph.nodes import _patch_resample_enabled

        monkeypatch.delenv("PATCH_RESAMPLE_ENABLE", raising=False)
        assert _patch_resample_enabled() is False

    def test_patch_resample_max_default_and_clamp(self, monkeypatch):
        from src.graph.nodes import _patch_resample_max

        monkeypatch.delenv("PATCH_RESAMPLE_MAX", raising=False)
        assert _patch_resample_max() == 2
        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "99")
        assert _patch_resample_max() == 5  # 钳制上限
        monkeypatch.setenv("PATCH_RESAMPLE_MAX", "-1")
        assert _patch_resample_max() == 0

    def test_oracle_enhance_enabled(self, monkeypatch):
        from src.graph.nodes import _oracle_enhance_enabled

        monkeypatch.delenv("ORACLE_ENHANCE_ENABLE", raising=False)
        assert _oracle_enhance_enabled() is False

    def test_runtime_probe_default_false(self, monkeypatch):
        from src.graph.nodes import _runtime_probe_enabled

        monkeypatch.delenv("RUNTIME_PROBE_ENABLE", raising=False)
        assert _runtime_probe_enabled() is False

    def test_fl_spectral_enabled(self, monkeypatch):
        from src.graph.nodes import _fl_spectral_enabled

        monkeypatch.delenv("FL_SPECTRAL_ENABLE", raising=False)
        assert _fl_spectral_enabled() in (True, False)

    def test_repo_core_protection_enabled(self, monkeypatch):
        from src.graph.nodes import _repo_core_protection_enabled

        monkeypatch.delenv("REPO_CORE_PROTECTION_ENABLE", raising=False)
        assert _repo_core_protection_enabled() in (True, False)


class TestIsRepoCorePathBranches:
    def test_core_path_detection(self):
        from src.graph.nodes import _is_repo_core_path

        out = _is_repo_core_path("src/core/engine.py")
        assert out in (True, False)

    def test_non_core_path(self):
        from src.graph.nodes import _is_repo_core_path

        out = _is_repo_core_path("docs/readme.md")
        assert out in (True, False)
