"""J-4（2026-10-17）：`_cross_file_analyzer_node` 依赖边来源与调用链上下文补测。

纪律：零 LLM、零网络、零文件写入——节点本身是纯静态 AST 分析，测试只需
构造 state + （必要时）替 `analyze_multi_entry_deps` 造边。

覆盖口径（coverage.xml 里 nodes.py 1743-1744 / 1766 / 1769 / 1771 / 1777）：
    - AST 边 vs benchmark 层预置边的优先级（含"预置边不被加 source 标记"）；
    - P0 1.1 聚焦上下文的三条腿：命中写入 / 源模块未载入跳过 / 符号解析不到跳过。
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.graph import nodes
from src.tools.cross_file import CrossFileDependency

# 自 import + 自定义：entry 模块同时是"调用方"和"被调方源码所在"，
# 这是节点一期口径下唯一能靠真实 AST 分析出边（见 nodes.py 1700-1705 注释）。
_FROM_IMPORT_WITH_DEF = (
    "from calculator import add\n\n\ndef add(a, b):\n    return a + b\n\n\ndef f():\n    return add(1, 2)\n"
)
# 自 import 但符号未在同段源码定义 → extract_function_context 解析不到
_FROM_IMPORT_WITHOUT_DEF = "from calculator import add\n\n\ndef f():\n    return add(1, 2)\n"

_PRESET_EDGE: dict[str, Any] = {
    "source_module": "module_a",
    "target_module": "calculator",
    "symbol": "add",
    "call_line": 12,
    "context": "total = add(1, 2)",
}


def _state(target_code: str, **extra: Any) -> dict[str, Any]:
    state = {
        "target_file": "examples/calculator.py",
        "module_name": "calculator",
        "target_code": target_code,
        "iteration": 0,
    }
    state.update(extra)
    return state


def _run(state: dict[str, Any]) -> dict[str, Any]:
    with patch.object(nodes, "_trace_node"):
        return nodes._cross_file_analyzer_node(state)  # type: ignore[arg-type]


@pytest.mark.unit
class TestDependencyEdgeProvenance:
    """AST 边 / 预置边两条写侧口径，以及它们的优先级。"""

    def test_ast_edges_are_marked_and_win_over_preset(self):
        """AST 命中 → 采用 AST 结果并打 ast_derived 标；预置边不参与。"""
        out = _run(_state(_FROM_IMPORT_WITH_DEF, cross_file_deps=[dict(_PRESET_EDGE)]))
        edges = out["cross_file_deps"]
        assert [e["source"] for e in edges] == ["ast_derived"]
        assert edges[0]["target_module"] == "calculator"
        assert edges[0]["symbol"] == "add"

    def test_zero_ast_edges_keep_preset_edges_verbatim(self):
        """nodes.py 1743-1748：AST 单视角 0 条边 + 预置边非空 → 原样保留。

        判别性断言：保留的预置边**不带** "source" 标记——它们来自 benchmark 层
        dep_chain（_write_cross_file_state），与 AST 推导边必须在数据上可区分
        （O11：跨文件 A/B 结论可外推的前提）。
        """
        with patch.object(nodes, "analyze_multi_entry_deps", return_value=[]):
            out = _run(_state(_FROM_IMPORT_WITHOUT_DEF, cross_file_deps=[dict(_PRESET_EDGE)]))
        assert out["cross_file_deps"] == [_PRESET_EDGE]
        assert "source" not in out["cross_file_deps"][0]
        assert out["cross_file_plan"] is None

    def test_no_ast_no_preset_is_empty_list_not_missing_key(self):
        """两条腿都不命中：cross_file_deps 写空列表（而非缺键）——下游按固定 key 取值。"""
        with patch.object(nodes, "analyze_multi_entry_deps", return_value=[]):
            out = _run(_state(_FROM_IMPORT_WITHOUT_DEF))
        assert out["cross_file_deps"] == []
        assert "cross_file_contexts" not in out

    def test_blank_entry_module_is_not_analyzed(self):
        """nodes.py:1720 的 False 腿：module_name 与 target_file 都空 → 无入口模块。

        入口名为空时不把 `""` 当模块名塞进 source_files/entry_modules——否则
        分析器会产出一条 target_module 为空串的伪依赖边，下游（特异性门的
        task_metadata、M1 委托层物化）都无法据此定位模块。锁的是"空入口 =
        零分析 = 空列表"而不是崩。
        """
        spy = MagicMock(return_value=[])
        with patch.object(nodes, "analyze_multi_entry_deps", spy):
            out = _run(_state(_FROM_IMPORT_WITH_DEF, module_name="", target_file=""))
        assert spy.call_args.args == ([], {})
        assert out["cross_file_deps"] == []


@pytest.mark.unit
class TestFocusedContextLegs:
    """P0 1.1 跨文件调用链上下文的三条腿。"""

    def test_symbol_resolvable_in_entry_source_writes_context(self):
        """nodes.py 1769/1771/1777：符号在同段源码可解析 → 写 cross_file_contexts。"""
        out = _run(_state(_FROM_IMPORT_WITH_DEF))
        contexts = out["cross_file_contexts"]
        assert list(contexts) == ["calculator"]
        assert "def add(a, b):" in contexts["calculator"]

    def test_target_module_not_loaded_is_skipped(self):
        """nodes.py 1766：dep.target_module 不在 source_files（一期仅 entry）→ 跳过。

        一期口径的已知缺口：被依赖模块源码未载入，聚焦上下文只对 entry 模块生效。
        这里必须造一条"外部模块"的边（真实分析器在单 source_files 下产不出），
        锁住"跳过而不是崩"的语义。
        """
        foreign = CrossFileDependency(
            source_module="calculator", target_module="other_mod", symbol="helper", call_line=4
        )
        with patch.object(nodes, "analyze_multi_entry_deps", return_value=[foreign]):
            out = _run(_state(_FROM_IMPORT_WITHOUT_DEF))
        assert len(out["cross_file_deps"]) == 1
        assert "cross_file_contexts" not in out, "全部边都取不到源码却写入 key = 空上下文伪装成功"

    def test_unresolvable_symbol_writes_no_context(self):
        """nodes.py 1769 假腿：边命中但符号在同段源码解析不到 → 不写 cross_file_contexts。"""
        out = _run(_state(_FROM_IMPORT_WITHOUT_DEF))
        assert len(out["cross_file_deps"]) == 1
        assert "cross_file_contexts" not in out

    def test_two_edges_same_module_do_not_duplicate(self):
        """同一 target_module 多条边 → setdefault 语义：只留一份上下文。"""
        deps = [
            CrossFileDependency(source_module="calculator", target_module="calculator", symbol="add", call_line=9),
            CrossFileDependency(source_module="calculator", target_module="calculator", symbol="add", call_line=14),
        ]
        with patch.object(nodes, "analyze_multi_entry_deps", return_value=deps):
            out = _run(_state(_FROM_IMPORT_WITH_DEF))
        assert list(out["cross_file_contexts"]) == ["calculator"]
        assert len(out["cross_file_deps"]) == 2
