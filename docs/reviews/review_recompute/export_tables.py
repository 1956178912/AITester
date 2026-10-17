#!/usr/bin/env python3
"""从评审报告 Markdown 抽取表格为 CSV（防纯文本表格错位；保留唯一事实源）。

用法（仓库根）：
    .venv/bin/python3 docs/reviews/review_recompute/export_tables.py

输出：docs/reviews/review_recompute/*.csv，与报告正文表格逐格一致
（同一数据源=报告本身；若正文改动需重跑本脚本）。
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPORT = HERE.parent / "INDEPENDENT_SYSTEMATIC_REVIEW_2026-10-17.md"

# (输出 CSV 名, 表头匹配特征, 该表前的锚点标题)
TABLES = [
    ("audit_claims_C1_C20.csv", "编号 | 所在文件/位置", "### 3.1 性能声明复核表"),
    ("frontier_test_generation.csv", "前沿方法/系统 | 关键指标", "### 4.1 测试生成子方向"),
    ("frontier_apr.csv", "前沿方法 | 关键指标", "### 4.3 多智能体协作与程序修复子方向"),
    ("comparison_matrix.csv", "维度 | 2025-2026 前沿 SOTA", "## 5. 项目与前沿量化对比矩阵"),
    ("recommendations.csv", "编号 | 对应文件/位置", "## 10. 改进/优化/新增建议表"),
]


def parse_row(line: str) -> list[str]:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return cells


def main() -> None:
    lines = REPORT.read_text(encoding="utf-8").splitlines()
    # 定位每个锚点后的第一个表格
    for csv_name, header_sig, anchor in TABLES:
        start = None
        for i, ln in enumerate(lines):
            if ln.startswith("## ") or ln.startswith("### "):
                if anchor.split()[-1] in ln and anchor[:6] in ln:
                    start = i
                    break
        if start is None:
            print(f"WARN: anchor not found: {anchor}")
            continue
        # 向后找表头行
        j = start
        while j < len(lines) and header_sig.split("|")[0].strip() not in lines[j]:
            j += 1
        if j >= len(lines):
            print(f"WARN: header not found for {csv_name}")
            continue
        rows: list[list[str]] = []
        k = j
        while k < len(lines) and lines[k].strip().startswith("|"):
            if not re.fullmatch(r"\s*\|\s*[-: ]+\|\s*", lines[k]):
                rows.append(parse_row(lines[k]))
            k += 1
        out = HERE / csv_name
        with out.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerows(rows)
        print(f"OK: {csv_name} ({len(rows)-1} data rows)")


if __name__ == "__main__":
    main()
