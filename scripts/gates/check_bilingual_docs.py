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
    3. 章节骨架对照：用语言无关的骨架指纹比对中英版 H2 结构——
       ① 两侧 H2 编号序列（"一、" / "1." 折算为整数）必须逐位相等
       （缺章节 / 顺序漂移即命中，即使 H2 总数差在 ±2 容差内）；
       ② 两侧 H2 数相等时，逐节 H3 小节数向量必须相等。
       H2 总数仍允许 ±2 容差（英文版可省略内部实现章节；被省略的
       若是编号章节，①会命中）。骨架漂移或超出容差 → 警告，strict
       时 fail。

用法：
    python3 scripts/gates/check_bilingual_docs.py [--strict]
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
# Z5（2026-10-06 审查修复）：门禁扩围到根目录核心文档配对——此前只扫
# docs/ 与 CHANGELOG，根目录 README / QUICKSTART / CONTRIBUTING /
# MODEL_CARD / SECURITY 的 .en 配对不在守卫范围（实测 CONTRIBUTING.en.md
# 曾落后中文版 8 天而 CI 无感知）。根目录其余单语文件（5 份
# *_BASELINE_2023-2026.md 前沿调研笔记、config.local.example 等）为研究
# 参考材料，不强制英文配对（与 _EXEMPT_NO_EN 同口径，不列入即不扫）。
_CHECK_FILES = [
    "CHANGELOG.md",  # CHANGELOG.md ↔ CHANGELOG.en.md
    "README.md",
    "QUICKSTART.md",
    "CONTRIBUTING.md",
    "MODEL_CARD.md",
    "SECURITY.md",
    "REPLICATION.md",  # DD 轮（2026-10-26）：补齐英文配对后纳入守卫
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
        # 2026-10-10 目录治理批次：按上方既有维护约定（"移入 docs/history/
        # 归档并从本清单删除"）清理 10 条**指向不存在路径**的死条目。
        # 这 10 个文件在 HEAD 即已不在 docs/ 顶层（早已归档至 docs/history/），
        # 而本门禁以 dp.glob("*.md") **非递归**扫描 docs/，docs/history/ 不在
        # 扫描面 → 这些条目永不可能被命中，属纯死代码；死条目会让"豁免清单 =
        # 真实现状"的假设失真，后续维护者据以判断时会得出错误结论。
        # 已移除（其中 8 项现位于 docs/history/）：
        #   0.7_audit_findings / assessment_2026-09-25_improvement_directions /
        #   code_analysis_report / experiment_ab_results_2026-09-28 /
        #   implementation_2026-09-25_improvement_directions /
        #   implementation_2026-09-25_p0_batch /
        #   implementation_2026-10_ab_negative_batch / log_redaction_audit
        # 2026-10-10 文档清理批次：另 2 项按上方维护约定判据（"对应轮次已过 +
        # 无后续引用"）**确认删除**（实测全仓 0 引用，含 docs/history/ 内索引
        # 与实验报告；内容留存于删除前提交历史）：
        #   full_test_report_2026-09-28 / implementation_2026-10_l25hard_n40_batch
        # DD 轮（2026-10-26）：troubleshooting 补齐英文配对，移出豁免。
        # 2026-10-15 EMSE 批次新增 2 条：审计 / 协议记录类单语文档，无英文配对
        # （按上方维护约定：非核心文档不强制英文配对）。
        #   MEASUREMENT_INTEGRITY.md       = 四起测量伪影"口径分叉"方法论章
        #                                    （逐起给出分叉口径 / 检测方式 / 量级 /
        #                                    修复 / 可重放证据 / 结论是否翻转）
        #   HUMAN_ADJUDICATION_PROTOCOL.md = E7 人工裁决操作协议（抽样框 / 五选一
        #                                    量表 / 双人独立 / 冲突解决 / Cohen's
        #                                    kappa；E7 尚未执行、无 Kappa 工件）
        # 三者均为"过程与口径记录"而非对外参考文档，故不补英文版；若未来升级为
        # 被论文正文直接引用的核心参考，按维护约定补英文配对并移出本清单。
        "docs/MEASUREMENT_INTEGRITY.md",
        "docs/HUMAN_ADJUDICATION_PROTOCOL.md",
        #   EVALUATION_SCOPE.md = 声明→证据→范围对账表（EMSE 编辑初筛用；
        #   含 contradicted 声明清单，属内部可判性工件）
        "docs/EVALUATION_SCOPE.md",
        #   COVERAGE_RATCHET_DEVIATION.md = 覆盖率棘轮偏差登记
        #   （实测 vs 水位、归因核验、三条处置路径；属过程记录）
        "docs/COVERAGE_RATCHET_DEVIATION.md",
        #   PROJECT_STATUS_REGISTER.md = 项目状态与决策登记册
        #   （已完成/遗留/阻断三类状态 + 每项验证入口 + 口径纪律；
        #    属内部交接与自查工件，随 BASELINE 同步刷新）
        "docs/PROJECT_STATUS_REGISTER.md",
        #   preregistration_c8_bugsinpy_draft_20261029.md = C8 外部效度小样
        #   预注册（冻结版；内部过程与口径记录，判据/协议/成本上限均在案；
        #   属"过程记录"非对外参考文档——与上方 EMSE 批次同口径）
        "docs/preregistration_c8_bugsinpy_draft_20261029.md",
    }
)

# 日期行匹配（中英文）
_DATE_RE = re.compile(r"(最后更新|Last\s+updated)[:：]?\s*(\d{4}-\d{2}-\d{2})")

# 12. P2 结构化对照检查：H2 骨架按序对齐。翻译文档的标题文本天然不同，
# 因此骨架指纹只取语言无关量：H2 编号（"一、" / "1." 折算为整数）与
# 每个 H2 下的 H3 小节数。历史实现比对标题字面量——实测 20 对配对中仅
# CHANGELOG 有 2 个跨语言相同标题，其余 19 对永不触发（ES 轮修复）。
_H2_RE = re.compile(r"^##\s+(?!#)(\S.*)$")
_H3_RE = re.compile(r"^###\s+(?!#)(\S.*)$")
_H2_ORDINAL_AR_RE = re.compile(r"^(\d+)[\.\)、]\s*")
_H2_ORDINAL_CN_RE = re.compile(r"^([一二三四五六七八九十]+)、\s*")
_CN_DIGITS = "一二三四五六七八九"


def _cn_numeral_to_int(text: str) -> int | None:
    """中文序号（一 / 十 / 十一 / 二十三…）折算为整数；非法形态返回 None。"""
    if not text:
        return None
    if "十" in text:
        head, _, tail = text.partition("十")
        tens = 1 if not head else _CN_DIGITS.find(head) + 1
        ones = 0 if not tail else _CN_DIGITS.find(tail) + 1
        if tens <= 0 or (tail and ones <= 0):
            return None
        return tens * 10 + ones
    if len(text) == 1:
        value = _CN_DIGITS.find(text) + 1
        return value or None
    return None


def _h2_ordinal(title: str) -> int | None:
    """H2 标题前置序号（"1." / "1)" / "一、"）折算为整数；无序号返回 None。"""
    m = _H2_ORDINAL_AR_RE.match(title)
    if m:
        return int(m.group(1))
    m = _H2_ORDINAL_CN_RE.match(title)
    if m:
        return _cn_numeral_to_int(m.group(1))
    return None


def _extract_h2_skeleton(text: str) -> list[tuple[int | None, int]]:
    """提取 H2 骨架：[(序号, 该节下 H3 小节数), ...]（语言无关，不读标题文本）。"""
    skeleton: list[tuple[int | None, int]] = []
    for line in text.splitlines():
        m = _H2_RE.match(line)
        if m:
            skeleton.append((_h2_ordinal(m.group(1).strip()), 0))
            continue
        if skeleton and _H3_RE.match(line):
            ordinal, subsections = skeleton[-1]
            skeleton[-1] = (ordinal, subsections + 1)
    return skeleton


def _h2_structure_drift(zh: list[tuple[int | None, int]], en: list[tuple[int | None, int]]) -> str | None:
    """返回中英 H2 骨架的漂移描述；一致返回 None。

    判据（ES 轮，2026-10-27）：
    1. 编号序列：两侧任一侧存在 H2 序号时，折算后的整数序列必须逐位
       相等——覆盖"缺章节 / 顺序漂移"，即使 H2 总数差在 ±2 容差内；
    2. 小节骨架：H2 数相等时，逐节 H3 小节数向量必须相等——覆盖无编号
       文档的章节内容漂移。
    """
    ordinals_zh = [ordinal for ordinal, _ in zh if ordinal is not None]
    ordinals_en = [ordinal for ordinal, _ in en if ordinal is not None]
    if (ordinals_zh or ordinals_en) and ordinals_zh != ordinals_en:
        return f"章节编号序列不等（中文 {ordinals_zh} vs 英文 {ordinals_en}：缺章节或顺序漂移）"
    if len(zh) == len(en) and zh:
        subsections_zh = [subsections for _, subsections in zh]
        subsections_en = [subsections for _, subsections in en]
        if subsections_zh != subsections_en:
            return f"每节 H3 小节数不等（中文 {subsections_zh} vs 英文 {subsections_en}）"
    return None


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

        # 12. P2 结构化对照：语言无关的 H2 骨架指纹（编号序列 + 每节 H3 数）。
        # 数量差 > 2 已被上面的章节数检查覆盖；这里补"缺章节 / 顺序漂移 /
        # 小节骨架漂移"，且对翻译标题同样生效（旧实现比对标题字面量）。
        drift = _h2_structure_drift(_extract_h2_skeleton(text_zh), _extract_h2_skeleton(text_en))
        if drift is not None:
            msg = f"章节骨架漂移：{rel} vs {en.as_posix()}（{drift}）"
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
