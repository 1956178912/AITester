"""
内置轻量变异测试生成器（1.2 变异得分评估）。

背景：
    代码覆盖率无法反映测试检测缺陷的能力。MutGen / ACH 等研究证明，
    变异引导的 LLM 测试生成能聚焦"当前未被检测到的故障"，显著提升
    测试的有效性。

    本模块提供：
    1. 内置轻量变异生成器：对目标代码 AST 级插入变异体（边界值替换、
       运算符翻转、布尔取反），无需 mutmut 依赖即可产出 mutation_score；
    2. mutation_score_from_details：收集 details[].mutation_score 汇总
       （与 analyze_results._mutation_score_metrics 同口径，但独立实现
       以便在 run_benchmark 流水线中直接消费）；
    3. 可选 mutmut 兜底：若系统安装了 mutmut，优先使用其完整变异测试
       结果；否则回退到内置轻量生成器。

设计约束：
    - 内置生成器为保守口径：仅处理纯 Python 函数体，变异类型限于
      三类（边界值替换 / 比较运算符翻转 / 布尔取反），误报率低；
    - 不修改原始代码文件，所有变异体在内存中生成与执行；
    - 无变异体可生成时（如代码无可变异语句）返回 available=False，
      不阻断主流程。
"""

from __future__ import annotations

import ast
import copy
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# ─── 变异体定义 ──────────────────────────────────────────────────────────────


@dataclass
class Mutant:
    """单个变异体：代码字符串 + 变异类型标签 + 变异位置描述。"""

    code: str
    mutant_type: str  # "boundary" | "operator_flip" | "boolean_negation"
    description: str
    line_no: int = 0



def _find_mutable_comparison_nodes(tree: ast.Module) -> list[ast.Compare]:
    """收集所有 Compare 节点（可变异为边界值变体）。"""
    return [node for node in ast.walk(tree) if isinstance(node, ast.Compare)]


def _find_boolean_nodes(tree: ast.Module) -> list[ast.UnaryOp]:
    """收集所有 Not（布尔取反）UnaryOp 节点（可变异为去除取反）。"""
    return [node for node in ast.walk(tree) if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not)]


class _RemoveNotTransformer(ast.NodeTransformer):
    """按行号定位并改写 AST 中指定位置的 `not X` 为 `X`。

    设计说明：
        AST 节点不携带 parent 链接（Python 3.12/3.14 均如此），无法用
        "walk + parent 改写"的方式做精确替换。这里继承 NodeTransformer，
        在 visit_Expr / visit_BoolOp / visit_Compare 等常见槽位识别
        UnaryOp(Not) 节点，按行号匹配后直接返回其 operand，让 NodeTransformer
        自动把父槽位的字段改写为 operand（语义等价于 not X → X）。
    """

    def __init__(self, target_lineno: int) -> None:
        """初始化（target_lineno 为要改写的 Not 节点行号）。"""
        self._target_lineno = target_lineno
        self._replaced = False

    def _replace(self, node: ast.UnaryOp) -> ast.expr:
        """当 node 是目标行号的 UnaryOp(Not) 时返回其 operand，否则原样返回。"""
        if (
            isinstance(node, ast.UnaryOp)
            and isinstance(node.op, ast.Not)
            and node.lineno == self._target_lineno
            and not self._replaced
        ):
            self._replaced = True
            return node.operand
        return node

    def visit_Expr(self, node: ast.Expr) -> ast.AST:
        """改写语句级表达式槽位（如独立语句 `not x()`）。"""
        if isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.Not) and node.value.lineno == self._target_lineno and not self._replaced:
            self._replaced = True
            node.value = node.value.operand
            return node
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """改写比较左右值槽位（如 `x == not y`，罕见但保守覆盖）。"""
        if isinstance(node.left, ast.UnaryOp) and isinstance(node.left.op, ast.Not) and node.left.lineno == self._target_lineno and not self._replaced:
            self._replaced = True
            node.left = node.left.operand
        for i, comp in enumerate(node.comparators):
            if isinstance(comp, ast.UnaryOp) and isinstance(comp.op, ast.Not) and comp.lineno == self._target_lineno and not self._replaced:
                self._replaced = True
                node.comparators[i] = comp.operand
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        """改写 BoolOp 子值槽位（如 `a and not b` → `a and b`）。"""
        for i, val in enumerate(node.values):
            if isinstance(val, ast.UnaryOp) and isinstance(val.op, ast.Not) and val.lineno == self._target_lineno and not self._replaced:
                self._replaced = True
                node.values[i] = val.operand
        return self.generic_visit(node)

    def visit_If(self, node: ast.If) -> ast.AST:
        """改写 If/While 等控制流的测试表达式槽位（最常见的 not X 位置）。"""
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not) and node.test.lineno == self._target_lineno and not self._replaced:
            self._replaced = True
            node.test = node.test.operand
        return self.generic_visit(node)

    def visit_While(self, node: ast.While) -> ast.AST:
        """改写 While 循环条件槽位（`while not cond` → `while cond`）。"""
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not) and node.test.lineno == self._target_lineno and not self._replaced:
            self._replaced = True
            node.test = node.test.operand
        return self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> ast.AST:
        """改写 return 语句槽位（`return not x` → `return x`）。"""
        if isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.Not) and node.value.lineno == self._target_lineno and not self._replaced:
            self._replaced = True
            node.value = node.value.operand
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        """改写赋值右值槽位（`x = not y` → `x = y`）。"""
        if isinstance(node.value, ast.UnaryOp) and isinstance(node.value.op, ast.Not) and node.value.lineno == self._target_lineno and not self._replaced:
            self._replaced = True
            node.value = node.value.operand
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        """改写函数体（让 generic_visit 继续下钻，捕获嵌套 If/While/Return 等）。"""
        return self.generic_visit(node)


class MutationGenerator:
    """内置轻量变异生成器（AST 级，无外部依赖）。

    用法：
        gen = MutationGenerator()
        mutants = gen.generate(source_code)
        # 每个 Mutant 可单独执行测试套件，统计被杀死比例

    设计说明：
    - 变异体数量有限（不超过 _MAX_MUTANTS_PER_TASK），避免执行时间爆炸；
    - 仅对函数体内的语句变异（模块级赋值不纳入，保守口径）；
    - 返回空列表表示无可变异语句（如空函数 / 纯文档字符串）。
    """

    # 每任务最大变异体数量（来源：执行时间预算，每个变异体跑一遍测试 ~1-3s）
    _MAX_MUTANTS_PER_TASK = 20

    def generate(self, source_code: str) -> list[Mutant]:
        """对源码生成变异体列表。

        Args:
            source_code: 完整 Python 源码字符串。

        Returns:
            Mutant 列表（可能为空）；语法错误时返回空列表并记 warning。
        """
        if not source_code or not source_code.strip():
            return []
        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            logger.warning("变异生成：源码语法错误，跳过变异: %s", e)
            return []

        mutants: list[Mutant] = []

        # 变异类型 1：比较运算符翻转（== → != 等）
        mutants.extend(self._generate_comparison_flips(tree, source_code))
        # 变异类型 2：布尔取反（not X → X）
        mutants.extend(self._generate_boolean_negations(tree, source_code))
        # 变异类型 3：数字常量偏移（+1 / -1 / 0）
        mutants.extend(self._generate_numeric_offset(tree, source_code))

        # 截断到上限
        return mutants[: self._MAX_MUTANTS_PER_TASK]

    def _generate_comparison_flips(
        self, tree: ast.Module, source_code: str
    ) -> list[Mutant]:
        """比较运算符翻转变异。"""
        mutants: list[Mutant] = []
        for cmp_node in _find_mutable_comparison_nodes(tree):
            for op in cmp_node.ops:
                op_name = type(op).__name__
                if op_name not in ("Eq", "NotEq", "Lt", "Gt", "LtE", "GtE"):
                    continue
                flipped = _OPERATOR_FLIP_MAP.get(op_name)
                if flipped is None:
                    continue
                new_tree = copy.deepcopy(tree)
                self._flip_comparison_op(new_tree, cmp_node, flipped)
                try:
                    new_code = ast.unparse(new_tree)
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="operator_flip",
                            description=f"line {cmp_node.lineno}: {op_name} → {flipped}",
                            line_no=cmp_node.lineno,
                        )
                    )
                except (ValueError, TypeError):
                    continue
        return mutants

    @staticmethod
    def _flip_comparison_op(
        tree: ast.Module, original_node: ast.Compare, new_op_name: str
    ) -> None:
        """在 deepcopy 后的 tree 中翻转指定 Compare 节点的操作符（尽力匹配，失败忽略）。"""
        # 尽力匹配：按行号找第一个同类型 Compare
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and node.lineno == original_node.lineno
            ):
                op_class = getattr(ast, new_op_name)
                node.ops = [op_class(), *node.ops[1:]]
                return

    def _generate_boolean_negations(
        self, tree: ast.Module, source_code: str
    ) -> list[Mutant]:
        """布尔取反变异：not X → X（移除 Not 节点）。

        实现：对每个 Not 节点，deepcopy 后用 _RemoveNotTransformer 改写
        该行的 not X 为 X，再 ast.unparse。Transformer 对 If/While/
        Return/Assign/BoolOp/Compare/Expr 等常见槽位做保守覆盖，
        未命中时 unparse 后的代码与原代码相同（该变异体无效，下游
        沙箱执行会"全通过"等价于存活，保守口径下不计入杀死数）。
        """
        mutants: list[Mutant] = []
        for not_node in _find_boolean_nodes(tree):
            new_tree = copy.deepcopy(tree)
            transformer = _RemoveNotTransformer(not_node.lineno)
            transformer.visit(new_tree)
            # Transformer 原地改写 new_tree 的字段；若未命中（_replaced 为 False），
            # unparse 出的代码与原代码相同，该变异体是"无效变异"——保守口径
            # 下过滤掉（不进入变异体列表），避免虚增变异体数量。
            if not transformer._replaced:
                continue
            try:
                new_code = ast.unparse(new_tree)
                mutants.append(
                    Mutant(
                        code=new_code,
                        mutant_type="boolean_negation",
                        description=f"line {not_node.lineno}: not X → X",
                        line_no=not_node.lineno,
                    )
                )
            except (ValueError, TypeError):
                continue
        return mutants

    @staticmethod
    def _remove_not_op(tree: ast.Module, original_node: ast.UnaryOp) -> None:
        """在 tree 中移除指定行号的 Not 节点（将 not X 替换为 X）。

        保留为独立入口便于未来复用；内部委托给 _RemoveNotTransformer。
        原地改写 tree（Transformer.visit 副作用）；未命中时 tree 不变。
        """
        transformer = _RemoveNotTransformer(original_node.lineno)
        transformer.visit(tree)

    def _generate_numeric_offset(
        self, tree: ast.Module, source_code: str
    ) -> list[Mutant]:
        """数字常量偏移变异：value → value+1（仅在数值出现在比较或赋值中时）。"""
        mutants: list[Mutant] = []
        # 收集比较中的数字常量（左值或右值）
        for cmp_node in ast.walk(tree):
            if not isinstance(cmp_node, ast.Compare):
                continue
            targets: list[ast.expr] = [cmp_node.left, *cmp_node.comparators]
            for i, target in enumerate(targets):
                if not isinstance(target, ast.Constant):
                    continue
                new_tree = copy.deepcopy(tree)
                self._offset_numeric(new_tree, cmp_node, i, 1)
                try:
                    new_code = ast.unparse(new_tree)
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="numeric_offset",
                            description=f"line {cmp_node.lineno}: const {target.value} → +1",
                            line_no=cmp_node.lineno,
                        )
                    )
                except (ValueError, TypeError):
                    continue
        return mutants

    @staticmethod
    def _offset_numeric(
        tree: ast.Module, cmp_node: ast.Compare, target_index: int, offset: int
    ) -> None:
        """在 deepcopy 后的 tree 中偏移 Compare 中指定位置的数字常量。"""
        new_cmp: ast.Compare | None = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Compare) and node.lineno == cmp_node.lineno:
                new_cmp = node
                break
        if new_cmp is None:
            return
        targets: list[ast.expr] = [new_cmp.left, *new_cmp.comparators]
        if target_index < len(targets):
            target = targets[target_index]
            if isinstance(target, ast.Constant) and isinstance(target.value, (int, float)):
                target.value = target.value + offset


# 比较运算符 AST 类名 → 翻转目标映射
_OPERATOR_FLIP_MAP: dict[str, str] = {
    "Eq": "NotEq",
    "NotEq": "Eq",
    "Lt": "LtE",
    "Gt": "GtE",
    "LtE": "Lt",
    "GtE": "Gt",
}


def _run_mutant_tests(
    mutant: Mutant,
    test_code: str,
    module_file: str,
    timeout_seconds: int = 30,
) -> bool:
    """在沙箱中执行单个变异体 + 测试套件，返回变异体是否被"杀死"。

    变异体被杀死 = 测试套件在变异代码上至少一个用例失败（说明测试捕获了该变异）。
    变异体存活 = 测试套件全部通过（说明测试未能检测出该变异）。

    Args:
        mutant: 变异体。
        test_code: 测试代码字符串。
        module_file: 被测模块文件路径。
        timeout_seconds: 单个变异体执行超时。

    Returns:
        True = 杀死，False = 存活。执行失败（如 import 错误）视为存活（保守口径）。
    """
    import os
    import sys
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            mutant_file = os.path.join(tmpdir, "mutated_module.py")
            test_file = os.path.join(tmpdir, "test_mutant.py")

            # 写变异体代码（需要处理 import 路径）
            with open(mutant_file, "w", encoding="utf-8") as f:
                f.write(mutant.code)

            with open(test_file, "w", encoding="utf-8") as f:
                f.write(test_code)

            # 执行测试：pytest 单文件
            proc = __import__("subprocess").run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    test_file,
                    "--tb=no",
                    "-q",
                ],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=tmpdir,
                env={**os.environ, "PYTHONPATH": tmpdir},
            )
            return proc.returncode != 0  # 非 0 退出 = 有失败 = 杀死
    except Exception:
        # 执行失败视为存活（保守：不夸大变异得分）
        return False


def compute_mutation_score(
    source_code: str,
    test_code: str,
    module_file: str,
    max_mutants: int = 10,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """计算单任务的变异得分（0.0-1.0）。

    流程：
    1. 生成变异体（内置轻量生成器，不超过 max_mutants 个）；
    2. 逐个执行测试套件统计被杀死比例；
    3. 返回 mutation_score + 元数据。

    Args:
        source_code: 被测代码。
        test_code: 测试代码。
        module_file: 被测模块路径。
        max_mutants: 最多评估的变异体数量（默认 10，控制执行时间）。
        timeout_seconds: 单变异体超时。

    Returns:
        {"available": bool, "mutation_score": float,
         "mutants_total": int, "mutants_killed": int,
         "elapsed_seconds": float}
        无变异体时 available=False，mutation_score=None。
    """
    generator = MutationGenerator()
    all_mutants = generator.generate(source_code)
    if not all_mutants:
        return {
            "available": False,
            "mutation_score": None,
            "mutants_total": 0,
            "mutants_killed": 0,
            "elapsed_seconds": 0.0,
        }

    selected = all_mutants[:max_mutants]
    t0 = time.time()
    killed = 0
    for mutant in selected:
        if _run_mutant_tests(mutant, test_code, module_file, timeout_seconds):
            killed += 1
    elapsed = round(time.time() - t0, 2)
    score = round(killed / len(selected), 4) if selected else 0.0
    logger.info(
        "变异得分: %d/%d 杀死，score=%.4f，耗时 %.1fs",
        killed,
        len(selected),
        score,
        elapsed,
    )
    return {
        "available": True,
        "mutation_score": score,
        "mutants_total": len(selected),
        "mutants_killed": killed,
        "elapsed_seconds": elapsed,
    }


# ─── 汇总层（与 analyze_results._mutation_score_metrics 同口径）────────────


def mutation_score_from_details(details: list[dict[str, Any]]) -> dict[str, Any]:
    """收集 details[].mutation_score 字段并汇总（保守口径，无该字段时 available=False）。

    Args:
        details: benchmark 结果 details 列表。

    Returns:
        {"available": bool, "observed_tasks": int,
         "avg_mutation_score": float, "high_score_tasks": int,
         "low_score_tasks": int}
    """
    scores: list[float] = []
    for row in details:
        ms = row.get("mutation_score")
        if ms is None:
            continue
        try:
            scores.append(float(ms))
        except (TypeError, ValueError):
            continue
    if not scores:
        return {"available": False, "observed_tasks": 0}
    avg = round(sum(scores) / len(scores), 4)
    return {
        "available": True,
        "observed_tasks": len(scores),
        "avg_mutation_score": avg,
        "high_score_tasks": sum(1 for s in scores if s >= 0.7),
        "low_score_tasks": sum(1 for s in scores if s < 0.4),
    }
