"""
GraphRAG：结构图索引 + 混合检索层（默认关）。

背景（P2 GraphRAG + 上下文压缩方向）：
    2026 年 GraphRAG（Microsoft）/ 知识图谱增强 RAG 的核心思想是：
    把"线性文本检索"升级为"结构化图索引 + 文本检索 + 实体关系"的混合
    检索，让 LLM 既看到相关文本片段，也看到代码间的调用/依赖关系，
    减少"只看局部、漏掉全局依赖"的修复失败。

    本模块在 `cross_file.py` 的跨文件依赖图（CrossFileDependency 边）之上
    构建**结构图索引 + 混合检索**（默认关，历史 RAG 纯文本检索口径不变）：
    - `GraphRAGIndex`：进程内结构图索引（邻接表 + 符号表 + 调用边），
      从 cross_file 依赖边 / 语言后端调用图构建；
    - `hybrid_retrieve`：混合检索（结构图子图 + 文本片段 + 符号锚点），
      把 LLM 相关子图（N 跳邻域）+ 相关文本片段一起注入 prompt，
      比纯文本 RAG 多"全局依赖视角"；
    - 零 LLM 成本（纯静态图遍历 + 文本定位），与 ADR-0004 零默认依赖口径一致。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `GRAPH_RAG_ENABLE=false`（默认）时，本模块零行为变化：
      工作流拓扑零改动，_debugger_node 不走 GraphRAG 混合检索路径；
    - 图索引纯内存（进程生命周期内），无外部数据库依赖（区别于
      GraphRAG 论文的图数据库方案，本模块是"轻量进程内图 + 文本混合"，
      避免 ADR-0004 默认引入外部依赖）；
    - 混合检索结果结构：{"subgraph": list[边], "text_snippets": list[str],
      "anchor_symbols": list[str], "hops": int, "center_symbol": str}；
    - 检索失败（索引为空 / 中心符号不存在）时保守降级（返回空结果，
      调用方走历史纯文本 RAG 路径，不阻断修复）。

使用方式（_debugger_node 集成）：
    from src.tools.graphrag import graph_rag_enabled, GraphRAGIndex, hybrid_retrieve

    if graph_rag_enabled():
        index = GraphRAGIndex.build_from_cross_file_deps(cross_file_deps)
        result = hybrid_retrieve(index, center_symbol="add", hops=2, top_k_snippets=5)
        # 把 result["subgraph"] + result["text_snippets"] 注入 debugger prompt
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)


def graph_rag_enabled() -> bool:
    """GraphRAG 开关（GRAPH_RAG_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("GRAPH_RAG_ENABLE", "false").lower() == "true"


def _graph_rag_max_hops() -> int:
    """混合检索最大跳数（GRAPH_RAG_MAX_HOPS，默认 2，范围 [1, 5]）。"""
    try:
        n = int(os.getenv("GRAPH_RAG_MAX_HOPS", "2"))
    except ValueError:
        n = 2
    return max(1, min(n, 5))


def _graph_rag_top_k_snippets() -> int:
    """混合检索文本片段数（GRAPH_RAG_TOP_K_SNIPPETS，默认 5，范围 [1, 20]）。"""
    try:
        n = int(os.getenv("GRAPH_RAG_TOP_K_SNIPPETS", "5"))
    except ValueError:
        n = 5
    return max(1, min(n, 20))


# ─── 图索引（邻接表 + 符号表，纯内存，无外部数据库）────────────────────────


class GraphRAGIndex:
    """进程内结构图索引（邻接表 + 符号表 + 调用边）。

    与 cross_file.CrossFileDependency 边格式对齐：
    每条边 (source_module, target_module, symbol, call_line, context)，
    邻接表按 source_module 分组（出边）+ 按 target_module 分组（入边），
    供 N 跳邻域遍历（混合检索的结构视角）。

    设计约束：
    - 纯内存（进程生命周期内），无外部数据库（ADR-0004 零默认依赖）；
    - 边去重（同 (source, target, symbol) 三元组只保留一条，call_line 取最小）；
    - 符号表 = 所有边涉及的 (target_module, symbol) 去重集合（检索锚点）。
    """

    def __init__(self) -> None:
        # 邻接表（出边 + 入边）：module -> set[(other_module, symbol)]
        self._out_edges: dict[str, set[tuple[str, str]]] = {}
        self._in_edges: dict[str, set[tuple[str, str]]] = {}
        # 符号表：(target_module, symbol) 集合（检索锚点）
        self._symbols: set[tuple[str, str]] = set()
        # 边详情（call_line / context，供 LLM 理解）
        self._edge_details: dict[tuple[str, str, str], dict[str, Any]] = {}
        # 模块源码（module_name -> source_text，供文本片段定位）
        self._module_sources: dict[str, str] = {}

    @classmethod
    def build_from_cross_file_deps(
        cls,
        cross_file_deps: list[dict[str, Any]],
        module_sources: dict[str, str] | None = None,
    ) -> GraphRAGIndex:
        """从 cross_file 依赖边列表（dict 格式，与 state["cross_file_deps"] 同 schema）构建图索引。

        Args:
            cross_file_deps: 依赖边列表（每项含 source_module / target_module /
                symbol / call_line / context 字段，与 asdict(CrossFileDependency) 同 schema）。
            module_sources: 模块名 → 源码文本（可选，供文本片段定位；None 时
                文本检索退化为"无片段"（仅结构子图 + 符号锚点））。

        Returns:
            GraphRAGIndex 实例（边去重、符号表已填充）。
        """
        index = cls()
        index._module_sources = module_sources or {}
        for dep in cross_file_deps or []:
            if not isinstance(dep, dict):
                continue
            source = str(dep.get("source_module", ""))
            target = str(dep.get("target_module", ""))
            symbol = str(dep.get("symbol", ""))
            call_line = int(dep.get("call_line", 0))
            context = str(dep.get("context", ""))
            if not source or not target or not symbol:
                continue
            edge_key = (source, target, symbol)
            # 出边：source -> (target, symbol)
            index._out_edges.setdefault(source, set()).add((target, symbol))
            # 入边：target -> (source, symbol)
            index._in_edges.setdefault(target, set()).add((source, symbol))
            # 符号表：(target_module, symbol)
            index._symbols.add((target, symbol))
            # 边详情（call_line 取最小，保守：同一三元组多次调用时保留最早调用行）
            existing = index._edge_details.get(edge_key)
            if existing is None or call_line < existing.get("call_line", 1 << 30):
                index._edge_details[edge_key] = {
                    "source_module": source,
                    "target_module": target,
                    "symbol": symbol,
                    "call_line": call_line,
                    "context": context,
                }
        return index

    @classmethod
    def build_from_call_graph(
        cls,
        call_edges: list[tuple[str, str]],
        module_sources: dict[str, str] | None = None,
    ) -> GraphRAGIndex:
        """从语言后端调用图（list[(caller, callee)]）构建图索引。

        调用边是"函数级"（caller_fn -> callee_fn），与 cross_file 的"模块级"
        不同。本方法把函数级调用边映射到模块级（caller_fn 所在模块 →
        callee_fn 所在模块，symbol = callee_fn），供 TypeScript / Go 等
        非 Python 后端的 GraphRAG 消费。

        Args:
            call_edges: 调用边列表（(caller_fn_name, callee_fn_name)）。
            module_sources: 模块名 → 源码文本（函数名 → 模块映射由调用方
                提供，经 module_sources 的键 + 函数定位启发式实现；
                None 时函数级边退化为"单模块内自环"（不跨模块））。

        Returns:
            GraphRAGIndex 实例（函数级调用边已映射到模块级）。
        """
        index = cls()
        index._module_sources = module_sources or {}
        # 函数名 → 模块映射（启发式：函数名出现在某模块源码里 → 该函数属于该模块）
        fn_module_map: dict[str, str] = {}
        for mod_name, mod_src in index._module_sources.items():
            for m in re.finditer(r"\b(function|const|class)\s+(\w+)", mod_src):
                fn = m.group(2)
                if fn not in fn_module_map:
                    fn_module_map[fn] = mod_name
        for caller_fn, callee_fn in call_edges or []:
            caller_mod = fn_module_map.get(caller_fn, caller_fn)
            callee_mod = fn_module_map.get(callee_fn, callee_fn)
            if caller_mod == callee_mod:
                # 同模块内调用：不跨模块，跳过（图索引只关心跨模块边）
                continue
            index._out_edges.setdefault(caller_mod, set()).add((callee_mod, callee_fn))
            index._in_edges.setdefault(callee_mod, set()).add((caller_mod, callee_fn))
            index._symbols.add((callee_mod, callee_fn))
            index._edge_details[(caller_mod, callee_mod, callee_fn)] = {
                "source_module": caller_mod,
                "target_module": callee_mod,
                "symbol": callee_fn,
                "call_line": 0,
                "context": f"{caller_fn}() calls {callee_fn}()",
            }
        return index

    def n_hop_subgraph(self, center_module: str, hops: int = 2) -> list[dict[str, Any]]:
        """从 center_module 出发的 N 跳邻域子图（BFS，含出边 + 入边）。

        Args:
            center_module: 中心模块名。
            hops: 最大跳数（默认 2，GRAPH_RAG_MAX_HOPS 钳制范围 [1,5]）。

        Returns:
            子图边列表（每项为 _edge_details 条目，含 source_module /
            target_module / symbol / call_line / context）。
        """
        visited: set[str] = {center_module}
        current_frontier: set[str] = {center_module}
        result_edges: list[tuple[str, str, str]] = []
        for _ in range(max(1, min(hops, _graph_rag_max_hops()))):
            next_frontier: set[str] = set()
            for mod in current_frontier:
                for other, _sym in self._out_edges.get(mod, set()):
                    if other not in visited:
                        next_frontier.add(other)
                    result_edges.append((mod, other, _sym))
                for other, _sym in self._in_edges.get(mod, set()):
                    if other not in visited:
                        next_frontier.add(other)
                    result_edges.append((other, mod, _sym))
            visited |= next_frontier
            current_frontier = next_frontier
            if not current_frontier:
                break
        # 去重 + 映射到 _edge_details
        seen: set[tuple[str, str, str]] = set()
        subgraph: list[dict[str, Any]] = []
        for edge_key in result_edges:
            if edge_key in seen:
                continue
            seen.add(edge_key)
            detail = self._edge_details.get(edge_key)
            if detail:
                subgraph.append(detail)
        return subgraph

    def find_symbol_anchor(self, symbol_name: str) -> list[tuple[str, str]]:
        """查找符号锚点（symbol_name 出现在哪些模块里）。"""
        return [(mod, sym) for (mod, sym) in self._symbols if sym == symbol_name]

    def find_text_snippets(self, query: str, top_k: int | None = None) -> list[str]:
        """在 module_sources 里检索 query 的文本片段（保守子串匹配，零 LLM 成本）。

        Args:
            query: 检索文本（如错误信息 / 函数名 / 变量名）。
            top_k: 最多返回的片段数（None 时读 GRAPH_RAG_TOP_K_SNIPPETS，
                默认 5）。

        Returns:
            文本片段列表（每片含上下文行，最多 top_k 个；module_sources
            为空 / 无匹配时返回空列表，保守降级）。
        """
        if not query or not self._module_sources:
            return []
        k = top_k if top_k is not None else _graph_rag_top_k_snippets()
        query_lower = query.lower()
        snippets: list[str] = []
        for mod_name, mod_src in self._module_sources.items():
            # 保守子串匹配（小写化，定位 query 出现的行）。
            # O35（P2 性能）：splitlines 提到循环外——此前**每次命中**都在
            # 命中分支内重跑一遍 `mod_src.splitlines()`，而外层迭代器本身
            # 也对同一字符串 splitlines，命中 k 次即多做 k 次全量分割
            # （O(行数²)），跨文件大模块 + 高 top_k 时开销明显。
            lines = mod_src.splitlines()
            lowered = [ln.lower() for ln in lines]
            for i, line_lowered in enumerate(lowered):
                if query_lower in line_lowered:
                    # 取 query 所在行 + 前后 2 行上下文
                    start = max(0, i - 2)
                    end = min(len(lines), i + 3)
                    context_block = "\n".join(lines[start:end])
                    snippets.append(f"[{mod_name}]:{i + 1}: {context_block}")
                    if len(snippets) >= k:
                        return snippets
        return snippets


def hybrid_retrieve(
    index: GraphRAGIndex,
    center_symbol: str | None = None,
    center_module: str | None = None,
    query_text: str | None = None,
    hops: int | None = None,
    top_k_snippets: int | None = None,
) -> dict[str, Any]:
    """混合检索：结构图子图 + 文本片段 + 符号锚点。

    把 LLM 相关子图（N 跳邻域）+ 相关文本片段一起返回，比纯文本 RAG
    多"全局依赖视角"（GraphRAG 核心思想：结构图 + 文本双视角）。

    检索逻辑（保守、零 LLM 成本）：
    1. 结构子图：若 center_module 指定，取 N 跳邻域子图（出边 + 入边）；
       否则若 center_symbol 指定，先经 find_symbol_anchor 定位符号所在
       模块，再取该模块的 N 跳邻域；
    2. 文本片段：若 query_text 指定，经 find_text_snippets 取 top_k 片段；
    3. 符号锚点：center_symbol / center_module 涉及的符号表条目。

    Args:
        index: GraphRAGIndex 实例。
        center_symbol: 中心符号名（可选，如函数名 "add"）。
        center_module: 中心模块名（可选，如 "math_utils"）。
        query_text: 检索文本（可选，如错误信息 / 变量名）。
        hops: 最大跳数（None 时读 GRAPH_RAG_MAX_HOPS，默认 2）。
        top_k_snippets: 文本片段数（None 时读 GRAPH_RAG_TOP_K_SNIPPETS，
            默认 5）。

    Returns:
        混合检索结果字典：
        {
            "subgraph": list[dict],      # N 跳邻域子图边
            "text_snippets": list[str],  # 相关文本片段
            "anchor_symbols": list[tuple[str, str]],  # 符号锚点
            "hops_used": int,           # 实际使用的跳数
            "center_symbol": str | None,
            "center_module": str | None,
        }
        （任一视角无数据时对应字段为空列表 / None，保守降级，不阻断修复。）
    """
    _hops = hops if hops is not None else _graph_rag_max_hops()
    _top_k = top_k_snippets if top_k_snippets is not None else _graph_rag_top_k_snippets()

    # 1. 定位中心模块（center_module 优先；否则从 center_symbol 符号锚点推）
    resolved_center: str | None = center_module
    if not resolved_center and center_symbol:
        anchors = index.find_symbol_anchor(center_symbol)
        if anchors:
            resolved_center = anchors[0][0]  # 取第一个锚点所在模块

    # 2. 结构子图（N 跳邻域，出边 + 入边）
    subgraph: list[dict[str, Any]] = []
    if resolved_center:
        subgraph = index.n_hop_subgraph(resolved_center, hops=_hops)

    # 3. 文本片段（query_text 检索）
    text_snippets: list[str] = []
    if query_text:
        text_snippets = index.find_text_snippets(query_text, top_k=_top_k)

    # 4. 符号锚点（center_symbol / center_module 涉及的符号）
    anchor_symbols: list[tuple[str, str]] = []
    if center_symbol:
        anchor_symbols = index.find_symbol_anchor(center_symbol)

    return {
        "subgraph": subgraph,
        "text_snippets": text_snippets,
        "anchor_symbols": anchor_symbols,
        "hops_used": _hops,
        "center_symbol": center_symbol,
        "center_module": resolved_center,
    }


def build_graphrag_prompt_section(result: dict[str, Any]) -> str:
    """把混合检索结果渲染为 debugger prompt 片段（空结果 → 空串）。

    渲染口径（保守、纯文本）：
    - 子图边 → "依赖: source_module.symbol → target_module (line N)"
    - 文本片段 → "片段: [module]:line: context_block"
    - 符号锚点 → "锚点: module.symbol"
    - 各视角为空时跳过（不渲染空段）。
    """
    if not result:
        return ""
    parts: list[str] = []
    subgraph: list[dict[str, Any]] = result.get("subgraph") or []
    if subgraph:
        edge_lines = [
            f"  {e.get('source_module')}.{e.get('symbol')} → {e.get('target_module')} (line {e.get('call_line', 0)})"
            for e in subgraph[:20]  # 限 20 条防 prompt 爆炸
        ]
        parts.append("【依赖子图】\n" + "\n".join(edge_lines))
    snippets: list[str] = result.get("text_snippets") or []
    if snippets:
        parts.append("【相关片段】\n" + "\n".join(f"  {s}" for s in snippets[:10]))
    anchors: list[tuple[str, str]] = result.get("anchor_symbols") or []
    if anchors:
        parts.append("【符号锚点】\n" + "\n".join(f"  {mod}.{sym}" for mod, sym in anchors[:10]))
    return "\n\n".join(parts)


__all__ = [
    "GraphRAGIndex",
    "build_graphrag_prompt_section",
    "graph_rag_enabled",
    "hybrid_retrieve",
]
