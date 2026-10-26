"""EF（2026-10-27）：浮点环境值的非有限值（NaN/±inf）静默改写控制流。

缺陷族（自查实证）：`config.py::_parse_float_env` 与
`src/utils/env_utils.py::env_float` 都已确立「非有限值 ⇒ 告警 + 回退默认值」
口径（`math.isfinite` 判定），但 `src/` 内仍有 6 个本地浮点解析点只捕
`ValueError`——而 `float("nan")` / `float("inf")` 根本不抛 `ValueError`：

- `deterministic_guard._sleep_threshold`：阈值原样返回，扫描里
  `arg_val > threshold` 对 NaN/inf 恒 False ⇒ `long_sleep` 规则被静默关闭；
- `semantic_cache._semantic_threshold`：`max(0.0, min(1.0, nan))` 把 NaN/inf
  夹成 1.0（缓存永不命中），`-inf` 夹成 0.0（任何最相似条目都被当命中返回，
  可能复用无关响应）；
- `semantic_cache._false_positive_sampling_rate`：同上，NaN/inf 夹成 1.0 ⇒
  每次命中都触发额外 LLM 抽样（成本失控），`-inf` 夹成 0.0 ⇒ 抽样静默关闭；
- `workflow._coverage_stall_eps`：`abs(delta) >= nan` 恒 False ⇒ 最近每一轮
  都判「覆盖率停滞」并提前终止；inf 同向；
- `risk_approval._env_float`：NaN 夹成上界 ⇒ `RISK_THRESHOLD_MEDIUM=nan`
  变成 1.0，medium/high 永不可达，人工审批回路被静默绕过；
- `failure_kb._decay_half_life_days`：NaN 经 `0.5 ** (age/NaN)` 把排序得分
  变成 NaN（`score <= 0` 恒 False、排序键不可比），失败知识库排序静默失真。

既有锁只覆盖「非法字符串」（如 `SEMANTIC_CACHE_THRESHOLD=高`），非有限值
全部放行——正是 `_parse_float_env` docstring 点名的「只做范围检查会让坏阈值
静默穿透」。修法 = 解析委托 `env_float`（非有限 → WARNING + 默认值），有限值
的既有钳制口径逐字保留。

每例先锁默认/有限值路径不变，再断言非有限值回退——只断言「不返回 nan」会
放过「静默夹到边界」这一真正的缺陷形态。
"""

from __future__ import annotations

import logging

import pytest

from src.agents import deterministic_guard as dg
from src.agents import failure_kb as fkb
from src.agents import semantic_cache as sc
from src.graph import risk_approval as ra
from src.graph import workflow as wf

# float() 接受的非有限字面量（含大小写与科学计数法溢出形态）
_NONFINITE = ("nan", "NaN", "inf", "-inf", "Infinity", "1e999")


@pytest.mark.unit
class TestNonFiniteEnvFallsBackToDefault:
    """5 个本地浮点解析点：非有限值一律回退文档口径的默认值。"""

    @pytest.mark.parametrize("raw", _NONFINITE)
    def test_sleep_threshold_falls_back(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("DETERMINISTIC_GUARD_SLEEP_THRESHOLD", raw)
        assert dg._sleep_threshold() == pytest.approx(0.5)

    @pytest.mark.parametrize("raw", _NONFINITE)
    def test_semantic_threshold_falls_back(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", raw)
        assert sc._semantic_threshold() == pytest.approx(0.92)

    @pytest.mark.parametrize("raw", _NONFINITE)
    def test_false_positive_sampling_falls_back(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", raw)
        assert sc._false_positive_sampling_rate() == pytest.approx(0.1)

    @pytest.mark.parametrize("raw", _NONFINITE)
    def test_coverage_stall_eps_falls_back(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("COVERAGE_STALL_EPS", raw)
        assert wf._coverage_stall_eps() == pytest.approx(0.5)

    @pytest.mark.parametrize("raw", _NONFINITE)
    def test_risk_env_float_falls_back(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("AITESTER_EF_RISK_FLOAT", raw)
        assert ra._env_float("AITESTER_EF_RISK_FLOAT", 0.33, 0.0, 1.0) == pytest.approx(0.33)

    @pytest.mark.parametrize("raw", _NONFINITE)
    def test_failure_kb_decay_falls_back(self, monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
        monkeypatch.setenv("FAILURE_KB_DECAY_DAYS", raw)
        assert fkb._decay_half_life_days() == pytest.approx(30.0)


@pytest.mark.unit
class TestFiniteCaliberUnchanged:
    """回归锁：有限值的既有口径（钳制 / 原样采用）不得被本轮改动。"""

    def test_out_of_range_finite_still_clamps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "5")
        assert sc._semantic_threshold() == pytest.approx(1.0)
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "-5")
        assert sc._semantic_threshold() == pytest.approx(0.0)
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "3")
        assert sc._false_positive_sampling_rate() == pytest.approx(1.0)
        monkeypatch.setenv("AITESTER_EF_RISK_FLOAT", "5")
        assert ra._env_float("AITESTER_EF_RISK_FLOAT", 0.33, 0.0, 1.0) == pytest.approx(1.0)
        monkeypatch.setenv("AITESTER_EF_RISK_FLOAT", "-5")
        assert ra._env_float("AITESTER_EF_RISK_FLOAT", 0.33, 0.0, 1.0) == pytest.approx(0.0)

    def test_in_range_finite_still_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETERMINISTIC_GUARD_SLEEP_THRESHOLD", "2.5")
        assert dg._sleep_threshold() == pytest.approx(2.5)
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "0.75")
        assert sc._semantic_threshold() == pytest.approx(0.75)
        monkeypatch.setenv("COVERAGE_STALL_EPS", "2.5")
        assert wf._coverage_stall_eps() == pytest.approx(2.5)


@pytest.mark.unit
class TestBehaviorConsequences:
    """非有限值不得静默改写控制流（每个站点一条行为锁）。"""

    def test_nan_threshold_does_not_disable_long_sleep_rule(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`long_sleep` 守卫：NaN 阈值此前让 `sleep(5)` 免检。"""
        monkeypatch.setenv("DETERMINISTIC_GUARD_ENABLE", "true")
        monkeypatch.setenv("DETERMINISTIC_GUARD_SLEEP_THRESHOLD", "nan")
        report = dg.scan_test_file("import time\n\ndef test_x():\n    time.sleep(5)\n")
        assert "long_sleep" in {f.rule for f in report.findings}

    def test_inf_threshold_does_not_disable_long_sleep_rule(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DETERMINISTIC_GUARD_ENABLE", "true")
        monkeypatch.setenv("DETERMINISTIC_GUARD_SLEEP_THRESHOLD", "inf")
        report = dg.scan_test_file("import time\n\ndef test_x():\n    time.sleep(5)\n")
        assert "long_sleep" in {f.rule for f in report.findings}

    def test_neg_inf_threshold_does_not_reuse_unrelated_entry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """语义缓存：-inf 此前夹成 0.0，0.71 相似度的无关条目也被当命中返回。"""
        monkeypatch.setattr(sc, "_semantic_cache_enabled", lambda: True)
        monkeypatch.setattr(
            "src.utils.embedding_utils.embed_text",
            lambda prompt: [0.7071067811865476, 0.7071067811865476],
        )
        index = sc.get_semantic_index()
        index._entries.clear()
        index._entries["/tmp/ef-unrelated.json"] = sc._SemanticEntry(
            cache_file="/tmp/ef-unrelated.json", prompt="p", response="r", embedding=[1.0, 0.0]
        )
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "-inf")
        assert index.find("query") is None

    def test_nan_eps_does_not_force_coverage_stall(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """覆盖率停滞：NaN eps 此前让大幅增长（delta=5.0）的窗口也判「停滞」。"""
        monkeypatch.setenv("COVERAGE_STALL_DETECT_ENABLE", "true")
        monkeypatch.setenv("COVERAGE_STALL_ROUNDS", "2")
        monkeypatch.setenv("COVERAGE_STALL_EPS", "nan")
        state = {
            "test_passed": False,
            "execution_trace": [
                {"passed": False, "coverage_delta": 5.0},
                {"passed": False, "coverage_delta": 5.0},
            ],
        }
        assert wf._coverage_stall_detected(state) is False

    def test_nan_rate_does_not_sample_every_hit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """假阳性抽样：NaN 此前夹成 1.0，每次命中都触发额外 LLM 抽样。"""
        monkeypatch.setattr(sc, "_fp_sample_counter", 0)
        monkeypatch.setenv("SEMANTIC_FALSE_POSITIVE_SAMPLING", "nan")
        assert sc.should_sample_false_positive() is False

    def test_nan_threshold_keeps_default_risk_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """风险分级：NaN 此前夹成 1.0，medium/high 永不可达（审批回路绕过）。"""
        for name in (
            "RISK_WEIGHT_CONFIDENCE",
            "RISK_WEIGHT_IMPACT",
            "RISK_WEIGHT_BUDGET",
            "RISK_THRESHOLD_MEDIUM",
            "RISK_THRESHOLD_HIGH",
        ):
            monkeypatch.delenv(name, raising=False)
        baseline = ra.assess_task_risk(confidence=0.5, changed_lines=100, changed_files=5)
        assert baseline.risk_level == "medium"
        monkeypatch.setenv("RISK_THRESHOLD_MEDIUM", "nan")
        with_nan = ra.assess_task_risk(confidence=0.5, changed_lines=100, changed_files=5)
        assert with_nan.risk_level == baseline.risk_level
        assert float(with_nan.risk_score) == pytest.approx(float(baseline.risk_score))

    def test_nan_decay_does_not_corrupt_knowledge_ranking(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """失败知识库：NaN 半衰期此前让得分变 NaN，排序静默退回插入序。"""
        now = 1_700_000_000.0
        day = 86400.0
        fresh = {"error_category": "assertion", "last_seen": now - 1 * day, "id": "fresh"}
        old = {"error_category": "assertion", "last_seen": now - 300 * day, "id": "old"}
        baseline = [e["id"] for e in fkb.rank_knowledge_entries([old, fresh], "assertion", now=now)]
        assert baseline == ["fresh", "old"]
        monkeypatch.setenv("FAILURE_KB_DECAY_DAYS", "nan")
        with_nan = [e["id"] for e in fkb.rank_knowledge_entries([old, fresh], "assertion", now=now)]
        assert with_nan == baseline


@pytest.mark.unit
class TestNonFiniteIsLoud:
    """「回退」必须伴随 WARNING（点名变量），否则仍是静默降级。"""

    def test_semantic_threshold_warns(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setenv("SEMANTIC_CACHE_THRESHOLD", "nan")
        with caplog.at_level(logging.WARNING):
            sc._semantic_threshold()
        assert "SEMANTIC_CACHE_THRESHOLD" in caplog.text
        assert "非有限值" in caplog.text

    def test_coverage_stall_eps_warns(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setenv("COVERAGE_STALL_EPS", "inf")
        with caplog.at_level(logging.WARNING):
            wf._coverage_stall_eps()
        assert "COVERAGE_STALL_EPS" in caplog.text
        assert "非有限值" in caplog.text

    def test_risk_env_float_warns(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setenv("AITESTER_EF_RISK_FLOAT", "-inf")
        with caplog.at_level(logging.WARNING):
            ra._env_float("AITESTER_EF_RISK_FLOAT", 0.33, 0.0, 1.0)
        assert "AITESTER_EF_RISK_FLOAT" in caplog.text
        assert "非有限值" in caplog.text

    def test_failure_kb_decay_warns(self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
        monkeypatch.setenv("FAILURE_KB_DECAY_DAYS", "nan")
        with caplog.at_level(logging.WARNING):
            fkb._decay_half_life_days()
        assert "FAILURE_KB_DECAY_DAYS" in caplog.text
        assert "非有限值" in caplog.text
