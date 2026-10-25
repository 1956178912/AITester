#!/usr/bin/env python3
"""文档命令可执行性门禁：文档里引用的脚本路径与 `make` 目标必须真的存在。

## 为什么需要它（CS 轮教训的直接落地）

CS 轮实测抓到一处**登记面失实**：`docs/study/PAPER_CITATION_KEYS.md` 写着「重跑导出脚本」，
而**那个脚本并不存在**——文档指向一个不存在的工件，维护者按文档操作必然落空，只能手改。
同型问题在 CK 轮也出现过一次（`CITATION.cff` 写「已备：experiments/results/zenodo_metadata.json」，
该文件不在盘）。

这类失实**没有任何机制**能发现：链接检查器只查 markdown 链接，不查代码块里的命令；
「命令能跑」是读者在踩坑之后才会知道的���本轮把它变成可执行判据。

## 判据

1. **脚本路径**：文档中出现的 `scripts/....py` 形态路径必须存在于仓库；
2. **`make` 目标**：文档中出现的 `make <target>` 的 `<target>` 必须是 Makefile 里真实存在的目标；
3. **只认命令位**：命令必须出现在**代码块内**或**行首**（可选 `$ ` 前缀）——否则英文散文里的
   "make the" 这类短语会被当成命令（CU 轮实测：行首扫描把散文里的 "make the/that/sure"
   误报成 3 处不存在的 make 目标）。

## 范围

`README.md` / `README.en.md` / `QUICKSTART.md` / `QUICKSTART.en.md` / `REPLICATION.md` /
`MODEL_CARD.md` / `CONTRIBUTING.md` / `docs/adr/*.md`。
不扫 `docs/history/`（历史快照不可回写）与 `experiments/`（批次工件）。

退出码：`0` = 全部存在（可含 notes）；`1` = 有指向不存在工件/目标的引用；`2` = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

#: 纳入扫描的文档（相对仓库根）。
DOC_GLOBS: tuple[str, ...] = (
    "README.md",
    "README.en.md",
    "QUICKSTART.md",
    "QUICKSTART.en.md",
    "REPLICATION.md",
    "MODEL_CARD.md",
    "CONTRIBUTING.md",
    "docs/adr/*.md",
)
#: 不扫描的目录片段（历史快照 / 批次工件 / 机器本地目录）。
SKIP_PARTS = frozenset({".git", ".workbuddy", ".private", ".venv", "node_modules", "history", "experiments"})

_SCRIPT_PATH = re.compile(r"(?<![\w/])((?:\./)?scripts/[\w./-]+\.py)")
#: `make <target>` 只认**整行**形态：行首是 make、target 之后只允许 flag。
#: 否则英文散文里的 "make sure the `target_file` path is correct" 会被误判成
#: 一个不存在的 make 目标（CU 轮实测：行内扫描误报 3 处）。
_MAKE_CMD = re.compile(r"^make\s+([a-z][a-z0-9_-]*)\s*((?:-{1,2}[^\s]+\s*)*)$")
_MAKE_TARGET_DEF = re.compile(r"^([a-zA-Z][a-zA-Z0-9_-]*):", re.M)
_CODE_FENCE = re.compile(r"^\s*```")


def _command_lines(text: str) -> list[tuple[int, str]]:
    """取出「命令位」的行：(行号, 行内容)。

    - 代码块内的所有非空行都算命令位；
    - 代码块外，只有**行首**（允许 `$ ` / `> ` 前缀）的行算命令位——散文里出现在句中的
      "make the" 不算。
    """
    out: list[tuple[int, str]] = []
    in_block = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if _CODE_FENCE.match(raw):
            in_block = not in_block
            continue
        if in_block:
            if raw.strip():
                out.append((lineno, raw.strip()))
            continue
        stripped = raw.strip()
        # 只剥 shell 提示符 `$ `；**不剥 `> `**——那是 Markdown 引用块，
        # 里面的英文散文（"make the same direction"）会被误判成 make 目标。
        if stripped.startswith("$ "):
            stripped = stripped[2:].strip()
        elif stripped.startswith(">"):
            continue
        if stripped:
            out.append((lineno, stripped))
    return out


def _makefile_targets(root: Path) -> set[str]:
    makefile = root / "Makefile"
    if not makefile.exists():
        return set()
    return set(_MAKE_TARGET_DEF.findall(makefile.read_text(encoding="utf-8")))


def _doc_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for pattern in DOC_GLOBS:
        for path in sorted(root.glob(pattern)):
            if SKIP_PARTS & set(path.parts):
                continue
            files.append(path)
    return files


def check(root: Path = PROJECT_ROOT) -> dict[str, object]:
    """返回 {"missing": [...], "checked": int, "docs": [...]}。"""
    targets = _makefile_targets(root)
    missing: list[dict[str, object]] = []
    checked = 0
    docs = [str(p.relative_to(root)) for p in _doc_files(root)]
    for path in _doc_files(root):
        text = path.read_text(encoding="utf-8", errors="replace")
        for lineno, line in _command_lines(text):
            for match in _SCRIPT_PATH.finditer(line):
                checked += 1
                rel = match.group(1).lstrip("./")
                if not (root / rel).exists():
                    missing.append(
                        {
                            "file": str(path.relative_to(root)),
                            "line": lineno,
                            "kind": "script",
                            "ref": match.group(1),
                            "context": line[:120],
                        }
                    )
            match = _MAKE_CMD.match(line)
            if match:
                checked += 1
                target = match.group(1)
                if target not in targets:
                    missing.append(
                        {
                            "file": str(path.relative_to(root)),
                            "line": lineno,
                            "kind": "make-target",
                            "ref": f"make {target}",
                            "context": line[:120],
                        }
                    )
    return {"missing": missing, "checked": checked, "docs": docs, "makefile_targets": len(targets)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="文档命令可执行性门禁")
    parser.add_argument("--root", default=str(PROJECT_ROOT), help="仓库根（默认项目根）")
    parser.add_argument("--json", default="-", help="JSON 输出路径（默认 - = 不输出）")
    args = parser.parse_args(argv)

    result = check(Path(args.root))
    missing = result["missing"]
    print(
        f"[doc-commands] 扫了 {result['checked']} 处命令引用（{len(result['docs'])} 份文档，"
        f"Makefile {result['makefile_targets']} 个目标）"
    )
    if missing:
        print(f"[doc-commands] 阻断：{len(missing)} 处引用指向不存在的工件/目标")
        for item in missing:
            print(f"  {item['file']}:L{item['line']}  {item['kind']}  {item['ref']}")
            print(f"      ← {item['context']}")
    else:
        print("[doc-commands] 通过：文档引用的脚本与 make 目标全部存在")
    if args.json and args.json != "-":
        Path(args.json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False),
            encoding="utf-8",
        )
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
