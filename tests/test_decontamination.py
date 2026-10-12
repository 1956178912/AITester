"""P1-B（2026-10-12 独立评审落地）：去污染时间戳过滤测试。

锁定口径（SWE-rebench 对齐）：
    - 严格晚于 cutoff 才保留（同日 = 无法证明先后，保守剔除）；
    - 无时间戳 / 不可解析 → unverifiable（默认剔除；keep_flagged 保留但
      报告层单列，不静默）；
    - 报告对账：kept + dropped_before_cutoff + unverifiable == total。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.datasets.decontamination import (
    decontamination_report,
    filter_tasks_by_created_at,
    parse_created_at,
    task_created_at,
)

# 知识截止：2025-01-31 UTC（epoch 由测试内计算，防硬编码漂移）
_CUTOFF = datetime(2025, 1, 31, tzinfo=UTC).timestamp()


def _task(created: object, tid: str = "t") -> dict:
    return {"task_id": tid, "task_created_at": created}


class TestParseCreatedAt:
    def test_iso8601_with_z(self) -> None:
        ts = parse_created_at("2025-06-01T12:00:00Z")
        assert ts == datetime(2025, 6, 1, 12, 0, 0, tzinfo=UTC).timestamp()

    def test_iso8601_with_offset(self) -> None:
        ts = parse_created_at("2025-06-01T12:00:00+08:00")
        assert ts == datetime(2025, 6, 1, 4, 0, 0, tzinfo=UTC).timestamp()

    def test_date_only_assumes_utc_midnight(self) -> None:
        assert parse_created_at("2025-06-01") == datetime(2025, 6, 1, tzinfo=UTC).timestamp()

    def test_epoch_number(self) -> None:
        assert parse_created_at(1_700_000_000.5) == 1_700_000_000.5

    def test_epoch_numeric_string(self) -> None:
        assert parse_created_at("1700000000") == 1_700_000_000.0

    @pytest.mark.parametrize("bad", [None, "", "   ", "not-a-date", True, False, -1, float("nan"), [1], {"a": 1}])
    def test_unparseable_returns_none(self, bad: object) -> None:
        assert parse_created_at(bad) is None

    def test_naive_datetime_assumed_utc(self) -> None:
        assert parse_created_at("2025-06-01T00:00:00") == datetime(2025, 6, 1, tzinfo=UTC).timestamp()


class TestTaskCreatedAt:
    def test_field_priority(self) -> None:
        task = {"created_at": "2025-06-01", "task_created_at": "2025-07-01"}
        assert task_created_at(task) == datetime(2025, 7, 1, tzinfo=UTC).timestamp()

    def test_fallback_field(self) -> None:
        assert task_created_at({"creation_date": "2025-06-01"}) is not None

    def test_missing_returns_none(self) -> None:
        assert task_created_at({"task_id": "x"}) is None


class TestFilterTasks:
    def test_strictly_after_cutoff_kept(self) -> None:
        tasks = [_task("2025-06-01"), _task("2025-01-31")]
        kept = filter_tasks_by_created_at(tasks, _CUTOFF)
        assert [t["task_id"] for t in kept] == ["t"]
        # 原列表不被修改
        assert len(tasks) == 2

    def test_equal_timestamp_dropped(self) -> None:
        """等于 cutoff 不保留（严格晚于）——同日同时刻无法证明先后。"""
        tasks = [_task("2025-01-31T00:00:00Z")]
        assert filter_tasks_by_created_at(tasks, _CUTOFF) == []

    def test_unverifiable_dropped_by_default(self) -> None:
        tasks = [_task("not-a-date"), _task(None), {"task_id": "no-field"}]
        assert filter_tasks_by_created_at(tasks, _CUTOFF) == []

    def test_keep_flagged_retains_unverifiable(self) -> None:
        tasks = [_task("not-a-date"), _task("2025-06-01")]
        kept = filter_tasks_by_created_at(tasks, _CUTOFF, mode="keep_flagged")
        assert len(kept) == 2  # 未验证的保留（报告层单列，不静默）

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            filter_tasks_by_created_at([], _CUTOFF, mode="launder")


class TestDecontaminationReport:
    def test_counts_reconcile(self) -> None:
        tasks = [
            _task("2025-06-01"),  # kept
            _task("2024-06-01"),  # dropped
            _task("garbage"),  # unverifiable
            {"task_id": "no-field"},  # unverifiable
        ]
        report = decontamination_report(tasks, _CUTOFF)
        assert report["total"] == 4
        assert report["kept"] == 1
        assert report["dropped_before_cutoff"] == 1
        assert report["unverifiable"] == 2
        assert report["kept"] + report["dropped_before_cutoff"] + report["unverifiable"] == report["total"]
        assert report["kept_ratio"] == 0.25
        # 可判定子集的干净比例 = 1/2
        assert report["decontamination_rate"] == 0.5

    def test_empty_input(self) -> None:
        report = decontamination_report([], _CUTOFF)
        assert report["total"] == 0 and report["kept"] == 0
        assert report["kept_ratio"] == 0.0 and report["decontamination_rate"] == 0.0

    def test_all_unverifiable_rate_zero(self) -> None:
        """全部不可验证时 decontamination_rate=0.0（不虚构干净比例）。"""
        report = decontamination_report([_task("x"), {"task_id": "y"}], _CUTOFF)
        assert report["unverifiable"] == 2
        assert report["decontamination_rate"] == 0.0
