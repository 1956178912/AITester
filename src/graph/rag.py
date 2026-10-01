"""
RAG 检索器单例、检索质量指标辅助，与 20. 关键词兜底检索（降级路径）。

从 workflow.py 拆分而来（代码可维护性优化）：承载 TestCaseRetriever 的单例
初始化（双重检查锁定）、初始化失败短路标志，以及单次检索质量指标的构建。
节点函数通过 `from .rag import ...` 复用，避免重复初始化 ChromaDB 客户端。

20. 关键词兜底检索（外部参照：LeanKG 三层检索回退链——精确匹配 → 模糊匹配
→ 语义嵌入/关键词回退；任一高级路径失败时降级到仍可行的另一路径，返回
归一化分数）：ChromaDB 向量检索器不可用（未安装 / 初始化失败 / 检索异常）
或结果空时，`retriever_or_keyword_fallback()` 退回**纯词袋关键词检索**
（对 src/cache/ 的缓存条目 prompt 文本与 rag_data/ 的失败案例 JSON 做
token 重叠打分，零外部依赖，确定性可复现）。该兜底让"检索增强"在
向量后端缺失时不再是全有或全无——至少给出基于关键词的相似案例线索。
"""

from __future__ import annotations

import glob
import json
import logging
import os
import os as _os
import re
import threading
from collections.abc import Callable
from typing import Any

from config import RAG_COLLECTION_NAME, RAG_PERSIST_PATH, RAG_TTL_SECONDS

logger = logging.getLogger(__name__)

# 可选导入 RAG 检索器（未安装 chromadb 时优雅降级，不影响主流程）
# 使用 try-import 而非 top-level import，避免 chromadb 未安装时整个项目无法启动；
# 保持原"导入失败即置 None 同名模块属性"的模式，测试 patch 路径
# （src.graph.rag.TestCaseRetriever / workflow_module.TestCaseRetriever）不变；
# 预先声明为 Any 变量，mypy 按运行期值处理（不报 Cannot assign to a type），
# 类型注解用字符串前向引用（TestCaseRetriever，惰性求值）
TestCaseRetriever: Any = None
try:
    from src.rag.retriever import TestCaseRetriever as _TestCaseRetriever

    TestCaseRetriever = _TestCaseRetriever
    RAG_MODULE_AVAILABLE = True
except ImportError:
    RAG_MODULE_AVAILABLE = False
    logger.info("RAG 模块未就绪（chromadb 未安装），将跳过检索增强")

# ─── RAG 检索器单例 ────────────────────────────────────────────────────────────
# _rag_retriever 模块级缓存：避免每次节点调用都重新初始化 ChromaDB 客户端
# ChromaDB 客户端初始化涉及模型加载和向量存储打开，耗时 2-6 秒
# 单例化后整个工作流执行期间只初始化一次
# （from __future__ import annotations 下注解惰性求值，chromadb 缺失时
#  模块期不会触发 TestCaseRetriever 解析；运行时经 TestCaseRetriever 取值）
_rag_retriever: Any = None
# 线程锁：保护单例初始化的双重检查锁定，确保多线程环境下的安全性
_rag_lock = threading.Lock()
# RAG 初始化失败标志：一旦构造抛异常即置位，后续节点调用直接返回 None 不再重试
# （ChromaDB 持久目录损坏/模型下载失败属持续性故障，重复初始化只浪费 2-6s/次）
_rag_init_failed = False


def get_rag_retriever() -> Any:
    """
    获取 RAG 检索器单例实例（线程安全版本）。

    使用双重检查锁定模式（Double-Checked Locking）：
    - 第一次检查（无锁）：若已初始化直接返回，避免后续调用的锁开销
    - 加锁后第二次检查：防止多线程并发时多次初始化

    保证 ChromaDB 客户端在整个工作流执行期间只初始化一次，
    避免每个节点都创建新实例导致的 2-6 秒重复初始化开销。

    Returns:
        TestCaseRetriever 实例。若 RAG 模块不可用则返回 None。
    """
    global _rag_retriever, _rag_init_failed
    # 初始化曾失败（持久目录损坏、模型下载失败等持续性故障）：直接返回 None，
    # 不再每节点调用都重付 2-6s 初始化 + 重复 warning。此前 except 分支把
    # _rag_retriever 置回 None 是 no-op（变量本就是 None），快路径检查失效，
    # 每个 generator/executor/debugger 节点都会重复尝试初始化
    if _rag_init_failed:
        return None
    # 第一次检查：无锁快速路径，已初始化时直接返回
    if _rag_retriever is not None:
        return _rag_retriever
    # 加锁进行二次检查和初始化
    with _rag_lock:
        # 第二次检查：防止多线程并发时多次初始化
        # 经 TestCaseRetriever 实例化（测试 patch 该属性即可注入 mock 构造器）
        if _rag_retriever is None and RAG_MODULE_AVAILABLE and TestCaseRetriever is not None:
            try:
                # P1 优化：此前总是无参构造（内存模式，进程重启数据全丢）。
                # 现由 config 控制持久化路径（默认项目下 rag_data/）与 TTL，
                # 保证跨实验运行的历史用例/修复案例可复用；RAG_PERSIST_PATH
                # 设为空字符串可回退内存模式。
                _rag_retriever = TestCaseRetriever(
                    collection_name=RAG_COLLECTION_NAME,
                    persist_path=RAG_PERSIST_PATH or None,
                    ttl_seconds=RAG_TTL_SECONDS,
                )
                logger.info("RAG 检索器单例已初始化（持久化=%s）", RAG_PERSIST_PATH or "内存模式")
            except Exception as e:
                logger.warning("RAG 检索器初始化失败，将跳过 RAG 增强: %s", e)
                # 持续性故障标志：后续 get_rag_retriever() 直接返回 None 不再重试。
                # 此前此处仅把 _rag_retriever 置 None（本就是 None，no-op），
                # 每个 generator/executor/debugger 节点都会重复尝试初始化
                _rag_init_failed = True
    return _rag_retriever


def _build_rag_stat(rag_refs: list | None, kind: str) -> dict[str, Any] | None:
    """构建一次 RAG 检索的质量指标记录（P1：消融实验单独报告检索质量）。

    容错：参考案例元素可能是 dict（正常）或 str（测试 mock），
    相似度缺失时记 0.0，不中断主流程。

    Args:
        rag_refs: 一次检索返回的参考案例列表（None 表示未启用 RAG）。
        kind: 检索类型（"test_cases" 或 "repairs"）。

    Returns:
        指标字典；未检索（rag_refs 为 None）时返回 None。
    """
    if rag_refs is None:
        return None
    sim_values = [float(c.get("similarity", 0.0) or 0.0) for c in rag_refs if isinstance(c, dict)]
    return {
        "kind": kind,
        "results": len(rag_refs),
        "max_similarity": max(sim_values) if sim_values else None,
        "avg_similarity": (sum(sim_values) / len(sim_values)) if sim_values else None,
    }


def _build_rag_stat_with_relevance(
    rag_refs: list | None,
    kind: str,
    relevance_filtered: int = 0,
    relevance_filter_rate: float = 0.0,
) -> dict[str, Any] | None:
    """P2 RAG 相关性观测：在 _build_rag_stat 基础上追加过滤比例指标。

    2026-10 改进（A/B 阴性结果驱动）：RAG 命中率 100% 但成功率 0pp，
    根因是"检索到但没用上"。本函数把"被相关性阈值过滤掉的案例数/比例"
    写进 rag_stats，让实验报告能分析"高命中率中有多少是低相关"。
    开关关闭时 relevance_filtered/relevance_filter_rate 均为 0，指标与
    _build_rag_stat 逐字段一致（历史口径零变化）。
    """
    base = _build_rag_stat(rag_refs, kind)
    if base is None:
        return None
    base["relevance_filtered"] = relevance_filtered
    base["relevance_filter_rate"] = relevance_filter_rate
    return base


def rag_guarded(
    op_name: str,
    action: Callable[[Any], None],
    *,
    enabled: bool,
    module_available: bool,
    retriever_cls: Any,
    get_retriever: Callable[[], Any],
) -> bool:
    """RAG 降级守卫：前置条件满足且检索器可用时执行 action(retriever)（P1 重构）。

    依赖注入式设计（关键点）：调用方把「RAG 是否启用 / 模块是否可用 / 检索器
    类 / 取实例函数」作为参数传入，而非在 rag.py 内部直接读模块全局。
    这样历史 patch 路径（`src.graph.nodes.ENABLE_RAG`、`src.graph.nodes.
    get_rag_retriever`、`src.graph.nodes.RAG_MODULE_AVAILABLE` 等）继续有效，
    测试 mock 行为不漂移。

    统一 nodes.py 中 4 处同构的「条件判断 + get_rag_retriever + try/except 降级」
    模板。未来调整 RAG 降级策略（失败计数、熔断等）只改本函数。

    Args:
        op_name: 操作标识（如 "retrieve_test_cases"），用于日志定位。
        action: 无返回值的回调，接收已就绪的检索器实例。
        enabled: RAG 开关（来自 config.ENABLE_RAG）。
        module_available: RAG 模块是否可用（来自 rag.RAG_MODULE_AVAILABLE）。
        retriever_cls: 检索器类（None 表示不可用，来自 rag.TestCaseRetriever）。
        get_retriever: 取检索器单例的函数（来自 rag.get_rag_retriever）。

    Returns:
        True 表示 action 已被执行（含 action 自身正常返回）；False 表示被跳过。
    """
    if not (enabled and module_available and retriever_cls is not None):
        return False
    retriever = get_retriever()
    if retriever is None:
        return False
    try:
        action(retriever)
    except Exception as e:
        logger.warning("RAG %s 失败，跳过: %s", op_name, e)
    return True


# ─── P2 RAG 相关性评分 + 条件注入（2026-10 改进，A/B 阴性结果驱动）────────────
# 背景：RAG A/B 显示检索命中率 100% 但成功率 0pp、token +40.7%——"检索到了
# 但没用上"。根因：retrieve_repairs 的 where 过滤只保证同类目非空即返回，
# 无相关性阈值；注入侧无条件拼接，低相关案例反增噪声。本层提供两个默认关
# 开关的增强能力（保守口径：未启用时与历史逐字节一致）：
#   1. RAG_RELEVANCE_THRESHOLD_ENABLE=true + RAG_RELEVANCE_THRESHOLD=0.7：
#      对检索结果按 similarity 过滤，低于阈值的案例不注入 prompt，并记录
#      被过滤比例（"高命中率中低相关占比"观测）；
#   2. RAG_CONDITIONAL_ENABLE=true：按错误类型条件注入——仅当检索到与
#      当前 error_category 匹配的案例时才注入（检索器侧 where 过滤已保证
#      同类目，本开关在注入侧做二次门控：零结果时明确不注入，避免空
#      案例占位）。

_RAG_RELEVANCE_THRESHOLD_ENABLE_ENV = "RAG_RELEVANCE_THRESHOLD_ENABLE"
_RAG_RELEVANCE_THRESHOLD_ENV = "RAG_RELEVANCE_THRESHOLD"
_RAG_CONDITIONAL_ENABLE_ENV = "RAG_CONDITIONAL_ENABLE"


def rag_relevance_threshold_enabled() -> bool:
    """P2 RAG 相关性阈值过滤开关（默认 false，历史口径零变化）。"""
    return _os.getenv(_RAG_RELEVANCE_THRESHOLD_ENABLE_ENV, "false").lower() == "true"


def rag_relevance_threshold() -> float:
    """P2 RAG 相关性阈值（默认 0.7，similarity = 1 - cosine_distance）。"""
    raw = _os.getenv(_RAG_RELEVANCE_THRESHOLD_ENV, "")
    try:
        v = float(raw)
        return max(0.0, min(v, 1.0))
    except ValueError:
        return 0.7


def rag_conditional_enabled() -> bool:
    """P2 RAG 条件注入开关（默认 false，历史口径零变化）。

    启用后：检索结果为空时明确不注入（保守降级）；非空时按错误类型
    门控（where 过滤已保证同类目，本开关仅在注入侧做二次确认，避免
    跨类目案例被误注入）。
    """
    return _os.getenv(_RAG_CONDITIONAL_ENABLE_ENV, "false").lower() == "true"


def filter_by_relevance(
    refs: list[dict[str, Any]] | None,
    threshold: float | None = None,
) -> tuple[list[dict[str, Any]], int, float]:
    """按 similarity 过滤 RAG 检索结果（纯函数，零 LLM 成本）。

    开关关闭（rag_relevance_threshold_enabled()=False）时直接原样返回，
    历史口径零变化；开启时过滤 similarity < threshold 的案例，并返回
    被过滤数量与过滤比例（供实验分析"高命中率中低相关占比"消费）。

    Args:
        refs: RAG 检索结果列表（每项含 similarity 字段）。
        threshold: 相关性阈值（None 时读 RAG_RELEVANCE_THRESHOLD，默认 0.7）。

    Returns:
        (filtered_refs, filtered_count, filter_rate_pct)：
        - filtered_refs：过滤后保留的案例列表（similarity >= threshold）；
        - filtered_count：被过滤掉的案例数；
        - filter_rate_pct：被过滤比例（0.0 = 无案例被过滤）。
    """
    if refs is None:
        # 2026-10-01 全面审查 P2 修复：mypy 错误——此前返回 refs（None）但签名
        # 声明 tuple[list[dict[str, Any]], int, float]。调用点 nodes.py:505/507、
        # 1176/1178 在调用前均 if refs: 兜底，None 输入永不到达此处（dead branch），
        # 但类型标注与返回值不符。现返回 ([], 0, 0.0) 与签名一致（语义等价：
        # "无案例"= 空列表）。
        return [], 0, 0.0
    if not rag_relevance_threshold_enabled():
        return refs, 0, 0.0
    if threshold is None:
        threshold = rag_relevance_threshold()
    kept = [r for r in refs if isinstance(r, dict) and float(r.get("similarity", 0.0) or 0.0) >= threshold]
    filtered_count = len(refs) - len(kept)
    filter_rate = round(filtered_count / len(refs) * 100, 2) if refs else 0.0
    if filtered_count:
        logger.info(
            "P2 RAG 相关性过滤：阈值=%.2f，保留 %d / 过滤 %d（%.1f%%）",
            threshold,
            len(kept),
            filtered_count,
            filter_rate,
        )
    return kept, filtered_count, filter_rate


def should_inject_refs(
    refs: list[dict[str, Any]] | None,
    error_category: str | None = None,
) -> bool:
    """P2 RAG 条件注入门控（纯函数，零 LLM 成本）。

    开关关闭（rag_conditional_enabled()=False）时恒返回 True（历史口径：
    有案例即注入，零变化）；开启时：
    - refs 为空 / None → False（不注入，避免空案例占位）；
    - error_category 提供时，确认至少一个案例的 error_category 匹配
      （where 过滤已保证同类目，此为二次确认）→ 不匹配则不注入；
    - 其余情况 → True（注入）。
    """
    if not rag_conditional_enabled():
        return True
    if not refs:
        return False
    if error_category:
        matched = any(
            isinstance(r, dict)
            and str(r.get("metadata", {}).get("error_category", "")).lower() == str(error_category).lower()
            for r in refs
        )
        if not matched:
            logger.info("P2 RAG 条件注入：error_category=%s 无匹配案例，跳过注入", error_category)
            return False
    return True


# ─── 20. 关键词兜底检索（LeanKG 三层回退链最底层：词袋打分）────────────────
# 设计约束（保守，零行为变化默认关闭）：
# - 开关 RAG_KEYWORD_FALLBACK_ENABLE 默认 false：关闭时本模块所有函数
#   直接返回空（调用方保持历史"检索器不可用即跳过 RAG 增强"口径）；
# - 开启后仅作为**兜底层**：先尝试 ChromaDB 向量检索，不可用/异常/空结果
#   时才退回关键词打分（LeanKG 口径：任一路径失败，检索器降级到仍可行的
#   另一路径，返回归一化分数）；
# - 关键词材料源（两处，均项目内既有产物，零新依赖）：
#   1. src/cache/*.json 的 prompt 文本（LLM 文件缓存条目，含历史任务文本）；
#   2. rag_data/*.json 失败案例（RAG 持久化目录，JSON 列表/对象扁平化）；
# - 打分：分词（英文 \w+ 小写 + 中文按单字——无外部分词依赖，保守口径）
#   后做 token 重叠度（query tokens 命中文档 tokens 的比例），除以
#   max(1, len(query_tokens)) 归一到 [0, 1]，与向量检索的 similarity 口径
#   对齐（下游 _build_rag_stat 直接消费）；
# - 结果上限（RAG_KEYWORD_FALLBACK_MAX_RESULTS，默认 5，与向量检索 top-k 同
#   量级）；空材料源 / 全部 0 分时返回空列表（调用方按"无参考案例"处理）。
_RAG_KEYWORD_FALLBACK_ENV = "RAG_KEYWORD_FALLBACK_ENABLE"
_RAG_KEYWORD_FALLBACK_MAX_RESULTS_ENV = "RAG_KEYWORD_FALLBACK_MAX_RESULTS"


def _keyword_fallback_enabled() -> bool:
    """关键词兜底开关（RAG_KEYWORD_FALLBACK_ENABLE，默认 false 历史口径）。"""
    return os.getenv(_RAG_KEYWORD_FALLBACK_ENV, "false").lower() in ("true", "1", "on")


def _keyword_fallback_max_results() -> int:
    """关键词兜底结果数上限（RAG_KEYWORD_FALLBACK_MAX_RESULTS，默认 5）。"""
    try:
        n = int(os.getenv(_RAG_KEYWORD_FALLBACK_MAX_RESULTS_ENV, "5"))
    except ValueError:
        n = 5
    return max(1, min(n, 100))


def _tokenize(text: str) -> set[str]:
    r"""轻量分词（零外部依赖保守口径）：英文 \w+ 小写 + 中文单字。"""
    tokens: set[str] = set()
    for m in re.findall(r"[a-z0-9_]+", text.lower()):
        tokens.add(m)
    for ch in re.findall(r"[\u4e00-\u9fff]", text):
        tokens.add(ch)
    return tokens


def _iter_candidate_docs() -> list[tuple[str, str, str]]:
    """枚举关键词材料源（cache prompt + rag_data 案例文本）。

    返回:
        (source, doc_id, text) 三元组列表；source ∈ {"cache", "rag_data"}。
        读取失败（损坏 JSON / 目录缺失）静默跳过（兜底层不阻断主流程）。
    """
    docs: list[tuple[str, str, str]] = []
    # 1. LLM 文件缓存条目（prompt 文本作参考——历史任务描述与修复指令）
    cache_dir = os.getenv("AITESTER_LLM_CACHE_DIR", "")
    if not cache_dir:
        # 与 llm_client._LLM_CACHE_DIR_DEFAULT 同口径（src/cache）
        cache_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"))
    for f in sorted(glob.glob(os.path.join(cache_dir, "*.json")))[-200:]:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            text = f"{data.get('prompt', '')}\n{data.get('response', '')}"
            if text.strip():
                docs.append(("cache", os.path.basename(f), text))
        except (OSError, json.JSONDecodeError, AttributeError, TypeError):
            continue
    # 2. rag_data 持久化案例（JSON 列表 / 对象扁平化文本）
    # 2026-10-02 审查修复：RAG_PERSIST_PATH 为空时此前仍执行
    # `glob(os.path.join("", "*.json"))` = `glob("*.json")`——在**当前工作
    # 目录**误扫一切 JSON（如 coverage.json / benchmark 结果），既污染关键词
    # 兜底材料源，也可能把无关大文件读进 prompt。空目录时直接跳过本段。
    rag_dir = RAG_PERSIST_PATH if isinstance(RAG_PERSIST_PATH, str) and RAG_PERSIST_PATH else ""
    for f in sorted(glob.glob(os.path.join(rag_dir, "*.json")))[:200] if rag_dir else []:
        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            text = json.dumps(data, ensure_ascii=False)[:8000]
            if text.strip():
                docs.append(("rag_data", os.path.basename(f), text))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
    return docs


def keyword_similarity(query: str, doc_text: str) -> float:
    """token 重叠度打分（归一化到 [0, 1]，与向量 similarity 同口径）。

    保守口径：query 空 / 分词为空 → 0.0；命中数 / query token 数。

    Args:
        query: 查询文本（任务描述 / 错误摘要）。
        doc_text: 候选文档文本。

    Returns:
        归一化相似度（0.0 = 零重叠；1.0 = query tokens 全部出现于文档）。
    """
    q_tokens = _tokenize(query)
    if not q_tokens:
        return 0.0
    d_tokens = _tokenize(doc_text)
    return len(q_tokens & d_tokens) / max(1, len(q_tokens))


def keyword_fallback_search(
    query: str,
    max_results: int | None = None,
    *,
    sources: list[tuple[str, str, str]] | None = None,
) -> list[dict[str, Any]]:
    """20. 关键词兜底检索（LeanKG 回退链底层）。

    Args:
        query: 查询文本。
        max_results: 结果数上限（None 时读 RAG_KEYWORD_FALLBACK_MAX_RESULTS）。
        sources: 候选文档源（测试注入；None 时枚举 cache + rag_data 材料源）。

    Returns:
        [{"source": ..., "doc_id": ..., "similarity": 归一化分数, "text": 截断文本}]
        按相似度降序，零分条目不返回；材料源为空 / 开关关闭时返回 []。
    """
    if not _keyword_fallback_enabled():
        return []
    if not query or not query.strip():
        return []
    limit = max_results if max_results is not None else _keyword_fallback_max_results()
    docs = sources if sources is not None else _iter_candidate_docs()
    scored: list[dict[str, Any]] = []
    for source, doc_id, text in docs:
        sim = keyword_similarity(query, text)
        if sim > 0.0:
            scored.append(
                {
                    "source": source,
                    "doc_id": doc_id,
                    "similarity": round(sim, 4),
                    "text": text[:1200],
                }
            )
    scored.sort(key=lambda d: d["similarity"], reverse=True)
    top = scored[:limit]
    global _keyword_fallback_last_results
    _keyword_fallback_last_results = top
    return top


# 观测层：最近一次关键词兜底检索结果（retriever_or_keyword_fallback 回填）
_keyword_fallback_last_results: list[dict[str, Any]] = []


def keyword_fallback_result_count() -> int:
    """观测层：关键词兜底最近一次检索的结果数（供 workflow stats 报告）。

    保守实现：仅统计显式调用方（retriever_or_keyword_fallback）回填的
    最近一次结果集；无调用记录时返回 0（不触发目录扫描，零副作用）。
    """
    return len(_keyword_fallback_last_results or [])


def retriever_or_keyword_fallback(
    op_name: str,
    action: Callable[[Any], None],
    *,
    enabled: bool,
    module_available: bool,
    retriever_cls: Any,
    get_retriever: Callable[[], Any],
    keyword_query: str = "",
) -> tuple[bool, bool]:
    """20. LeanKG 三层回退链入口：向量检索器可用走向量；不可用/异常/空结果
    时（开关 RAG_KEYWORD_FALLBACK_ENABLE=true）退回关键词兜底。

    与 rag_guarded 的关系（历史口径保护）：`rag_guarded` 保持不变（其 4 个
    既有调用点的测试 patch 路径不受影响）；本函数是**新增**的降级入口，
    供后续批次把 nodes.py 的 RAG 调用逐步切到"向量→关键词"双层守卫。
    当前默认（关键词开关关）时行为与 rag_guarded 完全等价。

    Args:
        op_name: 操作标识（如 "retrieve_test_cases"）。
        action: 向量检索回调（接收已就绪检索器，无返回值）。
        enabled: RAG 开关（config.ENABLE_RAG）。
        module_available: RAG 模块是否可用。
        retriever_cls: 检索器类（None 表示不可用）。
        get_retriever: 取检索器单例函数。
        keyword_query: 关键词兜底的查询文本（向量检索空结果/不可用且开关
            开启时，经 keyword_fallback_search 检索 rag_data/cache 材料源；
            结果经 logger 记录并写入观测层，**不替换** action 的向量结果——
            双层守卫的"结果合并"策略由调用方按 op_name 自行消费，本函数
            保持保守：仅在向量侧零产出时记录关键词候选，不改变 action
            回调契约（不向 action 注入关键词结果，避免 prompt 混层）。

    Returns:
        (vector_used, fallback_used) 二元组：
        - vector_used=True：action 经向量检索器成功执行（历史口径）；
        - fallback_used=True：向量侧不可用/空，关键词兜底开关开启且检索到
          候选（日志记录 + 观测层可查）；
        全 False = 两层均未产出（历史"跳过 RAG 增强"口径）。
    """
    vector_used = False
    if enabled and module_available and retriever_cls is not None:
        retriever = get_retriever()
        if retriever is not None:
            try:
                action(retriever)
                vector_used = True
            except Exception as e:
                logger.warning("RAG %s 向量检索失败，尝试关键词兜底: %s", op_name, e)
    if not vector_used and _keyword_fallback_enabled() and keyword_query:
        results = keyword_fallback_search(keyword_query)
        if results:
            logger.info("20. RAG 关键词兜底命中 %d 条候选（op=%s）", len(results), op_name)
            return vector_used, True
    return vector_used, False
