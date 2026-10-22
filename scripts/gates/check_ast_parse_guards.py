"""AST 可读性守卫的捕获面棘轮（BK 轮，2026-10-22；CI 阻断项）。

背景（缺陷族 F03 静态侧的第八个消费面）：
    BI 轮把"静态检查的可测量性"收敛成单一事实源 ``src/utils/check_status.py``，
    BJ 轮补了第四个消费者，但**词表只管"结论可不可信"，没管"守卫自己捕不捕得住"**。
    本守卫自己实测（对 HEAD 树）：``src/`` 78 个含 ``ast.parse`` 的 try 站点中
    35 个只捕 ``SyntaxError``——``ast.parse`` 还会抛 ``ValueError`` 族（孤立代理位 ⇒
    ``UnicodeEncodeError``），单腿守卫会让它从"读不懂 ⇒ 降级"分支里**抛穿到调用方**。
    更糟的是：逐点手工收敛（BG/BI/BJ 各改一个模块）永远不会收敛完，且新代码随时
    可以再写一个单腿守卫而无人拦截——这正是 BJ 手册 §7 按名登记的那条候选。
    （BK 轮开工普查曾给出"全仓 125 站点 / 60 单腿 / src 33"：该脚本的分类规则现已
    不可复现，且与守卫口径不同（守卫按 try 站点计、按"能否接住 ValueError 族"判）。
    **以本守卫自测数为准**，勘误登记于 BK 手册 §2；差值不强行归因。）

本守卫（纯 stdlib AST 扫描，零新依赖）：
    1. 扫描 ``src/**/*.py`` 中所有"``try`` 语句子树内直接调用 ``ast.parse``"的站点
       （含 handler/else/finally 内的调用——在 handler 里再解析同样会抛穿；站点按
       ``try`` 计，一处 ``try`` 里多个解析算一个站点）；
    2. 解析该 try 的 except 处理器能否接住**整个** ValueError 族——名字来源三处：
       同模块的元组常量赋值、``from src.utils.check_status import
       AST_UNREADABLE_ERRORS`` 这类**共享常量的真实运行时取值**、以及裸 except /
       ``Exception``。合格性用 ``issubclass(ValueError, cls)`` 判，只接
       ``UnicodeEncodeError`` 这种子类**不算**合格（ValueError 族成员不止一个）；
    3. 不合格 ⇒ 违规；命中 EXEMPT 额度（"文件::函数名" → (站点数, 折叠形态)）按站点
       放行，超出额度或未登记 ⇒ 退出码 1 阻断。

棘轮口径：EXEMPT 是**存量清单**，只允许变短。新增单腿守卫直接失败；把存量守卫
收敛到共享口径后必须同时删除对应条目或改小登记数——命中数为 0（失效条目）或
少于登记数（条目偏大）同样失败。豁免的是"这条分支现在折叠成了什么"这一事实，
不是"这里永远可以不看"。

CLI：
    python scripts/gates/check_ast_parse_guards.py            # 全 src 扫描（CI 阻断口径）
    python scripts/gates/check_ast_parse_guards.py --list     # 只列违规，退出码恒 0
    python scripts/gates/check_ast_parse_guards.py --all      # 连 experiments/ scripts/ 一起报（仅报告，不阻断）
"""

from __future__ import annotations

import argparse
import ast
import builtins
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SRC_DIR = REPO_ROOT / "src"
EXTRA_DIRS = ("experiments", "scripts")
#: 工件目录：里面是**被测产物/历史结果**而非仓库源码，其语法错误正是被读的对象，
#: 扫它们只会把"归档里确实存在读不懂的代码"误报成"守卫写错了"。
SKIP_DIR_PARTS = ("results", "__pycache__")

#: 共享常量的真实取值在此解析（而不是把 ``AST_UNREADABLE_ERRORS`` 硬编码成
#: "看起来像异常名"）——门禁与词表同源，词表加了腿门禁自动跟上。
sys.path.insert(0, str(REPO_ROOT))
from src.utils.check_status import AST_UNREADABLE_ERRORS  # noqa: E402

#: 视为"覆盖 ValueError 族"的名字（含裸 except 与 Exception 兜底）。
_CATCH_ALL = {"BARE", "Exception", "BaseException"}
#: 共享常量别名 → 真实运行时取值（词表加了腿，门禁自动跟上，不必改这里）。
_SHARED_EXCEPTION_ALIASES: dict[str, tuple[str, ...]] = {
    "AST_UNREADABLE_ERRORS": tuple(cls.__name__ for cls in AST_UNREADABLE_ERRORS)
}

#: 存量单腿守卫豁免（BK 轮登记，键 = "相对 src/ 的路径::函数名"，值 = (站点数, 折叠形态)）。
#: 口径：本轮（BK）收敛的是**判定面可达**的 5 个模块 13 站点
#: （deterministic_repair / cross_file / expert_pool / patch_intent / multi_candidate，
#: 其中 multi_candidate 由 BK 的回归锁以孤立代理位候选**当场抓到现场抛穿**），
#: BJ 另收敛 oracle_validator 2 站点；HEAD 的 35 处未覆盖 ⇒ 现存 20 处全部按名登记。
#: **额度是站点数而不是函数名**——在已豁免函数里再加一个新单腿守卫同样会违规；
#: 命中数少于登记数则说明条目偏大，同样失败（棘轮只允许变短）。
#: 这些不是"永久豁免"：逐个都要配套"读不懂 ⇒ 空结果"的消费面披露才能收，
#: 已作为 BK 手册 §7 的下一轮候选按名登记。
EXEMPT: dict[str, tuple[int, str]] = {
    "agents/deterministic_guard.py::scan_test_file": (1, "测试文件读不懂⇒空报告（守卫放行）"),
    "agents/fault_localizer.py::build_gold_injection_localization": (1, "读不懂⇒定位 None（保守降级）"),
    "agents/fault_localizer.py::gold_changed_functions": (1, "读不懂⇒{'<module>'}（整模块视为变更）"),
    "agents/fault_localizer.py::patch_changed_functions": (1, "同上（整模块视为变更）"),
    "agents/generator.py::_extract_existing_assertions": (1, "读不懂⇒[]（既有断言视为空）"),
    "agents/generator.py::_validate_parametrize": (1, "读不懂⇒False（fail-closed 方向已保守）"),
    "datasets/dataset_defects4j.py::_load_project_version": (1, "AST 计数失败⇒回退 regex 口径（分母换口径不标注）"),
    "datasets/dataset_realbugs.py::_count_test_functions": (1, "同上（实测 QuixBugs 84 文件 0 分歧 / 0 读不懂）"),
    "datasets/dataset_realbugs.py::_first_top_level_function": (1, "读不懂⇒None（suggested_function 缺位）"),
    "datasets/dataset_ult.py::_first_function_name": (1, "读不懂⇒合成名 func{N}（归档 4805 站点 0 实例）"),
    "tools/code_analyzer.py::replace_function_code": (2, "读不懂⇒(原码, False)（返回值带布尔位）"),
    "tools/hierarchical_summary.py::_extract_functions": (1, "读不懂⇒[]（上下文摘要缺位）"),
    "tools/hierarchical_summary.py::_extract_classes": (1, "读不懂⇒[]"),
    "tools/hierarchical_summary.py::_extract_module_symbols": (1, "读不懂⇒三键全空 dict"),
    "tools/patch_applier.py::_find_function_range_ast": (1, "读不懂⇒None（回落行级定位）"),
    "tools/patch_applier.py::safe_apply_patch": (1, "读不懂⇒(code, False)"),
    "tools/patch_localized.py::_function_ranges": (1, "读不懂⇒[]"),
    "tools/self_repair_trap.py::snapshot_test_quality": (1, "读不懂⇒tree=None（快照降级）"),
    "tools/testless_validation.py::_top_level_defs": (1, "读不懂⇒部分名字集"),
}


def _module_level_tuple_constants(tree: ast.Module) -> dict[str, list[str]]:
    """同模块内 ``X = (A, B)`` 形态的异常元组常量。"""
    out: dict[str, list[str]] = {}
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and node.targets
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Tuple)
        ):
            out[node.targets[0].id] = [ast.unparse(elt) for elt in node.value.elts]
    return out


def _handler_names(handler: ast.ExceptHandler, consts: dict[str, list[str]]) -> list[str]:
    """把 except 子句展开成异常类名列表（解析本地常量与共享常量别名）。"""
    if handler.type is None:
        return ["BARE"]
    if isinstance(handler.type, ast.Tuple):
        raw = [ast.unparse(elt) for elt in handler.type.elts]
    else:
        raw = [ast.unparse(handler.type)]
    names: list[str] = []
    for item in raw:
        names.extend(consts.get(item, [item]))
    return names


def _catches_whole_value_error_family(name: str) -> bool:
    """按**真实继承关系**判断某异常名能否接住整个 ValueError 族（不硬编码名单）。

    口径是 ``issubclass(ValueError, cls)``——只接住 ``UnicodeEncodeError`` 这类**子类**
    不算合格：``ast.parse`` 的 ValueError 族成员不止一个（孤立代理位是
    ``UnicodeEncodeError``、null 字节是 ``ValueError`` 本体），点状捕获会留新腿。
    查不到的名字（模块内自定义异常）按"不合格"处理，宁可多报让人去确认。
    """
    tail = name.rsplit(".", 1)[-1]
    if tail in _SHARED_EXCEPTION_ALIASES:
        return "ValueError" in _SHARED_EXCEPTION_ALIASES[tail]
    cls = getattr(builtins, tail, None)
    return isinstance(cls, type) and issubclass(cls, BaseException) and issubclass(ValueError, cls)


def _covers_value_error(names: list[str]) -> bool:
    return any(name in _CATCH_ALL or _catches_whole_value_error_family(name) for name in names)


def _enclosing_function(tree: ast.Module, lineno: int) -> str:
    funcs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.lineno <= lineno <= (node.end_lineno or 0)
    ]
    return max(funcs, key=lambda node: node.lineno).name if funcs else "<module>"


def _ast_parse_calls(node: ast.Try) -> list[ast.Call]:
    return [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Attribute)
        and call.func.attr == "parse"
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "ast"
    ]


def _iter_py_dirs(roots: list[Path]) -> list[Path]:
    """目录列表 → 待扫描 ``*.py``（剪掉 SKIP_DIR_PARTS 里任一路径段命中的文件）。"""
    out: list[Path] = []
    for root in roots:
        for path in sorted(root.rglob("*.py")):
            if set(path.relative_to(root).parts) & set(SKIP_DIR_PARTS):
                continue
            out.append(path)
    return out


def scan(paths: list[Path], root: Path = REPO_ROOT) -> tuple[list[tuple[str, str, str]], int, list[str]]:
    """返回 (违规项 [文件:行, 豁免键, except 文本], 守卫站点总数, 命中的 EXEMPT 键（可重复）)。

    命中键逐个返回（同一函数的多处豁免会重复出现）：棘轮要同时防三种漂移——
    新增单腿守卫（违规）、"豁免了但站点其实已收敛"（失效条目）、
    在已豁免函数里**再加**一处单腿守卫（超出登记额度 ⇒ 违规）。
    ``root`` 决定豁免键的前缀裁法，HEAD 内容对账（BK 手册 §2）据此把 HEAD 树
    解到临时目录后仍能得到与本轮同构的键。
    """
    violations: list[tuple[str, str, str]] = []
    exempt_hits: list[str] = []
    sites = 0
    for path in paths:
        rel = path.relative_to(root).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except (SyntaxError, ValueError, OSError) as exc:
            violations.append((rel, "<file>", f"门禁自身读不懂该文件：{type(exc).__name__}"))
            continue
        consts = _module_level_tuple_constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try) or not _ast_parse_calls(node):
                continue
            sites += 1
            names: list[str] = []
            for handler in node.handlers:
                names.extend(_handler_names(handler, consts))
            if _covers_value_error(names):
                continue
            key = f"{rel.removeprefix('src/') or rel}::{_enclosing_function(tree, node.lineno)}"
            quota = EXEMPT.get(key, (0, ""))[0]
            if key in EXEMPT and exempt_hits.count(key) < quota:
                exempt_hits.append(key)
                continue
            note = f"超出豁免额度 {quota} 处" if key in EXEMPT else "未登记豁免"
            violations.append((f"{rel}:{node.lineno}", f"{key}（{note}）", "|".join(names) or "(无 handler)"))
    return violations, sites, exempt_hits


def main() -> int:
    parser = argparse.ArgumentParser(description="AST 可读性守卫的捕获面棘轮（BK 轮）")
    parser.add_argument("--list", action="store_true", help="只列违规，不判退出码")
    parser.add_argument("--all", action="store_true", help="连 experiments/ scripts/ 一起扫描（仅报告，不阻断）")
    args = parser.parse_args()

    src_paths = _iter_py_dirs([SRC_DIR])
    violations, sites, exempt_hits = scan(src_paths)
    hits_by_key = Counter(exempt_hits)
    stale = sorted(key for key in EXEMPT if hits_by_key.get(key, 0) == 0)
    shrunk = sorted(
        f"{key}：登记 {quota} 处、实测 {hits_by_key.get(key, 0)} 处"
        for key, (quota, _) in EXEMPT.items()
        if 0 < hits_by_key.get(key, 0) < quota
    )

    print(
        f"扫描文件={len(src_paths)}  ast.parse 守卫站点={sites}  "
        f"未覆盖 ValueError 族={len(exempt_hits) + len(violations)}  "
        f"违规={len(violations)}  豁免命中={len(exempt_hits)}  EXEMPT 条目={len(EXEMPT)}"
    )
    for where, key, handlers in violations:
        print(f"  {where}  键={key}  except={handlers}")
    if stale:
        print(f"EXEMPT 失效条目（该站点已不再违规，请删除以收紧棘轮）={len(stale)}")
        for key in stale:
            print(f"  {key}")
    if shrunk:
        print(f"EXEMPT 登记数偏大（站点已减少，请同步改小）={len(shrunk)}")
        for line in shrunk:
            print(f"  {line}")
    if args.all:
        extra_paths = _iter_py_dirs([REPO_ROOT / d for d in EXTRA_DIRS])
        extra_violations, extra_sites, _ = scan(extra_paths)
        print(
            f"[仅报告] experiments/ + scripts/（不含 {', '.join(SKIP_DIR_PARTS)} 类目录）："
            f"扫描文件={len(extra_paths)} 守卫站点={extra_sites} 未覆盖={len(extra_violations)}"
            "（登记于 BK 手册 §7，本守卫暂不阻断）"
        )
        for where, key, handlers in extra_violations:
            print(f"  {where}  键={key}  except={handlers}")
    if args.list:
        return 0
    if violations or stale or shrunk:
        print(
            "FAIL：单腿 ast.parse 守卫会把 ValueError 族抛穿到调用方，请改用 "
            "src.utils.check_status.parses_as_module / AST_UNREADABLE_ERRORS，"
            "或为确需保守降级的站点登记 EXEMPT 并写明折叠形态。"
        )
        return 1
    print("PASS：src/ 全部 ast.parse 守卫覆盖 ValueError 族或已在豁免额度内按名登记。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
