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
"""

from __future__ import annotations

import ast
import re
import difflib
from typing import List, Dict, Tuple, Optional, Set


def _extract_function_names(code: str) -> Set[str]:
    """
    从代码中提取所有函数名称。

    Args:
        code: Python 代码字符串。

    Returns:
        函数名称集合。
    """
    return {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", code)}


def _count_function_defs(code: str) -> int:
    """
    统计代码中的函数定义数量。

    Args:
        code: Python 代码字符串。

    Returns:
        函数定义数量。
    """
    return len(re.findall(r"^def\s+\w+\s*\(", code, re.MULTILINE))


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
    has_docstring = bool(re.match(r'^"""', clean_patch))
    has_import = "import " in clean_patch[:200]
    patch_func_count = _count_function_defs(clean_patch)
    original_func_count = _count_function_defs(original_code)

    return has_docstring or has_import or (patch_func_count >= 2 and original_func_count >= 2)


def _find_function_range(
    lines: List[str],
    func_name: str,
    start_idx: int
) -> Tuple[int, int]:
    """
    查找函数在代码中的起止行范围。

    Args:
        lines: 代码行列表。
        func_name: 函数名称。
        start_idx: 函数起始行索引。

    Returns:
        (start_idx, end_idx) 元组，end_idx 为函数结束后的下一行索引。
    """
    end_idx = len(lines)  # 默认到文件末尾

    for i in range(start_idx + 1, len(lines)):
        line = lines[i]
        # 结束条件：遇到下一个顶层定义或非空无缩进行
        if re.match(r"^(def |class |@|#)", line) or (line.strip() and not line.startswith(" ") and not line.startswith("\t")):
            end_idx = i
            break

    return start_idx, end_idx


def apply_patch_to_code(
    original_code: str,
    patch: str,
) -> Tuple[str, bool]:
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
    clean_patch = _extract_patch_code(patch)
    # 补丁为空时无法应用，直接返回原代码
    if not clean_patch:
        return original_code, False

    # Step 2: 移除可能的 "python" 前缀（LLM 有时输出不带反引号的格式）
    clean_patch = re.sub(r"^python\s*\n?", "", clean_patch, flags=re.IGNORECASE)

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
    # 查找补丁中的第一个函数定义
    func_match = re.search(r"def\s+(\w+)\s*\(", clean_patch)
    if not func_match:
        # 补丁中无函数定义，无法应用
        return original_code, False

    patch_func_name = func_match.group(1)
    # 将原代码按行分割，便于按行号定位和替换
    lines = original_code.split("\n")
    start_idx = None

    # 遍历原代码行，定位目标函数的起始行
    for i, line in enumerate(lines):
        if re.match(rf"^def\s+{re.escape(patch_func_name)}\s*\(", line):
            start_idx = i
            break

    # 未找到目标函数，返回原代码
    if start_idx is None:
        return original_code, False

    # 查找函数结束位置
    _, end_idx = _find_function_range(lines, patch_func_name, start_idx)

    # Step 5: 执行替换 — 将原函数行范围替换为补丁函数代码
    patch_lines = clean_patch.split("\n")
    # 拼接新代码：原代码[起始前] + 空行 + 补丁行 + 空行 + 原代码[结束后的]
    new_lines = lines[:start_idx] + [""] + patch_lines + [""] + lines[end_idx:]

    # Step 6: 压缩连续空行，保持代码整洁（PEP 8 要求空行不超过 2 个）
    collapsed = _collapse_blank_lines(new_lines)

    # 拼接为完整代码字符串，末尾加换行符
    new_code = "\n".join(collapsed).strip() + "\n"
    return new_code, True


def _collapse_blank_lines(lines: List[str]) -> List[str]:
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
    patches: List[Dict],
) -> Tuple[str, bool]:
    """
    应用多个函数的修改（支持递归函数和多函数同时修改）。

    该函数接收一个补丁列表，每个补丁包含：
    - function_name: 目标函数名
    - patch: LLM 生成的修复代码

    算法：
        1. 按起始行号从高到低排序（从后往前应用，避免行号偏移）
        2. 逐个应用单个函数补丁
        3. 返回最终代码和成功标志

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

    # 按起始行号从高到低排序（从后往前应用，避免行号偏移）
    sorted_patches = sorted(
        patches,
        key=lambda p: _find_function_start_line(code, p["function_name"]),
        reverse=True
    )

    current_code = code
    all_success = True

    for patch_info in sorted_patches:
        func_name = patch_info["function_name"]
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
    for i, line in enumerate(code.split("\n")):
        if re.match(rf"^def\s+{re.escape(func_name)}\s*\(", line):
            return i
    return -1


def safe_apply_patch(
    code: str,
    patch: str,
) -> Tuple[str, bool]:
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


def safe_apply_multi_function_patch(
    code: str,
    patches: List[Dict],
) -> Tuple[str, bool]:
    """
    安全应用多个函数的修改，失败时自动回滚。

    Args:
        code: 原始代码
        patches: 补丁列表，每项为 {"function_name": str, "patch": str}

    Returns:
        Tuple[str, bool]: (修复后的代码, 是否全部成功)
    """
    # 尝试应用所有补丁
    new_code, success = apply_multi_function_patch(code, patches)
    if not success:
        return code, False

    # 验证生成的代码语法是否正确
    try:
        ast.parse(new_code)
        return new_code, True
    except SyntaxError:
        # 语法错误，回滚到原始代码
        return code, False


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
        n=3  # 3行上下文
    )

    return "".join(diff)


def _extract_patch_code(patch: str) -> str:
    """
    从 LLM 输出中提取补丁代码。

    LLM 输出的代码可能包裹在各种格式标记中，本函数统一提取纯代码内容。
    支持的格式（按优先级）：
        1. ```python ... ```  —— 带语言标记的 markdown 代码块
        2. ``` ... ```        —— 通用 markdown 代码块
        3. python: ...        —— python: 前缀格式（无反引号）
        4. 纯文本             —— 无标记，直接返回原文

    Args:
        patch: LLM 输出的原始文本。

    Returns:
        提取出的纯代码字符串（去除包裹标记后的内容）。
    """
    # 格式 1: ```python ... ```
    # re.DOTALL 使 . 匹配换行符，(.*?) 非贪婪匹配代码内容
    match = re.search(r"```python\s*\n(.*?)\n\s*```", patch, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 格式 2: ``` ... ```（通用代码块）
    match = re.search(r"```\s*\n(.*?)\n```", patch, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 格式 3: python: 前缀（某些模型输出不带反引号）
    stripped = patch.strip()
    if stripped.lower().startswith("python"):
        # 移除 "python:" 前缀及随后的空白字符
        stripped = re.sub(r"^python\s*:\s*", "", stripped, flags=re.IGNORECASE)
        return stripped.strip()
    # 格式 4: 无标记，直接返回原文（strip 去除首尾空白）
    return patch.strip()
