#!/usr/bin/env python
"""X3（2026-10-05 审查 P0-5）：环境变量开关预算守卫（freeze ratchet）。

背景：
    全仓环境变量开关已 143+（59 个 *_ENABLE，约 47 个默认关）——审查
    判定"开关矩阵不可导航，实验组合空间不可枚举"已成负资产。P0-5 决策：
    **冻结新增**——新产品开关必须显式登记（PR diff 可见），存量自然收敛。

    与 coverage_ratchet 同模式（只紧不松的棘轮）：
    - 登记表存 docs/env_budget.yaml（入库，随提交演进）；
    - CI（--check 模式）：扫描发现**未登记**的环境变量名 → exit 1 阻断；
    - 本地（默认模式）：新增名字自动登记写回（由贡献者随改动提交，
      "显式登记"即"改这个文件"这个动作本身）；删名允许（登记表随之
      收缩，下次扫描重建）。

口径与能力边界：
    - 扫描范围：src/**/*.py + config.py（产品开关面）。experiments/ 与
      scripts/ 的实验性 os.getenv 不计入（实验脚本不属于产品开关矩阵）；
    - 静态提取：os.getenv("X") / os.environ.get("X") / os.environ["X"] /
      os.environ.setdefault("X", ...) / 模块级 _ENV* = "X" 常量；
      动态拼接（os.getenv(f"...") ）提取不到——已知漏网面，登记表是
      名字集合而非完备性证明；
    - 计数口径：唯一名字数（同一名多处引用只计一次）。

用法：
    python scripts/check_env_budget.py             # 本地：检查 + 新名自动登记
    python scripts/check_env_budget.py --check     # CI：只检查不写（阻断未登记新增）

退出码：0 = 无未登记新增（本地模式含成功登记）；1 = 存在未登记新增；
2 = 登记表解析错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = PROJECT_ROOT / "docs" / "env_budget.yaml"
# 扫描范围：产品开关面（src/ 全部 .py + 根 config.py）
SCAN_GLOBS = ["src/**/*.py", "config.py"]

# 静态提取模式（按匹配优先级；同名去重）。
# 注：字符类用 \x22（双引号）/ \x27（单引号）十六进制转义——避免在
# Python 字符串字面量里嵌套两种引号转义（r"..." 内 \" 的可读性陷阱）。
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "os.getenv/environ.get/environ[]/setdefault",
        re.compile(
            r"os\.environ\.get\(\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]"
            r"|os\.getenv\(\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]"
            r"|os\.environ\[\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]\s*\]"
            r"|os\.environ\.setdefault\(\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]"
        ),
    ),
    (
        "模块级 _ENV* 常量（os.getenv(_ENV) 间接引用）",
        re.compile(r"^_ENV[A-Z0-9_]*\s*=\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]", re.MULTILINE),
    ),
]


def scan_env_names() -> set[str]:
    """扫描产品开关面，返回唯一环境变量名集合。"""
    names: set[str] = set()
    files: list[Path] = []
    for pattern in SCAN_GLOBS:
        files.extend(PROJECT_ROOT.glob(pattern))
    for path in sorted(set(files)):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for _, regex in _PATTERNS:
            for m in regex.finditer(text):
                # 多分支模式取第一个非 None 组
                name = next(g for g in m.groups() if g is not None)
                names.add(name)
    return names


def load_registered() -> set[str]:
    """解析登记表（'- NAME' 行格式，与 coverage_ratchet 同避 yaml 依赖）。"""
    if not STATE_FILE.exists():
        return set()
    registered: set[str] = set()
    for raw in STATE_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("- "):
            registered.add(line[2:].strip())
    return registered


def write_registered(names: set[str]) -> None:
    """写回登记表（计数 + 排序名单，diff 友好）。"""
    lines = [
        "# X3 环境变量开关预算登记表（scripts/check_env_budget.py 读写，新增须显式登记）",
        "#",
        "# 规则：本地运行 check_env_budget.py（无 --check）发现新名自动登记写回，",
        "# 由贡献者随改动提交——'登记'即'修改本文件'，PR diff 强制可见（P0-5 冻结决策）。",
        "# CI 以 --check 模式阻断未登记新增；删名允许（表随之收缩）。",
        f"env_total: {len(names)}",
        "names:",
    ]
    lines.extend(f"  - {n}" for n in sorted(names))
    STATE_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="环境变量开关预算守卫（X3/P0-5）")
    parser.add_argument("--check", action="store_true", help="CI 模式：只检查不写（阻断未登记新增）")
    args = parser.parse_args()

    scanned = scan_env_names()
    registered = load_registered()
    if STATE_FILE.exists() and not registered:
        print(f"[env-budget] 错误：登记表存在但解析出 0 个名字（格式损坏？{STATE_FILE}）", file=sys.stderr)
        return 2

    unregistered = scanned - registered
    removed = registered - scanned

    print(
        f"[env-budget] 扫描产品开关面（src/ + config.py）：{len(scanned)} 个唯一环境变量；登记表 {len(registered)} 个"
    )
    if removed:
        print(f"[env-budget] 已移除（登记表将收缩）：{sorted(removed)}")
    if not unregistered:
        if removed and not args.check:
            write_registered(scanned)
            print(f"[env-budget] 登记表已收缩至 {len(scanned)} 个名字")
        print("[env-budget] 通过：无未登记新增")
        return 0

    print(f"[env-budget] 未登记新增 {len(unregistered)} 个：{sorted(unregistered)}", file=sys.stderr)
    if args.check:
        print(
            "[env-budget] 阻断：新增环境变量须先本地运行 `python scripts/check_env_budget.py` "
            "登记到 docs/env_budget.yaml 并随改动提交（P0-5 冻结决策：新开关 = 显式 PR 动作）",
            file=sys.stderr,
        )
        return 1
    write_registered(scanned)
    print(f"[env-budget] 已自动登记 {len(unregistered)} 个新名（随改动提交 docs/env_budget.yaml）")
    print(f"[env-budget] 登记表更新：{len(registered)} → {len(scanned)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
