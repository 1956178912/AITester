"""P3 评测诚信校验器回归锁（2026-10-18；零 LLM / 零网络，纯合成工件）。

锁五类行为：
1. IC-1 provenance 缺失 → FAIL；
2. IC-4 补丁存在但未验证 → FAIL；弃权门（patch_abstained）例外不 FAIL；
3. IC-3/IC-8 None 行独立重算且显式披露（禁以 0 计）；
4. IC-7 变异占位值（mutants_total=0）→ WARN、计数矛盾 → FAIL；
5. IC-5 namespace 重复 → FAIL；CLI 退出码口径。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from experiments.eval_integrity_check import check_artifact_dir

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _batch(provenance: dict | None = None, rows: list[dict] | None = None, arm: str = "plain_llm_df") -> dict:
    return {
        "provenance": provenance
        if provenance is not None
        else {
            "git_sha": "a93c1f6",
            "git_dirty": False,
            "model_name": "deepseek-flash",
            "temperature": 0.0,
            "model_fingerprint": {"pinned": True},
            "cache_namespace": "ns_a",
            "env_snapshot": {"AITESTER_CACHE_NAMESPACE": "ns_a"},
        },
        "results": {arm: {"details": rows if rows is not None else []}},
    }


def _row(**kw) -> dict:
    base = {"task_id": "t0", "detection_rate": 1.0, "repair_rate": 0.0, "false_fix_rate": 0.0}
    base.update(kw)
    return base


def _write_batch(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestProvenanceChecks:
    def test_missing_provenance_field_fails_ic1(self, tmp_path: Path) -> None:
        prov = {"git_sha": "x", "git_dirty": False}  # 缺 model_name/temperature
        _write_batch(tmp_path, "benchmark_a.json", _batch(provenance=prov))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-1"]["status"] == "FAIL"

    def test_fingerprint_not_pinned_warns_ic2(self, tmp_path: Path) -> None:
        prov = _batch()["provenance"] | {"model_fingerprint": {"pinned": False}}
        _write_batch(tmp_path, "benchmark_a.json", _batch(provenance=prov))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-2"]["status"] == "WARN"


class TestPatchValidation:
    def test_unvalidated_patch_fails_ic4(self, tmp_path: Path) -> None:
        row = _row(patch="def f():\n    return 1\n", patch_validate_verdict="unvalidated")
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[row]))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-4"]["status"] == "FAIL"

    def test_abstained_patch_not_a_failure(self, tmp_path: Path) -> None:
        row = _row(patch="def f():\n    return 1\n", patch_validate_verdict="unvalidated", patch_abstained=True)
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[row]))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-4"]["status"] == "PASS"
        assert "弃权门" in rep["checks"]["IC-4"]["detail"]

    def test_raw_response_fence_is_not_artifact(self, tmp_path: Path) -> None:
        row = _row(patch="```python\ndef f():\n    return 1\n```", patch_validate_verdict="evidence")
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[row]))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-4"]["status"] == "PASS"
        assert "fence" in rep["checks"]["IC-4"]["detail"]


class TestFailClosedNone:
    def test_none_rows_counted_not_zeroed(self, tmp_path: Path) -> None:
        rows = [
            _row(task_id="a", detection_rate=1.0),
            _row(task_id="b", detection_rate=None),
            _row(task_id="c", detection_rate=0.0),
        ]
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=rows))
        rep = check_artifact_dir(tmp_path)
        agg = rep["recomputed"]["plain_llm_df"]["det"]
        assert agg == {"hit": 1, "measurable": 2}  # None 行不进分母
        assert rep["checks"]["IC-8"]["status"] == "PASS"
        assert "detection None = 1" in rep["checks"]["IC-8"]["detail"]


class TestMutationReporting:
    def test_placeholder_score_warns(self, tmp_path: Path) -> None:
        row = _row(mutation_score=1.0, mutants_total=0, mutants_killed=0)
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[row]))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-7"]["status"] == "WARN"

    def test_inconsistent_counts_fail(self, tmp_path: Path) -> None:
        row = _row(mutation_score=0.5, mutants_total=10, mutants_killed=12)
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[row]))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-7"]["status"] == "FAIL"

    def test_consistent_counts_pass(self, tmp_path: Path) -> None:
        row = _row(mutation_score=0.5, mutants_total=10, mutants_killed=5)
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[row]))
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-7"]["status"] == "PASS"


class TestCacheNamespace:
    def test_duplicate_namespace_fails_ic5(self, tmp_path: Path) -> None:
        for name in ("benchmark_a.json", "benchmark_b.json"):
            _write_batch(tmp_path, name, _batch())
        rep = check_artifact_dir(tmp_path)
        assert rep["checks"]["IC-5"]["status"] == "FAIL"


class TestCliContract:
    def test_clean_fixture_exit_zero_and_real_artifact_passes(self, tmp_path: Path) -> None:
        _write_batch(tmp_path, "benchmark_a.json", _batch(rows=[_row()]))
        out = tmp_path / "report.md"
        proc = subprocess.run(
            [sys.executable, "experiments/eval_integrity_check.py", "--artifact-dir", str(tmp_path), "--md", str(out)],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
            timeout=120,
        )
        assert proc.returncode == 0, proc.stdout + proc.stderr
        assert "总体：PASS" in out.read_text(encoding="utf-8")

    def test_real_decision_grade_artifact_passes(self) -> None:
        """真实工件（T 轮 B2 锁指纹批）必须 PASS——防校验规则过严误杀在场工件。"""
        target = _REPO_ROOT / "experiments/results/t_round_b2_main_batch_20261018"
        if not target.exists():
            pytest.skip("B2 工件不在场（fresh clone 精简场景）")
        rep = check_artifact_dir(target)
        for cid in ("IC-1", "IC-3", "IC-4", "IC-5", "IC-8"):
            assert rep["checks"][cid]["status"] == "PASS", rep["checks"][cid]
        assert rep["checks"]["IC-2"]["status"] == "PASS"
        assert rep["checks"]["IC-6"]["status"] == "PASS"
