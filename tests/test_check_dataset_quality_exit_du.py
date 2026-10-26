"""DU 轮：check-dataset 发现加载问题仍以 0 退出（校验命令无法失败）。

修复前实测（2026-10-26，零 LLM）::

    loader.quality_report() -> {"t1": ["bad patch"]}
    validate_task(task)     -> ["结构不完整"]
    python main.py check-dataset swe_bench --limit 1   → rc=0

而该命令自己的 docstring 写着「退出码：0 至少校验到一个任务且**无问题**」：
发现问题的路径只打 warning，退出码仍是 0，CI/脚本据此判定数据集健康。
口径（与 doctor / clean-venv-cache 的「发现失败即非 0」一致）：

- 质量报告非空 ⇒ rc=1，错误行单独落在报告之后（与「加载异常」同码、可区分文案）；
- 质量报告为空 dict ⇒ rc=0（经校验的通过）；
- 加载器不提供 quality_report ⇒ rc=0 + 显式跳过披露（DL 轮口径，能力缺失不计失败）；
- tasks_missing_source 非空仍为信息性披露（DL/DN 口径），单独不改变退出码。
"""

from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner, Result

from src.cli import app as cli_app
from src.datasets import dataset_loader


def _task(task_id: str = "t1") -> SimpleNamespace:
    return SimpleNamespace(
        task_id=task_id,
        repo_name="repo",
        total_test_count=1,
        expected_pass_count=1,
        problem_statement="问题描述",
        instance_code="def f():\n    return 1\n",
        test_code="def test_f():\n    assert f() == 1\n",
        metadata={},
    )


class _Loader:
    def __init__(self, tasks, *, quality_report=None, missing_source=None):
        self.tasks = tasks
        if quality_report is not None:
            self.quality_report = quality_report
        if missing_source is not None:
            self.tasks_missing_source = missing_source


def _invoke(monkeypatch, loader, *args: str) -> Result:
    monkeypatch.setattr(dataset_loader, "load_dataset", lambda *a, **k: loader)
    return CliRunner().invoke(cli_app.cli, ["check-dataset", "examples", *args])


class TestProblemsMakeTheCommandFail:
    def test_quality_report_problems_exit_1(self, monkeypatch):
        """质量报告非空 ⇒ rc=1，且错误行说明问题数量（不是「加载失败」）。"""
        loader = _Loader([_task()], quality_report=lambda: {"t1": ["bad patch"]}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 1, f"发现加载问题却报成功：{r.output}"
        assert "加载质量校验未通过" in r.stderr
        assert "1 个任务存在加载问题" in r.stderr
        assert "数据集加载失败" not in r.stderr

    def test_problem_count_matches_report(self, monkeypatch):
        """错误行的计数与报告条目数同源（2 条 ⇒ 写 2，不写「若干」）。"""
        report = {"t1": ["bad"], "t2": ["bad", "worse"]}
        loader = _Loader([_task("t1"), _task("t2")], quality_report=lambda: report, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 1
        assert "2 个任务存在加载问题" in r.stderr

    def test_failure_line_comes_after_quality_report(self, monkeypatch):
        """错误行在报告之后打印：读者先看到问题、再看到结论（顺序锁）。"""
        loader = _Loader([_task()], quality_report=lambda: {"t1": ["bad"]}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 1
        assert r.output.find("质量报告：") < r.output.find("加载质量校验未通过")

    def test_limit_zero_still_fails_from_full_report(self, monkeypatch):
        """--limit 0 不展示任务详情，但全量质量报告仍驱动失败（不是「没看到就没问题」）。"""
        loader = _Loader([_task()], quality_report=lambda: {"t1": ["bad"]}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader, "--limit", "0")
        assert r.exit_code == 1
        assert "加载质量校验未通过" in r.stderr

    def test_problems_with_missing_source_still_fail(self, monkeypatch):
        """质量报告非空 + 缺失源码非空：两者都披露，退出码由质量问题驱动。"""
        loader = _Loader(
            [_task()],
            quality_report=lambda: {"t1": ["bad"]},
            missing_source=lambda: ["t1"],
        )
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 1
        assert "缺失被测源码任务 1 个" in r.output
        assert "加载质量校验未通过" in r.stderr

    def test_quality_report_called_exactly_once(self, monkeypatch):
        """报告只算一遍：重复调用可能让「展示的问题」与「判定的问题」漂移。"""
        calls: list[int] = []

        def _report():
            calls.append(1)
            return {"t1": ["bad"]}

        loader = _Loader([_task()], quality_report=_report, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 1
        assert len(calls) == 1


class TestPassingPathsKeepExitZero:
    def test_empty_report_is_verified_pass(self, monkeypatch):
        """空报告 ⇒ rc=0，通过结论保留（经校验的通过）。"""
        loader = _Loader([_task()], quality_report=lambda: {}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "全量质量检查通过（1 个任务无加载问题）" in r.output
        assert "加载质量校验未通过" not in r.output

    def test_missing_capability_stays_exit_zero(self, monkeypatch):
        """无 quality_report ⇒ rc=0 + 跳过披露（能力缺失不是加载问题）。"""
        loader = _Loader([_task()])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "未提供 quality_report" in r.output
        assert "加载质量校验未通过" not in r.output

    def test_missing_source_alone_is_informational(self, monkeypatch):
        """只有缺失源码（报告为空）⇒ rc=0：源码补充是流程性披露，不是加载失败。"""
        loader = _Loader([_task()], quality_report=lambda: {}, missing_source=lambda: ["t1"])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "缺失被测源码任务 1 个" in r.output
        assert "加载质量校验未通过" not in r.output

    def test_real_examples_still_exit_zero(self):
        """真实 examples（InMemoryDataset）没有质量报告能力 ⇒ 仍 rc=0。"""
        r = CliRunner().invoke(cli_app.cli, ["check-dataset", "examples"])
        assert r.exit_code == 0, r.output
        assert "加载质量校验未通过" not in r.output


class TestUsageErrorsUnaffected:
    def test_unknown_dataset_still_exit_2(self):
        """用法错误仍为 2：质量问题不得把参数错误吞成 1。"""
        r = CliRunner().invoke(cli_app.cli, ["check-dataset", "no_such_dataset_xyz"])
        assert r.exit_code == 2
