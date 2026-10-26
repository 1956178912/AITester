#!/usr/bin/env python3
"""DB/DE（2026-10-26）：BibTeX 引用库**可编译性**守卫——注释里的 at 符号会静默破坏条目。

起因（DB 轮实测）：DB 轮给 `paper/tex/refs.bib` 增加两条条目时，在**百分号注释行**
里写了 `pass@1`（pass@1 是量子代码基准的指标名）。BibTeX 0.99e 的行为是：

    在百分号注释里遇到 at 符号会**重新开始扫描条目**，
    于是 `pass@1` 被读成「条目类型 `1`」，报
        You're missing an entry type---line 659 of file refs.bib

为什么这个缺陷值得单独设门（三条理由，都是本轮踩出来的）：

  1. **它不阻断 PDF 生成**。`pdflatex` 三遍的退出码全是 0，PDF 照样产出
     （70 页、0 未定义引用）——**只有 bibtex 的退出码是 2**，而 bibtex 只是
     三遍链的中间一步，不看它的退出码就发现不了。
  2. **失败是"部分成功"而非"全有全无"**：bibtex 跳过了那一条**之后**的条目，
     但**之前**的条目照常进了 .bbl ⇒ PDF 少了参考文献却看不出少了哪一条。
     本轮实测：refs.bib 从 72 条涨到 79 条，PDF 里少进了 1 条。
  3. **修复它的人会再犯**：我第一次修复时把解释写进注释，注释里又带了
     `pass@1` 和 at 符号 ⇒ **同一个错误立刻重现**。人眼在这里完全不可靠。

判定面（本门禁**实际调用 BibTeX**，不做正则猜测）：

  1. 若环境有 bibtex ⇒ 在临时目录里用**真实 refs.bib + 真实 spbasic.bst**
     跑一次 `\\citation{*}` 的 bibtex。退出码非 0、输出含 "error message"、
     `.bbl` 缺席，或**任一条目没有对应的 `\\bibitem`** ⇒ 判红。
     用 `\\citation{*}` 而不是一个虚构键，是为了证明**每个真实条目都经过了
     样式处理并进入 .bbl**；`.aux` 只写一个虚构 `\\citation{probe}` 时，
     bibtex 会报「找不到数据库条目」而根本不处理真实键，探针就成了假绿。
  2. 无论 bibtex 是否可用 ⇒ 对 refs.bib 的**注释区**做静态扫描：
     注释区里出现 at 符号即命中。注释区按 BibTeX 的括号深度判定——
     字段值 `{...}` 内的 `%` 是字面量（DE 轮实测 bibtex 接受
     `note={100% pass@1}`），不算注释；条目体内、字段之间的 `%` 才是注释
     （实测 bibtex 报 "missing a field name"）。行内/尾随注释同样覆盖。
  3. refs.bib 存在但 spbasic.bst 缺席 ⇒ 判红（**不得**静默退化到 plain：
     那会把「真实样式可编译」偷换成「任何样式可编译」）。
  4. refs.bib 不存在 ⇒ 默认档按 [SKIP] 披露（CI 双盲纪律）；
     `--require-paper` 判红（无法验证 ≠ 通过）。

口径诚实化（DE 轮修正）：
  - bibtex 不可用 ⇒ 静态扫描仍然执行；干净时打印 `[SKIP]` 披露
    「未做真实编译验证」并 **exit 0**。
  - `paper/` 按 `.gitignore` 双盲纪律**不入库** ⇒ CI clone 里 `refs.bib` 不存在。
    本门禁在 CI 里的角色是**契约测试面**（`tests/test_bibtex_compilability_gate.py`
    用合成 bib + fresh-clone 行为锁覆盖），不是「CI 编译真实稿件」。
    Makefile / ci.yml 的表述据此写成「本地有稿且有 bibtex 时阻断；无 bibtex 或
    CI 缺稿均披露 [SKIP]」，不再称「CI 阻断项」。
  - timeout / OSError / 解码异常都转成结构化 `ProbeResult(status="error")`，
    不抛栈、不静默。

用法：
    python scripts/gates/check_bibtex_compilability.py                  # 默认档
    python scripts/gates/check_bibtex_compilability.py --require-paper  # 稿件缺席即红
    python scripts/gates/check_bibtex_compilability.py --list           # 打印命中明细

真实编译探针需要 bibtex 在 PATH；TinyTeX 用户可临时：
    PATH="$HOME/Library/TinyTeX/bin/universal-darwin:$PATH" make bibtex-compilability
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

#: 稿件侧引用库与样式（双盲纪律下不入库，仅本地/有稿件环境在场）。
BIB = PROJECT_ROOT / "paper" / "tex" / "refs.bib"
BST = PROJECT_ROOT / "paper" / "tex" / "spbasic.bst"

#: 只有真实数据库条目才需要进 .bbl；@comment / @string / @preamble 不是条目。
_ENTRY_KEY_RE = re.compile(r"^@(?P<type>[A-Za-z]+)\s*\{\s*(?P<key>[^,\s]+)\s*,", re.MULTILINE)
_NON_ENTRY_TYPES = {"comment", "string", "preamble"}
_BIBITEM_RE_TEMPLATE = r"\\bibitem(?:\[[^\]]*\])?\{{{key}\}}"
_BIBITEM_COUNT_RE = re.compile(r"\\bibitem(?:\[[^\]]*\])?\{")


@dataclass(frozen=True)
class ProbeResult:
    """真实编译探针的结构化结果。

    status:
      - ``ok``   编译通过，且每个条目都进了 .bbl
      - ``fail`` bibtex 报错 / .bbl 缺条目
      - ``skip`` 环境无 bibtex（静态扫描仍执行）
      - ``error`` 样式缺席、无条目、超时、启动失败等**无法验证**
    """

    status: str
    output: str = ""
    reason: str = ""
    entries: int = 0
    bibitems: int = 0

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def skipped(self) -> bool:
        return self.status == "skip"


def _bibtex_binary() -> str | None:
    """找 bibtex；找不到返回 None（**不静默通过**，由调用方按 [SKIP] 披露）。"""
    return shutil.which("bibtex")


def _escaped(line: str, idx: int) -> bool:
    """`%` 前是否有**奇数**个连续反斜杠（奇数 = 转义，偶数 = 未转义）。

    TeX 的 `\\\\%` 是「换行 + 注释」，`\\%` 是字面百分号；只判断紧邻一个
    反斜杠会把两者混为一谈。
    """
    backslashes = 0
    j = idx - 1
    while j >= 0 and line[j] == "\\":
        backslashes += 1
        j -= 1
    return backslashes % 2 == 1


def _mask_comments(text: str) -> tuple[list[str], list[tuple[int, str]]]:
    """按 BibTeX 的括号深度剥注释，返回 (屏蔽后的行, 命中列表)。

    BibTeX 的 `%` 不是"任何位置都算注释"：
      - 条目外 / 条目体内、字段之间（深度 ≤ 1）的 `%` 是注释；
      - 字段值 `{...}` 内（深度 ≥ 2）或引号值内的 `%` 是字面量。
    DE 轮实测：`note={100% pass@1}` 编译 rc=0；`% pass@1` 在条目体内
    报 "missing a field name"。静态扫描必须按这个边界判，否则会把
    合法的百分号字段误报，或漏掉尾随注释。
    """
    masked: list[str] = []
    hits: list[tuple[int, str]] = []
    depth = 0
    in_quote = False
    for lineno, raw in enumerate(text.splitlines(), start=1):
        chars = list(raw)
        comment_start: int | None = None
        i = 0
        while i < len(raw):
            ch = raw[i]
            if in_quote:
                if ch == '"':
                    in_quote = False
                i += 1
                continue
            if ch == '"' and depth >= 1:
                in_quote = True
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth = max(0, depth - 1)
            elif ch == "%" and depth <= 1 and not _escaped(raw, i):
                comment_start = i
                break
            i += 1
        if comment_start is not None:
            for j in range(comment_start, len(chars)):
                chars[j] = " "
            if "@" in raw[comment_start:]:
                hits.append((lineno, raw.strip()))
        masked.append("".join(chars))
    return masked, hits


def _strip_bib_comments(text: str) -> str:
    """去掉注释区（保留行结构），用于提取真实条目键。"""
    masked, _ = _mask_comments(text)
    return "\n".join(masked)


def _static_scan(text: str) -> list[tuple[int, str]]:
    """静态扫描：返回 (行号, 该注释行) 列表。"""
    _, hits = _mask_comments(text)
    return hits


def _entry_keys(text: str) -> list[str]:
    """按注释剥离后的文本提取真实条目键（跳过 @comment / @string / @preamble）。"""
    stripped = _strip_bib_comments(text)
    keys: list[str] = []
    for match in _ENTRY_KEY_RE.finditer(stripped):
        if match.group("type").lower() in _NON_ENTRY_TYPES:
            continue
        keys.append(match.group("key"))
    return keys


def _compile_probe(
    bib_text: str,
    *,
    bibtex: str | None = None,
    bst: Path | None = None,
) -> ProbeResult:
    """在临时目录里真跑一次 bibtex，并证明每个条目都进了 .bbl。

    `bibtex` / `bst` 显式传入便于测试替换；缺省取 PATH 与仓库内真实样式。
    """
    bst_path = BST if bst is None else Path(bst)
    if not bst_path.exists():
        return ProbeResult("error", reason=f"样式文件缺席：{bst_path}")

    binary = bibtex if bibtex is not None else _bibtex_binary()
    keys = _entry_keys(bib_text)
    if not keys:
        return ProbeResult("error", reason="refs.bib 没有可探测的真实条目")
    if binary is None:
        return ProbeResult("skip", reason="bibtex 不在 PATH")

    with tempfile.TemporaryDirectory(prefix="bibtex_probe_") as tmp:
        work = Path(tmp)
        (work / "probe.bib").write_text(bib_text, encoding="utf-8")
        shutil.copy2(bst_path, work / bst_path.name)
        (work / "probe.aux").write_text(
            f"\\relax\n\\citation{{*}}\n\\bibstyle{{{bst_path.stem}}}\n\\bibdata{{probe}}\n",
            encoding="utf-8",
        )
        try:
            proc = subprocess.run(
                [binary, "probe"],
                cwd=work,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ProbeResult("error", reason="bibtex 超时（120s）")
        except OSError as exc:
            return ProbeResult("error", reason=f"bibtex 启动失败：{exc}")

        output = (proc.stdout or "") + (proc.stderr or "")
        lowered = output.lower()
        if proc.returncode != 0:
            return ProbeResult("fail", output=output, reason=f"bibtex 退出码 {proc.returncode}", entries=len(keys))
        if "error message" in lowered or "missing an entry type" in lowered:
            return ProbeResult("fail", output=output, reason="bibtex 输出含错误", entries=len(keys))

        bbl = work / "probe.bbl"
        if not bbl.exists():
            return ProbeResult("fail", output=output, reason="bibtex 未生成 .bbl", entries=len(keys))
        bbl_text = bbl.read_text(encoding="utf-8", errors="replace")
        bibitems = len(_BIBITEM_COUNT_RE.findall(bbl_text))
        missing = [key for key in keys if not re.search(_BIBITEM_RE_TEMPLATE.format(key=re.escape(key)), bbl_text)]
        if missing:
            return ProbeResult(
                "fail",
                output=output,
                reason=f".bbl 缺少条目：{', '.join(missing[:5])}（共 {len(missing)} 条）",
                entries=len(keys),
                bibitems=bibitems,
            )
        return ProbeResult("ok", output=output, entries=len(keys), bibitems=bibitems)


def main(argv: list[str] | None = None) -> int:
    """门禁主体。

    `argv` 显式传入（默认取 `sys.argv[1:]`）——测试直接调用本函数时传自己的参数，
    避免 `sys.argv` 在 pytest 进程里被 pytest 的参数污染。
    """
    parser = argparse.ArgumentParser(description="BibTeX 引用库可编译性守卫")
    parser.add_argument(
        "--require-paper",
        action="store_true",
        help="refs.bib 缺席即判红（本地/有稿件环境用；CI 默认档按 [SKIP] 披露）",
    )
    parser.add_argument("--list", action="store_true", help="打印命中明细")
    args = parser.parse_args(argv)

    if not BIB.exists():
        msg = f"稿件侧引用库缺席：{BIB}"
        if args.require_paper:
            print(f"[bibtex-gate] ❌ {msg}")
            return 1
        print(f"[bibtex-gate] [SKIP] {msg}——paper/ 按双盲纪律不入库，本档不做判定")
        return 0

    try:
        text = BIB.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"[bibtex-gate] ❌ 无法读取 {BIB}：{exc}")
        return 1

    static_hits = _static_scan(text)
    probe = _compile_probe(text)

    entries = len(_entry_keys(text))
    lines = len(text.splitlines())
    if probe.status == "ok":
        print(f"[bibtex-gate] 真实编译：OK（{probe.entries} 条目全部进入 .bbl，{probe.bibitems} 个 \\bibitem）")
    elif probe.status == "skip":
        print(f"[bibtex-gate] [SKIP] 真实编译：{probe.reason}——本环境无 TeX 发行版，仅执行静态扫描")
    else:
        print(f"[bibtex-gate] ❌ 真实编译失败：{probe.reason}")
        for line in probe.output.splitlines():
            if line.strip():
                print(f"    {line}")

    print(f"[bibtex-gate] 静态扫描：{lines} 行 / {entries} 条目，注释区 at 符号命中 {len(static_hits)} 处")
    if static_hits:
        print("[bibtex-gate] ❌ 注释区出现 at 符号（BibTeX 会重启条目扫描 ⇒ 静默丢条目）：")
        for idx, line in static_hits:
            print(f"    refs.bib:{idx}: {line[:150]}")
        return 1

    if probe.status in {"fail", "error"}:
        print("[bibtex-gate] ❌ 真实编译无法通过（静态扫描干净也不放行）")
        return 1

    print("[bibtex-gate] ✅ refs.bib 注释与解析均无已知陷阱")
    if args.list:
        # 呈现档：只多打印明细，**不改变退出码**（判定方向由上面的分支决定）。
        print(f"[bibtex-gate] 扫描面：refs.bib 共 {lines} 行，真实条目 {entries} 条，注释区 at 符号命中 0 处")
        print("[bibtex-gate] 命中明细结束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
