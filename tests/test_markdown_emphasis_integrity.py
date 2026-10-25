#!/usr/bin/env python3
"""文档里「孤立的 ***」必须转义（CR 轮，2026-10-25，零 LLM）。

## 背景

CHANGELOG 用 `***` 表示 p < 0.001 的显著性星号。Markdown 把 `***` 解析成
粗斜体标记，而且它**会吞掉后面最近的 `**` 当作闭合标记** ⇒ 从该处起，直到下一个
真正配对的 `**`，整段都被渲染成错乱的强调。本轮实测存量：`CHANGELOG.md` /
`CHANGELOG.en.md` 各 2 处、`docs/MEASUREMENT_INTEGRITY.md` 2 处、
`docs/study/RQ1_PAIRING_REPORT_2026-10-25.md` 2 处（表格里）与 1 处在行内代码中。

## 判据（精确、无误报）

判「孤立显著性星号」而不是「奇偶」：

- 先**剥离行内代码**（`` `***` `` 里的星号不参与强调解析，无需转义）；
- 再找 `***` 出现处**前后都不是星号、且前一个字符不是字母**的位置——
  嵌套强调的合法收尾（`*斜体*` + `**`）会紧跟字母，不会命中；
- 命中即须写成 `\\*\\*\\*`（渲染出来仍是 `***`）。

**为什么不用「奇偶」判据**：合法的嵌套强调（`**外层 *内层* 收尾**`）会让朴素的
`text.count("**")` 变成奇数——本轮实测 CHANGELOG 全文 `**` 计数为奇，其中两处
段落是**误报**（zh 段#1310 / en 段#862）。奇偶判据只能当粗筛，不能当判据。

## 冻结面

`docs/history/`（历史快照，不可回写）、`experiments/results/`（批次工件）、
`.private/` / `.workbuddy/`（机器本地目录，不在 git 里）一律不扫——否则结论会随
目录存在与否漂移。
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 孤立显著性星号：前后非星号，且前一个字符不是字母（排除嵌套强调收尾）。
_ISOLATED_TRIPLE = re.compile(r"(?<![\w*])\*\*\*(?![*\w])")
#: 行内代码（其中的星号不参与强调解析）。
_INLINE_CODE = re.compile(r"`[^`]*`")
#: 不扫描的目录片段。
_SKIP_PARTS = frozenset({".git", ".workbuddy", ".private", "node_modules", ".venv", "history"})


def _active_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in PROJECT_ROOT.rglob("*.md"):
        parts = set(path.parts)
        if parts & _SKIP_PARTS:
            continue
        if "experiments" in parts or "paper" in parts:
            continue
        files.append(path)
    return sorted(files)


def test_scanner_finds_the_repository_files() -> None:
    """解析面塌了要当场红——否则下面的判据会在空集上「零用例通过」。"""
    files = _active_markdown_files()
    assert len(files) >= 20, f"只扫到 {len(files)} 个 markdown 文件，扫描面异常"
    names = {path.name for path in files}
    assert "README.md" in names and "CHANGELOG.md" in names, names


def test_no_isolated_triple_asterisk_in_active_markdown() -> None:
    """孤立 `***` 会被 Markdown 当成粗斜体并吞掉后续 `**` ⇒ 必须转义。"""
    offenders: list[str] = []
    for path in _active_markdown_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        stripped = _INLINE_CODE.sub("", text)
        count = len(_ISOLATED_TRIPLE.findall(stripped))
        if count:
            offenders.append(f"{path.relative_to(PROJECT_ROOT)}: {count} 处")
    assert not offenders, (
        "这些文件里有未转义的孤立 `***`（会被 Markdown 解析成粗斜体，"
        "并吞掉后续的 `**` 作闭合标记）：" + "; ".join(offenders)
    )


def test_legitimate_nested_emphasis_is_not_flagged() -> None:
    """合法嵌套强调（`**外层 *内层* 收尾**`）不得被误判。"""
    sample = "**the loss comes from *removing it*, not from *adding one***; (3) ok"
    assert not _ISOLATED_TRIPLE.findall(_INLINE_CODE.sub("", sample)), sample
    assert not _ISOLATED_TRIPLE.findall(_INLINE_CODE.sub("", "`***` p < 0.001")), "行内代码不算"
    assert _ISOLATED_TRIPLE.findall(_INLINE_CODE.sub("", 'shown as "0.0000 (***)"')), "显著性星号应命中"
