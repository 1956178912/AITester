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


# ─── 双布局（2026-10-10 第四起测量伪影修复）────────────────────────────────


class TestDualLayout:
    """被测模块须**同时**以扁平与包结构两种方式可 import。

    背景（审查报告 §11.1b 结果二十一）：被测模块名取 task_id 末段（如
    `bitcount`），生产执行沙箱把模块**平铺**写成 `{module}.py`，故 Generator
    写出的测试用**扁平 import**（`from bitcount import bitcount`）——在它被
    生成的环境里是正确的。但判分树此前只提供包结构，扁平 import 一律
    `ModuleNotFoundError` → pytest rc=2（收集中断）→
    `_looks_like_test_execution_error` 判"没跑起来" → **detection 构造性恒为 0**。
    实测（12 任务子集 9 个缺陷程序）：修复前 **9/9 两侧 rc=2**、
    F2P 检出 **0/7**；修复后 F2P 检出 **6/7**。
    """

    def test_root_level_module_written(self, tmp_path, monkeypatch) -> None:
        """tmpdir 根须有 {module}.py（扁平 import 可解析）。"""
        monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
        tmpdir = str(tmp_path / "run")
        os.makedirs(tmpdir)
        _prepare_packaged_test_tree(tmpdir, "def foo():\n    return 1\n", "def test_a():\n    assert True\n", "foo")
        root = Path(tmpdir)
        # 双布局：扁平 + 包结构并存，且内容一致
        assert (root / "foo.py").is_file(), "扁平布局缺失（第四起伪影会复发）"
        assert (root / "python_programs" / "foo.py").is_file(), "包结构布局缺失"
        assert (root / "foo.py").read_text(encoding="utf-8") == (root / "python_programs" / "foo.py").read_text(
            encoding="utf-8"
        )

    def test_flat_import_runs_green(self, monkeypatch) -> None:
        """**关键回归锁**：扁平 import 的测试须能跑通（修复前 rc=2）。"""
        monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
        target = "def bitcount(n):\n    return bin(n).count('1')\n"
        test_code = "from bitcount import bitcount\n\ndef test_bitcount():\n    assert bitcount(7) == 3\n"
        res = _run_pytest_in_tmp(test_code, target, "bitcount", task_metadata={"source": "quixbugs"})
        assert res is not None
        rc, out, err = res
        assert rc == 0, f"扁平 import 应跑通，实际 rc={rc}\n{out[:400]}\n{err[:200]}"

    def test_flat_import_detects_bug(self, monkeypatch) -> None:
        """扁平 import 下 F2P 应能成立：buggy 红 ∧ fixed 绿。"""
        monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
        buggy = "def bitcount(n):\n    return 0\n"
        fixed = "def bitcount(n):\n    return bin(n).count('1')\n"
        test_code = "from bitcount import bitcount\n\ndef test_bitcount():\n    assert bitcount(7) == 3\n"
        rb = _run_pytest_in_tmp(test_code, buggy, "bitcount", task_metadata={"source": "quixbugs"})
        rf = _run_pytest_in_tmp(test_code, fixed, "bitcount", task_metadata={"source": "quixbugs"})
        assert rb is not None and rf is not None
        assert rb[0] != 0, "buggy 侧应变红"
        assert rf[0] == 0, "fixed 侧应变绿（F2P 第 2 段）"

    def test_packaged_import_still_works(self, monkeypatch) -> None:
        """包结构 import 不得因双布局而回归。"""
        monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
        target = "def bitcount(n):\n    return bin(n).count('1')\n"
        test_code = (
            "from python_programs.bitcount import bitcount\n\ndef test_bitcount():\n    assert bitcount(7) == 3\n"
        )
        res = _run_pytest_in_tmp(test_code, target, "bitcount", task_metadata={"source": "quixbugs"})
        assert res is not None
        assert res[0] == 0, f"包结构 import 回归，rc={res[0]}\n{res[1][:400]}"

    def test_invalid_test_still_scores_zero(self, monkeypatch) -> None:
        """**口径未放松**：恒失败测试在新布局下仍不得算检出（buggy 侧也红）。"""
        monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
        target = "def bitcount(n):\n    return bin(n).count('1')\n"
        test_code = "from bitcount import bitcount\n\ndef test_always_fail():\n    assert bitcount(7) == 999\n"
        rb = _run_pytest_in_tmp(test_code, target, "bitcount", task_metadata={"source": "quixbugs"})
        assert rb is not None
        assert rb[0] != 0, "恒失败测试在 buggy 侧也红 → 不构成 F2P（口径未放松）"
