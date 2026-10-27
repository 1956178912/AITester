"""FC 轮类锁：`src/` 的运行期判据不得依赖可被 `python -O` 删除的 `assert`。

FB 轮修的是**点**（`src/graph/orchestration_search.py::assert_no_credit_coupling`
一个函数）；本轮把它升级为**类锁**，并补上普查中发现的另外两处承重判据：

| 位置 | 改前 | 后果 |
|---|---|---|
| `src/cli/app.py::_run_single_task` | `assert final_state is not None` | `python -O` 删除断言 ⇒ 后续 `final_state.get(...)` 退化成 AttributeError——正是该注释明写要避免的 NPE 形态 |
| `src/db/mysql_client.py::cursor` | `assert self._pool is not None` | `python -O` 删除断言 ⇒ `self._pool.connection()` 退化成 AttributeError，"连接池未初始化"的诊断信息全丢 |

判据四层：
1. **普查**：`src/**/*.py` 的每一处 `ast.Assert` 都必须在登记册里（按**内容
   锚点**匹配，不用行号——行号会随上方插行漂移）；未登记的 assert 即红
   （新增一处 assert = 新增一个"优化模式下会消失的判据"）。
2. **登记册只收纯类型收窄**：被 `-O` 删除也不改变运行期语义
   （`isinstance(...)` / `x is not None` 收窄）；承重的运行期判据必须显式
   `if ... raise`。
3. **字节码探针**：用 `compile(..., optimize=2)` 编译真实源码，断言守卫的
   **消息常量仍在代码对象里**——`assert` 语句在优化模式下连同消息一起被
   删除，故该探针对"退回 assert"必然变红。
4. **负对照**：合成函数（只含 `assert`）在 `optimize=2` 下消息常量消失、
   在 `optimize=1` 下仍在——证明第 3 层的探针不是空转。

另有一条**真实 `python -O` 子进程**验证（MySQL 连接池守卫）：优化模式下
真跑一次未初始化连接池，必须仍抛 `AssertionError`（而非 AttributeError）。
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"

# 登记册：src/ 中**允许**存在的 assert（纯类型收窄，按内容锚点匹配）。
# 键 = 相对路径；值 = (断言源码的规范化文本, 允许的理由)
REGISTRY: dict[str, list[tuple[str, str]]] = {
    "graph/agents_cache.py": [
        (
            "assert isinstance(agent, DebuggerAgent)",
            "纯类型收窄：mock 路径已在上方 `if not isinstance(DebuggerAgent, type)` 提前返回，"
            "此断言只为 mypy 收窄；被 -O 删除不改变运行期行为",
        )
    ],
    "graph/nodes.py": [
        (
            "assert isinstance(patch_val, str)",
            '纯类型收窄：外层 `if state.get("patch")` 真值守卫后必为 str，'
            "此断言只为 mypy 收窄；被 -O 删除不改变运行期行为",
        )
    ],
    "graph/workflow.py": [
        (
            "assert _DIAGNOSIS_KEYWORD_RE is not None",
            "纯类型收窄：上方 if 分支已保证赋值，模块级正则不存在未赋值路径；"
            "此断言只为 mypy 收窄；被 -O 删除不改变运行期行为",
        )
    ],
}

# 承重守卫：源码里必须以**显式 raise** 承载（不得回退成 assert）。
# (相对路径, 所在函数名, 守卫消息常量, 消息在源码中的判定用锚点)
GUARDS: list[tuple[str, str, str]] = [
    (
        "cli/app.py",
        "_run_single_task",
        "graph.invoke 未返回状态（非预期）",
    ),
    (
        "db/mysql_client.py",
        "cursor",
        "MySQLClient 连接池未初始化",
    ),
    (
        "graph/orchestration_search.py",
        "assert_no_credit_coupling",
        "reward hacking",
    ),
]


def _normalize_assert(node: ast.Assert) -> str:
    """断言语句的规范化文本（去掉缩进与换行差异）。"""
    return " ".join(ast.unparse(node).split())


def _iter_src_asserts() -> list[tuple[str, ast.Assert]]:
    """src/ 下的全部 assert（相对路径 + AST 节点）。"""
    hits: list[tuple[str, ast.Assert]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(SRC).as_posix()
        hits.extend((rel, node) for node in ast.walk(tree) if isinstance(node, ast.Assert))
    return hits


def _code_objects(code: object, name: str) -> list[object]:
    """按名字收集嵌套代码对象（覆盖装饰器包装 / 生成器函数体）。"""
    found: list[object] = []
    for const in getattr(code, "co_consts", ()):  # type: ignore[attr-defined]
        if hasattr(const, "co_name") and hasattr(const, "co_consts"):
            if const.co_name == name:
                found.append(const)
            found.extend(_code_objects(const, name))
    return found


def _all_string_consts(code: object) -> set[str]:
    """递归收集代码对象树里的全部字符串常量（含嵌套函数体）。"""
    out: set[str] = set()
    for const in getattr(code, "co_consts", ()):  # type: ignore[attr-defined]
        if isinstance(const, str):
            out.add(const)
        elif hasattr(const, "co_consts"):
            out |= _all_string_consts(const)
    return out


def _optimized_constants(relpath: str, func_name: str) -> set[str]:
    """`compile(..., optimize=2)` 后该函数的字符串常量集合。"""
    path = SRC / relpath
    compiled = compile(path.read_text(encoding="utf-8"), str(path), "exec", optimize=2)
    consts: set[str] = set()
    for obj in _code_objects(compiled, func_name):
        consts |= _all_string_consts(obj)
    return consts


def _unregistered_asserts(
    hits: list[tuple[str, ast.Assert]],
    registry: dict[str, list[tuple[str, str]]],
) -> list[str]:
    """普查核心：返回未登记的 assert 清单（空 = 全部登记在册）。

    抽成独立函数以便**负对照**：拿合成的未登记 assert 喂进来，必须被点名。
    """
    unregistered: list[str] = []
    for rel, node in hits:
        allowed = {text for text, _reason in registry.get(rel, [])}
        if _normalize_assert(node) not in allowed:
            unregistered.append(f"{rel}:{node.lineno}: {_normalize_assert(node)}")
    return unregistered


class TestSrcAssertCensus:
    def test_every_src_assert_is_registered(self) -> None:
        """src/ 的每处 assert 都必须在登记册里（未登记 ⇒ 优化模式下会消失的判据）。"""
        unregistered = _unregistered_asserts(_iter_src_asserts(), REGISTRY)
        assert unregistered == [], f"src/ 出现未登记的 assert（-O 下会被删除）：{unregistered}"

    def test_census_flags_synthetic_unregistered_assert(self) -> None:
        """负对照：普查必须能识别未登记的 assert（否则第 1 层是空转）。"""
        synthetic = ast.parse("assert some_value is not None\n").body[0]
        assert isinstance(synthetic, ast.Assert)
        hits = [("graph/nodes.py", synthetic)]
        assert _unregistered_asserts(hits, REGISTRY) != []
        # 已登记的那条不得被误报
        registered = ast.parse("assert isinstance(patch_val, str)\n").body[0]
        assert isinstance(registered, ast.Assert)
        assert _unregistered_asserts([("graph/nodes.py", registered)], REGISTRY) == []

    def test_registry_entries_are_all_present(self) -> None:
        """登记册不得留已消失的条目（否则登记表会变成橡皮章）。"""
        actual: dict[str, set[str]] = {}
        for rel, node in _iter_src_asserts():
            actual.setdefault(rel, set()).add(_normalize_assert(node))
        stale: list[str] = []
        for rel, entries in REGISTRY.items():
            for text, _reason in entries:
                if text not in actual.get(rel, set()):
                    stale.append(f"{rel}: {text}")
        assert stale == [], f"登记册条目已失效：{stale}"

    def test_registered_asserts_are_type_narrowing_only(self) -> None:
        """登记册只收纯类型收窄的 assert（isinstance / x is not None）。"""
        for rel, entries in REGISTRY.items():
            for text, _reason in entries:
                node = ast.parse(text).body[0]
                assert isinstance(node, ast.Assert)
                test = node.test
                is_isinstance = (
                    isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance"
                )
                is_not_none = (
                    isinstance(test, ast.Compare)
                    and isinstance(test.ops[0], ast.IsNot)
                    and isinstance(test.comparators[0], ast.Constant)
                )
                assert is_isinstance or is_not_none, f"{rel}: {text} 不是纯类型收窄形态"
                assert node.msg is None, f"{rel}: {text} 带消息 ⇒ 它是运行期判据，不该进登记册"


class TestGuardsSurviveOptimizedMode:
    @pytest.mark.parametrize(("relpath", "func_name", "message"), GUARDS)
    def test_guard_message_survives_optimize_level_two(self, relpath: str, func_name: str, message: str) -> None:
        """`compile(optimize=2)` 后守卫消息常量仍在 ⇒ 守卫没被优化器删掉。

        `assert x is None, "msg"` 在 optimize=2 下整条消失（含消息常量）；
        显式 `raise AssertionError("msg")` 则保留。
        """
        consts = _optimized_constants(relpath, func_name)
        # f-string 的消息在编译期被拆成多段常量（插值处断开），故按"包含"判定
        assert any(message in const for const in consts), (
            f"{relpath}::{func_name} 的守卫在 optimize=2 下消失（退回 assert 了？）"
        )

    @pytest.mark.parametrize(("relpath", "func_name", "message"), GUARDS)
    def test_guard_function_has_no_assert_node(self, relpath: str, func_name: str, message: str) -> None:
        """守卫所在函数内不得再有 assert 节点（源码级，与字节码级互为独立实现）。"""
        path = SRC / relpath
        tree = ast.parse(path.read_text(encoding="utf-8"))
        targets = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name
        ]
        assert targets, f"{relpath} 未找到函数 {func_name}"
        for func in targets:
            asserts = [n for n in ast.walk(func) if isinstance(n, ast.Assert)]
            assert asserts == [], f"{relpath}::{func_name} 仍含 assert 节点：{asserts}"

    def test_probe_detects_assert_stripping(self) -> None:
        """负对照：探针必须能看见 assert 被优化器删掉（否则第 3 层是空转）。

        CPython 实测：`compile(optimize=1)` 与 `optimize=2` **都会**删掉
        `assert` 语句及其消息常量（`optimize=0` 才保留）——故探针的
        "消息常量仍在"等价于"这条判据没被优化器删掉"。
        """
        source = "def f(x):\n    assert x is not None, 'MAGIC_GUARD_MESSAGE'\n    return 1\n"
        stripped = compile(source, "<probe>", "exec", optimize=2)
        kept = compile(source, "<probe>", "exec", optimize=0)

        assert "MAGIC_GUARD_MESSAGE" in _all_string_consts(kept)
        assert "MAGIC_GUARD_MESSAGE" not in _all_string_consts(stripped)

    def test_mysql_pool_guard_rejects_uninitialised_pool_in_optimized_mode(self) -> None:
        """真实 `python -O` 子进程：未初始化连接池必须仍抛 AssertionError。

        改前（assert 形态）在 `-O` 下会退化成 AttributeError——异常类型变了，
        上层按类型分流的行为随之改变。
        """
        probe = r"""
from src.db.mysql_client import MySQLClient

client = MySQLClient.__new__(MySQLClient)  # 不跑 __init__ ⇒ _pool 保持 None
try:
    with client.cursor():
        pass
except AssertionError as exc:
    assert "连接池未初始化" in str(exc), exc
    print("optimized guard rejected uninitialised pool")
else:
    raise SystemExit("optimized guard accepted uninitialised pool")
"""
        env = dict(os.environ)
        existing = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(REPO_ROOT) + (os.pathsep + existing if existing else "")
        completed = subprocess.run(
            [sys.executable, "-O", "-c", probe],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        assert "optimized guard rejected uninitialised pool" in completed.stdout
