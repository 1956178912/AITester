"""DQ 轮：CLI 状态图标只允许一个来源——输出助手。

修复前实测（2026-10-26，零 LLM）::

    python3 main.py check-dataset examples --limit 1
    ...
    ℹ   ✓ 加载质量健康

`info_msg` 已经加 `ℹ ` 前缀，调用点又手写 `✓`；同族的 `warning_msg` 调用点带手写 `⚠`
时会输出 `⚠ ⚠ …`。三处成功事实（单个任务健康 / 全量质量通过 / 源码完整）还写成
`info_msg`（蓝 ℹ）而不是 `success_msg`（绿 ✓），读起来像两条互相矛盾的状态。

口径：图标由 `src/cli/output.py` 的四个助手唯一提供；调用点传入的字符串去掉前导空白后
不得以 `⚠ ✓ ℹ ✗` 开头。AST 锁对 `src/` 全量生效，行为锁覆盖四个助手与 `check-dataset`
的六个调用分支。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from src.cli import app as cli_app
from src.cli.output import error_msg, info_msg, success_msg, warning_msg
from src.datasets import dataset_loader

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
HELPERS = {"success_msg", "error_msg", "warning_msg", "info_msg"}
ICONS = ("⚠", "✓", "ℹ", "✗")

# 行首状态图标后紧跟第二个状态图标（含空行缩进形式的 `ℹ   ✓`）
_DOUBLED_ICON = re.compile(r"^[ \t]*(?:⚠|✓|ℹ|✗)\s+(?:⚠|✓|ℹ|✗)", re.MULTILINE)


def _leading_literal(call: ast.Call) -> str | None:
    """返回助手调用首参的起始字面量：Constant 整串，或 f-string 的第一段常量。"""
    if not call.args:
        return None
    arg = call.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value
    if isinstance(arg, ast.JoinedStr) and arg.values:
        head = arg.values[0]
        if isinstance(head, ast.Constant) and isinstance(head.value, str):
            return head.value
        return ""
    return None


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
    """能力方法按需挂载：缺省即「加载器不提供该能力」。"""

    def __init__(self, tasks, *, quality_report=None, missing_source=None):
        self.tasks = tasks
        if quality_report is not None:
            self.quality_report = quality_report
        if missing_source is not None:
            self.tasks_missing_source = missing_source


def _invoke(monkeypatch, loader):
    monkeypatch.setattr(dataset_loader, "load_dataset", lambda *a, **k: loader)
    return CliRunner().invoke(cli_app.cli, ["check-dataset", "swe_bench"])


class TestHelperOwnsTheIcon:
    """四个助手各自只加一个图标；调用方不需要也不应该补。"""

    @pytest.mark.parametrize(
        ("helper", "icon", "stream"),
        [
            (success_msg, "✓", "out"),
            (info_msg, "ℹ", "out"),
            (warning_msg, "⚠", "err"),
            (error_msg, "✗", "err"),
        ],
        ids=["success", "info", "warning", "error"],
    )
    def test_helper_adds_icon_exactly_once(self, capsys, helper, icon, stream):
        helper("payload")
        text = getattr(capsys.readouterr(), stream)
        assert text == f"{icon} payload\n"


class TestIconDetector:
    """AST 判据自身的正反例：扫描器失效时不能让锁空转。"""

    def _first_call(self, source: str) -> ast.Call:
        tree = ast.parse(source)
        return next(node for node in ast.walk(tree) if isinstance(node, ast.Call))

    def test_detects_manual_icon_in_fstring(self):
        head = _leading_literal(self._first_call('warning_msg(f"  ⚠ {issue}")'))
        assert head is not None
        assert head.lstrip().startswith(ICONS)

    def test_detects_manual_icon_in_plain_string(self):
        head = _leading_literal(self._first_call('info_msg("✓ 通过")'))
        assert head is not None
        assert head.lstrip().startswith(ICONS)

    def test_ignores_icon_after_expression(self):
        head = _leading_literal(self._first_call('info_msg(f"{icon} 通过")'))
        assert head == ""

    def test_ignores_message_without_icon(self):
        head = _leading_literal(self._first_call('warning_msg(f"质量报告：{n}")'))
        assert head is not None
        assert not head.lstrip().startswith(ICONS)


class TestCallSitesDoNotWriteIcons:
    """结构锁：`src/` 里所有助手调用的首参不得自带状态图标。"""

    def test_src_helper_calls_have_single_icon_source(self):
        violations: list[str] = []
        checked = 0
        for path in sorted(SRC_DIR.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                if not (isinstance(func, ast.Name) and func.id in HELPERS):
                    continue
                checked += 1
                head = _leading_literal(node)
                if head is not None and head.lstrip().startswith(ICONS):
                    violations.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}: {head!r}")
        assert checked >= 55, f"AST 扫描只看到 {checked} 处助手调用，判据已失效"
        assert violations == [], "图标必须由输出助手唯一提供：\n" + "\n".join(violations)


class TestRealCheckDatasetOutput:
    def test_examples_never_doubles_the_status_icon(self):
        r = CliRunner().invoke(cli_app.cli, ["check-dataset", "examples", "--limit", "1"])
        assert r.exit_code == 0, r.output
        assert _DOUBLED_ICON.search(r.output) is None, r.output
        assert "✓   加载质量健康" in r.output
        assert "ℹ   ✓" not in r.output


class TestFakeLoaderBranches:
    """六个调用分支逐个走一遍：图标一份、成功事实用 ✓。"""

    def test_task_issues_use_one_warning_icon(self, monkeypatch):
        monkeypatch.setattr(
            dataset_loader.SWEBenchDataset,
            "validate_task",
            staticmethod(lambda t: ["结构不完整"]),
        )
        r = _invoke(monkeypatch, _Loader([_task()], quality_report=lambda: {}, missing_source=lambda: []))
        assert r.exit_code == 0, r.output
        assert "⚠   结构不完整" in r.output
        assert _DOUBLED_ICON.search(r.output) is None, r.output

    def test_quality_report_problems_use_one_warning_icon(self, monkeypatch):
        # DU 轮改写：发现加载问题必须非零退出；本用例只锁图标单一来源。
        loader = _Loader([_task()], quality_report=lambda: {"t1": ["bad patch"]}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 1, r.output
        assert "⚠ 质量报告：1/1 个任务存在加载问题：" in r.output
        assert _DOUBLED_ICON.search(r.output) is None, r.output

    def test_missing_source_uses_one_warning_icon(self, monkeypatch):
        loader = _Loader([_task()], quality_report=lambda: {}, missing_source=lambda: ["t1"])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "⚠ 缺失被测源码任务 1 个" in r.output
        assert _DOUBLED_ICON.search(r.output) is None, r.output

    def test_success_facts_use_success_marker(self, monkeypatch):
        loader = _Loader([_task()], quality_report=lambda: {}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "✓   加载质量健康" in r.output
        assert re.search(r"^✓ 全量质量检查通过（1 个任务无加载问题）$", r.output, re.MULTILINE)
        assert re.search(r"^✓ 全部 1 个任务均含被测源码$", r.output, re.MULTILINE)
        assert "ℹ ✓" not in r.output
        assert _DOUBLED_ICON.search(r.output) is None, r.output

    def test_zero_tasks_warning_uses_one_warning_icon(self, monkeypatch):
        r = _invoke(monkeypatch, _Loader([]))
        assert r.exit_code == 1, r.output
        assert "⚠ 未加载到任何任务" in r.output
        assert _DOUBLED_ICON.search(r.output) is None, r.output
