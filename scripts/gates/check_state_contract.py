#!/usr/bin/env python
"""P1-6（2026-10-05 独立审查）：LangGraph 状态通道契约静态守卫。

背景：AITesterState（TypedDict）是 LangGraph 的 channel 白名单——节点
update dict / 节点内 state 写点中**未声明的键会被 LangGraph 静默丢弃**
（M14 四键、O35 三键等历史事故同类根因），写入方"以为写了"，读取方
恒 None。本脚本做静态差集审计，CI 阻断：

1. 从 src/graph/state.py 运行时导入 AITesterState.__annotations__ 键集；
2. AST 扫描 `src/` 全树（rglob，新增模块自动纳管）：
   - ``state["k"] = ...`` 下标赋值（含 cast 到 dict 的别名变量，按
     "变量名含 state"启发式识别）——k 必须已声明或以 "_" 开头
     （模块内临时键约定，state.py 注释口径）；
   - ``state.get("k")`` / ``state["k"]`` 读取——k 必须已声明（读取未声明
     键恒 None，正是"写不进 + 读不到"静默链的读侧）；
3. 未声明键输出到 stdout，exit 1。

G3（2026-10-16）扩容理由：旧扫描面是硬编码的两个文件（nodes.py / workflow.py），
与本 docstring 自称的 "src/graph/*.py" 不符；而当年真实存在的断链在**图外**——
observability/failure_taxonomy.py 读顶层 ``logic_degraded``，写侧却只写进
``test_plan`` 内部且该键从未声明，门禁因此对着缺陷全绿。扫描面过窄本身就是一种
假绿，故改为递归 glob（实测 132 文件 0.15s，零存量违规）。

豁免口径（--print 键清单随附）：
- 下划线前缀键：节点内临时传递约定（如 _1_3_contract_missing），
  不进 channel（node 侧 pop 消费），豁免；
- tests/ / experiments/ 不扫（构造 fixture 自由）。

用法：
    python scripts/gates/check_state_contract.py            # 审计，违规 exit 1
    python scripts/gates/check_state_contract.py --list     # 仅打印声明键集
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# G3（2026-10-16）扩容：扫描面从硬编码两个文件（nodes.py / workflow.py）扩到
# **整个 src/ 树**。理由：状态的读侧散落在图外——本轮发现的断链正是
# src/observability/failure_taxonomy.py 读顶层 `logic_degraded`（写侧只写进
# test_plan 内部、键也从未在 AITesterState 声明），旧扫描面不覆盖该文件，
# 于是门禁对着真实缺陷全绿（旧 docstring 还自称扫 src/graph/*.py，与实际不符）。
# 实测扩容成本：132 个文件 0.15s、零存量违规（2026-10-16）。
# 误报口径：宿主变量名启发式（见 _STATE_VAR_HINTS）可能命中与 LangGraph 通道
# 无关的同名局部 dict——此时按"改名或改用下划线前缀临时键"处置，不放宽容差。
SCAN_ROOTS = ("src",)
_STATE_VAR_HINTS = ("state", "_state")  # 变量名启发式：state / cast 后别名


def scan_files() -> list[Path]:
    """实际扫描面：SCAN_ROOTS 下全部 .py（glob 递归，新增模块自动纳管）。"""
    found: list[Path] = []
    for rel_root in SCAN_ROOTS:
        root = PROJECT_ROOT / rel_root
        if root.is_dir():
            found.extend(sorted(root.rglob("*.py")))
    return found


def _rel(path: str | Path) -> str:
    """显示名：仓库内用相对路径，仓库外（测试 tmp_path）退化为原样。"""
    p = Path(path)
    try:
        return str(p.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(p)


def declared_state_keys() -> set[str]:
    """运行时读取 AITesterState 的声明键集（TypedDict annotations）。"""
    from src.graph.state import AITesterState

    return set(AITesterState.__annotations__)


def _is_state_var(node: ast.AST) -> bool:
    """判定下标/get 的宿主表达式是否疑似 state 通道变量。

    口径：变量名精确为 "state"，或以 "state" 为前缀的 cast 别名
    （如 _state_pop）；避免把任意 dict 字面量误伤。
    """
    if isinstance(node, ast.Name):
        return node.id in _STATE_VAR_HINTS or node.id.startswith("_state")
    return False


def _audit_file(path: Path, declared: set[str]) -> list[tuple[str, int, str, str]]:
    """审计单文件，返回 (file, lineno, kind, key) 违规列表。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    violations: list[tuple[str, int, str, str]] = []

    for node in ast.walk(tree):
        # 1) 下标赋值：state["k"] = ...
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for tgt in targets:
                if isinstance(tgt, ast.Subscript) and _is_state_var(tgt.value):
                    key = _literal_key(tgt.slice)
                    if key and not _allowed(key, declared):
                        violations.append((str(path), node.lineno, "write", key))
        # 2) 读取：state.get("k") / state["k"]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "get" and _is_state_var(node.func.value):
                key = _literal_key(node.args[0]) if node.args else None
                if key and not _allowed(key, declared):
                    violations.append((str(path), node.lineno, "get", key))
        elif isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Store) and _is_state_var(node.value):
            key = _literal_key(node.slice)
            if key and not _allowed(key, declared):
                violations.append((str(path), node.lineno, "read", key))
    return violations


def _literal_key(slice_node: ast.AST) -> str | None:
    """下标切片为字符串字面量时返回键名，否则 None（动态键不审计）。"""
    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
        return slice_node.value
    return None


def _allowed(key: str, declared: set[str]) -> bool:
    """键是否豁免：已声明，或下划线前缀（节点内临时传递约定）。"""
    return key in declared or key.startswith("_")


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph 状态通道契约静态守卫（P1-6）")
    parser.add_argument("--list", action="store_true", help="仅打印声明键集与扫描范围")
    args = parser.parse_args()

    declared = declared_state_keys()
    if args.list:
        print(f"AITesterState 声明键 {len(declared)} 个：")
        for k in sorted(declared):
            print(f"  {k}")
        files = scan_files()
        print(f"扫描面：{', '.join(SCAN_ROOTS)}/ 全树递归，共 {len(files)} 个 .py 文件")
        return

    violations: list[tuple[str, int, str, str]] = []
    files = scan_files()
    for p in files:
        violations.extend(_audit_file(p, declared))

    if not violations:
        print(f"状态通道契约审计通过：{len(files)} 个文件（{', '.join(SCAN_ROOTS)}/ 全树）无未声明键读写")
        return

    print(f"❌ 状态通道契约违规 {len(violations)} 处（未声明键会被 LangGraph 静默丢弃）：")
    for f, lineno, kind, key in violations:
        print(f'  {_rel(f)}:{lineno} [{kind}] "{key}"')
    print(
        "\n修复口径：声明键加入 src/graph/state.py AITesterState（含 create_initial_state 默认值）；"
        "\n节点内临时传递键改用下划线前缀（_xxx）约定。"
    )
    raise SystemExit(1)


if __name__ == "__main__":
    main()
