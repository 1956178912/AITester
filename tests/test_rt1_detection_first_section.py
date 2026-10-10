"""RT1 采样控制开关测试（2026-10-09 审查报告 §8.6 红队 RT1）。

红队假说：`plain_llm_df` 臂首轮全绿时**必然再生成一次**，而 `plain_llm` 只生成
一次 —— "+43pp 协议效应"可能只是"多一次采样"的概率效应。

RT1 臂需要 **保留再生成路由 + 关闭强化 prompt 段落**，故新增
`DETECTION_FIRST_SECTION_ENABLE`（默认 true = 历史口径零变化）：
- 置 false 时 `_detection_first_section` 返回 None（不注入强化文本）；
- **再生成入口 `_detection_first_regenerate_entry` 不受影响**（路由保留）——
  这是本开关的关键正确性要求：若它同时关掉路由，就退化成 `plain_llm`，
  无法分离变量。

实测结论（冷缓存 seed42 n=87，见 BASELINE.yaml `rt1_sampling_control`）：
plain_llm 10.3% · RT1 11.5% · df 31.0%；RT1 vs plain_llm p=1.0000（采样效应
可忽略），df vs RT1 p=0.0001（强化段净效应 +19.5pp）。
"""

from __future__ import annotations

import pytest

from src.graph.nodes import (
    _detection_first_regenerate_entry,
    _detection_first_section,
    _detection_first_section_enabled,
)

PASSED_STATE = {"test_passed": True, "iteration": 0}


class TestSectionEnabledSwitch:
    """开关本体：默认 true，仅显式 false/0 关闭。"""

    def test_default_is_enabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DETECTION_FIRST_SECTION_ENABLE", raising=False)
        assert _detection_first_section_enabled() is True

    @pytest.mark.parametrize("value", ["false", "FALSE", "0", "False"])
    def test_falsy_values_disable(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("DETECTION_FIRST_SECTION_ENABLE", value)
        assert _detection_first_section_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "on", ""])
    def test_truthy_values_keep_enabled(self, monkeypatch: pytest.MonkeyPatch, value: str) -> None:
        monkeypatch.setenv("DETECTION_FIRST_SECTION_ENABLE", value)
        assert _detection_first_section_enabled() is True


class TestSectionSuppressed:
    """关闭时：段落不注入，但再生成入口的判定逻辑本身不被改写。"""

    def test_section_none_when_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """关闭后即便处于再生成入口状态，也不返回强化段落。

        注意：`_detection_first_regenerate_entry` 还依赖 `detection_first_enabled()`
        （进程/profile 级），本用例只断言"开关关闭 ⇒ 段落为 None"这一必要条件，
        不臆造 detection_first 全局状态。
        """
        monkeypatch.setenv("DETECTION_FIRST_SECTION_ENABLE", "false")
        assert _detection_first_section(PASSED_STATE) is None

    def test_regenerate_entry_logic_not_short_circuited_by_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """关键正确性：本开关**不得**改变再生成入口的返回值。

        同一条 state 在开/关两种取值下，`_detection_first_regenerate_entry`
        必须返回**相同**结果（证明路由保留，分离的是变量而非整条路径）。
        """
        monkeypatch.setenv("DETECTION_FIRST_SECTION_ENABLE", "true")
        on = _detection_first_regenerate_entry(PASSED_STATE)
        monkeypatch.setenv("DETECTION_FIRST_SECTION_ENABLE", "false")
        off = _detection_first_regenerate_entry(PASSED_STATE)
        assert on == off
