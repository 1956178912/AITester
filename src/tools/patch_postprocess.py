"""
LLM 输出后处理层（补丁卫生化 / sanitize 层）。

背景（1.1 改进）：
    SWE-bench 实测失败 5/7 LLM_BREAKS_IMPORT（LLM 重写破坏 sqlfluff 插件
    命名契约，Rule_L* 类名改坏 → 整个 import 链崩溃）+ 2/7 EMPTY_LLM_PATCH
    （LLM 未产出修复）。P0 1.3 的命名契约守卫是**拒绝层**（拒绝损坏补丁、
    交给 1.3 降级链重新生成）；本模块是**自动修复层**——在补丁应用前，
    自动检测并修复常见的 LLM 代码破坏模式，减少无效迭代。

自动修复的破坏模式（按保守程度分级）：
    P1 空壳补丁检测：补丁为纯空白/极短/无代码内容 → 标记为 EMPTY_LLM_PATCH
       （EMPTY_PATCH_GUARD，默认启用），调用方据此跳过应用并直接走重采样
       （不产生"应用成功但什么都没改"的幻象迭代）。
    P2 导入断裂修复：补丁（完整文件模式）删除了原代码的 import 语句，但
       原代码的存活符号仍在使用这些导入 → 自动把缺失的顶层 import 行
       重新插回补丁头部（IMPORT_REPAIR_ENABLE，默认关）。
    P3 契约符号回填：LLM 重命名/删除了模块级契约符号（Rule_L* 类名等）
       → 检测重命名嫌疑（同名前缀的存活新符号），保守场景下把原符号
       作为别名定义（`Old = New`）补回，保持 import 链不破（CONTRACT_ALIAS_ENABLE，
       默认关；与 1.3 契约守卫同口径——守卫仍为最终拒绝层）。

设计约束（与 patch_applier / safe_apply_patch 同口径）：
    - 零 LLM 依赖：纯静态 AST/正则分析，可测试、零 token 成本；
    - 保守降级：任何一步异常/不确定时返回原补丁（不引入损坏），由 1.3
      契约守卫与 2.2 重采样兜底；
    - 默认行为不变：三个开关中仅 P1 默认启用（P1 仅做"检测"不改代码，
      历史口径"空补丁不应用"本就是 safe_apply_patch 的既有行为，本层
      只是把它变成显式可观测的分类标签 + 调用方可据此快速跳轮）。
"""

from __future__ import annotations

import ast
import logging
import os
import re

logger = logging.getLogger(__name__)

# ─── 开关（环境变量，功能模块在调用期读取，与 multi_candidate/cross_file
# 模式一致，保留测试的 patch.dict(os.environ) 运行期切换能力）──────────────
# P1 空壳补丁检测（默认 true）：检测不修改，仅返回分类标签；调用方（
# _patch_applier_node）据此把 EMPTY_LLM_PATCH 标签写入 state，供
# refine_failure_category 识别与实验分析消费。
def _empty_patch_guard_enabled() -> bool:
    return os.getenv("EMPTY_PATCH_GUARD", "true").lower() != "false"

# P2 导入断裂修复（默认 false，保持历史行为）：补丁应用前自动把原代码的
# 顶层 import 行回填到补丁头部（仅当补丁是完整文件模式且丢失了原 import）。
def _import_repair_enabled() -> bool:
    return os.getenv("IMPORT_REPAIR_ENABLE", "false").lower() == "true"

# P3 契约符号别名回填（默认 false，保持历史行为）：检测 LLM 对模块级
# 契约符号的重命名（Old → New 嫌疑），在补丁中补 `Old = New` 别名定义。
def _contract_alias_enabled() -> bool:
    return os.getenv("CONTRACT_ALIAS_ENABLE", "false").lower() == "true"


# 空壳判定的最小代码字符数（去除 markdown/注释/空行后的有效代码）。
# 口径与 _patch_applier_node 安全检查 3（补丁过短拒绝，_MIN_PATCH_CHARS=40）
# 对齐但更严格：后处理层用 20——"def f(): pass"（14 字符）这类纯壳函数
# 也算空壳（无修复语义），40 字符以上的补丁才认为可能携带有效修复。
_EMPTY_PATCH_MIN_CHARS = 20

# 顶层 import 行探测（与 patch_applier._TOP_IMPORT_RE 同口径：行首 ^import /
# ^from，MULTILINE；排除函数体内缩进的局部 import）
_TOP_IMPORT_RE = re.compile(r"^(?:import |from )", re.MULTILINE)


def _effective_code_chars(text: str) -> int:
    """去除 markdown 包裹/注释/空行后的有效代码字符数（空壳判定口径）。"""
    if not text:
        return 0
    # 去 markdown 围栏（```python ... ```）——与 patch_applier 提取口径一致
    cleaned = re.sub(r"```(?:python)?\s*", "", text)
    lines: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            continue
        lines.append(stripped)
    return sum(len(x) for x in lines)


def detect_empty_patch(patch: str | None) -> bool:
    """P1 空壳补丁检测：补丁是否不构成有效修复（EMPTY_LLM_PATCH 标签）。

    判定（满足任一）：
    - 补丁为 None / 纯空白；
    - 去 markdown/注释/空行后有效代码 < _EMPTY_PATCH_MIN_CHARS；
    - 有效代码中不含任何 def/assert/raise/return/赋值等可改变行为的 token
      （纯注释/纯 import 重写也不算有效修复——但 import 重写可能修复
      导入错误，故 import 行计入有效代码）。

    纯检测不修改；开关 EMPTY_PATCH_GUARD=false 时恒返回 False（历史口径）。
    """
    if not _empty_patch_guard_enabled():
        return False
    if not patch or not patch.strip():
        return True
    return _effective_code_chars(patch) < _EMPTY_PATCH_MIN_CHARS


def _extract_top_level_imports(code: str) -> list[str]:
    """提取代码的顶层 import 行（AST 口径：import / from-import 语句原文）。

    原代码无法解析时返回空列表（保守：不做回填，交 1.3 守卫兜底）。
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return []
    lines = code.splitlines()
    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            # 多行 import（带括号）取首末行闭区间的原文
            start = node.lineno - 1
            end = getattr(node, "end_lineno", node.lineno) - 1
            imports.append("\n".join(lines[start : end + 1]))
    return imports


def repair_missing_imports(original_code: str, patch: str) -> str | None:
    """P2 导入断裂修复：把原代码中丢失的顶层 import 行回填到补丁头部。

    触发条件（全部满足才动手，否则返回 None 表示"无需修复"）：
    - 开关 IMPORT_REPAIR_ENABLE=true；
    - 补丁是完整文件形态（行首含 import/from，或 patch_applier 判定的
      多函数/diff 全文件形态由调用方保证——本函数只看行首 import）；
    - 原代码的顶层 import 集合中，至少一行在补丁中缺失（按行原文精确
      匹配，不误伤 LLM 有意改写的 import）；
    - 缺失的 import 行对应的模块名仍被原代码（除该 import 行外）引用
      （未使用的 import 不回填，避免把废弃依赖重新引入）。

    回填位置：补丁首部（首个非空代码行之前），保持 LLM 的其余输出不变。

    保守降级：原代码或补丁无法解析 → 返回 None（不修复）。
    """
    if not _import_repair_enabled():
        return None
    if not original_code or not patch or not patch.strip():
        return None
    orig_imports = _extract_top_level_imports(original_code)
    if not orig_imports:
        return None
    # 补丁需是"带顶层 import 意图"的形态才做回填（单函数片段不回填，
    # 其 import 依赖原文件头部，由 patch_applier 的单函数拼接语义保证）
    patch_has_top_import = bool(re.search(r"^(?:import |from )\S", patch, re.MULTILINE))
    if not patch_has_top_import:
        return None

    # 缺失判定：原 import 行的任一非空原文行在补丁全文中不存在
    missing = [imp for imp in orig_imports if imp not in patch]
    if not missing:
        return None
    # 引用存活判定：缺失 import 引入的模块名仍在原代码正文（去 import 行）
    # 中被使用——未使用则不回填（废弃 import 随 LLM 重写消失是合理行为）
    orig_body = "\n".join(x for x in original_code.splitlines() if not _TOP_IMPORT_RE.match(x))
    surviving = [
        imp for imp in missing if _import_module_names(imp) and any(n in orig_body for n in _import_module_names(imp))
    ]
    if not surviving:
        return None

    repaired = "\n".join(surviving) + "\n" + patch
    logger.info("P2 导入断裂修复：回填 %d 行缺失顶层 import（%s）", len(surviving), [s[:40] for s in surviving])
    return repaired


def _import_module_names(imp_line: str) -> list[str]:
    """提取 import/from-import 行引入的顶层模块名（用于引用存活判定）。

    `import a.b as c` → ["a", "c"]；`from x.y import m1, m2` → ["x.y", "m1", "m2"]。
    多行 import 取每行解析，解析失败返回空（该行不参与存活判定 = 保守不回填）。
    """
    try:
        mod = ast.parse(imp_line.strip())
    except (SyntaxError, ValueError):
        return []
    names: list[str] = []
    for node in mod.body:
        if isinstance(node, ast.Import):
            names.extend(a.asname or a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
            names.extend(a.asname or a.name for a in node.names if a.name != "*")
    return names


def repair_contract_aliases(original_code: str, patch: str) -> str | None:
    """P3 契约符号别名回填：LLM 重命名模块级契约符号时补 `Old = New` 别名。

    检测（保守启发式，宁可漏报不可误报）：
    - 原代码模块级符号 S（函数/类/常量）在补丁中缺失；
    - 补丁中存在"重命名嫌疑"新符号 N：N 与 S 共享前缀（如 Rule_L001 →
      RuleL001、rule_l001 → RuleL001），且 N 是补丁新增（原代码没有）；
      无嫌疑符号时退回"删除"口径：S 缺失且补丁中无 S 的任何变体 →
      无法自动回填（返回 None，交 1.3 契约守卫拒绝 + 降级链重生成）。

    回填位置：补丁尾部追加 `S = N  # alias restored by postprocess`，
    保持 import 链 / 插件注册不破。
    """
    if not _contract_alias_enabled():
        return None
    if not original_code or not patch or not patch.strip():
        return None
    try:
        orig_tree = ast.parse(original_code)
        patch_tree = ast.parse(patch)
    except (SyntaxError, ValueError):
        return None  # 补丁不可解析时不回填（避免叠加损坏）

    def _collect(tree: ast.Module, sink: set[str]) -> None:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                sink.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and not target.id.startswith("__"):
                        sink.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and not node.target.id.startswith(
                "__"
            ):
                sink.add(node.target.id)

    orig_symbols: set[str] = set()
    patch_symbols: set[str] = set()
    _collect(orig_tree, orig_symbols)
    _collect(patch_tree, patch_symbols)

    missing = sorted(orig_symbols - patch_symbols)
    if not missing:
        return None
    # 重命名嫌疑：缺失符号 S 与补丁新增符号 N 前缀相关（小写归一后
    # 共同前缀长度 >= 3，且 N 是新增）
    new_symbols = patch_symbols - orig_symbols
    def _common_prefix_len(a: str, b: str) -> int:
        n = 0
        for x, y in zip(a, b, strict=False):
            if x != y:
                break
            n += 1
        return n

    aliases: list[tuple[str, str]] = []
    for s in missing:
        s_norm = re.sub(r"[_\s]", "", s).lower()
        for n in sorted(new_symbols):
            n_norm = re.sub(r"[_\s]", "", n).lower()
            if s_norm and n_norm and _common_prefix_len(s_norm, n_norm) >= 3:
                aliases.append((s, n))
                break
    if not aliases:
        # 无重命名嫌疑（纯删除）：无法安全自动回填 → 交 1.3 守卫拒绝
        logger.debug("P3 契约符号缺失 %s 且无重命名嫌疑，交 1.3 守卫处理", missing)
        return None
    alias_lines = [f"{s} = {n}  # alias restored by patch postprocess (P3)" for s, n in aliases]
    repaired = patch.rstrip() + "\n" + "\n".join(alias_lines) + "\n"
    logger.info("P3 契约符号别名回填：%s", [f"{s} = {n}" for s, n in aliases])
    return repaired


def sanitize_patch(
    original_code: str,
    patch: str | None,
) -> tuple[str, list[str]]:
    """后处理层入口：按 P1→P2→P3 顺序处理 LLM 补丁。

    流程：
    1. P1 空壳检测：命中 → 原样返回（不修复），标签 ["empty_patch"]
       （调用方据此跳过应用并走重采样/失败分类）；
    2. P2 导入回填：开关启用且修复成功 → 用修复后文本继续；
    3. P3 契约别名回填：开关启用且修复成功 → 追加别名定义。

    任何步骤异常 → 保守返回原补丁（不引入半修复状态），标签记录已尝试
    的修复类型供观测。

    Args:
        original_code: 原始被测代码（P2/P3 的对比基准）。
        patch: LLM 生成的补丁文本（可能含 markdown 包裹）。

    Returns:
        (处理后补丁, 标签列表)。标签取值："empty_patch"（P1 命中）/
        "imports_repaired"（P2 生效）/ "contract_aliases_restored"（P3 生效）。
        空补丁（None/空白）且 P1 开关关闭时原样返回（历史口径）。
    """
    if patch is None:
        return "", ["empty_patch"] if _empty_patch_guard_enabled() else []
    labels: list[str] = []
    if detect_empty_patch(patch):
        labels.append("empty_patch")
        return patch, labels
    current = patch
    # P2 导入断裂回填（默认关）
    repaired_imports = repair_missing_imports(original_code, current)
    if repaired_imports is not None:
        current = repaired_imports
        labels.append("imports_repaired")
    # P3 契约符号别名回填（默认关）
    repaired_aliases = repair_contract_aliases(original_code, current)
    if repaired_aliases is not None:
        current = repaired_aliases
        labels.append("contract_aliases_restored")
    return current, labels


def postprocess_enabled_flags() -> dict[str, bool]:
    """当前三个后处理开关状态（供 get_workflow_stats / 观测层消费）。"""
    return {
        "empty_patch_guard": _empty_patch_guard_enabled(),
        "import_repair": _import_repair_enabled(),
        "contract_alias": _contract_alias_enabled(),
    }
