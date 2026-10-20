#!/usr/bin/env python3
"""Z 轮第三方全量静态审查（2026-10-19）文档/协议修复锁定测试。

对应报告 F08 / F15 / F16 / F17 / F18 / F20 的 **docs/ 文档侧**修复。纯静态只读：
不依赖实验工件、不调用 LLM、不联网。断言口径 = "错误句不存在 + 修正句存在"，
防止后续轮次把已收缩的主张/口径回填：

- F08：synthetic 低基线不得再被定因为"基线天花板/无 flip 空间/信息性真阴性"，
  保留预注册敏感性事实（+8pp≈24.5、+12pp≈31、实测 3）。
- F15：``red_not_repaired`` 只是协议层机制状态，不构成有效检出充分条件；
  有效检出始终由评估层独立 F2P 三段判据裁决（88 行过红 = detection=0 反例）。
- F16：算法设计文档标题/首句按 ADR-0016 重定位（检出优先协议；编排=可消融容器）。
- F17：VALIDITY 中 ASE 2025（ADR-0025）的"未一手核验"过期状态已传播为
  "2026-10-16 一手核验"，同时保留 Java→Python 外推限制；claude-code 聚合数字
  仍单独标注未一手核验。
- F18：DATA_CARD 区分"历史主批（n=50/seed42）"与"当前确认性主批（87×3
  seeds×3 臂 = 261 行/臂，--max-pattern-repeat 2）"。
- F20：T-10 匹配子集写全严格口径键（pattern×difficulty×seed）与两种口径各自的
  互补总体，并明确 strict 与 loose 是不同总体、不是互补对照。

说明：`_forbid` / `_require` 返回失败清单而非内部 raise，由各测试函数体内的
`assert ... == []` 发出断言信号（`scripts/gates/check_zero_assert_tests.py`
只把测试函数体内的 assert / assert_* / pytest.raises 计为断言信号）。
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DOCS = _ROOT / "docs"


def _read(rel: str) -> str:
    path = _DOCS / rel
    assert path.is_file(), f"文档缺失：{path}"
    return path.read_text(encoding="utf-8")


def _norm(text: str) -> str:
    """压平换行/缩进，便于对跨行句子做子串断言。"""
    return re.sub(r"\s+", " ", text)


def _require(text: str, *needles: str) -> list[str]:
    """返回**缺失**的修正句清单（空清单 = 全部存在；调用方在测试体内 assert）。"""
    flat = _norm(text)
    return [needle for needle in needles if needle not in flat]


def _forbid(text: str, *needles: str) -> list[str]:
    """返回**仍存在**的错误句清单（空清单 = 全部已移除；调用方在测试体内 assert）。"""
    flat = _norm(text)
    return [needle for needle in needles if needle in flat]


def _date_of(text: str) -> str | None:
    match = re.search(r"(最后更新|Last updated)[:：]?\s*(\d{4}-\d{2}-\d{2})", text)
    return match.group(2) if match else None


# ─── F08：synthetic 天花板定因撤回 ───────────────────────────────────────────


class TestF08SyntheticCeilingRetraction:
    """F08（docs/design/emse_layered_narrative.md）：定因撤回 + 敏感性事实保留。"""

    def test_wrong_causal_claims_removed(self) -> None:
        text = _read("design/emse_layered_narrative.md")
        found = _forbid(
            text,
            "~3%（无 flip 空间）",
            "**阴性（信息性真阴性）**",
            "**天花板反例**",
            "**主机制=基线天花板**",
            "## 1. 分层结论 1：detection 基线天花板",
            "是信息性真阴性**（基线天花板所致，非 SpecExpr 无效）",
            "预期不一致对 ≈25",
        )
        assert found == [], f"仍存在错误句：{found}"

    def test_corrected_caliber_and_sensitivity_present(self) -> None:
        text = _read("design/emse_layered_narrative.md")
        missing = _require(
            text,
            "replace 6/174 vs specir 5/174",
            "未检出 168/174 = 96.55%",
            "**未确认（数据不充分）**",
            "BF10=0.5/2",
            "若真有 +8pp 效应，预期不一致对 ≈24.5",
            "≈31；实测仅 3",
            '不能推出"无 0→1 flip 空间"',
            "不能排除 SpecExpr",
            "未由本设计识别",
            '不得写成"信息性真阴性"或"天花板反例"',
        )
        assert missing == [], f"缺少修正句：{missing}"


# ─── F15：red_not_repaired 语义（算法设计 + ADR-0015） ─────────────────────


class TestF15RedNotRepairedSemantics:
    """F15：协议层状态 ≠ 有效检出充分条件；评估层独立 F2P 裁决。"""

    def test_chinese_algorithm_design(self) -> None:
        text = _read("algorithm_design.md")
        found = _forbid(text, "`red_not_repaired`（检出但未修复）计检出")
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "`red_not_repaired`（曾观测红且未修复）只是**协议层机制状态**",
            "不构成有效检出的充分条件",
            "buggy 红 **∧** fixed 绿 **∧** 无执行错误）裁决",
            "主批 88 行",
            "`detection=0` 即反例",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_english_algorithm_design(self) -> None:
        text = _read("algorithm_design.en.md")
        found = _forbid(text, "`red_not_repaired` (detected but not repaired) counts as detection, not repair")
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "**protocol-layer mechanism state**",
            "does not by itself constitute a valid detection",
            "independent three-part F2P criterion",
            "the 88 main-batch",
            "(`detection=0`)",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_adr_0015(self) -> None:
        text = _read("adr/0015-detection-first-protocol.md")
        found = _forbid(text, "（检出成功但未修复——", "评估层 detection 口径应计数")
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "**red_not_repaired**（协议层机制状态",
            "不构成有效检出的充分条件",
            "主批 88 行",
            "detection=0 即反例",
        )
        assert missing == [], f"缺少修正句：{missing}"


# ─── F16：ADR-0016 定位同步（标题 + 首句） ───────────────────────────────────


class TestF16DetectionFirstRepositioning:
    """F16：标题/开篇以检出优先为主定位，多智能体编排=可消融容器（架构事实保留）。"""

    def test_chinese_repositioning(self) -> None:
        text = _read("algorithm_design.md")
        found = _forbid(
            text,
            "# 多智能体协作测试生成与自修复协议",
            "AITester 是一个基于多智能体协作",
        )
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "# 检出优先的测试生成与修复归因评估协议（算法设计文档）",
            "以检出优先（detection-first）协议为核心",
            "多智能体编排定位为可消融容器",
            "多智能体编排协议（可消融容器，ADR-0016）",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_english_repositioning(self) -> None:
        text = _read("algorithm_design.en.md")
        found = _forbid(
            text,
            "# Multi-Agent Collaborative Test Generation",
            "based on multi-agent collaboration",
        )
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "# Detection-First Test Generation and Repair-Attribution Evaluation Protocol",
            "built around the detection-first protocol",
            "multi-agent orchestration positioned as an ablatable container",
            "Multi-Agent Orchestration Protocol (ablatable container, ADR-0016)",
        )
        assert missing == [], f"缺少修正句：{missing}"


# ─── F17：引用核验状态传播（VALIDITY 双语） ─────────────────────────────────


class TestF17CitationVerificationPropagation:
    """F17：ADR-0025 已一手核验；claude-code 聚合数字仍单独标注未核验。"""

    def test_chinese_validity(self) -> None:
        text = _read("VALIDITY.md")
        found = _forbid(
            text,
            '自带"venue/数字未一手核验"标注',
            "自带未一手核验标注",
            "**未一手核验的仓外数字**",
        )
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "2026-10-16 一手核验",
            "10.1109/ASE63991.2025.00031",
            "已清空、零豁免",
            "仓外数字的核验状态（两条分开表述）",
            "claude-code",
            "仍是**未一手核验**的仓外聚合数字",
            "外推限制不因核验而解除",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_english_validity(self) -> None:
        text = _read("VALIDITY.en.md")
        found = _forbid(
            text,
            'carries its own "venue/numbers not first-hand verified" note',
            "carries its own not-first-hand-verified note",
        )
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "first-hand verified on 2026-10-16",
            "10.1109/ASE63991.2025.00031",
            "Verification status of external numbers (two statements kept separate)",
            "claude-code",
            "unverified-first-hand",
            "the extrapolation limit is not lifted by verification",
        )
        assert missing == [], f"缺少修正句：{missing}"


# ─── F18：历史主批 vs 当前确认性主批（DATA_CARD 双语） ─────────────────────


class TestF18HistoricalVersusCurrentMainBatch:
    """F18：n=50/seed42 标注为历史主批；当前确认性主批 87×3 seeds×3 臂。"""

    def test_chinese_data_card(self) -> None:
        text = _read("DATA_CARD.md")
        found = _forbid(text, "## 2. 合成模板库（当前主批次基准）", "主批次在用（n=50 任务")
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "历史主批",
            "当前确认性主批",
            "87 任务 × 3 种子",
            "261 行/臂",
            "--max-pattern-repeat 2",
            "50 是模板库唯一 pattern 数 / 历史主批任务数",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_english_data_card(self) -> None:
        text = _read("DATA_CARD.en.md")
        found = _forbid(
            text,
            "## 2. Synthetic Template Library (current main-batch benchmark)",
            "in use for the main batch (n=50 tasks",
        )
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "historical main batch",
            "confirmatory main-batch composition",
            "87 tasks × 3 seeds",
            "261 rows/arm",
            "--max-pattern-repeat 2",
            "template-library unique-pattern",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_data_card_bilingual_date_synced(self) -> None:
        zh = _date_of(_read("DATA_CARD.md"))
        en = _date_of(_read("DATA_CARD.en.md"))
        assert zh == en == "2026-10-19", (zh, en)


# ─── F20：T-10 严格/宽松口径（VALIDITY 双语） ──────────────────────────────


class TestF20PassMatchedCalibers:
    """F20：严格键含 difficulty；strict/loose 是不同总体、不是互补对照。"""

    def test_chinese_validity(self) -> None:
        text = _read("VALIDITY.md")
        found = _forbid(
            text,
            "严格口径 = pattern×seed",
            "未匹配子集 199 行 / 185 可测检出 38（20.54%）",
        )
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "严格口径**键 = pattern×difficulty×seed",
            "29 行 / 25 可测",
            "232 行 / **215 可测**",
            "38/215 = **17.67%**",
            "62 行 / 55 可测",
            "199 行 / **185 可测**",
            "38/185 = **20.54%**",
            "不同总体、不是互补对照",
        )
        assert missing == [], f"缺少修正句：{missing}"

    def test_english_validity(self) -> None:
        text = _read("VALIDITY.en.md")
        found = _forbid(text, "strict caliber = 29 rows / 25 measurable, loose caliber = 62 rows / 55 measurable")
        assert found == [], f"仍存在错误句：{found}"
        missing = _require(
            text,
            "strict caliber key = pattern×difficulty×seed",
            "29 rows / 25 measurable",
            "**215 measurable**",
            "38/215 = **17.67%**",
            "62 rows / 55 measurable",
            "199 rows / **185 measurable**",
            "38/185 = **20.54%**",
            "different populations, not complementary counterparts",
        )
        assert missing == [], f"缺少修正句：{missing}"


# ─── 双语日期同步（改动文件的头日期） ───────────────────────────────────────


class TestUpdatedHeaderDates:
    """本轮改动文件的"最后更新/Last updated"双侧同步为 2026-10-19。"""

    def test_validity_dates(self) -> None:
        zh = _date_of(_read("VALIDITY.md"))
        en = _date_of(_read("VALIDITY.en.md"))
        assert zh == en == "2026-10-19", (zh, en)

    def test_algorithm_design_dates(self) -> None:
        zh = _date_of(_read("algorithm_design.md"))
        en = _date_of(_read("algorithm_design.en.md"))
        assert zh == en == "2026-10-19", (zh, en)
