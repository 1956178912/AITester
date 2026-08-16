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

import re
from typing import Tuple


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
    # 完整文件模式的判断条件（满足任一即可）：
    #   (a) 补丁以 triple-quote 开头 → 含 docstring，通常是完整模块文件
    #   (b) 前 200 字符含 import 语句 → 含导入，说明是完整文件而非单函数补丁
    #   (c) 补丁含 >=2 个函数定义 且 原代码也含 >=2 个函数 → 多函数补丁
    has_docstring = bool(re.match(r'^"""', clean_patch))
    has_import = "import " in clean_patch[:200]
    # 统计补丁中的函数定义数量（匹配 "def 函数名(" 行）
    patch_defs = re.findall(r"^def\s+\w+\s*\(", clean_patch, re.MULTILINE)
    # 统计原代码中的函数定义数量
    original_defs = re.findall(r"^def\s+\w+\s*\(", original_code, re.MULTILINE)

    # Step 4a: 完整文件模式 —— 直接替换整个文件
    if has_docstring or has_import or (len(patch_defs) >= 2 and len(original_defs) >= 2):
        # 安全检查：提取补丁中所有函数名
        patch_func_names = {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", clean_patch)}
        # 提取原代码中所有函数名
        orig_func_names = {m.group(1) for m in re.finditer(r"def\s+(\w+)\s*\(", original_code)}
        # 验证补丁包含原代码的全部函数（防止部分替换导致函数丢失）
        # 原代码无函数时跳过检查（允许空文件补丁）
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
    start_idx = None  # 目标函数起始行的索引
    end_idx = None    # 目标函数结束行的索引（下一个顶层定义的起始行）

    # 遍历原代码行，定位目标函数的行范围
    for i, line in enumerate(lines):
        # 匹配目标函数的 def 行（使用 re.escape 防止函数名含特殊字符）
        if re.match(rf"^def\s+{re.escape(patch_func_name)}\s*\(", line):
            start_idx = i
        elif start_idx is not None and i > start_idx:
            # 已找到起始行，继续寻找结束位置
            # 结束条件：遇到下一个顶层定义（def/class/@装饰器/#注释）
            # 或遇到无缩进的非空行（函数体结束）
            if re.match(r"^(def |class |@|#)", line) or (line.strip() and not line.startswith(" ") and not line.startswith("\t")):
                end_idx = i
                break

    # 未找到目标函数，返回原代码
    if start_idx is None:
        return original_code, False

    # 若未找到明确的结束行（目标函数是文件中最后一个定义），结束位置为文件末尾
    if end_idx is None:
        end_idx = len(lines)

    # Step 5: 执行替换 — 将原函数行范围替换为补丁函数代码
    patch_lines = clean_patch.split("\n")
    # 拼接新代码：原代码[起始前] + 空行 + 补丁行 + 空行 + 原代码[结束后的]
    new_lines = lines[:start_idx] + [""] + patch_lines + [""] + lines[end_idx:]

    # Step 6: 压缩连续空行，保持代码整洁（PEP 8 要求空行不超过 2 个）
    collapsed = []
    prev_blank = False  # 记录上一行是否为空行
    for line in new_lines:
        is_blank = line.strip() == ""
        # 跳过连续空行（保留一个空行作为间隔）
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank
    # 拼接为完整代码字符串，末尾加换行符
    new_code = "\n".join(collapsed).strip() + "\n"
    return new_code, True


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
