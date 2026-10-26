"""DR 轮：CLI 显式空值不得被静默降级为「未提供」。

修复前实测（2026-10-26，零 LLM）::

    python3 main.py check-dataset examples --subset "" --limit 1
    ℹ 数据集 examples（子集: 全部）共加载 3 个任务      ← 显式请求的空 subset 被当作「未提供」
    ... rc=0

    run examples/calculator.py --func "" → _run_single_task(func="")，下游按「未指定」测试全部函数

真实脚本事故形态：``--func "$FUNC"`` / ``--subset "$SUBSET"`` 的变量未展开时，
shell 传的是空字符串，而不是省略选项。空值被当作「未提供」会把请求范围悄悄放宽
到全部函数 / 全量数据（前者还会按函数数消耗 LLM），且命令以 rc=0 报「成功」。

口径：显式空字符串（含纯空白）= 用法错误 rc=2，且不得触碰被测目标
（不启动任务 / 不加载数据集）。未提供选项（None）与显式空值不是同一件事。
"""

from __future__ import annotations

from click.testing import CliRunner

from src.cli import app as cli_app
from src.datasets import dataset_loader

CALCULATOR = "examples/calculator.py"


def _invoke(*args: str):
    return CliRunner().invoke(cli_app.cli, list(args))


def _forbid(message: str):
    def _boom(*_args, **_kwargs):
        raise AssertionError(message)

    return _boom


class TestRunRejectsBlankFunc:
    @staticmethod
    def _invoke_run(monkeypatch, func: str):
        monkeypatch.setattr(cli_app, "_run_single_task", _forbid("空 --func 不得启动任务"))
        return _invoke("run", CALCULATOR, "--func", func)

    @staticmethod
    def _blank_funcs() -> list[str]:
        return ["", " ", "   ", "\t", " \n "]

    def test_blank_func_is_usage_error(self, monkeypatch):
        for blank in self._blank_funcs():
            r = self._invoke_run(monkeypatch, blank)
            assert r.exit_code == 2, f"--func={blank!r} 应以用法错误拒绝: {r.output}"
            assert "--func 不能为空" in r.stderr, r.stderr

    def test_blank_func_does_not_start_any_task(self, monkeypatch):
        # _forbid 已在 _invoke_run 里挂上：走到 _run_single_task 就是断言失败。
        r = self._invoke_run(monkeypatch, "")
        assert r.exit_code == 2
        assert not isinstance(r.exception, AssertionError), r.exception

    def test_named_func_is_passed_through(self, monkeypatch):
        seen: dict[str, object] = {}

        def fake_run_single(task_file, func, max_iterations, timeout, coverage_threshold, output_json, **kwargs):
            seen["func"] = func
            return {
                "success": True,
                "file": task_file,
                "func": func or "all",
                "passed": True,
                "coverage": 1.0,
                "coverage_ok": True,
                "iterations": 1,
            }

        monkeypatch.setattr(cli_app, "_run_single_task", fake_run_single)
        r = _invoke("run", CALCULATOR, "--func", "divide", "--json")
        assert r.exit_code == 0, r.output
        assert seen["func"] == "divide", "合法的 --func 不应被改写"

    def test_omitting_func_still_means_all_functions(self, monkeypatch):
        seen: dict[str, object] = {}

        def fake_run_single(task_file, func, max_iterations, timeout, coverage_threshold, output_json, **kwargs):
            seen["func"] = func
            return {
                "success": True,
                "file": task_file,
                "func": func or "all",
                "passed": True,
                "coverage": 1.0,
                "coverage_ok": True,
                "iterations": 1,
            }

        monkeypatch.setattr(cli_app, "_run_single_task", fake_run_single)
        r = _invoke("run", CALCULATOR, "--json")
        assert r.exit_code == 0, r.output
        assert seen["func"] is None, "省略 --func 仍是「未提供」（测试全部函数），不是空值"


class TestCheckDatasetRejectsBlankSubset:
    @staticmethod
    def _invoke_check(monkeypatch, subset: str):
        monkeypatch.setattr(dataset_loader, "load_dataset", _forbid("空 --subset 不得加载数据集"))
        return _invoke("check-dataset", "examples", "--subset", subset, "--limit", "1")

    @staticmethod
    def _blank_subsets() -> list[str]:
        return ["", " ", "   ", "\t", " \n "]

    def test_blank_subset_is_usage_error(self, monkeypatch):
        for blank in self._blank_subsets():
            r = self._invoke_check(monkeypatch, blank)
            assert r.exit_code == 2, f"--subset={blank!r} 应以用法错误拒绝: {r.output}"
            assert "--subset 不能为空" in r.stderr, r.stderr

    def test_blank_subset_does_not_load_any_dataset(self, monkeypatch):
        # load_dataset 已被 _forbid 替换：走到加载就是断言失败。
        r = self._invoke_check(monkeypatch, "")
        assert r.exit_code == 2
        assert not isinstance(r.exception, AssertionError), r.exception
        assert "子集: 全部" not in r.output, "不得再把显式空 subset 渲染成「全部」"

    def test_omitting_subset_still_loads_all(self):
        r = _invoke("check-dataset", "examples", "--limit", "1")
        assert r.exit_code == 0, r.output
        assert "（子集: 全部）" in r.output

    def test_non_blank_subset_still_goes_through_support_check(self):
        # examples 不支持子集：非空值仍走能力表校验（DN 口径不变），不是被空值守卫吞掉。
        r = _invoke("check-dataset", "examples", "--subset", "lite")
        assert r.exit_code == 2, r.output
        assert "不支持子集" in r.output
