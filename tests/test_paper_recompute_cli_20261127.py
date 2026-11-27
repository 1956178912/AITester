"""2026-11-27：论文复算薄 CLI 的契约测试（零模型调用）。"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "tools" / "paper_recompute.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_help_lists_both_entry_points() -> None:
    proc = _run("--help")
    assert proc.returncode == 0, proc.stderr
    assert "aggregate" in proc.stdout
    assert "swebench-filter" in proc.stdout


def test_swebench_filter_evidence_is_consistent() -> None:
    from scripts.tools.paper_recompute import collect_swebench_filter_evidence

    evidence = collect_swebench_filter_evidence()
    assert evidence["pool"] == 225
    assert evidence["after_filter"] == 217
    assert evidence["skipped"] == 8
    assert len(evidence["instance_code_skipped"]) == 2
    assert len(evidence["test_material_skipped"]) == 6
    assert evidence["records"] == 34


def test_swebench_filter_json_output() -> None:
    proc = _run("swebench-filter", "--json")
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["after_filter"] == 217
    assert "sqlfluff__sqlfluff-3330" in payload["instance_code_skipped"]
    assert "pvlib__pvlib-python-1048" in payload["test_material_skipped"]


def test_aggregate_check_restores_published_pack() -> None:
    pack = ROOT / "experiments" / "results" / "RESULTS_DATA_PACK_20261111.json"
    before = pack.read_bytes()
    proc = _run("aggregate", "--check")
    assert proc.returncode == 0, proc.stderr
    assert pack.read_bytes() == before
