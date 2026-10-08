"""M1 包结构测试支持（_m1_metrics._prepare_packaged_test_tree / _run_pytest_in_tmp）单元测试。

背景（2026-10-08 QuixBugs A/B 实测）：QuixBugs 官方测试依赖辅助模块
（`from node import Node` / `from load_testdata import ...`）与包结构
（`from python_programs.xxx import xxx`），历史"单文件口径"在 tmp 环境
里这些 import 全部 ModuleNotFoundError → pytest 收集错误（rc=2）→
repair 被系统性判 0（9 个通过官方测试的正确补丁被误判 correct=0）。
本测试锁定包结构分支的目录树构建与端到端执行链路。
"""

from __future__ import annotations

import os
from pathlib import Path

from experiments._m1_metrics import (
    _prepare_packaged_test_tree,
    _quixbugs_support_root,
    _run_pytest_in_tmp,
)

# ─── _quixbugs_support_root ─────────────────────────────────────────────────


def test_support_root_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    assert _quixbugs_support_root() is None


def test_support_root_none_when_dir_missing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AITESTER_QUIXBUGS_DATA", str(tmp_path / "nope"))
    assert _quixbugs_support_root() is None


def test_support_root_valid(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("AITESTER_QUIXBUGS_DATA", str(tmp_path))
    assert _quixbugs_support_root() == str(tmp_path)


# ─── _prepare_packaged_test_tree ────────────────────────────────────────────


def test_prepare_packaged_tree_layout(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    tmpdir = str(tmp_path / "run")
    os.makedirs(tmpdir)
    test_path, pythonpath = _prepare_packaged_test_tree(
        tmpdir,
        "def foo():\n    return 1\n",
        "import pytest\n\ndef test_a():\n    assert True\n",
        "foo",
    )
    root = Path(tmpdir)
    assert (root / "conftest.py").is_file()
    assert (root / "python_programs" / "__init__.py").is_file()
    assert (root / "python_programs" / "foo.py").is_file()
    assert (root / "correct_python_programs" / "__init__.py").is_file()
    assert Path(test_path).is_file()
    # pytest.use_correct prelude 已注入（QuixBugs 测试的 if 条件依赖）
    assert "pytest.use_correct = False" in Path(test_path).read_text(encoding="utf-8")
    assert tmpdir in pythonpath
    assert "python_testcases" in pythonpath


# ─── _run_pytest_in_tmp 端到端 ──────────────────────────────────────────────


def test_run_pytest_packaged_end_to_end(monkeypatch) -> None:
    """包结构测试（from python_programs.xxx import）应能跑通（修复前 rc=2）。"""
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    target = "def add(a, b):\n    return a + b\n"
    test_code = (
        "import pytest\n"
        "if pytest.use_correct:\n"
        "    from correct_python_programs.add import add\n"
        "else:\n"
        "    from python_programs.add import add\n"
        "\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )
    rc = _run_pytest_in_tmp(test_code, target, "add")
    assert rc is not None
    assert rc[0] == 0, f"包结构测试应通过，实际 rc={rc[0]}: {(rc[1] or '')[-300:]}"


def test_run_pytest_packaged_detects_buggy(monkeypatch) -> None:
    """包结构分支同样能判失败（buggy 代码 → rc != 0）。"""
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    target = "def add(a, b):\n    return a - b\n"
    test_code = "from python_programs.add import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    rc = _run_pytest_in_tmp(test_code, target, "add")
    assert rc is not None and rc[0] != 0


def test_run_pytest_single_file_unchanged(monkeypatch) -> None:
    """历史口径（单文件 synthetic）不受影响。"""
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    target = "def add(a, b):\n    return a + b\n"
    test_code = "from add import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    rc = _run_pytest_in_tmp(test_code, target, "add")
    assert rc is not None and rc[0] == 0
