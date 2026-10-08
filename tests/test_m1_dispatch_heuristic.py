"""M1 执行器分派启发式（R16/R27，2026-10-08 R2）单元测试。

背景：
    历史分派用 ``"python_programs" in test_code`` 子串启发式——任何测试
    文本里**出现该字面串**（注释 / 断言消息 / 字符串）都会被误分派到
    包结构分支，在 QuixBugs 之外的新基准/多模块任务上产生错误口径。
    R16 要求显式 dispatch 契约（来源标记进 metadata），子串仅作 QuixBugs
    兼容回退（metadata 缺省时）。

本测试锁定：
    1. metadata 在场时**显式信号优先**——含字面 "python_programs" 的
       synthetic 单文件测试不被误分派到包结构分支（R16 核心防线）；
    2. source=="quixbugs"（显式）→ 包结构分支（即便测试不含子串）；
    3. metadata 缺省时子串回退保持（向后兼容 detection_gates 委托调用）。
"""

from __future__ import annotations

from typing import Any

from experiments._m1_metrics import _run_pytest_in_tmp

# 含字面 "python_programs" 的单文件测试（子串出现在注释里，非 import）
_SINGLE_FILE_TEST_WITH_LITERAL = (
    "# 说明：本测试与 python_programs 包结构无关（历史误分派诱因）\n"
    "from add import add\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
)


def _synthetic_md() -> dict[str, Any]:
    return {"source": "synthetic", "is_cross_file": False}


def _quixbugs_md() -> dict[str, Any]:
    return {"source": "quixbugs", "is_cross_file": False}


def test_synthetic_with_literal_substring_not_misdirected() -> None:
    """含字面 'python_programs' 的单文件测试（metadata 在场）→ 单文件分支。

    若仍走子串启发式，包分支会把 ``add.py`` 写到 python_programs/ 下，
    而测试 ``from add import add`` 在包分支不可解析 → rc=2。显式分派后
    单文件分支正常执行 rc=0。
    """
    target = "def add(a, b):\n    return a + b\n"
    rc = _run_pytest_in_tmp(_SINGLE_FILE_TEST_WITH_LITERAL, target, "add", task_metadata=_synthetic_md())
    assert rc is not None and rc[0] == 0, f"不应误分派到包结构分支，实际 rc={None if rc is None else rc[0]}"


def test_quixbugs_source_explicit_packaged() -> None:
    """source=='quixbugs'（显式）→ 包结构分支（测试内含 python_programs import）。"""
    target = "def add(a, b):\n    return a + b\n"
    test_code = "from python_programs.add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    rc = _run_pytest_in_tmp(test_code, target, "add", task_metadata=_quixbugs_md())
    assert rc is not None and rc[0] == 0


def test_fallback_substring_when_metadata_absent() -> None:
    """metadata 缺省（detection_gates 委托）→ 子串回退保持（含子串走包分支）。"""
    target = "def add(a, b):\n    return a + b\n"
    test_code = "from python_programs.add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    rc = _run_pytest_in_tmp(test_code, target, "add")
    assert rc is not None and rc[0] == 0


def test_single_file_regression_unchanged() -> None:
    """单文件口径回归不变（无 metadata、无子串）。"""
    target = "def add(a, b):\n    return a + b\n"
    test_code = "from add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"
    rc = _run_pytest_in_tmp(test_code, target, "add", task_metadata=_synthetic_md())
    assert rc is not None and rc[0] == 0
