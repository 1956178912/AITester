"""
G1 Tree-sitter 精确 AST 语言后端（可选依赖，默认关，缺失时透明降级）。

背景（gap_report 2026-09-28 P1 缺口 G1）：
    language_backend.py 的接口契约（extract_symbols / extract_call_graph /
    check_naming_contract）已对齐 Tree-sitter 后端，但内置的是保守的
    零依赖词法层后端（正则 + 缩进），精度低于 Tree-sitter 的精确 AST 层。
    本模块提供可选的 Tree-sitter 精确 AST 后端实现：
    - 可选依赖 `tree_sitter` + 对应语言的 grammar 包（如 tree_sitter_typescript）；
    - 缺依赖时 `is_available()` 返回 False，调用方自动回退到词法层后端
      （不阻断 Python 主路径，与 ADR-0004 零默认依赖口径一致）；
    - 实现 `LanguageBackend` 协议的 4 个核心方法，精度高于词法层
      （基于 AST 的顶层定义 / 调用边 / 导出符号，保守口径：
      仅取"明确可见"的符号，不推断跨模块 / 动态调用）。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `AITESTER_ENABLE_TYPESCRIPT_BACKEND=tree_sitter` 时启用精确后端
      （默认 "lexical" 词法层；"tree_sitter" 需 tree_sitter 依赖已装）；
      缺依赖时自动降级回词法层并记 warning（不阻断）；
    - 后端实现是纯解析器（无 LLM 成本、无网络调用），确定性可复现。

使用方式：
    from src.tools.tree_sitter_backend import TypeScriptTreeSitterBackend, is_tree_sitter_available

    if is_tree_sitter_available():
        backend = TypeScriptTreeSitterBackend()
        symbols = backend.extract_symbols(code)
        edges = backend.extract_call_graph(code)
        missing = backend.check_naming_contract(original, patched)
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Tree-sitter 可选依赖探活（缺依赖时 is_available() 返回 False，透明降级）
try:
    import tree_sitter  # type: ignore[import-not-found]

    _HAS_TREE_SITTER = True
except ImportError:
    tree_sitter = None  # type: ignore[assignment]
    _HAS_TREE_SITTER = False


def is_tree_sitter_available() -> bool:
    """tree-sitter 可选依赖是否已安装（未安装时返回 False，调用方降级）。"""
    return _HAS_TREE_SITTER


class TypeScriptTreeSitterBackend:
    """TypeScript Tree-sitter 精确 AST 后端（可选依赖，默认关，缺失时降级）。

    实现 LanguageBackend 协议的 4 个核心方法（extract_symbols /
    extract_call_graph / check_naming_contract / classify_error），
    基于 tree-sitter-typescript 的精确 AST（若可用），否则回退到
    词法层保守口径（与 language_backend.TypeScriptBackend 同精度，
    避免"树状后端缺失时整条语言链路无可用后端"的硬依赖）。
    """

    language = "typescript"

    def __init__(self) -> None:
        """初始化后端（若 tree-sitter 可用则预编译 language parser，失败不阻断）。"""
        self._parser: Any = None
        if _HAS_TREE_SITTER:
            try:
                import tree_sitter_typescript  # type: ignore[import-not-found]

                self._language = tree_sitter_typescript.language()
                self._parser = tree_sitter.Parser(self._language)
            except Exception as e:  # grammar 包缺失 / 版本不兼容时降级
                logger.warning("tree-sitter-typescript 不可用（保守降级回词法层）: %s", e)
                self._parser = None
                self._language = None
        else:
            self._language = None

    def _fallback_lexical(self) -> Any:
        """缺 tree-sitter 依赖时回退到词法层后端（同精度，避免无可用后端）。"""
        from src.tools.language_backend import TypeScriptBackend

        return TypeScriptBackend()

    def _parse(self, code: str) -> Any:
        """解析代码为 tree-sitter 语法树（失败时返回 None，调用方降级）。"""
        if self._parser is None:
            return None
        try:
            return self._parser.parse(code.encode("utf-8"))
        except Exception:
            return None

    def _walk_symbols(self, tree: Any) -> set[str]:
        """遍历 AST 收集模块级符号（函数 / 类 / 导出 const / 导出函数）。

        保守口径（与语言无关契约对齐）：
            - 仅取顶层（root child）的 FunctionDeclaration / ClassDeclaration /
              VariableDeclaration（含 export 修饰）的标识符名；
            - 嵌套函数 / 方法体内部定义不进符号表（模块级契约只看导出面）。
        """
        symbols: set[str] = set()
        if tree is None:
            return symbols
        root = tree.root_node
        for child in root.children:
            kind = child.type
            if kind in ("FunctionDeclaration", "ClassDeclaration", "InterfaceDeclaration"):
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    symbols.add(name_node.text.decode("utf-8"))
            elif kind == "VariableDeclaration":
                # 含 export const / export let / export var（导出常量 / 变量）
                for decl in child.children:
                    if decl.type == "VariableDeclarator":
                        name_node = decl.child_by_field_name("name")
                        if name_node is not None:
                            symbols.add(name_node.text.decode("utf-8"))
        return symbols

    def extract_symbols(self, code: str) -> set[str]:
        """提取模块级符号（精确 AST 口径；tree-sitter 不可用时回退词法层）。"""
        tree = self._parse(code)
        if tree is not None:
            return self._walk_symbols(tree)
        return self._fallback_lexical().extract_symbols(code)

    def extract_call_graph(self, code: str) -> list[tuple[str, str]]:
        """提取调用边（调用方 → 被调方，精确 AST 口径；缺依赖时回退词法层）。

        保守口径：仅取顶层函数 / 类方法体内**直接调用**的标识符
        （不做跨模块 / 动态调用推断——与词法层精度对齐但基于 AST，
        误报更少：词法层的正则会把 `if(` / `for(` 之外的字符串内
        假"调用"也命中，AST 层只对 CallExpression 节点取 callee）。
        """
        tree = self._parse(code)
        if tree is not None:
            edges: list[tuple[str, str]] = []

            def _collect_calls(node: Any, caller: str | None) -> None:
                if node.type == "CallExpression":
                    callee_node = node.child_by_field_name("function")
                    if callee_node is not None and callee_node.type == "identifier" and caller:
                        callee_name = callee_node.text.decode("utf-8")
                        if callee_name != caller:
                            edges.append((caller, callee_name))
                    return  # CallExpression 不再递归（避免把参数内的调用重复计）
                if caller and node.type in ("FunctionDeclaration", "ClassMethod"):
                    # 进入顶层函数 / 类方法体时更新 caller
                    name_node = node.child_by_field_name("name")
                    if name_node is not None:
                        new_caller = name_node.text.decode("utf-8")
                        for child in node.children:
                            _collect_calls(child, new_caller)
                        return
                for child in getattr(node, "children", []):
                    _collect_calls(child, caller)

            _collect_calls(tree.root_node, None)
            return edges
        return self._fallback_lexical().extract_call_graph(code)

    def check_naming_contract(self, original: str, patched: str) -> set[str]:
        """命名契约守卫：返回原文件有、补丁文件缺失的模块级符号（被删符号集）。"""
        orig_symbols = self.extract_symbols(original)
        patched_symbols = self.extract_symbols(patched)
        return orig_symbols - patched_symbols

    def classify_error(self, output: str) -> str:
        """TS 编译 / 运行时错误文本 → 错误类别映射（与词法层同口径，17 类子集）。"""
        return self._fallback_lexical().classify_error(output)


def register_tree_sitter_backend() -> None:
    """把 Tree-sitter 后端注册进 language_backend 的注册表（覆盖默认词法层）。

    调用前提：
        - tree-sitter 依赖已安装（is_tree_sitter_available() 为 True）；
        - 调用方应在 AITESTER_ENABLE_TYPESCRIPT_BACKEND=tree_sitter 时调用
          （默认 lexical 词法层不受影响，注册表默认仍指向词法层后端）。

    缺依赖时本函数 no-op（不抛错，保守降级：注册表保持词法层后端）。
    """
    if not is_tree_sitter_available():
        logger.debug("register_tree_sitter_backend: tree-sitter 不可用，跳过注册（保持词法层）")
        return
    from src.tools.language_backend import register_backend

    register_backend(TypeScriptTreeSitterBackend())


__all__ = [
    "TypeScriptTreeSitterBackend",
    "is_tree_sitter_available",
    "register_tree_sitter_backend",
]
