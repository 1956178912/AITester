"""R17（2026-10-08 R2）：统计加载数据集白名单泛化单元测试。

背景：
    `statistical_analysis._load_batch_file` 此前硬编码 ``dataset != "synthetic"``
    → QuixBugs（E4 真实基准阶梯）批次被静默剔除，"E4 正式执行时无法产出
    统计报告"成为 P0 阻塞。R17 改为支持集 `_SUPPORTED_DATASETS`
    （synthetic + quixbugs，留扩展点）。

本测试锁定：
    1. dataset=="quixbugs" 且 M1 schema 完备的批次可被加载（R17 修复点）；
    2. dataset 不在支持集（如 "swe_bench"）仍被剔除（防过度放开）；
    3. 支持集为白名单常量（登记扩展点的契约）。
"""

from __future__ import annotations

import json
from pathlib import Path

from experiments.statistical_analysis import (
    _SUPPORTED_DATASETS,
    load_experiment_results,
)


def _write_batch(results_dir: Path, name: str, dataset: str) -> str:
    """写一个 M1 schema 完备的最小批次 JSON，返回其相对 results_dir 的路径。"""
    sub = results_dir / "main_batch"
    sub.mkdir(parents=True, exist_ok=True)
    batch = {
        "dataset": dataset,
        "provenance": {"seed": 42, "git_dirty": False},
        "results": {
            "aitester": {
                "details": [
                    {"task_id": f"{dataset}__task_0001", "detection_rate": 1.0, "repair_rate": 1.0, "passed": True},
                    {"task_id": f"{dataset}__task_0002", "detection_rate": 0.0, "repair_rate": 0.0, "passed": False},
                ]
            }
        },
    }
    (sub / name).write_text(json.dumps(batch), encoding="utf-8")
    return f"main_batch/{name}"


def test_quixbugs_batch_is_loaded(tmp_path) -> None:
    """dataset=='quixbugs' 批次进入统计（R17 核心：此前被剔除）。"""
    rel = _write_batch(tmp_path, "benchmark_quixbugs_test.json", "quixbugs")
    results = load_experiment_results(str(tmp_path), [rel])
    assert "aitester" in results
    assert len(results["aitester"]) == 2


def test_synthetic_batch_still_loaded(tmp_path) -> None:
    """synthetic 批次行为不变（向后兼容）。"""
    rel = _write_batch(tmp_path, "benchmark_synthetic_test.json", "synthetic")
    results = load_experiment_results(str(tmp_path), [rel])
    assert len(results.get("aitester", [])) == 2


def test_unsupported_dataset_still_excluded(tmp_path) -> None:
    """不在支持集的 dataset（swe_bench）仍被剔除（防过度放开）。"""
    rel = _write_batch(tmp_path, "benchmark_swe_bench_test.json", "swe_bench")
    results = load_experiment_results(str(tmp_path), [rel])
    assert results.get("aitester", []) == []


def test_supported_datasets_whitelist() -> None:
    """支持集为白名单常量（扩展点契约）。"""
    assert "synthetic" in _SUPPORTED_DATASETS
    assert "quixbugs" in _SUPPORTED_DATASETS
    assert "swe_bench" not in _SUPPORTED_DATASETS
