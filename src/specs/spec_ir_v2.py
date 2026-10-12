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
    4. **通道级失败归因**（W2/T1，2026-10-11 独立评审 F14）：逐子句拒绝
       原因分类（natural_language / unsupported_syntax / unsupported_operator /
       unknown_name / parse_error / too_long / empty / not_a_string）+ 可写入
       结果行的聚合函数 spec_reject_reasons（纯观测、零 LLM；与可编译判定
       共用同一段门，见 §3b）——把"47.6% 为 0"拆成可行动的根因分布。

v3（2026-10-12 独立评审落地·P0-A-1 文法升阶，回应评审报告 C1：
    spec_compile_rate ~21% 的根因是文法表达力不足而非提示工程）：
    5. **字符串纯方法白名单**：_ALLOWED_ATTRS 补入 startswith/endswith/
       split/join/strip/lstrip/rstrip/lower/upper/isdigit/isalpha/isalnum/
       isspace/find/count/replace（真实规约中频率最高的不可编译子句来源；
       全部 str 无副作用方法，与 len/abs 同风险级；title/center/encode 等
       刻意不收，保留为反例教学形态）；
    6. **有限域量化**（forall/exists 的可编译形态）：all(...)/any(...) 推导式
       经 _free_names 作用域精确判定——循环变量在推导式内绑定、可编译，
       推导式外引用照旧按 unknown_name 拒绝（防 NameError 假红断言）；
       _ALLOWED_CALL_NAMES 同步补入 range/enumerate（量化迭代域，纯内建）；
    7. **方法调用门修正**：visit_Call 对 Attribute 方法调用不再以调用名
       白名单二次拦截（属性白名单门已覆盖），修复"前一门放行、后一门拒绝"
       的同门冲突（T1b 同类）。
    比较算子（== != < <= > >=）、成员测试（in / not in）、链式比较、
    布尔（and/or/not）、算术、一元正负号自 v2 起即在字符白名单与 AST
    放行之列（tests/test_spec_contract_grammar.py 锁定，v3 补断言明示）。

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
#
# S6b（2026-10-09 审查报告 §5 路径 A2）：补入 `isinstance`。实测依据——
# 真实 Planner 产出的 *_expr 子句高频使用类型判定（如
# `isinstance(celsius, int)` / `isinstance(result, bool)`），而它不在
# 白名单时整条子句被保守丢弃，是 S6 接线后注入率的主要残余阻塞项之一。
# 安全性：isinstance 为纯函数（无副作用、无 I/O、不触发用户代码执行），
# 与既有 len/abs/sorted 同风险级；其第二参为类型对象（int/str/bool/float
# 等内建），仍受 AST 白名单节点约束（属性链深度与 Name 解析照旧受限），
# 不扩大"规约里藏命令"的注入面。
#
# v3（2026-10-12 独立评审落地·P0-A-1 文法升阶）：补入 `range` / `enumerate`。
# 用途：有限域量化子句（forall/exists 的可编译形态，见 _free_names）的
# 迭代域，如 `all(ch.isdigit() for ch in range(len(text)))`。二者为纯
# 内建迭代器工厂（无 I/O、无用户代码触发），单独出现不构成表达式求值
# 风险（range(10**10) 惰性、不物化；list/sum 等物化调用不在白名单）。
_ALLOWED_CALL_NAMES: frozenset[str] = frozenset(
    {
        "len", "abs", "min", "max", "round", "float", "int", "str", "sorted", "any", "all", "isinstance",
        "range", "enumerate",
    }
)
# 允许的属性访问（容器/数值边界锚点 + v3 字符串纯方法白名单）：
# - value/real/imag：数值属性锚点（历史口径，防 x.__class__ 类 introspection 逃逸）；
# - startswith/endswith/split/join/strip/lstrip/rstrip/lower/upper/isdigit/
#   isalpha/isalnum/isspace/find/count/replace：v3（P0-A-1）补入的**字符串纯方法**。
#   实测依据：spec_reject_reasons 归因分布中 unsupported_operator 的高频形态
#   即 `text.startswith(...)` / `",".join(...)` 等字符串规约（评审报告 C1：
#   真实规约中出现频率最高的不可编译子句来源）。全部为 str 无副作用方法
#   （不触文件 / 不执行用户代码 / 不抛网络），与 len/abs 同风险级；
#   刻意**不**收 title/center/encode/format 等（保留为反例教学形态）。
# 注意：`len` 是函数（走 _ALLOWED_CALL_NAMES），不是属性——此处原含 "len"
# 系笔误（会放行无效的 x.len 属性访问），已移除。
_ALLOWED_ATTRS: frozenset[str] = frozenset(
    {
        "value", "real", "imag",
        "startswith", "endswith", "split", "join", "strip", "lstrip", "rstrip",
        "lower", "upper", "isdigit", "isalpha", "isalnum", "isspace",
        "find", "count", "replace",
    }
)
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
# 子句长度上限（形态门 / too_long 归因门 / 文档注释的单一事实源）。
# 此前 200 以字面量出现两处（is_expression_clause :111 与 _form_gate_reject_reason），
# 任何一侧改动都会使"可编译判定"与"拒绝归因"漂移——本常数杜绝该风险。
# 值 200 由历史默认锚定（形态门 ≤200 字符的保守上限，防 LLM 产出超长垃圾子句）。
_MAX_CLAUSE_LEN = 200


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
    if not text or len(text) > _MAX_CLAUSE_LEN:
        return False
    # 通道 1：字符白名单（中文 / 动词短语必含白名单外字符 → 快速排除）
    if not _EXPR_TOKEN_RE.match(text):
        return False
    # 通道 2：ast 精确判（mode="eval" 顶层必须是表达式节点，Assign 等语句
    # 在 eval 模式下 parse 失败 → 自动拒绝）
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError):
        return False
    # S11（2026-10-08 修复）：eval 模式下 tree.body 直接是表达式节点本身
    # （非 Expr 包装）——`ast.Expr` 分支恒不可达，此前 `(ast.Expr, ast.Compare)`
    # 只有 ast.Compare 能通过，纯算术（BinOp）/ 布尔（BoolOp/UnaryOp）/
    # 字面量（Constant）/ bare 名（Name）/ 调用（Call）子句被误判为
    # "非表达式"（spec_compile_rate 与 SMT 前件见证均受此低估）。
    # 改为 isinstance(tree.body, ast.expr)：所有表达式形态都是 ast.expr
    # 子类；语句（Assign 等）在 eval 模式 parse 失败已由上方 except 拒绝。
    return isinstance(tree.body, ast.expr)


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
        # 调用名白名单分两种形态（v3 P0-A-1 修正）：
        # - Name 直调（len(x) / isinstance(x, int)）→ 必须在 _ALLOWED_CALL_NAMES；
        # - Attribute 方法调用（text.startswith("a") / ",".join(x)）→ 属性白名单
        #   由 visit_Attribute 校验（.startswith ∈ _ALLOWED_ATTRS），**不再**以
        #   调用名白名单二次拦截——否则字符串纯方法纵使在属性白名单内也会被
        #   本门拒（"前一门放行、后一门拒绝"的同门冲突，T1b 同类缺陷）。
        #   方法调用的安全性边界 = 属性白名单本身（纯方法、无副作用）。
        func = node.func
        if isinstance(func, ast.Name):
            if func.id not in _ALLOWED_CALL_NAMES:
                self.violations.append(f"dangerous_call:{func.id}")
        elif isinstance(func, ast.Attribute):
            pass  # 属性白名单门（visit_Attribute）负责，避免双重拒绝
        else:
            self.violations.append("dangerous_call:(opaque)")  # 下标调用 / lambda 调用等
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


# ─── 3a. 子句可编译判定（P0-3：度量通道与注入通道的唯一事实源）────────────
# 历史缺口（REVIEW_2026_FRONTIER I-07 / C2，2026-10-10）：
# compile_readiness（度量通道，见 §4）的 expr 分支只用 is_expression_clause +
# _whitelist_check 两门，而 compile_spec_oracle（注入通道）经
# _compile_single_clause **额外**做标识符绑定检查 + assert 行自检 →
# **度量通道 ≠ 注入通道**，spec_compile_rate 是"上界"而非实际注入率
# （离线可达性实证：子句过白名单 73.3% 而端到端 compiler 非空 18.7%）。
# 修复：抽出 _clause_is_compilable() 为唯一判定函数，两个调用点共用；
# 四门全部保留（形态门 / 白名单门 / 未知标识符门 / 产物自检门），不放宽。


def _default_known_names() -> frozenset[str]:
    """历史默认绑定集合（signature_params=None 时与注入通道逐字节同口径）。"""
    return frozenset({"r", "x", "a", "b", "y"} | _ALLOWED_CALL_NAMES | {"True", "False", "None"})


# P0-3（2026-10-10）：结果变量名精准别名（契约与注入通道的命名对齐）。
# SPEC_EXPR_CONTRACT_SECTION（src/prompts/templates.py:39-53，产出 *_expr
# 通道的**文档化契约**）明确以 `result` 表示返回值——白名单形态示例
# "索引与属性访问（如 result[0]）"、后置条件示例 "result == sorted(result)"；
# ORACLE_ENHANCE 契约（templates.py:93）同样以 "assert result == a + b" 为例。
# 而注入通道把结果变量绑为 `r`——命名不一致使契约产物在注入通道被判
# "未知标识符"整条丢弃（度量通道同判）。修复：后置/不变量子句内的
# Name("result") 精准归一为绑定名 r（同义替换，不改语义）。
# 精准边界（不放宽未知标识符门）：
# - 仅 kind ∈ {postcondition, invariant}（前置条件无结果变量，不归一）；
# - 仅当 result 不是真实绑定名（签名参数名含 result → 那是入参，不替换）；
# - 只替换整名 Name（results / result_x 不受影响）；
# - 形态门 / 白名单门 / 产物自检门照旧先行，危险调用与真正的未知标识符
#   （如 r == total 的 total）仍被拒。
_RESULT_ALIAS = "result"


def _result_alias_allowed(kind: str, known_names: frozenset[str]) -> bool:
    """result 别名可用性：仅后置/不变量（有结果变量）且 result 非真实绑定名。"""
    return kind in ("postcondition", "invariant") and _RESULT_ALIAS not in known_names


def _normalize_result_alias(clause: str, kind: str, known_names: frozenset[str]) -> str:
    """把契约结果变量名 result 精准归一为注入通道绑定名 r（不可用时原样返回）。

    纯文本同义替换（按 ast Name 节点的 col_offset 精确切片，保留其余原始
    字形 / 格式），不做 ast.unparse 重排——保证 `result` 与 `r` 两种写法
    产生**逐字节相同**的编译产物（tests/test_spec_oracle_metrics.py 锁定）。
    """
    text = clause.strip()
    if not _result_alias_allowed(kind, known_names):
        return text
    spans: list[tuple[int, int]] = [
        (node.col_offset, node.end_col_offset)
        for node in ast.walk(ast.parse(text, mode="eval"))
        if isinstance(node, ast.Name)
        and node.id == _RESULT_ALIAS
        and node.end_col_offset is not None  # mypy 收窄：None 已在推导式内排除
    ]
    for start, end in sorted(spans, reverse=True):
        text = f"{text[:start]}r{text[end:]}"
    return text


def _known_names_for_signature(signature_params: list[str] | None) -> frozenset[str]:
    """按签名解析可编译标识符绑定上下文（R1b 三态口径，与注入通道共用）。

    - None = 签名未知 → 历史默认集合 {r,x,a,b,y} ∪ 白名单名 ∪ 常量；
    - [] = 0 参函数 → 仅 {r} ∪ 白名单名 ∪ 常量（无输入名可绑定）；
    - 非空 = {r} ∪ 签名参数名 ∪ 白名单名 ∪ 常量（多参 / 自定义参数名）。
    """
    if signature_params is None:
        return _default_known_names()
    return frozenset({"r"} | set(signature_params) | _ALLOWED_CALL_NAMES | {"True", "False", "None"})


def _clause_is_compilable(clause: Any, kind: str, known_names: frozenset[str] | None = None) -> bool:
    """单一子句"可编译为可执行断言"判定（度量通道与注入通道共用的唯一口径）。

    kind:
    - "precondition" → `assert <expr>`（对已绑定输入变量）
    - "postcondition" / "invariant" → `assert <expr>`（对已绑定结果变量 r）

    kind 的唯一作用域差异：后置/不变量子句允许结果变量名精准别名
    （`result` → 绑定名 `r`，见 _normalize_result_alias）；其余判定同口径。

    四门全部保留（保守，不放宽）：
    1. 形态门 is_expression_clause（字符白名单 + ast eval + ≤200 字符）；
    2. 白名单门 _whitelist_check（危险调用 / 属性逃逸 / 解析失败）；
    3. 未知标识符门：子句内全部 Name 必须落在绑定上下文内（防 NameError 断言）；
       ——后置/不变量子句先经 _normalize_result_alias 把契约结果变量名
       `result` 精准归一为绑定名 `r`（同义替换，见该函数注释；非"放宽未知
       标识符门"：result 之外的未知名照旧被拒）；
    4. 产物自检门：`assert <clause>` 必须 ast.parse 通过（防白名单漏网）。

    known_names=None 时用历史默认绑定集合（与 compile_spec_oracle 的
    signature_params=None 逐字节同口径）。

    W2/T1（2026-10-11 独立评审落地）：判定体委托 _clause_reject_reason_for_known
    （§3b 通道级失败归因）——"能否编译"与"为什么不能编译"由同一段门回答，
    归因不会与判定漂移；四门顺序 / 返回语义 / 性能口径逐字不变
    （归因函数返回 None 即本函数返回 True）。
    """
    return _clause_reject_reason_for_known(clause, kind, known_names) is None


# ─── 3b. 通道级失败归因（W2/T1，2026-10-11 独立评审落地）────────────────────
# 根因（CONSOLIDATED_REVIEW_AND_PLAN.md §3.3 / F14，真实 LLM 调用实测）：
# planner 系统性产出**自然语言**规约（如 preconditions[0] = "text 为 str 类型"），
# 而本模块的形态门只收 ASCII 形式表达式 → compile_spec_oracle 恒 0 字节
# （日志记 "SpecIR v2 oracle 产物自检失败，保守丢弃"）、全量 1,607 行里
# spec_compile_rate 中位数 0.200、47.6% 为 0。既有观测只有"可编译率"一个标量：
# 看得见"全丢"，看不见"为什么丢"——NL 形态 / 白名单外算子 / 未绑定标识符
# 无法区分，"下一步修提示还是扩文法"失去依据。
# 本段补**纯观测、零 LLM、零行为变更**的逐子句拒绝归因：
#   - 归因与 _clause_is_compilable 共用同一段门（后者委托前者），不会漂移；
#   - 不触碰 _ALLOWED_CALL_NAMES / _ALLOWED_ATTRS（扩文法属下一轮）；
#   - spec_reject_reasons() 产出可直接写入 M1 结果行的 JSON 可序列化计数。

# 拒绝原因闭合集合（下游 schema / 报告层可据此校验，测试锁定）：
#   natural_language     — 自然语言子句（字符串字面量外的中文 / ASCII 散文）；
#   unsupported_syntax   — 可解析为表达式，但含字符白名单外字形（单引号串 /
#                          冒号切片 / 花括号 / f-string / 非 ASCII 字符串字面量）；
#   unsupported_operator — 可解析但调用 / 属性不在白名单（strip() / open()）；
#   unknown_name         — 形态与白名单均过，但含绑定上下文外的标识符；
#   parse_error          — 语法错（"a && b" / 赋值语句 "result = a + b"）；
#   too_long             — 可解析但单条 > 200 字符（形态门长度上限）；
#   empty                — 空串 / 纯空白；
#   not_a_string         — 非 str 类型子句（上游类型污染）。
SPEC_REJECT_REASONS: frozenset[str] = frozenset(
    {
        "natural_language",
        "unsupported_syntax",
        "unsupported_operator",
        "unknown_name",
        "parse_error",
        "too_long",
        "empty",
        "not_a_string",
    }
)

# ASCII 散文启发式（仅在"解析失败"后使用）：无任何运算符 / 括号 / 引号 /
# 冒号 / 逗号字符，且 ≥2 个空白分隔词（如 "text is str type"）。真实表达式
# 必含运算符或括号，故本启发式不会误吞形式子句；中文 NL 由非 ASCII 判据命中。
_PROSE_SEPARATOR_RE = re.compile(r"[=<>!+\-*/%&|^~\[\]()\"':,]")


def _parses_as_expr(text: str) -> bool:
    """文本能否被解析为单个表达式（ast.parse mode="eval"；失败 → False）。"""
    try:
        ast.parse(text, mode="eval")
    except (SyntaxError, ValueError):
        return False
    return True


def _has_non_ascii(text: str) -> bool:
    """子句是否含非 ASCII 字符（中文 NL 的直接内容判据）。"""
    return any(ord(ch) > 127 for ch in text)


def _has_non_ascii_outside_strings(text: str) -> bool:
    """非 ASCII 字符是否出现在**字符串字面量之外**（解析失败时按整体判）。

    用途（NL 与非 NL 的分界，见 _form_gate_reject_reason）：
    - 中文出现在代码位置（散文 / 中文标识符，如 "文本必须为非空字符串"——
      它恰好是合法 Python 标识符、能 parse，故不能用"能否 parse"区分）
      → 自然语言形态；
    - 中文只出现在双引号字符串里（如 text != "你好"，形式完全合法）→ 是
      **形式子句被字符白名单拦下**，不归 NL（否则"NL 占比"会被高估）。
    """
    try:
        tree = ast.parse(text, mode="eval")
    except (SyntaxError, ValueError):
        return _has_non_ascii(text)  # 解析不了 → 无法区分字面量内外，按整体判
    masked = list(text)
    for node in ast.walk(tree):
        # 字符串常量：按 col_offset 精确挖空（仅本处用途，不做 ast.unparse 重排）
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.end_col_offset is not None:
            for index in range(node.col_offset, min(node.end_col_offset, len(masked))):
                masked[index] = " "
    return any(ord(ch) > 127 for ch in masked)


def _looks_like_ascii_prose(text: str) -> bool:
    """ASCII 散文启发式（判据见 _PROSE_SEPARATOR_RE 注释）。"""
    return not _PROSE_SEPARATOR_RE.search(text) and len(text.split()) >= 2


def _form_gate_reject_reason(text: str) -> str:
    """形态门（is_expression_clause）拒绝时的原因细分（text 为 strip 后文本）。

    归因优先级（**内容信号优先于门的内部顺序**，已文档化并由测试锁定）：
    1. 字符串字面量之外含非 ASCII（中文散文 / 中文标识符，如 "text 为 str 类型"、
       "文本必须为非空字符串"——后者恰好是合法标识符能 parse，故判据不是
       "能否 parse"）→ natural_language；
    2. 解析失败的 ASCII 散文（"text is str type"）→ natural_language；
       解析失败且带运算符 / 标点（"a && b" / 赋值语句 / "if a: pass"）→ parse_error；
    3. 能解析但超长 → too_long（长度门在字符门前，与 is_expression_clause 同）；
    4. 能解析但含字符白名单外字形 → unsupported_syntax（如 text != "你好"
       或 a == 'x' / text[0:2]：形式子句被字符集拦下，不归 NL——否则
       "NL 占比"会被高估）；
    5. 其余（顶层非表达式节点，eval 模式理论不可达）→ parse_error。
    """
    if _has_non_ascii_outside_strings(text):
        return "natural_language"
    if not _parses_as_expr(text):
        return "natural_language" if _looks_like_ascii_prose(text) else "parse_error"
    if len(text) > _MAX_CLAUSE_LEN:
        return "too_long"
    if not _EXPR_TOKEN_RE.match(text):
        return "unsupported_syntax"
    return "parse_error"


# ─── 3c. 推导式作用域（v3 P0-A-1：有限域量化的可编译化）────────────────────
# 背景（独立评审 C1 / 优化方案 P0-A）：真实规约高频出现"对所有元素成立"
# 类全称量化（如 `all(ch.isdigit() for ch in text)`）与存在量化
# （`any(...)`）。历史实现用 ast.walk 全量收集 Name，推导式的 for 目标
# （循环变量 ch）不在签名绑定集合里 → 整条按 unknown_name 拒绝，量化
# 子句 100% 不可编译。
#
# 本段按 Python 真实作用域规则计算**自由名**（未绑定名）：
# - comprehension（ListComp/SetComp/GeneratorExp/DictComp）的 for 目标在
#   推导式体内绑定（elt / ifs / 后续 iter 可见），不流入自由名集合；
# - 推导式**外**引用循环变量（如 `all(x > 0 for x in items) and x > 5` 的
#   第二个 x）仍计入自由名 → 照旧按 unknown_name 拒绝（防 NameError 假红
#   断言：编译产物是 assert 行，运行期 NameError 会在 gold 上误报）；
# - lambda 参数默认值在外层作用域求值、参数名在 body 绑定（保守保持正确）。
#
# 安全性：自由名集合只**缩小**（量化子句从"必然被拒"变为"可编译"），
# 不放宽任何既有拒绝路径；危险调用 / 属性逃逸仍由白名单门先行拦截。


def _comprehension_target_names(target: ast.expr) -> set[str]:
    """comprehension 的 for 目标绑定名集合（Name / Tuple / List 递归）。"""
    names: set[str] = set()
    if isinstance(target, ast.Name):
        names.add(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names |= _comprehension_target_names(elt)
    # Starred 目标（*rest）罕见，保守不计入（引用时按未绑定拒绝）
    return names


def _lambda_param_names(args: ast.arguments) -> frozenset[str]:
    """lambda 全部参数名（含 vararg / kwarg / kwonly）。"""
    names = {a.arg for a in args.args} | {a.arg for a in args.kwonlyargs}
    if args.vararg:
        names.add(args.vararg.arg)
    if args.kwarg:
        names.add(args.kwarg.arg)
    return frozenset(names)


def _free_names(node: ast.AST, bound: frozenset[str] = frozenset()) -> set[str]:
    """表达式的自由名集合（comprehension / lambda 作用域精确版）。

    与历史 ast.walk 全量收集的差别只在推导式：循环变量不再计入自由名
    （有限域量化子句因此可编译），其余子句的自由名集合逐字节等价
    （无 comprehension 时 bound 恒空、全量 Name 即自由名）。
    """
    if isinstance(node, ast.Name):
        return {node.id} if node.id not in bound else set()
    if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
        generators = node.generators
        if not generators:  # 理论不可达（AST 恒 ≥1 generator），保守走通用遍历
            return set().union(*(_free_names(child, bound) for child in ast.iter_child_nodes(node)))
        free: set[str] = set()
        # 第一个 generator 的 iter 在 enclosing 作用域求值（Python 语义）
        free |= _free_names(generators[0].iter, bound)
        inner = set(bound)
        for gen in generators:
            inner |= _comprehension_target_names(gen.target)
        # 后续 iter 可见此前 target；elt / ifs 可见全部 target
        for gen in generators[1:]:
            free |= _free_names(gen.iter, frozenset(inner))
        for gen in generators:
            for cond in gen.ifs:
                free |= _free_names(cond, frozenset(inner))
        if isinstance(node, ast.DictComp):
            free |= _free_names(node.key, frozenset(inner))
            free |= _free_names(node.value, frozenset(inner))
        else:
            free |= _free_names(node.elt, frozenset(inner))
        return free
    if isinstance(node, ast.Lambda):
        # 默认值在外层求值；参数名 + 已有绑定在 body 内绑定
        defaults: set[str] = set()
        for default in [*node.args.defaults, *(d for d in node.args.kw_defaults if d is not None)]:
            defaults |= _free_names(default, bound)
        return defaults | _free_names(node.body, bound | _lambda_param_names(node.args))
    free = set()
    for child in ast.iter_child_nodes(node):
        free |= _free_names(child, bound)
    return free


def _clause_reject_reason_for_known(clause: Any, kind: str, known_names: frozenset[str] | None) -> str | None:
    """单子句拒绝原因（None = 可编译）；门顺序与 _clause_is_compilable 逐门一致。

    known_names 语义与原 _clause_is_compilable 相同（None = 历史默认绑定集合）。
    """
    if not isinstance(clause, str):
        return "not_a_string"
    text = clause.strip()
    if not text:
        return "empty"
    if not is_expression_clause(clause):
        return _form_gate_reject_reason(text)
    violations = _whitelist_check(clause)
    if violations:
        # dangerous_call: / attr_escape: = 算子级越界；parse_failed = 语法级
        operator_level = any(v.startswith(("dangerous_call:", "attr_escape:")) for v in violations)
        return "unsupported_operator" if operator_level else "parse_error"
    known = known_names if known_names is not None else _default_known_names()
    normalized = _normalize_result_alias(clause, kind, known)
    tree = ast.parse(normalized, mode="eval")
    # v3（P0-A-1）：自由名集合（推导式 / lambda 作用域精确版）替代 ast.walk
    # 全量 Name——有限域量化子句（all(x > 0 for x in items)）的循环变量
    # 不再计入未绑定名；推导式外引用循环变量照旧被拒（防 NameError 假红）。
    identifiers = _free_names(tree)
    # T1b（2026-10-11 独立评审落地·真实调用实测缺陷）：**白名单调用名不算未绑定
    # 标识符**。`_ALLOWED_CALL_NAMES` 的内建（abs/all/any/float/int/isinstance/
    # len/max/min/range/round/sorted/str/enumerate）在 `_whitelist_check` 中已按
    # 调用位置逐个放行，但它们在 AST 里同样是 `ast.Name` 节点，会被下面的
    # `identifiers - known` 判成 unknown_name —— **同一白名单在前一门放行、
    # 在后一门拒绝**，使"白名单里的函数一个都用不了"（真实 LLM 实测）：
    #     `len(items) > 0`      → unknown_name（应为可编译）
    #     `isinstance(a, int)`  → unknown_name（应为可编译）
    #     `max(a, b) > 0`       → unknown_name（应为可编译）
    # 而 `a + b > 0` 通过。本模块注释自述支持"`len()` 等调用"（见 spec_smt
    # 能力边界段），故此为**使实现与既有声明一致的必要修正**，不放宽危险面：
    # 只有经 `_whitelist_check` 放行的调用名才进入已知集合；未白名单的调用
    # （如 `eval`）仍被前一门以 dangerous_call 拒掉，到不了此处。
    # 隔离性：仅影响"白名单调用 + 其它标识符全部已绑定"的子句；纯 Name 的
    # 未绑定标识符（如 `r == total`）照旧按 unknown_name 拒绝。
    known_with_calls = known | _ALLOWED_CALL_NAMES
    if identifiers - known_with_calls:
        return "unknown_name"
    try:
        ast.parse(f"assert {normalized}")
    except (SyntaxError, ValueError):
        return "parse_error"
    return None


def clause_reject_reason(
    clause: Any, kind: str = "precondition", signature_params: list[str] | None = None
) -> str | None:
    """单条规约子句的拒绝原因分类（None = 可编译；纯观测、零 LLM）。

    返回值恒 ∈ SPEC_REJECT_REASONS ∪ {None}（闭合集合）；判定门与
    _clause_is_compilable 完全一致（后者委托本口径），可直接用于报告层
    "该条为何未机器化"的逐条归因。

    Args:
        clause: 规约子句（任意类型；非 str → "not_a_string"，不抛异常）。
        kind: "precondition" / "postcondition" / "invariant"（其余值按"无结果
            变量别名"处理，与 _clause_is_compilable 同口径）。
        signature_params: 绑定上下文三态口径，与 compile_readiness /
            compile_spec_oracle 完全一致（None = 签名未知的历史默认集合；
            [] = 0 参函数；非空 = {r} ∪ 参数名 ∪ 白名单名 ∪ 常量）。
    """
    return _clause_reject_reason_for_known(clause, kind, _known_names_for_signature(signature_params))


def spec_reject_reasons(spec: dict[str, Any] | None, signature_params: list[str] | None = None) -> dict[str, int]:
    """聚合被拒子句的原因计数（可写入结果行；纯观测、零 LLM）。

    口径与 compile_readiness **完全一致**（同一 _select_compile_channels +
    同一拒绝判定）：
    - 只看**被消费的通道**（*_expr 优先，其为空时回退 NL 通道）；
    - 空白子句不计入（与 compile_readiness 分母"非空子句数"同口径）；
    - spec 为空 / None / 无可编译材料时返回 {}（保守，不抛异常）。

    返回值恒为 {原因: 计数} 的 JSON 可序列化 dict，且满足
    `非空子句数 - sum(values) == 可编译子句数`（可与 compile_readiness 对账）。
    用途：下一次实验直接把 "47.6% 为 0" 拆成"多少是 NL 形态 / 多少是
    未绑定标识符 / 多少是白名单外算子"，为"修提示 vs 扩文法"提供依据。
    """
    pre, post, inv = _select_compile_channels(spec)
    known = _known_names_for_signature(signature_params)
    counts: dict[str, int] = {}
    for clauses, kind in ((pre, "precondition"), (post + inv, "postcondition")):
        for clause in clauses:
            if not clause.strip():
                continue  # 空白既非"可编译"也不进分母（历史口径）
            reason = _clause_reject_reason_for_known(clause, kind, known)
            if reason is not None:
                counts[reason] = counts.get(reason, 0) + 1
    return counts


def spec_expr_grammar_terminals() -> dict[str, list[str]]:
    """SpecExpr 文法的白名单终结符（提示层 / 文档的**单一事实源**）。

    提示层（src/agents/planner.py 的 SpecExpr 文法段）据此渲染 BNF 里的
    `<func>` / `<attr>` 白名单，杜绝 "提示里写的算子集 ≠ 编译器真实接受的
    算子集"再次漂移（F14 根因即提示-文法契约断裂）。下一轮扩文法时只需改
    _ALLOWED_CALL_NAMES / _ALLOWED_ATTRS，提示与测试自动跟随。

    v3（P0-A-1）：`quantifiers` 键给出有限域量化的承载调用（all/any 的
    推导式形态）——planner BNF 的 `<quant>` 产生式据此渲染，循环变量
    作用域规则见 _free_names。
    """
    return {
        "calls": sorted(_ALLOWED_CALL_NAMES),
        "attrs": sorted(_ALLOWED_ATTRS),
        "quantifiers": sorted(n for n in ("all", "any") if n in _ALLOWED_CALL_NAMES),
    }


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
    （r/x/a/b/y + 调用白名单名 + 常量）；compile_spec_oracle 按实际
    绑定上下文显式传入（与"产物自检"口径一致：未知变量 → 不编译）。

    P0-3（2026-10-10）：本函数是 _clause_is_compilable 的薄封装——判定口径
    单一事实源，度量通道（compile_readiness）与注入通道逐字同判定；本函数
    只负责把通过判定的子句渲染为 `assert <expr>`（后置/不变量的契约结果
    变量名 result 先经 _normalize_result_alias 归一为绑定名 r）。

    保守口径（不臆测行为）：见 _clause_is_compilable 四门（形态 / 白名单 /
    未知标识符 / 产物自检）；任一不满足 → 返回空串（调用方按 NL 注释处理，
    不产出 NameError 的坏断言）。
    """
    if not _clause_is_compilable(clause, kind, known_names):
        return ""  # 调用方按 NL 注释处理
    known = known_names if known_names is not None else _default_known_names()
    return f"assert {_normalize_result_alias(clause, kind, known)}"


def _indent_oracle_body(text: str) -> str:
    """把 oracle 语句统一缩进到函数体一级（4 空格）。

    T1c（2026-10-11 独立评审落地·真实调用实测缺陷，**决定性**）：
    `compile_spec_oracle` 的产物此前**恒为空**——`_compile_single_clause`
    返回的是**无缩进**的语句，而本函数把 post/invariant 行额外做了一次
    `compiled.replace("assert ", "    assert ", 1)`，得到 8 空格缩进；pre 行
    则被拼成 `f"    {compiled}"`（4 空格）。两者与 oracle 里 4 空格的一级语句
    （`items = 0` / `r = func(items)`）混排后：

        def test_specir_v2_oracle():
            from target_module import find_max
            items = 0
                assert len(items) > 0     ← 8 空格，SyntaxError: unexpected indent
            r = find_max(items)
                assert r == max(items)

    产物总自检 `ast.parse` 因此失败并走"保守丢弃"分支（日志记
    "SpecIR v2 oracle 产物自检失败"）——**即使 readiness=1.0（全部子句可编译），
    产物仍为 0 字节**，这正是"逻辑驱动"在当前口径下空转的直接机制。
    本函数把每条语句规整到恰好 4 空格（去前导空白后重新缩进），使 pre/post/
    invariant 与 oracle 一级语句对齐；对单行语句逐字等价，对多行语句逐行规整。
    """
    stripped = text.strip("\n")
    return "\n".join(("    " + line.strip()) if line.strip() else "" for line in stripped.split("\n"))


def _as_comments(lines: list[str]) -> list[str]:
    """把一组 oracle 语句行降级为注释行（T1d 无见证分支）。

    用途：无 SMT 见证时字面量 0 绑定**不保证满足前件**，若照发前件断言会让
    oracle 在正确实现上误报。此时把前件断言降为注释——**保留 provenance
    （读者仍能看到规约内容与"为何未断言"），但不产生可执行的误报断言**。
    空行保持空行（不产出孤立的 `#`）。
    """
    out: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue
        indent = line[: len(line) - len(line.lstrip())]
        out.append(f"{indent}# [未断言·无满足前件的见证] {stripped}")
    return out


def _precondition_witness_binding(pre: list[str], signature_params: list[str]) -> dict[str, Any] | None:
    """用 SMT 见证求一组**满足前件**的参数绑定（T1d，2026-10-11 独立评审落地）。

    `compile_spec_oracle` 在无边界输入材料时历史上用退化字面量 `0` 绑定
    （`a, b = 0, 0`），注释自述为"已知保守权衡：层 2 的字面量 0 绑定可能本身
    违反前置条件"。T1c 修复缩进缺陷后 oracle 首次真正产出可执行代码，该权衡
    的实际后果随之显现：前件形如 `b != 0` 时 `0` 绑定**在 gold 实现上就断言
    失败** —— 产物从"确定性检出通道"退化为"确定性假报通道"（M1 三段判定按
    "两侧皆红"记 0）。

    本函数复用既有 z3 通道 `spec_smt.generate_spec_witnesses`（"满足前件的
    合法输入"本就是它的语义）取首个见证，返回参数名 → 字面量的绑定映射。

    保守边界（任一不满足即返回 None，调用方回落历史 `0` 口径，行为逐字不变）：
    - `SPEC_SMT_ENABLE` 关 / z3 缺失 / 前件不可翻译 / 前件 UNSAT → 无见证；
    - 见证未同时覆盖 `signature_params` 的**全部**参数 → 不部分绑定
      （避免"一半 SMT 一半 0"产生更难解释的失败）；
    - 见证值必须是可直接写进源码的字面量类型（int/float/bool/str/None）；
      容器等复杂值 → 放弃（`repr` 出的字面量未必可执行，不臆测）。
    """
    try:
        from src.specs.spec_smt import generate_spec_witnesses, spec_smt_enabled

        if not spec_smt_enabled():
            return None
        witnesses = generate_spec_witnesses({"preconditions": list(pre)}, list(signature_params))
    except Exception:
        # 求解层任何异常都不得阻断 oracle 生成（保守回落字面量 0 口径）
        return None
    if not witnesses:
        return None
    first = witnesses[0]
    if not isinstance(first, dict):
        return None
    # 见证结构（见 spec_smt.generate_spec_witnesses 文档）：
    #   {"inputs": {参数名: Python 标量}, "kind": "sat"|"boundary_min"|..., ...}
    # 参数绑定在 **inputs** 子字典里，不是顶层。
    binding = first.get("inputs")
    if not isinstance(binding, dict):
        return None
    if any(p not in binding for p in signature_params):
        return None
    if any(not isinstance(binding[p], (int, float, bool, str, type(None))) for p in signature_params):
        return None
    return {p: binding[p] for p in signature_params}


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
    # S6（2026-10-09 审查报告 §5 路径 A2 / J1 根因）：编译器改读**表达式通道**。
    # 历史缺口：本函数只读 NL 通道（preconditions/postconditions/invariants），
    # 而 spec_compile_rate 度量的是 *_expr 通道（见 _expr_channel_clauses）——
    # **度量通道 ≠ 消费通道**，导致主批次 10 批 1,997 行臂中可执行规约 oracle
    # 注入 0 行（"逻辑驱动"从未真正运行）。
    # 修复：优先读 *_expr（机器化子句）；该通道为空时**回退** NL 通道
    # （历史口径逐字节不变——原实现即读 NL）。两通道不合并计数，避免
    # 同一子句被编译两次产生重复断言。
    # P0-3（2026-10-10）：通道选择抽为 _select_compile_channels（与
    # compile_readiness 共用），"度量通道 = 注入通道"从此由同一函数保证。
    pre, post, inv = _select_compile_channels(spec)

    # 可编译子句的绑定上下文（R1b 签名感知，P0-3 起与 compile_readiness 共用
    # _known_names_for_signature）：
    # - signature_params 非 None（签名已知，含 [] = 0 参）：{r} ∪ 签名参数名
    #   （真实绑定变量，覆盖多参数场景；0 参时仅 {r}）；
    # - None（签名未知 / 未提取到）：历史默认集合 {r,x,a,b,y}（行为不变口径）。
    # 两种口径均并入调用白名单 + 布尔/None 常量，未知标识符 → 不编译
    # （保守，防 NameError 断言）。
    known_names = _known_names_for_signature(signature_params)
    # 计数在构建断言行的同一轮循环内累积，避免每个子句被
    # _compile_single_clause 二次编译（该函数内含 ast.parse 白名单校验，
    # 双重编译是纯浪费；readiness 数值与逐字复用编译结果完全一致）。
    pre_lines: list[str] = []
    pre_compiled_n = 0
    for clause in pre:
        compiled = _compile_single_clause(clause, "precondition", target_module, target_function, known_names)
        if compiled:
            pre_compiled_n += 1
            pre_lines.append(_indent_oracle_body(f"    # pre: {clause}"))
            pre_lines.append(_indent_oracle_body(compiled))
        else:
            pre_lines.append(_indent_oracle_body(f"    # NL provenance (uncompiled pre): {clause}"))

    post_lines: list[str] = []
    post_compiled_n = 0
    for clause in post + inv:
        # post 与 invariant 共用后置断言口径（invariant = 任意输入下的性质，
        # 保守编译为"在边界输入下成立"——不臆测全输入域）
        compiled = _compile_single_clause(clause, "postcondition", target_module, target_function, known_names)
        if compiled:
            post_compiled_n += 1
            kind_tag = "post" if clause in post else "invariant"
            post_lines.append(_indent_oracle_body(f"    # {kind_tag}: {clause}"))
            post_lines.append(_indent_oracle_body(compiled))
        else:
            post_lines.append(_indent_oracle_body(f"    # NL provenance (uncompiled post): {clause}"))

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
            # v3（P0-A-1）：单参函数不再排除 tuple/list 边界输入。历史判据
            # `单参 + input 非 tuple/list` 把 `def f(items)` + 边界 [1,2,3]
            # 判为"元数/形态不匹配"→ 返回空串——**列表型被测函数（量化后条件
            # `all(x > 0 for x in result)` 的主场景）的 oracle 通道静默失效**。
            # 单参场景无 *args 歧义：`p0 = <input>`（含 list/tuple）是唯一
            # 合理绑定，f(p0) 即 f([1,2,3])。多参 + tuple/list 的 *args 展开
            # 口径不变；多参 + 标量仍判不匹配返回空串（不臆测实参映射）。
            if len(signature_params) == 1:
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
            # T1d（2026-10-11 独立评审落地）：用 **SMT 见证**替代退化字面量 0
            # 绑定。T1c 修复后 oracle 首次真正产出可执行代码，随即暴露原
            # "已知保守权衡"的后果：`a, b = 0, 0` 会违反前件（如 `b != 0`），
            # 于是 oracle 在 **gold 实现上就断言失败** —— 该产物本应"在正确
            # 实现上通过"，否则它从"确定性检出通道"退化为"确定性假报通道"
            # （M1 三段判定按"两侧皆红"记 0，既不检出也污染观测）。
            # `spec_smt.generate_spec_witnesses` 本就是"满足前件的合法输入"
            # 求解器通道（z3），故直接复用。
            #
            # **两种绑定分支（缺一不可）**：
            # (a) 有见证 → 绑定见证值，并正常发出前件断言（前件由构造满足，
            #     不会在 gold 上误报）；
            # (b) 无见证 → 绑定退化字面量 0，但**不发出前件断言**（改为注释
            #     保留 provenance）。理由：无见证意味着"0 是否满足前件未知"，
            #     此时发出前件断言等于让 oracle 在**正确实现上**断言失败——
            #     产物从"确定性检出通道"退化为"确定性假报通道"。后件断言
            #     仍照发：后件是契约义务，在正确实现 + 任意合法输入下应成立，
            #     且它才是"逻辑驱动"的确定性检出源。
            witness = _precondition_witness_binding(pre, signature_params)
            if len(signature_params) == 1:
                p0 = signature_params[0]
                lines.append(f"    {p0} = {witness[p0]!r}" if witness else f"    {p0} = 0")
                lines.extend(pre_lines if witness else _as_comments(pre_lines))
                lines.append(f"    r = {target_function}({p0})")
                lines.extend(post_lines)
            else:
                p0, p1 = signature_params[0], signature_params[1]
                if witness:
                    lines.append(f"    {p0}, {p1} = {witness[p0]!r}, {witness[p1]!r}")
                    lines.extend(pre_lines)
                else:
                    lines.append(f"    {p0}, {p1} = 0, 0")
                    lines.extend(_as_comments(pre_lines))
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


def _select_compile_channels(spec: dict[str, Any] | None) -> tuple[list[str], list[str], list[str]]:
    """按 compile_spec_oracle 的口径选择编译通道（P0-3：度量通道 = 注入通道）。

    返回 (pre, post, inv) 三段 str 子句列表：
    - expr 通道（*_expr 字段）存在任何 str 子句时选它（S6 契约消费通道）；
      否则回退 NL 通道（历史口径）；两通道不合并——防同一子句被编译两次。

    与 _expr_channel_clauses 的差别：本函数不做 strip 非空过滤——"通道是否
    存在"与"子句是否非空"是两件事（空串子句仍意味着 expr 通道存在），
    非空过滤由调用方（判定 / 计率）自行处理。
    """
    if not spec:
        return [], [], []
    pre_expr = [c for c in (spec.get("preconditions_expr") or []) if isinstance(c, str)]
    post_expr = [c for c in (spec.get("postconditions_expr") or []) if isinstance(c, str)]
    inv_expr = [c for c in (spec.get("invariants_expr") or []) if isinstance(c, str)]
    if pre_expr or post_expr or inv_expr:
        return pre_expr, post_expr, inv_expr
    pre = [c for c in (spec.get("preconditions") or []) if isinstance(c, str)]
    post = [c for c in (spec.get("postconditions") or []) if isinstance(c, str)]
    inv = [c for c in (spec.get("invariants") or []) if isinstance(c, str)]
    return pre, post, inv


def _compile_rate_for_channels(pre: list[str], post: list[str], inv: list[str], known_names: frozenset[str]) -> float:
    """统一判定下的可编译率 = 可编译非空子句数 / 非空子句数（无材料 → 0.0）。

    分段口径与 compile_spec_oracle 一致：pre 按 precondition 判定，
    post + inv 按 postcondition 判定（invariant 与后置共用断言口径）。
    """
    compiled = 0
    total = 0
    for clauses, kind in ((pre, "precondition"), (post + inv, "postcondition")):
        for clause in clauses:
            if not clause.strip():
                continue  # 空串既非"可编译"也不进分母（历史"非空子句数"口径）
            total += 1
            if _clause_is_compilable(clause, kind, known_names):
                compiled += 1
    return compiled / total if total else 0.0


def compile_readiness(spec: dict[str, Any] | None, signature_params: list[str] | None = None) -> float:
    """SpecIR 子句可编译率 ∈ [0.0, 1.0]（A-01 验证指标 ①）。

    **P0-3（REVIEW_2026_FRONTIER I-07，2026-10-10）：本指标与实际注入率同
    一口径**——每个子句经 _clause_is_compilable 判定（形态门 + 白名单门 +
    标识符绑定门 + 产物自检门），通道选择经 _select_compile_channels，与
    compile_spec_oracle 逐字同判定、同绑定上下文。修复前 expr 通道缺
    "标识符绑定门"→ 本指标只是**上界**（实测某批 0.4599，而离线可达性显示
    端到端 compiler 非空仅 18.7%）；修复后上界即实际值，可证伪。

    定义（AC1 双通道口径，2026-10-06 第十轮审查 T-P0-2）：
    - 表达式通道存在 str 子句（*_expr 字段，SPEC_EXPR_CONTRACT_SECTION
      契约产物）时：rate = 可编译 expr 子句数 / 非空 expr 子句总数——
      衡量**编译器对 LLM 形式化产物的接受率**（= 注入通道接受率）；
    - expr 通道为空时回落历史口径：rate = 可机器解析且可绑定的 NL 子句 /
      非空 NL 子句总数（中文 NL 子句被 _EXPR_TOKEN_RE 拒绝 → 恒 0.0，
      即 AB1 验证批 12/12 实证的契约断裂基线）。分母为 0 时返回 0.0
      （无规约材料 = 不可编译，保守口径——"逻辑驱动"主张在 0% 时
      可证伪为"纯 LLM 话术"）。

    Args:
        spec: parse_logic_analysis 产物（pre/post/invariant 及 *_expr 列表）。
        signature_params: 绑定上下文（三态口径与 compile_spec_oracle 完全
            一致：None = 签名未知 → 历史默认集合 {r,x,a,b,y}；[] = 0 参函数
            → 仅 {r} + 白名单名 + 常量；非空 = {r} ∪ 参数名 + 白名单名 +
            常量）。缺省 None 保持既有调用方行为（签名不变）。

    用途：
    - M1 指标层：每任务 spec_compile_rate 字段（与 detection/repair/
      false_fix 并列，衡量"逻辑驱动"实际贡献）；
    - 实验层：SpecIR ON/OFF 对照批次的"可编译规约占比 ≥60%"门槛。
    """
    pre, post, inv = _select_compile_channels(spec)
    return _compile_rate_for_channels(pre, post, inv, _known_names_for_signature(signature_params))


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
    "SPEC_REJECT_REASONS",
    "clause_reject_reason",
    "compile_readiness",
    "compile_spec_oracle",
    "is_expression_clause",
    "spec_expr_coverage",
    "spec_expr_grammar_terminals",
    "spec_ir_dsl_enabled",
    "spec_provenance",
    "spec_reject_reasons",
]
