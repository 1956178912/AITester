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
import hashlib
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


def cross_file_bidirectional() -> bool:
    """2.2 改进：双向依赖图开关（CROSS_FILE_BIDIRECTIONAL=true 时启用，默认 false）。

    启用后 analyze_cross_file_deps 额外收集"其他模块 → entry_module"的
    反向依赖边（被调用方视角），形成双向依赖图，跨文件修复时能同步更新
    调用方（双向拓扑序应用补丁：被调用方 entry 先改，调用方后改）。
    默认关闭保持历史"单入口视角"口径。
    """
    return os.getenv("CROSS_FILE_BIDIRECTIONAL", "false").lower() == "true"


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
    bidirectional: bool = False,
) -> list[CrossFileDependency]:
    """AST 分析入口模块与其他模块的依赖关系。

    流程：
        1. 解析 entry_module 的源码，提取 import 语句（from X import Y）；
        2. 对每个导入的 X，若 X 在 source_files 中（项目内模块），
           则记录一条依赖边（entry → X，symbol 为导入的名称）；
        3. 进一步扫描 entry 中调用 X.symbol 的函数体，记录调用行上下文；
        4. 返回所有依赖边（按 source_module 排序，去重）。

    2.2 改进（双向依赖图）：
        当 bidirectional=True 时，除了 entry → 被调用方（调用方视角）的边，
        还扫描 source_files 中其他模块 → entry（被调用方视角）的边：
        即哪些其他模块 import 了 entry_module 的符号。这样依赖图包含
        "谁调用了入口模块"，跨文件修复时能同步更新调用方（双向拓扑序
        应用补丁：被调用方 entry 先改，调用方后改）。

        保守口径：仅对 entry 直接相关的模块做双向分析（不递归展开
        其他模块的 import，避免依赖图爆炸）；entry 不在 source_files
        时双向分析退化为单向（仅 entry 的 import 边）。

    Args:
        entry_module: 入口模块名（不含 .py，如 "calculator"）。
        source_files: 模块名 → 源码字符串的映射（项目内所有相关模块）。
        bidirectional: 是否启用双向依赖分析（2.2 改进，默认 False 保持
            历史单入口视角口径；True 时额外收集"其他模块 → entry"的边）。

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

    # 收集 entry 中所有 import 的项目内模块名及其符号（from X import Y / import X）
    imported_symbols = _collect_imported_symbols(tree, source_files)

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

    # 2.2 改进：双向依赖分析——扫描其他模块 import entry_module 的符号
    # （"谁调用了入口模块"视角，跨文件修复时调用方需同步更新）
    if bidirectional:
        reverse_deps = _collect_reverse_deps(entry_module, source_files)
        deps.extend(reverse_deps)

    # 去重（同一 source/target/symbol 只保留一条）
    seen: set[tuple[str, str, str]] = set()
    unique: list[CrossFileDependency] = []
    for d in deps:
        key = (d.source_module, d.target_module, d.symbol)
        if key not in seen:
            seen.add(key)
            unique.append(d)
    return unique


def _collect_reverse_deps(
    entry_module: str,
    source_files: dict[str, str],
) -> list[CrossFileDependency]:
    """2.2 改进：收集"其他模块 → entry_module"的反向依赖边（被调用方视角）。

    扫描 source_files 中每个模块（排除 entry 自身）的 import 语句，
    若某模块导入了 entry_module 中的符号，则记录一条
    source_module=该模块, target_module=entry_module 的依赖边。
    用于跨文件修复时同步更新"调用方"（双向拓扑序应用补丁）。

    Args:
        entry_module: 入口模块名（不含 .py）。
        source_files: 模块名 → 源码字符串的映射。

    Returns:
        反向依赖边列表（source_module=其他模块, target_module=entry_module）；
        无反向依赖时返回空列表。
    """
    reverse: list[CrossFileDependency] = []
    for module_name, code in source_files.items():
        if module_name == entry_module:
            continue
        if not code:
            continue
        try:
            tree = ast.parse(code)
        except SyntaxError:
            continue
        # 收集该模块 import 的 entry_module 符号
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module_name_imported = node.module or ""
                if module_name_imported != entry_module:
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    # 找到 entry_module 源码中该符号的定义行（保守：行号 0 占位）
                    call_line = _find_symbol_def_line(entry_module, source_files, alias.name)
                    context = ""
                    if call_line > 0:
                        entry_lines = source_files.get(entry_module, "").splitlines()
                        lo = max(0, call_line - 2)
                        hi = min(len(entry_lines), call_line + 1)
                        context = "\n".join(entry_lines[lo:hi])
                    reverse.append(
                        CrossFileDependency(
                            source_module=module_name,
                            target_module=entry_module,
                            symbol=alias.name,
                            call_line=call_line,
                            context=context,
                        )
                    )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name != entry_module:
                        continue
                    # import entry_module（模块级导入）
                    reverse.append(
                        CrossFileDependency(
                            source_module=module_name,
                            target_module=entry_module,
                            symbol=entry_module,
                            call_line=0,
                            context="",
                        )
                    )
    return reverse


def _find_symbol_def_line(module_name: str, source_files: dict[str, str], symbol: str) -> int:
    """在模块源码中查找符号定义行（1-based，未找到返回 0）。

    保守口径：匹配 `def symbol(` / `class symbol:` / `symbol =` 三类定义形式。
    """
    code = source_files.get(module_name, "")
    if not code:
        return 0
    patterns = [
        re.compile(rf"^\s*def\s+{re.escape(symbol)}\s*\("),
        re.compile(rf"^\s*class\s+{re.escape(symbol)}\s*[:(:]"),
        re.compile(rf"^\s*{re.escape(symbol)}\s*="),
    ]
    for i, line in enumerate(code.splitlines(), start=1):
        for p in patterns:
            if p.search(line):
                return i
    return 0


def analyze_multi_entry_deps(
    entry_modules: list[str],
    source_files: dict[str, str],
    max_depth: int = 1,
) -> list[CrossFileDependency]:
    """多入口跨文件依赖分析（3.5 二期，设计文档 §6 "多入口分析" 缺口补全）。

    背景：
        一期 analyze_cross_file_deps 仅分析单一 entry_module 的"一级 import"
        （调用方视角 + 可选反向边）。真实项目中"修复需同步更新 N 个调用方"
        场景下，入口不止一个（如公共库 lib.py 被 A/B/C 三个模块 import），
        仅分析其中一个入口会漏掉其他入口的依赖边。

    实现（保守口径，防依赖图爆炸）：
        1. 对每个 entry_module 调用 analyze_cross_file_deps（bidirectional=False，
           保持一期"调用方视角"口径，反向边由 analyze_cross_file_deps 的
           bidirectional=True 单独承担，不在此处叠加）；
        2. 对 max_depth=1（默认）：仅展开各 entry 的一级 import（即 entry →
           直接依赖），不递归展开"依赖的依赖"（依赖图爆炸风险）；
        3. 合并所有 entry 的边并去重（同 (source, target, symbol) 只保留一条，
           保留 call_line 较小的那条——更接近"最早定义/调用点"，便于 LLM 定位）。

    Args:
        entry_modules: 入口模块名列表（不含 .py，如 ["lib", "main"]）。
        source_files: 模块名 → 源码字符串的映射。
        max_depth: 展开深度（默认 1 = 一级 import；2 = 依赖的依赖，未实现
            递归展开，传 >1 时保守退化为 1，避免依赖图爆炸）。

    Returns:
        去重合并后的跨文件依赖边列表；所有 entry 都不在 source_files 时返回空列表。
    """
    if max_depth > 1:
        # 保守口径：未实现递归展开，退化为一级（避免依赖图爆炸）
        logger.debug("多入口依赖分析：max_depth=%d 退化为 1（保守口径）", max_depth)
    all_deps: list[CrossFileDependency] = []
    for entry in entry_modules:
        all_deps.extend(analyze_cross_file_deps(entry, source_files, bidirectional=False))

    # 去重：同 (source, target, symbol) 保留 call_line 最小（最早定义/调用点）
    best: dict[tuple[str, str, str], CrossFileDependency] = {}
    for d in all_deps:
        key = (d.source_module, d.target_module, d.symbol)
        existing = best.get(key)
        if existing is None or d.call_line < existing.call_line:
            best[key] = d
    return sorted(best.values(), key=lambda x: (x.source_module, x.target_module, x.symbol))


def _collect_imported_symbols(tree: ast.AST, source_files: dict[str, str]) -> dict[str, list[str]]:
    """收集 entry 模块中 import 的项目内模块及其符号（模块名 → 符号名列表）。"""
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
    return imported_symbols


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

    # 收集需要修改的模块（去重，保留 entry 自身 + 所有 target_module；
    # 按字典序排序后截断 max_modules，保证 LLM 预算的消耗对象可预测）
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
    deps: list[CrossFileDependency] | None = None,
) -> tuple[dict[str, str], bool]:
    """对多个文件同时应用补丁。

    应用顺序（二期改进，设计文档 §6）：
        1. 传入 deps（跨文件依赖边列表）时：按依赖图拓扑序应用——
           被调用方（target_module）先改，调用方（source_module）后改。
           这样调用方引用的函数签名变更在调用方应用前已生效，
           避免"调用方先改"时引用到旧签名导致的中间态不一致。
        2. 未传 deps（None，保持 0.5 一期口径）：按模块名字典序应用
           （确定性、不依赖 LLM 输出顺序）。

    策略：
        - 每个文件调用 patch_applier.apply_patch_to_code（单文件逻辑不变）；
        - 任一文件应用失败则整体回滚（与单文件 safe_apply_patch 同口径）。

    Args:
        original_files: 模块名 → 原始代码的映射。
        patches: 模块名 → 补丁文本的映射（仅包含需要修改的模块）。
        entry_module: 入口模块名（拓扑序排序时用于确定"被调用方"优先级）。
        deps: 跨文件依赖边列表（可选；传入时按拓扑序应用，None 时退回字典序）。

    Returns:
        (新文件映射, 是否全部成功)；失败时返回 (original_files, False)。
    """
    if not patches:
        return dict(original_files), True

    # 二期：传依赖边时按拓扑序（被调用方先改）；None 时退回字典序（一期口径）
    ordered_modules = _topological_order(patches, deps, entry_module) if deps is not None else sorted(patches.keys())

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


def _topological_order(
    patches: dict[str, str],
    deps: list[CrossFileDependency],
    entry_module: str,
) -> list[str]:
    """按依赖图拓扑序排列补丁应用顺序（被调用方先改，调用方后改）。

    算法：
        1. 构建模块间依赖（边：source_module 引用 target_module，
           即 source 依赖 target，target 应先应用）；
        2. Kahn 拓扑排序：入度为 0 的模块（不依赖其他待改模块的
           被调用方）优先应用；
        3. 有环时按字典序打破（保守回退，不阻塞应用）；
        4. entry_module 永远最先应用（被调用方视角的根）。

    Args:
        patches: 模块名 → 补丁文本（仅这些模块参与排序）。
        deps: 跨文件依赖边列表。
        entry_module: 入口模块名。

    Returns:
        拓扑序排列的模块名列表（仅含 patches 中的模块）。
    """
    modules = set(patches.keys())
    # 入度：module 的入度 = 它引用了哪些其他待改模块（需等这些模块先改）。
    # 按"边"计数（同一对模块的 K 条并行依赖边计 K，释放时逐边 -1，
    # 统计口径对称——见下方队列循环注释）
    in_degree: dict[str, int] = {m: 0 for m in modules}
    for d in deps:
        if d.source_module in modules and d.target_module in modules and d.source_module != d.target_module:
            # source 引用 target → source 入度 +1（需等 target 先改）
            in_degree[d.source_module] += 1

    order: list[str] = []
    remaining = set(modules)
    # entry 强制首位（被调用方根）：不进入队列，直接先排
    if entry_module in modules:
        order.append(entry_module)
        remaining.discard(entry_module)
    # 入度 0 的模块按字典序入队；每轮弹出队首（字典序最小者）后，
    # 重新全量排序队列——确定性口径："入度 0 节点中字典序最小者优先"。
    # 注意：不能用 min-heap 替代（上一轮 0.7 优化误判语义等价）：
    # 入度按"边"计数（同一对模块的 K 条并行边计 K），释放时逐边 -1，
    # heap 按"去重后的调用方集合"释放一次仅 -1，并行边 >1 时入度
    # 永远无法归零，节点会被误判为环尾追加，整体顺序改变。
    queue = sorted(m for m in remaining if in_degree.get(m, 0) == 0)
    while queue:
        m = queue.pop(0)
        if m not in remaining:
            continue
        order.append(m)
        remaining.discard(m)
        # m 应用后，引用 m 的 caller 入度 -1（逐边扣减，与入度按边累加对称）
        for d in deps:
            if d.target_module == m and d.source_module in remaining:
                in_degree[d.source_module] -= 1
                if in_degree[d.source_module] == 0:
                    queue.append(d.source_module)
        queue.sort()
    # 剩余有环模块按字典序追加（保守回退）
    order.extend(sorted(remaining))
    return order


def _repair_plan_cache_key(
    entry_modules: list[str],
    deps: list[CrossFileDependency],
    max_modules: int,
) -> str:
    """修复计划缓存指纹（3.5 二期：相同依赖图复用 LLM 生成结果，省 token）。

    指纹 = entry_modules + 依赖边(source/target/symbol 集合) + max_modules 的
    SHA1 前 16 位。故意排除 LLM 输出（patch 文本），只按"输入依赖图"做 key——
    相同依赖图 → 相同修复计划（保守口径：修复计划由依赖图 + 代码上下文决定，
    依赖图不变则复用，避免重复 LLM 调用）。

    Args:
        entry_modules: 入口模块名列表。
        deps: 跨文件依赖边列表。
        max_modules: 最大模块数（影响计划裁剪，纳入指纹）。

    Returns:
        缓存 key 字符串（"cf_plan_" 前缀 + 16 位 hex，避免与 LLM 调用缓存
        （纯 hash 名）混存冲突）。
    """
    fingerprint = json.dumps(
        {
            "entries": sorted(set(entry_modules)),
            "edges": sorted({(d.source_module, d.target_module, d.symbol) for d in deps}),
            "max_modules": max_modules,
        },
        sort_keys=True,
    )
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
    return f"cf_plan_{digest}"


def _load_repair_plan_cache(key: str) -> CrossFileRepairPlan | None:
    """从缓存读取跨文件修复计划（命中返回 plan，未命中/损坏返回 None）。

    缓存文件落在 LLM 缓存目录（复用 AITESTER_LLM_CACHE_DIR 口径），
    缓存关闭（AITESTER_LLM_CACHE=0）时直接返回 None（不读盘）。
    """
    from src.agents.llm_client import _llm_cache_dir, _llm_cache_enabled

    if not _llm_cache_enabled():
        return None
    cache_file = os.path.join(_llm_cache_dir(), f"{key}.json")
    if not os.path.isfile(cache_file):
        return None
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        return CrossFileRepairPlan(
            plan_id=data.get("plan_id", key),
            target_modules=data.get("target_modules", []),
            per_module_patches=data.get("per_module_patches", {}),
            dependency_edges=[
                CrossFileDependency(
                    source_module=e.get("source_module", ""),
                    target_module=e.get("target_module", ""),
                    symbol=e.get("symbol", ""),
                    call_line=int(e.get("call_line", 0)),
                    context=e.get("context", ""),
                )
                for e in data.get("dependency_edges", [])
            ],
            estimated_token_cost=int(data.get("estimated_token_cost", 0)),
        )
    except (json.JSONDecodeError, OSError, TypeError, ValueError) as e:
        # 缓存损坏/不可读时保守降级为未命中（不影响修复流程）
        logger.debug("跨文件修复计划缓存读取失败 %s: %s", key, e)
        return None


def _save_repair_plan_cache(key: str, plan: CrossFileRepairPlan) -> None:
    """把跨文件修复计划写入缓存（失败仅 debug 日志，不影响主流程）。"""
    from src.agents.llm_client import _llm_cache_dir, _llm_cache_enabled

    if not _llm_cache_enabled():
        return
    try:
        cache_dir = _llm_cache_dir()
        os.makedirs(cache_dir, exist_ok=True)
        with open(os.path.join(cache_dir, f"{key}.json"), "w", encoding="utf-8") as f:
            json.dump(plan.to_dict(), f, ensure_ascii=False)
    except OSError as e:
        logger.debug("跨文件修复计划缓存写入失败 %s: %s", key, e)


def build_cross_file_repair_plan_cached(
    entry_modules: list[str],
    source_files: dict[str, str],
    debugger: Any,
    target_code: str,
    test_output: str,
    failed_cases: list[dict[str, str]],
    focus_function: str | None = None,
    target_module: str | None = None,
    max_modules: int | None = None,
    use_cache: bool = True,
) -> CrossFileRepairPlan:
    """带缓存的跨文件修复计划构建（3.5 二期：相同依赖图复用 LLM 结果，省 token）。

    流程：
        1. 调 analyze_multi_entry_deps 收集多入口依赖边（一级展开，保守口径）；
        2. 计算依赖图指纹（_repair_plan_cache_key）；
        3. use_cache=True 时先查缓存，命中直接返回（零 LLM 调用）；
        4. 未命中调 build_cross_file_repair_plan（协调器-提议者 LLM 生成），
           生成后写缓存（供后续相同依赖图复用）。

    兼容性：
        - use_cache=False 时行为等同直接调 build_cross_file_repair_plan
          （经 analyze_multi_entry_deps 收集多入口依赖），不读写缓存；
        - 缓存开关关闭（AITESTER_LLM_CACHE=0）时自动退化为不缓存。

    Args:
        entry_modules: 入口模块名列表（多入口分析，一期单入口传 [entry]）。
        source_files: 模块名 → 源码字符串的映射。
        debugger: DebuggerAgent 实例（提供 .debug 方法）。
        target_code: 入口模块的原始代码。
        test_output: pytest 输出文本。
        failed_cases: 失败用例列表。
        focus_function: 焦点函数名（可选）。
        target_module: 被测模块名（可选）。
        max_modules: 最大模块数（None 时读 cross_file_max_modules()）。
        use_cache: 是否启用缓存（默认 True；False 时行为等同 build_cross_file_repair_plan）。

    Returns:
        CrossFileRepairPlan 实例（命中缓存时 returned_from_cache=True 语义
        由调用方按需判断——本函数返回值与 build_cross_file_repair_plan 同构，
        缓存命中/未命中均返回同一结构）。
    """
    if max_modules is None:
        max_modules = cross_file_max_modules()
    deps = analyze_multi_entry_deps(entry_modules, source_files)

    key = _repair_plan_cache_key(entry_modules, deps, max_modules)
    if use_cache:
        cached = _load_repair_plan_cache(key)
        if cached is not None:
            logger.info("跨文件修复计划缓存命中 %s（节省 LLM 调用）", key)
            return cached

    plan = build_cross_file_repair_plan(
        deps=deps,
        debugger=debugger,
        target_code=target_code,
        test_output=test_output,
        failed_cases=failed_cases,
        focus_function=focus_function,
        target_module=target_module,
        max_modules=max_modules,
    )
    if use_cache:
        _save_repair_plan_cache(key, plan)
    return plan


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
