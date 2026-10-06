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


class TestV5NeutralTaskIds:
    """V5：合成数据集 task_id 中性化（P1-4 评估泄漏修复）。

    锁定：task_id 末段为中性 task_XXXX（不含 pattern 语义），且 gold
    test_cases 的 import 与该中性模块名一致（M1 裁决与生成测试同名）。
    pattern 名仅保留在 metadata.pattern_name（分析用，不进 prompt）。
    """

    def test_task_id_neutral_and_gold_import_matches(self):
        from src.datasets.synthetic_dataset import SyntheticDataset

        ds = SyntheticDataset(task_count=6, seed=42)
        for t in ds.tasks:
            mod = t.task_id.split("__")[-1]
            assert mod.startswith("task_"), f"task_id 末段必须中性：{t.task_id}"
            assert t.metadata.get("pattern_name"), "pattern 名保留在 metadata 供分析"
            gold = t.metadata.get("test_cases") or ""
            if t.metadata.get("is_cross_file"):
                continue  # 跨文件 import module_a/b/c（本身中性）
            assert f"from {mod} import" in gold or f"import {mod}" in gold, (
                f"gold import 必须与中性模块名一致：{t.task_id}"
            )
            assert t.metadata.get("pattern_name") not in t.task_id

    def test_same_seed_same_task_ids(self):
        from src.datasets.synthetic_dataset import SyntheticDataset

        ids_a = [t.task_id for t in SyntheticDataset(task_count=5, seed=7).tasks]
        ids_b = [t.task_id for t in SyntheticDataset(task_count=5, seed=7).tasks]
        assert ids_a == ids_b, "同 seed 的中性 task_id 序列必须稳定"


class TestV6MainBatchReproGates:
    """V6：主批次 runner 复现性前置守卫（P0-1）。

    锁定：dirty tree 硬失败（SystemExit 2）、--allow-dirty 豁免；
    --no-deterministic 旗标解析（默认确定性开）。
    """

    def test_dirty_tree_rejected(self, tmp_path, monkeypatch):
        import subprocess

        from experiments.run_main_batch import _check_repo_clean

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": " M f.py\n"})())
        try:
            _check_repo_clean()
        except SystemExit as e:
            assert e.code == 2, "dirty tree 必须硬失败退出码 2"
        else:
            raise AssertionError("dirty tree 未被拒绝")

    def test_clean_tree_passes(self, monkeypatch):
        import subprocess

        from experiments.run_main_batch import _check_repo_clean

        monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())
        result = _check_repo_clean()  # 干净树返回 None（不抛 SystemExit）
        assert result is None

    def test_no_deterministic_flag_parsed(self, monkeypatch):
        import sys as _sys

        import experiments.run_main_batch as rmb

        monkeypatch.setattr(_sys, "argv", ["run_main_batch.py", "--no-deterministic"])
        args = rmb._parse_args()
        assert args.no_deterministic is True
        assert args.allow_dirty is False


class TestV6bMainBatchPatternRepeatPassthrough:
    """V6b：主批次 runner 透传 --max-pattern-repeat（R-P0-4，AA 批次口径）。

    锁定：argparse 解析（默认 None / 显式 N）与 kwargs 透传到
    run_benchmark.run_benchmark（仅 synthetic 生效的历史口径不变）。
    """

    def _run_main_capture(self, monkeypatch, tmp_path, argv):
        """跑 rmb.main()，捕获透传给 run_benchmark 的 kwargs（统计被跳过）。"""
        import subprocess
        import sys as _sys

        import experiments.run_benchmark as rb
        import experiments.run_main_batch as rmb

        captured: dict = {}

        def fake_run_benchmark(**kwargs):
            captured.update(kwargs)
            return {"results": {}}

        monkeypatch.setattr(_sys, "argv", ["run_main_batch.py", *argv])
        monkeypatch.setattr(rb, "run_benchmark", fake_run_benchmark)
        # 密闭化：干净树检查打桩，不依赖运行测试时的真实工作树状态
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())
        monkeypatch.setattr(rmb, "_warn_llm_cache_if_enabled", lambda: None)
        rmb.main()
        return captured

    def test_flag_parsed_default_none(self, monkeypatch):
        import sys as _sys

        import experiments.run_main_batch as rmb

        monkeypatch.setattr(_sys, "argv", ["run_main_batch.py"])
        args = rmb._parse_args()
        assert args.max_pattern_repeat is None, "默认必须 None（历史口径）"

    def test_passthrough_reaches_run_benchmark(self, tmp_path, monkeypatch):
        captured = self._run_main_capture(
            monkeypatch,
            tmp_path,
            [
                "--dataset",
                "synthetic",
                "--task-count",
                "5",
                "--seed",
                "42",
                "--baselines",
                "plain_llm",
                "--output-dir",
                str(tmp_path / "out"),
                "--skip-stats",
                "--max-pattern-repeat",
                "2",
            ],
        )
        assert captured["max_pattern_repeat"] == 2
        assert captured["task_count"] == 5
        assert captured["seed"] == 42
        assert captured["baselines"] == ["plain_llm"]
        assert captured["deterministic"] is True, "默认确定性采样协议不得被透传改动破坏"

    def test_default_none_keeps_legacy_behavior(self, tmp_path, monkeypatch):
        captured = self._run_main_capture(
            monkeypatch,
            tmp_path,
            [
                "--dataset",
                "synthetic",
                "--output-dir",
                str(tmp_path / "out"),
                "--skip-stats",
            ],
        )
        assert captured["max_pattern_repeat"] is None, "不带旗标时必须显式传 None（历史口径）"


class TestV7ConfidenceWiring:
    """V7：错误置信度接线 + reward simplicity 语义（P2-4 / P2-5）。"""

    def test_debugger_result_contains_error_confidence(self, monkeypatch):
        """debugger.debug 返回 dict 必含 error_confidence（规则层 0.2/0.5/0.9）。"""
        from src.agents.debugger import DebuggerAgent
        from src.agents.error_classifier import ErrorClassifier

        monkeypatch.setattr("src.agents.base_agent.BaseAgent.__init__", lambda self, *a, **k: None)
        agent = DebuggerAgent()  # system prompt 设置被跳过，classifier 正常实例化
        assert isinstance(agent.classifier, ErrorClassifier)
        # classify_with_confidence 走规则层（无 LLM），直接构造最小调用
        result = agent.classifier.classify_with_confidence(
            "E   assert 3 == 4\nE   +  where 3 = add(1, 2)\n",
            target_module="mod",
            failed_cases=[{"name": "test_x"}],
            enable_fallback=False,
        )
        assert result.confidence in (0.2, 0.5, 0.9)
        assert result.category is not None

    def test_state_declares_confidence_keys(self):
        """error_confidence / risk_approval_decision 已声明为 state 键（防
        LangGraph 通道静默丢弃——M14/O35 同类事故的守卫）。"""
        from src.graph.state import AITesterState, create_initial_state

        init = create_initial_state(
            task_uuid="v7-test", target_file="/tmp/v7_mod.py", target_code="def f():\n    return 1\n", max_iterations=3
        )
        assert "error_confidence" in init
        assert "risk_approval_decision" in init
        assert "error_confidence" in AITesterState.__annotations__
        assert "risk_approval_decision" in AITesterState.__annotations__

    def test_reward_simplicity_is_patch_size_not_elapsed(self):
        """P2-5：simplicity 必须对补丁行数敏感、对耗时无感（历史口径
        simplicity=1-elapsed/(2*TIMEOUT) 与 efficiency 同源的语义失真）。"""
        from src.graph.nodes import _compute_reward_signals

        # 同耗时、不同补丁体量 → simplicity 必须不同
        small = _compute_reward_signals(True, None, 5.0, patch_line_delta=2)
        big = _compute_reward_signals(True, None, 5.0, patch_line_delta=30)
        assert small["simplicity"] > big["simplicity"]
        assert small["simplicity"] == 1.0 - 2 / 30 or small["simplicity"] > 0.9
        assert big["simplicity"] == 0.0
        # None（无补丁来源）→ 保守 0
        assert _compute_reward_signals(True, None, 5.0)["simplicity"] == 0.0
        # efficiency 仍只随耗时变化
        assert (
            _compute_reward_signals(True, None, 5.0, patch_line_delta=2)["efficiency"]
            == (_compute_reward_signals(True, None, 5.0, patch_line_delta=30)["efficiency"])
        )
