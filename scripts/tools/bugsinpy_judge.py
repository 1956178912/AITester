#!/usr/bin/env python3
"""bugsinpy_judge.py — C8 外部效度：BugsInPy 小样红绿翻转判定（零 LLM 判定侧）。

预注册：docs/preregistration_c8_bugsinpy_draft_20261029.md（FROZEN 2026-10-29）。
协议：worktree(buggy) → setup → 跑官方 run_test 命令（预期红）→
      worktree(fixed) → setup → 重跑（预期绿）→ 双满足 = verdict PASS。

用法：
    python scripts/tools/bugsinpy_judge.py \
        --project PySnooper --bugs 1,2,3 \
        --py /tmp/mm_py38/bin/python \
        --out experiments/results/bugsinpy_judge_20261030.json
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

FW = Path.home() / ".cache/aitester/bugsinpy/framework/projects"
REPOS = Path.home() / ".cache/aitester/bugsinpy/repos"
MAT = Path("/tmp/bugsinpy_mat")


def _read_text_any_encoding(path: Path) -> str:
    """BugsInPy 部分元数据是 UTF-16（requirements.txt 实测）——逐编码探测。"""
    raw = path.read_bytes()
    for enc in ("utf-8", "utf-16", "utf-16-le"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def sh(cmd: list[str] | str, cwd: str | None = None, timeout: int = 600) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def setup_and_run(
    repo_name: str, commit: str, run_cmd: str, setup_cmd: str, py: str, bug_dir: Path, tag: str
) -> tuple[bool, str]:
    """单 commit 物化 + 安装 + 跑测试；返回 (通过, 输出尾部)。"""
    repo_dir = REPOS / repo_name
    mat = MAT / f"{repo_name}_{tag}"
    if mat.exists():
        shutil.rmtree(mat, ignore_errors=True)
    sh(["git", "-C", str(repo_dir), "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", str(repo_dir), "worktree", "add", str(mat), commit], timeout=120)
    if r.returncode != 0:
        return False, f"worktree 失败: {(r.stderr or '')[-150:]}"
    try:
        env = dict(subprocess.os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py).parent}:{env.get('PATH', '')}"
        # requirements **先装**（官方 BugsInPy 顺序：依赖在位后 setup.py install
        # 才不会走 easy_install 抓 egg——websockets 8.1 egg 抓取失败实测）；
        # 老 pin 在 arm64 可能无 wheel，逐包安装失败逐包披露
        reqs = bug_dir / "requirements.txt"
        req_text = _read_text_any_encoding(reqs) if reqs.is_file() else ""
        if req_text.strip():
            req_items = [
                line.strip()
                for line in req_text.splitlines()
                if line.strip() and not line.strip().startswith(("#", "-"))
            ]
            failed_pkgs = []
            for item in req_items:
                r = subprocess.run(
                    [py, "-m", "pip", "install", "-q", item],
                    capture_output=True,
                    text=True,
                    timeout=600,
                    env=env,
                )
                if r.returncode != 0:
                    failed_pkgs.append(item)
            # best-effort：失败包**披露不阻断**（pywin32=Windows 专用、
            # numpy 1.18.4/cryptography 2.9.2 无 arm64 wheel——均为原始
            # CI 环境 freeze 的非 sanic 运行时依赖；阻断会误杀全部实例）
            if failed_pkgs:
                print(f"  [deps 披露] 未装上 {len(failed_pkgs)} 包: {failed_pkgs[:5]}", flush=True)
        # setup（python setup.py build/install + extras；依赖已在位）
        if setup_cmd:
            r = subprocess.run(
                ["bash", "-c", setup_cmd], cwd=str(mat), capture_output=True, text=True, timeout=1800, env=env
            )
            if r.returncode != 0:
                return False, f"setup 失败: {(r.stderr or r.stdout)[-250:]}"
        r = subprocess.run(["bash", "-c", run_cmd], cwd=str(mat), capture_output=True, text=True, timeout=600, env=env)
        return r.returncode == 0, ((r.stdout or "") + (r.stderr or ""))[-250:]
    finally:
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(mat), "--force"], timeout=60)


def judge_bug(project: str, bug_id: str, py: str) -> dict[str, Any]:
    bug_dir = FW / project / "bugs" / bug_id
    info = dict(re.findall(r'(\w+)="([^"]*)"', (bug_dir / "bug.info").read_text(encoding="utf-8")))
    run_cmd = (bug_dir / "run_test.sh").read_text(encoding="utf-8").strip()
    setup_cmd = ""
    setup_sh = bug_dir / "setup.sh"
    if setup_sh.is_file():
        # 多行 setup.sh 用 "; " 顺序拼接（曾误用 "|" 变管道——语义全错）
        setup_cmd = "; ".join(
            line.strip()
            for line in _read_text_any_encoding(setup_sh).splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    rec: dict[str, Any] = {
        "project": project,
        "bug": bug_id,
        "buggy": info.get("buggy_commit_id", "")[:10],
        "fixed": info.get("fixed_commit_id", "")[:10],
    }
    t0 = time.time()
    red_ok, red_tail = setup_and_run(
        project, info["buggy_commit_id"], run_cmd, setup_cmd, py, bug_dir, f"b{bug_id}_buggy"
    )
    rec["baseline_red"] = not red_ok
    if red_ok:
        rec["verdict"], rec["tail"] = "baseline_not_red", red_tail
        return rec
    green_ok, green_tail = setup_and_run(
        project, info["fixed_commit_id"], run_cmd, setup_cmd, py, bug_dir, f"b{bug_id}_fixed"
    )
    rec["fix_green"] = green_ok
    rec["verdict"] = "PASS" if green_ok else "fix_not_green"
    rec["tail"] = green_tail if not green_ok else ""
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--bugs", required=True, help="逗号分隔 bug 号")
    ap.add_argument("--py", required=True, help="判定 python 绝对路径")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    records = [judge_bug(args.project, b.strip(), args.py) for b in args.bugs.split(",") if b.strip()]
    passed = sum(1 for r in records if r["verdict"] == "PASS")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"schema": "aitester_bugsinpy_judge/1", "records": records}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    for r in records:
        print(
            f"{r['project']} bug{r['bug']}: {r['verdict']} (red={r.get('baseline_red')} green={r.get('fix_green')}) {str(r.get('tail') or '')[-100:]}"
        )
    print(f"C8 小样: {passed}/{len(records)} PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
