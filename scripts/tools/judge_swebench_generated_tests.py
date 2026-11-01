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

_SPEC_PATH = Path(
    "/Users/wangchenyu/Workspace/AITester/experiments/results/swebench_repo_checkout_20261029/SPEC_EXTRACT.json"
)
_SPECS: dict[str, list[str]] = {}


def _load_specs() -> dict[str, list[str]]:
    """官方 spec（64 repo×version 线）→ requirements 列表（setup_env_script 解析）。"""
    out: dict[str, list[str]] = {}
    try:
        d = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
    except Exception:
        return out
    for ln in d.get("lines", []):
        repo = ln["repo"].split("/")[-1]
        m = re.search(
            r"cat <<'EOF_\d+' > \$HOME/requirements.txt\n(.*?)\nEOF_\d+", ln.get("setup_env_script", ""), re.S
        )
        if m:
            reqs = [x.strip() for x in m.group(1).splitlines() if x.strip() and not x.startswith("#")]
            out[f"{repo}@{ln['version']}"] = reqs
    return out


_SPECS = _load_specs()

_SLICE_ID = [0]  # judge_one 深处的 venv 隔离需要 slice 号（模块级单元素列表）
_PYTEST_FAIL = re.compile(r"(\d+) failed")
_PYTEST_ERROR = re.compile(r"(\d+) error")


def _project_venv(project: str, base_py: str, slice_id: int = 0) -> str:
    """每项目独立 venv（复用 judge_c8 的隔离纪律——跨项目 egg 污染防御）。"""
    # 2026-11-01 基座升级：py3.8 → py3.14（主仓 venv 基座）——django 4.x/5.x
    # requires py>=3.10 在 py3.8 装不上（env_error 246 实证）；py3.14 满足
    # >=3.10 且纯 Python 项目全兼容。sklearn/astropy 的 C 扩展 arm64 结构性
    # 失败保持 env_error 披露。
    base_py = "/Users/wangchenyu/Workspace/AITester/.venv/bin/python3"
    venv = Path(f"/tmp/b3_venv_{project}_s{slice_id}")  # 切片隔离：并发切片进程共写同 venv 会 pip 冲突死锁
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
        py = _project_venv(repo_dir.split("/")[-1], py, _SLICE_ID[0])
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py).parent}:{env.get('PATH', '')}"
        # editable 安装被测项目（django 等纯 Python 自含；C 扩展项目失败 ⇒
        # env_error 如实披露，不进检出分母）
        # 官方 spec deps 预装（repo 维度并集 best-effort——env_error 主因=deps 全缺）
        _reqs: list[str] = []
        for _k, _req_list in _SPECS.items():
            if _k.split("@")[0] == repo_dir.split("/")[-1]:
                for _x in _req_list:
                    if _x not in _reqs:
                        _reqs.append(_x)
        if _reqs:
            subprocess.run(
                [py, "-m", "pip", "install", "-q", *_reqs], capture_output=True, text=True, timeout=1800, env=env
            )
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
        py2 = _project_venv(repo_dir.split("/")[-1], py, _SLICE_ID[0])
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        env["PATH"] = f"{Path(py2).parent}:{env.get('PATH', '')}"
        # 官方 spec deps 预装（repo 维度并集 best-effort——env_error 主因=deps 全缺）
        _reqs: list[str] = []
        for _k, _req_list in _SPECS.items():
            if _k.split("@")[0] == repo_dir.split("/")[-1]:
                for _x in _req_list:
                    if _x not in _reqs:
                        _reqs.append(_x)
        if _reqs:
            subprocess.run(
                [py2, "-m", "pip", "install", "-q", *_reqs], capture_output=True, text=True, timeout=1800, env=env
            )
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
    ap.add_argument("--bench-dir", required=True)
    ap.add_argument("--instances", required=True, help="Lite instances JSONL")
    ap.add_argument("--py", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--slice", type=int, default=0)
    ap.add_argument("--nslices", type=int, default=1)
    args = ap.parse_args()

    inst_map: dict[str, dict] = {}
    with open(args.instances, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                inst_map[d["instance_id"]] = d

    _SLICE_ID[0] = args.slice
    bench = Path(args.bench_dir)
    records: list[dict] = []
    for arm in ("aitester", "plain_llm_df"):
        bjs = sorted((bench / arm).rglob("benchmark_*.json"))
        if not bjs:
            print(f"[warn] {arm} 无 benchmark JSON", file=sys.stderr)
            continue
        # 分片容错聚合（2026-11-01）：全部 json 按 task_id 去重，**有 generated_test
        # 的记录优先**（空壳 json——被杀实例的骨架——被真产物覆盖）
        merged: dict[str, dict] = {}
        for bj in bjs:
            try:
                _d = json.loads(bj.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[warn] {bj.name} 解析失败跳过: {e}", file=sys.stderr)
                continue
            for r in _d["results"][arm]["details"]:
                tid = r.get("task_id", f"__{len(merged)}")
                if r.get("generated_test") or tid not in merged:
                    merged[tid] = r
        details_all = list(merged.values())
        print(f"[info] {arm} 聚合 {len(bjs)} json → {len(details_all)} 任务", file=sys.stderr)
        _details = details_all[args.slice :: args.nslices]
        print(f"[info] {arm} 切片 {args.slice}/{args.nslices} → {len(_details)} 任务本进程", file=sys.stderr)
        for r in _details:
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
