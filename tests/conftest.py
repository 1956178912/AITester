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


@pytest.fixture(autouse=True)
def _isolate_llm_cache(tmp_path, monkeypatch) -> None:
    """默认关闭 LLM 文件缓存，并将缓存目录指向临时目录（测试间互不干扰）。

    需要验证缓存行为的测试可显式 monkeypatch 覆盖这两个环境变量。
    """
    monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
    monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "llm_cache"))
    yield
