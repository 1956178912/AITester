"""
11. 基线数字漂移守卫：核心文档"当前基线"块不得硬编码会过期的测试/静态检查数字。

背景（改进清单 #11，P0）：
    README.md / README.en.md 的"测试状态 / Test Status"表此前内联了
    "2046 passed / 1863 passed / 行覆盖 89%" 等当前基线数字，而 BASELINE.yaml
    （机器可读单一事实来源）推进后数字漂移（如 2046 → 2065），造成文档可信度
    受损。CONTRIBUTING.md "硬性规则：当前基线数字单一来源" 已明确约定：核心维护
    文档只保留"指向 BASELINE.yaml 的链接 + 一句话摘要"，不得各自硬编码。

    历史叙事（CHANGELOG 各条目、README "迭代优化记录" 各轮次快照）记录的是当时
    数字，属历史快照，允许（且应当）保留——本守卫只约束"当前基线"块。

本守卫检查（供 CI 门禁用，默认 fail 0）：
    1. README.md / README.en.md 的"测试状态 / Test Status"当前基线块（从该
       二级标题到下一个二级标题）不得出现"当前基线数字"硬编码模式：
         - `\\d+\\s+passed` / `\\d+\\s+failed`（测试通过/失败计数）
         - `\\d+\\s+collected`（收集计数）
         - `行覆盖\\s*\\d+%` / `total coverage \\d+%`（覆盖率百分比硬编码）
         - `mypy \\d+ 源文件` / `\\d+ source files`（源文件数硬编码）
       命中即 fail，提示"改为指向 BASELINE.yaml 对应节"。
    2. 历史叙事豁免：README 中"## 迭代优化记录 / Iteration log"章节之后的
       内容、CHANGELOG.md / CHANGELOG.en.md 全文，均不在检查范围。

用法：
    python3 scripts/check_baseline_numbers.py [--strict]
    # --strict：预留（当前无警告层，全部为 fail）

退出码：0 = 全过；1 = 有 fail。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# 当前基线块检查目标：(文件, 章节标题正则)。只检查该章节（到下一个 ## 标题为止）。
_TARGETS: list[tuple[str, str]] = [
    ("README.md", r"^##\s+测试状态\s*$"),
    ("README.en.md", r"^##\s+Test Status\s*$"),
]

# 当前基线数字硬编码模式（命中即 fail；历史叙事章节不在检查范围，见 _extract_section）
_DRIFT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("测试通过计数 `\\d+ passed`", re.compile(r"\d+\s+passed")),
    ("测试失败计数 `\\d+ failed`", re.compile(r"\d+\s+failed")),
    ("测试收集计数 `\\d+ collected`", re.compile(r"\d+\s+collected")),
    # O30（2026-09-29 审查 P1）：benchmark 节硬编码——实验数字（成功率 /
    # 变异得分 / FL@k 等）同样会随迭代漂移，守卫扩展至 benchmark 节
    ("benchmark 成功率百分比", re.compile(r"success_rate\s*[:=]\s*\d+\.\d+")),
    ("benchmark 变异得分", re.compile(r"mutation_score\s*[:=]\s*\d+\.\d+")),
    ("benchmark FL@k 指标", re.compile(r"FL@\d+\s*[:=]\s*\d+\.\d+")),
    ("benchmark 迭代次数", re.compile(r"avg_iterations\s*[:=]\s*\d+\.?\d*")),
    ("benchmark 任务总数", re.compile(r"total_tasks\s*[:=]\s*\d+")),
    # O30（2026-09-29 审查 P1）：ruff 检查计数硬编码（ruff 全过 / N 处 error）
    ("ruff 检查计数", re.compile(r"ruff\s+(?:全过|all checks passed|\d+\s+errors?)", re.IGNORECASE)),
    ("行覆盖百分比（中文）", re.compile(r"行覆盖\s*\d+\s*%")),
    ("行覆盖百分比（英文）", re.compile(r"(?:total|line)\s+coverage\s*[:=]?\s*\d+\s*%", re.IGNORECASE)),
    ("mypy 源文件数（中文）", re.compile(r"mypy\s+\d+\s+源文件")),
    ("mypy 源文件数（英文）", re.compile(r"mypy\s+\d+\s+source files", re.IGNORECASE)),
    # U7（2026-10-05 系统性审查落地）：逐模块覆盖率硬编码——README 曾内联
    # "code_analyzer.py (100%) ... api_manager.py (94%)" 逐模块表，与
    # BASELINE.yaml coverage.line_core_modules 漂移（100% vs 实测 89%）。
    # 该表已改为指向 BASELINE；本模式防回填（允许表内引用 BASELINE 数字时
    # 用"模块名 数字 /"的格式，不带 "(N%)" 括号形态）。
    ("逐模块覆盖率硬编码 `module.py (N%)`", re.compile(r"\w+\.py\s*\(\d+%\)")),
]


def _extract_section(text: str, heading_re: re.Pattern[str]) -> str:
    """提取从指定二级标题到下一个二级标题之间的内容；未找到标题时返回空串。"""
    lines = text.splitlines()
    start = -1
    for i, line in enumerate(lines):
        if heading_re.match(line):
            start = i + 1
            break
    if start < 0:
        return ""
    end = len(lines)
    for j in range(start, len(lines)):
        if lines[j].startswith("## "):
            end = j
            break
    return "\n".join(lines[start:end])


def check_baseline_numbers() -> list[str]:
    """检查核心文档当前基线块是否残留会过期的数字硬编码。

    Returns:
        fail 信息列表（空 = 全过）。
    """
    failures: list[str] = []
    for rel, heading in _TARGETS:
        path = Path(rel)
        if not path.exists():
            failures.append(f"{rel} 不存在（当前基线块无法校验）")
            continue
        section = _extract_section(path.read_text(encoding="utf-8"), re.compile(heading))
        if not section:
            failures.append(f"{rel} 未找到当前基线章节（{heading}）——章节改名后需同步更新本守卫")
            continue
        for line in section.splitlines():
            for label, pattern in _DRIFT_PATTERNS:
                if pattern.search(line):
                    failures.append(
                        f"{rel} 当前基线块残留 {label}：{line.strip()[:120]}（改为指向 BASELINE.yaml 对应节）"
                    )
    return failures


def main() -> int:
    failures = check_baseline_numbers()
    for f in failures:
        print(f"  [FAIL] {f}")
    if failures:
        print(f"基线数字漂移检查失败（{len(failures)} 处残留硬编码，见 CONTRIBUTING.md 单一来源约定）")
        return 1
    print("基线数字漂移检查通过（当前基线块零硬编码，统一指向 BASELINE.yaml）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
