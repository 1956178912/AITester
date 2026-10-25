"""CY 轮（2026-10-26）：远端定时作业巡检守卫 `scripts/gates/check_scheduled_workflows.py` 的回归锁。

纪律：**零 LLM、$0**。判定分两类：
  - 规则面（合成运行记录，不打网络）：红/绿的判定形状；
  - 接线面（真实树）：这道门**有人在跑**吗？登记**完整**吗？

为什么这道门必须存在（本轮实测的事实）：

- `perf.yml` 的定时作业在 2026-10-11 / 10-18 / 10-25 **连续三次红**（根因是构造期
  要凭据），`mutation.yml` 的定时作业 2026-10-19 红（`score=0.7500 < 0.8500`）。
- 两者的修复（CO 轮 `2d594419` / CQ 轮）都**晚于**最后一次红 ⇒ 修复从未被远端跑过。
- CI 只在 PR/push 上跑；定时作业是**另一条链**；本地复现用的是开发机环境
  （有 `.env`、有 venv），而定时作业跑的是**裸 requirements + 无凭据**的 runner。
- ⇒ 「定时作业红」这件事，在本项目里**没有任何机制能发现**。CQ 轮把教训写进了
  `docs/MEASUREMENT_INTEGRITY.md`，但一直没固化成工具——本文件就是那次固化。

判定形状（**关键**）：最近一次定时运行是红的，但**存在更新的、成功的
`workflow_dispatch` 运行** ⇒ 判绿——因为「收口声明必须绑定一次真跑」，一次在真实
runner 上成功的手动运行就是那次真跑。反之（更新的手动运行也红 / 没有手动运行）⇒ 判红。

分组：A 规则面 8 例 / B 接线面 3 例。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = PROJECT_ROOT / "scripts" / "gates" / "check_scheduled_workflows.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("_check_scheduled_workflows", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_check_scheduled_workflows"] = module
    spec.loader.exec_module(module)
    return module


gate = _load()


def _run(conclusion: str, run_id: int = 1, created_at: str = "2026-10-25T00:00:00Z") -> dict[str, Any]:
    return {
        "id": run_id,
        "status": "completed",
        "conclusion": conclusion,
        "created_at": created_at,
    }


def _pending(run_id: int = 9) -> dict[str, Any]:
    return {"id": run_id, "status": "in_progress", "conclusion": None, "created_at": "2026-10-26T00:00:00Z"}


class TestScheduledWorkflowRules:
    """A 组：规则面——红/绿的判定形状。"""

    @pytest.fixture()
    def fake_tree(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        """一个只含单个工作流的假仓库目录（cron 自洽面用）。"""
        wf_dir = tmp_path / ".github" / "workflows"
        wf_dir.mkdir(parents=True)
        (wf_dir / "perf.yml").write_text('on:\n  schedule:\n    - cron: "30 7 * * 0"\njobs: {}\n', encoding="utf-8")
        monkeypatch.setattr(gate, "WORKFLOW_DIR", wf_dir)
        monkeypatch.setattr(gate, "REGISTRY", {"perf.yml": "30 7 * * 0"})
        monkeypatch.setattr(gate, "_repo_slug", lambda: "owner/repo")
        return tmp_path

    def _patch_runs(self, monkeypatch: pytest.MonkeyPatch, *, schedule: list, dispatch: list) -> None:
        def fake_list_runs(slug: str, workflow: str, event: str) -> list:
            return schedule if event == "schedule" else dispatch

        monkeypatch.setattr(gate, "list_runs", fake_list_runs)

    def test_green_when_scheduled_run_succeeded(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._patch_runs(monkeypatch, schedule=[_run("success")], dispatch=[])
        assert gate.main([]) == 0

    def test_green_when_newer_dispatch_succeeded(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """定时红 + **更新的**手动绿 ⇒ 绿（修复已在真实 runner 上验证过）。"""
        self._patch_runs(
            monkeypatch,
            schedule=[_run("failure", 1, "2026-10-19T00:00:00Z")],
            dispatch=[_run("success", 2, "2026-10-25T00:00:00Z")],
        )
        assert gate.main([]) == 0

    def test_red_when_dispatch_also_failed(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """定时红 + 更新的手动也红 ⇒ 红。"""
        self._patch_runs(
            monkeypatch,
            schedule=[_run("failure", 1, "2026-10-19T00:00:00Z")],
            dispatch=[_run("failure", 2, "2026-10-25T00:00:00Z")],
        )
        assert gate.main([]) == 1

    def test_red_when_no_dispatch_at_all(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """定时红 + 从未手动跑过 ⇒ 红（「修复没人验证过」不算修好）。"""
        self._patch_runs(monkeypatch, schedule=[_run("failure")], dispatch=[])
        assert gate.main([]) == 1

    def test_pending_dispatch_does_not_hide_a_red_schedule(
        self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """正在跑的手动运行不算「更新且成功」⇒ 仍按定时红判红。"""
        self._patch_runs(
            monkeypatch,
            schedule=[_run("failure", 1, "2026-10-19T00:00:00Z")],
            dispatch=[_pending(2)],
        )
        assert gate.main([]) == 1

    def test_api_unreachable_is_skip_not_failure(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """API 不可达 ⇒ [SKIP] 带成因（环境性前提），**不得**判红也不得谎报通过。"""

        def boom(slug: str, workflow: str, event: str) -> list:
            raise RuntimeError("GitHub API 不可达（测试注入）")

        monkeypatch.setattr(gate, "list_runs", boom)
        assert gate.main([]) == 0

    def test_unlisted_scheduled_workflow_fails(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """盘上有 schedule 触发器却没登记 ⇒ 红（漏登 = 没人知道它红）。"""
        wf_dir = fake_tree / ".github" / "workflows"
        (wf_dir / "secret.yml").write_text('on:\n  schedule:\n    - cron: "0 1 * * 1"\njobs: {}\n', encoding="utf-8")
        self._patch_runs(monkeypatch, schedule=[_run("success")], dispatch=[])
        assert gate.main([]) == 1

    def test_cron_mismatch_fails(self, fake_tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """登记的 cron 与工作流文件里的不一致 ⇒ 红（登记面自己漂移了）。"""
        monkeypatch.setattr(gate, "REGISTRY", {"perf.yml": "0 9 * * 0"})
        self._patch_runs(monkeypatch, schedule=[_run("success")], dispatch=[])
        assert gate.main([]) == 1


class TestScheduledWorkflowWiring:
    """B 组：接线面——这道门有人在跑吗？登记完整吗？"""

    def test_real_registry_covers_every_scheduled_workflow(self) -> None:
        """真实树：每个带 schedule 触发器的工作流都必须登记（漏登 ⇒ 判红）。"""
        on_disk = gate.scheduled_workflow_files()
        assert on_disk, "盘上应当至少有一个带 schedule 触发器的工作流"
        missing = [name for name in on_disk if name not in gate.REGISTRY]
        assert missing == [], f"未登记的定时工作流：{missing}"

    def test_real_registry_cron_matches_workflow_files(self) -> None:
        """真实树：登记的 cron 必须与工作流文件逐字一致。"""
        for name, declared in gate.REGISTRY.items():
            path = PROJECT_ROOT / ".github" / "workflows" / name
            assert path.is_file(), f"登记的 {name} 不存在"
            actual = gate.workflow_cron(path)
            assert actual == declared, f"{name}: 盘上 {actual!r} ≠ 登记 {declared!r}"

    def test_gate_is_in_the_makefile_gates_chain(self) -> None:
        """「写了没人跑」是本项目反复出现的病症：必须进 `make gates` 链。"""
        makefile = (PROJECT_ROOT / "Makefile").read_text(encoding="utf-8")
        assert "scheduled-workflows:" in makefile
        assert "scripts/gates/check_scheduled_workflows.py" in makefile
        chain = next(line for line in makefile.splitlines() if line.startswith("gates:"))
        assert "scheduled-workflows" in chain

    def test_gate_is_wired_into_ci(self) -> None:
        """必须进 CI（否则远端定时作业红时，PR 流水线不会知道）。"""
        ci = (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        assert "scripts/gates/check_scheduled_workflows.py" in ci

    def test_list_switch_is_readable(self, capsys: pytest.CaptureFixture[str]) -> None:
        """`--list` 必须真参与调度（CG 门判「判据档无读者即红」，本文件即该开关的代码锁）。"""
        assert gate.main(["--list"]) in (0, 1)  # 判定面照常跑，不因 --list 改语义
        out = capsys.readouterr().out
        assert "登记表" in out
        assert "perf.yml" in out
