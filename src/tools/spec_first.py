"""P0-A-2（2026-10-12 独立评审落地）：规格优先生成（Spec-First Generation）。

背景（独立评审报告 §6 / 优化方案 P0-A，三源同向证据）：
    1. 项目自身阴性结果：plain_llm_df（检出优先协议）detection 44.8% vs
       aitester 完整编排 15.8%（−28pp）；48.6% 样本"全绿未检出"——
       根因是 Planner 读**缺陷代码**派生 expected_output，Generator 把
       实现行为当期望值（oracle-from-implementation），断言在 buggy 上
       全绿，检出被系统性抹掉；
    2. Zhao et al.（ISSTA 2026）misguidance effect：缺陷代码入提示会
       诱发"断言错误行为"的测试；
    3. Google Spec-Driven Test Generation（SpecOps '26）：生产代码上仅
       文档化前条件/后条件/未定义行为即 bug detection +9.8pp（p=0.0352）。

本模块实现两种 `DETECTION_SPEC_MODE` 干预臂（共享材料抽取 / 渲染管线）：

1. `replace`（P0-A-2，2026-10-12）：Generator prompt 中的"目标代码"块替换为
   **规约文档**（签名 + NL 规约 + SpecExpr 形式化子句 + 生成纪律）——LLM 只
   依据契约生成测试，接触不到实现细节，从源头切断
   oracle-from-implementation 锚点。
2. `augment`（M-1，2026-10-17，承接 L 轮 replace 阴性结论）：**保留完整缺陷
   代码**，在代码块之后**并列追加**人类独立规格锚——L 轮实测 replace 臂
   df 86.11% / doc 60.00% / union 61.76%（not_confirmed）表明"移除实现代码"
   是检出损失主因；增广是直接后续假设（代码 + 独立规格并列）。framing 与
   replace 不同：明确"规格锚与目标代码并列、请结合两者、实现与规格不一致时
   按规格构造期望值"，**不**说"本提示刻意不包含实现代码"。

设计口径（与 ADR-0003 一致：默认关，新开关独立）：
    - DETECTION_SPEC_MODE 缺省 "off"（历史口径：目标代码照常注入）；
    - "replace" 时仅当规约材料非空才替换（无材料 → 空串 → 调用方保持
      历史口径，不产出"无代码无规约"的空洞提示）；
    - "augment" 时仅当存在**非空**规约/规格材料才追加增广段（无材料 →
      空串 → 调用方保持历史口径 = 纯 df 代码提示，审计记 attempted_fallback）；
    - **既有 replace / off 渲染逐字节不变**：两模式共享 `_collect_spec_material`
      / `_render_spec_section` 管线，但 replace 的分帧/纪律行原样保留
      （tests/test_docstring_anchor.py 金标记锁定历史可复现性）；
    - 纯字符串渲染（零 LLM / 零子进程），失败路径保守返回空串；
    - 与 ORACLE_CONTEXT_MINIMAL 消融档同口径：minimal 时调用方不构建
      本段（该档意图是"无额外上下文"对照臂）。
    - P1（2026-10-17 独立评审 §6 P1 / A-02）：材料可选携带 `human_spec`
      键（模块级人类规格文本，见 module_spec_text）——键在场即进入 replace
      材料判定并渲染"独立于实现的规格锚"段落；不携带该键的既有材料（全部
      历史臂）渲染逐字节不变（tests/test_docstring_anchor.py 金标记锁定）。
"""

from __future__ import annotations

import ast
import logging
import os
import threading
from typing import Any

logger = logging.getLogger(__name__)

_ENV_SPEC_MODE = "DETECTION_SPEC_MODE"
# 合法取值（其余值按 "off" 处理并记 warning——保守：不认识的模式不改行为）
# augment（M-1，2026-10-17）：代码保留 + 人类规格锚并列追加（非替换）。
_SPEC_MODES = ("off", "replace", "augment")

# A-10（2026-10-16）：线程局部覆盖载体（与 config._DETECTION_FIRST_THREAD_LOCAL
# 同模式）。df_spec 臂（plain_llm_df_spec）在 --parallel 下与邻线程其它臂并发
# 执行——进程级 os.environ 无法区分"本线程在跑 df_spec 臂"，会串扰邻线程
# （X1 df 臂同源教训：run_plain_llm_df_baseline 用线程覆盖隔离检出优先开关）。
_SPEC_MODE_THREAD_LOCAL = threading.local()


def set_spec_mode_thread_override(value: str | None) -> None:
    """设置/清除当前线程的规格模式覆盖（None = 回落 env 开关）。

    供 run_benchmark 的 plain_llm_df_spec 基线在自身 invoke 窗口内强制
    "replace"；finally 中置 None 恢复，防线程池复用残留。
    """
    _SPEC_MODE_THREAD_LOCAL.override = value


def detection_spec_mode() -> str:
    """规格模式开关（DETECTION_SPEC_MODE：off=历史口径 / replace=规约文档替代实现代码 /
    augment=代码保留 + 人类规格锚并列追加）。

    默认 "off"：Generator prompt 与历史逐字节一致。实验层显式设
    "replace" 启用 P0-A-2 对照臂（建议与 plain_llm_df 臂同基准跑
    3 种子，判据 McNemar p<0.01 且 δ≥+10pp）；设 "augment" 启用 M-1
    增广臂（plain_llm_df_doc_augment：完整代码 + 人类 docstring 规格锚并列）。

    读取口径：线程局部覆盖（set_spec_mode_thread_override，A-10 df_spec /
    P1 doc / M-1 augment 臂用）优先于 env；覆盖值为非法模式串时记 warning
    并回落 env 口径。
    """
    _override = getattr(_SPEC_MODE_THREAD_LOCAL, "override", None)
    if _override is not None:
        raw_override = str(_override).strip().lower()
        if raw_override in _SPEC_MODES:
            return raw_override
        logger.warning(
            "DETECTION_SPEC_MODE 线程覆盖值 %r 未识别（可选：off/replace/augment），回落 env 口径", _override
        )
    raw = (os.getenv(_ENV_SPEC_MODE, "off") or "off").strip().lower()
    if raw not in _SPEC_MODES:
        logger.warning("DETECTION_SPEC_MODE=%r 未识别（可选：off/replace/augment），按 off 处理", raw)
        return "off"
    return raw


def _extract_signature_line(source_code: str, function_name: str) -> str:
    """从源码提取目标函数签名行（保守：失败 / 未找到 → 空串）。

    只取签名（不取函数体——replace 模式的全部意义就是不暴露实现）。
    标注类型注解（若有）一并保留：注解是规约信息而非实现细节。
    """
    if not source_code or not function_name:
        return ""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return ""
    for node in tree.body:  # 顶层函数 + 顶层类的直接方法（与 extract_signature_params 同口径）
        target = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == function_name:
                    target = sub
                    break
        if target is None:
            continue
        prefix = "async def" if isinstance(target, ast.AsyncFunctionDef) else "def"
        try:
            args = ast.unparse(target.args)
        except Exception:  # pragma: no cover - unparse 失败保守降级
            return ""
        returns = f" -> {ast.unparse(target.returns)}" if target.returns is not None else ""
        return f"{prefix} {target.name}({args}){returns}"
    return ""


def _docstring_of(source_code: str, function_name: str) -> str:
    """提取目标函数 docstring（若有）——文档化契约是规格材料的一部分。"""
    if not source_code or not function_name:
        return ""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return ""
    for node in tree.body:
        target = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
            target = node
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == function_name:
                    target = sub
                    break
        if target is None:
            continue
        doc = ast.get_docstring(target)
        return (doc or "").strip()
    return ""


def _bullet_list(items: list[str], label: str) -> list[str]:
    """把一组规约子句渲染为 "- label：item" 行（空组不产行）。"""
    return [f"- {label}：{item}" for item in items if item and item.strip()]


def module_spec_text(source_code: str) -> str:
    """提取模块级人类规格文本（独立于缺陷实现的规格锚候选，P1 三级回退 (a) 档）。

    背景（独立评审 2026-10-17 §6 P1 / A-02）：QuixBugs 缺陷程序**没有函数
    docstring**，但 40/41 个程序在文件尾部有一个顶层字符串字面量——人类书写的
    Input/Output/Examples 规格块（只有 ``node.py`` 缺失）。既有 `_docstring_of`
    只取函数 docstring，取不到该块；本 helper 补上这条"独立于缺陷实现"的
    人类规格来源（锚材料不来自对 buggy 代码的再描述，故不受
    oracle-from-implementation 机制污染）。

    提取规则（纯 stdlib AST，确定性、零 LLM）：
        1. 只认**模块级** ``Expr(Constant str)`` 语句（函数/类内部的不算——
           那不是模块级规格块）；
        2. 忽略 strip 后为空的字面量；
        3. 若存在"非首句"字面量（即不是模块 docstring 的顶层字符串），优先
           取**最靠后**的一个（QuixBugs 风格尾部规格块语义；多处时取尾部）；
        4. 否则回退首句模块 docstring（``ast.get_docstring`` 同口径）；
        5. 语法错误 / 空输入 / 无字面量 → 空串（保守：调用方自行决定回退）。

    Returns:
        规格文本（已 strip）；无可提取材料时返回空串。
    """
    if not source_code:
        return ""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError, TypeError, MemoryError, RecursionError):
        return ""
    body = getattr(tree, "body", None)
    if not body:
        return ""
    # 模块 docstring 只可能是"首条语句且为字符串字面量"
    first_is_docstring = (
        isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )
    literals: list[tuple[int, str]] = []
    for index, node in enumerate(body):
        value = getattr(node, "value", None)
        if not isinstance(node, ast.Expr) or not isinstance(value, ast.Constant):
            continue
        if not isinstance(value.value, str):
            continue
        text = value.value.strip()
        if text:
            literals.append((index, text))
    if not literals:
        return ""
    # 非首句字面量 = 不是模块 docstring 的顶层字符串（尾部规格块语义优先）
    non_doc = [text for index, text in literals if not (first_is_docstring and index == 0)]
    if non_doc:
        return non_doc[-1]
    return literals[0][1]


def sole_top_level_function_name(source_code: str) -> str:
    """模块唯一顶层函数名（确定性 AST 回退；无或>1 个顶层函数 → 空串）。

    用途（2026-10-14 度量侧修正）：Planner 降级（M10：JSON 解析失败/
    缺 function_name）时，spec 度量侧（nodes.py 的 spec_compile_rate /
    spec_reject_reasons）拿不到函数名 → 签名参数提取回退历史默认集
    {r,x,a,b,y} → 自定义参数名的可编译子句被误判 unknown_name（合成集
    实测 270 次拒绝的主要来源）。本 helper 在**模块恰有一个顶层函数**时
    给出无歧义回退（单函数模块是合成集/ULT 的主导形态）；多函数模块
    （含 helper）歧义，保守返回空串（维持原保守口径，不猜）。

    只读源码 AST，零 LLM、确定性。刻意**不**改注入侧（replace 段的
    target_function 解析口径）——注入侧改变会动处理（prompt 内容），
    属另一实验；本回退只修度量。
    """
    if not source_code:
        return ""
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return ""
    names = [node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    return names[0] if len(names) == 1 else ""


# ─── 渲染管线（replace / augment 共享）──────────────────────────────────────
# 两模式共享**材料抽取**（_collect_spec_material）与**主体渲染**
# （_render_spec_section）：签名 / 模块名 / 人类规格锚 / docstring / NL 规约 /
# SpecExpr 子句的顺序与措辞完全一致（历史工件可复现性的前提）。差异只在
# 分帧（framing）与生成纪律：
#   - replace：目标代码块被规约文档**替换**，不得让 LLM 接触实现；
#   - augment：目标代码**保留**，规格锚并列追加，要求"实现与规格不一致时
#     按规格构造期望值（这是检出缺陷的关键）"——不得出现"不包含实现代码"。
_REPLACE_HEADER: tuple[str, ...] = (
    "【规格优先模式（Spec-First）：本提示刻意不包含实现代码】",
    "请仅依据以下规约文档与函数签名生成测试。实现细节未知且**不得臆测**——",
    "照猜想中的实现行为写断言（oracle-from-implementation）会系统性抹掉缺陷检出，",
    "是本模式要杜绝的首要失败形态。",
    "",
)
_AUGMENT_HEADER: tuple[str, ...] = (
    "【规格增广模式（Spec-Augment）：规格锚与目标代码并列】",
    "上方已完整给出目标代码；以下并列追加同一函数的人类独立规格锚（独立于缺陷实现书写）。",
    "请结合两者：当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）。",
    ("不得仅凭当前实现的实际行为推断期望值——那会把缺陷固化成预期（oracle-from-implementation），系统性抹掉检出。"),
    "",
)
_REPLACE_DISCIPLINE: tuple[str, ...] = (
    "【生成纪律】",
    "1. 每个测试必须断言上述规约中可判定的性质（后置 / 不变量 / 边界）；",
    "2. 期望值只能来自规约与 docstring 约定；规约未覆盖的行为禁止臆造具体值——",
    "   改用记录实际行为的探索性断言并在 docstring 标注需人工确认；",
    "3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；",
    "4. 不得访问规约与签名之外的属性 / 符号。",
)
_AUGMENT_DISCIPLINE: tuple[str, ...] = (
    "【生成纪律（增广模式）】",
    "1. 人类规格 / docstring 明确覆盖的行为，必须按规格断言——不得以当前实现的实际行为作为期望值；",
    "2. 规格与实现不一致处即为嫌疑缺陷：按规格推导正确结果并断言（这是检出缺陷的关键）；",
    "3. 输入构造必须满足前置条件（不满足前件的输入应走 pytest.raises 路径或排除）；",
    "4. 可以阅读上方目标代码理解调用方式，但不得访问规约与签名之外的属性 / 符号。",
)


def _collect_spec_material(
    test_plan: dict[str, Any] | None,
    target_code: str,
    target_function: str = "",
) -> dict[str, Any] | None:
    """抽取规约材料（replace / augment 共享管线；非 dict 输入 → None）。

    Returns:
        材料 dict（键：fn / signature / docstring / has_human_spec_key /
        human_spec / pre_nl / post_nl / inv_nl / edge / pre_expr / post_expr /
        inv_expr）；非 dict 输入返回 None。空材料由调用方按模式判定。
    """
    if not isinstance(test_plan, dict):
        return None
    fn = target_function or test_plan.get("function_name") or ""
    logic = test_plan.get("logic_analysis")
    logic = logic if isinstance(logic, dict) else {}

    # 规约材料三源：NL 通道 / SpecExpr 形式化通道 / 边界情况
    pre_nl = [str(c) for c in (logic.get("preconditions") or []) if str(c).strip()]
    post_nl = [str(c) for c in (logic.get("postconditions") or []) if str(c).strip()]
    inv_nl = [str(c) for c in (logic.get("invariants") or []) if str(c).strip()]
    edge = [str(c) for c in (logic.get("edge_cases") or []) if str(c).strip()]
    pre_expr = [str(c) for c in (logic.get("preconditions_expr") or []) if str(c).strip()]
    post_expr = [str(c) for c in (logic.get("postconditions_expr") or []) if str(c).strip()]
    inv_expr = [str(c) for c in (logic.get("invariants_expr") or []) if str(c).strip()]
    # P1 独立锚（2026-10-17）：human_spec 键的**在场**决定 replace 材料判定
    # （空串也算材料——docstring 锚臂对"无人类规格"任务仍走替换口径而不是
    # 回落注入代码；是否渲染该段落由非空性决定）。不在场 → 历史材料判定
    # 逐字节不变。augment 只认真实非空内容（无锚可并列时回落 df 口径）。
    has_human_spec_key = "human_spec" in test_plan
    human_spec = ""
    if has_human_spec_key:
        raw_human_spec = test_plan.get("human_spec")
        human_spec = "" if raw_human_spec is None else str(raw_human_spec).strip()
    return {
        "fn": fn,
        "signature": _extract_signature_line(target_code, fn),
        "docstring": _docstring_of(target_code, fn),
        "has_human_spec_key": has_human_spec_key,
        "human_spec": human_spec,
        "pre_nl": pre_nl,
        "post_nl": post_nl,
        "inv_nl": inv_nl,
        "edge": edge,
        "pre_expr": pre_expr,
        "post_expr": post_expr,
        "inv_expr": inv_expr,
    }


def _material_sources(material: dict[str, Any]) -> list[Any]:
    """材料内容源（不含"键在场"语义；human_spec 只算非空内容）。"""
    return [
        material["pre_nl"],
        material["post_nl"],
        material["inv_nl"],
        material["edge"],
        material["pre_expr"],
        material["post_expr"],
        material["inv_expr"],
        material["docstring"],
        material["human_spec"],
    ]


def _has_replace_material(material: dict[str, Any]) -> bool:
    """replace 材料判定（历史口径逐字节保留：内容源非空 **或** human_spec 键在场）。"""
    return any(_material_sources(material)) or bool(material["has_human_spec_key"])


def _has_augment_material(material: dict[str, Any]) -> bool:
    """augment 材料判定：只认真实非空内容（无锚可并列 → 调用方回落 df 口径）。"""
    return any(_material_sources(material))


def _render_spec_section(material: dict[str, Any], module_name: str, *, augmented: bool) -> str:
    """渲染规格段主体（两模式共享；仅分帧与生成纪律不同）。"""
    lines: list[str] = list(_AUGMENT_HEADER if augmented else _REPLACE_HEADER)
    sig = material["signature"]
    if sig:
        lines.append(f"函数签名：{sig}")
    if module_name:
        lines.append(f"被测模块名：{module_name}（import 必须 `from {module_name} import ...`）")
    if material["human_spec"]:
        # 顺序纪律：人类独立锚优先于函数 docstring（后者可能缺失/被实现污染）
        lines.append("")
        lines.append("【独立于实现的规格锚（人类 docstring）】")
        lines.append(material["human_spec"])
    if material["docstring"]:
        lines.append("")
        lines.append("【文档化契约（docstring）】")
        lines.append(material["docstring"])

    nl_lines: list[str] = []
    nl_lines.extend(_bullet_list(material["pre_nl"], "前置条件"))
    nl_lines.extend(_bullet_list(material["post_nl"], "后置条件"))
    nl_lines.extend(_bullet_list(material["inv_nl"], "不变量"))
    nl_lines.extend(_bullet_list(material["edge"], "边界情况"))
    if nl_lines:
        lines.append("")
        lines.append("【自然语言规约（期望值的唯一合法来源）】")
        lines.extend(nl_lines)

    expr_lines: list[str] = []
    expr_lines.extend(_bullet_list(material["pre_expr"], "前置（可执行）"))
    expr_lines.extend(_bullet_list(material["post_expr"], "后置（可执行）"))
    expr_lines.extend(_bullet_list(material["inv_expr"], "不变量（可执行）"))
    if expr_lines:
        lines.append("")
        lines.append("【可执行规约（SpecExpr 形式化子句，可直接转写为断言）】")
        lines.extend(expr_lines)

    lines.append("")
    lines.extend(_AUGMENT_DISCIPLINE if augmented else _REPLACE_DISCIPLINE)
    return "\n".join(lines)


def build_spec_replace_section(
    test_plan: dict[str, Any] | None,
    target_code: str,
    module_name: str = "",
    target_function: str = "",
) -> str:
    """渲染规格优先提示段（规约文档，替代目标代码注入 Generator prompt）。

    Args:
        test_plan: 规约材料（Planner 测试计划的 ``logic_analysis`` 子集；或
            df_spec / docstring 锚臂预载的锚材料 dict）。None / 无规约材料
            → 空串。P1（2026-10-17）：键 ``human_spec`` **显式存在**时即为
            人类独立规格锚（docstring 锚臂），其值可为空串——"键在场"本身
            就进入材料判定（锚臂语义：无锚也必须走替换口径，不得注入缺陷
            实现代码）；渲染为空时省略该段落。未携带该键的材料（既有
            Planner 锚 / 全部历史臂）渲染结果逐字节不变。
        target_code: 被测源码（**只用于提取签名与 docstring**，函数体
            不进入产物——replace 模式的核心纪律）。
        module_name: 模块名（import 约束用）。
        target_function: 目标函数名（签名提取用；缺省时从 test_plan
            的 function_name 回退）。

    Returns:
        规格文档字符串；无任何规约材料时返回空串（调用方保持历史口径，
        即继续注入目标代码——不产出"无代码无规约"的空洞提示）。
    """
    material = _collect_spec_material(test_plan, target_code, target_function)
    if material is None or not _has_replace_material(material):
        return ""  # 无规约材料：调用方保持历史口径（注入目标代码）
    return _render_spec_section(material, module_name, augmented=False)


def build_spec_augment_section(
    test_plan: dict[str, Any] | None,
    target_code: str,
    module_name: str = "",
    target_function: str = "",
) -> str:
    """渲染规格增广提示段（M-1 / 2026-10-17：完整代码保留 + 人类规格锚并列追加）。

    与 :func:`build_spec_replace_section` 共享材料抽取 / 主体渲染管线，但
    framing 不同：目标代码**仍在提示中**（由 generator._build_query 注入
    code block），本段在 code block 之后并列追加规格材料，并要求
    "当实现与规格不一致时，按规格构造期望值（这是检出缺陷的关键）"。
    本段**不得**出现"本提示刻意不包含实现代码"之类 replace 专属措辞。

    材料判定比 replace 严格：只认真实非空内容（human_spec / docstring /
    NL 规约 / SpecExpr 子句任一非空）；仅有 ``human_spec`` 空键（如
    QuixBugs ``node.py``）→ 空串 → 调用方回落纯 df 代码提示
    （审计记 attempted_fallback，不产出"并列了不存在的锚"的误导提示）。

    Args:
        test_plan: 规格/锚材料（同 replace：Planner 计划子集或锚表条目）。
        target_code: 被测源码（只用于提取签名 / docstring；函数体不会进入
            本段——它已由调用方作为 code block 注入）。
        module_name: 模块名（import 约束用）。
        target_function: 目标函数名（缺省从 test_plan.function_name 回退）。

    Returns:
        增广段字符串；无非空规格材料时返回空串（调用方保持 df 历史口径）。
    """
    material = _collect_spec_material(test_plan, target_code, target_function)
    if material is None or not _has_augment_material(material):
        return ""
    return _render_spec_section(material, module_name, augmented=True)


__all__ = [
    "build_spec_augment_section",
    "build_spec_replace_section",
    "detection_spec_mode",
    "module_spec_text",
    "set_spec_mode_thread_override",
    "sole_top_level_function_name",
]
