"""AI 批次测试（2026-10-06 第十一轮审查漏配审计落地）。

背景：ab1_validation 的 provenance env 快照 + 生死实验工件审计发现
logic 档唯一漏配 FL_SPECTRAL_ENABLE——fl_spectral（Ochiai）经第四轮
C3 修复后从未接入 logic 档，导致全部 logic 档批次 fl_at_k 恒空
（生死实验实测 0/87），定位质量指标在 E2 复跑前缺数。AI1 补齐
（AA1 同类"漏配补齐"先例：DETECTION_FIRST_ENABLE 亦为档位定义早于
能力落地所致）。

覆盖：
- AI1a logic 档实验开关完整性锁——13 个实验相关开关必须全部注入
  （防"档位定义早于能力落地"类漏配再发：新实验开关落地时必须显式
  更新本集合）；
- AI1b 行为级注入验证（FL_SPECTRAL_ENABLE 经 _apply_profile_presets
  实际生效；显式 env 不被覆盖——setdefault 口径）；
- AI1c 刻意不注入说明：AGENT_TELEMETRY_ENABLE 不入 logic 档（MAST
  失效模式已由 AG1 离线分析覆盖，避免运行时开销与双重口径）。

全部纯 stdlib / 零 LLM / 零网络 / 零子进程。
"""

from __future__ import annotations

import os as _os
from typing import ClassVar

import pytest

from config import _PROFILE_PRESETS, _apply_profile_presets


class TestLogicProfileCompleteness:
    """logic 档 = 实验主口径档——实验相关开关必须零漏配。

    审计依据（2026-10-06）：生死实验 ab1_validation env 快照
    FL_SPECTRAL_ENABLE=None 与 fl_at_k 0/87 全空互为因果实证。
    """

    _INJECTED: ClassVar[list[str]] = sorted(_PROFILE_PRESETS["logic"])

    # 实验相关开关全集：新增实验开关落地时，必须同步进入本集合并经
    # 审查确认是否应入 logic 档（漏配 = 该维度在主口径批次缺数）。
    _EXPERIMENT_SWITCHES: ClassVar[tuple[str, ...]] = (
        # 检出优先协议（ADR-0015 / W3 / AC2 双门）
        "DETECTION_FIRST_ENABLE",
        "DETECTION_SPECIFICITY_GATE_ENABLE",
        "RED_REGRESSION_GATE_ENABLE",
        # 规约链（AC1 契约 / U12 SMT / R1c oracle 执行）
        "SPEC_IR_ENABLE",
        "SPEC_IR_DSL_ENABLE",
        "SPEC_SMT_ENABLE",
        "SPEC_ORACLE_EXEC_ENABLE",
        "LOGIC_SPEC_STRICT_ENABLE",
        "LOGIC_SPEC_STRICT_FALLBACK_ENABLE",
        # 测试质量与定位（E3 全指标口径）
        "ENABLE_MUTATION_SCORING",
        "FL_SPECTRAL_ENABLE",
        # 回滚安全（R4b fail-closed）
        "PATCH_SNAPSHOT_ROLLBACK_ENABLE",
        "PATCH_ROLLBACK_FAIL_CLOSED",
    )

    @pytest.fixture(autouse=True)
    def _cleanup_env(self):
        """动态全键清理（AA 教训：静态枚举会在档位扩键时漏清理）。"""
        saved = {k: _os.environ.get(k) for k in self._INJECTED}
        for k in self._INJECTED:
            _os.environ.pop(k, None)
        yield
        for k, v in saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v

    def test_all_experiment_switches_injected_true(self):
        """13 个实验相关开关在 logic 档全部注入且为 true。"""
        logic = _PROFILE_PRESETS["logic"]
        missing = [k for k in self._EXPERIMENT_SWITCHES if logic.get(k) != "true"]
        assert missing == [], (
            f"logic 档漏配实验开关（漏配维度在主口径批次缺数）：{missing}；新增开关须同步更新 _EXPERIMENT_SWITCHES 集合"
        )

    def test_fl_spectral_actually_applied(self, monkeypatch):
        """行为级：profile=logic 时 FL_SPECTRAL_ENABLE 真实生效。"""
        monkeypatch.setenv("AITESTER_PROFILE", "logic")
        assert _apply_profile_presets() == "logic"
        assert _os.environ.get("FL_SPECTRAL_ENABLE") == "true"

    def test_explicit_env_wins_over_profile(self, monkeypatch):
        """显式 env 不被 profile 覆盖（setdefault 口径，历史实验可显式关 FL）。"""
        monkeypatch.setenv("AITESTER_PROFILE", "logic")
        monkeypatch.setenv("FL_SPECTRAL_ENABLE", "false")
        _apply_profile_presets()
        assert _os.environ.get("FL_SPECTRAL_ENABLE") == "false"

    def test_default_profile_unaffected(self, monkeypatch):
        """不设 PROFILE 时零注入（默认档历史口径不变）。"""
        _apply_profile_presets()
        assert _os.environ.get("FL_SPECTRAL_ENABLE") is None

    def test_telemetry_deliberately_absent(self):
        """AGENT_TELEMETRY_ENABLE 刻意不入 logic 档（文档化决策）。

        MAST 失效模式已由 AG1 离线分析（experiments/mast_trace_analysis.py）
        覆盖——离线路径可从入库 trace 逐位复算且零运行时开销，优于
        运行时双重口径。若未来需要运行时 MAST 字段入报告，须显式修订
        本测试与本注释。
        """
        assert "AGENT_TELEMETRY_ENABLE" not in _PROFILE_PRESETS["logic"]
