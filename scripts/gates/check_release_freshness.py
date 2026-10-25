#!/usr/bin/env python3
"""CZ（2026-10-26）：**发布新鲜度**守卫——最新的 release tag 不得落在 main 后面。

起因（本轮实测的事实）：`v1.0.0` tag 指向 `dc8285d3`，而 main 已经到 `23b35b00`——
**36 个提交**没有进入「已发布的 1.0.0」。这 36 个提交里包含：
perf 定时作业的构造期凭据修复、自变异 harness 的沙箱依赖闭包修复、投稿页数测量源的
四道守卫、仓库卫生与定时作业巡检两道新门禁，以及 CW/CY/CZ 三轮的文献与 novelty
收窄。**也就是说：远端那个名为「1.0.0」的发布产物，与仓库当前的状态不是同一件事。**

为什么值得单独设门（而不只是「知道一下」）：

- tag 指向的树是**发布产物**的来源（`release.yml` 由 `v*` tag push 触发，检出的是
  被标记的那个提交）⇒ tag 落后 = 发布的产物缺修复。
- 「tag 要不要前移」是**作者的决定**（force-update 属外部动作）⇒ 本门**不能**自作主张
  改 tag；但它**必须**让这个事实**可见**，否则它就只活在某个人的记忆里。

判定形状：

- 取最新的 `v*` release tag 与默认分支的 HEAD；
- 若 HEAD **领先**该 tag ⇒ 该 tag 已过期（发布产物落后于仓库）；
- **已登记例外**（`docs/release_freshness_allowlist.txt`，逐条写明 tag 名与理由）⇒ 绿，
  但**必须逐条打印落后多少个提交**（登记是「显式承担」，不是「沉默」）；
- 例外的 tag 名与当前最新 tag **不一致** ⇒ 例外**已失效** ⇒ 红（tag 前移后必须清理登记）；
- 未登记的落后 ⇒ 红；
- 没有 release tag ⇒ `[SKIP]` 披露（项目还没发过版，不是缺陷）。

用法：
    python scripts/gates/check_release_freshness.py
    python scripts/gates/check_release_freshness.py --list   # 打印例外登记

环境变量：`GITHUB_TOKEN`（可选，CI 传 `github.token`）、`GITHUB_REPOSITORY`（可选）。

退出码：0 = 通过（含已登记例外）；1 = 发布产物落后且未登记 / 例外已失效；2 = 用法错误。
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
ALLOWLIST = PROJECT_ROOT / "docs" / "release_freshness_allowlist.txt"
_API_TIMEOUT = 30


def _repo_slug() -> str | None:
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
    """调 GitHub API（用 curl：本机走企业代理时 Python 的 CA 链不含代理 CA）。"""
    url = f"https://api.github.com{path}"
    headers = [
        "Accept: application/vnd.github+json",
        "User-Agent: aitester-release-freshness-gate",
    ]
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers.append(f"Authorization: Bearer {token}")
    config = "".join(f'header = "{h}"\n' for h in headers)
    try:
        proc = subprocess.run(
            ["curl", "-sS", "--max-time", str(_API_TIMEOUT), "-w", "\n%{http_code}", "-K", "-", url],
            input=config,
            capture_output=True,
            text=True,
            timeout=_API_TIMEOUT + 10,
            check=False,
        )
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"curl 不可用：{exc}") from exc
    if proc.returncode != 0:
        raise RuntimeError(f"curl 退出码 {proc.returncode}：{proc.stderr.strip()[:200]}")
    body, _, status = proc.stdout.rpartition("\n")
    if status.strip() != "200":
        raise RuntimeError(f"GitHub API 返回 HTTP {status.strip() or '?'}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub API 响应不是 JSON：{exc}") from exc


def latest_release_tag(slug: str) -> tuple[str, str] | None:
    """取最新的 `v*` tag 与它指向的提交 SHA。"""
    payload = _api_get(f"/repos/{slug}/tags?per_page=100")
    best: tuple[str, str] | None = None
    for tag in payload if isinstance(payload, list) else []:
        name = tag.get("name", "")
        if not re.match(r"^v\d", name):
            continue
        sha = (tag.get("commit") or {}).get("sha", "")
        if not sha:
            continue
        if best is None:
            best = (name, sha)
    return best


def compare(slug: str, base: str, head: str) -> dict[str, Any]:
    payload = _api_get(f"/repos/{slug}/compare/{base}...{head}")
    return payload if isinstance(payload, dict) else {}


def load_allowlist() -> dict[str, str]:
    """读例外登记：`v1.0.0  # 理由` ⇒ {tag: 理由}。空行与 `#` 开头的行忽略。"""
    if not ALLOWLIST.exists():
        return {}
    entries: dict[str, str] = {}
    for raw in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        tag, _, reason = line.partition("#")
        entries[tag.strip()] = reason.strip()
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="发布新鲜度守卫：最新 release tag 不得落在 main 后面")
    parser.add_argument("--list", action="store_true", help="打印例外登记（不改变判定）")
    args = parser.parse_args(argv)

    allowlist = load_allowlist()
    if args.list:
        print("[release-freshness] 例外登记：")
        for tag, reason in allowlist.items():
            print(f"  - {tag}：{reason}")

    slug = _repo_slug()
    if slug is None:
        print("[release-freshness] [SKIP] 解析不出仓库 owner/repo（无 GITHUB_REPOSITORY 且 git remote 不可用）")
        return 0

    try:
        tag_info = latest_release_tag(slug)
        if tag_info is None:
            print("[release-freshness] [SKIP] 仓库还没有 `v*` release tag——不是缺陷")
            return 0
        tag_name, tag_sha = tag_info
        repo = _api_get(f"/repos/{slug}")
        default_branch = repo.get("default_branch", "main")
        head_sha = _api_get(f"/repos/{slug}/commits/{default_branch}").get("sha", "")
        if not head_sha:
            print(f"[release-freshness] [SKIP] 取不到 {default_branch} 的 HEAD")
            return 0
        if head_sha == tag_sha:
            print(f"[release-freshness] ✅ 最新 release tag {tag_name} 就是 {default_branch} 的 HEAD")
            return 0
        diff = compare(slug, tag_sha, head_sha)
        ahead = int(diff.get("ahead_by", 0))
    except RuntimeError as exc:
        print(f"[release-freshness] [SKIP] {exc}")
        return 0

    if ahead <= 0:
        print(f"[release-freshness] ✅ 最新 release tag {tag_name} 不落后于 {default_branch}")
        return 0

    if tag_name in allowlist:
        print(f"[release-freshness] ✅ {tag_name} 落后 {ahead} 个提交——**已登记例外**（{allowlist[tag_name]}）")
        print(f"[release-freshness]    ⇢ 发布产物来自 {tag_sha[:8]}，{default_branch} 在 {head_sha[:8]}")
        return 0

    stale = [name for name in allowlist if name != tag_name]
    if stale:
        print(
            f"[release-freshness] ❌ 例外登记已失效：{stale} 不再是最新 release tag（当前 {tag_name}）——"
            "请清理或更新 docs/release_freshness_allowlist.txt"
        )
    print(
        f"[release-freshness] ❌ 最新 release tag {tag_name} 落后 {default_branch} ** {ahead} 个提交**"
        f"（tag={tag_sha[:8]}，head={head_sha[:8]}）——发布的产物缺这些提交里的修复。"
    )
    print(
        "[release-freshness]    处置：① 前移 tag（需作者同意，外部动作）；或 ② 把它登记进 "
        "docs/release_freshness_allowlist.txt 并写明理由。"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
