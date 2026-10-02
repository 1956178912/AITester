"""tools/tree_sitter_backend 精确 AST 路径 + 注册/降级分支补齐（2026-10-02 批次·七）。

背景：本仓未安装 tree_sitter / tree_sitter_typescript（可选依赖），
tree_sitter_backend 默认 _HAS_TREE_SITTER=False，4 个核心方法全走词法层
降级——精确 AST 路径（_walk_symbols / _collect_calls / tree 非 None 分支）
与注册成功路径（register 时 is_available()=True → register_backend）
此前零覆盖。本文件用 FakeNode / FakeTree 模拟 tree-sitter 节点 API
（type / children / child_by_field_name / text / root_node）构造"已解析"
状态，绕过真实解析器直接走精确 AST 分支，零网络零 LLM。

锁定口径：
- _walk_symbols：FunctionDeclaration / ClassDeclaration /
  InterfaceDeclaration 的 name 字段 + VariableDeclaration 内
  VariableDeclarator 子节点的 name 字段；None tree 返回空集。
- extract_symbols：tree 非 None 时走 _walk_symbols（精确 AST 口径），
  tree 为 None 时回退词法层。
- extract_call_graph：顶层函数 / 类方法体内直接调用的标识符边；
  自调用（callee == caller）不进边；非 identifier 的 callee 跳过；
  tree 为 None 时回退词法层。
- check_naming_contract：原符号 − 补丁符号 = 被删符号集。
- register_tree_sitter_backend：is_available()=True 时注册成功
  （language_backend.get_backend("typescript") 指向 tree-sitter 后端）；
  is_available()=False 时 no-op（注册表保持词法层后端，幂等不抛错）。
"""

from __future__ import annotations

from typing import Any


class FakeNode:
    """模拟 tree-sitter 节点（type / children / 字段名 / 文本）。"""

    def __init__(
        self,
        node_type: str,
        children: list[FakeNode] | None = None,
        text: str = "",
        fields: dict[str, FakeNode] | None = None,
    ) -> None:
        self.type = node_type
        self.children = children or []
        self._text = text.encode("utf-8")
        self._fields = fields or {}

    @property
    def text(self) -> bytes:
        return self._text

    def child_by_field_name(self, name: str) -> FakeNode | None:
        return self._fields.get(name)


class FakeTree:
    """模拟 tree-sitter 解析结果（root_node）。"""

    def __init__(self, root: FakeNode) -> None:
        self.root_node = root


def _make_backend_with_tree(tree: Any) -> Any:
    """构造 TypeScriptTreeSitterBackend，_parse 恒返回给定 fake tree。

    直接覆盖实例的 _parse 方法（闭包恒返回注入 tree）——精确 AST 路径
    （_walk_symbols / _collect_calls / tree 非 None 分支）被走通，零真实解析器。
    """
    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()
    b._parse = lambda _code: tree
    return b


# ─── _walk_symbols 精确 AST 路径 ─────────────────────────────────────────────


def test_walk_symbols_collects_top_level_declarations() -> None:
    """Function/Class/Interface/VariableDeclaration 顶层符号提取。"""
    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()
    root = FakeNode(
        "Program",
        children=[
            FakeNode("FunctionDeclaration", fields={"name": FakeNode("identifier", text="foo")}),
            FakeNode("ClassDeclaration", fields={"name": FakeNode("identifier", text="Bar")}),
            FakeNode("InterfaceDeclaration", fields={"name": FakeNode("identifier", text="Baz")}),
            FakeNode(
                "VariableDeclaration",
                children=[
                    FakeNode("VariableDeclarator", fields={"name": FakeNode("identifier", text="QUX")}),
                    FakeNode("VariableDeclarator", fields={"name": FakeNode("identifier", text="QUUX")}),
                ],
            ),
            # 非声明节点（语句等）不进符号表
            FakeNode("ExpressionStatement", text="console.log(1)"),
        ],
    )
    assert b._walk_symbols(FakeTree(root)) == {"foo", "Bar", "Baz", "QUX", "QUUX"}


def test_walk_symbols_skips_declaration_without_name_field() -> None:
    """FunctionDeclaration 缺 name 字段时跳过（child_by_field_name=None）。"""
    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()
    root = FakeNode(
        "Program",
        children=[
            FakeNode("FunctionDeclaration"),  # 无 name 字段
            FakeNode("VariableDeclaration", children=[FakeNode("VariableDeclarator")]),  # 无名 declarator
            FakeNode("ClassDeclaration", fields={"name": FakeNode("identifier", text="Keep")}),
        ],
    )
    assert b._walk_symbols(FakeTree(root)) == {"Keep"}


def test_walk_symbols_none_tree_returns_empty() -> None:
    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()
    assert b._walk_symbols(None) == set()


# ─── extract_symbols 精确 AST 路径（tree 非 None）────────────────────────────


def test_extract_symbols_uses_ast_when_tree_available() -> None:
    """tree 非 None 时 extract_symbols 走 _walk_symbols（非词法层）。"""
    b = _make_backend_with_tree(
        FakeTree(
            FakeNode(
                "Program",
                children=[
                    FakeNode("FunctionDeclaration", fields={"name": FakeNode("identifier", text="tsSymbol")}),
                ],
            )
        )
    )
    out = b.extract_symbols("function tsSymbol() {}")
    assert out == {"tsSymbol"}


def test_extract_symbols_falls_back_when_tree_is_none() -> None:
    """_parse 返回 None 时 extract_symbols 回退词法层。"""
    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()
    b._parser = None
    b._parse = lambda _c: None
    out = b.extract_symbols("function lexicalSym() {}\nconst lexConst = 1\n")
    # 词法层口径：提取 function / const 标识符
    assert "lexicalSym" in out
    assert "lexConst" in out


# ─── extract_call_graph 精确 AST 路径 ────────────────────────────────────────


def _callgraph_tree_with_calls() -> FakeTree:
    """构造：函数 a 调用 b（identifier callee）+ 调用 self.x（非 identifier 跳过）
    + 自调用 a（callee==caller 不进边）+ 顶层裸调用 c（caller=None 跳过）。

    2026-10-02 审查 P1 修复后口径：_collect_calls 对 FunctionDeclaration /
    ClassMethod 节点**无论 caller 是否已存在**均按 name 字段刷新 caller 并
    遍历其子节点（此前 `caller and` 限定使顶层函数体调用全丢——顶层 a 调 b
    时 a 是顶层 FunctionDeclaration，进入 a 时 caller 仍 None，b 的调用边被
    `and caller` 丢弃）。现顶层与嵌套体同口径，故 a 可作为顶层 Function
    Declaration 直接产生 (a→b) 边。
    """
    return FakeTree(
        FakeNode(
            "Program",
            children=[
                FakeNode(
                    "FunctionDeclaration",
                    fields={"name": FakeNode("identifier", text="a")},
                    children=[
                        # a 调 b：identifier callee（caller="a"）
                        FakeNode(
                            "CallExpression",
                            fields={"function": FakeNode("identifier", text="b")},
                        ),
                        # a 调 self.b（member expression callee，非 identifier → 跳过）
                        FakeNode(
                            "CallExpression",
                            fields={"function": FakeNode("member_expression", text="self.b")},
                        ),
                        # 自调用 a（callee==caller → 不进边）
                        FakeNode(
                            "CallExpression",
                            fields={"function": FakeNode("identifier", text="a")},
                        ),
                    ],
                ),
                FakeNode(
                    "ClassDeclaration",
                    fields={"name": FakeNode("identifier", text="C")},
                    children=[
                        FakeNode(
                            "ClassMethod",
                            fields={"name": FakeNode("identifier", text="m")},
                            children=[
                                # m 调 d（caller="m"）
                                FakeNode(
                                    "CallExpression",
                                    fields={"function": FakeNode("identifier", text="d")},
                                ),
                            ],
                        ),
                    ],
                ),
                # 顶层裸调用 c：caller=None → 不进边
                FakeNode("CallExpression", fields={"function": FakeNode("identifier", text="c")}),
            ],
        )
    )


def test_extract_call_graph_edges_from_ast() -> None:
    b = _make_backend_with_tree(_callgraph_tree_with_calls())
    edges = b.extract_call_graph("")
    pairs = {(c, f) for c, f in edges}
    assert ("a", "b") in pairs
    assert ("m", "d") in pairs
    # 自调用不进边
    assert ("a", "a") not in pairs
    # 非 identifier callee 跳过
    assert not any(f == "self.b" for _, f in edges)
    # 顶层裸调用（caller=None）跳过
    assert not any(f == "c" for _, f in edges)


def test_extract_call_graph_edges_no_callers_yields_empty() -> None:
    """纯常量声明（无函数 / 方法体）时精确 AST 路径返回空边集。"""
    tree = FakeTree(
        FakeNode(
            "Program",
            children=[
                FakeNode("VariableDeclaration", children=[FakeNode("VariableDeclarator", fields={"name": FakeNode("identifier", text="X")})]),
            ],
        )
    )
    b = _make_backend_with_tree(tree)
    assert b.extract_call_graph("") == []


def test_extract_call_graph_call_expression_stops_recursion() -> None:
    """CallExpression 节点不再递归（避免把参数内的调用重复计入 caller 体）。

    构造：a（顶层 FunctionDeclaration）调 fn(g())——若 CallExpression 继续
    递归进参数，g 的调用边 (a→g) 会被误计；保守口径 CallExpression 命中即
    return（不递归进参数）。2026-10-02 P1 修复后顶层 a 的调用边正常归属
    （caller="a"）。
    """
    tree = FakeTree(
        FakeNode(
            "Program",
            children=[
                FakeNode(
                    "FunctionDeclaration",
                    fields={"name": FakeNode("identifier", text="a")},
                    children=[
                        # a 调 fn(g())：外层 CallExpression 的 function=identifier fn，
                        # 内层 g() 是 fn 的参数（嵌套 CallExpression）——
                        # 外层命中后 return 不递归，g 不进 a 的调用边。
                        FakeNode(
                            "CallExpression",
                            fields={"function": FakeNode("identifier", text="fn")},
                            children=[
                                FakeNode(
                                    "CallExpression",
                                    fields={"function": FakeNode("identifier", text="g")},
                                )
                            ],
                        ),
                    ],
                ),
            ],
        )
    )
    b = _make_backend_with_tree(tree)
    edges = b.extract_call_graph("")
    pairs = {(c, f) for c, f in edges}
    assert ("a", "fn") in pairs
    assert ("a", "g") not in pairs


def test_extract_call_graph_top_level_function_call_attribution() -> None:
    """2026-10-02 审查 P1 回归：顶层函数的调用边正常归属（此前全丢）。

    历史缺陷：_collect_calls 的 `caller and node.type in (...)` 条件使
    顶层（caller=None）的 FunctionDeclaration 不刷新 caller，顶层函数体
    内的调用边全丢（a 调 b 时 a 是顶层函数，b 的调用边因 `and caller`
    被丢弃）。现去掉 `caller and` 限定，顶层与嵌套体同口径。
    """
    tree = FakeTree(
        FakeNode(
            "Program",
            children=[
                FakeNode(
                    "FunctionDeclaration",
                    fields={"name": FakeNode("identifier", text="a")},
                    children=[
                        FakeNode("CallExpression", fields={"function": FakeNode("identifier", text="b")}),
                    ],
                ),
            ],
        )
    )
    b = _make_backend_with_tree(tree)
    edges = b.extract_call_graph("")
    assert ("a", "b") in {(c, f) for c, f in edges}


def test_extract_call_graph_falls_back_when_tree_is_none() -> None:
    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()
    b._parser = None
    b._parse = lambda _c: None
    out = b.extract_call_graph("function p() { q(); }\n")
    # 词法层回退：p → q 边
    pairs = {(c, f) for c, f in out}
    assert ("p", "q") in pairs


# ─── check_naming_contract 差集口径 ──────────────────────────────────────────


def test_check_naming_contract_reports_removed_symbols() -> None:
    b = _two_version_backend()
    original = "function keep() {}\nfunction drop() {}\n"
    patched = "function keep() {}\n"
    removed = b.check_naming_contract(original, patched)
    assert "drop" in removed
    assert "keep" not in removed


def _two_version_backend() -> Any:
    """构造后端：_parse 按输入代码用正则提取顶层 function 名构造 tree。"""
    import re

    import src.tools.tree_sitter_backend as tsb

    b = tsb.TypeScriptTreeSitterBackend()

    def _fake_parse(code: str) -> Any:
        names = re.findall(r"function (\w+)", code)
        root = FakeNode(
            "Program",
            children=[
                FakeNode("FunctionDeclaration", fields={"name": FakeNode("identifier", text=n)}) for n in names
            ],
        )
        return FakeTree(root)

    b._parser = object()
    b._parse = _fake_parse
    return b


# ─── register_tree_sitter_backend 注册成功 / no-op 路径 ─────────────────────


def test_register_noop_when_unavailable(monkeypatch) -> None:
    """is_available()=False 时 register no-op（注册表保持词法层，幂等不抛错）。"""
    import src.tools.language_backend as lb
    import src.tools.tree_sitter_backend as tsb

    monkeypatch.setattr(tsb, "is_tree_sitter_available", lambda: False)
    tsb.register_tree_sitter_backend()  # 不抛错
    tsb.register_tree_sitter_backend()  # 幂等
    # 注册表未被覆盖为 tree-sitter 后端（仍为词法层 TypeScriptBackend）
    be = lb.get_language_backend("typescript")
    assert not isinstance(be, tsb.TypeScriptTreeSitterBackend)


def test_register_success_when_available(monkeypatch) -> None:
    """is_available()=True 时 register_backend 成功（_BACKENDS["typescript"] 指向 tree-sitter 后端）。

    注意：register_backend 直接写 _BACKENDS 注册表（不校验开关）；
    get_language_backend 经 backend_enabled（AITESTER_ENABLE_TYPESCRIPT_BACKEND
    默认 false）过滤——本用例验证"注册表层面"的注册成功（register 的核心
    契约），不查 get_language_backend（后者还受 env 开关控制，默认关）。
    monkeypatch 还原 is_tree_sitter_available；_BACKENDS 写入用 finally 恢复。
    """
    import src.tools.language_backend as lb
    import src.tools.tree_sitter_backend as tsb

    saved = lb._BACKENDS.get("typescript")
    monkeypatch.setattr(tsb, "is_tree_sitter_available", lambda: True)
    try:
        tsb.register_tree_sitter_backend()
        assert isinstance(lb._BACKENDS["typescript"], tsb.TypeScriptTreeSitterBackend)
    finally:
        if saved is not None:
            lb._BACKENDS["typescript"] = saved


# ─── classify_error 透传词法层 ───────────────────────────────────────────────


def test_classify_error_delegates_to_lexical() -> None:
    import src.tools.tree_sitter_backend as tsb
    from src.tools.language_backend import TypeScriptBackend

    b = tsb.TypeScriptTreeSitterBackend()
    ref = TypeScriptBackend()
    for text in ("TypeError: x is not a function", "SyntaxError: Unexpected token", ""):
        assert b.classify_error(text) == ref.classify_error(text)
