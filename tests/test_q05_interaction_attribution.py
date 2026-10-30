"""Q05 交互中心归因聚合器的契约锁（分层正确性 + 只读工件口径）。

锁定三个反模式：
1. 跨臂合并把「维度没被触发」读成「维度测过且为 0」——分层必须把
   aitester（编排）与其他臂分开；
2. 聚合数字不得来自工件字面量之外（edge_counts 缺键按 0 计、非整数字段
   不得让聚合崩溃）；
3. 输出工件必须严格 JSON（allow_nan=False），schema/口径字段在场。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
_SPEC = importlib.util.spec_from_file_location(
    "q05_interaction_attribution_report", _TOOLS / "q05_interaction_attribution_report.py"
)
q05 = importlib.util.module_from_spec(_SPEC)
sys.modules.setdefault("q05_interaction_attribution_report", q05)
_SPEC.loader.exec_module(q05)


def _write_batch(root: Path, rel: str, arm: str, total: int, edge: dict, side: dict) -> None:
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "dataset": "quixbugs",
        "results": {
            arm: {
                "total_functions": total,
                "passed_count": 0,
                "failure_bucket_distribution": {
                    "total": total,
                    "unclassified_rows": 0,
                    "harness_invalid_rows": 0,
                    "counts": {"uncategorized": total},
                    "edge_counts": edge,
                    "fault_side_counts": side,
                },
            }
        },
    }
    (d / "benchmark_demo_20261030_000000.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_tier_splits_orchestration_from_baselines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """编排臂与对照臂必须分层；aitester 大小写不敏感、其余臂一律 baseline。

    真实批次形态：一次 run_benchmark 把多臂写进**同一个** benchmark json 的
    results（每臂一个聚合单元）。
    """
    d = tmp_path / "batch_a"
    d.mkdir(parents=True)
    fbd = {
        "total": 10,
        "unclassified_rows": 0,
        "harness_invalid_rows": 0,
        "counts": {},
        "edge_counts": {},
        "fault_side_counts": {},
    }
    orch = dict(
        fbd,
        edge_counts={"planner_to_generator": 3, "harness": 7},
        fault_side_counts={"model_side": 2, "uncategorized": 8},
    )
    base = dict(fbd, total=5, edge_counts={"harness": 5}, fault_side_counts={"uncategorized": 5})
    payload = {
        "dataset": "quixbugs",
        "results": {
            "aitester": {"failure_bucket_distribution": orch},
            "plain_llm_df": {"failure_bucket_distribution": base},
        },
    }
    (d / "benchmark_demo_20261030_000000.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(q05, "RESULTS", tmp_path)
    units, n_files, n_have = q05.collect()
    assert (n_files, n_have) == (1, 1)
    assert len(units) == 2
    tiers = {u["arm"]: u["tier"] for u in units}
    assert tiers["aitester"] == "orchestration"
    assert tiers["plain_llm_df"] == "baseline"
    s = q05.summarize(units)
    # 编排臂只聚合自己的行；对照臂不得混入 planner 边
    assert s["orchestration"]["edge_counts"]["planner_to_generator"] == 3
    assert s["baseline"]["edge_counts"]["planner_to_generator"] == 0
    assert s["orchestration"]["total_rows"] == 10
    assert s["baseline"]["total_rows"] == 5
    assert s["all"]["total_rows"] == 15


def test_missing_edge_key_counts_as_zero_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """工件缺键按 0 计（旧 schema 批次仍可聚合），不得抛异常。"""
    d = tmp_path / "legacy"
    d.mkdir()
    payload = {
        "results": {
            "aitester": {
                "failure_bucket_distribution": {
                    "total": 4,
                    "edge_counts": {"harness": 4},
                    "fault_side_counts": {"harness_side": 1, "uncategorized": 3},
                }
            }
        }
    }
    (d / "benchmark_old.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(q05, "RESULTS", tmp_path)
    units, _n_files, n_have = q05.collect()
    assert n_have == 1
    u = units[0]
    assert u["edge_counts"]["planner_to_generator"] == 0
    assert u["fault_side_counts"]["grader"] == 0
    assert u["edge_counts"]["harness"] == 4


def test_render_contains_tiered_tables_and_caveat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Markdown 必须含分层表与「恒为 0 是标注器上限」告警，防报告层丢口径。"""
    _write_batch(
        tmp_path,
        "batch_b",
        "aitester",
        8,
        {"debugger_to_executor": 8},
        {"model_side": 8},
    )
    monkeypatch.setattr(q05, "RESULTS", tmp_path)
    units, n_files, n_have = q05.collect()
    payload = {
        "n_files": n_files,
        "n_have": n_have,
        "units": units,
        "summary": q05.summarize(units),
    }
    md = q05.render_markdown(payload)
    assert "编排臂 (aitester)" in md
    assert "对照臂" in md
    assert "全量(仅对账)" in md
    assert "标注器覆盖上限" in md
    assert "debugger_to_executor" in md


def test_main_writes_strict_json_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """端到端：main() 落盘 JSON 严格可解析、schema 在场、Markdown 在场。"""
    _write_batch(
        tmp_path,
        "batch_c",
        "aitester",
        6,
        {"harness": 6},
        {"uncategorized": 6},
    )
    monkeypatch.setattr(q05, "RESULTS", tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setattr(sys, "argv", ["q05", "--out-dir", str(out_dir)])
    rc = q05.main()
    assert rc == 0
    agg = json.loads((out_dir / "Q05_AGGREGATE.json").read_text(encoding="utf-8"))
    assert agg["schema"] == "aitester_q05_interaction_attribution/1"
    assert agg["summary"]["orchestration"]["total_rows"] == 6
    assert (out_dir / "Q05_SUMMARY.md").is_file()
