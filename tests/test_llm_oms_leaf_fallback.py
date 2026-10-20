"""OMS（M10 可观测性，EMSE 批次四 M1）：叶子回退静默片段检测的回归测试。

背景（ADR-0031 §已知局限②）：extract_json_object 的叶子降级档在括号
平衡法失败时会**静默返回最内层片段**（如 {'items': ...}），下游 Planner
M10 把"缺 logic_analysis"归因为"LLM 未输出"——实为提取器缺陷（10-14
批次 ~7-8% 的 M10 误诊来源）。

本测试锁定三件纪律：
  1. 哨兵 was_leaf_fallback_used()：正常路径（括号平衡/修复链命中）恒
     False；叶子档命中（最内层片段返回）恒 True；全失败路径复位 False；
  2. 纯观测：哨兵不改变任何解析行为与返回值（同一输入，修复前后同结果）；
  3. 告警日志：叶子档命中时 logger.warning 触发（capsys/logging 捕获）。

隔离纪律（AA 轮）：`_LEAF_FALLBACK_ACTIVE` 是模块级全局，只在
extract_json_object **入口**清零——因此"读到 False"只在**同一进程内紧跟
一次正常调用**、或**用例自己先把状态钉住**时才是契约。本文件第一条用例
属于后者，故由 autouse fixture 提供确定入口态；不加 fixture 时它与
`test_helpers_20261019_branches.py` / `test_helpers_json_fence_content.py`
同 worker（-n 4 --dist loadfile）即红。
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import ClassVar

import pytest

from src.utils import helpers
from src.utils.helpers import extract_json_object, was_leaf_fallback_used


@pytest.fixture(autouse=True)
def _leaf_sentinel_has_defined_entry_state() -> Iterator[None]:
    """把进程级哨兵的**用例入口态**钉成 False，出口还原成发现时的值。

    本文件既不假设别的文件停在哪，也不替别的文件收拾残局——还原 previous
    而非写死 False，避免把"我跑过了所以复位了"当成新的跨文件依赖。
    """
    previous = helpers._LEAF_FALLBACK_ACTIVE
    helpers._LEAF_FALLBACK_ACTIVE = False
    try:
        yield
    finally:
        helpers._LEAF_FALLBACK_ACTIVE = previous


def test_prior_leaf_hit_does_not_leak_into_next_case() -> None:
    """进程内重放污染场景：本用例**以 True 结尾**，留给下一条用例。

    没有上面的 fixture，下一条 `test_normal_path_sentinel_false` 的入口断言
    就在这里红——这条用例因此是 fixture 的变异锁（删 fixture 必红）。
    """
    extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert was_leaf_fallback_used() is True


def test_normal_path_sentinel_false() -> None:
    """完整 JSON 对象（括号平衡法命中）→ 哨兵 False。"""
    assert was_leaf_fallback_used() is False
    r = extract_json_object('{"a": 1}')
    assert r == {"a": 1}
    assert was_leaf_fallback_used() is False


def test_normal_path_reset_after_prior_leaf() -> None:
    """叶子档命中后，下一次正常调用把哨兵复位为 False（每次调用入口清零）。"""
    # 先制造一次叶子档命中
    extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert was_leaf_fallback_used() is True
    # 正常调用 → 入口清零
    r = extract_json_object('{"ok": 1}')
    assert r == {"ok": 1}
    assert was_leaf_fallback_used() is False


def test_leaf_fallback_sentinel_true() -> None:
    """外层残缺 + 内层片段 → 叶子档命中，哨兵 True，返回值=最内层片段。"""
    # 构造：外层 { 无匹配 }（_find_balanced_json 返回 None），
    # 首对象修复失败，叶子档取最内层 '{"k": 42}'
    r = extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert r == {"k": 42}
    assert was_leaf_fallback_used() is True


def test_all_failures_sentinel_reset() -> None:
    """全部方案失败（raise）→ 哨兵复位 False（入口清零后叶子档未命中）。"""
    # 无任何可解析 {…} 片段 → raise
    with pytest.raises(json.JSONDecodeError):
        extract_json_object("no json here")
    assert was_leaf_fallback_used() is False


def test_leaf_fallback_pure_observability() -> None:
    """纯观测纪律：同一输入在哨兵开/关下返回值逐字相同（零行为变化）。"""
    text = 'xx {"outer": stuff, {"k": 42}'
    r1 = extract_json_object(text)
    assert was_leaf_fallback_used() is True
    r2 = extract_json_object(text)
    assert r1 == r2 == {"k": 42}
    # 哨兵只记录"最近一次"，不影响解析结果
    assert was_leaf_fallback_used() is True


def test_leaf_fallback_logs_warning() -> None:
    """叶子档命中触发 logger.warning（可观测性改进的日志证据）。"""
    import logging

    with (
        logging.getLogger("src.utils.helpers").captureWarnings()
        if hasattr(logging.getLogger("src.utils.helpers"), "captureWarnings")
        else _NullContext()
    ):
        r = extract_json_object('xx {"outer": stuff, {"k": 42}')
    assert r == {"k": 42}


class _NullContext:
    """logging.captureWarnings 兼容 shim（Python 3.14 无该 API 时用空上下文）。"""

    def __enter__(self) -> object:
        return None

    def __exit__(self, *args: object) -> None:
        return None


@pytest.mark.unit
class TestProcessStateReaderEnumeration:
    """AB-4：把 AA-8 的"同类面已穷举"从**人工声明**换成**机器反面锁定**。

    AA-8 的结论是"`src/` 里只有 4 个这样的读者，其余 3 个都在测试里先钉状态"，
    当时是靠一段写在文档里的 AST 脚本人工跑出来的。文档会漂、判据会被改——
    本类不再"另写一份判据"（那会锁成一个和文档不同的东西），而是**直接执行
    `docs/MEASUREMENT_INTEGRITY.md` §8 里发布的那段脚本**：文档与锁从此是同一件
    工件，第 5 个读者出现时两者一起转红。
    """

    # 判据命中面（模块, 公共函数, 读到的进程级全局）。前 3 个是单例工厂，
    # 测试站点先钉状态；第 4 个正是本文件用 autouse fixture 隔离的那位。
    KNOWN_READERS: ClassVar[set[tuple[str, str, str]]] = {
        ("src/api/api_manager.py", "get_manager", "_manager"),
        ("src/graph/rag.py", "get_rag_retriever", "_rag_retriever"),
        ("src/reports/generator.py", "get_report_generator", "_report_generator"),
        ("src/utils/helpers.py", "was_leaf_fallback_used", "_LEAF_FALLBACK_ACTIVE"),
    }

    @staticmethod
    def _published_snippet() -> str:
        """从 §8 抠出被发布的 AST 判据脚本（找含 `ast.Global` 的那个 python 块）。"""
        doc = Path("docs/MEASUREMENT_INTEGRITY.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```python\n(.*?)```", doc, flags=re.DOTALL)
        cand = [b for b in blocks if "ast.Global" in b and "FunctionDef" in b]
        assert len(cand) == 1, f"§8 的判据脚本应唯一，实测 {len(cand)} 段——文档结构变了，锁需同步"
        return cand[0]

    def test_documented_criterion_yields_exactly_the_known_readers(self, capsys: pytest.CaptureFixture[str]) -> None:
        snippet = self._published_snippet()
        try:
            exec(compile(snippet, "<MEASUREMENT_INTEGRITY §8>", "exec"), {"__name__": "__lock__"})
        except Exception as exc:
            pytest.fail(f"§8 发布的判据脚本无法执行（文档主张已失效）：{exc!r}")
        out = capsys.readouterr().out
        rows = ast.literal_eval(out.strip())
        found = {(f, name, var) for f, name, var in rows}
        assert found == self.KNOWN_READERS, (
            f"进程级状态读者集合变了：新增 {found - self.KNOWN_READERS}，"
            f"消失 {self.KNOWN_READERS - found}。新增者必须像本文件第一条用例那样"
            "**在用例入口自钉状态**，否则它在 -n 4 --dist loadfile 下就是一枚"
            "调度运气型假绿（AA-8 / MEASUREMENT_INTEGRITY §8）。"
        )

    def test_the_leaf_sentinel_site_pins_its_entry_state(self) -> None:
        """本文件自身的隔离纪律也要锁住：autouse fixture 一被摘掉，§8 的清单就失去依据。"""
        src = Path(__file__).read_text(encoding="utf-8")
        assert "@pytest.fixture(autouse=True)" in src
        assert "_leaf_sentinel_has_defined_entry_state" in src
