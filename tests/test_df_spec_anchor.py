#!/usr/bin/env python3
"""A-10（2026-10-16）：df_spec 臂（plain_llm_df_spec）与规格锚表回归锁定。

锁定四组行为：
1. 锚表构建（`experiments/build_spec_anchor_table.py`）：
   - 内容寻址键 = sha256(源码.strip())；JSON 与 Python 字面量两种响应均可提取；
   - 候选优选确定性（含 *_expr > timestamp 大 > 文件名小）；坏响应/非 Planner
     条目/无栅栏块分别计数弃用；重跑逐位一致；
2. 规格模式线程覆盖（`src/tools/spec_first.py::set_spec_mode_thread_override`）：
   - 覆盖优先于 env；清除回落 env；非法覆盖值记 warning 并回落 env；
3. 臂接线（`experiments/run_benchmark.py`）：
   - BASELINE_REGISTRY 注册；env DF_SPEC_ANCHOR_TABLE 可指向表；快照键已登记；
   - 命中：invoke 窗口内 state["spec_anchor"] = 材料 + 规格模式 "replace"、
     检出优先线程覆盖 True，finally 全恢复；
   - 未命中：不注入材料（回落 df 口径），模式仍 replace（节点渲染空串 →
     attempted_fallback 由既有 test_spec_replace_applied 口径覆盖）；
4. 节点锚材料优先级（`src/graph/nodes.py::_generator_node`）：
   - state["spec_anchor"] 存在时优先于 test_plan 渲染替换段（df_spec 路径）；
   - 缺席时回落 test_plan（历史口径，其它臂零变化）。
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.tools.spec_first import detection_spec_mode, set_spec_mode_thread_override

# ─── 1. 锚表构建 ─────────────────────────────────────────────────────────────


def _entry_prompt(source: str) -> str:
    return f"请分析以下代码并制定测试计划：\n\n```\n{source}\n```\n\n请输出 JSON。"


_PLAN_JSON: dict[str, Any] = {
    "function_name": "fn",
    "logic_analysis": {
        "preconditions": ["x 为整数"],
        "postconditions": ["返回 x + 1"],
        "postconditions_expr": ["result == x + 1"],
    },
}
_PLAN_NO_EXPR: dict[str, Any] = {
    "function_name": "fn",
    "logic_analysis": {"preconditions": ["x 为整数"], "postconditions": ["返回 x + 1"]},
}


def _write_cache_entry(
    cache_dir: Path,
    name: str,
    source: str,
    plan: dict[str, Any],
    *,
    via: str = "json",
    timestamp: float = 1.0,
    system: str = "你是一名软件测试规划师。",
    response_override: str | None = None,
) -> Path:
    resp = (
        response_override
        if response_override is not None
        else (json.dumps(plan, ensure_ascii=False) if via == "json" else repr(plan))
    )
    payload = {
        "prompt": _entry_prompt(source),
        "system": system,
        "response": resp,
        "timestamp": timestamp,
    }
    path = cache_dir / name
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


class TestAnchorTableBuild:
    @pytest.mark.unit
    def test_builds_content_addressed_entry(self, tmp_path: Path) -> None:
        import hashlib

        build = importlib.import_module("experiments.build_spec_anchor_table")
        cache = tmp_path / "cache"
        cache.mkdir()
        source = "def fn(x):\n    return x + 1\n"
        _write_cache_entry(cache, "a.json", source, _PLAN_JSON)
        table, stats = build.build_anchor_table(cache)
        key = hashlib.sha256(source.strip().encode("utf-8")).hexdigest()
        assert key in table["anchors"]
        assert table["anchors"][key]["function_name"] == "fn"
        assert stats["parsed_json"] == 1 and stats["scanned_files"] == 1

    @pytest.mark.unit
    def test_python_literal_response_rescued(self, tmp_path: Path) -> None:
        build = importlib.import_module("experiments.build_spec_anchor_table")
        cache = tmp_path / "cache"
        cache.mkdir()
        _write_cache_entry(cache, "a.json", "def fn(x):\n    return 1\n", _PLAN_JSON, via="python_literal")
        table, stats = build.build_anchor_table(cache)
        assert stats["parsed_python_literal"] == 1
        assert len(table["anchors"]) == 1

    @pytest.mark.unit
    def test_broken_response_counted(self, tmp_path: Path) -> None:
        build = importlib.import_module("experiments.build_spec_anchor_table")
        cache = tmp_path / "cache"
        cache.mkdir()
        _write_cache_entry(cache, "a.json", "def fn():\n    return 1\n", _PLAN_JSON, response_override="{broken json")
        table, stats = build.build_anchor_table(cache)
        assert stats["rejected_json"] == 1
        assert table["anchors"] == {}

    @pytest.mark.unit
    def test_non_planner_and_no_fence_ignored(self, tmp_path: Path) -> None:
        build = importlib.import_module("experiments.build_spec_anchor_table")
        cache = tmp_path / "cache"
        cache.mkdir()
        _write_cache_entry(
            cache, "a.json", "def fn():\n    return 1\n", _PLAN_JSON, system="你是一名 Python 调试工程师。"
        )
        no_fence = cache / "b.json"
        no_fence.write_text(
            json.dumps(
                {"prompt": "无栅栏块", "system": "你是一名软件测试规划师。", "response": "{}", "timestamp": 1.0}
            ),
            encoding="utf-8",
        )
        table, stats = build.build_anchor_table(cache)
        assert stats["planner_entries"] == 1  # 非 Planner 不计
        assert stats["rejected_no_source"] == 1
        assert table["anchors"] == {}

    @pytest.mark.unit
    def test_expr_candidate_preferred(self, tmp_path: Path) -> None:
        build = importlib.import_module("experiments.build_spec_anchor_table")
        cache = tmp_path / "cache"
        cache.mkdir()
        source = "def fn(x):\n    return x + 1\n"
        # 旧条目含 *_expr；新条目不含——优选含 expr 者（材料更富）
        _write_cache_entry(cache, "a_old_expr.json", source, _PLAN_JSON, timestamp=1.0)
        _write_cache_entry(cache, "b_new_no_expr.json", source, _PLAN_NO_EXPR, timestamp=99.0)
        table, _ = build.build_anchor_table(cache)
        (anchor,) = table["anchors"].values()
        assert anchor["chosen_from"] == "a_old_expr.json"
        assert anchor["n_candidates"] == 2

    @pytest.mark.unit
    def test_rebuild_deterministic(self, tmp_path: Path) -> None:
        build = importlib.import_module("experiments.build_spec_anchor_table")
        cache = tmp_path / "cache"
        cache.mkdir()
        _write_cache_entry(cache, "a.json", "def fn():\n    return 1\n", _PLAN_JSON, timestamp=2.0)
        _write_cache_entry(cache, "b.json", "def g():\n    return 2\n", _PLAN_JSON, timestamp=1.0)
        first, _ = build.build_anchor_table(cache)
        second, _ = build.build_anchor_table(cache)
        assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
            second, ensure_ascii=False, sort_keys=True
        )


# ─── 2. 规格模式线程覆盖 ─────────────────────────────────────────────────────


class TestSpecModeThreadOverride:
    @pytest.mark.unit
    def test_override_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "off")
        set_spec_mode_thread_override("replace")
        try:
            assert detection_spec_mode() == "replace"
        finally:
            set_spec_mode_thread_override(None)
        assert detection_spec_mode() == "off"

    @pytest.mark.unit
    def test_default_off_without_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        assert detection_spec_mode() == "off"

    @pytest.mark.unit
    def test_invalid_override_falls_back_to_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        set_spec_mode_thread_override("bogus")
        try:
            assert detection_spec_mode() == "replace"
        finally:
            set_spec_mode_thread_override(None)


# ─── 3. 臂接线 ───────────────────────────────────────────────────────────────


class _FakeGraph:
    """记录 invoke 入参与调用期间关键开关状态的假图。"""

    def __init__(self, sink: dict[str, Any]) -> None:
        self._sink = sink

    def invoke(self, state: dict[str, Any]) -> dict[str, Any]:
        import config as _cfg

        self._sink["invoke_state"] = dict(state)
        self._sink["spec_mode_during"] = detection_spec_mode()
        self._sink["detection_first_during"] = _cfg.detection_first_enabled()
        return dict(state)


def _make_state(target_code: str) -> dict[str, Any]:
    from src.graph.state import create_initial_state

    state = create_initial_state("u_df_spec", "target_mod.py", target_code, 1, module_name="target_mod")
    state["task_id"] = "synthetic__task_0000"
    return dict(state)


class TestRunBenchmarkWiring:
    @pytest.mark.unit
    def test_registry_entry_present(self) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        assert "plain_llm_df_spec" in rb.BASELINE_REGISTRY
        assert rb.BASELINE_REGISTRY["plain_llm_df_spec"] is rb.run_plain_llm_df_spec_baseline

    @pytest.mark.unit
    def test_snapshot_key_listed(self) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        src = Path(rb.__file__).read_text(encoding="utf-8")
        assert '"DF_SPEC_ANCHOR_TABLE",' in src

    @pytest.mark.unit
    def test_load_table_from_env_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import hashlib

        rb = importlib.import_module("experiments.run_benchmark")
        source = "def fn(x):\n    return x + 1\n"
        key = hashlib.sha256(source.strip().encode()).hexdigest()
        table_path = tmp_path / "SPEC_ANCHOR_TABLE.json"
        table_path.write_text(
            json.dumps({"meta": {}, "anchors": {key: {"function_name": "fn", "logic_analysis": {}}}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("DF_SPEC_ANCHOR_TABLE", str(table_path))
        monkeypatch.setattr(rb, "_SPEC_ANCHOR_TABLE_CACHE", {})
        anchor = rb._lookup_spec_anchor({"target_code": source})
        assert anchor is not None and anchor["function_name"] == "fn"
        # 未命中
        assert rb._lookup_spec_anchor({"target_code": "def other():\n    return 0\n"}) is None

    @pytest.mark.unit
    def test_load_table_missing_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        monkeypatch.setenv("DF_SPEC_ANCHOR_TABLE", str(tmp_path / "nope.json"))
        monkeypatch.setattr(rb, "_SPEC_ANCHOR_TABLE_CACHE", {})
        assert rb._load_spec_anchor_table() is None
        assert rb._lookup_spec_anchor({"target_code": "def fn():\n    return 1\n"}) is None

    @pytest.mark.unit
    def test_arm_hit_injects_anchor_and_restores_flags(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import hashlib

        import config as _cfg

        rb = importlib.import_module("experiments.run_benchmark")
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        monkeypatch.delenv("DETECTION_FIRST_ENABLE", raising=False)
        source = "def fn(x):\n    return x + 1\n"
        key = hashlib.sha256(source.strip().encode()).hexdigest()
        table_path = tmp_path / "SPEC_ANCHOR_TABLE.json"
        material = {"function_name": "fn", "logic_analysis": {"postconditions_expr": ["result == x + 1"]}}
        table_path.write_text(json.dumps({"meta": {}, "anchors": {key: material}}), encoding="utf-8")
        monkeypatch.setenv("DF_SPEC_ANCHOR_TABLE", str(table_path))
        monkeypatch.setattr(rb, "_SPEC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        state = _make_state(source)
        result = rb.run_plain_llm_df_spec_baseline(state)

        assert sink["invoke_state"]["spec_anchor"] == material
        assert sink["spec_mode_during"] == "replace"
        assert sink["detection_first_during"] is True
        # finally 全恢复
        assert detection_spec_mode() == "off"
        assert _cfg.detection_first_enabled() is False
        assert result["spec_anchor"] == material

    @pytest.mark.unit
    def test_arm_miss_falls_back_without_material(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rb = importlib.import_module("experiments.run_benchmark")
        monkeypatch.setenv("DF_SPEC_ANCHOR_TABLE", str(tmp_path / "nope.json"))
        monkeypatch.setattr(rb, "_SPEC_ANCHOR_TABLE_CACHE", {})
        sink: dict[str, Any] = {}
        monkeypatch.setattr(rb, "build_workflow", lambda **kwargs: _FakeGraph(sink))

        rb.run_plain_llm_df_spec_baseline(_make_state("def unknown():\n    return 0\n"))
        # 未命中：defaults 的 None 保持（回落 df 口径）；模式仍 replace（节点渲染空串）
        assert sink["invoke_state"]["spec_anchor"] is None
        assert sink["spec_mode_during"] == "replace"
        assert detection_spec_mode() == "off"  # finally 恢复


# ─── 4. 节点锚材料优先级 ─────────────────────────────────────────────────────


class TestGeneratorNodeAnchorPreference:
    def _state(self, *, oracle: str, with_plan: bool = False) -> dict[str, Any]:
        from src.graph.state import create_initial_state

        code = 'def fn(x):\n    """fn docstring."""\n    return x\n'
        state = create_initial_state("u", "target_mod.py", code, 1, module_name="target_mod", target_function="fn")
        state["test_plan"] = (
            {
                "function_name": "fn",
                "logic_analysis": {"postconditions": ["PLAN_MARKER 计划侧材料"]},
                "test_cases": [
                    {"case_name": "basic", "input_args": "(1)", "expected_output": "1", "category": "basic"}
                ],
            }
            if with_plan
            else None
        )
        state["spec_anchor"] = {"function_name": "fn", "logic_analysis": {"postconditions": [oracle]}}
        return dict(state)

    def _run_generator(self, state: dict[str, Any]) -> tuple[dict[str, Any], MagicMock]:
        from src.graph.nodes import _generator_node

        mock_agent = MagicMock()
        mock_agent.generate.return_value = "def test_x():\n    assert True\n"
        with (
            patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
            patch("src.graph.nodes.ENABLE_RAG", False),
        ):
            update = _generator_node(state)  # type: ignore[arg-type]
        return update, mock_agent

    @pytest.mark.unit
    def test_anchor_preferred_over_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        state = self._state(oracle="ANCHOR_MARKER 锚侧材料", with_plan=True)
        update, mock_agent = self._run_generator(state)
        assert update["spec_replace_applied"] == "attempted_replaced"
        section = mock_agent.generate.call_args.kwargs["spec_replace_section"]
        assert "ANCHOR_MARKER" in section
        assert "PLAN_MARKER" not in section
        # 节点按原样转发 test_plan 给 generate（本测试注入的 plan 会被透传；
        # df_spec 真实链路的计划纯度由臂侧 planner=False → test_plan 恒 None
        # 保证，节点不做过滤——此处仅锁"透传不改变"语义）
        assert mock_agent.generate.call_args.args[0] == state["test_plan"]

    @pytest.mark.unit
    def test_without_anchor_falls_back_to_plan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        state = self._state(oracle="ANCHOR_MARKER", with_plan=True)
        state["spec_anchor"] = None  # 模拟非 df_spec 臂（历史口径）
        update, mock_agent = self._run_generator(state)
        assert update["spec_replace_applied"] == "attempted_replaced"
        section = mock_agent.generate.call_args.kwargs["spec_replace_section"]
        assert "PLAN_MARKER" in section
        assert "ANCHOR_MARKER" not in section
