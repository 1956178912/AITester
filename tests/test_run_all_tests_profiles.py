"""GL 轮（2026-11-04）：全量运行器的两档口径、进度读数与卡死检测。

一次命令跑完所有测试（用户第 11 条）在这里拆成两档：

- **smoke**：所有面各跑一项（pytest 每个文件 1 个 nodeid、LLM 每格 1 个任务），
  回答"管路通不通"，不产出判定读数；
- **full**：最大量（`make test-cov` 全量+覆盖率 → `make gates` 全链 → LLM 跑满每面）。

两档的先后不是建议而是判据：**冒烟未全通，全量一个阶段都不许开跑**——全量会真
实花钱，而"钱花在一条装配就坏了的管路上"是本仓反复判红的那一类浪费。

卡死检测必须是被测的：旧实现用 `for line in proc.stdout` 阻塞读、把墙钟判断写在
循环体内，子进程一声不出时循环根本不转，于是"卡死"恰好是唯一不会被发现的失效
模式。本文件用真实睡眠子进程把这条判据钉住（含进程组击杀后孙进程也不留）。
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from scripts import run_all_tests as runner

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _run_roots_land_in_pytemp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """本文件的运行临时根一律落到 pytest 自己的 tmp_path（跑完由 pytest 回收）。

    `run_tmp_root` 取系统临时目录；测试若不打桩，每个用例都会在那里留一个
    `aitester-run-*` 目录。本仓刚被"每判定一个临时目录、从不回收"堆到 196 万条目
    拖慢判定，不能自己再造一个同款泄漏。tmp_path 在系统临时区，仓库外的边界照样成立。
    """
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))
    yield


def _args(tmp_path: Path, extra: list[str]):
    return runner.build_parser().parse_args(["--out", str(tmp_path / "out"), *extra])


class TestLineBufferedProgress:
    def test_helper_sets_line_buffering_on_real_streams(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        sink = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)
        monkeypatch.setattr(sys, "stdout", sink)
        assert sink.line_buffering is False, "前提：TextIOWrapper 默认非行缓冲"
        runner._enable_line_buffered_output()
        assert sink.line_buffering is True

    def test_streams_without_reconfigure_do_not_break_main(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """pytest capture 形状的流（无 `reconfigure`）下 `main` 仍正常返回，不抛。"""

        class _PlainStream:
            def __init__(self) -> None:
                self.chunks: list[str] = []

            def write(self, text: str) -> int:
                self.chunks.append(text)
                return len(text)

        stream = _PlainStream()
        monkeypatch.setattr(sys, "stdout", stream)
        assert not hasattr(stream, "reconfigure"), "前提：capture 面没有 reconfigure"
        assert runner.main(["--selftest"]) == 0
        assert any("档位" in chunk for chunk in stream.chunks), "进度面应写到传入的流上"


class TestSmokeSampling:
    def test_one_node_id_per_file(self, tmp_path: Path) -> None:
        log = tmp_path / "collect.log"
        log.write_text(
            "tests/test_a.py::test_one\ntests/test_a.py::test_two\ntests/test_b.py::TestC::test_three\n"
            "tests/test_z.py::test_last\n2 tests collected in 0.01s\n",
            encoding="utf-8",
        )
        picked = runner._first_node_id_per_file(log)
        assert picked == [
            "tests/test_a.py::test_one",
            "tests/test_b.py::TestC::test_three",
            "tests/test_z.py::test_last",
        ]

    def test_noise_lines_are_not_mistaken_for_node_ids(self, tmp_path: Path) -> None:
        log = tmp_path / "collect.log"
        log.write_text(
            "collected 3 items\ntests/test_a.py::test_one \n  warnings summary\nplatform darwin -- Python 3.14.6\n",
            encoding="utf-8",
        )
        assert runner._first_node_id_per_file(log) == ["tests/test_a.py::test_one"]

    def test_missing_log_yields_empty_plan(self, tmp_path: Path) -> None:
        assert runner._first_node_id_per_file(tmp_path / "nope.log") == []

    def test_empty_plan_is_a_red_stage(self, tmp_path: Path) -> None:
        """收集面取不到任何东西时必须是红——"没有阶段"绝不能读作"全通"。"""
        args = _args(tmp_path, ["--no-llm"])
        stages = runner.build_smoke_stages(args, 1, Path(args.out), [])
        names = [s["name"] for s in stages]
        assert "pytest_smoke_no_samples" in names, names
        assert not any(name.startswith("pytest_smoke_1") for name in names), names

    def test_real_collect_output_yields_node_ids(self, tmp_path: Path) -> None:
        """形状锁：按运行器真实口径收集一个文件，必须能解析出 nodeid 行。

        本仓 addopts 带 `-v`，`-q` 会退化成 `<Function …>` 收集树（GL 实测），
        这条锁保证 `-qq` 的取值不被 pytest 升级悄悄改掉。
        """
        log = tmp_path / "collect.log"
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_env_utils.py",
                "--collect-only",
                "-qq",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
            timeout=300,
            check=False,
        )
        log.write_text(proc.stdout, encoding="utf-8")
        picked = runner._first_node_id_per_file(log)
        assert picked == ["tests/test_env_utils.py::TestEnvFlagEquivalence::test_unset_returns_default_false"], picked


class TestFingerprintAndEvidence:
    def test_matrix_knobs_move_the_fingerprint(self, tmp_path: Path) -> None:
        base = runner.config_fingerprint(_args(tmp_path, ["--llm-arms", "aitester"]), ["m1"])
        wider = runner.config_fingerprint(_args(tmp_path, ["--llm-arms", "aitester,plain_llm"]), ["m1"])
        more_models = runner.config_fingerprint(_args(tmp_path, ["--llm-arms", "aitester"]), ["m1", "m2"])
        assert base != wider != more_models

    def test_irrelevant_knobs_do_not(self, tmp_path: Path) -> None:
        """`--jobs` / `--out` 不改变"哪些面被覆盖"，进指纹会让每次换目录都要重跑冒烟。"""
        one = runner.config_fingerprint(_args(tmp_path, ["--jobs", "4"]), ["m1"])
        two = runner.config_fingerprint(_args(tmp_path / "other", ["--jobs", "8"]), ["m1"])
        assert one == two

    def test_evidence_round_trip_and_fingerprint_binding(self, tmp_path: Path) -> None:
        out = tmp_path / "test_run_20261104T000000Z"
        out.mkdir()
        results = [runner.StageResult(name="pytest_smoke_1", command=["x"], exit_code=0, attempts=1)]
        fp = "deadbeef00000000"
        evidence = runner.write_smoke_evidence(out, fp, results)
        assert evidence["ok"] is True
        assert json.loads((out / runner.SMOKE_GATE_FILE).read_text(encoding="utf-8"))["fingerprint"] == fp
        assert runner.find_smoke_evidence(out, fp) is not None
        assert runner.find_smoke_evidence(out, "0000000000000000") is None

    def test_failed_smoke_is_not_evidence(self, tmp_path: Path) -> None:
        out = tmp_path / "test_run_20261104T010000Z"
        out.mkdir()
        results = [runner.StageResult(name="llm_aitester__quixbugs", command=["x"], exit_code=1, attempts=2)]
        fp = "cafebabefacedbad"
        assert runner.write_smoke_evidence(out, fp, results)["ok"] is False
        assert runner.find_smoke_evidence(out, fp) is None

    def test_no_results_is_not_evidence(self, tmp_path: Path) -> None:
        """空清单不得写成"通过"——一个阶段都没跑不等于全通。"""
        out = tmp_path / "test_run_20261104T020000Z"
        out.mkdir()
        assert runner.write_smoke_evidence(out, "abcd" * 4, [])["ok"] is False

    def test_newest_evidence_wins(self, tmp_path: Path) -> None:
        fp = "ffff0000ffff0000"
        for name, at in (
            ("test_run_20261104T000000Z", "2026-11-04T00:00:00Z"),
            ("test_run_20261105T000000Z", "2026-11-05T00:00:00Z"),
        ):
            run = tmp_path / name
            run.mkdir()
            (run / runner.SMOKE_GATE_FILE).write_text(
                json.dumps({"spec": "smoke", "ok": True, "at": at, "fingerprint": fp, "stages": []}), encoding="utf-8"
            )
        newest = tmp_path / "test_run_20261105T000000Z"
        assert runner.find_smoke_evidence(newest, fp)["at"] == "2026-11-05T00:00:00Z"


class TestArmTieredTokenCap:
    """每任务上限必须**按臂**分档：一刀切 20k 掐断的是核心干预臂，不是便宜臂。

    依据是 2026-11-05 最小批（50 格、每格 1 任务）的实测读数，不是推演：
    `experiments/results/test_run_20261104T150046Z` 里 aitester 臂在 ult 被截于
    22,880 token（`budget_exceeded`，Debugger 因此跳过修复），在 testgeneval 累计
    26,418 仍不够；single_agent 在 testgeneval 累计 26,477；而三条 plain 臂单任务最多
    只用到 10,665。20k 一刀切把核心臂判成 `budget_exceeded`（判定无效），同时给便宜臂
    一个它用不到的上界（投影虚高）。
    """

    #: 实测峰值（token/任务，含被截断格）——上限不得低于它，否则等于继续截断核心臂。
    MEASURED_HEAVY_NEED = 26_477
    MEASURED_LIGHT_NEED = 10_665

    def test_heavy_arms_get_a_cap_that_fits_the_measured_need(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        for arm in ("aitester", "single_agent"):
            assert runner.arm_token_cap(arm) >= self.MEASURED_HEAVY_NEED, arm

    def test_light_arms_do_not_inherit_the_heavy_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        caps = {runner.arm_token_cap(arm) for arm in ("plain_llm", "plain_llm_df", "plain_llm_df_spec")}
        assert len(caps) == 1, f"三条 plain 臂口径应一致，实得 {caps}"
        assert caps.pop() >= self.MEASURED_LIGHT_NEED
        assert runner.arm_token_cap("plain_llm") < runner.arm_token_cap("aitester")

    def test_thinking_on_keeps_one_cap_for_every_arm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开思考档没有按臂实测依据 ⇒ 不编造分档，全部沿用 120k。"""
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        for arm in ("aitester", "single_agent", "plain_llm", "plain_llm_df", "plain_llm_df_spec"):
            assert runner.arm_token_cap(arm) == runner.NEED_BASED_TOKEN_CAP, arm

    def test_unknown_arm_is_refused_not_guessed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """新臂没登记档位就报错：猜小 = 静默截断（B3 本尊），猜大 = 投影虚高。"""
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        with pytest.raises(ValueError, match="未登记"):
            runner.arm_token_cap("brand_new_arm")

    def test_tiers_cover_every_registered_arm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """档位表必须覆盖跑批侧注册的全部臂（写侧加臂、读侧漏登记 ⇒ 本例先红）。"""
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        from experiments.run_benchmark import BASELINE_REGISTRY

        assert BASELINE_REGISTRY, "臂注册表为空 ⇒ 本例在判空气"
        for arm in BASELINE_REGISTRY:
            assert runner.arm_token_cap(arm) > 0, f"{arm} 无档位"

    def test_every_llm_stage_carries_its_own_arm_cap(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """阶段 env 的两个闸（token 与金额）必须同源于该臂上限。

        只抬 `COST_BUDGET_TOKENS` 而 `COST_BUDGET_USD` 仍按旧一刀切算，会先被金额闸
        掐断——实测截断信息正是"22880 tokens / 0.0794 >= 上限(tokens=20000, cost=0.1600)"
        两个量并列。
        """
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        monkeypatch.setattr(
            runner, "load_price_and_models", lambda: (["synthetic-model"], {"synthetic-model": 8.0}, "CNY")
        )
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _requested: ["synthface"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _name: 1)
        monkeypatch.setattr(runner, "dataset_signature", lambda _name: (1, "t0", "t0"))
        args = _args(tmp_path, ["--skip-dataset-gate", "--llm-arms", runner.DEFAULT_LLM_ARMS])
        stages = runner.build_full_stages(args, 1, Path(args.out), tasks_per_cell=1)
        sweep = [s for s in stages if "__" in s["name"]]
        assert len(sweep) == 5, f"应铺出 5 个臂的贯通阶段，实得 {[s['name'] for s in sweep]}"
        worst = 8.0
        for stage in sweep:
            arm = stage["name"].split("__")[1]
            cap = runner.arm_token_cap(arm)
            assert stage["env"]["COST_BUDGET_TOKENS"] == str(cap), stage["name"]
            assert float(stage["env"]["COST_BUDGET_USD"]) == round(cap * worst / 1_000_000, 6), stage["name"]

    def test_projection_bound_sums_the_arm_tiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """上界按各臂自己的上限求和，而不是拿最重的档乘所有臂。"""
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        caps = {"aitester": 40_000, "single_agent": 40_000, "plain_llm": 16_000}
        # 3 臂 × 1 模型 × 每面 100 任务 = 300 任务
        plan = runner.plan_llm_budget(300, 300.0, {"synthetic-model": 8.0}, "CNY", None, arm_caps=caps)
        assert plan["caps_by_arm"] == caps
        assert plan["per_task_token_cap"] is None, "分档口径下不得再发布单一上限"
        assert plan["upper_bound"] == round(100 * sum(caps.values()) * 8 / 1_000_000, 2)

    def test_uniform_projection_is_unchanged_without_arm_caps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """不传臂档时保持原口径（单一上限），避免顺带改掉历史投影语义。"""
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        plan = runner.plan_llm_budget(500, 300.0, {"synthetic-model": 8.0}, "CNY", None)
        assert plan["per_task_token_cap"] == runner.NEED_BASED_TOKEN_CAP_THINKING_OFF
        assert plan["upper_bound"] == 80.0


class TestCaliberAwareTokenCap:
    """每任务上限按**思考档**取——沿用开思考的 120k 会把满量档无据地挡在预算外。"""

    def test_default_cap_follows_the_thinking_tier(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        assert runner.thinking_default_on() is False
        assert runner.default_task_token_cap() == runner.NEED_BASED_TOKEN_CAP_THINKING_OFF
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        assert runner.default_task_token_cap() == runner.NEED_BASED_TOKEN_CAP

    def test_full_profile_projection_fits_the_ceiling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        plan = runner.plan_llm_budget(500, 300.0, {"synthetic-model": 8.0}, "CNY", None)
        assert plan["per_task_token_cap"] == runner.NEED_BASED_TOKEN_CAP_THINKING_OFF
        assert plan["upper_bound"] == 80.0
        assert plan["fits_budget"] is True
        # 实测参考 = 500 任务 × (709 输出/调用 × 4.3 调用/任务) × ¥8/M
        assert plan["measured_reference"] == round(500 * 709 * runner.MEASURED_CALLS_PER_TASK * 8 / 1_000_000, 2)

    def test_thinking_on_projection_has_no_off_reference(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """开思考档没有 off 的实测基数 ⇒ 不给参考值，且按 120k 上界确实超预算。"""
        monkeypatch.setenv("LLM_THINKING_MODE", "enabled")
        plan = runner.plan_llm_budget(500, 300.0, {"synthetic-model": 8.0}, "CNY", None)
        assert plan["measured_reference"] is None
        assert plan["upper_bound"] == 480.0
        assert plan["fits_budget"] is False

    def test_runner_default_matches_the_production_client(self) -> None:
        """投影的思考默认必须与 `llm_client` 同源，否则算的是另一档的钱。"""
        from src.agents import llm_client

        client_text = Path(llm_client.__file__).read_text(encoding="utf-8")
        runner_text = Path(runner.__file__).read_text(encoding="utf-8")
        assert 'os.getenv("LLM_THINKING_MODE", "disabled")' in client_text
        assert 'os.getenv("LLM_THINKING_MODE", "disabled")' in runner_text


class TestNoPaidRunsWithoutSource:
    """没源码的任务既不该数进分母，也不该拿到付费调用（B4，2026-11-05）。

    最小批实测：swebench 面 225 个任务在本地盘上**全部**缺 `instance_code`（官方
    JSONL 不含源码字段），加载器兜底成 issue 文本，跑出来的 10 格全是
    `harness_invalid`。加载器侧早有 S2 严格口径（`AITESTER_DATASET_STRICT_INSTANCE_CODE`）
    会把这类任务剔除，但运行器既没在数任务时用它、也没在阶段 env 里传下去，
    于是"跑满 225 个不可判定任务"照常进投影与阶段清单。
    """

    def test_counting_a_face_applies_the_strict_source_caliber(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.datasets.dataset_loader as dl

        monkeypatch.delenv("AITESTER_DATASET_STRICT_INSTANCE_CODE", raising=False)
        seen: dict[str, str | None] = {}

        def fake_load(_name: str) -> list:
            seen["caliber"] = os.environ.get("AITESTER_DATASET_STRICT_INSTANCE_CODE")
            return []

        monkeypatch.setattr(dl, "load_dataset", fake_load)
        assert runner.dataset_signature("quixbugs") is None
        assert seen["caliber"] == "true", "数任务时没开严格口径 ⇒ 投影按 225 个不可判定任务算钱"
        assert os.environ.get("AITESTER_DATASET_STRICT_INSTANCE_CODE") is None, "用完必须还原宿主口径"

    def test_smoke_profile_drops_a_face_with_no_admissible_tasks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """每格 1 任务的冒烟档也不能留这种面：1 次付费调用换一个 `harness_invalid`。"""
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs", "swebench"])
        monkeypatch.setattr(runner, "dataset_signature", lambda name: (50, "a", "b") if name == "quixbugs" else None)
        monkeypatch.setattr(runner, "dataset_task_count", lambda name: 50 if name == "quixbugs" else None)
        args = _args(tmp_path, ["--llm-datasets", "quixbugs,swebench", "--llm-arms", "aitester"])
        scale = runner.llm_scale_plan(args, runner.SMOKE_TASKS_PER_CELL)
        assert scale["datasets"] == ["quixbugs"], "无可跑任务的面必须被剔除并披露，而不是铺一格付费阶段"
        assert scale["face_counts"] == {"quixbugs": 1}

    def test_llm_stage_env_forbids_source_less_tasks(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """阶段 env 必须带严格口径：计数与执行同一规则，否则数到的分母跑不到。"""
        monkeypatch.delenv("LLM_THINKING_MODE", raising=False)
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quixbugs"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _n: 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda _n: (50, "quixbugs__bitcount", "quixbugs__wrap"))
        args = _args(tmp_path, ["--skip-dataset-gate", "--llm-arms", runner.DEFAULT_LLM_ARMS])
        stages = runner.build_full_stages(args, 1, Path(args.out), tasks_per_cell=1)
        sweep = [s for s in stages if "__" in s["name"]]
        assert sweep, "阶段清单为空 ⇒ 本锁在判空气"
        for stage in sweep:
            assert stage["env"]["AITESTER_DATASET_STRICT_INSTANCE_CODE"] == "true", stage["name"]


class TestFacesRunToTheirMaximum:
    """两档都覆盖全部面，差别只在每面 1 项 vs 跑满——面清单与上限都必须现取，不写死。"""

    def test_registry_faces_exclude_the_toy_faces(self) -> None:
        faces = runner.registered_dataset_faces()
        assert faces, "注册表面清单为空 ⇒ 满量档没有面可跑"
        assert "quixbugs" in faces
        for toy in runner.TOY_DATASET_FACES:
            assert toy not in faces, f"玩具面 {toy} 被当成基准面：3 条假任务会冒充'跑满'"

    def test_unknown_face_is_refused_not_degraded(self) -> None:
        """`load_dataset` 对未知名称静默降级成内置示例面；运行器必须先拒。"""
        with pytest.raises(ValueError, match="不在加载器注册表"):
            runner.resolve_dataset_faces("swebench_lite")

    def test_all_expands_and_explicit_list_is_order_stable(self) -> None:
        assert runner.resolve_dataset_faces("all") == runner.registered_dataset_faces()
        assert runner.resolve_dataset_faces("ult, quixbugs,ult") == ["ult", "quixbugs"]

    def test_duplicate_faces_are_dropped_and_priced_once(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """同一批数据被两个名字指向时只铺一遍（双倍付费 + 假独立面）。"""
        args = _args(tmp_path, ["--llm-datasets", "quixbugs,quix_bugs,ult"])
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["quix_bugs", "quixbugs", "ult"])
        counts = {"quix_bugs": 50, "quixbugs": 50, "ult": 200}
        sigs = {
            "quix_bugs": (50, "quixbugs__bitcount", "quixbugs__wrap"),
            "quixbugs": (50, "quixbugs__bitcount", "quixbugs__wrap"),
            "ult": (200, "ult__a", "ult__z"),
        }
        monkeypatch.setattr(runner, "dataset_task_count", lambda name: counts[name])
        monkeypatch.setattr(runner, "dataset_signature", lambda name: sigs[name])
        scale = runner.llm_scale_plan(args, None)
        assert scale["datasets"] == ["quixbugs", "ult"], "保留的应是更短的惯用名 + 独立面"
        assert scale["plan"]["tasks_total"] == 1 * 5 * (50 + 200)

    def test_unreadable_face_is_dropped_with_disclosure(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """数据未下载的面剔除并点名，不让它把整段 LLM 拖成"无法投影"。"""
        args = _args(tmp_path, ["--llm-datasets", "d4j_py,quixbugs"])
        monkeypatch.setattr(runner, "load_price_and_models", lambda: (["m1"], {"m1": 8.0}, "CNY"))
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _r: ["d4j_py", "quixbugs"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda name: None if name == "d4j_py" else 50)
        monkeypatch.setattr(runner, "dataset_signature", lambda name: (50, "a", "b") if name == "quixbugs" else None)
        scale = runner.llm_scale_plan(args, None)
        assert scale["datasets"] == ["quixbugs"]
        assert scale["plan"]["provable"] is True


class TestUnattendedLayer:
    def test_gate_targets_come_from_the_makefile_without_test(self) -> None:
        targets = runner.read_gate_targets()
        assert len(targets) > 10, f"门禁面只有 {len(targets)} 道 ⇒ 解析或 Makefile 变了"
        assert "test" not in targets, "冒烟档不得整跑全量套件（那是全量档的面）"
        assert "json-strict" in targets and "dependency-audit" in targets

    def test_progress_file_tracks_stages_and_eta(self, tmp_path: Path) -> None:
        path = tmp_path / runner.PROGRESS_FILE
        writer = runner.ProgressWriter(path, stages_total=4)
        writer.begin_stage(2, "pytest_smoke_1")
        state = runner.ProgressState(total=400, done=100, last_line="x")
        writer.tick(state, 20.0)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["stage"] == "pytest_smoke_1"
        assert payload["stage_eta_s"] == 60.0  # 20s/100 项 ⇒ 剩 300 项约 60s
        assert payload["overall_percent"] == pytest.approx(31.25)  # (index-1+frac)/total = (2-1+0.25)/4
        writer.finish(0, 4, 0)
        done = json.loads(path.read_text(encoding="utf-8"))["finished"]
        assert done == {**done, "rc": 0, "ok_stages": 4, "failed_stages": 0}

    def test_progress_percent_does_not_inflate_unknown_stages(self, tmp_path: Path) -> None:
        """读不到 done/total 的阶段按 0 计——用输出行数抬高总进度是假读数。"""
        path = tmp_path / runner.PROGRESS_FILE
        writer = runner.ProgressWriter(path, stages_total=2)
        writer.begin_stage(2, "opaque")
        writer.tick(runner.ProgressState(output_lines=999), 5.0)
        assert json.loads(path.read_text(encoding="utf-8"))["overall_percent"] == 50.0

    def test_live_lock_blocks_a_concurrent_run(self, tmp_path: Path) -> None:
        out = tmp_path / "run"
        out.mkdir()
        runner.acquire_run_lock(out, "abcd" * 4, force=False)  # 自己就是活 pid
        with pytest.raises(runner.RunLockError, match="仍活着"):
            runner.acquire_run_lock(out, "abcd" * 4, force=False)
        # 显式旗标下可以强行再开（并发风险由调用方承担）
        runner.acquire_run_lock(out, "abcd" * 4, force=True)

    def test_dead_pid_lock_does_not_block(self, tmp_path: Path) -> None:
        """陈旧锁（pid 已死）不该永久拦死后续运行——那会变成"没人能再跑"的新故障。"""
        out = tmp_path / "run"
        out.mkdir()
        stale = out / runner.LOCK_FILE
        stale.write_text(json.dumps({"pid": 999_999_999}), encoding="utf-8")
        path = runner.acquire_run_lock(out, "ffff" * 4, force=False)
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["pid"] == os.getpid(), f"陈旧锁未被接管，实得 {payload}"
        assert payload["fingerprint"] == "ffff" * 4

    def test_wall_clock_deadline_stops_opening_new_stages(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        args = _args(tmp_path, ["--no-llm"])
        marker = tmp_path / "ran"
        stages = [
            {
                "name": "would_run",
                "command": [sys.executable, "-c", f"pathlib.Path({str(marker)!r}).write_text('x')"],
                "env": dict(os.environ),
                "timeout": 60,
                "retries": 0,
            }
        ]
        results, _stalls = runner._execute_stages(stages, tmp_path, args, None, 0, deadline=time.time() - 1)
        assert not marker.exists(), "总时限到点后仍开了新阶段"
        assert results[0].name == "aborted_wall_clock" and results[0].exit_code == 1

    def test_stall_budget_stops_the_run(self, tmp_path: Path) -> None:
        """卡死预算耗尽后不再开新阶段（无人值守不能无限重跑）。"""
        args = _args(tmp_path, ["--no-llm", "--stall-after", "1", "--tick", "0.2"])
        stages = [
            {
                "name": f"stall_{i}",
                "command": [sys.executable, "-c", "import time; time.sleep(30)"],
                "env": dict(os.environ),
                "timeout": 0,
                "retries": 0,
            }
            for i in range(3)
        ]
        results, stalls = runner._execute_stages(stages, tmp_path, args, None, 0, None, stall_budget=0)
        assert stalls >= 1
        assert any(r.name == "aborted_stall_budget" for r in results), [r.name for r in results]


class TestFullRequiresSmoke:
    def test_full_refuses_without_evidence(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        rc = runner.main(["--spec", "full", "--out", str(tmp_path / "run"), "--no-llm", "--skip-gates"])
        printed = capsys.readouterr().out
        assert rc == 1
        assert "未开跑" in printed
        assert not (tmp_path / "run" / "REPORT.json").exists(), "拒跑时不得留下运行报告"

    def test_stale_smoke_flag_still_cannot_fake_a_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """显式旗标绕过前置后，空阶段清单仍必须判红并说明原因。"""
        rc = runner.main(
            ["--spec", "full", "--out", str(tmp_path / "run"), "--no-llm", "--skip-gates", "--allow-stale-smoke"]
        )
        printed = capsys.readouterr().out
        assert rc == 1
        assert "阶段清单为空" in printed, "无阶段可跑却没有任何说明 ⇒ '没验证'会被读成'验证过'"

    def test_both_stops_when_smoke_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """冒烟未全通 ⇒ 全量阶段一个都不**执行**（花钱的面保持零调用）。

        阶段可以先装配——进度面板要一次性知道总阶段数——所以判据管的是执行顺序，
        不是构造顺序。本例用 run_stage 间谍记录真正跑过哪些阶段名。
        """
        monkeypatch.setattr(runner, "collect_smoke_batches", lambda *_a, **_k: [])
        monkeypatch.setattr(
            runner,
            "build_full_stages",
            lambda *_a, **_k: [
                {
                    "name": "must_not_run",
                    "command": [sys.executable, "-c", "raise SystemExit('全量档被误开跑')"],
                    "env": dict(os.environ),
                    "timeout": 60,
                    "retries": 0,
                }
            ],
        )
        monkeypatch.setattr(
            runner,
            "build_smoke_stages",
            lambda args, jobs, out_dir, batches: [
                {
                    "name": "will_fail",
                    "command": [sys.executable, "-c", "raise SystemExit(3)"],
                    "env": dict(os.environ),
                    "timeout": 60,
                    "retries": 0,
                }
            ],
        )
        executed: list[str] = []
        real_run_stage = runner.run_stage

        def _spy(**kwargs):
            executed.append(str(kwargs["name"]))
            return real_run_stage(**kwargs)

        monkeypatch.setattr(runner, "run_stage", _spy)
        rc = runner.main(["--spec", "both", "--out", str(tmp_path / "run"), "--no-llm", "--skip-gates"])
        printed = capsys.readouterr().out
        assert rc == 1
        # 执行记录才是判据：全量阶段可以已被装配，但一条都不许被跑起来
        assert executed == ["will_fail"], f"冒烟未全通时执行了：{executed}"
        assert "全量档一个阶段都不启动" in printed


class TestStallAndTimeoutDetection:
    def test_silence_triggers_kill_instead_of_waiting(self, tmp_path: Path) -> None:
        """旧实现在这里只能等子进程自己吐字；现在静默阈值到点即终止。"""
        out = tmp_path / "logs"
        out.mkdir()
        t0 = time.time()
        result = runner.run_stage(
            name="silent",
            command=[sys.executable, "-c", "import time; time.sleep(30)"],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=0,
            stage_timeout_s=0,
            stall_after_s=1.0,
            tick_s=0.2,
        )
        waited = time.time() - t0
        assert result.stalled is True
        assert result.exit_code != 0
        assert waited < 12, f"静默 1s 就该击杀，实际等了 {waited:.1f}s（说明检测没在跑）"

    def test_grandchild_dies_with_the_group(self, tmp_path: Path) -> None:
        """只杀直接子进程会留下孙进程继续写盘——本仓的孤儿判定进程就是这么攒起来的。"""
        if sys.platform == "win32":
            pytest.skip("进程组语义（killpg）在 Windows 不成立，本锁只判 POSIX")
        out = tmp_path / "logs"
        out.mkdir()
        gp_pid = tmp_path / "gp.pid"
        script = (
            "import pathlib, subprocess, sys, time;"
            f"p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
            f"pathlib.Path({str(gp_pid)!r}).write_text(str(p.pid));"
            "time.sleep(120)"
        )
        result = runner.run_stage(
            name="with_child",
            command=[sys.executable, "-c", script],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=0,
            stall_after_s=1.0,
            tick_s=0.2,
        )
        assert result.stalled is True
        deadline = time.time() + 5
        while gp_pid.stat().st_size == 0 and time.time() < deadline:
            time.sleep(0.1)
        pid = int(gp_pid.read_text(encoding="utf-8"))
        time.sleep(0.5)
        orphan_alive = True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            orphan_alive = False
        assert not orphan_alive, f"孙进程 {pid} 在阶段被杀后仍存活（进程组没杀干净）"

    def test_wall_clock_timeout_fires(self, tmp_path: Path) -> None:
        out = tmp_path / "logs"
        out.mkdir()
        result = runner.run_stage(
            name="slow",
            command=[sys.executable, "-c", "import time; print('hi', flush=True); time.sleep(20)"],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=0,
            stage_timeout_s=2,
            stall_after_s=600,
            tick_s=0.2,
        )
        assert result.timed_out is True
        assert result.exit_code != 0

    def test_retry_after_stall_then_pass(self, tmp_path: Path) -> None:
        """卡死按一次失败计，仍走重跑通道。"""
        out = tmp_path / "logs"
        out.mkdir()
        script = "import time;"
        first = runner.run_stage(
            name="stalled_once",
            command=[sys.executable, "-c", script + "time.sleep(30)"],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=0,
            stall_after_s=0.5,
            tick_s=0.2,
        )
        assert first.attempts == 1 and first.stalled is True
        second = runner.run_stage(
            name="retried",
            command=[sys.executable, "-c", script + "time.sleep(30)"],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=1,
            stall_after_s=0.5,
            tick_s=0.2,
        )
        assert second.attempts == 2, "卡死后未进入第 2 次尝试"


class TestProgressReading:
    def test_pytest_totals_and_done_are_read(self, tmp_path: Path) -> None:
        out = tmp_path / "logs"
        out.mkdir()
        result = runner.run_stage(
            name="progress_probe",
            command=[
                sys.executable,
                "-m",
                "pytest",
                "tests/test_env_utils.py",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=0,
            heartbeat_s=0.0,
            tick_s=0.2,
        )
        assert result.exit_code == 0, result.progress
        assert result.progress["total"] > 0, "未从输出里读到 collected 数 ⇒ 进度只能靠猜"
        assert result.progress["done"] > 0, "未统计到任何结果行"
        assert result.progress["output_lines"] > 0

    def test_incremental_file_is_the_authoritative_counter(self, tmp_path: Path) -> None:
        """LLM 段的完成数取自增量落盘行数，而不是输出行数（后者受日志噪声支配）。"""
        out = tmp_path / "logs"
        out.mkdir()
        incremental = tmp_path / "INCREMENTAL_RESULTS.jsonl"
        child = tmp_path / "emit.py"
        child.write_text(
            "import sys, time\n"
            "path = sys.argv[1]\n"
            "with open(path, 'a', encoding='utf-8') as fh:\n"
            "    for i in range(2):\n"
            "        fh.write('{\"task\": %d}\\n' % i)\n"
            "        fh.flush()\n"
            "        print('task %d done' % i, flush=True)\n"
            "        time.sleep(0.2)\n",
            encoding="utf-8",
        )
        result = runner.run_stage(
            name="incremental_probe",
            command=[sys.executable, str(child), str(incremental)],
            env=dict(os.environ),
            cwd=REPO_ROOT,
            log_dir=out,
            retries=0,
            incremental_path=incremental,
            tick_s=0.2,
        )
        assert result.exit_code == 0
        assert result.progress["done"] == 2, result.progress
        # 输出行有 2 行，但 done 只认落盘行——混用会把进度读成别的东西
        assert result.progress["output_lines"] >= 2

    def test_count_incremental_lines_skips_blank_and_missing(self, tmp_path: Path) -> None:
        assert runner._count_incremental_lines(None) == 0
        assert runner._count_incremental_lines(tmp_path / "missing.jsonl") == 0
        path = tmp_path / "rows.jsonl"
        path.write_text('{"a": 1}\n\n   \n{"a": 2}\n', encoding="utf-8")
        assert runner._count_incremental_lines(path) == 2

    def test_render_shapes(self) -> None:
        assert "50.0%" in runner.ProgressState(total=4, done=2).render()
        assert "行输出" in runner.ProgressState(output_lines=7).render()


class TestRetryNarrowsToFailingNodeIds:
    """重跑必须真的重跑失败用例——`--lf` 做不到，因为它读仓库根的共享缓存。

    现场（2026-11-04 最小批）：第 1 轮红 2 条，第 2 轮 `--lf` 打出
    `7 workers [0 items]`、exit=5。`lastfailed` 存在仓库根 `.pytest_cache` 里，任何
    穿插的 pytest 运行都会改写它，于是"重跑"变成"什么都没跑"——四轮耗光后给出一个与
    套件无关的红。改判据为"跟着本轮日志的短摘要走"。
    """

    def test_failed_node_ids_reads_bare_quoted_and_error_lines(self, tmp_path: Path) -> None:
        log = tmp_path / "attempt1.log"
        log.write_text(
            "collected 3 items\n"
            "FAILED tests/test_a.py::test_one - assert 0 >= 2\n"
            "FAILED 'tests/test_b.py::TestC::test_two[x y-z]' - Failed: ...\n"
            "ERROR tests/test_d.py - FileNotFoundError: no such file\n"
            "FAILED tests/test_a.py::test_one - duplicate line\n",
            encoding="utf-8",
        )
        assert runner.failed_node_ids(log) == [
            "tests/test_a.py::test_one",
            "tests/test_b.py::TestC::test_two[x y-z]",
            "tests/test_d.py",
        ]

    def test_failed_node_ids_ignores_prose_and_missing_log(self, tmp_path: Path) -> None:
        """散文里的 FAILED/ERROR 不算用例；日志不存在不得抛。"""
        log = tmp_path / "noise.log"
        log.write_text(
            "FAILED to initialize plugin\n"
            "ERROR: not found: /tmp/x/test_y.py::test_z\n"
            "Some body line mentioning FAILED tests/test_real.py\n",
            encoding="utf-8",
        )
        assert runner.failed_node_ids(log) == []
        assert runner.failed_node_ids(tmp_path / "absent.log") == []

    def test_narrow_command_to_replaces_only_the_node_ids(self) -> None:
        command = [
            "/venv/bin/python",
            "-m",
            "pytest",
            "tests/test_a.py::test_one",
            "tests/test_b.py::test_two",
            "-n",
            "7",
            "--timeout=3600",
        ]
        assert runner.narrow_command_to(command, ["tests/test_b.py::test_two"]) == [
            "/venv/bin/python",
            "-m",
            "pytest",
            "tests/test_b.py::test_two",
            "-n",
            "7",
            "--timeout=3600",
        ]

    def test_narrow_command_to_returns_none_for_non_pytest_stages(self) -> None:
        assert runner.narrow_command_to(["make", "gates"], ["tests/test_a.py::test_one"]) is None

    def test_second_attempt_runs_only_the_failing_case(self, tmp_path: Path) -> None:
        out = tmp_path / "logs"
        out.mkdir()
        (tmp_path / "test_narrow_probe.py").write_text(
            "def test_alpha():\n    assert True\n\n\ndef test_beta():\n    assert False\n", encoding="utf-8"
        )
        env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
        result = runner.run_stage(
            name="narrow",
            command=[
                sys.executable,
                "-m",
                "pytest",
                "test_narrow_probe.py::test_alpha",
                "test_narrow_probe.py::test_beta",
                "-p",
                "no:cacheprovider",
                "--tb=no",
                "-rf",
            ],
            env=env,
            cwd=tmp_path,
            log_dir=out,
            retries=1,
            heartbeat_s=3600,
            tick_s=0.2,
        )
        first = (out / "narrow.attempt1.log").read_text(encoding="utf-8")
        second = (out / "narrow.attempt2.log").read_text(encoding="utf-8")
        assert "collected 2 items" in first, first
        assert "1 failed" in first and "1 passed" in first, first
        assert "1 item" in second and "2 items" not in second, second
        assert "test_alpha" not in second, "第 2 轮把已通过的用例又跑了一遍 ⇒ 没收窄"
        assert "test_beta" in second, "第 2 轮没跑失败用例 ⇒ 收窄后清单为空"
        assert result.attempts == 2
        assert any("只跑上一轮失败的 1 个用例" in note for note in result.notes), result.notes

    def test_unparsable_failure_falls_back_to_full_rerun(self, tmp_path: Path) -> None:
        """崩溃/用法错误没有 FAILED 行 ⇒ 只能整条重跑，不能收窄成空清单。"""
        out = tmp_path / "logs"
        out.mkdir()
        (tmp_path / "test_probe.py").write_text("def test_alpha():\n    assert True\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "PYTEST_ADDOPTS"}
        result = runner.run_stage(
            name="bogus",
            command=[sys.executable, "-m", "pytest", "test_probe.py::test_absent", "-p", "no:cacheprovider", "--tb=no"],
            env=env,
            cwd=tmp_path,
            log_dir=out,
            retries=1,
            heartbeat_s=3600,
            tick_s=0.2,
        )
        assert result.exit_code != 0
        assert result.attempts == 2
        assert any("整条重跑" in note for note in result.notes), result.notes

    def test_runner_source_no_longer_appends_lf(self) -> None:
        """防止有人把 `--lf` 加回来：源码里不得再出现该旗标形式（说明性提及除外）。"""
        # 仓库根取自本文件位置，不用 `sys.path[0]`：xdist 各 worker 的首个 sys.path
        # 条目随导入顺序漂移（实测 2026-11-04 认证跑读到 scripts/gates 下），
        # 拿它当仓库根会让本锁按运行顺序时红时绿。
        text = (REPO_ROOT / "scripts" / "run_all_tests.py").read_text(encoding="utf-8")
        assert '"--lf"' not in text
        assert "narrow_command_to" in text
