"""src.budget 包下沉验证（U9，2026-10-05 系统性审查落地）。

锁定三条契约：
1. 新旧导入路径取到同一对象（shim 是 re-export 而非复制）；
2. agents 层不再 import src.graph 的预算/token 模块（分层倒置修复）；
3. src.budget 导入无副作用（纯数据模块，不触发 LLM/网络/文件）。
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestBudgetPackageContract:
    def test_old_and_new_paths_same_object(self):
        """旧路径 shim 与新路径是同一函数对象。"""
        import src.budget.cost_budget as new_cb
        import src.budget.token_usage as new_tu
        import src.graph.cost_budget as old_cb
        import src.graph.token_usage as old_tu

        assert old_cb.check_budget is new_cb.check_budget
        assert old_cb.BudgetExceededError is new_cb.BudgetExceededError
        assert old_cb.record_usage_and_check is new_cb.record_usage_and_check
        assert old_cb.get_process_budget_stats is new_cb.get_process_budget_stats
        assert old_tu.TokenUsage is new_tu.TokenUsage
        assert old_tu.get_usage is new_tu.get_usage
        assert old_tu.record_usage is new_tu.record_usage
        assert old_tu.attach_usage is new_tu.attach_usage
        assert old_tu.global_usage is new_tu.global_usage
        assert old_tu.reset is new_tu.reset

    def test_package_reexports_match_modules(self):
        """src.budget 顶层 re-export 与子模块同一对象。"""
        import src.budget as pkg
        from src.budget import cost_budget as cb
        from src.budget import token_usage as tu

        assert pkg.BudgetExceededError is cb.BudgetExceededError
        assert pkg.check_budget is cb.check_budget
        assert pkg.TokenUsage is tu.TokenUsage
        assert pkg.get_usage is tu.get_usage

    def test_agents_no_longer_import_graph_budget(self):
        """分层倒置修复锁定：src/agents 下不得再引用 src.graph 的预算模块。"""
        forbidden = ("src.graph.cost_budget", "src.graph.token_usage")
        offenders = [
            f"{py.name}: {marker}"
            for py in (REPO_ROOT / "src" / "agents").rglob("*.py")
            for marker in forbidden
            if marker in py.read_text(encoding="utf-8")
        ]
        assert not offenders, f"agents 层仍引用 graph 预算模块: {offenders}"

    def test_budget_import_no_side_effects(self, tmp_path, monkeypatch):
        """导入 src.budget 无文件副作用（纯数据模块契约）。"""
        monkeypatch.chdir(tmp_path)

        import src.budget
        import src.budget.cost_budget
        import src.budget.token_usage  # noqa: F401

        assert list(tmp_path.iterdir()) == [], "导入产生了文件副作用"
        # token 记账线程隔离语义保持
        from src.budget.token_usage import record_usage, reset

        reset()
        record_usage(10, 5)
        assert list(tmp_path.iterdir()) == []
