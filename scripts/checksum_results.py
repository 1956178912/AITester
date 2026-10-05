#!/usr/bin/env python3
"""G6-lite（2026-10-05 优化批次·T6）：实验结果工件 SHA256 清单生成 / 校验。

背景（审查 G6）：
    experiments/results/ 下 149+ 个结果 JSON 全部未入 git——主批次工件只在
    本地磁盘，无任何完整性锚点。本脚本提供最小闭环：
    - --write：对结果目录生成 SHA256SUMS（排除清单文件自身），随批次工件
      一起归档 / 上传（Zenodo / LFS / 论文附件）；
    - --verify：按清单逐文件校验（缺失 / 多余 / 哈希不符分别报告），
      供复现流程（reproduce.sh / Dockerfile.repro）与审稿人核验。

用法：
    python3 scripts/checksum_results.py --write
    python3 scripts/checksum_results.py --verify
    python3 scripts/checksum_results.py --write --results-dir experiments/results/main_batch

退出码：0 = 全过；1 = 校验失败（--verify）或写入失败（--write）。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_NAME = "SHA256SUMS"
# 大文件按 1MiB 分块读取（结果 JSON 多为 KB 级，traces 可能达 MB 级）
_CHUNK = 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _collect(root: Path, manifest: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p != manifest and not p.name.startswith("."))


def write_manifest(results_dir: Path) -> int:
    manifest = results_dir / MANIFEST_NAME
    files = _collect(results_dir, manifest)
    if not files:
        print(f"[FAIL] 目录无可校验文件：{results_dir}")
        return 1
    lines = [f"{_sha256(p)}  {p.relative_to(results_dir).as_posix()}" for p in files]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[INFO] 写入 {manifest}：{len(files)} 个文件，总大小 {sum(p.stat().st_size for p in files)} 字节")
    return 0


def verify_manifest(results_dir: Path) -> int:
    manifest = results_dir / MANIFEST_NAME
    if not manifest.is_file():
        print(f"[FAIL] 清单不存在：{manifest}（先运行 --write）")
        return 1
    recorded: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, _, rel = line.partition("  ")
        recorded[rel.strip()] = digest.strip()

    failures: list[str] = []
    for rel, digest in sorted(recorded.items()):
        path = results_dir / rel
        if not path.is_file():
            failures.append(f"缺失: {rel}")
        elif _sha256(path) != digest:
            failures.append(f"哈希不符: {rel}")
    actual = {p.relative_to(results_dir).as_posix() for p in _collect(results_dir, manifest)}
    failures.extend(f"清单外新增（未记录）: {rel}" for rel in sorted(actual - set(recorded)))

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        print(f"[FAIL] 校验失败：{len(failures)} 项（共 {len(recorded)} 项）")
        return 1
    print(f"[INFO] 校验通过：{len(recorded)} 项全部一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="实验结果工件 SHA256 清单")
    parser.add_argument("--results-dir", default="experiments/results", help="结果目录（相对仓库根或绝对路径）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="生成/刷新 SHA256SUMS")
    mode.add_argument("--verify", action="store_true", help="按 SHA256SUMS 校验")
    args = parser.parse_args(argv)

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = PROJECT_ROOT / results_dir
    if not results_dir.is_dir():
        print(f"[FAIL] 目录不存在：{results_dir}")
        return 1
    return write_manifest(results_dir) if args.write else verify_manifest(results_dir)


if __name__ == "__main__":
    sys.exit(main())
