"""
补丁应用工具：将 LLM 生成的修复代码应用到原始代码。
支持两种格式：
1. 完整文件代码：直接用补丁替换原代码
2. 单个函数定义：定位并替换对应函数
"""

from __future__ import annotations

import re
from typing import Tuple


def apply_patch_to_code(original_code: str, patch: str) -> Tuple[str, bool]:
    """
    将补丁代码应用到原始代码。

    Args:
        original_code: 原始被测代码。
        patch: LLM 生成的修复代码（可能包含 ```python 标记，或完整文件）。

    Returns:
        (修复后的代码, 是否成功应用)
    """
    clean_patch = _extract_patch_code(patch)
    if not clean_patch:
        return original_code, False

    # 移除可能的 "python" 前缀（LLM 有时输出不带反引号的格式）
    clean_patch = re.sub(r"^python\s*\n?", "", clean_patch, flags=re.IGNORECASE)

    # 检测补丁是否为完整文件（包含文档字符串、import 或多函数）
    has_docstring = bool(re.match(r'^"""', clean_patch))
    has_import = "import " in clean_patch[:200]
    patch_defs = re.findall(r"^def\s+\w+\s*\(", clean_patch, re.MULTILINE)
    original_defs = re.findall(r"^def\s+\w+\s*\(", original_code, re.MULTILINE)

    # 如果补丁是完整文件（有 docstring/import 或多函数），直接替换
    if has_docstring or has_import or (len(patch_defs) >= 2 and len(original_defs) >= 2):
        patch_func_names = {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", clean_patch)}
        orig_func_names = {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", original_code)}
        if orig_func_names and orig_func_names.issubset(patch_func_names):
            return clean_patch + "\n", True

    # 单函数替换模式
    func_match = re.search(r"def\s+(\w+)\s*\(", clean_patch)
    if not func_match:
        return original_code, False

    patch_func_name = func_match.group(1)
    lines = original_code.split("\n")
    start_idx = None
    end_idx = None

    for i, line in enumerate(lines):
        if re.match(rf"^def\s+{re.escape(patch_func_name)}\s*\(", line):
            start_idx = i
        elif start_idx is not None and i > start_idx:
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
    """从 LLM 输出中提取补丁代码。"""
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
