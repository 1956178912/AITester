#!/usr/bin/env python3
"""judge_g8_docker.py — G8 M3 门禁的 per-instance docker 验证器（第一步：不烧 LLM）。

背景（2026-11-02 晨间盘点）
--------------------------
full178 两臂增量产物核验：on 177/178 harness_invalid、off 176/177 harness_invalid、
passed=0 ⇒ effective 分母 = 0，G8 四开关对比 ran_unmeasurable 从 10 任务定性
升级为全池实锤。根因 = M3 P2P 门禁的 fail-to-pass 翻转在 REPO_LEVEL_EXECUTION
本机环境下测不准（环境假红），不是任务本身无效。

本脚本做第几步
--------------
**第一步：只验证 harness 有效性**——per-instance docker 环境（daocloud x86 镜像
+ worktree@base_commit + 清华源 spec deps，B3 docker 通道同款链路）下：
应用 golden patch + test_patch → pytest fail_to_pass 清单 → 全绿 = harness_valid。
产出 = 178 任务的真实 effective 分母。**不调用任何 LLM、不跑四开关生成。**

口径偏离披露（预注册 M3 门禁的子集）
------------------------------------
第一步只测 f2p 翻转（门禁主判据）；pass_to_pass 不破检查留待第二步
（effective 任务上）完整执行——避免 178 任务全量 p2p 套件把机器时拖爆。

用法
----
    # smoke：前 3 任务验证链路
    python judge_g8_docker.py --limit 3 --out /tmp/g8_gate_smoke.json
    # 全量（建议在 daypatch 判定批结束后跑）
    python judge_g8_docker.py --out experiments/results/overnight_20261101/G8_GATE_DOCKER.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"
_INSTANCES = Path.home() / ".cache/aitester/swe_bench_pro/g8_full178/swe_bench_pro_instances.jsonl"
_SPEC_PATH = Path(
    "/Users/wangchenyu/Workspace/AITester/experiments/results/swebench_repo_checkout_20261029/SPEC_EXTRACT.json"
)
# G8 178 任务全部来自 ansible/openlibrary/qutebrowser（不在 swe_bench/repos 池）——
# 专用池在 swe_bench_pro/repos/（2026-11-02 实证）
_SWE_REPOS = Path.home() / ".cache/aitester/swe_bench_pro/repos"
# G8 三 repo 不在 SPEC_EXTRACT（那是 B3 swebench_lite 的 repo 集）——
# 依赖策略 = repo 树自带 requirements*.txt（base_commit 树内官方依赖），repo 级 line 镜像缓存

_SPEC_CACHE: dict[str, tuple[str, list[str]]] | None = None


def _load_specs() -> dict[str, tuple[str, list[str]]]:
    """repo -> (py_version, reqs)。G8 任务无 version 字段，退化 repo 级 best effort。"""
    global _SPEC_CACHE
    if _SPEC_CACHE is not None:
        return _SPEC_CACHE
    out: dict[str, tuple[str, list[str]]] = {}
    try:
        d = json.loads(_SPEC_PATH.read_text(encoding="utf-8"))
    except Exception:
        _SPEC_CACHE = out
        return out
    for ln in d.get("lines", []):
        repo = ln["repo"].split("/")[-1]
        script = ln.get("setup_env_script", "")
        py_m = re.search(r"conda create -n \w+ python=([\d.]+)", script)
        m = re.search(r"cat <<'EOF_\d+' > \$HOME/requirements.txt\n(.*?)\nEOF_\d+", script, re.S)
        reqs = [x.strip() for x in m.group(1).splitlines() if x.strip() and not x.startswith("#")] if m else []
        # 同 repo 多 version 时保留第一个（G8 第一步口径：repo 级 best effort，env_error 单独归类）
        out.setdefault(repo, (py_m.group(1) if py_m else "3.9", reqs))
    _SPEC_CACHE = out
    return out


def sh(args: list[str], timeout: int = 1800, **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def _as_list(x) -> list[str]:
    """f2p/p2p 字段容错：JSON 字符串或原生 list。"""
    if isinstance(x, list):
        return [str(i) for i in x if str(i).strip()]
    if isinstance(x, str):
        try:
            v = json.loads(x)
            return [str(i) for i in v] if isinstance(v, list) else []
        except Exception:
            return []
    return []


def gate_one(inst: dict, workdir: Path, tag: str) -> dict:
    iid = inst["instance_id"]
    rec: dict = {"task_id": iid}
    repo_full = inst["repo"]
    repo = repo_full.split("/")[-1]
    base_commit = inst.get("base_commit", "")
    f2p = _as_list(inst.get("fail_to_pass"))
    rec["f2p_n"] = len(f2p)
    if not f2p or not base_commit:
        rec["verdict"] = "data_missing"
        return rec

    spec_py = "3.11"  # G8 无 per-repo spec 数据；3.11 覆盖三 repo 的现代语法（best effort 口径）
    base_img = f"docker.m.daocloud.io/library/python:{spec_py}-slim"
    t0 = time.time()

    # 基础镜像
    if sh([DOCKER, "image", "inspect", base_img], timeout=60).returncode != 0:
        r = sh([DOCKER, "pull", "--platform", "linux/amd64", base_img], timeout=1800)
        if r.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"pull base: {r.stderr[-150:]}"
            return rec

    # worktree 物化
    wt = workdir / f"g8wt_{iid.replace('/', '_')[-50:]}"
    repo_dir = _SWE_REPOS / repo
    if not repo_dir.is_dir():
        rec["verdict"] = "repo_missing"
        return rec
    sh(["git", "-C", str(repo_dir), "worktree", "remove", str(wt), "--force"], timeout=60)
    sh(["git", "-C", str(repo_dir), "worktree", "prune"], timeout=60)
    r = sh(["git", "-C", str(repo_dir), "worktree", "add", str(wt), base_commit], timeout=300)
    if r.returncode != 0:
        # worktree add 失败可能因 base_commit 不在本仓——fetch 后重试一次
        sh(["git", "-C", str(repo_dir), "fetch", "--all", "--tags"], timeout=1800)
        r = sh(["git", "-C", str(repo_dir), "worktree", "add", str(wt), base_commit], timeout=300)
        if r.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"worktree: {r.stderr[-150:]}"
            return rec
    try:
        # 写入 gold/test patch 并在宿主端应用——worktree 的 .git 指针绑定宿主路径，
        # 容器内 git 不可用（fatal: not a git repository 实证）；容器只负责 deps+pytest
        (wt / "_g8_gold.patch").write_text(inst.get("patch", ""), encoding="utf-8")
        (wt / "_g8_test.patch").write_text(inst.get("test_patch", ""), encoding="utf-8")
        r_gold = sh(["git", "-C", str(wt), "apply", "--whitespace=nowarn", "_g8_gold.patch"], timeout=120)
        r_test_patch = (
            sh(["git", "-C", str(wt), "apply", "--whitespace=nowarn", "_g8_test.patch"], timeout=120)
            if r_gold.returncode == 0
            else None
        )
        if r_gold.returncode != 0 or (r_test_patch and r_test_patch.returncode != 0):
            rec["verdict"] = "patch_apply_failed"
            rec["tail"] = ((r_gold.stderr or "") + (r_test_patch.stderr if r_test_patch else ""))[-250:]
            return rec

        # 线级 deps 镜像（repo 级缓存）：用宿主 repo 池当前树的自带 requirements
        line_img = f"g8line_{repo}_{spec_py.replace('.', '_')}"
        if sh([DOCKER, "image", "inspect", line_img], timeout=60).returncode != 0:
            container = f"g8build_{repo}"
            sh([DOCKER, "rm", "-f", container], timeout=60)
            if (
                sh(
                    [
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
                    ],
                    timeout=180,
                ).returncode
                != 0
            ):
                rec["verdict"] = "env_error"
                rec["tail"] = "line build run fail"
                return rec
            sh(
                [
                    DOCKER,
                    "exec",
                    container,
                    "bash",
                    "-lc",
                    "sed -i 's|deb.debian.org|mirrors.tuna.tsinghua.edu.cn|g; s|security.debian.org|mirrors.tuna.tsinghua.edu.cn/debian-security|g' /etc/apt/sources.list* 2>/dev/null; apt-get update -qq 2>&1 | tail -1; apt-get install -y -qq gcc g++ git libxml2-dev libxslt-dev libpq-dev 2>&1 | tail -1",
                ],
                timeout=900,
            )
            req_files = [
                repo_dir / f for f in ("requirements.txt", "requirements_test.txt") if (repo_dir / f).is_file()
            ]
            ok = True
            for rf in req_files:
                content = rf.read_text(encoding="utf-8", errors="replace")
                if not content.strip():
                    continue
                # 容器内 github 443 不可达（宿主可达）——git+https 依赖走 ghproxy 前缀（pyopds2 实测 RC=0）
                content = content.replace("git+https://github.com/", "git+https://ghproxy.net/https://github.com/")
                rc_file = f"/tmp/{rf.name}"
                _up = subprocess.run(
                    [DOCKER, "exec", "-i", container, "bash", "-lc", f"cat > {rc_file}"],
                    input=content,
                    text=True,
                    capture_output=True,
                    timeout=60,
                )
                if _up.returncode != 0:
                    rec["tail"] = f"req upload: {_up.stderr[-150:]}"
                    sh([DOCKER, "rm", "-f", container], timeout=60)
                    rec["verdict"] = "env_error"
                    return rec
                r_dep = sh(
                    [
                        DOCKER,
                        "exec",
                        container,
                        "bash",
                        "-lc",
                        f"set -o pipefail; pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r {rc_file} 2>&1 | tail -3",
                    ],
                    timeout=1800,
                )
                if r_dep.returncode != 0:
                    ok = False
                    rec["tail"] = f"deps {rf.name}: {(r_dep.stdout or r_dep.stderr)[-200:]}"
                    break
            if not ok:
                sh([DOCKER, "rm", "-f", container], timeout=60)
                rec["verdict"] = "env_error"
                return rec
            sh(
                [
                    DOCKER,
                    "exec",
                    container,
                    "bash",
                    "-lc",
                    "pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple pytest 2>&1 | tail -1",
                ],
                timeout=600,
            )
            sh([DOCKER, "commit", container, line_img], timeout=600)
            sh([DOCKER, "rm", "-f", container], timeout=60)

        # 判定容器
        container = f"g8d_{iid.replace('/', '_')[-40:]}_{tag}"
        sh([DOCKER, "rm", "-f", container], timeout=60)
        if (
            sh(
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
                    line_img,
                    "sleep",
                    "infinity",
                ],
                timeout=180,
            ).returncode
            != 0
        ):
            rec["verdict"] = "env_error"
            rec["tail"] = "run fail"
            return rec
        # editable（尽力，openlibrary 结构性失败不阻断）→ pytest f2p（patch 已在宿主应用）
        f2p_args = " ".join("'" + x.replace("'", "'\\''") + "'" for x in f2p)
        setup = (
            "pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -e /testbed 2>&1 | tail -1 || true; "
            "cd /testbed && python -m pytest "
            + f2p_args
            + " -q --no-header -W ignore::DeprecationWarning 2>&1 | tail -8"
        )
        r_test = sh([DOCKER, "exec", container, "bash", "-lc", setup], timeout=2400)
        out = (r_test.stdout or "") + (r_test.stderr or "")
        if r_test.returncode == 0 and "no tests ran" not in out:
            rec["verdict"] = "harness_valid"
        elif "error: patch failed" in out or "does not apply" in out or "unrecognized input" in out:
            rec["verdict"] = "patch_apply_failed"
            rec["tail"] = out[-200:]
        elif "no tests ran" in out:
            rec["verdict"] = "env_error"
            rec["tail"] = "f2p 零收集（路径/依赖缺失）：" + out[-160:]
        elif ("ModuleNotFoundError" in out or "ImportError" in out) and "failed" not in out:
            rec["verdict"] = "env_error"
            rec["tail"] = out[-200:]
        else:
            # gold 后 f2p 仍未全绿 = 真翻转失败（预注册门禁语义的 per-instance 复核）
            rec["verdict"] = "f2p_not_fixed"
            rec["tail"] = out[-220:]
        sh([DOCKER, "rm", "-f", container], timeout=60)
        rec["elapsed_s"] = round(time.time() - t0, 1)
        return rec
    finally:
        sh(["git", "-C", str(repo_dir), "worktree", "remove", str(wt), "--force"], timeout=60)
        sh(["git", "-C", str(repo_dir), "worktree", "prune"], timeout=60)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--instances", default=str(_INSTANCES))
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="smoke：只跑前 N 任务")
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--tag", default="s0", help="容器名标签（多进程并行时区分）")
    ap.add_argument("--repo", default="", help="只跑指定 repo（ansible/openlibrary/qutebrowser）")
    args = ap.parse_args()

    with open(args.instances, encoding="utf-8") as _fh:
        rows = [json.loads(line) for line in _fh if line.strip()]
    mine = rows[args.offset : (args.offset + args.limit) if args.limit else len(rows)]
    if args.repo:
        mine = [r for r in mine if r["repo"].split("/")[-1] == args.repo]
    print(
        f"[info] G8 门禁 per-instance 验证：{len(mine)} 任务（tag={args.tag} repo={args.repo or 'ALL'}）",
        file=sys.stderr,
        flush=True,
    )

    records = []
    for r in mine:
        print(f"[gate] {r['instance_id'][:60]} ...", flush=True)
        records.append(gate_one(r, Path("/tmp/g8_gate"), args.tag))

    from collections import Counter

    c = Counter(x["verdict"] for x in records)
    Path(args.out).write_text(
        json.dumps({"summary": dict(c), "records": records}, ensure_ascii=False, allow_nan=False, indent=1),
        encoding="utf-8",
    )
    print(json.dumps(dict(c), ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
