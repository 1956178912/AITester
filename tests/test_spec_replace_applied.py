"""P0-A-2（2026-10-12）：规格优先生成可审计观测字段 `spec_replace_applied` 行为锁。

锁定三组行为（对应 SPEC_REPLACE_AB_REPORT_2026-10-12.md §5 建议）：
1. state 键声明与默认值（AITesterState / create_initial_state 的 None 占位）；
2. _generator_node 写入口径：
   - DETECTION_SPEC_MODE=off / 未设 → None（历史口径零变化）；
   - DETECTION_SPEC_MODE=replace 且规约材料非空 → "attempted_replaced"；
   - DETECTION_SPEC_MODE=replace 且规约材料为空（渲染返回空串）→ "attempted_fallback"；
3. 结果行键集合同构：成功分支读 state 值，失败分支 None 占位；
   BASELINE.yaml metrics_schema 登记该键。

纯字符串层验证（零 LLM / 零子进程），与 P0-4 spec_oracle 行级判定
（tests/test_spec_oracle_metrics.py::TestGeneratorWritesMetricKeys）同模式：
patch "src.graph.nodes.GeneratorAgent" 注入 MagicMock 短路 LLM 调用层。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.graph.state import AITesterState, create_initial_state

_LLM_TEST = "def test_llm():\n    assert True\n"
# 目标函数带 docstring——build_spec_replace_section 的规约材料来源之一
# （无 logic_analysis 时 docstring 非空即 has_material → attempted_replaced）
_TARGET_CODE = 'def fn(x):\n    """fn docstring."""\n    return x\n'
# 目标函数无 docstring 且 test_plan=None → 规约材料全空 → 渲染空串
# （DETECTION_SPEC_MODE=replace 时走 attempted_fallback）
_TARGET_CODE_NO_DOC = "def fn(x):\n    return x\n"


def _state(target_code: str = _TARGET_CODE, with_plan: bool = True) -> dict:
    state = create_initial_state(
        "u",
        "target_mod.py",
        target_code,
        1,
        module_name="target_mod",
        target_function="fn",
    )
    if with_plan:
        state["test_plan"] = {
            "function_name": "fn",
            "test_cases": [{"case_name": "basic", "input_args": "(1)", "expected_output": "1", "category": "basic"}],
        }
    else:
        state["test_plan"] = None
    return dict(state)


def _run_generator(state: dict) -> dict:
    """patch GeneratorAgent 短路 LLM 调用层（同 test_spec_oracle_metrics 模式）。"""
    from src.graph.nodes import _generator_node

    mock_agent = MagicMock()
    mock_agent.generate.return_value = _LLM_TEST
    with (
        patch("src.graph.nodes.GeneratorAgent", return_value=mock_agent),
        patch("src.graph.nodes.ENABLE_RAG", False),
    ):
        return _generator_node(state)  # type: ignore[arg-type]


@pytest.mark.unit
class TestSpecReplaceAppliedState:
    """1. state 键声明 + 默认值。"""

    def test_state_annotation_declared(self) -> None:
        assert "spec_replace_applied" in AITesterState.__annotations__

    def test_initial_state_defaults_none(self) -> None:
        state = create_initial_state("u", "m.py", "x = 1\n", 3)
        assert state["spec_replace_applied"] is None


@pytest.mark.unit
class TestSpecReplaceAppliedGenerator:
    """2. _generator_node 写入口径（三态：off → None / replace+材料 → attempted_replaced
    / replace+无材料 → attempted_fallback / 未知模式 → 按 off 处理 → None）。"""

    def test_default_off_is_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DETECTION_SPEC_MODE", raising=False)
        update = _run_generator(_state())
        assert update["spec_replace_applied"] is None

    def test_replace_with_material_is_attempted_replaced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """docstring 非空 → 规约材料非空 → 实际替换目标代码块。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        update = _run_generator(_state(target_code=_TARGET_CODE))
        assert update["spec_replace_applied"] == "attempted_replaced"

    def test_replace_without_material_is_attempted_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 docstring + test_plan=None → 规约材料全空 → 渲染空串，回退历史口径。"""
        monkeypatch.setenv("DETECTION_SPEC_MODE", "replace")
        update = _run_generator(_state(target_code=_TARGET_CODE_NO_DOC, with_plan=False))
        assert update["spec_replace_applied"] == "attempted_fallback"

    def test_unknown_mode_falls_back_to_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETECTION_SPEC_MODE", "bogus")
        update = _run_generator(_state())
        assert update["spec_replace_applied"] is None


@pytest.mark.unit
class TestSpecReplaceAppliedResultRow:
    """3. 结果行键集合同构 + BASELINE 登记。"""

    def test_result_row_key_present_in_both_branches(self) -> None:
        import importlib

        rb = importlib.import_module("experiments.run_benchmark")
        src = Path(rb.__file__).read_text(encoding="utf-8")
        # 成功分支：从 final_state 读取
        assert '"spec_replace_applied": final_state.get("spec_replace_applied")' in src
        # 失败分支：None 占位（键集合同构）
        assert '"spec_replace_applied": None' in src

    def test_baseline_schema_registerd(self) -> None:
        import yaml  # type: ignore[import-untyped]

        with open("BASELINE.yaml", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        schema = data["benchmark"]["metrics_schema"]
        assert "spec_replace_applied" in schema
