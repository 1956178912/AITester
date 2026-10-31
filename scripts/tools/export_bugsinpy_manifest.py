#!/usr/bin/env python3
"""导出 BugsInPy manifest JSONL（C8 外部效度小样用，2026-10-31）。

从 BugsInPy 官方 framework 布局（projects/<proj>/bugs/<id>/）导出
BugsInPyDataset 消费的 manifest（字段口径见 dataset_realbugs.py）：
project / bug_id / file_path / buggy_code / fixed_code / test_code /
problem_statement（可选）+ gold_patch（扩展字段，repo 级判定用）。

多文件 bug 的口径：以改动行数最多的文件为 file_path 主文件（LLM 生成
测试的上下文），完整 gold_patch 保留在 gold_patch 字段供 repo 级判定
（swebench_task_judge 协议）使用——单文件上下文截断在批次披露中登记。

用法：
    python scripts/tools/export_bugsinpy_manifest.py \
        --projects PySnooper,sanic \
        --framework-dir ~/.cache/aitester/bugsinpy/framework \
        --repos-dir ~/.cache/aitester/bugsinpy/repos \
        -o ~/.cache/aitester/bugsinpy/bugs_in_py_manifest.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

_DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+?)$")


def _run_git(repo: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)


def _changed_files_with_sizes(patch_text: str) -> list[tuple[str, int]]:
    """从 gold patch 提取改动文件与改动行数（+/− 行合计），按行数降序。"""
    files: list[str] = []
    counts: list[int] = []
    for line in patch_text.splitlines():
        m = _DIFF_HEADER.match(line)
        if m:
            files.append(m.group(2))
            counts.append(0)
        elif files and (line.startswith("+") or line.startswith("-")) and not line.startswith(("+++", "---")):
            counts[-1] += 1
    return sorted(zip(files, counts, strict=False), key=lambda x: -x[1])


def _git_show(repo: str, commit: str, path: str) -> str | None:
    r = _run_git(repo, "show", f"{commit}:{path}")
    return r.stdout if r.returncode == 0 else None


def export_bug(project: str, bug_id: str, framework_dir: str, repos_dir: str) -> dict | None:
    bug_dir = os.path.join(framework_dir, "projects", project, "bugs", bug_id)
    info_path = os.path.join(bug_dir, "bug.info")
    patch_path = os.path.join(bug_dir, "bug_patch.txt")
    if not (os.path.isfile(info_path) and os.path.isfile(patch_path)):
        print(f"[skip] {project}/{bug_id}: bug.info 或 bug_patch.txt 缺失", file=sys.stderr)
        return None

    info: dict[str, str] = {}
    with open(info_path, encoding="utf-8") as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip().strip('"')
    buggy_commit = info.get("buggy_commit_id", "")
    fixed_commit = info.get("fixed_commit_id", "")
    test_file = info.get("test_file", "")
    if not buggy_commit or not fixed_commit:
        print(f"[skip] {project}/{bug_id}: commit 字段缺失", file=sys.stderr)
        return None

    repo = os.path.join(repos_dir, project)
    if not os.path.isdir(repo):
        print(f"[skip] {project}/{bug_id}: repo 未克隆 {repo}", file=sys.stderr)
        return None
    for c in (buggy_commit, fixed_commit):
        if _run_git(repo, "cat-file", "-e", f"{c}^{{commit}}").returncode != 0:
            print(f"[skip] {project}/{bug_id}: commit 不可达 {c[:12]}", file=sys.stderr)
            return None

    with open(patch_path, encoding="utf-8") as f:
        gold_patch = f.read()
    changed = _changed_files_with_sizes(gold_patch)
    if not changed:
        print(f"[skip] {project}/{bug_id}: patch 无可识别改动文件", file=sys.stderr)
        return None
    file_path = changed[0][0]

    buggy_code = _git_show(repo, buggy_commit, file_path)
    fixed_code = _git_show(repo, fixed_commit, file_path)
    if buggy_code is None or fixed_code is None:
        print(f"[skip] {project}/{bug_id}: 主文件 {file_path} 在 commit 上不可读", file=sys.stderr)
        return None

    test_code = _git_show(repo, buggy_commit, test_file) if test_file else None

    return {
        "project": project,
        "bug_id": bug_id,
        "file_path": file_path,
        "buggy_code": buggy_code,
        "fixed_code": fixed_code,
        "test_code": test_code or "",
        "problem_statement": f"BugsInPy {project} bug {bug_id}（{file_path}，{len(changed)} 文件改动）",
        "gold_patch": gold_patch,
        "buggy_commit": buggy_commit,
        "fixed_commit": fixed_commit,
        "python_version": info.get("python_version", ""),
        "test_file": test_file,
        "changed_files": [f for f, _ in changed],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="导出 BugsInPy manifest JSONL")
    ap.add_argument("--projects", required=True, help="逗号分隔项目名（如 PySnooper,sanic）")
    ap.add_argument("--framework-dir", required=True, help="BugsInPy framework 根目录")
    ap.add_argument("--repos-dir", required=True, help="项目仓库克隆根目录")
    ap.add_argument("-o", "--output", required=True, help="输出 manifest JSONL 路径")
    args = ap.parse_args()

    rows: list[dict] = []
    skipped = 0
    for project in [p.strip() for p in args.projects.split(",") if p.strip()]:
        bugs_dir = os.path.join(args.framework_dir, "projects", project, "bugs")
        if not os.path.isdir(bugs_dir):
            print(f"[warn] 项目 bugs 目录不存在: {bugs_dir}", file=sys.stderr)
            continue
        for bug_id in sorted(os.listdir(bugs_dir)):
            row = export_bug(project, bug_id, args.framework_dir, args.repos_dir)
            if row is None:
                skipped += 1
            else:
                rows.append(row)

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    print(f"导出完成: 成功 {len(rows)}, 跳过 {skipped} → {args.output}")
    return 0 if rows else 1


if __name__ == "__main__":
    raise SystemExit(main())
