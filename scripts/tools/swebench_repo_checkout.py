#!/usr/bin/env python3
"""swebench_repo_checkout.py — SWE-bench Lite repo-checkout 协议阶段 1（零 LLM）。

把官方 300 任务（princeton-nlp/SWE-bench_Lite 转换件）的 12 个 repo 克隆到
本地缓存并验证全部 base_commit 可达——为阶段 2（per-task 环境物化 + 判定
协议）提供 repo 层地基。ADR-0036 判据 B1 SWE-bench 项的"复跑前置"工程。

产出：experiments/results/swebench_repo_checkout_20261029/REPO_CHECKOUT.json
（repo → 本地路径 → base_commit 可达性统计；不可达 commit 逐条列出）。

用法：python scripts/tools/swebench_repo_checkout.py [--cache-dir DIR] [--skip-clone]
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE = Path.home() / ".cache" / "aitester" / "swe_bench" / "repos"
INSTANCES = Path.home() / ".cache" / "aitester" / "swe_bench" / "swe_bench_lite_instances.jsonl"
OUT_DIR = REPO_ROOT / "experiments/results/swebench_repo_checkout_20261029"

GITHUB_URLS = {
    "django/django": "https://github.com/django/django.git",
    "sympy/sympy": "https://github.com/sympy/sympy.git",
    "matplotlib/matplotlib": "https://github.com/matplotlib/matplotlib.git",
    "scikit-learn/scikit-learn": "https://github.com/scikit-learn/scikit-learn.git",
    "pytest-dev/pytest": "https://github.com/pytest-dev/pytest.git",
    "sphinx-doc/sphinx": "https://github.com/sphinx-doc/sphinx.git",
    "astropy/astropy": "https://github.com/astropy/astropy.git",
    "psf/requests": "https://github.com/psf/requests.git",
    "pylint-dev/pylint": "https://github.com/pylint-dev/pylint.git",
    "pydata/xarray": "https://github.com/pydata/xarray.git",
    "mwaskom/seaborn": "https://github.com/mwaskom/seaborn.git",
    "pallets/flask": "https://github.com/pallets/flask.git",
}


def load_instances() -> dict[str, set[str]]:
    """repo → {base_commit} 清单。"""
    repos: dict[str, set[str]] = {}
    for line in INSTANCES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        repo = d.get("repo") or (d.get("metadata") or {}).get("repo")
        base = d.get("base_commit") or (d.get("metadata") or {}).get("base_commit")
        if repo and base:
            repos.setdefault(repo, set()).add(base)
    return repos


def ensure_clone(repo: str, cache_dir: Path) -> tuple[Path, str]:
    """克隆或复用本地 repo；返回 (本地路径, 状态 cloned|reused|failed)。"""
    dest = cache_dir / repo.split("/")[-1]
    if (dest / ".git").is_dir():
        return dest, "reused"
    url = GITHUB_URLS.get(repo)
    if url is None:
        return dest, "failed:unknown-repo"
    dest.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    proc = subprocess.run(
        ["git", "clone", url, str(dest)],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if proc.returncode != 0:
        print(f"[checkout] {repo} clone 失败: {proc.stderr.strip()[:200]}", flush=True)
        return dest, f"failed:{proc.stderr.strip()[:120]}"
    print(f"[checkout] {repo} cloned in {time.time() - t0:.0f}s", flush=True)
    return dest, "cloned"


def check_commits(repo_path: Path, commits: set[str]) -> tuple[list[str], list[str]]:
    """逐 commit 验证可达性；返回 (可达, 不可达)。"""
    ok, missing = [], []
    for c in sorted(commits):
        proc = subprocess.run(
            ["git", "-C", str(repo_path), "cat-file", "-e", f"{c}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        (ok if proc.returncode == 0 else missing).append(c)
    return ok, missing


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cache-dir", default=str(DEFAULT_CACHE))
    ap.add_argument("--skip-clone", action="store_true", help="只做 commit 可达性验证（repo 已克隆时）")
    args = ap.parse_args()
    cache_dir = Path(args.cache_dir)

    repos = load_instances()
    total_commits = sum(len(v) for v in repos.values())
    print(f"[checkout] {len(repos)} repo / {total_commits} base_commit", flush=True)

    payload: dict[str, dict] = {"repos": {}, "generated": time.strftime("%Y-%m-%d %H:%M:%S")}
    all_ok = True
    for repo, commits in sorted(repos.items(), key=lambda kv: -len(kv[1])):
        if args.skip_clone:
            dest = cache_dir / repo.split("/")[-1]
            status = "skipped-clone"
        else:
            dest, status = ensure_clone(repo, cache_dir)
        if status.startswith("failed"):
            all_ok = False
            payload["repos"][repo] = {"path": str(dest), "status": status, "n_commits": len(commits)}
            continue
        ok, missing = check_commits(dest, commits)
        if missing:
            all_ok = False
            # 补 fetch（浅克隆常见缺历史）——full clone 理论不缺
            subprocess.run(["git", "-C", str(dest), "fetch", "--unshallow"], capture_output=True, timeout=1800)
            ok2, missing = check_commits(dest, commits)
            ok = ok2
        payload["repos"][repo] = {
            "path": str(dest),
            "status": status,
            "n_commits": len(commits),
            "n_reachable": len(ok),
            "n_missing": len(missing),
            "missing_commits": missing[:20],
        }
        print(
            f"[checkout] {repo}: {len(ok)}/{len(commits)} 可达" + (f"（缺 {len(missing)}）" if missing else ""),
            flush=True,
        )

    payload["all_reachable"] = all_ok
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "REPO_CHECKOUT.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[checkout] 报告：{out} | all_reachable={all_ok}", flush=True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
