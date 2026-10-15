#!/usr/bin/env python3
"""JSON 契约调用点计数一致性门禁（EMSE 批次 2026-10-15，ADR-0031 配套）。

背景（审稿人可判性）：
    项目对外文档长期以"JSON 契约调用点"数量描述结构化输出加固的作用面，
    但同一事实曾在中英文文档中分裂为 6 与 7（实测：`README.md` 一处 6、
    一处 7；`MODEL_CARD.md` 一处 6、一处 7；英文同型）。审稿人看到同篇
    稿件自相矛盾，会直接质疑"作者是否清点过自己的调用面"。

本门禁把该事实机器化：
    1. **权威计数**：`src/**/*.py` 中显式 `json_mode=True` 的**实参**调用点
       （排除注释行与函数签名/文档字符串），必须等于 `EXPECTED_SITES`；
    2. **文档一致性**：白名单文档中的 "N 处/个"、"N JSON-contract call
       sites"、"seven/six/七/六" 等表述必须与权威计数一致；
    3. **口径 B 提示**（不 fail）：提示文本声明 JSON 契约但未开 json_mode
       的调用点数由 `--report` 打印，供论文附录声明所采用的口径。

口径定义（论文必须择一并声明）：
    - 口径 A（本门禁权威值）：`json_mode=True` / `response_format=json_object`
      绑定调用点；
    - 口径 B：提示文本声明 JSON 契约的调用点（含未开 json_mode 者），数量更大。

用法：
    python3 scripts/gates/check_json_contract_sites.py            # 门禁（CI）
    python3 scripts/gates/check_json_contract_sites.py --report   # 附加口径 B 明细

退出码：0 = 一致；1 = 计数漂移或文档不一致。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# 权威值：口径 A 调用点数量。**改动 src/ 调用面时必须同步更新此常量与文档**
# ——这正是门禁的目的（防文档静默漂移）。
EXPECTED_SITES = 7

# 白名单：对外文档（历史归档报告/审查记录不扫，避免"不得改写历史"冲突）
_DOC_FILES = [
    "README.md",
    "README.en.md",
    "MODEL_CARD.md",
    "MODEL_CARD.en.md",
    "docs/adr/0031-llm-structured-output-hardening.md",
]

_NUM_WORDS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

# 匹配 "七处/6 处/seven JSON-contract call sites/7 JSON契约调用点" 等表述
_CLAIM_PATTERNS = [
    re.compile(r"([0-9]+|\w+)\s*(?:处|个)\s*JSON"),
    re.compile(r"([0-9]+|\w+)\s*JSON[\s-]*(?:contract|契约)"),
]


def count_authoritative_sites() -> tuple[int, list[str]]:
    """口径 A：src/ 下显式 json_mode=True 的**调用实参**（AST 精确，排除注释/文档串）。"""
    import ast

    hits: list[str] = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            hits.extend(
                f"{rel}:{kw.value.lineno}"
                for kw in node.keywords
                if kw.arg == "json_mode" and isinstance(kw.value, ast.Constant) and kw.value.value is True
            )
    return len(hits), sorted(hits)


def count_prompt_declared_sites() -> tuple[int, list[str]]:
    """口径 B：提示文本声明 JSON 契约的调用点（含未开 json_mode 者）。

    判据保守：同一文件内出现"请输出 JSON"/"JSON 数组"/"JSON 对象"/JSON schema
    字样的调用点难以静态精确归属，故本函数只统计**未开 json_mode 但调用 LLM**
    的候选文件，供人工核定——门禁不据此 fail。
    """
    candidates: list[str] = []
    for path in sorted((REPO_ROOT / "src").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if "_call_llm_with_cache(" not in text:
            continue
        for lineno, raw in enumerate(text.splitlines(), start=1):
            if "_call_llm_with_cache(" in raw and "json_mode=True" not in raw and not raw.strip().startswith("#"):
                candidates.append(f"{path.relative_to(REPO_ROOT)}:{lineno}")
    return len(candidates), candidates


def scan_doc_claims() -> list[tuple[str, int, str]]:
    """返回 [(文件, 行号, 原文行)]，仅含有"数量 + JSON"表述的行。"""
    found: list[tuple[str, int, str]] = []
    for rel in _DOC_FILES:
        path = REPO_ROOT / rel
        if not path.is_file():
            continue
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pat in _CLAIM_PATTERNS:
                for m in pat.finditer(raw):
                    token = m.group(1)
                    if token.isdigit() or token in _NUM_WORDS:
                        # 保留**完整行**用于解析（截断会切掉待解析的数量词，
                        # 曾致 MODEL_CARD.en.md:3 误报 None）；显示时再截断。
                        found.append((rel, lineno, raw.strip()))
                        break
                else:
                    continue
                break
    return found


def _parse_claim(line: str) -> int | None:
    """从一行文本解析"数量 + JSON 契约调用点"表述，兼容中英文与词序。

    支持："七处 JSON 契约调用点" / "7 处 JSON" / "seven JSON-contract call
    sites" / "JSON-contract call sites: 7" / "JSON 契约调用点 7 处"。
    取**邻近 JSON 字样**的数量词，避免误取同行的其它数字。
    """
    anchors = [m.start() for m in re.finditer(r"JSON", line, re.IGNORECASE)]
    if not anchors:
        return None
    best: tuple[int, int] | None = None  # (distance, value)
    for m in re.finditer(r"([0-9]+|[A-Za-z]+|[\u4e00-\u9fff])", line):
        token = m.group(1)
        if token.isdigit():
            value = int(token)
        elif token.lower() in _NUM_WORDS:
            value = _NUM_WORDS[token.lower()]
        elif token in _NUM_WORDS:
            value = _NUM_WORDS[token]
        else:
            continue
        dist = min(abs(m.start() - a) for a in anchors)
        if dist <= 40 and (best is None or dist < best[0]):
            best = (dist, value)
    return None if best is None else best[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report", action="store_true", help="附加打印口径 B 候选明细")
    args = ap.parse_args(argv)

    failures: list[str] = []
    count, hits = count_authoritative_sites()
    print(f"口径 A（json_mode=True 实参调用点）：{count} 处（期望 {EXPECTED_SITES}）")
    for h in hits:
        print(f"  - {h}")
    if count != EXPECTED_SITES:
        failures.append(
            f"权威计数漂移：实测 {count} 处 ≠ 期望 {EXPECTED_SITES} 处"
            "（若确为有意变更，请同步更新本脚本 EXPECTED_SITES 与全部对外文档）"
        )

    claims = scan_doc_claims()
    print(f"\n文档数量表述：{len(claims)} 处")
    for rel, lineno, line in claims:
        claimed = _parse_claim(line)
        status = "OK" if claimed == EXPECTED_SITES else "MISMATCH"
        if status == "MISMATCH":
            failures.append(f"{rel}:{lineno} 表述为 {claimed}，与权威值 {EXPECTED_SITES} 不一致")
        print(f"  [{status}] {rel}:{lineno} -> {claimed}")

    if args.report:
        n_b, cand = count_prompt_declared_sites()
        print(f"\n口径 B（未开 json_mode 但调用 LLM 的候选调用点）：{n_b} 处（需人工核定哪些声明 JSON 契约）")
        for c in cand:
            print(f"  - {c}")

    if failures:
        print("\n门禁失败：")
        for f in failures:
            print(f"  ✗ {f}")
        return 1
    print("\nJSON 契约调用点计数一致性检查通过（口径 A）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
