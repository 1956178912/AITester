"""修复引擎批次 II（2026-10-07）：CPR/IDR 离线分析脚本行为锁。

锁定三组行为：
1. IDR 数学（plausible-but-wrong 中负信号命中比例；plausible=0 行不进分母）；
2. CPR 诚实口径（correct=0 → None 未定义；correct>0 → 未误伤比例）；
3. schema 过滤（缺 results.<arm>.details 的批次整批剔除，不进分母）。

运行方式：importlib 直调 main()（Mimosa 对测试内 subprocess 的污点
误报先例——AP 批起测试调脚本一律 importlib 模式，断言强度不损失）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.cpr_idr_report import _analyze, _row_flagged, main


def _row(**overrides):
    """最小结果行夹具（patch_plausible 缺省 1，其余负信号缺省 None）。"""
    row = {"patch_plausible": 1, "patch_correct": 0, "patch_evidence_level": "sbfl"}
    row.update(overrides)
    return row


class TestRowFlagged:
    def test_evidence_none_flags(self) -> None:
        assert _row_flagged(_row(patch_evidence_level="none")) is True

    def test_unverified_flags(self) -> None:
        assert _row_flagged(_row(source_patched_unverified=True)) is True

    def test_rolled_back_flags(self) -> None:
        assert _row_flagged(_row(patch_rolled_back=True)) is True

    def test_over_red_and_regression_stop_flags(self) -> None:
        assert _row_flagged(_row(specificity_gate_verdict="over_red")) is True
        assert _row_flagged(_row(stop_reason="regression_detected")) is True

    def test_missing_fields_do_not_flag(self) -> None:
        """字段缺失（None/缺键）= 无信号，保守不计。"""
        assert _row_flagged(_row()) is False
        assert _row_flagged(_row(source_patched_unverified=None, patch_rolled_back=None)) is False

    def test_false_flags_not_counted(self) -> None:
        assert _row_flagged(_row(source_patched_unverified=False)) is False


class TestAnalyze:
    def test_idr_math(self) -> None:
        rows = [
            ("b1.json", _row(patch_evidence_level="none")),  # 错误补丁，被检测
            ("b1.json", _row()),  # 错误补丁，未检测
            ("b1.json", _row(patch_rolled_back=True)),  # 错误补丁，被检测
            ("b1.json", _row(patch_plausible=0)),  # 非 plausible，不进分母
        ]
        stats = _analyze(rows)
        assert stats["plausible_total"] == 3
        assert stats["incorrect_total"] == 3
        assert stats["incorrect_flagged"] == 2
        assert abs(stats["idr"] - 2 / 3) < 1e-9
        assert stats["correct_total"] == 0
        assert stats["cpr"] is None  # correct=0 → 未定义

    def test_cpr_defined_when_correct_exists(self) -> None:
        rows = [
            ("b1.json", _row(patch_correct=1)),  # 正确补丁，未误伤 → 保留
            ("b1.json", _row(patch_correct=1, patch_rolled_back=True)),  # 正确补丁被误伤
        ]
        stats = _analyze(rows)
        assert stats["correct_total"] == 2
        assert stats["correct_retained"] == 1
        assert stats["cpr"] == 0.5

    def test_signal_distribution(self) -> None:
        rows = [
            ("b1.json", _row(patch_evidence_level="none", patch_rolled_back=True)),  # 双信号行
            ("b1.json", _row(patch_evidence_level="none")),
        ]
        stats = _analyze(rows)
        assert stats["signal_dist"] == {"patch_evidence_level": 2, "patch_rolled_back": 1}


class TestBuildReportAndMain:
    def test_report_contains_numbers_and_honesty(self, tmp_path, capsys) -> None:
        batch = {
            "results": {
                "aitester": {
                    "details": [
                        _row(patch_evidence_level="none"),
                        _row(),
                    ]
                }
            }
        }
        (tmp_path / "benchmark_synthetic_test.json").write_text(json.dumps(batch), encoding="utf-8")
        # 缺 details 的批次（schema 异构）应整批剔除
        (tmp_path / "unrelated.json").write_text(json.dumps({"foo": 1}), encoding="utf-8")
        rc = main(["--results-dir", str(tmp_path), "--arm", "aitester"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "IDR" in out and "0.5000" in out
        assert "CPR" in out and "未定义" in out  # correct=0 诚实披露
        assert "unrelated.json" not in out  # schema 过滤生效
        assert "benchmark_synthetic_test.json" in out

    def test_report_deterministic(self, tmp_path, capsys) -> None:
        batch = {"results": {"aitester": {"details": [_row()]}}}
        (tmp_path / "b.json").write_text(json.dumps(batch), encoding="utf-8")
        main(["--results-dir", str(tmp_path)])
        first = capsys.readouterr().out
        main(["--results-dir", str(tmp_path)])
        second = capsys.readouterr().out
        assert first == second  # 无时间戳/随机成分，逐字节可复现
