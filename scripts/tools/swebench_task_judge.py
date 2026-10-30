#!/usr/bin/env python3
"""swebench_task_judge.py — SWE-bench 阶段 2 单任务判定协议（零 LLM）。

端到端判定（2026-10-29 flask 单任务验证通过）：
  1. repo worktree checkout base_commit；
  2. 独立 venv（uv，Python 3.12）+ 依赖安装（PATCH-VERSION 锁定，-e 绕过用
     PYTHONPATH=src 布局——`pip install -e .` 的构建钩子在托管环境下不稳）；
  3. test_patch 应用 → FAIL_TO_PASS 基线（预期红）；
  4. patch（fix）应用 → FAIL_TO_PASS 复跑（预期绿）→ 红绿翻转 = 判定成功。

已知披露口径（flask 验证中固化）：
  - Python 3.12 跑老仓库需 `-W ignore::DeprecationWarning`（flask 2.0 conftest
    的 pkgutil.get_loader 在 3.12 弃用告警——属判定环境折衷，不改测试文件）；
  - 依赖版本按 API 兼容性锁定（flask 2.0 → werkzeug==2.3.*，新 werkzeug 移除
    url_quote）；
  - pytest 必须 cwd=任务物化目录 + env -u PYTHONPATH（防宿主环境污染）。

用法：python scripts/tools/swebench_task_judge.py --instance pallets__flask-4045
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTANCES = Path.home() / ".cache" / "aitester" / "swe_bench" / "swe_bench_lite_instances.jsonl"
REPOS = Path.home() / ".cache" / "aitester" / "swe_bench" / "repos"
OUT_DIR = REPO_ROOT / "experiments/results/swebench_repo_checkout_20261029"

# 依赖锁定表（repo → 按任务 version 锁定的运行时依赖；flask 端到端验证固化，
# 其余 repo 按同法逐个固化——每 repo 首跑都是一次版本考古）。
DEP_LOCKS: dict[str, dict[str, list[str]]] = {
    "pallets/flask": {
        "2.0": ["pytest==7.4.4", "werkzeug==2.3.7", "Jinja2>=3.0", "itsdangerous>=2.0", "click>=7.1.2", "blinker"],
    },
}


def load_instance(instance_id: str) -> dict:
    for line in INSTANCES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("instance_id") == instance_id:
            return d
    raise SystemExit(f"✗ 实例 {instance_id} 不在 {INSTANCES}")


def sh(args: list[str], cwd: str | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def pytest_run(venv_py: str, mat: str, tests: list[str], extra: list[str]) -> tuple[bool, str]:
    """跑指定测试；返回 (全绿, 原始输出尾部)。"""
    cmd = [
        "env",
        "-u",
        "PYTHONPATH",
        f"PYTHONPATH={mat}/src",
        venv_py,
        "-m",
        "pytest",
        *tests,
        "-q",
        "--no-header",
        "-W",
        "ignore::DeprecationWarning",
        *extra,
    ]
    proc = sh(cmd, cwd=mat, timeout=300)
    tail = (proc.stdout or "").strip().splitlines()[-3:]
    return proc.returncode == 0, "\n".join(tail)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--instance", required=True)
    ap.add_argument("--keep-mat", action="store_true", help="保留物化目录（调试用）")
    args = ap.parse_args()

    inst = load_instance(args.instance)
    repo = inst["repo"]
    base = inst["base_commit"]
    version = inst.get("version", "")
    ftp = json.loads(inst["FAIL_TO_PASS"]) if isinstance(inst["FAIL_TO_PASS"], str) else inst["FAIL_TO_PASS"]

    repo_dir = REPOS / repo.split("/")[-1]
    mat = Path("/tmp/swebench_mat") / f"{repo.split('/')[-1]}_{base[:8]}"
    record: dict[str, dict] = {"instance": args.instance, "repo": repo, "base_commit": base, "version": version}

    # 1. worktree checkout
    wt_ret = subprocess.run(
        ["git", "-C", str(repo_dir), "worktree", "add", str(mat), base], capture_output=True, text=True
    )
    if wt_ret.returncode != 0 and "already" not in wt_ret.stderr:
        record["error"] = f"worktree add 失败: {wt_ret.stderr.strip()[:200]}"
        print(json.dumps(record, ensure_ascii=False))
        return 1
    record["worktree"] = str(mat)

    # 2. venv + 依赖（uv 3.12）
    venv = Path("/tmp/swebench_mat") / f"{repo.split('/')[-1]}_venv_{version.replace('.', '_')}"
    deps = DEP_LOCKS.get(repo, {}).get(version)
    if deps is None:
        record["error"] = f"repo {repo} version {version} 无依赖锁定表条目（须先考古固化）"
        print(json.dumps(record, ensure_ascii=False))
        return 1
    subprocess.run(["uv", "venv", "--python", "3.12", str(venv)], capture_output=True, text=True)
    uv_install = subprocess.run(
        ["uv", "pip", "install", "--python", str(venv / "bin/python"), "-q", *deps],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if uv_install.returncode != 0:
        record["error"] = f"依赖安装失败: {uv_install.stderr.strip()[:200]}"
        print(json.dumps(record, ensure_ascii=False))
        return 1
    venv_py = str(venv / "bin/python")

    # 3. test_patch → 基线（预期红）
    tp = Path("/tmp") / f"{args.instance}_test.patch"
    tp.write_text(inst.get("test_patch") or "", encoding="utf-8")
    apply_tp = sh(["git", "apply", str(tp)], cwd=str(mat))
    record["test_patch_applied"] = apply_tp.returncode == 0
    baseline_ok, baseline_out = pytest_run(venv_py, str(mat), ftp, [])
    record["baseline_all_pass"] = baseline_ok
    record["baseline_tail"] = baseline_out

    # 4. fix patch → 复跑（预期绿）
    fp = Path("/tmp") / f"{args.instance}_fix.patch"
    fp.write_text(inst.get("patch") or "", encoding="utf-8")
    apply_fp = sh(["git", "apply", str(fp)], cwd=str(mat))
    record["fix_patch_applied"] = apply_fp.returncode == 0
    fixed_ok, fixed_out = pytest_run(venv_py, str(mat), ftp, [])
    record["fixed_all_pass"] = fixed_ok
    record["fixed_tail"] = fixed_out

    # 5. 红绿翻转判定
    record["verdict"] = (
        "PASS" if (apply_tp.returncode == 0 and apply_fp.returncode == 0 and not baseline_ok and fixed_ok) else "FAIL"
    )
    if not args.keep_mat:
        subprocess.run(["git", "-C", str(repo_dir), "worktree", "remove", "--force", str(mat)], capture_output=True)
    else:
        record["mat_dir"] = str(mat)

    print(json.dumps(record, ensure_ascii=False, indent=1))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"JUDGE_{args.instance.replace('/', '__')}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return 0 if record["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
