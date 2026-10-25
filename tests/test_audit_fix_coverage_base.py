#!/usr/bin/env python3
"""`scripts/tools/audit_fix_coverage.py` 的基线解析判据（CS 轮，2026-10-26）。

## 为什么需要它

该工具的用途是「找出**修复新增但从未被测试执行**的代码行」——它是为捕捉
「修复覆盖主路径、漏掉分支路径」这类复发模式而写的。但它的默认 `--base` 写死在
V 轮起点 `ff15a2f`，距今 50+ 轮 ⇒ 默认跑出来的「新增行」几乎覆盖整个 `src/`，
输出是「整仓未覆盖」的**噪声**（实测：几十个文件的未覆盖计数全为 0 命中），
没有诊断价值——这正是它长期无人跑、也无人给它读者（未进 Makefile / README / CI）
的主因。

CS 轮把默认基线改为 `auto`：**最近一次改动审计范围的提交**，即「本次修复」的
语义化起点。本锁覆盖：

1. `auto` ⇒ 最近改动 `pathspec` 的提交；
2. 显式提交号原样透传；
3. 解析不出（无该路径历史）⇒ 明确报错，**不静默回落到写死的历史提交**；
4. `audit()` 内部同样走解析路径（CLI 与测试共用一条实现）。

测试用 tmp_path 造微型 git 仓库，不依赖真实仓库历史。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "audit_fix_coverage.py"
_spec = importlib.util.spec_from_file_location("_audit_fix_coverage", _SCRIPT)
assert _spec and _spec.loader
fix_mod = importlib.util.module_from_spec(_spec)
sys.modules["_audit_fix_coverage"] = fix_mod
_spec.loader.exec_module(fix_mod)


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def _make_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """造一个有两提交的微型仓库：第一次建 src/，第二次改 src/。"""
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    first = _git(root, "rev-parse", "HEAD")
    (root / "src" / "a.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "second")
    second = _git(root, "rev-parse", "HEAD")
    return root, first, second


def test_auto_base_is_latest_commit_touching_pathspec(tmp_path):
    """auto ⇒ 最近一次改动 src/ 的提交。"""
    root, _first, second = _make_repo(tmp_path)
    assert fix_mod.resolve_base("auto", root, "src/") == second


def test_auto_base_respects_pathspec(tmp_path):
    """auto 对不同 pathspec 取各自的最近改动提交（不是全仓最近提交）。"""
    root, first, second = _make_repo(tmp_path)
    (root / "docs").mkdir()
    (root / "docs" / "d.md").write_text("d\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "docs only")
    docs_sha = _git(root, "rev-parse", "HEAD")
    assert fix_mod.resolve_base("auto", root, "src/") == second
    assert fix_mod.resolve_base("auto", root, "docs/") == docs_sha
    assert first != docs_sha


def test_explicit_base_passes_through(tmp_path):
    """显式提交号原样透传（不参与 auto 解析）。"""
    root, first, _second = _make_repo(tmp_path)
    assert fix_mod.resolve_base(first, root, "src/") == first


def test_unresolvable_base_returns_empty_and_audit_raises(tmp_path):
    """解析不出 ⇒ 明确报错，不静默回落到写死的历史提交。"""
    root = tmp_path / "empty"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "keep.txt").write_text("k\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "only docs"], cwd=root, check=True)
    assert fix_mod.resolve_base("auto", root, "src/") == ""
    with pytest.raises(ValueError):
        fix_mod.audit("auto", root / "coverage.xml", root, "src/")


def test_default_base_is_auto():
    """默认基线必须是 auto——写死的历史提交会随轮次漂移成噪声。"""
    assert fix_mod.DEFAULT_BASE == "auto"
