"""
5.1 语义级 LLM 缓存（semantic_cache 模块）单元测试。

覆盖：
- 开关默认关闭（find/upsert 零行为，精确缓存口径保持）；
- 嵌入后端缺失时自动降级（find 恒 None，不抛异常）；
- 嵌入可用时的命中/未命中判定（阈值口径）；
- 进程内索引单例与 reset；
- 观测统计（get_semantic_cache_stats）。

嵌入后端经 monkeypatch 注入伪向量（不依赖真实 CodeBERT/transformers）。
"""

from __future__ import annotations

import pytest

import src.utils.embedding_utils as embedding_utils
from src.agents import semantic_cache as sc
from src.agents.semantic_cache import (
    build_semantic_index_from_cache_dir,
    find_semantic_cache,
    get_semantic_cache_stats,
    get_semantic_index,
    reset_semantic_index,
)

# 伪嵌入：按关键词出现情况取正交基向量——用于纯逻辑验证余弦判定
# （不依赖真实模型）：
# - 仅 "alpha" → vec_a；仅 "beta" → vec_b（a·b = 0 → 余弦 0）；
# - 同时含两者 → vec_ab = vec_a + vec_b（与 vec_a 余弦 = 1/√2 ≈ 0.707）；
# - 关键词判定顺序敏感（"alpha beta" 同时命中前两分支，先 return vec_a，
#   故 vec_ab 分支不可达——测试中"混合文本"用例直接用 "gamma" 触发
#   第四分支，混合语义用例仅验证"同词文本"命中路径，不做混合向量测试）。
_DEFS = {
    "vec_a": [1.0, 0.0, 0.0, 0.0],
    "vec_b": [0.0, 1.0, 0.0, 0.0],
    "vec_other": [0.0, 0.0, 1.0, 0.0],
}


def _fake_embed(text: str) -> list[float] | None:
    t = (text or "").strip().lower()
    has_alpha = "alpha" in t
    has_beta = "beta" in t
    if has_alpha and has_beta:
        # 同时命中关键词：向量 = vec_a + vec_b（余弦 vs vec_a = 1/√2）
        return [1.0, 1.0, 0.0, 0.0]
    if has_alpha:
        return list(_DEFS["vec_a"])
    if has_beta:
        return list(_DEFS["vec_b"])
    return list(_DEFS["vec_other"])


@pytest.fixture(autouse=True)
def _reset_index():
    reset_semantic_index()
    yield
    reset_semantic_index()


@pytest.fixture
def _embed_on(monkeypatch):
    """伪嵌入可用（模拟 CodeBERT 已加载）。"""
    monkeypatch.setenv("SEMANTIC_CACHE_ENABLE", "true")
    monkeypatch.setattr(embedding_utils, "embed_text", _fake_embed)
    yield


@pytest.fixture
def _embed_off(monkeypatch):
    """嵌入后端缺失（返回 None，保守降级口径）。"""
    monkeypatch.setenv("SEMANTIC_CACHE_ENABLE", "true")
    monkeypatch.setattr(embedding_utils, "embed_text", lambda t: None)
    yield


class TestDisabledByDefault:
    """SEMANTIC_CACHE_ENABLE 默认 false：全部路径零行为。"""

    def test_find_returns_none(self) -> None:
        assert find_semantic_cache("f.json", "any prompt") is None

    def test_upsert_returns_false(self) -> None:
        assert get_semantic_index().upsert("f.json", "p", "r") is False

    def test_stats_report_disabled(self) -> None:
        s = get_semantic_cache_stats()
        assert s["enabled"] is False
        assert s["entries"] == 0

    def test_build_returns_zero(self, tmp_path) -> None:
        assert build_semantic_index_from_cache_dir(str(tmp_path)) == 0


class TestEmbedBackendMissing:
    """嵌入后端缺失：find/upsert 静默降级（不抛异常，索引为空）。"""

    def test_upsert_skipped(self, _embed_off) -> None:
        assert get_semantic_index().upsert("f.json", "alpha", "resp") is False
        s = get_semantic_cache_stats()
        assert s["entries"] == 0
        assert s["embed_failures"] == 1

    def test_find_returns_none(self, _embed_off) -> None:
        # 先强制塞一条索引（绕过 upsert 的嵌入守卫）验证查找侧降级
        idx = get_semantic_index()
        idx._entries["f.json"] = sc._SemanticEntry(
            cache_file="f.json", prompt="alpha", response="r", embedding=_DEFS["vec_a"]
        )
        assert find_semantic_cache("f.json", "beta") is None


class TestSemanticHit:
    """嵌入可用时：余弦 >= 阈值命中，< 阈值未命中。"""

    def test_exact_same_prompt_hits(self, _embed_on, monkeypatch) -> None:
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.9")
        get_semantic_index().upsert("f1.json", "fix alpha bug", "resp1")
        hit = find_semantic_cache("f1.json", "fix alpha bug")
        assert hit is not None
        assert hit[1] == "resp1"

    def test_orthogonal_prompt_misses(self, _embed_on, monkeypatch) -> None:
        """余弦 0 < 0.92 → 未命中（保守：宁可漏命中不可误命中）。"""
        get_semantic_index().upsert("f1.json", "alpha", "resp1")
        hit = find_semantic_cache("f1.json", "beta")
        assert hit is None

    def test_threshold_reduces_hits(self, _embed_on, monkeypatch) -> None:
        """混合文本嵌入与 vec_a 余弦 = 1/√2 ≈ 0.707：阈值 0.5 命中、0.8 未命中。"""
        get_semantic_index().upsert("f1.json", "alpha", "resp1")
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.5")
        assert find_semantic_cache("f1.json", "alpha beta") is not None
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.8")
        assert find_semantic_cache("f1.json", "alpha beta") is None
        assert get_semantic_cache_stats()["misses"] == 1

    def test_stats_counted(self, _embed_on, monkeypatch) -> None:
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.9")
        get_semantic_index().upsert("f1.json", "alpha", "resp1")
        find_semantic_cache("f1.json", "alpha")  # hit
        find_semantic_cache("f1.json", "beta")  # miss
        s = get_semantic_cache_stats()
        assert s["hits"] == 1
        assert s["misses"] == 1
        assert s["entries"] == 1

    def test_response_update_path(self, _embed_on, monkeypatch) -> None:
        """find 未命中 + response_for_update → 新条目入索引（下轮可命中）。"""
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.9")
        out = find_semantic_cache("f9.json", "alpha", response_for_update="new_resp")
        assert out is None  # 首查未命中
        hit = find_semantic_cache("f9.json", "alpha")
        assert hit is not None
        assert hit[0] == "f9.json"
        assert hit[1] == "new_resp"


class TestIndexBuild:
    """从文件缓存目录构建索引。"""

    def test_build_scans_json_files(self, _embed_on, tmp_path) -> None:
        import json

        f1 = tmp_path / "a.json"
        f1.write_text(json.dumps({"prompt": "alpha", "response": "r1"}), encoding="utf-8")
        f2 = tmp_path / "b.json"
        f2.write_text(json.dumps({"prompt": "beta", "response": "r2"}), encoding="utf-8")
        added = build_semantic_index_from_cache_dir(str(tmp_path))
        assert added == 2
        assert get_semantic_cache_stats()["entries"] == 2

    def test_build_skips_corrupt_files(self, _embed_on, tmp_path) -> None:
        good = tmp_path / "ok.json"
        good.write_text('{"prompt": "alpha", "response": "r"}', encoding="utf-8")
        bad = tmp_path / "bad.json"
        bad.write_text("{corrupted", encoding="utf-8")
        assert build_semantic_index_from_cache_dir(str(tmp_path)) == 1

    def test_max_entries_env_respected(self, _embed_on, tmp_path, monkeypatch) -> None:
        import json

        for i in range(10):
            (tmp_path / f"f{i}.json").write_text(
                json.dumps({"prompt": f"p{i}", "response": "r"}), encoding="utf-8"
            )
        # 直接传 max_entries 参数（环境变量的解析口径在测试其他用例覆盖）
        added = build_semantic_index_from_cache_dir(str(tmp_path), max_entries=3)
        assert added == 3
        # 同文件重复扫描：upsert 幂等（键唯一），条目数不增长
        added2 = build_semantic_index_from_cache_dir(str(tmp_path), max_entries=3)
        assert get_semantic_cache_stats()["entries"] == 3
