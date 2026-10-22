#!/usr/bin/env python3
"""BJ 轮围栏归因判据的独立复核（零依赖 `src/`，可在变异验证运行期间安全重跑）。

手册 `docs/reviews/ORACLE_VALIDATOR_MEASURABILITY_BJ_2026-10-22.md` §6 第 2 条登记的
读数（`strict_fenced=72 / loose_fenced=73 / loose_only=1 / syntax_strict=4`）由本脚本
产出。口径与 `bj_corpus_probe.py` 的语料面一致（递归
`experiments/results/**/*.json` 全树任一层出现的 `generated_test` 字符串），但**不
import 被测模块**：解析面直接用最标准库 `ast.parse` 复现 `parses_as_module` 的判定
（捕获 `SyntaxError` 与 `ValueError`），两种围栏归因判据并排计数，差额即"正文中间
出现过围栏标记但整块并非以围栏开头"的边界样本数。

零写入、零网络、零 LLM。
"""

from __future__ import annotations

import ast
import json
import warnings
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).resolve().parents[2] / "experiments" / "results"
_READ_ERRORS = (OSError, ValueError, RecursionError, UnicodeDecodeError)
#: `parses_as_module` 的判定面：孤立代理位抛的是 `UnicodeEncodeError`（`ValueError` 子类）
_PARSE_ERRORS = (SyntaxError, ValueError)
_FENCE = "```"


def _iter_generated_test(node: Any):
    """递归产出全树中任一层 `generated_test` 字符串值（与语料探针同口径）。"""
    if isinstance(node, dict):
        value = node.get("generated_test")
        if isinstance(value, str):
            yield value
        for sub in node.values():
            yield from _iter_generated_test(sub)
    elif isinstance(node, list):
        for sub in node:
            yield from _iter_generated_test(sub)


def _unparsable(text: str) -> bool:
    """标准库口径的"读不懂"：纯空白先按"没有可解析内容"排除，其余交给 `ast.parse`。"""
    if not text.strip():
        return False
    try:
        ast.parse(text)
    except _PARSE_ERRORS:
        return True
    return False


def main() -> int:
    warnings.filterwarnings("ignore", message=".*invalid escape sequence.*")

    sites = unparsable = strict = loose = loose_only = 0
    for path in sorted(RESULTS.rglob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except _READ_ERRORS:
            continue
        for generated_test in _iter_generated_test(data):
            sites += 1
            if not _unparsable(generated_test):
                continue
            unparsable += 1
            hits_strict = generated_test.lstrip().startswith(_FENCE)
            hits_loose = _FENCE in generated_test
            strict += hits_strict
            loose += hits_loose
            if hits_loose and not hits_strict:
                loose_only += 1

    print(f"sites={sites} unparsable={unparsable}")
    print(f"strict_fenced={strict} loose_fenced={loose} loose_only={loose_only}")
    print(f"syntax_strict={unparsable - strict} syntax_loose={unparsable - loose}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
