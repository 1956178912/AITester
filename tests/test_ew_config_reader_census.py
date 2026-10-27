"""EW 轮锁：config.py 的公开键必须被真实消费面读取，cap 必须走到真实搜索构造。

缺陷（2026-10-27 普查，51 个公开键）：
- `ORCHESTRATION_SEARCH_MAX_UNMEASURABLE` 注释承诺「超过即 excluded_structurally」，
  但唯一构造点 `experiments/run_orchestration_search.py` 从不传该参数 ⇒ 构造默认 5
  恒生效，设置 env 不改变任何行为；
- `DOCKER_ENABLED` / `DOCKER_IMAGE`：真实开关是 `EXECUTOR_USE_DOCKER` /
  `EXECUTOR_DOCKER_IMAGE`，这两个名字在 src/experiments/scripts 零引用（幽灵键）；
- `DEFAULT_LLM_CONFIG`：纯死符号（零引用）。

判据三层：
1. 静态普查：config.py 每个公开键都必须在 src/experiments/scripts 中被引用——
   AST Name/Attribute 加**非 docstring** 字符串字面量（覆盖 `env_flag("X")` 与
   `getattr(_cfg, "X", ...)` 两种间接读法）；tests/ 不算消费方（测试会给死键背书）；
2. 负对照：普查必须能识别合成死键（否则第 1 层是空转）；
3. 行为锁：走真实 CLI 与真实 `OrchestrationSearch`（只桩掉数据集与单 cell 评估），
   config cap=2 时全不可测臂第 3 次后退出 UCB 池；cap=5 时不退出（边界对照）；
   `--max-unmeasurable` 覆盖 config。
"""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest

import config as config_module
from experiments import run_orchestration_search as driver
from src.graph.orchestration_search import Cell, CellResult

_ROOT = Path(__file__).resolve().parents[1]
_CONSUMER_GLOBS = ("src/**/*.py", "experiments/**/*.py", "scripts/**/*.py")
_PUBLIC_KEY = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _public_config_keys(source: str) -> set[str]:
    """config.py 模块级公开全大写赋值名（`__all__` 等私有名不收）。"""
    keys: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and _PUBLIC_KEY.match(target.id):
                keys.add(target.id)
    return keys


def _string_literals(tree: ast.AST) -> list[str]:
    """全部非 docstring 字符串字面量（docstring 里的键名不构成读取）。"""
    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", ())
        if (
            body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstring_nodes.add(id(body[0].value))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstring_nodes
    ]


def _referenced_names(sources: Iterable[str]) -> set[str]:
    """源码语料里被提及的名字（Name 读点 / 属性名 / 非 docstring 字符串）。"""
    referenced: set[str] = set()
    for source in sources:
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                referenced.add(node.id)
            elif isinstance(node, ast.Attribute):
                referenced.add(node.attr)
            elif isinstance(node, ast.ImportFrom):
                referenced.update(alias.name for alias in node.names)
        referenced.update(_string_literals(tree))
    return referenced


def _unread_keys(keys: Iterable[str], referenced: Iterable[str]) -> set[str]:
    """无任何消费面引用的公开键（空集 = 普查通过）。"""
    return set(keys) - set(referenced)


def _consumer_sources() -> list[str]:
    return [
        path.read_text(encoding="utf-8")
        for pattern in _CONSUMER_GLOBS
        for path in sorted(_ROOT.glob(pattern))
        if path.is_file()
    ]


class TestConfigReaderCensus:
    def test_every_public_config_key_is_read_by_a_consumer(self) -> None:
        """config.py 不得声明无人读取的公开键（当前 4 个：1 个该接线，3 个该删）。"""
        keys = _public_config_keys((_ROOT / "config.py").read_text(encoding="utf-8"))
        assert keys, "config.py 未解析出任何公开键——普查自身失效"
        assert _unread_keys(keys, _referenced_names(_consumer_sources())) == set()

    def test_census_flags_synthetic_dead_key(self) -> None:
        """负对照：普查必须同时识别字符串间接读法的活键与合成死键。"""
        sources = ['LIVE = getattr(cfg, "LIVE_KEY")\n', "OTHER = env_flag('OTHER_KEY')\n"]
        referenced = _referenced_names(sources)
        assert _unread_keys({"LIVE_KEY", "OTHER_KEY", "GHOST_KEY"}, referenced) == {"GHOST_KEY"}

    def test_census_accepts_plain_load_and_attribute_reads(self) -> None:
        """负对照：直接 import 读法与属性读法都要算作消费。"""
        sources = ["from config import PLAIN_KEY\n", "VALUE = cfg.ATTR_KEY\n"]
        assert _unread_keys({"PLAIN_KEY", "ATTR_KEY"}, _referenced_names(sources)) == set()


def _make_cells(n: int) -> list[Cell]:
    return [Cell(task_id=f"t{i:03d}", seed=42, task=None) for i in range(n)]


def _always_unmeasurable(arm: Any, cell: Cell, *, trace_dir: str | None = None) -> CellResult:
    return CellResult(arm_id=arm.arm_id, task_id=str(cell.task_id), seed=cell.seed, detection=None)


def _run_driver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    config_cap: int,
    extra_argv: tuple[str, ...] = (),
    max_evals: int = 60,
) -> dict[str, Any]:
    """跑真实 CLI 主函数（数据集/单 cell 评估桩化，搜索与报告走真实实现）。"""
    monkeypatch.setenv("ORCHESTRATION_SEARCH_ENABLE", "true")
    monkeypatch.setenv("AITESTER_TRACE_DIR", "")
    monkeypatch.setenv("AITESTER_CACHE_NAMESPACE", "")
    monkeypatch.setattr(config_module, "ORCHESTRATION_SEARCH_MAX_UNMEASURABLE", config_cap)
    monkeypatch.setattr(driver, "load_design_set_cells", lambda **_kwargs: _make_cells(max_evals))
    monkeypatch.setattr(driver, "run_arm_cell", _always_unmeasurable)
    monkeypatch.setattr("experiments.run_benchmark._apply_deterministic_temperature", lambda: None)

    rc = driver.main(
        [
            "--task-count",
            "1",
            "--seeds",
            "42",
            "--output-dir",
            str(tmp_path),
            "--max-evals",
            str(max_evals),
            *extra_argv,
        ]
    )
    assert rc == 0
    reports = list(tmp_path.glob("orchestration_search_*/search_result.json"))
    assert len(reports) == 1, f"未找到唯一结果工件：{reports}"
    return json.loads(reports[0].read_text(encoding="utf-8"))


class TestUnmeasurableCapWiring:
    def test_config_cap_reaches_the_real_search(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """config cap=2 ⇒ 报告披露 2，且全不可测臂第 3 次后退出 UCB 池。

        修复前：构造默认 5 恒生效，60 次评估摊到 16 臂（每臂 ≤4）无任何排除，
        报告 config 也不含 max_unmeasurable。
        """
        report = _run_driver(tmp_path, monkeypatch, config_cap=2)
        assert report["config"]["max_unmeasurable"] == 2
        assert {stats["excluded_reason"] for stats in report["arm_stats"].values()} == {"unmeasurable_exceeded"}
        assert report["budget"]["evals_used"] == 48

    def test_cap_five_does_not_exclude_at_the_boundary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """边界对照：cap=5、首臂恰好 5 次不可测 ⇒ 不得排除（排除只在严格超过时发生）。"""
        report = _run_driver(tmp_path, monkeypatch, config_cap=5, max_evals=20)
        assert report["config"]["max_unmeasurable"] == 5
        assert {stats["excluded_reason"] for stats in report["arm_stats"].values()} == {None}
        assert max(stats["unmeasurable"] for stats in report["arm_stats"].values()) == 5
        assert report["budget"]["stop_reason"] == "max_evals"
        assert report["budget"]["evals_used"] == 20

    def test_cli_flag_overrides_config_cap(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`--max-unmeasurable 2` 必须覆盖 config 的 10（flag 优先级与四个兄弟旋钮一致）。"""
        report = _run_driver(tmp_path, monkeypatch, config_cap=10, extra_argv=("--max-unmeasurable", "2"))
        assert report["config"]["max_unmeasurable"] == 2
        assert {stats["excluded_reason"] for stats in report["arm_stats"].values()} == {"unmeasurable_exceeded"}
