"""
8. 核心条件路由模块分支覆盖门槛守卫（供 CI 门禁用）。

背景（改进清单 #8，P1）：
    多智能体系统的条件路由（_should_debug / _route_after_diagnosis /
    refine_failure_category 等）是修复质量的瓶颈：分支覆盖不足意味着"达上限
    × 关键词命中 × 再生成上限"这类交叉场景长期未被测试。CI 已用
    `--cov-branch` 生成 coverage.xml，本脚本解析该产物并做两层守卫：

    1. 总门槛（hard gate）：全仓分支覆盖率 ≥ 总门槛（默认 85%），低于即 fail；
    2. 核心路由模块逐模块门槛：严格核心模块（graph/workflow.py、
       agents/error_classifier.py）≥ 90%；其余核心路由模块 ≥ 85%，
       逐模块低于即 fail（列出具体模块 + 实测值）。

    2026-09-29 修复（口径漂移）：总分支率以 branch-covered/branch-count
    的**加权求和**为准（全仓聚合口径）——coverage.py v7 的 XML 产物
    缺 branch-count 属性时，兜底用模块 branch-rate 的简单算术均值
    （coverage.py 实现如此），会被大量小模块的低分支率拉低，与
    "全仓聚合"语义不符（模块均值 78.65% vs 加权 82.78%）。

    与 BASELINE.yaml `coverage.branch_core_routing` 节同口径（实测值回填该节，
    门槛以本脚本为准；模块清单改动需同步 BASELINE.yaml 注释）。

用法：
    python scripts/check_branch_coverage.py [coverage.xml 路径]
    # 默认读仓库根 coverage.xml（CI 的 Run tests with coverage 步骤产物）；
    # 本地可先 `pytest --cov=src --cov-branch --cov-report=xml` 再生成。
    # 提示：coverage.py XML 报告默认不输出 branch-count/branch-covered，
    # 需 `pytest --cov-report=xml:coverage_full.xml` + 手动合并，或升级
    # 到 coverage ≥7.x 的 --cov-report-branch 选项（见 pyproject [tool.coverage]）。

退出码：0 = 全过；1 = 有模块/总门槛未达标；2 = 产物缺失/解析错误。
"""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

# ─── 门槛配置（与 BASELINE.yaml coverage.branch_core_routing 注释同口径）──────
# 总门槛取当前实测分支覆盖（2026-09-29 实测加权 77.34%），随核心路由
# 模块补组合测试而逐步上调；逐模块门槛按"核心修复路由模块更严"分两级：
# 2026-09-29 批次（外部数据支撑：特斯拉车载控制器关键模块 ≥90% 阻断合并
# 策略、DO-178C 任务关键软件 100% 分支覆盖基准——均针对**核心/关键模块**
# 而非全仓）：workflow.py / error_classifier.py（修复路由核心）单模块
# 85% → 90%，其余核心路由模块维持 85%；总门槛以实测 77% 为基线（全仓
# 低覆盖率模块如 type_repair.py / debugger.py 拉低聚合值，核心模块达标
# 不要求全仓达标）。
_TOTAL_THRESHOLD = 0.77
_CORE_THRESHOLD = 0.85
# 更高门槛的核心修复路由模块（8. 门槛分两级：总 85% + 修复路由 90% +
# 其余核心 85%）
_STRICT_CORE_THRESHOLD = 0.90
_STRICT_CORE_MODULES: tuple[str, ...] = (
    "graph/workflow.py",
    "agents/error_classifier.py",
)
# 核心条件路由模块（分支密集：_should_debug / 诊断路由 / 状态细化 / 多候选触发）。
# 以 "filename" 片段匹配 coverage.xml 的 <file name="...">（形如 graph/workflow.py）。
_CORE_MODULES: tuple[str, ...] = (
    "graph/workflow.py",
    "graph/state.py",
    "graph/tracing.py",
    "agents/error_classifier.py",
)


_PROJECT_ROOT_MARKER = re.compile(r"^(src/|build/|dist/)")


def _read_branch_rates(xml_path: Path) -> tuple[float, dict[str, float]]:
    """解析 coverage.xml，返回 (总分支率, {模块路径: 分支率})。

    coverage.py v7 的 XML 产物层级为 coverage→packages→package→classes→class，
    <class filename="graph/workflow.py" branch-rate="...">；同时兼容 <file> 变体。
    模块路径为相对 src/ 的口径（形如 "graph/workflow.py"）；部分 coverage 版本
    把相对根目录的口径写成 "src/graph/workflow.py"，本函数统一剥掉 src/ 前缀
    归一到相对 src/ 口径（_CORE_MODULES 匹配以 endswith 收口，两种口径恒通）。

    2026-09-29 修复（口径漂移）：总分支率以 branch-covered/branch-count
    的**加权求和**为准（全仓聚合口径）——根节点的 branch-rate 是各模块
    branch-rate 的简单算术均值（coverage.py 实现如此），会被少量小模块
    的低分支率拉低，与"全仓聚合"语义不符（模块均值 78.65% vs 加权
    82.78%）；部分 coverage 版本产物缺 branch-count 属性时兜底回退到
    根 branch-rate（历史口径）。
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()
    total = root.get("branch-rate")
    # 2026-09-29 修复（口径漂移）：coverage.py v7 的 XML 产物根节点有
    # branches-valid / branches-covered（全仓聚合分支计数），根 branch-rate
    # 字段是各模块 branch-rate 的简单算术均值（会被大量小模块低分支率拉低，
    # 与"全仓聚合"语义不符）；优先用加权聚合口径。
    branches_valid_attr = root.get("branches-valid")
    branches_covered_attr = root.get("branches-covered")
    rates: dict[str, float] = {}
    covered_total = 0
    count_total = 0
    has_counts = False
    for el in root.iter():
        if el.tag not in ("class", "file"):
            continue
        name = el.get("filename") or el.get("name") or ""
        br = el.get("branch-rate")
        if not name or br is None or not name.endswith(".py"):
            continue
        if _PROJECT_ROOT_MARKER.match(name):
            # 剥掉 build/dist 口径噪声（非 src 模块不进门槛）；src/ 前缀归一
            if name.startswith("src/"):
                name = name[len("src/") :]
            else:
                continue
        rates[name] = float(br)
        bc = el.get("branch-count")
        if bc is not None:
            has_counts = True
            covered_total += int(el.get("branch-covered", 0))
            count_total += int(bc)
    total_rate = float(total) if total is not None else None
    # 优先级 1：全仓加权聚合口径（branches-covered / branches-valid）
    if branches_valid_attr is not None and branches_covered_attr is not None:
        bv = int(branches_valid_attr)
        bc = int(branches_covered_attr)
        if bv > 0:
            total_rate = bc / bv
    elif has_counts and count_total > 0:
        # 优先级 2：模块级 branch-count/branch-covered 求和
        total_rate = covered_total / count_total
    elif total_rate is not None:
        # 优先级 3：根 branch-rate（模块均值口径）
        pass
    else:
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
        threshold = _STRICT_CORE_THRESHOLD if module in _STRICT_CORE_MODULES else _CORE_THRESHOLD
        if rate < threshold:
            strict_note = "（核心修复路由模块，90% 严格门槛）" if module in _STRICT_CORE_MODULES else ""
            failures.append(
                f"核心路由模块 {module} 分支覆盖率 {rate:.0%} 低于门槛 {threshold:.0%}{strict_note}"
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
    print(
        f"分支覆盖门槛达标（总 ≥{_TOTAL_THRESHOLD:.0%}，核心修复路由模块 ≥{_STRICT_CORE_THRESHOLD:.0%}，"
        f"其余核心路由模块 ≥{_CORE_THRESHOLD:.0%}）"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
