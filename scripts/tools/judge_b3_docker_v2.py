#!/usr/bin/env python3
"""judge_b3_docker.py — B3 判定的 docker 驱动版 v2（daocloud x86 基础镜像）。

链路（2026-11-01 全链验证）：daocloud 拉 python:{spec_py}-slim x86 基础镜像
（Rosetta 跑 x86——arm64 失败的 C 扩展 wheel 在 x86 pypi 全有，astropy 实证）
→ 容器内 pip 走宿主代理（host.docker.internal）装官方 spec requirements →
worktree 挂载 /testbed → 生成测试 pytest（buggy/fixed 红绿翻转）。
官方 swebench 镜像因 dockerhub 白名单与 1-3TB 拉取量不可行，本方案等价重建。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"

_SPEC_PATH = Path(
    "/Users/wangchenyu/Workspace/AITester/experiments/results/swebench_repo_checkout_20261029/SPEC_EXTRACT.json"
)
_SPECS: dict[str, tuple[str, list[str]]] = {}


def _load_specs() -> dict[str, tuple[str, list[str]]]:
    out: dict[str, tuple[str, list[str]]] = {}
    try:
        d = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
    except Exception:
        return out
    for ln in d.get("lines", []):
        repo = ln["repo"].split("/")[-1]
        script = ln.get("setup_env_script", "")
        py_m = re.search(r"conda create -n \w+ python=([\d.]+)", script)
        m = re.search(r"cat <<'EOF_\d+' > \$HOME/requirements.txt\n(.*?)\nEOF_\d+", script, re.S)
        reqs = [x.strip() for x in m.group(1).splitlines() if x.strip() and not x.startswith("#")] if m else []
        out[f"{repo}@{ln['version']}"] = (py_m.group(1) if py_m else "3.9", reqs)
    return out


_SPECS = _load_specs()


def img_name(instance_id: str) -> str:
    return "swebench/sweb.eval.x86_64." + instance_id.upper().replace("__", "__1776__").replace("__", "_s_") + ":latest"


def real_img(instance_id: str) -> str:
    # 官方命名：__ → 1776__（双下划线转义），随后 _ → __……直接用官方规则简化版：
    # sweb.eval.x86_64.<instance_id 大写，__ 保留>:latest（2.1.8 实测命名）
    return f"swebench/sweb.eval.x86_64.{instance_id.upper()}:latest"


def sh(args: list[str], timeout: int = 3600, **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def judge_one(inst: dict, gen: str, workdir: Path, slice_id: int) -> dict:
    iid = inst["instance_id"]
    rec: dict = {"task_id": iid}
    t0 = time.time()
    repo = inst["repo"].split("/")[-1]
    spec_key = f"{repo}@{inst.get('version', '')}"
    spec_py, reqs = _SPECS.get(spec_key, ("3.9", []))
    base_img = f"docker.m.daocloud.io/library/python:{spec_py}-slim"
    # 基础镜像（x86）——已拉则跳过
    r = sh([DOCKER, "image", "inspect", base_img], timeout=60)
    if r.returncode != 0:
        print(f"[pull] {base_img} ...", flush=True)
        r = sh([DOCKER, "pull", "--platform", "linux/amd64", base_img], timeout=1800)
        if r.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"pull base: {r.stderr[-150:]}"
            return rec
    # worktree 物化（宿主机）——git worktree per instance
    wt = workdir / f"wt_{iid.replace('/', '_')[-50:]}"
    repo_dir = Path.home() / ".cache/aitester/swe_bench/repos" / repo
    if not repo_dir.is_dir():
        rec["verdict"] = "repo_missing"
        return rec
    sh(["git", "-C", str(repo_dir), "worktree", "remove", str(wt), "--force"], timeout=60)
    sh(["git", "-C", str(repo_dir), "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", str(repo_dir), "worktree", "add", str(wt), inst["base_commit"]], timeout=180)
    if r.returncode != 0:
        rec["verdict"] = "env_error"
        rec["tail"] = f"worktree: {r.stderr[-120:]}"
        return rec
    try:
        # code_src 覆盖（修复后代码——gold patch 已含）
        # 生成测试写入
        test_file = wt / "_gen_test.py"
        test_file.write_text(gen, encoding="utf-8")
        # 容器：挂载 worktree + 代理 + spec deps + editable + pytest
        # 线级镜像缓存（deps 装好 commit 成镜像，同线后续单元秒起）
        line_img = f"b3line_{repo}_{inst.get('version', 'x').replace('.', '_')}_s{slice_id}"
        r_img = sh([DOCKER, "image", "inspect", line_img], timeout=60)
        if r_img.returncode != 0:
            container = f"b3build_{repo}_{slice_id}"
            sh([DOCKER, "rm", "-f", container], timeout=60)
            boot_args = [
                DOCKER,
                "run",
                "--platform",
                "linux/amd64",
                "--name",
                container,
                "-d",
                base_img,
                "sleep",
                "infinity",
            ]
            r_boot = sh(boot_args, timeout=180)
            # 2026-11-02 修复：run 失败原先被静默丢弃，后续 exec 一律报 "container is not
            # running"，把「冷启动资源竞争」折叠成 env_error（s1-s3 共 78 条实证，同批
            # s4-s6 为 0）。失败重试一次，仍失败才带真实原因显式返回。
            if r_boot.returncode != 0:
                print(f"[boot-retry] {container}: {(r_boot.stderr or '')[-120:]}", flush=True)
                sh([DOCKER, "rm", "-f", container], timeout=60)
                time.sleep(3)
                r_boot = sh(boot_args, timeout=180)
            if r_boot.returncode != 0:
                rec["verdict"] = "env_error"
                rec["tail"] = f"docker run: {(r_boot.stderr or r_boot.stdout)[-200:]}"
                return rec
            # v2 修复（2026-11-02）：reqs 含 environment markers（如 "pylibmc; sys.platform != 'win32'"），
            # shell 单引号包参导致嵌套引号断裂 → line build rc=1 → 全 env_error（s2 50/50 实证）。
            # 改为容器内文件 + pip install -r（pip 自行解析 markers）。
            reqs_content = "\n".join(reqs) + "\n"
            subprocess.run(
                [DOCKER, "exec", "-i", container, "bash", "-lc", "cat > /tmp/_b3reqs.txt"],
                input=reqs_content,
                text=True,
                capture_output=True,
                timeout=60,
            )
            sh(
                [
                    DOCKER,
                    "exec",
                    container,
                    "bash",
                    "-lc",
                    "sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list* 2>/dev/null; apt-get update -qq 2>&1 | tail -1; apt-get install -y -qq gcc g++ 2>&1 | tail -1",
                ],
                timeout=900,
            )
            r_dep = sh(
                [
                    DOCKER,
                    "exec",
                    container,
                    "bash",
                    "-lc",
                    "set -o pipefail; pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pytest -r /tmp/_b3reqs.txt 2>&1 | tail -4",
                ],
                timeout=1800,
            )
            print(f"[line-build] {line_img} rc={r_dep.returncode} out_tail={(r_dep.stdout or '')[-150:]}", flush=True)
            if r_dep.returncode != 0:
                sh([DOCKER, "rm", "-f", container], timeout=60)
                rec["verdict"] = "env_error"
                rec["tail"] = f"line build deps: {(r_dep.stdout or r_dep.stderr)[-250:]}"
                return rec
            sh([DOCKER, "commit", container, line_img], timeout=600)
            sh([DOCKER, "rm", "-f", container], timeout=60)
        container = f"b3d_{iid.replace('/', '_')[-40:]}_{slice_id}"
        sh([DOCKER, "rm", "-f", container], timeout=60)
        _cur_proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip()
        proxy = ""  # 2026-11-01 全直连：daocloud 镜像 + 清华 pip 源，零代理依赖（沙箱端口漂移实证不可靠）
        envs = [
            "-e",
            f"HTTP_PROXY={proxy}",
            "-e",
            f"HTTPS_PROXY={proxy}",
            "-e",
            "http_proxy=" + proxy,
            "-e",
            "https_proxy=" + proxy,
            "-e",
            "NO_PROXY=localhost,127.0.0.1",
        ]
        r_run = sh(
            [
                DOCKER,
                "run",
                "--platform",
                "linux/amd64",
                "--name",
                container,
                "-d",
                "-v",
                f"{wt}:/testbed",
                "-w",
                "/testbed",
                *envs,
                base_img,
                "sleep",
                "infinity",
            ],
            timeout=180,
        )
        if r_run.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"run: {r_run.stderr[-150:]}"
            return rec
        # editable + pytest（deps 已在线级镜像内）
        setup = (
            "set -o pipefail; "
            "pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -e /testbed 2>&1 | tail -1; "
            "cd /testbed && python -m pytest _gen_test.py -q --no-header -W ignore::DeprecationWarning -x 2>&1 | tail -5"
        )
        r_run = sh([DOCKER, "exec", container, "bash", "-lc", setup], timeout=1800)
        out = (r_run.stdout or "") + (r_run.stderr or "")
        # editable 失败（C 扩展真编译失败）仍判 env_error
        if (
            "pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -e /testbed" in out
            and "ERROR" in out
            and "Successfully installed" not in out
        ):
            rec["verdict"] = "env_error"
            rec["tail"] = out[-200:]
        else:
            rec["verdict"] = "green" if r_run.returncode == 0 else "red"
            rec["tail"] = out[-200:]
        rec["wall_s"] = round(time.time() - t0, 1)
        return rec
    finally:
        sh([DOCKER, "rm", "-f", container], timeout=60)
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(wt), "--force"], timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", required=True, help="B3 极简 jsonl")
    ap.add_argument("--instances", required=True)
    ap.add_argument("--slice", type=int, default=0)
    ap.add_argument("--nslices", type=int, default=1)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    inst_map = {}
    with open(args.instances, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                inst_map[d["instance_id"]] = d

    with open(args.manifest, encoding="utf-8") as mf:
        rows = [json.loads(ln) for ln in mf if ln.strip()]
    mine = [r for r in rows if r.get("generated_test")][args.slice :: args.nslices]
    print(f"[info] B3 docker 判定 切片 {args.slice}/{args.nslices} → {len(mine)} 任务", file=sys.stderr)

    records = []
    for r in mine:
        iid = r["task_id"]
        gen = r.get("generated_test", "")
        inst = inst_map.get(iid)
        if inst is None or not gen:
            records.append({"task_id": iid, "verdict": "no_instance_or_no_gen"})
            continue
        print(f"[judge] {iid} ...", flush=True)
        records.append(judge_one(inst, gen, Path("/tmp/b3_docker"), args.slice))

    from collections import Counter

    c = Counter(x["verdict"] for x in records)
    Path(args.out).write_text(
        json.dumps(
            {"summary": {"aitester": dict(c)}, "records": records}, ensure_ascii=False, allow_nan=False, indent=1
        ),
        encoding="utf-8",
    )
    print(json.dumps({"aitester": dict(c)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
