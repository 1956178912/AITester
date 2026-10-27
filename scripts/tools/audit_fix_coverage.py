#!/usr/bin/env python3
"""修复覆盖率缺口审计：找出"修复新增但从未被测试执行"的代码行。

## 动机

2026-10-19 的审计发现：V/W 两轮第三方评审的 P1 修复中，有一批分支虽然
代码正确、接口也在，但**从未被任何测试执行**——一旦回退，全套 9000+ 测试
无一告警。这正是 `73481bb` 之后 A07/A09/A10 被第二轮评审抓到的复发模式
（"修复覆盖主路径、漏掉分支路径"）。本脚本把该检查固化为可重跑的工具。

## 口径

- **基线**：`--base`（默认 `auto` = **最近一次改动审计范围的提交**，即「本次修复」的语义化起点；
  可显式给提交号）。**CS 轮更正**：默认值原为 `ff15a2f`（V 轮修复起点），距今已 50+ 轮 ⇒
  默认跑出来的「新增行」几乎覆盖整个 `src/`，输出是「整仓未覆盖」的**噪声**（真读数：几十个
  文件的未覆盖计数全为 0 命中），没有诊断价值——这也是该工具长期无人跑的主因；
  改为 `auto` 后默认口径回到「本次修复引入的行」。
- **新增行**：`git diff --unified=0 <base> HEAD -- src/` 中 `+` 侧的行号
  （HEAD 行号）；
- **可执行行**：**以 `coverage.xml` 的 `<line>` 条目为唯一权威**，不自行用
  字节码/正则推断——coverage 用真实 trace 行事件判定，已排除 docstring、
  跨行函数签名的参数行、多行字面量；自建判定会把 `def` 的每行参数误算成
  可执行行（实测假阳性 885/1400，占 63%）；
- **缺口**：新增行中 hits==0 的行。
- **未测量**（FE 轮）：本作用域的文件**根本没被 coverage.xml 测量**（例如 `--pathspec experiments/`
  配 `--cov=src` 产出的 coverage.xml）。**「未测量」不等于「零缺口」**——FE 轮修掉的正是这个
  沉默零：改前此类情形会被读成「新增 0 行 / 未执行 0 行 / 0.00%」并以 rc=0 通过，
  与 FC 轮 champion 守卫「无观测被读作 0」同族。现要求：**作用域内存在未测量文件 ⇒ rc=1**
  （判决的输入不完整 ⇒ 判决不可信），并在输出中单列未测量清单。
- **已在本进程之外验证**（FD 轮）：判决面是**父进程**的 `coverage.xml`，**子进程**里跑的测试对它不可见——ED 轮那批「可选依赖装上但坏了」的负控制正是在子进程里验证的。这类路径登记在 `docs/fix_coverage_verified_elsewhere.txt`，从缺口清单剔除并单列；若登记行的**内容锚点**在该文件里已消失（内容被改写），登记即**失效**，审计以 rc=1 判红并要求重新判定。

注意：`coverage.xml` 必须由**当前 HEAD 代码**产出（`make test-cov`）。
旧数据行号会与代码错位，把未改动行误报为缺口。

## 用法

    make test-cov                     # 先产出与 HEAD 对齐的 coverage.xml
    python scripts/tools/audit_fix_coverage.py
    python scripts/tools/audit_fix_coverage.py --base ff15a2f --json out.json

退出码：0 = 执行完成（**有缺口也返回 0**，本工具是审计而非门禁）；
1 = **登记表畸形或失效**（登记完整性是判决的输入，坏了就不能继续出判决）。
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
#: `auto` = 最近一次改动审计范围的提交（修复起点的语义化默认；CS 轮取代写死的 V 轮起点）。
DEFAULT_BASE = "auto"
DEFAULT_COVERAGE_XML = PROJECT_ROOT / "coverage.xml"
#: 「已在本进程之外验证」的路径登记表（FD 轮）：子进程里验证的路径对父进程 coverage 不可见。
DEFAULT_REGISTRY = PROJECT_ROOT / "docs" / "fix_coverage_verified_elsewhere.txt"
#: 登记表语法：`<路径>:<行号> @<内容锚点>  # <理由>`（锚点为该行内容的唯一片段）。
_REGISTRY_LINE = re.compile(
    r"^(?P<path>[A-Za-z0-9_./-]+\.py):(?P<line>\d+)\s*@(?P<anchor>.+?)\s*(?:#\s*(?P<reason>.*))?$"
)


def resolve_base(base: str, root: Path, pathspec: str = "src/") -> str:
    """把 `base` 解析成具体提交号。

    `base == "auto"` ⇒ 取**最近一次改动 `pathspec` 的提交**（`git log -1 -- pathspec`）——
    这正是「本次修复的起点」的语义。解析不出（仓库无该路径历史）⇒ 返回空串，由调用方
    明确报错，不静默回落到某个写死的历史提交。
    """
    if base != "auto":
        return base
    proc = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", pathspec],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip()


def load_registry(path: Path | None) -> tuple[dict[tuple[str, int], tuple[str, str]], list[str]]:
    """解析「已在本进程之外验证」登记表。

    语法：``<路径>:<行号> @<内容锚点>  # <理由>``。

    Returns:
        ``(entries, errors)``——``entries[(路径, 行号)] = (锚点, 理由)``；
        ``errors`` 为畸形行（语法不符 / 缺理由 / 路径不存在）的可读描述。
    """
    if path is None:
        return {}, []
    if not path.is_file():
        return {}, [f"{path} 缺席：登记表是判决的输入，缺它就不能把「已验证」与「缺口」分开"]
    entries: dict[tuple[str, int], tuple[str, str]] = {}
    errors: list[str] = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _REGISTRY_LINE.match(line)
        if not match:
            errors.append(f"{path}:{lineno} 登记语法不符（应为 `<路径>:<行号> @<锚点>  # <理由>`）：{line}")
            continue
        reason = (match.group("reason") or "").strip()
        if not reason:
            errors.append(f"{path}:{lineno} 登记缺少理由")
            continue
        key = (match.group("path"), int(match.group("line")))
        if key in entries:
            errors.append(f"{path}:{lineno} 登记重复（{key[0]}:{key[1]} 已在册）")
            continue
        entries[key] = (match.group("anchor"), reason)
    return entries, errors


def anchor_present(root: Path, rel: str, anchor: str) -> bool:
    """锚点内容是否仍存在于该路径的文件里（内容被改写 ⇒ 登记失效）。"""
    target = root / rel
    if not target.is_file():
        return False
    return anchor in target.read_text(encoding="utf-8")


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


def audit(
    base: str,
    xml_path: Path,
    root: Path,
    pathspec: str = "src/",
    registry_path: Path | None = None,
) -> dict[str, Any]:
    """执行审计，返回结构化结果（供 CLI 与测试共用）。

    Args:
        base: 修复起点提交。
        xml_path: 与该 HEAD 对齐的 coverage.xml。
        root: 仓库根。
        pathspec: 审计范围前缀（``src/`` 或 ``experiments/``），同时用于
            还原 coverage.xml 的相对路径前缀。
        registry_path: 「已在本进程之外验证」登记表路径（None = 不启用该分类）。
    """
    resolved = resolve_base(base, root, pathspec)
    if not resolved:
        raise ValueError(f"无法解析 base={base!r}（pathspec={pathspec!r} 无历史提交）")
    added = added_lines_by_file(resolved, root, pathspec)
    cov = coverage_lines(xml_path, pathspec)
    entries, registry_errors = load_registry(registry_path)
    # 登记失效（锚点内容已消失）⇒ 该登记**不再参与分类**：失效登记不得继续把
    # 真缺口藏起来（fail-closed）——否则「登记写错了」会变成「缺口被豁免」。
    stale_keys = {key for key, (anchor, _reason) in entries.items() if not anchor_present(root, key[0], anchor)}
    effective_entries = {key: value for key, value in entries.items() if key not in stale_keys}

    files: list[dict[str, Any]] = []
    total_added = total_uncovered = total_verified = 0
    unmeasured_files: list[str] = []
    unmeasured_added_lines = 0
    for rel, lines in sorted(added.items()):
        hits = cov.get(rel)
        if hits is None:
            # FE 轮：**未测量 ≠ 零缺口**。这些文件的新增行**根本没被测过**——
            # 改前它们被记成「新增 0 / 未覆盖 0」，于是整片未测量会被读成
            # 「0 行缺口（0.00%）」并以 rc=0 通过（与 FC 轮 champion 守卫同族）。
            # 现单列未测量清单，并让它们**不进入分母**（分母只含真被测量的行），
            # 同时把「作用域内存在未测量文件」作为判决不可信的信号上报。
            unmeasured_files.append(rel)
            unmeasured_added_lines += len(lines)
            files.append(
                {
                    "file": rel,
                    "added": 0,
                    "uncovered": 0,
                    "missing_lines": [],
                    "verified_lines": [],
                    "unmeasured": True,
                    "unmeasured_lines": len(lines),
                    "note": "未被 coverage 测量",
                }
            )
            continue
        effective = [ln for ln in lines if ln in hits]
        uncovered = [ln for ln in effective if hits[ln] == 0]
        # FD 轮：登记在册的「已在本进程之外验证」路径不计缺口（子进程里已验证）。
        verified = [ln for ln in uncovered if (rel, ln) in effective_entries]
        gaps = [ln for ln in uncovered if (rel, ln) not in effective_entries]
        total_added += len(effective)
        total_uncovered += len(gaps)
        total_verified += len(verified)
        files.append(
            {
                "file": rel,
                "added": len(effective),
                "uncovered": len(gaps),
                "missing_lines": gaps,
                "verified_lines": verified,
            }
        )

    # 登记失效 = 锚点内容在该路径下已不存在（内容被改写 / 行被删）⇒ 必须重新判定。
    stale: list[str] = [f"{rel}:{ln} @锚点「{entries[(rel, ln)][0]}」" for (rel, ln) in sorted(stale_keys)]

    return {
        "base": resolved,
        "pathspec": pathspec,
        "coverage_xml": str(xml_path),
        "total_added": total_added,
        "total_uncovered": total_uncovered,
        "total_verified_elsewhere": total_verified,
        "total_unmeasured_files": len(unmeasured_files),
        "total_unmeasured_added_lines": unmeasured_added_lines,
        "unmeasured_files": unmeasured_files,
        "ratio": round(total_uncovered / total_added, 4) if total_added else 0.0,
        "files": files,
        "registry_errors": registry_errors,
        "registry_stale": stale,
    }


def render(result: dict[str, Any]) -> str:
    unmeasured = result.get("unmeasured_files") or []
    unmeasured_lines = result.get("total_unmeasured_added_lines") or 0
    scope_note = (
        f"（**另有 {len(unmeasured)} 个文件 / {unmeasured_lines} 行未被测量，未计入分母**）" if unmeasured else ""
    )
    lines = [
        f"基线 {result['base']} → HEAD；{result['pathspec']} 修复新增且被 coverage 测量的行 "
        f"{result['total_added']}，其中未执行 {result['total_uncovered']}"
        f"（{result['ratio']:.2%}）{scope_note}",
        "",
        f"{'':<3}{'文件':<42}{'新增':>6}{'未覆盖':>7}  未覆盖行号",
    ]
    for item in result["files"]:
        flag = "!!" if item["uncovered"] else "  "
        detail = item.get("note") or ", ".join(str(n) for n in item["missing_lines"][:25])
        lines.append(f"{flag} {item['file']:<42}{item['added']:>6}{item['uncovered']:>7}  {detail}")
    if unmeasured:
        lines.append("")
        lines.append("**未被 coverage 测量**（判决不可信 ⇒ 必须用同口径的 coverage.xml 重跑）：")
        lines.extend(
            f"   {item['file']:<40}{item.get('unmeasured_lines', 0)} 行新增从未被测过"
            for item in result["files"]
            if item.get("unmeasured")
        )
    verified_total = result.get("total_verified_elsewhere") or 0
    if verified_total:
        lines.append("")
        lines.append(f"已在本进程之外验证（登记在册，不计缺口）：{verified_total} 行")
        lines.extend(
            f"   {item['file']:<40}{', '.join(str(n) for n in item['verified_lines'][:25])}"
            for item in result["files"]
            if item.get("verified_lines")
        )
    stale = result.get("registry_stale") or []
    if stale:
        lines.append("")
        lines.append("登记表失效（锚点内容已消失 ⇒ 必须重新判定）：")
        lines.extend(f"   {item}" for item in stale)
    errors = result.get("registry_errors") or []
    if errors:
        lines.append("")
        lines.append("登记表畸形：")
        lines.extend(f"   {item}" for item in errors)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--base",
        default=DEFAULT_BASE,
        help="修复起点提交；默认 auto = 最近一次改动审计范围的提交（也可显式给提交号）",
    )
    parser.add_argument(
        "--pathspec",
        default="src/",
        help="审计范围前缀，须与 --coverage-xml 的 --cov 目标一致（src/ 或 experiments/）",
    )
    parser.add_argument("--coverage-xml", default=str(DEFAULT_COVERAGE_XML), help="coverage.xml 路径（须与 HEAD 对齐）")
    parser.add_argument("--json", default="-", help="JSON 输出路径（默认 - = 不输出）")
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="「已在本进程之外验证」登记表路径（默认 docs/fix_coverage_verified_elsewhere.txt）",
    )
    args = parser.parse_args()

    xml_path = Path(args.coverage_xml)
    if not xml_path.is_file():
        print(f"错误：找不到 {xml_path}——先跑 `make test-cov` 产出与 HEAD 对齐的覆盖率", file=sys.stderr)
        return 2

    result = audit(
        args.base,
        xml_path,
        PROJECT_ROOT,
        args.pathspec,
        registry_path=Path(args.registry),
    )
    print(render(result))

    if args.json != "-":
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"\nJSON 已写入 {args.json}")
    # 登记完整性是判决的输入：登记表畸形或失效 ⇒ 判决不可信 ⇒ rc=1。
    if result["registry_errors"] or result["registry_stale"]:
        return 1
    # FE 轮：**未测量 ≠ 零缺口**。作用域内存在未被 coverage 测量的文件 ⇒
    # 判决的输入不完整（分母只覆盖了被测量的那部分）⇒ 判决不可信 ⇒ rc=1。
    # 改前此处报「0 行缺口（0.00%）」并 rc=0 通过——「没测」被读成了「测得 0」。
    if result.get("total_unmeasured_files"):
        print(
            f"错误：作用域内有 {result['total_unmeasured_files']} 个文件未被 coverage 测量"
            f"（共 {result.get('total_unmeasured_added_lines', 0)} 行新增从未被测过）——"
            f"「未测量」不等于「零缺口」；请用与 --pathspec 同口径的 --cov 目标重跑覆盖率",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
