#!/usr/bin/env python3
"""judge_tge_accuracy.py — TestGenEval-Lite accuracy 判定（2 臂 320 单元）。

口径（对齐官方 full-file generation 任务形态）：
  accuracy = 生成测试在【修复后代码】（code_src 覆盖 code_file）上 pytest 全绿。
  环境 = repo worktree（base_commit）+ editable 安装（与 B3 判定同构）。
  code_file/test_file/local_imports 取自 parquet 元数据。

用法：
  python judge_tge_accuracy.py --manifest <tge_manifest.jsonl> --py <py> --out <json>
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
    os.environ.pop(var, None)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pandas as pd  # noqa: E402
from bugsinpy_judge import sh  # noqa: E402

SWE_REPOS = Path.home() / ".cache/aitester/swe_bench/repos"
MAT = Path("/tmp/tge_acc_mat")
_PARQUET = Path.home() / ".cache/aitester/testgeneval/test.parquet"


def _meta() -> dict[str, dict]:
    df = pd.read_parquet(_PARQUET)
    out = {}
    for _, r in df.iterrows():
        out[str(r["instance_id"])] = {
            "repo": str(r["repo"]),
            "base_commit": str(r["base_commit"]),
            "code_file": str(r["code_file"]),
            "test_file": str(r["test_file"]),
            "code_src": str(r["code_src"]),
            "version": str(r.get("version", "")),
        }
    return out


def _project_venv(project: str, base_py: str, arm: str, version: str = "") -> str:
    # version 分层（2026-11-01）：django 5.0 等新版本 requires py>=3.10——
    # py3.8 判定 venv 装不上（env_error 实证）→ 新版本用主仓 py3.14 基座
    try:
        if version and float(version.split(".")[0]) >= 4:
            base_py = "/Users/wangchenyu/Workspace/AITester/.venv/bin/python3"
    except ValueError:
        pass
    venv = Path(f"/tmp/tge_venv_{project}_{arm}_v{version.replace('.', '_')}")
    vpy = venv / "bin" / "python"
    if not vpy.exists():
        subprocess.run([base_py, "-m", "venv", str(venv)], capture_output=True, text=True, timeout=300)
        if vpy.exists():
            subprocess.run(
                [str(vpy), "-m", "pip", "install", "-q", "pytest"], capture_output=True, text=True, timeout=600
            )
    return str(vpy) if vpy.exists() else base_py


def judge_one(arm: str, task_id: str, gen: str, meta: dict, base_py: str) -> dict:
    rec: dict = {"arm": arm, "task_id": task_id}
    m = meta.get(task_id.replace("tge__", "", 1))
    if m is None or not gen:
        rec["verdict"] = "no_meta_or_no_gen"
        return rec
    repo_short = m["repo"].split("/")[-1]
    repo_dir = SWE_REPOS / repo_short
    if not repo_dir.is_dir():
        rec["verdict"] = "repo_missing"
        return rec
    t0 = time.time()
    mat = MAT / f"{repo_short}_{arm}_{task_id.replace('/', '_')[-40:]}"
    if mat.exists():
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(mat), "--force"], timeout=60)
    sh(["git", "-C", str(repo_dir), "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", str(repo_dir), "worktree", "add", str(mat), m["base_commit"]], timeout=180)
    if r.returncode != 0:
        rec["verdict"] = "env_error"
        rec["tail"] = f"worktree: {(r.stderr or '')[-150:]}"
        return rec
    try:
        # code_src 覆盖 code_file（修复后代码）；生成测试写 test_file
        code_dst = mat / m["code_file"]
        code_dst.parent.mkdir(parents=True, exist_ok=True)
        code_dst.write_text(m["code_src"], encoding="utf-8")
        test_dst = mat / m["test_file"]
        test_dst.parent.mkdir(parents=True, exist_ok=True)
        test_dst.write_text(gen, encoding="utf-8")
        py = _project_venv(repo_short, base_py, arm, m.get("version", ""))
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py).parent}:{env.get('PATH', '')}"
        inst = subprocess.run(
            [py, "-m", "pip", "install", "-q", "-e", str(mat)], capture_output=True, text=True, timeout=1800, env=env
        )
        if inst.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"editable: {(inst.stderr or inst.stdout)[-180:]}"
            rec["wall_s"] = round(time.time() - t0, 1)
            return rec
        pr = subprocess.run(
            [py, "-m", "pytest", m["test_file"], "-q", "-W", "ignore::DeprecationWarning", "--no-header", "-x"],
            cwd=str(mat),
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        rec["verdict"] = "green" if pr.returncode == 0 else "red"
        rec["tail"] = ((pr.stdout or "") + (pr.stderr or ""))[-150:]
        rec["wall_s"] = round(time.time() - t0, 1)
        return rec
    finally:
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(mat), "--force"], timeout=60)


def main() -> int:
    # 2026-11-01 根治：脱离控制终端（fork+setsid）——后台写 tty 的 SIGTTOU
    # 挂起（zsh suspended (tty output) 三次实证）从机制上不可能再发生。
    # fork 后父进程立即退出（命令行 wait 语义变为"启动即返回"），判定在
    # daemon 子进程继续；进度看 --out json 与 stderr 重定向文件。
    if (os.environ.get("JUDGE_NO_DAEMON") != "1" and os.isatty(0) is False) or True:
        try:
            if os.fork() > 0:
                print("[daemon] parent exit, judge continues in background", flush=True)
                sys.exit(0)
            os.setsid()
        except OSError:
            pass  # 已是会话首（重复 daemonize 防御）

    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="minimal_gen 的 tge jsonl（单臂）")
    ap.add_argument("--arm", required=True)
    ap.add_argument("--py", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--slice", type=int, default=0)
    ap.add_argument("--nslices", type=int, default=1)
    args = ap.parse_args()

    meta = _meta()
    with open(args.manifest, encoding="utf-8") as mf:
        rows = [json.loads(ln) for ln in mf if ln.strip()]
    mine = rows[args.slice :: args.nslices]
    print(f"[info] {args.arm} 切片 {args.slice}/{args.nslices} → {len(mine)} 任务", file=sys.stderr)

    records = []
    for r in mine:
        tid = r["task_id"]
        gen = r.get("generated_test", "")
        print(f"[judge] {args.arm} {tid} ...", flush=True)
        records.append(judge_one(args.arm, tid, gen, meta, args.py))

    from collections import Counter

    c = Counter(x["verdict"] for x in records)
    summary = {args.arm: dict(c)}
    green = c.get("green", 0)
    valid = sum(v for k, v in c.items() if k not in ("env_error", "no_meta_or_no_gen", "repo_missing"))
    summary[args.arm]["accuracy"] = round(green / valid, 4) if valid else 0.0
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps({"summary": summary, "records": records}, ensure_ascii=False, allow_nan=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
