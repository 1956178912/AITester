#!/usr/bin/env python3
"""覆盖率收口批次：去污染时间戳解析与原子写清理路径。

动机（EMSE 多轮优化批次·覆盖率收口最后一段）：

- `src/datasets/decontamination.py` 的 `parse_created_at` 是**污染视角**（ADR-0023）
  的时间基准：把布尔/非有限/负数/退化字符串解析成 epoch，误判会让"数据泄漏窗口"
  计算整体偏移（论文的 contamination 分级依赖它）。
- `src/utils/atomic_io.py` 的 finally 清理分支决定"写失败后是否留下半截临时文件"
  （评审曾以"工件被静默损坏"为高风险项）。

覆盖目标（coverage.xml 记录）：decontamination 87/97 行；atomic_io 63/68/69 行。
零 LLM、零网络。
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from src.datasets.decontamination import _CREATED_AT_FIELDS, parse_created_at, task_created_at
from src.utils.atomic_io import atomic_write_json, atomic_write_text


class TestParseCreatedAt:
    """退化输入谱：全部必须返回 None 或正确 epoch，**不得抛异常**。"""

    @pytest.mark.parametrize("value", [True, False])
    def test_bool_is_rejected(self, value: bool):
        """bool 是 int 子类（True→1 秒无意义）→ 必须显式排除。"""
        assert parse_created_at(value) is None

    @pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_numbers_are_rejected(self, value: float):
        assert parse_created_at(value) is None

    @pytest.mark.parametrize("value", [-1, -1.5])
    def test_negative_epoch_is_rejected(self, value: float):
        assert parse_created_at(value) is None

    def test_positive_epoch_passes_through(self):
        assert parse_created_at(1750000000.0) == pytest.approx(1750000000.0)
        assert parse_created_at(1750000000) == pytest.approx(1750000000.0)

    @pytest.mark.parametrize("value", ["nan", "inf", "-inf", "-5"])
    def test_degenerate_numeric_strings_are_rejected(self, value: str):
        """ISO 解析失败回退 epoch 后，仍须过"有限且非负"门。"""
        assert parse_created_at(value) is None

    def test_numeric_string_is_treated_as_epoch(self):
        assert parse_created_at("1750000000") == pytest.approx(1750000000.0)

    @pytest.mark.parametrize("value", ["", "   ", "not a date", "2026-13-45"])
    def test_unparsable_strings_return_none(self, value: str):
        assert parse_created_at(value) is None

    @pytest.mark.parametrize("value", [None, [], {}, 3 + 4j])
    def test_non_string_non_number_returns_none(self, value: object):
        assert parse_created_at(value) is None

    def test_iso_with_z_suffix_is_utc(self):
        assert parse_created_at("2026-10-15T10:00:00Z") == pytest.approx(1792058400.0)

    def test_iso_without_timezone_is_assumed_utc(self):
        naive = parse_created_at("2026-10-15T10:00:00")
        aware = parse_created_at("2026-10-15T10:00:00+00:00")
        assert naive == pytest.approx(aware)


class TestTaskCreatedAt:
    def test_non_dict_returns_none(self):
        assert task_created_at(None) is None
        assert task_created_at("x") is None  # type: ignore[arg-type]

    def test_first_field_wins_when_parsable(self):
        task = {_CREATED_AT_FIELDS[0]: 1750000000, _CREATED_AT_FIELDS[1]: 1}
        assert task_created_at(task) == pytest.approx(1750000000.0)

    def test_unparsable_field_falls_through_to_next(self):
        """第一个字段存在但不可解析 → 继续探测后续字段（不因坏值放弃整条）。"""
        task = {_CREATED_AT_FIELDS[0]: "bogus", _CREATED_AT_FIELDS[1]: 1750000000}
        assert task_created_at(task) == pytest.approx(1750000000.0)

    def test_no_known_field_returns_none(self):
        assert task_created_at({"unrelated": 1}) is None

    def test_all_fields_unparsable_returns_none(self):
        task = {field: "bogus" for field in _CREATED_AT_FIELDS}
        assert task_created_at(task) is None


class TestAtomicWriteCleanup:
    def test_write_text_then_read_back(self, tmp_path: Path):
        target = tmp_path / "out.txt"
        atomic_write_text(str(target), "hello")
        assert target.read_text(encoding="utf-8") == "hello"

    def test_write_json_roundtrip(self, tmp_path: Path):
        import json

        target = tmp_path / "out.json"
        atomic_write_json(str(target), {"k": 1})
        assert json.loads(target.read_text(encoding="utf-8")) == {"k": 1}

    def test_failure_leaves_no_temp_file_and_keeps_old_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """写失败 → 目标文件保持旧内容、临时文件被清理（finally 分支）。"""
        import src.utils.atomic_io as atomic_io

        target = tmp_path / "keep.txt"
        target.write_text("original", encoding="utf-8")
        before = {p.name for p in tmp_path.iterdir()}

        real_replace = os.replace

        def _boom(src: str, dst: str) -> None:
            raise OSError("simulated replace failure")

        monkeypatch.setattr(atomic_io.os, "replace", _boom)
        with pytest.raises(OSError):
            atomic_write_text(str(target), "new-content")
        monkeypatch.setattr(atomic_io.os, "replace", real_replace)

        assert target.read_text(encoding="utf-8") == "original"
        after = {p.name for p in tmp_path.iterdir()}
        assert after == before, f"临时文件未清理：{after - before}"

    def test_atomic_write_uses_secure_default_mode(self, tmp_path: Path):
        target = tmp_path / "secure.txt"
        atomic_write_text(str(target), "x")
        mode = target.stat().st_mode & 0o777
        assert mode in (0o600, 0o644), oct(mode)

    def test_no_stale_tmp_files_after_success(self, tmp_path: Path):
        target = tmp_path / "ok.txt"
        atomic_write_text(str(target), "x")
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "ok.txt"]
        assert leftovers == [], leftovers
        assert math.isfinite(target.stat().st_size)
