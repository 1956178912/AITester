"""
AST 级断言一致性检查（Oracle Validator，默认关）。

背景（P2 神经符号融合方向 · Argus 式预言验证的保守落地）：
    LLM 生成的测试断言可能存在三类问题（"通过" ≠ "有效"）：
    1. 恒真断言（`assert True`、`assert x is not None` 且 x 刚被赋值）；
    2. 类型不一致（`assert f(x) == "str"` 但 f 返回 int）；
    3. 魔数未命名（`assert result == 42` 中 42 的语义不明）。

    本模块提供纯 AST 级的断言一致性检查（零 LLM 成本、零外部依赖）：
    - 检查 1（恒真断言）：AST 扫描所有 `assert` 语句，识别断言体
      为常量 True / 恒真表达式（`x is not None` 且 x 为同作用域刚赋值变量）；
    - 检查 2（类型不一致）：AST 推断断言两侧的类型标签
      （`== str` 但 LHS 为 int 返回值），不一致时标记疑点；
    - 检查 3（魔数检测）：断言中出现的未命名整型/浮点常量
      （非 0/1/2 的魔数），标记为"建议命名"疑点。

BJ 轮（2026-10-22，缺陷族 F03 静态侧）：本模块的"空疑点列表"此前既可能是
    "扫过且无疑点"，也可能是"根本没扫成"（输入空 / 文本读不懂 / 被测侧读不懂
    ⇒ 类型推断通道失效）。现 `check_assertions` 接受可选 `outcome_sink`，
    逐条披露 `{check, status, reason}`（词表与聚合方向取自
    `src/utils/check_status.py` 单一事实源），判定值与判定方向逐字节不变。

设计约束（与 ADR-0003 默认关 + ADR-0004 零默认依赖口径一致）：
    - `ORACLE_VALIDATE_ENABLE=false`（默认）时，本模块零行为变化；
    - 开关开启后，仅做 AST 静态分析（不消耗 LLM token），
      产出"疑点列表"（非阻断）供 Generator / 实验分析消费；
    - 疑点列表为空时返回 []，调用方保守降级不注入额外 prompt；但 BJ 轮起
      读取口径为"空 + status=ok 才是无疑点"，空 + error/disabled 只表示没读出；
    - 纯只读（不修改测试代码），疑点仅作观测层信号。

使用方式（_generator_node / 实验分析集成）：
    from src.tools.oracle_validator import (
        oracle_validate_enabled,
        check_assertions,
    )

    outcomes: list[dict[str, str]] = []
    if oracle_validate_enabled():
        findings = check_assertions(test_code, target_code, outcome_sink=outcomes)
        if findings:
            logger.info("断言一致性检查发现 %d 个疑点", len(findings))
"""

from __future__ import annotations

import ast
import logging
from typing import Any

from src.utils.check_status import (
    CHECK_DISABLED,
    CHECK_ERROR,
    CHECK_OK,
    parses_as_module,
    record_check_outcome,
)
from src.utils.env_utils import env_flag

logger = logging.getLogger(__name__)

#: markdown 代码围栏标记（整块围栏是"生成器把 ```python 块原样返回"的传输层伪影）
_FENCE_MARKER = "```"

# 魔数白名单：这些整型常量在测试中是常见的合法值（边界/单位/基数）
_TOLERATED_INTS: frozenset[int] = frozenset({0, 1, 2, -1, 10, 100, 256, 1000})

# 类型标签推断保守表（AST 常量类型 → 类型名）
_CONST_TYPE_MAP: dict[str, str] = {
    "int": "int",
    "float": "float",
    "str": "str",
    "bytes": "bytes",
    "bool": "bool",
    "NoneType": "None",
}


def oracle_validate_enabled() -> bool:
    """断言一致性检查开关（ORACLE_VALIDATE_ENABLE=true 时启用，默认 false）。"""
    return env_flag("ORACLE_VALIDATE_ENABLE")


def check_assertions(
    test_code: str,
    target_code: str | None = None,
    outcome_sink: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """对测试代码的 assert 语句做 AST 级一致性检查（零 LLM 成本）。

    检查项（保守口径，仅产出"疑点"非"结论"）：
    1. 恒真断言：assert True / assert x is not None（x 刚被赋值）；
    2. 魔数断言：assert result == N（N ∉ 白名单）→ 建议命名常量；
    3. 类型不一致：assert f(x) == "str"（LHS 推断为 int，RHS 为 str）。

    BJ 轮（2026-10-22）：``[]`` 此前是**四件事**共用的返回值——"扫过且无疑点"、
    "输入为空"、"测试文本读不懂（从未扫描）"、加上被测侧的"读不懂 ⇒ 类型推断
    通道静默失效"。生产实测语料（手册 §3）：10855 条 ``generated_test`` 中
    153 条（77 空 + 76 读不懂）走的就是后两条腿，消费侧
    ``_run_generator_postchecks`` 把它们读成 ``tautological_count = 0`` ⇒
    O4"恒真断言强制重生成"对**读不懂的产物**永不触发。现按 sink 逐条披露
    ``{check, status, reason}``，**返回值与判定方向逐字节不变**，只补可测量性。
    唯一披露的口径变化：解析改走 ``parses_as_module``，孤立代理位文本触发的
    ``UnicodeEncodeError``（``SyntaxError`` 之外的 ``ValueError`` 子类）不再抛穿
    本函数，按"读不懂"处理（与 BH/BI 同口径，手册 §5 登记 + 锁）。

    Args:
        test_code: 生成的 pytest 测试代码字符串。
        target_code: 被测代码全文（可选，提供时增强类型推断精度）。
        outcome_sink: 可选列表，逐条追加 ``{check, status, reason}``（None 零开销）。
            至多两条：``assertion_consistency``（必记）与 ``target_type_inference``
            （仅在提供了 ``target_code`` 时记）。

    Returns:
        疑点列表，每项含：
        - "type": 疑点类型（"tautological" | "magic_number" | "type_mismatch"）
        - "line": 行号（int）
        - "message": 人类可读的描述
        - "suggestion": 改进建议（可选）
        无问题时返回空列表（**只在 sink 的 ``assertion_consistency`` 为
        ``ok`` 时**才是"断言无疑点"的证据）。
    """
    if not test_code or not test_code.strip():
        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_DISABLED, "empty_input")
        return []

    if not parses_as_module(test_code):
        # 测试代码本身读不懂 → 从未做过任何 assert 扫描，保守返回空（不阻断主流程）。
        # 但"空疑点列表"此时**不是**"断言干净"的证据：BJ 轮前它与真干净逐字节相同。
        record_check_outcome(outcome_sink, "assertion_consistency", CHECK_ERROR, _unparseable_test_reason(test_code))
        return []

    tree = ast.parse(test_code)

    findings: list[dict[str, Any]] = []
    assert_nodes = [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    record_check_outcome(
        outcome_sink,
        "assertion_consistency",
        CHECK_OK,
        "assertions_checked" if assert_nodes else "no_assert_statements",
    )

    # 收集被测代码中的函数名（用于推断调用返回值类型）
    target_func_names: set[str] = set()
    target_return_types: dict[str, str] = {}
    if not target_code:
        record_check_outcome(outcome_sink, "target_type_inference", CHECK_DISABLED, "target_not_provided")
    elif not parses_as_module(target_code):
        # 被测侧读不懂 → 类型推断表恒空 ⇒ type_mismatch 疑点通道实际关闭（旧口径静默）。
        record_check_outcome(outcome_sink, "target_type_inference", CHECK_ERROR, "unparseable_target")
    else:
        target_tree = ast.parse(target_code)
        record_check_outcome(outcome_sink, "target_type_inference", CHECK_OK, "target_parsed")
        for node in ast.walk(target_tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                target_func_names.add(node.name)
                # 推断返回类型（保守：只看简单的 return 常量）
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Return) and sub.value:
                        rt = _infer_constant_type(sub.value)
                        if rt:
                            target_return_types[node.name] = rt
                            break
                        # 非常量返回值（如 BinOp）→ 保守推断为 int（算术运算）
                        if isinstance(sub.value, ast.BinOp):
                            target_return_types[node.name] = "int"
                            break

    for node in assert_nodes:
        _check_assert_node(node, test_code, target_func_names, target_return_types, findings)

    return findings


def _unparseable_test_reason(test_code: str) -> str:
    """读不懂测试文本时区分"整块 markdown 围栏"与"真语法错误"（仅用于披露）。

    判据是"剥掉前导空白后以 ````` ``` ````` 开头"：实测语料（BJ 轮手册 §3）里
    这类占 72/76——生成器把整块 ```` ```python … ```` 当作测试文件返回，属传输层
    伪影；余下 4 条是产物本身的语法缺陷（缩进丢失等）。两者判定值相同（均返回
    ``[]``），但归因不同，读数侧需要能分开。围栏出现在正文中间（模型答了一段
    带代码块的解释）按 ``syntax`` 报——对 AST 而言它确实是语法错误，不自愈。
    """
    stripped = test_code.lstrip()
    if stripped.startswith(_FENCE_MARKER):
        return "unparseable_test:fenced_block"
    return "unparseable_test:syntax"


def _infer_constant_type(expr: ast.expr) -> str | None:
    """推断 AST 表达式节点的常量类型标签（保守：仅识别字面量常量）。"""
    if isinstance(expr, ast.Constant):
        if isinstance(expr.value, bool):
            return "bool"
        if isinstance(expr.value, int):
            return "int"
        if isinstance(expr.value, float):
            return "float"
        if isinstance(expr.value, str):
            return "str"
        if isinstance(expr.value, bytes):
            return "bytes"
        if expr.value is None:
            return "None"
    return None


def _is_tautological_assert(assert_expr: ast.expr) -> bool:
    """判断断言体是否为恒真表达式。

    O4（2026-09-29 审查 P1）：恒真判定修正 + 4 类漏检补充。
    历史口径：仅识别 `assert True` 和 `x is not None` 两种模式。
    现补充 4 类漏检（均为浅层 reaching-definition 判定，保守口径）：
    1. 自反比较：`assert x == x` / `assert x is x`（恒真）；
    2. 逻辑恒真：`assert x or not x`（德·摩根恒真式）；
    3. 范围恒真：`assert len(x) >= 0` / `assert len(x) < 0` 取反（len 永远非负）；
    4. 自包含：`assert x in x`（元素恒属于自身集合/序列）。
    原两类保留：
    5. `assert True`（常量 True）；
    6. `x is not None`（浅层 reaching-definition：x 为同作用域刚赋值的局部变量）。
    """
    # 1. 常量 True
    if isinstance(assert_expr, ast.Constant) and assert_expr.value is True:
        return True
    # 2. x is not None（浅层 reaching-definition）
    if (
        isinstance(assert_expr, ast.Compare)
        and len(assert_expr.ops) == 1
        and isinstance(assert_expr.ops[0], ast.IsNot)
        and len(assert_expr.comparators) == 1
        and isinstance(assert_expr.comparators[0], ast.Constant)
        and assert_expr.comparators[0].value is None
    ):
        return True
    # 3. O4 漏检：自反比较 assert x == x / assert x is x
    if (
        isinstance(assert_expr, ast.Compare)
        and len(assert_expr.ops) == 1
        and len(assert_expr.comparators) == 1
        and isinstance(assert_expr.ops[0], (ast.Eq, ast.Is))
        and isinstance(assert_expr.left, ast.Name)
        and isinstance(assert_expr.comparators[0], ast.Name)
        and assert_expr.left.id == assert_expr.comparators[0].id
    ):
        return True
    # 4. O4 漏检：逻辑恒真 assert x or not x / assert x and not x
    if isinstance(assert_expr, ast.BoolOp) and len(assert_expr.values) == 2:
        v0, v1 = assert_expr.values
        # x or not x（v0=Name, v1=Unary(Not, Name) 同名）
        if (
            isinstance(assert_expr.op, ast.Or)
            and isinstance(v0, ast.Name)
            and isinstance(v1, ast.UnaryOp)
            and isinstance(v1.op, ast.Not)
            and isinstance(v1.operand, ast.Name)
            and v0.id == v1.operand.id
        ):
            return True
        # x and not x（v0=Name, v1=Unary(Not, Name) 同名）——恒假，也标记为恒真（无信息量）
        if (
            isinstance(assert_expr.op, ast.And)
            and isinstance(v0, ast.Name)
            and isinstance(v1, ast.UnaryOp)
            and isinstance(v1.op, ast.Not)
            and isinstance(v1.operand, ast.Name)
            and v0.id == v1.operand.id
        ):
            return True
    # 5. O4 漏检：范围恒真 assert len(x) >= 0 / assert len(x) < 0（恒真）
    # 6. O4 漏检：自包含 assert x in x（元素恒属于自身序列/集合）
    # 检查 5 与 6 合并为单一 return（避免 SIM "inline condition" 嵌套模式）
    if isinstance(assert_expr, ast.Compare) and len(assert_expr.ops) == 1 and len(assert_expr.comparators) == 1:
        op = assert_expr.ops[0]
        left = assert_expr.left
        comp = assert_expr.comparators[0]
        # 5. len(x) >= 0 / len(x) < 0（len 永远非负，两种比较均无信息量）
        if (
            isinstance(comp, ast.Constant)
            and comp.value == 0
            and isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "len"
            and isinstance(op, (ast.GtE, ast.Lt))
        ):
            return True
        # 6. x in x（自包含，恒真）
        if isinstance(op, ast.In) and isinstance(left, ast.Name) and isinstance(comp, ast.Name) and left.id == comp.id:
            return True
    return False


def _check_assert_node(
    node: ast.Assert,
    source: str,
    target_func_names: set[str],
    target_return_types: dict[str, str],
    findings: list[dict[str, Any]],
) -> None:
    """检查单个 assert 节点，把疑点追加到 findings。"""
    line = node.lineno if hasattr(node, "lineno") else 0
    expr = node.test

    # 检查 1：恒真断言
    if _is_tautological_assert(expr):
        findings.append(
            {
                "type": "tautological",
                "line": line,
                "message": f"第 {line} 行：恒真断言（永远通过，无法检测缺陷）",
                "suggestion": "替换为基于函数行为的具体断言（如 assert result == expected）",
            }
        )
        return  # 恒真断言无需后续检查

    # 检查 2：魔数断言（assert result == N，N ∉ 白名单）
    if isinstance(expr, ast.Compare):
        _check_magic_numbers(expr, line, target_func_names, target_return_types, findings)
        # 检查 3：类型不一致（LHS/RHS 推断类型不匹配）
        _check_type_mismatch(expr, line, target_func_names, target_return_types, findings)


def _check_magic_numbers(
    compare: ast.Compare,
    line: int,
    target_func_names: set[str],
    target_return_types: dict[str, str],
    findings: list[dict[str, Any]],
) -> None:
    """检查断言比较中是否含魔数（∉ 白名单的整型/浮点常量）。"""
    if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq):
        return
    # 检查 LHS / RHS 中的常量
    for side in [compare.left, *compare.comparators]:
        for const in ast.walk(side):
            if isinstance(const, ast.Constant):
                val = const.value
                # 整型魔数（∉ 白名单 且 非 0/1/-1/2 等）
                if isinstance(val, int) and not isinstance(val, bool):
                    if val not in _TOLERATED_INTS and abs(val) > 2:
                        findings.append(
                            {
                                "type": "magic_number",
                                "line": line,
                                "message": f"第 {line} 行：断言使用未命名魔数 {val}，语义不明确",
                                "suggestion": f"建议提取为命名常量（如 EXPECTED_XXX = {val}）",
                            }
                        )
                # 浮点魔数（非简单 0.5/0.1 等）
                elif isinstance(val, float) and abs(val) > 0.01:
                    findings.append(
                        {
                            "type": "magic_number",
                            "line": line,
                            "message": f"第 {line} 行：断言使用未命名浮点魔数 {val}",
                            "suggestion": "建议提取为命名常量并注释含义",
                        }
                    )


def _check_type_mismatch(
    compare: ast.Compare,
    line: int,
    target_func_names: set[str],
    target_return_types: dict[str, str],
    findings: list[dict[str, Any]],
) -> None:
    """检查断言比较两侧的类型标签是否一致（保守推断，仅处理简单情况）。"""
    if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq):
        return
    # 仅处理 `func(...) == literal` 或 `literal == func(...)` 模式
    lhs = compare.left
    rhs = compare.comparators[0] if compare.comparators else None
    if rhs is None:
        return

    # 尝试推断 LHS / RHS 类型
    lhs_type = _infer_expr_type(lhs, target_func_names, target_return_types)
    rhs_type = _infer_expr_type(rhs, target_func_names, target_return_types)
    if (
        lhs_type
        and rhs_type
        and lhs_type != rhs_type
        and not {(lhs_type, rhs_type)} & {("int", "bool"), ("bool", "int")}
    ):
        findings.append(
            {
                "type": "type_mismatch",
                "line": line,
                "message": f"第 {line} 行：断言两侧类型不一致（LHS 推断为 {lhs_type}，RHS 为 {rhs_type}）",
                "suggestion": "检查函数返回值类型或断言预期的类型是否匹配",
            }
        )


def _infer_expr_type(
    expr: ast.expr,
    target_func_names: set[str],
    target_return_types: dict[str, str],
) -> str | None:
    """推断 AST 表达式的类型标签（保守：仅识别常量字面量与目标函数调用）。"""
    # 常量字面量
    const_type = _infer_constant_type(expr)
    if const_type:
        return const_type
    # 目标函数调用 → 查表推断返回类型
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name):
        fname = expr.func.id
        if fname in target_func_names:
            return target_return_types.get(fname)
    # 二元运算（如 x + 1）→ 推断为 int（保守：算术运算结果为 int/float）
    if isinstance(expr, ast.BinOp):
        return "int"
    # 变量（Name）→ 无法推断，返回 None（保守）
    return None


def oracle_validator_stats() -> dict[str, Any]:
    """断言一致性检查的观测统计（供 get_workflow_stats 消费，纯读操作）。"""
    return {
        "enabled": oracle_validate_enabled(),
        "tolerated_ints": sorted(_TOLERATED_INTS),
    }


__all__ = [
    "check_assertions",
    "oracle_validate_enabled",
    "oracle_validator_stats",
]
