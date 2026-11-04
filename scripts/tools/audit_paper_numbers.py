#!/usr/bin/env python3
"""Q11（2026-10-17 独立评审 §3/§10）：EMSE 论文草稿的"数字 ↔ SRC 证据"一致性审计。

## 为什么需要它

独立评审 Q11：论文稿 **不在 git（.gitignore 排除 `paper/`）**，正文中的百分比 /
DOI / 成本 / 样本量数字仅抽查了 3 处 `// SRC:` 注释；评审要求"投稿前必须完成全文
数字对账（建议用 `check_artifact_doc_consistency.py` 同口径扩展至 paper/），重点
核验论文中所有百分比/DOI/成本数字的 SRC 注释完整性"。本工具即该审计的本地实现。

## 检查项

1. **数字声明覆盖率**：识别稿件（默认 `paper/tex/manuscript.tex`）中的数字声明（百分比 / 货币 / p 值 / `n=`
   / `x/y` 比例 / DOI），判断其是否处在某条 `// SRC:` 注释的覆盖窗口（默认 ±12 行）
   内；输出未覆盖清单与逐节覆盖率。
2. **SRC 引用有效性**：解析每条 `// SRC:` 中的引用 token：
   - 仓库内路径（含 `/` 或以已知扩展名结尾）必须存在（文件或目录）；
   - `docs/adr/ADR-00XX` / 裸 `ADR-00XX` 必须能在 `docs/adr/` 找到对应编号文件；
   - `BASELINE.yaml#a.b.c` 形式的键必须能在 YAML 中解析；
   - 其余视为说明性文字（忽略）。
3. **引文卫生**：draft 引用的 `@key` 必须存在于 `refs.bib`；每条 bib 条目必须有
   note 含 DOI 或 arXiv（录入纪律：未核验字段留 TODO）；DOI 去重与格式校验；
   未被引用的 bib 条目作为 warning 列出。
4. **TODO 清单**：列出 draft/bib 中所有 `TODO` 标记（投稿前清零项）。

## 口径与边界

- **本地工具，非 CI**：`paper/` 不入库，本工具在 paper 缺失时直接 exit 0（CI 安全）；
  `make paper-audit` 供投稿前本地执行。
- 数字识别的启发式**不是**语义解析：可能漏报（如文字化数字 "three seeds"）与误报
  （如公式里的常数）；报告须人工复核，工具只给出"待对账清单 + 客观引用有效性"。
- 覆盖率是**块级近似**（SRC 窗口），不代表每条数字逐条被引用——投稿纪律仍要求
  关键数字逐条可追溯到工件。

用法：
    python scripts/tools/audit_paper_numbers.py
    python scripts/tools/audit_paper_numbers.py --json out.json --md out.md
    python scripts/tools/audit_paper_numbers.py --strict          # 引用无效/覆盖率不达标 → exit 1
    python scripts/tools/audit_paper_numbers.py --window 15 --min-coverage 0.8
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PAPER_DIR = PROJECT_ROOT / "paper"
DEFAULT_DRAFT = "draft.typ"  # 历史 Typst 稿；CN 轮清理后仅合成测试再用它
LATEX_DRAFT = "tex/manuscript.tex"

# SRC 注释前缀：Typst 用 `//`，LaTeX 用 `%`。两套都要认，否则换了权威源之后
# 审计器会把整篇当成「没有 SRC」——那是最危险的一种绿。
SRC_MARKERS = ("// SRC:", "% SRC:", "%SRC:")
DEFAULT_BIB = "refs.bib"
DEFAULT_WINDOW = 12
DEFAULT_MIN_COVERAGE = 0.8

# 数字声明识别（启发式；报告附匹配片段供人工复核）
_NUMERIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("percentage", re.compile(r"\d+(?:\.\d+)?\s*%")),
    # 货币：`$` 前不得紧邻字母/数字（排除 Typst 数学 `2$times$2` 的误报）
    ("currency", re.compile(r"(?<![A-Za-z0-9])\$\s?\d[\d,]*(?:\.\d+)?")),
    ("p_value", re.compile(r"\bp\s*(?:[=~<>]|approx)\s*\d")),
    ("sample_size", re.compile(r"\bn\s*=\s*\d+")),
    ("ratio", re.compile(r"\b\d+/\d+\b")),
    ("doi", re.compile(r"\b10\.\d{4,}/[^\s,;)\]]+")),
    ("count", re.compile(r"\b\d+\s+(?:tasks|programs|tests|pairs|batches|seeds|functions|calibers|artifacts)\b", re.I)),
)

# DOI 在 bib note 中的识别
_BIB_DOI_RE = re.compile(r"10\.\d{4,}/[^\s;,'\"}]+")
_BIB_ARXIV_RE = re.compile(r"arXiv:\s*\d{4}\.\d{4,5}")
# CR 轮（2026-10-25）：PMLR（Proceedings of Machine Learning Research）**不分配
# DOI**——其官方 BibTeX 模板只有 volume/series/publisher/month/url，引用形态是
# `PMLR 306:77728-77771, 2026`（一手核验：proceedings.mlr.press/v306/liu26ct.html，
# 2026-10-25）。旧判据「至少 DOI 或 arXiv 或 TODO」对这类出版物是**伪要求**：
# 它逼着作者写一个不存在的 TODO，或写一条并不存在的 DOI。判据改为承认
# 「出版方=PMLR」是一种正当标识——要求条目显式声明 publisher={PMLR}，
# 且该标识只在 publisher 命中时生效（不会放宽到其它出版物）。
_BIB_PMLR_RE = re.compile(r"publisher\s*=\s*\{PMLR\}", re.IGNORECASE)
_BIB_ENTRY_RE = re.compile(r"^@([a-zA-Z]+)\{([^,]+),")
_CITE_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]+)")
# 邮箱形态不是引用键（2026-10-29）：通讯邮箱落稿后，`a1956178912@outlook.com`
# 会被 _CITE_RE/_CITATION_RE 截出假键 `outlook`，前置判据误报「正文引用 @outlook
# 不在 refs.bib 中」。提引用键前先剥离邮箱文本——这是**输入归一化**（邮箱本来
# 就不是可引键），不放宽对真键的判定。
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _strip_emails(text: str) -> str:
    """把邮箱形态文本挖成空格，防止其 `@域名` 被引用键正则误读为 `@key`。"""
    return _EMAIL_RE.sub(" ", text)


# ── 可排版性判据（CR 轮，2026-10-25）────────────────────────────────────────
# 为什么需要它：本轮编译论文时 tectonic 报出一串
#   warning: could not represent character "档" (0x6863) in font "ec-lmr10"
#   manuscript.bbl:14: Missing character: There is no ��� ("540E) in font ec-lmr10!
# 而**编译退出码是 0**——「编译成功」与「排版正确」是两件事。根因是 refs.bib
# 的两个条目把中文写进了 `note` 字段：note 会进 .bbl，.bbl 被 \bibitem 原样
# 排版，而 Latin Modern（ec-lmr10）没有中文字形 ⇒ PDF 的参考文献处留下缺字符
# （读者看到的是空白/乱码）。这类缺陷此前 180 轮无人看见，因为大家只看
# 「0 未定义引用」，没看编译警告，而警告不影响退出码。
# 判据：**会被排版的文本里不得有 CJK**。LaTeX 与 BibTeX 都把 `%` 之后当注释
# （不排版），故按 `%` 截断后扫描；`\%` 是转义、不算注释起点。
# 编译警告不是判据（退出码骗人），把「不可排版的字符」变成可执行判据。
_CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uff00-\uffef]")


def _escaped(line: str, idx: int) -> bool:
    """`idx` 前的字符是否被**奇数**个连续反斜杠转义（奇数 = 转义，偶数 = 未转义）。"""
    backslashes = 0
    j = idx - 1
    while j >= 0 and line[j] == "\\":
        backslashes += 1
        j -= 1
    return backslashes % 2 == 1


def _escaped_percent(line: str, idx: int) -> bool:
    """`%` 前是否有**奇数**个连续反斜杠（奇数 = 转义，偶数 = 未转义）。"""
    return _escaped(line, idx)


def _strip_comment(line: str) -> str:
    """TeX 行注释：去掉第一个未转义的 `%` 及其后内容。

    `\\%` 是字面百分号；`\\\\%` 的 `%` 才是注释起点——只判断紧邻一个反斜杠
    会把两者混为一谈（DE 轮修正）。
    """
    for idx, ch in enumerate(line):
        if ch == "%" and not _escaped_percent(line, idx):
            return line[:idx]
    return line


def _strip_bib_comments(text: str) -> str:
    """BibTeX 注释：只有字段值括号外的 `%` 才是注释。

    实测 `note={100% pass@1}` 编译 rc=0（字面量），而条目体内的 `% pass@1`
    报 missing field name。按括号深度剥注释，避免把合法百分号字段里的
    TODO/CJK 误判掉。
    """
    out: list[str] = []
    depth = 0
    in_quote = False
    for line in text.splitlines():
        chars = list(line)
        i = 0
        while i < len(line):
            ch = line[i]
            if in_quote:
                if ch == '"' and not _escaped(line, i):
                    in_quote = False
                i += 1
                continue
            if ch == '"' and depth >= 1 and not _escaped(line, i):
                in_quote = True
                i += 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth = max(0, depth - 1)
            elif ch == "%" and depth <= 1 and not _escaped_percent(line, i):
                for j in range(i, len(chars)):
                    chars[j] = " "
                break
            i += 1
        out.append("".join(chars))
    return "\n".join(out)


def _strip_typst_comments(text: str) -> str:
    """Typst 注释：`//` 行注释 + 可嵌套的 `/* ... */` 块注释。

    字符串与反引号 raw 文本里的 `//` 不是注释；`https://` 里的 `//` 也按
    字面量保留（行注释的判定排除冒号前缀）。块注释跨行时保留换行，
    使行号与原始稿一致。
    """
    out: list[str] = []
    i = 0
    n = len(text)
    in_string = False
    raw_ticks = 0
    block_depth = 0
    while i < n:
        ch = text[i]
        if block_depth:
            if text.startswith("/*", i):
                block_depth += 1
                out.extend("  ")
                i += 2
                continue
            if text.startswith("*/", i):
                block_depth -= 1
                out.extend("  ")
                i += 2
                continue
            out.append(ch if ch == "\n" else " ")
            i += 1
            continue
        if raw_ticks:
            if ch == "`":
                j = i
                while j < n and text[j] == "`":
                    j += 1
                run = j - i
                out.extend("`" * run)
                if run >= raw_ticks:
                    raw_ticks = 0
                i = j
                continue
            out.append(ch)
            i += 1
            continue
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "`":
            j = i
            while j < n and text[j] == "`":
                j += 1
            raw_ticks = j - i
            out.extend("`" * raw_ticks)
            i = j
            continue
        if text.startswith("//", i) and not (i > 0 and text[i - 1] == ":"):
            j = text.find("\n", i)
            if j == -1:
                out.extend(" " * (n - i))
                i = n
            else:
                out.extend(" " * (j - i))
                i = j
            continue
        if text.startswith("/*", i):
            block_depth = 1
            out.extend("  ")
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_comments(text: str, suffix: str = ".tex") -> str:
    """按文件类型剥注释：Typst / BibTeX / TeX（默认）。"""
    lowered = suffix.lower()
    if lowered == ".typ":
        return _strip_typst_comments(text)
    if lowered == ".bib":
        return _strip_bib_comments(text)
    return "\n".join(_strip_comment(line) for line in text.splitlines())


def _stripped_lines(path: Path) -> list[str]:
    """读文件并**剥掉注释**（只留会被排版的部分）。文件不在场时返回空列表。"""
    if not path.exists():
        return []
    return _strip_comments(path.read_text(encoding="utf-8"), path.suffix).splitlines()


def _cjk_hits_text(text: str, suffix: str = ".tex") -> list[tuple[int, str]]:
    """(行号, 该行会排版部分里的 CJK 字符集合)——按文件类型剥注释。"""
    hits: list[tuple[int, str]] = []
    for idx, raw in enumerate(_strip_comments(text, suffix).splitlines(), start=1):
        found = "".join(sorted(set(_CJK_RE.findall(raw))))
        if found:
            hits.append((idx, found))
    return hits


def _cjk_hits(lines: list[str]) -> list[tuple[int, str]]:
    """行列表版 CJK 扫描（TeX 口径；audit_bib 与旧测试仍用它）。"""
    hits: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines, start=1):
        found = "".join(sorted(set(_CJK_RE.findall(_strip_comment(raw)))))
        if found:
            hits.append((idx, found))
    return hits


# LaTeX 侧引用：\citet{k} / \citep{k1,k2}（natbib）。缺了它，正文引文覆盖恒为 0，
# 外部文献数字会被误判成「无来源」——CN 轮换成 .tex 权威源时实测到的第一个坑。
_CITE_RE_LATEX = re.compile(r"\\cite[pt]?\{([^}]+)\}")
_ADR_RE = re.compile(r"ADR-(\d{4})", re.I)
_PATH_TOKEN_RE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.*%{}-]+)+|(?:[A-Za-z0-9_.-]+\.(?:md|json|yaml|yml|py|typ|cff|txt))"
)
_KNOWN_EXT = (".md", ".json", ".yaml", ".yml", ".py", ".typ", ".cff", ".txt")

# ── 数字存在性判据（CM 轮，2026-10-25）──────────────────────────────────────
# 为什么需要它：本工具此前只判「SRC 路径存在」。附录 E 的成本表把一个
# **已撤回批次**的四位小数读数挂在 `emse_stats_extensions_20261025/` 上，
# 而该工件根本不含这些数（它的臂是 n=20/36/41 的单批口径）——路径存在、
# 数字不在，综合可追溯率仍报 100%。存在性不等于内容，这是本项目反复
# 收口的「沉默分叉」在论文审计面的同形。
#
# 判据只对**高精度数字**生效（≥2 位小数或千分位整数）：这类数字是工件的
# 指纹，短整数（任务数、种子数、年份）不具备判别力，强行判会制造假红。
# 找不到可判定工件 ⇒ 记 unchecked（披露，不判红）；找到工件而数字不在
# ⇒ 记 failed（strict 下阻断）。
_PRECISE_NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d{2,})(?![\w.])")
# 历史数字的合法落点：撤回索引（冻结读数的权威文档，见 WITHDRAWN_ARTIFACTS 表 W-1）
_ARCHIVE_DOC_GLOBS = (
    "docs/study/WITHDRAWN_ARTIFACTS_*.md",
    # CN 轮：外部读数登记册与冻结统计报告也是「可判定工件」——它们存的是
    # 逐条抄录的读数与复算命令，审计器只能验证登记一致性（不是复算）。
    "docs/study/EXTERNAL_READINGS_*.md",
    "docs/study/RQ1_PAIRING_REPORT_*.md",
)
_JSON_SUFFIX = ".json"


def _precise_numbers(text: str) -> list[tuple[str, float, int]]:
    """抽取高精度数字：`(原文, 数值, 小数位数)`；千分位整数小数位记 0。"""
    found: list[tuple[str, float, int]] = []
    for match in _PRECISE_NUMBER_RE.finditer(text):
        raw = match.group(1)
        try:
            value = float(raw.replace(",", ""))
        except ValueError:  # pragma: no cover - 正则已限定形状
            continue
        decimals = len(raw.split(".", 1)[1]) if "." in raw else 0
        found.append((raw, value, decimals))
    return found


def _artifact_numbers(path: Path) -> list[float]:
    """读出工件里的全部数值（JSON 递归取数；Markdown/文本按字面数字抽取）。"""
    try:
        if path.suffix.lower() == _JSON_SUFFIX:
            data = json.loads(path.read_text(encoding="utf-8"))
            numbers: list[float] = []

            def _walk(node: Any) -> None:
                if isinstance(node, bool):
                    return
                if isinstance(node, (int, float)):
                    numbers.append(float(node))
                elif isinstance(node, dict):
                    for value in node.values():
                        _walk(value)
                elif isinstance(node, list):
                    for value in node:
                        _walk(value)

            _walk(data)
            return numbers
        text = path.read_text(encoding="utf-8", errors="ignore")
    except (OSError, ValueError, UnicodeError):
        return []
    return [value for _, value, _ in _precise_numbers(text)] + [
        float(raw) for raw in re.findall(r"(?<![\w.])\d+\.\d+(?![\w.])", text)
    ]


def src_comment(line: str) -> str | None:
    """返回一行里 `SRC:` 之后的内容；不是 SRC 行则 None。"""
    for marker in SRC_MARKERS:
        if marker in line:
            return line.split(marker, 1)[1]
    return None


def has_src(line: str) -> bool:
    """该行是否是一条 SRC 注释（兼容 `// SRC:` 与 `% SRC:`）。"""
    return src_comment(line) is not None


def select_draft(paper_dir: Path, draft: str | None = None) -> Path:
    """选权威稿：显式指定 > LaTeX 原生稿 > Typst 草稿。

    CN 轮起 `paper/tex/manuscript.tex` 是唯一权威源（不再由脚本生成）。若仍
    默认读 `draft.typ`，审计会持续对着旧稿给绿灯——**审错文件比不审更糟**。
    """
    if draft:
        return paper_dir / draft
    latex = paper_dir / LATEX_DRAFT
    if latex.is_file():
        return latex
    return paper_dir / DEFAULT_DRAFT


def _unescape_latex_path(token: str) -> str:
    r"""把 LaTeX 文本模式下的转义还原成真实路径字符（`\_` → `_` 等）。

    论文里的 SRC 注释常写成 `docs/study/WITHDRAWN\_ARTIFACTS\_...md`；不还原就
    会被判成「路径不存在」，33 条假红里有 30 条是这一个原因（CN 轮实测）。
    """
    for escaped, raw in (("\\_", "_"), ("\\%", "%"), ("\\&", "&"), ("\\#", "#")):
        token = token.replace(escaped, raw)
    return token


def _looks_like_reference(token: str) -> bool:
    """token 是否像一条路径引用（而不是 SRC 行里的数字注解）。

    SRC 注释里常带 `(26/50 vs 26/36)`、`+16.1/+19.5` 这类读数；它们不是引用，
    当成路径去校验只会制造假红。判据：有已知扩展名，或以仓库顶层真实目录开头。
    """
    if not token:
        return False
    # ADR 编号与 BASELINE 键有各自的校验分支，不能被「像不像路径」提前筛掉
    if token.startswith("ADR-") or token.startswith("BASELINE.yaml#"):
        return True
    if token.endswith(_KNOWN_EXT):
        return True
    head = token.split("/", 1)[0]
    return "/" in token and (PROJECT_ROOT / head).is_dir()


def _resolve_src_artifacts(line_text: str, root: Path) -> list[Path]:
    """把一条 SRC 注释里的 token 解析为可判定工件（JSON 文件 / 撤回索引）。"""
    artifacts: list[Path] = []
    for token in re.split(r"[;,\s]+", src_comment(line_text) or ""):
        token = _unescape_latex_path(token.strip().strip(";,.()[]{}\"'`"))
        if not token or token.startswith(("http://", "https://")):
            continue
        # 撤回索引（历史数字的权威落点）
        if any(Path(token).match(pattern) for pattern in _ARCHIVE_DOC_GLOBS):
            artifacts.extend(sorted(root.glob(token)))
            continue
        candidate = root / token
        if candidate.is_dir():
            artifacts.extend(sorted(candidate.glob("*.json")))
        elif candidate.suffix == _JSON_SUFFIX and candidate.exists():
            artifacts.append(candidate)
    # 去重且保持稳定顺序
    return list(dict.fromkeys(artifacts))


def _matches_artifact(claim_value: float, decimals: int, numbers: list[float], percent: bool) -> bool:
    """按声明精度做半单位容差匹配；百分比声明同时试 x/100 与 x*100 两种读法。"""
    tolerance = 0.5 * (10**-decimals) + 1e-12
    candidates = [claim_value]
    if percent:
        candidates.extend([claim_value / 100.0, claim_value * 100.0])
    for candidate in candidates:
        scale_tolerance = tolerance if candidate == claim_value else tolerance / 100.0
        if any(abs(value - candidate) <= scale_tolerance for value in numbers):
            return True
    return False


def verify_numbers_in_artifacts(
    claims: list[dict[str, Any]],
    src_lines: list[int],
    lines: list[str],
    window: int,
    root: Path,
) -> dict[str, Any]:
    """判「一段文字里的高精度数字是否能在其所指工件里找到至少一条」。

    为什么按**块**而不是按**条**：p 值、置信区间、z 常数、效应量都是**派生量**，
    本来就不会以字面形式存盘（`p = 0.0352` 由 McNemar 从行级数据算出）。逐条
    要求字面命中会把派生统计量全部误判成缺陷。真正的缺陷形状是**指向错工件**：
    整段（一张表 / 一段结果）没有一条数字能在所指工件里找到——附录 E 的成本表
    正是这种形状（261 行池的四位小数读数挂在单批工件上）。

    返回三档：verified（块内至少一条数字命中）/ failed（一条都不命中）/ unchecked
    （没有可判定工件）。unchecked 是披露，不是通过。
    """
    cache: dict[Path, list[float]] = {}

    # 按空行切块（与 _paragraph_citations 同口径，便于解释）
    block_of_line: list[int] = []
    block_idx = 0
    for raw in lines:
        block_of_line.append(block_idx)
        if not raw.strip():
            block_idx += 1
    block_count = block_idx + 1

    precise_by_block: dict[int, list[dict[str, Any]]] = {}
    for claim in claims:
        line0 = claim["line"] - 1
        if line0 >= len(block_of_line):
            continue
        numbers = _precise_numbers(claim["snippet"])
        if not numbers:
            continue
        precise_by_block.setdefault(block_of_line[line0], []).append({**claim, "precise": numbers})

    verified: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    unchecked: list[dict[str, Any]] = []
    strict_failed: list[dict[str, Any]] = []
    strict_markers = [
        i for i, line in enumerate(lines) if "// SRC-CHECK: strict" in line or "% SRC-CHECK: strict" in line
    ]

    for block in range(block_count):
        entries = precise_by_block.get(block)
        if not entries:
            continue
        block_lines = [i for i, b in enumerate(block_of_line) if b == block]
        block_start, block_end = min(block_lines), max(block_lines)
        is_strict = any(block_start <= marker <= block_end + 2 for marker in strict_markers)
        if is_strict:
            # 严格块只判"表行"（`[...], [...]`）：caption 里的派生比率（6.18/5.70）
            # 不在存盘读数里，把它们算进来会制造假红。
            entries = [entry for entry in entries if entry["snippet"].lstrip().startswith("[")]
            if not entries:
                continue
        claim_lines = [entry["line"] - 1 for entry in entries]
        # 块内任一数字声明附近的 SRC 注释（±window）都算该块的来源
        near_src = sorted({src for src in src_lines if any(abs(src - line0) <= window for line0 in claim_lines)})
        artifacts: list[Path] = []
        for src in near_src:
            for offset in (-1, 0, 1):  # SRC 常写成多行续行
                idx = src + offset
                if 0 <= idx < len(lines) and has_src(lines[idx]):
                    artifacts.extend(_resolve_src_artifacts(lines[idx], root))
        artifacts = list(dict.fromkeys(artifacts))
        first_line = min(claim_lines) + 1
        snippet = entries[0]["snippet"][:160]
        if not artifacts:
            unchecked.append({"line": first_line, "snippet": snippet, "reason": "SRC 未指向可判定工件"})
            continue

        for path in artifacts:
            if path not in cache:
                cache[path] = _artifact_numbers(path)
        pool = [value for path in artifacts for value in cache[path]]
        matched: list[str] = []
        missing: list[str] = []
        for entry in entries:
            for raw, value, decimals in entry["precise"]:
                if _matches_artifact(value, decimals, pool, percent="%" in entry["snippet"]):
                    matched.append(raw)
                else:
                    missing.append(raw)
        record = {
            "line": first_line,
            "snippet": snippet,
            "numbers": [raw for entry in entries for raw, _, _ in entry["precise"]],
            "artifacts": [str(path.relative_to(root)) for path in artifacts],
        }
        if is_strict:
            # 作者显式声明「这一块是存盘读数」⇒ 逐条必须命中，不给"任一条命中"放行
            if missing:
                strict_failed.append({**record, "missing": missing})
            else:
                verified.append({**record, "matched": matched[:5]})
        elif matched:
            verified.append({**record, "matched": matched[:5]})
        else:
            failed.append({**record, "missing": missing})

    total = len(verified) + len(failed) + len(unchecked)
    return {
        "checked_total": total,
        "verified": verified,
        "failed": failed,
        "unchecked": unchecked,
        "strict_failed": strict_failed,
        "verified_count": len(verified),
        "failed_count": len(failed),
        "unchecked_count": len(unchecked),
        "strict_failed_count": len(strict_failed),
        "verified_ratio": (len(verified) / total) if total else 1.0,
    }


def _load_yaml_mapping(path: Path) -> dict[str, Any] | None:
    """尽力加载 YAML（pyyaml 缺失/解析失败 → None，不阻断审计）。"""
    try:
        import yaml  # type: ignore[import-untyped]

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:  # pragma: no cover - 环境缺 pyyaml 时保守降级
        return None


def _resolve_dotted(data: Any, dotted: str) -> bool:
    """在嵌套 mapping 中解析点分键（`benchmark.docstring_anchor.decision.verdict`）。"""
    cur = data
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return False
    return True


def find_src_lines(lines: list[str]) -> list[int]:
    """返回含 `// SRC:` 注释的行号（0-based）。"""
    return [i for i, line in enumerate(lines) if has_src(line)]


def _normalize_markup(text: str) -> str:
    """把两种稿子的写法归一，供数字模式匹配。

    `60.0\\%` 里的反斜杠会让百分比模式失配（**漏报**比误报更危险：覆盖率
    会虚高）；`~` 在 LaTeX 里是不换行空格，替换为普通空格不影响数字。
    """
    return text.replace("\\%", "%").replace("~", " ")


def _keep_math(text: str) -> str:
    """数学模式预处理：**刻意保留**数学模式内的数字（Typst / LaTeX 两种写法都适用）。

    论文的统计量大量写在数学模式里（`$p approx 2.8 times 10^(-12)$`、
    `$n=261$`、`$minus$25.7 pp`），若剥除数学模式会系统性漏报关键声明；
    因此本函数只做恒等返回，保留为显式"不改写"口径（未来若需排除公式常数
    在此集中实现，便于审计口径可追溯）。
    """
    return text


def detect_numeric_claims(lines: list[str]) -> list[dict[str, Any]]:
    """逐行识别数字声明；每行最多归并为一条声明（kind = 首个命中类别）。"""
    claims: list[dict[str, Any]] = []
    for idx, raw in enumerate(lines):
        stripped = raw.strip()
        # `//` 是 Typst 注释、`%` 是 LaTeX 注释：两者都不参与数字声明识别，
        # 否则 SRC 注释里的路径/数字会被当成正文声明（假红）。
        if not stripped or stripped.startswith("//") or stripped.startswith("%"):
            continue
        if has_src(raw):
            continue
        for kind, pattern in _NUMERIC_PATTERNS:
            match = pattern.search(_keep_math(_normalize_markup(raw)))
            if match:
                claims.append(
                    {
                        "line": idx + 1,
                        "kind": kind,
                        "match": match.group(0),
                        "snippet": stripped[:160],
                    }
                )
                break
    return claims


_CITATION_RE = re.compile(r"@([a-zA-Z][a-zA-Z0-9_]+)")
_CITATION_PSEUDO_KEYS = frozenset({"sec", "tab", "fig", "eq"})


def _paragraph_citations(lines: list[str]) -> list[set[str]]:
    """按"段落块"（连续非空行，含表格/figure 块）归集正文引文 key。

    依据：论文每个数字声明所在段落的引文即为该声明的合法外部来源——
    引用可以出现在段落开头（如 "Zhao et al. (@zhao2026…) quantify …"），
    其后若干行数字共享同一来源；用 ±N 行窗口会系统性漏判段落级引用。
    """
    blocks: list[set[str]] = []
    current: set[str] = set()
    for raw in lines:
        if raw.strip():
            for key in _CITATION_RE.findall(_strip_emails(raw)):
                if key not in _CITATION_PSEUDO_KEYS:
                    current.add(key)
            for group in _CITE_RE_LATEX.findall(raw):
                for key in group.split(","):
                    key = key.strip()
                    if key and key not in _CITATION_PSEUDO_KEYS:
                        current.add(key)
        else:
            blocks.append(current)
            current = set()
    blocks.append(current)
    return blocks


def _citations_for_line(blocks: list[set[str]], lines: list[str], line0: int) -> list[str]:
    """定位声明行所属段落块的引文 key 列表（块内顺序去重）。"""
    block_idx = 0
    for idx in range(min(line0, len(lines) - 1)):
        if not lines[idx].strip():
            block_idx += 1
    return sorted(blocks[block_idx]) if block_idx < len(blocks) else []


def compute_coverage(
    claims: list[dict[str, Any]], src_lines: list[int], window: int, draft_lines: list[str] | None = None
) -> dict[str, Any]:
    """计算覆盖：SRC 窗口覆盖 + 正文引文覆盖（外部文献数字的合法来源）。

    区分两类来源（投稿纪律）：
      - **内部工件数字** → 必须被 `// SRC:` 覆盖；
      - **外部文献数字** → 由 `@citation`（refs.bib 一手核验条目）覆盖即可；
      - 两者皆无 → 未覆盖（待对账）。
    """
    covered: list[dict[str, Any]] = []
    covered_citation: list[dict[str, Any]] = []
    uncovered: list[dict[str, Any]] = []
    blocks = _paragraph_citations(draft_lines) if draft_lines is not None else []
    for claim in claims:
        line0 = claim["line"] - 1
        nearest = min(src_lines, key=lambda s: abs(s - line0)) if src_lines else None
        distance = abs(nearest - line0) if nearest is not None else None
        citations = _citations_for_line(blocks, draft_lines, line0) if draft_lines is not None else []
        claim = dict(
            claim,
            nearest_src_line=(nearest + 1) if nearest is not None else None,
            distance=distance,
            citations=citations,
        )
        if distance is not None and distance <= window:
            covered.append(claim)
        elif citations:
            covered_citation.append(claim)
        else:
            uncovered.append(claim)
    total = len(claims)
    return {
        "total_claims": total,
        "covered_src_claims": len(covered),
        "src_coverage_ratio": (len(covered) / total) if total else 1.0,
        "covered_citation_claims": len(covered_citation),
        "traceable_claims": len(covered) + len(covered_citation),
        "traceable_ratio": ((len(covered) + len(covered_citation)) / total) if total else 1.0,
        "window_lines": window,
        "uncovered": uncovered,
        "citation_covered": covered_citation,
    }


def _iter_src_tokens(lines: list[str]) -> list[tuple[int, str]]:
    """提取 SRC 注释中的引用 token：`(行号 1-based, token 原文)`。"""
    tokens: list[tuple[int, str]] = []
    for idx, raw in enumerate(lines):
        text = src_comment(raw)
        if text is None:
            continue
        for token in re.split(r"[;,\s]+", text):
            token = _unescape_latex_path(token.strip().strip(";,.()[]{}\"'"))
            if token:
                tokens.append((idx + 1, token))
    return tokens


def validate_src_tokens(tokens: list[tuple[int, str]], root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """校验 SRC 引用有效性；返回 (引用明细, 违规描述列表)。"""
    details: list[dict[str, Any]] = []
    failures: list[str] = []
    baseline_cache: dict[str, dict[str, Any] | None] = {}

    for line_no, token in tokens:
        if not _looks_like_reference(token):
            continue
        kind = "prose"
        ok: bool | None = None

        # BASELINE.yaml#a.b.c
        if "#" in token and token.split("#", 1)[0].endswith((".yaml", ".yml")):
            path_part, key_part = token.split("#", 1)
            kind = "yaml_key"
            path = root / path_part
            if not path.exists():
                ok = False
                failures.append(f"L{line_no}: SRC 引用文件不存在：{path_part}")
            else:
                if path_part not in baseline_cache:
                    baseline_cache[path_part] = _load_yaml_mapping(path)
                data = baseline_cache[path_part]
                if data is None:
                    ok = None  # 无法解析 → 不判失败（降级）
                elif not _resolve_dotted(data, key_part):
                    ok = False
                    failures.append(f"L{line_no}: SRC 键不存在：{path_part}#{key_part}")
                else:
                    ok = True
        # ADR-00XX（含 docs/adr/ADR-00XX 形式）
        elif (m := _ADR_RE.search(token)) is not None:
            kind = "adr"
            prefix = f"{int(m.group(1)):04d}"
            adr_dir = root / "docs" / "adr"
            matches = sorted(adr_dir.glob(f"{prefix}-*")) if adr_dir.is_dir() else []
            ok = bool(matches)
            if not ok:
                failures.append(f"L{line_no}: SRC ADR 引用不存在：{token}")
        # 仓库内路径（含 / 或以已知扩展名结尾）
        elif ("/" in token or token.endswith(_KNOWN_EXT)) and not token.startswith(("http://", "https://")):
            kind = "path"
            path = root / token
            # 容忍目录 + 通配（`emse_*`）；历史 SRC 口径可能相对 experiments/results/
            candidates = [path, root / "experiments" / "results" / token]
            if any(ch in token for ch in "*?["):
                ok = False
                for cand in candidates:
                    parent = cand.parent if cand.suffix else cand
                    if parent.exists():
                        ok = True
                        break
            else:
                ok = any(cand.exists() for cand in candidates)
            if not ok:
                failures.append(f"L{line_no}: SRC 引用路径不存在：{token}")
        # 数字编号（如 0031/0032）在 ADR 语境下忽略
        if kind != "prose":
            details.append({"line": line_no, "token": token, "kind": kind, "ok": ok})
    return details, failures


def audit_bib(bib_path: Path, draft_text: str) -> dict[str, Any]:
    """引文卫生审计：被引 key 存在、bib 条目 DOI/arXiv 齐备、重复/未引用。"""
    result: dict[str, Any] = {
        "bib_exists": bib_path.exists(),
        "entries": [],
        # 引用键 = Typst 风格 `@key` **与** LaTeX 风格 `\cite{key}` 的并集。
        # CW 轮实测：只用 `_CITE_RE`（Typst 风格）时，LaTeX 稿件里 `\citet{key}`
        # 引用了 refs.bib 中不存在的键却**不报**「引用无效」——该缺口让「正文引用了
        # 尚不存在的文献」长期不可见（CW 轮正文一次引入 8 个新键，审计器一声不吭）。
        "cited_keys": sorted(
            {
                k
                for k in (
                    list(_CITE_RE.findall(_strip_emails(draft_text)))
                    + [k.strip() for group in _CITE_RE_LATEX.findall(draft_text) for k in group.split(",")]
                )
                if k and k not in {"sec", "tab", "fig", "eq", "ref", "label"}
            }
        ),
        "missing_keys": [],
        "entries_without_identifier": [],
        "duplicate_dois": [],
        "unused_entries": [],
        "cjk_entries": [],
        "failures": [],
    }
    if not bib_path.exists():
        result["failures"].append(f"bib 文件不存在：{bib_path}")
        result["missing_keys"] = result["cited_keys"]
        return result

    text = bib_path.read_text(encoding="utf-8")
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if (m := _BIB_ENTRY_RE.match(line.strip())) is not None:
            if current is not None:
                entries.append(current)
            current = {"type": m.group(1), "key": m.group(2), "raw": [line.strip()]}
        elif current is not None:
            current["raw"].append(line)
    if current is not None:
        entries.append(current)

    doi_owner: dict[str, list[str]] = {}
    keys: set[str] = set()
    for entry in entries:
        raw = "\n".join(entry["raw"])
        keys.add(entry["key"])
        dois = _BIB_DOI_RE.findall(raw)
        arxiv = bool(_BIB_ARXIV_RE.search(raw))
        for doi in dois:
            doi_owner.setdefault(doi.rstrip("."), []).append(entry["key"])
        has_id = bool(dois) or arxiv
        is_pmlr = bool(_BIB_PMLR_RE.search(raw))
        has_id = has_id or is_pmlr
        has_todo = "TODO" in raw
        cjk = _cjk_hits_text("\n".join(entry["raw"]), ".bib")
        if cjk:
            chars = "".join(sorted({ch for _lineno, found in cjk for ch in found}))
            result.setdefault("cjk_entries", []).append({"key": entry["key"], "chars": chars})
            result["failures"].append(
                f"bib 条目 {entry['key']} 的字段值含中文字符「{chars}」——note 会进 .bbl 并被原样排版，"
                "而 Latin Modern 无中文字形（PDF 参考文献处出现缺字符）"
            )
        result["entries"].append(
            {
                "key": entry["key"],
                "type": entry["type"],
                "dois": dois,
                "arxiv": arxiv,
                "has_identifier": has_id,
                "pending_todo": (not has_id) and has_todo,
            }
        )
        if not has_id:
            result["entries_without_identifier"].append(entry["key"])
            if not has_todo:
                result["failures"].append(f"bib 条目 {entry['key']} 缺少 DOI/arXiv 标识（录入纪律要求至少其一或 TODO）")
    result["duplicate_dois"] = {doi: owners for doi, owners in doi_owner.items() if len(owners) > 1}
    cited = set(result["cited_keys"])
    result["missing_keys"] = sorted(cited - keys)
    result["unused_entries"] = sorted(keys - cited)
    for key in result["missing_keys"]:
        result["failures"].append(f"正文引用 @{key} 不在 refs.bib 中")
    for key in result["entries_without_identifier"]:
        result.setdefault("warnings", []).append(f"bib 条目 {key} 缺少 DOI/arXiv 标识（TODO 挂起项，投稿前回填或降级）")
    for doi, owners in result["duplicate_dois"].items():
        result["failures"].append(f"DOI 重复：{doi} 同时出现在 {owners}")
    return result


# ── 投稿包自洽判据（CS 轮，2026-10-26）──────────────────────────────────────
# 为什么需要它：CS 轮体检发现 `paper/SUBMISSION.md`——**投稿前的最后一道人工
# 检查清单**——自己已与工件脱节四处：页数写 54（实测 `xdv` 55 / PDF 57）、表数写
# 22（实测 19）、TODO 标记写 14 处（实测 18）、refs.bib 标识口径漏了
# `publisher={PMLR}`。审稿人看到的正是这张表，而它**没有任何机制能发现自己过期**
# ——「文档低于工件」的同型沉默分叉，且发生在最后一道关口。
# 判据：SUBMISSION.md 里声明的这几个数字必须与**源文件实测**一致。
#
# ── CX 轮：页数口径整体换源（原口径**从未生效过**）─────────────────────────
# CS 轮定的页数口径是「以构建产物的 `xdv` 日志为准，日志不在场 ⇒ 披露跳过，不判红」。
# CX 轮体检发现这道判据**一次也没红过**：它取页数的那行
# 「Output written on <file> (N pages …)」在 tectonic 日志里**根本不存在**
# （tectonic 写的是 .xdv，且成功后格式也不同），于是每次都走「跳过」分支。
# 更糟的是场上的 `paper/tex/manuscript.log` 恰是**一次失败构建**留下的
# （tectonic `Fatal error occurred, no output PDF file produced!`）——
# 一个失败产物被当成了「测量源在场」，把「缺测量」伪装成「无差异」。
# 后果实测：SUBMISSION.md 里「`manuscript.pdf` | 55」这个数字，从 CS 轮写下起
# **没有任何机制在核**；CX 轮用真 LaTeX（TeX Live 2026）编译出的实测值是 **62 页**。
# 新口径（见 `measure_pdf_pages`）：唯一可信来源是 **pdftex 自己的 PDF 口径**
# （`Output written on manuscript.pdf (N pages, M bytes)`），并加四道守卫：
# 失败构建 / 非 PDF 产物 / 日志与 PDF 不同次构建 / 构建产物早于任一输入源。

_SUBMISSION_CLAIMS: dict[str, re.Pattern[str]] = {
    "pages": re.compile(r"manuscript\.pdf`\s*\|\s*(\d+)"),
    # CX 轮新增：投稿包那张表里**三份**材料各有一个页数格，原来只有第一格
    # （manuscript）进了判定面，投稿信与 title page 的页数格无人核——
    # 实测投稿信已从 2 页变成 3 页（CW 轮加的差异化段落所致），声明仍写 2。
    "cover_letter_pages": re.compile(r"`cover_letter\.pdf`\s*\|\s*(\d+)"),
    "title_page_doc_pages": re.compile(r"`title_page\.pdf`\s*\|\s*(\d+)"),
    "tables": re.compile(r"稿件\s*(\d+)\s*张表"),
    "todo_marks": re.compile(r"共\s*(\d+)\s*处待填标记"),
    "submission_abstract_words": re.compile(r"稿件\s*(\d+)\s*词"),
    # CX 轮新增：`refs.bib` N 条 的声明必须等于实测条目数——「手写数字」本身就是
    # 失实来源（CW 轮加十条后，对照表仍写 35 条；CX 轮手改时又写成 46，而实测 56）。
    "bib_entries": re.compile(r"`refs\.bib`\s*(\d+)\s*条"),
}

#: 期刊对摘要的硬上限（EMSE Text formatting：150--250 词）。
ABSTRACT_WORD_LIMIT = 250
#: 留余量的软阈值：投稿系统的分词口径不可控（连字符复合词、破折号、数字），
#: 余量低于 5 词即视为「换个口径就超限」的风险面。
ABSTRACT_WORD_MARGIN = 5

#: 投稿材料（title page / 投稿包说明）里的摘要词数与页数声明。
#: 投稿信里出现的 arXiv 号必须能在 `refs.bib` 找到，且其条目对应的键必须被正文引用。
#: 理由（CV 轮）：`paper/` 按双盲纪律不入库 ⇒ 改正文**不会**自动带动投稿信；上一轮
#: 手工同步过一次，下一轮必然漂。此判据把「投稿信引了正文没引的文献」变成可执行红线。
_ARXIV_IN_TEXT = re.compile(r"arXiv:(\d{4}\.\d{4,5})")
_BIB_ARXIV_ID = re.compile(r"arXiv:\s*(\d{4}\.\d{4,5})")

_TITLE_PAGE_CLAIMS: dict[str, re.Pattern[str]] = {
    "title_page_abstract_words": re.compile(r"Abstract:\s*(\d+)\s*words"),
    "title_page_pages": re.compile(r"Manuscript body:\s*(\d+)\s*pages"),
}


def abstract_word_counts(draft_text: str) -> tuple[int, int]:
    """摘要词数双口径：(常规, 严格)。

    - **常规**：LaTeX 记号剥离后按空白分词，连字符复合词算 1 词。
    - **严格**：同上，但连字符复合词**拆开**计数（最保守的投稿系统口径）。

    摘要段必须先**去掉 `%` 注释行**——稿件把 `% SRC:` 溯源注释放在
    `\\end{abstract}` 之前，不去注释会把路径与文件名当成正文（实测多算 29 词）。
    """
    start = draft_text.find("\\begin{abstract}")
    end = draft_text.find("\\end{abstract}")
    if start < 0 or end <= start:
        return (0, 0)
    seg = "\n".join(
        line
        for line in draft_text[start + len("\\begin{abstract}") : end].splitlines()
        if not line.lstrip().startswith("%")
    )
    seg = re.sub(r"\\(emph|textbf|textit|mbox|texttt|mathrm|textsc)\{([^{}]*)\}", r"\2", seg)
    seg = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", seg)
    seg = re.sub(r"[{}$\\&%#_^~]", " ", seg)
    raw = re.sub(r"\s+", " ", seg).strip()
    normal = [w for w in raw.split() if re.search(r"[A-Za-z0-9]", w)]
    strict = [part for word in raw.split() for part in word.split("-") if re.search(r"[A-Za-z0-9]", part)]
    return (len(normal), len(strict))


#: pdftex 成功收尾时写下的那行：`Output written on manuscript.pdf (62 pages, 511245 bytes).`
#: 页数与字节数都由 pdftex 自己报出；字节数可用来判定「日志与 PDF 是不是同一次构建」。
_BUILD_OUTPUT_RE = re.compile(r"Output written on (\S+) \((\d+) pages?, ([\d,]+) bytes?\)")

#: 构建失败的标志性输出。tectonic 失败时写
#: `Fatal error occurred, no output PDF file produced!`；pdftex 失败时写 `! Emergency stop`。
_BUILD_FAILURE_MARKERS = (
    "Fatal error occurred",
    "! Emergency stop",
    "no output PDF file produced",
)

#: 会影响投稿 PDF 的输入源。构建产物必须不早于其中**任何一个**——否则 PDF 是旧稿。
_BUILD_INPUT_FILES = (
    "manuscript.tex",
    "refs.bib",
    "svjour3.cls",
    "spbasic.bst",
    "svglov3.clo",
)


def measure_pdf_pages(
    base_dir: Path,
    stem: str,
    inputs: tuple[str, ...],
    result: dict[str, Any],
    *,
    fresh: bool = True,
) -> int | None:
    """实测一份投稿 PDF 的页数；实测不可信时判红并返回 None。

    `fresh=False` 是**构建前**档（DG 轮）：源文件刚刚改过，产物必然过期，
    此时核对页数只会把「还没构建」判成「声明失实」，让 `build_paper.sh`
    在编辑源文件后永远无法进入编译步骤。构建前只查源侧判据，页数留给构建后。

    CX 轮起因（**判据存在却从未生效**）：CS 轮定的口径是「从 `tex/manuscript.log`
    取 `Output written on … (N pages`；取不到 ⇒ 披露跳过，不判红」。而 tectonic
    的日志里根本没有这一行 ⇒ 每次都走跳过分支 ⇒ 判据一次也没红过。场上那份
    日志还是**失败构建**留下的（`Fatal error occurred, no output PDF file
    produced!`）——一个失败产物被当成了「测量源在场」，把「缺测量」伪装成
    「无差异」。SUBMISSION.md 里「55 页」因此从写下起没有任何机制在核。

    四道守卫（任一不通过 ⇒ 判红，不静默跳过）：
      1. **失败构建**：日志含失败标记 ⇒ 页数无来源；
      2. **非 PDF 产物**：日志写出的不是 `.pdf`（tectonic 写 `.xdv`）⇒ 那是 DVI
         页数，与投稿 PDF 页数不是同一口径；
      3. **不同次构建**：日志记录的字节数 ≠ 磁盘上 PDF 的实际字节数 ⇒ 日志与
         PDF 不是同一次产物，日志里的页数不能代表这份 PDF；
      4. **过期构建**：任一输入源比构建日志新 ⇒ PDF 对应的是旧稿。

    日志与 PDF 都不在场时无物可核，只披露（note），不判红——避免在没有构建的
    环境里把「没构建」误判成「声明失实」。

    参数：`base_dir` 是 `.log`/`.pdf` 所在目录，`stem` 是文件名主干，
    `inputs` 是会影响该 PDF 的输入源文件名（相对 `base_dir`）。
    """
    log_path = base_dir / f"{stem}.log"
    pdf_path = base_dir / f"{stem}.pdf"

    if not fresh:
        result["notes"].append(f"构建前档：跳过 {stem} 的页数对账（产物将在本次构建后复查）")
        return None

    if not log_path.exists():
        result["notes"].append(f"{log_path.name} 不在场（未构建）——{stem} 的页数声明无物可核，跳过")
        return None

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    for marker in _BUILD_FAILURE_MARKERS:
        if marker in log_text:
            result["failures"].append(
                f"{log_path.name} 是**失败构建**（含「{marker}」）——{stem} 的页数声明无来源，"
                "请先成功构建 PDF 再核对投稿材料"
            )
            return None

    matches = _BUILD_OUTPUT_RE.findall(log_text)
    if not matches:
        result["failures"].append(
            f"{log_path.name} 里没有 pdftex 的「Output written on … (N pages, M bytes)」行"
            f"——{stem} 的页数声明无来源，无法验证"
        )
        return None

    out_name, pages_raw, nbytes_raw = matches[-1]
    pages = int(pages_raw)
    nbytes = int(nbytes_raw.replace(",", ""))

    if not out_name.endswith(".pdf"):
        result["failures"].append(
            f"{log_path.name} 写出的产物是 `{out_name}` 而非 PDF——那是 DVI/xdv 口径的页数，"
            "与投稿 PDF 页数不是同一口径，不能用作声明值"
        )
        return None

    if not pdf_path.exists():
        result["failures"].append(f"{log_path.name} 声称写出 `{out_name}`，但 {pdf_path.name} 不在场——页数声明无来源")
        return None

    actual_bytes = pdf_path.stat().st_size
    if actual_bytes != nbytes:
        result["failures"].append(
            f"{log_path.name} 记录的字节数 {nbytes} ≠ 磁盘上 {pdf_path.name} 的实际字节数 "
            f"{actual_bytes}——日志与 PDF 不是同一次构建，日志里的页数不能代表这份 PDF"
        )
        return None

    newest_input: tuple[float, str] | None = None
    for name in inputs:
        src = base_dir / name
        if not src.exists():
            continue
        mtime = src.stat().st_mtime
        if newest_input is None or mtime > newest_input[0]:
            newest_input = (mtime, name)
    if newest_input is not None and newest_input[0] > log_path.stat().st_mtime:
        result["failures"].append(
            f"输入源 `{newest_input[1]}` 的修改时间晚于 {log_path.name}——构建产物已过期，页数声明对应的是旧稿"
        )
        return None

    return pages


def audit_submission_package(paper_dir: Path, draft_text: str, *, pre_build: bool = False) -> dict[str, Any]:
    """投稿包自洽：SUBMISSION.md 声明的页数 / 表数 / TODO 数必须与实测一致。"""
    result: dict[str, Any] = {"present": False, "claims": {}, "failures": [], "notes": []}
    submission = paper_dir / "SUBMISSION.md"
    if not submission.exists():
        result["notes"].append("paper/SUBMISSION.md 不存在——跳过投稿包自洽判定面")
        return result
    result["present"] = True
    text = submission.read_text(encoding="utf-8")

    measured: dict[str, int | None] = {
        "bib_entries": None,
        "abstract_words": None,
        "title_page_abstract_words": None,
        "submission_abstract_words": None,
        "tables": len(re.findall(r"\\begin\{table\}", draft_text)),
        # DA 轮（2026-10-26）口径修正：只算**会被排版的部分**里的 `[TODO(` 占位符。
        # 原口径按「整文件出现 TODO 次数」计 ⇒ 把**约定注释里举例**的 `[TODO(…)]` 也算进去
        # （两个文件各 1 行注释、每行 2 个 token，共 4 个），于是投稿清单会指示作者
        # 「删除全部 [TODO(…)] 标记」时**连约定说明一起删掉**，且总数与逐文件拆分
        # （当时是行数 5 + 11 = 16 ≠ token 数 18）**互相对不上**。
        # 正确口径 = 会被排版、因而必须填的占位符：投稿信 4 + title page 10 = 14。
        "todo_marks": sum(
            sum(line.count("[TODO(") for line in _stripped_lines(paper_dir / name))
            for name in ("cover_letter.tex", "title_page.tex")
            if (paper_dir / name).exists()
        ),
        "pages": None,
        "cover_letter_pages": None,
        "title_page_doc_pages": None,
    }
    measured["pages"] = measure_pdf_pages(
        paper_dir / "tex", "manuscript", _BUILD_INPUT_FILES, result, fresh=not pre_build
    )
    measured["cover_letter_pages"] = measure_pdf_pages(
        paper_dir, "cover_letter", ("cover_letter.tex",), result, fresh=not pre_build
    )
    measured["title_page_doc_pages"] = measure_pdf_pages(
        paper_dir, "title_page", ("title_page.tex",), result, fresh=not pre_build
    )

    # ── 摘要词数：双口径实测（必须先算，后面的声明才有得比）──────────────
    normal_words, strict_words = abstract_word_counts(draft_text)
    measured["abstract_words"] = normal_words
    measured["title_page_abstract_words"] = normal_words
    measured["submission_abstract_words"] = normal_words
    result["abstract_words"] = {"normal": normal_words, "strict": strict_words}
    if normal_words:
        if strict_words > ABSTRACT_WORD_LIMIT:
            result["failures"].append(
                f"摘要词数（严格口径，拆连字符）= {strict_words} 超过期刊上限 {ABSTRACT_WORD_LIMIT}"
            )
        elif strict_words > ABSTRACT_WORD_LIMIT - ABSTRACT_WORD_MARGIN:
            result["notes"].append(
                f"摘要词数（严格口径）= {strict_words}，距上限 {ABSTRACT_WORD_LIMIT} 只剩 "
                f"{ABSTRACT_WORD_LIMIT - strict_words} 词——换个分词口径即可能超限"
            )

    bib_path = paper_dir / "tex" / "refs.bib"
    if bib_path.exists():
        measured["bib_entries"] = len(re.findall(r"^@", bib_path.read_text(encoding="utf-8"), re.M))

    for key, pattern in _SUBMISSION_CLAIMS.items():
        claims = [int(m.group(1)) for m in pattern.finditer(text)]
        if not claims:
            result["notes"].append(f"SUBMISSION.md 里未取到「{key}」的声明——该项跳过")
            continue
        if len(set(claims)) > 1:
            result["failures"].append(f"SUBMISSION.md 里「{key}」的声明出现多个不同值：{sorted(set(claims))}")
            continue
        claimed = claims[0]
        actual = measured.get(key)
        result["claims"][key] = {"claimed": claimed, "measured": actual}
        if actual is None:
            continue
        if claimed != actual:
            result["failures"].append(
                f"SUBMISSION.md 声明「{key}」= {claimed}，实测 = {actual}——投稿前的人工清单已与工件脱节"
            )

    # ── title page 里的摘要词数 / 页数声明 ────────────────────────────────
    title_page = paper_dir / "title_page.tex"
    if title_page.exists():
        tp_text = title_page.read_text(encoding="utf-8")
        for key, pattern in _TITLE_PAGE_CLAIMS.items():
            claims = [int(m.group(1)) for m in pattern.finditer(tp_text)]
            if not claims:
                result["notes"].append(f"title_page.tex 里未取到「{key}」的声明——该项跳过")
                continue
            if len(set(claims)) > 1:
                result["failures"].append(f"title_page.tex 里「{key}」的声明出现多个不同值：{sorted(set(claims))}")
                continue
            claimed = claims[0]
            actual = measured.get("title_page_abstract_words" if "words" in key else "pages")
            result["claims"][key] = {"claimed": claimed, "measured": actual}
            if actual is None:
                continue
            if claimed != actual:
                result["failures"].append(
                    f"title_page.tex 声明「{key}」= {claimed}，实测 = {actual}——投稿材料已与工件脱节"
                )
    else:
        result["notes"].append("title_page.tex 不存在——跳过 title page 声明对账")

    # ── 投稿信 ↔ 正文/bib 的引文一致性 ─────────────────────────────────
    cover = paper_dir / "cover_letter.tex"
    if not cover.exists():
        result["notes"].append("cover_letter.tex 不存在——跳过投稿信引文一致性判定")
        return result
    cover_text = cover.read_text(encoding="utf-8")
    cover_ids = sorted(set(_ARXIV_IN_TEXT.findall(cover_text)))
    if not cover_ids:
        result["notes"].append("投稿信里没有 arXiv 号——跳过 arXiv 一致性判定")
        return result
    bib_path = paper_dir / "tex" / "refs.bib"
    bib_text = bib_path.read_text(encoding="utf-8") if bib_path.exists() else ""
    bib_ids: dict[str, str] = {}
    for entry in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", bib_text, re.S):
        key, body = entry.group(1), entry.group(2)
        for pid in _BIB_ARXIV_ID.findall(body):
            bib_ids.setdefault(pid, key)
    cited_keys = set()
    for group in re.findall(r"\\cite[pt]?\{([^}]+)\}", draft_text):
        for key in group.split(","):
            cited_keys.add(key.strip())
    for pid in cover_ids:
        if pid not in bib_ids:
            result["failures"].append(f"投稿信提到 arXiv:{pid}，但 refs.bib 里没有对应条目——投稿信与文献库脱节")
        elif bib_ids[pid] not in cited_keys:
            result["failures"].append(
                f"投稿信提到 arXiv:{pid}（键 {bib_ids[pid]}），但正文没有引用该键——投稿信引用了正文未引的文献"
            )
    result["cover_letter_arxiv"] = {
        "ids": cover_ids,
        "in_bib": {pid: bib_ids.get(pid) for pid in cover_ids},
        "cited": {pid: (bib_ids.get(pid) in cited_keys) for pid in cover_ids},
    }
    return result


def find_todos(draft_text: str, bib_text: str, draft_name: str) -> list[dict[str, Any]]:
    """列出稿件/bib 中的 TODO 标记（投稿前清零项）。

    DA 轮口径：**只算会被排版的部分**。DE 轮再修正：注释语法按文件类型判——
    Typst 的 `//` / `/* */` 是注释，TeX/BibTeX 的 `%` 才是注释。原实现一律剥
    `%`，于是 `.typ` 里的 `// TODO(...)` 被误列、`% TODO(...)` 反被剥掉；
    tests 还把错误语法锁成了正确规则。现在三种剥离器分开，TODO 清单只认
    各自语言里**真正会被排版**的部分。
    """
    todos: list[dict[str, Any]] = []
    draft_lines = _strip_comments(draft_text, Path(draft_name).suffix).splitlines()
    for idx, raw in enumerate(draft_lines):
        if "TODO" in raw:
            todos.append({"file": draft_name, "line": idx + 1, "snippet": raw.strip()[:180]})
    for idx, raw in enumerate(_strip_comments(bib_text, ".bib").splitlines()):
        if "TODO" in raw:
            todos.append({"file": "refs.bib", "line": idx + 1, "snippet": raw.strip()[:180]})
    return todos


def per_section_coverage(
    draft_lines: list[str], claims: list[dict[str, Any]], src_lines: list[int], window: int
) -> list[dict[str, Any]]:
    """按 `= ` 一级标题统计覆盖率（帮助定位最缺 SRC 的章节）。"""
    headings: list[tuple[int, str]] = [
        (i, line[2:].strip()) for i, line in enumerate(draft_lines) if line.startswith("= ")
    ]
    if not headings:
        return []
    sections: list[dict[str, Any]] = []
    bounds = [i for i, _ in headings] + [len(draft_lines)]
    for pos, (start, title) in enumerate(headings):
        end = bounds[pos + 1]
        section_claims = [c for c in claims if start <= c["line"] - 1 < end]
        local_src = [s for s in src_lines if start <= s < end]
        cov = compute_coverage(section_claims, local_src, window, draft_lines)
        sections.append(
            {
                "title": title,
                "start_line": start + 1,
                "claims": cov["total_claims"],
                "covered": cov["covered_src_claims"],
                "citation_covered": cov["covered_citation_claims"],
                "traceable": cov["traceable_claims"],
                "coverage_ratio": cov["traceable_ratio"],
            }
        )
    return sections


def build_audit(
    paper_dir: Path,
    window: int,
    root: Path | None = None,
    draft: str | None = None,
    *,
    pre_build: bool = False,
) -> dict[str, Any]:
    """执行完整审计并返回结构化结果（供 CLI/测试复用）。

    `root` 是 SRC 路径与工件的解析根；缺省取模块级 `PROJECT_ROOT`。**必须
    在函数体内取默认值**：写成 `root: Path = PROJECT_ROOT` 会在 def 时求值，
    测试 monkeypatch 模块常量后仍读真仓库（CM 轮实测：既有端到端测试因此
    从「合成仓全绿」变成「真仓 main_batch 已撤回 ⇒ 红」）。
    """
    if root is None:
        root = PROJECT_ROOT
    draft_path = select_draft(paper_dir, draft)
    # 文献库与稿子同目录：`paper/tex/manuscript.tex` 的 bib 是 `paper/tex/refs.bib`；
    # 写死 `paper/refs.bib` 会在 Typst 侧清理后直接报「bib 不存在」并阻断 strict。
    bib_path = draft_path.parent / DEFAULT_BIB
    if not draft_path.exists():
        return {
            "paper_present": False,
            "paper_dir": str(paper_dir),
            "note": f"{draft_path.name} 不存在（paper/ 按 .gitignore 排除；CI/无本地论文稿时跳过）",
            "failures": [],
        }
    draft_text = draft_path.read_text(encoding="utf-8")
    lines = draft_text.splitlines()
    src_lines = find_src_lines(lines)
    claims = detect_numeric_claims(lines)
    coverage = compute_coverage(claims, src_lines, window, lines)
    _, src_failures = validate_src_tokens(_iter_src_tokens(lines), root)
    number_check = verify_numbers_in_artifacts(claims, src_lines, lines, window, root)
    # 披露档（failed）不阻断：p 值 / CI / z 常数是派生量，本来就不字面存盘。
    # 只有作者用 `// SRC-CHECK: strict` 显式声明「这一块是存盘读数」时才阻断。
    number_failures = [
        f"L{item['line']}: SRC-CHECK strict 块内数字在工件中查无 {item['missing']}：{item['snippet']}"
        for item in number_check["strict_failed"]
    ]
    bib = audit_bib(bib_path, draft_text)
    submission = audit_submission_package(paper_dir, draft_text, pre_build=pre_build)
    todos = find_todos(draft_text, bib_path.read_text(encoding="utf-8") if bib_path.exists() else "", draft_path.name)
    draft_cjk = _cjk_hits_text(draft_text, draft_path.suffix)
    cjk_failures = [
        f"L{lineno}: 稿件含中文字符「{chars}」（该行会被排版；Latin Modern 无中文字形 ⇒ PDF 缺字符）"
        for lineno, chars in draft_cjk
    ]
    return {
        "paper_present": True,
        "paper_dir": str(paper_dir),
        "draft": str(draft_path),
        "bib_path": str(bib_path),
        "window_lines": window,
        "src_lines": [i + 1 for i in src_lines],
        "src_count": len(src_lines),
        "coverage": coverage,
        "sections": per_section_coverage(lines, claims, src_lines, window),
        "src_reference_failures": src_failures,
        "number_check": number_check,
        "bib": bib,
        "submission": submission,
        "todos": todos,
        "cjk_findings": [{"line": lineno, "chars": chars} for lineno, chars in draft_cjk],
        "failures": (
            src_failures
            + number_failures
            + list(bib.get("failures", []))
            + cjk_failures
            + list(submission.get("failures", []))
        ),
    }


def render_markdown(audit: dict[str, Any]) -> str:
    """把审计结果渲染为 Markdown 报告。"""
    if not audit.get("paper_present"):
        where = audit.get("paper_dir", "paper")
        return (
            f"# 论文数字-SRC 一致性审计\n\n{where} 下没有稿件（{LATEX_DRAFT} / {DEFAULT_DRAFT}），跳过（本地工具）。\n"
        )
    src_failures = audit["src_reference_failures"]
    bib = audit["bib"]
    cov = audit["coverage"]
    lines: list[str] = [
        "# 论文数字-SRC 一致性审计（Q11，2026-10-17 独立评审）",
        "",
        "> 工具：`scripts/tools/audit_paper_numbers.py`（本地工具，paper/ 不入库）",
        f"> 输入：`{audit['draft']}` / `{audit['bib_path']}`；SRC 窗口 ±{audit['window_lines']} 行",
        "",
        "## 1. 数字声明覆盖率（块级近似）",
        "",
        "| 指标 | 数值 |",
        "|---|---|",
        f"| 识别到的数字声明 | {cov['total_claims']} |",
        f"| SRC 窗口覆盖（内部工件数字） | {cov['covered_src_claims']} |",
        f"| 正文引文覆盖（外部文献数字） | {cov['covered_citation_claims']} |",
        f"| **综合可追溯率** | **{cov['traceable_ratio']:.1%}** |",
        f"| 仅 SRC 覆盖率 | {cov['src_coverage_ratio']:.1%} |",
        f"| `// SRC:` 注释数 | {audit['src_count']} |",
        "",
        "### 逐节覆盖率",
        "",
        "| 章节 | 起始行 | 声明数 | SRC 覆盖 | 引文覆盖 | 综合可追溯率 |",
        "|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| {sec['title']} | {sec['start_line']} | {sec['claims']} | {sec['covered']} | "
        f"{sec['citation_covered']} | {sec['coverage_ratio']:.1%} |"
        for sec in audit.get("sections", [])
    )
    lines += ["", "### 未覆盖的数字声明（待对账清单）", ""]
    if cov["uncovered"]:
        lines += ["| 行 | 类别 | 片段 | 最近 SRC 行 | 距离 |", "|---|---|---|---|---|"]
        for claim in cov["uncovered"]:
            snippet = claim["snippet"].replace("|", "\\|")
            lines.append(
                f"| {claim['line']} | {claim['kind']} | `{snippet}` | {claim['nearest_src_line']} | {claim['distance']} |"
            )
    else:
        lines.append("（无）")

    lines += ["", "## 2. SRC 引用有效性", ""]
    if src_failures:
        lines += [f"- ❌ {item}" for item in src_failures]
    else:
        lines.append("- ✅ 全部 SRC 引用（路径 / ADR / BASELINE 键）可解析")

    checks = audit.get("number_check")
    if checks:
        lines += ["", "## 2b. 数字存在性（读侧：声明数字是否真在所指工件里）", ""]
        lines += [
            f"- 进入判据的高精度数字声明：{checks['checked_total']} 条",
            f"- 在工件内核实：{checks['verified_count']} 条",
            f"- 工件内**查无此数**（揭露，非阻断）：{checks['failed_count']} 条",
            f"- 无可判定工件（披露）：{checks['unchecked_count']} 条",
            f"- `// SRC-CHECK: strict` 声明块失败（**阻断**）：{checks['strict_failed_count']} 条",
        ]
        blocking = checks["failed"] + checks.get("strict_failed", [])
        if blocking:
            lines += [
                "",
                "| 行 | 缺失数字 | 片段 | 所指工件 |",
                "|---|---|---|---|",
            ]
            for item in checks["failed"]:
                snippet = item["snippet"].replace("|", "\\|")[:120]
                lines.append(
                    f"| {item['line']} | `{item['missing']}` | `{snippet}` | {'<br>'.join(item['artifacts'])} |"
                )

    lines += ["", "## 3. 引文卫生", ""]
    lines += [
        f"- 正文引用 key：{len(bib['cited_keys'])} 个",
        f"- bib 条目：{len(bib['entries'])} 个",
        f"- 缺失条目（正文引用但 bib 没有）：{bib['missing_keys'] or '无'}",
        f"- 缺 DOI/arXiv 的条目（含 TODO 挂起）：{bib['entries_without_identifier'] or '无'}",
        f"- 重复 DOI：{bib['duplicate_dois'] or '无'}",
        f"- 未被正文引用的条目（warning）：{bib['unused_entries'] or '无'}",
    ]
    lines += ["", "## 4. TODO（投稿前清零）", ""]
    if audit["todos"]:
        lines += [f"- {t['file']}:{t['line']} — `{t['snippet']}`" for t in audit["todos"]]
    else:
        lines.append("（无）")
    lines += [
        "",
        "## 5. 边界",
        "",
        "- 数字识别为启发式（漏报/误报均可能），未覆盖清单须人工复核；",
        "- 覆盖率为块级近似，不等于逐条数字均已逐项追溯；",
        "- 数字存在性判据只覆盖**高精度**数字（≥2 位小数或千分位整数）且 SRC 指向"
        "可判定工件（JSON / 撤回索引）；`unchecked` 是披露不是通过，"
        "低精度数字仍靠人工逐条核对；",
        "- 本报告为本地审计工件（paper/ 不入库），不接入 CI。",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="论文稿数字-SRC 一致性审计（本地工具，Q11）")
    parser.add_argument("--paper-dir", default=str(DEFAULT_PAPER_DIR), help="论文目录（默认 paper/）")
    parser.add_argument(
        "--draft",
        default=None,
        help=f"稿子相对路径（默认优先 {LATEX_DRAFT}，缺失时回退 {DEFAULT_DRAFT}）",
    )
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW, help="SRC 覆盖窗口（行，默认 12）")
    parser.add_argument("--json", default=None, help="审计 JSON 输出路径（可选）")
    parser.add_argument("--md", default=None, help="审计 Markdown 报告输出路径（可选）")
    parser.add_argument("--strict", action="store_true", help="引用无效或覆盖率低于阈值 → exit 1")
    parser.add_argument(
        "--pre-build",
        action="store_true",
        help="构建前档：只查源侧判据，跳过页数/产物过期对账（供 build_paper.sh 第一步用）",
    )
    parser.add_argument(
        "--min-coverage", type=float, default=DEFAULT_MIN_COVERAGE, help="strict 模式下最低覆盖率（默认 0.8）"
    )
    args = parser.parse_args(argv)

    paper_dir = Path(args.paper_dir)
    if not paper_dir.is_absolute():
        paper_dir = (PROJECT_ROOT / paper_dir).resolve()
    audit = build_audit(paper_dir, args.window, draft=args.draft, pre_build=args.pre_build)
    if not audit.get("paper_present"):
        print(f"[paper-audit] {audit['note']}")
        return 0

    coverage = audit["coverage"]
    print(
        f"[paper-audit] 数字声明 {coverage['total_claims']} 条：SRC 覆盖 "
        f"{coverage['covered_src_claims']} 条（{coverage['src_coverage_ratio']:.1%}），"
        f"正文引文覆盖 {coverage['covered_citation_claims']} 条，"
        f"综合可追溯率 {coverage['traceable_ratio']:.1%}；"
        f"SRC 注释 {audit['src_count']} 条；引用无效 {len(audit['src_reference_failures'])} 项；"
        f"数字存在性 核实 {audit['number_check']['verified_count']} / "
        f"查无 {audit['number_check']['failed_count']}（披露）/ "
        f"不可判 {audit['number_check']['unchecked_count']}（披露）/ "
        f"strict 块失败 {audit['number_check']['strict_failed_count']}；"
        f"引文问题 {len(audit['bib']['failures'])} 项；TODO {len(audit['todos'])} 项"
    )
    if coverage["uncovered"]:
        print("[paper-audit] 未覆盖数字声明（前 10 条）：")
        for claim in coverage["uncovered"][:10]:
            print(f"  L{claim['line']} [{claim['kind']}] {claim['snippet']}")
    for failure in audit["failures"]:
        print(f"[paper-audit] ❌ {failure}")

    if args.json:
        Path(args.json).write_text(json.dumps(audit, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        print(f"[paper-audit] JSON 已写入 {args.json}")
    if args.md:
        Path(args.md).write_text(render_markdown(audit), encoding="utf-8")
        print(f"[paper-audit] Markdown 已写入 {args.md}")

    if args.strict:
        problems = list(audit["failures"])
        if coverage["traceable_ratio"] < args.min_coverage:
            problems.append(f"数字声明综合可追溯率 {coverage['traceable_ratio']:.1%} < 阈值 {args.min_coverage:.0%}")
        if problems:
            print(f"[paper-audit] strict 失败：{len(problems)} 项")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
