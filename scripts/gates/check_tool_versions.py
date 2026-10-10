#!/usr/bin/env python3
"""B-05（2026-10-04 系统审查 P1）：CI / pre-commit / lock 三方工具版本一致性守卫。

背景：
    CI（ci.yml）与 pre-commit（mirrors-mypy rev）曾出现 mypy 双版本漂移
    （CI 锁 1.7.1 / hook 用 1.15.0）——本地 hook 绿 ≠ CI 绿。本脚本
    以 ci.yml / .pre-commit-config.yaml 为声明源，requirements.lock 为
    实物源，逐工具校验三方版本一致（无 lock 条目时仅校验"声明间一致"）。

口径（保守、无网络）：
    - 只比对**顶层工具版本**（mypy / ruff）；lock 无该条目 → 记
      "not_in_lock" 不阻断（工具可不在 lock 里，CI 独立安装），
      但声明间（ci.yml ↔ pre-commit）不一致时 exit 1；
    - 工具版本以"数字元组"比较（1.15.0 vs 1.7.1 精确比较，不做
      ">= 兼容"——门禁要求逐字一致，防上游发版行为漂移）。

用法：
    python scripts/gates/check_tool_versions.py            # 有漂移 exit 1
    python scripts/gates/check_tool_versions.py --check     # 同上（显式）

CI 接线：test 作业 "Check lock sync" 之后追加一步（见 ci.yml）。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

# 工具 → (ci.yml 安装行的固定版本正则, pre-commit rev 正则, lock 条目正则)
_TOOL_PATTERNS: dict[str, tuple[str, str | None, str]] = {
    "mypy": (
        r'pip install "mypy==([0-9.]+)"',  # ci.yml test 作业固定版本
        r"rev:\s*v?([0-9.]+)\s*$",  # mirrors-mypy 的 rev（v1.15.0 或 1.15.0）
        r"^mypy==([0-9.]+)$",  # lock 条目
    ),
    "ruff": (
        r'pip install "ruff==([0-9.]+)"',
        r"rev:\s*v?([0-9.]+)\s*$",  # ruff-pre-commit 的 rev（v0.16.3）
        r"^ruff==([0-9.]+)$",
    ),
}


def _extract(path: Path, pattern: str) -> str | None:
    """在文件文本里找第一个匹配的版本组（找不到 → None）。"""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1) if m else None


def _pre_commit_rev(path: Path, repo_name: str) -> str | None:
    """从 .pre-commit-config.yaml 提取指定 repo（astral-sh/ruff-pre-commit /
    pre-commit/mirrors-mypy）的 rev 版本号。

    保守口径：按 repo 名定位块，在块内找 rev；找不到 repo → None（工具
    不在 hook 里，不阻断）。
    """
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    in_block = False
    for line in lines:
        if line.strip().startswith("- repo:") and repo_name in line:
            in_block = True
            continue
        if in_block:
            if line.strip().startswith("- repo:"):
                break  # 下一块开始，本 repo 块结束
            # AP 批（2026-10-07）修复：rev 行带 YAML 缩进（`    rev: v0.16.3`），
            # re.match 锚定行首导致恒不匹配 → pre-commit 版本恒报 "<absent>"，
            # ci↔hook 一致性校验（B-05 建立之本）此前形同虚设。strip 后匹配。
            m = re.match(r"rev:\s*v?([0-9.]+)\s*$", line.strip())
            if m:
                return m.group(1)
    return None


def main() -> None:
    ci_path = ROOT / ".github" / "workflows" / "ci.yml"
    hook_path = ROOT / ".pre-commit-config.yaml"
    lock_path = ROOT / "requirements.lock"

    failures: list[str] = []
    for tool, (ci_pat, _hook_pat, lock_pat) in _TOOL_PATTERNS.items():
        ci_ver = _extract(ci_path, ci_pat)
        repo = "astral-sh/ruff-pre-commit" if tool == "ruff" else "pre-commit/mirrors-mypy"
        hook_ver = _pre_commit_rev(hook_path, repo)
        lock_ver = _extract(lock_path, lock_pat)

        if ci_ver is None:
            failures.append(f"{tool}: ci.yml 未找到固定版本安装行（{ci_pat}）——门禁失效")
        if hook_ver is None:
            # 工具不在 pre-commit hook 里 → 仅校验 ci/lock，不阻断
            hook_ver = "<absent>"
        if ci_ver and ci_ver != hook_ver and hook_ver != "<absent>":
            failures.append(f"{tool}: 版本漂移 ci.yml={ci_ver} vs pre-commit={hook_ver}（B-05 三方一致性）")
        if lock_ver is not None and ci_ver is not None and lock_ver != ci_ver:
            failures.append(f"{tool}: lock={lock_ver} ≠ ci.yml={ci_ver}（B-05 lock 同步）")
        print(f"  {tool}: ci={ci_ver} pre-commit={hook_ver} lock={lock_ver or '<not in lock>'}")

    if failures:
        print("B-05 工具版本漂移（阻断合并）：")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("B-05 工具版本一致性：OK")


if __name__ == "__main__":
    main()
