"""DO 轮（2026-10-26）CLI 表面一致性：help 渲染 / 文档宣称 / 覆盖率判定披露。

修复前实测：
- ``python main.py --help`` 原样打印 rich 标记 ``[bold]示例命令[/bold]`` 与 Markdown
  粗体 ``**…**``（组帮助 2 处、``doctor --help`` 1 处）——help 走 click 纯文本通道，
  两类标记都不会渲染，用户看到的是源码标记；
- CLI 组帮助与 ``docs/api_reference{,.en}.md`` 宣称 ``run`` 报告 detection / repair /
  false_fix 三指标；实测 ``run`` 只输出测试是否通过、覆盖率与迭代次数，三指标由
  ``experiments/_m1_metrics.py`` 计算、``experiments/run_benchmark.py`` 消费（需要
  gold 材料），CLI 从不计算也不输出；
- ``--coverage-threshold`` 的逐任务判定写入 ``coverage_ok``，但批次摘要只统计测试
  通过数——覆盖率判定在摘要中完全缺席，docstring 却宣称「用于结果判定与摘要输出」；
- ``docs/api_reference{,.en}.md`` 模块地图把 M1 指标记在 ``src/measurement/``，该包
  实际只有 MDO / 恢复延迟 / 检索质量。

本轮把「宣称」收敛到「现实」：help 不泄漏 rich/Markdown 标记；三指标如实归位基准
评估面并以「不在 CLI 输出中」显式披露；覆盖率判定以达标/未达标/不可测三态进入批次
摘要；退出码仍只看测试通过/失败，并在 ``run --help`` 与 api_reference 写明。
"""

from __future__ import annotations

import inspect
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from src.cli import app as cli_app

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _invoke(args: list[str]):
    return CliRunner().invoke(cli_app.cli, args)


class _FakeFinalState:
    """模拟 graph.invoke 返回的 final_state（dict-like 接口）。"""

    def __init__(self, test_passed: bool, coverage=None, iteration: int = 1):
        self._data = {
            "test_passed": test_passed,
            "coverage_report": coverage,
            "diagnosis": None,
            "error_category": None,
            "iteration": iteration,
        }

    def get(self, key, default=None):
        return self._data.get(key, default)


def _patch_workflow(monkeypatch, final_state: _FakeFinalState) -> None:
    graph = MagicMock()
    graph.invoke.side_effect = lambda state: final_state
    monkeypatch.setattr(cli_app, "build_workflow", lambda: graph)
    monkeypatch.setattr(cli_app.token_usage, "get_usage", lambda: MagicMock(as_dict=lambda: {}))
    monkeypatch.setattr(cli_app, "start_task_trace", lambda *a, **k: None)
    monkeypatch.setattr(cli_app, "end_task_trace", lambda *a, **k: None)


def _write_target(tmp_path) -> str:
    p = tmp_path / "calc.py"
    p.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    return str(p)


class TestGroupHelpRendering:
    """组帮助走 click 纯文本通道：rich 标记必须不落进用户可见输出。"""

    def test_group_help_has_no_raw_rich_markup(self):
        r = _invoke(["--help"])
        assert r.exit_code == 0
        assert "[bold]" not in r.output
        assert "[/bold]" not in r.output
        assert "**" not in r.output, "Markdown 粗体在 click 纯文本 help 里不会渲染"
        assert "示例命令" in r.output

    @pytest.mark.parametrize("command", ["run", "list-examples", "check-dataset", "clean-venv-cache", "doctor"])
    def test_command_help_is_plain_text(self, command):
        r = _invoke([command, "--help"])
        assert r.exit_code == 0
        assert "**" not in r.output
        assert "[bold]" not in r.output


class TestRunDocumentedSurface:
    """`run` 的文档/帮助必须如实描述实际输出面（含缺席面的显式披露）。"""

    def test_cli_help_discloses_m1_metrics_are_not_cli_output(self):
        out = _invoke(["--help"]).output
        assert "如实报告" not in out, "旧宣称：CLI 如实报告三指标——实际从不计算也不输出"
        assert "不在 CLI 输出中" in out, "缺席面必须显式披露，而不是从帮助里消失"

    def test_run_help_states_coverage_threshold_does_not_change_exit_code(self):
        out = _invoke(["run", "--help"]).output
        assert "不改变退出码" in out

    def test_api_reference_zh_documents_actual_run_surface(self):
        text = (PROJECT_ROOT / "docs/api_reference.md").read_text(encoding="utf-8")
        assert "`run` 的输出摘要包含三指标" not in text
        assert "coverage_ok" in text
        assert "不改变退出码" in text
        assert "experiments/_m1_metrics.py" in text

    def test_api_reference_en_documents_actual_run_surface(self):
        text = (PROJECT_ROOT / "docs/api_reference.en.md").read_text(encoding="utf-8")
        assert "prints the three metrics" not in text
        assert "coverage_ok" in text
        assert "does **not**" in text and "change the exit code" in text
        assert "experiments/_m1_metrics.py" in text

    def test_api_reference_module_map_does_not_credit_m1_to_measurement(self):
        for name in ("api_reference.md", "api_reference.en.md"):
            text = (PROJECT_ROOT / "docs" / name).read_text(encoding="utf-8")
            rows = [line for line in text.splitlines() if line.startswith("| `src/measurement/` |")]
            assert len(rows) == 1, f"{name} 模块地图应有且仅有 src/measurement 一行"
            assert "M1" not in rows[0], f"{name}：M1 实现在 experiments/_m1_metrics.py，不在 src/measurement"
            assert "compute_mdo" in rows[0], f"{name}：模块地图的主要入口必须是该包真实导出"

    def test_single_task_docstring_does_not_claim_result_judgement(self):
        doc = inspect.getdoc(cli_app._run_single_task) or ""
        assert "用于结果判定" not in doc, "阈值只写 coverage_ok，不参与任务通过/退出码判定"
        assert "coverage_ok" in doc


class TestBatchSummaryCoverageVerdict:
    """批次摘要必须披露已计算的覆盖率判定（达标 / 未达标 / 不可测三态）。"""

    def test_summary_reports_met_missed_unmeasured(self, capsys):
        results = [
            {"file": "a.py", "func": "all", "passed": True, "coverage": 90.0, "coverage_ok": True},
            {"file": "b.py", "func": "all", "passed": True, "coverage": 40.0, "coverage_ok": False},
            {"file": "c.py", "func": "all", "passed": False},
        ]
        cli_app._print_run_summary(results, total=3, passed=2, failed=1, elapsed_time=1.5, coverage_threshold=80.0)
        out = capsys.readouterr().out
        assert "覆盖率：1 达标 / 1 未达标 / 1 不可测（阈值 80.0%）" in out

    def test_error_result_counts_as_unmeasured(self, capsys):
        results = [{"file": "a.py", "func": "all", "passed": False, "error": "boom"}]
        cli_app._print_run_summary(results, total=1, passed=0, failed=1, elapsed_time=0.1, coverage_threshold=80.0)
        out = capsys.readouterr().out
        assert "覆盖率：0 达标 / 0 未达标 / 1 不可测（阈值 80.0%）" in out

    def test_run_below_threshold_still_exits_zero_and_summary_discloses(self, tmp_path, monkeypatch, capsys):
        path = _write_target(tmp_path)
        _patch_workflow(monkeypatch, _FakeFinalState(test_passed=True, coverage=50.0))
        r = _invoke(["run", path, "--coverage-threshold=80"])
        assert r.exit_code == 0, "覆盖率未达标不改变退出码（退出码只看测试通过/失败）"
        assert "覆盖率：0 达标 / 1 未达标 / 0 不可测（阈值 80.0%）" in r.output
        assert "通过：1" in r.output

    def test_run_without_coverage_data_discloses_unmeasured(self, tmp_path, monkeypatch):
        path = _write_target(tmp_path)
        _patch_workflow(monkeypatch, _FakeFinalState(test_passed=True, coverage=None))
        r = _invoke(["run", path])
        assert r.exit_code == 0
        assert "覆盖率：0 达标 / 0 未达标 / 1 不可测（阈值 80.0%）" in r.output
