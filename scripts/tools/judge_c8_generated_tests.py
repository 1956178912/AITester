#!/usr/bin/env python3
"""judge_c8_generated_tests.py — C8 主批：LLM 生成测试的红绿翻转判定。

判据（预注册 docs/preregistration_c8_bugsinpy_draft_20261029.md 冻结口径，
v1 修订选型 PySnooper+sanic 8 bugs 见偏离表）：
  检出 = 生成测试在 buggy commit 上「红」（pytest 有 failed 且非纯收集
  失败）∧ 在 fixed commit 上「绿」（退出码 0 全过）。
  收集失败（import error、无测试收集）= invalid_test，不计检出、如实披露。

环境复用 bugsinpy_judge.py（10-30 判定轮已验证 PySnooper/sanic 通路，
micromamba py3.8.20 /tmp/mm_py38）。

用法：
    python scripts/tools/judge_c8_generated_tests.py \
        --bench-dir experiments/results/c8_bugsinpy_20261031 \
        --py /tmp/mm_py38/bin/python \
        --out experiments/results/c8_bugsinpy_20261031/C8_JUDGE.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bugsinpy_judge import FW, REPOS, _read_text_any_encoding, sh

MAT = Path("/tmp/bugsinpy_mat")
_PYTEST_FAIL = re.compile(r"(\d+) failed")
_PYTEST_ERROR = re.compile(r"(\d+) error")


def _project_venv(project: str, base_py: str) -> str:
    """每项目独立 venv（py3.8 派生）——修复共享 mm_py38 的跨项目 egg 污染
    （sanic setup install 进全局 site-packages 后 asgi.py 的 import 链会
    在 PySnooper 判定的 pytest 收集期触发）。venv 内预装 pytest；venv 失败
    回退 base_py。"""
    venv = Path(f"/tmp/c8_venv_{project}")
    vpy = venv / "bin" / "python"
    if not vpy.exists():
        subprocess.run([base_py, "-m", "venv", str(venv)], capture_output=True, text=True, timeout=300)
        if vpy.exists():
            subprocess.run(
                [str(vpy), "-m", "pip", "install", "-q", "pytest"], capture_output=True, text=True, timeout=600
            )
    if vpy.exists():
        return str(vpy)
    return base_py


def setup_and_pytest(
    repo_name: str, commit: str, test_file_host: Path, setup_cmd: str, py: str, bug_dir: Path, tag: str
) -> tuple[str, str]:
    """物化 commit + 安装 + 跑生成测试；返回 (verdict_kind, 输出尾部)。

    verdict_kind ∈ {"green", "red", "invalid_test", "env_error"}
    """
    repo_dir = REPOS / repo_name
    mat = MAT / f"{repo_name}_c8_{tag}"
    if mat.exists():
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(mat), "--force"], timeout=60)
    sh(["git", "-C", str(repo_dir), "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", str(repo_dir), "worktree", "add", str(mat), commit], timeout=120)
    if r.returncode != 0:
        return "env_error", f"worktree 失败: {(r.stderr or '')[-150:]}"
    try:
        # 生成测试落盘到 worktree 根（pytest 根目录收集）
        dst = mat / "test_generated_c8.py"
        dst.write_text(test_file_host.read_text(encoding="utf-8"), encoding="utf-8")

        py = _project_venv(repo_name, py)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py).parent}:{env.get('PATH', '')}"
        # 依赖（bug 目录 requirements，逐包 best-effort——bugsinpy_judge 同款）
        reqs = bug_dir / "requirements.txt"
        req_text = _read_text_any_encoding(reqs) if reqs.is_file() else ""
        for item in [
            ln.strip() for ln in req_text.splitlines() if ln.strip() and not ln.strip().startswith(("#", "-"))
        ]:
            subprocess.run(
                [py, "-m", "pip", "install", "-q", item], capture_output=True, text=True, timeout=600, env=env
            )
        if setup_cmd:
            sr = subprocess.run(
                ["bash", "-c", setup_cmd], cwd=str(mat), capture_output=True, text=True, timeout=1800, env=env
            )
            if sr.returncode != 0:
                return "env_error", f"setup 失败: {(sr.stderr or sr.stdout)[-250:]}"
        # editable 安装被测项目（import 解析到当次物化 commit 的源码——
        # buggy/fixed 两轮各自正确；pytest 收集 `import pysnooper/sanic`）
        subprocess.run(
            [py, "-m", "pip", "install", "-q", "-e", str(mat)], capture_output=True, text=True, timeout=900, env=env
        )
        pr = subprocess.run(
            [py, "-m", "pytest", "test_generated_c8.py", "-q", "-W", "ignore::DeprecationWarning"],
            cwd=str(mat),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        out = ((pr.stdout or "") + (pr.stderr or ""))[-300:]
        if pr.returncode == 0:
            return "green", out
        if _PYTEST_FAIL.search(out):
            return "red", out
        if _PYTEST_ERROR.search(out) or "no tests ran" in out:
            return "invalid_test", out
        return "red", out  # 非零退出且无法归类的保守口径：按红处理并在 tail 留痕
    finally:
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(mat), "--force"], timeout=60)


def judge_one(arm: str, project: str, bug_id: str, gen_code: str, py: str) -> dict:
    bug_dir = FW / project / "bugs" / bug_id
    info = dict(re.findall(r'(\w+)="([^"]*)"', (bug_dir / "bug.info").read_text(encoding="utf-8")))
    setup_cmd = ""
    setup_sh = bug_dir / "setup.sh"
    if setup_sh.is_file():
        setup_cmd = "; ".join(
            ln.strip()
            for ln in _read_text_any_encoding(setup_sh).splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        )
    tf = Path(tempfile.mkdtemp(prefix="c8gen_")) / "gen_test.py"
    tf.write_text(gen_code, encoding="utf-8")

    rec: dict = {"arm": arm, "project": project, "bug": bug_id}
    t0 = time.time()
    red_kind, red_tail = setup_and_pytest(
        project, info["buggy_commit_id"], tf, setup_cmd, py, bug_dir, f"c8_{project}_{bug_id}_{arm}_buggy"
    )
    rec["buggy_kind"] = red_kind
    if red_kind != "red":
        rec["verdict"] = "not_detected" if red_kind == "invalid_test" else red_kind
        rec["tail"] = red_tail[-200:]
        rec["wall_s"] = round(time.time() - t0, 1)
        return rec
    green_kind, green_tail = setup_and_pytest(
        project, info["fixed_commit_id"], tf, setup_cmd, py, bug_dir, f"c8_{project}_{bug_id}_{arm}_fixed"
    )
    rec["fixed_kind"] = green_kind
    rec["verdict"] = (
        "detected" if green_kind == "green" else ("fix_not_green" if green_kind != "env_error" else "env_error")
    )
    rec["tail"] = green_tail[-200:]
    rec["wall_s"] = round(time.time() - t0, 1)
    return rec


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-dir", required=True)
    ap.add_argument("--py", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    bench = Path(args.bench_dir)
    records: list[dict] = []
    for arm in ("aitester", "plain_llm_df"):
        bjs = sorted((bench / arm).glob("benchmark_*.json"))
        if not bjs:
            print(f"[warn] {arm} 无 benchmark JSON", file=sys.stderr)
            continue
        d = json.loads(bjs[-1].read_text(encoding="utf-8"))
        for r in d["results"][arm]["details"]:
            gen = r.get("generated_test") or ""
            if not gen:
                records.append({"arm": arm, "task": r.get("task_id"), "verdict": "no_generated_test"})
                continue
            m = re.match(r"bugsinpy__(\w+)_(\w+)_(\w+)", r.get("task_id", ""))
            if not m:
                records.append({"arm": arm, "task": r.get("task_id"), "verdict": "unparsable_task_id"})
                continue
            project, bug_id = m.group(1), m.group(2)
            print(f"[judge] {arm} {project} bug{bug_id} ...", flush=True)
            records.append(judge_one(arm, project, bug_id, gen, args.py))

    by_arm: dict[str, dict[str, int]] = {}
    for r in records:
        a = by_arm.setdefault(r["arm"], {})
        a[r["verdict"]] = a.get(r["verdict"], 0) + 1
    summary = {arm: dict(v) for arm, v in by_arm.items()}

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(
            {"schema": "aitester_c8_generated_judge/1", "summary": summary, "records": records},
            ensure_ascii=False,
            indent=1,
            allow_nan=False,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
