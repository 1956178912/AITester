"""2026-10-05 独立审查优化批次（V 系列）回归测试。

本文件锁定统计管线可复算化与诚实指标检验口径：

- V1 批次排序确定性：去重"最新批次优先"的主键从 mtime（文件系统属性，
  clone/拷贝即漂移——χ²=12.96 vs 15.04 的报告不可复算即源于此）改为
  批次文件名内嵌时间戳降序（实验属性，run_benchmark 写盘时固化）；
  无内嵌时间戳的批次 mtime 降序兜底（N5 语义保留）。
- V2 诚实指标 McNemar：detection_rate / repair_rate（M1 三指标，gold
  独立裁决）的配对检验——历史口径只对 passed（自指指标）做推断统计，
  honest 指标下 aitester 与 plain_llm 的平手事实从未被检验。
- V3 配对分母口径：M1 字段值 None（无 gold 材料，分母外）跳过不并入
  分母，与"测量为失败"（0）区分。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiments.statistical_analysis import (
    _pair_by_task,
    _sort_batch_files_deterministic,
    mcnemar_test,
)


def _write_batch(root: Path, name: str, rows: dict[str, list[dict]]) -> Path:
    """写多臂多任务 benchmark 批次文件（dataset=synthetic，纳入统计口径）。"""
    path = root / name
    payload = {"dataset": "synthetic", "results": {b: {"details": rs} for b, rs in rows.items()}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestV1DeterministicBatchOrder:
    """V1：规范命名批次按文件名内嵌时间戳降序，与文件系统 mtime 无关。"""

    def test_embedded_timestamp_order_ignores_mtime(self, tmp_path):
        # 老批次（ts=..._20260901_000000）的 mtime 更新：顺序仍由内嵌 ts 决定
        old = _write_batch(tmp_path, "benchmark_synthetic_20260901_000000.json", {"aitester": {"details": []}})
        new = _write_batch(tmp_path, "benchmark_synthetic_20261001_121523.json", {"aitester": {"details": []}})
        # 故意让"老批次"的 mtime 更新（clone/拷贝后的典型情形）
        import os

        os.utime(old, (1_900_000_000, 1_900_000_000))
        os.utime(new, (1_000_000_000, 1_000_000_000))

        ordered = _sort_batch_files_deterministic([old, new])
        assert ordered[0].name == "benchmark_synthetic_20261001_121523.json", (
            "内嵌时间戳新的批次先加载，mtime 漂移不影响顺序"
        )
        assert ordered[1].name == "benchmark_synthetic_20260901_000000.json"

    def test_no_timestamp_files_fall_back_to_mtime(self, tmp_path):
        # 无内嵌时间戳（N5 构造的历史命名）：mtime 降序兜底，且排在规范批次之后
        import os

        a = _write_batch(tmp_path, "benchmark_a.json", {"aitester": {"details": []}})
        b = _write_batch(tmp_path, "benchmark_b.json", {"aitester": {"details": []}})
        std = _write_batch(tmp_path, "benchmark_synthetic_20260101_000000.json", {"aitester": {"details": []}})
        os.utime(a, (1_800_000_000, 1_800_000_000))
        os.utime(b, (1_700_000_000, 1_700_000_000))

        ordered = _sort_batch_files_deterministic([a, b, std])
        assert ordered[0].name.startswith("benchmark_synthetic_"), "规范批次排最前"
        assert ordered[1].name == "benchmark_a.json", "无 ts 组内 mtime 降序（N5 兜底）"
        assert ordered[2].name == "benchmark_b.json"

    def test_same_timestamp_path_tiebreak(self, tmp_path):
        # 同内嵌时间戳（同分钟两批，分置不同子目录）：路径名升序稳定打破
        # 平局（跨机一致）；正则要求 ts 紧邻 .json，同 ts 异名须借助目录分层
        import os

        (tmp_path / "d_x").mkdir()
        (tmp_path / "d_y").mkdir()
        x = _write_batch(tmp_path / "d_x", "benchmark_synthetic_20261001_121523.json", {"aitester": {"details": []}})
        y = _write_batch(tmp_path / "d_y", "benchmark_synthetic_20261001_121523.json", {"aitester": {"details": []}})
        # 干扰项：让 y 的 mtime 更新——平局打破只看路径名，不看 mtime
        os.utime(y, (1_900_000_000, 1_900_000_000))
        ordered = _sort_batch_files_deterministic([y, x])
        assert [p.as_posix() for p in ordered] == [x.as_posix(), y.as_posix()]


class TestV2HonestMetricMcNemar:
    """V2：detection_rate / repair_rate 字段的 McNemar 配对检验。"""

    def test_detection_rate_field_pairing(self):
        # aitester detection 2/5，baseline detection 0/5，共同不一致对 2
        aitester = [{"task_id": f"t{i}", "detection_rate": v} for i, v in enumerate([1, 1, 0, 0, 0])]
        baseline = [{"task_id": f"t{i}", "detection_rate": 0} for i in range(5)]
        chi2, p, n_diff, n_common = mcnemar_test(aitester, baseline, field="detection_rate")
        assert n_common == 5
        assert n_diff == 2
        # n01=2, n10=0 → chi2 = (2-1)^2/2 = 0.5
        assert abs(chi2 - 0.5) < 1e-9
        assert 0 < p < 0.5

    def test_identical_detection_rates_p_one(self):
        rows = [{"task_id": f"t{i}", "detection_rate": 0} for i in range(5)]
        chi2, p, n_diff, _ = mcnemar_test(rows, [dict(r) for r in rows], field="detection_rate")
        assert n_diff == 0
        assert chi2 == 0.0
        assert p == 1.0

    def test_none_detection_excluded_from_denominator(self):
        # aitester 在 t4 上 detection=None（无 gold 材料）→ 该任务退出分母
        aitester = [
            {"task_id": "t0", "detection_rate": 1},
            {"task_id": "t1", "detection_rate": 0},
            {"task_id": "t2", "detection_rate": None},
        ]
        baseline = [
            {"task_id": "t0", "detection_rate": 0},
            {"task_id": "t1", "detection_rate": 0},
            {"task_id": "t2", "detection_rate": 1},
        ]
        paired_a, paired_b, common = _pair_by_task(aitester, baseline, field="detection_rate")
        assert common == ["t0", "t1"], "None（分母外）任务不参与配对"
        assert paired_a == [1, 0]
        assert paired_b == [0, 0]


class TestV3PairDenominatorSemantics:
    """V3：M1 诚实指标的 None ≠ 0——"无法测量"不混入"测量为失败"。"""

    def test_none_passed_field_still_excluded(self):
        # passed 字段历史行为：值恒为 bool（None 行为历史未定义），新口径下
        # None 同样跳过——若未来结果行出现 passed=None 不会被误记 0
        rows_a = [{"task_id": "t0", "passed": True}, {"task_id": "t1", "passed": None}]
        rows_b = [{"task_id": "t0", "passed": False}, {"task_id": "t1", "passed": False}]
        paired_a, _paired_b, common = _pair_by_task(rows_a, rows_b)
        assert common == ["t0"]
        assert paired_a == [1]


class TestV4EvidenceGateBlocking:
    """V4：源码补丁证据门真阻断（2026-10-05 独立审查 P0）。

    锁定语义：PATCH_EVIDENCE_GATE_ENABLE 默认 true 且证据等级不足
    （keyword/none）→ 补丁不落盘（磁盘恢复原文、patch_applied=False、
    target_code 保持原文、source_patched_unverified=True）——文档契约
    （patch_evidence.py / state.py "拒绝写盘，源码保持原样"）兑现，
    防回归到"写盘后仅标记"的 fail-open 旧行为。
    """

    def _state(self, tmp_path, original: str, patch: str) -> dict:
        target = tmp_path / "mod.py"
        target.write_text(original)
        return {
            "target_code": original,
            "patch": patch,
            "target_file": str(target),
            "module_name": "mod",
            "error_category": "logic_error",
            "iteration": 0,
        }

    def test_no_evidence_patch_rejected_and_disk_restored(self, tmp_path, monkeypatch):
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        monkeypatch.delenv("PATCH_EVIDENCE_GATE_ENABLE", raising=False)  # 默认 true
        original = "def f():\n    return 1\n"
        state = self._state(tmp_path, original, "def f():\n    return 2\n")

        update = _patch_applier_node(state)  # type: ignore[arg-type]

        assert update["repair_history"][-1]["patch_applied"] is False, "无证据补丁必须被拒绝写盘"
        assert update["target_code"] == original, "state 保持原文"
        assert update["source_patched_unverified"] is True
        assert update["patch_evidence_level"] in ("keyword", "none")
        assert (tmp_path / "mod.py").read_text() == original, "磁盘必须恢复原文（fail-closed 契约）"
        assert update["last_applied_repair"] is None, "被拒补丁不得进入待验证暂存"

    def test_sbfl_evidence_patch_allowed(self, tmp_path, monkeypatch):
        # 谱系定位证据（改动行 ∩ Top-k 可疑行）→ 放行写盘
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        monkeypatch.delenv("PATCH_EVIDENCE_GATE_ENABLE", raising=False)
        original = "def f(x):\n    if x > 0:\n        return 1\n    return -1\n"
        state = self._state(tmp_path, original, "def f(x):\n    if x > 0:\n        return 2\n    return -1\n")
        # 补丁改动行（_patch_changed_lines 的 diff 计数口径 = 4）→ 与
        # Top-1 可疑行重叠（行号取值经 _patch_changed_lines 实测锁定）
        state["fl_spectral_focus"] = {"top_k": [{"line": 4, "score": 0.9}]}

        update = _patch_applier_node(state)  # type: ignore[arg-type]

        assert update["repair_history"][-1]["patch_applied"] is True
        assert update["patch_evidence_level"] == "sbfl"
        assert update["source_patched_unverified"] is False
        assert (tmp_path / "mod.py").read_text() != original

    def test_gold_evidence_patch_allowed(self, tmp_path, monkeypatch):
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        monkeypatch.delenv("PATCH_EVIDENCE_GATE_ENABLE", raising=False)
        original = "def f():\n    return 1\n"
        state = self._state(tmp_path, original, "def f():\n    return 2\n")
        state["repo_verification"] = {"passed": True}

        update = _patch_applier_node(state)  # type: ignore[arg-type]

        assert update["repair_history"][-1]["patch_applied"] is True
        assert update["patch_evidence_level"] == "gold"
        assert update["source_patched_unverified"] is False

    def test_opt_out_keeps_legacy_behavior(self, tmp_path, monkeypatch):
        # opt-out（false）→ 历史口径：无证据补丁照常写盘（消融对照）
        from src.graph.nodes import _patch_applier_node

        monkeypatch.setenv("PATCH_PROTECT_REPO_CORE", "0")
        monkeypatch.setenv("PATCH_EVIDENCE_GATE_ENABLE", "false")
        original = "def f():\n    return 1\n"
        state = self._state(tmp_path, original, "def f():\n    return 2\n")

        update = _patch_applier_node(state)  # type: ignore[arg-type]

        assert update["repair_history"][-1]["patch_applied"] is True
        assert update["patch_evidence_level"] in ("keyword", "none")
        assert (tmp_path / "mod.py").read_text() != original
