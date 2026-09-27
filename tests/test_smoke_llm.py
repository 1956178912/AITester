"""
9. P2 LLM 集成冒烟脚本单元测试（改进清单 P2 #9）。

验证：
- 开关关闭（AITESTER_SMOKE_LLM 缺省 false）时 main() 成功退出（0）且不触发真实调用；
- 响应断言逻辑（_check_response）：空响应 FAIL、非空 PASS（allow-empty）、
  合法短文本 PASS（require-json）、JSON 可提取 PASS；
- 冒烟 prompt 为固定短文本（不夹带代码上下文，成本可控）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from experiments.run_smoke_llm import _check_response, _smoke_enabled, _smoke_prompt


class TestSmokeSkipPath:
    """开关关闭时跳过（历史口径零 LLM 成本）。"""

    def test_smoke_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("AITESTER_SMOKE_LLM", raising=False)
        assert _smoke_enabled() is False

    def test_smoke_enabled_when_true(self, monkeypatch):
        monkeypatch.setenv("AITESTER_SMOKE_LLM", "true")
        assert _smoke_enabled() is True

    def test_main_returns_zero_when_disabled(self, monkeypatch):
        from experiments.run_smoke_llm import main

        monkeypatch.delenv("AITESTER_SMOKE_LLM", raising=False)
        # 解析空参（无 --allow-empty / --require-json）
        monkeypatch.setattr(sys, "argv", ["run_smoke_llm.py"])
        assert main() == 0


class TestResponseCheck:
    """响应断言逻辑（_check_response）。"""

    def test_empty_response_fails(self):
        ok, diag = _check_response("", require_json=False)
        assert not ok
        assert "空" in diag

    def test_non_empty_passes_allow_empty(self):
        ok, _ = _check_response("2", require_json=False)
        assert ok

    def test_short_text_passes_require_json(self):
        """非 JSON 但合法短文本（冒烟 prompt 允许自然语言回答）→ PASS。"""
        ok, _ = _check_response("2", require_json=True)
        assert ok

    def test_extractable_json_passes_require_json(self):
        ok, _ = _check_response('{"answer": "2"}', require_json=True)
        assert ok

    def test_long_malformed_fails_require_json(self):
        """过长且无法 JSON 提取 → FAIL（require_json 口径）。"""
        long_bad = "x" * 1000  # 超过 256 且非合法短文本
        ok, _ = _check_response(long_bad, require_json=True)
        assert not ok


class TestSmokePrompt:
    """冒烟 prompt 固定、短、无代码上下文。"""

    def test_prompt_is_short(self):
        assert len(_smoke_prompt()) < 256


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__, "-v"]))
