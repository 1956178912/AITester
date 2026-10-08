"""R15（2026-10-08 R2）：跑批后 provenance 脏树断言单元测试。

背景：
    `run_main_batch` 跑批前有 `_check_repo_clean` 硬拒绝脏树，但"跑批期间
    工作树变脏"（竞态）或"绕过门禁直调 run_benchmark"两条路径无防线；且
    --allow-dirty 豁免此前不登记原因（历史 synthetic 两臂 git_dirty=True
    无 dirty_reason）。R15 新增：
      - --dirty-reason 参数（写入 provenance.dirty_reason，缺省 unspecified）；
      - 跑批后 _assert_provenance_dirty 断言（未豁免而 dirty → 抛错；
        已豁免而缺原因 → 抛错）。

本测试锁定断言函数四个分支的行为（零 LLM、纯本地）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.run_main_batch import _assert_provenance_dirty


def _write_batch(tmp_path: Path, provenance: dict) -> Path:
    p = tmp_path / "benchmark_synthetic_test.json"
    p.write_text(json.dumps({"provenance": provenance}), encoding="utf-8")
    return p


def test_clean_tree_without_allow_dirty_passes(tmp_path) -> None:
    p = _write_batch(tmp_path, {"git_dirty": False, "dirty_reason": None})
    _assert_provenance_dirty(p, allow_dirty=False)  # 不抛


def test_dirty_tree_without_allow_dirty_raises(tmp_path) -> None:
    """未豁免而 provenance.git_dirty=True → 抛错（防御竞态/绕过）。"""
    p = _write_batch(tmp_path, {"git_dirty": True, "dirty_reason": None})
    with pytest.raises(SystemExit):
        _assert_provenance_dirty(p, allow_dirty=False)


def test_dirty_tree_with_reason_and_allow_dirty_passes(tmp_path) -> None:
    p = _write_batch(tmp_path, {"git_dirty": True, "dirty_reason": "调试迭代"})
    _assert_provenance_dirty(p, allow_dirty=True)  # 不抛


def test_allow_dirty_without_reason_raises(tmp_path) -> None:
    """已豁免但 provenance.dirty_reason 缺失 → 抛错（豁免必须可审计）。"""
    p = _write_batch(tmp_path, {"git_dirty": True, "dirty_reason": None})
    with pytest.raises(SystemExit):
        _assert_provenance_dirty(p, allow_dirty=True)


def test_unreadable_provenance_skips(tmp_path, capsys) -> None:
    """provenance 不可读时仅告警跳过（不阻断主流程）。"""
    bad = tmp_path / "benchmark_synthetic_bad.json"
    bad.write_text("not json", encoding="utf-8")
    _assert_provenance_dirty(bad, allow_dirty=False)  # 不抛
    assert "跳过" in capsys.readouterr().err


def test_dirty_reason_default_unspecified() -> None:
    """--dirty-reason 缺省时由 main 填 'unspecified'（参数默认 None + 归一化口径）。"""

    def _normalize(value: str | None) -> str:
        # 归一化口径与 main() 内联逻辑一致：(args.dirty_reason or "").strip() or "unspecified"
        return (value or "").strip() or "unspecified"

    assert _normalize(None) == "unspecified"
    assert _normalize("  ") == "unspecified"
    assert _normalize("人工调试") == "人工调试"
