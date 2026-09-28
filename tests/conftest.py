"""
全局 pytest fixture：为 AITester 测试提供稳定的 LLM 缓存隔离。

背景：
- base_agent 的 LLM 调用现已接入文件级缓存（src/cache/*.json，省 token）。
- 缓存键 = md5(user_message + system_prompt)，相同 prompt 会命中彼此留下的缓存文件，
  导致 mock 的 _call_llm 不被调用 → 测试相互干扰、结果 flaky。

策略：
- autouse fixture 在每个测试前关闭缓存开关（AITESTER_LLM_CACHE=0），
  使 _call_llm_with_cache 直接透传 _call_llm，行为与旧逻辑完全一致。
- 同时将缓存目录指向临时目录（AITESTER_LLM_CACHE_DIR），即使误开启也不污染 src/cache。
"""

import pytest

from src.agents.llm_client import clear_llm_cache_option_memory
from src.graph import nodes as _nodes


@pytest.fixture(autouse=True)
def _isolate_agent_instance_caches() -> None:
    """每个测试前清空 nodes 模块的 Agent 实例复用缓存（2026-09-28 性能优化）。

    _planner_node / _generator_node / _debugger_node / _diagnosis_node 经
    get_or_create_agent 复用 BaseAgent 子类实例（按类名分键，DCL + FIFO），
    _executor_node 经 _get_or_create_executor_agent 按沙箱配置元组分键复用
    ExecutorAgent 实例。跨测试复用在"测试以 MagicMock patch 类"的口径下
    会产生 mock 实例与真实类缓存键错位——每测试前清空恢复"每次新建"的
    历史口径（测试 mock 类被替换后不再被前一个测试的真实实例污染）。
    """
    _nodes.clear_agent_instance_cache()
    _nodes.clear_executor_agent_cache()
    yield
    _nodes.clear_agent_instance_cache()
    _nodes.clear_executor_agent_cache()


@pytest.fixture(autouse=True)
def _isolate_llm_cache(tmp_path, monkeypatch) -> None:
    """默认关闭 LLM 文件缓存，并将缓存目录指向临时目录（测试间互不干扰）。

    需要验证缓存行为的测试可显式 monkeypatch 覆盖这两个环境变量。
    """
    monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
    monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "llm_cache"))
    # 2026-09-28 性能优化配套：llm_client 热路径把缓存开关/目录做了进程内
    # 环境变量记忆（首次调用定值后复用，省每次 LLM 调用的两次 getenv）。
    # autouse 隔离在本 fixture 内切目录/开关，必须在切后清一次记忆；teardown
    # （monkeypatch 还原环境变量后）再清一次，恢复"读环境变量"历史口径
    # （conftest 是测试入口模块，顶层导入保持 import 排序干净、零运行时成本）
    clear_llm_cache_option_memory()
    yield
    clear_llm_cache_option_memory()
