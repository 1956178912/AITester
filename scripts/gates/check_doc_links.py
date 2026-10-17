#!/usr/bin/env python3
"""G16（2026-10-17 文档完整性批次·WP-C）：Markdown 文档链接完整性门禁（零网络、纯静态）。

背景：
    本仓有 100+ 份 Markdown 文档（读 README / docs/ / examples/），此前
    **没有任何链接检查**：文件改名、路径手滑、TOC 锚点写错、跨目录相对
    路径写错，全都只能靠读者 404 时人肉发现（且 macOS 默认大小写不敏感
    文件系统会掩盖大小写错误，本地一切正常、Linux/CI 上才 404）。本门禁
    把"文档里的每一条内部链接都指向真实存在的文件/锚点"变成可机检、
    可枚举复算的 CI 阻断项。

扫描面（source，只扫这些文件里的链接）：
    - 仓库根 `*.md`（README / QUICKSTART / CONTRIBUTING / MODEL_CARD /
      SECURITY / REPLICATION / 各日期审查报告等，17 份）；
    - `docs/**/*.md`（含 adr/ design/ emse/ integration/ reviews/ security/）；
    - `examples/**/*.md`。

排除面（source 不扫）与理由：
    - `CHANGELOG.md` / `CHANGELOG.en.md`：体量 500KB+ 的历史变更日志，
      逐批记录的是"当时"的路径与文件（如已删除/改名的历史工件）。对历史
      快照做链接门禁只有两种结局：强迫回写历史（违反"历史不可改写"）或
      登记上百条 allowlist（把门禁变成噪声）。故排除——CHANGELOG 的
      **正确性**由 `check_bilingual_docs.py`（双语配对）与 `check_citations.py`
      （引用真实性）另行守护；本门禁只管"当前文档"。
    - `docs/history/**`：同上，历史实施记录 / 归档快照（20 份）。
    - `.venv/ .git/ build/ dist/ node_modules/ __pycache__/`：构建产物与
      依赖树，非文档。
    - `experiments/results/**`：实验工件树（批次 JSON / 报告 / E7 工作表）
      是**数据不是文档**，且受 SHA256SUMS 字节级保护（ruff 的 extend-exclude
      同口径）；不扫其内部 md。注意：这些路径作为**链接目标**仍然会被
      校验（见下），只是不作为 source 扫描。
    - `.private/ .workbuddy/ .github/`、`tests/*.md`、`scripts/*.md`：不在
      上述 glob 内（工作区私有笔记 / 模板 / 与代码同目录的说明），不属于
      本门禁"对外文档"口径。

校验口径：
    1. **链接解析**：inline `[text](target)`、图片 `![alt](src)`、引用式
       `[text][label]` + `[label]: target` 定义、自动链接 `<scheme:...>`。
       裸 URL（纯文本 `http://...`）不是 Markdown 链接，不解析、不计数。
    2. **代码区忽略**：fenced code block（``` / ~~~，允许 ≤3 前导空格）
       整块忽略；行内 code span（`` `...` ``）忽略——文档里的示例命令
       （`pip install -e .`、`[link](placeholder.md)` 之类）不是真实链接。
       缩进 4 空格**不**视为代码（本仓大量嵌套列表用 4 空格缩进）。
    3. **外链零网络**：`http(s):` / `mailto:` / 其他 `scheme:` 目标只计数，
       绝不发起请求（本门禁可在离线 CI / 沙箱运行；外链存活率不是本门禁
       的承诺——那需要网络且会引入外部抖动）。
    4. **文件链接**：相对源文件所在目录解析（`/` 开头按仓库根解析）；
       支持 `<...>` 包裹、百分号编码（`%20`）解码、`?query` 与 `#fragment`
       剥离；目标可以是文件**或目录**（本仓有目录链接）。
       **大小写精确校验**：逐级用 `os.listdir` 比对目录项原样大小写——
       macOS 默认大小写不敏感会把 `Docs/Foo.md` 解析成 `docs/foo.md`，
       但 Linux/CI 上 404。本门禁在本地即报"大小写不匹配"。
    5. **行锚 `#L24` / `#L24-L30`**：只校验目标文件存在，不校验行号内容。
       理由：本仓行号链接大量存在，行号随每次编辑漂移，逐行校验会制造
       高频噪声且行锚语义（"指向该文件的这段代码"）由目标文件自身守护；
       任务口径亦明确"行锚只校验文件存在"。
    6. **锚点**：实现**近似 GitHub slug**（github-slugger v2 口径：小写、
       去 HTML 标签、删除 Unicode 标点/符号类 `P*`/`S*` 但保留 `-` 与
       `_`、空白→`-`、同名标题重复加 `-1`/`-2`）。`#foo` 校验同文件锚点；
       `file.md#foo` 校验目标文件锚点；目标非 `.md` 的锚点无法静态校验 →
       warning（`unverifiable-anchor` 类）。锚点未命中且**含 CJK** 时降级为
       warning：slug 近似与 GitHub 实际渲染（emoji / 全角符号 / 渲染细节）
       可能有偏差，宁可降级也不把中文文档的大量 TOC 变成硬红；**不含 CJK
       的锚点未命中一律 error**（不允许整体跳过锚点校验）。
    7. **allowlist**：`docs/link_check_allowlist.txt`，每行
       `<源文件相对路径>:<目标原文>`，行内 `  # 理由` 为理由注释；命中
       记 `[allow]`（计入 warning 列表并附理由，但**不触发** `--strict`
       失败——登记例外本身就是"人工已判定该链接可接受"的有成本承诺，否则
       allowlist 在 CI 的 strict 档下形同虚设）。allowlist 条目必须给理由。
    8. **扫描面为空即失败**：防"文档被误删/glob 写错导致门禁静默通过"
       （`--allow-empty` 可显式放行，供空仓库构造测试）。

诚实边界：
    - 只做**静态可判定**的那一半：目标存在性与锚点可达性。不判断链接
      指向的内容是否语义正确（如"README 说 96% 而链接指向旧报告"）；
    - 外链不判存活、不判重定向；锚点 slug 是近似实现，极端 Unicode 标题
      可能偏差（CJK 已按警告降级）；
    - 被排除的 source（CHANGELOG / docs/history）内部坏链不在本门禁范围。

用法：
    python scripts/gates/check_doc_links.py            # 人读报告；有 error 退出 1
    python scripts/gates/check_doc_links.py --strict   # warning 也视为失败（CI）
    python scripts/gates/check_doc_links.py --json     # 结构化输出（机器消费）
    python scripts/gates/check_doc_links.py --allowlist docs/link_check_allowlist.txt
    python scripts/gates/check_doc_links.py --root .   # 指定仓库根（测试用）

退出码：0 = 通过（无 error；`--strict` 时还要求无"非 allowlist" warning）；
        1 = 有 error，或 `--strict` 下存在非 allowlist warning。

CI 接线（给 Lead 的片段，本文件不改 Makefile / .github）：
    make docs-check 追加一行：
        $(PY) scripts/gates/check_doc_links.py --strict
    ci.yml docs 作业追加 step：
        - name: Documentation link integrity
          run: python scripts/gates/check_doc_links.py --strict
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 扫描面（source）：根级 md + docs 递归 + examples 递归。
SCAN_GLOBS: tuple[str, ...] = ("*.md", "docs/**/*.md", "examples/**/*.md")

# 排除的 source 文件 / 目录前缀（理由见模块 docstring 的"排除面"）。
EXCLUDED_SOURCE_FILES: frozenset[str] = frozenset(
    {
        "CHANGELOG.md",  # 500KB+ 历史变更日志：历史链接不作门禁（见 docstring）
        "CHANGELOG.en.md",
    }
)
EXCLUDED_SOURCE_PREFIXES: tuple[str, ...] = (
    "docs/history/",  # 历史快照归档（同上）
)
EXCLUDED_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "build",
        "dist",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
    }
)

# 例外登记清单（真实例外人工登记，必须带理由）。
DEFAULT_ALLOWLIST = Path("docs/link_check_allowlist.txt")

# 行锚：`#L24` / `#L24-L30`（只校验文件存在，见口径 5）。
_LINE_ANCHOR_RE = re.compile(r"^L\d+(?:-L\d+)?$")
# 外部 scheme（含 mailto / ftp / 自定义）；外链只统计不请求（口径 3）。
_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
# fenced code block 起始（口径 2）。
_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
# 行内 code span：支持 1-3 个反引号包裹（口径 2）。
_INLINE_CODE_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)")
# inline 链接 / 图片：target 支持 <...> 包裹与无空格普通路径（含单层括号）。
_LINK_RE = re.compile(
    r"(?P<bang>!?)\[(?P<text>(?:\\.|[^\[\]\\])*)\]"
    r"\(\s*(?P<target><[^<>\n]*>|[^\s()<>]+(?:\([^\s()]*\)[^\s()<>]*)?)"
    r"(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^()]*\)))?\s*\)"
)
# 引用式链接定义 + 使用（本仓当前 0 处，支持以防未来引入）。
_REF_DEF_RE = re.compile(r"^ {0,3}\[([^\]^][^\]]*)\]:\s*(<[^<>\n]*>|\S+)", re.MULTILINE)
_REF_USE_RE = re.compile(r"(?P<bang>!?)\[(?:\\.|[^\[\]\\])*\]\[(?P<label>[^\[\]]+)\]")
# 自动链接 <scheme:...>（口径 1）。
_AUTOLINK_RE = re.compile(r"<(?P<target>[A-Za-z][A-Za-z0-9+.\-]*:[^<>\s]+)>")
# ATX 标题（anchor 来源）。
_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_HTML_TAG_RE = re.compile(r"<[^>]*>")
_BACKSLASH_ESCAPE_RE = re.compile(r"\\(.)")
# 块引用前缀（`> ` / `>> `）：跨行链接常被 `>` 续行包裹，解析前剥离。
_BLOCKQUOTE_PREFIX_RE = re.compile(r"(?m)^(?: {0,3}> ?)+")
# Markdown 强调标记（**bold** / __bold__ / *it* / _it_）：GitHub slug 基于
# 渲染后文本，强调标记不进入 id；粗体/斜体先还原为纯文本再算 slug。
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1")
_ITALIC_RE = re.compile(r"(?<!\w)([*_])(?=\S)(.+?)(?<=\S)\1(?!\w)")
# github-slugger v2：删除 Unicode 标点/符号（保留 - 与 _ 两个例外）。
_SLUG_KEEP = frozenset({"-", "_"})

_LISTDIR_CACHE: dict[Path, frozenset[str]] = {}


@dataclass(frozen=True)
class Finding:
    """一条链接问题（error / warning / allowlist 命中统一结构）。"""

    source: str
    line: int
    target: str
    message: str
    allowlisted: bool = False
    reason: str = ""

    def as_dict(self) -> dict[str, object]:
        out: dict[str, object] = {
            "source": self.source,
            "line": self.line,
            "target": self.target,
            "message": self.message,
        }
        if self.allowlisted:
            out["allowlisted"] = True
            out["reason"] = self.reason
        return out


@dataclass
class ScanStats:
    """可枚举复算的统计（报告/JSON 的"分母"必须能对上）。"""

    files: int = 0
    links_total: int = 0
    internal_links: int = 0
    external_links: int = 0
    image_links: int = 0
    file_links: int = 0
    directory_links: int = 0
    anchor_links: int = 0
    line_anchor_links: int = 0
    unverifiable_anchor_links: int = 0
    allowlist_hits: int = 0
    files_by_area: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "scanned_files": self.files,
            "files_by_area": self.files_by_area,
            "links_total": self.links_total,
            "internal_links": self.internal_links,
            "external_links": self.external_links,
            "image_links": self.image_links,
            "file_links": self.file_links,
            "directory_links": self.directory_links,
            "anchor_links": self.anchor_links,
            "line_anchor_links": self.line_anchor_links,
            "unverifiable_anchor_links": self.unverifiable_anchor_links,
            "allowlist_hits": self.allowlist_hits,
        }


@dataclass
class ScanResult:
    """一次扫描的完整结果。"""

    root: str
    stats: ScanStats = field(default_factory=ScanStats)
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)

    @property
    def strict_warnings(self) -> list[Finding]:
        """`--strict` 会升级为失败的警告（allowlist 命中不升级，口径 7）。"""
        return [w for w in self.warnings if not w.allowlisted]

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, object]:
        return {
            "root": self.root,
            **self.stats.as_dict(),
            "errors": [f.as_dict() for f in self.errors],
            "warnings": [f.as_dict() for f in self.warnings],
            "ok": self.ok and not self.strict_warnings,
        }


@dataclass(frozen=True)
class LinkHit:
    """解析到的一条链接（offset 用于回算行号）。"""

    offset: int
    kind: str  # "link" | "image" | "autolink"
    target: str


# ---------------------------------------------------------------------------
# 解析层
# ---------------------------------------------------------------------------


def mask_fenced(text: str) -> str:
    """把 fenced code block（``` / ~~~）整块替换为空行，保留总行数。

    行号回算依赖"行数不变"，因此块内每一行都替换为空行。
    独立于行内 code masking：提取标题锚点时行内 code 的内容必须保留
    （`## `foo` bar` 的 slug 是 `foo-bar`），只有 fenced 块里的 `#` 行
    不是标题。
    """
    out: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        m = _FENCE_RE.match(line)
        if fence is not None:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append("")
            continue
        if m:
            fence = m.group(1)
            out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def mask_code(text: str) -> str:
    """把代码区（fenced block / 行内 code span）替换为空白，保留行数。

    用于链接解析：代码里的示例链接不是真实链接（口径 2）。
    """
    masked_fenced = mask_fenced(text)
    return "\n".join(
        _INLINE_CODE_RE.sub(lambda mm: " " * len(mm.group(0)), line) for line in masked_fenced.splitlines()
    )


def strip_blockquote_prefixes(text: str) -> str:
    """剥离 `>` 续行前缀（跨行链接常被块引用续行包裹，口径 1）。"""
    return _BLOCKQUOTE_PREFIX_RE.sub("", text)


def github_slug(heading: str) -> str:
    """近似 GitHub 标题 slug（github-slugger v2 口径，见口径 6 / docstring）。"""
    s = heading.strip().lower()
    out: list[str] = []
    for ch in s:
        if ch in _SLUG_KEEP:
            out.append(ch)
            continue
        category = unicodedata.category(ch)
        if category.startswith("P") or category.startswith("S"):
            continue
        out.append("-" if ch.isspace() else ch)
    return "".join(out)


def heading_text(raw: str) -> str:
    """把标题原文还原为"渲染后的纯文本"（链接取文本、code 取内容、去强调）。"""
    s = _LINK_RE.sub(lambda m: m.group("text"), raw)
    s = _INLINE_CODE_RE.sub(lambda m: m.group(2), s)
    s = _HTML_TAG_RE.sub("", s)
    s = _BOLD_RE.sub(r"\2", s)
    s = _ITALIC_RE.sub(r"\2", s)
    return _BACKSLASH_ESCAPE_RE.sub(r"\1", s)


def extract_anchors(text: str) -> set[str]:
    """提取文档全部锚点（标题 slug + 重复标题 -1/-2 后缀）。

    只 mask fenced 块（块内 `#` 行不是标题）；行内 code 保留内容——GitHub
    的 slug 取自渲染后文本，`` `foo` `` 的锚点是 `foo`。
    """
    masked = mask_fenced(text)
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in masked.splitlines():
        m = _HEADING_RE.match(line)
        if not m:
            continue
        slug = github_slug(heading_text(m.group(2)))
        if not slug:
            continue
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def split_target(target: str) -> tuple[str, str]:
    """拆分链接目标为 (path, anchor)：剥离 `?query` 与 `#fragment`。"""
    path, _, fragment = target.partition("#")
    path = path.split("?", 1)[0]
    return path, fragment


def strip_angle(target: str) -> str:
    """去掉 <...> 包裹（Markdown 允许尖括号包路径）。"""
    t = target.strip()
    if t.startswith("<") and t.endswith(">"):
        return t[1:-1]
    return t


def parse_links(text: str) -> list[LinkHit]:
    """解析一段 Markdown（已 mask 代码区）中的全部链接/图片/自动链接。"""
    hits: list[LinkHit] = []
    for m in _LINK_RE.finditer(text):
        kind = "image" if m.group("bang") else "link"
        hits.append(LinkHit(m.start(), kind, strip_angle(m.group("target"))))
    refs = {m.group(1).strip().lower(): strip_angle(m.group(2)) for m in _REF_DEF_RE.finditer(text)}
    if refs:
        for m in _REF_USE_RE.finditer(text):
            label = m.group("label").strip().lower()
            if label in refs:
                hits.append(LinkHit(m.start(), "image" if m.group("bang") else "link", refs[label]))
    hits.extend(LinkHit(m.start(), "autolink", m.group("target")) for m in _AUTOLINK_RE.finditer(text))
    hits.sort(key=lambda h: h.offset)
    return hits


# ---------------------------------------------------------------------------
# 文件系统层
# ---------------------------------------------------------------------------


def iter_doc_files(root: Path) -> list[Path]:
    """枚举扫描面内的 source 文件（排序去重；排除面见 docstring）。"""
    found: list[Path] = []
    for pattern in SCAN_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel in EXCLUDED_SOURCE_FILES:
                continue
            if rel.startswith(EXCLUDED_SOURCE_PREFIXES):
                continue
            if any(part in EXCLUDED_DIR_NAMES for part in Path(rel).parts):
                continue
            found.append(path)
    unique: dict[Path, None] = {}
    for path in found:
        unique.setdefault(path, None)
    return sorted(unique, key=lambda p: p.relative_to(root).as_posix())


def load_allowlist(path: Path | None) -> dict[str, str]:
    """读取 allowlist：`<源文件>:<目标>` + 行内 `# 理由` 注释（口径 7）。"""
    if path is None or not path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\s+#\s*", line, maxsplit=1)
        key = parts[0].strip()
        reason = parts[1].strip() if len(parts) > 1 else ""
        if ":" in key:
            out[key] = reason
    return out


def _entries(directory: Path) -> frozenset[str]:
    """目录项名字集合（带缓存；读失败返回空集）。"""
    cached = _LISTDIR_CACHE.get(directory)
    if cached is not None:
        return cached
    try:
        entries = frozenset(os.listdir(directory))
    except OSError:
        entries = frozenset()
    _LISTDIR_CACHE[directory] = entries
    return entries


def exact_exists(root: Path, path: Path) -> tuple[bool, bool]:
    """返回 (大小写精确存在, 大小写不敏感存在)。

    macOS 默认大小写不敏感：`Docs/Foo.md` 会被 `exists()` 当成
    `docs/foo.md`，但 Linux/CI 上 404。这里逐级用 listdir 比对原样大小写，
    在 macOS 本地就能抓出"本地绿、CI 红"的错误（口径 4）。
    仓库根之外的路径（理论上不应有）退回 `Path.exists()`。
    """
    try:
        rel = path.relative_to(root)
    except ValueError:
        exists = path.exists()
        return exists, exists
    current = root
    for part in rel.parts:
        if part in ("", "."):
            continue
        if part == "..":
            exists = path.exists()
            return exists, exists
        entries = _entries(current)
        if part in entries:
            current = current / part
            continue
        if part.lower() in {entry.lower() for entry in entries}:
            return False, True
        return False, False
    exists = path.exists()
    return exists, exists


def _relative(root: Path, path: Path) -> str:
    """仓库根的相对路径（不在根下则原样输出）。"""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------------------
# 扫描层
# ---------------------------------------------------------------------------


def _area_of(rel: str) -> str:
    """文件所属区域（根 / docs / examples），用于分区统计。"""
    head = rel.split("/", 1)[0]
    if "/" not in rel:
        return "root"
    return head if head in ("docs", "examples") else "other"


def _record(result: ScanResult, allowlist: dict[str, str], finding: Finding) -> None:
    """错误分级：allowlist 命中 → warning（带理由）；否则 → error（口径 7）。

    无理由的 allowlist 条目本身判为 error：豁免是"人工已判定该链接可接受"
    的有成本承诺，必须写清理由，否则清单会退化成无声的坏链垃圾桶。
    """
    key = f"{finding.source}:{finding.target}"
    if key in allowlist:
        reason = allowlist[key]
        if not reason:
            result.errors.append(
                Finding(
                    finding.source,
                    finding.line,
                    finding.target,
                    f"allowlist 条目缺少理由：{key}（每行必须写 ` # 理由`；"
                    "若无法给出理由则说明这不是真实例外，应修复链接或删除条目）",
                )
            )
            return
        result.stats.allowlist_hits += 1
        result.warnings.append(
            Finding(
                finding.source,
                finding.line,
                finding.target,
                f"[allowlist] {finding.message}",
                allowlisted=True,
                reason=reason,
            )
        )
        return
    result.errors.append(finding)


def _check_anchor(
    result: ScanResult,
    root: Path,
    source_rel: str,
    line: int,
    target: str,
    anchor_cache: dict[Path, set[str]],
    md_path: Path,
    anchor: str,
) -> None:
    """校验锚点是否命中目标 Markdown 的标题 slug 集合（口径 6）。"""
    anchors = anchor_cache.get(md_path)
    if anchors is None:
        anchors = extract_anchors(md_path.read_text(encoding="utf-8", errors="replace"))
        anchor_cache[md_path] = anchors
    wanted = unquote(anchor)
    if wanted in anchors:
        return
    lowered = wanted.lower()
    if lowered in anchors:
        return
    message = f"锚点未命中：{_relative(root, md_path)}#{anchor}"
    similar = sorted(a for a in anchors if a.lower() == lowered)
    if similar:
        message += f"（仅大小写近似：{similar[0]}）"
    if any("\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" for ch in wanted):
        result.stats.unverifiable_anchor_links += 1
        result.warnings.append(
            Finding(source_rel, line, target, f"{message}（含 CJK：slug 近似可能与 GitHub 渲染有偏差，降级警告）")
        )
        return
    result.stats.unverifiable_anchor_links += 1
    result.errors.append(Finding(source_rel, line, target, message))


def scan(
    root: Path | None = None,
    allowlist: dict[str, str] | None = None,
) -> ScanResult:
    """扫描 root 下全部 source 文档的链接完整性（纯静态，零网络）。

    Args:
        root: 仓库根；None 时用脚本上两级（真实仓库）。
        allowlist: 例外清单 {`<源文件>:<目标原文>`: 理由}；None 时自动读取
            `root/docs/link_check_allowlist.txt`。

    Returns:
        ScanResult：统计 + errors + warnings（allowlist 命中在 warnings 且
        标 `allowlisted=True`）。
    """
    root = Path(os.path.abspath(root if root is not None else PROJECT_ROOT))
    if allowlist is None:
        allowlist = load_allowlist(root / DEFAULT_ALLOWLIST)
    result = ScanResult(root=root.as_posix())
    files = iter_doc_files(root)
    result.stats.files = len(files)
    by_area: dict[str, int] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        area = _area_of(rel)
        by_area[area] = by_area.get(area, 0) + 1
    result.stats.files_by_area = by_area
    anchor_cache: dict[Path, set[str]] = {}

    for source in files:
        source_rel = source.relative_to(root).as_posix()
        raw = source.read_text(encoding="utf-8", errors="replace")
        # 先剥块引用前缀再 mask 代码区：跨行链接常被 `> ` 续行包裹，且块引用
        # 内的 fenced code 也要被正确识别为代码（口径 1 / 2）。
        masked = mask_code(strip_blockquote_prefixes(raw))
        for hit in parse_links(masked):
            line = masked.count("\n", 0, hit.offset) + 1
            result.stats.links_total += 1
            if hit.kind == "image":
                result.stats.image_links += 1
            if _SCHEME_RE.match(hit.target) or hit.target.startswith("//"):
                # 外链：只计数不请求（口径 3）。
                result.stats.external_links += 1
                continue
            path_part, anchor = split_target(hit.target)
            path_part = unquote(path_part)
            result.stats.internal_links += 1
            if path_part == "":
                # 同文件锚点（`#foo`）。
                if not anchor:
                    result.errors.append(Finding(source_rel, line, hit.target, "空链接目标（`#` 后无锚点且无路径）"))
                    continue
                result.stats.anchor_links += 1
                _check_anchor(result, root, source_rel, line, hit.target, anchor_cache, source, anchor)
                continue
            target_path = Path(path_part)
            if target_path.is_absolute():
                target_path = root / target_path.as_posix().lstrip("/")
            else:
                target_path = source.parent / target_path
            target_path = Path(os.path.normpath(target_path.as_posix()))
            exists, case_ok = exact_exists(root, target_path)
            if not exists:
                _record(
                    result,
                    allowlist,
                    Finding(source_rel, line, hit.target, f"目标不存在：{_relative(root, target_path)}"),
                )
                continue
            if not case_ok:
                _record(
                    result,
                    allowlist,
                    Finding(
                        source_rel,
                        line,
                        hit.target,
                        f"大小写不匹配：{_relative(root, target_path)}（macOS 可解析，Linux/CI 上 404）",
                    ),
                )
                continue
            if not anchor:
                if target_path.is_dir():
                    result.stats.directory_links += 1
                else:
                    result.stats.file_links += 1
                continue
            if _LINE_ANCHOR_RE.match(anchor):
                # 行锚：只校验文件存在（口径 5）。
                result.stats.line_anchor_links += 1
                continue
            if target_path.suffix.lower() == ".md":
                result.stats.anchor_links += 1
                _check_anchor(result, root, source_rel, line, hit.target, anchor_cache, target_path, anchor)
            else:
                # 非 Markdown 目标的锚点无法静态校验（口径 6）。
                result.stats.anchor_links += 1
                result.stats.unverifiable_anchor_links += 1
                result.warnings.append(
                    Finding(
                        source_rel,
                        line,
                        hit.target,
                        f"非 Markdown 目标锚点无法静态校验：{_relative(root, target_path)}#{anchor}",
                    )
                )
    return result


# ---------------------------------------------------------------------------
# 报告层
# ---------------------------------------------------------------------------


def print_report(result: ScanResult, strict: bool) -> int:
    """打印人读报告并返回退出码（统计必须可枚举复算）。"""
    for warning in result.warnings:
        tag = "[allow]" if warning.allowlisted else "[warn]"
        suffix = f"（理由：{warning.reason}）" if warning.allowlisted and warning.reason else ""
        print(f"  {tag} {warning.source}:{warning.line}: {warning.target} —— {warning.message}{suffix}")
    for error in result.errors:
        print(f"  [FAIL] {error.source}:{error.line}: {error.target} —— {error.message}")
    stats = result.stats
    areas = " / ".join(f"{area} {count}" for area, count in sorted(stats.files_by_area.items()))
    strict_warn = result.strict_warnings
    print(
        f"\n扫描文件 {stats.files} 份（{areas}）；"
        f"链接 {stats.links_total} 条（内部 {stats.internal_links} / 外链 {stats.external_links} / 图片 {stats.image_links}）；"
        f"文件 {stats.file_links}、目录 {stats.directory_links}、"
        f"锚点 {stats.anchor_links}、行锚 {stats.line_anchor_links}；"
        f"错误 {len(result.errors)}、警告 {len(result.warnings)}（其中 allowlist {stats.allowlist_hits}）、"
        f"无法静态校验 {stats.unverifiable_anchor_links}"
    )
    if not result.errors and not (strict and strict_warn):
        print("文档链接完整性检查通过" + ("（strict：0 错误 / 0 需处理警告）" if strict else ""))
        return 0
    reason = ""
    if strict and strict_warn and not result.errors:
        reason = f"（strict：{len(strict_warn)} 条需处理警告升级为失败）"
    print(f"文档链接完整性检查失败{reason}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Markdown 文档链接完整性门禁（零网络、纯静态）")
    parser.add_argument("--strict", action="store_true", help="warning 也视为失败（CI 口径）")
    parser.add_argument("--json", action="store_true", help="输出 JSON（机器消费）")
    parser.add_argument("--allowlist", type=Path, default=None, help=f"allowlist 路径（默认 {DEFAULT_ALLOWLIST}）")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="扫描面为空时视为通过（默认：为空即失败——防门禁因文档被误删而静默失效）",
    )
    parser.add_argument("--root", type=Path, default=None, help="仓库根（默认脚本上两级；测试用）")
    args = parser.parse_args(argv)

    root = Path(os.path.abspath(args.root if args.root is not None else PROJECT_ROOT))
    allowlist_path = args.allowlist if args.allowlist is not None else root / DEFAULT_ALLOWLIST
    result = scan(root=root, allowlist=load_allowlist(allowlist_path))

    if result.stats.files == 0 and not args.allow_empty:
        message = "[FAIL] 未找到任何扫描目标（SCAN_GLOBS 无命中）——门禁失效，请检查文档是否被误删"
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2) if args.json else message)
        return 1
    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
        return 0 if result.ok and not (args.strict and result.strict_warnings) else 1
    return print_report(result, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
