"""修复引擎批次 VI（2026-10-07）：跑批运营收口——--staging-dir + CPR/IDR 报告入口。

锁定三组行为：
1. _validated_staging_dir 路径穿越防御（拒绝 .. 分量；拒绝位于输出目录内）；
2. _snapshot_files/_stage_out_new_artifacts（新工件外移、既有工件不动、
   相对路径结构保留）；
3. run_main_batch 双出口接线（--skip-stats 早退同样外移）+ Makefile cpr-idr 目标。

背景：R16-8（变异反馈入 prompt）经核实已由 M7 批（2026-09-29，
mutation_advisor 图内节点 + build_mutation_prompt_section）完整落地——
本批回收该陈旧建议（AF 批"落地后须回收"纪律第二次生效）。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.run_main_batch import (
    _snapshot_files,
    _stage_out_new_artifacts,
    _validated_staging_dir,
)


class TestValidatedStagingDir:
    def test_rejects_dotdot_components(self, tmp_path) -> None:
        with pytest.raises(SystemExit):
            _validated_staging_dir(str(tmp_path / ".." / "elsewhere"), tmp_path / "out")

    def test_rejects_inside_output_dir(self, tmp_path) -> None:
        with pytest.raises(SystemExit):
            _validated_staging_dir(str(tmp_path / "out" / "staging"), tmp_path / "out")

    def test_accepts_external_dir(self, tmp_path) -> None:
        staging = _validated_staging_dir(str(tmp_path / "staging"), tmp_path / "out")
        assert staging == (tmp_path / "staging").resolve()


class TestStageOutNewArtifacts:
    def test_moves_only_new_files_preserving_structure(self, tmp_path) -> None:
        out_dir = tmp_path / "out"
        (out_dir / "sub").mkdir(parents=True)
        existing = out_dir / "SHA256SUMS"
        existing.write_text("old", encoding="utf-8")
        before = _snapshot_files(out_dir)
        # 跑批"新增"：根级批次 JSON + 子目录报告
        (out_dir / "benchmark_x.json").write_text("{}", encoding="utf-8")
        (out_dir / "sub" / "statistical_report.md").write_text("# r", encoding="utf-8")

        staging = tmp_path / "staging"
        moved = _stage_out_new_artifacts(out_dir, staging, before)

        assert len(moved) == 2
        assert (staging / "benchmark_x.json").is_file()
        assert (staging / "sub" / "statistical_report.md").is_file()
        assert not (out_dir / "benchmark_x.json").exists()  # 已移出
        assert existing.is_file() and existing.read_text(encoding="utf-8") == "old"  # 既有不动

    def test_no_new_files_no_moves(self, tmp_path) -> None:
        out_dir = tmp_path / "out"
        out_dir.mkdir()
        before = _snapshot_files(out_dir)
        assert _stage_out_new_artifacts(out_dir, tmp_path / "staging", before) == []


class TestWiringLocks:
    def test_main_wires_staging_at_both_exits(self) -> None:
        """接线存在性锁：main() 跑前快照 + 双出口（skip-stats 早退/正常收尾）外移。"""
        import inspect

        from experiments import run_main_batch

        src_text = inspect.getsource(run_main_batch.main)
        assert "_validated_staging_dir(args.staging_dir, out_dir)" in src_text
        assert "_snapshot_files(out_dir)" in src_text
        # --skip-stats 早退与正常收尾各调一次 _stage_and_report
        # （计数 3 = def 定义行 1 + 两处调用）
        assert src_text.count("_stage_and_report()") == 3

    def test_makefile_has_cpr_idr_target(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        makefile = (project_root / "Makefile").read_text(encoding="utf-8")
        assert "cpr-idr:" in makefile
        assert "experiments/cpr_idr_report.py" in makefile
        assert "cpr-idr" in makefile.split(".PHONY:", 1)[1].split("\n", 1)[0]
