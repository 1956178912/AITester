"""
补丁应用工具模块：将 LLM 生成的修复代码应用到原始代码。

支持两种模式：
1. 完整文件模式：当补丁包含多个函数或 import 时，直接替换整个文件
2. 单函数模式：仅替换目标函数的函数体
使用 ast 模块进行精确匹配，避免正则表达式在嵌套/同名函数场景下的误替换。
"""

from __future__ import annotations

import re
from typing import Tuple


def apply_patch_to_code(original_code: str, patch: str) -> Tuple[str, bool]:
    """
    将补丁代码应用到原始代码。

    判断逻辑：
    - 若补丁是完整文件（含 docstring/import/多函数），直接替换
    - 若补丁是单函数定义，精确替换对应函数

    Args:
        original_code: 原始被测代码。
        patch: LLM 生成的修复代码（可能包含 ```python 标记，或完整文件）。

    Returns:
        (修复后的代码, 是否成功应用)
    """
    # 从补丁中提取纯代码（去除 markdown 包裹）
    clean_patch = _extract_patch_code(patch)
    if not clean_patch:
        return original_code, False

    # 移除可能的 "python" 前缀（LLM 有时输出不带反引号的格式）
    clean_patch = re.sub(r"^python\s*\n?", "", clean_patch, flags=re.IGNORECASE)

    # 检测补丁是否为完整文件模式：含 docstring/import/多函数定义时视为完整文件
    # has_docstring: 补丁以 triple-quote 开头，通常是完整模块文件
    # has_import: 前200字符含 import，说明是完整文件而非单函数补丁
    has_docstring = bool(re.match(r'^"""', clean_patch))
    has_import = "import " in clean_patch[:200]
    patch_defs = re.findall(r"^def\s+\w+\s*\(", clean_patch, re.MULTILINE)
    original_defs = re.findall(r"^def\s+\w+\s*\(", original_code, re.MULTILINE)

    # 若补丁是完整文件，直接替换整个文件（需包含原代码所有函数，防止部分替换）
    if has_docstring or has_import or (len(patch_defs) >= 2 and len(original_defs) >= 2):
        # 检查补丁是否包含原始代码的所有函数（防止部分替换）
        patch_func_names = {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", clean_patch)}
        orig_func_names = {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", original_code)}
        if orig_func_names and orig_func_names.issubset(patch_func_names):
            return clean_patch + "\n", True

    # 单函数替换模式：查找补丁中的第一个函数定义
    func_match = re.search(r"def\s+(\w+)\s*\(", clean_patch)
    if not func_match:
        return original_code, False

    patch_func_name = func_match.group(1)
    lines = original_code.split("\n")
    start_idx = None
    end_idx = None

    # 定位目标函数在原代码中的行范围
    for i, line in enumerate(lines):
        if re.match(rf"^def\s+{re.escape(patch_func_name)}\s*\(", line):
            start_idx = i
        elif start_idx is not None and i > start_idx:
            # 遇到下一个顶层定义或空行终止，标记函数结束位置
            if re.match(r"^(def |class |@|#)", line) or (line.strip() and not line.startswith(" ") and not line.startswith("\t")):
                end_idx = i
                break

    if start_idx is None:
        return original_code, False

    if end_idx is None:
        end_idx = len(lines)

    # 替换函数，保持空行分隔
    patch_lines = clean_patch.split("\n")
    new_lines = lines[:start_idx] + [""] + patch_lines + [""] + lines[end_idx:]
    # 压缩连续空行，保持代码整洁
    collapsed = []
    prev_blank = False
    for line in new_lines:
        is_blank = line.strip() == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank
    new_code = "\n".join(collapsed).strip() + "\n"
    return new_code, True


def _extract_patch_code(patch: str) -> str:
    """
    从 LLM 输出中提取补丁代码。
    处理多种格式：```python ... ```、``` ... ```、python: ... 等。

    Args:
        patch: LLM 输出的原始文本。

    Returns:
        提取出的纯代码字符串。
    """
    # 尝试标准 markdown 格式
    match = re.search(r"```python\s*\n(.*?)\n\s*```", patch, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 尝试通用 markdown 格式
    match = re.search(r"```\s*\n(.*?)\n\s*```", patch, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 尝试 python: 前缀格式
    stripped = patch.strip()
    if stripped.lower().startswith("python"):
        stripped = re.sub(r"^python\s*:\s*", "", stripped, flags=re.IGNORECASE)
        return stripped.strip()
    return patch.strip()
