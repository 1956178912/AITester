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

CB 轮（2026-10-23）：**审计面本身必须被披露**。本门禁的判定面只有
「就地赋值 `state["k"] = ...` + `state.get/state[]` 字面读写」；LangGraph 的规范
写侧是节点返回局部更新 dict（`return {"k": v}`），实测 45 键 / 95 站点完全不在
判定面内——而 docstring 背景里点名的静默丢弃事故（M14 / O35）正是这条路径。
旧成功语句「无未声明键读写」于是把「判过且干净」与「压根没看」说成同一件事。
本轮只加披露、不动判定：`channel_coverage()` 一次遍历算出 声明键 → 读 / 就地写 /
update dict 写 的三向覆盖，未触及键再按「扫描面之外有无字面」分成两类，成功时
逐条打印；`--coverage` 输出逐键表。实测：声明 118 键，读侧 57 键 / 353 站点，
就地写 2 键 / 11 站点，update dict 45 键 / 95 站点，未触及 35 键（34 个在
tests/experiments/scripts 有字面、**1 个全仓零字面**：`failure_frequency_applied`——
声明处注释写「_debugger_node 写入 True」，实际全仓无写者，实验分析侧拿到的恒 None）。

CB 的第二个发现是**自指**：上面这句披露在本 docstring 里写下了死键字面，守卫测试
也硬编码该字面用于断言——首版 `_outside_literal_blob()` 把这两处算作「别处有出现」，
于是 `untouched_nowhere` 由 1 变 0，门禁用自己的披露文本把自己的结论证伪。现按
`_apparatus_paths()` 排除测量装置（本模块 + 直接 import 本模块的测试模块）后再分类；
排除面精确到模块级导入（`from scripts.gates import other` 不算），已加锁。

DS 轮（2026-10-26）重登记：CLI 崩溃结果与成功结果键集合同构后，
`src/cli/app.py::_make_task_error_result` 直接返回的结果 dict 让两个字面声明键
（`coverage_threshold` / `max_iterations`）进入 update dict 计数——实测 47 键 /
99 站点、未触及 34 键（33 有字面 / 1 零字面）、未审计 46 键。新增的 2 键 / 4 站点
是 CLI 呈现层的结果 dict，**不是状态节点写**，正是本条「普通 dict 与状态更新同形」
的已知噪声；判定面与通过/失败口径一处未改，仅按棘轮重登记读数。

用法：
    python scripts/gates/check_state_contract.py            # 审计，违规 exit 1
    python scripts/gates/check_state_contract.py --list     # 仅打印声明键集
    python scripts/gates/check_state_contract.py --coverage # 逐键覆盖表 + 审计面披露
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import Counter
from pathlib import Path
from typing import NamedTuple

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
#: CB 轮（2026-10-23）：判断「声明键在扫描面之外还有没有字面出现」时的对照面。
#: 只读文本，不扩充审计面——tests/ experiments/ 本就不在扫描面内（见 docstring 豁免口径）。
_OUTSIDE_ROOTS = ("tests", "experiments", "scripts")
#: LangGraph 的**规范写侧**：节点返回局部更新 dict（`return {"k": v}`）或对 update
#: dict 调 update/merge。CB 轮实测：本门禁只审就地赋值，不审这两条路径——故它们
#: 只进披露、不进判定（加入判定会把辅助函数的普通 dict 返回值误判为状态写）。
_UPDATE_MERGE_ATTRS = frozenset({"update", "merge"})


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


class ChannelCoverage(NamedTuple):
    """状态通道「声明面 vs 审计面」普查结果（CB 轮 2026-10-23）。

    NamedTuple 而非 dataclass 是刻意的：历史测试用 `spec_from_file_location`
    加载本模块且不登记 `sys.modules`，`@dataclass` 在 Python 3.14 的
    `dataclasses._is_type` 里会走到 `sys.modules.get(...).__dict__` 而抛
    AttributeError（CA 轮实测并锁在 test_gate_imports_without_sys_modules_registration）。
    """

    declared: tuple[str, ...]
    read_keys: tuple[str, ...]
    read_sites: int
    inplace_write_keys: tuple[str, ...]
    inplace_write_sites: int
    update_write_keys: tuple[str, ...]
    update_write_sites: int
    foreign_update_keys: int
    untouched: tuple[str, ...]
    untouched_elsewhere: tuple[str, ...]
    untouched_nowhere: tuple[str, ...]
    temp_keys: int
    temp_sites: int
    dynamic_sites: int
    undeclared_sites: int

    @property
    def written_keys(self) -> tuple[str, ...]:
        """任一写形态（就地赋值 ∪ update dict）触及的声明键。"""
        return tuple(sorted(set(self.inplace_write_keys) | set(self.update_write_keys)))

    @property
    def unaudited_write_keys(self) -> tuple[str, ...]:
        """update dict 侧可见、就地写/读判定面失明的声明键。

        与普通结果 dict 同形，故含不可静态归属的噪声（如 CLI 结果 dict 携带的
        `coverage_threshold` / `max_iterations`），只披露不判定。
        """
        return tuple(sorted(set(self.update_write_keys) - set(self.inplace_write_keys)))


class _Usage(NamedTuple):
    """单次遍历的逐键计数（Counter 语义：键 → 站点数）。"""

    read: Counter[str]
    inplace: Counter[str]
    update: Counter[str]
    temp: Counter[str]
    foreign_update: int
    dynamic_sites: int
    undeclared_sites: int


def _walk_channel_usage(paths: list[Path], declared: set[str]) -> _Usage:
    """与 `_audit_file` 同口径地走一遍，但只计数不判定。

    三形态：就地赋值 `state["k"] = ...`、读 `state.get("k")` / `state["k"]`、
    update dict（`return {"k": ...}` 与 update/merge 的 dict 实参）。
    update dict 只统计**已声明键**——普通函数返回的 dict 与状态更新同形，
    未声明键无法归属（CB 轮实测 898 处、DS 轮 922 处），计数会把噪声说成覆盖面。
    """
    read: Counter[str] = Counter()
    inplace: Counter[str] = Counter()
    update: Counter[str] = Counter()
    temp: Counter[str] = Counter()
    foreign = dynamic = undeclared = 0

    def note(key: str | None, bucket: Counter[str]) -> None:
        nonlocal dynamic, undeclared
        if key is None:
            dynamic += 1
        elif key.startswith("_"):
            temp[key] += 1
        elif key in declared:
            bucket[key] += 1
        else:
            undeclared += 1

    for path in paths:
        tree = ast.parse(Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for tgt in targets:
                    if isinstance(tgt, ast.Subscript) and _is_state_var(tgt.value):
                        note(_literal_key(tgt.slice), inplace)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "get" and _is_state_var(node.func.value):
                    note(_literal_key(node.args[0]) if node.args else None, read)
                elif node.func.attr in _UPDATE_MERGE_ATTRS:
                    for arg in node.args:
                        if isinstance(arg, ast.Dict):
                            for k in arg.keys:
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    key = k.value
                                    if key.startswith("_"):
                                        temp[key] += 1
                                    elif key in declared:
                                        update[key] += 1
                                    else:
                                        foreign += 1
            elif isinstance(node, ast.Subscript) and not isinstance(node.ctx, ast.Store) and _is_state_var(node.value):
                note(_literal_key(node.slice), read)
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        key = k.value
                        if key.startswith("_"):
                            temp[key] += 1
                        elif key in declared:
                            update[key] += 1
                        else:
                            foreign += 1
    return _Usage(read, inplace, update, temp, foreign, dynamic, undeclared)


def _module_dotted_name() -> str:
    """本模块的点分名（不受 `__main__` 调用方式影响），用于识别「谁在 import 门禁」。"""
    rel = Path(__file__).resolve().relative_to(PROJECT_ROOT).with_suffix("")
    return ".".join(rel.parts)


def _imports_module(tree: ast.Module, dotted: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module == dotted:
                return True
            if node.module and any(f"{node.module}.{a.name}" == dotted for a in node.names):
                return True
        elif isinstance(node, ast.Import):
            if any(alias.name == dotted for alias in node.names):
                return True
    return False


def _apparatus_paths() -> set[Path]:
    """测量装置自身：本模块 + 直接 import 它的测试模块。

    CB 轮实测踩到的自指缺陷：本模块 docstring 点名了死键
    `failure_frequency_applied`，守卫测试也硬编码该字面用于断言——若把这两处
    算作「该键在别处还有出现」，门禁就会用自己的披露文本把自己的结论证伪
    （实测 untouched_nowhere 由 1 变 0）。装置提到键名是披露/断言，不是消费者。
    """
    paths = {Path(__file__).resolve()}
    dotted = _module_dotted_name()
    tests_dir = PROJECT_ROOT / "tests"
    if tests_dir.is_dir():
        for p in sorted(tests_dir.rglob("test_*.py")):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
            except SyntaxError:
                continue
            if _imports_module(tree, dotted):
                paths.add(p.resolve())
    return paths


def _outside_literal_blob() -> str:
    """扫描面之外（tests/ experiments/ scripts/）的源码文本——只用于「还有没有字面」。

    排除测量装置（见 `_apparatus_paths`），否则门禁的自我披露会被当作用例证据。
    """
    skip = _apparatus_paths()
    parts: list[str] = []
    for rel_root in _OUTSIDE_ROOTS:
        root = PROJECT_ROOT / rel_root
        if root.is_dir():
            for p in sorted(root.rglob("*.py")):
                if p.resolve() in skip:
                    continue
                parts.append(p.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(parts)


def channel_coverage() -> ChannelCoverage:
    """一次性算出审计面覆盖：声明键 → 读 / 就地写 / update dict 写，及未触及键。

    未触及 ⇒ 再看扫描面之外有没有字面出现，把「只是不在判定面」与
    「全仓无人使用」分开——两者在「无未声明键读写」这句成功语句下同形。
    """
    declared = declared_state_keys()
    usage = _walk_channel_usage(scan_files(), declared)
    non_temp = {k for k in declared if not k.startswith("_")}
    touched = set(usage.read) | set(usage.inplace) | set(usage.update)
    untouched = tuple(sorted(non_temp - touched))
    outside = _outside_literal_blob()
    elsewhere = tuple(k for k in untouched if f'"{k}"' in outside or f"'{k}'" in outside)
    nowhere = tuple(k for k in untouched if k not in elsewhere)
    return ChannelCoverage(
        declared=tuple(sorted(declared)),
        read_keys=tuple(sorted(usage.read)),
        read_sites=sum(usage.read.values()),
        inplace_write_keys=tuple(sorted(usage.inplace)),
        inplace_write_sites=sum(usage.inplace.values()),
        update_write_keys=tuple(sorted(usage.update)),
        update_write_sites=sum(usage.update.values()),
        foreign_update_keys=usage.foreign_update,
        untouched=untouched,
        untouched_elsewhere=elsewhere,
        untouched_nowhere=nowhere,
        temp_keys=len(usage.temp),
        temp_sites=sum(usage.temp.values()),
        dynamic_sites=usage.dynamic_sites,
        undeclared_sites=usage.undeclared_sites,
    )


def coverage_lines(cov: ChannelCoverage) -> list[str]:
    """成功路径的审计面披露（CB 轮）：把「判定面覆盖了什么」写进同一句成功信息。"""
    return [
        f"  审计面披露：声明 {len(cov.declared)} 键；读侧 {len(cov.read_keys)} 键 / {cov.read_sites} 站点；"
        f"未触及声明键 {len(cov.untouched)} 个",
        f"  写侧判定面：就地赋值 {len(cov.inplace_write_keys)} 键 / {cov.inplace_write_sites} 站点；"
        f"未判定的 update dict {len(cov.update_write_keys)} 键 / {cov.update_write_sites} 站点"
        f"（LangGraph 规范写侧，只披露不判定）",
        f"  未触及声明键：{len(cov.untouched_elsewhere)} 个在 {' / '.join(_OUTSIDE_ROOTS)} 有字面出现，"
        f"{len(cov.untouched_nowhere)} 个全仓零字面（{', '.join(cov.untouched_nowhere) or '无'}）",
        f"  面外计数：下划线临时键 {cov.temp_keys} 个 / {cov.temp_sites} 站点；动态键 {cov.dynamic_sites} 站点；"
        f"未声明键 {cov.undeclared_sites} 站点；update dict 中非声明键 {cov.foreign_update_keys} 处（与普通 dict 无法区分，不计入覆盖）",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="LangGraph 状态通道契约静态守卫（P1-6）")
    parser.add_argument("--list", action="store_true", help="仅打印声明键集与扫描范围")
    parser.add_argument("--coverage", action="store_true", help="打印逐键审计面覆盖表（CB 轮）")
    args = parser.parse_args()

    declared = declared_state_keys()
    if args.list:
        print(f"AITesterState 声明键 {len(declared)} 个：")
        for k in sorted(declared):
            print(f"  {k}")
        files = scan_files()
        print(f"扫描面：{', '.join(SCAN_ROOTS)}/ 全树递归，共 {len(files)} 个 .py 文件")
        return

    if args.coverage:
        cov = channel_coverage()
        usage = _walk_channel_usage(scan_files(), declared)
        print(f"状态通道逐键覆盖（声明 {len(cov.declared)} 键；read / 就地写 / update dict 写）：")
        for key in cov.declared:
            print(f"  {key}: {usage.read[key]} / {usage.inplace[key]} / {usage.update[key]}")
        for line in coverage_lines(cov):
            print(line)
        return

    violations: list[tuple[str, int, str, str]] = []
    files = scan_files()
    for p in files:
        violations.extend(_audit_file(p, declared))

    if not violations:
        print(f"状态通道契约审计通过：{len(files)} 个文件（{', '.join(SCAN_ROOTS)}/ 全树）无未声明键读写")
        for line in coverage_lines(channel_coverage()):
            print(line)
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
