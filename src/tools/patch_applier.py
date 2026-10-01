"""
补丁应用工具模块：将 LLM 生成的修复代码应用到原始代码。

本模块支持两种补丁模式：
    1. 完整文件模式：当补丁包含 docstring/import/多函数定义时，直接替换整个文件
    2. 单函数模式：仅替换目标函数的函数体，保留其他函数不变

判断补丁类型的依据（按优先级）：
    - 补丁以 triple-quote 开头 → 完整文件模式（docstring 标志）
    - 前 200 字符含 import 语句 → 完整文件模式
    - 补丁含 >=2 个函数且原代码也含 >=2 个函数 → 完整文件模式
    - 否则 → 单函数模式（精确替换目标函数）

使用 ast 模块进行精确匹配，避免正则表达式在嵌套函数或同名函数场景下的误匹配问题。

P0 1.3 契约验证（命名契约检查）：
    补丁应用前对比修改前后模块级符号集合（函数/类/__all__/注册装饰器/
    插件入口点），缺失任何原符号则拒绝应用（防止 LLM 重写破坏 sqlfluff
    插件命名契约导致 import 链崩溃）。
"""

from __future__ import annotations

import ast
import difflib
import logging
import os
import re
import threading
from typing import Any

from src.utils.helpers import extract_code_block

logger = logging.getLogger(__name__)

# ─── 预编译正则（模块级单例，避免热路径重复编译）─────────────────────────────────
# 0.8 性能：全文扫描类函数（_is_full_file_patch / apply_patch_to_code 单函数
# 模式）原本每次调用现场 re.compile 4~6 遍，--parallel 多任务下累积可观。
# 全模式（无捕获组需求）提取为模块级常量；按函数名定制的边界定位正则仍按名
# 编译（数量少、re 内部 LRU 命中）。
_DEF_RE = re.compile(r"def\s+(\w+)\s*\(")
_TOP_DEF_RE = re.compile(r"^(?:async\s+)?def\s+\w+\s*\(", re.MULTILINE)
_TRIPLE_QUOTE_RE = re.compile(r'^"""')
_PYTHON_PREFIX_RE = re.compile(r"^python\s*\n?", re.IGNORECASE)
# 正则兜底路径的函数边界探测（_find_function_range 热循环内不再逐次编译）
_BOUNDARY_RE = re.compile(r"^(def |class |@|#)")
# 2026-09-26 round9 P1：顶层 import 探测（行首 ^import / ^from，与 _TOP_DEF_RE
# 同口径用 MULTILINE）。旧实现 `"import " in clean_patch[:200]` 用子串匹配，
# 函数体内局部 import（`def g(): import os`）落在前 200 字符内时被误判为
# 完整文件模式 → 原文件顶层 import 被静默丢弃（round9 P1 发现，已复现）。
_TOP_IMPORT_RE = re.compile(r"^(?:import |from )", re.MULTILINE)


def _extract_function_names(code: str) -> set[str]:
    """
    从代码中提取所有函数名称。

    Args:
        code: Python 代码字符串。

    Returns:
        函数名称集合。
    """
    return {m.group(1) for m in _DEF_RE.finditer(code)}


def _count_function_defs(code: str) -> int:
    """
    统计代码中的函数定义数量。

    0.8 口径：与拆分前一致，统计"行首 def"（`^def`，不匹配缩进的类方法/
    嵌套函数）数量；该函数被 multi_candidate 与测试直接导入，签名与语义不变。

    Args:
        code: Python 代码字符串。

    Returns:
        函数定义数量。
    """
    return len(_TOP_DEF_RE.findall(code))


def _is_full_file_patch(clean_patch: str, original_code: str) -> bool:
    """
    判断补丁是否为完整文件模式。

    完整文件模式的判断条件（满足任一即可）：
        (a) 补丁以 triple-quote 开头 → 含 docstring，通常是完整模块文件
        (b) 补丁**行首**含顶层 import 语句 → 含导入，说明是完整文件而非
            单函数补丁（2026-09-26 round9 P1 修复：旧实现用子串
            `"import " in clean_patch[:200]`，函数体内局部 import
            （`def g(): import os`）落在前 200 字符内时被误判为完整文件
            模式 → 原文件顶层 import 被静默丢弃，与 _TOP_DEF_RE 同口径
            用 MULTILINE 行首探测，排除函数体内局部 import 的误判路径）
        (c) 补丁含 >=2 个函数定义 且 原代码也含 >=2 个函数 → 多函数补丁

    Args:
        clean_patch: 清理后的补丁代码。
        original_code: 原始代码。

    Returns:
        True 表示使用完整文件模式，False 表示使用单函数模式。
    """
    has_docstring = bool(_TRIPLE_QUOTE_RE.match(clean_patch))
    # 2026-09-26 round9 P1：仅探测**行首**顶层 import（^import / ^from），
    # 函数体内缩进的局部 import（`    import os`）不命中行首锚定，
    # 不再误判单函数补丁为完整文件模式。
    has_import = bool(_TOP_IMPORT_RE.search(clean_patch[:200]))
    patch_func_count = _count_function_defs(clean_patch)
    original_func_count = _count_function_defs(original_code)

    return has_docstring or has_import or (patch_func_count >= 2 and original_func_count >= 2)


def _find_function_range_ast(original_code: str, func_name: str) -> tuple[int, int] | None:
    """
    用 AST 查找顶层函数在代码中的起止行范围（1-based 行号，ast 口径）。

    AST 精确定位比正则边界启发式更可靠：
    - 正则版（原 _find_function_range）把 `^#` 注释、`^@` 装饰器、类方法都当
      "边界"，遇到被装饰函数或含注释的函数体时过早截断，替换出残缺代码；
    - AST 直接读 ast.FunctionDef.lineno / end_lineno，嵌套定义/装饰器/注释
      都不干扰。

    Args:
        original_code: 原始代码全文。
        func_name: 目标函数名（顶层 def，含 async def；非嵌套）。

    Returns:
        (start_lineno, end_lineno) 1-based 闭区间（ast 行号）；
        未找到顶层同名函数或代码无法解析时返回 None（调用方回退正则路径）。
    """
    try:
        tree = ast.parse(original_code)
    except SyntaxError:
        return None
    for node in tree.body:
        # 2026-09-26 全面审查（P2 一致性）：含 ast.AsyncFunctionDef——
        # async def 在 AST 中是独立节点类型，仅遍历 ast.FunctionDef 漏检
        # async 目标函数（返回 None 走正则兜底路径，但正则不含 async
        # 前缀时 start_idx 恒 None，补丁应用失败）。与 _TOP_DEF_RE /
        # 下方正则定位口径一致。
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == func_name:
            # end_lineno 在 Python 3.8+ 恒有（普通 def 与 async def 均在
            # CPython 3.8+ 填充，已用真实 AST 核实；运行期 >=3.12 必然存在，
            # 下方 getattr 回退仅为 mypy 按 stub 的 Optional[int] 签名保留的
            # 空操作分支）
            end = getattr(node, "end_lineno", None) or node.lineno
            return node.lineno, end
    return None


def _find_function_range(lines: list[str], func_name: str, start_idx: int) -> tuple[int, int]:
    """
    查找函数在代码中的起止行范围（正则启发式，AST 不可用时的兜底）。

    0.8 口径：func_name 保留在签名中（历史调用方/tests 依赖 3 参形式），
    当前实现仅用于定位边界行，不参与逻辑（与拆分前行为一致）。

    Args:
        lines: 代码行列表。
        func_name: 函数名称（签名兼容保留，实现不使用）。
        start_idx: 函数起始行索引。

    Returns:
        (start_idx, end_idx) 元组，end_idx 为函数结束后的下一行索引。
    """
    end_idx = len(lines)  # 默认到文件末尾
    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        # 结束条件：遇到下一个顶层定义或非空无缩进行（复用模块级 _BOUNDARY_RE）
        if _BOUNDARY_RE.match(line) or (line.strip() and not line.startswith(" ") and not line.startswith("\t")):
            end_idx = i
            break

    return start_idx, end_idx


def apply_patch_to_code(
    original_code: str,
    patch: str,
) -> tuple[str, bool]:
    """
    将补丁代码应用到原始代码。

    核心判断逻辑：
        1. 从补丁文本中提取纯代码（去除 markdown 包裹）
        2. 判断补丁类型（完整文件 vs 单函数）
        3. 完整文件：验证补丁包含原代码所有函数后整体替换
        4. 单函数：定位目标函数在原代码中的行范围并精确替换

    Args:
        original_code: 原始被测代码（待修复的代码）。
        patch:         LLM 生成的修复代码（可能含 ```python 标记或 python: 前缀）。

    Returns:
        Tuple[str, bool]: (修复后的代码, 是否成功应用)
            - 成功时返回 (新代码, True)
            - 失败时返回 (原代码, False)
    """
    # Step 1: 从补丁文本中提取纯代码（去除 markdown 包裹和前缀）
    clean_patch = extract_code_block(patch)
    # 补丁为空时无法应用，直接返回原代码
    if not clean_patch:
        return original_code, False

    # Step 2: 移除可能的 "python" 前缀（LLM 有时输出不带反引号的格式）
    clean_patch = _PYTHON_PREFIX_RE.sub("", clean_patch, count=1)

    # Step 3: 检测补丁类型（完整文件模式 or 单函数模式）
    if _is_full_file_patch(clean_patch, original_code):
        # Step 4a: 完整文件模式 —— 验证并替换
        patch_func_names = _extract_function_names(clean_patch)
        orig_func_names = _extract_function_names(original_code)

        # 验证补丁包含原代码的全部函数（防止部分替换导致函数丢失）。
        # 注意：orig_func_names 为空集（原代码无顶层函数）时 subset 恒成立
        # （∅ ⊆ 任意集合），全文件替换合法——"无函数可丢"；
        # 不得用 `orig_func_names and ...` 做前置守卫——原 `and` 短路把空集
        # 场景错落到下方 Step 4b，而 Step 4b 因补丁无 def 也返回 False，
        # 导致全文件替换永远落不到（2026-09-26 round8 tools 审查 P1 修复：
        # 改为显式 `not orig_func_names or ...`，不改变非空集路径的判定口径）。
        if not orig_func_names or orig_func_names.issubset(patch_func_names):
            # 追加换行符确保代码以换行结尾（PEP 8 风格）
            return clean_patch + "\n", True

        # 2026-09-26 全面审查（P1 正确性）：完整文件模式 subset 校验失败
        # （补丁有 import/docstring 前缀但漏掉原代码某函数）——保守拒绝返回
        # 原代码，不再静默回退 Step 4b 单函数路径。此前静默回退把整个
        # "看似完整文件"补丁塞进首个函数的行范围切片（new_lines = 头 + 补丁
        # 全量 + 尾），当补丁前缀（import）与原代码前缀重叠时产出含重复
        # import、重复函数定义的损坏代码——ast.parse 通过、safe_apply_patch
        # 语法守卫不拦、multi_candidate 安全检查 4（函数定义数量不减少）反因
        # 重复定义"通过"，损坏代码直接写盘（sqlfluff 5/7 失败那类"删/漏
        # 函数"场景最危险的静默损坏路径）。
        # 与 multi_candidate 防御网设计（检查 4：函数定义数量不减少）同口径
        # 保守拒绝（宁拒绝不可损坏）。
        # 注：orig_func_names 非空但 subset 校验失败才走到此处（orig_func_names
        # 为空集时上方 L212 已提前返回成功，"无函数可丢"，本拒绝分支不可达）。
        # 补丁只含新函数（不含原函数）时 subset 校验也已在 L212 通过并返回
        # （新增函数不构成"误删"，历史口径保留；Step 4b 仅处理"非全文件
        # 模式"的补丁——有 def 的补丁若被判为全文件模式且 subset 通过，
        # 不会落到 Step 4b）。
        logger.warning("完整文件补丁漏掉原代码函数 %s，保守拒绝应用", sorted(orig_func_names - patch_func_names))
        return original_code, False

    # Step 4b: 单函数模式 —— 精确替换目标函数
    # 查找补丁中的第一个函数定义（复用模块级 _DEF_RE，避免热路径重复编译）
    func_match = _DEF_RE.search(clean_patch)
    if not func_match:
        # 补丁中无函数定义，无法应用
        return original_code, False

    patch_func_name = func_match.group(1)

    # AST 优先定位目标函数行范围；AST 不可用时（原代码无法解析）
    # 回退正则启发式（历史行为，保守）。
    # ast.FunctionDef.lineno 指向 `def` 行（不含装饰器），与正则路径
    # 定位口径一致；end_lineno 为函数体末行（1-based 闭区间）。
    # 统一转 0-based 切片索引：start_idx = lineno - 1（`def` 行）；
    # end_idx = end_lineno（末行下一行），替换 lines[:start] + lines[end:]
    # 恰好替换"def 行到函数体末行"，保留装饰器（与正则路径同口径）。
    # 将原代码按行分割（一次切分，AST 定位与正则兜底两条路径共用，
    # 消除原"两条分支各 split 一遍"的重复开销）
    lines = original_code.split("\n")
    ast_range = _find_function_range_ast(original_code, patch_func_name)
    if ast_range is not None:
        start_idx = ast_range[0] - 1  # 0-based `def` 行
        end_idx = ast_range[1]  # 0-based 末行下一行
    else:
        start_idx = None

        # 遍历原代码行，定位目标函数的起始行
        # 按名编译的边界定位正则（数量少；re 内部 LRU 命中后零编译开销）。
        # 2026-09-26 全面审查（P2 一致性）：含 async def 前缀——async def
        # 在 AST 中是独立节点类型（ast.AsyncFunctionDef），_find_function_range_ast
        # 仅遍历 ast.FunctionDef 漏检 async 目标函数（返回 None 走本正则兜底路径），
        # 正则不匹配 async def 前缀时 start_idx 恒 None，补丁应用失败（单函数
        # 模式 async 函数永远落不到）。本处同步修复，与 _TOP_DEF_RE 口径一致。
        func_def_re = re.compile(rf"^(?:async\s+)?def\s+{re.escape(patch_func_name)}\s*\(")
        for i, line in enumerate(lines):
            if func_def_re.match(line):
                start_idx = i
                break

        # 未找到目标函数，返回原代码
        if start_idx is None:
            return original_code, False

        # 查找函数结束位置（正则兜底路径）
        _, end_idx = _find_function_range(lines, patch_func_name, start_idx)

    # Step 5: 执行替换 — 将原函数行范围替换为补丁函数代码
    patch_lines = clean_patch.split("\n")
    # 拼接新代码：原代码[起始前] + 空行 + 补丁行 + 空行 + 原代码[结束后的]
    new_lines = [*lines[:start_idx], "", *patch_lines, "", *lines[end_idx:]]

    # Step 6: 压缩连续空行，保持代码整洁（PEP 8 要求空行不超过 2 个）
    collapsed = _collapse_blank_lines(new_lines)

    # 拼接为完整代码字符串，末尾加换行符
    new_code = "\n".join(collapsed).strip() + "\n"
    return new_code, True


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    """
    压缩连续空行，最多保留一个空行。

    Args:
        lines: 代码行列表。

    Returns:
        压缩后的行列表。
    """
    collapsed = []
    prev_blank = False

    for line in lines:
        is_blank = line.strip() == ""
        # 跳过连续空行（保留一个空行作为间隔）
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank

    return collapsed


def apply_multi_function_patch(
    code: str,
    patches: list[dict],
) -> tuple[str, bool]:
    """
    应用多个函数的修改（支持递归函数和多函数同时修改）。

    该函数接收一个补丁列表，每个补丁包含：
    - function_name: 目标函数名
    - patch: LLM 生成的修复代码

    算法：
        1. 定位各补丁目标函数的起始行号（预切分行一次，P13 O(n+m)）
        2. 排序：找到的按行序升序（稳定，输入序 tie-break）；未找到的排末尾
        3. 逐个应用（apply_patch_to_code 基于当前代码重新定位，行序无关）
        4. 任一失败时 all_success=False，后续继续尝试（不中断），返回当前代码

    Args:
        code: 原始代码
        patches: 补丁列表，每项为 {"function_name": str, "patch": str}

    Returns:
        Tuple[str, bool]: (修复后的代码, 是否全部成功)
            - 所有补丁成功时返回 (新代码, True)
            - 任一补丁失败时返回 (当前代码, False)
    """
    if not patches:
        return code, True

    # P13：预切分代码行一次，排序 key 复用（避免每个 patch 都重新 split）
    code_lines = code.split("\n")

    # 0.9 修正：此前排序为 _find_function_start_line_in_lines 行序 reverse=True，
    # 未找到的函数映射为 -1 反而排最前（0-based 最大），与"应用失败回滚"语义
    # 无关（apply_patch_to_code 逐补丁基于当前代码独立定位，行序假设不成立）。
    # 现改为"未找到的排末尾"：(found, line) 升序稳定，找到补丁按行序应用，
    # 未找到的最后尝试（必失败 → all_success=False，与历史"失败不中断"口径一致）
    def _sort_key(p: dict) -> tuple[int, int]:
        line = _find_function_start_line_in_lines(code_lines, p["function_name"])
        return (0, line) if line >= 0 else (1, 0)

    sorted_patches = sorted(patches, key=_sort_key)

    current_code = code
    all_success = True

    for patch_info in sorted_patches:
        patch = patch_info["patch"]

        new_code, success = apply_patch_to_code(current_code, patch)
        if not success:
            all_success = False
            # 继续尝试其他补丁，不中断
            continue
        current_code = new_code

    return current_code, all_success


def _find_function_start_line_in_lines(code_lines: list[str], func_name: str) -> int:
    """按预切分的行查找函数起始行号（P13 性能优化：供批量排序 key 复用，避免每个
    patch 都重新 split 一遍代码）。

    2026-09-26 round9 P2：正则补 async 前缀（与 L270 单函数模式正则兜底
    同口径，_TOP_DEF_RE 含 async 可选前缀），async 目标函数不再误判为
    "未找到"排到末尾。

    Args:
        code_lines: 代码行列表（code.split("\\n") 的结果）。
        func_name: 函数名。

    Returns:
        函数起始行号（从0开始），未找到返回 -1。
    """
    # 预编译函数定义匹配正则（避免逐行重复编译）
    # 2026-09-26 round9 P2：含 async 前缀（与 _TOP_DEF_RE 同口径）
    func_def_re = re.compile(rf"^(?:async\s+)?def\s+{re.escape(func_name)}\s*\(")
    for i, line in enumerate(code_lines):
        if func_def_re.match(line):
            return i
    return -1


def safe_apply_patch(
    code: str,
    patch: str,
) -> tuple[str, bool]:
    """
    安全应用 patch，失败时自动回滚。

    该函数在应用补丁后会验证生成的代码语法是否正确。
    如果语法错误，自动回滚到原始代码。
    S2 安全（2026-09-29）：另做危险 API 守卫差集检查——补丁新引入
    os.system / subprocess / eval / 网络外连 / 凭证读取时拒绝应用
    （与语法失败 / 命名契约破坏同口径，回滚原代码；开关
    PATCH_DANGEROUS_API_GUARD，默认 true）。

    Args:
        code: 原始代码
        patch: LLM 生成的补丁代码

    Returns:
        Tuple[str, bool]: (应用后的代码, 是否成功)
    """
    # 尝试应用补丁
    new_code, success = apply_patch_to_code(code, patch)
    if not success:
        return code, False

    # 验证生成的代码语法是否正确
    try:
        ast.parse(new_code)
    except SyntaxError:
        # 语法错误，回滚到原始代码
        return code, False

    # S2 安全（2026-09-29）：危险 API 守卫差集检查——补丁新引入
    # os.system / subprocess / eval / exec / 网络外连 / 凭证读取时
    # 拒绝应用（与语法失败同口径回滚原代码，不引入半应用状态）。
    # 开关 PATCH_DANGEROUS_API_GUARD 默认 true；原代码已有的危险调用
    # 不在差集内，不拦截（避免误伤既有依赖 subprocess 的代码修复）。
    if _dangerous_api_guard_enabled():
        added = dangerous_api_added(code, new_code)
        if added:
            logger.warning(
                "S2 危险 API 守卫：补丁新引入危险操作 %s，拒绝应用并回滚",
                added,
            )
            return code, False
    return new_code, True


# ─── S2 安全：补丁危险 API 守卫（AST 级，默认启用）────────────────────────────
# 背景（2026-09-29 安全审查 S2）：LLM 生成补丁可能夹带危险操作（os.system /
# subprocess / eval / exec / 网络外连 requests.post / 凭证文件读取 open('.env')
# 等）。历史防御仅靠 injection_guard.check_llm_patch_safety（正则、默认关、
# 且全仓无接线——孤儿函数）+ 默认关的 deterministic_guard。现补 AST 级
# 静态守卫作为 safe_apply_patch 的默认前置闸门（与 PATCH_CONTRACT_CHECK
# 命名契约检查同模式：默认启用、环境变量可关、纯 AST 零 LLM 成本）：
# - 检查应用后的**完整代码**（而非补丁文本）中是否新增危险调用；
# - 与"原始代码已有的危险调用"做差集——只拦截**补丁新引入**的
#   （原代码本就含 subprocess 的修复不拦截，避免误伤；与命名契约
#   "只拦删除、放行新增"对偶，本守卫"只拦新增危险、放行既有"）；
# - 命中时拒绝应用（safe_apply_patch 返回原代码 + False + 拒绝原因），
#   与语法失败 / 契约破坏同口径（保守不引入半应用状态）。
# 危险调用特征（模块限定名 AST 口径，与 deterministic_guard 的
# _EXTERNAL_MODULE_CALLS 同集合 + shell/eval/凭证读取扩展）：
#   shell:    os.system / os.popen / subprocess.run|call|Popen|check_output
#   eval:     eval / exec（任意代码求值）
#   network:  requests.post|put|delete / urllib.request.urlopen|Request /
#             httpx.post|put / socket.socket
#   cred:     open('.env' / '/etc/passwd' / 'credentials*')（凭证读取）
# 开关：PATCH_DANGEROUS_API_GUARD 环境变量（默认 true；设 false 时守卫
# 恒放行——历史对照 / 合成集无危险 API 场景，与 PATCH_CONTRACT_CHECK 同模式）。
_DANGEROUS_CALL_TARGETS: frozenset[str] = frozenset(
    {
        "os.system",
        "os.popen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.Popen",
        "subprocess.check_output",
        "eval",
        "exec",
        "requests.post",
        "requests.put",
        "requests.delete",
        "urllib.request.urlopen",
        "urllib.request.Request",
        "httpx.post",
        "httpx.put",
        "socket.socket",
    }
)
# 凭证文件读取特征（open 调用第一实参字符串字面量命中即拦截）
_DANGEROUS_OPEN_PATHS: frozenset[str] = frozenset(
    {
        ".env",
        ".env.local",
        "/etc/passwd",
        "credentials.txt",
        "credentials.json",
        "credentials.yml",
        "~/.ssh/id_rsa",
    }
)


def _qualify_call_node(func_node: ast.AST) -> str | None:
    """把调用节点的 func 展开为模块限定名（与 deterministic_guard
    ._qualified_attr 同口径：Attribute 链展开 + 已知模块别名 np→numpy）。

    返回形如 "subprocess.run" / "eval"（裸 Name）；无法展开（复杂表达式）
    返回 None（不拦截——保守：只有明确的危险调用才拒绝，避免误伤）。
    """
    parts: list[str] = []
    cur: ast.AST = func_node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        alias = cur.id
        if alias == "np":
            alias = "numpy"
        parts.append(alias)
        return ".".join(reversed(parts))
    return None


def _collect_dangerous_calls_core(code: str) -> set[str]:
    """收集代码中命中的危险调用特征集合（AST 级，纯标准库）。

    收集两类：
    - 模块限定调用（_DANGEROUS_CALL_TARGETS 命中）→ 记限定名；
    - 凭证文件 open 读取（open 第一实参字符串字面量命中 _DANGEROUS_OPEN_PATHS）
      → 记 "open('<path>')"。
    语法不合法时返回空集（不拦截——语法失败由 safe_apply_patch 的
    ast.parse 校验先行拦截，本守卫只做危险调用差集，职责单一）。
    """
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        qual = _qualify_call_node(node.func)
        if qual and qual in _DANGEROUS_CALL_TARGETS:
            found.add(qual)
        # 凭证文件读取：open(<str literal>) 命中特征路径
        if qual == "open" and node.args:
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                # 归一：展开 ~ 前缀（保守精确匹配，不做通配）
                val = first.value
                if val in _DANGEROUS_OPEN_PATHS or val.replace("~/", ".") in _DANGEROUS_OPEN_PATHS:
                    found.add(f"open({val!r})")
    return found


def _collect_dangerous_calls(code: str) -> set[str]:
    """收集代码中命中的危险调用特征集合（AST 级，语法失败返回空集）。

    含三层检测：
    - _collect_dangerous_calls_core：静态模块限定调用 + 凭证读取；
    - _collect_dynamic_import_bypass：__import__/getattr 动态获取绕过
      （2026-10-01 全面审查 P2 修复——此前 __import__("os").system /
      getattr(os_module, "system") 绕过 AST 守卫，现补充动态模式检测）；
    - O19（2026-09-29 审查 P0）：_collect_dynamic_bypass_constructions
      补齐 5 类可平凡混淆绕过的动态构造（getattr / importlib.import_module
      / ctypes / shutil.rmtree / __import__ 完整形态）。
    """
    found = _collect_dangerous_calls_core(code)
    found |= _collect_dynamic_import_bypass(code)
    found |= _collect_dynamic_bypass_constructions(code)
    return found


# O19（2026-09-29 审查 P0）：危险调用目标 —— 在 5.4 S2 安全守卫基础上
# 补齐 5 类可平凡混淆绕过的形态（getattr 构造调用 / importlib.import_module
# 动态导入 / ctypes 任意二进制加载 / shutil 文件破坏 / __import__ 完整形态）。
# 此前 _collect_dynamic_import_bypass 仅拦截"别名 os.system"类静态模式，
# getattr(os_module, "system")、importlib.import_module("subprocess").run(...)
# 等动态构造调用可绕过守卫，补丁内仍可注入任意 shell/网络/凭证读取。
# 现把 5 类构造形态纳入 _collect_dangerous_calls 的差集口径：
# 原代码已有的动态导入不拦截，补丁**新增**的动态导入即拦截。
# 2026-09-30 审查订正：shutil 检测的是 **shutil.<attr> 属性访问调用**
# （_collect_dynamic_bypass_constructions 匹配 shutil.rmtree / copy2 / move /
# unlink 四个属性），裸 `import shutil` 本身并不构成调用特征——集合项以
# 可检测形态命名。
_DYNAMIC_IMPORT_CONSTRUCT: frozenset[str] = frozenset(
    {
        "getattr",  # getattr(os_module, "system") / getattr(subprocess_mod, "run")
        "importlib",  # importlib.import_module("os") / importlib.import_module("subprocess")
        "ctypes",  # ctypes.CDLL / ctypes.create_string_buffer 任意二进制加载
        "shutil",  # shutil.rmtree / shutil.copy2 / shutil.move 文件破坏与覆盖
        "__import__",  # __import__("os").system 模式（已部分覆盖，此处完整纳入）
    }
)


def _collect_dynamic_bypass_constructions(code: str) -> set[str]:
    """O19（2026-09-29 审查 P0）：AST 级动态构造导入/反射调用检测。

    对 code 做单遍 AST 扫描，检测 5 类可平凡混淆绕过 5.4 S2 静态守卫
    的构造形态（getattr / importlib.import_module / ctypes / shutil.rmtree /
    __import__），返回命中特征列表（与 _collect_dangerous_calls 的差集
    口径结合：仅"补丁新增"的构造才拦截，原代码已有的构造放行——与
    命名契约"放行既有"对偶口径）。

    与 injection_guard._RE_DYNAMIC_BYPASS 的口径对齐但更严格：
    正则版匹配文本，AST 版识别真实调用节点（避免"getattr 出现在注释/
    字符串"的误报）。
    """
    import ast as _ast

    found: set[str] = set()
    try:
        tree = _ast.parse(code)
    except Exception:
        return found
    # 第一遍：收集所有"可能是动态构造"的调用节点
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Call):
            continue
        # getattr(X, "system" / "run" / "Popen" / ...)
        if isinstance(node.func, _ast.Name) and node.func.id == "getattr" and len(node.args) >= 2:
            _attr_arg = node.args[1]
            if isinstance(_attr_arg, _ast.Constant) and isinstance(_attr_arg.value, str):
                # 5.4 S2 扩展：getattr 目标属性命中危险 API 集即拦截
                # （与 _DANGEROUS_CALL_TARGETS 末段属性名匹配）
                _dangerous_attrs = {
                    "system",
                    "popen",
                    "run",
                    "call",
                    "Popen",
                    "check_output",
                    "socket",
                    "urlopen",
                    "post",
                    "put",
                    "delete",
                    "CDLL",
                    "create_string_buffer",
                    "windll",
                    "oledll",
                }
                # P1-2（2026-10-02 审查）：getattr 第一参数须为已知危险模块
                # （Name 或别名）才拦截——与 _collect_dynamic_import_bypass
                # L784 的"危险模块限定"同口径，避免 getattr(obj, "run")
                # 这类高频普通属性访问被误报（"run" 是合法属性名）。
                _base_arg = node.args[0]
                _dangerous_mod_names = {"os", "subprocess", "socket", "urllib", "ctypes", "shutil", "shlex", "pty"}
                _base_id: str | None = None
                if isinstance(_base_arg, _ast.Name):
                    _base_id = _base_arg.id
                elif isinstance(_base_arg, _ast.Attribute):
                    _base_id = _base_arg.attr
                if _base_id in _dangerous_mod_names:
                    found.add(f"getattr({_base_id!r}, {_attr_arg.value!r})")
                elif _attr_arg.value in _dangerous_attrs:
                    # 未知基对象但属性名命中危险集 → 保守拦截（防 getattr(
                    # 任意对象, "system") 漏网；与上方 L784 的别名兜底同口径）
                    found.add(f"getattr(…, {_attr_arg.value!r})")
        # importlib.import_module("os" / "subprocess" / ...)
        if (
            isinstance(node.func, _ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, _ast.Name)
            and node.func.value.id == "importlib"
            and node.args
            and isinstance(node.args[0], _ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            _mod_name = node.args[0].value.split(".")[0]
            _dangerous_mod_names = {"os", "subprocess", "socket", "urllib", "ctypes", "shutil"}
            if _mod_name in _dangerous_mod_names:
                found.add(f"importlib.import_module({_mod_name!r})")
        # ctypes.CDLL / ctypes.create_string_buffer / ctypes.memmove
        if (
            isinstance(node.func, _ast.Attribute)
            and isinstance(node.func.value, _ast.Name)
            and node.func.value.id == "ctypes"
            and node.func.attr in ("CDLL", "create_string_buffer", "memmove", "windll", "oledll")
        ):
            found.add(f"ctypes.{node.func.attr}")
        # shutil.rmtree / shutil.copy2（文件破坏/覆盖）
        if (
            isinstance(node.func, _ast.Attribute)
            and isinstance(node.func.value, _ast.Name)
            and node.func.value.id == "shutil"
            and node.func.attr in ("rmtree", "copy2", "move", "unlink")
        ):
            found.add(f"shutil.{node.func.attr}")
        # __import__("os") / __import__("subprocess")
        if (
            isinstance(node.func, _ast.Name)
            and node.func.id == "__import__"
            and node.args
            and isinstance(node.args[0], _ast.Constant)
            and isinstance(node.args[0].value, str)
            and node.args[0].value.split(".")[0] in {"os", "subprocess", "socket", "urllib", "ctypes", "shutil"}
        ):
            found.add(f"__import__({node.args[0].value!r})")
    return found


def _collect_dynamic_import_bypass(code: str) -> set[str]:
    """检测 __import__/getattr 动态获取危险模块/函数的绕过模式（P2）。

    2026-10-01 全面审查 P2 修复：__import__("os").system(...) /
    getattr(importlib.import_module("os"), "system") 等动态获取模式
    绕过 _qualify_call_node 的静态展开（Name 链无法穿透 __import__ 调用），
    导致 AST 守卫漏检。现补充模式：
      - 函数体出现 __import__("os") 或 importlib.import_module("os") 且
        后跟 .system/.popen 属性访问
      - getattr(<module>, "system"/"popen"/...) 调用

    保守口径：仅在明确命中已知危险模块名（os/subprocess/socket/urllib）
    时报告，避免误伤 getattr 的常规用途。
    """
    import ast as _ast

    try:
        tree = _ast.parse(code)
    except (SyntaxError, ValueError):
        return set()
    found: set[str] = set()
    dangerous_mod_names = {"os", "subprocess", "socket", "urllib"}
    dangerous_attrs = {"system", "popen", "run", "call", "Popen", "check_output", "socket"}
    # 预扫描：哪些 Name 被赋值为危险模块引用（__import__("os") /
    # importlib.import_module("os") / 裸 import os），供别名模式匹配
    dangerous_mod_aliases: set[str] = set()
    for node in _ast.walk(tree):
        if isinstance(node, _ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], _ast.Name):
            alias_name = node.targets[0].id
            val = node.value
            if (
                isinstance(val, _ast.Call)
                and isinstance(val.func, _ast.Name)
                and val.func.id == "__import__"
                and val.args
                and isinstance(val.args[0], _ast.Constant)
                and isinstance(val.args[0].value, str)
                and val.args[0].value.split(".")[0] in dangerous_mod_names
            ):
                dangerous_mod_aliases.add(alias_name)
            if (
                isinstance(val, _ast.Call)
                and isinstance(val.func, _ast.Attribute)
                and val.func.attr == "import_module"
                and isinstance(val.func.value, _ast.Name)
                and val.func.value.id == "importlib"
                and val.args
                and isinstance(val.args[0], _ast.Constant)
                and isinstance(val.args[0].value, str)
                and val.args[0].value.split(".")[0] in dangerous_mod_names
            ):
                dangerous_mod_aliases.add(alias_name)
        if isinstance(node, _ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if top in dangerous_mod_names:
                    dangerous_mod_aliases.add(alias.asname or alias.name)
    for node in _ast.walk(tree):
        # __import__("os").system 模式：Attribute(value=Call(func=Name('__import__')))
        if (
            isinstance(node, _ast.Attribute)
            and isinstance(node.value, _ast.Call)
            and isinstance(node.value.func, _ast.Name)
            and node.value.func.id == "__import__"
            and node.value.args
            and isinstance(node.value.args[0], _ast.Constant)
            and isinstance(node.value.args[0].value, str)
            and node.value.args[0].value.split(".")[0] in dangerous_mod_names
            and node.attr in dangerous_attrs
        ):
            found.add(f"__import__({node.value.args[0].value!r}).{node.attr}")
        # 别名引用：m.system / m.run（m 是 __import__/import_module/裸 import 的别名）
        if (
            isinstance(node, _ast.Attribute)
            and isinstance(node.value, _ast.Name)
            and node.value.id in dangerous_mod_aliases
            and node.attr in dangerous_attrs
        ):
            found.add(f"{node.value.id}.{node.attr}")
        # getattr(module, "system") 模式
        if (
            isinstance(node, _ast.Call)
            and isinstance(node.func, _ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], _ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value in dangerous_attrs
        ):
            # 第一参数是已知危险模块 Name 引用或已赋值为危险模块的别名
            base = node.args[0]
            if isinstance(base, _ast.Name) and base.id in (dangerous_mod_names | dangerous_mod_aliases):
                found.add(f"getattr({base.id}, {node.args[1].value!r})")
    return found


def dangerous_api_added(original_code: str, patched_code: str) -> list[str]:
    """S2 安全守卫：返回补丁**新引入**的危险 API 特征列表（差集口径）。

    新增 = patched_code 命中特征 - original_code 命中特征。
    原代码已有的危险调用不拦截（与命名契约"放行既有"对偶口径）；
    空 / 解析失败返回 []（保守放行，由 safe_apply_patch 语法校验兜底）。

    Args:
        original_code: 补丁应用前原始代码。
        patched_code: 应用后的完整代码。

    Returns:
        新增危险特征列表（空 = 无新增危险 API，放行）。
    """
    if not original_code or not patched_code:
        return []
    before = _collect_dangerous_calls(original_code)
    after = _collect_dangerous_calls(patched_code)
    return sorted(after - before)


def _dangerous_api_guard_enabled() -> bool:
    """S2 安全守卫开关（PATCH_DANGEROUS_API_GUARD，默认 true）。

    与 PATCH_CONTRACT_CHECK 同模式（默认启用、可环境变量关闭）；
    设 false 时恒放行（历史对照场景）。
    """
    return os.getenv("PATCH_DANGEROUS_API_GUARD", "true").lower() == "true"


# ─── P0 1.3 契约验证：命名契约检查 ─────────────────────────────────────────


def _collect_module_level_symbols(source_code: str) -> set[str]:
    """收集模块级符号集合（P0 1.3 命名契约检查）。

    包含：
    - 所有顶层函数名（FunctionDef / AsyncFunctionDef）
    - 所有顶层类名（ClassDef）
    - __all__ 中列出的符号（若存在）
    - 带注册装饰器的函数/类名（@register, @plugin, @entry_point 等常见模式）
    - 模块级赋值常量名（`NAME = ...` 形式的顶层 Assign，Name target）

    这些符号构成"命名契约"：LLM 重写时不得删除/重命名这些符号，
    否则 import 链 / 插件注册 / 外部调用方会崩溃（sqlfluff 实测 5/7 失败根因）。

    Args:
        source_code: 原始 Python 源码。

    Returns:
        符号名集合。源码无法解析时返回空集（不阻断应用，由调用方决定策略）。
    """
    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return set()

    symbols: set[str] = set()

    # 顶层函数 / 类
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)

    # __all__ 列表
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    # 尝试提取字面量列表
                    value = node.value
                    if isinstance(value, (ast.List, ast.Tuple)):
                        for elt in value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                symbols.add(elt.value)
                    break

    # 模块级常量赋值（顶层 `X = ...`，X 为 Name 且非 dunder）
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and not target.id.startswith("__"):
                    symbols.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target = node.target
            if not target.id.startswith("__"):
                symbols.add(target.id)

    return symbols


def check_naming_contract(
    original_code: str,
    patched_code: str,
) -> tuple[bool, list[str]]:
    """P0 1.3 命名契约检查：补丁不得删除原代码中的模块级符号。

    对比修改前后的模块级符号集合（_collect_module_level_symbols 口径），
    若任何原符号在补丁后代码中缺失，返回 (False, [缺失符号列表])。
    新增符号不报错（允许 LLM 增加辅助函数），仅删除/重命名报错。

    开关：PATCH_CONTRACT_CHECK 环境变量（默认 true）。设 false 时本函数
    恒返回 (True, [])，由调用方（_patch_applier_node）直接跳过契约检查，
    保持历史单补丁口径（历史对照 / 合成集无契约场景）。

    Args:
        original_code: 原始代码。
        patched_code: 应用补丁后的代码。

    Returns:
        (通过?, 缺失符号列表)。解析失败或开关关闭时通过（不阻断，保守降级）。
    """
    if os.getenv("PATCH_CONTRACT_CHECK", "true").lower() != "true":
        return True, []
    if not original_code or not patched_code:
        return True, []
    original_symbols = _collect_module_level_symbols(original_code)
    patched_symbols = _collect_module_level_symbols(patched_code)
    if not original_symbols:
        return True, []
    missing = sorted(original_symbols - patched_symbols)
    if missing:
        logger.warning(
            "命名契约检查失败：补丁删除了 %d 个模块级符号 %s（P0 1.3）",
            len(missing),
            missing,
        )
        return False, missing
    return True, []


def safe_apply_patch_contract(
    code: str,
    patch: str,
    enforce_contract: bool | None = None,
) -> tuple[str, bool, list[str]]:
    """P0 1.3 契约验证补丁应用：safe_apply_patch + 命名契约检查。

    在 safe_apply_patch 的语法验证之上，增加模块级符号删除检查。
    契约检查失败时回滚原代码（与语法失败同口径），不引入半应用状态。

    Args:
        code: 原始代码。
        patch: LLM 生成的补丁代码。
        enforce_contract: 是否强制执行契约检查。None 时读环境变量
            PATCH_CONTRACT_CHECK（默认 true，保持 P0 1.3 行为）；
            显式传 False 跳过（历史对照 / 合成集无契约场景）。

    Returns:
        (应用后的代码, 是否成功, 缺失符号列表)。契约通过时缺失列表为空。
    """
    new_code, success = safe_apply_patch(code, patch)
    if not success:
        return code, False, []

    if enforce_contract is None:
        enforce_contract = os.getenv("PATCH_CONTRACT_CHECK", "true").lower() == "true"
    if not enforce_contract:
        return new_code, True, []

    ok, missing = check_naming_contract(code, new_code)
    if not ok:
        # 契约破坏 → 回滚（与语法失败同口径，保守不引入半应用状态）
        logger.info("命名契约破坏，回滚补丁（P0 1.3）：缺失 %s", missing)
        return code, False, missing
    return new_code, True, []


# ─── 1.3 改进：分层压缩降级链（符号守卫拒绝时逐级收紧上下文再生成）──────
# 三级降级链（与路线图 1.3 口径）：
#   L1 full_context      完整函数上下文（depth=CODE_FOCUS_DEPTH，AST 聚焦）
#   L2 patch_ingredients 补丁配方保留（目标函数完整 AST + 调用签名 + 导出
#                        契约符号 + 模块常量，即"最小充分子序列"）
#   L3 minimal          签名 + import 的极简上下文（仅契约符号与 import）
# L1 生成的补丁被命名契约守卫拒绝时自动降级 L2，L2 再被拒绝降级 L3——
# 每级在更高约束（契约符号显式注入 + 更低温度）下重新生成，
# 破坏命名契约的概率逐级降低。各层预算/温度：

_CONTEXT_TIER_BUDGETS: dict[str, int] = {
    "full_context": 3000,
    "patch_ingredients": 2500,
    "minimal": 1200,
}
# 降级链顺序（下标即降级方向；0 = 最宽上下文，2 = 最严格约束）
_CONTEXT_TIER_ORDER: tuple[str, ...] = ("full_context", "patch_ingredients", "minimal")
# 各层 LLM 温度（降级层用更严格的采样，减少"创造性改写"破坏契约）
_CONTEXT_TIER_TEMPERATURES: dict[str, float] = {
    "full_context": 0.2,
    "patch_ingredients": 0.1,
    "minimal": 0.0,
}


def _contract_context_tier_index() -> int:
    """1.3 降级链：读当前上下文档位（CONTEXT_TIER 环境变量）。

    取值 "0"/"1"/"2"（对应 _CONTEXT_TIER_ORDER 下标），非法/缺省为 0
    （默认 full_context，与历史单补丁口径一致——降级链仅在"被符号守卫
    拒绝"后由调用方经 advance_context_tier 推进）。
    """
    raw = os.getenv("CONTEXT_TIER", "0").strip()
    try:
        idx = int(raw)
    except ValueError:
        return 0
    if idx not in (0, 1, 2):
        return 0
    return idx


def advance_context_tier() -> int:
    """1.3 降级链：推进到下一层上下文档位，返回新档位下标。

    在符号守卫（check_naming_contract）拒绝当前补丁后调用：当前层
    （_CONTEXT_TIER_INDEX 进程内状态）+1，封顶 2（minimal 层不再降级，
    返回 2 表示"已到最严格层，重新生成仍被拒则放弃本轮"）。
    同时同步 CONTEXT_TIER 环境变量（跨进程口径，与 LLM 温度透传路径
    一致：同进程内 LLM 调用方读取 _current_context_tier() 获得新档位）。

    线程安全：--parallel 多任务共享进程时，用 _TIER_LOCK 保护
    "读-改-写"临界区（min(idx+1, 2) + os.environ 赋值），避免两任务
    并发推进时丢失一次 +1（最坏情形：降级链推进到错误档位，仍比
    "不推进"更保守——降级到更严格层不会破坏命名契约）。
    """
    global _CONTEXT_TIER_INDEX
    with _TIER_LOCK:
        _CONTEXT_TIER_INDEX = min(_CONTEXT_TIER_INDEX + 1, 2)
        os.environ["CONTEXT_TIER"] = str(_CONTEXT_TIER_INDEX)
        idx_now = _CONTEXT_TIER_INDEX
    logger.info("1.3 分层压缩降级链：上下文降级至第 %d 层（%s）", idx_now + 1, _CONTEXT_TIER_ORDER[idx_now])
    return idx_now


def _current_context_tier() -> tuple[str, int, float]:
    """返回 (档位名, 下标, 温度) 三元组（调用方构建 prompt 上下文时消费）。

    读路径同样加锁（与 advance_context_tier 的写路径配对，避免 GIL 之外的
    读-写交错导致读到中间值——虽然 CPython 下 int 读是原子的，但锁口径
    与写路径一致，便于未来扩展到"档位名+温度"原子读取）。
    """
    with _TIER_LOCK:
        idx = _CONTEXT_TIER_INDEX
    name = _CONTEXT_TIER_ORDER[idx]
    return name, idx, _CONTEXT_TIER_TEMPERATURES[name]


# 降级链档位的进程级临界区锁（--parallel 多任务共享进程时，advance 的
# 读-改-写 + os.environ 同步需原子；读路径同锁口径，避免中间值）
# P2-1（2026-10-02 审查）：_TIER_LOCK 须先于 _CONTEXT_TIER_INDEX 初始化
# 定义——加载期调用 advance_context_tier 时锁已就绪（历史顺序下锁在
# 初始化之后才定义，加载期调用会 NameError）。
_TIER_LOCK = threading.Lock()
_CONTEXT_TIER_INDEX = _contract_context_tier_index()


def build_tiered_context(
    original_code: str,
    target_function: str | None,
    tier: int | None = None,
) -> str:
    """1.3 分层压缩降级链：按档位构建注入 prompt 的代码上下文。

    档位（下标 → 内容）：
    - 0 full_context：完整函数上下文（extract_function_context，depth 取
      CODE_FOCUS_DEPTH 层调用链展开）；
    - 1 patch_ingredients：补丁配方保留片段（render_patch_ingredient_context，
      目标函数完整 AST + 调用签名 + 导出契约符号 + import + 模块常量）；
    - 2 minimal：极简上下文（仅 import 语句 + 契约符号名单 + 目标函数
      签名行——"最小充分"底线，约束最强、token 成本最低）。

    档位语义由 advance_context_tier 的显式推进决定：指定 L2 就构建 L2，
    不逐级 fallback（避免"调用方指定 L2"被静默替换成 L3 的语义漂移）。
    该档位构建失败（AST 解析失败等）时返回空串，调用方回退"全文件 +
    字符级截断"历史口径（保守降级，不阻断修复主流程）。

    Args:
        original_code: 原始被测代码。
        target_function: 目标函数名（None 时各层退化为"无焦点"口径）。
        tier: 档位下标（None 时读 _current_context_tier()）。

    Returns:
        该档位的上下文字符串（可能为空）。
    """
    idx = tier if tier is not None else _current_context_tier()[1]
    idx = max(0, min(2, idx))
    if not original_code:
        return ""
    # 1.3 关键正确性：各层必须按"指定档位"构建，**不逐级 fallback**。
    # 若 L2 构建失败（AST 解析失败等）逐级落到 L3 会让"调用方指定 L2"的
    # 语义被静默替换——降级链档位语义由 advance_context_tier 的显式推进
    # 决定，build 失败时返回空串让调用方回退"全文件 + 字符级截断"历史口径
    # （保守降级，不引入跨档位行为漂移）。
    if idx == 0:
        from src.tools.code_analyzer import extract_function_context

        # 保守降级：上下文无法解析（函数不存在/AST 解析失败）时返回空串，
        # 调用方回退"全文件 + 字符级截断"历史口径（见函数 docstring）
        return extract_function_context(original_code, target_function or "") or ""
    if idx == 1:
        from src.tools.code_analyzer import preserve_patch_ingredients, render_patch_ingredient_context

        ingredients = preserve_patch_ingredients(original_code, target_function or None)
        return render_patch_ingredient_context(ingredients)
    # L3 minimal：仅 import + 契约符号名单 + 目标函数签名行
    from src.tools.code_analyzer import preserve_patch_ingredients

    ingredients = preserve_patch_ingredients(original_code, target_function or None)
    parts: list[str] = []
    imports = ingredients.get("imports") or ""
    if imports:
        parts.append(f"imports:\n{imports}")
    symbols: list[str] = []
    symbols.extend(ingredients.get("exports") or [])
    symbols.extend(ingredients.get("register_symbols") or [])
    if symbols:
        parts.append(f"must_keep_symbols: {', '.join(sorted(set(symbols)))}")
    sigs = ingredients.get("called_signatures") or []
    target_ast = ingredients.get("target_ast") or ""
    # 目标函数仅保留 def 行（首行）+ 调用签名（已含 def 行）
    if target_ast:
        first_line = target_ast.splitlines()[0]
        parts.append(f"target_signature:\n{first_line}")
    if sigs:
        parts.append("called_signatures:\n" + "\n".join(sigs))
    if not parts:
        return ""
    return "[MINIMAL_CONTEXT]\n" + "\n\n".join(parts)


def generate_diff(old_code: str, new_code: str) -> str:
    """
    生成 unified diff 格式的补丁。

    使用 difflib 生成标准的 unified diff，包含上下文行。

    Args:
        old_code: 原始代码
        new_code: 修改后的代码

    Returns:
        unified diff 格式的字符串
    """
    old_lines = old_code.splitlines(keepends=True)
    new_lines = new_code.splitlines(keepends=True)

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile="original",
        tofile="modified",
        n=3,  # 3行上下文
    )

    return "".join(diff)


# ─── 2.2 补丁后处理重采样策略（AST 解析验证 + 一次重采样）────────────────────
# 参考已有研究：对代码编辑任务，替换后的代码需通过语法检查（AST 解析）。
# 补丁应用后立即做 AST 解析验证，解析失败则触发一次重采样（带负面反馈），
# 确保 LLM 产出的补丁是语法合法的 Python。


def _patch_ast_valid(code: str) -> bool:
    """AST 解析验证：代码是否为语法合法的 Python。"""
    if not code or not code.strip():
        return False
    try:
        ast.parse(code)
        return True
    except (SyntaxError, ValueError):
        return False


def apply_patch_with_resample(
    original_code: str,
    patch: str,
    resample_fn: Any = None,
    max_resamples: int = 1,
) -> tuple[str, bool, dict[str, Any]]:
    """2.2 补丁后处理重采样策略：应用补丁 + AST 解析验证 + 失败重采样。

    流程：
    1. 应用补丁（apply_patch_to_code）；
    2. 应用后立即对结果做 AST 解析验证（语法合法性）；
    3. 解析失败 → 调用 resample_fn（LLM 重采样回调）重新生成一次补丁，
       再次应用 + 再次 AST 验证；
    4. 重采样后仍失败 → 返回原代码 + 失败标记（保守不引入半应用状态）。

    设计约束（与 safe_apply_patch 同口径）：
    - 任何失败路径都返回原代码，不引入半应用状态；
    - resample_fn 为 None 时跳过重采样（仅做 AST 验证），保持历史行为；
    - 最多 max_resamples 次重采样（默认 1，避免 LLM 反复生成相同错误）。

    Args:
        original_code: 原始代码。
        patch: LLM 生成的补丁代码。
        resample_fn: 可选 LLM 重采样回调 (query: str, original_code: str,
            patch: str, ast_error: str) → str（返回修订后的新补丁）。
            调用方注入（如 DebuggerAgent 的 _call_llm_with_cache + 负面反馈），
            避免本模块直接依赖 LLM 客户端（保持零硬依赖、可测试）。
        max_resamples: 最大重采样次数（默认 1）。

    Returns:
        (应用后的代码, 是否成功, 后处理统计 dict)。
        统计 dict 键：
        - ast_valid: bool（首次应用后 AST 是否合法）
        - resampled: bool（是否触发了重采样）
        - resample_count: int（实际重采样次数）
        - success: bool（最终是否成功应用且 AST 合法）
    """
    stats: dict[str, Any] = {"ast_valid": False, "resampled": False, "resample_count": 0, "success": False}

    # Step 0: 空补丁 / 全空白补丁短路（P0 性能优化 2026-10-01）
    # 空补丁既无法应用也无法被 LLM"修订"出有效内容——早退避免触发
    # resample_fn（真实 LLM 调用含指数退避时单次可 50s+），消除
    # 全量测试套件中该路径的 100s 级耗时瓶颈。
    # 返回 applied=False（空补丁不构成有效修复），ast_valid=False。
    if not patch or not patch.strip():
        stats["ast_valid"] = False
        return original_code, False, stats

    # Step 1: 首次应用
    new_code, applied = apply_patch_to_code(original_code, patch)
    stats["ast_valid"] = _patch_ast_valid(new_code)
    if applied and stats["ast_valid"]:
        stats["success"] = True
        return new_code, True, stats

    # Step 2: 首次失败（未应用 或 AST 不合法）→ 尝试重采样
    if not resample_fn:
        # 未注入重采样回调：保守返回原代码（保持历史行为）
        return original_code, applied and stats["ast_valid"], stats

    # 构造负面反馈（把 AST 错误信息注入 prompt，引导 LLM 修正）
    # getattr(e, "msg", e)：SyntaxError 有 .msg，ValueError 无 → 回退到 str(e)
    ast_err = ""
    if applied:
        try:
            ast.parse(new_code)
        except (SyntaxError, ValueError) as e:
            ast_err = f"补丁应用后的代码语法错误：{getattr(e, 'msg', e)}（行 {getattr(e, 'lineno', 0)}）"
    else:
        ast_err = "补丁未能成功应用到原始代码（无法定位目标函数或函数名不匹配）"

    for i in range(max_resamples):
        try:
            new_patch = resample_fn(
                f"【补丁重采样（第 {i + 1} 次）】以下补丁存在 {ast_err}，"
                f"请重新生成一个语法合法且能成功应用的修复补丁。"
                f"只输出代码块，不要其他文本。\n当前补丁：\n```\n{patch[:1500]}\n```",
                original_code,
                patch,
                ast_err,
            )
        except Exception as e:
            logger.warning("2.2 重采样回调异常（停止重采样）: %s", e)
            break
        if not new_patch:
            break
        stats["resampled"] = True
        stats["resample_count"] = i + 1
        patch = new_patch
        # 重新应用 + AST 验证
        new_code, applied = apply_patch_to_code(original_code, patch)
        stats["ast_valid"] = _patch_ast_valid(new_code)
        if applied and stats["ast_valid"]:
            stats["success"] = True
            logger.info("2.2 重采样第 %d 次成功，补丁已修订并通过 AST 验证", i + 1)
            return new_code, True, stats
        # 仍失败：更新错误信息供下一次重采样
        try:
            ast.parse(new_code)
        except (SyntaxError, ValueError) as e:
            ast_err = f"重采样后的补丁仍有语法错误：{getattr(e, 'msg', e)}（行 {getattr(e, 'lineno', 0)}）"
        else:
            ast_err = "重采样后的补丁仍未能成功应用"

    # 所有重采样都失败：保守返回原代码（不引入半应用状态）
    logger.warning("2.2 重采样 %d 次后仍失败，保留原代码", stats["resample_count"])
    return original_code, False, stats
