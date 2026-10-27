"""CZ 轮（2026-10-26）：发布新鲜度守卫 `scripts/gates/check_release_freshness.py` 的回归锁。

纪律：**零 LLM、$0**。判定分两类：
  - 规则面（合成 API 响应，不打网络）：红/绿/失效例外的判定形状；
  - 接线面（真实树）：这道门**有人在跑**吗？当前的 tag 落后**登记**了吗？

为什么需要这道门（本轮实测的事实）：`v1.0.0` tag 指向 `dc8285d3`，而 main 已到
`23b35b00`——**36 个提交**没有进入「已发布的 1.0.0」，其中包含 perf 定时作业的构造期
凭据修复、自变异 harness 的沙箱依赖闭包修复、投稿页数测量源的四道守卫与两道新门禁。
**tag 指向的树就是发布产物的来源**（`release.yml` 由 `v*` tag push 触发并检出被标记的
提交）⇒ tag 落后 = 发布的产物缺修复。而「要不要前移 tag」是**作者的决定**（force-update
属外部动作）⇒ 这道门**不能**自作主张改 tag，但**必须**让这个事实在 CI 里**可见**，
否则它只活在某个人的记忆里。

判定形状：
  - tag == HEAD ⇒ 绿；
  - tag 落后且**已登记** ⇒ 绿（显式承担），但必须打印落后多少个提交；
  - tag 落后且**未登记** ⇒ 红；
  - 登记的 tag **不再对应当前最新 tag** ⇒ 例外已失效 ⇒ 红；
  - 没有 `v*` tag ⇒ `[SKIP]`（项目还没发过版，不是缺陷）。

分组：A 规则面 6 例 / B 接线面 3 例。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_release_freshness.py"
ALLOWLIST = PROJECT_ROOT / "docs" / "release_freshness_allowlist.txt"


def _local_gap() -> tuple[str | None, int]:
    """本地判定「最新 v* tag 落后 HEAD 多少提交」（不打网络）。

    与门禁的 API 判定同一事实、两条实现：门禁问的是远端最新 release，本地问的是
    本地 tag；tag 已前移时两者都应为 0。
    """
    tag = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "tag", "--sort=-v:refname", "--list", "v*"],
        capture_output=True,
        text=True,
    )
    names = [line for line in tag.stdout.splitlines() if line.strip()]
    if tag.returncode != 0 or not names:
        return None, 0
    latest = names[0].strip()
    count = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-list", "--count", f"{latest}..HEAD"],
        capture_output=True,
        text=True,
    )
    if count.returncode != 0:
        return latest, 0
    return latest, int(count.stdout.strip() or "0")


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_check_release_freshness", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_release_freshness"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


def _patch(monkeypatch: pytest.MonkeyPatch, *, tags: list, head: str, ahead: int) -> None:
    """把 API 响应换成合成值。"""

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


class TestReleaseFreshnessRules:
    """A 组：规则面。"""

    def test_tag_at_head_is_green(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch(monkeypatch, tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}], head="abc", ahead=0)
        monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "none.txt")
        assert gate.main([]) == 0

    def test_unregistered_stale_tag_is_red(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """落后且未登记 ⇒ 红（发布产物缺修复，不能沉默）。"""
        _patch(monkeypatch, tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}], head="def", ahead=36)
        monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "none.txt")
        assert gate.main([]) == 1

    def test_registered_stale_tag_is_green(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """落后但**已登记** ⇒ 绿（显式承担），且必须打印落后多少个提交。"""
        allow = tmp_path / "allow.txt"
        allow.write_text("v1.0.0  # 因为需要作者同意前移 tag\n", encoding="utf-8")
        _patch(monkeypatch, tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}], head="def", ahead=36)
        monkeypatch.setattr(gate, "ALLOWLIST", allow)
        assert gate.main([]) == 0

    def test_stale_allowlist_entry_is_red(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """登记的 tag 不再是最新 tag ⇒ 例外**已失效** ⇒ 红（tag 前移后必须清理登记）。"""
        allow = tmp_path / "allow.txt"
        allow.write_text("v0.9.0  # 旧 tag\n", encoding="utf-8")
        _patch(monkeypatch, tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}], head="def", ahead=3)
        monkeypatch.setattr(gate, "ALLOWLIST", allow)
        assert gate.main([]) == 1

    def test_no_release_tag_is_skip(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """没有 `v*` tag ⇒ `[SKIP]`（还没发过版，不是缺陷）。"""
        _patch(monkeypatch, tags=[{"name": "nightly", "commit": {"sha": "abc"}}], head="abc", ahead=0)
        monkeypatch.setattr(gate, "ALLOWLIST", tmp_path / "none.txt")
        assert gate.main([]) == 0

    def test_allowlist_parser_ignores_comments_and_blanks(self, tmp_path: Path) -> None:
        """登记解析：空行与整行注释忽略；理由取 `#` 之后的部分。"""
        allow = tmp_path / "allow.txt"
        allow.write_text("# 说明\n\nv1.0.0  # 因为需要作者同意\nv0.9.0  # 更早\n", encoding="utf-8")
        monkeypatch_path = allow
        original = gate.ALLOWLIST
        gate.ALLOWLIST = monkeypatch_path
        try:
            entries = gate.load_allowlist()
        finally:
            gate.ALLOWLIST = original
        assert entries == {"v1.0.0": "因为需要作者同意", "v0.9.0": "更早"}


class TestReleaseFreshnessWiring:
    """B 组：接线面。"""

    def test_gate_is_in_the_makefile_gates_chain(self) -> None:
        """「写了没人跑」是本项目反复出现的病症：必须进 `make gates` 链。"""
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "release-freshness:" in makefile
        assert "scripts/gates/check_release_freshness.py" in makefile
        chain = next(line for line in makefile.splitlines() if line.startswith("gates:"))
        assert "release-freshness" in chain

    def test_gate_is_wired_into_ci(self) -> None:
        """必须进 CI（否则远端树照样能带着过期的发布产物）。"""
        ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "scripts/gates/check_release_freshness.py" in ci

    def test_current_tag_gap_is_registered(self) -> None:
        """落后必须登记；**不落后时例外表必须为空**（EZ 轮：前移后旧断言自我矛盾）。

        旧版断言 `entries` 非空，而失败消息自己写着「若当前 tag 已不落后，应当删除该表
        并让门禁自行判定」——两个方向互相打架：一旦作者前移 tag，本锁必红。现按本地
        落后数分两支判，两个方向都咬人。
        """
        assert ALLOWLIST.is_file(), "缺少 docs/release_freshness_allowlist.txt"
        entries = gate.load_allowlist()
        tag, gap = _local_gap()
        if gap <= 0:
            assert entries == {}, f"当前 tag 不落后（{tag}），例外表应为空，实际：{sorted(entries)}"
            return
        assert tag in entries, f"{tag} 落后 HEAD {gap} 个提交，但未登记例外"
        for name, reason in entries.items():
            assert reason, f"{name} 的例外登记没有写理由"

    def test_list_switch_is_readable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`--list` 必须真参与调度（CG 门判「判据档无读者即红」，本文件即该开关的代码锁）。"""
        allow = tmp_path / "allow.txt"
        allow.write_text("v1.0.0  # 因为需要作者同意前移 tag\n", encoding="utf-8")
        monkeypatch.setattr(gate, "ALLOWLIST", allow)
        _patch(
            monkeypatch,
            tags=[{"name": "v1.0.0", "commit": {"sha": "abc"}}],
            head="def",
            ahead=36,
        )
        assert gate.main(["--list"]) == 0
