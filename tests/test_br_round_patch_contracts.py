"""BR 轮（2026-10-22 第三方集中复审）N08/F04/F05：补丁、导入前缀与 P2P 基线。

N08：unified diff 识别只认 `diff --git` / `@@`，标准 `--- a/x` + `+++ b/x` 头被
当完整源码拒绝；difflib 回退又产出无前缀裸路径（git apply -p1 必拒）。
F04：sys.path 前缀直接放在测试最前，`from __future__` 被挤到非法位置。
F05：PASS_TO_PASS 只在补丁后测一次并当"基线"，补丁回归被误判 harness_invalid。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.agents.executor_imports import auto_fix_imports
from src.agents.executor_repo import RepoExecutor

_REPO_URL = "https://example.com/repo.git"
_COMMIT = "0" * 40
_TEST_PATCH = "--- a/t.py\n+++ b/t.py\n@@ -1 +1 @@\n-x\n+y\n"


class TestUnifiedDiffRecognition:
    @pytest.mark.parametrize(
        "patch",
        [
            "diff --git a/pkg.py b/pkg.py\n--- a/pkg.py\n+++ b/pkg.py\n@@ -1 +1 @@\n-a\n+b\n",
            "@@ -1 +1 @@\n-a\n+b\n",
            "--- a/pkg.py\n+++ b/pkg.py\n@@ -1 +1 @@\n-a\n+b\n",
            "--- pkg.py\n+++ pkg.py\n@@ -1 +1 @@\n-a\n+b\n",
        ],
    )
    def test_standard_shapes_recognized(self, patch):
        assert RepoExecutor._looks_like_unified_diff(patch) is True

    @pytest.mark.parametrize(
        "source",
        [
            "def f():\n    return 1\n",
            "--- 分隔线注释\nx = 1\n",
            "#!/usr/bin/env python\nprint(1)\n",
        ],
    )
    def test_source_code_not_misdetected(self, source):
        assert RepoExecutor._looks_like_unified_diff(source) is False

    def test_bare_headers_normalized(self):
        patch = "--- pkg.py\n+++ pkg.py\n@@ -1 +1 @@\n-a\n+b\n"
        out = RepoExecutor._normalize_unified_headers(patch)
        assert out.splitlines()[0] == "--- a/pkg.py"
        assert out.splitlines()[1] == "+++ b/pkg.py"
        assert "@@ -1 +1 @@" in out

    def test_already_prefixed_and_dev_null_untouched(self):
        patch = "--- a/x.py\n+++ b/x.py\n@@ -1 +1 @@\n-a\n+b\n"
        assert RepoExecutor._normalize_unified_headers(patch) == patch

        new_file = "--- /dev/null\n+++ b/new.py\n@@ -0,0 +1 @@\n+x\n"
        out = RepoExecutor._normalize_unified_headers(new_file)
        assert "--- /dev/null" in out and "+++ b/new.py" in out

    def test_hunk_content_lines_untouched(self):
        """hunk 内以 --- 开头的删除行不是文件头（不得被补前缀）。"""
        patch = "--- pkg.py\n+++ pkg.py\n@@ -1,2 +1,2 @@\n---- not a header\n+++ also content\n"
        lines = RepoExecutor._normalize_unified_headers(patch).splitlines()
        assert lines[0] == "--- a/pkg.py"
        assert lines[1] == "+++ b/pkg.py"
        assert lines[3] == "---- not a header"  # 删除行（内容 "-- not a header"）原样保留
        assert lines[4] == "+++ also content"  # 前一行不是 --- 文件头，不按头处理


class TestSysPathInsertion:
    def test_future_import_stays_first(self, tmp_path: Path):
        (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        code = (
            '"""测试模块 docstring。"""\n'
            "from __future__ import annotations\n"
            "\n"
            "from calculator import add\n"
            "\n"
            "def test_add():\n"
            "    assert add(1, 2) == 3\n"
        )

        fixed = auto_fix_imports(code, str(tmp_path / "calculator.py"), str(tmp_path))

        assert "sys.path" in fixed
        compile(fixed, "fixed", "exec")  # 不再抛 "future imports must occur at the beginning"
        tree_lines = fixed.splitlines()
        assert tree_lines.index("from __future__ import annotations") < tree_lines.index("import sys")

    def test_docstring_before_prefix(self, tmp_path: Path):
        (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        code = '"""docstring 必须是第一条语句。"""\n\nfrom calculator import add\n'
        fixed = auto_fix_imports(code, str(tmp_path / "calculator.py"), str(tmp_path))

        compile(fixed, "fixed", "exec")
        assert fixed.lstrip().startswith('"""docstring')  # 前缀未插到 docstring 之前

    def test_plain_code_prefix_at_top(self, tmp_path: Path):
        (tmp_path / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        code = "from calculator import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
        fixed = auto_fix_imports(code, str(tmp_path / "calculator.py"), str(tmp_path))

        compile(fixed, "fixed", "exec")
        assert fixed.lstrip().startswith("import sys")


class TestP2PBaselineSplit:
    """F05：补丁前基线与补丁后回归必须分开度量。"""

    def _run_verify(self, tmp_path: Path, monkeypatch, baseline: dict, after: dict):
        ex = RepoExecutor(timeout=5, setup_timeout=5)
        repo_dir = tmp_path / "repo"
        repo_dir.mkdir()
        scratch = tmp_path / "tmp"
        scratch.mkdir()
        monkeypatch.setattr("tempfile.gettempdir", lambda: str(scratch))
        monkeypatch.setattr(ex, "setup", lambda _u, _c: {"workdir": str(repo_dir), "cached": True, "error": None})
        monkeypatch.setattr(ex, "_official_harness_enabled", lambda: False)
        monkeypatch.setattr(ex, "_apply_patch_robust", lambda _d, _f: True)
        monkeypatch.setattr(ex, "_apply_llm_patch", lambda _d, _p: True)

        legs = iter(
            [
                {"expected": 2, "passed": 0, "failed_cases": [{"name": "f1"}, {"name": "f2"}]},
                {"expected": 2, "passed": 2, "failed_cases": []},
            ]
        )
        monkeypatch.setattr(ex, "_run_fail_to_pass", lambda _d, _n, repo_url="": next(legs))
        p2p = iter([baseline, after])
        monkeypatch.setattr(ex, "_run_pass_to_pass", lambda _d, _n, repo_url="": next(p2p))

        return ex.verify(_REPO_URL, _COMMIT, "", "lp", ["t.py::a", "t.py::b"], ["t.py::c", "t.py::d"])

    def test_patch_regression_is_not_harness_invalid(self, tmp_path: Path, monkeypatch):
        """基线 2/2、补丁后 1/2：补丁打坏回归 → passed=False，但 harness 有效。"""
        monkeypatch.delenv("P2P_GATE_ENABLE", raising=False)
        monkeypatch.delenv("P2P_GATE_THRESHOLD", raising=False)
        out = self._run_verify(
            tmp_path,
            monkeypatch,
            baseline={"expected": 2, "passed": 2, "failed_cases": []},
            after={"expected": 2, "passed": 1, "failed_cases": [{"name": "t.py::c"}]},
        )

        assert out["passed"] is False
        assert out["harness_invalid"] is False
        assert out["error_info"]["type"] != "harness_invalid" if out.get("error_info") else True
        assert out["p2p_baseline_rate"] == 1.0
        assert out["pass_to_pass_baseline"] == {"expected": 2, "passed": 2}
        assert out["pass_to_pass"] == {"expected": 2, "passed": 1}
        assert "[PASS_TO_PASS baseline] 2/2" in out["output"]
        assert "[PASS_TO_PASS after-llm-patch] 1/2" in out["output"]

    def test_broken_baseline_still_invalidates_harness(self, tmp_path: Path, monkeypatch):
        """基线本身 1/2 < 0.95 → harness_invalid（原门禁语义保留）。"""
        monkeypatch.delenv("P2P_GATE_ENABLE", raising=False)
        monkeypatch.delenv("P2P_GATE_THRESHOLD", raising=False)
        out = self._run_verify(
            tmp_path,
            monkeypatch,
            baseline={"expected": 2, "passed": 1, "failed_cases": [{"name": "t.py::c"}]},
            after={"expected": 2, "passed": 1, "failed_cases": [{"name": "t.py::c"}]},
        )

        assert out["harness_invalid"] is True
        assert out["passed"] is False
        assert out["error_info"]["type"] == "harness_invalid"
        assert out["p2p_baseline_rate"] == 0.5
