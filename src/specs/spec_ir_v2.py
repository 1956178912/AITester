"""SpecIR v2：受限表达式 DSL 层（A-01，2026-10 优化批次·P0）。

背景（2026-10-04 系统审查 A-01）：
    SpecIR v1（R7）把自然语言规约解析为 SpecIR dict，但 pre/post/invariant
    仍是 **str 列表（自然语言）**——NL 规约无语法、无类型、不可机器验证，
    "逻辑驱动"主张不可证伪；compile_to_hypothesis 对 NL 规约只能产出
    占位断言（assert True + 注释），确定性 oracle 通道路径上无拦截能力。
    主批次 M1 数字（false_fix=89.8%，BASELINE.yaml）实证了该缺口。

本模块（v2，纯 stdlib，零新默认依赖）：
    1. **受限表达式 DSL**（SpecExpr）：白名单 AST 节点子集
       （比较 / 布尔 / 算术 / 常量 / 函数白名单调用 / 容器下标·长度），
       把 Planner 规约字段中"形如表达式"的子句机器化；NL 原文保留为
       provenance（spec_provenance），机器化部分进 spec_exprs；
    2. **可编译性判定**（compile_readiness）：一个 SpecIR 的
       pre/post/invariant 可编译率 = 可解析为 SpecExpr 子句数 / 非空子句数，
       入 M1 metrics_schema（"逻辑驱动"主张的可测量内核：
       可编译率 0% = 纯 LLM 话术；>0% = 确定性 oracle 在线拦截）；
    3. **确定性 oracle 编译**（compile_spec_oracle）：
       - preconditions（输入约束）→ pytest 参数化前置断言（输入不合法时
         预期抛出 / 行为受限——保守：只断言"输入满足前件"，LLM 自由
         断言之外的机器锚点）；
       - postconditions（后置约束，形如 `r > 0` / `r == a + b`）→
         编译为 `assert <expr>`（变量绑定 r = func(input)），确定性断言；
       - invariants → 同后置口径（任意输入下成立的性质，保守编译为
         "给定边界输入时成立"的断言）；
       - 不可解析子句 → 逐条降级为 NL 注释（不产出占位 assert True——
         与 v1 不同：v2 明确区分"可执行断言"与"NL 溯源注释"，
         杜绝假通过通道）。

设计口径（与 ADR-0003 一致：默认关，新开关独立）：
    - SPEC_IR_DSL_ENABLE=true 时启用（默认 false，历史口径零变化）；
    - 本模块是纯静态函数（无 LLM / 无子进程），失败路径保守返回 [] / 0.0；
    - compile_spec_oracle 的产物恒为可执行 Python（ast.parse 自检，
      不合法时保守丢弃该条，不产出坏代码）。
"""

from __future__ import annotations

import ast
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_ENV_DSL = "SPEC_IR_DSL_ENABLE"

# ─── 白名单常量（保守：只放行"测试生成场景"需要的表达式形态）────────────
# 允许出现的调用名（函数白名单）：纯 Python 内置无副作用判定函数 +
# len/abs（数值/容器边界判定常用）。其他调用（open/eval/任意属性链深度>2）
# 一律不可编译（保守降级为 NL 注释，防"规约里藏命令"的注入面）。
_ALLOWED_CALL_NAMES: frozenset[str] = frozenset(
    {"len", "abs", "min", "max", "round", "float", "int", "str", "sorted", "any", "all"}
)
# 允许的下标 / 长度属性（容器边界锚点）：len(x) 之外的属性访问仅放行
# 白名单属性（防 x.__class__ 类 introspection 逃逸）
_ALLOWED_ATTRS: frozenset[str] = frozenset({"len", "value", "real", "imag"})
# 数值 / 字符串 / 布尔 / None / 容器字面量：全放行（ast 字面量）


def spec_ir_dsl_enabled() -> bool:
    """SpecIR v2 DSL 层开关（SPEC_IR_DSL_ENABLE=true 时启用，默认 false）。

    默认关闭：本模块所有函数仍保持可导入（纯静态），但 _generator_node /
    _planner_node 的 DSL 编译调用点均以此开关守门（与 R7 SpecIR 主开关
    解耦——SpecIR v1 已默认关，v2 双层默认关，历史口径零变化）。
    """
    return os.getenv(_ENV_DSL, "false").lower() in ("true", "1", "on")


# ─── 1. 子句识别（NL 字符串 vs 表达式形态）────────────────────────────────
# 保守判据：整条子句可被 ast.parse 为单个表达式且**不含**语句/赋值/
# 控制流关键字时才视为"表达式子句"（可机器化）。
# 注意：`a > 0` 是合法表达式；"x 是正整数" 是 NL（parse 失败 → 不可编译）；
# `r = f(x)` 是赋值语句（Expr 子节点为 Assign 时拒绝——规约里出现
# 赋值是 LLM 话术，不机器化，保守 NL 注释）。
_EXPR_TOKEN_RE = re.compile(r"^\s*[A-Za-z_\d\[\]\(\).\-+*/%<>=!&|~^, \"]*$")


def is_expression_clause(clause: Any) -> bool:
    """判定规约子句是否为"机器可解析表达式"形态（保守：双通道验证）。

    通道 1（字符白名单快判）：子句只含表达式可出现的字符（标识符 /
        数字 / 运算符 / 括号 / 引号 / 点号 / 下标）；NL 子句（含
        中文 / 空格动词）直接排除（零误报快路径，省 ast.parse 开销）；
    通道 2（ast 精确判）：ast.parse(clause, mode="eval") 成功且顶层
        为单一 Expr 节点（拒绝赋值语句 / 多语句 / 控制流）。

    任一通道失败 → False（保守：宁可降为 NL 注释，不产出坏断言）。
    """
    if not isinstance(clause, str):
        return False
    text = clause.strip()
    if not text or len(text) > 200:
        return False
    # 通道 1：字符白名单（中文 / 动词短语必含白名单外字符 → 快速排除）
    if not _EXPR_TOKEN_RE.match(text):
        return False
    # 通道 2：ast 精确判（mode="eval" 顶层必须是 Expr，Assign 等语句
    # 在 eval 模式下 parse 失败 → 自动拒绝）
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError):
        return False
    # 顶层为单一 Expr 节点（Assign 等语句在 eval 模式 parse 失败 → 自动拒绝）
    return isinstance(tree.body, (ast.Expr, ast.Compare))


# ─── 2. SpecExpr 白名单验证（可执行化前置安全闸）──────────────────────────
# 表达式通过 is_expression_clause 后仍需"白名单节点"验证：只允许
# 白名单内的调用名 / 属性 / 操作符出现（防规约子句藏危险调用——
# 如 len(open('/etc/passwd')) 的嵌套注入面）。


class _WhitelistVisitor(ast.NodeVisitor):
    """SpecExpr 白名单验证器（收集违例，不 raise——返回违例列表）。

    违例类型：
    - dangerous_call: 调用名不在 _ALLOWED_CALL_NAMES（如 os.system）；
    - attr_escape: 属性访问不在 _ALLOWED_ATTRS 且不是 len() 调用；
    - stmt_in_expr: 表达式子树含语句节点（eval 模式理论不可达，双保险）；
    - unknown_operator: 非常规运算符（AugmentedAssign 等 eval 不可达，双保险）。
    """

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:
        # 调用名白名单（Name 直调）；Attribute 链（os.system）取末段名
        name: str | None = None
        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr  # 末段属性名（len 之外的 attr 由 attr_escape 拦截）
        if name is None or name not in _ALLOWED_CALL_NAMES:
            self.violations.append(f"dangerous_call:{name or '(opaque)'}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        # 属性白名单：len 之外的属性访问（如 .real/.value）需白名单
        if node.attr not in _ALLOWED_ATTRS:
            self.violations.append(f"attr_escape:{node.attr}")
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        # eval 模式顶层 Expr 放行；子树内 Expr 不应出现（语句形态）
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        for child in ast.iter_child_nodes(node):
            self.visit(child)


def _whitelist_check(expr_text: str) -> list[str]:
    """对白名单内的表达式做"可执行节点"验证，返回违例列表（空 = 全通过）。"""
    try:
        tree = ast.parse(expr_text, mode="eval")
    except (SyntaxError, ValueError):
        return ["parse_failed"]
    visitor = _WhitelistVisitor()
    visitor.visit(tree)
    return visitor.violations


# ─── 3. 编译产物（确定性 oracle）────────────────────────────────────────────
# 编译产物恒为可执行 pytest 代码。结构：
#   1) import + 被测函数绑定（r = func(input...)）
#   2) 可编译 precondition 断言（输入约束：不满足时预期异常 →
#      pytest.raises 包裹；保守：只对"数值/容器边界"类前件用
#      assert 预检查，不臆测异常类型——臆测会引入假阳性）
#   3) 可编译 postcondition 断言（assert <expr>，变量已绑定）
#   4) 不可编译子句 → 逐条 "# NL provenance: <clause>" 注释（明确标注
#      "未机器化，LLM 断言仍负责该条"，杜绝 v1 的占位 assert True）


def _compile_single_clause(
    clause: str,
    kind: str,
    target_module: str = "",
    target_function: str = "",
    known_names: frozenset[str] | None = None,
) -> str:
    """把单个可编译子句编译为一行 pytest 代码（保守失败 → 返回空串）。

    kind:
    - "precondition"  → `assert <expr>`（对已绑定输入变量）
    - "postcondition" / "invariant" → `assert <expr>`（对已绑定结果变量 r）

    known_names: 可编译标识符白名单。None = 使用默认绑定集合
    （r/x/a/b + 调用白名单名 + 常量）；compile_spec_oracle 按实际
    绑定上下文显式传入（与"产物自检"口径一致：未知变量 → 不编译）。

    保守口径（不臆测行为）：
    - 子句变量名不在绑定上下文（输入参数名 / 结果变量 r / 白名单常量）时，
      保守降级为 NL 注释（不产出 NameError 的坏断言）；
    - 白名单违例（危险调用 / 属性逃逸）→ 降级 NL 注释；
    - 编译产物 ast.parse 自检失败 → 降级 NL 注释。
    """
    violations = _whitelist_check(clause)
    if violations:
        return ""  # 调用方按 NL 注释处理
    # 变量绑定上下文：结果变量 r + 单参数场景的入参名（保守：只用 r / x / a / b）
    base_known = (
        known_names
        if known_names is not None
        else frozenset({"r", "x", "a", "b"} | _ALLOWED_CALL_NAMES | {"True", "False", "None"})
    )
    identifiers = {n.id for n in ast.walk(ast.parse(clause, mode="eval")) if isinstance(n, ast.Name)}
    unknown = identifiers - base_known
    if unknown:
        return ""
    line = f"assert {clause.strip()}"
    # 产物自检：assert 行必须语法合法（防白名单漏网）
    try:
        ast.parse(line)
    except (SyntaxError, ValueError):
        return ""
    return line


def compile_spec_oracle(
    spec: dict[str, Any] | None,
    target_module: str = "",
    target_function: str = "",
    signature_params: list[str] | None = None,
) -> str:
    """把 SpecIR 的**可编译子句**编译为确定性 oracle 测试代码（A-01 v2）。

    与 v1 compile_to_hypothesis 的关系：本函数是"可执行断言"层（保守，
    恒可运行）；v1 的边界参数化层不变（v2 不触碰）。本层产物
    与 LLM 生成测试**并行**（不替代 LLM 断言，是"LLM 之外"的机器锚点：
    LLM 生成的测试通过 ≠ 机器 oracle 通过——后者才计入 M1 确定性检测）。

    R1b（2026-10-05 审查 R6 修复）：签名感知绑定。signature_params 为
    被测函数的真实参数名列表（经 spec_ir.extract_signature_params 从
    AST 签名提取）时：
    - 绑定上下文 known_names 扩展为 {r} ∪ signature_params（替代硬编码
      {r,x,a,b,y}——多参数 / 关键字参数 / 自定义参数名函数的规约子句
      从"必然不可编译"变为可编译）；
    - 调用元数按签名修正：单参函数不再误产 `func(a, b)`（TypeError），
      多参边界输入（tuple/list）按 `func(*args)` 展开；
    - 无边界材料时的保守字面量绑定按签名前 1~2 个参数名命名。
    signature_params 语义（三态）：None = 签名未知（历史绑定集合与行为
    逐字节不变）；[] = 0 参函数（无可绑定输入，保守返回空串）；
    非空 = 按签名绑定。

    产物结构（target_module/target_function 缺失时返回空串，保守）：
        # SpecIR v2 确定性 oracle（compile_readiness=<rate>）
        from <module> import <func>
        def test_specir_v2_oracle():
            <绑定 / 断言 / NL 注释>

    Args:
        spec: parse_logic_analysis 的产物（pre/post/invariant 为 str 列表）。
        target_module: 被测模块名（import 用）。
        target_function: 被测函数名（调用用）。
        signature_params: 被测函数参数名列表（None = 历史默认绑定集合）。

    Returns:
        测试代码字符串；无 spec / 无模块名 / 无任何可编译子句时返回空串
        （保守：不产出"只有注释无断言"的空测试——空测试会假通过）。
    """
    if not spec or not target_module or not target_function:
        return ""
    pre = [c for c in (spec.get("preconditions") or []) if isinstance(c, str)]
    post = [c for c in (spec.get("postconditions") or []) if isinstance(c, str)]
    inv = [c for c in (spec.get("invariants") or []) if isinstance(c, str)]

    # 可编译子句的绑定上下文（R1b 签名感知）：
    # - signature_params 非 None（签名已知，含 [] = 0 参）：{r} ∪ 签名参数名
    #   （真实绑定变量，覆盖多参数场景；0 参时仅 {r}）；
    # - None（签名未知 / 未提取到）：历史默认集合 {r,x,a,b,y}（行为不变口径）。
    # 两种口径均并入调用白名单 + 布尔/None 常量，未知标识符 → 不编译
    # （保守，防 NameError 断言）。
    if signature_params is not None:
        known_names = frozenset({"r"} | set(signature_params) | _ALLOWED_CALL_NAMES | {"True", "False", "None"})
    else:
        known_names = frozenset({"r", "x", "a", "b", "y"} | _ALLOWED_CALL_NAMES | {"True", "False", "None"})
    pre_lines: list[str] = []
    for clause in pre:
        compiled = _compile_single_clause(clause, "precondition", target_module, target_function, known_names)
        if compiled:
            pre_lines.append(f"    # pre: {clause}")
            pre_lines.append(f"    {compiled}")
        else:
            pre_lines.append(f"    # NL provenance (uncompiled pre): {clause}")

    post_lines: list[str] = []
    for clause in post + inv:
        # post 与 invariant 共用后置断言口径（invariant = 任意输入下的性质，
        # 保守编译为"在边界输入下成立"——不臆测全输入域）
        compiled = _compile_single_clause(clause, "postcondition", target_module, target_function, known_names)
        if compiled:
            kind_tag = "post" if clause in post else "invariant"
            post_lines.append(f"    # {kind_tag}: {clause}")
            post_lines.append(compiled.replace("assert ", "    assert ", 1))
        else:
            post_lines.append(f"    # NL provenance (uncompiled post): {clause}")

    pre_compiled_n = sum(
        1 for c in pre if _compile_single_clause(c, "precondition", target_module, target_function, known_names)
    )
    post_compiled_n = sum(
        1 for c in post + inv if _compile_single_clause(c, "postcondition", target_module, target_function, known_names)
    )
    total_n = len(pre) + len(post) + len(inv)
    readiness = (pre_compiled_n + post_compiled_n) / total_n if total_n else 0.0

    # 无任何可编译子句 → 保守返回空串（不产出无断言的空测试）
    if pre_compiled_n + post_compiled_n == 0:
        return ""

    lines: list[str] = [
        f"# SpecIR v2 确定性 oracle（compile_readiness={readiness:.2f}）",
        f"from {target_module} import {target_function}",
        "",
        "def test_specir_v2_oracle():",
    ]
    # 绑定上下文（保守分层，杜绝 NameError 断言）：
    # 层 1（有边界输入材料）：按签名元数绑定——
    #   - signature_params 有效：
    #     · 单参 + input 非 tuple/list → <p0> = <input>; r = func(<p0>)
    #     · 多参 + input 为 tuple/list → args = <input>; r = func(*args)
    #     · 0 参（签名感知下才发现的边界，保守跳过不臆测输入）
    #   - signature_params 缺席（历史口径）：x = <input>; r = func(x)
    # 层 2（无边界输入）：保守数值字面量 0 绑定——
    #   - signature_params 有效：按签名前 1~2 个参数名（修正历史
    #     `a, b = 0, 0` + `func(a, b)` 对单参/0 参函数的 TypeError）；
    #   - 缺席：a, b = 0, 0（历史口径不变）。
    # 层 3（无任何输入材料路径不可达）：无绑定不臆测，return ""
    #   （防"无断言测试"假通过）。
    # 注意：层 2 的字面量 0 绑定可能本身违反前置条件（preconditions）——
    # 已知保守权衡（有边界材料时层 1 优先，层 2 仅在无任何边界时兜底）。
    boundaries = [b for b in (spec.get("boundaries") or []) if b.get("input") is not None]
    if boundaries:
        # P0（2026-10-05 独立审查）：边界输入字面量类型矫正。derive_boundary_triplets
        # 历史产出字符串型 input（如 "4"），直绑成 str 字面量 `'4'` 会让 int 型被测
        # 函数在运行期 TypeError——"确定性检出"通道变"确定性假检出"通道。
        # 数字字符串（含容器元素）保守转 int/float；转换失败保持原值（不臆测）。
        first_input = _coerce_boundary_literal(boundaries[0]["input"])
        if signature_params is not None:
            if len(signature_params) == 1 and not isinstance(first_input, (tuple, list)):
                p0 = signature_params[0]
                lines.append(f"    {p0} = {first_input!r}")
                lines.extend(pre_lines)
                lines.append(f"    r = {target_function}({p0})")
                lines.extend(post_lines)
            elif len(signature_params) >= 2 and isinstance(first_input, (tuple, list)):
                lines.append(f"    args = {first_input!r}")
                lines.extend(pre_lines)
                lines.append(f"    r = {target_function}(*args)")
                lines.extend(post_lines)
            else:
                # 元数/形态不匹配（0 参、单参配 tuple、多参配标量等）：
                # 保守不绑定（不臆测输入如何映射到参数），返回空串
                return ""
        else:
            lines.append(f"    x = {first_input!r}")
            lines.extend(pre_lines)
            lines.append(f"    r = {target_function}(x)")
            lines.extend(post_lines)
    else:
        pre_refs_ab = [c for c in pre if c and any(v in c for v in ("a", "b", "y"))]
        if signature_params is not None:
            if not signature_params:
                return ""  # 0 参函数无输入可绑定，不臆测
            if len(signature_params) == 1:
                p0 = signature_params[0]
                lines.append(f"    {p0} = 0")
                lines.extend(pre_lines)
                lines.append(f"    r = {target_function}({p0})")
                lines.extend(post_lines)
            else:
                p0, p1 = signature_params[0], signature_params[1]
                lines.append(f"    {p0}, {p1} = 0, 0")
                lines.extend(pre_lines)
                lines.append(f"    r = {target_function}({p0}, {p1})")
                lines.extend(post_lines)
        elif pre_refs_ab:
            lines.append("    a, b = 0, 0")
            lines.extend(pre_lines)
            lines.append(f"    r = {target_function}(a, b)")
            lines.extend(post_lines)
        else:
            return ""
    code = "\n".join(lines)
    # 产物总自检（ast 不合法 → 保守返回空串，不产出坏代码）
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        logger.warning("SpecIR v2 oracle 产物自检失败，保守丢弃（防坏代码注入执行链路）")
        return ""
    # 产物必须有可执行断言（无 assert 行 = 假通过空测试 → 保守丢弃）
    if not any(line.strip().startswith("assert") for line in lines):
        return ""
    # G4（2026-10-05 优化批次·T2）：SPEC_SMT_ENABLE=true 且 z3 可用时，
    # 追加 SMT 见证测试（前件驱动的求解器输入，与主 oracle 并列执行）。
    # 开关关 / z3 缺失 / 无可翻译前件 → witness 段为空，产物与历史逐字节一致。
    witness_code = _compile_smt_witness_tests(spec, signature_params, pre_lines, post_lines, target_function)
    if witness_code:
        code = f"{code}\n\n{witness_code}"
    return code


def _coerce_boundary_literal(value: Any) -> Any:
    """把边界输入中的数字字符串字面量保守转为 int/float（P0 类型矫正）。

    规则（宁保持原值，不臆测）：
    - int / float / bool / None → 原样返回；
    - str → 仅当整体可 ast.literal_eval 为 int/float 时转换（"4"→4，
      "2.5"→2.5；"abc"/"4 "→"abc"/"4 " 保持原串）；
    - list → 逐元素递归转换（保持 list 形态，供多参 *args 展开）；
    - 其他类型（tuple/dict 等）→ 原样返回。

    源头层（logic_spec.derive_boundary_triplets）已同步产出类型化数值，
    本层兜底覆盖 LLM logic_analysis 产出的字符串型结构化边界。
    """
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            parsed = ast.literal_eval(value)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            return value
        if isinstance(parsed, (int, float)) and not isinstance(parsed, bool):
            return parsed
        return value
    if isinstance(value, list):
        return [_coerce_boundary_literal(v) for v in value]
    return value


def _compile_smt_witness_tests(
    spec: dict[str, Any] | None,
    signature_params: list[str] | None,
    pre_lines: list[str],
    post_lines: list[str],
    target_function: str,
) -> str:
    """把 SpecSMT 见证编译为并列的 pytest 见证测试（保守失败 → 空串）。

    每个见证产出一个 ``test_specir_v2_smt_witness_<i>``：绑定见证输入 →
    断言前件（求解器已保证 Python 语义成立，见 spec_smt._extract 复核）→
    调用被测函数 → 断言后件（与主 oracle 同一 post_lines，见证提供了
    字面量 0 / boundaries 之外的第三类输入来源：约束求解边界）。

    保守条件（任一不满足返回空串，主 oracle 不受影响）：
    - SPEC_SMT_ENABLE 关闭 / z3 未安装 / 无见证；
    - signature_params 未知或为空（无法把输入名映射到调用实参）；
    - 无任何可执行后件断言（见证测试无后件 = 只验前件的弱测试，不产出）；
    - 产物 ast.parse 自检失败。
    """
    from src.specs.spec_smt import generate_spec_witnesses, spec_smt_enabled

    if not spec_smt_enabled() or not signature_params:
        return ""
    if not any(line.strip().startswith("assert") for line in post_lines):
        return ""
    witnesses = generate_spec_witnesses(spec, signature_params)
    if not witnesses:
        return ""
    blocks: list[str] = []
    for idx, witness in enumerate(witnesses):
        inputs = witness.get("inputs") or {}
        header = (
            f"# SMT witness #{idx}（kind={witness.get('kind')}, "
            f"objective={witness.get('objective')}，前件求解产物，非 LLM 举例）"
        )
        test_lines = [header]
        test_lines.append(f"def test_specir_v2_smt_witness_{idx}():")
        bound = 0
        for param in signature_params:
            if param in inputs:
                test_lines.append(f"    {param} = {inputs[param]!r}")
                bound += 1
        if bound == 0:
            continue  # 见证输入与签名无交集（理论不可达，保守跳过）
        call_args = ", ".join(p for p in signature_params if p in inputs)
        test_lines.extend(pre_lines)
        test_lines.append(f"    r = {target_function}({call_args})")
        test_lines.extend(post_lines)
        if not any(line.strip().startswith("assert") for line in test_lines):
            continue
        blocks.append("\n".join(test_lines))
    if not blocks:
        return ""
    code = "\n\n".join(blocks)
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        logger.warning("SpecIR v2 SMT 见证产物自检失败，保守丢弃（防坏代码注入执行链路）")
        return ""
    return code


# ─── 4. 可编译率（"逻辑驱动"主张的量化内核，入 M1 metrics_schema）────────


def _expr_channel_clauses(spec: dict[str, Any] | None) -> list[str]:
    """提取表达式通道（AC1，*_expr 字段）的非空子句列表。"""
    if not spec:
        return []
    out: list[str] = []
    for key in ("preconditions_expr", "postconditions_expr", "invariants_expr"):
        out.extend(c.strip() for c in spec.get(key) or [] if isinstance(c, str) and c.strip())
    return out


def _nl_channel_clauses(spec: dict[str, Any] | None) -> list[str]:
    """提取 NL 通道（pre/post/invariant 字段）的非空子句列表（历史口径）。"""
    if not spec:
        return []
    out: list[str] = []
    for key in ("preconditions", "postconditions", "invariants"):
        out.extend(c.strip() for c in spec.get(key) or [] if isinstance(c, str) and c.strip())
    return out


def compile_readiness(spec: dict[str, Any] | None) -> float:
    """SpecIR 子句可编译率 ∈ [0.0, 1.0]（A-01 验证指标 ①）。

    定义（AC1 双通道口径，2026-10-06 第十轮审查 T-P0-2）：
    - 表达式通道存在非空子句（*_expr 字段，SPEC_EXPR_CONTRACT_SECTION
      契约产物）时：rate = 可编译 expr 子句数 / expr 子句总数——衡量
      **编译器对 LLM 形式化产物的接受率**；
    - expr 通道为空时回落历史口径：rate = 可机器解析 NL 子句 /
      非空 NL 子句总数（中文 NL 子句被 _EXPR_TOKEN_RE 拒绝 → 恒 0.0，
      即 AB1 验证批 12/12 实证的契约断裂基线）。分母为 0 时返回 0.0
      （无规约材料 = 不可编译，保守口径——"逻辑驱动"主张在 0% 时
      可证伪为"纯 LLM 话术"）。

    用途：
    - M1 指标层：每任务 spec_compile_rate 字段（与 detection/repair/
      false_fix 并列，衡量"逻辑驱动"实际贡献）；
    - 实验层：SpecIR ON/OFF 对照批次的"可编译规约占比 ≥60%"门槛。
    """
    expr_clauses = _expr_channel_clauses(spec)
    if expr_clauses:
        compiled = 0
        for clause in expr_clauses:
            if not is_expression_clause(clause):
                continue
            if _whitelist_check(clause):
                continue
            compiled += 1
        return compiled / len(expr_clauses)
    if not spec:
        return 0.0
    pre = [c for c in (spec.get("preconditions") or []) if isinstance(c, str) and c.strip()]
    post = [c for c in (spec.get("postconditions") or []) if isinstance(c, str) and c.strip()]
    inv = [c for c in (spec.get("invariants") or []) if isinstance(c, str) and c.strip()]
    clauses = pre + post + inv
    if not clauses:
        return 0.0
    compiled = 0
    for clause in clauses:
        if not is_expression_clause(clause):
            continue
        # 白名单检查 + 未知标识符检查（与 _compile_single_clause 同口径：
        # 子句可解析但变量不在已知绑定集合 → 不可编译为可执行断言，
        # 保守不计入可编译率）
        if _whitelist_check(clause):
            continue
        if not _compile_single_clause(clause, "postcondition", "", ""):
            continue
        compiled += 1
    return compiled / len(clauses)


def spec_expr_coverage(spec: dict[str, Any] | None) -> float | None:
    """表达式通道覆盖率 ∈ [0.0, 1.0]（AC1 观测指标，与 compile_rate 并列）。

    定义：expr 子句总数 / max(NL 子句总数, expr 子句总数)。衡量
    **LLM 把 NL 规约形式化的意愿/能力覆盖率**（与 compile_readiness
    衡量的"编译器接受率"正交：rate×coverage = NL 子句最终可确定性
    执行的占比）。None = 无任何规约材料。
    """
    expr_total = len(_expr_channel_clauses(spec))
    nl_total = len(_nl_channel_clauses(spec))
    if expr_total == 0 and nl_total == 0:
        return None
    return min(1.0, expr_total / max(nl_total, expr_total, 1))


# ─── 5. spec_provenance（NL 原文溯源，保守保留）─────────────────────────


def spec_provenance(spec: dict[str, Any] | None) -> list[str]:
    """提取 SpecIR 中不可机器化的 NL 子句清单（provenance 溯源）。

    用途：报告层"逻辑驱动"章节逐条标注"该条规约为 LLM 自然语言，
    未机器验证，其对应断言有效性由 LLM 生成测试承担"——与可编译子句
    的确定性 oracle 形成"可证伪 + 不可证伪"双清单（论文定位：
    逻辑驱动贡献 = 可编译率，而非 100% 宣称）。
    """
    if not spec:
        return []
    out: list[str] = []
    for kind in ("preconditions", "postconditions", "invariants"):
        for clause in spec.get(kind) or []:
            if not isinstance(clause, str) or not clause.strip():
                continue
            if not is_expression_clause(clause) or _whitelist_check(clause):
                out.append(f"{kind}: {clause.strip()}")
    return out


__all__ = [
    "compile_readiness",
    "compile_spec_oracle",
    "is_expression_clause",
    "spec_expr_coverage",
    "spec_ir_dsl_enabled",
    "spec_provenance",
]
