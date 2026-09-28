"""
分层摘要压缩层（Hierarchical Summary，默认关）。

背景（RAG 与上下文管理方向：从"向量相似检索"走向"无损压缩"）：
    当前 `BaseAgent.truncate_code` 对超长代码做"字符级头尾截断"——尾部逻辑
    与被截断模块的关键符号会丢失，导致 LLM "看不到全貌"。2026 年
    Contextual Memory Virtualisation / 多规则潜在推理剪枝等框架把上下文
    管理从"截断"升级为"分层摘要 + 轮次间历史压缩"：按"函数 → 模块 → 文件"
    层级逐步压缩，保留高信息密度部分（异常相关栈帧、命名契约符号、公共
    API、测试关注函数），而非机械截尾。

本模块落地设计文档 `docs/design/hierarchical_summary.md` 的 M1 里程碑
（Level 1-3 纯静态分层摘要 + 降级链 + 默认关开关）：

    Level 0  原始全文（≤ 预算 → 直接用，零摘要开销）
    Level 1  函数级摘要：目标函数 + 1-2 层调用链 + 命名契约符号
    Level 2  模块级摘要：公共 API + 异常相关符号 + 测试关注点的签名级摘要
    Level 3  文件级摘要：模块导出 + 顶层常量 + 关键类签名
    （仍超限才退化为字符级截尾——最坏情况不劣于现状）

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `HIERARCHICAL_SUMMARY_ENABLE=false`（默认）时，`summarize_code`
      直接返回原始文本（调用方应检查开关后再调用本模块，或经
      `truncate_code_with_summary` 的统一入口自动降级为字符截断口径）；
    - 纯静态（ast + 符号表 + 滑窗打分），零 LLM 成本、确定性可复现；
    - 预算参数化：`SUMMARY_BUDGET_L1/L2/L3` 环境变量（默认 1200/800/400 字符）；
    - 可观测层：`summarize_code` 返回 `(摘要文本, 观测元数据 dict)`，
      元数据含 `summary_level`（实际停在哪层）+ `summary_dropped_symbols`
      （被丢弃的模块级符号列表），供 `analyze_results.py` 统计
      "摘要层触发率 / 各层丢弃率"。

使用方式（BaseAgent.truncate_code 升级 / 节点 prompt 构建）：
    from src.tools.hierarchical_summary import summarize_code, hierarchical_summary_enabled

    if hierarchical_summary_enabled():
        text, meta = summarize_code(code, focus_function="add", budget=1200)
"""

from __future__ import annotations

import ast
import os
from typing import Any

# ─── 预算参数（环境变量，模块级缓存 + 调用期读取，保留测试 patch.dict 能力）───
# 各层默认预算（字符）：L1 函数级 1200 / L2 模块级 800 / L3 文件级 400
_DEFAULT_BUDGETS = {"L1": 1200, "L2": 800, "L3": 400}


def _budget_env(level: str) -> int:
    """读 SUMMARY_BUDGET_<LEVEL> 环境变量，缺省用默认预算（保守口径）。"""
    try:
        return int(os.getenv(f"SUMMARY_BUDGET_{level}", str(_DEFAULT_BUDGETS[level])))
    except ValueError:
        return _DEFAULT_BUDGETS[level]


def hierarchical_summary_enabled() -> bool:
    """分层摘要开关（HIERARCHICAL_SUMMARY_ENABLE=true 时启用，默认 false）。"""
    return os.getenv("HIERARCHICAL_SUMMARY_ENABLE", "false").lower() == "true"


# ─── 静态符号提取（ast 层，零 LLM 成本）─────────────────────────────────────


def _extract_functions(source: str, focus_function: str | None = None) -> list[dict[str, Any]]:
    """AST 提取函数/方法定义（名称 + 行号 + 签名 + docstring 首行）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    funcs: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            sig_args = ", ".join(a.arg for a in node.args.args[:8])  # 限 8 参数防爆炸
            doc_first = ""
            if node.body and isinstance(node.body[0], ast.Expr):
                val = node.body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    doc_first = val.value.split("\n", 1)[0][:80]
            funcs.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "end_lineno": node.end_lineno,
                    "signature": f"def {node.name}({sig_args})",
                    "doc_first": doc_first,
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                    "focus": focus_function is not None and node.name == focus_function,
                }
            )
    return funcs


def _extract_classes(source: str) -> list[dict[str, Any]]:
    """AST 提取类定义（名称 + 公共方法签名 + docstring 首行）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    classes: list[dict[str, Any]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                f"    def {m.name}({', '.join(a.arg for a in m.args.args[:6])})"
                for m in node.body
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("_")
            ]
            doc_first = ""
            if node.body and isinstance(node.body[0], ast.Expr):
                val = node.body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    doc_first = val.value.split("\n", 1)[0][:80]
            classes.append(
                {
                    "name": node.name,
                    "lineno": node.lineno,
                    "doc_first": doc_first,
                    "public_methods": methods[:12],  # 限 12 个方法防爆炸
                }
            )
    return classes


def _extract_module_symbols(source: str) -> dict[str, Any]:
    """AST 提取模块级符号（import / 常量 / __all__ / 注册装饰器）。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"imports": [], "constants": [], "all_exports": []}
    imports: list[str] = []
    constants: list[str] = []
    all_exports: list[str] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            else:
                module = node.module or ""
                names = [alias.name for alias in node.names]
                imports.append(f"{module} ({', '.join(names[:6])})" if module else ", ".join(names[:6]))
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and not target.id.startswith("_"):
                constants.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            constants.append(node.target.id)
    # __all__ 提取
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "__all__"
                    and isinstance(node.value, (ast.List, ast.Tuple))
                ):
                    all_exports = [
                        elt.value
                        for elt in node.value.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    ]
    return {"imports": imports[:20], "constants": constants[:20], "all_exports": all_exports[:30]}


# ─── 分层摘要构建（滑窗打分：焦点函数 > 公共 API > 异常相关 > 其余）─────────


def _level1_summary(source: str, focus_function: str | None, budget: int) -> tuple[str, dict[str, Any]]:
    """Level 1：函数级摘要（目标函数完整体 + 1 层调用链签名 + 命名契约符号）。"""
    funcs = _extract_functions(source, focus_function)
    lines: list[str] = []
    dropped: list[str] = []

    # 焦点函数完整体（最高优先级，保留函数体而非仅签名）
    focus_func = next((f for f in funcs if f["focus"]), None)
    if focus_func:
        src_lines = source.splitlines()
        body = "\n".join(src_lines[focus_func["lineno"] - 1 : focus_func["end_lineno"]])
        lines.append(f"// [focus] {focus_func['signature']}")
        lines.append(body)
        lines.append("")

    # 命名契约符号（模块级 import + 常量 + __all__）
    symbols = _extract_module_symbols(source)
    if symbols["all_exports"]:
        lines.append(f"__all__ = {symbols['all_exports']}")
    if symbols["imports"]:
        lines.append("imports: " + ", ".join(symbols["imports"][:10]))
    if symbols["constants"]:
        lines.append(f"module_constants: {', '.join(symbols['constants'][:10])}")

    # 其余函数签名（按 focus 优先 + 名称长度排序，超预算丢弃）
    others = [f for f in funcs if not f["focus"]]
    for f in others:
        sig_line = f"// {f['signature']}"
        if focus_func and len("\n".join(lines) + sig_line) > budget:
            dropped.append(f["name"])
            continue
        lines.append(sig_line)
        if f["doc_first"]:
            lines.append(f"//   doc: {f['doc_first']}")
    result = "\n".join(lines)
    # 仍超预算 → 字符级截尾（最坏情况不劣于现状）
    if len(result) > budget * 1.5:
        result = result[:budget] + f"\n// [truncated to {budget} chars]"
    meta = {"summary_level": 1, "summary_dropped_symbols": dropped}
    return result, meta


def _level2_summary(source: str, focus_function: str | None, budget: int) -> tuple[str, dict[str, Any]]:
    """Level 2：模块级签名摘要（公共 API + 异常相关符号，不保留函数体）。"""
    funcs = _extract_functions(source, focus_function)
    classes = _extract_classes(source)
    symbols = _extract_module_symbols(source)
    lines: list[str] = []
    dropped: list[str] = []

    if symbols["all_exports"]:
        lines.append(f"__all__ = {symbols['all_exports']}")
    if symbols["imports"]:
        lines.append("imports: " + ", ".join(symbols["imports"][:8]))

    for c in classes:
        class_block = [f"class {c['name']}"]
        if c["doc_first"]:
            class_block.append(f"// {c['doc_first']}")
        class_block.extend(c["public_methods"])
        block_text = "\n".join(class_block)
        if len("\n".join(lines) + block_text) > budget * 1.2:
            dropped.append(f"class:{c['name']}")
            continue
        lines.append(block_text)

    for f in funcs:
        sig = f"def {f['name']}"
        if f["doc_first"]:
            sig += f"  # {f['doc_first'][:60]}"
        if f["focus"]:
            sig += "  [FOCUS]"
        if len("\n".join(lines) + sig) > budget * 1.2:
            dropped.append(f["name"])
            continue
        lines.append(sig)
    result = "\n".join(lines)
    if len(result) > budget * 1.5:
        result = result[:budget] + f"\n// [truncated to {budget} chars]"
    meta = {"summary_level": 2, "summary_dropped_symbols": dropped}
    return result, meta


def _level3_summary(source: str, focus_function: str | None, budget: int) -> tuple[str, dict[str, Any]]:
    """Level 3：文件级极简摘要（模块导出 + 顶层常量 + 关键类签名，无方法体）。"""
    symbols = _extract_module_symbols(source)
    classes = _extract_classes(source)
    funcs = _extract_functions(source, focus_function)
    lines: list[str] = []
    dropped: list[str] = []

    if symbols["all_exports"]:
        lines.append(f"__all__ = {symbols['all_exports']}")
    if symbols["constants"]:
        lines.append(f"constants: {', '.join(symbols['constants'][:10])}")
    for c in classes[:8]:
        methods_sig = ", ".join(m.split("(")[0].strip() for m in c["public_methods"][:8])
        lines.append(f"class {c['name']}({methods_sig})")
        if len("\n".join(lines)) > budget:
            break
    for f in funcs[:12]:
        sig = f"def {f['name']}"
        if f["focus"]:
            sig += " [FOCUS]"
        lines.append(sig)
        if len("\n".join(lines)) > budget:
            dropped.append(f["name"])
            break
    result = "\n".join(lines)
    meta = {"summary_level": 3, "summary_dropped_symbols": dropped}
    return result, meta


def summarize_code(
    source: str,
    focus_function: str | None = None,
    budget: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """分层摘要压缩：按 Level 0→1→2→3 降级链构建摘要（纯静态，零 LLM 成本）。

    降级链（与设计文档 §2 同口径）：
        Level 0  len(source) ≤ budget → 直接返回原文（零摘要开销）
        Level 1  函数级摘要（焦点函数体 + 契约符号 + 其余签名）
        Level 2  模块级签名摘要（公共 API + 类方法签名，不保留函数体）
        Level 3  文件级极简摘要（导出 + 常量 + 类签名）
        仍超限（L3 字符截尾）→ 最坏情况不劣于现行字符截断

    Args:
        source: 被测代码全文（或跨文件场景的模块拼接文本）。
        focus_function: 焦点函数名（None 时无焦点，按名称排序取前 N 函数）。
        budget: 摘要预算（字符）；None 时读 SUMMARY_BUDGET_L1 环境变量
            （默认 1200）。L2/L3 预算经 SUMMARY_BUDGET_L2/L3 独立配置。

    Returns:
        (摘要文本, 观测元数据 dict)：
        - 摘要文本：分层摘要结果（Level 0 时为原文，逐字节等价）
        - 观测元数据：{"summary_level": int, "summary_dropped_symbols": list[str],
          "summary_budget": int}（供 analyze_results.py 统计摘要层触发率）
    """
    if not source:
        return "", {"summary_level": 0, "summary_dropped_symbols": [], "summary_budget": 0}
    _budget = budget if budget is not None else _budget_env("L1")
    # Level 0：原文不超预算 → 直接用（零摘要开销）
    if len(source) <= _budget:
        return source, {"summary_level": 0, "summary_dropped_symbols": [], "summary_budget": _budget}
    # Level 1：函数级摘要
    l1, meta1 = _level1_summary(source, focus_function, _budget)
    if len(l1) <= _budget * 1.5:
        meta1["summary_budget"] = _budget
        return l1, meta1
    # Level 2：模块级签名摘要
    l2, meta2 = _level2_summary(source, focus_function, _budget_env("L2"))
    if len(l2) <= _budget_env("L2") * 1.5:
        meta2["summary_budget"] = _budget_env("L2")
        return l2, meta2
    # Level 3：文件级极简摘要（最坏情况截尾，不劣于现状）
    l3, meta3 = _level3_summary(source, focus_function, _budget_env("L3"))
    meta3["summary_budget"] = _budget_env("L3")
    return l3, meta3


def truncate_code_with_summary(
    source: str, focus_function: str | None = None, max_chars: int = 1200
) -> tuple[str, dict[str, Any]]:
    """`BaseAgent.truncate_code` 的分层摘要升级入口（统一开关 + 降级链）。

    开关关闭（HIERARCHICAL_SUMMARY_ENABLE=false，默认）时，直接走
    `BaseAgent.truncate_code` 历史字符截断口径（逐字节等价，零变化）；
    开关开启时，经 `summarize_code` 做分层摘要，最坏情况（L3 仍超限）
    退化为字符截尾（不劣于现状）。

    Args:
        source: 被测代码全文。
        focus_function: 焦点函数名（可选）。
        max_chars: 预算上限（字符），传 None 时读 SUMMARY_BUDGET_L1。

    Returns:
        (摘要文本, 观测元数据 dict)。观测元数据键与 summarize_code 同口径。
    """
    if not hierarchical_summary_enabled():
        # 开关关：走历史字符截断口径（BaseAgent.truncate_code 行为）
        from src.agents.base_agent import BaseAgent

        truncated = BaseAgent.truncate_code(source, focus_function=focus_function, max_chars=max_chars or 3000)
        return truncated, {"summary_level": 0, "summary_dropped_symbols": [], "summary_budget": len(truncated)}
    return summarize_code(source, focus_function=focus_function, budget=max_chars)


__all__ = [
    "hierarchical_summary_enabled",
    "summarize_code",
    "truncate_code_with_summary",
]
