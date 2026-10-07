"""确定性优先修复路由（修复引擎批次 IV，2026-10-07，ADR-0019）。

背景（第二阶段"合成"段材料 + 前沿实证）：
    - 修复循环对 syntax/import/name-error 类失败仍整轮进 LLM——而其中
      一部分存在**零 token 的确定性修法**（To Run or Not to Run，
      arXiv:2606.26978：执行/验证按成本调度；Syntax Repair as
      Language Intersection，arXiv:2507.11873：语法修复可确定性化）；
    - PAGENT（ACM DL 2026）：类型与数据结构错误占失败补丁 27.19%，
      针对性确定性层可挽回其中 22.8%（29/127）——"按错误模式前置
      确定性修复器，残余才进 LLM"的路线依据。

本模块提供三个**保守的**确定性变换器（均零 LLM、可单测、失败即弃）：

    1. missing_import_inference（RUNTIME·NameError）：
       `NameError: name 'X' is not defined` 且 X ∈ 常用标准库模块集、
       目标代码以词边界使用 X、顶层无 `import X` → 在最后一个顶层
       import 后插入 `import X`；
    2. import_alias_backfill（IMPORT_ERROR·cannot import name）：
       `cannot import name 'X'` 且目标顶层恰有一个同前缀重命名嫌疑符号
       Y（Y.startswith(X) 或 X.startswith(Y)，多重嫌疑 → 保守放弃）→
       模块级追加别名 `X = Y`（P3 契约回填启发式复用）；
    3. tab_indent_normalize（SYNTAX·IndentationError）：
       "inconsistent use of tabs and spaces" 且目标含制表符 → 全量
       归一为 4 空格缩进。

统一验证门：候选必须通过 ast.parse 且与原码不同，否则弃用
（attempted=True / patch_code=None / reason=validation_failed）。

接线（_debugger_node）：DETERMINISTIC_REPAIR_FIRST_ENABLE（默认关，
ADR-0003 惯例）开启时，首个修复轮**先**走本路由——产出候选则跳过
该轮 LLM 调用（省 token），由既有 executor 回归验证兜底；未产出则
照常进 LLM。每任务至多尝试一次（state["deterministic_repair_status"]
非 None 即不再进），确定性补丁失败后自然回落 LLM 路径。
"""

from __future__ import annotations

import ast
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

_ENV = "DETERMINISTIC_REPAIR_FIRST_ENABLE"

# 常用标准库模块集（NameError→缺 import 推断的白名单；刻意收窄——
# 只对"确认是标准库"的名字自动插入 import，避免为任意未知名造补丁）
_STDLIB_MODULES: frozenset[str] = frozenset(
    {
        "abc",
        "array",
        "bisect",
        "collections",
        "copy",
        "dataclasses",
        "datetime",
        "decimal",
        "enum",
        "fractions",
        "functools",
        "heapq",
        "io",
        "itertools",
        "json",
        "math",
        "os",
        "random",
        "re",
        "statistics",
        "string",
        "sys",
        "time",
        "typing",
        "unittest",
    }
)

_NAME_ERROR_RE = re.compile(r"NameError:\s*name '(\w+)' is not defined")
_CANNOT_IMPORT_RE = re.compile(r"cannot import name '(\w+)'")
_TAB_INCONSISTENT_RE = re.compile(r"inconsistent use of tabs and spaces", re.IGNORECASE)


def deterministic_repair_first_enabled() -> bool:
    """确定性优先修复路由开关（默认关；A/B 对照用）。"""
    return os.getenv(_ENV, "false").lower() in ("true", "1", "on")


def _top_level_names(code: str) -> set[str]:
    """目标代码的顶层绑定名（def/class/赋值），供重命名嫌疑检测。"""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _insert_import(code: str, module: str) -> str:
    """在最后一个顶层 import 之后插入 `import module`（无 import 时插到
    模块 docstring 之后；均无则插到文件首）。纯行级操作，零语义风险。"""
    lines = code.splitlines(keepends=True)
    last_import_idx = -1
    doc_end = 0
    try:
        tree = ast.parse(code)
        first = tree.body[0] if tree.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            doc_end = first.end_lineno or 0
    except SyntaxError:
        pass
    for idx, line in enumerate(lines):
        if re.match(r"^(?:import |from )", line):
            last_import_idx = idx
    insert_at = last_import_idx + 1 if last_import_idx >= 0 else doc_end
    stmt = f"import {module}\n"
    new_lines = [*lines[:insert_at], stmt, *lines[insert_at:]]
    return "".join(new_lines)


def _try_missing_import(code: str, test_output: str) -> tuple[str, str] | None:
    """变换器 1：NameError → 缺 import 推断。返回 (method, 新码) 或 None。"""
    match = _NAME_ERROR_RE.search(test_output or "")
    if not match:
        return None
    name = match.group(1)
    if name not in _STDLIB_MODULES:
        return None
    if not re.search(rf"\b{re.escape(name)}\b", code):
        return None  # 目标代码未使用该名（NameError 可能来自测试自身）
    if re.search(rf"^import {re.escape(name)}\b", code, re.MULTILINE):
        return None  # 顶层已有 import（NameError 另有来源）
    new_code = _insert_import(code, name)
    if new_code == code:
        return None
    return "missing_import_inference", new_code


def _try_import_alias(code: str, test_output: str) -> tuple[str, str] | None:
    """变换器 2：cannot import name 'X' → 同前缀重命名嫌疑回填别名。"""
    match = _CANNOT_IMPORT_RE.search(test_output or "")
    if not match:
        return None
    wanted = match.group(1)
    suspects = {
        name
        for name in _top_level_names(code)
        if name != wanted and (name.startswith(wanted) or wanted.startswith(name))
    }
    if len(suspects) != 1:
        return None  # 无嫌疑 / 多重嫌疑 → 保守放弃（多重时确定性不足）
    replacement = suspects.pop()
    new_code = code.rstrip("\n") + f"\n\n{wanted} = {replacement}\n"
    return "import_alias_backfill", new_code


def _try_tab_normalize(code: str, test_output: str) -> tuple[str, str] | None:
    """变换器 3：tab/空格混用缩进错误 → 全量归一 4 空格。"""
    if not _TAB_INCONSISTENT_RE.search(test_output or ""):
        return None
    if "\t" not in code:
        return None
    return "tab_indent_normalize", code.replace("\t", "    ")


_TRANSFORMERS = (_try_missing_import, _try_import_alias, _try_tab_normalize)


def attempt_deterministic_repair(
    *,
    target_code: str,
    test_output: str,
    error_category: str = "",
) -> dict[str, Any]:
    """确定性优先修复入口（类别路由 + 统一验证门）。

    Returns:
        {"attempted": bool——是否有变换器匹配到修法线索；
         "method": str | None——命中变换器名；
         "reason": str——未产出补丁的原因（no_matching_transformer /
         validation_failed / empty_target）；
         "patch_code": str | None——确定性补丁（fenced 由调用方包装）；
         "category": str——入参类别透传（观测用）。}
    """
    outcome: dict[str, Any] = {
        "attempted": False,
        "method": None,
        "reason": "no_matching_transformer",
        "patch_code": None,
        "category": error_category,
    }
    if not target_code.strip():
        outcome["reason"] = "empty_target"
        return outcome
    for transformer in _TRANSFORMERS:
        hit = transformer(target_code, test_output)
        if hit is None:
            continue
        method, new_code = hit
        outcome["attempted"] = True
        outcome["method"] = method
        try:
            ast.parse(new_code)
        except SyntaxError as exc:
            outcome["reason"] = f"validation_failed:{exc.msg}"
            logger.warning("确定性修复候选（%s）未过 AST 门：%s", method, exc.msg)
            return outcome
        if new_code == target_code:
            outcome["reason"] = "validation_failed:no_change"
            return outcome
        outcome["patch_code"] = new_code
        outcome["reason"] = "produced"
        return outcome
    return outcome


def build_deterministic_debug_result(
    *,
    patch_code: str,
    method: str,
    reason: str,
    error_category: str,
) -> dict[str, Any]:
    """构造与 DebuggerAgent.debug() 返回**键集合同构**的确定性结果。

    下游 _debugger_node 按 debug() 契约消费这些键；此处补齐全部键并给
    零值，保证专家池/辩论/类型修复层等后续分支的读取不缺键。
    """
    return {
        "root_cause": f"确定性接管（{method}）：{reason}",
        "error_category": error_category or "UNKNOWN",
        # 规则级确定性修法，置信度按分类器最高档 0.9 口径
        "error_confidence": 0.9,
        "fix_strategy": f"deterministic::{method}",
        "patch": f"```python\n{patch_code}\n```",
        "adversarial_check": {"scenarios_checked": 0, "all_passed": False, "critic_degraded": False},
        "defect_type": "implementation_defect",
        "review_reason": None,
        "edit_intent_status": None,
        "position_aware_focus": {"focused": False, "function_name": None, "line": None, "hint": ""},
        "type_repair_findings": [],
        "mypy_findings_count": 0,
    }
