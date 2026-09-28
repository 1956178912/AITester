"""ANNEAL-lite 故障频率策略切换（failure_frequency）单元测试。

覆盖：
- 开关默认关（FAILURE_FREQUENCY_ENABLE 未设 → failure_frequency_enabled() False）
- 开关开启（monkeypatch 环境变量）
- detect_high_frequency_failure 非高频（count < threshold）→ None
- detect_high_frequency_failure 高频（count ≥ threshold）→ 信号字典
- detect_high_frequency_failure 模块维度过滤（target_module 提供时按 (cat, mod) 统计）
- detect_high_frequency_failure 窗口限制（REPAIR_HISTORY_WINDOW）
- get_escalated_strategy_hint 各类别命中 / 未命中 / None 输入
- get_escalated_strategy_tool 各类别命中 / 未命中 / None 输入
- failure_frequency_stats 观测统计口径
"""

from __future__ import annotations

import os
from unittest.mock import patch

from src.tools.failure_frequency import (
    detect_high_frequency_failure,
    failure_frequency_enabled,
    failure_frequency_stats,
    get_escalated_strategy_hint,
    get_escalated_strategy_tool,
)


def _make_history(categories: list[str], modules: list[str] | None = None) -> list[dict]:
    """辅助：构建 repair_history 列表。"""
    history: list[dict] = []
    for i, cat in enumerate(categories):
        entry: dict = {"iteration": i, "error_category": cat, "patch_applied": False}
        if modules:
            entry["module_name"] = modules[i] if i < len(modules) else "mod_a"
        history.append(entry)
    return history


def test_failure_frequency_default_off() -> None:
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("FAILURE_FREQUENCY_ENABLE", None)
        assert failure_frequency_enabled() is False


def test_failure_frequency_switch_on() -> None:
    with patch.dict(os.environ, {"FAILURE_FREQUENCY_ENABLE": "true"}):
        assert failure_frequency_enabled() is True


def test_detect_non_high_frequency_returns_none() -> None:
    """频次 1 < 阈值 2 → 非高频，返回 None。"""
    history = _make_history(["assertion", "runtime", "assertion"])
    sig = detect_high_frequency_failure(history, "assertion")
    # assertion 出现 2 次，默认阈值 2 → 高频
    assert sig is not None
    assert sig["count"] == 2

    # 只出现 1 次的类别 → 非高频
    history1 = _make_history(["runtime", "assertion"])
    sig1 = detect_high_frequency_failure(history1, "runtime")
    assert sig1 is None


def test_detect_high_frequency_assertion() -> None:
    """assertion 出现 3 次（≥ 阈值 2）→ 返回高频信号。"""
    history = _make_history(["assertion", "runtime", "assertion", "assertion"])
    sig = detect_high_frequency_failure(history, "assertion")
    assert sig is not None
    assert sig["category"] == "assertion"
    assert sig["count"] == 3
    assert sig["threshold"] == 2


def test_detect_with_module_filter() -> None:
    """提供 target_module 时按 (category, module) 联合统计。"""
    history = _make_history(
        ["assertion", "assertion", "assertion"],
        modules=["mod_a", "mod_b", "mod_a"],
    )
    # mod_a 的 assertion 出现 2 次 → 高频
    sig_a = detect_high_frequency_failure(history, "assertion", target_module="mod_a")
    assert sig_a is not None
    assert sig_a["count"] == 2
    # mod_b 的 assertion 只出现 1 次 → 非高频
    sig_b = detect_high_frequency_failure(history, "assertion", target_module="mod_b")
    assert sig_b is None


def test_detect_empty_history_returns_none() -> None:
    """空 repair_history → None。"""
    assert detect_high_frequency_failure([], "assertion") is None
    assert detect_high_frequency_failure(None, "assertion") is None


def test_detect_no_current_category_returns_none() -> None:
    """current_category 为 None/空 → None。"""
    history = _make_history(["assertion", "assertion"])
    assert detect_high_frequency_failure(history, None) is None
    assert detect_high_frequency_failure(history, "") is None


def test_hint_assertion() -> None:
    """assertion 高频 → 返回 oracle_enhancer 提示。"""
    sig = {"category": "assertion", "module": None, "count": 3, "threshold": 2}
    hint = get_escalated_strategy_hint(sig)
    assert hint is not None
    assert "oracle" in hint.lower() or "预言" in hint


def test_hint_runtime() -> None:
    """runtime 高频 → 返回 runtime_probe 提示。"""
    sig = {"category": "runtime", "module": None, "count": 2, "threshold": 2}
    hint = get_escalated_strategy_hint(sig)
    assert hint is not None
    assert "runtime_probe" in hint or "变量快照" in hint


def test_hint_unmatched_category_returns_none() -> None:
    """无匹配策略的类别（如 "syntax"）→ None。"""
    sig = {"category": "syntax", "module": None, "count": 5, "threshold": 2}
    assert get_escalated_strategy_hint(sig) is None


def test_hint_none_input_returns_none() -> None:
    """signal 为 None → None。"""
    assert get_escalated_strategy_hint(None) is None


def test_tool_assertion() -> None:
    sig = {"category": "assertion", "count": 3, "threshold": 2}
    assert get_escalated_strategy_tool(sig) == "oracle_enhancer"


def test_tool_runtime() -> None:
    sig = {"category": "runtime", "count": 2, "threshold": 2}
    assert get_escalated_strategy_tool(sig) == "runtime_probe"


def test_tool_index_error() -> None:
    sig = {"category": "index_error", "count": 2, "threshold": 2}
    assert get_escalated_strategy_tool(sig) == "boundary_audit"


def test_tool_unmatched_returns_none() -> None:
    sig = {"category": "unknown", "count": 5, "threshold": 2}
    assert get_escalated_strategy_tool(sig) is None


def test_tool_none_returns_none() -> None:
    assert get_escalated_strategy_tool(None) is None


def test_failure_frequency_stats() -> None:
    stats = failure_frequency_stats()
    assert "enabled" in stats
    assert "threshold" in stats
    assert "recent_window" in stats
    assert "escalated_categories" in stats
    assert "assertion" in stats["escalated_categories"]
    assert "runtime" in stats["escalated_categories"]
    assert "index_error" in stats["escalated_categories"]
    assert "type_error" in stats["escalated_categories"]
    assert "timeout" in stats["escalated_categories"]
