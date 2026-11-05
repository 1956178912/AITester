"""B8（2026-11-05，用户选定口径）：任务级缺陷 ⇒ 具名剔除；数据集闸 ⇒ 真正参与选面。

两条独立缺陷（同一次冒烟抓到）：

1. **任务级缺陷阻断整面**：`check-dataset swebench` 因 225 个任务里 8 个不可判
   （2 个无源码、6 个 `test_code` 里没有 Python 测试用例）整面判红，而那 6 个
   任务仍在付费分母里（严格源码口径只管"无源码"）。⇒ 加一条同族严格口径：
   **测试材料不可判定的任务也不进分母、不付费**，剔除具名披露。
2. **闸不消费自己的结果**：`dataset_gate_*` 只作为阶段铺在 LLM 段之前，没有任何
   代码读它的退出码 ⇒ 红面照样付费，而整轮 rc=1 ⇒ 冒烟证据不可用、full 档开不了。
   ⇒ 闸结果进入选面：红面剔除并披露，不进批、不付费、不再毒化 rc。

严格口径默认关（ADR-0003），跑批阶段 env 显式开启；`gate=None` 时 `llm_scale_plan`
保持纯算式（既有测试与投影路径逐位不变，也避免测试去依赖作者机盘面数据）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import scripts.run_all_tests as runner
from src.datasets.dataset_loader import SWEBenchDataset

# 三种形态：健康 / 测试代码里没有用例 / 用例数未知（通过率无分母）
_GOOD = {
    "instance_id": "repo__good-1",
    "repository": "repo/good",
    "problem_statement": "Fix bug",
    "instance_code": "def f():\n    return 1\n",
    "test_before_patches": "def test_f():\n    assert f() == 1\n",
    "n_tests_before": 1,
    "pass_num_before": 0,
    "pass_num_after": 1,
}
_NO_CASES = {
    "instance_id": "repo__nocases-1",
    "repository": "repo/nocases",
    "problem_statement": "Fix bug",
    "instance_code": "def f():\n    return 1\n",
    # sqlfluff 形态的真实反例：test_patch 只动夹具/说明文件，没有 Python 用例
    "test_before_patches": "# updated fixture expectations\n",
    "n_tests_before": 1,
    "pass_num_before": 0,
    "pass_num_after": 1,
}
_ZERO_TESTS = {
    "instance_id": "repo__zerotests-1",
    "repository": "repo/zerotests",
    "problem_statement": "Fix bug",
    "instance_code": "def f():\n    return 1\n",
    "test_before_patches": "def test_f():\n    assert f() == 1\n",
    "n_tests_before": 0,
    "pass_num_before": 0,
    "pass_num_after": 0,
}
_NO_SOURCE = {
    "instance_id": "repo__nosource-1",
    "repository": "repo/nosource",
    "problem_statement": "Fix bug (issue text only)",
    "test_before_patches": "def test_f():\n    assert f() == 1\n",
    "n_tests_before": 1,
    "pass_num_before": 0,
    "pass_num_after": 1,
}


def _dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> SWEBenchDataset:
    jsonl = tmp_path / "swe_bench_instances.jsonl"
    jsonl.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    monkeypatch.setenv("SWE_BENCH_DATA_DIR", str(tmp_path))
    ds = SWEBenchDataset()
    ds._loaded = False
    return ds


@pytest.mark.unit
class TestStrictTestCodeCaliber:
    def test_default_off_keeps_every_task(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：开关不设 ⇒ 三个任务照加载（历史口径逐位不变），问题仍由 validate_task 点名。"""
        monkeypatch.delenv("AITESTER_DATASET_STRICT_TEST_CODE", raising=False)
        ds = _dataset(tmp_path, monkeypatch, [_GOOD, _NO_CASES, _ZERO_TESTS])
        ids = [t.task_id for t in ds]
        assert ids == [_GOOD["instance_id"], _NO_CASES["instance_id"], _ZERO_TESTS["instance_id"]]
        report = ds.quality_report()
        assert _NO_CASES["instance_id"] in report and _ZERO_TESTS["instance_id"] in report
        assert ds.strict_skipped_test_task_ids == []

    def test_strict_on_drops_unjudgeable_test_material(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AITESTER_DATASET_STRICT_TEST_CODE", "true")
        ds = _dataset(tmp_path, monkeypatch, [_GOOD, _NO_CASES, _ZERO_TESTS])
        assert [t.task_id for t in ds] == [_GOOD["instance_id"]]
        assert sorted(ds.strict_skipped_test_task_ids) == [_NO_CASES["instance_id"], _ZERO_TESTS["instance_id"]]

    def test_drop_is_disclosed_not_silent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
        """剔除必须点名：静默少跑会被读成跑通（本仓已发生多次的事故类）。"""
        import logging

        monkeypatch.setenv("AITESTER_DATASET_STRICT_TEST_CODE", "true")
        with caplog.at_level(logging.WARNING, logger="src.datasets.dataset_loader"):
            ds = _dataset(tmp_path, monkeypatch, [_GOOD, _NO_CASES])
            list(ds)
        text = "\n".join(r.message for r in caplog.records)
        assert _NO_CASES["instance_id"] in text, f"未按任务点名剔除：{text[:200]}"
        assert "测试材料" in text

    def test_two_reasons_stay_in_separate_lists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """两条严格口径各记各的：源码缺失 ≠ 测试材料缺失（provenance 要能分辨）。"""
        monkeypatch.setenv("AITESTER_DATASET_STRICT_INSTANCE_CODE", "true")
        monkeypatch.setenv("AITESTER_DATASET_STRICT_TEST_CODE", "true")
        ds = _dataset(tmp_path, monkeypatch, [_GOOD, _NO_SOURCE, _NO_CASES])
        assert [t.task_id for t in ds] == [_GOOD["instance_id"]]
        assert ds.strict_skipped_task_ids == [_NO_SOURCE["instance_id"]]
        assert ds.strict_skipped_test_task_ids == [_NO_CASES["instance_id"]]

    def test_provenance_counts_both_lists(self) -> None:
        """源码锁：批次 provenance 必须把两条剔除清单都算进去，否则分母缺口不可见。"""
        import importlib
        import inspect

        # `__import__("a.b")` 返回**顶层包**（a），拿到的源码里没有子模块——用 importlib
        src = inspect.getsource(importlib.import_module("experiments.run_benchmark"))
        assert "strict_skipped_test_task_ids" in src, "provenance 只读源码清单，测试材料剔除进不了批次工件"


@pytest.mark.unit
class TestGatePrunesFaces:
    @staticmethod
    def _args(tmp_path: Path, extra: list[str]) -> Any:
        return runner.build_parser().parse_args(["--spec", "smoke", "--out", str(tmp_path / "run"), *extra])

    def test_red_face_is_dropped_and_disclosed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs", "swebench"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _n: 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda n: (50, f"{n}__first", f"{n}__last"))
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        args = self._args(tmp_path, ["--llm-arms", "aitester"])
        scale = runner.llm_scale_plan(args, 1, gate=lambda ds: 1 if ds == "swebench" else 0)
        assert scale["datasets"] == ["quixbugs"], scale["datasets"]
        assert scale["gate_dropped"] == {"swebench": "数据集闸 exit=1"}
        assert "swebench" in capsys.readouterr().out
        # 剔除必须进规模算式：面数与任务数都只剩 quixbugs（否则投影仍在为被剔的面算钱）
        assert "swebench" not in scale["plan"]["scale"]
        assert scale["face_counts"] == {"quixbugs": 1}

    def test_gate_none_leaves_the_pure_plan_unchanged(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`gate=None` ⇒ 不消费任何闸结果（既有投影/测试路径逐位不变，也不依赖作者机数据）。"""
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _n: 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda _n: (50, "a", "b"))
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        args = self._args(tmp_path, ["--llm-arms", "aitester"])
        scale = runner.llm_scale_plan(args, 1)
        assert scale["datasets"] == ["quixbugs"]
        assert scale["gate_dropped"] == {}

    def test_all_faces_rejected_refuses_instead_of_running_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs", "swebench"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _n: 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda n: (50, f"{n}__a", f"{n}__b"))
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        args = self._args(tmp_path, ["--llm-arms", "aitester"])
        scale = runner.llm_scale_plan(args, 1, gate=lambda _ds: 1)
        assert scale["datasets"] == []
        assert scale["plan"]["provable"] is False and scale["plan"]["fits_budget"] is False
        assert "闸" in scale["plan"]["reason"]

    def test_sweep_no_longer_schedules_gate_stages(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """闸红不再毒化 rc：它现在是选面输入，不是阶段。"""
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _n: 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda _n: (50, "quixbugs__bitcount", "quixbugs__wrap"))
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        args = self._args(tmp_path, ["--llm-arms", runner.DEFAULT_LLM_ARMS])
        stages = runner.build_full_stages(args, 1, Path(args.out), tasks_per_cell=1, gate=lambda _ds: 0)
        assert not [s for s in stages if str(s["name"]).startswith("dataset_gate_")], "闸仍以阶段身份毒化 rc"
        assert any("__" in str(s["name"]) for s in stages), "剔除闸阶段时把 LLM 段也弄没了"

    def test_gate_verdict_shares_the_stage_caliber(self) -> None:
        """闸与跑批必须同一口径：否则闸判绿的面，实跑按另一口径付费（数面≠跑面）。"""
        caliber = runner.protocol_caliber_env()
        for key in (runner._STRICT_INSTANCE_CODE_KEY, runner._OFFICIAL_TESTS_GOLD_KEY):
            assert key in caliber or key == runner._OFFICIAL_TESTS_GOLD_KEY
        assert caliber.get(runner._STRICT_INSTANCE_CODE_KEY) == "true"
        assert caliber.get(runner._STRICT_TEST_CODE_KEY) == "true"
        assert runner._STRICT_TEST_CODE_KEY == "AITESTER_DATASET_STRICT_TEST_CODE"
