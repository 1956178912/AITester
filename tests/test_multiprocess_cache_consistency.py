"""
P1 多进程缓存一致性 + 3.6 语义缓存假阳性抽样验证测试（2026-09-29 批次）。

外部参照：Clinejection 事件（恶意 issue 标题经 prompt injection 污染构建
缓存 → 跨工作流向 4,000 名开发者推送恶意 npm 版本）、KV 缓存时间边通道
研究（共享缓存 = 隐含信息通道）、银行业语义缓存假阳性实测（阈值 0.7
假阳性率 99% → 设计优化后 3.8%；阈值 0.95 → 15-25% 假阳性）。

覆盖：
- 缓存文件被"外部写入"（模拟跨工作流投毒）场景：读侧键材料不匹配 /
  创建者不匹配时按未命中处理（不应用被污染条目）；
- 负缓存过期后外部写入合法条目可恢复命中（"文件是事实来源"语义）；
- 语义缓存假阳性抽样：确定性采样序列 + 统计口径（confirmed /
  false_positive / fp_rate）。
"""

import json
import os
import sys
import time
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents import base_agent
from src.agents.base_agent import BaseAgent
from src.agents.llm_client import cache_creator_ok
from src.agents.semantic_cache import (
    get_false_positive_stats,
    get_semantic_cache_stats,
    record_false_positive_check,
    reset_false_positive_stats,
    should_sample_false_positive,
)


def _make_agent(system_prompt: str = "test system prompt") -> BaseAgent:
    return BaseAgent(system_prompt=system_prompt)


class TestExternalWriteScenarios:
    """缓存目录被外部写入（投毒模拟）场景。"""

    def test_poisoned_key_material_mismatch_not_applied(self, monkeypatch, tmp_path):
        """外部把同 md5 文件的 prompt 改成别的内容（键材料不匹配）→ 不命中。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))
        cache_dir = tmp_path / "cache"
        base_agent.clear_llm_lru_cache()

        agent = _make_agent()
        # 首次调用建立合法缓存文件
        with patch.object(agent, "_call_llm", MagicMock(return_value="good")):
            assert agent._call_llm_with_cache("k") == "good"
        # 模拟外部投毒：同文件 prompt 字段被改写（键材料失配）
        files = list(cache_dir.glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        data["prompt"] = "tampered"
        files[0].write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        base_agent.clear_llm_lru_cache()

        mock = MagicMock(return_value="fresh")
        with patch.object(agent, "_call_llm", mock):
            assert agent._call_llm_with_cache("k") == "fresh"
        assert mock.call_count == 1  # 被污染条目未被应用，走真实调用

    def test_cross_user_creator_not_applied(self, monkeypatch, tmp_path):
        """creator_uid 不一致（跨用户/共享 CI 投毒）→ 不命中。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))
        monkeypatch.setenv("AITESTER_CACHE_CREATOR", "me")
        cache_dir = tmp_path / "cache"
        base_agent.clear_llm_lru_cache()

        agent = _make_agent()
        with patch.object(agent, "_call_llm", MagicMock(return_value="mine")):
            agent._call_llm_with_cache("k")
        # 外部（其他用户）写入同键文件（creator 不同）
        files = list(cache_dir.glob("*.json"))
        data = json.loads(files[0].read_text(encoding="utf-8"))
        data["creator_uid"] = "attacker"
        files[0].write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        base_agent.clear_llm_lru_cache()

        mock = MagicMock(return_value="recomputed")
        with patch.object(agent, "_call_llm", mock):
            assert agent._call_llm_with_cache("k") == "recomputed"
        assert mock.call_count == 1  # 非本用户条目不命中
        assert cache_creator_ok("attacker") is False
        assert cache_creator_ok("me") is True

    def test_negative_cache_expiry_rechecks_external_write(self, monkeypatch, tmp_path):
        """负缓存过期后，外部合法写入可恢复命中（文件是事实来源语义）。"""
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "cache"))
        cache_dir = tmp_path / "cache"
        base_agent.clear_llm_lru_cache()

        agent = _make_agent()
        mock1 = MagicMock(return_value="v1")
        with patch.object(agent, "_call_llm", mock1):
            agent._call_llm_with_cache("n")
        # 清 L1 + 删文件（外部清理）
        for key in list(base_agent._lru_cache):
            if key[1] == "n":
                del base_agent._lru_cache[key]
        for f in cache_dir.glob("*.json"):
            f.unlink()
        mock2 = MagicMock(return_value="v2")
        with patch.object(agent, "_call_llm", mock2):
            assert agent._call_llm_with_cache("n") == "v2"
        # 人为记"刚过期"负缓存条目（模拟 TTL 窗口已过的惰性清理路径）
        files = list(cache_dir.glob("*.json"))
        assert len(files) == 1
        neg_key = (str(files[0]), "n", None)
        base_agent._lru_negatives[neg_key] = time.time() - base_agent._LRU_NEGATIVE_TTL_SECONDS - 1
        for key in list(base_agent._lru_cache):
            if key[1] == "n":
                del base_agent._lru_cache[key]
        with patch.object(agent, "_call_llm", mock2):
            # 负缓存过期 → 重读文件命中 v2（零新增 LLM 调用）
            assert agent._call_llm_with_cache("n") == "v2"
        assert mock2.call_count == 1  # 命中路径不再透传


class TestSemanticFalsePositiveSampling:
    """3.6 语义缓存假阳性抽样验证（确定性采样 + 统计口径）。"""

    def setup_method(self):
        reset_false_positive_stats()

    def test_sampling_disabled_by_zero_rate(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "0")
        assert should_sample_false_positive() is False
        assert should_sample_false_positive() is False

    def test_deterministic_sample_every_n(self, monkeypatch):
        """默认 10% → 每 10 次命中抽 1 次（确定性，可复现）。"""
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "0.1")
        seq = [should_sample_false_positive() for _ in range(10)]
        assert seq.count(True) == 1  # 第 10 次命中触发
        seq2 = [should_sample_false_positive() for _ in range(10)]
        assert seq2.count(True) == 1  # 下一个周期同样第 10 次

    def test_stats_ratio_computation(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "1")
        record_false_positive_check(confirmed=True)
        record_false_positive_check(confirmed=True)
        record_false_positive_check(confirmed=False)
        stats = get_false_positive_stats()
        assert stats["fp_checked"] == 3
        assert stats["fp_confirmed"] == 2
        assert stats["fp_false_positive"] == 1
        assert stats["fp_rate"] == 1 / 3

    def test_stats_merged_into_semantic_stats(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "1")
        record_false_positive_check(confirmed=False)
        s = get_semantic_cache_stats()
        assert "fp_checked" in s and "fp_rate" in s
        assert s["fp_checked"] == 1
        assert s["fp_rate"] == 1.0


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
