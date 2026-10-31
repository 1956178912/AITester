#!/usr/bin/env python3
"""judge_swebench_generated_tests.py — B3 执行批：Lite 任务生成测试的 repo 级红绿翻转判定。

B3 双 runner 接线的 C8 通路复用版：Lite 300 的生成测试（run_benchmark
-d swe_bench 单文件形态产出 generated_test）在真实 repo 环境判
「buggy 上红 ∧ gold patch 后绿 = 检出」。判据口径与 C8 判定脚本一致
（failed≥1 为红；exit 0 为绿；收集失败 invalid_test；环境失败
env_error 不进检出分母）。

与 judge_c8 的差异：
- 任务源 = SWE-bench Lite instances JSONL（base_commit/patch/instance_id）
- repo 目录 = ~/.cache/aitester/swe_bench/repos/<repo 短名>（REPO_CHECKOUT
  资产，12 repos）
- deps = pytest + editable 安装被测项目（django 纯 Python 自含；astropy/
  matplotlib/sklearn 的 C 扩展依赖失败 ⇒ env_error 如实披露，与阶段 2
  install_failed 口径一致）

用法：
    python scripts/tools/judge_swebench_generated_tests.py \
        --bench-dir experiments/results/b3_lite_20261031 \
        --py /tmp/mm_py38/bin/python \
        --out experiments/results/b3_lite_20261031/B3_JUDGE.json
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
from bugsinpy_judge import sh

SWE_REPOS = Path.home() / ".cache/aitester/swe_bench/repos"
MAT = Path("/tmp/swebench_gen_mat")
_PYTEST_FAIL = re.compile(r"(\d+) failed")
_PYTEST_ERROR = re.compile(r"(\d+) error")


def _project_venv(project: str, base_py: str) -> str:
    """每项目独立 venv（复用 judge_c8 的隔离纪律——跨项目 egg 污染防御）。"""
    venv = Path(f"/tmp/b3_venv_{project}")
    vpy = venv / "bin" / "python"
    if not vpy.exists():
        subprocess.run([base_py, "-m", "venv", str(venv)], capture_output=True, text=True, timeout=300)
        if vpy.exists():
            subprocess.run(
                [str(vpy), "-m", "pip", "install", "-q", "pytest"], capture_output=True, text=True, timeout=600
            )
    return str(vpy) if vpy.exists() else base_py


def setup_and_pytest(repo_dir: str, commit: str, gen_code: str, py: str, tag: str) -> tuple[str, str]:
    """物化 commit + editable 安装 + 跑生成测试；返回 (kind, tail)。"""
    mat = MAT / f"{repo_dir.split('/')[-1]}_{tag}"
    if mat.exists():
        sh(["git", "-C", repo_dir, "worktree", "remove", str(mat), "--force"], timeout=60)
    sh(["git", "-C", repo_dir, "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", repo_dir, "worktree", "add", str(mat), commit], timeout=180)
    if r.returncode != 0:
        return "env_error", f"worktree 失败: {(r.stderr or '')[-200:]}"
    try:
        dst = mat / "test_generated_b3.py"
        dst.write_text(gen_code, encoding="utf-8")
        py = _project_venv(repo_dir.split("/")[-1], py)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py).parent}:{env.get('PATH', '')}"
        # editable 安装被测项目（django 等纯 Python 自含；C 扩展项目失败 ⇒
        # env_error 如实披露，不进检出分母）
        inst = subprocess.run(
            [py, "-m", "pip", "install", "-q", "-e", str(mat)], capture_output=True, text=True, timeout=1200, env=env
        )
        if inst.returncode != 0:
            return "env_error", f"editable 安装失败: {(inst.stderr or inst.stdout)[-250:]}"
        pr = subprocess.run(
            [py, "-m", "pytest", "test_generated_b3.py", "-q", "-W", "ignore::DeprecationWarning"],
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
        return "red", out
    finally:
        sh(["git", "-C", repo_dir, "worktree", "remove", str(mat), "--force"], timeout=60)


def judge_one(
    arm: str, instance_id: str, repo_dir: str, base_commit: str, gold_patch: str, gen_code: str, py: str
) -> dict:

    tf = Path(tempfile.mkdtemp(prefix="b3gen_")) / "gen_test.py"
    tf.write_text(gen_code, encoding="utf-8")
    rec: dict = {"arm": arm, "instance_id": instance_id}
    t0 = time.time()
    red_kind, red_tail = setup_and_pytest(repo_dir, base_commit, gen_code, py, f"b3_{arm}_buggy")
    rec["buggy_kind"] = red_kind
    if red_kind != "red":
        rec["verdict"] = "not_detected" if red_kind == "invalid_test" else red_kind
        rec["tail"] = red_tail[-200:]
        rec["wall_s"] = round(time.time() - t0, 1)
        return rec
    # fixed 物化：buggy worktree 上应用 gold patch（与 C8 的 fixed commit
    # 物化等价——Lite 无 fixed commit 概念，gold patch 即修复）

    fix_tag = f"b3_{arm}_fixed"
    mat = MAT / f"{repo_dir.split('/')[-1]}_{fix_tag}"
    if mat.exists():
        sh(["git", "-C", repo_dir, "worktree", "remove", str(mat), "--force"], timeout=60)
    sh(["git", "-C", repo_dir, "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", repo_dir, "worktree", "add", str(mat), base_commit], timeout=180)
    if r.returncode != 0:
        rec["verdict"] = "env_error"
        rec["tail"] = f"worktree 失败: {(r.stderr or '')[-200:]}"
        return rec
    try:
        pf = Path(tempfile.mkdtemp(prefix="b3gold_")) / "gold.patch"
        pf.write_text(gold_patch, encoding="utf-8")
        ap = sh(["git", "apply", "--whitespace=nowarn", str(pf)], cwd=str(mat), timeout=120)
        if ap.returncode != 0:
            ap3 = sh(["git", "apply", "--3way", "--whitespace=nowarn", str(pf)], cwd=str(mat), timeout=120)
            if ap3.returncode != 0:
                rec["verdict"] = "gold_apply_failed"
                rec["tail"] = (ap.stderr or ap3.stderr or "")[-200:]
                rec["wall_s"] = round(time.time() - t0, 1)
                return rec
        dst = mat / "test_generated_b3.py"
        dst.write_text(gen_code, encoding="utf-8")
        py2 = _project_venv(repo_dir.split("/")[-1], py)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py2).parent}:{env.get('PATH', '')}"
        inst = subprocess.run(
            [py2, "-m", "pip", "install", "-q", "-e", str(mat)], capture_output=True, text=True, timeout=1200, env=env
        )
        if inst.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"fixed editable 失败: {(inst.stderr or inst.stdout)[-200:]}"
            rec["wall_s"] = round(time.time() - t0, 1)
            return rec
        pr = subprocess.run(
            [py2, "-m", "pytest", "test_generated_b3.py", "-q", "-W", "ignore::DeprecationWarning"],
            cwd=str(mat),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        out = ((pr.stdout or "") + (pr.stderr or ""))[-300:]
        if pr.returncode == 0:
            rec["fixed_kind"] = "green"
            rec["verdict"] = "detected"
        elif _PYTEST_FAIL.search(out):
            rec["fixed_kind"] = "red"
            rec["verdict"] = "fix_not_green"
        else:
            rec["fixed_kind"] = "invalid_test"
            rec["verdict"] = "fix_invalid"
        rec["tail"] = out[-200:]
        rec["wall_s"] = round(time.time() - t0, 1)
        return rec
    finally:
        sh(["git", "-C", repo_dir, "worktree", "remove", str(mat), "--force"], timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bench-dir", required=True)
    ap.add_argument("--instances", required=True, help="Lite instances JSONL")
    ap.add_argument("--py", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    inst_map: dict[str, dict] = {}
    with open(args.instances, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                inst_map[d["instance_id"]] = d

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
            tid = r.get("task_id", "")
            iid = tid.replace("swe_bench__", "").replace("swe_", "", 1) if tid else ""
            # run_benchmark 的 swe_bench task_id 形态需与 instance_id 对齐——
            # 按 details 的 task_id 内含 instance_id 的规则提取
            m = inst_map.get(iid)
            if m is None:
                for k in inst_map:
                    if k in tid:
                        m = inst_map[k]
                        iid = k
                        break
            if m is None or not gen:
                records.append({"arm": arm, "task": tid, "verdict": "no_instance_or_no_gen"})
                continue
            repo_short = m["repo"].split("/")[-1]
            repo_dir = str(SWE_REPOS / repo_short)
            if not Path(repo_dir).is_dir():
                records.append({"arm": arm, "instance_id": iid, "verdict": "repo_missing"})
                continue
            print(f"[judge] {arm} {iid} ...", flush=True)
            records.append(judge_one(arm, iid, repo_dir, m["base_commit"], m.get("patch", ""), gen, args.py))

    from collections import Counter

    summary = {}
    for arm in ("aitester", "plain_llm_df"):
        c = Counter(r["verdict"] for r in records if r.get("arm") == arm)
        summary[arm] = dict(c)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(
        json.dumps(
            {"schema": "aitester_b3_generated_judge/1", "summary": summary, "records": records},
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
