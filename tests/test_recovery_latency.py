"""P1-B（2026-10-12 独立评审落地）：MTTR-A 式认知恢复延迟测试。

锁定口径：
    - 端点缺失 → None（"不可测量"绝不是 0.0——零延迟是神话）；
    - 端点逆序 → ValueError（负延迟是数据错误，不是快恢复）；
    - 未知事件 kind → ValueError（闭合集合）；
    - 聚合中位数为主口径（右偏分布），None 不进统计；
    - 特异性未验证时带标记（检测延迟仍计算但消费方须知情）。
"""

from __future__ import annotations

import pytest

from src.measurement.recovery_latency import (
    RecoveryLatency,
    compute_recovery_latency,
    summarize_recovery_latencies,
)


def _events(*pairs: tuple[str, float]) -> list[dict]:
    return [{"kind": kind, "ts": ts} for kind, ts in pairs]


class TestComputeRecoveryLatency:
    def test_full_pipeline(self) -> None:
        events = _events(
            ("failure_observed", 100.0),
            ("effective_red_generated", 106.21),  # MTTR-A LangGraph 参考中位 ~6.21s
            ("patch_synthesized", 120.0),
            ("gold_adjudicated_pass", 131.5),
        )
        result = compute_recovery_latency(events)
        assert result.detection_latency == pytest.approx(6.21)
        assert result.reconfiguration_latency == pytest.approx(11.5)
        assert result.events_seen == 4
        assert not result.specificity_unverified

    def test_missing_endpoint_yields_none(self) -> None:
        """任一端点缺失 → None（不冒充 0.0）。"""
        events = _events(("failure_observed", 100.0))  # 无 effective_red
        result = compute_recovery_latency(events)
        assert result.detection_latency is None
        assert result.reconfiguration_latency is None

    def test_none_and_empty_events(self) -> None:
        assert compute_recovery_latency(None).detection_latency is None
        assert compute_recovery_latency([]).detection_latency is None

    def test_negative_latency_raises(self) -> None:
        """端点逆序 = 数据错误（时钟混用 / 事件乱序），必须显式失败。"""
        events = _events(
            ("effective_red_generated", 90.0),
            ("failure_observed", 100.0),
        )
        with pytest.raises(ValueError, match="逆序"):
            compute_recovery_latency(events)

    def test_unknown_event_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="未知事件 kind"):
            compute_recovery_latency([{"kind": "magic", "ts": 1.0}])

    def test_specificity_unverified_flagged(self) -> None:
        events = _events(
            ("failure_observed", 100.0),
            ("effective_red_generated", 105.0),
        )
        result = compute_recovery_latency(events, specificity_verified=False)
        assert result.detection_latency == pytest.approx(5.0)
        assert result.specificity_unverified is True
        assert result.as_dict()["specificity_unverified"] is True

    def test_as_dict_none_survives_serialization(self) -> None:
        """None 恒序列化为 None（下游 JSON 消费方不得误读为 0）。"""
        payload = compute_recovery_latency(_events(("failure_observed", 1.0))).as_dict()
        assert payload["detection_latency"] is None
        assert payload["reconfiguration_latency"] is None

    def test_first_event_wins(self) -> None:
        """同 kind 多次出现取首次（恢复延迟度量的是首次恢复）。"""
        events = _events(
            ("failure_observed", 100.0),
            ("effective_red_generated", 110.0),
            ("effective_red_generated", 200.0),
        )
        assert compute_recovery_latency(events).detection_latency == pytest.approx(10.0)


class TestSummarizeRecoveryLatencies:
    def test_none_excluded_from_stats(self) -> None:
        """None 不进统计——平均只覆盖实际有测量的任务。"""
        measured = compute_recovery_latency(
            _events(
                ("failure_observed", 0.0),
                ("effective_red_generated", 6.0),
            )
        )
        unmeasured = compute_recovery_latency(_events(("failure_observed", 0.0)))
        summary = summarize_recovery_latencies([measured, unmeasured])
        assert summary.n_total == 2
        assert summary.n_detection_measured == 1
        assert summary.detection_median == pytest.approx(6.0)
        assert summary.detection_mean == pytest.approx(6.0)

    def test_median_primary_for_skewed_distribution(self) -> None:
        """右偏分布下中位数为主口径（MTTR-A 一手口径即 median）。"""
        tasks = [
            compute_recovery_latency(_events(("failure_observed", 0.0), ("effective_red_generated", 5.0))),
            compute_recovery_latency(_events(("failure_observed", 0.0), ("effective_red_generated", 6.0))),
            compute_recovery_latency(_events(("failure_observed", 0.0), ("effective_red_generated", 7.0))),
            compute_recovery_latency(_events(("failure_observed", 0.0), ("effective_red_generated", 1000.0))),
        ]
        summary = summarize_recovery_latencies(tasks)
        assert summary.detection_median == pytest.approx(6.5)  # (6+7)/2
        assert summary.detection_mean == pytest.approx(254.5)  # 被离群值拉高——故 median 为主

    def test_empty_summary(self) -> None:
        summary = summarize_recovery_latencies([])
        assert summary.n_total == 0
        assert summary.detection_median is None
        assert summary.detection_mean is None

    def test_specificity_unverified_counted(self) -> None:
        tasks = [
            compute_recovery_latency(
                _events(("failure_observed", 0.0), ("effective_red_generated", 1.0)), specificity_verified=False
            ),
            RecoveryLatency(specificity_unverified=True),
        ]
        summary = summarize_recovery_latencies(tasks)
        assert summary.specificity_unverified_n == 2
