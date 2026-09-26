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
from typing import Any, ClassVar

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
        if (
            isinstance(node.value, ast.UnaryOp)
            and isinstance(node.value.op, ast.Not)
            and node.value.lineno == self._target_lineno
            and not self._replaced
        ):
            self._replaced = True
            node.value = node.value.operand
            return node
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        """改写比较左右值槽位（如 `x == not y`，罕见但保守覆盖）。"""
        if (
            isinstance(node.left, ast.UnaryOp)
            and isinstance(node.left.op, ast.Not)
            and node.left.lineno == self._target_lineno
            and not self._replaced
        ):
            self._replaced = True
            node.left = node.left.operand
        for i, comp in enumerate(node.comparators):
            if (
                isinstance(comp, ast.UnaryOp)
                and isinstance(comp.op, ast.Not)
                and comp.lineno == self._target_lineno
                and not self._replaced
            ):
                self._replaced = True
                node.comparators[i] = comp.operand
        return self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> ast.AST:
        """改写 BoolOp 子值槽位（如 `a and not b` → `a and b`）。"""
        for i, val in enumerate(node.values):
            if (
                isinstance(val, ast.UnaryOp)
                and isinstance(val.op, ast.Not)
                and val.lineno == self._target_lineno
                and not self._replaced
            ):
                self._replaced = True
                node.values[i] = val.operand
        return self.generic_visit(node)

    def visit_If(self, node: ast.If) -> ast.AST:
        """改写 If/While 等控制流的测试表达式槽位（最常见的 not X 位置）。"""
        if (
            isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and node.test.lineno == self._target_lineno
            and not self._replaced
        ):
            self._replaced = True
            node.test = node.test.operand
        return self.generic_visit(node)

    def visit_While(self, node: ast.While) -> ast.AST:
        """改写 While 循环条件槽位（`while not cond` → `while cond`）。"""
        if (
            isinstance(node.test, ast.UnaryOp)
            and isinstance(node.test.op, ast.Not)
            and node.test.lineno == self._target_lineno
            and not self._replaced
        ):
            self._replaced = True
            node.test = node.test.operand
        return self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> ast.AST:
        """改写 return 语句槽位（`return not x` → `return x`）。"""
        if (
            isinstance(node.value, ast.UnaryOp)
            and isinstance(node.value.op, ast.Not)
            and node.value.lineno == self._target_lineno
            and not self._replaced
        ):
            self._replaced = True
            node.value = node.value.operand
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        """改写赋值右值槽位（`x = not y` → `x = y`）。"""
        if (
            isinstance(node.value, ast.UnaryOp)
            and isinstance(node.value.op, ast.Not)
            and node.value.lineno == self._target_lineno
            and not self._replaced
        ):
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

    变异类型（P0 3.3 难度升级，共 7 类）：
        1. operator_flip   比较运算符翻转（== ↔ !=、< ↔ > 等）
        2. boolean_negation 布尔取反（not X → X）
        3. numeric_offset  数字常量偏移（+1 / -1 / 0）
        4. boundary_shift  条件边界变异（> ↔ >=、< ↔ <=，off-by-one 方向）
        5. return_void     返回值变异（return X → return None）
        6. return_empty    返回值变异（return X → return [] / return ""）
        7. exception_remove 异常路径变异（移除 raise 语句 / 修改异常类型）
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
        # 变异类型 4（1.2 改进）：条件边界变异（> → >=、< → <=、<= → <、>= → >）
        # 与比较运算符翻转的区别：翻转是"等值对"互换（== ↔ !=），边界变异专攻
        # 严格/非严格比较的边界语义（边界 off-by-one 类 bug 的经典变异方向）
        mutants.extend(self._generate_boundary_shifts(tree, source_code))
        # 变异类型 5（1.2 改进）：返回值变异（return X → return None）
        # 检测"测试是否真正校验了返回语义"：若测试断言了具体返回值，该变异体
        # 应被杀死；存活说明测试只跑了执行路径、未校验返回值
        mutants.extend(self._generate_return_voids(tree, source_code))
        # 变异类型 6（P0 3.3）：返回值变异增强（return X → return [] / return ""）
        # 检测"测试是否校验了返回类型"：若测试断言了具体列表/字符串，该变异体
        # 应被杀死；存活说明测试只校验了"能跑"未校验返回类型
        mutants.extend(self._generate_return_empty(tree, source_code))
        # 变异类型 7（P0 3.3）：异常路径变异（移除 raise 语句 / 修改异常类型）
        # 检测"测试是否校验了异常抛出"：若测试用 pytest.raises 校验了特定异常，
        # 移除 raise 后测试应失败；存活说明测试未覆盖异常路径
        mutants.extend(self._generate_exception_removals(tree, source_code))

        # 2026-09-26 全面审查（P1 正确性）：按 mutant.code 去重——此前同行
        # 多个比较产生"描述与改动不一致 + 重复变异体"（同一份代码文本被登记
        # 两次，下游按 mutants_total 计分时分母虚增、杀死比例失真）。
        seen_code: set[str] = set()
        deduped: list[Mutant] = []
        for m in mutants:
            if m.code in seen_code:
                continue
            seen_code.add(m.code)
            deduped.append(m)
        mutants = deduped

        # 截断到上限。2026-09-26 全面审查（P1 正确性）：此前按注册顺序
        # （类型 1-7 依次 extend）取前 20——前 4 类（比较翻转/布尔取反/
        # 数字偏移/边界）在富比较代码上易爆炸，把 P0 3.3 新增的第 5-7 类
        # （return_void / return_empty / exception_remove）整体挤掉，
        # "7 类全启用"的设计意图落空。改为**类型轮转均匀取样**：把 7 类
        # 按类分桶，桶间轮转各取 1 直至填满上限，保证每类都有代表、
        # 上限耗尽时各类比例均衡（口径对"变异体类型覆盖"更可预测）。
        if len(mutants) > self._MAX_MUTANTS_PER_TASK:
            # 按类型分桶（保持每类内部原顺序）
            type_order: list[str] = []
            buckets: dict[str, list[Mutant]] = {}
            for m in mutants:
                if m.mutant_type not in buckets:
                    buckets[m.mutant_type] = []
                    type_order.append(m.mutant_type)
                buckets[m.mutant_type].append(m)
            # 轮转取样：round-robin 逐桶取 1
            selected: list[Mutant] = []
            per_bucket_idx: dict[str, int] = {t: 0 for t in type_order}
            while len(selected) < self._MAX_MUTANTS_PER_TASK:
                progressed = False
                for t in type_order:
                    if len(selected) >= self._MAX_MUTANTS_PER_TASK:
                        break
                    idx = per_bucket_idx[t]
                    if idx < len(buckets[t]):
                        selected.append(buckets[t][idx])
                        per_bucket_idx[t] = idx + 1
                        progressed = True
                if not progressed:
                    break
            return selected
        return mutants

    def _generate_comparison_flips(self, tree: ast.Module, source_code: str) -> list[Mutant]:
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
    def _flip_comparison_op(tree: ast.Module, original_node: ast.Compare, new_op_name: str) -> None:
        """在 deepcopy 后的 tree 中翻转指定 Compare 节点的操作符（尽力匹配，失败忽略）。

        2026-09-26 全面审查（P1 正确性）：定位键从"行号取第一个同类型
        Compare"升级为 (lineno, col_offset) 双键——此前同一行多个比较
        （如 `a < b and c < d`）时只改到第一个，description 记录的是
        原节点操作符，产生描述与改动不一致 + 重复变异体。
        """
        op_class = getattr(ast, new_op_name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and node.lineno == original_node.lineno
                and getattr(node, "col_offset", 0) == getattr(original_node, "col_offset", 0)
            ):
                node.ops = [op_class(), *node.ops[1:]]
                return

    def _generate_boolean_negations(self, tree: ast.Module, source_code: str) -> list[Mutant]:
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

    def _generate_numeric_offset(self, tree: ast.Module, source_code: str) -> list[Mutant]:
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
    def _offset_numeric(tree: ast.Module, cmp_node: ast.Compare, target_index: int, offset: int) -> None:
        """在 deepcopy 后的 tree 中偏移 Compare 中指定位置的数字常量。

        2026-09-26 全面审查（P1 正确性）：定位键同 _flip_comparison_op，
        升级为 (lineno, col_offset) 双键（此前行号取第一个，同行多比较
        时改错位置）。
        """
        new_cmp: ast.Compare | None = None
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and node.lineno == cmp_node.lineno
                and getattr(node, "col_offset", 0) == getattr(cmp_node, "col_offset", 0)
            ):
                new_cmp = node
                break
        if new_cmp is None:
            return
        targets: list[ast.expr] = [new_cmp.left, *new_cmp.comparators]
        if target_index < len(targets):
            target = targets[target_index]
            if isinstance(target, ast.Constant) and isinstance(target.value, (int, float)):
                target.value = target.value + offset

    def _generate_boundary_shifts(self, tree: ast.Module, source_code: str) -> list[Mutant]:
        """1.2 改进：条件边界变异（严格/非严格比较互转：> ↔ >=、< ↔ <=）。

        针对 off-by-one 类边界 bug 的经典变异方向：
        - Gt → GtE（> 改 >=）
        - GtE → Gt（>= 改 >）
        - Lt → LtE（< 改 <=）
        - LtE → Lt（<= 改 <）
        保守口径：仅处理严格/非严格比较（不含 ==/!=，那是运算符翻转变异
        的覆盖范围）；同一比较节点每对边界只产一个变异体（避免 GtE→Gt 与
        Gt→GtE 对偶重复计入）。
        """
        mutants: list[Mutant] = []
        boundary_pairs = {"Gt": "GtE", "GtE": "Gt", "Lt": "LtE", "LtE": "Lt"}
        seen_pairs: set[tuple[int, int]] = set()
        for cmp_node in _find_mutable_comparison_nodes(tree):
            for op in cmp_node.ops:
                op_name = type(op).__name__
                target = boundary_pairs.get(op_name)
                if target is None:
                    continue
                # 去重：同一行的 Gt→GtE 与 GtE→Gt 不重复（比较链中相邻对偶）
                key = (cmp_node.lineno, op_name)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                new_tree = copy.deepcopy(tree)
                self._shift_boundary_op(new_tree, cmp_node, target)
                try:
                    new_code = ast.unparse(new_tree)
                    if new_code == source_code:
                        continue  # 无效变异（AST 未变），保守过滤
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="boundary_shift",
                            description=f"line {cmp_node.lineno}: {op_name} → {target}（边界变异）",
                            line_no=cmp_node.lineno,
                        )
                    )
                except (ValueError, TypeError):
                    continue
        return mutants

    @staticmethod
    def _shift_boundary_op(tree: ast.Module, original_node: ast.Compare, new_op_name: str) -> None:
        """在 deepcopy 后的 tree 中把指定行 Compare 的运算符替换为边界对偶。

        2026-09-26 全面审查（P1 正确性）：定位键升级为 (lineno, col_offset) 双键。
        """
        op_class = getattr(ast, new_op_name)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Compare)
                and node.lineno == original_node.lineno
                and getattr(node, "col_offset", 0) == getattr(original_node, "col_offset", 0)
            ):
                node.ops = [op_class(), *node.ops[1:]]
                return

    def _generate_exception_removals(self, tree: ast.Module, source_code: str) -> list[Mutant]:
        """P0 3.3 异常路径变异：移除 raise 语句 / 修改异常类型。

        检测"测试是否校验了异常路径"：
        - 移除 raise：若测试用 pytest.raises 校验了特定异常，移除后测试应失败；
          存活说明测试未覆盖异常路径（只测了正常路径）。
        - 修改异常类型（ValueError ↔ TypeError 等）：若测试校验了特定异常类型，
          改坏后测试应失败；存活说明测试只校验"有异常"未校验"哪种异常"。

        保守口径：
        - 仅处理函数体内的 raise 语句（模块级 raise 不纳入）；
        - 每类变异每函数最多 3 个（避免变异体爆炸）；
        - unparse 失败或代码不变时跳过。
        """
        mutants: list[Mutant] = []
        for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            raises = [n for n in ast.walk(func) if isinstance(n, ast.Raise)]
            per_func_removal = 0
            per_func_type_change = 0
            for raise_node in raises:
                # 变异 7a：移除 raise（替换为 pass）
                if per_func_removal >= 3:
                    break
                if raise_node.exc is None:
                    continue  # 裸 raise（无异常对象）无法移除（会破坏 try/except 结构）
                # 保守口径：仅移除"独立 raise 语句"（非 try 块内最后一条），
                # 避免移除后 try 块体为空 / except 结构破坏
                new_tree = copy.deepcopy(tree)
                transformer = _RemoveRaiseTransformer(raise_node.lineno, func.name)
                transformer.visit(new_tree)
                if not transformer._removed:
                    continue
                try:
                    new_code = ast.unparse(new_tree)
                    # unparse 成功但需验证语法合法（pass 替换 raise 后
                    # 若原 raise 是某 if/else 唯一分支体，可能产生空语句块）
                    ast.parse(new_code)
                    if new_code == source_code:
                        continue
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="exception_remove",
                            description=f"line {raise_node.lineno}: 移除 raise {ast.unparse(raise_node.exc)}（异常路径变异）",
                            line_no=raise_node.lineno,
                        )
                    )
                    per_func_removal += 1
                except (ValueError, TypeError, SyntaxError):
                    continue

            # 变异 7b：修改异常类型（ValueError ↔ TypeError 等）
            per_func_type_change = 0
            for raise_node in raises:
                if per_func_type_change >= 3:
                    break
                # 仅处理 `raise X(...)` 形式（异常类型是 Name 节点）
                if raise_node.exc is None:
                    continue
                exc = raise_node.exc
                exc_name = None
                if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                    exc_name = exc.func.id
                elif isinstance(exc, ast.Name):
                    exc_name = exc.id
                if exc_name is None:
                    continue
                new_exc_name = _ExceptionTypeTransformer._get_swap_pairs().get(exc_name, "")
                if not new_exc_name:
                    continue
                new_tree = copy.deepcopy(tree)
                transformer = _ExceptionTypeTransformer(raise_node.lineno, func.name, exc_name)
                transformer.visit(new_tree)
                if not transformer._replaced:
                    continue
                try:
                    new_code = ast.unparse(new_tree)
                    if new_code == source_code:
                        continue
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="exception_type_swap",
                            description=f"line {raise_node.lineno}: raise {exc_name} → raise {new_exc_name}（异常类型变异）",
                            line_no=raise_node.lineno,
                        )
                    )
                    per_func_type_change += 1
                except (ValueError, TypeError, SyntaxError):
                    continue
        return mutants

    def _generate_return_empty(self, tree: ast.Module, source_code: str) -> list[Mutant]:
        """P0 3.3 返回值变异增强（return X → return [] / return ""）。

        检测"测试是否校验了返回类型"：
        - return [1,2,3] → return []（空列表）：若测试断言了非空列表，该变异体应被杀死；
          存活说明测试只校验"能跑"未校验返回内容。
        - return "hello" → return ""（空字符串）：若测试断言了非空字符串，该变异体应被杀死。

        保守口径：
        - 仅处理"非空字面量"return（return [] / return "" / return None 已是空值，跳过）；
        - 每个函数体最多产 3 个返回值变异（与 return_voids 同口径，避免变异体爆炸）；
        - unparse 失败或代码不变时跳过。
        """
        mutants: list[Mutant] = []
        per_function: dict[str, int] = {}
        for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for ret in [n for n in ast.walk(func) if isinstance(n, ast.Return)]:
                if ret.value is None:
                    continue  # 无值 return
                # 跳过已是空值的情况（None / [] / "" / {} / set()）
                if isinstance(ret.value, ast.Constant):
                    val = ret.value.value
                    if val is None or val == [] or val == "" or val == {} or val == set():
                        continue
                if isinstance(ret.value, (ast.List, ast.Set, ast.Dict)) and not ret.value.elts:
                    continue  # 已是空容器
                if per_function.get(func.name, 0) >= 3:
                    continue  # 单函数上限 3 个
                new_tree = copy.deepcopy(tree)
                transformer = _ReturnEmptyTransformer(ret.lineno, ret.value)
                transformer.visit(new_tree)
                if not transformer._replaced:
                    continue
                try:
                    new_code = ast.unparse(new_tree)
                    if new_code == source_code:
                        continue
                    orig_repr = ast.unparse(ret.value)[:40]
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="return_empty",
                            description=f"line {ret.lineno}: return {orig_repr} → return 空容器（P0 3.3 返回类型变异）",
                            line_no=ret.lineno,
                        )
                    )
                    per_function[func.name] = per_function.get(func.name, 0) + 1
                except (ValueError, TypeError):
                    continue
        return mutants

    def _generate_return_voids(self, tree: ast.Module, source_code: str) -> list[Mutant]:
        """1.2 改进：返回值变异（return X → return None）。

        对每个"带非空返回值的 return 语句"（return 后跟表达式，且表达式
        不是 None 字面量）生成"改为 return None"的变异体。用途：检测测试
        是否真正校验了返回语义——若测试仅断言执行不报错而未检查返回值，
        该变异体会存活，提示测试缺"返回值断言"。

        保守口径：
        - 跳过 `return`（无值）与 `return None`（已是 None，无可变异）；
        - 每个函数体最多产 3 个返回值变异（避免大型函数变异体爆炸）；
        - unparse 失败或代码不变时跳过。
        """
        mutants: list[Mutant] = []
        per_function: dict[str, int] = {}
        for func in [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            for ret in [n for n in ast.walk(func) if isinstance(n, ast.Return)]:
                if ret.value is None:
                    continue  # 无值 return
                if isinstance(ret.value, ast.Constant) and ret.value.value is None:
                    continue  # 已是 return None
                if per_function.get(func.name, 0) >= 3:
                    continue  # 单函数上限 3 个
                new_tree = copy.deepcopy(tree)
                _ReturnVoidTransformer(ret.lineno, func.name).visit(new_tree)
                try:
                    new_code = ast.unparse(new_tree)
                    if new_code == source_code:
                        continue
                    mutants.append(
                        Mutant(
                            code=new_code,
                            mutant_type="return_void",
                            description=f"line {ret.lineno}: return {ast.unparse(ret.value)} → return None",
                            line_no=ret.lineno,
                        )
                    )
                    per_function[func.name] = per_function.get(func.name, 0) + 1
                except (ValueError, TypeError):
                    continue
        return mutants


class _ReturnVoidTransformer(ast.NodeTransformer):
    """按行号把指定 return 语句的返回值改写为 None（1.2 返回值变异用）。"""

    def __init__(self, target_lineno: int, func_name: str) -> None:
        """初始化（target_lineno 为目标 return 行号，func_name 仅供日志）。"""
        self._target_lineno = target_lineno
        self._func_name = func_name
        self._replaced = False

    def visit_Return(self, node: ast.Return) -> ast.AST:
        """命中目标行号的 return 时，把 value 替换为 None 常量。"""
        if (
            not self._replaced
            and node.lineno == self._target_lineno
            and node.value is not None
            and not (isinstance(node.value, ast.Constant) and node.value.value is None)
        ):
            self._replaced = True
            node.value = ast.Constant(value=None)
        return self.generic_visit(node)


class _ReturnEmptyTransformer(ast.NodeTransformer):
    """P0 3.3：按行号把指定 return 语句的返回值改写为空容器。

    检测"测试是否校验了返回类型"——return X 改为 return []（X 是 list）
    或 return ""（X 是 str），若测试断言了非空列表/字符串应被杀死。
    """

    def __init__(self, target_lineno: int, return_value_node: ast.AST) -> None:
        """初始化。

        Args:
            target_lineno: 目标 return 语句的行号。
            return_value_node: 原 return 值节点（用于判断返回类型，
                决定改写为空列表 / 空字符串 / 空 dict）。
        """
        self._target_lineno = target_lineno
        self._return_value_node = return_value_node
        self._replaced = False

    def _empty_replacement(self) -> ast.AST:
        """根据原返回值的类型选择空容器替换。

        - list/dict/set/Call(to list) → ast.List([])
        - str / f-string / JoinedStr → ast.Constant("")
        - 其他 → ast.Constant(None)（保守：无法判断类型时退回 None）
        """
        node = self._return_value_node
        if isinstance(node, ast.List) or (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "dict", "set")
        ):
            # 原返回值为列表字面量或 list()/dict() 调用 → 空容器
            if isinstance(node, ast.Dict):
                return ast.Dict(keys=[], values=[])
            if isinstance(node, ast.Set):
                return ast.Set(elts=[])
            # 保守用 List（list() 和 list 字面量都返回 list，dict 单独处理）
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "dict":
                    return ast.Dict(keys=[], values=[])
                if node.func.id == "set":
                    return ast.Set(elts=[])
            return ast.List(elts=[])
        if isinstance(node, (ast.Constant, ast.JoinedStr)):
            # 字符串字面量 / f-string → 空字符串
            return ast.Constant(value="")
        # 无法判断类型 → 保守退回 None
        return ast.Constant(value=None)

    def visit_Return(self, node: ast.Return) -> ast.AST:
        if (
            not self._replaced
            and node.lineno == self._target_lineno
            and node.value is not None
            and not (isinstance(node.value, ast.Constant) and node.value.value is None)
        ):
            self._replaced = True
            node.value = self._empty_replacement()
        return self.generic_visit(node)


class _RemoveRaiseTransformer(ast.NodeTransformer):
    """P0 3.3：按行号移除指定 raise 语句（异常路径变异用）。

    检测"测试是否校验了异常抛出"——移除 raise 后若测试用
    pytest.raises 校验了特定异常，测试应失败；存活说明测试未覆盖异常路径。

    保守口径：
    - 仅移除函数体内的 raise 语句（模块级 raise 不处理）；
    - 移除后在原地插入 `pass`（保持语法合法性，不产生空语句块）；
    - 每函数最多移除 3 个 raise（避免变异体爆炸）。
    """

    def __init__(self, target_lineno: int, func_name: str) -> None:
        """初始化（target_lineno 为目标 raise 行号，func_name 仅供日志）。"""
        self._target_lineno = target_lineno
        self._func_name = func_name
        self._removed = False

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        if not self._removed and node.lineno == self._target_lineno:
            self._removed = True
            # 替换为 pass（保持语法合法性）
            return ast.Pass()
        return self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        """改写函数体（让 generic_visit 继续下钻，捕获嵌套 raise 等）。"""
        return self.generic_visit(node)


class _ExceptionTypeTransformer(ast.NodeTransformer):
    """P0 3.3：修改异常类型（raise ValueError → raise TypeError，交替互换）。

    检测"测试是否校验了特定异常类型"——若测试用
    pytest.raises(ValueError) 校验了特定异常，把异常类型改坏后测试应失败；
    存活说明测试只校验"有异常"未校验"哪种异常"。

    保守口径：
    - 仅对 `raise X(...)` 形式（异常类型是 Name 节点）生效；
    - 仅处理常见内置异常互换对（ValueError ↔ TypeError、
      KeyError ↔ IndexError、RuntimeError ↔ ValueError）；
    - 每函数最多改 3 个（避免变异体爆炸）。
    """

    # 异常类型互换对（按 Name 节点）
    # RUF012：dict 类属性默认值改为 ClassVar 标注（惰性填充），避免告警
    _swap_pairs_cache: ClassVar[dict[str, str] | None] = None

    @classmethod
    def _get_swap_pairs(cls) -> dict[str, str]:
        if cls._swap_pairs_cache is None:
            cls._swap_pairs_cache = {
                "ValueError": "TypeError",
                "TypeError": "ValueError",
                "KeyError": "IndexError",
                "IndexError": "KeyError",
                "RuntimeError": "ValueError",
            }
        return cls._swap_pairs_cache

    def __init__(self, target_lineno: int, func_name: str, original_exc: str) -> None:
        """初始化。

        Args:
            target_lineno: 目标 raise 行号。
            func_name: 所属函数名（日志用）。
            original_exc: 原异常类型名（用于查互换对）。
        """
        self._target_lineno = target_lineno
        self._func_name = func_name
        self._original_exc = original_exc
        self._replaced = False

    def visit_Raise(self, node: ast.Raise) -> ast.AST:
        if not self._replaced and node.lineno == self._target_lineno and isinstance(node.exc, ast.Call):
            exc_name_node = node.exc.func
            if isinstance(exc_name_node, ast.Name):
                new_exc_name = self._get_swap_pairs().get(exc_name_node.id, "")
                if new_exc_name:
                    self._replaced = True
                    node.exc.func = ast.Name(id=new_exc_name, ctx=ast.Load())
        return self.generic_visit(node)


# 比较运算符 AST 类名 → 翻转目标映射
_OPERATOR_FLIP_MAP: dict[str, str] = {
    "Eq": "NotEq",
    "NotEq": "Eq",
    # 2026-09-26 全面审查（P1 修复配套）：严格/非严格比较（Lt/Gt 及 GtE/LtE）
    # 的对偶翻转与 boundary_shift 类型完全重叠（Lt→LtE 两者都生成同一份代码），
    # generate() 的代码级去重会把其中一类全部消除。为此 operator_flip 仅保留
    # 等值对（Eq↔NotEq，boundary_shift 不覆盖），严格比较的边界语义变异
    # 专属于 boundary_shift，两类互不重叠、各有独立变异体。
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

    2026-09-26 全面审查（P0 正确性修复）：此前 `return proc.returncode != 0`
    把 pytest 的**所有**非零退出码（含 2=收集错误 / ModuleNotFoundError /
    语法错误）一律当作"杀死"，与文档声明的保守口径（"执行失败（如 import
    错误）视为存活"）正好相反——实测 e2e 路径下测试文件 import 的模块名
    （如 `from module import check`）与写盘的 `mutated_module.py` 对不上时，
    每个变异体子进程都以收集错误退出（rc=2）→ 全部误判为"杀死" →
    mutation_score 恒 1.0，弱测试与强测试得分无法区分（指标失效）。
    现改为按 pytest 官方退出码精确判定：
    - rc == 1（有测试失败）→ 杀死（测试跑起来了且捕获了变异）；
    - rc == 0（全部通过）→ 存活（测试未能捕获）；
    - 其他（2/5/超时/异常）→ 存活（套件根本没成功运行，保守口径：
      不夸大变异得分）。

    Args:
        mutant: 变异体。
        test_code: 测试代码字符串。
        module_file: 被测模块文件路径。
        timeout_seconds: 单个变异体执行超时。

    Returns:
        True = 杀死，False = 存活。执行失败（如 import 错误）视为存活（保守口径）。
    """
    import os
    import subprocess
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

            # 执行测试：pytest 单文件（2026-09-26 全面审查：subprocess 改常规
            # 局部 import，与此处 os/sys/tempfile 口径一致，消除 __import__ 反模式）
            proc = subprocess.run(
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
            # 2026-09-26 全面审查：仅 rc==1（有测试失败）才算"杀死"。
            # rc==0（全通过）= 存活；rc==2/5（收集错误/无测试）或超时 =
            # 套件未成功运行，按保守口径视为存活（不误杀、不夸大得分）。
            return proc.returncode == 1
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


def build_mutation_feedback(
    source_code: str,
    test_code: str,
    max_mutants: int = 10,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """1.2 改进（MutGen 式变异反馈闭环）：生成变异反馈字典。

    对"生成测试 vs 被测代码"跑一遍变异测试，把"存活变异体"信息打包成
    可注入 Generator prompt 的反馈字典。闭环流程（在 run_benchmark 中消费）：
    1. 首轮生成测试 → 变异评估 → 得到存活变异体（未被测试捕获的故障模式）；
    2. 把存活变异体写回 state["mutation_feedback"]；
    3. Generator 再生成时消费该反馈，针对"未捕获的故障"补强断言；
    4. 再次变异评估，若得分提升说明闭环有效（形成"变异引导的测试增强"）。

    Args:
        source_code: 被测代码。
        test_code: 当前生成的测试代码。
        max_mutants: 最多评估的变异体数量（默认 10）。
        timeout_seconds: 单变异体超时。

    Returns:
        {"available": bool, "survived_mutants": [描述...],
         "killed_mutants": int, "mutants_total": int,
         "mutation_score": float | None}
        无变异体时 available=False，survived_mutants 为空。
    """
    generator = MutationGenerator()
    all_mutants = generator.generate(source_code)
    if not all_mutants:
        return {
            "available": False,
            "survived_mutants": [],
            "killed_mutants": 0,
            "mutants_total": 0,
            "mutation_score": None,
        }
    selected = all_mutants[:max_mutants]
    survived: list[str] = []
    killed = 0
    for mutant in selected:
        if _run_mutant_tests(mutant, test_code, module_file="", timeout_seconds=timeout_seconds):
            killed += 1
        else:
            # 存活变异体：记录其描述（变异类型 + 位置），供 prompt 注入
            survived.append(f"{mutant.description}（{mutant.mutant_type}）")
    score = round(killed / len(selected), 4) if selected else 0.0
    logger.info(
        "变异反馈闭环: 存活 %d / 总 %d，score=%.4f",
        len(survived),
        len(selected),
        score,
    )
    return {
        "available": True,
        "survived_mutants": survived,
        "killed_mutants": killed,
        "mutants_total": len(selected),
        "mutation_score": score,
    }


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
