"""B12（2026-11-05）：满跑并发按厂商额度的 80%，并受机器侧闸约束。

背景（冒烟实测，`test_run_20261105T115002Z`，79 阶段 / 50 格 / 152.9 分钟）：
每格并发被 `LLM_PARALLELISM_CAP = 4` 钉死，与厂商额度无关；心跳 `load/core 0.27`、
`mem 14.6/24 GB` ⇒ 时间几乎全花在等待本地测试子进程超时，不在 API。按 183s/任务
线性外推，满量档 1,464 任务 ≈ **74.6 小时**，远超 `--max-wall-hours=12` ⇒ 并发不是
优化项，是满量档能否跑完的前提。

额度语义必须分开（文档核实，2026-11-05）：
- **DeepSeek**（https://api-docs.deepseek.com/zh-cn/quick_start/rate_limit）给的是
  **在途并发**：`deepseek-flash` 2500、`deepseek-v4-pro` 500，语义"一个请求从发出后，
  到模型响应完成之前记为一个并发"；该页**没有** RPM/TPM 条目。
- **MiMo**（https://mimo.mi.com/docs/zh-CN/quick-start/summary/model）给的是
  **RPM 100 / TPM 10M**，没有并发数。
⇒ 一个"每分钟请求数"不能当"同时在途请求数"用：80% 落到 deepseek 是"至多 2000 在途"，
落到 mimo 是"每分钟至多发起 80 次"。本文件锁的就是这个区别不被写成同一个数。
"""

from __future__ import annotations

from typing import Any

import pytest

import scripts.run_all_tests as runner
from src.config.config_generator import MODEL_RATE_LIMITS, OPERATING_FRACTION

# ─── 额度登记面 ──────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestDeclaredAllowances:
    def test_values_match_the_vendor_docs(self) -> None:
        """值与出处逐字对账（不得凭记忆改数）。"""
        assert MODEL_RATE_LIMITS["deepseek-flash"] == {"kind": "in_flight", "limit": 2500}
        assert MODEL_RATE_LIMITS["deepseek-v4-pro"] == {"kind": "in_flight", "limit": 500}
        assert MODEL_RATE_LIMITS["mimo-v2.6-pro"] == {"kind": "rpm", "limit": 100, "tpm": 10_000_000}

    def test_operating_point_is_eighty_percent(self) -> None:
        assert OPERATING_FRACTION == 0.8
        assert runner.provider_concurrency_allowance("deepseek-flash") == 2000
        assert runner.provider_concurrency_allowance("deepseek-v4-pro") == 400

    def test_rpm_limit_is_not_reported_as_a_concurrency_number(self) -> None:
        """RPM 不是并发数：mimo 的 80 是"每分钟发起数"，不能当在途上限用。"""
        assert runner.provider_concurrency_allowance("mimo-v2.6-pro") is None
        assert runner.provider_rate_per_minute_allowance("mimo-v2.6-pro") == 80
        assert runner.provider_rate_per_minute_allowance("deepseek-flash") is None

    def test_unregistered_model_degrades_to_no_provider_cap(self) -> None:
        """没登记额度的模型不猜数：返回 None ⇒ 只受机器侧闸约束。"""
        assert runner.provider_concurrency_allowance("some-future-model") is None
        assert runner.provider_rate_per_minute_allowance("some-future-model") is None


# ─── 机器侧闸与取值合并 ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestMachineGuard:
    @pytest.mark.parametrize(
        "cpu,mem_gb,want",
        [
            pytest.param(10, 24.0, 24, id="作者机（10 核 / 24GB）"),
            pytest.param(4, 8.0, 8, id="小机器按核数×2.4 与内存双限取小"),
            pytest.param(64, 256.0, 40, id="大机器仍受在途上限 40 约束"),
            pytest.param(1, 2.0, 2, id="下限：至少 2，退回历史量级"),
        ],
    )
    def test_machine_parallelism_cap(self, cpu: int, mem_gb: float, want: int) -> None:
        assert runner.machine_parallelism_cap(cpu, mem_gb) == want

    def test_cap_uses_available_memory_not_total_when_available_given(self) -> None:
        """24GB 总内存但只剩 3GB 可用时，闸必须按**可用**量收——否则并发一开就 OOM。"""
        assert runner.machine_parallelism_cap(10, 24.0, available_gb=3.0) == 6
        assert runner.machine_parallelism_cap(10, 24.0) == 24

    def test_unusable_sampling_falls_back_to_conservative_floor(self) -> None:
        """采样失败（psutil 缺失/返回 -1）⇒ 宁保守也不放开并发。"""
        assert runner.machine_parallelism_cap(0, -1.0) == 2
        assert runner.machine_parallelism_cap(-4, 0.0) == 2


@pytest.mark.unit
class TestResolveLlmParallelism:
    def test_machine_cap_binds_when_the_provider_allowance_is_loose(self) -> None:
        """deepseek-flash 的 2000 在途远高于本机能力 ⇒ binding 必须是 machine（额度不该被当成"可以开到 2000"）。"""
        got = runner.resolve_llm_parallel("deepseek-flash", cpu=10, mem_gb=24.0, override=None)
        assert got["parallelism"] == 24
        assert got["binding"] == "machine", got

    def test_a_tight_provider_allowance_binds(self) -> None:
        got = runner.resolve_llm_parallel(
            "deepseek-flash", cpu=10, mem_gb=24.0, override=None, provider_limit_override=10
        )
        assert got["parallelism"] == 10
        assert got["binding"] == "provider"

    def test_explicit_override_still_respects_the_provider_ceiling(self) -> None:
        """`--llm-parallel` 是运维旋钮，但不得越过厂商 80% 线（越线只会换来 429）。"""
        got = runner.resolve_llm_parallel("deepseek-v4-pro", cpu=64, mem_gb=256.0, override=1000)
        # min(显式 1000, 额度 400, 机器 40) = 40 ⇒ binding 是机器，但越额度这件事必须被点名
        assert got["parallelism"] == 40, got
        assert got["binding"] == "machine" and got["provider_cap"] == 400, got
        assert "已按额度封顶" in got["note"], got

    def test_rpm_model_is_flagged_separately(self) -> None:
        """mimo 档：并发由机器定，但读数里必须带上"每分钟发起数"这道限。"""
        got = runner.resolve_llm_parallel("mimo-v2.6-pro", cpu=10, mem_gb=24.0, override=None)
        assert got["parallelism"] == 24
        assert got["provider_kind"] == "rpm"
        assert got["rate_per_minute"] == 80

    def test_unregistered_model_uses_machine_only(self) -> None:
        got = runner.resolve_llm_parallel("mystery-model", cpu=10, mem_gb=24.0, override=None)
        assert got["parallelism"] == 24
        assert got["provider_kind"] == "unknown"


# ─── 跑批面：并发必须进指纹与报告 ─────────────────────────────────────────


@pytest.mark.unit
class TestConcurrencyIsAuditable:
    def test_stages_carry_the_resolved_parallelism(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """每格 `-p` 必须等于解析出的并发，且值随模型变（RPM 档与在途档不同）。"""
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _n: 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda _n: (50, "a", "b"))
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["mimo-v2.6-pro"], {"mimo-v2.6-pro": 8.0}, "CNY"))
        monkeypatch.setattr(runner, "detect_cpu_count", lambda: 8)
        monkeypatch.setattr(runner, "detect_memory_gb", lambda: 16.0)
        # 可用内存必须钉住：装了 psutil 的机器上它是波动的实测量，不钉住本锁就
        # 变成"由本机当时的空闲内存决定"（判据随机器历史漂移）
        monkeypatch.setattr(runner, "available_memory_gb", lambda: None)
        args = runner.build_parser().parse_args(
            ["--spec", "smoke", "--out", str(tmp_path / "run"), "--skip-dataset-gate", "--llm-arms", "aitester"]
        )
        stages = runner.build_full_stages(args, 8, tmp_path / "run", tasks_per_cell=1)
        sweep = [s for s in stages if "__" in str(s["name"])]
        assert sweep, "阶段清单为空 ⇒ 本锁在判空气"
        for stage in sweep:
            p_index = stage["command"].index("-p")
            # 机器闸 = min(核数×2.4=19, 内存 16GB→16, 硬顶 40) = 16
            assert stage["command"][p_index + 1] == "16", stage["command"]
            assert stage["llm_parallel"]["binding"] == "machine", stage["llm_parallel"]
            assert stage["llm_parallel"]["rate_per_minute"] == 80

    def test_fingerprint_includes_the_parallelism(self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """并发改变"同一次配置"的含义：换了并发跑出的冒烟证据不得被 full 档当成同配置复用。"""
        monkeypatch.setattr(runner, "detect_cpu_count", lambda: 10, raising=False)
        monkeypatch.setattr(runner, "detect_memory_gb", lambda: 24.0, raising=False)
        payload_a: dict[str, Any] = {}
        runner.apply_concurrency_fingerprint(
            payload_a,
            {"deepseek-flash": runner.resolve_llm_parallel("deepseek-flash", cpu=10, mem_gb=24.0, override=None)},
        )
        payload_b: dict[str, Any] = {}
        runner.apply_concurrency_fingerprint(
            payload_b,
            {"deepseek-flash": runner.resolve_llm_parallel("deepseek-flash", cpu=4, mem_gb=8.0, override=None)},
        )
        assert payload_a["llm_parallelism"] != payload_b["llm_parallelism"], (
            "两档并发算出同一指纹 ⇒ 冒烟证据会被跨配置误用"
        )
        assert payload_a["llm_parallelism"]["deepseek-flash"]["parallelism"] == 24


@pytest.mark.unit
class TestTimeoutAttribution:
    """B11（2026-11-05）：60s 档被两个门共用，超时日志必须点名是谁烧的。"""

    _HANG = "import time\n\n\ndef test_hang():\n    time.sleep(30)\n"

    def test_official_test_gate_names_itself(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        import src.tools.detection_gates as dg

        with caplog.at_level(logging.WARNING):
            res = dg.run_official_tests(self._HANG, "def f():\n    return 1\n", "b11mod", timeout=1)
        assert res["verdict"] == "unavailable"
        text = "\n".join(r.message for r in caplog.records)
        assert "B1 官方测试门：执行超时（>1s）" in text, text[:300]

    def test_the_two_gates_do_not_share_one_label(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.tools.detection_gates as dg

        seen: list[str] = []

        def _spy(*args: Any, **kwargs: Any) -> None:
            # logger_name 在两个调用点都是**位置参数**，桩必须两边都接得住
            seen.append(str(kwargs.get("logger_name") or (args[5] if len(args) > 5 else "m1_metrics")))

        monkeypatch.setattr(dg, "_pytest_in_tmp_raw", _spy)
        dg._run_test_against_code("def test_x():\n    assert 1\n", "x = 1", "m")
        dg.run_official_tests("def test_x():\n    assert 1\n", "x = 1", "m")
        assert seen == ["AC2 对照门", "B1 官方测试门"], seen

    def test_m1_default_label_is_unchanged(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """对照腿：不传标签时仍是历史措辞 `m1_metrics`（既有日志检索/锁不外溢）。"""
        import subprocess

        import src.utils.process_utils as pu

        got: dict[str, object] = {}

        def _recorder(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
            got["logger_name"] = kwargs.get("logger_name")
            return subprocess.CompletedProcess(list(cmd), 0, "", "")

        # `_run_pytest_in_tmp` 在函数体内延迟 import，故必须打在源模块上才取得到
        import experiments._m1_metrics as m1_mod

        monkeypatch.setattr(pu, "run_with_timeout", _recorder)
        m1_mod._run_pytest_in_tmp("def test_x():\n    assert 1\n", "x = 1", "m11mod", timeout=5)
        assert got["logger_name"] == "m1_metrics", got
