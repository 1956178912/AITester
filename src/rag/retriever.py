"""
检索增强生成（RAG）模块：使用 ChromaDB 存储和检索历史测试用例与修复补丁。

在 Generator 和 Debugger 生成前，检索相似代码片段作为参考，
提升生成质量和修复效率。支持持久化存储，便于实验重复使用。
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# 延迟导入，避免未安装 chromadb 时整个项目无法启动
try:
    import chromadb

    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    chromadb = None


# 缓存配置常量
_DEFAULT_TTL_SECONDS = 3600  # 默认 TTL：1 小时
_DEFAULT_MAX_CASES = 1000  # 默认最大缓存条目数
# 自动清理节流间隔（秒）：TTL 默认 3600s，距上次全表扫描不足 60s 时跳过
# 重复扫描——过期清理最多延迟 60s 生效，对实际过期语义影响可忽略，
# 但避免每次 add_case/add_repair 都做一次 O(N) 元数据全表扫描（大缓存时
# 累积为 O(N^2) 成本）。容量满时仍每次扫描，保证驱逐语义不变。
_CLEANUP_INTERVAL_SECONDS = 60.0


class TestCaseRetriever:
    """
    基于 ChromaDB 的测试用例与修复补丁检索器。

    将历史成功测试用例和修复补丁向量化存储，在 Generator/Debugger 生成前
    检索最相似的历史案例作为参考，实现检索增强生成（RAG）。

    核心功能:
        - add_case: 添加成功测试用例到检索库（仅 passed=True 才会入库）
        - add_repair: 添加修复案例（原始代码 + 补丁 + 错误类型）
        - retrieve_test_cases: 检索相似测试用例（用于 Generator 参考风格）
        - retrieve_repairs: 检索相似修复方案（用于 Debugger 参考策略）
        - clear: 清空检索库（用于实验重置）
        - cleanup_expired: 清理过期缓存条目（TTL 机制）

    缓存策略:
        - TTL 过期机制：每个缓存条目记录添加时间，过期后自动清理
        - 容量限制：缓存达到最大条目数时，优先清理最旧的条目

    持久化:
        - 默认使用内存模式（进程重启后数据丢失）
        - 可通过 persist_path 参数指定持久化目录

    属性:
        collection_name: ChromaDB 集合名称，用于区分不同数据集。
        persist_path: 持久化路径（None 表示内存模式，重启后数据丢失）。
        client: ChromaDB 客户端实例。
        collection: ChromaDB 集合对象。
        ttl_seconds: TTL 过期时间（秒），默认 3600 秒（1 小时）。
        max_cases: 最大缓存条目数，默认 1000。

    使用示例:
        >>> retriever = TestCaseRetriever(persist_path="./rag_data")
        >>> retriever.add_case(
        ...     code="def add(a, b): return a + b",
        ...     test_code="def test_add(): assert add(2, 3) == 5",
        ...     passed=True,
        ... )
        >>> cases = retriever.retrieve_test_cases("def add(a, b): return a + b")
        >>> len(cases)
        1
    """

    # 防止 pytest 把本类误识别为测试类（类名以 Test 开头且带 __init__，
    # 否则 pytest 收集时会产生 PytestCollectionWarning）
    __test__ = False

    def __init__(
        self,
        collection_name: str = "aitester_cases",
        persist_path: str | None = None,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
        max_cases: int = _DEFAULT_MAX_CASES,
    ) -> None:
        """
        初始化检索器。

        Args:
            collection_name: ChromaDB 集合名称，用于区分不同数据集。
            persist_path: 持久化路径，None 时使用内存模式。
                         建议设置为项目目录下的 rag_data/ 以保证可复现性。
            ttl_seconds: TTL 过期时间（秒），默认 3600 秒（1 小时）。
            max_cases: 最大缓存条目数，默认 1000。
        """
        if not CHROMA_AVAILABLE:
            raise ImportError("chromadb 未安装，请执行: pip install chromadb")

        self.collection_name = collection_name
        self.persist_path = persist_path
        self.ttl_seconds = ttl_seconds
        self.max_cases = max_cases

        # 配置 ChromaDB 客户端（chromadb 1.x 现代 API）：
        # - persist_path 给定时用 PersistentClient 持久化到该目录
        # - 否则用 EphemeralClient 纯内存，进程结束即失效
        # 旧版 chromadb.Client(Settings(persist_directory=...)) 已弃用，且
        # Settings() 默认 persist_directory='./chroma'，"内存"分支实际会在 CWD
        # 落出持久目录；anonymized_telemetry 关闭避免后台遥测上报
        settings = chromadb.Settings(anonymized_telemetry=False)
        if persist_path:
            self.client = chromadb.PersistentClient(path=persist_path, settings=settings)
        else:
            self.client = chromadb.EphemeralClient(settings=settings)

        # 获取或创建集合，使用余弦相似度作为距离度量
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        # 记录上次全表清理时间（0.0 = 从未清理，保证首次 add 一定执行清理）
        self._last_cleanup_at = 0.0
        logger.info(
            "RAG 检索器已初始化，集合=%s，持久化路径=%s，TTL=%ds，最大容量=%d",
            collection_name,
            persist_path or "内存",
            ttl_seconds,
            max_cases,
        )

    def _add_timestamp_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """
        添加时间戳元数据（用于 TTL 过期机制）。

        Args:
            metadata: 原始元数据字典。

        Returns:
            添加了时间戳信息的元数据字典。
        """
        metadata = metadata.copy()
        metadata["_added_at"] = time.time()
        return metadata

    def _cleanup_expired_and_excess(self) -> None:
        """
        清理过期和超额的缓存条目。

        执行两步清理：
        1. 清理 TTL 过期的条目（当前时间 - 添加时间 > ttl_seconds）
        2. 如果条目数仍超过 max_cases，清理最旧的条目

        节流：未达容量上限时，距上次清理不足 _CLEANUP_INTERVAL_SECONDS
        （60s）则跳过全表扫描；容量满（需要驱逐）或首次调用时始终执行。
        """
        current_time = time.time()

        # 节流判断：容量未满 且 已清理过 且 距上次清理不足 60s → 跳过全表扫描。
        # 容量满（count >= max_cases）必须每次清理才能腾出空间；
        # 首次清理（_last_cleanup_at == 0.0）也始终执行（旧实例可能遗留过期条目）。
        count = self.collection.count()
        if (
            count < self.max_cases
            and self._last_cleanup_at != 0.0
            and current_time - self._last_cleanup_at < _CLEANUP_INTERVAL_SECONDS
        ):
            return

        # 步骤 1：获取所有条目，筛选出未过期的
        all_results = self.collection.get(include=["metadatas"])
        self._last_cleanup_at = current_time
        if not all_results["ids"]:
            return

        # 分离过期和未过期条目
        valid_ids = []
        expired_ids = []
        for doc_id, meta in zip(all_results["ids"], all_results["metadatas"], strict=False):
            added_at = meta.get("_added_at", 0)
            if current_time - added_at <= self.ttl_seconds:
                valid_ids.append(doc_id)
            else:
                expired_ids.append(doc_id)

        # 清理过期条目
        if expired_ids:
            self.collection.delete(ids=expired_ids)
            logger.debug("已清理 %d 个过期缓存条目", len(expired_ids))

        # 步骤 2：如果仍超容量，清理最旧的条目
        if len(valid_ids) > self.max_cases:
            # 获取所有有效条目的时间戳
            valid_results = self.collection.get(ids=valid_ids, include=["metadatas"])
            # 按添加时间排序，保留最新的 max_cases 个
            id_time_pairs = [
                (doc_id, meta.get("_added_at", 0))
                for doc_id, meta in zip(valid_results["ids"], valid_results["metadatas"], strict=False)
            ]
            id_time_pairs.sort(key=lambda x: x[1], reverse=True)  # 按时间降序
            remove_ids = [id for id, _ in id_time_pairs[self.max_cases :]]

            if remove_ids:
                self.collection.delete(ids=remove_ids)
                logger.debug("已清理 %d 个超额缓存条目", len(remove_ids))

    def add_case(
        self,
        code: str,
        test_code: str,
        passed: bool,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        添加一个成功测试用例到检索库。
        只有 passed=True 的测试用例才会被入库，确保检索到的案例都是高质量样本。
        入库前会自动清理过期和超额的缓存条目。

        Args:
            code: 被测代码原文。
            test_code: 成功的测试代码。
            passed: 是否通过测试（仅 True 才会入库）。
            metadata: 额外元数据（如函数名、覆盖率等）。
        """
        if not passed:
            return  # 只索引成功的测试用例

        # 自动清理过期和超额条目
        self._cleanup_expired_and_excess()

        # 检查是否已达到容量上限
        if self.collection.count() >= self.max_cases:
            logger.warning("缓存已达容量上限 (%d)，跳过添加", self.max_cases)
            return

        # 生成唯一 ID：使用代码 hash 避免重复入库

        doc_id = hashlib.md5(f"{code}|{test_code}".encode()).hexdigest()[:16]

        # 构建检索文档：将被测代码和测试代码拼接为检索文本
        document = f"def target_code:\n{code}\n\ndef test_code:\n{test_code}"

        # 准备元数据（添加时间戳用于 TTL 机制）
        meta = self._add_timestamp_metadata(metadata or {})
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
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        添加一个修复案例到检索库。
        用于 Debugger 在遇到相似错误时参考历史修复方案。
        入库前会自动清理过期和超额的缓存条目。

        Args:
            original_code: 原始有 bug 的代码。
            patch: 修复后的代码。
            error_category: 错误类型（syntax/runtime/assertion 等）。
            metadata: 额外元数据。
        """
        # 自动清理过期和超额条目
        self._cleanup_expired_and_excess()

        # 检查是否已达到容量上限
        if self.collection.count() >= self.max_cases:
            logger.warning("缓存已达容量上限 (%d)，跳过添加", self.max_cases)
            return

        # 生成唯一 ID：使用代码 hash 避免重复入库

        doc_id = hashlib.md5(f"{original_code}|{patch}".encode()).hexdigest()[:16]

        # 构建检索文档，包含错误类型和代码
        document = f"error_category: {error_category}\noriginal_code:\n{original_code}\npatch:\n{patch}"

        # 准备元数据（添加时间戳用于 TTL 机制）
        meta = self._add_timestamp_metadata(metadata or {})
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
    ) -> list[dict[str, Any]]:
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
            include=["documents", "metadatas", "distances"],
        )

        # ChromaDB 余弦空间：similarity = 1 - distance。
        # distance 不在 metadatas 里（此前 meta.get("distance") 恒为 0.0），
        # 必须从查询结果的 distances 字段取；缺失时（如 mock 返回值形状不同）
        # 宽松回退 0.0（相似度记 1.0，不影响排序，仅数值失真）。
        # 注意：distances 与 documents 同为双层嵌套（外层按 query_texts）
        distances_raw = results.get("distances")
        distances = distances_raw[0] if distances_raw else [0.0]
        cases = []
        for i, (_doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0], strict=False)):
            dist = distances[i] if i < len(distances) else 0.0
            cases.append(
                {
                    "test_code": meta.get("test_code", ""),
                    "similarity": round(1.0 - dist, 4),
                    "metadata": meta,
                }
            )
        return cases

    def retrieve_repairs(
        self,
        error_category: str,
        target_code: str,
        top_k: int = 2,
    ) -> list[dict[str, Any]]:
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

        # 构建检索查询文本：包含错误类型和代码上下文
        query_text = f"error_category: {error_category}\ntarget_code:\n{target_code}"
        results = self.collection.query(
            query_texts=[query_text],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
            where={"error_category": error_category},  # 过滤同类型错误
        )

        # 同 retrieve_test_cases：similarity 由余弦距离换算（1 - distance），
        # distance 不在 metadatas 里，需从查询结果的 distances 字段取；
        # distances 与 documents 同为双层嵌套（外层按 query_texts）
        distances_raw = results.get("distances")
        distances = distances_raw[0] if distances_raw else [0.0]
        repairs = []
        for i, (_doc, meta) in enumerate(zip(results["documents"][0], results["metadatas"][0], strict=False)):
            dist = distances[i] if i < len(distances) else 0.0
            repairs.append(
                {
                    "patch": meta.get("patch", ""),
                    "original_code": meta.get("original_code", ""),
                    "similarity": round(1.0 - dist, 4),
                    "metadata": meta,
                }
            )
        return repairs

    def cleanup_expired(self) -> int:
        """
        手动清理所有过期缓存条目。

        Returns:
            清理的过期条目数量。
        """
        current_time = time.time()

        all_results = self.collection.get(include=["metadatas"])
        self._last_cleanup_at = current_time
        if not all_results["ids"]:
            return 0

        expired_ids = []
        for doc_id, meta in zip(all_results["ids"], all_results["metadatas"], strict=False):
            added_at = meta.get("_added_at", 0)
            if current_time - added_at > self.ttl_seconds:
                expired_ids.append(doc_id)

        if expired_ids:
            self.collection.delete(ids=expired_ids)
            logger.info("已清理 %d 个过期缓存条目", len(expired_ids))

        return len(expired_ids)

    def evaluate_retrieval(
        self,
        queries: list[dict[str, str]],
        top_k: int = 5,
    ) -> dict[str, Any]:
        """计算检索质量指标（P1：RAG 检索质量评估）。

        针对一批"查询 → 期望命中"的标注对，在检索库上跑 retrieve_test_cases
        并统计两个常用 IR 指标：
        - hit_rate: Hit Rate@k，期望文档出现在前 k 个结果中的查询占比；
        - mrr: Mean Reciprocal Rank，首个命中位置倒数的平均值。

        Args:
            queries: 标注查询列表，每项为 {"query": 查询文本, "expected_id":
                期望命中的文档 ID（即 add_case 时的 doc_id，可用
                md5(f"{code}|{test_code}")[:16] 计算）}。
            top_k: 评估时取前 k 个结果。

        Returns:
            {"num_queries": int, "hits": int, "hit_rate": float, "mrr": float}
            （无查询时 hit_rate/mrr 均为 0.0）。
        """
        num_queries = len(queries)
        if num_queries == 0:
            return {"num_queries": 0, "hits": 0, "hit_rate": 0.0, "mrr": 0.0}

        hits = 0
        reciprocal_rank_sum = 0.0
        for item in queries:
            expected_id = item.get("expected_id", "")
            if not expected_id:
                continue
            cases = self.retrieve_test_cases(item.get("query", ""), top_k=top_k)
            # 检索结果不含 doc_id，按 (code, test_code) 组合反查期望文档：
            # 期望文档的文档 ID 由 md5(code|test_code)[:16] 决定，
            # 这里直接从命中的 metadata 里比对 original_code/test_code 指纹
            expected_fingerprint = expected_id
            rank = None
            for i, case in enumerate(cases):
                meta = case.get("metadata", {}) or {}
                # 期望文档 ID 与 add_case 入库时的 doc_id 同构（md5 指纹前 16 位）
                fingerprint = hashlib.md5(
                    f"{meta.get('code', '')}|{meta.get('test_code', '')}".encode()
                ).hexdigest()[:16]
                if fingerprint == expected_fingerprint:
                    rank = i + 1
                    break
            if rank is not None:
                hits += 1
                reciprocal_rank_sum += 1.0 / rank

        return {
            "num_queries": num_queries,
            "hits": hits,
            "hit_rate": round(hits / num_queries, 4),
            "mrr": round(reciprocal_rank_sum / num_queries, 4),
        }

    def clear(self) -> None:
        """清空检索库（用于实验重置）。"""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("RAG 检索库已清空")
