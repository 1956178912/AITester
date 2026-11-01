#!/usr/bin/env python3
"""judge_b3_docker.py — B3 判定的 docker 驱动版（官方 x86 镜像，arm64 经 Rosetta）。

对每个 instance：docker pull 官方镜像 → 容器内 code/test 物化 → pytest 生成
测试（buggy 红绿翻转口径）→ 判完 docker rmi 释放磁盘。
镜像命名：swebench/sweb.eval.x86_64.{instance_id 大写化双下划线}:latest
（官方 harness 命名规则，swebench 2.1.8）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

DOCKER = "/Applications/Docker.app/Contents/Resources/bin/docker"


def img_name(instance_id: str) -> str:
    return "swebench/sweb.eval.x86_64." + instance_id.upper().replace("__", "__1776__").replace("__", "_s_") + ":latest"


def real_img(instance_id: str) -> str:
    # 官方命名：__ → 1776__（双下划线转义），随后 _ → __……直接用官方规则简化版：
    # sweb.eval.x86_64.<instance_id 大写，__ 保留>:latest（2.1.8 实测命名）
    return f"swebench/sweb.eval.x86_64.{instance_id.upper()}:latest"


def sh(args: list[str], timeout: int = 3600, **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, **kw)


def judge_one(inst: dict, gen: str, workdir: Path) -> dict:
    iid = inst["instance_id"]
    rec: dict = {"task_id": iid}
    t0 = time.time()
    img = real_img(iid)

    # 拉镜像（已存在则跳过）
    r = sh([DOCKER, "image", "inspect", img], timeout=60)
    if r.returncode != 0:
        print(f"[pull] {img} ...", flush=True)
        r = sh([DOCKER, "pull", img], timeout=5400)
        if r.returncode != 0:
            rec["verdict"] = "env_error"
            rec["tail"] = f"pull: {r.stderr[-180:]}"
            return rec

    # 物化生成测试与 code 覆盖脚本
    workdir.mkdir(parents=True, exist_ok=True)
    test_file = workdir / f"{iid.replace('/', '_')}_gen.py"
    test_file.write_text(gen, encoding="utf-8")

    # 容器内：尝试 import 并跑生成测试（测试与 repo 同环境）
    # 官方镜像内 repo 位于 /testbed；生成测试直接放 /testbed 下跑
    container = f"b3judge_{iid.replace('/', '_')}"
    sh([DOCKER, "rm", "-f", container], timeout=60)
    # 将生成测试拷入容器 /testbed
    r_cp = sh([DOCKER, "run", "--name", container, "-d", img, "sleep", "infinity"], timeout=120)
    if r_cp.returncode != 0:
        rec["verdict"] = "env_error"
        rec["tail"] = f"run: {r_cp.stderr[-150:]}"
        return rec
    sh([DOCKER, "cp", str(test_file), f"{container}:/testbed/_gen_test.py"], timeout=60)
    # 跑生成测试（testbed 内 pytest——镜像含 conda testbed env）
    cmd = "source activate testbed 2>/dev/null || conda activate testbed; cd /testbed && python -m pytest _gen_test.py -q --no-header -W ignore::DeprecationWarning -x 2>&1 | tail -5"
    r_run = sh([DOCKER, "exec", container, "bash", "-lc", cmd], timeout=600)
    out = (r_run.stdout or "") + (r_run.stderr or "")
    rec["verdict"] = "green" if r_run.returncode == 0 else "red"
    rec["tail"] = out[-200:]
    rec["wall_s"] = round(time.time() - t0, 1)
    sh([DOCKER, "rm", "-f", container], timeout=60)
    sh([DOCKER, "rmi", img], timeout=300)  # 判完删镜像释放磁盘
    return rec


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
        records.append(judge_one(inst, gen, Path("/tmp/b3_docker")))

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
