#!/usr/bin/env python3
"""G6-lite（2026-10-05 优化批次·T6）：实验结果工件 SHA256 清单生成 / 校验。

背景（审查 G6）：
    experiments/results/ 下 149+ 个结果 JSON 全部未入 git——主批次工件只在
    本地磁盘，无任何完整性锚点。本脚本提供最小闭环：
    - --write：对结果目录生成 SHA256SUMS（排除清单文件自身），随批次工件
      一起归档 / 上传（Zenodo / LFS / 论文附件）；
    - --verify：按清单逐文件校验（缺失 / 多余 / 字节不符分别报告），
      供复现流程（reproduce.sh / Dockerfile.repro）与审稿人核验。

口径（2026-10-18 第三方审查 A17/A18 修复）：

1. **字节口径与换行诊断（A17）**：本门禁校验的是**原始字节** sha256。证据工件
   的换行策略由仓库根 ``.gitattributes`` 固定（``experiments/results/**`` 与
   ``docs/reviews/review_recompute/**`` 设 ``-text``，检出字节 = 入库字节 = LF），
   因此任何平台（含 Windows ``core.autocrlf=true``）的干净检出都应按原始字节
   一致。若受检文件仅换行符与记录不同（例如 Windows 换行约定把 LF 转成 CRLF），
   ``--verify`` 单独报告为 **EOL 差异**并以 0 退出（不误判为篡改）；内容确有
   变化仍判失败。需要"严格按字节、EOL 差异也算失败"时用 ``--strict-bytes``
   （适用于确认检出换行策略已生效后的发布闸）。
2. **清单只覆盖实际分发文件（A18）**：``--write``/``--verify`` 统一排除
   ``__pycache__`` 等 Python 字节码缓存（历史上 p/r/s 轮清单曾记录未分发的
   ``_helpers/__pycache__/*.pyc``，干净检出必然报缺失）；另可用 ``--exclude``
   追加排除模式（按相对路径的 fnmatch，例如只在本机留档、不随包分发的日志）。

用法：
    python3 scripts/gates/checksum_results.py --write
    python3 scripts/gates/checksum_results.py --verify
    python3 scripts/gates/checksum_results.py --verify --strict-bytes
    python3 scripts/gates/checksum_results.py --write --results-dir experiments/results/main_batch
    python3 scripts/gates/checksum_results.py --write --exclude '*.local.log' --results-dir <dir>

退出码：0 = 全过；1 = 校验失败（--verify）或写入失败（--write）。
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_NAME = "SHA256SUMS"
# 仓内存在外部工具（`shasum -a 256`）生成的 `SHA256SUMS.txt` 变体清单：
# `--verify` 按此优先级解析（--write 仍统一写规范名 SHA256SUMS）。
MANIFEST_NAMES: tuple[str, ...] = (MANIFEST_NAME, "SHA256SUMS.txt")
# 大文件按 1MiB 分块读取（结果 JSON 多为 KB 级，traces 可能达 MB 级）
_CHUNK = 1024 * 1024

# A18：Python 字节码缓存目录/后缀——本地运行 helper 时生成的解释器缓存从不随
# 批次工件分发（.gitignore 亦全局忽略），写入清单会在干净检出上必然报缺失。
_NON_DISTRIBUTED_DIR_PARTS = frozenset({"__pycache__"})
_NON_DISTRIBUTED_SUFFIXES = (".pyc", ".pyo", ".pyd")
# EOL 诊断时最多逐条打印的文件数（避免 Windows 全量检出刷出数千行日志）
_EOL_SAMPLE_LIMIT = 10


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_non_distributed(path: Path, root: Path, excludes: tuple[str, ...] = ()) -> bool:
    """是否为不分发文件（字节码缓存/调用方显式排除模式）。"""
    rel = path.relative_to(root)
    if any(part in _NON_DISTRIBUTED_DIR_PARTS for part in rel.parts[:-1]):
        return True
    if rel.name.endswith(_NON_DISTRIBUTED_SUFFIXES):
        return True
    if excludes:
        rel_posix = rel.as_posix()
        return any(fnmatch.fnmatch(rel_posix, pattern) for pattern in excludes)
    return False


def _collect(root: Path, manifest: Path, excludes: tuple[str, ...] = ()) -> list[Path]:
    """收集待校验文件：排除清单自身、隐藏路径、缓存字节码与显式排除模式。

    隐藏目录（如工装在本地的 ``.mimosa/`` hook-state）不会入库，fresh clone
    不含这些文件；若写入清单，CI ``--verify`` 在干净检出上必然报"缺失"。
    2026-10-16 修复：此前仅按 basename 排除，漏掉 ``.mimosa/xx.json`` 这类
    "点目录 + 常规文件名" 的路径——主批次清单曾因此含 2 条永不入库的
    .mimosa 条目，使 U1 门禁在 fresh clone 下必红（本地不可见）。
    A18 修复：``__pycache__`` / ``*.pyc`` 等解释器缓存不是分发文件，一律排除；
    ``excludes`` 允许调用方补充排除（fnmatch，匹配相对 root 的 POSIX 路径）。
    """
    files: list[Path] = []
    for p in root.rglob("*"):
        if not p.is_file() or p == manifest:
            continue
        if any(part.startswith(".") for part in p.relative_to(root).parts):
            continue
        if _is_non_distributed(p, root, excludes):
            continue
        files.append(p)
    return sorted(files)


def _excluded_count(root: Path, manifest: Path, excludes: tuple[str, ...]) -> int:
    """统计被缓存/排除规则跳过的文件数（仅供 --write 输出审计信息）。"""
    return sum(
        1
        for p in root.rglob("*")
        if p.is_file()
        and p != manifest
        and not any(part.startswith(".") for part in p.relative_to(root).parts)
        and _is_non_distributed(p, root, excludes)
    )


def write_manifest(results_dir: Path, excludes: tuple[str, ...] = ()) -> int:
    manifest = results_dir / MANIFEST_NAME
    files = _collect(results_dir, manifest, excludes)
    if not files:
        print(f"[FAIL] 目录无可校验文件：{results_dir}")
        return 1
    lines = [f"{_sha256(p)}  {p.relative_to(results_dir).as_posix()}" for p in files]
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    skipped = _excluded_count(results_dir, manifest, excludes)
    extra = f"，跳过 {skipped} 个非分发文件（缓存/--exclude）" if skipped else ""
    print(f"[INFO] 写入 {manifest}：{len(files)} 个文件，总大小 {sum(p.stat().st_size for p in files)} 字节{extra}")
    return 0


def _normalized_rel(rel: str) -> str:
    """清单路径写法归一（POSIX 语义下指向同一文件的三种写法）。

    T 轮 2026-10-18（审计 P2-14）：`shasum` 生成的清单可能带 `./` 前缀（相对
    当前目录）或 `sha256sum -b` 的二进制标记 `*`；Windows 工具链可能写反斜杠。
    三者 POSIX 语义下指向同一文件，不归一化会把"格式差异"误报成"缺失/清单外
    新增"（实测：emse_docstring_anchor_20261017 的 165 条 `./` 前缀清单被
    --verify 全判缺失，而 `shasum -c` 165/165 OK）。
    """
    rel = rel.strip()
    if rel.startswith("*"):
        rel = rel[1:]
    while rel.startswith("./"):
        rel = rel[2:]
    return rel.replace("\\", "/")


def _read_manifest(manifest: Path) -> dict[str, str]:
    recorded: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        digest, _, rel = line.partition("  ")
        recorded[_normalized_rel(rel)] = digest.strip()
    return recorded


def _resolve_manifest(results_dir: Path) -> Path:
    """返回目录内的清单路径（优先规范名 SHA256SUMS，其次外部工具 SHA256SUMS.txt）。"""
    for name in MANIFEST_NAMES:
        candidate = results_dir / name
        if candidate.is_file():
            return candidate
    return results_dir / MANIFEST_NAME


def verify_manifest(results_dir: Path, strict_bytes: bool = False, excludes: tuple[str, ...] = ()) -> int:
    """按 SHA256SUMS 校验目录工件。

    Args:
        results_dir: 受检目录（含 SHA256SUMS）。
        strict_bytes: True 时"仅换行符不同"也按失败处理（发布/归档字节闸）；
            默认 False——EOL 差异单独报告并视为通过（A17：不把换行约定误判
            为内容篡改，同时保留内容篡改检测）。
        excludes: 与 --write 同口径的显式排除模式（fnmatch，相对路径）。

    Returns:
        0 = 通过（默认口径下 EOL 差异不计失败）；1 = 存在缺失/内容不符/
        清单外新增（strict_bytes 时含 EOL 差异）。
    """
    manifest = _resolve_manifest(results_dir)
    if not manifest.is_file():
        print(f"[FAIL] 清单不存在：{results_dir / MANIFEST_NAME}（先运行 --write）")
        return 1
    recorded = _read_manifest(manifest)

    failures: list[str] = []
    eol_only: list[str] = []
    raw_ok = 0
    for rel, digest in sorted(recorded.items()):
        path = results_dir / rel
        if not path.is_file():
            failures.append(f"缺失: {rel}")
            continue
        content = path.read_bytes()
        if _sha256_bytes(content) == digest:
            raw_ok += 1
            continue
        # A17：区分"仅换行符不同"与"内容不符"（保持内容篡改检测）。
        # 方向 1：现有文件为 CRLF、记录按 LF 计算（Windows autocrlf=true 检出）；
        # 方向 2：现有文件为 LF、记录按 CRLF 计算（外部 Windows 工具生成的清单）。
        if _sha256_bytes(content.replace(b"\r\n", b"\n")) == digest:
            eol_only.append(rel)
            continue
        if _sha256_bytes(content.replace(b"\n", b"\r\n")) == digest:
            eol_only.append(rel)
            continue
        # 诊断措辞保留历史 "哈希不符" 关键字（既有门禁日志/测试契约），
        # 括号内标明已排除 EOL-only 情形。
        failures.append(f"哈希不符（内容不一致，非换行差异）: {rel}")

    actual = {p.relative_to(results_dir).as_posix() for p in _collect(results_dir, manifest, excludes)}
    failures.extend(f"清单外新增（未记录）: {rel}" for rel in sorted(actual - set(recorded)))

    if eol_only:
        # A17：默认不判失败，但必须显式报告（否则"通过"会掩盖跨平台检出差异）。
        print(
            f"[WARN] EOL 差异：{len(eol_only)} 项文件的记录摘要与原始字节不符、"
            f"仅换行符归一后一致（换行约定问题，不计为篡改；"
            f"证据工件字节策略见仓库根 .gitattributes；--strict-bytes 可强制按字节失败）"
        )
        for rel in eol_only[:_EOL_SAMPLE_LIMIT]:
            print(f"[WARN]   EOL-only: {rel}")
        if len(eol_only) > _EOL_SAMPLE_LIMIT:
            print(f"[WARN]   …（其余 {len(eol_only) - _EOL_SAMPLE_LIMIT} 项同形态）")

    if failures:
        for f in failures:
            print(f"[FAIL] {f}")
        print(f"[FAIL] 校验失败：{len(failures)} 项（共 {len(recorded)} 项）")
        return 1
    if eol_only and strict_bytes:
        print(
            f"[FAIL] --strict-bytes：{len(eol_only)} 项仅 EOL 差异也判失败"
            f"（共 {len(recorded)} 项）；如确认是跨平台检出换行，请按 .gitattributes 重检"
        )
        return 1

    summary = f"{len(recorded)} 项一致"
    if eol_only:
        summary = f"{raw_ok} 项原始字节一致 + {len(eol_only)} 项 EOL 差异（不计篡改）"
    print(f"[INFO] 校验通过：{summary}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="实验结果工件 SHA256 清单")
    parser.add_argument("--results-dir", default="experiments/results", help="结果目录（相对仓库根或绝对路径）")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--write",
        action="store_true",
        help="生成/刷新 SHA256SUMS（排除 __pycache__ 等非分发文件）",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="按 SHA256SUMS 校验（缺失/清单外新增/内容不符判失败；EOL 差异默认仅告警）",
    )
    parser.add_argument(
        "--strict-bytes",
        action="store_true",
        help="--verify 附属：仅 EOL 差异也判失败（发布/归档严格字节闸）",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="--write/--verify 追加排除模式（fnmatch，相对受检目录的 POSIX 路径；可重复）",
    )
    args = parser.parse_args(argv)
    if args.write and args.strict_bytes:
        print("[FAIL] --strict-bytes 仅用于 --verify")
        return 1

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = PROJECT_ROOT / results_dir
    if not results_dir.is_dir():
        print(f"[FAIL] 目录不存在：{results_dir}")
        return 1
    excludes = tuple(args.exclude)
    if args.write:
        return write_manifest(results_dir, excludes)
    if args.verify:
        return verify_manifest(results_dir, strict_bytes=args.strict_bytes, excludes=excludes)
    # 互斥组声明为 required=True，正常走不到这里；留着是因为「模式由开关自己选」才是这条判据的
    # 保证来源——若有人摘掉 required= 或往组里加第三个模式，缺分支时要报错退出，而不是静默校验。
    print("[FAIL] 未选择模式：--write 与 --verify 必须显式给出一个")
    return 2


if __name__ == "__main__":
    sys.exit(main())
