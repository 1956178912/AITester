"""2026-09-28 优化轮：Agent 实例复用缓存 + llm_client 开关/目录记忆的回归测试。

覆盖三项"默认行为不变、性能口径新增"的优化：
- src/graph/nodes._get_or_create_executor_agent（ExecutorAgent 按沙箱配置分键缓存）
- src/graph/nodes._get_or_create_debugger_agent（DebuggerAgent 类级缓存）
- src/agents/llm_client._llm_cache_enabled / _llm_cache_dir 的环境变量记忆
  与 clear_llm_cache_option_memory 清除钩子（conftest autouse 已接线）
"""

from __future__ import annotations

import pytest

from src.agents.executor import ExecutorAgent
from src.graph import nodes as _nodes


class TestAllNodeAgentsReuse:
    """_planner_node / _generator_node / _executor_node 均经 get_or_create_agent 复用。"""

    def setup_method(self) -> None:
        _nodes.clear_agent_instance_cache()
        _nodes.clear_executor_agent_cache()

    def teardown_method(self) -> None:
        _nodes.clear_agent_instance_cache()
        _nodes.clear_executor_agent_cache()

    def test_planner_generator_debugger_share_generic_cache(self) -> None:
        from src.agents.generator import GeneratorAgent
        from src.agents.planner import PlannerAgent

        assert _nodes.get_or_create_agent(PlannerAgent) is not None
        assert _nodes.get_or_create_agent(GeneratorAgent) is not None
        assert _nodes._get_or_create_debugger_agent() is not None
        assert set(_nodes._agent_instance_cache) == {
            "PlannerAgent",
            "GeneratorAgent",
            "DebuggerAgent",
        }


class TestExecutorAgentReuse:
    """_executor_node 的 ExecutorAgent 实例按沙箱配置分键复用（2026-09-28 优化）。"""

    def setup_method(self) -> None:
        _nodes.clear_executor_agent_cache()

    def teardown_method(self) -> None:
        _nodes.clear_executor_agent_cache()

    def test_same_config_returns_same_instance(self) -> None:
        a = _nodes._get_or_create_executor_agent(
            timeout=30,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        b = _nodes._get_or_create_executor_agent(
            timeout=30,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        assert a is b
        assert isinstance(a, ExecutorAgent)

    def test_different_timeout_gets_different_instance(self) -> None:
        a = _nodes._get_or_create_executor_agent(
            timeout=30,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        b = _nodes._get_or_create_executor_agent(
            timeout=60,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        assert a is not b
        assert a.timeout == 30 and b.timeout == 60

    def test_cache_disabled_by_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AITESTER_EXECUTOR_AGENT_CACHE", "0")
        a = _nodes._get_or_create_executor_agent(
            timeout=30,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        b = _nodes._get_or_create_executor_agent(
            timeout=30,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        # 开关关闭 → 每次新建
        assert a is not b
        assert len(_nodes._executor_agent_cache) == 0

    def test_clear_cache_empties(self) -> None:
        _nodes._get_or_create_executor_agent(
            timeout=30,
            use_docker=False,
            use_venv=False,
            auto_install_deps=False,
            dep_install_timeout=120,
            docker_image="aitester:latest",
        )
        assert len(_nodes._executor_agent_cache) == 1
        _nodes.clear_executor_agent_cache()
        assert len(_nodes._executor_agent_cache) == 0


class TestDebuggerAgentReuse:
    """_debugger_node / _diagnosis_node 的 DebuggerAgent 类级复用（2026-09-28 优化）。"""

    def setup_method(self) -> None:
        _nodes.clear_agent_instance_cache()

    def teardown_method(self) -> None:
        _nodes.clear_agent_instance_cache()

    def test_same_instance_across_calls(self) -> None:
        a = _nodes._get_or_create_debugger_agent()
        b = _nodes._get_or_create_debugger_agent()
        assert a is b
        from src.agents.debugger import DebuggerAgent

        assert isinstance(a, DebuggerAgent)

    def test_cache_disabled_by_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AITESTER_AGENT_REUSE", "0")
        a = _nodes._get_or_create_debugger_agent()
        b = _nodes._get_or_create_debugger_agent()
        assert a is not b
        assert len(_nodes._agent_instance_cache) == 0

    def test_clear_cache_empties(self) -> None:
        _nodes._get_or_create_debugger_agent()
        assert len(_nodes._agent_instance_cache) == 1
        _nodes.clear_agent_instance_cache()
        assert len(_nodes._agent_instance_cache) == 0

    def test_multiple_classes_use_class_name_keys(self) -> None:
        """通用工厂按类名分键：各 BaseAgent 子类各自独立复用一个实例。"""
        from src.agents.generator import GeneratorAgent
        from src.agents.planner import PlannerAgent

        g1 = _nodes.get_or_create_agent(GeneratorAgent)
        g2 = _nodes.get_or_create_agent(GeneratorAgent)
        _nodes.get_or_create_agent(PlannerAgent)
        d1 = _nodes._get_or_create_debugger_agent()
        assert g1 is g2
        assert g1 is not d1
        assert set(_nodes._agent_instance_cache) == {"GeneratorAgent", "PlannerAgent", "DebuggerAgent"}


class TestLlmCacheOptionMemory:
    """llm_client 的缓存开关/目录环境变量记忆（2026-09-28 优化）。

    热路径（每次 LLM 调用）读 _llm_cache_enabled / _llm_cache_dir 时，
    首次调用定值后复用进程内记忆（省两次 getenv）；
    clear_llm_cache_option_memory 清除后重新读环境变量（测试隔离口径恢复）。
    conftest autouse fixture 已在每个测试前后各清一次记忆，
    使 monkeypatch.setenv 的新值立即生效、teardown 后恢复历史口径。
    """

    def setup_method(self) -> None:
        from src.agents.llm_client import clear_llm_cache_option_memory

        clear_llm_cache_option_memory()

    def teardown_method(self) -> None:
        from src.agents.llm_client import clear_llm_cache_option_memory

        clear_llm_cache_option_memory()

    def test_enabled_memory_reads_env_once(self, monkeypatch) -> None:
        from src.agents import llm_client as lc

        # 本方法内先清一次记忆（setup_method 可能已被前置测试消费过），
        # 保证读到的是方法内设置的环境变量值
        lc.clear_llm_cache_option_memory()
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        assert lc._llm_cache_enabled() is False
        # 记忆生效后，外部修改环境变量不影响当前进程记忆值
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        assert lc._llm_cache_enabled() is False  # 仍读旧值（0）
        # 清除记忆后恢复读环境变量的历史口径
        lc.clear_llm_cache_option_memory()
        assert lc._llm_cache_enabled() is True  # 读到新值 1

    def test_dir_memory_reads_env_once(self, monkeypatch, tmp_path) -> None:
        from src.agents import llm_client as lc

        lc.clear_llm_cache_option_memory()
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "a"))
        first = lc._llm_cache_dir()
        assert first == str(tmp_path / "a")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "b"))
        assert lc._llm_cache_dir() == first  # 记忆值
        lc.clear_llm_cache_option_memory()
        assert lc._llm_cache_dir() == str(tmp_path / "b")  # 清记忆后读新值


@pytest.mark.usefixtures("_isolate_llm_cache")
class TestConftestClearsOptionMemory:
    """conftest autouse fixture 必须在 env 切换前后各清一次 llm_client 记忆。"""

    def test_fixture_reset_memory_and_env(self, tmp_path) -> None:
        """autouse fixture（_isolate_llm_cache）进入测试方法前：
        1) setenv AITESTER_LLM_CACHE=0 + 新 tmp_path 缓存目录；
        2) 清除 llm_client 的开关/目录进程内记忆。

        因此本方法体内（无额外 setenv）_llm_cache_enabled 应读到
        fixture 切后的新环境值（False），_llm_cache_dir 应读到
        fixture 切后的新 tmp 目录——而非前置测试遗留的记忆值。
        方法内先置入遗留记忆值，再重放"清记忆"序列验证钩子语义。
        """
        from src.agents import llm_client as lc

        lc._llm_cache_option_memory = True
        lc._llm_cache_dir_memory = "stale_dir_from_previous_test"
        # 本方法无显式 setenv，conftest autouse 在方法前已 setenv "0"+新 tmp 目录
        # 并清记忆——手动重放该序列：
        lc.clear_llm_cache_option_memory()
        assert lc._llm_cache_enabled() is False
        assert lc._llm_cache_dir() == str(tmp_path / "llm_cache")
        # 方法内对全局记忆的写入在断言后清除，避免污染后续测试
        lc.clear_llm_cache_option_memory()
