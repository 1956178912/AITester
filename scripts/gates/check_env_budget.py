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
      os.environ.setdefault("X", ...) / env_flag("X") / env_flag_opt_out("X") /
      env_int("X") / env_float("X") / _parse_int_env("X") / _parse_float_env("X") /
      模块级名字含 ENV 的常量（_ENV_X、_X_ENV、_X_ENV_VAR 三式均收）；
      动态拼接（os.getenv(f"...") ）提取不到——已知漏网面，登记表是
      名字集合而非完备性证明；
    - 计数口径：唯一名字数（同一名多处引用只计一次）。

用法：
    python scripts/gates/check_env_budget.py             # 本地：检查 + 新名自动登记
    python scripts/gates/check_env_budget.py --check     # CI：只检查不写（阻断未登记新增）

退出码：0 = 无未登记新增（本地模式含成功登记）；1 = 存在未登记新增；
2 = 登记表解析错误。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = PROJECT_ROOT / "docs" / "env_budget.yaml"
# 扫描范围：产品开关面（src/ 全部 .py + 根 config.py）
SCAN_GLOBS = ["src/**/*.py", "config.py"]
# Q-1（2026-10-18）：**人工登记**（不是扫描盲区静默豁免）——该键由 Q-3 的
# experiments/postprocess_wall.py 消费；扫描面刻意不含 experiments/（实验脚本
# 不属产品开关矩阵），故在登记表保留但不在扫描结果里。若不加此集合，本地模式
# 会把登记表收缩掉该行（CI --check 虽不阻断，但"显式登记"语义丢失）。
# 仅登记展示键，**不改变**产品开关扫描/阻断逻辑。
MANUALLY_REGISTERED: frozenset[str] = frozenset({"AITESTER_POSTPROCESS_WARN_S"})

# 静态提取模式（按匹配优先级；同名去重）。
# 注：字符类用 \x22（双引号）/ \x27（单引号）十六进制转义——避免在
# Python 字符串字面量里嵌套两种引号转义（r"..." 内 \" 的可读性陷阱）。
#
# 2026-10-16 C 轮：布尔开关解析收敛至 src/utils/env_utils.py::env_flag 后，
# 新增 env_flag("NAME") 字面量形态——不收该形态则新引用方式的开关将绕过
# 本门禁的预算治理（ADR-0003 纪律的隐性缺口）。env_flag(_ENV) 间接引用
# 由下方常量模式覆盖。
#
# 2026-10-16 F 轮（盲区修复）：常量形态此前只认 `_ENV*` **前缀式**，而仓内
# 另有 19 个开关以**后缀式**常量声明（`_TRACE_ENV_VAR = "AITESTER_TRACE_DIR"`
# 于 src/observability/trace.py:55、`_CROSS_FILE_ENV_VAR`、`_SLEEP_ENV`、
# `_EMBEDDING_BACKEND_ENV`、`_ORACLE_CONTEXT_TIER_ENV` 等），门禁既扫不到、
# 也永不报红——`--check` 输出 "194/194 通过" 属**假绿**：这些名字对
# ADR-0003 预算治理完全不可见。现放宽为"名字含 ENV 的模块级字符串常量"，
# 三式（前缀/后缀/双段）一并覆盖。同批把 env_flag 形态扩为
# `env_(?:flag|int)`：**刻意不加左词界**——如此可同时覆盖各模块自建的
# 同族包装器（如 src/tools/feedback_compression.py::_clamp_env_int，其字面
# 名此前同样不可见）；F 轮引入 env_utils.env_int 后该形态即为正向覆盖。
# 合计新扫出 25 个真名（194 → 219），逐个人工核实均有实际取用点、零误报。
#
# 2026-10-17 J-2（同族盲区二次复现，务必按"每新增一个取用口径就回来加分支"
# 理解为长期纪律而非一次性补票）：env_utils 布尔口径收敛新增 `env_flag_opt_out`、
# 数值同族新增 `env_float`（含各模块自建 `_env_float` 包装器，靠"无左词界"顺带
# 覆盖）后，旧模式 `env_(?:flag|int)\(` **匹配不到**这两式——括号必须紧跟 flag/int，
# 而 `env_flag_opt_out(` 在 flag 后是 `_`。即 10 个刚收敛的守卫开关会静默脱离
# ADR-0003 治理。同批补 config.py 自建的钳制解析式 `_parse_(?:int|float)_env(`：
# 该族此前完全不可见，`EXECUTION_TIMEOUT`/`MAX_ITERATIONS`/`MYSQL_PORT`/
# `TEMPERATURE` 等 24 个真实产品旋钮从未进过登记表（与 F 轮"194/194 假绿"同因）。
# 两式合计 219 → 248，新增名字逐个核实均有实际取用点。
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
        'env_flag/env_flag_opt_out/env_int/env_float("NAME") 单一事实源调用（2026-10-16 C/F 轮、2026-10-17 J-2 收敛后形态）',
        re.compile(r"env_(?:flag_opt_out|flag|int|float)\(\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]"),
    ),
    (
        "模块级名字含 ENV 的字符串常量（os.getenv(_X_ENV) 间接引用）",
        re.compile(
            r"^_?[A-Z0-9_]*ENV[A-Z0-9_]*\s*=\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]",
            re.MULTILINE,
        ),
    ),
    (
        'config.py::_parse_int_env/_parse_float_env("NAME") 钳制解析（2026-10-17 J-2 补）',
        re.compile(r"_parse_(?:int|float)_env\(\s*[\x22\x27]([A-Z][A-Z0-9_]+)[\x22\x27]"),
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
        "# X3 环境变量开关预算登记表（scripts/gates/check_env_budget.py 读写，新增须显式登记）",
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
    registered = load_registered() | set(MANUALLY_REGISTERED)
    if STATE_FILE.exists() and not registered:
        print(f"[env-budget] 错误：登记表存在但解析出 0 个名字（格式损坏？{STATE_FILE}）", file=sys.stderr)
        return 2

    unregistered = scanned - registered
    removed = registered - scanned - set(MANUALLY_REGISTERED)

    print(
        f"[env-budget] 扫描产品开关面（src/ + config.py）：{len(scanned)} 个唯一环境变量；登记表 {len(registered)} 个"
    )
    if removed:
        print(f"[env-budget] 已移除（登记表将收缩）：{sorted(removed)}")
    if not unregistered:
        if removed and not args.check:
            write_registered(scanned | set(MANUALLY_REGISTERED))
            print(f"[env-budget] 登记表已收缩至 {len(scanned)} 个名字")
        print("[env-budget] 通过：无未登记新增")
        return 0

    print(f"[env-budget] 未登记新增 {len(unregistered)} 个：{sorted(unregistered)}", file=sys.stderr)
    if args.check:
        print(
            "[env-budget] 阻断：新增环境变量须先本地运行 `python scripts/gates/check_env_budget.py` "
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
