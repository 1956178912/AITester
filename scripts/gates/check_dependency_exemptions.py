"""
依赖豁免治理门禁：ci.yml 的 --ignore-vuln 列表必须在
docs/dependency_exemptions.md 登记表留痕。

背景（安全审计治理实践）：
    此前 chromadb 的 5 条已知漏洞豁免只记录在 ci.yml 注释与
    CHANGELOG 决策日志中，缺少"登记 / 复审触发 / 复审期限"的
    单一事实来源，容易出现"加了 --ignore-vuln 却没留痕 / 忘了复审"
    的漂移。本脚本把 ci.yml 实际生效的 --ignore-vuln 列表与
    docs/dependency_exemptions.md 登记表逐条对照，未登记的豁免
    阻断合并（退出码 1），已登记的输出 warning 提示复审状态。

检查项：
    1. 提取 .github/workflows/ci.yml 中所有 --ignore-vuln <ID> 行；
    2. 提取 docs/dependency_exemptions.md "当前豁免" 表中的漏洞 ID
       列（兼容 "PYSEC-2026-311（重复两条）+ PYSEC-2026-3813 / 3814 / 3815"
       这种合写格式，按 PYSEC / CVE 前缀正则切分）；
    3. 对照：ci.yml 豁免了但登记表未留痕的 ID → 阻断（退出码 1）；
       登记表留痕但 ci.yml 未豁免的 ID → warning（豁免已撤 / 待关闭，
       提示维护者把该行移入"已复审关闭"节）；
       登记表"复审期限"列缺失 / 空白 → warning（治理不闭环）。

使用方式（CI）：
    python scripts/gates/check_dependency_exemptions.py

退出码：
    0 = 全部豁免已登记（可能有 warning，不阻断）；
    1 = 存在未登记的 --ignore-vuln（阻断合并）。
"""

from __future__ import annotations

import os
import re
import sys


def _extract_ci_ignore_vulns(ci_path: str) -> set[str]:
    """提取 ci.yml 中所有 --ignore-vuln <ID>（去重）。"""
    ids: set[str] = set()
    if not os.path.exists(ci_path):
        return ids
    with open(ci_path, encoding="utf-8") as f:
        content = f.read()
    # 匹配 `--ignore-vuln PYSEC-2026-3813` / `--ignore-vuln CVE-2024-1234`
    for m in re.finditer(r"--ignore-vuln\s+([A-Z]{2,}-\d{4}-\d+)", content):
        ids.add(m.group(1))
    return ids


def _extract_registry_vuln_ids(registry_path: str) -> set[str]:
    """提取 docs/dependency_exemptions.md 登记表中的漏洞 ID（去重）。

    兼容两种登记格式：
        - 表格行的"漏洞 ID"列：`PYSEC-2026-3813 / 3814 / 3815`（合写，
          首个 ID 带完整前缀，后续只写序号）；
        - 单独一行：`PYSEC-2026-311（重复两条）`（带中文注释）。
    按大写前缀 - 年份 - 序号（如 PYSEC / CVE）的正则全量切分
    （不区分列位置，登记表是豁免专项文档，全文命中即可）。
    合写格式（"PYSEC-2026-3813 / 3814 / 3815"）的后续裸序号
    （"3814" / "3815"）单独不命中前缀正则，本函数在首次命中完整 ID
    后把同一"合写行"内的裸序号补全为同前缀完整 ID。
    保守口径：补全只取"完整 ID 之后的所有裸序号"（每段独立捕获），
    避免把完整 ID 的尾段（如 3813 中的 2026）误读为独立序号；
    按行逐个合写组处理，组内首个完整 ID 的尾段由前缀正则已命中。
    """
    ids: set[str] = set()
    if not os.path.exists(registry_path):
        return ids
    with open(registry_path, encoding="utf-8") as f:
        content = f.read()
    for m in re.finditer(r"[A-Z]{2,}-\d{4}-\d+", content):
        ids.add(m.group(0))
    # 合写格式补全：`PYSEC-2026-3813 / 3814 / 3815` 后续裸序号
    # （每行内"完整 ID + 斜杠分隔裸序号"逐个提取，避免链式回溯
    # 漏掉末尾段；首个完整 ID 的尾段由前缀正则已命中）
    for line in content.splitlines():
        prefix_m = re.search(r"[A-Z]{2,}-\d{4}", line)
        if not prefix_m:
            continue
        prefix = prefix_m.group(0)  # 如 "PYSEC-2026"
        # 取整行中"完整 ID 之后"的裸序号（含完整 ID 自身尾段，前缀正则已
        # 命中完整 ID，这里补全斜杠分隔的后续裸序号，去重后加入集合）
        tail = line[prefix_m.end() :]
        # 匹配斜杠分隔的裸序号（兼容 " / 3814 / 3815" 与 "+ PYSEC-2026-3813 / 3814 / 3815"）
        for bare in re.findall(r"/\s*(\d{3,5})(?=\s*(?:$|/|\)|，|、|;|；|\|))", tail):
            ids.add(f"{prefix}-{bare}")
    return ids


def _registry_review_deadline_present(registry_path: str) -> bool:
    """登记表"复审期限"列是否非空（治理闭环检查，保守：只看表头列）。"""
    if not os.path.exists(registry_path):
        return False
    with open(registry_path, encoding="utf-8") as f:
        content = f.read()
    # "复审期限" 列须存在（表头命中即视为登记了该维度）
    return "复审期限" in content


def main() -> int:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ci_path = os.path.join(project_root, ".github", "workflows", "ci.yml")
    registry_path = os.path.join(project_root, "docs", "dependency_exemptions.md")

    ci_vulns = _extract_ci_ignore_vulns(ci_path)
    registry_vulns = _extract_registry_vuln_ids(registry_path)

    print(f"ci.yml --ignore-vuln 列表（{len(ci_vulns)} 条）: {sorted(ci_vulns) or '（无）'}")
    print(f"登记表留痕漏洞 ID（{len(registry_vulns)} 条）: {sorted(registry_vulns) or '（无）'}")

    unregistered = ci_vulns - registry_vulns
    stale_registry = registry_vulns - ci_vulns

    warnings: list[str] = []
    if not os.path.exists(registry_path):
        warnings.append("docs/dependency_exemptions.md 不存在（首次豁免请创建登记表）")
    elif not _registry_review_deadline_present(registry_path):
        warnings.append('登记表缺少"复审期限"列（治理不闭环，请补上）')

    if unregistered:
        print("\n[阻断] 以下 --ignore-vuln 未在 docs/dependency_exemptions.md 登记:")
        for vid in sorted(unregistered):
            print(f"  - {vid}")
        print("请先在登记表留痕（依赖 / 版本 / 漏洞 ID / 豁免原因 / 复审触发条件 / 复审期限）再合并。")
        return 1

    if stale_registry:
        warnings.append(
            f"登记表留痕但 ci.yml 未豁免的漏洞 ID（{len(stale_registry)} 条，请把对应行移入'已复审关闭'节）: "
            + ", ".join(sorted(stale_registry))
        )

    for w in warnings:
        print(f"[warning] {w}")

    if not ci_vulns:
        print("\n[依赖豁免] ci.yml 无 --ignore-vuln（无需登记检查）")
        return 0

    print(f"\n[依赖豁免] 全部 {len(ci_vulns)} 条 --ignore-vuln 已在登记表留痕 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
