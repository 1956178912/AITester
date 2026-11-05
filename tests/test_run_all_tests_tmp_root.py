"""GL 轮（2026-11-04）：全量运行器的临时根隔离。

现场不是理论风险：作者机 TMPDIR 根堆积 196 万条目（1,790,158 个 `b3gen_*` +
169,378 个 `c8gen_*`，来自 `scripts/tools/judge_swebench_generated_tests.py`
与 `judge_c8_generated_tests.py` 每次判定一个 `mkdtemp` 且从不回收），执行器把
测试文件写在临时根**下**、内层 pytest 因此把临时根挂进 `sys.path`，一个单行
用例的内层运行由 0.6s 变成 257s —— 跨过 `EXECUTION_TIMEOUT` 就被判超时，
"运行一次跑完所有测试"因此在作者机必红。本文件锁住运行器侧的隔离口径：每次运行独占、跑完即删、且必须在仓库**之外**。
第二条现场（同一批）：根建在报告目录（`experiments/results/test_run_*/tmp`，位于工作
树内）时，`test_check_doc_commands.py::test_existing_refs_pass` 与
`test_ew_config_reader_census.py` 的读取器普查例稳定变红（`assert 0 >= 2` /
`assert 空字典 == 非空`），而同一份 400 项 nodeid 清单在仓库外的根下全绿——红的是这
些用例按临时目录解析「当前仓库」，与被测代码无关。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from scripts import run_all_tests as runner

_TMP_KEYS = ("TMPDIR", "TEMP", "TMP")
_REPO_ROOT = Path(__file__).resolve().parents[1]


def _args(tmp_path: Path, extra: list[str]) -> object:
    return runner.build_parser().parse_args(["--out", str(tmp_path / "out"), *extra])


@pytest.fixture(autouse=True)
def _run_roots_land_in_pytemp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """运行临时根落到 pytest 自己的 tmp_path：断言完由 pytest 回收，不在系统临时区留目录。"""
    monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(tmp_path))


class TestStageBaseEnvTmpRoot:
    def test_all_three_variables_point_at_the_run_root(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "out"
        env = runner.stage_base_env(out_dir)
        expected = str(runner.run_tmp_root(out_dir))
        for key in _TMP_KEYS:
            assert env[key] == expected, key

    def test_run_root_is_created(self, tmp_path: Path) -> None:
        out_dir = tmp_path / "out"
        root = runner.run_tmp_root(out_dir)
        assert not root.exists()
        runner.stage_base_env(out_dir)
        assert root.is_dir()

    def test_run_root_is_derivable_and_per_run(self, tmp_path: Path) -> None:
        """同一次运行两次调用同根（阶段共享），不同报告目录不同根（运行之间互不串）。"""
        out_dir = tmp_path / "out"
        assert runner.run_tmp_root(out_dir) == runner.run_tmp_root(out_dir)
        assert runner.run_tmp_root(tmp_path / "out2") != runner.run_tmp_root(out_dir)

    def test_inherits_retries_and_http_timeout(self, tmp_path: Path) -> None:
        """隔离临时根不得顺手改掉上一轮登记的重试/超时口径。"""
        env = runner.stage_base_env(tmp_path / "out")
        assert env["LLM_MAX_RETRIES"] == "6"
        assert env["LLM_HTTP_TIMEOUT"] == "600"

    def test_does_not_mutate_the_parent_environment(self, tmp_path: Path) -> None:
        before = {key: os.environ.get(key) for key in _TMP_KEYS}
        runner.stage_base_env(tmp_path / "out")
        assert {key: os.environ.get(key) for key in _TMP_KEYS} == before


class TestRunRootStaysOutsideTheRepo:
    """临时根嵌进工作树会让夹具把报告目录当成仓库——本类锁住这条边界。"""

    def test_real_report_dir_root_is_outside_the_worktree(self) -> None:
        out_dir = runner.PROJECT_ROOT / "experiments" / "results" / "test_run_20261104T000000Z"
        assert runner._inside_repo(out_dir), "前提：报告目录本身在仓库内"
        root = runner.run_tmp_root(out_dir)
        assert not runner._inside_repo(root), f"临时根落进工作树：{root}"

    def test_repo_temp_dir_is_pushed_outside(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """外部把 TMPDIR 指到仓库内时不得照用：POSIX 退到系统级目录，其余环境明确报错。"""
        inside = runner.PROJECT_ROOT / "experiments" / "results" / "tmpdir_probe"
        monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(inside))
        if os.name == "posix":
            root = runner.run_tmp_root(tmp_path / "out")
            assert not runner._inside_repo(root), f"退回路径仍在仓库内：{root}"
            assert root.parent == Path("/tmp")
        else:
            with pytest.raises(RuntimeError, match="临时根"):
                runner.run_tmp_root(tmp_path / "out")

    def test_stage_base_env_shares_the_same_boundary(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """环境装配面必须走同一个算式，否则阶段 env 能绕过边界检查。"""
        inside = runner.PROJECT_ROOT / "experiments" / "results" / "tmpdir_probe"
        monkeypatch.setattr(runner.tempfile, "gettempdir", lambda: str(inside))
        if os.name == "posix":
            env = runner.stage_base_env(tmp_path / "out")
            assert not runner._inside_repo(Path(env["TMPDIR"])), env["TMPDIR"]
        else:
            with pytest.raises(RuntimeError):
                runner.stage_base_env(tmp_path / "out")


class TestStagesCarryTheIsolation:
    def test_every_full_stage_env_shares_the_run_root(self, tmp_path: Path) -> None:
        args = _args(tmp_path, ["--no-llm"])
        out_dir = Path(args.out)
        stages = runner.build_full_stages(args, 1, out_dir, tasks_per_cell=None)
        assert stages, "阶段列表为空 ⇒ 本锁在判空气"
        expected = str(runner.run_tmp_root(out_dir))
        for stage in stages:
            for key in _TMP_KEYS:
                assert stage["env"][key] == expected, f"{stage['name']} 的 {key} 逃出本运行临时根"

    def test_every_smoke_stage_env_shares_the_run_root(self, tmp_path: Path) -> None:
        args = _args(tmp_path, ["--no-llm"])
        out_dir = Path(args.out)
        stages = runner.build_smoke_stages(args, 1, out_dir, [["tests/test_env_utils.py::test_a"]])
        assert stages, "冒烟档阶段列表为空 ⇒ 本锁在判空气"
        expected = str(runner.run_tmp_root(out_dir))
        for stage in stages:
            for key in _TMP_KEYS:
                assert stage["env"][key] == expected, f"{stage['name']} 的 {key} 逃出本运行临时根"

    def test_no_stage_env_keeps_a_repo_inside_tmp(self, tmp_path: Path) -> None:
        """两档全部阶段的全部临时变量：一个都不允许指向工作树。"""
        args = _args(tmp_path, ["--no-llm"])
        out_dir = Path(args.out)
        stages = runner.build_full_stages(args, 1, out_dir, tasks_per_cell=None)
        stages += runner.build_smoke_stages(args, 1, out_dir, [["tests/test_env_utils.py::test_a"]])
        assert stages, "阶段清单为空 ⇒ 本锁在判空气"
        for stage in stages:
            for key in _TMP_KEYS:
                value = stage["env"].get(key)
                if value is not None:
                    assert not runner._inside_repo(Path(value)), f"{stage['name']}.{key} -> {value}"

    def test_llm_stages_are_also_isolated(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM 段（含数据集闸/缓存阶段）与 0 LLM 段同根，判定不依赖机器历史。

        模型与单价用注入的合成面：否则本例读的是作者机 `.env.local` 里配了几个
        端点——CI 上没有那两个端点时阶段清单为空，断言就变成"看机器配置决定判不判"。
        """
        monkeypatch.setattr(
            runner, "load_price_and_models", lambda: (["synthetic-model"], {"synthetic-model": 8.0}, "CNY")
        )
        # 面清单也注入：否则本例读本机数据集可用性，CI 上就变成"看机器配置决定判不判"
        monkeypatch.setattr(runner, "resolve_dataset_faces", lambda _requested: ["synthface"])
        monkeypatch.setattr(runner, "dataset_task_count", lambda _name: 1)
        monkeypatch.setattr(runner, "dataset_signature", lambda _name: (1, "t0", "t0"))
        args = _args(tmp_path, ["--skip-dataset-gate", "--llm-arms", "aitester,plain_llm"])
        out_dir = Path(args.out)
        stages = runner.build_full_stages(args, 1, out_dir, tasks_per_cell=1)
        sweep = [s for s in stages if "__" in s["name"]]  # llm_<model>__<arm>__<dataset>
        assert len(sweep) == 2, f"应按「模型 × 臂」铺出 2 个贯通阶段，实得 {[s['name'] for s in sweep]}"
        assert any(s["name"] == "llm_smoke" for s in stages), "端点契约冒烟阶段缺席"
        expected = str(runner.run_tmp_root(out_dir))
        for stage in sweep:
            assert stage["env"]["TMPDIR"] == expected, stage["name"]
            assert stage["incremental"], f"{stage['name']} 缺增量读数来源，进度只能靠猜"


class TestProducerLeavesAreNamed:
    """泄漏生产端点名（防"只修消费端"）：两个判定脚本仍是每判定一个临时目录。

    这两处由跑批侧的临时根隔离兜住（本运行器），脚本自身的回收另批处理；
    若有人给它们补上 `finally` 回收，本例的期望值需要同步改掉——那是好消息，
    不是回归。
    """

    @pytest.mark.parametrize(
        "script, prefix",
        [
            ("scripts/tools/judge_swebench_generated_tests.py", "b3gen_"),
            ("scripts/tools/judge_c8_generated_tests.py", "c8gen_"),
        ],
    )
    def test_mkdtemp_without_cleanup_is_still_the_current_state(self, script: str, prefix: str) -> None:
        # 仓库根取自本文件位置：`sys.path[0]` 在 xdist 各 worker 里随导入顺序漂移
        # （2026-11-04 认证跑实测读到 `scripts/gates/` 下，本锁因此时红时绿）。
        text = (_REPO_ROOT / script).read_text(encoding="utf-8")
        assert f'prefix="{prefix}"' in text, script
        assert "rmtree" not in text, f"{script} 已自行回收，请同步本锁与 CHANGELOG 口径"
