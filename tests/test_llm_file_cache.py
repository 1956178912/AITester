"""
LLM 文件缓存（base_agent._call_llm_with_cache）集成测试。

验证「省 token」目标：
- 开启缓存时，相同 prompt 的第二次调用命中缓存文件，底层 _call_llm 只被调用一次
- 缓存文件按 md5(prompt+system) 命名并持久化到缓存目录
- 关闭缓存（AITESTER_LLM_CACHE=0，conftest 默认）时，_call_llm_with_cache 每次透传，不落盘

注意：全局 conftest 的 autouse fixture 默认关闭缓存并指向临时目录；
需要验证缓存行为的用例在自身用 monkeypatch 覆盖这两个环境变量。
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.base_agent import BaseAgent


def _make_agent(system_prompt: str = "test system prompt") -> BaseAgent:
    """构造一个 BaseAgent 实例（LLM 客户端在测试环境可安全初始化）。"""
    return BaseAgent(system_prompt=system_prompt)


class TestCacheEnabled:
    """缓存开启时的行为。"""

    def test_second_call_hits_cache(self, monkeypatch, tmp_path):
        """相同 prompt 第二次调用命中缓存，底层仅调用一次（省 1 次 LLM 调用）。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))

        agent = _make_agent()
        mock_llm = MagicMock(return_value="```python\ndef test_x(): pass\n```")

        with patch.object(agent, "_call_llm", mock_llm):
            first = agent._call_llm_with_cache("hello")
            second = agent._call_llm_with_cache("hello")

        assert first == second == mock_llm.return_value
        # 第二次命中缓存，底层 _call_llm 只调用一次
        assert mock_llm.call_count == 1

    def test_writes_cache_file(self, monkeypatch, tmp_path):
        """成功后写入缓存文件到指定目录。"""
        cache_dir = tmp_path / "cache"
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(cache_dir))

        agent = _make_agent()
        with patch.object(agent, "_call_llm", MagicMock(return_value="resp")):
            agent._call_llm_with_cache("unique-prompt")

        files = list(cache_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["prompt"] == "unique-prompt"
        assert data["system"] == agent.system_prompt
        assert data["response"] == "resp"
        assert isinstance(data["timestamp"], float)  # 已修复为 time.time()

    def test_different_prompts_not_shared(self, monkeypatch, tmp_path):
        """不同 prompt 缓存键不同，互不命中。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))

        agent = _make_agent()
        mock_llm = MagicMock(side_effect=["A", "B"])

        with patch.object(agent, "_call_llm", mock_llm):
            assert agent._call_llm_with_cache("prompt-1") == "A"
            assert agent._call_llm_with_cache("prompt-2") == "B"
        # 两个不同 prompt 都实际调用了底层
        assert mock_llm.call_count == 2


class TestCacheDisabled:
    """缓存关闭时（conftest 默认行为）每次透传，不落盘。"""

    def test_calls_underlying_every_time(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AITESTER_LLM_CACHE", "0")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))

        agent = _make_agent()
        mock_llm = MagicMock(side_effect=["A", "B", "C"])

        with patch.object(agent, "_call_llm", mock_llm):
            assert agent._call_llm_with_cache("x") == "A"
            assert agent._call_llm_with_cache("x") == "B"  # 不命中，再次透传
        # 关闭缓存：两次相同 prompt 都透传，不写缓存文件
        assert mock_llm.call_count == 2
        assert not list((tmp_path / "cache").glob("*.json"))


if __name__ == "__main__":
    raise SystemExit(__import__("pytest").main([__file__, "-v"]))
