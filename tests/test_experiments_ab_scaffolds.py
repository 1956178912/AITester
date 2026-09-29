"""实验脚手架（A/B 对照 + 全链路汇总）单元测试。

覆盖：
- experiments/multi_candidate_ab.py：_success_rate / _bucket_error_counts 聚合
- experiments/position_aware_ab.py：_locate_accuracy 定位正确率 + 缺 state 保守 0.0
- experiments/summarize_full_stack.py：_aggregate_group / _render_on_vs_off
  保守 verdict（ON 组全零 → "无正向信息量"）
- experiments/run_full_stack_swe_bench_pro.py：_apply_full_stack_env 七开关注入
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ─── multi_candidate_ab 聚合 ─────────────────────────────────────────────────


def _make_summary(passed: list[bool], errors: list[str | None] | None = None) -> dict:
    """构造一个最小 aiterster benchmark summary（含 details）。"""
    details = []
    for i, p in enumerate(passed):
        row: dict = {"task_id": f"t{i}", "passed": p}
        if errors and i < len(errors) and errors[i]:
            row["error_category"] = errors[i]
        details.append(row)
    total = len(details)
    passed_count = sum(1 for row in details if row["passed"])
    return {
        "results": {
            "aitester": {
                "total_functions": total,
                "passed_count": passed_count,
                "details": details,
            }
        }
    }


def test_multi_candidate_ab_success_rate() -> None:
    """_success_rate 取 aiterester 基线 passed_count / total_functions。"""
    from experiments.multi_candidate_ab import _success_rate

    summary = _make_summary([True, True, False, False])
    assert _success_rate(summary) == 50.0
    # 无 aiterester 基线时保守 0.0
    assert _success_rate({"results": {}}) == 0.0


def test_multi_candidate_ab_bucket_counts() -> None:
    """_bucket_error_counts 按 aiterester 失败行分桶（已知桶 + other 兜底）。"""
    from experiments.multi_candidate_ab import _bucket_error_counts

    summary = _make_summary(
        [True, False, False, False, False],
        errors=[None, "assertion", "runtime", "something_odd", "unknown"],
    )
    buckets = _bucket_error_counts(summary)
    assert buckets["assertion"] == 1
    assert buckets["runtime"] == 1
    assert buckets["unknown"] == 1
    assert buckets["other"] == 1  # something_odd → other
    assert buckets.get("syntax", 0) == 0


# ─── position_aware_ab 定位正确率 ─────────────────────────────────────────────


def _write_state(raw_dir: str, task_id: str, state: dict) -> None:
    task_dir = os.path.join(raw_dir, task_id)
    os.makedirs(task_dir, exist_ok=True)
    with open(os.path.join(task_dir, "aitester.json"), "w", encoding="utf-8") as f:
        json.dump(state, f)


def test_position_aware_ab_locate_accuracy_hit() -> None:
    """ON 组 focused=True + function_name 命中 gold → 定位正确率 100%。"""
    from experiments.position_aware_ab import _locate_accuracy

    with tempfile.TemporaryDirectory() as d:
        raw_dir = os.path.join(d, "raw")
        _write_state(
            raw_dir,
            "task_1",
            {
                "position_aware_focus": {"focused": True, "function_name": "divide"},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        # iterations>0（有修复轮次）→ 定位激活 + 命中 gold → 100%
        summary = {"results": {"aitester": {"details": [{"task_id": "task_1", "iterations": 1}]}}}
        assert _locate_accuracy(d, summary) == 100.0


def test_position_aware_ab_locate_accuracy_miss() -> None:
    """function_name 不命中 gold → 定位正确率 0%。"""
    from experiments.position_aware_ab import _locate_accuracy

    with tempfile.TemporaryDirectory() as d:
        raw_dir = os.path.join(d, "raw")
        _write_state(
            raw_dir,
            "task_1",
            {
                "position_aware_focus": {"focused": True, "function_name": "subtract"},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        # iterations>0（有修复轮次）→ 定位激活但未命中 gold → 0.0
        summary = {"results": {"aitester": {"details": [{"task_id": "task_1", "iterations": 1}]}}}
        assert _locate_accuracy(d, summary) == 0.0


def test_position_aware_ab_locate_accuracy_unfocused_skipped() -> None:
    """focused=False 且无修复（iterations=0）→ 定位未激活，返回 -1.0（渲染层
    显示"未激活"而非误导性 0%）。2026-10 改进：区分"定位未执行"（无修复轮次）
    与"定位未命中"（有修复但 function_name 不命中 gold）。"""
    from experiments.position_aware_ab import _locate_accuracy

    with tempfile.TemporaryDirectory() as d:
        raw_dir = os.path.join(d, "raw")
        _write_state(
            raw_dir,
            "task_1",
            {
                "position_aware_focus": {"focused": False},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        # iterations=0 → 无修复轮次 → 定位未激活
        summary = {"results": {"aitester": {"details": [{"task_id": "task_1", "iterations": 0}]}}}
        assert _locate_accuracy(d, summary) == -1.0


def test_position_aware_ab_locate_accuracy_repaired_but_unfocused() -> None:
    """有修复（iterations>0）但 focused=False → 定位激活但未命中，计入 total
    （正确率 0.0，非 -1.0 的"未激活"口径）。"""
    from experiments.position_aware_ab import _locate_accuracy

    with tempfile.TemporaryDirectory() as d:
        raw_dir = os.path.join(d, "raw")
        _write_state(
            raw_dir,
            "task_1",
            {
                "position_aware_focus": {"focused": False},
                "task_metadata": {"suggested_function": "divide"},
            },
        )
        summary = {"results": {"aitester": {"details": [{"task_id": "task_1", "iterations": 2}]}}}
        assert _locate_accuracy(d, summary) == 0.0


def test_position_aware_ab_locate_accuracy_no_raw_dir() -> None:
    """raw/ 目录缺失 → 保守 0.0。"""
    from experiments.position_aware_ab import _locate_accuracy

    with tempfile.TemporaryDirectory() as d:
        summary = {"results": {"aitester": {"details": [{"task_id": "task_1"}]}}}
        assert _locate_accuracy(d, summary) == 0.0


def test_position_aware_ab_locate_accuracy_details_not_list() -> None:
    """details 缺失 / 非 list（旧 JSON 形态）→ 保守 0.0，不崩溃。"""
    from experiments.position_aware_ab import _locate_accuracy

    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "raw"))
        assert _locate_accuracy(d, {"results": {}}) == 0.0
        assert _locate_accuracy(d, {"results": {"aitester": {}}}) == 0.0


# ─── summarize_full_stack 聚合与 verdict ──────────────────────────────────────


def _make_summary_with_results(baseline_results: dict) -> dict:
    """构造一个含指定 baseline 的 benchmark summary。"""
    return {"results": baseline_results}


def _baseline_block(total: int, passed: int, details: list[dict] | None = None) -> dict:
    return {
        "total_functions": total,
        "passed_count": passed,
        "details": details or [],
    }


def test_summarize_full_stack_aggregate_group() -> None:
    """_aggregate_group 聚合多基线 summary（成功率 + 错误分桶）。"""
    from experiments.summarize_full_stack import _aggregate_group

    summary = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                4,
                1,
                details=[
                    {"task_id": "t0", "passed": True},
                    {"task_id": "t1", "passed": False, "error_category": "assertion"},
                    {"task_id": "t2", "passed": False, "error_category": "runtime"},
                    {"task_id": "t3", "passed": False, "error_category": "unknown"},
                ],
            )
        }
    )
    agg = _aggregate_group([summary])
    bl = agg["baselines"]["aitester"]
    assert bl["success_rate"] == 25.0
    assert bl["error_buckets"]["assertion"] == 1
    assert bl["error_buckets"]["runtime"] == 1
    assert bl["error_buckets"]["unknown"] == 1
    assert agg["total_benchmark_files"] == 1


def test_summarize_full_stack_aggregate_group_multiple_files() -> None:
    """聚合多份同组 benchmark JSON（跨文件合并）。"""
    from experiments.summarize_full_stack import _aggregate_group

    s1 = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                2, 1, [{"task_id": "a", "passed": True}, {"task_id": "b", "passed": False, "error_category": "syntax"}]
            )
        }
    )
    s2 = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                2,
                0,
                [
                    {"task_id": "c", "passed": False, "error_category": "import_error"},
                    {"task_id": "d", "passed": False, "error_category": "import_error"},
                ],
            )
        }
    )
    agg = _aggregate_group([s1, s2])
    bl = agg["baselines"]["aitester"]
    assert bl["total_tasks"] == 4
    assert bl["passed_count"] == 1
    assert bl["success_rate"] == 25.0
    assert bl["error_buckets"]["syntax"] == 1
    assert bl["error_buckets"]["import_error"] == 2
    assert agg["total_benchmark_files"] == 2


def test_summarize_full_stack_render_no_positive_information() -> None:
    """ON 组全基线 success_rate=0 → '无正向信息量'（保守 verdict）。"""
    from experiments.summarize_full_stack import _aggregate_group, _render_on_vs_off

    off_summary = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                2,
                1,
                [{"task_id": "a", "passed": True}, {"task_id": "b", "passed": False, "error_category": "assertion"}],
            )
        }
    )
    on_summary = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                2,
                0,
                [
                    {"task_id": "a", "passed": False, "error_category": "assertion"},
                    {"task_id": "b", "passed": False, "error_category": "runtime"},
                ],
            )
        }
    )
    off_agg = _aggregate_group([off_summary])
    on_agg = _aggregate_group([on_summary])
    md = _render_on_vs_off(on_agg, off_agg)
    assert "无正向信息量" in md


def test_summarize_full_stack_render_positive() -> None:
    """ON 组高于 OFF 组 → '正向信号'。"""
    from experiments.summarize_full_stack import _aggregate_group, _render_on_vs_off

    off_summary = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                4,
                1,
                [
                    {"task_id": "a", "passed": True},
                    {"task_id": "b", "passed": False},
                    {"task_id": "c", "passed": False},
                    {"task_id": "d", "passed": False},
                ],
            )
        }
    )
    on_summary = _make_summary_with_results(
        {
            "aitester": _baseline_block(
                4,
                2,
                [
                    {"task_id": "a", "passed": True},
                    {"task_id": "b", "passed": True},
                    {"task_id": "c", "passed": False},
                    {"task_id": "d", "passed": False},
                ],
            )
        }
    )
    off_agg = _aggregate_group([off_summary])
    on_agg = _aggregate_group([on_summary])
    md = _render_on_vs_off(on_agg, off_agg)
    assert "正向信号" in md


# ─── run_full_stack_swe_bench_pro 七开关注入 ─────────────────────────────────


def test_run_full_stack_applies_seven_switches() -> None:
    """_apply_full_stack_env 注入七开关 + trace 目录（默认全开）。"""
    from unittest.mock import patch

    from experiments.run_full_stack_swe_bench_pro import _apply_full_stack_env

    expected = {
        "RUNTIME_PROBE_ENABLE": "true",
        "STRATEGY_BANK_ENABLE": "true",
        "EXPERT_POOL_ENABLE": "true",
        "CROSS_FILE_ENABLE": "true",
        "CROSS_FILE_BIDIRECTIONAL": "true",
        "REPO_LEVEL_EXECUTION": "true",
        "SWE_REPO_VENV_ISOLATION": "true",
    }
    with patch.dict(os.environ, {k: "false" for k in expected}, clear=False), tempfile.TemporaryDirectory() as out_dir:
        _apply_full_stack_env(out_dir)
        for key, val in expected.items():
            assert os.environ.get(key) == val, f"{key} 未正确注入"
        # trace 目录指向 output_dir 子目录
        trace_dir = os.environ.get("AITESTER_TRACE_DIR")
        assert trace_dir is not None
        assert out_dir in trace_dir


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
