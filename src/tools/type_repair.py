"""
PAGENT 风格类型修复层（2.1 补丁类型错误后处理）。

背景：
    PAGENT 的系统性研究发现，在 SWE-bench Lite 上，类型和数据结构管理
    错误单独占所有失败补丁的 27.19%。PAGENT 是一个模型无关的后处理
    智能体，通过"仓库级静态分析 + LLM 类型推断"的混合架构修复生成
    补丁中的类型相关故障，在七个前沿智能体上修复了 75/217（34.56%）
    个类型相关失败。

本模块落地口径（零外部硬依赖、可复算、保守降级）：
    1. 静态层：用 ast 解析补丁后的代码，识别常见类型/数据结构缺陷
       （变量被重新赋值为不同类型、返回值类型与声明不一致、
       容器类型混用、属性/方法缺失等可静态判定的信号），产出
       "类型疑点"列表（纯标准库，零 LLM token）；
    2. LLM 层（可选）：疑点非空且启用 TYPE_REPAIR_LLM_ENABLE=true 时，
       把疑点注入 LLM 让其做类型推断与修复，产出修订补丁；
    3. 回环验证：修订补丁重新经过 patch_applier 的命名契约检查
       （check_naming_contract），契约破坏则拒绝修订（与语法失败同口径）。

设计约束：
    - 静态层为保守启发式（宁可漏报不可误报破坏正确代码）；
    - LLM 层默认关闭（TYPE_REPAIR_LLM_ENABLE），未启用时仅输出疑点
      不修改补丁（观测层，不影响历史实验口径）；
    - 全部失败路径降级为"返回原补丁 + 疑点记录"，不阻断修复主流程。
"""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ─── 开关 ────────────────────────────────────────────────────────────────────


def _type_repair_llm_enabled() -> bool:
    """2.1 类型修复 LLM 层开关（TYPE_REPAIR_LLM_ENABLE=true 时启用，默认 false）。

    默认关闭：未启用时本模块只做静态疑点识别（观测层），不修改补丁，
    保持历史实验口径；启用后 LLM 推断 + 修订 + 契约回环验证生效。
    """
    return os.getenv("TYPE_REPAIR_LLM_ENABLE", "false").lower() == "true"


# 静态疑点：每个疑点为 {file, line, message, kind} 的字典。
# kind 取值（与 PAGENT 类型故障分类对齐的保守子集）：
#   - type_mismatch:  变量在同一作用域被重新赋值为明显不同类型
#   - container_mixed: 同一变量先被初始化为 list/dict/set 又被赋为标量
#   - undefined_attr:  补丁新代码引用了原代码中不存在的顶层属性/函数
#   - return_inconsist: 函数存在多个 return，返回值的字面类型不一致


def _infer_literal_type(node: ast.expr) -> str | None:
    """从字面量/简单表达式推断粗类型标签（仅保守判定，推断不出返回 None）。"""
    if isinstance(node, ast.Constant):
        v = node.value
        if isinstance(v, bool):
            return "bool"
        if isinstance(v, int):
            return "int"
        if isinstance(v, float):
            return "float"
        if isinstance(v, str):
            return "str"
        if isinstance(v, bytes):
            return "bytes"
        if isinstance(v, type(None)):
            return "None"
        return None
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"
    return None


def _infer_call_return_type(call: ast.expr, known_calls: dict[str, str]) -> str | None:
    """已知调用表命中时返回其返回类型（保守：仅查表，不递归推断）。

    仅当 call 是 ast.Call 且 func 为简单 Name 时查表；其他表达式
    （BinOp / 属性访问等）推断不出，返回 None（保守不报）。
    """
    if not isinstance(call, ast.Call):
        return None
    if isinstance(call.func, ast.Name):
        return known_calls.get(call.func.id)
    return None


def _collect_assign_types(
    func: ast.AST,
) -> tuple[dict[str, list[tuple[int, str]]], dict[str, list[tuple[int, str]]]]:
    """收集函数体内"变量名 → 各次赋值的 (行号, 类型标签)"。

    返回 (var_type_hist, container_hist)：
    - var_type_hist: 任意变量（赋值/_augassign）的类型历史
    - container_hist: 仅容器初始化（list/dict/set 字面量）的历史
    """
    var_type_hist: dict[str, list[tuple[int, str]]] = {}
    container_hist: dict[str, list[tuple[int, str]]] = {}
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    # 2026-09-26 round8 死逻辑清理（round7 遗留债务项）：
                    # 原右支 `_infer_call_return_type(node.value, _EMPTY_CALLS)`
                    # 传入的 _EMPTY_CALLS 是空 dict（下方 L127），
                    # `_infer_literal_type` 已返回 None 时（value 非常量，
                    # 如调用/属性/表达式），查空表必然返回 None，整个 or 恒为
                    # 左支——右支是死代码。删除后行为等价（纯字面量口径）。
                    # 预留扩展点（未来接"已知调用返回类型表"）时再按需恢复。
                    t = _infer_literal_type(node.value)
                    if t:
                        line = getattr(node, "lineno", 0)
                        var_type_hist.setdefault(target.id, []).append((line, t))
                        if t in ("list", "dict", "set", "tuple"):
                            container_hist.setdefault(target.id, []).append((line, t))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            t = _infer_literal_type(node.value)
            if t:
                line = getattr(node, "lineno", 0)
                var_type_hist.setdefault(node.target.id, []).append((line, t))
    return var_type_hist, container_hist


def _static_type_findings(original_code: str, patched_code: str) -> list[dict[str, Any]]:
    """静态层：对补丁前后代码做保守类型疑点识别（零 LLM token）。

    检查项（保守，宁可漏报）：
    1. 补丁新增代码中，同一变量被重新赋值为明显不同类型（int↔str /
       容器↔标量）→ type_mismatch；
    2. 补丁新代码引用了原代码中不存在的顶层函数/类/常量名 → undefined_attr
       （仅当补丁是"完整文件"场景才检查，单函数替换不查，避免误报）；
    3. 单个函数内存在多个 return，返回值的字面类型不一致 → return_inconsist。

    无法解析任一侧代码时返回空列表（不阻断主流程）。
    """
    findings: list[dict[str, Any]] = []

    def _check_type_hist(code: str, side: str) -> None:
        try:
            tree = ast.parse(code)
        except (SyntaxError, ValueError):
            return
        for func in list(tree.body):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            var_type_hist, _ = _collect_assign_types(func)
            for var, hist in var_type_hist.items():
                if len(hist) < 2:
                    continue
                types_in_hist = {t for _, t in hist}
                # 仅当同一变量在函数内被赋值为"不同语义类型族"才报告
                # （保守：同族内的 int/float 不报，bool 与 int 在 Python 可互换不报）
                _family_members: dict[str, frozenset[str]] = {
                    "numeric": frozenset({"int", "float", "complex", "bool"}),
                    "text": frozenset({"str", "bytes"}),
                    "seq": frozenset({"list", "tuple"}),
                    "dict": frozenset({"dict", "set"}),
                    "none": frozenset({"None"}),
                }
                _type_family: dict[str, str] = {}
                for fam_name, members in _family_members.items():
                    for m in members:
                        _type_family[m] = fam_name
                families_hit = {_type_family.get(t, "other") for t in types_in_hist}
                # 存在 >=2 个不同语义族才报告（如 int 族 + text 族冲突）
                if len(families_hit - {"other"}) >= 2:
                    finding_kind = "container_mixed" if "dict" in families_hit else "type_mismatch"
                    findings.append(
                        {
                            "file": side,
                            "line": hist[-1][0],
                            "message": f"变量 {var!r} 在同函数内被赋值为冲突类型族 {sorted(types_in_hist)}",
                            "kind": finding_kind,
                        }
                    )
            # 3. return 不一致
            returns = [
                (sub.lineno, _infer_literal_type(sub.value))
                for sub in ast.walk(func)
                if isinstance(sub, ast.Return) and sub.value is not None
            ]
            typed_returns = [t for _, t in returns if t]
            if len(typed_returns) >= 2 and len(set(typed_returns)) > 1:
                findings.append(
                    {
                        "file": side,
                        "line": returns[-1][0],
                        "message": f"函数 {func.name} 的多个 return 字面类型不一致 {sorted(set(typed_returns))}",
                        "kind": "return_inconsist",
                    }
                )

    _check_type_hist(original_code, "original")
    _check_type_hist(patched_code, "patched")

    # 2. 完整文件场景：补丁引用了原代码不存在的顶层符号
    try:
        orig_tree = ast.parse(original_code)
        patched_tree = ast.parse(patched_code)
    except (SyntaxError, ValueError):
        return findings

    orig_top = set()
    for node in orig_tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            orig_top.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("__"):
                    orig_top.add(target.id)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and not node.target.id.startswith("__")
        ):
            orig_top.add(node.target.id)
    # 原代码中已被 import 的名称视为可用
    imported: set[str] = set()
    for node in orig_tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name)

    # 收集补丁中所有"函数局部名"（参数 / 局部赋值 / 嵌套定义），
    # 这些名字在函数体内可见，不应报 undefined_attr（仅查顶层可见名）
    patched_locals: set[str] = set()
    for func in ast.walk(patched_tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # 参数（args + posonlyargs + kwonlyargs + vararg + kwarg）
        a = func.args
        for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
            patched_locals.add(arg.arg)
        if a.vararg:
            patched_locals.add(a.vararg.arg)
        if a.kwarg:
            patched_locals.add(a.kwarg.arg)
        # 函数体内局部赋值 / 嵌套定义 / for / with 目标
        for sub in ast.walk(func):
            if isinstance(sub, ast.Assign):
                for tgt in sub.targets:
                    if isinstance(tgt, ast.Name):
                        patched_locals.add(tgt.id)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                patched_locals.add(sub.name)
            elif isinstance(sub, (ast.AugAssign, ast.AnnAssign)) and isinstance(sub.target, ast.Name):
                patched_locals.add(sub.target.id)
            # for / async for 目标（Name / Tuple-of-Names，`for i, j in ...` 形式）
            # 2026-09-26 round8（tools 子代理 P2 F5a）：直接取 sub.target（精确
            # 目标节点），替代 iter_child_nodes 宽匹配——旧写法会同时命中
            # target 与 iter 子节点（`for x in some_list` 时 some_list 被误
            # 收集为局部可见名，虚增 patched_locals 掩盖真实 undefined_attr）；
            # 元组目标（Tuple 节点）经 elts 展开收集各元素名。
            elif isinstance(sub, (ast.For, ast.AsyncFor)):
                t = sub.target
                if isinstance(t, ast.Name):
                    patched_locals.add(t.id)
                elif isinstance(t, ast.Tuple):
                    for el in t.elts:
                        if isinstance(el, ast.Name):
                            patched_locals.add(el.id)
            # with 目标（`with ... as name` / `with ... as (a, b)`）
            elif isinstance(sub, ast.With):
                for item in sub.items:
                    if item.optional_vars is None:
                        continue
                    if isinstance(item.optional_vars, ast.Name):
                        patched_locals.add(item.optional_vars.id)
                    elif isinstance(item.optional_vars, ast.Tuple):
                        for el in item.optional_vars.elts:
                            if isinstance(el, ast.Name):
                                patched_locals.add(el.id)
            elif isinstance(sub, ast.ExceptHandler) and sub.name:
                patched_locals.add(sub.name)
    # 全局名（顶层赋值 / import / def）不应算"局部"——它们本就可见
    # 这里只把"函数体内可见名"从 undefined_attr 检查中排除

    # 补丁中 Call/Name 引用的顶层名称（排除局部可见名）
    patched_calls: set[str] = set()
    for walk_node in ast.walk(patched_tree):
        if isinstance(walk_node, ast.Call) and isinstance(walk_node.func, ast.Name):
            patched_calls.add(walk_node.func.id)
        elif isinstance(walk_node, ast.Name) and isinstance(walk_node.ctx, ast.Load):
            patched_calls.add(walk_node.id)
    # 仅报告"补丁新增"且原代码中不存在、不在局部可见、且不在常见内置名中的引用
    # 使用 builtins 目录 + 少量常用名，避免硬编码子集漏掉 open/abs/iter 等常见内置
    import builtins
    _builtin_allow = set(dir(builtins)) | {
        "assert",  # 关键字，非 builtins 成员
        "pytest",  # 测试框架常用入口（非内置，保守放行避免误报）
        "os",  # 高频导入模块（原代码 import 时已被 imported 集合排除，此处置顶）
        "sys",  # 同上
    }
    new_refs = (patched_calls - orig_top - imported - patched_locals) - _builtin_allow
    findings.extend(
        {
            "file": "patched",
            "line": 0,
            "message": f"补丁引用了原代码中不存在的顶层名称 {name!r}（可能未导入或拼写错误）",
            "kind": "undefined_attr",
        }
        for name in sorted(new_refs)
    )
    return findings


def _repair_with_llm(
    original_code: str,
    patched_code: str,
    findings: list[dict[str, Any]],
    repair_fn: Any,
) -> str | None:
    """LLM 层：把静态疑点交给 repair_fn（LLM 调用回调）做类型推断与修复。

    repair_fn: 可调用 (query: str, original_code: str, patched_code: str) → str
    （返回修订后的补丁代码；由调用方注入，避免本模块直接依赖 BaseAgent /
    LLM 客户端，保持零硬依赖、可测试）。

    返回修订后的补丁代码；LLM 修订无效 / 异常时返回 None（调用方保留原补丁）。
    """
    if not findings:
        return None
    if repair_fn is None:
        return None
    lines = [
        "你是 Python 类型修复专家（PAGENT 式静态分析 + LLM 类型推断）。",
        "以下补丁被静态分析识别出若干类型/数据结构疑点，请做最小修改",
        "消除这些疑点，保持原有公共接口与行为不变：",
    ]
    lines.extend(f"- [line {f.get('line', 0)}] {f.get('kind')}: {f.get('message')}" for f in findings)
    lines.append("")
    lines.append(f"原始代码：\n```\n{original_code[:3000]}\n```\n")
    lines.append(f"当前补丁：\n```\n{patched_code[:3000]}\n```\n")
    lines.append("请只输出修订后的完整代码（用 ```python 包裹），不要输出其他文本。")
    try:
        repaired = repair_fn("\n".join(lines), original_code, patched_code)
    except Exception as e:
        logger.warning("类型修复 LLM 调用失败（保留原补丁）: %s", e)
        return None
    if not repaired:
        return None
    # 修订代码必须能通过 ast.parse（保守：语法错误的修订直接拒绝）
    try:
        ast.parse(repaired)
    except (SyntaxError, ValueError):
        logger.warning("类型修复产出的代码语法不合法（拒绝修订，保留原补丁）")
        return None
    return repaired


def type_repair_layer(
    original_code: str,
    patched_code: str,
    llm_repair: Any = None,
    enforce_contract: bool = True,
    enforce_contract_ref: str | None = None,
) -> dict[str, Any]:
    """PAGENT 风格类型修复层入口（2.1）。

    流程：
    1. 静态层：识别补丁前后代码的类型疑点（纯 ast，零 LLM token）；
    2. LLM 层（可选）：疑点非空且启用 TYPE_REPAIR_LLM_ENABLE 时，
       调用 llm_repair（调用方注入的 LLM 回调）做类型推断与修复；
    3. 回环验证：修订代码重新经过命名契约检查
       （patch_applier.check_naming_contract），契约破坏则拒绝修订。

    Args:
        original_code: 原始代码。
        patched_code: 应用补丁后的代码（Debugger 生成、patch_applier 应用后）。
        llm_repair: 可选 LLM 修复回调 (query, original_code, patched_code) → str。
            未提供且 TYPE_REPAIR_LLM_ENABLE=true 时，若本模块可惰性导入
            BaseAgent 则自动注入（保守：导入失败时仅做静态层）。
        enforce_contract: 是否对修订代码做命名契约回环检查（默认 True）。
        enforce_contract_ref: 契约回环检查的参照侧代码（默认 None，即使用
            original_code——check_naming_contract 的"删除检测"主语义：
            LLM 修订省略了原代码顶层符号即为契约破坏）。仅当需要改按
            "与补丁基线同符号集"口径校验时显式传入（参照侧 = 补丁后
            完整文件代码）。不传时行为不变（保守默认，
            DebuggerAgent.debug 主路径按原代码参照口径调用）。

    Returns:
        {"findings": 疑点列表, "repaired_code": 修订后代码（无修订时 = patched_code）,
         "repaired": bool, "contract_ok": bool, "missing_symbols": [缺失符号]}
        任何失败路径都不抛异常，保守降级为"未修订 + 疑点记录"。
    """
    findings = _static_type_findings(original_code, patched_code)
    result: dict[str, Any] = {
        "findings": findings,
        "repaired_code": patched_code,
        "repaired": False,
        "contract_ok": True,
        "missing_symbols": [],
    }
    if not findings:
        return result

    # 静态层已产出疑点。LLM 层（可选）：
    llm_layer = _type_repair_llm_enabled()
    if llm_layer and llm_repair is None:
        # 惰性尝试自动注入 BaseAgent 驱动的修复回调（导入失败仅做静态层）
        try:
            llm_repair = _auto_llm_repair()
        except Exception as e:
            logger.debug("类型修复 LLM 回调自动注入失败，仅做静态层: %s", e)
            llm_repair = None

    if llm_layer and llm_repair is not None:
        repaired = _repair_with_llm(original_code, patched_code, findings, llm_repair)
        if repaired:
            # 回环验证：修订代码重新经命名契约检查（P0 1.3 口径）
            if enforce_contract:
                try:
                    from src.tools.patch_applier import check_naming_contract

                    ok, missing = check_naming_contract(
                        enforce_contract_ref if enforce_contract_ref is not None else original_code,
                        repaired,
                    )
                    result["contract_ok"] = ok
                    result["missing_symbols"] = missing
                    if ok:
                        result["repaired_code"] = repaired
                        result["repaired"] = True
                        logger.info("类型修复成功（LLM 层），修订 %d 处疑点", len(findings))
                    else:
                        logger.warning("类型修复修订破坏命名契约（缺失 %s），拒绝修订", missing)
                except Exception as e:
                    logger.warning("类型修复契约回环检查异常（保守保留原补丁）: %s", e)
            else:
                result["repaired_code"] = repaired
                result["repaired"] = True
                logger.info("类型修复成功（LLM 层，未做契约回环）")
    else:
        logger.debug("类型疑点 %d 处（静态层，LLM 层未启用或未注入回调）", len(findings))
    return result


def _auto_llm_repair() -> Any:
    """惰性构造 BaseAgent 驱动的类型修复 LLM 回调（导入失败抛异常，由调用方降级）。

    复用 DebuggerAgent 的 system prompt（类型修复属于调试修复子类），
    保持"修复代码而非测试代码"的口径。
    """
    from src.agents.debugger import DebuggerAgent

    agent = DebuggerAgent()

    def _repair(query: str, original_code: str, patched_code: str) -> str:
        raw = agent._call_llm_with_cache(query)
        # 提取 ```python 代码块（与 Debugger 主路径同口径）
        from src.utils.helpers import extract_code_block

        return extract_code_block(raw, language="python")

    return _repair
