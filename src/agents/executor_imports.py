"""
导入路径自动修复：模块名提取、模块路径解析、sys.path 注入、相似名替换。

拆分自 executor.py（结构优化轮次）：ExecutorAgent 的导入修复子系统独立成模块，
executor.py 仅保留执行编排逻辑。函数均为纯函数，签名与返回值不变。
"""

from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

from src.tools.dependency import extract_import_module_names, is_standard_library

logger = logging.getLogger(__name__)

# 提取模块名（无扩展名）
_RE_MODULE_NAME = re.compile(r"([^/\\]+)\.py$")


def extract_module_name_from_file(target_file: str) -> str:
    """
    从文件路径提取模块名（不含扩展名）。

    Args:
        target_file: 被测代码文件路径。

    Returns:
        模块名称（如 'calculator' 从 'examples/calculator.py'）。
    """
    # 使用预编译的正则表达式提取模块名
    match = _RE_MODULE_NAME.search(target_file)
    if match:
        return match.group(1)
    # 备用方案：使用 os.path.splitext
    return os.path.splitext(os.path.basename(target_file))[0]


@lru_cache(maxsize=256)
def cached_search_module_path(module_name: str, root_path_str: str, max_depth: int) -> tuple[str, ...]:
    """
    缓存版本的模块路径搜索（优化高频调用场景）。

    使用 LRU 缓存避免重复搜索相同模块，显著提升性能。

    Args:
        module_name: 模块名称（不含 .py 后缀）。
        root_path_str: 项目根目录路径（字符串形式，用于缓存键）。
        max_depth: 最大搜索深度，默认 3 层。

    Returns:
        匹配的目录路径元组（去重）。
    """
    root_path = Path(root_path_str)
    matched_dirs = set()

    # 策略 1：直接匹配文件名
    py_file = root_path / f"{module_name}.py"
    if py_file.exists():
        matched_dirs.add(str(py_file.parent))
        return tuple(matched_dirs)

    # 策略 2：检查常见子目录
    common_dirs = ["src", "lib", "tests", "."]
    for common_dir in common_dirs:
        candidate = root_path / common_dir / f"{module_name}.py"
        if candidate.exists():
            matched_dirs.add(str(candidate.parent))
            return tuple(matched_dirs)

    # 策略 3：深度限制的 rglob 搜索
    for found_file in root_path.rglob(f"{module_name}.py"):
        rel_parts = found_file.relative_to(root_path).parts
        if len(rel_parts) <= max_depth:
            matched_dirs.add(str(found_file.parent))
            break

    # 策略 4：查找包目录
    pkg_dir = root_path / module_name
    if pkg_dir.is_dir() and (pkg_dir / "__init__.py").exists():
        matched_dirs.add(str(pkg_dir))

    return tuple(matched_dirs)


def auto_fix_imports(test_code: str, target_file: str, project_root: str) -> str:
    """
    自动修复模块导入路径（优化版）。

    分析测试代码中的 import 语句，动态添加 sys.path，解决 ModuleNotFoundError。
    支持两种场景：
    1. 模块名与文件名匹配：添加对应的目录到 sys.path
    2. 模块名与文件名不匹配：替换导入语句中的模块名为实际文件名

    Args:
        test_code: 原始测试代码。
        target_file: 被测代码文件路径。
        project_root: 项目根目录。

    Returns:
        修复后的测试代码（如无需修改则返回原代码）。
    """
    imports = extract_imports(test_code)
    if not imports:
        return test_code

    actual_module_name = extract_module_name_from_file(target_file)
    module_dirs, needs_replacement = resolve_module_paths(imports, actual_module_name, project_root, target_file)

    if not module_dirs and not needs_replacement:
        return test_code

    sys_path_code = build_sys_path_code(module_dirs)
    fixed_code = apply_import_replacements(test_code, imports, actual_module_name, needs_replacement)

    if sys_path_code:
        fixed_code = f"{sys_path_code}\n\n{fixed_code}\n"

    return fixed_code


def extract_imports(test_code: str) -> list[str]:
    """提取测试代码中的非标准库导入模块名（排除相对导入）。

    底层复用 dependency.extract_import_module_names 的单一实现：
    逗号分隔多模块导入（import numpy, scipy）完整捕获——此前本地复制的
    正则 ^import\\s+([\\w.]+) 只取首个模块，缺失的后续模块逃过依赖检测。

    标准库判定复用 dependency.is_standard_library（sys.stdlib_module_names
    权威清单），并显式跳过 pytest（测试运行器始终可用，无需导入路径修复）。
    此前硬编码 frozenset 已删除（含误列第三方 diskcache 的清单漂移）。
    """
    imports = []
    for module_name in extract_import_module_names(test_code):
        top_level = module_name.split(".")[0]
        if not is_standard_library(top_level) and top_level != "pytest":
            imports.append(module_name)
    return imports


def resolve_module_paths(
    imports: list[str], actual_module_name: str, project_root: str, target_file: str
) -> tuple[set, bool]:
    """根据导入列表解析模块路径，返回 (module_dirs, needs_replacement)。"""
    module_dirs = set()
    needs_replacement = False
    _MAX_SEARCH_DEPTH = 3

    for module_name in imports:
        found_dirs = cached_search_module_path(module_name, project_root, _MAX_SEARCH_DEPTH)
        if found_dirs:
            module_dirs.update(found_dirs)
        elif module_name != actual_module_name:
            needs_replacement = True
            target_dir = os.path.dirname(os.path.abspath(target_file))
            module_dirs.add(target_dir)

    return module_dirs, needs_replacement


def build_sys_path_code(module_dirs: set) -> str:
    """生成 sys.path 修改代码（import sys 只出现一次，避免原实现的重复导入）。"""
    inserts = "\n".join(f"sys.path.insert(0, {d!r})" for d in sorted(module_dirs))
    return f"import sys\n{inserts}"


def is_similar_module_name(imported_module: str, actual_module_name: str) -> bool:
    """判断导入名是否为被测模块名的"笔误"变体（大小写/缩写/近形名）。

    仅对相似名称做替换，避免把 numpy、requests 等第三方库导入
    错误地改写为被测模块名（原实现对所有未解析导入无差别替换）。

    Args:
        imported_module: 测试代码中的导入模块名。
        actual_module_name: 被测文件实际模块名。

    Returns:
        True 表示应替换为目标模块名。
    """
    a = imported_module.lower()
    b = actual_module_name.lower()
    if a == b:
        return True
    # 相似度阈值 0.6：覆盖常见笔误（如 calc vs calculator），
    # 同时排除无关名称（如 numpy vs calculator 相似度仅约 0.13）
    return SequenceMatcher(None, a, b).ratio() >= 0.6


def apply_import_replacements(
    test_code: str, imports: list[str], actual_module_name: str, needs_replacement: bool
) -> str:
    """对测试代码应用导入替换，返回修改后的代码。

    仅替换与被测模块名相似的导入（is_similar_module_name 门控），
    并按模块名精确锚定正则，避免原实现"一条正则改写全部 import"
    导致的第三方库导入被误替换问题。
    """
    fixed_code = test_code
    if needs_replacement and imports:
        replaced_any = False
        for imported_module in imports:
            if imported_module == actual_module_name:
                continue
            if not is_similar_module_name(imported_module, actual_module_name):
                # 无关模块（如第三方库）保持原样，不改写
                continue
            # 按模块名锚定，仅替换该模块的导入语句
            from_pattern = re.compile(rf"^from\s+{re.escape(imported_module)}\s+import", re.MULTILINE)
            fixed_code = from_pattern.sub(f"from {actual_module_name} import", fixed_code)
            import_pattern = re.compile(rf"^import\s+{re.escape(imported_module)}\s*$", re.MULTILINE)
            fixed_code = import_pattern.sub(f"import {actual_module_name}", fixed_code)
            replaced_any = True
            logger.info("模块名不匹配，已将导入 '%s' 替换为 '%s'", imported_module, actual_module_name)
        if not replaced_any:
            logger.debug("无需替换：未发现与目标模块相似的错误导入名")
    return fixed_code
