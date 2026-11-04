"""
测试规划师模块：实现逻辑驱动思维链（Logic-driven Chain-of-Thought）。

Planner 在输出测试计划前，先对函数进行输入域、输出域、前置条件、
后置条件、边界情况的显式分析，引导 Generator 按逻辑覆盖生成测试用例。
"""

from __future__ import annotations

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.prompts.templates import PLANNER_SYSTEM_PROMPT, SPEC_EXPR_CONTRACT_SECTION
from src.specs import spec_ir_dsl_enabled
from src.specs.spec_ir_v2 import spec_expr_grammar_terminals
from src.tools.control_flow import build_cfg_prompt_section, cfg_analysis_enabled
from src.utils.env_utils import env_flag

# 模块级日志记录器
logger = logging.getLogger(__name__)


# ─── W2/T1（2026-10-11 独立评审落地）：SpecExpr 文法契约段 ─────────────────────
# 根因（CONSOLIDATED_REVIEW_AND_PLAN.md §3.3 / F14，独立评审真实 LLM 调用实测）：
# planner 要求 LLM 产出规约时，LLM **系统性输出自然语言**（如
# preconditions[0] = "text 为 str 类型"、"成功时返回 int 类型结果"），而
# src/specs/spec_ir_v2.py 的白名单编译器只接受形式表达式 → compile_spec_oracle
# 产出 0 字节（日志记 "SpecIR v2 oracle 产物自检失败，保守丢弃"），全量 1,607 行
# 里 spec_compile_rate 中位数 0.200、47.6% 为 0，真实调用下 3 个函数里 2 个
# logic_degraded=True。
# 既有 SPEC_EXPR_CONTRACT_SECTION（templates.py）只给了 2 个示例，未给出**文法
# 边界**（哪些字形 / 算子 / 标识符真的被接受）→ LLM 只能猜。本段补齐四件东西
# （仅在 SPEC_IR_DSL_ENABLE=true 时追加；默认档 prompt 零变化，ADR-0003）：
#   1. SpecExpr BNF——白名单函数 / 属性由 spec_expr_grammar_terminals() 从
#      spec_ir_v2 的代码常量渲染（单一事实源，杜绝提示与编译器再次漂移）；
#   2. 5 个正例（逐条经 _clause_is_compilable 验证可编译，测试锁定）；
#   3. 5 个反例（逐条实测被拒，含评审实测的真实失败形态 "text 为 str 类型"；
#      每条标注拒绝原因分类，与 spec_ir_v2.clause_reject_reason 逐字一致）；
#   4. 输出前自检指令（四道校验门的可操作版）。
# 正 / 反例以模块级常量给出（不散落在提示文本里），tests/test_spec_contract_grammar.py
# 可直接遍历验证"提示里的每条例子都真的能编译 / 真的被拒"。
SPEC_EXPR_GRAMMAR_POSITIVE_EXAMPLES: tuple[tuple[str, str, str], ...] = (
    ("b != 0", "precondition", "precondition: the divisor is non-zero"),
    (
        "len(text) > 0 and isinstance(text, str)",
        "precondition",
        "precondition: non-empty + type check (isinstance is whitelisted)",
    ),
    (
        "result == a + b",
        "postcondition",
        "postcondition: result denotes the return value; the compiler aligns it to the internal bound name",
    ),
    ("isinstance(result, int) and result >= 0", "postcondition", "postcondition: type + range"),
    ("0 <= result <= 100", "invariant", "invariant: chained comparison written in one shot"),
    # v3（2026-10-12 P0-A-1 文法升阶）：有限域量化 + 字符串纯方法正例
    (
        "all(ch.isdigit() for ch in text)",
        "invariant",
        "universal quantification: every character is a digit (loop variable ch is bound only inside the comprehension)",
    ),
    (
        'text.startswith("a")',
        "precondition",
        "pure string method: prefix check (startswith is a whitelisted attribute)",
    ),
    # v4（2026-10-15 EMSE 批次六，emse_dsl_diag3 实测形态）：切片 + 字典读 API + set 去重
    (
        "result == text[::-1]",
        "postcondition",
        "slice: reversed-order assertion (colons are allowed only in slices and double-quoted strings)",
    ),
    (
        "all(v > 0 for v in counts.values())",
        "invariant",
        "dict read API: values() read-only iteration (keys/items/get are the same family)",
    ),
    (
        "len(set(result)) == len(result)",
        "postcondition",
        "set dedup: all-distinct elements check (set is a whitelisted call)",
    ),
)
SPEC_EXPR_GRAMMAR_NEGATIVE_EXAMPLES: tuple[tuple[str, str, str], ...] = (
    # 前两条的中文子句是刻意保留的教学素材：示范自然语言/中文输入被字符白名单拒绝。
    (
        "text 为 str 类型",
        "natural_language",
        "a CJK natural-language type sentence - a real failure shape observed in review",
    ),
    (
        "成功时返回 int 类型结果",
        "natural_language",
        "same shape: natural language, rejected by the character whitelist for non-ASCII characters",
    ),
    ("result = a + b", "parse_error", "an assignment statement is not an expression (write == for equality)"),
    ("r == total", "unknown_name", "total is unbound; always write the result variable as result, never r"),
    # v3：strip 已入白名单（字符串纯方法），反例换用刻意不收的 title
    (
        'result.title() == "Abc"',
        "unsupported_operator",
        "title is not a whitelisted attribute (pure string methods only allow startswith/split/lower and the like)",
    ),
    # v4（2026-10-15）：冒号放行后的护栏反例——lambda 子句无断言语义
    (
        "lambda r: r > 0",
        "unsupported_syntax",
        "a lambda clause compiles into a vacuously-true assertion (the BNF has no keyword-argument production; a lambda may only appear bare)",
    ),
)
# 示例所属字段标签（渲染进提示，避免 LLM 把后置示例写进前置）
_SPEC_EXPR_KIND_FIELD = {
    "precondition": "preconditions_expr",
    "postcondition": "postconditions_expr",
    "invariant": "invariants_expr",
}


def _build_spec_expr_grammar_section() -> str:
    """渲染 SpecExpr 文法契约段（白名单终结符取自 spec_ir_v2 代码常量）。"""
    terminals = spec_expr_grammar_terminals()
    funcs = " | ".join(terminals["calls"])
    attrs = " | ".join(terminals["attrs"])
    quants = " | ".join(terminals["quantifiers"])
    positives = "\n".join(
        f"{i}. {clause}    ({_SPEC_EXPR_KIND_FIELD[kind]}: {note})"
        for i, (clause, kind, note) in enumerate(SPEC_EXPR_GRAMMAR_POSITIVE_EXAMPLES, 1)
    )
    negatives = "\n".join(
        f"{i}. {clause}    -> rejected because: {reason} ({note})"
        for i, (clause, reason, note) in enumerate(SPEC_EXPR_GRAMMAR_NEGATIVE_EXAMPLES, 1)
    )
    return f"""
[SpecExpr grammar (the only legal shape for *_expr fields; matches the compiler whitelist verbatim)]
<clause>  ::= <or>
<or>      ::= <and> ("or" <and>)*
<and>     ::= <not> ("and" <not>)*
<not>     ::= "not" <not> | <cmp>
<cmp>     ::= <arith> (("==" | "!=" | "<" | "<=" | ">" | ">=" | "is" | "is not" | "in" | "not in") <arith>)*
<arith>   ::= <term> (("+" | "-") <term>)*
<term>    ::= <unary> (("*" | "/" | "//" | "%") <unary>)*
<unary>   ::= ("-" | "+") <unary> | <atom>
<atom>    ::= integer | double-quoted string | True | False | None
            | parameter name | result (postconditions / invariants only, the return value)
            | <call> | <quant> | <atom>[<slice>] | <atom>.<attr>
            | "(" <clause> ("," <clause>)* ")" | "[" <clause> ("," <clause>)* "]"
<slice>   ::= <arith> | [<arith>] ":" [<arith>] [":" [<arith>]]
<call>    ::= <func> "(" [<clause> ("," <clause>)*] ")"
<quant>   ::= ("{quants}") "(" <clause> "for" <name> "in" <clause> ")"
<func>    ::= {funcs}
<attr>    ::= {attrs}
Note 1: the bitwise operators (& | ^ ~ << >>) pass the compiler, but boolean semantics must always be written with and / or / not.
Note 2: <quant> is finite-domain quantification - universal (holds for every element) is written all(...), existential (holds for at least one element) is written any(...); <name> is the loop variable, bound only inside the comprehension and never referenced elsewhere in the clause.
Note 3: <attr> covers pure string methods (startswith/split/join/lower, etc., side-effect free); title()/center()/encode() and the like are not in the whitelist and must not appear.
Note 4: <slice> is the slice shape allowed by v4 (2026-10-15) - colons are permitted only inside slices and double-quoted strings (e.g. text[1:] / text[::-1] / "result: "); lambdas and walrus assignments ((x := 5)) are rejected outright (no assertion semantics).

[Positive examples (10 items, each passing every validation gate; copy them as-is)]
{positives}

[Negative examples (6 items, each rejected outright; these belong only in the NL field, never in *_expr)]
{negatives}

[Pre-output self-check (verify item by item; if any check fails, write that clause only in the NL field)]
(i) Characters: ASCII expression characters only - no CJK, no single quotes (strings are always double-quoted), no braces, no f-strings, no #; colons appear only in slices (text[1:] / text[::-1]) and double-quoted strings; each clause is at most 200 characters.
(ii) Calls: only calls within the <func> whitelist, attributes within the <attr> whitelist and pure string methods; title()/center()/encode()/open()/eval() and the like must never appear.
(iii) Names: only the real parameter names of the function under test; postconditions / invariants may additionally use result for the return value (do not write r); unbound names (internal variables such as total, left, scores) must never appear; a quantifier loop variable (the x in all(x > 0 for x in items)) is valid only inside its comprehension.
(iv) Shape: every clause must work verbatim as an assert condition - "result = a + b" (assignment), "if a is negative" (natural language), a lambda clause and the walrus assignment "(x := 5)" are all rejected; write equality as ==, type checks as isinstance(x, int), non-emptiness as len(x) > 0 or x != "".
(v) Write a clause into *_expr only after it passes the self-check; when unsure, keep it in the NL field only - the compiler drops uncompilable clauses one by one, will not fix them for you, and stuffing them in only lowers the compilable rate.
"""


SPEC_EXPR_GRAMMAR_SECTION = _build_spec_expr_grammar_section()


# ─── Q-1（2026-10-18）：规格可执行示例通道（Planner prompt 契约）─────────────
# 背景：P-1/P-1.1 在重放中验证"LLM spec-only 生成的可执行示例"能带来真检出，
# 但从未进入真实 Planner 链路。Q-1 新增双门 env：
#   SPEC_ORACLE_EXAMPLES_ENABLE=true ∧ SPEC_ORACLE_EXEC_ENABLE=true
# 时才在 Planner prompt 追加 examples 契约段；默认关 → prompt 逐字节不变
# （ADR-0003 零变化口径）。examples 由 compile_spec_oracle 编译为逐示例断言，
# 经 N-3 独立判读（oracle_suite_verdict）真实计入质量测量。
_SPEC_EXAMPLES_PROMPT_MAX = 3


def spec_oracle_examples_enabled() -> bool:
    """Q-1 双门开关：SPEC_ORACLE_EXAMPLES_ENABLE ∧ SPEC_ORACLE_EXEC_ENABLE。

    默认两个都关 → False（历史 prompt/产物零变化）。只有执行注入开关也开着
    才请求 examples——否则请求了也不会被编译注入，纯浪费 prompt token。
    """
    return env_flag("SPEC_ORACLE_EXAMPLES_ENABLE") and env_flag("SPEC_ORACLE_EXEC_ENABLE")


SPEC_EXPR_EXAMPLES_SECTION = """
[Executable specification examples (SPEC_ORACLE_EXAMPLES_ENABLE=true, strictly enforced)]
Append the optional field "examples" in logic_analysis (parallel to pre/post/*_expr, not a replacement):
"examples": [{"input": [...], "expected": ...}]
Rules:
1. At most 3 items; each item must be {"input": <JSON literal list>, "expected": <JSON literal>} and must be valid JSON.
2. input is **the argument list expanded in the function's parameter order** (a single-parameter function is written [x]); every value in input must be a JSON literal such as int/float/str/True/False/None/list/dict.
3. expected must be a JSON literal and must be **derived from the specification (docstring / type annotations / pre- and postconditions / boundary cases)**; never guess it from the implementation code; if the specification does not define the behaviour for that input, do not emit the item.
4. Keep inputs small (avoid big integers / long sequences / deep recursion) so they execute quickly.
5. Emit only examples the specification can clearly decide; when expected is uncertain, omit the item.
6. Self-check before emitting: examples is valid JSON, at most 3 items, input is an argument list, expected is a JSON literal.
"""


def _sanitize_logic_analysis_examples(result: dict[str, Any], enabled: bool) -> None:
    """Q-1：Planner 返回的 examples 严格净化（≤3、非法丢弃、关闭时删除）。

    - 开关开：只保留合法 JSON 字面量示例，最多 ``_SPEC_EXAMPLES_PROMPT_MAX`` 条
      （抽取逻辑与 ``spec_ir.parse_examples`` 同源；非法形状丢弃不抛）；
    - 开关关：**删除** ``logic_analysis.examples``（即使模型/缓存自发输出），
      保证关闭时下游 SpecIR/oracle 产物与历史口径逐字节一致。
    """
    logic = result.get("logic_analysis")
    if not isinstance(logic, dict):
        return
    if not enabled:
        logic.pop("examples", None)
        return
    from src.specs.spec_ir import parse_examples

    examples = parse_examples(logic.get("examples"), max_examples=_SPEC_EXAMPLES_PROMPT_MAX)
    if examples:
        logic["examples"] = examples
    else:
        logic.pop("examples", None)


def _logic_spec_strict_fallback_enabled() -> bool:
    """AB1（2026-10-06 生死实验根因修复）：M10 强校验拒绝的降级出口开关。

    生死实验（n=87×3 臂×3 种子，logic 档）实测 21/261 任务因
    LOGIC_SPEC_STRICT_ENABLE=true 在 Planner 第 0 轮直接 raise ——
    error_category='error'、detection=None（M1 分母外），而同任务在
    plain_llm_df 臂正常检出。强校验的设计意图（M10）是"拒绝**静默**
    兜底、供 CI 科学主张测试消费"，但 raise 把"模型未输出规约"
    （模型行为）升级成"整任务死亡"（系统故障），引入 8% 吞吐损失。

    开启本开关时，强校验拒绝改为**显式标记降级**：result 写入
    logic_spec_rejected=<原因> 后继续执行（空规约走 degraded 路径，
    下游 spec 链材料为空、spec_compile_rate 不受污染）——非静默
    （标记 + 日志），科学主张口径不回退。默认 false：独立 raise
    语义原样保留（CI 科学主张测试依赖）。logic profile 预设注入
    true（实验档吞吐恢复，行为经 provenance 可追溯）。
    """
    return env_flag("LOGIC_SPEC_STRICT_FALLBACK_ENABLE")


def _strict_reject(result: dict[str, Any], message: str) -> None:
    """M10 强校验拒绝出口：默认 raise；fallback 开启时标记降级继续。

    标记保留**首因**：logic_analysis 缺失路径先标记后进入 schema 校验，
    后续分支的 findings（对已填充空值的校验）是缺失的下游产物——
    覆盖首因会掩盖根因（观测口径以第一次拒绝为准）。

    Args:
        result: Planner 解析结果（fallback 时写入 logic_spec_rejected 标记）。
        message: 拒绝原因（raise 消息 / 标记值，含 M10 前缀供下游归因）。
    """
    if _logic_spec_strict_fallback_enabled():
        if "logic_spec_rejected" not in result:
            result["logic_spec_rejected"] = message
            logger.warning("M10 强校验拒绝已降级（LOGIC_SPEC_STRICT_FALLBACK_ENABLE=true）：%s", message)
        else:
            logger.warning("M10 强校验后续拒绝（首因已标记，保留）：%s", message)
        return
    raise ValueError(message)


class LogicAnalysisResult:
    """
    逻辑分析结果：记录 Planner 对单个函数的结构化分析。

    该结果包含函数的输入域、输出域、前置/后置条件和边界情况，
    用于引导后续测试生成器覆盖所有重要路径。

    属性:
        input_domain: 输入参数描述（含类型、取值范围、特殊值）。
        output_domain: 返回值描述（含类型、可能的异常）。
        preconditions: 调用前的前提条件列表。
        postconditions: 调用后的后置条件列表。
        edge_cases: 边界情况列表（如除零、空集合、负数等）。

    使用示例:
        >>> result = LogicAnalysisResult(
        ...     input_domain="整数 a, b，无范围限制",
        ...     output_domain="整数，a+b 的算术和",
        ...     preconditions=["a, b 均为整数"],
        ...     postconditions=["result == a + b"],
        ...     edge_cases=["a=0", "b=0", "大整数溢出"],
        ... )
        >>> result.to_dict()
        {'input_domain': '整数 a, b，无范围限制', ...}
    """

    def __init__(
        self,
        input_domain: str,
        output_domain: str,
        preconditions: list[str],
        postconditions: list[str],
        edge_cases: list[str],
    ) -> None:
        # 初始化各字段
        self.input_domain = input_domain
        self.output_domain = output_domain
        self.preconditions = preconditions
        self.postconditions = postconditions
        self.edge_cases = edge_cases

    def to_dict(self) -> dict[str, Any]:
        """
        将逻辑分析结果序列化为字典。
        便于 JSON 存储、传递和后续使用。

        Returns:
            包含五个字段的字典。
        """
        return {
            "input_domain": self.input_domain,
            "output_domain": self.output_domain,
            "preconditions": self.preconditions,
            "postconditions": self.postconditions,
            "edge_cases": self.edge_cases,
        }


class PlannerAgent(BaseAgent):
    """
    测试规划师：读取目标代码，先生成逻辑分析（思维链），再输出结构化测试计划。

    工作流程：
    1. 接收被测代码和可选的目标函数名
    2. 调用 LLM，要求其先进行逻辑分析，再生成测试计划 JSON
    3. 解析响应，确保包含 logic_analysis 字段

    输入:
        target_code: 被测 Python 源代码字符串。
        target_function: 指定要测试的函数名（可为 None，表示测试全部函数）。

    输出:
        测试计划字典，包含 logic_analysis（思维链）和 test_cases 列表。
    """

    def __init__(self) -> None:
        # 使用增强版 system prompt，要求先输出逻辑分析再输出测试计划
        super().__init__(PLANNER_SYSTEM_PROMPT)

    def plan(self, target_code: str, target_function: str | None = None) -> dict[str, Any]:
        """
        生成测试计划（含逻辑驱动思维链）。

        LLM 输出分为两个阶段：
        Phase 1: 逻辑分析（输入域、输出域、前置/后置条件、边界情况）
        Phase 2: 结构化测试计划 JSON

        Args:
            target_code: 被测代码全文。
            target_function: 目标函数名，用于聚焦分析；None 则分析全部。

        Returns:
            测试计划字典，结构如下：
            {
                "function_name": str,
                "description": str,
                "logic_analysis": {
                    "input_domain": str,
                    "output_domain": str,
                    "preconditions": List[str],
                    "postconditions": List[str],
                    "edge_cases": List[str]
                },
                "test_cases": List[dict]
            }

        Raises:
            RuntimeError: LLM 调用失败（重试耗尽）时抛出。
            json.JSONDecodeError: LLM 返回非 JSON 格式时抛出（_extract_json 委托 extract_json_object）。
        """
        # 截断超长代码，节省 token（大文件按焦点函数做 AST 智能截取，
        # 保留 import 与直接依赖，避免 LLM 看不到目标函数）
        target_code = BaseAgent.truncate_code(target_code, focus_function=target_function)
        # 构建查询：包含代码和可选的函数限定
        query = f"Analyse the following code and produce a test plan:\n\n```\n{target_code}\n```"
        if target_function:
            # 明确指定要测试的函数，要求输出中包含该函数名
            query += f"\n\n**Important: produce the test plan for the function below only; do not analyse any other function:**\n`{target_function}`"
            query += f"\n\nThe output's function_name field must be `{target_function}`."

        # 2.2 控制流图（CFG）静态层：纯 AST 分析（零 LLM 成本），把分支/
        # 循环/异常路径摘要注入 prompt，使测试用例覆盖系统化（按路径
        # 而非 LLM 自由发挥）。CFG_ANALYSIS_ENABLE=false 时零变化。
        if cfg_analysis_enabled():
            from src.tools.control_flow import analyze_control_flow

            cfg = analyze_control_flow(target_code, target_function)
            cfg_section = build_cfg_prompt_section(cfg)
            if cfg_section:
                query += cfg_section

        # AC1（2026-10-06 第十轮审查 T-P0-2）：规约表达式通道契约段。
        # SPEC_IR_DSL_ENABLE=true（logic/scientific 档）时追加，要求 LLM 在
        # 中文 NL 规约之外并行输出可机器执行的表达式子句——修复 prompt 与
        # SpecIR v2 编译器的契约断裂（NL 中文子句被 _EXPR_TOKEN_RE 白名单
        # 100% 拒绝 → spec_compile_rate 恒 0.0，AB1 验证批 12/12 实证）。
        # 默认关不追加，prompt 零变化（ADR-0003）。
        if spec_ir_dsl_enabled():
            query += SPEC_EXPR_CONTRACT_SECTION
            # W2/T1（2026-10-11 独立评审 F14）：契约段说"要哪三个字段"，文法段
            # 说"什么形态才真的能被编译"——补上 BNF + 5 正例 + 5 反例 + 自检。
            query += SPEC_EXPR_GRAMMAR_SECTION
        # Q-1（2026-10-18）：规格可执行示例契约段。双门（EXAMPLES ∧ EXEC）都开
        # 才追加——默认关时 prompt 与历史**逐字节一致**（零变化口径）。
        if spec_oracle_examples_enabled():
            query += SPEC_EXPR_EXAMPLES_SECTION

        # 调用 LLM 获取原始响应（内含逻辑分析和测试计划），带文件缓存省 token
        raw = self._call_llm_with_cache(query, json_mode=True)
        # 解析 JSON 响应
        result = self._extract_json(raw)

        # OMS（M10 可观测性，EMSE 批次四 M1）：叶子回退静默片段检测。
        # ADR-0031 §已知局限②：extract_json_object 的叶子降级档在括号平衡法
        # 失败时会**静默返回最内层错误片段**（如 {'items': ...}）——此前下游
        # 把"缺 logic_analysis"全部归因为"LLM 未输出"（10-14 批次 ~7-8% 的
        # M10 误诊来源，实为提取器缺陷，LLM 输出了完整正确 JSON）。
        # 现读取 helpers 哨兵：命中叶子回退时把归因改写为
        # "M10 提取器叶子回退"（纯观测标记，不参与路由；解析行为零变化）。
        from src.utils.helpers import was_leaf_fallback_used as _was_leaf_fallback

        _leaf_fallback = _was_leaf_fallback()
        if _leaf_fallback:
            logger.warning(
                "M10-OMS：logic_analysis 缺失源于**提取器叶子回退**（非 LLM 未输出），"
                "最内层片段缺关键字段——归因已改写，M10 误诊计数 +1（可观测性改进）"
            )

        # 兼容性处理：确保返回的 JSON 包含 logic_analysis 字段
        # 部分模型可能跳过思维链步骤直接输出测试计划，填充空值避免下游崩溃
        # M10（2026-09-29 审查 P0）：静默兜底改为显式标记。
        # 历史口径：LLM 不输出 logic_analysis 时静默填 5 个空字段
        # （"逻辑驱动"主张不可证伪）。现补 logic_degraded=True 标记
        # （纯观测，不参与路由），供实验层把该任务归入"未走逻辑驱动
        # 路径"而非"逻辑驱动成功"。LOGIC_SPEC_STRICT_ENABLE=true
        # （默认 false）时把 degraded 态提升为 ValueError（强校验），
        # 供 CI 科学主张测试消费。
        if "logic_analysis" not in result or result["logic_analysis"] is None:
            result["logic_analysis"] = {
                "input_domain": "",
                "output_domain": "",
                "preconditions": [],
                "postconditions": [],
                "edge_cases": [],
            }
            result["logic_degraded"] = True
            # OMS（EMSE 批次四 M1）：归因改写——命中叶子回退时记录提取器误诊
            # 标记（纯观测，不参与路由）：供实验层把 M10 降级任务中"实为
            # 提取器缺陷"的子集从"LLM 未输出"中分离计数。
            if _leaf_fallback:
                result["m10_leaf_fallback"] = True
            logger.warning(
                "M10：LLM 未输出 logic_analysis，已填充空值并标记 logic_degraded=True%s",
                "（归因：提取器叶子回退误诊，非 LLM 缺字段）" if _leaf_fallback else "",
            )
            if env_flag("LOGIC_SPEC_STRICT_ENABLE"):
                _strict_reject(result, "M10 LOGIC_SPEC_STRICT_ENABLE=true：logic_analysis 缺失，拒绝静默兜底")
        else:
            result.setdefault("logic_degraded", False)
        # Q-1：examples 严格净化（≤3、非法丢弃；关闭时删除键）——在 schema
        # 校验/下游 parse_logic_analysis 之前收敛，防止脏示例进入 oracle 编译。
        _sanitize_logic_analysis_examples(result, spec_oracle_examples_enabled())
        # M10（2026-09-29 审查 P0）：schema 强校验——对 logic_analysis 做
        # 必填字段 + 类型 + 非空校验（纯数据，零 LLM 成本）。findings 非空时
        # 写入 result["logic_spec_findings"]（纯观测，不参与路由），供
        # 实验层"空值率 = 0"指标消费。LOGIC_SPEC_STRICT_ENABLE=true
        # （默认 false）时把 degraded 态提升为 ValueError（强校验），
        # 供 CI 科学主张测试消费。
        from src.tools.logic_spec import logic_spec_strict_enabled as _logic_spec_strict_enabled
        from src.tools.logic_spec import validate_logic_spec as _validate_spec

        _spec_findings = _validate_spec(result.get("logic_analysis"))
        if _spec_findings:
            result["logic_spec_findings"] = _spec_findings
            # 仅当 LLM 已输出 logic_analysis（非静默兜底路径）且 findings 非空时
            # 才标记 logic_degraded=True（静默兜底路径已在上方 L176 标记）
            if not result.get("logic_degraded", False):
                result["logic_degraded"] = True
            logger.warning(
                "M10 schema 校验：%d 条 findings（fields=%s）",
                len(_spec_findings),
                [f.get("field") for f in _spec_findings],
            )
            if _logic_spec_strict_enabled() and result.get("logic_degraded"):
                _strict_reject(
                    result, "M10 LOGIC_SPEC_STRICT_ENABLE=true：logic_analysis schema 校验失败，拒绝静默兜底"
                )
        # M10（2026-09-29 审查 P0）：logic_coverage 字段消费者验证。
        # 历史口径：prompt 要求 test_case 标注 logic_coverage，但全仓
        # 无任何消费者（字段纯写入无读取）。现补 coverage_completeness
        # 观测指标（0.0–1.0）：统计 test_cases 中非空 logic_coverage
        # 的占比，供实验层度量"逻辑驱动"实际生效程度（纯观测，默认
        # 零行为变化）。
        _cases = result.get("test_cases") or []
        if _cases:
            _with_cov = sum(1 for c in _cases if isinstance(c, dict) and c.get("logic_coverage"))
            result["coverage_completeness"] = round(_with_cov / len(_cases), 4)
        else:
            result["coverage_completeness"] = None

        # 记录规划完成日志，便于追踪每个函数的分析耗时
        logger.info("Planner 完成对 %s 的逻辑分析", result.get("function_name", "unknown"))
        return result
