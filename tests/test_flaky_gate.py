"""
R35/R31（2026-09-30 独立审查 P0）：flaky 门禁单元测试。

覆盖：
- classify_flaky 纯数据分类（全 pass / 全 fail / 混合 / 空列表）
- flaky_repeat_count 默认值 / 环境变量覆盖 / 非法值兜底
- flaky_check_enabled 开关解析
- detect_flaky 对 mock executor 的重复执行（flaky / 稳定失败 / 异常降级）
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.flaky_gate import (
    classify_flaky,
    detect_flaky,
    flaky_check_enabled,
    flaky_repeat_count,
)


class TestClassifyFlaky:
    """纯数据分类口径。"""

    def test_all_pass_not_flaky(self):
        cls = classify_flaky([True, True, True])
        assert cls["flaky"] is False
        assert cls["pass_count"] == 3
        assert cls["fail_count"] == 0

    def test_all_fail_not_flaky(self):
        cls = classify_flaky([False, False])
        assert cls["flaky"] is False
        assert cls["pass_count"] == 0
        assert cls["fail_count"] == 2

    def test_mixed_is_flaky(self):
        cls = classify_flaky([True, False, True])
        assert cls["flaky"] is True
        assert cls["pass_count"] == 2
        assert cls["fail_count"] == 1

    def test_empty_list_not_flaky(self):
        cls = classify_flaky([])
        assert cls["flaky"] is False
        assert cls["total"] == 0


class TestSwitches:
    def test_enabled_default_false(self, monkeypatch):
        monkeypatch.delenv("FLAKY_CHECK_ENABLE", raising=False)
        assert flaky_check_enabled() is False

    def test_enabled_truthy(self, monkeypatch):
        monkeypatch.setenv("FLAKY_CHECK_ENABLE", "true")
        assert flaky_check_enabled() is True

    def test_repeat_default_and_override(self, monkeypatch):
        monkeypatch.delenv("FLAKY_REPEAT_COUNT", raising=False)
        assert flaky_repeat_count() == 3
        monkeypatch.setenv("FLAKY_REPEAT_COUNT", "30")
        assert flaky_repeat_count() == 30

    def test_repeat_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("FLAKY_REPEAT_COUNT", "not_a_number")
        assert flaky_repeat_count() == 3


class TestDetectFlaky:
    """对 mock executor 的重复执行检测。"""

    def test_stable_failure(self):
        """全 fail：flaky=False，稳定失败结果可信。"""
        executor = MagicMock()
        executor.execute.return_value = {"passed": False}
        base = {"passed": False}
        cls = detect_flaky(executor, "def t(): pass", "/tmp/target.py", None, base)
        assert cls["flaky"] is False
        assert cls["pass_count"] == 0

    def test_flaky_detected(self):
        """混合：flaky=True，pass_count > 0。"""
        executor = MagicMock()
        # 首轮 fail（base），后续 [True, False, True] → 混合
        executor.execute.side_effect = [
            {"passed": True},
            {"passed": False},
            {"passed": True},
        ]
        base = {"passed": False}
        cls = detect_flaky(executor, "def t(): pass", "/tmp/target.py", None, base)
        assert cls["flaky"] is True
        assert cls["pass_count"] >= 1
        assert cls["fail_count"] >= 1

    def test_exception_degrades_conservatively(self):
        """重复执行异常时保守降级（不阻断，results 截断）。"""
        executor = MagicMock()
        executor.execute.side_effect = [Exception("boom"), {"passed": False}]
        base = {"passed": False}
        cls = detect_flaky(executor, "def t(): pass", "/tmp/target.py", None, base)
        # 首轮 fail + 第一次异常 break → 结果 [False, False] 全 fail，稳定
        assert cls["flaky"] is False
        assert cls["fail_count"] >= 1
