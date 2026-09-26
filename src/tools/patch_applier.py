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

from src.utils.helpers import extract_code_block

logger = logging.getLogger(__name__)

# ─── 预编译正则（模块级单例，避免热路径重复编译）─────────────────────────────────
# 0.8 性能：全文扫描类函数（_is_full_file_patch / apply_patch_to_code 单函数
# 模式）原本每次调用现场 re.compile 4~6 遍，--parallel 多任务下累积可观。
# 全模式（无捕获组需求）提取为模块级常量；按函数名定制的边界定位正则仍按名
# 编译（数量少、re 内部 LRU 命中）。
_DEF_RE = re.compile(r"def\s+(\w+)\s*\(")
_TOP_DEF_RE = re.compile(r"^def\s+\w+\s*\(", re.MULTILINE)
_TRIPLE_QUOTE_RE = re.compile(r'^"""')
_PYTHON_PREFIX_RE = re.compile(r"^python\s*\n?", re.IGNORECASE)
# 正则兜底路径的函数边界探测（_find_function_range 热循环内不再逐次编译）
_BOUNDARY_RE = re.compile(r"^(def |class |@|#)")


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
        (b) 前 200 字符含 import 语句 → 含导入，说明是完整文件而非单函数补丁
        (c) 补丁含 >=2 个函数定义 且 原代码也含 >=2 个函数 → 多函数补丁

    Args:
        clean_patch: 清理后的补丁代码。
        original_code: 原始代码。

    Returns:
        True 表示使用完整文件模式，False 表示使用单函数模式。
    """
    has_docstring = bool(_TRIPLE_QUOTE_RE.match(clean_patch))
    has_import = "import " in clean_patch[:200]
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
        func_name: 目标函数名（顶层 def，非嵌套）。

    Returns:
        (start_lineno, end_lineno) 1-based 闭区间（ast 行号）；
        未找到顶层同名函数或代码无法解析时返回 None（调用方回退正则路径）。
    """
    try:
        tree = ast.parse(original_code)
    except SyntaxError:
        return None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            # end_lineno 在 Python 3.8+ 恒有；兜底取 body 末行。
            # getattr 回退取 int（运行期 3.8+ 必有该属性，mypy 按 stub 的
            # Optional[int] 报 None 分支，显式 `or node.lineno` 收窄为 int）
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

        # 验证补丁包含原代码的全部函数（防止部分替换导致函数丢失）
        if orig_func_names and orig_func_names.issubset(patch_func_names):
            # 追加换行符确保代码以换行结尾（PEP 8 风格）
            return clean_patch + "\n", True

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
        # 按名编译的边界定位正则（数量少；re 内部 LRU 命中后零编译开销）
        func_def_re = re.compile(rf"^def\s+{re.escape(patch_func_name)}\s*\(")
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


def _find_function_start_line(code: str, func_name: str) -> int:
    """
    查找函数在代码中的起始行号。

    Args:
        code: Python 代码字符串
        func_name: 函数名

    Returns:
        函数起始行号（从0开始），未找到返回 -1
    """
    return _find_function_start_line_in_lines(code.split("\n"), func_name)


def _find_function_start_line_in_lines(code_lines: list[str], func_name: str) -> int:
    """按预切分的行查找函数起始行号（P13 性能优化：供批量排序 key 复用，避免每个
    patch 都重新 split 一遍代码）。

    Args:
        code_lines: 代码行列表（code.split("\\n") 的结果）。
        func_name: 函数名。

    Returns:
        函数起始行号（从0开始），未找到返回 -1。
    """
    # 预编译函数定义匹配正则（避免逐行重复编译）
    func_def_re = re.compile(rf"^def\s+{re.escape(func_name)}\s*\(")
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
        return new_code, True
    except SyntaxError:
        # 语法错误，回滚到原始代码
        return code, False


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
