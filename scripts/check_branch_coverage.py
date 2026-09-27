"""
8. 核心条件路由模块分支覆盖门槛守卫（供 CI 门禁用）。

背景（改进清单 #8，P1）：
    多智能体系统的条件路由（_should_debug / _route_after_diagnosis /
    refine_failure_category 等）是修复质量的瓶颈：分支覆盖不足意味着"达上限
    × 关键词命中 × 再生成上限"这类交叉场景长期未被测试。CI 已用
    `--cov-branch` 生成 coverage.xml，本脚本解析该产物并做两层守卫：

    1. 总门槛（hard gate）：全仓分支覆盖率 ≥ 总门槛（默认 80%），低于即 fail；
    2. 核心路由模块逐模块门槛：GRAPH / ROUTING 模块分支覆盖率 ≥ 85%
       （_should_debug / error_classifier / state 的条件路由密集区），
       逐模块低于即 fail（列出具体模块 + 实测值）。

    与 BASELINE.yaml `coverage.branch_core_routing` 节同口径（实测值回填该节，
    门槛以本脚本为准；模块清单改动需同步 BASELINE.yaml 注释）。

用法：
    python scripts/check_branch_coverage.py [coverage.xml 路径]
    # 默认读仓库根 coverage.xml（CI 的 Run tests with coverage 步骤产物）；
    # 本地可先 `pytest --cov=src --cov-branch --cov-report=xml` 再生成。

退出码：0 = 全过；1 = 有模块/总门槛未达标；2 = 产物缺失/解析错误。
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ─── 门槛配置（与 BASELINE.yaml coverage.branch_core_routing 注释同口径）──────
# 总门槛取当前实测分支覆盖的保守值（2026-09-28 首测 79.56%），随核心路由
# 模块补组合测试而逐步上调（目标 85%+）；逐模块门槛 85% 不变。
_TOTAL_THRESHOLD = 0.79
_CORE_THRESHOLD = 0.85
# 核心条件路由模块（分支密集：_should_debug / 诊断路由 / 状态细化 / 多候选触发）。
# 以 "filename" 片段匹配 coverage.xml 的 <file name="...">（形如 graph/workflow.py）。
_CORE_MODULES: tuple[str, ...] = (
    "graph/workflow.py",
    "graph/state.py",
    "graph/tracing.py",
    "agents/error_classifier.py",
)


def _read_branch_rates(xml_path: Path) -> tuple[float, dict[str, float]]:
    """解析 coverage.xml，返回 (总分支率, {模块路径: 分支率})。

    coverage.py v7 的 XML 产物层级为 coverage→packages→package→classes→class，
    <class filename="graph/workflow.py" branch-rate="...">；同时兼容 <file> 变体。
    模块路径为相对 src/ 的口径（形如 "graph/workflow.py"）。
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    total = root.get("branch-rate")
    rates: dict[str, float] = {}
    for el in root.iter():
        if el.tag not in ("class", "file"):
            continue
        name = el.get("filename") or el.get("name") or ""
        br = el.get("branch-rate")
        if name and br is not None and name.endswith(".py"):
            rates[name] = float(br)
    total_rate = float(total) if total is not None else None
    if total_rate is None:
        # 兜底：根无 branch-rate（旧版 coverage）时用模块均值
        total_rate = sum(rates.values()) / len(rates) if rates else 0.0
    return total_rate, rates


def check_branch_coverage(xml_path: str | Path = "coverage.xml") -> list[str]:
    """校验总门槛 + 核心路由模块逐模块门槛。

    Returns:
        fail 信息列表（空 = 全过）。
    """
    p = Path(xml_path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        return [f"coverage.xml 不存在：{p}（先运行 pytest --cov=src --cov-branch --cov-report=xml）"]
    try:
        total_rate, rates = _read_branch_rates(p)
    except (ET.ParseError, ValueError) as e:
        return [f"coverage.xml 解析失败：{e}"]

    failures: list[str] = []
    if total_rate < _TOTAL_THRESHOLD:
        failures.append(f"总分支覆盖率 {total_rate:.0%} 低于门槛 {_TOTAL_THRESHOLD:.0%}（--cov-branch 总口径）")

    for module in _CORE_MODULES:
        # coverage.xml 中 filename 形如 "graph/workflow.py"（相对 src/ 口径）
        matched = {k: v for k, v in rates.items() if k.endswith(module)}
        if not matched:
            failures.append(f"核心路由模块 {module} 未在 coverage.xml 中匹配到（模块改名/移动需更新本脚本）")
            continue
        rate = min(matched.values())
        if rate < _CORE_THRESHOLD:
            failures.append(
                f"核心路由模块 {module} 分支覆盖率 {rate:.0%} 低于门槛 {_CORE_THRESHOLD:.0%}"
                "（补组合路由测试：达上限×关键词命中×再生成上限交叉场景）"
            )
    return failures


def main() -> int:
    xml_path = sys.argv[1] if len(sys.argv) > 1 else "coverage.xml"
    failures = check_branch_coverage(xml_path)
    if failures:
        for f in failures:
            print(f"  [FAIL] {f}")
        print(f"分支覆盖门槛未达标（{len(failures)} 处）")
        return 1
    print(f"分支覆盖门槛达标（总 ≥{_TOTAL_THRESHOLD:.0%}，核心路由模块 ≥{_CORE_THRESHOLD:.0%}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
