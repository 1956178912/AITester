"""
文档一致性治理：docs/history/ 历史快照文档的基线数字漂移检测（warning-only）。

背景（文档一致性 P2 缺口 #3）：
    docs/history/ 存放历史轮次的快照文档（含"1937 passed"这类基线数字），
    CONTRIBUTING.md 已约定"历史文档头部有归档说明，当前决策以 CHANGELOG 为准"，
    但缺少自动化的漂移提醒——当某历史文档标注的基线数字与
    BASELINE.yaml 的当前值偏离超过阈值时，应自动输出 warning 提示
    "该文档可能已被当前基线覆盖，考虑归档"。

设计口径（保守、非阻断）：
    - 检测范围：docs/history/*.md 中匹配 "N passed" / "N tests" / "total_passed"
      的数字声明（正则保守提取，避免误命中版本号 / 年份等数字）；
    - 对比基准：BASELINE.yaml 的 tests.total_passed（当前机器可读单一事实来源）；
    - 漂移阈值：--threshold 参数（默认 10%，偏离超过即 warning）；
    - 非阻断：--warn-only（默认）时仅输出 warning 不退出码 1；
      加 --strict 时偏离超阈值退出码 1（CI 可选启用严格模式）；
    - 无 docs/history/ 目录 / 无数字声明 / BASELINE.yaml 缺失 total_passed 时
      直接通过（无数据可对比，不误报）。

使用方式（CI，warning-only 默认）：
    python scripts/gates/check_docs_history_drift.py --warn-only
    python scripts/gates/check_docs_history_drift.py --threshold 20 --strict
"""

from __future__ import annotations

import argparse
import os
import re
import sys


def _load_baseline_total_passed() -> int | None:
    """读 BASELINE.yaml 的 tests.total_passed（缺失 / 解析失败时返回 None）。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    baseline_path = os.path.join(base_dir, "BASELINE.yaml")
    if not os.path.exists(baseline_path):
        return None
    try:
        import yaml  # 保守：缺 yaml 依赖时降级（不阻断，仅跳过对比）

        with open(baseline_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        total = (data.get("tests") or {}).get("total_passed")
        return int(total) if total is not None else None
    except (OSError, ImportError, yaml.YAMLError, ValueError, TypeError):
        return None


def _extract_baseline_numbers(doc_text: str) -> list[int]:
    """从历史文档提取"测试通过数"数字声明（保守正则，避免误命中年份 / 版本号）。

    匹配模式（任一命中即视为"基线数字声明"）：
        - `1937 passed` / `1937 tests`（"N passed" / "N tests" 口径）
        - `total_passed: 1937`（BASELINE 同口径键名）
    保守口径：仅取 100-99999 区间的整数（测试数量级，避免误命中
    "3.12" 版本 / "2026" 年份 / 覆盖率百分比 等）。
    """
    numbers: list[int] = []
    # "N passed" / "N tests"（行首 / 空格后，避免命中 "tests/" 路径误报）
    for m in re.finditer(r"\b(\d{3,5})\s+(?:passed|tests)\b", doc_text):
        val = int(m.group(1))
        if 100 <= val <= 99999:
            numbers.append(val)
    # "total_passed: N"（BASELINE 同口径键名）
    for m in re.finditer(r"total_passed\s*[:=]\s*(\d{3,5})\b", doc_text):
        val = int(m.group(1))
        if 100 <= val <= 99999:
            numbers.append(val)
    return numbers


def _check_history_drift(threshold_pct: float, strict: bool) -> int:
    """扫描 docs/history/*.md，输出漂移 warning（默认非阻断）。

    Returns:
        退出码（--strict 时偏离超阈值 → 1；--warn-only → 0）。
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    history_dir = os.path.join(base_dir, "docs", "history")
    if not os.path.isdir(history_dir):
        print("[docs-history-drift] docs/history/ 不存在（无需检测）")
        return 0

    baseline = _load_baseline_total_passed()
    if baseline is None:
        print("[docs-history-drift] BASELINE.yaml 缺失 / 无 tests.total_passed（跳过对比）")
        return 0

    drifts: list[tuple[str, int, int, float]] = []
    for name in sorted(os.listdir(history_dir)):
        if not name.endswith(".md"):
            continue
        path = os.path.join(history_dir, name)
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        for num in _extract_baseline_numbers(text):
            if num == 0:
                continue
            drift_pct = abs(num - baseline) / baseline * 100 if baseline > 0 else 0.0
            if drift_pct >= threshold_pct:
                drifts.append((name, num, baseline, drift_pct))

    if not drifts:
        print(
            f"[docs-history-drift] docs/history/ 全部文档基线数字与 BASELINE.yaml（{baseline}）偏离 < {threshold_pct:.0f}%，无需归档"
        )
        return 0

    for name, num, base, pct in drifts:
        print(
            f"[{'warning' if not strict else 'ERROR'}] docs/history/{name} 声明基线数字 {num}，"
            f"与 BASELINE.yaml（{base}）偏离 {pct:.1f}%（≥ 阈值 {threshold_pct:.0f}%）——"
            f"该文档可能已被当前基线覆盖，考虑归档或更新头部声明"
        )

    if strict:
        print(f"[docs-history-drift] 共 {len(drifts)} 条漂移（--strict 阻断）")
        return 1
    print(f"[docs-history-drift] 共 {len(drifts)} 条漂移（--warn-only 不阻断）")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="docs/history/ 历史快照文档的基线数字漂移检测")
    parser.add_argument("--threshold", type=float, default=10.0, help="漂移阈值（百分比，默认 10%%）")
    parser.add_argument("--strict", action="store_true", help="偏离超阈值时退出码 1（默认 warn-only 不阻断）")
    parser.add_argument(
        "--warn-only", action="store_true", help="显式标记为 warning-only（与默认行为一致，便于 CI 可读性）"
    )
    args = parser.parse_args()
    return _check_history_drift(args.threshold, strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
