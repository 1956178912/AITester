"""`_over_red_section` 测试（2026-10-10 审查报告 §11.1b 结果二十四）。

背景（实测）：QuixBugs 41 缺陷程序口径下，aitester 首轮 `over_red`（盲/过红）
占 **30/50（60%）**，而这类任务的 detection 为 **0%**；`specific_red` 则
**100%** 检出。代码级根因：`_detection_first_section` 只覆盖
`test_passed is True`（首轮全绿），而 `over_red` 是 `test_passed=False`
进入的 → **拿不到任何强化提示** → 再生成只是"用同一份计划再问一次" →
注定同样 over_red，不可恢复。

本模块锁定新段落的三条行为：默认关（零行为变化）、仅在 over_red 路径注入、
文本须含三条关键指令（输入规模受控 / 期望值来自契约 / 保持特异性）。
"""

from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.graph.nodes import (  # noqa: E402
    _over_red_section,
    _over_red_section_enabled,
)


def _over_red_state() -> dict:
    """构造 over_red 再生成入口成立的最小 state（见 _specificity_over_red_regenerate_entry）。"""
    return {"iteration": 0, "specificity_gate_verdict": "over_red"}


class TestDefaultOff:
    """ADR-0003：新功能默认关，历史口径零变化。"""

    def test_default_is_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OVER_RED_SECTION_ENABLE", raising=False)
        assert _over_red_section_enabled() is False

    def test_disabled_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OVER_RED_SECTION_ENABLE", raising=False)
        assert _over_red_section(_over_red_state()) is None

    @pytest.mark.parametrize("val", ["false", "0", "False", "no", ""])
    def test_falsy_values_disabled(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", val)
        assert _over_red_section(_over_red_state()) is None

    @pytest.mark.parametrize("val", ["true", "1", "TRUE", "True"])
    def test_truthy_values_enabled(self, monkeypatch: pytest.MonkeyPatch, val: str) -> None:
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", val)
        assert _over_red_section_enabled() is True


class TestOnlyOnOverRedPath:
    """只在 over_red 再生成路径注入；其他路径一律 None（不得误注入）。"""

    def test_injected_on_over_red(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", "true")
        out = _over_red_section(_over_red_state())
        assert out is not None and out.strip()

    def test_not_injected_when_iteration_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """iteration != 0（已进入修复循环）→ 不是 over_red 入口。"""
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", "true")
        st = _over_red_state()
        st["iteration"] = 1
        assert _over_red_section(st) is None

    @pytest.mark.parametrize("verdict", ["specific_red", "unavailable", None])
    def test_not_injected_for_other_verdicts(self, monkeypatch: pytest.MonkeyPatch, verdict: str | None) -> None:
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", "true")
        st = _over_red_state()
        st["specificity_gate_verdict"] = verdict
        assert _over_red_section(st) is None

    def test_not_injected_on_empty_state(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", "true")
        assert _over_red_section({}) is None


class TestSectionContent:
    """段落须含三条关键指令——这是修复的全部内容，缺失即失效。"""

    @pytest.fixture()
    def text(self, monkeypatch: pytest.MonkeyPatch) -> str:
        monkeypatch.setenv("OVER_RED_SECTION_ENABLE", "true")
        out = _over_red_section(_over_red_state())
        assert out is not None
        return out

    def test_instructs_bounded_inputs(self, text: str) -> None:
        """（a）输入规模受控：针对"缺陷实现不终止"这一实测主因。"""
        assert "输入规模受控" in text
        assert "挂起" in text or "超时" in text

    def test_instructs_contract_based_expectations(self, text: str) -> None:
        """（b）期望值来自契约，禁止照抄实现当前行为。"""
        assert "契约" in text
        assert "照抄" in text

    def test_instructs_preserving_specificity(self, text: str) -> None:
        """（c）保持特异性，禁止放松断言换通过。"""
        assert "特异" in text
        assert "放松" in text

    def test_forbids_copying_buggy_behavior(self, text: str) -> None:
        assert "缺陷" in text


class TestSnapshotKeyRegistered:
    """**审计缺口回归锁**（审查报告 §11.1b 结果二十七）。

    消融类开关必须出现在 `run_benchmark` 的 provenance `env_snapshot` 键表中，
    否则**无法从工件证明干预是否生效**——A1 首跑正是栽在这里
    （`PLAN_STRIP_EXPECTED_OUTPUT_ENABLE` 未生效却记为"零效应"），
    over_red 首跑又重复了一次（该键未登记）。

    本用例在**代码层**锁定该键已登记，不依赖跑批。
    """

    def test_over_red_flag_in_env_snapshot_keys(self) -> None:
        import inspect

        from experiments import run_benchmark

        src = inspect.getsource(run_benchmark)
        # 抓取 _env_snapshot_keys 列表字面量所在的源码块
        start = src.index("_env_snapshot_keys = [")
        end = src.index("]", start)
        block = src[start:end]
        assert '"OVER_RED_SECTION_ENABLE"' in block, (
            "OVER_RED_SECTION_ENABLE 未登记进 provenance env_snapshot —— 消融将无法从工件验证（同 A1 假阴性缺口）"
        )

    def test_plan_strip_flag_still_registered(self) -> None:
        """A1 的开关也必须仍在（防回归删除）。"""
        import inspect

        from experiments import run_benchmark

        src = inspect.getsource(run_benchmark)
        start = src.index("_env_snapshot_keys = [")
        end = src.index("]", start)
        assert '"PLAN_STRIP_EXPECTED_OUTPUT_ENABLE"' in src[start:end]
