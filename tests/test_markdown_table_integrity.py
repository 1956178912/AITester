#!/usr/bin/env python3
"""GFM 表格「行格数 > 表头列数 ⇒ 尾格被静默丢弃」的回归锁定（AB-7，2026-10-20，零 LLM）。

背景：README、状态登记册、预注册册里各有表格行把**裸 `|` 写进了行内代码**——shell 管道
（`ci.yml | sort -u`）、正则交替（`(API_KEY|BASE_URL)`、`(not in|!=|==)`）、绝对值记号
（`P(|delta|<=ROPE)`）。GFM 切单元格时**不认行内代码**，这些 `|` 照样把行切开；而当一个
行的格数**超过表头列数**时，超出的尾格被渲染器**直接丢弃**。于是文档源码看起来什么都不缺，
渲染出来却少一整格：README 的「安全审查」行丢掉 provider 名单之后的全部文字，登记册
「门禁总数」行丢掉整列「验证入口」。本文件锁定两件事：

1. **全仓活文档零丢格**（含把已修的 3 行逐一还原转义的变异验证——还原必红；
   另有 3 行随 DD 轮文档重写归档退役，见 `FIXED_ROWS` 注释）；
2. **判定器自身的 GFM 语义**，包括奇偶反斜杠规则：GitHub 的 cmark-gfm 只在「`|` 前有奇数
   个反斜杠」时视为转义，故 `` `\\|` ``（偶数个）在 GitHub 上**照样切格**；markdown-it 只认
   单个反斜杠，两者对 `` `\\|` `` 结论相反。判定器按 **GitHub 口径**实现，另设一例与
   markdown-it 的对照（该包非本项目声明依赖，缺席即 skip）。

「少于表头列数」不丢内容（渲染器补空格），属外观问题，本锁一律不报。

冻结面（只登记不修，按棘轮收口——允许变好、不允许变坏）：`docs/history/` 是历史快照
（不可回写），`experiments/results/` 是批次工件（其中两处带 `SHA256SUMS`，改写即破坏
`checksum_results.py --verify`）。`.private/`、`.workbuddy/` 不在 git 里，属机器本地目录，
一律不扫——否则 CI 与本地的结论会随目录存在与否漂移。
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

FROZEN_PREFIXES: tuple[str, ...] = ("docs/history/", "experiments/results/")
UNTRACKED_PREFIXES: tuple[str, ...] = (".private/", ".workbuddy/", ".venv/", "node_modules/")
# 2026-10-20 AB-7 实测：冻结面现存丢格行总数。棘轮只许下降。
REGISTERED_FROZEN_LOSS_ROWS = 9
# 逐文件清单（文件 → 现存丢格行数）。只许缩小不许扩大：新文件里的丢格行按 0 登记，
# 一律判为未登记。草稿曾把总数写成 12——那是不含「分隔行须与表头等宽」这条 GFM 规则
# 时的宽口径产物，按实测 9 行收紧（清单由 scan_root 现算复核，不靠记忆）。
FROZEN_LOSS_INVENTORY: dict[str, int] = {
    "docs/history/assessment_2026-09-25_improvement_directions.md": 1,
    "docs/history/optimization_plan.en.md": 2,
    "docs/history/optimization_plan.md": 2,
    "experiments/results/self_mutation_20261017/survivor_attribution.md": 2,
    "experiments/results/t_round_b1_protocol_text_20261018/README.md": 1,
    "experiments/results/t_round_b2_main_batch_20261018/PREREG.md": 1,
}

_CELL = r"\s*:?-+:?\s*"
_DELIM_RE = re.compile(rf"^\s*\|?{_CELL}(\|{_CELL})+\|?\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_MAX_TABLE_INDENT = 3

# 活文档里修好的 3 行（文件, 唯一定位锚文本, 表头列数）。
# 不用行号：文档增删会让行号漂移（AB-7 自己就漂过一次——§3.2 插入新行把登记册那行从
# 243 推到 244）。锚文本必须在文件里唯一命中，否则两例变异测试当场失败，不许静默空跑。
# DD 轮（2026-10-26）文档重写：README 的两处表格锚点（`**安全审查**` /
# `凭证剔除 P0 补强回归`）随旧 README 归档到 docs/history/（该目录按冻结面只登记
# 不修，且在扫描面之外）⇒ 三条锚点退役；活文档零丢格判据不变。
FIXED_ROWS: tuple[tuple[str, str, int], ...] = (
    ("docs/PROJECT_STATUS_REGISTER.md", "| 门禁总数 |", 3),
    ("docs/PROJECT_STATUS_REGISTER.md", "布尔口径残留分裂", 3),
    ("docs/preregistration.en.md", "e4_quixbugs_aitester", 6),
)


def _line_of(rel: str, anchor: str) -> int:
    lines = (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
    hits = [index + 1 for index, line in enumerate(lines) if anchor in line]
    assert len(hits) == 1, f"{rel} 的定位锚 {anchor!r} 命中 {hits} 行，无法唯一定位"
    return hits[0]


def _split_cells(line: str) -> list[str]:
    """按 cmark-gfm 口径切一行：`|` 前有奇数个反斜杠才不切。"""
    text = line.strip()
    parts: list[str] = []
    current: list[str] = []
    for index, char in enumerate(text):
        if char == "|":
            backslashes = 0
            probe = index - 1
            while probe >= 0 and text[probe] == "\\":
                backslashes += 1
                probe -= 1
            if backslashes % 2 == 0:
                parts.append("".join(current))
                current = []
                continue
        current.append(char)
    parts.append("".join(current))
    if text.startswith("|"):
        parts = parts[1:]
    if text.endswith("|") and parts:
        parts = parts[:-1]
    return parts


def _cell_count(line: str) -> int:
    return len(_split_cells(line))


def _looks_like_row(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and "|" in stripped and len(line) - len(line.lstrip()) <= _MAX_TABLE_INDENT


def tables_of(text: str) -> Iterator[tuple[int, int, list[tuple[int, int]]]]:
    """产出 (表头行号, 表头列数, [(数据行号, 该行格数)])，行号自 1 起；跳过围栏内区域。"""
    lines = text.splitlines()
    in_fence = False
    index = 0
    while index < len(lines):
        if _FENCE_RE.match(lines[index]):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence or index + 1 >= len(lines) or not _looks_like_row(lines[index]):
            index += 1
            continue
        header_cells = _cell_count(lines[index])
        if header_cells < 1 or not _DELIM_RE.match(lines[index + 1]):
            index += 1
            continue
        if _cell_count(lines[index + 1]) != header_cells:
            # GFM 要求分隔行与表头等宽，否则整段不是表格。
            index += 1
            continue
        rows: list[tuple[int, int]] = []
        walker = index + 2
        while walker < len(lines) and _looks_like_row(lines[walker]):
            rows.append((walker + 1, _cell_count(lines[walker])))
            walker += 1
        yield index + 1, header_cells, rows
        index = walker


def content_loss_rows(text: str) -> list[tuple[int, int, int]]:
    """格数超过表头列数的数据行 = 会被渲染器丢掉尾格的行。"""
    return [
        (line_no, header_cols, row_cols)
        for _, header_cols, rows in tables_of(text)
        for line_no, row_cols in rows
        if row_cols > header_cols
    ]


def _relpath(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_scanned(rel: str) -> bool:
    return not rel.startswith(UNTRACKED_PREFIXES)


def _is_frozen(rel: str) -> bool:
    return rel.startswith(FROZEN_PREFIXES)


def scan_root(root: Path) -> dict[str, list[tuple[int, int, int]]]:
    hits: dict[str, list[tuple[int, int, int]]] = {}
    for path in sorted(root.rglob("*.md")):
        rel = _relpath(path, root)
        if not _is_scanned(rel):
            continue
        found = content_loss_rows(path.read_text(encoding="utf-8", errors="replace"))
        if found:
            hits[rel] = found
    return hits


def live_markdown_paths() -> list[Path]:
    return [
        path
        for path in sorted(REPO_ROOT.rglob("*.md"))
        if _is_scanned(_relpath(path, REPO_ROOT)) and not _is_frozen(_relpath(path, REPO_ROOT))
    ]


class TestGfmCellSemantics:
    def test_bare_pipe_in_code_span_splits_the_row(self):
        text = "| a | b |\n|---|---|\n| x `grep p | sort` | y |\n"
        assert content_loss_rows(text) == [(3, 2, 3)]

    def test_escaped_pipe_stays_inside_one_cell(self):
        text = "| a | b |\n|---|---|\n| x `grep p \\| sort` | y |\n"
        assert content_loss_rows(text) == []

    def test_even_backslashes_before_pipe_still_splits_on_github(self):
        r"""`` `\\|` ``（偶数个反斜杠）在 cmark-gfm 里是「字面反斜杠 + 切格竖线」，必须判为丢格。

        这正是 AB-7 第一轮修复自己踩的坑：当时用 markdown-it 校验判「已修好」，GitHub 却
        照样丢格——两个参考实现对同一份文本结论相反。
        """
        text = "| a | b |\n|---|---|\n| x `a \\\\| b` | y |\n"
        assert content_loss_rows(text) == [(3, 2, 3)]

    def test_odd_backslashes_before_pipe_is_escaped(self):
        text = "| a | b |\n|---|---|\n| x `a \\\\.b \\| c` | y |\n"
        assert content_loss_rows(text) == []

    def test_row_narrower_than_header_only_blanks_a_cell(self):
        text = "| a | b | c |\n|---|---|---|\n| 1 | 2 |\n"
        assert content_loss_rows(text) == []

    def test_delimiter_width_must_match_header(self):
        text = "| a | b |\n|---|---|---|\n| 1 | 2 | 3 |\n"
        assert list(tables_of(text)) == []

    def test_fenced_example_table_is_not_scanned(self):
        text = "```markdown\n| a | b |\n|---|---|\n| 1 | 2 | 3 |\n```\n"
        assert content_loss_rows(text) == []

    def test_four_space_indent_is_code_not_a_table(self):
        text = "| a | b |\n|---|---|\n    | 1 | 2 | 3 |\n"
        assert content_loss_rows(text) == []


class TestCurrentRepo:
    def test_live_docs_have_zero_content_loss_rows(self):
        hits = {rel: rows for rel, rows in scan_root(REPO_ROOT).items() if not _is_frozen(rel)}
        assert hits == {}, f"活文档存在被 GFM 静默丢格的表格行：{hits}"

    def test_scan_surface_is_not_empty(self):
        """fail-closed：扫描面塌缩不得被当成「全绿」。"""
        live = live_markdown_paths()
        assert len(live) > 80, f"活文档仅 {len(live)} 份，扫描面异常"

    @pytest.mark.parametrize(("rel", "anchor", "cols"), FIXED_ROWS)
    def test_fixed_rows_author_exactly_the_header_width(self, rel: str, anchor: str, cols: int):
        lineno = _line_of(rel, anchor)
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        authored = {
            row_no: row_cols
            for _, header_cols, rows in tables_of(text)
            for row_no, row_cols in rows
            if header_cols == cols
        }
        assert authored.get(lineno) == cols, f"{rel}:{lineno}（{anchor}）应为 {cols} 格，实为 {authored.get(lineno)!r}"

    @pytest.mark.parametrize(("rel", "anchor", "cols"), FIXED_ROWS)
    def test_reverting_the_escape_reproduces_the_defect(self, rel: str, anchor: str, cols: int):
        r"""变异验证：把该行的 `\|` 还原成 `|`，判定器必须立刻报出该行丢格。

        「修好了但删掉修复也测不出来」不算锁。
        """
        lineno = _line_of(rel, anchor)
        lines = (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
        fixed = lines[lineno - 1]
        assert "\\|" in fixed, f"{rel}:{lineno} 已不含转义竖线，本例失去意义"
        mutated = "\n".join([*lines[: lineno - 1], fixed.replace("\\|", "|"), *lines[lineno:]])
        assert lineno in {row[0] for row in content_loss_rows(mutated)}, (
            f"{rel}:{lineno} 还原转义后仍未报丢格——判定器抓不到这一缺陷类"
        )


class TestFrozenScope:
    def test_registered_inventory_is_self_consistent(self):
        assert sum(FROZEN_LOSS_INVENTORY.values()) == REGISTERED_FROZEN_LOSS_ROWS

    def test_frozen_roots_are_exactly_registered(self):
        assert FROZEN_PREFIXES == ("docs/history/", "experiments/results/")
        assert UNTRACKED_PREFIXES[:2] == (".private/", ".workbuddy/")

    def test_frozen_loss_rows_stay_inside_the_registered_inventory(self):
        """逐文件对账：允许变好（某行被修），不允许变坏或冒出未登记的新文件。"""
        hits = {rel: len(rows) for rel, rows in scan_root(REPO_ROOT).items() if _is_frozen(rel)}
        overflow = {rel: n for rel, n in hits.items() if n > FROZEN_LOSS_INVENTORY.get(rel, 0)}
        assert overflow == {}, f"冻结面出现未登记的丢格行：{overflow}"

    def test_frozen_loss_rows_do_not_exceed_the_ratchet(self):
        hits = {rel: rows for rel, rows in scan_root(REPO_ROOT).items() if _is_frozen(rel)}
        found = sum(len(rows) for rows in hits.values())
        assert found <= REGISTERED_FROZEN_LOSS_ROWS, (
            f"冻结面丢格行数由 {REGISTERED_FROZEN_LOSS_ROWS} 升至 {found}：{hits}"
        )

    def test_exclusion_is_prefix_based_not_existence_based(self):
        """CI 上没有 `.private/`：判定必须按前缀，而不是「目录不存在所以没内容」。"""
        assert _is_scanned(".private/review/x.md") is False
        assert _is_scanned("docs/design/x.md") is True
        assert _is_frozen("docs/history/x.md") is True
        assert _is_frozen("docs/design/x.md") is False

    def test_new_loss_outside_frozen_paths_is_caught(self, tmp_path: Path):
        repo = tmp_path / "repo"
        (repo / "docs" / "design").mkdir(parents=True)
        broken = repo / "docs" / "design" / "new.md"
        broken.write_text("| a | b | c |\n|---|---|---|\n| 1 | `x | y` | 3 | 4 |\n", encoding="utf-8")
        assert content_loss_rows(broken.read_text(encoding="utf-8")) == [(3, 3, 5)]
        assert scan_root(repo) == {"docs/design/new.md": [(3, 3, 5)]}


class TestReferenceAgreement:
    def test_detector_matches_a_real_gfm_implementation(self):
        """与 markdown-it 逐行对照：它渲染时把行钳到表头宽度，被钳掉的格必须与判定器报出的同一批。

        依赖非声明包，缺席即 skip（精简环境口径与 `importorskip` 惯例一致）。
        """
        markdown_it = pytest.importorskip("markdown_it", reason="markdown-it 非本项目声明依赖，精简环境跳过")
        parser = markdown_it.MarkdownIt("commonmark").enable("table")
        disagree: list[str] = []
        for path in live_markdown_paths():
            text = path.read_text(encoding="utf-8", errors="replace")
            reference = _reference_loss(parser, text)
            mine = {line_no for line_no, _, _ in content_loss_rows(text)}
            if mine != reference:
                disagree.append(f"{_relpath(path, REPO_ROOT)}: mine={sorted(mine)} ref={sorted(reference)}")
        assert disagree == [], "判定器与 markdown-it 结论不一致：" + "; ".join(disagree)


def _reference_loss(parser, text: str) -> set[int]:
    """用真实解析器的 token 流定表头/行边界，只用 GFM 切格规则数源码格数。"""
    lines = text.splitlines()
    tokens = parser.parse(text)
    loss: set[int] = set()
    index = 0
    while index < len(tokens):
        if tokens[index].type != "thead_open":
            index += 1
            continue
        rows: list[tuple[int | None, int]] = []
        walker = index
        while walker < len(tokens) and tokens[walker].type != "tbody_close":
            if tokens[walker].type == "tr_open":
                start = tokens[walker].map[0] if tokens[walker].map else None
                cells = 0
                inner = walker + 1
                while tokens[inner].type != "tr_close":
                    if tokens[inner].type in ("th_open", "td_open"):
                        cells += 1
                    inner += 1
                rows.append((start, cells))
                walker = inner + 1
            else:
                walker += 1
        if rows:
            header_cols = rows[0][1]
            for start, _ in rows[1:]:
                if start is None:
                    continue
                if _cell_count(lines[start]) > header_cols:
                    loss.add(start + 1)
        index = walker
    return loss
