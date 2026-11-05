"""M1 包结构判分 fail-closed（R16，2026-10-08 R2）单元测试。

背景：
    历史口径下 QuixBugs 辅助材料（AITESTER_QUIXBUGS_DATA 指向的
    node.py / load_testdata.py / json_testcases）缺失时，"尽力而为"会把
    gold 测试的 import 失败（rc=2 收集错误）静默记成 repair=0 / detection=0
    ——"没跑起来"与"没修好/没检出"不可区分（假结论来源，第三起伪影的
    同源机制）。R16 改 fail-closed：材料缺失 → 记 None + logger.warning。

本测试锁定：
    1. 需要辅助模块（node/load_testdata）且支持根缺失 → 返回 None（非 0）；
    2. 支持根在但辅助文件缺失 → 返回 None；
    3. 自足包结构测试（不依赖辅助模块）在支持根缺失时**仍正常执行**
       （fail-closed 只作用于真正需要材料的测试，不误伤）。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from experiments._m1_metrics import _run_pytest_in_tmp

# 需要 QuixBugs 辅助模块的官方测试形态（node + load_testdata）
_QUIXBUGS_STYLE_TEST = (
    "from load_testdata import load_json_testcases\n"
    "from node import Node\n"
    "from python_programs.add import add\n"
    "\n"
    "\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
)

# 自足包结构测试（不依赖 node / load_testdata）
_SELF_CONTAINED_PACKAGE_TEST = "from python_programs.add import add\n\n\ndef test_add():\n    assert add(1, 2) == 3\n"


@pytest.fixture(autouse=True)
def _no_host_quixbugs_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """把「默认缓存目录」兜底指向空 tmp——模块级前提隔离。

    `_quixbugs_support_root()`（B1，2026-11-05）与 `QuixBugsDataset` 同源后多了一条
    默认缓存兜底；本文件所有"材料缺失"腿只 `delenv`，在作者机上会被
    `~/.cache/aitester/quixbugs` 里的真实数据满足 ⇒ 前提不成立、判定由机器历史
    决定（实测红 5 例）。兜底目录由夹具钉成空目录，`delenv` 才真的等于"没材料"。
    """
    import src.datasets.dataset_realbugs as realbugs

    empty = tmp_path / "empty_aitester_cache"
    empty.mkdir(exist_ok=True)
    monkeypatch.setattr(realbugs.QuixBugsDataset, "DEFAULT_CACHE_DIR", str(empty))


def _quixbugs_md() -> dict[str, Any]:
    return {"source": "quixbugs", "is_cross_file": False}


def test_missing_support_root_returns_none(monkeypatch, caplog) -> None:
    """支持根缺失 + 测试依赖辅助模块 → None（fail-closed），并记 warning。"""
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    target = "def add(a, b):\n    return a + b\n"
    with caplog.at_level(logging.WARNING, logger="experiments._m1_metrics"):
        rc = _run_pytest_in_tmp(_QUIXBUGS_STYLE_TEST, target, "add", task_metadata=_quixbugs_md())
    assert rc is None, "材料缺失应记 None（不误判为 0）"
    assert any("fail-closed" in r.message for r in caplog.records)


def test_missing_aux_files_returns_none(monkeypatch, tmp_path, caplog) -> None:
    """支持根存在但 node.py / load_testdata.py 缺失 → None。"""
    support = tmp_path / "quixbugs"
    (support / "python_testcases").mkdir(parents=True)
    monkeypatch.setenv("AITESTER_QUIXBUGS_DATA", str(support))
    target = "def add(a, b):\n    return a + b\n"
    with caplog.at_level(logging.WARNING, logger="experiments._m1_metrics"):
        rc = _run_pytest_in_tmp(_QUIXBUGS_STYLE_TEST, target, "add", task_metadata=_quixbugs_md())
    assert rc is None
    assert any("fail-closed" in r.message for r in caplog.records)


def test_self_contained_package_test_unaffected(monkeypatch) -> None:
    """自足包结构测试在支持根缺失时仍正常执行（不误伤）。"""
    monkeypatch.delenv("AITESTER_QUIXBUGS_DATA", raising=False)
    target = "def add(a, b):\n    return a + b\n"
    rc = _run_pytest_in_tmp(_SELF_CONTAINED_PACKAGE_TEST, target, "add", task_metadata=_quixbugs_md())
    assert rc is not None and rc[0] == 0
