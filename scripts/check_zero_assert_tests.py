"""零断言测试守卫（U3，2026-10-05 系统性审查落地）。

背景（2026-10-05 独立系统性审查）：
    tests/ 中存在大量"零断言"测试函数——函数体内没有任何断言信号
    （无 assert 语句、无 assert_* mock 校验、无 pytest.raises），仅
    "调用一下不抛异常"即通过。此类用例对行为零校验，却计入行覆盖率，
    使 90% 行覆盖虚高（审查实证样例：test_api_manager_extended.py:270、
    test_workflow.py:326-351）。

本守卫（纯 stdlib AST 扫描，零新依赖）：
    1. 扫描 tests/**.py 中全部"测试函数"（模块级 test_* 或 Test* 类内
       的 test_* 方法）；
    2. 判定函数体内是否存在任一"断言信号"：
       - ast.Assert 语句（含子句体内的——ast.walk 全子树）；
       - 名称/属性以 assert 开头的调用（assert_called_once、
         assertRaises 等，覆盖 unittest 与 mock 两种风格）；
       - pytest.raises / pytest.warns / pytest.fail / self.fail 调用；
       - 委托调用（helper 函数转发断言场景：函数体只有一处对其他
         test_ 函数的调用——保守放行，由 EXEMPT 显式登记兜底）。
    3. 命中 EXEMPT 登记项（"文件::函数名"→ 一句话理由）输出 INFO 跳过；
       未豁免且无断言信号 → 违规，退出码 1 阻断合并。

CLI：
    python scripts/check_zero_assert_tests.py            # 全仓扫描
    python scripts/check_zero_assert_tests.py --list     # 只列违规不判退出码
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = REPO_ROOT / "tests"

# 豁免登记：键 = "相对 tests/ 的文件路径::函数名"，值 = 一句话豁免理由。
# 豁免口径（审查批次 U3 确认）：测试意图就是"降级/兜底路径不抛异常"，
# 无可观测返回值可供断言。新增零断言用例必须在此登记，否则 CI 阻断。
EXEMPT: dict[str, str] = {
    # （U3 修复批次后清空——所有已知零断言用例已补强或豁免；此处保留
    #  结构供后续批次登记，登记时附理由与批次标签。）
}


def _is_test_function(node: ast.AST, in_test_class: bool) -> bool:
    """判定 AST 节点是否为测试函数（模块级 test_* 或 Test* 类内 test_*）。"""
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return node.name.startswith("test_") or (in_test_class and node.name.startswith("test"))


def _has_assertion_signal(func: ast.AST, helper_nodes: dict[str, ast.AST] | None = None) -> bool:
    """判定函数子树内是否存在任一断言信号（保守：宁可漏报不误报）。

    helper_nodes：同类/同模块辅助方法名 → AST 映射（一层内联解析）——
    测试把断言集中在 _check_* 辅助方法（如 test_workflow_combinations 的
    _check_graph）时，逐调用解析目标方法体是否含断言信号，避免误报。
    仅解析一层（helper 内再委托不再递归，保守口径）。
    """
    for node in ast.walk(func):
        # 信号 1：assert 语句
        if isinstance(node, ast.Assert):
            return True
        # 信号 2/3：调用形态（assert_* 方法 / pytest.raises / fail）
        if isinstance(node, ast.Call):
            fn = node.func
            name = ""
            if isinstance(fn, ast.Name):
                name = fn.id
            elif isinstance(fn, ast.Attribute):
                name = fn.attr
            if name.startswith("assert") or name.startswith("assertRaises") or name == "fail":
                return True
            # pytest.raises / pytest.warns（fn 为 Attribute：pytest.raises）
            if (
                isinstance(fn, ast.Attribute)
                and fn.attr in ("raises", "warns")
                and isinstance(fn.value, ast.Name)
                and fn.value.id == "pytest"
            ):
                return True
            # 一层内联解析：self._check_x(...) / _check_x(...) → helper 体含断言
            if helper_nodes and name in helper_nodes and _has_assertion_signal(helper_nodes[name]):
                return True
            # unittest 的 self.assertRaises 经属性名 assertRaises 已覆盖
    return False


def scan_file(path: Path) -> list[tuple[str, str]]:
    """扫描单个测试文件，返回 [(函数名, 豁免键)] 形式的零断言用例清单。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError as e:
        print(f"[WARN] {path} 语法错误，跳过扫描: {e}")
        return []
    violations: list[tuple[str, str]] = []
    for cls in ast.walk(tree):
        # Test* 类内的方法单独处理（in_test_class 语义由类名判定）
        if isinstance(cls, ast.ClassDef) and cls.name.startswith("Test"):
            # 一层内联解析的辅助方法表：同类中非 test_ 方法（_check_* 等）
            helpers = {
                item.name: item
                for item in cls.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and not item.name.startswith("test")
            }
            violations.extend(
                (item.name, f"{path.name}::{item.name}")
                for item in cls.body
                if _is_test_function(item, in_test_class=True) and not _has_assertion_signal(item, helper_nodes=helpers)
            )
    violations.extend(
        (node.name, f"{path.name}::{node.name}")
        for node in tree.body
        if _is_test_function(node, in_test_class=False) and not _has_assertion_signal(node)
    )
    return violations


def main() -> int:
    """主入口：全仓扫描 tests/，违规未豁免即退出码 1（--list 只列不判）。"""
    parser = argparse.ArgumentParser(description="零断言测试守卫（U3）")
    parser.add_argument("--list", action="store_true", help="只列违规不判退出码")
    args = parser.parse_args()

    test_files = sorted(TESTS_DIR.rglob("test_*.py"))
    all_violations: list[tuple[Path, str, str]] = []
    for path in test_files:
        for _name, key in scan_file(path):
            all_violations.append((path, key, EXEMPT.get(key, "")))

    n_exempt = 0
    violations_final: list[tuple[Path, str]] = []
    for path, key, reason in all_violations:
        if reason:
            n_exempt += 1
            print(f"[INFO] 豁免 {key}: {reason}")
        else:
            violations_final.append((path, key))

    print(
        f"扫描 {len(test_files)} 个测试文件：零断言用例 {len(all_violations)} 个"
        f"（豁免 {n_exempt}，违规 {len(violations_final)}）"
    )
    for path, key in violations_final:
        print(
            f"[FAIL] {path.relative_to(REPO_ROOT)}::{key.split('::', 1)[1]}——"
            f"无任何断言信号（assert / assert_* / pytest.raises）。"
            f"补有效断言，或确属'降级路径不抛异常'意图时在脚本 EXEMPT 登记理由"
        )
    if args.list:
        return 0
    return 1 if violations_final else 0


if __name__ == "__main__":
    sys.exit(main())
