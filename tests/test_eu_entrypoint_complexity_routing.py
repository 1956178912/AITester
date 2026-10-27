"""EU 轮：默认开启的复杂度感知路由必须覆盖所有入口（CLI / 搜索 / benchmark）。

缺陷族：``MODEL_ROUTING_STRATEGY=complexity_aware`` 是默认值，但只有
``experiments/run_benchmark.py`` 在 ``create_initial_state`` 之后补写
``state["complexity_class"]``；CLI（``src/cli/app.py``）与搜索入口直接使用
工厂产物，四个路由字段恒 None → ``APIManager._build_node_list`` 的复杂度分支
与 ``BaseAgent._reorder_api_groups_by_complexity`` 永不触发，
``fixed`` 与 ``complexity_aware`` 在 ``aitester run`` 下不可区分。

锁点：
1. 工厂在 complexity_aware 下按源码/metadata 写入四字段；fixed 保持
   historical ``"medium"``（score/breakdown/hints 为 None）；
2. CLI 真实路径送入 graph 的 state 携带档位（切换策略可见）；
3. 共享评分入口的维度口径、metadata 数值兜底、解析失败回退；
4. benchmark 委托工厂（传 ``task.metadata``），不再内联重复实现。
"""

from __future__ import annotations

import pathlib

import pytest
from click.testing import CliRunner

import src.cli.app as cli_app
from src.graph.state import create_initial_state

_LINES_NORM = 500
_FILES_NORM = 5


def _complex_source() -> str:
    """584 行 / 20 imports / cc=31 → 分数 0.80（complex 档）。"""
    imports = "\n".join(f"import module_{i}" for i in range(20))
    branches = "\n".join(f"    if x == {i}:\n        return {i}" for i in range(30))
    body = f"def f(x):\n{branches}\n    return -1\n"
    padding = "\n".join(f"CONST_{i} = {i}" for i in range(_LINES_NORM))
    return f"{imports}\n\n{body}\n{padding}\n"


def _padding_source() -> str:
    """500 行、无 import、cc=1 → 依赖 num_files 才能跨到 medium 档。"""
    padding = "\n".join(f"CONST_{i} = {i}" for i in range(_LINES_NORM - 2))
    return f"def f():\n    return 1\n{padding}\n"


def _unparseable_source() -> str:
    """语法错误 + 501 行 → 行/文件维度固定，cc 只能来自 metadata 兜底。"""
    return "def broken(:\n" + "x = 1\n" * 500


def _state(code: str, **kwargs) -> dict:
    return dict(
        create_initial_state(
            task_uuid="eu_round",
            target_file="demo.py",
            target_code=code,
            max_iterations=1,
            **kwargs,
        )
    )


class _CapturingGraph:
    """记录 CLI 送入 graph.invoke 的 state，返回最小成功终态。"""

    def __init__(self) -> None:
        self.invoked_states: list[dict] = []

    def invoke(self, state):
        self.invoked_states.append(dict(state))
        return {"test_passed": True, "coverage_report": 90.0, "iteration": 1}


class TestFactoryScoresComplexity:
    """唯一构造点必须自己完成评分（而非依赖 benchmark 事后补写）。"""

    def test_aware_strategy_writes_complex_class(self, monkeypatch) -> None:
        monkeypatch.setenv("MODEL_ROUTING_STRATEGY", "complexity_aware")
        st = _state(_complex_source())
        assert st["complexity_class"] == "complex"
        assert st["complexity_score"] == pytest.approx(0.80, abs=1e-6)
        assert st["complexity_breakdown"]["raw_files"] == 1
        assert st["complexity_breakdown"]["raw_deps"] == 20
        assert st["complexity_breakdown"]["raw_cc"] == 31
        assert st["routing_hints"]["max_candidates"] == 3
        assert st["routing_hints"]["extra_iteration"] == 1

    def test_default_strategy_is_complexity_aware(self, monkeypatch) -> None:
        """未显式设置环境变量时默认档位已生效（承诺的默认值）。"""
        monkeypatch.delenv("MODEL_ROUTING_STRATEGY", raising=False)
        st = _state(_complex_source())
        assert st["complexity_class"] == "complex"

    def test_fixed_strategy_keeps_historical_caliber(self, monkeypatch) -> None:
        """fixed = 不按复杂度分档：仅 class="medium"，其余保持 None。"""
        monkeypatch.setenv("MODEL_ROUTING_STRATEGY", "fixed")
        st = _state(_complex_source())
        assert st["complexity_class"] == "medium"
        assert st["complexity_score"] is None
        assert st["complexity_breakdown"] is None
        assert st["routing_hints"] is None

    def test_task_metadata_num_files_reaches_score(self, monkeypatch) -> None:
        monkeypatch.setenv("MODEL_ROUTING_STRATEGY", "complexity_aware")
        assert _state(_padding_source())["complexity_class"] == "simple"
        st = _state(_padding_source(), task_metadata={"num_files": _FILES_NORM})
        assert st["complexity_class"] == "medium"
        assert st["complexity_breakdown"]["raw_files"] == _FILES_NORM


class TestCliEntrypointRoutes:
    """CLI 真实调用链：送入 graph 的 state 必须已带档位。"""

    def _run_cli(self, tmp_path, monkeypatch, code: str) -> tuple[dict, object]:
        path = tmp_path / "target_mod.py"
        path.write_text(code, encoding="utf-8")
        graph = _CapturingGraph()
        monkeypatch.setattr(cli_app, "build_workflow", lambda: graph)
        monkeypatch.setattr(cli_app, "start_task_trace", lambda *a, **k: None)
        monkeypatch.setattr(cli_app, "end_task_trace", lambda *a, **k: None)
        result = CliRunner().invoke(cli_app.cli, ["run", str(path), "--json"])
        assert result.exit_code == 0, result.output
        assert len(graph.invoked_states) == 1
        return graph.invoked_states[0], result

    def test_cli_aware_state_carries_complex_class(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("MODEL_ROUTING_STRATEGY", "complexity_aware")
        state, _ = self._run_cli(tmp_path, monkeypatch, _complex_source())
        assert state["complexity_class"] == "complex"
        assert state["routing_hints"]["max_candidates"] == 3

    def test_cli_fixed_state_is_observably_different(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("MODEL_ROUTING_STRATEGY", "fixed")
        state, _ = self._run_cli(tmp_path, monkeypatch, _complex_source())
        assert state["complexity_class"] == "medium"
        assert state["complexity_score"] is None


class TestSharedScoringEntry:
    """CLI / 搜索 / benchmark 共用的评分入口（单一实现，不允许内联复制）。"""

    def test_source_dimensions(self) -> None:
        from src.api.complexity_router import score_source_complexity

        score = score_source_complexity(_complex_source())
        assert score.complexity_class == "complex"
        assert score.breakdown["raw_lines"] == len(_complex_source().splitlines())
        assert score.breakdown["raw_deps"] == 20
        assert score.breakdown["raw_cc"] == 31
        boolop = score_source_complexity("def f(a, b, c):\n    if a and b or c:\n        return 1\n    return 0\n")
        # 1（基线）+ 1（if）+ 1（and）+ 1（or）：BoolOp 按子表达式数展开
        assert boolop.breakdown["raw_cc"] == 4

    def test_metadata_num_files_changes_class(self) -> None:
        from src.api.complexity_router import score_task_complexity

        assert score_task_complexity(_padding_source()).complexity_class == "simple"
        with_files = score_task_complexity(_padding_source(), {"num_files": _FILES_NORM})
        assert with_files.complexity_class == "medium"
        assert with_files.breakdown["raw_files"] == _FILES_NORM

    def test_metadata_cc_is_parse_failure_fallback_only(self) -> None:
        from src.api.complexity_router import score_task_complexity

        parsed = score_task_complexity(_padding_source(), {"cyclomatic_complexity": 25})
        assert parsed.breakdown["raw_cc"] == 1, "源码可解析时以源码口径为准"
        fallback = score_task_complexity(_unparseable_source(), {"cyclomatic_complexity": 25})
        assert fallback.breakdown["raw_cc"] == 25
        assert fallback.complexity_class == "medium"
        assert score_task_complexity(_unparseable_source()).complexity_class == "simple"

    def test_metadata_imports_is_counter_exception_fallback(self, monkeypatch) -> None:
        import src.api.complexity_router as cr

        def _boom(*_a, **_k):
            raise RuntimeError("import 计数失败")

        monkeypatch.setattr(cr, "count_imports", _boom)
        fallback = cr.score_task_complexity(_padding_source(), {"num_imports": 20})
        assert fallback.breakdown["raw_deps"] == 20
        assert fallback.complexity_class == "medium"
        assert cr.score_task_complexity(_padding_source()).complexity_class == "simple"


class TestBenchmarkDelegates:
    """benchmark 不得再保留第二份评分实现。"""

    def _source(self) -> str:
        here = pathlib.Path(__file__).resolve()
        return (here.parents[1] / "experiments" / "run_benchmark.py").read_text(encoding="utf-8")

    def test_passes_task_metadata_to_factory(self) -> None:
        assert "task_metadata=task.metadata" in self._source()

    def test_no_inline_scoring_left(self) -> None:
        src = self._source()
        assert "compute_complexity_score(" not in src
        assert "_count_cc(" not in src
