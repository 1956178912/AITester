#!/usr/bin/env python3
"""修复覆盖率缺口审计：找出"修复新增但从未被测试执行"的代码行。

## 动机

2026-10-19 的审计发现：V/W 两轮第三方评审的 P1 修复中，有一批分支虽然
代码正确、接口也在，但**从未被任何测试执行**——一旦回退，全套 9000+ 测试
无一告警。这正是 `73481bb` 之后 A07/A09/A10 被第二轮评审抓到的复发模式
（"修复覆盖主路径、漏掉分支路径"）。本脚本把该检查固化为可重跑的工具。

## 口径

- **基线**：`--base`（默认 `ff15a2f`，即 V 轮修复起点）；
- **新增行**：`git diff --unified=0 <base> HEAD -- src/` 中 `+` 侧的行号
  （HEAD 行号）；
- **可执行行**：**以 `coverage.xml` 的 `<line>` 条目为唯一权威**，不自行用
  字节码/正则推断——coverage 用真实 trace 行事件判定，已排除 docstring、
  跨行函数签名的参数行、多行字面量；自建判定会把 `def` 的每行参数误算成
  可执行行（实测假阳性 885/1400，占 63%）；
- **缺口**：新增行中 hits==0 的行。

注意：`coverage.xml` 必须由**当前 HEAD 代码**产出（`make test-cov`）。
旧数据行号会与代码错位，把未改动行误报为缺口。

## 用法

    make test-cov                     # 先产出与 HEAD 对齐的 coverage.xml
    python scripts/tools/audit_fix_coverage.py
    python scripts/tools/audit_fix_coverage.py --base ff15a2f --json out.json

退出码：0 = 执行完成（**有缺口也返回 0**，本工具是审计而非门禁）。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
DEFAULT_BASE = "ff15a2f"
DEFAULT_COVERAGE_XML = PROJECT_ROOT / "coverage.xml"


def added_lines_by_file(base: str, root: Path, pathspec: str = "src/") -> dict[str, list[int]]:
    """解析 git diff，返回 ``{仓内相对路径: [HEAD 中新增行号...]}``。

    含注释/docstring 行（未过滤）——由调用方用 coverage 行集合过滤。
    """
    out = subprocess.run(
        ["git", "diff", "--unified=0", base, "HEAD", "--", pathspec],
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
    ).stdout

    result: dict[str, list[int]] = defaultdict(list)
    cur_file: str | None = None
    new_ln = 0
    for line in out.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:]
            continue
        m = HUNK_RE.match(line)
        if m:
            new_ln = int(m.group(1))
            continue
        if cur_file is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            result[cur_file].append(new_ln)
            new_ln += 1
        elif line.startswith("-") and not line.startswith("---"):
            continue  # 删除行不占 HEAD 行号
        elif not line.startswith("\\"):
            new_ln += 1
    return dict(result)


def coverage_lines(xml_path: Path, prefix: str = "src/") -> dict[str, dict[int, int]]:
    """解析 coverage.xml，返回 ``{仓内路径: {行号: hits}}``。

    coverage 的 ``filename`` 相对 ``source``（``--cov=src`` 时为 ``src``，
    ``--cov=experiments`` 时为 ``experiments``），故按 ``prefix`` 补前缀。
    """
    tree = ET.parse(xml_path)
    result: dict[str, dict[int, int]] = {}
    for cls in tree.iter("class"):
        fname = cls.get("filename") or ""
        if not fname.endswith(".py"):
            continue
        bucket = result.setdefault(prefix + fname, {})
        for ln in cls.iter("line"):
            number = ln.get("number")
            if number is None:
                continue
            bucket[int(number)] = int(ln.get("hits") or 0)
    return result


def audit(base: str, xml_path: Path, root: Path, pathspec: str = "src/") -> dict[str, Any]:
    """执行审计，返回结构化结果（供 CLI 与测试共用）。

    Args:
        base: 修复起点提交。
        xml_path: 与该 HEAD 对齐的 coverage.xml。
        root: 仓库根。
        pathspec: 审计范围前缀（``src/`` 或 ``experiments/``），同时用于
            还原 coverage.xml 的相对路径前缀。
    """
    added = added_lines_by_file(base, root, pathspec)
    cov = coverage_lines(xml_path, pathspec)

    files: list[dict[str, Any]] = []
    total_added = total_uncovered = 0
    for rel, lines in sorted(added.items()):
        hits = cov.get(rel)
        if hits is None:
            files.append(
                {"file": rel, "added": 0, "uncovered": 0, "missing_lines": [], "note": "未被 coverage 测量"}
            )
            continue
        effective = [ln for ln in lines if ln in hits]
        uncovered = [ln for ln in effective if hits[ln] == 0]
        total_added += len(effective)
        total_uncovered += len(uncovered)
        files.append(
            {"file": rel, "added": len(effective), "uncovered": len(uncovered), "missing_lines": uncovered}
        )

    return {
        "base": base,
        "pathspec": pathspec,
        "coverage_xml": str(xml_path),
        "total_added": total_added,
        "total_uncovered": total_uncovered,
        "ratio": round(total_uncovered / total_added, 4) if total_added else 0.0,
        "files": files,
    }


def render(result: dict[str, Any]) -> str:
    lines = [
        f"基线 {result['base']} → HEAD；{result['pathspec']} 修复新增且被 coverage 测量的行 "
        f"{result['total_added']}，其中未执行 {result['total_uncovered']}"
        f"（{result['ratio']:.2%}）",
        "",
        f"{'':<3}{'文件':<42}{'新增':>6}{'未覆盖':>7}  未覆盖行号",
    ]
    for item in result["files"]:
        flag = "!!" if item["uncovered"] else "  "
        detail = item.get("note") or ", ".join(str(n) for n in item["missing_lines"][:25])
        lines.append(f"{flag} {item['file']:<42}{item['added']:>6}{item['uncovered']:>7}  {detail}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default=DEFAULT_BASE, help=f"修复起点提交（默认 {DEFAULT_BASE}）")
    parser.add_argument(
        "--pathspec",
        default="src/",
        help="审计范围前缀，须与 --coverage-xml 的 --cov 目标一致（src/ 或 experiments/）",
    )
    parser.add_argument(
        "--coverage-xml", default=str(DEFAULT_COVERAGE_XML), help="coverage.xml 路径（须与 HEAD 对齐）"
    )
    parser.add_argument("--json", default="-", help="JSON 输出路径（默认 - = 不输出）")
    args = parser.parse_args()

    xml_path = Path(args.coverage_xml)
    if not xml_path.is_file():
        print(f"错误：找不到 {xml_path}——先跑 `make test-cov` 产出与 HEAD 对齐的覆盖率", file=sys.stderr)
        return 2

    result = audit(args.base, xml_path, PROJECT_ROOT, args.pathspec)
    print(render(result))

    if args.json != "-":
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON 已写入 {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
