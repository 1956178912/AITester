"""O3 分支覆盖注入（src/tools/branch_coverage_inject.py）单元测试。

背景：2026-09-29 批次新增的 opt-in 模块（BRANCH_COVERAGE_INJECT_ENABLE
默认关）落地时零测试覆盖——`tools/branch_coverage_inject.py` 20 个分支
在 coverage.xml 中全部未覆盖，是本批次总分支覆盖从 77% 跌至 73% 的
主因之一。本文件覆盖：开关解析 / 超时解析 / prompt 注入段落（含
排序、Top-20 截断、to=None 边界）/ measure_branch_coverage 降级与
真实测量路径（2026-10-02 审查修复）。
"""

from __future__ import annotations

import textwrap

import pytest

from src.tools.branch_coverage_inject import (
    _measure_timeout,
    branch_coverage_inject_enabled,
    build_branch_coverage_prompt_section,
    measure_branch_coverage,
)


class TestSwitches:
    """开关与超时参数解析（默认 false / 默认 60s 历史口径）。"""

    def test_enabled_default_false(self, monkeypatch):
        monkeypatch.delenv("BRANCH_COVERAGE_INJECT_ENABLE", raising=False)
        assert branch_coverage_inject_enabled() is False

    @pytest.mark.parametrize("value", ["true", "TRUE", "1", "on"])
    def test_enabled_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("BRANCH_COVERAGE_INJECT_ENABLE", value)
        assert branch_coverage_inject_enabled() is True

    def test_enabled_false_value(self, monkeypatch):
        monkeypatch.setenv("BRANCH_COVERAGE_INJECT_ENABLE", "no")
        assert branch_coverage_inject_enabled() is False

    def test_measure_timeout_default_and_invalid(self, monkeypatch):
        monkeypatch.delenv("BRANCH_COVERAGE_INJECT_TIMEOUT", raising=False)
        assert _measure_timeout() == 60
        monkeypatch.setenv("BRANCH_COVERAGE_INJECT_TIMEOUT", "15")
        assert _measure_timeout() == 15
        monkeypatch.setenv("BRANCH_COVERAGE_INJECT_TIMEOUT", "abc")
        assert _measure_timeout() == 60


class TestPromptSection:
    """build_branch_coverage_prompt_section 注入段落（保守口径）。"""

    def test_none_returns_empty(self):
        assert build_branch_coverage_prompt_section(None) == ""

    def test_empty_missing_returns_empty(self):
        assert build_branch_coverage_prompt_section({"missing_branches": []}) == ""
        assert build_branch_coverage_prompt_section({"branch_coverage": 80.0}) == ""

    def test_renders_count_and_coverage(self):
        text = build_branch_coverage_prompt_section(
            {"branch_coverage": 66.5, "missing_branches": [{"line": 10, "to": 14}]}
        )
        assert "共 1 条" in text
        assert "66.5" in text
        assert "第 10 行 → 第 14 行" in text

    def test_missing_to_renders_partial(self):
        text = build_branch_coverage_prompt_section({"missing_branches": [{"line": 7}]})
        assert "部分分支未覆盖" in text

    def test_sorted_by_line_and_capped_at_20(self):
        missing = [{"line": n, "to": n + 1} for n in range(100, 130)]  # 30 条
        text = build_branch_coverage_prompt_section({"missing_branches": missing})
        assert "共 30 条" in text  # 总数如实
        # 20 条截断：行首 100..119 展示（`- 第 N 行`），120..129 不作为条目行首
        assert "- 第 100 行" in text
        assert "- 第 119 行" in text
        assert "- 第 120 行" not in text
        assert "- 第 129 行" not in text
        assert text.count("\n- 第 ") == 20, "应恰好展示 20 条（Top-20 截断）"


class TestMeasureBranchCoverage:
    """measure_branch_coverage 降级路径 + 真实测量路径。"""

    def test_empty_test_code_returns_none(self, tmp_path):
        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        assert measure_branch_coverage(str(target), "  ") is None

    def test_missing_target_returns_none(self, tmp_path):
        missing = tmp_path / "nope.py"
        assert measure_branch_coverage(str(missing), "def test(): pass") is None

    def test_real_measurement_reports_branches(self, tmp_path):
        """真实测量：含分支的模块 + 触发分支的测试 → 返回分支统计。"""
        target = tmp_path / "branchy_mod.py"
        target.write_text(
            textwrap.dedent(
                """
                def check(n):
                    if n > 0:
                        return "pos"
                    return "non-pos"
                """
            ).strip(),
            encoding="utf-8",
        )
        test_code = textwrap.dedent(
            """
            from branchy_mod import check

            def test_positive():
                assert check(1) == "pos"
            """
        ).strip()
        result = measure_branch_coverage(str(target), test_code, module_name="branchy_mod")
        assert result is not None, "真实测量应成功（coverage + pytest 子进程）"
        assert result["target_module"] == "branchy_mod"
        assert result["total_branches"] > 0, "含 if 分支的模块应测得分支"
        assert 0.0 <= result["branch_coverage"] <= 100.0
        # 测试只走正分支 → 至少一条 missing 分支（if 的 else 方向）
        assert result["missing_branches"], "仅覆盖单侧分支时应报告 missing"
        first = result["missing_branches"][0]
        assert "line" in first and "to" in first

    def test_coverage_unavailable_returns_none(self, tmp_path):
        """coverage 模块不可用 → ImportError → 保守降级 None。"""
        import sys
        from unittest.mock import patch

        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        with patch.dict(sys.modules, {"coverage": None}):
            assert measure_branch_coverage(str(target), "def test(): pass") is None

    def test_subprocess_failure_returns_none(self, tmp_path):
        """子进程 rc != 0 且无 result 文件 → None。"""
        from unittest.mock import MagicMock, patch

        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        proc = MagicMock()
        proc.returncode = 1
        proc.stderr = "boom"
        with patch("subprocess.run", return_value=proc):
            assert measure_branch_coverage(str(target), "def test(): pass") is None

    def test_timeout_returns_none(self, tmp_path):
        """子进程超时 → TimeoutExpired → None。"""
        import subprocess
        from unittest.mock import patch

        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="x", timeout=60)):
            assert measure_branch_coverage(str(target), "def test(): pass") is None

    def test_unexpected_exception_returns_none(self, tmp_path):
        """测量过程意外异常 → 保守降级 None。"""
        from unittest.mock import patch

        target = tmp_path / "mod.py"
        target.write_text("def f():\n    return 1\n", encoding="utf-8")
        with patch("subprocess.run", side_effect=RuntimeError("boom")):
            assert measure_branch_coverage(str(target), "def test(): pass") is None
