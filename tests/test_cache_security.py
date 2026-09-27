"""
18. LLM 文件缓存安全改进单元测试（0o600/0o700 权限 + TTL 过期清理）。

验证改进清单 #18（P1）：
- ensure_llm_cache_dir 新建目录时收敛 0o700；
- secure_cache_file 把缓存临时文件收敛 0o600；
- cleanup_expired_cache_files 按 mtime 删除过期缓存（含 TTL 关闭口径）；
- base_agent 写缓存路径对新目录 / 新文件应用安全权限。
"""

import json
import os
import stat
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.llm_client import (
    cleanup_expired_cache_files,
    ensure_llm_cache_dir,
    secure_cache_file,
)


def _mode_of(path: str) -> int:
    """读取文件/目录实际权限位（非 POSIX 平台降级为 0，不 fail 测试）。"""
    try:
        return stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        return 0


class TestCacheDirPermissions:
    """缓存目录 0o700 收敛。"""

    def test_new_dir_created_with_0700(self, tmp_path, monkeypatch):
        cache_dir = str(tmp_path / "cache")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        result = ensure_llm_cache_dir()
        assert result == cache_dir
        assert os.path.isdir(cache_dir)
        if sys.platform != "win32":
            assert _mode_of(cache_dir) & 0o777 == 0o700, hex(_mode_of(cache_dir))

    def test_existing_dir_untouched(self, tmp_path, monkeypatch):
        """已存在目录不强制收敛权限（共享语义保护，18. 口径）。"""
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir, mode=0o755)
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        result = ensure_llm_cache_dir()
        assert result == cache_dir
        if sys.platform != "win32":
            assert _mode_of(cache_dir) & 0o777 == 0o755

    def test_existing_dir_idempotent(self, tmp_path, monkeypatch):
        cache_dir = str(tmp_path / "cache")
        os.makedirs(cache_dir)
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        assert ensure_llm_cache_dir() == cache_dir
        assert ensure_llm_cache_dir() == cache_dir


class TestCacheFilePermissions:
    """缓存文件 0o600 收敛。"""

    def test_secure_cache_file_sets_0600(self, tmp_path):
        p = tmp_path / "f.json"
        p.write_text("{}", encoding="utf-8")
        secure_cache_file(str(p))
        if sys.platform != "win32":
            assert _mode_of(str(p)) & 0o777 == 0o600

    def test_base_agent_cache_write_applies_secure_file_perms(self, tmp_path, monkeypatch):
        """端到端：BaseAgent 写缓存文件后新文件权限 0o600（新增缓存文件即收敛）。"""
        from src.agents.base_agent import BaseAgent

        cache_dir = str(tmp_path / "cache")
        monkeypatch.setenv("AITESTER_LLM_CACHE", "1")
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        # 禁用真实 LLM 调用：mock _call_llm 返回固定文本
        agent = BaseAgent(system_prompt="sys")
        monkeypatch.setattr(BaseAgent, "_call_llm", lambda self, *a, **k: "hello")
        try:
            out = agent._call_llm_with_cache("test message")
            assert out == "hello"
            files = list((tmp_path / "cache").glob("*.json"))
            assert len(files) == 1
            if sys.platform != "win32":
                assert _mode_of(str(files[0])) & 0o777 == 0o600
        finally:
            monkeypatch.delenv("AITESTER_LLM_CACHE", raising=False)
            monkeypatch.delenv("AITESTER_LLM_CACHE_DIR", raising=False)


class TestCacheExpiry:
    """TTL 过期清理。"""

    def _mk_cache(self, cache_dir: str, names: dict[str, float]) -> None:
        """names: {文件名: mtime 时间戳}。"""
        os.makedirs(cache_dir, exist_ok=True)
        for name, ts in names.items():
            p = os.path.join(cache_dir, name)
            with open(p, "w") as f:
                json.dump({"prompt": "x", "response": "y"}, f)
            os.utime(p, (ts, ts))

    def test_removes_expired_keeps_fresh(self, tmp_path, monkeypatch):
        import time

        cache_dir = str(tmp_path / "cache")
        now = time.time()
        self._mk_cache(
            cache_dir,
            {"old.json": now - 30 * 86400, "new.json": now - 1 * 86400, "notes.txt": now - 30 * 86400},
        )
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        removed = cleanup_expired_cache_files(max_age_days=7)
        assert removed == 1  # 仅 old.json（.txt 非缓存文件不碰）
        assert os.path.exists(os.path.join(cache_dir, "new.json"))
        assert not os.path.exists(os.path.join(cache_dir, "old.json"))
        assert os.path.exists(os.path.join(cache_dir, "notes.txt"))

    def test_ttl_disabled_zero(self, tmp_path, monkeypatch):
        import time

        cache_dir = str(tmp_path / "cache")
        now = time.time()
        self._mk_cache(cache_dir, {"old.json": now - 30 * 86400})
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        assert cleanup_expired_cache_files(max_age_days=0) == 0
        assert os.path.exists(os.path.join(cache_dir, "old.json"))

    def test_env_ttl_default_seven_days(self, tmp_path, monkeypatch):
        import time

        cache_dir = str(tmp_path / "cache")
        now = time.time()
        self._mk_cache(
            cache_dir,
            {"just_over.json": now - 8 * 86400, "inside.json": now - 6 * 86400},
        )
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", cache_dir)
        monkeypatch.setenv("AITESTER_LLM_CACHE_TTL_DAYS", "7")
        assert cleanup_expired_cache_files() == 1
        assert os.path.exists(os.path.join(cache_dir, "inside.json"))
        assert not os.path.exists(os.path.join(cache_dir, "just_over.json"))

    def test_missing_dir_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AITESTER_LLM_CACHE_DIR", str(tmp_path / "nope"))
        assert cleanup_expired_cache_files() == 0


# ─── 15. 多进程缓存协调（命中率观测层）──────────────────────────────────
class TestCacheHitRateObservation:
    """LLM 文件缓存命中率记录/读取（record_cache_hit / get_cache_hit_rate）。"""

    def test_hit_rate_none_when_no_records(self, monkeypatch):
        from src.agents import llm_client

        llm_client._LLM_CACHE_HIT_STATS["file_hits"] = 0
        llm_client._LLM_CACHE_HIT_STATS["file_misses"] = 0
        assert llm_client.get_cache_hit_rate() is None

    def test_hit_rate_computation(self, monkeypatch):
        from src.agents import llm_client

        llm_client._LLM_CACHE_HIT_STATS["file_hits"] = 0
        llm_client._LLM_CACHE_HIT_STATS["file_misses"] = 0
        llm_client.record_cache_hit(True)
        llm_client.record_cache_hit(True)
        llm_client.record_cache_hit(False)
        llm_client.record_cache_hit(False)
        # 2 hits / 4 total = 0.5
        assert llm_client.get_cache_hit_rate() == 0.5

    def test_hit_rate_all_hits(self, monkeypatch):
        from src.agents import llm_client

        llm_client._LLM_CACHE_HIT_STATS["file_hits"] = 0
        llm_client._LLM_CACHE_HIT_STATS["file_misses"] = 0
        llm_client.record_cache_hit(True)
        assert llm_client.get_cache_hit_rate() == 1.0

    def test_hit_rate_all_misses(self, monkeypatch):
        from src.agents import llm_client

        llm_client._LLM_CACHE_HIT_STATS["file_hits"] = 0
        llm_client._LLM_CACHE_HIT_STATS["file_misses"] = 0
        llm_client.record_cache_hit(False)
        assert llm_client.get_cache_hit_rate() == 0.0

    def test_workflow_stats_includes_hit_rate(self, monkeypatch):
        from src.agents import llm_client
        from src.graph.workflow import get_workflow_stats

        llm_client._LLM_CACHE_HIT_STATS["file_hits"] = 0
        llm_client._LLM_CACHE_HIT_STATS["file_misses"] = 0
        llm_client.record_cache_hit(True)
        llm_client.record_cache_hit(False)
        stats = get_workflow_stats()
        assert stats["llm_cache"]["hit_rate"] == 0.5
        # 恢复计数器，避免污染 get_workflow_stats 的既有断言（test_workflow.py）
        llm_client.reset_cache_hit_stats()


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
