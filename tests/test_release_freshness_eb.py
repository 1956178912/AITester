"""EB 轮（2026-10-27）：发布新鲜度门的**例外登记判定面**回归锁。

CZ 轮把门禁立起来了，也锁了「未登记落后 ⇒ 红」与「登记不再对应最新 tag ⇒ 红」——
但后者只在**最新 tag 未登记**的分支里可达：

    if tag_name in allowlist:
        print(✅)
        return 0          # ← 失效条目检查在这里之后
    stale = [name for name in allowlist if name != tag_name]

于是登记表同时含「当前最新 tag」与「旧 tag」时，门禁照样绿；登记表写了
一个**没有理由**的条目（表头承诺「例外必须写理由」）也照样绿；仓库连
`v*` tag 都没有、登记表却留着条目时，走 `[SKIP]` 同样绿。判定面在读登记
表时只读「当前 tag 在不在表里」，表头声明的两条语法承诺没有读者。

本文件锁两类事实：
  1. 登记表的两条语法承诺（理由非空 / 条目对应当前最新 tag）在**任何**
     绿色分支之前生效——tag 落后、tag == HEAD、无 tag 三种状态都不豁免；
  2. 既有绿色契约不变：当前 tag 已登记且落后仍绿（显式承担），并打印
     落后提交数；无 tag 且登记表为空仍 `[SKIP]`；`--list` 只打印不改变判定。

零网络：全部走合成 API 响应。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_release_freshness.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_check_release_freshness_eb", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_release_freshness_eb"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


def _patch(monkeypatch: pytest.MonkeyPatch, *, tags: list, head: str, ahead: int) -> None:
    """把 API 响应换成合成值（零网络）。"""

    def fake_api(path: str) -> Any:
        if "/tags" in path:
            return tags
        if "/compare/" in path:
            return {"ahead_by": ahead, "status": "ahead"}
        if "/commits/" in path:
            return {"sha": head}
        return {"default_branch": "main"}

    monkeypatch.setattr(gate, "_api_get", fake_api)
    monkeypatch.setattr(gate, "_repo_slug", lambda: "owner/repo")


def _allow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, text: str) -> Path:
    path = tmp_path / "allow.txt"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(gate, "ALLOWLIST", path)
    return path


# ───────────────────── A. 登记语法承诺在任何绿色之前 ─────────────────────


class TestRegistrationJudgment:
    def test_stale_entry_reds_even_when_current_tag_is_registered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """当前 tag 已登记 + 旧条目：旧条目已失效 ⇒ 红，不因当前条目合法而豁免。"""
        _allow(tmp_path, monkeypatch, "v1.1.0  # 当前 tag，等作者同意前移\nv1.0.0  # 旧 tag\n")
        _patch(monkeypatch, tags=[{"name": "v1.1.0", "commit": {"sha": "abc"}}], head="def", ahead=3)
        assert gate.main([]) == 1
        out = capsys.readouterr().out
        assert "例外登记无效" in out
        assert "v1.0.0" in out
        assert "失效" in out

    def test_stale_entry_reds_even_when_tag_is_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """tag == HEAD 时失效条目同样是登记面缺陷——不因「新鲜」而豁免。"""
        _allow(tmp_path, monkeypatch, "v1.0.0  # 当前 tag\nv0.9.0  # 旧 tag\n")
        _patch(monkeypatch, tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}], head="abc", ahead=0)
        assert gate.main([]) == 1
        out = capsys.readouterr().out
        assert "v0.9.0" in out
        assert "例外登记无效" in out

    def test_reasonless_entry_is_red(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """表头承诺「例外必须写理由」：无理由条目不得算作显式承担。"""
        _allow(tmp_path, monkeypatch, "v1.1.0\n")
        _patch(monkeypatch, tags=[{"name": "v1.1.0", "commit": {"sha": "abc"}}], head="def", ahead=3)
        assert gate.main([]) == 1
        out = capsys.readouterr().out
        assert "v1.1.0" in out
        assert "理由" in out

    def test_no_release_tag_but_registered_entry_is_red(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """仓库没有任何 `v*` tag，登记表却留着条目：登记没有对应对象 ⇒ 红。"""
        _allow(tmp_path, monkeypatch, "v1.0.0  # 旧 tag\n")
        _patch(monkeypatch, tags=[{"name": "nightly", "commit": {"sha": "abc"}}], head="abc", ahead=0)
        assert gate.main([]) == 1
        out = capsys.readouterr().out
        assert "v1.0.0" in out
        assert "例外登记无效" in out

    def test_multiple_problems_are_all_listed(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """一次登记里同时存在失效条目与无理由条目：两条都要点名，不遮蔽后一条。"""
        _allow(tmp_path, monkeypatch, "v1.1.0\nv1.0.0  # 旧 tag\n")
        _patch(monkeypatch, tags=[{"name": "v1.1.0", "commit": {"sha": "abc"}}], head="def", ahead=3)
        assert gate.main([]) == 1
        out = capsys.readouterr().out
        assert out.count("[release-freshness]   - ") == 2
        assert "理由" in out

    def test_list_switch_does_not_change_judgment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """`--list` 只打印登记（不改变判定）：失效条目照样红。"""
        _allow(tmp_path, monkeypatch, "v1.1.0  # 当前 tag\nv1.0.0  # 旧 tag\n")
        _patch(monkeypatch, tags=[{"name": "v1.1.0", "commit": {"sha": "abc"}}], head="def", ahead=3)
        assert gate.main(["--list"]) == 1
        out = capsys.readouterr().out
        assert "例外登记：" in out
        assert "v1.0.0：旧 tag" in out
        assert "v1.1.0：当前 tag" in out


# ───────────────────── B. 既有绿色/跳过契约不变 ─────────────────────


class TestExistingContracts:
    def test_registered_current_tag_still_green_with_ahead_count(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """当前 tag 已登记且落后：绿，且必须打印落后多少个提交（显式承担不是沉默）。"""
        _allow(tmp_path, monkeypatch, "v1.1.0  # 等作者同意前移 tag\n")
        _patch(monkeypatch, tags=[{"name": "v1.1.0", "commit": {"sha": "abc"}}], head="def", ahead=7)
        assert gate.main([]) == 0
        out = capsys.readouterr().out
        assert "落后 7 个提交" in out
        assert "已登记例外" in out

    def test_tag_at_head_with_reasoned_entry_is_green(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """tag == HEAD 且登记表只含当前 tag：绿（无失效条目）。"""
        _allow(tmp_path, monkeypatch, "v1.0.0  # 当前 tag\n")
        _patch(monkeypatch, tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}], head="abc", ahead=0)
        assert gate.main([]) == 0

    def test_no_tag_with_empty_registration_is_skip(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """没有 release tag 且没有登记：`[SKIP]`（还没发过版，不是缺陷）。"""
        _patch(monkeypatch, tags=[{"name": "nightly", "commit": {"sha": "abc"}}], head="abc", ahead=0)
        monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "none.txt")
        assert gate.main([]) == 0
        assert "[SKIP]" in capsys.readouterr().out
