"""EZ（2026-10-27）语料形状锁的判定面回归锁。

缺陷族：三个形状锁（AR / AQ 两个模块）把「文件数 / span 总数 / token 属性数」
钉在**盘面**读数上（`root.rglob("*.trace.jsonl")`），而语料的**入库面**只有盘面
的一半——`experiments/results/**` 按 Zenodo 纪律不入库，只有 pinned 批次被
`git add -f`。于是同一份锁在两种环境下都不判定：

- 作者机：盘面随本地重跑增长（实测 1,456 → 1,495 份 / 9,502 → 9,658 span），
  钉值必然过期 ⇒ 必红；
- fresh clone：`require_full_corpus()` 的盘面下界（1,456）达不到 ⇒ 显式 skip。

锁定口径：
1. 形状断言的判定面 = `archived_trace_files()`（`git ls-files` ∩ 盘面）；
2. 本地未入库语料（`local_extra_trace_files()`）只跑不变量，不进形状分母；
3. git 不可用 ⇒ 不降级到盘面，显式 skip（「入库面」不得被偷换成「盘面」）；
4. 仍以全归档为前提的锁必须登记进 `AUTHOR_ONLY_LOCKS`（带理由），新增未登记
   作者机专属锁即红。
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from tests._corpus_guard import (
    ARCHIVED_SPANS,
    ARCHIVED_TOKEN_ATTRS,
    ARCHIVED_TOKEN_FIELD_CHECKS,
    ARCHIVED_TRACE_FILES,
    AUTHOR_ONLY_LOCKS,
    archived_trace_files,
    disk_trace_files,
    local_extra_trace_files,
    shape_problem,
)

_TESTS_DIR = Path(__file__).resolve().parent


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _synthetic_repo(tmp_path: Path) -> Path:
    """两个入库 trace + 一个未入库（被 ignore）trace 的最小仓库。"""
    repo = tmp_path / "repo"
    (repo / "results" / "a").mkdir(parents=True)
    (repo / "results" / "b").mkdir(parents=True)
    (repo / "results" / "extra").mkdir(parents=True)
    (repo / ".gitignore").write_text("results/extra/\n", encoding="utf-8")
    (repo / "results" / "a" / "a.trace.jsonl").write_text("{}\n", encoding="utf-8")
    (repo / "results" / "b" / "b.trace.jsonl").write_text("{}\n", encoding="utf-8")
    (repo / "results" / "extra" / "c.trace.jsonl").write_text("{}\n", encoding="utf-8")
    _git(repo, "init")
    _git(repo, "add", ".gitignore", "results/a/a.trace.jsonl", "results/b/b.trace.jsonl")
    return repo


def test_tracked_surface_excludes_local_extras(tmp_path):
    """入库面 = git ls-files ∩ 盘面：本地未入库语料不得进入形状分母。"""
    repo = _synthetic_repo(tmp_path)
    archived = archived_trace_files(repo)
    extras = local_extra_trace_files(repo)
    assert [p.name for p in archived] == ["a.trace.jsonl", "b.trace.jsonl"], archived
    assert [p.name for p in extras] == ["c.trace.jsonl"], extras
    assert len(disk_trace_files(repo)) == 3


def test_git_unavailable_is_a_skip_not_a_disk_fallback(tmp_path):
    """git 不可用 ⇒ 显式 skip；不得把「入库面」偷换成「盘面」。"""
    not_a_repo = tmp_path / "plain"
    not_a_repo.mkdir()
    (not_a_repo / "x.trace.jsonl").write_text("{}\n", encoding="utf-8")
    with pytest.raises(pytest.skip.Exception):
        archived_trace_files(not_a_repo)


def test_archived_and_extra_partition_the_disk_surface():
    """盘面 = 入库面 ∪ 未入库面，且两侧互斥（形状分母不会重复计数）。"""
    archived = set(archived_trace_files())
    extras = set(local_extra_trace_files())
    assert not archived & extras
    assert archived | extras == set(disk_trace_files())


def test_shape_pins_are_reachable_on_the_archived_surface():
    """钉值必须在入库面成立——这正是旧口径做不到的事（作者机必红 / CI 必 skip）。"""
    archived = archived_trace_files()
    assert not shape_problem(len(archived), ARCHIVED_TRACE_FILES, "入库 trace 文件数")
    assert ARCHIVED_SPANS > 0 and ARCHIVED_TOKEN_ATTRS > 0 and ARCHIVED_TOKEN_FIELD_CHECKS > 0


def test_shape_problem_reports_drift_with_both_numbers():
    """负向对照：不一致时必须报出两个数，并点名判定面。"""
    problem = shape_problem(1, ARCHIVED_TRACE_FILES, "入库 trace 文件数")
    assert "1" in problem and str(ARCHIVED_TRACE_FILES) in problem
    assert "git ls-files" in problem
    assert shape_problem(ARCHIVED_TRACE_FILES, ARCHIVED_TRACE_FILES, "入库 trace 文件数") == ""


def _require_full_corpus_sites() -> set[str]:
    sites: set[str] = set()
    for path in sorted(_TESTS_DIR.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "require_full_corpus":
                sites.add(f"tests/{path.name}")
    return sites


def test_author_only_registry_covers_every_call_site():
    """作者机专属锁必须逐条登记：「CI 里永不执行」不得是新增测试的默认形态。"""
    registered = {path for path, _reason in AUTHOR_ONLY_LOCKS}
    assert _require_full_corpus_sites() == registered, (
        "作者机专属锁登记表与调用点不一致——新增的 require_full_corpus() 调用点"
        "要么改判入库面（archived_trace_files），要么在 AUTHOR_ONLY_LOCKS 写明理由"
    )


def test_author_only_entries_carry_reasons_and_exist():
    for path, reason in AUTHOR_ONLY_LOCKS:
        assert (_TESTS_DIR.parent / path).is_file(), f"登记表指向不存在的文件：{path}"
        assert len(reason.strip()) >= 20, f"{path} 的理由过短（登记≠通行）：{reason!r}"
