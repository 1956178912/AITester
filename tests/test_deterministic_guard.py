"""
P2 确定性守卫（src/agents/deterministic_guard.py）回归测试。

外部参照：AltTester 确定性工作流（"生成时用 LLM 写测试，保留确定性测试
套件，运行时无模型、无 token、每次结果相同"）+ 2026 年 LLM 非确定性
风险研究。覆盖：
- 开关默认关：任意内容恒判定确定性（历史口径零变化）；
- 随机数 / 长等待 / 墙钟 / 外部副作用四类规则命中与豁免口径；
- GuardReport.is_deterministic 汇总语义。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.deterministic_guard import (
    GuardReport,
    deterministic_guard_enabled,
    guard_generated_test,
    scan_test_file,
)


def _enable(monkeypatch):
    monkeypatch.setenv("DETERMINISTIC_GUARD_ENABLE", "true")


def _rules(report: GuardReport) -> set[str]:
    return {f.rule for f in report.findings}


class TestDefaultOff:
    def test_default_off_is_always_deterministic(self):
        assert deterministic_guard_enabled() is False
        r = guard_generated_test("import random\ndef t():\n    random.random()\n")
        assert r.is_deterministic
        assert r.findings == []


class TestGuardRules:
    def test_clean_test_passes(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file(
            "def test_add():\n    assert _add(1, 2) == 3\n\n\ndef _add(a, b):\n    return a + b\n"
        )
        assert r.is_deterministic

    def test_random_usage_flagged(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("import random\n\ndef test_x():\n    assert random.randint(1, 10) > 0\n")
        assert "random_usage" in _rules(r)

    def test_numpy_random_flagged(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("import numpy as np\n\ndef test_x():\n    np.random.seed(1)\n")
        assert "random_usage" in _rules(r)

    def test_short_sleep_exempt(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("import time\n\ndef test_x():\n    time.sleep(0.1)\n    assert True\n")
        assert "long_sleep" not in _rules(r)
        assert r.is_deterministic

    def test_long_sleep_flagged(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("import time\n\ndef test_x():\n    time.sleep(5)\n")
        assert "long_sleep" in _rules(r)

    def test_unbounded_sleep_flagged(self, monkeypatch):
        _enable(monkeypatch)
        # 非常量参数（无法判定阈值）保守计入
        r = scan_test_file("import time\n\ndef test_x(wait):\n    time.sleep(wait)\n")
        assert "long_sleep" in _rules(r)

    def test_sleep_threshold_env(self, monkeypatch):
        _enable(monkeypatch)
        monkeypatch.setenv("DETERMINISTIC_GUARD_SLEEP_THRESHOLD", "10")
        r = scan_test_file("import time\n\ndef test_x():\n    time.sleep(5)\n")
        assert "long_sleep" not in _rules(r)

    def test_wall_clock_flagged(self, monkeypatch):
        _enable(monkeypatch)
        # 守卫口径：墙钟调用须经 `import 后 模块.属性` 形式（time.time）；
        # `import time.time` 直绑形式不展开（保守防误伤，由 2.2 重采样口径兜底）
        r = scan_test_file("import time\n\ndef test_x():\n    time.time()\n")
        assert "wall_clock" in _rules(r)

    def test_wall_clock_imported_form_not_flagged(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("from time import time\n\ndef test_x():\n    time()\n")
        assert "wall_clock" not in _rules(r)

    def test_external_modules_flagged(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file(
            "import requests\nimport subprocess\n\ndef test_x():\n    requests.get('http://x')\n    subprocess.run(['ls'])\n"
        )
        assert "external_side_effect" in _rules(r)

    def test_syntax_error_returns_clean(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("def broken(:\n    pass\n")
        assert r.is_deterministic  # 语法错由 2.2 重采样口径兜底，守卫不叠加

    def test_report_lines_captured(self, monkeypatch):
        _enable(monkeypatch)
        r = scan_test_file("import random\n\ndef test_x():\n    random.random()\n")
        assert any(f.line > 0 for f in r.findings)
