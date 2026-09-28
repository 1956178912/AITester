"""
语言后端抽象层（Language Backend，默认关）。

背景（P2 多语言 Tree-sitter 层 + 设计文档 docs/design/multilanguage_extension.md）：
    设计文档已把"语言后端"抽象层、扩展点接口、默认关开关策略（
    AITESTER_ENABLE_<LANG>_BACKEND）全部定义清楚，但标注"Design-only，
    未落地代码"。本模块落地**单一语言验证接口抽象**（TypeScript 后端），
    用纯正则 / 词法分析（零默认依赖，ADR-0004 口径）实现"AST 依赖分析 +
    符号守卫 + 调用图提取"的语言无关骨架，使新增一种被测语言 =
    实现一个后端注册 + 数据（不改动核心图编排）。

    Tree-sitter 是设计文档规划的"可选扩展后端"（20+ 语言的精确调用图），
    本模块的**接口契约**与 Tree-sitter 后端对齐（extract_symbols /
    extract_call_graph / check_naming_contract），实现用零依赖词法分析
    做默认（缺 Tree-sitter 时透明降级，不阻断 Python 主路径）。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - 每种语言后端以 `AITESTER_ENABLE_<LANG>_BACKEND` 形式落地（默认 false），
      保证 Python 默认路径零变化；
    - 非 Python 后端的"符号提取 / 调用图"是**保守词法层**（正则 + 缩进），
      精度低于 Tree-sitter AST 层，但零依赖、确定性可复现；
    - 接口契约与 patch_applier.check_naming_contract（Python AST 专属）
      对齐：各语言后端实现 `check_naming_contract(original, patched) ->
      set[str]`（被删除的模块级符号集合），跨语言守卫可复用 patch_applier
      的拒绝 + 重采样骨架。

使用方式（未来多语言任务）：
    from src.tools.language_backend import get_language_backend, register_backend

    backend = get_language_backend("typescript")
    symbols = backend.extract_symbols(code)
    missing = backend.check_naming_contract(original, patched)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Protocol

logger = logging.getLogger(__name__)


class LanguageBackend(Protocol):
    """语言后端抽象协议（与 Tree-sitter 后端对齐的接口契约）。

    每种语言实现此协议的 4 个核心方法：
    - extract_symbols(code) -> set[str]：模块级符号集合（函数 / 类 / 导出常量）
    - extract_call_graph(code) -> list[tuple[str, str]]：调用边（调用方 → 被调方）
    - check_naming_contract(original, patched) -> set[str]：被删除的模块级符号
    - classify_error(output) -> str：异常文本 → 错误类别映射（17 类分类器）
    """

    language: str

    def extract_symbols(self, code: str) -> set[str]: ...

    def extract_call_graph(self, code: str) -> list[tuple[str, str]]: ...

    def check_naming_contract(self, original: str, patched: str) -> set[str]: ...

    def classify_error(self, output: str) -> str: ...


def backend_enabled(language: str) -> bool:
    """语言后端开关（AITESTER_ENABLE_<LANG>_BACKEND=true 时启用，默认 false）。

    环境变量名归一：language="typescript" → AITESTER_ENABLE_TYPESCRIPT_BACKEND。
    """
    upper = language.strip().upper()
    env_name = f"AITESTER_ENABLE_{upper}_BACKEND"
    return os.getenv(env_name, "false").lower() == "true"


# ─── TypeScript 后端（零依赖词法层，保守精度）───────────────────────────────

# TS 顶层函数 / 箭头函数 / 类 / const 导出的正则（保守词法层）
_TS_FUNC_RE = re.compile(
    r"^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|"
    r"^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async)?\s*[\(|\w]+\s*(?:=>|\()",
    re.MULTILINE,
)
_TS_CLASS_RE = re.compile(r"^(?:export\s+)?class\s+(\w+)", re.MULTILINE)
_TS_CONST_RE = re.compile(r"^(?:export\s+)?const\s+(\w+)\s*=", re.MULTILINE)
# 调用边：(调用方函数体内的 被调函数名)( 模式（保守：仅顶层函数内直接调用）
_TS_CALL_RE = re.compile(r"\b(\w+)\s*\(")


class TypeScriptBackend:
    """TypeScript 语言后端（零依赖词法层，保守精度，默认关）。

    实现 LanguageBackend 协议的 4 个核心方法。符号提取精度低于 Tree-sitter
    AST 层（正则 + 缩进），但零依赖、确定性可复现，满足"接口契约验证"
    目标（新增语言 = 实现一个后端 + 数据，不改动核心图编排）。
    """

    language = "typescript"

    def extract_symbols(self, code: str) -> set[str]:
        """提取模块级符号（函数 / 类 / const 导出），保守词法层。"""
        symbols: set[str] = set()
        for m in _TS_FUNC_RE.finditer(code):
            symbols.add(m.group(1) or m.group(2))
        for m in _TS_CLASS_RE.finditer(code):
            symbols.add(m.group(1))
        for m in _TS_CONST_RE.finditer(code):
            symbols.add(m.group(1))
        return symbols

    def extract_call_graph(self, code: str) -> list[tuple[str, str]]:
        """提取调用边（调用方 → 被调方），保守词法层。

        实现口径：按顶层函数切分（_TS_FUNC_RE 命中的函数名），
        函数体内的 被调函数名( 模式生成调用边。精度低于 Tree-sitter
        的精确调用图（无法区分同名函数 / 跨模块调用），但满足
        "单文件内直接调用"的保守口径。
        """
        edges: list[tuple[str, str]] = []
        func_positions: list[tuple[str, int, int]] = []
        for m in _TS_FUNC_RE.finditer(code):
            name = m.group(1) or m.group(2)
            if not name:
                continue
            func_positions.append((name, m.start(), m.end()))
        # 按位置排序（嵌套函数后命中先，保守：仅取顶层函数体的直接调用）
        func_positions.sort(key=lambda x: x[1])
        for i, (name, _start, end) in enumerate(func_positions):
            next_start = func_positions[i + 1][1] if i + 1 < len(func_positions) else len(code)
            body = code[end:next_start]
            for call in _TS_CALL_RE.finditer(body):
                callee = call.group(1)
                if callee != name and callee not in ("if", "for", "while", "switch", "return", "new"):
                    edges.append((name, callee))
        return edges

    def check_naming_contract(self, original: str, patched: str) -> set[str]:
        """命名契约守卫：返回原文件有、补丁文件缺失的模块级符号（被删除符号集）。"""
        orig_symbols = self.extract_symbols(original)
        patched_symbols = self.extract_symbols(patched)
        return orig_symbols - patched_symbols

    def classify_error(self, output: str) -> str:
        """TS 编译 / 运行时错误文本 → 错误类别映射（保守词法层，17 类口径子集）。"""
        out = output.lower()
        if "syntaxerror" in out or "syntax error" in out:
            return "syntax"
        if "timeout" in out or "timed out" in out:
            return "timeout"
        if "assertion" in out or "expected" in out:
            return "assertion"
        if "typeerror" in out or "undefined is not" in out:
            return "runtime"
        if "cannot find name" in out or "cannot find module" in out:
            return "import_error"
        return "unknown"


# ─── 后端注册表（按语言名查表，未注册 → 降级 None）───────────────────────────

_BACKENDS: dict[str, LanguageBackend] = {
    "typescript": TypeScriptBackend(),
}


def get_language_backend(language: str) -> LanguageBackend | None:
    """按语言名获取后端实例（未注册 / 未启用 → None，保守降级）。

    未注册的语言（如尚未实现后端的 Go / Java / Rust）返回 None，
    调用方走 Python 默认路径或字符截断口径（不阻断主流程）。
    """
    key = language.strip().lower()
    if key not in _BACKENDS:
        return None
    if not backend_enabled(key):
        return None
    return _BACKENDS[key]


def register_backend(backend: LanguageBackend) -> None:
    """注册一个语言后端（测试 / 扩展场景用；默认注册表只含 TypeScript）。"""
    _BACKENDS[backend.language] = backend


def list_registered_languages() -> list[str]:
    """返回已注册的语言后端名列表（供文档 / 实验分析消费）。"""
    return list(_BACKENDS.keys())


__all__ = [
    "LanguageBackend",
    "TypeScriptBackend",
    "backend_enabled",
    "get_language_backend",
    "list_registered_languages",
    "register_backend",
]
