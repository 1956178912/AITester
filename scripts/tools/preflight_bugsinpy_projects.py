#!/usr/bin/env python3
"""preflight_bugsinpy_projects.py — C8 扩样批的零 LLM 环境预检。

对每个项目取 1 个 bug 的 buggy commit：worktree 物化 + py3.8 派生 venv +
editable 安装。成功 = 该项目可进生成批；失败 = env_error 结构性披露
（不花 LLM 配额）。输出 JSONL 供批次编排消费。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

FW = Path.home() / ".cache/aitester/bugsinpy/framework/projects"
REPOS = Path.home() / ".cache/aitester/bugsinpy/repos"
MAT = Path("/tmp/c8_preflight_mat")
BASE_PY = Path("/tmp/mm_py38/bin/python")


def sh(cmd: list[str], cwd: str | None = None, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


def preflight(project: str) -> dict:
    bug_dir = FW / project / "bugs"
    bugs = sorted(bug_dir.iterdir()) if bug_dir.is_dir() else []
    if not bugs:
        return {"project": project, "n_bugs": 0, "editable_ok": False, "reason": "no bugs dir"}
    info = dict(
        re.findall(r'(\w+)="([^"]*)"', (bugs[0] / "bug.info").read_text(encoding="utf-8"))
        if (bugs[0] / "bug.info").is_file()
        else []
    )
    commit = info.get("buggy_commit_id", "")
    repo = REPOS / project
    if not commit or not repo.is_dir():
        return {"project": project, "n_bugs": len(bugs), "editable_ok": False, "reason": "no commit or repo"}
    mat = MAT / project
    if mat.exists():
        sh(["git", "-C", str(repo), "worktree", "remove", str(mat), "--force"])
    sh(["git", "-C", str(repo), "worktree", "prune"])
    r = sh(["git", "-C", str(repo), "worktree", "add", str(mat), commit], timeout=180)
    if r.returncode != 0:
        return {
            "project": project,
            "n_bugs": len(bugs),
            "editable_ok": False,
            "reason": f"worktree: {(r.stderr or '')[-100:]}",
        }
    try:
        venv = Path(f"/tmp/c8_venv_{project}")
        vpy = venv / "bin" / "python"
        if not vpy.exists():
            subprocess.run([str(BASE_PY), "-m", "venv", str(venv)], capture_output=True, text=True, timeout=300)
            subprocess.run(
                [str(vpy), "-m", "pip", "install", "-q", "pytest"], capture_output=True, text=True, timeout=600
            )
        if not vpy.exists():
            return {"project": project, "n_bugs": len(bugs), "editable_ok": False, "reason": "venv create failed"}
        env = dict(subprocess.os.environ)
        env.pop("PYTHONPATH", None)
        # 依赖 best-effort（bug 目录 requirements）

        req = bugs[0] / "requirements.txt"
        if req.is_file():
            raw = req.read_bytes()
            text = None
            for enc in ("utf-8", "utf-16", "utf-16-le"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if text:
                for item in [
                    ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith(("#", "-"))
                ]:
                    subprocess.run(
                        [str(vpy), "-m", "pip", "install", "-q", item],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        env=env,
                    )
        inst = subprocess.run(
            [str(vpy), "-m", "pip", "install", "-q", "-e", str(mat)],
            capture_output=True,
            text=True,
            timeout=1800,
            env=env,
        )
        ok = inst.returncode == 0
        return {
            "project": project,
            "n_bugs": len(bugs),
            "editable_ok": ok,
            "reason": "ok" if ok else f"editable: {(inst.stderr or inst.stdout)[-150:]}",
        }
    finally:
        sh(["git", "-C", str(repo), "worktree", "remove", str(mat), "--force"])


import re  # noqa: E402


def main() -> int:
    projects = sorted(d.name for d in FW.iterdir() if d.is_dir())
    out = []
    for p in projects:
        print(f"[preflight] {p} ...", flush=True)
        try:
            out.append(preflight(p))
        except Exception as e:
            out.append({"project": p, "editable_ok": False, "reason": f"exception: {e}"[:150]})
        print("   →", out[-1], flush=True)
    dst = Path.home() / ".cache/aitester/bugsinpy/c8_preflight.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = [r["project"] for r in out if r.get("editable_ok")]
    print(f"\n合格项目（{len(ok)}/{len(out)}）: {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
