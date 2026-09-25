"""
2.1 真实语义嵌入钩子（src/utils/embedding_utils.py）单元测试。

覆盖目标：
- cosine_similarity：numpy 余弦正确性、零向量、维度不一致、纯 Python 回退；
- embed_text：EMBEDDING_BACKEND=none 强制返回 None（词袋保守口径）；
- 空文本返回 None（避免空文本嵌入余弦误判高相似）；
- 后端可用时（chromadb 已装）返回真实向量，且 backend_name 标注来源；
- patch_semantic_similarity 的 semantic_source 字段传导（embedding/token_bag）。
"""

from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.utils import embedding_utils  # noqa: E402


class TestCosineSimilarity:
    """cosine_similarity 数值正确性与边界。"""

    def test_identical_vectors(self):
        from src.utils.embedding_utils import cosine_similarity

        assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == 1.0

    def test_orthogonal_vectors(self):
        from src.utils.embedding_utils import cosine_similarity

        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_zero_vector_returns_zero(self):
        from src.utils.embedding_utils import cosine_similarity

        assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0

    def test_mismatched_dims_returns_zero(self):
        from src.utils.embedding_utils import cosine_similarity

        assert cosine_similarity([1.0, 2.0], [1.0]) == 0.0

    def test_empty_lists_return_zero(self):
        from src.utils.embedding_utils import cosine_similarity

        assert cosine_similarity([], [1.0]) == 0.0
        assert cosine_similarity([1.0], []) == 0.0

    def test_pure_python_fallback_matches(self):
        """numpy 缺失时纯 Python 回退口径一致。"""
        a, b = [1.0, 2.0, 3.0], [4.0, 5.0, 6.0]

        def fake_import(name, *args, **kwargs):
            if name == "numpy" or name.startswith("numpy."):
                raise ImportError("numpy blocked for fallback test")
            import builtins

            return builtins.__import__(name, *args, **kwargs)

        import builtins

        import src.utils.embedding_utils as eu

        # 拦截 builtins.__import__（eu 内 `import numpy as np` 走此入口），
        # 仅屏蔽 numpy；finally 恢复，不影响后续用例
        orig = builtins.__import__
        builtins.__import__ = fake_import
        try:
            got = eu.cosine_similarity(a, b)
        finally:
            builtins.__import__ = orig
        # 期望值手算：dot=1*4+2*5+3*6=32; |a|=sqrt14, |b|=sqrt77; cos=32/sqrt(1078)
        expected = round(max(0.0, 32 / (14**0.5 * 77**0.5)), 4)
        assert got == expected


class TestEmbedText:
    """embed_text 后端选择与降级。"""

    def test_backend_none_forced_returns_none(self, monkeypatch):
        from src.utils.embedding_utils import embed_text

        monkeypatch.setenv("EMBEDDING_BACKEND", "none")
        assert embed_text("some code") is None

    def test_empty_text_returns_none(self, monkeypatch):
        """空文本/纯空白 → None（避免嵌入余弦误判高相似）。"""
        import src.utils.embedding_utils as eu

        eu._backend_initialized = False
        eu._backend_cache = {"instance": None, "name": None}
        monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
        assert eu.embed_text("") is None
        assert eu.embed_text("   ") is None

    def test_backend_name_reflects_available_backend(self, monkeypatch):
        """chromadb 已安装时 backend_name 应报告 chromadb（真实嵌入可用）。"""
        import src.utils.embedding_utils as eu

        eu._backend_initialized = False
        eu._backend_cache = {"instance": None, "name": None}
        monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
        try:
            import chromadb  # noqa: F401

            has_chromadb = True
        except ImportError:
            has_chromadb = False
        name = eu.backend_name()
        if has_chromadb:
            assert name == "chromadb"
        else:
            assert name is None


class TestSemanticSourceField:
    """patch_semantic_similarity 的 semantic_source 字段传导。"""

    def test_source_is_token_bag_when_no_embedding(self, monkeypatch):
        """强制 none 后端时，语义级来源标注为 token_bag（保守代理）。"""
        import experiments.contamination_check as cc
        import src.utils.embedding_utils as eu

        eu._backend_initialized = False
        eu._backend_cache = {"instance": None, "name": None}
        monkeypatch.setenv("EMBEDDING_BACKEND", "none")
        gen = "diff --git a/x.py b/x.py\n+def f(a):\n+    return a + 1\n"
        golden = "diff --git a/x.py b/x.py\n+def f(a):\n+    return a * 1\n"
        sims = cc.patch_semantic_similarity(gen, golden)
        assert sims["semantic_source"] == "token_bag"
        assert isinstance(sims["semantic"], float)

    def test_combined_risk_level_ignores_string_source(self, monkeypatch):
        """semantic_source（str）不参与阈值比较，不误报。"""
        import experiments.contamination_check as cc

        monkeypatch.setenv("EMBEDDING_BACKEND", "none")
        sims = {"jaccard": 0.3, "structural": 0.3, "semantic": 0.3, "semantic_source": "token_bag"}
        assert cc._combined_risk_level(sims) == "low"


def test_embedding_utils_importable():
    """embedding_utils 模块可导入且暴露核心函数。"""
    assert callable(embedding_utils.embed_text)
    assert callable(embedding_utils.cosine_similarity)
    assert callable(embedding_utils.backend_name)
