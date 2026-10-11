"""操作图（Operation Map）：已验证 utility helper 清单（结构接地·SPARC 第 2 阶段）。

背景（独立审查 2026-10-10 落地，报告建议 4 结构接地的第 2 阶段静态基础）：
    SPARC（arXiv:2602.16671）第 2 阶段"Operation Map"——把 LLM 测试合成
    **接地在已验证的 utility helper 上**，避免 leap-to-code 失败模式（LLM
    凭空调用不存在的 helper / 编造 API / 错写参数签名）。与路径枚举
    （`control_flow.enumerate_paths`，第 1 阶段）共同构成"结构接地"的静态
    两件套：路径枚举告诉 LLM"走哪些路径"，操作图告诉 LLM"能调用哪些符号"。

    此前的 `code_analyzer.parse_function_nodes` 只提取函数名/参数名/行号/
    docstring，不提取**类型注解**（参数类型 / 返回类型）、**类与方法**、
    **模块级常量**、**导入清单**——本模块补齐这些，产出可注入 prompt 的
    "已验证符号清单"。

设计纪律：
    - 纯 AST 静态分析，零 LLM 成本、不执行被测代码（安全）；
    - 解析失败返回空清单（保守降级，不阻断主流程）；
    - 输出 JSON 可序列化（供 state / trace / prompt 注入复用）。
"""

from __future__ import annotations

import ast
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 签名清单注入 prompt 时的最大符号数（防超长代码撑爆上下文）
_MAX_FUNCTIONS = 24
_MAX_CLASSES = 12
_MAX_CONSTANTS = 24
_MAX_IMPORTS = 24


def _func_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """函数节点 → 签名文本（``def name(args) -> ret``，去掉函数体）。

    用 ast.unparse 序列化参数（保留类型注解 + 默认值）与返回注解，使 LLM
    拿到"已验证存在且类型正确"的调用契约，避免编造参数签名。
    """
    args_text = ast.unparse(node.args)
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args_text}){ret}"


def _top_level_statements(tree: ast.Module) -> list[ast.stmt]:
    """模块顶层语句列表（排除 import——import 单独收集）。"""
    return [s for s in tree.body if not isinstance(s, (ast.Import, ast.ImportFrom))]


def _collect_imports(tree: ast.Module) -> list[str]:
    """显式导入清单（``import X`` / ``from X import Y``），去重保序。"""
    imports: list[str] = []
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                text = f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
                if text not in seen:
                    seen.add(text)
                    imports.append(text)
        elif isinstance(node, ast.ImportFrom):
            names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in node.names)
            text = f"from {node.module or ''}{'.' * node.level} import {names}"
            if text not in seen:
                seen.add(text)
                imports.append(text)
    return imports


def build_operation_map(code: str) -> dict[str, Any]:
    """收集被测代码的"操作图"（已验证 utility helper 清单，零 LLM 成本）。

    Args:
        code: 被测代码全文（AST 解析）。

    Returns:
        {
          "functions": [str, ...],   # 顶层函数签名（def name(args) -> ret）
          "classes": [str, ...],     # 顶层类签名 + 方法签名（缩进）
          "constants": [str, ...],   # 模块级常量（UPPER_CASE 赋值）
          "imports": [str, ...],     # 显式导入清单
        }
        代码不可解析时返回全空清单（保守降级）。
    """
    empty: dict[str, Any] = {"functions": [], "classes": [], "constants": [], "imports": []}
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return empty

    functions: list[str] = []
    classes: list[str] = []
    constants: list[str] = []
    seen_constants: set[str] = set()

    for stmt in _top_level_statements(tree):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if len(functions) < _MAX_FUNCTIONS:
                functions.append(_func_signature(stmt))
        elif isinstance(stmt, ast.ClassDef):
            if len(classes) < _MAX_CLASSES:
                bases = f"({', '.join(ast.unparse(b) for b in stmt.bases)})" if stmt.bases else ""
                classes.append(f"class {stmt.name}{bases}:")
                # 类方法签名（缩进一层，去函数体），受 _MAX_CLASSES 总量约束
                methods = [
                    f"    {_func_signature(m)}"
                    for m in stmt.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                classes.extend(methods[: _MAX_CLASSES - len(classes)])
        elif isinstance(stmt, ast.Assign):
            # 模块级常量：所有目标均为 UPPER_CASE 标识符的赋值
            names = [t.id for t in stmt.targets if isinstance(t, ast.Name)]
            if names and all(n.isupper() for n in names) and len(constants) < _MAX_CONSTANTS:
                for n in names:
                    if n not in seen_constants:
                        seen_constants.add(n)
                        try:
                            val = ast.unparse(stmt.value)[:40]
                        except Exception:
                            val = "?"
                        constants.append(f"{n} = {val}")

    imports = _collect_imports(tree)[:_MAX_IMPORTS]
    return {"functions": functions, "classes": classes, "constants": constants, "imports": imports}


def build_operation_map_section(opmap: dict[str, Any] | None) -> str:
    """操作图 → prompt 注入段落（结构接地·操作图提示）。

    与 build_paths_prompt_section 同口径：None / 全空清单时返回空串
    （无可接地符号 = 注入无增量）。默认零行为变化（由调用方在开关开启时拼接）。
    """
    if not opmap:
        return ""
    funcs = opmap.get("functions") or []
    classes = opmap.get("classes") or []
    constants = opmap.get("constants") or []
    imports = opmap.get("imports") or []
    if not (funcs or classes or constants):
        return ""

    lines: list[str] = ["\n【操作图（结构接地·已验证符号清单）】"]
    lines.append(
        "被测代码中**已验证存在**的可调用符号——测试代码只应调用下列符号，不得编造不存在的 API / helper / 参数签名："
    )
    if funcs:
        lines.append("函数：")
        lines.extend(f"- {f}" for f in funcs)
    if classes:
        lines.append("类：")
        lines.extend(f"- {c}" for c in classes)
    if constants:
        lines.append("常量：")
        lines.extend(f"- {c}" for c in constants)
    if imports:
        lines.append("可用导入：")
        lines.extend(f"- {i}" for i in imports)
    return "\n".join(lines)
