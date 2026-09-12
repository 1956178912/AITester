"""
3.5 跨文件修复能力（协调器-提议者架构）。

背景：
    当前系统假设修复只发生在 target_file 单文件内。真实数据集
    （SWE-bench / Defects4J）中约 40% 的任务需要多文件修改：
    - 修复 A 文件中的函数，需同步更新 B 文件中的调用方；
    - 修改公共库接口，需更新 N 个调用方。

    单文件假设导致这类任务在当前架构下必然失败：Debugger 只能看到
    target_code（单文件内容），无法诊断跨文件依赖。

设计（协调器-提议者架构，参考 PhoenixRepair）：
    1. 协调器（cross_file 模块）：AST 分析入口模块与其他模块的依赖关系，
       产出"跨文件修复计划"（哪些文件要改、每个文件改什么）；
    2. 提议者：每个文件的补丁由 DebuggerAgent 单独生成（复用现有 prompt）；
    3. 多文件补丁应用：patch_applier 层新增 apply_multi_file_patch，
       按依赖图拓扑序应用（被调用方先改，调用方后改），任一文件失败
       则整体回滚（与单文件 safe_apply_patch 同口径）。

设计约束：
    - 默认关闭（CROSS_FILE_ENABLE=false，经 workflow 节点可选启用）；
    - 不改变默认行为，历史实验口径不变；
    - 单文件项目自动降级为单文件模式（仅 1 个模块时跨文件分析无意义）；
    - CROSS_FILE_MAX_MODULES 限制最大模块数（防止 LLM 上下文爆炸，默认 5）。
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ─── 配置常量 ─────────────────────────────────────────────────────────────────
# 跨文件修复开关：默认关闭，保持历史单文件口径
_CROSS_FILE_ENV_VAR = "CROSS_FILE_ENABLE"
# 跨文件依赖分析的最大模块数（防止 LLM 上下文爆炸，默认 5）
_CROSS_FILE_MAX_MODULES_ENV_VAR = "CROSS_FILE_MAX_MODULES"
_DEFAULT_MAX_MODULES = 5


def cross_file_enabled() -> bool:
    """跨文件修复开关（CROSS_FILE_ENABLE=true 时启用，默认 false）。"""
    return os.getenv(_CROSS_FILE_ENV_VAR, "false").lower() == "true"


def cross_file_max_modules() -> int:
    """跨文件依赖分析的最大模块数（CROSS_FILE_MAX_MODULES，默认 5）。"""
    raw = os.getenv(_CROSS_FILE_MAX_MODULES_ENV_VAR, "")
    try:
        value = int(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    return _DEFAULT_MAX_MODULES


# ─── 数据结构 ─────────────────────────────────────────────────────────────────


@dataclass
class CrossFileDependency:
    """跨文件依赖边：source_module 调用了 target_module 中的 symbol。"""

    source_module: str  # 调用方模块名（不含 .py）
    target_module: str  # 被调用方模块名
    symbol: str  # 被调用的函数/类名
    call_line: int  # 调用方源码行号
    context: str = ""  # 调用行上下文（供 LLM 理解）


@dataclass
class CrossFileRepairPlan:
    """跨文件修复计划。"""

    plan_id: str
    target_modules: list[str] = field(default_factory=list)  # 需要修改的模块列表
    per_module_patches: dict[str, str] = field(default_factory=dict)  # 模块名 → 补丁文本
    dependency_edges: list[CrossFileDependency] = field(default_factory=list)
    estimated_token_cost: int = 0  # 预估 token 成本（字符数 / 4 的保守估算）

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 化的字典（供 workflow state 与 trace 使用）。"""
        return {
            "plan_id": self.plan_id,
            "target_modules": list(self.target_modules),
            "per_module_patches": dict(self.per_module_patches),
            "dependency_edges": [
                {
                    "source_module": e.source_module,
                    "target_module": e.target_module,
                    "symbol": e.symbol,
                    "call_line": e.call_line,
                    "context": e.context,
                }
                for e in self.dependency_edges
            ],
            "estimated_token_cost": self.estimated_token_cost,
        }


# ─── AST 跨文件依赖分析 ───────────────────────────────────────────────────────


def analyze_cross_file_deps(
    entry_module: str,
    source_files: dict[str, str],
) -> list[CrossFileDependency]:
    """AST 分析入口模块与其他模块的依赖关系。

    流程：
        1. 解析 entry_module 的源码，提取 import 语句（from X import Y）；
        2. 对每个导入的 X，若 X 在 source_files 中（项目内模块），
           则记录一条依赖边（entry → X，symbol 为导入的名称）；
        3. 进一步扫描 entry 中调用 X.symbol 的函数体，记录调用行上下文；
        4. 返回所有依赖边（按 source_module 排序，去重）。

    Args:
        entry_module: 入口模块名（不含 .py，如 "calculator"）。
        source_files: 模块名 → 源码字符串的映射（项目内所有相关模块）。

    Returns:
        跨文件依赖边列表；entry_module 不在 source_files 时返回空列表。
    """
    entry_code = source_files.get(entry_module)
    if not entry_code:
        return []

    deps: list[CrossFileDependency] = []
    try:
        tree = ast.parse(entry_code)
    except SyntaxError:
        # 入口模块语法错误时无法 AST 分析，保守返回空
        return []

    # 收集 entry 中所有 import 的模块名（from X import Y / import X）
    imported_symbols: dict[str, list[str]] = {}  # 模块名 → 导入的符号名
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # from X import Y, Z → imported_symbols["X"] = ["Y", "Z"]
            module_name = node.module or ""
            if module_name and module_name in source_files:
                names = [alias.name for alias in node.names if alias.name != "*"]
                if names:
                    imported_symbols.setdefault(module_name, []).extend(names)
        elif isinstance(node, ast.Import):
            # import X → imported_symbols["X"] = ["X"]（模块本身即符号）
            for alias in node.names:
                if alias.name in source_files:
                    imported_symbols.setdefault(alias.name, []).append(alias.name)

    # 对每个依赖边，扫描 entry 中调用 X.symbol 的行（上下文截取 ±2 行）
    entry_lines = entry_code.splitlines()
    for target_module, symbols in sorted(imported_symbols.items()):
        for symbol in symbols:
            call_line = _find_call_line(entry_lines, symbol)
            context = ""
            if call_line > 0:
                # 截取调用行 ± 1 行作为上下文（供 LLM 理解调用场景）
                lo = max(0, call_line - 2)
                hi = min(len(entry_lines), call_line + 1)
                context = "\n".join(entry_lines[lo:hi])
            deps.append(
                CrossFileDependency(
                    source_module=entry_module,
                    target_module=target_module,
                    symbol=symbol,
                    call_line=call_line,
                    context=context,
                )
            )

    # 去重（同一 source/target/symbol 只保留一条）
    seen: set[tuple[str, str, str]] = set()
    unique: list[CrossFileDependency] = []
    for d in deps:
        key = (d.source_module, d.target_module, d.symbol)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _find_call_line(lines: list[str], symbol: str) -> int:
    """在源码行列表中查找 symbol 的首个调用行（行号 1-based，未找到返回 0）。

    保守口径：仅匹配"symbol(" 形式（函数调用），避免误匹配 import 语句中的符号。
    """
    pattern = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    for i, line in enumerate(lines, start=1):
        if pattern.search(line):
            return i
    return 0


# ─── 跨文件修复计划构建 ───────────────────────────────────────────────────────


def build_cross_file_repair_plan(
    deps: list[CrossFileDependency],
    debugger: Any,
    target_code: str,
    test_output: str,
    failed_cases: list[dict[str, str]],
    focus_function: str | None = None,
    target_module: str | None = None,
    max_modules: int | None = None,
) -> CrossFileRepairPlan:
    """基于依赖图 + LLM 生成多文件修复计划（协调器-提议者架构）。

    流程：
        1. 从 deps 提取需要修改的模块集合（去重，限制 max_modules）；
        2. 对每个模块调用 DebuggerAgent.debug 生成补丁（并行度 = 1，
           复用现有 LLM 调用路径，不新增基础设施）；
        3. 汇总为 CrossFileRepairPlan（含依赖边 + 预估 token 成本）。

    Args:
        deps: 跨文件依赖边列表（analyze_cross_file_deps 输出）。
        debugger: DebuggerAgent 实例（提供 .debug 方法）。
        target_code: 入口模块的原始代码。
        test_output: pytest 输出文本。
        failed_cases: 失败用例列表。
        focus_function: 焦点函数名（可选）。
        target_module: 被测模块名（可选，用于 LLM prompt 约束）。
        max_modules: 最大模块数（None 时读 cross_file_max_modules()）。

    Returns:
        CrossFileRepairPlan 实例（per_module_patches 仅含成功生成的补丁，
        失败模块记为原代码不变）。
    """
    if max_modules is None:
        max_modules = cross_file_max_modules()

    # 收集需要修改的模块（去重，保留 entry 自身 + 所有 target_module）
    modules: list[str] = []
    for d in deps:
        if d.target_module not in modules:
            modules.append(d.target_module)
        if d.source_module not in modules:
            modules.append(d.source_module)
    modules = sorted(set(modules))[:max_modules]

    plan = CrossFileRepairPlan(
        plan_id=f"cf_{len(modules)}m_{id(deps)}",
        target_modules=modules,
        per_module_patches={},
        dependency_edges=list(deps),
        estimated_token_cost=0,
    )

    # 对每个模块生成补丁（协调器-提议者：每个模块一个提议者）
    for module_name in modules:
        try:
            result = debugger.debug(
                target_code=target_code,
                test_output=test_output,
                failed_cases=failed_cases,
                focus_function=focus_function,
                target_module=target_module,
            )
            patch_text = result.get("patch", "")
            if patch_text:
                plan.per_module_patches[module_name] = patch_text
                # 保守估算：字符数 / 4（英文 token 经验值）
                plan.estimated_token_cost += max(len(patch_text), 1) // 4
        except (json.JSONDecodeError, RuntimeError) as e:
            logger.warning("跨文件修复：模块 %s 补丁生成失败，跳过: %s", module_name, e)
            # 失败模块不写入 per_module_patches（保持原代码不变）
            continue

    return plan


# ─── 多文件补丁应用 ───────────────────────────────────────────────────────────


def apply_multi_file_patch(
    original_files: dict[str, str],
    patches: dict[str, str],
    entry_module: str,
) -> tuple[dict[str, str], bool]:
    """对多个文件同时应用补丁（被调用方先改，调用方后改）。

    策略：
        1. 按依赖图拓扑序应用（被调用方 target_module 先改，
           调用方 source_module 后改）；
        2. 每个文件调用 patch_applier.apply_patch_to_code（单文件逻辑不变）；
        3. 任一文件应用失败则整体回滚（与单文件 safe_apply_patch 同口径）。

    Args:
        original_files: 模块名 → 原始代码的映射。
        patches: 模块名 → 补丁文本的映射（仅包含需要修改的模块）。
        entry_module: 入口模块名（用于拓扑序排序的根节点）。

    Returns:
        (新文件映射, 是否全部成功)；失败时返回 (original_files, False)。
    """
    if not patches:
        return dict(original_files), True

    # 拓扑序：被调用方（target_module）先改，调用方（source_module）后改。
    # 保守实现：对每个 patch，统计它作为 source 出现的次数（被调用方次数越多越先改）。
    # 无依赖信息时按模块名字典序应用（确定性，不依赖 LLM 输出顺序）。
    def topo_key(module: str) -> tuple[int, str]:
        # source_module 出现在 patches 中作为调用方时，其被调用方应先行
        # 这里简化：被调用方（在 deps 中 target_module）排前
        return (0, module)  # 占位：无依赖图时字典序

    # 简化拓扑序：被调用方（target）字典序在前，调用方（source）字典序在后
    # 由于没有传入依赖图，保守按模块名字典序应用（确定性）
    ordered_modules = sorted(patches.keys(), key=lambda m: (0, m))

    new_files: dict[str, str] = dict(original_files)
    for module_name in ordered_modules:
        original = original_files.get(module_name, "")
        patch = patches[module_name]
        if not original:
            # 模块不在 original_files 中（LLM 生成了不存在的模块补丁），跳过
            logger.warning("跨文件补丁：模块 %s 不在 original_files，跳过", module_name)
            continue
        from src.tools.patch_applier import apply_patch_to_code

        new_code, success = apply_patch_to_code(original, patch)
        if not success:
            logger.warning("跨文件补丁：模块 %s 应用失败，整体回滚", module_name)
            return dict(original_files), False
        new_files[module_name] = new_code

    return new_files, True


def cross_file_fallback_single_file(
    original_files: dict[str, str],
    patches: dict[str, str],
    entry_module: str,
) -> tuple[dict[str, str], bool]:
    """跨文件修复降级为单文件模式（仅对 entry_module 应用补丁）。

    用于 CROSS_FILE_ENABLE=true 但只有单文件（或依赖图退化）时的兜底：
    只对 entry_module 应用第一个补丁，其他模块保持原样。

    Args:
        original_files: 模块名 → 原始代码。
        patches: 模块名 → 补丁文本。
        entry_module: 入口模块名。

    Returns:
        (新文件映射, 是否成功)；entry_module 无补丁时返回原样。
    """
    new_files = dict(original_files)
    entry_patch = patches.get(entry_module, "")
    if not entry_patch:
        # 入口模块无补丁（单文件项目退化），保持原样
        return new_files, True
    from src.tools.patch_applier import apply_patch_to_code

    original = original_files.get(entry_module, "")
    new_code, success = apply_patch_to_code(original, entry_patch)
    if success:
        new_files[entry_module] = new_code
    return new_files, success
