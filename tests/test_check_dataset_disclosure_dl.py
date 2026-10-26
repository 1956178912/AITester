"""DL 轮：check-dataset 的「无校验能力」不得折叠成 ✓ 或静默。

修复前实测（2026-10-26，零 LLM）::

    python3 main.py check-dataset examples
    ...
    ℹ ✓ 全量质量检查通过（3 个任务无加载问题）   ← DQ 轮起为 `✓ 全量…`（图标单来源）
`InMemoryDataset` 既没有 `quality_report` 也没有 `tasks_missing_source`：
前者缺失时 `report = {}` 被读成「全部健康」，后者缺失时完全无输出。
对真实数据集（`--limit` 只展示前 N 个）这意味着「只看 3 个任务，宣称全量通过」。

口径：
- 加载器提供 `quality_report` 且返回空 dict → 「✓ 全量质量检查通过」是经校验的结论；
- 加载器不提供 → 必须显式披露「跳过」，不得折叠成 ✓；
- 加载器不提供 `tasks_missing_source` → 必须显式披露「跳过检测」，不得静默。
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
    """最小加载器：只有 tasks 必填，能力方法按需挂载。"""

    def __init__(self, tasks, *, quality_report=None, missing_source=None):
        self.tasks = tasks
        if quality_report is not None:
            self.quality_report = quality_report
        if missing_source is not None:
            self.tasks_missing_source = missing_source


def _invoke(monkeypatch, loader) -> Result:
    monkeypatch.setattr(dataset_loader, "load_dataset", lambda *a, **k: loader)
    return CliRunner().invoke(cli_app.cli, ["check-dataset", "examples"])


class TestNoCapabilityDisclosure:
    def test_real_examples_does_not_claim_full_pass(self):
        """真实 examples（InMemoryDataset）没有 quality_report，不得出现「全量质量检查通过」。"""
        r = CliRunner().invoke(cli_app.cli, ["check-dataset", "examples"])
        assert r.exit_code == 0, r.output
        assert "全量质量检查通过" not in r.output
        assert "未提供 quality_report" in r.output

    def test_real_examples_discloses_missing_source_skip(self):
        """真实 examples 没有 tasks_missing_source，必须显式披露跳过而不是静默。"""
        r = CliRunner().invoke(cli_app.cli, ["check-dataset", "examples"])
        assert r.exit_code == 0, r.output
        assert "未提供 tasks_missing_source" in r.output

    def test_loader_without_capabilities_discloses_both(self, monkeypatch):
        """通用机制：无任何能力方法的加载器 → 两条跳过披露、无 ✓ 通过结论。"""
        r = _invoke(monkeypatch, _Loader([_task()]))
        assert r.exit_code == 0, r.output
        assert "未提供 quality_report" in r.output
        assert "未提供 tasks_missing_source" in r.output
        assert "全量质量检查通过" not in r.output
        assert "均含被测源码" not in r.output


class TestCapabilityPositivePathUnchanged:
    def test_empty_report_still_claims_verified_pass(self, monkeypatch):
        """有 quality_report 且返回空 dict → 通过结论有实跑校验背书，保持原文案。"""
        loader = _Loader([_task()], quality_report=lambda: {}, missing_source=lambda: [])
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "✓ 全量质量检查通过（1 个任务无加载问题）" in r.output
        assert "✓ 全部 1 个任务均含被测源码" in r.output
        assert "未提供 quality_report" not in r.output
        assert "未提供 tasks_missing_source" not in r.output

    def test_partial_capability_discloses_only_absent_one(self, monkeypatch):
        """只有 quality_report 时：质量结论保留，源码完整性显式披露跳过。"""
        loader = _Loader([_task()], quality_report=lambda: {})
        r = _invoke(monkeypatch, loader)
        assert r.exit_code == 0, r.output
        assert "✓ 全量质量检查通过" in r.output
        assert "未提供 quality_report" not in r.output
        assert "未提供 tasks_missing_source" in r.output
