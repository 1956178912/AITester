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

import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from scripts import run_all_tests as runner

REPO_ROOT = Path(__file__).resolve().parent.parent


def _args(tmp_path: Path, extra: list[str]):
    return runner.build_parser().parse_args(["--out", str(tmp_path / "out"), *extra])


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
