"""
检索增强生成（RAG）模块：使用 ChromaDB 存储和检索历史测试用例与修复补丁。

在 Generator 和 Debugger 生成前，检索相似代码片段作为参考，
提升生成质量和修复效率。支持持久化存储，便于实验重复使用。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 延迟导入，避免未安装 chromadb 时整个项目无法启动
try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None
    Settings = None


class TestCaseRetriever:
    """
    基于 ChromaDB 的测试用例与修复补丁检索器。

    将历史成功测试用例和修复补丁向量化存储，在 Generator/Debugger 生成前
    检索最相似的历史案例作为参考，实现检索增强生成（RAG）。

    属性:
        collection_name: ChromaDB 集合名称，用于区分不同数据集。
        persist_path: 持久化路径（None 表示内存模式，重启后数据丢失）。
        client: ChromaDB 客户端实例。
        collection: ChromaDB 集合对象。
    """

    def __init__(
        self,
        collection_name: str = "aitester_cases",
        persist_path: Optional[str] = None,
    ) -> None:
        """
        初始化检索器。

        Args:
            collection_name: ChromaDB 集合名称，用于区分不同数据集。
            persist_path: 持久化路径，None 时使用内存模式。
                         建议设置为项目目录下的 rag_data/ 以保证可复现性。
        """
        if not CHROMA_AVAILABLE:
            raise ImportError("chromadb 未安装，请执行: pip install chromadb")

        self.collection_name = collection_name
        self.persist_path = persist_path

        # 配置 ChromaDB 客户端
        # persist_directory 使数据跨进程持久化，便于实验重复使用
        settings = Settings(persist_directory=persist_path) if persist_path else Settings()
        self.client = chromadb.Client(settings)

        # 获取或创建集合，使用余弦相似度作为距离度量
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("RAG 检索器已初始化，集合=%s，持久化路径=%s",
                     collection_name, persist_path or "内存")

    def add_case(
        self,
        code: str,
        test_code: str,
        passed: bool,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        添加一个成功测试用例到检索库。
        只有 passed=True 的测试用例才会被入库，确保检索到的案例都是高质量样本。

        Args:
            code: 被测代码原文。
            test_code: 成功的测试代码。
            passed: 是否通过测试（仅 True 才会入库）。
            metadata: 额外元数据（如函数名、覆盖率等）。
        """
        if not passed:
            return  # 只索引成功的测试用例

        # 生成唯一 ID：使用代码 hash 避免重复入库
        import hashlib
        doc_id = hashlib.md5(f"{code}|{test_code}".encode()).hexdigest()[:16]

        # 构建检索文档：将被测代码和测试代码拼接为检索文本
        document = f"def target_code:\n{code}\n\ndef test_code:\n{test_code}"

        # 准备元数据
        meta = metadata or {}
        meta["code"] = code
        meta["test_code"] = test_code
        meta["passed"] = passed

        # 批量上载（ChromaDB 自动调用嵌入模型）
        self.collection.upsert(
            documents=[document],
            metadatas=[meta],
            ids=[doc_id],
        )
        logger.debug("已入库测试用例: %s", doc_id)

    def add_repair(
        self,
        original_code: str,
        patch: str,
        error_category: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        添加一个修复案例到检索库。
        用于 Debugger 在遇到相似错误时参考历史修复方案。

        Args:
            original_code: 原始有 bug 的代码。
            patch: 修复后的代码。
            error_category: 错误类型（syntax/runtime/assertion 等）。
            metadata: 额外元数据。
        """
        import hashlib
        doc_id = hashlib.md5(f"{original_code}|{patch}".encode()).hexdigest()[:16]

        # 构建检索文档，包含错误类型和代码
        document = (
            f"error_category: {error_category}\n"
            f"original_code:\n{original_code}\n"
            f"patch:\n{patch}"
        )

        meta = metadata or {}
        meta["error_category"] = error_category
        meta["original_code"] = original_code
        meta["patch"] = patch

        self.collection.upsert(
            documents=[document],
            metadatas=[meta],
            ids=[doc_id],
        )
        logger.debug("已入库修复案例: %s (类型=%s)", doc_id, error_category)

    def retrieve_test_cases(
        self,
        target_code: str,
        top_k: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        检索与被测代码最相似的历史测试用例。
        ChromaDB 使用余弦相似度进行向量检索。

        Args:
            target_code: 当前被测代码。
            top_k: 返回最相似的 K 个案例。

        Returns:
            相似案例列表，每项包含 test_code 和 metadata。
        """
        if self.collection.count() == 0:
            return []

        results = self.collection.query(
            query_texts=[target_code],
            n_results=top_k,
            include=["documents", "metadatas"],
        )

        cases = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            cases.append({
                "test_code": meta.get("test_code", ""),
                "similarity": meta.get("distance", 0.0),
                "metadata": meta,
            })
        return cases

    def retrieve_repairs(
        self,
        error_category: str,
        target_code: str,
        top_k: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        检索与当前错误类型和被测代码最相似的历史修复方案。
        通过 where 过滤器限定同类型错误，提高检索准确性。

        Args:
            error_category: 当前错误类型。
            target_code: 当前被测代码。
            top_k: 返回数量。

        Returns:
            相似修复方案列表，每项包含 patch 和 metadata。
        """
        if self.collection.count() == 0:
            return []

        # 构造查询文本，同时匹配错误类型和代码内容
        query_text = f"error_category: {error_category}\n{target_code}"

        # 构建检索查询文本：包含错误类型和代码上下文
        query_text = f"error_category: {error_category}\ntarget_code:\n{target_code}"
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k,
            include=["documents", "metadatas"],
            where={"error_category": error_category},  # 过滤同类型错误
        )

        repairs = []
        for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
            repairs.append({
                "patch": meta.get("patch", ""),
                "original_code": meta.get("original_code", ""),
                "similarity": meta.get("distance", 0.0),
                "metadata": meta,
            })
        return repairs

    def clear(self) -> None:
        """清空检索库（用于实验重置）。"""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("RAG 检索库已清空")
