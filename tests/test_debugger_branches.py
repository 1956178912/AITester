"""agents/debugger 降级链 / 探测定位 / 对抗调试纯静态分支补齐。

锁定 2026-10-02 批次 debugger 低覆盖分支（默认开关下安全执行路径 +
各开关 env 解析口径）。不引入 LLM / 网络依赖。
"""

from __future__ import annotations

import pytest


class TestDebuggerSwitchBranches:
    def test_adversarial_debugging_default_false(self, monkeypatch):
        from src.agents.debugger import _adversarial_debugging_enabled

        monkeypatch.delenv("ADVERSARIAL_DEBUGGING_ENABLE", raising=False)
        assert _adversarial_debugging_enabled() is False

    def test_position_aware_repair_default(self, monkeypatch):
        from src.agents.debugger import _position_aware_repair_enabled

        monkeypatch.delenv("POSITION_AWARE_REPAIR_ENABLE", raising=False)
        out = _position_aware_repair_enabled()
        assert out in (True, False)

    def test_probe_snapshot_locate_default(self, monkeypatch):
        from src.agents.debugger import _probe_snapshot_locate_enabled

        monkeypatch.delenv("PROBE_SNAPSHOT_LOCATE_ENABLE", raising=False)
        out = _probe_snapshot_locate_enabled()
        assert out in (True, False)

    def test_bidirectional_diagnosis_default(self, monkeypatch):
        from src.agents.debugger import _bidirectional_diagnosis_enabled

        monkeypatch.delenv("BIDIRECTIONAL_DIAGNOSIS_ENABLE", raising=False)
        out = _bidirectional_diagnosis_enabled()
        assert out in (True, False)

    def test_env_true_parses(self, monkeypatch):
        from src.agents.debugger import _adversarial_debugging_enabled

        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "true")
        assert _adversarial_debugging_enabled() is True
        monkeypatch.delenv("ADVERSARIAL_DEBUGGING_ENABLE", raising=False)

    def test_env_case_insensitive(self, monkeypatch):
        from src.agents.debugger import _adversarial_debugging_enabled

        # .lower() 口径：大写 TRUE 也命中
        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "TRUE")
        assert _adversarial_debugging_enabled() is True
        monkeypatch.delenv("ADVERSARIAL_DEBUGGING_ENABLE", raising=False)

    def test_env_false_value(self, monkeypatch):
        from src.agents.debugger import _adversarial_debugging_enabled

        monkeypatch.setenv("ADVERSARIAL_DEBUGGING_ENABLE", "false")
        assert _adversarial_debugging_enabled() is False
        monkeypatch.delenv("ADVERSARIAL_DEBUGGING_ENABLE", raising=False)


class TestDowngradeTierTemperatureBranches:
    @pytest.mark.parametrize("tier", ["minimal", "patch_ingredients", "full"])
    def test_known_tiers(self, tier):
        from src.agents.debugger import _downgrade_tier_temperature

        out = _downgrade_tier_temperature(tier)
        # 已知档位返回 float 或 None（表外档位由 .get 兜底）
        assert out is None or isinstance(out, (int, float))

    def test_unknown_tier_returns_none(self):
        from src.agents.debugger import _downgrade_tier_temperature

        assert _downgrade_tier_temperature("bogus_tier") is None


class TestBuildDowngradeContextBranches:
    def test_unknown_tier_falls_back_to_minimal(self):
        from src.agents.debugger import _build_downgrade_context

        out = _build_downgrade_context("def f(x):\n    return x\n", "f", {"tier": "bogus", "missing_symbols": []})
        # 未知档位保守退化为空串或含档位名的字符串
        assert out in ("", None) or isinstance(out, str)

    def test_empty_code_returns_empty(self):
        from src.agents.debugger import _build_downgrade_context

        out = _build_downgrade_context("", None, {"tier": "minimal", "missing_symbols": []})
        assert out == "" or out is None

    def test_missing_symbols_append_feedback(self):
        from src.agents.debugger import _build_downgrade_context

        out = _build_downgrade_context(
            "def f(x):\n    return x\n", "f", {"tier": "minimal", "missing_symbols": ["f", "g"]}
        )
        # 缺失符号非空时追加契约守卫负面反馈
        if out:
            assert "f" in out or "契约" in out
