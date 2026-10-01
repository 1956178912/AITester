"""
4.4 改进：双语文档同步检查（.md 与 .md.en / .en.md 配对一致性守卫）。

背景：
    项目文档有中英文双版本（docs/api_reference.md + api_reference.en.md、
    docs/failure_analysis.md + failure_analysis.en.md、CHANGELOG.md +
    CHANGELOG.en.md、docs/algorithm_design.md + .en.md 等）。此前靠人肉
    同步——英文版的"最后更新"日期常落后中文版若干批次（如 2026-09-27
    批次更新了中文版但英文版仍停在 2026-09-25），CI 无守卫。

本脚本检查（默认 fail 0，供 CI / 手动运行）：
    1. 配对完整性：每个有 .md 的文档（非 .en 后缀）必须有对应的 .en 版本
       在目录内（允许 CHANGELOG/QUICKSTART 等根目录文件）；
    2. 更新日期同步：中英文版的"最后更新 / Last updated"日期行若都
       存在，必须一致（若英文版无该行 → 警告，不 fail）；
    3. 章节数粗对齐：中英文版的二级标题（## ）数量允许 ±2 的容差
       （英文版可省略内部实现章节），超出则警告。

用法：
    python3 scripts/check_bilingual_docs.py [--strict]
    # --strict：把"警告"升级为 fail（CI 门禁用）

退出码：0 = 全过（或仅警告且非 strict）；1 = 有 fail。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 需检查双语文档同步的目录/文件（项目实际有中英配对的文档位置）
_CHECK_DIRS = [
    "docs",  # docs/*.md ↔ docs/*.en.md
]
_CHECK_FILES = [
    "CHANGELOG.md",  # CHANGELOG.md ↔ CHANGELOG.en.md
]

# 豁免清单：非核心文档（审查报告/审计/历史实施记录等）不强制英文配对。
# 核心参考文档（api_reference / failure_analysis / algorithm_design /
# performance_guide / usage_examples / roadmap / CHANGELOG / QUICKSTART）
# 必须有英文版配对，否则 fail。
#
# 维护约定（2026-09-28）：本清单为"非核心文档"判定的一次性快照，随时间
# 推移清单中的文档可能已演变为被其他文档引用 / 被新贡献者依赖的核心参考。
# 建议每季度（或每次重大版本发布后）人工复核一次：对清单内每个文件确认
# "是否仍属于非核心（审查/审计/历史实施记录）"——若已升级为核心参考文档，
# 补齐英文版配对并从本清单移除；若确认已过期（对应轮次已过、无后续引用），
# 移入 docs/history/ 归档并从本清单删除（归档后本脚本不再扫描，无需保留
# 豁免条目）。
_EXEMPT_NO_EN = frozenset(
    {
        "docs/0.7_audit_findings.md",
        "docs/assessment_2026-09-25_improvement_directions.md",
        "docs/code_analysis_report.md",
        "docs/experiment_ab_results_2026-09-28.md",
        "docs/full_test_report_2026-09-28.md",
        "docs/gap_report_2026-09-28_frontier_recommendations.md",
        # 2026-10-01 登记：英文单语"可验证前沿基线"核查文档（2024–2026 工具/标准/
        # 合规调研，含 UNVERIFIED 标注），属参考资料非核心参考文档，与上述中文
        # 单语基线文档同口径豁免。
        "docs/frontier-baseline-2024-2026-python-ai-compliance.md",
        "docs/implementation_2026-09-25_improvement_directions.md",
        "docs/implementation_2026-09-25_p0_batch.md",
        "docs/implementation_2026-10_ab_negative_batch.md",
        "docs/implementation_2026-10_l25hard_n40_batch.md",
        "docs/log_redaction_audit.md",
        # 2026-10-02 审查修复：未登记豁免导致 check_bilingual_docs --strict
        # 恒 exit 1（该文档为中文单语"前沿基线核查清单"，属参考资料非
        # 核心参考文档，与 gap_report / implementation_* 同口径豁免；
        # 此前无豁免 → 失败项使 CI --strict || true 兜底永远生效，
        # 门禁形同虚设）。
        "docs/Python工程化前沿基线（2024–2026）.md",
        "docs/review_2026-09-26_round7.md",
        "docs/review_2026-09-26_round8.md",
        "docs/review_2026-09-27_round10.md",
        "docs/review_2026-09-27_round11.md",
        "docs/review_2026-09-27_round9.md",
        "docs/troubleshooting.md",
    }
)

# 日期行匹配（中英文）
_DATE_RE = re.compile(r"(最后更新|Last\s+updated)[:：]?\s*(\d{4}-\d{2}-\d{2})")

# 12. P2 结构化对照检查：二级标题（## / ##）序列归一化后按序对齐，
# 检测"英文版缺失某章节 / 章节顺序漂移"。二级标题归一化规则：
# 去首尾空白、去前置序号（"一、" "1." 等）、转小写，便于中英标题文本
# 差异下仍按序比对"章节骨架"（非字面翻译校验——翻译口径由人工保证）。
_H2_RE = re.compile(r"^##\s+(?!#)(\S.*)$")


def _extract_h2_titles(text: str) -> list[str]:
    """提取二级标题序列（归一化：去序号前缀 + 转小写 + 去空白）。

    用于结构化对照：中英文版的 H2 骨架（章节顺序）应一致；
    缺失 / 顺序漂移会导致 H2 序列不等（超出 ±2 容差即警告，strict 时 fail）。
    """
    titles: list[str] = []
    for line in text.splitlines():
        m = _H2_RE.match(line)
        if m:
            t = m.group(1).strip()
            # 去序号前缀："一、" "二、" ... "1." "2)" 等
            t = re.sub(r"^[一二三四五六七八九十]+、\s*", "", t)
            t = re.sub(r"^\d+[\.\)、]\s*", "", t)
            titles.append(t.lower())
    return titles


def _find_en_pair(md_path: Path) -> Path | None:
    """找中英配对的英文版路径（api_reference.md ↔ api_reference.en.md 或 .md.en）。"""
    stem = md_path.stem  # 去掉 .md
    for suffix in (".en.md", ".md.en"):
        cand = md_path.parent / (stem + suffix)
        if cand.exists():
            return cand
    # CHANGELOG.md 特例：CHANGELOG.en.md（stem=CHANGELOG）
    cand = md_path.parent / (stem + ".en.md")
    return cand if cand.exists() else None


def _extract_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    return m.group(2) if m else None


def _extract_sections(text: str) -> int:
    """二级标题（## ）数量（粗对齐口径）。"""
    return sum(1 for line in text.splitlines() if line.startswith("## "))


def check_bilingual(strict: bool = False) -> tuple[list[str], list[str]]:
    """检查所有中英配对文档。

    Returns:
        (failures, warnings)：
        - failures：缺英文版配对（必须补齐或明确标记豁免）；
        - warnings：日期不一致 / 章节数偏差（strict 时升级为 fail）。
    """
    failures: list[str] = []
    warnings: list[str] = []

    candidates: list[Path] = []
    for d in _CHECK_DIRS:
        dp = Path(d)
        if dp.is_dir():
            for f in sorted(dp.glob("*.md")):
                # 排除已经是英文版的（.en.md / .md.en）与 design 子目录
                if f.name.endswith(".en.md") or f.name.endswith(".md.en"):
                    continue
                if "en" in f.stem.lower() and f.stem.endswith("_en"):
                    continue
                candidates.append(f)
    for f in _CHECK_FILES:
        fp = Path(f)
        if fp.exists():
            candidates.append(fp)

    for md in candidates:
        text_zh = md.read_text(encoding="utf-8")
        en = _find_en_pair(md)
        rel = md.as_posix()
        if en is None:
            if rel in _EXEMPT_NO_EN:
                continue  # 非核心文档豁免，不要求英文配对
            failures.append(f"缺英文版配对：{rel}（需 {md.stem}.en.md 或加入 _EXEMPT_NO_EN）")
            continue
        text_en = en.read_text(encoding="utf-8")
        date_zh = _extract_date(text_zh)
        date_en = _extract_date(text_en)
        if date_zh and date_en and date_zh != date_en:
            msg = f"日期不一致：{rel}={date_zh} vs {en.as_posix()}={date_en}"
            if strict:
                failures.append(msg)
            else:
                warnings.append(msg)
        elif date_en is None:
            warnings.append(f"英文版无更新日期行（无法核对）：{en.as_posix()}")

        sec_zh = _extract_sections(text_zh)
        sec_en = _extract_sections(text_en)
        if abs(sec_zh - sec_en) > 2:
            msg = f"章节数偏差过大：{rel}({sec_zh}) vs {en.as_posix()}({sec_en})"
            if strict:
                failures.append(msg)
            else:
                warnings.append(msg)

        # 12. P2 结构化对照：H2 骨架（章节顺序）按序对齐。
        # 英文 H2 数量少于中文且骨架前缀不一致（缺章节 / 顺序漂移）时警告；
        # 数量差 > 2 已被上面的章节数检查覆盖，这里补"顺序漂移"检测。
        h2_zh = _extract_h2_titles(text_zh)
        h2_en = _extract_h2_titles(text_en)
        # 比较"中文 H2 序列中出现在英文序列里的相对顺序"是否保持（子序列匹配）
        if h2_zh and h2_en:
            shorter = min(len(h2_zh), len(h2_en))
            zh_win = h2_zh[:shorter]
            en_win = h2_en[:shorter]
            # 宽松判定：英文序列中连续两节的相对顺序若与中文冲突（中文 A 在 B 前，
            # 英文 B 在 A 前）→ 顺序漂移。仅当两侧窗口均含该对时判定。
            drift = False
            # 英文窗口去重保留首现顺序
            seen_en: list[str] = []
            for title in en_win:
                if title not in seen_en:
                    seen_en.append(title)
            # 中文窗口去重保留首现顺序
            zh_dedup: list[str] = []
            for t in zh_win:
                if t not in zh_dedup:
                    zh_dedup.append(t)
            # 对每对相邻中文节，检查英文中是否出现逆序
            for i in range(len(zh_dedup) - 1):
                a, b = zh_dedup[i], zh_dedup[i + 1]
                if a in seen_en and b in seen_en and seen_en.index(b) < seen_en.index(a):
                    drift = True
                    break
            if drift:
                msg = f"章节顺序漂移：{rel} vs {en.as_posix()}（H2 骨架逆序）"
                if strict:
                    failures.append(msg)
                else:
                    warnings.append(msg)

    return failures, warnings


def main() -> int:
    strict = "--strict" in sys.argv
    failures, warnings = check_bilingual(strict=strict)

    for w in warnings:
        print(f"  [warn] {w}")
    for f in failures:
        print(f"  [FAIL] {f}")

    total = len(failures) + len(warnings)
    if total == 0:
        print("双语文档同步检查通过（0 警告 / 0 失败）")
        return 0
    if strict:
        print(f"双语文档同步检查失败（{len(failures)} 失败 / {len(warnings)} 警告，strict 模式）")
        return 1
    print(f"双语文档同步检查完成（{len(failures)} 失败 / {len(warnings)} 警告）")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
