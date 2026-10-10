#!/usr/bin/env python
"""W2（2026-10-05 审查落地）：覆盖率渐进式紧箍（ratchet）门禁。

背景：
    现行覆盖率门禁（check_branch_coverage.py：总行 85% / 总分支 77%）是
    **贴着历史基线设的静态门槛**——实测 89%/83% 远高于门槛，门禁锁的是
    "不退化到基线以下"而非"质量提升"；且已实际诱发"为门槛写测试"的行为
    （tests/test_branch_coverage_fill.py 文件头自述"把总分支覆盖从 76.4%
    抬到 ≥77%"）。本脚本引入只升不降的 ratchet：

    - 门槛水位存于 docs/coverage_ratchet.yaml（入库，随提交演进）；
    - CI（--check 模式）：实测低于水位 → exit 1 阻断（回退即失败）；
    - 本地（默认模式）：实测高于水位 + 步长（默认 0.5pp）→ 自动上调水位
      写回状态文件，由贡献者随改动一并提交；水位**永不下降**。

    与静态门槛的关系：叠加而非取代——静态门槛（85/77）仍是硬下限，
    ratchet 在其上单调收紧。

用法：
    python scripts/gates/coverage_ratchet.py                    # 本地：检查 + 满足步长则上调
    python scripts/gates/coverage_ratchet.py --check            # CI：只检查不写（阻断回退）
    python scripts/gates/coverage_ratchet.py --coverage-xml path/to/coverage.xml
    python scripts/gates/coverage_ratchet.py --bump 0.5         # 步长（百分点，默认 0.5）

退出码：0 = 达标（本地模式含成功上调）；1 = 实测低于水位（回退）；
2 = 产物缺失 / 状态文件解析错误。

口径：与 check_branch_coverage.py 同源——coverage.xml 根节点的
lines-covered/lines-valid 与 branches-covered/branches-valid 加权聚合；
缺 branches-* 属性时兜底根 branch-rate（算术均值口径，与该脚本同）。
"""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = PROJECT_ROOT / "docs" / "coverage_ratchet.yaml"

# 水位初始化基准（2026-10-05 W 批次）：实测行 89.45% / 分支 82.59%
# （BASELINE.yaml coverage 节），初始化为略低于实测、高于旧静态门槛
# （行 85 / 分支 77）的整数值——ratchet 从这里开始只升不降。
_INIT_LINE = 89.0
_INIT_BRANCH = 82.0


def _parse_state(path: Path) -> dict[str, float]:
    """解析水位状态文件（key: value 简单格式，避免引入 yaml 依赖）。

    文件缺失时返回初始水位并提示（首次运行自动落盘初始化）。
    """
    if not path.exists():
        print(f"[ratchet] 状态文件不存在，使用初始水位 line={_INIT_LINE} branch={_INIT_BRANCH}")
        return {"line_total": _INIT_LINE, "branch_total": _INIT_BRANCH}
    state: dict[str, float] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        try:
            state[key] = float(value)
        except ValueError:
            print(f"[ratchet] 忽略无法解析的行：{raw!r}")
    for required in ("line_total", "branch_total"):
        if required not in state:
            print(f"[ratchet] 状态文件缺 {required} 键，解析失败：{path}")
            sys.exit(2)
    return state


def _write_state(path: Path, state: dict[str, float]) -> None:
    """写回水位文件（带头部说明，key 保持稳定顺序）。"""
    header = (
        "# W2 覆盖率渐进式紧箍水位（scripts/gates/coverage_ratchet.py 读写，请勿手降）\n"
        "#\n"
        "# 规则：本地运行 ratchet（无 --check）实测高于水位+步长时自动上调并写回，\n"
        "# 由贡献者随改动提交；水位只升不降。CI 以 --check 模式阻断回退。\n"
        "# 静态硬下限（行 85 / 分支 77）仍由 check_branch_coverage.py 把守。\n"
    )
    body = "\n".join(
        [
            f"line_total: {state['line_total']:.2f}",
            f"branch_total: {state['branch_total']:.2f}",
        ]
    )
    path.write_text(header + body + "\n", encoding="utf-8")


def _read_actual(xml_path: Path) -> tuple[float, float]:
    """从 coverage.xml 读取 (总行覆盖%, 总分支覆盖%)。

    行覆盖：lines-covered / lines-valid 加权；分支覆盖：branches-covered /
    branches-valid 加权（缺属性时兜底根 branch-rate 算术均值口径，
    与 check_branch_coverage.py 同源兜底）。
    """
    if not xml_path.exists():
        print(f"[ratchet] coverage.xml 不存在：{xml_path}")
        sys.exit(2)
    root = ET.parse(xml_path).getroot()
    line_rate = root.get("line-rate")
    branch_rate = root.get("branch-rate")
    lines_valid = root.get("lines-valid")
    lines_covered = root.get("lines-covered")
    branches_valid = root.get("branches-valid")
    branches_covered = root.get("branches-covered")

    line_pct: float | None = None
    if lines_valid and lines_covered and float(lines_valid) > 0:
        line_pct = 100.0 * float(lines_covered) / float(lines_valid)
    elif line_rate is not None:
        line_pct = 100.0 * float(line_rate)

    branch_pct: float | None = None
    if branches_valid and branches_covered and float(branches_valid) > 0:
        branch_pct = 100.0 * float(branches_covered) / float(branches_valid)
    elif branch_rate is not None:
        branch_pct = 100.0 * float(branch_rate)

    if line_pct is None or branch_pct is None:
        print("[ratchet] coverage.xml 缺 line/branch 覆盖属性，解析失败")
        sys.exit(2)
    return line_pct, branch_pct


def main() -> int:
    parser = argparse.ArgumentParser(description="覆盖率渐进式紧箍（ratchet）门禁（W2）")
    parser.add_argument("--coverage-xml", default=str(PROJECT_ROOT / "coverage.xml"), help="coverage.xml 路径")
    parser.add_argument("--state", default=str(STATE_FILE), help="水位状态文件路径")
    parser.add_argument("--check", action="store_true", help="只检查不写（CI 模式：回退即失败）")
    parser.add_argument("--bump", type=float, default=0.5, help="上调步长（百分点，默认 0.5）")
    args = parser.parse_args()

    state = _parse_state(Path(args.state))
    line_pct, branch_pct = _read_actual(Path(args.coverage_xml))

    failed = False
    new_state = dict(state)
    for key, actual, label in (
        ("line_total", line_pct, "总行覆盖"),
        ("branch_total", branch_pct, "总分支覆盖"),
    ):
        floor = state[key]
        if actual < floor - 1e-9:
            print(f"[ratchet] ❌ {label}回退：实测 {actual:.2f}% < 水位 {floor:.2f}%")
            failed = True
            continue
        headroom = actual - floor
        if not args.check and headroom >= args.bump:
            # 上调至实测向下取整到 0.1pp（避免噪声抖动），永不下降。
            # floor 用 math.floor(x*10)/10（浮点 // 会出现 90.0//0.1*0.1→89.9 的精度坑）
            new_state[key] = math.floor(actual * 10) / 10
            print(f"[ratchet] ⬆ {label}水位上调：{floor:.2f}% → {new_state[key]:.1f}%（实测 {actual:.2f}%）")
        else:
            print(f"[ratchet] ✅ {label}达标：实测 {actual:.2f}% ≥ 水位 {floor:.2f}%（余量 {headroom:.2f}pp）")

    if failed:
        return 1
    if not args.check and new_state != state:
        _write_state(Path(args.state), new_state)
        print(f"[ratchet] 水位已写回 {args.state}（随本次改动一并提交）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
