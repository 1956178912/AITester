"""批次5 Tree-sitter 单语言后端（语言无关接口抽象，TypeScript 验证）单元测试。

覆盖：
- backend_enabled 默认关（AITESTER_ENABLE_TYPESCRIPT_BACKEND 未设）
- backend_enabled 开关开启
- TypeScriptBackend.extract_symbols 提取函数/类/const 符号
- TypeScriptBackend.extract_call_graph 提取调用边
- TypeScriptBackend.check_naming_contract 返回被删除符号
- TypeScriptBackend.classify_error 保守词法分类
- get_language_backend 未注册语言 → None
- get_language_backend 注册但未启用 → None
- get_language_backend 注册且启用 → 返回实例
- register_backend / list_registered_languages
"""

from __future__ import annotations

import os
from unittest.mock import patch


def test_backend_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AITESTER_ENABLE_TYPESCRIPT_BACKEND", None)
        from src.tools.language_backend import backend_enabled

        assert backend_enabled("typescript") is False
        assert backend_enabled("Typescript") is False  # 大小写不敏感


def test_backend_switch_on() -> None:
    with patch.dict(os.environ, {"AITESTER_ENABLE_TYPESCRIPT_BACKEND": "true"}):
        from src.tools.language_backend import backend_enabled

        assert backend_enabled("typescript") is True


def test_ts_extract_symbols() -> None:
    from src.tools.language_backend import TypeScriptBackend

    backend = TypeScriptBackend()
    code = (
        "export function add(a: number, b: number): number {\n"
        "    return a + b;\n"
        "}\n"
        "export class Calculator {\n"
        "    divide(x: number, y: number): number {\n"
        "        return x / y;\n"
        "    }\n"
        "}\n"
        "const PI = 3.14;\n"
        "function helper() {}\n"
    )
    symbols = backend.extract_symbols(code)
    assert "add" in symbols
    assert "Calculator" in symbols
    assert "PI" in symbols
    assert "helper" in symbols


def test_ts_extract_call_graph() -> None:
    from src.tools.language_backend import TypeScriptBackend

    backend = TypeScriptBackend()
    code = (
        "function compute(a, b) {\n"
        "    let s = add(a, b);\n"
        "    return normalize(s);\n"
        "}\n"
        "function add(x, y) {\n"
        "    return x + y;\n"
        "}\n"
        "function normalize(v) {\n"
        "    return v;\n"
        "}\n"
    )
    edges = backend.extract_call_graph(code)
    # compute 调用 add 和 normalize
    edge_set = set((a, b) for a, b in edges)
    assert ("compute", "add") in edge_set
    assert ("compute", "normalize") in edge_set
    # add 和 normalize 不互相调用
    assert ("add", "normalize") not in edge_set


def test_ts_check_naming_contract() -> None:
    from src.tools.language_backend import TypeScriptBackend

    backend = TypeScriptBackend()
    original = "export function foo() {}\nexport function bar() {}\nconst X = 1;\n"
    patched = "export function foo() {}\n"  # 删除了 bar 和 X
    missing = backend.check_naming_contract(original, patched)
    assert "bar" in missing
    assert "X" in missing
    assert "foo" not in missing


def test_ts_classify_error() -> None:
    from src.tools.language_backend import TypeScriptBackend

    backend = TypeScriptBackend()
    assert backend.classify_error("SyntaxError: Unexpected token") == "syntax"
    assert backend.classify_error("Test timed out after 30s") == "timeout"
    assert backend.classify_error("AssertionError: expected 1, got 2") == "assertion"
    assert backend.classify_error("TypeError: Cannot read property of undefined") == "runtime"
    assert backend.classify_error("Cannot find module './foo'") == "import_error"
    assert backend.classify_error("some random text") == "unknown"


def test_get_language_backend_unregistered_returns_none() -> None:
    from src.tools.language_backend import get_language_backend

    # Go / Java / Rust 未注册 → None（保守降级，不阻断 Python 主路径）
    assert get_language_backend("go") is None
    assert get_language_backend("java") is None


def test_get_language_backend_registered_but_disabled() -> None:
    from src.tools.language_backend import get_language_backend

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("AITESTER_ENABLE_TYPESCRIPT_BACKEND", None)
        assert get_language_backend("typescript") is None  # 未启用


def test_get_language_backend_enabled_returns_instance() -> None:
    from src.tools.language_backend import TypeScriptBackend, get_language_backend

    with patch.dict(os.environ, {"AITESTER_ENABLE_TYPESCRIPT_BACKEND": "true"}):
        backend = get_language_backend("typescript")
        assert isinstance(backend, TypeScriptBackend)


def test_register_backend_and_list() -> None:
    from src.tools.language_backend import list_registered_languages, register_backend

    languages = list_registered_languages()
    assert "typescript" in languages

    # 注册一个模拟后端（测试用）
    class _MockBackend:
        language = "mocklang"

        def extract_symbols(self, code: str) -> set[str]:
            return set()

        def extract_call_graph(self, code: str) -> list[tuple[str, str]]:
            return []

        def check_naming_contract(self, original: str, patched: str) -> set[str]:
            return set()

        def classify_error(self, output: str) -> str:
            return "unknown"

    register_backend(_MockBackend())
    assert "mocklang" in list_registered_languages()
