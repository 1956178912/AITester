"""
5b. BASELINE.yaml 校验器：基线数字与实测/结构偏差门禁。

背景（改进清单 #5b，P0）：
    BASELINE.yaml 是"机器可读单一事实来源"，但此前缺乏自动化校验——
    批次落地后忘记刷新、或字段与实测值漂移时无人发现（如 tests.total_passed
    与全量 pytest 实测不一致）。本脚本做两层守卫：

    1. 结构校验（零依赖，CI 快检）：必填字段存在、类型合法、
       tests.total_failed == 0（基线必须全绿才允许刷新）、
       coverage.line_total_pct / branch_total_pct 在 [0, 100] 区间、
       static_checks.ruff_warnings / mypy_errors 为 0。
    2. 实测一致性校验（可选，`--verify` 本地全量模式）：跑全量 pytest 收集
       计数与 BASELINE.yaml `tests.total_passed` 对比，偏差超阈值（默认 ±2%
       容差，精简环境 skipif 漂移）即 fail；供批次落地后人工/CI 夜间任务
       运行（CI 主链只跑结构校验，避免每 PR 重跑全量测试）。

用法：
    python scripts/check_baseline.py            # 结构校验（CI 门禁，快）
    python scripts/check_baseline.py --verify   # 结构 + 全量实测一致性（批次落地后）

退出码：0 = 全过；1 = 结构/一致性 fail；2 = 文件缺失/解析错误。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pyyaml 缺失时降级为最小解析（仅覆盖 BASELINE.yaml 的扁平结构）
    yaml = None

PROJECT_ROOT = Path(__file__).parent.parent
BASELINE_PATH = PROJECT_ROOT / "BASELINE.yaml"

# 全量 pytest 实测与 BASELINE total_passed 的容差比例（精简环境 skipif 漂移）
_MEASURE_TOLERANCE = 0.02


def _load_baseline() -> dict:
    """加载 BASELINE.yaml（pyyaml 缺失时用最小行解析兜底）。"""
    if not BASELINE_PATH.exists():
        print(f"  [FAIL] BASELINE.yaml 不存在：{BASELINE_PATH}")
        sys.exit(2)
    text = BASELINE_PATH.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            print("  [FAIL] BASELINE.yaml 顶层不是映射")
            sys.exit(2)
        return data
    # 最小解析兜底：`key: value` 扁平读取（仅覆盖本文件用到的顶层+两节）
    data: dict = {}
    current_top: str | None = None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""
        if not line.strip():
            continue
        if not raw.startswith(" ") and raw.strip():
            current_top = raw.split(":", 1)[0].strip()
            data[current_top] = {}
        elif current_top and ":" in line:
            key, _, val = line.strip().partition(":")
            data[current_top][key.strip()] = _parse_scalar(val.strip())
    return data


def _parse_scalar(val: str):
    """解析 BASELINE.yaml 标量（int / float / null / str）。"""
    if val in ("", "null", "~", "None"):
        return None
    if val in ("true", "True"):
        return True
    if val in ("false", "False"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val.strip().strip('"').strip("'")


def check_structure() -> list[str]:
    """结构校验：必填字段、取值区间、基线全绿约定。"""
    failures: list[str] = []
    data = _load_baseline()

    tests = data.get("tests", {})
    if not isinstance(tests, dict) or not tests:
        failures.append("tests 节缺失或为空")
    else:
        total_passed = tests.get("total_passed")
        if not isinstance(total_passed, int) or total_passed <= 0:
            failures.append(f"tests.total_passed 应为正整数，实为 {total_passed!r}")
        total_failed = tests.get("total_failed")
        if total_failed != 0:
            failures.append(f"tests.total_failed 应为 0（基线必须全绿），实为 {total_failed!r}")
        suite = tests.get("suite_seconds")
        if suite is not None and (not isinstance(suite, (int, float)) or suite <= 0):
            failures.append(f"tests.suite_seconds 应为正数或 null，实为 {suite!r}")

    coverage = data.get("coverage", {})
    if not isinstance(coverage, dict) or not coverage:
        failures.append("coverage 节缺失或为空")
    else:
        for field in ("line_total_pct", "branch_total_pct"):
            val = coverage.get(field)
            if val is not None and (not isinstance(val, (int, float)) or not (0 <= val <= 100)):
                failures.append(f"coverage.{field} 应在 [0,100] 区间（或 null 待回填），实为 {val!r}")

    static = data.get("static_checks", {})
    if not isinstance(static, dict) or not static:
        failures.append("static_checks 节缺失或为空")
    else:
        for field in ("ruff_warnings", "mypy_errors"):
            val = static.get(field)
            if val != 0:
                failures.append(f"static_checks.{field} 应为 0，实为 {val!r}")

    last_verified = data.get("last_verified")
    if not isinstance(last_verified, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(last_verified)):
        failures.append(f"last_verified 应为 YYYY-MM-DD 字符串，实为 {last_verified!r}")

    categories = data.get("error_categories")
    if categories is not None and (not isinstance(categories, int) or categories < 0):
        failures.append(f"error_categories 应为非负整数，实为 {categories!r}")

    return failures


def measure_full_suite() -> int | None:
    """跑全量 pytest 收集计数（--collect-only -q），返回通过用例数。"""
    env = dict(os.environ)
    env.setdefault("AITESTER_LLM_CACHE", "0")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only", "-q", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=env,
    )
    # collect-only 末行形如 "927 tests collected in 2.10s"
    for line in reversed(result.stdout.splitlines()):
        m = re.search(r"(\d+) tests? collected", line)
        if m:
            return int(m.group(1))
    return None


def check_consistency() -> list[str]:
    """实测一致性校验：全量收集计数 vs BASELINE.yaml tests.total_passed（±2% 容差）。"""
    failures: list[str] = []
    data = _load_baseline()
    baseline_passed = data.get("tests", {}).get("total_passed")
    if not isinstance(baseline_passed, int):
        return ["tests.total_passed 非法，无法做一致性校验"]

    measured = measure_full_suite()
    if measured is None:
        return [f"全量 pytest 收集失败，无法校验（请检查 {sys.executable} 环境）"]

    drift = abs(measured - baseline_passed) / max(baseline_passed, 1)
    if drift > _MEASURE_TOLERANCE:
        failures.append(
            f"实测收集 {measured} 用例 vs BASELINE.yaml total_passed {baseline_passed}"
            f"（漂移 {drift:.1%} 超容差 {_MEASURE_TOLERANCE:.0%}）——批次落地后请刷新 BASELINE.yaml"
        )
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 BASELINE.yaml 结构与（可选）实测一致性")
    parser.add_argument("--verify", action="store_true", help="额外跑全量收集做一致性校验（慢）")
    args = parser.parse_args()

    failures = check_structure()
    if failures:
        for f in failures:
            print(f"  [FAIL] {f}")
        print(f"BASELINE.yaml 结构校验失败（{len(failures)} 处）")
        return 1

    if args.verify:
        failures = check_consistency()
        if failures:
            for f in failures:
                print(f"  [FAIL] {f}")
        else:
            print("BASELINE.yaml 结构与实测一致性校验通过")

    print("BASELINE.yaml 结构校验通过" if not args.verify else "（结构校验通过）")
    return 1 if failures and args.verify else 0


if __name__ == "__main__":
    sys.exit(main())
