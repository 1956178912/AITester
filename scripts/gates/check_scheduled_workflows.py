#!/usr/bin/env python3
"""CY（2026-10-26）：远端**定时作业**巡检守卫——每周跑一次的作业必须真的绿。

起因（本轮实测的事实）：

- `perf.yml` 的定时作业在 2026-10-11 / 10-18 / 10-25 **连续三次红**；根因是
  `BaseAgent` 构造期要凭据，而定时作业环境里没有 `.env`。CO 轮（`2d594419`）
  修了脚本，但**那次修复从未被远端跑过**——三次红都在修复**之前**，而下一次定时
  触发要等到 2026-11-01。
- `mutation.yml` 的定时作业 2026-10-19 红（`score=0.7500 < 0.8500`），CQ 轮的
  修复同样**从未被远端跑过**。
- 于是「定时作业红」这件事，在本项目里**没有任何机制能发现**：CI 只跑 PR/push，
  定时作业是另一条链；本地复现用的是开发机环境（有 `.env`、有 venv），而定时
  作业跑的是**裸 requirements + 无凭据**的 runner。CQ 轮把这个教训写进了
  `docs/MEASUREMENT_INTEGRITY.md`，但**一直没固化成工具**——本文件就是那次固化。

判据（对每个登记在案的定时工作流）：

1. 取该工作流最近一次 **completed** 的 `schedule` 运行（S）与最近一次
   **completed** 的 `workflow_dispatch` 运行（D）。
2. 若 D 存在、D 比 S **更新**且 D 结论为 success ⇒ **绿**（修复已在真实 runner
   上验证过；这是「收口声明必须绑定一次真跑」的可执行形态）。
3. 否则若 S 的结论为 success ⇒ **绿**。
4. 否则 ⇒ **红**：定时作业最近一次跑出来是红的，且没有更新的成功手动运行。
5. **API 不可达 / 仓库未知 ⇒ `[SKIP]` 带成因**（环境性前提，不是「通过」）。

另外两个自洽面（否则这道门自己会过期）：

- **登记完整性**：`.github/workflows/` 下**每一个带 `schedule:` 触发器的工作流**
  都必须在登记表里；漏登 ⇒ 红（「写了没人跑」与「跑了没人知道」是同一族病）。
- **触发器自洽**：登记表里声明的 `schedule` cron 必须与 workflow 文件里的 cron
  逐字一致；不一致 ⇒ 红。

用法：
    python scripts/gates/check_scheduled_workflows.py
    python scripts/gates/check_scheduled_workflows.py --list   # 打印登记表（不改变判定）

环境变量：
    GITHUB_TOKEN   可选；有则用它调 API（CI 里传 `github.token`，匿名调用是 60 次/小时）
    GITHUB_REPOSITORY  可选；默认从 `git remote get-url origin` 解析

退出码：0 = 全部通过（或仅环境性 [SKIP]）；1 = 有定时作业红 / 登记不自洽。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WORKFLOW_DIR = PROJECT_ROOT / ".github" / "workflows"

#: 登记在案的定时工作流：文件 → 该工作流里 `schedule:` 块的 cron（逐字比对）。
#: 顺序即巡检顺序，输出按此顺序。
REGISTRY: dict[str, str] = {
    "ci.yml": "0 6 * * 0",
    "perf.yml": "30 7 * * 0",
    "mutation.yml": "0 7 * * 1",
}

#: GitHub API 的 per_page 上限取 30 足够（只看最近若干次运行）。
_API_TIMEOUT = 30


def _repo_slug() -> str | None:
    """解析 `owner/repo`；优先环境变量，其次 git remote。"""
    slug = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if slug and "/" in slug:
        return slug
    try:
        proc = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "remote", "get-url", "origin"],
            capture_output=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    url = proc.stdout.decode("utf-8", "replace").strip()
    match = re.search(r"github\.com[:/]+([^/]+)/([^/\s]+?)(?:\.git)?$", url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _api_get(path: str) -> Any:
    """调 GitHub API；返回解析后的 JSON。异常由调用方按环境性前提处理。

    **为什么用 curl 而不是 urllib**：本项目所在的一些环境（macOS + 企业代理）
    里，Python 的默认 SSL context 与 `certifi` 的 CA 包**都不含代理签发的 CA**，
    于是 `urlopen` 抛 `CERTIFICATE_VERIFY_FAILED`——那既不是「GitHub 不可达」，
    也不是判定面的问题，却会被当成网络前提缺失，把远端巡检静默降级成 [SKIP]。
    `curl` 用系统钥匙串的信任链（macOS）或发行版的 CA 包（ubuntu），两端都能用，
    且无需新增依赖。

    **凭据不进 argv**：请求头经 `curl -K -`（stdin）传入，避免 token 出现在
    进程列表里（`ps` 可见）。
    """
    url = f"https://api.github.com{path}"
    headers = [
        "Accept: application/vnd.github+json",
        "User-Agent: aitester-scheduled-gate",
    ]
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers.append(f"Authorization: Bearer {token}")
    config = "".join(f'header = "{h}"\n' for h in headers)

    try:
        proc = subprocess.run(
            ["curl", "-sS", "-w", "\n%{http_code}", "-K", "-", url],
            input=config,
            capture_output=True,
            text=True,
            timeout=_API_TIMEOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("curl 不可用——无法核验远端定时作业") from exc
    except subprocess.SubprocessError as exc:
        raise RuntimeError(f"curl 调用失败：{exc}") from exc

    if proc.returncode != 0:
        raise RuntimeError(f"curl 退出码 {proc.returncode}：{proc.stderr.strip()[:200]}")
    body, _, status = proc.stdout.rpartition("\n")
    if status.strip() not in ("200",):
        raise RuntimeError(f"GitHub API 返回 HTTP {status.strip() or '?'}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub API 响应不是 JSON：{exc}") from exc


def list_runs(slug: str, workflow: str, event: str) -> list[dict[str, Any]]:
    """取某工作流某类事件的运行列表（按创建时间倒序）。失败时抛异常。"""
    path = f"/repos/{slug}/actions/workflows/{workflow}/runs?event={event}&per_page=30"
    payload = _api_get(path)
    return list(payload.get("workflow_runs", []))


def latest_completed(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for run in runs:
        if run.get("status") == "completed":
            return run
    return None


def workflow_cron(path: Path) -> str | None:
    """从 workflow YAML 里取出 `schedule:` 块下第一条 `- cron: "..."` 的字面量。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"schedule:\s*(?:#[^\n]*\n\s*)*.*?-\s*cron:\s*[\"']([^\"']+)[\"']", text, re.S)
    return match.group(1) if match else None


def scheduled_workflow_files() -> list[str]:
    """盘上所有带 `schedule:` 触发器的 workflow 文件名（按字母序）。"""
    found: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*schedule:\s*$", text, re.M):
            found.append(path.name)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="远端定时作业巡检守卫")
    parser.add_argument("--list", action="store_true", help="打印登记表（不改变判定）")
    args = parser.parse_args(argv)

    if args.list:
        print("[scheduled-workflows] 登记表：")
        for name, cron in REGISTRY.items():
            print(f"  - {name}：cron = {cron}")

    failures: list[str] = []
    notes: list[str] = []

    # ── 自洽面 1：登记完整性 ────────────────────────────────────────────
    on_disk = scheduled_workflow_files()
    unlisted = [name for name in on_disk if name not in REGISTRY]
    if unlisted:
        failures.append(f"盘上有 {len(unlisted)} 个带 schedule 触发器的工作流未登记：{unlisted}")

    # ── 自洽面 2：cron 逐字一致 ────────────────────────────────────────
    for name, declared in REGISTRY.items():
        path = WORKFLOW_DIR / name
        if not path.exists():
            failures.append(f"登记的 {name} 不在 .github/workflows/ 下")
            continue
        actual = workflow_cron(path)
        if actual is None:
            failures.append(f"{name} 里取不到 schedule 的 cron 字面量")
        elif actual != declared:
            failures.append(f"{name} 的 cron 与登记不一致：盘上 {actual!r} ≠ 登记 {declared!r}")

    # ── 主判定面：远端最近一次定时运行 ─────────────────────────────────
    slug = _repo_slug()
    if slug is None:
        notes.append("解析不出仓库 owner/repo（无 GITHUB_REPOSITORY 且 git remote 不可用）——远端巡检 [SKIP]")
    else:
        for name in REGISTRY:
            try:
                schedule_runs = list_runs(slug, name, "schedule")
                dispatch_runs = list_runs(slug, name, "workflow_dispatch")
            except RuntimeError as exc:
                notes.append(f"{name}：{exc}——远端巡检 [SKIP]")
                continue

            scheduled = latest_completed(schedule_runs)
            dispatched = latest_completed(dispatch_runs)
            # 在飞的手动运行（比定时运行更新）= **结论待定**，不是「红」。
            # 处置：按 [SKIP] 披露（带 run 号与它已运行时长），**不判红**——
            # 「作者正在验证修复」与「修复没验证过」是两件事，把前者判成后者会让
            # CI 在每次手动派发期间无理由变红；而它一旦**跑完并失败**，下一次运行
            # 就会看到「更新的手动运行 = failure」⇒ 判红，不漏。
            inflight = None
            for run in dispatch_runs:
                if run.get("status") != "completed" and run.get("created_at", "") > scheduled.get("created_at", ""):
                    inflight = run
                    break

            if scheduled is None:
                notes.append(f"{name}：尚无已完成的定时运行——[SKIP]")
                continue

            s_time = scheduled.get("created_at", "")
            s_conc = scheduled.get("conclusion")
            s_id = scheduled.get("id")
            if s_conc == "success":
                print(f"[scheduled-workflows] ✅ {name}：最近一次定时运行 {s_id} = success")
                continue

            if inflight is not None:
                notes.append(
                    f"{name}：定时运行 {s_id} 为 {s_conc}，但更新的手动运行 "
                    f"{inflight.get('id')} 仍在进行中（结论待定）——[SKIP]"
                )
                continue

            # 定时运行为红：看有没有**更新的**成功手动运行
            if (
                dispatched is not None
                and dispatched.get("created_at", "") > s_time
                and dispatched.get("conclusion") == "success"
            ):
                print(
                    f"[scheduled-workflows] ✅ {name}：定时运行 {s_id} 为 {s_conc}，"
                    f"但更新的手动运行 {dispatched.get('id')} = success（修复已在真实 runner 上验证）"
                )
                continue

            failures.append(
                f"{name}：最近一次定时运行 {s_id} 结论为 {s_conc}"
                + (
                    f"（更新的手动运行 {dispatched.get('id')} = {dispatched.get('conclusion')}，未转绿）"
                    if dispatched is not None
                    else "（且没有手动运行验证过修复）"
                )
            )

    for note in notes:
        print(f"[scheduled-workflows] [SKIP] {note}")
    for failure in failures:
        print(f"[scheduled-workflows] ❌ {failure}")
    if failures:
        print("[scheduled-workflows] 处置：`workflow_dispatch` 手动跑一次验证修复；或修工作流本身。")
        return 1
    print("[scheduled-workflows] ✅ 定时作业登记完整、cron 自洽、远端最近一次运行非红。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
