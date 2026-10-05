"""2026-10-05 复审批次（N 系列）回归测试。

N5：statistical_analysis 批次加载按 mtime 降序——同 task_id 跨批次重复时
最新批次胜出。M13 的 _pair_by_task docstring 一直声称"按文件修改时间排序
后首见即最新"，但实现是 sorted(glob) 路径序（路径序 ≠ 时间序），本批把
口径落实为 _sort_batch_files_by_mtime 实现，本文件锁定"mtime 新者胜出"
且与路径命名顺序无关。

N7：污染检测口径诚实化——无黄金补丁材料返回 "not_applicable"（检测没有
发生），与"检测过且无重叠证据"的 "low" 区分；失败分支（无 patch 材料）
同样 not_applicable。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.run_benchmark import _compute_contamination_risk_level
from experiments.statistical_analysis import _pair_by_task, load_experiment_results_with_sources


def _write_batch_file(root: Path, name: str, *, passed: bool, task_id: str = "t0") -> Path:
    """写 aitester + plain_llm 双臂单任务的 benchmark_*.json，返回文件路径。

    plain_llm 臂恒 passed=False（不参与胜负断言，仅提供配对所需的同 task_id 观测）。
    """
    path = root / name
    payload = {
        "dataset": "synthetic",
        "results": {
            "aitester": {"details": [{"task_id": task_id, "passed": passed}]},
            "plain_llm": {"details": [{"task_id": task_id, "passed": False}]},
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestN5MtimeDedup:
    """N5：mtime 降序加载 → 配对层首见 = 最新批次（与路径命名顺序无关）。

    口径说明：加载层（load_experiment_results_with_sources）不去重——重复行
    全部保留（mtime 降序排列）；去重发生在配对层（_pair_by_task 首见优先）。
    因此胜出者断言必须经 _pair_by_task，included 清单断言锁加载顺序。
    """

    def test_latest_mtime_wins_regardless_of_path_order(self, tmp_path):
        """路径序在前（benchmark_a）的文件 mtime 更旧：配对去重后胜出者必须是
        mtime 更新的 benchmark_b（True），加载清单首位同样是 benchmark_b。"""
        old = _write_batch_file(tmp_path, "benchmark_a_old.json", passed=False)
        new = _write_batch_file(tmp_path, "benchmark_b_new.json", passed=True)
        # 构造"路径序与时间序相反"：a 路径序在前但 mtime 更旧
        t_old, t_new = 1_700_000_000, 1_800_000_000
        os.utime(old, (t_old, t_old))
        os.utime(new, (t_new, t_new))

        results, included = load_experiment_results_with_sources(str(tmp_path))

        # 加载层：mtime 降序（新文件先加载），重复行不去重（去重在配对层）
        assert included[0].endswith("benchmark_b_new.json"), "加载顺序应为 mtime 降序（新文件先加载）"
        assert included[1].endswith("benchmark_a_old.json")
        assert len(results["aitester"]) == 2

        # 配对层：同 task_id 首见 = mtime 最新批次 → 新批次（True）胜出
        pass_a, pass_b, common = _pair_by_task(results["aitester"], results["plain_llm"])
        assert common == ["t0"]
        assert pass_a == [1], "mtime 更新的批次（True）应胜出，而非路径序在前的旧批次"
        assert pass_b == [0]

    def test_explicit_batch_whitelist_also_mtime_ordered(self, tmp_path):
        """--batches 显式白名单同样按 mtime 降序加载（N5 与 glob 模式同口径）。"""
        old = _write_batch_file(tmp_path, "benchmark_x.json", passed=False)
        new = _write_batch_file(tmp_path, "benchmark_y.json", passed=True)
        # 路径序 y > x，但让 x 更新 → 白名单传入顺序故意乱序，胜出者应为 x
        os.utime(new, (1_700_000_000, 1_700_000_000))
        os.utime(old, (1_800_000_000, 1_800_000_000))

        results, included = load_experiment_results_with_sources(
            str(tmp_path), ["benchmark_y.json", "benchmark_x.json"]
        )

        assert included[0].endswith("benchmark_x.json"), "白名单同样 mtime 降序加载"
        pass_a, _, common = _pair_by_task(results["aitester"], results["plain_llm"])
        assert common == ["t0"]
        assert pass_a == [0], "mtime 更新的 benchmark_x（False）应胜出"


class TestN7ContaminationNotApplicable:
    """N7：无黄金补丁材料 → not_applicable（检测不适用，非"低风险"）。"""

    def test_no_golden_patches_dict(self):
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": "p"}, None) == "not_applicable"
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": "p"}, {}) == "not_applicable"

    def test_task_not_in_golden(self):
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": "p"}, {"t2": "g"}) == "not_applicable"

    def test_either_patch_side_empty(self):
        # 生成补丁为空（系统未产出补丁）→ 无可比材料
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": ""}, {"t1": "g"}) == "not_applicable"
        # 黄金补丁为空 → 无可比材料
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": "p"}, {"t1": ""}) == "not_applicable"

    def test_identical_patch_still_high(self):
        """有黄金材料且补丁逐字相同 → 检测发生且全维度重叠 → high（正例护栏：
        not_applicable 不是逃避检测的万能值）。补丁用 diff 文本（与
        test_roadmap_13_22_21_mypy_5 的正例同构，SWE-bench golden 口径）。"""
        g = (
            "diff --git a/f.py b/f.py\n"
            "--- a/f.py\n"
            "+++ b/f.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-def f():\n"
            "-    return 1\n"
            "+def f():\n"
            "+    return 2\n"
        )
        assert _compute_contamination_risk_level({"task_id": "t1", "patch": g}, {"t1": g}) == "high"
