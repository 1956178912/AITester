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
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import base_agent
from src.agents.base_agent import BaseAgent


@pytest.fixture(autouse=True)
def _clear_llm_lru():
    """每个测试前后清空 LLM 文件缓存的进程内 LRU（含负缓存）。

    LRU 键以缓存文件路径为锚，跨测试目录（tmp_path）不同故天然隔离；
    显式清空防御同路径键在不同测试间残留负缓存/命中值（缓存目录被外部
    清理后的口径一致性）。
    """
    base_agent.clear_llm_lru_cache()
    yield
    base_agent.clear_llm_lru_cache()


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

    def test_second_write_does_not_call_makedirs(self, monkeypatch, tmp_path):
        """写缓存热路径：目录已存在时第二次写入不重复调用 os.makedirs。

        0.8 优化回归：makedirs(exist_ok=True) 每次写都发 stat 系统调用；
        命中后目录必存在，改用 isdir 短路后第二次写入零 makedirs 调用。
        """
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))

        agent = _make_agent()
        makedirs_calls = []
        original_makedirs = os.makedirs

        def spy_makedirs(*args, **kwargs):
            makedirs_calls.append(kwargs)
            return original_makedirs(*args, **kwargs)

        with (
            patch.object(agent, "_call_llm", MagicMock(return_value="resp")),
            patch("src.agents.base_agent.os.makedirs", side_effect=spy_makedirs),
        ):
            agent._call_llm_with_cache("p1")
            agent._call_llm_with_cache("p2")
        # 两次写入：首次目录缺失调用 makedirs 一次；第二次 isdir 命中，零调用
        assert len(makedirs_calls) == 1

    def test_temperature_keying_avoids_cross_hit(self, monkeypatch, tmp_path):
        """不同 temperature 走不同缓存键，不会命中对方产物（3.3 动态策略）。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))

        agent = _make_agent()
        mock_llm = MagicMock(side_effect=["temp-07", "default"])

        with patch.object(agent, "_call_llm", mock_llm):
            assert agent._call_llm_with_cache("same", temperature=0.7) == "temp-07"
            # 默认温度（temperature=None 未传入）键不同，不命中上一份
            assert agent._call_llm_with_cache("same") == "default"
        assert mock_llm.call_count == 2

    def test_system_prompt_participates_in_key(self, monkeypatch, tmp_path):
        """0.9 回归：缓存键材料按 prompt/system 分段（\\x00 分隔），system_prompt
        变化产生不同键，互不命中（此前拼接处漏分隔符，理论上可同构碰撞）。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))

        agent_a = _make_agent(system_prompt="system A")
        agent_b = _make_agent(system_prompt="system B")
        mock_llm = MagicMock(side_effect=["resp-a", "resp-b"])

        with patch.object(agent_a, "_call_llm", mock_llm), patch.object(agent_b, "_call_llm", mock_llm):
            assert agent_a._call_llm_with_cache("same-prompt") == "resp-a"
            # 同 user_message、不同 system_prompt：键不同，不命中 agent_a 的缓存
            assert agent_b._call_llm_with_cache("same-prompt") == "resp-b"
        assert mock_llm.call_count == 2

    def test_negative_cache_expiry_rechecks_file(self, monkeypatch, tmp_path):
        """0.10 回归：负缓存带 TTL 过期——窗口内同键调用跳过文件重读（省
        "读不存在的文件" IO）；TTL 过期后重新读文件，外部写入的缓存文件
        可被读到并命中。

        场景模拟"磁盘缓存目录被外部清理 + 进程 LRU 正缓存条目被淘汰"：
        1. 首次调用写缓存文件 + L1 回填；
        2. 清 L1（模拟进程重启/淘汰）+ 删缓存文件（模拟外部清理）→
           该键 L1/文件双双缺失，再调用走"文件不存在"路径，记负缓存；
        3. 负缓存 TTL 窗口内：同键再次调用跳过文件重读（省 IO），透调 LLM；
        4. 外部在窗口外重写缓存文件 + TTL 过期 → 重新读文件，命中。

        注：负缓存窗口内的调用仍付 1 次 LLM 调用（省的是文件读取 IO，
        不是 LLM 调用本身）；TTL 到期后恢复"文件是事实来源"语义。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))
        cache_dir = tmp_path / "cache"

        agent = _make_agent()
        mock_llm = MagicMock(return_value="resp-1")
        with patch.object(agent, "_call_llm", mock_llm):
            # 首次：文件不存在 → 透调 + 写缓存文件 + L1 回填
            assert agent._call_llm_with_cache("neg") == "resp-1"
            assert mock_llm.call_count == 1

        # 模拟"进程重启 + 外部清理缓存目录"：清 L1 正缓存 + 删缓存文件
        for key in list(base_agent._lru_cache):
            if key[1] == "neg":
                del base_agent._lru_cache[key]
        cache_file_paths = list(cache_dir.glob("*.json"))
        assert len(cache_file_paths) == 1
        cache_file_paths[0].unlink()
        assert not list(cache_dir.glob("*.json"))

        mock_llm2 = MagicMock(return_value="resp-2")
        with patch.object(agent, "_call_llm", mock_llm2):
            # L1 缺失 + 文件被删 → FileNotFoundError 记负缓存 + 透调 LLM + 写回
            assert agent._call_llm_with_cache("neg") == "resp-2"
            assert mock_llm2.call_count == 1
        # 此时负缓存已被"写成功"清除；再清 L1 模拟第二次进程重启
        for key in list(base_agent._lru_cache):
            if key[1] == "neg":
                del base_agent._lru_cache[key]
        # 验证：写成功后负缓存条目已被清除（_lru_store 的 _lru_negatives.pop）
        assert not any(k[1] == "neg" for k in base_agent._lru_negatives)

        # 人为记一个"刚过期"的负缓存条目（时间戳 = 当前 - TTL - 1），验证
        # _lru_check_negative 的过期惰性清理路径（文件实际存在）
        _neg_key = (str(cache_file_paths[0]), "neg", None)
        base_agent._lru_negatives[_neg_key] = time.time() - base_agent._LRU_NEGATIVE_TTL_SECONDS - 1
        with patch.object(agent, "_call_llm", mock_llm2):
            # 负缓存已过期 → 重新读文件，命中磁盘缓存中的 resp-2（零 LLM 调用）
            assert agent._call_llm_with_cache("neg") == "resp-2"
        assert mock_llm2.call_count == 1


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
