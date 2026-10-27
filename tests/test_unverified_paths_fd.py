"""FD 轮（2026-10-27）：把「修复新增但从未被测试执行」的路径补成**进程内**真锁。

## 发现路径（可复跑）

用项目自带的 `scripts/tools/audit_fix_coverage.py` 复算，基线取 `v0.8.0`
（即整个 1.0.0 轮次区间），得到「新增行中本进程从未执行」的清单。
其中**真缺口**（任何测试、任何进程都没执行过）有四条，本文件逐条补锁：

| # | 位置 | 为什么从未执行 |
|---|---|---|
| 1 | `src/cli/app.py::_run_single_task` 的 `raise AssertionError("graph.invoke 未返回状态（非预期）")` | FC 轮把它从 `assert` 改成显式 raise，既有测试只跑正常路径 ⇒ **失败分支一行未执行** |
| 2 | `src/db/mysql_client.py::cursor` 的同名守卫 | FC 轮只在**子进程**（`python -O`）里验证过，父进程 coverage 看不见 |
| 3 | `src/observability/trace.py` 的**名字耗尽**分支（第 100 个候选名仍被占用 → OSError） | DX 轮承诺「O_EXCL + 序号重试、绝不覆盖旧快照」，但既有用例只撞名 1～2 次，从未跑到耗尽点 |
| 4 | `src/observability/trace.py` 调用方的**半成品清理**（写盘中途失败 → 删除本次留下的文件） | DX 轮的用例把故障注入在 `os.fdopen`（更早），那时文件由 `_open_unique_dump_file` 自己删 ⇒ 调用方这条分支从未执行 |

另有 `src/utils/trace_viz.py::_node_token_total` 的「非 int → None」分支同属此类。

## 为什么值得单独一轮

守卫的**失败分支与成功分支同等重要**：只在成功路径上验证过的守卫，等于
「写在那里但没人知道它会不会真的拦住」。本文件把上述四条改成**进程内真跑**，
使覆盖率读数与实际验证面一致（`audit_fix_coverage.py --base` 复算归零）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.cli import app as cli_app
from src.observability import trace as trace_module
from src.observability.trace import (
    _DUMP_NAME_ATTEMPTS,
    _open_unique_dump_file,
    dump_recent_to_with_reason,
    memory_buffer_snapshot,
    reset_memory_buffer,
)
from src.utils.trace_viz import _node_token_total

TS = 1700000000


@pytest.fixture(autouse=True)
def _isolated_buffer():
    reset_memory_buffer()
    assert trace_module._memory_buffer_enabled(), "本组锁要求内存缓冲启用（默认 true）"
    yield
    reset_memory_buffer()


class _GraphReturningNone:
    """工作流桩：`invoke` 返回 None（模拟图内部状态异常）。"""

    def invoke(self, _state):
        return None


class _GraphRaisingNone:
    """工作流桩：`invoke` 抛异常（对照：守卫只在「返回 None」时触发）。"""

    def invoke(self, _state):
        raise RuntimeError("图内部崩溃（对照分支）")


class TestCliInvokeNoneGuard:
    """`src/cli/app.py::_run_single_task` 的守卫失败分支（此前一行未执行）。"""

    def test_invoke_returning_none_raises_exact_assertion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """invoke 返回 None ⇒ 必须点名拒绝（消息与改前逐字一致）。"""
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(cli_app, "build_workflow", lambda: _GraphReturningNone())

        with pytest.raises(AssertionError) as excinfo:
            cli_app._run_single_task(
                target_file=str(target),
                func=None,
                max_iterations=1,
                timeout=30,
                coverage_threshold=80.0,
                output_json=True,
            )
        assert "graph.invoke 未返回状态" in str(excinfo.value)

    def test_guard_exception_is_absorbed_by_task_level_tolerance(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """守卫抛出的异常必须被**逐任务容错**接住：任务出现在结果流里，整批不中断。

        契约（`_append_task_error` 的 docstring）：异常任务也必须在结果流里出现，
        JSON 模式逐任务一行 JSON；否则调度层无法区分「没跑」和「崩了」。
        """
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(cli_app, "build_workflow", lambda: _GraphReturningNone())

        runner = CliRunner()
        result = runner.invoke(
            cli_app.cli,
            ["run", str(target), "--json", "--max-iterations", "1"],
        )
        assert result.exit_code != 0, "有任务失败时 run 不得返回 0"
        payload = result.output
        assert "mod.py" in payload, "失败任务必须出现在结果流里（不得静默消失）"
        assert "graph.invoke 未返回状态" in payload, "失败原因必须点名，不得只写「任务失败」"

    def test_graph_exception_path_is_not_masked_by_the_guard(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """反向对照：invoke **抛异常**时守卫不得误报（异常在上游 finally 已收尾）。"""
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        monkeypatch.setattr(cli_app, "build_workflow", lambda: _GraphRaisingNone())

        with pytest.raises(RuntimeError) as excinfo:
            cli_app._run_single_task(
                target_file=str(target),
                func=None,
                max_iterations=1,
                timeout=30,
                coverage_threshold=80.0,
                output_json=True,
            )
        assert "图内部崩溃" in str(excinfo.value)
        assert "graph.invoke 未返回状态" not in str(excinfo.value)


class TestMysqlCursorGuard:
    """`src/db/mysql_client.py::cursor` 的守卫失败分支（此前只在 `-O` 子进程里验证）。"""

    def test_uninitialised_pool_raises_in_process(self) -> None:
        """未初始化连接池 ⇒ 进程内必须点名拒绝（不是 AttributeError）。"""
        from src.db.mysql_client import MySQLClient

        client = MySQLClient.__new__(MySQLClient)  # 不跑 __init__ ⇒ _pool 保持 None
        with pytest.raises(AssertionError) as excinfo, client.cursor():
            pass
        assert "连接池未初始化" in str(excinfo.value)


class TestTraceDumpFailurePaths:
    """`src/observability/trace.py` 的两条失败路径（DX 轮从未验证到）。"""

    def test_name_exhaustion_is_reported_not_raised(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """同名候选名全部被占用 ⇒ 不得冒泡异常，转为「写盘失败」原因。"""
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])
        monkeypatch.setattr(trace_module.time, "time", lambda: float(TS))
        # 预先占满全部候选名（<ts>_failed_trace.jsonl 与 <ts>_2..<ts>_<N>）
        for attempt in range(1, _DUMP_NAME_ATTEMPTS + 1):
            suffix = "" if attempt == 1 else f"_{attempt}"
            (tmp_path / f"{TS}{suffix}_failed_trace.jsonl").write_text("occupied\n", encoding="utf-8")

        path, reason = dump_recent_to_with_reason(str(tmp_path))

        assert path is None
        assert reason is not None and "写盘失败" in reason
        # 不得覆盖任何既有文件（DX 轮「绝不覆盖旧快照」承诺在耗尽点同样成立）
        for attempt in range(1, _DUMP_NAME_ATTEMPTS + 1):
            suffix = "" if attempt == 1 else f"_{attempt}"
            target = tmp_path / f"{TS}{suffix}_failed_trace.jsonl"
            assert target.read_text(encoding="utf-8") == "occupied\n", f"既有快照被覆盖了：{target.name}"

    def test_exhaustion_raises_inside_the_helper(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """helper 层：耗尽即抛 OSError，且消息点名「连续占用 N 次」。"""
        monkeypatch.setattr(trace_module.time, "time", lambda: float(TS))
        for attempt in range(1, _DUMP_NAME_ATTEMPTS + 1):
            suffix = "" if attempt == 1 else f"_{attempt}"
            (tmp_path / f"{TS}{suffix}_failed_trace.jsonl").write_text("occupied\n", encoding="utf-8")

        with pytest.raises(OSError) as excinfo:
            _open_unique_dump_file(str(tmp_path))
        assert "连续占用" in str(excinfo.value)

    def test_partial_file_is_removed_when_write_fails(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """写盘中途失败 ⇒ 调用方删除本次留下的半成品文件。

        既有 DX 用例把故障注入在 `os.fdopen`（文件由 helper 自己删），调用方的
        清理分支从未执行——本例把故障注入在**写入阶段**（文件已创建、路径已记录）。
        """
        memory_buffer_snapshot("t0", [{"event": "node", "task": "t0"}])

        class _BoomWriter:
            def __init__(self, fd: int) -> None:
                self._fd = fd

            def write(self, _data: str) -> int:
                raise OSError("注入写盘失败")

            def __enter__(self) -> _BoomWriter:
                return self

            def __exit__(self, *_exc: object) -> bool:
                os.close(self._fd)
                return False

        monkeypatch.setattr(trace_module.os, "fdopen", lambda fd, *a, **k: _BoomWriter(fd))

        path, reason = dump_recent_to_with_reason(str(tmp_path))

        assert path is None
        assert reason is not None and "写盘失败" in reason
        assert not list(tmp_path.iterdir()), "写盘失败不得留下空壳 / 半成品文件"


class TestUltUnknownSubsetBranch:
    """`src/datasets/dataset_ult.py` 的「未知子集」分支（CLI 更早以 rc=2 拒绝，故此前未执行）。"""

    def test_unknown_subset_records_reason(self, tmp_path: Path) -> None:
        """未知子集 ⇒ 加载器必须留下可披露的原因（不能静默回退到通用 manifest）。

        注意加载是**惰性**的（`_ensure_loaded`）：`subset_fallback_reason` 只在
        真正加载后写入——CLI 侧先取 `loader.tasks` 再读该字段，顺序正确；
        本例同样先触发加载，否则读到的是「未加载」而非「已回退」。
        """
        from src.datasets.dataset_loader import load_dataset

        ds = load_dataset("ult", subset="definitely-not-a-subset", data_dir=str(tmp_path))
        assert len(ds.tasks) == 0  # 触发惰性加载
        assert ds.subset_fallback_reason is not None
        assert "未知子集" in ds.subset_fallback_reason
        assert "definitely-not-a-subset" in ds.subset_fallback_reason

    def test_cli_rejects_unknown_subset_before_loading(self) -> None:
        """对照：CLI 侧更早以 rc=2 拒绝（用法错误），不等加载器回退。"""
        from src.datasets.dataset_loader import dataset_subset_support

        support = dataset_subset_support("ult")
        assert support.supports is True
        assert support.allowed is not None
        assert "definitely-not-a-subset" not in support.allowed


class TestTraceVizTokenTotal:
    """`src/utils/trace_viz.py::_node_token_total` 的「非 int → None」分支。"""

    def test_int_total_is_returned(self) -> None:
        assert _node_token_total({"total_tokens": 12}) == 12

    @pytest.mark.parametrize("payload", [{"total_tokens": "12"}, {"total_tokens": 1.5}, {"total_tokens": True}])
    def test_non_int_total_is_none(self, payload: dict) -> None:
        """非 int（含 bool——bool 是 int 的子类）⇒ None，不得猜测。"""
        assert _node_token_total(payload) is None

    @pytest.mark.parametrize("payload", [None, {}, {"total_tokens": None}, "not-a-dict"])
    def test_non_dict_payload_is_none(self, payload: object) -> None:
        assert _node_token_total(payload) is None


class TestRemainingUncoveredPaths:
    """FD 轮补齐的另外三处：崩溃任务的诊断导出成功路径 + 通配符元字符路径的 rc=2。"""

    def test_crash_task_dump_success_records_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """崩溃任务同样做诊断导出（DW 轮承诺）——**导出成功**时结果行必须写 trace_dump_path。

        既有用例只断言了导出**失败**的 `trace_dump_error`，成功分支从未执行。
        """
        from src.observability.trace import memory_buffer_snapshot, reset_memory_buffer

        monkeypatch.setenv("TRACE_MEMORY_BUFFER_ENABLE", "true")
        reset_memory_buffer()
        memory_buffer_snapshot("crash_task", [{"event": "node", "node": "planner", "task": "crash_task"}])

        results: list[dict] = []
        cli_app._append_task_error(
            str(tmp_path / "mod.py"),
            None,
            RuntimeError("模拟崩溃"),
            results,
            json_output=False,
            dump_trace_on_failure=True,
        )
        assert len(results) == 1
        assert "trace_dump_path" in results[0], "崩溃任务导出成功时必须写 trace_dump_path"
        assert "trace_dump_error" not in results[0]
        reset_memory_buffer()

    def test_glob_magic_path_pointing_at_directory_is_usage_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """路径含通配符元字符但实际指向目录 ⇒ 按用法错误 rc=2 拒绝（不得当任务跑）。

        与「通配符只匹配到目录」是**不同**分支：此处 glob 不命中任何文件，
        而字面量路径本身存在（且是目录）。
        """
        weird_dir = tmp_path / "weird[1]"
        weird_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(cli_app.cli, ["run", str(weird_dir)])
        assert result.exit_code == 2, f"目录目标必须按用法错误退出，实际 {result.exit_code}"
        assert "不是普通文件" in result.output


class TestDoctorConclusionText:
    """doctor 的两处结论文案分支（此前无任何用例执行）。"""

    @staticmethod
    def _report(**overrides: object) -> dict:
        base: dict = {
            "conclusion": "fail",
            "exit_code": 2,
            "strict": False,
            "checks": [{"label": "环境", "status": "pass", "detail": "ok"}],
            "matrix": {"status": "usage", "detail": "未知分组", "stderr_tail": ""},
        }
        base.update(overrides)
        return base

    def test_usage_conclusion_mentions_checks_ran(self, capsys: pytest.CaptureFixture[str]) -> None:
        """矩阵是**子进程用法错误**且环境检查已跑过 ⇒ 措辞不得谎称「未执行环境检查」。"""
        cli_app._doctor_print_human(self._report())
        out = capsys.readouterr().out
        assert "用法错误（参数未通过校验；功能矩阵未执行，环境检查见上）" in out

    def test_strict_reason_is_disclosed_for_warn(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`--strict` 下 warn/skip 视为不通过 ⇒ 结论行必须点名这条理由。"""
        cli_app._doctor_print_human(
            self._report(
                conclusion="warn",
                exit_code=1,
                strict=True,
                matrix={"status": "skip", "detail": "跳过", "stderr_tail": ""},
            )
        )
        out = capsys.readouterr().out
        assert "--strict 下 warn/skip 视为不通过" in out


class TestRegistrationSurfaceTracksTrackedSurface:
    """登记一致性门的「已格式化」受检面 = **跟踪面**（= CI 干净检出）。"""

    @staticmethod
    def _gate():
        import importlib.util

        script = Path(__file__).resolve().parents[1] / "scripts" / "gates" / "check_registration_consistency.py"
        spec = importlib.util.spec_from_file_location("_check_registration_consistency_fd", script)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules["_check_registration_consistency_fd"] = module
        spec.loader.exec_module(module)
        return module

    def test_untracked_file_does_not_shift_the_surface_count(self) -> None:
        """工作树里多出一份未跟踪 `.py` ⇒ 「已格式化」读数**不得**变化。

        否则本地并行会话的产物会让登记数漂移，而 CI（干净检出）读数不同 ⇒
        登记面与运行面口径分叉（EZ 轮「语料形状锁判作者机盘面」的同型病灶）。
        """
        module = self._gate()
        repo = Path(__file__).resolve().parents[1]
        before, reason = module.ruff_surface(repo)
        assert before is not None, f"ruff 受检面复算不可用：{reason}"
        stray = repo / "zz_fd_untracked_probe.py"
        assert not stray.exists()
        stray.write_text("x = 1\n", encoding="utf-8")
        try:
            after, reason2 = module.ruff_surface(repo)
            assert after is not None, f"ruff 受检面复算不可用：{reason2}"
            assert after["已格式化"] == before["已格式化"], (
                f"未跟踪文件改变了受检面读数：{before['已格式化']} → {after['已格式化']}"
            )
        finally:
            stray.unlink()

    def test_untracked_file_is_discovered_by_the_untracked_helper(self) -> None:
        """未跟踪清单必须真的被算出来（否则上一例会假绿）。"""
        module = self._gate()
        repo = Path(__file__).resolve().parents[1]
        stray = repo / "zz_fd_untracked_probe2.py"
        assert not stray.exists()
        stray.write_text("y = 2\n", encoding="utf-8")
        try:
            untracked = module._untracked_paths(repo)
            assert untracked is not None
            assert "zz_fd_untracked_probe2.py" in untracked
        finally:
            stray.unlink()
